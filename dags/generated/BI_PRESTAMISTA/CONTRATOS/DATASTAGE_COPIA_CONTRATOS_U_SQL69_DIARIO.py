from airflow import DAG
from datetime import timedelta
from utils.datastage_operator import DataStageOperator
from airflow.operators.python import PythonOperator, ShortCircuitOperator
from airflow.operators.empty import EmptyOperator
from airflow.datasets import Dataset
from airflow.providers.microsoft.mssql.hooks.mssql import MsSqlHook
from airflow.utils.trigger_rule import TriggerRule
from airflow.utils.state import State
from airflow.models import Variable

import pendulum
import socket
import re
import json
import requests
# =========================
# Gerado automaticamente por etl_dag_factory
# Pipeline: DATASTAGE_COPIA_CONTRATOS_U_SQL69_DIARIO | Projeto: BI_PRESTAMISTA | Dominio: CONTRATOS
# =========================
DAG_ID        = "DATASTAGE_COPIA_CONTRATOS_U_SQL69_DIARIO"
SSH_CONN_ID   = "ssh_lnxprd021"
MSSQL_CONN_ID = "SQL14_DMDB41"
PROJECT_NAME  = "BI_PRESTAMISTA"
DOMAIN        = "CONTRATOS"
PIPELINE_NAME = "DATASTAGE_COPIA_CONTRATOS_U_SQL69_DIARIO"
BASE_LOG_DIR  = "/Projetos/BI_CVP/Logs/Airflow"
LOCAL_TZ      = "America/Sao_Paulo"
TEAMS_WEBHOOK_VAR = "TEAMS_WEBHOOK_URL_CVP"
DS_QUEUE      = 'MediumPriorityJobs'
RUNBOOK_MD    = None
CALENDARIO_NOME    = None
SOMENTE_DIAS_UTEIS = True
HORARIOS_ESPECIFICOS = None
DIAS_HORARIOS_MES = None
DATASET_URI   = "orq://pipeline/DATASTAGE_COPIA_CONTRATOS_U_SQL69_DIARIO"
default_args  = {"owner": "airflow", "depends_on_past": False, "retries": 1, "retry_delay": timedelta(seconds=300)}
JOBS          = ['SsdPrs_OdsContratosU_SQL69']
FLOW_JOBS     = ['SsdPrs_OdsContratosU_SQL69']

def _now_str():
    return pendulum.now(LOCAL_TZ).to_datetime_string()

def _build_log_file(job_name, execution_id):
    return f"{BASE_LOG_DIR}/{PROJECT_NAME}/{job_name}/{job_name}_{execution_id}.log"

def _extract_status_code(stdout):
    if not stdout: return None
    # O operador devolve JSON com o status_code da SEQUENCE no topo. NUNCA
    # usar o ultimo "status_code" do blob: child_jobs tambem tem esse campo,
    # entao um job filho ABORTED marcaria o pipeline como FAILED por engano.
    try:
        _obj = json.loads(stdout)
        if isinstance(_obj, dict) and _obj.get('status_code') is not None:
            return int(_obj['status_code'])
    except Exception:
        pass
    m = re.search(r"Job Status Code:\s*(-?\d+)", stdout)
    if m: return int(m.group(1))
    raw_m = re.findall(r"Status code\s*=\s*(-?\d+)", stdout)
    if raw_m: return int(raw_m[-1])
    return None

def _status_from_code(code, upstream_state):
    if code == 1:  return "SUCCESS"
    if code == 2:  return "WARNING"  # espelha o DataStage; nao falha o pipeline
    if code is not None: return "FAILED"
    if upstream_state == State.SUCCESS: return "SUCCESS"
    return "FAILED"

def _exec_telemetry(hook, execution_id, job_name, task_key, status,
                    start_time, end_time, duration_seconds, log_file, host=None):
    if host is None:
        host = socket.gethostname()
    sql = (
        "EXEC dbo.sp_etl_job_execution_log "
        "@execution_id=%s, @project=%s, @job_name=%s, @pipeline=%s, "
        "@host=%s, @start_time=%s, @end_time=%s, @duration_seconds=%s, "
        "@status=%s, @log_file=%s, @task_id=%s"
    )
    hook.run(sql, parameters=(
        execution_id, PROJECT_NAME, job_name, PIPELINE_NAME,
        host, start_time or "", end_time or "",
        duration_seconds, status, log_file, task_key,
    ))

