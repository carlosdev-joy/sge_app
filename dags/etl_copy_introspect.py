"""
etl_copy_introspect.py
======================
DAG RPC de introspecção do módulo Cópia de Dados (fallback do wizard).

Disparada pela API do ORQUESTRA quando o caminho rápido (pyodbc com a
credencial do próprio app) falha — a API faz o poll do dagRun e lê o XCom
(key='return_value'), com cache em dbo.etl_copy_catalogo.

conf:
  {
    "acao":       "databases" | "tables" | "columns" | "preview" | "query_columns",
    "conn_id":    "<Airflow Connection mssql>",    (obrigatório)
    "database":   "<banco>",                       (tables/columns/preview/query_columns)
    "schema":     "<schema>",                      (columns; default 'dbo')
    "table":      "<tabela>",                      (columns)
    "select_sql": "<SELECT compilado pela API>"    (preview)
    "src_query":  "<query livre validada pela API>" (query_columns)
  }

Saída XCom no MESMO formato dos endpoints /copias/introspect/* (a API repassa):
  databases     → {"databases": ["db1", ...]}
  tables        → {"tables": [{"schema", "name", "rows"}]}
  columns       → {"columns": [{"name","type","max_length","precision","scale",
                                "is_nullable","is_identity","is_pk"}],
                   "particao_sugerida": str | null}
  preview       → {"columns": [...], "rows": [[...]]} (datas/decimal como str)
  query_columns → {"columns": [{"name", "type"}]} (SELECT TOP 0 da query;
                   tipo básico do cursor.description, JSON-safe)

Credenciais SÓ via BaseHook.get_connection (nenhuma senha em log ou XCom).
Erros → raise (a API traduz dagRun failed em 502 com mensagem clara).
"""
from __future__ import annotations

import datetime as _dt
import decimal as _decimal

import pendulum
import pymssql
from airflow import DAG
from airflow.hooks.base import BaseHook
from airflow.operators.python import PythonOperator

from utils import bulk_copy

DAG_ID   = "etl_copy_introspect"
LOCAL_TZ = "America/Sao_Paulo"

default_args = {"owner": "airflow", "depends_on_past": False, "retries": 0}

_ACOES = {"databases", "tables", "columns", "preview", "query_columns"}

# Tipos elegíveis para a partição sugerida — os que o motor de faixas da
# etl_copy_exec sabe dividir (aritmética int/decimal ou divisão por dias).
_TIPOS_PARTICAO = {
    "int", "bigint", "decimal", "numeric",
    "date", "datetime", "datetime2", "smalldatetime",
}


def _json_safe(v):
    """Valor de célula → JSON-serializável (mesmo contrato de _json_safe em
    api/routers/jobs.py): datas/datetimes → ISO; Decimal → str; bytes → hex;
    resto str (None preservado)."""
    if v is None or isinstance(v, (str, int, float, bool)):
        return v
    if isinstance(v, (_dt.datetime, _dt.date, _dt.time)):
        return v.isoformat()
    if isinstance(v, _decimal.Decimal):
        return str(v)
    if isinstance(v, (bytes, bytearray)):
        return bytes(v).hex()
    return str(v)


# ---------------------------------------------------------------------------
# Ações
# ---------------------------------------------------------------------------

def _databases(conn) -> dict:
    """Bancos ONLINE acessíveis (mesma query de /jobs/databases)."""
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT d.name FROM sys.databases d "
            "WHERE d.state_desc = 'ONLINE' AND HAS_DBACCESS(d.name) = 1 "
            "ORDER BY d.name")
        return {"databases": [r[0] for r in cur.fetchall()]}
    finally:
        cur.close()


def _tables(conn) -> dict:
    """Tabelas do banco com contagem de linhas (sys.partitions, heap/clustered)."""
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT s.name, t.name, SUM(p.rows) AS total_rows "
            "FROM sys.tables t "
            "JOIN sys.schemas s ON s.schema_id = t.schema_id "
            "JOIN sys.partitions p ON p.object_id = t.object_id "
            "                     AND p.index_id IN (0, 1) "
            "GROUP BY s.name, t.name "
            "ORDER BY s.name, t.name")
        return {"tables": [{"schema": r[0], "name": r[1], "rows": int(r[2] or 0)}
                           for r in cur.fetchall()]}
    finally:
        cur.close()


def _columns(conn, schema, table) -> dict:
    """Colunas da tabela + sugestão de coluna de partição (1ª coluna PK de
    tipo particionável)."""
    fqn = f"{bulk_copy.quote_ident(schema)}.{bulk_copy.quote_ident(table)}"
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT c.name, t.name, c.max_length, c.precision, c.scale, "
            "       c.is_nullable, c.is_identity, "
            "       CASE WHEN pk.column_id IS NULL THEN 0 ELSE 1 END AS is_pk "
            "FROM sys.columns c "
            "JOIN sys.types t ON t.user_type_id = c.user_type_id "
            "LEFT JOIN ( "
            "    SELECT ic.object_id, ic.column_id "
            "    FROM sys.indexes i "
            "    JOIN sys.index_columns ic "
            "      ON ic.object_id = i.object_id AND ic.index_id = i.index_id "
            "    WHERE i.is_primary_key = 1 "
            ") pk ON pk.object_id = c.object_id AND pk.column_id = c.column_id "
            "WHERE c.object_id = OBJECT_ID(%s) "
            "ORDER BY c.column_id",
            (fqn,))
        colunas = [{
            "name":        r[0],
            "type":        r[1],
            "max_length":  int(r[2]) if r[2] is not None else None,
            "precision":   int(r[3]) if r[3] is not None else None,
            "scale":       int(r[4]) if r[4] is not None else None,
            "is_nullable": bool(r[5]),
            "is_identity": bool(r[6]),
            "is_pk":       bool(r[7]),
        } for r in cur.fetchall()]
    finally:
        cur.close()

    if not colunas:
        raise ValueError(f"Tabela {fqn} não encontrada (ou sem colunas visíveis).")

    particao = None
    for c in colunas:
        if c["is_pk"] and (c["type"] or "").lower() in _TIPOS_PARTICAO:
            particao = c["name"]
            break
    return {"columns": colunas, "particao_sugerida": particao}


