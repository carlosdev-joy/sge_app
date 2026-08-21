"""A fila e os indicadores contam a MESMA coisa.

O card da fila é o trabalho (o pedido com a tarefa dentro), e as agregações
precisam contar do mesmo jeito. Só que os dois caminhos são diferentes por
necessidade: a fila agrupa em Python (`_agrupar_por_pai`), porque a tela mostra
o pai como card e o filho como linha; as agregações cortam em SQL
(`_so_trabalhos`), porque elas só contam e trazer a tabela para o Python seria
desperdício.

Duas implementações da mesma regra é exatamente o tipo de coisa que diverge em
silêncio: a aba Indicadores diria 113 enquanto a Fila diz 60, e as duas
pareceriam certas. Este arquivo prende as duas pontas:

  1. **paridade** — a regra do SQL, traduzida linha a linha para Python, dá o
     mesmo conjunto de raízes que `_agrupar_por_pai` em todos os cenários que
     importam (inclusive os patológicos);
  2. **anti-drift** — agregação NOVA sobre `dbo.etl_chamado` que esqueça o
     predicado reprova, nomeando a query.

⚠️ O item 1 prova que as REGRAS concordam, não que o T-SQL execute como o
Python — isso é o smoke (alínea c da spec), que compara os dois números contra
o banco de verdade.
"""
from __future__ import annotations

import ast
import os
import pathlib
import sys
from unittest.mock import MagicMock

import pytest

if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()
os.environ.setdefault("MSSQL_CONN_STR", "__mock__")

from routers.chamados import _agrupar_por_pai, _so_trabalhos  # noqa: E402

FONTE = pathlib.Path(__file__).resolve().parents[1] / "api" / "routers" / "chamados.py"


# ═══════════ 1. paridade entre o Python da fila e o SQL das contas ══════════

def _raizes_pela_regra_do_sql(linhas: list[dict]) -> set[str]:
    """A tradução literal do NOT EXISTS de `_so_trabalhos`, em Python.

    Lê-se junto com o SQL: existe `pai` com `pai.sys_id = c.pai_sys_id`, com
    `pai.sys_id <> c.sys_id`, e esse pai é RAIZ (não tem pai, aponta para si
    mesmo, ou o avô não está no escopo)? Então `c` é filho e sai da conta.
    """
    por_id = {c["sys_id"]: c for c in linhas}

    def eh_raiz(p: dict) -> bool:
        pai = (p.get("pai_sys_id") or "").strip()
        return not pai or pai == p["sys_id"] or pai not in por_id

    raizes = set()
    for c in linhas:
        pai = por_id.get((c.get("pai_sys_id") or "").strip())
        ehFilho = (pai is not None and pai["sys_id"] != c["sys_id"]
                   and eh_raiz(pai))
        if not ehFilho:
            raizes.add(c["sys_id"])
    return raizes


def _linha(sys_id, pai=""):
    return {"sys_id": sys_id, "pai_sys_id": pai}


CENARIOS = {
    "ritm com uma task": [_linha("R1"), _linha("T1", "R1")],
    "ritm com duas tasks": [_linha("R1"), _linha("T1", "R1"), _linha("T2", "R1")],
    "task órfã (pai fora do espelho)": [_linha("T1", "R-de-outro-grupo")],
    "auto-referência": [_linha("A", "A")],
    "ciclo entre dois": [_linha("A", "B"), _linha("B", "A")],
    "cadeia de três": [_linha("A"), _linha("B", "A"), _linha("C", "B")],
    "filho antes do pai na ordem": [_linha("T1", "R1"), _linha("R1")],
    "só incidents, nenhum parentesco": [_linha("I1"), _linha("I2")],
    "fila vazia": [],
    "pai vazio com espaço": [_linha("R1"), _linha("T1", "  ")],
}


@pytest.mark.parametrize("nome", list(CENARIOS))
def test_a_fila_e_as_contas_veem_as_mesmas_raizes(nome):
    linhas = [dict(x) for x in CENARIOS[nome]]
    pela_fila = {c["sys_id"] for c in _agrupar_por_pai(linhas)}
    pelo_sql = _raizes_pela_regra_do_sql([dict(x) for x in CENARIOS[nome]])
    assert pela_fila == pelo_sql, (
        f"cenário '{nome}': a fila conta {sorted(pela_fila)} e as agregações "
        f"contariam {sorted(pelo_sql)} — a aba Indicadores discordaria da Fila")


