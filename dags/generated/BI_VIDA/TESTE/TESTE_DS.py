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

# F5 — portao da etapa em espera (utils/espera.py). Import guardado:
# sem os modulos no servidor a DAG importa igual, com o log_start de
# sempre (PythonOperator) e o portao desligado.
try:
    from utils import espera as _espera
    from utils.job_operators import LogStartOperator as _LogStart
except Exception as _espera_err:  # noqa: BLE001
    _espera = None
    _LogStart = PythonOperator
    print(f"[ESPERA] utils.espera indisponivel ({_espera_err}) — portao desligado")
# =========================
# Gerado automaticamente por etl_dag_factory
# Pipeline: TESTE_DS | Projeto: BI_VIDA | Dominio: TESTE
# =========================
DAG_ID        = "TESTE_DS"
SSH_CONN_ID   = "ssh_lnxprd021"
MSSQL_CONN_ID = "SQL14_DMDB41"
PROJECT_NAME  = "BI_VIDA"
DOMAIN        = "TESTE"
PIPELINE_NAME = "TESTE_DS"
BASE_LOG_DIR  = "/Projetos/BI_CVP/Logs/Airflow"
LOCAL_TZ      = "America/Sao_Paulo"
TEAMS_WEBHOOK_VAR = "TEAMS_WEBHOOK_URL_CVP"
DS_QUEUE      = 'HighPriorityJobs'
RUNBOOK_MD    = None
CALENDARIO_NOME    = None
SOMENTE_DIAS_UTEIS = False
HORARIOS_ESPECIFICOS = None
DIAS_HORARIOS_MES = None
DATASET_URI   = "orq://pipeline/TESTE_DS"
default_args  = {"owner": "airflow", "depends_on_past": False, "retries": 1, "retry_delay": timedelta(seconds=300)}
JOBS          = ['SsdVidaDimePessoa02Ftp_orq']
FLOW_JOBS     = ['SsdVidaDimePessoa02Ftp_orq']

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
    # F5 — portao da etapa em espera: SEM pausa pedida (o caso normal)
    # devolve None de imediato e o caminho abaixo e o de sempre.
    if _espera is not None:
        _espera.portao(hook, PIPELINE_NAME, job_name, execution_id)
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

def _disparado_por(context):
    # Origem do disparo: conf explicito (a F3 usara para nomear o pai) >
    # prefixo do run_id (manual / dataset) > agenda.
    dr = context.get('dag_run')
    conf = (getattr(dr, 'conf', None) or {}) if dr is not None else {}
    if conf.get('disparado_por'):
        return str(conf['disparado_por'])[:200]
    run_id = str(context.get('run_id') or '')
    if run_id.startswith('manual'):
        return 'manual'
    if run_id.startswith('dataset_triggered'):
        return 'dataset'
    return 'agenda'

def _origem_disparo(context):
    """Taxonomia EXPLICITA da origem do disparo (F3): agenda | manual |
    dep | guardia | dataset. Substitui o sniffing por startswith('manual')
    nas REGRAS do check_agenda — dep__* nao comeca com 'manual' e caia nas
    regras de relogio (era PULADO em 100% dos disparos por evento).
    Origem desconhecida degrada para 'manual' (acao humana): nunca julga
    hora, mas continua julgando dia — degradacao visivel, nunca execucao
    indevida."""
    run_id = str(context.get('run_id') or '')
    if run_id.startswith('scheduled'):
        return 'agenda'
    if run_id.startswith('dep__'):
        return 'dep'
    if run_id.startswith('guardia__'):
        return 'guardia'
    if run_id.startswith('dataset_triggered'):
        return 'dataset'
    return 'manual'

