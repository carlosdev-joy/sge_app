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
import re
import ast
import shlex
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


def _build_cron(pipeline):
    """Monta o cron a partir do agendamento do pipeline.

    Retorna (cron, horarios, dias_horarios_mes):
      - horarios: lista normalizada "HH:MM" quando o pipeline usa horários
        específicos (tipo 'custom'), None caso contrário.
      - dias_horarios_mes: dict {dia_do_mes: ["HH:MM", ...]} quando o tipo é
        'monthly_days_times', None caso contrário.
    Como um único cron não expressa horários arbitrários (ex: 09:00 e 10:30
    geram também 09:30 e 10:00), o cron dispara na união minuto×hora(×dia) e
    o check_agenda pula as combinações que não estão na lista configurada.
    """
    sched = str(pipeline.get("scheduled_time") or "06:00:00")
    stype = (pipeline.get("schedule_type") or "daily").lower().strip()
    horarios_raw = (pipeline.get("horarios_especificos") or "").strip()
    dias_semana  = (pipeline.get("dias_semana") or "").strip()
    dias_horarios_raw = (pipeline.get("dias_horarios_mes") or "").strip()
    parts = sched.split(":")
    h = int(parts[0]) if parts[0].isdigit() else 6
    m = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
    dow_expr = dias_semana if dias_semana else "*"

    if stype == "monthly_days_times" and dias_horarios_raw:
        import json
        try:
            entries = json.loads(dias_horarios_raw)
        except (ValueError, TypeError):
            entries = []
        dias_horarios = {}
        all_days, all_hours, all_mins = set(), set(), set()
        for entry in entries:
            try:
                dia = int(entry["dia"])
            except (KeyError, TypeError, ValueError):
                continue
            times = []
            for t in entry.get("horarios", []):
                tp = str(t).split(":")
                try:
                    hh, mm = int(tp[0]), int(tp[1]) if len(tp) > 1 else 0
                except ValueError:
                    continue
                times.append(f"{hh:02d}:{mm:02d}")
                all_hours.add(hh)
                all_mins.add(mm)
            if times:
                dias_horarios[dia] = sorted(times)
                all_days.add(dia)
        if dias_horarios:
            cron = (f"{','.join(map(str, sorted(all_mins)))} {','.join(map(str, sorted(all_hours)))} "
                    f"{','.join(map(str, sorted(all_days)))} * *")
            return cron, None, dias_horarios

    if horarios_raw:
        times = []
        for t in horarios_raw.split(","):
            t = t.strip()
            if not t:
                continue
            tp = t.split(":")
            try:
                times.append((int(tp[0]), int(tp[1]) if len(tp) > 1 else 0))
            except ValueError:
                continue
        if times:
            mins  = sorted({mm for _, mm in times})
            hours = sorted({hh for hh, _ in times})
            cron = (f"{','.join(map(str, mins))} {','.join(map(str, hours))} "
                    f"* * {dow_expr}")
            return cron, sorted(f"{hh:02d}:{mm:02d}" for hh, mm in times), None

    if stype == "hourly":
        return f"{m} * * * *", None, None
    if stype == "weekly":
        dow = pipeline.get("schedule_dow")
        return f"{m} {h} * * {int(dow) if dow is not None else 1}", None, None
    if stype == "monthly":
        dom = pipeline.get("schedule_dom")
        return f"{m} {h} {int(dom) if dom is not None else 1} * *", None, None
    if stype == "biweekly":  # quinzenal: dia D e D+15 de cada mês
        dom = pipeline.get("schedule_dom")
        d = int(dom) if dom is not None else 1
        return f"{m} {h} {d},{d + 15} * *", None, None
    return f"{m} {h} * * {dow_expr}", None, None


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


_PROC_NAME_RE  = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$")
_PARAM_NAME_RE = re.compile(r"^@?[A-Za-z_][A-Za-z0-9_]*$")


