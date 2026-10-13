"""UX profissional do Pipeline — F5 (execução e investigação).

Três camadas:
- bancada pura (tests/js/workspace_execution_harness.cjs): estados de etapa,
  ligação e corrida, orçamento de consulta, frescor, anúncio, solicitação guiada
  e filtros do histórico, executando lib/workspaceExecution.ts como está;
- bancada da tela (tests/js/workspace_ux_contexto_harness.cjs, seções 7 e 13):
  WorkspaceOperations real com um único gráfico, inspector operacional,
  solicitação e histórico;
- adaptador FastAPI GET /pipeline-run-history: permissões, validação antes do
  banco, consulta exata e paginada, degradação por migration e erro sanitizado.
Navegador real, SQL/Airflow reais e carga concorrente ficam para o QA/DEV.
"""
import json
import re
import shutil
import subprocess
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path

import pytest
from fastapi import HTTPException

from routers import execucoes

ROOT = Path(__file__).resolve().parents[1]
PERMS = {"permissoes": ["tela_pipelines", "tela_jobs", "tela_logs"]}


@lru_cache(maxsize=None)
def _node(script):
    result = subprocess.run(["node", script], cwd=ROOT, capture_output=True, text=True, timeout=90)
    return result.returncode, result.stdout, result.stderr


def _harness(script):
    if not shutil.which("node") or not (ROOT / "ui-react/node_modules/sucrase").is_dir():
        pytest.skip("Node/sucrase indisponível")
    code, stdout, stderr = _node(script)
    assert code == 0, stderr
    return json.loads(stdout.strip().splitlines()[-1])


def test_pure_execution_contract():
    out = _harness("tests/js/workspace_execution_harness.cjs")
    assert out["passed"] is True
    assert out["corrida"] == ["Solicitado", "Em fila", "Executando"]
    assert out["ligacoes"] == ["observed", "skipped", "unknown"]
    assert out["consulta"] == {"semMedicao": 30000, "comMedicaoAtiva": 5000, "oculta": False}
    assert out["canvasA11y"] == {"enter": True, "reduzido": 0}
    # Correção 2.21.2: tentativas do motor (fixture retries=1 falhou duas vezes).
    assert out["motor"] == {"fixture": [2, 1], "padrao": 2, "fora": "recusada", "fila": "sem log", "lacuna": "dita", "utc": True}


def test_shared_canvas_enter_selects_through_parent_and_fit_view_respects_reduced_motion():
    # Montagem e Execução usam o mesmo canvas: Enter na etapa focada segue o caminho
    # do clique (onSelect → inspector/URL), e nenhum reenquadramento anima com
    # prefers-reduced-motion (CSS animation:none não alcança o fitView do JS).
    src = (ROOT / "ui-react/src/components/workspace/WorkspaceCanvas.tsx").read_text(encoding="utf-8")
    fits = re.findall(r"fitView\(\{.*?\}\)", src)
    assert len(fits) == 2 and all("duration:motion()" in call for call in fits), fits
    assert "query=>window.matchMedia(query)" in src, "matchMedia sem o window lança e cairia nos 200 ms"
    capture = src.split("onKeyDownCapture={event=>{", 1)[1].split("}}", 1)[0]
    assert "nodeForEnter(event.nativeEvent" in capture and "event.stopPropagation()" in capture and "onSelect(id)" in capture
    assert "focus(" not in capture, "o foco continua na etapa"


def test_operations_screen_single_viewer_inspector_and_states():
    out = _harness("tests/js/workspace_ux_contexto_harness.cjs")
    assert out["execucao"] == {"graficos": 1, "estados": 6, "anuncioSelecionada": True, "logTexto": True, "outraCorrida": False, "ocultaSemPolling": True, "indisponivelSemAnimacao": True}
    assert out["fonteExecucao"] is True



def test_engine_attempts_govern_logs_and_sql_attempt_stays_operational():
    # O log abre pelo try_number do MOTOR (padrão: o mais recente iniciado); a
    # tentativa SQL continua visível como operacional e não abre log. Resposta
    # antiga, lacuna, fila sem início e motor fora do ar são ditos; a consulta
    # é sob demanda (Tentativas/Logs, aba exibida e navegador visível).
    out = _harness("tests/js/workspace_ux_contexto_harness.cjs")
    assert out["motor"] == {"padrao": 2, "alcancavel": 1, "operacionalSemLog": True, "filaSemLog": True, "respostaAntiga": "descartada", "lacuna": "dita", "indisponivel": "erro honesto", "sobDemanda": True}
    inspector = (ROOT / "ui-react/src/components/workspace/WorkspaceRunInspector.tsx").read_text(encoding="utf-8")
    assert "engineAttemptsPath(p.name, p.runId!, engineTask!), { signal }" in inspector, "pedido cancelável pela chave"
    assert "stageAttempts" not in inspector, "o número SQL não decide mais o log"


