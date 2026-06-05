"""
etl_catalogo_query.py
=====================
DAG do Catálogo de Dados — Governança ORQUESTRA.

Suporta dois modos via conf.mode:

  search  (padrão) — busca por nome de objeto (tabela/arquivo)
    Parâmetros:
      object_name  : str  — termo de busca (LIKE, obrigatório)
      direction    : str  — 'all' | 'origem' | 'destino' | 'transformacao'  (default 'all')
      database_name: str  — filtro exato de banco  (opcional)

    Retorna:
      {
        "mode": "search",
        "term": "...",
        "total_pipelines": int,
        "total_ocorrencias": int,
        "pipelines": [
          {
            "pipeline_name", "project_name", "domain", "active",
            "ocorrencias": int,
            "jobs": [
              { "job_name", "execution_order", "job_type",
                "direction", "object_name", "object_type",
                "database_name", "stage_name" }
            ]
          }
        ]
      }

  ranking — top tabelas mais utilizadas
    Parâmetros:
      top_n : int — quantidade de registros (default 15, max 50)

    Retorna:
      {
        "mode": "ranking",
        "data": [
          { "object_name", "database_name", "pipeline_count",
            "job_count", "as_origem", "as_destino" }
        ]
      }
"""
from __future__ import annotations

import json
import pendulum
from collections import defaultdict
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.microsoft.mssql.hooks.mssql import MsSqlHook

DAG_ID        = "etl_catalogo_query"
MSSQL_CONN_ID = "SQL14_DMDB41"
LOCAL_TZ      = "America/Sao_Paulo"

default_args = {"owner": "airflow", "depends_on_past": False, "retries": 0}


def _search(hook, object_name: str, direction: str, database_name: str) -> dict:
    where = [
        "l.object_name LIKE %s",
        "ISNULL(stm.type_category, 'banco') IN ('banco', 'arquivo')",
    ]
    params: list = [f"%{object_name}%"]

    if direction and direction != "all":
        where.append("l.direction = %s")
        params.append(direction)

    if database_name:
        where.append("l.database_name = %s")
        params.append(database_name)

    sql = f"""
        SELECT
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
            ISNULL(l.stage_name,   '')             AS stage_name,
            l.columns_json
        FROM dbo.etl_job_lineage l
        JOIN dbo.etl_pipeline     p   ON p.pipeline_name  = l.pipeline_name
        JOIN dbo.etl_pipeline_job pj  ON pj.pipeline_name = l.pipeline_name
                                      AND pj.job_name     = l.job_name
        LEFT JOIN dbo.etl_stage_type_map stm ON stm.type_raw = l.object_type
        WHERE {' AND '.join(where)}
        ORDER BY l.pipeline_name, pj.execution_order, l.direction, l.object_name
    """
    rows = hook.get_records(sql, parameters=params)
    cols = [
        "pipeline_name", "project_name", "domain", "active",
        "job_name", "execution_order", "job_type",
        "direction", "object_name", "object_type", "database_name", "stage_name", "columns_json",
    ]

    # Agrupa por pipeline → jobs
    by_pipeline: dict[str, dict] = {}
    for row in rows:
        rec = dict(zip(cols, row))
        pname = rec["pipeline_name"]
        if pname not in by_pipeline:
            by_pipeline[pname] = {
                "pipeline_name":  pname,
                "project_name":   rec["project_name"],
                "domain":         rec["domain"],
                "active":         rec["active"],
                "ocorrencias":    0,
                "jobs":           [],
            }
        try:
            cols = json.loads(rec["columns_json"]) if rec["columns_json"] else []
        except Exception:
            cols = []
        by_pipeline[pname]["ocorrencias"] += 1
        by_pipeline[pname]["jobs"].append({
            "job_name":       rec["job_name"],
            "execution_order": rec["execution_order"],
            "job_type":       rec["job_type"],
            "direction":      rec["direction"],
            "object_name":    rec["object_name"],
            "object_type":    rec["object_type"],
            "database_name":  rec["database_name"],
            "stage_name":     rec["stage_name"],
            "columns":        cols,
        })

    pipelines = sorted(by_pipeline.values(), key=lambda x: x["pipeline_name"])
    total_occ = sum(p["ocorrencias"] for p in pipelines)

    print(f"[CATALOGO] search='{object_name}' dir='{direction}' db='{database_name}' → "
          f"{len(pipelines)} pipeline(s), {total_occ} ocorrência(s)")

    return {
        "mode":              "search",
        "term":              object_name,
        "direction":         direction,
        "database_name":     database_name,
        "total_pipelines":   len(pipelines),
        "total_ocorrencias": total_occ,
        "pipelines":         pipelines,
    }


def _ranking(hook, top_n: int) -> dict:
    sql = f"""
        SELECT TOP {top_n}
            l.object_name,
            ISNULL(l.database_name, '') AS database_name,
            COUNT(DISTINCT l.pipeline_name)                                    AS pipeline_count,
            COUNT(DISTINCT l.job_name)                                         AS job_count,
            SUM(CASE WHEN l.direction = 'origem'  THEN 1 ELSE 0 END)          AS as_origem,
            SUM(CASE WHEN l.direction = 'destino' THEN 1 ELSE 0 END)          AS as_destino
        FROM dbo.etl_job_lineage l
        LEFT JOIN dbo.etl_stage_type_map stm ON stm.type_raw = l.object_type
        WHERE l.direction IN ('origem', 'destino')
          AND ISNULL(stm.type_category, 'banco') IN ('banco', 'arquivo')
          AND l.object_name IS NOT NULL
          AND l.object_name <> ''
        GROUP BY l.object_name, l.database_name
        ORDER BY COUNT(DISTINCT l.pipeline_name) DESC, l.object_name
    """
    rows = hook.get_records(sql)
    cols = ["object_name", "database_name", "pipeline_count", "job_count", "as_origem", "as_destino"]
    data = [dict(zip(cols, row)) for row in rows]

    print(f"[CATALOGO] ranking top={top_n} → {len(data)} objeto(s)")
    return {"mode": "ranking", "data": data}


def consultar_catalogo(**context):
    conf      = context["dag_run"].conf or {}
    mode      = (conf.get("mode") or "search").strip().lower()
    hook      = MsSqlHook(mssql_conn_id=MSSQL_CONN_ID)

    if mode == "ranking":
        top_n = min(50, max(1, int(conf.get("top_n", 15))))
        return _ranking(hook, top_n)

    # mode == "search"
    object_name   = (conf.get("object_name")   or "").strip()
    direction     = (conf.get("direction")      or "all").strip().lower()
    database_name = (conf.get("database_name") or "").strip()

    if not object_name:
        raise ValueError("Parâmetro 'object_name' é obrigatório para mode=search.")

    return _search(hook, object_name, direction, database_name)


with DAG(
    dag_id=DAG_ID,
    default_args=default_args,
    description="Catálogo de dados — busca por tabela e ranking de objetos",
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
