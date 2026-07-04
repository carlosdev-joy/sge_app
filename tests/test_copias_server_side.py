"""
Testes da correção do incidente 2026-07-03 do módulo Cópia de Dados
(funções PURAS de dags/etl_copy_exec.py — engine server-side + partição MD5):

  - _sql_da_faixa / _insert_da_faixa: fronteiras TEXTO (modo HEX) INLINE como
    literais varchar sargáveis (nunca N'...', nunca %s); numéricas/data seguem
    parametrizadas com escape %% do select_sql;
  - _workers_efetivos: engine server-side roda faixas SEQUENCIALMENTE (1) —
    INSERT...SELECT WITH (TABLOCK) concorrentes na mesma tabela destino se
    bloqueiam/deadlockam (erro 1205 do incidente);
  - _conexao_morta: distingue conexão MORTA (rede/KILL — DB-Lib 20047) de
    erro SQL comum com sessão viva (deadlock 1205, constraint);
  - _RegistroSpids: registro thread-safe faixa→SPID usado pelo vigia de
    cancelamento.

Mesmo harness do test_copias_bcp.py: os módulos das DAGs importam
pymssql/airflow (indisponíveis aqui), então as funções são EXTRAÍDAS por AST
e compiladas num namespace controlado — aqui estendido para ClassDef
(_RegistroSpids).
"""
from __future__ import annotations

import ast
import logging
import re
import threading
import types
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

_RAIZ = Path(__file__).parent.parent
_BULK_COPY = _RAIZ / "dags" / "utils" / "bulk_copy.py"
_COPY_EXEC = _RAIZ / "dags" / "etl_copy_exec.py"

_NOMES_BULK = {"quote_ident", "sql_literal", "montar_insert_select", "_CTRL_RE"}

_NOMES_EXEC = {
    "_sql_da_faixa", "_insert_da_faixa", "_workers_efetivos",
    "_conexao_morta", "_SINAIS_CONEXAO_MORTA", "_RegistroSpids",
}


def _extrair(path: Path, nomes: set, ns_extra: dict | None = None) -> dict:
    """Compila apenas os símbolos pedidos do módulo (sem importar
    pymssql/airflow) — versão do harness do test_copias_bcp.py que também
    aceita ast.ClassDef. Sanidade extra: ast.parse do ARQUIVO INTEIRO."""
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)  # SyntaxError se o arquivo estiver inválido
    keep = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)) and node.name in nomes:
            keep.append(node)
        elif isinstance(node, ast.Assign):
            alvos = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if any(a in nomes for a in alvos):
                keep.append(node)
    achados = {n.name for n in keep
               if isinstance(n, (ast.FunctionDef, ast.ClassDef))} | {
        t.id for n in keep if isinstance(n, ast.Assign)
        for t in n.targets if isinstance(t, ast.Name)}
    faltando = nomes - achados
    assert not faltando, f"símbolos não encontrados em {path.name}: {faltando}"
    ns = {"re": re, "date": date, "datetime": datetime, "Decimal": Decimal,
          "threading": threading,
          "log": logging.getLogger("test_copias_server_side")}
    ns.update(ns_extra or {})
    mod = ast.Module(body=keep, type_ignores=[])
    exec(compile(mod, str(path), "exec"), ns)
    return ns


@pytest.fixture(scope="module")
def bc():
    """Funções puras reais do bulk_copy.py usadas pelos helpers testados."""
    return _extrair(_BULK_COPY, _NOMES_BULK)


@pytest.fixture(scope="module")
def ce(bc):
    """Namespace com os helpers do etl_copy_exec.py + stub de bulk_copy."""
    stub = types.SimpleNamespace(
        quote_ident=bc["quote_ident"],
        sql_literal=bc["sql_literal"],
        montar_insert_select=bc["montar_insert_select"],
        ENGINE_SERVER_SIDE="server_side_insert",
    )
    return _extrair(_COPY_EXEC, _NOMES_EXEC, {"bulk_copy": stub})


_JOB = {"select_sql": "SELECT [cod_hash], [nome] FROM [DB].[dbo].[T] WITH (NOLOCK)",
        "particao_coluna": "cod_hash",
        "dst_database": "DST", "dst_schema": "dbo", "dst_table": "T2"}
_COLS = ["cod_hash", "nome"]


