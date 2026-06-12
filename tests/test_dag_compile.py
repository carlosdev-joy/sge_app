"""
Verifica que todos os arquivos .py em dags/generated/ compilam sem erros.
Gate obrigatório: nenhum arquivo gerado pelo etl_dag_factory pode ter erro de sintaxe.

Roda como:
    pytest tests/test_dag_compile.py
ou como parte do CI:
    python -m pytest tests/test_dag_compile.py -v
"""
from __future__ import annotations

import os
import py_compile
from pathlib import Path

import pytest

DAGS_GENERATED = Path(__file__).parent.parent / "dags" / "generated"


def _generated_dags() -> list[Path]:
    if not DAGS_GENERATED.exists():
        return []
    return sorted(DAGS_GENERATED.glob("*.py"))


@pytest.mark.parametrize("dag_file", _generated_dags(),
                         ids=lambda p: p.stem)
def test_dag_compiles(dag_file: Path):
    """Cada DAG gerado deve compilar sem erros de sintaxe."""
    try:
        py_compile.compile(str(dag_file), doraise=True)
    except py_compile.PyCompileError as exc:
        pytest.fail(f"Erro de sintaxe em {dag_file.name}:\n{exc}")


def test_factory_script_compiles():
    """O factory principal deve compilar sem erros."""
    factory = Path(__file__).parent.parent / "dags" / "etl_dag_factory.py"
    if not factory.exists():
        pytest.skip("etl_dag_factory.py não encontrado")
    try:
        py_compile.compile(str(factory), doraise=True)
    except py_compile.PyCompileError as exc:
        pytest.fail(f"Erro de sintaxe em etl_dag_factory.py:\n{exc}")


def test_api_main_compiles():
    """api/main.py deve compilar sem erros de sintaxe."""
    api_main = Path(__file__).parent.parent / "api" / "main.py"
    try:
        py_compile.compile(str(api_main), doraise=True)
    except py_compile.PyCompileError as exc:
        pytest.fail(f"Erro de sintaxe em api/main.py:\n{exc}")