def _dia_operacional(context):
    """O dia de calendario em que a corrida foi ORDENADA na origem — e
    contra ele que as regras de DIA sao julgadas. A data_referencia e o
    ROTULO de juncao da corrida (a virada e artificio de juncao, nao
    re-rotulacao do dia de negocio): julgar dia pela data_referencia
    pulava a corrida certa quando a virada a carimbava no dia seguinte.

    Precedencia: conf['dia_operacional'] valido > conf['data_referencia']
    (aproximacao com log — cobre trigger manual que so passou a data) >
    date do momento LOGICO em LOCAL_TZ. Nunca o relogio de parede: atraso
    de fila que vira a meia-noite nao muda o dia julgado."""
    dr = context.get('dag_run')
    conf = (getattr(dr, 'conf', None) or {}) if dr is not None else {}
    from datetime import datetime as _dt
    for chave in ('dia_operacional', 'data_referencia'):
        bruto = conf.get(chave)
        if not bruto:
            continue
        try:
            valor = _dt.strptime(str(bruto).strip(), '%Y-%m-%d').date()
        except (ValueError, TypeError):
            print(f'[DEP] {chave} herdado invalido ({bruto!r}) — seguindo a cadeia de precedencia')
            continue
        if chave == 'data_referencia':
            print('[DEP] dia_operacional ausente no conf — aproximando pela data_referencia herdada')
        return valor
    # Run MANUAL em DAG com cron: o data_interval_end e o ULTIMO TICK do
    # cron (domingo 06:00 num daily disparado segunda 05:50; o dia 1 num
    # mensal) — julgar dias uteis/calendario contra ele pularia um manual
    # legitimo (regressao pega pela revisao adversarial da F3). O dia de
    # um manual sem conf e HOJE: e o dia em que o operador ordenou.
    if _origem_disparo(context) == 'manual':
        return pendulum.now(LOCAL_TZ).date()
    momento = context.get('data_interval_end') or context.get('logical_date')
    if momento is not None:
        momento = momento.in_timezone(LOCAL_TZ)
    else:
        momento = pendulum.now(LOCAL_TZ)
    return momento.date()

def _data_referencia(context):
    """A que dia de processamento (ODATE) esta corrida pertence.

    1) Heranca: conf['data_referencia'] (carimbo do predecessor, ou de um
       disparo manual com data) prevalece; valor invalido loga e recalcula,
       nunca aborta.
    2) Calculo: momento LOGICO do run (data_interval_end/logical_date em
       LOCAL_TZ) deslocado pela hora de virada do pipeline (fallback:
       config global; qualquer erro degrada para 00:00 = data do
       calendario, o comportamento de sempre).
    NUNCA o relogio de parede: atraso de fila ou rerun no dia seguinte nao
    pode mudar a data da corrida."""
    dr = context.get('dag_run')
    conf = (getattr(dr, 'conf', None) or {}) if dr is not None else {}
    herdada = conf.get('data_referencia')
    if herdada:
        try:
            from datetime import datetime as _dt
            return _dt.strptime(str(herdada).strip(), '%Y-%m-%d').date()
        except (ValueError, TypeError):
            print(f'[EXEC] data_referencia herdada invalida ({herdada!r}) — recalculando')
    momento = context.get('data_interval_end') or context.get('logical_date')
    if momento is not None:
        momento = momento.in_timezone(LOCAL_TZ)
    else:
        momento = pendulum.now(LOCAL_TZ)
    virada = None
    try:
        row = MsSqlHook(mssql_conn_id=MSSQL_CONN_ID).get_first(
            "SELECT COALESCE(CONVERT(VARCHAR(8), p.hora_virada, 108), c.config_value) "
            "FROM dbo.etl_pipeline p "
            "LEFT JOIN dbo.etl_app_config c ON c.config_key='dependencia_hora_virada' "
            "WHERE p.pipeline_name=%s",
            parameters=(PIPELINE_NAME,),
        )
        if row:
            virada = row[0]
    except Exception as e:
        print(f'[EXEC] hora de virada indisponivel ({e}) — usando 00:00')
    from utils.data_referencia import calcular as _calcular_data_ref
    return _calcular_data_ref(momento, virada)

