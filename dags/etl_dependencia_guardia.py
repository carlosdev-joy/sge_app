"""
etl_dependencia_guardia.py

DAG guardiã das dependências entre pipelines — F4 da retomada
(docs/retomada-f4-desenho.md; spec docs/spec-dependencias-pipelines.md §3).

O push (F3) é o caminho principal: pai termina, filho dispara. A guardiã é o
New Day + rede de segurança do Control-M, num ciclo de poucos minutos com UMA
task (`ciclo`) e as responsabilidades EM ORDEM — ordenar cria as linhas que a
rede varre; a rede dispara ANTES de o deadline julgar (senão o ciclo alertaria
a corrida que ele mesmo ia disparar); a divergência lê o que sobrou; o Teams
sai no FIM, em lote (Decisão 1 do desenho):

  1. Fecha o dia anterior (§6): linha aguardando que atravessou um dia
     operacional COMPLETO sem liberar vira NAO_LIBEROU + evento — é o UNTIL
     de dia; nenhuma cascata morre sem aviso (D41).
  2. New Day (§3): ordena a corrida do dia dos dependentes previstos. Datas
     SÓ de calcular(agora, virada do predecessor) — nunca varredura de
     histórico (D45); viradas divergentes viram DATA_DIVERGENTE (Decisão 5).
  3. Rede de segurança (§4): varre as linhas aguardando que EXISTEM —
     liberado() (a MESMA função do push), janela, filho pausado não dispara,
     claim reusado da F3, trigger, devolução em exceção (o ciclo seguinte
     re-tenta: a varredura É o retry do D16/D50). Resgate de reserva órfã
     com tripla guarda (§4.2) E resgate da corrida que COMEÇOU e cujo
     DagRun morreu sem fechar nada (§4.3, F5): `dagrun_timeout` estourado
     pula `registrar_falha`/`flow_close` e deixaria EXECUTANDO para sempre,
     bloqueando todo dependente. Fecha FALHA só com DagRun `failed`; com
     `success` (ou sem DagRun) só ALERTA — a guardiã não inventa verde.
  4. Deadline (§5): hora limite OPT-IN estourada vira evento JANELA_ESTOUROU;
     o pipeline fica PENDENTE — nada falha, nada fecha aqui.
  5. Divergência de execução + PREDECESSOR_FALHOU (§7): só com carimbo
     dentro do dia operacional corrente (D42) / FALHA sem sucesso na data.
  6. Observadores de malha (F14 — docs/malha-componentes-desenho.md §5/§6;
     no desenho de componentes é a "responsabilidade 5, depois do fechamento
     §6 da F4"): nós Notificação/Fim de malhas ATIVAS viram eventos
     MALHA_NOTIFICACAO/MALHA_CONCLUIDA com marcador #no:{id}, na janela fixa
     {D, D-1} do presente — nunca varredura de histórico (D45). Upstream
     vazio ou viradas divergentes pulam com log (Decisão 13); o card do Fim
     é OPT-IN por config (Decisão 14). Nada aqui dispara nem fecha corrida:
     observador observa.
  7. Envio ao Teams (§8): canal derivado da supervisão DataStage, lote por
     ciclo, notificado_em só após 2xx, URL do webhook JAMAIS em log.

ZERO SQL neste arquivo (Decisão 15): toda pergunta ao banco mora em
utils/dependencias.py — o mesmo módulo do push; o predicado de liberação é o
MESMO objeto `liberado()` (paridade por identidade, não por cópia).

Erro em UM pipeline não interrompe o ciclo (try/except por item, D51); o
ciclo INTEIRO quebrado falha a task — a guardiã vermelha é informação, não
vergonha (a única folha do grafo é o próprio ciclo, §1.3). Sem a migration
067 o ciclo encerra limpo com log (D52).

CONFIGURAÇÃO (Variables do Airflow, todas com default; nada derruba o
import — D47):
  DEPENDENCIA_GUARDIA_INTERVAL_MINUTES  (default: 5; válido 1..59)
  DEPENDENCIA_LOTE_NOTIFICACAO          (default: 50; mínimo 1) — cards/ciclo
  DEPENDENCIA_MSSQL_CONN_ID             (default: SQL14_DMDB41)

A DAG nasce pausada onde o Airflow pausa DAGs novas (default da instalação):
despausar é a última etapa do deploy da F4.
"""
from __future__ import annotations

import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path

import pendulum
from airflow import DAG
from airflow.models import Variable
from airflow.operators.python import PythonOperator

# utils/ é irmão deste arquivo dentro de dags/ — com guarda para não empilhar
# entradas a cada parse do scheduler (mesmo cuidado da supervisão).
_DAGS_DIR = str(Path(__file__).parent)
if _DAGS_DIR not in sys.path:
    sys.path.insert(0, _DAGS_DIR)

from utils import dependencias as dep                     # noqa: E402
from utils.data_referencia import calcular                # noqa: E402
# O CANÔNICO da expansão dos nós (F14): a guardiã importa o próprio objeto —
# paridade por IDENTIDADE com o port da API, como a F4 fez com liberado().
from utils.malha_nos import expandir                      # noqa: E402

DAG_ID = "etl_dependencia_guardia"
LOCAL_TZ = "America/Sao_Paulo"

# Janela máxima (dias) de reenvio de eventos ao Teams: consertar um webhook
# não pode despejar semanas de alertas velhos no canal (mesma razão da
# supervisão). Constante de propósito — as Variables desta DAG são só as da
# tabela do desenho §10.
JANELA_NOTIFICACAO_DIAS = 2

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


