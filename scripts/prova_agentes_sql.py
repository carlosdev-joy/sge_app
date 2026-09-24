"""Prova da consulta a banco dos agentes no SQL Server do DEV — critério 2 da
spec docs/spec-agentes-ferramenta-banco.md: "só SELECT roda, mesmo com login
de escrita". Rodar a cada mudança de services/agentes_sql.py.

Cria dois bancos (`agsql_liberado`, `agsql_outro`), três logins temporários
(escritor = db_owner; leitor com SHOWPLAN; leitor sem SHOWPLAN) e três
conexões nativas `agsql_e2e_*` em dbo.etl_conexao; roda os casos pelo
`consultar()` de verdade — os ataques COM A CAMADA 1 DESLIGADA, para provar
que as camadas 2 e 3 sozinhas seguram — e apaga tudo no fim, passe ou falhe.

Uso (DEV — nunca em produção):

    docker cp api orquestra-api:/tmp/api_c1
    docker cp scripts/prova_agentes_sql.py orquestra-api:/tmp/
    docker exec -e ORQ_PROVA_DEV=1 -w /tmp/api_c1 orquestra-api python /tmp/prova_agentes_sql.py

`MSSQL_CONN_STR` (a do container) precisa ser de um login que crie banco e
login (o `sa` do DEV). Sai com código 1 se algum caso falhar.
"""
from __future__ import annotations

import os
import re
import sys

if os.environ.get("ORQ_PROVA_DEV") != "1":
    sys.exit("recusado: defina ORQ_PROVA_DEV=1 (cria e apaga bancos e logins — só no DEV)")

sys.path.insert(0, os.getcwd())
import pyodbc  # noqa: E402

from services import agentes_sql as s  # noqa: E402
from services.conn_crypto import encrypt_password  # noqa: E402

CS = os.environ["MSSQL_CONN_STR"]
BANCO_APP = re.search(r"DATABASE=([^;]+)", CS, re.I).group(1)
host, _, port = re.search(r"SERVER=([^;]+)", CS, re.I).group(1).partition(",")
adm = pyodbc.connect(CS, autocommit=True, timeout=10)
a = adm.cursor()
SENHA = "Agsql#prova!2026x"
LOGINS = ("agsql_leitor", "agsql_escritor", "agsql_semplano", "agsql_tabela")
E, L, SP = "agsql_e2e_agsql_escritor", "agsql_e2e_agsql_leitor", "agsql_e2e_agsql_semplano"
T = "agsql_e2e_agsql_tabela"   # leitor com GRANT de escrita só numa tabela
LIB = {"agsql_liberado"}


def x(sql: str, db: str | None = None) -> None:
    if db:
        a.execute(f"USE {db}")
    a.execute(sql)
    while a.nextset():
        pass


def um(sql: str, db: str):
    a.execute(f"USE {db}")
    a.execute(sql)
    return a.fetchone()[0]


def limpar() -> None:
    x("USE master")
    a.execute("SELECT session_id FROM sys.dm_exec_sessions WHERE login_name LIKE 'agsql[_]%'")
    for (sid,) in a.fetchall():
        x(f"KILL {sid}")
    for db in ("agsql_liberado", "agsql_outro"):
        x(f"IF DB_ID('{db}') IS NOT NULL BEGIN ALTER DATABASE {db} SET SINGLE_USER WITH ROLLBACK IMMEDIATE; "
          f"DROP DATABASE {db} END")
    for login in LOGINS:
        x(f"IF SUSER_ID('{login}') IS NOT NULL DROP LOGIN {login}")
    x(f"DELETE FROM {BANCO_APP}.dbo.etl_conexao WHERE conn_id LIKE 'agsql[_]e2e[_]%'")


