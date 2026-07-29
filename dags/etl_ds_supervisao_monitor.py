"""
etl_ds_supervisao_monitor.py

Coleta da Supervisão de Jobs DataStage (F2 da spec docs/spec-supervisao-ds.md).

O QUE FAZ, a cada ciclo:
  1. Lê os jobs ativos de dbo.etl_ds_supervisao_job.
  2. Abre UMA conexão SSH e roda `dsjob -logsum -max N <projeto> <job>` para cada
     um, em sequência — mesmo padrão de economia do etl_ds_monitor_centralizado.
  3. Segmenta a saída em runs (utils/ds_logsum) e guarda os dos últimos 7 dias
     em dbo.etl_ds_supervisao_run — início e término de cada execução, que é a
     base histórica para sugerir SLA no futuro.
  4. Classifica o dia (utils/ds_supervisao_regras) e grava os eventos em
     dbo.etl_ds_supervisao_evento: ABORTOU, NAO_EXECUTOU, ATRASO, ESTRUTURA e o
     SITUACAO_INICIAL da entrada em vigência.
  5. Uma vez por dia, na janela das 03h, expurga o que passou de 1 ano.

O QUE NÃO FAZ: enviar ao Teams. O envio é a F4 — os eventos ficam com
`notificado_em` nulo esperando por ela. O painel do dashboard é a F3.

IDEMPOTÊNCIA: rodar o mesmo ciclo duas vezes não duplica nada. Runs fazem upsert
pela chave (supervisao_id, run_inicio); eventos entram com INSERT ... WHERE NOT
EXISTS sobre a mesma chave do índice único da migration 062. É isso que permite
reprocessar sem inundar o canal depois.

FALHA ISOLADA: erro num job vira evento ESTRUTURA e o ciclo segue para os
demais. SSH fora do ar gera ESTRUTURA para todos e a task ainda conclui — a DAG
não é o alarme, os eventos são.

CONFIGURAÇÃO (Variables do Airflow, todas com default):
  DS_SUPERVISAO_INTERVAL_MINUTES  (default: 15)
  DS_MONITOR_SSH_CONN_ID          (default: ssh_lnxprd021)   — reusa a do monitor
  DS_MONITOR_MSSQL_CONN_ID        (default: SQL14_DMDB41)
  DS_MONITOR_DSHOME               (default: /opt/IBM/InformationServer/Server/DSEngine)
  DS_SUPERVISAO_RETENCAO_DIAS     (default: 365)
"""
from __future__ import annotations

import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pendulum
from airflow import DAG
from airflow.models import Variable
from airflow.operators.python import PythonOperator

# utils/ é irmão deste arquivo dentro de dags/ — o mesmo import que as outras
# DAGs usam ("from utils.x import y") depende de dags/ estar no sys.path. Com
# guarda para não empilhar entradas a cada parse do scheduler (mesmo cuidado de
# etl_lineage_extract_dsx.py).
_DAGS_DIR = str(Path(__file__).parent)
if _DAGS_DIR not in sys.path:
    sys.path.insert(0, _DAGS_DIR)

from utils.ds_logsum import parse_logsum, runs_desde                      # noqa: E402
from utils.ds_supervisao_regras import (                                  # noqa: E402
    JobSupervisionado, avaliar, evento_estrutura,
)

DAG_ID   = "etl_ds_supervisao_monitor"
LOCAL_TZ = "America/Sao_Paulo"

# Janela de log que interessa: a spec fala em 7 dias de histórico visível.
DIAS_DE_LOG = 7

# Anti shell-injection — mesma allowlist do console e do operador.
_SAFE_DS_RE = re.compile(r"^[A-Za-z0-9_.]+$")

default_args = {
    "owner":           "airflow",
    "depends_on_past": False,
    "retries":         0,
}


def _var(chave: str, default: str) -> str:
    try:
        return Variable.get(chave) or default
    except Exception:
        return default


def _var_int(chave: str, default: int) -> int:
    try:
        return int(_var(chave, str(default)))
    except (TypeError, ValueError):
        return default


# ── Leitura do cadastro ─────────────────────────────────────────────────────

