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
from datetime import date, datetime

_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_OPERADORES = {"=", "==", "<>", "!=", ">", ">=", "<", "<="}
_COMPARACOES = {"texto", "data", "numero"}
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


def _aplica_operador(a, b, operador) -> bool:
    """Aplica ``a <operador> b`` com valores já normalizados (números ou datas).
    ``operador`` já validado (∈ _OPERADORES)."""
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


def _to_date(v):
    """Normaliza ``v`` para ``datetime.date`` (nível de dia, ignora hora).

    Aceita date/datetime (pyodbc devolve assim) ou string. Token ``HOJE`` (case-
    insensitive, com strip) → ``date.today()``. String tenta ``YYYY-MM-DD`` (e o
    prefixo de um ISO datetime ``YYYY-MM-DD HH:MM:SS`` / ``…THH:MM:SS``). Não
    parseável → None (o chamador loga e devolve False)."""
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v).strip()
    if not s:
        return None
    if s.upper() == "HOJE":
        return date.today()
    # Pega só a parte da data de um possível datetime (espaço ou 'T' como separador).
    head = re.split(r"[ T]", s, 1)[0]
    try:
        return datetime.strptime(head, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def compara_tipado(obtido, operador, valor, comparacao, fail_loud: bool = False) -> bool:
    """Compara ``obtido <operador> valor`` honrando o tipo ``comparacao``.

    ``comparacao`` ∈ {'numero','data','texto'} ou None/''/desconhecido (delega ao
    ``compara`` legado — auto-coerção numérica/textual, retrocompatível).

      - 'numero': converte ambos p/ float; falha de conversão vira 0.0 (não quebra).
      - 'data'  : resolve ambos p/ ``date`` (date-level). ``valor`` pode ser o
                  token ``HOJE``/``hoje`` (→ hoje) ou ``YYYY-MM-DD``. Qualquer lado
                  não parseável → log + False (não levanta).
      - 'texto' : compara como string (str de ambos).

    Por padrão NUNCA levanta por erro de parse — só ``operador`` inválido (via
    _aplica/compara), checado antes. Erro inesperado → log + False.

    ``fail_loud=True`` (condição com ``on_error='falhar'``): valor que não pode
    ser resolvido para o tipo declarado LEVANTA ValueError em vez de degradar —
    a decisão falha alto no Airflow, em vez de rotear o ramo errado em silêncio."""
    comp = str(comparacao or "").strip().lower()
    if comp not in _COMPARACOES:
        return compara(obtido, operador, valor)
    operador = str(operador or "").strip()
    if operador not in _OPERADORES:
        raise ValueError(f"operador inválido: {operador!r}")
    try:
        if comp == "numero":
            a = _coerce_num(obtido)
            b = _coerce_num(valor)
            if fail_loud and (a is None or b is None):
                raise ValueError(
                    f"comparação 'numero' não resolveu valor "
                    f"(obtido={obtido!r}, valor={valor!r}) — on_error=falhar")
            a = 0.0 if a is None else a
            b = 0.0 if b is None else b
            return _aplica_operador(a, b, operador)
        if comp == "data":
            a = _to_date(obtido)
            b = _to_date(valor)
            if a is None or b is None:
                if fail_loud:
                    raise ValueError(
                        f"comparação 'data' não resolveu data "
                        f"(obtido={obtido!r}, valor={valor!r}) — on_error=falhar")
                print(f"[CONDICAO data] não foi possível resolver data "
                      f"(obtido={obtido!r}→{a!r}, valor={valor!r}→{b!r}) — resultado False.")
                return False
            return _aplica_operador(a, b, operador)
        # 'texto'
        a = "" if obtido is None else str(obtido)
        b = "" if valor is None else str(valor)
        return _aplica_operador(a, b, operador)
    except ValueError:
        raise
    except Exception as exc:  # noqa: BLE001 — degrada sem derrubar a DAG
        if fail_loud:
            raise ValueError(
                f"erro ao comparar (obtido={obtido!r}, valor={valor!r}, "
                f"op={operador!r}): {exc} — on_error=falhar") from exc
        print(f"[CONDICAO {comp}] erro ao comparar "
              f"(obtido={obtido!r}, valor={valor!r}, op={operador!r}): {exc} — resultado False.")
        return False


def eval_condition(cond: dict, default_conn_id: str, execution_id: str | None = None,
                   pipeline_name: str | None = None, ti=None):
    """Avalia a condição do nó de decisão.

    Retorna ``(resultado: bool, valor_obtido)``.
    ``cond`` = {tipo, operador, valor, [tabela, database] | [sql] |
                [job_name (linhas_job)] | [source_job (valor_sql)], [mssql_conn_id]}.

    ``execution_id`` identifica a execução ATUAL (ts_nodash da DAG run). É
    obrigatório apenas para ``tipo='linhas_job'`` (lê o rows_out do job a
    montante na MESMA execução em dbo.etl_ds_job_log). Os outros tipos o ignoram.

    Para ``tipo='linhas_job'`` com ``child_job`` preenchido, a decisão usa as
    linhas daquele job FILHO (dentro do SEQUENCE ``job_name``), lidas do JSON
    ``child_jobs`` do registro de etl_ds_job_log; vazio = total (rows_out).

    ``ti`` (TaskInstance) é necessário apenas para ``tipo='valor_sql'``: a decisão
    lê o XCom publicado pelo nó SQL a montante (``source_job``) e compara — não
    roda SQL próprio. Os demais tipos ignoram ``ti``. Sem ``ti`` ou sem valor no
    XCom → log + ``obtido=None`` (degrada para False na comparação tipada).

    ``cond['on_error']='falhar'`` (default carimbado pela API nos fluxos salvos a
    partir de agora): qualquer degradação silenciosa acima vira ValueError — a
    decisão FALHA no Airflow (fail-fast + card no Teams) em vez de rotear o ramo
    'não' com um erro escondido no log. Ausente/'ramo_falso' = comportamento
    legado (fluxos antigos não mudam até serem re-salvos e republicados).
    """
    from airflow.providers.microsoft.mssql.hooks.mssql import MsSqlHook  # lazy

    cond = cond or {}
    tipo = str(cond.get("tipo") or "").strip().lower()
    operador = cond.get("operador") or ">"
    limite = cond.get("valor")
    fail_loud = str(cond.get("on_error") or "").strip().lower() == "falhar"

    # valor_sql: NÃO roda SQL — lê o XCom do nó SQL a montante (source_job) e
    # compara via compara_tipado. Resolvido ANTES de abrir hook/conexão (não
    # precisa de banco).
    if tipo == "valor_sql":
        source_job = str(cond.get("source_job") or "").strip()
        obtido = None
        if not source_job:
            if fail_loud:
                raise ValueError("[CONDICAO valor_sql] source_job vazio — on_error=falhar")
            print("[CONDICAO valor_sql] source_job vazio — valor tratado como None (resultado False).")
        elif ti is None:
            if fail_loud:
                raise ValueError(
                    f"[CONDICAO valor_sql] sem TaskInstance para ler o XCom de "
                    f"'{source_job}' — on_error=falhar")
            print(f"[CONDICAO valor_sql] sem TaskInstance (ti) para ler o XCom de "
                  f"'{source_job}' — valor tratado como None (resultado False).")
        else:
            try:
                obtido = ti.xcom_pull(task_ids=source_job)
            except Exception as exc:  # noqa: BLE001 — degrada sem derrubar a DAG
                if fail_loud:
                    raise ValueError(
                        f"[CONDICAO valor_sql] xcom_pull de '{source_job}' falhou: "
                        f"{exc} — on_error=falhar") from exc
                print(f"[CONDICAO valor_sql] xcom_pull de '{source_job}' falhou ({exc}) — valor None.")
                obtido = None
            if obtido is None:
                if fail_loud:
                    raise ValueError(
                        f"[CONDICAO valor_sql] sem valor no XCom de '{source_job}' "
                        f"(nó SQL falhou/publicou NULL) — on_error=falhar")
                print(f"[CONDICAO valor_sql] sem valor no XCom de '{source_job}' "
                      f"— valor tratado como None (resultado False).")
        return compara_tipado(obtido, operador, limite, cond.get("comparacao"), fail_loud), obtido

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
        child_job = (cond.get("child_job") or "").strip()
        if child_job:
            obtido = _rows_do_filho(
                hook, cond.get("job_name") or "", child_job, execution_id, pipeline_name,
                fail_loud=fail_loud)
        else:
            obtido = _rows_out_do_job(hook, cond.get("job_name") or "", execution_id,
                                      pipeline_name, fail_loud=fail_loud)
    else:
        raise ValueError(f"tipo de condição desconhecido: {tipo!r}")

    # query/contagem: comparação tipada quando 'comparacao' vier no contrato
    # (ausente = compara legado, retrocompatível). linhas_job é sempre numérico
    # (rows_out) → usa o compara legado.
    if tipo in ("query", "contagem"):
        return compara_tipado(obtido, operador, limite, cond.get("comparacao"), fail_loud), obtido
    return compara(obtido, operador, limite), obtido


def _ds_log_first(hook, col, job_name, execution_id, pipeline_name):
    """SELECT TOP 1 <col> de dbo.etl_ds_job_log para ``job_name`` na execução
    atual, ESCOPADO por pipeline quando disponível — o execution_id (ts_nodash)
    pode colidir entre pipelines do mesmo horário, então sem o pipeline a leitura
    poderia pegar o registro de OUTRO pipeline. Sem execution_id: melhor esforço
    pelo registro mais recente do job. ``col`` é literal fixo (rows_out/child_jobs)."""
    conds, params = [], []
    if execution_id:
        conds.append("execution_id=%s"); params.append(execution_id)
        if pipeline_name:
            conds.append("pipeline_name=%s"); params.append(pipeline_name)
    conds.append("job_name=%s"); params.append(job_name)
    return hook.get_first(
        f"SELECT TOP 1 {col} FROM dbo.etl_ds_job_log WHERE "
        + " AND ".join(conds)
        + " ORDER BY COALESCE(updated_at, last_polled_at) DESC",
        parameters=tuple(params),
    )


def _linhas_degrade(msg: str, fail_loud: bool) -> int:
    """Degradação padrão da decisão por linhas: log + 0. Com ``on_error='falhar'``
    (fail_loud), LEVANTA em vez de degradar — a decisão falha alto no Airflow."""
    if fail_loud:
        raise ValueError(f"[CONDICAO linhas_job] {msg} — on_error=falhar")
    print(f"[CONDICAO linhas_job] {msg} — tratando como 0.")
    return 0


def _rows_out_do_job(hook, job_name: str, execution_id: str | None,
                     pipeline_name: str | None = None, fail_loud: bool = False) -> int:
    """Lê o rows_out mais recente de dbo.etl_ds_job_log para ``job_name`` na
    execução ATUAL (``execution_id``). Sem registro / rows_out NULL → 0 (logado).

    Degrada graciosamente: se a tabela/coluna não existir (migration 049 ainda
    não aplicada) ou a leitura falhar, retorna 0 sem quebrar a avaliação.
    ``fail_loud=True`` → cada degradação vira ValueError (ver _linhas_degrade)."""
    job_name = (job_name or "").strip()
    pipeline_name = (pipeline_name or "").strip()
    if not job_name:
        return _linhas_degrade("job_name vazio", fail_loud)
    if not execution_id:
        print("[CONDICAO linhas_job] sem execution_id — usando o registro mais recente do job.")
    try:
        row = _ds_log_first(hook, "rows_out", job_name, execution_id, pipeline_name)
    except Exception as exc:
        return _linhas_degrade(f"leitura de etl_ds_job_log falhou ({exc})", fail_loud)
    if not row or row[0] is None:
        return _linhas_degrade(
            f"sem rows_out para job '{job_name}' (execution_id={execution_id!r})", fail_loud)
    try:
        return int(row[0])
    except (TypeError, ValueError):
        return _linhas_degrade(f"rows_out não numérico ({row[0]!r})", fail_loud)


def _rows_do_filho(hook, job_name: str, child_job: str, execution_id: str | None,
                   pipeline_name: str | None = None, fail_loud: bool = False) -> int:
    """Lê as linhas de SAÍDA de um job FILHO (``child_job``) dentro do SEQUENCE
    ``job_name``, na execução ATUAL. Faz parse do JSON ``child_jobs`` gravado em
    dbo.etl_ds_job_log pelo operador e usa o campo ``rows`` da entrada cujo
    ``name == child_job``.

    Degrada graciosamente (mesmo espírito de ``_rows_out_do_job``): sem registro,
    JSON ausente/ inválido, filho não encontrado, ``rows`` None, ou tabela/coluna
    inexistente → 0 (logado). Mantém o fallback de ``execution_id`` ausente.
    ``fail_loud=True`` → cada degradação vira ValueError (ver _linhas_degrade)."""
    import json as _json

    job_name = (job_name or "").strip()
    child_job = (child_job or "").strip()
    pipeline_name = (pipeline_name or "").strip()
    if not job_name:
        return _linhas_degrade("job_name vazio (filho)", fail_loud)
    if not child_job:
        return _linhas_degrade("child_job vazio", fail_loud)
    if not execution_id:
        print("[CONDICAO linhas_job] sem execution_id — usando o registro mais recente do job (filho).")
    try:
        row = _ds_log_first(hook, "child_jobs", job_name, execution_id, pipeline_name)
    except Exception as exc:
        return _linhas_degrade(f"leitura de child_jobs falhou ({exc})", fail_loud)
    if not row or not row[0]:
        return _linhas_degrade(
            f"sem child_jobs para job '{job_name}' (execution_id={execution_id!r}, "
            f"filho '{child_job}')", fail_loud)
    try:
        children = _json.loads(row[0])
    except (ValueError, TypeError) as exc:
        return _linhas_degrade(f"child_jobs JSON inválido ({exc})", fail_loud)
    if not isinstance(children, list):
        return _linhas_degrade("child_jobs não é lista", fail_loud)
    for cj in children:
        if isinstance(cj, dict) and str(cj.get("name") or "").strip() == child_job:
            rows = cj.get("rows")
            if rows is None:
                return _linhas_degrade(
                    f"filho '{child_job}' sem 'rows' (job '{job_name}')", fail_loud)
            try:
                return int(rows)
            except (TypeError, ValueError):
                return _linhas_degrade(
                    f"rows do filho '{child_job}' não numérico ({rows!r})", fail_loud)
    return _linhas_degrade(
        f"filho '{child_job}' não encontrado em child_jobs do job '{job_name}'", fail_loud)