def test_nenhum_cenario_perde_registro():
    """A regra pode mover um registro para dentro de outro, nunca sumir com
    ele: todo sys_id ou é raiz, ou é filho de alguma raiz."""
    for nome, base in CENARIOS.items():
        linhas = [dict(x) for x in base]
        todos = {c["sys_id"] for c in linhas}
        raizes = _agrupar_por_pai(linhas)
        vistos = {r["sys_id"] for r in raizes}
        for r in raizes:
            vistos |= {f["sys_id"] for f in r.get("filhos", [])}
        assert vistos == todos, f"cenário '{nome}': sumiu {todos - vistos}"


def test_o_predicado_muda_de_escopo_conforme_a_agregacao():
    """Agregação sobre a fila olha pai ATIVO; agregação de histórico olha o
    espelho inteiro, porque lá o pai já pode ter saído da fila."""
    assert "pai.ativo = 1" in _so_trabalhos()
    assert "pai.ativo = 1" not in _so_trabalhos(entre_ativos=False)


def test_o_predicado_nao_usa_not_in():
    """`NOT IN` com um NULL na subconsulta devolve conjunto VAZIO — a conta
    inteira viraria zero sem erro nenhum. O predicado usa NOT EXISTS."""
    sql = _so_trabalhos()
    assert "NOT EXISTS" in sql
    assert "NOT IN" not in sql


# ═══════════ 2. anti-drift: agregação nova não pode esquecer o recorte ══════

def _literais(no: ast.AST) -> str:
    """O texto das strings literais de uma expressão (concatenações inclusive)."""
    return "".join(
        x.value for x in ast.walk(no)
        if isinstance(x, ast.Constant) and isinstance(x.value, str))


def _chama_o_recorte(no: ast.AST) -> bool:
    return any(isinstance(x, ast.Call) and isinstance(x.func, ast.Name)
               and x.func.id == "_so_trabalhos" for x in ast.walk(no))


def _executes_sobre_o_espelho():
    """Toda `cur.execute(...)` cujo SQL literal cita dbo.etl_chamado.

    A query da FILA não aparece aqui de propósito: ela é montada em variáveis
    (`base + novas + fim`) e não agrupa no SQL — quem agrupa é o Python.
    """
    arvore = ast.parse(FONTE.read_text(encoding="utf-8"))
    for no in ast.walk(arvore):
        if not (isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute)
                and no.func.attr == "execute" and no.args):
            continue
        sql = _literais(no.args[0])
        if "dbo.etl_chamado" not in sql or "etl_chamado_sync" in sql:
            continue
        yield no, sql


def test_toda_agregacao_sobre_o_espelho_aplica_o_recorte():
    """Uma conta nova que esqueça `_so_trabalhos` faz a aba Indicadores voltar
    a contar 113 onde a Fila conta 60 — e nada quebra, o número só fica
    errado. Por isso o teste é sobre o CÓDIGO, não sobre o resultado."""
    faltando = [sql[:110] for no, sql in _executes_sobre_o_espelho()
                if not _chama_o_recorte(no)]
    assert not faltando, (
        "agregação sobre dbo.etl_chamado sem `_so_trabalhos()` — ela contaria "
        "o pedido e a tarefa como dois trabalhos:\n  - "
        + "\n  - ".join(faltando))


def test_o_anti_drift_esta_realmente_olhando_alguma_coisa():
    """Um teste que não encontra nada passa para sempre. Este prende o piso:
    se o módulo for reorganizado e as queries deixarem de ser vistas, é aqui
    que aparece — e não no teste acima, que ficaria verde e vazio."""
    achadas = list(_executes_sobre_o_espelho())
    assert len(achadas) >= 12, (
        f"o varredor só achou {len(achadas)} agregações; ele já achou 15. "
        "Se as queries mudaram de forma, ajuste _executes_sobre_o_espelho — "
        "não baixe este número sem olhar.")
