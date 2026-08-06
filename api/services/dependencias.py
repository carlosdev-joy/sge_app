"""
api/services/dependencias.py — o predicado de liberação por dependência, visto
da API (F5 da retomada, D29).

PORT de dags/utils/dependencias.py — **o canônico é o de dags/**: quem mudar a
regra muda lá primeiro e espelha aqui. A cópia existe pelo mesmo motivo de
api/services/data_referencia.py (F9): api/ e dags/ são árvores de deploy
separadas, e um import cruzado quebraria no primeiro deploy parcial. A paridade
é garantida por teste em DOIS níveis (tests/test_dependencias_f5_paridade.py):
o SQL capturado tem de ser IDÊNTICO ao do canônico (normalizado %s→?) e a
matriz semântica D14/D20/D21 tem de dar o MESMO resultado nas duas árvores.

Placeholder `?` (pyodbc — árvore api/); em dags/ é `%s` (pymssql). Trocar dá
"Incorrect syntax near '?'" com task verde — o GOTCHA registrado do projeto.

CONTRATO DE LEITURA (F2 §9): a liberação é
    EXISTS(pipeline=P AND data_referencia=D AND status='SUCESSO')
— nunca "linha mais recente", nunca COALESCE(inicio, criado_em), nenhuma
ordenação por criado_em em lugar nenhum deste módulo (D14, D15). Foi
exatamente o `TOP 1 ... ORDER BY COALESCE(inicio, criado_em)` do endpoint da
1ª F5 que fez o painel divergir do motor (B2/D14/D15/N9).

Este módulo NUNCA decide disparo: `liberado()` aqui é LEITURA para painel e
tooltip — quem dispara continua sendo o push/guardiã em dags/. Todas as
funções recebem `cur` (cursor aberto) e o CHAMADOR é dono da transação.
"""
from __future__ import annotations

import logging
import re
from datetime import date

log = logging.getLogger("orquestra-api")

# Sentinel de "não consegui perguntar" (≠ "condição não fechou") — o MESMO do
# canônico: erro de consulta nunca vira "pode disparar" (D21).
ERRO_CONSULTA = "erro na consulta:"


# Marca da migration 078 e fallback — o MESMO recurso do canônico de dags/
# (`_MARCA_078`/`_exec_com_fallback_078`), portado para cá pela regra de
# paridade: o predicado emite UMA consulta só, e ela tem de ser textualmente
# igual à do motor (o teste de paridade conta as chamadas). Um probe de coluna
# aqui gastaria uma consulta a mais e quebraria essa contagem.
_MARCA_078 = "substituida_em"


def _exec_com_fallback_078(cur, sql_078: str, sql_legado: str, params) -> bool:
    """Executa `sql_078`; se o banco ainda não tem a coluna da 078, repete com
    `sql_legado`. True = caiu no legado. Qualquer outro erro PROPAGA (a
    tradução D21 é de `liberado()`)."""
    try:
        cur.execute(sql_078, params)
        return False
    except Exception as e:  # noqa: BLE001 — reagimos SÓ ao Invalid column name da 078
        # ⚠️ LACUNA CONHECIDA: ao contrário de `_marca_de`, esta marca não
        # distingue "a coluna não existe" de "o banco negou a coluna"
        # (erro 230). Com um DENY em `substituida_em`, o legado assume e o
        # descarte da corrida substituída some em silêncio. Mora aqui
        # porque `test_claim_tem_fallback_para_banco_sem_a_078` pina este
        # texto-fonte; fechar exige mexer no teste, e é da 078, não da F6.
        if _MARCA_078 not in str(e):
            raise
        cur.execute(sql_legado, params)
        return True


# ── SQL do predicado: port EXATO do canônico (só ? no lugar de %s) ──────────
# A 2ª coluna traz o id do Aguarde SEGURADO (082) que compilou a linha: a trava
# vale nas TRÊS portas porque todas passam por este predicado. A cascata
# 082 → 078 → legado existe para um banco sem a coluna nova NÃO virar
# "não liberado para todo mundo" — a trava pararia a produção inteira.
_MARCA_082 = "retido_em"
# A marca da 085 — port do canônico, e a mais importante desta cascata: sem a
# migration, um SQL que cite `dbo.etl_malha_execucao` levanta "Invalid object
# name" e `liberado()` viraria NÃO-liberado para o banco inteiro (célula 2 da
# matriz §11.1). Duas marcas por degrau porque o banco reclama da COLUNA quando
# só ela falta e da TABELA quando a migration inteira não passou.
_MARCA_085 = "malha_execucao_id"
_MARCAS_085 = (_MARCA_085, "etl_malha_execucao")
# `origem_no` entra nas marcas da 082 pelo mesmo motivo que `etl_malha_no`: as
# duas nasceram na 075 e os SQLs do modo SEQUENCIA citam AS DUAS. Sem esta
# marca, um banco sem a coluna devolvia `Invalid column name 'origem_no'`, que
# nao casava com degrau nenhum, propagava, e `liberado()` respondia
# NAO-LIBERADO para o banco INTEIRO — a mesma catastrofe da §11.1 por outra
# coluna. Era anterior a esta fase (a `main` tambem cita `dd.origem_no`), mas
# endurecer a cascata sem fechar o buraco vizinho seria consertar so o que a
# revisao apontou.
_MARCAS_082 = (_MARCA_082, "etl_malha_no", "origem_no")


