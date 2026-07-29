"""
Painel de supervisão do dashboard (GET /dashboard/supervisao).

O ponto sensível aqui é a DERIVAÇÃO do estado do dia: o painel não reclassifica
nada, ele traduz os eventos que a DAG já gravou. Se essa tradução errar a
precedência, um job que abortou pode aparecer verde no dashboard.

Banco mockado — nenhum destes testes precisa de SQL Server.
"""
from __future__ import annotations

import os
import sys
from datetime import date
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()
os.environ.setdefault("MSSQL_CONN_STR", "__mock__")
from api.main import app as _app  # noqa: F401,E402

from routers import ds_supervisao  # noqa: E402
from routers.ds_supervisao import ESTADOS_COM_ALERTA, _pior, painel  # noqa: E402

HOJE = date(2026, 7, 27)


class CursorFalso:
    """Devolve, a cada execute+fetchall, o próximo conjunto da fila."""

    def __init__(self, resultados: list[list[tuple]]):
        self._fila = list(resultados)
        self.sqls: list[str] = []

    def execute(self, sql, params=()):
        self.sqls.append(" ".join(sql.split()))

    def fetchall(self):
        return self._fila.pop(0) if self._fila else []

    def close(self):
        pass


def _linha_job(sid=1, project="BI_CVP", job="SeqVida", dias="1,2,3,4,5", ativo=1):
    # (id, project, job_name, janela_inicio, janela_fim, dias_semana, ativo, vigencia)
    return (sid, project, job, "02:00:00", "03:00:00", dias, ativo, "2026-07-01")


def _montar(monkeypatch, jobs, runs=(), eventos=()):
    cur = CursorFalso([list(jobs), list(runs), list(eventos)])
    conn = MagicMock()
    conn.cursor.return_value = cur
    monkeypatch.setattr(ds_supervisao, "get_db_conn", lambda: conn)
    return cur


# ── Precedência do estado ───────────────────────────────────────────────────

def test_pior_sem_nada_e_sem_registro():
    assert _pior([]) == "sem_registro"


@pytest.mark.parametrize("estados,esperado", [
    (["ok"], "ok"),
    (["ok", "abortado"], "abortado"),
    (["abortado", "sem_verificacao"], "sem_verificacao"),
    (["atrasado", "nao_executou"], "nao_executou"),
    (["executando", "ok"], "executando"),
    (["ok", "atrasado"], "atrasado"),
])
def test_pior_respeita_a_precedencia(estados, esperado):
    assert _pior(estados) == esperado


def test_estados_com_alerta_nao_incluem_sucesso():
    assert "ok" not in ESTADOS_COM_ALERTA
    assert "executando" not in ESTADOS_COM_ALERTA
    assert "sem_registro" not in ESTADOS_COM_ALERTA


# ── Validação da data ───────────────────────────────────────────────────────

@pytest.mark.parametrize("valor", ["27/07/2026", "2026-13-01", "ontem", "20260727"])
def test_date_ref_invalido_devolve_400(valor):
    with pytest.raises(HTTPException) as exc:
        painel(date_ref=valor, _user={})
    assert exc.value.status_code == 400
    assert "date_ref" in exc.value.detail


def test_date_ref_vazio_usa_hoje(monkeypatch):
    _montar(monkeypatch, jobs=[])
    assert painel(date_ref=None, _user={})["date_ref"] == date.today().isoformat()


# ── Montagem da resposta ────────────────────────────────────────────────────

def test_job_com_run_ok_fica_verde(monkeypatch):
    _montar(monkeypatch,
            jobs=[_linha_job()],
            runs=[(1, "2026-07-27 02:10:00", "2026-07-27 02:50:00", 2400, "ok", 3)])
    resp = painel(date_ref="2026-07-27", _user={})
    item = resp["data"][0]
    assert item["estado"] == "ok"
    assert resp["resumo"] == {"total": 1, "com_alerta": 0}
    assert item["runs"][0]["duracao_seg"] == 2400


def test_evento_de_abort_domina_run_anterior_bem_sucedido(monkeypatch):
    # Rodou ok de manhã e abortou à tarde: o dia é "abortou".
    _montar(monkeypatch,
            jobs=[_linha_job()],
            runs=[(1, "2026-07-27 02:10:00", "2026-07-27 02:50:00", 2400, "ok", 3)],
            eventos=[(1, "ABORTOU", "abortou às 14h", "2026-07-27 14:05:00", None)])
    item = painel(date_ref="2026-07-27", _user={})["data"][0]
    assert item["estado"] == "abortado"