def preparar() -> None:
    limpar()
    for db in ("agsql_liberado", "agsql_outro"):
        x(f"CREATE DATABASE {db}")
    x("CREATE TABLE dbo.t (id INT PRIMARY KEY, nome VARCHAR(50))", "agsql_outro")
    x("CREATE TABLE dbo.t (id INT PRIMARY KEY, nome VARCHAR(50), cpf VARCHAR(20), obs VARCHAR(100))",
      "agsql_liberado")
    x("INSERT dbo.t VALUES (1,'ana','529.982.247-25','fone (11) 91234-5678'),(2,'bia',NULL,'bia@x.com')",
      "agsql_liberado")
    x("INSERT dbo.t SELECT TOP 300 100 + ROW_NUMBER() OVER (ORDER BY (SELECT 1)), 'n', NULL, NULL "
      "FROM sys.all_objects", "agsql_liberado")
    x("CREATE SEQUENCE dbo.seq START WITH 1", "agsql_liberado")
    x("CREATE SYNONYM dbo.syn_outro FOR agsql_outro.dbo.t", "agsql_liberado")
    x("CREATE VIEW dbo.v_outro AS SELECT id FROM agsql_outro.dbo.t", "agsql_liberado")
    x("ALTER DATABASE agsql_liberado SET COMPATIBILITY_LEVEL = 140")   # UDF escalar não inline
    x("CREATE FUNCTION dbo.fn_dmv() RETURNS NVARCHAR(200) AS BEGIN "
      "RETURN (SELECT TOP 1 login_name FROM sys.dm_exec_sessions) END", "agsql_liberado")
    x("CREATE TABLE dbo.anexo (id INT PRIMARY KEY, conteudo VARBINARY(MAX))", "agsql_liberado")
    x("INSERT dbo.anexo SELECT TOP 30 ROW_NUMBER() OVER (ORDER BY (SELECT 1)), "
      "CAST(REPLICATE(CAST('x' AS VARCHAR(MAX)), 10000000) AS VARBINARY(MAX)) FROM sys.all_objects",
      "agsql_liberado")
    for login in LOGINS:
        x(f"CREATE LOGIN {login} WITH PASSWORD = '{SENHA}', CHECK_POLICY = OFF", "master")
        x(f"CREATE USER {login} FOR LOGIN {login}", "agsql_liberado")
    x("ALTER ROLE db_datareader ADD MEMBER agsql_leitor; GRANT SHOWPLAN TO agsql_leitor", "agsql_liberado")
    x("ALTER ROLE db_owner ADD MEMBER agsql_escritor", "agsql_liberado")
    x("CREATE USER agsql_escritor FOR LOGIN agsql_escritor; ALTER ROLE db_owner ADD MEMBER agsql_escritor",
      "agsql_outro")
    x("ALTER ROLE db_datareader ADD MEMBER agsql_semplano", "agsql_liberado")
    x("ALTER ROLE db_datareader ADD MEMBER agsql_tabela; GRANT SHOWPLAN TO agsql_tabela; "
      "GRANT INSERT, DELETE ON dbo.t TO agsql_tabela", "agsql_liberado")
    for login in LOGINS:
        x(f"INSERT {BANCO_APP}.dbo.etl_conexao (conn_id, conn_type, host, port, login, senha_enc) VALUES "
          f"('agsql_e2e_{login}', 'mssql', '{host}', {port or 'NULL'}, '{login}', '{encrypt_password(SENHA)}')")


def estado() -> tuple:
    return (um("SELECT COUNT(*) FROM dbo.t", "agsql_liberado"),
            um("SELECT CHECKSUM_AGG(CHECKSUM(*)) FROM dbo.t", "agsql_liberado"),
            um("SELECT CONVERT(BIGINT, current_value) FROM sys.sequences WHERE name = 'seq'", "agsql_liberado"),
            um("SELECT COUNT(*) FROM sys.objects WHERE is_ms_shipped = 0", "agsql_liberado"),
            um("SELECT COUNT(*) FROM dbo.t", "agsql_outro"),
            um("SELECT COUNT(*) FROM sys.objects WHERE is_ms_shipped = 0", "agsql_outro"))


