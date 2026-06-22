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

# Nome de job seguro p/ interpolar no comando dsjob remoto (evita injeção shell)
_SAFE_JOB_RE = re.compile(r"^[A-Za-z0-9_.]+$")


def _abort_decision(children, stuck_since, now, grace_s):
    """Decide se o ABORT de um job filho deve ser propagado ao pai (com carência).

    Compartilhada pelo operador (estado em memória) e pelo monitor central
    (stuck_since persistido em etl_ds_job_log). 'Travado' = há filho ABORTED
    (status_code=3) E NENHUM filho ainda em execução (todos finalizaram) — ou
    seja, a sequence parou de progredir, mas o pai segue RUNNING. Só nesse estado
    o relógio corre; após grace_s segundos travado, propaga.

    Qualquer progresso (um filho voltou a rodar após reset, ou um novo filho
    iniciou) deixa de ser 'travado' e zera o relógio — evita falso-positivo em
    sequences que toleram/recuperam a falha de um filho.

    Retorna (propagate: bool, new_stuck_since: datetime|None, aborted: list[str]).
    """
    aborted     = [c.get("name") for c in children if c.get("status_code") == 3]
    any_running = any(c.get("status_code") is None for c in children)
    travado     = bool(aborted) and not any_running
    if not travado:
        return False, None, aborted
    if stuck_since is None:
        return False, now, aborted            # entrou em 'travado' agora — inicia o relógio
    if (now - stuck_since).total_seconds() >= grace_s:
        return True, stuck_since, aborted     # travado tempo suficiente — propaga
    return False, stuck_since, aborted        # ainda na carência


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
        mirror_child_abort: bool = True,  # espelha DataStage: filho ABORTED → falha o pai
        child_check_interval: int = 2,    # a cada N polls checa filhos ABORTED (pai RUNNING)
        child_abort_grace_s: int = 600,   # carência: só propaga após N s 'travado' (default 10 min)
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
        self.mirror_child_abort   = mirror_child_abort
        self.child_check_interval = max(1, int(child_check_interval))
        self.child_abort_grace_s  = max(0, int(child_abort_grace_s))

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
        abort_stuck_since: datetime | None = None   # carência p/ espelhar ABORT de filho
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
                    self._persist_queued_seconds(execution_id, pipeline, queued_seconds)

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
                # Espelha o DataStage: se um filho do run atual ABORTOU e a sequence
                # parou de progredir (nenhum filho rodando) com o pai ainda RUNNING,
                # propaga o ABORTED APÓS a carência — grava ABORTED (ORQUESTRA) e
                # falha a task (Airflow), em vez de ficar "RUNNING" indefinidamente.
                # Throttle por child_check_interval para limitar a carga de -logsum.
                if (self.mirror_child_abort and sc == self._ST_RUNNING
                        and poll_count % self.child_check_interval == 0):
                    aborted, children, logsum = self._detect_aborted_children()
                    now = datetime.utcnow()
                    propagate, abort_stuck_since, _ = _abort_decision(
                        children, abort_stuck_since, now, self.child_abort_grace_s)
                    if propagate:
                        self.log.error(
                            "[DS] Filho(s) ABORTED e sequence travada >%ds com o pai "
                            "RUNNING — espelhando ABORTED (DataStage): %s",
                            self.child_abort_grace_s, ", ".join(aborted))
                        self._log_child_jobs(children)
                        self._persist(
                            execution_id, pipeline,
                            info.get("wave_number") or wave_num, info.get("pid"),
                            "ABORTED", self._ST_ABORTED, children, logsum, None,
                            ds_start_time=info.get("start_time"),
                            ds_end_time=now,
                        )
                        raise AirflowException(
                            f"[DS] '{self.project}/{self.job_name}': job(s) filho(s) "
                            f"ABORTED e sequence travada (sem progresso) por "
                            f">{self.child_abort_grace_s}s com o pai RUNNING "
                            f"(espelhando DataStage): {', '.join(aborted)}.\n"
                            f"Log summary (2 000 chars):\n{(logsum or '')[:2000]}"
                        )
                    elif aborted and abort_stuck_since is not None:
                        self.log.warning(
                            "[DS] Filho(s) ABORTED (%s) — aguardando carência "
                            "(%ds/%ds) antes de espelhar.", ", ".join(aborted),
                            int((now - abort_stuck_since).total_seconds()),
                            self.child_abort_grace_s)
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

                # Causa frequente: o controller não conseguiu rodar um filho porque
                # ele está em estado inválido (DSRunJob code=-2). Reset do pai não
                # resolve — é preciso resetar o próprio filho.
                stuck = self._badstate_children(logsum)
                cause = ""
                if stuck:
                    self.log.warning(
                        "[DS] Job(s) filho(s) em estado inválido (DSRunJob code=-2): %s", stuck)
                    cause = ("\nCausa provável: job(s) filho(s) em estado inválido "
                             "(DSRunJob code=-2 / 'not in the right state'): "
                             + ", ".join(stuck) + ".")

                if self.attach_only:
                    raise AirflowException(
                        f"[DS] '{self.project}/{self.job_name}' ABORTED.{cause}\n"
                        f"Log summary (2 000 chars):\n{logsum[:2000]}"
                    )

                if ds_attempt < self.max_ds_retries:
                    # Reseta primeiro os filhos travados (o reset do pai não os
                    # desbloqueia), depois o pai, e tenta de novo.
                    for child in stuck:
                        self.log.info("[DS] reset do filho travado '%s' antes do retry", child)
                        self._reset_job(child)
                    self.log.info("[DS] RESET + retry in %ds …", self.retry_wait)
                    self._reset()
                    time.sleep(self.retry_wait)
                    wave_num = self._trigger_run(logical_date)
                    ti.xcom_push(key="ds_wave_num", value=wave_num)
                    continue

                raise AirflowException(
                    f"[DS] '{self.project}/{self.job_name}' ABORTED after "
                    f"{self.max_ds_retries} attempt(s).{cause}\n"
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
        parts += [f"'{self.project}'", f"'{self.job_name}'"]
        cmd = " ".join(parts)

        rc, out, err = self._exec(cmd, timeout=60)
        combined = (out + " " + err).strip()
        self.log.info("[DS] trigger rc=%d | %s", rc, combined[:300])

        # DSJE_BADSTATE (rc=-2): o job está em estado inválido (não "compiled, not
        # running") — sobrou TRAVADO de um run anterior (zumbi / abortado sem reset
        # / lock). RESET + 1 novo disparo auto-recupera; senão a task falharia os
        # 4 retries do Airflow sempre no mesmo erro.
        if rc not in (0, 1) and "BADSTATE" in combined.upper():
            self.log.warning("[DS] disparo recusado (DSJE_BADSTATE) — RESET do job e novo disparo")
            self._reset_job(self.job_name)
            time.sleep(self.retry_wait)
            rc, out, err = self._exec(cmd, timeout=60)
            combined = (out + " " + err).strip()
            self.log.info("[DS] trigger (pós-reset) rc=%d | %s", rc, combined[:300])

        if rc not in (0, 1):
            raise AirflowException(
                f"[DS] Failed to trigger '{self.job_name}': rc={rc} | {combined[:300]}"
            )

        info = self._jobinfo()
        try:
            return int(info.get("wave_number") or 0)
        except (TypeError, ValueError):
            return 0

    def _reset(self) -> None:
        self._reset_job(self.job_name)

    def _reset_job(self, job_name: str) -> None:
        """RESET de um job específico (-run -mode RESET) — devolve ao estado
        'compiled, not running'. Usado no pai e nos filhos travados (code=-2)."""
        if not _SAFE_JOB_RE.match(job_name or ""):
            self.log.warning("[DS] nome de job inseguro p/ reset, ignorado: %r", job_name)
            return
        cmd = f"{self.dshome}/bin/dsjob -run -mode RESET '{self.project}' '{job_name}'"
        rc, out, err = self._exec(cmd, timeout=60)
        self.log.info("[DS] reset '%s' rc=%d | %s", job_name, rc, (out + err).strip()[:200])

    # ── dsjob wrappers ───────────────────────────────────────────────────────

    def _jobinfo(self) -> dict:
        cmd = f"{self.dshome}/bin/dsjob -jobinfo '{self.project}' '{self.job_name}'"
        _, out, _ = self._exec(cmd, timeout=30)
        return self._parse_jobinfo(out)

    def _logsum(self) -> str:
        # -max limita às últimas N entradas (o run atual), evitando puxar o
        # histórico inteiro do job (runs antigos) — isso reduz o tráfego SSH,
        # o tamanho gravado em etl_ds_job_log e o eco no log do Airflow.
        cmd = f"{self.dshome}/bin/dsjob -logsum -max {self.logsum_max} '{self.project}' '{self.job_name}'"
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
        """Extrai os jobs filhos do RUN ATUAL de uma SEQUENCE (dsjob -logsum).

        O -logsum retém várias execuções da sequence (auto-purge guarda N entradas,
        que para sequences pequenas cobrem vários dias). Sem delimitar, o mesmo job
        filho aparece uma vez por run histórico, com status de datas diferentes
        misturados — dando a falsa impressão de 'reset → ok → erro em seguida'.
        Aqui consideramos só os eventos após o ÚLTIMO 'Starting Job' (= run atual).
        """
        batch_re  = re.compile(r"BATCH\s+.*?->\s+\(([^)]+)\):\s+Job run requested")
        finish_re = re.compile(r"Job (\S+) has finished,\s*status\s*=\s*(\d+)\s+\(([^)]+)\)")

        lines = self._current_run_lines(logsum)   # só o run atual

        tracked: dict = {}
        result:  list = []

        for line in lines:
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

    def _current_run_lines(self, logsum: str) -> list:
        """Linhas do -logsum referentes ao RUN ATUAL (após o último 'Starting Job').
        O -logsum retém várias execuções; sem isso, eventos antigos vazam."""
        lines = logsum.splitlines()
        last_start = 0
        for i, line in enumerate(lines):
            if re.search(r"\bStarting Job\b", line):
                last_start = i
        return lines[last_start:]

    def _detect_aborted_children(self):
        """Durante o RUNNING do pai, busca o -logsum e devolve os filhos do RUN
        ATUAL que estão ABORTED (status_code=3). Retorna (nomes, children, logsum).

        Best-effort: qualquer erro de SSH/parse devolve ([], [], "") para não
        derrubar o polling — a próxima iteração tenta de novo. Usa o status mais
        recente por filho (via _parse_child_jobs), então um filho que abortou mas
        foi resetado/re-executado com sucesso NÃO é considerado abortado.
        """
        try:
            logsum   = self._logsum()
            children = self._parse_child_jobs(logsum)
        except Exception as exc:
            self.log.debug("[DS] checagem de filho abortado ignorada: %s", exc)
            return [], [], ""
        aborted = [c["name"] for c in children
                   if c.get("status_code") == self._ST_ABORTED]
        return aborted, children, logsum

    def _badstate_children(self, logsum: str) -> list:
        """Jobs filhos que o controller não conseguiu rodar por estarem em estado
        inválido — 'Error calling DSRunJob(<job>), code=-2 [Job is not in the right
        state [compiled and not running]]'. Esses precisam de RESET individual antes
        do retry: o reset do pai NÃO os desbloqueia (é a causa do abort recorrente)."""
        names: list = []
        seen: set = set()
        for line in self._current_run_lines(logsum):
            low = line.lower()
            if "dsrunjob(" not in low:
                continue
            if "code=-2" not in low and "not in the right state" not in low:
                continue
            m = re.search(r"DSRunJob\(([^)]+)\)", line)
            if not m:
                continue
            name = m.group(1).strip()
            if name and name not in seen:
                seen.add(name)
                names.append(name)
        return names

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

    def _persist_queued_seconds(self, execution_id: str, pipeline: str, queued_seconds: int) -> None:
        """Grava o tempo de espera em fila do WM DataStage em etl_ds_job_log.

        Filtra também por pipeline_name: execution_id (derivado de ts_nodash)
        pode colidir entre pipelines distintos agendados no mesmo horário.
        """
        try:
            from airflow.providers.microsoft.mssql.hooks.mssql import MsSqlHook
            hook = MsSqlHook(mssql_conn_id=self.mssql_conn_id)
            hook.run(
                "UPDATE dbo.etl_ds_job_log "
                "SET queued_seconds=%s, updated_at=GETDATE() "
                "WHERE execution_id=%s AND pipeline_name=%s AND job_name=%s",
                parameters=(queued_seconds, execution_id, pipeline, self.job_name),
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
            "ds_status":   ds_label,
            "wave_number": info.get("wave_number"),
            "start_time":  info.get("start_time"),
            "pid":         info.get("pid"),
            "child_jobs":  child_jobs,
            "log_summary": logsum[:3000] if logsum else "",
            # status_code da SEQUENCE por ÚLTIMO de propósito: o extractor legado
            # do log_end (json_m[-1]) pega o ÚLTIMO "status_code" do blob; como os
            # child_jobs também têm "status_code", o da sequence precisa ser o
            # último a aparecer — senão um filho ABORTED faz o pipeline falhar.
            "status_code": xcom_status_code,
        }, ensure_ascii=False)


def _status_label(sc: int) -> str:
    return {0: "RUNNING", 1: "SUCCESS", 2: "WARNING", 3: "ABORTED", 4: "QUEUED"}.get(sc, "UNKNOWN")
