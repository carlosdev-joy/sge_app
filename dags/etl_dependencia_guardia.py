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
  6. CORRIDA de malha (F2 de docs/spec-malha-execucao.md §6, TUDO atrás do
     interruptor etl_app_config.malha_corrida_ativa): abre pelas portas 2 e 3
     (raiz assinada pelo nó Início; raiz sem predecessor interno em malha SEM
     Início) ANTES dos observadores, e fecha pelos sete desfechos DEPOIS deles
     — o card do desfecho sai no lote do mesmo ciclo. Nenhuma DAG fecha
     corrida (Decisão 19): a que mais precisa fechar é a que não tem nada
     rodando. Com o interruptor em 0 nada abre, nada fecha e o log não muda.
  7. Observadores de malha (F14 — docs/malha-componentes-desenho.md §5/§6;
     no desenho de componentes é a "responsabilidade 5, depois do fechamento
     §6 da F4"): nós Notificação/Fim de malhas ATIVAS viram eventos
     MALHA_NOTIFICACAO/MALHA_CONCLUIDA com marcador #no:{id}, escopados pela
     corrida aberta quando ela existe e, sem ela, na janela fixa {D, D-1} do
     presente — nunca varredura de histórico (D45). Upstream vazio ou viradas
     divergentes pulam com log (Decisão 13); o card do Fim é OPT-IN por config
     (Decisão 14). Nada aqui dispara nem fecha corrida: observador observa.
  8. Envio ao Teams (§8): canal derivado da supervisão DataStage, lote por
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
from utils import malha_corrida as mc                     # noqa: E402
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

def _fechar_dia_anterior(conn, agora: datetime, log, corrida_on: bool = False) -> int:
    """NAO_LIBEROU: fecha as linhas aguardando que atravessaram um dia
    operacional COMPLETO sem liberar. Três guardas, cada uma com dono
    (Decisão 11): idade de um dia inteiro (a cadeia noturna meramente LENTA
    sobrevive — o push das 02:00 ainda adota a linha); liberado() == False
    (linha velha porém LIBERADA vai para a rede, que dispara — rodar
    atrasado é o propósito da feature); sem predecessor EXECUTANDO (pai de
    30h rodando não derruba o filho que o espera). Fechou → evento
    NAO_LIBEROU + card: é o D41 de quem não configurou deadline.

    **F7 — mais duas guardas, e as duas consertam defeitos que existem HOJE**
    (spec-malha-execucao §6.7/§6.8, Decisões 30 e 31):

      • **corrida ABERTA cobre a linha** (Decisão 31): esta função corta por
        `criado_em < virada_anterior`, régua derivada da VIRADA. Malha com teto
        de 48h, ou corrida que atravessa a virada seguinte (cadeia noturna longa
        + rerun), teria os `AGUARDANDO_DEPENDENCIA` dela fechados como
        `NAO_LIBEROU` **enquanto a corrida ainda é válida** — os membros virariam
        pendentes e a corrida iria a `FALHA` por ação da própria guardiã. A
        corrida passa a ser a autoridade sobre "este ciclo ainda não acabou";
      • **nó SEGURADO** (Decisão 30): com um Aguarde retido, `liberado()`
        devolve False por construção — é a trava que o operador pôs, não um
        predecessor que faltou. Fechar aqui é a guardiã desfazendo o gesto dele
        depois de 24h, sem que ninguém tenha soltado nada. O faltante já
        DIZ que é retenção (`dep.eh_retencao`, 2ª coluna do predicado); o que
        faltava era alguém escutar.
    """
    fechadas = 0
    # `corrida_on` chega PRONTO de `ciclo()` (avaliado uma vez, no portão): com
    # o interruptor em 0 — o estado de todo ambiente antes desta fase — a
    # pergunta da Decisão 31 nem chega ao banco, e esta função sai byte a byte
    # como antes. O default `False` é o que mantém verdes os chamadores de
    # teste que a exercitam com três argumentos.
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
            # Decisão 31 — depois do corte de propósito: só as linhas que ESTÃO
            # para ser fechadas pagam a consulta (o corte descarta a esmagadora
            # maioria), e nenhum ciclo saudável gasta uma ida ao banco a mais.
            if corrida_on:
                aberta = mc.corrida_aberta_da_linha(conn, pipeline, data_ref)
                if aberta is not None:
                    if aberta["id"] is None:
                        log.warning("[GUARDIA] corrida de %s em %s indisponivel "
                                    "— fechamento adiado", pipeline, data_ref)
                    else:
                        log.info("[GUARDIA] %s em %s pertence a corrida ABERTA "
                                 "da malha '%s' — NAO fechado como NAO_LIBEROU "
                                 "(o ciclo ainda nao acabou)", pipeline,
                                 data_ref, aberta["malha_name"])
                    continue
            lib, faltantes = dep.liberado(conn, pipeline, data_ref)
            if lib:
                continue        # liberada velha: disparo (rede), não fechamento
            if any(dep.eh_retencao(f) for f in faltantes):
                # Decisão 30: quem segura é o OPERADOR. "Nenhum vivo, nenhum
                # liberado" aqui não é abandono — é uma decisão humana em curso,
                # e ela não tem prazo de 24h.
                log.info("[GUARDIA] %s em %s espera no de malha SEGURADO (%s) "
                         "— NAO fechado como NAO_LIBEROU", pipeline, data_ref,
                         ", ".join(str(f) for f in faltantes
                                   if dep.eh_retencao(f))[:200])
                continue
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
    o retry (D16/D50), sem código novo de retry.

    **F7 — esta é a QUARTA PORTA DE DISPARO** (pendência 14 da §18), e até aqui
    ela era a única que não levava a corrida junto: `montar_conf(data_ref,
    dia_op, "guardia")`, sem `malha_execucao_id`. A DATA nunca sofreu (o degrau
    0 do §7 lê a linha que o claim acabou de carimbar), mas a PROVENIÊNCIA se
    perdia exatamente no caso que a F5 existe para tratar — o pipeline membro de
    duas corridas do MESMO ODATE, em que o degrau 3 se recusa a escolher e a
    linha ficaria sem dono. Agora a porta faz as duas coisas que as outras três
    já faziam: **recusa por ODATE ambíguo** (Decisão 34) e **propaga a corrida**
    (Decisão 35).
    """
    disparadas = 0
    for pipeline, data_ref, _run_id, _criado_em in dep.corridas_aguardando(conn):
        try:
            # F6: aqui a corrida da linha NÃO está em mãos — `corridas_aguardando`
            # devolve (pipeline, data, run_id, criado_em), e trazer o
            # `malha_execucao_id` mudaria a aridade de uma leitura que quatro
            # responsabilidades consomem. Sem ela o corte cai no degrau 2 (a
            # corrida ABERTA da malha que assinou a dependência), que é a resposta
            # certa em todo ciclo em voo; só quando a corrida da linha já fechou é
            # que o degrau 3 (janela) decide — que é EXATAMENTE o comportamento
            # de hoje, não uma regressão.
            lib, _faltantes = dep.liberado(conn, pipeline, data_ref)
            if not lib:
                continue    # deadline (§5) e divergência (§7) diagnosticam o resto
            # F7 (Decisão 34) — duas corridas abertas com ODATEs DIFERENTES para
            # este pipeline: recusa nominal, nunca escolha. Vem ANTES do claim de
            # propósito: reservar e não disparar deixaria a linha com
            # `execution_id` de um run que nunca existiu, e o próximo ciclo teria
            # de devolver a reserva para chegar à mesma recusa.
            #
            # Com o interruptor em 0 (ou sem a 085) `odate()` devolve o vazio na
            # PRIMEIRA linha, sem tocar o banco: nenhuma consulta a mais nesta
            # varredura enquanto a corrida não estiver ligada.
            od = mc.odate(conn, pipeline)
            if od["ambiguo"]:
                log.warning("[GUARDIA] %s NAO disparado — %s", pipeline,
                            od["detalhe"])
                try:
                    dep.gravar_evento(conn, pipeline, data_ref,
                                      "DATA_DIVERGENTE", od["detalhe"])
                    conn.commit()
                except Exception as e_amb:   # noqa: BLE001 — o evento é rastro
                    _rollback(conn)
                    log.warning("[GUARDIA] evento de ODATE ambiguo de %s nao "
                                "gravado (%s)", pipeline, e_amb)
                continue
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
            # F7 (pendência 14) — a PROVENIÊNCIA, perguntada DEPOIS do claim
            # porque é o claim que carimba `execution_id = ganho` na linha: com
            # o `run_id` em mãos, o degrau 0 devolve a corrida DA PRÓPRIA LINHA
            # (o que a pendência 20 queria de `corridas_aguardando` sem mudar a
            # aridade dela), e não uma corrida "provável" da malha. `herdada`
            # fecha o caso da linha que ainda não tem dono: a data é a dela,
            # ponto, e a corrida só é aceita se carimbar exatamente essa data.
            #
            # Nunca levanta: `montar_conf` sem a chave é o conf de antes desta
            # spec, byte a byte, e disparar sem proveniência é infinitamente
            # melhor que não disparar.
            corrida_id = None
            try:
                corrida_id = mc.odate(conn, pipeline, run_id=ganho,
                                      herdada=data_ref).get("corrida_id")
            except Exception as e_prov:  # noqa: BLE001
                log.warning("[GUARDIA] corrida de %s nao resolvida (%s) — "
                            "disparo segue sem a proveniencia", pipeline, e_prov)
            try:
                _trigger(pipeline, ganho,
                         dep.montar_conf(data_ref, dia_op, "guardia",
                                         malha_execucao_id=corrida_id))
                disparadas += 1
                log.info("[GUARDIA] %s disparado: run_id=%s data_ref=%s dia_op=%s "
                         "corrida=%s", pipeline, ganho, data_ref, dia_op,
                         corrida_id if corrida_id is not None else "-")
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


# ── Responsabilidade 6 — a CORRIDA de malha (spec docs/spec-malha-execucao.md
#    §6, fase F2): abrir pelas portas 2 e 3, fechar pelos sete desfechos ──────
#
# Por que aqui e não numa DAG: a corrida que MAIS precisa fechar é justamente a
# que não tem nada rodando — quiescência, teto, aborto. Uma DAG que fecha o
# próprio ciclo nunca fecharia essa (Decisão 19; precedente literal
# `_resgatar_em_execucao`: "a rede de segurança tem de ser de fora").
#
# Por que a abertura mora aqui e NÃO no fonte gerado (Decisão 13): assim a
# regra de abertura muda sem `force_all`, o grafo dos nós não é caminhado dentro
# do caminho quente de toda raiz, e quem abre e quem fecha deployam JUNTOS — a
# mesma árvore, no mesmo bind mount. O custo é latência de até um ciclo entre a
# raiz partir e a corrida existir, e ele é pago por construção: `aberta_em`
# RECUA para o instante da linha âncora, de modo que a corrida nunca "perde" o
# trabalho que a originou.
#
# ZERO SQL aqui também (Decisão 15): toda pergunta mora em utils/malha_corrida.py
# (a única autoridade sobre o registro da corrida) e em utils/dependencias.py.

# `pipeline_name` do evento da corrida (a tabela de eventos é chaveada por
# pipeline, e a corrida não é um pipeline). Mesma convenção do '#no:{id}' dos
# observadores: '#' não colide com dag_id, e o ds_teams publica a MALHA no card,
# nunca o marcador.
MARCADOR_CORRIDA = "#corrida:{}"

# O que a guardiã assina quando fecha.
FECHADA_POR = "guardia"


def _corrida_habilitada(conn, log) -> bool:
    """A corrida de malha opera neste ciclo?

    Duas perguntas, UMA vez por ciclo e nesta ordem:

      1. o interruptor `malha_corrida_ativa` (§11.2). É absoluto e vem
         primeiro: com `0` nada abre, nada fecha e **nenhuma linha nova
         aparece no log** — critério de aceite literal da fase, e a razão de
         o resumo do ciclo só ganhar a frase da corrida quando ela está
         ligada;
      2. a presença da 085. O aviso sai UMA vez por ciclo (não uma por malha
         nem uma por responsabilidade) e o ciclo INTEIRO segue: uma exceção
         aqui derrubaria a guardiã, que é quem faz o push de dependências de
         toda a casa.

    O cache do interruptor é limpo no começo de cada ciclo: `corrida_ativa` o
    memoriza por processo (a task do Airflow é curta), e sem a limpeza um worker
    reaproveitado carregaria a chave antiga até morrer. Virar a chave passa a
    valer no ciclo seguinte — que é o comportamento esperado de configuração.
    """
    mc.limpar_cache()
    if not mc.corrida_ativa(conn):
        return False
    if not mc.tabela_085_presente(conn):
        log.warning("[GUARDIA] 085 ausente — corrida de malha nao operada "
                    "neste ciclo; o restante do ciclo segue normal")
        return False
    return True


def _porta_da_malha(conn, malha: str, membros, nos, expansao):
    """`(origem, raizes, no_inicio)` — quem pode ABRIR a corrida desta malha.

    Malha **com** nó Início: só os pipelines que ele assina (porta 2). Malha
    **sem** Início: as raízes internas, isto é, membros sem predecessor dentro
    da malha (porta 3, Decisão 16).

    A Decisão 17 é consequência direta desta escolha, não um `if` extra: numa
    malha com Início, quem não está assinado por ele **nunca** entra na lista, e
    o membro com cron próprio não sequestra o ciclo nem transforma o Início em
    decoração.
    """
    inicios = [n["id"] for n in nos if n["tipo"] == "inicio"]
    if inicios:
        assinadas: set = set()
        for no_id in inicios:
            assinadas |= set(expansao["nos"].get(no_id, {})
                             .get("saidas_pipeline", ()))
        return "inicio", sorted(assinadas & set(membros)), inicios[0]
    return "implicita", mc.raizes_da_malha(conn, malha), None


def _abrir_uma_corrida(conn, desenho: dict, origem: str, no_inicio,
                       partidas: list, expansao: dict, teto: int, log):
    """Abre (ou adere a) a corrida de UMA malha, com o snapshot no mesmo commit.

    A âncora é a partida MAIS ANTIGA: `aberta_em` recua para o instante dela, e
    recuar para a mais antiga é o que impede a corrida de nascer depois de
    metade do trabalho e classificar esse trabalho como "não partiu".

    O ODATE é o CANÔNICO da malha (Decisão 18) calculado sobre o instante da
    âncora — nunca o que o membro carimbou. Quando os dois discordam, a corrida
    nasce com o canônico, o `motivo` registra a discordância e sai
    `DATA_DIVERGENTE`: divergência visível é o oposto de divergência silenciosa,
    e é exatamente o que faltou no incidente `Carga_Vida`.

    Quando a malha já tem corrida aberta de OUTRO ODATE, a resposta é RECUSA
    (Decisão 15) — nunca adesão calada. Uma corrida de terça travada adotaria a
    carga de quarta e carimbaria terça nela inteira, e para o motor estaria tudo
    coerente, porque é uma corrida só: é o mesmo incidente por dentro do
    mecanismo criado para matá-lo.
    """
    malha, membros = desenho["malha"], desenho["membros"]
    ancora = partidas[0]
    # ⚠️ O LOTE desta corrida é só o que compartilha o ODATE da âncora, e isso
    # foi MEDIDO no dev. `partidas_a_cobrir` varre a janela {D-1, D}, então
    # depois de a guardiã ficar fora do ar atravessando a virada o lote traz as
    # duas madrugadas juntas. Sem este recorte, a corrida de D-1 carimbava
    # `malha_execucao_id` na linha de D — e como a coluna é WRITE-ONCE e a busca
    # exclui o que uma corrida DESTA malha já cobriu, o ciclo de D **nunca mais
    # abria**: o dia inteiro saía sem corrida, sem card e sem alarme. As linhas
    # do outro ODATE voltam no ciclo seguinte e passam pela conferência da
    # Decisão 15, que é onde a divergência tem de ser decidida — nunca aqui.
    #
    # O critério é o ODATE da ÂNCORA, e não o canônico: quando os dois divergem,
    # a §6.2 manda a linha âncora entrar mesmo assim, classificada como
    # `fora_do_odate` (§6.4) — divergência visível é o oposto de silenciosa.
    lote = [p for p in partidas
            if p["data_referencia"] == ancora["data_referencia"]]
    odate = mc.odate_da_abertura(conn, malha, ancora["momento"])
    fins = [n["id"] for n in desenho["nos"] if n["tipo"] == "fim"]
    conta_fim = None
    if fins:
        alvo: set = set()
        for no_id in fins:
            alvo |= set(expansao["nos"].get(no_id, {}).get("upstream", ()))
        # Conjunto VAZIO é diferente de None e não é erro (§6.9/#2): existe um
        # Fim e ele não alcança ninguém. O fechamento por Fim continua exigindo
        # nenhum membro vivo, e o painel lista os `fora_do_fim` nominalmente.
        conta_fim = sorted(alvo & set(membros))
    divergiu = ancora["data_referencia"] != odate
    motivo = None
    if divergiu:
        motivo = ("DATA_DIVERGENTE: a linha ancora %s carimbou %s e o ciclo "
                  "da malha e de %s" % (ancora["pipeline"],
                                        _iso(ancora["data_referencia"]),
                                        _iso(odate)))
    corrida = mc.abrir_corrida(
        conn, malha, odate, origem,
        aberta_por=(f"inicio:#{no_inicio}" if no_inicio is not None
                    else f"implicita:{ancora['pipeline']}"),
        aberta_em=ancora["momento"],
        ancora_pipeline=ancora["pipeline"],
        ancora_execution_id=ancora["execution_id"],
        no_inicio=no_inicio, no_fim=(fins[0] if fins else None),
        modo_fechamento=("fim" if fins else "quiescencia"),
        teto_horas=teto, motivo=motivo)
    if corrida is None:
        _rollback(conn)
        return None
    marcador = MARCADOR_CORRIDA.format(corrida["id"])
    if not corrida["odate_confere"]:
        detalhe = (f"{mc.MOTIVO_OUTRO_ODATE}: corrida #{corrida['id']} de "
                   f"{_iso(corrida['data_referencia'])} ainda aberta - o ciclo "
                   f"de {_iso(odate)} nao foi aberto e estas execucoes ficam "
                   f"fora dele")
        for p in lote:
            mc.carimbar_motivo(conn, p["pipeline"], p["data_referencia"],
                               p["execution_id"], mc.MOTIVO_OUTRO_ODATE,
                               detalhe)
        dep.gravar_evento(conn, marcador, odate, "DATA_DIVERGENTE", detalhe,
                          malha_execucao_id=corrida["id"])
        conn.commit()
        log.warning("[GUARDIA] malha '%s': %s", malha, detalhe)
        return corrida
    if corrida["nova"]:
        # Snapshot NO MESMO COMMIT da abertura (§6.2): corrida sem membros tem
        # denominador zero e a §6.5 a levaria a ABORTADA com a malha rodando ao
        # lado.
        mc.congelar_snapshot(conn, corrida["id"], malha,
                             conta_para_fim=conta_fim)
    # As raízes que partiram passam a pertencer à corrida. Além da honestidade
    # do card, é o que faz o laço CONVERGIR: a partida carimbada deixa de ser
    # candidata, e sem isso o PULADO de sábado abriria uma corrida a cada 5 min.
    # Só o `lote` — as linhas do outro ODATE não pertencem a este ciclo.
    for p in lote:
        mc.vincular_execucao(conn, p["pipeline"], p["data_referencia"],
                             p["execution_id"], corrida["id"])
    if divergiu:
        dep.gravar_evento(conn, marcador, odate, "DATA_DIVERGENTE", motivo,
                          malha_execucao_id=corrida["id"])
    conn.commit()
    if corrida["nova"]:
        log.info("[GUARDIA] corrida da malha '%s' aberta em %s (origem=%s, "
                 "ancora=%s, inicio recuado para %s)", malha, _iso(odate),
                 origem, ancora["pipeline"], ancora["momento"])
    return corrida


def _carimbar_fora_da_corrida(conn, desenho: dict, raizes, janela, teto,
                              log) -> int:
    """Decisão 17 — malha COM nó Início e NENHUMA corrida aberta: o membro que
    rodou sozinho **não** abre ciclo, fica sem corrida e carimba o porquê na
    PRÓPRIA linha.

    O diagnóstico tem de viajar com a execução: de plantão se chega pelo
    pipeline, não pela malha. É exatamente o alarme que faltou no `Carga_Vida` —
    lá a linha rodou com a data errada e não havia, nela, nada que dissesse por
    quê.

    Havendo corrida aberta, nada é carimbado: a linha pertence ao ciclo em voo
    (o recorte de tempo da Decisão 23 já a conta), e dizer "fora da corrida"
    seria mentira gravada no banco.
    """
    malha = desenho["malha"]
    if mc.corrida_aberta(conn, malha) is not None:
        return 0
    fora = [p for p in desenho["membros"] if p not in set(raizes)]
    if not fora:
        return 0
    texto = (f"{mc.MOTIVO_FORA_DA_CORRIDA}: a malha {malha} parte pelo no "
             f"Inicio e nao havia corrida aberta - esta execucao rodou FORA do "
             f"ciclo da malha")
    carimbadas = 0
    for o in mc.partidas_a_cobrir(conn, malha, fora, janela, teto):
        if mc.carimbar_motivo(conn, o["pipeline"], o["data_referencia"],
                              o["execution_id"], mc.MOTIVO_FORA_DA_CORRIDA,
                              texto):
            carimbadas += 1
            log.warning("[GUARDIA] %s rodou FORA da corrida da malha '%s' em "
                        "%s — a malha tem no Inicio e nada abriu o ciclo",
                        o["pipeline"], malha, _iso(o["data_referencia"]))
    if carimbadas:
        conn.commit()
    return carimbadas


def _abrir_corridas_malha(conn, log) -> int:
    """Portas 2 e 3 do §6.2: a raiz partiu, a corrida nasce.

    Um erro em UMA malha não interrompe as outras (try/except por item, D51) —
    a mesma disciplina das cinco responsabilidades antigas.
    """
    try:
        malhas = dep.malhas_ativas_com_desenho(conn)
        agora_banco = dep.agora_do_banco(conn)
    except Exception as e:  # noqa: BLE001
        log.warning("[GUARDIA] desenho das malhas indisponivel (%s) — nenhuma "
                    "corrida aberta neste ciclo", e)
        return 0
    abertas = 0
    for desenho in malhas:
        malha = desenho["malha"]
        try:
            if not desenho["membros"]:
                continue
            expansao = expandir(desenho["nos"], desenho["arestas"])
            origem, raizes, no_inicio = _porta_da_malha(
                conn, malha, desenho["membros"], desenho["nos"], expansao)
            teto = mc.teto_horas_da_malha(conn, malha)
            # Janela {D-1, D} do PRESENTE, pela virada da MALHA — o mesmo
            # recorte dos observadores (D45: nunca varredura de histórico). O
            # D-1 pega a cadeia noturna que parte antes da meia-noite.
            hoje = mc.odate_da_abertura(conn, malha, agora_banco)
            janela = (hoje - timedelta(days=1), hoje)
            corrida = None
            partidas = mc.partidas_a_cobrir(conn, malha, raizes, janela, teto)
            if partidas:
                corrida = _abrir_uma_corrida(conn, desenho, origem, no_inicio,
                                             partidas, expansao, teto, log)
                if corrida is not None and corrida.get("nova"):
                    abertas += 1
            if no_inicio is not None and corrida is None:
                _carimbar_fora_da_corrida(conn, desenho, raizes, janela, teto,
                                          log)
        except Exception as e:  # noqa: BLE001
            _rollback(conn)
            log.warning("[GUARDIA] abertura da corrida da malha '%s' falhou "
                        "(%s) — seguindo", malha, e)
    return abertas


def _fechar_uma_corrida(conn, corrida: dict, desfecho: str, tipo_evento,
                        detalhe: str, log, notificar: bool = True,
                        so_se_primeira_falha: bool = False) -> bool:
    """Grava o evento e fecha a corrida na MESMA transação, commit único
    (Decisão 20).

    A ordem antiga — fechar, commitar, e só então o evento — perdia o card PARA
    SEMPRE se a falha caísse entre os dois commits, porque a detecção consome a
    própria fonte: aqui a detecção é "sem data de fechamento", e é ela que o
    fechamento consome. A lição já está paga e escrita em `_fechar_dia_anterior`.

    `so_se_primeira_falha` cobre o `MALHA_FALHOU`: ele pode já ter saído no
    ciclo da DETECÇÃO (Decisão 12), horas antes. `marcar_visto` é o árbitro em
    UMA operação — `rowcount = 0` significa "já saiu", e aí o fechamento
    acontece sem card repetido.
    """
    cid = corrida["id"]
    if so_se_primeira_falha and not mc.marcar_visto(conn, cid, "falha"):
        tipo_evento = None
    if tipo_evento:
        dep.gravar_evento(conn, MARCADOR_CORRIDA.format(cid),
                          corrida["data_referencia"], tipo_evento, detalhe,
                          notificar=notificar, malha_execucao_id=cid)
    if not mc.fechar_corrida(conn, cid, desfecho, FECHADA_POR, motivo=detalhe):
        _rollback(conn)     # outra ponta fechou primeiro — o certo
        return False
    conn.commit()
    log.info("[GUARDIA] corrida da malha '%s' em %s fechada como %s: %s",
             corrida["malha_name"], _iso(corrida["data_referencia"]), desfecho,
             detalhe)
    return True


def _dispensa_por_dia(conn, corrida: dict, cache: dict):
    """O callback do §6.4: "membro sem linha nenhuma — o dia dele permitia
    rodar?". REUSA `dia_permitido` (o mesmo julgamento de
    `_predecessor_esperado`), em vez de duplicá-lo dentro do módulo da corrida.

    Sem cadastro → NÃO dispensa: o membro aparece como pendente e a corrida
    nomeia quem não rodou, em vez de dispensar em silêncio um pipeline que
    ninguém sabe se devia rodar.
    """
    def _resolve(pipeline: str) -> bool:
        if pipeline not in cache:
            cfg = dep.config_dependente(conn, pipeline)
            cache[pipeline] = bool(cfg) and not dep.dia_permitido(
                cfg["regras_dia"], corrida["data_referencia"])[0]
        return cache[pipeline]
    return _resolve


def _quiescencia_liberada(conn, corrida: dict, log) -> bool:
    """Guarda 1 das três (§6.5): nenhuma linha `AGUARDANDO_DEPENDENCIA` de
    membro desta corrida que `liberado()` aprove.

    Sem ela a rede de segurança ainda vai disparar essa linha neste ciclo ou no
    próximo, e a corrida teria fechado no meio de si mesma. É a MESMA função
    `liberado()` do push — paridade por identidade de objeto, não por cópia.

    "Não consegui perguntar" nunca vira "pode fechar": tanto a marca de erro de
    leitura quanto o `ERRO_CONSULTA` do predicado adiam o fechamento para o
    próximo ciclo. Adiar custa 5 min; fechar como FALHA uma corrida liberada
    custa o card mentiroso que a spec existe para matar.
    """
    esperando = mc.aguardando_do_snapshot(conn, corrida)
    if mc.ERRO_LEITURA in esperando:
        return False
    for pipeline in esperando:
        # F6 (Decisão 39): a corrida da LINHA avaliada, e aqui ela é conhecida —
        # a linha é membro DESTA corrida. Passá-la é o que faz o corte do modo
        # SEQUÊNCIA continuar valendo no instante exato em que este ciclo pode
        # fechá-la: se o corte viesse de "corrida aberta agora", o fechamento
        # que esta função autoriza mudaria, na avaliação seguinte, o próprio
        # critério que a autorizou — e a janela de 12h liberaria um filho com o
        # sucesso da rodada anterior, sem nada no banco explicando a virada.
        lib, faltantes = dep.liberado(conn, pipeline,
                                      corrida["data_referencia"], corrida["id"])
        if lib:
            log.info("[GUARDIA] corrida da malha '%s': %s esta liberado e vai "
                     "partir — fechamento adiado", corrida["malha_name"],
                     pipeline)
            return False
        if any(str(f).startswith(dep.ERRO_CONSULTA) for f in faltantes):
            log.warning("[GUARDIA] corrida da malha '%s': condicao de %s "
                        "indisponivel — fechamento adiado",
                        corrida["malha_name"], pipeline)
            return False
    return True


def _fechar_corridas_malha(conn, log) -> int:
    """Os sete desfechos do §6.5, na ordem em que a spec os torna verdadeiros.

    A ordem NÃO é decorativa:

      • a falha vai ao Teams na DETECÇÃO (Decisão 12), antes de qualquer
        fechamento: numa malha de 40 membros, `CARGA_A` falha às 01:12 e os
        outros 38 seguem até 05:00 — tocar o canal só no fim é tarde por
        definição, e `falha_vista_em` é a memória que impede o mesmo card 200
        vezes no dia;
      • **nada fecha com membro vivo** (Decisão 25). O teto com vivo é ALARME,
        nunca desfecho: fechar aqui liberaria o disparo por cima de 8 pipelines
        `EXECUTANDO`, e as linhas que terminassem depois carregariam id de
        corrida fechada — mentira estável que nenhum refresh corrige;
      • "tudo dispensado" vem ANTES de "zero linhas": o sábado da malha
        `somente_dias_uteis` é `SEM_TRABALHO` imediato (Decisão 26), e chamá-lo
        de `ABORTADA` diria "não chegou a começar" para um dia que funcionou
        exatamente como projetado;
      • `ABORTADA` só depois da carência de partida (Decisão 28): entre o
        commit da abertura e o primeiro `EXECUTANDO` há latência de scheduler,
        pool saturado, DAG pausada e `nao_iniciar_antes`;
      • as três guardas antes da quiescência, e o teto como última rede.

    Nenhum desfecho que não seja `CONCLUIDA` emite `MALHA_CONCLUIDA`
    (Decisão 24) — o teste dessa invariante é de AUSÊNCIA.
    """
    corridas = mc.corridas_abertas(conn)
    if not corridas:
        return 0
    quiescencia = mc.quiescencia_minutos(conn)
    carencia = mc.carencia_partida_min(conn)
    fechadas = 0
    for corrida in corridas:
        malha = corrida["malha_name"]
        try:
            est = mc.estado(conn, corrida,
                            dispensa_sem_linha=_dispensa_por_dia(conn, corrida, {}))
            # ⚠️ `estado()` degrada LARGA: lock timeout na tabela das execuções
            # (a maior do schema, e às 3h a mais disputada), deadlock ou coluna
            # ausente fazem a função logar e devolver os BALDES VAZIOS —
            # a razão de o nome dela não aparecer aqui é a invariante "zero SQL
            # no fonte da DAG". Vazio lido como fato é `linhas == 0`, e
            # `linhas == 0` com a carência vencida fecha a corrida como
            # `ABORTADA` — "não chegou a começar", com card no Teams, por cima
            # de oito pipelines `EXECUTANDO`. É o MESMO furo que a revisão da F3
            # achou na porta do disparo, na única leitura que ainda não o
            # tratava; `_expirar_na_porta` já recusa por este exato motivo.
            #
            # `membros` é o discriminador honesto: toda corrida nasce com o
            # snapshot congelado no MESMO commit (§6.2), logo `membros = 0` só
            # acontece quando a leitura não respondeu. Pular custa um ciclo de
            # 5 min — e a corrida travada de verdade tem o teto e o botão
            # Encerrar corrida (§6.8). "Não consegui perguntar" nunca vira
            # "pode fechar", literal.
            if int(est.get("membros") or 0) == 0:
                log.warning("[GUARDIA] estado da corrida da malha '%s' nao "
                            "pode ser lido (snapshot vazio) — NENHUM desfecho "
                            "neste ciclo", malha)
                continue
            rel = mc.relogios(conn, corrida, carencia, quiescencia)
            # HOLD suspende os relógios (Decisão 30): um Aguarde que o próprio
            # operador segurou faz liberado() devolver False para o dependente
            # — literalmente "nenhum vivo, nenhum liberado" — e sem esta guarda
            # a corrida fecharia como FALHA por causa da trava que ele pôs.
            retido = mc.ha_no_retido(conn, malha)

            falhados = [p["pipeline"] for p in est["pendentes"]
                        if p["classe"] == "falhou"]
            if falhados and mc.marcar_visto(conn, corrida["id"], "falha"):
                detalhe = ("falha em " + ", ".join(sorted(falhados))
                           + f" - a corrida da malha {malha} em "
                           + _iso(corrida["data_referencia"])
                           + " esta comprometida")
                dep.gravar_evento(conn, MARCADOR_CORRIDA.format(corrida["id"]),
                                  corrida["data_referencia"], "MALHA_FALHOU",
                                  detalhe, malha_execucao_id=corrida["id"])
                conn.commit()
                log.warning("[GUARDIA] MALHA_FALHOU da malha '%s': %s", malha,
                            detalhe)

            if est["vivos"]:
                if rel["teto_vencido"] and not retido and \
                        mc.marcar_visto(conn, corrida["id"], "atraso"):
                    detalhe = ("teto da corrida vencido com "
                               f"{len(est['vivos'])} pipeline(s) ainda em "
                               "execucao: " + ", ".join(est["vivos"][:10])
                               + " - nada foi encerrado e o disparo segue "
                                 "bloqueado")
                    dep.gravar_evento(
                        conn, MARCADOR_CORRIDA.format(corrida["id"]),
                        corrida["data_referencia"], "MALHA_ATRASADA", detalhe,
                        malha_execucao_id=corrida["id"])
                    conn.commit()
                    log.warning("[GUARDIA] MALHA_ATRASADA da malha '%s': %s",
                                malha, detalhe)
                continue

            if est["dispensados"] and not est["ok"] and not est["pendentes"]:
                # Decisão 26/27: informativo, e FORA do lote de notificação —
                # na primeira semana o operador aprenderia a ignorar o alarme
                # de sábado, e aí ele deixa de servir para o caso real.
                detalhe = ("nenhum pipeline da malha roda em "
                           + _iso(corrida["data_referencia"])
                           + f" (regra de dia): {len(est['dispensados'])} "
                             "membro(s) dispensado(s)")
                if _fechar_uma_corrida(conn, corrida, "SEM_TRABALHO",
                                       "MALHA_SEM_TRABALHO", detalhe, log,
                                       notificar=False):
                    fechadas += 1
                continue

            if est["linhas"] == 0:
                if rel["partida_vencida"] and not retido:
                    # `linhas` conta o que rodou NO ODATE da corrida. Quando a
                    # ancora carimbou outra data (o caso Carga_Vida literal), ha
                    # execucao vinculada e mesmo assim `linhas` e 0 — dizer "nao
                    # chegou a comecar" para uma malha que rodou seria a mesma
                    # familia de mentira que esta spec existe para matar. O
                    # desfecho continua ABORTADA (§6.5: zero trabalho no ODATE
                    # da corrida), mas o texto nomeia a causa que o operador tem
                    # de investigar — e o evento DATA_DIVERGENTE ja saiu antes.
                    fora = est.get("fora_do_odate") or []
                    if fora:
                        datas = sorted({_iso(x["data"]) for x in fora})
                        detalhe = (
                            "nenhum pipeline rodou na data de referencia da "
                            "corrida (" + _iso(corrida["data_referencia"])
                            + f"), mas {len(fora)} execucao(oes) da malha "
                              "rodaram com data divergente ("
                            + ", ".join(datas)
                            + ") - a malha rodou com a data errada, nao deixou "
                              "de rodar")
                    else:
                        detalhe = ("nenhum pipeline da malha registrou execucao "
                                   "apos a carencia de partida - a corrida nao "
                                   "chegou a comecar")
                    if _fechar_uma_corrida(conn, corrida, "ABORTADA",
                                           "MALHA_ABORTADA", detalhe, log):
                        fechadas += 1
                continue

            if retido:
                continue
            if not _quiescencia_liberada(conn, corrida, log):
                continue
            if not rel["quiescente"]:
                if rel["teto_vencido"]:
                    detalhe = ("teto da corrida vencido sem nenhum pipeline em "
                               "execucao - encerrada sem terminar; confira o "
                               "que ficou para tras")
                    if _fechar_uma_corrida(conn, corrida, "EXPIRADA",
                                           "MALHA_EXPIRADA", detalhe, log):
                        fechadas += 1
                continue

            # O denominador do desfecho: com nó Fim, quem manda é o upstream
            # dele (§6.5); sem Fim, todo membro conta. Em qualquer dos dois, o
            # "nenhum vivo" já foi exigido acima — sem essa segunda cláusula o
            # Fim que não alcança todos fecharia a corrida com membro rodando.
            pendentes = est["pendentes"]
            if corrida["modo_fechamento"] == "fim":
                contam = set(est["conta_para_fim"])
                pendentes = [p for p in pendentes if p["pipeline"] in contam]
            if pendentes:
                nomes = ", ".join(f"{p['pipeline']} ({p['classe']})"
                                  for p in pendentes[:10])
                detalhe = (f"{len(pendentes)} pipeline(s) sem concluir: "
                           + nomes)
                if _fechar_uma_corrida(conn, corrida, "FALHA", "MALHA_FALHOU",
                                       detalhe, log,
                                       so_se_primeira_falha=True):
                    fechadas += 1
                continue
            if est["ok"]:
                detalhe = (f"{len(est['ok'])} pipeline(s) com sucesso em "
                           + _iso(corrida["data_referencia"]))
                # Com nó Fim quem emite o card é o OBSERVADOR (F14), no mesmo
                # ciclo e com o mesmo id de corrida na chave: emitir aqui
                # também daria dois cards para a mesma conclusão. Sem Fim não há
                # observador, e o evento sai daqui com o marcador da corrida.
                tipo = "MALHA_CONCLUIDA" if corrida["no_fim"] is None else None
                if _fechar_uma_corrida(conn, corrida, "CONCLUIDA", tipo,
                                       detalhe, log):
                    fechadas += 1
                continue
            # Nenhum vivo, nenhum pendente, nenhum OK e havia linha: só sobra
            # dispensado (o caso já tratado acima) — chegar aqui é sinal de
            # snapshot vazio com linha de membro removido do desenho.
            log.warning("[GUARDIA] corrida da malha '%s' sem membro "
                        "classificavel — nada a fechar; confira o snapshot",
                        malha)
        except Exception as e:  # noqa: BLE001
            _rollback(conn)
            log.warning("[GUARDIA] fechamento da corrida da malha '%s' nao "
                        "concluido (%s) — nada persistido; proximo ciclo "
                        "repete", malha, e)
    return fechadas


# ── Responsabilidade 7 — observadores de malha (F14 §5/§6) ──────────────────

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


def _observadores_malha(conn, agora: datetime, log, corrida_on: bool = False) -> int:
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
      • **escopo pela CORRIDA quando ela existe** (F2): havendo corrida aberta
        da malha, o observador avalia o ODATE DELA e só ele — é o ciclo em voo
        que define o dia, e uma cadeia longa pode ter começado antes de D-1. A
        janela fixa {D-1, D} derivada do PRESENTE (D = calcular(agora, virada))
        vira FALLBACK: é o que vale com o interruptor desligado, sem a 085 ou
        para malha sem corrida — nunca varredura de histórico (D45). O D-1 pega
        a cadeia noturna que conclui depois da meia-noite; data anterior ao DIA
        de criação do nó nunca é avaliada (corte anti-retroativo — achado 1 da
        revisão);
      • o evento carrega o id da corrida DAQUELA data, aberta ou fechada — e
        não só o da aberta. A chave do índice único inclui a corrida, então
        gravar com o id enquanto ela está aberta e sem ele no ciclo seguinte
        (já fechada) produziria DUAS chaves distintas e DOIS cards para a mesma
        conclusão. Com a corrida do dia, a chave é a mesma antes e depois do
        fechamento;
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
            datas = (data_corrente - timedelta(days=1), data_corrente)
            aberta = mc.corrida_aberta(conn, malha) if corrida_on else None
            if aberta is not None:
                datas = (aberta["data_referencia"],)
            for data_ref in datas:
                if corte is not None and data_ref < corte:
                    continue
                if not dep.pipelines_todos_sucesso(conn, upstream, data_ref):
                    continue
                corrida_id = None
                if corrida_on:
                    dona = (aberta if aberta is not None
                            else mc.corrida_da_data(conn, malha, data_ref))
                    corrida_id = dona["id"] if dona else None
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
                                     detalhe, notificar=notificar,
                                     malha_execucao_id=corrida_id):
                    eventos += 1
                    log.info("[GUARDIA] %s do no %s (malha '%s') em %s",
                             tipo_ev, no_id, malha, _iso(data_ref))
                conn.commit()
        except Exception as e:
            _rollback(conn)
            log.warning("[GUARDIA] observador %s da malha '%s' falhou (%s) — "
                        "seguindo", obs.get("no_id"), obs.get("malha"), e)
    return eventos


# ── Responsabilidade 8 — envio ao Teams (§8) ────────────────────────────────

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
        # O portão da corrida sobe ANTES da primeira responsabilidade (F7). Ele
        # já era "uma vez por ciclo"; o que mudou é que a responsabilidade 1
        # passou a depender dele — `_fechar_dia_anterior` não pode fechar como
        # NAO_LIBEROU a linha de uma corrida ABERTA (Decisão 31). Avaliá-lo no
        # meio do ciclo faria a primeira responsabilidade ler o cache do ciclo
        # ANTERIOR num worker reaproveitado, e virar a chave às 3h deixaria de
        # valer justamente na função que a chave passou a governar.
        corrida_on = _corrida_habilitada(conn, log)
        fechadas    = _fechar_dia_anterior(conn, agora, log, corrida_on)
        ordenadas   = _new_day(conn, agora, log)
        resgatadas  = _resgatar_orfas(conn, intervalo, log)
        # Órfãs que COMEÇARAM (§4.3) ANTES da rede: uma corrida fechada aqui
        # pode ser a que falta para um dependente decidir o dia no MESMO ciclo
        # (FALHA é resposta; EXECUTANDO eterno não é).
        orfas_exec = _resgatar_em_execucao(conn, agora, intervalo, log)
        disparadas  = _rede_seguranca(conn, agora, log)
        deadlines   = _deadline(conn, agora, log)
        eventos     = _divergencias_e_falhas(conn, agora, log)
        # A CORRIDA de malha (F2, §6.3): abrir ANTES dos observadores — o
        # observador passa a ler o ODATE do ciclo em voo, e a corrida aberta
        # neste mesmo ciclo já vale para ele. Fechar DEPOIS dele e ANTES do
        # Teams: o card do desfecho sai no lote do MESMO ciclo, e o observador
        # do nó Fim ainda enxerga a corrida aberta quando grava a conclusão.
        #
        # O interruptor foi avaliado UMA vez, no portão lá em cima, e governa
        # estas três chamadas junto com a responsabilidade 1: com ele em 0 nada
        # abre, nada fecha, o observador volta ao comportamento anterior byte a
        # byte e o log não ganha uma linha sequer.
        corridas_abertas = _abrir_corridas_malha(conn, log) if corrida_on else 0
        observadores = _observadores_malha(conn, agora, log, corrida_on)
        corridas_fechadas = (_fechar_corridas_malha(conn, log)
                             if corrida_on else 0)
        if corrida_on:
            # Heartbeat DEPOIS do trabalho: ele significa "a guardiã deste
            # deploy OPEROU a corrida neste ciclo", que é a pergunta que a F3
            # faz antes de deixar a API abrir uma. Carimbá-lo antes diria
            # "cheguei", e "cheguei" não é o que a API precisa saber.
            # O commit fica na guarda junto com a escrita: `marcar_heartbeat`
            # engole a própria exceção SEM rollback, então um erro ali deixaria
            # a transação suja e este commit — o único do caminho quente sem
            # protecao — estouraria ANTES de `_notificar`, segurando os cards
            # que o ciclo acabou de gerar. O heartbeat e' o item mais dispensavel
            # do ciclo; nao pode ser quem impede o Teams de tocar.
            try:
                mc.marcar_heartbeat(conn)
                conn.commit()
            except Exception as e:  # noqa: BLE001 — heartbeat nunca derruba o ciclo
                log.warning("[GUARDIA] heartbeat da corrida nao gravado (%s); "
                            "o ciclo segue e a API pode recusar abrir corrida "
                            "ate o proximo", e)
                try:
                    conn.rollback()
                except Exception:  # noqa: BLE001
                    pass
        notificados = _notificar(conn, log, _lote_notificacao())
    finally:
        conn.close()

    log.info("[GUARDIA] ciclo concluído: %d fechada(s), %d ordenada(s), "
             "%d resgatada(s), %d orfa(s) em execucao, %d disparada(s), "
             "%d deadline(s), %d evento(s), %d observador(es), "
             "%d notificado(s).",
             fechadas, ordenadas, resgatadas, orfas_exec, disparadas,
             deadlines, eventos, observadores, notificados)
    # A frase da corrida é uma linha à PARTE e só sai com o interruptor ligado:
    # o critério de aceite da fase é literal — com `malha_corrida_ativa = 0` o
    # log da guardiã não muda de tamanho.
    if corrida_on:
        log.info("[GUARDIA] corrida de malha: %d aberta(s), %d fechada(s).",
                 corridas_abertas, corridas_fechadas)
    return {"fechadas": fechadas, "ordenadas": ordenadas,
            "resgatadas": resgatadas, "orfas_em_execucao": orfas_exec,
            "disparadas": disparadas,
            "deadlines": deadlines, "eventos": eventos,
            "observadores": observadores, "notificados": notificados,
            "corrida_ativa": corrida_on,
            "corridas_abertas": corridas_abertas,
            "corridas_fechadas": corridas_fechadas}


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
