"""
dags/utils/malha_corrida.py — a CORRIDA de malha como registro (F1 da spec
docs/spec-malha-execucao.md §5 e §6).

O ciclo da malha deixa de ser inferido por quatro réguas incompatíveis (a janela
em horas, a virada do dia, "o membro mais recente" e o `(malha, data)`) e passa a
ser UM registro com identidade: aberto pelo Início (ou pelo disparo), fechado
pela guardiã, carregando o ODATE do ciclo, o instante exato de abertura e o
desfecho. Este módulo é a ÚNICA autoridade sobre esse registro — quem precisar
perguntar ou escrever qualquer coisa sobre a corrida entra AQUI (a regra que
utils/dependencias.py já impõe: "nenhuma consulta paralela").

CONTRATO (idêntico ao de utils/dependencias.py e utils/malha_ciclo.py):
  • placeholder `%s` (pymssql — árvore `dags/`); o gêmeo api/services/malha_corrida.py
    usa `?` (pyodbc). O canônico é ESTE: quem muda a regra muda aqui primeiro e
    espelha lá, no mesmo commit, com o teste de paridade (SQL textualmente igual
    a menos do placeholder — precedente tests/test_dependencias_f5_paridade.py);
  • **nenhuma função abre conexão, commita ou faz rollback**: o CHAMADOR é dono da
    transação. Abrir a corrida e congelar o snapshot são UM commit só (§6.2), e
    fechar a corrida commita junto com o evento (Decisão 20);
  • todo relógio da corrida é o do BANCO (Decisão 10): `SYSDATETIME()`/`DATEADD`
    no SQL, nunca `datetime.now()` nem aritmética de timedelta em Python. No dev,
    o SQL Server está ~3h à frente do worker — medido, não suposto;
  • toda transição é `UPDATE ... WHERE <estado esperado>` com `rowcount` de
    árbitro (Decisão 8): `rowcount = 0` NÃO é erro, é "outra ponta chegou
    primeiro".

DEGRADAÇÃO — a política tem duas metades, de propósito:
  • **leitura degrada larga**: sem a 085 (ou com o banco fora por um instante) a
    resposta é None/[]/False COM log, nunca exceção. É a regra do §16/10 — a tela
    volta ao comportamento de hoje e o motor não muda de comportamento em ponto
    nenhum. Precedente literal: utils/malha_ciclo.py;
  • **escrita degrada ESTREITA**: só os erros 207/208 (coluna/objeto inexistente)
    que nomeiem os objetos da 085 viram None/False com log; qualquer outro erro
    PROPAGA. Engolir um deadlock, um timeout ou uma violação de FK devolvendo
    "não abriu" faria o chamador seguir achando que não há corrida — a classe de
    defeito que o `ERRO_CONSULTA` de utils/dependencias.py existe para evitar.

O QUE **NÃO** ESTÁ AQUI, e por quê:
  • `estado(conn, corrida)` (Decisão 19) — a classificação de cada membro do
    snapshot (§6.4) é entregável da F2 e depende de `dia_permitido`/eventos órfãos
    que a guardiã já sabe ler; escrevê-la agora seria escrever sem consumidor e
    sem como provar;
  • a expiração PREGUIÇOSA na porta (Decisão 29) — ela só pode expirar quando
    NÃO há membro vivo (Decisão 25 e invariante §16/5), e "vivo" é resposta do
    `estado()` da F2. Uma versão que ignorasse os vivos fecharia corrida com 8
    pipelines `EXECUTANDO` e liberaria o disparo por cima deles: exatamente o
    defeito que a corrida existe para matar;
  • `CAPACIDADES += ("malha_corrida_085",)` em utils/dependencias.py — a
    declaração vale o que o código FAZ, e na F1 nada no motor usa este módulo.
    Declarar capacidade que não existe é o defeito, não a cura (o comentário já
    escrito naquela tupla). Entra na F2, junto com o consumidor.

NENHUM CONSUMIDOR NESTA FASE: nem o motor, nem a guardiã, nem a API chamam este
módulo na F1. É deliberado (§10/F1) — o modelo entra antes, sozinho e provável.
"""
from __future__ import annotations

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
# ciclo da 081 — misturar os três num `grep` de plantão às 3h é ruído.
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
# O número vem do driver: pymssql entrega `args[0]` inteiro; o pyodbc do gêmeo
# põe o código nativo entre parênteses no texto. Nada disso depende do IDIOMA
# do SQL Server — a instalação da Caixa pode estar em pt-BR.
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

