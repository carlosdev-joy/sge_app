"""GET /chamados — o espelho servido para a tela.

O que estes testes prendem:

  1. **Fila vazia não pode ter uma explicação só.** Zero chamados com sync OK
     é notícia boa; zero com sync em ERRO (ou sem sync nenhum) é a integração
     quebrada com cara de "tudo resolvido" — o risco #4 da spec. A resposta
     precisa carregar QUAL dos três casos é.
  2. **Sem a migration 088 a tela avisa, não quebra.** `migration_ausente` em
     vez de 500: tela branca não diz nada a quem opera.
  3. **Erro no sync não esconde o espelho.** Os dados anteriores continuam
     servindo, com o aviso por cima — melhor fila velha AVISADA que fila
     nenhuma.
  4. **Ciclo que não fechou ≠ ciclo com erro.** `terminado_em` nulo é worker
     morto no meio; status ERRO é a integração recusando. Causas diferentes,
     tratamentos diferentes.
  5. **A contagem por coluna bate com a lista** — número de cabeçalho que
     mente é pior que número nenhum.

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

# Colunas do SELECT de chamados, na ordem do router.
def _chamado(numero="INC001", tipo="incident", estado="novo", ativo=1,
             idade=3, titulo="Falha na carga", sys_id=None):
    return (sys_id or f"sid-{numero}", numero, tipo, titulo, "In Progress",
            estado, "3 - Moderate", "Fulano", "Engenharia",
            "2026-08-10 10:00:00", "2026-08-13 09:00:00", None, ativo,
            "https://x.service-now.com/nav", "2026-08-13 12:00:00", idade)


def _ciclo(status="OK", idade_min=30, terminado="2026-08-13 12:05:00", erro=None):
    return (7, "2026-08-13 12:00:00", terminado, status, 10, 3, 2, 1, 0,
            erro, idade_min)


class CursorFalso:
    """Devolve a lista de chamados no 1º SELECT e o ciclo no 2º."""

    def __init__(self, chamados, ciclo=None, explode=False):
        self.chamados = chamados
        self.ciclo = ciclo
        self.explode = explode
        self._proximo = None

    def execute(self, sql, params=None):
        if self.explode:
            raise RuntimeError("Invalid object name 'dbo.etl_chamado'")
        self._proximo = "ciclo" if "etl_chamado_sync" in sql else "chamados"
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

    def _fabrica():
        conn = MagicMock()
        conn.cursor.return_value = estado["cur"]
        return conn

    monkeypatch.setattr("routers.chamados.get_db_conn", _fabrica)
    return estado


# ═══════════ 1. as três caras da fila vazia ═════════════════════════════════

def test_fila_vazia_com_sync_ok_e_noticia_boa(cliente, banco):
    banco["cur"] = CursorFalso([], _ciclo(status="OK"))
    d = cliente.get("/chamados").json()
    assert d["total"] == 0
    assert "confira o grupo" in d["alerta_fila_vazia"]
    assert "falhou" not in d["alerta_fila_vazia"]


def test_fila_vazia_com_sync_em_erro_avisa_integracao(cliente, banco):
    """O falso verde do risco #4: zero chamados porque o sync quebrou."""
    banco["cur"] = CursorFalso([], _ciclo(status="ERRO", erro="HTTP 403 em change_request"))
    d = cliente.get("/chamados").json()
    assert d["total"] == 0
    assert "falhou" in d["alerta_fila_vazia"]
    assert "403" in d["alerta_fila_vazia"], "a causa precisa chegar na tela"


def test_fila_vazia_sem_sync_nenhum_aponta_o_admin(cliente, banco):
    banco["cur"] = CursorFalso([], None)
    d = cliente.get("/chamados").json()
    assert "Nenhuma sincronização registrada" in d["alerta_fila_vazia"]
    assert "Admin > ServiceNow" in d["alerta_fila_vazia"]


def test_fila_com_chamados_nao_tem_alerta_de_vazio(cliente, banco):
    banco["cur"] = CursorFalso([_chamado()], _ciclo())
    d = cliente.get("/chamados").json()
    assert d["alerta_fila_vazia"] is None


# ═══════════ 2. degradação sem a migration ══════════════════════════════════