def _registrar_execucao(status, context, motivo=None):
    """Upsert em dbo.etl_pipeline_execucao pela chave COMPLETA:
    (pipeline_name, data_referencia, execution_id = run_id do Airflow).

    A linha NASCE com execution_id preenchido; reserva com NULL e proibida
    por contrato — quem quiser criar linha antes do run (push/guardia, F3)
    calcula o run_id primeiro, insere JA com ele e passa o mesmo valor ao
    trigger. (etl_job_execution segue com o carimbo ts_nodash proprio do
    nivel job — semanticas distintas, de proposito.)

    Contrato de LEITURA (consumido na F3): liberacao e EXISTS(pipeline=P
    AND data_referencia=D AND status='SUCESSO') — nunca 'linha mais
    recente', nunca COALESCE(inicio, criado_em). PULADO/FALHA nao negam um
    SUCESSO existente da mesma data; N execucoes no dia = N linhas.

    Registro e observabilidade: NUNCA derruba a carga. Sem a migration 067
    loga o aviso e retorna; qualquer excecao vira print, jamais propaga."""
    try:
        run_id = str(context['run_id'])
        hook = MsSqlHook(mssql_conn_id=MSSQL_CONN_ID)
        obj = hook.get_first("SELECT OBJECT_ID('dbo.etl_pipeline_execucao','U')")
        if not obj or obj[0] is None:
            print('[EXEC] migration 067 ausente — execucao nao registrada')
            return
        data_ref = _data_referencia(context)
        origem = _disparado_por(context)
        motivo = str(motivo)[:500] if motivo is not None else None
        guarda_terminal = ''
        if status == 'EXECUTANDO':
            # Re-tentativa de run inteiro limpo reseta a janela da corrida.
            upd_extra, ins_inicio, ins_fim = 'inicio=GETDATE(), fim=NULL', 'GETDATE()', 'NULL'
        elif status == 'PULADO':
            # Pulado nao comecou nem terminou: inicio e fim ficam NULL.
            # GUARDA: PULADO nao rebaixa estado TERMINAL da mesma linha.
            # Cenario real (revisao adversarial da F2): Clear de um run
            # SUCESSO num dia em que uma regra de relogio bloqueia (fim de
            # semana/blackout) reexecuta o check_agenda, que decide PULADO
            # — sem a guarda, o unico SUCESSO da data viraria PULADO e o
            # contrato EXISTS(SUCESSO) da F3 quebraria retroativamente.
            upd_extra, ins_inicio, ins_fim = 'inicio=NULL, fim=NULL', 'NULL', 'NULL'
            guarda_terminal = " AND status NOT IN ('SUCESSO', 'FALHA')"
        else:  # SUCESSO / FALHA fecham a corrida sem mexer no inicio
            upd_extra, ins_inicio, ins_fim = 'fim=GETDATE()', 'NULL', 'GETDATE()'
        conn = hook.get_conn()
        try:
            cur = conn.cursor()
            cur.execute(
                'UPDATE dbo.etl_pipeline_execucao '
                'SET status=%s, motivo=%s, disparado_por=%s, atualizado_em=GETDATE(), ' + upd_extra + ' '
                'WHERE pipeline_name=%s AND data_referencia=%s AND execution_id=%s' + guarda_terminal,
                (status, motivo, origem, PIPELINE_NAME, data_ref, run_id),
            )
            precisa_insert = (cur.rowcount == 0)
            if precisa_insert and guarda_terminal:
                # rowcount 0 com a guarda pode ser 'linha existe e e terminal'
                # — nesse caso NAO insere (duplicaria a chave) nem rebaixa.
                cur.execute(
                    'SELECT 1 FROM dbo.etl_pipeline_execucao '
                    'WHERE pipeline_name=%s AND data_referencia=%s AND execution_id=%s',
                    (PIPELINE_NAME, data_ref, run_id),
                )
                if cur.fetchone():
                    print(f'[EXEC] PULADO nao rebaixa estado terminal: {PIPELINE_NAME} run_id={run_id}')
                    conn.commit()
                    return
            if precisa_insert:
                cur.execute(
                    'INSERT INTO dbo.etl_pipeline_execucao '
                    '(pipeline_name, data_referencia, execution_id, status, inicio, fim, disparado_por, motivo) '
                    'VALUES (%s, %s, %s, %s, ' + ins_inicio + ', ' + ins_fim + ', %s, %s)',
                    (PIPELINE_NAME, data_ref, run_id, status, origem, motivo),
                )
            conn.commit()
        finally:
            conn.close()
        print(f'[EXEC] {status} registrado: {PIPELINE_NAME} data_ref={data_ref} run_id={run_id} origem={origem}')
    except Exception as e:
        print(f'[EXEC] Aviso: execucao nao registrada (migration 067 aplicada?): {e}')

