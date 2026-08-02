"""
POST /pipelines/{name}/gerar-dag com pipeline inativo → 409 claro.

A sp_etl_pipelines_pendentes_criar filtra active=1: um pipeline inativo nunca
entra no lote da factory e o run terminava "vazio", sem explicação — enquanto a
UI prometia "DAG pausada (pipeline inativo)". Agora a publicação é recusada
ANTES de disparar a factory, com o motivo na mensagem (o GenDagModal exibe o
detail de 4xx via e.message do apiFetch).

Padrão de test_finalizacao.py: TestClient do conftest, get_db_conn/httpx
mockados em routers.pipelines e autenticação via dependency_overrides.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()
os.environ.setdefault("MSSQL_CONN_STR", "__mock__")
from api.main import app as _app  # noqa: F401  (ordem de import — ver test_copias.py)

from deps import PERM_EXECUTAR, get_current_user

MSG_409 = "Pipeline inativo não entra na geração de DAGs — ative-o antes de publicar."


def _conn_active(row):
    """Conexão para _pipeline_active: fetchone → (CAST(active AS INT),) ou None."""
    cur = MagicMock()
    cur.fetchone.return_value = row
    conn = MagicMock()
    conn.cursor.return_value = cur
    return conn


class _FakeResp:
    def __init__(self, status_code=200, text=""):
        self.status_code = status_code
        self.text = text

    @property
    def is_success(self):
        return 200 <= self.status_code < 300


class _FakeAirflow:
    """Stub do httpx.AsyncClient usado direto no gerar-dag (async context
    manager); registra os POSTs em ``calls``."""

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, **kw):
        self.calls.append((url, kw))
        return _FakeResp(200)


@pytest.fixture
def auth_executar(app):
    app.dependency_overrides[get_current_user] = lambda: {
        "matricula": "OP1", "perfil": "operador", "permissoes": [PERM_EXECUTAR],
    }
    yield
    app.dependency_overrides.pop(get_current_user, None)


def _gerar(client, row, fake_airflow=None):
    fake = fake_airflow or _FakeAirflow()
    with patch("routers.pipelines.get_db_conn", return_value=_conn_active(row)), \
         patch("routers.pipelines.httpx.AsyncClient", return_value=fake), \
         patch("routers.pipelines.enqueue_dag_pendente") as m_enq:
        r = client.post("/pipelines/PIPE_X/gerar-dag")
    return r, fake, m_enq


# ── pipeline inativo → 409, sem efeito colateral ─────────────────────────────

def test_gerar_dag_inativo_409_com_mensagem(client, auth_executar):
    r, fake, m_enq = _gerar(client, (0,))
    assert r.status_code == 409
    assert r.json()["detail"] == MSG_409
    assert fake.calls == []          # a factory NÃO foi disparada
    m_enq.assert_not_called()        # nada entra na fila de ativação


def test_gerar_dag_active_null_conta_como_inativo(client, auth_executar):
    """NULL não casa o filtro active=1 da SP — precisa recusar igual ao 0."""
    r, fake, m_enq = _gerar(client, (None,))
    assert r.status_code == 409
    assert r.json()["detail"] == MSG_409
    assert fake.calls == []
    m_enq.assert_not_called()


def test_gerar_dag_pipeline_inexistente_404(client, auth_executar):
    r, fake, _ = _gerar(client, None)
    assert r.status_code == 404
    assert fake.calls == []


# ── pipeline ativo → comportamento atual intacto ─────────────────────────────

def test_gerar_dag_ativo_dispara_factory_e_enfileira(client, auth_executar):
    r, fake, m_enq = _gerar(client, (1,))
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["pipeline_name"] == "PIPE_X"
    assert body["desired_active"] is True

    # A factory foi disparada com o pipeline no conf…
    assert len(fake.calls) == 1
    url, kw = fake.calls[0]
    assert url == "/api/v1/dags/etl_dag_factory/dagRuns"
    assert kw["json"]["conf"]["pipeline_name"] == "PIPE_X"
    # …e a intenção de ativação foi persistida (DAG despausada: ativo).
    m_enq.assert_called_once()
    args = m_enq.call_args.args
    assert args[0] == "PIPE_X"
    assert args[1] is False          # desired_paused
    assert args[2] == "OP1"


def test_gerar_dag_falha_do_airflow_vira_502(client, auth_executar):
    """Não-regressão: pipeline ativo com Airflow fora → 502 (como antes)."""
    class _Fora(_FakeAirflow):
        async def post(self, url, **kw):
            self.calls.append((url, kw))
            return _FakeResp(500, "boom")
    r, fake, m_enq = _gerar(client, (1,), fake_airflow=_Fora())
    assert r.status_code == 502
    m_enq.assert_not_called()
