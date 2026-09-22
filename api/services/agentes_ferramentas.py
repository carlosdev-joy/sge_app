"""api/services/agentes_ferramentas.py — as ferramentas do agente DataStage e
a allowlist que as guarda (F2 + F2b da spec docs/spec-agentes-datastage.md).

Cinco ferramentas, e só cinco (ferramenta nova entra por PR, nunca por
aprendizado do modelo):

  • `resolver_projeto` — decide o PROJETO DataStage da conversa (§3,
    "resolução do projeto"). Não toca o servidor: valida contra a BASE
    (`etl_pipeline`/`etl_ds_job_isx`) e a lista de arquivos `.dsx`
    (`DSX_BASE_DIR`, só os NOMES — ler o conteúdo é `dsx_consulta`). Sem
    projeto resolvido, `base`/`dsjob`/`dsx_consulta`/`isx_extrair` se
    recusam a rodar — é a guarda central contra "consultas às cegas"
    (risco 28 da spec).
  • `base` — o que o Orquestra já sabe do job (`etl_ds_job_isx` +
    `etl_job_lineage` `isx_auto`; `etl_agente_fato` só a partir da F5).
    Sempre tentada ANTES de `dsjob`/`dsx_consulta` — é o "base primeiro".
  • `dsjob` — leitura ao vivo no servidor DataStage, só os 5 subcomandos
    read-only que não expõem valor de dado (`ljobs`, `lstages`, `lparams`,
    `jobinfo`, `report`; **nunca** `logsum`/`logdetail`), atrás de um
    semáforo de sessões SSH (`agentes_ssh_max`) e sempre `redigir()`ada
    antes de qualquer gravação ou de ir ao modelo.
  • `dsx_consulta` (F2b) — **somente leitura** dos `.dsx` que já existem em
    `DSX_BASE_DIR` (nunca toca o servidor DataStage), pelo `DSXEngine`
    existente — as MESMAS funções que `api/routers/lineage.py` já usa.
    Toda resposta traz nome+data do arquivo (é um retrato); `redigir()`
    sempre; roda num executor com teto (um `.dsx` grande não pode travar
    a rodada).
  • `isx_extrair` (F2b) — export via `istool` + parse + gravação, com a
    MESMA régua do botão `POST /lineage/isx/extrair` da Governança: as
    MESMAS funções (`lineage_isx.localizar/extrair/gravar`) e o MESMO
    executor dedicado (`routers.lineage_isx._EXECUTOR_ISX`, 2 por
    processo) — nenhum pool novo. Exige `acao_editar` do usuário (o mesmo
    do botão); sem ela, devolve o link da Governança em vez de extrair.
"""
from __future__ import annotations

import asyncio
import os
import re
import time
from datetime import datetime

from fastapi import HTTPException

from routers.lineage_isx import _EXECUTOR_ISX as ISX_EXECUTOR  # noqa: F401 — reexportado (testes)
from routers.lineage_isx import _no_executor as isx_no_executor
from routers.lineage_isx import _TETO_EXTRAIR_S as ISX_TETO_EXTRAIR_S
from services import lineage_isx
from services.ssh_datastage import DsConsoleError, run_dsjob, ssh_configured

