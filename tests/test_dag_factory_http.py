"""
Testes do tipo de etapa `http` (HttpCallOperator) — destravado de ponta a ponta.

Mesmo princípio de test_dag_factory_sql_node.py: módulos do Airflow stubados via
sys.modules antes do import; _generate_dag_source é função pura; EXECUTAMOS a
fonte gerada para pegar erros de tempo de carga. Também cobre a validação de URL
do backend (_valid_http_url em api/routers/jobs.py).
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
    return _load_module("etl_dag_factory_http_test", "dags/etl_dag_factory.py")


def _pipeline(**overrides):
    base = {
        "pipeline_name": "PIPE_HTTP", "project_name": "BI_CVP", "domain": "TESTE",
        "tags": "ETL", "scheduled_time": "06:00:00",
        "envia_msg_inicio": 0, "envia_msg_fim": 1, "envia_msg_erro": 1,
        "ambiente": "PROD", "schedule_type": "daily",
    }
    base.update(overrides)
    return base


def _job(name, jtype="datastage", order=1, cmd="ds.job", depends=None):
    j = {"job_name": name, "job_type": jtype, "job_command": cmd,
         "execution_order": order}
    if depends is not None:
        j["depends_on_jobs"] = depends
    return j


def _exec_source(src):
    """Importa DE FATO a DAG gerada — pega NameError de tempo de carga."""
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


# ───────────────────────────── DAG gerada ──────────────────────────────────

def test_http_compila_e_importa_com_trio_de_telemetria(factory):
    # JobB a jusante do http: garante que t_end_CHAMA_API existe e é referenciado
    # (a classe de NameError que o _exec_source pega no import da DAG).
    jobs = [_job("JobA"),
            _job("CHAMA_API", jtype="http", order=2,
                 cmd="https://servidor.interno/api/disparo", depends="JobA"),
            _job("JobB", order=3, depends="CHAMA_API")]
    src = factory._generate_dag_source(_pipeline(), jobs)
    ast.parse(src)
    _exec_source(src)
    assert "HttpCallOperator(" in src
    assert "https://servidor.interno/api/disparo" in src
    # http é etapa de 1ª classe: ganha o trio t_start/t_job/t_end (telemetria)
    assert "t_start_CHAMA_API" in src
    assert "t_job_CHAMA_API" in src
    assert "t_end_CHAMA_API" in src
    # e o default antigo (httpbin.org) não existe mais em lugar nenhum
    assert "httpbin.org" not in src


def test_http_sem_url_recusa_publicar(factory):
    """Fail-loud na geração — o default antigo (httpbin.org) chamava endpoint
    externo em produção quando o job_command vinha vazio."""
    jobs = [_job("CHAMA_API", jtype="http", cmd=None)]
    with pytest.raises(ValueError, match="sem URL"):
        factory._generate_dag_source(_pipeline(), jobs)


# ───────────────────── validação de URL no backend ─────────────────────────

@pytest.fixture(scope="module")
def J():
    import routers.jobs as _j
    return _j


@pytest.mark.parametrize("ok", [
    "https://servidor/api/disparo",
    "http://10.0.0.5:8080/hook?x=1&y=2",
    "HTTPS://Servidor.Interno/rota",
])
def test_valid_http_url_aceita(J, ok):
    assert J._valid_http_url(ok) is True


@pytest.mark.parametrize("ruim", [
    "", "ftp://servidor/arq", "file:///etc/passwd", "servidor/api",
    "https://servidor/a b", "https://servidor/'x'", 'https://servidor/"x"',
])
def test_valid_http_url_rejeita(J, ruim):
    assert J._valid_http_url(ruim) is False
