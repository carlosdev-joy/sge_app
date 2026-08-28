"""O parentesco chega à tela, e as tarefas de um RITM têm rota própria.

Todo RITM do catálogo gera uma `sc_task`, e o espelho traz as duas como linhas
irmãs: medido no dev em 2026-08-28, a fila tinha **95 registros para 59
trabalhos**. O parentesco está no banco desde a migration 090 e, até aqui, nada
acima do banco o usava.

O que estes testes prendem:

  1. **`pai_sys_id` e `pai_numero` chegam na listagem.** Sem eles a tela não
     tem como saber que a tarefa já está representada pelo card do pedido.
  2. **String vazia é ausência.** O sync grava `''` — e não NULL — quando o
     campo não vem da API. Se `''` chegasse à tela como valor, TODO chamado
     teria um "pai" e a fila inteira sumiria.
  3. **Sem a migration 090, a fila continua servida — plana.** As colunas
     entram no bloco degradável, junto com as 091/092: ambiente sem a
     migration serve a fila de sempre em vez de virar "sistema em atualização".
  4. **`/chamados/{sys_id}/tasks` devolve as filhas, inclusive INATIVAS.** A
     fila mostra o pedido vivo; quem abre um RITM quer a execução inteira.
  5. **Espelho indisponível vira aviso, não "nenhuma tarefa".** Dizer "não há
     tarefas" quando a consulta falhou é uma afirmação — e falsa.

Nada toca banco: cursor dublê e `get_db_conn` substituído.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()
os.environ.setdefault("MSSQL_CONN_STR", "__mock__")
from api.main import app  # noqa: E402

from deps import get_current_user  # noqa: E402

from tests.test_chamados_api import _chamado, _ciclo  # noqa: E402


class CursorFalso:
    """1º SELECT devolve os chamados; o que citar etl_chamado_sync, o ciclo."""

    def __init__(self, chamados, ciclo=None, explode_em=None):
        self.chamados = chamados
        self.ciclo = ciclo
        self.explode_em = explode_em      # trecho de SQL que deve falhar
        self._alvo = None

    def execute(self, sql, params=None):
        if self.explode_em and self.explode_em in sql:
            raise RuntimeError("Invalid column name 'pai_sys_id'")
        self._alvo = "ciclo" if "etl_chamado_sync" in sql else "chamados"
        return self

    def fetchall(self):
        return list(self.chamados)

    def fetchone(self):
        return self.ciclo

    def close(self):
        pass


@pytest.fixture
def cliente():
    app.dependency_overrides[get_current_user] = lambda: {
        "matricula": "U1", "perfil": "operador", "permissoes": ["tela_chamados"]}
    yield TestClient(app)
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def banco(monkeypatch):
    estado = {"cur": CursorFalso([], None)}

    class ConexaoFalsa:
        def cursor(self):
            return estado["cur"]

        def close(self):
            pass

    monkeypatch.setattr("routers.chamados.get_db_conn", lambda: ConexaoFalsa())
    return estado


# ── 1. o parentesco chega à tela ────────────────────────────────────────────

def test_pai_sys_id_e_numero_chegam_na_listagem(cliente, banco):
    banco["cur"] = CursorFalso(
        [_chamado(numero="SCTASK001", tipo="task", sys_id="t1",
                  pai_sys_id="sid-RITM001", pai_numero="RITM001")],
        _ciclo())
    r = cliente.get("/chamados")
    assert r.status_code == 200
    c = r.json()["chamados"][0]
    assert c["pai_sys_id"] == "sid-RITM001"
    assert c["pai_numero"] == "RITM001"


def test_string_vazia_do_sync_vira_ausencia_de_pai(cliente, banco):
    """O sync grava '' quando o campo não vem — e '' é ausência, não valor.

    Se `''` chegasse como valor, a tela trataria TODO chamado como filho e a
    fila inteira desapareceria. Um teste que só usasse NULL passaria verde com
    esse defeito de pé, porque o NULL do laboratório não é o que o sync grava.
    """
    banco["cur"] = CursorFalso(
        [_chamado(numero="RITM001", tipo="ritm", pai_sys_id="", pai_numero="")],
        _ciclo())
    c = cliente.get("/chamados").json()["chamados"][0]
    assert c["pai_sys_id"] is None
    assert c["pai_numero"] is None


def test_sem_a_migration_090_a_fila_continua_servida_plana(cliente, banco):
    """Coluna ausente derruba o SELECT completo, não a tela."""
    linha_curta = _chamado(numero="INC001")[:16]   # só o bloco base
    banco["cur"] = CursorFalso([linha_curta], _ciclo(),
                               explode_em="pai_sys_id")
    r = cliente.get("/chamados")
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["migration_ausente"] is False, "a fila tem de continuar servida"
    assert corpo["derivacoes_pendentes"] is True, "e a tela precisa SABER disso"
    assert corpo["chamados"][0]["pai_sys_id"] is None


# ── 2. as tarefas de um RITM ────────────────────────────────────────────────

def _task(numero="SCTASK001", ativo=1, sys_id=None):
    return (sys_id or f"sid-{numero}", numero, "task", "Executar a carga",
            "andamento", "3 - Moderate", "Fulano", "Engenharia",
            "2026-08-10 10:00:00", "2026-08-13 09:00:00", None, ativo,
            "https://x.service-now.com/nav", "2026-08-13 12:00:00")


def test_tasks_do_ritm_devolve_as_filhas(cliente, banco):
    banco["cur"] = CursorFalso([_task("SCTASK001"), _task("SCTASK002")])
    r = cliente.get("/chamados/sid-RITM001/tasks")
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["sys_id"] == "sid-RITM001"
    assert corpo["total"] == 2
    assert [t["numero"] for t in corpo["tasks"]] == ["SCTASK001", "SCTASK002"]


def test_tasks_inclui_inativa(cliente, banco):
    """A fila mostra o vivo; o card do pedido mostra a execução inteira."""
    banco["cur"] = CursorFalso([_task("SCTASK001", ativo=1),
                                _task("SCTASK002", ativo=0)])
    tasks = cliente.get("/chamados/sid-RITM001/tasks").json()["tasks"]
    assert [t["ativo"] for t in tasks] == [True, False]


def test_espelho_indisponivel_avisa_em_vez_de_dizer_que_nao_ha_tarefa(cliente, banco):
    banco["cur"] = CursorFalso([], explode_em="pai_sys_id")
    r = cliente.get("/chamados/sid-RITM001/tasks")
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["migration_ausente"] is True, (
        "sem a marca, a tela anuncia 'nenhuma tarefa' — que é uma afirmação, "
        "e falsa: o que houve foi consulta que falhou")
    assert corpo["tasks"] == []


def test_a_rota_de_tasks_exige_autenticacao():
    """Sem o override da dependência, a rota não pode responder 200."""
    with TestClient(app) as c:
        assert c.get("/chamados/sid-RITM001/tasks").status_code in (401, 403)
