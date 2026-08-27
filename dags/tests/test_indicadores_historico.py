"""tests/test_indicadores_historico.py — testa GET /chamados/indicadores/historico.

Verifica estrutura da resposta, parâmetros de período e ausência de 500.

Run:
    docker exec orquestra-api python -m pytest /opt/airflow/dags/tests/test_indicadores_historico.py -v
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

# ── Fixtures ──────────────────────────────────────────────────────────────────

_SNAP_ROW = (
    "2026-08-23 10:00:00", 42.0, 5.0, 18.0, 12.0, 7.0, 0.0, 3.0,
    4.2, 18.5, 22.0, 19.0, 8.0,
)

_ANALISTA_ROW = ("João Silva", "joao@empresa.com", 10, 2, 3.5)
_GRUPO_ROW = ("Eng. Dados", 42, 3, 4.2)
_META_ROW = ("sla_vencidos", 5.0, None)


def _conn_historico(snap_rows=None, ultimo_id=99,
                    analista_rows=None, grupo_rows=None, meta_rows=None):
    conn = MagicMock()
    cur = MagicMock()
    cur.fetchall.side_effect = [
        snap_rows if snap_rows is not None else [_SNAP_ROW],
        analista_rows if analista_rows is not None else [],
        grupo_rows if grupo_rows is not None else [],
        meta_rows if meta_rows is not None else [],
    ]
    cur.fetchone.return_value = (ultimo_id,)
    conn.cursor.return_value = cur
    return conn


# ── Testes ────────────────────────────────────────────────────────────────────

class TestIndicadoresHistorico:
    def test_retorna_estrutura_esperada(self):
        conn = _conn_historico()
        with patch(_DB_PATCH, return_value=conn):
            resp = client.get("/chamados/indicadores/historico?periodo=30d",
                              headers={"Authorization": "Bearer test"})
        assert resp.status_code == 200
        body = resp.json()
        assert "snapshots" in body
        assert "por_analista" in body
        assert "por_grupo" in body
        assert "metas" in body

    def test_retorna_snapshots_com_dados(self):
        conn = _conn_historico()
        with patch(_DB_PATCH, return_value=conn):
            resp = client.get("/chamados/indicadores/historico",
                              headers={"Authorization": "Bearer test"})
        body = resp.json()
        assert len(body["snapshots"]) == 1
        snap = body["snapshots"][0]
        assert snap["total_ativos"] == 42.0
        assert snap["sla_vencidos"] == 3.0

    def test_periodo_hoje(self):
        conn = _conn_historico()
        with patch(_DB_PATCH, return_value=conn):
            resp = client.get("/chamados/indicadores/historico?periodo=hoje",
                              headers={"Authorization": "Bearer test"})
        assert resp.status_code == 200

    def test_periodo_historico_longo(self):
        conn = _conn_historico()
        with patch(_DB_PATCH, return_value=conn):
            resp = client.get("/chamados/indicadores/historico?periodo=historico",
                              headers={"Authorization": "Bearer test"})
        assert resp.status_code == 200

    def test_periodo_invalido_usa_30d_sem_500(self):
        """Período não reconhecido cai no branch 30d — não pode dar 500."""
        conn = _conn_historico()
        with patch(_DB_PATCH, return_value=conn):
            resp = client.get("/chamados/indicadores/historico?periodo=invalido",
                              headers={"Authorization": "Bearer test"})
        assert resp.status_code == 200

    def test_por_analista_retornado(self):
        conn = _conn_historico(analista_rows=[_ANALISTA_ROW])
        with patch(_DB_PATCH, return_value=conn):
            resp = client.get("/chamados/indicadores/historico",
                              headers={"Authorization": "Bearer test"})
        body = resp.json()
        assert len(body["por_analista"]) == 1
        assert body["por_analista"][0]["atribuido_a"] == "João Silva"

    def test_por_grupo_retornado(self):
        conn = _conn_historico(grupo_rows=[_GRUPO_ROW])
        with patch(_DB_PATCH, return_value=conn):
            resp = client.get("/chamados/indicadores/historico",
                              headers={"Authorization": "Bearer test"})
        body = resp.json()
        assert len(body["por_grupo"]) == 1
        assert body["por_grupo"][0]["grupo"] == "Eng. Dados"

    def test_metas_retornadas(self):
        conn = _conn_historico(meta_rows=[_META_ROW])
        with patch(_DB_PATCH, return_value=conn):
            resp = client.get("/chamados/indicadores/historico",
                              headers={"Authorization": "Bearer test"})
        body = resp.json()
        assert len(body["metas"]) == 1
        assert body["metas"][0]["metrica"] == "sla_vencidos"
        assert body["metas"][0]["valor_meta"] == 5.0

    def test_filtro_grupo_passado_como_param(self):
        """Parâmetro grupo deve ser aceito sem erro."""
        conn = _conn_historico()
        with patch(_DB_PATCH, return_value=conn):
            resp = client.get(
                "/chamados/indicadores/historico?grupo=Eng.+Dados",
                headers={"Authorization": "Bearer test"})
        assert resp.status_code == 200

    def test_sem_snapshots_retorna_listas_vazias(self):
        conn = MagicMock()
        cur = MagicMock()
        cur.fetchall.side_effect = [[], [], [], []]
        cur.fetchone.return_value = (None,)
        conn.cursor.return_value = cur
        with patch(_DB_PATCH, return_value=conn):
            resp = client.get("/chamados/indicadores/historico",
                              headers={"Authorization": "Bearer test"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["snapshots"] == []
        assert body["por_analista"] == []
        assert body["por_grupo"] == []
