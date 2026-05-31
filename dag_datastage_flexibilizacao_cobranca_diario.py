from airflow import DAG
from airflow.providers.ssh.operators.ssh import SSHOperator
from airflow.operators.python import PythonOperator
from airflow.providers.microsoft.mssql.hooks.mssql import MsSqlHook
from airflow.utils.trigger_rule import TriggerRule
from airflow.utils.state import State
from airflow.models import Variable

import pendulum
import socket
import re
import requests

# =========================
# CONFIGURAÇÕES
# =========================
DAG_ID = "datastage_flexibilizacao_cobranca_diario"
SSH_CONN_ID = "ssh_lnxprd021"

MSSQL_CONN_ID = "SQL14_DMDB41"
SP_NAME = "dbo.sp_etl_job_execution_log"

PROJECT_NAME = "BI_CVP"
PIPELINE_NAME = "datastage_flexibilizacao_cobranca_diario"
BASE_LOG_DIR = "/Projetos/BI_CVP/Logs/Airflow"

LOCAL_TZ = "America/Sao_Paulo"

TEAMS_WEBHOOK_VAR = "TEAMS_WEBHOOK_URL_CVP"

default_args = {
    "owner": "airflow",
    "depends_on_past": False,
    "retries": 0,
}

JOBS = [
    "BiCvp_BaseCobranca_00_ext_Parcelas_Pagas",
    "BiCvp_BaseCobranca_01_ins_Parcelas_Pagas",
    "BiCvp_BaseCobranca_02_ext_Parcelas_Clientes",
    "BiCvp_BaseCobranca_03_ins_Parcelas_Clientes",
]

# =========================
# FUNÇÕES AUXILIARES
# =========================
def _now_str():
    return pendulum.now(LOCAL_TZ).to_datetime_string()  # "YYYY-MM-DD HH:MM:SS"


def _build_log_file(job_name: str, execution_id: str) -> str:
    return f"{BASE_LOG_DIR}/{PROJECT_NAME}/{job_name}/{job_name}_{execution_id}.log"


def _extract_status_code(stdout: str):
    if not stdout:
        return None

    json_matches = re.findall(r'"status_code"\s*:\s*(-?\d+)', stdout)
    if json_matches:
        return int(json_matches[-1])

    m = re.search(r'Job Status Code:\s*(-?\d+)', stdout)
    if m:
        return int(m.group(1))

    raw_matches = re.findall(r'Status code\s*=\s*(-?\d+)', stdout)
    if raw_matches:
        return int(raw_matches[-1])

    return None


def _status_from_code(code: int | None, upstream_state: str | None):
    if code == 1:
        return "SUCCESS"
    if code == 2:
        return "WARNING"
    if code is not None:
        return "FAILED"
    if upstream_state == State.SUCCESS:
        return "SUCCESS"
    return "FAILED"


def _exec_telemetry(
    hook: MsSqlHook,
    execution_id: str,
    job_name: str,
    task_key: str,
    status: str,
    start_time: str,
    end_time: str,
    duration_seconds: int,
    log_file: str,
    host: str = None,
):
    """
    Chama a SP com parâmetros (sem GETDATE() inline) para evitar erro de sintaxe.
    """
    if host is None:
        host = socket.gethostname()

    sql = f"""
    EXEC {SP_NAME}
        @execution_id=%s,
        @project=%s,
        @job_name=%s,
        @pipeline=%s,
        @host=%s,
        @start_time=%s,
        @end_time=%s,
        @duration_seconds=%s,
        @status=%s,
        @log_file=%s,
        @task_id=%s
    """

    params = (
        execution_id,
        PROJECT_NAME,
        job_name,
        PIPELINE_NAME,
        host,
        start_time or "",
        end_time or "",
        duration_seconds,
        status,
        log_file,
        task_key,
    )

    hook.run(sql, parameters=params)


def _update_status_code(hook: MsSqlHook, execution_id: str, job_name: str, task_key: str, status_code: int | None):
    sql = """
    UPDATE dbo.etl_job_execution
       SET status_code = %s,
           updated_at = GETDATE()
     WHERE execution_id = %s
       AND job_name = %s
       AND task_id = %s
    """
    params = (status_code, execution_id, job_name, task_key)
    hook.run(sql, parameters=params)


