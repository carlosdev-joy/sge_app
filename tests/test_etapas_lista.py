"""A tela Etapas (`/jobs`): buscar sem filtro, copiar e colunas ajustáveis.

Três comportamentos pedidos pelo usuário em 2026-09-02, e o que cada teste
protege:

  1. **Buscar sem filtro nenhum lista TUDO.** A API já tratava filtro vazio (o
     WHERE simplesmente não entra) — era a tela que travava o botão e exigia
     digitar alguma coisa para ver qualquer coisa. Se alguém puser filtro
     obrigatório no backend, a tela volta a não mostrar nada com o botão
     habilitado: pior que antes, porque agora ela promete.
  2. **O nome do pipeline é copiável.** Ele passa da largura da coluna e ficava
     só no `title`, que não dá para colar em lugar nenhum.
  3. **As colunas são arrastáveis**, com a largura lembrada entre visitas.

Os itens 2 e 3 são de front, e este repo não tem test runner de JS — são lidos
do TSX, como os demais testes de tela.
"""
from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
JOBS_TSX = RAIZ / "ui-react" / "src" / "pages" / "Jobs.tsx"
HOOK_TSX = RAIZ / "ui-react" / "src" / "components" / "ui" / "useColunasRedimensionaveis.tsx"
ALCA_TSX = RAIZ / "ui-react" / "src" / "components" / "ui" / "AlcaColuna.tsx"
ROUTER = RAIZ / "api" / "routers" / "jobs.py"


def _fonte(p: Path) -> str:
    assert p.exists(), f"{p.name} sumiu — a tela Etapas mudou de estrutura"
    return p.read_text(encoding="utf-8")


# ═══════════ 1. buscar sem filtro ═══════════════════════════════════════════

def test_o_backend_lista_sem_filtro():
    """O `WHERE` só entra se houver filtro. Um `if not (fp or fj or ft): raise`
    aqui deixaria a tela com o botão habilitado e a lista sempre vazia."""
    fonte = _fonte(ROUTER)
    corpo = fonte[fonte.index("def list_jobs("):]
    corpo = corpo[:corpo.index("\n@router")] if "\n@router" in corpo else corpo
    assert 'where_sql = ("WHERE " + " AND ".join(where)) if where else ""' in corpo, (
        "a montagem do WHERE mudou — conferir se filtro vazio ainda lista tudo")
    for proibido in ("filtro obrigatório", "ao menos um filtro", "status_code=400"):
        assert proibido not in corpo, f"list_jobs passou a exigir filtro ({proibido})"


def test_a_busca_da_tela_nao_exige_filtro():
    fonte = _fonte(JOBS_TSX)
    assert "enabled: hasSearched," in fonte, (
        "a query voltou a exigir filtro para consultar")
    assert "hasFilter" not in fonte, (
        "`hasFilter` voltou — era ele que travava a busca sem filtro")


def test_o_botao_de_buscar_nunca_fica_travado():
    """Botão desabilitado enquanto não se digita nada era exatamente o que
    impedia listar todas as etapas."""
    fonte = _fonte(JOBS_TSX)
    bloco = re.search(r"<Button size=\"sm\" onClick=\{doSearch\}[^>]*>", fonte)
    assert bloco, "o botão Buscar mudou de forma — reconferir"
    assert "disabled" not in bloco.group(0), (
        "o botão Buscar voltou a ficar desabilitado sem filtro")


def test_buscar_sem_filtro_nao_devolve_erro_ao_usuario():
    """O toast 'Informe ao menos um filtro' era a recusa; buscar tudo é uma
    operação legítima."""
    fonte = _fonte(JOBS_TSX)
    assert "Informe ao menos um filtro" not in fonte


# ═══════════ 2. copiar o nome ═══════════════════════════════════════════════

def test_pipeline_e_etapa_sao_copiaveis_na_lista():
    """A Etapa já tinha o botão; o Pipeline, que é o nome que mais estoura a
    coluna, não tinha."""
    fonte = _fonte(JOBS_TSX)
    for campo in ("j.pipeline_name", "j.job_name"):
        assert f"copyText({campo})" in fonte, (
            f"não há como copiar {campo} na Lista — o nome truncado fica ilegível")


# ═══════════ 3. colunas ajustáveis ══════════════════════════════════════════

def test_a_tabela_da_lista_e_ajustavel():
    fonte = _fonte(JOBS_TSX)
    assert "table-fixed" in fonte and "cols.colgroup" in fonte, (
        "sem `table-fixed` + colgroup o navegador redistribui as colunas e o "
        "arrasto não gruda")
    # Toda coluna de conteúdo variável precisa de alça — sem ela, a coluna que
    # estoura é justamente a que não dá para alargar.
    for chave in ("pipeline", "etapa", "comando"):
        assert f'chave="{chave}"' in fonte, f"a coluna {chave} ficou sem alça de arrasto"


def test_largura_tem_piso_e_e_lembrada():
    """Piso: um arrasto distraído some com a coluna e não há como pegá-la de
    volta. Persistência: ajustar a cada visita é pior que não ter o recurso.

    O piso é conferido DENTRO do handler de arrasto: procurar `Math.max(MIN_PX`
    no arquivo inteiro passa verde só porque o handler de teclado também usa —
    foi o que aconteceu na primeira versão deste teste.
    """
    fonte = _fonte(HOOK_TSX)
    assert "const MIN_PX" in fonte, "a largura mínima sumiu"

    mover = fonte[fonte.index("function mover"):]
    mover = mover[:mover.index("function soltar")]
    assert "Math.max(MIN_PX" in mover, (
        "o ARRASTO perdeu o piso — dá para puxar a coluna até sumir")

    assert "localStorage.setItem" in fonte and "orq." in fonte, (
        "a largura deixou de ser lembrada entre visitas")


def test_o_localstorage_nunca_derruba_a_tela():
    """Janela privada e site data bloqueado fazem `localStorage` LANÇAR, não
    devolver vazio — e aí a tela inteira quebra por causa de uma largura."""
    fonte = _fonte(HOOK_TSX)
    assert fonte.count("catch") >= 2, (
        "leitura e escrita do localStorage precisam das duas guardas")


def test_a_alca_funciona_sem_mouse():
    """Redimensionar só com arrasto deixa de fora quem navega por teclado."""
    fonte = _fonte(HOOK_TSX)
    assert "ArrowLeft" in fonte and "ArrowRight" in fonte, (
        "a alça deixou de responder às setas")
    assert "tabIndex={0}" in _fonte(ALCA_TSX), "a alça não é mais focável"


def test_a_alca_nao_dispara_a_ordenacao_da_coluna():
    """A alça fica DENTRO do `<th>`, ao lado do botão de ordenar: sem parar a
    propagação, cada arrasto reordenaria a tabela."""
    fonte = _fonte(HOOK_TSX)
    assert "stopPropagation()" in fonte and "preventDefault()" in fonte


def test_o_cursor_volta_ao_normal_depois_do_arrasto():
    """O arrasto troca o cursor e trava a seleção no `body`; sem devolver, a
    página inteira fica com cursor de resize se o mouse soltar fora."""
    fonte = _fonte(HOOK_TSX)
    soltar = fonte[fonte.index("function soltar"):]
    assert "document.body.style.cursor = ''" in soltar
    assert "document.body.style.userSelect = ''" in soltar
