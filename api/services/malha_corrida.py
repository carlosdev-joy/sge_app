"""
api/services/malha_corrida.py — a CORRIDA de malha como registro, vista da API
(F1 da spec docs/spec-malha-execucao.md §5 e §6).

PORT de dags/utils/malha_corrida.py — **o canônico é o de dags/**: quem mudar a
regra muda lá primeiro e espelha aqui, no mesmo commit. A cópia existe pelo mesmo
motivo de api/services/data_referencia.py (F9) e api/services/dependencias.py
(F5): `api/` e `dags/` são árvores de deploy separadas (o container da API não
embarca `dags/`), e um import cruzado quebraria no primeiro deploy parcial — que,
pela §11.1, é a célula MAIS PROVÁVEL da matriz, porque a etapa 7 (`api/`) é
automática e a etapa 5 (`dags/`) é padrão-NÃO.

A paridade é garantida por teste em dois níveis (precedente literal
tests/test_dependencias_f5_paridade.py): o SQL emitido tem de ser TEXTUALMENTE
idêntico ao do canônico depois de normalizar whitespace e placeholder, e a
matriz semântica tem de dar o MESMO resultado nas duas árvores. É por isso que
todo SQL mora em constante nomeada, com o MESMO nome dos dois lados: constante o
teste compara sem executar nada.

DUAS DIFERENÇAS DE FORMA, e só duas:
  • placeholder `?` (pyodbc — árvore `api/`); em `dags/` é `%s` (pymssql).
    Trocar dá "Incorrect syntax near '?'" com task VERDE — o GOTCHA do projeto;
  • **estas funções recebem `cur`** (cursor já aberto), como
    api/services/dependencias.py; no canônico elas recebem `conn` e abrem o
    cursor lá dentro. A API já carrega o cursor pela request inteira.

Fora isso o contrato é idêntico ao do canônico:
  • **nenhuma função abre conexão, commita ou faz rollback**: o CHAMADOR é dono
    da transação. Abrir a corrida e congelar o snapshot são UM commit só (§6.2),
    e fechar a corrida commita junto com o evento (Decisão 20);
  • todo relógio da corrida é o do BANCO (Decisão 10): `SYSDATETIME()`/`DATEADD`
    no SQL, nunca `datetime.now()` nem aritmética de timedelta em Python. No dev
    o SQL Server está ~3h à frente da API — medido, não suposto;
  • toda transição é `UPDATE ... WHERE <estado esperado>` com `rowcount` de
    árbitro (Decisão 8): `rowcount = 0` NÃO é erro, é "outra ponta chegou
    primeiro".

DEGRADAÇÃO — a política tem duas metades, de propósito (a mesma do canônico):
  • **leitura degrada larga**: sem a 085 (ou com o banco fora por um instante) a
    resposta é None/[]/False COM log, nunca exceção. É a regra do §16/10 — a tela
    volta ao comportamento de hoje;
  • **escrita degrada ESTREITA**: só os erros 207/208 (coluna/objeto inexistente)
    que nomeiem os objetos da 085 viram None/False com log; qualquer outro erro
    PROPAGA. Engolir um deadlock, um timeout ou uma violação de FK devolvendo
    "não abriu" faria o chamador seguir achando que não há corrida.

O QUE **NÃO** ESTÁ AQUI: `estado()` e a expiração preguiçosa da porta (Decisão
29). Não é omissão do port — o canônico também não os tem, e a razão está escrita
lá: `estado()` (§6.4) depende de `dia_permitido` e dos eventos órfãos que a
guardiã já sabe ler, e a expiração só pode expirar quando NÃO há membro vivo
(Decisão 25 / invariante §16/5), que é resposta do `estado()`. Os dois são
entregável da F2. Escrever aqui uma versão que ignorasse os vivos fecharia
corrida com 8 pipelines `EXECUTANDO` e liberaria o disparo por cima deles.

NENHUM CONSUMIDOR NESTA FASE: nenhum router chama este módulo na F1. É
deliberado (§10/F1) — o modelo entra antes, sozinho e provável.
"""
from __future__ import annotations

import logging
import time as _t

log = logging.getLogger("orquestra-api")

# ═════════════════════════ domínio (espelha a 085) ══════════════════════════
# Os CHECKs da migration são a autoridade; estas tuplas são o espelho em Python
# para recusar na BORDA o que o banco recusaria no meio da transação do
# chamador. Erro de domínio aqui é erro de PROGRAMA (ValueError), não
# degradação: um desfecho inventado é bug, não banco fora do ar.
STATUS_ABERTA = "ABERTA"
DESFECHOS = ("CONCLUIDA", "FALHA", "SEM_TRABALHO", "EXPIRADA",
             "ABORTADA", "CANCELADA")
ORIGENS = ("inicio", "manual", "implicita")
MODOS_FECHAMENTO = ("fim", "quiescencia")
# Só CONCLUIDA e FALHA reabrem (§6.1). SEM_TRABALHO, EXPIRADA, ABORTADA e
# CANCELADA são fim de linha: reabrir uma delas seria ressuscitar um ciclo que
# alguém (ou o teto) encerrou de propósito.
REABREM = ("CONCLUIDA", "FALHA")

# Defaults e domínios das configs da 085. Fora do domínio volta ao default —
# mesma regra de `janela_sequencia_horas`: teto 0 congelaria a malha para
# sempre e teto de mil horas transformaria a rede de segurança em decoração.
TETO_HORAS_PADRAO = 24
TETO_HORAS_MIN, TETO_HORAS_MAX = 1, 168
QUIESCENCIA_MIN_PADRAO = 15
QUIESCENCIA_MIN_MIN, QUIESCENCIA_MIN_MAX = 5, 240
CARENCIA_PARTIDA_PADRAO = 15
CARENCIA_PARTIDA_MIN, CARENCIA_PARTIDA_MAX = 1, 240

CHAVE_ATIVA = "malha_corrida_ativa"
CHAVE_TETO = "malha_teto_horas_padrao"
CHAVE_QUIESCENCIA = "malha_quiescencia_minutos"
CHAVE_CARENCIA = "malha_carencia_partida_min"

# Prefixo de log próprio: `[DEP]` é do predicado de dependência e `[MALHA]` é do
# ciclo da 081 — misturar os três num `grep` de plantão às 3h é ruído. O mesmo
# prefixo dos dois lados, para o grep atravessar worker e API.
LOG = "[CORRIDA]"

# ── Como se reconhece "a 085 não está aplicada" ─────────────────────────────
# Duas condições, e as DUAS são necessárias:
#   1. o número do erro é 207 (Invalid column name) ou 208 (Invalid object
#      name) — é o que separa "o objeto não existe" de qualquer outra coisa; e
#   2. a mensagem nomeia um objeto da 085.
# Só (2) — o atalho do `_MARCA_078` — daria falso positivo caro: a violação de
# FK_mexec_membro_corrida, o CHECK CK_mexec_status e o truncamento de string
# TAMBÉM citam a tabela na mensagem, e todos os três são BUG do chamador que
# precisa subir, não deploy parcial que precisa degradar.
# O código é o mesmo do canônico, e de propósito: o pymssql de lá entrega
# `args[0]` inteiro; o pyodbc daqui põe o código nativo entre parênteses no
# texto ("... Invalid column name 'malha_execucao_id'. (207) ..."), e é o
# segundo ramo que dispara. Nada disso depende do IDIOMA do SQL Server — a
# instalação da Caixa pode estar em pt-BR.
_ERROS_AUSENCIA = (207, 208)
_MARCAS_085 = ("etl_malha_execucao", "malha_execucao_id")

# Os dois índices únicos, distinguidos PELO NOME (Decisão 7): eles significam
# coisas OPOSTAS. `ux_malha_exec_aberta` = "outra ponta abriu primeiro, adira";
# `ux_malha_exec_seq` = "outra corrida do mesmo dia levou a sequência, recalcule
# e tente de novo". Um handler genérico de 2601 aderiria à corrida errada — ou,
# pior, a uma corrida FECHADA, deixando linhas carimbadas com id de ciclo
# encerrado, invisíveis para o ciclo vivo.
IX_ABERTA = "ux_malha_exec_aberta"
IX_SEQUENCIA = "ux_malha_exec_seq"
_TENTATIVAS_ABERTURA = 3

# Projeção explícita e ÚNICA da corrida (nunca `SELECT *`: o canônico tem de
# emitir o mesmo texto, e a ordem das colunas é o contrato de `_como_dict`).
# `criado_em`/`atualizado_em` ficam de fora — são auditoria; os relógios da
# corrida são `aberta_em`, `fechada_em` e `teto_em`.
_COLS = (
    "id, malha_name, data_referencia, sequencia, status, aberta_em, fechada_em, "
    "fechada_por, origem, aberta_por, ancora_pipeline, ancora_execution_id, "
    "no_inicio, no_fim, modo_fechamento, teto_em, teto_creditado_min, "
    "falha_vista_em, atraso_visto_em, tentativas, reaberta_em, reaberta_por, "
    "motivo")
# Derivado do texto, não digitado de novo: assim é impossível a projeção e o
# dicionário divergirem quando alguém acrescentar uma coluna.
_CAMPOS = tuple(c.strip() for c in _COLS.split(","))
_COLS_ME = ", ".join("me." + c for c in _CAMPOS)
_COLS_OUTPUT = ", ".join("inserted." + c for c in _CAMPOS)
_INTEIROS = ("id", "sequencia", "no_inicio", "no_fim", "teto_creditado_min",
             "tentativas")


def _como_dict(row) -> dict:
    """Linha da projeção `_COLS` → dict. Os inteiros são coeridos para `int`
    porque pymssql e pyodbc discordam no tipo devolvido para BIGINT/INT e o id
    da corrida viaja daqui para dentro de outro SQL."""
    d = dict(zip(_CAMPOS, row))
    for campo in _INTEIROS:
        if d.get(campo) is not None:
            d[campo] = int(d[campo])
    return d


def _sem_085(e) -> bool:
    """O erro é "a 085 não está neste banco"? (ver o bloco `_ERROS_AUSENCIA`)"""
    texto = str(e)
    if not any(marca in texto for marca in _MARCAS_085):
        return False
    args = getattr(e, "args", ())
    if args and isinstance(args[0], int) and args[0] in _ERROS_AUSENCIA:
        return True
    return any("(%d)" % codigo in texto for codigo in _ERROS_AUSENCIA)


def _violou(e, indice: str) -> bool:
    """A exceção é violação de chave única do índice `indice`?

    Casa o NOME do índice, não o número do erro: 2601 sozinho não diz QUAL
    invariante foi tocada, e as duas da corrida pedem reações opostas."""
    return indice in str(e)


def _inteiro_no_dominio(valor, minimo: int, maximo: int):
    """Texto/número → int dentro de [minimo, maximo], ou None."""
    try:
        n = int(str(valor).strip())
    except (TypeError, ValueError):
        return None
    return n if minimo <= n <= maximo else None


# ═══════════════════ o interruptor (§11.2, Decisão 51) ══════════════════════

_CACHE_ATIVA: dict = {}
# ⚠️ DIVERGÊNCIA DELIBERADA do canônico, com precedente literal: lá o
# interruptor é lido uma vez por PROCESSO, porque a task do Airflow é curta e
# morre levando o cache. O processo da API é LONGO — cachear para sempre faria
# o operador virar a chave no Admin e ter de reiniciar o container para ela
# valer. Mesmo desenho e mesmo TTL de `modo_sequencia`
# (api/services/dependencias.py:141), e o teste de paridade daquela dupla já
# acomoda as duas formas de cache no fixture.
_TTL_ATIVA_S = 30


def limpar_cache() -> None:
    """Esquece o interruptor lido. Existe para TESTE e para quem quiser
    reavaliar no mesmo processo."""
    _CACHE_ATIVA.clear()


def corrida_ativa(cur) -> bool:
    """A corrida de malha está LIGADA? (`etl_app_config.malha_corrida_ativa`)

    É o kill switch do §11.2: com `0`, nada abre, nada fecha, o card usa o
    fallback e o ODATE fica no degrau de hoje. Nasce em `0` na própria 085 e só
    vai a `1` depois da F7 e do smoke — todas as mudanças recentes de
    comportamento do motor entraram atrás de uma chave em `etl_app_config`
    (`dependencia_modo_sequencia`, `dependencia_janela_sequencia_horas`), porque
    sem ela o rollback é "reverter o merge e refazer o deploy", às 3h.

    Ausente (banco sem a 085), ilegível ou banco fora → **False**: o interruptor
    nunca liga sozinho, e é ele quem faz "sem a 085" e "desligado" serem o mesmo
    caminho para todos os chamadores.

    Cacheado por 30s (ver `_TTL_ATIVA_S`), não pelo processo inteiro como no
    canônico: virar a chave no Admin passa a valer no refresh seguinte, sem
    reiniciar container nenhum."""
    agora = _t.time()
    if _CACHE_ATIVA.get("ate", 0) > agora:
        return _CACHE_ATIVA["ativa"]
    valor = False
    try:
        cur.execute("SELECT config_value FROM dbo.etl_app_config "
                    "WHERE config_key = ?", (CHAVE_ATIVA,))
        row = cur.fetchone()
        valor = bool(row) and str(row[0] or "").strip() in ("1", "true", "True")
    # WARNING, não DEBUG: a falha de leitura do kill switch é o caminho por onde
    # a feature fica desligada SEM ninguém saber — e o nível padrão do container
    # é INFO, então em `debug` a linha não existe para o plantão. O canônico
    # imprime sempre; aqui o TTL de 30s já limita a repetição.
    except Exception as e:  # noqa: BLE001 — sem config não há corrida, e ponto
        log.warning("%s interruptor %s indisponivel (%s) — corrida DESLIGADA",
                    LOG, CHAVE_ATIVA, e)
    _CACHE_ATIVA.update({"ativa": valor, "ate": agora + _TTL_ATIVA_S})
    if valor:
        log.info("%s corrida de malha LIGADA", LOG)
    return valor


