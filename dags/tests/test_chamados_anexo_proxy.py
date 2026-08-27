"""tests/test_chamados_anexo_proxy.py — testa proxy de anexos ServiceNow.

Verifica Content-Type, Content-Disposition e 404 para anexo não encontrado.

Run:
    docker exec orquestra-api python -m pytest /opt/airflow/dags/tests/test_chamados_anexo_proxy.py -v
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

def _make_conn_para_proxy(mime, nome_arquivo):
    """Cursor que retorna o anexo + cfg do banco via fetchone + fetchall."""
    conn = MagicMock()
    cur = MagicMock()
    cur.fetchone.return_value = (
        "https://sn.empresa.com/api/now/attachment/ANX001/file",
        nome_arquivo,
        mime,
    )
    cur.fetchall.return_value = [
        ("servicenow_usuario", "svc_user"),
        ("servicenow_senha_enc", "enc_token"),
    ]
    conn.cursor.return_value = cur
    return conn


def _make_sn_response(content, content_type):
    sn_resp = MagicMock()
    sn_resp.content = content
    sn_resp.headers = {"content-type": content_type}
    sn_resp.raise_for_status = MagicMock()
    return sn_resp


class TestAnexoProxy:
    def test_imagem_sem_content_disposition(self):
        conn = _make_conn_para_proxy("image/png", "arquivo.png")
        sn_resp = _make_sn_response(b"\x89PNG\r\n", "image/png")

        with patch(_DB_PATCH, return_value=conn), \
             patch("routers.chamados._httpx.Client") as mock_cli:
            mock_cli.return_value.__enter__.return_value.get.return_value = sn_resp
            resp = client.get("/chamados/SYS001/anexos/ANX001",
                              headers={"Authorization": "Bearer test"})

        assert resp.status_code == 200
        assert "content-disposition" not in resp.headers

    def test_nao_imagem_tem_content_disposition(self):
        conn = _make_conn_para_proxy("text/plain", "log.txt")
        sn_resp = _make_sn_response(b"linha de log", "text/plain")

        with patch(_DB_PATCH, return_value=conn), \
             patch("routers.chamados._httpx.Client") as mock_cli:
            mock_cli.return_value.__enter__.return_value.get.return_value = sn_resp
            resp = client.get("/chamados/SYS001/anexos/ANX001",
                              headers={"Authorization": "Bearer test"})

        assert resp.status_code == 200
        cd = resp.headers.get("content-disposition", "")
        assert "attachment" in cd
        assert "log.txt" in cd

    def test_404_para_anexo_inexistente(self):
        conn = MagicMock()
        cur = MagicMock()
        cur.fetchone.return_value = None
        conn.cursor.return_value = cur

        with patch(_DB_PATCH, return_value=conn):
            resp = client.get("/chamados/SYS001/anexos/INEXISTENTE",
                              headers={"Authorization": "Bearer test"})

        assert resp.status_code == 404

    def test_pdf_tem_content_disposition(self):
        conn = _make_conn_para_proxy("application/pdf", "relatorio.pdf")
        sn_resp = _make_sn_response(b"%PDF-1.4", "application/pdf")

        with patch(_DB_PATCH, return_value=conn), \
             patch("routers.chamados._httpx.Client") as mock_cli:
            mock_cli.return_value.__enter__.return_value.get.return_value = sn_resp
            resp = client.get("/chamados/SYS001/anexos/ANX002",
                              headers={"Authorization": "Bearer test"})

        assert resp.status_code == 200
        assert "attachment" in resp.headers.get("content-disposition", "")