# ⚠️ O SQL Server NOMEIA o objeto também quando RECUSA a consulta (229 na
# tabela, 230 na coluna), e as marcas casam por SUBSTRING — sem esta guarda uma
# permissão faltando seria lida como "a migration não passou" e a cascata
# desceria um degrau em silêncio. Port do canônico, onde está o porquê inteiro.
_NUM_RECUSA = re.compile(r"\((?:229|230|297|300)[,)]")


def _recusa_de_permissao(erro) -> bool:
    """O banco RECUSOU a consulta, em vez de não ter o objeto? (port)"""
    msg = str(erro)
    return bool(_NUM_RECUSA.search(msg)) or "permission was denied" in msg


def _marca_de(erro, marcas) -> bool:
    """O erro é UMA das marcas conhecidas de deploy parcial? (port) Só elas
    degradam: deadlock, timeout e permissão continuam PROPAGANDO."""
    if _recusa_de_permissao(erro):
        return False
    msg = str(erro)
    return any(m in msg for m in marcas)


def _degrau_apos(erro):
    """Depois deste erro, qual degrau tentar — ou None para PROPAGAR (port).

    085 → `"seq_084"` (o modo sobrevive, o corte vira a janela); 082/078 →
    `"data"` (nenhum SQL do modo roda neste banco)."""
    if _marca_de(erro, _MARCAS_085):
        return "seq_084"
    if _marca_de(erro, _MARCAS_082) or _marca_de(erro, (_MARCA_078,)):
        return "data"
    return None


_SELECT_RETENCAO = (
    ", (SELECT TOP 1 n.id FROM dbo.etl_malha_no n "
    "   WHERE n.id = dd.origem_no AND n.retido_em IS NOT NULL) AS aguarde_retido ")
_ONDE_SEM_SUCESSO_078 = (
    "AND NOT EXISTS (SELECT 1 FROM dbo.etl_pipeline_execucao e "
    "WHERE e.pipeline_name = dd.depende_de "
    "AND e.data_referencia = ? AND e.status = 'SUCESSO' "
    "AND e.substituida_em IS NULL)")
_ONDE_SEM_SUCESSO_LEGADO = (
    "AND NOT EXISTS (SELECT 1 FROM dbo.etl_pipeline_execucao e "
    "WHERE e.pipeline_name = dd.depende_de "
    "AND e.data_referencia = ? AND e.status = 'SUCESSO')")
SQL_LIBERADO_082 = (
    "SELECT dd.depende_de" + _SELECT_RETENCAO +
    "FROM dbo.etl_pipeline_dependencia dd "
    "WHERE dd.pipeline_name = ? AND dd.tipo = 'PIPELINE' "
    "AND (" + _ONDE_SEM_SUCESSO_078[4:] +
    " OR EXISTS (SELECT 1 FROM dbo.etl_malha_no n2 "
    "            WHERE n2.id = dd.origem_no AND n2.retido_em IS NOT NULL))")
_ONDE_SEM_SUCESSO_SEQ_084 = (
    "AND NOT EXISTS (SELECT 1 FROM dbo.etl_pipeline_execucao e "
    "WHERE e.pipeline_name = dd.depende_de "
    "AND e.status = 'SUCESSO' AND e.substituida_em IS NULL "
    "AND ISNULL(e.fim, e.inicio) >= ?)")
SQL_LIBERADO_SEQ_084 = (
    "SELECT dd.depende_de" + _SELECT_RETENCAO +
    "FROM dbo.etl_pipeline_dependencia dd "
    "WHERE dd.pipeline_name = ? AND dd.tipo = 'PIPELINE' "
    "AND (" + _ONDE_SEM_SUCESSO_SEQ_084[4:] +
    " OR EXISTS (SELECT 1 FROM dbo.etl_malha_no n2 "
    "            WHERE n2.id = dd.origem_no AND n2.retido_em IS NOT NULL))")

# O corte em TRÊS degraus (Decisão 38, §8) — port do canônico, onde está o
# porquê de cada degrau. Em uma frase: (1) a corrida da PRÓPRIA LINHA avaliada,
# como parâmetro e não como subconsulta viva; (2) a corrida aberta da malha que
# ASSINOU a dependência (`origem_no`, migration 075 — a malha é determinada, e
# a ambiguidade do membro compartilhado não aparece); (3) a janela em horas, o
# fallback de quem não tem corrida. `ORDER BY` explícito no `TOP 1` (D15).
#
# O painel tem de contar a MESMA história do motor: se lá o corte passou a ser
# o `aberta_em` da corrida, aqui também — senão a tela diria "liberado" para um
# filho que o motor está segurando, que é a divergência painel×motor que a
# paridade existe para impedir.
_CORTE_SEQ_085 = (
    "COALESCE("
    "(SELECT me.aberta_em FROM dbo.etl_malha_execucao me "
    "WHERE me.id = CAST(? AS BIGINT)), "
    "(SELECT TOP 1 me2.aberta_em FROM dbo.etl_malha_no n3 "
    "JOIN dbo.etl_malha_execucao me2 ON me2.malha_name = n3.malha_name "
    "AND me2.fechada_em IS NULL WHERE n3.id = dd.origem_no "
    "ORDER BY me2.aberta_em DESC, me2.id DESC), "
    "?)")
