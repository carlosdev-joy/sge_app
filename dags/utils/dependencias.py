"""
dags/utils/dependencias.py — predicados e protocolo de disparo por dependência (F3).

Desenho: docs/retomada-f3-desenho.md §6 · Spec: docs/spec-dependencias-pipelines.md.

Mesma divisão do utils/data_referencia.py: o que é REGRA é puro (sem banco,
sem Airflow — testável sozinho); o que é ESTADO recebe `conn` (pymssql,
placeholder %s — árvore dags/) e o CHAMADOR é dono da transação: nenhuma
função abre conexão, commita ou faz rollback. Quem chama o claim commita
IMEDIATAMENTE depois (transação curta — os range locks do HOLDLOCK seguram
até o commit).

CONTRATO DE LEITURA (F2 §9, gravado na tabela e consumido aqui): a liberação
é EXISTS(pipeline=P AND data_referencia=D AND status='SUCESSO') — nunca
"linha mais recente", nunca COALESCE(inicio, criado_em), nenhuma ordenação
por criado_em em lugar nenhum deste módulo (D14, D15).

CONTRATO COM A F4 (guardiã): a guardiã reusa `dependentes_de` + `liberado` +
`reservar_corrida` com origem='guardia' e run_id `guardia__*` (novo_run_id);
a adoção de linhas AGUARDANDO_DEPENDENCIA é o caminho (a) do claim;
`ordenar_corrida` é o New Day. Nenhuma consulta paralela: se a guardiã (ou o
push) precisar de outra pergunta ao banco, ela entra AQUI.

CONTRATO COM A F5 (D29): o predicado de `liberado` é a referência canônica —
o endpoint /pipelines/dependencias/estado deverá portá-lo com teste de
paridade, como api/services/data_referencia.py fez com o canônico de dags/.
"""
from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta

# Sentinel de "não consegui perguntar" (≠ "condição não fechou"). liberado()
# o embute nos faltantes (D21: erro é NÃO liberado para DISPARO); quem toma
# decisão TERMINAL (fechamento NAO_LIBEROU da guardiã) deve checá-lo e ADIAR
# — fechar uma corrida liberada por erro transitório de consulta seria
# irrecuperável (achado da revisão adversarial da F4).
ERRO_CONSULTA = "erro na consulta:"

# ═════════════════════ puro (sem banco, sem Airflow) ════════════════════════


def cron_dow_para_weekday(dow) -> int:
    """Converte dia-da-semana de cron (0 OU 7 = domingo, 1 = segunda, ...)
    para o weekday() do Python (0 = segunda ... 6 = domingo).

    Conversão EXPLÍCITA e testada (D05): dow=0 É domingo — o padrão
    `int(x or 1)` da 1ª execução transformava domingo em segunda-feira.
    """
    d = int(dow) % 7
    return 6 if d == 0 else d - 1


def _weekdays_de_csv(csv):
    """CSV de dias no formato do cron ('1,3,5', com ranges '1-5' e '*') →
    set de weekday() do Python, ou None quando não há restrição.

    Token inválido é ignorado (tolerante): o pior caso é NÃO restringir por
    aquele token — o filho re-julga com as próprias constantes de qualquer
    forma (defesa em profundidade do §2.2).
    """
    texto = (str(csv or "")).strip()
    if not texto or texto == "*":
        return None
    dias: set[int] = set()
    for token in texto.split(","):
        token = token.strip()
        if not token or token == "*":
            continue
        try:
            if "-" in token:
                ini, fim = token.split("-", 1)
                for d in range(int(ini), int(fim) + 1):
                    dias.add(cron_dow_para_weekday(d))
            else:
                dias.add(cron_dow_para_weekday(int(token)))
        except (ValueError, TypeError):
            continue
    return dias or None


def dia_permitido(regras: dict, dia: date):
    """O `dia` (dia OPERACIONAL — o dia em que a corrida foi ordenada na
    origem, §1.1 do desenho) passa nas restrições de DIA do agendamento?

    Devolve (permitido, motivo). Julga SÓ dia — hora nunca entra aqui (regra
    de relógio é só de disparo por agenda, D03). É o MESMO predicado que o
    check_agenda do pipeline gerado executa e que o push usa de pré-filtro
    (paridade por construção, espírito do D29).

    `regras` = {somente_dias_uteis, schedule_type, schedule_dow,
    schedule_dom, dias_semana, dias_horarios_mes_dias} — chaves ausentes não
    restringem. A precedência espelha a do _build_cron do gerador:
    dias do mês (monthly_days_times) > weekly > monthly > biweekly >
    dias_semana (CSV); somente_dias_uteis soma-se a qualquer uma.

    Derivação SEMPRE com `is not None` — nunca `int(x or 1)`: dow=0 é
    domingo (D05); os defaults (dow 1, dom 1) são os MESMOS do cron gerado.
    """
    regras = regras or {}
    stype = str(regras.get("schedule_type") or "").lower().strip()
    dias_mes = regras.get("dias_horarios_mes_dias")
    if dias_mes:
        permitidos_mes = {int(d) for d in dias_mes}
        if dia.day not in permitidos_mes:
            return False, f"dia {dia.day} fora dos dias do mes configurados"
    elif stype == "weekly":
        dow = regras.get("schedule_dow")
        alvo = cron_dow_para_weekday(int(dow) if dow is not None else 1)
        if dia.weekday() != alvo:
            return False, f"{dia.isoformat()} fora do dia da semana agendado"
    elif stype == "monthly":
        dom = regras.get("schedule_dom")
        alvo_dom = int(dom) if dom is not None else 1
        if dia.day != alvo_dom:
            return False, f"dia {dia.day} fora do agendamento mensal (dia {alvo_dom})"
    elif stype == "biweekly":
        dom = regras.get("schedule_dom")
        d1 = int(dom) if dom is not None else 1
        if dia.day not in (d1, d1 + 15):
            return False, (f"dia {dia.day} fora do agendamento quinzenal "
                           f"(dias {d1} e {d1 + 15})")
    else:
        permitidos = _weekdays_de_csv(regras.get("dias_semana"))
        if permitidos is not None and dia.weekday() not in permitidos:
            return False, f"{dia.isoformat()} fora dos dias da semana configurados"
    if regras.get("somente_dias_uteis") and dia.weekday() >= 5:
        # Mesmo texto do check_agenda gerado (D58 não regride).
        return False, "fim de semana e pipeline somente dias uteis"
    return True, None


def montar_conf(data_ref: date, dia_operacional: date, pai: str) -> dict:
    """Conf do disparo por dependência — o schema do §7 num lugar só.

    data_referencia: a data DA CORRIDA DO PAI — o filho NÃO recalcula
    (herança, decisão nº 1 do usuário); dia_operacional: o dia contra o qual
    as regras de DIA julgam (§1.1); disparado_por: consumido pelo
    _disparado_por da F2. A cascata repassa os dois valores do próprio run —
    o rótulo e o dia da RAIZ atravessam a cadeia sem recálculo (D12).
    """
    return {
        "data_referencia": _como_iso(data_ref),
        "dia_operacional": _como_iso(dia_operacional),
        "disparado_por": str(pai),
    }


def novo_run_id(origem: str, data_ref: date, nome: str) -> str:
    """run_id calculado ANTES da reserva (contrato F2 §1: a linha nasce com
    execution_id preenchido e o MESMO valor vai ao disparo — reserva com
    NULL é proibida).

    Formato (§3.3): {origem}__{AAAA-MM-DD}__{nome[:60]}__{AAAAMMDDTHHMMSSffffff}
    (~100 chars — cabe no VARCHAR(250) da migration 072; NUNCA truncar em
    50: colidiria prefixos no índice único). origem='dep' no push;
    origem='guardia' é reservado à F4.
    """
    carimbo = datetime.now().strftime("%Y%m%dT%H%M%S%f")
    return f"{origem}__{_como_iso(data_ref)}__{str(nome)[:60]}__{carimbo}"


def candidatos_dia_operacional(agora: datetime, virada: time) -> list:
    """F4 §2.3 — os dias de calendário que podem ser o dia OPERACIONAL da
    corrida corrente de um predecessor com esta virada.

    Para virada v > 00:00, o dia de origem é ambíguo no corredor
    pós-meia-noite (o pai pode ter rodado ontem 23:30 ou hoje 01:00):

      virada == 00:00        -> [hoje]
      agora.time() >= virada -> [hoje]            (corrida de amanhã, ordenada hoje)
      senão                  -> [hoje - 1, hoje]  (corredor pós-meia-noite)

    O chamador julga `dia_permitido` por ALGUM candidato e prefere o mais
    antigo (o dia de origem provável) como dia_operacional do conf — é o que
    impede o sweep pós-meia-noite da guardiã de reabrir D06/D07 (Decisão 3).
    """
    hoje = agora.date()
    v = _como_time(virada) or time(0, 0)
    if v == time(0, 0) or agora.time() >= v:
        return [hoje]
    return [hoje - timedelta(days=1), hoje]


