"""Migration 140 — versão 2.6.1 do Card 1 do PIO (RITM0117336).

Registra só a versão; não toca nas tabelas do PIO. Idempotente (título ou versão).
"""
from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
MIGS = RAIZ / "sql" / "migrations"
MIG = MIGS / "140_versao_pio_card1_foto.sql"
_TITULO = re.compile(r"DECLARE @titulo NVARCHAR\(200\) = N'([^']+)';")


def test_titulo_proprio_entre_todas_as_versoes():
    titulos = [m.group(1) for p in sorted(MIGS.glob("*_versao_*.sql"))
               if (m := _TITULO.search(p.read_text(encoding="utf-8")))]
    assert titulos.count("Card 1 do PIO lê a foto diária") == 1
    assert len(set(titulos)) == len(titulos), titulos


def test_registra_2_6_1_idempotente_e_sincroniza_a_versao():
    sql = MIG.read_text(encoding="utf-8")
    assert "DECLARE @versao NVARCHAR(20)  = N'2.6.1';" in sql
    assert "WHERE titulo = @titulo OR versao = @versao" in sql
    assert "config_key = 'app_version'" in sql and "config_key = 'app_release_name'" in sql
    assert (RAIZ / "docs/release-notes/pio-card1-foto.md").is_file()


def test_nao_toca_nas_tabelas_do_pio():
    sql = MIG.read_text(encoding="utf-8").upper()
    codigo = "\n".join(l for l in sql.splitlines() if not l.strip().startswith("--"))
    for tabela in ("ORQ_CARD01", "PIO_"):
        assert tabela not in codigo, f"a migration de versão não pode mencionar {tabela}"
    for verbo in ("DROP ", "TRUNCATE", "ALTER ", "CREATE "):
        assert verbo not in codigo
