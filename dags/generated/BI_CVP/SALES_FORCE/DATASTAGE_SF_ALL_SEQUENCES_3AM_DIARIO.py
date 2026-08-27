from airflow import DAG
from datetime import timedelta
from utils.datastage_operator import DataStageOperator
from airflow.operators.python import PythonOperator, ShortCircuitOperator
from airflow.operators.empty import EmptyOperator
from airflow.datasets import Dataset
from airflow.providers.microsoft.mssql.hooks.mssql import MsSqlHook
from airflow.utils.trigger_rule import TriggerRule
from airflow.utils.state import State
from airflow.models import Variable

import pendulum
import socket
import re
import requests
# =========================
# Gerado automaticamente por etl_dag_factory
# Pipeline: DATASTAGE_SF_ALL_SEQUENCES_3AM_DIARIO | Projeto: BI_CVP | Dominio: SALES_FORCE
# =========================
DAG_ID        = "DATASTAGE_SF_ALL_SEQUENCES_3AM_DIARIO"
SSH_CONN_ID   = "ssh_lnxprd021"
MSSQL_CONN_ID = "SQL14_DMDB41"
PROJECT_NAME  = "BI_CVP"
DOMAIN        = "SALES_FORCE"
PIPELINE_NAME = "DATASTAGE_SF_ALL_SEQUENCES_3AM_DIARIO"
BASE_LOG_DIR  = "/Projetos/BI_CVP/Logs/Airflow"
LOCAL_TZ      = "America/Sao_Paulo"
TEAMS_WEBHOOK_VAR = "TEAMS_WEBHOOK_URL_CVP"
DS_QUEUE      = 'MediumPriorityJobs'
RUNBOOK_MD    = None
CALENDARIO_NOME    = None
SOMENTE_DIAS_UTEIS = False
HORARIOS_ESPECIFICOS = None
DATASET_URI   = "orq://pipeline/DATASTAGE_SF_ALL_SEQUENCES_3AM_DIARIO"
default_args  = {"owner": "airflow", "depends_on_past": False, "retries": 3, "retry_delay": timedelta(seconds=300)}
JOBS          = ['SEQ_SF_CONTRACT', 'SEQ_SF_CASE', 'SEQ_SF_CASE_TASK', 'SEQ_SF_ADM_ASSUNTOS', 'SEQ_SF_LIVECHATBUTTON', 'SEQ_SF_LIVECHATTRANSCRIPT', 'SEQ_SF_LIVECHATTRANSCRIPTEVENT', 'SEQ_SF_LIVECHATVISITOR', 'SEQ_SF_PROFILE', 'SEQ_SF_PROTOCOLO', 'SEQ_SF_SURVEY_C', 'SEQ_SF_SURVEY_QUESTION', 'SEQ_SF_SURVEY_RESPONSE', 'SEQ_SF_SURVEY_TAKER_C', 'SEQ_SF_USER', 'SEQ_SF_USERROLE']

def _now_str():
    return pendulum.now(LOCAL_TZ).to_datetime_string()

def _build_log_file(job_name, execution_id):
    return f"{BASE_LOG_DIR}/{PROJECT_NAME}/{job_name}/{job_name}_{execution_id}.log"

def _extract_status_code(stdout):
    if not stdout: return None
    json_m = re.findall(r"\"status_code\"\s*:\s*(-?\d+)", stdout)
    if json_m: return int(json_m[-1])
    m = re.search(r"Job Status Code:\s*(-?\d+)", stdout)
    if m: return int(m.group(1))
    raw_m = re.findall(r"Status code\s*=\s*(-?\d+)", stdout)
    if raw_m: return int(raw_m[-1])
    return None

def _status_from_code(code, upstream_state):
    if code == 1:  return "SUCCESS"
    if code == 2:  return "SUCCESS"  # WARNING = finalizou, conta como sucesso
    if code is not None: return "FAILED"
    if upstream_state == State.SUCCESS: return "SUCCESS"
    return "FAILED"

def _exec_telemetry(hook, execution_id, job_name, task_key, status,
                    start_time, end_time, duration_seconds, log_file, host=None):
    if host is None:
        host = socket.gethostname()
    sql = (
        "EXEC dbo.sp_etl_job_execution_log "
        "@execution_id=%s, @project=%s, @job_name=%s, @pipeline=%s, "
        "@host=%s, @start_time=%s, @end_time=%s, @duration_seconds=%s, "
        "@status=%s, @log_file=%s, @task_id=%s"
    )
    hook.run(sql, parameters=(
        execution_id, PROJECT_NAME, job_name, PIPELINE_NAME,
        host, start_time or "", end_time or "",
        duration_seconds, status, log_file, task_key,
    ))

def _update_status_code(hook, execution_id, job_name, task_key, status_code):
    hook.run(
        "UPDATE dbo.etl_job_execution SET status_code=%s, updated_at=GETDATE() "
        "WHERE execution_id=%s AND job_name=%s AND task_id=%s",
        parameters=(status_code, execution_id, job_name, task_key),
    )