# ══════════════ _sql_da_faixa — fronteiras TEXTO inline sargáveis ═══════════

def test_sql_da_faixa_hex_inline_sem_n_e_sem_parametros(ce):
    sql, params = ce["_sql_da_faixa"](_JOB, {"ini": "00", "fim": "80",
                                             "ultima": False})
    assert params is None                       # nada para o pymssql formatar
    assert sql.endswith("WHERE [cod_hash] >= '00' AND [cod_hash] < '80'")
    assert "N'" not in sql                      # N'...' mataria a sargabilidade
    assert "%s" not in sql
    # última faixa é FECHADA
    sql, params = ce["_sql_da_faixa"](_JOB, {"ini": "80", "fim": "ff",
                                             "ultima": True})
    assert params is None
    assert sql.endswith(">= '80' AND [cod_hash] <= 'ff'")


def test_sql_da_faixa_hex_nao_escapa_porcento_do_select(ce):
    """Sem parâmetros o pymssql NÃO formata o SQL — escapar %% quebraria."""
    job = dict(_JOB, select_sql="SELECT [a] FROM [D].[dbo].[T] WHERE [a] LIKE 'x%'",
               particao_coluna="a")
    sql, params = ce["_sql_da_faixa"](job, {"ini": "b", "fim": "c",
                                            "ultima": False})
    assert params is None
    assert "LIKE 'x%'" in sql and "%%" not in sql


def test_sql_da_faixa_hex_fronteira_com_aspas_escapada(ce):
    sql, params = ce["_sql_da_faixa"](_JOB, {"ini": "O'Hara", "fim": "z'z",
                                             "ultima": False})
    assert params is None
    assert ">= 'O''Hara' AND [cod_hash] < 'z''z'" in sql


def test_sql_da_faixa_numerica_continua_parametrizada_com_escape(ce):
    job = dict(_JOB, select_sql="SELECT [id] FROM [D].[dbo].[T] WHERE [x] LIKE 'a%'",
               particao_coluna="id")
    sql, params = ce["_sql_da_faixa"](job, {"ini": 1, "fim": 100,
                                            "ultima": False})
    assert params == (1, 100)
    assert sql.endswith("WHERE [id] >= %s AND [id] < %s")
    assert "LIKE 'a%%'" in sql                  # escape %% preservado


def test_sql_da_faixa_unica_null_e_hash_inalteradas(ce):
    sql, params = ce["_sql_da_faixa"](_JOB, {"unica": True})
    assert (sql, params) == (f"SELECT * FROM ({_JOB['select_sql']}) AS src", None)
    sql, params = ce["_sql_da_faixa"](_JOB, {"is_null": True})
    assert sql.endswith("WHERE [cod_hash] IS NULL") and params is None
    sql, params = ce["_sql_da_faixa"](_JOB, {"hash": (2, 8)})
    assert sql.endswith("AND ABS(CHECKSUM([cod_hash])) % 8 = 2")
    assert "IS NOT NULL" in sql and params is None


# ═════════ _insert_da_faixa (server-side) — mesmas regras no INSERT ═════════

def test_insert_da_faixa_hex_inline_sargavel(ce):
    sql, params = ce["_insert_da_faixa"](_JOB, {"ini": "00ab", "fim": "ff",
                                                "ultima": True}, _COLS)
    assert params is None
    assert sql.startswith("INSERT INTO [DST].[dbo].[T2] WITH (TABLOCK) "
                          "([cod_hash], [nome])")
    assert sql.endswith("WHERE [cod_hash] >= '00ab' AND [cod_hash] <= 'ff'")
    assert "N'" not in sql and "%s" not in sql and "%%" not in sql


def test_insert_da_faixa_numerica_continua_parametrizada(ce):
    job = dict(_JOB, particao_coluna="id")
    sql, params = ce["_insert_da_faixa"](job, {"ini": 1, "fim": 100,
                                               "ultima": False}, _COLS)
    assert params == (1, 100)
    assert sql.endswith("WHERE [id] >= %s AND [id] < %s")


