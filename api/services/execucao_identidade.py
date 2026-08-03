"""
api/services/execucao_identidade.py — a ponte de identidade entre as DUAS
tabelas de execução (F2 da spec `docs/spec-operacao-nivel-etapa.md`).

═══════════════════════════════════════════════════════════════════════════════
O PROBLEMA (a "armadilha central" do §2 da spec)
═══════════════════════════════════════════════════════════════════════════════
As duas tabelas de execução usam chaves DIFERENTES para a mesma corrida:

  • ``dbo.etl_job_execution.execution_id``   = **ts_nodash** da logical date do
    dag_run (ex.: ``20260803T124924``). Gravada pela própria DAG, via
    ``EXEC dbo.sp_etl_job_execution_log`` (dags/etl_dag_factory.py).
  • ``dbo.etl_pipeline_execucao.execution_id`` = **run_id do Airflow**
    (ex.: ``manual__2026-08-03__DEV_F10_A__20260803T094924510486``).
    Gravada por ``_registrar_execucao`` (migration 067).

Até a F2 a conversão existia espalhada e implícita — ``_iso_to_ts_nodash`` /
``_escolhe_dag_run`` em routers/execucoes.py e ``toNodash`` no front. Todo
drill-down malha → etapa passa por essa ponte; ela precisa ser **uma peça só**.

═══════════════════════════════════════════════════════════════════════════════
A REGRA ÚNICA
═══════════════════════════════════════════════════════════════════════════════
    ts_nodash = ts_nodash(dag_run.logical_date)
    run_id    = dag_run.dag_run_id

**O dag_run do Airflow é a ÚNICA peça que carrega as duas chaves ao mesmo
tempo.** Logo, a tradução canônica run_id ↔ ts_nodash é uma leitura do Airflow.
Só existe UM atalho legítimo, e ele é restrito de propósito (ver
``ts_nodash_do_run_id``): quando o run_id é gerado pelo PRÓPRIO Airflow, ele
tem a forma ``<tipo>__<logical_date ISO>`` e a logical date sai da string.

⚠️ **ARMADILHA COMPROVADA NO DEV (2026-08-03)** — o Orquestra gera run_ids
PRÓPRIOS, e neles o timestamp embutido NÃO é a logical date:

    run_id  : manual__2026-08-03__DEV_F10_A__20260803T094924510486
    logical : 2026-08-03T12:49:24.715592+00:00  →  ts_nodash 20260803T124924

O ``20260803T094924`` do run_id é o relógio de parede LOCAL (America/Sao_Paulo,
UTC-3) e o ``2026-08-03`` do meio é a **data de referência (ODATE)**, não a data
lógica. Uma regex frouxa do tipo ``\\d{8}T\\d{6}`` casaria com ele e devolveria
um ts_nodash **3 horas errado**, apontando para uma execução que não existe (ou,
pior, para outra). Por isso ``ts_nodash_do_run_id`` só aceita a forma ISO
ANCORADA do Airflow e devolve ``None`` para tudo mais — quem não é traduzível
vai para o Airflow ou volta "não resolvido".

═══════════════════════════════════════════════════════════════════════════════
AMBIGUIDADE E IMPOSSIBILIDADE — o vocabulário fechado do "não sei"
═══════════════════════════════════════════════════════════════════════════════
Este módulo **nunca chuta em silêncio**. Toda resolução devolve o dict de
identidade (ver ``identidade_vazia``) com ``resolvido``, ``ambiguo``,
``candidatos``, ``regra`` e ``motivo`` preenchidos.

**AMBÍGUO** — mais de uma corrida no MESMO (pipeline, ODATE). Acontece de
verdade: rerun manual, disparo pela malha e agendamento por horários
específicos convivem no mesmo dia. A resolução NÃO recusa por padrão, porque
recusar quebraria o drill-down do caso mais comum e — pior — faria a tela de
baixo divergir da de cima: ``GET /malhas/{m}/execucao`` já pinta o pipeline com
a corrida vencedora de ``services.dependencias.mais_recente_da_data``. Descer
para uma corrida DIFERENTE da que foi pintada é exatamente a classe de defeito
registrada em services/dependencias.py (B2/D14/D15/N9: o painel contando uma
história e o motor outra).

Então a regra é: **escolher a MESMA corrida que o painel já escolheu, com a
MESMA função, e DECLARAR a escolha** — ``ambiguo=True``, a lista completa de
``candidatos`` e ``regra="mais_recente_da_data"``. Não é chute: é uma escolha
documentada e visível para quem consome.

Para o chamador que NÃO pode escolher — o rerun da F4 limpa tasks de um dag_run
concreto, e errar o run é destrutivo — existe ``estrito=True``: com mais de uma
candidata a resolução volta NÃO resolvida (motivo ``ambiguo``) com a lista, para
o gesto perguntar em vez de agir.

**IMPOSSÍVEL / INCOMPLETO** — o campo ``motivo``. Ver a nota de semântica em
``identidade_vazia``: ``motivo`` diz por que a identidade não ficou COMPLETA e
pode conviver com ``resolvido=True`` (ts_nodash conhecido, corrida não).
  • ``sem_linha_na_data``          — nenhuma corrida do pipeline naquele ODATE.
  • ``run_id_nao_traduzivel``      — a corrida existe, mas o run_id não é da
    forma ISO do Airflow e o Airflow não respondeu (ou não tem mais o run).
  • ``sem_dag_run_correspondente`` — a corrida existe na 067 mas o Airflow não
    tem dag_run com aquele run_id (run expurgado, DAG recriada, ou registro
    órfão gravado sem run correspondente).
  • ``sem_execucao_para_ts``       — sentido inverso: o ts_nodash não casa com
    nenhuma linha de etl_pipeline_execucao na janela consultada. As etapas
    continuam legíveis (``resolvido=True``); o que falta é o lado da 067.
  • ``migration_067_pendente``     — deploy parcial; ver degradação abaixo.
  • ``ambiguo``                    — só em modo estrito.

═══════════════════════════════════════════════════════════════════════════════
DEGRADAÇÃO SEM A MIGRATION 067
═══════════════════════════════════════════════════════════════════════════════
Sem ``etl_pipeline_execucao`` não existe a associação (corrida ↔ ODATE). O
módulo então responde pelo que dá: agrupa ``etl_job_execution`` pelos
``execution_id`` (= ts_nodash) cujo ``start_time`` cai na **janela do ODATE**
(``janela_odate``, derivada da MESMA virada de ``services.data_referencia``).
A identidade volta ``degradado=True``, ``run_id=None`` (não há como saber o
run_id sem a 067 nem sem o Airflow) e ``origem="etl_job_execution"``.

⚠️ Limite honesto do modo degradado: ``etl_job_execution.start_time`` é o
relógio de parede LOCAL do início da task (``pendulum.now(LOCAL_TZ)`` no
factory), não a logical date. Uma corrida cuja primeira task só começou depois
da virada é atribuída ao ODATE seguinte. É aproximação declarada — por isso
``degradado=True`` — e **não deve alimentar gesto destrutivo** (a F4 deve exigir
``resolvido and not degradado``).

═══════════════════════════════════════════════════════════════════════════════
CONVENÇÕES
═══════════════════════════════════════════════════════════════════════════════
• Placeholder ``?`` (pyodbc — árvore api/). Em dags/ é ``%s`` (pymssql):
  trocar dá "Incorrect syntax near '?'" — o GOTCHA registrado do projeto.
• Todas as funções recebem ``cur`` (cursor aberto); o CHAMADOR é dono da
  transação e da conexão. **Nenhuma função deste módulo faz I/O de rede**: a
  leitura do Airflow fica no router (que é quem tem o client, o timeout e a
  política de degradação) e entra aqui pela função PURA
  ``completa_com_airflow``. Isso mantém o módulo testável sem Airflow.
• Comparação de nome de pipeline/job é sempre case-insensitive
  (``casefold``): a colação do banco é CI e a grafia gravada diverge — o
  incidente da PR #236 (grafia dupla de pipeline_name) nasceu de dict
  case-sensitive em Python.
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime, time, timedelta

from services import data_referencia as dref
from services import dependencias as deps_svc

log = logging.getLogger("orquestra-api")

# ── Motivos de NÃO resolução (vocabulário fechado — a tela traduz, não inventa)
SEM_LINHA_NA_DATA = "sem_linha_na_data"
RUN_ID_NAO_TRADUZIVEL = "run_id_nao_traduzivel"
SEM_DAG_RUN = "sem_dag_run_correspondente"
SEM_EXECUCAO_PARA_TS = "sem_execucao_para_ts"
MIGRATION_067_PENDENTE = "migration_067_pendente"
AMBIGUO = "ambiguo"

# ── Origem de cada peça da identidade (de ONDE veio, para o consumidor julgar)
ORIGEM_067 = "etl_pipeline_execucao"
ORIGEM_RUN_ID = "run_id"
ORIGEM_AIRFLOW = "airflow"
ORIGEM_JOB_EXECUTION = "etl_job_execution"

# A regra de desempate — a MESMA do painel da malha (F9 §6 risco 6), aplicada
# pela MESMA função. Ver o bloco AMBIGUIDADE no docstring do módulo.
REGRA_MAIS_RECENTE = "mais_recente_da_data"

# Formas de run_id geradas pelo PRÓPRIO Airflow, em que a logical date está na
# string. ANCORADA nas duas pontas de propósito: os run_ids do Orquestra
# (`dep__<odate>__<pai>__<wallclock>`, `manual__<odate>__<pipe>__<wallclock>`)
# contêm dígitos parecidos e NÃO podem casar aqui — ver a armadilha no
# docstring do módulo.
_RUN_ID_ISO_RE = re.compile(
    r"^(?:scheduled|manual|backfill|dataset_triggered)__"
    r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[+-]\d{2}:\d{2}|Z)?)$"
)


# ═════════════════════════════ conversões puras ══════════════════════════════

def ts_nodash(iso) -> str:
    """logical date ISO do Airflow → ``ts_nodash`` (o execution_id da telemetria).

    ``'2026-07-05T03:00:00+00:00'`` → ``'20260705T030000'``.

    Implementação IDÊNTICA à antiga ``routers.execucoes._iso_to_ts_nodash``
    (que agora delega para cá): corta em 19 caracteres e remove ``-`` e ``:``.
    O corte cru é de propósito — preserva o comportamento de produção para
    entrada fora do formato (ex.: separador espaço vira ``'20260705 030000'``,
    que simplesmente não casa com nada). Mudar isso é mudar a semântica do
    rerun.
    """
    return (iso or "")[:19].replace("-", "").replace(":", "")


def ts_nodash_do_run_id(run_id) -> str | None:
    """run_id do Airflow → ts_nodash, **sem consultar o Airflow** — ou ``None``.

    Só traduz a forma que o próprio Airflow gera (``<tipo>__<ISO>``). Devolve
    ``None`` para os run_ids gerados pelo Orquestra: neles o timestamp embutido
    é relógio LOCAL, e traduzi-lo daria um ts_nodash deslocado do fuso (a
    armadilha comprovada no docstring do módulo). ``None`` significa
    "pergunte ao Airflow", nunca "chute".
    """
    m = _RUN_ID_ISO_RE.match(str(run_id or "").strip())
    return ts_nodash(m.group(1)) if m else None


def escolhe_dag_run(runs: list, exec_id: str) -> dict:
    """Escolhe o dag_run correspondente a ``exec_id`` (ts_nodash).

    Casa a logical date com o ts_nodash; sem match, mantém o **fallback legado**
    (1º run terminado da lista, que vem ordenada por ``-execution_date``; senão
    o mais recente). Corpo movido de ``routers.execucoes._escolhe_dag_run`` SEM
    alteração de semântica — é o caminho do rerun em produção.
    """
    if exec_id:
        for run in runs:
            logical = run.get("logical_date") or run.get("execution_date") or ""
            if ts_nodash(logical) == exec_id:
                return run
    for run in runs:
        if run.get("state") in ("failed", "success"):
            return run
    return runs[0]


def dag_run_por_id(runs: list, run_id: str) -> dict | None:
    """O dag_run cujo ``dag_run_id`` é exatamente ``run_id``, ou ``None``.

    Match EXATO (o run_id é a chave do Airflow) — sem fallback: aqui "não
    achei" é resposta legítima e vira o motivo ``sem_dag_run_correspondente``.
    """
    alvo = str(run_id or "").strip()
    if not alvo:
        return None
    for run in runs:
        if str(run.get("dag_run_id") or "").strip() == alvo:
            return run
    return None


def janela_odate(data_ref: date, virada=None) -> tuple:
    """Intervalo ``[inicio, fim)`` de relógio de parede que cai no ODATE ``data_ref``.

    É a INVERSA de ``services.data_referencia.calcular`` — e o teste de paridade
    (tests/test_execucao_identidade.py) prova isso nas duas bordas: todo momento
    dentro da janela tem ``calcular(momento, virada) == data_ref`` e todo momento
    imediatamente fora, não.

      • virada 00:00 (padrão): ``[D 00:00, D+1 00:00)`` — o dia do calendário;
      • virada V ≠ 00:00:      ``[D-1 V, D V)`` — porque ``calcular`` empurra
        para o dia seguinte tudo que acontece a partir de V.

    Usada só no modo degradado (sem a 067), para filtrar ``etl_job_execution``
    por ``start_time``.
    """
    v = dref.parse_virada(virada)
    if v == dref.VIRADA_PADRAO:
        return (datetime.combine(data_ref, time(0, 0)),
                datetime.combine(data_ref + timedelta(days=1), time(0, 0)))
    return (datetime.combine(data_ref - timedelta(days=1), v),
            datetime.combine(data_ref, v))


# ═════════════════════════════ o dict de identidade ══════════════════════════

def identidade_vazia(motivo: str | None = None, **extra) -> dict:
    """O molde da identidade — TODAS as chaves sempre presentes.

    ⚠️ **Semântica exata de ``resolvido`` e ``motivo``** (elas NÃO são o
    inverso uma da outra, e confundi-las é o erro fácil aqui):

      ``resolvido=True``  ⇔  **o ts_nodash é conhecido**. É a única chave que
      abre ``etl_job_execution``, ou seja: dá para listar as etapas. Nada mais.

      ``dag_run_id`` (== ``run_id``) **não nulo** ⇔ dá para AGIR no Airflow.
      É o que a F4 exige para reexecutar; a F3, que só desenha, não precisa.

      ``motivo``  ⇔  por que a identidade não ficou **COMPLETA**. Pode vir
      preenchido JUNTO com ``resolvido=True`` — o caso legítimo é "sei qual é o
      ts_nodash (e portanto as etapas), mas não achei a corrida correspondente
      na 067". Quem lê deve olhar o campo que precisa, não inferir um do outro.

    Chaves:
      ``resolvido``   bool  — o ts_nodash é conhecido? (ver acima)
      ``ts_nodash``   str?  — chave de ``etl_job_execution``
      ``run_id``      str?  — chave de ``etl_pipeline_execucao``
      ``dag_run_id``  str?  — o mesmo valor de run_id, nomeado como o Airflow
                              o chama (é o que a F4 manda no clearTaskInstances)
      ``logical_date``str?  — ISO cru do Airflow, quando conhecido
      ``data_referencia`` date? — o ODATE da corrida, quando conhecido
      ``origem``      str?  — de onde a tradução veio (constantes ORIGEM_*)
      ``ambiguo``     bool  — havia mais de uma corrida candidata?
      ``candidatos``  list  — TODAS as corridas candidatas (não só a vencedora)
      ``regra``       str?  — a regra de desempate aplicada, quando ambíguo
      ``degradado``   bool  — resolvido por aproximação (sem a 067)
      ``motivo``      str?  — por que não ficou completa (constantes do módulo)
    """
    base = {
        "resolvido": False,
        "ts_nodash": None,
        "run_id": None,
        "dag_run_id": None,
        "logical_date": None,
        "data_referencia": None,
        "origem": None,
        "ambiguo": False,
        "candidatos": [],
        "regra": None,
        "degradado": False,
        "motivo": motivo,
    }
    base.update(extra)
    return base


def precisa_airflow(ident: dict) -> bool:
    """A identidade só fecha com uma leitura do Airflow?

    True quando falta o ts_nodash mas há um run_id para perguntar (o caso comum:
    run_id gerado pelo Orquestra), ou quando falta o run_id mas há ts_nodash (o
    sentido inverso, vindo do Dashboard). O router usa isto para decidir se paga
    o custo da chamada.

    **Modo degradado nunca pede rede.** Sem a 067 a resposta já é assumidamente
    aproximada e o ponto do deploy parcial é depender do MÍNIMO: o Airflow
    poderia devolver o run_id, mas uma resposta meio-degradada/meio-exata seria
    mais difícil de ler do que uma degradada e declarada. Consequência aceita e
    registrada: em modo degradado o `dag_run_id` fica nulo e a F4 não age —
    exatamente o que a spec pede para gesto destrutivo sobre dado aproximado.

    Também não pede rede quando não há o que perguntar: sem corrida na data,
    sem a 067, ou em recusa por ambiguidade (modo estrito).
    """
    if ident.get("degradado"):
        return False
    if ident.get("motivo") in (MIGRATION_067_PENDENTE, SEM_LINHA_NA_DATA, AMBIGUO):
        return False
    tem_ts = bool(ident.get("ts_nodash"))
    tem_run = bool(ident.get("run_id"))
    return (tem_run and not tem_ts) or (tem_ts and not tem_run)


def completa_com_airflow(ident: dict, runs: list) -> dict:
    """Fecha a identidade com a lista de dag_runs — **função PURA**.

    O router faz o HTTP (``GET /api/v1/dags/{dag}/dagRuns``) e entrega a lista
    aqui. Assim o módulo continua testável sem Airflow e o router continua dono
    do timeout e da degradação.

    Dois sentidos:
      • tem ``run_id``, falta ``ts_nodash`` → acha o dag_run por id e converte a
        logical date (o caminho dos run_ids do Orquestra);
      • tem ``ts_nodash``, falta ``run_id`` → acha o dag_run cuja logical date
        casa e pega o ``dag_run_id``.

    O Airflow é a AUTORIDADE: se o ts_nodash já tinha sido derivado da string do
    run_id e o Airflow discorda, o do Airflow vence e a divergência vai para o
    log (é sintoma de run_id fora do padrão, não algo para engolir).

    Devolve um dict NOVO (não muta a entrada).
    """
    novo = dict(ident)
    novo["candidatos"] = list(ident.get("candidatos") or [])
    runs = runs or []

    if novo.get("run_id"):
        run = dag_run_por_id(runs, novo["run_id"])
        if run is None:
            if not novo.get("ts_nodash"):
                novo["motivo"] = SEM_DAG_RUN
            return novo
        logical = run.get("logical_date") or run.get("execution_date") or ""
        ts = ts_nodash(logical)
        if not ts:
            return novo
        anterior = novo.get("ts_nodash")
        if anterior and anterior != ts:
            log.warning(
                "[IDENT] ts_nodash derivado do run_id (%s) diverge do Airflow "
                "(%s) para run_id=%s — vale o do Airflow", anterior, ts,
                novo["run_id"])
        novo["ts_nodash"] = ts
        novo["logical_date"] = logical or None
        novo["resolvido"] = True
        novo["motivo"] = None
        novo["origem"] = _com_origem(novo.get("origem"), ORIGEM_AIRFLOW)
        return novo

    if novo.get("ts_nodash"):
        if not runs:
            return novo
        run = escolhe_dag_run(runs, novo["ts_nodash"])
        logical = run.get("logical_date") or run.get("execution_date") or ""
        # `escolhe_dag_run` tem fallback legado (para não mudar o rerun); aqui
        # só aceitamos o MATCH EXATO — resolver identidade pelo "1º terminado"
        # seria exatamente o chute que este módulo existe para não dar.
        if ts_nodash(logical) != novo["ts_nodash"]:
            novo["motivo"] = SEM_DAG_RUN
            return novo
        novo["run_id"] = run.get("dag_run_id")
        novo["dag_run_id"] = run.get("dag_run_id")
        novo["logical_date"] = logical or None
        novo["origem"] = _com_origem(novo.get("origem"), ORIGEM_AIRFLOW)
        novo["motivo"] = None
        novo["resolvido"] = True
    return novo


def _com_origem(atual, nova) -> str:
    """Acumula origens em ``a+b`` sem repetir — a identidade diz de onde veio
    CADA peça, e isso é o que permite ao consumidor julgar a confiança."""
    partes = [p for p in str(atual or "").split("+") if p]
    if nova not in partes:
        partes.append(nova)
    return "+".join(partes)


# ═════════════════════════ leituras de banco (com guardas) ═══════════════════

def tem_tabela_067(cur) -> bool:
    """``dbo.etl_pipeline_execucao`` existe? (uma consulta por request).

    Mesma disciplina de ``routers.malhas._tabelas_067_execucao``: deploy parcial
    degrada em vez de estourar "Invalid object name". Aqui a checagem é SÓ da
    tabela de execução — ``etl_dependencia_evento`` não é lida por este módulo.
    """
    try:
        cur.execute("SELECT OBJECT_ID('dbo.etl_pipeline_execucao', 'U')")
        row = cur.fetchone()
        return bool(row and row[0] is not None)
    except Exception as e:
        log.warning("[IDENT] checagem da tabela da migration 067 falhou: %s", e)
        return False


def pipeline_oficial(cur, pipeline_name):
    """Grafia registrada do pipeline em ``etl_pipeline``, ou ``None``.

    Regra da PR #236 (incidente 2026-08-01, "grafia dupla de pipeline_name"): a
    colação do banco é CI e casa qualquer caixa, mas o nome tem de ser
    canonizado ANTES de virar chave de dict em Python. Implementação extraída
    de ``routers.malhas._pipeline_oficial`` (que passou a delegar) — uma
    autoridade só.
    """
    cur.execute("SELECT pipeline_name FROM dbo.etl_pipeline WHERE pipeline_name = ?",
                (pipeline_name,))
    row = cur.fetchone()
    return (row[0] or "").strip() if row else None


def corridas_na_data(cur, pipeline: str, data_ref: date) -> list:
    """TODAS as linhas de ``etl_pipeline_execucao`` de (pipeline, ODATE).

    Sem ``TOP 1`` e sem ``ORDER BY``: a escolha da vencedora é do Python, pela
    função compartilhada com o painel da malha. Ordenar aqui criaria uma segunda
    regra de "mais recente" — o defeito D14/D15 registrado no projeto.
    """
    cur.execute(
        "SELECT execution_id, status, inicio, fim, disparado_por, motivo "
        "FROM dbo.etl_pipeline_execucao "
        "WHERE pipeline_name = ? AND data_referencia = ?",
        (pipeline, data_ref))
    return [{"execution_id": str(r[0] or ""), "status": r[1], "inicio": r[2],
             "fim": r[3], "disparado_por": r[4], "motivo": r[5]}
            for r in cur.fetchall()]


def corrida_por_run_id(cur, pipeline: str, run_id: str):
    """A linha de ``etl_pipeline_execucao`` de (pipeline, run_id), ou ``None``.

    É a peça que fecha o SENTIDO INVERSO: quem entra pelo ts_nodash e só
    descobre o run_id perguntando ao Airflow precisa de uma segunda passada na
    067 para recuperar o ODATE e o status da corrida. Sem ela a resposta volta
    com ``data_referencia`` nula — os run_ids do Orquestra não são traduzíveis
    pela string, então a varredura de ``resolve_por_ts_nodash`` não casa nada.
    """
    run_id = str(run_id or "").strip()
    if not run_id or not tem_tabela_067(cur):
        return None
    cur.execute(
        "SELECT data_referencia, status, inicio, fim, disparado_por, motivo "
        "FROM dbo.etl_pipeline_execucao "
        "WHERE pipeline_name = ? AND execution_id = ?",
        (pipeline, run_id))
    row = cur.fetchone()
    if row is None:
        return None
    return {"execution_id": run_id, "data_referencia": row[0], "status": row[1],
            "inicio": row[2], "fim": row[3], "disparado_por": row[4],
            "motivo": row[5]}


def aplica_corrida(ident: dict, corrida) -> dict:
    """Enxerta a corrida da 067 numa identidade já resolvida (dict NOVO).

    Preserva o que a identidade já sabia (``logical_date``, ``ts_nodash``) e só
    acrescenta o lado da 067 — ODATE, candidato e origem. `corrida` ``None``
    devolve a identidade intacta: não achar a corrida não apaga o que já se
    sabe.
    """
    novo = dict(ident)
    novo["candidatos"] = list(ident.get("candidatos") or [])
    if corrida is None:
        return novo
    novo["data_referencia"] = corrida.get("data_referencia")
    novo["candidatos"] = [_candidato(corrida)]
    novo["origem"] = _com_origem(novo.get("origem"), ORIGEM_067)
    novo["motivo"] = None
    return novo


def _candidato(linha: dict) -> dict:
    """Corrida candidata, no formato que vai para ``candidatos`` da identidade
    (o suficiente para a tela dizer "há N corridas hoje; esta é a mais recente"
    e para o gesto da F4 oferecer a escolha)."""
    return {
        "run_id": linha.get("execution_id") or None,
        "status": linha.get("status"),
        "inicio": linha.get("inicio"),
        "fim": linha.get("fim"),
        "disparado_por": linha.get("disparado_por"),
    }


# ═══════════════════════════ resolução — os dois sentidos ════════════════════

def resolve_por_odate(cur, pipeline: str, data_ref: date, *,
                      virada=None, estrito: bool = False) -> dict:
    """(pipeline, ODATE) → identidade. **O sentido que a malha fala.**

    Caminho normal (com a 067): pega as corridas do dia; com mais de uma,
    aplica ``mais_recente_da_data`` — a MESMA regra e a MESMA função do painel
    de ``GET /malhas/{m}/execucao`` — e DECLARA ``ambiguo=True`` + ``candidatos``.
    Com ``estrito=True``, mais de uma corrida devolve NÃO resolvido (motivo
    ``ambiguo``): é o modo para gesto destrutivo (rerun da F4), que deve
    perguntar em vez de escolher.

    Sem a 067: cai em ``_resolve_degradado`` (aproximação declarada).

    O ts_nodash sai da string do run_id quando ele é da forma do Airflow; senão
    a identidade volta com ``motivo=run_id_nao_traduzivel`` e
    ``precisa_airflow()`` True — o router completa com ``completa_com_airflow``.
    """
    if not tem_tabela_067(cur):
        log.warning("[IDENT] migration 067 ausente — identidade de '%s' em %s "
                    "resolvida em modo degradado", pipeline, data_ref)
        return _resolve_degradado(cur, pipeline, data_ref, virada=virada,
                                  estrito=estrito)

    linhas = corridas_na_data(cur, pipeline, data_ref)
    if not linhas:
        return identidade_vazia(SEM_LINHA_NA_DATA, data_referencia=data_ref)

    candidatos = [_candidato(l) for l in linhas]
    ambiguo = len(linhas) > 1
    if ambiguo and estrito:
        return identidade_vazia(AMBIGUO, data_referencia=data_ref,
                                ambiguo=True, candidatos=candidatos,
                                origem=ORIGEM_067)

    vencedora = deps_svc.mais_recente_da_data(linhas)
    run_id = vencedora["execution_id"] or None
    ts = ts_nodash_do_run_id(run_id)
    return identidade_vazia(
        None if ts else RUN_ID_NAO_TRADUZIVEL,
        resolvido=bool(ts),
        ts_nodash=ts,
        run_id=run_id,
        dag_run_id=run_id,
        data_referencia=data_ref,
        origem=_com_origem(ORIGEM_067, ORIGEM_RUN_ID) if ts else ORIGEM_067,
        ambiguo=ambiguo,
        candidatos=candidatos,
        regra=REGRA_MAIS_RECENTE if ambiguo else None,
    )


def resolve_por_run_id(cur, pipeline: str, run_id: str) -> dict:
    """(pipeline, run_id) → identidade.

    Traduz o run_id pela string quando dá; sempre tenta enriquecer com a linha
    da 067 daquele run_id (para trazer o ODATE e o status da corrida). Sem a
    067, devolve o que a string permitir — nada mais.
    """
    run_id = str(run_id or "").strip()
    ts = ts_nodash_do_run_id(run_id)
    ident = identidade_vazia(
        None if ts else RUN_ID_NAO_TRADUZIVEL,
        resolvido=bool(ts),
        ts_nodash=ts,
        run_id=run_id or None,
        dag_run_id=run_id or None,
        origem=ORIGEM_RUN_ID if ts else None,
    )
    if not tem_tabela_067(cur):
        ident["degradado"] = True
        return ident
    corrida = corrida_por_run_id(cur, pipeline, run_id)
    if corrida is None:
        return ident
    enxertada = aplica_corrida(ident, corrida)
    # `aplica_corrida` limpa o motivo (achou a corrida); mas se o ts_nodash
    # continua desconhecido, o motivo original vale — a identidade segue
    # incompleta pelo lado do Airflow.
    if not enxertada.get("ts_nodash"):
        enxertada["motivo"] = RUN_ID_NAO_TRADUZIVEL
    return enxertada


def resolve_por_ts_nodash(cur, pipeline: str, ts: str, *,
                          run_id: str | None = None) -> dict:
    """ts_nodash → a linha de ``etl_pipeline_execucao`` correspondente.

    **O sentido inverso** (o que o Dashboard tem em mãos: ele conhece o
    ``execution_id`` da telemetria, não o ODATE).

    Como a 067 guarda o run_id — e não o ts_nodash — o casamento é feito assim:
      1. se o chamador já resolveu o ``run_id`` no Airflow, casa por igualdade
         (caminho exato, sem heurística);
      2. senão, varre as corridas do pipeline numa janela de ±1 dia em torno da
         data do ts_nodash e casa as que forem traduzíveis pela string.

    **Por que ±1 dia:** o ts_nodash é a logical date em UTC e o ODATE é local
    (America/Sao_Paulo, UTC-3) deslocado pela virada — o ODATE de uma corrida
    fica sempre em ``[data(ts) - 1, data(ts)]``. A janela usa ±1 nos dois lados
    por folga; ela só LIMITA a varredura, nunca escolhe.

    Sem match, o ``motivo`` fica ``sem_execucao_para_ts`` com ``candidatos``
    preenchido — o chamador vê o que existia e por que nada casou. Note que
    ``resolvido`` continua True: o ts_nodash veio do chamador e já abre as
    etapas; o que faltou foi o lado da 067 (ver a nota em ``identidade_vazia``).
    Esse caso é REAL em produção pré-retomada: a 067 existe mas nada a alimenta,
    então todo drill-down por execution_id cai aqui — e tem de funcionar.
    """
    ts = str(ts or "").strip()
    ident = identidade_vazia(
        SEM_EXECUCAO_PARA_TS,
        resolvido=bool(ts),
        ts_nodash=ts or None,
        run_id=run_id or None,
        dag_run_id=run_id or None,
        origem=ORIGEM_JOB_EXECUTION if ts else None,
    )
    if not ts:
        ident["resolvido"] = False
        return ident
    if not tem_tabela_067(cur):
        ident["degradado"] = True
        ident["motivo"] = MIGRATION_067_PENDENTE
        return ident

    dia = _data_do_ts_nodash(ts)
    if dia is None:
        return ident
    cur.execute(
        "SELECT execution_id, status, inicio, fim, disparado_por, "
        "       motivo, data_referencia "
        "FROM dbo.etl_pipeline_execucao "
        "WHERE pipeline_name = ? AND data_referencia BETWEEN ? AND ?",
        (pipeline, dia - timedelta(days=1), dia + timedelta(days=1)))
    linhas = [{"execution_id": str(r[0] or ""), "status": r[1], "inicio": r[2],
               "fim": r[3], "disparado_por": r[4], "motivo": r[5],
               "data_referencia": r[6]} for r in cur.fetchall()]
    ident["candidatos"] = [_candidato(l) for l in linhas]

    alvo = str(run_id or "").strip()
    if alvo:
        # Caminho 1: o chamador já resolveu o run_id no Airflow — igualdade pura.
        casadas = [l for l in linhas if l["execution_id"] == alvo]
    else:
        # Caminho 2: sem Airflow, só casam as corridas de run_id traduzível.
        casadas = [l for l in linhas
                   if ts_nodash_do_run_id(l["execution_id"]) == ts]
    if not casadas:
        return ident
    if len(casadas) > 1:
        # Não deveria acontecer: o índice único da 067 é
        # (pipeline_name, data_referencia, execution_id) e o run_id é único no
        # Airflow. Se acontecer, é dado sujo — declarar, nunca escolher.
        ident["ambiguo"] = True
        ident["motivo"] = AMBIGUO
        ident["resolvido"] = False
        return ident
    vencedora = casadas[0]
    ident["run_id"] = vencedora["execution_id"] or None
    ident["dag_run_id"] = ident["run_id"]
    ident["data_referencia"] = vencedora["data_referencia"]
    ident["origem"] = _com_origem(ident.get("origem"), ORIGEM_067)
    ident["motivo"] = None
    ident["resolvido"] = True
    return ident


def _data_do_ts_nodash(ts: str):
    """``'20260803T124924'`` → ``date(2026, 8, 3)``; ``None`` se não for do
    formato (não estoura — entrada torta vira "não resolvido")."""
    try:
        return datetime.strptime(str(ts)[:8], "%Y%m%d").date()
    except (ValueError, TypeError):
        return None


def _resolve_degradado(cur, pipeline: str, data_ref: date, *,
                       virada=None, estrito: bool = False) -> dict:
    """Identidade sem a 067 — só o que ``etl_job_execution`` permite dizer.

    Agrupa por ``execution_id`` (= ts_nodash) as linhas cujo ``start_time`` cai
    na janela do ODATE e aplica a MESMA regra de desempate. ``run_id`` fica
    ``None`` (não há de onde tirar) e ``degradado=True`` — ver o limite honesto
    no docstring do módulo.
    """
    ini, fim = janela_odate(data_ref, virada)
    try:
        cur.execute(
            "SELECT execution_id, MIN(start_time) FROM dbo.etl_job_execution "
            "WHERE pipeline = ? AND start_time >= ? AND start_time < ? "
            "GROUP BY execution_id",
            (pipeline, ini, fim))
        linhas = [{"execution_id": str(r[0] or ""), "inicio": r[1],
                   "status": None, "fim": None, "disparado_por": None}
                  for r in cur.fetchall()]
    except Exception as e:
        log.warning("[IDENT] modo degradado falhou para '%s' em %s: %s",
                    pipeline, data_ref, e)
        return identidade_vazia(MIGRATION_067_PENDENTE, degradado=True,
                                data_referencia=data_ref)
    if not linhas:
        return identidade_vazia(SEM_LINHA_NA_DATA, degradado=True,
                                data_referencia=data_ref)
    candidatos = [_candidato(l) for l in linhas]
    ambiguo = len(linhas) > 1
    if ambiguo and estrito:
        return identidade_vazia(AMBIGUO, degradado=True, ambiguo=True,
                                candidatos=candidatos, data_referencia=data_ref,
                                origem=ORIGEM_JOB_EXECUTION)
    vencedora = deps_svc.mais_recente_da_data(linhas)
    return identidade_vazia(
        None,
        resolvido=True,
        ts_nodash=vencedora["execution_id"] or None,
        data_referencia=data_ref,
        origem=ORIGEM_JOB_EXECUTION,
        ambiguo=ambiguo,
        candidatos=candidatos,
        regra=REGRA_MAIS_RECENTE if ambiguo else None,
        degradado=True,
    )


# ═════════════════════ etapas: execução + desenho, compostas ═════════════════

def etapas_executadas(cur, pipeline: str, ts: str) -> list:
    """Linhas de ``etl_job_execution`` da execução ``ts`` do pipeline.

    Filtra por ``(execution_id, pipeline)`` — o índice
    ``IX_etl_job_execution_execution_id_pipeline`` cobre exatamente esse par, e
    o pipeline no WHERE é obrigatório: a chave da telemetria inclui o pipeline
    porque o MESMO ts_nodash aparece em pipelines diferentes disparados na
    mesma logical date (visto no dev: ACF_C e ACF_D com 20260803T140715).
    """
    cur.execute(
        "SELECT job_name, task_id, status, start_time, end_time, "
        "       duration_seconds, status_code, attempt, log_file, host "
        "FROM dbo.etl_job_execution "
        "WHERE execution_id = ? AND pipeline = ? "
        "ORDER BY start_time, job_name",
        (ts, pipeline))
    return [{"job_name": r[0], "task_id": r[1], "status": r[2],
             "inicio": r[3], "fim": r[4],
             "duration_seconds": int(r[5]) if r[5] is not None else None,
             "status_code": r[6], "attempt": r[7], "log_file": r[8],
             "host": r[9]}
            for r in cur.fetchall()]


def tem_tabela_tentativas(cur) -> bool:
    """``dbo.etl_job_execution_tentativa`` (migration 078) existe?

    Mesma disciplina de ``tem_tabela_067``: deploy parcial DEGRADA — sem a
    tabela o drill-down mostra só a tentativa corrente, que é exatamente o que
    ele mostrava antes da F4. Qualquer falha conta como ausente.
    """
    try:
        cur.execute("SELECT OBJECT_ID('dbo.etl_job_execution_tentativa', 'U')")
        row = cur.fetchone()
        return bool(row and row[0] is not None)
    except Exception as e:  # noqa: BLE001
        log.warning("[IDENT] checagem da tabela da migration 078 falhou: %s", e)
        return False


def tentativas_anteriores(cur, pipeline: str, ts: str) -> list:
    """Tentativas JÁ SUPERADAS da execução ``ts`` — o histórico da 078.

    ⚠️ **Onde mora cada tentativa** (decisão de desenho da F4, registrada por
    inteiro no cabeçalho de sql/migrations/078): ``etl_job_execution`` continua
    com UMA linha por etapa — a tentativa CORRENTE, agora com ``attempt``
    preenchido. Toda tentativa superada é arquivada em
    ``etl_job_execution_tentativa`` pela própria SP de telemetria. Assim os ~17
    agregados de produção que somam/contam sobre ``etl_job_execution``
    (dashboard, SLA, cards do Teams, Gestão de Falhas) continuam vendo
    exatamente o que viam — e nada se perde.

    A linha do tempo do dia de uma etapa é, portanto,
    ``tentativas_anteriores(...) + [a linha corrente]``.

    Devolve ``[]`` (nunca levanta) sem a tabela: o drill-down não pode quebrar
    por causa de um deploy parcial.
    """
    if not tem_tabela_tentativas(cur):
        return []
    try:
        cur.execute(
            "SELECT job_name, task_id, attempt, status, start_time, end_time, "
            "       duration_seconds, status_code, log_file, host, arquivado_em "
            "FROM dbo.etl_job_execution_tentativa "
            "WHERE execution_id = ? AND pipeline = ? "
            "ORDER BY job_name, attempt",
            (ts, pipeline))
        return [{"job_name": r[0], "task_id": r[1], "attempt": r[2],
                 "status": r[3], "inicio": r[4], "fim": r[5],
                 "duration_seconds": int(r[6]) if r[6] is not None else None,
                 "status_code": r[7], "log_file": r[8], "host": r[9],
                 "arquivado_em": r[10]}
                for r in cur.fetchall()]
    except Exception as e:  # noqa: BLE001 — histórico ausente nunca derruba a tela
        log.warning("[IDENT] tentativas anteriores de '%s'/%s indisponiveis: %s",
                    pipeline, ts, e)
        return []


def etapas_do_desenho(cur, pipeline: str) -> list:
    """Etapas do DESENHO atual do pipeline: ``job_name``, ``job_type``,
    ``execution_order`` e ``depends_on_jobs`` (CSV → lista).

    É o mínimo para desenhar o grafo (o canvas usa ``job_name`` como id de nó e
    as arestas vêm de ``depends_on_jobs``). O payload COMPLETO do canvas
    (layout, condition, params…) continua sendo de
    ``GET /pipelines/{p}/fluxo`` — aqui não se duplica aquilo.

    Guarda de coluna igual à do ``/fluxo``: sem a migration 038 o SELECT direto
    falharia e um pipeline EXISTENTE apareceria vazio.
    """
    try:
        cur.execute(
            "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME='etl_pipeline_job'")
        cols = {str(r[0]).lower() for r in cur.fetchall()}
    except Exception:
        cols = set()
    sel_deps = "depends_on_jobs" if "depends_on_jobs" in cols else "NULL"
    try:
        cur.execute(
            "SELECT job_name, ISNULL(job_type,'datastage'), "
            f"CAST(execution_order AS INT), {sel_deps} "
            "FROM dbo.etl_pipeline_job WHERE pipeline_name = ? "
            "ORDER BY execution_order, job_name",
            (pipeline,))
        rows = cur.fetchall()
    except Exception as e:
        log.warning("[IDENT] desenho de '%s' indisponível: %s", pipeline, e)
        return []
    return [{"job_name": r[0], "job_type": r[1], "execution_order": r[2],
             "depends_on_jobs": [d.strip() for d in str(r[3] or "").split(",")
                                 if d.strip()]}
            for r in rows]


def _chave_tentativa(e: dict) -> tuple:
    """Ordem entre linhas da MESMA etapa: ``attempt`` manda; empate (ou
    ``attempt`` nulo, o dado pré-078) desempata pelo início.

    ``attempt`` nulo vira 0 — linha antiga, sem número, perde de qualquer
    tentativa numerada. É a leitura honesta: se uma delas se declara tentativa
    2, a que não se declara nada é mais velha.
    """
    a = e.get("attempt")
    try:
        n = int(a) if a is not None else 0
    except (TypeError, ValueError):
        n = 0
    return (n, str(e.get("inicio") or ""))


def compor_etapas(desenho: list, executadas: list, anteriores: list | None = None) -> list:
    """Une DESENHO e EXECUÇÃO numa lista só — a regra de honestidade do §3.

    • Etapa do desenho SEM linha de execução → ``status=None`` e
      ``sem_execucao=True``. Nunca verde: a ausência de linha não é sucesso.
    • Etapa EXECUTADA que não está mais no desenho → entra no fim com
      ``no_desenho=False``. Acontece de verdade: o desenho é o de HOJE e a
      execução é a de ONTEM. Esconder essas linhas faria o canvas mentir por
      omissão sobre o que realmente rodou.

    O casamento é por ``job_name`` casefold (colação CI do banco × dict
    case-sensitive do Python — o incidente da PR #236).

    ⚠️ **F4 — a etapa mostra a tentativa MAIS RECENTE, com as anteriores
    junto.** Até a F3 o casamento era ``setdefault``, isto é, "a primeira linha
    que aparecer vence" — e como ``etapas_executadas`` ordena por
    ``start_time``, a primeira é a MAIS ANTIGA. Com tentativas acumuladas isso
    mostraria a tentativa que FALHOU depois de o operador já ter reexecutado e
    passado; o pior tipo de mentira que esta tela pode contar. Agora vence a de
    maior ``attempt`` (``_chave_tentativa``), explicitamente, sem depender da
    ordem em que as linhas chegaram.

    ``anteriores`` (histórico da 078) entra em cada etapa como ``tentativas``,
    da mais antiga para a mais nova, SEM a corrente — a tela monta a linha do
    tempo do dia juntando as duas. Ausente/vazio, o payload é o da F3 com
    ``tentativas: []``.
    """
    por_nome: dict = {}
    for e in executadas:
        k = str(e.get("job_name") or "").strip().casefold()
        atual = por_nome.get(k)
        if atual is None or _chave_tentativa(e) > _chave_tentativa(atual):
            por_nome[k] = e

    hist: dict = {}
    for t in (anteriores or []):
        k = str(t.get("job_name") or "").strip().casefold()
        hist.setdefault(k, []).append(t)
    for k in hist:
        hist[k].sort(key=_chave_tentativa)

    saida, usados = [], set()
    for no in desenho:
        chave = str(no.get("job_name") or "").strip().casefold()
        exec_ = por_nome.get(chave)
        usados.add(chave)
        saida.append(_etapa(no, exec_, no_desenho=True, anteriores=hist.get(chave)))
    for e in executadas:
        chave = str(e.get("job_name") or "").strip().casefold()
        if chave in usados:
            continue
        usados.add(chave)
        saida.append(_etapa(None, por_nome.get(chave) or e, no_desenho=False,
                            anteriores=hist.get(chave)))
    return saida


def _tentativa_json(t: dict) -> dict:
    """Uma tentativa anterior, no molde curto que a tela precisa para a linha
    do tempo (número, status, horários, duração e host). Sem `job_name`: ela já
    vive DENTRO da etapa."""
    return {
        "attempt": t.get("attempt"),
        "status": t.get("status"),
        "inicio": t.get("inicio"),
        "fim": t.get("fim"),
        "duration_seconds": t.get("duration_seconds"),
        "status_code": t.get("status_code"),
        "host": t.get("host"),
        "log_file": t.get("log_file"),
    }


def _etapa(no, exec_, *, no_desenho: bool, anteriores=None) -> dict:
    """Uma etapa do payload: identidade do nó + execução (ou a ausência dela)."""
    no = no or {}
    exec_ = exec_ or {}
    tentativas = [_tentativa_json(t) for t in (anteriores or [])]
    return {
        "job_name": no.get("job_name") or exec_.get("job_name"),
        "task_id": exec_.get("task_id") or no.get("job_name"),
        "job_type": no.get("job_type"),
        "execution_order": no.get("execution_order"),
        "depends_on_jobs": list(no.get("depends_on_jobs") or []),
        "no_desenho": no_desenho,
        "sem_execucao": not exec_,
        "status": exec_.get("status"),
        "inicio": exec_.get("inicio"),
        "fim": exec_.get("fim"),
        "duration_seconds": exec_.get("duration_seconds"),
        "status_code": exec_.get("status_code"),
        "attempt": exec_.get("attempt"),
        "log_file": exec_.get("log_file"),
        "host": exec_.get("host"),
        # F4: tentativas SUPERADAS (da mais antiga para a mais nova), sem a
        # corrente — que são os campos acima. Lista vazia = só houve uma.
        "tentativas": tentativas,
        "total_tentativas": len(tentativas) + (1 if exec_ else 0),
    }