def instante_deadline(data_ref: date, hora_limite: time, virada: time) -> datetime:
    """F4 §5.1 — o instante REAL do deadline de uma corrida: `hora_limite`
    ancorada dentro do dia operacional [(D-1)@virada, D@virada), nunca a
    hora sozinha.

      virada == 00:00       -> data_ref @ hora_limite
      hora_limite >= virada -> (data_ref - 1) @ hora_limite  (trecho pré-meia-noite)
      senão                 -> data_ref @ hora_limite        (trecho pós-meia-noite)

    Sem a âncora de DATA, a linha de D=sábado criada sexta 21:00 com limite
    02:00 alertaria sexta 21:05. `virada` é a efetiva dos PREDECESSORES — a
    mesma que carimbou D. `hora_limite` é obrigatória (o deadline é opt-in:
    o chamador só chega aqui com a regra configurada).
    """
    v = _como_time(virada) or time(0, 0)
    limite = _como_time(hora_limite)
    if v == time(0, 0) or limite < v:
        return datetime.combine(data_ref, limite)
    return datetime.combine(data_ref - timedelta(days=1), limite)


def _como_iso(valor) -> str:
    """date/datetime → 'AAAA-MM-DD'; string já formatada passa direto."""
    if isinstance(valor, datetime):
        return valor.date().isoformat()
    if hasattr(valor, "isoformat"):
        return valor.isoformat()
    return str(valor).strip()


def _como_time(valor):
    """TIME do banco (time/datetime/'HH:MM[:SS]') → time; inválido → None
    ("sem regra" ≠ "regra às 00:00" — mesma filosofia do D35)."""
    if valor is None or valor == "":
        return None
    if isinstance(valor, time):
        return valor
    if isinstance(valor, datetime):
        return valor.time()
    texto = str(valor).strip()
    for formato in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(texto, formato).time()
        except ValueError:
            continue
    return None


def _dias_do_horarios_mes(raw):
    """dias_horarios_mes (JSON '[{"dia": 5, "horarios": [...]}, ...]') →
    lista ordenada dos DIAS, ou None. Só o dia interessa aqui: a parte de
    hora é regra de relógio e não se aplica a evento (D03)."""
    texto = (str(raw or "")).strip()
    if not texto:
        return None
    try:
        entradas = json.loads(texto)
    except (ValueError, TypeError):
        return None
    dias = set()
    for entrada in entradas if isinstance(entradas, list) else []:
        try:
            dias.add(int(entrada["dia"]))
        except (KeyError, TypeError, ValueError):
            continue
    return sorted(dias) or None


# ═════════════════════════════════ banco ════════════════════════════════════
# Todas recebem conn pymssql (%s); o chamador é dono da transação.


def dependentes_de(conn, pai: str) -> list:
    """Quem depende de `pai`? Seek em ix_dep_predecessor (067), só tipo
    PIPELINE (spec §9: JOB é reservado) e só dependente ATIVO.

    O pai não tem lista de filhos no código gerado — esta leitura ao vivo é
    o que faz um dependente novo valer no próximo fim do pai sem regeração.
    A grafia devolvida É o dag_id real (a 071 canonizou a tabela).
    F4: a guardiã usa esta MESMA pergunta na varredura.
    """
    cur = conn.cursor()
    cur.execute(
        "SELECT d.pipeline_name FROM dbo.etl_pipeline_dependencia d "
        "JOIN dbo.etl_pipeline p ON p.pipeline_name = d.pipeline_name "
        "WHERE d.depende_de = %s AND d.tipo = 'PIPELINE' AND p.active = 1",
        (pai,))
    return [r[0] for r in cur.fetchall()]


# ── Reabertura deliberada de corrida (F4 de docs/spec-operacao-nivel-etapa.md)
# A migration 078 acrescentou `substituida_em` a etl_pipeline_execucao. Uma
# corrida com esse carimbo foi APOSENTADA por um rerun com cascata pedido na
# tela, com dono e hora — e o motor passa a ignorá-la, exatamente como já
# ignora 'PULADO'. É o que faz a cascata acontecer pelo caminho NORMAL do
# motor: quando o pai reexecutado conclui, o push encontra a corrida do
# dependente aposentada, GANHA o claim e dispara com run_id novo e o MESMO
# ODATE. Nada é disparado fora do claim, e a linha antiga não é apagada nem
# reescrita — o histórico do dia fica inteiro.
#
# ⚠️ SÃO TRÊS AS PORTAS, e elas têm de concordar: `liberado()` (quem PODE
# rodar), `ordenar_corrida` (o que conta como "já há corrida na data") e
# `reservar_corrida` (o claim). A F4 ensinou só as duas últimas; a terceira
# ficou para trás e o dev provou o estrago em 2026-08-03 — ver o docstring de
# `liberado()`. Regra do módulo: cláusula de corrida substituída nova entra
# NAS TRÊS ou em nenhuma.
#
# ⚠️ POR QUE O FALLBACK, E NÃO UM PROBE DE COLUNA: este é o caminho mais quente
# do motor de dependências e ele roda em DAG já publicada (utils/ é importado em
# runtime, não inlinado no código gerado). Num deploy parcial — dags/ novo, banco
# ainda sem a 078 — a referência à coluna daria Msg 207 "Invalid column name" e
# derrubaria o push de TODO pipeline com dependente. Um probe por chamada
# custaria uma consulta extra em todo disparo; o fallback custa zero no caminho
# feliz, é preciso (só reage à mensagem que cita a coluna, nunca a um deadlock
# ou timeout, que continuam propagando) e se autocorrige assim que a migration
# entra, sem reiniciar worker.
_MARCA_078 = "substituida_em"

# ⚠️ CONTRATO COM A API (correção do achado "078 sim / dags não").
# `tem_coluna_substituida()` da API responde sobre o BANCO. Com as migrations
# aplicadas e o `dags/` AINDA ANTIGO, a API oferecia a cascata, carimbava as
# corridas (rowcount > 0), respondia "2 dependentes reabertos" — e o push
# antigo ignorava o carimbo: nenhum dependente rodava e as corridas ficavam
# aposentadas para sempre. Esta tupla é a resposta HONESTA à pergunta "o
# motor deployado entende o carimbo?": a API monta `dags/` read-only
# (docker-compose.yaml, orquestra-api) e LÊ esta declaração do arquivo — a
# mesma árvore que o scheduler e o worker importam.
#
# Regra: quem TIRAR a cláusula `substituida_em` de qualquer uma das três
# portas tira 'rerun_cascata_078' daqui no MESMO commit. A declaração vale o
# que o código faz — declarar capacidade que não existe é o defeito, não a
# cura. (Teste de amarração em tests/test_rerun_etapa_f4.py.)
CAPACIDADES = ("rerun_cascata_078",)


def _exec_com_fallback_078(cur, sql_078: str, sql_legado: str, params) -> bool:
    """Executa `sql_078`; se o banco ainda não tem a coluna da 078, repete com
    `sql_legado`. Devolve True quando caiu no legado (o chamador loga uma vez).

    Qualquer outro erro PROPAGA — degradar em silêncio um erro de banco seria
    a classe D21 (erro virando "pode disparar")."""
    try:
        cur.execute(sql_078, params)
        return False
    except Exception as e:  # noqa: BLE001 — reagimos SÓ ao Invalid column name da 078
        if _MARCA_078 not in str(e):
            raise
        cur.execute(sql_legado, params)
        return True