def test_insert_da_faixa_data_inline_nao_se_aplica(ce):
    """date/datetime NÃO são str → seguem no caminho parametrizado."""
    job = dict(_JOB, particao_coluna="dt_mov")
    sql, params = ce["_insert_da_faixa"](
        job, {"ini": date(2024, 1, 1), "fim": datetime(2024, 6, 30),
              "ultima": True}, _COLS)
    assert params == (date(2024, 1, 1), datetime(2024, 6, 30))
    assert "%s" in sql


def test_insert_da_faixa_unica_null_e_hash_inalteradas(ce):
    sql, params = ce["_insert_da_faixa"](_JOB, {"unica": True}, _COLS)
    assert params is None and "WHERE" not in sql.split("AS src")[-1]
    sql, params = ce["_insert_da_faixa"](_JOB, {"is_null": True}, _COLS)
    assert sql.endswith("WHERE [cod_hash] IS NULL") and params is None
    sql, params = ce["_insert_da_faixa"](_JOB, {"hash": (0, 4)}, _COLS)
    assert sql.endswith("AND ABS(CHECKSUM([cod_hash])) % 4 = 0")
    assert params is None


# ═══════════ _workers_efetivos — server-side é SEQUENCIAL ═══════════════════

def test_workers_efetivos_server_side_sempre_1(ce):
    f = ce["_workers_efetivos"]
    assert f("server_side_insert", 8, 17) == 1
    assert f("server_side_insert", 1, 1) == 1


def test_workers_efetivos_demais_engines_min_streams_faixas(ce):
    f = ce["_workers_efetivos"]
    assert f("bcp_native", 8, 3) == 3
    assert f("pymssql_bulk_copy", 4, 17) == 4
    assert f("pyodbc_fast", 0, 0) == 1          # piso defensivo
    assert f("pymssql_executemany", None, 5) == 1


# ═══════════ _conexao_morta — conexão morta ≠ erro SQL comum ════════════════

def test_conexao_morta_casa_incidente_20047(ce):
    # Mensagem REAL do incidente 2026-07-03 (log db_erro.png)
    exc = Exception("(20047, b'DB-Lib error message 20047, severity 9:\\n"
                    "DBPROCESS is dead or not enabled\\n')")
    assert ce["_conexao_morta"](exc) is True


def test_conexao_morta_casa_kill_e_quedas_de_rede(ce):
    f = ce["_conexao_morta"]
    assert f(Exception("Read from the server failed (20004)"))
    assert f(Exception("Write to the server failed"))
    assert f(Exception("Connection reset by peer"))
    assert f(Exception("A severe error occurred... severed the connection."))


def test_conexao_morta_nao_casa_erro_sql_com_sessao_viva(ce):
    f = ce["_conexao_morta"]
    # deadlock 1205 (também do incidente) chega com a conexão VIVA
    assert not f(Exception(
        "(1205, b'Transaction (Process ID 68) was deadlocked on lock "
        "resources with another process and has been chosen as the "
        "deadlock victim. Rerun the transaction.')"))
    assert not f(Exception("Violation of PRIMARY KEY constraint"))
    assert not f(Exception("Invalid object name 'dbo.X'"))


# ═══════════ _RegistroSpids — registro thread-safe faixa→SPID ═══════════════

def test_registro_spids_registra_remove_e_isola_snapshot(ce):
    reg = ce["_RegistroSpids"]()
    assert reg.ativos() == {}
    reg.registrar(10, 68)
    reg.registrar(11, "72")                     # coage para int
    assert reg.ativos() == {10: 68, 11: 72}
    snap = reg.ativos()
    snap[99] = 1                                # snapshot é CÓPIA
    assert 99 not in reg.ativos()
    reg.remover(10)
    reg.remover(10)                             # idempotente
    assert reg.ativos() == {11: 72}


def test_registro_spids_concorrente(ce):
    reg = ce["_RegistroSpids"]()

    def registra_e_remove(base):
        for i in range(200):
            reg.registrar(base + i, i + 1)
            reg.remover(base + i)

    ths = [threading.Thread(target=registra_e_remove, args=(b,))
           for b in (0, 1000, 2000, 3000)]
    for t in ths:
        t.start()
    for t in ths:
        t.join()
    assert reg.ativos() == {}


# ═════════════════ sanidade do módulo tocado (ast.parse) ════════════════════

def test_dag_tocada_compila():
    ast.parse(_COPY_EXEC.read_text(encoding="utf-8"))  # SyntaxError se inválido