# ⚠️ O corte sai UMA VEZ POR LINHA, num `CROSS APPLY` — porque dentro do
# `NOT EXISTS` ele vira expressão correlacionada, o SQL Server abandona o seek
# em `ix_pipe_exec_cond` e varre `etl_pipeline_execucao` inteira. Medido no dev
# (40 membros, 57.640 execuções): 227–346 ms → 24–30 ms, resposta idêntica. O
# porquê completo está no canônico de `dags/`; aqui vale em dobro, porque esta
# árvore responde a uma TELA que se atualiza sozinha.
_ONDE_SEM_SUCESSO_SEQ_085 = (
    "AND NOT EXISTS (SELECT 1 FROM dbo.etl_pipeline_execucao e "
    "WHERE e.pipeline_name = dd.depende_de "
    "AND e.status = 'SUCESSO' AND e.substituida_em IS NULL "
    "AND ISNULL(e.fim, e.inicio) >= k.corte)")
# Parâmetros, na ordem em que o texto os pede: (pipeline, corrida, janela).
SQL_LIBERADO_SEQ_085 = (
    "SELECT dd.depende_de" + _SELECT_RETENCAO +
    "FROM (SELECT depende_de, origem_no FROM dbo.etl_pipeline_dependencia "
    "WHERE pipeline_name = ? AND tipo = 'PIPELINE') dd "
    "CROSS APPLY (SELECT corte = " + _CORTE_SEQ_085 + ") k "
    "WHERE (" + _ONDE_SEM_SUCESSO_SEQ_085[4:] +
    " OR EXISTS (SELECT 1 FROM dbo.etl_malha_no n2 "
    "            WHERE n2.id = dd.origem_no AND n2.retido_em IS NOT NULL))")

SQL_LIBERADO_078 = (
    "SELECT dd.depende_de FROM dbo.etl_pipeline_dependencia dd "
    "WHERE dd.pipeline_name = ? AND dd.tipo = 'PIPELINE' " +
    _ONDE_SEM_SUCESSO_078)
SQL_LIBERADO_LEGADO = (
    "SELECT dd.depende_de FROM dbo.etl_pipeline_dependencia dd "
    "WHERE dd.pipeline_name = ? AND dd.tipo = 'PIPELINE' " +
    _ONDE_SEM_SUCESSO_LEGADO)

# ── O MESMO predicado, na forma de CONJUNTO (F10, §9.6/Decisão 73) ──────────
#
# O DEFEITO que este bloco mata: o painel perguntava `liberado()` **por membro
# esperando** (`routers/malhas.py`, no laço de `execucoes[]`). Numa malha de 40
# membros com 12 esperando são 12 idas ao banco só para o predicado — e o modo
# SEQUÊNCIA multiplica por 3, porque `inicio_do_ciclo_corrente()` gasta
# `SELECT GETDATE()` + a janela A CADA CHAMADA. Com o painel se atualizando
# sozinho durante um incidente, é o pior ordenamento possível: a tela mais
# consultada da madrugada é a que mais pesa exatamente quando o banco já está
# ruim.
#
# ⚠️ A regra que torna isto seguro: **os textos abaixo são montados dos MESMOS
# fragmentos** (`_ONDE_SEM_SUCESSO_*`, `_CORTE_SEQ_085`, `_SELECT_RETENCAO`)
# que os de uma linha. Uma segunda redação do predicado, ainda que "igual hoje",
# seria o painel e o motor discordando no dia em que alguém mudasse um deles —
# a doença que a paridade D29 existe para impedir. Quem mexer no predicado
# muda o canônico de `dags/`, espelha nos fragmentos daqui, e as DUAS formas
# andam juntas de graça.
#
# O que muda, e só isto: `pipeline_name = ?` vira `pipeline_name IN (…)`, e a
# projeção ganha `dd.pipeline_name` na frente para o chamador saber de QUEM é
# cada faltante. A linha devolvida é `(pipeline, depende_de[, aguarde_retido])`
# — o mesmo `_faltante()` a lê, deslocada de uma coluna.
_ALVO_LOTE = "IN ({m})"
_EXISTS_RETIDO = (
    " OR EXISTS (SELECT 1 FROM dbo.etl_malha_no n2 "
    "            WHERE n2.id = dd.origem_no AND n2.retido_em IS NOT NULL))")