def _carregar_jobs(hook) -> list[JobSupervisionado]:
    linhas = hook.get_records(
        "SELECT id, project, job_name, janela_inicio, janela_fim, tolerancia_min, "
        "       dias_semana, vigencia_inicio, max_linhas, alerta_abortou, "
        "       alerta_nao_executou, alerta_atraso, alerta_estrutura, descricao "
        "FROM dbo.etl_ds_supervisao_job WHERE ativo = 1 "
        "ORDER BY project, job_name")
    jobs: list[JobSupervisionado] = []
    for r in (linhas or []):
        jobs.append(JobSupervisionado(
            id=int(r[0]), project=r[1], job_name=r[2],
            janela_inicio=r[3], janela_fim=r[4], tolerancia_min=int(r[5] or 0),
            dias_semana=r[6], vigencia_inicio=r[7], max_linhas=int(r[8] or 200),
            alerta_abortou=bool(r[9]), alerta_nao_executou=bool(r[10]),
            alerta_atraso=bool(r[11]), alerta_estrutura=bool(r[12]),
            descricao=(r[13] if len(r) > 13 else "") or "",
        ))
    return jobs


def _carregar_mensagens(hook) -> dict[int, dict[str, str]]:
    """Mensagens configuradas por (job, tipo). Ausente → padrão de ds_mensagens.

    Degrada para vazio se a migration 063 ainda não foi aplicada: sem mensagem
    cadastrada o alerta continua saindo com o texto padrão."""
    try:
        linhas = hook.get_records(
            "SELECT supervisao_id, tipo, mensagem FROM dbo.etl_ds_supervisao_mensagem")
    except Exception:
        return {}
    por_job: dict[int, dict[str, str]] = {}
    for r in (linhas or []):
        por_job.setdefault(int(r[0]), {})[r[1]] = r[2]
    return por_job


# ── Gravação ────────────────────────────────────────────────────────────────

def _gravar_runs(cur, supervisao_id: int, runs, job: JobSupervisionado, log) -> int:
    """Upsert dos runs observados. Devolve quantos foram gravados/atualizados.

    A data_ref de cada run é o dia da JANELA a que ele pertence, não o dia do
    calendário em que começou — senão um job de janela 23:00→01:00 apareceria
    ora num dia, ora no outro."""
    from utils.ds_supervisao_regras import janela_do_dia

    gravados = 0
    for run in runs:
        if run.inicio is None:
            continue
        # Descobre a qual data_ref o run pertence: testa o dia dele e o anterior
        # (cobre a janela que atravessa a meia-noite).
        data_ref = run.inicio.date()
        for candidata in (run.inicio.date(), run.inicio.date() - timedelta(days=1)):
            inicio, _fim, _limite = janela_do_dia(job, candidata)
            if inicio <= run.inicio < inicio + timedelta(days=1):
                data_ref = candidata
                break
        try:
            cur.execute(
                "UPDATE dbo.etl_ds_supervisao_run SET "
                "  run_fim = ?, duracao_seg = ?, resultado = ?, jobs_filhos = ?, "
                "  data_ref = ?, coletado_em = GETDATE() "
                "WHERE supervisao_id = ? AND run_inicio = ?",
                (run.fim, run.duracao_seg, run.resultado, run.jobs_filhos,
                 data_ref, supervisao_id, run.inicio))
            if cur.rowcount == 0:
                cur.execute(
                    "INSERT INTO dbo.etl_ds_supervisao_run "
                    "(supervisao_id, data_ref, run_inicio, run_fim, duracao_seg, "
                    " resultado, jobs_filhos) VALUES (?,?,?,?,?,?,?)",
                    (supervisao_id, data_ref, run.inicio, run.fim,
                     run.duracao_seg, run.resultado, run.jobs_filhos))
            gravados += 1
        except Exception as e:
            log.warning("[DS Superv] falha ao gravar run %s de %s: %s",
                        run.inicio, job.rotulo, e)
    return gravados


def _rodou_pelo_orquestra(cur, job: JobSupervisionado, data_ref) -> bool:
    """O job rodou naquele dia segundo a telemetria do próprio Orquestra?

    Rede de segurança contra falso NAO_EXECUTOU: se o log do DataStage rotacionou
    ou o `-max` ficou curto, o run some do logsum — mas se o Orquestra foi quem
    disparou o job, dbo.etl_ds_job_log ainda lembra. Best-effort: qualquer erro
    devolve False e o alerta segue (deixar de avisar é pior que avisar demais)."""
    inicio_dia = datetime.combine(data_ref, datetime.min.time())
    try:
        cur.execute(
            "SELECT TOP 1 1 FROM dbo.etl_ds_job_log "
            "WHERE job_name = ? AND project = ? "
            "  AND created_at >= ? AND created_at < ?",
            (job.job_name, job.project, inicio_dia, inicio_dia + timedelta(days=1)))
        return cur.fetchone() is not None
    except Exception:
        return False


