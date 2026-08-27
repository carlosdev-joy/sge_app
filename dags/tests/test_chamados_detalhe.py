"""tests/test_chamados_detalhe.py — testa GET /chamados/{sys_id}/detalhe.

Padrão idêntico ao test_chamados_api.py:
  - stub db/deps antes de qualquer import de routers
  - _auth_override sem parâmetros (evita que FastAPI trate *a/**kw como query params)
  - patch via _DB_PATCH = "routers.chamados.get_db_conn"

Run:
    docker exec orquestra-api python -m pytest /opt/airflow/dags/tests/test_chamados_detalhe.py -v
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

# Stub conn_crypto para evitar dependência de Fernet real
_services_mod = types.ModuleType("services")
_crypto_mod = types.ModuleType("services.conn_crypto")
_crypto_mod.decrypt_password = lambda t: "senha_decriptada"
sys.modules["services"] = _services_mod
sys.modules["services.conn_crypto"] = _crypto_mod

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from routers.chamados import router  # noqa: E402
from deps import get_current_user  # noqa: E402 — já stubado acima

app = FastAPI()
app.dependency_overrides[get_current_user] = _auth_override
app.include_router(router)

client = TestClient(app, raise_server_exceptions=False)

_DB_PATCH = "routers.chamados.get_db_conn"

# ── Fixtures de dados ─────────────────────────────────────────────────────────

_CHAMADO_ROW = (
    "SYS001", "INC0012345", "incident", "Erro ETL", "Falha no job",
    "andamento", "João Silva", "joao@empresa.com", "Eng. Dados",
    "2026-08-15 10:00:00", "https://inst.sn.com/INC0012345", 1, 0, None,
)
_NOTA_ROW = (
    "NOTA001", "João Silva", "joao@empresa.com",
    "2026-08-20 10:32:15", "Verificado o job.", "work_notes",
)
_ANEXO_ROW = (
    "ANX001", "screenshot.png", "image/png", 420000,
    "2026-08-19 14:05:00",
)


def _make_conn(fetchone_val, fetchall_side_effect):
    conn = MagicMock()
    cur = MagicMock()
    cur.fetchone.return_value = fetchone_val
    cur.fetchall.side_effect = fetchall_side_effect
    conn.cursor.return_value = cur
    return conn


class TestChamadoDetalhe:
    def test_retorna_chamado_com_notas_e_anexos(self):
        conn = _make_conn(_CHAMADO_ROW, [[_NOTA_ROW], [_ANEXO_ROW]])
        with patch(_DB_PATCH, return_value=conn):
            resp = client.get("/chamados/SYS001/detalhe",
                              headers={"Authorization": "Bearer test"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["chamado"]["numero"] == "INC0012345"
        assert body["chamado"]["tem_anexo"] is True
        assert len(body["notas"]) == 1
        assert body["notas"][0]["sys_id_nota"] == "NOTA001"
        assert len(body["anexos"]) == 1
        assert "url_proxy" in body["anexos"][0]
        assert "SYS001" in body["anexos"][0]["url_proxy"]

    def test_404_para_sys_id_inexistente(self):
        conn = _make_conn(None, [[], []])
        with patch(_DB_PATCH, return_value=conn):
            resp = client.get("/chamados/NAOEXI/detalhe",
                              headers={"Authorization": "Bearer test"})
        assert resp.status_code == 404

    def test_chamado_sem_notas_e_sem_anexos(self):
        conn = _make_conn(_CHAMADO_ROW, [[], []])
        with patch(_DB_PATCH, return_value=conn):
            resp = client.get("/chamados/SYS001/detalhe",
                              headers={"Authorization": "Bearer test"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["notas"] == []
        assert body["anexos"] == []

    def test_url_proxy_formato_correto(self):
        conn = _make_conn(_CHAMADO_ROW, [[], [_ANEXO_ROW]])
        with patch(_DB_PATCH, return_value=conn):
            resp = client.get("/chamados/SYS001/detalhe",
                              headers={"Authorization": "Bearer test"})
        body = resp.json()
        assert body["anexos"][0]["url_proxy"] == "/chamados/SYS001/anexos/ANX001"
