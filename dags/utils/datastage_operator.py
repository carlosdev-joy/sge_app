"""
utils/datastage_operator.py

Async DataStage operator for Apache Airflow 2.x.

Features:
  - Idempotent trigger: attaches to an already-running job on Airflow restart
  - Real-time polling via dsjob -jobinfo (no blocking -wait flag)
  - Full log capture via dsjob -logsum on completion or failure only
  - Child job visibility for SEQUENCE type jobs (BATCH/finish events)
  - Auto RESET + retry on ABORTED status (up to max_ds_retries)
  - Optional logical-date parameter for catch-up scheduling correctness
  - DB persistence to etl_ds_job_log via sp_etl_ds_job_log_upsert
  - attach_only mode: monitor an already-running job without triggering
  - XCom JSON output compatible with etl_dag_factory._extract_status_code()
  - Workload queue: criticidade do pipeline é mapeada para a fila de
    execução do DataStage Workload Management via -queue no dsjob -run
    (ALTA/CRÍTICO → HighPriorityJobs · MEDIA/NORMAL → MediumPriorityJobs
     BAIXA → LowPriorityJobs). Sem configuração usa o padrão do projeto.
  - verbose_log: quando True, chama dsjob -logsum a cada verbose_interval
    polls durante a execução para mostrar progresso de jobs filhos
    (SEQUENCE). Default False — use apenas para investigar jobs específicos.
    Pode ser ativado regenerando a DAG via factory sem alterar a malha.

dsjob -jobinfo "Job Status" codes:
   0 = RUNNING
   1 = Finished OK
   2 = Finished with warnings
   3 = Aborted
   4 = Queued
  99 = Not running
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime

from airflow.exceptions import AirflowException
from airflow.models import BaseOperator
from airflow.providers.ssh.hooks.ssh import SSHHook


class DataStageOperator(BaseOperator):
    """
    Triggers (or attaches to) a DataStage job asynchronously over SSH via dsjob CLI
    and polls until completion.  Works for SEQUENCE and regular ETL jobs.

    Set attach_only=True to monitor a job that was triggered externally (e.g. the
    etl_datastage_monitor DAG) without starting a new run.

    Set verbose_log=True to enable intermediate dsjob -logsum calls during execution
    (useful for diagnosing slow SEQUENCE jobs). Off by default to minimize SSH load.

    XCom return value is a JSON string with:
        system, project, job, status, status_code, wave_number,
        start_time, pid, child_jobs, log_summary

    status_code uses the standard dsjob convention (1=OK, 2=WARNING, 3=ABORTED),
    compatible with etl_dag_factory._extract_status_code().
    """

    ui_color   = "#4A90D9"
    ui_fgcolor = "#FFFFFF"

    _ST_RUNNING = 0
    _ST_OK      = 1
    _ST_WARNING = 2
    _ST_ABORTED = 3
    _ST_QUEUED  = 4
    _ST_NOT_RUN = 99

    def __init__(
        self,
        project: str,
        job_name: str,
        ssh_conn_id: str = "ssh_lnxprd021",
        dshome: str = "/opt/IBM/InformationServer/Server/DSEngine",
        poll_interval: int = 60,
        max_ds_retries: int = 3,
        retry_wait: int = 60,
        execution_date_param: str | None = None,
        attach_only: bool = False,
        mssql_conn_id: str = "SQL14_DMDB41",
        pipeline_name: str = "",
        queue_name: str | None = None,
        verbose_log: bool = False,
        verbose_interval: int = 5,   # chama -logsum a cada N polls (só com verbose_log=True)
        logsum_max: int = 200,       # nº máx. de entradas no -logsum (limita ao run atual)
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.project              = project
        self.job_name             = job_name
        self.ssh_conn_id          = ssh_conn_id
        self.dshome               = dshome
        self.poll_interval        = poll_interval
        self.max_ds_retries       = max_ds_retries
        self.retry_wait           = retry_wait
        self.execution_date_param = execution_date_param
        self.attach_only          = attach_only
        self.mssql_conn_id        = mssql_conn_id
        self.pipeline_name        = pipeline_name
        self.queue_name           = queue_name    # DS Workload Management queue
        self.verbose_log          = verbose_log   # logsum periódico durante execução
        self.verbose_interval     = verbose_interval
        self.logsum_max           = logsum_max     # limita -logsum ao run atual

    # ── entry point ──────────────────────────────────────────────────────────

    def execute(self, context: dict) -> str:
        ti           = context["ti"]
        logical_date = context["ds"]
        execution_id = context["ts_nodash"]
        pipeline     = self.pipeline_name or context["dag"].dag_id

        if self.attach_only:
            # Monitor mode: attach to whatever is running, don't trigger
            info = self._jobinfo()
            if info["status_code"] != self._ST_RUNNING:
                self.log.warning(
                    "[DS] attach_only=True but job is not RUNNING (status=%s). "
                    "Will still poll for final state.", info["status_code"]
                )
            wave_num = info.get("wave_number", 0)
            self.log.info("[DS] Attached to job (wave=%s)", wave_num)
        else:
            wave_num = ti.xcom_pull(key="ds_wave_num", task_ids=ti.task_id)
            if wave_num is not None:
                self.log.info("[DS] Resuming from XCom wave_num=%s", wave_num)
            else:
                wave_num = self._trigger_or_attach(logical_date)
                ti.xcom_push(key="ds_wave_num", value=wave_num)
                self.log.info("[DS] Job triggered — wave_num=%s", wave_num)

        # Persist initial state to DB
        self._persist(execution_id, pipeline, wave_num, None, "QUEUED", self._ST_QUEUED, [], "", None)

        if self.verbose_log:
            self.log.info("[DS] verbose_log=True — logsum parcial a cada %d polls", self.verbose_interval)

        # Polling loop — cada iteração faz apenas dsjob -jobinfo (leve).
        # dsjob -logsum (pesado) só é chamado em: estado terminal, ABORTED,
        # ou verbose_log=True (para investigação pontual de jobs específicos).
        ds_attempt      = 0
        poll_count      = 0
        queued_since: datetime | None = datetime.utcnow()
        queued_seconds: int = 0
        while True:
            time.sleep(self.poll_interval)
            poll_count += 1
            info = self._jobinfo()
            sc   = info["status_code"]
            self.log.info(
                "[DS] wave=%s  status=%s(%s)  controller=%s",
                info.get("wave_number"), sc, info.get("status_text"),
                info.get("controller"),
            )

            # Detecta transição QUEUED → RUNNING: registra tempo de espera em fila
            if sc != self._ST_QUEUED and queued_since is not None:
                queued_seconds = int((datetime.utcnow() - queued_since).total_seconds())
                queued_since   = None
                if queued_seconds > 0:
                    self.log.info("[DS] Tempo em fila: %ds", queued_seconds)
                    self._persist_queued_seconds(execution_id, queued_seconds)

            # Logsum parcial: só com verbose_log=True — opt-in por job/DAG
            if self.verbose_log and sc == self._ST_RUNNING and poll_count % self.verbose_interval == 0:
                try:
                    partial_logsum   = self._logsum()
                    partial_children = self._parse_child_jobs(partial_logsum)
                    if partial_children:
                        self.log.info("[DS][verbose] Progresso — %d job(s) filhos:", len(partial_children))
                        self._log_child_jobs(partial_children)
                except Exception as exc:
                    self.log.debug("[DS][verbose] logsum parcial ignorado: %s", exc)

            # Snapshot de poll (só status_code + text — sem logsum)
            snapshot = json.dumps({
                "ts": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
                "status_code": sc,
                "status_text": info.get("status_text", ""),
            }, ensure_ascii=False)
            self._persist(
                execution_id, pipeline, info.get("wave_number") or wave_num,
                info.get("pid"), _status_label(sc), sc, [], "", snapshot,
            )

            if sc in (self._ST_RUNNING, self._ST_QUEUED):
                continue

            if sc in (self._ST_OK, self._ST_WARNING):
                label = "SUCCESS" if sc == self._ST_OK else "WARNING"
                return self._finish(execution_id, pipeline, sc, label, info)

            if sc == self._ST_ABORTED:
                ds_attempt += 1
                self.log.warning("[DS] ABORTED (attempt %d/%d)", ds_attempt, self.max_ds_retries)
                logsum     = self._logsum()   # logsum sempre em ABORTED para diagnóstico
                child_jobs = self._parse_child_jobs(logsum)
                self._log_child_jobs(child_jobs)
                self._persist(
                    execution_id, pipeline, info.get("wave_number") or wave_num,
                    info.get("pid"), "ABORTED", sc, child_jobs, logsum, None,
                )

                if self.attach_only:
                    raise AirflowException(
                        f"[DS] '{self.project}/{self.job_name}' ABORTED.\n"
                        f"Log summary (2 000 chars):\n{logsum[:2000]}"
                    )

                if ds_attempt < self.max_ds_retries:
                    self.log.info("[DS] RESET + retry in %ds …", self.retry_wait)
                    self._reset()
                    time.sleep(self.retry_wait)
                    wave_num = self._trigger_run(logical_date)
                    ti.xcom_push(key="ds_wave_num", value=wave_num)
                    continue

                raise AirflowException(
                    f"[DS] '{self.project}/{self.job_name}' ABORTED after "
                    f"{self.max_ds_retries} attempt(s).\n"
                    f"Log summary (2 000 chars):\n{logsum[:2000]}"
                )

            if sc == self._ST_NOT_RUN:
                raise AirflowException(
                    f"[DS] '{self.project}/{self.job_name}' is NOT RUNNING unexpectedly "
                    f"(wave {wave_num}). Check DataStage logs."
                )

            raise AirflowException(f"[DS] Unknown status code {sc} for '{self.job_name}'")

    # ── trigger / attach ─────────────────────────────────────────────────────

    def _trigger_or_attach(self, logical_date: str) -> int:
        info = self._jobinfo()
        if info["status_code"] == self._ST_RUNNING:
            self.log.info(
                "[DS] Already RUNNING (wave=%s) — attaching", info.get("wave_number")
            )
            try:
                return int(info["wave_number"])
            except (TypeError, ValueError):
                return 0
        return self._trigger_run(logical_date)

    def _trigger_run(self, logical_date: str) -> int:
        # dsjob requer todas as flags ANTES de project/job
        parts = [f"{self.dshome}/bin/dsjob", "-run", "-mode", "NORMAL"]
        if self.queue_name:
            parts += ["-queue", self.queue_name]
        if self.execution_date_param and logical_date:
            parts += ["-param", f"{self.execution_date_param}={logical_date}"]
        parts += [self.project, self.job_name]

        rc, out, err = self._exec(" ".join(parts), timeout=60)
        combined = (out + " " + err).strip()
        self.log.info("[DS] trigger rc=%d | %s", rc, combined[:300])

        if rc not in (0, 1):
            raise AirflowException(
                f"[DS] Failed to trigger '{self.job_name}': rc={rc} | {err[:300]}"
            )

        info = self._jobinfo()
        try:
            return int(info.get("wave_number") or 0)
        except (TypeError, ValueError):
            return 0

    def _reset(self) -> None:
        cmd = f"{self.dshome}/bin/dsjob -run -mode RESET {self.project} {self.job_name}"
        rc, out, err = self._exec(cmd, timeout=60)
        self.log.info("[DS] reset rc=%d | %s", rc, (out + err).strip()[:200])

    # ── dsjob wrappers ───────────────────────────────────────────────────────

    def _jobinfo(self) -> dict:
        cmd = f"{self.dshome}/bin/dsjob -jobinfo {self.project} {self.job_name}"
        _, out, _ = self._exec(cmd, timeout=30)
        return self._parse_jobinfo(out)

    def _logsum(self) -> str:
        # -max limita às últimas N entradas (o run atual), evitando puxar o
        # histórico inteiro do job (runs antigos) — isso reduz o tráfego SSH,
        # o tamanho gravado em etl_ds_job_log e o eco no log do Airflow.
        cmd = f"{self.dshome}/bin/dsjob -logsum -max {self.logsum_max} {self.project} {self.job_name}"
        _, out, _ = self._exec(cmd, timeout=120)
        return out

    # ── SSH execution ────────────────────────────────────────────────────────

    def _exec(self, cmd: str, timeout: int = 120):
        full_cmd = f"source {self.dshome}/dsenv && {cmd}"
        hook   = SSHHook(ssh_conn_id=self.ssh_conn_id)
        client = hook.get_conn()
        try:
            _, stdout, stderr = client.exec_command(full_cmd, timeout=timeout)
            exit_code = stdout.channel.recv_exit_status()
            out = stdout.read().decode(errors="replace").strip()
            err = stderr.read().decode(errors="replace").strip()
        finally:
            client.close()
        return exit_code, out, err

    # ── parsers ──────────────────────────────────────────────────────────────

    def _parse_jobinfo(self, output: str) -> dict:
        fields: dict = {}
        for line in output.splitlines():
            if ":" in line:
                key, _, val = line.partition(":")
                fields[key.strip()] = val.strip()

        status_line = fields.get("Job Status", "")
        m = re.search(r"\((\d+)\)", status_line)
        status_code = int(m.group(1)) if m else self._ST_NOT_RUN

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

    def _parse_child_jobs(self, logsum: str) -> list:
        """Extract child job events from dsjob -logsum output (SEQUENCE jobs)."""
        batch_re  = re.compile(r"BATCH\s+.*?->\s+\(([^)]+)\):\s+Job run requested")
        finish_re = re.compile(r"Job (\S+) has finished,\s*status\s*=\s*(\d+)\s+\(([^)]+)\)")

        tracked: dict = {}
        result:  list = []

        for line in logsum.splitlines():
            m = batch_re.search(line)
            if m:
                name  = m.group(1)
                entry = {"name": name, "status": "RUNNING", "status_code": None}
                tracked[name] = entry
                result.append(entry)
                continue

            m = finish_re.search(line)
            if m:
                name = m.group(1)
                sc   = int(m.group(2))
                text = m.group(3)
                if name in tracked:
                    tracked[name]["status"]      = text
                    tracked[name]["status_code"] = sc
                else:
                    result.append({"name": name, "status": text, "status_code": sc})

        return result

    def _log_child_jobs(self, child_jobs: list) -> None:
        if not child_jobs:
            return
        self.log.info("[DS] Child jobs (%d):", len(child_jobs))
        for cj in child_jobs:
            icon = {"1": "OK", "2": "WARN", "3": "FAIL"}.get(
                str(cj.get("status_code")), "..."
            )
            self.log.info("  [%s] %-50s  %s", icon, cj["name"], cj.get("status", ""))

    # ── DB persistence ────────────────────────────────────────────────────────

    def _persist_queued_seconds(self, execution_id: str, queued_seconds: int) -> None:
        """Grava o tempo de espera em fila do WM DataStage em etl_ds_job_log."""
        try:
            from airflow.providers.microsoft.mssql.hooks.mssql import MsSqlHook
            hook = MsSqlHook(mssql_conn_id=self.mssql_conn_id)
            hook.run(
                "UPDATE dbo.etl_ds_job_log "
                "SET queued_seconds=%s, updated_at=GETDATE() "
                "WHERE execution_id=%s AND job_name=%s",
                parameters=(queued_seconds, execution_id, self.job_name),
            )
        except Exception as exc:
            self.log.warning("[DS] Não foi possível gravar queued_seconds: %s", exc)

    def _persist(
        self, execution_id, pipeline, wave_num, pid, status, status_code,
        child_jobs, log_summary, poll_snapshot,
        ds_start_time=None, ds_end_time=None,
    ) -> None:
        try:
            from airflow.providers.microsoft.mssql.hooks.mssql import MsSqlHook
            hook = MsSqlHook(mssql_conn_id=self.mssql_conn_id)
            hook.run(
                "EXEC dbo.sp_etl_ds_job_log_upsert "
                "@execution_id=%s, @pipeline_name=%s, @job_name=%s, @project=%s, "
                "@wave_number=%s, @pid=%s, @status=%s, @status_code=%s, "
                "@child_jobs=%s, @log_summary=%s, @poll_snapshot=%s, "
                "@ds_start_time=%s, @ds_end_time=%s",
                parameters=(
                    execution_id,
                    pipeline,
                    self.job_name,
                    self.project,
                    wave_num,
                    pid or "",
                    status,
                    status_code,
                    json.dumps(child_jobs, ensure_ascii=False) if child_jobs else "",
                    (log_summary or "")[:8000],
                    poll_snapshot or "",
                    ds_start_time or "",
                    ds_end_time,
                ),
            )
        except Exception as exc:
            self.log.warning("[DS] Could not persist to etl_ds_job_log: %s", exc)

    # ── finish ────────────────────────────────────────────────────────────────

    def _finish(self, execution_id, pipeline, status_code, label, info) -> str:
        logsum     = self._logsum()   # uma única chamada -logsum, ao terminar
        child_jobs = self._parse_child_jobs(logsum)
        self.log.info("[DS] %s — %d child job(s)", label, len(child_jobs))
        self._log_child_jobs(child_jobs)

        # Para WARNING: grava o detalhe real no DS log, mas reporta SUCCESS
        # ao Airflow/factory (job finalizou — só teve avisos, não falhou)
        ds_label = "Finished with warnings" if label == "WARNING" else label
        xcom_status_code = 1  # SUCCESS para o factory em ambos OK e WARNING
        if label not in ("SUCCESS", "WARNING"):
            xcom_status_code = status_code

        ds_end_time = datetime.utcnow()

        self._persist(
            execution_id, pipeline,
            info.get("wave_number"), info.get("pid"),
            ds_label, status_code, child_jobs, logsum, None,
            ds_start_time=info.get("start_time"),
            ds_end_time=ds_end_time,
        )

        return json.dumps({
            "system":      "datastage",
            "project":     self.project,
            "job":         self.job_name,
            "status":      "SUCCESS",
            "status_code": xcom_status_code,
            "ds_status":   ds_label,
            "wave_number": info.get("wave_number"),
            "start_time":  info.get("start_time"),
            "pid":         info.get("pid"),
            "child_jobs":  child_jobs,
            "log_summary": logsum[:3000] if logsum else "",
        }, ensure_ascii=False)


def _status_label(sc: int) -> str:
    return {0: "RUNNING", 1: "SUCCESS", 2: "WARNING", 3: "ABORTED", 4: "QUEUED"}.get(sc, "UNKNOWN")
