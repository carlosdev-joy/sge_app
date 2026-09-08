"""Casca da aplicação (AppShellV2): a página não pode "ir para baixo" quando um campo
ganha foco (captura do usuário em 2026-09-07: Admin › Utilitários com o cabeçalho e o
topo do menu fora da tela e o rodapé vazio).

Causa: `overflow: hidden` ainda é rolável por programa — `autoFocus` (caminho da raiz ao
editar, no Admin) e o `focus()` do navegador de pastas fazem o navegador rolar a casca
inteira, e não há barra para voltar. `overflow: clip` não rola nunca; o único contêiner
rolável fica sendo o <main>. Anti-drift: as duas classes nos dois contêineres da casca,
`overflow-hidden` mantido como reserva (navegador sem `clip` ignora a declaração), e o
foco devolvido pelo navegador de pastas com `preventScroll`.
"""
from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
CASCA = RAIZ / "ui-react/src/components/layout/AppShellV2.tsx"
NAVEGADOR = RAIZ / "ui-react/src/components/utilitarios/NavegadorPastas.tsx"


def _sem_comentarios(texto: str) -> str:
    return re.sub(r"//[^\n]*|/\*.*?\*/", "", texto, flags=re.DOTALL)


def test_casca_usa_overflow_clip_nos_dois_conteineres_com_hidden_de_reserva():
    fonte = _sem_comentarios(CASCA.read_text(encoding="utf-8"))
    raiz = re.search(r'className="flex flex-col h-screen bg-canvas ([^"]+)"', fonte)
    meio = re.search(r'className="flex flex-1 ([^"]+)"', fonte)
    assert raiz and meio, "a estrutura da casca mudou — ajuste o teste e confira a rolagem por foco"
    for classes in (raiz.group(1), meio.group(1)):
        lista = classes.split()
        assert "overflow-clip" in lista and "overflow-hidden" in lista, classes
        # a reserva vem ANTES: o Tailwind emite .overflow-clip depois de .overflow-hidden,
        # então quem entende `clip` fica com ele; a ordem no className deixa isso legível
        assert lista.index("overflow-hidden") < lista.index("overflow-clip"), classes
    # o <main> continua sendo o único que rola
    assert 'className="flex-1 overflow-y-auto"' in fonte


def test_navegador_de_pastas_devolve_o_foco_sem_rolar():
    fonte = _sem_comentarios(NAVEGADOR.read_text(encoding="utf-8"))
    assert "el.focus({ preventScroll: true })" in fonte
    assert not re.search(r"\.focus\(\)", fonte), "focus() sem preventScroll rola o <main> a cada listagem"


def test_tailwind_gera_overflow_clip_depois_de_overflow_hidden():
    """A reserva só funciona se `.overflow-clip` vier DEPOIS de `.overflow-hidden` no CSS
    gerado — é a ordem do plugin do Tailwind 3.4; o teste prende isso na dist."""
    css = sorted((RAIZ / "ui-react/dist/assets").glob("*.css"))
    if not css:
        return  # dist ainda não construída neste checkout
    texto = css[-1].read_text(encoding="utf-8")
    i_hidden, i_clip = texto.find(".overflow-hidden{"), texto.find(".overflow-clip{")
    assert i_hidden != -1 and i_clip != -1 and i_hidden < i_clip
    assert "overflow:clip" in texto
