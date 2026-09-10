"""
Bloco DataStage gerado pelo etl_dag_factory (F2 da spec
docs/spec-parametros-job-datastage.md).

O que se prende: o operador recebe `pipeline_name=PIPELINE_NAME` (constante do
módulo gerado) — é a chave com que ele lê etl_pipeline_job_param em runtime —
e NENHUM parâmetro entra no código gerado (a decisão da spec é leitura em
runtime, não embutir na DAG). Os demais kwargs seguem como antes.

Mesmo padrão de tests/test_dag_factory_shell.py: Airflow stubado, fonte
gerada analisada por AST.
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

_ROOT = Path(__file__).parent.parent


@pytest.fixture(scope="module")
def factory():
    path = _ROOT / "dags/etl_dag_factory.py"
    spec = importlib.util.spec_from_file_location("etl_dag_factory_ds_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _pipeline(**overrides):
    base = {
        "pipeline_name": "PIPE_DS", "project_name": "BI_VIDA", "domain": "TESTE",
        "tags": "ETL", "scheduled_time": "06:00:00",
        "envia_msg_inicio": 0, "envia_msg_fim": 1, "envia_msg_erro": 1,
        "ambiente": "PROD", "schedule_type": "daily", "criticidade": "Alta",
    }
    base.update(overrides)
    return base


def _ds_job(name="SeqCarga", **extra):
    j = {"job_name": name, "job_type": "datastage", "job_command": name, "execution_order": 1,
         "params": [{"param_name": "pData", "param_type": "Date", "param_value": None,
                     "param_source": "data_referencia"}]}
    j.update(extra)
    return j


def _kwargs(src: str, task_var: str) -> dict:
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if (isinstance(node, ast.Assign) and node.targets
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == task_var
                and isinstance(node.value, ast.Call)):
            return {kw.arg: kw.value for kw in node.value.keywords}
    raise AssertionError(f"{task_var} não encontrado no código gerado")


def test_operador_recebe_pipeline_name_como_constante(factory):
    src = factory._generate_dag_source(_pipeline(), [_ds_job()])
    ast.parse(src)
    kw = _kwargs(src, "t_job_SeqCarga")
    assert isinstance(kw["pipeline_name"], ast.Name) and kw["pipeline_name"].id == "PIPELINE_NAME"
    assert 'PIPELINE_NAME = "PIPE_DS"' in src


def test_demais_kwargs_seguem_como_antes(factory):
    src = factory._generate_dag_source(_pipeline(), [_ds_job()])
    kw = _kwargs(src, "t_job_SeqCarga")
    assert kw["project"].id == "PROJECT_NAME"
    assert kw["ssh_conn_id"].id == "SSH_CONN_ID"
    assert kw["queue_name"].id == "DS_QUEUE"
    assert ast.literal_eval(kw["job_name"]) == "SeqCarga"
    assert ast.literal_eval(kw["task_id"]) == "SeqCarga"
    assert "verbose_log" not in kw
    assert 'DS_QUEUE      = \'HighPriorityJobs\'' in src


def test_verbose_log_continua_opcional(factory):
    src = factory._generate_dag_source(_pipeline(), [_ds_job(verbose_log=1)])
    kw = _kwargs(src, "t_job_SeqCarga")
    assert ast.literal_eval(kw["verbose_log"]) is True


def test_nenhum_parametro_entra_no_codigo_gerado(factory):
    """Leitura em runtime: a lista `params` do job (que a fábrica carrega para o
    storedproc) NÃO vira kwarg nem literal no bloco datastage."""
    src = factory._generate_dag_source(_pipeline(), [_ds_job()])
    kw = _kwargs(src, "t_job_SeqCarga")
    assert "params" not in kw and "proc_params" not in kw and "execution_date_param" not in kw
    assert "pData" not in src and "data_referencia" not in src.split("t_job_SeqCarga = DataStageOperator(")[1].split(")")[0]
