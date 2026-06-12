"""api/routers/sync.py — GET /sync/pipeline-status/dry-run, POST /sync/pipeline-status."""
from __future__ import annotations

import logging
import os
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException

from db import get_db_conn
from deps import (
    AIRFLOW_URL, AIRFLOW_USER, AIRFLOW_PASSWORD,
    PERM_EXECUTAR,
    require_perm,
)

log = logging.getLogger("orquestra-api")

router = APIRouter()

DAGS_FOLDER = os.getenv("DAGS_FOLDER", "/opt/airflow/dags")


def get_airflow_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=AIRFLOW_URL,
        auth=(AIRFLOW_USER, AIRFLOW_PASSWORD),
        timeout=15,
    )


async def _fetch_airflow_dags() -> dict[str, dict]:
    async with get_airflow_client() as client:
        all_dags: dict[str, dict] = {}
        offset = 0; limit = 100
        while True:
            r = await client.get("/api/v1/dags", params={"limit": limit, "offset": offset})
            if r.status_code == 401:
                raise HTTPException(status_code=401, detail="Credenciais Airflow inválidas")
            r.raise_for_status()
            data = r.json(); dags = data.get("dags", [])
            for d in dags:
                all_dags[d["dag_id"]] = d
            if offset + limit >= data.get("total_entries", 0):
                break
            offset += limit
        return all_dags


def _dag_file_exists(pipeline_name: str) -> bool:
    generated_root = os.path.join(DAGS_FOLDER, "generated")
    if not os.path.isdir(generated_root):
        return False
    target = f"{pipeline_name}.py"
    for dirpath, _, filenames in os.walk(generated_root):
        if target in filenames:
            return True
    return False


def _build_sync_actions(pipelines: list[dict], airflow_dags: dict[str, dict]) -> list[dict[str, Any]]:
    actions = []
    for p in pipelines:
        name       = p["pipeline_name"]
        dag_criada = int(p["dag_criada"] or 0)
        active_now = int(p["active"]     or 0)

        if dag_criada == 0:
            actions.append({"pipeline": name, "action": "skip", "reason": "dag_criada=0 — ainda não gerada"})
            continue

        file_ok    = _dag_file_exists(name)
        airflow_ok = name in airflow_dags

        if not file_ok:
            actions.append({"pipeline": name, "action": "deactivate",
                             "reason": "arquivo .py não encontrado em dags/",
                             "set_active": 0, "set_dag_criada": 0})
            continue
        if not airflow_ok:
            actions.append({"pipeline": name, "action": "deactivate",
                             "reason": "DAG não encontrada no Airflow",
                             "set_active": 0, "set_dag_criada": 0})
            continue

        is_paused  = bool(airflow_dags[name].get("is_paused", False))
        new_active = 0 if is_paused else 1
        if new_active == active_now:
            actions.append({"pipeline": name, "action": "ok",
                             "reason": "status já sincronizado", "active": active_now})
        else:
            actions.append({"pipeline": name, "action": "sync",
                             "reason": f"Airflow is_paused={is_paused} → active={new_active}",
                             "set_active": new_active})
    return actions


def _apply_actions(actions: list[dict]) -> dict:
    deactivated = synced = skipped = ok_count = 0
    conn = get_db_conn(); cur = conn.cursor()
    try:
        for a in actions:
            if a["action"] == "ok":      ok_count += 1; continue
            if a["action"] == "skip":    skipped  += 1; continue
            if a["action"] == "deactivate":
                cur.execute(
                    "UPDATE dbo.etl_pipeline SET active=0, dag_criada=0, updated_at=GETDATE() WHERE pipeline_name=?",
                    (a["pipeline"],))
                deactivated += 1
            elif a["action"] == "sync":
                cur.execute(
                    "UPDATE dbo.etl_pipeline SET active=?, updated_at=GETDATE() WHERE pipeline_name=?",
                    (a["set_active"], a["pipeline"]))
                synced += 1
        conn.commit()
    finally:
        cur.close(); conn.close()
    return {"deactivated": deactivated, "synced": synced, "already_ok": ok_count, "skipped": skipped}


@router.get("/sync/pipeline-status/dry-run", tags=["sync"])
async def sync_dry_run():
    """Simula sincronização sem alterar banco."""
    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute("SELECT pipeline_name, active, dag_criada FROM dbo.etl_pipeline ORDER BY pipeline_name")
        pipelines = [{"pipeline_name": r[0], "active": r[1], "dag_criada": r[2]} for r in cur.fetchall()]
        cur.close(); conn.close()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro DB: {e}")
    try:
        airflow_dags = await _fetch_airflow_dags()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Erro Airflow: {e}")
    actions = _build_sync_actions(pipelines, airflow_dags)
    summary = {
        "would_deactivate": sum(1 for a in actions if a["action"] == "deactivate"),
        "would_sync":       sum(1 for a in actions if a["action"] == "sync"),
        "already_ok":       sum(1 for a in actions if a["action"] == "ok"),
        "skipped":          sum(1 for a in actions if a["action"] == "skip"),
        "total_pipelines":  len(pipelines),
        "airflow_dags_found": len(airflow_dags),
    }
    return {"dry_run": True, "summary": summary, "actions": actions}


@router.post("/sync/pipeline-status", tags=["sync"])
async def sync_pipeline_status(_auth: dict = Depends(require_perm(PERM_EXECUTAR))):
    """Sincroniza status dos pipelines com Airflow."""
    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute("SELECT pipeline_name, active, dag_criada FROM dbo.etl_pipeline ORDER BY pipeline_name")
        pipelines = [{"pipeline_name": r[0], "active": r[1], "dag_criada": r[2]} for r in cur.fetchall()]
        cur.close(); conn.close()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro DB: {e}")
    try:
        airflow_dags = await _fetch_airflow_dags()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Erro Airflow: {e}")
    actions = _build_sync_actions(pipelines, airflow_dags)
    result  = _apply_actions(actions)
    log.info("Sync concluído: %s", result)
    return {
        "dry_run": False,
        "summary": {**result, "total_pipelines": len(pipelines), "airflow_dags_found": len(airflow_dags)},
        "actions": actions,
    }
