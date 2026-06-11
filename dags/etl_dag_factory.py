"""
etl_dag_factory.py
Gera DAGs automaticamente a partir de pipelines cadastrados (dag_criada=0).

Parâmetros opcionais no conf (via Admin ORQUESTRA):
  force_all      (bool) — regenera todas as DAGs, incluindo as já criadas
  filter_project (str)  — restringe a regeneração a um projeto específico

Comportamento fail-fast (desde v2.3.0):
  Se log_end detecta que o job falhou (status FAILED/DESCONHECIDO),
  levanta RuntimeError para interromper a cadeia de tarefas seguintes.
  t_teams_error (ONE_FAILED) é então acionado automaticamente.
"""
from __future__ import annotations
import os
import ast
from collections import defaultdict
from datetime import timedelta
import pendulum
from airflow import DAG
from airflow.models import Variable
from airflow.operators.python import PythonOperator
from airflow.providers.microsoft.mssql.hooks.mssql import MsSqlHook

DAG_ID        = "etl_dag_factory"
MSSQL_CONN_ID = "SQL14_DMDB41"
LOCAL_TZ      = "America/Sao_Paulo"
SSH_CONN_ID   = "ssh_lnxprd021"
BASE_LOG_ROOT = "/Projetos/BI_CVP/Logs/Airflow"

default_args = {"owner": "airflow", "depends_on_past": False, "retries": 0}


def _get_output_root():
    try:
        root = Variable.get("DAG_FACTORY_OUTPUT").rstrip("/")
        if root:
            return root
    except Exception:
        pass
    try:
        from airflow.configuration import conf
        return conf.get("core", "dags_folder").rstrip("/")
    except Exception:
        return "/opt/airflow/dags"


def _time_to_cron(t):
    parts = t.split(":")
    return f"{int(parts[1]) if len(parts) > 1 else 0} {int(parts[0])} * * *"


def _ind(code, n=4):
    pad = " " * n
    return "\n".join(pad + ln if ln.strip() else ln for ln in code.split("\n"))


_TYPE_ALIAS = {
    "bash":         "shell",
    "shell script": "shell",
    "proc":         "storedproc",
    "stored proc":  "storedproc",
    "stored_proc":  "storedproc",
    "procedure":    "storedproc",
}


def _varname(job_name: str) -> str:
    """Converte um nome de job em identificador Python válido (substitui chars inválidos por _)."""
    import re as _re
    return _re.sub(r"[^A-Za-z0-9_]", "_", job_name)


