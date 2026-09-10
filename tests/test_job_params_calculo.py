"""
Cálculo de data dos parâmetros DataStage (api/services/job_params.py) —
spec docs/spec-parametros-job-datastage.md §4.

O contrato é a ORDEM: meses → âncora → dias → formato. A tabela de exemplos e
as bordas (31/03 −1 mês, bissexto, virada de ano, semana seg–dom) são as
mesmas que o teste anti-drift (F2) vai cobrar da cópia em dags/utils/ds_params.py.

Módulo puro — importado direto, sem app.
"""
from __future__ import annotations

from datetime import date

import pytest

from services import job_params as jp

REF = date(2026, 9, 9)


# ── Tabela do §4 (referência 2026-09-09) ─────────────────────────────────────

@pytest.mark.parametrize("meses, ancora, dias, formato, esperado", [
    (-1, "inicio_mes", 0, "%Y-%m-%d", "2026-08-01"),      # pDataIni do mês anterior
    (-1, "fim_mes", 0, "%Y-%m-%d", "2026-08-31"),         # pDataFim do mês anterior
    (0, None, -1, "%Y%m%d", "20260908"),                  # D-1 compacto
    (0, "fim_mes", 0, "%d/%m/%Y", "30/09/2026"),          # último dia do mês corrente
    (-3, "inicio_trimestre", 0, "%Y-%m-%d", "2026-04-01"),  # início do trimestre anterior
    (0, None, 0, "%Y%m", "202609"),                       # ano-mês de referência
    (0, "inicio_semana", -7, "%Y-%m-%d", "2026-08-31"),   # semana passada, segunda
    (0, None, 0, None, "2026-09-09"),                     # formato NULL = padrão
])
def test_tabela_da_spec(meses, ancora, dias, formato, esperado):
    assert jp.formatar(jp.calcular_data(REF, meses, ancora, dias), formato) == esperado


# ── Bordas de mês ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("base, meses, esperado", [
    (date(2026, 1, 31), -1, date(2025, 12, 31)),   # virada de ano para trás
    (date(2026, 3, 31), -1, date(2026, 2, 28)),    # dia truncado ao último válido
    (date(2024, 3, 31), -1, date(2024, 2, 29)),    # bissexto
    (date(2026, 4, 30), 1, date(2026, 5, 30)),     # dia cabe: mantém
    (date(2026, 12, 15), 1, date(2027, 1, 15)),    # virada de ano para frente
    (date(2026, 9, 9), 0, date(2026, 9, 9)),       # zero = identidade
    (date(2026, 9, 9), -120, date(2016, 9, 9)),    # limite da faixa
])
def test_deslocar_meses(base, meses, esperado):
    assert jp.deslocar_meses(base, meses) == esperado


def test_ordem_meses_antes_da_ancora_e_o_que_faz_mes_anterior_funcionar():
    # 30/04: ancorar ANTES daria 30/04 → 30/03 (não é fim de março).
    assert jp.calcular_data(date(2026, 4, 30), -1, "fim_mes") == date(2026, 3, 31)
    # 31/03 −1 mês = 28/02 e fim_mes confirma 28/02.
    assert jp.calcular_data(date(2026, 3, 31), -1, "fim_mes") == date(2026, 2, 28)
    assert jp.calcular_data(date(2024, 3, 31), -1, "fim_mes") == date(2024, 2, 29)


@pytest.mark.parametrize("base, ancora, esperado", [
    (date(2026, 9, 9), "inicio_mes", date(2026, 9, 1)),
    (date(2024, 2, 10), "fim_mes", date(2024, 2, 29)),
    (date(2026, 9, 9), "inicio_trimestre", date(2026, 7, 1)),
    (date(2026, 9, 9), "fim_trimestre", date(2026, 9, 30)),
    (date(2026, 1, 15), "inicio_trimestre", date(2026, 1, 1)),
    (date(2026, 12, 15), "fim_trimestre", date(2026, 12, 31)),
    (date(2026, 9, 9), "inicio_ano", date(2026, 1, 1)),
    (date(2026, 9, 9), "fim_ano", date(2026, 12, 31)),
    (date(2026, 9, 9), "inicio_semana", date(2026, 9, 7)),   # quarta → segunda
    (date(2026, 9, 9), "fim_semana", date(2026, 9, 13)),     # quarta → domingo
    (date(2026, 9, 7), "inicio_semana", date(2026, 9, 7)),   # segunda é ela mesma
    (date(2026, 9, 13), "fim_semana", date(2026, 9, 13)),    # domingo é ele mesmo
    (date(2026, 9, 9), None, date(2026, 9, 9)),
    (date(2026, 9, 9), "", date(2026, 9, 9)),
])
def test_ancorar(base, ancora, esperado):
    assert jp.ancorar(base, ancora) == esperado


def test_ancora_desconhecida_estoura():
    with pytest.raises(ValueError):
        jp.ancorar(REF, "fim_do_mundo")


def test_trimestre_anterior_a_partir_de_janeiro_cruza_o_ano():
    assert jp.calcular_data(date(2026, 1, 20), -3, "inicio_trimestre") == date(2025, 10, 1)
    assert jp.calcular_data(date(2026, 1, 20), -3, "fim_trimestre") == date(2025, 12, 31)


# ── Descrição (o rastro) ─────────────────────────────────────────────────────

def test_descrever_mes_anterior():
    assert jp.descrever(REF, "data_referencia", -1, "fim_mes") == \
        "referência 2026-09-09 → -1 mês → fim do mês → 2026-08-31"


def test_descrever_so_dias_com_formato():
    assert jp.descrever(REF, "data_logica", 0, None, -1, "%Y%m%d") == \
        "data lógica 2026-09-09 → -1 dia → 20260908"


def test_descrever_plural_e_sinal():
    assert jp.descrever(REF, "data_execucao", 2, None, 10) == \
        "data da execução 2026-09-09 → +2 meses → +10 dias → 2026-11-19"


def test_descrever_sem_calculo_e_so_a_data():
    assert jp.descrever(REF, "data_referencia") == "referência 2026-09-09 → 2026-09-09"


# ── parse_data ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("entrada, esperado", [
    ("2026-09-09", date(2026, 9, 9)),
    (" 2026-09-09 ", date(2026, 9, 9)),
    (date(2026, 9, 9), date(2026, 9, 9)),
    ("09/09/2026", None),
    ("", None),
    (None, None),
    ("2026-02-30", None),
])
def test_parse_data(entrada, esperado):
    assert jp.parse_data(entrada) == esperado
