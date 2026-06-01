from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime
from airflow.providers.microsoft.mssql.hooks.mssql import MsSqlHook

DAG_ID        = "etl_pipeline_job_register"
MSSQL_CONN_ID = "SQL14_DMDB41"

VALID_JOB_TYPES    = {"datastage", "shell", "python", "storedproc"}
VALID_DIRECTIONS   = {"origem", "destino"}
#
# IMPORTANTE:
# A validação de object_type foi removida.
# Motivo: em DataStage/DSX podem surgir tipos como "DataSet" e outros,
# e o processo de cadastro não deve falhar por causa disso.
# Mantemos apenas a validação de object_name obrigatório.


def registrar_pipeline_jobs(**context):
    """
    conf esperado:
      pipeline_name : str  — obrigatório
      jobs : list de {
          job_name        : str
          execution_order : int
          job_type        : datastage | shell | python | storedproc
          job_command     : str | null
          origens  : list de { object_type, object_name }  — mín. 1
          destinos : list de { object_type, object_name }  — mín. 1
      }
      OU modo simples: job_name, execution_order, job_type, job_command,
                       origens, destinos no nível raiz do conf
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
            "job_name":        job_name,
            "execution_order": int(execution_order),
            "job_type":        conf.get("job_type", "datastage"),
            "job_command":     conf.get("job_command", None),
            "origens":         conf.get("origens", []),
            "destinos":        conf.get("destinos", []),
        }]

    hook = MsSqlHook(mssql_conn_id=MSSQL_CONN_ID)

    sql_job = """
    EXEC dbo.sp_etl_pipeline_job_upsert
        @pipeline_name   = %s,
        @job_name        = %s,
        @execution_order = %s,
        @job_type        = %s,
        @job_command     = %s
    """

    sql_lineage = """
    EXEC dbo.sp_etl_job_lineage_upsert
        @pipeline_name = %s,
        @job_name      = %s,
        @direction     = %s,
        @object_type   = %s,
        @object_name   = %s,
        @stage_name        = %s,
        @stage_type_raw    = %s,
        @database_name     = %s,
        @sql_expression    = %s,
        @dsx_source_file   = %s,
        @extracted_at      = %s,
        @extraction_method = %s
    """

    erros = []

    for idx, job in enumerate(jobs):
        j_name    = job.get("job_name")
        j_order   = job.get("execution_order")
        j_type    = (job.get("job_type") or "datastage").lower().strip()
        j_command = job.get("job_command") or None
        origens   = job.get("origens",  [])
        destinos  = job.get("destinos", [])

        # Validações básicas
        if not j_name or j_order is None:
            erros.append(f"Item {idx}: job_name e execution_order são obrigatórios")
            continue
        if j_type not in VALID_JOB_TYPES:
            erros.append(f"Item {idx} ({j_name}): job_type '{j_type}' inválido")
            continue
        if not origens:
            erros.append(f"Item {idx} ({j_name}): pelo menos 1 origem é obrigatória")
            continue
        if not destinos:
            erros.append(f"Item {idx} ({j_name}): pelo menos 1 destino é obrigatório")
            continue

        # 1. Grava o job
        try:
            hook.run(sql_job, parameters=(pipeline_name, j_name, int(j_order), j_type, j_command))
            print(f"[OK] job={j_name} | order={j_order} | type={j_type}")
        except Exception as e:
            erros.append(f"Item {idx} ({j_name}): erro ao gravar job — {e}")
            continue

        # 2. Grava lineage (origens + destinos)
        for direction, objects in [("origem", origens), ("destino", destinos)]:
            for obj_idx, obj in enumerate(objects):
                obj_type = (obj.get("object_type") or "Tabela").strip()
                obj_name = obj.get("object_name", "").strip()

                if not obj_name:
                    erros.append(f"Item {idx} ({j_name}) {direction}[{obj_idx}]: object_name obrigatório")
                    continue

                try:
                    hook.run(
                        sql_lineage,
                        parameters=(
                            pipeline_name,
                            j_name,
                            direction,
                            obj_type,
                            obj_name,
                            obj.get("stage_name"),
                            obj.get("stage_type_raw"),
                            obj.get("database_name"),
                            obj.get("sql_expression"),
                            obj.get("dsx_source_file"),
                            obj.get("extracted_at"),
                            obj.get("extraction_method"),
                        ),
                    )
                    print(f"  [OK] lineage {direction} → {obj_type}:{obj_name}")
                except Exception as e:
                    erros.append(f"Item {idx} ({j_name}) {direction} '{obj_name}': {e}")

    if erros:
        raise RuntimeError(f"{len(erros)} erro(s):\n" + "\n".join(erros))

    print(f"[CONCLUÍDO] {len(jobs)} job(s) registrado(s) com lineage para '{pipeline_name}'")


with DAG(
    dag_id=DAG_ID,
    start_date=datetime(2024, 1, 1),
    catchup=False,
    schedule_interval=None,
    tags=["etl", "pipeline", "job", "cadastro"],
    access_control={"Op": {"can_read", "can_edit"}},
) as dag:
    task = PythonOperator(
        task_id="registrar_pipeline_jobs",
        python_callable=registrar_pipeline_jobs,
    )