def test_falha_de_estrutura_tem_prioridade_sobre_abort(monkeypatch):
    _montar(monkeypatch,
            jobs=[_linha_job()],
            eventos=[(1, "ABORTOU", "abortou", "2026-07-27 03:00:00", None),
                     (1, "ESTRUTURA", "dsjob retornou 255", "2026-07-27 04:00:00", None)])
    item = painel(date_ref="2026-07-27", _user={})["data"][0]
    assert item["estado"] == "sem_verificacao"


def test_situacao_inicial_sozinha_nao_conta_como_alerta(monkeypatch):
    # O card de validação não é problema — não pode pintar o painel de vermelho.
    _montar(monkeypatch,
            jobs=[_linha_job()],
            eventos=[(1, "SITUACAO_INICIAL", "monitoramento iniciado",
                      "2026-07-27 08:00:00", "2026-07-27 08:01:00")])
    resp = painel(date_ref="2026-07-27", _user={})
    assert resp["resumo"]["com_alerta"] == 0
    assert resp["data"][0]["estado"] == "sem_registro"
    assert resp["data"][0]["eventos"][0]["tipo"] == "SITUACAO_INICIAL"


def test_dia_fora_da_semana_configurada_vem_marcado(monkeypatch):
    # 2026-08-01 é sábado; o job roda seg–sex.
    _montar(monkeypatch, jobs=[_linha_job(dias="1,2,3,4,5")])
    item = painel(date_ref="2026-08-01", _user={})["data"][0]
    assert item["previsto"] is False


def test_dia_previsto_vem_marcado(monkeypatch):
    _montar(monkeypatch, jobs=[_linha_job(dias="1,2,3,4,5")])
    assert painel(date_ref="2026-07-27", _user={})["data"][0]["previsto"] is True


def test_job_inativo_com_historico_ainda_aparece(monkeypatch):
    _montar(monkeypatch,
            jobs=[_linha_job(ativo=0)],
            runs=[(1, "2026-07-27 02:10:00", "2026-07-27 02:50:00", 2400, "ok", 1)])
    item = painel(date_ref="2026-07-27", _user={})["data"][0]
    assert item["ativo"] is False
    assert item["runs"]


def test_contagem_de_alerta_soma_so_os_problematicos(monkeypatch):
    _montar(monkeypatch,
            jobs=[_linha_job(sid=1, job="SeqA"), _linha_job(sid=2, job="SeqB"),
                  _linha_job(sid=3, job="SeqC")],
            runs=[(1, "2026-07-27 02:10:00", "2026-07-27 02:50:00", 2400, "ok", 1)],
            eventos=[(2, "ATRASO", "não iniciou", "2026-07-27 03:05:00", None)])
    resp = painel(date_ref="2026-07-27", _user={})
    assert resp["resumo"] == {"total": 3, "com_alerta": 1}
    estados = {d["job_name"]: d["estado"] for d in resp["data"]}
    assert estados == {"SeqA": "ok", "SeqB": "atrasado", "SeqC": "sem_registro"}


# ── Degradação ──────────────────────────────────────────────────────────────

def test_banco_indisponivel_devolve_painel_vazio_sem_estourar(monkeypatch):
    def _explode():
        raise RuntimeError("sem conexão")

    monkeypatch.setattr(ds_supervisao, "get_db_conn", _explode)
    resp = painel(date_ref="2026-07-27", _user={})
    assert resp == {"date_ref": "2026-07-27", "data": [],
                    "resumo": {"total": 0, "com_alerta": 0}}


def test_tabela_ausente_devolve_painel_vazio(monkeypatch):
    # Migration 062 ainda não aplicada: o dashboard inteiro não pode quebrar.
    class CursorQuebrado(CursorFalso):
        def execute(self, sql, params=()):
            raise RuntimeError("Invalid object name 'dbo.etl_ds_supervisao_job'")

    conn = MagicMock()
    conn.cursor.return_value = CursorQuebrado([])
    monkeypatch.setattr(ds_supervisao, "get_db_conn", lambda: conn)
    assert painel(date_ref="2026-07-27", _user={})["data"] == []


def test_painel_nunca_consulta_ssh(monkeypatch):
    # Contrato da fase: o dashboard lê só do banco. Um SELECT é barato; abrir
    # SSH por request derrubaria a tela.
    cur = _montar(monkeypatch, jobs=[_linha_job()])
    painel(date_ref="2026-07-27", _user={})
    assert all("dsjob" not in sql for sql in cur.sqls)
    assert all(sql.upper().startswith("SELECT") for sql in cur.sqls)