def _task_block(job, project, pipeline):
    name  = job["job_name"]
    vname = _varname(name)   # identificador Python seguro
    jtype = _TYPE_ALIAS.get(job["job_type"].lower().strip(), job["job_type"].lower().strip())
    jcmd  = job["job_command"] or ""

    if jtype == "datastage":
        main = "\n".join([
            f't_job_{vname} = DataStageOperator(',
            f'    task_id="{name}",',
            f'    project=PROJECT_NAME,',
            f'    job_name="{name}",',
            f'    ssh_conn_id=SSH_CONN_ID,',
            f')',
        ])
    elif jtype == "shell":
        cmd = jcmd or "echo 'comando nao configurado'"
        ssh = job.get("ssh_conn_id") or None
        ssh_val = f'"{ssh}"' if ssh else 'SSH_CONN_ID'
        main = "\n".join([
            f't_job_{vname} = SSHOperator(',
            f'    task_id="{name}",',
            f'    ssh_conn_id={ssh_val},',
            f'    command="{cmd}",',
            f'    cmd_timeout=None,',
            f'    do_xcom_push=True,',
            f')',
        ])
    elif jtype == "python":
        mod = jcmd or name
        main = "\n".join([
            f'def _run_{vname}(**context):',
            f'    import importlib',
            f'    mod = importlib.import_module("{mod}")',
            f'    if hasattr(mod, "run"): mod.run(**context)',
            f'    elif hasattr(mod, "main"): mod.main()',
            f'',
            f't_job_{vname} = PythonOperator(',
            f'    task_id="{name}",',
            f'    python_callable=_run_{vname},',
            f')',
        ])
    elif jtype == "storedproc":
        proc = jcmd or name
        main = "\n".join([
            f'def _run_{vname}(**context):',
            f'    hook = MsSqlHook(mssql_conn_id=MSSQL_CONN_ID)',
            f'    hook.run("EXEC {proc}")',
            f'',
            f't_job_{vname} = PythonOperator(',
            f'    task_id="{name}",',
            f'    python_callable=_run_{vname},',
            f')',
        ])
    elif jtype == "sql":
        sql_stmt = jcmd or f"SELECT 1 -- job {name}"
        safe_sql = sql_stmt.replace('"', '\\"').replace('\n', ' ')
        main = "\n".join([
            f'def _run_{vname}(**context):',
            f'    hook = MsSqlHook(mssql_conn_id=MSSQL_CONN_ID)',
            f'    hook.run("{safe_sql}")',
            f'',
            f't_job_{vname} = PythonOperator(',
            f'    task_id="{name}",',
            f'    python_callable=_run_{vname},',
            f')',
        ])
    elif jtype == "http":
        url = jcmd or "https://httpbin.org/get"
        main = "\n".join([
            f'def _run_{vname}(**context):',
            f'    resp = requests.get("{url}", timeout=30)',
            f'    resp.raise_for_status()',
            f'    print(f"HTTP {name}: status={{resp.status_code}}")',
            f'',
            f't_job_{vname} = PythonOperator(',
            f'    task_id="{name}",',
            f'    python_callable=_run_{vname},',
            f')',
        ])
    else:
        main = "\n".join([
            f't_job_{vname} = PythonOperator(',
            f'    task_id="{name}",',
            f'    python_callable=lambda **kw: print("job_type desconhecido: {jtype}"),',
            f')',
        ])

    log_start = "\n".join([
        f't_start_{vname} = PythonOperator(',
        f'    task_id="log_start_{name}",',
        f'    python_callable=log_start,',
        f'    op_kwargs={{"job_name": "{name}", "task_key": "{name}"}},',
        f')',
    ])
    log_end = "\n".join([
        f't_end_{vname} = PythonOperator(',
        f'    task_id="log_end_{name}",',
        f'    python_callable=log_end,',
        f'    op_kwargs={{"job_name": "{name}", "task_key": "{name}", "upstream_task_id": "{name}"}},',
        f'    trigger_rule=TriggerRule.ALL_DONE,',
        f')',
    ])

    return "\n\n".join([log_start, main, log_end])