# =========================
# TEAMS (Adaptive Card via Workflows Webhook)
# =========================
def _teams_post_card(title: str, lines: list[str], status: str = "INFO"):
    try:
        webhook_url = Variable.get(TEAMS_WEBHOOK_VAR)
    except Exception:
        print(f"[TEAMS] Airflow Variable '{TEAMS_WEBHOOK_VAR}' não encontrada. Pulando envio.")
        return

    emoji = {"SUCCESS": "🟢", "WARNING": "🟡", "FAILED": "🔴", "INFO": "🔵"}.get(status, "🔵")
    body_text = "\n".join(lines)

    payload = {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.4",
                    "body": [
                        {"type": "TextBlock", "text": f"{emoji} {title}", "size": "Large", "weight": "Bolder", "wrap": True},
                        {"type": "TextBlock", "text": body_text, "wrap": True},
                    ],
                },
            }
        ],
    }

    try:
        resp = requests.post(webhook_url, json=payload, timeout=15)
        print(f"[TEAMS] status={resp.status_code}")
    except Exception as e:
        print(f"[TEAMS] Falha ao enviar alerta: {e}")


def teams_start(**context):
    execution_id = context["ts_nodash"]
    lines = [
        f"Processo: {PIPELINE_NAME}",
        "Execução iniciada",
        "",
        f"🆔 Execução: {execution_id}",
        f"⏱️ Início: {_now_str()}",
    ]
    _teams_post_card(title="Execução iniciada", lines=lines, status="INFO")


def teams_end(**context):
    """
    Consolida status e tempos com query robusta (sem MAX(status)).
    """
    execution_id = context["ts_nodash"]
    hook = MsSqlHook(mssql_conn_id=MSSQL_CONN_ID)

    row = hook.get_first(
        """
        SELECT
            pipeline,
            MIN(start_time) AS inicio,
            MAX(end_time) AS fim,
            COALESCE(SUM(duration_seconds), 0) AS duracao_total_segundos,
            CASE
                WHEN SUM(CASE WHEN status = 'FAILED' THEN 1 ELSE 0 END) > 0 THEN 'FAILED'
                WHEN SUM(CASE WHEN status = 'WARNING' THEN 1 ELSE 0 END) > 0 THEN 'WARNING'
                WHEN SUM(CASE WHEN status = 'SUCCESS' THEN 1 ELSE 0 END) > 0 THEN 'SUCCESS'
                ELSE 'FAILED'
            END AS status_geral
        FROM dbo.etl_job_execution
        WHERE execution_id = %s
          AND pipeline = %s
        GROUP BY pipeline
        """,
        parameters=(execution_id, PIPELINE_NAME),
    )

    if not row:
        _teams_post_card(
            title="Execução finalizada",
            lines=[f"Processo: {PIPELINE_NAME}", "Sem dados no banco para esta execução."],
            status="FAILED",
        )
        return

    pipeline, inicio, fim, duracao_seg, status_geral = row

    status_text_map = {
        "SUCCESS": "Finalizado com sucesso ✅",
        "WARNING": "Finalizado com avisos ⚠️",
        "FAILED": "Falha na execução ❌",
    }
    status_text = status_text_map.get(status_geral, "Status desconhecido")

    inicio_str = inicio.strftime("%d/%m/%Y %H:%M") if inicio else "-"
    fim_str = fim.strftime("%d/%m/%Y %H:%M") if fim else "-"
    duracao_min = int(duracao_seg / 60) if duracao_seg else 0

    lines = [
        f"Processo: {pipeline}",
        status_text,
        "",
        f"⏱️ Início: {inicio_str}",
        f"🏁 Fim: {fim_str}",
        f"⏳ Duração: {duracao_min} min",
    ]

    _teams_post_card(title="Execução finalizada", lines=lines, status=status_geral)


# =========================
# TELEMETRIA START/END POR JOB
# =========================
def log_start(job_name: str, task_key: str, **context):
    hook = MsSqlHook(mssql_conn_id=MSSQL_CONN_ID)
    execution_id = context["ts_nodash"]

    start_time = _now_str()
    log_file = _build_log_file(job_name, execution_id)

    _exec_telemetry(
        hook=hook,
        execution_id=execution_id,
        job_name=job_name,
        task_key=task_key,
        status="RUNNING",
        start_time=start_time,   # <-- SEM GETDATE()
        end_time="",
        duration_seconds=0,
        log_file=log_file,
    )


