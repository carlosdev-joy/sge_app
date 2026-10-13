"""UX profissional do Pipeline — F2 (descoberta e entrada única).

Camadas:
- bancada (tests/js/pipeline_index_harness.cjs): lib/pipelineIndex pura e as telas
  reais PipelineCatalog, Pipelines (portão da coorte) e PipelineCreate;
- contrato estrutural do índice .NET/SQL (endpoint, RBAC sem tela_jobs, SQL com
  igualdade pela collation, uma linha por pipeline, posse só válida e resumo de
  todo leitor autorizado, leitura sem transação serializável, lote em instruções curtas que não seguram
  lock de rascunho, posse, pipeline gerido ou publicação enquanto esperam, posse capturada por último e
  filtrada por um corte UTC único, vítima de deadlock em LOW num pool próprio com repetição
  só da 1205) — os testes executáveis ficam em
  backend-dotnet/Orquestra.Tests/PipelineIndexTests.cs e PipelineIndexRetryTests.cs (offline) e
  PipelineIndexSqlTests.cs (SQL real, bancada autorizada);
- migration de versão sequencial.
Navegador real, SQL vivo e DEV ficam para QA/root.
"""
import json
import re
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DOTNET = ROOT / "backend-dotnet"


@lru_cache(maxsize=None)
def _node(script):
    result = subprocess.run(["node", script], cwd=ROOT, capture_output=True, text=True, timeout=120)
    return result.returncode, result.stdout, result.stderr


def _harness():
    if not shutil.which("node") or not (ROOT / "ui-react/node_modules/sucrase").is_dir():
        pytest.skip("Node/sucrase indisponível")
    code, stdout, stderr = _node("tests/js/pipeline_index_harness.cjs")
    assert code == 0, stderr
    return json.loads(stdout.strip().splitlines()[-1])


def _read(path):
    return (ROOT / path).read_text(encoding="utf-8")


def test_harness_contract_catalog_cohort_and_creation():
    assert _harness() == {"contrato": "ok", "lista": "ok", "coorte": "ok", "criacao": "ok"}


def test_endpoint_is_in_the_guarded_group_and_allows_summary_without_stages():
    src = _read("backend-dotnet/Orquestra.Api/DraftEndpoints.cs")
    group = src.index('var group = app.MapGroup("/workspace")')
    endpoint = src.index('group.MapGet("/pipeline-index"')
    assert group < endpoint, "o filtro do grupo (flag, sessão, tela_pipelines) vale para o índice"
    allowance = re.search(r"var pipelineContext = (.+?);", src).group(1)
    assert 'StartsWithSegments("/workspace/pipeline-index")' in allowance and 'context.Request.Method == "GET"' in allowance
    body = src[endpoint:src.index("group.Map", endpoint + 1)]
    # Validação antes do banco; o resumo (com editor de posse válida e filtro editing) não depende de tela_jobs.
    assert "index.ReadAsync(PipelineIndexRules.Parse(search, project, domain, state, limit, offset), ct)" in body
    assert "tela_jobs" not in body and "Permissions" not in body and "EditorUser = null" not in body
    # O índice não amplia rascunho/definição: as demais rotas GET continuam exigindo tela_jobs.
    assert 'if (!pipelineContext && !actor.Permissions.Contains("tela_jobs"))' in src
    assert "/workspace/drafts" not in allowance
    assert "builder.Services.AddScoped<IPipelineIndex, SqlPipelineIndex>();" in _read("backend-dotnet/Orquestra.Api/Program.cs")


