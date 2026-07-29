"""
Parser do `dsjob -logsum` em Python (dags/utils/ds_logsum.py).

Este é o teste que a spec exige antes de confiar na coleta: o parser é um porte
do que o Console DataStage já usa no front (parseLogsum em DsConsole.tsx), e
divergir dele significa classificar um dia errado — dizer que o job não rodou
quando rodou, ou o contrário.

As fixtures reproduzem o formato de saída do dsjob: cada evento são duas linhas,
o cabeçalho "<id> <TIPO> <data>" e a mensagem embaixo.
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import pytest

_DAGS = Path(__file__).parent.parent / "dags"
if str(_DAGS) not in sys.path:
    sys.path.insert(0, str(_DAGS))

from utils.ds_logsum import (  # noqa: E402
    ABORTADO, EXECUTANDO, OK, parse_ds_time, parse_logsum, runs_desde,
)


# ── Fixtures de log ─────────────────────────────────────────────────────────

RUN_OK = """
   1201 STARTED       Mon Jul 27 02:10:15 2026
Starting Job SeqSsdVida7Peps.
   1202 INFO          Mon Jul 27 02:10:16 2026
SeqSsdVida7Peps..JobControl (@Coordinator): -> (SsdVidaCarga): Job run requested
   1203 INFO          Mon Jul 27 02:10:17 2026
SeqSsdVida7Peps..JobControl (@Coordinator): Waiting for job SsdVidaCarga to finish
   1204 INFO          Mon Jul 27 02:40:00 2026
SeqSsdVida7Peps..JobControl (@Coordinator): Job SsdVidaCarga has finished, status = 1 (Finished OK)
   1205 STARTED       Mon Jul 27 02:45:10 2026
Finished Job SeqSsdVida7Peps.
"""

RUN_ABORTADO = """
   1301 STARTED       Tue Jul 28 02:05:00 2026
Starting Job SeqSsdVida7Peps.
   1302 INFO          Tue Jul 28 02:05:01 2026
SeqSsdVida7Peps..JobControl (@Coordinator): -> (SsdVidaCarga): Job run requested
   1303 INFO          Tue Jul 28 02:20:00 2026
SeqSsdVida7Peps..JobControl (@Coordinator): Job SsdVidaCarga has finished, status = 3 (Aborted)
   1304 FATAL         Tue Jul 28 02:20:05 2026
SeqSsdVida7Peps..JobControl (@Coordinator): Job under control aborted due to a fatal error
"""

RUN_EM_EXECUCAO = """
   1401 STARTED       Wed Jul 29 02:03:00 2026
Starting Job SeqSsdVida7Peps.
   1402 INFO          Wed Jul 29 02:03:01 2026
SeqSsdVida7Peps..JobControl (@Coordinator): -> (SsdVidaCarga): Job run requested
   1403 INFO          Wed Jul 29 02:03:02 2026
SeqSsdVida7Peps..JobControl (@Coordinator): Waiting for job SsdVidaCarga to start
"""

# Três runs em dias diferentes, como o log realmente acumula.
TRES_DIAS = RUN_OK + RUN_ABORTADO + RUN_EM_EXECUCAO

# O `-max` corta o começo: o log abre no meio de um run, sem "Starting Job".
TRUNCADO = """
SeqSsdVida7Peps..JobControl (@Coordinator): Job SsdVidaAntigo has finished, status = 1 (Finished OK)
   1150 STARTED       Sun Jul 26 03:00:00 2026
Finished Job SeqSsdVida7Peps.
""" + RUN_OK

SOB_CONTROLE = """
   1501 STARTED       Mon Jul 27 05:00:00 2026
Starting Job SeqOutro.
   1502 INFO          Mon Jul 27 05:00:01 2026
SeqOutro..JobControl (@Coord): -> (FilhoA): Job run requested
   1503 INFO          Mon Jul 27 05:30:00 2026
SeqOutro..JobControl (@Coord): Job under control finished
   1504 INFO          Mon Jul 27 06:00:00 2026
