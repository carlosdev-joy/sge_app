"""Versões do bloco de DOMÍNIO do prompt dos agentes (A1 da spec
docs/spec-agentes-admin.md §3.2–§3.3).

O prompt é montado em `services/agentes._prompt_sistema`: contexto da conversa
+ DOMÍNIO + blocos fixos. Este módulo cuida só do domínio que o admin edita:

  • **Versões só acrescentam** (`dbo.etl_agente_prompt`, migration 120):
    gravar cria a versão seguinte; restaurar grava o texto antigo como versão
    nova. A ativa é a de maior número; sem linha, vale o padrão do código
    (`PROMPT_DOMINIO_PADRAO`, "versão 0").
  • **Sem cache**: a versão ativa é lida a cada pergunta, na conexão que já lê
    a config. A API roda com 2 workers — um cache por processo faria cada um
    ver uma versão diferente por até N segundos depois de o admin gravar.
  • **Validação** antes de gravar: tamanho, motivo, marcadores do protocolo e
    valor com cara de credencial (o texto vai ao gateway de IA a cada
    pergunta).
"""
from __future__ import annotations

import hashlib
import logging
import re

from services import agentes as svc
from services.ssh_arquivos import utf16_len

logger = logging.getLogger(__name__)

TEXTO_MAX = 20_000
MOTIVO_MIN, MOTIVO_MAX = 3, 200  # unidades UTF-16 — o que o NVARCHAR(200) conta
VERSAO_MAX = 2**31 - 1  # `versao INT`: acima disso o pyodbc nem converte (OverflowError → 500)

# O domínio não pode IMITAR o protocolo: esses trechos são do bloco de
# ferramenta e do de propostas/aprendizados, que o código monta DEPOIS do
# domínio. Um domínio com eles confundiria o modelo sobre qual formato vale.
# O padrão do código não tem nenhum (tests/test_agentes_prompt_blocos.py).
MARCADORES_RESERVADOS = ('"ferramenta":', '"propostas":', '"aprendizados":', "<ferramenta", "</ferramenta",
                         "<aprendizados")

# ── credencial no texto (§3.3, regra testada na 3ª revisão da spec) ─────────
#
# NÃO é o `af.redigir()`: ele casa `senha`/`token`/`secret`/`Encrypted` em
# qualquer lugar da linha e recusaria texto normal de prompt ("nunca peça a
# senha", "parâmetros Encrypted", o stage `TokenizerTransform`). Aqui só conta
# um VALOR: palavra-chave + `:`/`=` + um valor de 6+ caracteres com dígito ou
# símbolo — ou um formato conhecido de chave/token.
#
# A palavra-chave só não pode vir colada a letra/dígito — `_` antes vale, e é
# isso que pega `DB_PASSWORD`/`client_secret`/`access_token` SEM um grupo de
# prefixo. A 1ª versão tinha `(?:[a-z0-9]+_)*` antes da chave: com o
# lookbehind, cada `_` de um texto como "a_a_a_…" virava um novo começo que
# percorria o resto — quadrático, ~10 s de CPU para 20.000 caracteres dentro
# do event loop (revisão adversarial da A1). Agora é linear.
_CHAVE = r"(?:senha|password|passwd|pwd|secret|token|api[_-]?key)"
_RE_CHAVE_VALOR = re.compile(
    r"(?<![a-z0-9])" + _CHAVE + r"(?![a-z])"
    # Espaço que NÃO é quebra de linha (`[^\S\r\n]`): inclui o U+00A0 que o
    # Word/Outlook/Teams põe ao colar — com `[ \t]` ele escapava (2ª revisão).
    r"[\"']?[^\S\r\n]*[:=][^\S\r\n]*[\"']?"
    r"(?P<valor>[^\s\"',;}]{6,})", re.I)
# Referência ou marcador, não segredo: `#PS_X.Y#`, `$PS_X.Y`, `<valor>`,
# `****`, início de JSON. Formas ESTRITAS — `$enha123!` e `#abc123` (sem o `#`
# de fechamento) não são referência e continuam recusados.
_RE_VALOR_REFERENCIA = re.compile(r"#[A-Za-z0-9_.]+#|\$[A-Za-z_][A-Za-z0-9_.]*|<[^>]*>|\*+|[{\[].*")
_RE_FORMATOS = (
    re.compile(r"(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{20,}"),       # sk-…, sk-ant-api03-…, sk-proj-…
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{20,}"),
    re.compile(r"-----BEGIN [A-Z ]*KEY-----"),
)


def tem_segredo(texto: str) -> bool:
    if any(r.search(texto) for r in _RE_FORMATOS):
        return True
    for m in _RE_CHAVE_VALOR.finditer(texto):
        v = m.group("valor")
        if _RE_VALOR_REFERENCIA.fullmatch(v):
            continue
        if re.search(r"[^A-Za-z]", v):  # dígito ou símbolo
            return True
    return False


