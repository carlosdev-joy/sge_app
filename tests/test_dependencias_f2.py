"""
Testes da F2 de docs/spec-dependencias-pipelines.md — registro da execução do
pipeline com data de referência.

Inspeciona a DAG GERADA (string) do mesmo jeito que test_dag_factory_decisao.py,
com o Airflow stubado via sys.modules: `_generate_dag_source` é função pura.
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
        "etl_dag_factory_f2_test", _ROOT / "dags/etl_dag_factory.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _pipeline(**over):
    base = {
        "pipeline_name": "PIPE_F2", "project_name": "BI_CVP", "domain": "TESTE",
        "tags": "ETL", "scheduled_time": "07:00:00", "envia_msg_inicio": 0,
        "envia_msg_fim": 0, "envia_msg_erro": 1, "ambiente": "PROD",
        "schedule_type": "daily",
    }
    base.update(over)
    return base


def _jobs(n=1):
    return [{"job_name": f"Job{i}", "job_type": "python", "job_command": "pkg.mod",
             "execution_order": i} for i in range(1, n + 1)]


def _src(factory, **over):
    return factory._generate_dag_source(_pipeline(**over), _jobs(2))


# ─────────────────────────────── Estrutura ─────────────────────────────────

def test_dag_gerada_compila(factory):
    ast.parse(_src(factory))


def test_tres_tasks_de_execucao_presentes(factory):
    src = _src(factory)
    for task in ("registrar_inicio", "registrar_fim", "registrar_falha"):
        assert f'task_id="{task}"' in src, f"task {task} ausente"


def test_default_args_nao_referencia_helper(factory):
    """As constantes são emitidas ANTES dos helpers no arquivo gerado.

    Pôr a função de falha em default_args daria NameError no import da DAG —
    erro que só apareceria no Airflow, nunca no pytest de geração.
    """
    src = _src(factory)
    consts = src[:src.index("def _registrar_execucao")]
    assert "registrar_falha" not in consts
    assert "on_failure_callback" not in consts


def test_registro_inicia_depois_do_check_agenda(factory):
    """Corrida pulada não pode virar EXECUTANDO que nunca termina."""
    src = _src(factory)
    assert "t_check_agenda >> t_exec_inicio" in src
    # E o primeiro job pendura no registro, não mais no check direto.
    assert "t_exec_inicio >> t_start_Job1" in src


def test_sucesso_pendura_no_ponto_de_convergencia(factory):
    src = _src(factory)
    assert "t_publish_dataset >> t_exec_fim" in src


def test_falha_pendura_nos_fins_de_ramo_com_one_failed(factory):
    """ONE_FAILED só enxerga upstream DIRETO.

    Pendurar a task de falha apenas no publish_dataset a deixaria cega: numa
    falha o publish nem chega a rodar.
    """
    src = _src(factory)
    assert ">> t_exec_falha" in src
    bloco = src[src.index("t_exec_falha = PythonOperator("):]
    assert "TriggerRule.ONE_FAILED" in bloco[:300]


def test_pipeline_com_decisao_tolera_ramo_pulado_no_sucesso(factory):
    """Convergência com ramos pulados: ALL_SUCCESS marcaria FALHA sem falha."""
    import json
    jobs = [
        {"job_name": "A", "job_type": "python", "job_command": "m", "execution_order": 1},
        {"job_name": "Dec", "job_type": "decisao", "job_command": "m", "execution_order": 2,
         "depends_on_jobs": "A",
         "condition_json": json.dumps({"tipo": "contagem", "tabela": "dbo.T",
                                       "operador": ">", "valor": 1,
                                       "ramo_verdadeiro": ["B"], "ramo_falso": ["C"]})},
        {"job_name": "B", "job_type": "python", "job_command": "m", "execution_order": 3,
         "depends_on_jobs": ""},
        {"job_name": "C", "job_type": "python", "job_command": "m", "execution_order": 4,
         "depends_on_jobs": ""},
    ]
    src = factory._generate_dag_source(_pipeline(pipeline_name="PIPE_DEC"), jobs)
    ast.parse(src)
    bloco = src[src.index("t_exec_fim = PythonOperator("):]
    assert "NONE_FAILED_MIN_ONE_SUCCESS" in bloco[:300]


# ──────────────────────────── Data de referência ───────────────────────────

def test_heranca_tem_precedencia_sobre_o_calculo(factory):
    """Quem é disparado por dependência NÃO recalcula: herda do predecessor."""
    src = _src(factory)
    bloco = src[src.index("def _data_referencia"):src.index("def _registrar_execucao")]
    assert "conf.get('data_referencia')" in bloco
    # A herança é lida ANTES de qualquer consulta de virada.
    assert bloco.index("_herdada") < bloco.index("SELECT COALESCE")


def test_usa_horario_agendado_e_nao_o_relogio(factory):
    """Atraso de fila não pode empurrar a corrida para outra data."""
    src = _src(factory)
    bloco = src[src.index("def _momento_logico"):src.index("def _data_referencia")]
    assert "data_interval_end" in bloco and "logical_date" in bloco


def test_registro_degrada_sem_a_migration_067(factory):
    """Deploy que leva dags/ sem a 067 não pode derrubar uma carga que rodou."""
    src = _src(factory)
    bloco = src[src.index("def _registrar_execucao"):src.index("def registrar_inicio")]
    assert "except Exception" in bloco
    assert "migration 067" in bloco


def test_pulado_registrado_por_wrapper_e_nao_por_return(factory):
    """São 5 caminhos de saída no check_agenda; instrumentar cada um perderia um.

    Corrida sem registro nenhum é indistinguível de 'nunca foi ordenada' — que
    é exatamente o que a guardiã da F4 vai procurar.
    """
    src = _src(factory)
    assert "def _check_agenda_regras(**context):" in src
    assert "def check_agenda(**context):" in src
    wrapper = src[src.index("def check_agenda(**context):"):]
    assert "'PULADO'" in wrapper[:400]
    assert "_check_agenda_regras(**context)" in wrapper[:400]


def test_import_de_datetime_presente(factory):
    """_registrar_execucao usa datetime.now() no INSERT."""
    src = _src(factory)
    assert "from datetime import datetime, timedelta" in src