# ── Redação de segredos ──────────────────────────────────────────────────────
#
# O que sai do `dsjob` (em especial `-lparams` e `-report`) pode trazer valor
# de parâmetro `Encrypted` e trechos de configuração com senha — nada disso
# pode chegar ao modelo nem ser gravado (mensagem, fato ou aprendizado).
# Conservador de propósito (D-07 ainda não fechada — não sabemos o formato
# exato): mascara qualquer coisa que PAREÇA um valor de campo sensível, e o
# nome do parâmetro/campo continua visível (é o que o operador precisa ler).
#
# HISTÓRICO (7 rodadas de revisão adversarial da F2, depois F2b — deixado
# registrado porque cada tentativa "mais esperta" baseada numa ÚNICA regex
# complexa (`.sub()` com quantificador variável + requisito condicional)
# se provou frágil de um jeito NOVO a cada rodada: miss por aspas ao redor
# do nome; vazamento do resto do MESMO valor por aspa escapada; vazamento
# de um CAMPO SEGUINTE inteiro por barra-antes-de-aspa-real; corte no meio
# de um valor `{iisenc}...` por causa de `}` tratado como delimitador;
# `\b` não reconhecendo `_` como fronteira de SNAKE_CASE; um sufixo SEM
# limite virando ReDoS quadrático; um sufixo COM limite virando falha
# total de match (vazamento) para nome mais longo que o limite; e por
# fim, uma "rede de segurança" testando `_MASCARA in linha` (a linha
# INTEIRA) como proxy de "já tratada" — que erra quando a MESMA linha tem
# DOIS segredos (um tratado, um não) ou quando o texto original já
# continha "••••" por acaso, pulando a linha e vazando por completo.
#
# A causa raiz comum: tentar resolver "onde o valor termina" e "o nome
# cabe no padrão" na MESMA regex, com um separador CONDICIONAL disputando
# posição com um quantificador. O desenho abaixo (7ª rodada) separa as
# duas decisões: (1) achar a PRIMEIRA ocorrência de QUALQUER keyword na
# linha — sempre O(1) por keyword, sem quantificador variável nenhum,
# então NUNCA pode ter backtracking catastrófico nem falhar por tamanho
# de nome; (2) por PYTHON PURO (não regex), numa janela CURTA e fixa
# logo depois da keyword, procurar um separador `:`/`=` — se achar,
# masca a partir dali (boa granularidade, nome completo visível); se não
# achar dentro da janela, masca a partir da PRÓPRIA keyword (nunca falha
# por completo — o preço é perder a visibilidade do nome quando ele é
# mais verboso que a janela, nunca vazar o valor). Processa só a
# PRIMEIRA ocorrência de cada linha porque, como sempre masca até o FIM
# da linha a partir dali, qualquer segredo SEGUINTE na mesma linha já
# fica coberto — não existe mais a possibilidade de "pular" um segredo
# anterior para tratar um posterior, que era a causa da 7ª rodada.
#
# Achado real da 8ª rodada: a versão original desta regex (herdada,
# sem mudança, de `_RE_SEGREDO`/`_RE_KEYWORD_SOLTA` das rodadas
# anteriores) exigia delimitador não-letra tanto ANTES quanto DEPOIS da
# keyword. O delimitador de DEPOIS é o que evita falso positivo em
# "TOKENIZER" (depois de "token" vem "i", uma letra — não casa). Mas o
# delimitador de ANTES tem um efeito colateral grave: um nome em
# camelCase/PascalCase, onde a keyword vem colada a outra palavra sem
# `_`/`-`/espaço (`DbPassword`, `authToken`, `accessToken`,
# `clientSecret` — nomes plausíveis de parâmetro DataStage, o mesmo
# domínio que `dags/utils/isx_engine.py` já trata com regex SEM
# boundary nenhum), nunca satisfaz esse delimitador — `_RE_KEYWORD` não
# casa em lugar NENHUM da linha, e o segredo sai por completo, sem
# máscara. Esse era o único ponto de defesa no caminho do stdout cru do
# `dsjob` via SSH (`ferramenta_dsjob`) — vazamento real, não hipotético.
# Removido o delimitador de ANTES (commit anterior desta mesma rodada de
# achados).
#
# Achado real da 9ª rodada: remover só o delimitador de ANTES resolveu
# metade do problema (keyword como SUFIXO de um nome colado —
# `DbPassword`). A outra metade — keyword como PREFIXO/miolo de um nome
# colado, com mais letras ENTRE ela e o separador (`PasswordHash=`,
# `SecretKey=`, `TokenValue=`, `encryptedValue":`) — continuava vazando
# por completo: o delimitador de DEPOIS (`(?=$|[^a-zA-Z])`) também
# falhava aqui, pelo mesmo motivo. 1ª tentativa desta correção: remover
# TAMBÉM o delimitador de DEPOIS, mas guardar `_redigir_linha` com "se a
# linha não tem `:`/`=` em lugar nenhum, devolve intacta sem procurar
# keyword" — preservava "TOKENIZER processa..." ileso.
#
# Achado real da 10ª rodada: essa guarda tem a MESMA forma de bug de
# TODAS as rodadas anteriores — assumir um formato fixo (aqui, que o
# separador só pode ser `:`/`=`) quando D-07 (o formato real do
# `dsjob`) segue ABERTA. Qualquer separador fora desse alfabeto (tab,
# `|`, `->`, espaços múltiplos — todos plausíveis em saída tabular de
# CLI) fazia a linha passar **intacta**, mesmo com uma keyword real
# colada a um segredo logo depois: `"Password\tSEGREDO123"` saía sem
# máscara nenhuma, porque a guarda nunca deixava `_RE_KEYWORD.search()`
# rodar.
#
# Correção final: removida a guarda de linha inteira. `_redigir_linha`
# tenta a keyword SEMPRE (`search()`, sem lookahead algum antes/depois
# — primeira ocorrência da linha, nunca uma posterior: cortar a partir
# de uma ocorrência posterior deixaria `linha[:corte]` preservar um
# segredo associado à ocorrência anterior, o mesmo bug da 7ª rodada,
# pego durante o desenvolvimento desta mesma correção). Achando
# separador `:`/`=` na janela curta, masca a partir dali (boa
# granularidade). Não achando — janela sem separador reconhecido, seja
# porque não há um, seja porque é um separador fora do alfabeto
# conhecido, seja porque pontuação no meio bloqueou a varredura —
# masca a partir da PRÓPRIA keyword até o fim da linha: cobre qualquer
# separador, conhecido ou não, sem precisar enumerá-los. É a mesma
# garantia "nunca falha por completo" de sempre, agora sem depender de
# reconhecer o separador para sequer TENTAR mascarar.
# Preço aceito (o mesmo trade-off de sempre, nunca vazamento): qualquer
# menção às keywords em texto livre — mesmo "TOKENIZER processa o texto
# normalmente." SEM separador nenhum na linha — agora é mascarada a
# partir do ponto de match. Não há mais como diferenciar sintaticamente
# "é uma palavra comum que contém a keyword" de "é um campo sensível
# com separador desconhecido" sem arriscar reabrir uma nova classe de
# vazamento a cada tentativa — as 10 rodadas desta função confirmam
# isso na prática. Dado o histórico, a escolha é sempre a mais
# conservadora: masca.
_JANELA_NOME_S = 40  # generoso para qualquer nome de parâmetro real
_RE_KEYWORD = re.compile(
    r"(?i)(?:senha|password|pwd|secret|token|api[_-]?key|Encrypted)", re.M)
