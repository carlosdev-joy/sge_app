"""
Testes das validações do nó de Decisão no backend (api/routers/jobs.py).

São funções puras (não tocam banco): identificador de tabela, SQL read-only,
validação da condição e detecção de ciclo (deps + arestas do branch).

routers.jobs NÃO é importado no topo do módulo: na coleção, isso carregaria
routers.* contra o airflow stubado (sys.modules) pelos testes de factory e
poluiria o app usado por outros testes. Importamos via fixture, em tempo de
teste, depois que o app já carregou.
"""
from __future__ import annotations

import pytest


@pytest.fixture(scope="module")
def J():
    import routers.jobs as _j
    return _j


_JOBS = {"Decisao", "JobA", "JobB", "JobC"}


def _cond_contagem(**ov):
    base = {
        "tipo": "contagem", "tabela": "dbo.FatoVendas", "operador": ">",
        "valor": 10000, "ramo_verdadeiro": ["JobB"], "ramo_falso": ["JobC"],
    }
    base.update(ov)
    return base


# ───────────────────────── identificador / SQL ─────────────────────────────

@pytest.mark.parametrize("ok", ["dbo.FatoVendas", "Tabela", "BI.dbo.X"])
def test_valid_table_ident_aceita(J, ok):
    assert J._valid_table_ident(ok) is True


@pytest.mark.parametrize("ruim", [
    "dbo.Fato; DROP TABLE x", "a.b.c.d", "", "dbo.[Fato]", "1tabela", "dbo.Fato Vendas",
])
def test_valid_table_ident_rejeita(J, ruim):
    assert J._valid_table_ident(ruim) is False


@pytest.mark.parametrize("ok", [
    "SELECT 1", "  select count(*) from x ;  ", "WITH c AS (SELECT 1) SELECT * FROM c",
])
def test_valid_select_aceita(J, ok):
    assert J._valid_select(ok) is True


@pytest.mark.parametrize("ruim", [
    "DELETE FROM x", "SELECT 1; DROP TABLE x", "INSERT INTO x VALUES (1)",
    "EXEC sp_who", "", "SELECT * INTO y FROM x",
])
def test_valid_select_rejeita(J, ruim):
    assert J._valid_select(ruim) is False


# ───────────────────────── _validate_condition ─────────────────────────────

def test_condicao_contagem_valida(J):
    assert J._validate_condition(_cond_contagem(), _JOBS, "Decisao", None) == []


def test_condicao_query_valida(J):
    cond = {"tipo": "query", "sql": "SELECT MAX(f) FROM dbo.C", "operador": "=",
            "valor": 1, "ramo_verdadeiro": ["JobB"], "ramo_falso": []}
    assert J._validate_condition(cond, _JOBS, "Decisao", None) == []


def test_condicao_ausente(J):
    assert J._validate_condition(None, _JOBS, "Decisao", None)


def test_condicao_tipo_invalido(J):
    errs = J._validate_condition(_cond_contagem(tipo="regex"), _JOBS, "Decisao", None)
    assert any("tipo" in e for e in errs)


def test_condicao_operador_invalido(J):
    errs = J._validate_condition(_cond_contagem(operador="LIKE"), _JOBS, "Decisao", None)
    assert any("operador" in e for e in errs)


def test_condicao_valor_nao_numerico_contagem(J):
    errs = J._validate_condition(_cond_contagem(valor="abc"), _JOBS, "Decisao", None)
    assert any("numérico" in e for e in errs)


def test_condicao_tabela_invalida(J):
    errs = J._validate_condition(_cond_contagem(tabela="dbo.x; DROP"), _JOBS, "Decisao", None)
    assert any("tabela" in e for e in errs)


def test_condicao_ramo_job_inexistente(J):
    errs = J._validate_condition(_cond_contagem(ramo_verdadeiro=["Fantasma"]), _JOBS, "Decisao", None)
    assert any("não existe" in e for e in errs)


def test_condicao_ramo_autorreferencia(J):
    errs = J._validate_condition(_cond_contagem(ramo_falso=["Decisao"]), _JOBS, "Decisao", None)
    assert any("própria decisão" in e for e in errs)


def test_condicao_ramos_vazios(J):
    errs = J._validate_condition(
        _cond_contagem(ramo_verdadeiro=[], ramo_falso=[]), _JOBS, "Decisao", None)
    assert any("ao menos um job" in e for e in errs)


def test_condicao_query_nao_readonly(J):
    cond = {"tipo": "query", "sql": "DELETE FROM x", "operador": "=", "valor": 1,
            "ramo_verdadeiro": ["JobB"], "ramo_falso": []}
    errs = J._validate_condition(cond, _JOBS, "Decisao", None)
    assert any("read-only" in e for e in errs)


def test_condicao_conn_inexistente(J):
    cond = _cond_contagem(mssql_conn_id="nao_existe")
    errs = J._validate_condition(cond, _JOBS, "Decisao", {"mssql_default"})
    assert any("conexão" in e for e in errs)


# ───────────────────────────── ciclo ───────────────────────────────────────

def test_ciclo_detecta(J):
    adj = {"A": {"B"}, "B": {"C"}, "C": {"A"}}
    assert J._graph_has_cycle(adj) is True


def test_ciclo_ausente_em_branch_acyclic(J):
    # Decisao → JobB, JobC ; JobA → Decisao  (DAG, sem ciclo)
    adj = {"JobA": {"Decisao"}, "Decisao": {"JobB", "JobC"}, "JobB": set(), "JobC": set()}
    assert J._graph_has_cycle(adj) is False


def test_ciclo_branch_volta_para_dependencia(J):
    # JobB depende de JobA; a Decisao (após JobB) ramifica p/ JobA → ciclo
    adj = {"JobA": {"JobB"}, "JobB": {"Decisao"}, "Decisao": {"JobA"}}
    assert J._graph_has_cycle(adj) is True