def _teams_post_card(title, facts, status='INFO', subtitle=None):
    try:
        webhook_url = Variable.get(TEAMS_WEBHOOK_VAR)
    except Exception:
        print(f"[TEAMS] Variable '{TEAMS_WEBHOOK_VAR}' nao encontrada.")
        return
    icon = {"SUCCESS": "🟢", "WARNING": "🟡", "FAILED": "🔴", "INFO": "🔵"}.get(status, "⚪")
    color = {"SUCCESS": "Good", "WARNING": "Warning", "FAILED": "Attention", "INFO": "Accent"}.get(status, "Default")
    body = [
        {"type": "TextBlock", "text": f"{icon} {title}", "size": "Large", "weight": "Bolder", "wrap": True, "color": color},
    ]
    if subtitle:
        body.append({"type": "TextBlock", "text": subtitle, "wrap": True, "spacing": "None", "isSubtle": True})
    if facts:
        body.append({"type": "FactSet", "spacing": "Medium", "facts": facts})
    payload = {
        "type": "message",
        "attachments": [{
            "contentType": "application/vnd.microsoft.card.adaptive",
            "content": {
                "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                "type": "AdaptiveCard", "version": "1.4",
                "body": body,
            },
        }],
    }
    try:
        resp = requests.post(webhook_url, json=payload, timeout=15)
        print(f"[TEAMS] status={resp.status_code}")
    except Exception as e:
        print(f"[TEAMS] Falha: {e}")

def _fact(title, value):
    return {"title": title, "value": str(value) if value is not None else "—"}

def _fmt_duration(seconds):
    if not seconds: return '—'
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h: return f'{h}h {m}min {sec}s'
    if m: return f'{m}min {sec}s'
    return f'{sec}s'

def teams_start(**context):
    execution_id = context['ts_nodash']
    _teams_post_card(
        title="Execução iniciada",
        subtitle=f"O pipeline {PIPELINE_NAME} foi iniciado e está em processamento.",
        facts=[
            _fact("Pipeline",      PIPELINE_NAME),
            _fact("Domínio",       DOMAIN),
            _fact("Projeto",       PROJECT_NAME),
            _fact("Execution ID",  execution_id),
            _fact("Início",        _now_str()),
        ],
        status='INFO',
    )

def teams_end(**context):
    execution_id = context['ts_nodash']
    hook = MsSqlHook(mssql_conn_id=MSSQL_CONN_ID)
    row = hook.get_first(
        "SELECT pipeline, MIN(start_time), MAX(end_time), COALESCE(SUM(duration_seconds),0), "
        "CASE WHEN SUM(CASE WHEN status='FAILED' THEN 1 ELSE 0 END)>0 THEN 'FAILED' "
        "     WHEN SUM(CASE WHEN status='WARNING' THEN 1 ELSE 0 END)>0 THEN 'WARNING' "
        "     WHEN SUM(CASE WHEN status='SUCCESS' THEN 1 ELSE 0 END)>0 THEN 'SUCCESS' "
        "     ELSE 'FAILED' END "
        "FROM dbo.etl_job_execution WHERE execution_id=%s AND pipeline=%s GROUP BY pipeline",
        parameters=(execution_id, PIPELINE_NAME),
    )
    if not row:
        _teams_post_card(
            title="Execução finalizada — sem dados",
            subtitle=f"O pipeline {PIPELINE_NAME} foi concluído, mas não foram encontrados registros de execução.",
            facts=[_fact("Pipeline", PIPELINE_NAME), _fact("Execution ID", execution_id)],
            status='WARNING',
        )
        return
    pipeline, inicio, fim, dur_seg, status_geral = row
    titles = {"SUCCESS": "Execução concluída com sucesso", "WARNING": "Execução concluída com avisos", "FAILED": "Execução finalizada com falha"}
    subtitles = {
        "SUCCESS": f"O pipeline {pipeline} foi executado e finalizado sem erros.",
        "WARNING": f"O pipeline {pipeline} foi concluído, mas registrou avisos durante a execução.",
        "FAILED":  f"O pipeline {pipeline} foi encerrado com falha. Verifique os jobs com erro.",
    }
    _teams_post_card(
        title=titles.get(status_geral, 'Execução finalizada'),
        subtitle=subtitles.get(status_geral),
        facts=[
            _fact("Pipeline",      pipeline),
            _fact("Domínio",       DOMAIN),
            _fact("Projeto",       PROJECT_NAME),
            _fact("Execution ID",  execution_id),
            _fact("Início",        inicio.strftime('%d/%m/%Y %H:%M') if inicio else '—'),
            _fact("Fim",           fim.strftime('%d/%m/%Y %H:%M') if fim else '—'),
            _fact("Duração",       _fmt_duration(dur_seg)),
        ],
        status=status_geral,
    )

