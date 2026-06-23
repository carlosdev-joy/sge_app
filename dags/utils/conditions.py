"""dags/utils/conditions.py — avaliação de condições do nó de Decisão.

O factory gera DAGs com um BranchPythonOperator cujo callable chama
``eval_condition(...)``. Manter a lógica AQUI (e não no código gerado) significa
que melhorias entram sem regenerar as DAGs — mesmo princípio de
``job_operators.py``.

Segurança (mesmo perfil do tipo de job 'sql' já existente):
  - contagem: identificador de tabela/database validado por regex (anti-injeção).
  - query: SQL precisa ser read-only — começar com SELECT/WITH, sem ';' nem DML.
"""
from __future__ import annotations

import re

_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_OPERADORES = {"=", "==", "<>", "!=", ">", ">=", "<", "<="}
_DML_RE = re.compile(
    r"\b(INSERT|UPDATE|DELETE|MERGE|DROP|ALTER|CREATE|TRUNCATE|EXEC|EXECUTE|"
    r"GRANT|REVOKE|INTO)\b",
    re.IGNORECASE,
)


def _safe_table(tabela: str) -> str:
    """Valida 'db.schema.tabela' (1–3 partes, cada uma identificador válido) e
    devolve com colchetes. Levanta ValueError se inválido (anti-injeção)."""
    if not tabela or not isinstance(tabela, str):
        raise ValueError("tabela da condição vazia")
    parts = tabela.strip().split(".")
    if not 1 <= len(parts) <= 3:
        raise ValueError(f"identificador de tabela inválido: {tabela!r}")
    for p in parts:
        if not _IDENT_RE.match(p):
            raise ValueError(f"parte inválida no identificador de tabela: {p!r}")
    return ".".join(f"[{p}]" for p in parts)


def _validate_select(sql: str) -> str:
    """Garante SQL read-only de leitura única. Levanta ValueError caso contrário."""
    if not sql or not isinstance(sql, str):
        raise ValueError("SQL da condição vazio")
    s = sql.strip().rstrip(";").strip()
    if ";" in s:
        raise ValueError("SQL da condição não pode conter ';' (apenas um SELECT)")
    head = s.lstrip("(").lstrip().upper()
    if not (head.startswith("SELECT") or head.startswith("WITH")):
        raise ValueError("SQL da condição precisa começar com SELECT (read-only)")
    if _DML_RE.search(s):
        raise ValueError("SQL da condição contém comando não permitido (read-only)")
    return s


def _coerce_num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def compara(obtido, operador, limite) -> bool:
    """Compara ``valor_obtido <operador> valor_limite``. Numérico quando ambos
    convertem para número; senão, comparação textual."""
    operador = str(operador or "").strip()
    if operador not in _OPERADORES:
        raise ValueError(f"operador inválido: {operador!r}")
    a, b = _coerce_num(obtido), _coerce_num(limite)
    if a is None or b is None:
        a = "" if obtido is None else str(obtido)
        b = "" if limite is None else str(limite)
    if operador in ("=", "=="):
        return a == b
    if operador in ("<>", "!="):
        return a != b
    if operador == ">":
        return a > b
    if operador == ">=":
        return a >= b
    if operador == "<":
        return a < b
    return a <= b  # "<="


def eval_condition(cond: dict, default_conn_id: str):
    """Avalia a condição do nó de decisão.

    Retorna ``(resultado: bool, valor_obtido)``.
    ``cond`` = {tipo, operador, valor, [tabela, database] | [sql], [mssql_conn_id]}.
    """
    from airflow.providers.microsoft.mssql.hooks.mssql import MsSqlHook  # lazy

    cond = cond or {}
    tipo = str(cond.get("tipo") or "").strip().lower()
    operador = cond.get("operador") or ">"
    limite = cond.get("valor")
    conn_id = (cond.get("mssql_conn_id") or "").strip() or default_conn_id
    hook = MsSqlHook(mssql_conn_id=conn_id)

    if tipo == "contagem":
        tabela = _safe_table(cond.get("tabela") or "")
        database = (cond.get("database") or "").strip()
        sql = f"SELECT COUNT_BIG(*) FROM {tabela}"
        if database:
            if not _IDENT_RE.match(database):
                raise ValueError(f"database inválido: {database!r}")
            sql = f"USE [{database}]; {sql}"
        row = hook.get_first(sql)
        obtido = int(row[0]) if row and row[0] is not None else 0
    elif tipo == "query":
        sql = _validate_select(cond.get("sql") or "")
        row = hook.get_first(sql)
        obtido = row[0] if row else None
    else:
        raise ValueError(f"tipo de condição desconhecido: {tipo!r}")

    return compara(obtido, operador, limite), obtido
