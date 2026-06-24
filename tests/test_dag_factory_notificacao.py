"""
Testes do nó de Notificação (Teams) gerado pelo etl_dag_factory.

Mesmo princípio dos demais testes de factory: módulos do Airflow stubados via
sys.modules antes do import; _generate_dag_source é função pura (gera string a
partir de dicts).

Regressão principal (test_job_que_depende_de_notificacao_usa_t_notif): um job que
DEPENDE de um nó de notificação deve referenciar t_notif_<dep> — a notificação
NÃO tem t_end_ próprio. Antes gerava `NameError: name 't_end_<notif>' is not
defined` quando o Airflow importava a DAG (o ast.parse da factory não pega, pois
é erro de tempo de carga). Por isso os testes EXECUTAM a fonte (com utils
stubados), espelhando o import real do Airflow.
"""
from __future__ import annotations

import ast
import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_AIRFLOW_STUBS = [
    "airflow", "airflow.models", "airflow.operators", "airflow.operators.python",
    "airflow.operators.empty", "airflow.datasets", "airflow.utils",
    "airflow.utils.trigger_rule", "airflow.utils.state",
    "airflow.providers", "airflow.providers.microsoft", "airflow.providers.microsoft.mssql",
    "airflow.providers.microsoft.mssql.hooks", "airflow.providers.microsoft.mssql.hooks.mssql",
    "pendulum", "requests",
]
for _mod in _AIRFLOW_STUBS:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

_ROOT = Path(__file__).parent.parent


def _load_module(name, relpath):
    path = _ROOT / relpath
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def factory():
    return _load_module("etl_dag_factory_notif_test", "dags/etl_dag_factory.py")


def _pipeline(**overrides):
    base = {
        "pipeline_name": "PIPE_NOTIF", "project_name": "BI_CVP", "domain": "TESTE",
        "tags": "ETL", "scheduled_time": "06:00:00",
        "envia_msg_inicio": 0, "envia_msg_fim": 1, "envia_msg_erro": 1,
        "ambiente": "PROD", "schedule_type": "daily",
    }
    base.update(overrides)
    return base


def _job(name, jtype="datastage", order=1, depends=None, notify=None):
    j = {"job_name": name, "job_type": jtype, "job_command": "ds.job",
         "execution_order": order}
    if depends is not None:
        j["depends_on_jobs"] = depends
    if notify is not None:
        j["notify_json"] = json.dumps(notify)
    return j


_NOTIFY = {"grupo_id": 1, "template_id": None, "mensagem": "linhas {linhas}"}


def _exec_source(src):
    """Importa DE FATO a DAG gerada — pega NameError de tempo de carga, que é o
    que o Airflow faria ao importar o arquivo .py. Stuba ``utils.*`` SÓ durante o
    exec (e restaura), para não poluir a coleção de outros testes que importam o
    ``utils`` real (ex.: utils.dsx_engine)."""
    util_mods = ("utils", "utils.datastage_operator", "utils.conditions", "utils.job_operators")
    saved = {m: sys.modules.get(m) for m in util_mods}
    try:
        for m in util_mods:
            sys.modules[m] = MagicMock()
        exec(compile(src, "<dag>", "exec"), {})
    finally:
        for m, prev in saved.items():
            if prev is None:
                sys.modules.pop(m, None)
            else:
                sys.modules[m] = prev


def test_notificacao_terminal_compila_e_importa(factory):
    jobs = [_job("JobA"),
            _job("Notif", jtype="notificacao", order=2, depends="JobA", notify=_NOTIFY)]
    src = factory._generate_dag_source(_pipeline(), jobs)
    ast.parse(src)
    _exec_source(src)
    assert "t_notif_Notif = PythonOperator(" in src
    # notificação não entra em end_tasks (não tem t_end_ próprio)
    assert "t_end_Notif" not in src


def test_job_que_depende_de_notificacao_usa_t_notif(factory):
    """Regressão: JobB depende da notificação Notif → o wiring usa t_notif_Notif,
    NÃO t_end_Notif (inexistente → NameError no import do Airflow)."""
    jobs = [
        _job("JobA"),
        _job("Notif", jtype="notificacao", order=2, depends="JobA", notify=_NOTIFY),
        _job("JobB", order=3, depends="Notif"),
    ]
    src = factory._generate_dag_source(_pipeline(), jobs)
    ast.parse(src)
    _exec_source(src)  # NameError de carga aqui se regredir
    assert "t_notif_Notif >> t_start_JobB" in src
    assert "t_end_Notif" not in src


def test_notificacao_depende_de_notificacao(factory):
    """N2 depende de N1 (ambas notificação) → N1 conclui em t_notif_N1."""
    jobs = [
        _job("JobA"),
        _job("N1", jtype="notificacao", order=2, depends="JobA", notify=_NOTIFY),
        _job("N2", jtype="notificacao", order=3, depends="N1", notify=_NOTIFY),
    ]
    src = factory._generate_dag_source(_pipeline(), jobs)
    ast.parse(src)
    _exec_source(src)
    assert "t_notif_N1 >> t_notif_N2" in src