def _registrar_falha(**context):
    # Fecha a corrida como FALHA nomeando as tasks que falharam. Roda em
    # qualquer falha do run — o registro e observabilidade, nao
    # notificacao, por isso existe mesmo com os cards do Teams desligados.
    falhas = []
    dr = context.get('dag_run')
    if dr is not None:
        try:
            falhas = sorted(ti.task_id for ti in dr.get_task_instances()
                            if str(ti.state) == 'failed')
        except Exception as e:
            print(f'[EXEC] lista de tasks com falha indisponivel: {e}')
    motivo = ('falha em: ' + ', '.join(falhas)) if falhas else 'falha na execucao'
    _registrar_execucao('FALHA', context, motivo=motivo)

def _registrar_sucesso(**context):
    # Corpo do publish_dataset: grava SUCESSO e devolve — o Dataset segue
    # publicado pelos outlets no sucesso da task, como sempre foi.
    # Degradado por construcao: _registrar_execucao nunca levanta.
    _registrar_execucao('SUCESSO', context)
    # F3: avalia e dispara os dependentes DEPOIS do commit do SUCESSO,
    # no MESMO callable — commit -> avaliar e sequencia, nao corrida (a
    # condicao do candidato enxerga este pipeline ja gravado). Roda mesmo
    # se o registro degradou: sem o SUCESSO no banco a condicao nao fecha
    # e nada dispara — sem mentira. Nunca levanta (falha no disparo nao
    # derruba o pai).
    _disparar_dependentes(context)

def _disparar_dependentes(context):
    """F3 — disparo imediato dos dependentes (docs/retomada-f3-desenho.md).

    A lista de dependentes NAO fica no codigo gerado: e lida ao vivo da
    tabela da migration 067 — cadastrar dependente novo vale no proximo
    fim deste pipeline sem regenerar o pai (so o filho e regerado).

    Por candidato: pre-filtro de dia (MESMO predicado puro que o filho
    julga, com o MESMO dia operacional que vai no conf) -> condicao
    EXISTS -> janela nao_iniciar_antes (relogio de parede: janela E de
    relogio, por definicao) -> claim -> disparo com heranca de
    data_referencia + dia_operacional -> devolucao se o disparo levantar.
    Blackout NAO e pre-filtrado (e sobre o agora do FILHO, e a corrida
    devida merece linha PULADO visivel). Erro em um candidato nao cancela
    os demais e NENHUMA falha aqui derruba o pipeline pai — tudo logado
    com [DEP], nunca silencio."""
    try:
        from utils.dependencias import (
            config_dependente as _dep_config,
            dependentes_de as _dep_dependentes,
            devolver_reserva as _dep_devolver,
            dia_permitido as _dep_dia_permitido,
            liberado as _dep_liberado,
            montar_conf as _dep_montar_conf,
            novo_run_id as _dep_novo_run_id,
            ordenar_corrida as _dep_ordenar,
            reservar_corrida as _dep_reservar,
        )
        hook = MsSqlHook(mssql_conn_id=MSSQL_CONN_ID)
        obj = hook.get_first("SELECT OBJECT_ID('dbo.etl_pipeline_dependencia','U')")
        if not obj or obj[0] is None:
            print('[DEP] migration 067 ausente — dependentes nao avaliados')
            return
        data_ref = _data_referencia(context)
        dia_op = _dia_operacional(context)
        conn = hook.get_conn()
        try:
            candidatos = _dep_dependentes(conn, PIPELINE_NAME)
            if not candidatos:
                return
            print(f'[DEP] candidatos de {PIPELINE_NAME} em {data_ref}: {candidatos}')
            for filho in candidatos:
                try:
                    cfg = _dep_config(conn, filho)
                    if cfg is None:
                        print(f'[DEP] {filho} sem cadastro em etl_pipeline — ignorado')
                        continue
                    ok_dia, motivo_dia = _dep_dia_permitido(cfg['regras_dia'], dia_op)
                    if not ok_dia:
                        print(f'[DEP] {filho} fora do dia em {dia_op}: {motivo_dia}')
                        continue
                    lib, faltantes = _dep_liberado(conn, filho, data_ref)
                    if not lib:
                        print(f'[DEP] {filho} aguardando: ' + ', '.join(faltantes))
                        continue
                    run_id = _dep_novo_run_id('dep', data_ref, PIPELINE_NAME)
                    janela = cfg.get('nao_iniciar_antes')
                    if janela is not None and pendulum.now(LOCAL_TZ).time() < janela:
                        criou = _dep_ordenar(conn, filho, data_ref, run_id, PIPELINE_NAME)
                        conn.commit()
                        print(f'[DEP] {filho} liberado antes da janela {janela} — '
                              + ('corrida ordenada, aguardando' if criou else 'corrida ja existente'))
                        continue
                    ganho = _dep_reservar(conn, filho, data_ref, run_id, PIPELINE_NAME)
                    conn.commit()
                    if ganho is None:
                        print(f'[DEP] {filho} ja tem corrida em {data_ref} — sem novo disparo')
                        continue
                    try:
                        from airflow.api.client.local_client import Client
                        Client(None, None).trigger_dag(
                            dag_id=filho, run_id=ganho,
                            conf=_dep_montar_conf(data_ref, dia_op, PIPELINE_NAME))
                        print(f'[DEP] {filho} disparado: run_id={ganho} data_ref={data_ref}')
                    except Exception as e:
                        _dep_devolver(conn, filho, data_ref, ganho,
                                      veio_de_adocao=(ganho != run_id))
                        conn.commit()
                        print(f'[DEP] disparo de {filho} falhou ({e}) — reserva devolvida')
                except Exception as e:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                    print(f'[DEP] avaliacao de {filho} falhou ({e}) — seguindo para o proximo')
        finally:
            conn.close()
    except Exception as e:
        print(f'[DEP] disparo de dependentes indisponivel ({e}) — o pipeline pai segue')