def _intervalo() -> int:
    """Minutos entre ciclos — D47: Variable ausente, lixo, 0 ou 60 NÃO
    derrubam o import; fora de 1..59 devolve o default 5 (o teto existe
    porque */60 é cron inválido — o clamp que falta no monitor
    centralizado)."""
    try:
        v = int(Variable.get("DEPENDENCIA_GUARDIA_INTERVAL_MINUTES",
                             default_var="5"))
        return v if 1 <= v <= 59 else 5
    except Exception:
        return 5


def _lote_notificacao() -> int:
    try:
        return max(1, int(_var("DEPENDENCIA_LOTE_NOTIFICACAO", "50")))
    except (TypeError, ValueError):
        return 50


def _agora() -> datetime:
    """Relógio de parede LOCAL, naive (§2.1 do desenho): a guardiã é monitor
    do PRESENTE — não tem corrida de negócio própria, então o princípio do
    momento lógico (D10) não se aplica a ela. Naive porque todo carimbo do
    banco (GETDATE()) é naive local; pendulum protege de servidor em UTC."""
    return pendulum.now(LOCAL_TZ).naive()


# ── Costuras com o Airflow (isoladas para teste; nenhuma toca banco) ────────

def _dag_pausada(dag_id: str) -> bool:
    from airflow.models import DagModel
    dm = DagModel.get_dagmodel(dag_id)
    return bool(dm is not None and dm.is_paused)


def _dagrun_existe(dag_id: str, run_id: str) -> bool:
    from airflow.models import DagRun
    return bool(DagRun.find(dag_id=dag_id, run_id=run_id))


# Estados TERMINAIS de DagRun no Airflow. 'queued'/'running' ficam de fora de
# propósito: corrida em andamento não é órfã, e essa é a única distinção que
# separa uma rede de segurança de um assassino de corrida legítima.
DAGRUN_TERMINAIS = ("failed", "success")


def _dagrun_terminado(dag_id: str, run_id: str):
    """``(state, end_date)`` do DagRun, ou ``None`` quando ele não existe.

    ``state`` vem como texto minúsculo (o Airflow devolve enum em algumas
    versões e str em outras); ``end_date`` é naive local, para comparar com o
    relógio de parede da guardiã sem misturar fusos."""
    from airflow.models import DagRun
    runs = DagRun.find(dag_id=dag_id, run_id=run_id)
    if not runs:
        return None
    dr = runs[0]
    estado = getattr(dr, "state", None)
    estado = str(getattr(estado, "value", estado) or "").lower()
    fim = getattr(dr, "end_date", None)
    if fim is not None and getattr(fim, "tzinfo", None) is not None:
        fim = pendulum.instance(fim).in_tz(LOCAL_TZ).naive()
    return (estado, fim)


def _trigger(dag_id: str, run_id: str, conf: dict) -> None:
    # Mesmo caminho de produção do push da F3 (local_client no worker).
    from airflow.api.client.local_client import Client
    Client(None, None).trigger_dag(dag_id=dag_id, run_id=run_id, conf=conf)


# ── Datas (puro; as perguntas ao banco moram no módulo) ─────────────────────

def _iso(valor) -> str:
    return valor.isoformat() if hasattr(valor, "isoformat") else str(valor)


def _rollback(conn) -> None:
    try:
        conn.rollback()
    except Exception:
        pass


def _virada_corrente(agora: datetime, virada: time) -> datetime:
    """O instante do New Day mais recente (início do dia operacional
    corrente) para esta virada."""
    base = agora.date() if agora.time() >= virada else agora.date() - timedelta(days=1)
    return datetime.combine(base, virada)


def _viradas_dos_predecessores(conn, pipeline: str) -> dict:
    """{predecessor: virada efetiva} — quem carimba as datas da corrida é a
    virada do PREDECESSOR (§2.2), nunca a do dependente (herança, F3 §7)."""
    return {p: dep.virada_efetiva(conn, p)
            for p in dep.predecessores_de(conn, pipeline)}


def _virada_de_referencia(viradas) -> time:
    """Uma virada determinística para as âncoras (deadline §5.1, início do
    dia corrente §7.1) quando há mais de um predecessor: a mais cedo.
    Viradas divergentes já têm evento próprio (DATA_DIVERGENTE) — aqui só é
    preciso uma âncora ESTÁVEL entre ciclos."""
    distintas = sorted(set(viradas))
    return distintas[0] if distintas else time(0, 0)


def _candidatos(agora: datetime, viradas) -> list:
    """União ordenada dos candidatos a dia operacional (§2.3) das viradas."""
    candidatos: list = []
    for v in sorted(set(viradas)) or [time(0, 0)]:
        for c in dep.candidatos_dia_operacional(agora, v):
            if c not in candidatos:
                candidatos.append(c)
    candidatos.sort()
    return candidatos


def _dia_operacional_escolhido(agora: datetime, viradas, regras_dia) -> date:
    """Decisão 3 (§2.3): o candidato que passa nas regras de DIA do
    dependente, preferindo o mais antigo (o dia de origem provável) — é o
    dia_operacional que vai no conf do disparo. Nenhum passa → o mais antigo
    mesmo assim: o filho re-julga e decide PULADO honesto (defesa em
    profundidade da F3 §2.2)."""
    candidatos = _candidatos(agora, viradas)
    for c in candidatos:
        ok, _motivo = dep.dia_permitido(regras_dia, c)
        if ok:
            return c
    return candidatos[0]