def test_index_sql_unions_by_column_collation_one_row_and_never_returns_definition():
    src = _read("backend-dotnet/Orquestra.Infrastructure/Drafts/SqlPipelineIndex.cs")
    assert "Serializable" not in src and "SET TRANSACTION ISOLATION LEVEL READ COMMITTED" in src
    # Nomes: cadastro legado UNION rascunhos ativos (lidos pelo índice filtrado, estado='ativo'), na collation real da coluna.
    assert re.search(r"SELECT pipeline_name FROM dbo\.etl_pipeline\s+UNION\s+SELECT pipeline_name FROM @rascunho", src)
    assert "INSERT @ativo(draft_id) SELECT x.draft_id FROM dbo.etl_workspace_rascunho x WHERE x.estado='ativo';" in src
    assert "pipeline_name NVARCHAR(200) COLLATE {names} NOT NULL" in src and src.count("NVARCHAR(4000) COLLATE {json} NULL") == 3
    assert "(SELECT collation_name FROM sys.columns WHERE object_id=OBJECT_ID('dbo.etl_workspace_rascunho','U') AND name='pipeline_name')" in src
    assert "(SELECT collation_name FROM sys.columns WHERE object_id=OBJECT_ID('dbo.etl_workspace_rascunho','U') AND name='definition_json')" in src
    assert "(SELECT collation_name FROM sys.columns WHERE object_id=OBJECT_ID('dbo.etl_workspace_pipeline','U') AND name='pipeline_name')" in src
    assert "pipeline_name NVARCHAR(200) COLLATE {managedNames} NOT NULL PRIMARY KEY" in src
    applies = re.findall(r"OUTER APPLY \((SELECT\s+\S+)", src)
    assert len(applies) == 5 and set(applies) == {"SELECT TOP(1)"}, applies
    # Nenhuma igualdade de nome em memória (collation é do SQL).
    assert not re.search(r"GroupBy|Distinct\(|ToLower|ToUpper|StringComparer", src)
    # Posse: só válida, calculada no servidor, igual para todo leitor autorizado.
    assert "WHERE x.expires_at>SYSUTCDATETIME();" in src and "FROM @posse x WHERE x.draft_id=r.draft_id AND x.expires_at>@corte) l" in src and "@stages" not in src and "stages" not in src
    final = re.search(r"SELECT COUNT\(\*\) OVER\(\) AS total,(.+?)\n\s*FROM @resumo r \{holder\}", src).group(1)
    assert "definition" not in final and "layout" not in src and "fence" not in src and "holder_session_hash" not in src
    # Ordem decidida na origem, pela collation das colunas (com desempate binário), e só aplicada na página.
    assert "SELECT ROW_NUMBER() OVER(ORDER BY COALESCE(r.display_name,r.pipeline_name),r.pipeline_name,r.pipeline_name COLLATE Latin1_General_BIN2)," in src
    assert "ORDER BY r.ordem OFFSET @offset ROWS FETCH NEXT @limit ROWS ONLY;" in src
    assert "LikePattern" in src and "@pattern IS NULL OR r.pipeline_name LIKE @pattern OR r.display_name LIKE @pattern" in src
    # Projeção em reconciliação não é publicação (mesma regra do pipeline-context).
    assert "COALESCE(m.version_id,m.base_version_id)" in src
    assert "COALESCE(p.version_id,d.base_version_id)" in _read("backend-dotnet/Orquestra.Infrastructure/Drafts/SqlDraftRepository.cs")


