"""api/services/copy_sql.py — compilador de transformações da Cópia de Dados.

Converte o mapeamento ``colunas_json`` (fonte da verdade editada no wizard)
em ``select_sql``/``count_sql`` T-SQL prontos, persistidos em
``dbo.etl_copy_job`` no MOMENTO DO SALVAMENTO. A DAG ``etl_copy_exec`` usa o
SQL compilado (não recompila) e o envolve em subquery para aplicar a faixa
de partição: ``SELECT * FROM (<select_sql>) AS src WHERE [part] >= ? AND ...``.

MODO QUERY (``src_query`` presente): a fonte é uma query SQL livre validada
por ``validate_src_query`` — transformações e filtro do wizard são ignorados
e ``select_sql`` passa a ser a própria query (a subquery da DAG continua
funcionando igual).

Segurança (anti-injeção):
  - Identificadores SEMPRE entre ``[colchetes]`` com escape ``]`` → ``]]`` e
    validados por allowlist de caracteres (rejeita fora do padrão).
  - Literais de string com aspas simples duplicadas (``'`` → ``''``).
  - Tipos de CAST validados por allowlist (regex, p/s/n numéricos).
  - Expressão livre (transform ``sql``) e ``src_filtro`` passam por validação
    read-only: sem ``;``, sem comentários (``--``, ``/*``), sem palavras-chave
    DML/DDL/EXEC — mesmo espírito de ``_validate_select_strict`` em
    api/routers/jobs.py. Nenhum valor de usuário é concatenado sem escape.

Funções puras (sem I/O) — levantam ``ValueError`` com mensagem clara em
pt-BR, que os endpoints traduzem em HTTP 422.
"""
from __future__ import annotations

import re

# Allowlist de caracteres para identificadores (colunas/schemas/tabelas/bancos).
# Colchetes, aspas e ';' ficam de fora — o escape ']' → ']]' é defesa extra.
_IDENT_RE = re.compile(r"^[A-Za-z0-9_ \-\.\$#@áéíóúãõçÁÉÍÓÚÃÕÇ]{1,128}$")

# Allowlist de tipos do transform 'cast' (p/s/n estritamente numéricos).
_CAST_TIPO_RE = re.compile(
    r"^(INT|BIGINT|DATE|DATETIME|FLOAT|BIT"
    r"|DECIMAL\(\d{1,2},\d{1,2}\)"
    r"|VARCHAR\(\d{1,4}\)"
    r"|NVARCHAR\(\d{1,4}\))$"
)

# Alias final colado pelo usuário na expressão livre ("... AS NUM_CPF_CNPJ").
# O compile_job já acrescenta "AS [destino]" — o alias vindo na expressão é
# removido para não gerar alias duplo (SQL inválido). O identificador do alias
# não admite parênteses, então "CAST(x AS VARCHAR(20))" NÃO casa (termina em ')').
_ALIAS_FINAL_RE = re.compile(
    r"\s+AS\s+(\[?[A-Za-z_][A-Za-z0-9_]*\]?)\s*$", re.IGNORECASE)

# Palavras-chave proibidas em expressão livre/filtro (mesmo conjunto do
# _COND_DML_RE de api/routers/jobs.py — read-only de verdade).
_EXPR_PROIBIDO_RE = re.compile(
    r"\b(INSERT|UPDATE|DELETE|MERGE|DROP|ALTER|CREATE|TRUNCATE|EXEC|EXECUTE|"
    r"GRANT|REVOKE|INTO)\b",
    re.IGNORECASE,
)

_EXPR_MAX_CHARS = 2000

# Tamanho máximo da query livre usada como FONTE da cópia (src_query).
_SRC_QUERY_MAX_CHARS = 20000

# Tamanho máximo do pad: o pad usa CAST(... AS VARCHAR(50)) como base, então
# um preenchimento acima de 50 seria truncado silenciosamente — rejeitamos.
_PAD_TAMANHO_MAX = 50

TIPOS_TRANSFORM = {
    "pad_condicional", "pad_fixo", "trim", "upper", "lower",
    "substring", "cast", "sql",
}


def quote_ident(nome) -> str:
    """Valida e devolve o identificador entre colchetes, com ']' escapado."""
    if not isinstance(nome, str) or not _IDENT_RE.match(nome):
        raise ValueError(f"identificador inválido: {nome!r}")
    return "[" + nome.replace("]", "]]") + "]"


def quote_literal(valor) -> str:
    """Escapa um valor como literal T-SQL (aspas simples duplicadas)."""
    if valor is None:
        raise ValueError("valor de literal não pode ser nulo")
    return "'" + str(valor).replace("'", "''") + "'"