def tabela_085_presente(cur) -> bool:
    """As duas tabelas e a coluna de vínculo da 085 existem?

    Mesma razão da sonda da 067/075 (D52): a sonda é SQL, e SQL não entra na
    DAG. Serve para a API dizer "085 ausente" uma vez em vez de descobrir isso
    malha a malha — o interruptor já cobre o caminho normal, esta sonda cobre o
    diagnóstico e a flag `migration_085_pendente` do card (Decisão 41)."""
    try:
        cur.execute(
            "SELECT OBJECT_ID('dbo.etl_malha_execucao','U'), "
            "OBJECT_ID('dbo.etl_malha_execucao_membro','U'), "
            "COL_LENGTH('dbo.etl_pipeline_execucao','malha_execucao_id')")
        row = cur.fetchone()
        return bool(row) and all(v is not None for v in row)
    except Exception as e:  # noqa: BLE001
        log.warning("%s sonda da 085 indisponivel (%s) — assumindo ausente",
                    LOG, e)
        return False


# ═══════════════════════ configs numéricas (§6.6, §6.5) ═════════════════════
# NÃO são cacheadas por processo, ao contrário do interruptor: são lidas uma vez
# por corrida (não por membro), e um teto que só muda depois de reiniciar o
# worker seria uma armadilha justamente na madrugada em que alguém precisa
# alargar a janela.

SQL_TETO_DA_MALHA = (
    "SELECT m.teto_horas, c.config_value FROM dbo.etl_malha m "
    "LEFT JOIN dbo.etl_app_config c ON c.config_key = '" + CHAVE_TETO + "' "
    "WHERE m.malha_name = ?")


def teto_horas_da_malha(cur, malha: str) -> int:
    """Teto da corrida desta malha, em horas: `etl_malha.teto_horas` ?? config
    global ?? 24 — resolvido em UMA consulta (a forma de `virada_efetiva`).

    O teto é OBRIGATÓRIO (§6.6): corrida `ABERTA` bloqueia o disparo, então uma
    corrida sem teto seria estritamente pior que o estado de hoje — congelaria a
    malha para sempre, sem tela para destravar. É a classe do `factory_log`
    órfão em RUNNING, elevada da geração para o ciclo.

    Malha inexistente, coluna ausente (sem a 085/081) ou valor fora de
    1..168 → o padrão. Nunca devolve 0."""
    try:
        cur.execute(SQL_TETO_DA_MALHA, (malha,))
        row = cur.fetchone()
    except Exception as e:  # noqa: BLE001 — sem teto lido, o padrão protege
        log.warning("%s teto de %s indisponivel (%s) — usando %sh",
                    LOG, malha, e, TETO_HORAS_PADRAO)
        return TETO_HORAS_PADRAO
    if not row:
        return TETO_HORAS_PADRAO
    da_malha = _inteiro_no_dominio(row[0], TETO_HORAS_MIN, TETO_HORAS_MAX)
    if da_malha is not None:
        return da_malha
    global_ = _inteiro_no_dominio(row[1], TETO_HORAS_MIN, TETO_HORAS_MAX)
    return global_ if global_ is not None else TETO_HORAS_PADRAO


def _config_int(cur, chave: str, padrao: int, minimo: int, maximo: int) -> int:
    cur.execute("SELECT config_value FROM dbo.etl_app_config "
                "WHERE config_key = ?", (chave,))
    row = cur.fetchone()
    n = _inteiro_no_dominio(row[0], minimo, maximo) if row else None
    return n if n is not None else padrao


def quiescencia_minutos(cur) -> int:
    """Carência de quiescência, em minutos (5..240, padrão 15 = 3 ciclos da
    guardiã): tempo sem NENHUM membro vivo antes de a corrida poder fechar por
    quiescência.

    O piso não é decorativo: `_registrar_sucesso` commita o SUCESSO e **só
    então** chama `_disparar_dependentes` — segundos no caminho feliz, minutos
    quando o push falha e a rede de segurança assume. Uma carência curta fecharia
    a corrida exatamente nessa fresta, no meio dela mesma."""
    try:
        return _config_int(cur, CHAVE_QUIESCENCIA, QUIESCENCIA_MIN_PADRAO,
                           QUIESCENCIA_MIN_MIN, QUIESCENCIA_MIN_MAX)
    except Exception as e:  # noqa: BLE001
        log.warning("%s %s indisponivel (%s) — usando %s min",
                    LOG, CHAVE_QUIESCENCIA, e, QUIESCENCIA_MIN_PADRAO)
        return QUIESCENCIA_MIN_PADRAO


def carencia_partida_min(cur) -> int:
    """Carência de partida, em minutos (1..240, padrão 15): piso absoluto desde
    `aberta_em` antes de uma corrida com ZERO linhas poder ser `ABORTADA`
    (Decisão 28).

    Existe porque o disparo manual fecha o banco ANTES de chamar o Airflow: entre
    o commit da corrida e o primeiro `EXECUTANDO` há latência de scheduler, pool
    saturado, DAG pausada e `nao_iniciar_antes`. Sem o piso, a guardiã que passa
    nessa fresta aborta a corrida e as raízes registram `EXECUTANDO` apontando
    para um ciclo já encerrado — o card volta a mentir e o disparo seguinte é
    liberado por cima da malha rodando."""
    try:
        return _config_int(cur, CHAVE_CARENCIA, CARENCIA_PARTIDA_PADRAO,
                           CARENCIA_PARTIDA_MIN, CARENCIA_PARTIDA_MAX)
    except Exception as e:  # noqa: BLE001
        log.warning("%s %s indisponivel (%s) — usando %s min",
                    LOG, CHAVE_CARENCIA, e, CARENCIA_PARTIDA_PADRAO)
        return CARENCIA_PARTIDA_PADRAO


# ══════════════════════ o ODATE canônico (Decisão 18) ═══════════════════════

SQL_VIRADA_DA_MALHA = (
    "SELECT m.hora_virada, c.config_value FROM dbo.etl_malha m "
    "LEFT JOIN dbo.etl_app_config c ON c.config_key = 'dependencia_hora_virada' "
    "WHERE m.malha_name = ?")
SQL_VIRADA_GLOBAL = (
    "SELECT config_value FROM dbo.etl_app_config "
    "WHERE config_key = 'dependencia_hora_virada'")


def odate_da_abertura(cur, malha: str, momento):
    """O ODATE que a corrida desta malha carimba ao nascer:
    `calcular(momento, etl_malha.hora_virada ?? virada global)`.

    **Uma função, três portas** (Decisão 18). Hoje existem três fórmulas: a API
    usa a virada GLOBAL (com a divergência painel×disparo confessada em
    api/routers/malhas.py:2377-2384), o `check_agenda` usa a virada do PIPELINE e
    a 081 introduziu a virada da MALHA. Com abertura INSERT-first, quem vencesse o
    índice carimbaria o ODATE do ciclo inteiro — disparar às 02:00 pela tela e
    pelo cron no mesmo minuto produziria ciclos com DIAS diferentes conforme
    quem chegasse primeiro: não-determinismo puro. A virada do PIPELINE nunca
    abre corrida de malha; ela continua valendo para pipeline fora de malha.

    `momento` é do relógio do BANCO (Decisão 10) — no dev o banco está 3h à
    frente da API, e passar `datetime.now()` aqui é o defeito que a Decisão 10
    nomeia.

    Degradação: se a leitura falhar (banco sem a 081, por exemplo) a virada cai
    para a GLOBAL e, em último caso, para 00:00 — que é o comportamento anterior
    a esta spec, não um terceiro comportamento inventado."""
    from services.data_referencia import calcular  # lazy: mantém o módulo puro
    # de dependências de import para o carregamento por caminho dos testes de
    # paridade, e é o mesmo gesto do canônico.
    bruto = None
    try:
        cur.execute(SQL_VIRADA_DA_MALHA, (malha,))
        row = cur.fetchone()
        if row:
            bruto = row[0] if row[0] is not None else row[1]
    except Exception as e:  # noqa: BLE001 — sem a 081 ainda há a virada global
        log.warning("%s virada de %s indisponivel (%s) — tentando a global",
                    LOG, malha, e)
        try:
            cur.execute(SQL_VIRADA_GLOBAL)
            row = cur.fetchone()
            bruto = row[0] if row else None
        except Exception as e2:  # noqa: BLE001
            log.warning("%s virada global indisponivel (%s) — usando 00:00",
                        LOG, e2)
    return calcular(momento, bruto)


# ═════════════════════════════ leituras ═════════════════════════════════════

SQL_CORRIDA_ABERTA = (
    "SELECT " + _COLS + " FROM dbo.etl_malha_execucao "
    "WHERE malha_name = ? AND fechada_em IS NULL")
SQL_CORRIDAS_ABERTAS = (
    "SELECT " + _COLS + " FROM dbo.etl_malha_execucao "
    "WHERE fechada_em IS NULL ORDER BY malha_name")
SQL_CORRIDA_POR_ID = (
    "SELECT " + _COLS + " FROM dbo.etl_malha_execucao WHERE id = ?")
SQL_ABERTAS_DO_PIPELINE = (
    "SELECT " + _COLS_ME + " FROM dbo.etl_malha_execucao me "
    "JOIN dbo.etl_malha_pipeline mp ON mp.malha_name = me.malha_name "
    "WHERE mp.pipeline_name = ? AND me.fechada_em IS NULL "
    "ORDER BY me.malha_name")
SQL_MEMBROS = (
    "SELECT pipeline_name, conta_para_fim, ativo_na_abertura, eh_raiz "
    "FROM dbo.etl_malha_execucao_membro WHERE malha_execucao_id = ? "
    "ORDER BY pipeline_name")


def corrida_aberta(cur, malha: str):
    """A corrida ABERTA da malha, ou None.

    A releitura é SEMPRE `malha_name = ? AND fechada_em IS NULL` — **jamais**
    por `(malha, data)` (Decisão 7). Identidade é o `id`; `(malha, data)` é o
    beco do qual esta spec inteira sai: duas corridas no mesmo ODATE são
    legítimas (redisparo) e colidiriam.

    `fechada_em IS NULL` é o MESMO predicado do índice filtrado
    `ux_malha_exec_aberta`, e o `CK_mexec_coerente` garante que ele e
    `status = 'ABERTA'` não podem discordar — por isso não se filtra por
    status: seria uma segunda régua para o mesmo fato."""
    try:
        cur.execute(SQL_CORRIDA_ABERTA, (malha,))
        row = cur.fetchone()
        return _como_dict(row) if row else None
    except Exception as e:  # noqa: BLE001 — leitura degrada larga (docstring do módulo)
        log.warning("%s corrida aberta de %s indisponivel (%s) — seguindo sem",
                    LOG, malha, e)
        return None


def corridas_abertas(cur) -> list:
    """TODAS as corridas abertas, por malha — o universo do card da lista.

    Uma consulta só para a tela inteira (nunca uma por malha): é o mesmo
    princípio do `GROUP BY` único que api/routers/malhas.py:1529-1530 se proíbe
    em comentário de virar N+1."""
    try:
        cur.execute(SQL_CORRIDAS_ABERTAS)
        return [_como_dict(r) for r in cur.fetchall()]
    except Exception as e:  # noqa: BLE001
        log.warning("%s corridas abertas indisponiveis (%s) — card no fallback",
                    LOG, e)
        return []


def corrida(cur, corrida_id):
    """A corrida por id, aberta ou fechada — a releitura de quem acabou de
    fechar/reabrir e precisa do registro para o evento e o log."""
    try:
        cur.execute(SQL_CORRIDA_POR_ID, (int(corrida_id),))
        row = cur.fetchone()
        return _como_dict(row) if row else None
    except Exception as e:  # noqa: BLE001
        log.warning("%s corrida #%s indisponivel (%s) — seguindo sem",
                    LOG, corrida_id, e)
        return None


def corrida_aberta_do_pipeline(cur, pipeline: str) -> dict:
    """As corridas abertas das malhas de que `pipeline` é membro, e o veredito
    sobre o ODATE — o degrau 3 do §7 (Decisão 33).

    Devolve `{"corridas": [...], "odate": date|None, "ambiguo": bool}`.

    É o conserto do incidente `Carga_Vida` para quem **não foi republicado**: o
    membro com cron próprio, em vez de calcular a própria data, ADERE ao ODATE do
    ciclo em voo. Sem este degrau a proteção existiria só para quem já tinha sido
    republicado — que é exatamente por que a 081 não fechou o caso.

    **`ambiguo` nunca é resolvido por escolha** (Decisão 34): duas corridas
    abertas com ODATEs diferentes para o mesmo pipeline devolvem `odate=None` e
    `ambiguo=True`, e o chamador PULA com motivo nominal. Escolher uma seria
    reintroduzir a doença com rótulo novo. Duas corridas com o MESMO ODATE não
    são ambiguidade nenhuma — a resposta é a mesma data.

    Não filtra por `etl_malha.ativo`: corrida já aberta segue até fechar mesmo
    que alguém inative a malha no meio do voo (§6.9/#8), e filtrar por `ativo`
    esconderia justamente a corrida que está carimbando as linhas agora."""
    corridas: list = []
    try:
        cur.execute(SQL_ABERTAS_DO_PIPELINE, (pipeline,))
        corridas = [_como_dict(r) for r in cur.fetchall()]
    except Exception as e:  # noqa: BLE001
        log.warning("%s corridas abertas de %s indisponiveis (%s) — seguindo sem",
                    LOG, pipeline, e)
        return {"corridas": [], "odate": None, "ambiguo": False}
    odates = {c["data_referencia"] for c in corridas}
    if len(odates) > 1:
        log.warning("%s %s e membro de %d corridas abertas com ODATEs "
                    "diferentes — ambiguo, sem escolha",
                    LOG, pipeline, len(corridas))
        return {"corridas": corridas, "odate": None, "ambiguo": True}
    return {"corridas": corridas,
            "odate": next(iter(odates)) if odates else None,
            "ambiguo": False}


# ═══════════ o ODATE do §7 — a precedência num lugar só (F5) ════════════════
#
# Port do canônico `dags/utils/malha_corrida.py`. O motor é quem CARIMBA; esta
# árvore existe para que a API responda a mesma coisa que ele — o disparo avulso
# e o painel precisam saber qual ODATE uma execução TERIA, e uma segunda régua
# aqui é como a tela e o motor voltam a discordar sobre o mesmo fato.

# ⚠️ SEM `substituida_em IS NULL`, e de PROPOSITO — e a unica consulta do
# projeto sobre etl_pipeline_execucao que a omite, entao a ausencia precisa
# estar escrita ou alguem "conserta". As outras perguntam "o que CONTA para a
# corrida", e linha aposentada por rerun nao conta. Esta pergunta e outra:
# "que ODATE ESTE run ja carimbou" — identidade, nao contagem. Se o rerun
# aposentou a linha, o run_id continua sendo o mesmo e a data dele tambem;
# filtrar aqui faria a task seguinte do MESMO run cair no degrau 3/4 e
# eventualmente gravar uma segunda linha noutro dia, que e a doenca que este
# degrau existe para impedir.
SQL_ODATE_DO_RUN = (
    "SELECT TOP 1 data_referencia, malha_execucao_id "
    "FROM dbo.etl_pipeline_execucao "
    "WHERE pipeline_name = ? AND execution_id = ? "
    "ORDER BY id")

SQL_CORRIDA_DO_CONF = (
    "SELECT " + _COLS_ME + " FROM dbo.etl_malha_execucao me "
    "JOIN dbo.etl_malha_pipeline mp ON mp.malha_name = me.malha_name "
    "WHERE me.id = ? AND mp.pipeline_name = ? AND me.fechada_em IS NULL")

DEGRAU_CARIMBO = "carimbo"
DEGRAU_CONF_CORRIDA = "conf_corrida"
DEGRAU_CONF_DATA = "conf_data"
DEGRAU_CORRIDA = "corrida"
DEGRAU_CALCULO = "calculo"

MOTIVO_ODATE_AMBIGUO = "MALHA_ODATE_AMBIGUO"


def _odate_carimbado(cur, pipeline: str, run_id) -> dict:
    """Degrau 0 — o que a linha deste run já gravou, ou `{}`."""
    try:
        cur.execute(SQL_ODATE_DO_RUN, (pipeline, str(run_id)))
        row = cur.fetchone()
    except Exception as e:  # noqa: BLE001 — leitura degrada larga
        log.warning("%s carimbo do run %s indisponivel (%s) — seguindo pelos degraus",
                    LOG, run_id, e)
        return {}
    if not row or row[0] is None:
        return {}
    return {"data": row[0],
            "corrida_id": int(row[1]) if row[1] is not None else None}


def _corrida_do_conf(cur, conf_id, pipeline: str):
    """Degrau 1 — a corrida do conf, **se** aberta e de malha deste pipeline."""
    try:
        alvo = int(str(conf_id).strip())
    except (TypeError, ValueError):
        log.warning("%s conf malha_execucao_id invalido (%r) — tratado como AUSENTE",
                    LOG, conf_id)
        return None
    try:
        cur.execute(SQL_CORRIDA_DO_CONF, (alvo, pipeline))
        row = cur.fetchone()
    except Exception as e:  # noqa: BLE001 — leitura degrada larga
        log.warning("%s corrida #%s do conf indisponivel (%s) — tratada como AUSENTE",
                    LOG, alvo, e)
        return None
    if row is None:
        log.warning("%s conf aponta a corrida #%s, que nao esta aberta ou nao e de "
                    "malha de %s — tratado como AUSENTE (Decisao 37)",
                    LOG, alvo, pipeline)
        return None
    return _como_dict(row)


def _dona_do_odate(cur, pipeline: str, data_ref, conf_id=None):
    """A corrida DONA de uma data já decidida, ou None — nunca muda a data."""
    if conf_id is not None:
        c = _corrida_do_conf(cur, conf_id, pipeline)
        if c is not None and c["data_referencia"] == data_ref:
            return c["id"]
    aberta = corrida_aberta_do_pipeline(cur, pipeline)
    donas = [c for c in aberta["corridas"] if c["data_referencia"] == data_ref]
    return donas[0]["id"] if len(donas) == 1 else None


def odate(cur, pipeline: str, run_id=None, conf_id=None, herdada=None) -> dict:
    """A precedência do §7 (degraus 0 a 3) para UM run deste pipeline.

    Gêmea da função canônica de `dags/utils/malha_corrida.py` — a documentação
    inteira dos degraus está lá, e é lá que se muda a regra primeiro.
    """
    vazio = {"data": None, "corrida_id": None, "ambiguo": False,
             "degrau": None, "detalhe": None}
    if not corrida_ativa(cur):
        return vazio
    if run_id:
        carimbo = _odate_carimbado(cur, pipeline, run_id)
        if carimbo:
            # O degrau 0 decide a DATA, e só ela — a proveniência continua
            # sendo procurada quando a linha ainda não tem dono (ver o
            # comentário do canônico: é o caso do dependente, cuja linha nasce
            # no claim do pai, sem vínculo).
            if carimbo["corrida_id"] is not None:
                return {**vazio, "data": carimbo["data"],
                        "corrida_id": carimbo["corrida_id"],
                        "degrau": DEGRAU_CARIMBO}
            return {**vazio, "data": carimbo["data"],
                    "corrida_id": _dona_do_odate(cur, pipeline,
                                                 carimbo["data"], conf_id),
                    "degrau": DEGRAU_CARIMBO}
    if conf_id is not None:
        c = _corrida_do_conf(cur, conf_id, pipeline)
        if c is not None:
            return {**vazio, "data": c["data_referencia"],
                    "corrida_id": c["id"], "degrau": DEGRAU_CONF_CORRIDA}
    aberta = corrida_aberta_do_pipeline(cur, pipeline)
    if herdada is not None:
        dona = (aberta["corridas"][0] if len(aberta["corridas"]) == 1
                and aberta["odate"] == herdada else None)
        if aberta["ambiguo"]:
            log.warning("%s %s tem corridas abertas com ODATEs diferentes, mas a "
                        "data %s veio herdada — a heranca prevalece",
                        LOG, pipeline, herdada)
        elif aberta["odate"] is not None and dona is None:
            log.warning("%s %s: data herdada %s difere do ODATE %s da corrida "
                        "aberta — a heranca prevalece e a linha fica sem "
                        "proveniencia", LOG, pipeline, herdada, aberta["odate"])
        return {**vazio, "data": herdada,
                "corrida_id": (dona["id"] if dona else None),
                "degrau": DEGRAU_CONF_DATA}
    if aberta["ambiguo"]:
        datas = ", ".join(sorted(f"#{c['id']} ({c['data_referencia']})"
                                 for c in aberta["corridas"]))
        return {**vazio, "ambiguo": True, "degrau": DEGRAU_CORRIDA,
                "detalhe": (f"{MOTIVO_ODATE_AMBIGUO}: {pipeline} e membro de "
                            f"corridas abertas com ODATEs diferentes — {datas}. "
                            f"Encerre a corrida que nao deveria estar aberta "
                            f"(Malha ▸ Encerrar corrida) e dispare de novo")}
    if aberta["odate"] is not None:
        unica = aberta["corridas"][0] if len(aberta["corridas"]) == 1 else None
        if unica is None:
            log.warning("%s %s e membro de %d corridas abertas no MESMO ODATE %s "
                        "— data resolvida, proveniencia sem dono",
                        LOG, pipeline, len(aberta["corridas"]), aberta["odate"])
        return {**vazio, "data": aberta["odate"],
                "corrida_id": (unica["id"] if unica else None),
                "degrau": DEGRAU_CORRIDA}
    return vazio


def membros(cur, corrida_id) -> list:
    """O snapshot congelado da corrida: `[{pipeline, conta_para_fim,
    ativo_na_abertura, eh_raiz}]`, por pipeline.

    É o DENOMINADOR do "4 de 7", e ele é do desenho **no instante da abertura**:
    editar a malha durante o ciclo não muda a conta desta corrida (§6.9/#16) —
    vale da próxima em diante. Sem isso, o denominador mudaria embaixo do
    operador no meio da madrugada."""
    try:
        cur.execute(SQL_MEMBROS, (int(corrida_id),))
        return [{"pipeline": r[0], "conta_para_fim": bool(r[1]),
                 "ativo_na_abertura": bool(r[2]), "eh_raiz": bool(r[3])}
                for r in cur.fetchall()]
    except Exception as e:  # noqa: BLE001
        log.warning("%s membros da corrida #%s indisponiveis (%s)",
                    LOG, corrida_id, e)
        return []


# ═════════════════════════════ abertura ═════════════════════════════════════

# INSERT-first, nunca SELECT-then-INSERT (Decisão 14): entre o clique no botão e
# o ciclo da guardiã existe uma janela real, porque as duas pontas consultam e
# decidem separadamente. Claim, não check — o padrão de `reservar_corrida`.
#
# A `sequencia` sai de DENTRO do próprio INSERT, sob (UPDLOCK, HOLDLOCK) na faixa
# (malha_name, data_referencia) (Decisão 6): dois redisparos simultâneos
# calculariam MAX+1 = 2 os dois e um violaria `ux_malha_exec_seq` — um índice
# DIFERENTE do de abertura, cujo tratamento é oposto.
#
# `aberta_em` entra por uma tabela derivada (`v.ab`) em vez de repetir
# `SYSDATETIME()` duas vezes: `teto_em` é `aberta_em + teto`, e duas avaliações
# do relógio no mesmo INSERT deixariam o teto microssegundos fora do que a tela
# mostra como início. Uma avaliação só, provada pela estrutura, não por confiança
# no otimizador.
SQL_ABRIR = (
    "INSERT INTO dbo.etl_malha_execucao "
    "(malha_name, data_referencia, sequencia, status, aberta_em, origem, "
    "aberta_por, ancora_pipeline, ancora_execution_id, no_inicio, no_fim, "
    "modo_fechamento, teto_em, motivo) "
    "OUTPUT " + _COLS_OUTPUT + " "
    "SELECT ?, ?, "
    "(SELECT ISNULL(MAX(x.sequencia), 0) + 1 FROM dbo.etl_malha_execucao x "
    "WITH (UPDLOCK, HOLDLOCK) "
    "WHERE x.malha_name = ? AND x.data_referencia = ?), "
    "'ABERTA', v.ab, ?, ?, ?, ?, ?, ?, ?, "
    "DATEADD(HOUR, ?, v.ab), ? "
    "FROM (SELECT COALESCE(CAST(? AS DATETIME2), SYSDATETIME()) AS ab) v")


