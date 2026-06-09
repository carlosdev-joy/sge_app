"""
etl_lineage_query.py
====================
Consulta de lineage para a aba "Governança" (Fase 2).

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
      "origens":  [ ... ],
      "transformacoes": [ ... ],
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


def _fmt(val):
    if val is None:
        return None
    if hasattr(val, "strftime"):
        return val.strftime("%Y-%m-%d %H:%M:%S")
    return str(val)


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
            COALESCE(m.type_label, l.object_type) AS object_type,
            COALESCE(m.type_label, l.stage_type_raw) AS type_label,
            m.type_category,
            m.role_hint,
            l.stage_name,
            l.stage_type_raw,
            l.database_name,
            l.sql_expression,
            l.file_path,
            l.dsx_source_file,
            l.extracted_at,
            l.extraction_method,
            l.columns_json
        FROM dbo.etl_pipeline_job j
        LEFT JOIN dbo.etl_job_lineage l
               ON l.pipeline_name = j.pipeline_name
              AND l.job_name = j.job_name
        LEFT JOIN dbo.etl_stage_type_map m
               ON m.stage_type = l.stage_type_raw
        WHERE j.pipeline_name = %s
        ORDER BY
            j.execution_order,
            j.job_name,
            CASE l.direction
                WHEN 'origem'        THEN 1
                WHEN 'INPUT'         THEN 1
                WHEN 'transformacao' THEN 2
                WHEN 'destino'       THEN 3
                WHEN 'OUTPUT'        THEN 3
                ELSE 9
            END,
            l.object_name
    """

    rows = hook.get_records(sql, parameters=[pipeline_name])

    # agrega por job
    jobs_map: dict[str, dict] = {}
    for r in rows or []:
        (
            order,
            job_name,
            job_type,
            direction,
            obj_name,
            obj_type,
            type_label,
            type_category,
            role_hint,
            stage_name,
            stage_type_raw,
            db_name,
            sql_expression,
            file_path,
            dsx_source_file,
            extracted_at,
            extraction_method,
            columns_json,
        ) = r

        if job_name not in jobs_map:
            jobs_map[job_name] = {
                "execution_order": int(order or 0),
                "job_name": job_name,
                "job_type": job_type,
                "origens": [],
                "transformacoes": [],
                "destinos": [],
            }

        if obj_name is None:
            continue

        import json as _json  # noqa: PLC0415
        try:
            cols = _json.loads(columns_json) if columns_json else []
        except Exception:
            cols = []

        item = {
            "object_name":      obj_name,
            "object_type":      obj_type,
            "stage_name":       stage_name,
            "stage_type_raw":   stage_type_raw,
            "type_label":       type_label,
            "type_category":    type_category,
            "role_hint":        role_hint,
            "database_name":    db_name,
            "sql_expression":   sql_expression,
            "file_path":        file_path,
            "dsx_source_file":  dsx_source_file,
            "extracted_at":     _fmt(extracted_at),
            "extraction_method": extraction_method,
            "columns":          cols,
        }

        dir_norm = (direction or "").lower()
        if dir_norm in ("origem", "input"):
            jobs_map[job_name]["origens"].append(item)
        elif dir_norm == "transformacao":
            jobs_map[job_name]["transformacoes"].append(item)
        elif dir_norm in ("destino", "output"):
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

