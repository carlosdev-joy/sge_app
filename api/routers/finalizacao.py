"""api/routers/finalizacao.py — GET /finalizacao/executando, POST /finalizacao/finalizar.

Finalização manual de execuções penduradas em RUNNING. Diferente do
/execucoes/reconciliar (espelho puro, só fecha o que o DataStage já reporta
terminal), aqui o operador FORÇA o encerramento nos logs do Orquestra quando o
processo já terminou no DataStage mas o registro ficou órfão (worker morreu
antes do log_end e o etl_ds_job_log também ficou RUNNING — nada mais fecha).

Uma finalização toca três lugares, na mesma transação:
  1. dbo.etl_job_execution  — status final + end_time (some do Executando/Gantt/KPIs/SLA);
  2. dbo.etl_ds_job_log     — status/status_code terminal (monitor central para de pollar);
  3. dbo.etl_pipeline_performance_snapshot — DELETE (some da tela Performance na hora).
Auditoria em dbo.etl_pipeline_audit (quem, quando, motivo) + notificação best-effort.

NÃO toca no DataStage nem no Airflow — é só o registro no Orquestra.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Body, Depends, HTTPException

from db import get_db_conn
from deps import PERM_EXECUTAR, get_current_user, require_perm
from services.notify import add_notificacao

log = logging.getLogger("orquestra-api")

router = APIRouter()

# status final permitido → (status, status_code) equivalentes no etl_ds_job_log
_STATUS_DS = {
    "SUCCESS": ("SUCCESS", 1),
    "WARNING": ("WARNING", 2),
    "FAILED":  ("ABORTED", 3),
}


def _fmt_dt(v):
    if v is None:
        return None
    if hasattr(v, "strftime"):
        return v.strftime("%Y-%m-%d %H:%M:%S")
    return str(v)


@router.get("/finalizacao/executando", tags=["finalizacao"])
def list_executando(q: str = "", _auth: dict = Depends(get_current_user)):
    """Execuções em RUNNING agregadas por (execution_id, pipeline), com o rastro que
    a finalização vai limpar: jobs RUNNING, estruturas abertas no etl_ds_job_log e
    snapshots de performance. Filtro opcional `q` por nome de pipeline (LIKE)."""
    q = (q or "").strip()
    data: list[dict] = []
    try:
        conn = get_db_conn(); cur = conn.cursor()
        params: list = []
        where = "WHERE status = 'RUNNING' AND end_time IS NULL"
        if q:
            where += " AND pipeline LIKE ?"
            params.append(f"%{q}%")
        cur.execute(f"""
            SELECT execution_id, pipeline, MAX(project) AS project,
                   COUNT(*) AS jobs_running, MIN(start_time) AS inicio,
                   DATEDIFF(SECOND, MIN(start_time), GETDATE()) AS elapsed_seconds
            FROM dbo.etl_job_execution
            {where}
            GROUP BY execution_id, pipeline
            ORDER BY MIN(start_time) ASC
        """, params)
        data = [
            {
                "execution_id": r[0], "pipeline": r[1], "project": r[2],
                "jobs_running": int(r[3] or 0), "inicio": _fmt_dt(r[4]),
                "elapsed_seconds": int(r[5] or 0),
                "estruturas_abertas": 0, "snapshots": 0,
            }
            for r in cur.fetchall()
        ]

        # Estruturas ainda abertas no log do DataStage (inclui órfãs sem par no
        # etl_job_execution — também precisam de finalização)
        try:
            params_ds: list = []
            where_ds = "WHERE status IN ('RUNNING', 'QUEUED')"
            if q:
                where_ds += " AND pipeline_name LIKE ?"
                params_ds.append(f"%{q}%")
            cur.execute(f"""
                SELECT execution_id, pipeline_name, MAX(project), COUNT(*)
                FROM dbo.etl_ds_job_log
                {where_ds}
                GROUP BY execution_id, pipeline_name
            """, params_ds)
            idx = {(d["execution_id"], d["pipeline"]): d for d in data}
            for r in cur.fetchall():
                d = idx.get((r[0], r[1]))
                if d is None:
                    d = {
                        "execution_id": r[0], "pipeline": r[1], "project": r[2],
                        "jobs_running": 0, "inicio": None, "elapsed_seconds": 0,
                        "estruturas_abertas": 0, "snapshots": 0,
                    }
                    data.append(d); idx[(r[0], r[1])] = d
                d["estruturas_abertas"] = int(r[3] or 0)
        except Exception as e:
            log.warning("finalizacao: etl_ds_job_log indisponível: %s", e)

        # Snapshots de performance pendurados na tela Performance
        try:
            cur.execute("""
                SELECT execution_id, pipeline, COUNT(*)
                FROM dbo.etl_pipeline_performance_snapshot
                GROUP BY execution_id, pipeline
            """)
            idx = {(d["execution_id"], d["pipeline"]): d for d in data}
            for r in cur.fetchall():
                d = idx.get((r[0], r[1]))
                if d is not None:
                    d["snapshots"] = int(r[2] or 0)
        except Exception as e:
            log.warning("finalizacao: snapshots indisponíveis: %s", e)

        cur.close(); conn.close()
    except Exception as e:
        log.warning("finalizacao: listagem degradou para vazio: %s", e)
        return {"data": []}
    return {"data": data}


@router.post("/finalizacao/finalizar", tags=["finalizacao"])
def finalizar_execucao(body: dict = Body(default={}),
                       user: dict = Depends(require_perm(PERM_EXECUTAR))):
    """Força o encerramento de execuções RUNNING de um pipeline nos logs do Orquestra.

    Body: pipeline (obrigatório), status_final ('SUCCESS'|'WARNING'|'FAILED',
          obrigatório), execution_id (opcional — sem ele fecha TODAS as execuções
          RUNNING do pipeline), motivo (opcional, vai para a auditoria).
    """
    pipeline     = (body.get("pipeline") or "").strip()
    execution_id = (body.get("execution_id") or "").strip()
    status_final = (body.get("status_final") or "").strip().upper()
    motivo       = (body.get("motivo") or "").strip() or None

    if not pipeline:
        raise HTTPException(status_code=422, detail="pipeline é obrigatório")
    if status_final not in _STATUS_DS:
        raise HTTPException(status_code=422,
                            detail="status_final deve ser SUCCESS, WARNING ou FAILED")
    ds_status, ds_code = _STATUS_DS[status_final]

    try:
        conn = get_db_conn(); cur = conn.cursor()

        # Alvos: execuções RUNNING no log principal + estruturas abertas no log DS
        # (união — cobre a órfã que só existe em um dos dois)
        extra_exec = " AND execution_id = ?" if execution_id else ""
        args = [pipeline] + ([execution_id] if execution_id else [])
        cur.execute(f"""
            SELECT execution_id FROM dbo.etl_job_execution
            WHERE pipeline = ? AND status = 'RUNNING' AND end_time IS NULL{extra_exec}
            UNION
            SELECT execution_id FROM dbo.etl_ds_job_log
            WHERE pipeline_name = ? AND status IN ('RUNNING', 'QUEUED'){extra_exec}
        """, args + args)
        alvos = [r[0] for r in cur.fetchall()]
        if not alvos:
            cur.close(); conn.close()
            raise HTTPException(status_code=404,
                detail="Nenhuma execução em andamento encontrada para este pipeline")

        # 1) Tira do Executando (Logs, card do Dashboard, Gantt, SLA/perf monitors)
        cur.execute(f"""
            UPDATE dbo.etl_job_execution
               SET status = ?, end_time = GETDATE(),
                   duration_seconds = DATEDIFF(SECOND, start_time, GETDATE()),
                   updated_at = GETDATE()
             WHERE pipeline = ? AND status = 'RUNNING' AND end_time IS NULL{extra_exec}
        """, [status_final] + args)
        jobs_fechados = max(0, cur.rowcount or 0)

        # 2) Fecha a estrutura no log do DataStage (monitor central para de pollar)
        cur.execute(f"""
            UPDATE dbo.etl_ds_job_log
               SET status = ?, status_code = ?,
                   ds_end_time = COALESCE(ds_end_time, GETDATE()),
                   updated_at = GETDATE()
             WHERE pipeline_name = ? AND status IN ('RUNNING', 'QUEUED'){extra_exec}
        """, [ds_status, ds_code] + args)
        estruturas_fechadas = max(0, cur.rowcount or 0)

        # 3) Limpa a tela Performance imediatamente (novos snapshots não voltam:
        #    o monitor de performance só insere para status='RUNNING')
        cur.execute(f"""
            DELETE FROM dbo.etl_pipeline_performance_snapshot
             WHERE pipeline = ?{extra_exec}
        """, args)
        snapshots_removidos = max(0, cur.rowcount or 0)

        # Auditoria: uma linha por execução finalizada
        matricula = str(user.get("matricula") or "?")
        for eid in alvos:
            novo = f"{status_final} (finalização manual, execução {eid})"
            if motivo:
                novo += f" — motivo: {motivo}"
            cur.execute(
                "INSERT INTO dbo.etl_pipeline_audit "
                "(pipeline_name, changed_by, field_name, old_value, new_value, changed_at) "
                "VALUES (?, ?, 'finalizacao_manual', 'RUNNING', ?, GETDATE())",
                (pipeline, matricula, novo),
            )

        conn.commit()
        cur.close(); conn.close()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    add_notificacao(
        user.get("matricula"),
        f"Pipeline {pipeline} finalizado manualmente",
        f"{len(alvos)} execução(ões) marcadas como {status_final}; "
        f"{jobs_fechados} job(s) e {estruturas_fechadas} estrutura(s) fechados, "
        f"{snapshots_removidos} snapshot(s) de performance removidos.",
        tipo="warning", link="/finalizacao",
    )
    log.info("Finalização manual: %s por %s → %s (execs=%s jobs=%s estruturas=%s snaps=%s)",
             pipeline, user.get("matricula"), status_final,
             alvos, jobs_fechados, estruturas_fechadas, snapshots_removidos)

    return {
        "ok": True, "pipeline": pipeline, "status_final": status_final,
        "execucoes_finalizadas": alvos, "jobs_fechados": jobs_fechados,
        "estruturas_fechadas": estruturas_fechadas,
        "snapshots_removidos": snapshots_removidos,
    }
