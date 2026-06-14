"""
api/db.py — Utilitários de conexão com o SQL Server.

Uso:
    from db import get_db_conn, managed_conn

    # one-shot (fecha manualmente):
    conn = get_db_conn()
    ...
    conn.close()

    # context manager (fecha automaticamente mesmo com exceção):
    with managed_conn() as (conn, cur):
        cur.execute(...)
        conn.commit()
"""
from __future__ import annotations

import os
from contextlib import contextmanager

import pyodbc
from fastapi import HTTPException

MSSQL_CONN_STR: str = os.getenv("MSSQL_CONN_STR", "")


def get_db_conn() -> pyodbc.Connection:
    """Abre e retorna uma conexão pyodbc. Levanta HTTP 500 se MSSQL_CONN_STR não definida."""
    if not MSSQL_CONN_STR:
        raise HTTPException(status_code=500, detail="MSSQL_CONN_STR não configurada")
    return pyodbc.connect(MSSQL_CONN_STR, timeout=10)


@contextmanager
def managed_conn():
    """Context manager que abre conexão + cursor e fecha ambos ao sair.

    Faz rollback automático se a conexão ainda tiver transação aberta ao fechar.
    Uso:
        with managed_conn() as (conn, cur):
            cur.execute(...)
            conn.commit()
    """
    conn = get_db_conn()
    cur  = conn.cursor()
    try:
        yield conn, cur
    finally:
        try:
            cur.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass
