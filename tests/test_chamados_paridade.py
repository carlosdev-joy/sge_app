"""A Fila e os Indicadores contam a MESMA coisa — e continuam contando.

A tela separa em JavaScript (`lib/filaChamados.separarFila`) porque precisa dos
dois registros: o pai vira card, o filho vira linha dentro dele. As agregações
só CONTAM, então cortam no banco (`_so_trabalhos()`). São dois caminhos para a
mesma regra — uma duplicação deliberada, e é por isso que este arquivo existe.

Sem ele, a aba Indicadores diria **95** onde a Fila diz **59** (medido no dev em
2026-08-28, contra a instância real) e as duas pareceriam certas. Número de
cabeçalho que mente é pior que número nenhum.

O que se prende aqui:

  1. **Paridade** — a regra do SQL, traduzida linha a linha para Python, dá o
     mesmo conjunto que a regra da tela, nos cenários patológicos inclusive.
  2. **O predicado não usa `NOT IN`** — com um NULL na subconsulta ele devolve
     conjunto VAZIO, e a conta inteira viraria zero sem erro nenhum.
  3. **Anti-drift** — varre por AST as queries que citam `dbo.etl_chamado` e
     reprova a que não passar pelo recorte, NOMEANDO a query. É o que impede a
     próxima agregação de nascer contando registros.
  4. **Um piso no varredor** — varredor que deixa de achar qualquer coisa passa
     verde para sempre.

⚠️ A paridade prova que as REGRAS concordam, não que o T-SQL execute como o
Python. Isso é o smoke: comparar os dois números contra o banco de verdade.
"""
from __future__ import annotations

import ast
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()
os.environ.setdefault("MSSQL_CONN_STR", "__mock__")

RAIZ = Path(__file__).resolve().parents[1]
FONTE = RAIZ / "api" / "routers" / "chamados.py"

sys.path.insert(0, str(RAIZ / "api"))
from routers.chamados import _so_trabalhos  # noqa: E402


# ── 1. paridade ─────────────────────────────────────────────────────────────

def _conta_pela_regra_do_sql(linhas: list[dict]) -> set[str]:
    """A tradução literal do predicado de `_so_trabalhos()`, em Python.

    Escrita à mão de propósito: se ela fosse gerada a partir da mesma função
    que o router usa, provaria só que a função é igual a si mesma.
    """
    saida = set()
    for c in linhas:
        pai = c.get("pai_sys_id")
        excluido = (c["tipo"] == "task"
                    and pai is not None
                    and pai != ""
                    and pai != c["sys_id"])
        if not excluido:
            saida.add(c["sys_id"])
    return saida


def _conta_pela_regra_da_tela(linhas: list[dict]) -> set[str]:
    """A regra do `separarFila`, em Python — o que vira CARD."""
    return {c["sys_id"] for c in linhas
            if not (c["tipo"] == "task" and c.get("pai_sys_id")
                    and c["pai_sys_id"] != c["sys_id"])}


def _l(sys_id, tipo="ritm", pai=None):
    return {"sys_id": sys_id, "tipo": tipo, "pai_sys_id": pai}


CENARIOS = {
    "par simples":          [_l("R1"), _l("T1", "task", "R1")],
    "órfã nula":            [_l("R1"), _l("T9", "task", None)],
    "órfã string vazia":    [_l("R1"), _l("T9", "task", "")],
    "auto-referência":      [_l("R1"), _l("T7", "task", "T7")],
    "pai fora do escopo":   [_l("R1"), _l("T2", "task", "R-SUMIU")],
    "filho antes do pai":   [_l("T1", "task", "R1"), _l("R1")],
    "duas filhas":          [_l("R1"), _l("T1", "task", "R1"), _l("T2", "task", "R1")],
    "RITM com pai":         [_l("R2", "ritm", "R1"), _l("R1")],
    "incidente":            [_l("I1", "incident")],
    "fila só de tarefas":   [_l("T1", "task", "R1"), _l("T2", "task", "R1")],
    "vazio":                [],
}


