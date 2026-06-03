"""
etl_app_config_query.py
========================
DAG leve que busca os parâmetros de configuração da aplicação ORQUESTRA
a partir da tabela dbo.etl_app_config e os retorna via XCom.

Chamada uma vez no login para popular window.__appConfig no frontend.
Também pode ser acionada manualmente para recarregar configs sem restart.

Saída XCom (key='return_value'):
{
  "dashboard_refresh_interval_sec": 60,
  "failure_badge_refresh_sec": 300,
  "failure_badge_hours_lookback": 24,
  "app_version": "2.1.0",
  "app_release_name": "Sprint 1 — Junho/2026",
  "pipeline_query_limit": 20,
  "jobs_query_limit": 50,
  "logs_query_limit": 30
}
"""

from __future__ import annotations
import pendulum
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.microsoft.mssql.hooks.mssql import MsSqlHook

DAG_ID        = 'etl_app_config_query'
MSSQL_CONN_ID = 'SQL14_DMDB41'
LOCAL_TZ      = 'America/Sao_Paulo'

default_args = {'owner': 'airflow', 'depends_on_past': False, 'retries': 0}

# Valores padrão (fallback caso a tabela ainda não exista)
DEFAULTS = {
    'dashboard_refresh_interval_sec': 60,
    'failure_badge_refresh_sec':      300,
    'failure_badge_hours_lookback':   24,
    'app_version':                    '2.1.0',
    'app_release_name':               'Sprint 1 — Junho/2026',
    'pipeline_query_limit':           20,
    'jobs_query_limit':               50,
    'logs_query_limit':               30,
}

# Chaves que devem ser convertidas para inteiro
INT_KEYS = {
    'dashboard_refresh_interval_sec',
    'failure_badge_refresh_sec',
    'failure_badge_hours_lookback',
    'pipeline_query_limit',
    'jobs_query_limit',
    'logs_query_limit',
}


def buscar_configuracoes(**context):
    result = dict(DEFAULTS)  # começa com os defaults

    try:
        hook = MsSqlHook(mssql_conn_id=MSSQL_CONN_ID)
        rows = hook.get_records(
            'SELECT config_key, config_value FROM dbo.etl_app_config'
        )
        for key, value in rows:
            if key in INT_KEYS:
                try:
                    result[key] = int(value)
                except (ValueError, TypeError):
                    pass  # mantém o default
            else:
                result[key] = str(value) if value is not None else result.get(key)

        print(f'[APP_CONFIG] {len(rows)} parâmetros carregados do banco.')
    except Exception as e:
        print(f'[APP_CONFIG] Aviso: não foi possível acessar etl_app_config: {e}')
        print('[APP_CONFIG] Usando valores padrão.')

    for k, v in result.items():
        print(f'  {k} = {v}')

    return result


with DAG(
    dag_id=DAG_ID,
    default_args=default_args,
    description='Busca parâmetros de configuração do ORQUESTRA no banco',
    start_date=pendulum.datetime(2024, 1, 1, tz=LOCAL_TZ),
    schedule=None,
    catchup=False,
    tags=['etl', 'config', 'admin'],
) as dag:

    PythonOperator(
        task_id='buscar_configuracoes',
        python_callable=buscar_configuracoes,
        do_xcom_push=True,
    )