# Projeção explícita e ÚNICA da corrida (nunca `SELECT *`: o gêmeo da API tem de
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


def limpar_cache() -> None:
    """Esquece o interruptor lido. Existe para TESTE e para quem quiser
    reavaliar no mesmo processo — em produção o cache morre com a task."""
    _CACHE_ATIVA.clear()


def corrida_ativa(conn) -> bool:
    """A corrida de malha está LIGADA? (`etl_app_config.malha_corrida_ativa`)

    É o kill switch do §11.2: com `0`, nada abre, nada fecha, o card usa o
    fallback e o ODATE fica no degrau de hoje. Nasce em `0` na própria 085 e só
    vai a `1` depois da F7 e do smoke — todas as mudanças recentes de
    comportamento do motor entraram atrás de uma chave em `etl_app_config`
    (`dependencia_modo_sequencia`, `dependencia_janela_sequencia_horas`), porque
    sem ela o rollback é "reverter o merge e refazer o deploy", às 3h.

    Lido uma vez por PROCESSO (precedente `modo_sequencia`): o ciclo da guardiã
    avalia N malhas e a API responde N requisições no mesmo worker — perguntar
    por malha seria N idas ao banco para uma resposta que não muda no meio do
    ciclo. Trocar a chave vale no ciclo seguinte (≤5 min na guardiã), que é o
    comportamento esperado de configuração.

    Ausente (banco sem a 085), ilegível ou banco fora → **False**: o interruptor
    nunca liga sozinho, e é ele quem faz "sem a 085" e "desligado" serem o mesmo
    caminho para todos os chamadores."""
    if "ativa" in _CACHE_ATIVA:
        return _CACHE_ATIVA["ativa"]
    valor = False
    try:
        cur = conn.cursor()
        cur.execute("SELECT config_value FROM dbo.etl_app_config "
                    "WHERE config_key = %s", (CHAVE_ATIVA,))
        row = cur.fetchone()
        valor = bool(row) and str(row[0] or "").strip() in ("1", "true", "True")
    except Exception as e:  # noqa: BLE001 — sem config não há corrida, e ponto
        print(f"{LOG} interruptor {CHAVE_ATIVA} indisponivel ({e}) — corrida DESLIGADA")
    _CACHE_ATIVA["ativa"] = valor
    if valor:
        print(f"{LOG} corrida de malha LIGADA")
    return valor


def tabela_085_presente(conn) -> bool:
    """As duas tabelas e a coluna de vínculo da 085 existem?

    Mesma razão da sonda da 067/075 (D52): a sonda é SQL, e SQL não entra na
    DAG. Serve para a guardiã dizer "085 ausente" UMA vez por ciclo em vez de
    descobrir isso pipeline a pipeline — o interruptor já cobre o caminho
    normal, esta sonda cobre o diagnóstico."""
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT OBJECT_ID('dbo.etl_malha_execucao','U'), "
            "OBJECT_ID('dbo.etl_malha_execucao_membro','U'), "
            "COL_LENGTH('dbo.etl_pipeline_execucao','malha_execucao_id')")
        row = cur.fetchone()
        return bool(row) and all(v is not None for v in row)
    except Exception as e:  # noqa: BLE001
        print(f"{LOG} sonda da 085 indisponivel ({e}) — assumindo ausente")
        return False


