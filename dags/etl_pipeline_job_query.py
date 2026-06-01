"""
etl_pipeline_job_query.py
=========================
DAG de leitura — consulta jobs de pipeline com paginação.

Objetivo:
- Dar suporte ao módulo "Jobs" da UI (grid/listagem), retornando dados via XCom.

Entrada via conf:
  offset            : int  (default 0)
  limit             : int  (default 50, max 200)
  filter_pipeline   : str  (opcional — filtro exato em pipeline_name)
  filter_job_name   : str  (opcional — filtro LIKE em job_name)
  filter_job_type   : str  (opcional — filtro exato em job_type)

Saída via XCom (key='return_value'):
{
  "total"   : int,
  "offset"  : int,
  "limit"   : int,
  "pages"   : int,
  "table"   : str,   # tabela usada na consulta
  "data"    : [
     {
       "pipeline_name": str,
       "project_name": str | None,
       "job_name": str,
       "execution_order": int,
       "job_type": str | None,
       "job_command": str | None,
       "active": int | None,
       "created_at": str | None,
       "updated_at": str | None
     }
  ]
}

Observação:
- Como o ambiente pode ter nomes de tabelas/colunas diferentes, este DAG tenta
  detectar automaticamente a tabela de jobs e mapear colunas comuns para um
  formato padrão consumível pela UI.
"""

from __future__ import annotations

from datetime import datetime

import pendulum
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.microsoft.mssql.hooks.mssql import MsSqlHook

DAG_ID = "etl_pipeline_job_query"
MSSQL_CONN_ID = "SQL14_DMDB41"
LOCAL_TZ = "America/Sao_Paulo"
MAX_LIMIT = 200

default_args = {"owner": "airflow", "depends_on_past": False, "retries": 0}


def _fmt(val) -> str | None:
    if val is None:
        return None
    if hasattr(val, "strftime"):
        return val.strftime("%Y-%m-%d %H:%M:%S")
    return str(val)


def _pick_col(cols: set[str], *candidates: str) -> str | None:
    """Retorna o primeiro candidato existente no set cols."""
    for c in candidates:
        if c in cols:
            return c
    return None


def _detect_table(hook: MsSqlHook) -> str:
    """
    Detecta a tabela de jobs em dbo.
    Ajuste a lista de candidatos conforme necessário.
    """
    candidates = [
        "etl_pipeline_job",
        "etl_pipeline_jobs",
        "etl_job",
        "etl_jobs",
        "pipeline_job",
        "pipeline_jobs",
    ]
    sql = """
    SELECT TABLE_NAME
    FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_SCHEMA = 'dbo'
      AND TABLE_NAME IN ({placeholders})
    """
    placeholders = ",".join(["%s"] * len(candidates))
    sql = sql.format(placeholders=placeholders)
    rows = hook.get_records(sql, parameters=candidates)
    if rows:
        return rows[0][0]
    raise RuntimeError(
        "Não foi possível detectar a tabela de jobs. "
        f"Verifique se existe uma das tabelas: {', '.join(candidates)}"
    )


def _get_columns(hook: MsSqlHook, table: str) -> set[str]:
    sql = """
    SELECT COLUMN_NAME
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME=%s
    """
    return {r[0] for r in hook.get_records(sql, parameters=[table])}


def _table_exists(hook: MsSqlHook, table: str) -> bool:
    sql = """
    SELECT 1
    FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME=%s
    """
    return bool(hook.get_first(sql, parameters=[table]))