def abrir_corrida(cur, malha: str, odate, origem: str, *,
                  aberta_por=None, aberta_em=None, ancora_pipeline=None,
                  ancora_execution_id=None, no_inicio=None, no_fim=None,
                  modo_fechamento="quiescencia", teto_horas=None, motivo=None):
    """Abre a corrida da malha — ou ADERE à que já está aberta.

    Devolve o dict da corrida acrescido de:
      • `nova`          — True se esta chamada a criou;
      • `odate_confere` — se o ODATE pedido é o da corrida devolvida.
    Devolve None quando a 085 não está no banco (com log).

    **Violação de `ux_malha_exec_aberta` não é erro** (Decisão 14): significa que
    outra ponta abriu primeiro. Relê por `malha_name AND fechada_em IS NULL` e
    devolve a existente com `nova=False`. Violação de `ux_malha_exec_seq`
    significa outra coisa — recalcular a sequência e tentar de novo (Decisão 7).

    `odate_confere` vem no retorno em vez de ficar a cargo do chamador porque a
    adesão TEM de conferir o ODATE (Decisão 15): corrida de terça travada, quarta
    01:00 o cron parte, adere à corrida de terça e carimba **terça** em toda a
    carga de quarta — e para o motor está tudo coerente, porque é uma corrida só.
    É o `Carga_Vida` por dentro do mecanismo criado para matá-lo. Divergiu, o
    chamador PULA com motivo nominal e emite `DATA_DIVERGENTE`; o caminho
    automático de hoje já recusa nesse caso, e trocar recusa explícita por adesão
    silenciosa seria regressão.

    `aberta_em` **recua** para o `COALESCE(inicio, criado_em)` da linha âncora nas
    portas 2 e 3 (guardiã) — a corrida nasce até um ciclo (5 min) depois de a raiz
    partir, e sem o recuo ela "perderia" o trabalho que a originou. `None` =
    agora, no relógio do banco (porta 1, o disparo manual — que é a porta desta
    árvore).

    `modo_fechamento` é derivado do DESENHO na abertura e congela com ele
    (§6.9/#1): `'fim'` quando a malha tem nó Fim, `'quiescencia'` — o padrão, e o
    caso de 3 em 4 malhas do dev — quando não tem. Nunca é configurado à mão.

    ⚠️ Quem abre **congela o snapshot no mesmo commit** (`congelar_snapshot`):
    corrida sem membros tem denominador zero e a §6.5 a levaria a `ABORTADA`
    depois da carência de partida, com a malha rodando ao lado."""
    if origem not in ORIGENS:
        raise ValueError(f"origem invalida: {origem!r} (esperado {ORIGENS})")
    if modo_fechamento not in MODOS_FECHAMENTO:
        raise ValueError(f"modo_fechamento invalido: {modo_fechamento!r} "
                         f"(esperado {MODOS_FECHAMENTO})")
    # O override do chamador passa pelo MESMO domínio da config (1..168) — não
    # é confiança no chamador, é a mesma trava. `teto_horas=0` nasceria com
    # `teto_em = aberta_em`, isto é, corrida EXPIRADA no ato de abrir, e o teto é
    # a única rede que impede corrida aberta de congelar o disparo (§6.6). Fora
    # do domínio (ou `None`) resolve pela malha, nunca por um teto inventado.
    teto = _inteiro_no_dominio(teto_horas, TETO_HORAS_MIN, TETO_HORAS_MAX)
    if teto is None:
        teto = teto_horas_da_malha(cur, malha)
    params = (malha, odate, malha, odate, origem, aberta_por, ancora_pipeline,
              ancora_execution_id, no_inicio, no_fim, modo_fechamento, teto,
              motivo, aberta_em)
    for tentativa in range(1, _TENTATIVAS_ABERTURA + 1):
        try:
            cur.execute(SQL_ABRIR, params)
            row = cur.fetchone()
            if row:
                nova = _como_dict(row)
                nova["nova"] = True
                nova["odate_confere"] = nova["data_referencia"] == odate
                return nova
            # INSERT sem OUTPUT devolvido não deveria acontecer; tratar como
            # "não abri" é mais honesto que devolver um dict pela metade.
            log.warning("%s abertura de %s nao devolveu a linha — sem corrida",
                        LOG, malha)
            return None
        except Exception as e:  # noqa: BLE001 — três casos NOMEADOS, o resto sobe
            if _violou(e, IX_ABERTA):
                # O canônico abre um cursor NOVO aqui, porque o anterior morreu
                # no meio de um INSERT com OUTPUT. Aqui o cursor é do chamador e
                # não temos como trocá-lo — no pyodbc um erro em `execute` não
                # deixa resultado pendente, então o `execute` seguinte é válido.
                # Isto é AFIRMAÇÃO TESTADA contra o SQL Server do dev, não
                # suposição sobre o driver.
                existente = corrida_aberta(cur, malha)
                if existente is not None:
                    existente["nova"] = False
                    existente["odate_confere"] = existente["data_referencia"] == odate
                    return existente
                # Fechou entre a violação e a releitura — a vaga do índice
                # filtrado vagou; tentar de novo é a resposta certa.
                log.info("%s corrida de %s fechou durante a abertura — "
                         "tentando de novo (%s/%s)",
                         LOG, malha, tentativa, _TENTATIVAS_ABERTURA)
                continue
            if _violou(e, IX_SEQUENCIA):
                log.info("%s sequencia de %s em %s tomada por outra ponta — "
                         "recalculando (%s/%s)",
                         LOG, malha, odate, tentativa, _TENTATIVAS_ABERTURA)
                continue
            if _sem_085(e):
                log.warning("%s 085 ausente (%s) — corrida de %s nao aberta",
                            LOG, e, malha)
                return None
            raise
    log.warning("%s abertura de %s desistiu apos %s tentativas — sem corrida "
                "neste ciclo", LOG, malha, _TENTATIVAS_ABERTURA)
    return None


# O snapshot é IDEMPOTENTE (o NOT EXISTS final): a abertura pode ter aderido a
# uma corrida que já congelou, e uma violação de PK aqui rolaria de volta a
# transação de quem chamou — inclusive o INSERT da corrida.
_SQL_SNAPSHOT = (
    "INSERT INTO dbo.etl_malha_execucao_membro "
    "(malha_execucao_id, pipeline_name, conta_para_fim, ativo_na_abertura, eh_raiz) "
    "SELECT ?, mp.pipeline_name, "
    "CASE WHEN {conta} THEN 1 ELSE 0 END, "
    "CASE WHEN ISNULL(p.active, 0) = 1 THEN 1 ELSE 0 END, "
    "CASE WHEN NOT EXISTS (SELECT 1 FROM dbo.etl_pipeline_dependencia d "
    "JOIN dbo.etl_malha_pipeline irmao ON irmao.malha_name = mp.malha_name "
    "AND irmao.pipeline_name = d.depende_de "
    "WHERE d.pipeline_name = mp.pipeline_name AND d.tipo = 'PIPELINE') "
    "THEN 1 ELSE 0 END "
    "FROM dbo.etl_malha_pipeline mp "
    "LEFT JOIN dbo.etl_pipeline p ON p.pipeline_name = mp.pipeline_name "
    "WHERE mp.malha_name = ? "
    "AND NOT EXISTS (SELECT 1 FROM dbo.etl_malha_execucao_membro m "
    "WHERE m.malha_execucao_id = ? AND m.pipeline_name = mp.pipeline_name)")


def sql_snapshot(quantos_contam) -> str:
    """O SQL do snapshot para `quantos_contam` pipelines em `conta_para_fim`.

    Público porque o teste de paridade compara o TEXTO das duas árvores, e ele
    varia com o tamanho da lista (não há `IN ()` em T-SQL: lista vazia vira
    `1 = 0`, e `None` — malha sem nó Fim — vira `1 = 1`)."""
    if quantos_contam is None:
        conta = "1 = 1"
    elif quantos_contam == 0:
        conta = "1 = 0"
    else:
        conta = "mp.pipeline_name IN (%s)" % ", ".join("?" for _ in range(quantos_contam))
    return _SQL_SNAPSHOT.format(conta=conta)


def congelar_snapshot(cur, corrida_id, malha: str, conta_para_fim=None):
    """Congela os membros da corrida — o denominador do ciclo. Devolve quantos
    membros gravou, ou None se a 085 não estiver no banco.

    Três fatos, congelados de uma vez, direto de `etl_malha_pipeline`:

      • `conta_para_fim` — o upstream expandido do nó Fim, calculado pelo
        chamador com `malha_nos.expandir()` (a única autoridade da expansão).
        `None` significa "malha SEM nó Fim": todos contam, e o fechamento é por
        quiescência (§6.9/#1). Um conjunto VAZIO é diferente e não é erro: há um
        Fim, e ele não alcança ninguém — o painel lista os `fora_do_fim`
        nominalmente (§6.9/#2), em vez de a corrida fechar com membros vivos;
      • `ativo_na_abertura` — `etl_pipeline.active` AGORA. Membro inativo sai do
        denominador mas NÃO some: o painel diz "N membro(s) inativo(s), fora
        desta corrida" (§6.9/#9);
      • `eh_raiz` — membro sem predecessor DENTRO da malha, por
        `etl_pipeline_dependencia ∩ etl_malha_pipeline`, sem tocar `malha_nos`
        (Decisão 16). É o que restringe a porta implícita: sem isso, um membro do
        meio da cadeia abriria a corrida com `aberta_em` DEPOIS de metade dos
        membros ter concluído, essas linhas virariam "pendentes" e a corrida iria
        a FALHA numa malha que rodou perfeitamente.

    O `LEFT JOIN` em `etl_pipeline` é deliberado: membro apagado do cadastro mas
    ainda em `etl_malha_pipeline` entra como inativo, não derruba o snapshot."""
    lista = None if conta_para_fim is None else sorted(set(conta_para_fim))
    sql = sql_snapshot(None if lista is None else len(lista))
    params = [int(corrida_id)]
    if lista:
        params.extend(lista)
    params.extend([malha, int(corrida_id)])
    try:
        cur.execute(sql, tuple(params))
        return int(cur.rowcount or 0)
    except Exception as e:  # noqa: BLE001 — escrita degrada ESTREITA
        if _sem_085(e):
            log.warning("%s 085 ausente (%s) — snapshot de %s nao congelado",
                        LOG, e, malha)
            return None
        raise


# ═══════════════════════ vínculo da linha de execução ═══════════════════════

SQL_VINCULAR = (
    "UPDATE dbo.etl_pipeline_execucao "
    "SET malha_execucao_id = ?, atualizado_em = GETDATE() "
    "WHERE pipeline_name = ? AND data_referencia = ? AND execution_id = ? "
    "AND malha_execucao_id IS NULL")


def vincular_execucao(cur, pipeline: str, data_ref, execution_id,
                      corrida_id) -> bool:
    """Carimba a PROVENIÊNCIA do ODATE na linha de execução. True = carimbou.

    A coluna é proveniência, não participação (Decisão 1): "de onde veio o ODATE
    desta linha", que tem exatamente uma origem. Quem conta para o fechamento é
    o snapshot (N:N) — e a PROVA de que um membro concluiu é da linha no
    intervalo, nunca da proveniência (Decisão 2), senão o pipeline membro de A e
    de B, com as duas abertas, carimbaria A e ficaria pendente para sempre em B.

    **WRITE-ONCE** (Decisão 9): o `AND malha_execucao_id IS NULL` é o que impede
    reescrever o passado — o `UPDATE` de `_registrar_execucao` roda a cada estado
    e o Clear do rerun REUSA o mesmo `run_id`; sem a guarda, uma linha da corrida
    #12 reexecutada no dia seguinte passaria a pertencer à #13. Na F5, dentro do
    `UPDATE` multi-coluna do caminho quente, a mesma garantia toma a forma
    `malha_execucao_id = COALESCE(malha_execucao_id, %s)`, porque lá o `WHERE` já
    é da linha; aqui a guarda mora no `WHERE` e ainda faz o `rowcount` responder
    a verdade ("carimbei" × "já tinha dono"), que a forma com COALESCE não faz.

    `rowcount = 0` não é erro (Decisão 8): ou a linha já pertence a uma corrida,
    ou ela não existe mais com essa chave."""
    try:
        cur.execute(SQL_VINCULAR,
                    (int(corrida_id), pipeline, data_ref, execution_id))
        return (cur.rowcount or 0) == 1
    except Exception as e:  # noqa: BLE001 — escrita degrada ESTREITA
        if _sem_085(e):
            log.warning("%s 085 ausente (%s) — %s nao vinculado a corrida #%s",
                        LOG, e, pipeline, corrida_id)
            return False
        raise


# ═══════════════════════ fechamento e reabertura ════════════════════════════

# `motivo` ACUMULA (o `CASE` com o mesmo parâmetro duas vezes): o histórico do
# que aconteceu com a corrida é curto e cabe em 500 chars, e sobrescrever
# apagaria justamente o `DATA_DIVERGENTE` da abertura. Um SQL só, e não duas
# variantes, para o teste de paridade comparar UM texto.
SQL_FECHAR = (
    "UPDATE dbo.etl_malha_execucao "
    "SET status = ?, fechada_em = SYSDATETIME(), fechada_por = ?, "
    "motivo = CASE WHEN ? IS NULL THEN motivo "
    "ELSE LEFT(ISNULL(motivo + ' | ', '') + ?, 500) END, "
    "atualizado_em = SYSDATETIME() "
    "WHERE id = ? AND fechada_em IS NULL")


def fechar_corrida(cur, corrida_id, desfecho: str, fechada_por: str,
                   motivo=None) -> bool:
    """Fecha a corrida com um dos sete desfechos. True = ESTA chamada fechou.

    `WHERE id = ? AND fechada_em IS NULL` com `rowcount` de árbitro (Decisão 8):
    duas pontas não fecham a mesma corrida com desfechos diferentes, e
    `rowcount = 0` é "outra ponta chegou primeiro" — não é erro.

    ⚠️ O CHAMADOR grava o evento e fecha no MESMO commit (Decisão 20). A ordem
    antiga — fechar, commitar, e só então o evento — perdia o card PARA SEMPRE se
    a falha caísse entre os dois commits, porque a detecção consome a própria
    fonte: aqui a detecção é `fechada_em IS NULL`, e é ela que o fechamento
    consome. A lição já foi paga e está escrita em etl_dependencia_guardia.py.

    `desfecho` fora do domínio levanta ValueError: seria o `CK_mexec_status`
    estourando dentro da transação do chamador, e **`ABERTA` aqui** seria o
    `CK_mexec_coerente` (status aberto com `fechada_em` preenchida) — os dois são
    bug de programa, não estado do mundo. E nada aqui emite `MALHA_CONCLUIDA`
    (Decisão 24): "não inventar verde" é do chamador, e o teste é de AUSÊNCIA."""
    if desfecho not in DESFECHOS:
        raise ValueError(f"desfecho invalido: {desfecho!r} (esperado {DESFECHOS})")
    try:
        cur.execute(SQL_FECHAR,
                    (desfecho, fechada_por, motivo, motivo, int(corrida_id)))
        return (cur.rowcount or 0) == 1
    except Exception as e:  # noqa: BLE001 — escrita degrada ESTREITA
        if _sem_085(e):
            log.warning("%s 085 ausente (%s) — corrida #%s nao fechada",
                        LOG, e, corrida_id)
            return False
        raise