def _generate_dag_source(pipeline, jobs):
    pname      = pipeline["pipeline_name"]
    project    = pipeline["project_name"]
    domain     = pipeline["domain"]
    tags_raw   = pipeline["tags"]
    sched      = pipeline["scheduled_time"]
    depends_on = (pipeline.get("depends_on") or "").strip() or None
    is_prd  = (pipeline.get("ambiente") or "PROD").upper() == "PROD"
    f_ini   = bool(pipeline["envia_msg_inicio"]) and is_prd
    f_fim   = bool(pipeline["envia_msg_fim"])    and is_prd
    f_err   = bool(pipeline["envia_msg_erro"])   and is_prd
    dag_start_date_raw = pipeline.get("dag_start_date")

    retries_val         = int(pipeline.get("retries_count") or 1)
    retry_delay_val     = int(pipeline.get("retry_delay_seconds") or 300)
    max_active_runs_val = int(pipeline.get("max_active_runs") or 1)
    pool_name_val       = (pipeline.get("pool_name") or "").strip() or None
    sla_minutos_val     = pipeline.get("sla_minutos")
    ssh_conn_id_val     = (pipeline.get("ssh_conn_id") or "ssh_lnxprd021").strip()

    cron        = _time_to_cron(sched)
    base_log    = BASE_LOG_ROOT
    user_tags   = [t.strip() for t in tags_raw.split(",") if t.strip()]
    all_tags    = list(dict.fromkeys([project, domain] + user_tags))
    sorted_jobs = sorted(jobs, key=lambda j: j["execution_order"])
    first       = _varname(sorted_jobs[0]["job_name"])
    first_name  = sorted_jobs[0]["job_name"]
    others      = sorted_jobs[1:]
    all_ends    = [f"t_end_{_varname(j['job_name'])}" for j in sorted_jobs]

    def _jtypes(jobs):
        return {_TYPE_ALIAS.get(j["job_type"].lower(), j["job_type"].lower()) for j in jobs}

    job_types  = _jtypes(sorted_jobs)
    ds_needed  = "datastage" in job_types
    sh_needed  = "shell"     in job_types

    # Seção de imports
    import_lines = ["from airflow import DAG"]
    import_lines.append("from datetime import timedelta")
    if ds_needed:
        import_lines.append("from utils.datastage_operator import DataStageOperator")
    if sh_needed:
        import_lines.append("from airflow.providers.ssh.operators.ssh import SSHOperator")
    import_lines += [
        "from airflow.operators.python import PythonOperator",
        "from airflow.providers.microsoft.mssql.hooks.mssql import MsSqlHook",
        "from airflow.utils.trigger_rule import TriggerRule",
        "from airflow.utils.state import State",
        "from airflow.models import Variable",
        "",
        "import pendulum",
        "import socket",
        "import re",
        "import requests",
    ]

    # Constantes
    consts_lines = [
        f'DAG_ID        = "{pname}"',
        f'SSH_CONN_ID   = "{ssh_conn_id_val}"',
        f'MSSQL_CONN_ID = "SQL14_DMDB41"',
        f'PROJECT_NAME  = "{project}"',
        f'DOMAIN        = "{domain}"',
        f'PIPELINE_NAME = "{pname}"',
        f'BASE_LOG_DIR  = "{base_log}"',
        f'LOCAL_TZ      = "America/Sao_Paulo"',
        f'TEAMS_WEBHOOK_VAR = "TEAMS_WEBHOOK_URL_CVP"',
        f'default_args  = {{"owner": "airflow", "depends_on_past": False, "retries": {retries_val}, "retry_delay": timedelta(seconds={retry_delay_val})}}',
        f'JOBS          = {repr([j["job_name"] for j in sorted_jobs])}',
    ]
    if depends_on:
        consts_lines.append(f'DEPENDS_ON_DAG_ID = "{depends_on}"')
    if pool_name_val:
        consts_lines.append(f'POOL_NAME = "{pool_name_val}"')
    consts_str = "\n".join(consts_lines)

    # Helpers
    helpers_lines = [
        "def _now_str():",
        "    return pendulum.now(LOCAL_TZ).to_datetime_string()",
        "",
        "def _build_log_file(job_name, execution_id):",
        '    return f"{BASE_LOG_DIR}/{PROJECT_NAME}/{job_name}/{job_name}_{execution_id}.log"',
        "",
        "def _extract_status_code(stdout):",
        "    if not stdout: return None",
        r'    json_m = re.findall(r"\"status_code\"\s*:\s*(-?\d+)", stdout)',
        "    if json_m: return int(json_m[-1])",
        r'    m = re.search(r"Job Status Code:\s*(-?\d+)", stdout)',
        "    if m: return int(m.group(1))",
        r'    raw_m = re.findall(r"Status code\s*=\s*(-?\d+)", stdout)',
        "    if raw_m: return int(raw_m[-1])",
        "    return None",
        "",
        "def _status_from_code(code, upstream_state):",
        '    if code == 1:  return "SUCCESS"',
        '    if code == 2:  return "SUCCESS"  # WARNING = finalizou, conta como sucesso',
        '    if code is not None: return "FAILED"',
        "    if upstream_state == State.SUCCESS: return \"SUCCESS\"",
        '    return "FAILED"',
        "",
        "def _exec_telemetry(hook, execution_id, job_name, task_key, status,",
        "                    start_time, end_time, duration_seconds, log_file, host=None):",
        "    if host is None:",
        "        host = socket.gethostname()",
        "    sql = (",
        '        "EXEC dbo.sp_etl_job_execution_log "',
        '        "@execution_id=%s, @project=%s, @job_name=%s, @pipeline=%s, "',
        '        "@host=%s, @start_time=%s, @end_time=%s, @duration_seconds=%s, "',
        '        "@status=%s, @log_file=%s, @task_id=%s"',
        "    )",
        "    hook.run(sql, parameters=(",
        "        execution_id, PROJECT_NAME, job_name, PIPELINE_NAME,",
        '        host, start_time or "", end_time or "",',
        "        duration_seconds, status, log_file, task_key,",
        "    ))",
        "",
        "def _update_status_code(hook, execution_id, job_name, task_key, status_code):",
        "    hook.run(",
        '        "UPDATE dbo.etl_job_execution SET status_code=%s, updated_at=GETDATE() "',
        '        "WHERE execution_id=%s AND job_name=%s AND task_id=%s",',
        "        parameters=(status_code, execution_id, job_name, task_key),",
        "    )",
        "",
        "def _teams_post_card(title, facts, status='INFO', subtitle=None):",
        "    try:",
        "        webhook_url = Variable.get(TEAMS_WEBHOOK_VAR)",
        "    except Exception:",
        "        print(f\"[TEAMS] Variable '{TEAMS_WEBHOOK_VAR}' nao encontrada.\")",
        "        return",
        '    icon = {"SUCCESS": "🟢", "WARNING": "🟡", "FAILED": "🔴", "INFO": "🔵"}.get(status, "⚪")',
        '    color = {"SUCCESS": "Good", "WARNING": "Warning", "FAILED": "Attention", "INFO": "Accent"}.get(status, "Default")',
        "    body = [",
        '        {"type": "TextBlock", "text": f"{icon} {title}", "size": "Large", "weight": "Bolder", "wrap": True, "color": color},',
        "    ]",
        "    if subtitle:",
        '        body.append({"type": "TextBlock", "text": subtitle, "wrap": True, "spacing": "None", "isSubtle": True})',
        "    if facts:",
        '        body.append({"type": "FactSet", "spacing": "Medium", "facts": facts})',
        "    payload = {",
        '        "type": "message",',
        '        "attachments": [{',
        '            "contentType": "application/vnd.microsoft.card.adaptive",',
        '            "content": {',
        '                "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",',
        '                "type": "AdaptiveCard", "version": "1.4",',
        '                "body": body,',
        "            },",
        "        }],",
        "    }",
        "    try:",
        "        resp = requests.post(webhook_url, json=payload, timeout=15)",
        "        print(f\"[TEAMS] status={resp.status_code}\")",
        "    except Exception as e:",
        "        print(f\"[TEAMS] Falha: {e}\")",
        "",
        "def _fact(title, value):",
        '    return {"title": title, "value": str(value) if value is not None else "—"}',
        "",
        "def _fmt_duration(seconds):",
        "    if not seconds: return '—'",
        "    s = int(seconds)",
        "    h, rem = divmod(s, 3600)",
        "    m, sec = divmod(rem, 60)",
        "    if h: return f'{h}h {m}min {sec}s'",
        "    if m: return f'{m}min {sec}s'",
        "    return f'{sec}s'",
        "",
        "def teams_start(**context):",
        "    execution_id = context['ts_nodash']",
        "    _teams_post_card(",
        '        title="Execução iniciada",',
        '        subtitle=f"O pipeline {PIPELINE_NAME} foi iniciado e está em processamento.",',
        "        facts=[",
        '            _fact("Pipeline",      PIPELINE_NAME),',
        '            _fact("Domínio",       DOMAIN),',
        '            _fact("Projeto",       PROJECT_NAME),',
        '            _fact("Execution ID",  execution_id),',
        '            _fact("Início",        _now_str()),',
        "        ],",
        "        status='INFO',",
        "    )",
        "",
        "def teams_end(**context):",
        "    execution_id = context['ts_nodash']",
        "    hook = MsSqlHook(mssql_conn_id=MSSQL_CONN_ID)",
        "    row = hook.get_first(",
        '        "SELECT pipeline, MIN(start_time), MAX(end_time), COALESCE(SUM(duration_seconds),0), "',
        '        "CASE WHEN SUM(CASE WHEN status=\'FAILED\' THEN 1 ELSE 0 END)>0 THEN \'FAILED\' "',
        '        "     WHEN SUM(CASE WHEN status=\'WARNING\' THEN 1 ELSE 0 END)>0 THEN \'WARNING\' "',
        '        "     WHEN SUM(CASE WHEN status=\'SUCCESS\' THEN 1 ELSE 0 END)>0 THEN \'SUCCESS\' "',
        '        "     ELSE \'FAILED\' END "',
        '        "FROM dbo.etl_job_execution WHERE execution_id=%s AND pipeline=%s GROUP BY pipeline",',
        "        parameters=(execution_id, PIPELINE_NAME),",
        "    )",
        "    if not row:",
        "        _teams_post_card(",
        '            title="Execução finalizada — sem dados",',
        '            subtitle=f"O pipeline {PIPELINE_NAME} foi concluído, mas não foram encontrados registros de execução.",',
        '            facts=[_fact("Pipeline", PIPELINE_NAME), _fact("Execution ID", execution_id)],',
        "            status='WARNING',",
        "        )",
        "        return",
        "    pipeline, inicio, fim, dur_seg, status_geral = row",
        '    titles = {"SUCCESS": "Execução concluída com sucesso", "WARNING": "Execução concluída com avisos", "FAILED": "Execução finalizada com falha"}',
        '    subtitles = {',
        '        "SUCCESS": f"O pipeline {pipeline} foi executado e finalizado sem erros.",',
        '        "WARNING": f"O pipeline {pipeline} foi concluído, mas registrou avisos durante a execução.",',
        '        "FAILED":  f"O pipeline {pipeline} foi encerrado com falha. Verifique os jobs com erro.",',
        "    }",
        "    _teams_post_card(",
        "        title=titles.get(status_geral, 'Execução finalizada'),",
        "        subtitle=subtitles.get(status_geral),",
        "        facts=[",
        '            _fact("Pipeline",      pipeline),',
        '            _fact("Domínio",       DOMAIN),',
        '            _fact("Projeto",       PROJECT_NAME),',
        '            _fact("Execution ID",  execution_id),',
        '            _fact("Início",        inicio.strftime(\'%d/%m/%Y %H:%M\') if inicio else \'—\'),',
        '            _fact("Fim",           fim.strftime(\'%d/%m/%Y %H:%M\') if fim else \'—\'),',
        '            _fact("Duração",       _fmt_duration(dur_seg)),',
        "        ],",
        "        status=status_geral,",
        "    )",
        "",
        "def teams_error(**context):",
        "    execution_id = context['ts_nodash']",
        "    hook = MsSqlHook(mssql_conn_id=MSSQL_CONN_ID)",
        "    # Resumo do pipeline (mesma query do teams_end)",
        "    row = hook.get_first(",
        '        "SELECT pipeline, MIN(start_time), MAX(end_time), COALESCE(SUM(duration_seconds),0) "',
        '        "FROM dbo.etl_job_execution WHERE execution_id=%s AND pipeline=%s GROUP BY pipeline",',
        "        parameters=(execution_id, PIPELINE_NAME),",
        "    )",
        "    pipeline_nm = row[0] if row else PIPELINE_NAME",
        "    inicio      = row[1] if row else None",
        "    fim         = row[2] if row else None",
        "    dur_seg     = row[3] if row else 0",
        "    # Jobs com falha — detalhado",
        "    try:",
        "        failed = hook.get_records(",
        '            "SELECT job_name, start_time, end_time, COALESCE(duration_seconds,0), log_file "',
        '            "FROM dbo.etl_job_execution "',
        '            "WHERE execution_id=%s AND pipeline=%s AND status=\'FAILED\' "',
        '            "ORDER BY start_time",',
        "            parameters=(execution_id, PIPELINE_NAME),",
        "        )",
        "    except Exception:",
        "        failed = []",
        "    facts = [",
        '        _fact("Pipeline",      pipeline_nm),',
        '        _fact("Domínio",       DOMAIN),',
        '        _fact("Projeto",       PROJECT_NAME),',
        '        _fact("Execution ID",  execution_id),',
        '        _fact("Início",        inicio.strftime(\'%d/%m/%Y %H:%M\') if inicio else \'—\'),',
        '        _fact("Fim",           fim.strftime(\'%d/%m/%Y %H:%M\') if fim else \'—\'),',
        '        _fact("Duração total", _fmt_duration(dur_seg)),',
        "    ]",
        "    if failed:",
        '        facts.append(_fact("─────────────", "Jobs com falha"))',
        "        for jname, jstart, jend, jdur, jlog in failed:",
        '            facts.append(_fact("Job",     jname))',
        '            facts.append(_fact("  Início",  jstart.strftime(\'%d/%m/%Y %H:%M\') if jstart else \'—\'))',
        '            facts.append(_fact("  Fim",     jend.strftime(\'%d/%m/%Y %H:%M\') if jend else \'—\'))',
        '            facts.append(_fact("  Duração", _fmt_duration(jdur)))',
        "    else:",
        '        facts.append(_fact("Job com falha", "Não identificado"))',
        "    _teams_post_card(",
        '        title="Falha na execução",',
        '        subtitle=f"O pipeline {pipeline_nm} foi interrompido por falha em um ou mais jobs. Verifique os detalhes abaixo.",',
        "        facts=facts,",
        "        status='FAILED',",
        "    )",
        "",
        "def log_start(job_name, task_key, **context):",
        "    hook = MsSqlHook(mssql_conn_id=MSSQL_CONN_ID)",
        "    execution_id = context['ts_nodash']",
        "    _exec_telemetry(hook, execution_id, job_name, task_key, 'RUNNING',",
        "                    _now_str(), '', 0, _build_log_file(job_name, execution_id))",
        "",
        "def _update_last_execution():",
        "    hook = MsSqlHook(mssql_conn_id=MSSQL_CONN_ID)",
        "    hook.run(",
        '        "UPDATE dbo.etl_pipeline SET last_execution=GETDATE(), updated_at=GETDATE() "',
        '        "WHERE pipeline_name=%s",',
        "        parameters=(PIPELINE_NAME,),",
        "    )",
        "",
        "def log_end(job_name, task_key, upstream_task_id, **context):",
        "    hook = MsSqlHook(mssql_conn_id=MSSQL_CONN_ID)",
        "    execution_id = context['ts_nodash']",
        "    end_time = _now_str()",
        "    job_ti = context['dag_run'].get_task_instance(upstream_task_id)",
        "    upstream_state = job_ti.state if job_ti else None",
        "    ti = context['ti']",
        "    stdout = ti.xcom_pull(task_ids=upstream_task_id)",
        "    status_code = _extract_status_code(str(stdout) if stdout else '')",
        "    final_status = _status_from_code(status_code, upstream_state)",
        "    duration_seconds = 0",
        "    if job_ti and job_ti.start_date and job_ti.end_date:",
        "        duration_seconds = int((job_ti.end_date - job_ti.start_date).total_seconds())",
        "    _exec_telemetry(hook, execution_id, job_name, task_key, final_status,",
        "                    '', end_time, duration_seconds, _build_log_file(job_name, execution_id))",
        "    _update_status_code(hook, execution_id, job_name, task_key, status_code)",
        "    try:",
        "        _update_last_execution()",
        "    except Exception as _ule_exc:",
        "        print(f'[log_end] Aviso: nao foi possivel atualizar last_execution — {_ule_exc}')",
        "    if final_status in ('FAILED', 'DESCONHECIDO'):",
        "        raise RuntimeError(",
        "            f\"Job '{job_name}' finalizou com status {final_status} — \"",
        "            \"execucao interrompida. Corrija o erro antes de reprocessar.\"",
        "        )",
    ]
    helpers_str = "\n".join(helpers_lines)

    # Bloco with DAG
    teams_tasks = []
    if f_ini:
        teams_tasks.append("\n".join([
            't_teams_start = PythonOperator(',
            '    task_id="teams_start",',
            '    python_callable=teams_start,',
            ')',
        ]))
    if f_fim:
        teams_tasks.append("\n".join([
            't_teams_end = PythonOperator(',
            '    task_id="teams_end",',
            '    python_callable=teams_end,',
            '    trigger_rule=TriggerRule.ALL_DONE,',
            ')',
        ]))
    if f_err:
        teams_tasks.append("\n".join([
            't_teams_error = PythonOperator(',
            '    task_id="teams_error",',
            '    python_callable=teams_error,',
            '    trigger_rule=TriggerRule.ONE_FAILED,',
            ')',
        ]))

    job_blocks = [_task_block(j, project, pname) for j in sorted_jobs]

    # S4: ExternalTaskSensor — suporte a múltiplas dependências
    dep_list = [d.strip() for d in depends_on.split(",") if d.strip()] if depends_on else []
    sensor_block = ""
    sensor_names = []
    if dep_list:
        if "from airflow.sensors.external_task import ExternalTaskSensor" not in import_lines:
            import_lines.append("from airflow.sensors.external_task import ExternalTaskSensor")
        sensor_parts = []
        for dep in dep_list:
            sname = f"t_sensor_{dep}"
            sensor_names.append(sname)
            sensor_parts.append("\n".join([
                f'{sname} = ExternalTaskSensor(',
                f'    task_id="wait_{dep}",',
                f'    external_dag_id="{dep}",',
                f'    mode="reschedule",',
                f'    timeout=3600,',
                f'    poke_interval=60,',
                f')',
            ]))
        sensor_block = "\n\n".join(sensor_parts)
    # Rebuild imports_str after potential append
    imports_str = "\n".join(import_lines)

    if f_ini:
        first_chain = f"t_start_{first} >> t_teams_start >> t_job_{first} >> t_end_{first}"
    else:
        first_chain = f"t_start_{first} >> t_job_{first} >> t_end_{first}"

    dep_lines = [
        f"previous = t_end_{first}",
        first_chain,
    ]
    if sensor_names:
        sensors_ref = "[" + ", ".join(sensor_names) + "]"
        dep_lines.insert(0, f"{sensors_ref} >> t_start_{first}")

    for j in others:
        n = _varname(j["job_name"])
        dep_lines.append(f"previous >> t_start_{n} >> t_job_{n} >> t_end_{n}")
        dep_lines.append(f"previous = t_end_{n}")

    end_tasks_ref = "[" + ", ".join(all_ends) + "]"
    dep_lines.append(f"end_tasks = {end_tasks_ref}")
    if f_fim:
        dep_lines.append(f"{end_tasks_ref} >> t_teams_end")
    if f_err:
        dep_lines.append(f"{end_tasks_ref} >> t_teams_error")

    with_parts = []
    if sensor_block:
        with_parts.append(_ind(sensor_block))
    for t in teams_tasks:
        with_parts.append(_ind(t))
    for b in job_blocks:
        with_parts.append(_ind(b))
    for d in dep_lines:
        with_parts.append("    " + d)

    if dag_start_date_raw:
        if hasattr(dag_start_date_raw, "year"):
            sd_y, sd_m, sd_d = dag_start_date_raw.year, dag_start_date_raw.month, dag_start_date_raw.day
        else:
            parts = str(dag_start_date_raw).split("-")
            sd_y, sd_m, sd_d = int(parts[0]), int(parts[1]), int(parts[2])
    else:
        sd_y, sd_m, sd_d = 2026, 1, 1

    dag_header_lines = [
        "with DAG(",
        "    dag_id=DAG_ID,",
        "    default_args=default_args,",
        f'    description="Pipeline {pname} - {project} / {domain}",',
        f"    start_date=pendulum.datetime({sd_y}, {sd_m}, {sd_d}, tz=LOCAL_TZ),",
        f'    schedule="{cron}",',
        "    catchup=False,",
        f"    max_active_runs={max_active_runs_val},",
    ]
    if sla_minutos_val is not None:
        dag_header_lines.append(f"    dagrun_timeout=timedelta(minutes={int(sla_minutos_val)}),")
    dag_header_lines += [
        f"    tags={repr(all_tags)},",
        ") as dag:",
    ]
    dag_header = "\n".join(dag_header_lines)

    dag_block = dag_header + "\n\n" + "\n\n".join(with_parts) + "\n"

    sep = "# " + "=" * 25
    parts = [
        imports_str,
        sep,
        f"# Gerado automaticamente por etl_dag_factory",
        f"# Pipeline: {pname} | Projeto: {project} | Dominio: {domain}",
        sep,
        consts_str,
        "",
        helpers_str,
        "",
        dag_block,
    ]
    return "\n".join(parts)


