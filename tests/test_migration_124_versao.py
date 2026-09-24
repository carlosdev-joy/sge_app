"""Migration 124 — versão da entrega "cards + tempos", no formato da 123.

Entrega pequena: +1 no TERCEIRO número (2.3.0 → 2.3.1). Comportamento provado
no SQL Server do DEV num banco temporário (123 e 124 em sequência, cada uma 2×:
2.2.0 → 2.3.0 → 2.3.1). Aqui se prende a forma, como no teste da 123.
"""
from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
MIG = RAIZ / "sql" / "migrations" / "124_versao_agentes_cards_tempos.sql"
MIG123 = RAIZ / "sql" / "migrations" / "123_versao_agentes_banco.sql"


def _sql() -> str:
    return MIG.read_text(encoding="utf-8")


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
