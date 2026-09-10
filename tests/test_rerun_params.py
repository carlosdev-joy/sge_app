"""
Sobreposição de parâmetros DataStage na reexecução — api/services/rerun_params.py
(F5 da spec docs/spec-parametros-job-datastage.md).

  1. parametros_da_previa: só etapas DataStage do conjunto limpo; defaults do
     pipeline entram `condicional` e a etapa sobrepõe por nome exato; o valor
     efetivo é calculado pela referência (mês anterior, 31/03) pelo MESMO
     módulo da tela; Encrypted sai `***` e não é editável; sem referência a
     origem de data fica sem valor e diz por quê.
  2. validar_overrides: job não DataStage/fora do pipeline, parâmetro
     inexistente (caixa exata), Encrypted, valor pelo tipo, repetido, sem a 109.
  3. gravar/apagar: replace por corrida, `?` (árvore api/), criado_por.

Cursor de mentira que responde por trecho do SQL. Nada toca banco.
"""
from __future__ import annotations

import os
import sys
from datetime import date
from unittest.mock import MagicMock

import pytest

if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()
os.environ.setdefault("MSSQL_CONN_STR", "__mock__")
from api.main import app  # noqa: E402,F401

from services import rerun_params as RP  # noqa: E402


def _linha(nome, tipo="String", origem="fixo", valor=None, meses=None, ancora=None, dias=None, formato=None):
    return (nome, tipo, valor, origem, meses, ancora, dias, formato)


class _Cursor:
    def __init__(self, jobs=None, etapa=None, pipeline=None, tabelas=("etl_pipeline_param", "etl_job_param_override"),
                 tem_107=True):
        self.jobs = jobs or []                 # (job_name, job_type)
        self.etapa = etapa or []               # (job_name, *linha)
        self.pipeline = pipeline or []         # linha
        self.tabelas, self.tem_107 = set(tabelas), tem_107
        self.executados: list[tuple[str, tuple]] = []
        self._sql, self._params = "", ()

    def execute(self, sql, params=None):
        self._sql, self._params = sql, tuple(params or ())
        self.executados.append((sql, self._params))

    def fetchone(self):
        if "INFORMATION_SCHEMA.TABLES" in self._sql:
            return (1 if self._params[0] in self.tabelas else 0,)
        if "INFORMATION_SCHEMA.COLUMNS" in self._sql:
            return (1 if self.tem_107 else 0,)
        return None

    def fetchall(self):
        if "FROM dbo.etl_pipeline_job " in self._sql:
            return self.jobs
        if "FROM dbo.etl_pipeline_job_param" in self._sql:
            return self.etapa
        if "FROM dbo.etl_pipeline_param" in self._sql:
            return self.pipeline
        return []


JOBS = [("SeqCarga", "datastage"), ("RodaProc", "storedproc"), ("Envia", "http")]


# ═══════════ 1. prévia ══════════════════════════════════════════════════════

def test_previa_mensal_com_default_e_sobreposicao_da_etapa():
    cur = _Cursor(
        jobs=JOBS,
        etapa=[("SeqCarga",) + _linha("pDataIni", "Date", "data_referencia", meses=-1, ancora="inicio_mes"),
               ("SeqCarga",) + _linha("pAmb", valor="HML"),
               ("SeqCarga",) + _linha("pSenha", "Encrypted", valor="token")],
        pipeline=[_linha("pAmb", valor="PRD"), _linha("pDataFim", "Date", "data_referencia", meses=-1, ancora="fim_mes")],
    )
    out = RP.parametros_da_previa(cur, "PIPE", ["SeqCarga", "RodaProc", "Envia"], date(2026, 9, 9))
    assert [e["job_name"] for e in out] == ["SeqCarga"]          # só a etapa DataStage
    por = {it["param_name"]: it for it in out[0]["itens"]}
    assert por["pDataIni"]["valor_efetivo"] == "2026-08-01" and por["pDataIni"]["fonte"] == "etapa"
    assert por["pDataIni"]["descricao"] == "referência 2026-09-09 → -1 mês → início do mês → 2026-08-01"
    assert por["pDataFim"]["valor_efetivo"] == "2026-08-31" and por["pDataFim"]["fonte"] == "pipeline"
    assert por["pDataFim"]["condicional"] is True
    assert por["pAmb"]["valor_efetivo"] == "HML" and por["pAmb"]["fonte"] == "etapa"   # etapa vence o default
    assert por["pSenha"]["valor_efetivo"] == "***" and por["pSenha"]["editavel"] is False
    assert "token" not in str(out)
    assert all(it["editavel"] for n, it in por.items() if n != "pSenha")