def _diagnostico(conn, pipeline: str, data_ref) -> str:
    """As três mensagens do D46, testadas NESTA ordem (a ordem errada era o
    D4 — 'nenhum executou' saindo quando todos tinham executado):
      1. liberado          → o disparo é que está falhando;
      2. alguém tem linha  → aguardando os faltantes;
      3. ninguém tem linha → nenhum predecessor executou.
    """
    lib, faltantes = dep.liberado(conn, pipeline, data_ref)
    if lib:
        return "liberado mas sem disparo - verifique DAG/scheduler"
    resumo = dep.resumo_predecessores(conn, pipeline, data_ref)
    if any(resumo.values()):
        return "aguardando: " + ", ".join(str(f) for f in faltantes)
    return f"nenhum predecessor executou em {_iso(data_ref)}"


# ── Responsabilidade 1 — fechar o dia anterior (§6) ─────────────────────────

def _fechar_dia_anterior(conn, agora: datetime, log) -> int:
    """NAO_LIBEROU: fecha as linhas aguardando que atravessaram um dia
    operacional COMPLETO sem liberar. Três guardas, cada uma com dono
    (Decisão 11): idade de um dia inteiro (a cadeia noturna meramente LENTA
    sobrevive — o push das 02:00 ainda adota a linha); liberado() == False
    (linha velha porém LIBERADA vai para a rede, que dispara — rodar
    atrasado é o propósito da feature); sem predecessor EXECUTANDO (pai de
    30h rodando não derruba o filho que o espera). Fechou → evento
    NAO_LIBEROU + card: é o D41 de quem não configurou deadline."""
    fechadas = 0
    for pipeline, data_ref, run_id, criado_em in dep.corridas_aguardando(conn):
        try:
            if criado_em is None:
                continue
            viradas = _viradas_dos_predecessores(conn, pipeline)
            if not viradas:
                continue        # sem predecessor não há dia operacional a fechar
            # A linha precisa ser anterior à virada ANTERIOR por TODOS os
            # relógios envolvidos: o corte mais conservador (min) nunca
            # fecha cedo demais.
            corte = min(_virada_corrente(agora, v) - timedelta(days=1)
                        for v in viradas.values())
            if criado_em >= corte:
                continue
            lib, faltantes = dep.liberado(conn, pipeline, data_ref)
            if lib:
                continue        # liberada velha: disparo (rede), não fechamento
            if any(str(f).startswith(dep.ERRO_CONSULTA) for f in faltantes):
                # "Não consegui perguntar" ≠ "não liberou": fechar TERMINAL
                # com base em erro transitório mataria uma corrida liberada
                # (achado da revisão). Adia para o próximo ciclo.
                log.warning("[GUARDIA] condicao de %s em %s indisponivel — "
                            "fechamento adiado", pipeline, data_ref)
                continue
            resumo = dep.resumo_predecessores(conn, pipeline, data_ref)
            if any("EXECUTANDO" in status for status in resumo.values()):
                continue
            if any(resumo.values()):
                motivo = "aguardando: " + ", ".join(str(f) for f in faltantes)
            else:
                motivo = f"nenhum predecessor executou em {_iso(data_ref)}"
            # Evento e fechamento na MESMA transação (commit único): a antiga
            # ordem fechar→commit→evento perdia o card PARA SEMPRE se a falha
            # caísse entre os dois commits — a detecção consome a própria
            # fonte (a linha sai de AGUARDANDO) e nada re-tenta o evento
            # (achado da revisão). Falhou no meio → rollback dos DOIS e o
            # próximo ciclo repete (gravar_evento é idempotente pela chave).
            dep.gravar_evento(
                conn, pipeline, data_ref, "NAO_LIBEROU",
                f"corrida de {_iso(data_ref)} fechada sem liberar - {motivo}")
            if not dep.fechar_nao_liberou(conn, pipeline, data_ref, run_id, motivo):
                _rollback(conn)  # desfaz o evento junto — outra ponta mexeu
                continue
            conn.commit()
            fechadas += 1
            log.info("[GUARDIA] %s em %s fechada como NAO_LIBEROU: %s",
                     pipeline, data_ref, motivo)
        except Exception as e:
            _rollback(conn)
            log.warning("[GUARDIA] fechamento de %s em %s nao concluido (%s) — "
                        "nada persistido; proximo ciclo repete", pipeline,
                        data_ref, e)
    return fechadas


# ── Responsabilidade 2 — New Day (§3) ───────────────────────────────────────

def _predecessor_esperado(conn, pred: str, candidatos, status_na_data) -> bool:
    """D44: o predecessor conta como esperado se as regras de DIA dele
    aceitam algum candidato OU se ele tem linha na data com
    SUCESSO/EXECUTANDO/FALHA (rodou ou está rodando apesar da agenda — ex.:
    manual). PULADO sozinho NÃO conta: pai pulado em dia não devido não
    cria expectativa (é a linha órfã de fim de semana do D3/N11)."""
    if status_na_data & {"SUCESSO", "EXECUTANDO", "FALHA"}:
        return True
    cfg = dep.config_dependente(conn, pred)
    if cfg is None:
        return False
    return any(dep.dia_permitido(cfg["regras_dia"], c)[0] for c in candidatos)


