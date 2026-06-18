"""
Testa a geração de código para jobs job_type='storedproc' com e sem
parâmetros fixos (migration 024). Garante que:
  - valores de parâmetro nunca são concatenados na string SQL (sempre via
    hook.run(sql, parameters=[...]));
  - nome de procedure/parâmetro inválido não quebra a geração do DAG;
  - mssql_conn_id por job é respeitado, com fallback para a conexão global.

Airflow não está instalado neste ambiente de teste — os módulos necessários
são stubados antes do import de dags/etl_dag_factory.py.
"""
from __future__ import annotations

import sys
import types
import py_compile
import tempfile
from pathlib import Path

import pytest


def _stub_airflow():
    if "airflow" in sys.modules:
        return

    class _DAG:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False

    airflow = types.ModuleType("airflow")
    airflow.DAG = _DAG
    sys.modules["airflow"] = airflow

    models = types.ModuleType("airflow.models")
    models.Variable = type("Variable", (), {"get": staticmethod(lambda *a, **k: "")})
    sys.modules["airflow.models"] = models

    class _PythonOperator:
        def __init__(self, *a, **k): pass
        def __rshift__(self, other): return other
        def __lshift__(self, other): return other

    operators = types.ModuleType("airflow.operators")
    sys.modules["airflow.operators"] = operators
    operators_python = types.ModuleType("airflow.operators.python")
    operators_python.PythonOperator = _PythonOperator
    sys.modules["airflow.operators.python"] = operators_python

    providers = types.ModuleType("airflow.providers")
    sys.modules["airflow.providers"] = providers
    ms = types.ModuleType("airflow.providers.microsoft")
    sys.modules["airflow.providers.microsoft"] = ms
    mssql = types.ModuleType("airflow.providers.microsoft.mssql")
    sys.modules["airflow.providers.microsoft.mssql"] = mssql
    hooks = types.ModuleType("airflow.providers.microsoft.mssql.hooks")
    sys.modules["airflow.providers.microsoft.mssql.hooks"] = hooks
    hooks_mssql = types.ModuleType("airflow.providers.microsoft.mssql.hooks.mssql")
    hooks_mssql.MsSqlHook = type("MsSqlHook", (), {})
    sys.modules["airflow.providers.microsoft.mssql.hooks.mssql"] = hooks_mssql


_stub_airflow()

sys.path.insert(0, str(Path(__file__).parent.parent / "dags"))
import etl_dag_factory as factory  # noqa: E402


def _compiles(code: str) -> bool:
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
        f.write(code)
        path = f.name
    try:
        py_compile.compile(path, doraise=True)
        return True
    finally:
        Path(path).unlink(missing_ok=True)
        Path(path + "c").unlink(missing_ok=True)


def test_storedproc_sem_parametro_mantem_comportamento_atual():
    job = {"job_name": "j1", "job_type": "storedproc", "job_command": "dbo.sp_teste"}
    code = factory._task_block(job, "proj", {})
    assert 'EXEC dbo.sp_teste"' in code
    assert "parameters=" not in code
    assert _compiles(code)


def test_storedproc_com_parametros_usa_bind_real():
    job = {
        "job_name": "j2", "job_type": "storedproc", "job_command": "dbo.sp_teste",
        "params": [
            {"param_name": "@p_texto", "param_type": "VARCHAR", "param_value": "abc"},
            {"param_name": "p_numero", "param_type": "INT", "param_value": "5"},
        ],
    }
    code = factory._task_block(job, "proj", {})
    assert "EXEC dbo.sp_teste @p_texto=?, @p_numero=?" in code
    assert "parameters=['abc', 5]" in code
    assert _compiles(code)


def test_storedproc_nome_invalido_nao_quebra_geracao():
    job = {"job_name": "j3", "job_type": "storedproc", "job_command": "dbo.sp_teste; DROP TABLE x"}
    code = factory._task_block(job, "proj", {})
    assert "raise ValueError" in code
    assert _compiles(code)


def test_storedproc_usa_conexao_por_job_com_fallback_global():
    job_custom  = {"job_name": "j4", "job_type": "storedproc", "job_command": "dbo.sp_teste", "mssql_conn_id": "SQL_HOMOLOG"}
    job_default = {"job_name": "j5", "job_type": "storedproc", "job_command": "dbo.sp_teste"}
    assert "mssql_conn_id='SQL_HOMOLOG'" in factory._task_block(job_custom, "proj", {})
    assert "mssql_conn_id=MSSQL_CONN_ID" in factory._task_block(job_default, "proj", {})


@pytest.mark.parametrize("ptype,raw,expected", [
    ("INT", "5", 5),
    ("DECIMAL", "1.5", 1.5),
    ("VARCHAR", "abc", "abc"),
    ("BIT", "1", True),
])
def test_coerce_param_value(ptype, raw, expected):
    assert factory._coerce_param_value({"param_type": ptype, "param_value": raw}) == expected
