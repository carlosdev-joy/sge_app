"""dags/utils/bulk_copy.py — motor compartilhado do módulo Cópia de Dados.

Helpers usados pelas DAGs etl_copy_exec e etl_copy_introspect para copiar
tabelas entre servidores SQL Server com alta performance:

  - resolve_engine()         → melhor engine de escrita STREAMING disponível,
                               nesta ordem:
                               pymssql Connection.bulk_copy (TDS bulk load)
                               → pyodbc + fast_executemany (se driver ODBC presente)
                               → pymssql executemany (último recurso, com warning);
  - ENGINE_SERVER_SIDE       → engine "server_side_insert": quando origem e
                               destino resolvem para o MESMO servidor, a cópia
                               NÃO trafega pelo worker — vira INSERT...SELECT
                               cross-database DENTRO do próprio SQL Server
                               (a DAG etl_copy_exec detecta e decide);
  - montar_insert_select(...) → instrução INSERT...SELECT do engine
                               server-side (função PURA, testável);
  - faixas_hex(...)          → fronteiras lexicográficas de partição TEXTO
                               hexadecimal (ex.: PK CHAR(32) de hash MD5) por
                               prefixo hex de 2 caracteres (função PURA,
                               testável) — usada pela etl_copy_exec quando
                               MIN/MAX da coluna de partição são strings hex;
  - open_src_conn(...)       → conexão pymssql de LEITURA/controle (autocommit);
  - open_dst_conn(...)       → conexão de ESCRITA (pymssql ou pyodbc conforme engine);
  - prepare_bulk_target(...) → resolve o ALVO de escrita UMA vez por execução:
                               no pymssql bulk_copy (mapeamento POSICIONAL),
                               resolve os ordinais físicos (column_ids) das
                               colunas de destino via sys.columns e valida que
                               todas existem; sem suporte a column_ids, cai
                               para engine por NOME se a ordem física divergir;
  - bulk_write(...)          → grava UM lote de linhas no destino;
  - script_create_table(...) → DDL do destino a partir de sys.columns/sys.types
                               da ORIGEM (heap, sem IDENTITY, nullability preservada);
  - script_create_table_from_query(...) → DDL do destino a partir do result set
                               de uma query livre (sp_describe_first_result_set
                               na origem — MODO QUERY da Cópia de Dados).

Credenciais SEMPRE via Airflow Connection — o chamador resolve com
``BaseHook.get_connection(conn_id)`` e passa o objeto Connection pronto.
Este módulo NUNCA loga senha (somente host/porta/banco/usuário).
"""
from __future__ import annotations

import inspect
import logging
from datetime import date, datetime

import pymssql

log = logging.getLogger(__name__)

# Engines de escrita (valor gravado em dbo.etl_copy_exec.engine)
ENGINE_BULK_COPY   = "pymssql_bulk_copy"
ENGINE_PYODBC_FAST = "pyodbc_fast_executemany"
ENGINE_EXECUTEMANY = "pymssql_executemany"
# Origem e destino no MESMO servidor: INSERT...SELECT dentro do SQL Server
# (cross-database, sem linked server) — nada trafega pelo worker.
ENGINE_SERVER_SIDE = "server_side_insert"

# Tipos numéricos da origem que viram VARCHAR(n) quando a coluna recebe
# transformação pad_fixo/pad_condicional (zeros à esquerda produzem texto).
_TIPOS_NUMERICOS = {
    "int", "bigint", "smallint", "tinyint", "decimal", "numeric",
    "money", "smallmoney", "float", "real", "bit",
}


def quote_ident(nome) -> str:
    """Identificador T-SQL SEMPRE entre [colchetes], com escape ``]`` → ``]]``."""
    return "[" + str(nome).replace("]", "]]") + "]"


