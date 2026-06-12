"""api/routers/factory.py — GET /factory/runs, GET /factory/runs/{dag_run_id}/log."""
from __future__ import annotations

import json as _json
import logging

from fastapi import APIRouter, HTTPException, Query

from api.db import get_db_conn

log = logging.getLogger("orquestra-api")

router = APIRouter()

FACTORY_DAG_ID  = "etl_dag_factory"
FACTORY_TASK_ID = "gerar_dags"


def _fmt_dt(v):
    if v is None:
        return None
    if hasattr(v, "strftime"):
        return v.strftime("%Y-%m-%d %H:%M:%S")
    return str(v)


@router.get("/factory/runs", tags=["factory"])
def factory_runs(limit: int = Query(20, le=100)):
    """Últimas execuções da etl_dag_factory lidas de dbo.etl_factory_log."""
    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute(
            "SELECT TOP (?) dag_run_id, iniciado_em, finalizado_em, estado, "
            "       escopo, pipeline_name, geradas, erros "
            "FROM dbo.etl_factory_log "
            "ORDER BY iniciado_em DESC",
            (limit,),
        )
        cols = ["dag_run_id", "iniciado_em", "finalizado_em", "estado",
                "escopo", "pipeline_name", "geradas", "erros"]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        cur.close(); conn.close()
        for r in rows:
            r["iniciado_em"]   = _fmt_dt(r["iniciado_em"])
            r["finalizado_em"] = _fmt_dt(r["finalizado_em"])
        return {"data": rows}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao consultar factory log: {e}")


@router.get("/factory/runs/{dag_run_id}/log", tags=["factory"])
def factory_run_log(dag_run_id: str):
    """Etapas estruturadas de uma execução da factory (de dbo.etl_factory_log)."""
    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute(
            "SELECT estado, escopo, geradas, erros, detalhes_json, iniciado_em, finalizado_em "
            "FROM dbo.etl_factory_log WHERE dag_run_id=?",
            (dag_run_id,),
        )
        row = cur.fetchone()
        cur.close(); conn.close()
        if not row:
            raise HTTPException(status_code=404, detail="Execução não encontrada no banco")
        estado, escopo, geradas_n, erros_n, detalhes_json, ini, fim = row
        detalhes = _json.loads(detalhes_json) if detalhes_json else {}
        return {
            "dag_run_id":    dag_run_id,
            "estado":        estado,
            "escopo":        escopo,
            "geradas":       geradas_n,
            "erros":         erros_n,
            "iniciado_em":   _fmt_dt(ini),
            "finalizado_em": _fmt_dt(fim),
            "steps":         detalhes.get("steps", []),
            "erros_lista":   detalhes.get("erros", []),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao consultar log: {e}")