SeqOutro..JobControl (@Coord): Job FilhoZ has finished, status = 1 (Finished OK)
"""


# ── parse_ds_time ───────────────────────────────────────────────────────────

def test_parse_time_converte_formato_do_datastage():
    assert parse_ds_time("Mon Jul 27 02:10:15 2026") == datetime(2026, 7, 27, 2, 10, 15)


def test_parse_time_aceita_dia_com_um_digito():
    assert parse_ds_time("Tue Jun 2 14:33:26 2026") == datetime(2026, 6, 2, 14, 33, 26)


@pytest.mark.parametrize("valor", [
    None, "", "27/07/2026", "Mon Xxx 27 02:10:15 2026", "Mon Jul 27 02:10 2026",
])
def test_parse_time_devolve_none_em_entrada_ruim(valor):
    assert parse_ds_time(valor) is None


def test_parse_time_nao_explode_em_data_impossivel():
    # Log corrompido não pode derrubar a coleta inteira.
    assert parse_ds_time("Mon Feb 31 02:10:15 2026") is None


# ── Segmentação em runs ─────────────────────────────────────────────────────

def test_run_concluido():
    runs = parse_logsum(RUN_OK)
    assert len(runs) == 1
    run = runs[0]
    assert run.resultado == OK
    assert run.inicio == datetime(2026, 7, 27, 2, 10, 15)
    assert run.fim == datetime(2026, 7, 27, 2, 45, 10)
    assert run.duracao_seg == 2095
    assert run.jobs_filhos == 1
    assert run.filhos_abortados == []


def test_run_abortado_identifica_filho_culpado():
    runs = parse_logsum(RUN_ABORTADO)
    assert len(runs) == 1
    run = runs[0]
    assert run.resultado == ABORTADO
    assert run.fim == datetime(2026, 7, 28, 2, 20, 5)
    # status = 3 é o código de Aborted do DataStage.
    assert run.filhos_abortados == ["SsdVidaCarga"]


def test_run_sem_termino_fica_em_execucao():
    runs = parse_logsum(RUN_EM_EXECUCAO)
    assert len(runs) == 1
    assert runs[0].resultado == EXECUTANDO
    assert runs[0].fim is None
    assert runs[0].duracao_seg is None


def test_varios_runs_saem_do_mais_antigo_ao_mais_novo():
    runs = parse_logsum(TRES_DIAS)
    assert [r.resultado for r in runs] == [OK, ABORTADO, EXECUTANDO]
    assert [r.inicio.day for r in runs] == [27, 28, 29]


def test_log_truncado_descarta_trecho_sem_inicio():
    # O pedaço inicial não tem "Starting Job": não dá para afirmar quando
    # aquele run começou, então ele não vira um run com início errado.
    runs = parse_logsum(TRUNCADO)
    assert len(runs) == 1
    assert runs[0].inicio == datetime(2026, 7, 27, 2, 10, 15)


def test_job_under_control_finished_fecha_o_run():
    runs = parse_logsum(SOB_CONTROLE)
    assert len(runs) == 1
    assert runs[0].fim == datetime(2026, 7, 27, 5, 30, 0)
    # O evento posterior ao fechamento não entra no run encerrado.
    assert runs[0].jobs_filhos == 1


@pytest.mark.parametrize("entrada", ["", "   ", "\n\n", None])
def test_saida_vazia_nao_gera_run(entrada):
    assert parse_logsum(entrada) == []


def test_saida_sem_nenhum_starting_job_nao_gera_run():
    assert parse_logsum("   999 INFO   Mon Jul 27 02:00:00 2026\nalgo irrelevante") == []


# ── Contagem de filhos ──────────────────────────────────────────────────────

def test_conta_filhos_disparados_e_aguardados_sem_duplicar():
    log = """
   2001 STARTED       Mon Jul 27 01:00:00 2026
Starting Job SeqMulti.
   2002 INFO          Mon Jul 27 01:00:01 2026
SeqMulti..JobControl (@Coord): -> (JobA): Job run requested
   2003 INFO          Mon Jul 27 01:00:02 2026
SeqMulti..JobControl (@Coord): -> (JobB): Job reset requested
   2004 INFO          Mon Jul 27 01:00:03 2026
SeqMulti..JobControl (@Coord): Waiting for job JobA+JobB+JobC to finish
   2005 INFO          Mon Jul 27 01:30:00 2026
SeqMulti..JobControl (@Coord): Job JobA has finished, status = 1 (Finished OK)
   2006 STARTED       Mon Jul 27 01:40:00 2026
Finished Job SeqMulti.
"""
    run = parse_logsum(log)[0]
    assert run.jobs_filhos == 3          # A e B disparados, C só aguardado
    assert run.resultado == OK


def test_filho_com_status_aborted_entra_na_lista():
    log = """
   3001 STARTED       Mon Jul 27 01:00:00 2026
Starting Job SeqMulti.
   3002 INFO          Mon Jul 27 01:10:00 2026
SeqMulti..JobControl (@Coord): Job JobA has finished, status = 3 (Aborted)
   3003 INFO          Mon Jul 27 01:11:00 2026
SeqMulti..JobControl (@Coord): Job JobB has finished, status = 3 (Aborted)
   3004 INFO          Mon Jul 27 01:12:00 2026
SeqMulti..JobControl (@Coord): sequence abort requested
"""
    run = parse_logsum(log)[0]
    assert run.resultado == ABORTADO
    assert sorted(run.filhos_abortados) == ["JobA", "JobB"]


# ── Janela de 7 dias ────────────────────────────────────────────────────────

def test_runs_desde_corta_pelo_inicio():
    runs = parse_logsum(TRES_DIAS)
    recentes = runs_desde(runs, datetime(2026, 7, 28, 0, 0, 0))
    assert len(recentes) == 2
    assert all(r.inicio >= datetime(2026, 7, 28) for r in recentes)


def test_runs_desde_descarta_run_sem_hora_legivel():
    # Run cujo cabeçalho veio corrompido: sem hora não dá para atribuir a um dia,
    # e contá-lo como "rodou" esconderia uma falha real.
    log = """
   4001 STARTED       Mon Xxx 27 02:00:00 2026
Starting Job SeqSemHora.
   4002 STARTED       Mon Xxx 27 02:30:00 2026
Finished Job SeqSemHora.
"""
    runs = parse_logsum(log)
    assert len(runs) == 1 and runs[0].inicio is None
    assert runs_desde(runs, datetime(2026, 1, 1)) == []
