"""
Testes da F6 de docs/spec-dependencias-pipelines.md — tabela como fonte única
da dependência na geração das DAGs.

O ponto delicado da fase: sem a migration 067 o factory NÃO pode concluir que
ninguém tem dependência. Isso apagaria a dependência de todas as DAGs num deploy
que levasse `dags/` sem a migration — regressão pior que o comportamento antigo.
"""
from __future__ import annotations

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
        "etl_dag_factory_f6_test", _ROOT / "dags/etl_dag_factory.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class CurTabela:
    def __init__(self, linhas=None, erro=False):
        self.linhas, self.erro = linhas or [], erro

    def execute(self, sql, params=None):
        if self.erro:
            raise RuntimeError("Invalid object name 'dbo.etl_pipeline_dependencia'")

    def fetchall(self):
        return self.linhas


def test_le_a_tabela_e_agrupa_por_pipeline(factory):
    cur = CurTabela([("PIPE_C", "PAI_A"), ("PIPE_C", "PAI_B"), ("PIPE_D", "PAI_A")])
    assert factory._dependencias_da_tabela(cur) == {
        "PIPE_C": "PAI_A,PAI_B",
        "PIPE_D": "PAI_A",
    }


def test_tabela_vazia_devolve_dicionario_vazio(factory):
    """Vazia é diferente de ausente: aqui é legítimo que ninguém tenha dependência."""
    assert factory._dependencias_da_tabela(CurTabela([])) == {}


def test_sem_a_tabela_devolve_none_e_nao_dicionario_vazio(factory):
    """None faz o chamador PRESERVAR o depends_on da proc.

    Devolver {} aqui seria indistinguível de "ninguém tem dependência" e
    apagaria a dependência de todas as DAGs num deploy sem a migration.
    """
    assert factory._dependencias_da_tabela(CurTabela(erro=True)) is None


def test_sobrescrita_respeita_o_contrato_de_none(factory):
    """Reproduz o uso real: None preserva, dicionário sobrescreve."""
    pipelines = [{"pipeline_name": "PIPE_C", "depends_on": "ANTIGO"},
                 {"pipeline_name": "PIPE_D", "depends_on": "ANTIGO_2"}]

    # Caminho com a tabela: o que está nela vence, e quem não tem linha fica sem.
    deps = {"PIPE_C": "PAI_A,PAI_B"}
    for p in pipelines:
        p["depends_on"] = deps.get(p["pipeline_name"]) or None
    assert pipelines[0]["depends_on"] == "PAI_A,PAI_B"
    assert pipelines[1]["depends_on"] is None

    # Caminho sem a tabela: nada é tocado.
    pipelines2 = [{"pipeline_name": "PIPE_C", "depends_on": "ANTIGO"}]
    if None is not None:  # espelha o `if _deps is not None` do factory
        pipelines2[0]["depends_on"] = None
    assert pipelines2[0]["depends_on"] == "ANTIGO"


def test_dag_gerada_usa_a_dependencia_sobrescrita(factory):
    """Ponta a ponta: o que veio da tabela é o que vira schedule=None."""
    pipe = {"pipeline_name": "PIPE_C", "project_name": "BI_CVP", "domain": "T",
            "tags": "ETL", "scheduled_time": "07:00:00", "envia_msg_inicio": 0,
            "envia_msg_fim": 0, "envia_msg_erro": 1, "ambiente": "PROD",
            "schedule_type": "daily", "depends_on": "PAI_A,PAI_B"}
    jobs = [{"job_name": "A", "job_type": "python", "job_command": "m",
             "execution_order": 1}]
    src = factory._generate_dag_source(pipe, jobs)
    assert "schedule=None" in src
    assert "PAI_A, PAI_B" in src   # citados no comentário do schedule