# Parâmetros, na ordem em que o texto os pede: (…nomes…, corrida, janela).
SQL_LOTE_SEQ_085 = (
    "SELECT dd.pipeline_name, dd.depende_de" + _SELECT_RETENCAO +
    "FROM (SELECT pipeline_name, depende_de, origem_no "
    "FROM dbo.etl_pipeline_dependencia "
    "WHERE pipeline_name " + _ALVO_LOTE + " AND tipo = 'PIPELINE') dd "
    "CROSS APPLY (SELECT corte = " + _CORTE_SEQ_085 + ") k "
    "WHERE (" + _ONDE_SEM_SUCESSO_SEQ_085[4:] + _EXISTS_RETIDO)
# (…nomes…, corte da janela)
SQL_LOTE_SEQ_084 = (
    "SELECT dd.pipeline_name, dd.depende_de" + _SELECT_RETENCAO +
    "FROM dbo.etl_pipeline_dependencia dd "
    "WHERE dd.pipeline_name " + _ALVO_LOTE + " AND dd.tipo = 'PIPELINE' "
    "AND (" + _ONDE_SEM_SUCESSO_SEQ_084[4:] + _EXISTS_RETIDO)
# (…nomes…, data_ref)
SQL_LOTE_082 = (
    "SELECT dd.pipeline_name, dd.depende_de" + _SELECT_RETENCAO +
    "FROM dbo.etl_pipeline_dependencia dd "
    "WHERE dd.pipeline_name " + _ALVO_LOTE + " AND dd.tipo = 'PIPELINE' "
    "AND (" + _ONDE_SEM_SUCESSO_078[4:] + _EXISTS_RETIDO)
# Os dois últimos degraus são anteriores à 082 e por isso NÃO trazem a coluna
# da retenção: `origem_no` só existe a partir da 075, e citá-la aqui devolveria
# o "Invalid column name" no degrau que existe justamente para sobreviver a ele.
SQL_LOTE_078 = (
    "SELECT dd.pipeline_name, dd.depende_de "
    "FROM dbo.etl_pipeline_dependencia dd "
    "WHERE dd.pipeline_name " + _ALVO_LOTE + " AND dd.tipo = 'PIPELINE' " +
    _ONDE_SEM_SUCESSO_078)
SQL_LOTE_LEGADO = (
    "SELECT dd.pipeline_name, dd.depende_de "
    "FROM dbo.etl_pipeline_dependencia dd "
    "WHERE dd.pipeline_name " + _ALVO_LOTE + " AND dd.tipo = 'PIPELINE' " +
    _ONDE_SEM_SUCESSO_LEGADO)

# Teto de nomes por consulta. O TDS aceita 2100 parâmetros por statement, e
# passar disso não devolve "consulta grande": devolve erro, e a tela perderia
# TODOS os faltantes de uma vez. Com o teto, uma malha absurda degrada para
# duas ou três consultas de conjunto — que continua sendo O(1) em relação ao
# número de membros ESPERANDO, que é o que esta fase existe para consertar.
_TETO_NOMES_POR_CONSULTA = 900

MSG_AGUARDE_RETIDO = "Aguarde #{} SEGURADO na malha (libere no diagrama)"
# Port do canônico: o prefixo pelo qual quem CONSOME os faltantes reconhece a
# retenção sem reimplementar o texto (§6.7, Decisão 30).
MARCA_RETIDO = MSG_AGUARDE_RETIDO.split("#", 1)[0]


def eh_retencao(faltante) -> bool:
    """O faltante é uma TRAVA do operador, e não um predecessor que não
    concluiu? (Port do canônico — as duas árvores têm de concordar sobre isto,
    senão a tela chama de "esperando outro pipeline" o que o motor sabe que é
    um nó segurado.)"""
    return str(faltante).startswith(MARCA_RETIDO)


def _faltante(linha):
    """Linha do predicado → texto do faltante (port do canônico)."""
    if len(linha) > 1 and linha[1] is not None:
        return MSG_AGUARDE_RETIDO.format(linha[1])
    return linha[0]


def _descer_cascata(cur, seq085, seq084, s082, s078, legado):
    """Cascata **SEQ_085 → SEQ_084 → 082 → 078 → legado** (port do canônico).

    Cada degrau é um par `(sql, params)`; `seq085`/`seq084` vêm `None` quando o
    modo SEQUÊNCIA está desligado. Sem esta cascata, um banco sem a 085 faria
    `liberado()` devolver não-liberado para o banco inteiro — no painel isso é
    toda malha pintada de "aguardando" sem que ninguém esteja aguardando nada.

    ⚠️ A cascata mora AQUI, num lugar só, porque a partir da F10 ela tem DOIS
    consumidores: o predicado de uma linha (`_exec_liberado`) e o de conjunto
    (`_exec_faltantes_em_lote`). Duplicá-la faria o painel degradar por um
    caminho e o motor por outro — a divergência painel×motor que a paridade D29
    existe para impedir, reaparecendo pela porta do deploy parcial, que é
    justamente quando ela é mais cara de diagnosticar."""
    if seq085 is not None:
        try:
            cur.execute(*seq085)
            return True, False
        except Exception as e:  # noqa: BLE001 — só as marcas conhecidas degradam
            proximo, motivo = _degrau_apos(e), e
            if proximo is None:
                raise
        if proximo == "seq_084":
            log.info("[DEP] migration 085 ausente — o corte do modo SEQUENCIA "
                     "volta a ser a janela em horas")
            try:
                cur.execute(*seq084)
                return True, False
            except Exception as e:  # noqa: BLE001
                proximo, motivo = _degrau_apos(e), e
                if proximo != "data":
                    raise
        log.warning("[DEP] modo SEQUENCIA indisponivel neste banco (%s) — a "
                    "liberacao volta a olhar a data de referencia", motivo)
    try:
        cur.execute(*s082)
        return True, False
    except Exception as e:  # noqa: BLE001 — só as marcas conhecidas degradam
        if not _marca_de(e, _MARCAS_082) and not _marca_de(e, (_MARCA_078,)):
            raise
    return False, _exec_com_fallback_078(cur, s078[0], legado[0], s078[1])