def gerar_dags(**context):
    hook        = MsSqlHook(mssql_conn_id=MSSQL_CONN_ID)
    output_root = _get_output_root()
    conf        = context["dag_run"].conf or {}

    force_all      = bool(conf.get("force_all", False))
    filter_project = (conf.get("filter_project") or "").strip()
    pipeline_name  = (conf.get("pipeline_name")  or "").strip()

    if pipeline_name:
        # Regerar pipeline específico — reseta dag_criada só para ele
        hook.run(
            "UPDATE dbo.etl_pipeline SET dag_criada=0, updated_at=GETDATE() "
            "WHERE pipeline_name=%s",
            parameters=(pipeline_name,),
        )
        print(f"[FACTORY] pipeline_name='{pipeline_name}' — dag_criada resetado para regeneração")
    elif force_all:
        if filter_project:
            hook.run(
                "UPDATE dbo.etl_pipeline SET dag_criada=0, updated_at=GETDATE() "
                "WHERE project_name=%s AND DAG_CRIADA=1",
                parameters=(filter_project,),
            )
            print(f"[FACTORY] force_all=True, project='{filter_project}' — dag_criada resetado")
        else:
            hook.run(
                "UPDATE dbo.etl_pipeline SET dag_criada=0, updated_at=GETDATE() "
                "WHERE DAG_CRIADA=1"
            )
            print("[FACTORY] force_all=True — dag_criada resetado para todos os pipelines")

    conn   = hook.get_conn()
    cursor = conn.cursor()
    cursor.execute("EXEC dbo.sp_etl_pipelines_pendentes_criar")

    pipelines_rows = cursor.fetchall()
    pipeline_cols  = [d[0].lower() for d in cursor.description]
    cursor.nextset()
    jobs_rows = cursor.fetchall()
    jobs_cols = [d[0].lower() for d in cursor.description]
    cursor.close()
    conn.close()

    if not pipelines_rows:
        print("[FACTORY] Nenhum pipeline pendente.")
        return

    pipelines = [dict(zip(pipeline_cols, row)) for row in pipelines_rows]
    jobs_all  = [dict(zip(jobs_cols, row))     for row in jobs_rows]

    # Supplement with advanced fields (not in SP result set)
    if pipelines:
        pnames_sql = ",".join(f"'{p['pipeline_name']}'" for p in pipelines)
        conn2 = hook.get_conn()
        cur2  = conn2.cursor()
        cur2.execute(
            f"SELECT pipeline_name, criticidade, sla_minutos, ambiente, "
            f"max_active_runs, retries_count, retry_delay_seconds, pool_name, descricao, dag_start_date "
            f"FROM dbo.etl_pipeline WHERE pipeline_name IN ({pnames_sql})"
        )
        adv_rows = cur2.fetchall()
        adv_cols = [d[0].lower() for d in cur2.description]
        cur2.close(); conn2.close()
        adv_map = {r[0]: dict(zip(adv_cols, r)) for r in adv_rows}
        for p in pipelines:
            p.update(adv_map.get(p['pipeline_name'], {}))

    jobs_by_pipeline = defaultdict(list)
    for j in jobs_all:
        jobs_by_pipeline[j["pipeline_name"]].append(j)

    geradas, erros = [], []

    for pipeline in pipelines:
        pname   = pipeline["pipeline_name"]
        project = pipeline["project_name"]
        domain  = pipeline["domain"]
        jobs    = jobs_by_pipeline.get(pname, [])

        if not jobs:
            print(f"[FACTORY] AVISO: '{pname}' sem jobs — ignorado.")
            continue

        dest_dir  = os.path.join(output_root, "generated", project, domain)
        os.makedirs(dest_dir, exist_ok=True)
        dest_file = os.path.join(dest_dir, f"{pname}.py")

        try:
            source = _generate_dag_source(pipeline, jobs)
        except Exception as e:
            erros.append(f"{pname}: erro ao gerar — {e}")
            continue

        try:
            ast.parse(source)
        except SyntaxError as e:
            erros.append(f"{pname}: sintaxe invalida — linha {e.lineno}: {e.msg}")
            print(f"[FACTORY] SINTAXE INVALIDA {pname}: linha {e.lineno} — {e.msg}")
            continue

        try:
            with open(dest_file, "w", encoding="utf-8") as f:
                f.write(source)
            print(f"[FACTORY] OK -> {dest_file}")
        except Exception as e:
            erros.append(f"{pname}: erro ao salvar — {e}")
            continue

        try:
            hook.run(
                "EXEC dbo.sp_etl_pipeline_upsert "
                "@pipeline_name=%s, @scheduled_time=%s, @active=%s, "
                "@envia_msg_inicio=%s, @envia_msg_fim=%s, @envia_msg_erro=%s, "
                "@dag_criada=1, @project_name=%s, @domain=%s, @tags=%s",
                parameters=(
                    pname, pipeline["scheduled_time"], 1,
                    int(pipeline["envia_msg_inicio"]),
                    int(pipeline["envia_msg_fim"]),
                    int(pipeline["envia_msg_erro"]),
                    project, domain, pipeline.get("tags", ""),
                ),
            )
            print(f"[FACTORY] dag_criada=1 -> '{pname}'")
        except Exception as e:
            erros.append(f"{pname}: dag gerada mas erro ao atualizar banco — {e}")

        geradas.append(pname)

    print(f"\n[FACTORY] Geradas: {len(geradas)} | Erros: {len(erros)}")
    for e in erros:
        print(f"  x {e}")

    if geradas:
        try:
            import httpx as _httpx
            api_url = Variable.get("ORQUESTRA_API_URL", default_var="http://orquestra-api:8000")
            r = _httpx.post(f"{api_url}/sync/pipeline-status", timeout=15)
            print(f"[FACTORY] sync/pipeline-status → HTTP {r.status_code}")
        except Exception as _e:
            print(f"[FACTORY] AVISO: sync/pipeline-status falhou (não bloqueante) — {_e}")

    if erros:
        raise RuntimeError(f"{len(erros)} pipeline(s) com erro:\n" + "\n".join(erros))


with DAG(
    dag_id=DAG_ID,
    default_args=default_args,
    description="Gera DAGs automaticamente a partir de pipelines com dag_criada=0",
    start_date=pendulum.datetime(2024, 1, 1, tz=LOCAL_TZ),
    schedule=None,
    catchup=False,
    tags=["factory", "infraestrutura", "gerador"],
    access_control={"Op": {"can_read", "can_edit"}},
) as dag:

    task_gerar = PythonOperator(
        task_id="gerar_dags",
        python_callable=gerar_dags,
    )