# ═══════════════════════ configs numéricas (§6.6, §6.5) ═════════════════════
# NÃO são cacheadas por processo, ao contrário do interruptor: são lidas uma vez
# por corrida (não por membro), e um teto que só muda depois de reiniciar o
# worker seria uma armadilha justamente na madrugada em que alguém precisa
# alargar a janela.

SQL_TETO_DA_MALHA = (
    "SELECT m.teto_horas, c.config_value FROM dbo.etl_malha m "
    "LEFT JOIN dbo.etl_app_config c ON c.config_key = '" + CHAVE_TETO + "' "
    "WHERE m.malha_name = %s")


def teto_horas_da_malha(conn, malha: str) -> int:
    """Teto da corrida desta malha, em horas: `etl_malha.teto_horas` ?? config
    global ?? 24 — resolvido em UMA consulta (a forma de `virada_efetiva`).

    O teto é OBRIGATÓRIO (§6.6): corrida `ABERTA` bloqueia o disparo, então uma
    corrida sem teto seria estritamente pior que o estado de hoje — congelaria a
    malha para sempre, sem tela para destravar. É a classe do `factory_log`
    órfão em RUNNING, elevada da geração para o ciclo.

    Malha inexistente, coluna ausente (sem a 085/081) ou valor fora de
    1..168 → o padrão. Nunca devolve 0."""
    try:
        cur = conn.cursor()
        cur.execute(SQL_TETO_DA_MALHA, (malha,))
        row = cur.fetchone()
    except Exception as e:  # noqa: BLE001 — sem teto lido, o padrão protege
        print(f"{LOG} teto de {malha} indisponivel ({e}) — usando "
              f"{TETO_HORAS_PADRAO}h")
        return TETO_HORAS_PADRAO
    if not row:
        return TETO_HORAS_PADRAO
    da_malha = _inteiro_no_dominio(row[0], TETO_HORAS_MIN, TETO_HORAS_MAX)
    if da_malha is not None:
        return da_malha
    global_ = _inteiro_no_dominio(row[1], TETO_HORAS_MIN, TETO_HORAS_MAX)
    return global_ if global_ is not None else TETO_HORAS_PADRAO


def _config_int(conn, chave: str, padrao: int, minimo: int, maximo: int) -> int:
    cur = conn.cursor()
    cur.execute("SELECT config_value FROM dbo.etl_app_config "
                "WHERE config_key = %s", (chave,))
    row = cur.fetchone()
    n = _inteiro_no_dominio(row[0], minimo, maximo) if row else None
    return n if n is not None else padrao


def quiescencia_minutos(conn) -> int:
    """Carência de quiescência, em minutos (5..240, padrão 15 = 3 ciclos da
    guardiã): tempo sem NENHUM membro vivo antes de a corrida poder fechar por
    quiescência.

    O piso não é decorativo: `_registrar_sucesso` commita o SUCESSO e **só
    então** chama `_disparar_dependentes` — segundos no caminho feliz, minutos
    quando o push falha e a rede de segurança assume. Uma carência curta fecharia
    a corrida exatamente nessa fresta, no meio dela mesma."""
    try:
        return _config_int(conn, CHAVE_QUIESCENCIA, QUIESCENCIA_MIN_PADRAO,
                           QUIESCENCIA_MIN_MIN, QUIESCENCIA_MIN_MAX)
    except Exception as e:  # noqa: BLE001
        print(f"{LOG} {CHAVE_QUIESCENCIA} indisponivel ({e}) — usando "
              f"{QUIESCENCIA_MIN_PADRAO} min")
        return QUIESCENCIA_MIN_PADRAO


