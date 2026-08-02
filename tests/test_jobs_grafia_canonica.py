"""
Canonização da grafia do pipeline na gravação de etapas (api/routers/jobs.py).

Incidente 2026-08-01: pipeline registrado em MAIÚSCULAS ('SEQSSDVIDA6SINISTRO')
recebeu etapas em CamelCase ('SeqSsdVida6Sinistro'). A colação CI do SQL Server
junta tudo, mas os dicts da dag_factory são case-sensitive → o pipeline "não
tem etapas" e o run inteiro morre em "pipeline sem nenhuma etapa".

Aqui garantimos que os DOIS caminhos de gravação (POST /pipelines/jobs/register
e o POST /pipelines/{p}/fluxo do canvas) buscam a grafia REGISTRADA em
dbo.etl_pipeline e a usam em TODAS as gravações — e que, sem registro prévio,
a grafia do request é mantida (comportamento atual do wizard).

Padrão de test_finalizacao.py: TestClient do conftest, get_db_conn mockado em
routers.jobs e autenticação via dependency_overrides — nada toca rede ou banco.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()
os.environ.setdefault("MSSQL_CONN_STR", "__mock__")
from api.main import app as _app  # noqa: F401  (ordem de import — ver test_copias.py)

from deps import PERM_EDITAR, get_current_user

GRAFIA_IMPORT  = "SeqSsdVida6Sinistro"    # como veio do .dsx / request
GRAFIA_OFICIAL = "SEQSSDVIDA6SINISTRO"    # como está registrada em etl_pipeline

# Todas as colunas opcionais presentes → os UPDATEs por-coluna rodam e também
# precisam sair com a grafia oficial.
_COLS_OPCIONAIS = [
    "depends_on_jobs", "mssql_database", "condition_json", "notify_json",
    "sql_json", "python_json", "aguarde_json", "layout_x", "layout_y",
    "ssh_conn_id", "verbose_log", "mssql_conn_id",
]


class _FakeCursor:
    """Cursor roteado pelo TEXTO do SQL (robusto a reordenação de queries):
    devolve a grafia registrada no SELECT de etl_pipeline e registra cada
    execute em ``executed`` para as asserções de gravação."""

    def __init__(self, oficial: str | None, owned: list[tuple] | None = None):
        self.oficial = oficial
        self.owned = owned or []
        self.executed: list[tuple[str, tuple]] = []
        self._last = ""

    def execute(self, sql, params=None):
        self._last = sql
        self.executed.append((sql, tuple(params) if params is not None else ()))

    def fetchone(self):
        if "FROM dbo.etl_pipeline WHERE pipeline_name" in self._last:
            return (self.oficial,) if self.oficial else None
        if "INFORMATION_SCHEMA.COLUMNS" in self._last:
            return (1,)   # COUNT(*) das colunas opcionais → todas existem
        return None

    def fetchall(self):
        if "INFORMATION_SCHEMA.COLUMNS" in self._last:
            return [(c,) for c in _COLS_OPCIONAIS]
        if "SELECT job_name FROM dbo.etl_pipeline_job" in self._last:
            return list(self.owned)
        return []

    def close(self):
        pass


def _mock_conn(cur):
    conn = MagicMock()
    conn.cursor.return_value = cur
    return conn


def _writes(cur):
    """Só as gravações (EXEC/UPDATE/DELETE/INSERT) — o SELECT de canonização
    carrega a grafia do request de propósito e fica de fora."""
    return [(s, p) for (s, p) in cur.executed
            if s.lstrip().upper().startswith(("EXEC", "UPDATE", "DELETE", "INSERT"))]


@pytest.fixture
def auth_editar(app):
    app.dependency_overrides[get_current_user] = lambda: {
        "matricula": "DEV1", "perfil": "desenvolvedor", "permissoes": [PERM_EDITAR],
    }
    yield
    app.dependency_overrides.pop(get_current_user, None)


# ── POST /pipelines/jobs/register ────────────────────────────────────────────

def _post_register(client, cur, pipeline_name=GRAFIA_IMPORT):
    with patch("routers.jobs.get_db_conn", return_value=_mock_conn(cur)), \
         patch("routers.jobs._list_mssql_conn_ids", new=AsyncMock(return_value=None)):
        return client.post("/pipelines/jobs/register", json={
            "pipeline_name": pipeline_name,
            "require_lineage": False,
            "jobs": [{"job_name": "JobEtapa1", "execution_order": 1,
                      "job_type": "datastage", "job_command": "JobEtapa1"}],
        })


def test_register_grava_com_grafia_oficial(client, auth_editar):
    """Etapa enviada em CamelCase num pipeline MAIÚSCULO → toda gravação sai
    com a grafia registrada (a que a dag_factory vai procurar)."""
    cur = _FakeCursor(oficial=GRAFIA_OFICIAL)
    r = _post_register(client, cur)
    assert r.status_code == 200
    assert r.json()["pipeline_name"] == GRAFIA_OFICIAL

    writes = _writes(cur)
    assert writes, "nenhuma gravação executada"
    for sql, params in writes:
        assert GRAFIA_IMPORT not in params, f"grafia do request vazou em: {sql}"
    assert any(GRAFIA_OFICIAL in params for _, params in writes)


def test_register_upsert_do_job_usa_grafia_oficial(client, auth_editar):
    """O EXEC do upsert (a linha que a factory lê) leva a grafia registrada."""
    cur = _FakeCursor(oficial=GRAFIA_OFICIAL)
    assert _post_register(client, cur).status_code == 200
    upserts = [(s, p) for s, p in cur.executed if "sp_etl_pipeline_job_upsert" in s]
    assert upserts
    assert all(p[0] == GRAFIA_OFICIAL for _, p in upserts)


def test_register_sem_registro_mantem_grafia_do_request(client, auth_editar):
    """Pipeline ainda não registrado (wizard salva jobs antes) → comportamento
    atual: a grafia do request é a oficial."""
    cur = _FakeCursor(oficial=None)
    r = _post_register(client, cur)
    assert r.status_code == 200
    assert r.json()["pipeline_name"] == GRAFIA_IMPORT
    assert any(GRAFIA_IMPORT in params for _, params in _writes(cur))


def test_register_grafia_identica_nao_muda_nada(client, auth_editar):
    """Grafia do request já é a registrada → nada muda (não-regressão)."""
    cur = _FakeCursor(oficial=GRAFIA_OFICIAL)
    r = _post_register(client, cur, pipeline_name=GRAFIA_OFICIAL)
    assert r.status_code == 200
    assert r.json()["pipeline_name"] == GRAFIA_OFICIAL


# ── POST /pipelines/{p}/fluxo (canvas v2) ────────────────────────────────────

def _post_fluxo(client, cur, body):
    with patch("routers.jobs.get_db_conn", return_value=_mock_conn(cur)):
        return client.post(f"/pipelines/{GRAFIA_IMPORT}/fluxo", json=body)


def test_fluxo_grava_com_grafia_oficial(client, auth_editar):
    """O canvas salvando com a grafia divergente na URL → gravações (upsert,
    deps, layout) saem todas com a grafia registrada."""
    cur = _FakeCursor(oficial=GRAFIA_OFICIAL)
    r = _post_fluxo(client, cur, {
        "nodes": [{"job_name": "JobEtapa1", "job_type": "datastage",
                   "job_command": "JobEtapa1", "execution_order": 1,
                   "depends_on_jobs": [], "layout_x": 10, "layout_y": 20}],
    })
    assert r.status_code == 200
    assert r.json()["saved"] == 1

    writes = _writes(cur)
    assert writes, "nenhuma gravação executada"
    for sql, params in writes:
        assert GRAFIA_IMPORT not in params, f"grafia do request vazou em: {sql}"
    assert any(GRAFIA_OFICIAL in params for _, params in writes)


def test_fluxo_delete_usa_grafia_oficial(client, auth_editar):
    """A remoção de nó no canvas também precisa apagar pela grafia registrada —
    senão o DELETE por grafia divergente 'funciona' via CI hoje, mas quebraria
    junto com qualquer consulta case-sensitive futura."""
    cur = _FakeCursor(oficial=GRAFIA_OFICIAL, owned=[("JobVelho",)])
    r = _post_fluxo(client, cur, {"nodes": [], "deleted": ["JobVelho"]})
    assert r.status_code == 200
    assert r.json()["deleted"] == 1
    deletes = [(s, p) for s, p in cur.executed if s.lstrip().upper().startswith("DELETE")]
    assert len(deletes) == 2   # lineage + job
    assert all(p == (GRAFIA_OFICIAL, "JobVelho") for _, p in deletes)


def test_fluxo_sem_registro_mantem_grafia_do_request(client, auth_editar):
    cur = _FakeCursor(oficial=None)
    r = _post_fluxo(client, cur, {
        "nodes": [{"job_name": "JobEtapa1", "job_type": "datastage",
                   "job_command": "JobEtapa1", "execution_order": 1}],
    })
    assert r.status_code == 200
    assert any(GRAFIA_IMPORT in params for _, params in _writes(cur))
