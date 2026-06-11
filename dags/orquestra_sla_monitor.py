"""
orquestra_sla_monitor.py
========================
DAG sentinela — roda a cada 5 minutos.

Objetivo:
- Verificar execuções RUNNING contra o SLA configurado no pipeline (sla_minutos).
- Alertar no Teams quando o SLA estiver EM RISCO (>= 80% do tempo) ou ESTOURADO.
- Dedup via dbo.etl_sla_alert: cada (execution_id, pipeline, tipo) alerta uma única vez.
"""

from __future__ import annotations

import pendulum
import requests
from airflow import DAG
from airflow.models import Variable
from airflow.operators.python import PythonOperator
from airflow.providers.microsoft.mssql.hooks.mssql import MsSqlHook

DAG_ID            = "orquestra_sla_monitor"
MSSQL_CONN_ID     = "SQL14_DMDB41"
LOCAL_TZ          = "America/Sao_Paulo"
TEAMS_WEBHOOK_VAR = "TEAMS_WEBHOOK_URL_CVP"
RISK_THRESHOLD    = 0.8  # 80% do SLA → alerta de risco

default_args = {"owner": "airflow", "depends_on_past": False, "retries": 0}


def _teams_post_card(title, facts, status="WARNING", subtitle=None):
    try:
        webhook_url = Variable.get(TEAMS_WEBHOOK_VAR)
    except Exception:
        print(f"[TEAMS] Variable '{TEAMS_WEBHOOK_VAR}' nao encontrada.")
        return
    icon  = {"WARNING": "⏰", "FAILED": "🚨"}.get(status, "⏰")
    color = {"WARNING": "Warning", "FAILED": "Attention"}.get(status, "Warning")
    body = [
        {"type": "TextBlock", "text": f"{icon} {title}", "size": "Large",
         "weight": "Bolder", "wrap": True, "color": color},
    ]
    if subtitle:
        body.append({"type": "TextBlock", "text": subtitle, "wrap": True,
                     "spacing": "None", "isSubtle": True})
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


def _fmt_min(minutes):
    m = int(minutes or 0)
    h, rem = divmod(m, 60)
    return f"{h}h {rem}min" if h else f"{rem}min"


def monitorar_sla(**context):
    hook = MsSqlHook(mssql_conn_id=MSSQL_CONN_ID)

    rows = hook.get_records("""
        SELECT e.execution_id, e.pipeline, e.project,
               p.sla_minutos, p.criticidade, p.runbook_md,
               DATEDIFF(MINUTE, MIN(e.start_time), GETDATE()) AS elapsed_min
        FROM dbo.etl_job_execution e
        JOIN dbo.etl_pipeline p ON p.pipeline_name = e.pipeline
        WHERE e.status = 'RUNNING'
          AND p.sla_minutos IS NOT NULL AND p.sla_minutos > 0
        GROUP BY e.execution_id, e.pipeline, e.project,
                 p.sla_minutos, p.criticidade, p.runbook_md
    """)
    if not rows:
        print("[SLA] Nenhuma execução RUNNING com SLA configurado.")
        return {"checked": 0, "alerts": 0}

    # Dedup: insere apenas se ainda não alertou esse tipo para essa execução
    insert_sql = """
        INSERT INTO dbo.etl_sla_alert (execution_id, pipeline, alert_type, sla_minutos, elapsed_min)
        SELECT %s, %s, %s, %s, %s
        WHERE NOT EXISTS (
            SELECT 1 FROM dbo.etl_sla_alert
            WHERE execution_id = %s AND pipeline = %s AND alert_type = %s
        )
    """

    alerts = 0
    for exec_id, pipeline, project, sla_min, criticidade, runbook, elapsed in rows:
        sla_min  = int(sla_min)
        elapsed  = int(elapsed or 0)
        breached = elapsed >= sla_min
        at_risk  = (not breached) and elapsed >= sla_min * RISK_THRESHOLD

        if not breached and not at_risk:
            continue

        alert_type = "BREACH" if breached else "RISK"
        before = hook.get_first(
            "SELECT COUNT(*) FROM dbo.etl_sla_alert "
            "WHERE execution_id=%s AND pipeline=%s AND alert_type=%s",
            parameters=(exec_id, pipeline, alert_type),
        )
        if before and before[0] > 0:
            continue  # já alertado

        hook.run(insert_sql, parameters=(
            exec_id, pipeline, alert_type, sla_min, elapsed,
            exec_id, pipeline, alert_type,
        ))
        alerts += 1

        facts = [
            _fact("Pipeline",     pipeline),
            _fact("Projeto",      project),
            _fact("Criticidade",  criticidade or "—"),
            _fact("Execution ID", exec_id),
            _fact("SLA",          _fmt_min(sla_min)),
            _fact("Tempo decorrido", _fmt_min(elapsed)),
        ]
        if breached:
            title    = "SLA estourado"
            subtitle = (f"O pipeline {pipeline} ultrapassou o SLA de {_fmt_min(sla_min)} "
                        f"e continua em execução ({_fmt_min(elapsed)} decorridos).")
            status   = "FAILED"
        else:
            title    = "SLA em risco"
            subtitle = (f"O pipeline {pipeline} já consumiu {elapsed * 100 // sla_min}% do SLA "
                        f"de {_fmt_min(sla_min)} e ainda está em execução.")
            status   = "WARNING"
        if runbook:
            facts.append(_fact("Runbook", (runbook[:300] + "…") if len(runbook) > 300 else runbook))

        _teams_post_card(title=title, subtitle=subtitle, facts=facts, status=status)
        print(f"[SLA] {alert_type}: {pipeline} exec={exec_id} elapsed={elapsed}min sla={sla_min}min")

    print(f"[SLA] Execuções verificadas: {len(rows)} | Alertas enviados: {alerts}")
    return {"checked": len(rows), "alerts": alerts}


with DAG(
    dag_id=DAG_ID,
    default_args=default_args,
    description="Sentinela de SLA — alerta Teams quando execução estoura ou ameaça o SLA",
    start_date=pendulum.datetime(2026, 1, 1, tz=LOCAL_TZ),
    schedule="*/5 * * * *",
    catchup=False,
    max_active_runs=1,
    tags=["orquestra", "monitor", "sla"],
    access_control={"Op": {"can_read", "can_edit"}},
) as dag:
    PythonOperator(task_id="monitorar_sla", python_callable=monitorar_sla, do_xcom_push=True)
