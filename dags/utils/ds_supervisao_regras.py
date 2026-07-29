"""
dags/utils/ds_supervisao_regras.py — regras da supervisão de jobs DataStage.

Decide, a partir dos runs lidos do logsum e do cadastro (migration 062), quais
eventos o dia merece. Módulo PURO: recebe `agora` de fora, não toca banco nem
SSH — é o que permite testar cada regra sem servidor
(tests/test_ds_supervisao_regras.py).

As três decisões que moram aqui:

  • **data_ref é o dia em que a JANELA COMEÇA.** Janela 23:00→01:00 cadastrada na
    segunda pertence à segunda, mesmo que o job rode 00:30 de terça.
  • **ATRASO é o aviso, NAO_EXECUTOU é a confirmação.** Passou o fim da janela
    mais a tolerância sem run → ATRASO. Fechou as 24h do dia sem run →
    NAO_EXECUTOU. Os dois podem existir no mesmo dia: um avisou cedo, o outro
    encerrou o assunto.
  • **SITUACAO_INICIAL sai sempre que a vigência começa**, mesmo sem problema
    algum e mesmo em dia não supervisionado — sua função é o usuário conferir se
    janela, dias e limite de linhas ficaram certos.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from utils.ds_logsum import ABORTADO, EXECUTANDO, OK, DsRun

# Tipos de evento — espelham o CHECK de etl_ds_supervisao_evento (migration 062).
ABORTOU          = "ABORTOU"
NAO_EXECUTOU     = "NAO_EXECUTOU"
ATRASO           = "ATRASO"
ESTRUTURA        = "ESTRUTURA"
SITUACAO_INICIAL = "SITUACAO_INICIAL"

_NOMES_DIA = {1: "seg", 2: "ter", 3: "qua", 4: "qui", 5: "sex", 6: "sáb", 7: "dom"}


@dataclass
class JobSupervisionado:
    """Uma linha de dbo.etl_ds_supervisao_job."""
    id: int
    project: str
    job_name: str
    janela_inicio: time
    janela_fim: time
    tolerancia_min: int
    dias_semana: str
    vigencia_inicio: date
    max_linhas: int = 200
    # Obrigatória desde a migration 063: é o rótulo que dá contexto ao alerta.
    descricao: str = ""
    alerta_abortou: bool = True
    alerta_nao_executou: bool = True
    alerta_atraso: bool = True
    alerta_estrutura: bool = True

    @property
    def rotulo(self) -> str:
        return f"{self.project}.{self.job_name}"


@dataclass
class EventoDetectado:
    """Evento a gravar em dbo.etl_ds_supervisao_evento."""
    tipo: str
    data_ref: date
    chave_ocorrencia: str = ""
    detalhe: str = ""
    run_inicio: datetime | None = None


# ── Janela e dias ───────────────────────────────────────────────────────────

def dias_ativos(csv: str) -> set[int]:
    """'1,2,3' → {1,2,3} (ISO: 1=seg … 7=dom). Lixo é ignorado, não explode."""
    dias: set[int] = set()
    for parte in (csv or "").split(","):
        parte = parte.strip()
        if not parte:
            continue
        try:
            d = int(parte)
        except ValueError:
            continue
        if 1 <= d <= 7:
            dias.add(d)
    return dias


def roda_no_dia(job: JobSupervisionado, data_ref: date) -> bool:
    return data_ref.isoweekday() in dias_ativos(job.dias_semana)


def janela_do_dia(job: JobSupervisionado, data_ref: date) -> tuple[datetime, datetime, datetime]:
    """(início, fim, limite) da janela de `data_ref`.

    Janela que cruza a meia-noite (fim <= início) termina no dia seguinte.
    `limite` é o fim mais a tolerância — é dele que sai o ATRASO."""
    inicio = datetime.combine(data_ref, job.janela_inicio)
    fim = datetime.combine(data_ref, job.janela_fim)
    if fim <= inicio:
        fim += timedelta(days=1)
    return inicio, fim, fim + timedelta(minutes=max(0, job.tolerancia_min))


def datas_candidatas(job: JobSupervisionado, agora: datetime) -> list[date]:
    """Dias que este ciclo deve avaliar, do mais antigo ao mais novo.

    Hoje e ontem: ontem entra porque o NAO_EXECUTOU só se confirma quando as 24h
    do dia fecham, o que costuma acontecer já no dia seguinte."""
    candidatas: list[date] = []
    hoje = agora.date()
    for data_ref in (hoje - timedelta(days=1), hoje):
        if data_ref < job.vigencia_inicio:
            continue
        if not roda_no_dia(job, data_ref):
            continue
        inicio, _fim, _limite = janela_do_dia(job, data_ref)
        if agora < inicio:
            continue          # a janela nem começou — nada a cobrar ainda
        candidatas.append(data_ref)
    return candidatas


def runs_do_dia(job: JobSupervisionado, data_ref: date, runs: list[DsRun]) -> list[DsRun]:
    """Runs atribuídos a `data_ref`: do início da janela até 24h depois.

    A faixa vai além do fim da janela de propósito — job que começou atrasado
    ainda é o run daquele dia, e precisa aparecer como tal."""
    inicio, _fim, _limite = janela_do_dia(job, data_ref)
    corte = inicio + timedelta(days=1)
    return [r for r in runs if r.inicio is not None and inicio <= r.inicio < corte]


# ── Descrição legível (usada no card e no detalhe do evento) ────────────────

def _hm(momento: datetime | None) -> str:
    return momento.strftime("%H:%M") if momento else "—"


def descrever_dia(job: JobSupervisionado, data_ref: date,
                  runs: list[DsRun], agora: datetime) -> str:
    """Frase única com a situação do dia — a mesma que vai no card de validação."""
    if not roda_no_dia(job, data_ref):
        dias = ", ".join(_NOMES_DIA[d] for d in sorted(dias_ativos(job.dias_semana))) or "nenhum dia"
        return f"{data_ref.isoformat()}: job não roda neste dia da semana (configurado para {dias})."

    inicio, fim, limite = janela_do_dia(job, data_ref)
    do_dia = runs_do_dia(job, data_ref, runs)

    if not do_dia:
        if agora < inicio:
            return (f"{data_ref.isoformat()}: janela ainda não começou "
                    f"(prevista para {_hm(inicio)}–{_hm(fim)}).")
        if agora < limite:
            return (f"{data_ref.isoformat()}: ainda não iniciou — dentro da janela "
                    f"{_hm(inicio)}–{_hm(fim)}.")
        return (f"{data_ref.isoformat()}: NÃO iniciou até {_hm(limite)} "
                f"(janela {_hm(inicio)}–{_hm(fim)}).")

    ultimo = do_dia[-1]
    if ultimo.resultado == ABORTADO:
        filhos = f" Jobs abortados: {', '.join(ultimo.filhos_abortados)}." if ultimo.filhos_abortados else ""
        return (f"{data_ref.isoformat()}: ABORTOU — iniciou {_hm(ultimo.inicio)}, "
                f"parou {_hm(ultimo.fim)}.{filhos}")
    if ultimo.resultado == EXECUTANDO:
        return f"{data_ref.isoformat()}: em execução desde {_hm(ultimo.inicio)}."
    if ultimo.resultado == OK:
        dur = ultimo.duracao_seg
        tempo = f" ({dur // 60} min)" if dur is not None else ""
        return (f"{data_ref.isoformat()}: executou {_hm(ultimo.inicio)} → "
                f"{_hm(ultimo.fim)}{tempo}.")
    return f"{data_ref.isoformat()}: run encontrado, resultado indefinido no log."


# ── Classificação ───────────────────────────────────────────────────────────

def avaliar_dia(job: JobSupervisionado, data_ref: date,
                runs: list[DsRun], agora: datetime) -> list[EventoDetectado]:
    """Eventos de alerta de UM dia. Não inclui o card de situação inicial."""
    eventos: list[EventoDetectado] = []
    inicio, fim, limite = janela_do_dia(job, data_ref)
    do_dia = runs_do_dia(job, data_ref, runs)

    if do_dia:
        if job.alerta_abortou:
            for run in do_dia:
                if run.resultado != ABORTADO:
                    continue
                filhos = (f" Jobs abortados: {', '.join(run.filhos_abortados)}."
                          if run.filhos_abortados else "")
                eventos.append(EventoDetectado(
                    tipo=ABORTOU, data_ref=data_ref,
                    # Dois abortos no mesmo dia são ocorrências distintas.
                    chave_ocorrencia=run.inicio.strftime("%Y-%m-%d %H:%M:%S") if run.inicio else "",
                    detalhe=(f"{job.rotulo} abortou: iniciou {_hm(run.inicio)}, "
                             f"parou {_hm(run.fim)}.{filhos}"),
                    run_inicio=run.inicio))
        return eventos

    # Nenhum run no dia.
    if agora < limite:
        return eventos                      # ainda dentro do prazo

    dia_fechado = agora >= inicio + timedelta(days=1)

    if dia_fechado:
        if job.alerta_nao_executou:
            eventos.append(EventoDetectado(
                tipo=NAO_EXECUTOU, data_ref=data_ref,
                detalhe=(f"{job.rotulo} não executou em {data_ref.isoformat()} "
                         f"(janela {_hm(inicio)}–{_hm(fim)}).")))
    elif job.alerta_atraso:
        eventos.append(EventoDetectado(
            tipo=ATRASO, data_ref=data_ref,
            detalhe=(f"{job.rotulo} não iniciou até {_hm(limite)} "
                     f"(janela {_hm(inicio)}–{_hm(fim)}).")))
    return eventos


def evento_situacao_inicial(job: JobSupervisionado, runs: list[DsRun],
                            agora: datetime) -> EventoDetectado | None:
    """Card de validação da entrada em vigência — um por vigência.

    Sai mesmo quando está tudo normal e mesmo em dia não supervisionado: é o
    retorno que diz ao usuário se a configuração ficou como ele quis. A
    repetição é barrada na gravação (índice único da migration 062)."""
    if agora.date() < job.vigencia_inicio:
        return None
    return EventoDetectado(
        tipo=SITUACAO_INICIAL, data_ref=job.vigencia_inicio,
        detalhe=(f"Monitoramento iniciado para {job.rotulo}. "
                 + descrever_dia(job, job.vigencia_inicio, runs, agora)))


def evento_estrutura(job: JobSupervisionado, data_ref: date, motivo: str) -> EventoDetectado:
    """Falha ao LER o job (projeto/job inexistente, SSH fora, exit != 0).

    Categoria própria de propósito: aqui o problema é do cadastro ou do
    ambiente, não do job — tratar como 'abortou' mandaria a operação procurar
    erro no lugar errado."""
    return EventoDetectado(
        tipo=ESTRUTURA, data_ref=data_ref,
        detalhe=f"Não foi possível verificar {job.rotulo}: {motivo}"[:1000])


def avaliar(job: JobSupervisionado, runs: list[DsRun],
            agora: datetime) -> list[EventoDetectado]:
    """Todos os eventos que este ciclo deve gravar para o job."""
    eventos: list[EventoDetectado] = []
    inicial = evento_situacao_inicial(job, runs, agora)
    if inicial:
        eventos.append(inicial)
    for data_ref in datas_candidatas(job, agora):
        eventos.extend(avaliar_dia(job, data_ref, runs, agora))
    return eventos
