"""Prévia do corpo do e-mail na tela (F1 da spec
docs/spec-email-modelos-e-navegacao.md).

Dois grupos:

  1. **O isolamento do iframe**, lido do fonte do componente. É o teste que
     importa: o corpo é HTML escrito por uma pessoa e renderizado na tela de
     outra, o produto **não tem CSP** (`config/nginx.conf` só define
     Cache-Control) e não há biblioteca de sanitização no projeto. O
     `sandbox` vazio é a única defesa — se alguém acrescentar `allow-scripts`
     para "a prévia ficar mais fiel", script no corpo passa a executar na sessão
     de quem edita o fluxo.

  2. **Os valores de exemplo**, que precisam bater com o que o operador do
     worker resolve de verdade — uma prévia que mostra marcador que não existe
     (ou deixa de mostrar um que existe) ensina errado.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
FONTE = RAIZ / "ui-react/src/components/etapas/PreviaEmail.tsx"
HARNESS = RAIZ / "tests/js/ds_params_harness.cjs"
OPERADOR = RAIZ / "dags/utils/email_operator.py"
DADOS = RAIZ / "ui-react/src/components/etapas/previaEmailDados.ts"


# ── 1. isolamento ───────────────────────────────────────────────────────────

def _codigo_sem_comentarios() -> str:
    """O fonte sem as linhas de comentário — elas CITAM `allow-scripts` para
    dizer que não o usam, e uma busca crua acusaria isso como defeito."""
    src = FONTE.read_text(encoding="utf-8")
    return "\n".join(l for l in src.splitlines() if not l.lstrip().startswith("//"))


def test_ancora_iframe_sem_scripts_e_sem_mesma_origem():
    """⛔ Âncora. `sandbox=""` (vazio) é o mais restritivo que existe."""
    codigo = _codigo_sem_comentarios()
    assert 'sandbox=""' in codigo, "a prévia precisa de um iframe com sandbox vazio"
    for perigoso in ("allow-scripts", "allow-same-origin", "allow-popups",
                     "allow-top-navigation", "allow-forms"):
        assert perigoso not in codigo, (
            f"`{perigoso}` no sandbox da prévia: HTML de terceiro passa a agir na "
            "sessão de quem edita o fluxo, e o produto não tem CSP para segurar")


def test_previa_nao_injeta_html_na_propria_pagina():
    """O caminho proibido é o `dangerouslySetInnerHTML`: ele colocaria o HTML
    do corpo DENTRO da página do Orquestra, com a sessão do usuário junto."""
    codigo = _codigo_sem_comentarios()
    assert "dangerouslySetInnerHTML" not in codigo
    assert "srcDoc" in codigo, "o corpo entra pelo srcDoc do iframe"


def test_modo_texto_puro_escapa_o_conteudo():
    """Com 'Corpo em HTML' desligado, o corpo é texto: `<b>` tem de aparecer
    como `<b>`, não virar negrito — e, de quebra, não virar marcação nenhuma."""
    src = DADOS.read_text(encoding="utf-8")
    assert "function escapar" in src
    trecho = src[src.index("function escapar"):]
    for entidade in ("&amp;", "&lt;", "&gt;"):
        assert entidade in trecho, f"o escape do modo texto não cobre {entidade}"


# ── 2. valores de exemplo × o que o operador resolve ────────────────────────

@pytest.fixture(scope="module")
def previa():
    node = shutil.which("node")
    if node is None:
        pytest.skip("front não instalado nesta máquina")
    r = subprocess.run([node, str(HARNESS)], capture_output=True, text=True, cwd=str(RAIZ), timeout=180)
    assert r.returncode == 0, f"bancada do front falhou:\n{r.stderr}"
    return json.loads(r.stdout)["previaEmail"]


def _chaves_do_operador() -> set[str]:
    """As chaves que `_mapa` monta, lidas do fonte.

    A leitura é por texto porque importar o operador exigiria o Airflow. Por
    isso ela **recusa** as formas que sabe não conseguir ler (`mapa[...] =`,
    `.update(`, `**`) em vez de devolver um conjunto incompleto: um teste de
    paridade que não enxerga a chave nova fica VERDE enquanto a tela já
    diverge — exatamente o modo de falso verde que ele existe para impedir."""
    fonte = OPERADOR.read_text(encoding="utf-8")
    bloco = fonte[fonte.index("def _mapa"):fonte.index("# ── execução")]
    corpo = bloco[bloco.index("return {"):]
    for dinamico in ("mapa[", ".update(", "**"):
        assert dinamico not in corpo, (
            f"`{dinamico}` no mapa do operador: esta leitura por texto não "
            "enxerga chave montada assim — ajuste o teste junto com o código")
    # aspas simples E duplas; o operador usa duplas, mas nada impede a troca
    chaves = set(re.findall(r"""["']([A-Za-z_]+)["']\s*:""", corpo))
    assert len(chaves) >= 5, f"leitura do mapa do operador suspeita: {chaves}"
    return chaves


def test_ancora_exemplo_cobre_exatamente_os_marcadores_do_operador(previa):
    """⛔ Âncora. Os marcadores da prévia saem do mesmo conjunto que o operador
    monta em `_mapa`. Divergir ensina errado: um marcador a mais some no envio,
    um a menos parece inválido na tela e é aceito lá."""
    do_operador = _chaves_do_operador()
    assert set(previa["chaves"]) == do_operador, (
        f"prévia {sorted(previa['chaves'])} × operador {sorted(do_operador)}")


def test_ancora_seletor_inserir_oferece_o_mesmo_conjunto():
    """⛔ Âncora da TERCEIRA lista do mesmo conjunto: `EMAIL_PLACEHOLDERS`, que
    alimenta o botão *Inserir* do painel. Um marcador só nela faria o próprio
    botão produzir o que a linha de baixo denuncia como desconhecido."""
    fonte = (RAIZ / "ui-react/src/components/etapas/fluxoTypes.ts").read_text(encoding="utf-8")
    bloco = fonte[fonte.index("EMAIL_PLACEHOLDERS"):]
    bloco = bloco[:bloco.index("]")]
    do_seletor = set(re.findall(r"'([a-z_]+)'", bloco))
    assert do_seletor == _chaves_do_operador(), (
        f"seletor {sorted(do_seletor)} × operador {sorted(_chaves_do_operador())}")


def test_exemplo_resolve_e_deixa_desconhecido_intacto(previa):
    assert previa["resolvido"] == "O fluxo CARGA_VIDA terminou em 11/09/2026 14:30 com 4.200 linhas."
    assert previa["intacto"] == "Fim de CARGA_VIDA {variavel_errada}"
    assert previa["vazio"] == ["", "", ""]


def test_odate_de_exemplo_e_data_de_referencia_em_aaaammdd(previa):
    """A prévia não pode sugerir que `{odate}` é a data do relógio: no envio ele
    é a data de referência da corrida, no formato que nomeia arquivo."""
    assert re.fullmatch(r"\d{8}", previa["odate"]), previa["odate"]


def test_marcador_desconhecido_e_listado_sem_repetir(previa):
    semnada, comerro, vazio, caixa = previa["desconhecidos"]
    assert semnada == [] and vazio == []
    assert comerro == ["nao_existe", "outro_errado"]
    # caixa errada é o engano mais provável, e o backend só resolve minúsculas
    assert caixa == ["ODATE", "Pipeline"]


def test_marcador_com_caixa_errada_ganha_a_sugestao_pronta(previa):
    de_odate, de_pipeline, inexistente, certo = previa["dicas"]
    assert de_odate == "{odate}" and de_pipeline == "{pipeline}"
    assert inexistente is None and certo is None


# ── 3. o documento que vai para o iframe ────────────────────────────────────

@pytest.fixture(scope="module")
def documento(previa, request):
    node = shutil.which("node")
    if node is None:
        pytest.skip("front não instalado nesta máquina")
    r = subprocess.run([node, str(HARNESS)], capture_output=True, text=True, cwd=str(RAIZ), timeout=180)
    assert r.returncode == 0, f"bancada do front falhou:\n{r.stderr}"
    return json.loads(r.stdout)["previaDocumento"]


def test_ancora_modelo_completo_entra_inteiro(documento):
    """⛔ Âncora. Corpo que já é um documento (o caso dos modelos
    institucionais) NÃO pode ser embrulhado: o navegador descarta os atributos
    do segundo `<body>`, e o `style` com o fundo do modelo some. A prévia
    mentiria exatamente sobre o que promete mostrar."""
    doc = documento["modeloInteiro"]
    assert "background:#f4f4f4" in doc, "o style do body do modelo foi descartado"
    assert doc.count("<body") == 1, "dois <body>: o do modelo perde os atributos"
    assert documento["soBody"].count("<body") == 1


def test_fragmento_ganha_documento_e_texto_e_escapado(documento):
    assert documento["fragmento"].startswith("<!doctype html>")
    assert "a &lt; b &amp; c" in documento["texto"]


def test_link_do_corpo_nao_navega_a_previa(documento):
    """Clicar num link levaria a própria prévia para fora, e ela viraria uma
    página de erro sem caminho de volta."""
    for chave in ("modeloInteiro", "fragmento", "texto"):
        assert "pointer-events:none" in documento[chave], chave


def test_ancora_isolamento_sobrevive_ao_empacotamento():
    """⛔ Âncora. `sandbox=""` é um atributo VAZIO, e minificador que remove
    atributo vazio deixaria a defesa só no fonte. Confere no bundle publicado —
    é ele que roda no navegador de quem edita o fluxo."""
    assets = sorted((RAIZ / "ui-react/dist/assets").glob("index-*.js"),
                    key=lambda p: p.stat().st_mtime, reverse=True)
    if not assets:
        pytest.skip("dist não construída nesta máquina")
    bundle = assets[0].read_text(encoding="utf-8", errors="replace")
    if "Prévia do e-mail" not in bundle:
        pytest.skip("dist anterior à prévia — rode npm run build")
    assert re.search(r'sandbox\s*:\s*[`"\']{2}', bundle), (
        "o sandbox do iframe sumiu no empacotamento")
    for perigoso in ("allow-scripts", "allow-same-origin", "allow-top-navigation"):
        assert perigoso not in bundle, f"`{perigoso}` no bundle publicado"