def _exec_liberado(cur, params, params_seq=None):
    """A cascata para UMA linha. `params` = (pipeline, data_ref);
    `params_seq`, quando presente, = (pipeline, corrida, corte da janela)."""
    seq085 = seq084 = None
    if params_seq is not None:
        seq085 = (SQL_LIBERADO_SEQ_085, params_seq)
        seq084 = (SQL_LIBERADO_SEQ_084, (params_seq[0], params_seq[2]))
    return _descer_cascata(cur, seq085, seq084,
                           (SQL_LIBERADO_082, params),
                           (SQL_LIBERADO_078, params),
                           (SQL_LIBERADO_LEGADO, params))


_MODO_CACHE: dict = {}


def limpar_cache_modo() -> None:
    """Esquece o modo lido (teste / reavaliação no mesmo processo)."""
    _MODO_CACHE.clear()


def modo_sequencia(cur) -> bool:
    """A liberação está em modo SEQUÊNCIA? Port do canônico — aqui o cache
    dura o processo da API, e a API é longa: por isso o TTL curto, para o
    operador não precisar reiniciar nada depois de virar a chave no Admin."""
    import time as _t
    agora = _t.time()
    if _MODO_CACHE.get("ate", 0) > agora:
        return _MODO_CACHE["modo"]
    valor = False
    try:
        cur.execute("SELECT config_value FROM dbo.etl_app_config "
                    "WHERE config_key = 'dependencia_modo_sequencia'")
        row = cur.fetchone()
        valor = bool(row) and str(row[0] or "").strip() in ("1", "true", "True")
    except Exception as e:  # noqa: BLE001
        log.debug("[DEP] modo de liberacao indisponivel (%s)", e)
    _MODO_CACHE.update({"modo": valor, "ate": agora + 30})
    return valor


JANELA_SEQ_PADRAO_H = 12


def janela_sequencia_horas(cur) -> int:
    """Port do canônico: janela do modo sequência em horas (default 12,
    domínio 1..168).

    ⚠️ **A partir da F6 é o FALLBACK de quem não tem corrida** (3º degrau do
    corte, §8) — não o corte único. E **não** está depreciada: dependência
    criada à mão pelo `POST /dependencias` tem `origem_no IS NULL` e nunca terá
    corrida; removê-la quebraria toda dependência avulsa."""
    try:
        cur.execute("SELECT config_value FROM dbo.etl_app_config "
                    "WHERE config_key = 'dependencia_janela_sequencia_horas'")
        row = cur.fetchone()
        n = int(str(row[0]).strip()) if row and row[0] is not None else JANELA_SEQ_PADRAO_H
        return n if 1 <= n <= 168 else JANELA_SEQ_PADRAO_H
    except Exception as e:  # noqa: BLE001
        log.debug("[DEP] janela do modo sequencia indisponivel (%s)", e)
        return JANELA_SEQ_PADRAO_H


def inicio_do_ciclo_corrente(cur):
    """O corte de FALLBACK do modo sequência (port): `agora - janela`, na régua
    do BANCO.

    ⚠️ **A partir da F6 é o 3º degrau do corte**, não o corte (§8): vale para a
    linha sem corrida — a dependência avulsa e a linha de malha cujo ciclo ainda
    não abriu. O valor é calculado e passado SEMPRE (é o último argumento do
    `COALESCE`); quem decide se ele chega a ser usado é o SQL Server.

    NÃO é a virada do dia: com o corte na virada, a corrida que atravessa a
    meia-noite (pai 23h30, filho 01h) travaria em silêncio."""
    from datetime import datetime, timedelta
    try:
        cur.execute("SELECT GETDATE()")
        row = cur.fetchone()
        agora = row[0] if row and row[0] is not None else datetime.now()
    except Exception:  # noqa: BLE001
        agora = datetime.now()
    return agora - timedelta(hours=janela_sequencia_horas(cur))


