"""
services/conn_native.py — conexão pyodbc com a credencial NATIVA da conexão
(dbo.etl_conexao, senha Fernet — services.conn_crypto).

Caminho rápido da introspecção (routers/copias.py): consultar o catálogo
DIRETO da API com a MESMA credencial que o worker usa nas cargas — enxerga
os mesmos objetos (permissões reais da conexão) e sempre FRESCO, sem o cache
de 24h do RPC via DAG (que escondia tabelas recém-criadas). Antes deste
módulo, o caminho rápido só existia com a credencial do APP
(MSSQL_CONN_STR com SERVER trocado), que raramente existe nos servidores de
origem/destino — toda conexão nova caía no RPC lento.

routers/admin.py mantém um equivalente inline no conn_test (teste de
conexão salva) — mesmo padrão de conn string e redação de senha.
"""
from __future__ import annotations

import logging

import pyodbc

from db import get_db_conn
from services.conn_crypto import decrypt_password

log = logging.getLogger("orquestra-api")


def sem_senha(texto, *segredos) -> str:
    """Remove qualquer ocorrência dos segredos de um texto de erro/resposta."""
    out = str(texto or "")
    for s in segredos:
        if s:
            out = out.replace(str(s), "••••")
    return out


def odbc_quote(v: str) -> str:
    """Valor entre chaves para connection string ODBC ('}' duplicado) — evita
    que senha/login/database com ';' injete pares na conn string."""
    return "{" + str(v).replace("}", "}}") + "}"


def melhor_driver_odbc() -> str:
    """Melhor 'ODBC Driver N for SQL Server' instalado no container da API
    (ordem lexicográfica funciona para 11/13/17/18)."""
    try:
        drivers = sorted(d for d in pyodbc.drivers() if "ODBC Driver" in d)
        if drivers:
            return drivers[-1]
    except Exception:
        pass
    return "ODBC Driver 18 for SQL Server"


def abrir_conexao_nativa(conn_id: str, database: str, timeout_s: int = 15):
    """``(conn, cursor)`` pyodbc no ``database`` com a credencial da própria
    conexão (dbo.etl_conexao).

    - ``None`` quando o conn_id NÃO é nativo (legado só no Airflow) ou a
      leitura/decifra falhar — o chamador cai para a credencial do app;
    - ``RuntimeError`` (mensagem SEM senha) quando a conexão nativa existe
      mas o connect falha — erro real de login/rede, o chamador decide o
      fallback (RPC via DAG).
    """
    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute("SELECT host, port, login, senha_enc FROM dbo.etl_conexao "
                    "WHERE conn_id = ?", (conn_id,))
        row = cur.fetchone()
        cur.close(); conn.close()
        if row is None:
            return None
        host = (row[0] or "").strip()
        port = int(row[1] or 1433)
        login = row[2]
        senha = decrypt_password(row[3])
        if not host:
            return None
    except Exception as e:
        log.warning("conn_native: '%s' indisponível em etl_conexao (%s) — "
                    "caindo para a credencial do app", conn_id, e)
        return None

    conn_str = (f"DRIVER={{{melhor_driver_odbc()}}};SERVER={host},{port};"
                f"DATABASE={odbc_quote(database)};UID={odbc_quote(login)};"
                f"PWD={odbc_quote(senha)};TrustServerCertificate=yes")
    try:
        cx = pyodbc.connect(conn_str, timeout=max(1, int(timeout_s or 15)))
        return cx, cx.cursor()
    except Exception as e:
        raise RuntimeError(
            f"conexão '{conn_id}' ({host},{port}) falhou com a credencial "
            f"cadastrada: {sem_senha(e, senha)[:300]}") from e
