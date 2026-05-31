"""
etl_job_execution_query.py
==========================
DAG de leitura — consulta paginada em dbo.etl_job_execution (SQL Server / DMDB41).

Objetivo:
- Retornar execuções agregadas por (execution_id, pipeline, project).
- Permitir filtros por projeto, pipeline (LIKE), status geral e período.

Retorno via XCom (key='return_value') — mesmo padrão das outras query DAGs:
{
  "total": int,
  "offset": int,
  "limit": int,
  "pages": int,
  "filters": {...},
  "data": [
    {
      "execution_id": str,
      "project": str,
      "pipeline": str | null,
      "inicio": "YYYY-MM-DD HH:MM:SS" | null,
      "fim": "YYYY-MM-DD HH:MM:SS" | null,
      "duracao_total_segundos": int,
      "total_jobs": int,
      "jobs_ok": int,
      "jobs_falha": int,
      "jobs_warning": int,
      "jobs_running": int,
      "status_geral": "FAILED" | "WARNING" | "RUNNING" | "SUCCESS" | "DESCONHECIDO"
    }
  ]
}

Conf esperado:
{
  "offset":          0,
  "limit":           50,
  "filter_project":  "BI_CVP",        // opcional — filtra por projeto (igualdade)
  "filter_pipeline": "datastage_",    // opcional — LIKE %valor%
  "filter_status":   "FAILED",        // opcional — SUCCESS | FAILED | WARNING | RUNNING
  "filter_date_from":"2026-05-01",    // opcional — YYYY-MM-DD
  "filter_date_to":  "2026-05-31"     // opcional — YYYY-MM-DD (inclusive)
}

Task que produz o XCom: consultar_logs
"""

from __future__ import annotations

import pendulum
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.microsoft.mssql.hooks.mssql import MsSqlHook

DAG_ID = "etl_job_execution_query"
MSSQL_CONN_ID = "SQL14_DMDB41"
LOCAL_TZ = "America/Sao_Paulo"
MAX_LIMIT = 200

default_args = {"owner": "airflow", "depends_on_past": False, "retries": 0}


def _fmt_dt(v) -> str | None:
    if v is None:
        return None
    if hasattr(v, "strftime"):
        return v.strftime("%Y-%m-%d %H:%M:%S")
    return str(v)