def _preview(conn, select_sql) -> dict:
    """Amostra de 50 linhas do SELECT compilado pela API (já validado lá)."""
    cur = conn.cursor()
    try:
        cur.execute(f"SELECT TOP 50 * FROM ({select_sql}) AS _prev")
        columns = [d[0] for d in (cur.description or [])]
        rows = [[_json_safe(v) for v in r] for r in cur.fetchall()]
        return {"columns": columns, "rows": rows}
    finally:
        cur.close()


def _tipo_basico(type_code):
    """Nome legível do type_code do cursor.description do pymssql (constantes
    DB-API STRING/NUMBER/DATETIME/DECIMAL/BINARY). JSON-safe (str ou None)."""
    if type_code is None:
        return None
    for nome in ("STRING", "NUMBER", "DATETIME", "DECIMAL", "BINARY"):
        t = getattr(pymssql, nome, None)
        if t is not None and type_code == t:
            return nome.lower()
    return str(type_code)


def _query_columns(conn, src_query) -> dict:
    """Colunas do result set de uma query livre (MODO QUERY do wizard):
    SELECT TOP 0 * FROM (<query>) AS _q — nomes/tipos via cursor.description.
    A query já foi validada (read-only) pela API antes do dispatch."""
    cur = conn.cursor()
    try:
        cur.execute(f"SELECT TOP 0 * FROM (\n{src_query}\n) AS _q")
        columns = [{"name": d[0], "type": _tipo_basico(d[1])}
                   for d in (cur.description or [])]
        return {"columns": columns}
    finally:
        cur.close()


# ---------------------------------------------------------------------------
# Task principal
# ---------------------------------------------------------------------------

def introspect(**context):
    conf = context["dag_run"].conf or {}
    acao    = (conf.get("acao") or "").strip().lower()
    conn_id = (conf.get("conn_id") or "").strip()

    if acao not in _ACOES:
        raise ValueError(
            f"Parâmetro 'acao' inválido: {acao!r}. Use: {sorted(_ACOES)}")
    if not conn_id:
        raise ValueError("Parâmetro 'conn_id' é obrigatório.")

    database   = (conf.get("database") or "").strip()
    schema     = (conf.get("schema") or "dbo").strip()
    table      = (conf.get("table") or "").strip()
    select_sql = (conf.get("select_sql") or "").strip()
    src_query  = (conf.get("src_query") or "").strip()

    if acao in ("tables", "columns", "query_columns") and not database:
        raise ValueError(f"Parâmetro 'database' é obrigatório para acao={acao}.")
    if acao == "columns" and not table:
        raise ValueError("Parâmetro 'table' é obrigatório para acao=columns.")
    if acao == "preview" and not select_sql:
        raise ValueError("Parâmetro 'select_sql' é obrigatório para acao=preview.")
    if acao == "query_columns" and not src_query:
        raise ValueError("Parâmetro 'src_query' é obrigatório para acao=query_columns.")

    airflow_conn = BaseHook.get_connection(conn_id)
    banco = "master" if acao == "databases" else (database or "master")
    print(f"[INTROSPECT] acao={acao} conn_id={conn_id} database={banco}"
          + (f" tabela={schema}.{table}" if acao == "columns" else ""))

    conn = bulk_copy.open_src_conn(airflow_conn, banco)
    try:
        if acao == "databases":
            payload = _databases(conn)
            print(f"[INTROSPECT] {len(payload['databases'])} banco(s).")
        elif acao == "tables":
            payload = _tables(conn)
            print(f"[INTROSPECT] {len(payload['tables'])} tabela(s).")
        elif acao == "columns":
            payload = _columns(conn, schema, table)
            print(f"[INTROSPECT] {len(payload['columns'])} coluna(s); "
                  f"particao_sugerida={payload['particao_sugerida']}")
        elif acao == "query_columns":
            payload = _query_columns(conn, src_query)
            print(f"[INTROSPECT] query_columns: {len(payload['columns'])} coluna(s).")
        else:  # preview
            payload = _preview(conn, select_sql)
            print(f"[INTROSPECT] preview: {len(payload['rows'])} linha(s), "
                  f"{len(payload['columns'])} coluna(s).")
    finally:
        try:
            conn.close()
        except Exception:
            pass

    return payload


with DAG(
    dag_id=DAG_ID,
    default_args=default_args,
    description=("Cópia de Dados — introspecção RPC de origem/destino "
                 "(conf: {\"acao\", \"conn_id\", ...})"),
    start_date=pendulum.datetime(2024, 1, 1, tz=LOCAL_TZ),
    schedule=None,
    catchup=False,
    tags=["etl", "copy"],
) as dag:

    PythonOperator(
        task_id="introspect",
        python_callable=introspect,
        do_xcom_push=True,
    )