def montar_insert_select(dst_db, dst_schema, dst_table, dst_columns,
                         select_sql, where_faixa=None) -> str:
    """Instrução do engine server-side (``ENGINE_SERVER_SIDE``): o
    ``INSERT INTO ... SELECT ...`` roda DENTRO do SQL Server (cross-database,
    sem linked server) — nada trafega pelo worker.

      - destino SEMPRE em 3 partes ``[db].[schema].[tabela]`` (a conexão fica
        no database de ORIGEM, para o ``select_sql`` — modo tabela E modo
        query — funcionar sem requalificação);
      - ``WITH (TABLOCK)`` para habilitar carga com minimal logging;
      - lista de colunas EXPLÍCITA = ``dst_columns`` (ordem do SELECT
        compilado) — nunca INSERT sem lista de colunas;
      - ``where_faixa`` (opcional) restringe à faixa de partição; o CHAMADOR
        monta a condição (mesma lógica do streaming) e cuida do escape
        ``%`` → ``%%`` do ``select_sql`` quando a instrução for parametrizada
        no pymssql.

    Função PURA (sem I/O) — identificadores via ``quote_ident``.
    """
    if not dst_columns:
        raise ValueError(
            "montar_insert_select exige a lista de colunas de destino "
            "(dst_columns vazio)")
    fqn = (f"{quote_ident(dst_db)}.{quote_ident(dst_schema)}."
           f"{quote_ident(dst_table)}")
    cols = ", ".join(quote_ident(c) for c in dst_columns)
    sql = (f"INSERT INTO {fqn} WITH (TABLOCK) ({cols}) "
           f"SELECT * FROM ({select_sql}) AS src")
    if where_faixa:
        sql += f" WHERE {where_faixa}"
    return sql


def faixas_hex(vmin, vmax, streams):
    """Fronteiras de partição TEXTO hexadecimal (modo HEX da etl_copy_exec).

    Divide o intervalo lexicográfico ``[vmin, vmax]`` (strings que casam com
    ``^[0-9A-Fa-f]+$`` — ex.: PK ``CHAR(32)`` de hash MD5) em até ``streams``
    faixas por prefixo hexadecimal de **2 caracteres**, no espaço de buckets
    entre o prefixo de MIN e o de MAX. Retorna ``[(ini, fim, ultima), ...]``:

      - faixas SEMIABERTAS ``[ini, fim)`` — a ÚLTIMA fechada ``[ini, fim]``
        (mesma convenção das faixas numéricas/data);
      - a comparação é LEXICOGRÁFICA (``col >= 'ini' AND col < 'fim'``) —
        vira range seek em índice/PK da coluna (sargável);
      - ``ini`` da primeira faixa = prefixo de 2 chars do PRÓPRIO ``vmin``
        (caixa do dado real; prefixo <= vmin lexicograficamente, cobre o MIN);
        ``fim`` da última = ``vmax`` REAL (fechada — cobre o MAX inteiro);
      - fronteiras intermediárias são sintéticas, geradas na caixa
        PREDOMINANTE entre as letras de MIN/MAX (empate ou sem letras →
        minúscula). Sob collation case-insensitive — o padrão do SQL Server —
        a caixa das fronteiras é indiferente; dados de caixa MISTA sob
        collation case-sensitive não são suportados (assumimos CI, o comum);
      - ``streams`` maior que o nº de buckets do intervalo → fronteiras
        deduplicadas (menos faixas); ``streams <= 1`` ou ``vmin == vmax`` →
        faixa única fechada ``[(vmin, vmax, True)]``.

    Todas as fronteiras cabem em NVARCHAR(100) quando os valores da coluna
    cabem (prefixos têm 2 chars; extremos são os valores reais).
    Função PURA (sem I/O) — o chamador detecta se MIN/MAX são hex e passa os
    valores já sem espaços à direita (padding de CHAR).
    """
    vmin = (vmin or "").strip()
    vmax = (vmax or "").strip()
    if not vmin or not vmax:
        raise ValueError("faixas_hex exige vmin e vmax não vazios")
    streams = max(1, int(streams or 1))
    if streams == 1 or vmin == vmax:
        return [(vmin, vmax, True)]

    def _bucket(s):
        # Bucket (piso) do prefixo hex de 2 chars que CONTÉM a string ``s``:
        # com 2+ chars é o próprio prefixo; com 1 char ('a') a string fica
        # ANTES de 'a0' e depois de '9f' → bucket 0x9f (clamp em 0).
        s = s.lower()
        if len(s) >= 2:
            return int(s[:2], 16)
        return max(0, int(s, 16) * 16 - 1)

    p_min, p_max = _bucket(vmin), _bucket(vmax)
    if p_max <= p_min:
        # mesmo prefixo de 2 chars (ou entrada fora de ordem) → faixa única
        return [(vmin, vmax, True)]

    letras = [ch for ch in (vmin + vmax) if ch.isalpha()]
    maiusculas = sum(1 for ch in letras if ch.isupper())
    caixa_alta = maiusculas > (len(letras) - maiusculas)

    def _hex2(b):
        h = format(b, "02x")
        return h.upper() if caixa_alta else h

    span = p_max - p_min + 1
    internos = sorted({p_min + (span * i) // streams
                       for i in range(1, streams)})
    internos = [b for b in internos if p_min < b <= p_max]

    inis = [vmin[:2]] + [_hex2(b) for b in internos]
    faixas = []
    for i, ini in enumerate(inis):
        ultima = i == len(inis) - 1
        fim = vmax if ultima else inis[i + 1]
        faixas.append((ini, fim, ultima))
    return faixas


