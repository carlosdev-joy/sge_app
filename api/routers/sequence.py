"""api/routers/sequence.py — POST /sequence/parse, POST /sequence/approve."""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Body, Depends, HTTPException

from db import get_db_conn
from deps import (
    PERM_EDITAR,
    require_perm,
)

log = logging.getLogger("orquestra-api")

router = APIRouter()


def _build_cron(schedule_type, hour, minute, dow, dom):
    """Cron do rascunho importado, ou None quando é sob demanda.

    Mesma regra de api/routers/pipelines.py: 'on_demand' não tem cron, e o
    gerador transforma isso em `schedule=None` (DAG ativa, só manual).
    """
    st = (schedule_type or "daily").strip().lower()
    if st == "on_demand": return None
    h, m = int(hour or 0), int(minute or 0)
    if st == "hourly":   return f"{m} * * * *"
    if st == "daily":    return f"{m} {h} * * *"
    if st == "weekly":   return f"{m} {h} * * {int(dow or 1)}"
    if st == "monthly":  return f"{m} {h} {int(dom or 1)} * *"
    if st == "biweekly":
        d = int(dom or 1)
        return f"{m} {h} {d},{d + 15} * *"
    return f"{m} {h} * * *"


@router.post("/sequence/parse", tags=["sequence"])
async def sequence_parse(body: dict = Body(default={}), _auth: dict = Depends(require_perm(PERM_EDITAR))):
    """Faz parse de uma sequence DataStage .dsx e grava em staging (etl_sequence_import_parse)."""
    import os, sys, re

    project_name = (body.get("project_name") or "").strip()
    seq_name     = (body.get("seq_name") or "").strip()
    imported_by  = (body.get("imported_by") or "system").strip()
    domain       = (body.get("domain") or "").strip() or None

    if not project_name or not seq_name:
        raise HTTPException(status_code=422, detail="project_name e seq_name são obrigatórios")

    dsx_base = os.environ.get("DSX_BASE_DIR", "/opt/airflow/dsx")
    dsx_path = os.path.join(dsx_base, f"{project_name}.dsx")
    if not os.path.exists(dsx_path):
        raise HTTPException(status_code=404,
            detail=f"Arquivo '{project_name}.dsx' não encontrado em '{dsx_base}'")

    dags_folder = os.environ.get("DAGS_FOLDER", "/opt/airflow/dags")
    for p in [dags_folder, os.path.dirname(dags_folder)]:
        if p not in sys.path:
            sys.path.insert(0, p)
    try:
        from utils.dsx_engine import DSXEngine  # type: ignore
    except ImportError as e:
        raise HTTPException(status_code=500, detail=f"DSXEngine não disponível: {e}")

    def _decode_dsx(text):
        return re.sub(r'\\\(([0-9A-Fa-f]{2})\)', lambda m: chr(int(m.group(1), 16)), text)

    def _sanitize(name):
        for c, r in [('ç','c'),('ã','a'),('â','a'),('á','a'),('à','a'),('é','e'),('ê','e'),
                     ('í','i'),('ó','o'),('ô','o'),('õ','o'),('ú','u')]:
            name = name.replace(c, r).replace(c.upper(), r.upper())
        return re.sub(r'_+', '_', re.sub(r'[^a-zA-Z0-9_]', '_', name)).strip('_')

    try:
        with open(dsx_path, "r", encoding="utf-8", errors="ignore") as fh:
            content = fh.read()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao ler DSX: {e}")

    # Localizar a sequence no arquivo
    pattern = re.escape(seq_name)
    match = re.search(
        r'(BEGIN DSJOB\s+Identifier\s+"' + pattern + r'".*?)(?=BEGIN DSJOB|\Z)',
        content, re.DOTALL | re.IGNORECASE
    )
    if not match:
        raise HTTPException(status_code=404,
            detail=f"Sequence '{seq_name}' não encontrada em '{project_name}.dsx'")

    seq_block = match.group(1)
    jtype = re.search(r'JobType\s+"?(\d+)"?', seq_block)
    if not jtype or jtype.group(1) != '2':
        raise HTTPException(status_code=422, detail="O bloco encontrado não é uma sequence (JobType != 2)")

    # Extrair jobs em ordem
    jcc_m = re.search(r'JobControlCode\s*=\+=\+=\+=\s*(.*?)\s*=\+=\+=\+=', seq_block, re.DOTALL)
    jobs_in_order: list[str] = []
    if jcc_m:
        jcc  = jcc_m.group(1)
        seen: set[str] = set()
        for pat in [r'DSAttachJob\(\\"([^\\"]+)\\"', r'DSAttachJob\(\"([^\"]+)\"', r'DSAttachJob\("([^"]+)"']:
            for job in re.findall(pat, jcc):
                if job and job not in seen:
                    seen.add(job); jobs_in_order.append(job)
            if jobs_in_order:
                break

    name_m   = re.search(r'^\s+Name\s+"([^"]+)"', seq_block, re.MULTILINE)
    seq_decoded = _decode_dsx(name_m.group(1) if name_m else seq_name)
    pipeline_suggestion = _sanitize(seq_decoded)

    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute(
            "INSERT INTO dbo.etl_seq_import "
            "(dsx_filename, seq_name_raw, seq_name, project_name, domain, "
            "pipeline_name_override, status, imported_by, imported_at) "
            "VALUES (?, ?, ?, ?, ?, ?, 'pendente_aprovacao', ?, GETDATE())",
            [f"{project_name}.dsx", seq_decoded, seq_decoded, project_name, domain,
             pipeline_suggestion, imported_by],
        )
        cur.execute("SELECT MAX(id) FROM dbo.etl_seq_import")
        import_id = cur.fetchone()[0]

        engine = DSXEngine(dsx_base)
        jobs_preview = []
        for order, job_name in enumerate(jobs_in_order):
            cur.execute(
                "INSERT INTO dbo.etl_seq_import_job "
                "(import_id, execution_order, job_name_ds, job_name_orq, job_type, status) "
                "VALUES (?, ?, ?, ?, 'datastage', 'pendente')",
                [import_id, order, job_name, job_name],
            )
            cur.execute(
                "SELECT MAX(id) FROM dbo.etl_seq_import_job WHERE import_id=? AND execution_order=?",
                [import_id, order]
            )
            job_id = cur.fetchone()[0]

            lineage_result = engine.extrair(project_name, job_name)
            lineage_data, lineage_ok = [], False
            if lineage_result.get("sucesso"):
                lineage_ok   = True
                lineage_data = lineage_result.get("dados", [])
                for item in lineage_data:
                    cols = item.get("columns") or []
                    cols_json = json.dumps(cols, ensure_ascii=False) if cols else None
                    cur.execute(
                        "INSERT INTO dbo.etl_seq_import_lineage "
                        "(import_job_id, direction, object_name, object_type, stage_type_raw, "
                        "sql_expression, file_path, database_name, dsx_source_file, "
                        "extraction_method, columns_json, status) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'dsx_auto', ?, 'pendente')",
                        [job_id, item.get("direction"), item.get("object_name"),
                         item.get("object_type"), item.get("stage_type_raw"),
                         item.get("sql_expression"), item.get("file_path"),
                         item.get("database_name"), item.get("dsx_source_file"), cols_json],
                    )
                cur.execute(
                    "UPDATE dbo.etl_seq_import_job SET lineage_extracted=1, lineage_count=? WHERE id=?",
                    [len(lineage_data), job_id]
                )
            jobs_preview.append({"import_job_id": job_id, "execution_order": order,
                                  "job_name_ds": job_name, "job_name_orq": job_name,
                                  "lineage_extracted": lineage_ok, "lineage_count": len(lineage_data),
                                  "lineage": lineage_data})

        conn.commit(); cur.close(); conn.close()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao processar sequence: {e}")

    return {"import_id": import_id, "seq_name": seq_decoded, "project_name": project_name,
            "pipeline_name_suggestion": pipeline_suggestion,
            "jobs_count": len(jobs_in_order), "jobs": jobs_preview}


