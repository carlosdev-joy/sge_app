"""
Testes do job SHELL gerado pelo etl_dag_factory.

Regressão do bug do shlex.quote: comando sem caractere especial (path puro,
palavra única — o caso MAIS comum) era emitido SEM aspas no código gerado e a
DAG quebrava no import (SyntaxError/NameError). O contrato correto:

  - o comando vira um LITERAL Python (repr) — byte a byte o que o usuário digitou;
  - o operador é ShellOperator (SSHOperator): executa o comando VIA SSH no
    servidor do ssh_conn_id do JOB; sem ssh_conn_id, cai no SSH_CONN_ID do
    pipeline (default global).

Mesmo padrão dos testes vizinhos: Airflow stubado em sys.modules e
_generate_dag_source tratada como função pura.
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
    spec = importlib.util.spec_from_file_location("etl_dag_factory_shell_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _pipeline(**overrides):
    base = {
        "pipeline_name": "PIPE_SHELL", "project_name": "BI_CVP", "domain": "TESTE",
        "tags": "ETL", "scheduled_time": "06:00:00",
        "envia_msg_inicio": 0, "envia_msg_fim": 1, "envia_msg_erro": 1,
        "ambiente": "PROD", "schedule_type": "daily",
    }
    base.update(overrides)
    return base


def _shell_job(cmd, ssh=None, name="SH_1"):
    j = {"job_name": name, "job_type": "shell", "job_command": cmd, "execution_order": 1}
    if ssh is not None:
        j["ssh_conn_id"] = ssh
    return j


def _extrai_kwargs_shell(src: str, task_var: str) -> dict:
    """Extrai (via AST) os kwargs do ShellOperator do código gerado — prova que
    o literal chega EXATAMENTE como o usuário digitou, sem depender de grep."""
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if (isinstance(node, ast.Assign) and node.targets
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == task_var
                and isinstance(node.value, ast.Call)):
            out = {}
            for kw in node.value.keywords:
                out[kw.arg] = (ast.literal_eval(kw.value)
                               if isinstance(kw.value, ast.Constant) else kw.value)
            return out
    raise AssertionError(f"{task_var} não encontrado no código gerado")


# ── Regressão do shlex.quote ─────────────────────────────────────────────────

@pytest.mark.parametrize("cmd", [
    "/opt/scripts/run.sh",          # path puro (o placeholder da UI!) — quebrava com SyntaxError
    "ls",                           # palavra única — quebrava com NameError no import
    "/opt/scripts/run.sh --full",   # com espaço — já funcionava (por acidente)
    "echo 'oi mundo'",              # aspas simples embutidas
    'echo "a" && ./x.sh $VAR | tee /tmp/l.log',  # metacaracteres de shell
])
def test_comando_vira_literal_python_fiel(factory, cmd):
    src = factory._generate_dag_source(_pipeline(), [_shell_job(cmd)])
    ast.parse(src)  # SyntaxError se o literal estiver malformado
    kwargs = _extrai_kwargs_shell(src, "t_job_SH_1")
    # byte a byte o que o usuário digitou — o shell REMOTO é quem interpreta
    assert kwargs["command"] == cmd


def test_comando_vazio_usa_placeholder(factory):
    src = factory._generate_dag_source(_pipeline(), [_shell_job("")])
    kwargs = _extrai_kwargs_shell(src, "t_job_SH_1")
    assert kwargs["command"] == "echo 'comando nao configurado'"


# ── Servidor de execução (ssh_conn_id) ───────────────────────────────────────

def test_usa_ssh_conn_id_do_job(factory):
    src = factory._generate_dag_source(
        _pipeline(), [_shell_job("/opt/x.sh", ssh="ssh_servidor_x")])
    kwargs = _extrai_kwargs_shell(src, "t_job_SH_1")
    assert kwargs["ssh_conn_id"] == "ssh_servidor_x"
    assert "ShellOperator" in src and "from utils.job_operators import" in src


def test_sem_ssh_do_job_cai_no_default_do_pipeline(factory):
    src = factory._generate_dag_source(_pipeline(), [_shell_job("/opt/x.sh")])
    kwargs = _extrai_kwargs_shell(src, "t_job_SH_1")
    # referência à constante do módulo gerado (não string) = default do pipeline
    assert isinstance(kwargs["ssh_conn_id"], ast.Name)
    assert kwargs["ssh_conn_id"].id == "SSH_CONN_ID"
    assert 'SSH_CONN_ID   = "ssh_lnxprd021"' in src


def test_ssh_conn_id_do_pipeline_respeitado(factory):
    src = factory._generate_dag_source(
        _pipeline(ssh_conn_id="ssh_outro_srv"), [_shell_job("/opt/x.sh")])
    assert 'SSH_CONN_ID   = "ssh_outro_srv"' in src
