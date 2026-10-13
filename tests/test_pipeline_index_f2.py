"""UX profissional do Pipeline — F2 (descoberta e entrada única).

Camadas:
- bancada (tests/js/pipeline_index_harness.cjs): lib/pipelineIndex pura e as telas
  reais PipelineCatalog, Pipelines (portão da coorte) e PipelineCreate;
- contrato estrutural do índice .NET/SQL (endpoint, RBAC sem tela_jobs, SQL com
  igualdade pela collation, uma linha por pipeline, posse só válida e resumo de
  todo leitor autorizado, leitura sem transação serializável, vítima de deadlock em LOW num pool
  próprio com repetição só da 1205) — os testes executáveis ficam em
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
    assert re.search(r"SELECT pipeline_name FROM dbo\.etl_pipeline\s+UNION\s+SELECT pipeline_name FROM dbo\.etl_workspace_rascunho WHERE estado='ativo'", src)
    applies = re.findall(r"OUTER APPLY \((SELECT\s+\S+)", src)
    assert len(applies) == 7 and set(applies) == {"SELECT TOP(1)"}, applies
    # Nenhuma igualdade de nome em memória (collation é do SQL).
    assert not re.search(r"GroupBy|Distinct\(|ToLower|ToUpper|StringComparer", src)
    # Posse: só válida, calculada no servidor, igual para todo leitor autorizado.
    assert "WHERE x.draft_id=d.draft_id AND x.expires_at>SYSUTCDATETIME()" in src and "@stages" not in src and "stages" not in src
    final = re.search(r'"SELECT COUNT\(\*\) OVER\(\) AS total,(.+?) FROM summary r"', src).group(1)
    assert "definition" not in final and "layout" not in src and "fence" not in src and "holder_session_hash" not in src
    assert "COLLATE Latin1_General_BIN2 OFFSET @offset ROWS FETCH NEXT @limit ROWS ONLY" in src
    assert "LikePattern" in src and "@pattern IS NULL OR r.pipeline_name LIKE @pattern OR r.display_name LIKE @pattern" in src
    # Projeção em reconciliação não é publicação (mesma regra do pipeline-context).
    assert "COALESCE(m.version_id,pend.base_version_id)" in src
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
    assert "deadline.CancelAfter(retry.Budget);" in read and "await wait(retry.Backoff(n), deadline.Token);" in read
    cancelled = "catch (Exception e) when (ct.IsCancellationRequested && e is OperationCanceledException or SqlException or InvalidOperationException) { throw new OperationCanceledException(ct); }"
    expired = "catch (Exception e) when (deadline.IsCancellationRequested && e is OperationCanceledException or SqlException or InvalidOperationException) { throw new DependencyUnavailableException(); }"
    assert read.index(cancelled) < read.index(expired) < read.index("catch (SqlException) { throw new DependencyUnavailableException(); }")
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
    assert live.count("finally { await Drop(running, failure, master, created ? database : null); }") == 2
    assert live.count("catch (Exception e) { failure = e; throw; }") == 2
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


def test_version_migration_is_the_next_sequential_minor():
    numbers = sorted(int(p.name[:3]) for p in (ROOT / "sql/migrations").glob("[0-9][0-9][0-9]_*.sql"))
    assert numbers[-3:] == [168, 169, 170]
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
