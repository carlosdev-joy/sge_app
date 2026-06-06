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


def _search_tabela(hook, object_name: str, direction: str, database_name: str) -> dict:
    # Busca em sql_expression (tabelas reais do SQL) OU object_name (nome do stage)
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


def _ranking_tabela(hook, top_n: int) -> dict:
    # Usa STRING_SPLIT para extrair cada tabela individual do sql_expression
    # (armazenado como lista separada por \n). Quando sql_expression é NULL/vazio
    # usa object_name como fallback (stages sem SQL explícito).
    sql = f"""
        SELECT TOP {top_n}
            tbl_name,
            ISNULL(database_name, '') AS database_name,
            COUNT(DISTINCT pipeline_name)                           AS pipeline_count,
            COUNT(DISTINCT job_name)                                AS job_count,
            SUM(CASE WHEN direction = 'origem'  THEN 1 ELSE 0 END) AS as_origem,
            SUM(CASE WHEN direction = 'destino' THEN 1 ELSE 0 END) AS as_destino
        FROM (
            -- Stages COM sql_expression: expande cada linha como uma tabela
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

            -- Stages SEM sql_expression: usa object_name como fallback
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


def consultar_catalogo(**context):
    conf = context["dag_run"].conf or {}
    mode = (conf.get("mode") or "search").strip().lower()
    hook = MsSqlHook(mssql_conn_id=MSSQL_CONN_ID)

    if mode == "ranking":
        top_n        = min(50, max(1, int(conf.get("top_n", 15))))
        ranking_type = (conf.get("ranking_type") or "tabela").strip().lower()
        if ranking_type == "arquivo":
            return _ranking_arquivo(hook, top_n)
        return _ranking_tabela(hook, top_n)

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