# A guarda de "não há outra corrida aberta desta malha" mora DENTRO do UPDATE, e
# não num SELECT antes: a reabertura acontece na transação que carimba
# `substituida_em` no rerun com cascata (api/services/rerun.py), e um 2601 do
# `ux_malha_exec_aberta` ali dentro ou rolaria o rerun inteiro de volta, ou
# deixaria a corrida sem reabrir sem ninguém perceber (§6.9/#3). Com a condição
# no WHERE, o pior caso é `rowcount = 0` — que é uma resposta, não um estrago.
SQL_REABRIR = (
    "UPDATE me SET me.status = 'ABERTA', me.fechada_em = NULL, "
    "me.fechada_por = NULL, me.tentativas = me.tentativas + 1, "
    "me.reaberta_em = SYSDATETIME(), me.reaberta_por = ?, "
    "me.motivo = CASE WHEN ? IS NULL THEN me.motivo "
    "ELSE LEFT(ISNULL(me.motivo + ' | ', '') + ?, 500) END, "
    "me.atualizado_em = SYSDATETIME() "
    "FROM dbo.etl_malha_execucao me "
    "WHERE me.id = ? AND me.status IN (" +
    ", ".join("?" for _ in REABREM) + ") "
    "AND NOT EXISTS (SELECT 1 FROM dbo.etl_malha_execucao o "
    "WITH (UPDLOCK, HOLDLOCK) "
    "WHERE o.malha_name = me.malha_name AND o.fechada_em IS NULL)")


def reabrir_corrida(cur, corrida_id, reaberta_por: str, motivo=None) -> bool:
    """Reabre uma corrida CONCLUIDA ou FALHA (rerun com cascata, §6.9/#3).
    True = reabriu; conta `tentativas += 1`.

    False tem duas causas, e o chamador que quiser nomeá-la lê
    `corrida_aberta(malha)`: (i) o desfecho é fim de linha — `SEM_TRABALHO`,
    `EXPIRADA`, `ABORTADA` e `CANCELADA` não voltam; (ii) já existe OUTRA corrida
    aberta da malha, e nesse caso a regra da spec é explícita: **não reabre**, a
    linha preserva o `malha_execucao_id` original (Decisão 9) e grava-se
    `MALHA_REPROCESSO` na corrida antiga."""
    try:
        cur.execute(SQL_REABRIR,
                    (reaberta_por, motivo, motivo, int(corrida_id), *REABREM))
        return (cur.rowcount or 0) == 1
    except Exception as e:  # noqa: BLE001 — escrita degrada ESTREITA
        if _sem_085(e):
            log.warning("%s 085 ausente (%s) — corrida #%s nao reaberta",
                        LOG, e, corrida_id)
            return False
        raise


# ═════════════════ memória de efeito colateral (Decisão 12) ═════════════════

_SQL_VISTO = {
    "falha": ("UPDATE dbo.etl_malha_execucao "
              "SET falha_vista_em = SYSDATETIME(), atualizado_em = SYSDATETIME() "
              "WHERE id = ? AND fechada_em IS NULL AND falha_vista_em IS NULL"),
    "atraso": ("UPDATE dbo.etl_malha_execucao "
               "SET atraso_visto_em = SYSDATETIME(), atualizado_em = SYSDATETIME() "
               "WHERE id = ? AND fechada_em IS NULL AND atraso_visto_em IS NULL"),
}


def marcar_visto(cur, corrida_id, o_que: str) -> bool:
    """Carimba `falha_vista_em`/`atraso_visto_em`. **True = é a primeira vez**,
    e só então o chamador emite o evento.

    Estas duas colunas são as únicas materializações de EFEITO COLATERAL do
    modelo (§5.2): elas não são estado — são a memória que impede o ciclo de 5
    min da guardiã de repetir o mesmo card 200 vezes num dia. `MALHA_FALHOU` sai
    na DETECÇÃO da primeira falha, não no fechamento (Decisão 12): numa malha de
    40 membros, `CARGA_A` falha às 01:12 e os outros 38 seguem até 05:00 — tocar
    o Teams só no fim é tarde por definição.

    O `rowcount` é o árbitro do "primeira vez", em UMA operação: ler-e-decidir
    deixaria a janela entre o SELECT e o UPDATE, que é justo o que dois workers
    da guardiã em paralelo encontrariam."""
    sql = _SQL_VISTO.get(o_que)
    if sql is None:
        raise ValueError(f"marcador invalido: {o_que!r} (esperado 'falha'/'atraso')")
    try:
        cur.execute(sql, (int(corrida_id),))
        return (cur.rowcount or 0) == 1
    except Exception as e:  # noqa: BLE001 — escrita degrada ESTREITA
        if _sem_085(e):
            log.warning("%s 085 ausente (%s) — marcador %s da corrida #%s nao "
                        "gravado", LOG, e, o_que, corrida_id)
            return False
        raise


# ════════════════ F2 — as portas 2 e 3, o estado e os relógios ══════════════
# Tudo daqui para baixo nasceu na F2 (a guardiã) e é o PRIMEIRO consumidor do
# módulo. A regra que governa este bloco é a mesma do de cima: SQL em constante
# nomeada, o chamador é dono da transação e NENHUMA conta de tempo em Python —
# `teto_em < SYSDATETIME()`, `DATEADD(MINUTE, -N, SYSDATETIME())` e o `>=` da
# carência saem todos do banco, porque no dev o SQL Server está ~3h à frente do
# worker e da API (medido), e a mesma diferença existe em qualquer servidor
# com o fuso desalinhado.

# Os estados que significam "esta linha PARTIU" (§6.2, portas 2 e 3).
# `PULADO` está dentro de propósito: é ele que abre a corrida do sábado, e sem a
# corrida não existe o `SEM_TRABALHO` imediato da Decisão 26 — a malha
# `somente_dias_uteis` ficaria o dia inteiro sem ciclo nenhum e o `MALHA_ORFA`
# do domingo voltaria. `AGUARDANDO_DEPENDENCIA` e `NAO_LIBEROU` ficam FORA: a
# primeira é linha ORDENADA (o New Day criou, ninguém partiu) e a segunda é uma
# ordenação que morreu sem nunca ter partido.
STATUS_PARTIU = ("EXECUTANDO", "SUCESSO", "FALHA", "PULADO")

# O tipo do evento que a guardiã emite para a linha órfã (o `EVENTO_ORFA` de
# dags/etl_dependencia_guardia.py). Aparece DENTRO do SQL de `estado()` porque
# a Decisão 22 é uma regra de classificação, não de apresentação; o teste amarra
# as duas grafias para que renomear uma sem a outra não passe.
EVENTO_ORFA = "EXECUCAO_ORFA"

# Prefixos dos motivos carimbados NA LINHA de execução (Decisões 15 e 17). São
# `chave` + texto: a chave é o que o `NOT LIKE` usa para não carimbar duas vezes
# a mesma coisa a cada ciclo de 5 min, e o texto é o que o plantonista lê.
MOTIVO_FORA_DA_CORRIDA = "FORA_DA_CORRIDA"
MOTIVO_OUTRO_ODATE = "CORRIDA_ABERTA_DE_OUTRO_ODATE"

# O evento do crédito de retenção (F7, Decisão 61). Existe porque a barra do
# limite de segurança ANDA PARA TRÁS quando um hold é solto — às 03:00 ela está
# em 80%, alguém solta um hold de 6h e ela cai para 55% sozinha. Uma barra de
# prazo que recua sem explicação destrói a confiança em todas as outras: o
# crédito vira FATO NOMEADO na aba Eventos, com o quanto e o quando.
#
# É gravado com `notificar=False` de propósito: o gesto é humano e síncrono (o
# operador acabou de clicar em Soltar e leu o toast), e um card no Teams seria o
# eco do próprio clique dele às 3h — exatamente o alarme que as Decisões 26/27
# mandam não criar.
EVENTO_TETO_CREDITADO = "MALHA_TETO_CREDITADO"

# Heartbeat da guardiã (§10/F2): "a guardiã DESTE deploy passou por aqui e está
# operando a corrida". É o que a F3 consulta, junto com `capacidade_dags()`,
# antes de deixar a API abrir corrida — a célula mais provável da matriz §11.1 é
# `api/` nova com `dags/` antigo, e nela a API abriria corridas que o motor
# deployado não sabe fechar. Fica em `etl_app_config` (e não em tabela nova)
# porque é configuração operacional de uma chave só, e a 085 está FECHADA:
# editá-la depois de aplicada é no-op silencioso (§11.3).
CHAVE_HEARTBEAT = "malha_corrida_guardia_visto_em"
DESCRICAO_HEARTBEAT = (
    "Carimbo do ultimo ciclo em que a guardia operou a corrida de malha "
    "(gravado pela propria guardia, so com malha_corrida_ativa=1 e a 085 "
    "presente). A API consulta este valor antes de abrir corrida pelo disparo.")

# Como se reconhece "o hold da 082/075 não está neste banco" — mesmo par de
# condições de `_sem_085`, com outras marcas. Existe separado porque a resposta
# é OPOSTA: sem a coluna não há nó retido nenhum (False, e a corrida fecha
# normalmente); com a coluna presente e a consulta falhando por outro motivo, a
# resposta é True — "não consegui perguntar" nunca pode virar "pode fechar".
_MARCAS_HOLD = ("etl_malha_no", "retido_em")


def _sem_hold(e) -> bool:
    texto = str(e)
    if not any(marca in texto for marca in _MARCAS_HOLD):
        return False
    args = getattr(e, "args", ())
    if args and isinstance(args[0], int) and args[0] in _ERROS_AUSENCIA:
        return True
    return any("(%d)" % codigo in texto for codigo in _ERROS_AUSENCIA)


# ── porta 3: quem é raiz DENTRO da malha (Decisão 16) ───────────────────────
# É o MESMO predicado do `eh_raiz` do snapshot (`_SQL_SNAPSHOT`), de propósito:
# a porta implícita e o snapshot têm de concordar sobre quem é raiz, senão a
# corrida nasceria ancorada num membro que ela própria não considera raiz.
# `etl_pipeline_dependencia ∩ etl_malha_pipeline` e nada de `malha_nos`: o
# Aguarde já compilou para linhas normais da 067 (Decisão 16).
SQL_RAIZES_DA_MALHA = (
    "SELECT mp.pipeline_name FROM dbo.etl_malha_pipeline mp "
    "WHERE mp.malha_name = ? "
    "AND NOT EXISTS (SELECT 1 FROM dbo.etl_pipeline_dependencia d "
    "JOIN dbo.etl_malha_pipeline irmao ON irmao.malha_name = mp.malha_name "
    "AND irmao.pipeline_name = d.depende_de "
    "WHERE d.pipeline_name = mp.pipeline_name AND d.tipo = 'PIPELINE') "
    "ORDER BY mp.pipeline_name")


def raizes_da_malha(cur, malha: str) -> list:
    """Membros SEM predecessor dentro da malha — as raízes da porta 3.

    Malha inteira sem dependência interna (o caso de `SMOKE_F11_E5` no dev) faz
    TODOS os membros serem raiz, e isso é a resposta certa: sem aresta não há
    ordem, e qualquer um que parta abre o ciclo."""
    try:
        cur.execute(SQL_RAIZES_DA_MALHA, (malha,))
        return [r[0] for r in cur.fetchall()]
    except Exception as e:  # noqa: BLE001 — leitura degrada larga
        log.warning("%s raizes de %s indisponiveis (%s) — porta implicita "
                    "pulada neste ciclo", LOG, malha, e)
        return []


# ── portas 2 e 3: as linhas que partiram e a corrida ainda não cobriu ───────
# O `NOT EXISTS` é o que impede a guardiã de reabrir a mesma corrida a cada 5
# minutos, e ele tem DUAS pernas de propósito:
#
#   • `e.malha_execucao_id = me.id` (sem olhar `fechada_em`) — a linha JÁ foi
#     carimbada por uma corrida desta malha. É a perna que fecha o laço do
#     sábado: o `PULADO` das 06:00 abre a corrida, ela fecha `SEM_TRABALHO` no
#     mesmo ciclo, e sem esta perna o ciclo das 06:05 abriria a corrida #2, o
#     das 06:10 a #3, e o dia inteiro sairia com 288 corridas;
#   • a linha caiu DENTRO do intervalo `[aberta_em, fechada_em]` de uma corrida
#     FECHADA desta malha — a perna do membro compartilhado. `DEV_F10_A` é
#     membro de quatro malhas no dev: ele carimba a corrida de UMA (a coluna é
#     proveniência, tem um dono só — Decisão 1) e as outras três precisam de
#     outro critério para saber que já viram aquela linha.
#
# A corrida ABERTA de propósito NÃO exclui: enquanto ela está aberta, cada raiz
# que parte tem de passar pela conferência de ODATE da Decisão 15. Excluir aqui
# seria exatamente a "adesão silenciosa" que reintroduz o `Carga_Vida` por
# dentro do mecanismo criado para matá-lo. O preço é um INSERT que falha com
# 2601 por ciclo enquanto a corrida está aberta — barato, e é o padrão claim da
# Decisão 14.
#
# ⚠️ A perna do INTERVALO — e só ela — exige `e.data_referencia =
# me.data_referencia`. A cláusula e o lugar dela foram MEDIDOS no dev:
#
#   • na perna do intervalo ela é obrigatória. Sem ela, a corrida de D-1 que
#     atravessou a virada "cobre" toda a madrugada de D só por causa do
#     `[aberta_em, fechada_em]`. Efeito medido: guardiã parada das 23:00 às
#     02:00, a corrida de D-1 abre e fecha às 02:00, e a raiz que partiu às
#     01:00 do dia D fica coberta PARA SEMPRE — o ciclo de D nunca abre e o dia
#     sai mudo, que é o defeito (a) desta spec produzido pela própria cura;
#   • na perna da PROVENIÊNCIA ela não pode entrar, e isso também foi medido:
#     quando a linha âncora carimbou um ODATE diferente do canônico (o
#     `Carga_Vida` literal), a corrida nasce com o canônico e a linha entra como
#     `fora_do_odate` (§6.2) — datas diferentes por construção. Exigir o ODATE
#     aqui faria a linha nunca contar como coberta, e a guardiã abriria uma
#     corrida nova a cada 5 min, cada uma fechando `ABORTADA` com dois cards no
#     Teams: 288 corridas e 576 cards por dia. Proveniência é dona, não data.
_SQL_PARTIDAS = (
    "SELECT e.pipeline_name, e.data_referencia, e.execution_id, "
    "COALESCE(e.inicio, e.criado_em), e.status "
    "FROM dbo.etl_pipeline_execucao e "
    "WHERE {lista} "
    "AND e.data_referencia IN (?, ?) "
    "AND e.status IN (" + ", ".join("?" for _ in STATUS_PARTIU) + ") "
    "AND e.substituida_em IS NULL "
    "AND COALESCE(e.inicio, e.criado_em) >= DATEADD(HOUR, -?, SYSDATETIME()) "
    "AND NOT EXISTS (SELECT 1 FROM dbo.etl_malha_execucao me "
    "WHERE me.malha_name = ? "
    "AND (e.malha_execucao_id = me.id "
    "OR (me.fechada_em IS NOT NULL "
    "AND e.data_referencia = me.data_referencia "
    "AND COALESCE(e.inicio, e.criado_em) >= me.aberta_em "
    "AND COALESCE(e.inicio, e.criado_em) <= me.fechada_em))) "
    "ORDER BY COALESCE(e.inicio, e.criado_em), e.pipeline_name, e.execution_id")


