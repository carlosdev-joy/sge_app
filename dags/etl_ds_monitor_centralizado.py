"""
etl_ds_monitor_centralizado.py

DAG de monitoramento CENTRALIZADO de jobs DataStage.

PROBLEMA QUE RESOLVE:
  No modelo antigo cada DataStageOperator mantinha seu próprio loop de polling,
  abrindo UMA conexão SSH nova a cada poll (default 60s) por job. Com dezenas de
  jobs concorrentes isso gera centenas/milhares de conexões SSH ao servidor
  DataStage por ciclo, sobrecarregando o dsenv/SSH.

COMO FUNCIONA:
  Roda a cada MONITOR_INTERVAL_MINUTES (default 3). Uma única task Python:
    1. Consulta etl_ds_job_log por todos os jobs em RUNNING/QUEUED.
    2. Abre UMA conexão SSH e reusa para todos os jobs:
       - dsjob -jobinfo de cada job (leve);
       - dsjob -logsum apenas dos que terminaram neste ciclo (e, de forma
         throttled, dos RUNNING, para mostrar progresso parcial dos filhos).
    3. Calcula queued_seconds na transição QUEUED→RUNNING (DATEDIFF de created_at).
    4. Persiste resultados via dbo.sp_etl_ds_job_log_upsert (mesma SP do operator).

PARIDADE COM O OPERATOR (modo blocking):
  - queued_seconds (tempo em fila WM)              ✅ calculado aqui
  - progresso parcial dos jobs filhos (SEQUENCE)   ✅ logsum throttled
  - WARNING reportado como SUCCESS, detalhe no DS   ✅ preservado
  - RESET + retry em ABORTED                        ❌ NÃO (decisão: ver abaixo)

  Retry automático em ABORTED permanece responsabilidade do Airflow (retries da
  task) / operação manual. O monitor apenas registra o estado ABORTED final —
  ele não dispara novos runs para não competir com o scheduler.

CONFIGURAÇÃO (Airflow Variables):
  MONITOR_INTERVAL_MINUTES   intervalo do monitor em minutos      (default 3)
  DS_MONITOR_SSH_CONN_ID     conexão SSH                          (default ssh_lnxprd021)
  DS_MONITOR_MSSQL_CONN_ID   conexão MSSQL                        (default SQL14_DMDB41)
  DS_MONITOR_DSHOME          DSEngine home                        (default /opt/IBM/.../DSEngine)
  DS_MONITOR_LOGSUM_MAX      máx. de jobs RUNNING p/ logsum/ciclo (default 30)
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta

import pendulum
from airflow import DAG
from airflow.models import Variable
from airflow.operators.python import PythonOperator

DAG_ID   = "etl_ds_monitor_centralizado"
LOCAL_TZ = "America/Sao_Paulo"

# status_code dsjob (igual ao DataStageOperator)
_ST_RUNNING = 0
_ST_OK      = 1
_ST_WARNING = 2
_ST_ABORTED = 3
_ST_QUEUED  = 4
_ST_NOT_RUN = 99

default_args = {"owner": "airflow", "depends_on_past": False, "retries": 0}


# ── config helpers ────────────────────────────────────────────────────────────

def _var(key: str, default: str) -> str:
    try:
        return Variable.get(key) or default
    except Exception:
        return default


def _var_int(key: str, default: int) -> int:
    try:
        return int(Variable.get(key, default_var=str(default)))
    except Exception:
        return default


def _interval() -> int:
    return max(1, _var_int("MONITOR_INTERVAL_MINUTES", 3))


# ── parsers (espelham o DataStageOperator) ────────────────────────────────────

def _parse_jobinfo(output: str) -> dict:
    fields: dict = {}
    for line in output.splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            fields[key.strip()] = val.strip()

    status_line = fields.get("Job Status", "")
    m = re.search(r"\((\d+)\)", status_line)
    status_code = int(m.group(1)) if m else _ST_NOT_RUN

    try:
        wave_num = int(fields.get("Job Wave Number", 0))
    except (TypeError, ValueError):
        wave_num = 0

    return {
        "status_code": status_code,
        "status_text": status_line,
        "wave_number": wave_num,
        "start_time":  fields.get("Job Start Time"),
        "pid":         fields.get("Job Process ID"),
        "controller":  fields.get("Job Controller"),
    }


def _parse_child_jobs(logsum: str) -> list:
    batch_re  = re.compile(r"BATCH\s+.*?->\s+\(([^)]+)\):\s+Job run requested")
    finish_re = re.compile(r"Job (\S+) has finished,\s*status\s*=\s*(\d+)\s+\(([^)]+)\)")
    tracked: dict = {}
    result:  list = []
    for line in logsum.splitlines():
        m = batch_re.search(line)
        if m:
            entry = {"name": m.group(1), "status": "RUNNING", "status_code": None}
            tracked[m.group(1)] = entry
            result.append(entry)
            continue
        m = finish_re.search(line)
        if m:
            name, sc, text = m.group(1), int(m.group(2)), m.group(3)
            if name in tracked:
                tracked[name].update({"status": text, "status_code": sc})
            else:
                result.append({"name": name, "status": text, "status_code": sc})
    return result


def _status_label(sc: int) -> str:
    return {0: "RUNNING", 1: "SUCCESS", 2: "WARNING",
            3: "ABORTED", 4: "QUEUED"}.get(sc, "UNKNOWN")


# ── DB ────────────────────────────────────────────────────────────────────────

def _get_active_jobs(mssql_conn_id: str) -> list[dict]:
    """Jobs em RUNNING ou QUEUED no banco — os que precisam ser verificados."""
    from airflow.providers.microsoft.mssql.hooks.mssql import MsSqlHook
    hook = MsSqlHook(mssql_conn_id=mssql_conn_id)
    rows = hook.get_records("""
        SELECT execution_id, pipeline_name, job_name, project,
               wave_number, status, queued_seconds
        FROM dbo.etl_ds_job_log
        WHERE status IN ('RUNNING', 'QUEUED')
        ORDER BY created_at ASC
    """)
    jobs = []
    for r in (rows or []):
        jobs.append({
            "execution_id":   r[0],
            "pipeline_name":  r[1],
            "job_name":       r[2],
            "project":        r[3],
            "wave_number":    r[4],
            "db_status":      r[5],
            "queued_seconds": r[6],
        })
    return jobs


def _persist(hook, execution_id, pipeline, job_name, project, wave_num, pid,
             status, status_code, child_jobs, log_summary, poll_snapshot,
             ds_start_time=None, ds_end_time=None) -> None:
    """Chama dbo.sp_etl_ds_job_log_upsert — assinatura idêntica ao operator."""
    hook.run(
        "EXEC dbo.sp_etl_ds_job_log_upsert "
        "@execution_id=%s, @pipeline_name=%s, @job_name=%s, @project=%s, "
        "@wave_number=%s, @pid=%s, @status=%s, @status_code=%s, "
        "@child_jobs=%s, @log_summary=%s, @poll_snapshot=%s, "
        "@ds_start_time=%s, @ds_end_time=%s",
        parameters=(
            execution_id, pipeline, job_name, project,
            wave_num, pid or "", status, status_code,
            json.dumps(child_jobs, ensure_ascii=False) if child_jobs else "",
            (log_summary or "")[:8000],
            poll_snapshot or "",
            ds_start_time or "",
            ds_end_time,
        ),
    )


def _persist_queued_seconds(hook, execution_id, job_name) -> None:
    """queued_seconds = tempo entre created_at (entrada na fila) e agora."""
    hook.run(
        "UPDATE dbo.etl_ds_job_log "
        "SET queued_seconds = DATEDIFF(SECOND, created_at, GETDATE()), "
        "    updated_at = GETDATE() "
        "WHERE execution_id=%s AND job_name=%s AND queued_seconds IS NULL",
        parameters=(execution_id, job_name),
    )


# ── task principal ────────────────────────────────────────────────────────────

def monitor_jobs(**context) -> None:
    import logging
    log = logging.getLogger("ds_monitor")

    mssql_conn_id = _var("DS_MONITOR_MSSQL_CONN_ID", "SQL14_DMDB41")
    ssh_conn_id   = _var("DS_MONITOR_SSH_CONN_ID",   "ssh_lnxprd021")
    dshome        = _var("DS_MONITOR_DSHOME",
                         "/opt/IBM/InformationServer/Server/DSEngine")
    logsum_max    = _var_int("DS_MONITOR_LOGSUM_MAX", 30)

    jobs = _get_active_jobs(mssql_conn_id)
    if not jobs:
        log.info("[DS Monitor] Nenhum job RUNNING/QUEUED. Nada a fazer.")
        return

    log.info("[DS Monitor] %d job(s) ativos — abrindo 1 conexão SSH.", len(jobs))

    from airflow.providers.microsoft.mssql.hooks.mssql import MsSqlHook
    from airflow.providers.ssh.hooks.ssh import SSHHook

    client = SSHHook(ssh_conn_id=ssh_conn_id).get_conn()   # UMA conexão p/ todos
    ts_now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    def _ssh(cmd: str, timeout: int = 30) -> str:
        full = f"source {dshome}/dsenv && {cmd}"
        _, stdout, _ = client.exec_command(full, timeout=timeout)
        stdout.channel.recv_exit_status()
        return stdout.read().decode(errors="replace").strip()

    results: list[dict] = []   # estado lido por job, p/ persistir depois
    finalizados = 0
    logsum_budget = logsum_max

    try:
        for job in jobs:
            project, jname = job["project"], job["job_name"]
            try:
                info = _parse_jobinfo(_ssh(f"{dshome}/bin/dsjob -jobinfo {project} {jname}"))
            except Exception as e:
                log.warning("[DS Monitor] jobinfo falhou p/ %s/%s: %s", project, jname, e)
                continue

            sc       = info["status_code"]
            terminal = sc not in (_ST_RUNNING, _ST_QUEUED)
            logsum, child_jobs = "", []

            # logsum: sempre p/ terminais; throttled p/ RUNNING (progresso parcial)
            want_logsum = terminal or (sc == _ST_RUNNING and logsum_budget > 0)
            if want_logsum:
                if not terminal:
                    logsum_budget -= 1
                try:
                    logsum     = _ssh(f"{dshome}/bin/dsjob -logsum {project} {jname}", timeout=120)
                    child_jobs = _parse_child_jobs(logsum)
                except Exception as e:
                    log.warning("[DS Monitor] logsum falhou p/ %s/%s: %s", project, jname, e)

            results.append({"job": job, "info": info, "sc": sc,
                            "terminal": terminal, "logsum": logsum,
                            "child_jobs": child_jobs})
            if terminal:
                finalizados += 1
            log.info("[DS Monitor] %s/%s → %s(%s)%s",
                     project, jname, sc, _status_label(sc),
                     f" [{len(child_jobs)} filhos]" if child_jobs else "")
    finally:
        client.close()
        log.info("[DS Monitor] Conexão SSH encerrada.")

    # ── persistência (fora do SSH) ────────────────────────────────────────────
    hook = MsSqlHook(mssql_conn_id=mssql_conn_id)

    for r in results:
        job, info, sc = r["job"], r["info"], r["sc"]
        exec_id  = job["execution_id"]
        pipeline = job["pipeline_name"]
        jname    = job["job_name"]
        project  = job["project"]
        wave     = info.get("wave_number") or job.get("wave_number") or 0

        try:
            # queued_seconds: registra quando o job DEIXA a fila (estava QUEUED
            # no banco e agora não está mais QUEUED) e ainda não foi medido.
            if (job["db_status"] == "QUEUED" and sc != _ST_QUEUED
                    and job.get("queued_seconds") is None):
                _persist_queued_seconds(hook, exec_id, jname)
                log.info("[DS Monitor] queued_seconds registrado p/ %s", jname)

            if not r["terminal"]:
                # ainda RUNNING/QUEUED: anexa snapshot
                snapshot = json.dumps({
                    "ts": ts_now, "status_code": sc,
                    "status_text": info.get("status_text", ""),
                }, ensure_ascii=False)
                _persist(hook, exec_id, pipeline, jname, project, wave,
                         info.get("pid"), _status_label(sc), sc,
                         [], "", snapshot)
                continue

            # ── terminal ──
            if sc in (_ST_OK, _ST_WARNING):
                # WARNING vira SUCCESS no log do Airflow/factory; detalhe no DS
                ds_label = "Finished with warnings" if sc == _ST_WARNING else "SUCCESS"
                _persist(hook, exec_id, pipeline, jname, project, wave,
                         info.get("pid"), ds_label, sc,
                         r["child_jobs"], r["logsum"], None,
                         ds_start_time=info.get("start_time"),
                         ds_end_time=datetime.utcnow())
            elif sc == _ST_ABORTED:
                _persist(hook, exec_id, pipeline, jname, project, wave,
                         info.get("pid"), "ABORTED", sc,
                         r["child_jobs"], r["logsum"], None,
                         ds_start_time=info.get("start_time"),
                         ds_end_time=datetime.utcnow())
            else:  # NOT_RUN ou desconhecido
                _persist(hook, exec_id, pipeline, jname, project, wave,
                         info.get("pid"), _status_label(sc), sc,
                         r["child_jobs"], r["logsum"], None,
                         ds_end_time=datetime.utcnow())
        except Exception as e:
            log.warning("[DS Monitor] persistência falhou p/ %s: %s", jname, e)

    log.info("[DS Monitor] Ciclo OK — %d verificados, %d finalizados.",
             len(results), finalizados)


# ── DAG ───────────────────────────────────────────────────────────────────────

with DAG(
    dag_id=DAG_ID,
    default_args=default_args,
    description="Polling centralizado de jobs DataStage — 1 conexão SSH p/ N jobs",
    schedule_interval=f"*/{_interval()} * * * *",
    start_date=pendulum.datetime(2025, 1, 1, tz=LOCAL_TZ),
    catchup=False,
    max_active_runs=1,   # nunca dois ciclos simultâneos
    tags=["datastage", "monitor", "infraestrutura"],
) as dag:

    PythonOperator(
        task_id="monitorar_jobs_datastage",
        python_callable=monitor_jobs,
        execution_timeout=timedelta(minutes=max(1, _interval() - 1)),
    )