def liberado(conn, pipeline: str, data_ref: date):
    """Todos os predecessores de `pipeline` têm SUCESSO VIVO em `data_ref`?

    Devolve (liberado, faltantes). Contrato EXISTS do §9 da F2 (serve-se de
    ix_pipe_exec_cond): FALHA, EXECUTANDO, PULADO, ausência e SUCESSO em
    OUTRA data não liberam (D20); PULADO intercalado não mascara um SUCESSO
    existente (D14); nenhuma ordenação por criado_em (D15).

    ⚠️ **TERCEIRA PORTA DO MODELO DE CORRIDA (correção pós-F4).** Corrida com
    `substituida_em` NÃO conta como SUCESSO — a MESMA regra que
    `reservar_corrida` e `ordenar_corrida` já seguem. Sem esta cláusula a
    cascata do rerun tinha um buraco de dado velho: reaberto A→B→C, a corrida
    APOSENTADA de B continuava dizendo SUCESSO na data, a guardiã liberava C
    no ciclo seguinte e C rodava com a saída ANTIGA de B — e, pior, quando B
    reexecutava e publicava, o claim de C encontrava corrida viva e devolvia
    None: **C nunca mais rodava com o dado novo, sem volta no ODATE**
    (reproduzido no dev em 2026-08-03, cadeia de três níveis).

    As três portas têm de concordar sobre o que é uma corrida que conta:
    quem libera, quem ordena e quem reserva. Divergir entre elas é o que
    produz disparo cedo (libera sem reservar) ou corrida órfã (reserva sem
    liberar). Mesmo fallback das outras duas (`_exec_com_fallback_078`): sem a
    migration 078 o comportamento é o de antes, byte a byte.

    Qualquer exceção na consulta → NÃO liberado, com log [DEP] (D21: erro
    nunca vira "pode disparar"). Predicado canônico para F4 e F5/D29.
    """
    try:
        # Modo SEQUÊNCIA: a chave da pergunta deixa de ser o ODATE e passa a
        # ser o ciclo corrente. Tudo o mais é igual — inclusive a retenção do
        # Aguarde e o descarte de corrida substituída.
        if modo_sequencia(conn):
            cur = conn.cursor()
            cur.execute(SQL_LIBERADO_SEQ,
                        (pipeline, inicio_do_ciclo_corrente(conn)))
            faltantes = [_faltante(r) for r in cur.fetchall()]
            return (not faltantes), faltantes
        cur = conn.cursor()
        _com_retencao, legado = _exec_liberado(cur, (pipeline, data_ref))
        faltantes = [_faltante(r) for r in cur.fetchall()]
        if legado:
            print("[DEP] migration 078 ausente — liberacao segue a regra "
                  "anterior (corrida substituida ainda conta como SUCESSO)")
        return (not faltantes), faltantes
    except Exception as e:  # noqa: BLE001 — D21: erro é NÃO liberado, nunca silêncio
        print(f"[DEP] condicao de {pipeline} indisponivel ({e}) — tratada como NAO liberada")
        return False, [f"{ERRO_CONSULTA} {e}"[:200]]


def calendario_bloqueia(conn, calendario_nome: str, dia: date) -> bool:
    """O calendário bloqueia o `dia`? Consulta PARAMETRIZADA pelo dia
    operacional — nunca CAST(GETDATE()) (D06: a regra de calendário fala do
    dia da corrida, não do relógio). Exceção propaga: o chamador decide a
    degradação (o check_agenda gerado loga e segue)."""
    cur = conn.cursor()
    cur.execute(
        "SELECT TOP 1 1 FROM dbo.etl_calendario "
        "WHERE calendario_nome = %s AND data = %s",
        (calendario_nome, dia))
    return cur.fetchone() is not None


def config_dependente(conn, pipeline: str):
    """Config de disparo do candidato, lida ao vivo de etl_pipeline:
    {'regras_dia': <dict p/ dia_permitido>, 'nao_iniciar_antes': time|None}
    ou None se o pipeline não existir.

    A derivação das regras espelha a das constantes geradas no filho (teste
    de paridade em tests/) — pusher e filho julgam o MESMO predicado com o
    MESMO dia (§2.2). F4: a guardiã usa esta MESMA leitura antes de ordenar.
    """
    cur = conn.cursor()
    cur.execute(
        "SELECT schedule_type, schedule_dow, schedule_dom, dias_semana, "
        "dias_horarios_mes, somente_dias_uteis, nao_iniciar_antes, "
        "hora_limite_dependencia "
        "FROM dbo.etl_pipeline WHERE pipeline_name = %s",
        (pipeline,))
    row = cur.fetchone()
    if row is None:
        return None
    stype, dow, dom, dias_semana, dias_horarios_mes, dias_uteis, nia = row[:7]
    # F4 (aditivo): hora_limite_dependencia vira a chave 'hora_limite' — o
    # push a ignora; leitura TOLERANTE a linhas de 7 colunas para o contrato
    # da F3 (e os stubs dela) seguirem valendo sem emenda.
    hora_limite = row[7] if len(row) > 7 else None
    return {
        "regras_dia": {
            "somente_dias_uteis": bool(dias_uteis or 0),
            "schedule_type": (str(stype or "daily")).lower().strip(),
            "schedule_dow": int(dow) if dow is not None else None,
            "schedule_dom": int(dom) if dom is not None else None,
            "dias_semana": (str(dias_semana or "")).strip(),
            "dias_horarios_mes_dias": _dias_do_horarios_mes(dias_horarios_mes),
        },
        "nao_iniciar_antes": _como_time(nia),
        "hora_limite": _como_time(hora_limite),
    }


def reservar_corrida(conn, filho: str, data_ref: date, novo_run_id: str, origem: str):
    """Claim da corrida do dependente (§3.2) — devolve o run_id a disparar,
    ou None (perdi a corrida / já há corrida na data).

    O índice único NÃO arbitra (dois pais calculam run_ids diferentes e não
    colidem): o árbitro é o lock otimista por rowcount + anti-corrida
    serializable (UPDLOCK/HOLDLOCK) sobre (pipeline, data_referencia).

      (a) adota linha ordenada (AGUARDANDO_DEPENDENCIA → EXECUTANDO): o
          run_id devolvido é o execution_id QUE A LINHA JÁ TINHA — é a
          arbitragem push × guardiã do D18;
      (b) senão, INSERT condicional já com run_id e status EXECUTANDO
          (contrato F2 §1: reserva com NULL é proibida). PULADO não bloqueia
          o claim (status <> 'PULADO'): um blackout não mata a corrida para
          sempre (eco do D15). rowcount 0 → corrida existe → None (é a
          barreira final contra redisparo N×/ODATE, D14; FALHA também
          bloqueia — rerun é Clear do plantonista, D17).

    Reserva claimada distingue-se de corrida adotada por inicio IS NULL (o
    check_agenda do filho carimba inicio ao adotar). O chamador COMMITA
    imediatamente após (transação curta, fora da tx do SUCESSO do pai).
    F4: a guardiã chama com origem='guardia' e run_id guardia__*.

    F4 (rerun com cascata): corrida com `substituida_em` NÃO bloqueia — nos
    dois caminhos. Ver o bloco de comentário acima; sem a migration 078 o
    comportamento é o de antes, byte a byte.
    """
    cur = conn.cursor()
    legado = _exec_com_fallback_078(
        cur,
        "UPDATE e SET e.status='EXECUTANDO', e.disparado_por=%s, "
        "e.atualizado_em=GETDATE() "
        "OUTPUT inserted.execution_id "
        "FROM dbo.etl_pipeline_execucao e WITH (UPDLOCK, HOLDLOCK) "
        "WHERE e.pipeline_name=%s AND e.data_referencia=%s "
        "AND e.status='AGUARDANDO_DEPENDENCIA' AND e.substituida_em IS NULL",
        "UPDATE e SET e.status='EXECUTANDO', e.disparado_por=%s, "
        "e.atualizado_em=GETDATE() "
        "OUTPUT inserted.execution_id "
        "FROM dbo.etl_pipeline_execucao e WITH (UPDLOCK, HOLDLOCK) "
        "WHERE e.pipeline_name=%s AND e.data_referencia=%s "
        "AND e.status='AGUARDANDO_DEPENDENCIA'",
        (origem, filho, data_ref))
    if legado:
        print("[DEP] migration 078 ausente — reabertura de corrida indisponivel; "
              "claim segue a regra anterior")
    row = cur.fetchone()
    if row and row[0]:
        return row[0]
    _exec_com_fallback_078(
        cur,
        "INSERT INTO dbo.etl_pipeline_execucao "
        "(pipeline_name, data_referencia, execution_id, status, disparado_por) "
        "SELECT %s, %s, %s, 'EXECUTANDO', %s "
        "WHERE NOT EXISTS (SELECT 1 FROM dbo.etl_pipeline_execucao "
        "WITH (UPDLOCK, HOLDLOCK) "
        "WHERE pipeline_name=%s AND data_referencia=%s AND status <> 'PULADO' "
        "AND substituida_em IS NULL)",
        "INSERT INTO dbo.etl_pipeline_execucao "
        "(pipeline_name, data_referencia, execution_id, status, disparado_por) "
        "SELECT %s, %s, %s, 'EXECUTANDO', %s "
        "WHERE NOT EXISTS (SELECT 1 FROM dbo.etl_pipeline_execucao "
        "WITH (UPDLOCK, HOLDLOCK) "
        "WHERE pipeline_name=%s AND data_referencia=%s AND status <> 'PULADO')",
        (filho, data_ref, novo_run_id, origem, filho, data_ref))
    if cur.rowcount == 1:
        return novo_run_id
    return None