def _id_corrida(valor):
    """`corrida` → int, ou None (port). Tolerante: id ilegível é "não tenho
    corrida", nunca exceção — o degrau 2 resolve."""
    if valor is None:
        return None
    try:
        return int(valor)
    except (TypeError, ValueError):
        log.warning("[DEP] id de corrida ilegivel (%r) — ignorado", valor)
        return None


def faltantes(cur, pipeline: str, data_ref: date, corrida=None) -> list:
    """Predecessores de `pipeline` SEM SUCESSO VIVO em `data_ref`.

    Port EXATO do SELECT de dags/utils/dependencias.liberado() (só o
    placeholder muda, %s→?): NOT EXISTS(... status='SUCESSO' na data) por
    predecessor — FALHA, EXECUTANDO, PULADO, ausência e SUCESSO em OUTRA data
    contam como faltando (D20); PULADO intercalado não mascara um SUCESSO
    existente (D14). Exceção PROPAGA — a tradução D21 fica em `liberado()`.

    Corrida com `substituida_em` (078) NÃO conta como SUCESSO — a correção da
    terceira porta do modelo de corrida, feita primeiro no canônico. O painel
    tem de contar a MESMA história do motor: com o dependente reaberto pela
    cascata, "aguardando o predecessor" é a verdade dos dois lados.
    """
    # Modo SEQUÊNCIA: o painel tem de contar a MESMA história do motor —
    # se lá a data saiu da conta, aqui também. E se lá o corte passou a sair da
    # CORRIDA da linha (F6), aqui também: o painel que mostrasse a janela de 12h
    # enquanto o motor usa o `aberta_em` diria "aguardando" para um filho já
    # liberado (ou o contrário) nas horas em que os dois cortes discordam — que
    # são exatamente as horas em que alguém está olhando a tela.
    params_seq = None
    if modo_sequencia(cur):
        params_seq = (pipeline, _id_corrida(corrida),
                      inicio_do_ciclo_corrente(cur))
    _exec_liberado(cur, (pipeline, data_ref), params_seq)
    return [_faltante(r) for r in cur.fetchall()]


def _params_do_lote(cur, nomes: list, data_ref: date, corrida=None):
    """Os cinco degraus da cascata já com o `IN (…)` expandido e os parâmetros
    na ordem do TEXTO. Devolve `(seq085, seq084, s082, s078, legado)`, cada um
    `(sql, params)` — `seq085`/`seq084` são `None` fora do modo SEQUÊNCIA.

    O corte da janela e o modo são lidos **uma vez por lote**, e é aí que mora
    metade do ganho: em `faltantes()` eles saem por CHAMADA, então cada membro
    esperando custava também um `SELECT GETDATE()` e a leitura da config."""
    marcadores = ",".join("?" for _ in nomes)
    nomes = tuple(nomes)
    seq085 = seq084 = None
    if modo_sequencia(cur):
        corte = inicio_do_ciclo_corrente(cur)
        seq085 = (SQL_LOTE_SEQ_085.replace("{m}", marcadores),
                  nomes + (_id_corrida(corrida), corte))
        seq084 = (SQL_LOTE_SEQ_084.replace("{m}", marcadores), nomes + (corte,))
    por_data = nomes + (data_ref,)
    return (seq085, seq084,
            (SQL_LOTE_082.replace("{m}", marcadores), por_data),
            (SQL_LOTE_078.replace("{m}", marcadores), por_data),
            (SQL_LOTE_LEGADO.replace("{m}", marcadores), por_data))


def faltantes_em_lote(cur, pipelines, data_ref: date, corrida=None) -> dict:
    """`{pipeline: [faltantes]}` para TODOS os `pipelines` numa consulta só.

    O irmão de conjunto de `faltantes()` — MESMO predicado, MESMA cascata,
    MESMOS textos de faltante (inclusive o da retenção). É o que tira o N+1 do
    caminho corrente do painel (§9.6): o custo deixa de crescer com o número
    de membros esperando, que é justamente o número que cresce durante um
    incidente.

    Todo nome pedido volta como chave, mesmo sem faltante nenhum — `[]` é a
    resposta "perguntei e não falta ninguém", e ela é diferente de "não
    perguntei". Nome sem chave nenhuma seria o chamador tendo de adivinhar qual
    dos dois aconteceu.

    Falha de consulta degrada como em `liberado()` (D21): o sentinel
    `ERRO_CONSULTA` entra nos faltantes dos nomes daquele lote — erro NUNCA
    vira "pode disparar", nem no painel. E degrada **por lote**, não por nome:
    o lote que respondeu continua valendo.
    """
    alvos, vistos = [], set()
    for p in pipelines:
        chave = str(p or "").strip().casefold()
        if not chave or chave in vistos:
            continue
        vistos.add(chave)
        alvos.append(str(p).strip())
    out: dict = {nome: [] for nome in alvos}
    if not alvos:
        return out
    # `casefold` porque o SQL Server compara nome de pipeline sem distinguir
    # caixa (collation CI) mas o dict do Python distingue: sem esta ponte, uma
    # linha gravada como `carga_a` devolveria os faltantes numa chave que o
    # chamador nunca procuraria — o GOTCHA de grafia que a F8 já pagou.
    indice = {nome.casefold(): nome for nome in alvos}
    for i in range(0, len(alvos), _TETO_NOMES_POR_CONSULTA):
        lote = alvos[i:i + _TETO_NOMES_POR_CONSULTA]
        try:
            _descer_cascata(cur, *_params_do_lote(cur, lote, data_ref, corrida))
            linhas = cur.fetchall()
        except Exception as e:  # noqa: BLE001 — D21: erro é NÃO liberado
            log.warning("[DEP] condicao em lote de %d pipelines indisponivel "
                        "(%s) — tratada como NAO liberada", len(lote), e)
            marca = f"{ERRO_CONSULTA} {e}"[:200]
            for nome in lote:
                out[nome] = [marca]
            continue
        for linha in linhas:
            nome = indice.get(str(linha[0] or "").strip().casefold())
            if nome is None:
                continue        # não pedimos por este; nunca deveria acontecer
            out[nome].append(_faltante(linha[1:]))
    return out