def _int_positivo(valor, campo: str, minimo: int = 1, maximo: int = 8000) -> int:
    """Converte para int validando faixa (bool não conta como int)."""
    if isinstance(valor, bool) or not isinstance(valor, (int, str)):
        raise ValueError(f"{campo} deve ser inteiro")
    try:
        n = int(str(valor).strip())
    except (ValueError, TypeError):
        raise ValueError(f"{campo} deve ser inteiro")
    if not minimo <= n <= maximo:
        raise ValueError(f"{campo} deve estar entre {minimo} e {maximo}")
    return n


def validate_sql_expr(expr, rotulo: str = "expressão SQL") -> str:
    """Valida uma expressão T-SQL livre (transform 'sql' / src_filtro).

    Read-only: sem ';', sem comentários ('--', '/*'), sem DML/DDL/EXEC,
    tamanho máximo de 2000 chars. Devolve a expressão limpa (strip)."""
    if not expr or not isinstance(expr, str) or not expr.strip():
        raise ValueError(f"{rotulo} vazia")
    s = expr.strip()
    if len(s) > _EXPR_MAX_CHARS:
        raise ValueError(f"{rotulo} excede o tamanho máximo de {_EXPR_MAX_CHARS} caracteres")
    if ";" in s:
        raise ValueError(f"{rotulo} não pode conter ';'")
    if "--" in s or "/*" in s or "*/" in s:
        raise ValueError(f"{rotulo} não pode conter comentários ('--' ou '/*')")
    m = _EXPR_PROIBIDO_RE.search(s)
    if m:
        raise ValueError(f"{rotulo} contém comando não permitido ({m.group(1).upper()})")
    return s


def validate_src_query(q) -> str:
    """Valida a query SQL livre usada como FONTE da cópia (modo query).

    Read-only, mesma família de guarda de ``validate_sql_expr``: precisa
    começar com SELECT ou WITH (case-insensitive), sem ``;``, sem comentários
    (``--``, ``/*``), sem palavras-chave de escrita/execução (INSERT/UPDATE/
    DELETE/MERGE/DROP/ALTER/CREATE/TRUNCATE/EXEC/EXECUTE/GRANT/REVOKE/INTO),
    tamanho máximo de 20000 chars. Devolve a query limpa (strip)."""
    if not q or not isinstance(q, str) or not q.strip():
        raise ValueError("src_query vazia")
    s = q.strip()
    if len(s) > _SRC_QUERY_MAX_CHARS:
        raise ValueError(
            f"src_query excede o tamanho máximo de {_SRC_QUERY_MAX_CHARS} caracteres")
    if not re.match(r"^(SELECT|WITH)\b", s, re.IGNORECASE):
        raise ValueError("src_query deve começar com SELECT ou WITH")
    if ";" in s:
        raise ValueError("src_query não pode conter ';'")
    if "--" in s or "/*" in s or "*/" in s:
        raise ValueError("src_query não pode conter comentários ('--' ou '/*')")
    m = _EXPR_PROIBIDO_RE.search(s)
    if m:
        raise ValueError(f"src_query contém comando não permitido ({m.group(1).upper()})")
    return s


def _pad_expr(col_quoted: str, tamanho: int) -> str:
    """RIGHT(REPLICATE('0', n) + LTRIM(RTRIM(CAST([col] AS VARCHAR(50)))), n)."""
    return (f"RIGHT(REPLICATE('0', {tamanho}) + "
            f"LTRIM(RTRIM(CAST({col_quoted} AS VARCHAR(50)))), {tamanho})")


