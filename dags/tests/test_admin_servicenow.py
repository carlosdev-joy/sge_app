"""tests/test_admin_servicenow.py — testa endpoints admin/servicenow.

Cobre: config GET/PUT, testar POST, grupos GET/POST/PUT, ciclos GET,
disparar-delta POST, perfis-acesso GET/PUT.

Run:
    docker exec orquestra-api python -m pytest /opt/airflow/dags/tests/test_admin_servicenow.py -v
"""
import sys
import types
from unittest.mock import MagicMock, patch

sys.path.insert(0, "/app")

# ── Stubs de infraestrutura ───────────────────────────────────────────────────

_db_mod = types.ModuleType("db")
_db_mod.get_db_conn = MagicMock()
sys.modules["db"] = _db_mod

_FAKE_USER = {"matricula": "TEST", "perfil": "admin",
              "permissoes": ["tela_chamados", "acao_admin"]}

_deps_mod = types.ModuleType("deps")

async def _auth_override():
    return _FAKE_USER

_deps_mod.get_current_user = _auth_override
_deps_mod.get_admin_user = _auth_override
_deps_mod.PERM_ADMIN = "acao_admin"
sys.modules["deps"] = _deps_mod

_services_mod = types.ModuleType("services")
_crypto_mod = types.ModuleType("services.conn_crypto")
_crypto_mod.decrypt_password = lambda t: "senha_decriptada"
sys.modules["services"] = _services_mod
sys.modules["services.conn_crypto"] = _crypto_mod

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from routers.chamados import router  # noqa: E402
from deps import get_current_user  # noqa: E402

app = FastAPI()
app.dependency_overrides[get_current_user] = _auth_override
app.include_router(router)

client = TestClient(app, raise_server_exceptions=False)

_DB_PATCH = "routers.chamados.get_db_conn"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _conn_with_fetchall(rows):
    conn = MagicMock()
    cur = MagicMock()
    cur.fetchall.return_value = rows
    conn.cursor.return_value = cur
    return conn


def _conn_with_fetchone(row):
    conn = MagicMock()
    cur = MagicMock()
    cur.fetchone.return_value = row
    conn.cursor.return_value = cur
    return conn


# ── Config ────────────────────────────────────────────────────────────────────