def sql_partidas(quantos: int) -> str:
    """O SQL das partidas para `quantos` pipelines na lista.

    Público pela mesma razão de `sql_snapshot`: não há `IN ()` em T-SQL, então
    o texto muda com o tamanho da lista e o teste de paridade precisa comparar
    as duas formas. Lista vazia vira `1 = 0` — nunca `IN ()`, que é erro de
    sintaxe, e nunca a ausência da cláusula, que varreria a tabela inteira."""
    if quantos <= 0:
        return _SQL_PARTIDAS.format(lista="1 = 0")
    marcadores = ", ".join("?" for _ in range(quantos))
    return _SQL_PARTIDAS.format(lista="e.pipeline_name IN (" + marcadores + ")")


def partidas_a_cobrir(cur, malha: str, pipelines, datas, teto_horas: int) -> list:
    """As linhas de `pipelines` que PARTIRAM e que nenhuma corrida desta malha
    cobriu ainda — o insumo das portas 2 e 3.

    `datas` é a janela `{D-1, D}` do PRESENTE, derivada da virada da malha (o
    mesmo recorte dos observadores, D45): sem ela, o reprocesso do dia 03 feito
    hoje abriria uma corrida do dia 03 no meio da corrida de hoje. `teto_horas`
    é o segundo limite, e o mais importante: uma corrida cujo `aberta_em` recua
    para além do próprio teto nasceria EXPIRADA no ato — a guardiã que voltou
    depois de um dia fora não pode ressuscitar a madrugada de ontem.

    Devolve `[{pipeline, data_referencia, execution_id, momento, status}]`
    ordenado por `momento` — a PRIMEIRA é a âncora (§6.2: `aberta_em` recua para
    o início da linha âncora, e recuar para a mais antiga é o que impede a
    corrida de "perder" o trabalho que a originou)."""
    nomes = sorted({str(p).strip() for p in pipelines if str(p or "").strip()})
    if not nomes:
        return []
    janela = list(datas)[:2]
    while len(janela) < 2:            # a forma do SQL é fixa em duas datas
        janela.append(janela[0])
    try:
        cur.execute(sql_partidas(len(nomes)),
                    tuple(nomes) + tuple(janela) + STATUS_PARTIU
                    + (int(teto_horas), malha))
        return [{"pipeline": r[0], "data_referencia": r[1],
                 "execution_id": r[2], "momento": r[3], "status": r[4]}
                for r in cur.fetchall()]
    except Exception as e:  # noqa: BLE001 — leitura degrada larga
        log.warning("%s partidas de %s indisponiveis (%s) — nenhuma "
                    "abertura neste ciclo", LOG, malha, e)
        return []


# ── o predicado 'estado' (§6.4, Decisões 21/22/23) ──────────────────────────
# UM predicado, dois consumidores (o padrão de `liberado()`): o fechador carimba
# o desfecho e o painel da F4 lê o mesmo dicionário. Nenhum dos dois deriva do
# outro.
#
# O escopo da linha é o SQL da Decisão 23, literal: `data_referencia = @odate`
# **nos dois ramos**, e a linha entra por PROVENIÊNCIA (`malha_execucao_id`) OU
# por RECORTE DE TEMPO (`>= aberta_em`). O ramo do recorte é o que faz o
# fechamento funcionar ANTES de a F5 carimbar as linhas; o ramo da proveniência
# é o que continua funcionando quando a próxima corrida do mesmo dia já abriu.
# Exigir o ODATE no ramo do vínculo é o que impede o reprocesso do dia 03, feito
# às 3h da manhã do dia 04, de contar como OK para a corrida do dia 04.
SQL_ESTADO = (
    "SELECT m.pipeline_name, m.conta_para_fim, m.ativo_na_abertura, m.eh_raiz, "
    "e.status, COALESCE(e.inicio, e.criado_em), "
    "CASE WHEN e.status = 'EXECUTANDO' AND EXISTS "
    "(SELECT 1 FROM dbo.etl_dependencia_evento ev "
    "WHERE ev.pipeline_name = e.pipeline_name "
    "AND ev.data_referencia = e.data_referencia "
    "AND ev.tipo = '" + EVENTO_ORFA + "') THEN 1 ELSE 0 END "
    "FROM dbo.etl_malha_execucao_membro m "
    "LEFT JOIN dbo.etl_pipeline_execucao e "
    "ON e.pipeline_name = m.pipeline_name "
    "AND e.data_referencia = ? "
    "AND e.substituida_em IS NULL "
    "AND (e.malha_execucao_id = ? "
    "OR COALESCE(e.inicio, e.criado_em) >= ?) "
    "WHERE m.malha_execucao_id = ? "
    "ORDER BY m.pipeline_name, e.id")

# §6.9/#15 e Decisão 23: a linha que a corrida carimbou mas cujo ODATE é outro.
# Nunca conta como OK, e o painel a mostra NOMINALMENTE — divergência visível é
# o oposto de divergência silenciosa.
SQL_FORA_DO_ODATE = (
    "SELECT DISTINCT e.pipeline_name, e.data_referencia "
    "FROM dbo.etl_pipeline_execucao e "
    "WHERE e.malha_execucao_id = ? AND e.data_referencia <> ? "
    "AND e.substituida_em IS NULL "
    "ORDER BY e.pipeline_name, e.data_referencia")

# Prioridade da classificação quando um membro tem MAIS DE UMA linha viva no
# escopo (o caso é real: `PULADO` do cron às 06:00 + disparo manual às 09:00, ou
# `FALHA` + rerun bem-sucedido). Lê-se de cima para baixo, o primeiro que
# aparecer vence:
#   • `vivo` na frente de tudo — nunca fechar com trabalho em voo (§16/5);
#   • `ok` na frente de `falhou` — é o MESMO julgamento de `liberado()` e de
#     `_divergencias_e_falhas` ("FALHA sem SUCESSO na data"): o rerun que deu
#     certo apaga a falha anterior, senão a corrida iria a FALHA por causa da
#     tentativa que o operador já consertou;
#   • `dispensado` (PULADO) atrás dos pendentes: pulado numa linha e falhado em
#     outra é um problema, não uma dispensa.
_ORDEM_CLASSE = ("vivo", "ok", "falhou", "orfa", "nao_liberou", "dispensado",
                 "nao_partiu")
CLASSES_PENDENTES = ("falhou", "orfa", "nao_liberou", "nao_partiu")


def _classe_da_linha(status, orfa) -> str:
    """Status da linha → classe do §6.4. Status desconhecido vira `nao_partiu`
    (pendente) e NUNCA `vivo`: um status que o código não entende classificado
    como vivo congelaria a corrida até o teto — e o teto, por não poder matar
    vivo (Decisão 25), só alarmaria. A corrida ficaria aberta para sempre,
    bloqueando o disparo, que é o pior desfecho possível."""
    s = str(status or "").strip().upper()
    if s == "EXECUTANDO":
        # Decisão 22: órfã JÁ ALERTADA sai de "vivo". O caso órfão mais comum do
        # sistema (DagRun success, linha EXECUTANDO) viraria N horas de malha
        # bloqueada em vez de um alerta; a corrida fecha FALHA nomeando a linha,
        # que é a verdade, em vez de esperar 24h para dizer EXPIRADA.
        return "orfa" if orfa else "vivo"
    if s == "AGUARDANDO_DEPENDENCIA":
        return "vivo"
    if s == "SUCESSO":
        return "ok"
    if s == "FALHA":
        return "falhou"
    if s == "NAO_LIBEROU":
        return "nao_liberou"
    if s == "PULADO":
        return "dispensado"
    return "nao_partiu"


def estado(cur, corrida: dict, dispensa_sem_linha=None) -> dict:
    """A classificação de cada membro do snapshot (§6.4) — o predicado que o
    fechador da F2 e o painel da F4 leem.

    Devolve
    `{vivos[], ok[], pendentes[{pipeline, classe, desde, faltante}],
      dispensados[], fora_do_fim[], fora_do_odate[{pipeline, data}],
      inativos[], conta_para_fim[], linhas, membros}`.

    `dispensa_sem_linha(pipeline) -> bool` é injetado pelo CHAMADOR e responde
    "membro sem linha nenhuma: o dia dele permitia rodar?". O julgamento mora
    fora daqui de propósito — ele é `dia_permitido(regras_dia, dia_operacional)`,
    exatamente o de `_predecessor_esperado` da guardiã (§6.4 manda REUSAR, não
    duplicar), e trazê-lo para cá obrigaria este módulo a reimplementar as regras
    de agenda. Sem o callback todo membro sem linha é `nao_partiu`, que é a
    resposta conservadora: a corrida vai a FALHA nomeando quem não rodou, em vez
    de dispensar em silêncio.

    Membro `ativo_na_abertura = 0` sai de TODOS os baldes e vai para `inativos`
    (§6.9/#9): fora do denominador, mas nunca sumindo em silêncio."""
    odate, corrida_id = corrida["data_referencia"], int(corrida["id"])
    vazio = {"vivos": [], "ok": [], "pendentes": [], "dispensados": [],
             "fora_do_fim": [], "fora_do_odate": [], "inativos": [],
             "conta_para_fim": [], "linhas": 0, "membros": 0}
    try:
        cur.execute(SQL_ESTADO,
                    (odate, corrida_id, corrida["aberta_em"], corrida_id))
        linhas = cur.fetchall()
    except Exception as e:  # noqa: BLE001 — leitura degrada larga
        log.warning("%s estado da corrida #%s indisponivel (%s) — nada a "
                    "fechar neste ciclo", LOG, corrida_id, e)
        return vazio

    membros: dict = {}
    total_linhas = 0
    for pipeline, conta_fim, ativo, _raiz, status, desde, orfa in linhas:
        m = membros.setdefault(pipeline, {
            "conta_para_fim": bool(conta_fim), "ativo": bool(ativo),
            "classe": None, "desde": None})
        if status is None:
            continue                    # membro sem linha no escopo
        total_linhas += 1
        classe = _classe_da_linha(status, bool(orfa))
        atual = m["classe"]
        if atual is None or _ORDEM_CLASSE.index(classe) < _ORDEM_CLASSE.index(atual):
            m["classe"], m["desde"] = classe, desde

    saida = dict(vazio)
    saida["linhas"] = total_linhas
    saida["membros"] = len(membros)
    for pipeline in sorted(membros):
        m = membros[pipeline]
        if not m["ativo"]:
            saida["inativos"].append(pipeline)
            continue
        if m["conta_para_fim"]:
            saida["conta_para_fim"].append(pipeline)
        else:
            saida["fora_do_fim"].append(pipeline)
        classe = m["classe"]
        if classe is None:
            # Sem linha: quem decide é a regra de DIA do próprio membro.
            classe = "dispensado" if (
                dispensa_sem_linha is not None
                and dispensa_sem_linha(pipeline)) else "nao_partiu"
        if classe == "vivo":
            saida["vivos"].append(pipeline)
        elif classe == "ok":
            saida["ok"].append(pipeline)
        elif classe == "dispensado":
            saida["dispensados"].append(pipeline)
        else:
            # Decisão 21: o pendente carrega a CLASSE, não só o nome — é o que
            # separa "rode o job de novo" de "solte a dependência" de "descubra
            # por que a DAG nunca partiu". `faltante` é preenchido pelo painel
            # da F4, que tem o `liberado()` em mãos.
            saida["pendentes"].append({"pipeline": pipeline, "classe": classe,
                                       "desde": m["desde"], "faltante": None})
    try:
        cur.execute(SQL_FORA_DO_ODATE, (corrida_id, odate))
        saida["fora_do_odate"] = [{"pipeline": r[0], "data": r[1]}
                                  for r in cur.fetchall()]
    except Exception as e:  # noqa: BLE001 — leitura degrada larga
        log.warning("%s linhas fora do ODATE da corrida #%s indisponiveis "
                    "(%s)", LOG, corrida_id, e)
    return saida


# Sentinela de "não consegui perguntar" (o `ERRO_CONSULTA` de
# utils/dependencias.py, na forma deste módulo): nunca é nome de pipeline, então
# não colide, e força o chamador a decidir explicitamente.
ERRO_LEITURA = "#erro-de-leitura"