def consultar_jobs(**context):
    conf = context["dag_run"].conf or {}
    offset = max(0, int(conf.get("offset", 0)))
    limit = min(MAX_LIMIT, max(1, int(conf.get("limit", 50))))
    fp = (conf.get("filter_pipeline") or "").strip()
    fj = (conf.get("filter_job_name") or "").strip()
    ft = (conf.get("filter_job_type") or "").strip()

    hook = MsSqlHook(mssql_conn_id=MSSQL_CONN_ID)
    table = _detect_table(hook)
    cols = _get_columns(hook, table)

    # Mapeia colunas para um formato padrão
    col_pipeline = _pick_col(cols, "pipeline_name", "pipeline", "pipeline_id")
    col_job_name = _pick_col(cols, "job_name", "name", "job")
    col_order = _pick_col(cols, "execution_order", "job_order", "order", "seq", "sequence")
    col_type = _pick_col(cols, "job_type", "type")
    col_cmd = _pick_col(cols, "job_command", "command", "cmd")
    col_active = _pick_col(cols, "active", "is_active")
    col_created = _pick_col(cols, "created_at", "created_on", "dt_created")
    col_updated = _pick_col(cols, "updated_at", "updated_on", "dt_updated")

    # Project (etl_pipeline.project_name) — usado pela UI no fluxo: Jobs → Lineage → Extrair DSX
    pipeline_table = "etl_pipeline"
    join_project = False
    if _table_exists(hook, pipeline_table) and col_pipeline in ("pipeline_name", "pipeline"):
        pcols = _get_columns(hook, pipeline_table)
        join_project = "project_name" in pcols

    # Campos mínimos para o grid
    if not col_pipeline or not col_job_name or not col_order:
        raise RuntimeError(
            f"Tabela dbo.{table} não possui colunas mínimas esperadas. "
            f"Encontrado pipeline={col_pipeline}, job={col_job_name}, order={col_order}."
        )

    def sel(col: str | None, alias: str, cast_int: bool = False) -> str:
        if not col:
            return f"NULL AS {alias}"
        if cast_int:
            return f"CAST(j.{col} AS INT) AS {alias}"
        return f"j.{col} AS {alias}"

    # WHERE dinâmico
    where = []
    params = []
    if fp:
        where.append(f"j.{col_pipeline} = %s")
        params.append(fp)
    if fj:
        where.append(f"j.{col_job_name} LIKE %s")
        params.append(f"%{fj}%")
    if ft and col_type:
        where.append(f"j.{col_type} = %s")
        params.append(ft)

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    # COUNT
    count_sql = f"SELECT COUNT(*) FROM dbo.{table} j {where_sql}"
    total = hook.get_first(count_sql, parameters=params or None)[0]

    # DATA
    data_sql = f"""
    SELECT
      {sel(col_pipeline, 'pipeline_name')},
      {('p.project_name AS project_name' if join_project else 'NULL AS project_name')},
      {sel(col_job_name, 'job_name')},
      {sel(col_order, 'execution_order', cast_int=True)},
      {sel(col_type, 'job_type')},
      {sel(col_cmd, 'job_command')},
      {sel(col_active, 'active', cast_int=True)},
      {sel(col_created, 'created_at')},
      {sel(col_updated, 'updated_at')}
    FROM dbo.{table} j
    {('LEFT JOIN dbo.' + pipeline_table + ' p ON p.pipeline_name = j.' + col_pipeline if join_project else '')}
    {where_sql}
    ORDER BY j.{col_pipeline}, j.{col_order}, j.{col_job_name}
    OFFSET %s ROWS FETCH NEXT %s ROWS ONLY
    """
    data_params = list(params)
    data_params.extend([offset, limit])
    rows = hook.get_records(data_sql, parameters=data_params)

    data = []
    for r in rows:
        rec = {
            "pipeline_name": r[0],
            "project_name": r[1],
            "job_name": r[2],
            "execution_order": r[3],
            "job_type": r[4],
            "job_command": r[5],
            "active": r[6],
            "created_at": _fmt(r[7]),
            "updated_at": _fmt(r[8]),
        }
        data.append(rec)

    pages = 0 if total == 0 else -(-total // limit)

    result = {
        "total": total,
        "offset": offset,
        "limit": limit,
        "pages": pages,
        "table": table,
        "data": data,
    }
    print(
        f"[JOB_QUERY] table={table} total={total} | offset={offset} | limit={limit} | retornando={len(data)}"
    )
    return result


with DAG(
    dag_id=DAG_ID,
    default_args=default_args,
    description="Consulta paginada de jobs — retorna JSON via XCom",
    start_date=pendulum.datetime(2024, 1, 1, tz=LOCAL_TZ),
    schedule=None,
    catchup=False,
    tags=["etl", "query", "job", "pipeline"],
    access_control={"Op": {"can_read", "can_edit"}},
) as dag:
    task = PythonOperator(
        task_id="consultar_jobs",
        python_callable=consultar_jobs,
        do_xcom_push=True,
    )

