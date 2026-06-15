"""api/routers/lineage.py — GET /lineage, PUT /lineage/job, POST /lineage/extract-dsx, POST /lineage/normalize."""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Body, Depends, HTTPException

from db import get_db_conn
from deps import (
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


def _import_dsx_engine():
    """Importa o DSXEngine do pacote utils das DAGs (mesmo padrão de extract-dsx)."""
    import os, sys
    dags_folder = os.environ.get("DAGS_FOLDER", "/opt/airflow/dags")
    if dags_folder not in sys.path:
        sys.path.insert(0, dags_folder)
    try:
        from utils.dsx_engine import DSXEngine, _DEFAULT_DSX_DIR  # type: ignore
    except ImportError as e:
        raise HTTPException(status_code=500, detail=f"DSXEngine não disponível: {e}")
    return DSXEngine, _DEFAULT_DSX_DIR


def _safe_project_name(dsx: str) -> str:
    """Valida o nome do .dsx contra path traversal e devolve o nome de projeto."""
    name = (dsx or "").strip()
    if name.lower().endswith(".dsx"):
        name = name[:-4]
    if not name or "/" in name or "\\" in name or ".." in name:
        raise HTTPException(status_code=400, detail="Nome de DSX inválido.")
    return name


@router.get("/lineage", tags=["lineage"])
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


@router.put("/lineage/job", tags=["lineage"])
async def put_lineage_job(body: dict = Body(default={}), _auth: dict = Depends(require_perm(PERM_EDITAR))):
    """Substitui a lineage de um job: remove tudo e regrava o que veio no payload.

    Diferente da DAG etl_pipeline_job_register (upsert puro, nunca apaga),
    este endpoint permite editar e excluir entradas erradas pela UI.
    Body: { pipeline_name, job_name, origens: [], destinos: [], transformacoes: [] }
    """
    pipeline_name = (body.get("pipeline_name") or "").strip()
    job_name      = (body.get("job_name") or "").strip()
    if not pipeline_name or not job_name:
        raise HTTPException(status_code=422, detail="pipeline_name e job_name são obrigatórios")

    grupos = [("origem", body.get("origens") or []),
              ("transformacao", body.get("transformacoes") or []),
              ("destino", body.get("destinos") or [])]

    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute(
            "DELETE FROM dbo.etl_job_lineage WHERE pipeline_name = ? AND job_name = ?",
            [pipeline_name, job_name])
        removidos = cur.rowcount

        inseridos = 0
        for direction, objects in grupos:
            for obj in objects:
                obj_name = (obj.get("object_name") or "").strip()
                if not obj_name:
                    continue
                cols = obj.get("columns")
                columns_json = json.dumps(cols, ensure_ascii=False) if cols else None
                cur.execute(
                    """INSERT INTO dbo.etl_job_lineage
                       (pipeline_name, job_name, direction, object_type, object_name,
                        stage_name, stage_type_raw, database_name, sql_expression,
                        file_path, dsx_source_file, extraction_method, columns_json,
                        extracted_at, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, GETDATE(), GETDATE(), GETDATE())""",
                    [pipeline_name, job_name, direction,
                     (obj.get("object_type") or "Tabela").strip(), obj_name,
                     obj.get("stage_name"), obj.get("stage_type_raw"),
                     obj.get("database_name"), obj.get("sql_expression"),
                     obj.get("file_path"), obj.get("dsx_source_file"),
                     obj.get("extraction_method") or "manual", columns_json])
                inseridos += 1

        conn.commit()
        cur.close(); conn.close()
        return {"sucesso": True, "pipeline_name": pipeline_name, "job_name": job_name,
                "removidos": removidos, "inseridos": inseridos}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/lineage/extract-dsx", tags=["lineage"])
async def lineage_extract_dsx(body: dict = Body(default={}), _auth: dict = Depends(require_perm(PERM_EDITAR))):
    """Extrai lineage de um job DataStage a partir do arquivo .dsx (etl_lineage_extract_dsx)."""
    import os, sys
    project_name = (body.get("project_name") or "").strip()
    job_name     = (body.get("job_name") or "").strip()
    if not project_name or not job_name:
        raise HTTPException(status_code=422, detail="project_name e job_name são obrigatórios")

    dags_folder = os.environ.get("DAGS_FOLDER", "/opt/airflow/dags")
    if dags_folder not in sys.path:
        sys.path.insert(0, dags_folder)
    try:
        from utils.dsx_engine import DSXEngine, _DEFAULT_DSX_DIR  # type: ignore
    except ImportError as e:
        raise HTTPException(status_code=500, detail=f"DSXEngine não disponível: {e}")

    try:
        motor = DSXEngine(diretorio_base=_DEFAULT_DSX_DIR)
        resultado = motor.buscar_linhagem(nome_projeto=project_name, nome_job=job_name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao extrair DSX: {e}")

    if resultado.get("erro"):
        raise HTTPException(status_code=422, detail=resultado["erro"])

    dados = resultado.get("dados") or []
    return {"sucesso": True, "project_name": project_name, "job_name": job_name,
            "dsx_file": f"{project_name}.dsx", "dados": dados}


@router.get("/lineage/dsx-files", tags=["lineage"])
def list_dsx_files():
    """Lista os arquivos .dsx disponíveis para varredura (nome sem extensão)."""
    DSXEngine, base_dir = _import_dsx_engine()
    try:
        files = DSXEngine(diretorio_base=base_dir).listar_dsx()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao listar DSX: {e}")
    return {"base_dir": base_dir, "files": files}


@router.get("/lineage/dsx-folders", tags=["lineage"])
def list_dsx_folders(dsx: str):
    """Lista as pastas (Category) distintas de um .dsx, com a contagem de jobs."""
    project = _safe_project_name(dsx)
    DSXEngine, base_dir = _import_dsx_engine()
    try:
        resultado = DSXEngine(diretorio_base=base_dir).listar_pastas(project)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao listar pastas: {e}")
    if resultado.get("erro"):
        raise HTTPException(status_code=404, detail=resultado["erro"])
    return resultado


@router.get("/lineage/field-impact", tags=["lineage"])
def field_impact(dsx: str, campo: str, exato: bool = False,
                 tipo: str = "", excluir: bool = False,
                 incluir_bkp: bool = False, incluir_copy: bool = False,
                 alvo: str = "coluna", pasta: str = ""):
    """Impacto por campo: varre um .dsx (escolhido pelo nome exato) e retorna
    todos os jobs/stages cujas colunas casam com o termo (LIKE por padrão),
    com o datatype de cada coluna.

    Query params:
      dsx         — nome exato do arquivo .dsx (com ou sem extensão)
      campo       — termo do campo a procurar (busca substring case-insensitive)
      exato       — quando true, exige igualdade exata do nome da coluna
      tipo        — filtro de datatype: nomes separados por vírgula (ex.: VARCHAR,CHAR)
      excluir     — quando true, retorna colunas cujo tipo NÃO está em `tipo`
                    (ex.: tipo=VARCHAR,CHAR & excluir=true → campos que NÃO são texto)
      incluir_bkp — quando true, inclui jobs em pastas de backup (bkp/bckp/backup);
                    por padrão (false) esses jobs são ignorados
      incluir_copy— quando true, inclui jobs cópia (ex.: CopyOf...);
                    por padrão (false) esses jobs são ignorados
      alvo        — onde procurar: coluna (padrão) | tabela | arquivo | tabela_arquivo
      pasta       — restringe a jobs cuja pasta (Category) contém o texto (ex.: ML)
    """
    project = _safe_project_name(dsx)
    termo = (campo or "").strip()
    if not termo:
        raise HTTPException(status_code=400, detail="O parâmetro 'campo' é obrigatório.")

    tipos = [t.strip() for t in (tipo or "").split(",") if t.strip()]

    DSXEngine, base_dir = _import_dsx_engine()
    try:
        resultado = DSXEngine(diretorio_base=base_dir).buscar_campo(
            project_name=project, termo=termo, exato=exato,
            tipos=tipos, excluir=excluir,
            incluir_bkp=incluir_bkp, incluir_copy=incluir_copy,
            alvo=alvo, pasta=pasta)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao varrer DSX: {e}")

    if resultado.get("erro"):
        raise HTTPException(status_code=404, detail=resultado["erro"])
    return resultado


@router.post("/lineage/normalize", tags=["lineage"])
async def lineage_normalize(body: dict = Body(default={}), _auth: dict = Depends(require_perm(PERM_EDITAR))):
    """Normaliza lineage legado: object_name → tabela real (etl_lineage_normalize)."""
    pipeline_filter = (body.get("pipeline_name") or "").strip() or None
    dry_run = str(body.get("dry_run", "false")).lower() in ("true", "1", "yes")

    try:
        conn = get_db_conn(); cur = conn.cursor()
        where_extra = "AND l.pipeline_name = ?" if pipeline_filter else ""
        params = [pipeline_filter] if pipeline_filter else []

        cur.execute(
            f"""SELECT l.id, l.pipeline_name, l.job_name, l.direction, l.object_type,
                       l.stage_name, l.stage_type_raw, l.database_name, l.sql_expression,
                       l.file_path, l.dsx_source_file, l.extraction_method, l.columns_json, l.object_name
                FROM dbo.etl_job_lineage l
                WHERE l.sql_expression IS NOT NULL AND l.sql_expression <> ''
                  AND CHARINDEX(l.object_name, l.sql_expression) = 0
                  {where_extra}
                ORDER BY l.pipeline_name, l.job_name""",
            params if params else [],
        )
        rows = cur.fetchall()

        total_old, total_new, ids_to_del = 0, 0, []
        for row in rows:
            (rec_id, pip, job, direction, obj_type, stage_name, stage_type_raw,
             db_name, sql_expr, fp, dsx_src, extr_method, cols_json, obj_name) = row
            tables = [t.strip() for t in sql_expr.split("\n") if t.strip()]
            if not tables or obj_name.strip().lower() in {t.lower() for t in tables}:
                continue
            total_old += 1
            if not dry_run:
                for tbl in tables:
                    cur.execute(
                        """INSERT INTO dbo.etl_job_lineage
                           (pipeline_name, job_name, direction, object_type, object_name,
                            stage_name, stage_type_raw, database_name, sql_expression,
                            file_path, dsx_source_file, extraction_method, columns_json,
                            extracted_at, created_at, updated_at)
                           SELECT ?, ?, ?,
                               CASE WHEN CHARINDEX('.', ?) > 0 THEN 'Tabela' ELSE ISNULL(?,'Tabela') END,
                               ?, ?, ?, ?, ?, ?, ?, ?, ?, GETDATE(), GETDATE(), GETDATE()
                           WHERE NOT EXISTS (
                               SELECT 1 FROM dbo.etl_job_lineage
                               WHERE pipeline_name=? AND job_name=? AND direction=? AND object_name=?
                           )""",
                        [pip, job, direction, tbl, obj_type,
                         tbl, stage_name, stage_type_raw, db_name,
                         sql_expr, fp, dsx_src, extr_method, cols_json,
                         pip, job, direction, tbl],
                    )
                    total_new += 1
                ids_to_del.append(rec_id)

        if not dry_run and ids_to_del:
            for i in range(0, len(ids_to_del), 100):
                chunk = ids_to_del[i:i+100]
                cur.execute(f"DELETE FROM dbo.etl_job_lineage WHERE id IN ({','.join(['?']*len(chunk))})", chunk)
        if not dry_run:
            conn.commit()
        cur.close(); conn.close()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro DB: {e}")
    return {"dry_run": dry_run, "entradas_antigas": total_old,
            "entradas_novas": total_new, "removidas": len(ids_to_del)}
