#!/usr/bin/env python3
"""
dump_dados.py — Exporta dados das tabelas etl_* como script de INSERTs (offline, pyodbc).

Pensado para rodar DENTRO do container orquestra-api de produção, que já tem
pyodbc instalado e a variável MSSQL_CONN_STR apontando para o banco de prod.

Uso:
    python dump_dados.py --out /tmp/dump_prod.sql
    python dump_dados.py --conn "DRIVER={...};SERVER=...;DATABASE=...;UID=...;PWD=..." --out dump.sql
    python dump_dados.py --tables etl_pipeline,etl_pipeline_job --out parcial.sql

O arquivo gerado é idempotente e auto-contido:
  - desabilita as constraints das tabelas alvo
  - faz DELETE do conteúdo atual (para ser re-executável)
  - reinsere os dados (com SET IDENTITY_INSERT quando a tabela tem identity)
  - reabilita as constraints (sem revalidar linhas já existentes)

NÃO inclui tabelas de autenticação (etl_usuario, etl_sessao, etl_perfil*),
que o ambiente dev já tem via migrations — evita derrubar a sessão atual.

Carregue no dev com:
    docker cp dump_prod.sql orquestra-sqlserver-dev:/tmp/dump_prod.sql
    docker exec orquestra-sqlserver-dev /opt/mssql-tools18/bin/sqlcmd \\
        -C -S localhost -U sa -P 'SENHA' -d orquestra_dev -i /tmp/dump_prod.sql
"""
import argparse
import datetime
import decimal
import os
import sys

try:
    import pyodbc
except ImportError:
    sys.exit("pyodbc não encontrado — rode este script dentro do container orquestra-api.")

# Tabelas de dados (definições + histórico). Ordem pai→filho só por organização;
# como as constraints são desabilitadas no load, a ordem não é crítica.
DEFAULT_TABLES = [
    "etl_project",
    "etl_app_config",
    "etl_job_type",
    "etl_stage_type_map",
    "etl_versao_ferramenta",
    "etl_pipeline",
    "etl_pipeline_job",
    "etl_job_lineage",
    "etl_job_execution",
    "etl_pipeline_audit",
    "etl_pipeline_owner",
    "etl_pipeline_performance_snapshot",
    "etl_object_tag",
    "etl_calendario",
    "etl_blackout",
    "etl_seq_import",
    "etl_seq_import_job",
    "etl_seq_import_lineage",
    "etl_datastage_job_log",
    "etl_factory_log",
]

BATCH = 500  # linhas por INSERT (limite do SQL Server é 1000)


def sql_literal(v) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return repr(v)
    if isinstance(v, decimal.Decimal):
        return str(v)
    if isinstance(v, datetime.datetime):
        return "'" + v.isoformat(sep=" ")[:23] + "'"
    if isinstance(v, datetime.date):
        return "'" + v.isoformat() + "'"
    if isinstance(v, datetime.time):
        return "'" + v.isoformat() + "'"
    if isinstance(v, (bytes, bytearray)):
        return "0x" + bytes(v).hex()
    return "N'" + str(v).replace("'", "''") + "'"


def table_exists(cur, t) -> bool:
    cur.execute(
        "SELECT 1 FROM INFORMATION_SCHEMA.TABLES "
        "WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME=?", [t])
    return cur.fetchone() is not None


def get_columns(cur, t):
    """Colunas inseríveis: exclui computed e timestamp/rowversion."""
    cur.execute(
        "SELECT COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS "
        "WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME=? ORDER BY ORDINAL_POSITION", [t])
    cols = [name for name, dtype in cur.fetchall() if dtype not in ("timestamp", "rowversion")]
    cur.execute(
        "SELECT name FROM sys.computed_columns WHERE object_id = OBJECT_ID('dbo.' + ?)", [t])
    computed = {r[0] for r in cur.fetchall()}
    return [c for c in cols if c not in computed]


def has_identity(cur, t) -> bool:
    cur.execute(
        "SELECT 1 FROM sys.identity_columns WHERE object_id = OBJECT_ID('dbo.' + ?)", [t])
    return cur.fetchone() is not None


def dump_table(cur, t, out) -> int:
    cols = get_columns(cur, t)
    if not cols:
        return 0
    collist = ", ".join("[" + c + "]" for c in cols)
    cur.execute(f"SELECT {collist} FROM dbo.[{t}]")
    rows = cur.fetchall()
    ident = has_identity(cur, t)
    out.write(f"\n-- ===== {t} ({len(rows)} linhas) =====\n")
    if not rows:
        return 0
    if ident:
        out.write(f"SET IDENTITY_INSERT dbo.[{t}] ON;\n")
    for i in range(0, len(rows), BATCH):
        chunk = rows[i:i + BATCH]
        out.write(f"INSERT INTO dbo.[{t}] ({collist}) VALUES\n")
        out.write(",\n".join("(" + ", ".join(sql_literal(v) for v in r) + ")" for r in chunk))
        out.write(";\n")
    if ident:
        out.write(f"SET IDENTITY_INSERT dbo.[{t}] OFF;\n")
    out.write("GO\n")
    return len(rows)


def main():
    ap = argparse.ArgumentParser(description="Dump de dados etl_* como INSERTs.")
    ap.add_argument("--conn", default=os.getenv("MSSQL_CONN_STR", ""),
                    help="Connection string (default: env MSSQL_CONN_STR).")
    ap.add_argument("--out", default="dump_prod.sql", help="Arquivo de saída.")
    ap.add_argument("--tables", default="", help="Lista separada por vírgula (default: todas etl_*).")
    args = ap.parse_args()

    if not args.conn:
        sys.exit("Defina --conn ou a variável de ambiente MSSQL_CONN_STR.")

    tables = [t.strip() for t in args.tables.split(",") if t.strip()] or DEFAULT_TABLES

    conn = pyodbc.connect(args.conn)
    cur = conn.cursor()

    existing = [t for t in tables if table_exists(cur, t)]
    missing = [t for t in tables if t not in existing]

    total = {}
    with open(args.out, "w", encoding="utf-8") as out:
        out.write("-- Dump de dados ORQUESTRA — gerado por sql/dump_dados.py\n")
        out.write("SET NOCOUNT ON;\nGO\n")
        for t in existing:
            out.write(f"ALTER TABLE dbo.[{t}] NOCHECK CONSTRAINT ALL;\n")
        out.write("GO\n")
        for t in reversed(existing):
            out.write(f"DELETE FROM dbo.[{t}];\n")
        out.write("GO\n")
        for t in existing:
            total[t] = dump_table(cur, t, out)
        for t in existing:
            out.write(f"ALTER TABLE dbo.[{t}] CHECK CONSTRAINT ALL;\n")
        out.write("GO\nPRINT 'Dump de dados carregado com sucesso.';\nGO\n")

    print(f"✓ Dump gerado: {args.out}")
    for t in existing:
        print(f"  {t}: {total[t]} linhas")
    if missing:
        print("  (ignoradas — não existem na origem): " + ", ".join(missing))


if __name__ == "__main__":
    main()
