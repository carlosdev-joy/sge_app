"""C1 da spec docs/spec-agentes-ferramenta-banco.md — camadas 1 e 2 da
consulta a banco dos agentes, mascaramento e mensagens de erro.

A matriz de recusas reproduz os ataques PROVADOS no SQL Server do DEV nas
revisões da spec (§C6): cada um deles gravou dados, leu outro banco ou vazou
o login quando só havia filtro de texto.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))

from services import agentes_sql as s  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures" / "showplan"

ACEITAS = [
    "SELECT 1",
    "select top 10 a.x from dbo.t a where a.y like '%a%'",
    ";WITH c AS (SELECT 1 x) SELECT * FROM c;",
    "WITH c(x) AS (SELECT 1), d AS (SELECT 2 y) SELECT * FROM c CROSS JOIN d",
    "WITH c AS (SELECT 1 x UNION ALL SELECT 2) SELECT x FROM c",
    "SELECT ROW_NUMBER() OVER (PARTITION BY a ORDER BY x) FROM t",
    "SELECT SUM(v) OVER (ORDER BY d ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) FROM t",
    "SELECT * FROM t ORDER BY x OFFSET 0 ROWS FETCH NEXT 5 ROWS ONLY",
    "SELECT a FROM t UNION ALL SELECT b FROM u EXCEPT SELECT c FROM v",
    "SELECT CASE WHEN a = 1 THEN 2 ELSE CASE WHEN b = 1 THEN 3 END END FROM t",
    "SELECT * FROM sys.tables",
    "SELECT * FROM INFORMATION_SCHEMA.COLUMNS",
    "SELECT user_id, host_name FROM t",
    "SELECT 1e5, 0xFF, .5, 1.5E-3",
    "SELECT * FROM a, b WHERE a.x = b.x",
    "SELECT OBJECT_NAME(object_id) FROM sys.objects",
    "SELECT CONVERT(varchar(10), GETDATE(), 103), DB_NAME()",
    "SELECT * FROM t WHERE x IN (SELECT y FROM u) AND NOT EXISTS (SELECT 1 FROM v)",
    "SELECT TOP 5 WITH TIES x FROM t ORDER BY x",
    "SELECT a, COUNT(*) FROM t GROUP BY a WITH ROLLUP",
    "SELECT [select], [delete] FROM [dbo].[minha tabela]",
    "SELECT 'DELETE FROM t; DROP TABLE x' AS texto",
    "SELECT N'ação' AS x, 'it''s' AS y",
    "SELECT * FROM t CROSS APPLY STRING_SPLIT(t.lista, ',') s",
    "SELECT * FROM t OUTER APPLY OPENJSON(t.j) j",
    "SELECT * FROM t PIVOT (SUM(v) FOR c IN ([a], [b])) p",
    "SELECT u.id, u.k, u.v FROM t UNPIVOT (v FOR k IN (a, b)) u",
    "SELECT STRING_AGG(nome, ', ') WITHIN GROUP (ORDER BY nome) FROM t",
    "SELECT v.x FROM (VALUES (1), (2)) v(x)",
    "SELECT CASE WHEN a > 0 THEN 1 ELSE NULL END, LAG(a) OVER (ORDER BY d) FROM t",
    "SELECT 'a;b', 'DELETE', '-- x', 'MERGE' FROM t",
    "SELECT d AT TIME ZONE 'UTC' FROM t",
    "SELECT CAST(x AS DATE), TRY_CAST(y AS INT), TRY_CONVERT(INT, z), IIF(a = 1, 'x', 'y') FROM t",
    "SELECT a, b, SUM(c) FROM t GROUP BY GROUPING SETS ((a), (b))",
    "SELECT * FROM t ORDER BY x OFFSET 0 ROWS FETCH FIRST 5 ROWS ONLY",
    "SELECT TOP (10) PERCENT x FROM t",
    "SELECT LEFT(nome, 3), RIGHT(nome, 2) FROM t",
    "SELECT dbo.fn_local(t.id) FROM t",
    "SELECT * FROM t; ",
    "SELECT t.* FROM dbo.Clientes t",
    "SELECT c.id, p.* FROM dbo.c c JOIN dbo.p p ON p.c_id = c.id",
    "SELECT OBJECT_ID('dbo.t'), OBJECT_ID(N't', 'U'), COL_LENGTH('dbo.t', 'x'), IDENT_CURRENT('t')",
    "SELECT SCHEMA_NAME(schema_id), TYPE_ID('int') FROM sys.tables",
    "SELECT dt_timeout FROM dbo.t",
]

RECUSADAS = [
    "SELECT 1DELETE FROM t SELECT 1COMMIT",   # provado: apagou dados
    "SELECT 1.DELETE FROM t",
    "SELECT 1e0DELETE FROM t",
    "SELECT 1; DELETE FROM t",
    "SELECT 1 DELETE FROM t",
    "DELETE FROM t",
    "UPDATE t SET a = 1",
    "SELECT NEXT VALUE FOR dbo.s",               # provado: grava a sequence
    "SELECT * INTO x FROM t",
    "SELECT * FROM t WITH (NOLOCK)",
    "SELECT * FROM t (NOLOCK)",
    "SELECT * FROM sysprocesses",                # provado: SQL de outras sessões
    "SELECT * FROM a, sysobjects",
    "SELECT * FROM sys.login_token",             # provado: o login
    "SELECT * FROM sys.sysprocesses",
    "SELECT * FROM sys . syslogins",
    "SELECT * FROM [sys].[sql_logins]",
    "SELECT * FROM \"sys\".\"server_principals\"",
    "SELECT * FROM INFORMATION_SCHEMA.SCHEMATA",
    "SELECT * FROM master.dbo.t",
    "SELECT * FROM master..t",
    "SELECT * FROM srv.db.dbo.t",
    "SELECT SUSER_NAME()",
    "SELECT ORIGINAL_LOGIN()",
    "SELECT SERVERPROPERTY('MachineName')",
    "SELECT @@VERSION",
    "SELECT @x",
    "SELECT * FROM ##global",                    # provado: lida de outra sessão
    "SELECT * FROM #t",
    "SELECT 1 -- comentario",
    "SELECT /* x */ 1",
    "EXEC sp_who",
    "SELECT OBJECT_NAME(1, 2)",                  # provado: nome de outro banco
    "SELECT OBJECT_ID('master.dbo.t')",
    "SELECT DB_NAME(1)",
    "SELECT * FROM t FOR XML PATH",
    "SELECT 1 SELECT 2",
    "SELECT * FROM t OPTION (MAXDOP 1)",
    "SELECT {fn user()}",
    "SELECT * FROM OPENROWSET('SQLNCLI', 'x', 'y')",
    "SELECT * FROM OPENQUERY(srv, 'x')",
    "WITH c AS (SELECT 1 x) DELETE FROM c",
    "WITH c AS (SELECT 1 x) SELECT * FROM c; SELECT 2",
    "SELECT 'abc",
    "SELECT END",
    "SELECT CASE WHEN 1 = 1 THEN 1",
    "SELECT 1 WAITFOR DELAY '0:0:5'",
    "SELECT * FROM t WHERE (a = 1",
    "SELECT a) FROM t",
    "SELECT 'token=abcdefghijklmnopqrstuvwx1234567890' AS x",
    "THROW 50000, 'x', 1",
    "SELECT * FROM t FOR JSON AUTO",
    "SELECT * FROM t FOR BROWSE",
    "SELECT * FROM t PIVOT (SUM(v) FOR c IN ([a])) p FOR XML RAW",
    "SELECT * FROM sp_helptext",
    "SELECT [xp_cmdshell] FROM t",
    "SELECT 1\u00a0FROM t",
    "SELECT SYSTEM_USER",
    "SELECT CURRENT_USER",
    "SELECT USER",
    "SELECT DATABASEPROPERTYEX('outro', 'Status')",
    "SELECT * FROM dbo.fn_x() CROSS APPLY master.dbo.fn_y(1)",
    "SELECT a.b.c FROM t",
    "SELECT * FROM t WHERE x = 1 IF 1 = 1 SELECT 2",
    "SELECT 1 RAISERROR('x', 16, 1)",
    "SELECT 1 PRINT 'x'",
    "USE master SELECT 1",
    "SELECT * FROM t TABLESAMPLE (10 PERCENT) WITH (NOLOCK)",
    "SELECT CURRENT OF c",
    "SELECT * FROM t lbl: SELECT 1",
    "SELECT IDENT_CURRENT('outro.dbo.segredo')",          # revisão C1: valor de outro banco
    "SELECT COL_LENGTH('outro.dbo.segredo', 'valor')",
    "SELECT OBJECT_ID('outro.' + 'dbo.segredo')",         # concatenação contornava a regra
    "SELECT OBJECT_ID(t.nome) FROM t",
    "SELECT IDENT_SEED('outro..t')",
    "SELECT SCHEMA_NAME()",
    "SELECT SCHEMA_ID()",
    "SELECT DATABASEPROPERTY('outro', 'IsReadOnly')",
    "SELECT DATABASE_PRINCIPAL_ID()",
    "SELECT DEFAULT_DOMAIN()",
    "SELECT PERMISSIONS()",
    "SELECT dbo.t.*.x FROM dbo.t",
    "SELECT outro.dbo.t.* FROM t",
    "",
    "   ;  ",
    "SELECT " + "1," * 10_000 + "1",
]


@pytest.mark.parametrize("sql", ACEITAS)
def test_camada1_aceita(sql):
    s.validar(sql)


@pytest.mark.parametrize("sql", RECUSADAS)
def test_camada1_recusa(sql):
    with pytest.raises(s.SqlRecusado):
        s.validar(sql)


def test_camada1_tira_ponto_e_virgula_das_pontas():
    assert s.validar(";WITH c AS (SELECT 1 x) SELECT * FROM c;") == "WITH c AS (SELECT 1 x) SELECT * FROM c"


def test_camada1_nao_aceita_tipo_que_nao_e_texto():
    for v in (None, 1, ["SELECT 1"]):
        with pytest.raises(s.SqlRecusado):
            s.validar(v)


# ── camada 2: planos REAIS capturados do SQL Server 2019 do DEV ──

def _plano(nome: str) -> list[str]:
    return [(FIXTURES / f"{nome}.xml").read_text(encoding="utf-8")]


LIBERADOS = {"agsql_liberado"}


@pytest.mark.parametrize("nome", sorted(p.stem for p in FIXTURES.glob("ok_*.xml")))
def test_camada2_aceita(nome):
    s.analisar_plano(_plano(nome), LIBERADOS)


@pytest.mark.parametrize("nome", sorted(p.stem for p in FIXTURES.glob("ruim_*.xml")))
def test_camada2_recusa(nome):
    with pytest.raises(s.SqlRecusado):
        s.analisar_plano(_plano(nome), LIBERADOS)


def test_camada2_mais_de_um_plano_recusa():
    xml = _plano(sorted(FIXTURES.glob("ok_*.xml"))[0].stem)[0]
    with pytest.raises(s.SqlRecusado):
        s.analisar_plano([xml, xml], LIBERADOS)


def test_camada2_xml_quebrado_recusa():
    with pytest.raises(s.SqlRecusado):
        s.analisar_plano(["<nao-fecha"], LIBERADOS)


def test_camada2_banco_com_caixa_diferente():
    xml = _plano("ok_select_tabela")[0]
    s.analisar_plano([xml], {"AGSQL_LIBERADO"})
    with pytest.raises(s.SqlRecusado):
        s.analisar_plano([xml], {"outro"})


# ── mascaramento e formatação ──

def test_mascara_por_valor():
    t = s.mascarar_texto("cpf 529.982.247-25 cnpj 11.222.333/0001-81 a@b.com.br (11) 91234-5678")
    assert "529" not in t and "11.222" not in t and "a@b" not in t and "91234" not in t
    assert "[cpf]" in t and "[cnpj]" in t and "[email]" in t and "[telefone]" in t


def test_mascara_nao_pega_numero_que_nao_e_cpf():
    assert s.mascarar_texto("pedido 12345678901") == "pedido 12345678901"
    assert s.mascarar_texto("111.111.111-11") == "111.111.111-11"
    assert s.mascarar_texto("52998224725") == "[cpf]"


def test_formatar_coluna_pessoal_inteira():
    txt = s.formatar(["id", "cpf_cliente", "EMAIL"], [(1, "qualquer", "x")], mascarar=True, havia_mais=False)
    assert txt.splitlines()[1] == "1\t[oculto]\t[oculto]"
    sem = s.formatar(["id", "cpf_cliente"], [(1, "529.982.247-25")], mascarar=False, havia_mais=False)
    assert "529.982.247-25" in sem


def test_formatar_segredo_sempre_escondido():
    txt = s.formatar(["v"], [("password=abcdefghijklmnopqrstuvwxyz0123",)], mascarar=False, havia_mais=False)
    assert "abcdefghij" not in txt


def test_formatar_limites():
    txt = s.formatar(["v"], [("x" * 500,)], mascarar=False, havia_mais=True)
    linha = txt.splitlines()[1]
    assert len(linha) == s.MAX_CELULA + 1
    assert "havia mais de 100" in txt
    grande = s.formatar(["v"], [("y" * 199,)] * 100, mascarar=False, havia_mais=False)
    assert len(grande) <= s.MAX_BLOCO + 200 and "não mostradas" in grande
    assert s.formatar(["a", "b"], [(None, b"\x00\x01")], mascarar=False, havia_mais=False).endswith("NULL\t<2 bytes>")


# ── erros: mensagens fixas, sem host/login ──

class _ErroDriver(Exception):
    pass


@pytest.mark.parametrize("estado,texto,esperado,categoria", [
    ("42S02", "[42S02] [Microsoft][ODBC Driver 18 for SQL Server][SQL Server]Invalid object name 'dbo.x'. (208)",
     "tabela ou objeto inexistente: dbo.x", "banco_objeto_inexistente"),
    ("42S22", "[42S22] ... Invalid column name 'y'. (207)", "coluna inexistente: y", "banco_objeto_inexistente"),
    ("42000", "[42000] ... The SELECT permission was denied on the object 't', database 'd', schema 'dbo'. (229)",
     "banco sem acesso para esta consulta", "banco_sem_acesso"),
    ("28000", "[28000] ... Login failed for user 'svc_leitura'. (18456)", "conexão indisponível", None),
    ("HYT00", "[HYT00] [Microsoft][ODBC Driver 18 for SQL Server]Query timeout expired (0)", "tempo esgotado", None),
    ("42000", "[42000] ... Incorrect syntax near 'FORM'. (102)", "sintaxe inválida perto de FORM", None),
])
def test_mensagem_de_erro(estado, texto, esperado, categoria):
    msg, cat = s.mensagem_de_erro(_ErroDriver(estado, texto), mascarar=True)
    assert msg.startswith(esperado)
    assert cat == categoria
    assert "Microsoft" not in msg and "svc_leitura" not in msg


def test_mensagem_de_erro_mascara_o_nome():
    msg, _ = s.mensagem_de_erro(_ErroDriver("42000", "... near 'a@b.com'. (102)"), mascarar=True)
    assert "a@b.com" not in msg


def test_timeout_so_pelo_sqlstate():
    class E(Exception):
        pass
    msg, cat = s.mensagem_de_erro(E("42S22", "[42S22] ... Invalid column name 'dt_timeout'. (207)"), mascarar=True)
    assert msg == "coluna inexistente: dt_timeout" and cat == "banco_objeto_inexistente"


class _CursorLinhas:
    def __init__(self, linhas):
        self.linhas, self.lidas = list(linhas), 0

    def fetchone(self):
        if not self.linhas:
            return None
        self.lidas += 1
        return self.linhas.pop(0)


def test_leitura_linha_a_linha_reduz_na_hora():
    grande = b"x" * 5_000_000
    cur = _CursorLinhas([(i, grande, "t" * 50_000) for i in range(3)])
    linhas, mais, _ = s._ler_linhas(cur)
    assert not mais and len(linhas) == 3
    assert str(linhas[0][1]) == "<5000000 bytes>" and len(linhas[0][2]) == s._GUARDA_CELULA
    assert s.formatar(["id", "b", "t"], linhas, mascarar=False, havia_mais=False).splitlines()[1].startswith(
        "0\t<5000000 bytes>\t" + "t" * 200)


def test_leitura_para_no_teto_de_linhas_e_de_bytes():
    cur = _CursorLinhas([(i,) for i in range(500)])
    linhas, mais, por_tamanho = s._ler_linhas(cur)
    assert len(linhas) == 100 and mais and not por_tamanho and cur.lidas == 101
    cur = _CursorLinhas([(i,) for i in range(100)])
    assert s._ler_linhas(cur)[1:] == (False, False)  # exatamente 100: não havia mais
    cur = _CursorLinhas([(b"x" * 10_000_000,) for _ in range(50)])
    linhas, mais, por_tamanho = s._ler_linhas(cur)
    assert mais and por_tamanho and len(linhas) == 4 and cur.lidas == 4  # 40 MB > 32 MB: parou
    txt = s.formatar(["b"], linhas, mascarar=False, havia_mais=mais, por_tamanho=por_tamanho)
    assert "volume de dados" in txt and "100 linhas" not in txt