_CHAR_NOME = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-\"' ")
_MASCARA = "••••"


def _corte_apos_keyword(linha: str, fim_keyword: int) -> int | None:
    """A partir do fim da keyword, procura um separador `:`/`=` numa
    janela CURTA e FIXA (`_JANELA_NOME_S` chars, checagem char a char em
    Python — nunca regex, nunca backtracking). Achando, devolve a
    posição logo depois dele (e de espaços/tabs seguintes). Não achando
    dentro da janela, devolve `None` — cabe a quem chama decidir o
    fallback (ver `_redigir_linha`)."""
    limite = min(len(linha), fim_keyword + _JANELA_NOME_S)
    i = fim_keyword
    while i < limite:
        ch = linha[i]
        if ch in ":=":
            i += 1
            while i < len(linha) and linha[i] in " \t":
                i += 1
            return i
        if ch not in _CHAR_NOME:
            break
        i += 1
    return None


_CHAR_MESMO_TOKEN = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-")


def _redigir_linha(linha: str) -> str:
    m = _RE_KEYWORD.search(linha)
    if m is None:
        return linha  # nenhuma keyword na linha: nada a mascarar
    # SEMPRE a PRIMEIRA ocorrência da linha, nunca uma posterior — pular
    # para uma 2ª ocorrência (por a 1ª não ter achado separador na
    # própria janela) e cortar a partir dela deixaria `linha[:corte]`
    # preservar tudo o que veio ANTES, inclusive um segredo real
    # associado à 1ª ocorrência (mesmo bug da 7ª rodada, pego durante o
    # desenvolvimento desta correção antes de commitar).
    corte = _corte_apos_keyword(linha, m.end())
    fim = corte if corte is not None else m.end()
    # Achado real da 11ª rodada, e achado NOVO da 12ª: mascarar só a
    # partir de `fim` deixa vazar por completo um valor sensível que
    # apareça ANTES da keyword na mesma linha (texto livre:
    # anotação/descrição de job, mensagem de log). A 11ª rodada corrigiu
    # isso apenas para o ramo SEM separador reconhecido (`corte is
    # None`) — a 12ª rodada mostrou que o ramo COM separador reconhecido
    # (`corte is not None`) tem exatamente o MESMO buraco: achar um
    # `:`/`=` depois da keyword só prova que HÁ algum campo:valor dali
    # em diante, nunca que o texto ANTES do match é seguro (ex.:
    # `"...senha_real_aqui, campo relacionado: password: outro"` — o
    # separador de "password:" é reconhecido, mas "senha_real_aqui"
    # continua exposto se só mascararmos a partir da keyword).
    #
    # Achado real da 13ª rodada: checar só o caractere IMEDIATAMENTE
    # antes do match (como a 12ª rodada corrigiu) prova apenas que a
    # keyword é sufixo/infixo do IDENTIFICADOR LOCAL — nunca que TODO o
    # prefixo da linha até ali é seguro. Quando a keyword está no MEIO
    # de um identificador mais adiante (`campo_token_relacionado`,
    # `refresh_token_interval` — nomes plausíveis de parâmetro/config em
    # ETL), o caractere adjacente ('_') passava no teste, e a linha
    # INTEIRA até o corte era preservada — inclusive um valor sensível
    # completamente diferente, mais cedo na mesma linha, separado por
    # espaço/vírgula/ponto-e-vírgula REAIS (`"SEGREDO_REAL_999
    # campo_token_relacionado: ..."` vazava por completo).
    #
    # 1ª tentativa desta correção: exigir que TODO caractere do prefixo
    # (do início da linha até o match) esteja em `_CHAR_MESMO_TOKEN` —
    # corrigia o vazamento, mas quebrava o formato JSON mais comum
    # (`'"AUTH_TOKEN": "segredo123"'`): a aspas de ABERTURA do campo,
    # antes do nome, não está em `_CHAR_MESMO_TOKEN`, então a linha
    # inteira virava máscara mesmo sem NENHUM valor antes da keyword —
    # over-masking severo, pego pela suíte antes de commitar.
    #
    # Correção final: anda para trás a partir do início do match SÓ por
    # caracteres de `_CHAR_MESMO_TOKEN`, até achar onde o IDENTIFICADOR
    # LOCAL de fato começa (`inicio_ident` — `AUTH_` em `"AUTH_TOKEN"`,
    # `campo_` em `campo_token_relacionado`). Só então checa: sobra
    # algum caractere alfanumérico/`_`/`-` em `linha[:inicio_ident]`? Se
    # sim, é outro TOKEN/palavra — um valor independente em potencial —
    # inseguro, masca a linha inteira. Se não (só pontuação estrutural
    # neutra: aspas, `{`, espaços, vírgulas, ou início de linha), é
    # seguro: nada além de sintaxe existe antes do identificador local.
    i = m.start()
    while i > 0 and linha[i - 1] in _CHAR_MESMO_TOKEN:
        i -= 1
    if any(c in _CHAR_MESMO_TOKEN for c in linha[:i]):
        return _MASCARA
    return linha[:fim] + _MASCARA