class TestAdminConfig:
    def test_get_config_retorna_campos(self):
        conn = _conn_with_fetchall([
            ("servicenow_url", "https://sn.empresa.com"),
            ("servicenow_usuario", "svc_user"),
            ("servicenow_habilitado", "1"),
        ])
        with patch(_DB_PATCH, return_value=conn):
            resp = client.get("/admin/servicenow/config",
                              headers={"Authorization": "Bearer admin"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["url"] == "https://sn.empresa.com"
        assert body["usuario"] == "svc_user"
        assert body["habilitado"] is True

    def test_get_config_habilitado_falso_quando_zero(self):
        conn = _conn_with_fetchall([
            ("servicenow_habilitado", "0"),
        ])
        with patch(_DB_PATCH, return_value=conn):
            resp = client.get("/admin/servicenow/config",
                              headers={"Authorization": "Bearer admin"})
        assert resp.status_code == 200
        assert resp.json()["habilitado"] is False

    def test_put_config_retorna_ok(self):
        conn = MagicMock()
        cur = MagicMock()
        conn.cursor.return_value = cur
        with patch(_DB_PATCH, return_value=conn):
            resp = client.put(
                "/admin/servicenow/config",
                json={"servicenow_url": "https://sn.empresa.com",
                      "servicenow_habilitado": "1"},
                headers={"Authorization": "Bearer admin"})
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_put_config_ignora_campos_invalidos(self):
        conn = MagicMock()
        cur = MagicMock()
        conn.cursor.return_value = cur
        with patch(_DB_PATCH, return_value=conn):
            resp = client.put(
                "/admin/servicenow/config",
                json={"campo_invalido": "valor"},
                headers={"Authorization": "Bearer admin"})
        # campos inválidos são silenciosamente ignorados
        assert resp.status_code == 200


# ── Grupos ────────────────────────────────────────────────────────────────────

class TestAdminGrupos:
    def test_lista_grupos(self):
        conn = _conn_with_fetchall([
            (1, "Eng. Dados", 1, "2026-08-01 00:00:00"),
            (2, "Dados Cloud", 0, "2026-08-10 00:00:00"),
        ])
        with patch(_DB_PATCH, return_value=conn):
            resp = client.get("/admin/servicenow/grupos",
                              headers={"Authorization": "Bearer admin"})
        assert resp.status_code == 200
        grupos = resp.json()
        assert len(grupos) == 2
        assert grupos[0]["nome"] == "Eng. Dados"
        assert grupos[0]["ativo"] is True
        assert grupos[1]["ativo"] is False

    def test_criar_grupo_retorna_ok(self):
        conn = MagicMock()
        cur = MagicMock()
        conn.cursor.return_value = cur
        with patch(_DB_PATCH, return_value=conn):
            resp = client.post(
                "/admin/servicenow/grupos",
                json={"nome": "Novo Grupo"},
                headers={"Authorization": "Bearer admin"})
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_criar_grupo_sem_nome_retorna_422(self):
        with patch(_DB_PATCH, return_value=MagicMock()):
            resp = client.post(
                "/admin/servicenow/grupos",
                json={"nome": ""},
                headers={"Authorization": "Bearer admin"})
        assert resp.status_code == 422

    def test_editar_grupo_retorna_ok(self):
        conn = MagicMock()
        cur = MagicMock()
        conn.cursor.return_value = cur
        with patch(_DB_PATCH, return_value=conn):
            resp = client.put(
                "/admin/servicenow/grupos/1",
                json={"ativo": False},
                headers={"Authorization": "Bearer admin"})
        assert resp.status_code == 200
        assert resp.json()["ok"] is True


# ── Ciclos ────────────────────────────────────────────────────────────────────

class TestAdminCiclos:
    def test_lista_ciclos(self):
        conn = _conn_with_fetchall([
            (42, "delta", "2026-08-23 10:00:00", "2026-08-23 10:03:00",
             "OK", 18, 5, 2, 0, "etl_servicenow_delta", None),
            (41, "full", "2026-08-23 02:00:00", "2026-08-23 02:18:00",
             "OK", 320, 80, 15, 3, "etl_servicenow_full", None),
        ])
        with patch(_DB_PATCH, return_value=conn):
            resp = client.get("/admin/servicenow/ciclos",
                              headers={"Authorization": "Bearer admin"})
        assert resp.status_code == 200
        ciclos = resp.json()
        assert len(ciclos) == 2
        assert ciclos[0]["modo"] == "delta"
        assert ciclos[0]["status"] == "OK"
        assert ciclos[1]["modo"] == "full"


# ── Disparar delta ────────────────────────────────────────────────────────────

class TestAdminDispararDelta:
    def test_dispara_delta_com_sucesso(self):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"dag_run_id": "manual_20260823"}

        with patch("routers.chamados._httpx.Client") as mock_cli:
            mock_cli.return_value.__enter__.return_value.post.return_value = mock_resp
            resp = client.post(
                "/admin/servicenow/disparar-delta",
                headers={"Authorization": "Bearer admin"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["dag_run_id"] == "manual_20260823"

    def test_dispara_delta_502_quando_airflow_falha(self):
        with patch("routers.chamados._httpx.Client") as mock_cli:
            mock_cli.return_value.__enter__.return_value.post.side_effect = (
                Exception("Connection refused"))
            resp = client.post(
                "/admin/servicenow/disparar-delta",
                headers={"Authorization": "Bearer admin"})
        assert resp.status_code == 502


# ── Perfis de acesso ──────────────────────────────────────────────────────────

class TestAdminPerfisAcesso:
    def test_get_perfis(self):
        conn = _conn_with_fetchone(("gestor,analista_senior",))
        with patch(_DB_PATCH, return_value=conn):
            resp = client.get("/admin/servicenow/perfis-acesso",
                              headers={"Authorization": "Bearer admin"})
        assert resp.status_code == 200
        body = resp.json()
        assert "gestor" in body["perfis"]
        assert "analista_senior" in body["perfis"]

    def test_get_perfis_vazio_quando_nao_configurado(self):
        conn = _conn_with_fetchone(None)
        with patch(_DB_PATCH, return_value=conn):
            resp = client.get("/admin/servicenow/perfis-acesso",
                              headers={"Authorization": "Bearer admin"})
        assert resp.status_code == 200
        assert resp.json()["perfis"] == []

    def test_put_perfis_retorna_ok(self):
        conn = MagicMock()
        cur = MagicMock()
        conn.cursor.return_value = cur
        with patch(_DB_PATCH, return_value=conn):
            resp = client.put(
                "/admin/servicenow/perfis-acesso",
                json={"perfis": ["gestor", "analista"]},
                headers={"Authorization": "Bearer admin"})
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