def _check_agenda_regras(context):
    """Regras de agenda (F2/F3). Devolve (liberado, motivo) — quem
    escreve o resultado da corrida e o wrapper check_agenda.

    Regras de HORA valem so para disparo de agenda: evento e 'quando
    liberou', nao 'que horas sao' — o piso de horario de um dependente e
    nao_iniciar_antes, no pusher. Regras de DIA valem para TODA origem e
    julgam o dia OPERACIONAL (nunca o relogio: atraso de fila que vira a
    meia-noite nao pula a corrida). Blackout segue medindo o relogio DE
    PROPOSITO: freeze operacional e sobre o agora, em qualquer origem."""
    _origem = _origem_disparo(context)
    _dia_op = _dia_operacional(context)
    # Horários específicos: o cron dispara na união minuto×hora;
    # só executa se o horário agendado estiver na lista configurada.
    if HORARIOS_ESPECIFICOS and _origem == 'agenda':
        _die = context.get('data_interval_end') or context.get('logical_date')
        if _die is not None:
            _hhmm = _die.in_timezone(LOCAL_TZ).strftime('%H:%M')
            if _hhmm not in HORARIOS_ESPECIFICOS:
                print(f"[AGENDA] {_hhmm} fora dos horarios configurados {HORARIOS_ESPECIFICOS} — execucao pulada.")
                return False, f'horario {_hhmm} fora dos horarios configurados'
    # Dia + hora específico do mês: parte de HORA (só agenda). O DIA é
    # julgado pelo dia operacional; para disparo por evento a parte de
    # dia sobrevive na restrição de dia gerada, julgada adiante.
    if DIAS_HORARIOS_MES and _origem == 'agenda':
        _die = context.get('data_interval_end') or context.get('logical_date')
        if _die is not None:
            _hhmm = _die.in_timezone(LOCAL_TZ).strftime('%H:%M')
            _dia = _dia_op.day
            if _hhmm not in DIAS_HORARIOS_MES.get(_dia, []):
                print(f"[AGENDA] dia {_dia} as {_hhmm} fora da configuracao {DIAS_HORARIOS_MES} — execucao pulada.")
                return False, f'dia {_dia} as {_hhmm} fora da configuracao de dia e hora do mes'
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
            return False, f'blackout vigente: {row[0]}'
    except Exception as e:
        print(f"[AGENDA] Aviso: verificacao de blackout falhou ({e}) — seguindo.")
    if SOMENTE_DIAS_UTEIS and _dia_op.weekday() >= 5:
        print("[AGENDA] Fim de semana e pipeline e somente dias uteis — execucao pulada.")
        return False, 'fim de semana e pipeline somente dias uteis'
    if CALENDARIO_NOME:
        try:
            from utils.dependencias import calendario_bloqueia as _cal_bloqueia
            _conn_cal = hook.get_conn()
            try:
                _bloqueado = _cal_bloqueia(_conn_cal, CALENDARIO_NOME, _dia_op)
            finally:
                _conn_cal.close()
            if _bloqueado:
                print(f"[AGENDA] Data bloqueada no calendario {CALENDARIO_NOME} — execucao pulada.")
                return False, f'data bloqueada no calendario {CALENDARIO_NOME}'
        except Exception as e:
            print(f"[AGENDA] Aviso: verificacao de calendario falhou ({e}) — seguindo.")
    return True, None