def liberado(cur, pipeline: str, data_ref: date, corrida=None):
    """Todos os predecessores de `pipeline` têm SUCESSO em `data_ref`?

    Devolve (liberado, faltantes) — a MESMA pergunta e a MESMA resposta do
    canônico de dags/. Qualquer exceção na consulta → NÃO liberado, com o
    sentinel ERRO_CONSULTA embutido nos faltantes (D21: erro nunca vira
    "pode disparar" — nem no painel).

    `corrida` (F6, Decisão 39) é a corrida de malha DA LINHA avaliada — no
    painel, a da LENTE. Aditiva: quem chama com três argumentos tem exatamente
    o comportamento anterior.
    """
    try:
        falta = faltantes(cur, pipeline, data_ref, corrida)
        return (not falta), falta
    except Exception as e:  # noqa: BLE001 — D21: erro é NÃO liberado, nunca silêncio
        log.warning("[DEP] condicao de %s indisponivel (%s) — tratada como NAO liberada",
                    pipeline, e)
        return False, [f"{ERRO_CONSULTA} {e}"[:200]]


def resumo_predecessores(cur, pipeline: str, data_ref: date) -> dict:
    """Status por predecessor na data — {predecessor: {status, ...}};
    predecessor sem linha na data aparece com set VAZIO.

    SÓ para exibição e mensagem — NUNCA decide liberação: a pergunta de
    liberação é exclusivamente `liberado()` (proteção do D29, a mesma
    docstring do canônico da F4).
    """
    cur.execute(
        "SELECT dd.depende_de, e.status "
        "FROM dbo.etl_pipeline_dependencia dd "
        "LEFT JOIN dbo.etl_pipeline_execucao e "
        "ON e.pipeline_name = dd.depende_de AND e.data_referencia = ? "
        "WHERE dd.pipeline_name = ? AND dd.tipo = 'PIPELINE'",
        (data_ref, pipeline))
    resumo: dict = {}
    for pred, status in cur.fetchall():
        resumo.setdefault(pred, set())
        if status is not None:
            resumo[pred].add(status)
    return resumo


def mais_recente_da_data(linhas):
    """A execução MAIS RECENTE entre `linhas` — a regra F9 (§6 risco 6 da
    spec), extraída de get_malha_execucao: vence a chave
    (inicio is not None, inicio, execution_id) — linha ainda sem inicio
    (AGUARDANDO_DEPENDENCIA) perde de qualquer linha iniciada; empate de
    inicio desempata por execution_id. NENHUMA menção a criado_em (D15).

    `linhas`: iterável de dicts com ao menos {"inicio", "execution_id"}.
    Devolve o dict vencedor, ou None se a sequência for vazia.
    """
    vencedora, chave_v = None, None
    for linha in linhas:
        chave = (linha.get("inicio") is not None, linha.get("inicio"),
                 str(linha.get("execution_id") or ""))
        if chave_v is None or chave > chave_v:
            vencedora, chave_v = linha, chave
    return vencedora


def virada_global(cur):
    """Valor CRU de etl_app_config['dependencia_hora_virada'] (a hora de virada
    GLOBAL do ODATE — mesma chave que dags/ lê), ou None se ausente/ilegível.
    O parse tolerante fica em services.data_referencia: config quebrado degrada
    para a virada padrão 00:00, nunca derruba a tela. (Extraído de malhas.py —
    reusado pelos dois routers.)"""
    try:
        cur.execute(
            "SELECT config_value FROM dbo.etl_app_config WHERE config_key = ?",
            ("dependencia_hora_virada",))
        row = cur.fetchone()
        return row[0] if row else None
    except Exception as e:
        log.warning("[DEP] leitura de dependencia_hora_virada falhou: %s", e)
        return None


