"""
Testes do Inventário de Consumidores (api/routers/inventario.py).

Padrão de test_copias.py / test_admin_conexoes.py: TestClient do conftest,
get_db_conn mockado em routers.inventario e autenticação sobrescrita via
dependency_overrides — nenhum teste toca rede ou banco.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# Replica o mock de pyodbc do conftest (garante o import de api.main mesmo se
# este arquivo for coletado antes do conftest configurar o ambiente).
if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()
os.environ.setdefault("MSSQL_CONN_STR", "__mock__")
from api.main import app as _app  # noqa: F401  (ordem de import — ver test_copias.py)

from deps import get_current_user
from routers.inventario import PERM_INVENTARIO


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


@pytest.fixture
def auth_dev(app):
    """Usuário com o recurso tela_inventario (perfil desenvolvedor/admin)."""
    app.dependency_overrides[get_current_user] = lambda: {
        "matricula": "DEV1", "perfil": "desenvolvedor",
        "permissoes": [PERM_INVENTARIO],
    }
    yield
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def auth_consulta(app):
    """Usuário autenticado SEM o recurso tela_inventario (só leitura)."""
    app.dependency_overrides[get_current_user] = lambda: {
        "matricula": "USER1", "perfil": "consulta", "permissoes": [],
    }
    yield
    app.dependency_overrides.pop(get_current_user, None)


# ── registro do router ───────────────────────────────────────────────────────

def test_router_inventario_registrado(client):
    """Endpoints de /inventario devem aparecer no schema OpenAPI."""
    r = client.get("/openapi.json")
    assert r.status_code == 200
    paths = r.json().get("paths", {})
    for p in ("/inventario/endpoints", "/inventario/endpoints/{eid}",
              "/inventario/endpoints/{eid}/objetos", "/inventario/objetos/{oid}"):
        assert p in paths, f"rota {p} não registrada em api/main.py"


# ── auth 401/403 ─────────────────────────────────────────────────────────────

def test_inventario_sem_auth_401(client):
    assert client.get("/inventario/endpoints").status_code == 401
    assert client.post("/inventario/endpoints", json={}).status_code == 401
    assert client.delete("/inventario/endpoints/1").status_code == 401
    assert client.post("/inventario/endpoints/1/objetos", json={}).status_code == 401
    assert client.patch("/inventario/objetos/1", json={}).status_code == 401
    assert client.delete("/inventario/objetos/1").status_code == 401


def test_escrita_exige_tela_inventario_403(client, auth_consulta):
    """Perfil sem o recurso tela_inventario lê, mas não escreve."""
    assert client.post("/inventario/endpoints",
                       json={"endpoint": "X"}).status_code == 403
    assert client.delete("/inventario/endpoints/1").status_code == 403
    assert client.post("/inventario/endpoints/1/objetos",
                       json={"objeto": "VW_X"}).status_code == 403
    assert client.patch("/inventario/objetos/1",
                        json={"status_validacao": "validado"}).status_code == 403
    assert client.delete("/inventario/objetos/1").status_code == 403


def test_leitura_nao_exige_tela_inventario(client, auth_consulta):
    with patch("routers.inventario.get_db_conn",
               return_value=_mock_conn(_mock_cursor())):
        r = client.get("/inventario/endpoints")
    assert r.status_code == 200
    assert r.json() == {"data": []}


# ── GET /inventario/endpoints ────────────────────────────────────────────────

def test_listar_degrada_sem_tabela(client, auth_dev):
    """Tabelas da migration 055 ausentes → data [] (nunca 500)."""
    with patch("routers.inventario.get_db_conn",
               side_effect=Exception("Invalid object name 'dbo.etl_inventario_endpoint'")):
        r = client.get("/inventario/endpoints")
    assert r.status_code == 200
    assert r.json() == {"data": []}


def _endpoint_row(eid=1, endpoint="GBE_ConsultaContratos", plataforma="GI",
                  consumidor="Salesforce", banco="BUCC"):
    return (eid, endpoint, plataforma, consumidor, banco,
            "descrição", "Carlos", "SEED", "2026-07-02 10:00:00", None, None)


def test_listar_agrega_objetos_por_endpoint(client, auth_dev):
    cur = _mock_cursor()
    cur.fetchall.side_effect = [
        # 1º SELECT: endpoints ativos
        [_endpoint_row(1, "EP_A"), _endpoint_row(2, "EP_B")],
        # 2º SELECT: objetos dos endpoints (id, endpoint_id, objeto, tipo, status, obs)
        [(10, 1, "VW_X", "view", "pendente", None),
         (11, 1, "PROC_Y", "proc", "validado", "ok"),
         (12, 2, "VW_Z", "view", "com_erro", "recompilar")],
    ]
    with patch("routers.inventario.get_db_conn", return_value=_mock_conn(cur)):
        r = client.get("/inventario/endpoints")
    assert r.status_code == 200
    data = r.json()["data"]
    assert [e["endpoint"] for e in data] == ["EP_A", "EP_B"]
    assert [o["objeto"] for o in data[0]["objetos"]] == ["VW_X", "PROC_Y"]
    assert data[0]["objetos"][1]["status_validacao"] == "validado"
    assert data[1]["objetos"] == [{"id": 12, "objeto": "VW_Z", "tipo": "view",
                                   "status_validacao": "com_erro",
                                   "observacao": "recompilar"}]


def test_listar_endpoint_sem_objetos_vem_com_lista_vazia(client, auth_dev):
    cur = _mock_cursor()
    cur.fetchall.side_effect = [[_endpoint_row(5, "EP_VAZIO")], []]
    with patch("routers.inventario.get_db_conn", return_value=_mock_conn(cur)):
        r = client.get("/inventario/endpoints")
    assert r.status_code == 200
    assert r.json()["data"][0]["objetos"] == []


def test_listar_aplica_filtros_q_e_banco(client, auth_dev):
    cur = _mock_cursor()
    cur.fetchall.side_effect = [[], []]
    with patch("routers.inventario.get_db_conn", return_value=_mock_conn(cur)):
        r = client.get("/inventario/endpoints?q=VW_CLIENTES&banco=BUCC")
    assert r.status_code == 200
    sql, params = cur.execute.call_args_list[0].args
    assert "LIKE ?" in sql and "e.banco = ?" in sql
    assert "etl_inventario_objeto" in sql          # q busca também nos objetos
    assert params == ["%VW_CLIENTES%", "%VW_CLIENTES%", "%VW_CLIENTES%", "BUCC"]


# ── POST /inventario/endpoints ───────────────────────────────────────────────

def test_criar_endpoint_grava_criado_por(client, auth_dev):
    cur = _mock_cursor()
    cur.fetchone.side_effect = [None, (42,)]  # nome livre → INSERT OUTPUT id
    with patch("routers.inventario.get_db_conn", return_value=_mock_conn(cur)):
        r = client.post("/inventario/endpoints", json={
            "endpoint": "GBE_Novo", "plataforma": "GI",
            "consumidor": "Salesforce", "banco": "BUCC"})
    assert r.status_code == 200
    assert r.json() == {"ok": True, "id": 42, "criado": True}
    inserts = [c for c in cur.execute.call_args_list
               if c.args and "INSERT INTO dbo.etl_inventario_endpoint" in str(c.args[0])]
    assert len(inserts) == 1
    assert "DEV1" in inserts[0].args[1], "criado_por deve ser a matrícula autenticada"


def test_criar_endpoint_422_sem_nome(client, auth_dev):
    r = client.post("/inventario/endpoints", json={"endpoint": "  "})
    assert r.status_code == 422
    assert "endpoint" in r.json()["detail"]


def test_criar_endpoint_422_nome_duplicado_entre_ativos(client, auth_dev):
    cur = _mock_cursor()
    cur.fetchone.side_effect = [(7,)]  # já existe endpoint ATIVO com o nome
    with patch("routers.inventario.get_db_conn", return_value=_mock_conn(cur)):
        r = client.post("/inventario/endpoints", json={"endpoint": "GBE_Dup"})
    assert r.status_code == 422
    # a checagem de unicidade considera apenas ativos (índice filtrado da 055)
    sel = str(cur.execute.call_args_list[0].args[0])
    assert "ativo = 1" in sel


def test_atualizar_endpoint_grava_atualizado_por(client, auth_dev):
    cur = _mock_cursor()
    cur.fetchone.side_effect = [None, (3,)]  # nome livre → endpoint existe
    with patch("routers.inventario.get_db_conn", return_value=_mock_conn(cur)):
        r = client.post("/inventario/endpoints", json={
            "id": 3, "endpoint": "GBE_Editado", "responsavel": "Jordan"})
    assert r.status_code == 200
    assert r.json() == {"ok": True, "id": 3, "criado": False}
    updates = [c for c in cur.execute.call_args_list
               if c.args and "UPDATE dbo.etl_inventario_endpoint" in str(c.args[0])]
    assert len(updates) == 1
    assert "atualizado_por" in str(updates[0].args[0])
    assert "DEV1" in updates[0].args[1]


def test_atualizar_endpoint_404_inexistente(client, auth_dev):
    cur = _mock_cursor()
    cur.fetchone.side_effect = [None, None]  # nome livre → id não encontrado
    with patch("routers.inventario.get_db_conn", return_value=_mock_conn(cur)):
        r = client.post("/inventario/endpoints",
                        json={"id": 999, "endpoint": "GBE_Sumiu"})
    assert r.status_code == 404


# ── DELETE /inventario/endpoints/{id} — soft delete ─────────────────────────

def test_excluir_endpoint_soft_delete(client, auth_dev):
    cur = _mock_cursor()
    cur.fetchone.side_effect = [(3,)]  # endpoint existe e está ativo
    with patch("routers.inventario.get_db_conn", return_value=_mock_conn(cur)):
        r = client.delete("/inventario/endpoints/3")
    assert r.status_code == 200
    assert r.json() == {"ok": True, "id": 3}
    updates = [str(c.args[0]) for c in cur.execute.call_args_list
               if c.args and "UPDATE" in str(c.args[0])]
    assert updates and "ativo = 0" in updates[0], "exclusão deve ser soft delete"
    deletes = [c for c in cur.execute.call_args_list
               if c.args and str(c.args[0]).strip().startswith("DELETE")]
    assert not deletes, "não pode haver DELETE físico do endpoint"


def test_excluir_endpoint_404_inexistente(client, auth_dev):
    cur = _mock_cursor()
    cur.fetchone.side_effect = [None]
    with patch("routers.inventario.get_db_conn", return_value=_mock_conn(cur)):
        r = client.delete("/inventario/endpoints/999")
    assert r.status_code == 404


# ── POST /inventario/endpoints/{id}/objetos ──────────────────────────────────

def test_adicionar_objeto_ok(client, auth_dev):
    cur = _mock_cursor()
    cur.fetchone.side_effect = [(1,), (55,)]  # endpoint existe → INSERT OUTPUT id
    with patch("routers.inventario.get_db_conn", return_value=_mock_conn(cur)):
        r = client.post("/inventario/endpoints/1/objetos",
                        json={"objeto": "VW_CLIENTES_EMAIL_TELEFONE_CVP",
                              "tipo": "view"})
    assert r.status_code == 200
    assert r.json() == {"ok": True, "id": 55}
    inserts = [c for c in cur.execute.call_args_list
               if c.args and "INSERT INTO dbo.etl_inventario_objeto" in str(c.args[0])]
    assert len(inserts) == 1
    assert "DEV1" in inserts[0].args[1]


def test_adicionar_objeto_422_validacoes(client, auth_dev):
    r = client.post("/inventario/endpoints/1/objetos", json={"objeto": ""})
    assert r.status_code == 422
    r = client.post("/inventario/endpoints/1/objetos",
                    json={"objeto": "VW_X", "tipo": "trigger"})
    assert r.status_code == 422
    assert "tipo" in r.json()["detail"]
    r = client.post("/inventario/endpoints/1/objetos",
                    json={"objeto": "VW_X", "status_validacao": "aprovado"})
    assert r.status_code == 422
    assert "status_validacao" in r.json()["detail"]


def test_adicionar_objeto_404_endpoint_inexistente(client, auth_dev):
    cur = _mock_cursor()
    cur.fetchone.side_effect = [None]
    with patch("routers.inventario.get_db_conn", return_value=_mock_conn(cur)):
        r = client.post("/inventario/endpoints/999/objetos",
                        json={"objeto": "VW_X"})
    assert r.status_code == 404


# ── PATCH /inventario/objetos/{id} ───────────────────────────────────────────

def test_patch_objeto_status(client, auth_dev):
    cur = _mock_cursor()
    cur.fetchone.side_effect = [(10,)]  # objeto existe
    with patch("routers.inventario.get_db_conn", return_value=_mock_conn(cur)):
        r = client.patch("/inventario/objetos/10",
                         json={"status_validacao": "validado"})
    assert r.status_code == 200
    assert r.json() == {"ok": True, "id": 10}
    updates = [c for c in cur.execute.call_args_list
               if c.args and "UPDATE dbo.etl_inventario_objeto" in str(c.args[0])]
    assert len(updates) == 1
    assert "status_validacao = ?" in str(updates[0].args[0])
    assert updates[0].args[1] == ["validado", 10]


def test_patch_objeto_status_e_observacao(client, auth_dev):
    cur = _mock_cursor()
    cur.fetchone.side_effect = [(10,)]
    with patch("routers.inventario.get_db_conn", return_value=_mock_conn(cur)):
        r = client.patch("/inventario/objetos/10",
                         json={"status_validacao": "com_erro",
                               "observacao": "view sem o campo de CNPJ"})
    assert r.status_code == 200
    sql = str([c for c in cur.execute.call_args_list
               if c.args and "UPDATE" in str(c.args[0])][0].args[0])
    assert "status_validacao = ?" in sql and "observacao = ?" in sql


def test_patch_objeto_422_status_invalido_ou_body_vazio(client, auth_dev):
    r = client.patch("/inventario/objetos/10",
                     json={"status_validacao": "qualquer"})
    assert r.status_code == 422
    r = client.patch("/inventario/objetos/10", json={})
    assert r.status_code == 422


def test_patch_objeto_404_inexistente(client, auth_dev):
    cur = _mock_cursor()
    cur.fetchone.side_effect = [None]
    with patch("routers.inventario.get_db_conn", return_value=_mock_conn(cur)):
        r = client.patch("/inventario/objetos/999",
                         json={"status_validacao": "validado"})
    assert r.status_code == 404


# ── DELETE /inventario/objetos/{id} ──────────────────────────────────────────

def test_remover_objeto_ok(client, auth_dev):
    cur = _mock_cursor()
    cur.fetchone.side_effect = [(10,)]
    with patch("routers.inventario.get_db_conn", return_value=_mock_conn(cur)):
        r = client.delete("/inventario/objetos/10")
    assert r.status_code == 200
    deletes = [c for c in cur.execute.call_args_list
               if c.args and "DELETE FROM dbo.etl_inventario_objeto" in str(c.args[0])]
    assert len(deletes) == 1


def test_remover_objeto_404_inexistente(client, auth_dev):
    cur = _mock_cursor()
    cur.fetchone.side_effect = [None]
    with patch("routers.inventario.get_db_conn", return_value=_mock_conn(cur)):
        r = client.delete("/inventario/objetos/999")
    assert r.status_code == 404
