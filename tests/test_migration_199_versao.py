"""Migration 199 — versão da F3 do agente Terminal (leitura no servidor). Mesmo formato da 196/198."""
from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
MIGS = RAIZ / "sql" / "migrations"
MIG = MIGS / "199_versao_agente_terminal_leitura.sql"
_TITULO = re.compile(r"DECLARE @titulo NVARCHAR\(200\) = N'([^']+)';")


def test_titulo_proprio_entre_todas_as_versoes():
    titulos = [m.group(1) for p in sorted(MIGS.glob("*_versao_*.sql"))
               if (m := _TITULO.search(p.read_text(encoding="utf-8")))]
    assert titulos.count("Agente Terminal — leitura no servidor") == 1 and len(set(titulos)) == len(titulos)


def test_idempotente_funcional_e_com_release_note():
    sql = MIG.read_text(encoding="utf-8")
    assert "ELSE IF EXISTS (SELECT 1 FROM dbo.etl_versao_ferramenta WHERE titulo = @titulo)" in sql
    assert "SET @nova = CONCAT(@maior, '.', @menor + 1, '.0');" in sql
    assert "config_key = 'app_version'" in sql and "config_key = 'app_release_name'" in sql
    assert "docs/release-notes/agente-terminal-f3.md" in sql and (RAIZ / "docs/release-notes/agente-terminal-f3.md").is_file()
    assert sql.rstrip().endswith("GO") and "enviar" not in MIG.name


def test_numeracao_sequencial_sem_lacuna_ate_a_199():
    nums = sorted(int(p.name[:3]) for p in MIGS.glob("[0-9][0-9][0-9]_*.sql"))
    assert nums[-3:] == [197, 198, 199] or nums[-1] >= 199
    assert all(b - a == 1 for a, b in zip(nums[-30:], nums[-29:])), "sem lacuna na numeração recente"


def test_variaveis_novas_chegam_ao_container_da_api_e_estao_documentadas():
    compose = (RAIZ / "docker-compose.yaml").read_text(encoding="utf-8")
    exemplo = (RAIZ / ".env.dev.example").read_text(encoding="utf-8")
    nota = (RAIZ / "docs/release-notes/agente-terminal-f3.md").read_text(encoding="utf-8")
    for var in ("AF_SSH_HOST", "AF_SSH_PORT", "AF_SSH_USER", "AF_SSH_PASSWORD", "AF_SSH_KEY_FILE", "AF_SSH_KNOWN_HOSTS",
                "TERMINAL_SSH_AUTO_ADD", "TERMINAL_RAIZES_DATASTAGE", "TERMINAL_RAIZES_AIRFLOW",
                "TERMINAL_CONTAINERS_DATASTAGE", "TERMINAL_CONTAINERS_AIRFLOW"):
        assert f"{var}:" in compose or f"{var}: " in compose, f"{var} não é repassada ao container da API"
        assert f"{var}=" in exemplo, f"{var} não está no .env.dev.example"
        assert var in nota or var.split("_")[0] + "_" in nota, f"{var} não está documentada"
    # o que o código lê tem de estar no compose (anti-drift)
    fonte = (RAIZ / "api/services/agentes_terminal_ssh.py").read_text(encoding="utf-8")
    assert 'f"TERMINAL_RAIZES_{' in fonte and 'f"TERMINAL_CONTAINERS_{' in fonte and '"TERMINAL_SSH_AUTO_ADD"' in fonte