@router.post("/sequence/approve", tags=["sequence"])
async def sequence_approve(body: dict = Body(default={}), _auth: dict = Depends(require_perm(PERM_EDITAR))):
    """Aprova importação de sequence: move staging → tabelas principais (etl_sequence_import_approve)."""
    import_id    = int(body.get("import_id", 0))
    reviewed_by  = (body.get("reviewed_by") or "system").strip()
    if not import_id:
        raise HTTPException(status_code=422, detail="import_id é obrigatório")

    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute(
            "SELECT id, seq_name, project_name, status FROM dbo.etl_seq_import WHERE id = ?",
            (import_id,)
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"Importação id={import_id} não encontrada")
        if row[3] != "pendente_aprovacao":
            raise HTTPException(status_code=422,
                detail=f"Importação id={import_id} está com status '{row[3]}' e não pode ser aprovada")

        seq_name, project_name = row[1], row[2]
        pipeline_override = (body.get("pipeline_name_override") or "").strip() or None
        schedule_type     = (body.get("schedule_type") or "").strip() or None

        if pipeline_override or schedule_type:
            parts, params = [], []
            if pipeline_override:
                parts.append("pipeline_name_override = ?"); params.append(pipeline_override)
            if schedule_type:
                h   = int(body.get("schedule_hour",   6))
                m   = int(body.get("schedule_minute", 0))
                dow = body.get("schedule_dow")
                dom = body.get("schedule_dom")
                cron = _build_cron(schedule_type, h, m, dow, dom)
                parts += ["schedule_type = ?", "schedule_cron = ?",
                          "schedule_hour = ?", "schedule_minute = ?"]
                params += [schedule_type, cron, h, m]
                if dow is not None: parts.append("schedule_dow = ?"); params.append(int(dow))
                if dom is not None: parts.append("schedule_dom = ?"); params.append(int(dom))
            params.append(import_id)
            cur.execute(f"UPDATE dbo.etl_seq_import SET {', '.join(parts)} WHERE id = ?", params)

        cur.execute("EXEC dbo.sp_etl_seq_import_approve ?, ?", (import_id, reviewed_by))

        active           = int(body.get("active",           1))
        envia_msg_inicio = int(body.get("envia_msg_inicio", 1))
        envia_msg_fim    = int(body.get("envia_msg_fim",    1))
        envia_msg_erro   = int(body.get("envia_msg_erro",   1))
        dag_start_date   = (body.get("dag_start_date") or "").strip() or None

        cur.execute(
            "SELECT COALESCE(pipeline_name_override, seq_name) FROM dbo.etl_seq_import WHERE id = ?",
            (import_id,)
        )
        pipeline_name = (cur.fetchone() or [None])[0]

        if pipeline_name:
            extra_parts  = ["active=?","envia_msg_inicio=?","envia_msg_fim=?","envia_msg_erro=?","updated_at=GETDATE()"]
            extra_params = [active, envia_msg_inicio, envia_msg_fim, envia_msg_erro]
            if dag_start_date:
                extra_parts.append("dag_start_date=?"); extra_params.append(dag_start_date)
            extra_params.append(pipeline_name)
            cur.execute(f"UPDATE dbo.etl_pipeline SET {', '.join(extra_parts)} WHERE pipeline_name=?", extra_params)

            try:
                cur.execute(
                    """UPDATE jl SET jl.columns_json = sil.columns_json
                       FROM dbo.etl_job_lineage jl
                       JOIN dbo.etl_pipeline_job pj  ON pj.pipeline_name=jl.pipeline_name AND pj.job_name=jl.job_name
                       JOIN dbo.etl_seq_import_job sij ON sij.job_name_orq=pj.job_name AND sij.import_id=?
                       JOIN dbo.etl_seq_import_lineage sil ON sil.import_job_id=sij.id
                           AND sil.direction=jl.direction AND sil.object_name=jl.object_name
                       WHERE jl.pipeline_name=? AND sil.columns_json IS NOT NULL""",
                    [import_id, pipeline_name],
                )
            except Exception:
                pass

        conn.commit(); cur.close(); conn.close()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao aprovar sequence: {e}")

    return {"import_id": import_id, "pipeline_name": pipeline_name,
            "project_name": project_name, "status": "aprovado", "reviewed_by": reviewed_by}
