"""
dags/utils/conn_resolver.py — resolução de conexões MSSQL do Orquestra.
=======================================================================

Fonte da verdade: **dbo.etl_conexao** (migration 054 — senha cifrada com
Fernet, chave em ORQUESTRA_CONN_KEY, a mesma do orquestra-api). Fallback:
Airflow Connections (BaseHook), para conexões ainda não migradas.

Uso (etl_copy_exec / etl_copy_introspect):
    from utils.conn_resolver import get_conexao
    conn = get_conexao("SQL14_DMDB41")

O retorno tem a MESMA interface de atributos de ``airflow.models.Connection``
usada pelas DAGs (host, port, login, password, extra, extra_dejson):
``bulk_copy._conn_params`` e ``charset_da_conexao`` funcionam sem mudança.
Registro de dbo.etl_conexao → ``ConexaoOrquestra`` (objeto leve, SEM o ORM
do Airflow); fallback → o ``Connection`` real de ``BaseHook.get_connection``.

A senha NUNCA deve ser logada pelo chamador.
"""
from __future__ import annotations

import json
import os

from airflow.hooks.base import BaseHook
from airflow.providers.microsoft.mssql.hooks.mssql import MsSqlHook

# Banco do Orquestra (mesma connection usada pelas DAGs para ler etl_copy_job)
MSSQL_CONN_ID = "SQL14_DMDB41"

_ENV_KEY = "ORQUESTRA_CONN_KEY"


class ConexaoOrquestra:
    """Conexão resolvida de dbo.etl_conexao — mesma interface de ATRIBUTOS de
    ``airflow.models.Connection`` que as DAGs usam (host, port, login,
    password, extra, extra_dejson), SEM o ORM do Airflow.

    Motivo (incidente 2026-07-04): construir ``Connection(password=...)``
    aciona o ``set_password`` do Airflow, que instancia o Fernet INTERNO do
    Airflow (AIRFLOW__CORE__FERNET_KEY) — uma chave core malformada no .env
    derrubava a resolução de TODA conexão nativa, mesmo com a senha já
    decifrada corretamente pela ORQUESTRA_CONN_KEY. A senha daqui nunca é
    persistida no metastore, então o ORM não tem função nenhuma."""

    __slots__ = ("conn_id", "conn_type", "host", "port", "login",
                 "password", "extra")

    def __init__(self, conn_id, host, port, login, password, extra=None):
        self.conn_id = conn_id
        self.conn_type = "mssql"
        self.host = host
        self.port = port
        self.login = login
        self.password = password
        self.extra = extra

    @property
    def extra_dejson(self) -> dict:
        """extra (JSON em texto) → dict; {} quando vazio/ilegível — o mesmo
        contrato tolerante de charset_da_conexao."""
        try:
            return json.loads(self.extra) if self.extra else {}
        except (ValueError, TypeError):
            return {}

    def __repr__(self):  # NUNCA expor a senha em logs/tracebacks
        return (f"ConexaoOrquestra(conn_id={self.conn_id!r}, "
                f"host={self.host!r}, port={self.port!r})")


def _decrypt(token: str) -> str:
    from cryptography.fernet import Fernet  # cryptography é dependência do próprio Airflow
    key = (os.getenv(_ENV_KEY) or "").strip()
    if not key:
        raise ValueError(
            f"{_ENV_KEY} não configurada no worker — defina no .env/compose o "
            "MESMO valor usado pelo orquestra-api (x-airflow-common)")
    return Fernet(key.encode()).decrypt(str(token).encode("ascii")).decode("utf-8")


def get_conexao(conn_id: str):
    """Conexão do conn_id: dbo.etl_conexao primeiro (ConexaoOrquestra);
    fallback BaseHook (airflow.models.Connection).

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
    return ConexaoOrquestra(
        conn_id=conn_id,
        host=host,
        port=int(port) if port else None,
        login=login,
        password=_decrypt(senha_enc),
        extra=extra_json or None,
    )


def schema_da_conexao(cx):
    """Database default da conexão: ``schema`` (Airflow Connection) ou a chave
    ``database`` do extra JSON (nativa). None quando não configurado."""
    db = getattr(cx, "schema", None)
    if db and str(db).strip():
        return str(db).strip()
    try:
        return (cx.extra_dejson or {}).get("database") or None
    except Exception:
        return None


def abrir_conexao_mssql(conn_id: str, database: str | None = None,
                        timeout: int = 0, autocommit: bool = False,
                        appname: str = "orquestra-fluxo"):
    """Conexão **pymssql** resolvida pelo Orquestra: dbo.etl_conexao PRIMEIRO
    (login/senha nativos), Airflow Connection como fallback — a MESMA regra da
    Cópia de Dados, agora para os componentes SQL do fluxo (nó SQL, decisão,
    storedproc).

    Database do connect (precedência): ``database`` explícito > schema/extra da
    conexão resolvida > schema da Airflow Connection HOMÔNIMA (ambiente híbrido:
    a nativa migrada não guarda database, mas as DAGs legadas assumiam o schema
    da conn do Airflow) > default do login.
    """
    import pymssql  # dependência do MsSqlHook — sempre presente no worker

    cx = get_conexao(conn_id)
    db = (database or "").strip() or schema_da_conexao(cx)
    if not db and isinstance(cx, ConexaoOrquestra):
        try:
            db = (BaseHook.get_connection(conn_id).schema or "").strip() or None
        except Exception:
            db = None
    try:
        charset = (cx.extra_dejson or {}).get("charset") or None
    except Exception:
        charset = None
    kw = dict(
        server=cx.host, port=str(int(cx.port or 1433)),
        user=cx.login, password=cx.password,
        login_timeout=30, timeout=int(timeout or 0),
        charset=charset or "UTF-8", appname=appname, autocommit=autocommit,
    )
    if db:
        kw["database"] = db
    return pymssql.connect(**kw)
