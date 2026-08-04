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

Registro de execução por data de referência (F2 — docs/retomada-f2-desenho.md):
  cada corrida grava UMA linha em dbo.etl_pipeline_execucao com a chave
  (pipeline, data_referencia, run_id) — EXECUTANDO/PULADO nascem no
  check_agenda, FALHA na task registrar_falha (espelho do teams_error),
  SUCESSO no próprio publish_dataset. O registro é observabilidade e NUNCA
  derruba a carga (degrada com aviso sem a migration 067).

Liberação por condição e disparo push (F3 — docs/retomada-f3-desenho.md):
  pipeline com dependência (tabela etl_pipeline_dependencia, migration 067)
  nasce sem gatilho próprio e é disparado pelo publish_dataset do
  predecessor, que — DEPOIS do commit do próprio SUCESSO — avalia os
  dependentes ao vivo (utils/dependencias.py: condição EXISTS por data de
  referência, pré-filtro de dia, claim serializable) e faz trigger_dag com o
  conf herdando data_referencia + dia_operacional. Regras de HORA do
  check_agenda valem só para disparo de agenda; regras de DIA valem para
  toda origem e julgam o dia operacional. Falha no disparo NUNCA derruba o
  pai (tudo logado com [DEP]). O ExternalTaskSensor e o consumo de Dataset
  saíram do gerador; o outlet permanece como ponte para DAGs antigas.
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

    # Sob demanda: sem agendamento. Cron None vira `schedule=None` na DAG — que
    # no Airflow é uma DAG ATIVA e visível, disparável só manualmente.
    #
    # Sem este caso, 'on_demand' caía no fallback do fim da função e virava
    # "{m} {h} * * *" com o horário PADRÃO do formulário (06:00): o pipeline que
    # o usuário pediu manual nascia rodando todo dia às 6h.
    if stype == "on_demand":
        return None, None, None

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


def _chave_ci(nome) -> str:
    """Chave de junção case-insensitive — espelha a colação CI do SQL Server.

    Os nomes cruzam TABELAS diferentes (etl_pipeline × etl_pipeline_job) e o
    banco os considera iguais ignorando caixa e espaço à direita; os dicts do
    Python, não. Sem esta normalização, um pipeline cadastrado em MAIÚSCULAS
    com etapas importadas do .dsx em CamelCase "perde" todas as etapas na
    factory (incidente SEQSSDVIDA6SINISTRO, 2026-08-01) e o run inteiro falha
    com "pipeline sem nenhuma etapa".
    """
    return (nome or "").strip().upper()


def _derivar_restricao_dia(pipeline, dias_horarios_mes):
    """Constante RESTRICAO_DIA do pipeline DEPENDENTE (F3, desenho §4.2).

    A restrição de DIA do agendamento não pode evaporar quando o gatilho
    próprio é desligado (D04: fechamento mensal dia 5 roda SÓ dia 5, nunca
    30×/mês) — ela vira constante gerada e o check_agenda a julga contra o
    dia operacional via utils.dependencias.dia_permitido, para TODA origem.

    Derivação com `is not None`, nunca `int(x or 1)`: dow=0 é DOMINGO (D05).
    Devolve None quando o agendamento não restringe dia (ex.: daily) — a
    interpretação (conversão cron-dow, quinzenal d/d+15) mora SÓ no
    dia_permitido; aqui é passthrough das colunas, com teste de paridade
    contra a derivação de runtime do utils/dependencias.config_dependente.
    """
    stype = (pipeline.get("schedule_type") or "daily").lower().strip()
    dias_semana = (pipeline.get("dias_semana") or "").strip()
    dow = pipeline.get("schedule_dow")
    dom = pipeline.get("schedule_dom")
    dias_mes = sorted(dias_horarios_mes) if dias_horarios_mes else None
    if stype not in ("weekly", "monthly", "biweekly") and not dias_mes and not dias_semana:
        return None
    return {
        "schedule_type": stype,
        "schedule_dow": int(dow) if dow is not None else None,
        "schedule_dom": int(dom) if dom is not None else None,
        "dias_semana": dias_semana,
        "dias_horarios_mes_dias": dias_mes,
    }