def redigir(texto: str) -> str:
    """Mascara o VALOR de qualquer linha que pareça um campo sensível — o
    NOME do campo/parâmetro fica visível quando cabe numa janela curta
    depois da keyword; sempre mascarado (nunca vaza), mesmo quando não
    cabe. Nunca levanta: texto vazio/None volta como veio."""
    if not texto:
        return texto or ""
    return "\n".join(_redigir_linha(linha) for linha in texto.split("\n"))


# Formato real de um PARÂMETRO de job DataStage (`dags/utils/isx_engine.py`,
# `has_ParameterDef`): `{"name": ..., "type": ..., "default": ..., "description": ...}`.
# Quando esse dict já chega DESSERIALIZADO (dict Python, não string JSON —
# ex.: depois da correção de `ferramenta_base` para o achado 1), a keyword
# sensível mora numa CHAVE IRMÃ (`type` == "Encrypted", ou `name` contendo
# "senha"/"password"), NUNCA dentro da MESMA STRING que o valor real
# (`default`) — `redigir()`, textual e por string isolada, não enxerga essa
# relação estrutural entre campos. Achado real da 2ª rodada da revisão
# adversarial da F2b: `redigir_estrutura()` "por string" sozinha deixava o
# `default`/`value` de um parâmetro Encrypted intocado, porque a string do
# VALOR em si não contém nenhuma keyword.
_CHAVES_TIPO_PARAMETRO = ("type", "Type", "extendedType", "typeCode")
_CHAVES_NOME_PARAMETRO = ("name", "Name")
_CHAVES_VALOR_PARAMETRO = ("default", "defaultValue", "default_value", "value", "Value", "valor")
# `\b` NÃO é delimitador de palavra suficiente aqui: `_` é caractere de
# PALAVRA em regex (`\w` inclui `_`), então `\btoken\b` não casa "TOKEN"
# dentro de "AUTH_TOKEN" — e SNAKE_CASE é o padrão dominante de nome de
# parâmetro em ETL/DataStage (`AUTH_TOKEN`, `API_KEY_PROD`, `DB_PASSWORD`,
# `MY_API_KEY`...). Achado real da 3ª rodada da revisão adversarial da
# F2b: a checagem por `name` nunca disparava para esse padrão — só o
# caminho por `type == "Encrypted"` funcionava, e um parâmetro de token/
# API key tipado como `String` (comum — nem todo parâmetro de credencial
# é tipado `Encrypted` no DataStage) vazava o valor sem máscara nenhuma.
# Corrigido trocando `\b` por `(?:^|[^a-z])`/`(?:$|[^a-z])` — com `(?i)`,
# `[^a-z]` também exclui A-Z, então SOBRA exatamente "não é letra": `_`,
# dígito, espaço, início/fim de string — delimitador de verdade para
# nome de variável, sem depender da convenção de `\w`.
_RE_NOME_PARAMETRO_SENSIVEL = re.compile(
    r"(?i)(?:^|[^a-z])(?:senha|password|pwd|secret|token|api[_-]?key)(?:$|[^a-z])")


def _parece_parametro_sensivel(d: dict) -> bool:
    for chave in _CHAVES_TIPO_PARAMETRO:
        if str(d.get(chave) or "").strip().lower() == "encrypted":
            return True
    for chave in _CHAVES_NOME_PARAMETRO:
        if _RE_NOME_PARAMETRO_SENSIVEL.search(str(d.get(chave) or "")):
            return True
    return False


def redigir_estrutura(valor):
    """Aplica `redigir()` a cada STRING FOLHA de um dict/list, recursivamente
    — NUNCA ao JSON serializado inteiro de uma vez. `redigir()` mascara até
    o fim da LINHA que contém a keyword sensível (decisão de design das
    rodadas anteriores da F2, pensada para a saída MULTI-LINHA do `dsjob`);
    um `json.dumps(..., default=str)` compacto (sem `indent`, como
    `isx_extrair`/`base`/`dsx_consulta` produzem) é UMA linha lógica só —
    mascarar o texto serializado inteiro apagava a resposta INTEIRA sempre
    que qualquer parte dela (ex.: `job_description` em prosa mencionando
    "senha", ou o VALOR de um campo `type` sendo literalmente "Encrypted")
    continha a keyword — over-masking severo, destruindo o lineage útil
    (achado real da revisão adversarial da F2b). Aplicar por STRING isola
    o dano a cada campo individualmente, sem perder segurança (a defesa
    multi-linha original de `redigir()` continua valendo DENTRO de uma
    string que, por si só, tenha várias linhas — ex.: um `job_description`
    grande, ou o stdout redigido de um `dsjob`).

    Camada ESTRUTURAL adicional (2ª rodada): quando um dict parece um
    PARÂMETRO sensível (`_parece_parametro_sensivel`), o(s) campo(s) de
    VALOR (`default`/`value`/...) são mascarados diretamente — cobre o
    caso em que a keyword está numa chave irmã, não na mesma string."""
    if isinstance(valor, dict):
        sensivel = _parece_parametro_sensivel(valor)
        saida = {}
        for k, v in valor.items():
            if sensivel and k in _CHAVES_VALOR_PARAMETRO and isinstance(v, str) and v:
                saida[k] = _MASCARA
            else:
                saida[k] = redigir_estrutura(v)
        return saida
    if isinstance(valor, list):
        return [redigir_estrutura(v) for v in valor]
    if isinstance(valor, str):
        return redigir(valor)
    return valor