# Ataques que ESCREVERIAM se chegassem a executar — rodados SEM a camada 1.
ATAQUES = [
    "SELECT 1DELETE FROM dbo.t SELECT 1COMMIT",
    "DELETE FROM dbo.t",
    "UPDATE dbo.t SET nome = 'x'",
    "INSERT dbo.t (id) VALUES (999)",
    "MERGE dbo.t AS d USING (SELECT 999 id) o ON d.id = o.id WHEN NOT MATCHED THEN INSERT (id) VALUES (o.id);",
    "SELECT NEXT VALUE FOR dbo.seq",
    "SELECT * INTO dbo.copia FROM dbo.t",
    "SELECT 1 IF 1 = 1 DELETE FROM dbo.t",
    "WHILE 1 = 0 SELECT 1",
    "SELECT 1; TRUNCATE TABLE dbo.t",
    "CREATE TABLE dbo.nova (x INT)",
    "DROP TABLE dbo.t",
    "EXEC ('DELETE FROM dbo.t')",
    "SELECT 1 EXEC sp_executesql N'DELETE FROM dbo.t'",
    "SELECT * FROM dbo.syn_outro",
    "SELECT * FROM dbo.v_outro",
    "SELECT * FROM agsql_outro.dbo.t",
    "DELETE FROM agsql_outro.dbo.t",
    "SELECT * FROM sysprocesses",
    "SELECT * FROM sys.login_token",
    "SELECT sql FROM syscacheobjects",
    "SELECT 1 WAITFOR DELAY '00:00:01'",
    "BEGIN TRAN DELETE FROM dbo.t COMMIT",
    "SET SHOWPLAN_XML OFF",
    "SELECT dbo.fn_dmv()",
]


