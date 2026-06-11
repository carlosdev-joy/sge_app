"""
etl_lineage_normalize.py
========================
DAG de normalização do lineage existente.

Problema: importações feitas com versão anterior do DSXEngine gravavam
o nome do componente DataStage (ex: CONSULTA_PREST) como object_name,
com as tabelas reais separadas por '\\n' em sql_expression.

Este DAG converte entradas no formato antigo para o formato atual:
uma linha por tabela real, com object_name = nome da tabela.

Pode ser executado mais de uma vez (idempotente).

Entrada via conf (opcional):
  pipeline_name : str — normaliza só este pipeline (padrão: todos)
  dry_run       : bool — exibe o que seria feito sem alterar (padrão: false)
"""
from __future__ import annotations

import pendulum
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.microsoft.mssql.hooks.mssql import MsSqlHook

DAG_ID        = "etl_lineage_normalize"
MSSQL_CONN_ID = "SQL14_DMDB41"
LOCAL_TZ      = "America/Sao_Paulo"

default_args = {"owner": "airflow", "depends_on_past": False, "retries": 0}


def normalizar_lineage(**context):
    conf          = context["dag_run"].conf or {}
    pipeline_name = (conf.get("pipeline_name") or "").strip() or None
    dry_run       = str(conf.get("dry_run", "false")).lower() in ("true", "1", "yes")

    hook = MsSqlHook(mssql_conn_id=MSSQL_CONN_ID)

    # Busca entradas onde sql_expression tem tabelas mas object_name é um
    # nome de componente (não coincide com nenhuma das linhas do sql_expression).
    # Heurística: sql_expression IS NOT NULL e object_name NÃO está na lista de tabelas.
    where_extra = "AND l.pipeline_name = %s" if pipeline_name else ""
    params = [pipeline_name] if pipeline_name else []

    rows = hook.get_records(f"""
        SELECT
            l.id,
            l.pipeline_name,
            l.job_name,
            l.direction,
            l.object_type,
            l.stage_name,
            l.stage_type_raw,
            l.database_name,
            l.sql_expression,
            l.file_path,
            l.dsx_source_file,
            l.extraction_method,
            l.columns_json,
            l.object_name
        FROM dbo.etl_job_lineage l
        WHERE l.sql_expression IS NOT NULL
          AND l.sql_expression <> ''
          -- object_name é o componente quando NÃO está entre as linhas do sql_expression
          AND CHARINDEX(l.object_name, l.sql_expression) = 0
          {where_extra}
        ORDER BY l.pipeline_name, l.job_name
    """, parameters=params if params else None)

    total_old  = 0
    total_new  = 0
    ids_to_del = []

    for row in rows:
        (rec_id, pip, job, direction, obj_type, stage_name, stage_type_raw,
         db_name, sql_expr, fp, dsx_src, extr_method, cols_json, obj_name) = row

        tables = [t.strip() for t in sql_expr.split("\n") if t.strip()]
        if not tables:
            continue

        # Se object_name já é uma das tabelas extraídas → já normalizado
        if obj_name.strip().lower() in {t.lower() for t in tables}:
            continue

        total_old += 1
        print(f"[NORMALIZE] {pip} / {job}: '{obj_name}' → {tables}")

        if not dry_run:
            # Insere uma linha por tabela real
            for tbl in tables:
                hook.run("""
                    INSERT INTO dbo.etl_job_lineage
                        (pipeline_name, job_name, direction, object_type,
                         object_name, stage_name, stage_type_raw,
                         database_name, sql_expression, file_path,
                         dsx_source_file, extraction_method, columns_json,
                         extracted_at, created_at, updated_at)
                    SELECT %s, %s, %s,
                        CASE WHEN CHARINDEX('.', %s) > 0 THEN 'Tabela'
                             ELSE ISNULL(%s, 'Tabela') END,
                        %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        GETDATE(), GETDATE(), GETDATE()
                    WHERE NOT EXISTS (
                        SELECT 1 FROM dbo.etl_job_lineage
                        WHERE pipeline_name=%s AND job_name=%s
                          AND direction=%s AND object_name=%s
                    )
                """, parameters=[
                    pip, job, direction,
                    tbl, obj_type,       # object_type CASE
                    tbl, stage_name, stage_type_raw, db_name,
                    sql_expr, fp, dsx_src, extr_method, cols_json,
                    # WHERE NOT EXISTS
                    pip, job, direction, tbl,
                ])
                total_new += 1

            ids_to_del.append(rec_id)

    if not dry_run and ids_to_del:
        # Remove entradas antigas com nome de componente
        for chunk_start in range(0, len(ids_to_del), 100):
            chunk = ids_to_del[chunk_start:chunk_start + 100]
            placeholders = ",".join(["%s"] * len(chunk))
            hook.run(
                f"DELETE FROM dbo.etl_job_lineage WHERE id IN ({placeholders})",
                parameters=chunk,
            )

    mode = "[DRY-RUN] " if dry_run else ""
    print(
        f"{mode}Normalização concluída: "
        f"{total_old} entrada(s) antiga(s) → {total_new} nova(s) por tabela. "
        f"{len(ids_to_del)} entrada(s) de componente removida(s)."
    )

    return {
        "dry_run":        dry_run,
        "entradas_antigas": total_old,
        "entradas_novas":   total_new,
        "removidas":        len(ids_to_del),
    }


with DAG(
    dag_id=DAG_ID,
    default_args=default_args,
    description="Normaliza lineage legado: object_name = tabela real (não componente)",
    start_date=pendulum.datetime(2024, 1, 1, tz=LOCAL_TZ),
    schedule=None,
    catchup=False,
    tags=["governanca", "lineage", "manutencao"],
    access_control={"Op": {"can_read", "can_edit"}},
) as dag:

    PythonOperator(
        task_id="normalizar_lineage",
        python_callable=normalizar_lineage,
        do_xcom_push=True,
    )
