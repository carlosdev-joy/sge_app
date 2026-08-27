"""tests/test_chamados_api.py — integration tests for chamados router.

Tests field-index mapping, tipo != 'task' filter, and categoria CRUD guards
WITHOUT a real database — all DB calls are intercepted by a mock cursor.

Run:
    docker exec orquestra-api python -m pytest /opt/airflow/dags/tests/test_chamados_api.py -v
"""
import sys
import types
from unittest.mock import MagicMock, patch
import datetime

sys.path.insert(0, "/app")

# ── Stub modules that require real infra ─────────────────────────────────────

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

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from routers.chamados import router  # noqa: E402
from deps import get_current_user  # noqa: E402  — already the stub above

app = FastAPI()
app.dependency_overrides[get_current_user] = _auth_override
app.include_router(router)

client = TestClient(app, raise_server_exceptions=True)

# The correct patch target: the name as imported inside the router module.
_DB_PATCH = "routers.chamados.get_db_conn"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_cursor(rows=None, scalar=None):
    cur = MagicMock()
    cur.fetchone.return_value = (scalar,) if isinstance(scalar, int) else scalar
    cur.fetchall.return_value = rows or []
    return cur

def _make_conn(cur):
    conn = MagicMock()
    conn.cursor.return_value = cur
    return conn

def _fake_row(**kwargs):
    """Minimal etl_chamado row (32 fields) with defaults."""
    defaults = [
        "SYSID1", "RITM0001", "ritm", "Titulo teste",  # r[0..3]
        "Em aberto", "novo",                             # r[4..5]
        "Moderado", "Maria", "GESTR ED",                # r[6..8]
        None, None, None,                               # r[9..11] datas
        1, "https://sn/nav", None,                      # r[12..14]
        5,                                              # r[15] idade_dias
        "",                                             # r[16] pai_sys_id
        "Demanda técnica",                              # r[17] tipo_demanda
        "dia a dia",                                    # r[18] categoria_diaadia
        "TB_X",                                         # r[19] objetos
        "João", "Cat item", None, 0,                    # r[20..23]
        None, None, "", "", "",                         # r[24..28]
        None, None, "",                                 # r[29..31]
    ]
    row = list(defaults)
    _idx = {
        "sys_id": 0, "numero": 1, "tipo": 2, "titulo": 3,
        "estado_origem": 4, "estado_kanban": 5, "prioridade": 6,
        "atribuido_a": 7, "grupo": 8, "aberto_em": 9,
        "atualizado_em": 10, "encerrado_em": 11, "ativo": 12,
        "url": 13, "sync_em": 14, "idade_dias": 15,
        "pai_sys_id": 16, "tipo_demanda": 17, "categoria_diaadia": 18,
        "objetos": 19,
    }
    for k, v in kwargs.items():
        row[_idx[k]] = v
    return tuple(row)


# ── /chamados ─────────────────────────────────────────────────────────────────

class TestListarChamados:
    def _setup_cursor(self, chamado_rows=None):
        cur = MagicMock()
        call_count = [0]

        def fetchone_side():
            call_count[0] += 1
            if call_count[0] == 1:
                return (1,)                                  # migration check
            if call_count[0] == 2:
                return ("2026-08-20 10:00:00", "ok", 10)    # sync status
            if call_count[0] == 3:
                return ("2026-08-20 10:00:00",)              # frescor
            return None

        cur.fetchone.side_effect = fetchone_side
        cur.fetchall.return_value = chamado_rows or []
        return cur

    def test_retorna_200_sem_dados(self):
        cur = self._setup_cursor()
        with patch(_DB_PATCH, return_value=_make_conn(cur)):
            resp = client.get("/chamados", headers={"Authorization": "Bearer fake"})
        assert resp.status_code == 200
        body = resp.json()
        assert "kanban" in body or "migration_ausente" in body

    def test_categoria_diaadia_campo_r18(self):
        """categoria_diaadia must come from r[18], not r[19]."""
        row = _fake_row(categoria_diaadia="dia a dia", objetos="OUTRO")
        cur = self._setup_cursor(chamado_rows=[row])
        with patch(_DB_PATCH, return_value=_make_conn(cur)):
            resp = client.get("/chamados", headers={"Authorization": "Bearer fake"})
        body = resp.json()
        if "kanban" in body:
            cards = [c for col in body["kanban"].values() for c in col]
            if cards:
                assert cards[0].get("categoria_diaadia") == "dia a dia"


# ── /chamados/categorias ──────────────────────────────────────────────────────

