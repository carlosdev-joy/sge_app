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


def _alias(job) -> str:
    """Tipo de job normalizado (aplica _TYPE_ALIAS, lower, strip)."""
    raw = job["job_type"].lower().strip()
    return _TYPE_ALIAS.get(raw, raw)


def _task_block(job, project, pipeline, branch_reachable=False):
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
        # repr() embute o comando como LITERAL Python válido no código gerado.
        # O shlex.quote usado antes devolvia o comando SEM aspas quando ele não
        # tinha caractere especial (ex.: /opt/scripts/run.sh, ls) — a DAG
        # quebrava no import (SyntaxError/NameError). O comando roda VIA SSH no
        # servidor do ssh_conn_id do job (fallback: SSH_CONN_ID do pipeline).
        ssh = job.get("ssh_conn_id") or None
        ssh_val = f'"{ssh}"' if ssh else 'SSH_CONN_ID'
        main = "\n".join([
            f't_job_{vname} = ShellOperator(',
            f'    task_id={name!r},',
            f'    ssh_conn_id={ssh_val},',
            f'    command={cmd!r},',
            f'    cmd_timeout=None,',
            f'    do_xcom_push=True,',
            f')',
        ])
    elif jtype == "python":
        pyc = job.get("_python_cfg")
        if pyc:
            # Nó Python v2 (modos arquivo/código): roda via SSH no servidor do
            # ssh_conn_id do job. Literais via repr; quoting de shell é feito
            # em RUNTIME pelo operador (shlex.quote).
            ssh = job.get("ssh_conn_id") or None
            ssh_val = f'"{ssh}"' if ssh else 'SSH_CONN_ID'
            linhas = [
                f't_job_{vname} = PythonScriptOperator(',
                f'    task_id={name!r},',
                f'    ssh_conn_id={ssh_val},',
                f'    modo={str(pyc.get("modo"))!r},',
            ]
            if pyc.get("modo") == "arquivo":
                linhas.append(f'    script_path={str(pyc.get("script_path") or "")!r},')
            else:
                linhas.append(f'    destino_dir={str(pyc.get("destino_dir") or "")!r},')
                linhas.append(f'    arquivo={str(pyc.get("arquivo") or "")!r},')
                linhas.append(f'    codigo={str(pyc.get("codigo") or "")!r},')
            interp = str(pyc.get("interpretador") or "").strip()
            if interp and interp != "python3":
                linhas.append(f'    interpretador={interp!r},')
            linhas += [
                f'    cmd_timeout=None,',
                f'    do_xcom_push=True,',
                f')',
            ]
            main = "\n".join(linhas)
        else:
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
    elif jtype == "http":
        # Fail-loud na geração (precedente 0625b16): sem URL, recusa publicar —
        # o default antigo (httpbin.org) chamaria um endpoint EXTERNO em produção.
        url = (jcmd or "").strip()
        if not url:
            raise ValueError(
                f"job http '{name}' sem URL (job_command) — preencha a URL e republique")
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

    # Jobs alcançáveis a partir de um nó de Decisão: o t_start usa
    # NONE_FAILED_MIN_ONE_SUCCESS (não é pulado por engano numa junção entre
    # ramos) e o t_end usa NONE_SKIPPED (propaga o skip do ramo não escolhido,
    # mas PRESERVA o fail-fast quando o job escolhido falha de verdade).
    start_rule = (
        '    trigger_rule=TriggerRule.NONE_FAILED_MIN_ONE_SUCCESS,'
        if branch_reachable else None
    )
    end_rule = "TriggerRule.NONE_SKIPPED" if branch_reachable else "TriggerRule.ALL_DONE"
    log_start = "\n".join(filter(None, [
        f't_start_{vname} = PythonOperator(',
        f'    task_id={("log_start_" + name)!r},',
        f'    python_callable=log_start,',
        f'    op_kwargs={{"job_name": {name!r}, "task_key": {name!r}}},',
        start_rule,
        f')',
    ]))
    log_end = "\n".join([
        f't_end_{vname} = PythonOperator(',
        f'    task_id={("log_end_" + name)!r},',
        f'    python_callable=log_end,',
        f'    op_kwargs={{"job_name": {name!r}, "task_key": {name!r}, "upstream_task_id": {name!r}}},',
        f'    trigger_rule={end_rule},',
        f')',
    ])

    return "\n\n".join([log_start, main, log_end])


def _decision_block(job, condition, job_names, notif_names=None):
    """Bloco de um nó de Decisão: BranchPythonOperator que avalia a condição
    (via utils.conditions.eval_condition) e retorna os t_start do ramo escolhido.
    Não tem t_start/t_end próprios (é um roteador) — fica fora de end_tasks.

    Membros que são nós de Notificação não têm log_start_* (rodam direto via
    t_notif_*, task_id = próprio nome); para esses, a branch devolve o próprio
    task_id do nó em vez de log_start_<nome>.

    SWITCH (N-way): quando a condição tem ``casos``, o branch avalia via
    eval_switch (primeiro caso que casar vence; nenhum → 'senao') e roteia pelo
    mapa nome-do-caso → t_start dos membros. Condições sem ``casos`` seguem o
    caminho binário INALTERADO (DAG byte-idêntica para fluxos existentes)."""
    notif_names = notif_names or set()
    name  = job["job_name"]
    vname = _varname(name)
    casos = condition.get("casos") if isinstance(condition.get("casos"), list) else None
    if casos:
        def _ids(membros):
            ms = [j for j in (membros or []) if j in job_names and j != name]
            return [(j if j in notif_names else "log_start_" + j) for j in ms]
        ramos_ids = {}
        for c in casos:
            cnome = str(c.get("nome") or "").strip() if isinstance(c, dict) else ""
            if cnome:
                ramos_ids[cnome] = _ids(c.get("ramo"))
        ramos_ids["senao"] = _ids(condition.get("ramo_senao"))
        return "\n".join([
            f'def _decide_{vname}(**context):',
            f'    cond = {condition!r}',
            f'    _exec_id = context.get("ts_nodash")',
            f'    _ti = context.get("ti")',
            f'    _caso, _valor = eval_switch(cond, MSSQL_CONN_ID, execution_id=_exec_id, pipeline_name=PIPELINE_NAME, ti=_ti)',
            f'    _job = {name!r}',
            f'    print("[DECISAO " + _job + "] valor=" + str(_valor) + " -> caso " + _caso)',
            '    context["ti"].xcom_push(key="decisao", value={"valor": str(_valor), "caso": _caso})',
            f'    _ramos = {ramos_ids!r}',
            f'    return _ramos.get(_caso, [])',
            f'',
            f't_dec_{vname} = BranchPythonOperator(',
            f'    task_id={name!r},',
            f'    python_callable=_decide_{vname},',
            f')',
        ])
    ramo_v = [j for j in (condition.get("ramo_verdadeiro") or []) if j in job_names and j != name]
    ramo_f = [j for j in (condition.get("ramo_falso") or []) if j in job_names and j != name]
    # Notificação: o branch aponta para o próprio task_id (t_notif_* usa task_id=nome);
    # demais membros entram pelo log_start_<nome>.
    v_ids = [(j if j in notif_names else "log_start_" + j) for j in ramo_v]
    f_ids = [(j if j in notif_names else "log_start_" + j) for j in ramo_f]
    return "\n".join([
        f'def _decide_{vname}(**context):',
        f'    cond = {condition!r}',
        f'    _exec_id = context.get("ts_nodash")',
        f'    _ti = context.get("ti")',
        f'    resultado, _valor = eval_condition(cond, MSSQL_CONN_ID, execution_id=_exec_id, pipeline_name=PIPELINE_NAME, ti=_ti)',
        f'    _ramo = "verdadeiro" if resultado else "falso"',
        f'    _job = {name!r}',
        f'    print("[DECISAO " + _job + "] valor=" + str(_valor) + " resultado=" + str(resultado) + " -> ramo " + _ramo)',
        '    context["ti"].xcom_push(key="decisao", value={"valor": str(_valor), "resultado": bool(resultado), "ramo": _ramo})',
        f'    return {v_ids!r} if resultado else {f_ids!r}',
        f'',
        f't_dec_{vname} = BranchPythonOperator(',
        f'    task_id={name!r},',
        f'    python_callable=_decide_{vname},',
        f')',
    ])


def _notify_block(job, notify_cfg, upstream_jobs, branch_reachable=False):
    """Bloco de um nó de Notificação (Teams): PythonOperator EXECUTÁVEL.

    Espelha o nó de Decisão por NÃO ter t_start/t_end (sem lineage em
    etl_job_execution — fica fora de end_tasks), mas, diferente do roteador,
    ELE RODA: lê notify_json (grupo_id/template_id/mensagem), resolve o webhook
    do grupo em etl_msg_grupo e o texto (mensagem inline; se vazia, o corpo do
    etl_msg_template), interpola {pipeline} {job} {linhas} {status} {data} e
    chama _teams_post_card.

    É tipicamente o ramo_falso de uma decisão — usa trigger_rule tolerante a skip
    (NONE_FAILED_MIN_ONE_SUCCESS) quando alcançável a partir de um branch."""
    name  = job["job_name"]
    vname = _varname(name)
    grupo_id    = notify_cfg.get("grupo_id")
    template_id = notify_cfg.get("template_id")
    mensagem    = notify_cfg.get("mensagem") or ""
    # Jobs a montante (no run) cujo rows_out alimenta {linhas}.
    up_names = list(upstream_jobs or [])
    rule = (
        '    trigger_rule=TriggerRule.NONE_FAILED_MIN_ONE_SUCCESS,'
        if branch_reachable else None
    )
    return "\n".join(filter(None, [
        f'def _notify_{vname}(**context):',
        f'    _job = {name!r}',
        f'    _grupo_id = {grupo_id!r}',
        f'    _template_id = {template_id!r}',
        f'    _mensagem = {mensagem!r}',
        f'    _up_jobs = {up_names!r}',
        f'    _exec_id = context.get("ts_nodash")',
        f'    _resolve_e_envia_notificacao(_job, _grupo_id, _template_id, _mensagem, _up_jobs, _exec_id, context)',
        f'',
        f't_notif_{vname} = PythonOperator(',
        f'    task_id={name!r},',
        f'    python_callable=_notify_{vname},',
        rule,
        f')',
    ]))