def ordenar_corrida(conn, filho: str, data_ref: date, run_id: str, origem: str) -> bool:
    """Ordena a corrida SEM disparar (§3.4): INSERT condicional em
    AGUARDANDO_DEPENDENCIA, mesmo NOT EXISTS do claim, run_id já calculado
    (linha nasce com run_id — contrato F2 §1).

    Devolve True se criou de fato; False = já havia corrida (idempotente —
    e o chamador não pode assumir ordenação, lição do D48). Usos: janela
    nao_iniciar_antes no push (outro pai — ou a guardiã, F4 — adota depois
    pelo caminho (a) do claim); New Day da F4. Esta linha AGUARDANDO é
    intencional e nunca sofre devolução.

    F4 (rerun com cascata): MESMO NOT EXISTS do claim, inclusive a cláusula
    `substituida_em IS NULL` — as duas portas têm de concordar sobre o que
    conta como "já há corrida na data", senão a janela nao_iniciar_antes
    contaria uma corrida aposentada e o push, não.
    """
    cur = conn.cursor()
    _exec_com_fallback_078(
        cur,
        "INSERT INTO dbo.etl_pipeline_execucao "
        "(pipeline_name, data_referencia, execution_id, status, disparado_por) "
        "SELECT %s, %s, %s, 'AGUARDANDO_DEPENDENCIA', %s "
        "WHERE NOT EXISTS (SELECT 1 FROM dbo.etl_pipeline_execucao "
        "WITH (UPDLOCK, HOLDLOCK) "
        "WHERE pipeline_name=%s AND data_referencia=%s AND status <> 'PULADO' "
        "AND substituida_em IS NULL)",
        "INSERT INTO dbo.etl_pipeline_execucao "
        "(pipeline_name, data_referencia, execution_id, status, disparado_por) "
        "SELECT %s, %s, %s, 'AGUARDANDO_DEPENDENCIA', %s "
        "WHERE NOT EXISTS (SELECT 1 FROM dbo.etl_pipeline_execucao "
        "WITH (UPDLOCK, HOLDLOCK) "
        "WHERE pipeline_name=%s AND data_referencia=%s AND status <> 'PULADO')",
        (filho, data_ref, run_id, origem, filho, data_ref))
    return cur.rowcount == 1


def devolver_reserva(conn, filho: str, data_ref: date, run_id: str,
                     veio_de_adocao: bool) -> None:
    """Devolução da reserva quando o disparo LEVANTA (§3.3, D16) — e SÓ
    nesse caso. A guarda `status='EXECUTANDO' AND inicio IS NULL` é a
    tradução de "corrida já adotada não é revertida" para o modelo com
    run_id (o texto original do D16 falava execution_id IS NULL porque vinha
    do modelo NULL, morto pelo contrato da F2).

      • veio_de_adocao=False (caminho b do claim): DELETE da reserva — se o
        run tiver sido criado apesar da exceção, o upsert da F2 recria a
        linha pela própria chave e converge para UMA linha (D13);
      • veio_de_adocao=True (caminho a): a linha volta a
        AGUARDANDO_DEPENDENCIA — a guardiã (F4) redispara no ciclo seguinte.
    """
    cur = conn.cursor()
    if veio_de_adocao:
        cur.execute(
            "UPDATE dbo.etl_pipeline_execucao "
            "SET status='AGUARDANDO_DEPENDENCIA', atualizado_em=GETDATE() "
            "WHERE pipeline_name=%s AND data_referencia=%s AND execution_id=%s "
            "AND status='EXECUTANDO' AND inicio IS NULL",
            (filho, data_ref, run_id))
    else:
        cur.execute(
            "DELETE FROM dbo.etl_pipeline_execucao "
            "WHERE pipeline_name=%s AND data_referencia=%s AND execution_id=%s "
            "AND status='EXECUTANDO' AND inicio IS NULL",
            (filho, data_ref, run_id))


# ═══════════════════ banco — F4 (guardiã) ═══════════════════════════════════
# As perguntas do ciclo da guardiã (docs/retomada-f4-desenho.md §9). Mesmo
# contrato: conn pymssql (%s), chamador dono da transação. Nenhuma delas
# decide liberação — a pergunta de liberação continua sendo SÓ `liberado()`.


def tabelas_067_presentes(conn) -> bool:
    """As três tabelas da migration 067 existem? (D52 — degradação limpa da
    guardiã: ausente qualquer uma, o ciclo encerra com log, sem exceção.)

    Mora aqui, e não na DAG, por exigência da Decisão 15: a sonda OBJECT_ID
    é SQL, e SQL não entra na DAG guardiã.
    """
    cur = conn.cursor()
    cur.execute(
        "SELECT OBJECT_ID('dbo.etl_pipeline_dependencia','U'), "
        "OBJECT_ID('dbo.etl_pipeline_execucao','U'), "
        "OBJECT_ID('dbo.etl_dependencia_evento','U')")
    row = cur.fetchone()
    return bool(row) and all(v is not None for v in row)


def dependentes_com_dependencia(conn) -> list:
    """Universo do New Day (F4 §3.1): pipelines ATIVOS com pelo menos uma
    dependência tipo PIPELINE. É a única lista de "previstos" que a guardiã
    conhece — quem não está aqui não é ordenado nem alertado."""
    cur = conn.cursor()
    cur.execute(
        "SELECT DISTINCT d.pipeline_name FROM dbo.etl_pipeline_dependencia d "
        "JOIN dbo.etl_pipeline p ON p.pipeline_name = d.pipeline_name "
        "WHERE d.tipo = 'PIPELINE' AND p.active = 1")
    return [r[0] for r in cur.fetchall()]


# ── SQL do predicado: uma consulta só, com a retenção do Aguarde dentro ─────
# A 2ª coluna é o id do Aguarde SEGURADO (migration 082) que compilou aquela
# linha. Trazê-la aqui — em vez de perguntar depois — mantém o contrato de UMA
# ida ao banco e faz a trava valer nas TRÊS portas de uma vez (push, guardiã e
# o painel consultam este mesmo predicado). A lição da F4 em forma de SQL:
# regra que mora numa porta só não protege.
#
# `_MARCA_082` é o que o fallback reconhece: sem a coluna (ou sem a tabela de
# nós), a consulta cai na versão sem retenção e o comportamento é o de antes.
_MARCA_082 = "retido_em"

_SELECT_RETENCAO = (
    ", (SELECT TOP 1 n.id FROM dbo.etl_malha_no n "
    "   WHERE n.id = dd.origem_no AND n.retido_em IS NOT NULL) AS aguarde_retido ")
_ONDE_SEM_SUCESSO_078 = (
    "AND NOT EXISTS (SELECT 1 FROM dbo.etl_pipeline_execucao e "
    "WHERE e.pipeline_name = dd.depende_de "
    "AND e.data_referencia = %s AND e.status = 'SUCESSO' "
    "AND e.substituida_em IS NULL)")
_ONDE_SEM_SUCESSO_LEGADO = (
    "AND NOT EXISTS (SELECT 1 FROM dbo.etl_pipeline_execucao e "
    "WHERE e.pipeline_name = dd.depende_de "
    "AND e.data_referencia = %s AND e.status = 'SUCESSO')")
# Com a 082, a linha entra na resposta por DOIS motivos: predecessor sem
# sucesso OU Aguarde segurado. Sem ela, só o primeiro.
SQL_LIBERADO_082 = (
    "SELECT dd.depende_de" + _SELECT_RETENCAO +
    "FROM dbo.etl_pipeline_dependencia dd "
    "WHERE dd.pipeline_name = %s AND dd.tipo = 'PIPELINE' "
    "AND (" + _ONDE_SEM_SUCESSO_078[4:] +
    " OR EXISTS (SELECT 1 FROM dbo.etl_malha_no n2 "
    "            WHERE n2.id = dd.origem_no AND n2.retido_em IS NOT NULL))")
