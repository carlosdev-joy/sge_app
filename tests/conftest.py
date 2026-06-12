"""
Fixtures compartilhadas de teste.

Para rodar localmente (com banco disponível):
    MSSQL_CONN_STR="DSN=..." pytest

Para rodar em modo smoke sem banco (apenas endpoints que não tocam DB):
    pytest -k "smoke"

Wheels necessárias (adicionar em api/wheels/ antes do deploy):
    pip download pytest pytest-asyncio httpx anyio -d api/wheels/
    # em seguida: pip install --no-index --find-links api/wheels/ pytest pytest-asyncio httpx
"""
from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="session")
def app():
    """Importa o app FastAPI com MSSQL_CONN_STR mockada se não definida."""
    conn_str = os.getenv("MSSQL_CONN_STR", "")
    if not conn_str:
        os.environ.setdefault("MSSQL_CONN_STR", "__mock__")
    from api.main import app as _app
    return _app


@pytest.fixture(scope="session")
def client(app):
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