def _new_day(conn, agora: datetime, log) -> int:
    """Ordena a corrida do dia. Previsto = dia permitido do DEPENDENTE em
    algum candidato E expectativa de TODOS os predecessores (Decisão 4 —
    sábado com pai somente-dias-úteis não cria linha órfã nem alerta; pai
    pulado por blackout em dia devido ordena, e o dia acaba em NAO_LIBEROU:
    QA5/D41 preservado). Datas SÓ de calcular(agora, virada do predecessor)
    — proibida varredura histórica (Decisão 2, D45)."""
    ordenadas = 0
    for filho in dep.dependentes_com_dependencia(conn):
        try:
            cfg = dep.config_dependente(conn, filho)
            if cfg is None:
                log.info("[GUARDIA] %s sem cadastro — ignorado", filho)
                continue
            viradas = _viradas_dos_predecessores(conn, filho)
            if not viradas:
                continue
            # 1) dia do próprio filho, por candidatos (§2.3)
            candidatos = _candidatos(agora, viradas.values())
            if not any(dep.dia_permitido(cfg["regras_dia"], c)[0]
                       for c in candidatos):
                continue    # não é previsto hoje: nada é criado, nada alerta (§5.3)
            # 2) data-alvo: calcular(agora, virada de CADA predecessor)
            datas = {p: calcular(agora, v) for p, v in viradas.items()}
            distintas = sorted(set(datas.values()))
            if len(distintas) > 1:
                # Decisão 5: ordenar criaria corrida que NUNCA fecharia numa
                # data só. Evento chaveado no min (determinístico entre ciclos).
                detalhe = "viradas divergentes: " + ", ".join(
                    f"{p}->{_iso(d)}" for p, d in sorted(datas.items()))
                if dep.gravar_evento(conn, filho, distintas[0],
                                     "DATA_DIVERGENTE", detalhe):
                    log.warning("[GUARDIA] %s não ordenado: %s", filho, detalhe)
                conn.commit()
                continue
            data_ref = distintas[0]
            # 3) expectativa de TODOS os predecessores (D44)
            resumo = dep.resumo_predecessores(conn, filho, data_ref)
            fora = next((p for p in viradas
                         if not _predecessor_esperado(conn, p, candidatos,
                                                      resumo.get(p) or set())),
                        None)
            if fora is not None:
                log.info("[GUARDIA] %s não ordenado em %s: %s fora do dia",
                         filho, data_ref, fora)
                continue
            # 4) ordena — a linha nasce com run_id guardia__* (contrato F2 §1)
            criou = dep.ordenar_corrida(
                conn, filho, data_ref,
                dep.novo_run_id("guardia", data_ref, filho), "guardia")
            conn.commit()
            if criou:
                ordenadas += 1
                log.info("[GUARDIA] corrida de %s em %s ordenada", filho, data_ref)
            # criou == False: já havia corrida — nada se assume (D48)
        except Exception as e:
            _rollback(conn)
            log.warning("[GUARDIA] New Day de %s falhou (%s) — seguindo", filho, e)
    return ordenadas


# ── Responsabilidade 3 — rede de segurança (§4) ─────────────────────────────

def _resgatar_orfas(conn, intervalo: int, log) -> int:
    """§4.2 — o buraco que a devolução da F3 não cobre: worker morto entre
    o commit do claim e o trigger deixa EXECUTANDO sem início para sempre.
    Tripla guarda (Decisão 7): início nulo + idade (as duas no módulo) +
    DagRun inexistente (aqui). DagRun existe (ex.: run queued de filho
    pausado depois do trigger) → a corrida é do Airflow, não se mexe."""
    resgatadas = 0
    idade = max(10, 2 * intervalo)
    for pipeline, data_ref, run_id in dep.reservas_orfas(conn, idade):
        try:
            if _dagrun_existe(pipeline, run_id):
                continue
            if dep.resgatar_reserva(conn, pipeline, data_ref, run_id):
                conn.commit()
                resgatadas += 1
                log.info("[GUARDIA] reserva orfa de %s em %s resgatada",
                         pipeline, data_ref)
        except Exception as e:
            _rollback(conn)
            log.warning("[GUARDIA] resgate de %s em %s falhou (%s) — seguindo",
                        pipeline, data_ref, e)
    return resgatadas


EVENTO_ORFA = "EXECUCAO_ORFA"


