"""Marcador `{coluna:ALIAS}` / `{coluna:NO.ALIAS}` no e-mail
(spec docs/spec-email-coluna-sql.md).

O que se prende:
  1. resolve só com resultado de UMA linha — com 0 ou 2+ sai literal e o log
     diz quantas linhas vieram;
  2. a forma curta só escolhe quando há UM nó SQL a montante;
  3. o valor é dado de banco: escapado no corpo HTML (aspas incluídas), cru no
     assunto e no corpo em texto; NULL vira vazio, nunca o marcador literal;
  4. o nome do anexo NÃO resolve `{coluna:…}`;
  5. `{tabela}` e o escalar da Decisão não mudam.
"""
from __future__ import annotations

import email
import types

import pytest

from tests.test_email_operator import (  # noqa: F401 — `mod` é fixture
    NO_PADRAO, _Client, _contexto, _Hook, _preparar, mod,
)


def _tabela(columns, rows, **extra):
    base = {"columns": columns, "rows": rows, "total": len(rows), "truncado": False,
            "havia_mais": False, "colunas_ocultas": 0}
    base.update(extra)
    return base


CVP = _tabela(["mes", "total", "ativos"], [["2026/09", "17.326.307", "16.642.733"]])


class _Log:
    def __init__(self):
        self.linhas = []

    def info(self, msg, *a, **k):
        self.linhas.append(("info", msg % a if a else msg))

    def warning(self, msg, *a, **k):
        self.linhas.append(("warning", msg % a if a else msg))

    def texto(self):
        return "\n".join(m for _, m in self.linhas)


def _enviar(mod, monkeypatch, *, corpo, tabelas, upstream, html=True, assunto="Aviso", anexo=None):
    no = dict(NO_PADRAO, corpo=corpo, html=html, assunto=assunto, anexo=anexo)
    hook, client = _Hook(no=no), _Client(rc=0)
    op = _preparar(mod, monkeypatch, hook, client)
    op.log = _Log()
    op.upstream_task_ids = set(upstream)
    op.execute(_contexto(tabelas=tabelas))
    msg = email.message_from_bytes(client._entrada.escrito)
    partes = [p for p in msg.walk() if not p.is_multipart()]
    alvo = next((p for p in partes if p.get_content_type() == ("text/html" if html else "text/plain")),
                partes[0])
    corpo_final = alvo.get_payload(decode=True).decode(alvo.get_content_charset() or "utf-8")
    assunto_final = str(email.header.make_header(email.header.decode_header(msg["Subject"])))
    return corpo_final, assunto_final, op.log


def test_forma_curta_e_longa_resolvem_com_um_no_e_uma_linha(mod, monkeypatch):
    corpo, _, log = _enviar(mod, monkeypatch,
                            corpo="<b>{coluna:total}</b> em {coluna:SQL_1.mes}",
                            tabelas={"SQL_1": CVP}, upstream={"SQL_1"})
    assert "<b>17.326.307</b> em 2026/09" in corpo
    assert "{coluna:" not in corpo
    # linha de sucesso (prova de worker sem cache) e SEM o valor
    assert "[EMAIL] coluna SQL_1.total resolvida" in log.texto()
    assert "17.326.307" not in log.texto()


@pytest.mark.parametrize("linhas,esperado", [([], "0 linha"), ([["a"], ["b"]], "2 linha")])
def test_resultado_sem_exatamente_uma_linha_fica_literal(mod, monkeypatch, linhas, esperado):
    corpo, _, log = _enviar(mod, monkeypatch, corpo="x {coluna:SQL_1.n} y",
                            tabelas={"SQL_1": _tabela(["n"], linhas)}, upstream={"SQL_1"})
    assert "{coluna:SQL_1.n}" in corpo
    assert f"SQL_1 trouxe {esperado}(s) (esperado: 1)" in log.texto()


def test_teto_de_leitura_nao_e_confundido_com_uma_linha(mod, monkeypatch):
    """`rows` cortado em 1 com `total` maior: não é resultado de uma linha."""
    t = _tabela(["n"], [["1"]], total=1000, havia_mais=True, truncado=True)
    corpo, _, log = _enviar(mod, monkeypatch, corpo="{coluna:n}", tabelas={"S": t}, upstream={"S"})
    assert "{coluna:n}" in corpo
    assert "mais de 1000" in log.texto()


def test_dois_nos_forma_curta_literal_e_longa_resolve(mod, monkeypatch):
    outra = _tabela(["total"], [["999"]])
    corpo, _, log = _enviar(mod, monkeypatch, corpo="[{coluna:total}] [{coluna:SQL_1.total}]",
                            tabelas={"SQL_1": CVP, "SQL_2": outra}, upstream={"SQL_1", "SQL_2"})
    assert "[{coluna:total}] [17.326.307]" in corpo
    assert "2 nós SQL a montante (SQL_1, SQL_2)" in log.texto()
    assert "{coluna:NOME_DO_NO.total}" in log.texto()


def test_sem_no_sql_a_montante_fica_literal_e_explica(mod, monkeypatch):
    corpo, _, log = _enviar(mod, monkeypatch, corpo="{coluna:total}", tabelas={},
                            upstream={"log_end_CARGA"})
    assert "{coluna:total}" in corpo
    assert "nenhum nó SQL imediatamente a montante (vizinhos: CARGA)" in log.texto()