# ── Truncagem ────────────────────────────────────────────────────────────────
#
# `run_dsjob` já trunca o stdout em 200 000 caracteres (o teto do Console) —
# isso ainda é grande demais para ir ao modelo (custo, e o `-report` de um
# job com muitos stages pode ter dezenas de milhares de linhas). O agente
# trunca de novo, bem mais curto, e avisa que truncou.
MAX_SAIDA_MODELO = 6000


def _truncar(texto: str, limite: int = MAX_SAIDA_MODELO) -> str:
    texto = texto or ""
    if len(texto) <= limite:
        return texto
    return texto[:limite] + f"\n… [saída truncada em {limite} caracteres — {len(texto) - limite} a mais]"


# ── Semáforo de sessões SSH (D-09: teto configurável, padrão 10) ────────────

class ServidorOcupado(Exception):
    """A espera pelo semáforo de SSH estourou o prazo — nomeado, não um
    timeout genérico (spec, critério 5 da F2)."""


class SemaforoSsh:
    """Um `asyncio.Semaphore` reconstruído quando o teto muda (o admin edita
    `agentes_ssh_max` em runtime — trocar o `Semaphore` no meio de um
    `acquire()` alheio não afeta quem já entrou, só os próximos)."""

    def __init__(self) -> None:
        self._teto = 0
        self._sem: asyncio.Semaphore | None = None

    def _para(self, teto: int) -> asyncio.Semaphore:
        if self._sem is None or teto != self._teto:
            self._teto = teto
            self._sem = asyncio.Semaphore(teto)
        return self._sem

    async def __call__(self, teto: int, espera_max_s: float):
        """Async context manager: `async with semaforo(teto, espera_s):`."""
        sem = self._para(teto)
        try:
            await asyncio.wait_for(sem.acquire(), timeout=max(0.1, espera_max_s))
        except asyncio.TimeoutError:
            raise ServidorOcupado(
                "Servidor DataStage ocupado (todas as sessões SSH em uso) — tente de novo em instantes.")
        return _SoltarAoSair(sem)


class _SoltarAoSair:
    def __init__(self, sem: asyncio.Semaphore) -> None:
        self._sem = sem

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        self._sem.release()
        return False


SEMAFORO_SSH = SemaforoSsh()


# ── resolver_projeto ─────────────────────────────────────────────────────────

def _projetos_da_base(cur) -> list[str]:
    """Nomes de projeto DataStage que a base já conhece — `etl_pipeline` (todo
    pipeline cadastrado) ∪ `etl_ds_job_isx` (todo job com ISX gravado)."""
    vistos: set[str] = set()
    try:
        cur.execute("SELECT DISTINCT project_name FROM dbo.etl_pipeline WHERE project_name <> ''")
        vistos |= {str(r[0]).strip() for r in cur.fetchall() if r[0]}
    except Exception:
        pass
    try:
        cur.execute("SELECT DISTINCT ds_project FROM dbo.etl_ds_job_isx")
        vistos |= {str(r[0]).strip() for r in cur.fetchall() if r[0]}
    except Exception:
        pass
    return sorted(vistos)


def _dsx_engine_cls():
    """Importa o `DSXEngine` do pacote das DAGs — mesmo padrão de
    `api/routers/lineage.py::_import_dsx_engine` (o container da API monta
    `dags/`, e o `orquestra-api` monta `DSX_BASE_DIR` `:ro`)."""
    import sys
    dags_folder = os.environ.get("DAGS_FOLDER", "/opt/airflow/dags")
    if dags_folder not in sys.path:
        sys.path.insert(0, dags_folder)
    from utils.dsx_engine import DSXEngine  # type: ignore
    return DSXEngine


def _projetos_com_dsx() -> list[str]:
    """Nomes de projeto com arquivo `.dsx` em `DSX_BASE_DIR` — só a LISTA
    (`listar_dsx`); ler o conteúdo de um `.dsx` é a ferramenta `dsx_consulta`."""
    try:
        return list(_dsx_engine_cls()().listar_dsx())
    except Exception:
        return []


def projeto_tem_dsx(nome: str) -> bool:
    """Se `nome` (já resolvido) tem arquivo `.dsx` — usado por `dsx_consulta`
    para recusar sem tocar o disco de novo além da listagem (critério 11 da
    F2b: só roda com projeto **com** `.dsx`)."""
    dsx = _projetos_com_dsx()
    return nome in dsx or _casa_ignorando_caixa(nome, dsx) is not None


def nome_dsx_valido(nome: str) -> str | None:
    """Réplica de `api/routers/lineage.py::_safe_project_name`, sem
    `HTTPException` — devolve `None` (não levanta) quando o nome está vazio
    ou tem sinal de path traversal (critério 7 da F2b)."""
    n = (nome or "").strip()
    if n.lower().endswith(".dsx"):
        n = n[:-4]
    if not n or "/" in n or "\\" in n or ".." in n:
        return None
    return n


def _casa_exato(nome: str, candidatos: list[str]) -> str | None:
    return nome if nome in candidatos else None


