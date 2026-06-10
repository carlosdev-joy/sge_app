"""
ORQUESTRA API — v0.3.0

Endpoints:
  GET  /health                       — health check
  GET  /pipelines                    — lista pipelines (paginado, filtros)
  GET  /dashboard                    — KPIs + status + falhas + running
  GET  /config                       — parâmetros de configuração da app
  GET  /versao                       — histórico de versões
  GET  /jobs                         — lista jobs de pipeline
  GET  /execucoes                    — execuções paginadas (agregado ou detalhe)
  GET  /lineage                      — lineage de um pipeline
  POST /catalogo                     — catálogo de dados (multi-modo)
  POST /sync/pipeline-status         — sincroniza status com Airflow
  GET  /sync/pipeline-status/dry-run — simula sem alterar banco
"""
from __future__ import annotations

import json
import os
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

import httpx
import pyodbc
from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("orquestra-api")

# ── Configuração via variáveis de ambiente ────────────────────────────────────
AIRFLOW_URL      = os.getenv("AIRFLOW_URL",      "http://airflow-webserver:8080")
AIRFLOW_USER     = os.getenv("AIRFLOW_USER",     "airflow")
AIRFLOW_PASSWORD = os.getenv("AIRFLOW_PASSWORD", "airflow")
DAGS_FOLDER      = os.getenv("DAGS_FOLDER",      "/opt/airflow/dags")
MSSQL_CONN_STR   = os.getenv("MSSQL_CONN_STR",  "")

MAX_LIMIT = 200


def get_db_conn():
    if not MSSQL_CONN_STR:
        raise HTTPException(status_code=500, detail="MSSQL_CONN_STR não configurada")
    return pyodbc.connect(MSSQL_CONN_STR, timeout=10)


def get_airflow_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=AIRFLOW_URL,
        auth=(AIRFLOW_USER, AIRFLOW_PASSWORD),
        timeout=15,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("ORQUESTRA API v0.3.0 iniciando — Airflow: %s", AIRFLOW_URL)
    yield
    log.info("ORQUESTRA API encerrando.")