def _conn_params(airflow_conn):
    """host/port/login/senha de uma Airflow Connection (porta default 1433).
    A senha NUNCA deve ser logada pelo chamador."""
    host = airflow_conn.host
    port = int(airflow_conn.port or 1433)
    return host, port, airflow_conn.login, airflow_conn.password


def _melhor_driver_odbc():
    """Melhor 'ODBC Driver N for SQL Server' instalado (None se nenhum)."""
    try:
        import pyodbc
    except Exception:
        return None
    try:
        drivers = [d for d in pyodbc.drivers() if "ODBC Driver" in d]
    except Exception:
        return None
    # Ordem lexicográfica funciona para 'ODBC Driver 11/13/17/18 for SQL Server'
    return sorted(drivers)[-1] if drivers else None


def resolve_engine() -> str:
    """Detecta o melhor engine de escrita disponível no worker.

    1. pymssql Connection.bulk_copy (pymssql>=2.2 — protocolo TDS bulk load);
    2. pyodbc + fast_executemany (só se houver algum 'ODBC Driver' instalado);
    3. pymssql executemany (último recurso — INSERT linha a linha, lento).
    """
    conn_cls = getattr(pymssql, "Connection", None)
    if conn_cls is not None and callable(getattr(conn_cls, "bulk_copy", None)):
        log.info("[COPY] Engine de escrita: %s", ENGINE_BULK_COPY)
        return ENGINE_BULK_COPY
    try:
        import pyodbc  # provider pode não trazer — import guardado
        if any("ODBC Driver" in d for d in pyodbc.drivers()):
            log.info("[COPY] Engine de escrita: %s", ENGINE_PYODBC_FAST)
            return ENGINE_PYODBC_FAST
    except Exception:
        pass
    log.warning(
        "[COPY] Nenhum engine bulk disponível (pymssql sem bulk_copy e sem "
        "driver ODBC) — usando %s (INSERT executemany, MUITO mais lento). "
        "Considere atualizar o pymssql para >= 2.2.", ENGINE_EXECUTEMANY,
    )
    return ENGINE_EXECUTEMANY


def charset_da_conexao(airflow_conn):
    """Charset configurado no extra JSON da Airflow Connection (chave
    ``charset``, ex.: ``{"charset": "CP1252"}``) — override manual por
    servidor. None quando não configurado."""
    try:
        return (airflow_conn.extra_dejson or {}).get("charset") or None
    except Exception:
        return None


def open_src_conn(airflow_conn, database, query_timeout=0):
    """Conexão pymssql de LEITURA/controle (autocommit=True).

    Usada para: streaming de leitura na origem (cursor + fetchmany, sem manter
    transação aberta), COUNT/MIN/MAX, DDL/TRUNCATE no destino (conexão de
    controle da DAG de execução) e o INSERT...SELECT do engine server-side.

    ``query_timeout`` → parâmetro ``timeout`` do pymssql (segundos por
    instrução). O default do pymssql já é 0 (SEM limite) — explicitamos para
    garantir que instruções longas (ex.: INSERT...SELECT server-side de
    dezenas de minutos) nunca sejam mortas por timeout de query.
    """
    host, port, login, password = _conn_params(airflow_conn)
    charset = charset_da_conexao(airflow_conn) or "UTF-8"
    log.info("[COPY] Conectando (leitura/controle) em %s:%s/%s como %s (charset %s)",
             host, port, database, login, charset)
    return pymssql.connect(
        server=host, port=str(port), user=login, password=password,
        database=database, autocommit=True, login_timeout=30,
        timeout=int(query_timeout or 0),
        charset=charset, appname="orquestra-copia-dados",
    )


