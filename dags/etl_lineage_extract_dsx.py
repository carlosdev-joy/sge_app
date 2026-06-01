"""
etl_lineage_extract_dsx.py
==========================
Extrai linhagem de um job DataStage a partir do arquivo .dsx do projeto.

Conf:
  project_name : str — nome do projeto (== nome do arquivo .dsx sem extensão)
                 ex: "BI_CVP" → lê /opt/airflow/dsx/BI_CVP.dsx
  job_name : str — nome exato do job dentro do arquivo .dsx

IMPORTANTE:
  pipeline_name NÃO é parâmetro de extração. O pipeline é um conceito do Airflow; o .dsx não o conhece.
  A UI adiciona o pipeline_name apenas na hora de salvar.

Retorno via XCom (task: extrair_lineage_dsx):
{
  "sucesso": true,
  "project_name": "BI_CVP",
  "job_name": "BiCvp_Extrai_Pedidos",
  "dsx_file": "BI_CVP.dsx",
  "dados": [ ... ]
}
"""

from __future__ import annotations

import os
import sys

import pendulum
from airflow import DAG
from airflow.operators.python import PythonOperator

DAG_ID = "etl_lineage_extract_dsx"
LOCAL_TZ = "America/Sao_Paulo"

default_args = {"owner": "airflow", "depends_on_past": False, "retries": 0}


def extrair_lineage_dsx(**context):
    conf = context["dag_run"].conf or {}
    project_name = (conf.get("project_name") or "").strip()
    job_name = (conf.get("job_name") or "").strip()

    if not project_name or not job_name:
        raise ValueError("project_name e job_name são obrigatórios.")

    # Importar DSXEngine do módulo utils (dentro do diretório dags)
    dags_folder = os.path.dirname(os.path.abspath(__file__))
    if dags_folder not in sys.path:
        sys.path.insert(0, dags_folder)

    from utils.dsx_engine import DSXEngine, _DEFAULT_DSX_DIR

    motor = DSXEngine(diretorio_base=_DEFAULT_DSX_DIR)
    resultado = motor.buscar_linhagem(nome_projeto=project_name, nome_job=job_name)

    if resultado.get("erro"):
        raise RuntimeError(resultado["erro"])

    dsx_file = f"{project_name}.dsx"
    dados = resultado.get("dados") or []
    print(f"[DSX] Extraídos {len(dados)} ponto(s) de contato de {dsx_file}/{job_name}")

    return {
        "sucesso": True,
        "project_name": project_name,
        "job_name": job_name,
        "dsx_file": dsx_file,
        "dados": dados,
    }


with DAG(
    dag_id=DAG_ID,
    default_args=default_args,
    description="Extrai linhagem de job DataStage a partir de arquivo .dsx",
    start_date=pendulum.datetime(2026, 1, 1, tz=LOCAL_TZ),
    schedule=None,
    catchup=False,
    tags=["orquestra", "lineage", "dsx"],
    access_control={"Op": {"can_read", "can_edit"}},
) as dag:
    PythonOperator(
        task_id="extrair_lineage_dsx",
        python_callable=extrair_lineage_dsx,
        do_xcom_push=True,
    )