@pytest.mark.parametrize("nome", list(CENARIOS))
def test_a_fila_e_as_contas_veem_o_mesmo_conjunto(nome: str) -> None:
    linhas = CENARIOS[nome]
    pela_tela = _conta_pela_regra_da_tela(linhas)
    pelo_sql = _conta_pela_regra_do_sql(linhas)
    assert pela_tela == pelo_sql, (
        f"cenário '{nome}': a Fila veria {sorted(pela_tela)} e os Indicadores "
        f"contariam {sorted(pelo_sql)} — os dois números apareceriam na mesma "
        f"tela, e os dois pareceriam certos")


def test_a_auto_referencia_nao_some_de_nenhum_dos_dois() -> None:
    """Dado corrompido tem de aparecer, não sumir em silêncio."""
    linhas = CENARIOS["auto-referência"]
    assert "T7" in _conta_pela_regra_da_tela(linhas)
    assert "T7" in _conta_pela_regra_do_sql(linhas)


def test_a_orfa_conta_dos_dois_lados() -> None:
    for nome in ("órfã nula", "órfã string vazia"):
        linhas = CENARIOS[nome]
        assert "T9" in _conta_pela_regra_da_tela(linhas), nome
        assert "T9" in _conta_pela_regra_do_sql(linhas), nome


# ── 2. o predicado ──────────────────────────────────────────────────────────

def test_o_predicado_nao_usa_not_in() -> None:
    """`NOT IN` com um NULL na subconsulta devolve conjunto VAZIO.

    A conta inteira viraria zero, sem erro nenhum para avisar.
    """
    sql = _so_trabalhos()
    assert "NOT IN" not in sql.upper()


def test_o_predicado_cobre_as_tres_condicoes() -> None:
    sql = _so_trabalhos()
    assert "tipo = 'task'" in sql, "sem isto, RITM com pai torto sumiria"
    assert "pai_sys_id <> ''" in sql, "o sync grava '' — e '' é ausência"
    assert "pai_sys_id <> sys_id" in sql, "auto-referência não pode sumir"


def test_o_predicado_comeca_com_and() -> None:
    """Ele é colado a WHEREs existentes; sem o AND vira erro de sintaxe."""
    assert _so_trabalhos().strip().startswith("AND ")


# ── 3. anti-drift ───────────────────────────────────────────────────────────

def _chama_o_recorte(no: ast.AST) -> bool:
    return any(isinstance(x, ast.Call) and isinstance(x.func, ast.Name)
               and x.func.id == "_so_trabalhos" for x in ast.walk(no))


def _literais(no: ast.AST) -> str:
    return " ".join(x.value for x in ast.walk(no)
                    if isinstance(x, ast.Constant) and isinstance(x.value, str))


def _sql_em_ordem(no: ast.AST) -> str:
    """O SQL remontado na ORDEM em que aparece no arquivo.

    `ast.walk` percorre em largura e devolve os literais fora de ordem — o que
    basta para procurar substring, mas não para perguntar "o que vem DEPOIS do
    GROUP BY". Ordenar por posição reconstrói a concatenação como ela é lida.
    (Este teste nasceu com esse defeito: acusou duas queries de fluxo cujo `?`
    está no WHERE, não no GROUP BY.)
    """
    partes = sorted(
        ((x.lineno, x.col_offset, x.value) for x in ast.walk(no)
         if isinstance(x, ast.Constant) and isinstance(x.value, str)),
        key=lambda t: (t[0], t[1]))
    return " ".join(p[2] for p in partes)


def _executes_sobre_o_espelho() -> list[tuple[int, str, bool]]:
    """Cada `cur.execute` que cita dbo.etl_chamado: linha, trecho, tem recorte."""
    achados = []
    arvore = ast.parse(FONTE.read_text(encoding="utf-8"))
    for no in ast.walk(arvore):
        if not (isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute)
                and no.func.attr == "execute"):
            continue
        sql = _literais(no)
        if "dbo.etl_chamado" not in sql:
            continue
        # o espelho do ciclo (etl_chamado_sync) não é fila de chamados
        if "dbo.etl_chamado_sync" in sql and "FROM dbo.etl_chamado " not in sql:
            continue
        achados.append((no.lineno, sql[:70], _chama_o_recorte(no)))
    return achados