app = FastAPI(
    title="ORQUESTRA API",
    version="0.3.0",
    description="API de integração ORQUESTRA — sincronização de pipelines com Airflow",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

LOCAL_TZ = timezone(timedelta(hours=-3))  # America/Sao_Paulo


def _fmt_dt(v):
    if v is None:
        return None
    if hasattr(v, "strftime"):
        return v.strftime("%Y-%m-%d %H:%M:%S")
    return str(v)


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health", tags=["infra"])
def health():
    return {"status": "ok", "version": "0.3.0"}


# ── Config ────────────────────────────────────────────────────────────────────

DEFAULTS_CONFIG = {
    "dashboard_refresh_interval_sec": 60,
    "failure_badge_refresh_sec":      300,
    "failure_badge_hours_lookback":   24,
    "app_version":                    "2.1.0",
    "app_release_name":               "Sprint 1 — Junho/2026",
    "pipeline_query_limit":           20,
    "jobs_query_limit":               50,
    "logs_query_limit":               30,
}
INT_CONFIG_KEYS = {
    "dashboard_refresh_interval_sec",
    "failure_badge_refresh_sec",
    "failure_badge_hours_lookback",
    "pipeline_query_limit",
    "jobs_query_limit",
    "logs_query_limit",
}


@app.get("/config", tags=["config"])
def get_config():
    """Retorna parâmetros de configuração da aplicação. Substitui etl_app_config_query."""
    result = dict(DEFAULTS_CONFIG)
    try:
        conn = get_db_conn()
        cur  = conn.cursor()
        cur.execute("SELECT config_key, config_value FROM dbo.etl_app_config")
        for key, value in cur.fetchall():
            if key in INT_CONFIG_KEYS:
                try:
                    result[key] = int(value)
                except (ValueError, TypeError):
                    pass
            else:
                result[key] = str(value) if value is not None else result.get(key)
        cur.close(); conn.close()
    except HTTPException:
        raise
    except Exception as e:
        log.warning("etl_app_config indisponível, usando defaults: %s", e)
    return result


# ── Versão ────────────────────────────────────────────────────────────────────

@app.get("/versao", tags=["config"])
def get_versao():
    """Retorna histórico de versões do ORQUESTRA. Substitui etl_versao_query."""
    try:
        conn = get_db_conn()
        cur  = conn.cursor()
        cur.execute("""
            SELECT id, versao, titulo, descricao_md, criado_em, criado_por
            FROM dbo.etl_versao_ferramenta
            ORDER BY criado_em DESC
        """)
        cols = ["id", "versao", "titulo", "descricao_md", "criado_em", "criado_por"]
        data = []
        for row in cur.fetchall():
            rec = dict(zip(cols, row))
            rec["criado_em"] = _fmt_dt(rec["criado_em"])
            data.append(rec)
        cur.close(); conn.close()
        return {"total": len(data), "data": data}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Pipelines ─────────────────────────────────────────────────────────────────

@app.get("/pipelines", tags=["pipelines"])
def list_pipelines(
    offset: int = 0,
    limit: int = 20,
    filter_name: Optional[str] = None,
    filter_project: Optional[str] = None,
    filter_active: Optional[int] = None,
):
    """Lista pipelines cadastrados (paginado). Substitui etl_pipeline_query."""
    limit = min(100, max(1, limit))
    offset = max(0, offset)
    fname = (filter_name or "").strip()
    fproj = (filter_project or "").strip()

    where = []
    params_count: list = []
    params_data: list  = []

    if fname:
        where.append("pipeline_name LIKE ?")
        params_count.append(f"%{fname}%")
        params_data.append(f"%{fname}%")
    if fproj:
        where.append("project_name = ?")
        params_count.append(fproj)
        params_data.append(fproj)
    if filter_active is not None:
        where.append("active = ?")
        params_count.append(int(filter_active))
        params_data.append(int(filter_active))

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    try:
        conn = get_db_conn()
        cur  = conn.cursor()

        cur.execute(f"SELECT COUNT(*) FROM dbo.etl_pipeline {where_sql}", params_count)
        total = cur.fetchone()[0]

        data_sql = f"""
            SELECT
                pipeline_name, project_name, domain, tags,
                CONVERT(VARCHAR(8), scheduled_time, 108) AS scheduled_time,
                schedule_type,
                CAST(schedule_hour   AS INT) AS schedule_hour,
                CAST(schedule_minute AS INT) AS schedule_minute,
                CAST(schedule_dow    AS INT) AS schedule_dow,
                CAST(schedule_dom    AS INT) AS schedule_dom,
                CAST(active          AS INT) AS active,
                CAST(dag_criada      AS INT) AS dag_criada,
                CAST(envia_msg_inicio AS INT) AS envia_msg_inicio,
                CAST(envia_msg_fim    AS INT) AS envia_msg_fim,
                CAST(envia_msg_erro   AS INT) AS envia_msg_erro,
                depends_on,
                CONVERT(VARCHAR(10), dag_start_date, 120) AS dag_start_date,
                descricao,
                ISNULL(criticidade, 'Media')   AS criticidade,
                sla_minutos,
                ISNULL(ambiente, 'PROD')       AS ambiente,
                ISNULL(CAST(max_active_runs    AS INT), 1)   AS max_active_runs,
                ISNULL(CAST(retries_count      AS INT), 1)   AS retries_count,
                ISNULL(CAST(retry_delay_seconds AS INT), 300) AS retry_delay_seconds,
                pool_name, last_execution, created_at, updated_at
            FROM dbo.etl_pipeline
            {where_sql}
            ORDER BY project_name, domain, pipeline_name
            OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
        """
        params_data.extend([offset, limit])
        cur.execute(data_sql, params_data)
        cols = [
            "pipeline_name", "project_name", "domain", "tags", "scheduled_time",
            "schedule_type", "schedule_hour", "schedule_minute", "schedule_dow", "schedule_dom",
            "active", "dag_criada", "envia_msg_inicio", "envia_msg_fim", "envia_msg_erro",
            "depends_on", "dag_start_date", "descricao", "criticidade", "sla_minutos",
            "ambiente", "max_active_runs", "retries_count", "retry_delay_seconds",
            "pool_name", "last_execution", "created_at", "updated_at",
        ]
        data = []
        for row in cur.fetchall():
            rec = dict(zip(cols, row))
            rec["last_execution"] = _fmt_dt(rec["last_execution"])
            rec["created_at"]     = _fmt_dt(rec["created_at"])
            rec["updated_at"]     = _fmt_dt(rec["updated_at"])
            data.append(rec)
        cur.close(); conn.close()

        pages = max(1, -(-total // limit))
        return {"total": total, "offset": offset, "limit": limit, "pages": pages, "data": data}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Jobs ──────────────────────────────────────────────────────────────────────

@app.get("/jobs", tags=["jobs"])
def list_jobs(
    offset: int = 0,
    limit: int = 50,
    filter_pipeline: Optional[str] = None,
    filter_job_name: Optional[str] = None,
    filter_job_type: Optional[str] = None,
):
    """Lista jobs de pipeline. Substitui etl_pipeline_job_query."""
    limit  = min(200, max(1, limit))
    offset = max(0, offset)
    fp = (filter_pipeline or "").strip()
    fj = (filter_job_name or "").strip()
    ft = (filter_job_type or "").strip()

    try:
        conn = get_db_conn()
        cur  = conn.cursor()

        # Detecta quais colunas opcionais existem na tabela
        cur.execute("""
            SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME='etl_pipeline_job'
        """)
        existing_cols = {r[0].lower() for r in cur.fetchall()}

        def _sel(col: str, alias: str, cast_int: bool = False) -> str:
            if col.lower() in existing_cols:
                return f"CAST(j.{col} AS INT) AS {alias}" if cast_int else f"j.{col} AS {alias}"
            return f"NULL AS {alias}"

        where: list[str] = []
        params: list = []
        if fp:
            where.append("j.pipeline_name = ?")
            params.append(fp)
        if fj:
            where.append("j.job_name LIKE ?")
            params.append(f"%{fj}%")
        if ft:
            where.append("j.job_type = ?")
            params.append(ft)

        where_sql = ("WHERE " + " AND ".join(where)) if where else ""

        cur.execute(f"SELECT COUNT(*) FROM dbo.etl_pipeline_job j {where_sql}", params)
        total = cur.fetchone()[0]

        data_sql = f"""
            SELECT
                j.pipeline_name,
                p.project_name,
                j.job_name,
                CAST(j.execution_order AS INT) AS execution_order,
                {_sel('job_type',    'job_type')},
                {_sel('job_command', 'job_command')},
                {_sel('active',      'active', cast_int=True)},
                {_sel('created_at',  'created_at')},
                {_sel('updated_at',  'updated_at')}
            FROM dbo.etl_pipeline_job j
            LEFT JOIN dbo.etl_pipeline p ON p.pipeline_name = j.pipeline_name
            {where_sql}
            ORDER BY j.pipeline_name, j.execution_order, j.job_name
            OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
        """
        data_params = list(params) + [offset, limit]
        cur.execute(data_sql, data_params)
        data = [
            {
                "pipeline_name":  r[0], "project_name": r[1], "job_name": r[2],
                "execution_order": r[3], "job_type": r[4], "job_command": r[5],
                "active": r[6], "created_at": _fmt_dt(r[7]), "updated_at": _fmt_dt(r[8]),
            }
            for r in cur.fetchall()
        ]
        cur.close(); conn.close()
        pages = 0 if total == 0 else -(-total // limit)
        return {"total": total, "offset": offset, "limit": limit, "pages": pages,
                "table": "etl_pipeline_job", "data": data}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Execuções ─────────────────────────────────────────────────────────────────

@app.get("/execucoes", tags=["execucoes"])
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

        cur.execute(f"""
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
            ORDER BY MIN(start_time) DESC
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


# ── Lineage ───────────────────────────────────────────────────────────────────

@app.get("/lineage", tags=["lineage"])
def get_lineage(pipeline_name: str):
    """Retorna lineage de um pipeline. Substitui etl_lineage_query."""
    if not pipeline_name.strip():
        raise HTTPException(status_code=400, detail="pipeline_name é obrigatório")

    try:
        conn = get_db_conn()
        cur  = conn.cursor()
        cur.execute("""
            SELECT
                j.execution_order, j.job_name, j.job_type,
                l.direction, l.object_name,
                COALESCE(m.type_label, l.object_type) AS object_type,
                COALESCE(m.type_label, l.stage_type_raw) AS type_label,
                m.type_category, m.role_hint,
                l.stage_name, l.stage_type_raw, l.database_name,
                l.sql_expression, l.file_path, l.dsx_source_file,
                l.extracted_at, l.extraction_method, l.columns_json
            FROM dbo.etl_pipeline_job j
            LEFT JOIN dbo.etl_job_lineage l
                   ON l.pipeline_name = j.pipeline_name AND l.job_name = j.job_name
            LEFT JOIN dbo.etl_stage_type_map m ON m.stage_type = l.stage_type_raw
            WHERE j.pipeline_name = ?
            ORDER BY j.execution_order, j.job_name,
                CASE l.direction
                    WHEN 'origem'        THEN 1 WHEN 'INPUT'  THEN 1
                    WHEN 'transformacao' THEN 2
                    WHEN 'destino'       THEN 3 WHEN 'OUTPUT' THEN 3
                    ELSE 9
                END, l.object_name
        """, [pipeline_name])
        rows = cur.fetchall()
        cur.close(); conn.close()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    jobs_map: dict[str, dict] = {}
    for r in rows:
        (order, job_name, job_type, direction, obj_name, obj_type, type_label,
         type_category, role_hint, stage_name, stage_type_raw, db_name,
         sql_expression, file_path, dsx_source_file, extracted_at,
         extraction_method, columns_json) = r

        if job_name not in jobs_map:
            jobs_map[job_name] = {
                "execution_order": int(order or 0), "job_name": job_name,
                "job_type": job_type, "origens": [], "transformacoes": [], "destinos": [],
            }

        if obj_name is None:
            continue

        try:
            cols = json.loads(columns_json) if columns_json else []
        except Exception:
            cols = []

        item = {
            "object_name": obj_name, "object_type": obj_type,
            "stage_name": stage_name, "stage_type_raw": stage_type_raw,
            "type_label": type_label, "type_category": type_category,
            "role_hint": role_hint, "database_name": db_name,
            "sql_expression": sql_expression, "file_path": file_path,
            "dsx_source_file": dsx_source_file, "extracted_at": _fmt_dt(extracted_at),
            "extraction_method": extraction_method, "columns": cols,
        }

        dir_norm = (direction or "").lower()
        if dir_norm in ("origem", "input"):
            jobs_map[job_name]["origens"].append(item)
        elif dir_norm == "transformacao":
            jobs_map[job_name]["transformacoes"].append(item)
        elif dir_norm in ("destino", "output"):
            jobs_map[job_name]["destinos"].append(item)

    jobs = sorted(jobs_map.values(), key=lambda x: (x["execution_order"], x["job_name"]))
    return {"pipeline_name": pipeline_name, "jobs": jobs}


# ── Catálogo ──────────────────────────────────────────────────────────────────

_ASSETS_CTE = """
    WITH assets AS (
        SELECT
            LTRIM(RTRIM(s.value))          AS asset_name,
            'tabela'                        AS asset_type,
            ISNULL(l.database_name, '')     AS database_name,
            COUNT(DISTINCT l.pipeline_name) AS pipeline_count,
            SUM(CASE WHEN l.direction = 'origem'  THEN 1 ELSE 0 END) AS as_origem,
            SUM(CASE WHEN l.direction = 'destino' THEN 1 ELSE 0 END) AS as_destino
        FROM dbo.etl_job_lineage l
        CROSS APPLY STRING_SPLIT(l.sql_expression, CHAR(10)) s
        WHERE l.sql_expression IS NOT NULL AND l.sql_expression <> ''
          AND (l.file_path IS NULL OR l.file_path = '')
          AND LTRIM(RTRIM(s.value)) <> ''
        GROUP BY LTRIM(RTRIM(s.value)), l.database_name

        UNION ALL

        SELECT
            l.object_name, 'tabela', ISNULL(l.database_name, ''),
            COUNT(DISTINCT l.pipeline_name),
            SUM(CASE WHEN l.direction = 'origem'  THEN 1 ELSE 0 END),
            SUM(CASE WHEN l.direction = 'destino' THEN 1 ELSE 0 END)
        FROM dbo.etl_job_lineage l
        WHERE (l.sql_expression IS NULL OR l.sql_expression = '')
          AND (l.file_path IS NULL OR l.file_path = '')
          AND l.object_name IS NOT NULL AND l.object_name <> ''
        GROUP BY l.object_name, l.database_name

        UNION ALL

        SELECT
            l.file_path, 'arquivo', '',
            COUNT(DISTINCT l.pipeline_name),
            SUM(CASE WHEN l.direction = 'origem'  THEN 1 ELSE 0 END),
            SUM(CASE WHEN l.direction = 'destino' THEN 1 ELSE 0 END)
        FROM dbo.etl_job_lineage l
        WHERE l.file_path IS NOT NULL AND l.file_path <> ''
        GROUP BY l.file_path
    )
"""

_SELECT_COLS = """
    l.pipeline_name,
    p.project_name,
    p.domain,
    CAST(p.active AS INT)           AS active,
    l.job_name,
    CAST(pj.execution_order AS INT) AS execution_order,
    pj.job_type,
    l.direction,
    l.object_name,
    ISNULL(stm.type_label, l.object_type) AS object_type,
    ISNULL(l.database_name, '')            AS database_name,
    ISNULL(l.file_path, '')                AS file_path,
    ISNULL(l.stage_name,   '')             AS stage_name,
    l.columns_json
"""

_JOIN_CLAUSE = """
    FROM dbo.etl_job_lineage l
    JOIN dbo.etl_pipeline     p   ON p.pipeline_name  = l.pipeline_name
    JOIN dbo.etl_pipeline_job pj  ON pj.pipeline_name = l.pipeline_name
                                  AND pj.job_name     = l.job_name
    LEFT JOIN dbo.etl_stage_type_map stm ON stm.type_raw = l.object_type
"""

_COL_NAMES = [
    "pipeline_name", "project_name", "domain", "active",
    "job_name", "execution_order", "job_type", "direction",
    "object_name", "object_type", "database_name", "file_path", "stage_name", "columns_json",
]


def _build_pipeline_list(rows, col_names):
    by_pipeline: dict = {}
    for row in rows:
        rec = dict(zip(col_names, row))
        pname = rec["pipeline_name"]
        if pname not in by_pipeline:
            by_pipeline[pname] = {
                "pipeline_name": pname, "project_name": rec["project_name"],
                "domain": rec["domain"], "active": rec["active"],
                "ocorrencias": 0, "jobs": [],
            }
        try:
            cols = json.loads(rec["columns_json"]) if rec["columns_json"] else []
        except Exception:
            cols = []
        by_pipeline[pname]["ocorrencias"] += 1
        by_pipeline[pname]["jobs"].append({
            "job_name": rec["job_name"], "execution_order": rec["execution_order"],
            "job_type": rec["job_type"], "direction": rec["direction"],
            "object_name": rec["object_name"], "object_type": rec["object_type"],
            "database_name": rec["database_name"], "file_path": rec.get("file_path", ""),
            "stage_name": rec["stage_name"], "columns": cols,
        })
    pipelines = sorted(by_pipeline.values(), key=lambda x: x["pipeline_name"])
    total_occ = sum(p["ocorrencias"] for p in pipelines)
    return pipelines, total_occ


def _cat_search_tabela(cur, object_name, direction, database_name):
    term = f"%{object_name}%"
    where = ["(l.sql_expression LIKE ? OR l.object_name LIKE ?)"]
    params: list = [term, term]
    if direction and direction != "all":
        where.append("l.direction = ?"); params.append(direction)
    if database_name:
        where.append("l.database_name = ?"); params.append(database_name)
    cur.execute(
        f"SELECT {_SELECT_COLS} {_JOIN_CLAUSE} WHERE {' AND '.join(where)} "
        f"ORDER BY l.pipeline_name, pj.execution_order, l.direction, l.object_name",
        params,
    )
    pipelines, total_occ = _build_pipeline_list(cur.fetchall(), _COL_NAMES)
    return {"mode": "search", "search_type": "tabela", "term": object_name, "direction": direction,
            "database_name": database_name, "total_pipelines": len(pipelines),
            "total_ocorrencias": total_occ, "pipelines": pipelines}


def _cat_search_arquivo(cur, file_name, direction):
    where = ["l.file_path LIKE ?", "l.file_path IS NOT NULL", "l.file_path <> ''"]
    params: list = [f"%{file_name}%"]
    if direction and direction != "all":
        where.append("l.direction = ?"); params.append(direction)
    cur.execute(
        f"SELECT {_SELECT_COLS} {_JOIN_CLAUSE} WHERE {' AND '.join(where)} "
        f"ORDER BY l.pipeline_name, pj.execution_order, l.direction, l.file_path",
        params,
    )
    pipelines, total_occ = _build_pipeline_list(cur.fetchall(), _COL_NAMES)
    return {"mode": "search", "search_type": "arquivo", "term": file_name, "direction": direction,
            "total_pipelines": len(pipelines), "total_ocorrencias": total_occ, "pipelines": pipelines}


def _cat_ranking_tabela(cur, top_n):
    cur.execute(f"""
        SELECT TOP {top_n} tbl_name, ISNULL(database_name,'') AS database_name,
            COUNT(DISTINCT pipeline_name) AS pipeline_count,
            COUNT(DISTINCT job_name) AS job_count,
            SUM(CASE WHEN direction='origem'  THEN 1 ELSE 0 END) AS as_origem,
            SUM(CASE WHEN direction='destino' THEN 1 ELSE 0 END) AS as_destino
        FROM (
            SELECT LTRIM(RTRIM(s.value)) AS tbl_name, l.database_name, l.pipeline_name, l.job_name, l.direction
            FROM dbo.etl_job_lineage l CROSS APPLY STRING_SPLIT(l.sql_expression, CHAR(10)) s
            WHERE l.direction IN ('origem','destino') AND (l.file_path IS NULL OR l.file_path='')
              AND l.sql_expression IS NOT NULL AND l.sql_expression<>'' AND LTRIM(RTRIM(s.value))<>''
            UNION ALL
            SELECT l.object_name, l.database_name, l.pipeline_name, l.job_name, l.direction
            FROM dbo.etl_job_lineage l
            WHERE l.direction IN ('origem','destino') AND (l.file_path IS NULL OR l.file_path='')
              AND (l.sql_expression IS NULL OR l.sql_expression='') AND l.object_name IS NOT NULL AND l.object_name<>''
        ) x GROUP BY tbl_name, database_name ORDER BY COUNT(DISTINCT pipeline_name) DESC, tbl_name
    """)
    cols = ["object_name", "database_name", "pipeline_count", "job_count", "as_origem", "as_destino"]
    return {"mode": "ranking", "ranking_type": "tabela", "data": [dict(zip(cols, r)) for r in cur.fetchall()]}


def _cat_ranking_arquivo(cur, top_n):
    cur.execute(f"""
        SELECT TOP {top_n} l.file_path,
            COUNT(DISTINCT l.pipeline_name) AS pipeline_count,
            COUNT(DISTINCT l.job_name) AS job_count,
            SUM(CASE WHEN l.direction='origem'  THEN 1 ELSE 0 END) AS as_origem,
            SUM(CASE WHEN l.direction='destino' THEN 1 ELSE 0 END) AS as_destino
        FROM dbo.etl_job_lineage l
        WHERE l.direction IN ('origem','destino') AND l.file_path IS NOT NULL AND l.file_path<>''
        GROUP BY l.file_path ORDER BY COUNT(DISTINCT l.pipeline_name) DESC, l.file_path
    """)
    cols = ["file_path", "pipeline_count", "job_count", "as_origem", "as_destino"]
    return {"mode": "ranking", "ranking_type": "arquivo", "data": [dict(zip(cols, r)) for r in cur.fetchall()]}


def _cat_overview(cur):
    cur.execute(f"{_ASSETS_CTE} SELECT COUNT(*) FROM (SELECT asset_name,asset_type,database_name FROM assets GROUP BY asset_name,asset_type,database_name) sub")
    total_assets = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM dbo.etl_pipeline")
    total_pipelines = cur.fetchone()[0]
    cur.execute("SELECT COUNT(DISTINCT pipeline_name) FROM dbo.etl_pipeline_owner")
    total_with_owner = cur.fetchone()[0]
    cur.execute("""
        SELECT SUM(CASE WHEN tag='PII' THEN 1 ELSE 0 END),
               SUM(CASE WHEN tag='Confidencial' THEN 1 ELSE 0 END),
               SUM(CASE WHEN tag='Regulado'     THEN 1 ELSE 0 END),
               SUM(CASE WHEN tag='Publico'      THEN 1 ELSE 0 END)
        FROM (SELECT tag, object_key FROM dbo.etl_object_tag
              WHERE tag IN ('PII','Confidencial','Regulado','Publico')
              GROUP BY tag, object_key) sub
    """)
    rc = cur.fetchone() or (0, 0, 0, 0)
    classification_counts = {"pii": int(rc[0] or 0), "confidencial": int(rc[1] or 0),
                              "regulado": int(rc[2] or 0), "publico": int(rc[3] or 0)}
    cur.execute(f"""
        {_ASSETS_CTE}
        SELECT TOP 15 asset_name, asset_type, database_name,
            SUM(pipeline_count), SUM(as_origem), SUM(as_destino)
        FROM assets GROUP BY asset_name, asset_type, database_name
        ORDER BY SUM(pipeline_count) DESC
    """)
    top_cols = ["asset_name", "asset_type", "database_name", "pipeline_count", "as_origem", "as_destino"]
    top_assets = [dict(zip(top_cols, r)) for r in cur.fetchall()]
    cur.execute("SELECT TOP 5 pipeline_name FROM dbo.etl_pipeline WHERE pipeline_name NOT IN (SELECT DISTINCT pipeline_name FROM dbo.etl_pipeline_owner) ORDER BY pipeline_name")
    alerts = [{"type": "pipeline_sem_owner", "message": f"Pipeline sem owner: {r[0]}"} for r in cur.fetchall()]
    return {"mode": "overview", "total_assets": total_assets, "total_pipelines": total_pipelines,
            "total_with_owner": total_with_owner, "classification_counts": classification_counts,
            "top_assets": top_assets, "alerts": alerts}


def _cat_browse(cur, search, database_name, asset_type, classification, top_n):
    top_n = min(200, max(1, top_n))
    where: list[str] = []
    params: list = []
    if search:
        where.append("a.asset_name LIKE ?"); params.append(f"%{search}%")
    if database_name:
        where.append("a.database_name = ?"); params.append(database_name)
    if asset_type:
        where.append("a.asset_type = ?"); params.append(asset_type)
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    if classification:
        sql = f"""
            {_ASSETS_CTE}
            SELECT TOP {top_n} a.asset_name, a.asset_type, a.database_name,
                SUM(a.pipeline_count), SUM(a.as_origem), SUM(a.as_destino)
            FROM assets a
            JOIN dbo.etl_object_tag ot ON ot.tag = ?
              AND ((a.asset_type='tabela'  AND ot.object_key = a.database_name+'.'+a.asset_name)
                OR (a.asset_type='tabela'  AND ot.object_key = a.asset_name)
                OR (a.asset_type='arquivo' AND ot.object_key = a.asset_name))
            {where_sql}
            GROUP BY a.asset_name, a.asset_type, a.database_name
            ORDER BY SUM(a.pipeline_count) DESC, a.asset_name
        """
        params = [classification] + params
    else:
        sql = f"""
            {_ASSETS_CTE}
            SELECT TOP {top_n} a.asset_name, a.asset_type, a.database_name,
                SUM(a.pipeline_count), SUM(a.as_origem), SUM(a.as_destino)
            FROM assets a {where_sql}
            GROUP BY a.asset_name, a.asset_type, a.database_name
            ORDER BY SUM(a.pipeline_count) DESC, a.asset_name
        """
    cur.execute(sql, params if params else [])
    asset_cols = ["asset_name", "asset_type", "database_name", "pipeline_count", "as_origem", "as_destino"]
    assets = [dict(zip(asset_cols, r)) for r in cur.fetchall()]
    cur.execute(f"{_ASSETS_CTE} SELECT DISTINCT database_name FROM assets WHERE database_name<>'' ORDER BY database_name")
    databases = [r[0] for r in cur.fetchall()]
    cur.execute(f"{_ASSETS_CTE} SELECT DISTINCT asset_type FROM assets ORDER BY asset_type")
    types = [r[0] for r in cur.fetchall()]
    cur.execute("SELECT DISTINCT tag FROM dbo.etl_object_tag WHERE tag IN ('PII','Confidencial','Regulado','Publico') ORDER BY tag")
    classifications = [r[0] for r in cur.fetchall()]
    return {"mode": "browse", "assets": assets,
            "facets": {"databases": databases, "types": types, "classifications": classifications}}


def _cat_asset_detail(cur, asset_name, asset_type, database_name):
    asset_type = (asset_type or "tabela").lower()
    if asset_type == "arquivo":
        where_l = "l.file_path = ?"; params_l: list = [asset_name]
    else:
        where_l = "(l.sql_expression LIKE ? OR l.object_name = ?)"; params_l = [f"%{asset_name}%", asset_name]
        if database_name:
            where_l += " AND l.database_name = ?"; params_l.append(database_name)
    cur.execute(f"""
        SELECT l.pipeline_name, l.job_name, CAST(pj.execution_order AS INT),
               l.columns_json, l.direction, ISNULL(l.sql_expression,'')
        FROM dbo.etl_job_lineage l
        JOIN dbo.etl_pipeline_job pj ON pj.pipeline_name=l.pipeline_name AND pj.job_name=l.job_name
        WHERE {where_l} ORDER BY l.direction, l.pipeline_name, pj.execution_order
    """, params_l)
    rows = cur.fetchall()
    p_orig: list = []; p_dest: list = []; all_cols: list = []; first_sql = ""
    for r in rows:
        p_name, j_name, exec_order, cols_json, direction, sql_expr = r
        try: cols = json.loads(cols_json) if cols_json else []
        except: cols = []
        all_cols.extend(cols)
        if not first_sql and sql_expr: first_sql = sql_expr
        entry = {"pipeline_name": p_name, "job_name": j_name,
                 "execution_order": exec_order, "columns_json": cols_json or ""}
        (p_orig if direction == "origem" else p_dest).append(entry)
    seen: set = set(); unique_cols: list = []
    for c in all_cols:
        if c not in seen: seen.add(c); unique_cols.append(c)
    candidates = ([f"{database_name}.{asset_name}", asset_name]
                  if asset_type != "arquivo" else [asset_name])
    tags: list = []; seen_tags: set = set()
    for ok in candidates:
        cur.execute("SELECT tag FROM dbo.etl_object_tag WHERE object_key=? ORDER BY tag", [ok])
        for rt in cur.fetchall():
            if rt[0] not in seen_tags: seen_tags.add(rt[0]); tags.append(rt[0])
    return {"mode": "asset_detail", "asset_name": asset_name, "asset_type": asset_type,
            "database_name": database_name or "", "pipelines_origem": p_orig,
            "pipelines_destino": p_dest, "columns": unique_cols, "tags": tags, "sql_expression": first_sql}


def _cat_list_jobs_lineage(cur, pipeline_name):
    cur.execute("""
        SELECT pj.job_name, CAST(pj.execution_order AS INT), pj.job_type, ISNULL(pj.job_command,'')
        FROM dbo.etl_pipeline_job pj WHERE pj.pipeline_name=?
        ORDER BY pj.execution_order, pj.job_name
    """, [pipeline_name])
    job_rows = cur.fetchall()
    cur.execute("""
        SELECT l.job_name, ISNULL(stm.type_label, l.object_type), l.object_name, l.direction
        FROM dbo.etl_job_lineage l
        LEFT JOIN dbo.etl_stage_type_map stm ON stm.type_raw=l.object_type
        WHERE l.pipeline_name=? AND l.object_name IS NOT NULL AND l.object_name<>''
        ORDER BY l.job_name, l.direction, l.object_type, l.object_name
    """, [pipeline_name])
    lineage_map: dict = {}
    for r in cur.fetchall():
        jn, otype, oname, direction = r
        if jn not in lineage_map: lineage_map[jn] = {"origens": [], "destinos": []}
        entry = {"tipo": otype or "", "nome": oname or ""}
        (lineage_map[jn]["origens"] if direction == "origem" else lineage_map[jn]["destinos"]).append(entry)
    job_list = []
    for row in job_rows:
        job_name, order, job_type, cmd = row
        lg = lineage_map.get(job_name, {"origens": [], "destinos": []})
        job_list.append({"job_name": job_name, "execution_order": order,
                         "job_type": job_type or "", "job_command": cmd or "",
                         "origens": lg["origens"], "destinos": lg["destinos"]})
    return {"pipeline_name": pipeline_name, "jobs": job_list}


@app.post("/catalogo", tags=["catalogo"])
def catalogo(body: dict = Body(default={})):
    """
    Catálogo de dados multi-modo. Substitui etl_catalogo_query.
    Modos: search, ranking, overview, browse, get_owner, save_owner, get_tags, save_tag,
           pipeline_history, file_lineage, list_pipelines, list_projects,
           list_job_types, save_job_type, delete_job_type, list_jobs_lineage, asset_detail
    """
    mode = (body.get("mode") or "search").strip().lower()
    try:
        conn = get_db_conn()
        cur  = conn.cursor()

        if mode == "list_projects":
            try:
                cur.execute("SELECT project_name, ativo FROM dbo.etl_project ORDER BY project_name")
                result = {"projects": [{"project_name": r[0], "ativo": r[1]} for r in cur.fetchall()]}
            except Exception:
                result = {"projects": [{"project_name": n, "ativo": 1} for n in
                          ["BI_CVP", "BI_VIDA", "BI_PRESTAMISTA", "BI_PREVIDENCIA"]]}

        elif mode == "list_job_types":
            inc = bool(body.get("include_inactive", False))
            where = "" if inc else "WHERE status=1"
            cur.execute(f"SELECT id,nome,descricao,lineage_enabled,status FROM dbo.etl_job_type {where} ORDER BY nome")
            result = {"job_types": [
                {"id": r[0], "nome": r[1], "descricao": r[2], "lineage_enabled": bool(r[3]), "status": bool(r[4])}
                for r in cur.fetchall()
            ]}

        elif mode == "save_job_type":
            data = body.get("data", {})
            user = body.get("user", "admin")
            jt_id = data.get("id")
            nome = (data.get("nome") or "").strip()
            if not nome:
                raise HTTPException(status_code=400, detail="Campo 'nome' obrigatório")
            descricao  = (data.get("descricao") or "").strip() or None
            lineage_en = 1 if data.get("lineage_enabled") else 0
            status_val = 1 if data.get("status", True) else 0
            if jt_id:
                cur.execute(
                    "UPDATE dbo.etl_job_type SET nome=?,descricao=?,lineage_enabled=?,status=? WHERE id=?",
                    (nome, descricao, lineage_en, status_val, int(jt_id)))
                result = {"ok": True, "action": "updated", "id": int(jt_id)}
            else:
                cur.execute(
                    "INSERT INTO dbo.etl_job_type (nome,descricao,lineage_enabled,status,criado_por) VALUES (?,?,?,?,?)",
                    (nome, descricao, lineage_en, status_val, user))
                cur.execute("SELECT MAX(id) FROM dbo.etl_job_type WHERE nome=?", (nome,))
                row = cur.fetchone()
                result = {"ok": True, "action": "created", "id": row[0] if row else None}
            conn.commit()

        elif mode == "delete_job_type":
            jt_id = int(body.get("id", 0))
            if not jt_id:
                raise HTTPException(status_code=400, detail="Parâmetro 'id' obrigatório")
            cur.execute("DELETE FROM dbo.etl_job_type WHERE id=?", (jt_id,))
            conn.commit()
            result = {"ok": True, "action": "deleted", "id": jt_id}

        elif mode == "list_jobs_lineage":
            result = _cat_list_jobs_lineage(cur, body.get("pipeline_name", ""))

        elif mode == "list_pipelines":
            cur.execute("SELECT pipeline_name FROM dbo.etl_pipeline ORDER BY pipeline_name")
            result = {"mode": "list_pipelines", "pipelines": [r[0] for r in cur.fetchall()]}

        elif mode == "get_owner":
            pname = body.get("pipeline_name", "")
            cur.execute("""
                SELECT owner_name, owner_email, steward_name, steward_email, updated_at, updated_by
                FROM dbo.etl_pipeline_owner WHERE pipeline_name=?
            """, [pname])
            rows = cur.fetchall()
            if rows:
                r = rows[0]
                result = {"pipeline_name": pname, "owner_name": r[0], "owner_email": r[1],
                          "steward_name": r[2], "steward_email": r[3],
                          "updated_at": str(r[4]) if r[4] else None, "updated_by": r[5]}
            else:
                result = {"pipeline_name": pname}

        elif mode == "save_owner":
            pname = body.get("pipeline_name", "")
            data  = body.get("data", {})
            user  = body.get("user", "sistema")
            cur.execute("""
                MERGE dbo.etl_pipeline_owner AS tgt
                USING (SELECT ? AS pipeline_name) AS src ON tgt.pipeline_name=src.pipeline_name
                WHEN MATCHED THEN UPDATE SET
                    owner_name=?,owner_email=?,steward_name=?,steward_email=?,updated_at=GETDATE(),updated_by=?
                WHEN NOT MATCHED THEN INSERT
                    (pipeline_name,owner_name,owner_email,steward_name,steward_email,updated_at,updated_by)
                    VALUES (?,?,?,?,?,GETDATE(),?);
            """, [pname, data.get("owner_name"), data.get("owner_email"),
                  data.get("steward_name"), data.get("steward_email"), user,
                  pname, data.get("owner_name"), data.get("owner_email"),
                  data.get("steward_name"), data.get("steward_email"), user])
            conn.commit()
            result = {"ok": True, "pipeline_name": pname}

        elif mode == "get_tags":
            ok = body.get("object_key", "")
            cur.execute("SELECT tag, added_by, added_at FROM dbo.etl_object_tag WHERE object_key=? ORDER BY tag", [ok])
            result = {"object_key": ok,
                      "tags": [{"tag": r[0], "added_by": r[1], "added_at": str(r[2])} for r in cur.fetchall()]}

        elif mode == "save_tag":
            ok   = body.get("object_key", "")
            tag  = body.get("tag", "")
            user = body.get("user", "sistema")
            remove = bool(body.get("remove", False))
            if remove:
                cur.execute("DELETE FROM dbo.etl_object_tag WHERE object_key=? AND tag=?", [ok, tag])
            else:
                cur.execute("""
                    IF NOT EXISTS (SELECT 1 FROM dbo.etl_object_tag WHERE object_key=? AND tag=?)
                        INSERT INTO dbo.etl_object_tag (object_key, tag, added_by) VALUES (?,?,?)
                """, [ok, tag, ok, tag, user])
            conn.commit()
            result = {"ok": True}

        elif mode == "pipeline_history":
            pname = body.get("pipeline_name", "")
            cur.execute("""
                SELECT TOP 20 created_at, status, reviewed_by, reviewed_at, LEFT(ISNULL(obs,''),120)
                FROM dbo.etl_seq_import
                WHERE seq_name=? OR pipeline_name_override=?
                ORDER BY created_at DESC
            """, [pname, pname])
            cols_h = ["imported_at", "status", "reviewed_by", "reviewed_at", "obs"]
            history = []
            for r in cur.fetchall():
                rec = dict(zip(cols_h, r))
                rec["imported_at"] = str(rec["imported_at"]) if rec["imported_at"] else None
                rec["reviewed_at"] = str(rec["reviewed_at"]) if rec["reviewed_at"] else None
                history.append(rec)
            result = {"mode": "pipeline_history", "pipeline_name": pname, "history": history}

        elif mode == "file_lineage":
            fname = body.get("file_name", "")
            cur.execute("""
                SELECT l.pipeline_name, l.job_name, l.direction
                FROM dbo.etl_job_lineage l
                WHERE l.file_path LIKE ? AND l.direction IN ('origem','destino')
                ORDER BY l.direction, l.pipeline_name
            """, [f"%{fname}%"])
            rows = cur.fetchall()
            result = {
                "mode": "file_lineage", "file_name": fname,
                "writers": [{"pipeline_name": r[0], "job_name": r[1]} for r in rows if r[2] == "destino"],
                "readers": [{"pipeline_name": r[0], "job_name": r[1]} for r in rows if r[2] == "origem"],
            }

        elif mode == "ranking":
            top_n = min(50, max(1, int(body.get("top_n", 15))))
            ranking_type = (body.get("ranking_type") or "tabela").lower()
            result = (_cat_ranking_arquivo(cur, top_n) if ranking_type == "arquivo"
                      else _cat_ranking_tabela(cur, top_n))

        elif mode == "overview":
            result = _cat_overview(cur)

        elif mode == "browse":
            result = _cat_browse(
                cur,
                search=(body.get("search") or "").strip(),
                database_name=(body.get("database_name") or "").strip(),
                asset_type=(body.get("asset_type") or "").strip().lower(),
                classification=(body.get("classification") or "").strip(),
                top_n=int(body.get("top_n", 100)),
            )

        elif mode == "asset_detail":
            asset_name = (body.get("asset_name") or "").strip()
            if not asset_name:
                raise HTTPException(status_code=400, detail="Parâmetro 'asset_name' obrigatório")
            result = _cat_asset_detail(
                cur, asset_name,
                asset_type=(body.get("asset_type") or "tabela").strip().lower(),
                database_name=(body.get("database_name") or "").strip(),
            )

        else:  # search
            search_type   = (body.get("search_type")   or "tabela").lower()
            direction     = (body.get("direction")      or "all").lower()
            database_name = (body.get("database_name") or "").strip()
            if search_type == "arquivo":
                file_name = (body.get("file_name") or "").strip()
                if not file_name:
                    raise HTTPException(status_code=400, detail="file_name obrigatório para search_type=arquivo")
                result = _cat_search_arquivo(cur, file_name, direction)
            else:
                object_name = (body.get("object_name") or "").strip()
                if not object_name:
                    raise HTTPException(status_code=400, detail="object_name obrigatório para search_type=tabela")
                result = _cat_search_tabela(cur, object_name, direction, database_name)

        cur.close(); conn.close()
        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Dashboard ────────────────────────────────────────────────────────────────

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

        cur.execute(f"""
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
                SELECT *, ROW_NUMBER() OVER (PARTITION BY pipeline ORDER BY inicio DESC) AS rn FROM execs
            )
            SELECT TOP 20
                r.pipeline, r.project, r.ultimo_status, r.inicio, r.duracao_segundos,
                r.total_jobs, r.execution_id, COALESCE(p.criticidade,'') AS criticidade
            FROM ranked r
            LEFT JOIN dbo.etl_pipeline p ON p.pipeline_name = r.pipeline
            WHERE rn=1 AND COALESCE(p.ambiente,'PROD')='PROD'
            ORDER BY
                CASE COALESCE(p.criticidade,'') WHEN 'ALTA' THEN 1 WHEN 'MEDIA' THEN 2 WHEN 'BAIXA' THEN 3 ELSE 4 END,
                CASE r.ultimo_status WHEN 'FAILED' THEN 1 WHEN 'WARNING' THEN 2 WHEN 'RUNNING' THEN 3 ELSE 4 END,
                r.inicio DESC
        """, [fp] if fp else [])
        pipeline_status = [
            {
                "pipeline": r[0], "project": r[1], "ultimo_status": r[2],
                "ultimo_inicio": _fmt_dt(r[3]), "duracao_segundos": int(r[4] or 0),
                "total_jobs": int(r[5] or 0), "execution_id": r[6], "criticidade": r[7] or "",
            }
            for r in cur.fetchall()
        ]

        cur.execute(f"""
            SELECT TOP 5
                e.pipeline, e.project, e.job_name, e.status, e.start_time, e.execution_id, e.log_file
            FROM dbo.etl_job_execution e
            JOIN dbo.etl_pipeline p ON p.pipeline_name = e.pipeline
            WHERE e.status='FAILED' AND COALESCE(p.ambiente,'PROD')='PROD' {where_proj_alias}
            ORDER BY e.start_time DESC
        """, [fp] if fp else [])
        ultimas_falhas = [
            {"pipeline": r[0], "project": r[1], "job_name": r[2], "status": r[3],
             "inicio": _fmt_dt(r[4]), "execution_id": r[5], "log_file": r[6]}
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
            "por_projeto": por_projeto, "filter_project": fp,
        },
        "pipeline_status": pipeline_status,
        "ultimas_falhas": ultimas_falhas,
        "executando_agora": executando_agora,
        "alertas_perf": alertas_perf,
    }


# ── Sync pipeline status ──────────────────────────────────────────────────────

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


@app.get("/sync/pipeline-status/dry-run", tags=["sync"])
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


@app.post("/sync/pipeline-status", tags=["sync"])
async def sync_pipeline_status():
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