def test_dotnet_tests_cover_rbac_validation_cancellation_and_live_sql():
    endpoint = _read("backend-dotnet/Orquestra.Tests/PipelineIndexTests.cs")
    for name in ["SessionPermissionAndFlagAreCheckedBeforeTheIndex", "EveryAuthorizedReaderSeesTheValidEditorAndFiltersEditingButNeverProtectedData",
                 "ReaderWithoutStagesStillCannotReadTheDraftDefinitionOrLease", "RepositoryHasNoPermissionGateAndFailsHonestlyWithoutDatabase",
                 "InvalidInputIsRejectedInPortugueseBeforeTheDatabase", "ClientCancellationReachesTheIndexQuery", "MissingSchemaIsAnHonest503NamingTheMigration"]:
        assert f"public async Task {name}(" in endpoint, name
    live = _read("backend-dotnet/Orquestra.Tests/PipelineIndexSqlTests.cs")
    assert "[SqlFact]" in live and "COLLATE SQL_Latin1_General_CP1_CI_AS" in live and "PublishAsync" in live
    # Posse expirada some do filtro e do total; posse no rascunho de grafia divergente conta uma vez.
    assert "SET expires_at=DATEADD(second,-1,SYSUTCDATETIME())" in live and 'Query(state: "editing", search: "ÁRVORE")' in live
    # Revisão EOC-F2: posse que expira com a leitura presa em qualquer estágio (rascunho, resumo, posse) não é edição.
    expiry = _body(live, "public async Task IndexDropsLeaseThatExpiresWhileAnyStageWaitsUsingOneFinalCutoff(", "\n    }\n")
    for marker in ['"INSERT @ativo(", "INSERT @rascunho("', '"WITH names AS ("', '"INSERT @posse(", "UPDATE p SET p.holder_name="', "BlockedStatements(c, writerSession, 2, stage)",
                   "expires_at>SYSUTCDATETIME()\") > 0; tick++)", 'Assert.False(editing.IsCompleted, stage)', 'await Execute(writer, "COMMIT");',
                   "Assert.Empty(editingPage.Items); Assert.Equal(0, editingPage.Total);", "Assert.Null(row.EditorUser); Assert.Null(row.EditorName); Assert.Null(row.LeaseExpiresAt);",
                   'Query(state: "editing", offset: 50)']:
        assert marker in expiry, marker
    # Base publicada da operação pendente preservada com o rascunho dela fora dos ativos.
    assert "SET estado='publicado' WHERE draft_id='{target.DraftId}'" in live and 'Assert.False(closed.HasDraft); Assert.Null(closed.PublishedVersionNumber); Assert.Equal("Proj", closed.Project);' in live


def _body(src, start, end):
    return src[src.index(start):src.index(end, src.index(start) + 1)]