# Queries que NÃO levam o recorte, e por quê. Toda exceção mora aqui, com
# motivo — exceção sem nome é o mesmo que esquecimento.
SEM_RECORTE_POR_DESIGN = {
    # A listagem devolve o espelho INTEIRO: a tela precisa dos dois registros
    # (pai vira card, filho vira linha dentro dele). É lá que `separarFila`
    # aplica a mesma regra, em JavaScript.
    "SELECT sys_id, numero, tipo, titulo, estado_origem, estado_kanban",
    # As filhas de um RITM: pedir "só trabalhos" aqui devolveria zero — a
    # rota existe justamente para listar filhas.
    "SELECT sys_id, numero, tipo, titulo, estado_kanban, prioridade",
    # ── Consultas POR ID, não agregações ────────────────────────────────────
    # O recorte responde "este registro conta na SOMA?". Quem abriu um chamado
    # específico já sabe qual quer — aplicar o recorte aqui faria a tela de
    # detalhe de uma TAREFA responder 404, e é justamente pela tarefa que se
    # abre o detalhe a partir da linha dentro do card.
    "SELECT sys_id, numero, tipo, titulo, descricao, estado_kanban",
    # Notas e anexos de UM chamado, buscados por sys_id do pai.
    "SELECT sys_id_nota, autor, autor_email, criado_em, texto, tipo",
    "SELECT sys_id_anexo, nome_arquivo, mime_type, tamanho_bytes, criado_em",
    # O proxy de anexo resolve UMA url a partir do id do anexo.
    "SELECT url_download, nome_arquivo, mime_type",
}


def test_toda_agregacao_sobre_o_espelho_passa_pelo_recorte() -> None:
    achados = _executes_sobre_o_espelho()
    faltando = [
        (linha, trecho) for linha, trecho, tem in achados
        if not tem and not any(p in trecho for p in SEM_RECORTE_POR_DESIGN)
    ]
    assert not faltando, (
        "estas queries contam REGISTROS onde a fila conta TRABALHOS — a aba "
        "vai discordar da tela e as duas vão parecer certas:\n" +
        "\n".join(f"  linha {ln}: {tr}…" for ln, tr in faltando))


def test_o_varredor_acha_alguma_coisa() -> None:
    """Piso: varredor que deixa de achar passa verde para sempre."""
    achados = _executes_sobre_o_espelho()
    assert len(achados) >= 12, (
        f"o varredor achou só {len(achados)} queries sobre o espelho — se o "
        f"router foi reescrito, este teste precisa ser revisto, não ignorado")
    assert sum(1 for _, _, tem in achados if tem) >= 10, (
        "quase nenhuma query passa pelo recorte — o varredor perdeu o alvo")


# ── 4. o parâmetro que não pode entrar no GROUP BY ──────────────────────────

def test_nenhuma_query_usa_parametro_no_group_by() -> None:
    """`GROUP BY ISNULL(expr, ?)` é recusado pelo SQL Server — e em silêncio.

    O valor do parâmetro não é conhecido em tempo de compilação, então a
    expressão do GROUP BY não é reconhecida como a mesma do SELECT:

        Column 'tipo_demanda' is invalid in the select list because it is not
        contained in either an aggregate function or the GROUP BY clause

    O estrago é mudo: a exceção cai no `except` que envolve o bloco inteiro
    dos indicadores, e a resposta segue "servindo o painel base". Os chips de
    tipo, categoria, sem_categoria, resolvidos e os três da triagem somem — sem
    erro na tela, sem número errado. Só o log sabe.

    Estava assim na `main` e passou por toda a suíte, porque teste com cursor
    dublê não executa SQL. Foi encontrado rodando contra o banco do dev em
    2026-08-28. O rótulo do vazio se aplica no Python.
    """
    arvore = ast.parse(FONTE.read_text(encoding="utf-8"))
    problemas = []
    for no in ast.walk(arvore):
        if not (isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute)
                and no.func.attr == "execute"):
            continue
        sql = _sql_em_ordem(no)
        if "GROUP BY" not in sql.upper():
            continue
        depois = sql.upper().split("GROUP BY", 1)[1]
        # corta no ORDER BY: parâmetro lá é legítimo
        depois = depois.split("ORDER BY", 1)[0]
        if "?" in depois:
            problemas.append((no.lineno, sql[:70]))
    assert not problemas, (
        "parâmetro dentro do GROUP BY — o SQL Server recusa e o bloco inteiro "
        "degrada em silêncio:\n" +
        "\n".join(f"  linha {ln}: {tr}…" for ln, tr in problemas))
