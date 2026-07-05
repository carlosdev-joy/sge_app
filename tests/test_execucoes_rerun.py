"""
Testes do casamento execução→dag_run do POST /execucoes/rerun.

Funções puras de api/routers/execucoes.py: _iso_to_ts_nodash (converte a
logical date ISO do Airflow para o formato ts_nodash usado como execution_id
na telemetria) e _escolhe_dag_run (match por ts_nodash com fallback legado).

Mesmo padrão de test_jobs_decisao.py: o módulo do router é importado via
fixture (depois do app), nunca no topo.
"""
from __future__ import annotations

import pytest


@pytest.fixture(scope="module")
def E():
    import routers.execucoes as _e
    return _e


# ─────────────────────────── _iso_to_ts_nodash ──────────────────────────────

@pytest.mark.parametrize("iso,esperado", [
    ("2026-07-05T03:00:00+00:00", "20260705T030000"),
    ("2026-07-05T03:00:00.123456+00:00", "20260705T030000"),
    ("2026-07-05T03:00:00Z", "20260705T030000"),
    ("2026-07-05 03:00:00", "20260705 030000"),   # separador espaço não é o formato do Airflow
    ("", ""),
])
def test_iso_to_ts_nodash(E, iso, esperado):
    assert E._iso_to_ts_nodash(iso) == esperado


def test_iso_to_ts_nodash_none(E):
    assert E._iso_to_ts_nodash(None) == ""


# ─────────────────────────── _escolhe_dag_run ───────────────────────────────

_RUNS = [
    {"dag_run_id": "scheduled__hoje", "logical_date": "2026-07-05T06:00:00+00:00",
     "state": "running"},
    {"dag_run_id": "scheduled__ontem", "logical_date": "2026-07-04T06:00:00+00:00",
     "state": "failed"},
    {"dag_run_id": "scheduled__anteontem", "logical_date": "2026-07-03T06:00:00+00:00",
     "state": "success"},
]


def test_escolhe_run_pelo_execution_id(E):
    """Match por ts_nodash vence, mesmo não sendo o 1º terminado da lista."""
    run = E._escolhe_dag_run(_RUNS, "20260703T060000")
    assert run["dag_run_id"] == "scheduled__anteontem"


def test_escolhe_run_de_hoje_mesmo_rodando(E):
    """O run casado é escolhido mesmo em estado running (era o bug: pegava o
    1º failed/success — o de ONTEM — e limpava o run errado)."""
    run = E._escolhe_dag_run(_RUNS, "20260705T060000")
    assert run["dag_run_id"] == "scheduled__hoje"


def test_sem_match_cai_no_fallback_legado(E):
    run = E._escolhe_dag_run(_RUNS, "20990101T000000")
    assert run["dag_run_id"] == "scheduled__ontem"   # 1º failed/success


def test_sem_exec_id_usa_fallback(E):
    run = E._escolhe_dag_run(_RUNS, "")
    assert run["dag_run_id"] == "scheduled__ontem"


def test_sem_terminados_usa_mais_recente(E):
    runs = [{"dag_run_id": "r1", "logical_date": "2026-07-05T06:00:00+00:00", "state": "running"}]
    assert E._escolhe_dag_run(runs, "20990101T000000")["dag_run_id"] == "r1"
