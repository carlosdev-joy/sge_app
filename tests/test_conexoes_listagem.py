"""
Testes da LISTAGEM unificada de conexões MSSQL (fix pós-PR #148).

O PR #148 fez de dbo.etl_conexao a fonte da verdade e uniu as duas fontes na
RESOLUÇÃO (host/porta, allowlist) — mas três pontos de LISTAGEM/validação
seguiam olhando só o Airflow, então conexões nascidas no Orquestra não
apareciam na tela de cópia nem nos selects do nó SQL, e o save de pipeline
com conn nativa era recusado:

  - GET /copias/conexoes          (wizard da Cópia de Dados)
  - GET /airflow/connections/mssql (nó SQL/decisão — Jobs e FluxoEditor)
  - jobs._list_mssql_conn_ids      (validação de conn_id no save)

Regras testadas: união das fontes, Orquestra vence em conn_id repetido,
cada fonte degrada de forma independente na listagem, e a validação do save
devolve None (permissiva) se QUALQUER fonte falhar.
"""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from deps import get_current_user


def _mock_conn(cur):
    conn = MagicMock()
    conn.cursor.return_value = cur
    return conn


class _FakeResp:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}

    @property
    def is_success(self):
        return 200 <= self.status_code < 300

    def json(self):
        return self._payload


class _FakeAirflowClient:
    """Stub do httpx.AsyncClient de get_airflow_client (async context manager)."""

    def __init__(self, get_resp=None, get_exc=None):
        self.get_calls: list = []
        self._get_resp = get_resp or _FakeResp(200, {})
        self._get_exc = get_exc

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, **kw):
        self.get_calls.append((url, kw))
        if self._get_exc is not None:
            raise self._get_exc
        return self._get_resp


@pytest.fixture
def auth_user(app):
    app.dependency_overrides[get_current_user] = lambda: {
        "matricula": "TESTER", "perfil": "admin", "permissoes": []}
    yield
    app.dependency_overrides.pop(get_current_user, None)


_AIRFLOW_CONNS = _FakeResp(200, {"connections": [
    {"connection_id": "SQL14_DMDB41", "conn_type": "mssql", "host": "sql14",
     "port": 1433, "schema": "", "description": "legada"},
    # conn_id repetido — o registro do Orquestra deve vencer
    {"connection_id": "SRV_NOVA", "conn_type": "mssql", "host": "host-velho",
     "port": None, "schema": "", "description": "duplicada no Airflow"},
    {"connection_id": "SSH_UNIX", "conn_type": "ssh", "host": "unix01"},
]})

# linhas de dbo.etl_conexao: (conn_id, host, port, descricao)
_ROWS_ORQUESTRA = [("SRV_NOVA", "sql99", 1450, "Criada no Orquestra"),
                   ("SRV_SO_ORQ", "sql77", None, None)]


# ═══════════════════ GET /copias/conexoes (wizard de cópia) ═════════════════

def test_copias_conexoes_une_orquestra_e_airflow(client, auth_user):
    cur = MagicMock()
    cur.fetchall.return_value = list(_ROWS_ORQUESTRA)
    fake = _FakeAirflowClient(get_resp=_AIRFLOW_CONNS)
    with patch("routers.copias.get_db_conn", return_value=_mock_conn(cur)), \
         patch("routers.copias.get_airflow_client", return_value=fake):
        r = client.get("/copias/conexoes")
    assert r.status_code == 200
    conns = r.json()["connections"]
    por_id = {c["conn_id"]: c for c in conns}
    # união: 2 do Orquestra + 1 só do Airflow; ssh fica de fora
    assert set(por_id) == {"SRV_NOVA", "SRV_SO_ORQ", "SQL14_DMDB41"}
    # conn_id repetido → dados do Orquestra (host/porta/descrição)
    assert por_id["SRV_NOVA"]["host"] == "sql99"
    assert por_id["SRV_NOVA"]["port"] == 1450
    assert por_id["SRV_NOVA"]["description"] == "Criada no Orquestra"
    # ordenada por conn_id (case-insensitive) para o select da UI
    assert [c["conn_id"] for c in conns] == sorted(
        [c["conn_id"] for c in conns], key=str.lower)


