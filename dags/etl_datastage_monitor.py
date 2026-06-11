"""
etl_datastage_monitor.py

DAG de monitoramento manual de jobs DataStage.

Disparado via ORQUESTRA (ou trigger manual no Airflow) com:
  {
    "project":       "BI_VIDA",
    "job_name":      "SeqExecCargaVida",
    "poll_interval": 60    (opcional, default 60s)
  }

Comportamento:
  - Anexa ao job em execução sem disparar um novo run
  - Faz polling a cada poll_interval segundos
  - Persiste snapshots em etl_ds_job_log (visível no ORQUESTRA)
  - Retorna status final, child jobs e logsum via XCom
  - Se o job não está rodando: registra o estado atual e encerra normalmente

Não usar para disparar jobs — use as DAGs geradas pelo factory.
"""

from __future__ import annotations

import pendulum
from airflow import DAG
from airflow.operators.python import PythonOperator

DAG_ID        = "etl_datastage_monitor"
SSH_CONN_ID   = "ssh_lnxprd021"
MSSQL_CONN_ID = "SQL14_DMDB41"
LOCAL_TZ      = "America/Sao_Paulo"
DSHOME        = "/opt/IBM/InformationServer/Server/DSEngine"

default_args = {"owner": "airflow", "depends_on_past": False, "retries": 0}


def _run_monitor(**context):
    """
    Instancia DataStageOperator em modo attach_only e executa inline.
    Recebe parâmetros via dag_run.conf.
    """
    conf         = context["dag_run"].conf or {}
    project      = conf.get("project", "BI_VIDA")
    job_name     = conf.get("job_name")
    poll_interval = int(conf.get("poll_interval", 60))

    if not job_name:
        raise ValueError(
            "Parâmetro 'job_name' obrigatório. "
            "Exemplo: {\"project\": \"BI_VIDA\", \"job_name\": \"SeqExecCargaVida\"}"
        )

    print(f"[MONITOR] Iniciando monitoramento: {project}/{job_name}")
    print(f"[MONITOR] poll_interval={poll_interval}s")

    from utils.datastage_operator import DataStageOperator

    op = DataStageOperator(
        task_id="monitor_inline",
        project=project,
        job_name=job_name,
        ssh_conn_id=SSH_CONN_ID,
        mssql_conn_id=MSSQL_CONN_ID,
        dshome=DSHOME,
        poll_interval=poll_interval,
        attach_only=True,
        pipeline_name=DAG_ID,
    )

    result = op.execute(context)

    import json
    data = json.loads(result)
    print("\n" + "=" * 60)
    print(f"[MONITOR] Resultado final: {data['status']} (code={data['status_code']})")
    print(f"[MONITOR] Wave: {data.get('wave_number')}  PID: {data.get('pid')}")
    print(f"[MONITOR] Jobs filhos: {len(data.get('child_jobs', []))}")
    for cj in data.get("child_jobs", []):
        icon = {"1": "OK", "2": "WARN", "3": "FAIL"}.get(str(cj.get("status_code")), "?")
        print(f"  [{icon}] {cj['name']:50s}  {cj.get('status', '')}")
    print("=" * 60)

    context["ti"].xcom_push(key="ds_monitor_result", value=result)
    return result


with DAG(
    dag_id=DAG_ID,
    default_args=default_args,
    description="Monitora job DataStage em execução — disparar via ORQUESTRA com {project, job_name}",
    start_date=pendulum.datetime(2024, 1, 1, tz=LOCAL_TZ),
    schedule=None,
    catchup=False,
    tags=["datastage", "monitor", "infraestrutura"],
) as dag:

    task_monitor = PythonOperator(
        task_id="monitorar_job",
        python_callable=_run_monitor,
    )
