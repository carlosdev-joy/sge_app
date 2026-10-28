"""Migration 144 — versão 2.6.4 do Card 3 do PIO. Só registra a versão."""
from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
MIGS = RAIZ / "sql" / "migrations"
MIG = MIGS / "144_versao_pio_card3_foto.sql"
_TITULO = re.compile(r"DECLARE @titulo NVARCHAR\(200\) = N'([^']+)';")


def test_titulo_proprio_entre_todas_as_versoes():
    titulos = [m.group(1) for p in sorted(MIGS.glob("*_versao_*.sql"))
               if (m := _TITULO.search(p.read_text(encoding="utf-8")))]
    assert titulos.count("Card 3 do PIO lê a foto diária") == 1
    assert len(set(titulos)) == len(titulos), titulos


def test_registra_2_6_4_idempotente_e_sincroniza_a_versao():
    sql = MIG.read_text(encoding="utf-8")
    assert "DECLARE @versao NVARCHAR(20)  = N'2.6.4';" in sql
    assert "WHERE titulo = @titulo OR versao = @versao" in sql
    assert "config_key = 'app_version'" in sql and "config_key = 'app_release_name'" in sql
    assert sql.rstrip().endswith("GO")
    assert (RAIZ / "docs/release-notes/pio-card3-foto.md").is_file()


def test_nao_toca_nas_tabelas_do_pio():
    sql = MIG.read_text(encoding="utf-8").upper()
    codigo = "\n".join(l for l in sql.splitlines() if not l.strip().startswith("--"))
    for tabela in ("ORQ_CARD0", "PIO_"):
        assert tabela not in codigo
    for verbo in ("DROP ", "TRUNCATE", "ALTER ", "CREATE "):
        assert verbo not in codigo
