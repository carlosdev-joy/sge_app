"""api/routers/execucoes.py — GET /execucoes, POST /execucoes/rerun, POST /execucoes/ack, GET /execucoes/duracao-media."""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from typing import Optional

import httpx
from fastapi import APIRouter, Body, Depends, HTTPException, Query

from db import get_db_conn
from deps import (
    AIRFLOW_URL, AIRFLOW_USER, AIRFLOW_PASSWORD,
    PERM_EXECUTAR,
    get_current_user, require_perm,
)

log = logging.getLogger("orquestra-api")

router = APIRouter()

MAX_LIMIT = 200


def _fmt_dt(v):
    if v is None:
        return None
    if hasattr(v, "strftime"):
        return v.strftime("%Y-%m-%d %H:%M:%S")
    return str(v)


def get_airflow_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=AIRFLOW_URL,
        auth=(AIRFLOW_USER, AIRFLOW_PASSWORD),
        timeout=15,
    )


def _get_app_config_value(key: str) -> str | None:
    """Lê um parâmetro único de dbo.etl_app_config. Retorna None se ausente/erro."""
    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute("SELECT config_value FROM dbo.etl_app_config WHERE config_key=?", (key,))
        row = cur.fetchone()
        cur.close(); conn.close()
        val = (row[0] or "").strip() if row else ""
        return val or None
    except Exception as e:
        log.warning("etl_app_config leitura de '%s' falhou: %s", key, e)
        return None


def _teams_ack_card(pipeline: str, exec_id: str, ack_by: str, display_name: str,
                    ack_at: str, note: str | None, webhook_var: str) -> None:
    """Posta card no Teams informando que alguém assumiu a falha.

    Ordem de resolução do webhook:
      1. dbo.etl_app_config chave 'teams_webhook_url_ack' (canal dedicado a acks)
      2. dbo.etl_app_config chave 'teams_webhook_url'     (canal padrão/geral)
      3. variável de ambiente TEAMS_WEBHOOK_URL_CVP
    """
    webhook_url = _get_app_config_value("teams_webhook_url_ack") \
        or _get_app_config_value("teams_webhook_url") \
        or os.getenv("TEAMS_WEBHOOK_URL_CVP", "")
    if not webhook_url:
        log.warning("[ACK] webhook do Teams não configurado — cadastre o parâmetro "
                    "'teams_webhook_url_ack' em Admin > Configurações. Notificação ignorada.")
        return

    identity = f"{display_name} ({ack_by})" if display_name and display_name != ack_by else ack_by
    facts = [
        {"title": "Pipeline",    "value": pipeline},
        {"title": "Responsável", "value": identity},
        {"title": "Matrícula",   "value": ack_by},
        {"title": "Assumido em", "value": ack_at or "agora"},
        {"title": "Execution ID","value": exec_id},
    ]
    if note:
        facts.append({"title": "Observação", "value": note})

    payload = {
        "type": "message",
        "attachments": [{
            "contentType": "application/vnd.microsoft.card.adaptive",
            "content": {
                "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                "type": "AdaptiveCard", "version": "1.4",
                "body": [
                    {"type": "TextBlock",
                     "text": f"👁 Falha assumida para análise",
                     "size": "Large", "weight": "Bolder", "wrap": True, "color": "Accent"},
                    {"type": "TextBlock",
                     "text": f"{identity} está investigando a falha no pipeline {pipeline}.",
                     "wrap": True, "spacing": "None", "isSubtle": True},
                    {"type": "FactSet", "spacing": "Medium", "facts": facts},
                ],
            },
        }],
    }
    try:
        resp = httpx.post(webhook_url, json=payload, timeout=10)
        log.info("[ACK] Teams status=%s body=%.120s", resp.status_code, resp.text)
    except Exception as e:
        log.warning("[ACK] Falha ao enviar Teams: %s", e)