def _coerce_param_value(p):
    """Converte o valor fixo (sempre string vinda do banco/UI) para o tipo Python adequado."""
    val = p.get("param_value")
    ptype = (p.get("param_type") or "VARCHAR").upper()
    if val is None:
        return None
    if ptype == "INT":
        return int(val)
    if ptype == "BIT":
        return bool(int(val)) if str(val) not in ("True", "False") else val == "True"
    if ptype == "DECIMAL":
        return float(val)
    return str(val)  # VARCHAR, DATE, DATETIME — driver converte a partir de string


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
        verbose_line = f'    verbose_log=True,' if job.get("verbose_log") else ''
        main = "\n".join(filter(None, [
            f't_job_{vname} = DataStageOperator(',
            f'    task_id={name!r},',
            f'    project=PROJECT_NAME,',
            f'    job_name={name!r},',
            f'    ssh_conn_id=SSH_CONN_ID,',
            f'    queue_name=DS_QUEUE,',
            verbose_line,
            f')',
        ]))
    elif jtype == "shell":
        cmd = jcmd or "echo 'comando nao configurado'"
        # shlex.quote garante que o comando não escape das aspas no código gerado
        cmd_safe = shlex.quote(cmd)
        ssh = job.get("ssh_conn_id") or None
        ssh_val = f'"{ssh}"' if ssh else 'SSH_CONN_ID'
        main = "\n".join([
            f't_job_{vname} = ShellOperator(',
            f'    task_id={name!r},',
            f'    ssh_conn_id={ssh_val},',
            f'    command={cmd_safe},',
            f'    cmd_timeout=None,',
            f'    do_xcom_push=True,',
            f')',
        ])
    elif jtype == "python":
        mod = jcmd or name
        main = "\n".join([
            f't_job_{vname} = PythonModuleOperator(',
            f'    task_id={name!r},',
            f'    module={mod!r},',
            f')',
        ])
    elif jtype == "storedproc":
        proc_raw = jcmd or name
        proc = proc_raw if _PROC_NAME_RE.match(proc_raw) else None
        conn_id  = job.get("mssql_conn_id") or None
        conn_val = repr(conn_id) if conn_id else "MSSQL_CONN_ID"
        valid_params = [p for p in (job.get("params") or []) if _PARAM_NAME_RE.match(p.get("param_name") or "")]

        if proc is None:
            main = "\n".join([
                f'def _run_{vname}(**context):',
                f'    raise ValueError("nome de procedure invalido: {proc_raw!r}")',
                f'',
                f't_job_{vname} = PythonOperator(',
                f'    task_id={name!r},',
                f'    python_callable=_run_{vname},',
                f')',
            ])
        else:
            # Apenas CHAMA o StoredProcOperator — o EXEC, o bind de parâmetros e o
            # log do retorno/erro vivem no operador (mudanças não exigem regenerar).
            params_payload = [
                {"name": p["param_name"], "type": p.get("param_type"), "value": p.get("param_value")}
                for p in valid_params
            ]
            mssql_db = (job.get("mssql_database") or "").strip() or None
            main = "\n".join([
                f't_job_{vname} = StoredProcOperator(',
                f'    task_id={name!r},',
                f'    proc={proc!r},',
                f'    mssql_conn_id={conn_val},',
                f'    database={mssql_db!r},',
                f'    params={params_payload!r},',
                f')',
            ])
    elif jtype == "sql":
        sql_stmt = jcmd or f"SELECT 1 -- job {name}"
        main = "\n".join([
            f't_job_{vname} = SqlOperator(',
            f'    task_id={name!r},',
            f'    sql={sql_stmt!r},',
            f'    mssql_conn_id=MSSQL_CONN_ID,',
            f')',
        ])
    elif jtype == "http":
        url = jcmd or "https://httpbin.org/get"
        main = "\n".join([
            f't_job_{vname} = HttpCallOperator(',
            f'    task_id={name!r},',
            f'    url={url!r},',
            f')',
        ])
    else:
        main = "\n".join([
            f't_job_{vname} = PythonOperator(',
            f'    task_id={name!r},',
            f'    python_callable=lambda **kw: print("job_type desconhecido: {jtype}"),',
            f')',
        ])

    log_start = "\n".join([
        f't_start_{vname} = PythonOperator(',
        f'    task_id={("log_start_" + name)!r},',
        f'    python_callable=log_start,',
        f'    op_kwargs={{"job_name": {name!r}, "task_key": {name!r}}},',
        f')',
    ])
    log_end = "\n".join([
        f't_end_{vname} = PythonOperator(',
        f'    task_id={("log_end_" + name)!r},',
        f'    python_callable=log_end,',
        f'    op_kwargs={{"job_name": {name!r}, "task_key": {name!r}, "upstream_task_id": {name!r}}},',
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
    # Fase 4 — scheduling avançado
    calendario_val      = (pipeline.get("calendario_nome") or "").strip() or None
    dias_uteis_val      = bool(pipeline.get("somente_dias_uteis") or 0)
    trigger_dep_val     = bool(pipeline.get("trigger_por_dependencia") or 0)
    _DS_QUEUE_MAP = {"ALTA": "HighPriorityJobs", "CRITICA": "HighPriorityJobs",
                     "MEDIA": "MediumPriorityJobs", "BAIXA": "LowPriorityJobs"}
    ds_queue_val = _DS_QUEUE_MAP.get((pipeline.get("criticidade") or "").upper().strip())
    runbook_val  = (pipeline.get("runbook_md") or "").strip() or None

    cron, horarios_list, dias_horarios_mes = _build_cron(pipeline)
    base_log    = BASE_LOG_ROOT
    user_tags   = [t.strip() for t in tags_raw.split(",") if t.strip()]
    all_tags    = list(dict.fromkeys([project, domain] + user_tags))
    sorted_jobs = sorted(jobs, key=lambda j: j["execution_order"])
    # Group by execution_order — same order → parallel execution
    _grp_key = lambda j: j["execution_order"]
    job_groups = []
    _last_key = object()
    for j in sorted_jobs:
        if j["execution_order"] != _last_key:
            job_groups.append([])
            _last_key = j["execution_order"]
        job_groups[-1].append(j)
    first       = _varname(job_groups[0][0]["job_name"])
    first_name  = job_groups[0][0]["job_name"]
    others      = sorted_jobs[1:]   # kept for jtypes — not used for chaining anymore
    all_ends    = [f"t_end_{_varname(j['job_name'])}" for j in sorted_jobs]

    def _jtypes(jobs):
        return {_TYPE_ALIAS.get(j["job_type"].lower(), j["job_type"].lower()) for j in jobs}

    job_types   = _jtypes(sorted_jobs)
    ds_needed   = "datastage"  in job_types
    sh_needed   = "shell"      in job_types
    sp_needed   = "storedproc" in job_types
    py_needed   = "python"     in job_types
    sql_needed  = "sql"        in job_types
    http_needed = "http"       in job_types

    # Seção de imports
    import_lines = ["from airflow import DAG"]
    import_lines.append("from datetime import timedelta")
    if ds_needed:
        import_lines.append("from utils.datastage_operator import DataStageOperator")
    # Operadores reutilizáveis (utils/job_operators) — só os tipos presentes.
    _ops = []
    if sh_needed:   _ops.append("ShellOperator")
    if sp_needed:   _ops.append("StoredProcOperator")
    if sql_needed:  _ops.append("SqlOperator")
    if py_needed:   _ops.append("PythonModuleOperator")
    if http_needed: _ops.append("HttpCallOperator")
    if _ops:
        import_lines.append("from utils.job_operators import " + ", ".join(_ops))
    import_lines += [
        "from airflow.operators.python import PythonOperator, ShortCircuitOperator",
        "from airflow.operators.empty import EmptyOperator",
        "from airflow.datasets import Dataset",
        "from airflow.providers.microsoft.mssql.hooks.mssql import MsSqlHook",
        "from airflow.utils.trigger_rule import TriggerRule",
        "from airflow.utils.state import State",
        "from airflow.models import Variable",
        "",
        "import pendulum",
        "import socket",
        "import re",
        "import json",
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
        f'DS_QUEUE      = {repr(ds_queue_val)}',  # None = usa fila padrão do projeto DS
        f'RUNBOOK_MD    = {repr(runbook_val)}',
        f'CALENDARIO_NOME    = {repr(calendario_val)}',
        f'SOMENTE_DIAS_UTEIS = {dias_uteis_val}',
        f'HORARIOS_ESPECIFICOS = {repr(horarios_list)}',
        f'DIAS_HORARIOS_MES = {repr(dias_horarios_mes)}',
        f'DATASET_URI   = "orq://pipeline/{pname}"',
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
        "    # O operador devolve JSON com o status_code da SEQUENCE no topo. NUNCA",
        "    # usar o ultimo \"status_code\" do blob: child_jobs tambem tem esse campo,",
        "    # entao um job filho ABORTED marcaria o pipeline como FAILED por engano.",
        "    try:",
        "        _obj = json.loads(stdout)",
        "        if isinstance(_obj, dict) and _obj.get('status_code') is not None:",
        "            return int(_obj['status_code'])",
        "    except Exception:",
        "        pass",
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
        "    if RUNBOOK_MD:",
        '        facts.append(_fact("📖 Runbook", RUNBOOK_MD[:400] + ("…" if len(RUNBOOK_MD) > 400 else "")))',
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
        "",
        "def check_agenda(**context):",
        "    \"\"\"Fase 4 — blackout/freeze, dias úteis e calendário de feriados.",
        "    Retorna False (ShortCircuit) para pular a execução inteira.\"\"\"",
        "    # Horários específicos: o cron dispara na união minuto×hora;",
        "    # só executa se o horário agendado estiver na lista configurada.",
        "    if HORARIOS_ESPECIFICOS and not str(context.get('run_id', '')).startswith('manual'):",
        "        _die = context.get('data_interval_end') or context.get('logical_date')",
        "        if _die is not None:",
        "            _hhmm = _die.in_timezone(LOCAL_TZ).strftime('%H:%M')",
        "            if _hhmm not in HORARIOS_ESPECIFICOS:",
        "                print(f\"[AGENDA] {_hhmm} fora dos horarios configurados {HORARIOS_ESPECIFICOS} — execucao pulada.\")",
        "                return False",
        "    # Dia + hora específico: o cron dispara na união dia×minuto×hora;",
        "    # só executa se (dia, horario) atual estiver configurado para aquele dia.",
        "    if DIAS_HORARIOS_MES and not str(context.get('run_id', '')).startswith('manual'):",
        "        _die = context.get('data_interval_end') or context.get('logical_date')",
        "        if _die is not None:",
        "            _local = _die.in_timezone(LOCAL_TZ)",
        "            _dia = _local.day",
        "            _hhmm = _local.strftime('%H:%M')",
        "            if _hhmm not in DIAS_HORARIOS_MES.get(_dia, []):",
        "                print(f\"[AGENDA] dia {_dia} as {_hhmm} fora da configuracao {DIAS_HORARIOS_MES} — execucao pulada.\")",
        "                return False",
        "    hook = MsSqlHook(mssql_conn_id=MSSQL_CONN_ID)",
        "    try:",
        "        row = hook.get_first(",
        '            "SELECT TOP 1 motivo FROM dbo.etl_blackout "',
        '            "WHERE ativo=1 AND GETDATE() BETWEEN inicio AND fim "',
        '            "AND (escopo IS NULL OR escopo=%s OR escopo=%s)",',
        "            parameters=(PROJECT_NAME, PIPELINE_NAME),",
        "        )",
        "        if row:",
        "            print(f\"[AGENDA] Blackout vigente: {row[0]} — execucao pulada.\")",
        "            return False",
        "    except Exception as e:",
        "        print(f\"[AGENDA] Aviso: verificacao de blackout falhou ({e}) — seguindo.\")",
        "    if SOMENTE_DIAS_UTEIS and pendulum.now(LOCAL_TZ).weekday() >= 5:",
        "        print(\"[AGENDA] Fim de semana e pipeline e somente dias uteis — execucao pulada.\")",
        "        return False",
        "    if CALENDARIO_NOME:",
        "        try:",
        "            row = hook.get_first(",
        '                "SELECT TOP 1 ISNULL(descricao, \'\') FROM dbo.etl_calendario "',
        '                "WHERE calendario_nome=%s AND data=CAST(GETDATE() AS DATE)",',
        "                parameters=(CALENDARIO_NOME,),",
        "            )",
        "            if row is not None:",
        "                print(f\"[AGENDA] Data bloqueada no calendario {CALENDARIO_NOME} ({row[0]}) — execucao pulada.\")",
        "                return False",
        "        except Exception as e:",
        "            print(f\"[AGENDA] Aviso: verificacao de calendario falhou ({e}) — seguindo.\")",
        "    return True",
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

    # Fase 4 — check_agenda: blackout/freeze + calendário + dias úteis.
    # ShortCircuitOperator pula TODAS as tasks downstream (inclusive ALL_DONE).
    check_block = "\n".join([
        't_check_agenda = ShortCircuitOperator(',
        '    task_id="check_agenda",',
        '    python_callable=check_agenda,',
        ')',
    ])

    # Fase 4 — publica Dataset ao final (consumido por pipelines com trigger_por_dependencia)
    publish_block = "\n".join([
        't_publish_dataset = EmptyOperator(',
        '    task_id="publish_dataset",',
        '    outlets=[Dataset(DATASET_URI)],',
        ')',
    ])

    # S4: ExternalTaskSensor — suporte a múltiplas dependências
    dep_list = [d.strip() for d in depends_on.split(",") if d.strip()] if depends_on else []
    # Em modo trigger_por_dependencia o schedule já é dirigido pelos Datasets
    # dos pipelines dos quais depende — sensores são desnecessários.
    use_dataset_schedule = trigger_dep_val and bool(dep_list)
    if use_dataset_schedule:
        dep_list = []
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

    dep_lines = []

    # anchor: check_agenda → (sensors or first group)
    if sensor_names:
        sensors_ref = "[" + ", ".join(sensor_names) + "]"
        dep_lines.append(f"t_check_agenda >> {sensors_ref}")

    # Modo de dependência: EXPLÍCITO (algum job tem depends_on_jobs) ou ONDAS
    # (execution_order). Opt-in por pipeline — pipelines sem deps explícitas
    # continuam exatamente como antes.
    _job_names = {j["job_name"] for j in sorted_jobs}

    def _deps_of(j):
        raw = (j.get("depends_on_jobs") or "")
        return [d.strip() for d in str(raw).split(",")
                if d.strip() and d.strip() in _job_names and d.strip() != j["job_name"]]

    explicit_deps = any(_deps_of(j) for j in sorted_jobs)

    if explicit_deps:
        root_anchor = sensors_ref if sensor_names else "t_check_agenda"
        teams_start_done = False
        for j in sorted_jobs:
            n = _varname(j["job_name"])
            deps = _deps_of(j)
            if deps:
                ends = [f"t_end_{_varname(d)}" for d in deps]
                up = "[" + ", ".join(ends) + "]" if len(ends) > 1 else ends[0]
            else:
                up = root_anchor
            # Notificação de início no primeiro job raiz (sem dependências)
            if (not deps) and (not teams_start_done) and f_ini:
                teams_start_done = True
                chain = f"{up} >> t_start_{n} >> t_teams_start >> t_job_{n} >> t_end_{n}"
            else:
                chain = f"{up} >> t_start_{n} >> t_job_{n} >> t_end_{n}"
            dep_lines.append(chain)
        if f_ini and not teams_start_done:
            dep_lines.append(f"{root_anchor} >> t_teams_start")
    else:
        # Modo ondas (comportamento original)
        prev_ends: list[str] = []  # ends of the previous group (empty = start of DAG)
        for g_idx, group in enumerate(job_groups):
            g_ends = [f"t_end_{_varname(j['job_name'])}" for j in group]
            if prev_ends:
                up = "[" + ", ".join(prev_ends) + "]" if len(prev_ends) > 1 else prev_ends[0]
            elif sensor_names:
                up = sensors_ref
            else:
                up = "t_check_agenda"
            for j_idx, j in enumerate(group):
                n = _varname(j["job_name"])
                if g_idx == 0 and j_idx == 0 and f_ini:
                    chain = f"{up} >> t_start_{n} >> t_teams_start >> t_job_{n} >> t_end_{n}"
                else:
                    chain = f"{up} >> t_start_{n} >> t_job_{n} >> t_end_{n}"
                dep_lines.append(chain)
            prev_ends = g_ends

    end_tasks_ref = "[" + ", ".join(all_ends) + "]"
    dep_lines.append(f"end_tasks = {end_tasks_ref}")
    dep_lines.append(f"{end_tasks_ref} >> t_publish_dataset")
    if f_fim:
        dep_lines.append(f"{end_tasks_ref} >> t_teams_end")
    if f_err:
        dep_lines.append(f"{end_tasks_ref} >> t_teams_error")

    with_parts = []
    with_parts.append(_ind(check_block))
    with_parts.append(_ind(publish_block))
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

    if use_dataset_schedule:
        deps_orig = [d.strip() for d in depends_on.split(",") if d.strip()]
        ds_items = ", ".join(f'Dataset("orq://pipeline/{d}")' for d in deps_orig)
        schedule_line = f"    schedule=[{ds_items}],  # dispara quando as dependências publicarem"
    else:
        schedule_line = f'    schedule="{cron}",'

    dag_header_lines = [
        "with DAG(",
        "    dag_id=DAG_ID,",
        "    default_args=default_args,",
        f'    description="Pipeline {pname} - {project} / {domain}",',
        f"    start_date=pendulum.datetime({sd_y}, {sd_m}, {sd_d}, tz=LOCAL_TZ),",
        schedule_line,
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
    import json as _json
    hook        = MsSqlHook(mssql_conn_id=MSSQL_CONN_ID)
    output_root = _get_output_root()
    conf        = context["dag_run"].conf or {}
    dag_run_id  = context["dag_run"].run_id

    force_all      = bool(conf.get("force_all", False))
    filter_project = (conf.get("filter_project") or "").strip()
    pipeline_name  = (conf.get("pipeline_name")  or "").strip()

    if pipeline_name:
        escopo = f"Pipeline específico: {pipeline_name}"
    elif force_all and filter_project:
        escopo = f"Todos os pipelines do projeto {filter_project} (regeneração forçada)"
    elif force_all:
        escopo = "Todos os pipelines (regeneração forçada)"
    else:
        escopo = "Apenas pipelines pendentes de criação"

    def _log_upsert(estado, geradas_count=0, erros_count=0, steps=None, erros_list=None):
        try:
            hook.run(
                "MERGE dbo.etl_factory_log AS t "
                "USING (SELECT %s AS r) AS s ON t.dag_run_id = s.r "
                "WHEN MATCHED THEN UPDATE SET "
                "  estado=%s, finalizado_em=CASE WHEN %s IN ('SUCCESS','FAILED') THEN GETDATE() ELSE NULL END, "
                "  geradas=%s, erros=%s, detalhes_json=%s "
                "WHEN NOT MATCHED THEN INSERT "
                "  (dag_run_id, estado, escopo, pipeline_name, geradas, erros, detalhes_json) "
                "  VALUES (%s, %s, %s, %s, %s, %s, %s);",
                parameters=(
                    dag_run_id,
                    estado, estado,
                    geradas_count, erros_count,
                    _json.dumps({"steps": steps or [], "erros": erros_list or []}, ensure_ascii=False),
                    dag_run_id, estado, escopo, pipeline_name or None,
                    geradas_count, erros_count,
                    _json.dumps({"steps": steps or [], "erros": erros_list or []}, ensure_ascii=False),
                ),
            )
        except Exception as _le:
            print(f"[FACTORY] AVISO: falha ao gravar etl_factory_log — {_le}")

    steps_log: list = []
    _log_upsert("RUNNING")

    # ── Tudo na mesma conexão: reset + SP rodam na mesma sessão após commit ──
    conn   = hook.get_conn()
    cursor = conn.cursor()

    if pipeline_name:
        cursor.execute(
            "UPDATE dbo.etl_pipeline SET dag_criada=0, updated_at=GETDATE() "
            "WHERE pipeline_name=%s",
            (pipeline_name,),
        )
        msg = f"Pipeline '{pipeline_name}' liberado para regeneração"
        print(f"[FACTORY] {msg}")
        steps_log.append({"tipo": "reset", "msg": msg})
    elif force_all:
        if filter_project:
            cursor.execute(
                "UPDATE dbo.etl_pipeline SET dag_criada=0, updated_at=GETDATE() "
                "WHERE project_name=%s AND dag_criada=1",
                (filter_project,),
            )
            msg = f"Todos os pipelines do projeto '{filter_project}' liberados para regeneração"
            print(f"[FACTORY] {msg}")
            steps_log.append({"tipo": "reset", "msg": msg})
        else:
            cursor.execute(
                "UPDATE dbo.etl_pipeline SET dag_criada=0, updated_at=GETDATE() "
                "WHERE dag_criada=1"
            )
            msg = "Todos os pipelines liberados para regeneração"
            print(f"[FACTORY] {msg}")
            steps_log.append({"tipo": "reset", "msg": msg})

    conn.commit()   # commit antes da SP — mesma sessão, sem problema de isolamento

    cursor.execute("EXEC dbo.sp_etl_pipelines_pendentes_criar")

    pipelines_rows = cursor.fetchall()
    pipeline_cols  = [d[0].lower() for d in cursor.description]
    cursor.nextset()
    jobs_rows = cursor.fetchall()
    jobs_cols = [d[0].lower() for d in cursor.description]
    params_rows, params_cols = [], []
    if cursor.nextset():
        params_rows = cursor.fetchall()
        params_cols = [d[0].lower() for d in cursor.description]

    if not pipelines_rows:
        cursor.close(); conn.close()
        msg = "Nenhum pipeline pendente encontrado — nada foi regenerado"
        print(f"[FACTORY] {msg}")
        steps_log.append({"tipo": "vazio", "msg": msg})
        _log_upsert("SUCCESS", 0, 0, steps_log, [])
        return

    pipelines = [dict(zip(pipeline_cols, row)) for row in pipelines_rows]
    jobs_all  = [dict(zip(jobs_cols, row))     for row in jobs_rows]

    params_by_job = defaultdict(list)
    for r in [dict(zip(params_cols, row)) for row in params_rows]:
        params_by_job[(r["pipeline_name"], r["job_name"])].append(r)
    for j in jobs_all:
        j["params"] = params_by_job.get((j["pipeline_name"], j["job_name"]), [])

    # Supplement: dependência por job (degrada se a coluna não existir — migration 038)
    try:
        cursor.execute(
            "SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='dbo' "
            "AND TABLE_NAME='etl_pipeline_job' AND COLUMN_NAME='depends_on_jobs'")
        if cursor.fetchone()[0]:
            cursor.execute(
                "SELECT pipeline_name, job_name, depends_on_jobs FROM dbo.etl_pipeline_job "
                "WHERE depends_on_jobs IS NOT NULL")
            _depmap = {(r[0], r[1]): r[2] for r in cursor.fetchall()}
            for j in jobs_all:
                j["depends_on_jobs"] = _depmap.get((j["pipeline_name"], j["job_name"]))
    except Exception as _de:
        print(f"[FACTORY] depends_on_jobs supplement ignorado: {_de}")

    # Supplement: banco-alvo por job storedproc (degrada se a coluna não existir — migration 039)
    try:
        cursor.execute(
            "SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='dbo' "
            "AND TABLE_NAME='etl_pipeline_job' AND COLUMN_NAME='mssql_database'")
        if cursor.fetchone()[0]:
            cursor.execute(
                "SELECT pipeline_name, job_name, mssql_database FROM dbo.etl_pipeline_job "
                "WHERE mssql_database IS NOT NULL")
            _dbmap = {(r[0], r[1]): r[2] for r in cursor.fetchall()}
            for j in jobs_all:
                j["mssql_database"] = _dbmap.get((j["pipeline_name"], j["job_name"]))
    except Exception as _dbe:
        print(f"[FACTORY] mssql_database supplement ignorado: {_dbe}")

    # Supplement with advanced fields (not in SP result set)
    if pipelines:
        pnames_sql = ",".join(["%s"] * len(pipelines))
        pnames_vals = tuple(p['pipeline_name'] for p in pipelines)
        # colunas da migration 017 (scheduling avançado) — degradam se ausentes
        cursor.execute(
            "SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME='etl_pipeline' "
            "AND COLUMN_NAME='calendario_nome'"
        )
        has_sched_cols = bool(cursor.fetchone()[0])
        sched_cols = (
            ", calendario_nome, somente_dias_uteis, trigger_por_dependencia"
            if has_sched_cols else ""
        )
        # colunas da migration 018 (horários múltiplos) — degradam se ausentes
        cursor.execute(
            "SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME='etl_pipeline' "
            "AND COLUMN_NAME='horarios_especificos'"
        )
        if cursor.fetchone()[0]:
            sched_cols += ", horarios_especificos, dias_semana"
        # coluna da migration 024 (dia + hora específico) — degrada se ausente
        cursor.execute(
            "SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME='etl_pipeline' "
            "AND COLUMN_NAME='dias_horarios_mes'"
        )
        if cursor.fetchone()[0]:
            sched_cols += ", dias_horarios_mes"
        # colunas do builder de agendamento (Fase 3) — degradam se ausentes
        cursor.execute(
            "SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME='etl_pipeline' "
            "AND COLUMN_NAME='schedule_type'"
        )
        if cursor.fetchone()[0]:
            sched_cols += ", schedule_type, schedule_hour, schedule_minute, schedule_dow, schedule_dom"
        cursor.execute(
            f"SELECT pipeline_name, criticidade, sla_minutos, ambiente, "
            f"max_active_runs, retries_count, retry_delay_seconds, pool_name, descricao, dag_start_date, "
            f"runbook_md{sched_cols} "
            f"FROM dbo.etl_pipeline WHERE pipeline_name IN ({pnames_sql})",
            pnames_vals,
        )
        adv_rows = cursor.fetchall()
        adv_cols = [d[0].lower() for d in cursor.description]
        adv_map  = {r[0]: dict(zip(adv_cols, r)) for r in adv_rows}
        for p in pipelines:
            p.update(adv_map.get(p['pipeline_name'], {}))

    cursor.close(); conn.close()

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
            msg = f"Arquivo da DAG gravado em {dest_file}"
            print(f"[FACTORY] OK -> {dest_file}")
            steps_log.append({"tipo": "gerada", "msg": msg})
        except Exception as e:
            erros.append(f"{pname}: erro ao salvar — {e}")
            steps_log.append({"tipo": "erro", "msg": f"Erro ao gravar arquivo de '{pname}': {e}"})
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
            steps_log.append({"tipo": "banco", "msg": f"Pipeline '{pname}' marcado como criado no cadastro"})
        except Exception as e:
            erros.append(f"{pname}: dag gerada mas erro ao atualizar banco — {e}")
            steps_log.append({"tipo": "erro", "msg": f"Erro ao atualizar cadastro de '{pname}': {e}"})

        geradas.append(pname)

    resumo = f"{len(geradas)} DAG(s) regenerada(s) com sucesso, {len(erros)} erro(s)"
    print(f"\n[FACTORY] Geradas: {len(geradas)} | Erros: {len(erros)}")
    for e in erros:
        print(f"  x {e}")
    steps_log.append({"tipo": "resumo", "msg": resumo})

    estado_final = "FAILED" if erros else "SUCCESS"
    # Fluxo "Gerar DAG" da UI (conf.aguardar_ativacao): o arquivo foi gerado, mas
    # a DAG ainda não está ativa no Airflow. Marca GERADA (aguardando ativação);
    # o reconciliador do ORQUESTRA vira para SUCCESS quando a DAG ficar ativa, ou
    # TIMEOUT se não aparecer no tempo limite. (Regeneração em massa segue SUCCESS.)
    if estado_final == "SUCCESS" and pipeline_name and conf.get("aguardar_ativacao"):
        estado_final = "GERADA"
        steps_log.append({
            "tipo": "aguardando",
            "msg": "Aguarde — ativando a DAG no Airflow… O ORQUESTRA confirma e marca como pronta quando estiver ativa.",
        })
    _log_upsert(estado_final, len(geradas), len(erros), steps_log, erros)

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
