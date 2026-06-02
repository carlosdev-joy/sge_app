from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime
from airflow.providers.microsoft.mssql.hooks.mssql import MsSqlHook

DAG_ID        = "etl_pipeline_register"
MSSQL_CONN_ID = "SQL14_DMDB41"

VALID_PROJECTS = {"BI_CVP", "BI_VIDA", "BI_PRESTAMISTA", "BI_PREVIDENCIA"}


def _build_cron(schedule_type: str | None, hour, minute, dow, dom) -> str:
    """Converte schedule_type + parâmetros para cron expression."""
    st = (schedule_type or "daily").strip().lower()
    h = int(hour or 0)
    m = int(minute or 0)
    if st == "hourly":
        return f"{m} * * * *"
    if st == "daily":
        return f"{m} {h} * * *"
    if st == "weekly":
        d = int(dow if dow is not None else 1)
        return f"{m} {h} * * {d}"
    if st == "monthly":
        day = int(dom if dom is not None else 1)
        return f"{m} {h} {day} * *"
    return f"{m} {h} * * *"


def registrar_pipeline(**context):
    """
    Parâmetros esperados via conf:

      pipeline_name    : str  — obrigatório
      scheduled_time   : str  — obrigatório (legado) ex: "08:00:00"
      schedule_type    : str  — hourly | daily | weekly | monthly (opcional)
      schedule_hour    : int  — 0-23 (opcional)
      schedule_minute  : int  — 0-59 (opcional)
      schedule_dow     : int  — 0=Dom..6=Sab (opcional, weekly)
      schedule_dom     : int  — 1-31 (opcional, monthly)
      active           : int  — 0 | 1  (default 1)
      envia_msg_inicio : int  — 0 | 1  (default 1)
      envia_msg_fim    : int  — 0 | 1  (default 1)
      envia_msg_erro   : int  — 0 | 1  (default 1)
      dag_criada       : int  — 0 | 1  (default 0 — gerenciado pela factory)
      project_name     : str  — BI_CVP | BI_VIDA | BI_PRESTAMISTA | BI_PREVIDENCIA
      domain           : str  — ex: Clientes, Cobrança (default 'Geral')
      tags             : str  — separadas por vírgula (default '')
    """
    conf = context["dag_run"].conf or {}

    pipeline = conf.get("pipeline_name")
    horario  = conf.get("scheduled_time")
    if not pipeline or not horario:
        raise ValueError("conf.pipeline_name e conf.scheduled_time são obrigatórios")

    project = conf.get("project_name", "BI_CVP")
    if project not in VALID_PROJECTS:
        raise ValueError(f"project_name inválido: '{project}'. Valores aceitos: {VALID_PROJECTS}")

    active           = int(conf.get("active",           1))
    envia_msg_inicio = int(conf.get("envia_msg_inicio", 1))
    envia_msg_fim    = int(conf.get("envia_msg_fim",    1))
    envia_msg_erro   = int(conf.get("envia_msg_erro",   1))
    dag_criada       = int(conf.get("dag_criada",       0))
    domain           = conf.get("domain", "Geral")
    tags             = conf.get("tags", "")

    # ── Schedule avançado (Fase 3) ───────────────────────────
    schedule_type   = (conf.get("schedule_type") or None)
    schedule_hour   = conf.get("schedule_hour")
    schedule_minute = conf.get("schedule_minute")
    schedule_dow    = conf.get("schedule_dow")
    schedule_dom    = conf.get("schedule_dom")

    cron = _build_cron(schedule_type, schedule_hour, schedule_minute, schedule_dow, schedule_dom)

    hook = MsSqlHook(mssql_conn_id=MSSQL_CONN_ID)

    sql = """
    EXEC dbo.sp_etl_pipeline_upsert
        @pipeline_name    = %s,
        @scheduled_time   = %s,
        @schedule_type    = %s,
        @schedule_hour    = %s,
        @schedule_minute  = %s,
        @schedule_dow     = %s,
        @schedule_dom     = %s,
        @active           = %s,
        @envia_msg_inicio = %s,
        @envia_msg_fim    = %s,
        @envia_msg_erro   = %s,
        @dag_criada       = %s,
        @project_name     = %s,
        @domain           = %s,
        @tags             = %s
    """

    hook.run(sql, parameters=(
        pipeline, horario,
        schedule_type, schedule_hour, schedule_minute, schedule_dow, schedule_dom,
        active,
        envia_msg_inicio, envia_msg_fim, envia_msg_erro,
        dag_criada, project, domain, tags,
    ))

    print(
        f"[OK] pipeline='{pipeline}' | horario={horario} | cron='{cron}' | project={project} | "
        f"domain={domain} | tags={tags} | active={active} | "
        f"msg_inicio={envia_msg_inicio} | msg_fim={envia_msg_fim} | "
        f"msg_erro={envia_msg_erro} | dag_criada={dag_criada}"
    )


with DAG(
    dag_id=DAG_ID,
    start_date=datetime(2024, 1, 1),
    catchup=False,
    schedule_interval=None,
    tags=["etl", "pipeline", "cadastro"],
    access_control={"Op": {"can_read", "can_edit"}},
) as dag:
    task = PythonOperator(
        task_id="registrar_pipeline",
        python_callable=registrar_pipeline,
    )
