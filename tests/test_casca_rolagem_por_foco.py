"""A página não pode "ir para baixo" perdendo a referência da tela (captura do usuário em
2026-09-07: Admin › Utilitários com cabeçalho e topo do menu fora da tela, rodapé vazio e
sem barra para voltar; nas outras telas não acontecia).

Causa medida no DEV (Chromium headless): o input `sr-only` do Switch "Guardar cópia de
segurança" é `position: absolute` (é o que `sr-only` faz). Sem NENHUM ancestral
posicionado, ele se ancora no documento na posição em que estaria (y = 1141 numa janela
de 700 px) e estica a área rolável da página inteira em 442 px; a casca é
`overflow-hidden`, mas o documento passa a rolar — e a rolagem do <main> encadeia para
ele no fim da aba. Nas outras telas os Checkbox/Switch ficam acima da dobra ou dentro
de algo `relative`, por isso "diferente das demais".

Correção em duas camadas: `relative` nos invólucros dos inputs sr-only (Checkbox,
Switch, RadioItem, seletor de arquivo do Enviar) e `relative` na casca, que vira o
bloco de contenção de qualquer absolute perdido (a `overflow-hidden` da casca então o
corta em vez de o documento crescer). Anti-drift abaixo.
"""
from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
SRC = RAIZ / "ui-react/src"
CASCA = SRC / "components/layout/AppShellV2.tsx"


def _sem_comentarios(texto: str) -> str:
    return re.sub(r"\{/\*.*?\*/\}|//[^\n]*|/\*.*?\*/", "", texto, flags=re.DOTALL)


def test_casca_e_o_bloco_de_contencao_dos_absolutes_perdidos():
    fonte = _sem_comentarios(CASCA.read_text(encoding="utf-8"))
    raiz = re.search(r'<div className="([^"]+)">\s*<HeaderV2', fonte)
    assert raiz, "a estrutura da casca mudou — confira o bloco de contenção"
    classes = raiz.group(1).split()
    assert {"relative", "h-screen", "overflow-hidden"} <= set(classes), classes
    assert "overflow-clip" not in fonte      # clip faria o transbordo rolar o documento inteiro


_SR_ONLY_CONHECIDOS = {
    # arquivo → quantas ocorrências de `sr-only`, todas dentro de um invólucro posicionado
    "components/ui/Checkbox.tsx": 1,
    "components/ui/Switch.tsx": 1,
    "components/ui/RadioGroup.tsx": 1,
    "components/utilitarios/FormEnviarArquivo.tsx": 1,
    "components/utilitarios/BarraTransferencia.tsx": 1,
    "components/utilitarios/ModalEnvioArquivo.tsx": 1,
}


def test_todo_sr_only_esta_na_lista_conhecida():
    """`sr-only` = `position: absolute`. Todo uso novo entra aqui DEPOIS de garantir um
    ancestral posicionado (`relative`/`fixed`) — senão o elemento escapa para o documento
    quando fica abaixo da dobra e a página inteira passa a rolar."""
    achados: dict[str, int] = {}
    for arquivo in sorted(SRC.rglob("*.tsx")):
        fonte = _sem_comentarios(arquivo.read_text(encoding="utf-8"))
        n = len(re.findall(r"className=\"[^\"]*\bsr-only\b", fonte))
        if n:
            achados[str(arquivo.relative_to(SRC))] = n
    assert achados == _SR_ONLY_CONHECIDOS, (
        f"uso de sr-only fora da lista conhecida: {achados} — confira o invólucro posicionado e atualize a lista")


def test_os_quatro_invólucros_conhecidos():
    esperados = {
        "components/ui/Checkbox.tsx": "relative inline-flex items-center gap-2 select-none",
        "components/ui/Switch.tsx": "relative inline-flex items-center gap-2 select-none",
        "components/ui/RadioGroup.tsx": "relative inline-flex items-center gap-2 select-none",
        "components/utilitarios/FormEnviarArquivo.tsx": "relative flex flex-col gap-1",
    }
    for rel, trecho in esperados.items():
        assert trecho in (SRC / rel).read_text(encoding="utf-8"), rel


def test_regioes_aria_live_sr_only_vivem_em_ancestral_posicionado():
    """As regiões `sr-only` de leitor de tela: a da BarraTransferencia vive no FLUXO da
    página (não na faixa fixa) e por isso o invólucro é `relative`; a do ModalEnvioArquivo
    fica dentro do Modal (`fixed`). Se alguém mover uma para fora, este teste avisa."""
    barra = _sem_comentarios((SRC / "components/utilitarios/BarraTransferencia.tsx").read_text(encoding="utf-8"))
    invólucro = re.search(r'<div data-transferencia=\{[^}]+\} className="([^"]+)">\s*<div aria-live="polite" className="sr-only"', barra)
    assert invólucro and "relative" in invólucro.group(1).split(), "a região sr-only da faixa precisa de um pai relative"
    modal = _sem_comentarios((SRC / "components/utilitarios/ModalEnvioArquivo.tsx").read_text(encoding="utf-8"))
    assert modal.index("<Modal ") < modal.index('className="sr-only"')
