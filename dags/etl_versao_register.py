"""
etl_versao_register.py
======================
DAG de CRUD para versões da ferramenta ORQUESTRA.

Recebe via conf:
  action       : str  — 'create' | 'update' | 'delete'
  id           : int  — obrigatório para update e delete
  versao       : str  — ex: '2.2.0'  (create/update)
  titulo       : str  — título curto da versão (create/update)
  descricao_md : str  — descrição em markdown (create/update, opcional)
  criado_por   : str  — usuário que registrou (default 'admin')
"""
from __future__ import annotations

import pendulum
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.microsoft.mssql.hooks.mssql import MsSqlHook

DAG_ID        = "etl_versao_register"
MSSQL_CONN_ID = "SQL14_DMDB41"
LOCAL_TZ      = "America/Sao_Paulo"

default_args = {"owner": "airflow", "depends_on_past": False, "retries": 0}


def registrar_versao(**context):
    conf   = context["dag_run"].conf or {}
    action = (conf.get("action") or "create").strip().lower()

    hook = MsSqlHook(mssql_conn_id=MSSQL_CONN_ID)

    if action == "delete":
        record_id = int(conf.get("id", 0))
        if not record_id:
            raise ValueError("Parâmetro 'id' é obrigatório para action=delete.")
        hook.run(
            "DELETE FROM dbo.etl_versao_ferramenta WHERE id = %s",
            parameters=(record_id,),
        )
        print(f"[VERSAO_REGISTER] Versão id={record_id} excluída.")
        return {"action": "delete", "id": record_id}

    versao      = (conf.get("versao") or "").strip()
    titulo      = (conf.get("titulo") or "").strip()
    descricao   = (conf.get("descricao_md") or "").strip() or None
    criado_por  = (conf.get("criado_por") or "admin").strip()

    if not versao or not titulo:
        raise ValueError("Parâmetros 'versao' e 'titulo' são obrigatórios.")

    def _sync_app_config(h, v, t):
        """Mantém etl_app_config sincronizado com a versão mais recente."""
        for key, val in (("app_version", v), ("app_release_name", t)):
            h.run(
                "UPDATE dbo.etl_app_config SET config_value=%s WHERE config_key=%s",
                parameters=(val, key),
            )
            h.run(
                "INSERT INTO dbo.etl_app_config (config_key, config_value) "
                "SELECT %s, %s WHERE NOT EXISTS "
                "(SELECT 1 FROM dbo.etl_app_config WHERE config_key=%s)",
                parameters=(key, val, key),
            )
        print(f"[VERSAO_REGISTER] etl_app_config atualizado: app_version={v}")

    if action == "update":
        record_id = int(conf.get("id", 0))
        if not record_id:
            raise ValueError("Parâmetro 'id' é obrigatório para action=update.")
        hook.run(
            "UPDATE dbo.etl_versao_ferramenta "
            "SET versao=%s, titulo=%s, descricao_md=%s, criado_por=%s "
            "WHERE id=%s",
            parameters=(versao, titulo, descricao, criado_por, record_id),
        )
        _sync_app_config(hook, versao, titulo)
        print(f"[VERSAO_REGISTER] Versão id={record_id} atualizada: {versao} — {titulo}")
        return {"action": "update", "id": record_id, "versao": versao}

    # action == "create"
    hook.run(
        "INSERT INTO dbo.etl_versao_ferramenta (versao, titulo, descricao_md, criado_por) "
        "VALUES (%s, %s, %s, %s)",
        parameters=(versao, titulo, descricao, criado_por),
    )
    _sync_app_config(hook, versao, titulo)
    print(f"[VERSAO_REGISTER] Nova versão criada: {versao} — {titulo}")
    return {"action": "create", "versao": versao, "titulo": titulo}


with DAG(
    dag_id=DAG_ID,
    default_args=default_args,
    description="CRUD de versões do ORQUESTRA (create/update/delete)",
    start_date=pendulum.datetime(2024, 1, 1, tz=LOCAL_TZ),
    schedule=None,
    catchup=False,
    tags=["admin", "versao", "changelog"],
    access_control={"Op": {"can_read", "can_edit"}},
) as dag:

    task = PythonOperator(
        task_id="registrar_versao",
        python_callable=registrar_versao,
    )
