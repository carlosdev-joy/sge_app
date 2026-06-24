"""
utils/datastage_operator.py

Async DataStage operator for Apache Airflow 2.x.

Features:
  - Idempotent trigger: attaches to an already-running job on Airflow restart
  - Real-time polling via dsjob -jobinfo (no blocking -wait flag)
  - Full log capture via dsjob -logsum on completion or failure only
  - Child job visibility for SEQUENCE type jobs (BATCH/finish events)
  - Espelha fielmente o status do DataStage (sem RESET/retry — nao manipula o job)
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
                # Espelho puro: enquanto o DataStage disser RUNNING/QUEUED, seguimos
                # RUNNING — sem heurística de filho abortado, sem manipular o job.
                continue

            if sc in (self._ST_OK, self._ST_WARNING):
                label = "SUCCESS" if sc == self._ST_OK else "WARNING"
                return self._finish(execution_id, pipeline, sc, label, info)

            if sc == self._ST_ABORTED:
                # Espelho puro: o DataStage abortou → reportamos ABORTED (FAILED) e
                # paramos. Sem RESET, sem retry, sem re-disparo — não manipulamos o job.
                logsum     = self._logsum()   # logsum para diagnóstico
                child_jobs = self._parse_child_jobs(logsum)
                self._log_child_jobs(child_jobs)
                self._persist(
                    execution_id, pipeline, info.get("wave_number") or wave_num,
                    info.get("pid"), "ABORTED", sc, child_jobs, logsum, None,
                    ds_start_time=info.get("start_time"),
                    ds_end_time=datetime.utcnow(),
                )
                raise AirflowException(
                    f"[DS] '{self.project}/{self.job_name}' ABORTED.\n"
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

        # Espelho puro: não tentamos RESET no BADSTATE. Se o disparo for recusado
        # (job travado de um run anterior), reportamos o erro — não manipulamos o job.
        if rc not in (0, 1):
            raise AirflowException(
                f"[DS] Failed to trigger '{self.job_name}': rc={rc} | {combined[:300]}"
            )

        info = self._jobinfo()
        try:
            return int(info.get("wave_number") or 0)
        except (TypeError, ValueError):
            return 0

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

    def _report_detail(self, job_name: str) -> str:
        """`dsjob -report '<project>' '<job>' DETAIL` — relatório com os
        contadores de linha por link (mesma primitiva read-only do console,
        api/services/ssh_datastage.py 'report'/DETAIL). Best-effort: devolve
        string vazia em qualquer falha (o chamador degrada para rows_out=None)."""
        if not _SAFE_JOB_RE.match(job_name or ""):
            return ""
        cmd = f"{self.dshome}/bin/dsjob -report '{self.project}' '{job_name}' DETAIL"
        try:
            _, out, _ = self._exec(cmd, timeout=60)
            return out or ""
        except Exception as exc:
            self.log.warning("[DS] -report DETAIL falhou para '%s': %s", job_name, exc)
            return ""

    # ── contagem de linhas de saída (rows_out) ────────────────────────────────

    def _rows_out(self, info: dict, child_jobs: list) -> int | None:
        """Linhas de SAÍDA do job (soma dos links de saída). Para SEQUENCE (sem
        links próprios) soma as linhas dos jobs filhos. Best-effort: devolve None
        e loga warning se não der pra obter/parsear — NUNCA falha o job por isso.

        Efeito colateral (best-effort): enriquece cada entrada de ``child_jobs``
        com a chave ``rows`` (int|None) = linhas de SAÍDA daquele filho, obtidas
        do MESMO -report DETAIL usado para somar (sem chamadas SSH extras). Isso
        habilita a decisão por linhas POR FILHO (conditions.linhas_job/child_job).
        Falha aqui nunca falha o job — ``rows`` fica ausente/None."""
        try:
            # Sempre enriquece os filhos com `rows` (mesmo que o job tenha links
            # próprios) — a granularidade por filho é independente do total.
            self._annotate_child_rows(child_jobs)
            total = self._parse_output_rows(self._report_detail(self.job_name))
            if total is not None:
                return total
            # SEQUENCE: sem links próprios → soma os filhos do RUN ATUAL.
            # Reusa o `rows` já anotado em cada filho (sem novo -report DETAIL).
            child_total = 0
            got_any = False
            for cj in child_jobs or []:
                if not isinstance(cj, dict):
                    continue
                sub = cj.get("rows")
                if sub is not None:
                    child_total += sub
                    got_any = True
            if got_any:
                return child_total
            self.log.warning(
                "[DS] rows_out indisponível para '%s' (sem links de saída nem filhos com contagem).",
                self.job_name,
            )
            return None
        except Exception as exc:
            self.log.warning("[DS] rows_out: falha ao obter/parsear (%s) — seguindo sem.", exc)
            return None

    def _annotate_child_rows(self, child_jobs: list) -> None:
        """Anexa a cada filho a chave ``rows`` (int|None) com as linhas de SAÍDA
        daquele filho (uma chamada -report DETAIL por filho — a MESMA que o
        fallback de SEQUENCE já precisaria). Best-effort por filho: qualquer falha
        deixa ``rows=None`` para aquele filho e segue — NUNCA propaga erro."""
        for cj in child_jobs or []:
            if not isinstance(cj, dict):
                continue
            try:
                cname = cj.get("name")
                cj["rows"] = self._parse_output_rows(self._report_detail(cname)) if cname else None
            except Exception as exc:
                self.log.debug("[DS] rows por filho indisponível para '%s': %s",
                               cj.get("name"), exc)
                cj["rows"] = None

    # Saída do dsjob -report DETAIL varia por versão/stage; o relatório lista os
    # links com seu nome e a contagem de linhas. Capturamos os links de SAÍDA
    # (link name + nº de linhas) por padrões tolerantes a rótulos PT/EN.
    _ROWS_OUT_PATTERNS = (
        # "Link 'X' (Output): Rows = 1234"  /  "Output Link 'X': ... Rows: 1234"
        re.compile(r"(?:Output|Sa[ií]da).{0,120}?Rows?(?:\s*Processed)?\s*[:=]\s*([\d,]+)", re.IGNORECASE | re.DOTALL),
        # "Rows = 1234 ... Output"  (ordem invertida em alguns relatórios)
        re.compile(r"Rows?(?:\s*Processed)?\s*[:=]\s*([\d,]+).{0,60}?(?:Output|Sa[ií]da)", re.IGNORECASE | re.DOTALL),
    )

    def _parse_output_rows(self, report: str) -> int | None:
        """Soma as linhas dos links de SAÍDA no `dsjob -report DETAIL`.

        Devolve None quando o relatório não tem nenhum link de saída identificável
        (ex.: SEQUENCE, que não tem stages próprios) — sinaliza ao chamador para
        cair no fallback dos filhos. Devolve 0 quando há link de saída com 0 linhas.

        RISCO: o formato do -report DETAIL muda por VERSÃO do DataStage e por tipo
        de STAGE; os padrões abaixo são tolerantes (rótulos Output/Saída + Rows/
        Rows Processed), mas se a versão local usar outro layout o parser não casa
        e degrada para None (rows_out fica nulo, sem falhar o job)."""
        if not report:
            return None
        total = 0
        matched = False
        seen_spans: set = set()
        for pat in self._ROWS_OUT_PATTERNS:
            for m in pat.finditer(report):
                # Evita contar o mesmo trecho duas vezes via padrões sobrepostos.
                key = (m.start(1), m.end(1))
                if key in seen_spans:
                    continue
                seen_spans.add(key)
                try:
                    total += int(m.group(1).replace(",", ""))
                    matched = True
                except (TypeError, ValueError):
                    continue
        return total if matched else None

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
        ds_start_time=None, ds_end_time=None, rows_out=None,
    ) -> None:
        # Assinatura alinhada à migration 049 de sp_etl_ds_job_log_upsert
        # (@rows_out adicionado; @ds_start_time/@ds_end_time mantidos como
        # opcionais se o proc deployado ainda os expuser). Tentamos primeiro a
        # chamada com timing + rows_out; se o proc não tiver esses parâmetros
        # (versão antiga/nova divergente), caímos para a chamada mínima.
        try:
            from airflow.providers.microsoft.mssql.hooks.mssql import MsSqlHook
            hook = MsSqlHook(mssql_conn_id=self.mssql_conn_id)
        except Exception as exc:
            self.log.warning("[DS] Could not persist to etl_ds_job_log: %s", exc)
            return

        base_params = (
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
        )
        # 1) Tenta a forma completa (timing + rows_out) — proc com ambos os conjuntos.
        try:
            hook.run(
                "EXEC dbo.sp_etl_ds_job_log_upsert "
                "@execution_id=%s, @pipeline_name=%s, @job_name=%s, @project=%s, "
                "@wave_number=%s, @pid=%s, @status=%s, @status_code=%s, "
                "@child_jobs=%s, @log_summary=%s, @poll_snapshot=%s, "
                "@ds_start_time=%s, @ds_end_time=%s, @rows_out=%s",
                parameters=base_params + (ds_start_time or "", ds_end_time, rows_out),
            )
            return
        except Exception as exc:
            self.log.debug("[DS] upsert com timing+rows_out falhou (%s) — tentando rows_out só.", exc)
        # 2) Proc da migration 049 (sem timing): execution_id…poll_snapshot + rows_out.
        try:
            hook.run(
                "EXEC dbo.sp_etl_ds_job_log_upsert "
                "@execution_id=%s, @pipeline_name=%s, @job_name=%s, @project=%s, "
                "@wave_number=%s, @pid=%s, @status=%s, @status_code=%s, "
                "@child_jobs=%s, @log_summary=%s, @poll_snapshot=%s, @rows_out=%s",
                parameters=base_params + (rows_out,),
            )
            return
        except Exception as exc:
            self.log.debug("[DS] upsert com rows_out falhou (%s) — tentando forma mínima.", exc)
        # 3) Forma mínima (proc antigo sem rows_out nem timing) — não perde o log.
        try:
            hook.run(
                "EXEC dbo.sp_etl_ds_job_log_upsert "
                "@execution_id=%s, @pipeline_name=%s, @job_name=%s, @project=%s, "
                "@wave_number=%s, @pid=%s, @status=%s, @status_code=%s, "
                "@child_jobs=%s, @log_summary=%s, @poll_snapshot=%s",
                parameters=base_params,
            )
        except Exception as exc:
            self.log.warning("[DS] Could not persist to etl_ds_job_log: %s", exc)

    # ── finish ────────────────────────────────────────────────────────────────

    def _finish(self, execution_id, pipeline, status_code, label, info) -> str:
        logsum     = self._logsum()   # uma única chamada -logsum, ao terminar
        child_jobs = self._parse_child_jobs(logsum)
        self.log.info("[DS] %s — %d child job(s)", label, len(child_jobs))
        self._log_child_jobs(child_jobs)

        # Espelho puro: reporta o status real do DataStage (1=OK, 2=WARNING). O
        # WARNING é gravado como WARNING e NÃO falha o pipeline (ver _status_from_code).
        ds_label = "Finished with warnings" if label == "WARNING" else label
        xcom_status_code = status_code

        ds_end_time = datetime.utcnow()

        # Linhas de SAÍDA do job (best-effort; None se indisponível — não falha).
        rows_out = self._rows_out(info, child_jobs)
        if rows_out is not None:
            self.log.info("[DS] rows_out (linhas de saída) = %d", rows_out)

        self._persist(
            execution_id, pipeline,
            info.get("wave_number"), info.get("pid"),
            ds_label, status_code, child_jobs, logsum, None,
            ds_start_time=info.get("start_time"),
            ds_end_time=ds_end_time,
            rows_out=rows_out,
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
            "rows_out":    rows_out,
            "log_summary": logsum[:3000] if logsum else "",
            # status_code da SEQUENCE por ÚLTIMO de propósito: o extractor legado
            # do log_end (json_m[-1]) pega o ÚLTIMO "status_code" do blob; como os
            # child_jobs também têm "status_code", o da sequence precisa ser o
            # último a aparecer — senão um filho ABORTED faz o pipeline falhar.
            "status_code": xcom_status_code,
        }, ensure_ascii=False)


def _status_label(sc: int) -> str:
    return {0: "RUNNING", 1: "SUCCESS", 2: "WARNING", 3: "ABORTED", 4: "QUEUED"}.get(sc, "UNKNOWN")
