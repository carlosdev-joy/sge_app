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


def liberado(conn, pipeline: str, data_ref: date):
    """Todos os predecessores de `pipeline` têm SUCESSO em `data_ref`?

    Devolve (liberado, faltantes). Contrato EXISTS do §9 da F2 (serve-se de
    ix_pipe_exec_cond): FALHA, EXECUTANDO, PULADO, ausência e SUCESSO em
    OUTRA data não liberam (D20); PULADO intercalado não mascara um SUCESSO
    existente (D14); nenhuma ordenação por criado_em (D15).

    Qualquer exceção na consulta → NÃO liberado, com log [DEP] (D21: erro
    nunca vira "pode disparar"). Predicado canônico para F4 e F5/D29.
    """
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT dd.depende_de FROM dbo.etl_pipeline_dependencia dd "
            "WHERE dd.pipeline_name = %s AND dd.tipo = 'PIPELINE' "
            "AND NOT EXISTS (SELECT 1 FROM dbo.etl_pipeline_execucao e "
            "WHERE e.pipeline_name = dd.depende_de "
            "AND e.data_referencia = %s AND e.status = 'SUCESSO')",
            (pipeline, data_ref))
        faltantes = [r[0] for r in cur.fetchall()]
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
    """
    cur = conn.cursor()
    cur.execute(
        "UPDATE e SET e.status='EXECUTANDO', e.disparado_por=%s, "
        "e.atualizado_em=GETDATE() "
        "OUTPUT inserted.execution_id "
        "FROM dbo.etl_pipeline_execucao e WITH (UPDLOCK, HOLDLOCK) "
        "WHERE e.pipeline_name=%s AND e.data_referencia=%s "
        "AND e.status='AGUARDANDO_DEPENDENCIA'",
        (origem, filho, data_ref))
    row = cur.fetchone()
    if row and row[0]:
        return row[0]
    cur.execute(
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
    """
    cur = conn.cursor()
    cur.execute(
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
    `liberado()` (proteção do D29)."""
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
                  detalhe: str) -> bool:
    """INSERT ... WHERE NOT EXISTS na chave do ux_dep_evento (pipeline,
    data, tipo): idempotente — os 200 ciclos seguintes do dia não duplicam
    nem reenviam (D49). True = evento novo.

    O tipo NAO_LIBEROU estende o domínio comentado na migration 067 (o
    campo é VARCHAR(30) sem CHECK — extensão registrada no desenho F4 §6)."""
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO dbo.etl_dependencia_evento "
        "(pipeline_name, data_referencia, tipo, detalhe) "
        "SELECT %s, %s, %s, %s "
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
    (ordenar a execução por criado_em) não se aplica aqui."""
    cur = conn.cursor()
    cur.execute(
        "SELECT TOP (%s) e.id, e.pipeline_name, "
        "CONVERT(VARCHAR(10), e.data_referencia, 23), e.tipo, e.detalhe, "
        "CONVERT(VARCHAR(19), e.detectado_em, 120) "
        "FROM dbo.etl_dependencia_evento e "
        "WHERE e.notificado_em IS NULL "
        "AND e.detectado_em >= DATEADD(day, -%s, GETDATE()) "
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
