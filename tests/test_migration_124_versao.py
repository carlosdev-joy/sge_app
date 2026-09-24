"""Migrations 124 e 125 — versões das entregas de ajuste, no formato da 123.

Entrega pequena: +1 no TERCEIRO número (2.3.0 → 2.3.1). Comportamento provado
no SQL Server do DEV num banco temporário (123 e 124 em sequência, cada uma 2×:
2.2.0 → 2.3.0 → 2.3.1). Aqui se prende a forma, como no teste da 123.
"""
from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
import pytest

MIGS = [RAIZ / "sql" / "migrations" / n for n in ("124_versao_agentes_cards_tempos.sql", "125_versao_admin_agentes.sql")]
MIG123 = RAIZ / "sql" / "migrations" / "123_versao_agentes_banco.sql"
_ATUAL = {"mig": MIGS[0]}


@pytest.fixture(params=MIGS, ids=lambda p: p.name[:3], autouse=True)
def _cada_migration(request):
    _ATUAL["mig"] = request.param


def _sql() -> str:
    return _ATUAL["mig"].read_text(encoding="utf-8")


def test_titulos_das_versoes_sao_todos_diferentes():
    titulos = [re.search(r"DECLARE @titulo NVARCHAR\(200\) = N'([^']+)';", p.read_text(encoding="utf-8")).group(1)
               for p in [MIG123, *MIGS]]
    assert len(set(titulos)) == len(titulos), titulos


def test_um_lote_so_e_titulo_proprio():
    sql = _sql()
    assert not re.search(r"^\s*GO\s*$", sql, re.M | re.I)
    titulo = re.search(r"DECLARE @titulo NVARCHAR\(200\) = N'([^']+)';", sql).group(1)
    titulo123 = re.search(r"DECLARE @titulo NVARCHAR\(200\) = N'([^']+)';",
                          MIG123.read_text(encoding="utf-8")).group(1)
    assert titulo != titulo123  # o título é a chave: igual, a 124 nunca registraria
    assert "ELSE IF EXISTS (SELECT 1 FROM dbo.etl_versao_ferramenta WHERE titulo = @titulo)" in sql


def test_sobe_o_terceiro_numero_com_a_regra_da_123():
    sql = _sql()
    assert "SET @nova = CONCAT(@maior, '.', @menor, '.', @patch + 1);" in sql
    assert "SELECT TOP 1 @maior = a, @menor = b, @patch = c" in sql
    assert "ORDER BY a DESC, b DESC, c DESC, d DESC" in sql
    assert "[ATENÇÃO] há versões fora do padrão" in sql
    for chave in ("app_version", "app_release_name"):
        assert f"WHERE config_key = '{chave}'" in sql


def test_markdown_sem_aspa_solta():
    corpo = re.search(r"VALUES \(@nova, @titulo, N'(.*?)', 'deploy'\);", _sql(), re.S).group(1)
    assert "'" not in corpo.replace("''", "")


def test_titulo_ascii_porque_app_release_name_e_varchar():
    """`etl_app_config.config_value` é VARCHAR (não Unicode): um "›" no título
    viraria "?" conforme a collation do servidor."""
    titulo = re.search(r"DECLARE @titulo NVARCHAR\(200\) = N'([^']+)';", _sql()).group(1)
    assert titulo.isascii(), titulo