def main() -> int:
    falhas: list[str] = []

    def conferir(nome: str, ok: bool, detalhe="") -> None:
        print(("OK   " if ok else "FALHA"), nome, str(detalhe)[:140].replace("\n", " | "))
        if not ok:
            falhas.append(nome)

    def consultar(conn_id: str, sql: str, banco: str = "agsql_liberado", **kw):
        return s.consultar(conn_id, banco, sql, bancos_da_conexao=kw.pop("liberados", LIB),
                           mascarar=kw.pop("mascarar", True), timeout_s=kw.pop("timeout_s", 30))

    preparar()
    try:
        antes = estado()
        r = consultar(E, "SELECT id, nome, cpf, obs FROM dbo.t ORDER BY id")
        conferir("select com login de escrita", r["havia_mais"] and len(r["linhas"]) == 100, r["texto"][:80])
        conferir("máscara por coluna e por valor",
                 "[oculto]" in r["texto"] and "[telefone]" in r["texto"] and "[email]" in r["texto"]
                 and "529.982" not in r["texto"] and "bia@x" not in r["texto"])
        r = consultar(E, "SELECT TOP 1 cpf FROM dbo.t ORDER BY id", mascarar=False)
        conferir("sem máscara quando desligada", "529.982.247-25" in r["texto"])
        conferir("SQL executado é o recebido", r["sql"] == "SELECT TOP 1 cpf FROM dbo.t ORDER BY id")

        original = s.validar
        s.validar = lambda sql: sql  # camada 1 DESLIGADA: só as camadas 2 e 3
        try:
            for sql in ATAQUES:
                try:
                    consultar(E, sql, liberados=LIB)
                    conferir(f"ataque sem camada 1: {sql}", False, "EXECUTOU")
                except (s.SqlRecusado, s.BancoIndisponivel, pyodbc.Error) as e:
                    conferir(f"ataque sem camada 1: {sql}", True, getattr(e, "regra", None) or type(e).__name__)
                conferir(f"  estado intacto após: {sql}", estado() == antes)
        finally:
            s.validar = original

        for sql in ATAQUES:
            try:
                s.validar(sql)
                conferir(f"camada 1 recusa: {sql}", sql in ("SELECT * FROM dbo.syn_outro", "SELECT * FROM dbo.v_outro",
                                                              "SELECT dbo.fn_dmv()"),
                         "passou na camada 1 (a 2 segura)")
            except s.SqlRecusado as e:
                conferir(f"camada 1 recusa: {sql}", True, e.regra)

        import resource
        pico = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        r = consultar(E, "SELECT id, conteudo FROM dbo.anexo ORDER BY id")
        cresceu_mb = (resource.getrusage(resource.RUSAGE_SELF).ru_maxrss - pico) / 1024
        conferir("anexo grande: memória com teto", cresceu_mb < 120 and "<10000000 bytes>" in r["texto"],
                 f"pico +{cresceu_mb:.0f} MB, {len(r['linhas'])} linhas, havia_mais={r['havia_mais']}")
        for sql in ("SELECT IDENT_CURRENT('agsql_outro.dbo.t')", "SELECT COL_LENGTH('agsql_outro.dbo.t', 'id')",
                    "SELECT OBJECT_ID('agsql_outro.' + 'dbo.t')", "SELECT t.* FROM dbo.t t WHERE t.id = 1"):
            try:
                r = consultar(E, sql)
                conferir(f"metadado de outro banco: {sql}", sql.startswith("SELECT t.*"), r["texto"][:60])
            except s.SqlRecusado as e:
                conferir(f"metadado de outro banco: {sql}", not sql.startswith("SELECT t.*"), e.regra)
        conferir("aviso: escrita concedida por tabela", len(s.verificar_pares([(T, "agsql_liberado")])) == 1)
        conferir("sem aviso para leitor puro", s.verificar_pares([(L, "agsql_liberado")]) == [])
        r = consultar(L, "SELECT COUNT(*) n FROM dbo.t")
        conferir("leitor com SHOWPLAN", r["texto"].endswith("302"))
        try:
            consultar(SP, "SELECT id FROM dbo.t")
            conferir("sem SHOWPLAN é indisponível", False, "EXECUTOU")
        except s.BancoIndisponivel as e:
            conferir("sem SHOWPLAN é indisponível", True, e)
        for nome, sql, esperado in (
                ("tabela inexistente", "SELECT * FROM dbo.nao_existe", "tabela ou objeto inexistente"),
                ("coluna inexistente", "SELECT zzz FROM dbo.t", "coluna inexistente"),
                ("sintaxe", "SELECT id FROM dbo.t WHERE", "sintaxe inválida"),
                ("tempo", "SELECT COUNT_BIG(*) FROM dbo.t a CROSS JOIN dbo.t b CROSS JOIN dbo.t c "
                          "CROSS JOIN dbo.t d CROSS JOIN dbo.t e", "tempo esgotado")):
            try:
                consultar(E, sql, timeout_s=2 if nome == "tempo" else 30)
                conferir(nome, False, "sem erro")
            except Exception as e:  # noqa: BLE001
                msg, _ = s.mensagem_de_erro(e, mascarar=True)
                conferir(nome, msg.startswith(esperado) and host not in msg, msg)
        for nome, conn_id, banco in (("conexão inexistente", "agsql_e2e_nao_existe", "agsql_liberado"),
                                     ("banco sem acesso", L, "agsql_outro")):
            try:
                consultar(conn_id, "SELECT 1", banco=banco)
                conferir(nome, False, "abriu")
            except s.BancoIndisponivel as e:
                conferir(nome, str(e) == "conexão indisponível", e)

        r = s.estrutura(E, "agsql_liberado", filtro="%_", tabela=None, mascarar=True, timeout_s=30)
        conferir("estrutura: filtro com curinga é literal", r["texto"] == "nenhuma tabela encontrada", r["texto"])
        r = s.estrutura(E, "agsql_liberado", filtro=None, tabela="dbo.t", mascarar=True, timeout_s=30)
        conferir("estrutura: colunas", "\tcpf\t" in r["texto"], r["texto"])
        info = s.bancos_da_conexao(E)
        conferir("bancos: escritor avisa escrita", all(b["escrita"] for b in info["bancos"]), info)
        info = s.bancos_da_conexao(SP)
        conferir("bancos: sem SHOWPLAN aparece", info["bancos"] == [
            {"banco": "agsql_liberado", "showplan": False, "escrita": False}], info)
        try:
            s.verificar_pares([(SP, "agsql_liberado")])
            conferir("verificar_pares recusa sem SHOWPLAN", False)
        except ValueError as e:
            conferir("verificar_pares recusa sem SHOWPLAN", "SHOWPLAN" in str(e), e)
        conferir("verificar_pares avisa escrita", len(s.verificar_pares([(E, "agsql_liberado")])) == 1)
        conferir("estado final intacto", estado() == antes, estado())
        abertas = um("SELECT COUNT(*) FROM sys.dm_tran_session_transactions st JOIN sys.dm_exec_sessions es "
                     "ON es.session_id = st.session_id WHERE es.login_name LIKE 'agsql[_]%'", "master")
        conferir("nenhuma transação aberta", abertas == 0, abertas)
    finally:
        limpar()
    print(f"\n{len(falhas)} falha(s)" if falhas else "\ntudo certo")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
