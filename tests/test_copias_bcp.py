"""
Testes do engine bcp_native do módulo Cópia de Dados (funções PURAS de
dags/utils/bulk_copy.py e dags/etl_copy_exec.py).

Os módulos das DAGs importam pymssql/airflow (indisponíveis no ambiente de
teste), então as funções puras são EXTRAÍDAS por AST e compiladas num
namespace controlado — mesmo espírito dos testes ast.parse das factories.
Cobertura: redação de senha (redigir_cmd), literais SQL seguros
(sql_literal — aspas/unicode/data/número/controle), montagem dos comandos
queryout/in, parsing do progresso do bcp e o SELECT de faixa com fronteiras
inline (_sql_da_faixa_bcp).
"""
from __future__ import annotations

import ast
import logging
import re
import types
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

_RAIZ = Path(__file__).parent.parent
_BULK_COPY = _RAIZ / "dags" / "utils" / "bulk_copy.py"
_COPY_EXEC = _RAIZ / "dags" / "etl_copy_exec.py"

_NOMES_BULK = {
    # constantes (regex) + funções puras do engine bcp
    "_BCP_LOTE_RE", "_BCP_TOTAL_RE", "_BCP_FLAG_RE", "_CTRL_RE",
    "_BCP_PATH_PADRAO",
    "quote_ident", "redigir_cmd", "_redigir_texto", "sql_literal",
    "montar_cmd_bcp_queryout", "montar_cmd_bcp_in",
    "parse_progresso_bcp", "bcp_flags_suportadas",
}


def _extrair(path: Path, nomes: set, ns_extra: dict | None = None) -> dict:
    """Compila apenas as funções/constantes pedidas do módulo (sem importar
    pymssql/airflow). Sanidade extra: ast.parse do ARQUIVO INTEIRO."""
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)  # SyntaxError se o arquivo estiver inválido
    keep = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                and node.name in nomes:
            keep.append(node)
        elif isinstance(node, ast.Assign):
            alvos = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if any(a in nomes for a in alvos):
                keep.append(node)
    achados = {n.name for n in keep if isinstance(n, ast.FunctionDef)} | {
        t.id for n in keep if isinstance(n, ast.Assign)
        for t in n.targets if isinstance(t, ast.Name)}
    faltando = nomes - achados
    assert not faltando, f"símbolos não encontrados em {path.name}: {faltando}"
    ns = {"re": re, "date": date, "datetime": datetime, "Decimal": Decimal,
          "log": logging.getLogger("test_copias_bcp")}
    ns.update(ns_extra or {})
    mod = ast.Module(body=keep, type_ignores=[])
    exec(compile(mod, str(path), "exec"), ns)
    return ns


@pytest.fixture(scope="module")
def bc():
    """Namespace com as funções puras do bulk_copy.py."""
    return _extrair(_BULK_COPY, _NOMES_BULK)


@pytest.fixture(scope="module")
def sql_faixa_bcp(bc):
    """_sql_da_faixa_bcp do etl_copy_exec.py, com o stub de bulk_copy."""
    stub = types.SimpleNamespace(quote_ident=bc["quote_ident"],
                                 sql_literal=bc["sql_literal"])
    ns = _extrair(_COPY_EXEC, {"_sql_da_faixa_bcp"}, {"bulk_copy": stub})
    return ns["_sql_da_faixa_bcp"]


# ═════════════════════════ redigir_cmd (senha em log) ═══════════════════════

def test_redigir_cmd_senha_separada_e_colada(bc):
    cmd = ["bcp", "q", "queryout", "/dev/stdout", "-U", "sa", "-P", "s3cr3t!"]
    red = bc["redigir_cmd"](cmd)
    assert "s3cr3t!" not in red
    assert red[-1] == "****" and red[-2] == "-P"
    assert bc["redigir_cmd"](["-Ps3cr3t!"]) == ["-P****"]
    # nada além da senha é alterado; a lista original não é mutada
    assert red[:6] == cmd[:6]
    assert cmd[-1] == "s3cr3t!"


def test_redigir_cmd_nos_comandos_montados(bc):
    """Nenhum comando montado pode conter a senha após a redação."""
    out = bc["montar_cmd_bcp_queryout"](
        "/opt/mssql-tools18/bin/bcp", "SELECT 1", "h", 1433, "db", "u",
        "Xy'z9!", datafile="/tmp/stg.dat")
    inn = bc["montar_cmd_bcp_in"](
        "bcp", "dbo", "T", "h", 1433, "db", "u", "Xy'z9!", 50000,
        "/tmp/stg.dat")
    for cmd in (out, inn):
        assert "Xy'z9!" in cmd                       # senha vai no argv
        assert "Xy'z9!" not in " ".join(bc["redigir_cmd"](cmd))
        assert "****" in " ".join(bc["redigir_cmd"](cmd))