def _casa_ignorando_caixa(nome: str, candidatos: list[str]) -> str | None:
    """DataStage é sensível a caixa (nomes de job/projeto). Casa ignorando
    e devolve a grafia CANÔNICA (a que está cadastrada) — mas quem chama
    (`resolver_projeto`) só usa isso para SUGERIR: o critério 11 da F2 pede
    confirmação antes de assumir, nunca corrigir sozinho."""
    alvo = nome.strip().lower()
    for c in candidatos:
        if c.strip().lower() == alvo:
            return c
    return None


def projeto_do_pipeline_job(cur, pipeline_name: str, job_name: str) -> str | None:
    """Se o usuário citou um pipeline/job do Orquestra, o projeto sai daí —
    sem perguntar (spec, critério 10 da F2). Nome vindo de `etl_pipeline_job`
    já é a grafia cadastrada — não precisa de confirmação de caixa."""
    info = lineage_isx.job_do_pipeline(cur, pipeline_name, job_name)
    return info["ds_project"] if info else None


def resolver_projeto(cur, nome_informado: str | None = None,
                     pipeline_name: str | None = None, job_name: str | None = None) -> dict:
    """Valida um nome de projeto DataStage contra o que o Orquestra já
    conhece — a base e a lista de `.dsx`. NÃO toca o servidor DataStage.

    Duas portas de entrada (critério 10 da F2): `pipeline_name`+`job_name`
    (o usuário citou algo do Orquestra — resolve sem perguntar) OU
    `nome_informado` (um nome de projeto DataStage cru, que pode vir com a
    caixa errada — DataStage é sensível a ela).

    Devolve `{"estado": "resolvido"|"quase"|"desconhecido", "projeto": str|None,
    "sugerido": str|None, "tem_dsx": bool, "sugestoes": [str]}`.
    `"quase"` (crítério 11) é SÓ sugestão — nunca resolve sozinho por essa
    via; confirmar é chamar de novo com a grafia exata (`sugerido`)."""
    conhecidos = _projetos_da_base(cur)
    dsx = _projetos_com_dsx()
    todos = sorted(set(conhecidos) | set(dsx))

    if pipeline_name and job_name:
        projeto = projeto_do_pipeline_job(cur, pipeline_name, job_name)
        if projeto:
            return {"estado": "resolvido", "projeto": projeto, "sugerido": None,
                    "tem_dsx": projeto in dsx or _casa_ignorando_caixa(projeto, dsx) is not None,
                    "sugestoes": []}
        # Pipeline/job não achado na base — cai para tentar como nome cru,
        # se também veio; senão desconhecido (sem inventar).

    nome = (nome_informado or "").strip()
    if not nome:
        return {"estado": "desconhecido", "projeto": None, "sugerido": None,
                "tem_dsx": False, "sugestoes": todos[:10]}

    exato = _casa_exato(nome, conhecidos) or _casa_exato(nome, dsx)
    if exato:
        return {"estado": "resolvido", "projeto": exato, "sugerido": None,
                "tem_dsx": exato in dsx, "sugestoes": []}

    quase = _casa_ignorando_caixa(nome, conhecidos) or _casa_ignorando_caixa(nome, dsx)
    if quase:
        return {"estado": "quase", "projeto": None, "sugerido": quase,
                "tem_dsx": quase in dsx, "sugestoes": []}

    return {"estado": "desconhecido", "projeto": None, "sugerido": None,
            "tem_dsx": False, "sugestoes": todos[:10]}


# ── base (o que o Orquestra já sabe) ────────────────────────────────────────

def _idade_dias(data_iso: str | None) -> int | None:
    """Dias desde `data_iso` (o `ds_last_modified` do ISX — "texto ISO da
    API REST", formato exato não confirmado — D-08 da spec). Nunca levanta:
    formato inesperado devolve None, e a resposta diz "idade desconhecida"
    em vez de inventar um número."""
    if not data_iso:
        return None
    import datetime as _dt
    texto = str(data_iso).strip()
    quando = None
    try:
        quando = _dt.datetime.fromisoformat(texto.replace("Z", "+00:00"))
        if quando.tzinfo is not None:
            quando = quando.astimezone(_dt.timezone.utc).replace(tzinfo=None)
    except ValueError:
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                quando = _dt.datetime.strptime(texto, fmt)
                break
            except ValueError:
                continue
    if quando is None:
        return None
    return max(0, (_dt.datetime.now() - quando).days)


def _json_ou(v, padrao):
    """`json.loads` tolerante — texto vazio/`None`/inválido devolve `padrao`,
    nunca levanta. Mesma função de `services.lineage_isx._json_ou`, copiada
    aqui para não acoplar `agentes_ferramentas` ao módulo inteiro por uma
    função de 5 linhas."""
    if not v:
        return padrao
    try:
        import json as _json
        return _json.loads(v)
    except (TypeError, ValueError):
        return padrao