def test_index_yields_deadlocks_to_writers_and_retries_only_the_victim():
    # Correção EOC-F2 (deadlock real no SQL do root): o índice é a vítima preferencial, num pool próprio, e só a
    # vítima 1205 refaz a leitura inteira sob um prazo único. Escritas, isolamento e o banco não mudam.
    src = _read("backend-dotnet/Orquestra.Infrastructure/Drafts/SqlPipelineIndex.cs")
    assert 'internal const string ApplicationName = "Orquestra.Workspace.Index";' in src
    assert "new SqlConnectionStringBuilder(options.ConnectionString()) { ApplicationName = ApplicationName }.ConnectionString;" in src
    assert 'SessionSettings = "SET NOCOUNT ON; SET DEADLOCK_PRIORITY LOW; SET TRANSACTION ISOLATION LEVEL READ COMMITTED;' in src
    assert "new(SessionSettings + sql, c)" in src and "new SqlCommand(" not in src
    read = _body(src, "public async Task<PipelineIndexPage> ReadAsync(", "private async Task<PipelineIndexPage> ReadOnceAsync(")
    once = _body(src, "private async Task<PipelineIndexPage> ReadOnceAsync(", "private static PipelineIndexItem Item(")
    # Conexão e acumuladores nascem em cada tentativa; a repetição não carrega nada da vítima.
    assert "new SqlConnection(ConnectionString(options))" in once and "var items = new List<PipelineIndexItem>(); var total = 0;" in once
    assert "new SqlConnection" not in read and "new List" not in read and "items" not in read
    assert "private const int DeadlockVictim = 1205;" in src
    assert "catch (SqlException e) when (e.Number == DeadlockVictim && n < retry.Attempts && !deadline.IsCancellationRequested) { }" in read
    assert "deadline.CancelAfter(retry.Budget);" in read and "var delay = retry.Backoff(n);" in read and "await wait(delay, deadline.Token);" in read
    cancelled = "catch (Exception e) when (ct.IsCancellationRequested && e is OperationCanceledException or SqlException or InvalidOperationException) { throw new OperationCanceledException(ct); }"
    expired = "catch (Exception e) when (deadline.IsCancellationRequested && e is OperationCanceledException or SqlException or InvalidOperationException) { Interlocked.Increment(ref expired); throw new DependencyUnavailableException(); }"
    exhausted = "catch (SqlException e) when (e.Number == DeadlockVictim) { Interlocked.Increment(ref exhausted); throw new DependencyUnavailableException(); }"
    assert read.index(cancelled) < read.index(expired) < read.index(exhausted) < read.index("catch (SqlException) { throw new DependencyUnavailableException(); }")
    assert "new(5, TimeSpan.FromSeconds(10), TimeSpan.FromMilliseconds(50))" in src
    # Sem leitura suja, pulo de linha travada, snapshot ou opção global de banco.
    dotnet = sorted((ROOT / "backend-dotnet").rglob("*.cs"))
    production = [p for p in dotnet if "Orquestra.Tests" not in p.parts and "bin" not in p.parts and "obj" not in p.parts]
    hints = re.compile(r"WITH\s*\(\s*(NOLOCK|READPAST|READUNCOMMITTED)|ISOLATION LEVEL (READ UNCOMMITTED|SNAPSHOT)|IsolationLevel\.(ReadUncommitted|Snapshot)|READ_COMMITTED_SNAPSHOT|ALLOW_SNAPSHOT_ISOLATION", re.I)
    for path in production + [ROOT / "sql/migrations/170_versao_pipeline_descoberta.sql"]:
        assert not hints.search(path.read_text(encoding="utf-8")), path
    # Prioridade só no índice; escritas seguem NORMAL no pool de sempre, serializáveis, com 1205 → 409 e sem repetição geral.
    assert [p.name for p in production if "DEADLOCK_PRIORITY" in p.read_text(encoding="utf-8")] == ["SqlPipelineIndex.cs"]
    assert 'ApplicationName = "Orquestra.Workspace", PersistSecurityInfo = false' in _read("backend-dotnet/Orquestra.Infrastructure/Security/SqlSessionRepository.cs")
    drafts = _read("backend-dotnet/Orquestra.Infrastructure/Drafts/SqlDraftRepository.cs")
    run = _body(drafts, "private async Task<T> Run<T>(", "\n    }\n")
    assert "IsolationLevel.Serializable" in run and "for (" not in run and "while (" not in run and "Delay" not in run
    assert 'catch (SqlException e) when (e.Number is 2601 or 2627 or 1205) { throw Conflict("draft_conflict"' in run
    assert '<InternalsVisibleTo Include="Orquestra.Tests" />' in _read("backend-dotnet/Orquestra.Infrastructure/Orquestra.Infrastructure.csproj")
    # Testes: política offline completa, prova SQL determinística e o cenário concorrente real mantido.
    retry = _read("backend-dotnet/Orquestra.Tests/PipelineIndexRetryTests.cs")
    for name in ["IndexHasItsOwnPoolAndLowPriorityWhileWritersKeepTheirs", "DeadlockVictimRepeatsTheWholeAttemptAndReturnsOnlyTheLastResult",
                 "OnlyTheDeadlockVictimIsRetried", "FailuresOutsideSqlAreNotRetried", "ExhaustedDeadlockRetriesAreAnHonest503WithoutSqlText",
                 "OneBudgetCoversEveryAttemptAndWaitAndEndsIn503", "ClientCancellationWinsInTheAttemptInTheWaitAndAfterAVictim"]:
        assert f" {name}(" in retry, name
    live = _read("backend-dotnet/Orquestra.Tests/PipelineIndexSqlTests.cs")
    assert "public async Task IndexRunsAtLowPriorityInItsOwnPoolWaitsForCommittedDataAndLosesTheDeadlockToWriters(" in live
    assert "Assert.Equal(-5, reading.Priority)" in live and "Assert.Equal(1205, (await Assert.ThrowsAsync<SqlException>(() => lowRead)).Number)" in live
    assert "Enumerable.Range(0, 4)" in live and "for (var i = 0; i < 10; i++)" in live
    # Limpeza: nenhum pedido do teste segue rodando no DROP; prazo local finito, sem corrida contra um relógio.
    assert "WhenAny" not in live and "Task.Delay(TimeSpan.FromMinutes" not in live
    assert live.count("finally { await Drop(running, failure, master, created ? database : null); }") == 3
    assert live.count("catch (Exception e) { failure = e; throw; }") == 3
    assert "running.Restart(TimeSpan.FromMinutes(3));" in live and live.count("index.ReadAsync(Query(search: \"pubc\"), running.Token)") == 1
    for started in ["var read = running.Track(index.ReadAsync(", "var create = running.Track(new SqlDraftRepository(options).CreateAsync(",
                    "var lowRead = running.Track(Execute(low,", "var normalWrite = running.Track(Execute(normal,"]:
        assert started in live and "running.Token)" in live.split(started, 1)[1].split("\n", 1)[0], started
    for held in ["writer", "blocker", "low", "normal"]:
        assert f"var {held} = await running.Open(" in live, held
    stop = _body(live, "public async Task<List<Exception>> StopAsync()", "public void Dispose()")
    assert stop.index("abort.Cancel();") < stop.index("await Task.WhenAll(tasks)") < stop.index("IF @@TRANCOUNT > 0 ROLLBACK") < stop.index("DisposeAsync")
    drop = _body(live, "private static async Task Drop(", "\n    }\n")
    assert drop.index("await running.StopAsync()") < drop.index("DROP DATABASE") and "failure is null ? errors : [failure, .. errors]" in drop
    assert "Assert.Null(row.PublishedVersionNumber)" in live and "WHERE draft_id='{target.DraftId}'\"))" in live


