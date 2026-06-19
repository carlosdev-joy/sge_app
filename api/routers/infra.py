"""api/routers/infra.py — Endpoints de infra: health, config, versao, audit, performance."""
from __future__ import annotations

import logging
import os
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query

from db import get_db_conn
from deps import (
    PERM_EDITAR,
    get_current_user, get_admin_user, require_perm,
)

log = logging.getLogger("orquestra-api")

router = APIRouter()

# ── helpers de data ───────────────────────────────────────────────────────────

def _fmt_dt(v):
    if v is None:
        return None
    if hasattr(v, "strftime"):
        return v.strftime("%Y-%m-%d %H:%M:%S")
    return str(v)


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
    # URL do Airflow para os links "Ver no Airflow" (abrem no NAVEGADOR do usuário).
    # Default vem da env AIRFLOW_UI_URL (definida no compose); 'localhost' é só último
    # recurso e NÃO funciona em produção. O valor em etl_app_config (Admin) sobrepõe.
    "airflow_ui_url":                 os.getenv("AIRFLOW_UI_URL") or "http://localhost:8080",
}
INT_CONFIG_KEYS = {
    "dashboard_refresh_interval_sec",
    "failure_badge_refresh_sec",
    "failure_badge_hours_lookback",
    "pipeline_query_limit",
    "jobs_query_limit",
    "logs_query_limit",
}

# Chaves que não devem ser expostas no GET /config público (visíveis apenas no Admin)
SENSITIVE_CONFIG_KEYS = {"teams_webhook_url", "powerbi_client_secret"}


def _is_sensitive_config(key: str) -> bool:
    """Webhooks (teams_webhook_*), segredos do Power BI e chaves listadas não vazam no /config público."""
    return (
        key in SENSITIVE_CONFIG_KEYS
        or key.startswith("teams_webhook")
        or key == "powerbi_client_secret"
    )


# ── Health ────────────────────────────────────────────────────────────────────

@router.get("/health", tags=["infra"])
def health():
    return {"status": "ok", "version": "0.3.0"}


# ── Config ────────────────────────────────────────────────────────────────────

@router.get("/config", tags=["config"])
def get_config():
    """Retorna parâmetros de configuração da aplicação. Substitui etl_app_config_query."""
    result = dict(DEFAULTS_CONFIG)
    try:
        conn = get_db_conn()
        cur  = conn.cursor()
        cur.execute("SELECT config_key, config_value FROM dbo.etl_app_config")
        for key, value in cur.fetchall():
            if _is_sensitive_config(key):
                continue
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

@router.get("/versao", tags=["config"])
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


# ── Versão Register ───────────────────────────────────────────────────────────

@router.post("/versao/register", tags=["config"])
async def register_versao(body: dict = Body(default={}), _auth: dict = Depends(require_perm(PERM_EDITAR))):
    """CRUD de versões do ORQUESTRA (etl_versao_register).

    body.action: create | update | delete
    """
    action = (body.get("action") or "create").strip().lower()
    try:
        conn = get_db_conn(); cur = conn.cursor()

        if action == "delete":
            record_id = int(body.get("id", 0))
            if not record_id:
                raise HTTPException(status_code=422, detail="id é obrigatório para action=delete")
            cur.execute("DELETE FROM dbo.etl_versao_ferramenta WHERE id = ?", (record_id,))
            conn.commit(); cur.close(); conn.close()
            return {"action": "delete", "id": record_id}

        versao     = (body.get("versao") or "").strip()
        titulo     = (body.get("titulo") or "").strip()
        descricao  = (body.get("descricao_md") or "").strip() or None
        criado_por = (body.get("criado_por") or "admin").strip()

        if not versao or not titulo:
            raise HTTPException(status_code=422, detail="versao e titulo são obrigatórios")

        def _sync_config(cur, v, t):
            for key, val in (("app_version", v), ("app_release_name", t)):
                cur.execute(
                    "UPDATE dbo.etl_app_config SET config_value=? WHERE config_key=?", (val, key)
                )
                cur.execute(
                    "INSERT INTO dbo.etl_app_config (config_key, config_value) "
                    "SELECT ?, ? WHERE NOT EXISTS (SELECT 1 FROM dbo.etl_app_config WHERE config_key=?)",
                    (key, val, key),
                )

        if action == "update":
            record_id = int(body.get("id", 0))
            if not record_id:
                raise HTTPException(status_code=422, detail="id é obrigatório para action=update")
            cur.execute(
                "UPDATE dbo.etl_versao_ferramenta SET versao=?, titulo=?, descricao_md=?, criado_por=? "
                "WHERE id=?", (versao, titulo, descricao, criado_por, record_id)
            )
            _sync_config(cur, versao, titulo)
            conn.commit(); cur.close(); conn.close()
            return {"action": "update", "id": record_id, "versao": versao}

        # create
        cur.execute(
            "INSERT INTO dbo.etl_versao_ferramenta (versao, titulo, descricao_md, criado_por) "
            "VALUES (?, ?, ?, ?)", (versao, titulo, descricao, criado_por)
        )
        _sync_config(cur, versao, titulo)
        conn.commit(); cur.close(); conn.close()
        return {"action": "create", "versao": versao, "titulo": titulo}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro DB: {e}")