def ferramenta_base(cur, ds_project: str, job_name: str) -> dict:
    """Lê `etl_ds_job_isx`/`etl_job_lineage` (isx_auto) para (projeto, job).
    Sem FK direta por projeto — busca por `ds_project` + `job_name`, que é
    único por job dentro de um projeto na prática do DataStage.

    Inclui `idade_dias` do `ds_last_modified` — a RESPOSTA já traz a idade
    computada (critério 3 da F2: "a resposta informa a idade do dado"), sem
    depender do modelo calcular a partir de uma data crua.

    `parameters_json`/`flow_json` são DESSERIALIZADOS aqui (nunca devolvidos
    como string JSON crua) — achado real da revisão adversarial da F2b:
    essas colunas guardam um `json.dumps(...)` COMPACTO (uma linha só,
    gravado por `lineage_isx._js()`); `redigir_estrutura()`, rio abaixo,
    só desce em dict/list — uma STRING contendo um blob JSON inteiro era
    tratada como UMA folha só, e `redigir()` sobre ela reproduzia o
    over-masking "até o fim da linha" exatamente onde moram os parâmetros
    `Encrypted`. Desserializar aqui iguala o formato ao que
    `lineage_isx.montar()` já devolve (dict/list em memória), que
    `redigir_estrutura()` já trata corretamente campo a campo."""
    cur.execute(
        "SELECT pipeline_name, job_name, ds_folder_path, ds_job_type, ds_last_modified, "
        "       job_description, parameters_json, flow_json, status, erro, extracted_at "
        "FROM dbo.etl_ds_job_isx WHERE ds_project = ? AND job_name = ?", [ds_project, job_name])
    row = cur.fetchone()
    if not row:
        return {"encontrado": False}
    cur.execute(
        "SELECT COUNT(*) FROM dbo.etl_job_lineage "
        "WHERE pipeline_name = ? AND job_name = ? AND extraction_method = 'isx_auto'",
        [row[0], job_name])
    n_stages = cur.fetchone()
    return {
        "encontrado": True, "origem": "isx", "pipeline_name": row[0], "job_name": row[1],
        "ds_folder_path": row[2], "job_type": row[3], "ds_last_modified": row[4],
        "idade_dias": _idade_dias(row[4]),
        "job_description": row[5],
        "parameters_json": _json_ou(row[6], []), "flow_json": _json_ou(row[7], []),
        "status": row[8], "erro": row[9], "extracted_at": str(row[10]) if row[10] else None,
        "stages": int(n_stages[0]) if n_stages else 0,
    }


# ── dsjob (leitura ao vivo) ──────────────────────────────────────────────────

ALLOWLIST_DSJOB = ("ljobs", "lstages", "lparams", "jobinfo", "report")


async def ferramenta_dsjob(comando: str, ds_project: str, job_name: str | None,
                           *, teto_sessoes: int, espera_max_s: float) -> dict:
    """`dsjob` de leitura, atrás do semáforo. Levanta `DsConsoleError`
    (comando/nome inválido, SSH não configurado) ou `ServidorOcupado`
    (semáforo estourou a espera) — o chamador (a orquestração) as traduz em
    mensagem nomeada; nunca deixa o modelo escolher um comando fora da
    allowlist, mesmo que o pedido venha bem formado.

    Duas fases com segurança de cancelamento DIFERENTE (achado real da 3ª
    rodada da revisão adversarial da F2): enquanto só está NA FILA do
    semáforo, cancelar de fora (ex.: o orçamento da rodada estourando) é
    seguro e desejável — larga a vaga na hora, sem custo. Mas depois de
    OBTIDA a vaga, a sessão real (paramiko, via `asyncio.to_thread`) não é
    interrompível — abandonar o `async with` no meio liberaria o semáforo
    "mentindo": o teto contaria a vaga como livre enquanto a sessão de
    verdade ainda roda no servidor DataStage. Por isso só ESSA fase
    (adquirido → trabalho → libera) é protegida com `asyncio.shield`: um
    cancelamento externo durante ela não a interrompe, só deixa de esperar
    por ela — ela termina sozinha, no seu tempo, e libera o semáforo no
    momento certo."""
    if comando not in ALLOWLIST_DSJOB:
        raise DsConsoleError(f"Comando '{comando}' não é permitido — só {', '.join(ALLOWLIST_DSJOB)}.")
    if not ssh_configured():
        raise DsConsoleError("SSH do DataStage não configurado no servidor.")
    t0 = time.monotonic()
    gerenciador = await SEMAFORO_SSH(teto_sessoes, espera_max_s)  # cancelável — só fila, nada obtido ainda

    async def _com_a_vaga_obtida():
        async with gerenciador:
            # run_dsjob é síncrono/bloqueante (paramiko) — roda num thread
            # para não travar o loop async, mesmo padrão de
            # routers/lineage_isx.py.
            return await asyncio.to_thread(run_dsjob, comando, ds_project, job_name)

    tarefa = asyncio.ensure_future(_com_a_vaga_obtida())
    try:
        resultado = await asyncio.shield(tarefa)
    except asyncio.CancelledError:
        if not tarefa.cancelled():
            # Abandonada, não cancelada — segue rodando sozinha (é ela quem
            # libera o semáforo, no fim). Consome uma eventual exceção só
            # para não virar warning de "exception never retrieved".
            tarefa.add_done_callback(lambda t: None if t.cancelled() else t.exception())
        raise
    resultado["saida_redigida"] = _truncar(redigir(resultado.get("stdout") or ""))
    resultado["espera_ms"] = int((time.monotonic() - t0) * 1000) - resultado.get("duration_ms", 0)
    return resultado


