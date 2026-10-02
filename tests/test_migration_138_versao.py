"""Migration 138 — versão da entrega `{coluna:…}` (spec-email-coluna-sql).

Entrega funcional: +1 no SEGUNDO número e zera o terceiro (2.5.3 → 2.6.0), no
formato da 134. Aplicada 2× no SQL Server do DEV em 02/10/2026 (2.6.0, depois
`[SKIP]`). Aqui se prende a forma.
"""
from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
MIGS = RAIZ / "sql" / "migrations"
MIG = MIGS / "138_versao_email_coluna_sql.sql"
_TITULO = re.compile(r"DECLARE @titulo NVARCHAR\(200\) = N'([^']+)';")


def test_titulo_proprio_entre_todas_as_versoes():
    titulos = [m.group(1) for p in sorted(MIGS.glob("*_versao_*.sql"))
               if (m := _TITULO.search(p.read_text(encoding="utf-8")))]
    assert titulos.count("E-mail: valor de cada coluna do SQL") == 1
    assert len(set(titulos)) == len(titulos), titulos


def test_idempotente_e_sobe_o_segundo_numero():
    sql = MIG.read_text(encoding="utf-8")
    assert "ELSE IF EXISTS (SELECT 1 FROM dbo.etl_versao_ferramenta WHERE titulo = @titulo)" in sql
    assert "SET @nova = CONCAT(@maior, '.', @menor + 1, '.0');" in sql
    assert "config_key = 'app_version'" in sql and "config_key = 'app_release_name'" in sql
    assert "docs/release-notes/email-coluna-sql.md" in sql
    assert (RAIZ / "docs/release-notes/email-coluna-sql.md").is_file()
