"""api/routers/airflow.py — Proxy de endpoints do Airflow."""
from __future__ import annotations

import logging
import re

import httpx
from fastapi import APIRouter, Body, Depends, HTTPException, Path
from fastapi.responses import PlainTextResponse

from db import get_db_conn
from deps import (
    AIRFLOW_URL, AIRFLOW_USER, AIRFLOW_PASSWORD,
    get_current_user, require_perm, PERM_EXECUTAR,
)

_DAG_ID_RE = re.compile(r'^[a-zA-Z0-9_.\-]+$')
_ALLOWED_ORDER = {
    "execution_date", "-execution_date", "start_date", "-start_date",
    "end_date", "-end_date", "logical_date", "-logical_date",
    "dag_run_id", "-dag_run_id", "state", "-state",
}

log = logging.getLogger("orquestra-api")

router = APIRouter()


def get_airflow_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=AIRFLOW_URL,
        auth=(AIRFLOW_USER, AIRFLOW_PASSWORD),
        timeout=30,
    )


@router.get("/airflow/dags/{dag_id}/dagRuns/{dag_run_id}/taskInstances")
async def list_task_instances(dag_id: str, dag_run_id: str,
                              _auth: dict = Depends(get_current_user)):
    """Lista task instances de um dag_run — proxy para Airflow REST API."""
    if not _DAG_ID_RE.match(dag_id):
        raise HTTPException(status_code=422, detail="dag_id inválido")
    try:
        async with get_airflow_client() as client:
            r = await client.get(f"/api/v1/dags/{dag_id}/dagRuns/{dag_run_id}/taskInstances")
            if not r.is_success:
                raise HTTPException(status_code=r.status_code, detail="Erro ao consultar o Airflow")
            return r.json()
    except HTTPException:
        raise
    except Exception as e:
        log.warning("Erro ao listar task instances %s/%s: %s", dag_id, dag_run_id, e)
        raise HTTPException(status_code=502, detail="Erro ao consultar o Airflow")


@router.get("/airflow/dags/{dag_id}/dagRuns/{dag_run_id}/taskInstances/{task_id}/logs/{try_number}")
async def get_task_log(dag_id: str, dag_run_id: str, task_id: str, try_number: int = 1,
                       _auth: dict = Depends(get_current_user)):
    """Retorna log de uma task como texto — proxy para Airflow REST API."""
    if not _DAG_ID_RE.match(dag_id):
        raise HTTPException(status_code=422, detail="dag_id inválido")
    try:
        async with get_airflow_client() as client:
            r = await client.get(
                f"/api/v1/dags/{dag_id}/dagRuns/{dag_run_id}/taskInstances/{task_id}/logs/{try_number}",
                headers={"Accept": "text/plain"},
            )
            if not r.is_success:
                raise HTTPException(status_code=r.status_code, detail="Erro ao consultar o Airflow")
            return PlainTextResponse(content=r.text)
    except HTTPException:
        raise
    except Exception as e:
        log.warning("Erro ao buscar log %s/%s/%s: %s", dag_id, dag_run_id, task_id, e)
        raise HTTPException(status_code=502, detail="Erro ao consultar o Airflow")


@router.get("/airflow/dags/{dag_id}/dagRuns")
async def list_dag_runs(dag_id: str, limit: int = 50, order_by: str = "-execution_date",
                        _auth: dict = Depends(get_current_user)):
    """Lista dag_runs de um DAG — proxy para Airflow REST API."""
    if not _DAG_ID_RE.match(dag_id):
        raise HTTPException(status_code=422, detail="dag_id inválido")
    if order_by not in _ALLOWED_ORDER:
        order_by = "-execution_date"
    limit = min(200, max(1, limit))
    try:
        async with get_airflow_client() as client:
            r = await client.get(f"/api/v1/dags/{dag_id}/dagRuns", params={"limit": limit, "order_by": order_by})
            if not r.is_success:
                raise HTTPException(status_code=r.status_code, detail="Erro ao consultar o Airflow")
            return r.json()
    except HTTPException:
        raise
    except Exception as e:
        log.warning("Erro ao listar dagRuns %s: %s", dag_id, e)
        raise HTTPException(status_code=502, detail="Erro ao consultar o Airflow")


@router.post("/airflow/dags/{dag_id}/dagRuns")
async def trigger_dag_run(dag_id: str, body: dict = Body(default={}), _auth: dict = Depends(require_perm(PERM_EXECUTAR))):
    """Dispara uma execução manual de um DAG — proxy para Airflow REST API."""
    if not _DAG_ID_RE.match(dag_id):
        raise HTTPException(status_code=400, detail="dag_id inválido")
    safe_body = {k: body[k] for k in ('dag_run_id', 'conf', 'logical_date') if k in body}
    try:
        async with get_airflow_client() as client:
            r = await client.post(
                f"/api/v1/dags/{dag_id}/dagRuns",
                json=safe_body,
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


@router.patch("/airflow/dags/{dag_id}")
async def patch_dag(dag_id: str, body: dict = Body(default={}), _auth: dict = Depends(require_perm(PERM_EXECUTAR))):
    """Ativa ou pausa um DAG (is_paused) — proxy para Airflow REST API."""
    if not _DAG_ID_RE.match(dag_id):
        raise HTTPException(status_code=400, detail="dag_id inválido")
    safe_body = {k: body[k] for k in ('is_paused',) if k in body}
    try:
        async with get_airflow_client() as client:
            r = await client.patch(
                f"/api/v1/dags/{dag_id}",
                json=safe_body,
                headers={"Content-Type": "application/json"},
            )
            if not r.is_success:
                raise HTTPException(status_code=r.status_code, detail=r.text)
            return r.json()
    except HTTPException:
        raise
    except Exception as e:
        log.warning("Erro ao atualizar DAG %s: %s", dag_id, e)
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/airflow/connections/ssh")
async def list_ssh_connections(_auth: dict = Depends(get_current_user)):
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


@router.get("/airflow/connections/mssql")
async def list_mssql_connections(_auth: dict = Depends(get_current_user)):
    """Lista conexões MSSQL — UNIÃO de dbo.etl_conexao (fonte da verdade,
    migration 054) com as cadastradas no Airflow (legadas). Alimenta os
    selects do nó SQL/decisão (Jobs e FluxoEditor). Cada fonte degrada para
    vazio de forma independente; conn_id repetido fica com o Orquestra."""
    conns: dict[str, dict] = {}
    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute("SELECT conn_id, host, descricao FROM dbo.etl_conexao "
                    "WHERE conn_type = 'mssql'")
        for row in cur.fetchall():
            cid = (row[0] or "").strip()
            if cid:
                conns[cid] = {"conn_id": cid, "host": (row[1] or "").strip(),
                              "schema": "", "description": row[2] or ""}
        cur.close(); conn.close()
    except Exception as e:
        log.warning("Leitura de etl_conexao falhou (%s) — listando só as "
                    "connections do Airflow", e)
    try:
        async with get_airflow_client() as client:
            r = await client.get("/api/v1/connections?limit=100")
            if r.is_success:
                for c in r.json().get("connections", []):
                    cid = c.get("connection_id")
                    if c.get("conn_type") == "mssql" and cid and cid not in conns:
                        conns[cid] = {"conn_id": cid, "host": c.get("host", ""),
                                      "schema": c.get("schema", ""),
                                      "description": c.get("description", "")}
    except Exception as e:
        log.warning("Erro ao listar conexões MSSQL do Airflow: %s", e)
    return {"connections": sorted(conns.values(),
                                  key=lambda c: c["conn_id"].lower())}
