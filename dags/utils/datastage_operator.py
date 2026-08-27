"""
utils/datastage_operator.py

Async DataStage operator for Apache Airflow 2.x.

Features:
  - Idempotent trigger: attaches to an already-running job on Airflow restart
  - Real-time polling via dsjob -jobinfo (no blocking -wait flag)
  - Full log capture via dsjob -logsum on completion or failure only
  - Diagnóstico no caminho de erro: quando o dsjob recusa o disparo (ou o job
    some/volta com status desconhecido), o log do JOB é anexado à exceção —
    best-effort, nunca substitui o erro original (incidente DSJE_REPERROR)
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

# ── Classificação de erro do dsjob (incidente 2026-08-01) ────────────────────
# O log real de produção dizia apenas "Failed to trigger '<job>'", que soa como
# problema de FILA/disparo. O que aconteceu de verdade foi outra coisa: o job
# NÃO EXISTIA no projeto, porque o DataStage diferencia maiúsculas de minúsculas
# nos nomes de job e o Orquestra tinha cadastrado 'SsdVida…' onde o DataStage
# tem 'SSDVida…'. Pior: o operador já sabia — o `_jobinfo()` roda ANTES do
# trigger e recebeu o MESMO "Cannot find job", mas o parse não tratava job
# inexistente (caía no status 99) e seguia para o disparo. Duas conexões SSH
# antes do erro genérico.
#
# Os padrões abaixo são de TEXTO da saída do dsjob — foi o que o incidente
# comprovou (mensagem + "Status code = -1004"); o de-para de códigos já existe
# em ui-react/src/pages/DsConsole.tsx. Sem categorias inventadas: só entram
# casos com marcador textual reconhecível.
_ERR_JOB_INEXISTENTE = re.compile(
    r"cannot find job|invalid job name|status code\s*=\s*-1004", re.IGNORECASE)
_ERR_PROJETO = re.compile(
    r"failed to open project|cannot open project|project .{0,60}not (?:found|recognised|recognized)"
    r"|invalid project|status code\s*=\s*-1002",
    re.IGNORECASE)
_ERR_ESTADO = re.compile(
    r"badstate|not in the (?:right|correct) state|job is (?:not compiled|being reset)"
    r"|needs? (?:to be )?reset",
    re.IGNORECASE)
# ── Segundo incidente, 2026-08-02 (pipeline TESTE_DS / SsdVidaDimePessoa02Ftp) ─
# O log dizia só:
#     [DS] trigger rc=255 | Error running job
#     Status code = -99 DSJE_REPERROR
# Diferente do de ontem: o job FOI ENCONTRADO (não é "Cannot find job"). O
# DataStage abriu o job e RECUSOU o -run com o erro genérico de repositório
# (DSJE_REPERROR, -99), que por definição não diz o motivo. O motivo real (job
# não compilado, -param que o job não declara, -queue inexistente, run travado,
# permissão) está no LOG DO JOB — que o operator sabe buscar (`_logsum`) e não
# buscava neste caminho. O marcador é confirmável (texto DSJE_REPERROR + código
# -99), então vira categoria própria; o que ela NÃO faz é adivinhar qual das
# causas foi — ela lista as hipóteses e mostra o que o Orquestra enviou.
# `\b` depois de -99 evita casar -999/-9999 (este último é erro de sintaxe do
# próprio dsjob, outra coisa).
_ERR_REPOSITORIO = re.compile(
    r"dsje_reperror|status code\s*=\s*-99\b", re.IGNORECASE)


def _classifica_erro_dsjob(saida: str) -> str | None:
    """Categoria do erro na saída do dsjob: 'job_inexistente' | 'projeto' |
    'estado' | 'repositorio' | None (não reconhecido). Ordem importa: 'Cannot
    find job' é o marcador mais específico e vence; 'repositorio' fica por
    ÚLTIMO porque o -99 é o balde genérico do DataStage — se a saída trouxer
    junto um marcador que diz de fato o que houve (projeto, BADSTATE), esse
    ganha."""
    texto = saida or ""
    if _ERR_JOB_INEXISTENTE.search(texto):
        return "job_inexistente"
    if _ERR_PROJETO.search(texto):
        return "projeto"
    if _ERR_ESTADO.search(texto):
        return "estado"
    if _ERR_REPOSITORIO.search(texto):
        return "repositorio"
    return None


def _prefixo_comum(a: str, b: str) -> int:
    """Tamanho do prefixo comum entre duas strings já normalizadas."""
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    return n


def nomes_parecidos(alvo: str, candidatos, limite: int = 5) -> list:
    """Nomes de ``candidatos`` parecidos com ``alvo``, para a mensagem de erro.

    Prioriza o casamento SEM CAIXA (o caso do incidente: mesma grafia, caixa
    diferente); depois ordena por MAIOR PREFIXO COMUM e, por último, os que
    contêm/estão contidos. Tudo sem caixa. Função pura — só é chamada no
    CAMINHO DE ERRO, então custa zero quando está tudo certo.

    ⚠️ Prefixo COMUM em vez de ``startswith``: o erro real de digitação quase
    nunca deixa um nome como prefixo do outro ('…Cobranca09Inexistente' ×
    '…Cobranca01…'), e a lista saía vazia justo quando era mais útil."""
    alvo_cf = (alvo or "").strip().casefold()
    if not alvo_cf:
        return []
    min_prefixo = min(4, len(alvo_cf))
    exatos, por_prefixo, contidos = [], [], []
    for c in candidatos or []:
        c = (c or "").strip()
        if not c:
            continue
        c_cf = c.casefold()
        if c_cf == alvo_cf:
            exatos.append(c)
            continue
        n = _prefixo_comum(c_cf, alvo_cf)
        if n >= min_prefixo:
            por_prefixo.append((n, c))
        elif alvo_cf in c_cf or c_cf in alvo_cf:
            contidos.append(c)
    por_prefixo.sort(key=lambda t: -t[0])
    return (exatos + [c for _, c in por_prefixo] + contidos)[:limite]


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
                # Best-effort: uma falha do -logsum aqui NÃO pode esconder do
                # operador que o job ABORTOU (o erro de diagnóstico tomaria o
                # lugar do erro real).
                logsum     = self._logsum_seguro()   # logsum para diagnóstico
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
                    + (f"Log summary (2 000 chars):\n{logsum[:2000]}" if logsum
                       else "O DataStage não devolveu log para este job "
                            "(dsjob -logsum vazio ou indisponível).")
                )

            # Os dois ramos abaixo mandavam o operador "conferir o log do
            # DataStage" sem trazer o log — sendo que aqui ele está a uma
            # chamada de distância e o custo é zero (caminho de erro).
            if sc == self._ST_NOT_RUN:
                diag = self._logsum_diagnostico()
                raise AirflowException(
                    f"[DS] '{self.project}/{self.job_name}' is NOT RUNNING unexpectedly "
                    f"(wave {wave_num}). Check DataStage logs."
                    + ("\n" + diag if diag else "")
                )

            diag = self._logsum_diagnostico()
            raise AirflowException(
                f"[DS] Unknown status code {sc} for '{self.job_name}'"
                + ("\n" + diag if diag else "")
            )

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
        # O comando disparado NÃO carrega credencial: usuário/chave vêm da
        # conexão SSH do Airflow (`SSHHook`) e o dsjob autentica pelo dsenv do
        # servidor — o que aparece aqui é dshome, -mode, -queue, -param (data
        # lógica), projeto e job. Pode ir para o log. Mostramos SEMPRE no
        # caminho de erro (é a informação que diz se a fila/param que o
        # Orquestra mandou existe no job) e, no caminho feliz, só com
        # verbose_log — mesma disciplina do -logsum parcial.
        if rc not in (0, 1) or self.verbose_log:
            self.log.info("[DS] comando: %s", cmd)

        # Espelho puro: não tentamos RESET no BADSTATE. Se o disparo for recusado
        # (job travado de um run anterior), reportamos o erro — não manipulamos o job.
        if rc not in (0, 1):
            categoria = _classifica_erro_dsjob(((out or "") + "\n" + (err or "")).strip())
            # Incidente 2026-08-02: quando o disparo é recusado com erro
            # genérico, o motivo real está no log do JOB. Buscamos best-effort,
            # só aqui (custo zero no caminho feliz). Exceção: job inexistente —
            # job que não existe não tem log, e ali o diagnóstico bom é a lista
            # de nomes parecidos (-ljobs), que a mensagem já traz.
            diag = "" if categoria == "job_inexistente" else self._logsum_diagnostico()
            # Primeiro, o motivo VERDADEIRO quando ele é reconhecível (job
            # inexistente / projeto / estado / repositório). Só cai no genérico
            # se a saída não trouxer marcador — aí a mensagem crua é tudo que temos.
            self._falhar_se_erro_dsjob(
                rc, out, err, "disparar o job (dsjob -run)", cmd=cmd, extra=diag)
            generico = (
                f"[DS] Failed to trigger '{self.job_name}': rc={rc} | {combined[:300]}"
                f"\n     Comando: {cmd}"
            )
            raise AirflowException(generico + ("\n" + diag if diag else ""))

        info = self._jobinfo()
        try:
            return int(info.get("wave_number") or 0)
        except (TypeError, ValueError):
            return 0

    # ── dsjob wrappers ───────────────────────────────────────────────────────

    def _jobinfo(self) -> dict:
        cmd = f"{self.dshome}/bin/dsjob -jobinfo '{self.project}' '{self.job_name}'"
        rc, out, err = self._exec(cmd, timeout=30)
        # O -jobinfo roda ANTES do trigger: se o job não existe, o erro aparece
        # AQUI. Antes o parse ignorava a mensagem, devolvia status 99 ("not
        # running") e o operador seguia para o disparo — que falhava com a
        # mensagem genérica "Failed to trigger". Agora falhamos no primeiro
        # ponto em que a informação existe, com o motivo verdadeiro.
        self._falhar_se_erro_dsjob(rc, out, err, "consultar o job (dsjob -jobinfo)")
        return self._parse_jobinfo(out)

    # ── diagnóstico de erro do dsjob ─────────────────────────────────────────

    def _falhar_se_erro_dsjob(self, rc: int, out: str, err: str, acao: str,
                              cmd: str = "", extra: str = "") -> None:
        """Levanta AirflowException com mensagem ESPECÍFICA quando a saída do
        dsjob traz um erro reconhecível. Silencioso (no-op) quando não há
        marcador de erro — inclusive com rc≠0 desconhecido, que segue para o
        tratamento genérico de quem chamou.

        ``cmd``   — comando que foi executado (entra na mensagem; sem credencial).
        ``extra`` — bloco de diagnóstico já pronto (ex.: o log do job), anexado
        no fim. Quem monta o ``extra`` é responsável por ele ser best-effort:
        aqui ele só é concatenado."""
        combinado = ((out or "") + "\n" + (err or "")).strip()
        categoria = _classifica_erro_dsjob(combinado)
        if categoria is None:
            return
        msg = self._mensagem_erro(categoria, acao, rc, combinado, cmd=cmd)
        raise AirflowException(msg + ("\n" + extra if extra else ""))

    def _mensagem_erro(self, categoria: str, acao: str, rc, combinado: str,
                       cmd: str = "") -> str:
        trecho = (combinado or "")[:300]
        if categoria == "job_inexistente":
            linhas = [
                f"[DS] O job '{self.job_name}' NÃO EXISTE no projeto "
                f"'{self.project}' do DataStage (ao {acao}, rc={rc}).",
                "     O DataStage DIFERENCIA maiúsculas de minúsculas nos nomes "
                "de job — o SQL Server, não. Confira a grafia exata cadastrada "
                "na etapa do Orquestra.",
            ]
            parecidos = nomes_parecidos(self.job_name, self._nomes_do_projeto())
            if parecidos:
                linhas.append(
                    "     Nomes parecidos no projeto: " + ", ".join(parecidos))
            linhas.append(f"     Saída do dsjob: {trecho}")
            return "\n".join(linhas)
        if categoria == "projeto":
            return (
                f"[DS] O projeto '{self.project}' não pôde ser aberto no "
                f"DataStage (ao {acao}, rc={rc}) — confira o projeto do pipeline "
                f"e o dsenv de {self.dshome}.\n     Saída do dsjob: {trecho}")
        if categoria == "repositorio":
            # DSJE_REPERROR (-99) é o balde genérico do DataStage: ele NÃO diz o
            # motivo. O que podemos afirmar é o que o marcador garante (o job
            # existe e foi aberto; a execução foi recusada) + o que só o
            # Orquestra sabe: os valores que ELE mandou no comando. Nada de
            # eleger uma causa sem marcador.
            linhas = [
                f"[DS] O DataStage RECUSOU a execução de "
                f"'{self.project}/{self.job_name}' (ao {acao}, rc={rc}).",
                "     O job EXISTE e foi aberto — o erro é o genérico de "
                "repositório do DataStage (DSJE_REPERROR, código -99), que NÃO "
                "informa o motivo. Confira, nesta ordem:",
                "     1) o job está COMPILADO no projeto? (recompile no "
                "Designer e dispare de novo — é a causa mais comum);",
                f"     2) o job declara o parâmetro que o Orquestra enviou? "
                f"{self._descreve_param()}",
                f"     3) a fila do Workload Management existe e está "
                f"habilitada? {self._descreve_fila()}",
                "     4) sobrou run anterior travado, ou falta permissão ao "
                "usuário da conexão SSH sobre o job/projeto.",
            ]
            if cmd:
                linhas.append(f"     Comando: {cmd}")
            linhas.append(f"     Saída do dsjob: {trecho}")
            return "\n".join(linhas)
        # 'estado'
        return (
            f"[DS] O job '{self.project}/{self.job_name}' está em estado que não "
            f"aceita a operação (ao {acao}, rc={rc}) — normalmente é um run "
            "anterior travado/abortado que precisa de RESET no DataStage. "
            "O Orquestra é espelho puro: não damos reset por conta própria.\n"
            f"     Saída do dsjob: {trecho}")

    def _descreve_param(self) -> str:
        """O que o Orquestra manda em -param — informação que só ELE tem."""
        if self.execution_date_param:
            return (f"o Orquestra envia '-param {self.execution_date_param}=<data>' "
                    f"(parâmetro de data lógica da etapa). Se o job não declarar "
                    f"'{self.execution_date_param}', o DataStage recusa o run.")
        return "o Orquestra NÃO envia nenhum -param nesta etapa."

    def _descreve_fila(self) -> str:
        """O que o Orquestra manda em -queue (mapeado da criticidade)."""
        if self.queue_name:
            return (f"o Orquestra envia '-queue {self.queue_name}' (fila derivada "
                    f"da criticidade do pipeline). Se essa fila não existir no "
                    f"Workload Management, o DataStage recusa o run.")
        return "o Orquestra NÃO envia -queue (usa a fila padrão do projeto)."

    def _logsum_seguro(self) -> str:
        """`_logsum()` que NUNCA levanta — devolve '' em qualquer falha. Para os
        ramos em que o logsum é insumo (parse de filhos, persistência) e uma
        falha de diagnóstico não pode substituir o erro real."""
        try:
            return self._logsum() or ""
        except Exception as exc:
            self.log.warning("[DS] -logsum indisponível: %s", exc)
            return ""

    def _logsum_diagnostico(self, limite: int = 2000) -> str:
        """Bloco com o log do JOB (`dsjob -logsum`) para ANEXAR a uma mensagem de
        erro — é onde está o motivo real quando o dsjob devolve erro genérico.

        Best-effort de verdade (mesma disciplina do `_nomes_do_projeto`): se o
        -logsum falhar ou expirar, devolve string VAZIA e o erro ORIGINAL sai
        íntegro — nunca é substituído por um erro de diagnóstico. Se o DataStage
        responder mas sem conteúdo, dizemos isso explicitamente em vez de anexar
        um bloco vazio. Só é chamado no CAMINHO DE ERRO: custo zero quando o
        disparo dá certo."""
        try:
            logsum = self._logsum()
        except Exception as exc:
            self.log.debug("[DS] -logsum para diagnóstico falhou: %s", exc)
            return ""
        texto = (logsum or "").strip()
        if not texto:
            return ("     Log do job: o DataStage não devolveu log para este job "
                    "(dsjob -logsum vazio).")
        # Mesmo teto do ramo ABORTED (2 000 chars) para não inundar o log do Airflow.
        return (f"     Log do job (dsjob -logsum, últimas {self.logsum_max} "
                f"entradas, {limite} chars):\n{texto[:limite]}")

    def _nomes_do_projeto(self) -> list:
        """Nomes de job do projeto (`dsjob -ljobs`). SÓ é chamado no caminho de
        erro — custo zero quando o disparo dá certo. Best-effort: qualquer falha
        devolve lista vazia (a mensagem sai sem a lista de parecidos, nunca
        troca o erro real por um erro de diagnóstico)."""
        try:
            cmd = f"{self.dshome}/bin/dsjob -ljobs '{self.project}'"
            _, out, _ = self._exec(cmd, timeout=30)
            nomes = []
            for raw in (out or "").splitlines():
                linha = raw.strip()
                if (not linha or linha.lower() == "<none>"
                        or re.match(r"^status code\s*=", linha, re.IGNORECASE)
                        or not _SAFE_JOB_RE.match(linha)):
                    continue
                nomes.append(linha)
            return nomes
        except Exception as exc:
            self.log.debug("[DS] -ljobs para diagnóstico falhou: %s", exc)
            return []

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

    # O `dsjob -report ... DETAIL` (formato server clássico) lista cada stage e
    # link com a contagem de linhas, ex.:
    #   Stage: EXT_SEGURADOS_VGAP, 6866540 rows input
    #   Link: LnkSegurados_VGAP, 6866540 rows
    # Capturamos essas contagens (+ layouts alternativos por versão). O formato
    # varia por versão/stage; os padrões são tolerantes (PT/EN).
    _ROWS_OUT_PATTERNS = (
        # "Link: <nome>, 6866540 rows"
        re.compile(r"\bLink:\s.*?,\s*([\d,]+)\s+rows\b", re.IGNORECASE),
        # "Stage: <nome>, 6866540 rows input"  (ou "rows output")
        re.compile(r"\bStage:\s.*?,\s*([\d,]+)\s+rows\b", re.IGNORECASE),
        # Layouts alternativos por versão: "Output ... Rows = N" / "Rows = N ... Output"
        re.compile(r"(?:Output|Sa[ií]da).{0,120}?Rows?(?:\s*Processed)?\s*[:=]\s*([\d,]+)", re.IGNORECASE | re.DOTALL),
        re.compile(r"Rows?(?:\s*Processed)?\s*[:=]\s*([\d,]+).{0,60}?(?:Output|Sa[ií]da)", re.IGNORECASE | re.DOTALL),
    )

    def _parse_output_rows(self, report: str) -> int | None:
        """MAIOR contagem de linhas (stages/links) no `dsjob -report DETAIL`.

        Usa o MÁXIMO, não a soma: num fluxo linear (extract → … → load) cada
        stage/link reporta a MESMA contagem, então somar duplicaria (no relatório
        do usuário, stage 6866540 + link 6866540 daria 13M). O máximo reflete o
        volume processado. Para SEQUENCE, `_rows_out` soma o resultado de cada job
        filho (cada um com seu próprio máximo).

        Devolve None quando o relatório não tem nenhuma contagem identificável
        (ex.: SEQUENCE, sem stages próprios) — sinaliza ao chamador para cair no
        fallback dos filhos.

        RISCO: o formato do -report varia por VERSÃO/stage; os padrões são
        tolerantes, mas se a versão local usar outro layout o parser não casa e
        degrada para None (rows_out nulo, sem falhar o job)."""
        if not report:
            return None
        best: int | None = None
        for pat in self._ROWS_OUT_PATTERNS:
            for m in pat.finditer(report):
                try:
                    val = int(m.group(1).replace(",", ""))
                except (TypeError, ValueError):
                    continue
                best = val if best is None else max(best, val)
        return best

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
