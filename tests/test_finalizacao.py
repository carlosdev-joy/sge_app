"""
Testes da Finalização Manual (api/routers/finalizacao.py).

Padrão de test_inventario.py: TestClient do conftest, get_db_conn mockado em
routers.finalizacao e autenticação sobrescrita via dependency_overrides —
nenhum teste toca rede ou banco.
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

from deps import PERM_EXECUTAR, get_current_user


# ── stubs ────────────────────────────────────────────────────────────────────

def _mock_cursor(fetchall=None, rowcount=0):
    cur = MagicMock()
    cur.description = []
    cur.rowcount = rowcount
    if isinstance(fetchall, list) and fetchall and isinstance(fetchall[0], list):
        cur.fetchall.side_effect = fetchall     # uma lista de linhas por chamada
    else:
        cur.fetchall.return_value = fetchall or []
    return cur


def _mock_conn(cur):
    conn = MagicMock()
    conn.cursor.return_value = cur
    return conn


@pytest.fixture
def auth_operador(app):
    """Usuário com acao_executar (perfil operador/desenvolvedor/admin)."""
    app.dependency_overrides[get_current_user] = lambda: {
        "matricula": "OP1", "perfil": "operador",
        "permissoes": [PERM_EXECUTAR, "tela_finalizacao"],
    }
    yield
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def auth_consulta(app):
    """Usuário autenticado SEM acao_executar (só leitura)."""
    app.dependency_overrides[get_current_user] = lambda: {
        "matricula": "USER1", "perfil": "consulta", "permissoes": [],
    }
    yield
    app.dependency_overrides.pop(get_current_user, None)


# ── registro do router ───────────────────────────────────────────────────────

def test_router_finalizacao_registrado(client):
    """Endpoints de /finalizacao devem aparecer no schema OpenAPI."""
    r = client.get("/openapi.json")
    assert r.status_code == 200
    paths = r.json().get("paths", {})
    for p in ("/finalizacao/executando", "/finalizacao/finalizar"):
        assert p in paths, f"rota {p} não registrada em api/main.py"


# ── auth 401/403 ─────────────────────────────────────────────────────────────

def test_finalizacao_sem_auth_401(client):
    assert client.get("/finalizacao/executando").status_code == 401
    assert client.post("/finalizacao/finalizar", json={}).status_code == 401


def test_finalizar_exige_acao_executar_403(client, auth_consulta):
    """Perfil sem acao_executar vê a lista, mas não finaliza."""
    r = client.post("/finalizacao/finalizar",
                    json={"pipeline": "PIPE_X", "status_final": "SUCCESS"})
    assert r.status_code == 403


def test_leitura_nao_exige_acao_executar(client, auth_consulta):
    with patch("routers.finalizacao.get_db_conn",
               return_value=_mock_conn(_mock_cursor())):
        r = client.get("/finalizacao/executando")
    assert r.status_code == 200
    assert r.json() == {"data": []}


# ── GET /finalizacao/executando ──────────────────────────────────────────────

def test_listar_degrada_sem_tabela(client, auth_operador):
    """Banco indisponível/tabela ausente → data [] (nunca 500)."""
    with patch("routers.finalizacao.get_db_conn",
               side_effect=Exception("tabela não existe")):
        r = client.get("/finalizacao/executando")
    assert r.status_code == 200
    assert r.json() == {"data": []}


def test_listar_agrega_estruturas_e_snapshots(client, auth_operador):
    """Linha do etl_job_execution enriquecida com estruturas abertas e snapshots;
    estrutura órfã (só no etl_ds_job_log) também entra na lista."""
    cur = _mock_cursor(fetchall=[
        [("e1", "PIPE_X", "PROJ", 2, None, 3600)],   # etl_job_execution agregado
        [("e1", "PIPE_X", "PROJ", 5), ("e2", "PIPE_ORFA", "PROJ", 1)],  # ds_job_log
        [("e1", "PIPE_X", 4)],                        # snapshots de performance
    ])
    with patch("routers.finalizacao.get_db_conn", return_value=_mock_conn(cur)):
        r = client.get("/finalizacao/executando")
    assert r.status_code == 200
    data = {d["execution_id"]: d for d in r.json()["data"]}
    assert data["e1"]["pipeline"] == "PIPE_X"
    assert data["e1"]["jobs_running"] == 2
    assert data["e1"]["estruturas_abertas"] == 5
    assert data["e1"]["snapshots"] == 4
    assert data["e2"]["pipeline"] == "PIPE_ORFA"     # órfã: sem par no log principal
    assert data["e2"]["jobs_running"] == 0
    assert data["e2"]["estruturas_abertas"] == 1


# ── POST /finalizacao/finalizar ──────────────────────────────────────────────

def test_finalizar_valida_body(client, auth_operador):
    assert client.post("/finalizacao/finalizar", json={}).status_code == 422
    assert client.post("/finalizacao/finalizar",
                       json={"pipeline": "PIPE_X"}).status_code == 422
    assert client.post("/finalizacao/finalizar",
                       json={"pipeline": "PIPE_X",
                             "status_final": "CANCELADO"}).status_code == 422


def test_finalizar_sem_execucao_running_404(client, auth_operador):
    cur = _mock_cursor(fetchall=[])
    with patch("routers.finalizacao.get_db_conn", return_value=_mock_conn(cur)):
        r = client.post("/finalizacao/finalizar",
                        json={"pipeline": "PIPE_X", "status_final": "SUCCESS"})
    assert r.status_code == 404


def test_finalizar_fecha_logs_estrutura_e_snapshots(client, auth_operador):
    """Caminho feliz: fecha etl_job_execution + etl_ds_job_log, limpa snapshots,
    audita em etl_pipeline_audit e responde o resumo."""
    cur = _mock_cursor(fetchall=[("20260701T0300",)], rowcount=3)
    conn = _mock_conn(cur)
    with patch("routers.finalizacao.get_db_conn", return_value=conn), \
         patch("routers.finalizacao.add_notificacao") as notif:
        r = client.post("/finalizacao/finalizar", json={
            "pipeline": "PIPE_X", "execution_id": "20260701T0300",
            "status_final": "SUCCESS", "motivo": "terminou no DS; worker caiu",
        })
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["execucoes_finalizadas"] == ["20260701T0300"]
    assert body["jobs_fechados"] == 3
    assert body["estruturas_fechadas"] == 3
    assert body["snapshots_removidos"] == 3
    conn.commit.assert_called_once()
    notif.assert_called_once()

    # SQL executado: select de alvos, 2 UPDATEs, DELETE e INSERT de auditoria
    sqls = [c.args[0] for c in cur.execute.call_args_list]
    assert any("UPDATE dbo.etl_job_execution" in s for s in sqls)
    assert any("UPDATE dbo.etl_ds_job_log" in s for s in sqls)
    assert any("DELETE FROM dbo.etl_pipeline_performance_snapshot" in s for s in sqls)
    audit = [c for c in cur.execute.call_args_list
             if "etl_pipeline_audit" in c.args[0]]
    assert len(audit) == 1
    assert audit[0].args[1][1] == "OP1"              # changed_by = matrícula
    assert "motivo: terminou no DS" in audit[0].args[1][2]


def test_finalizar_failed_vira_aborted_no_ds_log(client, auth_operador):
    """status_final=FAILED → estrutura fecha como ABORTED/status_code 3."""
    cur = _mock_cursor(fetchall=[("e9",)], rowcount=1)
    with patch("routers.finalizacao.get_db_conn", return_value=_mock_conn(cur)), \
         patch("routers.finalizacao.add_notificacao"):
        r = client.post("/finalizacao/finalizar",
                        json={"pipeline": "PIPE_X", "status_final": "FAILED"})
    assert r.status_code == 200
    ds_update = next(c for c in cur.execute.call_args_list
                     if "UPDATE dbo.etl_ds_job_log" in c.args[0])
    assert ds_update.args[1][0] == "ABORTED"
    assert ds_update.args[1][1] == 3