def test_previa_borda_31_de_marco_e_caixa_do_nome_da_etapa():
    cur = _Cursor(jobs=JOBS, etapa=[("SeqCarga",) + _linha("pFim", "Date", "data_referencia", meses=-1, ancora="fim_mes")])
    out = RP.parametros_da_previa(cur, "PIPE", ["seqcarga"], "2026-03-31")   # casefold + string ISO
    assert out[0]["job_name"] == "SeqCarga"
    assert out[0]["itens"][0]["valor_efetivo"] == "2026-02-28"


def test_previa_sem_referencia_diz_que_calcula_no_disparo():
    cur = _Cursor(jobs=JOBS, etapa=[("SeqCarga",) + _linha("pD", "String", "data_referencia"),
                                    ("SeqCarga",) + _linha("pAmb", valor="PRD")])
    out = RP.parametros_da_previa(cur, "PIPE", ["SeqCarga"], None)
    por = {it["param_name"]: it for it in out[0]["itens"]}
    assert por["pD"]["valor_efetivo"] is None and "desconhecida" in por["pD"]["descricao"]
    assert por["pAmb"]["valor_efetivo"] == "PRD"


def test_previa_sem_parametro_nenhum_e_vazia():
    assert RP.parametros_da_previa(_Cursor(jobs=JOBS), "PIPE", ["SeqCarga"], date(2026, 9, 9)) == []


def test_previa_sem_migration_107_nem_108_nao_quebra():
    cur = _Cursor(jobs=JOBS, tabelas=(), tem_107=False)
    assert RP.parametros_da_previa(cur, "PIPE", ["SeqCarga"], date(2026, 9, 9)) == []


# ═══════════ 2. validação ═══════════════════════════════════════════════════

def _cur_valid():
    return _Cursor(jobs=JOBS,
                   etapa=[("SeqCarga",) + _linha("pDataIni", "Date", "data_referencia", meses=-1, ancora="inicio_mes",
                                                 formato="%Y%m%d"),
                          ("SeqCarga",) + _linha("pDataFixa", "Date", valor="2026-01-01"),
                          ("SeqCarga",) + _linha("pQtd", "Integer", valor="1"),
                          ("SeqCarga",) + _linha("pSenha", "Encrypted", valor="token")],
                   pipeline=[_linha("pAmb", valor="PRD")])


def test_validar_aceita_valor_pelo_tipo_da_linha():
    linhas, erros = RP.validar_overrides(_cur_valid(), "PIPE", [
        # origem de data: o valor vai no FORMATO DO JOB (o mesmo que a prévia mostra)
        {"job_name": "seqcarga", "param_name": "pDataIni", "param_value": "20260901"},   # job em outra caixa
        {"job_name": "SeqCarga", "param_name": "pAmb", "param_value": "HML"},            # default do pipeline
        {"job_name": "SeqCarga", "param_name": "pQtd", "param_value": "7"},
        {"job_name": "SeqCarga", "param_name": "pDataFixa", "param_value": "2026-02-01"},
    ])
    assert erros == []
    assert linhas == [
        {"job_name": "SeqCarga", "param_name": "pDataIni", "param_value": "20260901"},
        {"job_name": "SeqCarga", "param_name": "pAmb", "param_value": "HML"},
        {"job_name": "SeqCarga", "param_name": "pQtd", "param_value": "7"},
        {"job_name": "SeqCarga", "param_name": "pDataFixa", "param_value": "2026-02-01"},
    ]