def test_identity_fence_frozen_intents_and_hidden_reads():
    # Resposta de outro pipeline (mesmo run_id), outra corrida ou outra data não
    # define desenho, versão nem estados; reprocessar mira o task_id real; a
    # confirmação congelada some ao mudar etapa/corrida/sessão e o envio com a
    # sessão trocada não posta; leituras param com a aba oculta.
    out = _harness("tests/js/workspace_ux_contexto_harness.cjs")
    assert out["cerca"] == {"outroPipelineMesmoRun": "sem desenho/versão/estados", "outraCorrida": "sem desenho/versão/estados", "outraData": "sem desenho/versão/estados", "reprocessoTaskId": "grupo.n4", "intencaoDescartada": ["etapa", "corrida", "sessão"], "envioComSessaoTrocada": 0, "leiturasOcultas": False}
    assert out["cercaSolicitacao"] == {"descartada": ["corrida exibida", "sessão"], "envioComSessaoTrocada": 0}


def test_guided_run_request_and_history_on_demand():
    out = _harness("tests/js/workspace_ux_contexto_harness.cjs")
    assert out["solicitacao"] == {"semJson": True, "invalidaNaoDispara": True, "mesmoIdentificador": True, "estados": ["Solicitado", "Em fila", "Executando"]}
    assert out["historico"] == {"sobDemanda": True, "paginas": 3, "filtros": ["data", "situação", "versão"], "abre": "mesmo visualizador"}


def test_execution_tab_no_longer_mounts_the_legacy_graph():
    # Um renderer: o canvas da Montagem. O FluxoEditor continua só nas telas legadas.
    for source in (ROOT / "ui-react/src/components/workspace").glob("*.tsx"):
        assert "etapas/FluxoEditor" not in source.read_text(encoding="utf-8"), source.name
    assert "workspace?:" not in (ROOT / "ui-react/src/components/etapas/FluxoEditor.tsx").read_text(encoding="utf-8")


def test_execution_entry_loads_history_request_and_confirmations_on_demand():
    # Orçamento da entrada (<300 KiB gzip): histórico, pedido de execução e as
    # confirmações de reprocesso/pausa só carregam quando abertos.
    workspace = ROOT / "ui-react/src/components/workspace"
    operations = (workspace / "WorkspaceOperations.tsx").read_text(encoding="utf-8")
    inspector = (workspace / "WorkspaceRunInspector.tsx").read_text(encoding="utf-8")
    for name in ("WorkspaceRunHistory", "WorkspaceRunRequest"):
        assert f"import {{ {name} }}" not in operations and f"import('./{name}')" in operations, name
    for name in ("ModalRerunEtapa", "ModalPausaEtapa"):
        assert f"import {{ {name} }}" not in inspector and f"import('../etapas/{name}')" in inspector, name


class Cursor:
    def __init__(self, *, has_067=True, versions=True, replaced=True, total=2, rows=None, fail=False):
        self.has_067, self.versions, self.replaced, self.total, self.fail = has_067, versions, replaced, total, fail
        self.rows = rows if rows is not None else [
            ("manual__r1", date(2026, 10, 10), "EXECUTANDO", datetime(2026, 10, 10, 10, 0, 0), None, "manual", None, 4),
            ("scheduled__a", date(2026, 10, 9), "SUCESSO", datetime(2026, 10, 9, 6, 0), datetime(2026, 10, 9, 6, 10), "agenda", datetime(2026, 10, 9, 7, 0), None),
        ]
        self.calls = []; self.closed = False; self._next = None

    def execute(self, sql, params=()):
        self.calls.append((sql, list(params)))
        if self.fail:
            raise RuntimeError("synthetic-private-db-detail")
        if "OBJECT_ID('dbo.etl_pipeline_execucao'" in sql:
            self._next = (1 if self.has_067 else None,)
        elif "etl_workspace_execucao','U') IS NOT NULL" in sql:
            self._next = (1 if self.versions else 0,)
        elif "COL_LENGTH" in sql:
            self._next = (1 if self.replaced else 0,)
        elif sql.startswith("SELECT COUNT(*)"):
            self._next = (self.total,)
        return self

    def fetchone(self):
        return self._next

    def fetchall(self):
        return self.rows

    def close(self):
        self.closed = True


class Connection:
    def __init__(self, cursor):
        self.c = cursor; self.closed = False

    def cursor(self):
        return self.c

    def close(self):
        self.closed = True


def _history(monkeypatch, cursor=None, **kwargs):
    cursor = cursor or Cursor()
    connection = Connection(cursor)
    monkeypatch.setattr(execucoes, "get_db_conn", lambda: connection)
    kwargs.setdefault("auth", PERMS)
    return execucoes.workspace_run_history(kwargs.pop("pipeline_name", "ação/A %25"), **kwargs), cursor, connection


