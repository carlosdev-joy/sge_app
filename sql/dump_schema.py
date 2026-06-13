#!/usr/bin/env python3
"""
dump_schema.py — Exporta o SCHEMA (CREATE TABLE) das tabelas etl_* como SQL,
para reproduzir em DEV exatamente a estrutura de PRODUÇÃO (a mesma que a API
em api/main.py espera).

Roda DENTRO do container orquestra-api de produção (tem pyodbc + MSSQL_CONN_STR).

Gera, para cada tabela alvo existente:
  - DROP TABLE IF EXISTS (re-executável)
  - CREATE TABLE com colunas, tipos, tamanho/precisão, nullability,
    IDENTITY e PRIMARY KEY.
NÃO inclui FKs nem índices (não são necessários para carregar dados e servir
a API; evitam problemas de ordem de carga — igual à estratégia do dump de dados).

Uso:
    python dump_schema.py --out /tmp/prod_schema.sql
    python dump_schema.py --tables etl_pipeline,etl_job_execution --out parcial.sql

Aplique no dev (depois de dropar as tabelas divergentes):
    docker cp prod_schema.sql orquestra-sqlserver-dev:/tmp/prod_schema.sql
    docker exec orquestra-sqlserver-dev /opt/mssql-tools18/bin/sqlcmd \\
        -C -S localhost -U sa -P 'SENHA' -d orquestra_dev -i /tmp/prod_schema.sql
"""
import argparse
import os
import sys

try:
    import pyodbc
except ImportError:
    sys.exit("pyodbc não encontrado — rode dentro do container orquestra-api.")

DEFAULT_TABLES = [
    "etl_project", "etl_app_config", "etl_job_type", "etl_stage_type_map",
    "etl_versao_ferramenta", "etl_pipeline", "etl_pipeline_job",
    "etl_job_lineage", "etl_job_execution", "etl_pipeline_audit",
    "etl_pipeline_owner", "etl_pipeline_performance_snapshot",
    "etl_object_tag", "etl_calendario", "etl_blackout",
    "etl_seq_import", "etl_seq_import_job", "etl_seq_import_lineage",
    "etl_datastage_job_log", "etl_factory_log",
]

# Tipos cujo "tamanho" se expressa como (length) em caracteres/bytes
LEN_TYPES = {"varchar", "nvarchar", "char", "nchar", "varbinary", "binary"}
# Tipos com precisão/escala
PREC_TYPES = {"decimal", "numeric"}


def table_exists(cur, t) -> bool:
    cur.execute("SELECT 1 FROM INFORMATION_SCHEMA.TABLES "
                "WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME=?", [t])
    return cur.fetchone() is not None


def column_defs(cur, t):
    cur.execute("""
        SELECT c.name,
               ty.name AS type_name,
               c.max_length,
               c.precision,
               c.scale,
               c.is_nullable,
               c.is_identity,
               COLUMNPROPERTY(c.object_id, c.name, 'IsComputed') AS is_computed
        FROM sys.columns c
        JOIN sys.types ty ON ty.user_type_id = c.user_type_id
        WHERE c.object_id = OBJECT_ID('dbo.' + ?)
        ORDER BY c.column_id
    """, [t])
    return cur.fetchall()


def identity_seed(cur, t):
    cur.execute("""
        SELECT seed_value, increment_value
        FROM sys.identity_columns
        WHERE object_id = OBJECT_ID('dbo.' + ?)
    """, [t])
    r = cur.fetchone()
    return (r[0], r[1]) if r else (1, 1)


def pk_columns(cur, t):
    cur.execute("""
        SELECT col.name
        FROM sys.indexes i
        JOIN sys.index_columns ic ON ic.object_id = i.object_id AND ic.index_id = i.index_id
        JOIN sys.columns col ON col.object_id = ic.object_id AND col.column_id = ic.column_id
        WHERE i.object_id = OBJECT_ID('dbo.' + ?) AND i.is_primary_key = 1
        ORDER BY ic.key_ordinal
    """, [t])
    return [r[0] for r in cur.fetchall()]


def render_type(type_name, max_length, precision, scale):
    tn = type_name.lower()
    if tn in LEN_TYPES:
        if max_length == -1:
            length = "MAX"
        elif tn in ("nvarchar", "nchar"):
            length = str(max_length // 2)  # max_length é em bytes p/ unicode
        else:
            length = str(max_length)
        return f"{type_name}({length})"
    if tn in PREC_TYPES:
        return f"{type_name}({precision},{scale})"
    return type_name


def dump_table(cur, t, out):
    cols = column_defs(cur, t)
    if not cols:
        return False
    pk = pk_columns(cur, t)
    seed, incr = identity_seed(cur, t)
    lines = []
    for name, type_name, max_len, prec, scale, is_null, is_ident, is_comp in cols:
        if is_comp:
            # coluna computada: pula (não temos a expressão aqui; raramente usada nos etl_*)
            continue
        parts = [f"    [{name}]", render_type(type_name, max_len, prec, scale)]
        if is_ident:
            parts.append(f"IDENTITY({seed},{incr})")
        parts.append("NULL" if is_null else "NOT NULL")
        lines.append(" ".join(parts))
    if pk:
        pk_cols = ", ".join(f"[{c}]" for c in pk)
        lines.append(f"    CONSTRAINT [PK_{t}] PRIMARY KEY ({pk_cols})")
    out.write(f"\nIF OBJECT_ID('dbo.{t}', 'U') IS NOT NULL DROP TABLE dbo.[{t}];\nGO\n")
    out.write(f"CREATE TABLE dbo.[{t}] (\n")
    out.write(",\n".join(lines))
    out.write("\n);\nGO\n")
    return True


def main():
    ap = argparse.ArgumentParser(description="Dump de schema (CREATE TABLE) das etl_*.")
    ap.add_argument("--conn", default=os.getenv("MSSQL_CONN_STR", ""))
    ap.add_argument("--out", default="prod_schema.sql")
    ap.add_argument("--tables", default="")
    args = ap.parse_args()
    if not args.conn:
        sys.exit("Defina --conn ou MSSQL_CONN_STR.")

    tables = [s.strip() for s in args.tables.split(",") if s.strip()] or DEFAULT_TABLES
    conn = pyodbc.connect(args.conn)
    cur = conn.cursor()

    feitas, faltando = [], []
    with open(args.out, "w", encoding="utf-8") as out:
        out.write("-- Schema de produção ORQUESTRA — gerado por sql/dump_schema.py\n")
        out.write("SET NOCOUNT ON;\nGO\n")
        for t in tables:
            if not table_exists(cur, t):
                faltando.append(t)
                continue
            if dump_table(cur, t, out):
                feitas.append(t)
        out.write("\nPRINT 'Schema de produção aplicado.';\nGO\n")

    print(f"✓ Schema gerado: {args.out}")
    print("  tabelas:", ", ".join(feitas) or "—")
    if faltando:
        print("  (ignoradas — não existem na origem):", ", ".join(faltando))


if __name__ == "__main__":
    main()