def _resgatar_em_execucao(conn, agora: datetime, intervalo: int, log) -> int:
    """§4.3 (F5) — a corrida que COMEÇOU, cujo DagRun já morreu e que ninguém
    fechou. Devolve quantas foram fechadas ou alertadas.

    **Por que a guardiã e não a DAG.** O buraco é justamente o caso em que a
    DAG não roda mais nada: `dagrun_timeout` estourado marca o DagRun FAILED e
    **toda TI não-finalizada como SKIPPED** — `registrar_falha` (ONE_FAILED) e
    `flow_close` (ALL_DONE) são pulados, e ninguém grava FALHA. Não há dentro
    da DAG um lugar que ainda execute; a rede de segurança tem de ser de fora.
    A F5 tornou a rota alcançável **por desenho** (etapa parada no portão
    consome o SLA sem consumir worker), mas ela sempre existiu para qualquer
    morte dura do worker.

    **Três guardas contra falso-positivo**, na ordem em que descartam mais:

      1. `inicio IS NOT NULL` + sem carimbo há mais de `idade` minutos
         (`corridas_em_execucao`) — corrida que acabou de ser tocada não entra;
      2. DagRun em estado **terminal** no Airflow (`failed`/`success`).
         `queued`/`running` — inclusive a corrida PARADA NO PORTÃO da F5, que
         fica `up_for_reschedule` com o DagRun `running` — nunca são tocadas;
      3. o DagRun terminou há mais de `idade` minutos. É a guarda que fecha a
         janela de segundos entre o Airflow marcar o DagRun e o
         `registrar_falha` da própria DAG gravar FALHA: nesse intervalo quem
         fecha é a DAG, como sempre foi.

    **Fecha FALHA só quando o DagRun FALHOU.** DagRun `success` com a corrida
    ainda EXECUTANDO é outro defeito (o `flow_close` não gravou) e a guardiã
    **não inventa verde**: sai o alerta e o conserto é a Finalização Manual,
    a tela que existe para registro órfão. Fechar como falha um pipeline que
    o Airflow diz ter concluído seria a mentira simétrica.

    DagRun inexistente também não fecha: sem o Airflow confirmar o desfecho,
    o que a guardiã sabe é que não sabe — e isso vira alerta, não sentença.
    """
    tocadas = 0
    idade = max(15, 3 * intervalo)
    for pipeline, data_ref, run_id, inicio in dep.corridas_em_execucao(conn, idade):
        try:
            info = _dagrun_terminado(pipeline, run_id)
            if info is None:
                # Sem DagRun não há desfecho para copiar. Alerta e segue: a
                # linha continua bloqueando, e dizer isso é o mínimo honesto.
                if dep.gravar_evento(
                        conn, pipeline, data_ref, EVENTO_ORFA,
                        f"corrida {run_id} em EXECUTANDO desde {_iso(inicio)} "
                        "sem DagRun no Airflow - finalize pela tela de "
                        "Finalizacao Manual"):
                    tocadas += 1
                    log.warning("[GUARDIA] corrida %s de %s sem DagRun — "
                                "alertada", run_id, pipeline)
                conn.commit()
                continue
            estado, fim_dagrun = info
            if estado not in DAGRUN_TERMINAIS:
                continue        # em andamento (inclusive parada no portão)
            if fim_dagrun is not None and \
                    fim_dagrun > agora - timedelta(minutes=idade):
                continue        # a própria DAG ainda pode estar fechando
            if estado == "success":
                # Nunca inventar verde: alerta e Finalização Manual.
                if dep.gravar_evento(
                        conn, pipeline, data_ref, EVENTO_ORFA,
                        f"corrida {run_id} ficou EXECUTANDO apesar de o DagRun "
                        "ter concluido com sucesso - a corrida NAO foi fechada "
                        "automaticamente; use a Finalizacao Manual"):
                    tocadas += 1
                    log.warning("[GUARDIA] corrida %s de %s: DagRun success "
                                "sem fecho — alertada", run_id, pipeline)
                conn.commit()
                continue
            motivo = (f"corrida orfa: DagRun {run_id} terminou como FALHA no "
                      "Airflow sem fechar a execucao (timeout do DagRun ou "
                      "worker interrompido) - fechada pela guardia")
            # Evento e fechamento na MESMA transação, pelo motivo do §6: a
            # detecção consome a própria fonte (a linha sai de EXECUTANDO) e
            # nada re-tentaria o evento perdido.
            dep.gravar_evento(
                conn, pipeline, data_ref, EVENTO_ORFA,
                f"corrida de {_iso(data_ref)} fechada como FALHA - {motivo}")
            if not dep.fechar_orfa_em_execucao(conn, pipeline, data_ref,
                                               run_id, motivo):
                _rollback(conn)   # outra ponta fechou primeiro — o certo
                continue
            conn.commit()
            tocadas += 1
            log.warning("[GUARDIA] corrida orfa de %s em %s fechada como FALHA "
                        "(DagRun %s failed)", pipeline, data_ref, run_id)
        except Exception as e:
            _rollback(conn)
            log.warning("[GUARDIA] orfa em execucao de %s em %s nao tratada "
                        "(%s) — seguindo", pipeline, data_ref, e)
    return tocadas


def _rede_seguranca(conn, agora: datetime, log) -> int:
    """§4.1 — a rede opera SÓ sobre linhas que existem (Decisão 6) e reusa
    claim/devolução da F3 intocados: liberado() (a MESMA função do push) →
    janela (relógio de parede — o 'dispara às 08:00' do D22) → filho
    pausado não dispara (Decisão 8) → claim → trigger → devolução em
    exceção. O ciclo seguinte re-tenta pela mesma varredura: a varredura É
    o retry (D16/D50), sem código novo de retry."""
    disparadas = 0
    for pipeline, data_ref, _run_id, _criado_em in dep.corridas_aguardando(conn):
        try:
            lib, _faltantes = dep.liberado(conn, pipeline, data_ref)
            if not lib:
                continue    # deadline (§5) e divergência (§7) diagnosticam o resto
            cfg = dep.config_dependente(conn, pipeline)
            if cfg is None:
                log.info("[GUARDIA] %s sem cadastro — ignorado", pipeline)
                continue
            janela = cfg.get("nao_iniciar_antes")
            if janela is not None and agora.time() < janela:
                continue    # a linha fica: o primeiro ciclo após a hora dispara (D22)
            if _dag_pausada(pipeline):
                log.info("[GUARDIA] %s pausado — não disparado", pipeline)
                continue    # a linha permanece aguardando; o deadline sabe alertar
            viradas = _viradas_dos_predecessores(conn, pipeline)
            dia_op = _dia_operacional_escolhido(agora, viradas.values(),
                                                cfg["regras_dia"])
            rid_novo = dep.novo_run_id("guardia", data_ref, pipeline)
            ganho = dep.reservar_corrida(conn, pipeline, data_ref, rid_novo,
                                         "guardia")
            conn.commit()   # commit imediato — contrato do claim
            if ganho is None:
                log.info("[GUARDIA] %s já tem corrida em %s — outra ponta venceu",
                         pipeline, data_ref)
                continue    # push × guardiã: exatamente um vence (D18)
            try:
                _trigger(pipeline, ganho,
                         dep.montar_conf(data_ref, dia_op, "guardia"))
                disparadas += 1
                log.info("[GUARDIA] %s disparado: run_id=%s data_ref=%s dia_op=%s",
                         pipeline, ganho, data_ref, dia_op)
            except Exception as e:
                dep.devolver_reserva(conn, pipeline, data_ref, ganho,
                                     veio_de_adocao=(ganho != rid_novo))
                conn.commit()
                log.warning("[GUARDIA] disparo de %s falhou (%s) — reserva "
                            "devolvida; o próximo ciclo re-tenta", pipeline, e)
        except Exception as e:
            _rollback(conn)
            log.warning("[GUARDIA] varredura de %s em %s falhou (%s) — seguindo",
                        pipeline, data_ref, e)
    return disparadas