def log_end(job_name: str, task_key: str, upstream_task_id: str, **context):
    hook = MsSqlHook(mssql_conn_id=MSSQL_CONN_ID)
    execution_id = context["ts_nodash"]

    end_time = _now_str()
    log_file = _build_log_file(job_name, execution_id)

    job_ti = context["dag_run"].get_task_instance(upstream_task_id)
    upstream_state = job_ti.state if job_ti else None

    ti = context["ti"]
    stdout = ti.xcom_pull(task_ids=upstream_task_id)
    stdout_str = stdout if isinstance(stdout, str) else str(stdout)

    status_code = _extract_status_code(stdout_str)
    final_status = _status_from_code(status_code, upstream_state)

    duration_seconds = 0
    if job_ti and job_ti.start_date and job_ti.end_date:
        duration_seconds = int((job_ti.end_date - job_ti.start_date).total_seconds())

    _exec_telemetry(
        hook=hook,
        execution_id=execution_id,
        job_name=job_name,
        task_key=task_key,
        status=final_status,
        start_time="",        # mantém o start gravado no primeiro call
        end_time=end_time,    # <-- SEM GETDATE()
        duration_seconds=duration_seconds,
        log_file=log_file,
    )

    _update_status_code(hook, execution_id, job_name, task_key, status_code)


# =========================
# DAG
# =========================
with DAG(
    dag_id=DAG_ID,
    default_args=default_args,
    description="Executa Carga de Parcelas Pendentes para o Portal Economiario - Menu Adimplencia",
    start_date=pendulum.datetime(2026, 5, 25, tz=LOCAL_TZ),
    schedule_interval="0 9 * * *",
    catchup=False,
    tags=["datastage", "PortalEconomiario"],
) as dag:

    # 1) Primeiro job: log_start -> teams_start -> job -> log_end
    first_job = JOBS[0]
    task_key = first_job

    t_start_first = PythonOperator(
        task_id=f"log_start_{first_job}",
        python_callable=log_start,
        op_kwargs={"job_name": first_job, "task_key": task_key},
    )

    t_teams_start = PythonOperator(
        task_id="teams_start",
        python_callable=teams_start,
    )

    t_job_first = SSHOperator(
        task_id=first_job,
        ssh_conn_id=SSH_CONN_ID,
        command=(
            "/Projetos/BI_CVP/Scripts/Airflow/run_datastage_job.sh "
            f"{PROJECT_NAME} {first_job} "
            "{{ ts_nodash }} "
            f"{PIPELINE_NAME} "
            "{{ task_instance.task_id }}"
        ),
        cmd_timeout=None,
        do_xcom_push=True,
    )

    t_end_first = PythonOperator(
        task_id=f"log_end_{first_job}",
        python_callable=log_end,
        op_kwargs={"job_name": first_job, "task_key": task_key, "upstream_task_id": first_job},
        trigger_rule=TriggerRule.ALL_DONE,
    )

    t_start_first >> t_teams_start >> t_job_first >> t_end_first

    previous = t_end_first
    end_tasks = [t_end_first]

    # 2) Demais jobs
    for job in JOBS[1:]:
        task_key = job

        t_start = PythonOperator(
            task_id=f"log_start_{job}",
            python_callable=log_start,
            op_kwargs={"job_name": job, "task_key": task_key},
        )

        t_job = SSHOperator(
            task_id=job,
            ssh_conn_id=SSH_CONN_ID,
            command=(
                "/Projetos/BI_CVP/Scripts/Airflow/run_datastage_job.sh "
                f"{PROJECT_NAME} {job} "
                "{{ ts_nodash }} "
                f"{PIPELINE_NAME} "
                "{{ task_instance.task_id }}"
            ),
            cmd_timeout=None,
            do_xcom_push=True,
        )

        t_end = PythonOperator(
            task_id=f"log_end_{job}",
            python_callable=log_end,
            op_kwargs={"job_name": job, "task_key": task_key, "upstream_task_id": job},
            trigger_rule=TriggerRule.ALL_DONE,
        )

        previous >> t_start >> t_job >> t_end
        previous = t_end
        end_tasks.append(t_end)

    # 3) Teams END após o último log_end
    t_teams_end = PythonOperator(
        task_id="teams_end",
        python_callable=teams_end,
        trigger_rule=TriggerRule.ALL_DONE,
    )

    end_tasks >> t_teams_end