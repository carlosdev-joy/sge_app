"""
orquestra_teste.py
==================
Módulo Python de teste para validação do ORQUESTRA.

Usado como job_command no wizard:  orquestra_teste

O Airflow importa este módulo via importlib e chama run(**context).
"""
import pendulum


def run(**context):
    """Função chamada pelo PythonOperator via importlib."""
    execution_id = context.get("ts_nodash", "N/A")
    dag_id       = context.get("dag", None)
    dag_name     = dag_id.dag_id if dag_id else "N/A"
    now          = pendulum.now("America/Sao_Paulo").to_datetime_string()

    print("=" * 60)
    print("[ORQUESTRA_TESTE] Python job executado com sucesso")
    print(f"  dag_id       : {dag_name}")
    print(f"  execution_id : {execution_id}")
    print(f"  timestamp    : {now}")
    print("=" * 60)

    # Simula lógica de negócio mínima
    resultado = {"status": "ok", "linhas_processadas": 42, "ts": now}
    print(f"[ORQUESTRA_TESTE] resultado = {resultado}")

    # Status code 1 = SUCCESS para o log_end detectar
    print("Job Status Code: 1")
    return resultado