def open_dst_conn(airflow_conn, database, engine=ENGINE_EXECUTEMANY, charset=None):
    """Conexão de ESCRITA no destino (autocommit=False; commit por lote é
    responsabilidade do bulk_write). pyodbc quando engine=fast_executemany;
    pymssql nos demais casos.

    ``charset`` importa no caminho BCP: os bytes de texto entram CRUS na
    coluna — o charset do cliente precisa casar com o codepage das colunas
    char/varchar do destino (resolvido por prepare_bulk_target e propagado
    em ``target['charset']``). Precedência: parâmetro > extra da connection
    > UTF-8."""
    host, port, login, password = _conn_params(airflow_conn)
    charset = charset or charset_da_conexao(airflow_conn) or "UTF-8"
    log.info("[COPY] Conectando (escrita/%s) em %s:%s/%s como %s (charset %s)",
             engine, host, port, database, login, charset)
    if engine == ENGINE_PYODBC_FAST:
        import pyodbc
        driver = _melhor_driver_odbc()
        if not driver:
            raise RuntimeError(
                "Engine pyodbc_fast_executemany selecionado, mas nenhum "
                "'ODBC Driver' está disponível no worker")
        conn_str = (
            f"DRIVER={{{driver}}};SERVER={host},{port};DATABASE={database};"
            f"UID={login};PWD={password};TrustServerCertificate=yes"
        )
        return pyodbc.connect(conn_str, timeout=30, autocommit=False)
    return pymssql.connect(
        server=host, port=str(port), user=login, password=password,
        database=database, autocommit=False, login_timeout=30,
        charset=charset, appname="orquestra-copia-dados",
    )


def _bulk_copy_params(conn):
    """Parâmetros da assinatura do ``bulk_copy`` instalado (None quando a
    assinatura não é introspectável — extensão C sem metadados)."""
    try:
        return inspect.signature(conn.bulk_copy).parameters
    except (TypeError, ValueError):
        return None


def _bulk_copy_kwargs(conn, batch_size) -> dict:
    """kwargs suportados pelo ``bulk_copy`` da versão instalada do pymssql.

    Os parâmetros variam entre versões — inspecionamos a assinatura e usamos
    apenas o que existir (``tablock=True`` somente se o parâmetro estiver
    disponível). Sem assinatura introspectável (extensão C), tentamos só
    ``batch_size`` — o chamador ainda tem fallback posicional em TypeError.
    """
    params = _bulk_copy_params(conn)
    if params is None:
        return {"batch_size": batch_size}
    kwargs = {}
    if "batch_size" in params:
        kwargs["batch_size"] = batch_size
    if "tablock" in params:
        kwargs["tablock"] = True
    return kwargs


def _colunas_fisicas_destino(dst_conn, dst_schema, dst_table):
    """``[(name, ordinal_bcp), ...]`` das colunas FÍSICAS da tabela de destino,
    em ordem física. ``ordinal_bcp`` é o ordinal DENSO 1..N (ROW_NUMBER sobre
    column_id), que é o que o protocolo BCP espera no bind — ``column_id`` cru
    tem buracos após ALTER TABLE DROP COLUMN e desalinharia o mapeamento.
    Lista vazia = tabela inexistente. ``dst_conn`` deve ser pymssql (%s)."""
    fqn = f"{quote_ident(dst_schema)}.{quote_ident(dst_table)}"
    cur = dst_conn.cursor()
    try:
        cur.execute(
            "SELECT name, ROW_NUMBER() OVER (ORDER BY column_id) AS ordinal_bcp "
            "FROM sys.columns WHERE object_id = OBJECT_ID(%s) ORDER BY column_id",
            (fqn,),
        )
        return [(row[0], int(row[1])) for row in cur.fetchall()]
    finally:
        cur.close()


