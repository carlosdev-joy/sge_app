"""
Testes de services/conn_native.py — caminho rápido da introspecção com a
credencial NATIVA da conexão (dbo.etl_conexao).

Contrato de abrir_conexao_nativa:
  - conn_id legado (fora da tabela) ou tabela indisponível → None (o chamador
    cai para a credencial do app);
  - conexão nativa existe e conecta → (conn, cursor) pyodbc;
  - conexão nativa existe mas o connect falha → RuntimeError SEM a senha.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from services.conn_native import (
    abrir_conexao_nativa, melhor_driver_odbc, odbc_quote, sem_senha,
)


def _db_com_row(row):
    cur = MagicMock()
    cur.fetchone.return_value = row
    conn = MagicMock()
    conn.cursor.return_value = cur
    return conn


# ═════════════════════════ abrir_conexao_nativa ═════════════════════════════

def test_conn_id_legado_retorna_none():
    with patch("services.conn_native.get_db_conn",
               return_value=_db_com_row(None)):
        assert abrir_conexao_nativa("SQL_LEGADA", "master") is None


def test_tabela_indisponivel_retorna_none():
    with patch("services.conn_native.get_db_conn",
               side_effect=Exception("tabela não existe")):
        assert abrir_conexao_nativa("SQL69", "master") is None


def test_nativa_conecta_com_credencial_da_conexao():
    row = ("SQL69", 1478, "usr_dstage_bicvp", "gAAAA-token")
    fake_cx = MagicMock()
    with patch("services.conn_native.get_db_conn",
               return_value=_db_com_row(row)), \
         patch("services.conn_native.decrypt_password",
               return_value="s3nh4!") as dec, \
         patch("services.conn_native.pyodbc") as pyo:
        pyo.connect.return_value = fake_cx
        par = abrir_conexao_nativa("SQL69", "DBBUCC", timeout_s=7)
    assert par == (fake_cx, fake_cx.cursor.return_value)
    dec.assert_called_once_with("gAAAA-token")
    conn_str = pyo.connect.call_args.args[0]
    assert "SERVER=SQL69,1478" in conn_str
    assert "DATABASE={DBBUCC}" in conn_str
    assert "UID={usr_dstage_bicvp}" in conn_str
    assert "PWD={s3nh4!}" in conn_str
    assert "TrustServerCertificate=yes" in conn_str
    assert pyo.connect.call_args.kwargs["timeout"] == 7


def test_nativa_falha_no_connect_levanta_runtimeerror_sem_senha():
    row = ("SQL69", 1478, "usr", "tok")
    with patch("services.conn_native.get_db_conn",
               return_value=_db_com_row(row)), \
         patch("services.conn_native.decrypt_password",
               return_value="s3nh4-secreta"), \
         patch("services.conn_native.pyodbc") as pyo:
        pyo.connect.side_effect = Exception("Login failed; PWD=s3nh4-secreta")
        with pytest.raises(RuntimeError) as exc:
            abrir_conexao_nativa("SQL69", "master")
    msg = str(exc.value)
    assert "s3nh4-secreta" not in msg          # senha NUNCA vaza no erro
    assert "SQL69" in msg and "1478" in msg


def test_host_vazio_retorna_none():
    with patch("services.conn_native.get_db_conn",
               return_value=_db_com_row(("   ", 1433, "u", "tok"))), \
         patch("services.conn_native.decrypt_password", return_value="p"):
        assert abrir_conexao_nativa("SQL_X", "master") is None


# ═══════════════════════════ helpers puros ══════════════════════════════════

def test_odbc_quote_escapa_chaves_e_ponto_e_virgula():
    assert odbc_quote("senha;PWD=x") == "{senha;PWD=x}"   # ';' inerte entre chaves
    assert odbc_quote("ab}cd") == "{ab}}cd}"


def test_sem_senha_redige_segredos():
    assert "abc123" not in sem_senha("erro pw=abc123", "abc123", None)
    assert sem_senha("sem segredo", "x") == "sem segredo"


def test_melhor_driver_odbc_tem_fallback():
    with patch("services.conn_native.pyodbc") as pyo:
        pyo.drivers.return_value = ["ODBC Driver 17 for SQL Server",
                                    "ODBC Driver 18 for SQL Server"]
        assert melhor_driver_odbc() == "ODBC Driver 18 for SQL Server"
        pyo.drivers.side_effect = Exception("sem driver")
        assert melhor_driver_odbc() == "ODBC Driver 18 for SQL Server"
