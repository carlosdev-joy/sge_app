"""Cabeçalho do modelo institucional de e-mail (F3 da spec
docs/spec-email-tabela-sql-e-ajustes.md) — migration 113.

O modelo semeado pela 112 chegava quebrado no Outlook desktop: cabeçalho cortado
ao meio e uma faixa de outra cor à direita. As causas estavam no bloco VML do
cabeçalho e na ausência de `<head>` no envio (tratada em `documento_html`, com
testes em test_email_mime.py).

Aqui se prende a migration: o corpo novo não pode voltar a depender do que o
motor do Word ignora, e a guarda que protege o modelo EDITADO precisa comparar
exatamente o texto semeado pela 112 — um hash errado faria a migration não
corrigir nada (e passar despercebida, porque ela degrada em silêncio).
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
M112 = RAIZ / "sql/migrations/112_email_modelos.sql"
M113 = RAIZ / "sql/migrations/113_email_modelo_header.sql"


def _corpo_semeado_pela_112() -> str:
    s = M112.read_text(encoding="utf-8")
    ini = s.index("N'<table width=\"100%\"") + 2
    fim = s.index("',\n            1, 1, 1, N'migration 112');")
    return s[ini:fim]


def _corpo_novo_da_113() -> str:
    s = M113.read_text(encoding="utf-8")
    ini = s.index("SET corpo = N'") + len("SET corpo = N'")
    fim = s.index("',\n               atualizado_em = GETDATE()")
    return s[ini:fim].replace("''", "'")


def test_o_hash_da_guarda_e_o_do_corpo_semeado_pela_112():
    """⚠️ A guarda decide se o modelo foi editado. Com um hash que não bate, a
    migration nunca corrige nada — e não falha: imprime "corpo preservado" e
    segue. Este teste é o que impede esse verde silencioso.

    `HASHBYTES('SHA2_256', <NVARCHAR>)` do SQL Server digere UTF-16LE; foi assim
    que o valor foi conferido contra o banco do DEV antes de escrever a 113."""
    esperado = hashlib.sha256(_corpo_semeado_pela_112().encode("utf-16-le")).hexdigest().upper()
    hashes = set(re.findall(r"0x([0-9A-F]{64})", M113.read_text(encoding="utf-8")))
    assert hashes == {esperado}, (
        "o hash da guarda não corresponde ao corpo semeado pela 112 — a 113 "
        "deixaria de corrigir o cabeçalho, em silêncio")


def test_o_update_repete_a_guarda_no_where():
    """O EXISTS confere uma linha e o UPDATE escreve — se o WHERE do UPDATE não
    repetisse a condição, bastaria existir UMA linha intacta para sobrescrever
    outra que alguém editou."""
    sql = M113.read_text(encoding="utf-8")
    update = sql[sql.index("UPDATE dbo.etl_email_modelo"):sql.index("PRINT '[OK]")]
    assert "HASHBYTES('SHA2_256', corpo) =" in update
    assert "WHERE nome = N'Aviso de fim de carga'" in update


def test_o_cabecalho_novo_nao_depende_do_que_o_word_ignora():
    corpo = _corpo_novo_da_113()
    assert "<v:rect" not in corpo and "<v:textbox" not in corpo and "[if mso]" not in corpo, (
        "VML de volta: sem mso-fit-shape-to-text o Word clipa o conteúdo, e o "
        "modo escuro inverte bgcolor mas não inverte preenchimento VML")
    assert "linear-gradient" not in corpo, "gradiente não sobrevive ao motor do Word"
    # Os quadradinhos do logo eram <div> com width/height, e o Word ignora os
    # dois em <div> — o logo sumia. Em <td> (com os atributos width/height
    # clássicos) ele respeita, então o que se proíbe aqui é a DIV dimensionada,
    # não a medida em si.
    cabecalho = corpo[:corpo.index('bgcolor="#F26B00"')]
    assert not re.search(r"<div[^>]*(width|height)\s*:", cabecalho), (
        "quadrado do logo voltou a ser <div> dimensionada — o Outlook desktop não desenha")
    assert 'bgcolor="#0F4C88"' in cabecalho          # cor sólida, que o Word respeita
    assert 'height="8"' in cabecalho                 # o quadrado virou célula


def test_o_corpo_novo_continua_cabendo_e_com_os_marcadores():
    corpo = _corpo_novo_da_113()
    assert len(corpo) < 20000, "LIMITE_CORPO do envio"
    for marcador in ("{pipeline}", "{status}", "{linhas}", "{inicio}", "{duracao}", "{odate}"):
        assert marcador in corpo, marcador


def test_a_113_nao_toca_em_nada_quando_a_112_nao_rodou():
    """Ambiente sem a tabela não pode quebrar o deploy — a etapa 6c aplica tudo
    em sequência e um erro aqui abortaria o resto."""
    sql = M113.read_text(encoding="utf-8")
    assert "IF OBJECT_ID('dbo.etl_email_modelo', 'U') IS NULL" in sql
    assert "migration 112 pendente" in sql