def teams_error(**context):
    execution_id = context['ts_nodash']
    hook = MsSqlHook(mssql_conn_id=MSSQL_CONN_ID)
    # Resumo do pipeline (mesma query do teams_end)
    row = hook.get_first(
        "SELECT pipeline, MIN(start_time), MAX(end_time), COALESCE(SUM(duration_seconds),0) "
        "FROM dbo.etl_job_execution WHERE execution_id=%s AND pipeline=%s GROUP BY pipeline",
        parameters=(execution_id, PIPELINE_NAME),
    )
    pipeline_nm = row[0] if row else PIPELINE_NAME
    inicio      = row[1] if row else None
    fim         = row[2] if row else None
    dur_seg     = row[3] if row else 0
    # Jobs com falha — detalhado
    try:
        failed = hook.get_records(
            "SELECT job_name, start_time, end_time, COALESCE(duration_seconds,0), log_file "
            "FROM dbo.etl_job_execution "
            "WHERE execution_id=%s AND pipeline=%s AND status='FAILED' "
            "ORDER BY start_time",
            parameters=(execution_id, PIPELINE_NAME),
        )
    except Exception:
        failed = []
    facts = [
        _fact("Pipeline",      pipeline_nm),
        _fact("Domínio",       DOMAIN),
        _fact("Projeto",       PROJECT_NAME),
        _fact("Execution ID",  execution_id),
        _fact("Início",        inicio.strftime('%d/%m/%Y %H:%M') if inicio else '—'),
        _fact("Fim",           fim.strftime('%d/%m/%Y %H:%M') if fim else '—'),
        _fact("Duração total", _fmt_duration(dur_seg)),
    ]
    if failed:
        facts.append(_fact("─────────────", "Jobs com falha"))
        for jname, jstart, jend, jdur, jlog in failed:
            facts.append(_fact("Job",     jname))
            facts.append(_fact("  Início",  jstart.strftime('%d/%m/%Y %H:%M') if jstart else '—'))
            facts.append(_fact("  Fim",     jend.strftime('%d/%m/%Y %H:%M') if jend else '—'))
            facts.append(_fact("  Duração", _fmt_duration(jdur)))
    else:
        facts.append(_fact("Job com falha", "Não identificado"))
    if RUNBOOK_MD:
        facts.append(_fact("📖 Runbook", RUNBOOK_MD[:400] + ("…" if len(RUNBOOK_MD) > 400 else "")))
    _teams_post_card(
        title="Falha na execução",
        subtitle=f"O pipeline {pipeline_nm} foi interrompido por falha em um ou mais jobs. Verifique os detalhes abaixo.",
        facts=facts,
        status='FAILED',
    )

def log_start(job_name, task_key, **context):
    hook = MsSqlHook(mssql_conn_id=MSSQL_CONN_ID)
    execution_id = context['ts_nodash']
    _exec_telemetry(hook, execution_id, job_name, task_key, 'RUNNING',
                    _now_str(), '', 0, _build_log_file(job_name, execution_id))

def _update_last_execution():
    hook = MsSqlHook(mssql_conn_id=MSSQL_CONN_ID)
    hook.run(
        "UPDATE dbo.etl_pipeline SET last_execution=GETDATE(), updated_at=GETDATE() "
        "WHERE pipeline_name=%s",
        parameters=(PIPELINE_NAME,),
    )

def log_end(job_name, task_key, upstream_task_id, **context):
    hook = MsSqlHook(mssql_conn_id=MSSQL_CONN_ID)
    execution_id = context['ts_nodash']
    end_time = _now_str()
    job_ti = context['dag_run'].get_task_instance(upstream_task_id)
    upstream_state = job_ti.state if job_ti else None
    ti = context['ti']
    stdout = ti.xcom_pull(task_ids=upstream_task_id)
    status_code = _extract_status_code(str(stdout) if stdout else '')
    final_status = _status_from_code(status_code, upstream_state)
    duration_seconds = 0
    if job_ti and job_ti.start_date and job_ti.end_date:
        duration_seconds = int((job_ti.end_date - job_ti.start_date).total_seconds())
    _exec_telemetry(hook, execution_id, job_name, task_key, final_status,
                    '', end_time, duration_seconds, _build_log_file(job_name, execution_id))
    _update_status_code(hook, execution_id, job_name, task_key, status_code)
    try:
        _update_last_execution()
    except Exception as _ule_exc:
        print(f'[log_end] Aviso: nao foi possivel atualizar last_execution — {_ule_exc}')
    if final_status in ('FAILED', 'DESCONHECIDO'):
        raise RuntimeError(
            f"Job '{job_name}' finalizou com status {final_status} — "
            "execucao interrompida. Corrija o erro antes de reprocessar."
        )

def check_agenda(**context):
    """Fase 4 — blackout/freeze, dias úteis e calendário de feriados.
    Retorna False (ShortCircuit) para pular a execução inteira."""
    # Horários específicos: o cron dispara na união minuto×hora;
    # só executa se o horário agendado estiver na lista configurada.
    if HORARIOS_ESPECIFICOS and not str(context.get('run_id', '')).startswith('manual'):
        _die = context.get('data_interval_end') or context.get('logical_date')
        if _die is not None:
            _hhmm = _die.in_timezone(LOCAL_TZ).strftime('%H:%M')
            if _hhmm not in HORARIOS_ESPECIFICOS:
                print(f"[AGENDA] {_hhmm} fora dos horarios configurados {HORARIOS_ESPECIFICOS} — execucao pulada.")
                return False
    hook = MsSqlHook(mssql_conn_id=MSSQL_CONN_ID)
    try:
        row = hook.get_first(
            "SELECT TOP 1 motivo FROM dbo.etl_blackout "
            "WHERE ativo=1 AND GETDATE() BETWEEN inicio AND fim "
            "AND (escopo IS NULL OR escopo=%s OR escopo=%s)",
            parameters=(PROJECT_NAME, PIPELINE_NAME),
        )
        if row:
            print(f"[AGENDA] Blackout vigente: {row[0]} — execucao pulada.")
            return False
    except Exception as e:
        print(f"[AGENDA] Aviso: verificacao de blackout falhou ({e}) — seguindo.")
    if SOMENTE_DIAS_UTEIS and pendulum.now(LOCAL_TZ).weekday() >= 5:
        print("[AGENDA] Fim de semana e pipeline e somente dias uteis — execucao pulada.")
        return False
    if CALENDARIO_NOME:
        try:
            row = hook.get_first(
                "SELECT TOP 1 ISNULL(descricao, '') FROM dbo.etl_calendario "
                "WHERE calendario_nome=%s AND data=CAST(GETDATE() AS DATE)",
                parameters=(CALENDARIO_NOME,),
            )
            if row is not None:
                print(f"[AGENDA] Data bloqueada no calendario {CALENDARIO_NOME} ({row[0]}) — execucao pulada.")
                return False
        except Exception as e:
            print(f"[AGENDA] Aviso: verificacao de calendario falhou ({e}) — seguindo.")
    return True

