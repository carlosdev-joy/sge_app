"""
Pipeline "Sob demanda" (schedule_type='on_demand').

O tipo existia só na tela: a API e o gerador não o conheciam e ele caía no
fallback `"{m} {h} * * *"`, com o horário PADRÃO do formulário. Resultado: o
pipeline que o usuário pediu manual nascia agendado para todo dia às 06:00.

Correção: cron None → `schedule=None` na DAG, que no Airflow é uma DAG ATIVA e
visível, disparável apenas pelo botão Executar.
"""
from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

for _mod in [
    "airflow", "airflow.decorators", "airflow.models", "airflow.operators",
    "airflow.operators.python", "airflow.operators.empty", "airflow.operators.bash",
    "airflow.providers.microsoft.mssql.hooks.mssql", "airflow.utils",
    "airflow.utils.trigger_rule", "airflow.sensors.external_task", "airflow.datasets",
    "pendulum", "airflow.providers.ssh.hooks.ssh", "airflow.utils.dates",
    "airflow.exceptions",
]:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

_ROOT = Path(__file__).parent.parent


@pytest.fixture(scope="module")
def factory():
    spec = importlib.util.spec_from_file_location(
        "etl_dag_factory_ondemand_test", _ROOT / "dags/etl_dag_factory.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def pipes():
    for m in ["pyodbc", "fastapi", "fastapi.responses", "pydantic", "httpx"]:
        sys.modules.setdefault(m, MagicMock())
    sys.path.insert(0, str(_ROOT / "api"))
    spec = importlib.util.spec_from_file_location(
        "pipelines_ondemand_test", _ROOT / "api/routers/pipelines.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _pipeline(**over):
    base = {
        "pipeline_name": "PIPE_MANUAL", "project_name": "BI_CVP", "domain": "T",
        "tags": "ETL", "scheduled_time": "06:00:00", "schedule_hour": 6,
        "schedule_minute": 0, "envia_msg_inicio": 0, "envia_msg_fim": 0,
        "envia_msg_erro": 1, "ambiente": "PROD",
    }
    base.update(over)
    return base


def _src(factory, **over):
    return factory._generate_dag_source(
        _pipeline(**over), [{"job_name": "A", "job_type": "python",
                             "job_command": "m", "execution_order": 1}])


# ───────────────────────────── O defeito ───────────────────────────────────

def test_sob_demanda_nao_tem_cron(factory):
    """Era aqui que 'on_demand' virava um cron diário com o horário padrão."""
    cron, horarios, dias = factory._build_cron(_pipeline(schedule_type="on_demand"))
    assert cron is None
    assert horarios is None
    assert dias is None


def test_sob_demanda_ignora_o_horario_herdado_do_formulario(factory):
    """O formulário nasce com 06:00 e mantém o valor ao trocar de tipo.

    Mesmo recebendo um horário qualquer, sob demanda não pode gerar cron.
    """
    for hora in ("06:00:00", "23:45:00", "00:00:00"):
        cron, _, _ = factory._build_cron(
            _pipeline(schedule_type="on_demand", scheduled_time=hora))
        assert cron is None, hora


def test_dag_sob_demanda_usa_schedule_none(factory):
    src = _src(factory, schedule_type="on_demand")
    ast.parse(src)
    linhas = [l.strip() for l in src.splitlines() if l.strip().startswith("schedule=")]
    assert len(linhas) == 1
    assert linhas[0].startswith("schedule=None")


def test_dag_sob_demanda_continua_ativa_e_completa(factory):
    """`schedule=None` tira o gatilho, não a DAG: ela fica listada e executável."""
    src = _src(factory, schedule_type="on_demand")
    assert "t_check_agenda" in src        # a moldura continua
    assert "t_job_A" in src               # os jobs continuam
    assert "is_paused" not in src         # nada pausa a DAG
    assert "catchup=False" in src


# ────────────────────── Os outros tipos não regridem ───────────────────────

def test_demais_tipos_mantem_o_cron(factory):
    casos = [
        ({"schedule_type": "daily"}, "0 6 * * *"),
        ({"schedule_type": "weekly", "schedule_dow": 3}, "0 6 * * 3"),
        ({"schedule_type": "monthly", "schedule_dom": 5}, "0 6 5 * *"),
        ({"schedule_type": "biweekly", "schedule_dom": 2}, "0 6 2,17 * *"),
        ({"schedule_type": "hourly"}, "0 * * * *"),
    ]
    for extra, esperado in casos:
        cron, _, _ = factory._build_cron(_pipeline(**extra))
        assert cron == esperado, extra


def test_tipo_desconhecido_continua_no_fallback_diario(factory):
    """Só 'on_demand' perde o cron — tipo estranho segue com o padrão de antes."""
    cron, _, _ = factory._build_cron(_pipeline(schedule_type="coisa_nova"))
    assert cron == "0 6 * * *"


def test_dag_agendada_continua_com_cron(factory):
    src = _src(factory, schedule_type="daily")
    linhas = [l.strip() for l in src.splitlines() if l.strip().startswith("schedule=")]
    assert linhas == ['schedule="0 6 * * *",']


# ────────────────────────────── Lado da API ────────────────────────────────

def test_api_devolve_cron_nulo_para_sob_demanda(pipes):
    """A resposta do cadastro precisa contar a mesma história que a DAG."""
    assert pipes._build_cron("on_demand", 6, 0, None, None) is None


def test_api_mantem_o_cron_dos_demais(pipes):
    assert pipes._build_cron("daily", 6, 0, None, None) == "0 6 * * *"
    assert pipes._build_cron("weekly", 6, 0, 3, None) == "0 6 * * 3"
    assert pipes._build_cron(None, 6, 0, None, None) == "0 6 * * *"