def _gravar_eventos(cur, job: JobSupervisionado, eventos, log,
                    runs=None, mensagens=None, agora=None) -> int:
    """INSERT ... WHERE NOT EXISTS sobre a chave do índice único.

    Sem exceção de chave duplicada e sem card repetido: o ciclo seguinte que
    reencontrar o mesmo problema simplesmente não insere nada.

    A mensagem do alerta é renderizada AQUI, com o contexto do dia em mãos, e
    guardada pronta no evento — o envio (F4) só entrega o texto já montado."""
    from utils.ds_mensagens import montar_mensagem
    from utils.ds_supervisao_regras import NAO_EXECUTOU

    runs = runs or []
    agora = agora or datetime.now()

    novos = 0
    for ev in eventos:
        if ev.tipo == NAO_EXECUTOU and _rodou_pelo_orquestra(cur, job, ev.data_ref):
            log.info("[DS Superv] %s: NAO_EXECUTOU descartado em %s — etl_ds_job_log "
                     "tem execução no dia (log do DataStage provavelmente rotacionou)",
                     job.rotulo, ev.data_ref)
            continue

        # Run que originou o alerta (o abort específico), quando houver.
        origem = next((r for r in runs if r.inicio == ev.run_inicio), None) if ev.run_inicio else None
        try:
            mensagem = montar_mensagem(job, ev.tipo, ev.data_ref, runs, agora,
                                       mensagens=mensagens, run=origem)[:2000]
        except Exception as e:
            # Texto do usuário não pode impedir o registro do alerta.
            log.warning("[DS Superv] falha ao montar mensagem de %s (%s): %s",
                        job.rotulo, ev.tipo, e)
            mensagem = ev.detalhe

        try:
            cur.execute(
                "INSERT INTO dbo.etl_ds_supervisao_evento "
                "(supervisao_id, data_ref, tipo, chave_ocorrencia, detalhe, run_inicio, mensagem) "
                "SELECT ?, ?, ?, ?, ?, ?, ? "
                "WHERE NOT EXISTS (SELECT 1 FROM dbo.etl_ds_supervisao_evento "
                "  WHERE supervisao_id = ? AND data_ref = ? AND tipo = ? AND chave_ocorrencia = ?)",
                (job.id, ev.data_ref, ev.tipo, ev.chave_ocorrencia, ev.detalhe,
                 ev.run_inicio, mensagem,
                 job.id, ev.data_ref, ev.tipo, ev.chave_ocorrencia))
            if cur.rowcount:
                novos += 1
                log.info("[DS Superv] evento %s p/ %s em %s: %s",
                         ev.tipo, job.rotulo, ev.data_ref, ev.detalhe)
        except Exception as e:
            log.warning("[DS Superv] falha ao gravar evento %s de %s: %s",
                        ev.tipo, job.rotulo, e)
    return novos


def _expurgar(cur, dias: int, log) -> None:
    corte = (datetime.now() - timedelta(days=dias)).date()
    for tabela in ("etl_ds_supervisao_run", "etl_ds_supervisao_evento"):
        try:
            cur.execute(f"DELETE FROM dbo.{tabela} WHERE data_ref < ?", (corte,))
            if cur.rowcount:
                log.info("[DS Superv] expurgo: %d linha(s) de %s antes de %s",
                         cur.rowcount, tabela, corte)
        except Exception as e:
            log.warning("[DS Superv] expurgo de %s falhou: %s", tabela, e)


# ── Task principal ──────────────────────────────────────────────────────────