def carencia_partida_min(conn) -> int:
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
        return _config_int(conn, CHAVE_CARENCIA, CARENCIA_PARTIDA_PADRAO,
                           CARENCIA_PARTIDA_MIN, CARENCIA_PARTIDA_MAX)
    except Exception as e:  # noqa: BLE001
        print(f"{LOG} {CHAVE_CARENCIA} indisponivel ({e}) — usando "
              f"{CARENCIA_PARTIDA_PADRAO} min")
        return CARENCIA_PARTIDA_PADRAO


# ══════════════════════ o ODATE canônico (Decisão 18) ═══════════════════════

SQL_VIRADA_DA_MALHA = (
    "SELECT m.hora_virada, c.config_value FROM dbo.etl_malha m "
    "LEFT JOIN dbo.etl_app_config c ON c.config_key = 'dependencia_hora_virada' "
    "WHERE m.malha_name = %s")
SQL_VIRADA_GLOBAL = (
    "SELECT config_value FROM dbo.etl_app_config "
    "WHERE config_key = 'dependencia_hora_virada'")


def odate_da_abertura(conn, malha: str, momento):
    """O ODATE que a corrida desta malha carimba ao nascer:
    `calcular(momento, etl_malha.hora_virada ?? virada global)`.

    **Uma função, três portas** (Decisão 18). Hoje existem três fórmulas: a API
    usa a virada GLOBAL (com a divergência painel×disparo confessada em
    api/routers/malhas.py), o `check_agenda` usa a virada do PIPELINE e a 081
    introduziu a virada da MALHA. Com abertura INSERT-first, quem vencesse o
    índice carimbaria o ODATE do ciclo inteiro — disparar às 02:00 pela tela e
    pelo cron no mesmo minuto produziria ciclos com DIAS diferentes conforme
    quem chegasse primeiro: não-determinismo puro. A virada do PIPELINE nunca
    abre corrida de malha; ela continua valendo para pipeline fora de malha.

    `momento` é do relógio do BANCO (Decisão 10) — `dep.agora_do_banco(conn)`, ou
    o `inicio` da linha âncora nas portas 2 e 3. Passar `datetime.now()` aqui é o
    defeito que a Decisão 10 nomeia: no dev o banco está 3h à frente do worker.

    Degradação: se a leitura falhar (banco sem a 081, por exemplo) a virada cai
    para a GLOBAL e, em último caso, para 00:00 — que é o comportamento anterior
    a esta spec, não um terceiro comportamento inventado."""
    from utils.data_referencia import calcular  # lazy: mantém o módulo puro de
    # dependências de import para o carregamento por caminho dos testes, e é o
    # mesmo gesto do `_data_referencia` gerado.
    bruto = None
    try:
        cur = conn.cursor()
        cur.execute(SQL_VIRADA_DA_MALHA, (malha,))
        row = cur.fetchone()
        if row:
            bruto = row[0] if row[0] is not None else row[1]
    except Exception as e:  # noqa: BLE001 — sem a 081 ainda há a virada global
        print(f"{LOG} virada de {malha} indisponivel ({e}) — tentando a global")
        try:
            cur = conn.cursor()
            cur.execute(SQL_VIRADA_GLOBAL)
            row = cur.fetchone()
            bruto = row[0] if row else None
        except Exception as e2:  # noqa: BLE001
            print(f"{LOG} virada global indisponivel ({e2}) — usando 00:00")
    return calcular(momento, bruto)


# ═════════════════════════════ leituras ═════════════════════════════════════

SQL_CORRIDA_ABERTA = (
    "SELECT " + _COLS + " FROM dbo.etl_malha_execucao "
    "WHERE malha_name = %s AND fechada_em IS NULL")
SQL_CORRIDAS_ABERTAS = (
    "SELECT " + _COLS + " FROM dbo.etl_malha_execucao "
    "WHERE fechada_em IS NULL ORDER BY malha_name")
SQL_CORRIDA_POR_ID = (
    "SELECT " + _COLS + " FROM dbo.etl_malha_execucao WHERE id = %s")