# Modo SEQUÊNCIA (config `dependencia_modo_sequencia`): a pergunta deixa de
# ser "SUCESSO nesta data de referência" e passa a ser "SUCESSO NESTE ciclo".
# `ISNULL(fim, inicio)` porque uma corrida que concluiu sem carimbar fim ainda
# é um sucesso desta rodada; o corte vem de quem chama (relógio do BANCO).
_ONDE_SEM_SUCESSO_SEQ = (
    "AND NOT EXISTS (SELECT 1 FROM dbo.etl_pipeline_execucao e "
    "WHERE e.pipeline_name = dd.depende_de "
    "AND e.status = 'SUCESSO' AND e.substituida_em IS NULL "
    "AND ISNULL(e.fim, e.inicio) >= %s)")
SQL_LIBERADO_SEQ = (
    "SELECT dd.depende_de" + _SELECT_RETENCAO +
    "FROM dbo.etl_pipeline_dependencia dd "
    "WHERE dd.pipeline_name = %s AND dd.tipo = 'PIPELINE' "
    "AND (" + _ONDE_SEM_SUCESSO_SEQ[4:] +
    " OR EXISTS (SELECT 1 FROM dbo.etl_malha_no n2 "
    "            WHERE n2.id = dd.origem_no AND n2.retido_em IS NOT NULL))")

SQL_LIBERADO_078 = (
    "SELECT dd.depende_de FROM dbo.etl_pipeline_dependencia dd "
    "WHERE dd.pipeline_name = %s AND dd.tipo = 'PIPELINE' " +
    _ONDE_SEM_SUCESSO_078)
SQL_LIBERADO_LEGADO = (
    "SELECT dd.depende_de FROM dbo.etl_pipeline_dependencia dd "
    "WHERE dd.pipeline_name = %s AND dd.tipo = 'PIPELINE' " +
    _ONDE_SEM_SUCESSO_LEGADO)


_MODO_CACHE: dict = {}


def limpar_cache_modo() -> None:
    """Esquece o modo lido. Existe para TESTE e para quem quiser reavaliar no
    mesmo processo — em produção o cache morre com a task."""
    _MODO_CACHE.clear()


def modo_sequencia(conn) -> bool:
    """A liberação está em modo SEQUÊNCIA (ODATE fora da conta)?

    Lido de etl_app_config uma vez por PROCESSO: a task do Airflow é curta e
    avalia N dependentes — perguntar por filho seria N idas ao banco para uma
    resposta que não muda no meio do run. Trocar a chave vale no próximo run,
    que é o comportamento esperado de configuração.

    Ausente, ilegível ou banco fora → False (modo DATA, o de sempre): o
    interruptor nunca liga sozinho."""
    if "modo" in _MODO_CACHE:
        return _MODO_CACHE["modo"]
    valor = False
    try:
        cur = conn.cursor()
        cur.execute("SELECT config_value FROM dbo.etl_app_config "
                    "WHERE config_key = 'dependencia_modo_sequencia'")
        row = cur.fetchone()
        valor = bool(row) and str(row[0] or "").strip() in ("1", "true", "True")
    except Exception as e:  # noqa: BLE001
        print(f"[DEP] modo de liberacao indisponivel ({e}) — usando data de referencia")
    _MODO_CACHE["modo"] = valor
    if valor:
        print("[DEP] modo SEQUENCIA ligado — a liberacao olha o ciclo, nao o ODATE")
    return valor


def inicio_do_ciclo_corrente(conn) -> datetime:
    """Corte do ciclo para o modo sequência: a virada global mais recente, na
    régua do BANCO (é lá que `fim`/`inicio` são carimbados)."""
    agora = agora_do_banco(conn)
    try:
        cur = conn.cursor()
        cur.execute("SELECT config_value FROM dbo.etl_app_config "
                    "WHERE config_key = 'dependencia_hora_virada'")
        row = cur.fetchone()
        bruto = row[0] if row else None
    except Exception:  # noqa: BLE001 — sem config, meia-noite
        bruto = None
    v = _como_time(bruto) or time(0, 0)
    base = agora.date() if agora.time() >= v else agora.date() - timedelta(days=1)
    return datetime.combine(base, v)


def _exec_liberado(cur, params):
    """Executa o predicado no nível mais alto que o banco aguenta.

    Cascata 082 → 078 → legado. Sem ela, um banco sem a 082 receberia
    "Invalid column name 'retido_em'", o erro subiria e `liberado` devolveria
    NÃO-liberado para TODO mundo (D21) — a trava nova pararia a produção
    inteira em vez de segurar um Aguarde. Devolve (com_retencao, no_legado)."""
    try:
        cur.execute(SQL_LIBERADO_082, params)
        return True, False
    except Exception as e:  # noqa: BLE001 — só as marcas conhecidas degradam
        msg = str(e)
        if (_MARCA_082 not in msg and "etl_malha_no" not in msg
                and _MARCA_078 not in msg):
            raise
    return False, _exec_com_fallback_078(
        cur, SQL_LIBERADO_078, SQL_LIBERADO_LEGADO, params)

# Mensagem do faltante quando quem segura é o Aguarde, não o predecessor:
# dizer "aguardando PIPE_A" com PIPE_A já concluído mandaria o plantonista
# investigar o pipeline errado.
MSG_AGUARDE_RETIDO = "Aguarde #{} SEGURADO na malha (libere no diagrama)"


def _faltante(linha):
    """Linha do predicado → texto do faltante. Com o id do Aguarde na 2ª
    coluna, quem segura é a TRAVA — e é isso que o operador precisa ler."""
    if len(linha) > 1 and linha[1] is not None:
        return MSG_AGUARDE_RETIDO.format(linha[1])
    return linha[0]


def datas_dos_predecessores(conn, pipeline: str, agora: datetime) -> dict:
    """{predecessor: data de referência que ELE carimbaria agora}.

    A virada que vale é sempre a do PREDECESSOR (§2.2): é ele quem produz o
    dado, e é a data dele que o filho herda. Vazio quando não há predecessor.
    """
    from utils.data_referencia import calcular      # import tardio: módulo puro
    return {p: calcular(agora, virada_efetiva(conn, p))
            for p in predecessores_de(conn, pipeline)}


def datas_divergentes(datas: dict) -> bool:
    """Os predecessores calculam datas DIFERENTES entre si?

    É a Decisão 5 da guardiã, extraída para valer também no PUSH: com viradas
    divergentes, a condição do filho não fecha numa data só — e liberar assim
    junta, na mesma corrida, dados de dias diferentes (incidente da malha
    Carga_Vida, 2026-08-04). Menos de dois predecessores nunca diverge."""
    return len(set(datas.values())) > 1


def detalhe_divergencia(datas: dict) -> str:
    """Texto do evento DATA_DIVERGENTE — o MESMO formato da guardiã, para o
    operador ler a mesma frase venha ela de onde vier."""
    return "viradas divergentes: " + ", ".join(
        f"{p}->{d.strftime('%Y-%m-%d')}" for p, d in sorted(datas.items()))


def predecessores_de(conn, pipeline: str) -> list:
    """De quem `pipeline` depende (tipo PIPELINE) — o caminho inverso de
    `dependentes_de`. A guardiã usa para carimbar datas (a virada que vale é
    a do PREDECESSOR, §2.2) e para diagnóstico."""
    cur = conn.cursor()
    cur.execute(
        "SELECT dd.depende_de FROM dbo.etl_pipeline_dependencia dd "
        "WHERE dd.pipeline_name = %s AND dd.tipo = 'PIPELINE'",
        (pipeline,))
    return [r[0] for r in cur.fetchall()]


def virada_efetiva(conn, pipeline: str) -> time:
    """A virada do dia que vale para `pipeline`: hora_virada ?? config
    global ?? 00:00 — a MESMA cadeia de precedência do _data_referencia
    gerado (F2). O fallback é resolvido em Python, sem COALESCE no SQL (a
    proibição do D15 vale para o módulo inteiro). Pipeline inexistente ou
    valor inválido degradam para 00:00, o comportamento de sempre."""
    cur = conn.cursor()
    cur.execute(
        "SELECT p.hora_virada, c.config_value "
        "FROM dbo.etl_pipeline p "
        "LEFT JOIN dbo.etl_app_config c "
        "ON c.config_key = 'dependencia_hora_virada' "
        "WHERE p.pipeline_name = %s",
        (pipeline,))
    row = cur.fetchone()
    if not row:
        return time(0, 0)
    bruto = row[0] if row[0] is not None else row[1]
    v = _como_time(bruto)
    return v if v is not None else time(0, 0)