@router.get("/execucoes", tags=["execucoes"])
def list_execucoes(
    offset: int = 0,
    limit: int = 50,
    filter_project: Optional[str] = None,
    filter_pipeline: Optional[str] = None,
    filter_execution_id: Optional[str] = None,
    filter_status: Optional[str] = None,
    filter_hours_back: Optional[int] = None,
    filter_date_from: Optional[str] = None,
    filter_date_to: Optional[str] = None,
    detail_mode: bool = False,
):
    """Consulta paginada de execuções. Substitui etl_job_execution_query."""
    limit  = min(MAX_LIMIT, max(1, limit))
    offset = max(0, offset)
    fp  = (filter_project  or "").strip()
    fpl = (filter_pipeline or "").strip()
    fei = (filter_execution_id or "").strip()
    fst = (filter_status   or "").strip().upper()
    fdf = (filter_date_from or "").strip()
    fdt = (filter_date_to   or "").strip()
    fhb = filter_hours_back if (filter_hours_back and filter_hours_back > 0) else None

    where_parts: list[str] = []
    params: list = []

    if fp:
        where_parts.append("project = ?")
        params.append(fp)
    if fpl:
        where_parts.append("pipeline LIKE ?")
        params.append(f"%{fpl}%")
    if fei:
        where_parts.append("execution_id = ?")
        params.append(fei)
    if fhb:
        where_parts.append(f"start_time >= DATEADD(hour, -{fhb}, GETDATE())")
    elif fdf:
        where_parts.append("start_time >= ?")
        params.append(fdf + " 00:00:00")
    if fdt:
        try:
            dt_to = (datetime.strptime(fdt, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
            where_parts.append("start_time < ?")
            params.append(dt_to + " 00:00:00")
        except Exception:
            where_parts.append("start_time < ?")
            params.append(fdt + " 23:59:59")

    where_sql = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""

    status_expr = """
        CASE
            WHEN SUM(CASE WHEN status='FAILED'  THEN 1 ELSE 0 END) > 0 THEN 'FAILED'
            WHEN SUM(CASE WHEN status='WARNING' THEN 1 ELSE 0 END) > 0 THEN 'WARNING'
            WHEN SUM(CASE WHEN status='RUNNING' THEN 1 ELSE 0 END) > 0 THEN 'RUNNING'
            WHEN SUM(CASE WHEN status='SUCCESS' THEN 1 ELSE 0 END) > 0 THEN 'SUCCESS'
            ELSE 'DESCONHECIDO'
        END
    """

    try:
        conn = get_db_conn()
        cur  = conn.cursor()

        if detail_mode:
            if fst:
                where_parts.append("status = ?")
                params.append(fst)
                where_sql = "WHERE " + " AND ".join(where_parts)

            cur.execute(f"SELECT COUNT(*) FROM dbo.etl_job_execution {where_sql}", params)
            total = cur.fetchone()[0]

            cur.execute(f"""
                SELECT execution_id, project, pipeline, job_name, status,
                       start_time, end_time, duration_seconds, status_code, log_file, task_id
                FROM dbo.etl_job_execution
                {where_sql}
                ORDER BY start_time DESC
                OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
            """, params + [offset, limit])
            data = [
                {
                    "execution_id": r[0], "project": r[1], "pipeline": r[2],
                    "job_name": r[3], "status": r[4],
                    "inicio": _fmt_dt(r[5]), "fim": _fmt_dt(r[6]),
                    "duration_seconds": int(r[7] or 0) if r[7] is not None else None,
                    "status_code": r[8], "log_file": r[9], "task_id": r[10],
                }
                for r in cur.fetchall()
            ]
            cur.close(); conn.close()
            pages = 0 if total == 0 else -(-total // limit)
            return {
                "mode": "detail", "total": int(total), "offset": offset,
                "limit": limit, "pages": pages,
                "filters": {"project": fp, "pipeline": fpl, "execution_id": fei,
                            "status": fst, "date_from": fdf, "date_to": fdt},
                "data": data,
            }

        # Aggregated mode
        having_sql    = ""
        having_params: list = []
        if fst:
            having_sql = f"HAVING {status_expr} = ?"
            having_params.append(fst)

        cur.execute(f"""
            SELECT COUNT(*) FROM (
                SELECT execution_id, project, pipeline
                FROM dbo.etl_job_execution
                {where_sql}
                GROUP BY execution_id, project, pipeline
                {having_sql}
            ) t
        """, params + having_params)
        total = cur.fetchone()[0]

        agg_cte = f"""
            WITH agg AS (
                SELECT
                    execution_id, project, pipeline,
                    MIN(start_time)                    AS inicio,
                    MAX(end_time)                      AS fim,
                    COALESCE(SUM(duration_seconds), 0) AS duracao_total_segundos,
                    COUNT(*)                           AS total_jobs,
                    SUM(CASE WHEN status='SUCCESS' THEN 1 ELSE 0 END) AS jobs_ok,
                    SUM(CASE WHEN status='FAILED'  THEN 1 ELSE 0 END) AS jobs_falha,
                    SUM(CASE WHEN status='WARNING' THEN 1 ELSE 0 END) AS jobs_warning,
                    SUM(CASE WHEN status='RUNNING' THEN 1 ELSE 0 END) AS jobs_running,
                    {status_expr} AS status_geral
                FROM dbo.etl_job_execution
                {where_sql}
                GROUP BY execution_id, project, pipeline
                {having_sql}
            )
        """
        # etl_failure_ack pode não existir ainda (migration 013) — degrada sem ack
        has_ack = True
        has_resolved = False
        try:
            cur.execute(agg_cte + """
                SELECT a.*, ack.ack_by, ack.display_name, ack.ack_at,
                       ack.resolved_by, ack.resolved_at, ack.resolution_note, ack.snow_ticket
                FROM agg a
                LEFT JOIN dbo.etl_failure_ack ack
                       ON ack.execution_id = a.execution_id AND ack.pipeline = a.pipeline
                ORDER BY a.inicio DESC
                OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
            """, params + having_params + [offset, limit])
            has_resolved = True
        except Exception:
            try: conn.rollback()
            except Exception: pass
            try:
                cur.execute(agg_cte + """
                    SELECT a.*, ack.ack_by, ack.display_name, ack.ack_at
                    FROM agg a
                    LEFT JOIN dbo.etl_failure_ack ack
                           ON ack.execution_id = a.execution_id AND ack.pipeline = a.pipeline
                    ORDER BY a.inicio DESC
                    OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
                """, params + having_params + [offset, limit])
            except Exception:
                has_ack = False
                try: conn.rollback()
                except Exception: pass
                cur.execute(agg_cte + """
                    SELECT a.* FROM agg a
                    ORDER BY a.inicio DESC
                    OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
                """, params + having_params + [offset, limit])
        data = [
            {
                "execution_id": r[0], "project": r[1], "pipeline": r[2],
                "inicio": _fmt_dt(r[3]), "fim": _fmt_dt(r[4]),
                "duracao_total_segundos": int(r[5] or 0),
                "total_jobs": int(r[6] or 0), "jobs_ok": int(r[7] or 0),
                "jobs_falha": int(r[8] or 0), "jobs_warning": int(r[9] or 0),
                "jobs_running": int(r[10] or 0), "status_geral": r[11],
                "ack_by": r[12] if has_ack else None,
                "display_name": r[13] if has_ack else None,
                "ack_at": _fmt_dt(r[14]) if has_ack else None,
                "resolved_by": r[15] if has_resolved else None,
                "resolved_at": _fmt_dt(r[16]) if has_resolved else None,
                "resolution_note": r[17] if has_resolved else None,
                "snow_ticket": r[18] if has_resolved else None,
            }
            for r in cur.fetchall()
        ]
        cur.close(); conn.close()
        pages = 0 if total == 0 else -(-total // limit)
        return {
            "total": int(total), "offset": offset, "limit": limit, "pages": pages,
            "filters": {"project": fp, "pipeline": fpl, "status": fst,
                        "hours_back": fhb, "date_from": fdf, "date_to": fdt},
            "data": data,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/execucoes/rerun", tags=["execucoes"])
async def rerun_from_task(body: dict = Body(default={}), _auth: dict = Depends(require_perm(PERM_EXECUTAR))):
    """Limpa tasks a partir de um job específico e reexecuta o DAG.

    Body:
      pipeline_name  — nome do pipeline (= dag_id no Airflow)
      execution_id   — execution_id da execução original (usado para localizar o dag_run_id)
      task_id        — task_id a partir da qual reexecutar (inclusive, com downstream)
      dag_run_id     — dag_run_id real (opcional; se não informado, tenta resolver via API)
    """
    pipeline   = (body.get("pipeline_name") or "").strip()
    exec_id    = (body.get("execution_id")  or "").strip()
    task_id    = (body.get("task_id")       or "").strip()
    dag_run_id = (body.get("dag_run_id")    or "").strip()

    if not pipeline or not task_id:
        raise HTTPException(status_code=422, detail="pipeline_name e task_id são obrigatórios")

    dag_id = pipeline  # no Airflow o dag_id = pipeline_name exato

    async with get_airflow_client() as client:
        # 1. Resolver dag_run_id se não fornecido
        if not dag_run_id:
            r = await client.get(f"/api/v1/dags/{dag_id}/dagRuns",
                                 params={"limit": 50, "order_by": "-execution_date"})
            if not r.is_success:
                raise HTTPException(status_code=502, detail=f"Airflow: {r.status_code}")
            runs = r.json().get("dag_runs", [])
            if not runs:
                raise HTTPException(status_code=404, detail="Nenhum dag_run encontrado para este pipeline")
            # Tentar casar pelo execution_id (formato ts_nodash) ou pegar o mais recente com falha
            chosen = None
            for run in runs:
                if run.get("state") in ("failed", "success"):
                    chosen = run; break
            dag_run_id = (chosen or runs[0])["dag_run_id"]

        # 2. Limpar a task e downstream via clearTaskInstances
        clear_body = {
            "dry_run": False,
            "task_ids": [task_id],
            "include_downstream": True,
            "include_future": False,
            "include_past": False,
            "include_upstream": False,
            "reset_dag_runs": True,
        }
        r2 = await client.post(
            f"/api/v1/dags/{dag_id}/clearTaskInstances",
            json=clear_body,
        )
        if not r2.is_success:
            raise HTTPException(status_code=502,
                detail=f"Airflow clearTaskInstances falhou: {r2.status_code} — {r2.text[:300]}")

        cleared = r2.json()
        log.info("Rerun %s/%s a partir de %s — %s tasks limpas",
                 dag_id, dag_run_id, task_id, len(cleared.get("task_instances", [])))

        return {
            "ok": True,
            "pipeline_name": pipeline,
            "dag_id": dag_id,
            "dag_run_id": dag_run_id,
            "task_id": task_id,
            "tasks_cleared": len(cleared.get("task_instances", [])),
        }


@router.post("/execucoes/ack", tags=["execucoes"])
async def ack_failure(body: dict = Body(default={}), _auth: dict = Depends(require_perm(PERM_EXECUTAR))):
    """Acknowledge de falha — operador assume o incidente e notifica o Teams.

    Body: execution_id, pipeline, user (matrícula), display_name (nome completo),
          note (opcional), remove (bool, desfaz)
    """
    exec_id      = (body.get("execution_id") or "").strip()
    pipeline     = (body.get("pipeline")     or "").strip()
    user         = (body.get("user")         or "").strip()
    display_name = (body.get("display_name") or "").strip() or None
    note         = (body.get("note")         or "").strip() or None
    remove       = bool(body.get("remove", False))

    if not exec_id or not pipeline:
        raise HTTPException(status_code=422, detail="execution_id e pipeline são obrigatórios")
    if not remove and not user:
        raise HTTPException(status_code=422, detail="user é obrigatório")

    try:
        conn = get_db_conn(); cur = conn.cursor()
        if remove:
            cur.execute(
                "DELETE FROM dbo.etl_failure_ack WHERE execution_id=? AND pipeline=?",
                (exec_id, pipeline))
            conn.commit(); cur.close(); conn.close()
            return {"ok": True, "action": "removed"}

        # Idempotente: só insere se ainda não existe
        cur.execute("""
            IF NOT EXISTS (SELECT 1 FROM dbo.etl_failure_ack WHERE execution_id=? AND pipeline=?)
                INSERT INTO dbo.etl_failure_ack (execution_id, pipeline, ack_by, display_name, note)
                VALUES (?, ?, ?, ?, ?)
        """, (exec_id, pipeline, exec_id, pipeline, user, display_name, note))
        conn.commit()

        cur.execute(
            "SELECT ack_by, display_name, ack_at FROM dbo.etl_failure_ack "
            "WHERE execution_id=? AND pipeline=?",
            (exec_id, pipeline))
        row = cur.fetchone()
        cur.close(); conn.close()

        ack_by_db      = row[0] if row else user
        display_name_db = row[1] if row else display_name
        ack_at_db      = _fmt_dt(row[2]) if row else None

        # Notificar Teams (em background — falha silenciosa para não bloquear o ACK)
        try:
            _teams_ack_card(
                pipeline=pipeline, exec_id=exec_id,
                ack_by=ack_by_db, display_name=display_name_db or ack_by_db,
                ack_at=ack_at_db, note=note,
                webhook_var="TEAMS_WEBHOOK_URL_CVP",
            )
        except Exception as e:
            log.warning("[ACK] Teams ignorado: %s", e)

        return {"ok": True, "action": "acked",
                "ack_by": ack_by_db,
                "display_name": display_name_db or ack_by_db,
                "ack_at": ack_at_db}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/execucoes/falhas-summary", tags=["execucoes"])
def get_falhas_summary(days: int = Query(7, ge=1, le=90)):
    """Retorna contadores de falhas para os cards de KPI da tela de Logs.

    Retorna: total, sem_ack, com_ack, resolvidas — no período (days).
    Degrada graciosamente se colunas resolved_* ainda não existem.
    """
    try:
        conn = get_db_conn(); cur = conn.cursor()

        # Garante colunas de resolução (idempotente)
        for col, ddl in [
            ("resolved_by",       "NVARCHAR(64)"),
            ("resolved_at",       "DATETIME"),
            ("resolution_note",   "NVARCHAR(500)"),
            ("snow_ticket",       "NVARCHAR(64)"),
        ]:
            try:
                cur.execute(f"""
                    IF NOT EXISTS (
                        SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
                        WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME='etl_failure_ack'
                          AND COLUMN_NAME=?
                    ) ALTER TABLE dbo.etl_failure_ack ADD {col} {ddl} NULL
                """, (col,))
                conn.commit()
            except Exception:
                try: conn.rollback()
                except Exception: pass

        cutoff = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")

        # Total falhas no período
        cur.execute("""
            SELECT COUNT(DISTINCT a.execution_id)
            FROM dbo.etl_pipeline_execution a
            WHERE a.status_geral = 'FAILED' AND a.start_time >= ?
        """, (cutoff,))
        row = cur.fetchone()
        total = int(row[0]) if row else 0

        # Sem ack (não assumidas)
        cur.execute("""
            SELECT COUNT(DISTINCT a.execution_id)
            FROM dbo.etl_pipeline_execution a
            LEFT JOIN dbo.etl_failure_ack ack
                   ON ack.execution_id = a.execution_id AND ack.pipeline = a.pipeline
            WHERE a.status_geral = 'FAILED' AND a.start_time >= ?
              AND ack.execution_id IS NULL
        """, (cutoff,))
        row = cur.fetchone()
        sem_ack = int(row[0]) if row else 0

        # Com ack mas não resolvidas
        has_resolved = False
        try:
            cur.execute("""
                SELECT COUNT(DISTINCT a.execution_id)
                FROM dbo.etl_pipeline_execution a
                INNER JOIN dbo.etl_failure_ack ack
                        ON ack.execution_id = a.execution_id AND ack.pipeline = a.pipeline
                WHERE a.status_geral = 'FAILED' AND a.start_time >= ?
                  AND ack.resolved_at IS NULL
            """, (cutoff,))
            row = cur.fetchone()
            com_ack = int(row[0]) if row else 0

            cur.execute("""
                SELECT COUNT(DISTINCT a.execution_id)
                FROM dbo.etl_pipeline_execution a
                INNER JOIN dbo.etl_failure_ack ack
                        ON ack.execution_id = a.execution_id AND ack.pipeline = a.pipeline
                WHERE a.status_geral = 'FAILED' AND a.start_time >= ?
                  AND ack.resolved_at IS NOT NULL
            """, (cutoff,))
            row = cur.fetchone()
            resolvidas = int(row[0]) if row else 0
            has_resolved = True
        except Exception:
            try: conn.rollback()
            except Exception: pass
            # Sem coluna resolved_at: considera tudo como com_ack não resolvido
            cur.execute("""
                SELECT COUNT(DISTINCT a.execution_id)
                FROM dbo.etl_pipeline_execution a
                INNER JOIN dbo.etl_failure_ack ack
                        ON ack.execution_id = a.execution_id AND ack.pipeline = a.pipeline
                WHERE a.status_geral = 'FAILED' AND a.start_time >= ?
            """, (cutoff,))
            row = cur.fetchone()
            com_ack = int(row[0]) if row else 0
            resolvidas = 0

        cur.close(); conn.close()
        return {
            "period_days": days,
            "total": total,
            "sem_ack": sem_ack,
            "com_ack": com_ack,
            "resolvidas": resolvidas,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/execucoes/resolve", tags=["execucoes"])
async def resolve_failure(body: dict = Body(default={}), user: dict = Depends(require_perm(PERM_EXECUTAR))):
    """Marca uma falha como resolvida (ou desfaz a resolução com remove=true).

    Body: execution_id, pipeline, resolution_note (opcional), snow_ticket (opcional),
          remove (bool, desfaz)
    """
    exec_id         = (body.get("execution_id") or "").strip()
    pipeline        = (body.get("pipeline")     or "").strip()
    resolution_note = (body.get("resolution_note") or "").strip() or None
    snow_ticket     = (body.get("snow_ticket")  or "").strip() or None
    remove          = bool(body.get("remove", False))
    matricula       = (body.get("user")         or "").strip() or user.get("matricula", "")
    display_name    = (body.get("display_name") or "").strip() or None

    if not exec_id or not pipeline:
        raise HTTPException(status_code=422, detail="execution_id e pipeline são obrigatórios")

    try:
        conn = get_db_conn(); cur = conn.cursor()

        if remove:
            cur.execute("""
                UPDATE dbo.etl_failure_ack
                SET resolved_by=NULL, resolved_at=NULL, resolution_note=NULL, snow_ticket=NULL
                WHERE execution_id=? AND pipeline=?
            """, (exec_id, pipeline))
            conn.commit(); cur.close(); conn.close()
            return {"ok": True, "action": "unresolved"}

        # Garante que existe ack (cria se não existir)
        cur.execute("""
            IF NOT EXISTS (SELECT 1 FROM dbo.etl_failure_ack WHERE execution_id=? AND pipeline=?)
                INSERT INTO dbo.etl_failure_ack (execution_id, pipeline, ack_by, display_name)
                VALUES (?, ?, ?, ?)
        """, (exec_id, pipeline, exec_id, pipeline, matricula, display_name))

        cur.execute("""
            UPDATE dbo.etl_failure_ack
            SET resolved_by=?, resolved_at=GETDATE(), resolution_note=?, snow_ticket=?
            WHERE execution_id=? AND pipeline=?
        """, (matricula, resolution_note, snow_ticket, exec_id, pipeline))
        conn.commit()

        cur.execute(
            "SELECT resolved_by, resolved_at, resolution_note, snow_ticket "
            "FROM dbo.etl_failure_ack WHERE execution_id=? AND pipeline=?",
            (exec_id, pipeline))
        row = cur.fetchone()
        cur.close(); conn.close()

        return {
            "ok": True,
            "action": "resolved",
            "resolved_by": row[0] if row else matricula,
            "resolved_at": _fmt_dt(row[1]) if row else None,
            "resolution_note": row[2] if row else resolution_note,
            "snow_ticket": row[3] if row else snow_ticket,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/execucoes/falhas", tags=["execucoes"])
def list_falhas(
    days: int = Query(7, ge=1, le=90),
    status_ack: Optional[str] = Query(None),  # "sem_ack" | "com_ack" | "resolvida"
    filter_pipeline: Optional[str] = None,
    filter_project: Optional[str] = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    """Lista execuções com falha no período, com dados de ack e resolução.

    Usado na aba 'Gestão de Falhas'.
    """
    try:
        conn = get_db_conn(); cur = conn.cursor()
        cutoff = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")

        where = ["a.status_geral = 'FAILED'", "a.start_time >= ?"]
        params: list = [cutoff]

        if filter_pipeline:
            where.append("a.pipeline LIKE ?")
            params.append(f"%{filter_pipeline}%")
        if filter_project:
            where.append("a.project = ?")
            params.append(filter_project)

        has_resolved = False
        try:
            cur.execute("""
                SELECT COUNT(DISTINCT a.execution_id)
                FROM dbo.etl_pipeline_execution a
                LEFT JOIN dbo.etl_failure_ack ack
                       ON ack.execution_id = a.execution_id AND ack.pipeline = a.pipeline
                WHERE """ + " AND ".join(where), params)
            cur.fetchone()
            has_resolved = True
        except Exception:
            try: conn.rollback()
            except Exception: pass

        # status_ack filter
        if status_ack == "sem_ack":
            where.append("ack.execution_id IS NULL")
        elif status_ack == "com_ack":
            where.append("ack.execution_id IS NOT NULL")
            if has_resolved:
                where.append("(ack.resolved_at IS NULL OR ack.resolved_at IS NULL)")
        elif status_ack == "resolvida":
            where.append("ack.execution_id IS NOT NULL")
            if has_resolved:
                where.append("ack.resolved_at IS NOT NULL")

        where_sql = " AND ".join(where)

        try:
            if has_resolved:
                cur.execute(f"""
                    SELECT COUNT(DISTINCT a.execution_id)
                    FROM dbo.etl_pipeline_execution a
                    LEFT JOIN dbo.etl_failure_ack ack
                           ON ack.execution_id = a.execution_id AND ack.pipeline = a.pipeline
                    WHERE {where_sql}
                """, params)
            else:
                cur.execute(f"""
                    SELECT COUNT(DISTINCT a.execution_id)
                    FROM dbo.etl_pipeline_execution a
                    LEFT JOIN dbo.etl_failure_ack ack
                           ON ack.execution_id = a.execution_id AND ack.pipeline = a.pipeline
                    WHERE {where_sql}
                """, params)
            total_row = cur.fetchone()
            total = int(total_row[0]) if total_row else 0
        except Exception:
            try: conn.rollback()
            except Exception: pass
            total = 0

        select_cols = """
            a.execution_id, a.project, a.pipeline, a.start_time, a.end_time,
            a.duracao_total_segundos, a.total_jobs, a.jobs_falha, a.jobs_warning,
            ack.ack_by, ack.display_name, ack.ack_at, ack.note
        """
        resolve_cols = ""
        if has_resolved:
            resolve_cols = ", ack.resolved_by, ack.resolved_at, ack.resolution_note, ack.snow_ticket"

        try:
            cur.execute(f"""
                SELECT {select_cols}{resolve_cols}
                FROM dbo.etl_pipeline_execution a
                LEFT JOIN dbo.etl_failure_ack ack
                       ON ack.execution_id = a.execution_id AND ack.pipeline = a.pipeline
                WHERE {where_sql}
                ORDER BY a.start_time DESC
                OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
            """, params + [offset, limit])
        except Exception:
            try: conn.rollback()
            except Exception: pass
            cur.execute(f"""
                SELECT {select_cols}
                FROM dbo.etl_pipeline_execution a
                LEFT JOIN dbo.etl_failure_ack ack
                       ON ack.execution_id = a.execution_id AND ack.pipeline = a.pipeline
                WHERE {where_sql}
                ORDER BY a.start_time DESC
                OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
            """, params + [offset, limit])
            has_resolved = False

        rows = cur.fetchall()
        cur.close(); conn.close()

        data = []
        for r in rows:
            item: dict = {
                "execution_id": r[0], "project": r[1], "pipeline": r[2],
                "inicio": _fmt_dt(r[3]), "fim": _fmt_dt(r[4]),
                "duracao_total_segundos": int(r[5] or 0),
                "total_jobs": int(r[6] or 0), "jobs_falha": int(r[7] or 0),
                "jobs_warning": int(r[8] or 0),
                "ack_by": r[9], "display_name": r[10], "ack_at": _fmt_dt(r[11]),
                "note": r[12],
                "resolved_by": r[13] if has_resolved else None,
                "resolved_at": _fmt_dt(r[14]) if has_resolved else None,
                "resolution_note": r[15] if has_resolved else None,
                "snow_ticket": r[16] if has_resolved else None,
            }
            data.append(item)

        return {"total": total, "offset": offset, "limit": limit, "data": data}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/execucoes/duracao-media", tags=["execucoes"])
def get_duracao_media(pipeline: str = Query(...), limit: int = Query(30, ge=5, le=200)):
    """Retorna duração média (P50) por job_name para um pipeline — usado para desvio de duração."""
    try:
        conn = get_db_conn(); cur = conn.cursor()
        # PERCENTILE_CONT é função de janela — não pode coexistir com GROUP BY
        # no mesmo nível; calculamos a janela em subquery e agregamos por fora.
        cur.execute(f"""
            SELECT job_name,
                   AVG(CAST(duration_seconds AS FLOAT)) AS avg_sec,
                   MAX(p50_sec) AS p50_sec,
                   COUNT(*) AS execucoes
            FROM (
                SELECT job_name, duration_seconds,
                       PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY duration_seconds)
                           OVER (PARTITION BY job_name) AS p50_sec
                FROM (
                    SELECT TOP {limit * 10} job_name, duration_seconds
                    FROM dbo.etl_job_execution
                    WHERE pipeline = ? AND status IN ('SUCCESS','WARNING')
                      AND duration_seconds IS NOT NULL AND duration_seconds > 0
                    ORDER BY start_time DESC
                ) base
            ) t
            GROUP BY job_name
        """, [pipeline])
        data = {r[0]: {"avg": round(r[1] or 0), "p50": round(r[2] or 0), "n": r[3]}
                for r in cur.fetchall()}
        cur.close(); conn.close()
        return {"pipeline": pipeline, "data": data}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
