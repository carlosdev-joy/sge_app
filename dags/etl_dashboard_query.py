from __future__ import annotations

import pendulum
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.microsoft.mssql.hooks.mssql import MsSqlHook

DAG_ID = "etl_dashboard_query"
MSSQL_CONN_ID = "SQL14_DMDB41"
LOCAL_TZ = "America/Sao_Paulo"
MAX_LIMIT = 200

default_args = {"owner": "airflow", "depends_on_past": False, "retries": 0}


def _fmt_dt(v):
    if v is None:
        return None
    if hasattr(v, "strftime"):
        return v.strftime("%Y-%m-%d %H:%M:%S")
    return str(v)


def _status_expr_sql() -> str:
    return """
        CASE
            WHEN SUM(CASE WHEN status = 'FAILED'  THEN 1 ELSE 0 END) > 0 THEN 'FAILED'
            WHEN SUM(CASE WHEN status = 'WARNING' THEN 1 ELSE 0 END) > 0 THEN 'WARNING'
            WHEN SUM(CASE WHEN status = 'RUNNING' THEN 1 ELSE 0 END) > 0 THEN 'RUNNING'
            WHEN SUM(CASE WHEN status = 'SUCCESS' THEN 1 ELSE 0 END) > 0 THEN 'SUCCESS'
            ELSE 'DESCONHECIDO'
        END
    """