class PromptInvalido(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


class PromptMudou(Exception):
    """A versão ativa não é a que o admin tinha na tela (outro admin gravou)."""

    def __init__(self, atual: int):
        super().__init__(f"versão ativa é {atual}")
        self.atual = atual


class VersaoNaoEncontrada(LookupError):
    pass


def validar_texto(texto) -> str:
    t = str(texto or "").strip() if isinstance(texto, str) or texto is None else None
    if t is None:
        raise PromptInvalido("prompt_invalido", "o texto do prompt deve ser uma string")
    if not t:
        raise PromptInvalido("prompt_vazio", "o texto do prompt não pode ficar vazio")
    if len(t) > TEXTO_MAX:
        raise PromptInvalido("prompt_grande", f"o texto do prompt passa de {TEXTO_MAX} caracteres")
    achados = [m for m in MARCADORES_RESERVADOS if m in t]
    if achados:
        raise PromptInvalido("prompt_com_marcador",
                             "o texto usa trechos reservados do protocolo, que o Orquestra monta sozinho: "
                             + ", ".join(achados))
    if tem_segredo(t):
        raise PromptInvalido("prompt_com_segredo",
                             "o texto parece conter uma credencial (senha, token ou chave) — "
                             "o prompt vai ao gateway de IA a cada pergunta; remova o valor")
    return t


def validar_motivo(motivo) -> str:
    m = str(motivo or "").strip() if isinstance(motivo, str) or motivo is None else ""
    if not (MOTIVO_MIN <= utf16_len(m) <= MOTIVO_MAX):
        raise PromptInvalido("motivo_obrigatorio",
                             f"informe o motivo da mudança ({MOTIVO_MIN} a {MOTIVO_MAX} caracteres)")
    return m


def validar_versao(v, campo: str = "versao_base") -> int:
    if isinstance(v, bool) or not isinstance(v, int) or not (0 <= v <= VERSAO_MAX):
        raise PromptInvalido(f"{campo}_invalida", f"{campo} deve ser um inteiro entre 0 e {VERSAO_MAX}")
    return v


def hash_do_texto(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()[:12]


def padrao(agente_id: str) -> str:
    """Aparado, como qualquer texto gravado (`validar_texto`): assim a versão 0
    e a restauração dela têm o MESMO hash e o mesmo tamanho."""
    return svc.PROMPT_DOMINIO_PADRAO[agente_id].strip()


def tem_padrao(agente_id: str) -> bool:
    return agente_id in svc.PROMPT_DOMINIO_PADRAO


# ── leitura ─────────────────────────────────────────────────────────────────

_COLS = "versao, texto, motivo, origem_versao, criado_em, criado_por"


def _linha(r) -> dict:
    return {"versao": int(r[0]), "texto": r[1], "motivo": r[2],
            "origem_versao": int(r[3]) if r[3] is not None else None,
            "criado_em": r[4], "criado_por": r[5]}


def versao_ativa(cur, agente_id: str) -> dict | None:
    cur.execute(f"SELECT TOP 1 {_COLS} FROM dbo.etl_agente_prompt WHERE agente_id = ? ORDER BY versao DESC",
                [agente_id])
    r = cur.fetchone()
    return _linha(r) if r else None


def dominio_em_uso(cur, agente_id: str) -> dict:
    """O domínio que ESTA pergunta vai usar: `{versao, texto, hash}`.

    Falha de leitura (tabela ainda sem a 120, erro do driver) NÃO derruba o
    chat de um agente que tem padrão no código — usa o padrão e registra
    `warning`. Agente sem padrão (Fase B) não tem para onde cair: a exceção
    sobe e o chamador responde 503."""
    try:
        v = versao_ativa(cur, agente_id)
    except Exception:  # noqa: BLE001
        if not tem_padrao(agente_id):
            raise
        logger.warning("agentes: leitura do prompt de %s falhou — usando o padrão do código", agente_id,
                       exc_info=True)
        v = None
    if v is None:
        texto, versao = padrao(agente_id), 0
    else:
        texto, versao = v["texto"], v["versao"]
    return {"versao": versao, "texto": texto, "hash": hash_do_texto(texto)}


def listar_versoes(cur, agente_id: str) -> list[dict]:
    cur.execute(f"SELECT {_COLS} FROM dbo.etl_agente_prompt WHERE agente_id = ? ORDER BY versao DESC",
                [agente_id])
    return [_linha(r) for r in cur.fetchall()]


def texto_da_versao(cur, agente_id: str, versao: int) -> dict:
    if versao == 0:
        if not tem_padrao(agente_id):
            raise VersaoNaoEncontrada(versao)
        return {"versao": 0, "texto": padrao(agente_id), "motivo": "padrão do código",
                "origem_versao": None, "criado_em": None, "criado_por": None}
    cur.execute(f"SELECT {_COLS} FROM dbo.etl_agente_prompt WHERE agente_id = ? AND versao = ?",
                [agente_id, versao])
    r = cur.fetchone()
    if not r:
        raise VersaoNaoEncontrada(versao)
    return _linha(r)


# ── gravação ────────────────────────────────────────────────────────────────

def _eh_violacao_unique(e: Exception) -> bool:
    msg = str(e)
    return any(x in msg for x in ("2627", "2601", "UQ_etl_agente_prompt_versao"))


def gravar_versao(conn, cur, *, agente_id: str, texto: str, motivo: str, matricula: str,
                  versao_base: int, origem_versao: int | None = None) -> dict:
    """Grava a versão seguinte à ATIVA, se a ativa ainda for `versao_base`.

    Duas proteções contra dois admins gravando juntos: a comparação com
    `versao_base` (quem tinha a versão velha na tela) e, na corrida entre a
    leitura e o INSERT, o UNIQUE (agente_id, versao) — os dois viram 409."""
    atual = versao_ativa(cur, agente_id)
    n_atual = atual["versao"] if atual else 0
    if n_atual != versao_base:
        raise PromptMudou(n_atual)
    try:
        cur.execute(
            "INSERT INTO dbo.etl_agente_prompt (agente_id, versao, texto, motivo, origem_versao, criado_por) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [agente_id, n_atual + 1, texto, motivo, origem_versao, matricula])
        conn.commit()
    except Exception as e:  # noqa: BLE001
        try:
            conn.rollback()
        except Exception:  # noqa: BLE001
            pass
        if _eh_violacao_unique(e):
            novo = versao_ativa(cur, agente_id)
            raise PromptMudou(novo["versao"] if novo else n_atual) from e
        raise
    return versao_ativa(cur, agente_id)
