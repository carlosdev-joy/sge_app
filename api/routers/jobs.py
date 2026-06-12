"""api/routers/jobs.py — GET /jobs, POST /pipelines/jobs/register, POST /pipelines/jobs/reorder."""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException

from api.db import get_db_conn
from api.deps import (
    PERM_EDITAR,
    get_current_user, require_perm,
)

log = logging.getLogger("orquestra-api")

router = APIRouter()


def _fmt_dt(v):
    if v is None:
        return None
    if hasattr(v, "strftime"):
        return v.strftime("%Y-%m-%d %H:%M:%S")
    return str(v)


VALID_JOB_TYPES = {"datastage", "shell", "python", "storedproc"}


@router.get("/jobs", tags=["jobs"])
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
                {_sel('updated_at',  'updated_at')},
                {_sel('ssh_conn_id', 'ssh_conn_id')}
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
                "ssh_conn_id": r[9],
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


@router.post("/pipelines/jobs/register", tags=["jobs"])
async def register_pipeline_jobs(body: dict = Body(default={}), _auth: dict = Depends(require_perm(PERM_EDITAR))):
    """Registra/atualiza jobs e lineage de um pipeline (etl_pipeline_job_register)."""
    pipeline_name = (body.get("pipeline_name") or "").strip()
    if not pipeline_name:
        raise HTTPException(status_code=422, detail="pipeline_name é obrigatório")
    # Wizard de pipeline salva jobs antes do lineage estar completo
    require_lineage = bool(body.get("require_lineage", True))

    jobs_raw = body.get("jobs")
    if jobs_raw:
        if not isinstance(jobs_raw, list) or len(jobs_raw) == 0:
            raise HTTPException(status_code=422, detail="jobs deve ser lista não vazia")
        jobs = jobs_raw
    else:
        job_name = body.get("job_name")
        order    = body.get("execution_order")
        if not job_name or order is None:
            raise HTTPException(status_code=422, detail="Informe jobs[] ou job_name+execution_order")
        jobs = [{"job_name": job_name, "execution_order": int(order),
                 "job_type": body.get("job_type", "datastage"),
                 "job_command": body.get("job_command"),
                 "origens": body.get("origens", []),
                 "destinos": body.get("destinos", [])}]

    erros = []
    try:
        conn = get_db_conn(); cur = conn.cursor()
        for idx, job in enumerate(jobs):
            j_name   = (job.get("job_name") or "").strip()
            j_order  = job.get("execution_order")
            j_type   = (job.get("job_type") or "datastage").lower().strip()
            j_cmd    = job.get("job_command") or None
            origens  = job.get("origens",  [])
            destinos = job.get("destinos", [])
            transfs  = job.get("transformacoes", [])

            if not j_name or j_order is None:
                erros.append(f"Item {idx}: job_name e execution_order obrigatórios"); continue
            if j_type not in VALID_JOB_TYPES:
                erros.append(f"Item {idx} ({j_name}): job_type '{j_type}' inválido"); continue
            if not origens and not transfs and require_lineage:
                erros.append(f"Item {idx} ({j_name}): ao menos 1 origem é obrigatória"); continue
            if not destinos and not transfs and require_lineage:
                erros.append(f"Item {idx} ({j_name}): ao menos 1 destino é obrigatório"); continue

            try:
                cur.execute(
                    "EXEC dbo.sp_etl_pipeline_job_upsert "
                    "@pipeline_name=?, @job_name=?, @execution_order=?, @job_type=?, @job_command=?, @ssh_conn_id=?",
                    (pipeline_name, j_name, int(j_order), j_type, j_cmd, job.get("ssh_conn_id") or None),
                )
            except Exception as e:
                erros.append(f"Item {idx} ({j_name}): erro ao gravar job — {e}"); continue

            for direction, objects in [("origem", origens), ("transformacao", transfs), ("destino", destinos)]:
                for oi, obj in enumerate(objects):
                    obj_name = (obj.get("object_name") or "").strip()
                    if not obj_name:
                        erros.append(f"Item {idx} ({j_name}) {direction}[{oi}]: object_name obrigatório"); continue
                    try:
                        cur.execute(
                            "EXEC dbo.sp_etl_job_lineage_upsert "
                            "@pipeline_name=?, @job_name=?, @direction=?, @object_type=?, @object_name=?, "
                            "@stage_name=?, @stage_type_raw=?, @database_name=?, @sql_expression=?, "
                            "@file_path=?, @dsx_source_file=?, @extracted_at=?, @extraction_method=?",
                            (pipeline_name, j_name, direction,
                             (obj.get("object_type") or "Tabela").strip(), obj_name,
                             obj.get("stage_name"), obj.get("stage_type_raw"),
                             obj.get("database_name"), obj.get("sql_expression"),
                             obj.get("file_path"), obj.get("dsx_source_file"),
                             obj.get("extracted_at"), obj.get("extraction_method")),
                        )
                    except Exception as e:
                        erros.append(f"Item {idx} ({j_name}) {direction} '{obj_name}': {e}")

        if erros:
            conn.rollback()
            raise HTTPException(status_code=422, detail={"errors": erros})
        conn.commit()
        cur.close(); conn.close()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro DB: {e}")
    return {"ok": True, "pipeline_name": pipeline_name, "jobs_registered": len(jobs)}


@router.post("/pipelines/jobs/reorder", tags=["jobs"])
async def reorder_pipeline_jobs(body: dict = Body(default={}), _auth: dict = Depends(require_perm(PERM_EDITAR))):
    """Reordena jobs sem tocar em lineage (etl_pipeline_job_reorder)."""
    pipeline_name = (body.get("pipeline_name") or "").strip()
    if not pipeline_name:
        raise HTTPException(status_code=422, detail="pipeline_name é obrigatório")

    jobs_raw = body.get("jobs")
    if jobs_raw:
        if not isinstance(jobs_raw, list) or len(jobs_raw) == 0:
            raise HTTPException(status_code=422, detail="jobs deve ser lista não vazia")
        jobs = jobs_raw
    else:
        job_name = body.get("job_name")
        order    = body.get("execution_order")
        if not job_name or order is None:
            raise HTTPException(status_code=422, detail="Informe jobs[] ou job_name+execution_order")
        jobs = [{"job_name": job_name, "execution_order": int(order)}]

    erros = []
    for idx, j in enumerate(jobs):
        name  = (j.get("job_name") or "").strip()
        order = j.get("execution_order")
        if not name or order is None:
            erros.append(f"Item {idx}: job_name e execution_order obrigatórios")
        elif int(order) < 1:
            erros.append(f"Item {idx} ({name}): execution_order deve ser >= 1")
    if erros:
        raise HTTPException(status_code=422, detail={"errors": erros})

    try:
        conn = get_db_conn(); cur = conn.cursor()
        for j in jobs:
            cur.execute(
                "EXEC dbo.sp_etl_pipeline_job_reorder @pipeline_name=?, @job_name=?, @execution_order=?",
                (pipeline_name, j["job_name"].strip(), int(j["execution_order"])),
            )
        conn.commit()
        cur.close(); conn.close()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro DB: {e}")
    return {"ok": True, "pipeline_name": pipeline_name, "jobs_reordered": len(jobs)}
