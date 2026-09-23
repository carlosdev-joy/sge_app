"""Histórico de conversas no front (F4 da spec docs/spec-agentes-datastage.md).

Leitura do fonte TS por regex, como `test_agentes_f3_front.py` — o repo não
tem runtime de teste para React.

O que se prende, e por quê:

  1. **A busca é do SERVIDOR** (`?q=`), não filtro do que já veio. A lista
     traz no máximo as 100 conversas mais recentes de 30 dias; filtrar só o
     que está na tela daria "não encontrei" para uma conversa que existe.

  2. **A data aparece nas respostas retomadas** (critério 3): o que o agente
     disse há três semanas pode ter envelhecido, e o operador decide com
     essa informação à vista. Só nas do ASSISTENTE — a pergunta do usuário
     não "vence".

  3. **`conversa_expirada` tem texto próprio.** Quem guardou um link de mais
     de 30 dias merece "essa conversa passou dos 30 dias", não "erro ao
     carregar" — é o caso NORMAL do prazo, não uma falha.

  4. **O prazo do front espelha o do backend.** Duas constantes que precisam
     concordar; se divergirem, a tela promete um prazo que a API não cumpre.
"""
from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
FRONT = RAIZ / "ui-react" / "src"

HISTORICO = FRONT / "components" / "agentes" / "HistoricoConversas.tsx"
PAGINA = FRONT / "pages" / "Agentes.tsx"
CHAT = FRONT / "components" / "agentes" / "ChatAgente.tsx"
LIB = FRONT / "lib" / "agentes.ts"


def ler(p: Path) -> str:
    assert p.exists(), f"arquivo da F4 não existe: {p.relative_to(RAIZ)}"
    return p.read_text(encoding="utf-8")


def codigo(p: Path) -> str:
    """O fonte sem comentários — as regras falam do que o componente FAZ."""
    fonte = re.sub(r"/\*.*?\*/", " ", ler(p), flags=re.S)
    return "\n".join(l for l in fonte.splitlines() if not l.strip().startswith("//"))


# ═══════════ 1. busca no servidor ════════════════════════════════════════

def test_busca_vai_ao_servidor_com_q():
    fonte = codigo(HISTORICO)
    assert "/agentes/conversas?" in fonte
    assert re.search(r"p\.set\('q',\s*busca\.trim\(\)\)", fonte), \
        "o termo precisa ir na query `?q=`, não filtrar no cliente"
    # O termo entra na queryKey: cada busca é uma consulta própria e cacheada.
    assert re.search(r"queryKey:\s*\['agentes-conversas',\s*agenteId,\s*busca\.trim\(\)\]", fonte)


def test_busca_nao_filtra_a_lista_no_cliente():
    """Um `.filter(...)` sobre `conversas` mentiria: a lista é limitada a
    100 itens pelo servidor."""
    fonte = codigo(HISTORICO)
    assert not re.search(r"conversas\s*\.\s*filter\(", fonte), \
        "a busca é do servidor; filtrar o que já veio esconde resultado real"


def test_lista_pede_so_as_conversas_do_agente_aberto():
    assert "agente: agenteId" in codigo(HISTORICO)


# ═══════════ 2. a data das respostas retomadas (critério 3) ══════════════

def test_chat_mostra_quando_a_resposta_e_antiga():
    fonte = codigo(CHAT)
    assert "{m.em &&" in fonte, "a mensagem retomada precisa mostrar a data"
    assert "quando(m.em)" in fonte
    assert "data-agentes-quando" in fonte


def test_a_data_so_vai_nas_respostas_do_assistente():
    """A pergunta do usuário não envelhece — quem pode ter virado notícia
    velha é a RESPOSTA do agente."""
    fonte = codigo(PAGINA)
    assert re.search(r"em:\s*m\.papel\s*===\s*'assistant'\s*\?\s*m\.criada_em\s*:\s*undefined", fonte), \
        "só a mensagem do assistente carrega a data"


def test_helper_de_data_trata_iso_do_sql_server():
    """`2026-09-22 14:30:00` (espaço, como o `_iso` do backend devolve) é
    Invalid Date no Safari sem a troca por `T`."""
    fonte = codigo(LIB)
    assert "export function quando(" in fonte
    assert "iso.replace(' ', 'T')" in fonte
    assert "Number.isNaN(d.getTime())" in fonte, "data inválida não pode virar 'Invalid Date' na tela"


# ═══════════ 3. conversa expirada tem texto próprio ══════════════════════

def test_conversa_expirada_nao_vira_erro_generico():
    fonte = codigo(PAGINA)
    assert "codigoDoErro(e) === 'conversa_expirada'" in fonte, \
        "a tela decide pelo `code`, não pelo texto do erro"
    assert re.search(r"passou dos \{?RETENCAO_CONVERSAS_DIAS\}? dias|passou dos 30 dias", fonte), \
        "o usuário precisa saber que foi o prazo, não uma falha"


