"""api/routers/malha_ds.py — Malha DataStage persistida (a partir do export XML).

ROTA NOVA E APARTADA — não toca na tela/rota "Malha" do Orquestra nem na geração
de DAG. Parseia o export XML <DSExport> UMA vez e grava em etl_ds_malha* ; as
consultas leem do banco (sem reparsear o XML).

Endpoints:
  POST /malha-ds/import           — parseia o XML do projeto e grava a malha
  GET  /malha-ds                  — lista projetos com malha importada
  GET  /malha-ds/{project}        — malha do projeto (cabeçalho + árvore + raízes)
  GET  /malha-ds/{project}/jobs   — lista plana de jobs reais (para dsjob -jobinfo)
  DELETE /malha-ds/{project}      — remove a malha do projeto
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import sys

import httpx
from fastapi import APIRouter, Body, Depends, HTTPException

from db import managed_conn
from deps import (
    AIRFLOW_URL, AIRFLOW_USER, AIRFLOW_PASSWORD,
    PERM_EDITAR, PERM_EXECUTAR, get_current_user, require_perm,
)

router = APIRouter()

# Diretório dos exports XML (mesmo padrão do DSX; configurável)
_XML_BASE_DIR = os.environ.get("XML_BASE_DIR") or os.environ.get("DSX_BASE_DIR", "/opt/airflow/dsx")
_STATUS_DAG = "etl_ds_malha_status"


def _quem(user: dict) -> str:
    nome = " ".join(filter(None, [user.get("primeiro_nome"), user.get("ultimo_nome")])).strip()
    return nome or user.get("matricula") or "?"


def _safe_project(p: str) -> str:
    name = (p or "").strip()
    if name.lower().endswith(".xml"):
        name = name[:-4]
    if not name or "/" in name or "\\" in name or ".." in name:
        raise HTTPException(status_code=400, detail="Nome de projeto inválido.")
    return name


def _malha_mod():
    """Importa o módulo de parsing de malha (apartado, em dags/utils)."""
    dags_folder = os.environ.get("DAGS_FOLDER", "/opt/airflow/dags")
    if dags_folder not in sys.path:
        sys.path.insert(0, dags_folder)
    try:
        from utils import ds_xml_malha as M  # type: ignore
        return M
    except ImportError as e:
        raise HTTPException(status_code=500, detail=f"ds_xml_malha indisponível: {e}")


def _read_rows(cur, project: str):
    cur.execute("SELECT name, kind, is_sequence, is_executor, stage_types "
                "FROM dbo.etl_ds_malha_node WHERE project = ?", [project])
    nodes = [{
        "name": r[0], "kind": r[1], "is_sequence": bool(r[2]), "is_executor": bool(r[3]),
        "stage_types": json.loads(r[4]) if r[4] else [],
    } for r in cur.fetchall()]
    cur.execute("SELECT parent, seq_order, activity, jobname, real_target, kind "
                "FROM dbo.etl_ds_malha_edge WHERE project = ? ORDER BY parent, seq_order", [project])
    edges = [{
        "parent": r[0], "seq_order": r[1], "activity": r[2],
        "jobname": r[3], "real_target": r[4], "kind": r[5],
    } for r in cur.fetchall()]
    return nodes, edges


@router.post("/malha-ds/import", tags=["malha-ds"])
def import_malha(body: dict = Body(default={}), user: dict = Depends(require_perm(PERM_EDITAR))):
    """Parseia XML_BASE_DIR/<project>.xml e (re)grava a malha do projeto."""
    project = _safe_project(body.get("project") or "")
    path = os.path.join(_XML_BASE_DIR, f"{project}.xml")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"Arquivo '{project}.xml' não encontrado em '{_XML_BASE_DIR}'.")

    M = _malha_mod()
    try:
        parsed = M.parse_file(path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao parsear XML: {e}")
    if parsed.get("erro"):
        raise HTTPException(status_code=422, detail=parsed["erro"])

    rows = M.to_rows(parsed)

    try:
        with managed_conn() as (conn, cur):
            cur.execute("DELETE FROM dbo.etl_ds_malha_edge WHERE project = ?", [project])
            cur.execute("DELETE FROM dbo.etl_ds_malha_node WHERE project = ?", [project])
            cur.execute("DELETE FROM dbo.etl_ds_malha WHERE project = ?", [project])

            if rows["nodes"]:
                cur.executemany(
                    "INSERT INTO dbo.etl_ds_malha_node (project, name, kind, is_sequence, is_executor, stage_types) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    [[project, n["name"], n["kind"], 1 if n["is_sequence"] else 0,
                      1 if n["is_executor"] else 0, json.dumps(n["stage_types"], ensure_ascii=False)]
                     for n in rows["nodes"]])
            if rows["edges"]:
                cur.executemany(
                    "INSERT INTO dbo.etl_ds_malha_edge (project, parent, seq_order, activity, jobname, real_target, kind) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    [[project, e["parent"], e["seq_order"], e["activity"], e["jobname"], e["real_target"], e["kind"]]
                     for e in rows["edges"]])
            cur.execute(
                "INSERT INTO dbo.etl_ds_malha (project, server_name, ds_version, source_file, "
                "nodes_count, edges_count, imported_by) VALUES (?, ?, ?, ?, ?, ?, ?)",
                [project, rows["server"], rows["version"], f"{project}.xml",
                 len(rows["nodes"]), len(rows["edges"]), _quem(user)])
            conn.commit()
    except Exception as e:
        # Surfacing do erro real (ex.: tabelas ausentes → aplicar migration 028)
        raise HTTPException(status_code=500, detail=f"Erro ao gravar malha no banco: {e}")

    return {"sucesso": True, "project": project, "nodes": len(rows["nodes"]),
            "edges": len(rows["edges"]), "roots": rows["roots"]}


@router.get("/malha-ds", tags=["malha-ds"])
def list_malha(_auth: dict = Depends(get_current_user)):
    with managed_conn() as (conn, cur):
        cur.execute("SELECT project, server_name, ds_version, nodes_count, edges_count, "
                    "imported_by, imported_at FROM dbo.etl_ds_malha ORDER BY project")
        rows = cur.fetchall()
    return {"malhas": [{
        "project": r[0], "server_name": r[1], "ds_version": r[2],
        "nodes_count": r[3], "edges_count": r[4], "imported_by": r[5],
        "imported_at": r[6].strftime("%Y-%m-%d %H:%M:%S") if r[6] else None,
    } for r in rows]}


@router.get("/malha-ds/xml-files", tags=["malha-ds"])
def list_xml_files(_auth: dict = Depends(get_current_user)):
    """Lista os exports .xml disponíveis no diretório (para a pessoa escolher)."""
    try:
        files = sorted((f[:-4] for f in os.listdir(_XML_BASE_DIR) if f.lower().endswith(".xml")),
                       key=str.lower)
    except OSError:
        files = []
    return {"base_dir": _XML_BASE_DIR, "files": files}


@router.get("/malha-ds/{project}", tags=["malha-ds"])
def get_malha(project: str, root: str | None = None, _auth: dict = Depends(get_current_user)):
    project = _safe_project(project)
    M = _malha_mod()
    with managed_conn() as (conn, cur):
        cur.execute("SELECT project, server_name, ds_version, nodes_count, edges_count, "
                    "imported_by, imported_at FROM dbo.etl_ds_malha WHERE project = ?", [project])
        h = cur.fetchone()
        if not h:
            raise HTTPException(status_code=404, detail="Malha não importada para este projeto.")
        nodes, edges = _read_rows(cur, project)

    parsed = M.from_rows(nodes, edges, project=project)
    return {
        "malha": {"project": h[0], "server_name": h[1], "ds_version": h[2],
                  "nodes_count": h[3], "edges_count": h[4], "imported_by": h[5],
                  "imported_at": h[6].strftime("%Y-%m-%d %H:%M:%S") if h[6] else None},
        "roots": M.root_sequences(parsed),
        "tree":  M.build_tree(parsed, root),
    }


@router.get("/malha-ds/{project}/jobs", tags=["malha-ds"])
def get_malha_jobs(project: str, root: str | None = None, _auth: dict = Depends(get_current_user)):
    project = _safe_project(project)
    M = _malha_mod()
    with managed_conn() as (conn, cur):
        nodes, edges = _read_rows(cur, project)
    if not nodes:
        raise HTTPException(status_code=404, detail="Malha não importada para este projeto.")
    parsed = M.from_rows(nodes, edges, project=project)
    return {"project": project, "jobs": M.monitorable_jobs(parsed, root)}


@router.post("/malha-ds/{project}/scan", tags=["malha-ds"])
async def scan_malha(project: str, _auth: dict = Depends(require_perm(PERM_EXECUTAR))):
    """Dispara a varredura de status (dsjob -jobinfo) dos jobs da malha via Airflow."""
    project = _safe_project(project)
    run_id = f"malhastatus_{project}_{_dt.datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}"
    async with httpx.AsyncClient(base_url=AIRFLOW_URL, auth=(AIRFLOW_USER, AIRFLOW_PASSWORD), timeout=15) as client:
        r = await client.post(f"/api/v1/dags/{_STATUS_DAG}/dagRuns",
                              json={"dag_run_id": run_id, "conf": {"project": project}})
        if r.status_code not in (200, 201):
            raise HTTPException(status_code=r.status_code,
                                detail=f"Airflow recusou trigger: {r.text[:300]}")
    return {"status": "scan_disparado", "dag_run_id": run_id, "project": project}


@router.get("/malha-ds/{project}/status", tags=["malha-ds"])
def get_status(project: str, _auth: dict = Depends(get_current_user)):
    """Último snapshot de status por job (gravado pela DAG etl_ds_malha_status)."""
    project = _safe_project(project)
    with managed_conn() as (conn, cur):
        cur.execute("SELECT job_name, status_code, status_label, info, scanned_at "
                    "FROM dbo.etl_ds_malha_status WHERE project = ? ORDER BY job_name", [project])
        rows = cur.fetchall()
    jobs = [{
        "job_name": r[0], "status_code": r[1], "status_label": r[2], "info": r[3],
        "scanned_at": r[4].strftime("%Y-%m-%d %H:%M:%S") if r[4] else None,
    } for r in rows]
    summary: dict[str, int] = {}
    for j in jobs:
        k = j["status_label"] or "?"
        summary[k] = summary.get(k, 0) + 1
    return {"project": project, "scanned_at": jobs[0]["scanned_at"] if jobs else None,
            "summary": summary, "jobs": jobs}


@router.delete("/malha-ds/{project}", tags=["malha-ds"])
def delete_malha(project: str, _auth: dict = Depends(require_perm(PERM_EDITAR))):
    project = _safe_project(project)
    with managed_conn() as (conn, cur):
        cur.execute("DELETE FROM dbo.etl_ds_malha_edge WHERE project = ?", [project])
        cur.execute("DELETE FROM dbo.etl_ds_malha_node WHERE project = ?", [project])
        cur.execute("DELETE FROM dbo.etl_ds_malha WHERE project = ?", [project])
        affected = cur.rowcount
        conn.commit()
    if affected == 0:
        raise HTTPException(status_code=404, detail="Malha não encontrada.")
    return {"sucesso": True, "project": project}
