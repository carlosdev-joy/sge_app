"""api/routers/lineage_xml.py — Lineage via export XML (DSX), read-only.

Extraído do antigo `malha_ds.py`: contém SOMENTE os endpoints de lineage que leem
o export XML <DSExport> do disco (sem persistir nada). A parte de "malha" (mesh)
persistida em etl_ds_malha* foi removida; isto aqui é a parte de DSX/lineage.

Endpoints (mesmos paths de antes — o frontend não muda):
  GET /malha-ds/xml-files                  — lista os exports .xml disponíveis no diretório
  GET /malha-ds/{project}/lineage-preview  — lineage do XML × lineage atual (etl_job_lineage), read-only
"""
from __future__ import annotations

import os
import sys

from fastapi import APIRouter, Depends, HTTPException

from db import managed_conn
from deps import get_current_user

router = APIRouter()

# Diretório dos exports XML (mesmo padrão do DSX; configurável)
_XML_BASE_DIR = os.environ.get("XML_BASE_DIR") or os.environ.get("DSX_BASE_DIR", "/opt/airflow/dsx")


def _safe_project(p: str) -> str:
    name = (p or "").strip()
    if name.lower().endswith(".xml"):
        name = name[:-4]
    if not name or "/" in name or "\\" in name or ".." in name:
        raise HTTPException(status_code=400, detail="Nome de projeto inválido.")
    return name


def _lineage_mod():
    """Importa o extrator de lineage do XML (apartado, em dags/utils)."""
    dags_folder = os.environ.get("DAGS_FOLDER", "/opt/airflow/dags")
    if dags_folder not in sys.path:
        sys.path.insert(0, dags_folder)
    try:
        from utils import ds_xml_lineage as LX  # type: ignore
        return LX
    except ImportError as e:
        raise HTTPException(status_code=500, detail=f"ds_xml_lineage indisponível: {e}")


_DIR2KEY = {"origem": "origens", "destino": "destinos", "transformacao": "transformacoes"}


@router.get("/malha-ds/xml-files", tags=["lineage"])
def list_xml_files(_auth: dict = Depends(get_current_user)):
    """Lista os exports .xml disponíveis no diretório (para a pessoa escolher)."""
    try:
        files = sorted((f[:-4] for f in os.listdir(_XML_BASE_DIR) if f.lower().endswith(".xml")),
                       key=str.lower)
    except OSError:
        files = []
    return {"base_dir": _XML_BASE_DIR, "files": files}


@router.get("/malha-ds/{project}/lineage-preview", tags=["lineage"])
def lineage_preview(project: str, _auth: dict = Depends(get_current_user)):
    """PREVIEW (somente leitura): extrai o lineage do export XML do projeto e devolve,
    por job, o lineage do **XML** + o lineage **ATUAL** (etl_job_lineage, DSX/manual)
    para COMPARAÇÃO na Governança. NÃO grava nada no banco."""
    project = _safe_project(project)
    path = os.path.join(_XML_BASE_DIR, f"{project}.xml")
    if not os.path.exists(path):
        raise HTTPException(status_code=404,
                            detail=f"Arquivo '{project}.xml' não encontrado em '{_XML_BASE_DIR}'.")
    LX = _lineage_mod()
    try:
        xml_lin = LX.extract_lineage(path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao extrair lineage do XML: {e}")

    jobs = sorted(xml_lin.keys())
    atual: dict = {}
    if jobs:
        with managed_conn() as (conn, cur):
            try:
                placeholders = ",".join("?" for _ in jobs)
                cur.execute(
                    "SELECT job_name, direction, object_name, object_type, stage_name, "
                    "stage_type_raw, database_name, sql_expression, file_path, extraction_method "
                    f"FROM dbo.etl_job_lineage WHERE job_name IN ({placeholders})", jobs)
                for r in cur.fetchall():
                    jn = r[0]
                    key = _DIR2KEY.get((r[1] or "").lower())
                    if not key:
                        continue
                    atual.setdefault(jn, {"origens": [], "destinos": [], "transformacoes": []})
                    atual[jn][key].append({
                        "object_name": r[2], "object_type": r[3], "stage_name": r[4],
                        "stage_type_raw": r[5], "database_name": r[6],
                        "sql_expression": r[7], "file_path": r[8], "extraction_method": r[9],
                    })
            except Exception:
                try: conn.rollback()
                except Exception: pass  # etl_job_lineage ausente/vazia → comparação só com XML

    empty = {"origens": [], "destinos": [], "transformacoes": []}
    items = [{"job_name": jn, "xml": xml_lin[jn], "atual": atual.get(jn, empty)} for jn in jobs]
    resumo = {k: sum(len(v[k]) for v in xml_lin.values())
              for k in ("origens", "destinos", "transformacoes")}
    return {"project": project, "jobs": len(jobs), "resumo": resumo, "items": items}