def _update_status_code(hook, execution_id, job_name, task_key, status_code):
    hook.run(
        "UPDATE dbo.etl_job_execution SET status_code=%s, updated_at=GETDATE() "
        "WHERE execution_id=%s AND pipeline=%s AND job_name=%s AND task_id=%s",
        parameters=(status_code, execution_id, PIPELINE_NAME, job_name, task_key),
    )

def _teams_post_card(title, facts, status='INFO', subtitle=None, button=None):
    try:
        webhook_url = Variable.get(TEAMS_WEBHOOK_VAR)
    except Exception:
        print(f"[TEAMS] Variable '{TEAMS_WEBHOOK_VAR}' nao encontrada.")
        return
    icon = {"SUCCESS": "🟢", "WARNING": "🟡", "FAILED": "🔴", "INFO": "🔵"}.get(status, "⚪")
    color = {"SUCCESS": "Good", "WARNING": "Warning", "FAILED": "Attention", "INFO": "Accent"}.get(status, "Default")
    body = [
        {"type": "TextBlock", "text": f"{icon} {title}", "size": "Large", "weight": "Bolder", "wrap": True, "color": color},
    ]
    if subtitle:
        body.append({"type": "TextBlock", "text": subtitle, "wrap": True, "spacing": "None", "isSubtle": True})
    if facts:
        body.append({"type": "FactSet", "spacing": "Medium", "facts": facts})
    content = {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard", "version": "1.4",
        "body": body,
    }
    # Botao de link opcional (Action.OpenUrl) — so quando titulo e url presentes.
    if button and button.get('url'):
        content["actions"] = [{"type": "Action.OpenUrl",
                               "title": button.get('titulo') or 'Abrir',
                               "url": button.get('url')}]
    payload = {
        "type": "message",
        "attachments": [{
            "contentType": "application/vnd.microsoft.card.adaptive",
            "content": content,
        }],
    }
    try:
        resp = requests.post(webhook_url, json=payload, timeout=15)
        print(f"[TEAMS] status={resp.status_code}")
    except Exception as e:
        print(f"[TEAMS] Falha: {e}")

def _fact(title, value):
    return {"title": title, "value": str(value) if value is not None else "—"}

def _fmt_duration(seconds):
    if not seconds: return '—'
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h: return f'{h}h {m}min {sec}s'
    if m: return f'{m}min {sec}s'
    return f'{sec}s'

def _notif_resolve_linhas(up_jobs, execution_id, context):
    # {linhas} = rows_out do(s) job(s) a montante. 1º tenta o XCom do run
    # (DataStageOperator empurra 'rows_out' no JSON); fallback: etl_ds_job_log
    # da execução atual. Degrada para '' se nada disponível.
    total = 0; achou = False
    ti = context.get('ti') if context else None
    for jn in (up_jobs or []):
        val = None
        if ti is not None:
            try:
                _x = ti.xcom_pull(task_ids=jn)
                if _x:
                    _o = json.loads(_x) if isinstance(_x, str) else _x
                    if isinstance(_o, dict) and _o.get('rows_out') is not None:
                        val = int(_o['rows_out'])
            except Exception:
                val = None
        if val is None and execution_id:
            try:
                hook = MsSqlHook(mssql_conn_id=MSSQL_CONN_ID)
                _r = hook.get_first(
                    "SELECT TOP 1 rows_out FROM dbo.etl_ds_job_log "
                    "WHERE execution_id=%s AND pipeline_name=%s AND job_name=%s "
                    "ORDER BY COALESCE(updated_at, last_polled_at) DESC",
                    parameters=(execution_id, PIPELINE_NAME, jn),
                )
                if _r and _r[0] is not None:
                    val = int(_r[0])
            except Exception as _e:
                print(f'[NOTIF] rows_out de {jn} indisponivel: {_e}')
                val = None
        if val is not None:
            total += val; achou = True
    return str(total) if achou else ''

