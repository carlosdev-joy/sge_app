"""
Testes da F3 de docs/spec-dependencias-pipelines.md — liberação por condição e
disparo imediato.

Cobre os critérios de aceite da fase, incluindo os que só apareceriam em
produção: predecessor concluído em OUTRA data de referência, e liberação antes
da janela de início.
"""
from __future__ import annotations

import ast
import importlib.util
import sys
from datetime import date, datetime, time
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
_DAGS = _ROOT / "dags"
if str(_DAGS) not in sys.path:
    sys.path.insert(0, str(_DAGS))


def _load(name, relpath):
    spec = importlib.util.spec_from_file_location(name, _ROOT / relpath)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def dep():
    return _load("dependencias_test", "dags/utils/dependencias.py")


@pytest.fixture(scope="module")
def factory():
    return _load("etl_dag_factory_f3_test", "dags/etl_dag_factory.py")


def _src(factory, **over):
    pipe = {
        "pipeline_name": "PIPE_F3", "project_name": "BI_CVP", "domain": "T",
        "tags": "ETL", "scheduled_time": "07:00:00", "envia_msg_inicio": 0,
        "envia_msg_fim": 0, "envia_msg_erro": 1, "ambiente": "PROD",
        "schedule_type": "daily",
    }
    pipe.update(over)
    return factory._generate_dag_source(
        pipe, [{"job_name": "A", "job_type": "python", "job_command": "m",
                "execution_order": 1}])


# ───────────────────────── Condição de liberação (AND) ─────────────────────

def test_todas_concluidas_libera(dep):
    assert dep.avaliar_liberacao({"A": "SUCESSO", "B": "SUCESSO"}) == (True, [])


def test_uma_pendente_segura(dep):
    """C depende de A e B: A conclui e B não → C NÃO dispara."""
    assert dep.avaliar_liberacao({"A": "SUCESSO", "B": None}) == (False, ["B"])


def test_uma_falhou_segura(dep):
    assert dep.avaliar_liberacao({"A": "SUCESSO", "B": "FALHA"}) == (False, ["B"])


def test_predecessor_ainda_executando_segura(dep):
    assert dep.avaliar_liberacao({"A": "EXECUTANDO"}) == (False, ["A"])


def test_predecessor_pulado_segura(dep):
    """Pai pulado (blackout/dia não útil) não tem insumo para entregar.

    É o defeito 5 do QA ao contrário: o modo Dataset sumia em silêncio; aqui o
    dependente fica explicitamente aguardando, e a guardiã (F4) alerta.
    """
    assert dep.avaliar_liberacao({"A": "PULADO"}) == (False, ["A"])


def test_sem_predecessores_nao_libera(dep):
    """Lista vazia por erro de consulta não pode virar 'pode disparar'."""
    assert dep.avaliar_liberacao({}) == (False, [])


def test_pendentes_saem_ordenados(dep):
    _, pendentes = dep.avaliar_liberacao({"Z": None, "A": None, "M": "SUCESSO"})
    assert pendentes == ["A", "Z"]


# ─────────────────────────────── Janela de início ──────────────────────────

def test_sem_janela_dispara_imediato(dep):
    assert dep.dentro_da_janela(None, datetime(2026, 8, 1, 3, 0)) is True


def test_antes_da_janela_segura(dep):
    """Liberado às 07:10 com janela 08:00 → espera (a guardiã dispara depois)."""
    assert dep.dentro_da_janela(time(8, 0), datetime(2026, 8, 1, 7, 10)) is False


def test_depois_da_janela_dispara(dep):
    assert dep.dentro_da_janela(time(8, 0), datetime(2026, 8, 1, 8, 0)) is True
    assert dep.dentro_da_janela(time(8, 0), datetime(2026, 8, 1, 9, 30)) is True


def test_janela_como_texto_do_banco(dep):
    """CONVERT(VARCHAR(8), ..., 108) devolve 'HH:MM:SS'."""
    assert dep.dentro_da_janela("08:00:00", datetime(2026, 8, 1, 7, 0)) is False
    assert dep.dentro_da_janela("08:00", datetime(2026, 8, 1, 9, 0)) is True


