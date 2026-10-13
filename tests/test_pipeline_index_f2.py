"""UX profissional do Pipeline — F2 (descoberta e entrada única).

Camadas:
- bancada (tests/js/pipeline_index_harness.cjs): lib/pipelineIndex pura e as telas
  reais PipelineCatalog, Pipelines (portão da coorte) e PipelineCreate;
- contrato estrutural do índice .NET/SQL (endpoint, RBAC sem tela_jobs, SQL com
  igualdade pela collation, uma linha por pipeline, posse só válida e resumo de
  todo leitor autorizado, leitura sem transação serializável) — os testes executáveis ficam em
  backend-dotnet/Orquestra.Tests/PipelineIndexTests.cs (endpoint, offline) e
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
