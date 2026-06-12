"""api/routers/airflow.py — GET /airflow/connections/ssh."""
from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, HTTPException

from deps import (
    AIRFLOW_URL, AIRFLOW_USER, AIRFLOW_PASSWORD,
)

log = logging.getLogger("orquestra-api")

router = APIRouter()


def get_airflow_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=AIRFLOW_URL,
        auth=(AIRFLOW_USER, AIRFLOW_PASSWORD),
        timeout=15,
    )


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