# ── Responsabilidade 4 — deadline (§5) ──────────────────────────────────────

def _deadline(conn, agora: datetime, log) -> int:
    """Hora limite OPT-IN (NULL = a guardiã NUNCA gera JANELA_ESTOUROU para
    o pipeline — 'sem regra' não é 'regra às 00:00', D35): estourou →
    evento + card e o pipeline fica PENDENTE — a linha continua aguardando,
    nada falha, nada é fechado aqui (o fechamento é do §6, em outro momento
    e por outra regra). Idempotente pela chave do evento (D49). Só avalia
    linhas que EXISTEM: sábado sem malha prevista = zero linhas = zero
    alerta (§5.3)."""
    alertas = 0
    for pipeline, data_ref, _run_id, _criado_em in dep.corridas_aguardando(conn):
        try:
            cfg = dep.config_dependente(conn, pipeline)
            limite = (cfg or {}).get("hora_limite")
            if limite is None:
                continue
            viradas = _viradas_dos_predecessores(conn, pipeline)
            virada = _virada_de_referencia(viradas.values())
            instante = dep.instante_deadline(data_ref, limite, virada)
            if agora < instante:
                continue
            if instante < _virada_corrente(agora, virada):
                # Deadline que ficou no passado (linha de reprocesso de data
                # antiga): log apenas, nunca alerta.
                log.info("[GUARDIA] deadline de %s em %s fora do dia corrente "
                         "— sem alerta", pipeline, data_ref)
                continue
            detalhe = _diagnostico(conn, pipeline, data_ref)
            if dep.gravar_evento(conn, pipeline, data_ref,
                                 "JANELA_ESTOUROU", detalhe):
                alertas += 1
                log.warning("[GUARDIA] JANELA_ESTOUROU de %s em %s: %s",
                            pipeline, data_ref, detalhe)
            conn.commit()
        except Exception as e:
            _rollback(conn)
            log.warning("[GUARDIA] deadline de %s em %s falhou (%s) — seguindo",
                        pipeline, data_ref, e)
    return alertas


# ── Responsabilidade 5 — divergência e predecessor falhado (§7) ─────────────

def _divergencias_e_falhas(conn, agora: datetime, log) -> int:
    """As duas caras restantes, sobre o que sobrou aguardando:
    DATA_DIVERGENTE de execução exige carimbo DENTRO do dia operacional
    corrente (fim depois da virada mais recente — o sucesso normal de ontem
    NÃO alerta, Decisão 12/D42) e cita as DUAS datas; PREDECESSOR_FALHOU é
    IMEDIATO (FALHA sem sucesso na data é fato consumado — esperar deadline
    seria reeditar o silêncio do QA5, Decisão 13)."""
    eventos = 0
    # Régua do banco: o corte do "dia operacional corrente" é calculado em
    # hora LOCAL, mas `fim` é carimbado por GETDATE (que pode estar em UTC —
    # caso real do dev). Converter o corte para a régua do banco elimina o
    # DATA_DIVERGENTE falso do pai que conclui entre (virada-3h) e a virada.
    desvio_banco = dep.agora_do_banco(conn) - agora
    for pipeline, data_ref, _run_id, _criado_em in dep.corridas_aguardando(conn):
        try:
            viradas = _viradas_dos_predecessores(conn, pipeline)
            inicio_dia = _virada_corrente(agora,
                                          _virada_de_referencia(viradas.values()))
            pares = dep.sucesso_recente_outra_data(conn, pipeline, data_ref,
                                                   inicio_dia + desvio_banco)
            if pares:
                detalhe = "; ".join(
                    f"aguarda {_iso(data_ref)}; {p} concluiu hoje com "
                    f"data_referencia={_iso(d)}"
                    for p, d in sorted(pares))
                if dep.gravar_evento(conn, pipeline, data_ref,
                                     "DATA_DIVERGENTE", detalhe):
                    eventos += 1
                    log.warning("[GUARDIA] DATA_DIVERGENTE de %s: %s",
                                pipeline, detalhe)
                conn.commit()
            resumo = dep.resumo_predecessores(conn, pipeline, data_ref)
            falhados = sorted(p for p, status in resumo.items()
                              if "FALHA" in status and "SUCESSO" not in status)
            if falhados:
                detalhe = (f"predecessor com FALHA em {_iso(data_ref)}: "
                           + ", ".join(falhados))
                if dep.gravar_evento(conn, pipeline, data_ref,
                                     "PREDECESSOR_FALHOU", detalhe):
                    eventos += 1
                    log.warning("[GUARDIA] PREDECESSOR_FALHOU de %s: %s",
                                pipeline, detalhe)
                conn.commit()
        except Exception as e:
            _rollback(conn)
            log.warning("[GUARDIA] diagnóstico de %s em %s falhou (%s) — seguindo",
                        pipeline, data_ref, e)
    return eventos


# ── Responsabilidade 6 — observadores de malha (F14 §5/§6) ──────────────────