SQL_ABERTAS_DO_PIPELINE = (
    "SELECT " + _COLS_ME + " FROM dbo.etl_malha_execucao me "
    "JOIN dbo.etl_malha_pipeline mp ON mp.malha_name = me.malha_name "
    "WHERE mp.pipeline_name = %s AND me.fechada_em IS NULL "
    "ORDER BY me.malha_name")
SQL_MEMBROS = (
    "SELECT pipeline_name, conta_para_fim, ativo_na_abertura, eh_raiz "
    "FROM dbo.etl_malha_execucao_membro WHERE malha_execucao_id = %s "
    "ORDER BY pipeline_name")


def corrida_aberta(conn, malha: str):
    """A corrida ABERTA da malha, ou None.

    A releitura é SEMPRE `malha_name = %s AND fechada_em IS NULL` — **jamais**
    por `(malha, data)` (Decisão 7). Identidade é o `id`; `(malha, data)` é o
    beco do qual esta spec inteira sai: duas corridas no mesmo ODATE são
    legítimas (redisparo) e colidiriam.

    `fechada_em IS NULL` é o MESMO predicado do índice filtrado
    `ux_malha_exec_aberta`, e o `CK_mexec_coerente` garante que ele e
    `status = 'ABERTA'` não podem discordar — por isso não se filtra por
    status: seria uma segunda régua para o mesmo fato."""
    try:
        cur = conn.cursor()
        cur.execute(SQL_CORRIDA_ABERTA, (malha,))
        row = cur.fetchone()
        return _como_dict(row) if row else None
    except Exception as e:  # noqa: BLE001 — leitura degrada larga (docstring do módulo)
        print(f"{LOG} corrida aberta de {malha} indisponivel ({e}) — seguindo sem")
        return None


def corridas_abertas(conn) -> list:
    """TODAS as corridas abertas, por malha — o universo do fechador da F2.

    Uma consulta só para o ciclo inteiro (nunca uma por malha): é o mesmo
    princípio do `GROUP BY` único que api/routers/malhas.py se proíbe em
    comentário de virar N+1."""
    try:
        cur = conn.cursor()
        cur.execute(SQL_CORRIDAS_ABERTAS)
        return [_como_dict(r) for r in cur.fetchall()]
    except Exception as e:  # noqa: BLE001
        print(f"{LOG} corridas abertas indisponiveis ({e}) — nada a fechar neste ciclo")
        return []


def corrida(conn, corrida_id):
    """A corrida por id, aberta ou fechada — a releitura de quem acabou de
    fechar/reabrir e precisa do registro para o evento e o log."""
    try:
        cur = conn.cursor()
        cur.execute(SQL_CORRIDA_POR_ID, (int(corrida_id),))
        row = cur.fetchone()
        return _como_dict(row) if row else None
    except Exception as e:  # noqa: BLE001
        print(f"{LOG} corrida #{corrida_id} indisponivel ({e}) — seguindo sem")
        return None


def corrida_aberta_do_pipeline(conn, pipeline: str) -> dict:
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
        cur = conn.cursor()
        cur.execute(SQL_ABERTAS_DO_PIPELINE, (pipeline,))
        corridas = [_como_dict(r) for r in cur.fetchall()]
    except Exception as e:  # noqa: BLE001
        print(f"{LOG} corridas abertas de {pipeline} indisponiveis ({e}) — sem ODATE")
        return {"corridas": [], "odate": None, "ambiguo": False}
    odates = {c["data_referencia"] for c in corridas}
    if len(odates) > 1:
        print(f"{LOG} {pipeline} e membro de {len(corridas)} corridas abertas com "
              f"ODATEs diferentes — ambiguo, sem escolha")
        return {"corridas": corridas, "odate": None, "ambiguo": True}
    return {"corridas": corridas,
            "odate": next(iter(odates)) if odates else None,
            "ambiguo": False}