def _ceil_div(a: int, b: int) -> int:
    return 0 if b <= 0 else -(-a // b)


def consultar_logs(**context):
    conf = context["dag_run"].conf or {}

    offset = max(0, int(conf.get("offset", 0)))
    limit = int(conf.get("limit", 50))
    limit = min(MAX_LIMIT, max(1, limit))

    filter_project = (conf.get("filter_project") or "").strip()
    filter_pipeline = (conf.get("filter_pipeline") or "").strip()
    filter_status = (conf.get("filter_status") or "").strip().upper()
    filter_date_from = (conf.get("filter_date_from") or "").strip()
    filter_date_to = (conf.get("filter_date_to") or "").strip()

    hook = MsSqlHook(mssql_conn_id=MSSQL_CONN_ID)

    # ── WHERE dinâmico (por linha) ─────────────────────────────────────────────
    where_parts: list[str] = []
    params: list[object] = []

    if filter_project:
        where_parts.append("project = %s")
        params.append(filter_project)

    if filter_pipeline:
        where_parts.append("pipeline LIKE %s")
        params.append(f"%{filter_pipeline}%")

    # Período (inclusive)
    # - date_from: >= 00:00:00
    # - date_to:   < (date_to + 1 dia) 00:00:00  (equivalente a <= 23:59:59, porém mais seguro)
    if filter_date_from:
        where_parts.append("start_time >= %s")
        params.append(filter_date_from + " 00:00:00")

    if filter_date_to:
        try:
            dt_to = pendulum.parse(filter_date_to).add(days=1).format("YYYY-MM-DD")
            where_parts.append("start_time < %s")
            params.append(dt_to + " 00:00:00")
        except Exception:
            # fallback (mantém compatível)
            where_parts.append("start_time < %s")
            params.append(filter_date_to + " 23:59:59")

    where_sql = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""

    # ── STATUS GERAL (agregado) / HAVING ──────────────────────────────────────
    # Regras do status_geral:
    # - FAILED   se qualquer linha status='FAILED'
    # - WARNING  se não tem FAILED e qualquer WARNING
    # - RUNNING  se não tem FAILED/WARNING e qualquer RUNNING
    # - SUCCESS  se não tem acima e existe SUCCESS
    # - DESCONHECIDO caso contrário
    status_expr = """
        CASE
            WHEN SUM(CASE WHEN status = 'FAILED'  THEN 1 ELSE 0 END) > 0 THEN 'FAILED'
            WHEN SUM(CASE WHEN status = 'WARNING' THEN 1 ELSE 0 END) > 0 THEN 'WARNING'
            WHEN SUM(CASE WHEN status = 'RUNNING' THEN 1 ELSE 0 END) > 0 THEN 'RUNNING'
            WHEN SUM(CASE WHEN status = 'SUCCESS' THEN 1 ELSE 0 END) > 0 THEN 'SUCCESS'
            ELSE 'DESCONHECIDO'
        END
    """

    having_sql = ""
    having_params: list[object] = []
    if filter_status:
        having_sql = f"HAVING {status_expr} = %s"
        having_params.append(filter_status)

    # ── Total (contagem de grupos) ────────────────────────────────────────────
    count_sql = f"""
        SELECT COUNT(*)
        FROM (
            SELECT execution_id, project, pipeline
            FROM dbo.etl_job_execution
            {where_sql}
            GROUP BY execution_id, project, pipeline
            {having_sql}
        ) t
    """
    total_row = hook.get_first(count_sql, parameters=(params + having_params) or None)
    total = total_row[0] if total_row else 0
    pages = _ceil_div(int(total), int(limit))

    # ── Dados agregados ───────────────────────────────────────────────────────
    data_sql = f"""
        SELECT
            execution_id,
            project,
            pipeline,
            MIN(start_time)                    AS inicio,
            MAX(end_time)                      AS fim,
            COALESCE(SUM(duration_seconds), 0) AS duracao_total_segundos,
            COUNT(*)                           AS total_jobs,
            SUM(CASE WHEN status = 'SUCCESS' THEN 1 ELSE 0 END) AS jobs_ok,
            SUM(CASE WHEN status = 'FAILED'  THEN 1 ELSE 0 END) AS jobs_falha,
            SUM(CASE WHEN status = 'WARNING' THEN 1 ELSE 0 END) AS jobs_warning,
            SUM(CASE WHEN status = 'RUNNING' THEN 1 ELSE 0 END) AS jobs_running,
            {status_expr} AS status_geral
        FROM dbo.etl_job_execution
        {where_sql}
        GROUP BY execution_id, project, pipeline
        {having_sql}
        ORDER BY MIN(start_time) DESC
        OFFSET %s ROWS FETCH NEXT %s ROWS ONLY
    """

    all_params = (params + having_params + [offset, limit]) if (params or having_params) else [offset, limit]
    rows = hook.get_records(data_sql, parameters=all_params)

    data = [
        {
            "execution_id": r[0],
            "project": r[1],
            "pipeline": r[2],
            "inicio": _fmt_dt(r[3]),
            "fim": _fmt_dt(r[4]),
            "duracao_total_segundos": int(r[5] or 0),
            "total_jobs": int(r[6] or 0),
            "jobs_ok": int(r[7] or 0),
            "jobs_falha": int(r[8] or 0),
            "jobs_warning": int(r[9] or 0),
            "jobs_running": int(r[10] or 0),
            "status_geral": r[11],
        }
        for r in rows
    ]

    result = {
        "total": int(total),
        "offset": int(offset),
        "limit": int(limit),
        "pages": int(pages),
        "filters": {
            "project": filter_project,
            "pipeline": filter_pipeline,
            "status": filter_status,
            "date_from": filter_date_from,
            "date_to": filter_date_to,
        },
        "data": data,
    }

    print(f"[{DAG_ID}] total={total} | offset={offset} | limit={limit} | retornando={len(data)}")
    return result  # vai para XCom key='return_value'


with DAG(
    dag_id=DAG_ID,
    default_args=default_args,
    description="Consulta paginada de logs de execução — retorna JSON via XCom",
    start_date=pendulum.datetime(2026, 1, 1, tz=LOCAL_TZ),
    schedule=None,
    catchup=False,
    tags=["orquestra", "logs", "query"],
    access_control={"Op": {"can_read", "can_edit"}},
) as dag:
    consultar_logs_task = PythonOperator(
        task_id="consultar_logs",
        python_callable=consultar_logs,
        do_xcom_push=True,
    )

