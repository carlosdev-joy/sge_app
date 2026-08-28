"""O gesto de abrir o conteúdo do chamado é ANUNCIADO na tela.

Pedido do dono do produto ao usar o kanban:

    "precisamos deixar de alguma forma clara sobre o modal no orquestra para
     visualizar os detalhes, para mim não esta intuitivo ainda."

A rota `GET /chamados/{sys_id}/detalhe` e o modal existem desde a F4. O que
faltava era a PROMESSA: a primeira versão abria o modal pelo título, com
`hover:underline` e um `title`. Quem não passasse o mouse — ou estivesse no
toque, ou usasse teclado — não tinha como saber que havia o que ver. Affordance
que só existe no hover é affordance que não existe.

O que estes testes prendem, nas duas telas onde o chamado aparece:

  * **kanban** (`CabecalhoCard`) — um botão VISÍVEL, com a palavra "detalhes" e
    o ícone junto; clicar nele abre; o título continua abrindo (alvo maior de
    quem já descobriu); e o link do ServiceNow continua existindo, separado e
    dito, para o gesto NÃO se confundir com "sair da tela".
  * **painel** (`ListaDoBloco`) — o número abre o detalhe AQUI. Antes ele era
    âncora para o ServiceNow: quem clicava para conferir um número do painel
    perdia o contexto inteiro numa aba nova.

⚠️ ESTE ARQUIVO RENDERIZA E CLICA. Procurar a palavra "detalhes" no `.tsx`
provaria só que ela foi digitada — não que aparece, nem que clicar abre coisa
alguma. Foi exatamente assim que um teste desta mesma spec passou VERDE com o
defeito de pé (ver `test_kanban_rodape_card.py`).

Sem Node ou sem `node_modules` a suíte SALTA em vez de falhar.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
HARNESS = RAIZ / "tests" / "js" / "detalhe_gesto_harness.cjs"
SUCRASE = RAIZ / "ui-react" / "node_modules" / "sucrase"

CABECALHOS = ["cabecalho", "cabecalho_sem_url", "cabecalho_sem_titulo"]
LISTAS = ["lista", "lista_resolvidos"]


def _node() -> str | None:
    caminho = shutil.which("node")
    if not caminho or not SUCRASE.is_dir():
        return None
    try:
        v = subprocess.run([caminho, "-v"], capture_output=True, text=True,
                           timeout=30).stdout.strip()
        return caminho if int(v.lstrip("v").split(".")[0]) >= 18 else None
    except Exception:      # noqa: BLE001 — sonda de ambiente degrada em salto
        return None


@pytest.fixture(scope="module")
def cen() -> dict:
    node = _node()
    if node is None:
        pytest.skip("front não instalado nesta máquina")
    r = subprocess.run([node, str(HARNESS)], capture_output=True, text=True,
                       cwd=str(RAIZ), timeout=120)
    assert r.returncode == 0, f"bancada do front falhou:\n{r.stderr}"
    return json.loads(r.stdout)


# ═══════════ 1. o kanban: a promessa está na tela ═══════════════════════════

@pytest.mark.parametrize("cenario", CABECALHOS)
def test_o_gesto_e_visivel_sem_passar_o_mouse(cen: dict, cenario: str) -> None:
    """A palavra "detalhes" é RENDERIZADA, não escondida atrás do hover."""
    c = cen[cenario]
    assert c["temBotao"] is True
    assert "detalhes" in c["texto"], "o texto tem de aparecer na tela"
    assert c["botaoAchadoPeloTexto"] is True


@pytest.mark.parametrize("cenario", CABECALHOS)
def test_o_gesto_tem_icone_e_palavra(cen: dict, cenario: str) -> None:
    """Ícone sozinho vira adivinhação: uma lupa pode ser buscar, ampliar ou
    inspecionar, e quem chega na tela não deveria testar para descobrir."""
    assert cen[cenario]["iconeDoBotao"] is True, "o ícone acompanha a palavra"


@pytest.mark.parametrize("cenario", CABECALHOS)
def test_clicar_no_gesto_abre_o_detalhe(cen: dict, cenario: str) -> None:
    """Anunciar sem abrir seria pior que não anunciar."""
    assert cen[cenario]["abreNoBotao"] is True


@pytest.mark.parametrize("cenario", CABECALHOS)
def test_o_titulo_continua_abrindo(cen: dict, cenario: str) -> None:
    """Quem já descobriu o gesto tem um alvo maior; o botão é para quem não."""
    assert cen[cenario]["abreNoTitulo"] is True


@pytest.mark.parametrize("cenario", CABECALHOS)
def test_a_ajuda_diz_o_que_sera_aberto(cen: dict, cenario: str) -> None:
    """"detalhes" de quê? O `title` nomeia o conteúdo — descrição, notas e
    anexos — em vez de deixar a descoberta por conta do clique."""
    ajuda = cen[cenario]["ajudaDoBotao"]
    assert "descrição" in ajuda and "notas" in ajuda and "anexos" in ajuda


# ═══════════ 2. abrir AQUI ≠ sair para o ServiceNow ═════════════════════════

def test_o_link_do_servicenow_continua_e_e_link_de_verdade(cen: dict) -> None:
    """Os dois gestos ficam lado a lado e a diferença é DITA. Se o link
    externo sumisse, o botão novo teria custado uma função existente."""
    ext = cen["cabecalho"]["linkExterno"]
    assert ext is not None
    assert ext["tag"] == "a", "âncora de verdade: abre em aba, copia, favorita"
    assert ext["target"] == "_blank"
    assert "noopener" in (ext["rel"] or ""), "aba nova sem acesso ao opener"
    assert "ServiceNow" in ext["title"], "a ajuda distingue um gesto do outro"
    assert ext["icone"] is True


def test_chamado_sem_url_nao_ganha_link_morto(cen: dict) -> None:
    """Âncora sem `href` parece clicável e não faz nada — pior que ausência."""
    assert cen["cabecalho_sem_url"]["temLinkExterno"] is False
    assert cen["cabecalho_sem_url"]["temBotao"] is True, "o detalhe não depende"


# ═══════════ 3. o painel: conferir um número sem perder a tela ══════════════

@pytest.mark.parametrize("cenario", LISTAS)
def test_o_numero_da_lista_abre_o_detalhe(cen: dict, cenario: str) -> None:
    """A pergunta de quem clica num número do painel é "o que é este
    chamado?" — e ir a outra aba para responder custa o contexto inteiro."""
    c = cen[cenario]
    assert c["numeroEhBotao"] is True, "é botão, não âncora para fora"
    assert c["abre"] == "abc123", "e abre o chamado da LINHA clicada"


@pytest.mark.parametrize("cenario", LISTAS)
def test_a_lista_mantem_a_saida_para_o_servicenow(cen: dict, cenario: str) -> None:
    """Trocar o destino do número não pode fechar a porta de sair."""
    c = cen[cenario]
    assert c["temLinkExterno"] is True
    assert c["alvoDoLink"] == "_blank"