def membros(conn, corrida_id) -> list:
    """O snapshot congelado da corrida: `[{pipeline, conta_para_fim,
    ativo_na_abertura, eh_raiz}]`, por pipeline.

    É o DENOMINADOR do "4 de 7", e ele é do desenho **no instante da abertura**:
    editar a malha durante o ciclo não muda a conta desta corrida (§6.9/#16) —
    vale da próxima em diante. Sem isso, o denominador mudaria embaixo do
    operador no meio da madrugada."""
    try:
        cur = conn.cursor()
        cur.execute(SQL_MEMBROS, (int(corrida_id),))
        return [{"pipeline": r[0], "conta_para_fim": bool(r[1]),
                 "ativo_na_abertura": bool(r[2]), "eh_raiz": bool(r[3])}
                for r in cur.fetchall()]
    except Exception as e:  # noqa: BLE001
        print(f"{LOG} membros da corrida #{corrida_id} indisponiveis ({e})")
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
    "SELECT %s, %s, "
    "(SELECT ISNULL(MAX(x.sequencia), 0) + 1 FROM dbo.etl_malha_execucao x "
    "WITH (UPDLOCK, HOLDLOCK) "
    "WHERE x.malha_name = %s AND x.data_referencia = %s), "
    "'ABERTA', v.ab, %s, %s, %s, %s, %s, %s, %s, "
    "DATEADD(HOUR, %s, v.ab), %s "
    "FROM (SELECT COALESCE(CAST(%s AS DATETIME2), SYSDATETIME()) AS ab) v")


