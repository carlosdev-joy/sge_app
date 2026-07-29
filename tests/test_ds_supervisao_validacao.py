"""
Validação de entrada do cadastro de jobs DataStage supervisionados
(routers/ds_supervisao.py). Funções puras — não dependem de banco.

O que estes testes protegem:
  • A allowlist de projeto/job: esses nomes são interpolados num comando `dsjob`
    remoto pela DAG de coleta (F2). Espaço, ';' ou '$' passando aqui viram
    injeção de shell lá.
  • A normalização da janela e dos dias: a classificação do dia depende deles;
    'HH:MM' e 'HH:MM:SS' têm de convergir para o mesmo valor gravado.
  • Os limites de max_linhas (1..2000, o mesmo cap de build_dsjob_command) e da
    tolerância — CHECK constraints da migration 062 dependem disso para nunca
    serem exercitadas por entrada de usuário.
"""
from __future__ import annotations

import os
import sys
from datetime import date
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

# Mesma ordem de import de tests/test_pipelines_dias_horarios_mes.py: api.main
# ANTES de qualquer router isolado, senão a árvore de routers inicializa fora de
# ordem e corrompe o app real para o resto da sessão de testes.
if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()
os.environ.setdefault("MSSQL_CONN_STR", "__mock__")
from api.main import app as _app  # noqa: F401,E402

from routers.ds_supervisao import (  # noqa: E402
    _bit, _data, _dias, _hora, _inteiro, _nome,
)


# ── Allowlist de projeto/job (anti-injeção no comando remoto) ────────────────

@pytest.mark.parametrize("valor", [
    "BI_CVP", "SeqSsdVida7Peps", "Seq.Job.Final", "job_2026", "A",
])
def test_nome_aceita_padrao_do_console(valor):
    assert _nome(valor, "Job") == valor


def test_nome_remove_espacos_das_bordas():
    assert _nome("  BI_CVP  ", "Projeto") == "BI_CVP"


@pytest.mark.parametrize("valor", [
    "com espaço", "job;rm -rf /", "job$(whoami)", "job|cat", "job&&ls",
    "job'or'1", 'job"x', "job\noutra", "job/../etc", "", "   ", None,
])
def test_nome_recusa_entrada_perigosa_ou_vazia(valor):
    with pytest.raises(HTTPException) as exc:
        _nome(valor, "Job")
    assert exc.value.status_code == 422


# ── Janela de início ────────────────────────────────────────────────────────

@pytest.mark.parametrize("entrada,esperado", [
    ("02:00", "02:00:00"),
    ("02:00:30", "02:00:30"),
    ("00:00", "00:00:00"),
    ("23:59", "23:59:00"),
    ("  07:15  ", "07:15:00"),
])
def test_hora_normaliza_para_hhmmss(entrada, esperado):
    assert _hora(entrada, "Janela") == esperado


@pytest.mark.parametrize("valor", [
    "24:00", "2:00", "02:60", "25:61", "0200", "2h", "abc", "", None, "02:00:60",
])
def test_hora_recusa_formato_invalido(valor):
    with pytest.raises(HTTPException) as exc:
        _hora(valor, "Janela")
    assert exc.value.status_code == 422


# ── Dias da semana ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("entrada,esperado", [
    ("1,2,3,4,5", "1,2,3,4,5"),
    ("5,3,1", "1,3,5"),               # ordena
    ("1,1,2", "1,2"),                 # remove repetição
    (" 6 , 7 ", "6,7"),               # tolera espaço
    ([1, 2, 3], "1,2,3"),             # aceita lista
    (["7"], "7"),
])
def test_dias_normaliza(entrada, esperado):
    assert _dias(entrada) == esperado


@pytest.mark.parametrize("valor", ["", None, "0", "8", "-1", "abc", "1,9", []])
def test_dias_recusa_invalido(valor):
    with pytest.raises(HTTPException) as exc:
        _dias(valor)
    assert exc.value.status_code == 422


# ── Inteiros com faixa (max_linhas, tolerância) ─────────────────────────────

def test_inteiro_usa_default_quando_vazio():
    assert _inteiro(None, "Limite", 1, 2000, 200) == 200
    assert _inteiro("", "Limite", 1, 2000, 200) == 200


@pytest.mark.parametrize("entrada,esperado", [(1, 1), ("500", 500), (2000, 2000)])
def test_inteiro_aceita_dentro_da_faixa(entrada, esperado):
    assert _inteiro(entrada, "Limite", 1, 2000, 200) == esperado


@pytest.mark.parametrize("valor", [0, 2001, -5, "abc", "3.5x"])
def test_inteiro_recusa_fora_da_faixa_ou_nao_numerico(valor):
    with pytest.raises(HTTPException) as exc:
        _inteiro(valor, "Limite", 1, 2000, 200)
    assert exc.value.status_code == 422


def test_inteiro_respeita_faixa_da_tolerancia():
    assert _inteiro(1440, "Tolerância", 0, 1440, 0) == 1440
    with pytest.raises(HTTPException):
        _inteiro(1441, "Tolerância", 0, 1440, 0)


# ── Vigência ────────────────────────────────────────────────────────────────

def test_data_vazia_vira_hoje():
    assert _data(None, "Vigência") == date.today().isoformat()
    assert _data("", "Vigência") == date.today().isoformat()


def test_data_aceita_iso_e_corta_hora():
    assert _data("2026-07-29", "Vigência") == "2026-07-29"
    assert _data("2026-07-29T10:30:00", "Vigência") == "2026-07-29"


@pytest.mark.parametrize("valor", ["29/07/2026", "2026-13-01", "2026-02-30", "ontem", "20260729"])
def test_data_recusa_formato_invalido(valor):
    with pytest.raises(HTTPException) as exc:
        _data(valor, "Vigência")
    assert exc.value.status_code == 422


# ── Flags de alerta ─────────────────────────────────────────────────────────

def test_bit_ausente_usa_default():
    assert _bit({}, "alerta_abortou") == 1
    assert _bit({}, "alerta_abortou", 0) == 0


@pytest.mark.parametrize("valor,esperado", [
    (True, 1), (False, 0), (1, 1), (0, 0), ("sim", 1), ("", 0), (None, 0),
])
def test_bit_converte_valor_recebido(valor, esperado):
    assert _bit({"alerta_atraso": valor}, "alerta_atraso") == esperado