def _notif_status_geral(execution_id):
    # Status agregado do pipeline na execução (mesma regra do teams_end).
    try:
        hook = MsSqlHook(mssql_conn_id=MSSQL_CONN_ID)
        row = hook.get_first(
            "SELECT CASE WHEN SUM(CASE WHEN status='FAILED' THEN 1 ELSE 0 END)>0 THEN 'FAILED' "
            "     WHEN SUM(CASE WHEN status='WARNING' THEN 1 ELSE 0 END)>0 THEN 'WARNING' "
            "     WHEN SUM(CASE WHEN status='SUCCESS' THEN 1 ELSE 0 END)>0 THEN 'SUCCESS' "
            "     WHEN SUM(CASE WHEN status='SKIPPED' THEN 1 ELSE 0 END)>0 THEN 'SKIPPED' "
            "     ELSE 'INFO' END "
            "FROM dbo.etl_job_execution WHERE execution_id=%s AND pipeline=%s",
            parameters=(execution_id, PIPELINE_NAME),
        )
        return row[0] if row and row[0] else 'INFO'
    except Exception:
        return 'INFO'

def _notif_interpola(texto, mapa):
    # Substitui placeholders {pipeline} {job} {linhas} {status} {data} de forma
    # tolerante (placeholder desconhecido fica intacto — não quebra).
    out = texto or ''
    for k, v in mapa.items():
        out = out.replace('{' + k + '}', str(v) if v is not None else '')
    return out

