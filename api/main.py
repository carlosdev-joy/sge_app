"""
ORQUESTRA API — v0.1.0
Primeira versão FastAPI: sincronização de status de pipelines.

Endpoints:
  GET  /health                    — health check
  GET  /pipelines                 — lista pipelines do banco
  POST /sync/pipeline-status      — sincroniza status com Airflow (DAG existe? pausada?)
  GET  /sync/pipeline-status/dry-run — simula sem alterar banco
"""
from __future__ import annotations

import os
import logging
from contextlib import asynccontextmanager
from typing import Any

import httpx
import pyodbc
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("orquestra-api")

# ── Configuração via variáveis de ambiente ────────────────────────────────────
AIRFLOW_URL      = os.getenv("AIRFLOW_URL",      "http://airflow-webserver:8080")
AIRFLOW_USER     = os.getenv("AIRFLOW_USER",     "airflow")
AIRFLOW_PASSWORD = os.getenv("AIRFLOW_PASSWORD", "airflow")
DAGS_FOLDER      = os.getenv("DAGS_FOLDER",      "/opt/airflow/dags")

MSSQL_CONN_ID = os.getenv("MSSQL_CONN_ID", "SQL14_DMDB41")

# cache em memória para não buscar a cada request
_db_conn_cache: dict = {}


async def _fetch_airflow_connection(conn_id: str) -> dict:
    """Busca os dados de uma connection do Airflow via REST."""
    async with get_airflow_client() as client:
        r = await client.get(f"/api/v1/connections/{conn_id}")
        if r.status_code == 404:
            raise HTTPException(status_code=500, detail=f"Connection '{conn_id}' não encontrada no Airflow")
        if r.status_code == 401:
            raise HTTPException(status_code=401, detail="Credenciais Airflow inválidas")
        r.raise_for_status()
        return r.json()


async def get_db_conn_async():
    """Retorna conexão pyodbc usando credenciais da connection do Airflow."""
    global _db_conn_cache
    if not _db_conn_cache:
        conn_data = await _fetch_airflow_connection(MSSQL_CONN_ID)
        _db_conn_cache = {
            "server":   conn_data.get("host", ""),
            "database": conn_data.get("schema", ""),
            "user":     conn_data.get("login", ""),
            "password": conn_data.get("password", ""),
        }
        log.info("DB connection carregada do Airflow: server=%s db=%s",
                 _db_conn_cache["server"], _db_conn_cache["database"])

    conn_str = (
        f"DRIVER={{ODBC Driver 18 for SQL Server}};"
        f"SERVER={_db_conn_cache['server']};"
        f"DATABASE={_db_conn_cache['database']};"
        f"UID={_db_conn_cache['user']};"
        f"PWD={_db_conn_cache['password']};"
        "TrustServerCertificate=yes;"
    )
    return pyodbc.connect(conn_str, timeout=10)


def get_db_conn():
    """Conexão síncrona usando cache já carregado. Requer get_db_conn_async chamado antes."""
    if not _db_conn_cache:
        raise RuntimeError("Cache de conexão DB não inicializado — use get_db_conn_async()")
    conn_str = (
        f"DRIVER={{ODBC Driver 18 for SQL Server}};"
        f"SERVER={_db_conn_cache['server']};"
        f"DATABASE={_db_conn_cache['database']};"
        f"UID={_db_conn_cache['user']};"
        f"PWD={_db_conn_cache['password']};"
        "TrustServerCertificate=yes;"
    )
    return pyodbc.connect(conn_str, timeout=10)


def get_airflow_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=AIRFLOW_URL,
        auth=(AIRFLOW_USER, AIRFLOW_PASSWORD),
        timeout=15,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("ORQUESTRA API iniciando — Airflow: %s | DB: %s/%s", AIRFLOW_URL, MSSQL_SERVER, MSSQL_DATABASE)
    yield
    log.info("ORQUESTRA API encerrando.")


app = FastAPI(
    title="ORQUESTRA API",
    version="0.1.0",
    description="API de integração ORQUESTRA — sincronização de pipelines com Airflow",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health", tags=["infra"])
def health():
    return {"status": "ok", "version": "0.1.0"}


# ── Pipelines ─────────────────────────────────────────────────────────────────

@app.get("/pipelines", tags=["pipelines"])
async def list_pipelines(project: str | None = None, active_only: bool = False):
    """Lista pipelines cadastrados no banco."""
    try:
        conn = await get_db_conn_async()
        cur  = conn.cursor()
        sql  = """
            SELECT pipeline_name, project_name, domain, active, dag_criada,
                   ambiente, criticidade, scheduled_time
            FROM dbo.etl_pipeline
            WHERE 1=1
        """
        params = []
        if project:
            sql += " AND project_name = ?"
            params.append(project)
        if active_only:
            sql += " AND active = 1"
        sql += " ORDER BY project_name, pipeline_name"
        cur.execute(sql, params)
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, row)) for row in cur.fetchall()]
        cur.close(); conn.close()
        return {"total": len(rows), "pipelines": rows}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Sync pipeline status ──────────────────────────────────────────────────────