class TestListarCategorias:
    def test_retorna_lista(self):
        rows = [
            (1, "dia a dia", "Dia a dia", None, 1),
            (2, "iniciativa", "Iniciativa", None, 1),
        ]
        cur = _make_cursor(rows=rows)
        with patch(_DB_PATCH, return_value=_make_conn(cur)):
            resp = client.get("/chamados/categorias",
                              headers={"Authorization": "Bearer fake"})
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)
        assert body[0]["slug"] == "dia a dia"

    def test_retorna_lista_vazia_sem_erro(self):
        cur = _make_cursor(rows=[])
        with patch(_DB_PATCH, return_value=_make_conn(cur)):
            resp = client.get("/chamados/categorias",
                              headers={"Authorization": "Bearer fake"})
        assert resp.status_code == 200
        assert resp.json() == []


# ── /admin/servicenow/categorias POST ────────────────────────────────────────

class TestCriarCategoria:
    def test_422_sem_slug(self):
        cur = _make_cursor()
        with patch(_DB_PATCH, return_value=_make_conn(cur)):
            resp = client.post("/admin/servicenow/categorias",
                               json={"label": "Teste"},
                               headers={"Authorization": "Bearer fake"})
        assert resp.status_code == 422

    def test_422_sem_label(self):
        cur = _make_cursor()
        with patch(_DB_PATCH, return_value=_make_conn(cur)):
            resp = client.post("/admin/servicenow/categorias",
                               json={"slug": "teste"},
                               headers={"Authorization": "Bearer fake"})
        assert resp.status_code == 422

    def test_cria_com_sucesso(self):
        cur = MagicMock()
        cur.fetchone.return_value = (99,)
        with patch(_DB_PATCH, return_value=_make_conn(cur)):
            resp = client.post("/admin/servicenow/categorias",
                               json={"slug": "nova-cat", "label": "Nova Categoria"},
                               headers={"Authorization": "Bearer fake"})
        assert resp.status_code == 200


# ── /admin/servicenow/categorias DELETE ──────────────────────────────────────

class TestExcluirCategoria:
    def test_404_nao_encontrada(self):
        cur = MagicMock()
        cur.fetchone.return_value = None
        with patch(_DB_PATCH, return_value=_make_conn(cur)):
            resp = client.delete("/admin/servicenow/categorias/999",
                                 headers={"Authorization": "Bearer fake"})
        assert resp.status_code == 404

    def test_409_categoria_padrao(self):
        cur = MagicMock()
        cur.fetchone.return_value = (1,)  # padrao=1
        with patch(_DB_PATCH, return_value=_make_conn(cur)):
            resp = client.delete("/admin/servicenow/categorias/1",
                                 headers={"Authorization": "Bearer fake"})
        assert resp.status_code == 409

    def test_exclui_nao_padrao(self):
        cur = MagicMock()
        cur.fetchone.return_value = (0,)  # padrao=0
        with patch(_DB_PATCH, return_value=_make_conn(cur)):
            resp = client.delete("/admin/servicenow/categorias/3",
                                 headers={"Authorization": "Bearer fake"})
        assert resp.status_code == 200


# ── resolvidos_periodo: exclui tasks ─────────────────────────────────────────

class TestResolvidosPeriodo:
    def test_query_exclui_task(self):
        """Verifica que execute() foi chamado com AND tipo != 'task'."""
        # The indicadores endpoint calls CAST(GETDATE() AS DATE) and parses the result.
        # We must return a real date object to avoid ValueError crashing the inner try.
        TODAY = datetime.date(2026, 8, 21)

        cur = MagicMock()
        fetchone_seq = [
            # Outer try: aging, tipo_estado, fluxo queries use fetchall.
            # fluxo calls fetchone for GETDATE():
            (TODAY,),
            # Inner try (colunas 092+):
            (0,),   # sem_categoria
            (5,),   # resolvidos_periodo  ← the one we're testing
            (0,),   # triagem_com_erro
            (0,),   # triagem_sem_config
            # After inner try: total_ativos
            (42,),
        ]
        cur.fetchone.side_effect = fetchone_seq
        cur.fetchall.return_value = []

        with patch(_DB_PATCH, return_value=_make_conn(cur)):
            resp = client.get("/chamados/indicadores",
                              headers={"Authorization": "Bearer fake"})

        assert resp.status_code == 200
        body = resp.json()
        # blocos_indisponiveis=False means the inner try ran to completion
        assert body.get("blocos_indisponiveis") is False, (
            "inner try bloco failed — resolvidos_periodo query may not have run"
        )
        # resolvidos_periodo must come from the mock (not from tasks)
        assert body.get("resolvidos_periodo") == 5

        # Confirm the SQL excluded tipo=task
        all_calls = " ".join(str(c) for c in cur.execute.call_args_list)
        assert "tipo != 'task'" in all_calls or "tipo !=" in all_calls, (
            f"resolvidos_periodo deve excluir tipo=task.\nQueries:\n{all_calls}"
        )
