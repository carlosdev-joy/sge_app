"""
etl_catalogo_query.py
=====================
DAG do Catálogo de Dados — Governança ORQUESTRA.

Modos (conf.mode):

  search — busca por tabela/banco OU por arquivo
    Parâmetros:
      search_type  : 'tabela' | 'arquivo'   (default 'tabela')
      object_name  : str  — termo de busca tabela (LIKE, obrigatório se search_type=tabela)
      file_name    : str  — termo de busca arquivo (LIKE, obrigatório se search_type=arquivo)
      direction    : 'all' | 'origem' | 'destino'  (default 'all')
      database_name: str  — filtro exato de banco (opcional, só para search_type=tabela)

  ranking — top objetos mais utilizados
    Parâmetros:
      ranking_type : 'tabela' | 'arquivo'  (default 'tabela')
      top_n        : int  (default 15, max 50)

  list_pipelines — lista todos os pipelines cadastrados

  get_owner — retorna owner/steward de um pipeline
    Parâmetros:
      pipeline_name: str

  save_owner — salva/atualiza owner/steward de um pipeline
    Parâmetros:
      pipeline_name: str
      data         : dict {owner_name, owner_email, steward_name, steward_email}
      user         : str

  get_tags — retorna tags de um objeto
    Parâmetros:
      object_key: str

  save_tag — adiciona ou remove uma tag de um objeto
    Parâmetros:
      object_key: str
      tag       : str
      user      : str
      remove    : bool (default False)

  pipeline_history — histórico de importações de um pipeline
    Parâmetros:
      pipeline_name: str

  file_lineage — leitores/escritores de um arquivo
    Parâmetros:
      file_name: str

  overview — resumo geral do catálogo
    Retorna totais, classificações, top assets e alertas.

  browse — navegação/filtro de assets
    Parâmetros:
      search        : str  (opcional, LIKE)
      database_name : str  (opcional, filtro exato)
      asset_type    : 'tabela' | 'arquivo'  (opcional)
      classification: 'PII' | 'Confidencial' | 'Regulado' | 'Publico'  (opcional)
      top_n         : int  (default 100, max 200)

  list_projects — lista projetos ativos de dbo.etl_project

  list_job_types — lista tipos de job de dbo.etl_job_type
    Parâmetros:
      include_inactive: bool (default False) — inclui tipos inativos

  save_job_type — cria ou atualiza um tipo de job (admin)
    Parâmetros:
      data: dict {id?, nome, descricao?, lineage_enabled, status}
      user: str

  delete_job_type — remove um tipo de job (admin)
    Parâmetros:
      id: int

  asset_detail — detalhes de um asset específico
    Parâmetros:
      asset_name   : str  (obrigatório)
      asset_type   : 'tabela' | 'arquivo'
      database_name: str  (opcional)

  list_jobs_lineage — jobs e lineage de um pipeline
    Parâmetros:
      pipeline_name: str  (obrigatório)
"""
from __future__ import annotations

import json
import pendulum
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.microsoft.mssql.hooks.mssql import MsSqlHook

DAG_ID        = "etl_catalogo_query"
MSSQL_CONN_ID = "SQL14_DMDB41"
LOCAL_TZ      = "America/Sao_Paulo"

default_args = {"owner": "airflow", "depends_on_past": False, "retries": 0}

# ---------------------------------------------------------------------------
# CTE base para assets unificados (tabelas + arquivos)
# Usada por overview, browse e asset_detail.
# ---------------------------------------------------------------------------
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
            l.object_name,
            'tabela',
            ISNULL(l.database_name, ''),
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
            l.file_path,
            'arquivo',
            '',
            COUNT(DISTINCT l.pipeline_name),
            SUM(CASE WHEN l.direction = 'origem'  THEN 1 ELSE 0 END),
            SUM(CASE WHEN l.direction = 'destino' THEN 1 ELSE 0 END)
        FROM dbo.etl_job_lineage l
        WHERE l.file_path IS NOT NULL AND l.file_path <> ''
        GROUP BY l.file_path
    )