def coletar(**context) -> dict:
    import logging
    log = logging.getLogger("airflow.task")

    from airflow.providers.microsoft.mssql.hooks.mssql import MsSqlHook

    mssql_conn_id = _var("DS_MONITOR_MSSQL_CONN_ID", "SQL14_DMDB41")
    ssh_conn_id   = _var("DS_MONITOR_SSH_CONN_ID", "ssh_lnxprd021")
    dshome        = _var("DS_MONITOR_DSHOME", "/opt/IBM/InformationServer/Server/DSEngine")
    retencao      = _var_int("DS_SUPERVISAO_RETENCAO_DIAS", 365)

    agora = datetime.now()
    hook  = MsSqlHook(mssql_conn_id=mssql_conn_id)

    try:
        jobs = _carregar_jobs(hook)
    except Exception as e:
        log.warning("[DS Superv] cadastro indisponível (migration 062 aplicada?): %s", e)
        return {"jobs": 0, "runs": 0, "eventos": 0}

    if not jobs:
        log.info("[DS Superv] nenhum job supervisionado ativo.")
        return {"jobs": 0, "runs": 0, "eventos": 0}

    mensagens = _carregar_mensagens(hook)

    log.info("[DS Superv] %d job(s) supervisionado(s) — abrindo SSH...", len(jobs))

    from airflow.providers.ssh.hooks.ssh import SSHHook

    saidas: dict[int, tuple[str, str]] = {}   # supervisao_id → (stdout, erro)
    try:
        client = SSHHook(ssh_conn_id=ssh_conn_id).get_conn()
    except Exception as e:
        # SSH fora: todo job vira ESTRUTURA. O ciclo continua até o banco.
        log.warning("[DS Superv] SSH indisponível: %s", e)
        saidas = {j.id: ("", f"SSH indisponível: {e}") for j in jobs}
        client = None

    if client is not None:
        try:
            for job in jobs:
                if not (_SAFE_DS_RE.match(job.project or "")
                        and _SAFE_DS_RE.match(job.job_name or "")):
                    saidas[job.id] = ("", "nome de projeto/job fora do padrão permitido")
                    continue
                maxl = max(1, min(int(job.max_linhas or 200), 2000))
                cmd = (f"source {dshome}/dsenv && {dshome}/bin/dsjob -logsum "
                       f"-max {maxl} {job.project} {job.job_name}")
                try:
                    _, stdout, stderr = client.exec_command(cmd, timeout=120)
                    codigo = stdout.channel.recv_exit_status()
                    saida  = stdout.read().decode(errors="replace")
                    erro   = stderr.read().decode(errors="replace").strip()
                    if codigo != 0:
                        saidas[job.id] = ("", f"dsjob retornou {codigo}: {erro or 'sem detalhe'}"[:400])
                    elif not saida.strip():
                        saidas[job.id] = ("", "logsum vazio — job existe no projeto?")
                    else:
                        saidas[job.id] = (saida, "")
                except Exception as e:
                    saidas[job.id] = ("", f"falha ao executar dsjob: {e}"[:400])
        finally:
            client.close()
            log.info("[DS Superv] conexão SSH encerrada.")

    # ── persistência ────────────────────────────────────────────────────────
    limite_log = agora - timedelta(days=DIAS_DE_LOG)
    total_runs = total_eventos = com_falha = 0

    conn = hook.get_conn()
    cur  = conn.cursor()
    try:
        for job in jobs:
            saida, erro = saidas.get(job.id, ("", "job não consultado neste ciclo"))

            msgs = mensagens.get(job.id, {})

            if erro:
                com_falha += 1
                if job.alerta_estrutura:
                    total_eventos += _gravar_eventos(
                        cur, job, [evento_estrutura(job, agora.date(), erro)], log,
                        runs=[], mensagens=msgs, agora=agora)
                else:
                    log.info("[DS Superv] %s: falha de estrutura silenciada por configuração (%s)",
                             job.rotulo, erro)
                continue

            runs = runs_desde(parse_logsum(saida), limite_log)
            total_runs += _gravar_runs(cur, job.id, runs, job, log)
            total_eventos += _gravar_eventos(cur, job, avaliar(job, runs, agora), log,
                                             runs=runs, mensagens=msgs, agora=agora)

        # Expurgo uma vez por dia, na primeira passagem depois das 03h.
        intervalo = _var_int("DS_SUPERVISAO_INTERVAL_MINUTES", 15)
        if agora.hour == 3 and agora.minute < intervalo:
            _expurgar(cur, retencao, log)

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close(); conn.close()

    log.info("[DS Superv] ciclo concluído: %d job(s), %d run(s), %d evento(s) novo(s), "
             "%d falha(s) de leitura.", len(jobs), total_runs, total_eventos, com_falha)
    return {"jobs": len(jobs), "runs": total_runs,
            "eventos": total_eventos, "falhas": com_falha}


_INTERVALO = _var_int("DS_SUPERVISAO_INTERVAL_MINUTES", 15)

with DAG(
    dag_id=DAG_ID,
    default_args=default_args,
    description="Supervisão DataStage: coleta o logsum dos jobs cadastrados e classifica o dia",
    schedule=f"*/{_INTERVALO} * * * *",
    start_date=pendulum.datetime(2026, 7, 1, tz=LOCAL_TZ),
    catchup=False,
    max_active_runs=1,          # ciclos não podem se atropelar na mesma SSH
    tags=["datastage", "supervisao", "monitoramento"],
) as dag:
    PythonOperator(
        task_id="coletar",
        python_callable=coletar,
    )