def test_redigir_texto_apaga_senhas(bc):
    txt = bc["_redigir_texto"]("Login failed for user 'sa' pw=abc123", ("abc123", None))
    assert "abc123" not in txt and "****" in txt


# ═════════════════════════ sql_literal (fronteiras inline) ══════════════════

def test_sql_literal_string_aspas_e_unicode(bc):
    f = bc["sql_literal"]
    assert f("O'Brien") == "'O''Brien'"                    # aspas duplicadas
    assert f("00ab") == "'00ab'"                           # hex ASCII sem N
    assert f("coração") == "N'coração'"                    # unicode ganha N
    assert f("a''b") == "'a''''b'"


def test_sql_literal_rejeita_caractere_de_controle(bc):
    for ruim in ("a\x00b", "x\nY", "t\tz", "\x1b[0m"):
        with pytest.raises(ValueError):
            bc["sql_literal"](ruim)


def test_sql_literal_data_e_datetime_iso(bc):
    f = bc["sql_literal"]
    assert f(date(2024, 1, 2)) == "'2024-01-02'"
    assert f(datetime(2024, 1, 2, 3, 4, 5)) == "'2024-01-02T03:04:05'"
    # milissegundo exato → 3 dígitos (compatível com DATETIME)
    assert f(datetime(2024, 1, 2, 3, 4, 5, 123000)) == "'2024-01-02T03:04:05.123'"
    # precisão sub-ms (datetime2) → 6 dígitos preservados
    assert f(datetime(2024, 1, 2, 3, 4, 5, 123456)) == "'2024-01-02T03:04:05.123456'"


def test_sql_literal_numeros_bool_none(bc):
    f = bc["sql_literal"]
    assert f(42) == "42"
    assert f(-7) == "-7"
    assert f(Decimal("10.50")) == "10.50"
    assert f(3.5) == "3.5"
    assert f(True) == "1" and f(False) == "0"
    assert f(None) == "NULL"


# ═════════════════════ montagem dos comandos bcp ═════════════════════════════

def test_montar_cmd_bcp_queryout_bem_formado(bc):
    sql = "SELECT * FROM (SELECT [id] FROM [DB].[dbo].[T]) AS src"
    cmd = bc["montar_cmd_bcp_queryout"](
        "/opt/mssql-tools18/bin/bcp", sql, "srv01", 1450, "DB_A",
        "usr", "pw", datafile="/dev/fd/9", trust_cert=True)
    assert cmd[0].endswith("bcp")
    assert cmd[1] == sql                       # a query é UM argv (sem shell)
    assert cmd[2:4] == ["queryout", "/dev/fd/9"]
    assert cmd[cmd.index("-S") + 1] == "srv01,1450"
    assert cmd[cmd.index("-d") + 1] == "DB_A"
    assert "-n" in cmd and "-k" in cmd         # formato NATIVO + keep nulls
    assert "-c" not in cmd and "-w" not in cmd  # nunca charset/unicode char
    assert "-u" in cmd                         # trust server certificate
    # sem trust_cert (binário antigo sem -u) a flag some
    cmd2 = bc["montar_cmd_bcp_queryout"]("bcp", sql, "h", None, "d", "u", "p",
                                         trust_cert=False)
    assert "-u" not in cmd2
    assert cmd2[cmd2.index("-S") + 1] == "h,1433"   # porta default


def test_montar_cmd_bcp_in_bem_formado(bc):
    cmd = bc["montar_cmd_bcp_in"](
        "bcp", "dbo", "Minha]Tabela", "srv02", 1433, "DB_B", "usr", "pw",
        75000, "/tmp/stg.dat", trust_cert=True, tablock=True)
    assert cmd[1] == "[dbo].[Minha]]Tabela]"   # 2 partes + quote_ident
    assert cmd[2:4] == ["in", "/tmp/stg.dat"]  # arquivo de staging, não pipe
    assert cmd[cmd.index("-b") + 1] == "75000"
    # -m 1 = aborta no PRIMEIRO erro com exit != 0 (-m 0 = erros ILIMITADOS
    # tolerados com exit 0 — parte do incidente 2026-07-04)
    assert cmd[cmd.index("-m") + 1] == "1"
    assert cmd[cmd.index("-d") + 1] == "DB_B"  # -d + 2 partes (nunca 3 + -d)
    assert "-n" in cmd and "-k" in cmd and "-u" in cmd
    i = cmd.index("-h")
    assert cmd[i + 1] == "TABLOCK"
    # sem suporte a -h (doc: hints são Windows-only) o hint não é passado
    cmd2 = bc["montar_cmd_bcp_in"]("bcp", "dbo", "T", "h", 1433, "d", "u",
                                   "p", 1000, "/tmp/stg.dat", tablock=False)
    assert "-h" not in cmd2


