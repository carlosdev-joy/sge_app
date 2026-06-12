#!/usr/bin/env python3
"""
sql/migrate.py — Aplica migrations pendentes do ORQUESTRA em ordem.

Uso:
    python sql/migrate.py                    # aplica tudo pendente
    python sql/migrate.py --dry-run          # mostra o que seria aplicado
    python sql/migrate.py --status           # lista estado de todas as migrations
    python sql/migrate.py --conn "DSN=..."   # substitui MSSQL_CONN_STR

Sem dependências além de pyodbc (já instalado na API) e stdlib Python 3.10+.
Funciona 100% offline — não requer internet nem npm.

Convenção de nomes:
    Arquivos em sql/migrations/ com formato NNN_descricao.sql
    são aplicados em ordem numérica crescente.
    Apenas o prefixo numérico importa para a ordenação.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
from pathlib import Path

try:
    import pyodbc
except ImportError:
    print("ERRO: pyodbc não encontrado. Instale com: pip install pyodbc", file=sys.stderr)
    sys.exit(1)


MIGRATIONS_DIR = Path(__file__).parent / "migrations"
CONN_STR = os.getenv("MSSQL_CONN_STR", "")


def _conn(conn_str: str) -> "pyodbc.Connection":
    if not conn_str:
        print("ERRO: MSSQL_CONN_STR não definida. Use --conn ou a variável de ambiente.",
              file=sys.stderr)
        sys.exit(1)
    return pyodbc.connect(conn_str, timeout=30, autocommit=False)


def _migration_name(path: Path) -> str:
    """Retorna o nome canônico sem extensão (ex: '021_schema_version')."""
    return path.stem


def _sort_key(path: Path) -> int:
    """Ordena pelo prefixo numérico: 002_... → 2, 021_... → 21."""
    m = re.match(r"^(\d+)", path.stem)
    return int(m.group(1)) if m else 9999


def _file_checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def _ensure_schema_version_table(cur) -> None:
    cur.execute("""
        IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES
                       WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME='etl_schema_version')
        CREATE TABLE dbo.etl_schema_version (
            id             INT          IDENTITY(1,1) NOT NULL,
            migration_name VARCHAR(120) NOT NULL,
            applied_at     DATETIME     NOT NULL DEFAULT GETDATE(),
            applied_by     VARCHAR(50)  NULL,
            checksum       VARCHAR(64)  NULL,
            CONSTRAINT PK_schema_version PRIMARY KEY (id),
            CONSTRAINT UQ_schema_version_name UNIQUE (migration_name)
        )
    """)


def _applied_set(cur) -> set[str]:
    cur.execute("SELECT migration_name FROM dbo.etl_schema_version")
    return {row[0] for row in cur.fetchall()}


def _apply_migration(conn, cur, path: Path, applied_by: str = "migrate.py") -> None:
    """Executa um arquivo .sql. Suporta blocos separados por GO (T-SQL)."""
    sql_text = path.read_text(encoding="utf-8")
    # Remove comentários de linha e divide em blocos por GO
    blocks = re.split(r"^\s*GO\s*$", sql_text, flags=re.MULTILINE | re.IGNORECASE)
    for block in blocks:
        block = block.strip()
        if block:
            cur.execute(block)
    # Registra na tabela de controle
    name = _migration_name(path)
    chk  = _file_checksum(path)
    cur.execute(
        "INSERT INTO dbo.etl_schema_version (migration_name, applied_by, checksum) "
        "VALUES (?, ?, ?)",
        [name, applied_by, chk],
    )
    conn.commit()


def list_migrations() -> list[Path]:
    """Retorna todos os .sql em sql/migrations/, ordenados por prefixo numérico."""
    if not MIGRATIONS_DIR.exists():
        print(f"ERRO: diretório {MIGRATIONS_DIR} não encontrado", file=sys.stderr)
        sys.exit(1)
    return sorted(MIGRATIONS_DIR.glob("*.sql"), key=_sort_key)


def cmd_status(conn_str: str) -> None:
    conn = _conn(conn_str)
    cur  = conn.cursor()
    _ensure_schema_version_table(cur)
    conn.commit()
    applied = _applied_set(cur)
    migrations = list_migrations()
    print(f"{'STATUS':<10} {'MIGRATION':<45} {'CHECKSUM'}")
    print("-" * 75)
    for path in migrations:
        name   = _migration_name(path)
        status = "APLICADA" if name in applied else "PENDENTE"
        chk    = _file_checksum(path)
        marker = "✓" if name in applied else "→"
        print(f"{marker} {status:<8}  {name:<45} {chk}")
    pending = [p for p in migrations if _migration_name(p) not in applied]
    cur.close(); conn.close()
    print()
    print(f"Total: {len(migrations)} migrations | {len(applied)} aplicadas | {len(pending)} pendentes")


def cmd_migrate(conn_str: str, dry_run: bool = False) -> None:
    conn = _conn(conn_str)
    cur  = conn.cursor()
    _ensure_schema_version_table(cur)
    conn.commit()
    applied    = _applied_set(cur)
    migrations = list_migrations()
    pending    = [p for p in migrations if _migration_name(p) not in applied]

    if not pending:
        print("Nenhuma migration pendente — banco está atualizado.")
        cur.close(); conn.close()
        return

    print(f"{'DRY-RUN: ' if dry_run else ''}Aplicando {len(pending)} migration(s):")
    for path in pending:
        name = _migration_name(path)
        if dry_run:
            print(f"  [DRY-RUN] {name}")
            continue
        print(f"  → Aplicando {name}...", end=" ", flush=True)
        try:
            _apply_migration(conn, cur, path)
            print("OK")
        except Exception as exc:
            print(f"ERRO\n\nFalha ao aplicar {name}:\n{exc}", file=sys.stderr)
            try:
                conn.rollback()
            except Exception:
                pass
            cur.close(); conn.close()
            sys.exit(1)

    cur.close(); conn.close()
    if not dry_run:
        print(f"\nConcluído: {len(pending)} migration(s) aplicada(s).")


def main() -> None:
    parser = argparse.ArgumentParser(description="Aplicador de migrations ORQUESTRA")
    parser.add_argument("--dry-run",  action="store_true",
                        help="Mostra o que seria aplicado sem executar")
    parser.add_argument("--status",   action="store_true",
                        help="Lista o estado de todas as migrations")
    parser.add_argument("--conn",     default=CONN_STR,
                        help="Connection string pyodbc (padrão: MSSQL_CONN_STR)")
    args = parser.parse_args()

    if args.status:
        cmd_status(args.conn)
    else:
        cmd_migrate(args.conn, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