def _sql_block(job, sql_cfg, branch_reachable=False):
    """Bloco de um nó SQL: PythonOperator EXECUTÁVEL que RODA um SELECT e PUBLICA
    o valor escalar (1ª coluna da 1ª linha) no XCom default da task (task_id =
    nome do nó). Análogo ao nó de Notificação por NÃO ter t_start/t_end (sem
    lineage — fica fora de end_tasks), mas, em vez de postar no Teams, devolve o
    valor para uma Decisão 'valor_sql' a jusante comparar.

    on_error do sql_json dirige a falha: 'falhar' (default carimbado pela API
    nos fluxos re-salvos) → erro no SELECT LEVANTA e a task falha alto;
    'nulo'/ausente (legado) → log + None (não derruba a DAG, mas pode rotear a
    decisão a jusante para o ramo errado em silêncio). Quando alcançável a
    partir de um branch, usa trigger_rule tolerante a skip."""
    name  = job["job_name"]
    vname = _varname(name)
    sql       = sql_cfg.get("sql") or ""
    conn_id   = (sql_cfg.get("mssql_conn_id") or "").strip() or None
    database  = (sql_cfg.get("database") or "").strip() or None
    on_error  = (str(sql_cfg.get("on_error") or "").strip().lower() or "nulo")
    rule = (
        '    trigger_rule=TriggerRule.NONE_FAILED_MIN_ONE_SUCCESS,'
        if branch_reachable else None
    )
    return "\n".join(filter(None, [
        f'def _sql_{vname}(**context):',
        f'    _job = {name!r}',
        f'    _sql = {sql!r}',
        f'    _conn_id = {conn_id!r}',
        f'    _database = {database!r}',
        f'    _valor = _resolve_e_roda_sql(_sql, _conn_id, _database, context, on_error={on_error!r})',
        f'    print("[SQL NODE " + _job + "] valor publicado=" + repr(_valor))',
        f'    return _valor',
        f'',
        f't_sql_{vname} = PythonOperator(',
        f'    task_id={name!r},',
        f'    python_callable=_sql_{vname},',
        rule,
        f')',
    ]))


def _restricao_dia(pipeline):
    """Restrição de DIA que o cron carregava, para quem vai ficar sem cron.

    Um pipeline `monthly` com `schedule_dom=5` tinha a regra "só dia 5" embutida
    no cron `0 7 5 * *`. Ao virar `schedule=None` (disparo por dependência), essa
    regra desaparecia e o pipeline passava a rodar em todo dia em que o
    predecessor concluísse — fechamento mensal executando 30x/mês.

    Devolve None para os tipos que não restringem dia (daily, hourly, custom,
    monthly_days_times — este último já é checado por DIAS_HORARIOS_MES).
    """
    stype = (pipeline.get("schedule_type") or "daily").lower().strip()
    if stype == "weekly":
        return {"tipo": "weekly", "dow": int(pipeline.get("schedule_dow") or 1)}
    if stype in ("monthly", "biweekly"):
        return {"tipo": stype, "dom": int(pipeline.get("schedule_dom") or 1)}
    return None


