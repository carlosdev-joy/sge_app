"""A janela dos "próximos dias" nunca cai em cima de hoje.

O painel divide os prazos em três cartões que NÃO se sobrepõem — vencidas,
vencem hoje e vencem nos próximos dias — para que somar os três dê o total, e
não o total com o dia de hoje contado duas vezes. O terceiro cartão vai de
amanhã até a próxima sexta-feira.

Dois defeitos moraram nessa conta, e os dois davam número plausível:

  1. **Toda sexta-feira o cartão zerava.** `DATEADD(DAY, 6-DATEPART(WEEKDAY,
     GETDATE()), …)` devolve HOJE quando hoje é sexta, e o filtro é
     `prazo > hoje AND prazo <= fim` — condição impossível. Medido no dev em
     2026-08-28, uma sexta: 14 chamados venciam hoje, 16 venciam depois, e o
     cartão dizia **0**. A spec de origem tinha a proteção (o `|| 7` do
     JavaScript); ela se perdeu na tradução para SQL.
  2. **`DATEPART(WEEKDAY)` depende de `SET DATEFIRST`**, que varia por sessão e
     por idioma do login: a mesma consulta daria janelas diferentes conforme
     quem conecta. `DATEDIFF(DAY, 0, data) % 7` não depende de configuração —
     o dia 0 do SQL Server (1900-01-01) foi uma segunda-feira.

O teste estático roda sempre. O vivo pergunta ao SQL Server e SALTA onde não há
banco (CI e máquina de deploy) — visível no `-rs`, nunca silencioso.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

import pytest

if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()
os.environ.setdefault("MSSQL_CONN_STR", "__mock__")

from pathlib import Path  # noqa: E402

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "api"))
from routers.chamados import _proxima_sexta  # noqa: E402


# ═══════════ 1. contrato da expressão (roda sempre) ═════════════════════════

def test_a_janela_avanca_quando_hoje_e_o_limite() -> None:
    """O `CASE WHEN … = 0 THEN 7` é o `|| 7` da spec.

    Sem ele, na sexta-feira o cartão nasce vazio — no dia em que ele mais
    importa, porque é quando o operador decide o que ainda dá para fechar.
    """
    sql = _proxima_sexta()
    assert "THEN 7" in sql, (
        "sem o degrau de 7 dias, sexta-feira devolve HOJE e o filtro "
        "`prazo > hoje AND prazo <= fim` vira condição impossível")


def test_a_expressao_nao_depende_de_datefirst() -> None:
    """`DATEPART(WEEKDAY)` muda com a sessão; `DATEDIFF(DAY, 0, …)` não."""
    sql = _proxima_sexta()
    assert "DATEPART" not in sql.upper(), (
        "DATEPART(WEEKDAY) depende de SET DATEFIRST — a mesma consulta daria "
        "janelas diferentes conforme quem conecta")
    assert "DATEDIFF(DAY, 0," in sql


def test_a_janela_e_uma_data_e_nao_um_instante() -> None:
    """Comparar com `GETDATE()` cru deixaria de fora o que vence hoje à tarde."""
    assert "CAST(GETDATE() AS DATE)" in _proxima_sexta()


# ═══════════ 2. o que o banco responde (salta sem banco) ════════════════════

def _conectar():
    senha = os.getenv("ORQ_TEST_MSSQL_PASSWORD")
    if not senha:
        return None
    try:
        import pymssql
    except Exception:      # noqa: BLE001 — driver ausente é motivo de salto
        return None
    try:
        return pymssql.connect(
            server=os.getenv("ORQ_TEST_MSSQL_HOST", "127.0.0.1"),
            port=int(os.getenv("ORQ_TEST_MSSQL_PORT", "1433")),
            user=os.getenv("ORQ_TEST_MSSQL_USER", "sa"),
            password=senha,
            database=os.getenv("ORQ_TEST_MSSQL_DATABASE", "orquestra_dev"))
    except Exception:      # noqa: BLE001
        return None


# 24/08/2026 é uma segunda-feira. Sete dias seguidos cobrem a semana inteira,
# e o caso que interessa — sexta — está no meio, não numa borda esquecida.
DIAS = [
    ("2026-08-24", "segunda", "2026-08-28"),
    ("2026-08-25", "terça",   "2026-08-28"),
    ("2026-08-26", "quarta",  "2026-08-28"),
    ("2026-08-27", "quinta",  "2026-08-28"),
    # o caso do defeito: a janela vai para a sexta SEGUINTE, não para hoje
    ("2026-08-28", "sexta",   "2026-09-04"),
    ("2026-08-29", "sábado",  "2026-09-04"),
    ("2026-08-30", "domingo", "2026-09-04"),
]


@pytest.fixture(scope="module")
def banco():
    conn = _conectar()
    if conn is None:
        pytest.skip("banco dev indisponível — defina ORQ_TEST_MSSQL_PASSWORD")
    yield conn
    conn.close()


@pytest.mark.parametrize("data,dia,esperado", DIAS)
def test_a_proxima_sexta_no_banco(banco, data, dia, esperado) -> None:
    """A expressão real, avaliada pelo SQL Server, para cada dia da semana."""
    # A expressão do router é sobre GETDATE(); aqui a data é fixada para o
    # teste não depender do dia em que roda — teste de data que só passa hoje
    # é a pior espécie.
    sql = _proxima_sexta().replace("GETDATE()", f"CAST('{data}' AS DATETIME)")
    cur = banco.cursor()
    cur.execute(f"SELECT CONVERT(VARCHAR(10), {sql}, 120)")
    obtido = cur.fetchone()[0]
    cur.close()
    assert obtido == esperado, (
        f"partindo de {data} ({dia}), a janela deveria terminar em {esperado} "
        f"e terminou em {obtido}")


def test_a_janela_nunca_e_hoje(banco) -> None:
    """A afirmação que resume o defeito: o fim é sempre no futuro."""
    for data, dia, _ in DIAS:
        sql = _proxima_sexta().replace("GETDATE()", f"CAST('{data}' AS DATETIME)")
        cur = banco.cursor()
        cur.execute(f"SELECT CASE WHEN {sql} > CAST('{data}' AS DATE) THEN 1 ELSE 0 END")
        adiante = cur.fetchone()[0]
        cur.close()
        assert adiante == 1, (
            f"em {data} ({dia}) a janela terminou em cima do próprio dia — o "
            f"filtro `prazo > hoje AND prazo <= fim` não casaria com nada")