def _detalhe_notificacao(config: dict, malha: str, data_ref, upstream) -> str:
    """Mensagem do evento MALHA_NOTIFICACAO, renderizada na DETECÇÃO com o
    contexto em mãos (padrão da supervisão): título/mensagem do config do nó
    + malha + a lista do upstream resumida (§5 passo 4). gravar_evento clipa
    em 1000 — o resumo aqui é para o card sair legível, não para caber."""
    cfg = config or {}
    titulo = (str(cfg.get("titulo") or "")).strip() or "Notificação da malha"
    mensagem = (str(cfg.get("mensagem") or "")).strip()
    resumo = ", ".join(upstream[:10])
    if len(upstream) > 10:
        resumo += f" (+{len(upstream) - 10})"
    detalhe = (f"{titulo} — malha {malha}: todas as entradas com SUCESSO "
               f"em {_iso(data_ref)} ({resumo})")
    if mensagem:
        detalhe += f" - {mensagem}"
    return detalhe


def _observadores_malha(conn, agora: datetime, log) -> int:
    """F14 (desenho de componentes §5/§6, Decisão 12): avalia os nós
    Notificação/Fim de malhas ativas DENTRO do ciclo — nenhuma task nova em
    DAG nenhuma; em runtime os nós não existem, quem observa é a guardiã.

    Por observador (try/except por nó, D51):
      • upstream via o CANÔNICO expandir (utils/malha_nos.py) — vazio pula
        com log (Decisão 13: o "todos com sucesso" vacuamente verdadeiro
        jamais emite);
      • viradas do upstream via virada_efetiva — divergentes pulam com log
        (a face de configuração do DATA_DIVERGENTE já alerta a doença; o
        observador não adivinha);
      • janela fixa {D-1, D} derivada do PRESENTE (D = calcular(agora,
        virada)) — nunca varredura de histórico (D45). O D-1 pega a cadeia
        noturna que conclui depois da meia-noite; a chave do
        ux_dep_evento_corrida (ux_dep_evento até a 085) impede duplicata
        quando o evento já saiu no próprio dia; data
        anterior ao DIA de criação do nó nunca é avaliada (corte
        anti-retroativo — achado 1 da revisão);
      • condição = pipelines_todos_sucesso (o MESMO contrato EXISTS de
        liberado(), sobre a lista explícita) → gravar_evento com o marcador
        #no:{id} (convenção §5: id é IDENTITY global; '#' não colide com
        dag_id) e commit — evento e carimbo de opt-out saem na MESMA
        transação, numa escrita só. Notificação SEMPRE vai à fila do Teams; o card
        do Fim é OPT-IN (config notificar_teams, Decisão 14) — o evento e o
        painel são sempre.

    Sem a migration 075 os observadores são pulados com log — o restante do
    ciclo (F4) não depende dela.
    """
    if not dep.tabela_075_presente(conn):
        log.info("[GUARDIA] migration 075 ausente — observadores de malha "
                 "pulados")
        return 0
    eventos = 0
    expansoes: dict = {}    # malha -> expandir(...) (uma expansão por malha)
    for obs in dep.nos_observadores(conn):
        try:
            malha, no_id = obs["malha"], obs["no_id"]
            if malha not in expansoes:
                expansoes[malha] = expandir(obs["nos"], obs["arestas"])
            upstream = sorted(expansoes[malha]["nos"][no_id]["upstream"])
            if not upstream:
                log.info("[GUARDIA] no %s (%s) da malha '%s' sem upstream — "
                         "nao avaliado (Decisao 13)", no_id, obs["tipo"], malha)
                continue
            viradas = sorted({dep.virada_efetiva(conn, p) for p in upstream})
            if len(viradas) > 1:
                log.warning("[GUARDIA] no %s da malha '%s' com viradas "
                            "divergentes no upstream — nao avaliado", no_id,
                            malha)
                continue
            # Corte anti-retroativo (achado 1 da revisão adversarial): o nó
            # só observa datas >= o DIA em que foi criado — não existe
            # notificação "pedida" antes de o nó existir. Sem isto, criar o
            # nó às 14:00 com a malha de ontem concluída faria a janela D-1
            # emitir um card retroativo que ninguém pediu (violação direta
            # do anti-ruído, Decisões 13/14). Ruído único ACEITO e
            # documentado: reativar uma malha inativa pode emitir pela
            # janela {D-1, D} corrente (não há carimbo de reativação para
            # cortar — rastreá-lo seria estado novo sem dono no modelo).
            criado_em = obs.get("criado_em")
            corte = (criado_em.date() if isinstance(criado_em, datetime)
                     else criado_em)
            data_corrente = calcular(agora, viradas[0])
            for data_ref in (data_corrente - timedelta(days=1), data_corrente):
                if corte is not None and data_ref < corte:
                    continue
                if not dep.pipelines_todos_sucesso(conn, upstream, data_ref):
                    continue
                if obs["tipo"] == "notificacao":
                    tipo_ev, notificar = "MALHA_NOTIFICACAO", True
                    detalhe = _detalhe_notificacao(obs["config"], malha,
                                                   data_ref, upstream)
                else:
                    tipo_ev = "MALHA_CONCLUIDA"
                    notificar = (obs["config"] or {}).get("notificar_teams") is True
                    detalhe = (f"Malha {malha} concluída na data "
                               f"{_iso(data_ref)} — {len(upstream)} "
                               "pipeline(s) com SUCESSO")
                if dep.gravar_evento(conn, f"#no:{no_id}", data_ref, tipo_ev,
                                     detalhe, notificar=notificar):
                    eventos += 1
                    log.info("[GUARDIA] %s do no %s (malha '%s') em %s",
                             tipo_ev, no_id, malha, _iso(data_ref))
                conn.commit()
        except Exception as e:
            _rollback(conn)
            log.warning("[GUARDIA] observador %s da malha '%s' falhou (%s) — "
                        "seguindo", obs.get("no_id"), obs.get("malha"), e)
    return eventos


