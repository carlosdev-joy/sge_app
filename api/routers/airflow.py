"""api/routers/airflow.py — Proxy de endpoints do Airflow."""
from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, Body, HTTPException, Path
from fastapi.responses import PlainTextResponse

from deps import (
    AIRFLOW_URL, AIRFLOW_USER, AIRFLOW_PASSWORD,
)

log = logging.getLogger("orquestra-api")

router = APIRouter()


def get_airflow_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=AIRFLOW_URL,
        auth=(AIRFLOW_USER, AIRFLOW_PASSWORD),
        timeout=30,
    )


@router.get("/airflow/dags/{dag_id}/dagRuns/{dag_run_id}/taskInstances")
async def list_task_instances(dag_id: str, dag_run_id: str):
    """Lista task instances de um dag_run — proxy para Airflow REST API."""
    try:
        async with get_airflow_client() as client:
            r = await client.get(f"/api/v1/dags/{dag_id}/dagRuns/{dag_run_id}/taskInstances")
            if not r.is_success:
                raise HTTPException(status_code=r.status_code, detail=r.text)
            return r.json()
    except HTTPException:
        raise
    except Exception as e:
        log.warning("Erro ao listar task instances %s/%s: %s", dag_id, dag_run_id, e)
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/airflow/dags/{dag_id}/dagRuns/{dag_run_id}/taskInstances/{task_id}/logs/{try_number}")
async def get_task_log(dag_id: str, dag_run_id: str, task_id: str, try_number: int = 1):
    """Retorna log de uma task como texto — proxy para Airflow REST API."""
    try:
        async with get_airflow_client() as client:
            r = await client.get(
                f"/api/v1/dags/{dag_id}/dagRuns/{dag_run_id}/taskInstances/{task_id}/logs/{try_number}",
                headers={"Accept": "text/plain"},
            )
            if not r.is_success:
                raise HTTPException(status_code=r.status_code, detail=r.text)
            return PlainTextResponse(content=r.text)
    except HTTPException:
        raise
    except Exception as e:
        log.warning("Erro ao buscar log %s/%s/%s: %s", dag_id, dag_run_id, task_id, e)
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/airflow/dags/{dag_id}/dagRuns")
async def list_dag_runs(dag_id: str, limit: int = 50, order_by: str = "-execution_date"):
    """Lista dag_runs de um DAG — proxy para Airflow REST API."""
    try:
        async with get_airflow_client() as client:
            r = await client.get(f"/api/v1/dags/{dag_id}/dagRuns", params={"limit": limit, "order_by": order_by})
            if not r.is_success:
                raise HTTPException(status_code=r.status_code, detail=r.text)
            return r.json()
    except HTTPException:
        raise
    except Exception as e:
        log.warning("Erro ao listar dagRuns %s: %s", dag_id, e)
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/airflow/dags/{dag_id}/dagRuns")
async def trigger_dag_run(dag_id: str, body: dict = Body(default={})):
    """Dispara uma execução manual de um DAG — proxy para Airflow REST API."""
    try:
        async with get_airflow_client() as client:
            r = await client.post(
                f"/api/v1/dags/{dag_id}/dagRuns",
                json=body,
                headers={"Content-Type": "application/json"},
            )
            if not r.is_success:
                raise HTTPException(status_code=r.status_code, detail=r.text)
            return r.json()
    except HTTPException:
        raise
    except Exception as e:
        log.warning("Erro ao disparar DAG %s: %s", dag_id, e)
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/airflow/connections/ssh")
async def list_ssh_connections():
    """Lista conexões SSH cadastradas no Airflow (conn_type=ssh)."""
    try:
        async with get_airflow_client() as client:
            r = await client.get("/api/v1/connections?limit=100")
            if not r.is_success:
                return {"connections": []}
            data = r.json()
            conns = [
                {"conn_id": c["connection_id"], "host": c.get("host",""), "description": c.get("description","")}
                for c in data.get("connections", [])
                if c.get("conn_type") == "ssh"
            ]
            return {"connections": conns}
    except Exception as e:
        log.warning("Erro ao listar conexões SSH: %s", e)
        return {"connections": []}
