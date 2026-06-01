"""
etl_lineage_query.py
====================
Consulta de lineage para a aba "Governança".

Conf esperado:
{
  "pipeline_name": "datastage_cobranca_diario"
}

Retorna via XCom (task: consultar_lineage):
{
  "pipeline_name": "...",
  "jobs": [
    {
      "execution_order": 1,
      "job_name": "job_x",
      "job_type": "datastage",
      "origens":  [ { "object_name": "...", "object_type": "...", "stage_name": "...", "database_name": "...", "extraction_method": "..." }, ... ],
      "destinos": [ ... ]
    }
  ]
}
"""

from __future__ import annotations

import pendulum
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.microsoft.mssql.hooks.mssql import MsSqlHook

DAG_ID = "etl_lineage_query"
MSSQL_CONN_ID = "SQL14_DMDB41"
LOCAL_TZ = "America/Sao_Paulo"

default_args = {"owner": "airflow", "depends_on_past": False, "retries": 0}


def consultar_lineage(**context):
    conf = context["dag_run"].conf or {}
    pipeline_name = (conf.get("pipeline_name") or "").strip()
    if not pipeline_name:
        raise ValueError("pipeline_name é obrigatório.")

    hook = MsSqlHook(mssql_conn_id=MSSQL_CONN_ID)

    sql = """
        SELECT
            j.execution_order,
            j.job_name,
            j.job_type,
            l.direction,
            l.object_name,
            l.object_type,
            l.stage_name,
            l.database_name,
            l.extraction_method
        FROM dbo.etl_pipeline_job j
        LEFT JOIN dbo.etl_job_lineage l
               ON l.pipeline_name = j.pipeline_name
              AND l.job_name = j.job_name
        WHERE j.pipeline_name = %s
        ORDER BY j.execution_order, j.job_name
    """

    rows = hook.get_records(sql, parameters=[pipeline_name])

    # agrega por job
    jobs_map: dict[str, dict] = {}
    for r in rows or []:
        order, job_name, job_type, direction, obj_name, obj_type, stage_name, db_name, extraction_method = r

        if job_name not in jobs_map:
            jobs_map[job_name] = {
                "execution_order": int(order or 0),
                "job_name": job_name,
                "job_type": job_type,
                "origens": [],
                "destinos": [],
            }

        if obj_name is None:
            continue

        item = {
            "object_name": obj_name,
            "object_type": obj_type,
            "stage_name": stage_name,
            "database_name": db_name,
            "extraction_method": extraction_method,
        }

        if direction == "origem":
            jobs_map[job_name]["origens"].append(item)
        elif direction == "destino":
            jobs_map[job_name]["destinos"].append(item)

    # ordena por execution_order (e nome)
    jobs = sorted(jobs_map.values(), key=lambda x: (x["execution_order"], x["job_name"]))

    return {"pipeline_name": pipeline_name, "jobs": jobs}


with DAG(
    dag_id=DAG_ID,
    default_args=default_args,
    description="Consulta lineage (job e pipeline) para Governança — via XCom",
    start_date=pendulum.datetime(2026, 1, 1, tz=LOCAL_TZ),
    schedule=None,
    catchup=False,
    tags=["orquestra", "lineage", "governanca", "query"],
    access_control={"Op": {"can_read", "can_edit"}},
) as dag:
    PythonOperator(
        task_id="consultar_lineage",
        python_callable=consultar_lineage,
        do_xcom_push=True,
    )