def _codepage_destino(dst_conn, dst_schema, dst_table, dst_columns):
    """Codepage (nome iconv, ex. ``CP1252``) das colunas char/varchar/text
    COPIADAS no destino, via COLLATIONPROPERTY. None = manter UTF-8 (sem
    colunas char na cópia, collation UTF-8/65001, ou codepages mistos).

    Motivo: no BCP os bytes de texto entram crus na coluna — sem casar o
    charset do cliente com o codepage do destino, acentuação vira mojibake
    ("ç" → "Ã§"). NVARCHAR não depende disso (convertido para UCS-2)."""
    fqn = f"{quote_ident(dst_schema)}.{quote_ident(dst_table)}"
    cur = dst_conn.cursor()
    try:
        cur.execute(
            "SELECT c.name, CONVERT(INT, COLLATIONPROPERTY(c.collation_name, 'CodePage')) "
            "FROM sys.columns c JOIN sys.types t ON t.user_type_id = c.user_type_id "
            "WHERE c.object_id = OBJECT_ID(%s) "
            "AND t.name IN ('char', 'varchar', 'text') "
            "AND c.collation_name IS NOT NULL",
            (fqn,),
        )
        copiadas = {str(c).lower() for c in dst_columns}
        codepages = {int(cp) for nome, cp in cur.fetchall()
                     if cp and str(nome).lower() in copiadas}
    finally:
        cur.close()
    codepages.discard(65001)  # collation UTF-8 nativa: cliente UTF-8 já casa
    if len(codepages) == 1:
        return f"CP{codepages.pop()}"
    if len(codepages) > 1:
        log.warning("[COPY] Codepages mistos nas colunas de destino (%s) — "
                    "mantendo UTF-8; se houver mojibake, configure "
                    "{\"charset\": ...} no extra da connection", sorted(codepages))
    return None


def prepare_bulk_target(dst_conn, dst_schema, dst_table, dst_columns, engine,
                        charset_override=None) -> dict:
    """Resolve o ALVO de escrita UMA vez por execução (nunca por lote).

    Retorna o contexto consumido por ``bulk_write``::

        {"engine", "table_fqn", "columns", "column_ids", "motivo_fallback"}

    O pymssql ``bulk_copy`` mapeia os valores POSICIONALMENTE contra as
    colunas físicas 1..N do destino quando ``column_ids=None`` — destino com
    ordem física diferente, coluna extra (IDENTITY/auditoria) ou cópia de
    subconjunto embaralharia dados SILENCIOSAMENTE. Por isso, para
    ENGINE_BULK_COPY:

      - resolve os ordinais BCP densos (ROW_NUMBER sobre column_id) das
        colunas de destino em sys.columns do banco de DESTINO e valida que
        TODAS as colunas de ``dst_columns`` existem (faltante → ValueError);
      - se a assinatura do ``bulk_copy`` aceitar ``column_ids`` → monta a
        lista na ordem EXATA de ``dst_columns`` e passa adiante;
      - senão, só mantém o bulk_copy se as colunas físicas 1..N coincidirem
        EXATAMENTE com ``dst_columns`` (mesma ordem, sem colunas extras);
        caso contrário cai para engine por NOME (pyodbc fast_executemany se
        houver driver ODBC, senão executemany), logando o motivo.

    ``dst_conn`` deve ser uma conexão pymssql no banco de DESTINO (a conexão
    de controle da DAG serve). Os demais engines inserem por NOME e não
    precisam de introspecção.
    """
    table_fqn = f"{quote_ident(dst_schema)}.{quote_ident(dst_table)}"
    target = {"engine": engine, "table_fqn": table_fqn,
              "columns": list(dst_columns), "column_ids": None,
              "charset": charset_override, "motivo_fallback": None}
    if engine != ENGINE_BULK_COPY:
        return target

    duplicadas = {c for c in dst_columns
                  if [str(x).lower() for x in dst_columns].count(str(c).lower()) > 1}
    if duplicadas:
        raise ValueError(
            "Coluna(s) de destino duplicada(s) no mapeamento: "
            f"{', '.join(sorted(str(d) for d in duplicadas))} — o bulk por "
            "ordinal sobrescreveria um dos valores silenciosamente")

    fisicas = _colunas_fisicas_destino(dst_conn, dst_schema, dst_table)
    if not fisicas:
        raise ValueError(
            f"Tabela de destino {table_fqn} não encontrada ao resolver as "
            "colunas do bulk_copy")

    # Match exato primeiro; case-insensitive só quando não ambíguo (collation
    # CI é o comum no SQL Server).
    por_nome = {nome: cid for nome, cid in fisicas}
    por_nome_ci = {}
    for nome, cid in fisicas:
        por_nome_ci.setdefault(nome.lower(), []).append(cid)

    ordinais, faltantes = [], []
    for col in dst_columns:
        cid = por_nome.get(col)
        if cid is None:
            candidatos = por_nome_ci.get(str(col).lower()) or []
            cid = candidatos[0] if len(candidatos) == 1 else None
        if cid is None:
            faltantes.append(str(col))
        else:
            ordinais.append(cid)
    if faltantes:
        raise ValueError(
            f"Coluna(s) de destino inexistente(s) em {table_fqn}: "
            f"{', '.join(faltantes)} — ajuste o mapeamento ou a tabela de destino")

    if not target["charset"]:
        target["charset"] = _codepage_destino(
            dst_conn, dst_schema, dst_table, dst_columns)
        if target["charset"]:
            log.info("[COPY] Charset da carga bulk ajustado ao codepage do "
                     "destino: %s", target["charset"])

    params = _bulk_copy_params(dst_conn)
    if params is not None and "column_ids" in params:
        target["column_ids"] = ordinais
        log.info("[COPY] bulk_copy em %s com column_ids=%s (ordem de dst_columns)",
                 table_fqn, ordinais)
        return target

    # pymssql sem column_ids (ou assinatura não introspectável): o mapeamento
    # POSICIONAL só é seguro se as colunas físicas 1..N forem EXATAMENTE
    # dst_columns (mesma ordem e nenhuma coluna extra no destino).
    nomes_fisicos = [nome for nome, _ in fisicas]
    if [n.lower() for n in nomes_fisicos] == [str(c).lower() for c in dst_columns]:
        return target

    motivo = (
        "pymssql instalado não aceita column_ids no bulk_copy e a ordem "
        f"física do destino {nomes_fisicos} não coincide com as colunas da "
        f"cópia {list(dst_columns)}"
    )
    fallback = (ENGINE_PYODBC_FAST if _melhor_driver_odbc()
                else ENGINE_EXECUTEMANY)
    log.warning("[COPY] %s — usando engine por NOME: %s", motivo, fallback)
    target["engine"] = fallback
    target["motivo_fallback"] = motivo
    return target