def agora_do_banco(conn) -> datetime:
    """O relógio do SQL Server (GETDATE) — para converter cortes calculados em
    hora LOCAL para a régua do banco antes de comparar com colunas carimbadas
    por GETDATE (fim/criado_em/...). O dev provou que o banco pode estar em
    UTC com a guardiã em -03: comparar régua local com carimbo do banco era a
    ÚNICA comparação mista do módulo e gerava DATA_DIVERGENTE falso diário
    (achado da revisão adversarial da F4)."""
    cur = conn.cursor()
    cur.execute("SELECT GETDATE()")
    return cur.fetchone()[0]


def corridas_aguardando(conn) -> list:
    """As linhas AGUARDANDO_DEPENDENCIA que EXISTEM — a única fonte da rede
    de segurança, do deadline e do fechamento (Decisão 6 da F4: a guardiã
    não inventa datas; uma linha só existe se foi ordenada de propósito).

    Devolve [(pipeline, data_referencia, execution_id, criado_em)]. O
    `criado_em` sai como COLUNA (é a idade da linha, insumo do fechamento
    §6) — jamais em ORDER BY ou COALESCE (D15)."""
    cur = conn.cursor()
    cur.execute(
        "SELECT pipeline_name, data_referencia, execution_id, criado_em "
        "FROM dbo.etl_pipeline_execucao "
        "WHERE status = 'AGUARDANDO_DEPENDENCIA'")
    return [(r[0], r[1], r[2], r[3]) for r in cur.fetchall()]


def resumo_predecessores(conn, pipeline: str, data_ref: date) -> dict:
    """Status por predecessor na data — {predecessor: {status, ...}};
    predecessor sem linha na data aparece com set VAZIO.

    SÓ para diagnóstico e mensagem (as três frases do D46, o
    PREDECESSOR_FALHOU do §7.2 e as guardas de fechamento do §6): NUNCA
    decide liberação — a pergunta de liberação é exclusivamente
    `liberado()` (proteção do D29).

    ⚠️ Examinada de propósito pela lente da corrida substituída e MANTIDA
    como está: aqui a pergunta é "o que ACONTECEU nesta data", e uma corrida
    aposentada aconteceu. Os dois consumidores que decidem algo com este
    resumo continuam corretos com ela dentro — `_predecessor_esperado` (D44)
    fica MAIS certo (o predecessor reaberto vai mesmo rodar hoje) e a guarda
    "predecessor EXECUTANDO não fecha o dia" só adia fechamento, que é o
    lado seguro. Quem decide liberação é `liberado()`, e só ele filtra."""
    cur = conn.cursor()
    cur.execute(
        "SELECT dd.depende_de, e.status "
        "FROM dbo.etl_pipeline_dependencia dd "
        "LEFT JOIN dbo.etl_pipeline_execucao e "
        "ON e.pipeline_name = dd.depende_de AND e.data_referencia = %s "
        "WHERE dd.pipeline_name = %s AND dd.tipo = 'PIPELINE'",
        (data_ref, pipeline))
    resumo: dict = {}
    for pred, status in cur.fetchall():
        resumo.setdefault(pred, set())
        if status is not None:
            resumo[pred].add(status)
    return resumo


def sucesso_recente_outra_data(conn, pipeline: str, data_ref: date,
                               inicio_dia: datetime) -> list:
    """F4 §7.1, face de execução do DATA_DIVERGENTE: predecessores de
    `pipeline` SEM SUCESSO em `data_ref` mas COM SUCESSO carimbado em OUTRA
    data cujo `fim` >= `inicio_dia` (a virada mais recente; o carimbo é
    `fim`, nunca criado_em — D15). Ou seja: o predecessor trabalhou DENTRO
    do dia operacional corrente e ainda assim as datas não casam. O sucesso
    normal de ontem tem fim anterior à virada corrente e NÃO aparece (D42 —
    o anti-ruído dos 200 cards/dia da 1ª guardiã).

    Devolve [(predecessor, data_referencia_divergente)]. Pergunta fora da
    lista do §9 do desenho, exigida pelo §7.1 — entra aqui pelo contrato do
    módulo (nenhuma consulta paralela).
    """
    cur = conn.cursor()
    cur.execute(
        "SELECT DISTINCT dd.depende_de, e.data_referencia "
        "FROM dbo.etl_pipeline_dependencia dd "
        "JOIN dbo.etl_pipeline_execucao e "
        "ON e.pipeline_name = dd.depende_de AND e.status = 'SUCESSO' "
        "AND e.fim >= %s AND e.data_referencia <> %s "
        "WHERE dd.pipeline_name = %s AND dd.tipo = 'PIPELINE' "
        "AND NOT EXISTS (SELECT 1 FROM dbo.etl_pipeline_execucao s "
        "WHERE s.pipeline_name = dd.depende_de "
        "AND s.data_referencia = %s AND s.status = 'SUCESSO')",
        (inicio_dia, data_ref, pipeline, data_ref))
    return [(r[0], r[1]) for r in cur.fetchall()]


def reservas_orfas(conn, idade_min: int) -> list:
    """F4 §4.2 — candidatas a resgate: EXECUTANDO com inicio IS NULL (claim
    que nunca virou corrida: worker morto entre o commit e o trigger),
    paradas há mais de `idade_min` minutos. São as duas primeiras guardas da
    tripla; a terceira (DagRun inexistente no Airflow) é do chamador, que é
    quem fala com o Airflow. A guarda de idade elimina o falso resgate na
    janela de milissegundos entre claim e trigger.

    Devolve [(pipeline, data_referencia, execution_id)]."""
    cur = conn.cursor()
    cur.execute(
        "SELECT pipeline_name, data_referencia, execution_id "
        "FROM dbo.etl_pipeline_execucao "
        "WHERE status = 'EXECUTANDO' AND inicio IS NULL "
        "AND atualizado_em < DATEADD(minute, -%s, GETDATE())",
        (int(idade_min),))
    return [(r[0], r[1], r[2]) for r in cur.fetchall()]


def resgatar_reserva(conn, pipeline: str, data_ref: date, run_id: str) -> bool:
    """Devolve a reserva órfã a AGUARDANDO_DEPENDENCIA — com a MESMA guarda
    da devolução (status EXECUTANDO + inicio IS NULL): corrida adotada pelo
    filho jamais é revertida (eco da Decisão 5 da F3). True = resgatou."""
    cur = conn.cursor()
    cur.execute(
        "UPDATE dbo.etl_pipeline_execucao "
        "SET status='AGUARDANDO_DEPENDENCIA', atualizado_em=GETDATE() "
        "WHERE pipeline_name=%s AND data_referencia=%s AND execution_id=%s "
        "AND status='EXECUTANDO' AND inicio IS NULL",
        (pipeline, data_ref, run_id))
    return cur.rowcount == 1


def corridas_em_execucao(conn, idade_min: int) -> list:
    """F5 §rede de segurança — corridas que COMEÇARAM e nunca fecharam:
    EXECUTANDO com `inicio` NÃO nulo, sem carimbo há mais de `idade_min`
    minutos.

    É o complemento exato de `reservas_orfas` (aquela cobre `inicio IS NULL`
    — o claim que nunca virou corrida). O buraco que sobrava:

      • uma etapa parada no portão da F5 fica `up_for_reschedule` até o teto
        (default 240 min); se o pipeline tem SLA, a DAG é gerada com
        `dagrun_timeout=timedelta(minutes=sla)` (`etl_dag_factory`);
      • estourando o `dagrun_timeout`, o scheduler marca o DagRun FAILED e
        **toda TI não-finalizada como SKIPPED** — então `registrar_falha`
        (ONE_FAILED) e `flow_close` (ALL_DONE) são PULADOS;
      • ninguém grava FALHA: `etl_pipeline_execucao` fica EXECUTANDO para
        sempre e **bloqueia todos os dependentes** (é a classe "órfão em
        RUNNING" que este projeto já pagou uma vez).

    O mesmo desfecho vale para qualquer morte dura do worker no meio da
    corrida — o `dagrun_timeout` só tornou a rota alcançável por desenho.

    A guarda de estado do DagRun (terminal no Airflow) é do CHAMADOR, que é
    quem fala com o Airflow — mesma divisão de `reservas_orfas`.

    Devolve [(pipeline, data_referencia, execution_id, inicio)]."""
    cur = conn.cursor()
    cur.execute(
        "SELECT pipeline_name, data_referencia, execution_id, inicio "
        "FROM dbo.etl_pipeline_execucao "
        "WHERE status = 'EXECUTANDO' AND inicio IS NOT NULL "
        "AND atualizado_em < DATEADD(minute, -%s, GETDATE())",
        (int(idade_min),))
    return [(r[0], r[1], r[2], r[3]) for r in cur.fetchall()]