def tabela_067(cur) -> bool:
    """True se etl_pipeline_dependencia (migration 067) existe. Uma consulta
    por request, para o deploy parcial degradar em vez de estourar
    'Invalid object name'. (Extraída de malhas.py — reusada pelos dois
    routers.)"""
    try:
        cur.execute("SELECT OBJECT_ID('dbo.etl_pipeline_dependencia', 'U')")
        row = cur.fetchone()
        return bool(row and row[0] is not None)
    except Exception as e:
        log.warning("[DEP] checagem da tabela da migration 067 falhou: %s", e)
        return False


# ── Assinatura de proveniência (F11 — origem_no da migration 075) ────────────
# Helpers EXCLUSIVOS da árvore api/ (não são port de dags/): a assinatura é
# proteção de ESCRITA (Decisão 4 do desenho de componentes — linha compilada
# só se mexe pela malha dona) e o motor nunca a lê — `liberado()` continua
# ignorando origem_no. Vivem aqui porque as TRÊS portas precisam da mesma
# resposta e da MESMA mensagem: DELETE /dependencias (routers/malhas.py),
# _gravar_dependencias do register (routers/pipelines.py) e o estado do modal
# F5 (GET /pipelines/dependencias/estado) — e pipelines.py não pode importar
# malhas.py (ciclo).

def coluna_origem_no(cur) -> bool:
    """True se etl_pipeline_dependencia.origem_no (migration 075) existe.
    Best-effort no padrão dos guards de coluna (073/074): qualquer falha conta
    como ausente e as portas se comportam como antes da F11."""
    try:
        cur.execute("SELECT COL_LENGTH('dbo.etl_pipeline_dependencia', 'origem_no')")
        row = cur.fetchone()
        return bool(row and row[0] is not None)
    except Exception as e:
        log.warning("[DEP] checagem da coluna origem_no da migration 075 falhou: %s", e)
        return False


def tabela_malha_pipeline(cur) -> bool:
    """True se etl_malha_pipeline (migration 070) existe.

    F11 (§9.8/Decisão 70): o painel "Aguardando dependência" do Dashboard
    despejava o operador na LISTA de malhas (`navigate('/malha')`, sem malha e
    sem modo). Para levá-lo à malha certa é preciso saber a que malha o
    dependente pertence — e essa é a única razão desta sonda. Ausente = o link
    volta a ser o de hoje, que é a degradação correta: um deploy sem a 070 não
    pode transformar o Dashboard em 500."""
    try:
        cur.execute("SELECT OBJECT_ID('dbo.etl_malha_pipeline', 'U')")
        row = cur.fetchone()
        return bool(row and row[0] is not None)
    except Exception as e:
        log.warning("[DEP] checagem da tabela etl_malha_pipeline falhou: %s", e)
        return False


def assinatura(cur, pipeline: str, depende_de: str):
    """Assinatura da linha (pipeline, depende_de, PIPELINE) na 067:
    {"origem_no": id, "malha": nome} se ela foi COMPILADA por um nó de malha,
    None se é manual ou não existe. Chamar só com coluna_origem_no True."""
    cur.execute(
        "SELECT d.origem_no, n.malha_name "
        "FROM dbo.etl_pipeline_dependencia d "
        "LEFT JOIN dbo.etl_malha_no n ON n.id = d.origem_no "
        "WHERE d.pipeline_name = ? AND d.depende_de = ? AND d.tipo = 'PIPELINE'",
        (pipeline, depende_de))
    row = cur.fetchone()
    if row is None or row[0] is None:
        return None
    return {"origem_no": int(row[0]),
            "malha": (str(row[1]).strip() if row[1] else None)}


def linhas_assinadas(cur, pipeline: str) -> dict:
    """Linhas ASSINADAS do dependente: {casefold(depende_de): {"depende_de",
    "origem_no", "malha"}}. É o que o replace-all do register consulta ANTES
    do DELETE — remover uma delas por lá é 422 (Decisão 4), mantê-la na lista
    preserva a assinatura intacta (nunca re-gravada sem origem_no)."""
    cur.execute(
        "SELECT d.depende_de, d.origem_no, n.malha_name "
        "FROM dbo.etl_pipeline_dependencia d "
        "LEFT JOIN dbo.etl_malha_no n ON n.id = d.origem_no "
        "WHERE d.pipeline_name = ? AND d.tipo = 'PIPELINE' "
        "AND d.origem_no IS NOT NULL",
        (pipeline,))
    out = {}
    for r in cur.fetchall():
        dep = str(r[0] or "").strip()
        out[dep.casefold()] = {
            "depende_de": dep,
            "origem_no": int(r[1]),
            "malha": (str(r[2]).strip() if r[2] else None)}
    return out


def msg_linha_assinada(pipeline, depende_de, malha, origem_no) -> str:
    """Mensagem ÚNICA das três portas (Decisão 4): nomeia malha e nó donos e
    instrui a porta certa. Texto compartilhado de propósito — divergir entre
    as portas recriaria a classe cliente≠servidor que a F8 matou."""
    return (f"A dependência '{pipeline}' → '{depende_de}' é compilada pelo "
            f"Aguarde #{origem_no} da malha '{malha}' — edite pelo desenho da "
            "malha (linha assinada só se mexe pela malha dona).")