async def _fetch_airflow_dags() -> dict[str, dict]:
    """Busca todos os DAGs do Airflow via REST. Retorna dict keyed by dag_id."""
    async with get_airflow_client() as client:
        all_dags: dict[str, dict] = {}
        offset = 0
        limit  = 100
        while True:
            r = await client.get("/api/v1/dags", params={"limit": limit, "offset": offset})
            if r.status_code == 401:
                raise HTTPException(status_code=401, detail="Credenciais Airflow inválidas")
            r.raise_for_status()
            data  = r.json()
            dags  = data.get("dags", [])
            for d in dags:
                all_dags[d["dag_id"]] = d
            if offset + limit >= data.get("total_entries", 0):
                break
            offset += limit
        return all_dags


def _dag_file_exists(pipeline_name: str) -> bool:
    """Verifica se o arquivo .py da DAG existe no DAGS_FOLDER."""
    path = os.path.join(DAGS_FOLDER, f"{pipeline_name}.py")
    return os.path.isfile(path)


def _build_sync_actions(
    pipelines: list[dict],
    airflow_dags: dict[str, dict],
) -> list[dict[str, Any]]:
    """
    Determina ações de sincronização para cada pipeline.

    Regras:
      1. dag_criada=0 → ignora (pipeline ainda não gerou DAG)
      2. Arquivo .py não existe em DAGS_FOLDER → marca inactive + dag_criada=0
      3. DAG não registrada no Airflow → marca inactive + dag_criada=0
      4. DAG existe e is_paused=True  → marca active=0
      5. DAG existe e is_paused=False → marca active=1
    """
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
            actions.append({
                "pipeline":    name,
                "action":      "deactivate",
                "reason":      "arquivo .py não encontrado em dags/",
                "set_active":  0,
                "set_dag_criada": 0,
            })
            continue

        if not airflow_ok:
            actions.append({
                "pipeline":    name,
                "action":      "deactivate",
                "reason":      "DAG não encontrada no Airflow (arquivo existe mas não foi carregado)",
                "set_active":  0,
                "set_dag_criada": 0,
            })
            continue

        dag_info   = airflow_dags[name]
        is_paused  = bool(dag_info.get("is_paused", False))
        new_active = 0 if is_paused else 1

        if new_active == active_now:
            actions.append({"pipeline": name, "action": "ok", "reason": "status já sincronizado", "active": active_now})
        else:
            actions.append({
                "pipeline":   name,
                "action":     "sync",
                "reason":     f"Airflow is_paused={is_paused} → active={new_active}",
                "set_active": new_active,
            })

    return actions


def _apply_actions(actions: list[dict]) -> dict:
    """Aplica as ações no banco SQL Server."""
    deactivated = synced = skipped = ok_count = 0
    conn = get_db_conn()
    cur  = conn.cursor()
    try:
        for a in actions:
            if a["action"] == "skip" or a["action"] == "ok":
                if a["action"] == "ok":
                    ok_count += 1
                else:
                    skipped += 1
                continue

            if a["action"] == "deactivate":
                cur.execute(
                    "UPDATE dbo.etl_pipeline SET active=0, dag_criada=0, updated_at=GETDATE() WHERE pipeline_name=?",
                    (a["pipeline"],)
                )
                deactivated += 1

            elif a["action"] == "sync":
                cur.execute(
                    "UPDATE dbo.etl_pipeline SET active=?, updated_at=GETDATE() WHERE pipeline_name=?",
                    (a["set_active"], a["pipeline"])
                )
                synced += 1

        conn.commit()
    finally:
        cur.close()
        conn.close()

    return {
        "deactivated": deactivated,
        "synced":      synced,
        "already_ok":  ok_count,
        "skipped":     skipped,
    }


@app.get("/sync/pipeline-status/dry-run", tags=["sync"])
async def sync_dry_run():
    """
    Simula a sincronização sem alterar o banco.
    Retorna quais pipelines seriam afetados e por quê.
    """
    try:
        conn = await get_db_conn_async()
        cur  = conn.cursor()
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


@app.post("/sync/pipeline-status", tags=["sync"])
async def sync_pipeline_status():
    """
    Sincroniza o status dos pipelines com o Airflow:
    - Se o arquivo .py não existe em dags/ → pipeline inativo + dag_criada=0
    - Se a DAG está pausada no Airflow     → pipeline inativo
    - Se a DAG está ativa no Airflow       → pipeline ativo
    - Pipelines com dag_criada=0 são ignorados
    """
    try:
        conn = await get_db_conn_async()
        cur  = conn.cursor()
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