def compile_transform(origem: str, transform) -> str:
    """Compila a transformação de UMA coluna para uma expressão T-SQL.

    ``transform`` é o dict do colunas_json (ou None = coluna sem transformação).
    Levanta ValueError com mensagem clara em qualquer entrada inválida."""
    col = quote_ident(origem)
    if transform is None:
        return col
    if not isinstance(transform, dict):
        raise ValueError(f"transform da coluna '{origem}' deve ser objeto ou nulo")
    tipo = str(transform.get("tipo") or "").strip().lower()
    if tipo not in TIPOS_TRANSFORM:
        raise ValueError(
            f"transform da coluna '{origem}': tipo '{tipo}' inválido "
            f"(use {', '.join(sorted(TIPOS_TRANSFORM))})")

    if tipo == "trim":
        return f"LTRIM(RTRIM({col}))"
    if tipo == "upper":
        return f"UPPER({col})"
    if tipo == "lower":
        return f"LOWER({col})"

    if tipo == "pad_fixo":
        tamanho = _int_positivo(transform.get("tamanho"),
                                f"tamanho do pad_fixo da coluna '{origem}'",
                                1, _PAD_TAMANHO_MAX)
        return _pad_expr(col, tamanho)

    if tipo == "pad_condicional":
        campo = transform.get("campo_condicao")
        if not campo:
            raise ValueError(
                f"pad_condicional da coluna '{origem}': campo_condicao é obrigatório")
        campo_q = quote_ident(campo)
        casos = transform.get("casos")
        if not isinstance(casos, list) or not casos:
            raise ValueError(
                f"pad_condicional da coluna '{origem}': casos (lista não vazia) é obrigatório")
        partes = ["CASE"]
        for i, caso in enumerate(casos):
            if not isinstance(caso, dict) or caso.get("valor") is None:
                raise ValueError(
                    f"pad_condicional da coluna '{origem}': caso #{i + 1} sem 'valor'")
            tamanho = _int_positivo(caso.get("tamanho"),
                                    f"tamanho do caso #{i + 1} do pad_condicional "
                                    f"da coluna '{origem}'",
                                    1, _PAD_TAMANHO_MAX)
            partes.append(
                f"WHEN {campo_q} = {quote_literal(caso['valor'])} "
                f"THEN {_pad_expr(col, tamanho)}")
        partes.append(f"ELSE {col} END")
        return " ".join(partes)

    if tipo == "substring":
        inicio = _int_positivo(transform.get("inicio"),
                               f"inicio do substring da coluna '{origem}'", 1, 8000)
        tamanho = _int_positivo(transform.get("tamanho"),
                                f"tamanho do substring da coluna '{origem}'", 1, 8000)
        return f"SUBSTRING({col}, {inicio}, {tamanho})"

    if tipo == "cast":
        tipo_sql = str(transform.get("tipo_sql") or "").strip().upper()
        tipo_sql = re.sub(r"\s+", "", tipo_sql)  # normaliza 'DECIMAL(10, 2)'
        if not _CAST_TIPO_RE.match(tipo_sql):
            raise ValueError(
                f"cast da coluna '{origem}': tipo '{transform.get('tipo_sql')}' fora da "
                "allowlist (INT, BIGINT, DECIMAL(p,s), VARCHAR(n), NVARCHAR(n), "
                "DATE, DATETIME, FLOAT, BIT)")
        return f"CAST({col} AS {tipo_sql})"

    # tipo == "sql" — expressão livre validada (read-only). Alias final
    # ("... END AS NUM_CPF_CNPJ") é removido: o compile_job já põe AS [destino].
    expressao = validate_sql_expr(transform.get("expressao"),
                                  f"expressão SQL da coluna '{origem}'")
    return _ALIAS_FINAL_RE.sub("", expressao).rstrip()


