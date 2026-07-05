"""
orquestra_daily_report.py
=========================
DAG diária — 07:00 (America/Sao_Paulo).

Objetivo:
- Postar no Teams o resumo da janela das últimas 24h:
  total de execuções, sucessos, falhas, warnings, SLAs estourados
  e os 5 pipelines mais lentos.
"""

from __future__ import annotations

import pendulum
import requests
from airflow import DAG
from airflow.models import Variable
from airflow.operators.python import PythonOperator
from airflow.providers.microsoft.mssql.hooks.mssql import MsSqlHook

DAG_ID            = "orquestra_daily_report"
MSSQL_CONN_ID     = "SQL14_DMDB41"
LOCAL_TZ          = "America/Sao_Paulo"
TEAMS_WEBHOOK_VAR = "TEAMS_WEBHOOK_URL_CVP"

default_args = {"owner": "airflow", "depends_on_past": False, "retries": 1}


def _fmt_duration(seconds):
    s = int(seconds or 0)
    h, rem = divmod(s, 3600)
    m, _ = divmod(rem, 60)
    if h:
        return f"{h}h {m}min"
    return f"{m}min" if m else f"{s}s"


def _fact(title, value):
    return {"title": title, "value": str(value) if value is not None else "—"}


def gerar_relatorio(**context):
    hook = MsSqlHook(mssql_conn_id=MSSQL_CONN_ID)

    # KPIs agregados por execução (últimas 24h)
    row = hook.get_first("""
        WITH execs AS (
            SELECT e.execution_id, e.pipeline,
                DATEDIFF(SECOND, MIN(e.start_time),
                         MAX(COALESCE(e.end_time, GETDATE()))) AS dur,
                CASE
                    WHEN SUM(CASE WHEN e.status='FAILED'  THEN 1 ELSE 0 END) > 0 THEN 'FAILED'
                    WHEN SUM(CASE WHEN e.status='WARNING' THEN 1 ELSE 0 END) > 0 THEN 'WARNING'
                    WHEN SUM(CASE WHEN e.status='RUNNING' THEN 1 ELSE 0 END) > 0 THEN 'RUNNING'
                    WHEN SUM(CASE WHEN e.status='SUCCESS' THEN 1 ELSE 0 END) > 0 THEN 'SUCCESS'
                    WHEN SUM(CASE WHEN e.status='SKIPPED' THEN 1 ELSE 0 END) > 0 THEN 'SKIPPED'
                    ELSE 'SUCCESS'
                END AS status_geral
            FROM dbo.etl_job_execution e
            JOIN dbo.etl_pipeline p ON p.pipeline_name = e.pipeline
            WHERE e.start_time >= DATEADD(HOUR, -24, GETDATE())
              AND COALESCE(p.ambiente, 'PROD') = 'PROD'
            GROUP BY e.execution_id, e.pipeline
        )
        SELECT COUNT(*),
            SUM(CASE WHEN status_geral='SUCCESS' THEN 1 ELSE 0 END),
            SUM(CASE WHEN status_geral='FAILED'  THEN 1 ELSE 0 END),
            SUM(CASE WHEN status_geral='WARNING' THEN 1 ELSE 0 END),
            SUM(CASE WHEN status_geral='RUNNING' THEN 1 ELSE 0 END),
            SUM(CASE WHEN status_geral='SKIPPED' THEN 1 ELSE 0 END)
        FROM execs
    """)
    total, ok, falhas, warns, running, skipped = [
        int(v or 0) for v in (row or (0, 0, 0, 0, 0, 0))]

    # SLAs estourados nas últimas 24h
    sla_row = hook.get_first(
        "SELECT COUNT(*) FROM dbo.etl_sla_alert "
        "WHERE alert_type='BREACH' AND alerted_at >= DATEADD(HOUR, -24, GETDATE())"
    )
    sla_breaches = int(sla_row[0] or 0) if sla_row else 0

    # Pipelines com falha (para listar nominalmente)
    failed_rows = hook.get_records("""
        SELECT DISTINCT e.pipeline
        FROM dbo.etl_job_execution e
        JOIN dbo.etl_pipeline p ON p.pipeline_name = e.pipeline
        WHERE e.status = 'FAILED'
          AND e.start_time >= DATEADD(HOUR, -24, GETDATE())
          AND COALESCE(p.ambiente, 'PROD') = 'PROD'
        ORDER BY e.pipeline
    """) or []

    # Top 5 mais lentos
    slow_rows = hook.get_records("""
        SELECT TOP 5 pipeline, MAX(dur) AS max_dur
        FROM (
            -- Relógio de parede: a SOMA inflava pipelines com jobs paralelos.
            SELECT e.pipeline, e.execution_id,
                   DATEDIFF(SECOND, MIN(e.start_time),
                            MAX(COALESCE(e.end_time, GETDATE()))) AS dur
            FROM dbo.etl_job_execution e
            WHERE e.start_time >= DATEADD(HOUR, -24, GETDATE())
            GROUP BY e.pipeline, e.execution_id
        ) t
        GROUP BY pipeline
        ORDER BY MAX(dur) DESC
    """) or []

    # Execuções 100% puladas (decisão) não entram na taxa — não são sucesso nem
    # falha; contam num fato próprio quando existirem.
    base_taxa = total - skipped
    taxa = round(ok * 100.0 / base_taxa, 1) if base_taxa else 0.0
    if falhas == 0 and sla_breaches == 0:
        icon, color, headline = "🟢", "Good", "Janela noturna sem falhas"
    elif falhas > 0:
        icon, color, headline = "🔴", "Attention", f"{falhas} execução(ões) com falha"
    else:
        icon, color, headline = "🟡", "Warning", f"{sla_breaches} SLA(s) estourado(s)"

    facts = [
        _fact("Período",          "Últimas 24 horas"),
        _fact("Execuções",        total),
        _fact("Sucesso",          f"{ok} ({taxa}%)"),
        _fact("Falhas",           falhas),
        _fact("Warnings",         warns),
        _fact("Em execução",      running),
        _fact("SLAs estourados",  sla_breaches),
    ]
    if skipped:
        facts.append(_fact("Puladas (decisão)", skipped))
    if failed_rows:
        facts.append(_fact("Pipelines com falha", ", ".join(r[0] for r in failed_rows[:10])))
    for i, (pname, dur) in enumerate(slow_rows, 1):
        facts.append(_fact(f"Top {i} mais lento", f"{pname} — {_fmt_duration(dur)}"))

    try:
        webhook_url = Variable.get(TEAMS_WEBHOOK_VAR)
    except Exception:
        print(f"[TEAMS] Variable '{TEAMS_WEBHOOK_VAR}' nao encontrada.")
        return

    payload = {
        "type": "message",
        "attachments": [{
            "contentType": "application/vnd.microsoft.card.adaptive",
            "content": {
                "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                "type": "AdaptiveCard", "version": "1.4",
                "body": [
                    {"type": "TextBlock", "text": f"{icon} Relatório diário ORQUESTRA",
                     "size": "Large", "weight": "Bolder", "wrap": True, "color": color},
                    {"type": "TextBlock", "text": headline, "wrap": True,
                     "spacing": "None", "isSubtle": True},
                    {"type": "FactSet", "spacing": "Medium", "facts": facts},
                ],
            },
        }],
    }
    resp = requests.post(webhook_url, json=payload, timeout=15)
    print(f"[TEAMS] status={resp.status_code} | total={total} falhas={falhas} sla={sla_breaches}")


with DAG(
    dag_id=DAG_ID,
    default_args=default_args,
    description="Relatório diário 07h — resumo da janela noturna no Teams",
    start_date=pendulum.datetime(2026, 1, 1, tz=LOCAL_TZ),
    schedule="0 7 * * *",
    catchup=False,
    max_active_runs=1,
    tags=["orquestra", "report", "teams"],
    access_control={"Op": {"can_read", "can_edit"}},
) as dag:
    PythonOperator(task_id="gerar_relatorio", python_callable=gerar_relatorio)
