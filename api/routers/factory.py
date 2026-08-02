"""api/routers/factory.py — GET /factory/runs, GET /factory/runs/{dag_run_id}/log, GET /factory/preview."""
from __future__ import annotations

import json as _json
import logging
import re as _re
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Query

from db import get_db_conn
from deps import get_current_user
from services.dag_reconcile import recheck_geradas

log = logging.getLogger("orquestra-api")

router = APIRouter()

FACTORY_DAG_ID  = "etl_dag_factory"
FACTORY_TASK_ID = "gerar_dags"


def _fmt_dt(v):
    if v is None:
        return None
    if hasattr(v, "strftime"):
        return v.strftime("%Y-%m-%d %H:%M:%S")
    return str(v)


@router.get("/factory/runs", tags=["factory"])
def factory_runs(limit: int = Query(20, le=100)):
    """Últimas execuções da etl_dag_factory lidas de dbo.etl_factory_log."""
    # Auto-cura: revalida runs em 'GERADA' (vira SUCCESS/TIMEOUT) a cada acesso,
    # evitando que fiquem 'GERADA' para sempre. Best-effort — nunca quebra a tela.
    try:
        recheck_geradas()
    except Exception as _e:
        log.debug("[FACTORY] recheck_geradas ignorado: %s", _e)
    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute(
            "SELECT TOP (?) dag_run_id, iniciado_em, finalizado_em, estado, "
            "       escopo, pipeline_name, geradas, erros "
            "FROM dbo.etl_factory_log "
            "ORDER BY iniciado_em DESC",
            (limit,),
        )
        cols = ["dag_run_id", "iniciado_em", "finalizado_em", "estado",
                "escopo", "pipeline_name", "geradas", "erros"]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        cur.close(); conn.close()
        for r in rows:
            r["iniciado_em"]   = _fmt_dt(r["iniciado_em"])
            r["finalizado_em"] = _fmt_dt(r["finalizado_em"])
        return {"data": rows}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao consultar factory log: {e}")


