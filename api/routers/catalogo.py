"""api/routers/catalogo.py — POST /catalogo."""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Body, HTTPException

from api.db import get_db_conn

log = logging.getLogger("orquestra-api")

router = APIRouter()

# ── SQL helpers ───────────────────────────────────────────────────────────────

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


@router.post("/catalogo", tags=["catalogo"])
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
        log.exception("catalogo mode=%s error=%s", mode, e)
        raise HTTPException(status_code=500, detail=str(e))
