"""
ORQUESTRA — Importação de Sequence (v1.0)

DAG: etl_sequence_import_approve
Objetivo:
  - receber ajustes do usuário (pipeline_name_override, schedule, jobs renomeados/ignorados)
  - atualizar staging (etl_seq_import / etl_seq_import_job)
  - executar dbo.sp_etl_seq_import_approve

Entrada (dag_run.conf):
  import_id: int (obrigatório)
  reviewed_by: str (obrigatório)
  pipeline_name_override: str (opcional)
  domain: str (opcional)
  schedule_type/hour/minute/dow/dom (opcional)
  jobs: [
    { import_job_id: int, job_name_orq: str, ignored: 0|1 }
  ] (opcional)
"""

from __future__ import annotations

import os
from datetime import datetime

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.microsoft.mssql.hooks.mssql import MsSqlHook


MSSQL_CONN_ID = os.environ.get("MSSQL_CONN_ID", "SQL14_DMDB41")
default_args = {"owner": "airflow", "depends_on_past": False, "retries": 0}


def approve_sequence(**context):
    conf = context["dag_run"].conf or {}
    import_id = conf.get("import_id")
    reviewed_by = (conf.get("reviewed_by") or "").strip()
    if not import_id or not reviewed_by:
        raise ValueError("conf.import_id e conf.reviewed_by são obrigatórios")

    hook = MsSqlHook(mssql_conn_id=MSSQL_CONN_ID)

    # Atualiza header (override + domain + schedule)
    pipeline_override = conf.get("pipeline_name_override")
    domain = conf.get("domain")
    schedule_type = conf.get("schedule_type")
    schedule_hour = conf.get("schedule_hour")
    schedule_minute = conf.get("schedule_minute")
    schedule_dow = conf.get("schedule_dow")
    schedule_dom = conf.get("schedule_dom")
    scheduled_time = conf.get("scheduled_time")  # opcional

    upd_cols = []
    params = []
    if pipeline_override is not None:
        upd_cols.append("pipeline_name_override = %s")
        params.append(pipeline_override)
    if domain is not None:
        upd_cols.append("domain = %s")
        params.append(domain)
    if schedule_type is not None:
        upd_cols.append("schedule_type = %s")
        params.append(schedule_type)
    if schedule_hour is not None:
        upd_cols.append("schedule_hour = %s")
        params.append(schedule_hour)
    if schedule_minute is not None:
        upd_cols.append("schedule_minute = %s")
        params.append(schedule_minute)
    if schedule_dow is not None:
        upd_cols.append("schedule_dow = %s")
        params.append(schedule_dow)
    if schedule_dom is not None:
        upd_cols.append("schedule_dom = %s")
        params.append(schedule_dom)
    if scheduled_time is not None:
        upd_cols.append("scheduled_time = %s")
        params.append(scheduled_time)

    if upd_cols:
        sql = f"UPDATE dbo.etl_seq_import SET {', '.join(upd_cols)}, updated_at = SYSDATETIME() WHERE id = %s"
        params.append(import_id)
        hook.run(sql, parameters=tuple(params))

    # Atualiza jobs (rename/ignore)
    jobs = conf.get("jobs") or []
    for j in jobs:
        jid = j.get("import_job_id")
        if not jid:
            continue
        jname = j.get("job_name_orq")
        ignored = j.get("ignored")
        cols = []
        p = []
        if jname is not None:
            cols.append("job_name_orq = %s")
            p.append(jname)
        if ignored is not None:
            cols.append("ignored = %s")
            p.append(int(ignored))
        if cols:
            p.extend([import_id, jid])
            hook.run(
                f"UPDATE dbo.etl_seq_import_job SET {', '.join(cols)} WHERE import_id = %s AND id = %s",
                parameters=tuple(p),
            )

    # Aprova (staging -> produção)
    hook.run("EXEC dbo.sp_etl_seq_import_approve @import_id=%s, @reviewed_by=%s", parameters=(import_id, reviewed_by))

    # Retorna pipeline final
    row = hook.get_first(
        "SELECT COALESCE(NULLIF(pipeline_name_override,''), NULLIF(pipeline_name_suggest,'')) FROM dbo.etl_seq_import WHERE id=%s",
        parameters=(import_id,),
    )
    pipeline_name = row[0] if row else None
    return {"import_id": import_id, "pipeline_name": pipeline_name, "status": "aprovado"}


with DAG(
    dag_id="etl_sequence_import_approve",
    default_args=default_args,
    start_date=datetime(2026, 1, 1),
    schedule_interval=None,
    catchup=False,
    tags=["ORQUESTRA", "SEQUENCE", "IMPORT"],
) as dag:
    t_approve = PythonOperator(
        task_id="approve_sequence",
        python_callable=approve_sequence,
        provide_context=True,
    )

