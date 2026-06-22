"""api/routers/datastage.py — POST /datastage/monitor, GET /datastage/log, GET /datastage/status."""
from __future__ import annotations

import json as _json
import logging

import httpx
from fastapi import APIRouter, Body, Depends, HTTPException, Query

from db import get_db_conn
from deps import (
    AIRFLOW_URL, AIRFLOW_USER, AIRFLOW_PASSWORD,
    PERM_EXECUTAR,
    require_perm, get_admin_user,
)
from services.ssh_datastage import (
    DSJOB_COMMANDS, DsConsoleError, run_dsjob, ssh_configured,
)

log = logging.getLogger("orquestra-api")

router = APIRouter()


def get_airflow_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=AIRFLOW_URL,
        auth=(AIRFLOW_USER, AIRFLOW_PASSWORD),
        timeout=15,
    )


@router.post("/datastage/monitor")
async def datastage_monitor_trigger(body: dict = Body(...), _auth: dict = Depends(require_perm(PERM_EXECUTAR))):
    """
    Dispara a DAG etl_datastage_monitor para monitorar um job já em execução.

    Body: { "project": "BI_VIDA", "job_name": "SeqExecCargaVida", "poll_interval": 60 }
    """
    import datetime as _dt
    project      = (body.get("project") or "").strip()
    job_name     = (body.get("job_name") or "").strip()
    poll_interval = int(body.get("poll_interval", 60))

    if not job_name:
        raise HTTPException(status_code=422, detail="job_name é obrigatório")
    if not project:
        raise HTTPException(status_code=422, detail="project é obrigatório")

    run_id = f"monitor_{job_name}_{_dt.datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}"

    async with get_airflow_client() as client:
        r = await client.post(
            "/api/v1/dags/etl_datastage_monitor/dagRuns",
            json={
                "dag_run_id": run_id,
                "conf": {
                    "project":       project,
                    "job_name":      job_name,
                    "poll_interval": poll_interval,
                },
            },
        )
        if r.status_code not in (200, 201):
            raise HTTPException(
                status_code=r.status_code,
                detail=f"Airflow recusou trigger: {r.text[:300]}",
            )

    return {
        "status":       "monitor_iniciado",
        "dag_run_id":   run_id,
        "project":      project,
        "job_name":     job_name,
        "poll_interval": poll_interval,
    }


@router.get("/datastage/log")
async def datastage_log_query(
    pipeline_name: str = Query(...),
    job_name:      str = Query(None),
    execution_id:  str = Query(None),
    project:       str = Query(None),
    limit:         int = Query(10),
):
    """
    Consulta logs detalhados DataStage persistidos em etl_ds_job_log.

    pipeline_name é obrigatório: execution_id por si só pode colidir entre
    pipelines diferentes disparados no mesmo timestamp (ts_nodash).
    Demais parâmetros são opcionais: job_name, execution_id, project, limit (default 10)
    """
    try:
        conn   = get_db_conn()
        cursor = conn.cursor()

        where_parts  = []
        params: list = []

        if execution_id:
            where_parts.append("execution_id = ?"); params.append(execution_id)
        if job_name:
            where_parts.append("job_name = ?"); params.append(job_name)
        if project:
            where_parts.append("project = ?"); params.append(project)
        if pipeline_name:
            where_parts.append("pipeline_name = ?"); params.append(pipeline_name)

        where = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""

        base_cols = (
            "id, execution_id, pipeline_name, job_name, project, "
            "wave_number, pid, status, status_code, child_jobs, "
            "log_summary, poll_snapshots, last_polled_at, created_at, updated_at, "
            "ds_start_time, ds_end_time"
        )
        try:
            cursor.execute(
                f"SELECT TOP (?) {base_cols}, queued_seconds "
                f"FROM dbo.etl_ds_job_log {where} ORDER BY created_at DESC",
                [limit] + params,
            )
        except Exception:
            # coluna queued_seconds pode não existir (migration 016 não aplicada)
            try: conn.rollback()
            except Exception: pass
            cursor = conn.cursor()
            cursor.execute(
                f"SELECT TOP (?) {base_cols} "
                f"FROM dbo.etl_ds_job_log {where} ORDER BY created_at DESC",
                [limit] + params,
            )
        cols = [d[0] for d in cursor.description]
        rows = [dict(zip(cols, row)) for row in cursor.fetchall()]
        cursor.close(); conn.close()

        for row in rows:
            for field in ("child_jobs", "poll_snapshots"):
                raw = row.get(field)
                if raw and isinstance(raw, str):
                    try:
                        row[field] = _json.loads(raw)
                    except Exception:
                        pass
            for field in ("last_polled_at", "created_at", "updated_at"):
                if row.get(field) and hasattr(row[field], "isoformat"):
                    row[field] = row[field].isoformat()

        return {"total": len(rows), "logs": rows}
    except Exception as e:
        log.exception("Erro ao consultar etl_ds_job_log")
        raise HTTPException(status_code=500, detail=f"Erro ao consultar DS log: {e}")