def _dates_para_datetime(rows):
    """O bcp do pymssql rejeita ``datetime.date`` puro (colunas DATE chegam
    assim do cursor): *"value can only be a datetime.datetime"*. Converte para
    ``datetime`` à meia-noite — o servidor converte de volta para DATE na
    carga. Só copia as linhas que precisam; lote sem datas volta intacto."""
    convertidas = None
    for i, row in enumerate(rows):
        # type() exato: datetime é subclasse de date e já é aceito pelo bcp
        if any(type(v) is date for v in row):
            if convertidas is None:
                convertidas = list(rows[:i])
            convertidas.append(tuple(
                datetime(v.year, v.month, v.day) if type(v) is date else v
                for v in row))
        elif convertidas is not None:
            convertidas.append(row)
    return convertidas if convertidas is not None else rows


def bulk_write(dst_conn, target, rows, batch_size) -> int:
    """Grava UM lote de linhas no destino. Retorna o nº de linhas gravadas.

    ``target`` é o contexto resolvido por ``prepare_bulk_target`` (UMA vez por
    execução, nunca por lote): engine EFETIVO, ``table_fqn`` totalmente
    qualificado ``[schema].[tabela]`` (o database é o da conexão), ``columns``
    na MESMA ordem das tuplas de ``rows`` (= ordem do SELECT compilado /
    dst_columns_json) e, no pymssql bulk_copy, ``column_ids`` com os ordinais
    físicos correspondentes no destino.
    """
    if not rows:
        return 0

    engine    = target["engine"]
    table_fqn = target["table_fqn"]
    columns   = target["columns"]

    if engine == ENGINE_BULK_COPY:
        kwargs = _bulk_copy_kwargs(dst_conn, batch_size)
        if target.get("column_ids"):
            kwargs["column_ids"] = target["column_ids"]
        rows = _dates_para_datetime(rows)
        try:
            dst_conn.bulk_copy(table_fqn, rows, **kwargs)
        except TypeError:
            if "column_ids" in kwargs:
                # NUNCA degradar para posicional quando o mapeamento por
                # ordinal é exigido — melhor falhar claro que embaralhar dados.
                raise
            # Assinatura divergente entre versões do pymssql — forma mínima.
            # Segura aqui: prepare_bulk_target garantiu ordem física idêntica.
            dst_conn.bulk_copy(table_fqn, rows)
        except UnicodeEncodeError as e:
            charset = target.get("charset") or "UTF-8"
            raise ValueError(
                f"Texto da origem não representável no charset da carga "
                f"({charset}): {e} — configure {{\"charset\": \"...\"}} no "
                "extra da connection de destino ou use NVARCHAR no destino"
            ) from e
        dst_conn.commit()
        return len(rows)

    cols_sql = ", ".join(quote_ident(c) for c in columns)

    if engine == ENGINE_PYODBC_FAST:
        placeholders = ", ".join(["?"] * len(columns))
        sql = f"INSERT INTO {table_fqn} ({cols_sql}) VALUES ({placeholders})"
        cur = dst_conn.cursor()
        try:
            cur.fast_executemany = True
            cur.executemany(sql, [tuple(r) for r in rows])
            dst_conn.commit()
        finally:
            cur.close()
        return len(rows)

    # Último recurso: pymssql executemany (um INSERT por linha no protocolo).
    placeholders = ", ".join(["%s"] * len(columns))
    sql = f"INSERT INTO {table_fqn} ({cols_sql}) VALUES ({placeholders})"
    cur = dst_conn.cursor()
    try:
        cur.executemany(sql, [tuple(r) for r in rows])
        dst_conn.commit()
    finally:
        cur.close()
    return len(rows)