# ── isx_extrair (F2b: export via istool + parse + gravação, mesma régua) ────
#
# Reaproveita 100% de `services.lineage_isx` (localizar/extrair/gravar/
# cabecalho/conta_linhas/mapa_tipos/config/montar) e o MESMO executor
# dedicado do router (`ISX_EXECUTOR`/`isx_no_executor`/`ISX_TETO_EXTRAIR_S`,
# importados de `routers.lineage_isx` acima) — "nenhum segundo pool"
# (spec F2b, item 1). Nunca reimplementa o export/parse/gravação.

_DS_JOB_TYPES = ("datastage", "")  # mesmo conjunto de routers/lineage_isx.py::_DS_JOB_TYPES
ORIGEM_AGENTE = "agente:datastage"  # sufixo em extracted_by — rastreia extrações feitas pelo agente
MAX_EXTRACOES_ISX = 2  # no máx. 2 extrações ISX por pergunta (spec F2b, item 5)


def isx_info_do_job(cur, pipeline_name: str, job_name: str) -> dict | None:
    """Mesma checagem de `routers.lineage_isx._info_do_job`, sem levantar
    `HTTPException` — devolve `None` quando o job não está mapeado no
    pipeline, o pipeline não tem projeto DataStage, ou o nó não é um job
    DataStage. Devolve os nomes na GRAFIA DO BANCO (case-insensitive na
    colação, mas o DataStage distingue caixa)."""
    info = lineage_isx.job_do_pipeline(cur, pipeline_name, job_name)
    if info is None or not info["ds_project"]:
        return None
    if str(info.get("job_type") or "").strip().lower() not in _DS_JOB_TYPES:
        return None
    return info


def mensagem_erro_lineage(e: Exception) -> str:
    """Traduz uma falha do `lineage_isx` (`ISXError`, `HTTPException`,
    genérica) numa mensagem nomeada para o chat — nunca vaza detalhe
    interno (`.interno`/traceback ficam só no log, como o router já faz
    em `_http()`)."""
    if isinstance(e, HTTPException):
        detalhe = e.detail
        return detalhe if isinstance(detalhe, str) else str(detalhe)
    status = getattr(e, "status", None)
    detail = getattr(e, "detail", None)
    if status is not None and detail is not None:
        return str(detail)
    return f"Falha inesperada na extração ISX ({type(e).__name__}) — tente de novo."


# ── dsx_consulta (F2b: só leitura dos .dsx já existentes) ───────────────────

DSX_TETO_S = 20  # parse de um .dsx grande num executor com prazo (critério 10 da F2b)
DSX_OPERACOES = ("listar_jobs", "listar_pastas", "buscar_campo", "extrair")


def _dsx_data_arquivo(diretorio_base: str, projeto: str) -> str | None:
    """Data de modificação do `.dsx` — toda resposta de `dsx_consulta` traz
    nome+data do arquivo (é um RETRATO, não o estado agora — critério 8)."""
    try:
        mtime = os.path.getmtime(os.path.join(diretorio_base, f"{projeto}.dsx"))
        return datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
    except OSError:
        return None


async def ferramenta_dsx_consulta(projeto: str, operacao: str, args: dict) -> dict:
    """Só leitura dos `.dsx` já existentes em `DSX_BASE_DIR` — NUNCA toca o
    servidor DataStage (critério 7 da F2b: sem SSH, sem `dsjob`, sem criar
    nem alterar arquivo). `projeto` já validado contra path traversal e
    contra "tem .dsx" por quem chama (`nome_dsx_valido`/`projeto_tem_dsx`).

    Roda num executor com teto — um `.dsx` grande não pode travar a rodada
    (critério 10). Como é só LEITURA de arquivo local (sem semáforo, sem
    sessão remota a proteger), `asyncio.wait_for` simples é seguro aqui:
    diferente do `dsjob`, não há recurso compartilhado que "vazaria" se a
    espera for abandonada — a thread órfã só termina de ler um arquivo."""
    if operacao not in DSX_OPERACOES:
        raise ValueError(f"Operação '{operacao}' não existe em dsx_consulta — "
                         f"use uma de: {', '.join(DSX_OPERACOES)}.")
    DSXEngine = _dsx_engine_cls()
    motor = DSXEngine()

    def _rodar():
        if operacao == "listar_jobs":
            return motor.listar_jobs(projeto)
        if operacao == "listar_pastas":
            return motor.listar_pastas(projeto)
        if operacao == "buscar_campo":
            termo = str(args.get("termo") or "").strip()
            tipos = args.get("tipos") if isinstance(args.get("tipos"), list) else None
            return motor.buscar_campo(
                projeto, termo, exato=bool(args.get("exato")), tipos=tipos,
                excluir=bool(args.get("excluir")), pasta=str(args.get("pasta") or ""))
        job_name = str(args.get("job_name") or "").strip()
        return motor.extrair(projeto, job_name)

    resultado = await asyncio.wait_for(asyncio.to_thread(_rodar), timeout=DSX_TETO_S)
    resultado = dict(resultado or {})
    resultado["dsx_arquivo"] = f"{projeto}.dsx"
    resultado["dsx_data"] = _dsx_data_arquivo(motor.diretorio_base, projeto)
    return resultado
