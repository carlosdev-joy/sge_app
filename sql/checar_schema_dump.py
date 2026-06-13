#!/usr/bin/env python3
"""
checar_schema_dump.py — Compara o schema embutido em um dump (gerado por
sql/dump_dados.py) com o schema real do banco DEV, sem carregar nada.

O dump traz, em cada bloco, um INSERT com a lista exata de colunas de produção:
    INSERT INTO dbo.[etl_xxx] ([col_a], [col_b], ...) VALUES
Este script extrai essas listas e compara com INFORMATION_SCHEMA do banco alvo,
apontando colunas que existem no dump mas faltam no dev (causa do erro 207),
e colunas que o dev tem mas o dump não preenche.

Uso (dentro do container orquestra-api do DEV, que tem pyodbc):
    python checar_schema_dump.py --dump /tmp/dump_prod.sql
    python checar_schema_dump.py --dump dump_prod.sql \\
        --conn "DRIVER={...};SERVER=orquestra-sqlserver-dev,1433;DATABASE=orquestra_dev;UID=sa;PWD=...;Encrypt=no;TrustServerCertificate=yes"
"""
import argparse
import os
import re
import sys

try:
    import pyodbc
except ImportError:
    sys.exit("pyodbc não encontrado — rode dentro do container orquestra-api do dev.")

INSERT_RE = re.compile(
    r"INSERT\s+INTO\s+dbo\.\[(?P<tbl>[^\]]+)\]\s*\((?P<cols>[^)]*)\)\s+VALUES",
    re.IGNORECASE,
)


def parse_dump(path):
    """Retorna {tabela: [colunas]} a partir do primeiro INSERT de cada tabela."""
    seen = {}
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    for m in INSERT_RE.finditer(text):
        tbl = m.group("tbl")
        if tbl in seen:
            continue
        cols = [c.strip().strip("[]") for c in m.group("cols").split(",")]
        seen[tbl] = cols
    return seen


def dev_columns(cur, tbl):
    cur.execute(
        "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
        "WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME=? ORDER BY ORDINAL_POSITION", [tbl])
    return [r[0] for r in cur.fetchall()]


def main():
    ap = argparse.ArgumentParser(description="Diff de schema dump x dev.")
    ap.add_argument("--dump", default="dump_prod.sql")
    ap.add_argument("--conn", default=os.getenv("MSSQL_CONN_STR", ""))
    args = ap.parse_args()
    if not args.conn:
        sys.exit("Defina --conn ou MSSQL_CONN_STR.")
    if not os.path.exists(args.dump):
        sys.exit(f"Dump não encontrado: {args.dump}")

    dump = parse_dump(args.dump)
    conn = pyodbc.connect(args.conn)
    cur = conn.cursor()

    ok, problemas = [], []
    for tbl, prod_cols in dump.items():
        dev_cols = dev_columns(cur, tbl)
        if not dev_cols:
            problemas.append((tbl, "TABELA NÃO EXISTE NO DEV", prod_cols, []))
            continue
        faltam = [c for c in prod_cols if c not in dev_cols]   # no dump, faltam no dev -> erro 207
        if faltam:
            problemas.append((tbl, "COLUNAS AUSENTES NO DEV", faltam, dev_cols))
        else:
            ok.append(tbl)

    print("=" * 70)
    print(f"OK ({len(ok)} tabelas alinhadas): {', '.join(ok) or '—'}")
    print("=" * 70)
    if not problemas:
        print("Nenhuma divergência — o dump deve carregar sem erro de schema.")
        return
    for tbl, motivo, det, dev_cols in problemas:
        print(f"\n[!] {tbl} — {motivo}")
        print(f"    dump quer : {det}")
        if dev_cols:
            print(f"    dev tem   : {dev_cols}")
    print("\n" + "=" * 70)
    print(f"{len(problemas)} tabela(s) com divergência de schema.")


if __name__ == "__main__":
    main()
