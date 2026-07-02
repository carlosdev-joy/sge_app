"""
Testes das actions de Conexões de Dados do POST /admin (api/routers/admin.py):
conn_list / conn_upsert / conn_delete / conn_test.

Padrão de test_copias.py: TestClient do conftest, get_db_conn/get_airflow_client
mockados em routers.admin e autenticação sobrescrita via dependency_overrides.
O Airflow é stubado por um AsyncClient fake com roteamento por método+URL —
nenhum teste toca rede ou banco.
"""
from __future__ import annotations

import json
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Replica o mock de pyodbc do conftest (garante o import de api.main mesmo se
# este arquivo for coletado antes do conftest configurar o ambiente).
if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()
os.environ.setdefault("MSSQL_CONN_STR", "__mock__")
from api.main import app as _app  # noqa: F401  (ordem de import — ver test_copias.py)

from deps import PERM_ADMIN, get_current_user
from fastapi import HTTPException


# ── stubs ────────────────────────────────────────────────────────────────────

def _mock_cursor():
    cur = MagicMock()
    cur.description = []
    cur.fetchall.return_value = []
    return cur


def _mock_conn(cur):
    conn = MagicMock()
    conn.cursor.return_value = cur
    return conn


class _FakeResp:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.text = text

    @property
    def is_success(self):
        return 200 <= self.status_code < 300

    def json(self):
        return self._payload


class _FakeAirflowClient:
    """Stub do httpx.AsyncClient de get_airflow_client, com roteamento por
    (método, URL) via handler; registra todas as chamadas em ``calls``."""

    def __init__(self, handler=None):
        self.calls: list[tuple[str, str, dict]] = []
        self._handler = handler or (lambda m, u, kw: _FakeResp(200, {}))

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def _do(self, method, url, kw):
        self.calls.append((method, url, kw))
        return self._handler(method, url, kw)

    async def get(self, url, **kw):
        return await self._do("GET", url, kw)

    async def post(self, url, **kw):
        return await self._do("POST", url, kw)

    async def patch(self, url, **kw):
        return await self._do("PATCH", url, kw)

    async def delete(self, url, **kw):
        return await self._do("DELETE", url, kw)


@pytest.fixture
def auth_admin(app):
    app.dependency_overrides[get_current_user] = lambda: {
        "matricula": "ADMIN1", "perfil": "admin", "permissoes": [PERM_ADMIN],
    }
    yield
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def auth_sem_admin(app):
    app.dependency_overrides[get_current_user] = lambda: {
        "matricula": "USER1", "perfil": "consulta", "permissoes": [],
    }
    yield
    app.dependency_overrides.pop(get_current_user, None)


def _admin_post(client, fake_airflow, body, cur=None):
    """POST /admin com get_db_conn e get_airflow_client mockados."""
    cur = cur or _mock_cursor()
    with patch("routers.admin.get_db_conn", return_value=_mock_conn(cur)), \
         patch("routers.admin.get_airflow_client", return_value=fake_airflow):
        return client.post("/admin", json=body)


# ── auth ─────────────────────────────────────────────────────────────────────

def test_conn_actions_exigem_admin(client, auth_sem_admin):
    for action in ("conn_list", "conn_upsert", "conn_delete", "conn_test"):
        r = client.post("/admin", json={"action": action})
        assert r.status_code == 403, action


def test_conn_actions_sem_auth_401(client):
    assert client.post("/admin", json={"action": "conn_list"}).status_code == 401


# ── conn_list ────────────────────────────────────────────────────────────────

def test_conn_list_filtra_mssql_e_extrai_charset(client, auth_admin):
    payload = {"connections": [
        {"connection_id": "MSSQL_A", "conn_type": "mssql", "host": "srv-a",
         "port": 1450, "schema": "dbo", "login": "sa", "description": "origem",
         "extra": json.dumps({"charset": "CP1252", "outra_chave": 1})},
        {"connection_id": "SSH_B", "conn_type": "ssh", "host": "srv-b"},
        {"connection_id": "MSSQL_C", "conn_type": "mssql", "host": "srv-c",
         "extra": ""},
        {"connection_id": "HTTP_D", "conn_type": "http", "host": "srv-d"},
    ]}
    fake = _FakeAirflowClient(lambda m, u, kw: _FakeResp(200, payload))
    r = _admin_post(client, fake, {"action": "conn_list"})
    assert r.status_code == 200
    conns = r.json()["connections"]
    assert [c["conn_id"] for c in conns] == ["MSSQL_A", "MSSQL_C"]
    assert conns[0] == {"conn_id": "MSSQL_A", "host": "srv-a", "port": 1450,
                        "schema": "dbo", "login": "sa", "description": "origem",
                        "extra_charset": "CP1252"}
    assert conns[1]["extra_charset"] is None
    # nunca devolve password (a API do Airflow nem envia)
    assert "password" not in r.text
    assert fake.calls[0][:2] == ("GET", "/api/v1/connections?limit=100")


def test_conn_list_busca_detalhe_quando_lista_omite_extra(client, auth_admin):
    """Airflow 2.x não devolve 'extra' no endpoint de LISTA (campo sensível,
    só no GET por id) — o conn_list busca o detalhe para extrair o charset."""
    lista = {"connections": [
        {"connection_id": "MSSQL_A", "conn_type": "mssql", "host": "srv-a"},
        {"connection_id": "MSSQL_B", "conn_type": "mssql", "host": "srv-b"},
    ]}

    def _handler(method, url, kw):
        if url == "/api/v1/connections?limit=100":
            return _FakeResp(200, lista)
        if url == "/api/v1/connections/MSSQL_A":
            return _FakeResp(200, {"connection_id": "MSSQL_A",
                                   "conn_type": "mssql", "host": "srv-a",
                                   "extra": json.dumps({"charset": "CP850"})})
        return _FakeResp(500)  # detalhe de MSSQL_B falha → charset None

    fake = _FakeAirflowClient(_handler)
    r = _admin_post(client, fake, {"action": "conn_list"})
    assert r.status_code == 200
    conns = r.json()["connections"]
    assert conns[0]["extra_charset"] == "CP850"
    assert conns[1]["extra_charset"] is None
    urls = [u for m, u, _ in fake.calls if m == "GET"]
    assert "/api/v1/connections/MSSQL_A" in urls
    assert "/api/v1/connections/MSSQL_B" in urls


def test_conn_list_airflow_fora_502(client, auth_admin):
    fake = _FakeAirflowClient(lambda m, u, kw: _FakeResp(500))
    r = _admin_post(client, fake, {"action": "conn_list"})
    assert r.status_code == 502


# ── conn_upsert — validações ────────────────────────────────────────────────

@pytest.mark.parametrize("ruim", ["", "com espaço", "com.ponto", "a" * 101, "x;y", "ç"])
def test_conn_upsert_422_conn_id_invalido(client, auth_admin, ruim):
    r = _admin_post(client, _FakeAirflowClient(),
                    {"action": "conn_upsert", "conn_id": ruim, "host": "srv"})
    assert r.status_code == 422


def test_conn_upsert_422_host_obrigatorio_e_valido(client, auth_admin):
    r = _admin_post(client, _FakeAirflowClient(),
                    {"action": "conn_upsert", "conn_id": "C1", "host": ""})
    assert r.status_code == 422
    assert "host" in r.json()["detail"]
    r = _admin_post(client, _FakeAirflowClient(),
                    {"action": "conn_upsert", "conn_id": "C1", "host": "srv;DROP"})
    assert r.status_code == 422


@pytest.mark.parametrize("porta", [0, -1, 65536, "abc"])
def test_conn_upsert_422_porta_invalida(client, auth_admin, porta):
    r = _admin_post(client, _FakeAirflowClient(),
                    {"action": "conn_upsert", "conn_id": "C1", "host": "srv",
                     "login": "sa", "password": "x", "port": porta})
    assert r.status_code == 422


# ── conn_upsert — criação (GET 404 → POST) ───────────────────────────────────

def _handler_inexistente(method, url, kw):
    if method == "GET":
        return _FakeResp(404)
    return _FakeResp(200, {})


def test_conn_upsert_cria_via_post_quando_nao_existe(client, auth_admin):
    fake = _FakeAirflowClient(_handler_inexistente)
    r = _admin_post(client, fake, {
        "action": "conn_upsert", "conn_id": "NOVA_CONN", "host": "srv1",
        "login": "sa", "password": "s3nh@!", "description": "Origem BI",
        "charset": "CP1252"})
    assert r.status_code == 200
    assert r.json()["sucesso"] is True and r.json()["criada"] is True
    assert "s3nh@!" not in r.text  # resposta nunca ecoa a senha
    posts = [c for c in fake.calls if c[0] == "POST"]
    assert len(posts) == 1
    assert posts[0][1] == "/api/v1/connections"
    payload = posts[0][2]["json"]
    assert payload == {"connection_id": "NOVA_CONN", "conn_type": "mssql",
                       "host": "srv1", "port": 1433, "login": "sa",
                       "password": "s3nh@!", "description": "Origem BI",
                       "extra": json.dumps({"charset": "CP1252"})}


def test_conn_upsert_criacao_exige_login_e_password(client, auth_admin):
    r = _admin_post(client, _FakeAirflowClient(_handler_inexistente), {
        "action": "conn_upsert", "conn_id": "NOVA", "host": "srv1", "login": "sa"})
    assert r.status_code == 422
    assert "password" in r.json()["detail"]
    r = _admin_post(client, _FakeAirflowClient(_handler_inexistente), {
        "action": "conn_upsert", "conn_id": "NOVA", "host": "srv1", "password": "x"})
    assert r.status_code == 422
    assert "login" in r.json()["detail"]


def test_conn_upsert_criacao_sem_charset_nao_manda_extra(client, auth_admin):
    fake = _FakeAirflowClient(_handler_inexistente)
    r = _admin_post(client, fake, {
        "action": "conn_upsert", "conn_id": "NOVA", "host": "srv1",
        "login": "sa", "password": "x"})
    assert r.status_code == 200
    payload = [c for c in fake.calls if c[0] == "POST"][0][2]["json"]
    assert "extra" not in payload
    assert payload["port"] == 1433  # default


# ── conn_upsert — atualização (PATCH + update_mask) ──────────────────────────

_ATUAL = {"connection_id": "CONN_X", "conn_type": "mssql", "host": "srv-old",
          "port": 1433, "login": "sa_old", "description": "antiga",
          "extra": json.dumps({"charset": "CP850", "chave_livre": "fica"})}


def _handler_existente(method, url, kw):
    if method == "GET":
        return _FakeResp(200, _ATUAL)
    return _FakeResp(200, {})


def test_conn_upsert_atualiza_via_patch_com_update_mask(client, auth_admin):
    fake = _FakeAirflowClient(_handler_existente)
    r = _admin_post(client, fake, {
        "action": "conn_upsert", "conn_id": "CONN_X", "host": "srv-novo",
        "port": 1450, "login": "sa_novo", "description": "nova",
        "charset": "UTF-8"})   # SEM password → mantém a atual
    assert r.status_code == 200
    body = r.json()
    assert body["criada"] is False
    patches = [c for c in fake.calls if c[0] == "PATCH"]
    assert len(patches) == 1
    assert patches[0][1] == "/api/v1/connections/CONN_X"
    mask = patches[0][2]["params"]["update_mask"].split(",")
    payload = patches[0][2]["json"]
    # senha ausente = FORA do update_mask e do payload (mantém a do Airflow)
    assert "password" not in mask and "password" not in payload
    assert set(mask) == {"host", "port", "login", "description", "extra"}
    assert payload["host"] == "srv-novo" and payload["port"] == 1450
    assert payload["login"] == "sa_novo" and payload["description"] == "nova"
    # merge do extra: charset trocado E chave alheia preservada
    assert json.loads(payload["extra"]) == {"charset": "UTF-8",
                                            "chave_livre": "fica"}


def test_conn_upsert_com_password_entra_no_mask(client, auth_admin):
    fake = _FakeAirflowClient(_handler_existente)
    r = _admin_post(client, fake, {
        "action": "conn_upsert", "conn_id": "CONN_X", "host": "srv-old",
        "login": "sa_old", "password": "NovaSenha1"})
    assert r.status_code == 200
    assert "NovaSenha1" not in r.text
    patches = [c for c in fake.calls if c[0] == "PATCH"]
    mask = patches[0][2]["params"]["update_mask"].split(",")
    assert "password" in mask
    assert patches[0][2]["json"]["password"] == "NovaSenha1"
    # port/description/charset não enviados → fora do mask
    assert "port" not in mask and "description" not in mask and "extra" not in mask


def test_conn_upsert_charset_igual_nao_inclui_extra_no_mask(client, auth_admin):
    fake = _FakeAirflowClient(_handler_existente)
    r = _admin_post(client, fake, {
        "action": "conn_upsert", "conn_id": "CONN_X", "host": "srv-old",
        "login": "sa_old", "charset": "CP850"})  # igual ao atual
    assert r.status_code == 200
    mask = [c for c in fake.calls if c[0] == "PATCH"][0][2]["params"]["update_mask"]
    assert "extra" not in mask.split(",")


def test_conn_upsert_charset_vazio_remove_a_chave_preservando_extra(client, auth_admin):
    fake = _FakeAirflowClient(_handler_existente)
    r = _admin_post(client, fake, {
        "action": "conn_upsert", "conn_id": "CONN_X", "host": "srv-old",
        "login": "sa_old", "charset": ""})
    assert r.status_code == 200
    patch_call = [c for c in fake.calls if c[0] == "PATCH"][0]
    assert "extra" in patch_call[2]["params"]["update_mask"].split(",")
    assert json.loads(patch_call[2]["json"]["extra"]) == {"chave_livre": "fica"}


def test_conn_upsert_409_se_existente_nao_for_mssql(client, auth_admin):
    atual_ssh = {"connection_id": "CONN_X", "conn_type": "ssh", "host": "h"}
    fake = _FakeAirflowClient(
        lambda m, u, kw: _FakeResp(200, atual_ssh) if m == "GET" else _FakeResp(200))
    r = _admin_post(client, fake, {
        "action": "conn_upsert", "conn_id": "CONN_X", "host": "srv",
        "login": "sa"})
    assert r.status_code == 409
    assert "ssh" in r.json()["detail"]
    assert not [c for c in fake.calls if c[0] in ("PATCH", "POST")]


# ── conn_delete ──────────────────────────────────────────────────────────────

def test_conn_delete_409_quando_referenciada(client, auth_admin):
    cur = _mock_cursor()
    # 1ª consulta: cópias ativas; 2ª: jobs de pipeline com nó SQL
    cur.fetchall.side_effect = [[("Copia Clientes",)],
                                [("PIPE_BI", "job_carga")]]
    fake = _FakeAirflowClient()
    r = _admin_post(client, fake, {"action": "conn_delete", "conn_id": "CONN_X"},
                    cur=cur)
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert "Copia Clientes" in detail
    assert "job_carga" in detail and "PIPE_BI" in detail
    assert fake.calls == []  # não chega a chamar o Airflow


def test_conn_delete_livre_chama_delete_do_airflow(client, auth_admin):
    cur = _mock_cursor()
    cur.fetchall.side_effect = [[], []]
    fake = _FakeAirflowClient(lambda m, u, kw: _FakeResp(204))
    r = _admin_post(client, fake, {"action": "conn_delete", "conn_id": "CONN_X"},
                    cur=cur)
    assert r.status_code == 200
    assert r.json()["sucesso"] is True
    assert fake.calls == [("DELETE", "/api/v1/connections/CONN_X", {})]


def test_conn_delete_degrada_sem_tabelas_e_exclui(client, auth_admin):
    """Tabelas de referência ausentes (migrations não aplicadas) → a guarda é
    ignorada graciosamente e a exclusão segue."""
    cur = _mock_cursor()
    cur.execute.side_effect = Exception("Invalid object name 'dbo.etl_copy_job'")
    fake = _FakeAirflowClient(lambda m, u, kw: _FakeResp(200))
    r = _admin_post(client, fake, {"action": "conn_delete", "conn_id": "CONN_X"},
                    cur=cur)
    assert r.status_code == 200
    assert [c[0] for c in fake.calls] == ["DELETE"]


def test_conn_delete_404_inexistente_no_airflow(client, auth_admin):
    cur = _mock_cursor()
    cur.fetchall.side_effect = [[], []]
    fake = _FakeAirflowClient(lambda m, u, kw: _FakeResp(404))
    r = _admin_post(client, fake, {"action": "conn_delete", "conn_id": "SUMIU"},
                    cur=cur)
    assert r.status_code == 404


def test_conn_delete_422_conn_id_invalido(client, auth_admin):
    r = _admin_post(client, _FakeAirflowClient(),
                    {"action": "conn_delete", "conn_id": "tem espaço"})
    assert r.status_code == 422


# ── conn_test — modo (a): senha em mãos, pyodbc direto ───────────────────────

def test_conn_test_direto_ok_roda_select_1(client, auth_admin):
    with patch("routers.admin.pyodbc") as fake_pyodbc, \
         patch("routers.admin.get_db_conn",
               return_value=_mock_conn(_mock_cursor())):
        fake_pyodbc.drivers.return_value = [
            "ODBC Driver 17 for SQL Server", "ODBC Driver 18 for SQL Server"]
        cx = MagicMock()
        fake_pyodbc.connect.return_value = cx
        r = client.post("/admin", json={
            "action": "conn_test", "host": "srv1", "port": 1450,
            "login": "sa", "password": "s3cr3t!", "database": "DB_A"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert "s3cr3t!" not in r.text  # a senha NUNCA volta na resposta
    conn_str = fake_pyodbc.connect.call_args.args[0]
    assert "DRIVER={ODBC Driver 18 for SQL Server}" in conn_str
    assert "SERVER=srv1,1450" in conn_str
    assert "DATABASE={DB_A}" in conn_str
    assert "PWD={s3cr3t!}" in conn_str
    assert "TrustServerCertificate=yes" in conn_str
    assert fake_pyodbc.connect.call_args.kwargs["timeout"] == 5
    cx.cursor.return_value.execute.assert_called_once_with("SELECT 1")
    cx.close.assert_called_once()


def test_conn_test_direto_falha_sem_ecoar_senha(client, auth_admin):
    with patch("routers.admin.pyodbc") as fake_pyodbc, \
         patch("routers.admin.get_db_conn",
               return_value=_mock_conn(_mock_cursor())):
        fake_pyodbc.drivers.return_value = ["ODBC Driver 18 for SQL Server"]
        fake_pyodbc.connect.side_effect = Exception(
            "Login failed for user 'sa' (PWD=s3cr3t!)")
        r = client.post("/admin", json={
            "action": "conn_test", "host": "srv1",
            "login": "sa", "password": "s3cr3t!"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert "Login failed" in body["mensagem"]
    assert "s3cr3t!" not in r.text  # mensagem de erro sanitizada
    assert "••••" in body["mensagem"]


def test_conn_test_direto_422_sem_host_ou_login(client, auth_admin):
    r = _admin_post(client, _FakeAirflowClient(),
                    {"action": "conn_test", "password": "x", "login": "sa"})
    assert r.status_code == 422
    r = _admin_post(client, _FakeAirflowClient(),
                    {"action": "conn_test", "password": "x", "host": "srv"})
    assert r.status_code == 422


# ── conn_test — modo (b): connection salva (reuso do caminho de copias) ──────

def test_conn_test_salva_caminho_direto(client, auth_admin):
    with patch("routers.admin.get_db_conn",
               return_value=_mock_conn(_mock_cursor())), \
         patch("routers.admin._server_da_conexao",
               new=AsyncMock(return_value="srv1,1433")), \
         patch("routers.admin._consulta_direta",
               return_value=[("master",), ("DB_A",)]):
        r = client.post("/admin", json={"action": "conn_test",
                                        "conn_id": "CONN_X"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True and body["via"] == "direto"
    assert "2 banco(s)" in body["mensagem"]


def test_conn_test_salva_fallback_dag(client, auth_admin):
    with patch("routers.admin.get_db_conn",
               return_value=_mock_conn(_mock_cursor())), \
         patch("routers.admin._server_da_conexao",
               new=AsyncMock(return_value="srv1,1433")), \
         patch("routers.admin._consulta_direta",
               side_effect=HTTPException(status_code=400, detail="login failed")), \
         patch("routers.admin._introspect_via_dag",
               new=AsyncMock(return_value=({"databases": ["a", "b", "c"]},
                                           "airflow"))):
        r = client.post("/admin", json={"action": "conn_test",
                                        "conn_id": "CONN_X"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True and body["via"] == "airflow"
    assert "3 banco(s)" in body["mensagem"]


def test_conn_test_salva_falha_total_ok_false(client, auth_admin):
    with patch("routers.admin.get_db_conn",
               return_value=_mock_conn(_mock_cursor())), \
         patch("routers.admin._server_da_conexao",
               new=AsyncMock(side_effect=HTTPException(
                   status_code=404,
                   detail="connection 'CONN_X' não encontrada no Airflow"))):
        r = client.post("/admin", json={"action": "conn_test",
                                        "conn_id": "CONN_X"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert "não encontrada" in body["mensagem"]


def test_conn_test_422_sem_senha_e_sem_conn_id(client, auth_admin):
    r = _admin_post(client, _FakeAirflowClient(), {"action": "conn_test"})
    assert r.status_code == 422