def test_retomar_descarta_resposta_fora_de_ordem():
    """Mesma trava do envio: clicar em duas conversas seguidas não pode
    deixar a segunda ser sobrescrita pela primeira que chegar."""
    fonte = codigo(PAGINA)
    bloco = fonte.split("async function retomar(")[1].split("function novaConversa")[0]
    assert "++pedidoRef.current" in bloco
    assert bloco.count("pedidoRef.current !== meuPedido") >= 2, \
        "checar o pedido no sucesso E no catch"


# ═══════════ 4. o prazo do front espelha o do backend ════════════════════

def test_retencao_do_front_bate_com_a_do_servico():
    from_front = re.search(r"RETENCAO_CONVERSAS_DIAS\s*=\s*(\d+)", ler(LIB))
    assert from_front, "a constante precisa existir no front"
    servico = (RAIZ / "api" / "services" / "agentes.py").read_text(encoding="utf-8")
    from_back = re.search(r"^RETENCAO_CONVERSAS_DIAS\s*=\s*(\d+)", servico, re.M)
    assert from_back, "a constante precisa existir no serviço"
    assert from_front.group(1) == from_back.group(1) == "30", \
        "front e backend precisam prometer o mesmo prazo"


# ═══════════ 5. acessibilidade e tokens (mesma régua da F3) ══════════════

def test_historico_tem_rotulos_acessiveis():
    fonte = codigo(HISTORICO)
    assert 'aria-label="Histórico de conversas"' in fonte
    assert 'aria-label="Buscar nas conversas"' in fonte
    assert 'aria-label="Fechar histórico"' in fonte
    # A lista muda ao buscar — o leitor de tela precisa saber.
    assert 'aria-live="polite"' in fonte
    # A conversa aberta é anunciada, não só destacada por cor.
    assert "aria-current=" in fonte


_FAMILIAS = ("slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|"
             "teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose|white|black")
_COR_UTIL = re.compile(rf"(?<!dark:)\b(bg|text|border|border-l|ring|fill)-(?:{_FAMILIAS})"
                       r"(?:-\d{2,3})?\b")


def test_historico_nao_usa_cor_fora_dos_tokens():
    achados = [m.group(0) for m in _COR_UTIL.finditer(codigo(HISTORICO))]
    assert not achados, f"cor fora dos tokens: {sorted(set(achados))}"


def test_historico_nao_acrescenta_overflow_hidden():
    """Mesma lição do Caixa Seguro: o painel rola na própria caixa."""
    assert "overflow-hidden" not in codigo(HISTORICO)


# ═══════════ 6. quem invalida o pedido limpa o estado do outro ═══════════
#
# Achado BLOQUEANTE da revisão adversarial da F4. `enviar`, `retomar` e
# `novaConversa` compartilham o mesmo `pedidoRef`: incrementá-lo invalida a
# resposta em voo dos outros — e o `finally` deles NÃO roda, porque checa
# `pedidoRef.current === meuPedido`. Quem incrementa tem de limpar o estado
# de quem invalidou, senão a flag fica presa:
#   • retomar sem `setEnviando(false)` → `enviando` preso em `true`: o campo
#     e o Enter param, a bolha "está consultando…" congela, e a conversa
#     recém-retomada NUNCA pode ser continuada (a função central da F4);
#   • enviar sem `setRetomando(false)` → `retomando` preso: todo clique
#     futuro no histórico é descartado em silêncio (`if (retomando) return`).
# `novaConversa` já fazia certo; `retomar` copiou o incremento e não a
# compensação.

def _bloco(fonte: str, inicio: str, fim: str) -> str:
    return fonte.split(inicio)[1].split(fim)[0]


def test_retomar_libera_o_envio_em_voo():
    bloco = _bloco(codigo(PAGINA), "async function retomar(", "function novaConversa")
    assert "++pedidoRef.current" in bloco
    assert "setEnviando(false)" in bloco, \
        "retomar invalida o enviar em voo — sem este reset o chat trava para sempre"


def test_enviar_libera_a_retomada_em_voo():
    bloco = _bloco(codigo(PAGINA), "async function enviar(", "async function retomar(")
    assert "++pedidoRef.current" in bloco
    assert "setRetomando(false)" in bloco, \
        "enviar invalida a retomada em voo — sem este reset o histórico para de responder"


def test_nova_conversa_continua_limpando_tudo():
    """Não-regressão: era o único que já fazia certo."""
    bloco = _bloco(codigo(PAGINA), "function novaConversa()", "const plotavel")
    assert "++pedidoRef.current" in bloco or "pedidoRef.current++" in bloco
    assert "setEnviando(false)" in bloco
    assert "setRetomando(false)" in bloco or "setRetomando" not in codigo(PAGINA)


def test_painel_nao_empurra_o_chat_em_tela_estreita():
    """Abaixo de `sm` o contêiner é flex-COLUNA: um aside `shrink-0` sem
    teto de altura empurra o chat (`flex-1`, basis 0) para altura zero."""
    fonte = codigo(HISTORICO)
    assert "sm:shrink-0" in fonte, "o shrink-0 não pode valer no empilhado"
    assert re.search(r"max-h-\S+\s+sm:max-h-none", fonte), \
        "no empilhado o painel precisa de teto próprio e rolar por dentro"