def test_janela_invalida_nao_trava_o_disparo(dep):
    assert dep.dentro_da_janela("qualquer coisa", datetime(2026, 8, 1, 3, 0)) is True


# ─────────────────────── Consulta: data de referência ──────────────────────

def test_status_consulta_amarrada_a_data_de_referencia(dep):
    """Sucesso de ONTEM não pode liberar a corrida de HOJE."""
    hook = MagicMock()
    hook.get_records.return_value = [("PAI_A", "SUCESSO"), ("PAI_B", None)]
    resultado = dep.status_dos_predecessores(hook, "FILHO", date(2026, 8, 1))
    assert resultado == {"PAI_A": "SUCESSO", "PAI_B": None}
    sql, kwargs = hook.get_records.call_args[0][0], hook.get_records.call_args[1]
    assert "data_referencia = %s" in sql
    assert kwargs["parameters"] == (date(2026, 8, 1), "FILHO")


def test_status_usa_a_execucao_mais_recente(dep):
    """Pipeline com horários específicos roda várias vezes: vale a última."""
    hook = MagicMock()
    hook.get_records.return_value = []
    dep.status_dos_predecessores(hook, "FILHO", date(2026, 8, 1))
    sql = hook.get_records.call_args[0][0]
    assert "TOP 1" in sql and "ORDER BY" in sql and "DESC" in sql


def test_dependentes_de_filtra_por_tipo_pipeline(dep):
    """job→job (backlog) não pode ser disparado por engano quando entrar."""
    hook = MagicMock()
    hook.get_records.return_value = [("FILHO_1",), ("FILHO_2",)]
    assert dep.dependentes_de(hook, "PAI") == ["FILHO_1", "FILHO_2"]
    assert "tipo = 'PIPELINE'" in hook.get_records.call_args[0][0]


def test_config_de_pipeline_inexistente_nao_dispara(dep):
    hook = MagicMock()
    hook.get_records.return_value = []
    assert dep.config_do_dependente(hook, "SUMIU")["ativo"] is False


# ─────────────────────────────── DAG gerada ────────────────────────────────

def test_sensor_saiu_de_vez(factory):
    """O ExternalTaskSensor era o defeito 1 e 2 do QA."""
    com_dep = _src(factory, depends_on="PAI_A,PAI_B")
    assert "ExternalTaskSensor" not in com_dep
    assert "wait_PAI_A" not in com_dep


def test_pipeline_com_dependencia_nao_tem_agenda(factory):
    """Cron aqui recriaria o problema: começaria pelo relógio, não pelo insumo."""
    src = _src(factory, depends_on="PAI_A")
    ast.parse(src)
    assert "schedule=None" in src
    assert 'schedule="0 7 * * *"' not in src


def test_pipeline_sem_dependencia_mantem_o_cron(factory):
    src = _src(factory)
    ast.parse(src)
    assert 'schedule="0 7 * * *"' in src
    assert "schedule=None" not in src


def test_disparo_pendura_depois_do_sucesso(factory):
    """Só corrida marcada SUCESSO pode satisfazer a condição de alguém."""
    src = _src(factory)
    assert "t_publish_dataset >> t_exec_fim >> t_disparar_dependentes" in src


def test_disparo_herda_data_de_referencia_e_marca_origem(factory):
    src = _src(factory)
    bloco = src[src.index("def _disparar_dag"):]
    assert "'data_referencia': str(data_referencia)" in bloco
    assert "'disparado_por': PIPELINE_NAME" in bloco


def test_disparo_protege_contra_execucao_dupla(factory):
    """Guardiã e pai podem passar no mesmo instante.

    Quem consegue mudar AGUARDANDO_DEPENDENCIA → EXECUTANDO é quem dispara.
    """
    src = _src(factory)
    bloco = src[src.index("def _disparar_dag"):]
    assert "status='AGUARDANDO_DEPENDENCIA'" in bloco
    assert "rowcount" in bloco


def test_disparo_nao_derruba_o_pipeline(factory):
    """O pipeline já fez o trabalho dele; falha no disparo é problema da guardiã."""
    src = _src(factory)
    bloco = src[src.index("def disparar_dependentes"):src.index("def _disparar_dag")]
    assert "except Exception" in bloco
    assert "guardia" in bloco
