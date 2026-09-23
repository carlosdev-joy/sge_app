"""services/agentes.py — as funções puras do histórico (F4 da spec
docs/spec-agentes-datastage.md).

Sem banco, sem rede: aqui ficam as três decisões que dariam bug silencioso
se estivessem embutidas numa query.

  1. **`escapar_like`** — `%` e `_` digitados pelo usuário são LITERAIS na
     busca, não curingas. Sem isso, procurar `100%` no histórico traz tudo,
     e `job_x` casa com `jobax`/`job1x`. O `\\` tem de ser escapado
     PRIMEIRO, senão escaparíamos os escapes recém-inseridos.

  2. **`titulo_da_conversa`** — corta em unidades UTF-16, a largura real do
     `NVARCHAR(200)`. `mensagem[:200]` conta CARACTERES: 200 emojis são 200
     caracteres em Python e 400 unidades no SQL Server — estouraria a
     coluna. E o corte não pode partir um par substituto ao meio.

  3. **`ultimas_rodadas`** — a janela que volta ao gateway começa sempre
     numa PERGUNTA. Uma janela que comece por uma resposta deixa o modelo
     lendo o que ele disse sem saber o que foi perguntado.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

import pytest

if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()
os.environ.setdefault("MSSQL_CONN_STR", "__mock__")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))

from services import agentes as svc  # noqa: E402


# ═══════════ 1. escapar_like ═════════════════════════════════════════════

@pytest.mark.parametrize("termo,esperado", [
    ("100%", r"100\%"),
    ("job_x", r"job\_x"),
    ("a[b]", r"a\[b]"),
    (r"c:\temp", r"c:\\temp"),
    ("normal", "normal"),
    ("", ""),
])
def test_escapar_like(termo, esperado):
    assert svc.escapar_like(termo) == esperado


def test_escapar_like_trata_a_barra_antes_dos_curingas():
    r"""Ordem importa: escapando `%` antes de `\`, o `\` inserido pelo
    próprio escape viraria `\\%` e o LIKE leria um literal `\` seguido de
    curinga — exatamente o que se queria evitar."""
    assert svc.escapar_like(r"50\%") == r"50\\\%"


def test_escapar_like_nao_deixa_curinga_efetivo():
    """O ponto todo: depois de escapado, nenhum `%`/`_` sobra sem barra."""
    import re
    for termo in ("100%", "job_x", r"a\%b", "%%__"):
        saida = svc.escapar_like(termo)
        assert not re.search(r"(?<!\\)[%_]", saida), f"{termo!r} → {saida!r} tem curinga solto"


# ═══════════ 2. titulo_da_conversa (NVARCHAR conta UTF-16) ═══════════════

def test_titulo_curto_passa_inteiro():
    assert svc.titulo_da_conversa("o que o job X faz?") == "o que o job X faz?"


def test_titulo_corta_no_limite():
    assert len(svc.titulo_da_conversa("a" * 500)) == svc.TITULO_MAX


def test_titulo_com_emoji_nao_estoura_o_nvarchar():
    """Cada emoji é 1 caractere em Python e 2 unidades UTF-16 no banco.
    `mensagem[:200]` devolveria 200 caracteres = 400 unidades e o INSERT
    falharia (ou truncaria) na coluna NVARCHAR(200)."""
    titulo = svc.titulo_da_conversa("🙂" * 300)
    unidades = len(titulo.encode("utf-16-le", errors="surrogatepass")) // 2
    assert unidades <= svc.TITULO_MAX


def test_titulo_nao_parte_emoji_ao_meio():
    """Cortar no meio de um par substituto grava meio caractere — o banco
    aceita e a tela mostra o losango de erro."""
    titulo = svc.titulo_da_conversa("a" * (svc.TITULO_MAX - 1) + "🙂")
    # Se partisse, o decode com surrogatepass deixaria um substituto solto.
    assert all(not (0xD800 <= ord(c) <= 0xDFFF) for c in titulo)


def test_titulo_de_mensagem_vazia_nao_levanta():
    assert svc.titulo_da_conversa("") == ""
    assert svc.titulo_da_conversa("   ") == ""


# ═══════════ 3. ultimas_rodadas ══════════════════════════════════════════

def _conversa(n_rodadas: int) -> list[dict]:
    msgs = []
    for i in range(n_rodadas):
        msgs.append({"role": "user", "content": f"p{i}"})
        msgs.append({"role": "assistant", "content": f"r{i}"})
    return msgs


def test_historico_curto_volta_inteiro():
    h = _conversa(3)
    assert svc.ultimas_rodadas(h) == h


def test_historico_longo_e_cortado_nas_ultimas_rodadas():
    h = _conversa(20)
    janela = svc.ultimas_rodadas(h, max_rodadas=12)
    assert len(janela) == 24
    assert janela[0] == {"role": "user", "content": "p8"}      # 20 - 12
    assert janela[-1] == {"role": "assistant", "content": "r19"}


def test_janela_sempre_comeca_numa_pergunta():
    """Com um número ÍMPAR de mensagens (ex.: a última rodada ainda sem
    resposta gravada), o corte cru cairia numa resposta de assistente."""
    h = _conversa(20)
    h.append({"role": "user", "content": "p20"})  # 41 mensagens
    janela = svc.ultimas_rodadas(h, max_rodadas=12)
    assert janela[0]["role"] == "user"
    assert janela[-1] == {"role": "user", "content": "p20"}


def test_ultimas_rodadas_com_zero_nao_manda_nada():
    assert svc.ultimas_rodadas(_conversa(5), max_rodadas=0) == []


def test_ultimas_rodadas_nao_muda_a_lista_original():
    h = _conversa(20)
    copia = [dict(m) for m in h]
    svc.ultimas_rodadas(h)
    assert h == copia


def test_o_teto_padrao_e_12_rodadas():
    """A spec fixa 12 — se mudar, é decisão, não acidente."""
    assert svc.MAX_RODADAS_HISTORICO == 12
    assert len(svc.ultimas_rodadas(_conversa(50))) == 24


def test_retencao_de_30_dias_e_a_da_spec():
    assert svc.RETENCAO_CONVERSAS_DIAS == 30
