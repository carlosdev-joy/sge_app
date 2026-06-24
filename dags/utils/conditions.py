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


def eval_condition(cond: dict, default_conn_id: str, execution_id: str | None = None):
    """Avalia a condição do nó de decisão.

    Retorna ``(resultado: bool, valor_obtido)``.
    ``cond`` = {tipo, operador, valor, [tabela, database] | [sql] |
                [job_name (linhas_job)], [mssql_conn_id]}.

    ``execution_id`` identifica a execução ATUAL (ts_nodash da DAG run). É
    obrigatório apenas para ``tipo='linhas_job'`` (lê o rows_out do job a
    montante na MESMA execução em dbo.etl_ds_job_log). Os outros tipos o ignoram.
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
    elif tipo == "linhas_job":
        obtido = _rows_out_do_job(hook, cond.get("job_name") or "", execution_id)
    else:
        raise ValueError(f"tipo de condição desconhecido: {tipo!r}")

    return compara(obtido, operador, limite), obtido


def _rows_out_do_job(hook, job_name: str, execution_id: str | None) -> int:
    """Lê o rows_out mais recente de dbo.etl_ds_job_log para ``job_name`` na
    execução ATUAL (``execution_id``). Sem registro / rows_out NULL → 0 (logado).

    Degrada graciosamente: se a tabela/coluna não existir (migration 049 ainda
    não aplicada) ou a leitura falhar, retorna 0 sem quebrar a avaliação."""
    job_name = (job_name or "").strip()
    if not job_name:
        print("[CONDICAO linhas_job] job_name vazio — tratando rows_out como 0.")
        return 0
    try:
        if execution_id:
            row = hook.get_first(
                "SELECT TOP 1 rows_out FROM dbo.etl_ds_job_log "
                "WHERE execution_id=%s AND job_name=%s "
                "ORDER BY COALESCE(updated_at, last_polled_at) DESC",
                parameters=(execution_id, job_name),
            )
        else:
            # Sem execution_id: melhor esforço — registro mais recente do job.
            print("[CONDICAO linhas_job] sem execution_id — usando o registro mais recente do job.")
            row = hook.get_first(
                "SELECT TOP 1 rows_out FROM dbo.etl_ds_job_log "
                "WHERE job_name=%s "
                "ORDER BY COALESCE(updated_at, last_polled_at) DESC",
                parameters=(job_name,),
            )
    except Exception as exc:
        print(f"[CONDICAO linhas_job] leitura de etl_ds_job_log falhou ({exc}) — rows_out=0.")
        return 0
    if not row or row[0] is None:
        print(f"[CONDICAO linhas_job] sem rows_out para job '{job_name}' "
              f"(execution_id={execution_id!r}) — tratando como 0.")
        return 0
    try:
        return int(row[0])
    except (TypeError, ValueError):
        return 0