# ── Audit ─────────────────────────────────────────────────────────────────────

@router.get("/audit", tags=["audit"])
def get_audit(
    pipeline_name: str = Query(...),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """Histórico de alterações de um pipeline (etl_pipeline_audit_query)."""
    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM dbo.etl_pipeline_audit WHERE pipeline_name = ?",
            (pipeline_name,),
        )
        total = cur.fetchone()[0] or 0

        cur.execute(
            """
            SELECT changed_at, changed_by, field_name, old_value, new_value
            FROM dbo.etl_pipeline_audit
            WHERE pipeline_name = ?
            ORDER BY changed_at DESC
            OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
            """,
            (pipeline_name, offset, limit),
        )
        cols = [d[0] for d in cur.description]
        rows = []
        for row in cur.fetchall():
            r = dict(zip(cols, row))
            if r.get("changed_at") and hasattr(r["changed_at"], "isoformat"):
                r["changed_at"] = r["changed_at"].isoformat()
            rows.append(r)
        cur.close(); conn.close()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro DB: {e}")
    pages = max(1, -(-total // limit))
    return {"total": total, "offset": offset, "limit": limit, "pages": pages,
            "filters": {"pipeline_name": pipeline_name}, "data": rows}


# ── Performance ───────────────────────────────────────────────────────────────

@router.get("/performance", tags=["monitor"])
def get_performance(
    pipeline: str = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """Retorna snapshots de performance (pipelines com alertas de duração)."""
    try:
        conn = get_db_conn(); cur = conn.cursor()
        where = "WHERE 1=1"
        params: list = []
        if pipeline:
            where += " AND pipeline = ?"; params.append(pipeline)

        cur.execute(f"SELECT COUNT(*) FROM dbo.etl_pipeline_performance_snapshot {where}", params)
        total = cur.fetchone()[0] or 0

        cur.execute(
            f"""SELECT pipeline, project, execution_id, alerta_horas, elapsed_seconds, snapshot_at
                FROM dbo.etl_pipeline_performance_snapshot
                {where}
                ORDER BY snapshot_at DESC
                OFFSET ? ROWS FETCH NEXT ? ROWS ONLY""",
            params + [offset, limit],
        )
        cols = [d[0] for d in cur.description]
        rows = []
        for row in cur.fetchall():
            r = dict(zip(cols, row))
            if r.get("snapshot_at") and hasattr(r["snapshot_at"], "isoformat"):
                r["snapshot_at"] = r["snapshot_at"].isoformat()
            rows.append(r)
        cur.close(); conn.close()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro DB: {e}")
    pages = max(1, -(-total // limit))
    return {"total": total, "offset": offset, "limit": limit, "pages": pages, "data": rows}