@pytest.mark.parametrize("missing", ["tela_pipelines", "tela_jobs", "tela_logs"])
def test_history_denies_missing_permission_before_db(monkeypatch, missing):
    monkeypatch.setattr(execucoes, "get_db_conn", lambda: pytest.fail("sem permissão não consulta o banco"))
    with pytest.raises(HTTPException) as error:
        execucoes.workspace_run_history("p", auth={"permissoes": [p for p in PERMS["permissoes"] if p != missing]})
    assert error.value.status_code == 403


@pytest.mark.parametrize("kwargs", [
    {"pipeline_name": ""}, {"pipeline_name": "a\nb"}, {"pipeline_name": "x" * 201},
    {"date_from": "10/10/2026"}, {"date_to": "2026-02-30"}, {"date_from": "2026-10-11", "date_to": "2026-10-10"},
    {"status": "DROP"}, {"status": "SUCESSO' OR 1=1 --"}, {"version": 0}, {"version": 2_147_483_648},
    {"limit": 0}, {"limit": 101}, {"offset": -1}, {"offset": 1_000_001},
])
def test_history_rejects_invalid_input_before_db(monkeypatch, kwargs):
    monkeypatch.setattr(execucoes, "get_db_conn", lambda: pytest.fail("entrada inválida não consulta o banco"))
    with pytest.raises(HTTPException) as error:
        execucoes.workspace_run_history(kwargs.pop("pipeline_name", "p"), auth=PERMS, **kwargs)
    assert error.value.status_code == 422


def test_history_exact_name_filters_pagination_and_version(monkeypatch):
    out, cursor, connection = _history(monkeypatch, date_from="2026-10-01", date_to="2026-10-10", status="falha", version=4, limit=25, offset=50)
    count_sql, count_params = cursor.calls[3]
    select_sql, select_params = cursor.calls[4]
    assert "LIKE" not in count_sql + select_sql
    assert "e.pipeline_name = ?" in select_sql and "v.numero = ?" in select_sql and "e.status = ?" in select_sql
    assert count_params == ["ação/A %25", date(2026, 10, 1), date(2026, 10, 10), "FALHA", 4]
    assert select_params == count_params + [50, 25]
    assert "ORDER BY e.data_referencia DESC, e.inicio DESC, e.id DESC OFFSET ? ROWS FETCH NEXT ? ROWS ONLY" in select_sql
    assert out["total"] == 2 and out["limit"] == 25 and out["offset"] == 50 and out["versionsAvailable"] is True
    assert out["items"][0] == {"runId": "manual__r1", "date": "2026-10-10", "status": "EXECUTANDO", "startedAt": "2026-10-10 10:00:00", "finishedAt": None, "triggeredBy": "manual", "replacedAt": None, "versionNumber": 4, "snapshot": True}
    assert out["items"][1]["snapshot"] is False and out["items"][1]["replacedAt"] == "2026-10-09 07:00:00"
    assert out["source"] == "Registro operacional das corridas", "sem nome técnico de tabela"
    assert all(set(item) == {"runId", "date", "status", "startedAt", "finishedAt", "triggeredBy", "replacedAt", "versionNumber", "snapshot"} for item in out["items"])
    assert cursor.closed and connection.closed


def test_history_without_filters_sends_only_the_pipeline(monkeypatch):
    _, cursor, _ = _history(monkeypatch)
    assert cursor.calls[3][1] == ["ação/A %25"]
    assert cursor.calls[4][1] == ["ação/A %25", 0, 25]


def test_history_without_067_names_the_migration(monkeypatch):
    with pytest.raises(HTTPException) as error:
        _history(monkeypatch, Cursor(has_067=False))
    assert error.value.status_code == 503 and "067" in error.value.detail


def test_history_degrades_without_workspace_version_tables(monkeypatch):
    out, cursor, _ = _history(monkeypatch, Cursor(versions=False, replaced=False, rows=[("r", date(2026, 10, 9), "SUCESSO", None, None, None, None, None)]))
    select_sql = cursor.calls[4][0]
    assert "etl_workspace_execucao" not in select_sql and "NULL, NULL FROM" in select_sql
    assert out["versionsAvailable"] is False and out["items"][0]["versionNumber"] is None
    filtered, cursor, _ = _history(monkeypatch, Cursor(versions=False), version=3)
    assert filtered["items"] == [] and filtered["total"] == 0 and filtered["versionsAvailable"] is False
    assert not any(sql.startswith("SELECT COUNT(*)") for sql, _ in cursor.calls)


def test_history_db_failure_is_sanitized_and_closes(monkeypatch):
    cursor = Cursor(fail=True)
    with pytest.raises(HTTPException) as error:
        _history(monkeypatch, cursor)
    assert error.value.status_code == 503 and "synthetic-private" not in error.value.detail
    assert cursor.closed
