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

# Nome de job/projeto seguro para interpolar no comando dsjob remoto (anti shell-injection)
_SAFE_DS_RE = re.compile(r"^[A-Za-z0-9_.]+$")

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
    """Retorna todos os jobs com status RUNNING no banco. Inclui stuck_since
    (carência da migration 040) — degrada para None se a coluna não existir."""
    from airflow.providers.microsoft.mssql.hooks.mssql import MsSqlHook
    hook = MsSqlHook(mssql_conn_id=mssql_conn_id)
    base = ("FROM dbo.etl_ds_job_log WHERE status = 'RUNNING' ORDER BY created_at ASC")
    try:
        rows = hook.get_records(
            "SELECT execution_id, pipeline_name, job_name, project, wave_number, "
            "pid, stuck_since " + base)
        has_stuck = True
    except Exception:
        rows = hook.get_records(
            "SELECT execution_id, pipeline_name, job_name, project, wave_number, pid "
            + base)
        has_stuck = False
    return [
        {
            "execution_id":  r[0], "pipeline_name": r[1],
            "job_name":      r[2], "project":       r[3],
            "wave_number":   r[4], "pid":           r[5],
            "stuck_since":   (r[6] if has_stuck else None),
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


def _current_run_lines(logsum: str) -> list:
    """Linhas do -logsum referentes ao RUN ATUAL (após o último 'Starting Job').
    O -logsum retém várias execuções; sem isso, um ABORTED de run antigo vazaria
    e marcaria o job como abortado por engano."""
    lines = logsum.splitlines()
    last_start = 0
    for i, line in enumerate(lines):
        if re.search(r"\bStarting Job\b", line):
            last_start = i
    return lines[last_start:]


def _parse_child_jobs(logsum: str) -> list:
    batch_re  = re.compile(r"BATCH\s+.*?->\s+\(([^)]+)\):\s+Job run requested")
    finish_re = re.compile(r"Job (\S+) has finished,\s*status\s*=\s*(\d+)\s+\(([^)]+)\)")
    tracked: dict = {}
    result:  list = []
    for line in _current_run_lines(logsum):
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
    try:
        grace_s = max(0, int(_var("DS_ABORT_GRACE_SECONDS", "600")))
    except (TypeError, ValueError):
        grace_s = 600
    # Decisão de carência compartilhada com o operador (fonte única).
    from utils.datastage_operator import _abort_decision

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
    stuck_updates: list[tuple] = []  # (exec_id, pipeline, job_name, stuck_since|None)
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

            # Anti shell-injection: project/job_name vêm da config de pipeline; só
            # interpola no comando remoto se forem nomes seguros.
            if not (_SAFE_DS_RE.match(project or "") and _SAFE_DS_RE.match(jname or "")):
                print(f"[MONITOR] nome inseguro, pulando: project={project!r} job={jname!r}")
                continue

            try:
                out  = _exec_ssh(f"{dshome}/bin/dsjob -jobinfo '{project}' '{jname}'")
                info = _parse_jobinfo(out)
                sc   = info["status_code"]

                snapshot = json.dumps({
                    "ts": ts_now, "status_code": sc,
                    "status_text": info.get("status_text", ""),
                }, ensure_ascii=False)
                snapshots.append((exec_id, pipeline, jname, project,
                                  info.get("wave_number", 0), info.get("pid", ""),
                                  _status_label(sc), sc, snapshot))

                if sc not in (0, 4):  # terminal no PAI → finaliza
                    finalizados.append({**job, "status_code": sc, "info": info})
                elif sc == 0:
                    # Pai RUNNING: espelha o DataStage — se um filho do run atual
                    # ABORTOU e a sequence parou de progredir (nenhum filho rodando),
                    # propaga ABORTED APÓS a carência. Progresso zera o relógio
                    # (stuck_since). Persistido no banco (monitor é stateless).
                    try:
                        # -max limita ao run atual (evita puxar histórico); essa
                        # chamada agora roda para todo job RUNNING a cada ciclo.
                        run_logsum = _exec_ssh(
                            f"{dshome}/bin/dsjob -logsum -max 200 {project} {jname}",
                            timeout=120)
                        children = _parse_child_jobs(run_logsum)
                    except Exception as e:
                        log.warning("[DS Monitor] logsum(running) %s/%s falhou: %s",
                                    project, jname, e)
                        children, run_logsum = [], ""
                    now = datetime.utcnow()
                    propagate, new_stuck, aborted = _abort_decision(
                        children, job.get("stuck_since"), now, grace_s)
                    stuck_updates.append((exec_id, pipeline, jname, new_stuck))
                    if propagate:
                        log.error(
                            "[DS Monitor] %s/%s: filho(s) ABORTED e sequence travada "
                            ">%ds com pai RUNNING — espelhando ABORTED: %s",
                            project, jname, grace_s, ", ".join(aborted))
                        finalizados.append({**job, "status_code": 3, "info": info,
                                            "logsum": run_logsum, "child_jobs": children})
                    elif aborted:
                        log.warning(
                            "[DS Monitor] %s/%s: filho(s) ABORTED (%s) — aguardando "
                            "carência antes de espelhar.", project, jname, ", ".join(aborted))

            except Exception as e:
                log.warning("[DS Monitor] Erro ao consultar %s/%s: %s", project, jname, e)

        # Busca logsum só para os finalizados (fora do loop principal, ainda na mesma
        # SSH). Pula os que já têm logsum (jobs reclassificados como ABORTED por filho
        # com o pai RUNNING já o buscaram acima — evita 2ª chamada -logsum).
        for job in finalizados:
            if "logsum" in job:
                continue
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

    # Persiste snapshots de jobs ainda RUNNING (via upsert existente). Exclui os
    # reclassificados como ABORTED (filho abortado com pai RUNNING) — senão
    # gravaríamos RUNNING e ABORTED para o mesmo job no mesmo ciclo.
    reclass = {(j["execution_id"], j["job_name"]) for j in finalizados}
    running_snaps = [s for s in snapshots
                     if s[7] in (0, 4) and (s[0], s[2]) not in reclass]
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

    # Persiste o relógio de carência (stuck_since) dos jobs RUNNING. Best-effort:
    # se a coluna não existir (migration 040 não aplicada) degrada — o operador
    # continua cobrindo via estado em memória.
    for exec_id, pipeline, jname, new_stuck in stuck_updates:
        try:
            mssql_hook.run(
                "UPDATE dbo.etl_ds_job_log SET stuck_since=%s "
                "WHERE execution_id=%s AND pipeline_name=%s AND job_name=%s",
                parameters=(new_stuck, exec_id, pipeline, jname),
            )
        except Exception as e:
            log.warning("[DS Monitor] stuck_since de %s não persistido (ok se 040 ausente): %s", jname, e)

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
