
"""
etl_pipeline_query.py
=====================
DAG de leitura — consulta etl_pipeline com paginação.

Recebe via conf:
  offset      : int  (default 0)
  limit       : int  (default 20, max 100)
  filter_name : str  (opcional — filtro LIKE no pipeline_name)
  filter_project: str (opcional — filtro exato no project_name)
  filter_active : int (opcional — 0 | 1)

Retorna via XCom (key='return_value'):
{
  "total"   : int,
  "offset"  : int,
  "limit"   : int,
  "pages"   : int,
  "data"    : [ { pipeline_name, project_name, domain, tags,
                  scheduled_time, active, dag_criada,
                  envia_msg_inicio, envia_msg_fim, envia_msg_erro,
                  last_execution, created_at, updated_at } ]
}
"""
from __future__ import annotations

import json
from datetime import datetime

import pendulum
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.microsoft.mssql.hooks.mssql import MsSqlHook

DAG_ID        = "etl_pipeline_query"
MSSQL_CONN_ID = "SQL14_DMDB41"
LOCAL_TZ      = "America/Sao_Paulo"
MAX_LIMIT     = 100

default_args = {"owner": "airflow", "depends_on_past": False, "retries": 0}


def _fmt(val) -> str | None:
    """Converte datetime para string ISO ou retorna None."""
    if val is None:
        return None
    if hasattr(val, "strftime"):
        return val.strftime("%Y-%m-%d %H:%M:%S")
    return str(val)


def consultar_pipelines(**context):
    conf   = context["dag_run"].conf or {}
    offset = max(0, int(conf.get("offset", 0)))
    limit  = min(MAX_LIMIT, max(1, int(conf.get("limit", 20))))
    fname  = (conf.get("filter_name")    or "").strip()
    fproj  = (conf.get("filter_project") or "").strip()
    factive = conf.get("filter_active")

    hook = MsSqlHook(mssql_conn_id=MSSQL_CONN_ID)

    # ── Monta WHERE dinâmico ────────────────────────────────
    where_clauses = []
    params_count  = []
    params_data   = []

    if fname:
        where_clauses.append("pipeline_name LIKE %s")
        params_count.append(f"%{fname}%")
        params_data.append(f"%{fname}%")

    if fproj:
        where_clauses.append("project_name = %s")
        params_count.append(fproj)
        params_data.append(fproj)

    if factive is not None:
        where_clauses.append("active = %s")
        params_count.append(int(factive))
        params_data.append(int(factive))

    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    # ── Total de registros ──────────────────────────────────
    count_sql = f"SELECT COUNT(*) FROM dbo.etl_pipeline {where_sql}"
    total = hook.get_first(count_sql, parameters=params_count or None)[0]

    # ── Dados paginados ─────────────────────────────────────
    data_sql = f"""
    SELECT
        pipeline_name,
        project_name,
        domain,
        tags,
        CONVERT(VARCHAR(8), scheduled_time, 108) AS scheduled_time,
        CAST(active           AS INT) AS active,
        CAST(DAG_CRIADA       AS INT) AS dag_criada,
        CAST(ENVIA_MSG_INICIO AS INT) AS envia_msg_inicio,
        CAST(ENVIA_MSG_FIM    AS INT) AS envia_msg_fim,
        CAST(ENVIA_MSG_ERRO   AS INT) AS envia_msg_erro,
        last_execution,
        created_at,
        updated_at
    FROM dbo.etl_pipeline
    {where_sql}
    ORDER BY project_name, domain, pipeline_name
    OFFSET %s ROWS FETCH NEXT %s ROWS ONLY
    """

    params_data.extend([offset, limit])
    rows = hook.get_records(data_sql, parameters=params_data)

    cols = [
        "pipeline_name", "project_name", "domain", "tags",
        "scheduled_time", "active", "dag_criada",
        "envia_msg_inicio", "envia_msg_fim", "envia_msg_erro",
        "last_execution", "created_at", "updated_at",
    ]

    data = []
    for row in rows:
        record = dict(zip(cols, row))
        record["last_execution"] = _fmt(record["last_execution"])
        record["created_at"]     = _fmt(record["created_at"])
        record["updated_at"]     = _fmt(record["updated_at"])
        data.append(record)

    pages = max(1, -(-total // limit))  # ceil division

    result = {
        "total":  total,
        "offset": offset,
        "limit":  limit,
        "pages":  pages,
        "data":   data,
    }

    print(f"[QUERY] total={total} | offset={offset} | limit={limit} | retornando={len(data)}")
    return result   # vai automaticamente para XCom key='return_value'


with DAG(
    dag_id=DAG_ID,
    default_args=default_args,
    description="Consulta paginada de etl_pipeline — retorna JSON via XCom",
    start_date=pendulum.datetime(2024, 1, 1, tz=LOCAL_TZ),
    schedule=None,
    catchup=False,
    tags=["etl", "query", "pipeline"],
    access_control={"Op": {"can_read", "can_edit"}},
) as dag:

    task = PythonOperator(
        task_id="consultar_pipelines",
        python_callable=consultar_pipelines,
        do_xcom_push=True,
    )