def test_copias_conexoes_degrada_sem_tabela(client, auth_user):
    """etl_conexao indisponível (pré-054) → lista só as do Airflow."""
    fake = _FakeAirflowClient(get_resp=_AIRFLOW_CONNS)
    with patch("routers.copias.get_db_conn",
               side_effect=Exception("tabela não existe")), \
         patch("routers.copias.get_airflow_client", return_value=fake):
        r = client.get("/copias/conexoes")
    assert r.status_code == 200
    ids = {c["conn_id"] for c in r.json()["connections"]}
    assert ids == {"SQL14_DMDB41", "SRV_NOVA"}


def test_copias_conexoes_degrada_sem_airflow(client, auth_user):
    """Airflow fora → lista só as do Orquestra (era o cenário do bug:
    antes do fix, este caso devolvia lista VAZIA)."""
    cur = MagicMock()
    cur.fetchall.return_value = list(_ROWS_ORQUESTRA)
    fake = _FakeAirflowClient(get_exc=RuntimeError("airflow fora"))
    with patch("routers.copias.get_db_conn", return_value=_mock_conn(cur)), \
         patch("routers.copias.get_airflow_client", return_value=fake):
        r = client.get("/copias/conexoes")
    assert r.status_code == 200
    ids = {c["conn_id"] for c in r.json()["connections"]}
    assert ids == {"SRV_NOVA", "SRV_SO_ORQ"}


# ══════════════ GET /airflow/connections/mssql (nó SQL/decisão) ═════════════

def test_airflow_connections_mssql_une_fontes(client, auth_user):
    cur = MagicMock()
    # (conn_id, host, descricao) — este endpoint não expõe porta
    cur.fetchall.return_value = [("SRV_NOVA", "sql99", "Criada no Orquestra")]
    fake = _FakeAirflowClient(get_resp=_AIRFLOW_CONNS)
    with patch("routers.airflow.get_db_conn", return_value=_mock_conn(cur)), \
         patch("routers.airflow.get_airflow_client", return_value=fake):
        r = client.get("/airflow/connections/mssql")
    assert r.status_code == 200
    por_id = {c["conn_id"]: c for c in r.json()["connections"]}
    assert set(por_id) == {"SRV_NOVA", "SQL14_DMDB41"}
    assert por_id["SRV_NOVA"]["host"] == "sql99"          # Orquestra vence
    assert por_id["SRV_NOVA"]["description"] == "Criada no Orquestra"


# ═══════════ jobs._list_mssql_conn_ids (validação de save) ══════════════════

def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def test_list_mssql_conn_ids_une_fontes(app):
    from routers import jobs as jobs_mod
    cur = MagicMock()
    cur.fetchall.return_value = [("SRV_NOVA",), ("SRV_SO_ORQ",)]
    fake = _FakeAirflowClient(get_resp=_AIRFLOW_CONNS)
    with patch("routers.jobs.get_db_conn", return_value=_mock_conn(cur)), \
         patch("routers.jobs.get_airflow_client", return_value=fake):
        ids = _run(jobs_mod._list_mssql_conn_ids())
    assert ids == {"SRV_NOVA", "SRV_SO_ORQ", "SQL14_DMDB41"}


def test_list_mssql_conn_ids_none_se_qualquer_fonte_falha(app):
    """None = validação permissiva (não bloqueia o save): uma conexão nativa
    não pode ser recusada porque a tabela ou o Airflow estavam fora."""
    from routers import jobs as jobs_mod
    fake_ok = _FakeAirflowClient(get_resp=_AIRFLOW_CONNS)
    with patch("routers.jobs.get_db_conn", side_effect=Exception("db fora")), \
         patch("routers.jobs.get_airflow_client", return_value=fake_ok):
        assert _run(jobs_mod._list_mssql_conn_ids()) is None

    cur = MagicMock()
    cur.fetchall.return_value = [("SRV_NOVA",)]
    fake_erro = _FakeAirflowClient(get_exc=RuntimeError("airflow fora"))
    with patch("routers.jobs.get_db_conn", return_value=_mock_conn(cur)), \
         patch("routers.jobs.get_airflow_client", return_value=fake_erro):
        assert _run(jobs_mod._list_mssql_conn_ids()) is None