def _generate_dag_source(pipeline, jobs):
    pname      = pipeline["pipeline_name"]
    project    = pipeline["project_name"]
    domain     = pipeline["domain"]
    tags_raw   = pipeline["tags"]
    sched      = pipeline["scheduled_time"]
    depends_on = (pipeline.get("depends_on") or "").strip() or None
    # Definido aqui (e não junto do wiring) porque as CONSTANTES do arquivo
    # gerado precisam saber se este pipeline perde o cron.
    dep_list = [d.strip() for d in depends_on.split(",") if d.strip()] if depends_on else []
    tem_dependencia = bool(dep_list)
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
    # OBSOLETO desde a F3 da spec de dependências: ter dependência JÁ implica
    # ser disparado por ela (schedule=None). O campo continua no banco e é lido
    # aqui só para não quebrar quem o envia; a F5 o tira da tela e a F6 do
    # modelo. Não usar em decisão nova.
    trigger_dep_val     = bool(pipeline.get("trigger_por_dependencia") or 0)  # noqa: F841
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
    # Nós de Decisão (roteador), de Notificação (sem lineage) e SQL (roda o SELECT
    # e publica o valor escalar) não têm t_start/t_end próprios — ficam fora de
    # end_tasks.
    _SPECIAL_NODES = ("decisao", "notificacao", "sql")
    all_ends    = [f"t_end_{_varname(j['job_name'])}" for j in sorted_jobs if _alias(j) not in _SPECIAL_NODES]

    def _jtypes(jobs):
        return {_TYPE_ALIAS.get(j["job_type"].lower(), j["job_type"].lower()) for j in jobs}

    job_types   = _jtypes(sorted_jobs)
    ds_needed   = "datastage"  in job_types
    sh_needed   = "shell"      in job_types
    sp_needed   = "storedproc" in job_types
    # 'sql' agora é nó ESPECIAL (roda SELECT + publica XCom via callable gerado,
    # que usa MsSqlHook direto) — não usa o SqlOperator de utils.job_operators.
    http_needed = "http"       in job_types

    # ── Nó de Decisão (migration 043) ──────────────────────────────────────
    # Parse das condições (degrada se condition_json ausente/invalido), mapa de
    # arestas do branch (job → decisões que o citam num ramo) e o conjunto de
    # jobs ALCANÇÁVEIS a jusante de qualquer decisão (recebem trigger_rule
    # tolerante a skip). Tudo derivado da config — sem efeito quando não há
    # decisão.
    import json as _json
    _job_names = {j["job_name"] for j in sorted_jobs}

    # ── Nó Python v2 (migration 059) — parse do python_json ────────────────
    # modo 'arquivo'/'codigo' roda via SSH (PythonScriptOperator); ausente ou
    # inválido = modo legado 'modulo' (PythonModuleOperator no worker) — jobs
    # antigos geram código BYTE-IDÊNTICO.
    for _j in sorted_jobs:
        if _TYPE_ALIAS.get(_j["job_type"].lower(), _j["job_type"].lower()) == "python":
            _raw_py = _j.get("python_json")
            try:
                _cfg_py = _json.loads(_raw_py) if _raw_py else None
            except (ValueError, TypeError):
                _cfg_py = None
            _j["_python_cfg"] = (_cfg_py if isinstance(_cfg_py, dict)
                                 and _cfg_py.get("modo") in ("arquivo", "codigo") else None)
    pyscript_needed = any(j.get("_python_cfg") for j in sorted_jobs)
    pymodulo_needed = any(
        _TYPE_ALIAS.get(j["job_type"].lower(), j["job_type"].lower()) == "python"
        and not j.get("_python_cfg") for j in sorted_jobs)

    def _deps_of(j):
        raw = (j.get("depends_on_jobs") or "")
        return [d.strip() for d in str(raw).split(",")
                if d.strip() and d.strip() in _job_names and d.strip() != j["job_name"]]

    decision_conditions = {}
    for j in sorted_jobs:
        if _alias(j) == "decisao":
            raw = j.get("condition_json")
            try:
                decision_conditions[j["job_name"]] = _json.loads(raw) if raw else {}
            except (ValueError, TypeError):
                decision_conditions[j["job_name"]] = {}
    has_decision = bool(decision_conditions)

    # ── Nó de Notificação (migration 049) ──────────────────────────────────
    # Parse de notify_json (degrada se ausente/invalido). O nó é executável mas
    # sem lineage (espelha o roteador de decisão). notificacao_nodes mapeia
    # job_name → {grupo_id, template_id, mensagem}.
    notificacao_nodes = {}
    for j in sorted_jobs:
        if _alias(j) == "notificacao":
            raw = j.get("notify_json")
            try:
                notificacao_nodes[j["job_name"]] = _json.loads(raw) if raw else {}
            except (ValueError, TypeError):
                notificacao_nodes[j["job_name"]] = {}
    has_notificacao = bool(notificacao_nodes)

    # ── Nó SQL (migration 051) ─────────────────────────────────────────────
    # Parse de sql_json (degrada se ausente/invalido). O nó é executável mas sem
    # lineage (espelha o roteador de decisão / a notificação): RODA um SELECT e
    # publica o valor escalar no XCom para uma Decisão 'valor_sql' a jusante.
    # sql_nodes mapeia job_name → {sql, mssql_conn_id, database}.
    sql_nodes = {}
    for j in sorted_jobs:
        if _alias(j) == "sql":
            raw = j.get("sql_json")
            try:
                sql_nodes[j["job_name"]] = _json.loads(raw) if raw else {}
            except (ValueError, TypeError):
                sql_nodes[j["job_name"]] = {}
    has_sql_node = bool(sql_nodes)

    branch_parents = defaultdict(list)   # job_name → [nome da(s) decisão(ões)]
    ramo_members = set()
    for dname, cond in decision_conditions.items():
        # Binária (ramo_verdadeiro/ramo_falso) e switch (casos[].ramo + ramo_senao)
        # — a ordem preserva a emissão binária existente (DAG byte-idêntica).
        _membros = list(cond.get("ramo_verdadeiro") or []) + list(cond.get("ramo_falso") or [])
        if isinstance(cond.get("casos"), list):
            for _caso in cond["casos"]:
                if isinstance(_caso, dict):
                    _membros += list(_caso.get("ramo") or [])
        _membros += list(cond.get("ramo_senao") or [])
        for m in _membros:
            if m in _job_names and m != dname:
                ramo_members.add(m)
                if dname not in branch_parents[m]:
                    branch_parents[m].append(dname)
    # Fecho transitivo a jusante (segue depends_on_jobs a partir dos membros).
    _children = defaultdict(set)
    for j in sorted_jobs:
        for d in _deps_of(j):
            _children[d].add(j["job_name"])
    reachable = set()
    _stack = list(ramo_members)
    while _stack:
        x = _stack.pop()
        if x in reachable:
            continue
        reachable.add(x)
        _stack.extend(_children.get(x, ()))

    # Seção de imports
    import_lines = ["from airflow import DAG"]
    # `datetime` (além de timedelta) é usado pelo registro de execução do
    # pipeline — ver _registrar_execucao nos helpers.
    import_lines.append("from datetime import datetime, timedelta")
    if ds_needed:
        import_lines.append("from utils.datastage_operator import DataStageOperator")
    # Operadores reutilizáveis (utils/job_operators) — só os tipos presentes.
    _ops = []
    if sh_needed:   _ops.append("ShellOperator")
    if sp_needed:   _ops.append("StoredProcOperator")
    if pymodulo_needed: _ops.append("PythonModuleOperator")
    if pyscript_needed: _ops.append("PythonScriptOperator")
    if http_needed: _ops.append("HttpCallOperator")
    if _ops:
        import_lines.append("from utils.job_operators import " + ", ".join(_ops))
    if has_decision:
        # eval_switch só entra quando alguma decisão é N-way (casos) — pipelines
        # binários mantêm a linha de import (e a DAG) byte-idêntica.
        _has_switch = any(isinstance(c, dict) and c.get("casos")
                          for c in decision_conditions.values())
        import_lines.append("from utils.conditions import eval_condition"
                            + (", eval_switch" if _has_switch else ""))
    import_lines += [
        "from airflow.operators.python import PythonOperator, ShortCircuitOperator"
        + (", BranchPythonOperator" if has_decision else ""),
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
        # Restrição de DIA para pipeline disparado por dependência. Só é
        # preenchida quando o pipeline perde o cron (schedule=None): a restrição
        # morava no próprio cron ("0 7 5 * *" = dia 5), e trocá-lo por None a
        # apagava — o fechamento mensal passava a rodar todo dia que o
        # predecessor concluísse. Pipeline com cron não precisa (o cron já filtra).
        f'RESTRICAO_DIA = {repr(_restricao_dia(pipeline) if tem_dependencia else None)}',
        f'default_args  = {{"owner": "airflow", "depends_on_past": False, "retries": {retries_val}, "retry_delay": timedelta(seconds={retry_delay_val})}}',
        f'JOBS          = {repr([j["job_name"] for j in sorted_jobs])}',
        # Jobs EXECUTÁVEIS (com trio de telemetria) — base do registro de SKIPPED
        # do flow_close; nós especiais (decisão/notificação/sql) ficam de fora.
        f'FLOW_JOBS     = {repr([j["job_name"] for j in sorted_jobs if _alias(j) not in _SPECIAL_NODES])}',
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
        # ── F2 da spec de dependências: execução no nível PIPELINE ──────────
        # Até aqui só existia etl_job_execution (por JOB). Sem uma execução de
        # pipeline carimbada com a data de referência, não há como responder "o
        # predecessor concluiu na mesma corrida?" — que é a pergunta que libera
        # um dependente (F3).
        "def _momento_logico(context):",
        "    \"\"\"Instante que define a data de referência.",
        "",
        "    Usa o horário AGENDADO (data_interval_end/logical_date), não o",
        "    relógio: um atraso de fila que empurrasse a execução para depois da",
        "    meia-noite mudaria a data de referência e quebraria a dependência —",
        "    justamente o que a data de referência existe para evitar. Mesma",
        "    fonte que o check_agenda já usa.\"\"\"",
        "    _m = context.get('data_interval_end') or context.get('logical_date')",
        "    if _m is None:",
        "        return pendulum.now(LOCAL_TZ)",
        "    try:",
        "        return _m.in_timezone(LOCAL_TZ)",
        "    except Exception:",
        "        return _m",
        "",
        "def _data_referencia(context):",
        "    \"\"\"Data de referência (ODATE) desta execução.",
        "",
        "    Precedência: herança > cálculo. Quem é disparado por dependência",
        "    recebe a data do predecessor em conf e NÃO recalcula — é isso que",
        "    mantém a corrida coerente quando ela atravessa a meia-noite.\"\"\"",
        "    from utils.data_referencia import calcular",
        "    _conf = (context.get('dag_run').conf or {}) if context.get('dag_run') else {}",
        "    _herdada = _conf.get('data_referencia')",
        "    if _herdada:",
        "        try:",
        "            return pendulum.parse(str(_herdada)).date()",
        "        except Exception:",
        "            print(f'[EXEC] data_referencia herdada invalida: {_herdada!r} — recalculando.')",
        "    _virada = None",
        "    try:",
        "        _hook = MsSqlHook(mssql_conn_id=MSSQL_CONN_ID)",
        "        _row = _hook.get_first(",
        '            "SELECT COALESCE(CONVERT(VARCHAR(8), p.hora_virada, 108), c.config_value) "',
        '            "FROM dbo.etl_pipeline p "',
        '            "LEFT JOIN dbo.etl_app_config c ON c.config_key = \'dependencia_hora_virada\' "',
        '            "WHERE p.pipeline_name = %s",',
        "            parameters=(PIPELINE_NAME,))",
        "        _virada = _row[0] if _row else None",
        "    except Exception as e:",
        "        # Sem a migration 067 a coluna não existe: cai na virada padrão,",
        "        # que devolve a data do calendário (comportamento de sempre).",
        "        print(f'[EXEC] virada indisponivel ({e}) — usando padrao 00:00.')",
        "    _dt = _momento_logico(context)",
        "    return calcular(datetime(_dt.year, _dt.month, _dt.day, _dt.hour, _dt.minute, _dt.second), _virada)",
        "",
        "def _registrar_execucao(status, context, motivo=None, apenas_se_executando=False):",
        "    \"\"\"Upsert da execução do pipeline. NUNCA derruba o pipeline.",
        "",
        "    Três caminhos, nesta ordem:",
        "      1. atualiza a linha DESTA execução (mesmo execution_id);",
        "      2. ADOTA a linha reservada pelo push/guardiã — que foi criada antes",
        "         da DAG existir e por isso tem execution_id NULL. Sem esta adoção",
        "         a reserva ficava órfã em EXECUTANDO para sempre e a corrida",
        "         ganhava duas linhas;",
        "      3. cria a linha, quando a corrida veio por agenda.",
        "",
        "    `apenas_se_executando` protege estados terminais: PULADO (gravado pelo",
        "    check_agenda) e FALHA não podem ser sobrescritos por um SUCESSO de",
        "    fechamento que rodou com ALL_DONE.",
        "",
        "    Degrada com log se a 067 não foi aplicada: o registro é observabilidade",
        "    e insumo da liberação, não pode derrubar uma carga que rodou bem.\"\"\"",
        "    _exec_id = context.get('ts_nodash')",
        "    try:",
        "        _dref = _data_referencia(context)",
        "        _disparado = 'agenda'",
        "        _conf = (context.get('dag_run').conf or {}) if context.get('dag_run') else {}",
        "        if _conf.get('disparado_por'):",
        "            _disparado = str(_conf['disparado_por'])[:200]",
        "        elif str(context.get('run_id', '')).startswith('manual'):",
        "            _disparado = 'manual'",
        "        _extra = \" AND status = 'EXECUTANDO'\" if apenas_se_executando else ''",
        "        _hook = MsSqlHook(mssql_conn_id=MSSQL_CONN_ID)",
        "        _conn = _hook.get_conn(); _cur = _conn.cursor()",
        "        try:",
        "            _set = (\"SET status=%s, \"",
        "                    \"  fim = CASE WHEN %s IN ('SUCESSO','FALHA','PULADO') THEN GETDATE() ELSE fim END, \"",
        "                    \"  motivo=COALESCE(%s, motivo), atualizado_em=GETDATE() \")",
        "            _cur.execute(",
        '                "UPDATE dbo.etl_pipeline_execucao " + _set +',
        '                "WHERE pipeline_name=%s AND data_referencia=%s AND execution_id=%s" + _extra,',
        "                (status, status, motivo, PIPELINE_NAME, _dref, _exec_id))",
        "            if _cur.rowcount == 0:",
        "                # Adoção da reserva: carimba o execution_id na linha que o",
        "                # push/guardiã criou, em vez de abrir uma segunda.",
        "                _cur.execute(",
        '                    "UPDATE dbo.etl_pipeline_execucao SET execution_id=%s, " +',
        "                    _set.replace('SET ', '', 1) +",
        '                    "WHERE pipeline_name=%s AND data_referencia=%s AND execution_id IS NULL" + _extra,',
        "                    (_exec_id, status, status, motivo, PIPELINE_NAME, _dref))",
        "                if _cur.rowcount:",
        "                    print(f'[EXEC] {PIPELINE_NAME}: reserva de {_dref} adotada por {_exec_id}.')",
        "            if _cur.rowcount == 0 and not apenas_se_executando:",
        "                _cur.execute(",
        '                    "INSERT INTO dbo.etl_pipeline_execucao "',
        '                    "(pipeline_name, data_referencia, execution_id, status, inicio, fim, "',
        '                    " disparado_por, motivo) VALUES (%s,%s,%s,%s, "',
        # `inicio` só para quem realmente começou: PULADO com inicio preenchido
        # ficava "mais recente" que o SUCESSO da mesma data e escondia o sucesso
        # de um pipeline que roda várias vezes ao dia.
        '                    " CASE WHEN %s = \'PULADO\' THEN NULL ELSE %s END, "',
        '                    " CASE WHEN %s IN (\'SUCESSO\',\'FALHA\',\'PULADO\') THEN GETDATE() ELSE NULL END, %s,%s)",',
        "                    (PIPELINE_NAME, _dref, _exec_id, status,",
        "                     status, datetime.now(), status, _disparado, motivo))",
        "            elif _cur.rowcount == 0:",
        "                print(f'[EXEC] {PIPELINE_NAME}: {status} ignorado — a corrida de {_dref} nao esta mais EXECUTANDO.')",
        "            _conn.commit()",
        "        finally:",
        "            _cur.close(); _conn.close()",
        "        print(f'[EXEC] {PIPELINE_NAME} {status} — data de referencia {_dref}')",
        "    except Exception as e:",
        "        print(f'[EXEC] Aviso: execucao nao registrada (migration 067 aplicada?): {e}')",
        "",
        "def registrar_inicio(**context):",
        "    _registrar_execucao('EXECUTANDO', context)",
        "",
        "def registrar_fim(**context):",
        "    \"\"\"Fecha a corrida como SUCESSO — só se ela ainda estiver EXECUTANDO.",
        "",
        "    Roda com ALL_DONE porque havia um caminho em que a corrida ficava",
        "    presa: decisão na raiz com um ramo vazio deixa o publish_dataset",
        "    pulado, e a regra condicional anterior pulava o fechamento junto —",
        "    a linha ficava EXECUTANDO para sempre, sem ninguém alertar.",
        "",
        "    Com ALL_DONE a task sempre roda, e a guarda de estado é que decide:",
        "    corrida PULADA pelo check_agenda ou já marcada FALHA não vira SUCESSO.\"\"\"",
        "    _registrar_execucao('SUCESSO', context, apenas_se_executando=True)",
        "",
        # ── F3: disparo imediato de quem depende deste pipeline ─────────────
        "def disparar_dependentes(**context):",
        "    \"\"\"Libera quem espera por este pipeline, agora que ele terminou bem.",
        "",
        "    Só dispara quem tem TODAS as dependências concluídas com sucesso na",
        "    MESMA data de referência: com dois predecessores, o primeiro a",
        "    terminar não dispara nada — quem completa a condição é o último.",
        "",
        "    Nunca derruba o pipeline: ele já fez o trabalho dele. Dependente que",
        "    não subir aqui é pego pela guardiã (F4).\"\"\"",
        "    from utils.dependencias import (avaliar_liberacao, config_do_dependente,",
        "                                    dentro_da_janela, dependentes_de,",
        "                                    status_dos_predecessores)",
        "    try:",
        "        _dref = _data_referencia(context)",
        "        _hook = MsSqlHook(mssql_conn_id=MSSQL_CONN_ID)",
        "        # A task roda com ALL_DONE (o fechamento também), então quem decide",
        "        # é o estado REAL da corrida: só um SUCESSO satisfaz a condição de",
        "        # alguém. Sem esta guarda, um pipeline PULADO ou que falhou liberaria",
        "        # os dependentes.",
        "        _meu = _hook.get_first(",
        '            "SELECT TOP 1 status FROM dbo.etl_pipeline_execucao "',
        '            "WHERE pipeline_name=%s AND data_referencia=%s "',
        '            "ORDER BY COALESCE(inicio, criado_em) DESC, id DESC",',
        "            parameters=(PIPELINE_NAME, _dref))",
        "        if _meu and str(_meu[0]) != 'SUCESSO':",
        "            print(f'[DEP] {PIPELINE_NAME} terminou como {_meu[0]} — dependentes nao liberados.')",
        "            return",
        "        _filhos = dependentes_de(_hook, PIPELINE_NAME)",
        "        if not _filhos:",
        "            return",
        "        _agora = pendulum.now(LOCAL_TZ)",
        "    except Exception as e:",
        "        print(f'[DEP] Aviso: avaliacao de dependentes falhou ({e}) — a guardia cobre.')",
        "        return",
        "    for _filho in _filhos:",
        "        # try DENTRO do laço: um dependente problemático não pode cancelar",
        "        # a avaliação dos outros — antes, o primeiro erro abortava todos.",
        "        try:",
        "            _cfg = config_do_dependente(_hook, _filho)",
        "            if not _cfg['ativo']:",
        "                print(f'[DEP] {_filho}: inativo — nao disparado.')",
        "                continue",
        "            _status = status_dos_predecessores(_hook, _filho, _dref)",
        "            _ok, _pendentes = avaliar_liberacao(_status)",
        "            if not _ok:",
        "                print(f'[DEP] {_filho}: aguardando {_pendentes} (data ref {_dref}).')",
        "                continue",
        "            if not dentro_da_janela(_cfg['nao_iniciar_antes'], _agora):",
        "                # Liberado, mas cedo demais. A guardiã dispara na hora certa.",
        "                print(f\"[DEP] {_filho}: liberado, aguardando janela de \"",
        "                      f\"{_cfg['nao_iniciar_antes']} (data ref {_dref}).\")",
        "                continue",
        "            _disparar_dag(_filho, _dref)",
        "        except Exception as e:",
        "            print(f'[DEP] Aviso: {_filho} nao disparado ({e}) — a guardia cobre.')",
        "",
        "def _disparar_dag(nome_filho, data_referencia):",
        "    \"\"\"Coloca o dependente em execução, herdando a data de referência.",
        "",
        "    A marca AGUARDANDO_DEPENDENCIA é o que evita disparo em dobro quando",
        "    a guardiã passa no mesmo instante: quem consegue mudar a linha para",
        "    EXECUTANDO é quem dispara. Sem esse aperto, dois caminhos poderiam",
        "    subir a mesma corrida duas vezes.\"\"\"",
        "    _hook = MsSqlHook(mssql_conn_id=MSSQL_CONN_ID)",
        "    _conn = _hook.get_conn(); _cur = _conn.cursor()",
        "    try:",
        "        _cur.execute(",
        '            "UPDATE dbo.etl_pipeline_execucao SET status=\'EXECUTANDO\', "',
        '            "  disparado_por=%s, atualizado_em=GETDATE() "',
        '            "WHERE pipeline_name=%s AND data_referencia=%s "',
        '            "  AND status=\'AGUARDANDO_DEPENDENCIA\'",',
        "            (PIPELINE_NAME, nome_filho, data_referencia))",
        "        _tomou = _cur.rowcount",
        "        if _tomou == 0:",
        "            _cur.execute(",
        '                "SELECT COUNT(*) FROM dbo.etl_pipeline_execucao "',
        '                "WHERE pipeline_name=%s AND data_referencia=%s",',
        "                (nome_filho, data_referencia))",
        "            if (_cur.fetchone() or [0])[0]:",
        "                _conn.commit()",
        "                print(f'[DEP] {nome_filho}: ja existe corrida em {data_referencia} — nao redisparado.')",
        "                return",
        "            _cur.execute(",
        '                "INSERT INTO dbo.etl_pipeline_execucao "',
        '                "(pipeline_name, data_referencia, status, disparado_por) "',
        '                "VALUES (%s,%s,\'EXECUTANDO\',%s)",',
        "                (nome_filho, data_referencia, PIPELINE_NAME))",
        "        _conn.commit()",
        "    finally:",
        "        _cur.close(); _conn.close()",
        "    try:",
        "        from airflow.api.client.local_client import Client",
        "        Client(None, None).trigger_dag(",
        "            dag_id=nome_filho,",
        "            run_id=f'dep__{PIPELINE_NAME}__{data_referencia}',",
        "            conf={'data_referencia': str(data_referencia), 'disparado_por': PIPELINE_NAME},",
        "        )",
        "    except Exception as e:",
        "        # DEVOLVE a reserva. O EXECUTANDO foi commitado antes do trigger",
        "        # para impedir disparo duplo; se o trigger falha (DAG ainda não",
        "        # serializada, worker morto), sem esta reversão a corrida ficava",
        "        # presa em EXECUTANDO — a guardiã só age sobre",
        "        # AGUARDANDO_DEPENDENCIA e nunca mais tentava, nem alertava.",
        "        _c2 = _hook.get_conn(); _cur2 = _c2.cursor()",
        "        try:",
        "            _cur2.execute(",
        '                "UPDATE dbo.etl_pipeline_execucao "',
        '                "SET status=\'AGUARDANDO_DEPENDENCIA\', motivo=%s, atualizado_em=GETDATE() "',
        '                "WHERE pipeline_name=%s AND data_referencia=%s "',
        # execution_id IS NULL: só a RESERVA volta atrás. Se a corrida real já
        # adotou a linha, ela está rodando e não pode ser revertida.
        '                "  AND status=\'EXECUTANDO\' AND execution_id IS NULL",',
        "                (f'trigger falhou: {type(e).__name__}'[:500], nome_filho, data_referencia))",
        "            _c2.commit()",
        "        finally:",
        "            _cur2.close(); _c2.close()",
        "        print(f'[DEP] {nome_filho}: trigger falhou ({e}) — reserva devolvida para a guardia.')",
        "        raise",
        "    print(f'[DEP] {nome_filho} DISPARADO (data ref {data_referencia}).')",
        "",
        "def registrar_falha(**context):",
        "    \"\"\"Task com ONE_FAILED: qualquer job que falhe reprova a corrida.",
        "",
        "    Task e não on_failure_callback em default_args porque as constantes",
        "    são emitidas ANTES dos helpers no arquivo gerado — referenciar a",
        "    função ali daria NameError no import da DAG. Também segue o padrão",
        "    que o teams_error já usa neste gerador.\"\"\"",
        "    _registrar_execucao('FALHA', context, motivo='job do pipeline falhou')",
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
        '    if code == 2:  return "WARNING"  # espelha o DataStage; nao falha o pipeline',
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
        '        "WHERE execution_id=%s AND pipeline=%s AND job_name=%s AND task_id=%s",',
        "        parameters=(status_code, execution_id, PIPELINE_NAME, job_name, task_key),",
        "    )",
        "",
        "def _teams_post_card(title, facts, status='INFO', subtitle=None, button=None):",
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
        "    content = {",
        '        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",',
        '        "type": "AdaptiveCard", "version": "1.4",',
        '        "body": body,',
        "    }",
        "    # Botao de link opcional (Action.OpenUrl) — so quando titulo e url presentes.",
        "    if button and button.get('url'):",
        '        content["actions"] = [{"type": "Action.OpenUrl",',
        "                               \"title\": button.get('titulo') or 'Abrir',",
        "                               \"url\": button.get('url')}]",
        "    payload = {",
        '        "type": "message",',
        '        "attachments": [{',
        '            "contentType": "application/vnd.microsoft.card.adaptive",',
        '            "content": content,',
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
        "def _notif_resolve_linhas(up_jobs, execution_id, context):",
        "    # {linhas} = rows_out do(s) job(s) a montante. 1º tenta o XCom do run",
        "    # (DataStageOperator empurra 'rows_out' no JSON); fallback: etl_ds_job_log",
        "    # da execução atual. Degrada para '' se nada disponível.",
        "    total = 0; achou = False",
        "    ti = context.get('ti') if context else None",
        "    for jn in (up_jobs or []):",
        "        val = None",
        "        if ti is not None:",
        "            try:",
        "                _x = ti.xcom_pull(task_ids=jn)",
        "                if _x:",
        "                    _o = json.loads(_x) if isinstance(_x, str) else _x",
        "                    if isinstance(_o, dict) and _o.get('rows_out') is not None:",
        "                        val = int(_o['rows_out'])",
        "            except Exception:",
        "                val = None",
        "        if val is None and execution_id:",
        "            try:",
        "                hook = MsSqlHook(mssql_conn_id=MSSQL_CONN_ID)",
        "                _r = hook.get_first(",
        '                    "SELECT TOP 1 rows_out FROM dbo.etl_ds_job_log "',
        '                    "WHERE execution_id=%s AND pipeline_name=%s AND job_name=%s "',
        '                    "ORDER BY COALESCE(updated_at, last_polled_at) DESC",',
        "                    parameters=(execution_id, PIPELINE_NAME, jn),",
        "                )",
        "                if _r and _r[0] is not None:",
        "                    val = int(_r[0])",
        "            except Exception as _e:",
        "                print(f'[NOTIF] rows_out de {jn} indisponivel: {_e}')",
        "                val = None",
        "        if val is not None:",
        "            total += val; achou = True",
        "    return str(total) if achou else ''",
        "",
        "def _notif_status_geral(execution_id):",
        "    # Status agregado do pipeline na execução (mesma regra do teams_end).",
        "    try:",
        "        hook = MsSqlHook(mssql_conn_id=MSSQL_CONN_ID)",
        "        row = hook.get_first(",
        '            "SELECT CASE WHEN SUM(CASE WHEN status=\'FAILED\' THEN 1 ELSE 0 END)>0 THEN \'FAILED\' "',
        '            "     WHEN SUM(CASE WHEN status=\'WARNING\' THEN 1 ELSE 0 END)>0 THEN \'WARNING\' "',
        '            "     WHEN SUM(CASE WHEN status=\'SUCCESS\' THEN 1 ELSE 0 END)>0 THEN \'SUCCESS\' "',
        '            "     WHEN SUM(CASE WHEN status=\'SKIPPED\' THEN 1 ELSE 0 END)>0 THEN \'SKIPPED\' "',
        '            "     ELSE \'INFO\' END "',
        '            "FROM dbo.etl_job_execution WHERE execution_id=%s AND pipeline=%s",',
        "            parameters=(execution_id, PIPELINE_NAME),",
        "        )",
        "        return row[0] if row and row[0] else 'INFO'",
        "    except Exception:",
        "        return 'INFO'",
        "",
        "def _notif_interpola(texto, mapa):",
        "    # Substitui placeholders {pipeline} {job} {linhas} {status} {data} de forma",
        "    # tolerante (placeholder desconhecido fica intacto — não quebra).",
        "    out = texto or ''",
        "    for k, v in mapa.items():",
        "        out = out.replace('{' + k + '}', str(v) if v is not None else '')",
        "    return out",
        "",
        "def _resolve_e_envia_notificacao(job, grupo_id, template_id, mensagem, up_jobs, execution_id, context):",
        "    hook = MsSqlHook(mssql_conn_id=MSSQL_CONN_ID)",
        "    # 1) Webhook do grupo (canal Teams). Sem webhook → cai no Variable padrão.",
        "    webhook = None; titulo = None",
        "    try:",
        "        if grupo_id is not None:",
        "            g = hook.get_first(",
        '                "SELECT webhook_url FROM dbo.etl_msg_grupo WHERE id=%s AND ativo=1",',
        "                parameters=(grupo_id,),",
        "            )",
        "            if g and g[0]:",
        "                webhook = g[0]",
        "    except Exception as _e:",
        "        print(f'[NOTIF] grupo {grupo_id} indisponivel: {_e}')",
        "    # 2) Texto: mensagem inline; se vazia, o corpo do template. O TEMPLATE",
        "    # tambem define facts(JSON)/cor/botao do card estruturado (migration 050).",
        "    corpo = (mensagem or '').strip()",
        "    tpl_facts_raw = None; tpl_cor = None; tpl_btn_txt = None; tpl_btn_url = None",
        "    if template_id is not None:",
        "        t = None",
        "        try:",
        "            t = hook.get_first(",
        '                "SELECT titulo, corpo, facts, cor, botao_texto, botao_url "',
        '                "FROM dbo.etl_msg_template WHERE id=%s AND ativo=1",',
        "                parameters=(template_id,),",
        "            )",
        "            if t:",
        "                titulo = t[0]",
        "                if not corpo: corpo = t[1] or ''",
        "                tpl_facts_raw = t[2]; tpl_cor = t[3]",
        "                tpl_btn_txt = t[4]; tpl_btn_url = t[5]",
        "        except Exception as _e:",
        "            # Colunas do card podem nao existir (sem 050) — fallback ao SELECT antigo.",
        "            print(f'[NOTIF] card cols indisponiveis p/ template {template_id}: {_e}')",
        "            try:",
        "                t = hook.get_first(",
        '                    "SELECT titulo, corpo FROM dbo.etl_msg_template WHERE id=%s AND ativo=1",',
        "                    parameters=(template_id,),",
        "                )",
        "                if t:",
        "                    titulo = t[0]",
        "                    if not corpo: corpo = t[1] or ''",
        "            except Exception as _e2:",
        "                print(f'[NOTIF] template {template_id} indisponivel: {_e2}')",
        "    # 3) Placeholders.",
        "    linhas = _notif_resolve_linhas(up_jobs, execution_id, context)",
        "    status_geral = _notif_status_geral(execution_id)",
        "    mapa = {",
        "        'pipeline': PIPELINE_NAME, 'job': job, 'linhas': linhas,",
        "        'status': status_geral, 'data': _now_str(),",
        "    }",
        "    corpo_final  = _notif_interpola(corpo, mapa)",
        "    titulo_final = _notif_interpola(titulo or 'Notificação', mapa)",
        "    facts = [",
        "        _fact('Pipeline', PIPELINE_NAME),",
        "        _fact('Execução', execution_id),",
        "    ]",
        "    if linhas != '':",
        "        facts.append(_fact('Linhas', linhas))",
        "    # facts do template (JSON array de {label,value}; value interpolado).",
        "    # Tolerante: JSON invalido/None → ignora o extra, nao quebra o envio.",
        "    if tpl_facts_raw:",
        "        try:",
        "            _arr = json.loads(tpl_facts_raw) if isinstance(tpl_facts_raw, str) else tpl_facts_raw",
        "            if isinstance(_arr, list):",
        "                for _f in _arr:",
        "                    if isinstance(_f, dict) and (_f.get('label') or ''):",
        "                        facts.append(_fact(_f.get('label'), _notif_interpola(str(_f.get('value') or ''), mapa)))",
        "        except Exception as _e:",
        "            print(f'[NOTIF] facts do template invalidos: {_e}')",
        "    # cor do template → status do card; vazio/'auto' usa o status agregado.",
        "    _cor_map = {'error': 'FAILED', 'warning': 'WARNING', 'success': 'SUCCESS', 'info': 'INFO'}",
        "    card_status = _cor_map.get((tpl_cor or '').strip().lower(), status_geral)",
        "    # botao de link opcional (texto/url interpolados); url vazia → sem botao.",
        "    btn_url_final = _notif_interpola(tpl_btn_url or '', mapa).strip()",
        "    btn_txt_final = _notif_interpola(tpl_btn_txt or '', mapa).strip()",
        "    button = {'titulo': btn_txt_final, 'url': btn_url_final} if btn_url_final else None",
        "    print(f'[NOTIF] {job}: grupo={grupo_id} template={template_id} linhas={linhas!r} status={card_status} botao={bool(button)}')",
        "    # Webhook específico do grupo: posta direto; senão usa _teams_post_card",
        "    # (Variable padrão do projeto). Mantém o mesmo card adaptativo (mesmos",
        "    # facts/cor/botao nos dois caminhos).",
        "    if webhook:",
        "        try:",
        '            _icon = {"SUCCESS": "🟢", "WARNING": "🟡", "FAILED": "🔴", "INFO": "🔵"}.get(card_status, "⚪")',
        '            _color = {"SUCCESS": "Good", "WARNING": "Warning", "FAILED": "Attention", "INFO": "Accent"}.get(card_status, "Default")',
        '            _content = {"$schema": "http://adaptivecards.io/schemas/adaptive-card.json",',
        '                        "type": "AdaptiveCard", "version": "1.4",',
        '                        "body": [',
        '                            {"type": "TextBlock", "text": f"{_icon} {titulo_final}", "size": "Large", "weight": "Bolder", "wrap": True, "color": _color},',
        '                            {"type": "TextBlock", "text": corpo_final, "wrap": True},',
        '                            {"type": "FactSet", "facts": facts},',
        "                        ]}",
        "            if button and button.get('url'):",
        '                _content["actions"] = [{"type": "Action.OpenUrl",',
        "                                        \"title\": button.get('titulo') or 'Abrir',",
        "                                        \"url\": button.get('url')}]",
        '            payload = {"type": "message", "attachments": [{',
        '                "contentType": "application/vnd.microsoft.card.adaptive",',
        '                "content": _content}]}',
        "            resp = requests.post(webhook, json=payload, timeout=15)",
        "            print(f'[NOTIF] webhook do grupo status={resp.status_code}')",
        "        except Exception as _e:",
        "            print(f'[NOTIF] falha ao postar no webhook do grupo: {_e}')",
        "    else:",
        "        _teams_post_card(title=titulo_final, subtitle=corpo_final, facts=facts, status=card_status, button=button)",
        "",
        "def _resolve_e_roda_sql(sql, conn_id, database, context, on_error='nulo'):",
        "    # Nó SQL: roda o SELECT e devolve o valor ESCALAR (1a coluna da 1a linha),",
        "    # que vira o XCom default da task (a Decisao 'valor_sql' a jusante o le).",
        "    # Conexao resolvida pelo ORQUESTRA (dbo.etl_conexao primeiro, Airflow",
        "    # como fallback) — antes o MsSqlHook ignorava as conexoes nativas.",
        "    # on_error='falhar' -> erro LEVANTA (task falha alto, fail-fast do run);",
        "    # 'nulo'/ausente (legado) -> log + None (nao derruba a DAG).",
        "    _falha_alto = str(on_error or '').strip().lower() == 'falhar'",
        "    if not sql:",
        "        if _falha_alto:",
        "            raise ValueError('[SQL NODE] sql vazio — on_error=falhar')",
        "        print('[SQL NODE] sql vazio — valor None.')",
        "        return None",
        "    try:",
        "        from utils.conn_resolver import abrir_conexao_mssql",
        "        _cid = (conn_id or '').strip() or MSSQL_CONN_ID",
        "        _db = (database or '').strip() or None",
        "        _conn = abrir_conexao_mssql(_cid, database=_db, autocommit=True,",
        "                                    appname='orquestra-sql-node')",
        "        try:",
        "            _cur = _conn.cursor()",
        "            _cur.execute(sql)",
        "            row = _cur.fetchone()",
        "        finally:",
        "            _conn.close()",
        "        val = row[0] if row else None",
        "        print('[SQL NODE] conn=' + _cid + ' database=' + repr(_db) + ' -> valor=' + repr(val))",
        "        return val",
        "    except Exception as _e:",
        "        if _falha_alto:",
        "            raise",
        "        print('[SQL NODE] falha ao rodar SELECT (' + str(_e) + ') — valor None.')",
        "        return None",
        "",
        "def _flow_close(**context):",
        "    # SKIPPED de 1a classe: registra na telemetria os jobs PULADOS POR",
        "    # DECISAO nesta execucao (state='skipped'). Job que nao rodou por",
        "    # FALHA a montante (upstream_failed) segue SEM linha — semantica",
        "    # diferente (precisa reprocessar), nao pode virar SKIPPED.",
        "    execution_id = context['ts_nodash']",
        "    dr = context.get('dag_run')",
        "    if dr is None:",
        "        return",
        "    try:",
        "        estados = {ti.task_id: str(ti.state) for ti in dr.get_task_instances()}",
        "    except Exception as e:",
        "        print(f'[FLOW CLOSE] get_task_instances falhou ({e}) — sem registro de SKIPPED.')",
        "        return",
        "    hook = MsSqlHook(mssql_conn_id=MSSQL_CONN_ID)",
        "    agora = _now_str()",
        "    for job in FLOW_JOBS:",
        "        if estados.get(job) != 'skipped':",
        "            continue",
        "        try:",
        "            _exec_telemetry(hook, execution_id, job, job, 'SKIPPED', agora, agora, 0, None)",
        "            print(f'[FLOW CLOSE] SKIPPED registrado para {job}.')",
        "        except Exception as e:",
        "            print(f'[FLOW CLOSE] falha ao registrar SKIPPED de {job}: {e}')",
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
        # Duração = relógio de parede (a SOMA inflava pipelines com jobs paralelos).
        '        "SELECT pipeline, MIN(start_time), MAX(end_time), "',
        '        "DATEDIFF(SECOND, MIN(start_time), MAX(COALESCE(end_time, GETDATE()))), "',
        '        "CASE WHEN SUM(CASE WHEN status=\'FAILED\' THEN 1 ELSE 0 END)>0 THEN \'FAILED\' "',
        '        "     WHEN SUM(CASE WHEN status=\'WARNING\' THEN 1 ELSE 0 END)>0 THEN \'WARNING\' "',
        '        "     WHEN SUM(CASE WHEN status=\'SUCCESS\' THEN 1 ELSE 0 END)>0 THEN \'SUCCESS\' "',
        '        "     WHEN SUM(CASE WHEN status=\'SKIPPED\' THEN 1 ELSE 0 END)>0 THEN \'SKIPPED\' "',
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
        '    titles = {"SUCCESS": "Execução concluída com sucesso", "WARNING": "Execução concluída com avisos", "FAILED": "Execução finalizada com falha", "SKIPPED": "Execução pulada"}',
        '    subtitles = {',
        '        "SUCCESS": f"O pipeline {pipeline} foi executado e finalizado sem erros.",',
        '        "WARNING": f"O pipeline {pipeline} foi concluído, mas registrou avisos durante a execução.",',
        '        "FAILED":  f"O pipeline {pipeline} foi encerrado com falha. Verifique os jobs com erro.",',
        '        "SKIPPED": f"Todos os jobs do pipeline {pipeline} foram pulados pela decisão nesta execução.",',
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
        '        "SELECT pipeline, MIN(start_time), MAX(end_time), "',
        '        "DATEDIFF(SECOND, MIN(start_time), MAX(COALESCE(end_time, GETDATE()))) "',
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
        "def _disparo_por_evento(context):",
        "    \"\"\"Esta corrida veio de uma dependência (push do predecessor ou guardiã)?",
        "",
        "    Distinção que faltava e que causou os dois piores defeitos da revisão:",
        "    as regras de RELÓGIO abaixo só fazem sentido quando quem disparou foi o",
        "    cron. Num disparo por dependência o instante é o do término do",
        "    predecessor — que nunca coincide com a lista de horários, e fazia o",
        "    dependente ser PULADO em 100% das vezes.\"\"\"",
        "    _rid = str(context.get('run_id', ''))",
        "    return _rid.startswith('dep__') or _rid.startswith('guardia__')",
        "",
        "def _check_agenda_regras(**context):",
        "    \"\"\"Este pipeline deve executar ESTA corrida?",
        "",
        "    Duas famílias de regra, que antes estavam misturadas:",
        "",
        "    • RELÓGIO (quando disparar) — horários específicos e dia+hora do mês.",
        "      Existem para filtrar os disparos do cron, que acontece na união",
        "      minuto×hora. Não se aplicam a disparo manual nem por dependência.",
        "",
        "    • DIA DE PROCESSAMENTO (se deve rodar hoje) — dia da semana, dia do",
        "      mês, dias úteis e calendário. Valem SEMPRE, e são avaliadas contra a",
        "      DATA DE REFERÊNCIA, não contra o relógio: um pipeline de sexta que",
        "      só termina de ser liberado no sábado pertence à sexta.",
        "",
        "    Retorna False (ShortCircuit) para pular a execução inteira.\"\"\"",
        "    _por_evento = _disparo_por_evento(context)",
        "    _manual = str(context.get('run_id', '')).startswith('manual')",
        "    _dref = _data_referencia(context)",
        "",
        "    # ── Regras de RELÓGIO ───────────────────────────────────────────",
        "    if HORARIOS_ESPECIFICOS and not _manual and not _por_evento:",
        "        _die = context.get('data_interval_end') or context.get('logical_date')",
        "        if _die is not None:",
        "            _hhmm = _die.in_timezone(LOCAL_TZ).strftime('%H:%M')",
        "            if _hhmm not in HORARIOS_ESPECIFICOS:",
        "                print(f\"[AGENDA] {_hhmm} fora dos horarios configurados {HORARIOS_ESPECIFICOS} — execucao pulada.\")",
        "                return False",
        "    if DIAS_HORARIOS_MES and not _manual and not _por_evento:",
        "        _die = context.get('data_interval_end') or context.get('logical_date')",
        "        if _die is not None:",
        "            _local = _die.in_timezone(LOCAL_TZ)",
        "            _dia = _local.day",
        "            _hhmm = _local.strftime('%H:%M')",
        "            if _hhmm not in DIAS_HORARIOS_MES.get(_dia, []):",
        "                print(f\"[AGENDA] dia {_dia} as {_hhmm} fora da configuracao {DIAS_HORARIOS_MES} — execucao pulada.\")",
        "                return False",
        "",
        "    # ── Regras de DIA DE PROCESSAMENTO ──────────────────────────────",
        "    # RESTRICAO_DIA existe só em pipeline SEM cron (disparado por",
        "    # dependência): a restrição de dia morava no próprio cron, e ao trocá-lo",
        "    # por schedule=None ela evaporava — um fechamento mensal do dia 5 passava",
        "    # a rodar TODO dia em que o predecessor concluísse.",
        "    if RESTRICAO_DIA:",
        "        _tipo = RESTRICAO_DIA.get('tipo')",
        "        if _tipo == 'weekly':",
        "            _dow_ok = (_dref.isoweekday() % 7) == int(RESTRICAO_DIA.get('dow') or 0) % 7",
        "            if not _dow_ok:",
        "                print(f\"[AGENDA] {_dref} nao e o dia da semana configurado ({RESTRICAO_DIA}) — execucao pulada.\")",
        "                return False",
        "        elif _tipo in ('monthly', 'biweekly'):",
        "            _dom = int(RESTRICAO_DIA.get('dom') or 1)",
        "            _dias = [_dom] if _tipo == 'monthly' else [_dom, _dom + 15]",
        "            if _dref.day not in _dias:",
        "                print(f\"[AGENDA] dia {_dref.day} nao esta em {_dias} (config {RESTRICAO_DIA}) — execucao pulada.\")",
        "                return False",
        "",
        "    hook = MsSqlHook(mssql_conn_id=MSSQL_CONN_ID)",
        "    try:",
        "        row = hook.get_first(",
        '            "SELECT TOP 1 motivo FROM dbo.etl_blackout "',
        '            "WHERE ativo=1 AND GETDATE() BETWEEN inicio AND fim "',
        '            "AND (escopo IS NULL OR escopo=%s OR escopo=%s)",',
        "            parameters=(PROJECT_NAME, PIPELINE_NAME),",
        "        )",
        "        if row:",
        "            # Blackout é uma JANELA DE RELÓGIO (freeze operacional agora),",
        "            # então continua comparando com GETDATE() de propósito.",
        "            print(f\"[AGENDA] Blackout vigente: {row[0]} — execucao pulada.\")",
        "            return False",
        "    except Exception as e:",
        "        print(f\"[AGENDA] Aviso: verificacao de blackout falhou ({e}) — seguindo.\")",
        "    # Dias úteis e calendário passam a olhar a DATA DE REFERÊNCIA. Com o",
        "    # relógio, a corrida de sexta que atravessava a meia-noite era pulada no",
        "    # sábado — justamente o caso que a data de referência existe para tratar.",
        "    if SOMENTE_DIAS_UTEIS and _dref.weekday() >= 5:",
        "        print(f\"[AGENDA] Data de referencia {_dref} e fim de semana e o pipeline e somente dias uteis — execucao pulada.\")",
        "        return False",
        "    if CALENDARIO_NOME:",
        "        try:",
        "            row = hook.get_first(",
        '                "SELECT TOP 1 ISNULL(descricao, \'\') FROM dbo.etl_calendario "',
        '                "WHERE calendario_nome=%s AND data=%s",',
        "                parameters=(CALENDARIO_NOME, _dref),",
        "            )",
        "            if row is not None:",
        "                print(f\"[AGENDA] Data de referencia {_dref} bloqueada no calendario {CALENDARIO_NOME} ({row[0]}) — execucao pulada.\")",
        "                return False",
        "        except Exception as e:",
        "            print(f\"[AGENDA] Aviso: verificacao de calendario falhou ({e}) — seguindo.\")",
        "    return True",
        "",
        # Envolve as regras em vez de instrumentar cada `return False`: são cinco
        # caminhos de saída (horários, dia+hora, blackout, dia útil, calendário)
        # e esquecer um deixaria a corrida sem registro nenhum — indistinguível
        # de "nunca foi ordenada", que é o que a guardiã da F4 vai procurar.
        "def check_agenda(**context):",
        "    _ok = _check_agenda_regras(**context)",
        "    if not _ok:",
        "        _registrar_execucao('PULADO', context, motivo='fora da agenda (blackout/dia util/calendario/horario)')",
        "    return _ok",
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
    # flow_close: só em pipelines com Decisão (única origem de skip por ramo).
    # ALL_DONE — roda no fechamento do run e registra SKIPPED de 1ª classe.
    if has_decision:
        teams_tasks.append("\n".join([
            't_flow_close = PythonOperator(',
            '    task_id="flow_close",',
            '    python_callable=_flow_close,',
            '    trigger_rule=TriggerRule.ALL_DONE,',
            ')',
        ]))

    # Jobs a montante de cada nó de notificação, usados para resolver {linhas}:
    # os deps diretos do nó + os deps da(s) decisão(ões) que o citam num ramo
    # (quando é ramo_falso de uma 'linhas_job', o rows_out avaliado é o do job
    # do qual a decisão depende). Mantém só nomes de jobs conhecidos.
    _deps_by_job = {j["job_name"]: _deps_of(j) for j in sorted_jobs}
    _notif_upstream = {}
    for nname in notificacao_nodes:
        ups = list(_deps_by_job.get(nname, []))
        for dname in branch_parents.get(nname, []):
            ups += _deps_by_job.get(dname, [])
        # dedup preservando ordem
        _notif_upstream[nname] = list(dict.fromkeys(ups))

    _notif_set = set(notificacao_nodes)
    job_blocks = []
    for j in sorted_jobs:
        if _alias(j) == "decisao":
            job_blocks.append(_decision_block(
                j, decision_conditions.get(j["job_name"], {}), _job_names, _notif_set))
        elif _alias(j) == "notificacao":
            job_blocks.append(_notify_block(
                j, notificacao_nodes.get(j["job_name"], {}),
                _notif_upstream.get(j["job_name"], []),
                branch_reachable=(j["job_name"] in reachable)))
        elif _alias(j) == "sql":
            job_blocks.append(_sql_block(
                j, sql_nodes.get(j["job_name"], {}),
                branch_reachable=(j["job_name"] in reachable)))
        else:
            job_blocks.append(_task_block(j, project, pname, branch_reachable=(j["job_name"] in reachable)))

    # Fase 4 — check_agenda: blackout/freeze + calendário + dias úteis.
    # ShortCircuitOperator pula TODAS as tasks downstream (inclusive ALL_DONE).
    check_block = "\n".join([
        't_check_agenda = ShortCircuitOperator(',
        '    task_id="check_agenda",',
        '    python_callable=check_agenda,',
        ')',
        '',
        '# Execução do pipeline carimbada com a data de referência (ODATE).',
        '# Fica DEPOIS do check_agenda: corrida pulada é registrada como PULADO',
        '# pelo próprio check, não como EXECUTANDO que nunca termina.',
        't_exec_inicio = PythonOperator(',
        '    task_id="registrar_inicio",',
        '    python_callable=registrar_inicio,',
        ')',
    ])

    # Fechamento: só marca SUCESSO se nada falhou. ALL_SUCCESS não serve quando o
    # pipeline tem ramos que podem ser pulados por decisão — aí a convergência
    # legítima traz tasks SKIPPED.
    exec_fim_block = "\n".join(filter(None, [
        't_exec_fim = PythonOperator(',
        '    task_id="registrar_fim",',
        '    python_callable=registrar_fim,',
        # ALL_DONE: com ramo pulado o publish_dataset fica SKIPPED e o
        # fechamento condicional anterior era pulado junto, deixando a corrida
        # presa em EXECUTANDO. A guarda de estado dentro da função é quem impede
        # um PULADO/FALHA de virar SUCESSO.
        '    trigger_rule=TriggerRule.ALL_DONE,',
        ')',
        '',
        '# FALHA da corrida. ONE_FAILED (mesmo padrão do teams_error): basta um',
        '# job reprovar para o pipeline não liberar quem depende dele (F3).',
        't_exec_falha = PythonOperator(',
        '    task_id="registrar_falha",',
        '    python_callable=registrar_falha,',
        '    trigger_rule=TriggerRule.ONE_FAILED,',
        ')',
        '',
        '# Libera quem depende deste pipeline. Depois do registrar_fim: só uma',
        '# corrida marcada SUCESSO pode satisfazer a condição de alguém.',
        't_disparar_dependentes = PythonOperator(',
        '    task_id="disparar_dependentes",',
        '    python_callable=disparar_dependentes,',
        ')',
    ]))

    # Fase 4 — publica Dataset ao final (consumido por pipelines com trigger_por_dependencia)
    publish_block = "\n".join(filter(None, [
        't_publish_dataset = EmptyOperator(',
        '    task_id="publish_dataset",',
        '    outlets=[Dataset(DATASET_URI)],',
        # Convergência final: tolera ramos pulados (≥1 t_end com sucesso).
        ('    trigger_rule=TriggerRule.NONE_FAILED_MIN_ONE_SUCCESS,'
         if (has_decision or has_notificacao or has_sql_node) else None),
        ')',
    ]))

    # (dep_list / tem_dependencia já definidos no topo — as constantes do
    # arquivo gerado dependem deles.)
    # F3 da spec de dependências: o ExternalTaskSensor SAIU.
    #
    # Ele exigia que pai e filho tivessem o MESMO logical_date — ou seja, o mesmo
    # horário de agendamento — e desistia depois de 1h fixa. Na prática só
    # funcionava na configuração que ninguém faz (pai e filho no mesmo horário) e
    # reprovava qualquer pai que durasse mais de uma hora.
    #
    # Agora o pipeline dependente não tem agenda própria: é DISPARADO por quem
    # ele espera, assim que a última dependência conclui na mesma data de
    # referência. Sem sensor, sem polling, sem janela perdida.
    # Rebuild imports_str after potential append
    imports_str = "\n".join(import_lines)

    dep_lines = []

    # O registro da execução entra logo depois do check_agenda e passa a ser a
    # raiz de tudo que vem abaixo: assim a corrida existe no banco ANTES do
    # primeiro job, e uma falha logo no início já encontra a linha para marcar.
    dep_lines.append("t_check_agenda >> t_exec_inicio")


    # Modo de dependência: EXPLÍCITO (algum job tem depends_on_jobs OU há um nó
    # de Decisão) ou ONDAS (execution_order). Opt-in por pipeline — pipelines
    # sem deps explícitas/decisão continuam exatamente como antes.
    # (_job_names/_deps_of já definidos acima, junto do parsing das decisões.)
    explicit_deps = has_decision or has_notificacao or has_sql_node or any(_deps_of(j) for j in sorted_jobs)

    notif_task_refs = []   # t_notif_* a convergir no publish_dataset
    sql_task_refs = []     # t_sql_* a convergir no publish_dataset
    if explicit_deps:
        root_anchor = "t_exec_inicio"
        teams_start_done = False
        def _end_ref(d):
            # Tarefa de conclusão de uma dependência. Nós de notificação, decisão e
            # SQL NÃO têm t_end_ próprio (são especiais): a notificação conclui em
            # t_notif_<d>, a decisão roteia via t_dec_<d> e o nó SQL roda em
            # t_sql_<d>. Um job que depende desses deve referenciá-los, não
            # t_end_<d> (que seria NameError no import do Airflow).
            if d in notificacao_nodes:
                return f"t_notif_{_varname(d)}"
            if d in decision_conditions:
                return f"t_dec_{_varname(d)}"
            if d in sql_nodes:
                return f"t_sql_{_varname(d)}"
            return f"t_end_{_varname(d)}"
        for j in sorted_jobs:
            n = _varname(j["job_name"])
            deps = _deps_of(j)
            ends = [_end_ref(d) for d in deps]
            # Nó de Decisão: roteador (BranchPythonOperator). Liga ao upstream e
            # as arestas Decisão → t_start dos membros saem dos próprios membros
            # (via branch_parents), garantindo que o branch skip atue direto.
            if _alias(j) == "decisao":
                up = ("[" + ", ".join(ends) + "]" if len(ends) > 1 else ends[0]) if ends else root_anchor
                dep_lines.append(f"{up} >> t_dec_{n}")
                continue
            parents = branch_parents.get(j["job_name"], [])
            ups = ends + [f"t_dec_{_varname(d)}" for d in parents]
            up = ("[" + ", ".join(ups) + "]" if len(ups) > 1 else ups[0]) if ups else root_anchor
            # Nó de Notificação: executável, sem t_start/t_end. Liga ao upstream
            # (deps + decisões que o citam num ramo) direto ao t_notif_*; como é
            # tipicamente ramo_falso, o skip do ramo oposto chega via t_dec_*.
            if _alias(j) == "notificacao":
                dep_lines.append(f"{up} >> t_notif_{n}")
                notif_task_refs.append(f"t_notif_{n}")
                continue
            # Nó SQL: executável, sem t_start/t_end. Liga ao upstream direto ao
            # t_sql_*; roda o SELECT e publica o valor escalar (XCom) para a
            # Decisão 'valor_sql' a jusante. Converge no fechamento (como a
            # notificação) para não ficar pendente do publish_dataset.
            if _alias(j) == "sql":
                dep_lines.append(f"{up} >> t_sql_{n}")
                sql_task_refs.append(f"t_sql_{n}")
                continue
            is_root = (not deps) and (not parents)
            # Notificação de início no primeiro job raiz (sem deps/decisão)
            if is_root and (not teams_start_done) and f_ini:
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
            else:
                up = "t_exec_inicio"
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
    # Nós de notificação (sem t_end) convergem no fechamento: rodam antes do
    # publish_dataset e dos cards de fim/erro, e toleram skip (ramo oposto).
    for nref in notif_task_refs:
        dep_lines.append(f"{nref} >> t_publish_dataset")
        if f_fim:
            dep_lines.append(f"{nref} >> t_teams_end")
        if f_err:
            dep_lines.append(f"{nref} >> t_teams_error")
    # Nós SQL (sem t_end) convergem no fechamento como a notificação — rodam
    # antes do publish_dataset/cards de fim/erro. (A Decisão a jusante já depende
    # do t_sql_* via _end_ref, então o valor publicado é lido antes do roteio.)
    for sref in sql_task_refs:
        dep_lines.append(f"{sref} >> t_publish_dataset")
        if f_fim:
            dep_lines.append(f"{sref} >> t_teams_end")
        if f_err:
            dep_lines.append(f"{sref} >> t_teams_error")
    # flow_close fecha DEPOIS de tudo (ends + nós especiais) e ANTES do card de
    # fim — assim o teams_end já enxerga as linhas SKIPPED que ele gravou.
    if has_decision:
        dep_lines.append(f"{end_tasks_ref} >> t_flow_close")
        for nref in notif_task_refs:
            dep_lines.append(f"{nref} >> t_flow_close")
        for sref in sql_task_refs:
            dep_lines.append(f"{sref} >> t_flow_close")
        if f_fim:
            dep_lines.append("t_flow_close >> t_teams_end")

    # SUCESSO é gravado depois do publish_dataset — que já é o ponto de
    # convergência de tudo (ends, notificações e nós SQL). Pendurar aqui evita
    # repetir a lista de convergência e garante que nenhum ramo ficou de fora.
    dep_lines.append("t_publish_dataset >> t_exec_fim >> t_disparar_dependentes")
    # A task de FALHA pendura nos MESMOS fins de ramo do teams_error: ONE_FAILED
    # só dispara olhando os upstreams diretos, então pendurá-la apenas no
    # publish_dataset a deixaria cega para o ramo que falhou.
    dep_lines.append(f"{end_tasks_ref} >> t_exec_falha")
    for nref in notif_task_refs:
        dep_lines.append(f"{nref} >> t_exec_falha")
    for sref in sql_task_refs:
        dep_lines.append(f"{sref} >> t_exec_falha")

    with_parts = []
    with_parts.append(_ind(check_block))
    with_parts.append(_ind(exec_fim_block))
    with_parts.append(_ind(publish_block))
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

    if tem_dependencia:
        # Pipeline com dependência NÃO tem agenda própria: quem o coloca em
        # execução é o predecessor (t_disparar_dependentes) ou a guardiã (F4).
        # Manter um cron aqui recriaria o problema que a F3 resolve — a corrida
        # começaria no horário do relógio, não quando o insumo ficou pronto.
        schedule_line = (f'    schedule=None,  # disparado por dependência: {", ".join(dep_list)}')
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


def _dependencias_da_tabela(cursor):
    """{pipeline: 'A,B'} de etl_pipeline_dependencia — fonte da verdade (067).

    Devolve None (e não {}) quando a tabela não existe: um dicionário vazio
    seria indistinguível de "nenhum pipeline tem dependência" e apagaria as
    dependências de TODAS as DAGs num deploy que levasse `dags/` sem a
    migration. None faz o chamador preservar o que a proc trouxe.
    """
    try:
        cursor.execute(
            "SELECT pipeline_name, depende_de FROM dbo.etl_pipeline_dependencia "
            "WHERE tipo = 'PIPELINE' ORDER BY pipeline_name, depende_de")
        por_pipeline = defaultdict(list)
        for nome, dep in cursor.fetchall():
            por_pipeline[str(nome)].append(str(dep))
        return {nome: ",".join(deps) for nome, deps in por_pipeline.items()}
    except Exception as e:
        print(f"[FACTORY] dependencias da tabela indisponiveis ({e}) — usando o depends_on da proc.")
        return None


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

    # F6: a dependência que vai para a DAG vem da TABELA, não do CSV.
    # A stored procedure devolve o depends_on de etl_pipeline (mantido em
    # espelho); sobrescrever aqui evita mexer na proc — que é usada em outros
    # pontos — e faz a geração seguir a mesma fonte da verdade que o cadastro,
    # a guardiã e o disparo. Sem a migration 067 o valor da proc é preservado.
    _deps = _dependencias_da_tabela(cursor)
    if _deps is not None:
        for _p in pipelines:
            _p["depends_on"] = _deps.get(_p["pipeline_name"]) or None

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

    # Supplement: condição do nó de decisão (degrada se a coluna não existir — migration 043)
    try:
        cursor.execute(
            "SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='dbo' "
            "AND TABLE_NAME='etl_pipeline_job' AND COLUMN_NAME='condition_json'")
        if cursor.fetchone()[0]:
            cursor.execute(
                "SELECT pipeline_name, job_name, condition_json FROM dbo.etl_pipeline_job "
                "WHERE condition_json IS NOT NULL")
            _condmap = {(r[0], r[1]): r[2] for r in cursor.fetchall()}
            for j in jobs_all:
                j["condition_json"] = _condmap.get((j["pipeline_name"], j["job_name"]))
    except Exception as _ce:
        print(f"[FACTORY] condition_json supplement ignorado: {_ce}")

    # Supplement: config do nó de notificação (degrada se a coluna não existir — migration 049)
    try:
        cursor.execute(
            "SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='dbo' "
            "AND TABLE_NAME='etl_pipeline_job' AND COLUMN_NAME='notify_json'")
        if cursor.fetchone()[0]:
            cursor.execute(
                "SELECT pipeline_name, job_name, notify_json FROM dbo.etl_pipeline_job "
                "WHERE notify_json IS NOT NULL")
            _notifmap = {(r[0], r[1]): r[2] for r in cursor.fetchall()}
            for j in jobs_all:
                j["notify_json"] = _notifmap.get((j["pipeline_name"], j["job_name"]))
    except Exception as _ne:
        print(f"[FACTORY] notify_json supplement ignorado: {_ne}")

    # Supplement: config do nó SQL (degrada se a coluna não existir — migration 051)
    try:
        cursor.execute(
            "SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='dbo' "
            "AND TABLE_NAME='etl_pipeline_job' AND COLUMN_NAME='sql_json'")
        if cursor.fetchone()[0]:
            cursor.execute(
                "SELECT pipeline_name, job_name, sql_json FROM dbo.etl_pipeline_job "
                "WHERE sql_json IS NOT NULL")
            _sqlmap = {(r[0], r[1]): r[2] for r in cursor.fetchall()}
            for j in jobs_all:
                j["sql_json"] = _sqlmap.get((j["pipeline_name"], j["job_name"]))
    except Exception as _sqe:
        print(f"[FACTORY] sql_json supplement ignorado: {_sqe}")

    # Supplement: nó Python v2 (degrada se a coluna não existir — migration 059)
    try:
        cursor.execute(
            "SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='dbo' "
            "AND TABLE_NAME='etl_pipeline_job' AND COLUMN_NAME='python_json'")
        if cursor.fetchone()[0]:
            cursor.execute(
                "SELECT pipeline_name, job_name, python_json FROM dbo.etl_pipeline_job "
                "WHERE python_json IS NOT NULL")
            _pymap = {(r[0], r[1]): r[2] for r in cursor.fetchall()}
            for j in jobs_all:
                j["python_json"] = _pymap.get((j["pipeline_name"], j["job_name"]))
    except Exception as _pye:
        print(f"[FACTORY] python_json supplement ignorado: {_pye}")

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
