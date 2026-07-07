"""
Testes do nó PYTHON v2 na geração de DAG (migration 059 — python_json).

Contrato:
  - python_json ausente/None/inválido → modo LEGADO 'modulo': PythonModuleOperator
    (worker), código gerado byte-idêntico ao anterior.
  - modo 'arquivo'  → PythonScriptOperator via SSH no servidor do job
    (script_path literal fiel).
  - modo 'codigo'   → PythonScriptOperator com destino_dir/arquivo/codigo —
    o código do usuário embutido byte a byte (repr) no fonte da DAG.
  - import de PythonScriptOperator só aparece quando algum job usa os modos
    novos (pipelines legados não mudam).
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
    spec = importlib.util.spec_from_file_location("etl_dag_factory_py_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _pipeline():
    return {
        "pipeline_name": "PIPE_PY", "project_name": "BI_CVP", "domain": "TESTE",
        "tags": "ETL", "scheduled_time": "06:00:00",
        "envia_msg_inicio": 0, "envia_msg_fim": 1, "envia_msg_erro": 1,
        "ambiente": "PROD", "schedule_type": "daily",
    }


def _py_job(cfg=None, cmd="scripts.carga.run", ssh=None, name="PY_1"):
    j = {"job_name": name, "job_type": "python", "job_command": cmd, "execution_order": 1}
    if cfg is not None:
        j["python_json"] = json.dumps(cfg) if isinstance(cfg, dict) else cfg
    if ssh is not None:
        j["ssh_conn_id"] = ssh
    return j


def _kwargs(src: str, task_var: str) -> dict:
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if (isinstance(node, ast.Assign) and node.targets
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == task_var
                and isinstance(node.value, ast.Call)):
            return {kw.arg: (ast.literal_eval(kw.value)
                             if isinstance(kw.value, ast.Constant) else kw.value)
                    for kw in node.value.keywords}
    raise AssertionError(f"{task_var} não encontrado")


# ── Modo legado (módulo no worker) — inalterado ──────────────────────────────

def test_legado_sem_python_json_usa_module_operator(factory):
    src = factory._generate_dag_source(_pipeline(), [_py_job()])
    ast.parse(src)
    assert "PythonModuleOperator(" in src
    assert "PythonScriptOperator" not in src   # import e uso ausentes
    kwargs = _kwargs(src, "t_job_PY_1")
    assert kwargs["module"] == "scripts.carga.run"


def test_python_json_invalido_degrada_para_legado(factory):
    src = factory._generate_dag_source(_pipeline(), [_py_job(cfg="{nao é json")])
    assert "PythonModuleOperator(" in src
    assert "PythonScriptOperator" not in src


# ── Modo arquivo (script já existe no servidor) ──────────────────────────────

def test_modo_arquivo_emite_script_operator_com_ssh_do_job(factory):
    cfg = {"modo": "arquivo", "script_path": "/opt/scripts/carga diaria.py"}
    src = factory._generate_dag_source(_pipeline(), [_py_job(cfg, ssh="ssh_srv_py")])
    ast.parse(src)
    kwargs = _kwargs(src, "t_job_PY_1")
    assert kwargs["modo"] == "arquivo"
    assert kwargs["script_path"] == "/opt/scripts/carga diaria.py"
    assert kwargs["ssh_conn_id"] == "ssh_srv_py"
    assert "PythonScriptOperator" in src
    assert "PythonModuleOperator" not in src


def test_modo_arquivo_sem_ssh_cai_no_default_do_pipeline(factory):
    cfg = {"modo": "arquivo", "script_path": "/opt/x.py"}
    src = factory._generate_dag_source(_pipeline(), [_py_job(cfg)])
    kwargs = _kwargs(src, "t_job_PY_1")
    assert isinstance(kwargs["ssh_conn_id"], ast.Name)
    assert kwargs["ssh_conn_id"].id == "SSH_CONN_ID"


def test_interpretador_custom_emitido_e_default_omitido(factory):
    com = {"modo": "arquivo", "script_path": "/opt/x.py", "interpretador": "/usr/bin/python3.11"}
    sem = {"modo": "arquivo", "script_path": "/opt/x.py", "interpretador": "python3"}
    src_com = factory._generate_dag_source(_pipeline(), [_py_job(com)])
    src_sem = factory._generate_dag_source(_pipeline(), [_py_job(sem)])
    assert _kwargs(src_com, "t_job_PY_1")["interpretador"] == "/usr/bin/python3.11"
    assert "interpretador" not in _kwargs(src_sem, "t_job_PY_1")


# ── Modo código (o Orquestra publica e executa) ──────────────────────────────

def test_modo_codigo_embute_o_codigo_fiel(factory):
    codigo = (
        "import sys\n"
        "print('linha com aspas \"duplas\" e simples')\n"
        "if __name__ == '__main__':\n"
        "    sys.exit(0)\n"
    )
    cfg = {"modo": "codigo", "destino_dir": "/opt/scripts", "arquivo": "gerado.py",
           "codigo": codigo}
    src = factory._generate_dag_source(_pipeline(), [_py_job(cfg, ssh="ssh_srv_py")])
    ast.parse(src)
    kwargs = _kwargs(src, "t_job_PY_1")
    assert kwargs["modo"] == "codigo"
    assert kwargs["destino_dir"] == "/opt/scripts"
    assert kwargs["arquivo"] == "gerado.py"
    assert kwargs["codigo"] == codigo   # byte a byte


def test_misto_importa_os_dois_operadores(factory):
    jobs = [
        _py_job(name="PY_LEG"),
        _py_job({"modo": "arquivo", "script_path": "/opt/x.py"}, name="PY_NOVO"),
    ]
    jobs[1]["execution_order"] = 2
    src = factory._generate_dag_source(_pipeline(), jobs)
    ast.parse(src)
    assert "PythonModuleOperator" in src
    assert "PythonScriptOperator" in src