def consultar_dashboard(**context):
    conf = context["dag_run"].conf or {}
    filter_project = (conf.get("filter_project") or "").strip()
    date_ref = (conf.get("date_ref") or "").strip()  # YYYY-MM-DD

    if not date_ref:
        date_ref = pendulum.now(LOCAL_TZ).format("YYYY-MM-DD")

    dt_ini = pendulum.parse(date_ref, tz=LOCAL_TZ).start_of("day")
    dt_fim = dt_ini.add(days=1)

    hook = MsSqlHook(mssql_conn_id=MSSQL_CONN_ID)
    params_base: list[object] = []
    where_proj = ""
    if filter_project:
        where_proj = " AND project = %s "
        params_base.append(filter_project)

    status_expr = _status_expr_sql()

    # ── KPI do dia (agregado por execução) ───────────────────────────────────
    kpi_sql = f"""
        WITH execs AS (
            SELECT
                execution_id,
                project,
                pipeline,
                MIN(start_time) AS inicio,
                MAX(end_time)   AS fim,
                COALESCE(SUM(duration_seconds), 0) AS duracao_total_segundos,
                {status_expr} AS status_geral
            FROM dbo.etl_job_execution
            WHERE start_time >= %s AND start_time < %s
              {where_proj}
            GROUP BY execution_id, project, pipeline
        )
        SELECT
            COUNT(*) AS total_execucoes,
            SUM(CASE WHEN status_geral='SUCCESS' THEN 1 ELSE 0 END) AS total_sucesso,
            SUM(CASE WHEN status_geral='FAILED'  THEN 1 ELSE 0 END) AS total_falha,
            SUM(CASE WHEN status_geral='WARNING' THEN 1 ELSE 0 END) AS total_warning,
            CAST(AVG(CAST(duracao_total_segundos AS float)) AS int) AS duracao_media_segundos
        FROM execs;
    """
    row = hook.get_first(kpi_sql, parameters=[dt_ini.to_datetime_string(), dt_fim.to_datetime_string()] + params_base)
    total_exec = int(row[0] or 0) if row else 0
    total_sucesso = int(row[1] or 0) if row else 0
    total_falha = int(row[2] or 0) if row else 0
    total_warning = int(row[3] or 0) if row else 0
    duracao_media = int(row[4] or 0) if row else 0
    taxa = round((total_sucesso * 100.0 / total_exec), 1) if total_exec else 0.0

    por_projeto_sql = f"""
        WITH execs AS (
            SELECT
                execution_id,
                project,
                pipeline,
                {status_expr} AS status_geral
            FROM dbo.etl_job_execution
            WHERE start_time >= %s AND start_time < %s
            GROUP BY execution_id, project, pipeline
        )
        SELECT
            project,
            COUNT(*) AS execucoes,
            SUM(CASE WHEN status_geral='FAILED'  THEN 1 ELSE 0 END) AS falhas,
            SUM(CASE WHEN status_geral='WARNING' THEN 1 ELSE 0 END) AS warnings
        FROM execs
        {("WHERE project = %s" if filter_project else "")}
        GROUP BY project
        ORDER BY project;
    """
    pp_params = [dt_ini.to_datetime_string(), dt_fim.to_datetime_string()] + ([filter_project] if filter_project else [])
    pp_rows = hook.get_records(por_projeto_sql, parameters=pp_params)
    por_projeto = [
        {"project": r[0], "execucoes": int(r[1] or 0), "falhas": int(r[2] or 0), "warnings": int(r[3] or 0)}
        for r in (pp_rows or [])
    ]

    # ── Status por pipeline (última execução) ────────────────────────────────
    pipe_status_sql = f"""
        WITH execs AS (
            SELECT
                execution_id,
                project,
                pipeline,
                MIN(start_time) AS inicio,
                COALESCE(SUM(duration_seconds), 0) AS duracao_segundos,
                COUNT(*) AS total_jobs,
                {status_expr} AS ultimo_status
            FROM dbo.etl_job_execution
            WHERE 1=1
              {where_proj}
            GROUP BY execution_id, project, pipeline
        ),
        ranked AS (
            SELECT *,
                   ROW_NUMBER() OVER (PARTITION BY pipeline ORDER BY inicio DESC) AS rn
            FROM execs
        )
        SELECT TOP 20
            r.pipeline, r.project, r.ultimo_status, r.inicio, r.duracao_segundos,
            r.total_jobs, r.execution_id,
            COALESCE(p.criticidade, '') AS criticidade
        FROM ranked r
        LEFT JOIN dbo.etl_pipeline p ON p.pipeline_name = r.pipeline
        WHERE rn = 1
        ORDER BY
            CASE COALESCE(p.criticidade,'') WHEN 'ALTA' THEN 1 WHEN 'MEDIA' THEN 2 WHEN 'BAIXA' THEN 3 ELSE 4 END,
            CASE r.ultimo_status WHEN 'FAILED' THEN 1 WHEN 'WARNING' THEN 2 WHEN 'RUNNING' THEN 3 ELSE 4 END,
            r.inicio DESC;
    """
    ps_rows = hook.get_records(pipe_status_sql, parameters=params_base or None)
    pipeline_status = [
        {
            "pipeline":      r[0],
            "project":       r[1],
            "ultimo_status": r[2],
            "ultimo_inicio": _fmt_dt(r[3]),
            "duracao_segundos": int(r[4] or 0),
            "total_jobs":    int(r[5] or 0),
            "execution_id":  r[6],
            "criticidade":   r[7] or "",
        }
        for r in (ps_rows or [])
    ]

    # ── Últimas falhas (jobs) ────────────────────────────────────────────────
    falhas_sql = f"""
        SELECT TOP 5
            pipeline, project, job_name, status, start_time AS inicio, execution_id, log_file
        FROM dbo.etl_job_execution
        WHERE status = 'FAILED'
          {where_proj}
        ORDER BY start_time DESC;
    """
    ff_rows = hook.get_records(falhas_sql, parameters=params_base or None)
    ultimas_falhas = [
        {
            "pipeline": r[0],
            "project": r[1],
            "job_name": r[2],
            "status": r[3],
            "inicio": _fmt_dt(r[4]),
            "execution_id": r[5],
            "log_file": r[6],
        }
        for r in (ff_rows or [])
    ]

    # ── Executando agora (por execução/pipeline) ─────────────────────────────
    running_sql = f"""
        WITH runs AS (
            SELECT
                execution_id,
                project,
                pipeline,
                MIN(start_time) AS inicio,
                COUNT(*) AS total_jobs,
                SUM(CASE WHEN status='RUNNING' THEN 1 ELSE 0 END) AS jobs_running,
                SUM(CASE WHEN status='SUCCESS' THEN 1 ELSE 0 END) AS jobs_ok
            FROM dbo.etl_job_execution
            WHERE status = 'RUNNING'
              {where_proj}
            GROUP BY execution_id, project, pipeline
        )
        SELECT TOP 10
            execution_id, project, pipeline, inicio, total_jobs, jobs_running, jobs_ok,
            DATEDIFF(SECOND, inicio, GETDATE()) AS elapsed_seconds
        FROM runs
        ORDER BY inicio DESC;
    """
    rn_rows = hook.get_records(running_sql, parameters=params_base or None)
    executando_agora = [
        {
            "execution_id": r[0],
            "project": r[1],
            "pipeline": r[2],
            "inicio": _fmt_dt(r[3]),
            "total_jobs": int(r[4] or 0),
            "jobs_running": int(r[5] or 0),
            "jobs_ok": int(r[6] or 0),
            "elapsed_seconds": int(r[7] or 0),
        }
        for r in (rn_rows or [])
    ]

    # ── Alertas de performance (>= 3h) ───────────────────────────────────────
    alert_sql = f"""
        WITH running_exec AS (
            SELECT
                execution_id,
                project,
                pipeline,
                MIN(start_time) AS inicio,
                DATEDIFF(SECOND, MIN(start_time), GETDATE()) AS elapsed_seconds,
                DATEDIFF(HOUR, MIN(start_time), GETDATE()) AS elapsed_hours
            FROM dbo.etl_job_execution
            WHERE status = 'RUNNING'
              {where_proj}
            GROUP BY execution_id, project, pipeline
        )
        SELECT TOP 10
            execution_id,
            project,
            pipeline,
            inicio,
            elapsed_seconds,
            CASE
                WHEN elapsed_hours >= 12 THEN 12
                WHEN elapsed_hours >= 6 THEN 6
                ELSE 3
            END AS alerta_horas
        FROM running_exec
        WHERE elapsed_seconds >= 10800
        ORDER BY elapsed_seconds DESC;
    """
    al_rows = hook.get_records(alert_sql, parameters=params_base or None)
    alertas_perf = [
        {
            "execution_id": r[0],
            "project": r[1],
            "pipeline": r[2],
            "inicio": _fmt_dt(r[3]),
            "elapsed_seconds": int(r[4] or 0),
            "alerta_horas": int(r[5] or 3),
        }
        for r in (al_rows or [])
    ]

    result = {
        "date_ref": date_ref,
        "kpis": {
            "total_execucoes": total_exec,
            "total_sucesso": total_sucesso,
            "total_falha": total_falha,
            "total_warning": total_warning,
            "taxa_sucesso_pct": taxa,
            "duracao_media_segundos": duracao_media,
            "por_projeto": por_projeto,
            "filter_project": filter_project,
        },
        "pipeline_status": pipeline_status,
        "ultimas_falhas": ultimas_falhas,
        "executando_agora": executando_agora,
        "alertas_perf": alertas_perf,
    }

    print(f"[{DAG_ID}] date_ref={date_ref} project={filter_project or '*'}")
    return result


with DAG(
    dag_id=DAG_ID,
    default_args=default_args,
    description="Dashboard de observabilidade (KPIs + status + falhas + running) via XCom",
    start_date=pendulum.datetime(2026, 1, 1, tz=LOCAL_TZ),
    schedule=None,
    catchup=False,
    tags=["orquestra", "dashboard", "query"],
    access_control={"Op": {"can_read", "can_edit"}},
) as dag:
    consultar_dashboard_task = PythonOperator(
        task_id="consultar_dashboard",
        python_callable=consultar_dashboard,
        do_xcom_push=True,
    )

