"""
Testes do ShellOperator (job shell — execução via SSH no servidor escolhido).

Regressão do incidente SHELL_LIMPA_FS_DATASTAGE (2026-07-07): o SSHOperator
herda ``template_ext=('.sh',)`` e o Airflow trata campo templated que TERMINA
em .sh como CAMINHO de template Jinja — um comando legítimo como
``cd /x && ./script.sh`` morria com TemplateNotFound no render. O contrato do
Orquestra: comando é SEMPRE string inline (``template_ext = ()``), e as macros
``{{ ds }}`` seguem disponíveis (``template_fields`` intacto).

Airflow não está instalado no ambiente de teste — stub mínimo antes do import
(mesmo padrão do test_ds_operator.py).
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

_ROOT = Path(__file__).parent.parent


def _ensure_module(name: str) -> types.ModuleType:
    mod = sys.modules.get(name)
    if mod is None:
        mod = types.ModuleType(name)
        sys.modules[name] = mod
        if "." in name:
            parent, _, child = name.rpartition(".")
            setattr(_ensure_module(parent), child, mod)
    return mod


def _stub_airflow():
    _ensure_module("airflow")
    _ensure_module("airflow.exceptions").AirflowException = type(
        "AirflowException", (Exception,), {})
    _ensure_module("airflow.models").BaseOperator = type(
        "BaseOperator", (), {"__init__": lambda self, *a, **k: None})
    _ensure_module("airflow.providers.microsoft.mssql.hooks.mssql").MsSqlHook = type(
        "MsSqlHook", (), {})

    # SSHOperator FIEL no que importa: template_fields/template_ext do provider
    # real (command templated; .sh como extensão de template) — é exatamente o
    # comportamento que o ShellOperator precisa neutralizar.
    class _FakeSSHOperator:
        template_fields = ("command", "environment", "remote_host")
        template_ext = (".sh",)

        def __init__(self, *a, **k):
            pass

    _ensure_module("airflow.providers.ssh.operators.ssh").SSHOperator = _FakeSSHOperator


@pytest.fixture(scope="module")
def job_operators():
    _stub_airflow()
    path = _ROOT / "dags/utils/job_operators.py"
    spec = importlib.util.spec_from_file_location("job_operators_shell_test", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("utils", types.ModuleType("utils"))
    spec.loader.exec_module(mod)
    return mod


def test_template_ext_vazio_comando_terminando_em_sh_nao_vira_arquivo(job_operators):
    # A raiz do TemplateNotFound: com ('.sh',) o Airflow carrega o comando como
    # ARQUIVO de template. Vazio = comando é sempre string inline.
    assert job_operators.ShellOperator.template_ext == ()


def test_command_continua_templated_para_macros(job_operators):
    # Macros {{ ds }} dentro da STRING seguem renderizando (só a interpretação
    # como arquivo morre) — template_fields herdado intacto.
    assert "command" in job_operators.ShellOperator.template_fields


def test_e_subclasse_do_ssh_operator(job_operators):
    # Executa via SSH no servidor do ssh_conn_id — herança direta.
    from airflow.providers.ssh.operators.ssh import SSHOperator
    assert issubclass(job_operators.ShellOperator, SSHOperator)
