"""
etl_performance_monitor.py
=========================
DAG agendada a cada hora (minuto 0).

Objetivo:
- Verificar pipelines RUNNING que ultrapassaram 3h / 6h / 12h.
- Inserir snapshots em dbo.etl_pipeline_performance_snapshot evitando duplicatas.

Regra anti-duplicata:
- Não insere novamente o mesmo (execution_id, alerta_horas) no mesmo dia.
"""

from __future__ import annotations

import pendulum
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.microsoft.mssql.hooks.mssql import MsSqlHook

DAG_ID = "etl_performance_monitor"
MSSQL_CONN_ID = "SQL14_DMDB41"
LOCAL_TZ = "America/Sao_Paulo"
LIMIARES = [3, 6, 12]  # horas

default_args = {"owner": "airflow", "depends_on_past": False, "retries": 0}


def monitorar_performance(**context):
    hook = MsSqlHook(mssql_conn_id=MSSQL_CONN_ID)

    # Busca execuções com RUNNING >= 3h (agregado por execução)
    running_sql = """
        SELECT
            pipeline,
            project,
            execution_id,
            DATEDIFF(SECOND, MIN(start_time), GETDATE()) AS elapsed_seconds
        FROM dbo.etl_job_execution
        WHERE status = 'RUNNING'
        GROUP BY pipeline, project, execution_id
        HAVING DATEDIFF(HOUR, MIN(start_time), GETDATE()) >= 3
        ORDER BY MIN(start_time) ASC
    """
    rows = hook.get_records(running_sql)
    if not rows:
        print("[MONITOR] Nenhum pipeline em alerta.")
        return {"checked": 0, "inserted": 0}

    insert_sql = """
        INSERT INTO dbo.etl_pipeline_performance_snapshot
            (pipeline, project, execution_id, alerta_horas, elapsed_seconds)
        SELECT %s, %s, %s, %s, %s
        WHERE NOT EXISTS (
            SELECT 1
            FROM dbo.etl_pipeline_performance_snapshot
            WHERE execution_id = %s
              AND alerta_horas = %s
              AND CAST(snapshot_at AS DATE) = CAST(GETDATE() AS DATE)
        )
    """

    inserted = 0
    checked = 0

    for pipeline, project, exec_id, elapsed_seconds in rows:
        checked += 1
        elapsed_h = int(elapsed_seconds or 0) // 3600

        # Insere um snapshot por limiar atingido (3/6/12), mantendo histórico
        for limiar in LIMIARES:
            if elapsed_h >= limiar:
                params = (
                    pipeline,
                    project,
                    exec_id,
                    limiar,
                    int(elapsed_seconds or 0),
                    exec_id,
                    limiar,
                )
                hook.run(insert_sql, parameters=params)
                inserted += 1

        print(
            f"[MONITOR] {pipeline} | exec={exec_id} | elapsed={elapsed_seconds}s | limiar_max={max([l for l in LIMIARES if elapsed_h >= l] or [0])}h"
        )

    print(f"[MONITOR] Total verificado: {checked} | Inserts tentados: {inserted}")
    return {"checked": checked, "inserted": inserted}


with DAG(
    dag_id=DAG_ID,
    default_args=default_args,
    description="Monitor horário de performance — snapshots 3h/6h/12h",
    start_date=pendulum.datetime(2026, 1, 1, tz=LOCAL_TZ),
    schedule="0 * * * *",
    catchup=False,
    tags=["orquestra", "monitor", "performance"],
    access_control={"Op": {"can_read", "can_edit"}},
) as dag:
    PythonOperator(task_id="monitorar_performance", python_callable=monitorar_performance, do_xcom_push=True)