def test_sem_a_migration_avisa_em_vez_de_quebrar(cliente, banco):
    banco["cur"] = CursorFalso([], None, explode=True)
    r = cliente.get("/chamados")
    assert r.status_code == 200, "tela branca não diz nada a quem opera"
    d = r.json()
    assert d["migration_ausente"] is True
    assert d["chamados"] == [] and d["total"] == 0


# ═══════════ 3. erro no sync não esconde o espelho ══════════════════════════

def test_sync_com_erro_ainda_serve_os_chamados(cliente, banco):
    """Fila velha AVISADA é melhor que fila nenhuma."""
    banco["cur"] = CursorFalso([_chamado(), _chamado("INC002")],
                               _ciclo(status="ERRO", erro="401 na credencial"))
    d = cliente.get("/chamados").json()
    assert d["total"] == 2, "o espelho anterior continua servindo"
    assert d["ultimo_sync"]["erro"] == "401 na credencial"


# ═══════════ 4. ciclo que não fechou ≠ ciclo com erro ═══════════════════════

def test_ciclo_sem_terminado_em_e_em_andamento(cliente, banco):
    banco["cur"] = CursorFalso([_chamado()], _ciclo(terminado=None))
    d = cliente.get("/chamados").json()
    assert d["ultimo_sync"]["em_andamento"] is True


def test_ciclo_fechado_nao_e_em_andamento(cliente, banco):
    banco["cur"] = CursorFalso([_chamado()], _ciclo())
    assert cliente.get("/chamados").json()["ultimo_sync"]["em_andamento"] is False


# ═══════════ 5. frescor ═════════════════════════════════════════════════════

def test_sync_recente_nao_esta_atrasado(cliente, banco):
    banco["cur"] = CursorFalso([_chamado()], _ciclo(idade_min=30))
    assert cliente.get("/chamados").json()["ultimo_sync"]["atrasado"] is False


def test_sync_de_sete_horas_esta_atrasado(cliente, banco):
    """Acima de 6h são 2 ciclos de 3h perdidos."""
    banco["cur"] = CursorFalso([_chamado()], _ciclo(idade_min=7 * 60))
    assert cliente.get("/chamados").json()["ultimo_sync"]["atrasado"] is True


def test_limite_de_seis_horas_ainda_nao_alerta(cliente, banco):
    banco["cur"] = CursorFalso([_chamado()], _ciclo(idade_min=6 * 60))
    assert cliente.get("/chamados").json()["ultimo_sync"]["atrasado"] is False


# ═══════════ 6. a contagem tem que bater com a lista ════════════════════════

def test_contagem_por_coluna_bate_com_a_lista(cliente, banco):
    banco["cur"] = CursorFalso([
        _chamado("INC1", estado="novo"), _chamado("INC2", estado="novo"),
        _chamado("INC3", estado="andamento"), _chamado("INC4", estado="outros"),
    ], _ciclo())
    d = cliente.get("/chamados").json()
    assert d["por_coluna"]["novo"] == 2
    assert d["por_coluna"]["andamento"] == 1
    assert d["por_coluna"]["outros"] == 1
    assert d["por_coluna"]["aguardando"] == 0
    assert sum(d["por_coluna"].values()) == d["total"], (
        "cabeçalho de coluna que mente é pior que cabeçalho nenhum")


def test_toda_coluna_do_kanban_vem_na_resposta(cliente, banco):
    """A tela desenha as colunas a partir daqui — faltar uma some com ela."""
    banco["cur"] = CursorFalso([_chamado()], _ciclo())
    d = cliente.get("/chamados").json()
    assert d["colunas"] == ["novo", "andamento", "aguardando", "resolvido", "outros"]
    for coluna in d["colunas"]:
        assert coluna in d["por_coluna"]


def test_chamado_traz_o_estado_de_origem_e_a_idade(cliente, banco):
    banco["cur"] = CursorFalso([_chamado(idade=8)], _ciclo())
    c = cliente.get("/chamados").json()["chamados"][0]
    assert c["estado_origem"] == "In Progress", (
        "sem o valor cru, um card em 'Outros' não se explica")
    assert c["idade_dias"] == 8
    assert c["url"].startswith("https://")


def test_exige_autenticacao():
    """Sem override de auth a rota não pode responder 200."""
    with TestClient(app) as anonimo:
        assert anonimo.get("/chamados").status_code in (401, 403)