@router.get("/factory/runs/{dag_run_id}/log", tags=["factory"])
def factory_run_log(dag_run_id: str):
    """Etapas estruturadas de uma execução da factory (de dbo.etl_factory_log)."""
    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute(
            "SELECT estado, escopo, geradas, erros, detalhes_json, iniciado_em, finalizado_em "
            "FROM dbo.etl_factory_log WHERE dag_run_id=?",
            (dag_run_id,),
        )
        row = cur.fetchone()
        cur.close(); conn.close()
        if not row:
            raise HTTPException(status_code=404, detail="Execução não encontrada no banco")
        estado, escopo, geradas_n, erros_n, detalhes_json, ini, fim = row
        detalhes = _json.loads(detalhes_json) if detalhes_json else {}
        return {
            "dag_run_id":    dag_run_id,
            "estado":        estado,
            "escopo":        escopo,
            "geradas":       geradas_n,
            "erros":         erros_n,
            "iniciado_em":   _fmt_dt(ini),
            "finalizado_em": _fmt_dt(fim),
            "steps":         detalhes.get("steps", []),
            "erros_lista":   detalhes.get("erros", []),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao consultar log: {e}")


# ── Preview helpers ───────────────────────────────────────────────────────────

_TYPE_ALIAS = {
    "bash": "shell", "shell script": "shell",
    "proc": "storedproc", "stored proc": "storedproc",
    "stored_proc": "storedproc", "procedure": "storedproc",
}

def _preview_cron(pipeline: dict) -> str:
    sched = str(pipeline.get("scheduled_time") or "06:00:00")
    stype = (pipeline.get("schedule_type") or "daily").lower().strip()
    horarios_raw = (pipeline.get("horarios_especificos") or "").strip()
    parts = sched.split(":")
    h = int(parts[0]) if parts[0].isdigit() else 6
    m = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
    dias = (pipeline.get("dias_semana") or "").strip()

    if stype == "daily":
        return f"{m} {h} * * *"
    if stype == "weekly":
        dow = int(pipeline.get("schedule_dow") or 1)
        return f"{m} {h} * * {dow}"
    if stype == "monthly":
        dom = int(pipeline.get("schedule_dom") or 1)
        return f"{m} {h} {dom} * *"
    if stype == "biweekly":
        dom = int(pipeline.get("schedule_dom") or 1)
        d2 = min(dom + 15, 28)
        return f"{m} {h} {dom},{d2} * *"
    if stype in ("hourly_n", "custom") or horarios_raw:
        times = []
        for t in horarios_raw.split(","):
            t = t.strip()
            if not t:
                continue
            tp = t.split(":")
            try:
                times.append((int(tp[0]), int(tp[1]) if len(tp) > 1 else 0))
            except ValueError:
                pass
        if times:
            hours = sorted(set(h2 for h2, _ in times))
            mins  = sorted(set(m2 for _, m2 in times))
            dow_expr = dias if dias else "*"
            return f"{','.join(map(str, mins))} {','.join(map(str, hours))} * * {dow_expr}"
        n = int(pipeline.get("schedule_hour") or 1)
        return f"0 */{max(1, n)} * * *"
    if stype == "on_demand":
        return "(sem agendamento)"
    return f"{m} {h} * * *"


@router.get("/factory/preview", tags=["factory"])
def factory_preview(
    pipeline_name: str = Query(..., description="Nome do pipeline para simular a geração de DAG"),
    _auth: dict = Depends(get_current_user),
):
    """Simula a geração de DAG sem escrever nada em disco.

    Retorna a estrutura que seria gerada: cron, jobs ordenados, operadores, parâmetros de execução.
    Use para validar o cadastro antes de clicar em 'Gerar DAG'.
    """
    try:
        conn = get_db_conn(); cur = conn.cursor()

        # trigger_por_dependencia saiu do SELECT na F5: não decide nada desde a
        # F3 (ter dependência JÁ significa disparo por evento) — mantê-lo aqui
        # era prometer um comportamento que o gerador ignora.
        cur.execute(
            """SELECT pipeline_name, project_name, domain, tags, scheduled_time, schedule_type,
                      schedule_hour, schedule_minute, schedule_dow, schedule_dom,
                      horarios_especificos, dias_semana, somente_dias_uteis,
                      envia_msg_inicio, envia_msg_fim, envia_msg_erro,
                      depends_on, calendario_nome,
                      retries_count, retry_delay_seconds, max_active_runs, pool_name,
                      criticidade, sla_minutos, ambiente, runbook_md, ssh_conn_id, dag_criada
               FROM dbo.etl_pipeline WHERE pipeline_name = ?""",
            (pipeline_name,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"Pipeline '{pipeline_name}' não encontrado")

        cols = [
            "pipeline_name", "project_name", "domain", "tags", "scheduled_time", "schedule_type",
            "schedule_hour", "schedule_minute", "schedule_dow", "schedule_dom",
            "horarios_especificos", "dias_semana", "somente_dias_uteis",
            "envia_msg_inicio", "envia_msg_fim", "envia_msg_erro",
            "depends_on", "calendario_nome",
            "retries_count", "retry_delay_seconds", "max_active_runs", "pool_name",
            "criticidade", "sla_minutos", "ambiente", "runbook_md", "ssh_conn_id", "dag_criada",
        ]
        pipeline = dict(zip(cols, row))

        # F6: a pré-visualização tem de mostrar a MESMA dependência que a DAG
        # vai receber, e a fonte da verdade é a tabela (067). Sem ela, mantém o
        # CSV que veio da consulta acima — e registra que a GERAÇÃO será
        # recusada (F3 Decisão 6): o preview não pode prometer o que o factory
        # vai negar.
        tabela_067_ok = True
        try:
            cur.execute(
                "SELECT depende_de FROM dbo.etl_pipeline_dependencia "
                "WHERE pipeline_name = ? AND tipo = 'PIPELINE' ORDER BY depende_de",
                (pipeline_name,))
            pipeline["depends_on"] = ",".join(str(r[0]) for r in cur.fetchall()) or None
        except Exception as e:
            tabela_067_ok = False
            log.warning("[FACTORY] preview sem a tabela de dependências (%s) — usando o CSV.", e)

        cur.execute(
            """SELECT job_name, execution_order, job_type, job_command, ssh_conn_id, verbose_log
               FROM dbo.etl_pipeline_job WHERE pipeline_name = ?
               ORDER BY execution_order, job_name""",
            (pipeline_name,),
        )
        job_cols = ["job_name", "execution_order", "job_type", "job_command", "ssh_conn_id", "verbose_log"]
        jobs = [dict(zip(job_cols, r)) for r in cur.fetchall()]
        cur.close(); conn.close()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro DB: {e}")

    # Build preview structure. Pipeline DEPENDENTE não tem cron: a DAG gerada
    # sai com schedule=None e o disparo vem da conclusão dos predecessores
    # (F3). O preview prometia o cron mesmo assim — a mesma mentira do
    # ViewModal, corrigida na F5 (§6 do desenho): string no lugar do cron,
    # espelhando o padrão do próprio 'on_demand'.
    dependencias = [d.strip() for d in str(pipeline.get("depends_on") or "").split(",")
                    if d.strip()]
    if dependencias:
        cron = f"(sem agendamento — disparo pelos predecessores: {', '.join(dependencias)})"
    else:
        cron = _preview_cron(pipeline)

    # Group jobs by execution_order
    by_order: dict = defaultdict(list)
    for j in jobs:
        by_order[j["execution_order"]].append(j)
    ordered_groups = [
        {
            "execution_order": ord_key,
            "parallel": len(grp) > 1,
            "jobs": [
                {
                    "job_name": j["job_name"],
                    "operator": _TYPE_ALIAS.get((j["job_type"] or "").lower(), (j["job_type"] or "").lower()),
                    "command": j["job_command"],
                    "ssh_conn_id": j.get("ssh_conn_id") or "ssh_lnxprd021",
                    "verbose_log": bool(j.get("verbose_log")),
                }
                for j in grp
            ],
        }
        for ord_key, grp in sorted(by_order.items())
    ]

    # Notifications
    is_prd = (pipeline.get("ambiente") or "PROD").upper() == "PROD"
    notifs = {
        "inicio": bool(pipeline.get("envia_msg_inicio")) and is_prd,
        "fim":    bool(pipeline.get("envia_msg_fim")) and is_prd,
        "erro":   bool(pipeline.get("envia_msg_erro")) and is_prd,
    }

    _DS_QUEUE_MAP = {
        "ALTA": "HighPriorityJobs", "CRITICA": "HighPriorityJobs",
        "MEDIA": "MediumPriorityJobs", "BAIXA": "LowPriorityJobs",
    }
    ds_queue = _DS_QUEUE_MAP.get((pipeline.get("criticidade") or "").upper().strip())

    warnings = []
    if not jobs:
        warnings.append("Pipeline sem jobs cadastrados — DAG gerada ficará vazia.")
    if pipeline.get("schedule_type") == "on_demand":
        warnings.append("Agendamento 'sob demanda': DAG não terá schedule.")
    if dependencias:
        warnings.append(
            "Pipeline com dependência: a DAG é gerada com schedule=None — o horário "
            "deixa de valer e o disparo vem da conclusão dos predecessores "
            f"({', '.join(dependencias)}); as restrições de DIA continuam valendo.")
        if not tabela_067_ok:
            # Espelha a recusa ruidosa do factory (F3 Decisão 6): dependência
            # que só existe no CSV, sem a tabela, não gera DAG.
            warnings.append(
                "dependência cadastrada mas migration 067 ausente — a geração "
                "desta DAG será recusada")
    if not pipeline.get("dag_criada"):
        warnings.append("DAG ainda não foi gerada — esta seria a primeira geração.")

    return {
        "pipeline_name":   pipeline_name,
        "dag_id":          pipeline_name,
        "cron":            cron,
        "ambiente":        pipeline.get("ambiente") or "PROD",
        "criticidade":     pipeline.get("criticidade") or "Media",
        "ds_queue":        ds_queue,
        "sla_minutos":     pipeline.get("sla_minutos"),
        "retries":         int(pipeline.get("retries_count") or 1),
        "retry_delay_s":   int(pipeline.get("retry_delay_seconds") or 300),
        "max_active_runs": int(pipeline.get("max_active_runs") or 1),
        "pool_name":       pipeline.get("pool_name"),
        "depends_on":      pipeline.get("depends_on"),
        "calendario":      pipeline.get("calendario_nome"),
        "somente_dias_uteis": bool(pipeline.get("somente_dias_uteis")),
        "notificacoes":    notifs,
        "total_jobs":      len(jobs),
        "job_groups":      ordered_groups,
        "warnings":        warnings,
    }
