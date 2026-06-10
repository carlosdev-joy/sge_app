"""
ORQUESTRA API — v0.2.0

Endpoints:
  GET  /health                       — health check
  GET  /pipelines                    — lista pipelines do banco
  GET  /dashboard                    — KPIs + status + falhas + running (substitui etl_dashboard_query)
  POST /sync/pipeline-status         — sincroniza status com Airflow
  GET  /sync/pipeline-status/dry-run — simula sem alterar banco
"""
from __future__ import annotations

import os
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
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

MSSQL_CONN_STR = os.getenv("MSSQL_CONN_STR", "")


def get_db_conn():
    if not MSSQL_CONN_STR:
        raise HTTPException(status_code=500, detail="MSSQL_CONN_STR não configurada")
    return pyodbc.connect(MSSQL_CONN_STR, timeout=10)


async def get_db_conn_async():
    return get_db_conn()


def get_airflow_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=AIRFLOW_URL,
        auth=(AIRFLOW_USER, AIRFLOW_PASSWORD),
        timeout=15,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("ORQUESTRA API iniciando — Airflow: %s", AIRFLOW_URL)
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


# ── Dashboard ────────────────────────────────────────────────────────────────

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
            ELSE 'DESCONHECIDO'
        END
    """


@app.get("/dashboard", tags=["dashboard"])
async def get_dashboard(filter_project: str | None = None, date_ref: str | None = None):
    """
    Retorna KPIs, status de pipelines, últimas falhas, executando agora e alertas de performance.
    Substitui a DAG etl_dashboard_query.
    """
    fp = (filter_project or "").strip()
    dr = (date_ref or "").strip()

    if not dr:
        now_sp = datetime.now(LOCAL_TZ)
        dr = now_sp.strftime("%Y-%m-%d")

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

        # KPIs
        kpi_sql = f"""
            WITH execs AS (
                SELECT execution_id, project, pipeline,
                    COALESCE(SUM(duration_seconds), 0) AS duracao_total_segundos,
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
        """
        kpi_params = [dt_ini, dt_fim] + ([fp] if fp else [])
        cur.execute(kpi_sql, kpi_params)
        row = cur.fetchone()
        total_exec    = int(row[0] or 0) if row else 0
        total_sucesso = int(row[1] or 0) if row else 0
        total_falha   = int(row[2] or 0) if row else 0
        total_warning = int(row[3] or 0) if row else 0
        duracao_media = int(row[4] or 0) if row else 0
        taxa = round(total_sucesso * 100.0 / total_exec, 1) if total_exec else 0.0

        # Por projeto
        pp_sql = f"""
            WITH execs AS (
                SELECT execution_id, project, pipeline,
                    {status_expr} AS status_geral
                FROM dbo.etl_job_execution e
                JOIN dbo.etl_pipeline p ON p.pipeline_name = e.pipeline
                WHERE e.start_time >= ? AND e.start_time < ?
                  AND COALESCE(p.ambiente, 'PROD') = 'PROD'
                GROUP BY e.execution_id, e.project, e.pipeline
            )
            SELECT project,
                COUNT(*),
                SUM(CASE WHEN status_geral='FAILED'  THEN 1 ELSE 0 END),
                SUM(CASE WHEN status_geral='WARNING' THEN 1 ELSE 0 END)
            FROM execs
            {("WHERE project = ?" if fp else "")}
            GROUP BY project ORDER BY project
        """
        pp_params = [dt_ini, dt_fim] + ([fp] if fp else [])
        cur.execute(pp_sql, pp_params)
        por_projeto = [
            {"project": r[0], "execucoes": int(r[1] or 0), "falhas": int(r[2] or 0), "warnings": int(r[3] or 0)}
            for r in cur.fetchall()
        ]

        # Status por pipeline (última execução)
        ps_sql = f"""
            WITH execs AS (
                SELECT execution_id, project, pipeline,
                    MIN(start_time) AS inicio,
                    COALESCE(SUM(duration_seconds), 0) AS duracao_segundos,
                    COUNT(*) AS total_jobs,
                    {status_expr} AS ultimo_status
                FROM dbo.etl_job_execution
                WHERE 1=1 {where_proj}
                GROUP BY execution_id, project, pipeline
            ),
            ranked AS (
                SELECT *, ROW_NUMBER() OVER (PARTITION BY pipeline ORDER BY inicio DESC) AS rn
                FROM execs
            )
            SELECT TOP 20
                r.pipeline, r.project, r.ultimo_status, r.inicio, r.duracao_segundos,
                r.total_jobs, r.execution_id, COALESCE(p.criticidade, '') AS criticidade
            FROM ranked r
            LEFT JOIN dbo.etl_pipeline p ON p.pipeline_name = r.pipeline
            WHERE rn = 1 AND COALESCE(p.ambiente, 'PROD') = 'PROD'
            ORDER BY
                CASE COALESCE(p.criticidade,'') WHEN 'ALTA' THEN 1 WHEN 'MEDIA' THEN 2 WHEN 'BAIXA' THEN 3 ELSE 4 END,
                CASE r.ultimo_status WHEN 'FAILED' THEN 1 WHEN 'WARNING' THEN 2 WHEN 'RUNNING' THEN 3 ELSE 4 END,
                r.inicio DESC
        """
        cur.execute(ps_sql, [fp] if fp else [])
        pipeline_status = [
            {
                "pipeline": r[0], "project": r[1], "ultimo_status": r[2],
                "ultimo_inicio": _fmt_dt(r[3]), "duracao_segundos": int(r[4] or 0),
                "total_jobs": int(r[5] or 0), "execution_id": r[6], "criticidade": r[7] or "",
            }
            for r in cur.fetchall()
        ]

        # Últimas falhas
        ff_sql = f"""
            SELECT TOP 5
                e.pipeline, e.project, e.job_name, e.status,
                e.start_time, e.execution_id, e.log_file
            FROM dbo.etl_job_execution e
            JOIN dbo.etl_pipeline p ON p.pipeline_name = e.pipeline
            WHERE e.status = 'FAILED'
              AND COALESCE(p.ambiente, 'PROD') = 'PROD'
              {where_proj_alias}
            ORDER BY e.start_time DESC
        """
        cur.execute(ff_sql, [fp] if fp else [])
        ultimas_falhas = [
            {
                "pipeline": r[0], "project": r[1], "job_name": r[2], "status": r[3],
                "inicio": _fmt_dt(r[4]), "execution_id": r[5], "log_file": r[6],
            }
            for r in cur.fetchall()
        ]

        # Executando agora
        rn_sql = f"""
            WITH runs AS (
                SELECT execution_id, project, pipeline, MIN(start_time) AS inicio,
                    COUNT(*) AS total_jobs,
                    SUM(CASE WHEN status='RUNNING' THEN 1 ELSE 0 END) AS jobs_running,
                    SUM(CASE WHEN status='SUCCESS' THEN 1 ELSE 0 END) AS jobs_ok
                FROM dbo.etl_job_execution
                WHERE status = 'RUNNING' {where_proj}
                GROUP BY execution_id, project, pipeline
            )
            SELECT TOP 10 execution_id, project, pipeline, inicio,
                total_jobs, jobs_running, jobs_ok,
                DATEDIFF(SECOND, inicio, GETDATE()) AS elapsed_seconds
            FROM runs ORDER BY inicio DESC
        """
        cur.execute(rn_sql, [fp] if fp else [])
        executando_agora = [
            {
                "execution_id": r[0], "project": r[1], "pipeline": r[2],
                "inicio": _fmt_dt(r[3]), "total_jobs": int(r[4] or 0),
                "jobs_running": int(r[5] or 0), "jobs_ok": int(r[6] or 0),
                "elapsed_seconds": int(r[7] or 0),
            }
            for r in cur.fetchall()
        ]

        # Alertas de performance >= 3h
        al_sql = f"""
            WITH running_exec AS (
                SELECT execution_id, project, pipeline, MIN(start_time) AS inicio,
                    DATEDIFF(SECOND, MIN(start_time), GETDATE()) AS elapsed_seconds,
                    DATEDIFF(HOUR,   MIN(start_time), GETDATE()) AS elapsed_hours
                FROM dbo.etl_job_execution
                WHERE status = 'RUNNING' {where_proj}
                GROUP BY execution_id, project, pipeline
            )
            SELECT TOP 10 execution_id, project, pipeline, inicio, elapsed_seconds,
                CASE WHEN elapsed_hours >= 12 THEN 12 WHEN elapsed_hours >= 6 THEN 6 ELSE 3 END
            FROM running_exec WHERE elapsed_seconds >= 10800
            ORDER BY elapsed_seconds DESC
        """
        cur.execute(al_sql, [fp] if fp else [])
        alertas_perf = [
            {
                "execution_id": r[0], "project": r[1], "pipeline": r[2],
                "inicio": _fmt_dt(r[3]), "elapsed_seconds": int(r[4] or 0),
                "alerta_horas": int(r[5] or 3),
            }
            for r in cur.fetchall()
        ]

        cur.close()
        conn.close()

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro DB: {e}")

    return {
        "date_ref": dr,
        "kpis": {
            "total_execucoes": total_exec,
            "total_sucesso": total_sucesso,
            "total_falha": total_falha,
            "total_warning": total_warning,
            "taxa_sucesso_pct": taxa,
            "duracao_media_segundos": duracao_media,
            "por_projeto": por_projeto,
            "filter_project": fp,
        },
        "pipeline_status": pipeline_status,
        "ultimas_falhas": ultimas_falhas,
        "executando_agora": executando_agora,
        "alertas_perf": alertas_perf,
    }


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
    """Verifica se o arquivo .py da DAG existe em dags/generated/**/pipeline_name.py."""
    generated_root = os.path.join(DAGS_FOLDER, "generated")
    if not os.path.isdir(generated_root):
        return False
    target = f"{pipeline_name}.py"
    for dirpath, _, filenames in os.walk(generated_root):
        if target in filenames:
            return True
    return False


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