def _resolve_e_envia_notificacao(job, grupo_id, template_id, mensagem, up_jobs, execution_id, context):
    hook = MsSqlHook(mssql_conn_id=MSSQL_CONN_ID)
    # 1) Webhook do grupo (canal Teams). Sem webhook → cai no Variable padrão.
    webhook = None; titulo = None
    try:
        if grupo_id is not None:
            g = hook.get_first(
                "SELECT webhook_url FROM dbo.etl_msg_grupo WHERE id=%s AND ativo=1",
                parameters=(grupo_id,),
            )
            if g and g[0]:
                webhook = g[0]
    except Exception as _e:
        print(f'[NOTIF] grupo {grupo_id} indisponivel: {_e}')
    # 2) Texto: mensagem inline; se vazia, o corpo do template. O TEMPLATE
    # tambem define facts(JSON)/cor/botao do card estruturado (migration 050).
    corpo = (mensagem or '').strip()
    tpl_facts_raw = None; tpl_cor = None; tpl_btn_txt = None; tpl_btn_url = None
    if template_id is not None:
        t = None
        try:
            t = hook.get_first(
                "SELECT titulo, corpo, facts, cor, botao_texto, botao_url "
                "FROM dbo.etl_msg_template WHERE id=%s AND ativo=1",
                parameters=(template_id,),
            )
            if t:
                titulo = t[0]
                if not corpo: corpo = t[1] or ''
                tpl_facts_raw = t[2]; tpl_cor = t[3]
                tpl_btn_txt = t[4]; tpl_btn_url = t[5]
        except Exception as _e:
            # Colunas do card podem nao existir (sem 050) — fallback ao SELECT antigo.
            print(f'[NOTIF] card cols indisponiveis p/ template {template_id}: {_e}')
            try:
                t = hook.get_first(
                    "SELECT titulo, corpo FROM dbo.etl_msg_template WHERE id=%s AND ativo=1",
                    parameters=(template_id,),
                )
                if t:
                    titulo = t[0]
                    if not corpo: corpo = t[1] or ''
            except Exception as _e2:
                print(f'[NOTIF] template {template_id} indisponivel: {_e2}')
    # 3) Placeholders.
    linhas = _notif_resolve_linhas(up_jobs, execution_id, context)
    status_geral = _notif_status_geral(execution_id)
    mapa = {
        'pipeline': PIPELINE_NAME, 'job': job, 'linhas': linhas,
        'status': status_geral, 'data': _now_str(),
    }
    corpo_final  = _notif_interpola(corpo, mapa)
    titulo_final = _notif_interpola(titulo or 'Notificação', mapa)
    facts = [
        _fact('Pipeline', PIPELINE_NAME),
        _fact('Execução', execution_id),
    ]
    if linhas != '':
        facts.append(_fact('Linhas', linhas))
    # facts do template (JSON array de {label,value}; value interpolado).
    # Tolerante: JSON invalido/None → ignora o extra, nao quebra o envio.
    if tpl_facts_raw:
        try:
            _arr = json.loads(tpl_facts_raw) if isinstance(tpl_facts_raw, str) else tpl_facts_raw
            if isinstance(_arr, list):
                for _f in _arr:
                    if isinstance(_f, dict) and (_f.get('label') or ''):
                        facts.append(_fact(_f.get('label'), _notif_interpola(str(_f.get('value') or ''), mapa)))
        except Exception as _e:
            print(f'[NOTIF] facts do template invalidos: {_e}')
    # cor do template → status do card; vazio/'auto' usa o status agregado.
    _cor_map = {'error': 'FAILED', 'warning': 'WARNING', 'success': 'SUCCESS', 'info': 'INFO'}
    card_status = _cor_map.get((tpl_cor or '').strip().lower(), status_geral)
    # botao de link opcional (texto/url interpolados); url vazia → sem botao.
    btn_url_final = _notif_interpola(tpl_btn_url or '', mapa).strip()
    btn_txt_final = _notif_interpola(tpl_btn_txt or '', mapa).strip()
    button = {'titulo': btn_txt_final, 'url': btn_url_final} if btn_url_final else None
    print(f'[NOTIF] {job}: grupo={grupo_id} template={template_id} linhas={linhas!r} status={card_status} botao={bool(button)}')
    # Webhook específico do grupo: posta direto; senão usa _teams_post_card
    # (Variable padrão do projeto). Mantém o mesmo card adaptativo (mesmos
    # facts/cor/botao nos dois caminhos).
    if webhook:
        try:
            _icon = {"SUCCESS": "🟢", "WARNING": "🟡", "FAILED": "🔴", "INFO": "🔵"}.get(card_status, "⚪")
            _color = {"SUCCESS": "Good", "WARNING": "Warning", "FAILED": "Attention", "INFO": "Accent"}.get(card_status, "Default")
            _content = {"$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                        "type": "AdaptiveCard", "version": "1.4",
                        "body": [
                            {"type": "TextBlock", "text": f"{_icon} {titulo_final}", "size": "Large", "weight": "Bolder", "wrap": True, "color": _color},
                            {"type": "TextBlock", "text": corpo_final, "wrap": True},
                            {"type": "FactSet", "facts": facts},
                        ]}
            if button and button.get('url'):
                _content["actions"] = [{"type": "Action.OpenUrl",
                                        "title": button.get('titulo') or 'Abrir',
                                        "url": button.get('url')}]
            payload = {"type": "message", "attachments": [{
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": _content}]}
            resp = requests.post(webhook, json=payload, timeout=15)
            print(f'[NOTIF] webhook do grupo status={resp.status_code}')
        except Exception as _e:
            print(f'[NOTIF] falha ao postar no webhook do grupo: {_e}')
    else:
        _teams_post_card(title=titulo_final, subtitle=corpo_final, facts=facts, status=card_status, button=button)

def _resolve_e_roda_sql(sql, conn_id, database, context, on_error='nulo'):
    # Nó SQL: roda o SELECT e devolve o valor ESCALAR (1a coluna da 1a linha),
    # que vira o XCom default da task (a Decisao 'valor_sql' a jusante o le).
    # Conexao resolvida pelo ORQUESTRA (dbo.etl_conexao primeiro, Airflow
    # como fallback) — antes o MsSqlHook ignorava as conexoes nativas.
    # on_error='falhar' -> erro LEVANTA (task falha alto, fail-fast do run);
    # 'nulo'/ausente (legado) -> log + None (nao derruba a DAG).
    _falha_alto = str(on_error or '').strip().lower() == 'falhar'
    if not sql:
        if _falha_alto:
            raise ValueError('[SQL NODE] sql vazio — on_error=falhar')
        print('[SQL NODE] sql vazio — valor None.')
        return None
    try:
        from utils.conn_resolver import abrir_conexao_mssql
        _cid = (conn_id or '').strip() or MSSQL_CONN_ID
        _db = (database or '').strip() or None
        _conn = abrir_conexao_mssql(_cid, database=_db, autocommit=True,
                                    appname='orquestra-sql-node')
        try:
            _cur = _conn.cursor()
            _cur.execute(sql)
            row = _cur.fetchone()
        finally:
            _conn.close()
        val = row[0] if row else None
        print('[SQL NODE] conn=' + _cid + ' database=' + repr(_db) + ' -> valor=' + repr(val))
        return val
    except Exception as _e:
        if _falha_alto:
            raise
        print('[SQL NODE] falha ao rodar SELECT (' + str(_e) + ') — valor None.')
        return None

def _flow_close(**context):
    # SKIPPED de 1a classe: registra na telemetria os jobs PULADOS POR
    # DECISAO nesta execucao (state='skipped'). Job que nao rodou por
    # FALHA a montante (upstream_failed) segue SEM linha — semantica
    # diferente (precisa reprocessar), nao pode virar SKIPPED.
    execution_id = context['ts_nodash']
    dr = context.get('dag_run')
    if dr is None:
        return
    try:
        estados = {ti.task_id: str(ti.state) for ti in dr.get_task_instances()}
    except Exception as e:
        print(f'[FLOW CLOSE] get_task_instances falhou ({e}) — sem registro de SKIPPED.')
        return
    hook = MsSqlHook(mssql_conn_id=MSSQL_CONN_ID)
    agora = _now_str()
    for job in FLOW_JOBS:
        if estados.get(job) != 'skipped':
            continue
        try:
            _exec_telemetry(hook, execution_id, job, job, 'SKIPPED', agora, agora, 0, None)
            print(f'[FLOW CLOSE] SKIPPED registrado para {job}.')
        except Exception as e:
            print(f'[FLOW CLOSE] falha ao registrar SKIPPED de {job}: {e}')

def teams_start(**context):
    execution_id = context['ts_nodash']
    _teams_post_card(
        title="Execução iniciada",
        subtitle=f"O pipeline {PIPELINE_NAME} foi iniciado e está em processamento.",
        facts=[
            _fact("Pipeline",      PIPELINE_NAME),
            _fact("Domínio",       DOMAIN),
            _fact("Projeto",       PROJECT_NAME),
            _fact("Execution ID",  execution_id),
            _fact("Início",        _now_str()),
        ],
        status='INFO',
    )

def teams_end(**context):
    execution_id = context['ts_nodash']
    hook = MsSqlHook(mssql_conn_id=MSSQL_CONN_ID)
    row = hook.get_first(
        "SELECT pipeline, MIN(start_time), MAX(end_time), "
        "DATEDIFF(SECOND, MIN(start_time), MAX(COALESCE(end_time, GETDATE()))), "
        "CASE WHEN SUM(CASE WHEN status='FAILED' THEN 1 ELSE 0 END)>0 THEN 'FAILED' "
        "     WHEN SUM(CASE WHEN status='WARNING' THEN 1 ELSE 0 END)>0 THEN 'WARNING' "
        "     WHEN SUM(CASE WHEN status='SUCCESS' THEN 1 ELSE 0 END)>0 THEN 'SUCCESS' "
        "     WHEN SUM(CASE WHEN status='SKIPPED' THEN 1 ELSE 0 END)>0 THEN 'SKIPPED' "
        "     ELSE 'FAILED' END "
        "FROM dbo.etl_job_execution WHERE execution_id=%s AND pipeline=%s GROUP BY pipeline",
        parameters=(execution_id, PIPELINE_NAME),
    )
    if not row:
        _teams_post_card(
            title="Execução finalizada — sem dados",
            subtitle=f"O pipeline {PIPELINE_NAME} foi concluído, mas não foram encontrados registros de execução.",
            facts=[_fact("Pipeline", PIPELINE_NAME), _fact("Execution ID", execution_id)],
            status='WARNING',
        )
        return
    pipeline, inicio, fim, dur_seg, status_geral = row
    titles = {"SUCCESS": "Execução concluída com sucesso", "WARNING": "Execução concluída com avisos", "FAILED": "Execução finalizada com falha", "SKIPPED": "Execução pulada"}
    subtitles = {
        "SUCCESS": f"O pipeline {pipeline} foi executado e finalizado sem erros.",
        "WARNING": f"O pipeline {pipeline} foi concluído, mas registrou avisos durante a execução.",
        "FAILED":  f"O pipeline {pipeline} foi encerrado com falha. Verifique os jobs com erro.",
        "SKIPPED": f"Todos os jobs do pipeline {pipeline} foram pulados pela decisão nesta execução.",
    }
    _teams_post_card(
        title=titles.get(status_geral, 'Execução finalizada'),
        subtitle=subtitles.get(status_geral),
        facts=[
            _fact("Pipeline",      pipeline),
            _fact("Domínio",       DOMAIN),
            _fact("Projeto",       PROJECT_NAME),
            _fact("Execution ID",  execution_id),
            _fact("Início",        inicio.strftime('%d/%m/%Y %H:%M') if inicio else '—'),
            _fact("Fim",           fim.strftime('%d/%m/%Y %H:%M') if fim else '—'),
            _fact("Duração",       _fmt_duration(dur_seg)),
        ],
        status=status_geral,
    )

def teams_error(**context):
    execution_id = context['ts_nodash']
    hook = MsSqlHook(mssql_conn_id=MSSQL_CONN_ID)
    # Resumo do pipeline (mesma query do teams_end)
    row = hook.get_first(
        "SELECT pipeline, MIN(start_time), MAX(end_time), "
        "DATEDIFF(SECOND, MIN(start_time), MAX(COALESCE(end_time, GETDATE()))) "
        "FROM dbo.etl_job_execution WHERE execution_id=%s AND pipeline=%s GROUP BY pipeline",
        parameters=(execution_id, PIPELINE_NAME),
    )
    pipeline_nm = row[0] if row else PIPELINE_NAME
    inicio      = row[1] if row else None
    fim         = row[2] if row else None
    dur_seg     = row[3] if row else 0
    # Jobs com falha — detalhado
    try:
        failed = hook.get_records(
            "SELECT job_name, start_time, end_time, COALESCE(duration_seconds,0), log_file "
            "FROM dbo.etl_job_execution "
            "WHERE execution_id=%s AND pipeline=%s AND status='FAILED' "
            "ORDER BY start_time",
            parameters=(execution_id, PIPELINE_NAME),
        )
    except Exception:
        failed = []
    facts = [
        _fact("Pipeline",      pipeline_nm),
        _fact("Domínio",       DOMAIN),
        _fact("Projeto",       PROJECT_NAME),
        _fact("Execution ID",  execution_id),
        _fact("Início",        inicio.strftime('%d/%m/%Y %H:%M') if inicio else '—'),
        _fact("Fim",           fim.strftime('%d/%m/%Y %H:%M') if fim else '—'),
        _fact("Duração total", _fmt_duration(dur_seg)),
    ]
    if failed:
        facts.append(_fact("─────────────", "Jobs com falha"))
        for jname, jstart, jend, jdur, jlog in failed:
            facts.append(_fact("Job",     jname))
            facts.append(_fact("  Início",  jstart.strftime('%d/%m/%Y %H:%M') if jstart else '—'))
            facts.append(_fact("  Fim",     jend.strftime('%d/%m/%Y %H:%M') if jend else '—'))
            facts.append(_fact("  Duração", _fmt_duration(jdur)))
    else:
        facts.append(_fact("Job com falha", "Não identificado"))
    if RUNBOOK_MD:
        facts.append(_fact("📖 Runbook", RUNBOOK_MD[:400] + ("…" if len(RUNBOOK_MD) > 400 else "")))
    _teams_post_card(
        title="Falha na execução",
        subtitle=f"O pipeline {pipeline_nm} foi interrompido por falha em um ou mais jobs. Verifique os detalhes abaixo.",
        facts=facts,
        status='FAILED',
    )

def log_start(job_name, task_key, **context):
    hook = MsSqlHook(mssql_conn_id=MSSQL_CONN_ID)
    execution_id = context['ts_nodash']
    _exec_telemetry(hook, execution_id, job_name, task_key, 'RUNNING',
                    _now_str(), '', 0, _build_log_file(job_name, execution_id))

def _update_last_execution():
    hook = MsSqlHook(mssql_conn_id=MSSQL_CONN_ID)
    hook.run(
        "UPDATE dbo.etl_pipeline SET last_execution=GETDATE(), updated_at=GETDATE() "
        "WHERE pipeline_name=%s",
        parameters=(PIPELINE_NAME,),
    )

def log_end(job_name, task_key, upstream_task_id, **context):
    hook = MsSqlHook(mssql_conn_id=MSSQL_CONN_ID)
    execution_id = context['ts_nodash']
    end_time = _now_str()
    job_ti = context['dag_run'].get_task_instance(upstream_task_id)
    upstream_state = job_ti.state if job_ti else None
    ti = context['ti']
    stdout = ti.xcom_pull(task_ids=upstream_task_id)
    status_code = _extract_status_code(str(stdout) if stdout else '')
    final_status = _status_from_code(status_code, upstream_state)
    duration_seconds = 0
    if job_ti and job_ti.start_date and job_ti.end_date:
        duration_seconds = int((job_ti.end_date - job_ti.start_date).total_seconds())
    _exec_telemetry(hook, execution_id, job_name, task_key, final_status,
                    '', end_time, duration_seconds, _build_log_file(job_name, execution_id))
    _update_status_code(hook, execution_id, job_name, task_key, status_code)
    try:
        _update_last_execution()
    except Exception as _ule_exc:
        print(f'[log_end] Aviso: nao foi possivel atualizar last_execution — {_ule_exc}')
    if final_status in ('FAILED', 'DESCONHECIDO'):
        raise RuntimeError(
            f"Job '{job_name}' finalizou com status {final_status} — "
            "execucao interrompida. Corrija o erro antes de reprocessar."
        )

def check_agenda(**context):
    """Fase 4 — blackout/freeze, dias úteis e calendário de feriados.
    Retorna False (ShortCircuit) para pular a execução inteira."""
    # Horários específicos: o cron dispara na união minuto×hora;
    # só executa se o horário agendado estiver na lista configurada.
    if HORARIOS_ESPECIFICOS and not str(context.get('run_id', '')).startswith('manual'):
        _die = context.get('data_interval_end') or context.get('logical_date')
        if _die is not None:
            _hhmm = _die.in_timezone(LOCAL_TZ).strftime('%H:%M')
            if _hhmm not in HORARIOS_ESPECIFICOS:
                print(f"[AGENDA] {_hhmm} fora dos horarios configurados {HORARIOS_ESPECIFICOS} — execucao pulada.")
                return False
    # Dia + hora específico: o cron dispara na união dia×minuto×hora;
    # só executa se (dia, horario) atual estiver configurado para aquele dia.
    if DIAS_HORARIOS_MES and not str(context.get('run_id', '')).startswith('manual'):
        _die = context.get('data_interval_end') or context.get('logical_date')
        if _die is not None:
            _local = _die.in_timezone(LOCAL_TZ)
            _dia = _local.day
            _hhmm = _local.strftime('%H:%M')
            if _hhmm not in DIAS_HORARIOS_MES.get(_dia, []):
                print(f"[AGENDA] dia {_dia} as {_hhmm} fora da configuracao {DIAS_HORARIOS_MES} — execucao pulada.")
                return False
    hook = MsSqlHook(mssql_conn_id=MSSQL_CONN_ID)
    try:
        row = hook.get_first(
            "SELECT TOP 1 motivo FROM dbo.etl_blackout "
            "WHERE ativo=1 AND GETDATE() BETWEEN inicio AND fim "
            "AND (escopo IS NULL OR escopo=%s OR escopo=%s)",
            parameters=(PROJECT_NAME, PIPELINE_NAME),
        )
        if row:
            print(f"[AGENDA] Blackout vigente: {row[0]} — execucao pulada.")
            return False
    except Exception as e:
        print(f"[AGENDA] Aviso: verificacao de blackout falhou ({e}) — seguindo.")
    if SOMENTE_DIAS_UTEIS and pendulum.now(LOCAL_TZ).weekday() >= 5:
        print("[AGENDA] Fim de semana e pipeline e somente dias uteis — execucao pulada.")
        return False
    if CALENDARIO_NOME:
        try:
            row = hook.get_first(
                "SELECT TOP 1 ISNULL(descricao, '') FROM dbo.etl_calendario "
                "WHERE calendario_nome=%s AND data=CAST(GETDATE() AS DATE)",
                parameters=(CALENDARIO_NOME,),
            )
            if row is not None:
                print(f"[AGENDA] Data bloqueada no calendario {CALENDARIO_NOME} ({row[0]}) — execucao pulada.")
                return False
        except Exception as e:
            print(f"[AGENDA] Aviso: verificacao de calendario falhou ({e}) — seguindo.")
    return True

with DAG(
    dag_id=DAG_ID,
    default_args=default_args,
    description="Pipeline DATASTAGE_COPIA_CONTRATOS_U_SQL69_DIARIO - BI_PRESTAMISTA / CONTRATOS",
    start_date=pendulum.datetime(2026, 7, 22, tz=LOCAL_TZ),
    schedule="0 4 * * *",
    catchup=False,
    max_active_runs=1,
    tags=['BI_PRESTAMISTA', 'CONTRATOS', 'DATASTAGE', 'DIARIO'],
) as dag:

    t_check_agenda = ShortCircuitOperator(
        task_id="check_agenda",
        python_callable=check_agenda,
    )

    t_publish_dataset = EmptyOperator(
        task_id="publish_dataset",
        outlets=[Dataset(DATASET_URI)],
    )

    t_teams_error = PythonOperator(
        task_id="teams_error",
        python_callable=teams_error,
        trigger_rule=TriggerRule.ONE_FAILED,
    )

    t_start_SsdPrs_OdsContratosU_SQL69 = PythonOperator(
        task_id='log_start_SsdPrs_OdsContratosU_SQL69',
        python_callable=log_start,
        op_kwargs={"job_name": 'SsdPrs_OdsContratosU_SQL69', "task_key": 'SsdPrs_OdsContratosU_SQL69'},
    )

    t_job_SsdPrs_OdsContratosU_SQL69 = DataStageOperator(
        task_id='SsdPrs_OdsContratosU_SQL69',
        project=PROJECT_NAME,
        job_name='SsdPrs_OdsContratosU_SQL69',
        ssh_conn_id=SSH_CONN_ID,
        queue_name=DS_QUEUE,
    )

    t_end_SsdPrs_OdsContratosU_SQL69 = PythonOperator(
        task_id='log_end_SsdPrs_OdsContratosU_SQL69',
        python_callable=log_end,
        op_kwargs={"job_name": 'SsdPrs_OdsContratosU_SQL69', "task_key": 'SsdPrs_OdsContratosU_SQL69', "upstream_task_id": 'SsdPrs_OdsContratosU_SQL69'},
        trigger_rule=TriggerRule.ALL_DONE,
    )

    t_check_agenda >> t_start_SsdPrs_OdsContratosU_SQL69 >> t_job_SsdPrs_OdsContratosU_SQL69 >> t_end_SsdPrs_OdsContratosU_SQL69

    end_tasks = [t_end_SsdPrs_OdsContratosU_SQL69]

    [t_end_SsdPrs_OdsContratosU_SQL69] >> t_publish_dataset

    [t_end_SsdPrs_OdsContratosU_SQL69] >> t_teams_error
