"""
dags/utils/conn_resolver.py — resolução de conexões MSSQL do Orquestra.
=======================================================================

Fonte da verdade: **dbo.etl_conexao** (migration 054 — senha cifrada com
Fernet, chave em ORQUESTRA_CONN_KEY, a mesma do orquestra-api). Fallback:
Airflow Connections (BaseHook), para conexões ainda não migradas.

Uso (etl_copy_exec / etl_copy_introspect):
    from utils.conn_resolver import get_conexao
    conn = get_conexao("SQL14_DMDB41")   # objeto airflow.models.Connection

O retorno é sempre um ``airflow.models.Connection`` (mesma interface de
``BaseHook.get_connection``): ``bulk_copy._conn_params`` e
``charset_da_conexao`` (extra_dejson) continuam funcionando sem mudança.

A senha NUNCA deve ser logada pelo chamador.
"""
from __future__ import annotations

import os

from airflow.hooks.base import BaseHook
from airflow.models.connection import Connection
from airflow.providers.microsoft.mssql.hooks.mssql import MsSqlHook

# Banco do Orquestra (mesma connection usada pelas DAGs para ler etl_copy_job)
MSSQL_CONN_ID = "SQL14_DMDB41"

_ENV_KEY = "ORQUESTRA_CONN_KEY"


def _decrypt(token: str) -> str:
    from cryptography.fernet import Fernet  # cryptography é dependência do próprio Airflow
    key = (os.getenv(_ENV_KEY) or "").strip()
    if not key:
        raise ValueError(
            f"{_ENV_KEY} não configurada no worker — defina no .env/compose o "
            "MESMO valor usado pelo orquestra-api (x-airflow-common)")
    return Fernet(key.encode()).decrypt(str(token).encode("ascii")).decode("utf-8")


def get_conexao(conn_id: str) -> Connection:
    """Connection do conn_id: dbo.etl_conexao primeiro; fallback BaseHook.

    A leitura da tabela degrada graciosamente (tabela ausente/banco fora →
    fallback Airflow), mas um registro EXISTENTE com senha ilegível levanta
    erro claro em vez de cair no fallback — senão a cópia rodaria com uma
    credencial diferente da cadastrada na UI.
    """
    row = None
    try:
        hook = MsSqlHook(mssql_conn_id=MSSQL_CONN_ID)
        rows = hook.get_records(
            "SELECT host, port, login, senha_enc, extra_json "
            "FROM dbo.etl_conexao WHERE conn_id = %s",
            parameters=(conn_id,))
        row = rows[0] if rows else None
    except Exception as e:
        print(f"[CONEXAO] leitura de dbo.etl_conexao falhou ({e}) — "
              f"fallback Airflow Connections")

    if row is None:
        print(f"[CONEXAO] '{conn_id}' não está em dbo.etl_conexao — "
              f"usando Airflow Connection (BaseHook)")
        return BaseHook.get_connection(conn_id)

    host, port, login, senha_enc, extra_json = row
    print(f"[CONEXAO] '{conn_id}' resolvida em dbo.etl_conexao (host={host})")
    return Connection(
        conn_id=conn_id,
        conn_type="mssql",
        host=host,
        port=int(port) if port else None,
        login=login,
        password=_decrypt(senha_enc),
        extra=extra_json or None,
    )