def test_bcp_flags_suportadas_extrai_do_usage(bc):
    usage = (
        "usage: /opt/mssql-tools18/bin/bcp {dbtable | query} {in | out | queryout | format} datafile\n"
        "  [-m maxerrors]            [-f formatfile]          [-e errfile]\n"
        "  [-b batchsize]            [-n native type]         [-k keep null values]\n"
        "  [-h \"load hints\"]         [-d database name]\n"
        "  [-Y conn encryption option[s|m|o]] [-u trust server cert]\n")
    flags = bc["bcp_flags_suportadas"](usage)
    assert {"-m", "-b", "-n", "-k", "-h", "-u", "-Y"} <= flags
    assert bc["bcp_flags_suportadas"]("") == set()
    assert bc["bcp_flags_suportadas"](None) == set()


# ═════════════════════ parse do progresso do bcp in ═════════════════════════

def test_parse_progresso_bcp(bc):
    p = bc["parse_progresso_bcp"]
    assert p("1000 rows sent to SQL Server. Total sent: 1000") == ("lote", 1000)
    assert p("50000 rows sent to SQL Server. Total sent: 150000") == ("lote", 150000)
    assert p("1234567 rows copied.") == ("total", 1234567)
    assert p("0 rows copied.") == ("total", 0)
    assert p("Starting copy...") is None
    assert p("Clock Time (ms.) Total     : 1500") is None
    assert p("") is None and p(None) is None


# ═════════════ SELECT de faixa com fronteiras inline (bcp) ══════════════════

_JOB = {"select_sql": "SELECT [id], [nome] FROM [DB].[dbo].[T] WITH (NOLOCK)",
        "particao_coluna": "id"}


def test_sql_da_faixa_bcp_intervalo_inline(sql_faixa_bcp):
    sql = sql_faixa_bcp(_JOB, {"ini": 1, "fim": 100, "ultima": False})
    assert sql.endswith("WHERE [id] >= 1 AND [id] < 100")
    # última faixa é FECHADA
    sql = sql_faixa_bcp(_JOB, {"ini": 100, "fim": 200, "ultima": True})
    assert sql.endswith("WHERE [id] >= 100 AND [id] <= 200")


def test_sql_da_faixa_bcp_hex_string_escapada(sql_faixa_bcp):
    job = dict(_JOB, particao_coluna="cod_hash")
    sql = sql_faixa_bcp(job, {"ini": "00", "fim": "ff", "ultima": True})
    assert "WHERE [cod_hash] >= '00' AND [cod_hash] <= 'ff'" in sql
    sql = sql_faixa_bcp(job, {"ini": "O'Hara", "fim": "z'z", "ultima": False})
    assert ">= 'O''Hara' AND [cod_hash] < 'z''z'" in sql


def test_sql_da_faixa_bcp_sem_escape_de_porcento(sql_faixa_bcp):
    """O bcp recebe o SQL cru — NUNCA aplicar o escape %% do pymssql."""
    job = {"select_sql": "SELECT [a] FROM [D].[dbo].[T] WHERE [a] LIKE 'x%'",
           "particao_coluna": "a"}
    sql = sql_faixa_bcp(job, {"ini": "b", "fim": "c", "ultima": False})
    assert "LIKE 'x%'" in sql and "%%" not in sql


def test_sql_da_faixa_bcp_unica_null_e_hash(sql_faixa_bcp):
    assert sql_faixa_bcp(_JOB, {"unica": True}) == \
        f"SELECT * FROM ({_JOB['select_sql']}) AS src"
    assert sql_faixa_bcp(_JOB, {"is_null": True}).endswith("WHERE [id] IS NULL")
    sql = sql_faixa_bcp(_JOB, {"hash": (2, 8)})
    assert sql.endswith("AND ABS(CHECKSUM([id])) % 8 = 2")
    assert "IS NOT NULL" in sql


def test_sql_da_faixa_bcp_data_iso(sql_faixa_bcp):
    job = dict(_JOB, particao_coluna="dt_mov")
    sql = sql_faixa_bcp(job, {"ini": date(2024, 1, 1),
                              "fim": datetime(2024, 6, 30, 23, 59, 59),
                              "ultima": True})
    assert ">= '2024-01-01'" in sql
    assert "<= '2024-06-30T23:59:59'" in sql


# ═════════════════ sanidade dos módulos tocados (ast.parse) ══════════════════

def test_dags_tocadas_compilam():
    for p in (_BULK_COPY, _COPY_EXEC):
        ast.parse(p.read_text(encoding="utf-8"))  # SyntaxError se inválido
