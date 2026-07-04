"""dags/utils/bulk_copy.py — motor compartilhado do módulo Cópia de Dados.

Helpers usados pelas DAGs etl_copy_exec e etl_copy_introspect para copiar
tabelas entre servidores SQL Server com alta performance:

  - resolve_engine()         → melhor engine de escrita STREAMING disponível,
                               nesta ordem:
                               bcp nativo (mssql-tools18, staging em disco)
                               → pymssql Connection.bulk_copy (TDS bulk load)
                               → pyodbc + fast_executemany (se driver ODBC presente)
                               → pymssql executemany (último recurso, com warning);
  - ENGINE_BCP               → engine "bcp_native": ``bcp queryout`` exporta
                               a faixa (formato NATIVO) para um ARQUIVO de
                               staging em disco e ``bcp in`` o importa —
                               NUNCA pipe/FIFO (o bcp in desalinha o stream
                               nativo em leituras não-seekáveis e perde
                               linhas em SILÊNCIO — incidente 2026-07-04);
                               helpers: preparar_bcp(),
                               probe_bcp(), copiar_faixa_bcp() e as funções
                               PURAS sql_literal(), redigir_cmd(),
                               montar_cmd_bcp_queryout/in() e
                               parse_progresso_bcp();
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
import os
import re
import shutil
import subprocess
import tempfile
from collections import deque
from datetime import date, datetime
from decimal import Decimal

import pymssql

log = logging.getLogger(__name__)

# Engines de escrita (valor gravado em dbo.etl_copy_exec.engine)
ENGINE_BCP         = "bcp_native"
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


def resolve_engine(incluir_bcp: bool = True) -> str:
    """Detecta o melhor engine de escrita disponível no worker.

    0. bcp nativo (mssql-tools18) — ``queryout`` → arquivo de staging →
       ``in``, formato NATIVO, C nas duas pontas (10–50× o streaming Python
       por stream; custo: a faixa toca disco no worker);
       ``incluir_bcp=False`` pula esta etapa — usado nos fallbacks de runtime
       (probe de conexão/TLS falhou ou mapeamento posicional inseguro);
    1. pymssql Connection.bulk_copy (pymssql>=2.2 — protocolo TDS bulk load);
    2. pyodbc + fast_executemany (só se houver algum 'ODBC Driver' instalado);
    3. pymssql executemany (último recurso — INSERT linha a linha, lento).
    """
    if incluir_bcp:
        caminho = bcp_disponivel()
        if caminho:
            log.info("[COPY] Engine de escrita: %s (%s)", ENGINE_BCP, caminho)
            return ENGINE_BCP
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


# ---------------------------------------------------------------------------
# Engine bcp_native — utilitário nativo bcp (mssql-tools18)
# ---------------------------------------------------------------------------

# Caminho padrão do bcp instalado pelo pacote mssql-tools18 (ver Dockerfiles).
_BCP_PATH_PADRAO = "/opt/mssql-tools18/bin/bcp"

# Linhas do stdout do ``bcp in`` com -b (progresso por lote e total final):
#   "50000 rows sent to SQL Server. Total sent: 150000"
#   "1234567 rows copied."
_BCP_LOTE_RE  = re.compile(
    r"^\s*(\d+)\s+rows sent to SQL Server\.\s*Total sent:\s*(\d+)")
_BCP_TOTAL_RE = re.compile(r"^\s*(\d+)\s+rows copied\b")

# Flags anunciadas no usage do bcp: tokens "[-x ..." (ex.: "[-u trust ...]").
_BCP_FLAG_RE = re.compile(r"\[\s*(-[A-Za-z])(?=[\s\]\[])")

# Caracteres de CONTROLE proibidos em literais de fronteira (sql_literal).
_CTRL_RE = re.compile(r"[\x00-\x1f\x7f]")


def bcp_disponivel():
    """Caminho do utilitário nativo ``bcp`` no worker (PATH ou o caminho
    padrão do mssql-tools18) — None quando ausente."""
    caminho = shutil.which("bcp")
    if caminho:
        return caminho
    if os.access(_BCP_PATH_PADRAO, os.X_OK):
        return _BCP_PATH_PADRAO
    return None


def bcp_flags_suportadas(usage_text) -> set:
    """Flags de linha de comando anunciadas no usage do bcp (função PURA —
    o chamador roda ``bcp`` sem argumentos e passa stdout+stderr).

    Decidimos por INSPEÇÃO do próprio binário (a doc e os binários divergem
    entre versões/SO):
      - ``-u`` (trust server certificate, bcp >= 18): os mssql-tools 18
        exigem criptografia E validação de certificado por padrão — sem
        ``-u``, servidor com certificado self-signed recusa a conexão (é o
        equivalente do TrustServerCertificate=yes do caminho pyodbc);
      - ``-h`` (load hints, ex.: TABLOCK): a doc oficial marca como
        Windows-only — só passamos se o usage do binário anunciar.
    """
    return set(_BCP_FLAG_RE.findall(usage_text or ""))


def preparar_bcp():
    """Contexto do engine bcp no worker: ``{"path", "flags"}`` — None quando
    o binário não existe. As flags saem do usage do próprio binário (rodado
    sem argumentos; exit != 0 é esperado)."""
    caminho = bcp_disponivel()
    if not caminho:
        return None
    usage = ""
    try:
        proc = subprocess.run([caminho], capture_output=True, text=True,
                              errors="replace", timeout=15)
        usage = (proc.stdout or "") + (proc.stderr or "")
    except Exception as e:
        log.warning("[COPY] bcp presente mas não foi possível ler o usage "
                    "(flags -u/-h desabilitadas): %s", e)
    return {"path": caminho, "flags": bcp_flags_suportadas(usage)}


def redigir_cmd(args):
    """Lista de argumentos com a senha REDIGIDA para log (função PURA):
    o valor após ``-P`` (ou colado, ``-Psenha``) vira ``****``. NENHUM
    comando bcp pode ser logado sem passar por aqui."""
    red, oculta = [], False
    for a in args:
        a = str(a)
        if oculta:
            red.append("****")
            oculta = False
        elif a == "-P":
            red.append(a)
            oculta = True
        elif a.startswith("-P") and len(a) > 2:
            red.append("-P****")
        else:
            red.append(a)
    return red


def _redigir_texto(texto, senhas):
    """Redige as senhas em texto livre (o stderr do bcp não ecoa a senha,
    mas redigimos por segurança antes de logar/persistir mensagens)."""
    texto = str(texto or "")
    for s in senhas:
        if s:
            texto = texto.replace(str(s), "****")
    return texto


def sql_literal(v) -> str:
    """Valor de fronteira de faixa → literal T-SQL SEGURO para inline no
    SELECT do engine bcp_native (o bcp NÃO tem parâmetros — mesmo estilo do
    ``quote_literal`` do copy_sql da API). Função PURA.

      - str  → aspas simples DUPLICADAS; prefixo ``N'...'`` apenas quando há
        caractere não-ASCII (N'' contra coluna VARCHAR pode custar a
        sargabilidade do range seek; fronteiras hex são sempre ASCII);
        caracteres de CONTROLE (< 0x20 e 0x7f) são REJEITADOS (ValueError) —
        fronteira de partição nunca deveria contê-los;
      - datetime → ISO 8601 com 'T' (independe de idioma/DATEFORMAT); fração
        reduzida a 3 dígitos quando for milissegundo exato (compatível com
        DATETIME); date → 'YYYY-MM-DD';
      - bool → 1/0; int/float/Decimal → str();
      - None → NULL (defensivo; a faixa IS NULL não usa literal);
      - outros tipos → str() entre aspas (mesma regra de controle/escape).
    """
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, (int, float, Decimal)):
        return str(v)
    if isinstance(v, datetime):
        txt = v.isoformat()
        if v.microsecond and v.microsecond % 1000 == 0:
            txt = txt[:-3]  # .123000 → .123 (aceito por DATETIME)
        return f"'{txt}'"
    if isinstance(v, date):
        return f"'{v.isoformat()}'"
    s = str(v)
    if _CTRL_RE.search(s):
        raise ValueError(
            "Fronteira de faixa contém caractere de controle — literal "
            "rejeitado por segurança no engine bcp_native")
    esc = s.replace("'", "''")
    prefixo = "N" if any(ord(ch) > 127 for ch in s) else ""
    return f"{prefixo}'{esc}'"


def montar_cmd_bcp_queryout(bcp_path, select_sql, host, port, database,
                            user, password, datafile="/dev/stdout",
                            trust_cert=True):
    """Comando (lista argv, SEM shell) do LEITOR ``bcp <query> queryout``:
    formato NATIVO (``-n``, tipos binários — o desvio de codepage do caminho
    pymssql NÃO se aplica; nunca -c/-w) e ``-k`` (keep nulls). O ``datafile``
    é o ARQUIVO de staging em disco (ou /dev/null no probe) — NUNCA um
    pipe/FIFO: o ``bcp in`` da outra ponta desalinha o formato nativo em
    leituras não-seekáveis e perde linhas em silêncio (incidente
    2026-07-04). Função PURA (não executa nada)."""
    cmd = [str(bcp_path), str(select_sql), "queryout", str(datafile),
           "-S", f"{host},{int(port or 1433)}", "-d", str(database),
           "-U", str(user), "-P", str(password or ""), "-n", "-k"]
    if trust_cert:
        cmd.append("-u")
    return cmd


def montar_cmd_bcp_in(bcp_path, dst_schema, dst_table, host, port, database,
                      user, password, batch_size, datafile,
                      trust_cert=True, tablock=False, errfile=None):
    """Comando (lista argv, SEM shell) do ESCRITOR ``bcp <tabela> in``:
    formato nativo + keep nulls, ``-b`` (lote → progresso por linha no
    stdout), ``-m 1`` (aborta com exit != 0 no PRIMEIRO erro de linha —
    ATENÇÃO: ``-m 0`` significa erros ILIMITADOS tolerados com exit 0, NÃO
    "para no primeiro erro"; comprovado empiricamente no 18.6.2.1, parte do
    incidente 2026-07-04) e, quando o binário suportar, ``-h TABLOCK``
    (minimal logging). O ``datafile`` é o MESMO arquivo de staging do
    queryout (nunca pipe/FIFO). ``errfile`` → ``-e``: o bcp grava ali a
    linha REJEITADA em texto tab-separado com cabeçalho
    '#@ Row N, Column M: <erro> @#' (linha/coluna/valor exatos — mesmo na
    carga nativa). A tabela vai em DUAS partes ``[schema].[tabela]`` +
    ``-d`` — a doc do bcp PROÍBE nome em 3 partes junto com ``-d``
    (database duas vezes). Função PURA."""
    tabela = f"{quote_ident(dst_schema)}.{quote_ident(dst_table)}"
    cmd = [str(bcp_path), tabela, "in", str(datafile),
           "-S", f"{host},{int(port or 1433)}", "-d", str(database),
           "-U", str(user), "-P", str(password or ""), "-n", "-k",
           "-b", str(int(batch_size)), "-m", "1"]
    if errfile:
        cmd += ["-e", str(errfile)]
    if trust_cert:
        cmd.append("-u")
    if tablock:
        cmd += ["-h", "TABLOCK"]
    return cmd


def parse_progresso_bcp(linha):
    """Interpreta UMA linha do stdout do ``bcp in`` (função PURA):
    ``("lote", total_acumulado)`` para as linhas de progresso por lote
    ("N rows sent to SQL Server. Total sent: M"), ``("total", n)`` para o
    resumo final ("N rows copied." — valor de RECONCILIAÇÃO da faixa) e
    None para as demais linhas (banner, clock time...)."""
    m = _BCP_LOTE_RE.match(linha or "")
    if m:
        return ("lote", int(m.group(2)))
    m = _BCP_TOTAL_RE.match(linha or "")
    if m:
        return ("total", int(m.group(1)))
    return None


def total_nas_mensagens(linhas):
    """Total final ("N rows copied.") nas mensagens de UM processo bcp —
    None se a linha de resumo não apareceu (função PURA). O ``bcp queryout``
    (leitor) imprime o MESMO resumo do ``bcp in``: é o que permite
    RECONCILIAR exportado × gravado no pipe — bcp pode sair com exit 0 sem
    ter movido linha nenhuma (incidente 2026-07-04: faixa 'concluída' com 0
    linha e 1M na origem), então exit code sozinho NÃO é prova de sucesso."""
    total = None
    for linha in (linhas or ()):
        ev = parse_progresso_bcp(linha)
        if ev and ev[0] == "total":
            total = ev[1]
    return total


# "Column N" nos cabeçalhos do arquivo -e do bcp (p/ traduzir em nome).
_ERRFILE_COL_RE = re.compile(r"(Column\s+(\d+))")


def resumo_errfile(texto, dst_columns=None, limite=1000):
    """Trecho legível do arquivo ``-e`` do bcp (função PURA): os cabeçalhos
    '#@ Row N, Column M: <erro> @#' seguidos da PRÓPRIA linha rejeitada —
    o bcp grava a linha em texto tab-separado mesmo na carga nativa, o que
    aponta a linha, a coluna (ordinal no DESTINO) e o valor exatos que
    falharam. Com ``dst_columns`` (nomes na ordem do destino) o ordinal
    ganha o nome: 'Column 2 (num_cpf_cnpj)'. Vazio → ''."""
    linhas = [l.strip() for l in (texto or "").splitlines() if l.strip()]
    trecho = " | ".join(linhas)
    if dst_columns:
        def _nome(m):
            i = int(m.group(2))
            if 1 <= i <= len(dst_columns):
                return f"{m.group(1)} ({dst_columns[i - 1]})"
            return m.group(1)
        trecho = _ERRFILE_COL_RE.sub(_nome, trecho)
    return trecho[:limite]


def probe_bcp(src_air, src_db, dst_air, dst_db):
    """Probe de viabilidade do engine bcp_native — roda ANTES das faixas:
    um ``SELECT 1`` queryout para /dev/null em CADA servidor valida binário,
    login e TLS nas duas pontas em segundos. Retorna None quando viável;
    senão o MOTIVO (stderr truncado e com senha redigida) — o chamador loga
    claro e cai para o streaming pymssql NA EXECUÇÃO INTEIRA (atualizando o
    engine gravado), sem deixar a exec presa em falhas sistemáticas."""
    ctx = preparar_bcp()
    if ctx is None:
        return "binário bcp não encontrado no worker"
    trust = "-u" in ctx["flags"]
    for rotulo, air, db in (("origem", src_air, src_db),
                            ("destino", dst_air, dst_db)):
        host, port, user, senha = _conn_params(air)
        cmd = montar_cmd_bcp_queryout(ctx["path"], "SELECT 1", host, port,
                                      db, user, senha, datafile="/dev/null",
                                      trust_cert=trust)
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True,
                                  errors="replace", timeout=90)
        except Exception as e:
            return f"probe bcp na {rotulo} ({host}:{port}/{db}) falhou: {e}"
        if proc.returncode != 0:
            err = _redigir_texto(
                (proc.stderr or proc.stdout or "").strip(), (senha,))[:400]
            return (f"probe bcp na {rotulo} ({host}:{port}/{db}) falhou "
                    f"(exit {proc.returncode}): {err}")
    return None


def copiar_faixa_bcp(bcp_ctx, select_sql, src_air, src_db, dst_air, dst_db,
                     dst_schema, dst_table, batch_size,
                     on_lote=None, deve_cancelar=None,
                     dst_columns=None) -> dict:
    """Copia UMA faixa com o utilitário nativo bcp em DUAS fases, via
    ARQUIVO de staging em disco: ``bcp queryout`` exporta a faixa (formato
    NATIVO) para o arquivo e ``bcp in`` o importa no destino.

    Por que arquivo e NUNCA pipe/FIFO (incidente 2026-07-04): em stream
    não-seekável o ``bcp in`` faz leituras curtas e desalinha o formato
    nativo — linhas são descartadas/corrompidas em SILÊNCIO e o processo
    ainda sai com exit 0 (reproduzido com mssql-tools 18.6.2.1: via pipe,
    11.818 de 200.000 linhas chegaram; via arquivo, 200.000/200.000). Custo
    aceito: a faixa toca disco no worker — o diretório vem de
    ``COPY_BCP_TMPDIR`` (default: tmp do sistema), o espaço livre é logado
    antes do export e o arquivo é SEMPRE removido no ``finally``. Partição
    em N faixas divide o staging em N arquivos menores (um por faixa em
    andamento).

    Progresso/cancelamento: na fase de EXPORT cada linha de progresso do
    leitor checa ``deve_cancelar()`` (True → terminate, faixa 'cancelado');
    na fase de IMPORT cada linha "N rows sent ... Total sent: M" do escritor
    vira ``on_lote(delta)`` (best-effort) além da checagem de cancelamento.
    A granularidade depende do flush do stdout do bcp.

    Sucesso exige, ALÉM do exit 0 nas duas pontas, a RECONCILIAÇÃO dos
    totais: o "N rows copied." do LEITOR (queryout) tem que bater com o do
    escritor — bcp pode sair 0 sem ter movido nada (incidente 2026-07-04).

    Falha (exit != 0 em qualquer ponta): a cauda do STDOUT do processo entra
    na erro_msg (os erros de linha do bcp saem no stdout, não no stderr) +
    stderr do escritor (senha redigida, truncado em 4000) →
    {"status": "erro"}. O escritor roda com ``-e`` (arquivo de erro ao lado
    do staging): a linha REJEITADA entra na erro_msg em texto legível, com
    linha/coluna/valor — ``dst_columns`` (nomes na ordem do destino) traduz
    o ordinal 'Column N' no nome da coluna. Sem timeout próprio (faixas
    longas) — o teto é o execution_timeout da task (6h).

    Trade-off ACEITO do v1: a senha vai em ``-P`` no argv dos processos bcp
    — ela NUNCA aparece em log (redigir_cmd) nem em mensagem persistida
    (_redigir_texto), mas fica visível no process list DENTRO do container
    do worker enquanto o bcp roda (container mono-serviço, não interativo).

    Retorna {"status": concluido|cancelado|erro, "rows": int,
    "erro_msg": str|None} — nunca levanta exceção.
    """
    host_s, port_s, user_s, senha_s = _conn_params(src_air)
    host_d, port_d, user_d, senha_d = _conn_params(dst_air)
    flags = bcp_ctx.get("flags") or set()
    trust = "-u" in flags
    tablock = "-h" in flags

    status, rows, erro_msg = "erro", 0, None
    total_lote, total_final = 0, None
    cancelada = False
    saida_leitor = deque(maxlen=400)
    saida_escritor = deque(maxlen=400)
    err_escritor = ""

    def _cauda(linhas, n=8):
        return " | ".join(list(linhas)[-n:])

    def _esperar(proc, curto):
        try:
            proc.wait(timeout=120 if curto else None)
        except Exception:
            try:
                proc.kill()
                proc.wait(timeout=30)
            except Exception:
                pass

    tmp_dir = os.environ.get("COPY_BCP_TMPDIR") or None
    fd, staging = tempfile.mkstemp(prefix="orq_copy_bcp_", suffix=".dat",
                                   dir=tmp_dir)
    os.close(fd)
    errfile = staging + ".err"
    leitor = escritor = None
    try:
        # ---------- fase 1: EXPORT (queryout → arquivo de staging) ----------
        cmd_leitor = montar_cmd_bcp_queryout(
            bcp_ctx["path"], select_sql, host_s, port_s, src_db,
            user_s, senha_s, datafile=staging, trust_cert=trust)
        log.info("[COPY][bcp] leitor:   %s", " ".join(redigir_cmd(cmd_leitor)))
        try:
            livre_gb = shutil.disk_usage(os.path.dirname(staging)).free / 1e9
            log.info("[COPY][bcp] staging: %s (%.1f GB livres no diretório)",
                     staging, livre_gb)
        except Exception:
            pass

        leitor = subprocess.Popen(
            cmd_leitor, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, errors="replace")
        for linha in leitor.stdout:
            saida_leitor.append(linha.rstrip("\n"))
            if deve_cancelar is not None and deve_cancelar():
                cancelada = True
                try:
                    leitor.terminate()
                except Exception:
                    pass
                break
        _esperar(leitor, cancelada)

        if cancelada:
            status, rows = "cancelado", 0
        elif leitor.returncode != 0:
            erro_msg = _redigir_texto(
                f"bcp queryout exit {leitor.returncode}: "
                f"{_cauda(saida_leitor)}", (senha_s, senha_d))[:4000]
        else:
            leitor_total = total_nas_mensagens(saida_leitor)
            try:
                tam_mb = os.path.getsize(staging) / 1e6
            except Exception:
                tam_mb = float("nan")
            log.info("[COPY][bcp] export: %s linha(s), %.1f MB em staging",
                     leitor_total, tam_mb)

            # ---------- fase 2: IMPORT (arquivo de staging → bcp in) --------
            cmd_escritor = montar_cmd_bcp_in(
                bcp_ctx["path"], dst_schema, dst_table, host_d, port_d,
                dst_db, user_d, senha_d, batch_size, datafile=staging,
                trust_cert=trust, tablock=tablock, errfile=errfile)
            log.info("[COPY][bcp] escritor: %s",
                     " ".join(redigir_cmd(cmd_escritor)))
            escritor = subprocess.Popen(
                cmd_escritor, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, errors="replace")
            for linha in escritor.stdout:
                saida_escritor.append(linha.rstrip("\n"))
                evento = parse_progresso_bcp(linha)
                if evento:
                    tipo, n = evento
                    if tipo == "total":
                        total_final = n
                        continue
                    delta = n - total_lote
                    total_lote = n
                    if delta > 0 and on_lote is not None:
                        try:
                            on_lote(delta)
                        except Exception as e:
                            log.warning("[COPY][bcp] progresso falhou "
                                        "(segue): %s", e)
                if deve_cancelar is not None and deve_cancelar():
                    cancelada = True
                    try:
                        escritor.terminate()
                    except Exception:
                        pass
                    break
            try:
                _, err_escritor = escritor.communicate(
                    timeout=120 if cancelada else None)
            except Exception:
                try:
                    escritor.kill()
                    _, err_escritor = escritor.communicate(timeout=30)
                except Exception:
                    pass

            if cancelada:
                status, rows = "cancelado", total_lote
            elif escritor.returncode == 0:
                rows = total_final if total_final is not None else total_lote
                # RECONCILIAÇÃO leitor × escritor: exit 0 dos dois bcp NÃO
                # prova que os dados fluíram (incidente 2026-07-04: pipe
                # desalinhado + -m 0 = perda silenciosa com exit 0). O total
                # exportado pelo leitor tem que bater com o gravado pelo
                # escritor — divergência (ou resumo ausente) é ERRO, com a
                # cauda das mensagens dos DOIS processos para diagnóstico.
                log.info("[COPY][bcp] reconciliação: leitor exportou %s, "
                         "escritor gravou %s", leitor_total, rows)
                if leitor_total == rows:
                    status = "concluido"
                else:
                    erro_msg = _redigir_texto(
                        "bcp terminou sem código de erro, mas os totais "
                        "divergem: leitor exportou "
                        f"{leitor_total if leitor_total is not None else 'resumo ausente'} "
                        f"e o escritor gravou {rows} linha(s). "
                        f"Mensagens do leitor: {_cauda(saida_leitor) or '(vazio)'} | "
                        f"Mensagens do escritor: {_cauda(saida_escritor) or '(vazio)'}",
                        (senha_s, senha_d))[:4000]
            else:
                partes = [f"bcp in exit {escritor.returncode}: "
                          f"{_cauda(saida_escritor)}"]
                cauda_err = " | ".join(
                    (err_escritor or "").strip().splitlines()[-4:])
                if cauda_err:
                    partes.append(f"stderr: {cauda_err}")
                # Arquivo -e do bcp: a linha REJEITADA (texto tab-separado,
                # latin-1 cobre o CP1252 dos servidores) com linha/coluna/
                # valor — é o diagnóstico que aponta a coluna estourada.
                try:
                    with open(errfile, encoding="latin-1") as f:
                        trecho = resumo_errfile(f.read(65536), dst_columns)
                except Exception:
                    trecho = ""
                if trecho:
                    partes.append(f"linha rejeitada (-e): {trecho}")
                erro_msg = _redigir_texto(
                    " | ".join(partes), (senha_s, senha_d))[:4000]
                rows = total_lote
    except Exception as e:
        erro_msg = _redigir_texto(str(e), (senha_s, senha_d))[:4000]
        for p in (leitor, escritor):
            try:
                if p is not None and p.poll() is None:
                    p.kill()
            except Exception:
                pass
    finally:
        for arq in (staging, errfile):
            try:
                os.unlink(arq)
            except Exception:
                pass
    return {"status": status, "rows": int(rows or 0), "erro_msg": erro_msg}


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
    subconjunto embaralharia dados SILENCIOSAMENTE.

    O ``bcp ... in`` SEM format file tem o MESMO perigo (mapeamento
    posicional contra todas as colunas físicas do destino). Política do
    ENGINE_BCP (v1 NUNCA gera format file — complexidade/risco):

      - o engine bcp_native só se mantém quando as colunas físicas 1..N do
        destino coincidirem EXATAMENTE com ``dst_columns`` (mesma checagem
        case-insensitive do pymssql posicional) E o binário bcp continuar
        disponível — nesse caso ``target["bcp"]`` recebe o contexto
        {"path", "flags"} e ``charset`` fica None (formato NATIVO: tipos
        binários, o codepage não se aplica);
      - caso contrário, cai para o próximo engine streaming
        (``resolve_engine(incluir_bcp=False)`` — normalmente
        pymssql_bulk_copy, que tem column_ids), logando o motivo.

    Para ENGINE_BULK_COPY:

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

    if engine == ENGINE_BCP:
        fisicas = _colunas_fisicas_destino(dst_conn, dst_schema, dst_table)
        if not fisicas:
            raise ValueError(
                f"Tabela de destino {table_fqn} não encontrada ao resolver "
                "as colunas do engine bcp_native")
        nomes_fisicos = [nome for nome, _ in fisicas]
        bcp_ctx = preparar_bcp()
        if bcp_ctx is not None and [n.lower() for n in nomes_fisicos] \
                == [str(c).lower() for c in dst_columns]:
            target["bcp"] = bcp_ctx
            target["charset"] = None  # formato nativo: codepage não se aplica
            log.info("[COPY] bcp_native mantido: colunas físicas 1..N do "
                     "destino coincidem exatamente com dst_columns")
            return target
        if bcp_ctx is None:
            motivo = "binário bcp indisponível no worker"
        else:
            motivo = (
                "bcp in sem format file mapeia POSICIONALMENTE contra as "
                f"colunas físicas do destino {nomes_fisicos}, que não "
                f"coincidem com as colunas da cópia {list(dst_columns)} "
                "(format file fica fora do v1)")
        engine = resolve_engine(incluir_bcp=False)
        log.warning("[COPY] %s — caindo para o engine %s", motivo, engine)
        target["engine"] = engine
        target["motivo_fallback"] = motivo
        # segue no fluxo do engine escolhido (column_ids/charset abaixo)

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

    if engine == ENGINE_BCP:
        # O engine bcp copia por PIPE de processos (copiar_faixa_bcp), não
        # por lotes em memória — chegar aqui é bug do chamador.
        raise ValueError(
            "bulk_write não atende o engine bcp_native — use copiar_faixa_bcp")

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


# Nome de collation válido (identificador simples do catálogo) — guarda
# contra qualquer valor inesperado ir parar no DDL.
_COLLATION_RE = re.compile(r"^[A-Za-z0-9_]+$")


def _collate_sql(collation) -> str:
    """Cláusula `` COLLATE <nome>`` para o DDL (função PURA) — '' quando a
    coluna não tem collation (tipos não-texto) ou o nome não passa na
    guarda de identificador."""
    if collation and _COLLATION_RE.match(str(collation)):
        return f" COLLATE {collation}"
    return ""


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

    Regras (spec Cópia de Dados — réplica FIEL da estrutura da origem):
      - tipos, tamanhos, nulabilidade e COLLATION preservados
        (sys.columns/sys.types da origem);
      - colunas com pad_condicional/pad_fixo viram
        VARCHAR(max(tamanhos do pad, largura ORIGINAL da coluna texto)) —
        o pad produz strings de exatamente n chars, então NUNCA pode nascer
        mais estreita que o maior caso (origem numérica usa só os tamanhos;
        origem (n)varchar(max) fica como está);
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
            f"SELECT c.name, t.name, c.max_length, c.precision, c.scale, "
            f"c.is_nullable, c.collation_name "
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
                "is_nullable": bool(row[5]), "collation": row[6],
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
        # Pad produz strings de EXATAMENTE n chars — a coluna do destino
        # precisa de VARCHAR(max(tamanhos do pad, largura ORIGINAL)) para
        # QUALQUER tipo de origem. A regra antiga só alargava origem
        # NUMÉRICA: origem VARCHAR(11) com pad_condicional de 14 (CNPJ)
        # nascia varchar(11) e a carga estourava "String data, right
        # truncation" (incidente 2026-07-04, DM_Clientes_contratos).
        # Origem (n)varchar(max) fica como está — já comporta o pad.
        tipo_orig = (info["tipo"] or "").lower()
        if ttipo in ("pad_fixo", "pad_condicional") \
                and not (tipo_orig not in _TIPOS_NUMERICOS
                         and int(info["max_length"] or 0) < 0):
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
            if tipo_orig not in _TIPOS_NUMERICOS:
                largura = int(info["max_length"] or 0)
                if tipo_orig in ("nchar", "nvarchar"):
                    largura //= 2  # max_length de N* é em BYTES
                tamanhos.append(largura)
            n = max((t for t in tamanhos if t > 0), default=50)
            tipo_sql = f"VARCHAR({n})"

        # COLLATION da origem preservada (fidelidade 100% da réplica; sem
        # ela a coluna nasce com a collation default do BANCO de destino e
        # a carga nativa pode sofrer conversão de codepage).
        colacao = _collate_sql(info.get("collation"))
        nulabilidade = "NULL" if info["is_nullable"] else "NOT NULL"
        defs.append(
            f"    {quote_ident(nome)} {tipo_sql}{colacao} {nulabilidade}")

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
    # r[4]=system_type_id, r[5]=system_type_name, ... r[9]=collation_name
    defs = []
    for r in rows:
        if r[0]:  # is_hidden
            continue
        nome, is_nullable, tipo_sql = r[2], bool(r[3]), r[5]
        colacao = _collate_sql(r[9] if len(r) > 9 else None)
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
        defs.append(f"    {quote_ident(nome)} {tipo_sql}{colacao} {nulabilidade}")

    if not defs:
        raise ValueError(
            "sp_describe_first_result_set não retornou colunas para a query "
            "— crie a tabela de destino manualmente e desmarque 'Criar nova tabela'.")

    fqn_destino = f"{quote_ident(dst_schema)}.{quote_ident(dst_table)}"
    return f"CREATE TABLE {fqn_destino} (\n" + ",\n".join(defs) + "\n)"