def test_index_batch_never_holds_draft_or_lease_locks_while_waiting():
    # Correção EOC-F2 (contenção no SQL nativo): na instrução única, o LOB do rascunho (S até o fim da instrução) e o
    # lookup do índice filtrado (S na chave) ficavam presos enquanto a leitura esperava a posse/linha da escrita: ciclo a
    # cada descarte, pago com o intervalo do monitor de deadlock. O lote separa as leituras em instruções curtas.
    # Revisão da materialização: a página ainda lia o rascunho real pela operação pendente (S de versão/pipeline gerido
    # presos esperando o rascunho) e a posse era capturada antes do estágio de rascunho, sem corte final.
    src = _read("backend-dotnet/Orquestra.Infrastructure/Drafts/SqlPipelineIndex.cs")
    sql = _body(src, "private static string Sql(bool managed, string names, string json, string managedNames, string holders)", "\n    }\n")
    batch = sql[sql.index('return $"""'):]
    # 1) ids ativos; 2) resumo dos ativos pela chave; 3) gerido; 4) resumo filtrado; 5) posse; 6) corte; 7) página; contagem além do fim.
    order = ["DECLARE @ativo TABLE(", "DECLARE @rascunho TABLE(", "DECLARE @resumo TABLE(", "DECLARE @posse TABLE(", "DECLARE @corte DATETIME2;",
             "INSERT @ativo(", "INSERT @rascunho(", "{managedReads}", "WITH names AS (", "INSERT @resumo(", "INSERT @posse(", "UPDATE p SET p.holder_name=", "SET @corte=SYSUTCDATETIME();",
             "SELECT COUNT(*) OVER() AS total,", "IF @@ROWCOUNT=0 AND @offset>0", "SELECT COUNT(*) FROM @resumo r {holder}"]
    positions = [batch.index(step) for step in order]
    assert positions == sorted(positions), order
    ativo = _body(batch, "INSERT @ativo(", "INSERT @rascunho(")
    rascunho = _body(batch, "INSERT @rascunho(", "{managedReads}")
    resumo = _body(batch, "WITH names AS (", "INSERT @posse(")
    posse = _body(batch, "INSERT @posse(", "SET @corte=SYSUTCDATETIME();")
    page = batch[batch.index("SET @corte=SYSUTCDATETIME();"):]
    managed_apply = _body(sql, "var managedApply = managed", ': "";')
    managed_reads = _body(sql, "var managedReads = managed", ': "";')
    tables = lambda text: set(re.findall(r"dbo\.(\w+)", text))  # noqa: E731
    # Ids pelo índice filtrado (draft_id é a chave do índice): nenhuma coluna fora dele, logo nenhum lookup.
    assert tables(ativo) == {"etl_workspace_rascunho"} and "SELECT x.draft_id FROM dbo.etl_workspace_rascunho x WHERE x.estado='ativo';" in ativo
    # Único LOB do rascunho: só aqui, pela chave primária, sem outra tabela na mesma instrução.
    assert tables(rascunho) == {"etl_workspace_rascunho"} and "FROM @ativo a JOIN dbo.etl_workspace_rascunho x WITH(FORCESEEK) ON x.draft_id=a.draft_id WHERE x.estado='ativo';" in rascunho
    assert src.count("JSON_VALUE(x.definition_json,") == 3 and rascunho.count("JSON_VALUE(x.definition_json,") == 3
    # Gerido: uma tabela real por instrução, chave primária, sem LOB; a base pendente vem do rascunho da operação
    # pela chave, sem filtro de estado (ativo ou não), e só para pipeline sem versão confirmada.
    statements = [x.strip() for x in managed_reads.split(";") if "dbo." in x]
    assert [tables(x) for x in statements] == [{"etl_workspace_pipeline"}, {"etl_workspace_publicacao"}, {"etl_workspace_rascunho"}], statements
    assert "JOIN dbo.etl_workspace_publicacao o WITH(FORCESEEK) ON o.operation_id=g.pending_operation_id WHERE g.version_id IS NULL" in managed_reads
    assert "UPDATE g SET g.base_version_id=x.base_version_id FROM @gerido g JOIN dbo.etl_workspace_rascunho x WITH(FORCESEEK) ON x.draft_id=g.pending_draft_id;" in managed_reads
    assert "definition_json" not in managed_reads and "estado" not in managed_reads
    # Resumo: só cadastro legado e versão (somente inserida pelo código); nunca rascunho, posse, pipeline gerido ou publicação.
    assert tables(resumo) == {"etl_pipeline"} and tables(managed_apply) == {"etl_workspace_versao"}
    assert "FROM @gerido x WHERE x.pipeline_name=n.pipeline_name) m" in managed_apply and "pend" not in managed_apply
    assert "FROM @rascunho x WHERE x.pipeline_name=n.pipeline_name ORDER BY x.atualizado_em DESC,x.draft_id) d" in resumo
    assert "holder" not in resumo and "@posse" not in resumo and "(@state='editing' AND r.draft_id IS NOT NULL)" in resumo
    # Posse por último, perto da página; filtro preliminar no início da instrução e corte único depois de todas as leituras.
    assert tables(posse) == {"etl_workspace_lease", "etl_usuario"} and "WHERE x.expires_at>SYSUTCDATETIME();" in posse and "definition_json" not in posse
    # Posse e nome do titular em instruções separadas (no APPLY, S na posse ficava preso esperando o usuário).
    assert [tables(x) for x in posse.split(";") if "dbo." in x] == [{"etl_workspace_lease"}, {"etl_usuario"}] and "APPLY" not in posse
    assert "holder_user NVARCHAR(100) COLLATE {holders} NOT NULL" in batch
    # @corte: declarado, definido uma vez e usado só no holder (interpolado na página e na contagem).
    assert sql.count("SYSUTCDATETIME()") == 2 and sql.count("@corte") == 3 and sql.count("SET @corte=") == 1
    # Página e contagem: só variáveis de tabela, o mesmo resumo, a mesma posse e o mesmo corte.
    assert not tables(page) and page.count("{holder}") == 2 and page.count("WHERE @state<>'editing' OR l.holder_user IS NOT NULL") == 2
    holder = re.search(r'var holder = "(.+?)";', sql).group(1)
    assert holder == "OUTER APPLY (SELECT TOP(1) x.holder_user,x.expires_at,x.holder_name FROM @posse x WHERE x.draft_id=r.draft_id AND x.expires_at>@corte) l"
    # Collation real do catálogo, validada como nome antes de entrar no SQL; nada da requisição vira texto SQL.
    once = _body(src, "private async Task<PipelineIndexPage> ReadOnceAsync(", "private static PipelineIndexItem Item(")
    assert "names = Collation(r.GetString(2)); json = Collation(r.GetString(3)); managedNames = managed ? Collation(r.GetString(4)) : \"\";" in once
    assert "if (managed && r.IsDBNull(4)) throw Missing();" in once and "holders = Collation(r.GetString(5));" in once and "r.IsDBNull(5)) throw Missing();" in once
    assert "(SELECT collation_name FROM sys.columns WHERE object_id=OBJECT_ID('dbo.etl_workspace_lease','U') AND name='holder_user')" in once
    assert "name.All(ch => char.IsAsciiLetterOrDigit(ch) || ch == '_') ? name : throw new DependencyUnavailableException();" in once
    assert not re.search(r"\{(query|search|pattern|project|domain|state)", batch, re.I)
    # Contagem além do fim no mesmo lote (mesmas leituras), sem segundo comando.
    assert once.count("Command(c,") == 2 and "await r.NextResultAsync(ct)" in once
    # Diagnóstico interno de parada (sem DTO): 1205 esgotada × prazo, maior nº de tentativas, espera cumprida.
    assert "internal readonly record struct PipelineIndexStops(int Exhausted, int Expired, int LongestSuccess, TimeSpan Backoff);" in src
    assert "PipelineIndexStops" not in _read("backend-dotnet/Orquestra.Application/Drafts/PipelineIndexContracts.cs")
    retry = _read("backend-dotnet/Orquestra.Tests/PipelineIndexRetryTests.cs")
    assert "Assert.Equal(new PipelineIndexStops(0, 0, 3, waits[0] + waits[1]), index.Stops);" in retry and "Assert.Equal(new PipelineIndexStops(0, 1, 0, TimeSpan.Zero), waiting.Stops);" in retry
    assert "Assert.Equal(1, index.Stops.Exhausted); Assert.Equal(0, index.Stops.Expired);" in retry and retry.count("Assert.Equal(default, index.Stops);") == 2
    # Bancada: busca e lista completa medidas à parte, escritas cronometradas, paradas e vítimas informadas.
    live = _read("backend-dotnet/Orquestra.Tests/PipelineIndexSqlTests.cs")
    assert "busca {Percentiles(samples.SelectMany(s => s.Search))}; lista completa {Percentiles(samples.SelectMany(s => s.Full))}; escritas {Percentiles(writes)}" in live
    assert "var operation = await Write(() => drafts.PublishAsync(" in live and "await Write(() => drafts.CreateAsync(" in live and "await Write(() => drafts.LeaseAsync(" in live and "await drafts.DiscardAsync(" in live


def test_version_migration_is_the_next_sequential_minor():
    numbers = sorted(int(p.name[:3]) for p in (ROOT / "sql/migrations").glob("[0-9][0-9][0-9]_*.sql"))
    assert numbers[numbers.index(170) - 2:numbers.index(170) + 1] == [168, 169, 170]
    sql = _read("sql/migrations/170_versao_pipeline_descoberta.sql")
    assert "SET @nova = CONCAT(@maior, '.', @menor + 1, '.0');" in sql
    assert sql.count("N'Lista única de pipelines e criação essencial'") == 1 and sql.rstrip().endswith("GO")


def test_legacy_list_is_kept_outside_the_cohort():
    src = _read("ui-react/src/pages/Pipelines.tsx")
    gate, legacy = src.split("function LegacyPipelines(", 1)
    assert "contextualNavigation" in gate and "search.get('legado') !== '1'" in gate and "<PipelineCatalog" in gate
    # O corpo anterior continua inteiro na lista clássica (ações e modais legados).
    for marker in ["<PipelineRow", "<PipelineFormModal", "<GenDagModal", "<ExecModal", "exportModeloCsv", "<InactivateModal"]:
        assert marker in legacy, marker