# ── guarda 1 da quiescência (§6.5) ──────────────────────────────────────────
# Deliberadamente SEM o recorte de tempo do `estado()`: a linha que a guarda
# procura é justamente a que ficou de FORA dele — ordenada pelo New Day às 00:05,
# com a corrida aberta às 01:10. Ela não é "vivo" pelo §6.4 e mesmo assim a
# `_rede_seguranca` vai dispará-la neste ciclo ou no próximo. Fechar a corrida
# aqui seria fechá-la no meio de si mesma.
SQL_AGUARDANDO_DO_SNAPSHOT = (
    "SELECT DISTINCT e.pipeline_name "
    "FROM dbo.etl_pipeline_execucao e "
    "JOIN dbo.etl_malha_execucao_membro m "
    "ON m.malha_execucao_id = ? AND m.pipeline_name = e.pipeline_name "
    "WHERE e.data_referencia = ? AND e.status = 'AGUARDANDO_DEPENDENCIA' "
    "AND e.substituida_em IS NULL "
    "ORDER BY e.pipeline_name")


def aguardando_do_snapshot(cur, corrida: dict) -> list:
    """Membros do snapshot com linha `AGUARDANDO_DEPENDENCIA` no ODATE da
    corrida — o chamador pergunta `liberado()` a cada um (a MESMA função do
    push) e, se algum estiver liberado, NÃO fecha."""
    try:
        cur.execute(SQL_AGUARDANDO_DO_SNAPSHOT,
                    (int(corrida["id"]), corrida["data_referencia"]))
        return [r[0] for r in cur.fetchall()]
    except Exception as e:  # noqa: BLE001 — leitura degrada larga
        log.warning("%s aguardando da corrida #%s indisponivel (%s) — "
                    "fechamento adiado", LOG, corrida["id"], e)
        # [] diria "não há ninguém aguardando" e liberaria o fechamento com base
        # numa pergunta que não foi respondida. O chamador trata a marca abaixo
        # como "não fecho neste ciclo" — a mesma política do ERRO_CONSULTA.
        return [ERRO_LEITURA]


# ── os relógios, todos no banco (Decisão 10) ────────────────────────────────
# UMA consulta para os três: teto vencido, carência de partida vencida e
# quiescência. Fossem três, seriam três idas ao banco por corrida por ciclo, e a
# terceira poderia ler um instante diferente da primeira.
#
# A âncora da quiescência é `GREATEST(aberta_em, MAX(COALESCE(fim, inicio,
# criado_em)))`, escrita como "as DUAS pontas abaixo do corte" porque `GREATEST`
# só existe no SQL Server 2022 e a Caixa não declarou a edição. E é
# `COALESCE(fim, inicio, criado_em)` — **nunca `atualizado_em`**: `malha_ciclo.
# equalizar` e `rerun.marcar_substituidas` bumpam `atualizado_em` por gesto
# ADMINISTRATIVO, e a corrida ficaria com o relógio de quiescência reiniciado
# sem que nada tivesse rodado.
SQL_RELOGIOS = (
    "SELECT "
    "CASE WHEN me.teto_em IS NOT NULL AND me.teto_em < SYSDATETIME() "
    "THEN 1 ELSE 0 END, "
    "CASE WHEN me.aberta_em < DATEADD(MINUTE, -?, SYSDATETIME()) "
    "THEN 1 ELSE 0 END, "
    "CASE WHEN me.aberta_em < DATEADD(MINUTE, -?, SYSDATETIME()) "
    "AND COALESCE((SELECT MAX(COALESCE(e.fim, e.inicio, e.criado_em)) "
    "FROM dbo.etl_pipeline_execucao e "
    "JOIN dbo.etl_malha_execucao_membro mm "
    "ON mm.malha_execucao_id = me.id AND mm.pipeline_name = e.pipeline_name "
    "WHERE e.data_referencia = me.data_referencia "
    "AND e.substituida_em IS NULL "
    "AND (e.malha_execucao_id = me.id "
    "OR COALESCE(e.inicio, e.criado_em) >= me.aberta_em)), me.aberta_em) "
    "< DATEADD(MINUTE, -?, SYSDATETIME()) THEN 1 ELSE 0 END "
    "FROM dbo.etl_malha_execucao me WHERE me.id = ?")


def relogios(cur, corrida: dict, carencia_min: int, quiescencia_min: int) -> dict:
    """`{teto_vencido, partida_vencida, quiescente}` — os três relógios da
    corrida, respondidos pelo BANCO numa consulta só.

    Falha de leitura devolve os três em `False`: nenhum desfecho por relógio
    acontece no ciclo em que a pergunta não pôde ser feita. É a política do
    `ERRO_CONSULTA` — "não consegui perguntar" nunca vira "o teto estourou"."""
    try:
        cur.execute(SQL_RELOGIOS, (int(carencia_min), int(quiescencia_min),
                                   int(quiescencia_min), int(corrida["id"])))
        row = cur.fetchone()
    except Exception as e:  # noqa: BLE001 — leitura degrada larga
        log.warning("%s relogios da corrida #%s indisponiveis (%s) — nenhum "
                    "desfecho por tempo neste ciclo", LOG, corrida["id"], e)
        row = None
    if not row:
        return {"teto_vencido": False, "partida_vencida": False,
                "quiescente": False}
    return {"teto_vencido": bool(row[0]), "partida_vencida": bool(row[1]),
            "quiescente": bool(row[2])}


# ── guarda 3 da quiescência: o HOLD (§6.7, Decisões 30 e 31) ────────────────
# O hold é DERIVADO de `MIN(etl_malha_no.retido_em)` a cada avaliação, e nunca
# materializado numa coluna da corrida. O teste que separa as duas formas é o
# aceite da F7: com DOIS Aguardes segurados, soltar UM não pode destravar os
# relógios. Um espelho ("esta corrida está retida") seria limpo pelo primeiro
# `soltar` e o teto voltaria a correr com a malha ainda travada — a corrida
# expirando por causa da trava que o próprio operador pôs.
#
# `MIN` (e não `MAX`): o hold começou no PRIMEIRO nó segurado. A janela do
# crédito é [MIN(retido_em), agora], e é o banco quem a mede — `DATEDIFF` aqui,
# nunca subtração em Python (o SQL Server do dev está 3h à frente da API).
#
# ⚠️ O **Início fica de fora** (§6.7, literal: *"Hold do Início não para corrida
# aberta — está certo: ele segura a partida"*). Quem trava o ciclo EM VOO é o
# Aguarde: segurado, ele faz `liberado()` devolver False para o dependente
# (`dependencias._SQL_*`, correlação por `n.id = dd.origem_no`), e é ESSA a
# razão de o teto ter de parar. O Início não segura ninguém que já partiu — ele
# impede a PRÓXIMA corrida de nascer, e quem lê isso é `malha_ciclo.
# inicio_retido`, que filtra `tipo = 'inicio'` de propósito.
#
# Sem este recorte, segurar o Início às 22h para a malha não partir de
# madrugada PARARIA o teto da corrida já aberta: ela nunca fecharia (nem por
# quiescência, nem por teto), o disparo ficaria bloqueado enquanto o cadeado
# estivesse lá, e soltar dias depois creditaria os mesmos dias ao teto. É
# exatamente o *"congelaria a malha para sempre, sem tela para destravar"* que
# a §6.6 dá como justificativa do teto — e o próprio endpoint promete o
# contrário ao operador ("a corrida em andamento SEGUE").
TIPO_NO_DA_PARTIDA = "inicio"
_SO_NO_QUE_TRAVA = "AND {a}.tipo <> '" + TIPO_NO_DA_PARTIDA + "' "
SQL_HOLD_DA_MALHA = (
    "SELECT COUNT(*), MIN(n.retido_em), "
    "DATEDIFF(MINUTE, MIN(n.retido_em), SYSDATETIME()), "
    "(SELECT TOP 1 n2.retido_por FROM dbo.etl_malha_no n2 "
    "WHERE n2.malha_name = ? AND n2.retido_em IS NOT NULL "
    + _SO_NO_QUE_TRAVA.format(a="n2") +
    "ORDER BY n2.retido_em, n2.id) "
    "FROM dbo.etl_malha_no n "
    "WHERE n.malha_name = ? AND n.retido_em IS NOT NULL "
    + _SO_NO_QUE_TRAVA.format(a="n").rstrip())


def hold_da_malha(cur, malha: str) -> dict:
    """O HOLD desta malha AGORA: `{retido, nos, desde, minutos, por}`.

    `desde` é `MIN(retido_em)` — o instante em que o hold começou — e `minutos`
    é o `DATEDIFF` que o BANCO calculou até `SYSDATETIME()`. Nenhum dos dois
    passa por conta em Python: `desde` vem do relógio do banco e comparar com o
    relógio do container da API (3h atrás no dev, medido) daria "segurado há
    -3h".

    Retido = o teto não corre, a quiescência não avalia, o aborto por carência
    não acontece (Decisão 30) e `_fechar_dia_anterior` pula os membros
    (Decisão 31). Sem isso, um Aguarde que o próprio operador segurou faz
    `liberado()` devolver False para o dependente — que é literalmente "nenhum
    vivo, nenhum liberado" — e a corrida fecharia como **FALHA por causa da
    trava que o operador pôs**.

    Sem a 075/082 (`etl_malha_no`/`retido_em` ausentes) → **não retido**: não há
    nó, logo não há retenção. Qualquer OUTRO erro → **retido**, com `desde=None`:
    "não consegui perguntar" nunca pode virar "pode fechar" (a lição do
    `ERRO_CONSULTA`, literal). Adiar um fechamento custa um ciclo de 5 min;
    fechar uma corrida como FALHA por causa de um timeout custa o card
    mentiroso que esta spec existe para matar. `desde=None` com `retido=True` é
    deliberado: quem escreve na tela não pode inventar um instante que a
    consulta não devolveu."""
    vazio = {"retido": False, "nos": 0, "desde": None, "minutos": 0, "por": None}
    try:
        cur.execute(SQL_HOLD_DA_MALHA, (malha, malha))
        row = cur.fetchone()
    except Exception as e:  # noqa: BLE001
        if _sem_hold(e):
            return vazio
        log.warning("%s retencao de %s indisponivel (%s) — assumindo "
                    "RETIDA; nada fecha neste ciclo", LOG, malha, e)
        return {**vazio, "retido": True}
    if not row or not int(row[0] or 0):
        return vazio
    return {"retido": True, "nos": int(row[0] or 0),
            "desde": row[1] if len(row) > 1 else None,
            "minutos": int(row[2] or 0) if len(row) > 2 and row[2] is not None else 0,
            "por": row[3] if len(row) > 3 else None}


def ha_no_retido(cur, malha: str) -> bool:
    """Existe nó da malha SEGURADO agora — **fora o Início**? A pergunta de
    SIM/NÃO sobre o mesmo `hold_da_malha`: uma consulta só, uma derivação só.

    O Início não entra (§6.7): ele segura a PARTIDA, e a corrida em andamento
    segue. Ver o comentário de `SQL_HOLD_DA_MALHA`."""
    return hold_da_malha(cur, malha)["retido"]


# ── o crédito do teto ao soltar o ÚLTIMO nó (§6.7, Decisão 30) ──────────────
# Soltar depois de 6h de hold numa malha com teto de 4h empurra o teto em 6h, e
# a corrida NÃO expirou. Três coisas fazem isso ser verdade, e as três estão
# neste UPDATE — num statement só, porque medir o hold e apagá-lo em dois
# statements abre a janela em que o crédito se perde:
#
#   • `h.cred` é `DATEDIFF(MINUTE, MIN(retido_em), SYSDATETIME())` — o banco
#     mede, e mede ANTES de o `retido_em` ser limpo (quem chama limpa DEPOIS);
#   • `NOT EXISTS (... n2.id <> ?)` é o "ÚLTIMO nó": com outro Aguarde ainda
#     segurado, nada é creditado e os relógios seguem parados — o hold continua
#     correndo e o crédito virá inteiro quando o último for solto;
#   • `teto_em = DATEADD(MINUTE, h.cred, teto_em)` reprojeta o teto. É
#     equivalente a `aberta_em + teto_horas + creditado`, porque `teto_em` só se
#     move por crédito — e incremental não precisa reler `teto_horas`, que pode
#     ter sido editado no cadastro no meio do voo (o snapshot do ciclo é o que
#     valia na abertura).
#
# ⚠️ SUBESTIMA de propósito quando houve DOIS holds encavalados: A segurado às
# 01:00 e solto às 02:00, B segurado às 01:30 e solto às 03:00 credita 90 min
# (de B), não 120. `MIN` é sobre quem AINDA está retido, e não há histórico de
# retenção no modelo. Errar para MENOS é a direção segura: crédito a mais
# adiaria o único mecanismo anti-travamento que a malha tem.
#
# `atraso_visto_em = NULL`: o `MALHA_ATRASADA` já emitido falava de um teto que
# acabou de mudar de lugar. Sem zerar, um atraso NOVO — depois do crédito —
# ficaria mudo para sempre, porque a memória de efeito colateral é por corrida.
#
# O Início fica fora das DUAS pontas (ver `SQL_HOLD_DA_MALHA`): fora do `MIN`
# que mede — soltar o Início não pode creditar nada, porque ele nunca parou o
# ciclo — e fora do `NOT EXISTS` do "último nó" — um Início segurado não pode
# impedir o crédito do último Aguarde solto.
SQL_CREDITAR_HOLD = (
    "UPDATE me SET teto_creditado_min = me.teto_creditado_min + h.cred, "
    "teto_em = DATEADD(MINUTE, h.cred, me.teto_em), "
    "atraso_visto_em = NULL, atualizado_em = SYSDATETIME() "
    "OUTPUT inserted.id, "
    "inserted.teto_creditado_min - deleted.teto_creditado_min, "
    "inserted.teto_em, inserted.teto_creditado_min, inserted.data_referencia "
    "FROM dbo.etl_malha_execucao me "
    "CROSS APPLY (SELECT DATEDIFF(MINUTE, MIN(n.retido_em), SYSDATETIME()) AS cred "
    "FROM dbo.etl_malha_no n "
    "WHERE n.malha_name = me.malha_name AND n.retido_em IS NOT NULL "
    + _SO_NO_QUE_TRAVA.format(a="n") + ") h "
    "WHERE me.malha_name = ? AND me.fechada_em IS NULL "
    "AND me.teto_em IS NOT NULL AND h.cred > 0 "
    "AND NOT EXISTS (SELECT 1 FROM dbo.etl_malha_no n2 "
    "WHERE n2.malha_name = me.malha_name AND n2.retido_em IS NOT NULL "
    + _SO_NO_QUE_TRAVA.format(a="n2") +
    "AND n2.id <> ?)")


