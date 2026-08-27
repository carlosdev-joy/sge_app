"""
etl_versao_query.py
===================
DAG de leitura — retorna o histórico de versões da ferramenta ORQUESTRA.

Retorna via XCom (key='return_value'):
{
  "total": int,
  "data": [
    { "id", "versao", "titulo", "descricao_md", "criado_em", "criado_por" }
  ]
}
"""
from __future__ import annotations

from datetime import datetime

import pendulum
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.microsoft.mssql.hooks.mssql import MsSqlHook

DAG_ID        = "etl_versao_query"
MSSQL_CONN_ID = "SQL14_DMDB41"
LOCAL_TZ      = "America/Sao_Paulo"

default_args = {"owner": "airflow", "depends_on_past": False, "retries": 0}


def _fmt(val) -> str | None:
    if val is None:
        return None
    if hasattr(val, "strftime"):
        return val.strftime("%Y-%m-%d %H:%M:%S")
    return str(val)


def consultar_versoes(**context):
    hook = MsSqlHook(mssql_conn_id=MSSQL_CONN_ID)

    rows = hook.get_records("""
        SELECT id, versao, titulo, descricao_md, criado_em, criado_por
        FROM dbo.etl_versao_ferramenta
        ORDER BY criado_em DESC
    """)

    cols = ["id", "versao", "titulo", "descricao_md", "criado_em", "criado_por"]
    data = []
    for row in rows:
        record = dict(zip(cols, row))
        record["criado_em"] = _fmt(record["criado_em"])
        data.append(record)

    result = {"total": len(data), "data": data}
    print(f"[VERSAO_QUERY] {len(data)} versão(ões) retornada(s)")
    return result


with DAG(
    dag_id=DAG_ID,
    default_args=default_args,
    description="Consulta histórico de versões do ORQUESTRA",
    start_date=pendulum.datetime(2024, 1, 1, tz=LOCAL_TZ),
    schedule=None,
    catchup=False,
    tags=["admin", "versao", "changelog"],
    access_control={"Op": {"can_read", "can_edit"}},
) as dag:

    task = PythonOperator(
        task_id="consultar_versoes",
        python_callable=consultar_versoes,
        do_xcom_push=True,
    )
