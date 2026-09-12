"""Marcador `{tabela}` no corpo do e-mail (F5 da spec
docs/spec-email-tabela-sql-e-ajustes.md).

O pedido que originou a spec: "passar o resultado do SQL para o próximo nó".
O nó SQL publica a tabela (F4) e aqui ela entra no aviso.

O que se prende:
  1. **o render da tela e o do worker são o MESMO** — a prévia é o que a pessoa
     aprova antes de salvar, e um estilo diferente faria a tela prometer um
     aviso que não é o que chega;
  2. **escape por célula** — este é o primeiro lugar do e-mail onde entra dado
     de fora;
  3. o aviso de corte nunca afirma um total que não foi contado;
  4. no ASSUNTO a tabela vira resumo, porque markup em cabeçalho de e-mail faz a
     régua recusar a mensagem depois de resolver os marcadores.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "dags"))

from utils import sql_node as sq  # noqa: E402

CASOS = {
    "simples": {"columns": ["Produto", "Qtd"], "rows": [["ACIDO A", "3"], ["DIPIRONA", "1"]],
                "total": 2, "truncado": False, "havia_mais": False, "colunas_ocultas": 0},
    "perigosa": {"columns": ["Razão & Cia"], "rows": [["<b>negrito</b>"], [None]],
                 "total": 2, "truncado": False, "havia_mais": False, "colunas_ocultas": 0},
    "truncada": {"columns": ["n"], "rows": [["1"], ["2"]],
                 "total": 60, "truncado": True, "havia_mais": False, "colunas_ocultas": 3},
    "teto": {"columns": ["n"], "rows": [["1"]],
             "total": 1000, "truncado": True, "havia_mais": True, "colunas_ocultas": 0},
    "semLinhas": {"columns": ["a", "b"], "rows": [],
                  "total": 0, "truncado": False, "havia_mais": False, "colunas_ocultas": 0},
    "vazia": {"columns": [], "rows": [], "total": 0, "truncado": False,
              "havia_mais": False, "colunas_ocultas": 0},
}


@pytest.fixture(scope="module")
def do_front_texto(_bancada):
    return _bancada["tabelasTexto"]


@pytest.fixture(scope="module")
def do_front(_bancada):
    return _bancada["tabelas"]


@pytest.fixture(scope="module")
def _bancada():
    node = shutil.which("node")
    if node is None:
        pytest.skip("front não instalado nesta máquina")
    r = subprocess.run([node, str(RAIZ / "tests/js/ds_params_harness.cjs")],
                       capture_output=True, text=True, cwd=str(RAIZ), timeout=180)
    assert r.returncode == 0, f"bancada do front falhou:\n{r.stderr}"
    return json.loads(r.stdout)["previaEmail"]


@pytest.mark.parametrize("caso", sorted(CASOS))
def test_o_render_da_previa_e_o_do_worker_sao_o_mesmo(do_front, caso):
    """⛔ Teste CRUZADO, no padrão que a F3 do anexo estabeleceu: entre `api/` e
    `dags/` o anti-drift compara o fonte; entre a tela e o worker não dá (são
    linguagens diferentes), então os mesmos dados rodam nos dois e o markup tem
    de bater byte a byte."""
    assert sq.tabela_html(CASOS[caso]) == do_front[caso]


def test_celula_com_marcacao_vira_texto():
    """Este é o primeiro lugar do e-mail onde entra dado de FORA — tudo mais
    (pipeline, status, datas) é gerado pelo produto. Uma descrição com `<b>` ou
    um `&` de razão social quebraria o layout; um `</table>` quebraria o resto
    da mensagem."""
    html = sq.tabela_html(CASOS["perigosa"])
    assert "&lt;b&gt;negrito&lt;/b&gt;" in html and "<b>" not in html
    assert "Razão &amp; Cia" in html
    # célula vazia vira travessão, não um buraco no meio da tabela
    assert "—" in html


def test_o_aviso_de_corte_nao_inventa_total():
    """Acima do teto de leitura o total é um PISO. Dizer "de 1.000 linhas" seria
    afirmar um número que ninguém contou."""
    assert "mostrando 2 de 60 linhas" in sq.tabela_html(CASOS["truncada"])
    assert "3 colunas não cabem" in sq.tabela_html(CASOS["truncada"])
    assert "mais de 1.000 linhas" in sq.tabela_html(CASOS["teto"])
    # sem corte, sem rodapé
    assert "mostrando" not in sq.tabela_html(CASOS["simples"])


def test_sem_resultado_diz_isso_em_vez_de_deixar_buraco():
    assert "(sem resultado)" in sq.tabela_html(CASOS["vazia"])
    assert "não devolveu linhas" in sq.tabela_html(CASOS["semLinhas"])


def test_versao_texto_para_corpo_que_nao_e_html():
    """O nó aceita "Corpo livre" em texto simples: mandar markup para lá encheria
    o aviso de `<td style=…>`."""
    texto = sq.tabela_texto(CASOS["simples"])
    assert "<" not in texto
    # colunas alinhadas por largura — o cabeçalho acompanha a maior célula
    assert texto.splitlines()[0].startswith("Produto") and "Qtd" in texto.splitlines()[0]
    assert "ACIDO A" in texto and "DIPIRONA" in texto
    assert sq.tabela_texto(CASOS["vazia"]) == "(sem resultado)"


def test_no_assunto_a_tabela_vira_resumo():
    """⛔ Markup (ou o bloco de texto com quebras de linha) num cabeçalho de
    e-mail faz `validar_assunto` recusar a mensagem DEPOIS de resolver os
    marcadores — a etapa falharia por algo que a tela deixou escrever."""
    assert sq.resumo_curto(CASOS["simples"]) == "2 linhas × 2 colunas"
    # milhar no MESMO formato do rodapé da tabela: assunto e corpo do mesmo
    # e-mail dizendo "mais de 1000" e "mais de 1.000" é desleixo visível
    assert sq.resumo_curto(CASOS["teto"]) == "mais de 1.000 linhas × 1 coluna"
    assert sq.resumo_curto(CASOS["vazia"]) == "(sem resultado)"
    for caso in CASOS.values():
        resumo = sq.resumo_curto(caso)
        assert "<" not in resumo and "\n" not in resumo


# ── correções da revisão adversarial ────────────────────────────────────────

@pytest.mark.parametrize("caso", ["simples", "comVazio", "truncada", "semLinhas", "vazia"])
def test_a_tabela_em_texto_tambem_bate_nos_dois_lados(do_front_texto, caso):
    """O corpo NÃO-HTML é o default do nó novo (`defaultEmailNo`), então este
    render é o mais provável de chegar a quem recebe."""
    casos = {
        "simples": CASOS["simples"],
        "comVazio": {"columns": ["a", "b"], "rows": [["x", None]], "total": 1,
                     "truncado": False, "havia_mais": False, "colunas_ocultas": 0},
        "truncada": {"columns": ["n"], "rows": [["1"]], "total": 60,
                     "truncado": True, "havia_mais": False, "colunas_ocultas": 1},
        "semLinhas": CASOS["semLinhas"],
        "vazia": CASOS["vazia"],
    }
    assert sq.tabela_texto(casos[caso]) == do_front_texto[caso]


def test_concordancia_de_uma_coluna_oculta():
    """"1 coluna não cabem" — o erro passou pelo teste cruzado porque os DOIS
    lados erravam igual, que é o buraco clássico desse tipo de teste."""
    um = {"columns": ["a"], "rows": [["x"]], "total": 1, "truncado": False,
          "havia_mais": False, "colunas_ocultas": 1}
    assert "1 coluna não cabe no aviso" in sq.tabela_html(um)
    assert "não cabem" not in sq.tabela_html(um)


def test_celula_com_quebra_de_linha_nao_destroi_o_alinhamento():
    """`valor_publicavel` preserva o que vem do banco, e um `\\n` numa célula
    fazia a tabela em texto virar degrau."""
    assert sq.valor_publicavel("linha1\nlinha2") == "linha1 linha2"
    t = {"columns": ["obs", "n"], "rows": [[sq.valor_publicavel("a\nb"), "9"]],
         "total": 1, "truncado": False, "havia_mais": False, "colunas_ocultas": 0}
    linhas = sq.tabela_texto(t).splitlines()
    assert len(linhas) == 3 and linhas[2].startswith("a b")


def test_a_previa_mostra_texto_quando_o_corpo_nao_e_html(_bancada):
    """⛔ O corpo em texto é o DEFAULT do nó novo. A prévia mostrava o markup
    escapado dentro de um `<pre>` enquanto o envio mandava a tabela alinhada —
    a tela prometendo o que o e-mail não cumpre."""
    assert "<table" not in _bancada["exemploTexto"]
    assert "ACIDO ACETILSALICILICO 100MG |" in _bancada["exemploTexto"]
    assert "<table" in _bancada["exemploHtml"]


def test_tabela_no_nome_do_anexo_continua_sendo_acusada(_bancada):
    """⛔ Regressão que a revisão pegou: com `tabela` na lista compartilhada,
    `relatorio_{tabela}.xlsx` deixou de ser acusado — e ali o marcador nunca
    resolve (o anexo é um arquivo procurado por nome), então o e-mail sairia
    SEM anexo com um aviso discreto no log."""
    assert _bancada["desconhecidosNoAnexo"] == ["tabela"]


def test_texto_simples_do_corpo_html_nao_cola_as_celulas():
    """⛔ Defeito no artefato entregue: `re.sub(r"<[^>]+>", "")` colava o
    conteúdo — `ProdutoQtdACIDO A3DIPIRONA1`, com o número de uma linha
    encostando no nome da seguinte. É o que chega a quem lê em modo texto."""
    import sys as _sys
    from unittest.mock import MagicMock

    _sys.modules.setdefault("pyodbc", MagicMock())
    _sys.path.insert(0, str(RAIZ / "api"))
    from services import email_mime as em

    corpo = "Resultado:<br>" + sq.tabela_html(CASOS["simples"]) + "<p>Abraço.</p>"
    texto = em.html_para_texto(corpo)
    assert "Produto | Qtd" in texto
    assert "ACIDO A | 3" in texto and "DIPIRONA | 1" in texto
    assert "ACIDO A3" not in texto
    assert "<" not in texto and "&#160;" not in texto
