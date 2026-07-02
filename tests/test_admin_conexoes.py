"""
Testes das actions de Conexões de Dados do POST /admin (api/routers/admin.py):
conn_list / conn_upsert / conn_delete / conn_test / conn_migrate.

A fonte da verdade agora é dbo.etl_conexao (migration 054) — senha cifrada com
Fernet (services/conn_crypto, chave ORQUESTRA_CONN_KEY). O Airflow aparece só
como fallback de leitura/exclusão para conexões legadas e como executor da
migração (DAG etl_admin_manage).

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

from cryptography.fernet import Fernet
from deps import PERM_ADMIN, get_current_user
from fastapi import HTTPException
from services.conn_crypto import decrypt_password, encrypt_password

# Chave Fernet REAL para os testes — encrypt/decrypt rodam de verdade.
_KEY = Fernet.generate_key().decode()


@pytest.fixture(autouse=True)
def conn_key(monkeypatch):
    monkeypatch.setenv("ORQUESTRA_CONN_KEY", _KEY)


# ── stubs ────────────────────────────────────────────────────────────────────

def _mock_cursor():
    cur = MagicMock()
    cur.description = []
    cur.fetchall.return_value = []
    cur.fetchone.return_value = None
    cur.rowcount = 0
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


# ── crypto (services/conn_crypto) ────────────────────────────────────────────

def test_crypto_roundtrip():
    token = encrypt_password("s3nh@!ç")
    assert token != "s3nh@!ç"
    assert decrypt_password(token) == "s3nh@!ç"


def test_crypto_sem_chave_500(monkeypatch):
    monkeypatch.delenv("ORQUESTRA_CONN_KEY", raising=False)
    with pytest.raises(HTTPException) as exc:
        encrypt_password("x")
    assert exc.value.status_code == 500
    assert "ORQUESTRA_CONN_KEY" in exc.value.detail


def test_crypto_chave_errada_500():
    token = encrypt_password("segredo")
    os.environ["ORQUESTRA_CONN_KEY"] = Fernet.generate_key().decode()
    with pytest.raises(HTTPException) as exc:
        decrypt_password(token)
    assert exc.value.status_code == 500
    assert "não corresponde" in exc.value.detail


# ── auth ─────────────────────────────────────────────────────────────────────

def test_conn_actions_exigem_admin(client, auth_sem_admin):
    for action in ("conn_list", "conn_upsert", "conn_delete", "conn_test",
                   "conn_migrate"):
        r = client.post("/admin", json={"action": action})
        assert r.status_code == 403, action


def test_conn_actions_sem_auth_401(client):
    assert client.post("/admin", json={"action": "conn_list"}).status_code == 401


# ── conn_list ────────────────────────────────────────────────────────────────

def test_conn_list_le_da_tabela_e_marca_origem(client, auth_admin):
    cur = _mock_cursor()
    cur.fetchall.return_value = [
        ("MSSQL_A", "srv-a", 1450, "sa", "origem BI",
         json.dumps({"charset": "CP1252"}), "orquestra"),
        ("MSSQL_B", "srv-b", None, "app", None, None, "migrada_airflow"),
    ]
    fake = _FakeAirflowClient(lambda m, u, kw: _FakeResp(200, {"connections": []}))
    r = _admin_post(client, fake, {"action": "conn_list"}, cur=cur)
    assert r.status_code == 200
    conns = r.json()["connections"]
    assert [c["conn_id"] for c in conns] == ["MSSQL_A", "MSSQL_B"]
    assert conns[0]["extra_charset"] == "CP1252"
    assert conns[0]["origem"] == "orquestra"
    assert conns[1]["origem"] == "orquestra"  # migrada = já vive no Orquestra
    assert "senha" not in r.text and "password" not in r.text


def test_conn_list_mescla_airflow_pendentes_sem_duplicar(client, auth_admin):
    cur = _mock_cursor()
    cur.fetchall.return_value = [
        ("MSSQL_A", "srv-a", 1450, "sa", None, None, "orquestra"),
    ]
    payload = {"connections": [
        {"connection_id": "MSSQL_A", "conn_type": "mssql", "host": "srv-a",
         "extra": ""},  # já migrada → não duplica
        {"connection_id": "MSSQL_LEGADA", "conn_type": "mssql", "host": "srv-x",
         "extra": json.dumps({"charset": "CP850"})},
        {"connection_id": "SSH_B", "conn_type": "ssh", "host": "srv-b"},
    ]}
    fake = _FakeAirflowClient(lambda m, u, kw: _FakeResp(200, payload))
    r = _admin_post(client, fake, {"action": "conn_list"}, cur=cur)
    assert r.status_code == 200
    conns = {c["conn_id"]: c for c in r.json()["connections"]}
    assert set(conns) == {"MSSQL_A", "MSSQL_LEGADA"}
    assert conns["MSSQL_A"]["origem"] == "orquestra"
    assert conns["MSSQL_LEGADA"]["origem"] == "airflow"
    assert conns["MSSQL_LEGADA"]["extra_charset"] == "CP850"


def test_conn_list_airflow_fora_nao_derruba_a_listagem(client, auth_admin):
    cur = _mock_cursor()
    cur.fetchall.return_value = [
        ("MSSQL_A", "srv-a", None, "sa", None, None, "orquestra"),
    ]
    fake = _FakeAirflowClient(lambda m, u, kw: _FakeResp(500))
    r = _admin_post(client, fake, {"action": "conn_list"}, cur=cur)
    assert r.status_code == 200
    assert [c["conn_id"] for c in r.json()["connections"]] == ["MSSQL_A"]


def test_conn_list_tabela_ausente_degrada_para_airflow(client, auth_admin):
    cur = _mock_cursor()
    cur.execute.side_effect = Exception("Invalid object name 'dbo.etl_conexao'")
    payload = {"connections": [
        {"connection_id": "MSSQL_X", "conn_type": "mssql", "host": "srv-x",
         "extra": ""}]}
    fake = _FakeAirflowClient(lambda m, u, kw: _FakeResp(200, payload))
    r = _admin_post(client, fake, {"action": "conn_list"}, cur=cur)
    assert r.status_code == 200
    conns = r.json()["connections"]
    assert [c["conn_id"] for c in conns] == ["MSSQL_X"]
    assert conns[0]["origem"] == "airflow"


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


# ── conn_upsert — criação (INSERT em dbo.etl_conexao) ────────────────────────

def test_conn_upsert_cria_com_senha_cifrada(client, auth_admin):
    cur = _mock_cursor()  # fetchone → None = não existe → INSERT
    r = _admin_post(client, _FakeAirflowClient(), {
        "action": "conn_upsert", "conn_id": "NOVA_CONN", "host": "srv1",
        "login": "sa", "password": "s3nh@!", "description": "Origem BI",
        "charset": "CP1252"}, cur=cur)
    assert r.status_code == 200
    assert r.json()["sucesso"] is True and r.json()["criada"] is True
    assert "s3nh@!" not in r.text  # resposta nunca ecoa a senha
    inserts = [c for c in cur.execute.call_args_list
               if "INSERT INTO dbo.etl_conexao" in str(c.args[0])]
    assert len(inserts) == 1
    params = inserts[0].args[1]
    conn_id, host, port, login, senha_enc, desc, extra, criado_por = params
    assert (conn_id, host, port, login) == ("NOVA_CONN", "srv1", 1433, "sa")
    assert desc == "Origem BI" and criado_por == "ADMIN1"
    assert json.loads(extra) == {"charset": "CP1252"}
    assert senha_enc != "s3nh@!"                       # nunca texto puro
    assert decrypt_password(senha_enc) == "s3nh@!"     # e decifra com a chave


def test_conn_upsert_criacao_exige_login_e_password(client, auth_admin):
    r = _admin_post(client, _FakeAirflowClient(), {
        "action": "conn_upsert", "conn_id": "NOVA", "host": "srv1", "login": "sa"})
    assert r.status_code == 422
    assert "password" in r.json()["detail"]
    r = _admin_post(client, _FakeAirflowClient(), {
        "action": "conn_upsert", "conn_id": "NOVA", "host": "srv1", "password": "x"})
    assert r.status_code == 422
    assert "login" in r.json()["detail"]


def test_conn_upsert_criacao_sem_charset_extra_null(client, auth_admin):
    cur = _mock_cursor()
    r = _admin_post(client, _FakeAirflowClient(), {
        "action": "conn_upsert", "conn_id": "NOVA", "host": "srv1",
        "login": "sa", "password": "x"}, cur=cur)
    assert r.status_code == 200
    params = [c for c in cur.execute.call_args_list
              if "INSERT INTO dbo.etl_conexao" in str(c.args[0])][0].args[1]
    assert params[2] == 1433   # port default
    assert params[6] is None   # extra_json


# ── conn_upsert — atualização (UPDATE só com o que veio) ─────────────────────

_EXTRA_ATUAL = json.dumps({"charset": "CP850", "chave_livre": "fica"})


def _cur_existente():
    cur = _mock_cursor()
    cur.fetchone.return_value = (_EXTRA_ATUAL,)
    return cur


def _update_call(cur):
    ups = [c for c in cur.execute.call_args_list
           if "UPDATE dbo.etl_conexao" in str(c.args[0])]
    assert len(ups) == 1
    return str(ups[0].args[0]), list(ups[0].args[1])


def test_conn_upsert_atualiza_so_o_que_veio(client, auth_admin):
    cur = _cur_existente()
    r = _admin_post(client, _FakeAirflowClient(), {
        "action": "conn_upsert", "conn_id": "CONN_X", "host": "srv-novo",
        "port": 1450, "login": "sa_novo", "description": "nova",
        "charset": "UTF-8"}, cur=cur)   # SEM password → mantém a atual
    assert r.status_code == 200
    assert r.json()["criada"] is False
    sql, params = _update_call(cur)
    assert "senha_enc" not in sql       # senha ausente = intocada
    assert "host = ?" in sql and "port = ?" in sql
    assert "login = ?" in sql and "descricao = ?" in sql
    assert "extra_json = ?" in sql
    # merge do extra: charset trocado E chave alheia preservada
    extra_novo = [p for p in params if isinstance(p, str) and "chave_livre" in p][0]
    assert json.loads(extra_novo) == {"charset": "UTF-8", "chave_livre": "fica"}


def test_conn_upsert_com_password_recifra(client, auth_admin):
    cur = _cur_existente()
    r = _admin_post(client, _FakeAirflowClient(), {
        "action": "conn_upsert", "conn_id": "CONN_X", "host": "srv-old",
        "login": "sa_old", "password": "NovaSenha1"}, cur=cur)
    assert r.status_code == 200
    assert "NovaSenha1" not in r.text
    sql, params = _update_call(cur)
    assert "senha_enc = ?" in sql
    assert "port = ?" not in sql and "descricao" not in sql
    token = [p for p in params
             if isinstance(p, str) and p.startswith("gAAAA")][0]
    assert decrypt_password(token) == "NovaSenha1"


def test_conn_upsert_charset_igual_nao_toca_extra(client, auth_admin):
    cur = _cur_existente()
    r = _admin_post(client, _FakeAirflowClient(), {
        "action": "conn_upsert", "conn_id": "CONN_X", "host": "srv-old",
        "login": "sa_old", "charset": "CP850"}, cur=cur)  # igual ao atual
    assert r.status_code == 200
    sql, _ = _update_call(cur)
    assert "extra_json" not in sql


def test_conn_upsert_charset_vazio_remove_a_chave_preservando_extra(client, auth_admin):
    cur = _cur_existente()
    r = _admin_post(client, _FakeAirflowClient(), {
        "action": "conn_upsert", "conn_id": "CONN_X", "host": "srv-old",
        "login": "sa_old", "charset": ""}, cur=cur)
    assert r.status_code == 200
    sql, params = _update_call(cur)
    assert "extra_json = ?" in sql
    extra_novo = [p for p in params if isinstance(p, str) and "chave_livre" in p][0]
    assert json.loads(extra_novo) == {"chave_livre": "fica"}


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


def test_conn_delete_remove_da_tabela_sem_tocar_airflow(client, auth_admin):
    cur = _mock_cursor()
    cur.fetchall.side_effect = [[], []]
    cur.rowcount = 1
    fake = _FakeAirflowClient()
    r = _admin_post(client, fake, {"action": "conn_delete", "conn_id": "CONN_X"},
                    cur=cur)
    assert r.status_code == 200
    assert "Orquestra" in r.json()["mensagem"]
    assert fake.calls == []


def test_conn_delete_legada_cai_no_airflow(client, auth_admin):
    cur = _mock_cursor()
    cur.fetchall.side_effect = [[], []]
    cur.rowcount = 0   # não estava em dbo.etl_conexao
    fake = _FakeAirflowClient(lambda m, u, kw: _FakeResp(204))
    r = _admin_post(client, fake, {"action": "conn_delete", "conn_id": "CONN_X"},
                    cur=cur)
    assert r.status_code == 200
    assert fake.calls == [("DELETE", "/api/v1/connections/CONN_X", {})]


def test_conn_delete_404_inexistente_em_ambos(client, auth_admin):
    cur = _mock_cursor()
    cur.fetchall.side_effect = [[], []]
    cur.rowcount = 0
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


# ── conn_test — modo (b): conexão salva ──────────────────────────────────────

def test_conn_test_salva_no_orquestra_testa_com_credencial_real(client, auth_admin):
    cur = _mock_cursor()
    cur.fetchone.return_value = ("srv1", 1450, "sa", encrypt_password("Secr3ta"))
    with patch("routers.admin.pyodbc") as fake_pyodbc, \
         patch("routers.admin.get_db_conn", return_value=_mock_conn(cur)):
        fake_pyodbc.drivers.return_value = ["ODBC Driver 18 for SQL Server"]
        cx = MagicMock()
        c2 = cx.cursor.return_value
        c2.fetchone.return_value = (4,)
        fake_pyodbc.connect.return_value = cx
        r = client.post("/admin", json={"action": "conn_test",
                                        "conn_id": "CONN_X"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True and body["via"] == "orquestra"
    assert "4 banco(s)" in body["mensagem"]
    assert "Secr3ta" not in r.text
    conn_str = fake_pyodbc.connect.call_args.args[0]
    assert "SERVER=srv1,1450" in conn_str and "PWD={Secr3ta}" in conn_str


def test_conn_test_salva_falha_sem_ecoar_senha(client, auth_admin):
    cur = _mock_cursor()
    cur.fetchone.return_value = ("srv1", None, "sa", encrypt_password("Secr3ta"))
    with patch("routers.admin.pyodbc") as fake_pyodbc, \
         patch("routers.admin.get_db_conn", return_value=_mock_conn(cur)):
        fake_pyodbc.drivers.return_value = ["ODBC Driver 18 for SQL Server"]
        fake_pyodbc.connect.side_effect = Exception("Login failed (PWD=Secr3ta)")
        r = client.post("/admin", json={"action": "conn_test",
                                        "conn_id": "CONN_X"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False and body["via"] == "orquestra"
    assert "Secr3ta" not in r.text
    assert "••••" in body["mensagem"]


def test_conn_test_legada_cai_no_caminho_airflow(client, auth_admin):
    cur = _mock_cursor()   # fetchone → None = não está em dbo.etl_conexao
    with patch("routers.admin.get_db_conn", return_value=_mock_conn(cur)), \
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


def test_conn_test_legada_fallback_dag(client, auth_admin):
    cur = _mock_cursor()
    with patch("routers.admin.get_db_conn", return_value=_mock_conn(cur)), \
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


def test_conn_test_422_sem_senha_e_sem_conn_id(client, auth_admin):
    r = _admin_post(client, _FakeAirflowClient(), {"action": "conn_test"})
    assert r.status_code == 422


# ── conn_migrate — dispara a DAG etl_admin_manage e lê o resultado ───────────

def _handler_migrate(estado="success", xcom=None):
    resultado = xcom if xcom is not None else {
        "sucesso": True, "mensagem": "Migração concluída: 2 conexão(ões) migrada(s).",
        "detalhes": {"migradas": ["A", "B"], "ja_existiam": [], "sem_dados": []}}

    def _handler(method, url, kw):
        if method == "POST" and url.endswith("/dags/etl_admin_manage/dagRuns"):
            return _FakeResp(200, {})
        if "/xcomEntries/return_value" in url:
            return _FakeResp(200, {"value": json.dumps(resultado)})
        if "/dagRuns/conn_migrate_" in url:
            return _FakeResp(200, {"state": estado})
        return _FakeResp(404)
    return _handler


def test_conn_migrate_dispara_dag_e_devolve_resumo(client, auth_admin):
    fake = _FakeAirflowClient(_handler_migrate())
    with patch("routers.admin.asyncio.sleep", new=AsyncMock()):
        r = _admin_post(client, fake, {"action": "conn_migrate"})
    assert r.status_code == 200
    body = r.json()
    assert body["sucesso"] is True
    assert "2 conexão(ões)" in body["mensagem"]
    post = [c for c in fake.calls if c[0] == "POST"][0]
    assert post[2]["json"]["conf"] == {"action": "conn_migrate",
                                       "requested_by": "ADMIN1"}


def test_conn_migrate_dag_failed_502(client, auth_admin):
    fake = _FakeAirflowClient(_handler_migrate(estado="failed"))
    with patch("routers.admin.asyncio.sleep", new=AsyncMock()):
        r = _admin_post(client, fake, {"action": "conn_migrate"})
    assert r.status_code == 502
    assert "etl_admin_manage" in r.json()["detail"] \
        or "admin_manage" in r.json()["detail"]


def test_conn_migrate_airflow_recusa_502(client, auth_admin):
    fake = _FakeAirflowClient(lambda m, u, kw: _FakeResp(409))
    with patch("routers.admin.asyncio.sleep", new=AsyncMock()):
        r = _admin_post(client, fake, {"action": "conn_migrate"})
    assert r.status_code == 502
