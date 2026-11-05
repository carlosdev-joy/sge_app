"""Migration 200 — versão da F4 do agente Terminal (escrita com confirmação). Mesmo formato da 196/198."""
from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
MIGS = RAIZ / "sql" / "migrations"
MIG = MIGS / "200_versao_agente_terminal_escrita.sql"
_TITULO = re.compile(r"DECLARE @titulo NVARCHAR\(200\) = N'([^']+)';")


def test_titulo_proprio_entre_todas_as_versoes():
    titulos = [m.group(1) for p in sorted(MIGS.glob("*_versao_*.sql"))
               if (m := _TITULO.search(p.read_text(encoding="utf-8")))]
    assert titulos.count("Agente Terminal — escrita com confirmação") == 1 and len(set(titulos)) == len(titulos)


def test_idempotente_funcional_e_com_release_note():
    sql = MIG.read_text(encoding="utf-8")
    assert "ELSE IF EXISTS (SELECT 1 FROM dbo.etl_versao_ferramenta WHERE titulo = @titulo)" in sql
    assert "SET @nova = CONCAT(@maior, '.', @menor + 1, '.0');" in sql
    assert "config_key = 'app_version'" in sql and "config_key = 'app_release_name'" in sql
    assert "docs/release-notes/agente-terminal-f4.md" in sql and (RAIZ / "docs/release-notes/agente-terminal-f4.md").is_file()
    assert sql.rstrip().endswith("GO") and "enviar" not in MIG.name


def test_numeracao_sequencial_sem_lacuna_ate_a_200():
    nums = sorted(int(p.name[:3]) for p in MIGS.glob("[0-9][0-9][0-9]_*.sql"))
    assert nums[-1] >= 200 and 200 in nums
    assert all(b - a == 1 for a, b in zip(nums[-30:], nums[-29:])), "sem lacuna na numeração recente"