def abrir_corrida(conn, malha: str, odate, origem: str, *,
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
    agora, no relógio do banco (porta 1, o disparo manual).

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
        teto = teto_horas_da_malha(conn, malha)
    params = (malha, odate, malha, odate, origem, aberta_por, ancora_pipeline,
              ancora_execution_id, no_inicio, no_fim, modo_fechamento, teto,
              motivo, aberta_em)
    for tentativa in range(1, _TENTATIVAS_ABERTURA + 1):
        try:
            cur = conn.cursor()
            cur.execute(SQL_ABRIR, params)
            row = cur.fetchone()
            if row:
                nova = _como_dict(row)
                nova["nova"] = True
                nova["odate_confere"] = nova["data_referencia"] == odate
                return nova
            # INSERT sem OUTPUT devolvido não deveria acontecer; tratar como
            # "não abri" é mais honesto que devolver um dict pela metade.
            print(f"{LOG} abertura de {malha} nao devolveu a linha — sem corrida")
            return None
        except Exception as e:  # noqa: BLE001 — três casos NOMEADOS, o resto sobe
            if _violou(e, IX_ABERTA):
                # Cursor NOVO de propósito: o anterior morreu no meio de um
                # INSERT com OUTPUT e pode carregar resultado pendente.
                existente = corrida_aberta(conn, malha)
                if existente is not None:
                    existente["nova"] = False
                    existente["odate_confere"] = existente["data_referencia"] == odate
                    return existente
                # Fechou entre a violação e a releitura — a vaga do índice
                # filtrado vagou; tentar de novo é a resposta certa.
                print(f"{LOG} corrida de {malha} fechou durante a abertura — "
                      f"tentando de novo ({tentativa}/{_TENTATIVAS_ABERTURA})")
                continue
            if _violou(e, IX_SEQUENCIA):
                print(f"{LOG} sequencia de {malha} em {odate} tomada por outra "
                      f"ponta — recalculando ({tentativa}/{_TENTATIVAS_ABERTURA})")
                continue
            if _sem_085(e):
                print(f"{LOG} 085 ausente ({e}) — corrida de {malha} nao aberta")
                return None
            raise
    print(f"{LOG} abertura de {malha} desistiu apos {_TENTATIVAS_ABERTURA} "
          f"tentativas — sem corrida neste ciclo")
    return None


# O snapshot é IDEMPOTENTE (o NOT EXISTS final): a abertura pode ter aderido a
# uma corrida que já congelou, e uma violação de PK aqui rolaria de volta a
# transação de quem chamou — inclusive o INSERT da corrida.
_SQL_SNAPSHOT = (
    "INSERT INTO dbo.etl_malha_execucao_membro "
    "(malha_execucao_id, pipeline_name, conta_para_fim, ativo_na_abertura, eh_raiz) "
    "SELECT %s, mp.pipeline_name, "
    "CASE WHEN {conta} THEN 1 ELSE 0 END, "
    "CASE WHEN ISNULL(p.active, 0) = 1 THEN 1 ELSE 0 END, "
    "CASE WHEN NOT EXISTS (SELECT 1 FROM dbo.etl_pipeline_dependencia d "
    "JOIN dbo.etl_malha_pipeline irmao ON irmao.malha_name = mp.malha_name "
    "AND irmao.pipeline_name = d.depende_de "
    "WHERE d.pipeline_name = mp.pipeline_name AND d.tipo = 'PIPELINE') "
    "THEN 1 ELSE 0 END "
    "FROM dbo.etl_malha_pipeline mp "
    "LEFT JOIN dbo.etl_pipeline p ON p.pipeline_name = mp.pipeline_name "
    "WHERE mp.malha_name = %s "
    "AND NOT EXISTS (SELECT 1 FROM dbo.etl_malha_execucao_membro m "
    "WHERE m.malha_execucao_id = %s AND m.pipeline_name = mp.pipeline_name)")


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
        marcadores = ", ".join("%s" for _ in range(quantos_contam))
        conta = "mp.pipeline_name IN (" + marcadores + ")"
    return _SQL_SNAPSHOT.format(conta=conta)


def congelar_snapshot(conn, corrida_id, malha: str, conta_para_fim=None):
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
        cur = conn.cursor()
        cur.execute(sql, tuple(params))
        return int(cur.rowcount or 0)
    except Exception as e:  # noqa: BLE001 — escrita degrada ESTREITA
        if _sem_085(e):
            print(f"{LOG} 085 ausente ({e}) — snapshot de {malha} nao congelado")
            return None
        raise


# ═══════════════════════ vínculo da linha de execução ═══════════════════════

SQL_VINCULAR = (
    "UPDATE dbo.etl_pipeline_execucao "
    "SET malha_execucao_id = %s, atualizado_em = GETDATE() "
    "WHERE pipeline_name = %s AND data_referencia = %s AND execution_id = %s "
    "AND malha_execucao_id IS NULL")


def vincular_execucao(conn, pipeline: str, data_ref, execution_id,
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
        cur = conn.cursor()
        cur.execute(SQL_VINCULAR,
                    (int(corrida_id), pipeline, data_ref, execution_id))
        return (cur.rowcount or 0) == 1
    except Exception as e:  # noqa: BLE001 — escrita degrada ESTREITA
        if _sem_085(e):
            print(f"{LOG} 085 ausente ({e}) — {pipeline} nao vinculado a corrida "
                  f"#{corrida_id}")
            return False
        raise


# ═══════════════════════ fechamento e reabertura ════════════════════════════

# `motivo` ACUMULA (o `CASE` com o mesmo parâmetro duas vezes): o histórico do
# que aconteceu com a corrida é curto e cabe em 500 chars, e sobrescrever
# apagaria justamente o `DATA_DIVERGENTE` da abertura. Um SQL só, e não duas
# variantes, para o teste de paridade comparar UM texto.
SQL_FECHAR = (
    "UPDATE dbo.etl_malha_execucao "
    "SET status = %s, fechada_em = SYSDATETIME(), fechada_por = %s, "
    "motivo = CASE WHEN %s IS NULL THEN motivo "
    "ELSE LEFT(ISNULL(motivo + ' | ', '') + %s, 500) END, "
    "atualizado_em = SYSDATETIME() "
    "WHERE id = %s AND fechada_em IS NULL")


def fechar_corrida(conn, corrida_id, desfecho: str, fechada_por: str,
                   motivo=None) -> bool:
    """Fecha a corrida com um dos sete desfechos. True = ESTA chamada fechou.

    `WHERE id = %s AND fechada_em IS NULL` com `rowcount` de árbitro (Decisão 8):
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
        cur = conn.cursor()
        cur.execute(SQL_FECHAR,
                    (desfecho, fechada_por, motivo, motivo, int(corrida_id)))
        return (cur.rowcount or 0) == 1
    except Exception as e:  # noqa: BLE001 — escrita degrada ESTREITA
        if _sem_085(e):
            print(f"{LOG} 085 ausente ({e}) — corrida #{corrida_id} nao fechada")
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
    "me.reaberta_em = SYSDATETIME(), me.reaberta_por = %s, "
    "me.motivo = CASE WHEN %s IS NULL THEN me.motivo "
    "ELSE LEFT(ISNULL(me.motivo + ' | ', '') + %s, 500) END, "
    "me.atualizado_em = SYSDATETIME() "
    "FROM dbo.etl_malha_execucao me "
    "WHERE me.id = %s AND me.status IN (" +
    ", ".join("%s" for _ in REABREM) + ") "
    "AND NOT EXISTS (SELECT 1 FROM dbo.etl_malha_execucao o "
    "WITH (UPDLOCK, HOLDLOCK) "
    "WHERE o.malha_name = me.malha_name AND o.fechada_em IS NULL)")


def reabrir_corrida(conn, corrida_id, reaberta_por: str, motivo=None) -> bool:
    """Reabre uma corrida CONCLUIDA ou FALHA (rerun com cascata, §6.9/#3).
    True = reabriu; conta `tentativas += 1`.

    False tem duas causas, e o chamador que quiser nomeá-la lê
    `corrida_aberta(malha)`: (i) o desfecho é fim de linha — `SEM_TRABALHO`,
    `EXPIRADA`, `ABORTADA` e `CANCELADA` não voltam; (ii) já existe OUTRA corrida
    aberta da malha, e nesse caso a regra da spec é explícita: **não reabre**, a
    linha preserva o `malha_execucao_id` original (Decisão 9) e grava-se
    `MALHA_REPROCESSO` na corrida antiga."""
    try:
        cur = conn.cursor()
        cur.execute(SQL_REABRIR,
                    (reaberta_por, motivo, motivo, int(corrida_id), *REABREM))
        return (cur.rowcount or 0) == 1
    except Exception as e:  # noqa: BLE001 — escrita degrada ESTREITA
        if _sem_085(e):
            print(f"{LOG} 085 ausente ({e}) — corrida #{corrida_id} nao reaberta")
            return False
        raise


# ═════════════════ memória de efeito colateral (Decisão 12) ═════════════════

_SQL_VISTO = {
    "falha": ("UPDATE dbo.etl_malha_execucao "
              "SET falha_vista_em = SYSDATETIME(), atualizado_em = SYSDATETIME() "
              "WHERE id = %s AND fechada_em IS NULL AND falha_vista_em IS NULL"),
    "atraso": ("UPDATE dbo.etl_malha_execucao "
               "SET atraso_visto_em = SYSDATETIME(), atualizado_em = SYSDATETIME() "
               "WHERE id = %s AND fechada_em IS NULL AND atraso_visto_em IS NULL"),
}


def marcar_visto(conn, corrida_id, o_que: str) -> bool:
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
        cur = conn.cursor()
        cur.execute(sql, (int(corrida_id),))
        return (cur.rowcount or 0) == 1
    except Exception as e:  # noqa: BLE001 — escrita degrada ESTREITA
        if _sem_085(e):
            print(f"{LOG} 085 ausente ({e}) — marcador {o_que} da corrida "
                  f"#{corrida_id} nao gravado")
            return False
        raise