def _render_sql_type(info) -> str:
    """Renderiza o tipo T-SQL a partir do catálogo (sys.columns/sys.types)."""
    tipo       = (info["tipo"] or "").lower()
    max_length = info["max_length"]
    precision  = info["precision"]
    scale      = info["scale"]
    if tipo in ("varchar", "char", "binary", "varbinary"):
        n = "MAX" if max_length == -1 else str(max_length)
        return f"{tipo.upper()}({n})"
    if tipo in ("nvarchar", "nchar"):
        # max_length em bytes → caracteres = bytes / 2
        n = "MAX" if max_length == -1 else str(max_length // 2)
        return f"{tipo.upper()}({n})"
    if tipo in ("decimal", "numeric"):
        return f"{tipo.upper()}({precision},{scale})"
    if tipo in ("datetime2", "time", "datetimeoffset"):
        return f"{tipo.upper()}({scale})"
    return tipo.upper()


def script_create_table(src_conn, src_db, src_schema, src_table,
                        dst_columns, transforms,
                        dst_schema="dbo", dst_table=None) -> str:
    """DDL ``CREATE TABLE`` do destino a partir do catálogo da ORIGEM.

    Regras (spec Cópia de Dados):
      - tipos preservados (sys.columns/sys.types da origem);
      - colunas com pad_condicional/pad_fixo viram VARCHAR(max(tamanhos))
        quando o tipo original é numérico;
      - IDENTITY NÃO é preservada; nullability preservada;
      - SEM índices/constraints — heap (a carga bulk agradece).

    ``dst_columns``  → nomes de destino na ordem do SELECT compilado.
    ``transforms``   → lista ``colunas_json["colunas"]`` ({origem, destino, transform}).
    ``dst_table``    → nome da tabela de destino (default = src_table).
    """
    dst_table  = dst_table or src_table
    qdb        = quote_ident(src_db)
    fqn_origem = f"{qdb}.{quote_ident(src_schema)}.{quote_ident(src_table)}"

    cur = src_conn.cursor()
    try:
        cur.execute(
            f"SELECT c.name, t.name, c.max_length, c.precision, c.scale, c.is_nullable "
            f"FROM {qdb}.sys.columns c "
            f"JOIN {qdb}.sys.types t ON t.user_type_id = c.user_type_id "
            f"WHERE c.object_id = OBJECT_ID(%s) "
            f"ORDER BY c.column_id",
            (fqn_origem,),
        )
        meta = {
            row[0]: {
                "tipo": row[1], "max_length": row[2],
                "precision": row[3], "scale": row[4],
                "is_nullable": bool(row[5]),
            }
            for row in cur.fetchall()
        }
    finally:
        cur.close()

    if not meta:
        raise ValueError(f"Tabela de origem não encontrada: {fqn_origem}")

    por_destino = {}
    for col in transforms or []:
        destino = col.get("destino") or col.get("origem")
        if destino:
            por_destino[destino] = col

    defs = []
    for nome in dst_columns:
        mapa   = por_destino.get(nome) or {}
        origem = mapa.get("origem") or nome
        info   = meta.get(origem)
        if info is None:
            raise ValueError(
                f"Coluna de origem '{origem}' não existe em {fqn_origem}")

        tipo_sql  = _render_sql_type(info)
        transform = mapa.get("transform") or {}
        ttipo     = (transform.get("tipo") or "").lower()
        if ttipo in ("pad_fixo", "pad_condicional") \
                and (info["tipo"] or "").lower() in _TIPOS_NUMERICOS:
            tamanhos = []
            try:
                if transform.get("tamanho"):
                    tamanhos.append(int(transform["tamanho"]))
            except (TypeError, ValueError):
                pass
            for caso in transform.get("casos") or []:
                try:
                    tamanhos.append(int(caso.get("tamanho") or 0))
                except (TypeError, ValueError):
                    pass
            n = max((t for t in tamanhos if t > 0), default=50)
            tipo_sql = f"VARCHAR({n})"

        nulabilidade = "NULL" if info["is_nullable"] else "NOT NULL"
        defs.append(f"    {quote_ident(nome)} {tipo_sql} {nulabilidade}")

    fqn_destino = f"{quote_ident(dst_schema)}.{quote_ident(dst_table)}"
    return f"CREATE TABLE {fqn_destino} (\n" + ",\n".join(defs) + "\n)"


def script_create_table_from_query(src_conn, src_query, dst_schema, dst_table) -> str:
    """DDL ``CREATE TABLE`` do destino a partir do RESULT SET de uma query
    livre (MODO QUERY da Cópia de Dados), via ``sp_describe_first_result_set``
    na ORIGEM: cada coluna sai com name + system_type_name + is_nullable.
    Heap, sem índices/constraints e sem IDENTITY (mesmo espírito do
    ``script_create_table``).

    Erros do sp_describe (query dinâmica, tipos CLR, coluna sem nome...) →
    ValueError com mensagem clara sugerindo criar a tabela manualmente.
    ``src_conn`` deve ser pymssql (%s).
    """
    cur = src_conn.cursor()
    try:
        try:
            cur.execute("EXEC sp_describe_first_result_set @tsql = %s",
                        (src_query,))
            rows = cur.fetchall()
        except Exception as e:
            raise ValueError(
                "Não foi possível descrever o resultado da query na origem "
                f"(sp_describe_first_result_set): {e} — crie a tabela de "
                "destino manualmente e desmarque 'Criar nova tabela'.")
    finally:
        cur.close()

    # Colunas do result set do sp_describe_first_result_set (posições fixas):
    # r[0]=is_hidden, r[1]=column_ordinal, r[2]=name, r[3]=is_nullable,
    # r[4]=system_type_id, r[5]=system_type_name
    defs = []
    for r in rows:
        if r[0]:  # is_hidden
            continue
        nome, is_nullable, tipo_sql = r[2], bool(r[3]), r[5]
        if not nome:
            raise ValueError(
                f"A query tem coluna sem nome (posição {r[1]}) — dê um alias "
                "a todas as colunas (ex.: expressao AS nome_coluna).")
        if not tipo_sql:
            raise ValueError(
                f"Não foi possível resolver o tipo da coluna '{nome}' "
                "(tipo CLR/alias?) — crie a tabela de destino manualmente "
                "e desmarque 'Criar nova tabela'.")
        nulabilidade = "NULL" if is_nullable else "NOT NULL"
        defs.append(f"    {quote_ident(nome)} {tipo_sql} {nulabilidade}")

    if not defs:
        raise ValueError(
            "sp_describe_first_result_set não retornou colunas para a query "
            "— crie a tabela de destino manualmente e desmarque 'Criar nova tabela'.")

    fqn_destino = f"{quote_ident(dst_schema)}.{quote_ident(dst_table)}"
    return f"CREATE TABLE {fqn_destino} (\n" + ",\n".join(defs) + "\n)"