def creditar_hold(cur, malha: str, no_id) -> dict:
    """Credita ao teto da corrida ABERTA o tempo que a malha passou segurada —
    e só quando `no_id` é o ÚLTIMO nó retido. `None` quando não há o que
    creditar. **Não commita**: o crédito e a limpeza do `retido_em` são o mesmo
    gesto e têm de cair no mesmo commit.

    Chamado ANTES do `UPDATE ... SET retido_em = NULL`, porque é o próprio
    `retido_em` que mede o crédito.

    Devolve `{corrida_id, minutos, teto_em, total_min, data_referencia}`.
    Hold de menos de um minuto não credita (`h.cred > 0`) — e não gera evento,
    que é o certo: "+0h creditados" seria ruído com a forma de fato.

    Degrada em silêncio para `None`: sem a 085 (banco a meio deploy), sem a 082
    ou com a leitura indisponível, **soltar o nó continua funcionando**. Perder
    o crédito adia o teto para o valor original; falhar o `soltar` deixaria a
    malha travada, que é o oposto do gesto."""
    try:
        cur.execute(SQL_CREDITAR_HOLD, (malha, int(no_id)))
        row = cur.fetchone()
    except Exception as e:  # noqa: BLE001 — o gesto do operador nunca cai por isto
        log.warning("%s credito de retencao da malha %s nao aplicado (%s) — o "
                    "teto segue com o valor original", LOG, malha, e)
        return None
    if not row:
        return None
    return {"corrida_id": int(row[0]), "minutos": int(row[1] or 0),
            "teto_em": row[2], "total_min": int(row[3] or 0),
            "data_referencia": row[4] if len(row) > 4 else None}


# ── Decisão 31: a corrida ABERTA que cobre uma linha AGUARDANDO ─────────────
# `_fechar_dia_anterior` corta por `criado_em < virada_anterior` — régua
# derivada da VIRADA. Uma malha com teto de 48h, ou uma corrida que atravessa a
# virada seguinte (cadeia noturna longa + rerun), teria seus
# `AGUARDANDO_DEPENDENCIA` fechados como `NAO_LIBEROU` **enquanto a corrida
# ainda é válida** — e esses membros virariam pendentes, levando a corrida a
# FALHA por ação da própria guardiã. A corrida passa a ser a autoridade sobre
# "este ciclo ainda não acabou".
#
# Duas portas no mesmo `EXISTS`, e a segunda não é zelo: a linha do dependente
# NASCE no claim do pai (`reservar_corrida`), sem `malha_execucao_id`, e só o
# `_registrar_execucao` do filho a carimba. Fechar por "a linha não aponta para
# corrida nenhuma" mataria exatamente as linhas que ainda não partiram — que
# são as que a corrida está esperando.
SQL_CORRIDA_ABERTA_DA_LINHA = (
    "SELECT TOP 1 me.id, me.malha_name, me.data_referencia "
    "FROM dbo.etl_malha_execucao me "
    "WHERE me.fechada_em IS NULL AND ("
    "EXISTS (SELECT 1 FROM dbo.etl_pipeline_execucao e "
    "WHERE e.pipeline_name = ? AND e.data_referencia = ? "
    "AND e.malha_execucao_id = me.id) "
    "OR (me.data_referencia = ? AND EXISTS ("
    "SELECT 1 FROM dbo.etl_malha_execucao_membro mm "
    "WHERE mm.malha_execucao_id = me.id AND mm.pipeline_name = ?))) "
    "ORDER BY me.id")


def corrida_aberta_da_linha(cur, pipeline: str, data_ref):
    """A corrida ABERTA que cobre a linha `(pipeline, data_ref)`, ou `None`.

    `{"id": None}` é o veredito de LEITURA INDISPONÍVEL: quem chama trata como
    "há corrida" e adia o fechamento por um ciclo. É a política do
    `ERRO_CONSULTA` — "não consegui perguntar" nunca vira "pode fechar
    NAO_LIBEROU". Sem a 085, `None`: o comportamento é o de antes desta spec,
    byte a byte."""
    try:
        cur.execute(SQL_CORRIDA_ABERTA_DA_LINHA,
                    (pipeline, data_ref, data_ref, pipeline))
        row = cur.fetchone()
    except Exception as e:  # noqa: BLE001
        if _sem_085(e):
            return None
        log.warning("%s corrida aberta de %s em %s indisponivel (%s) — "
                    "fechamento adiado", LOG, pipeline, data_ref, e)
        return {"id": None, "malha_name": None, "data_referencia": None}
    if not row:
        return None
    return {"id": int(row[0]), "malha_name": row[1],
            "data_referencia": row[2] if len(row) > 2 else None}


# ── o carimbo NA LINHA (Decisões 15 e 17) ──────────────────────────────────
# O diagnóstico tem de viajar com a EXECUÇÃO: de plantão se chega pelo pipeline,
# não pela malha. É exatamente o alarme que faltou no incidente `Carga_Vida` —
# lá a linha rodou com a data errada e não havia, na própria linha, nada que
# dissesse por quê.
#
# O `NOT LIKE` é a idempotência: a guardiã passa a cada 5 min e o carimbo é o
# mesmo. ⚠️ `_registrar_execucao` do fonte gerado SOBRESCREVE `motivo` a cada
# transição de status, então um carimbo posto em `EXECUTANDO` some quando a
# linha vira `SUCESSO` — e o ciclo seguinte o repõe. É aceito: o carimbo
# interessa no estado TERMINAL, que é onde ele sobrevive.
SQL_CARIMBAR_MOTIVO = (
    "UPDATE dbo.etl_pipeline_execucao "
    "SET motivo = LEFT(ISNULL(motivo + ' | ', '') + ?, 500), "
    "atualizado_em = GETDATE() "
    "WHERE pipeline_name = ? AND data_referencia = ? AND execution_id = ? "
    "AND (motivo IS NULL OR motivo NOT LIKE ?)")


def carimbar_motivo(cur, pipeline: str, data_ref, execution_id,
                    chave: str, texto: str) -> bool:
    """Anexa `texto` ao `motivo` da linha, uma vez só (a `chave` é o que o
    `NOT LIKE` procura). True = carimbou agora.

    ⚠️ **Sem guarda por `malha_execucao_id IS NULL`, e isso foi MEDIDO.** A
    primeira versão só carimbava linha sem corrida, o que parecia coerente
    ("não escrever *ficou fora do ciclo* numa linha que está num ciclo"). No
    dev, com `DEV_F10_A` membro de quatro malhas, a consequência foi a
    seguinte: a corrida da primeira malha carimbou a linha, e quando a segunda
    malha recusou por ODATE divergente (Decisão 15) o motivo NÃO foi gravado —
    o `rowcount` voltou 0 e o diagnóstico sumiu justamente no caso do §6.9/#6,
    que é o mais difícil de entender de plantão.

    A guarda era desnecessária porque quem chama já garante o que ela tentava
    garantir: `partidas_a_cobrir` exclui as linhas que uma corrida DESTA malha
    já cobriu, então a linha carimbada nunca pertence à corrida sobre a qual o
    texto fala. E o texto nomeia a MALHA, então "fora do ciclo da malha X" é
    verdade mesmo quando a linha está no ciclo da malha Y."""
    # SEM try/except de degradação, de propósito: este statement não toca
    # objeto nenhum da 085 (o `WHERE` é pipeline/data/execution_id), então um
    # `_sem_085` aqui seria um ramo morto — e ramo morto de degradação é pior
    # que ramo nenhum, porque promete uma proteção que não existe. Quem chama
    # já passou pelo portão que confere a 085, e o `try/except` por malha da
    # guardiã desfaz o ciclo inteiro daquela malha se algo aqui estourar.
    cur.execute(SQL_CARIMBAR_MOTIVO,
                (str(texto)[:400], pipeline, data_ref, execution_id,
                 "%" + chave + "%"))
    return (cur.rowcount or 0) == 1


# ── o heartbeat da guardiã (§10/F2, contrato com a F3) ─────────────────────
SQL_HEARTBEAT_GRAVAR = (
    "UPDATE dbo.etl_app_config "
    "SET config_value = CONVERT(VARCHAR(19), SYSDATETIME(), 120), "
    "updated_by = ?, updated_at = GETDATE() "
    "WHERE config_key = ?")
SQL_HEARTBEAT_CRIAR = (
    "INSERT INTO dbo.etl_app_config "
    "(config_key, config_value, descricao, updated_by) "
    "SELECT ?, CONVERT(VARCHAR(19), SYSDATETIME(), 120), ?, ? "
    "WHERE NOT EXISTS (SELECT 1 FROM dbo.etl_app_config WHERE config_key = ?)")
SQL_HEARTBEAT_LER = (
    "SELECT c.config_value, "
    "CASE WHEN TRY_CONVERT(DATETIME2, c.config_value) >= "
    "DATEADD(MINUTE, -?, SYSDATETIME()) THEN 1 ELSE 0 END "
    "FROM dbo.etl_app_config c WHERE c.config_key = ?")


def marcar_heartbeat(cur, quem: str = "guardia") -> bool:
    """Carimba `malha_corrida_guardia_visto_em` com o relógio do BANCO.

    UPDATE-e-depois-INSERT (e não MERGE): duas guardiãs em paralelo com MERGE
    produzem a duplicata clássica da chave, e aqui o INSERT já vem com
    `WHERE NOT EXISTS`. O valor é texto ISO porque `etl_app_config.config_value`
    é `VARCHAR(1000)` — a conversão é do BANCO (`CONVERT(..., 120)`), nunca um
    `datetime.now().isoformat()` do processo, que no dev estaria 3h atrás.

    Só é chamado com o interruptor LIGADO e a 085 presente: o heartbeat responde
    "a guardiã está OPERANDO a corrida", e não "a guardiã está viva". Com o
    interruptor em 0 a resposta honesta à pergunta da F3 é NÃO."""
    try:
        cur.execute(SQL_HEARTBEAT_GRAVAR, (quem, CHAVE_HEARTBEAT))
        if (cur.rowcount or 0) >= 1:
            return True
        cur.execute(SQL_HEARTBEAT_CRIAR,
                    (CHAVE_HEARTBEAT, DESCRICAO_HEARTBEAT, quem,
                     CHAVE_HEARTBEAT))
        return (cur.rowcount or 0) == 1
    except Exception as e:  # noqa: BLE001 — o heartbeat NUNCA derruba o ciclo
        log.warning("%s heartbeat da guardia nao gravado (%s) — a F3 vai "
                    "tratar como guardia ausente", LOG, e)
        return False


def heartbeat_guardia(cur, minutos: int = 15) -> dict:
    """`{visto_em, recente}` — o que a F3 consulta antes de deixar a API abrir
    corrida (§11.1: a célula `api/` nova × `dags/` antigo é a mais provável, e
    nela a API abriria corridas que o motor deployado não sabe fechar).

    A comparação com `minutos` é feita no BANCO: a API e o worker podem estar em
    relógios diferentes, e comparar em Python daria "guardiã morta" ou "guardiã
    viva" conforme o servidor. Ausente/ilegível → `recente=False`."""
    try:
        cur.execute(SQL_HEARTBEAT_LER, (int(minutos), CHAVE_HEARTBEAT))
        row = cur.fetchone()
    except Exception as e:  # noqa: BLE001 — leitura degrada larga
        log.warning("%s heartbeat da guardia indisponivel (%s) — tratado "
                    "como ausente", LOG, e)
        return {"visto_em": None, "recente": False}
    if not row:
        return {"visto_em": None, "recente": False}
    return {"visto_em": row[0], "recente": bool(row[1])}


# ── a corrida daquele DIA (chave estável do evento do observador) ───────────
# `TOP 1` com `ORDER BY` explícito (regra da casa D15): a mais recente do dia,
# aberta ou fechada. Não é identidade — identidade é o `id` (Decisão 7) — é a
# resposta a "de que corrida é o evento desta data?", e ela precisa continuar a
# MESMA depois de a corrida fechar. Sem isso, o observador do nó Fim gravaria
# `MALHA_CONCLUIDA` com a corrida no ciclo em que ela ainda está aberta e
# gravaria de novo, com a corrida em NULL, no ciclo seguinte — chave diferente,
# índice satisfeito, DOIS cards para a mesma malha no mesmo dia.
SQL_CORRIDA_DA_DATA = (
    "SELECT TOP 1 " + _COLS + " FROM dbo.etl_malha_execucao "
    "WHERE malha_name = ? AND data_referencia = ? "
    "ORDER BY sequencia DESC, id DESC")


def corrida_da_data(cur, malha: str, data_ref):
    """A corrida mais recente da malha naquele ODATE, aberta ou fechada, ou
    None."""
    try:
        cur.execute(SQL_CORRIDA_DA_DATA, (malha, data_ref))
        row = cur.fetchone()
        return _como_dict(row) if row else None
    except Exception as e:  # noqa: BLE001 — leitura degrada larga
        log.warning("%s corrida de %s em %s indisponivel (%s) — seguindo "
                    "sem", LOG, malha, data_ref, e)
        return None