def fechar_orfa_em_execucao(conn, pipeline: str, data_ref: date, run_id: str,
                            motivo: str) -> bool:
    """Fecha como FALHA a corrida que começou, cujo DagRun já MORREU e que
    ninguém fechou. True = fechei eu.

    ⚠️ **Só FALHA, nunca SUCESSO.** A guardiã fecha o que o Airflow já disse
    que terminou mal; corrida cujo DagRun terminou em `success` sem fecho na
    067 é outro defeito (o `flow_close` não gravou) e **não se conserta
    inventando verde** — ela vira alerta e vai para a Finalização Manual, que
    existe exatamente para isso. A lição do sucesso falso vale aqui também.

    `AND status='EXECUTANDO' AND inicio IS NOT NULL` é a trava contra a
    corrida com quem estiver fechando de verdade no mesmo instante: quem
    chegar primeiro vence e o outro vê rowcount 0."""
    cur = conn.cursor()
    cur.execute(
        "UPDATE dbo.etl_pipeline_execucao "
        "SET status='FALHA', motivo=%s, fim=GETDATE(), atualizado_em=GETDATE() "
        "WHERE pipeline_name=%s AND data_referencia=%s AND execution_id=%s "
        "AND status='EXECUTANDO' AND inicio IS NOT NULL",
        (str(motivo)[:500] if motivo is not None else None,
         pipeline, data_ref, run_id))
    return cur.rowcount == 1


def fechar_nao_liberou(conn, pipeline: str, data_ref: date, run_id: str,
                       motivo: str) -> bool:
    """F4 §6 — fecha a corrida como NAO_LIBEROU (o fim do ciclo de vida; a
    F9 já renderiza o status). Guarda status='AGUARDANDO_DEPENDENCIA': só
    linha ainda aguardando fecha; as guardas de idade, de não-liberada e de
    predecessor-não-EXECUTANDO são do chamador (guardiã, §6).

    NAO_LIBEROU é TERMINAL para a guardiã: nenhuma função deste módulo o
    reabre — reprocesso do dia fechado é gesto explícito do operador
    (trigger manual com conf), como o New Day do Control-M."""
    cur = conn.cursor()
    cur.execute(
        "UPDATE dbo.etl_pipeline_execucao "
        "SET status='NAO_LIBEROU', motivo=%s, atualizado_em=GETDATE() "
        "WHERE pipeline_name=%s AND data_referencia=%s AND execution_id=%s "
        "AND status='AGUARDANDO_DEPENDENCIA'",
        (str(motivo)[:500] if motivo is not None else None,
         pipeline, data_ref, run_id))
    return cur.rowcount == 1


def gravar_evento(conn, pipeline: str, data_ref: date, tipo: str,
                  detalhe: str, notificar: bool = True) -> bool:
    """INSERT ... WHERE NOT EXISTS na chave do ux_dep_evento (pipeline,
    data, tipo): idempotente — os 200 ciclos seguintes do dia não duplicam
    nem reenviam (D49). True = evento novo.

    O tipo NAO_LIBEROU estende o domínio comentado na migration 067 (o
    campo é VARCHAR(30) sem CHECK — extensão registrada no desenho F4 §6);
    MALHA_NOTIFICACAO/MALHA_CONCLUIDA são a F14 (desenho de componentes
    §5/§6), gravados com o marcador '#no:{id}' em pipeline_name.

    `notificar=False` (F14, Decisão 14 — card do Fim é OPT-IN) grava o
    evento JÁ carimbado com notificado_em: ele nunca entra na fila do Teams
    (`eventos_nao_notificados` filtra por notificado_em IS NULL), mas existe
    e vive no painel — "o evento e o painel são sempre; o card é opt-in".
    Carimbar no NASCIMENTO é o que mantém a infra da F4 intacta: a
    alternativa (filtrar na fila) deixaria o evento entupindo o lote por
    dois dias. O contrato "notificado_em só após 2xx" segue valendo para
    todo evento que DEVE ser notificado — aqui o carimbo significa "nada
    pendente de notificação", decidido por configuração, não por envio."""
    cur = conn.cursor()
    if notificar:
        cur.execute(
            "INSERT INTO dbo.etl_dependencia_evento "
            "(pipeline_name, data_referencia, tipo, detalhe) "
            "SELECT %s, %s, %s, %s "
            "WHERE NOT EXISTS (SELECT 1 FROM dbo.etl_dependencia_evento "
            "WHERE pipeline_name=%s AND data_referencia=%s AND tipo=%s)",
            (pipeline, data_ref, tipo,
             str(detalhe)[:1000] if detalhe is not None else None,
             pipeline, data_ref, tipo))
    else:
        cur.execute(
            "INSERT INTO dbo.etl_dependencia_evento "
            "(pipeline_name, data_referencia, tipo, detalhe, notificado_em) "
            "SELECT %s, %s, %s, %s, GETDATE() "
            "WHERE NOT EXISTS (SELECT 1 FROM dbo.etl_dependencia_evento "
            "WHERE pipeline_name=%s AND data_referencia=%s AND tipo=%s)",
            (pipeline, data_ref, tipo,
             str(detalhe)[:1000] if detalhe is not None else None,
             pipeline, data_ref, tipo))
    return cur.rowcount == 1


def eventos_nao_notificados(conn, limite: int, janela_dias: int) -> list:
    """Fila de notificação da guardiã (F4 §8): eventos sem notificado_em,
    do passado recente (consertar um webhook não pode despejar semanas de
    alertas velhos no canal), mais antigos primeiro, no máximo `limite` por
    ciclo. O ORDER BY é sobre `detectado_em` do EVENTO — a proibição do D15
    (ordenar a execução por criado_em) não se aplica aqui.

    Guarda de EXISTÊNCIA (achado 2 da revisão da F14 — a 076 derrubou a FK
    de pipeline do evento, então a fila é quem confere): evento comum só sai
    ao canal se o pipeline ainda existir em etl_pipeline; evento de marcador
    '#no:{id}' só se o nó ainda existir em etl_malha_no — e essa segunda
    checagem SÓ quando a 075 existe (sem ela não há como conferir, e a fila
    dos eventos comuns não pode quebrar por isso). O evento órfão em si FICA
    na tabela (histórico, filosofia F4 §7.2): ele só não vira card para uma
    coisa que já não existe. O LIKE usa '%%' — pymssql interpola '%s' e o
    literal precisa ser escapado (gotcha do placeholder por árvore)."""
    if tabela_075_presente(conn):
        guarda_no = ("EXISTS (SELECT 1 FROM dbo.etl_malha_no n "
                     "WHERE e.pipeline_name = '#no:' + CAST(n.id AS VARCHAR(20)))")
    else:
        guarda_no = "1 = 1"
    cur = conn.cursor()
    cur.execute(
        "SELECT TOP (%s) e.id, e.pipeline_name, "
        "CONVERT(VARCHAR(10), e.data_referencia, 23), e.tipo, e.detalhe, "
        "CONVERT(VARCHAR(19), e.detectado_em, 120) "
        "FROM dbo.etl_dependencia_evento e "
        "WHERE e.notificado_em IS NULL "
        "AND e.detectado_em >= DATEADD(day, -%s, GETDATE()) "
        "AND ((e.pipeline_name NOT LIKE '#no:%%' AND EXISTS "
        "(SELECT 1 FROM dbo.etl_pipeline p "
        "WHERE p.pipeline_name = e.pipeline_name)) "
        "OR (e.pipeline_name LIKE '#no:%%' AND " + guarda_no + ")) "
        "ORDER BY e.detectado_em",
        (int(limite), int(janela_dias)))
    return [{"id": r[0], "pipeline": r[1], "data_ref": r[2], "tipo": r[3],
             "detalhe": r[4], "detectado_em": r[5]} for r in cur.fetchall()]


def marcar_notificado(conn, evento_id) -> None:
    """Carimba notificado_em — o chamador SÓ chama depois de o webhook
    responder 2xx (contrato do ds_teams: 'avisei', nunca 'tentei avisar')."""
    cur = conn.cursor()
    cur.execute(
        "UPDATE dbo.etl_dependencia_evento SET notificado_em=GETDATE() "
        "WHERE id=%s", (evento_id,))