def compile_job(job: dict) -> dict:
    """Compila um job de cópia para SQL pronto.

    Entrada (dict): src_database, src_schema (default 'dbo'), src_table,
    src_filtro (opcional), src_top (opcional — limite de linhas da CARGA),
    src_query (opcional — MODO QUERY) e colunas —
    lista [{origem, destino, transform}].

    Saída: {"select_sql", "count_sql", "dst_columns"} onde
      select_sql = SELECT [TOP (N) ]<expr> AS [dst], ... FROM
                   [db].[schema].[tabela] WITH (NOLOCK) [WHERE (<filtro>)]
                   (SEM ORDER BY)
      count_sql  = SELECT COUNT_BIG(*) FROM ... (mesmo FROM/WHERE; com
                   src_top, envolve um SELECT TOP (N) para o rows_total
                   refletir o limite real da carga)
      dst_columns = nomes de destino na ordem do SELECT.

    src_top (int 1..1_000_000_000): o TOP vai EMBUTIDO no select_sql
    compilado — é a query final da carga (todos os engines a envolvem em
    subquery), não um limite só de preview. Uso típico: rodar o mapeamento/
    transformações com uma amostra antes da carga completa. Sem ORDER BY, as
    N linhas não são determinísticas — adequado para teste, não para corte
    exato. No MODO QUERY é ignorado (aplique TOP na própria query).

    MODO QUERY (src_query presente): a fonte da cópia é a própria query
    (validada por ``validate_src_query``) — transformações e filtro do wizard
    NÃO se aplicam (transform de qualquer coluna deve ser nulo; src_filtro é
    ignorado). Saída:
      select_sql = a query crua validada
      count_sql  = SELECT COUNT_BIG(*) FROM (\\n<query>\\n) AS _q
      dst_columns = nomes das colunas informadas (detectadas pela UI via
                    /copias/introspect/query-columns).

    Levanta ValueError (→ 422 nos endpoints) para qualquer entrada inválida."""
    if not isinstance(job, dict):
        raise ValueError("definição da cópia inválida")

    src_database = (job.get("src_database") or "").strip()
    src_schema = (job.get("src_schema") or "dbo").strip() or "dbo"
    src_table = (job.get("src_table") or "").strip()
    src_query = (job.get("src_query") or "").strip()
    if not src_database:
        raise ValueError("src_database é obrigatório")
    if not src_table and not src_query:
        raise ValueError("src_table é obrigatório")

    colunas = job.get("colunas")
    if isinstance(colunas, dict):  # aceita o próprio colunas_json {"colunas": [...]}
        colunas = colunas.get("colunas")
    if not isinstance(colunas, list) or not colunas:
        raise ValueError("colunas (lista não vazia) é obrigatório")

    src_top = job.get("src_top")
    if src_top in (None, "", 0):
        src_top = None
    else:
        try:
            src_top = int(src_top)
        except (TypeError, ValueError):
            raise ValueError("src_top deve ser um inteiro positivo")
        if not 1 <= src_top <= 1_000_000_000:
            raise ValueError("src_top deve estar entre 1 e 1.000.000.000")

    if src_query:
        # MODO QUERY: a query é a fonte — TOP, se quiser, vai nela mesma
        return _compile_job_query(src_query, colunas)

    exprs: list[str] = []
    dst_columns: list[str] = []
    vistos: set[str] = set()
    for i, c in enumerate(colunas):
        if not isinstance(c, dict):
            raise ValueError(f"coluna #{i + 1} inválida (esperado objeto)")
        origem = (c.get("origem") or "").strip()
        if not origem:
            raise ValueError(f"coluna #{i + 1}: origem é obrigatória")
        destino = (c.get("destino") or "").strip() or origem
        destino_q = quote_ident(destino)
        chave = destino.lower()
        if chave in vistos:
            raise ValueError(f"coluna de destino duplicada: '{destino}'")
        vistos.add(chave)
        expr = compile_transform(origem, c.get("transform"))
        exprs.append(f"{expr} AS {destino_q}")
        dst_columns.append(destino)

    from_sql = (f"FROM {quote_ident(src_database)}.{quote_ident(src_schema)}."
                f"{quote_ident(src_table)} WITH (NOLOCK)")

    where_sql = ""
    filtro = (job.get("src_filtro") or "").strip()
    if filtro:
        filtro = validate_sql_expr(filtro, "src_filtro")
        where_sql = f" WHERE ({filtro})"

    top_sql = f"TOP ({src_top}) " if src_top else ""
    select_sql = "SELECT " + top_sql + ", ".join(exprs) + " " + from_sql + where_sql
    if src_top:
        # count limitado ao TOP — rows_total/ETA refletem a carga real
        count_sql = (f"SELECT COUNT_BIG(*) FROM (SELECT TOP ({src_top}) 1 AS um "
                     + from_sql + where_sql + ") AS _t")
    else:
        count_sql = "SELECT COUNT_BIG(*) " + from_sql + where_sql
    return {"select_sql": select_sql, "count_sql": count_sql, "dst_columns": dst_columns}


def _compile_job_query(src_query: str, colunas: list) -> dict:
    """Compila o MODO QUERY: select_sql = query crua validada; count_sql
    envolve a query em subquery; dst_columns = nomes das colunas informadas
    (a UI detecta via /copias/introspect/query-columns e envia com
    origem=destino=nome e transform nulo). Transform preenchido → erro."""
    src_query = validate_src_query(src_query)

    dst_columns: list[str] = []
    vistos: set[str] = set()
    for i, c in enumerate(colunas):
        if not isinstance(c, dict):
            raise ValueError(f"coluna #{i + 1} inválida (esperado objeto)")
        if c.get("transform") is not None:
            nome = (c.get("destino") or c.get("origem") or f"#{i + 1}")
            raise ValueError(
                f"coluna '{nome}': transformações não são permitidas no modo "
                "query — trate os dados na própria query (src_query)")
        destino = (c.get("destino") or c.get("origem") or "").strip()
        if not destino:
            raise ValueError(f"coluna #{i + 1}: nome da coluna é obrigatório")
        quote_ident(destino)  # valida o identificador (allowlist)
        chave = destino.lower()
        if chave in vistos:
            raise ValueError(f"coluna de destino duplicada: '{destino}'")
        vistos.add(chave)
        dst_columns.append(destino)

    count_sql = f"SELECT COUNT_BIG(*) FROM (\n{src_query}\n) AS _q"
    return {"select_sql": src_query, "count_sql": count_sql,
            "dst_columns": dst_columns}
