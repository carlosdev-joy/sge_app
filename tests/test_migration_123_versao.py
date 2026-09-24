"""Migration 123 — a versão da entrega entra sozinha em Admin › Versões.

O número do cabeçalho é a MAIOR versão de `etl_versao_ferramenta`
(ui-react/src/lib/version.ts) e até a 123 só entrava à mão. O comportamento
(número calculado, idempotência, sincronia de `app_version`) foi provado no
SQL Server do DEV num banco temporário; aqui se prende a forma:

  • UM lote só — o `migrate.py` divide por GO, e as variáveis não atravessam;
  • o título é a chave da idempotência (roda 2× sem duplicar nem renumerar);
  • o número segue a regra do cabeçalho (1 a 4 partes, comparadas como números);
  • `app_version`/`app_release_name` acompanham, como no "Nova Versão" da aba.
"""
from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
MIG = RAIZ / "sql" / "migrations" / "123_versao_agentes_banco.sql"


def _sql() -> str:
    return MIG.read_text(encoding="utf-8")


def test_um_lote_so():
    assert not re.search(r"^\s*GO\s*$", _sql(), re.M | re.I)


def test_titulo_e_a_chave_da_idempotencia():
    sql = _sql()
    titulo = re.search(r"DECLARE @titulo NVARCHAR\(200\) = N'([^']+)';", sql).group(1)
    assert titulo == "Agentes pela tela e consulta a banco"
    assert "ELSE IF EXISTS (SELECT 1 FROM dbo.etl_versao_ferramenta WHERE titulo = @titulo)" in sql
    assert sql.count("INSERT INTO dbo.etl_versao_ferramenta") == 1


def test_numero_pela_regra_do_cabecalho():
    sql = _sql()
    assert "BETWEEN 0 AND 3" in sql and "REPLICATE('.0', 3 -" in sql  # 1 a 4 partes
    assert "ORDER BY a DESC, b DESC, c DESC, d DESC" in sql            # como números, não texto
    assert "SET @nova = CONCAT(@maior, '.', @menor + 1, '.0');" in sql
    assert "SELECT @maior = 2, @menor = 2;" in sql                     # sem nenhuma: 2.3.0
    front = (RAIZ / "ui-react" / "src" / "lib" / "version.ts").read_text(encoding="utf-8")
    assert "compareVersions" in front  # o cabeçalho escolhe a maior, numericamente


def test_sincroniza_app_version_como_a_aba():
    sql = _sql()
    for chave in ("app_version", "app_release_name"):
        assert f"WHERE config_key = '{chave}'" in sql
    aba = (RAIZ / "api" / "routers" / "infra.py").read_text(encoding="utf-8")
    assert '("app_version", v), ("app_release_name", t)' in aba


def test_cabe_nas_colunas():
    sql = _sql()
    corpo = re.search(r"VALUES \(@nova, @titulo, N'(.*?)', 'deploy'\);", sql, re.S).group(1)
    assert "'" not in corpo.replace("''", "")  # nenhuma aspa solta no markdown
    assert len("Agentes pela tela e consulta a banco") <= 200


def test_avisa_versao_fora_do_padrao():
    """Revisão da C3: '2.10-hotfix' é ignorada no cálculo mas não pelo cabeçalho."""
    assert "[ATENÇÃO] há versões fora do padrão" in _sql()
