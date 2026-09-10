"""
Anti-drift: api/services/job_params.py × dags/utils/ds_params.py.

As duas árvores rodam em containers diferentes e o repo nunca importou uma da
outra, então o cálculo de data (meses → âncora → dias → formato) e a descrição
existem em DUAS cópias. A prévia da tela vem da API; o valor que vai ao dsjob
vem do worker. Se as cópias divergirem, a tela promete um valor e o job recebe
outro — e nenhum teste unitário de uma árvore só enxerga isso.

Este arquivo importa AS DUAS e cobra igualdade de valor E descrição na tabela do
§4 da spec docs/spec-parametros-job-datastage.md e nas bordas.
"""
from __future__ import annotations

import inspect
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "dags"))
from services import job_params as api_jp  # noqa: E402  (pythonpath=api)
from utils import ds_params as dag_jp      # noqa: E402

CASOS = [
    # (base, origem, meses, ancora, dias, formato)
    (date(2026, 9, 9), "data_referencia", -1, "inicio_mes", 0, None),
    (date(2026, 9, 9), "data_referencia", -1, "fim_mes", 0, None),
    (date(2026, 9, 9), "data_logica", 0, None, -1, "%Y%m%d"),
    (date(2026, 9, 9), "data_execucao", 0, "fim_mes", 0, "%d/%m/%Y"),
    (date(2026, 9, 9), "data_referencia", -3, "inicio_trimestre", 0, None),
    (date(2026, 9, 9), "data_referencia", 0, None, 0, "%Y%m"),
    (date(2026, 9, 9), "data_referencia", 0, "inicio_semana", -7, None),
    (date(2026, 1, 31), "data_referencia", -1, None, 0, None),
    (date(2026, 3, 31), "data_referencia", -1, None, 0, None),
    (date(2024, 3, 31), "data_referencia", -1, "fim_mes", 0, None),
    (date(2026, 4, 30), "data_referencia", 1, None, 0, None),
    (date(2026, 4, 30), "data_referencia", -1, "fim_mes", 0, None),
    (date(2026, 1, 20), "data_referencia", -3, "inicio_trimestre", 0, None),
    (date(2026, 1, 20), "data_referencia", -3, "fim_trimestre", 0, None),
    (date(2026, 12, 15), "data_referencia", 1, "fim_ano", 0, "%Y-%m-%d %H:%M:%S"),
    (date(2026, 9, 7), "data_referencia", 0, "inicio_semana", 0, None),
    (date(2026, 9, 13), "data_referencia", 0, "fim_semana", 0, None),
    (date(2026, 9, 9), "data_referencia", 2, None, 10, None),
    (date(2026, 9, 9), "data_referencia", -120, None, 3660, None),
]


@pytest.mark.parametrize("base, origem, meses, ancora, dias, formato", CASOS)
def test_valor_e_descricao_iguais_nas_duas_arvores(base, origem, meses, ancora, dias, formato):
    v_api = api_jp.formatar(api_jp.calcular_data(base, meses, ancora, dias), formato)
    v_dag = dag_jp.formatar(dag_jp.calcular_data(base, meses, ancora, dias), formato)
    assert v_api == v_dag
    assert (api_jp.descrever(base, origem, meses, ancora, dias, formato)
            == dag_jp.descrever(base, origem, meses, ancora, dias, formato))


def test_vocabulario_igual():
    for nome in ("DS_PARAM_TYPES", "DS_PARAM_SOURCES", "DS_SOURCES_DATA", "DS_PARAM_ANCORAS",
                 "FORMATO_PADRAO", "ENCRYPTED_MASCARA", "ROTULO_ORIGEM", "ROTULO_ANCORA"):
        assert getattr(api_jp, nome) == getattr(dag_jp, nome), nome


@pytest.mark.parametrize("funcao", ["deslocar_meses", "ancorar", "calcular_data", "formatar",
                                    "_plural", "descrever", "parse_data"])
def test_codigo_fonte_das_funcoes_espelhadas_e_identico(funcao):
    """Além do comportamento na tabela, o TEXTO das funções: um `if` novo numa
    cópia só apareceria na tabela se alguém lembrasse de acrescentar o caso."""
    assert inspect.getsource(getattr(api_jp, funcao)) == inspect.getsource(getattr(dag_jp, funcao))


def test_parse_data_igual():
    for v in ("2026-09-09", " 2026-09-09 ", "09/09/2026", "", None, date(2026, 9, 9)):
        assert api_jp.parse_data(v) == dag_jp.parse_data(v)
