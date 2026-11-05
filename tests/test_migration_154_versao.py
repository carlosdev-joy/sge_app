"""Migration 154 — versão 2.6.13 do agente Terminal na `main` (linha do PIO). Só registra a versão."""
from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
MIGS = RAIZ / "sql" / "migrations"
MIG = MIGS / "154_versao_agente_terminal.sql"
_TITULO = re.compile(r"DECLARE @titulo NVARCHAR\(200\) = N'([^']+)';")


def test_titulo_proprio_entre_todas_as_versoes():
    titulos = [m.group(1) for p in sorted(MIGS.glob("*_versao_*.sql"))
               if (m := _TITULO.search(p.read_text(encoding="utf-8")))]
    assert titulos.count("Agente Terminal em /agentes") == 1
    assert len(set(titulos)) == len(titulos), titulos


def test_registra_2_6_13_idempotente_e_sincroniza_a_versao():
    sql = MIG.read_text(encoding="utf-8")
    assert "DECLARE @versao NVARCHAR(20)  = N'2.6.13';" in sql
    assert "WHERE titulo = @titulo OR versao = @versao" in sql
    assert "config_key = 'app_version'" in sql and "config_key = 'app_release_name'" in sql
    assert sql.rstrip().endswith("GO")
    assert (RAIZ / "docs/release-notes/agente-terminal-main.md").is_file()


def test_so_registra_versao():
    codigo = "\n".join(l for l in MIG.read_text(encoding="utf-8").upper().splitlines() if not l.strip().startswith("--"))
    for verbo in ("DROP ", "TRUNCATE", "ALTER ", "CREATE "):
        assert verbo not in codigo


def test_numeracao_sequencial_sem_lacuna_ate_a_154():
    nums = sorted(int(p.name[:3]) for p in MIGS.glob("[0-9][0-9][0-9]_*.sql"))
    assert 153 in nums and 154 in nums
    assert all(b - a == 1 for a, b in zip(nums[-30:], nums[-29:])), "sem lacuna na numeração recente"
