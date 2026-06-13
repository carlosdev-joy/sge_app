"""
etl_ds_monitor_centralizado.py

DAG de monitoramento centralizado de jobs DataStage.

ARQUITETURA:
  Roda a cada MONITOR_INTERVAL minutos (default 3 min).
  Uma única task Python:
    1. Consulta o banco (etl_ds_job_log) por todos os jobs com status=RUNNING.
    2. Abre UMA conexão SSH e chama `dsjob -jobinfo` para cada job ativo
       em sequência — reutilizando a mesma conexão SSH (sem abrir/fechar).
    3. Para jobs que terminaram (OK/WARNING/ABORTED), chama `dsjob -logsum`
       (somente uma vez, ao final) e persiste o resultado final.
    4. Persiste snapshots de estado em batch (uma transação por ciclo).

COMPARATIVO:
  Antes (polling por job): N_jobs × (duração / poll_interval) conexões SSH
  Depois (monitor central): duração_total / MONITOR_INTERVAL conexões SSH
  Exemplo: 50 jobs × 30 min / 60s = 1.500 conexões → 30 min / 3 min = 10 conexões

CONFIGURAÇÃO:
  Variável Airflow  MONITOR_INTERVAL_MINUTES  (default: 3)
  Variável Airflow  DS_MONITOR_SSH_CONN_ID    (default: ssh_lnxprd021)
  Variável Airflow  DS_MONITOR_MSSQL_CONN_ID  (default: SQL14_DMDB41)
  Variável Airflow  DS_MONITOR_DSHOME         (default: /opt/IBM/InformationServer/Server/DSEngine)
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

default_args = {
    "owner":           "airflow",
    "depends_on_past": False,
    "retries":         0,
}

# ── helpers ──────────────────────────────────────────────────────────────────

def _var(key: str, default: str) -> str:
    try:
        return Variable.get(key) or default
    except Exception:
        return default


def _get_running_jobs(mssql_conn_id: str) -> list[dict]:
    """Retorna todos os jobs com status RUNNING no banco."""
    from airflow.providers.microsoft.mssql.hooks.mssql import MsSqlHook
    hook = MsSqlHook(mssql_conn_id=mssql_conn_id)
    rows = hook.get_records("""
        SELECT execution_id, pipeline_name, job_name, project, wave_number, pid
        FROM dbo.etl_ds_job_log
        WHERE status = 'RUNNING'
        ORDER BY created_at ASC
    """)
    return [
        {
            "execution_id":  r[0], "pipeline_name": r[1],
            "job_name":      r[2], "project":       r[3],
            "wave_number":   r[4], "pid":           r[5],
        }
        for r in (rows or [])
    ]


def _parse_jobinfo(output: str) -> dict:
    fields: dict = {}
    for line in output.splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            fields[key.strip()] = val.strip()

    status_line = fields.get("Job Status", "")
    m = re.search(r"\((\d+)\)", status_line)
    status_code = int(m.group(1)) if m else 99  # 99 = NOT_RUN

    try:
        wave_num = int(fields.get("Job Wave Number", 0))
    except (TypeError, ValueError):
        wave_num = 0

    return {
        "status_code": status_code,
        "status_text": status_line,
        "wave_number": wave_num,
        "pid":         fields.get("Job Process ID"),
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
    return {0: "RUNNING", 1: "SUCCESS", 2: "WARNING", 3: "ABORTED", 4: "QUEUED"}.get(sc, "UNKNOWN")


# ── tarefa principal ──────────────────────────────────────────────────────────

def monitor_jobs(**context) -> None:
    import logging
    log = logging.getLogger(__name__)

    mssql_conn_id = _var("DS_MONITOR_MSSQL_CONN_ID", "SQL14_DMDB41")
    ssh_conn_id   = _var("DS_MONITOR_SSH_CONN_ID",   "ssh_lnxprd021")
    dshome        = _var("DS_MONITOR_DSHOME",
                         "/opt/IBM/InformationServer/Server/DSEngine")

    jobs = _get_running_jobs(mssql_conn_id)
    if not jobs:
        log.info("[DS Monitor] Nenhum job RUNNING no momento.")
        return

    log.info("[DS Monitor] %d job(s) RUNNING — abrindo SSH...", len(jobs))

    from airflow.providers.microsoft.mssql.hooks.mssql import MsSqlHook
    from airflow.providers.ssh.hooks.ssh import SSHHook

    ssh_hook = SSHHook(ssh_conn_id=ssh_conn_id)
    client   = ssh_hook.get_conn()   # UMA conexão SSH para todos os jobs

    snapshots:  list[tuple] = []   # (execution_id, job_name, snapshot_json)
    finalizados: list[dict] = []   # jobs que terminaram neste ciclo
    ts_now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    def _exec_ssh(cmd: str, timeout: int = 30) -> str:
        full = f"source {dshome}/dsenv && {cmd}"
        _, stdout, _ = client.exec_command(full, timeout=timeout)
        stdout.channel.recv_exit_status()
        return stdout.read().decode(errors="replace").strip()

    try:
        for job in jobs:
            project = job["project"]
            jname   = job["job_name"]
            exec_id = job["execution_id"]
            pipeline = job["pipeline_name"]

            try:
                out  = _exec_ssh(f"{dshome}/bin/dsjob -jobinfo {project} {jname}")
                info = _parse_jobinfo(out)
                sc   = info["status_code"]

                snapshot = json.dumps({
                    "ts": ts_now, "status_code": sc,
                    "status_text": info.get("status_text", ""),
                }, ensure_ascii=False)
                snapshots.append((exec_id, pipeline, jname, project,
                                  info.get("wave_number", 0), info.get("pid", ""),
                                  _status_label(sc), sc, snapshot))

                if sc not in (0, 4):  # não é RUNNING nem QUEUED
                    finalizados.append({**job, "status_code": sc, "info": info})

            except Exception as e:
                log.warning("[DS Monitor] Erro ao consultar %s/%s: %s", project, jname, e)

        # Busca logsum só para os finalizados (fora do loop principal, ainda na mesma SSH)
        for job in finalizados:
            try:
                logsum     = _exec_ssh(
                    f"{dshome}/bin/dsjob -logsum {job['project']} {job['job_name']}",
                    timeout=120,
                )
                child_jobs = _parse_child_jobs(logsum)
                job["logsum"]     = logsum
                job["child_jobs"] = child_jobs
            except Exception as e:
                log.warning("[DS Monitor] Erro ao buscar logsum de %s: %s", job["job_name"], e)
                job["logsum"]     = ""
                job["child_jobs"] = []

    finally:
        client.close()
        log.info("[DS Monitor] Conexão SSH encerrada.")

    # ── persiste resultados no banco (batch) ──────────────────────────────────

    mssql_hook = MsSqlHook(mssql_conn_id=mssql_conn_id)

    # Persiste snapshots de jobs ainda RUNNING (via upsert existente)
    running_snaps = [s for s in snapshots if s[7] in (0, 4)]
    for snap in running_snaps:
        exec_id, pipeline, jname, project, wave, pid, status_label, sc, snapshot = snap
        try:
            mssql_hook.run(
                "EXEC dbo.sp_etl_ds_job_log_upsert "
                "@execution_id=%s, @pipeline_name=%s, @job_name=%s, @project=%s, "
                "@wave_number=%s, @pid=%s, @status=%s, @status_code=%s, "
                "@child_jobs=%s, @log_summary=%s, @poll_snapshot=%s",
                parameters=(exec_id, pipeline, jname, project, wave,
                             pid, status_label, sc, "", "", snapshot),
            )
        except Exception as e:
            log.warning("[DS Monitor] Erro ao persistir snapshot de %s: %s", jname, e)

    # Persiste estado final dos jobs finalizados
    for job in finalizados:
        sc         = job["status_code"]
        label      = _status_label(sc)
        logsum     = job.get("logsum", "")
        child_jobs = job.get("child_jobs", [])
        info       = job.get("info", {})
        try:
            mssql_hook.run(
                "EXEC dbo.sp_etl_ds_job_log_upsert "
                "@execution_id=%s, @pipeline_name=%s, @job_name=%s, @project=%s, "
                "@wave_number=%s, @pid=%s, @status=%s, @status_code=%s, "
                "@child_jobs=%s, @log_summary=%s, @poll_snapshot=%s",
                parameters=(
                    job["execution_id"], job["pipeline_name"], job["job_name"],
                    job["project"], info.get("wave_number", 0), info.get("pid", ""),
                    label, sc,
                    json.dumps(child_jobs, ensure_ascii=False) if child_jobs else "",
                    logsum[:8000],
                    "",
                ),
            )
            log.info("[DS Monitor] Job finalizado: %s/%s → %s",
                     job["project"], job["job_name"], label)
        except Exception as e:
            log.warning("[DS Monitor] Erro ao persistir final de %s: %s", job["job_name"], e)

    log.info(
        "[DS Monitor] Ciclo concluído — %d jobs verificados, %d finalizados neste ciclo.",
        len(jobs), len(finalizados),
    )


# ── DAG definition ────────────────────────────────────────────────────────────

def _get_interval() -> int:
    try:
        return max(1, int(Variable.get("MONITOR_INTERVAL_MINUTES", default_var="3")))
    except Exception:
        return 3


with DAG(
    dag_id=DAG_ID,
    default_args=default_args,
    schedule_interval=f"*/{_get_interval()} * * * *",
    start_date=pendulum.datetime(2025, 1, 1, tz=LOCAL_TZ),
    catchup=False,
    max_active_runs=1,   # nunca dois ciclos de monitor simultâneos
    tags=["monitor", "datastage", "infra"],
) as dag:

    PythonOperator(
        task_id="monitorar_jobs_datastage",
        python_callable=monitor_jobs,
        execution_timeout=timedelta(minutes=_get_interval() - 1),  # não bloqueia o próximo ciclo
    )
