"""Migrations 126 e 127 — fechamento da reestruturação do Admin (F6 de
docs/spec-admin-reestruturacao.md).

126 — versão da entrega, no formato da 123 (funcionalidade nova: +1 no SEGUNDO
número, zerando o terceiro: 2.3.2 → 2.4.0). Comportamento (número, 2× sem
duplicar, sincronia de app_version) provado no SQL Server do DEV; aqui se prende
a forma, como nos testes da 123/124/125.

127 — pendências da entrega no Backlog de PRODUÇÃO (dbo.etl_backlog, decisão
§9.4). Prende: todo INSERT atrás de um IF NOT EXISTS pelo MESMO título (roda 2×
sem duplicar), título ≤ 200 em UTF-16 (NVARCHAR(200) conta unidades UTF-16),
tipo/área/prioridade/status dentro dos domínios da 035 e a guarda OBJECT_ID.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
MIGS = RAIZ / "sql" / "migrations"
MIG126 = MIGS / "126_versao_admin_reestruturado.sql"
MIG127 = MIGS / "127_backlog_admin_reestruturacao.sql"
VERSOES = ("123_versao_agentes_banco.sql", "124_versao_agentes_cards_tempos.sql",
           "125_versao_admin_agentes.sql", "126_versao_admin_reestruturado.sql")
RE_TITULO = re.compile(r"DECLARE @titulo NVARCHAR\(200\) = N'([^']+)';")


def _utf16(s: str) -> int:
    return len(s.encode("utf-16-le")) // 2


# ═══════════ 126 — versão ════════════════════════════════════════════════

def test_126_titulo_unico_ascii_e_chave_da_idempotencia():
    sql = MIG126.read_text(encoding="utf-8")
    titulo = RE_TITULO.search(sql).group(1)
    assert titulo == "Admin reorganizado: sub-menu, busca e link por aba"
    # app_release_name é VARCHAR: título ASCII não vira "?"
    assert titulo.isascii()
    titulos = [RE_TITULO.search((MIGS / n).read_text(encoding="utf-8")).group(1) for n in VERSOES]
    assert len(set(titulos)) == len(titulos), titulos
    assert "ELSE IF EXISTS (SELECT 1 FROM dbo.etl_versao_ferramenta WHERE titulo = @titulo)" in sql
    assert sql.count("INSERT INTO dbo.etl_versao_ferramenta") == 1


def test_126_um_lote_so_e_sobe_o_segundo_numero():
    sql = MIG126.read_text(encoding="utf-8")
    assert not re.search(r"^\s*GO\s*$", sql, re.M | re.I)
    assert "SET @nova = CONCAT(@maior, '.', @menor + 1, '.0');" in sql
    assert "SELECT TOP 1 @maior = a, @menor = b\n" in sql
    assert "SELECT @maior = 2, @menor = 2;" in sql
    assert "@patch" not in sql
    assert "ORDER BY a DESC, b DESC, c DESC, d DESC" in sql
    assert "BETWEEN 0 AND 3" in sql and "REPLICATE('.0', 3 -" in sql
    assert "[ATENÇÃO] há versões fora do padrão" in sql
    for chave in ("app_version", "app_release_name"):
        assert f"WHERE config_key = '{chave}'" in sql


def test_126_changelog_cobre_a_entrega():
    sql = MIG126.read_text(encoding="utf-8")
    corpo = re.search(r"VALUES \(@nova, @titulo, N'(.*?)', 'deploy'\);", sql, re.S).group(1)
    assert "'" not in corpo.replace("''", "")  # nenhuma aspa solta no markdown
    for termo in ("Acesso", "Inteligência Artificial", "Comunicação", "Integrações & Dados",
                  "Pipelines & Ambiente", "Sistema", "email_remetente", "**/**", "Copiar link",
                  "última aba visitada", "⌘K", "Perfis e Permissões", "Roles do Airflow",
                  "Triagem de chamados", "Diagnóstico", "webhook padrão", "Bancos & Monitoramento",
                  "Performance", "Power BI", "Console DataStage", "Parâmetros avançados"):
        assert termo in corpo, termo


# ═══════════ 127 — backlog ═══════════════════════════════════════════════

DOMINIOS = {  # sql/migrations/035_backlog.sql
    "tipo": {"feature", "bug", "debt", "spike"},
    "area": {"backend", "frontend", "datastage", "deploy", "infra", "outro"},
    "prioridade": {"P0", "P1", "P2", "P3"},
    "status": {"ideia", "refinado", "em_andamento", "concluido", "descartado"},
}
RE_ITEM = re.compile(
    r"IF NOT EXISTS \(SELECT 1 FROM dbo\.etl_backlog WHERE titulo = N'((?:[^']|'')+)'\)\n"
    r"\s+INSERT INTO dbo\.etl_backlog \(titulo, descricao, tipo, area, prioridade, status, tags, criado_por\)\n"
    r"\s+VALUES \(N'((?:[^']|'')+)',\n"
    r"\s+N'((?:[^']|'')*)',\n"
    r"\s+N'(\w+)', N'(\w+)', N'(\w+)', N'(\w+)', N'([\w-]+)', N'([\w-]+)'\);")


def _itens() -> list[tuple[str, ...]]:
    return RE_ITEM.findall(MIG127.read_text(encoding="utf-8"))


def test_127_dez_itens_todos_idempotentes_pelo_titulo():
    sql = MIG127.read_text(encoding="utf-8")
    itens = _itens()
    assert len(itens) == 10
    # nenhum INSERT fora do padrão casado acima
    assert sql.count("INSERT INTO dbo.etl_backlog") == len(itens)
    for titulo_guarda, titulo, *_ in itens:
        assert titulo_guarda == titulo, "a guarda precisa checar o MESMO título que insere"
    titulos = [i[0] for i in itens]
    assert len(set(titulos)) == len(titulos)


def test_127_guarda_da_tabela_e_um_lote():
    sql = MIG127.read_text(encoding="utf-8")
    assert "IF OBJECT_ID('dbo.etl_backlog', 'U') IS NULL" in sql
    corpo = sql.split("ELSE\nBEGIN", 1)
    assert len(corpo) == 2 and "INSERT" not in corpo[0].split("SET NOCOUNT ON;", 1)[1]
    assert len(re.findall(r"^\s*GO\s*$", sql, re.M | re.I)) == 1 and sql.rstrip().endswith("GO")


@pytest.mark.parametrize("campo,pos", [("tipo", 3), ("area", 4), ("prioridade", 5), ("status", 6)])
def test_127_valores_dentro_dos_dominios_da_035(campo, pos):
    for item in _itens():
        assert item[pos] in DOMINIOS[campo], (campo, item[0])


def test_127_colunas_cabem():
    for titulo, _, desc, _tipo, _area, _prio, status, tags, criado_por in _itens():
        t = titulo.replace("''", "'")
        assert 0 < _utf16(t) <= 200, t
        assert status == "ideia" and tags == "admin-reestruturacao" and criado_por == "spec-admin-reestruturacao"
        assert _utf16(tags) <= 200 and _utf16(criado_por) <= 64
        assert "**Pronto quando:**" in desc, t  # descrição com critério de pronto
        assert re.search(r"`[\w/.-]+\.(py|tsx?|sql)", desc), t  # e com o arquivo


def test_127_cobre_as_pendencias_da_spec():
    alvo = " ".join(i[0] + " " + i[2] for i in _itens())
    for termo in ("url_valida", "test-webhook", "etl_admin_manage", "Acessos e Comunicacao",
                  "RBAC por aba", "user_perm_set", "histórico", "Failed to fetch dynamically imported module",
                  "TEAMS_WEBHOOK_URL_CVP", "servicenow_proxy"):
        assert termo in alvo, termo


# ═══════════ smoke — scripts/smoke_admin.sh ══════════════════════════════

def test_smoke_usa_os_mesmos_padroes_de_segredo_do_backend():
    """Lista paralela de segredos já ficou para trás uma vez (o /config vazava
    servicenow_senha_enc — F5): o smoke espelha a fonte única do backend."""
    fonte = (RAIZ / "api" / "services" / "admin_config_donos.py").read_text(encoding="utf-8")
    backend = re.search(r"PADROES_SEGREDO = \((.*?)\)", fonte, re.S).group(1)
    esperados = re.findall(r'"([^"]+)"', backend)
    smoke = (RAIZ / "scripts" / "smoke_admin.sh").read_text(encoding="utf-8")
    linha = re.search(r'^SEGREDO="\((.*)\)"$', smoke, re.M).group(1)
    assert re.findall(r"'([^']+)'", linha) == esperados
    assert smoke.count("$SEGREDO") == 3 and "'_enc')" not in smoke.replace(linha, "")
    # senha só pelo ambiente: toda atribuição é placeholder ou repasse da variável
    assert set(re.findall(r"ORQ_SENHA=(\S+)", smoke)) <= {"'…'", "…", '"$ORQ_SENHA"'}
