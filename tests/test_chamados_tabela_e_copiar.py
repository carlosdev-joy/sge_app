"""A tabela alinhada e o botão de copiar o número.

Dois pedidos do dono do produto ao olhar a tela:

    "deve ser colocado em formato de tabela, para garantir que o usuario sempre
     veja responsavel em 'coluna' responsavel. neste momento por exemplo tem
     uma demanda sem prazo, e acabou jogando o nome do responsavel para baixo
     do prazo, e os nomes ainda estão cortando."

    "nos cards, e todo local que tenha numero de chamado ou task, incluir um
     botão para copiar o numero."

**O defeito de alinhamento.** A lista era um `flex` onde prazo e data só eram
RENDERIZADOS quando existiam. Chamado sem prazo perdia duas células e o
responsável escorregava para a posição delas — a mesma coluna visual mostrava
prazo numa linha e nome de pessoa na seguinte.

⚠️ ESTE ARQUIVO RENDERIZA E ARRASTA. O alinhamento é uma propriedade do que foi
RENDERIZADO: a lista antiga também "tinha" uma coluna de responsável no fonte;
ela só sumia quando faltava o prazo. Procurar `<th>Responsável` no `.tsx`
passaria verde com o defeito de pé.

Sem Node ou sem `node_modules` a suíte SALTA em vez de falhar.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
HARNESS = RAIZ / "tests" / "js" / "tabela_copiar_harness.cjs"
SUCRASE = RAIZ / "ui-react" / "node_modules" / "sucrase"


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


# ═══════════ 1. a coluna é posição, não sobra ═══════════════════════════════

def test_toda_linha_tem_uma_celula_por_coluna(cen: dict) -> None:
    """O CORAÇÃO do pedido. A primeira linha da bancada não tem prazo, e o
    prazo vem ANTES do responsável: se a célula vazia deixar de ser
    renderizada, o responsável cai na coluna do prazo."""
    t = cen["tabela"]["antes"]
    assert t["celulasPorLinha"] == [3, 3, 3], (
        "linha com campo faltando tem de manter a célula vazia")


def test_o_responsavel_fica_sempre_na_coluna_do_responsavel(cen: dict) -> None:
    """A linha SEM PRAZO é a primeira: é ela que quebrava antes."""
    assert cen["tabela"]["antes"]["responsavelNaColuna"] == [
        "Cristiane Gomes de Moura", "Carlos Henrique", "sem responsável",
    ]


def test_sem_responsavel_e_dito_e_nao_deixado_em_branco(cen: dict) -> None:
    """Célula vazia numa coluna de nome parece falha de carga; a informação
    aqui é que o chamado não tem dono — que é o que faz alguém agir."""
    assert cen["tabela"]["antes"]["responsavelNaColuna"][2] == "sem responsável"


def test_a_tabela_tem_cabecalho_nomeado(cen: dict) -> None:
    """Sem cabeçalho, "coluna do responsável" é combinação, não leitura."""
    assert cen["tabela"]["antes"]["cabecalhos"] == [
        "Chamado", "Prazo", "Responsável"]


def test_o_valor_inteiro_fica_no_title(cen: dict) -> None:
    """Enquanto o usuário não arrasta, é o `title` que resgata o nome que a
    coluna corta — foi a segunda metade da reclamação."""
    assert cen["tabela"]["antes"]["tituloDaCelula"][0] == "Cristiane Gomes de Moura"


def test_lista_vazia_diz_o_motivo_em_vez_de_tabela_sem_linhas(cen: dict) -> None:
    """Cabeçalho sozinho, sem linha nenhuma, parece carregamento travado."""
    v = cen["tabela"]["vazia"]
    assert v["temTabela"] is False
    assert "Nenhum chamado" in v["texto"]


# ═══════════ 2. arrastar a largura ══════════════════════════════════════════

def test_arrastar_muda_a_largura_da_coluna(cen: dict) -> None:
    """60px para a direita na coluna do meio: 190 → 250, e só ela muda."""
    assert cen["tabela"]["antes"]["larguras"] == [160, 110, 190]
    assert cen["tabela"]["depoisDeArrastar"] == [160, 110, 250]


def test_a_coluna_nao_pode_sumir_no_arrasto(cen: dict) -> None:
    """Arrasto de -900px para na largura mínima. Sem piso, a coluna vai a zero
    e o conteúdo fica INALCANÇÁVEL — não há alça no que não tem largura."""
    assert cen["tabela"]["noPiso"] == [160, 110, 100]


def test_a_largura_escolhida_e_lembrada(cen: dict) -> None:
    """Reajustar a mesma coluna a cada visita é o mesmo trabalho de novo."""
    assert cen["tabela"]["lembrada"] == [160, 110, 100]


def test_cada_tabela_lembra_a_sua(cen: dict) -> None:
    """Uma preferência global faria a tabela do painel mudar sozinha quando o
    usuário ajustasse a dos indicadores."""
    assert cen["tabela"]["outroId"] == [160, 110, 190]


@pytest.mark.parametrize("caso,esperado", [
    # Coluna que sumiu do código não vira coluna fantasma; a que ficou usa o
    # valor salvo.
    ("salvasParciais", {"numero": 160, "responsavel": 260, "prazo": 110}),
    # `localStorage` é editável pelo usuário: lixo cai no padrão em vez de
    # virar coluna de largura zero.
    ("salvasInvalidas", {"numero": 160, "responsavel": 190, "prazo": 110}),
    ("salvasAusentes", {"numero": 160, "responsavel": 190, "prazo": 110}),
    # Salva abaixo do mínimo sobe para o mínimo.
    ("salvaAbaixoDoMinimo", {"numero": 160, "responsavel": 100, "prazo": 110}),
])
def test_preferencia_salva_incompativel_nao_quebra_a_tabela(
        cen: dict, caso: str, esperado: dict) -> None:
    assert cen["puras"][caso] == esperado


# ═══════════ 3. copiar o número ═════════════════════════════════════════════

CENARIOS_COPIA = ["copia_ok", "copia_recusada", "copia_sem_api"]


@pytest.mark.parametrize("cenario", CENARIOS_COPIA)
def test_o_botao_de_copiar_existe_e_diz_o_que_copia(cen: dict, cenario: str) -> None:
    """"Copiar" sozinho, ao lado de um número truncado, deixa a dúvida de se
    copia o número ou a linha."""
    c = cen[cenario]
    assert c["temBotao"] is True
    assert c["ajuda"] == "Copiar RITM0103367"
    assert c["etiqueta"] == "Copiar RITM0103367", "e o mesmo para leitor de tela"


@pytest.mark.parametrize("cenario", CENARIOS_COPIA)
def test_o_aviso_so_aparece_depois_do_clique(cen: dict, cenario: str) -> None:
    """"copiado" antes de qualquer clique afirmaria algo que não aconteceu."""
    assert cen[cenario]["avisoAntes"] is False


def test_copiar_com_a_api_disponivel_copia_e_confirma(cen: dict) -> None:
    """Cópia não muda nada na tela: sem retorno, o usuário clica de novo por
    dúvida e não sabe se funcionou."""
    c = cen["copia_ok"]
    assert c["escritos"] == ["RITM0103367"], "o número CERTO foi para a área"
    assert c["aviso"] == "copiado"
    assert "Check" in c["icone"], "a confirmação também no ícone"


@pytest.mark.parametrize("cenario", ["copia_recusada", "copia_sem_api"])
def test_falha_de_clipboard_pede_ctrl_c_em_vez_de_calar(
        cen: dict, cenario: str) -> None:
    """`navigator.clipboard` exige contexto seguro e pode ser negado — e o
    Orquestra roda atrás do proxy da Caixa. Botão que falha em silêncio faz o
    usuário colar o que estava ANTES na área e mandar para outra pessoa."""
    c = cen[cenario]
    assert c["escritos"] == []
    assert c["aviso"] == "use Ctrl+C", "o aviso PEDE uma ação, não afirma sucesso"
    assert "Check" not in c["icone"], "sem check: não houve cópia"


@pytest.mark.parametrize("caso,esperado", [
    ("apiOk", "copiado"),
    # Sem a API, o caminho legado (`execCommand`) ainda copia sem HTTPS.
    ("legadoSalva", "copiado"),
    ("legadoFalha", "selecionado"),
    # Número vazio não é "copiado com sucesso".
    ("vazio", "falhou"),
])
def test_a_funcao_de_copia_distingue_as_saidas(
        cen: dict, caso: str, esperado: str) -> None:
    """Booleano não bastaria: a tela diz coisas diferentes para "copiei" e
    para "não consegui, use Ctrl+C"."""
    assert cen["direto"][caso] == esperado