def check_agenda(**context):
    """Decide E registra: avalia as regras de agenda e grava o resultado da
    corrida — EXECUTANDO quando libera, PULADO quando pula (sem inicio nem
    fim: nao comecou nem terminou). Ponto UNICO de nascimento da linha em
    etl_pipeline_execucao, ja com o run_id como chave. A decisao e
    calculada ANTES do registro e devolvida independentemente dele;
    False pula a execucao inteira."""
    ok, motivo = _check_agenda_regras(context)
    _registrar_execucao('EXECUTANDO' if ok else 'PULADO', context, motivo=motivo)
    return ok

with DAG(
    dag_id=DAG_ID,
    default_args=default_args,
    description="Pipeline TESTE_DS - BI_VIDA / TESTE",
    start_date=pendulum.datetime(2026, 1, 1, tz=LOCAL_TZ),
    schedule=None,  # sob demanda: só execução manual
    catchup=False,
    max_active_runs=1,
    tags=['BI_VIDA', 'TESTE', 'VIDA'],
) as dag:

    t_check_agenda = ShortCircuitOperator(
        task_id="check_agenda",
        python_callable=check_agenda,
    )

    t_publish_dataset = PythonOperator(
        task_id="publish_dataset",
        python_callable=_registrar_sucesso,
        outlets=[Dataset(DATASET_URI)],
    )

    t_reg_falha = PythonOperator(
        task_id="registrar_falha",
        python_callable=_registrar_falha,
        trigger_rule=TriggerRule.ONE_FAILED,
    )

    t_start_SsdVidaDimePessoa02Ftp_orq = _LogStart(
        task_id='log_start_SsdVidaDimePessoa02Ftp_orq',
        python_callable=log_start,
        op_kwargs={"job_name": 'SsdVidaDimePessoa02Ftp_orq', "task_key": 'SsdVidaDimePessoa02Ftp_orq'},
    )

    t_job_SsdVidaDimePessoa02Ftp_orq = DataStageOperator(
        task_id='SsdVidaDimePessoa02Ftp_orq',
        project=PROJECT_NAME,
        job_name='SsdVidaDimePessoa02Ftp_orq',
        ssh_conn_id=SSH_CONN_ID,
        queue_name=DS_QUEUE,
    )

    t_end_SsdVidaDimePessoa02Ftp_orq = PythonOperator(
        task_id='log_end_SsdVidaDimePessoa02Ftp_orq',
        python_callable=log_end,
        op_kwargs={"job_name": 'SsdVidaDimePessoa02Ftp_orq', "task_key": 'SsdVidaDimePessoa02Ftp_orq', "upstream_task_id": 'SsdVidaDimePessoa02Ftp_orq'},
        trigger_rule=TriggerRule.ALL_DONE,
    )

    t_check_agenda >> t_start_SsdVidaDimePessoa02Ftp_orq >> t_job_SsdVidaDimePessoa02Ftp_orq >> t_end_SsdVidaDimePessoa02Ftp_orq

    end_tasks = [t_end_SsdVidaDimePessoa02Ftp_orq]

    [t_end_SsdVidaDimePessoa02Ftp_orq] >> t_publish_dataset

    [t_end_SsdVidaDimePessoa02Ftp_orq] >> t_reg_falha