def test_coluna_inexistente_e_caixa_errada(mod, monkeypatch):
    corpo, _, log = _enviar(mod, monkeypatch, corpo="{coluna:Total} {coluna:nada}",
                            tabelas={"SQL_1": CVP}, upstream={"SQL_1"})
    assert "{coluna:Total}" in corpo and "{coluna:nada}" in corpo
    assert "seria {coluna:total}?" in log.texto()
    assert "não tem a coluna nada (colunas: mes, total, ativos)" in log.texto()


def test_no_inexistente_fica_literal(mod, monkeypatch):
    corpo, _, log = _enviar(mod, monkeypatch, corpo="{coluna:OUTRO.total}",
                            tabelas={"SQL_1": CVP}, upstream={"SQL_1"})
    assert "{coluna:OUTRO.total}" in corpo
    assert "a montante existem: SQL_1" in log.texto()


def test_no_com_ponto_no_nome_separa_no_ultimo_ponto(mod, monkeypatch):
    corpo, _, _ = _enviar(mod, monkeypatch, corpo="{coluna:A.B.total}",
                          tabelas={"A.B": CVP}, upstream={"A.B"})
    assert "17.326.307" in corpo


def test_alias_invalido_e_coluna_repetida(mod, monkeypatch):
    t = _tabela(["x", "x", ""], [["1", "2", "3"]])
    corpo, _, log = _enviar(mod, monkeypatch, corpo="{coluna:x} {coluna:a-b}",
                            tabelas={"S": t}, upstream={"S"})
    assert "{coluna:x}" in corpo and "{coluna:a-b}" in corpo
    assert "S tem 2 colunas chamadas x" in log.texto()
    assert '"a-b" não é alias válido' in log.texto()


def test_coluna_alem_do_limite_explica_o_corte(mod, monkeypatch):
    t = _tabela(["a"], [["1"]], colunas_ocultas=3)
    _, _, log = _enviar(mod, monkeypatch, corpo="{coluna:p}", tabelas={"S": t}, upstream={"S"})
    assert "3 coluna(s) além da 15ª não chegam ao e-mail" in log.texto()


def test_html_escapa_inclusive_aspas_e_texto_vai_cru(mod, monkeypatch):
    t = _tabela(["nome"], [['<b>R&"Cia</b>']])
    corpo, _, _ = _enviar(mod, monkeypatch, corpo='<p title="{coluna:nome}">{coluna:nome}</p>',
                          tabelas={"S": t}, upstream={"S"})
    assert "&lt;b&gt;R&amp;&quot;Cia&lt;/b&gt;" in corpo
    assert "<b>R&" not in corpo
    texto, _, _ = _enviar(mod, monkeypatch, corpo="{coluna:nome}", tabelas={"S": t},
                          upstream={"S"}, html=False)
    assert '<b>R&"Cia</b>' in texto


def test_null_vira_vazio_e_nao_marcador_literal(mod, monkeypatch):
    t = _tabela(["obs"], [[None]])
    corpo, _, _ = _enviar(mod, monkeypatch, corpo="[{coluna:obs}]", tabelas={"S": t}, upstream={"S"})
    assert "[]" in corpo


def test_assunto_recebe_o_valor_cru(mod, monkeypatch):
    t = _tabela(["mes"], [["2026/09 & cia"]])
    _, assunto, _ = _enviar(mod, monkeypatch, corpo="x", assunto="Carga {coluna:mes}",
                            tabelas={"S": t}, upstream={"S"})
    assert assunto == "Carga 2026/09 & cia"


def test_tabela_e_coluna_no_mesmo_corpo(mod, monkeypatch):
    corpo, _, _ = _enviar(mod, monkeypatch, corpo="{tabela:SQL_1}|{coluna:SQL_1.ativos}",
                          tabelas={"SQL_1": CVP}, upstream={"SQL_1"})
    assert "16.642.733" in corpo and "<table" in corpo and "{" not in corpo.split("|")[-1]


def test_sem_marcador_de_coluna_nao_le_nem_avisa(mod, monkeypatch):
    """Nó que não usa `{coluna:…}` não pode ganhar aviso em toda corrida."""
    _, _, log = _enviar(mod, monkeypatch, corpo="carga fechou", tabelas={"S": CVP}, upstream={"S"})
    assert "coluna" not in log.texto()


def test_anexo_nao_resolve_coluna(mod):
    """O anexo é interpolado só com o `mapa`: dado de banco não vira caminho."""
    import inspect
    fonte = inspect.getsource(mod.EmailOperator.execute)
    trecho = fonte[fonte.index("ev.resolver_anexo("):]
    trecho = trecho[:trecho.index(")")]
    assert trecho.rstrip().endswith("mapa"), trecho


def test_contexto_sem_ti_nao_quebra(mod):
    op = types.SimpleNamespace(log=_Log(), upstream_task_ids=set())
    op._tabelas_a_montante = lambda ctx: mod.EmailOperator._tabelas_a_montante(op, ctx)
    op._jobs_a_montante = lambda: []
    assert mod.EmailOperator._marcadores_de_coluna(op, {}, True, "{coluna:x}") == {}
