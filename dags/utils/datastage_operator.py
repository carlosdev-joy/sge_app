"""
utils/datastage_operator.py

Async DataStage operator for Apache Airflow 2.x.

Replaces the SSHOperator + run_datastage_job.sh shell script with a Python
implementation that provides:
  - Idempotent trigger: attaches to an already-running job on Airflow restart
  - Real-time polling via dsjob -jobinfo (no blocking -wait flag)
  - Full log capture via dsjob -logsum on completion or failure
  - Child job visibility for SEQUENCE type jobs (BATCH/finish events)
  - Auto RESET + retry on ABORTED status (up to max_ds_retries)
  - Optional logical-date parameter for catch-up scheduling correctness
  - XCom JSON output compatible with etl_dag_factory._extract_status_code()

SSH connection (default: ssh_lnxprd021) must point to the DataStage engine server.
dsjob user on the remote host must have access to the target project.

dsjob -jobinfo "Job Status" codes:
   0 = RUNNING
   1 = Finished OK
   2 = Finished with warnings
   3 = Aborted
  99 = Not running
"""

from __future__ import annotations

import json
import re
import time

from airflow.exceptions import AirflowException
from airflow.models import BaseOperator
from airflow.providers.ssh.hooks.ssh import SSHHook


class DataStageOperator(BaseOperator):
    """
    Triggers a DataStage job asynchronously over SSH via dsjob CLI and polls
    until completion.  Works for both SEQUENCE and regular ETL jobs.

    XCom return value is a JSON string with keys:
        system, project, job, status, status_code, wave_number,
        start_time, pid, child_jobs, log_summary

    ``status_code`` uses the standard dsjob convention (1=OK, 2=WARNING, 3=ABORTED)
    which is compatible with ``etl_dag_factory._extract_status_code()``.
    """

    ui_color  = "#4A90D9"
    ui_fgcolor = "#FFFFFF"

    _ST_RUNNING  = 0
    _ST_OK       = 1
    _ST_WARNING  = 2
    _ST_ABORTED  = 3
    _ST_NOT_RUN  = 99

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
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.project             = project
        self.job_name            = job_name
        self.ssh_conn_id         = ssh_conn_id
        self.dshome              = dshome
        self.poll_interval       = poll_interval
        self.max_ds_retries      = max_ds_retries
        self.retry_wait          = retry_wait
        self.execution_date_param = execution_date_param

    # ── entry point ──────────────────────────────────────────────────────────

    def execute(self, context: dict) -> str:
        ti           = context["ti"]
        logical_date = context["ds"]  # Airflow logical date string (YYYY-MM-DD)

        # Idempotency: if a previous attempt already triggered a run, reuse it
        wave_num = ti.xcom_pull(key="ds_wave_num", task_ids=ti.task_id)
        if wave_num is not None:
            self.log.info("[DS] Resuming from XCom wave_num=%s", wave_num)
        else:
            wave_num = self._trigger_or_attach(logical_date)
            ti.xcom_push(key="ds_wave_num", value=wave_num)
            self.log.info("[DS] Job triggered — wave_num=%s", wave_num)

        # Polling loop
        ds_attempt = 0
        while True:
            time.sleep(self.poll_interval)
            info = self._jobinfo()
            sc   = info["status_code"]
            self.log.info(
                "[DS] wave=%s  status=%s(%s)  controller=%s",
                info.get("wave_number"), sc, info.get("status_text"), info.get("controller"),
            )

            if sc == self._ST_RUNNING:
                continue

            if sc in (self._ST_OK, self._ST_WARNING):
                label = "SUCCESS" if sc == self._ST_OK else "WARNING"
                return self._finish(sc, label, info)

            if sc == self._ST_ABORTED:
                ds_attempt += 1
                self.log.warning("[DS] ABORTED (attempt %d/%d)", ds_attempt, self.max_ds_retries)
                logsum     = self._logsum()
                child_jobs = self._parse_child_jobs(logsum)
                self._log_child_jobs(child_jobs)

                if ds_attempt < self.max_ds_retries:
                    self.log.info("[DS] RESET + retry in %ds …", self.retry_wait)
                    self._reset()
                    time.sleep(self.retry_wait)
                    wave_num = self._trigger_run(logical_date)
                    ti.xcom_push(key="ds_wave_num", value=wave_num)
                    continue

                logsum = self._logsum()
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
                "[DS] Already RUNNING (wave=%s) — attaching without new trigger",
                info.get("wave_number"),
            )
            try:
                return int(info["wave_number"])
            except (TypeError, ValueError):
                return 0
        return self._trigger_run(logical_date)

    def _trigger_run(self, logical_date: str) -> int:
        parts = [
            f"{self.dshome}/bin/dsjob",
            "-run", "-mode", "NORMAL",
            self.project, self.job_name,
        ]
        if self.execution_date_param and logical_date:
            parts += ["-param", f"{self.execution_date_param}={logical_date}"]

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
        cmd = f"{self.dshome}/bin/dsjob -logsum {self.project} {self.job_name}"
        _, out, _ = self._exec(cmd, timeout=120)
        return out

    # ── SSH execution ────────────────────────────────────────────────────────

    def _exec(self, cmd: str, timeout: int = 120):
        """Execute cmd on remote host via SSH, sourcing dsenv first."""
        full_cmd = f"source {self.dshome}/dsenv && {cmd}"
        hook = SSHHook(ssh_conn_id=self.ssh_conn_id)
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
        """
        Extract child job events from dsjob -logsum output.

        SEQUENCE logs include:
          BATCH  SeqName -> (ChildName): Job run requested
          INFO   Job ChildName has finished, status = 1 (Finished OK)
        """
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
            icon = "OK" if cj.get("status_code") == 1 else ("WARN" if cj.get("status_code") == 2 else "FAIL" if cj.get("status_code") == 3 else "...")
            self.log.info("  [%s] %-50s  %s", icon, cj["name"], cj.get("status", ""))

    # ── XCom payload ─────────────────────────────────────────────────────────

    def _finish(self, status_code: int, status_name: str, info: dict) -> str:
        logsum     = self._logsum()
        child_jobs = self._parse_child_jobs(logsum)
        self.log.info("[DS] %s — %d child job(s)", status_name, len(child_jobs))
        self._log_child_jobs(child_jobs)

        payload = {
            "system":      "datastage",
            "project":     self.project,
            "job":         self.job_name,
            "status":      status_name,
            "status_code": status_code,
            "wave_number": info.get("wave_number"),
            "start_time":  info.get("start_time"),
            "pid":         info.get("pid"),
            "child_jobs":  child_jobs,
            "log_summary": logsum[:3000] if logsum else "",
        }
        return json.dumps(payload, ensure_ascii=False)