def _dependencias_da_tabela(cursor):
    """Supplement F3: dependências lidas DIRETO da tabela da migration 067
    (a sp_etl_pipelines_pendentes_criar não devolve depends_on — D37; a SP
    de produção pode divergir do repo, então ela NÃO muda: o supplement
    versiona junto do código que o consome).

    Contrato None × {} (D36): devolve **None** quando a tabela não existe
    (o chamador preserva o que houver — deploy de dags/ sem a 067 não pode
    apagar a dependência de todas as DAGs) e **dict {chave_ci: [predecessores]}**
    quando existe — vazio SOBRESCREVE (dependência removida É remoção).
    Erro de leitura é logado alto e tratado como tabela ausente: pipeline
    com dependência então recusa a geração ruidosamente (D40), nunca volta
    ao cron em silêncio.
    """
    try:
        cursor.execute("SELECT OBJECT_ID('dbo.etl_pipeline_dependencia','U')")
        row = cursor.fetchone()
        if not row or row[0] is None:
            return None
        cursor.execute(
            "SELECT pipeline_name, depende_de FROM dbo.etl_pipeline_dependencia "
            "WHERE tipo = 'PIPELINE'")
        mapa = {}
        for dependente, predecessor in cursor.fetchall():
            mapa.setdefault(_chave_ci(dependente), []).append(predecessor)
        return mapa
    except Exception as e:
        print(f"[FACTORY] AVISO: leitura de etl_pipeline_dependencia falhou ({e}) "
              "— tratando como tabela ausente (migration 067)")
        return None


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
            # ⚠️ O kwarg é proc_params: 'params' é reservado do BaseOperator
            # (lista → TypeError no import; conf não-vazia sobrescreve self.params).
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
                f'    proc_params={params_payload!r},',
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
    # ⚠️ F5 — `_LogStart` é `LogStartOperator` (utils/job_operators.py): um
    # PythonOperator que publica o atributo `reschedule` nos campos
    # serializados. SEM ele, o Airflow ACEITA a AirflowRescheduleException do
    # portão mas IGNORA a data do próximo teste (ReadyToRescheduleDep sai por
    # "Task is not in reschedule mode") — medido na prova viva: 56 verificações
    # em 5 minutos em vez de 1 por minuto. Sem os módulos de utils, o import
    # guardado do topo faz `_LogStart = PythonOperator` e o bloco volta a ser,
    # byte a byte, o de antes desta fase.
    log_start = "\n".join(filter(None, [
        f't_start_{vname} = _LogStart(',
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


_AGUARDE_POLITICAS = ("todas_sucesso", "todas_terminarem")


def _wait_block(job, aguarde_cfg, branch_reachable=False):
    """Bloco de um nó Aguarde: ponto de encontro entre pernas paralelas.

    EmptyOperator sem t_start/t_end (como os demais nós especiais — fica fora de
    end_tasks): não roda nada, não tem lineage. O que ele faz é inteiramente
    decidido pela trigger rule, derivada da política gravada em aguarde_json:

      todas_sucesso (default) → só libera o que vem depois se TODAS as pernas
        ligadas a ele tiverem sucesso. Alcançável a partir de um branch, usa a
        variante tolerante a skip, senão o ramo não escolhido (que chega
        SKIPPED) travaria a junção para sempre.
      todas_terminarem → libera assim que todas terminarem, com sucesso ou
        falha. É o caso da limpeza de arquivos compartilhados pelas pernas.

    A segunda política NÃO esconde a falha do pipeline: cada perna continua com
    o seu t_end em end_tasks e ligado ao fechamento, e é ele quem decide o
    estado do DagRun. Ver o teste-âncora em tests/test_dag_factory_aguarde.py.
    """
    name  = job["job_name"]
    vname = _varname(name)
    politica = (str((aguarde_cfg or {}).get("politica") or "").strip().lower()
                or "todas_sucesso")
    if politica not in _AGUARDE_POLITICAS:
        politica = "todas_sucesso"
    if politica == "todas_terminarem":
        rule = "TriggerRule.ALL_DONE"
    elif branch_reachable:
        rule = "TriggerRule.NONE_FAILED_MIN_ONE_SUCCESS"
    else:
        rule = "TriggerRule.ALL_SUCCESS"
    return "\n".join([
        f't_wait_{vname} = EmptyOperator(',
        f'    task_id={name!r},',
        f'    trigger_rule={rule},',
        f')',
    ])


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


def _generate_dag_source(pipeline, jobs):
    pname      = pipeline["pipeline_name"]
    project    = pipeline["project_name"]
    domain     = pipeline["domain"]
    tags_raw   = pipeline["tags"]
    sched      = pipeline["scheduled_time"]
    depends_on = (pipeline.get("depends_on") or "").strip() or None
    # F3 — dependências pela TABELA (supplement _dependencias_da_tabela):
    # None = migration 067 ausente; lista (possivelmente vazia) = a tabela é a
    # verdade. Sem a 067, pipeline COM dependência (via CSV) NÃO é gerado:
    # nem `schedule=None` sem mecanismo de disparo (nunca roda, mudo), nem
    # regressão a cron (roda sozinho, mudo — a classe do D40). Recusar
    # ruidosamente é a única saída honesta; o arquivo antigo fica preservado.
    deps_tabela = pipeline.get("_deps_tabela")
    if deps_tabela is None and depends_on:
        raise ValueError(
            f"pipeline '{pname}': dependencia cadastrada ({depends_on}) mas a "
            "migration 067 esta ausente — DAG nao gerada; o arquivo anterior "
            "foi preservado")
    # CSV órfão (revisão adversarial da F3): depends_on preenchido mas ZERO
    # linhas na 067 — legado que a carga F descartou (predecessor fora de
    # etl_pipeline, ex.: DAG externa que o sensor antigo esperava). Gerar como
    # cron puro perderia a dependência EM SILÊNCIO no force_all; o sensor não
    # existe mais para honrá-la. Recusa ruidosa: o operador decide (cadastrar
    # a dependência na tabela ou limpar o campo).
    if deps_tabela is not None and not deps_tabela and depends_on:
        raise ValueError(
            f"pipeline '{pname}': depends_on legado ({depends_on}) sem "
            "correspondencia na tabela de dependencias (067) — DAG nao "
            "gerada; cadastre a dependencia ou limpe o campo; o arquivo "
            "anterior foi preservado")
    tem_dependencia = bool(deps_tabela)
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
    _DS_QUEUE_MAP = {"ALTA": "HighPriorityJobs", "CRITICA": "HighPriorityJobs",
                     "MEDIA": "MediumPriorityJobs", "BAIXA": "LowPriorityJobs"}
    ds_queue_val = _DS_QUEUE_MAP.get((pipeline.get("criticidade") or "").upper().strip())
    runbook_val  = (pipeline.get("runbook_md") or "").strip() or None

    cron, horarios_list, dias_horarios_mes = _build_cron(pipeline)
    # F3 — restrição de DIA do dependente vira constante gerada (§4.2): sem o
    # gatilho próprio, o cron não julga mais nada — o dia sobrevive no check.
    restricao_dia_val = (_derivar_restricao_dia(pipeline, dias_horarios_mes)
                         if tem_dependencia else None)
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
    _SPECIAL_NODES = ("decisao", "notificacao", "sql", "aguarde")
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
    # Espelho case-insensitive dos nomes: depends_on_jobs guarda TEXTO livre e o
    # banco (colação CI) aceita 'joba' apontando para 'JobA'. Como _varname NÃO
    # normaliza caixa, gerar as referências com a grafia da DEPENDÊNCIA
    # produziria t_end_joba — NameError no import do Airflow mesmo com a etapa
    # existindo. Por isso toda dep é resolvida para a grafia REAL da etapa.
    _job_real_ci = {_chave_ci(j["job_name"]): j["job_name"] for j in sorted_jobs}

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
        deps = []
        for d in str(raw).split(","):
            d = d.strip()
            if not d or _chave_ci(d) == _chave_ci(j["job_name"]):
                continue   # vazio ou auto-referência: ignorada, como sempre foi
            real = _job_real_ci.get(_chave_ci(d))
            if real is None:
                # Antes a dep fantasma era DESCARTADA em silêncio: a etapa
                # virava raiz e rodava sem esperar ninguém — ou, pior, uma
                # referência t_end_<dep> órfã só explodia como NameError no
                # import do Airflow, longe de quem cadastrou. Falhar AQUI
                # transforma isso num erro claro da geração, com o culpado.
                raise ValueError(
                    f"pipeline '{pname}': a etapa '{j['job_name']}' depende de "
                    f"'{d}', que não existe neste pipeline — corrija ou remova "
                    f"a dependência")
            deps.append(real)
        return deps

    # Valida TODAS as dependências já aqui, antes de qualquer fiação: _deps_of
    # levanta ValueError na primeira dep fantasma. O passo é redundante com os
    # usos abaixo hoje, mas garante o erro cedo e claro mesmo que a fiação seja
    # refatorada e deixe de percorrer todos os jobs.
    for _j in sorted_jobs:
        _deps_of(_j)

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

    # ── Nó Aguarde (migration 068) ─────────────────────────────────────────
    # Parse de aguarde_json (degrada se ausente/inválido → política default no
    # _wait_block). Ponto de encontro entre pernas paralelas: não roda nada,
    # não tem lineage. aguarde_nodes mapeia job_name → {politica}.
    aguarde_nodes = {}
    for j in sorted_jobs:
        if _alias(j) == "aguarde":
            raw = j.get("aguarde_json")
            try:
                aguarde_nodes[j["job_name"]] = _json.loads(raw) if raw else {}
            except (ValueError, TypeError):
                aguarde_nodes[j["job_name"]] = {}
    has_aguarde = bool(aguarde_nodes)

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
    import_lines.append("from datetime import timedelta")
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
        "",
        # ── F5: o portão da etapa em espera (docs/spec-operacao-nivel-etapa.md
        # §5 Bloco C). Este bloco e a chamada dentro do log_start são o ÚNICO
        # delta que a F5 introduz no fonte gerado — é exatamente o que
        # tests/test_dag_factory_espera.py remove para provar que o resto sai
        # byte-idêntico ao de antes (mitigação do §9: "sem linha de pausa na
        # tabela, o caminho é byte-idêntico ao atual").
        #
        # Import GUARDADO de propósito: se utils/espera.py não estiver no
        # servidor (deploy parcial), a DAG continua importando e o portão fica
        # desligado. Uma feature nova não pode derrubar 100% dos pipelines por
        # um arquivo que faltou subir.
        "# F5 — portao da etapa em espera (utils/espera.py). Import guardado:",
        "# sem os modulos no servidor a DAG importa igual, com o log_start de",
        "# sempre (PythonOperator) e o portao desligado.",
        "try:",
        "    from utils import espera as _espera",
        "    from utils.job_operators import LogStartOperator as _LogStart",
        "except Exception as _espera_err:  # noqa: BLE001",
        "    _espera = None",
        "    _LogStart = PythonOperator",
        "    print(f\"[ESPERA] utils.espera indisponivel ({_espera_err}) — portao desligado\")",
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
        # Jobs EXECUTÁVEIS (com trio de telemetria) — base do registro de SKIPPED
        # do flow_close; nós especiais (decisão/notificação/sql) ficam de fora.
        f'FLOW_JOBS     = {repr([j["job_name"] for j in sorted_jobs if _alias(j) not in _SPECIAL_NODES])}',
    ]
    if tem_dependencia:
        # Regras de dia como CONSTANTES geradas (mesmo padrão de
        # HORARIOS_ESPECIFICOS): editar agendamento/dependência exige regerar
        # o FILHO — dívida igual à do cron hoje (D30/F5 marca a DAG suja).
        consts_lines.append(f'RESTRICAO_DIA = {repr(restricao_dia_val)}')
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
        # Caso-borda herdado da correção B da 1ª execução (decisão-raiz com ramo
        # vazio): o publish é pulado e a linha da corrida ficaria presa em
        # EXECUTANDO para sempre. O fechamento entra SÓ quando o pipeline tem
        # decisão (única origem desse skip) — pipelines sem decisão não ganham
        # uma linha sequer a mais no código gerado.
        *([
            "    houve_falha = any(s in ('failed', 'upstream_failed') for s in estados.values())",
            "    if estados.get('publish_dataset') == 'skipped' and not houve_falha:",
            "        # Nenhuma falha e nada publicado: a decisao pulou todos os jobs",
            "        # — a corrida fecha como PULADO em vez de ficar presa em",
            "        # EXECUTANDO. Se houve falha, quem fecha a linha e o registro",
            "        # de falha; aqui nada e escrito.",
            "        _registrar_execucao('PULADO', context, motivo='decisao pulou todos os jobs')",
        ] if has_decision else []),
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
        # ⚠️ ORDEM: o portão vem ANTES da telemetria. Uma etapa segurada no
        # portão NÃO iniciou — gravar RUNNING antes de esperar faria a tela
        # mostrar como "executando" algo que está parado, e ainda estragaria a
        # duração. Enquanto espera, a etapa não tem linha: neutra, que é a
        # regra de honestidade do §3 da spec.
        "    # F5 — portao da etapa em espera: SEM pausa pedida (o caso normal)",
        "    # devolve None de imediato e o caminho abaixo e o de sempre.",
        "    if _espera is not None:",
        "        _espera.portao(hook, PIPELINE_NAME, job_name, execution_id)",
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
        "def _disparado_por(context):",
        "    # Origem do disparo: conf explicito (a F3 usara para nomear o pai) >",
        "    # prefixo do run_id (manual / dataset) > agenda.",
        "    dr = context.get('dag_run')",
        "    conf = (getattr(dr, 'conf', None) or {}) if dr is not None else {}",
        "    if conf.get('disparado_por'):",
        "        return str(conf['disparado_por'])[:200]",
        "    run_id = str(context.get('run_id') or '')",
        "    if run_id.startswith('manual'):",
        "        return 'manual'",
        "    if run_id.startswith('dataset_triggered'):",
        "        return 'dataset'",
        "    return 'agenda'",
        "",
        "def _origem_disparo(context):",
        "    \"\"\"Taxonomia EXPLICITA da origem do disparo (F3): agenda | manual |",
        "    dep | guardia | dataset. Substitui o sniffing por startswith('manual')",
        "    nas REGRAS do check_agenda — dep__* nao comeca com 'manual' e caia nas",
        "    regras de relogio (era PULADO em 100% dos disparos por evento).",
        "    Origem desconhecida degrada para 'manual' (acao humana): nunca julga",
        "    hora, mas continua julgando dia — degradacao visivel, nunca execucao",
        "    indevida.\"\"\"",
        "    run_id = str(context.get('run_id') or '')",
        "    if run_id.startswith('scheduled'):",
        "        return 'agenda'",
        "    if run_id.startswith('dep__'):",
        "        return 'dep'",
        "    if run_id.startswith('guardia__'):",
        "        return 'guardia'",
        "    if run_id.startswith('dataset_triggered'):",
        "        return 'dataset'",
        "    return 'manual'",
        "",
        "def _dia_operacional(context):",
        "    \"\"\"O dia de calendario em que a corrida foi ORDENADA na origem — e",
        "    contra ele que as regras de DIA sao julgadas. A data_referencia e o",
        "    ROTULO de juncao da corrida (a virada e artificio de juncao, nao",
        "    re-rotulacao do dia de negocio): julgar dia pela data_referencia",
        "    pulava a corrida certa quando a virada a carimbava no dia seguinte.",
        "",
        "    Precedencia: conf['dia_operacional'] valido > conf['data_referencia']",
        "    (aproximacao com log — cobre trigger manual que so passou a data) >",
        "    date do momento LOGICO em LOCAL_TZ. Nunca o relogio de parede: atraso",
        "    de fila que vira a meia-noite nao muda o dia julgado.\"\"\"",
        "    dr = context.get('dag_run')",
        "    conf = (getattr(dr, 'conf', None) or {}) if dr is not None else {}",
        "    from datetime import datetime as _dt",
        "    for chave in ('dia_operacional', 'data_referencia'):",
        "        bruto = conf.get(chave)",
        "        if not bruto:",
        "            continue",
        "        try:",
        "            valor = _dt.strptime(str(bruto).strip(), '%Y-%m-%d').date()",
        "        except (ValueError, TypeError):",
        "            print(f'[DEP] {chave} herdado invalido ({bruto!r}) — seguindo a cadeia de precedencia')",
        "            continue",
        "        if chave == 'data_referencia':",
        "            print('[DEP] dia_operacional ausente no conf — aproximando pela data_referencia herdada')",
        "        return valor",
        "    # Run MANUAL em DAG com cron: o data_interval_end e o ULTIMO TICK do",
        "    # cron (domingo 06:00 num daily disparado segunda 05:50; o dia 1 num",
        "    # mensal) — julgar dias uteis/calendario contra ele pularia um manual",
        "    # legitimo (regressao pega pela revisao adversarial da F3). O dia de",
        "    # um manual sem conf e HOJE: e o dia em que o operador ordenou.",
        "    if _origem_disparo(context) == 'manual':",
        "        return pendulum.now(LOCAL_TZ).date()",
        "    momento = context.get('data_interval_end') or context.get('logical_date')",
        "    if momento is not None:",
        "        momento = momento.in_timezone(LOCAL_TZ)",
        "    else:",
        "        momento = pendulum.now(LOCAL_TZ)",
        "    return momento.date()",
        "",
        "def _data_referencia(context):",
        "    \"\"\"A que dia de processamento (ODATE) esta corrida pertence.",
        "",
        "    1) Heranca: conf['data_referencia'] (carimbo do predecessor, ou de um",
        "       disparo manual com data) prevalece; valor invalido loga e recalcula,",
        "       nunca aborta.",
        "    2) Calculo: momento LOGICO do run (data_interval_end/logical_date em",
        "       LOCAL_TZ) deslocado pela hora de virada do pipeline (fallback:",
        "       config global; qualquer erro degrada para 00:00 = data do",
        "       calendario, o comportamento de sempre).",
        "    NUNCA o relogio de parede: atraso de fila ou rerun no dia seguinte nao",
        "    pode mudar a data da corrida.\"\"\"",
        "    dr = context.get('dag_run')",
        "    conf = (getattr(dr, 'conf', None) or {}) if dr is not None else {}",
        "    herdada = conf.get('data_referencia')",
        "    if herdada:",
        "        try:",
        "            from datetime import datetime as _dt",
        "            return _dt.strptime(str(herdada).strip(), '%Y-%m-%d').date()",
        "        except (ValueError, TypeError):",
        "            print(f'[EXEC] data_referencia herdada invalida ({herdada!r}) — recalculando')",
        "    momento = context.get('data_interval_end') or context.get('logical_date')",
        "    if momento is not None:",
        "        momento = momento.in_timezone(LOCAL_TZ)",
        "    else:",
        "        momento = pendulum.now(LOCAL_TZ)",
        "    virada = None",
        "    try:",
        "        row = MsSqlHook(mssql_conn_id=MSSQL_CONN_ID).get_first(",
        '            "SELECT COALESCE(CONVERT(VARCHAR(8), p.hora_virada, 108), c.config_value) "',
        '            "FROM dbo.etl_pipeline p "',
        '            "LEFT JOIN dbo.etl_app_config c ON c.config_key=\'dependencia_hora_virada\' "',
        '            "WHERE p.pipeline_name=%s",',
        "            parameters=(PIPELINE_NAME,),",
        "        )",
        "        if row:",
        "            virada = row[0]",
        "    except Exception as e:",
        "        print(f'[EXEC] hora de virada indisponivel ({e}) — usando 00:00')",
        "    from utils.data_referencia import calcular as _calcular_data_ref",
        "    return _calcular_data_ref(momento, virada)",
        "",
        "def _registrar_execucao(status, context, motivo=None):",
        "    \"\"\"Upsert em dbo.etl_pipeline_execucao pela chave COMPLETA:",
        "    (pipeline_name, data_referencia, execution_id = run_id do Airflow).",
        "",
        "    A linha NASCE com execution_id preenchido; reserva com NULL e proibida",
        "    por contrato — quem quiser criar linha antes do run (push/guardia, F3)",
        "    calcula o run_id primeiro, insere JA com ele e passa o mesmo valor ao",
        "    trigger. (etl_job_execution segue com o carimbo ts_nodash proprio do",
        "    nivel job — semanticas distintas, de proposito.)",
        "",
        "    Contrato de LEITURA (consumido na F3): liberacao e EXISTS(pipeline=P",
        "    AND data_referencia=D AND status='SUCESSO') — nunca 'linha mais",
        "    recente', nunca COALESCE(inicio, criado_em). PULADO/FALHA nao negam um",
        "    SUCESSO existente da mesma data; N execucoes no dia = N linhas.",
        "",
        "    Registro e observabilidade: NUNCA derruba a carga. Sem a migration 067",
        "    loga o aviso e retorna; qualquer excecao vira print, jamais propaga.\"\"\"",
        "    try:",
        "        run_id = str(context['run_id'])",
        "        hook = MsSqlHook(mssql_conn_id=MSSQL_CONN_ID)",
        "        obj = hook.get_first(\"SELECT OBJECT_ID('dbo.etl_pipeline_execucao','U')\")",
        "        if not obj or obj[0] is None:",
        "            print('[EXEC] migration 067 ausente — execucao nao registrada')",
        "            return",
        "        data_ref = _data_referencia(context)",
        "        origem = _disparado_por(context)",
        "        motivo = str(motivo)[:500] if motivo is not None else None",
        "        guarda_terminal = ''",
        "        if status == 'EXECUTANDO':",
        "            # Re-tentativa de run inteiro limpo reseta a janela da corrida.",
        "            upd_extra, ins_inicio, ins_fim = 'inicio=GETDATE(), fim=NULL', 'GETDATE()', 'NULL'",
        "        elif status == 'PULADO':",
        "            # Pulado nao comecou nem terminou: inicio e fim ficam NULL.",
        "            # GUARDA: PULADO nao rebaixa estado TERMINAL da mesma linha.",
        "            # Cenario real (revisao adversarial da F2): Clear de um run",
        "            # SUCESSO num dia em que uma regra de relogio bloqueia (fim de",
        "            # semana/blackout) reexecuta o check_agenda, que decide PULADO",
        "            # — sem a guarda, o unico SUCESSO da data viraria PULADO e o",
        "            # contrato EXISTS(SUCESSO) da F3 quebraria retroativamente.",
        "            upd_extra, ins_inicio, ins_fim = 'inicio=NULL, fim=NULL', 'NULL', 'NULL'",
        "            guarda_terminal = \" AND status NOT IN ('SUCESSO', 'FALHA')\"",
        "        else:  # SUCESSO / FALHA fecham a corrida sem mexer no inicio",
        "            upd_extra, ins_inicio, ins_fim = 'fim=GETDATE()', 'NULL', 'GETDATE()'",
        "        conn = hook.get_conn()",
        "        try:",
        "            cur = conn.cursor()",
        "            cur.execute(",
        "                'UPDATE dbo.etl_pipeline_execucao '",
        "                'SET status=%s, motivo=%s, disparado_por=%s, atualizado_em=GETDATE(), ' + upd_extra + ' '",
        "                'WHERE pipeline_name=%s AND data_referencia=%s AND execution_id=%s' + guarda_terminal,",
        "                (status, motivo, origem, PIPELINE_NAME, data_ref, run_id),",
        "            )",
        "            precisa_insert = (cur.rowcount == 0)",
        "            if precisa_insert and guarda_terminal:",
        "                # rowcount 0 com a guarda pode ser 'linha existe e e terminal'",
        "                # — nesse caso NAO insere (duplicaria a chave) nem rebaixa.",
        "                cur.execute(",
        "                    'SELECT 1 FROM dbo.etl_pipeline_execucao '",
        "                    'WHERE pipeline_name=%s AND data_referencia=%s AND execution_id=%s',",
        "                    (PIPELINE_NAME, data_ref, run_id),",
        "                )",
        "                if cur.fetchone():",
        "                    print(f'[EXEC] PULADO nao rebaixa estado terminal: {PIPELINE_NAME} run_id={run_id}')",
        "                    conn.commit()",
        "                    return",
        "            if precisa_insert:",
        "                cur.execute(",
        "                    'INSERT INTO dbo.etl_pipeline_execucao '",
        "                    '(pipeline_name, data_referencia, execution_id, status, inicio, fim, disparado_por, motivo) '",
        "                    'VALUES (%s, %s, %s, %s, ' + ins_inicio + ', ' + ins_fim + ', %s, %s)',",
        "                    (PIPELINE_NAME, data_ref, run_id, status, origem, motivo),",
        "                )",
        "            conn.commit()",
        "        finally:",
        "            conn.close()",
        "        print(f'[EXEC] {status} registrado: {PIPELINE_NAME} data_ref={data_ref} run_id={run_id} origem={origem}')",
        "    except Exception as e:",
        "        print(f'[EXEC] Aviso: execucao nao registrada (migration 067 aplicada?): {e}')",
        "",
        "def _registrar_falha(**context):",
        "    # Fecha a corrida como FALHA nomeando as tasks que falharam. Roda em",
        "    # qualquer falha do run — o registro e observabilidade, nao",
        "    # notificacao, por isso existe mesmo com os cards do Teams desligados.",
        "    falhas = []",
        "    dr = context.get('dag_run')",
        "    if dr is not None:",
        "        try:",
        "            falhas = sorted(ti.task_id for ti in dr.get_task_instances()",
        "                            if str(ti.state) == 'failed')",
        "        except Exception as e:",
        "            print(f'[EXEC] lista de tasks com falha indisponivel: {e}')",
        "    motivo = ('falha em: ' + ', '.join(falhas)) if falhas else 'falha na execucao'",
        "    _registrar_execucao('FALHA', context, motivo=motivo)",
        "",
        "def _registrar_sucesso(**context):",
        "    # Corpo do publish_dataset: grava SUCESSO e devolve — o Dataset segue",
        "    # publicado pelos outlets no sucesso da task, como sempre foi.",
        "    # Degradado por construcao: _registrar_execucao nunca levanta.",
        "    _registrar_execucao('SUCESSO', context)",
        "    # F3: avalia e dispara os dependentes DEPOIS do commit do SUCESSO,",
        "    # no MESMO callable — commit -> avaliar e sequencia, nao corrida (a",
        "    # condicao do candidato enxerga este pipeline ja gravado). Roda mesmo",
        "    # se o registro degradou: sem o SUCESSO no banco a condicao nao fecha",
        "    # e nada dispara — sem mentira. Nunca levanta (falha no disparo nao",
        "    # derruba o pai).",
        "    _disparar_dependentes(context)",
        "",
        "def _disparar_dependentes(context):",
        "    \"\"\"F3 — disparo imediato dos dependentes (docs/retomada-f3-desenho.md).",
        "",
        "    A lista de dependentes NAO fica no codigo gerado: e lida ao vivo da",
        "    tabela da migration 067 — cadastrar dependente novo vale no proximo",
        "    fim deste pipeline sem regenerar o pai (so o filho e regerado).",
        "",
        "    Por candidato: pre-filtro de dia (MESMO predicado puro que o filho",
        "    julga, com o MESMO dia operacional que vai no conf) -> condicao",
        "    EXISTS -> janela nao_iniciar_antes (relogio de parede: janela E de",
        "    relogio, por definicao) -> claim -> disparo com heranca de",
        "    data_referencia + dia_operacional -> devolucao se o disparo levantar.",
        "    Blackout NAO e pre-filtrado (e sobre o agora do FILHO, e a corrida",
        "    devida merece linha PULADO visivel). Erro em um candidato nao cancela",
        "    os demais e NENHUMA falha aqui derruba o pipeline pai — tudo logado",
        "    com [DEP], nunca silencio.\"\"\"",
        "    try:",
        "        from utils.dependencias import (",
        "            config_dependente as _dep_config,",
        "            datas_dos_predecessores as _dep_datas_pred,",
        "            datas_divergentes as _dep_datas_divergentes,",
        "            dependentes_de as _dep_dependentes,",
        "            detalhe_divergencia as _dep_detalhe_div,",
        "            devolver_reserva as _dep_devolver,",
        "            dia_permitido as _dep_dia_permitido,",
        "            gravar_evento as _dep_gravar_evento,",
        "            liberado as _dep_liberado,",
        "            montar_conf as _dep_montar_conf,",
        "            novo_run_id as _dep_novo_run_id,",
        "            ordenar_corrida as _dep_ordenar,",
        "            reservar_corrida as _dep_reservar,",
        "        )",
        "        hook = MsSqlHook(mssql_conn_id=MSSQL_CONN_ID)",
        "        obj = hook.get_first(\"SELECT OBJECT_ID('dbo.etl_pipeline_dependencia','U')\")",
        "        if not obj or obj[0] is None:",
        "            print('[DEP] migration 067 ausente — dependentes nao avaliados')",
        "            return",
        "        data_ref = _data_referencia(context)",
        "        dia_op = _dia_operacional(context)",
        "        conn = hook.get_conn()",
        "        try:",
        "            candidatos = _dep_dependentes(conn, PIPELINE_NAME)",
        "            if not candidatos:",
        "                return",
        "            print(f'[DEP] candidatos de {PIPELINE_NAME} em {data_ref}: {candidatos}')",
        "            for filho in candidatos:",
        "                try:",
        "                    cfg = _dep_config(conn, filho)",
        "                    if cfg is None:",
        "                        print(f'[DEP] {filho} sem cadastro em etl_pipeline — ignorado')",
        "                        continue",
        "                    ok_dia, motivo_dia = _dep_dia_permitido(cfg['regras_dia'], dia_op)",
        "                    if not ok_dia:",
        "                        print(f'[DEP] {filho} fora do dia em {dia_op}: {motivo_dia}')",
        "                        continue",
        "                    # F4 (spec-malha-data-unica): a MESMA trava que a",
        "                    # guardia ja tinha (Decisao 5). Com os predecessores",
        "                    # em datas diferentes, a condicao do filho nao fecha",
        "                    # numa data so — liberar aqui junta dados de dois",
        "                    # dias na mesma corrida (incidente Carga_Vida).",
        "                    try:",
        "                        from datetime import datetime as _dt_div",
        "                        _datas_pred = _dep_datas_pred(conn, filho, _dt_div.now())",
        "                    except Exception as _e_div:",
        "                        _datas_pred = {}",
        "                        print(f'[DEP] viradas de {filho} indisponiveis ({_e_div}) — seguindo')",
        "                    if _dep_datas_divergentes(_datas_pred):",
        "                        _det = _dep_detalhe_div(_datas_pred)",
        "                        print(f'[DEP] {filho} NAO disparado — {_det}')",
        "                        try:",
        "                            _dep_gravar_evento(conn, filho, data_ref,",
        "                                               'DATA_DIVERGENTE', _det)",
        "                            conn.commit()",
        "                        except Exception as _e_ev:",
        "                            print(f'[DEP] evento DATA_DIVERGENTE de {filho} nao gravado: {_e_ev}')",
        "                        continue",
        "                    lib, faltantes = _dep_liberado(conn, filho, data_ref)",
        "                    if not lib:",
        "                        print(f'[DEP] {filho} aguardando: ' + ', '.join(faltantes))",
        "                        continue",
        "                    run_id = _dep_novo_run_id('dep', data_ref, PIPELINE_NAME)",
        "                    janela = cfg.get('nao_iniciar_antes')",
        "                    if janela is not None and pendulum.now(LOCAL_TZ).time() < janela:",
        "                        criou = _dep_ordenar(conn, filho, data_ref, run_id, PIPELINE_NAME)",
        "                        conn.commit()",
        "                        print(f'[DEP] {filho} liberado antes da janela {janela} — '",
        "                              + ('corrida ordenada, aguardando' if criou else 'corrida ja existente'))",
        "                        continue",
        "                    ganho = _dep_reservar(conn, filho, data_ref, run_id, PIPELINE_NAME)",
        "                    conn.commit()",
        "                    if ganho is None:",
        "                        print(f'[DEP] {filho} ja tem corrida em {data_ref} — sem novo disparo')",
        "                        continue",
        "                    try:",
        "                        from airflow.api.client.local_client import Client",
        "                        Client(None, None).trigger_dag(",
        "                            dag_id=filho, run_id=ganho,",
        "                            conf=_dep_montar_conf(data_ref, dia_op, PIPELINE_NAME))",
        "                        print(f'[DEP] {filho} disparado: run_id={ganho} data_ref={data_ref}')",
        "                    except Exception as e:",
        "                        _dep_devolver(conn, filho, data_ref, ganho,",
        "                                      veio_de_adocao=(ganho != run_id))",
        "                        conn.commit()",
        "                        print(f'[DEP] disparo de {filho} falhou ({e}) — reserva devolvida')",
        "                except Exception as e:",
        "                    try:",
        "                        conn.rollback()",
        "                    except Exception:",
        "                        pass",
        "                    print(f'[DEP] avaliacao de {filho} falhou ({e}) — seguindo para o proximo')",
        "        finally:",
        "            conn.close()",
        "    except Exception as e:",
        "        print(f'[DEP] disparo de dependentes indisponivel ({e}) — o pipeline pai segue')",
        "",
        "def _check_agenda_regras(context):",
        "    \"\"\"Regras de agenda (F2/F3). Devolve (liberado, motivo) — quem",
        "    escreve o resultado da corrida e o wrapper check_agenda.",
        "",
        "    Regras de HORA valem so para disparo de agenda: evento e 'quando",
        "    liberou', nao 'que horas sao' — o piso de horario de um dependente e",
        "    nao_iniciar_antes, no pusher. Regras de DIA valem para TODA origem e",
        "    julgam o dia OPERACIONAL (nunca o relogio: atraso de fila que vira a",
        "    meia-noite nao pula a corrida). Blackout segue medindo o relogio DE",
        "    PROPOSITO: freeze operacional e sobre o agora, em qualquer origem.\"\"\"",
        "    _origem = _origem_disparo(context)",
        "    _dia_op = _dia_operacional(context)",
        "    # Horários específicos: o cron dispara na união minuto×hora;",
        "    # só executa se o horário agendado estiver na lista configurada.",
        "    if HORARIOS_ESPECIFICOS and _origem == 'agenda':",
        "        _die = context.get('data_interval_end') or context.get('logical_date')",
        "        if _die is not None:",
        "            _hhmm = _die.in_timezone(LOCAL_TZ).strftime('%H:%M')",
        "            if _hhmm not in HORARIOS_ESPECIFICOS:",
        "                print(f\"[AGENDA] {_hhmm} fora dos horarios configurados {HORARIOS_ESPECIFICOS} — execucao pulada.\")",
        "                return False, f'horario {_hhmm} fora dos horarios configurados'",
        "    # Dia + hora específico do mês: parte de HORA (só agenda). O DIA é",
        "    # julgado pelo dia operacional; para disparo por evento a parte de",
        "    # dia sobrevive na restrição de dia gerada, julgada adiante.",
        "    if DIAS_HORARIOS_MES and _origem == 'agenda':",
        "        _die = context.get('data_interval_end') or context.get('logical_date')",
        "        if _die is not None:",
        "            _hhmm = _die.in_timezone(LOCAL_TZ).strftime('%H:%M')",
        "            _dia = _dia_op.day",
        "            if _hhmm not in DIAS_HORARIOS_MES.get(_dia, []):",
        "                print(f\"[AGENDA] dia {_dia} as {_hhmm} fora da configuracao {DIAS_HORARIOS_MES} — execucao pulada.\")",
        "                return False, f'dia {_dia} as {_hhmm} fora da configuracao de dia e hora do mes'",
        *([
        "    # Restrição de DIA do agendamento (F3): sem gatilho próprio, o cron",
        "    # não julga mais nada — o dia sobrevive aqui, para TODA origem:",
        "    # fechamento mensal dia 5 roda SÓ dia 5, dispare quem disparar.",
        "    if RESTRICAO_DIA:",
        "        from utils.dependencias import dia_permitido as _dia_permitido",
        "        _lib_dia, _motivo_dia = _dia_permitido(RESTRICAO_DIA, _dia_op)",
        "        if not _lib_dia:",
        "            print(f\"[AGENDA] {_motivo_dia} — execucao pulada.\")",
        "            return False, _motivo_dia",
        ] if tem_dependencia else []),
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
        "            return False, f'blackout vigente: {row[0]}'",
        "    except Exception as e:",
        "        print(f\"[AGENDA] Aviso: verificacao de blackout falhou ({e}) — seguindo.\")",
        "    if SOMENTE_DIAS_UTEIS and _dia_op.weekday() >= 5:",
        "        print(\"[AGENDA] Fim de semana e pipeline e somente dias uteis — execucao pulada.\")",
        "        return False, 'fim de semana e pipeline somente dias uteis'",
        "    if CALENDARIO_NOME:",
        "        try:",
        "            from utils.dependencias import calendario_bloqueia as _cal_bloqueia",
        "            _conn_cal = hook.get_conn()",
        "            try:",
        "                _bloqueado = _cal_bloqueia(_conn_cal, CALENDARIO_NOME, _dia_op)",
        "            finally:",
        "                _conn_cal.close()",
        "            if _bloqueado:",
        "                print(f\"[AGENDA] Data bloqueada no calendario {CALENDARIO_NOME} — execucao pulada.\")",
        "                return False, f'data bloqueada no calendario {CALENDARIO_NOME}'",
        "        except Exception as e:",
        "            print(f\"[AGENDA] Aviso: verificacao de calendario falhou ({e}) — seguindo.\")",
        "    return True, None",
        "",
        "def check_agenda(**context):",
        "    \"\"\"Decide E registra: avalia as regras de agenda e grava o resultado da",
        "    corrida — EXECUTANDO quando libera, PULADO quando pula (sem inicio nem",
        "    fim: nao comecou nem terminou). Ponto UNICO de nascimento da linha em",
        "    etl_pipeline_execucao, ja com o run_id como chave. A decisao e",
        "    calculada ANTES do registro e devolvida independentemente dele;",
        "    False pula a execucao inteira.\"\"\"",
        "    ok, motivo = _check_agenda_regras(context)",
        "    _registrar_execucao('EXECUTANDO' if ok else 'PULADO', context, motivo=motivo)",
        "    return ok",
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
    # Registro de FALHA da corrida (F2) — INCONDICIONAL: o registro é
    # observabilidade, não notificação, então a task existe mesmo com
    # envia_msg_erro=0. Folha nova PARALELA ao publish_dataset com fiação
    # espelho do teams_error (ONE_FAILED só enxerga upstream DIRETO — pendurar
    # no publish deixaria a task cega, pois numa falha ele nem roda). Sem
    # falha ela fica SKIPPED, e folha skipped não altera o estado do DagRun:
    # quem carrega a falha segue sendo o publish_dataset (upstream_failed).
    teams_tasks.append("\n".join([
        't_reg_falha = PythonOperator(',
        '    task_id="registrar_falha",',
        '    python_callable=_registrar_falha,',
        '    trigger_rule=TriggerRule.ONE_FAILED,',
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
        elif _alias(j) == "aguarde":
            job_blocks.append(_wait_block(
                j, aguarde_nodes.get(j["job_name"], {}),
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
    ])

    # Fase 4/F3 — o publish mantém o outlet Dataset como PONTE: DAG antiga não
    # regenerada que consome o Dataset deste pipeline continua disparando.
    # F2: o publish deixa de ser EmptyOperator e vira PythonOperator com o
    # MESMO task_id, MESMA trigger rule (inclusive a condicional de decisão),
    # MESMOS outlets e MESMA posição — o callable grava SUCESSO (degradado,
    # nunca levanta) e o Dataset continua publicado no sucesso da task. Grafo
    # topologicamente idêntico; a folha que carrega a falha segue sendo ela.
    publish_block = "\n".join(filter(None, [
        't_publish_dataset = PythonOperator(',
        '    task_id="publish_dataset",',
        '    python_callable=_registrar_sucesso,',
        '    outlets=[Dataset(DATASET_URI)],',
        # Convergência final: tolera ramos pulados (≥1 t_end com sucesso).
        ('    trigger_rule=TriggerRule.NONE_FAILED_MIN_ONE_SUCCESS,'
         if (has_decision or has_notificacao or has_sql_node) else None),
        ')',
    ]))

    # F3 — o ExternalTaskSensor e o schedule-por-Dataset SAÍRAM do gerador
    # (D01): a espera por polling (timeout de 1h, exigência de mesmo horário)
    # deu lugar ao disparo por condição no publish do predecessor. O outlet
    # Dataset do publish PERMANECE como ponte para DAGs antigas não regeradas;
    # a âncora do grafo volta a ser sempre o t_check_agenda.
    imports_str = "\n".join(import_lines)

    dep_lines = []

    # Modo de dependência: EXPLÍCITO (algum job tem depends_on_jobs OU há um nó
    # de Decisão) ou ONDAS (execution_order). Opt-in por pipeline — pipelines
    # sem deps explícitas/decisão continuam exatamente como antes.
    # (_job_names/_deps_of já definidos acima, junto do parsing das decisões.)
    explicit_deps = (has_decision or has_notificacao or has_sql_node or has_aguarde
                     or any(_deps_of(j) for j in sorted_jobs))

    notif_task_refs = []   # t_notif_* a convergir no publish_dataset
    sql_task_refs = []     # t_sql_* a convergir no publish_dataset
    wait_task_refs = []    # t_wait_* a convergir no publish_dataset
    if explicit_deps:
        root_anchor = "t_check_agenda"
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
            if d in aguarde_nodes:
                return f"t_wait_{_varname(d)}"
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
            # Nó Aguarde: ponto de encontro, sem t_start/t_end. Liga ao upstream
            # (as pernas que ele espera) direto no t_wait_*; quem vem depois
            # dele o referencia via _end_ref. Converge no fechamento como a
            # notificação, para não ficar pendente quando é a ponta do fluxo.
            if _alias(j) == "aguarde":
                dep_lines.append(f"{up} >> t_wait_{n}")
                wait_task_refs.append(f"t_wait_{n}")
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
    # t_reg_falha (F2): fiação ESPELHO do teams_error — end_tasks + cada nó
    # especial, nunca o publish_dataset (numa falha ele nem roda e a task
    # ficaria cega). Incondicional: registra FALHA mesmo sem card de erro.
    dep_lines.append(f"{end_tasks_ref} >> t_reg_falha")
    # Nós de notificação (sem t_end) convergem no fechamento: rodam antes do
    # publish_dataset e dos cards de fim/erro, e toleram skip (ramo oposto).
    for nref in notif_task_refs:
        dep_lines.append(f"{nref} >> t_publish_dataset")
        if f_fim:
            dep_lines.append(f"{nref} >> t_teams_end")
        if f_err:
            dep_lines.append(f"{nref} >> t_teams_error")
        dep_lines.append(f"{nref} >> t_reg_falha")
    # Nós SQL (sem t_end) convergem no fechamento como a notificação — rodam
    # antes do publish_dataset/cards de fim/erro. (A Decisão a jusante já depende
    # do t_sql_* via _end_ref, então o valor publicado é lido antes do roteio.)
    for sref in sql_task_refs:
        dep_lines.append(f"{sref} >> t_publish_dataset")
        if f_fim:
            dep_lines.append(f"{sref} >> t_teams_end")
        if f_err:
            dep_lines.append(f"{sref} >> t_teams_error")
        dep_lines.append(f"{sref} >> t_reg_falha")
    # Nós Aguarde (sem t_end) convergem no fechamento como a notificação. Isso
    # é o que impede um Aguarde na ponta do fluxo de ficar pendurado fora do
    # grafo de fechamento — e é INDEPENDENTE das arestas de end_tasks, que
    # seguem intactas e continuam decidindo o estado do DagRun.
    for wref in wait_task_refs:
        dep_lines.append(f"{wref} >> t_publish_dataset")
        if f_fim:
            dep_lines.append(f"{wref} >> t_teams_end")
        if f_err:
            dep_lines.append(f"{wref} >> t_teams_error")
        dep_lines.append(f"{wref} >> t_reg_falha")
    # flow_close fecha DEPOIS de tudo (ends + nós especiais) e ANTES do card de
    # fim — assim o teams_end já enxerga as linhas SKIPPED que ele gravou.
    if has_decision:
        dep_lines.append(f"{end_tasks_ref} >> t_flow_close")
        for nref in notif_task_refs:
            dep_lines.append(f"{nref} >> t_flow_close")
        for sref in sql_task_refs:
            dep_lines.append(f"{sref} >> t_flow_close")
        for wref in wait_task_refs:
            dep_lines.append(f"{wref} >> t_flow_close")
        if f_fim:
            dep_lines.append("t_flow_close >> t_teams_end")

    with_parts = []
    with_parts.append(_ind(check_block))
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
        # Dependente (F3): DAG ativa e visível, sem gatilho próprio — quem a
        # dispara é o publish do predecessor (push), com a data herdada.
        schedule_line = "    schedule=None,  # dependente: o gatilho e o disparo dos predecessores"
    elif cron is None:
        # Sob demanda. `schedule=None` mantém a DAG ATIVA no Airflow, listada e
        # disparável pelo botão Executar — ela só não tem gatilho automático.
        schedule_line = "    schedule=None,  # sob demanda: só execução manual"
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


def _nomes_do_conf(bruto) -> list:
    """Normaliza `conf["pipelines"]` numa lista de nomes limpa e sem repetição.

    O conf vem da REST do Airflow: pode chegar como lista, como string única ou
    como qualquer coisa. Nada de confiar no formato — item não-texto é
    descartado e a ordem de chegada é preservada (é ela que o log mostra).
    A dedup é case-insensitive: dois nomes que só diferem na caixa são o MESMO
    pipeline para o banco (colação CI), e cobrá-los duas vezes no lote geraria
    um erro fantasma."""
    if bruto is None:
        return []
    itens = bruto if isinstance(bruto, (list, tuple, set)) else [bruto]
    vistos, out = set(), []
    for item in itens:
        if not isinstance(item, str):
            continue
        nome = item.strip()
        chave = _chave_ci(nome)
        if not nome or chave in vistos:
            continue
        vistos.add(chave)
        out.append(nome)
    return out


def gerar_dags(**context):
    import json as _json
    hook        = MsSqlHook(mssql_conn_id=MSSQL_CONN_ID)
    output_root = _get_output_root()
    conf        = context["dag_run"].conf or {}
    dag_run_id  = context["dag_run"].run_id

    force_all      = bool(conf.get("force_all", False))
    filter_project = (conf.get("filter_project") or "").strip()
    pipeline_name  = (conf.get("pipeline_name")  or "").strip()
    # Lista de alvos (republicação de malha): mesma semântica do pipeline_name,
    # para N pipelines — libera cada um para regeneração, cobra cada um no lote
    # e trata pendência de terceiro como AVISO. `escopo_rotulo` deixa o log da
    # factory dizer de onde veio ("Malha X") em vez de "apenas pendentes".
    alvos_nomes    = _nomes_do_conf(conf.get("pipelines"))
    escopo_rotulo  = (conf.get("escopo_rotulo") or "").strip()
    if pipeline_name and _chave_ci(pipeline_name) not in {
            _chave_ci(n) for n in alvos_nomes}:
        alvos_nomes.append(pipeline_name)

    if pipeline_name:
        escopo = f"Pipeline específico: {pipeline_name}"
    elif alvos_nomes:
        escopo = (escopo_rotulo or "Pipelines selecionados") + \
                 f" ({len(alvos_nomes)} pipeline(s))"
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

    if alvos_nomes:
        # Um UPDATE por alvo (em vez de IN com N marcadores): mantém o mesmo
        # SQL simples do caso de um pipeline e não depende de montar lista de
        # placeholders — o lote típico é de poucas dezenas.
        for _nome in alvos_nomes:
            cursor.execute(
                "UPDATE dbo.etl_pipeline SET dag_criada=0, updated_at=GETDATE() "
                "WHERE pipeline_name=%s",
                (_nome,),
            )
        msg = (f"Pipeline '{alvos_nomes[0]}' liberado para regeneração"
               if len(alvos_nomes) == 1 else
               f"{len(alvos_nomes)} pipelines liberados para regeneração: "
               + ", ".join(alvos_nomes))
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

    # Carimbo do LOTE no relógio do PRÓPRIO banco (F6): a limpeza da pendência
    # de publicação, ao concluir cada pipeline, só apaga carimbos <= este
    # instante — mudança de cadastro feita DURANTE a geração continua pendente
    # (mesma régua do reconciliador da API em services/dag_reconcile).
    momento_lote = None
    try:
        cursor.execute("SELECT GETDATE()")
        _row_momento = cursor.fetchone()
        momento_lote = _row_momento[0] if _row_momento else None
    except Exception as _mle:
        print(f"[FACTORY] carimbo do lote indisponivel — pendencia de publicacao "
              f"nao sera zerada nesta execucao: {_mle}")

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
        if alvos_nomes:
            # Run disparado para alvos específicos que NÃO entraram no lote:
            # inexistentes, inativos (a SP filtra active=1) ou corrida entre o
            # clique e a execução. SUCCESS aqui seria um verde mentiroso — o
            # operador pediu DAGs que não foram geradas (achado da revisão
            # adversarial desta correção). Vale para um alvo ou para a lista
            # inteira da republicação de malha: cada nome pedido é dito.
            msgs = [f"{nome}: pipeline solicitado não entrou na geração — "
                    "inexistente, inativo ou sem pendência no momento da execução"
                    for nome in alvos_nomes]
            for msg in msgs:
                print(f"[FACTORY] {msg}")
                steps_log.append({"tipo": "erro", "msg": msg})
            _log_upsert("FAILED", 0, len(msgs), steps_log, msgs)
            raise _ErrosPorPipeline("\n".join(msgs))
        msg = "Nenhum pipeline pendente encontrado — nada foi regenerado"
        print(f"[FACTORY] {msg}")
        steps_log.append({"tipo": "vazio", "msg": msg})
        _log_upsert("SUCCESS", 0, 0, steps_log, [])
        return

    pipelines = [dict(zip(pipeline_cols, row)) for row in pipelines_rows]
    jobs_all  = [dict(zip(jobs_cols, row))     for row in jobs_rows]

    # Chave CI também aqui: params vêm de etl_pipeline_job_param e as etapas de
    # etl_pipeline_job — tabelas DIFERENTES, mesmo padrão cross-table do
    # incidente da grafia. Com a chave crua, um job 'Pipe' com params gravados
    # como 'PIPE' geraria a DAG chamando a procedure SEM os parâmetros fixos,
    # em silêncio (achado da revisão adversarial desta correção).
    params_by_job = defaultdict(list)
    for r in [dict(zip(params_cols, row)) for row in params_rows]:
        params_by_job[(_chave_ci(r["pipeline_name"]), _chave_ci(r["job_name"]))].append(r)
    for j in jobs_all:
        j["params"] = params_by_job.get((_chave_ci(j["pipeline_name"]), _chave_ci(j["job_name"])), [])

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

    # Supplement: política do nó Aguarde (degrada se a coluna não existir —
    # migration 068). Sem ela, o _wait_block cai na política conservadora.
    try:
        cursor.execute(
            "SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='dbo' "
            "AND TABLE_NAME='etl_pipeline_job' AND COLUMN_NAME='aguarde_json'")
        if cursor.fetchone()[0]:
            cursor.execute(
                "SELECT pipeline_name, job_name, aguarde_json FROM dbo.etl_pipeline_job "
                "WHERE aguarde_json IS NOT NULL")
            _agmap = {(r[0], r[1]): r[2] for r in cursor.fetchall()}
            for j in jobs_all:
                j["aguarde_json"] = _agmap.get((j["pipeline_name"], j["job_name"]))
    except Exception as _age:
        print(f"[FACTORY] aguarde_json supplement ignorado: {_age}")

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
        # trigger_por_dependencia saiu do SELECT junto com o consumo (F3): o
        # modo Dataset não é mais gerado; a coluna morre na limpeza da F6.
        sched_cols = (
            ", calendario_nome, somente_dias_uteis"
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
        # depends_on (CSV legado) — fallback INFORMATIVO da F3: quando a tabela
        # da 067 não existe, é ele que denuncia "dependência cadastrada" e faz
        # a geração recusar ruidosamente em vez de regredir a cron em silêncio.
        cursor.execute(
            "SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME='etl_pipeline' "
            "AND COLUMN_NAME='depends_on'"
        )
        if cursor.fetchone()[0]:
            sched_cols += ", depends_on"
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

    # Supplement F3: dependências pela TABELA da migration 067 — contrato
    # None × {} (D36): None = tabela ausente, preserva o que houver (o CSV
    # vira só o denunciante da recusa); dict = a tabela é a verdade e o
    # VAZIO sobrescreve (dependência removida É remoção).
    _depmapa = _dependencias_da_tabela(cursor)
    if _depmapa is None:
        print("[FACTORY] etl_pipeline_dependencia indisponivel — dependencias "
              "pela tabela nao aplicadas (migration 067)")
    for p in pipelines:
        p["_deps_tabela"] = (None if _depmapa is None
                             else _depmapa.get(_chave_ci(p["pipeline_name"]), []))

    cursor.close(); conn.close()

    # Agrupamento com chave normalizada (_chave_ci): pipelines vêm de
    # etl_pipeline e etapas de etl_pipeline_job, e a colação CI do banco junta
    # 'SEQSSDVIDA6SINISTRO' com 'SeqSsdVida6Sinistro' — o dict Python, não.
    # Agrupar pelo nome cru fazia o pipeline "perder" as etapas quando a grafia
    # divergia (cadastro na tela × import .dsx) e o run falhava inteiro.
    jobs_by_pipeline = defaultdict(list)
    for j in jobs_all:
        jobs_by_pipeline[_chave_ci(j["pipeline_name"])].append(j)

    geradas, erros = [], []

    # Isolamento de pendências de terceiros: a sp_etl_pipelines_pendentes_criar
    # é GLOBAL — devolve TODOS os pendentes (dag_criada=0 AND active=1), não só
    # o pipeline do clique. Um pendente quebrado nunca sai desse conjunto (a
    # geração dele falha e o dag_criada segue 0), então qualquer defeito dele
    # reprovaria TODO run futuro — inclusive o clique num pipeline saudável.
    # Em run de pipeline específico, problema de TERCEIRO vira step 'aviso' e o
    # loop segue; problema do pipeline SOLICITADO — e qualquer problema em run
    # global/force_all — continua erro de primeira classe, preservando a
    # intenção da PR #234 (falha visível, nunca silêncio).
    # `pipelines_alvo` (lista no conf) generaliza o mesmo isolamento para um
    # CONJUNTO de alvos — é o que a republicação de malha usa: os membros são
    # os alvos, e um pendente quebrado de terceiro não pode pintar o run de
    # vermelho quando todos os membros foram gerados (visto ao vivo no dev).
    _alvos_ci = {_chave_ci(p) for p in (alvos_nomes or []) if p} or None
    _SUFIXO_TERCEIRO = " — pendência de outro pipeline, ignorada nesta execução"

    def _pendencia_de_terceiro(pname_do_loop):
        return _alvos_ci is not None and _chave_ci(pname_do_loop) not in _alvos_ci

    # O alvo entrou no lote? A SP filtra active=1 e dag_criada=0: entre o clique
    # e a execução o pipeline pode ter sido inativado/excluído, ou o conf de um
    # trigger manual pode ter vindo com nome errado. Sem esta checagem, o run
    # demoveria tudo a 'aviso' e fecharia SUCCESS com "0 geradas" — sem uma
    # linha sequer mencionando o pipeline pedido. Com vários alvos, a cobrança
    # é POR ALVO: um membro que não entrou é erro nomeado, e os outros seguem.
    if _alvos_ci is not None:
        _no_lote = {_chave_ci(p["pipeline_name"]) for p in pipelines}
        for _nome in (alvos_nomes or []):
            if _chave_ci(_nome) in _no_lote:
                continue
            msg = (f"{_nome}: pipeline solicitado não entrou na geração — "
                   "inexistente, inativo ou sem pendência no momento da execução")
            print(f"[FACTORY] {msg}")
            erros.append(msg)
            steps_log.append({"tipo": "erro", "msg": msg})

    for pipeline in pipelines:
        pname   = pipeline["pipeline_name"]
        project = pipeline["project_name"]
        domain  = pipeline["domain"]
        jobs    = jobs_by_pipeline.get(_chave_ci(pname), [])

        if not jobs:
            # Antes isto era só um print: o pipeline sumia da geração sem
            # aparecer na tela, e quem pediu a DAG ficava esperando um arquivo
            # que nunca viria. Agora é erro de primeira classe, com a causa —
            # exceto quando é pendência de OUTRO pipeline num run específico.
            msg = f"{pname}: pipeline sem nenhuma etapa — nada a gerar"
            print(f"[FACTORY] {msg}")
            if _pendencia_de_terceiro(pname):
                steps_log.append({"tipo": "aviso", "msg": msg + _SUFIXO_TERCEIRO})
            else:
                erros.append(msg)
                steps_log.append({"tipo": "erro", "msg": msg})
            continue

        dest_dir  = os.path.join(output_root, "generated", project, domain)
        dest_file = os.path.join(dest_dir, f"{pname}.py")

        # makedirs FORA de try derrubava a execução inteira (volume read-only,
        # permissão, disco cheio) e levava junto os pipelines seguintes.
        try:
            os.makedirs(dest_dir, exist_ok=True)
        except Exception as e:
            msg = f"{pname}: erro ao criar a pasta de destino {dest_dir} — {e}"
            if _pendencia_de_terceiro(pname):
                steps_log.append({"tipo": "aviso", "msg": msg + _SUFIXO_TERCEIRO})
            else:
                erros.append(msg)
                steps_log.append({"tipo": "erro", "msg": msg})
            continue

        try:
            source = _generate_dag_source(pipeline, jobs)
        except Exception as e:
            if _pendencia_de_terceiro(pname):
                steps_log.append({"tipo": "aviso",
                                  "msg": f"Erro ao gerar '{pname}': {e}" + _SUFIXO_TERCEIRO})
            else:
                erros.append(f"{pname}: erro ao gerar — {e}")
                steps_log.append({"tipo": "erro", "msg": f"Erro ao gerar '{pname}': {e}"})
            continue

        try:
            ast.parse(source)
        except SyntaxError as e:
            msg = f"{pname}: sintaxe invalida — linha {e.lineno}: {e.msg}"
            print(f"[FACTORY] SINTAXE INVALIDA {pname}: linha {e.lineno} — {e.msg}")
            if _pendencia_de_terceiro(pname):
                steps_log.append({"tipo": "aviso", "msg": msg + _SUFIXO_TERCEIRO})
            else:
                erros.append(msg)
            continue

        try:
            with open(dest_file, "w", encoding="utf-8") as f:
                f.write(source)
            msg = f"Arquivo da DAG gravado em {dest_file}"
            print(f"[FACTORY] OK -> {dest_file}")
            steps_log.append({"tipo": "gerada", "msg": msg})
        except Exception as e:
            if _pendencia_de_terceiro(pname):
                steps_log.append({"tipo": "aviso",
                                  "msg": f"Erro ao gravar arquivo de '{pname}': {e}" + _SUFIXO_TERCEIRO})
            else:
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
            # F6 — fecha o falso-pendente do force_all fora da API (pendência
            # registrada no desenho da F5 §7.2): uma regeneração administrativa
            # direto no Airflow deixava o badge "publicação pendente" mentindo
            # até a próxima publicação. SÓ nos runs SEM aguardar_ativacao: no
            # fluxo da UI quem zera é o RECONCILIADOR, e só quando a ativação
            # no Airflow é CONFIRMADA — import error e TIMEOUT deliberadamente
            # NÃO limpam ("falso-pendente é recuperável; pendência escondida
            # não é"). Zerar aqui nesses fluxos anularia o gating (achado da
            # revisão adversarial da F6). Zera só carimbos <= momento_lote.
            # Sem a migration 073, o batch nem compila (erro 207) e cai no
            # except — é o except que segura, não o IF (deferred name
            # resolution só vale para TABELA); comportamento final idêntico.
            if momento_lote is not None and not conf.get("aguardar_ativacao"):
                try:
                    hook.run(
                        "IF COL_LENGTH('dbo.etl_pipeline','dag_config_pendente_em') IS NOT NULL "
                        "UPDATE dbo.etl_pipeline SET dag_config_pendente_em = NULL "
                        "WHERE pipeline_name = %s AND dag_config_pendente_em <= %s",
                        parameters=(pname, momento_lote),
                    )
                except Exception as _dcpe:
                    print(f"[FACTORY] dag_config_pendente_em nao zerado para "
                          f"'{pname}' (migration 073?): {_dcpe}")
        except Exception as e:
            if _pendencia_de_terceiro(pname):
                steps_log.append({"tipo": "aviso",
                                  "msg": f"Erro ao atualizar cadastro de '{pname}': {e}" + _SUFIXO_TERCEIRO})
            else:
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
        raise _ErrosPorPipeline(f"{len(erros)} pipeline(s) com erro:\n" + "\n".join(erros))


class _ErrosPorPipeline(RuntimeError):
    """Erro de um ou mais pipelines DURANTE a geração — o log já foi fechado
    com a lista detalhada de cada um. Só existe para o wrapper da task não
    sobrescrever esse detalhe com uma mensagem genérica."""


def _escopo_de(conf):
    """Mesma régua de escopo do gerar_dags — usada quando ele morre antes de
    montar a própria descrição."""
    if (conf.get("pipeline_name") or "").strip():
        return f"Pipeline específico: {conf['pipeline_name'].strip()}"
    alvos = _nomes_do_conf(conf.get("pipelines"))
    if alvos:
        rotulo = (conf.get("escopo_rotulo") or "").strip() or "Pipelines selecionados"
        return f"{rotulo} ({len(alvos)} pipeline(s))"
    if conf.get("force_all") and (conf.get("filter_project") or "").strip():
        return f"Todos os pipelines do projeto {conf['filter_project'].strip()} (regeneração forçada)"
    if conf.get("force_all"):
        return "Todos os pipelines (regeneração forçada)"
    return "Apenas pipelines pendentes de criação"


def _fechar_log_em_falha(dag_run_id, escopo, pipeline_name, exc):
    """Fecha o registro da factory como FAILED quando a task morre no meio.

    Sem isso, QUALQUER exceção entre o log de RUNNING e o fechamento normal
    (conexão com o banco, a SP de pendentes, criação do diretório de saída…)
    deixa o registro em RUNNING para sempre. Do lado do operador o efeito é o
    pior possível: a tela não mostra causa nenhuma, o arquivo não aparece no
    servidor e o reconciliador só desiste 15 minutos depois, com um TIMEOUT que
    não explica nada.

    Best-effort de propósito — se nem isso conseguir gravar, o erro original é
    o que importa e segue subindo para o Airflow marcar a task como vermelha.
    """
    causa = f"{type(exc).__name__}: {exc}"
    detalhe = ("A geração foi interrompida por um erro antes de concluir — "
               "nenhuma DAG foi gravada nesta execução.")
    try:
        import json as _json
        payload = _json.dumps(
            {"steps": [{"tipo": "erro", "msg": detalhe}], "erros": [causa]},
            ensure_ascii=False)
        MsSqlHook(mssql_conn_id=MSSQL_CONN_ID).run(
            "MERGE dbo.etl_factory_log AS t "
            "USING (SELECT %s AS r) AS s ON t.dag_run_id = s.r "
            "WHEN MATCHED THEN UPDATE SET "
            "  estado='FAILED', finalizado_em=GETDATE(), erros=1, detalhes_json=%s "
            "WHEN NOT MATCHED THEN INSERT "
            "  (dag_run_id, estado, escopo, pipeline_name, geradas, erros, detalhes_json) "
            "  VALUES (%s, 'FAILED', %s, %s, 0, 1, %s);",
            parameters=(dag_run_id, payload,
                        dag_run_id, escopo, pipeline_name or None, payload),
        )
        print(f"[FACTORY] registro {dag_run_id} fechado como FAILED — {causa}")
    except Exception as _le:
        print(f"[FACTORY] AVISO: falha ao fechar o log da execução — {_le}")


def gerar_dags_task(**context):
    """python_callable da task — garante que o registro do log SEMPRE feche.

    Envolve gerar_dags sem tocar no corpo dele: o caminho feliz e os erros por
    pipeline continuam exatamente como eram; o que muda é que uma exceção
    inesperada deixa de virar um RUNNING órfão.
    """
    dag_run = context.get("dag_run")
    conf = (getattr(dag_run, "conf", None) or {})
    pname = (conf.get("pipeline_name") or "").strip()
    run_id = getattr(dag_run, "run_id", None)
    try:
        return gerar_dags(**context)
    except _ErrosPorPipeline:
        # O log já foi fechado com o detalhe de CADA pipeline que falhou —
        # reescrever aqui apagaria essa lista.
        raise
    except Exception as exc:
        _fechar_log_em_falha(run_id, _escopo_de(conf), pname, exc)
        raise


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
        python_callable=gerar_dags_task,
    )
