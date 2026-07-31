"""
Testes da F5 de docs/spec-dependencias-pipelines.md — cadastro e visão.

Cobre o backend da fase: normalização dos horários da janela e o agrupamento do
endpoint de estado da malha.
"""
from __future__ import annotations

import importlib.util
import sys
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_ROOT = Path(__file__).parent.parent


@pytest.fixture(scope="module")
def pipes():
    for m in ["pyodbc", "fastapi", "fastapi.responses", "pydantic", "httpx"]:
        sys.modules.setdefault(m, MagicMock())
    sys.path.insert(0, str(_ROOT / "api"))
    spec = importlib.util.spec_from_file_location(
        "pipelines_f5_test", _ROOT / "api/routers/pipelines.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ───────────────────────── Horários da janela ──────────────────────────────

def test_hora_normalizada_para_o_sql_server(pipes):
    assert pipes._hora_ou_nulo("08:00") == "08:00:00"
    assert pipes._hora_ou_nulo("8:5") == "08:05:00"
    assert pipes._hora_ou_nulo("23:59") == "23:59:00"


def test_vazio_vira_nulo_e_nao_meia_noite(pipes):
    """Em branco significa 'sem regra'.

    Gravar '00:00' criaria uma janela que o usuário não pediu — e, no caso do
    limite, um alerta diário que ninguém configurou.
    """
    assert pipes._hora_ou_nulo("") is None
    assert pipes._hora_ou_nulo(None) is None
    assert pipes._hora_ou_nulo("   ") is None


def test_hora_invalida_nao_impede_de_salvar(pipes):
    """Os três campos são opcionais: lixo em um não derruba o cadastro todo."""
    for ruim in ("qualquer", "25:00", "10:99", "10", "abc:def"):
        assert pipes._hora_ou_nulo(ruim) is None, ruim


# ─────────────────────── Estado da malha (endpoint) ────────────────────────

class CurEstado:
    """Cursor falso: primeira consulta traz as arestas, segunda os eventos."""

    def __init__(self, arestas, eventos=()):
        self.arestas, self.eventos = arestas, eventos
        self._resultado = []

    def execute(self, sql, params=()):
        if "etl_dependencia_evento" in sql:
            self._resultado = list(self.eventos)
        else:
            self._resultado = list(self.arestas)

    def fetchall(self):
        return self._resultado

    def close(self):
        pass


def _rodar(pipes, monkeypatch, cur):
    conn = MagicMock()
    conn.cursor.return_value = cur
    monkeypatch.setattr(pipes, "get_db_conn", lambda: conn)
    return pipes.estado_dependencias(date_ref="2026-08-01", _auth={})


def test_agrupa_predecessores_por_dependente(pipes, monkeypatch):
    cur = CurEstado([
        ("PIPE_C", "PAI_A", "SUCESSO", "AGUARDANDO_DEPENDENCIA"),
        ("PIPE_C", "PAI_B", None, "AGUARDANDO_DEPENDENCIA"),
    ])
    r = _rodar(pipes, monkeypatch, cur)
    assert len(r["data"]) == 1
    item = r["data"][0]
    assert item["pipeline_name"] == "PIPE_C"
    assert item["pendentes"] == ["PAI_B"]
    assert item["liberado"] is False
    assert item["status"] == "AGUARDANDO_DEPENDENCIA"


def test_liberado_quando_todos_concluiram(pipes, monkeypatch):
    cur = CurEstado([
        ("PIPE_C", "PAI_A", "SUCESSO", "EXECUTANDO"),
        ("PIPE_C", "PAI_B", "SUCESSO", "EXECUTANDO"),
    ])
    item = _rodar(pipes, monkeypatch, cur)["data"][0]
    assert item["pendentes"] == []
    assert item["liberado"] is True


def test_predecessor_que_falhou_conta_como_pendente(pipes, monkeypatch):
    cur = CurEstado([("PIPE_C", "PAI_A", "FALHA", "AGUARDANDO_DEPENDENCIA")])
    item = _rodar(pipes, monkeypatch, cur)["data"][0]
    assert item["pendentes"] == ["PAI_A"]


def test_eventos_anexados_ao_pipeline(pipes, monkeypatch):
    cur = CurEstado(
        [("PIPE_C", "PAI_A", None, "AGUARDANDO_DEPENDENCIA")],
        [("PIPE_C", "JANELA_ESTOUROU", "Não liberou até 11:00: PAI_A")])
    item = _rodar(pipes, monkeypatch, cur)["data"][0]
    assert item["eventos"][0]["tipo"] == "JANELA_ESTOUROU"
    assert "PAI_A" in item["eventos"][0]["detalhe"]


def test_data_invalida_recusada(pipes, monkeypatch):
    monkeypatch.setattr(pipes, "get_db_conn", lambda: MagicMock())
    with pytest.raises(Exception):
        pipes.estado_dependencias(date_ref="31-07-2026", _auth={})


def test_sem_a_migration_devolve_vazio(pipes, monkeypatch):
    """A tela some, o resto do Malha continua de pé."""
    cur = MagicMock()
    cur.execute.side_effect = RuntimeError("Invalid object name")
    conn = MagicMock()
    conn.cursor.return_value = cur
    monkeypatch.setattr(pipes, "get_db_conn", lambda: conn)
    r = pipes.estado_dependencias(date_ref="2026-08-01", _auth={})
    assert r == {"date_ref": "2026-08-01", "data": []}


def test_sem_date_ref_usa_hoje(pipes, monkeypatch):
    cur = CurEstado([])
    r = _rodar(pipes, monkeypatch, CurEstado([]))
    assert r["date_ref"] == "2026-08-01"
    conn = MagicMock()
    conn.cursor.return_value = cur
    monkeypatch.setattr(pipes, "get_db_conn", lambda: conn)
    hoje = pipes.estado_dependencias(date_ref=None, _auth={})
    assert hoje["date_ref"] == date.today().isoformat()