"""


def _build_pipeline_list(rows, col_names: list) -> tuple[list, int]:
    by_pipeline: dict[str, dict] = {}
    for row in rows:
        rec = dict(zip(col_names, row))
        pname = rec["pipeline_name"]
        if pname not in by_pipeline:
            by_pipeline[pname] = {
                "pipeline_name": pname,
                "project_name":  rec["project_name"],
                "domain":        rec["domain"],
                "active":        rec["active"],
                "ocorrencias":   0,
                "jobs":          [],
            }
        try:
            cols = json.loads(rec["columns_json"]) if rec["columns_json"] else []
        except Exception:
            cols = []
        by_pipeline[pname]["ocorrencias"] += 1
        by_pipeline[pname]["jobs"].append({
            "job_name":        rec["job_name"],
            "execution_order": rec["execution_order"],
            "job_type":        rec["job_type"],
            "direction":       rec["direction"],
            "object_name":     rec["object_name"],
            "object_type":     rec["object_type"],
            "database_name":   rec["database_name"],
            "file_path":       rec.get("file_path", ""),
            "stage_name":      rec["stage_name"],
            "columns":         cols,
        })
    pipelines = sorted(by_pipeline.values(), key=lambda x: x["pipeline_name"])
    total_occ = sum(p["ocorrencias"] for p in pipelines)
    return pipelines, total_occ


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
    "job_name", "execution_order", "job_type",
    "direction", "object_name", "object_type", "database_name", "file_path", "stage_name", "columns_json",
]


# ---------------------------------------------------------------------------
# Existing mode: search
# ---------------------------------------------------------------------------

def _search_tabela(hook, object_name: str, direction: str, database_name: str) -> dict:
    where = ["(l.sql_expression LIKE %s OR l.object_name LIKE %s)"]
    term = f"%{object_name}%"
    params: list = [term, term]

    if direction and direction != "all":
        where.append("l.direction = %s")
        params.append(direction)
    if database_name:
        where.append("l.database_name = %s")
        params.append(database_name)

    sql = f"""
        SELECT {_SELECT_COLS}
        {_JOIN_CLAUSE}
        WHERE {' AND '.join(where)}
        ORDER BY l.pipeline_name, pj.execution_order, l.direction, l.object_name
    """
    rows = hook.get_records(sql, parameters=params)
    pipelines, total_occ = _build_pipeline_list(rows, _COL_NAMES)

    print(f"[CATALOGO] tabela='{object_name}' dir='{direction}' db='{database_name}' "
          f"→ {len(pipelines)} pipeline(s), {total_occ} ocorrência(s)")
    return {
        "mode": "search", "search_type": "tabela",
        "term": object_name, "direction": direction, "database_name": database_name,
        "total_pipelines": len(pipelines), "total_ocorrencias": total_occ,
        "pipelines": pipelines,
    }


def _search_arquivo(hook, file_name: str, direction: str) -> dict:
    where = ["l.file_path LIKE %s", "l.file_path IS NOT NULL", "l.file_path <> ''"]
    params: list = [f"%{file_name}%"]

    if direction and direction != "all":
        where.append("l.direction = %s")
        params.append(direction)

    sql = f"""
        SELECT {_SELECT_COLS}
        {_JOIN_CLAUSE}
        WHERE {' AND '.join(where)}
        ORDER BY l.pipeline_name, pj.execution_order, l.direction, l.file_path
    """
    rows = hook.get_records(sql, parameters=params)
    pipelines, total_occ = _build_pipeline_list(rows, _COL_NAMES)

    print(f"[CATALOGO] arquivo='{file_name}' dir='{direction}' "
          f"→ {len(pipelines)} pipeline(s), {total_occ} ocorrência(s)")
    return {
        "mode": "search", "search_type": "arquivo",
        "term": file_name, "direction": direction,
        "total_pipelines": len(pipelines), "total_ocorrencias": total_occ,
        "pipelines": pipelines,
    }


# ---------------------------------------------------------------------------
# Existing mode: ranking
# ---------------------------------------------------------------------------

def _ranking_tabela(hook, top_n: int) -> dict:
    sql = f"""
        SELECT TOP {top_n}
            tbl_name,
            ISNULL(database_name, '') AS database_name,
            COUNT(DISTINCT pipeline_name)                           AS pipeline_count,
            COUNT(DISTINCT job_name)                                AS job_count,
            SUM(CASE WHEN direction = 'origem'  THEN 1 ELSE 0 END) AS as_origem,
            SUM(CASE WHEN direction = 'destino' THEN 1 ELSE 0 END) AS as_destino
        FROM (
            SELECT
                LTRIM(RTRIM(s.value)) AS tbl_name,
                l.database_name,
                l.pipeline_name,
                l.job_name,
                l.direction
            FROM dbo.etl_job_lineage l
            CROSS APPLY STRING_SPLIT(l.sql_expression, CHAR(10)) s
            WHERE l.direction IN ('origem', 'destino')
              AND (l.file_path IS NULL OR l.file_path = '')
              AND l.sql_expression IS NOT NULL AND l.sql_expression <> ''
              AND LTRIM(RTRIM(s.value)) <> ''

            UNION ALL

            SELECT
                l.object_name AS tbl_name,
                l.database_name,
                l.pipeline_name,
                l.job_name,
                l.direction
            FROM dbo.etl_job_lineage l
            WHERE l.direction IN ('origem', 'destino')
              AND (l.file_path IS NULL OR l.file_path = '')
              AND (l.sql_expression IS NULL OR l.sql_expression = '')
              AND l.object_name IS NOT NULL AND l.object_name <> ''
        ) x
        GROUP BY tbl_name, database_name
        ORDER BY COUNT(DISTINCT pipeline_name) DESC, tbl_name
    """
    rows = hook.get_records(sql)
    cols = ["object_name", "database_name", "pipeline_count", "job_count", "as_origem", "as_destino"]
    data = [dict(zip(cols, row)) for row in rows]
    print(f"[CATALOGO] ranking tabela top={top_n} → {len(data)} objeto(s)")
    return {"mode": "ranking", "ranking_type": "tabela", "data": data}


def _ranking_arquivo(hook, top_n: int) -> dict:
    sql = f"""
        SELECT TOP {top_n}
            l.file_path,
            COUNT(DISTINCT l.pipeline_name)                           AS pipeline_count,
            COUNT(DISTINCT l.job_name)                                AS job_count,
            SUM(CASE WHEN l.direction = 'origem'  THEN 1 ELSE 0 END) AS as_origem,
            SUM(CASE WHEN l.direction = 'destino' THEN 1 ELSE 0 END) AS as_destino
        FROM dbo.etl_job_lineage l
        WHERE l.direction IN ('origem', 'destino')
          AND l.file_path IS NOT NULL AND l.file_path <> ''
        GROUP BY l.file_path
        ORDER BY COUNT(DISTINCT l.pipeline_name) DESC, l.file_path
    """
    rows = hook.get_records(sql)
    cols = ["file_path", "pipeline_count", "job_count", "as_origem", "as_destino"]
    data = [dict(zip(cols, row)) for row in rows]
    print(f"[CATALOGO] ranking arquivo top={top_n} → {len(data)} objeto(s)")
    return {"mode": "ranking", "ranking_type": "arquivo", "data": data}


# ---------------------------------------------------------------------------
# Existing modes: owner, tags, history, lineage, list
# ---------------------------------------------------------------------------

def _get_owner(hook, pipeline_name: str) -> dict:
    sql = """
        SELECT owner_name, owner_email, steward_name, steward_email, updated_at, updated_by
        FROM dbo.etl_pipeline_owner WHERE pipeline_name = %s
    """
    rows = hook.get_records(sql, parameters=[pipeline_name])
    if rows:
        r = rows[0]
        return {"pipeline_name": pipeline_name,
                "owner_name": r[0], "owner_email": r[1],
                "steward_name": r[2], "steward_email": r[3],
                "updated_at": str(r[4]) if r[4] else None, "updated_by": r[5]}
    return {"pipeline_name": pipeline_name}


def _save_owner(hook, pipeline_name: str, data: dict, user: str) -> dict:
    sql = """
        MERGE dbo.etl_pipeline_owner AS tgt
        USING (SELECT %s AS pipeline_name) AS src ON tgt.pipeline_name = src.pipeline_name
        WHEN MATCHED THEN UPDATE SET
            owner_name=%s, owner_email=%s, steward_name=%s, steward_email=%s,
            updated_at=GETDATE(), updated_by=%s
        WHEN NOT MATCHED THEN INSERT (pipeline_name,owner_name,owner_email,steward_name,steward_email,updated_at,updated_by)
            VALUES (%s,%s,%s,%s,%s,GETDATE(),%s);
    """
    hook.run(sql, parameters=[
        pipeline_name,
        data.get("owner_name"), data.get("owner_email"),
        data.get("steward_name"), data.get("steward_email"), user,
        pipeline_name,
        data.get("owner_name"), data.get("owner_email"),
        data.get("steward_name"), data.get("steward_email"), user,
    ])
    return {"ok": True, "pipeline_name": pipeline_name}


def _get_tags(hook, object_key: str) -> dict:
    sql = "SELECT tag, added_by, added_at FROM dbo.etl_object_tag WHERE object_key = %s ORDER BY tag"
    rows = hook.get_records(sql, parameters=[object_key])
    return {"object_key": object_key,
            "tags": [{"tag": r[0], "added_by": r[1], "added_at": str(r[2])} for r in rows]}


def _save_tag(hook, object_key: str, tag: str, user: str, remove: bool) -> dict:
    if remove:
        hook.run("DELETE FROM dbo.etl_object_tag WHERE object_key=%s AND tag=%s", parameters=[object_key, tag])
    else:
        hook.run("""
            IF NOT EXISTS (SELECT 1 FROM dbo.etl_object_tag WHERE object_key=%s AND tag=%s)
                INSERT INTO dbo.etl_object_tag (object_key, tag, added_by) VALUES (%s, %s, %s)
        """, parameters=[object_key, tag, object_key, tag, user])
    return {"ok": True}


def _pipeline_history(hook, pipeline_name: str) -> dict:
    sql = """
        SELECT TOP 20
            created_at   AS imported_at,
            status,
            reviewed_by,
            reviewed_at,
            LEFT(ISNULL(obs, ''), 120) AS obs
        FROM dbo.etl_seq_import
        WHERE seq_name = %s OR pipeline_name_override = %s
        ORDER BY created_at DESC
    """
    rows = hook.get_records(sql, parameters=[pipeline_name, pipeline_name])
    cols = ["imported_at", "status", "reviewed_by", "reviewed_at", "obs"]
    history = []
    for r in rows:
        rec = dict(zip(cols, r))
        rec["imported_at"] = str(rec["imported_at"]) if rec["imported_at"] else None
        rec["reviewed_at"] = str(rec["reviewed_at"]) if rec["reviewed_at"] else None
        history.append(rec)
    return {"mode": "pipeline_history", "pipeline_name": pipeline_name, "history": history}


def _file_lineage(hook, file_name: str) -> dict:
    sql = """
        SELECT l.pipeline_name, l.job_name, l.direction
        FROM dbo.etl_job_lineage l
        WHERE l.file_path LIKE %s
          AND l.direction IN ('origem', 'destino')
        ORDER BY l.direction, l.pipeline_name
    """
    rows = hook.get_records(sql, parameters=[f"%{file_name}%"])
    writers = [{"pipeline_name": r[0], "job_name": r[1]} for r in rows if r[2] == "destino"]
    readers = [{"pipeline_name": r[0], "job_name": r[1]} for r in rows if r[2] == "origem"]
    return {"mode": "file_lineage", "file_name": file_name, "writers": writers, "readers": readers}


def _list_pipelines(hook) -> dict:
    sql = "SELECT pipeline_name FROM dbo.etl_pipeline ORDER BY pipeline_name"
    rows = hook.get_records(sql)
    names = [r[0] for r in rows]
    print(f"[CATALOGO] list_pipelines → {len(names)} pipeline(s)")
    return {"mode": "list_pipelines", "pipelines": names}


# ---------------------------------------------------------------------------
# New mode: overview
# ---------------------------------------------------------------------------

def _overview(hook) -> dict:
    # Total distinct assets
    sql_total_assets = f"""
        {_ASSETS_CTE}
        SELECT COUNT(*) FROM (
            SELECT asset_name, asset_type, database_name
            FROM assets
            GROUP BY asset_name, asset_type, database_name
        ) sub
    """
    total_assets: int = hook.get_first(sql_total_assets)[0]

    # Total pipelines
    total_pipelines: int = hook.get_first(
        "SELECT COUNT(*) FROM dbo.etl_pipeline"
    )[0]

    # Total pipelines with at least one owner
    total_with_owner: int = hook.get_first(
        "SELECT COUNT(DISTINCT pipeline_name) FROM dbo.etl_pipeline_owner"
    )[0]

    # Classification counts (distinct object_keys per tag)
    sql_class = """
        SELECT
            SUM(CASE WHEN tag = 'PII'          THEN 1 ELSE 0 END) AS pii,
            SUM(CASE WHEN tag = 'Confidencial' THEN 1 ELSE 0 END) AS confidencial,
            SUM(CASE WHEN tag = 'Regulado'     THEN 1 ELSE 0 END) AS regulado,
            SUM(CASE WHEN tag = 'Publico'      THEN 1 ELSE 0 END) AS publico
        FROM (
            SELECT tag, object_key
            FROM dbo.etl_object_tag
            WHERE tag IN ('PII', 'Confidencial', 'Regulado', 'Publico')
            GROUP BY tag, object_key
        ) sub
    """
    row_class = hook.get_first(sql_class) or (0, 0, 0, 0)
    classification_counts = {
        "pii":          int(row_class[0] or 0),
        "confidencial": int(row_class[1] or 0),
        "regulado":     int(row_class[2] or 0),
        "publico":      int(row_class[3] or 0),
    }

    # Top 15 assets
    sql_top = f"""
        {_ASSETS_CTE}
        SELECT TOP 15
            asset_name, asset_type, database_name,
            SUM(pipeline_count) AS pipeline_count,
            SUM(as_origem)      AS as_origem,
            SUM(as_destino)     AS as_destino
        FROM assets
        GROUP BY asset_name, asset_type, database_name
        ORDER BY SUM(pipeline_count) DESC
    """
    rows_top = hook.get_records(sql_top)
    top_cols = ["asset_name", "asset_type", "database_name", "pipeline_count", "as_origem", "as_destino"]
    top_assets = [dict(zip(top_cols, r)) for r in rows_top]

    # Alerts: pipelines without owner (limit 5)
    sql_no_owner = """
        SELECT TOP 5 pipeline_name
        FROM dbo.etl_pipeline
        WHERE pipeline_name NOT IN (
            SELECT DISTINCT pipeline_name FROM dbo.etl_pipeline_owner
        )
        ORDER BY pipeline_name
    """
    rows_no_owner = hook.get_records(sql_no_owner)
    alerts = [
        {"type": "pipeline_sem_owner", "message": f"Pipeline sem owner: {r[0]}"}
        for r in rows_no_owner
    ]

    # Alerts: PII/Regulado assets without an owner on any pipeline that uses them (limit 5)
    sql_pii_no_owner = """
        SELECT TOP 5 ot.object_key
        FROM dbo.etl_object_tag ot
        WHERE ot.tag IN ('PII', 'Regulado')
          AND NOT EXISTS (
              SELECT 1
              FROM dbo.etl_job_lineage l
              JOIN dbo.etl_pipeline_owner po ON po.pipeline_name = l.pipeline_name
              WHERE l.object_name = ot.object_key
                 OR l.file_path   = ot.object_key
                 OR (l.database_name + '.' + l.object_name) = ot.object_key
          )
        GROUP BY ot.object_key
        ORDER BY ot.object_key
    """
    rows_pii = hook.get_records(sql_pii_no_owner)
    for r in rows_pii:
        alerts.append({"type": "pii_sem_owner", "message": f"Asset PII/Regulado sem owner: {r[0]}"})

    print(f"[CATALOGO] overview → assets={total_assets} pipelines={total_pipelines} "
          f"with_owner={total_with_owner} alerts={len(alerts)}")
    return {
        "mode": "overview",
        "total_assets": total_assets,
        "total_pipelines": total_pipelines,
        "total_with_owner": total_with_owner,
        "classification_counts": classification_counts,
        "top_assets": top_assets,
        "alerts": alerts,
    }


# ---------------------------------------------------------------------------
# New mode: browse
# ---------------------------------------------------------------------------

def _browse(hook, search: str, database_name: str, asset_type: str,
            classification: str, top_n: int) -> dict:
    top_n = min(200, max(1, top_n))

    where_clauses: list[str] = []
    params: list = []

    if search:
        where_clauses.append("a.asset_name LIKE %s")
        params.append(f"%{search}%")
    if database_name:
        where_clauses.append("a.database_name = %s")
        params.append(database_name)
    if asset_type:
        where_clauses.append("a.asset_type = %s")
        params.append(asset_type)

    where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

    if classification:
        # Join to etl_object_tag; object_key is database_name.asset_name for tables, asset_name for files
        sql = f"""
            {_ASSETS_CTE}
            SELECT TOP {top_n}
                a.asset_name, a.asset_type, a.database_name,
                SUM(a.pipeline_count) AS pipeline_count,
                SUM(a.as_origem)      AS as_origem,
                SUM(a.as_destino)     AS as_destino
            FROM assets a
            JOIN dbo.etl_object_tag ot
              ON ot.tag = %s
             AND (
                   (a.asset_type = 'tabela'  AND ot.object_key = a.database_name + '.' + a.asset_name)
                OR (a.asset_type = 'tabela'  AND ot.object_key = a.asset_name)
                OR (a.asset_type = 'arquivo' AND ot.object_key = a.asset_name)
             )
            {where_sql}
            GROUP BY a.asset_name, a.asset_type, a.database_name
            ORDER BY SUM(a.pipeline_count) DESC, a.asset_name
        """
        params = [classification] + params
    else:
        sql = f"""
            {_ASSETS_CTE}
            SELECT TOP {top_n}
                a.asset_name, a.asset_type, a.database_name,
                SUM(a.pipeline_count) AS pipeline_count,
                SUM(a.as_origem)      AS as_origem,
                SUM(a.as_destino)     AS as_destino
            FROM assets a
            {where_sql}
            GROUP BY a.asset_name, a.asset_type, a.database_name
            ORDER BY SUM(a.pipeline_count) DESC, a.asset_name
        """

    rows = hook.get_records(sql, parameters=params if params else None)
    asset_cols = ["asset_name", "asset_type", "database_name", "pipeline_count", "as_origem", "as_destino"]
    assets = [dict(zip(asset_cols, r)) for r in rows]

    # Facets — computed independently (no top_n limit, no filters applied)
    sql_facets_db = f"""
        {_ASSETS_CTE}
        SELECT DISTINCT database_name FROM assets WHERE database_name <> '' ORDER BY database_name
    """
    sql_facets_type = f"""
        {_ASSETS_CTE}
        SELECT DISTINCT asset_type FROM assets ORDER BY asset_type
    """
    sql_facets_class = """
        SELECT DISTINCT tag FROM dbo.etl_object_tag
        WHERE tag IN ('PII', 'Confidencial', 'Regulado', 'Publico')
        ORDER BY tag
    """
    databases      = [r[0] for r in hook.get_records(sql_facets_db)]
    types          = [r[0] for r in hook.get_records(sql_facets_type)]
    classifications = [r[0] for r in hook.get_records(sql_facets_class)]

    print(f"[CATALOGO] browse → {len(assets)} asset(s) returned (top_n={top_n})")
    return {
        "mode": "browse",
        "assets": assets,
        "facets": {
            "databases":       databases,
            "types":           types,
            "classifications": classifications,
        },
    }


# ---------------------------------------------------------------------------
# New mode: asset_detail
# ---------------------------------------------------------------------------

def _asset_detail(hook, asset_name: str, asset_type: str, database_name: str) -> dict:
    asset_type = (asset_type or "tabela").strip().lower()

    if asset_type == "arquivo":
        where_lineage = "l.file_path = %s"
        params_lineage: list = [asset_name]
    else:
        where_lineage = "(l.sql_expression LIKE %s OR l.object_name = %s)"
        params_lineage = [f"%{asset_name}%", asset_name]
        if database_name:
            where_lineage += " AND l.database_name = %s"
            params_lineage.append(database_name)

    sql_lineage = f"""
        SELECT
            l.pipeline_name,
            l.job_name,
            CAST(pj.execution_order AS INT) AS execution_order,
            l.columns_json,
            l.direction,
            ISNULL(l.sql_expression, '') AS sql_expression
        FROM dbo.etl_job_lineage l
        JOIN dbo.etl_pipeline_job pj
          ON pj.pipeline_name = l.pipeline_name AND pj.job_name = l.job_name
        WHERE {where_lineage}
        ORDER BY l.direction, l.pipeline_name, pj.execution_order
    """
    rows_lineage = hook.get_records(sql_lineage, parameters=params_lineage)

    pipelines_origem: list[dict] = []
    pipelines_destino: list[dict] = []
    all_columns: list[str] = []
    first_sql: str = ""

    for r in rows_lineage:
        p_name, j_name, exec_order, cols_json, direction, sql_expr = r
        try:
            cols = json.loads(cols_json) if cols_json else []
        except Exception:
            cols = []
        all_columns.extend(cols)
        if not first_sql and sql_expr:
            first_sql = sql_expr
        entry = {
            "pipeline_name":   p_name,
            "job_name":        j_name,
            "execution_order": exec_order,
            "columns_json":    cols_json or "",
        }
        if direction == "origem":
            pipelines_origem.append(entry)
        else:
            pipelines_destino.append(entry)

    # Unique column names preserving first-seen order
    seen: set = set()
    unique_columns: list[str] = []
    for c in all_columns:
        if c not in seen:
            seen.add(c)
            unique_columns.append(c)

    # Tags for this asset
    if asset_type == "arquivo":
        object_key_candidates = [asset_name]
    else:
        object_key_candidates = [
            f"{database_name}.{asset_name}" if database_name else asset_name,
            asset_name,
        ]

    tags: list[str] = []
    seen_tags: set = set()
    for ok in object_key_candidates:
        rows_tags = hook.get_records(
            "SELECT tag FROM dbo.etl_object_tag WHERE object_key = %s ORDER BY tag",
            parameters=[ok],
        )
        for rt in rows_tags:
            if rt[0] not in seen_tags:
                seen_tags.add(rt[0])
                tags.append(rt[0])

    print(f"[CATALOGO] asset_detail asset='{asset_name}' type='{asset_type}' "
          f"→ origem={len(pipelines_origem)} destino={len(pipelines_destino)}")
    return {
        "mode": "asset_detail",
        "asset_name":        asset_name,
        "asset_type":        asset_type,
        "database_name":     database_name or "",
        "pipelines_origem":  pipelines_origem,
        "pipelines_destino": pipelines_destino,
        "columns":           unique_columns,
        "tags":              tags,
        "sql_expression":    first_sql,
    }


# ---------------------------------------------------------------------------
# Projects + Job Types
# ---------------------------------------------------------------------------

def _list_projects(hook):
    try:
        rows = hook.get_records(
            "SELECT project_name, ativo FROM dbo.etl_project ORDER BY project_name"
        )
        return {"projects": [{"project_name": r[0], "ativo": r[1]} for r in rows]}
    except Exception:
        return {"projects": [
            {"project_name": "BI_CVP",         "ativo": 1},
            {"project_name": "BI_VIDA",         "ativo": 1},
            {"project_name": "BI_PRESTAMISTA",  "ativo": 1},
            {"project_name": "BI_PREVIDENCIA",  "ativo": 1},
        ]}


def _list_job_types(hook, include_inactive: bool = False):
    where = "" if include_inactive else "WHERE status = 1"
    rows = hook.get_records(
        f"SELECT id, nome, descricao, lineage_enabled, status FROM dbo.etl_job_type {where} ORDER BY nome"
    )
    return {"job_types": [
        {"id": r[0], "nome": r[1], "descricao": r[2], "lineage_enabled": bool(r[3]), "status": bool(r[4])}
        for r in rows
    ]}


def _save_job_type(hook, data: dict, user: str):
    jt_id       = data.get("id")
    nome        = (data.get("nome") or "").strip()
    descricao   = (data.get("descricao") or "").strip() or None
    lineage_en  = 1 if data.get("lineage_enabled") else 0
    status      = 1 if data.get("status", True) else 0

    if not nome:
        raise ValueError("Campo 'nome' é obrigatório para salvar tipo de job.")

    if jt_id:
        hook.run(
            "UPDATE dbo.etl_job_type SET nome=%s, descricao=%s, lineage_enabled=%s, status=%s "
            "WHERE id=%s",
            parameters=(nome, descricao, lineage_en, status, int(jt_id)),
        )
        return {"ok": True, "action": "updated", "id": int(jt_id)}
    else:
        hook.run(
            "INSERT INTO dbo.etl_job_type (nome, descricao, lineage_enabled, status, criado_por) "
            "VALUES (%s, %s, %s, %s, %s)",
            parameters=(nome, descricao, lineage_en, status, user),
        )
        row = hook.get_first("SELECT MAX(id) FROM dbo.etl_job_type WHERE nome=%s", parameters=(nome,))
        return {"ok": True, "action": "created", "id": row[0] if row else None}


def _delete_job_type(hook, jt_id: int):
    hook.run("DELETE FROM dbo.etl_job_type WHERE id=%s", parameters=(jt_id,))
    return {"ok": True, "action": "deleted", "id": jt_id}


def _list_jobs_lineage(hook, pipeline_name: str):
    """Retorna jobs e lineage de um pipeline específico."""
    if not pipeline_name:
        return {"jobs": []}

    # Busca jobs do pipeline
    job_rows = hook.get_records(
        """
        SELECT
            pj.job_name,
            CAST(pj.execution_order AS INT) AS execution_order,
            pj.job_type,
            ISNULL(pj.job_command, '')     AS job_command
        FROM dbo.etl_pipeline_job pj
        WHERE pj.pipeline_name = %s
        ORDER BY pj.execution_order, pj.job_name
        """,
        parameters=[pipeline_name],
    )

    # Busca lineage de todos os jobs do pipeline numa só query
    lin_rows = hook.get_records(
        """
        SELECT
            l.job_name,
            ISNULL(stm.type_label, l.object_type) AS object_type,
            l.object_name,
            l.direction
        FROM dbo.etl_job_lineage l
        LEFT JOIN dbo.etl_stage_type_map stm ON stm.type_raw = l.object_type
        WHERE l.pipeline_name = %s
          AND l.object_name IS NOT NULL AND l.object_name <> ''
        ORDER BY l.job_name, l.direction, l.object_type, l.object_name
        """,
        parameters=[pipeline_name],
    )

    # Agrupa lineage por job
    lineage_map: dict = {}
    for r in lin_rows:
        jn, otype, oname, direction = r
        if jn not in lineage_map:
            lineage_map[jn] = {"origens": [], "destinos": []}
        entry = {"tipo": otype or "", "nome": oname or ""}
        if direction == "origem":
            lineage_map[jn]["origens"].append(entry)
        else:
            lineage_map[jn]["destinos"].append(entry)

    job_list = []
    for row in job_rows:
        job_name, order, job_type, cmd = row
        lg = lineage_map.get(job_name, {"origens": [], "destinos": []})
        job_list.append({
            "job_name":        job_name,
            "execution_order": order,
            "job_type":        job_type or "",
            "job_command":     cmd or "",
            "origens":         lg["origens"],
            "destinos":        lg["destinos"],
        })

    return {"pipeline_name": pipeline_name, "jobs": job_list}


# ---------------------------------------------------------------------------
# Main callable
# ---------------------------------------------------------------------------

def consultar_catalogo(**context):
    conf = context["dag_run"].conf or {}
    mode = (conf.get("mode") or "search").strip().lower()
    hook = MsSqlHook(mssql_conn_id=MSSQL_CONN_ID)

    if mode == "list_projects":
        return _list_projects(hook)

    if mode == "list_job_types":
        include_inactive = bool(conf.get("include_inactive", False))
        return _list_job_types(hook, include_inactive)

    if mode == "save_job_type":
        return _save_job_type(hook, conf.get("data", {}), conf.get("user", "admin"))

    if mode == "delete_job_type":
        jt_id = int(conf.get("id", 0))
        if not jt_id:
            raise ValueError("Parâmetro 'id' é obrigatório para mode=delete_job_type.")
        return _delete_job_type(hook, jt_id)

    if mode == "list_jobs_lineage":
        return _list_jobs_lineage(hook, conf.get("pipeline_name", ""))

    if mode == "list_pipelines":
        return _list_pipelines(hook)

    if mode == "get_owner":
        return _get_owner(hook, conf.get("pipeline_name", ""))

    if mode == "save_owner":
        return _save_owner(hook, conf.get("pipeline_name", ""),
                           conf.get("data", {}), conf.get("user", "sistema"))

    if mode == "get_tags":
        return _get_tags(hook, conf.get("object_key", ""))

    if mode == "save_tag":
        return _save_tag(hook, conf.get("object_key", ""),
                         conf.get("tag", ""), conf.get("user", "sistema"),
                         bool(conf.get("remove", False)))

    if mode == "pipeline_history":
        return _pipeline_history(hook, conf.get("pipeline_name", ""))

    if mode == "file_lineage":
        return _file_lineage(hook, conf.get("file_name", ""))

    if mode == "ranking":
        top_n        = min(50, max(1, int(conf.get("top_n", 15))))
        ranking_type = (conf.get("ranking_type") or "tabela").strip().lower()
        if ranking_type == "arquivo":
            return _ranking_arquivo(hook, top_n)
        return _ranking_tabela(hook, top_n)

    if mode == "overview":
        return _overview(hook)

    if mode == "browse":
        return _browse(
            hook,
            search=       (conf.get("search")        or "").strip(),
            database_name=(conf.get("database_name") or "").strip(),
            asset_type=   (conf.get("asset_type")    or "").strip().lower(),
            classification=(conf.get("classification") or "").strip(),
            top_n=        int(conf.get("top_n", 100)),
        )

    if mode == "asset_detail":
        asset_name = (conf.get("asset_name") or "").strip()
        if not asset_name:
            raise ValueError("Parâmetro 'asset_name' é obrigatório para mode=asset_detail.")
        return _asset_detail(
            hook,
            asset_name=   asset_name,
            asset_type=   (conf.get("asset_type")    or "tabela").strip().lower(),
            database_name=(conf.get("database_name") or "").strip(),
        )

    # mode == "search"
    search_type   = (conf.get("search_type") or "tabela").strip().lower()
    direction     = (conf.get("direction")    or "all").strip().lower()

    if search_type == "arquivo":
        file_name = (conf.get("file_name") or "").strip()
        if not file_name:
            raise ValueError("Parâmetro 'file_name' é obrigatório para search_type=arquivo.")
        return _search_arquivo(hook, file_name, direction)

    object_name   = (conf.get("object_name")   or "").strip()
    database_name = (conf.get("database_name") or "").strip()
    if not object_name:
        raise ValueError("Parâmetro 'object_name' é obrigatório para search_type=tabela.")
    return _search_tabela(hook, object_name, direction, database_name)


# ---------------------------------------------------------------------------
# DAG definition
# ---------------------------------------------------------------------------

with DAG(
    dag_id=DAG_ID,
    default_args=default_args,
    description="Catálogo de dados — busca por tabela/arquivo e ranking",
    start_date=pendulum.datetime(2024, 1, 1, tz=LOCAL_TZ),
    schedule=None,
    catchup=False,
    tags=["governanca", "catalogo", "lineage"],
    access_control={"Op": {"can_read", "can_edit"}},
) as dag:

    PythonOperator(
        task_id="consultar_catalogo",
        python_callable=consultar_catalogo,
        do_xcom_push=True,
    )