@router.get("/datastage/console/config")
async def datastage_console_config(_admin: dict = Depends(get_admin_user)):
    """
    Metadados para o Console DataStage do Admin: se o SSH está configurado no
    servidor e a lista de comandos read-only disponíveis (id, rótulo, se exige job).
    """
    return {
        "configured": ssh_configured(),
        "commands": [
            {"id": cid, "label": spec["label"], "needs_job": spec["needs_job"]}
            for cid, spec in DSJOB_COMMANDS.items()
        ],
    }


@router.post("/datastage/console")
async def datastage_console_exec(body: dict = Body(...), user: dict = Depends(get_admin_user)):
    """
    Console DataStage: executa um subcomando `dsjob` (read-only) no servidor Unix
    via SSH e devolve a saída crua para a UI formatar.

    Body: { "command": "jobinfo", "project": "BI_VIDA", "job": "SeqSsdVida7Peps", "max_lines": 200 }

    Somente admin (acao_admin). project/job são validados por allowlist estrita
    e só comandos de consulta são aceitos (sem -run/-reset/-stop).
    """
    command   = (body.get("command") or "").strip()
    project   = (body.get("project") or "").strip()
    job       = (body.get("job") or "").strip() or None
    max_lines = body.get("max_lines", 200)

    try:
        result = run_dsjob(command, project, job, max_lines)
    except DsConsoleError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        log.exception("Console DataStage: falha ao executar dsjob via SSH")
        raise HTTPException(status_code=502, detail=f"Falha ao executar dsjob via SSH: {e}")

    log.info(
        "DS console: user=%s command=%s project=%s job=%s exit=%s",
        user.get("matricula"), command, project, job, result.get("exit_code"),
    )
    return {"command": command, "project": project, "job": job, **result}


@router.get("/datastage/status")
async def datastage_job_status(
    project:       str = Query(...),
    job_name:      str = Query(...),
    pipeline_name: str = Query(None),
):
    """
    Retorna status atual de um job DataStage diretamente do último log persistido.
    Usado pelo painel de monitor no ORQUESTRA para refresh sem novo trigger.

    pipeline_name é opcional aqui para não quebrar o monitor de trigger
    (que ainda não conhece o nome do pipeline antes do disparo), mas deve
    ser informado sempre que disponível para evitar ambiguidade entre
    pipelines distintos com o mesmo project/job_name.
    """
    try:
        conn   = get_db_conn()
        cursor = conn.cursor()
        where  = "WHERE project = ? AND job_name = ?"
        params = [project, job_name]
        if pipeline_name:
            where += " AND pipeline_name = ?"
            params.append(pipeline_name)
        cursor.execute(
            f"""
            SELECT TOP 1 status, status_code, wave_number, pid,
                         child_jobs, poll_snapshots, last_polled_at, updated_at
            FROM dbo.etl_ds_job_log
            {where}
            ORDER BY created_at DESC
            """,
            params,
        )
        row = cursor.fetchone()
        cursor.close(); conn.close()

        if not row:
            raise HTTPException(
                status_code=404,
                detail=f"Nenhum log encontrado para {project}/{job_name}",
            )

        cols = ["status", "status_code", "wave_number", "pid",
                "child_jobs", "poll_snapshots", "last_polled_at", "updated_at"]
        data = dict(zip(cols, row))

        for field in ("child_jobs", "poll_snapshots"):
            raw = data.get(field)
            if raw and isinstance(raw, str):
                try:
                    data[field] = _json.loads(raw)
                except Exception:
                    pass
        for field in ("last_polled_at", "updated_at"):
            if data.get(field) and hasattr(data[field], "isoformat"):
                data[field] = data[field].isoformat()

        return {"project": project, "job_name": job_name, **data}
    except HTTPException:
        raise
    except Exception as e:
        log.exception("Erro ao consultar status DS")
        raise HTTPException(status_code=500, detail=f"Erro ao consultar DS status: {e}")