# ── Responsabilidade 7 — envio ao Teams (§8) ────────────────────────────────

def _notificar(conn, log, limite: int) -> int:
    """Envio no FIM do ciclo, depois de toda a detecção, para o lote sair
    de uma vez e em ordem (padrão da supervisão). Canal derivado do que a
    supervisão DE FATO usa (decisão fechada: sem grupo novo); sem canal os
    eventos ficam gravados e vivem no painel (degradação prevista — no dev
    não há webhook real). notificado_em SÓ após 2xx; falha de envio não
    marca (o próximo ciclo re-tenta); a URL JAMAIS aparece em log."""
    from utils.ds_teams import enviar_card, montar_card_dependencia

    eventos = dep.eventos_nao_notificados(conn, limite, JANELA_NOTIFICACAO_DIAS)
    if not eventos:
        return 0
    canal = dep.canal_teams_supervisao(conn)
    if canal is None:
        log.info("[GUARDIA] sem canal do Teams — eventos só no painel")
        return 0

    enviados = 0
    for ev in eventos:
        ok, motivo = enviar_card(canal["webhook_url"],
                                 montar_card_dependencia(ev))
        if not ok:
            log.warning("[GUARDIA] evento %s de %s não foi ao canal '%s': %s",
                        ev.get("tipo"), ev.get("pipeline"),
                        canal.get("nome"), motivo)
            continue
        try:
            dep.marcar_notificado(conn, ev["id"])
            conn.commit()
            enviados += 1
            log.info("[GUARDIA] %s de %s enviado ao canal '%s' (%s)",
                     ev.get("tipo"), ev.get("pipeline"),
                     canal.get("nome"), motivo)
        except Exception as e:
            # Enviou mas não marcou: o próximo ciclo reenvia. Duplicar um
            # card é ruim, mas menos grave que perder o alerta.
            _rollback(conn)
            log.warning("[GUARDIA] card enviado mas notificado_em não gravou "
                        "(id=%s): %s", ev.get("id"), e)
    if len(eventos) == limite:
        log.info("[GUARDIA] lote de notificação cheio (%d) — o restante sai "
                 "no próximo ciclo.", limite)
    return enviados


# ── Task única (§1.2): as responsabilidades em ordem, estado compartilhado ──

def ciclo(**context) -> dict:
    import logging
    log = logging.getLogger("airflow.task")

    from airflow.providers.microsoft.mssql.hooks.mssql import MsSqlHook

    agora = _agora()
    intervalo = _intervalo()
    hook = MsSqlHook(mssql_conn_id=_var("DEPENDENCIA_MSSQL_CONN_ID",
                                        "SQL14_DMDB41"))
    conn = hook.get_conn()
    try:
        if not dep.tabelas_067_presentes(conn):
            log.warning("[GUARDIA] migration 067 ausente — ciclo encerrado")
            return {"migration_067": False}
        fechadas    = _fechar_dia_anterior(conn, agora, log)
        ordenadas   = _new_day(conn, agora, log)
        resgatadas  = _resgatar_orfas(conn, intervalo, log)
        # Órfãs que COMEÇARAM (§4.3) ANTES da rede: uma corrida fechada aqui
        # pode ser a que falta para um dependente decidir o dia no MESMO ciclo
        # (FALHA é resposta; EXECUTANDO eterno não é).
        orfas_exec = _resgatar_em_execucao(conn, agora, intervalo, log)
        disparadas  = _rede_seguranca(conn, agora, log)
        deadlines   = _deadline(conn, agora, log)
        eventos     = _divergencias_e_falhas(conn, agora, log)
        # Observadores DEPOIS de toda a detecção do dia (fechamento incluso)
        # e ANTES do Teams: o card da malha sai no lote do MESMO ciclo.
        observadores = _observadores_malha(conn, agora, log)
        notificados = _notificar(conn, log, _lote_notificacao())
    finally:
        conn.close()

    log.info("[GUARDIA] ciclo concluído: %d fechada(s), %d ordenada(s), "
             "%d resgatada(s), %d orfa(s) em execucao, %d disparada(s), "
             "%d deadline(s), %d evento(s), %d observador(es), "
             "%d notificado(s).",
             fechadas, ordenadas, resgatadas, orfas_exec, disparadas,
             deadlines, eventos, observadores, notificados)
    return {"fechadas": fechadas, "ordenadas": ordenadas,
            "resgatadas": resgatadas, "orfas_em_execucao": orfas_exec,
            "disparadas": disparadas,
            "deadlines": deadlines, "eventos": eventos,
            "observadores": observadores, "notificados": notificados}


_INTERVALO = _intervalo()

with DAG(
    dag_id=DAG_ID,
    default_args=default_args,
    description="Guardiã de dependências: ordena o dia, redispara, vigia deadline e alerta",
    schedule=f"*/{_INTERVALO} * * * *",
    start_date=pendulum.datetime(2026, 8, 1, tz=LOCAL_TZ),
    catchup=False,
    max_active_runs=1,          # ciclos nunca se atropelam (claims e eventos)
    tags=["dependencias", "guardia", "monitoramento"],
) as dag:
    PythonOperator(
        task_id="ciclo",
        python_callable=ciclo,
        # Um ciclo travado não pode segurar o seguinte.
        execution_timeout=timedelta(minutes=max(1, _INTERVALO - 1)),
    )
