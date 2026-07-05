"""api/routers/dashboard.py — GET /dashboard, GET /dashboard/gantt."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException

from db import get_db_conn

log = logging.getLogger("orquestra-api")

router = APIRouter()

LOCAL_TZ = timezone(timedelta(hours=-3))  # America/Sao_Paulo


def _fmt_dt(v):
    if v is None:
        return None
    if hasattr(v, "strftime"):
        return v.strftime("%Y-%m-%d %H:%M:%S")
    return str(v)


def _status_expr_sql() -> str:
    return """
        CASE
            WHEN SUM(CASE WHEN status = 'FAILED'  THEN 1 ELSE 0 END) > 0 THEN 'FAILED'
            WHEN SUM(CASE WHEN status = 'WARNING' THEN 1 ELSE 0 END) > 0 THEN 'WARNING'
            WHEN SUM(CASE WHEN status = 'RUNNING' THEN 1 ELSE 0 END) > 0 THEN 'RUNNING'
            WHEN SUM(CASE WHEN status = 'SUCCESS' THEN 1 ELSE 0 END) > 0 THEN 'SUCCESS'
            WHEN SUM(CASE WHEN status = 'SKIPPED' THEN 1 ELSE 0 END) > 0 THEN 'SKIPPED'
            ELSE 'DESCONHECIDO'
        END
    """


@router.get("/dashboard", tags=["dashboard"])
def get_dashboard(filter_project: Optional[str] = None, date_ref: Optional[str] = None):
    """KPIs + status + falhas + running. Substitui etl_dashboard_query."""
    fp = (filter_project or "").strip()
    dr = (date_ref or "").strip()
    if not dr:
        dr = datetime.now(LOCAL_TZ).strftime("%Y-%m-%d")

    try:
        dt_ini_obj = datetime.strptime(dr, "%Y-%m-%d").replace(tzinfo=LOCAL_TZ)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"date_ref inválido: '{dr}' — use YYYY-MM-DD")

    dt_ini = dt_ini_obj.strftime("%Y-%m-%d 00:00:00")
    dt_fim = (dt_ini_obj + timedelta(days=1)).strftime("%Y-%m-%d 00:00:00")

    where_proj       = " AND project = ?   "   if fp else ""
    where_proj_alias = " AND e.project = ? "   if fp else ""
    status_expr      = _status_expr_sql()

    try:
        conn = get_db_conn()
        cur  = conn.cursor()

        cur.execute(f"""
            WITH execs AS (
                SELECT execution_id, project, pipeline,
                    -- Relógio de parede (não a SOMA): jobs paralelos inflavam a média.
                    DATEDIFF(SECOND, MIN(e.start_time),
                             MAX(COALESCE(e.end_time, GETDATE()))) AS duracao_total_segundos,
                    {status_expr} AS status_geral
                FROM dbo.etl_job_execution e
                JOIN dbo.etl_pipeline p ON p.pipeline_name = e.pipeline
                WHERE e.start_time >= ? AND e.start_time < ?
                  AND COALESCE(p.ambiente, 'PROD') = 'PROD'
                  {where_proj_alias}
                GROUP BY e.execution_id, e.project, e.pipeline
            )
            SELECT COUNT(*),
                SUM(CASE WHEN status_geral='SUCCESS' THEN 1 ELSE 0 END),
                SUM(CASE WHEN status_geral='FAILED'  THEN 1 ELSE 0 END),
                SUM(CASE WHEN status_geral='WARNING' THEN 1 ELSE 0 END),
                CAST(AVG(CAST(duracao_total_segundos AS float)) AS int)
            FROM execs
        """, [dt_ini, dt_fim] + ([fp] if fp else []))
        row = cur.fetchone()
        total_exec    = int(row[0] or 0) if row else 0
        total_sucesso = int(row[1] or 0) if row else 0
        total_falha   = int(row[2] or 0) if row else 0
        total_warning = int(row[3] or 0) if row else 0
        duracao_media = int(row[4] or 0) if row else 0
        taxa = round(total_sucesso * 100.0 / total_exec, 1) if total_exec else 0.0

        cur.execute(f"""
            WITH execs AS (
                SELECT execution_id, project, pipeline,
                    {status_expr} AS status_geral
                FROM dbo.etl_job_execution e
                JOIN dbo.etl_pipeline p ON p.pipeline_name = e.pipeline
                WHERE e.start_time >= ? AND e.start_time < ?
                  AND COALESCE(p.ambiente, 'PROD') = 'PROD'
                GROUP BY e.execution_id, e.project, e.pipeline
            )
            SELECT project, COUNT(*),
                SUM(CASE WHEN status_geral='FAILED'  THEN 1 ELSE 0 END),
                SUM(CASE WHEN status_geral='WARNING' THEN 1 ELSE 0 END)
            FROM execs {("WHERE project = ?" if fp else "")}
            GROUP BY project ORDER BY project
        """, [dt_ini, dt_fim] + ([fp] if fp else []))
        por_projeto = [
            {"project": r[0], "execucoes": int(r[1] or 0), "falhas": int(r[2] or 0), "warnings": int(r[3] or 0)}
            for r in cur.fetchall()
        ]

        # "Status por pipeline": TOP 5 por ATIVIDADE mais recente (início OU fim de
        # execução). atividade = fim do job mais recente da execução (MAX(end_time))
        # ou o início quando nada terminou ainda (execução em andamento). Assim um
        # pipeline que acabou de iniciar/encerrar aparece no topo, alinhado com o
        # painel "Rodando agora" — sem ser escondido por ordenação de criticidade.
        cur.execute(f"""
            WITH execs AS (
                SELECT e.execution_id, e.project, e.pipeline,
                    MIN(e.start_time) AS inicio,
                    MAX(e.end_time)   AS fim,
                    -- Relógio de parede (não a SOMA — jobs paralelos inflavam).
                    DATEDIFF(SECOND, MIN(e.start_time),
                             MAX(COALESCE(e.end_time, GETDATE()))) AS duracao_segundos,
                    COUNT(*) AS total_jobs,
                    {status_expr} AS ultimo_status
                FROM dbo.etl_job_execution e
                JOIN dbo.etl_pipeline p ON p.pipeline_name = e.pipeline
                WHERE e.start_time >= ? AND e.start_time < ?
                  AND COALESCE(p.ambiente, 'PROD') = 'PROD'
                  {where_proj_alias}
                GROUP BY e.execution_id, e.project, e.pipeline
            ),
            ranked AS (
                SELECT *,
                    COALESCE(fim, inicio) AS atividade,
                    ROW_NUMBER() OVER (
                        PARTITION BY pipeline
                        ORDER BY COALESCE(fim, inicio) DESC, inicio DESC
                    ) AS rn
                FROM execs
            )
            SELECT TOP 5
                r.pipeline, r.project, r.ultimo_status, r.inicio, r.duracao_segundos,
                r.total_jobs, r.execution_id, COALESCE(p.criticidade,'') AS criticidade,
                COALESCE(fila.fila_total, 0) AS fila_segundos
            FROM ranked r
            LEFT JOIN dbo.etl_pipeline p ON p.pipeline_name = r.pipeline
            LEFT JOIN (
                -- Escopo por pipeline TAMBÉM: execution_id (ts_nodash) colide entre
                -- pipelines agendadas no mesmo tick (migration 027) — sem o
                -- pipeline_name a fila somaria a espera de outra pipeline.
                SELECT execution_id, pipeline_name,
                       SUM(CAST(queued_seconds AS bigint)) AS fila_total
                FROM dbo.etl_ds_job_log
                WHERE queued_seconds IS NOT NULL AND queued_seconds > 0
                GROUP BY execution_id, pipeline_name
            ) fila ON fila.execution_id = r.execution_id
                  AND fila.pipeline_name = r.pipeline
            WHERE rn=1 AND COALESCE(p.ambiente,'PROD')='PROD'
            ORDER BY r.atividade DESC
        """, [dt_ini, dt_fim] + ([fp] if fp else []))
        pipeline_status = [
            {
                "pipeline": r[0], "project": r[1], "ultimo_status": r[2],
                "ultimo_inicio": _fmt_dt(r[3]), "duracao_segundos": int(r[4] or 0),
                "total_jobs": int(r[5] or 0), "execution_id": r[6], "criticidade": r[7] or "",
                "fila_segundos": int(r[8] or 0),
            }
            for r in cur.fetchall()
        ]

        cur.execute(f"""
            SELECT TOP 5
                e.pipeline, e.project, e.job_name, e.status, e.start_time, e.execution_id, e.log_file,
                CASE
                    WHEN ack.resolved_at IS NOT NULL THEN 'Resolvido'
                    WHEN ack.id IS NOT NULL          THEN 'Em análise'
                    ELSE                                  'Aguardando'
                END AS situacao
            FROM dbo.etl_job_execution e
            JOIN dbo.etl_pipeline p ON p.pipeline_name = e.pipeline
            LEFT JOIN dbo.etl_failure_ack ack ON ack.execution_id = e.execution_id AND ack.pipeline = e.pipeline
            WHERE e.status='FAILED'
              AND e.start_time >= ? AND e.start_time < ?
              AND COALESCE(p.ambiente,'PROD')='PROD' {where_proj_alias}
            ORDER BY e.start_time DESC
        """, [dt_ini, dt_fim] + ([fp] if fp else []))
        ultimas_falhas = [
            {"pipeline": r[0], "project": r[1], "job_name": r[2], "status": r[3],
             "inicio": _fmt_dt(r[4]), "execution_id": r[5], "log_file": r[6], "situacao": r[7]}
            for r in cur.fetchall()
        ]

        cur.execute(f"""
            WITH runs AS (
                SELECT execution_id, project, pipeline, MIN(start_time) AS inicio,
                    COUNT(*) AS total_jobs,
                    SUM(CASE WHEN status='RUNNING' THEN 1 ELSE 0 END) AS jobs_running,
                    SUM(CASE WHEN status='SUCCESS' THEN 1 ELSE 0 END) AS jobs_ok
                FROM dbo.etl_job_execution
                WHERE status='RUNNING' {where_proj}
                GROUP BY execution_id, project, pipeline
            )
            SELECT TOP 10 execution_id, project, pipeline, inicio,
                total_jobs, jobs_running, jobs_ok,
                DATEDIFF(SECOND, inicio, GETDATE()) AS elapsed_seconds
            FROM runs ORDER BY inicio DESC
        """, [fp] if fp else [])
        executando_agora = [
            {
                "execution_id": r[0], "project": r[1], "pipeline": r[2],
                "inicio": _fmt_dt(r[3]), "total_jobs": int(r[4] or 0),
                "jobs_running": int(r[5] or 0), "jobs_ok": int(r[6] or 0),
                "elapsed_seconds": int(r[7] or 0),
            }
            for r in cur.fetchall()
        ]

        cur.execute(f"""
            WITH running_exec AS (
                SELECT execution_id, project, pipeline, MIN(start_time) AS inicio,
                    DATEDIFF(SECOND, MIN(start_time), GETDATE()) AS elapsed_seconds,
                    DATEDIFF(HOUR,   MIN(start_time), GETDATE()) AS elapsed_hours
                FROM dbo.etl_job_execution
                WHERE status='RUNNING' {where_proj}
                GROUP BY execution_id, project, pipeline
            )
            SELECT TOP 10 execution_id, project, pipeline, inicio, elapsed_seconds,
                CASE WHEN elapsed_hours>=12 THEN 12 WHEN elapsed_hours>=6 THEN 6 ELSE 3 END
            FROM running_exec WHERE elapsed_seconds >= 10800
            ORDER BY elapsed_seconds DESC
        """, [fp] if fp else [])
        alertas_perf = [
            {
                "execution_id": r[0], "project": r[1], "pipeline": r[2],
                "inicio": _fmt_dt(r[3]), "elapsed_seconds": int(r[4] or 0),
                "alerta_horas": int(r[5] or 3),
            }
            for r in cur.fetchall()
        ]

        # Tempo de fila WM DataStage (graceful: coluna pode não existir ainda)
        fila_media = fila_max = fila_jobs = 0
        try:
            cur.execute("""
                SELECT CAST(AVG(CAST(queued_seconds AS float)) AS int),
                       MAX(queued_seconds), COUNT(*)
                FROM dbo.etl_ds_job_log
                WHERE queued_seconds IS NOT NULL AND queued_seconds > 0
                  AND created_at >= ? AND created_at < ?
            """, (dt_ini, dt_fim))
            frow = cur.fetchone()
            if frow:
                fila_media = int(frow[0] or 0)
                fila_max   = int(frow[1] or 0)
                fila_jobs  = int(frow[2] or 0)
        except Exception:
            try: conn.rollback()
            except Exception: pass

        cur.close()
        conn.close()

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro DB: {e}")

    return {
        "date_ref": dr,
        "kpis": {
            "total_execucoes": total_exec, "total_sucesso": total_sucesso,
            "total_falha": total_falha, "total_warning": total_warning,
            "taxa_sucesso_pct": taxa, "duracao_media_segundos": duracao_media,
            "fila_media_segundos": fila_media, "fila_max_segundos": fila_max,
            "fila_jobs": fila_jobs,
            "por_projeto": por_projeto, "filter_project": fp,
        },
        "pipeline_status": pipeline_status,
        "ultimas_falhas": ultimas_falhas,
        "executando_agora": executando_agora,
        "alertas_perf": alertas_perf,
    }


@router.get("/dashboard/gantt", tags=["dashboard"])
def get_dashboard_gantt(filter_project: Optional[str] = None, date_ref: Optional[str] = None):
    """Linha do tempo das execuções do dia (uma barra por execução de pipeline)."""
    fp = (filter_project or "").strip()
    dr = (date_ref or "").strip() or datetime.now(LOCAL_TZ).strftime("%Y-%m-%d")
    try:
        dt_ini_obj = datetime.strptime(dr, "%Y-%m-%d").replace(tzinfo=LOCAL_TZ)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"date_ref inválido: '{dr}'")
    dt_ini = dt_ini_obj.strftime("%Y-%m-%d 00:00:00")
    dt_fim = (dt_ini_obj + timedelta(days=1)).strftime("%Y-%m-%d 00:00:00")
    where_proj = " AND e.project = ? " if fp else ""
    status_expr = _status_expr_sql()

    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute(f"""
            SELECT e.execution_id, e.pipeline, e.project,
                MIN(e.start_time) AS inicio,
                MAX(COALESCE(e.end_time, GETDATE())) AS fim,
                {status_expr} AS status_geral,
                COUNT(*) AS total_jobs,
                COALESCE(p.criticidade, '') AS criticidade
            FROM dbo.etl_job_execution e
            JOIN dbo.etl_pipeline p ON p.pipeline_name = e.pipeline
            WHERE e.start_time >= ? AND e.start_time < ?
              AND COALESCE(p.ambiente, 'PROD') = 'PROD'
              {where_proj}
            GROUP BY e.execution_id, e.pipeline, e.project, p.criticidade
            ORDER BY MIN(e.start_time)
        """, [dt_ini, dt_fim] + ([fp] if fp else []))
        data = [
            {
                "execution_id": r[0], "pipeline": r[1], "project": r[2],
                "inicio": _fmt_dt(r[3]), "fim": _fmt_dt(r[4]),
                "status": r[5], "total_jobs": int(r[6] or 0),
                "criticidade": r[7] or "",
            }
            for r in cur.fetchall()
        ]
        cur.close(); conn.close()
        return {"date_ref": dr, "data": data}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro DB: {e}")
