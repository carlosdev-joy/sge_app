"""
Testes para a tradução de 'monthly_days_times' em DAGs gerados pelo etl_dag_factory.
Os módulos do Airflow não estão instalados neste ambiente de teste — são
stubados via sys.modules antes do import, mesmo princípio do mock de pyodbc
em tests/conftest.py. _build_cron e _generate_dag_source são funções puras
(constroem strings a partir de dicts), não tocam Airflow/banco em runtime.
"""
from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_AIRFLOW_STUBS = [
    "airflow", "airflow.models", "airflow.operators", "airflow.operators.python",
    "airflow.providers", "airflow.providers.microsoft", "airflow.providers.microsoft.mssql",
    "airflow.providers.microsoft.mssql.hooks", "airflow.providers.microsoft.mssql.hooks.mssql",
    "pendulum",
]
for _mod in _AIRFLOW_STUBS:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()


def _load_factory():
    path = Path(__file__).parent.parent / "dags" / "etl_dag_factory.py"
    spec = importlib.util.spec_from_file_location("etl_dag_factory_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def factory():
    return _load_factory()


def _base_pipeline(**overrides):
    base = {
        "pipeline_name": "TESTE_MDT", "project_name": "BI_CVP", "domain": "TESTE",
        "tags": "ETL", "scheduled_time": "06:00:00",
        "envia_msg_inicio": 0, "envia_msg_fim": 0, "envia_msg_erro": 0,
        "ambiente": "DEV", "schedule_type": "monthly_days_times",
        "horarios_especificos": None, "dias_semana": None,
    }
    base.update(overrides)
    return base


def _job():
    return {"job_name": "job_teste", "job_type": "python", "job_command": "pkg.mod", "execution_order": 1}


def test_build_cron_monthly_days_times_superset(factory):
    pipeline = _base_pipeline(dias_horarios_mes=(
        '[{"dia": 1, "horarios": ["09:00"]}, '
        '{"dia": 15, "horarios": ["14:00", "18:00"]}, '
        '{"dia": 28, "horarios": ["10:00"]}]'
    ))
    cron, horarios_list, dias_horarios = factory._build_cron(pipeline)
    assert cron == "0 9,10,14,18 1,15,28 * *"
    assert horarios_list is None
    assert dias_horarios == {1: ["09:00"], 15: ["14:00", "18:00"], 28: ["10:00"]}


def test_build_cron_other_types_return_none_dias_horarios(factory):
    pipeline = _base_pipeline(schedule_type="daily", dias_horarios_mes=None)
    cron, horarios_list, dias_horarios = factory._build_cron(pipeline)
    assert dias_horarios is None
    assert cron == "0 6 * * *"


def test_build_cron_custom_type_unaffected(factory):
    pipeline = _base_pipeline(schedule_type="custom", dias_horarios_mes=None,
                               horarios_especificos="09:00,10:30", dias_semana="1,3,5")
    cron, horarios_list, dias_horarios = factory._build_cron(pipeline)
    assert dias_horarios is None
    assert horarios_list == ["09:00", "10:30"]