def canal_teams_supervisao(conn):
    """F4 §8 — o canal do Teams que a supervisão DataStage DE FATO usa
    (decisão fechada da spec: reusa o canal, sem grupo novo): grupo ativo
    com webhook preenchido e com jobs de supervisão ativos, o mais usado
    primeiro (empate resolvido pelo menor id — determinístico).

    Devolve {'id', 'webhook_url', 'nome'} ou None — sem grupo elegível os
    eventos ficam gravados (notificado_em NULL) e vivem no painel; a URL é
    credencial e JAMAIS vai a log. Pergunta fora da lista do §9 do desenho
    pelo mesmo motivo da sonda 067: é SQL, e SQL não entra na DAG."""
    cur = conn.cursor()
    cur.execute(
        "SELECT TOP 1 g.id, g.webhook_url, g.nome "
        "FROM dbo.etl_msg_grupo g "
        "WHERE g.ativo = 1 AND g.webhook_url IS NOT NULL "
        "AND LTRIM(RTRIM(g.webhook_url)) <> '' "
        "AND EXISTS (SELECT 1 FROM dbo.etl_ds_supervisao_job s "
        "WHERE s.grupo_id = g.id AND s.ativo = 1) "
        "ORDER BY (SELECT COUNT(*) FROM dbo.etl_ds_supervisao_job s2 "
        "WHERE s2.grupo_id = g.id AND s2.ativo = 1) DESC, g.id")
    row = cur.fetchone()
    if not row:
        return None
    return {"id": row[0], "webhook_url": row[1], "nome": row[2]}


# ═══════════════ banco — F14 (observadores de malha) ════════════════════════
# As perguntas da responsabilidade nova da guardiã (docs/
# malha-componentes-desenho.md §5/§6): Notificação e Fim são OBSERVADORES —
# nada aqui dispara, reserva ou fecha corrida; a única escrita é o evento
# (gravar_evento, acima). Mesmo contrato do módulo: conn pymssql (%s),
# chamador dono da transação, nenhuma consulta paralela.


def tabela_075_presente(conn) -> bool:
    """As tabelas de desenho da migration 075 (e a etl_malha da 070) existem?
    Mesma razão da sonda da 067 (D52): sem elas os observadores são pulados
    com log, sem exceção — e a sonda é SQL, então mora AQUI, não na DAG."""
    cur = conn.cursor()
    cur.execute(
        "SELECT OBJECT_ID('dbo.etl_malha','U'), "
        "OBJECT_ID('dbo.etl_malha_no','U'), "
        "OBJECT_ID('dbo.etl_malha_aresta','U')")
    row = cur.fetchone()
    return bool(row) and all(v is not None for v in row)


def nos_observadores(conn) -> list:
    """Universo dos observadores (F14 §5 passo 1): nós notificacao/fim de
    malhas ATIVAS (`etl_malha.ativo=1`), cada um acompanhado do DESENHO
    inteiro da sua malha (nós + arestas de nó) — é o insumo do canônico
    `utils.malha_nos.expandir`, que a guardiã importa direto (paridade por
    identidade de objeto, como a F4 fez com `liberado`).

    Malha inativa NÃO aparece (filtro no SQL — Decisão do §12: inativar
    desliga só os observadores; as dependências compiladas continuam).
    config_json ilegível degrada para None com log — evento sem título é
    melhor que observador mudo. `criado_em` (o carimbo da 075) sai junto:
    é o corte anti-retroativo do observador — não existe notificação
    "pedida" antes de o nó existir (achado 1 da revisão adversarial).

    Devolve [{"malha", "no_id", "tipo", "config", "criado_em",
              "nos": [{"id","tipo"}], "arestas": [{origem_no, origem_pipeline,
              destino_no, destino_pipeline}]}], determinístico por (malha, id).
    """
    cur = conn.cursor()
    cur.execute(
        "SELECT n.malha_name, n.id, n.tipo, n.config_json, n.criado_em "
        "FROM dbo.etl_malha_no n "
        "JOIN dbo.etl_malha m ON m.malha_name = n.malha_name "
        "WHERE m.ativo = 1")
    nos_por_malha: dict = {}
    for malha, no_id, tipo, config_json, criado_em in cur.fetchall():
        nos_por_malha.setdefault(str(malha), []).append(
            {"id": int(no_id), "tipo": (str(tipo or "")).strip().lower(),
             "config_json": config_json, "criado_em": criado_em})
    cur.execute(
        "SELECT a.malha_name, a.origem_no, a.origem_pipeline, "
        "a.destino_no, a.destino_pipeline "
        "FROM dbo.etl_malha_aresta a "
        "JOIN dbo.etl_malha m ON m.malha_name = a.malha_name "
        "WHERE m.ativo = 1")
    arestas_por_malha: dict = {}
    for malha, ono, opipe, dno, dpipe in cur.fetchall():
        arestas_por_malha.setdefault(str(malha), []).append(
            {"origem_no": int(ono) if ono is not None else None,
             "origem_pipeline": opipe,
             "destino_no": int(dno) if dno is not None else None,
             "destino_pipeline": dpipe})

    observadores = []
    for malha in sorted(nos_por_malha):
        nos = sorted(nos_por_malha[malha], key=lambda n: n["id"])
        arestas = arestas_por_malha.get(malha, [])
        for no in nos:
            if no["tipo"] not in ("notificacao", "fim"):
                continue
            observadores.append({
                "malha": malha,
                "no_id": no["id"],
                "tipo": no["tipo"],
                "config": _config_do_no(no["config_json"], malha, no["id"]),
                "criado_em": no["criado_em"],
                "nos": [{"id": n["id"], "tipo": n["tipo"]} for n in nos],
                "arestas": arestas,
            })
    return observadores


def _config_do_no(raw, malha: str, no_id: int):
    """config_json do nó → dict ou None, tolerante (o espelho do _no_config
    da API): valor quebrado por SQL direto degrada com log, nunca derruba o
    ciclo da guardiã."""
    if raw is None or str(raw).strip() == "":
        return None
    try:
        v = json.loads(raw)
        if isinstance(v, dict):
            return v
    except (ValueError, TypeError):
        pass
    print(f"[DEP] config_json ilegivel no no {no_id} da malha {malha} — ignorado")
    return None


def pipelines_todos_sucesso(conn, pipelines, data_ref: date) -> bool:
    """A condição dos observadores (F14 §5 passo 3): TODOS os `pipelines`
    (lista explícita — o upstream expandido do nó) têm SUCESSO em `data_ref`?

    O MESMO contrato EXISTS de `liberado()` (F2 §9), sobre nomes explícitos:
    FALHA, EXECUTANDO, PULADO, ausência e SUCESSO em OUTRA data não contam;
    nenhuma ordenação por criado_em (D15). Lista vazia → False SEMPRE — o
    "vacuamente verdadeiro" é a guarda de runtime da Decisão 13 (a de
    desenho é o aviso forte da §2.2).

    Dedup por casefold com uma grafia representante (a colação do banco é
    CI; o COUNT DISTINCT do SQL conta como o banco compara — o len do
    Python precisa contar igual). Exceção → False com log [DEP] (o espelho
    do D21: erro nunca vira "condição fechou"); o próximo ciclo re-pergunta.

    Corrida SUBSTITUÍDA não conta (mesma lente de `liberado()`): a entrada
    foi aposentada por um rerun com cascata e vai rodar de novo — anunciar
    "malha concluída" com ela seria avisar o fim de um dia que voltou a
    correr. Mesmo fallback para banco sem a 078.
    """
    vistos: dict = {}
    for p in pipelines:
        nome = str(p or "").strip()
        if nome:
            vistos.setdefault(nome.casefold(), nome)
    nomes = sorted(vistos.values())
    if not nomes:
        return False
    try:
        cur = conn.cursor()
        marcadores = ", ".join(["%s"] * len(nomes))
        _exec_com_fallback_078(
            cur,
            "SELECT COUNT(DISTINCT e.pipeline_name) "
            "FROM dbo.etl_pipeline_execucao e "
            "WHERE e.data_referencia = %s AND e.status = 'SUCESSO' "
            "AND e.substituida_em IS NULL "
            "AND e.pipeline_name IN (" + marcadores + ")",
            "SELECT COUNT(DISTINCT e.pipeline_name) "
            "FROM dbo.etl_pipeline_execucao e "
            "WHERE e.data_referencia = %s AND e.status = 'SUCESSO' "
            "AND e.pipeline_name IN (" + marcadores + ")",
            tuple([data_ref] + nomes))
        return int(cur.fetchone()[0]) == len(nomes)
    except Exception as e:  # noqa: BLE001 — espelho do D21
        print(f"[DEP] condicao dos observadores em {data_ref} indisponivel "
              f"({e}) — tratada como NAO satisfeita")
        return False
