"""Migration 141/142 — monitoramento de uso do módulo Busca & Vendas (v2.6.2).

A 141 cria as tabelas e semeia o recurso no perfil admin; a 142 só registra a versão.
Ambas idempotentes (a corrida de 2× está em test_migrations_idempotentes.py).
"""
from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
MIGS = RAIZ / "sql" / "migrations"
M141 = MIGS / "141_uso_busca_vendas.sql"
M142 = MIGS / "142_versao_uso_busca_vendas.sql"
_TITULO = re.compile(r"DECLARE @titulo NVARCHAR\(200\) = N'([^']+)';")


def _codigo(p: Path) -> str:
    return "\n".join(l for l in p.read_text(encoding="utf-8").splitlines() if not l.strip().startswith("--"))


def test_titulo_proprio_entre_todas_as_versoes():
    titulos = [m.group(1) for p in sorted(MIGS.glob("*_versao_*.sql"))
               if (m := _TITULO.search(p.read_text(encoding="utf-8")))]
    assert titulos.count("Uso do módulo Busca & Vendas") == 1
    assert len(set(titulos)) == len(titulos), titulos


def test_142_registra_2_6_2_idempotente_e_sincroniza_a_versao():
    sql = M142.read_text(encoding="utf-8")
    assert "DECLARE @versao NVARCHAR(20)  = N'2.6.2';" in sql
    assert "WHERE titulo = @titulo OR versao = @versao" in sql
    assert "config_key = 'app_version'" in sql and "config_key = 'app_release_name'" in sql
    assert (RAIZ / "docs/release-notes/uso-busca-vendas.md").is_file()


def test_142_so_registra_versao():
    codigo = _codigo(M142).upper()
    for tabela in ("ETL_USO_", "CAIXA_SEGURO_USO"):
        assert tabela not in codigo
    for verbo in ("DROP ", "TRUNCATE", "ALTER ", "CREATE "):
        assert verbo not in codigo


def test_141_cria_as_duas_tabelas_com_guarda_e_sem_fk_para_usuario():
    codigo = _codigo(M141)
    assert "IF OBJECT_ID('dbo.etl_uso_evento', 'U') IS NULL" in codigo
    assert "IF OBJECT_ID('dbo.etl_uso_presenca', 'U') IS NULL" in codigo
    # O evento sobrevive à remoção do usuário: nada de FK/ON DELETE CASCADE.
    assert "FOREIGN KEY" not in codigo.upper() and "REFERENCES" not in codigo.upper()


def test_141_nao_guarda_ip_nem_user_agent():
    codigo = _codigo(M141).lower()
    for campo in ("ip_", "user_agent", "useragent", "remote_addr", "dispositivo"):
        assert campo not in codigo


def test_141_semeia_o_recurso_so_no_perfil_admin():
    codigo = _codigo(M141)
    perfis = re.findall(r"\('(\w+)', 'caixa_seguro_uso'\)", codigo)
    assert perfis == ["admin"], perfis


def test_141_indices_cobrem_as_consultas_do_resumo():
    codigo = _codigo(M141)
    assert "ON dbo.etl_uso_evento (ocorrido_em)" in codigo
    assert "ON dbo.etl_uso_evento (matricula, ocorrido_em)" in codigo