with DAG(
    dag_id=DAG_ID,
    default_args=default_args,
    description="Pipeline DATASTAGE_SF_ALL_SEQUENCES_3AM_DIARIO - BI_CVP / SALES_FORCE",
    start_date=pendulum.datetime(2026, 6, 14, tz=LOCAL_TZ),
    schedule="0 3 * * *",
    catchup=False,
    max_active_runs=1,
    tags=['BI_CVP', 'SALES_FORCE', 'DATASTAGE', 'SF', 'DIARIO'],
) as dag:

    t_check_agenda = ShortCircuitOperator(
        task_id="check_agenda",
        python_callable=check_agenda,
    )

    t_publish_dataset = EmptyOperator(
        task_id="publish_dataset",
        outlets=[Dataset(DATASET_URI)],
    )

    t_teams_start = PythonOperator(
        task_id="teams_start",
        python_callable=teams_start,
    )

    t_teams_end = PythonOperator(
        task_id="teams_end",
        python_callable=teams_end,
        trigger_rule=TriggerRule.ALL_DONE,
    )

    t_teams_error = PythonOperator(
        task_id="teams_error",
        python_callable=teams_error,
        trigger_rule=TriggerRule.ONE_FAILED,
    )

    t_start_SEQ_SF_CONTRACT = PythonOperator(
        task_id="log_start_SEQ_SF_CONTRACT",
        python_callable=log_start,
        op_kwargs={"job_name": "SEQ_SF_CONTRACT", "task_key": "SEQ_SF_CONTRACT"},
    )

    t_job_SEQ_SF_CONTRACT = DataStageOperator(
        task_id="SEQ_SF_CONTRACT",
        project=PROJECT_NAME,
        job_name="SEQ_SF_CONTRACT",
        ssh_conn_id=SSH_CONN_ID,
        queue_name=DS_QUEUE,
    )

    t_end_SEQ_SF_CONTRACT = PythonOperator(
        task_id="log_end_SEQ_SF_CONTRACT",
        python_callable=log_end,
        op_kwargs={"job_name": "SEQ_SF_CONTRACT", "task_key": "SEQ_SF_CONTRACT", "upstream_task_id": "SEQ_SF_CONTRACT"},
        trigger_rule=TriggerRule.ALL_DONE,
    )

    t_start_SEQ_SF_CASE = PythonOperator(
        task_id="log_start_SEQ_SF_CASE",
        python_callable=log_start,
        op_kwargs={"job_name": "SEQ_SF_CASE", "task_key": "SEQ_SF_CASE"},
    )

    t_job_SEQ_SF_CASE = DataStageOperator(
        task_id="SEQ_SF_CASE",
        project=PROJECT_NAME,
        job_name="SEQ_SF_CASE",
        ssh_conn_id=SSH_CONN_ID,
        queue_name=DS_QUEUE,
    )

    t_end_SEQ_SF_CASE = PythonOperator(
        task_id="log_end_SEQ_SF_CASE",
        python_callable=log_end,
        op_kwargs={"job_name": "SEQ_SF_CASE", "task_key": "SEQ_SF_CASE", "upstream_task_id": "SEQ_SF_CASE"},
        trigger_rule=TriggerRule.ALL_DONE,
    )

    t_start_SEQ_SF_CASE_TASK = PythonOperator(
        task_id="log_start_SEQ_SF_CASE_TASK",
        python_callable=log_start,
        op_kwargs={"job_name": "SEQ_SF_CASE_TASK", "task_key": "SEQ_SF_CASE_TASK"},
    )

    t_job_SEQ_SF_CASE_TASK = DataStageOperator(
        task_id="SEQ_SF_CASE_TASK",
        project=PROJECT_NAME,
        job_name="SEQ_SF_CASE_TASK",
        ssh_conn_id=SSH_CONN_ID,
        queue_name=DS_QUEUE,
    )

    t_end_SEQ_SF_CASE_TASK = PythonOperator(
        task_id="log_end_SEQ_SF_CASE_TASK",
        python_callable=log_end,
        op_kwargs={"job_name": "SEQ_SF_CASE_TASK", "task_key": "SEQ_SF_CASE_TASK", "upstream_task_id": "SEQ_SF_CASE_TASK"},
        trigger_rule=TriggerRule.ALL_DONE,
    )

    t_start_SEQ_SF_ADM_ASSUNTOS = PythonOperator(
        task_id="log_start_SEQ_SF_ADM_ASSUNTOS",
        python_callable=log_start,
        op_kwargs={"job_name": "SEQ_SF_ADM_ASSUNTOS", "task_key": "SEQ_SF_ADM_ASSUNTOS"},
    )

    t_job_SEQ_SF_ADM_ASSUNTOS = DataStageOperator(
        task_id="SEQ_SF_ADM_ASSUNTOS",
        project=PROJECT_NAME,
        job_name="SEQ_SF_ADM_ASSUNTOS",
        ssh_conn_id=SSH_CONN_ID,
        queue_name=DS_QUEUE,
    )

    t_end_SEQ_SF_ADM_ASSUNTOS = PythonOperator(
        task_id="log_end_SEQ_SF_ADM_ASSUNTOS",
        python_callable=log_end,
        op_kwargs={"job_name": "SEQ_SF_ADM_ASSUNTOS", "task_key": "SEQ_SF_ADM_ASSUNTOS", "upstream_task_id": "SEQ_SF_ADM_ASSUNTOS"},
        trigger_rule=TriggerRule.ALL_DONE,
    )

    t_start_SEQ_SF_LIVECHATBUTTON = PythonOperator(
        task_id="log_start_SEQ_SF_LIVECHATBUTTON",
        python_callable=log_start,
        op_kwargs={"job_name": "SEQ_SF_LIVECHATBUTTON", "task_key": "SEQ_SF_LIVECHATBUTTON"},
    )

    t_job_SEQ_SF_LIVECHATBUTTON = DataStageOperator(
        task_id="SEQ_SF_LIVECHATBUTTON",
        project=PROJECT_NAME,
        job_name="SEQ_SF_LIVECHATBUTTON",
        ssh_conn_id=SSH_CONN_ID,
        queue_name=DS_QUEUE,
    )

    t_end_SEQ_SF_LIVECHATBUTTON = PythonOperator(
        task_id="log_end_SEQ_SF_LIVECHATBUTTON",
        python_callable=log_end,
        op_kwargs={"job_name": "SEQ_SF_LIVECHATBUTTON", "task_key": "SEQ_SF_LIVECHATBUTTON", "upstream_task_id": "SEQ_SF_LIVECHATBUTTON"},
        trigger_rule=TriggerRule.ALL_DONE,
    )

    t_start_SEQ_SF_LIVECHATTRANSCRIPT = PythonOperator(
        task_id="log_start_SEQ_SF_LIVECHATTRANSCRIPT",
        python_callable=log_start,
        op_kwargs={"job_name": "SEQ_SF_LIVECHATTRANSCRIPT", "task_key": "SEQ_SF_LIVECHATTRANSCRIPT"},
    )

    t_job_SEQ_SF_LIVECHATTRANSCRIPT = DataStageOperator(
        task_id="SEQ_SF_LIVECHATTRANSCRIPT",
        project=PROJECT_NAME,
        job_name="SEQ_SF_LIVECHATTRANSCRIPT",
        ssh_conn_id=SSH_CONN_ID,
        queue_name=DS_QUEUE,
    )

    t_end_SEQ_SF_LIVECHATTRANSCRIPT = PythonOperator(
        task_id="log_end_SEQ_SF_LIVECHATTRANSCRIPT",
        python_callable=log_end,
        op_kwargs={"job_name": "SEQ_SF_LIVECHATTRANSCRIPT", "task_key": "SEQ_SF_LIVECHATTRANSCRIPT", "upstream_task_id": "SEQ_SF_LIVECHATTRANSCRIPT"},
        trigger_rule=TriggerRule.ALL_DONE,
    )

    t_start_SEQ_SF_LIVECHATTRANSCRIPTEVENT = PythonOperator(
        task_id="log_start_SEQ_SF_LIVECHATTRANSCRIPTEVENT",
        python_callable=log_start,
        op_kwargs={"job_name": "SEQ_SF_LIVECHATTRANSCRIPTEVENT", "task_key": "SEQ_SF_LIVECHATTRANSCRIPTEVENT"},
    )

    t_job_SEQ_SF_LIVECHATTRANSCRIPTEVENT = DataStageOperator(
        task_id="SEQ_SF_LIVECHATTRANSCRIPTEVENT",
        project=PROJECT_NAME,
        job_name="SEQ_SF_LIVECHATTRANSCRIPTEVENT",
        ssh_conn_id=SSH_CONN_ID,
        queue_name=DS_QUEUE,
    )

    t_end_SEQ_SF_LIVECHATTRANSCRIPTEVENT = PythonOperator(
        task_id="log_end_SEQ_SF_LIVECHATTRANSCRIPTEVENT",
        python_callable=log_end,
        op_kwargs={"job_name": "SEQ_SF_LIVECHATTRANSCRIPTEVENT", "task_key": "SEQ_SF_LIVECHATTRANSCRIPTEVENT", "upstream_task_id": "SEQ_SF_LIVECHATTRANSCRIPTEVENT"},
        trigger_rule=TriggerRule.ALL_DONE,
    )

    t_start_SEQ_SF_LIVECHATVISITOR = PythonOperator(
        task_id="log_start_SEQ_SF_LIVECHATVISITOR",
        python_callable=log_start,
        op_kwargs={"job_name": "SEQ_SF_LIVECHATVISITOR", "task_key": "SEQ_SF_LIVECHATVISITOR"},
    )

    t_job_SEQ_SF_LIVECHATVISITOR = DataStageOperator(
        task_id="SEQ_SF_LIVECHATVISITOR",
        project=PROJECT_NAME,
        job_name="SEQ_SF_LIVECHATVISITOR",
        ssh_conn_id=SSH_CONN_ID,
        queue_name=DS_QUEUE,
    )

    t_end_SEQ_SF_LIVECHATVISITOR = PythonOperator(
        task_id="log_end_SEQ_SF_LIVECHATVISITOR",
        python_callable=log_end,
        op_kwargs={"job_name": "SEQ_SF_LIVECHATVISITOR", "task_key": "SEQ_SF_LIVECHATVISITOR", "upstream_task_id": "SEQ_SF_LIVECHATVISITOR"},
        trigger_rule=TriggerRule.ALL_DONE,
    )

    t_start_SEQ_SF_PROFILE = PythonOperator(
        task_id="log_start_SEQ_SF_PROFILE",
        python_callable=log_start,
        op_kwargs={"job_name": "SEQ_SF_PROFILE", "task_key": "SEQ_SF_PROFILE"},
    )

    t_job_SEQ_SF_PROFILE = DataStageOperator(
        task_id="SEQ_SF_PROFILE",
        project=PROJECT_NAME,
        job_name="SEQ_SF_PROFILE",
        ssh_conn_id=SSH_CONN_ID,
        queue_name=DS_QUEUE,
    )

    t_end_SEQ_SF_PROFILE = PythonOperator(
        task_id="log_end_SEQ_SF_PROFILE",
        python_callable=log_end,
        op_kwargs={"job_name": "SEQ_SF_PROFILE", "task_key": "SEQ_SF_PROFILE", "upstream_task_id": "SEQ_SF_PROFILE"},
        trigger_rule=TriggerRule.ALL_DONE,
    )

    t_start_SEQ_SF_PROTOCOLO = PythonOperator(
        task_id="log_start_SEQ_SF_PROTOCOLO",
        python_callable=log_start,
        op_kwargs={"job_name": "SEQ_SF_PROTOCOLO", "task_key": "SEQ_SF_PROTOCOLO"},
    )

    t_job_SEQ_SF_PROTOCOLO = DataStageOperator(
        task_id="SEQ_SF_PROTOCOLO",
        project=PROJECT_NAME,
        job_name="SEQ_SF_PROTOCOLO",
        ssh_conn_id=SSH_CONN_ID,
        queue_name=DS_QUEUE,
    )

    t_end_SEQ_SF_PROTOCOLO = PythonOperator(
        task_id="log_end_SEQ_SF_PROTOCOLO",
        python_callable=log_end,
        op_kwargs={"job_name": "SEQ_SF_PROTOCOLO", "task_key": "SEQ_SF_PROTOCOLO", "upstream_task_id": "SEQ_SF_PROTOCOLO"},
        trigger_rule=TriggerRule.ALL_DONE,
    )

    t_start_SEQ_SF_SURVEY_C = PythonOperator(
        task_id="log_start_SEQ_SF_SURVEY_C",
        python_callable=log_start,
        op_kwargs={"job_name": "SEQ_SF_SURVEY_C", "task_key": "SEQ_SF_SURVEY_C"},
    )

    t_job_SEQ_SF_SURVEY_C = DataStageOperator(
        task_id="SEQ_SF_SURVEY_C",
        project=PROJECT_NAME,
        job_name="SEQ_SF_SURVEY_C",
        ssh_conn_id=SSH_CONN_ID,
        queue_name=DS_QUEUE,
    )

    t_end_SEQ_SF_SURVEY_C = PythonOperator(
        task_id="log_end_SEQ_SF_SURVEY_C",
        python_callable=log_end,
        op_kwargs={"job_name": "SEQ_SF_SURVEY_C", "task_key": "SEQ_SF_SURVEY_C", "upstream_task_id": "SEQ_SF_SURVEY_C"},
        trigger_rule=TriggerRule.ALL_DONE,
    )

    t_start_SEQ_SF_SURVEY_QUESTION = PythonOperator(
        task_id="log_start_SEQ_SF_SURVEY_QUESTION",
        python_callable=log_start,
        op_kwargs={"job_name": "SEQ_SF_SURVEY_QUESTION", "task_key": "SEQ_SF_SURVEY_QUESTION"},
    )

    t_job_SEQ_SF_SURVEY_QUESTION = DataStageOperator(
        task_id="SEQ_SF_SURVEY_QUESTION",
        project=PROJECT_NAME,
        job_name="SEQ_SF_SURVEY_QUESTION",
        ssh_conn_id=SSH_CONN_ID,
        queue_name=DS_QUEUE,
    )

    t_end_SEQ_SF_SURVEY_QUESTION = PythonOperator(
        task_id="log_end_SEQ_SF_SURVEY_QUESTION",
        python_callable=log_end,
        op_kwargs={"job_name": "SEQ_SF_SURVEY_QUESTION", "task_key": "SEQ_SF_SURVEY_QUESTION", "upstream_task_id": "SEQ_SF_SURVEY_QUESTION"},
        trigger_rule=TriggerRule.ALL_DONE,
    )

    t_start_SEQ_SF_SURVEY_RESPONSE = PythonOperator(
        task_id="log_start_SEQ_SF_SURVEY_RESPONSE",
        python_callable=log_start,
        op_kwargs={"job_name": "SEQ_SF_SURVEY_RESPONSE", "task_key": "SEQ_SF_SURVEY_RESPONSE"},
    )

    t_job_SEQ_SF_SURVEY_RESPONSE = DataStageOperator(
        task_id="SEQ_SF_SURVEY_RESPONSE",
        project=PROJECT_NAME,
        job_name="SEQ_SF_SURVEY_RESPONSE",
        ssh_conn_id=SSH_CONN_ID,
        queue_name=DS_QUEUE,
    )

    t_end_SEQ_SF_SURVEY_RESPONSE = PythonOperator(
        task_id="log_end_SEQ_SF_SURVEY_RESPONSE",
        python_callable=log_end,
        op_kwargs={"job_name": "SEQ_SF_SURVEY_RESPONSE", "task_key": "SEQ_SF_SURVEY_RESPONSE", "upstream_task_id": "SEQ_SF_SURVEY_RESPONSE"},
        trigger_rule=TriggerRule.ALL_DONE,
    )

    t_start_SEQ_SF_SURVEY_TAKER_C = PythonOperator(
        task_id="log_start_SEQ_SF_SURVEY_TAKER_C",
        python_callable=log_start,
        op_kwargs={"job_name": "SEQ_SF_SURVEY_TAKER_C", "task_key": "SEQ_SF_SURVEY_TAKER_C"},
    )

    t_job_SEQ_SF_SURVEY_TAKER_C = DataStageOperator(
        task_id="SEQ_SF_SURVEY_TAKER_C",
        project=PROJECT_NAME,
        job_name="SEQ_SF_SURVEY_TAKER_C",
        ssh_conn_id=SSH_CONN_ID,
        queue_name=DS_QUEUE,
    )

    t_end_SEQ_SF_SURVEY_TAKER_C = PythonOperator(
        task_id="log_end_SEQ_SF_SURVEY_TAKER_C",
        python_callable=log_end,
        op_kwargs={"job_name": "SEQ_SF_SURVEY_TAKER_C", "task_key": "SEQ_SF_SURVEY_TAKER_C", "upstream_task_id": "SEQ_SF_SURVEY_TAKER_C"},
        trigger_rule=TriggerRule.ALL_DONE,
    )

    t_start_SEQ_SF_USER = PythonOperator(
        task_id="log_start_SEQ_SF_USER",
        python_callable=log_start,
        op_kwargs={"job_name": "SEQ_SF_USER", "task_key": "SEQ_SF_USER"},
    )

    t_job_SEQ_SF_USER = DataStageOperator(
        task_id="SEQ_SF_USER",
        project=PROJECT_NAME,
        job_name="SEQ_SF_USER",
        ssh_conn_id=SSH_CONN_ID,
        queue_name=DS_QUEUE,
    )

    t_end_SEQ_SF_USER = PythonOperator(
        task_id="log_end_SEQ_SF_USER",
        python_callable=log_end,
        op_kwargs={"job_name": "SEQ_SF_USER", "task_key": "SEQ_SF_USER", "upstream_task_id": "SEQ_SF_USER"},
        trigger_rule=TriggerRule.ALL_DONE,
    )

    t_start_SEQ_SF_USERROLE = PythonOperator(
        task_id="log_start_SEQ_SF_USERROLE",
        python_callable=log_start,
        op_kwargs={"job_name": "SEQ_SF_USERROLE", "task_key": "SEQ_SF_USERROLE"},
    )

    t_job_SEQ_SF_USERROLE = DataStageOperator(
        task_id="SEQ_SF_USERROLE",
        project=PROJECT_NAME,
        job_name="SEQ_SF_USERROLE",
        ssh_conn_id=SSH_CONN_ID,
        queue_name=DS_QUEUE,
    )

    t_end_SEQ_SF_USERROLE = PythonOperator(
        task_id="log_end_SEQ_SF_USERROLE",
        python_callable=log_end,
        op_kwargs={"job_name": "SEQ_SF_USERROLE", "task_key": "SEQ_SF_USERROLE", "upstream_task_id": "SEQ_SF_USERROLE"},
        trigger_rule=TriggerRule.ALL_DONE,
    )

    t_check_agenda >> t_start_SEQ_SF_CONTRACT >> t_teams_start >> t_job_SEQ_SF_CONTRACT >> t_end_SEQ_SF_CONTRACT

    t_end_SEQ_SF_CONTRACT >> t_start_SEQ_SF_CASE >> t_job_SEQ_SF_CASE >> t_end_SEQ_SF_CASE

    t_end_SEQ_SF_CASE >> t_start_SEQ_SF_CASE_TASK >> t_job_SEQ_SF_CASE_TASK >> t_end_SEQ_SF_CASE_TASK

    t_end_SEQ_SF_CASE_TASK >> t_start_SEQ_SF_ADM_ASSUNTOS >> t_job_SEQ_SF_ADM_ASSUNTOS >> t_end_SEQ_SF_ADM_ASSUNTOS

    t_end_SEQ_SF_ADM_ASSUNTOS >> t_start_SEQ_SF_LIVECHATBUTTON >> t_job_SEQ_SF_LIVECHATBUTTON >> t_end_SEQ_SF_LIVECHATBUTTON

    t_end_SEQ_SF_LIVECHATBUTTON >> t_start_SEQ_SF_LIVECHATTRANSCRIPT >> t_job_SEQ_SF_LIVECHATTRANSCRIPT >> t_end_SEQ_SF_LIVECHATTRANSCRIPT

    t_end_SEQ_SF_LIVECHATTRANSCRIPT >> t_start_SEQ_SF_LIVECHATTRANSCRIPTEVENT >> t_job_SEQ_SF_LIVECHATTRANSCRIPTEVENT >> t_end_SEQ_SF_LIVECHATTRANSCRIPTEVENT

    t_end_SEQ_SF_LIVECHATTRANSCRIPTEVENT >> t_start_SEQ_SF_LIVECHATVISITOR >> t_job_SEQ_SF_LIVECHATVISITOR >> t_end_SEQ_SF_LIVECHATVISITOR

    t_end_SEQ_SF_LIVECHATVISITOR >> t_start_SEQ_SF_PROFILE >> t_job_SEQ_SF_PROFILE >> t_end_SEQ_SF_PROFILE

    t_end_SEQ_SF_PROFILE >> t_start_SEQ_SF_PROTOCOLO >> t_job_SEQ_SF_PROTOCOLO >> t_end_SEQ_SF_PROTOCOLO

    t_end_SEQ_SF_PROTOCOLO >> t_start_SEQ_SF_SURVEY_C >> t_job_SEQ_SF_SURVEY_C >> t_end_SEQ_SF_SURVEY_C

    t_end_SEQ_SF_SURVEY_C >> t_start_SEQ_SF_SURVEY_QUESTION >> t_job_SEQ_SF_SURVEY_QUESTION >> t_end_SEQ_SF_SURVEY_QUESTION

    t_end_SEQ_SF_SURVEY_QUESTION >> t_start_SEQ_SF_SURVEY_RESPONSE >> t_job_SEQ_SF_SURVEY_RESPONSE >> t_end_SEQ_SF_SURVEY_RESPONSE

    t_end_SEQ_SF_SURVEY_RESPONSE >> t_start_SEQ_SF_SURVEY_TAKER_C >> t_job_SEQ_SF_SURVEY_TAKER_C >> t_end_SEQ_SF_SURVEY_TAKER_C

    t_end_SEQ_SF_SURVEY_TAKER_C >> t_start_SEQ_SF_USER >> t_job_SEQ_SF_USER >> t_end_SEQ_SF_USER

    t_end_SEQ_SF_USER >> t_start_SEQ_SF_USERROLE >> t_job_SEQ_SF_USERROLE >> t_end_SEQ_SF_USERROLE

    end_tasks = [t_end_SEQ_SF_CONTRACT, t_end_SEQ_SF_CASE, t_end_SEQ_SF_CASE_TASK, t_end_SEQ_SF_ADM_ASSUNTOS, t_end_SEQ_SF_LIVECHATBUTTON, t_end_SEQ_SF_LIVECHATTRANSCRIPT, t_end_SEQ_SF_LIVECHATTRANSCRIPTEVENT, t_end_SEQ_SF_LIVECHATVISITOR, t_end_SEQ_SF_PROFILE, t_end_SEQ_SF_PROTOCOLO, t_end_SEQ_SF_SURVEY_C, t_end_SEQ_SF_SURVEY_QUESTION, t_end_SEQ_SF_SURVEY_RESPONSE, t_end_SEQ_SF_SURVEY_TAKER_C, t_end_SEQ_SF_USER, t_end_SEQ_SF_USERROLE]

    [t_end_SEQ_SF_CONTRACT, t_end_SEQ_SF_CASE, t_end_SEQ_SF_CASE_TASK, t_end_SEQ_SF_ADM_ASSUNTOS, t_end_SEQ_SF_LIVECHATBUTTON, t_end_SEQ_SF_LIVECHATTRANSCRIPT, t_end_SEQ_SF_LIVECHATTRANSCRIPTEVENT, t_end_SEQ_SF_LIVECHATVISITOR, t_end_SEQ_SF_PROFILE, t_end_SEQ_SF_PROTOCOLO, t_end_SEQ_SF_SURVEY_C, t_end_SEQ_SF_SURVEY_QUESTION, t_end_SEQ_SF_SURVEY_RESPONSE, t_end_SEQ_SF_SURVEY_TAKER_C, t_end_SEQ_SF_USER, t_end_SEQ_SF_USERROLE] >> t_publish_dataset

    [t_end_SEQ_SF_CONTRACT, t_end_SEQ_SF_CASE, t_end_SEQ_SF_CASE_TASK, t_end_SEQ_SF_ADM_ASSUNTOS, t_end_SEQ_SF_LIVECHATBUTTON, t_end_SEQ_SF_LIVECHATTRANSCRIPT, t_end_SEQ_SF_LIVECHATTRANSCRIPTEVENT, t_end_SEQ_SF_LIVECHATVISITOR, t_end_SEQ_SF_PROFILE, t_end_SEQ_SF_PROTOCOLO, t_end_SEQ_SF_SURVEY_C, t_end_SEQ_SF_SURVEY_QUESTION, t_end_SEQ_SF_SURVEY_RESPONSE, t_end_SEQ_SF_SURVEY_TAKER_C, t_end_SEQ_SF_USER, t_end_SEQ_SF_USERROLE] >> t_teams_end

    [t_end_SEQ_SF_CONTRACT, t_end_SEQ_SF_CASE, t_end_SEQ_SF_CASE_TASK, t_end_SEQ_SF_ADM_ASSUNTOS, t_end_SEQ_SF_LIVECHATBUTTON, t_end_SEQ_SF_LIVECHATTRANSCRIPT, t_end_SEQ_SF_LIVECHATTRANSCRIPTEVENT, t_end_SEQ_SF_LIVECHATVISITOR, t_end_SEQ_SF_PROFILE, t_end_SEQ_SF_PROTOCOLO, t_end_SEQ_SF_SURVEY_C, t_end_SEQ_SF_SURVEY_QUESTION, t_end_SEQ_SF_SURVEY_RESPONSE, t_end_SEQ_SF_SURVEY_TAKER_C, t_end_SEQ_SF_USER, t_end_SEQ_SF_USERROLE] >> t_teams_error