@pytest.mark.parametrize("item, trecho", [
    ({"job_name": "RodaProc", "param_name": "pQtd", "param_value": "1"}, "não é uma etapa DataStage"),
    ({"job_name": "Inexistente", "param_name": "pQtd", "param_value": "1"}, "não é uma etapa DataStage"),
    ({"job_name": "SeqCarga", "param_name": "pqtd", "param_value": "1"}, "não existe"),          # caixa exata
    ({"job_name": "SeqCarga", "param_name": "pSenha", "param_value": "x"}, "Encrypted"),
    ({"job_name": "SeqCarga", "param_name": "pQtd", "param_value": "abc"}, "não é um Integer válido"),
    ({"job_name": "SeqCarga", "param_name": "pDataFixa", "param_value": "01/09/2026"}, "não é um Date válido"),
    ({"job_name": "SeqCarga", "param_name": "pDataIni", "param_value": "a\nb"}, "quebra de linha"),
    ({"job_name": "SeqCarga", "param_name": "pQtd", "param_value": ""}, "valor obrigatório"),
    ("lixo", "inválido"),
])
def test_validar_recusa(item, trecho):
    linhas, erros = RP.validar_overrides(_cur_valid(), "PIPE", [item])
    assert linhas == [] and erros and trecho in erros[0], erros


def test_validar_repetido_e_lista_invalida():
    _, erros = RP.validar_overrides(_cur_valid(), "PIPE", [
        {"job_name": "SeqCarga", "param_name": "pQtd", "param_value": "1"},
        {"job_name": "SeqCarga", "param_name": "pQtd", "param_value": "2"}])
    assert erros == ["SeqCarga: 'pQtd' repetido"]
    assert RP.validar_overrides(_cur_valid(), "PIPE", "x") == ([], ["parametros deve ser uma lista"])
    assert RP.validar_overrides(_cur_valid(), "PIPE", []) == ([], [])


def test_validar_sem_migration_109_e_erro_claro():
    cur = _Cursor(jobs=JOBS, tabelas=("etl_pipeline_param",))
    _, erros = RP.validar_overrides(cur, "PIPE", [{"job_name": "SeqCarga", "param_name": "pQtd", "param_value": "1"}])
    assert erros == [RP.ERRO_SEM_109]


# ═══════════ 3. gravação / compensação ══════════════════════════════════════

def test_gravar_faz_replace_por_corrida_com_criado_por():
    cur = _Cursor()
    RP.gravar_overrides(cur, "PIPE", "manual__2026-09-09", [
        {"job_name": "SeqCarga", "param_name": "pDataIni", "param_value": "2026-09-01"},
        {"job_name": "SeqCarga", "param_name": "pQtd", "param_value": "7"},
    ], "C123456")
    sqls = [e[0] for e in cur.executados]
    assert sqls[0].startswith("DELETE FROM dbo.etl_job_param_override") and cur.executados[0][1] == ("PIPE", "manual__2026-09-09")
    assert len(sqls) == 3 and all(s.startswith("INSERT INTO dbo.etl_job_param_override") for s in sqls[1:])
    assert cur.executados[1][1] == ("PIPE", "SeqCarga", "manual__2026-09-09", "pDataIni", "2026-09-01", "C123456")
    assert all("%s" not in s for s in sqls)


def test_sobreposicoes_anteriores_lista_nomes_nunca_valores():
    cur = _Cursor()
    cur.fetchall = lambda: [("SeqCarga", "pDataFim"), ("SeqCarga", "pQtd")]
    assert RP.sobreposicoes_anteriores(cur, "PIPE", "run-1") == ["SeqCarga.pDataFim", "SeqCarga.pQtd"]
    sql, params = cur.executados[-1]
    assert "param_value" not in sql and params == ("PIPE", "run-1")
    assert RP.sobreposicoes_anteriores(cur, "PIPE", "") == []
    assert RP.sobreposicoes_anteriores(_Cursor(tabelas=()), "PIPE", "run-1") == []


def test_apagar_e_por_pipeline_e_corrida():
    cur = _Cursor()
    RP.apagar_overrides(cur, "PIPE", "run-1")
    assert cur.executados == [("DELETE FROM dbo.etl_job_param_override WHERE pipeline_name=? AND dag_run_id=?", ("PIPE", "run-1"))]
