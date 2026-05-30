from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime
from airflow.providers.microsoft.mssql.hooks.mssql import MsSqlHook

DAG_ID        = "etl_pipeline_job_reorder"
MSSQL_CONN_ID = "SQL14_DMDB41"


def reorder_pipeline_jobs(**context):
    """
    Reordena jobs SEM tocar em lineage.

    conf esperado:
      pipeline_name : str  — obrigatório
      jobs : list de {
          job_name        : str
          execution_order : int
      }
      OU modo simples: job_name + execution_order no nível raiz do conf
    """
    conf = context["dag_run"].conf or {}

    pipeline_name = conf.get("pipeline_name")
    if not pipeline_name:
        raise ValueError("conf.pipeline_name é obrigatório")

    jobs_raw = conf.get("jobs")
    if jobs_raw:
        if not isinstance(jobs_raw, list) or len(jobs_raw) == 0:
            raise ValueError("conf.jobs deve ser uma lista não vazia")
        jobs = jobs_raw
    else:
        job_name = conf.get("job_name")
        execution_order = conf.get("execution_order")
        if not job_name or execution_order is None:
            raise ValueError("Informe conf.jobs (batch) ou job_name + execution_order (simples)")
        jobs = [{
            "job_name": job_name,
            "execution_order": int(execution_order),
        }]

    # validação básica
    erros = []
    for idx, j in enumerate(jobs):
        name = (j.get("job_name") or "").strip()
        order = j.get("execution_order")
        if not name or order is None:
            erros.append(f"Item {idx}: job_name e execution_order são obrigatórios")
            continue
        try:
            j["job_name"] = name
            j["execution_order"] = int(order)
            if j["execution_order"] < 1:
                raise ValueError("execution_order deve ser >= 1")
        except Exception:
            erros.append(f"Item {idx} ({name}): execution_order inválido")

    if erros:
        raise RuntimeError(f"{len(erros)} erro(s):\n" + "\n".join(erros))

    hook = MsSqlHook(mssql_conn_id=MSSQL_CONN_ID)

    sql = """
    EXEC dbo.sp_etl_pipeline_job_reorder
        @pipeline_name   = %s,
        @job_name        = %s,
        @execution_order = %s
    """

    for j in jobs:
        hook.run(sql, parameters=(pipeline_name, j["job_name"], int(j["execution_order"])))
        print(f"[OK] reorder job={j['job_name']} | order={j['execution_order']} | pipeline={pipeline_name}")

    print(f"[CONCLUÍDO] reorder de {len(jobs)} job(s) para '{pipeline_name}'")


with DAG(
    dag_id=DAG_ID,
    start_date=datetime(2024, 1, 1),
    catchup=False,
    schedule_interval=None,
    tags=["etl", "pipeline", "job", "reorder"],
    access_control={"Op": {"can_read", "can_edit"}},
) as dag:
    task = PythonOperator(
        task_id="reorder_pipeline_jobs",
        python_callable=reorder_pipeline_jobs,
    )

