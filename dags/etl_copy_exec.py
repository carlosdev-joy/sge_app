"""
etl_copy_exec.py
================
DAG genérica de execução do módulo Cópia de Dados (tela /copia-dados).

Disparada pela API do ORQUESTRA (POST /copias/{id}/executar) com:
  {"exec_id": <id em dbo.etl_copy_exec>}

Fluxo:
  1. Carrega execução + job (dbo.etl_copy_exec JOIN dbo.etl_copy_job);
  2. status='executando'; escolhe o engine: se origem e destino resolvem para
     o MESMO servidor (host:port das Airflow Connections, case-insensitive)
     → engine server_side_insert (INSERT...SELECT cross-database DENTRO do
     próprio SQL Server — nada trafega pelo worker; probe de viabilidade
     best-effort na conexão de origem, com fallback para streaming); senão
     resolve o engine de escrita streaming
     (bcp nativo → pymssql bulk_copy → pyodbc fast_executemany →
     pymssql executemany); com bcp_native, um PROBE de conexão/TLS nas duas
     pontas decide antes das faixas — falhou → cai para o streaming pymssql
     NA EXECUÇÃO INTEIRA (engine gravado atualizado), sem exec presa;
  3. Prepara o destino: criar_tabela (via script_create_table, se não existir;
     no MODO QUERY — job com src_query — via script_create_table_from_query,
     que usa sp_describe_first_result_set na origem)
     e truncar_antes (TRUNCATE com fallback DELETE); no fluxo STREAMING,
     resolve o ALVO de escrita UMA vez (bulk_copy.prepare_bulk_target:
     ordinais/column_ids das colunas de destino via sys.columns; sem suporte
     a column_ids no pymssql e ordem física divergente → cai para engine por
     nome, atualizando o engine registrado) — no engine server-side
     prepare_bulk_target e charset NÃO se aplicam (nada trafega pelo cliente);
  4. rows_total via count_sql na origem;
  5. Divide em faixas pela coluna de partição (int/bigint/decimal por
     aritmética; date/datetime por dias) — semiabertas [a, b), última fechada;
     coluna TEXTO (MIN/MAX chegam como str): se MIN e MAX forem hexadecimais
     (ex.: PK CHAR(32) de hash MD5) → modo HEX, faixas LEXICOGRÁFICAS
     sargáveis por prefixo hex de 2 chars (bulk_copy.faixas_hex); senão →
     modo HASH, faixas ABS(CHECKSUM(col)) % N = i (NÃO sargável — cada
     stream varre a origem filtrando; aviso no log), registradas como
     valor_ini='#HASH', valor_fim='i/N'. Faixa extra IS NULL
     (range_index=-1) se a coluna admitir NULL — vale nos DOIS modos.
     Sem partição → faixa única. Persistidas em dbo.etl_copy_exec_range;
  6. ThreadPoolExecutor (uma task só, IO-bound — pymssql solta o GIL): cada
     faixa lê por streaming (fetchmany) e grava por bulk_write, com progresso
     incremental atômico best-effort e checagem de cancelamento a cada 5 lotes;
     no engine server-side cada faixa vira UMA instrução INSERT...SELECT
     executada na conexão de origem (progresso e cancelamento por FAIXA);
     no engine bcp_native cada faixa vira um PIPE de processos
     ``bcp queryout → bcp in`` (formato nativo, C nas duas pontas) — as
     fronteiras vão INLINE como literais seguros (bulk_copy.sql_literal, o
     bcp não tem parâmetros), o progresso sai das linhas "rows sent" do
     escritor e o cancelamento termina os DOIS processos;
  7. Finaliza (concluido | erro | cancelado), notifica o solicitante em
     dbo.etl_notificacao (best-effort) e, se houve erro, falha a task
     (AirflowException) APÓS persistir tudo.

Estado/progresso ficam no banco do ORQUESTRA — a UI acompanha por polling.
Credenciais de origem/destino resolvidas por utils.conn_resolver.get_conexao
(dbo.etl_conexao primeiro — senha cifrada com ORQUESTRA_CONN_KEY —, fallback
Airflow Connections/BaseHook para conexões não migradas); nenhuma senha é
logada, retornada em XCom ou gravada em tabela.
"""
from __future__ import annotations

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from decimal import Decimal

import pendulum
from airflow import DAG
from airflow.exceptions import AirflowException
from airflow.operators.python import PythonOperator
from airflow.providers.microsoft.mssql.hooks.mssql import MsSqlHook

from utils import bulk_copy, conn_resolver

DAG_ID        = "etl_copy_exec"
MSSQL_CONN_ID = "SQL14_DMDB41"
LOCAL_TZ      = "America/Sao_Paulo"

# Checagem de cancelamento (etl_copy_exec.status='cancelando') a cada N lotes
CHECK_CANCEL_A_CADA_LOTES = 5

default_args = {"owner": "airflow", "depends_on_past": False, "retries": 0}


def _hook() -> MsSqlHook:
    """Hook do banco do ORQUESTRA (estado/progresso/notificação)."""
    return MsSqlHook(mssql_conn_id=MSSQL_CONN_ID)


# ---------------------------------------------------------------------------
# Carga da execução + job
# ---------------------------------------------------------------------------

_CAMPOS = [
    "exec_pk", "exec_status", "matricula",
    "job_id", "nome", "src_conn_id", "src_database", "src_schema", "src_table",
    "dst_conn_id", "dst_database", "dst_schema", "dst_table",
    "criar_tabela", "truncar_antes", "particao_coluna",
    "streams", "batch_size", "select_sql", "count_sql",
    "dst_columns_json", "colunas_json",
    "src_query",  # migration 053 (modo query) — pode não existir; ver abaixo
]

_SQL_CARREGAR = """
        SELECT e.id, e.status, e.matricula,
               j.id, j.nome, j.src_conn_id, j.src_database, j.src_schema, j.src_table,
               j.dst_conn_id, j.dst_database, j.dst_schema, j.dst_table,
               j.criar_tabela, j.truncar_antes, j.particao_coluna,
               j.streams, j.batch_size, j.select_sql, j.count_sql,
               j.dst_columns_json, j.colunas_json{extra}
        FROM dbo.etl_copy_exec e
        JOIN dbo.etl_copy_job j ON j.id = e.copy_job_id
        WHERE e.id = %s
        """


def _carregar_execucao(hook, exec_id):
    # Degradação graciosa (padrão do repo): tenta com a coluna src_query
    # (migration 053) e, se ela não existir no ambiente, refaz sem.
    try:
        row = hook.get_first(_SQL_CARREGAR.format(extra=", j.src_query"),
                             parameters=(exec_id,))
        campos = _CAMPOS
    except Exception as e:
        print(f"[COPY] Aviso: coluna src_query indisponível "
              f"(migration 053 aplicada?): {e} — carregando sem ela.")
        row = hook.get_first(_SQL_CARREGAR.format(extra=""),
                             parameters=(exec_id,))
        campos = _CAMPOS[:-1]
    if not row:
        return None
    d = dict(zip(campos, row))
    d.setdefault("src_query", None)
    d["src_query"]     = (d["src_query"] or "").strip() or None
    d["criar_tabela"]  = bool(d["criar_tabela"])
    d["truncar_antes"] = bool(d["truncar_antes"])
    d["batch_size"]    = max(1000, min(200000, int(d["batch_size"] or 50000)))
    return d


# ---------------------------------------------------------------------------
# Preparação do destino / contagem
# ---------------------------------------------------------------------------

def _fqn_destino(job) -> str:
    return (f"{bulk_copy.quote_ident(job['dst_schema'])}."
            f"{bulk_copy.quote_ident(job['dst_table'])}")


def _preparar_destino(src, dst_ctl, job):
    """criar_tabela (se não existir) e truncar_antes no destino (conexão de
    controle pymssql autocommit). MODO QUERY: o DDL sai do result set da
    própria query (sp_describe_first_result_set na origem)."""
    fqn = _fqn_destino(job)
    cur = dst_ctl.cursor()
    try:
        cur.execute("SELECT OBJECT_ID(%s, 'U')", (fqn,))
        existe = cur.fetchone()[0] is not None
        if not existe:
            if not job["criar_tabela"]:
                raise ValueError(
                    f"Tabela de destino {fqn} não existe e criar_tabela=0 — "
                    "crie a tabela ou marque 'Criar nova tabela' no job.")
            if job.get("src_query"):
                ddl = bulk_copy.script_create_table_from_query(
                    src, job["src_query"],
                    dst_schema=job["dst_schema"], dst_table=job["dst_table"])
            else:
                dst_cols = json.loads(job["dst_columns_json"])
                colunas  = (json.loads(job["colunas_json"] or "{}") or {}).get("colunas") or []
                ddl = bulk_copy.script_create_table(
                    src, job["src_database"], job["src_schema"], job["src_table"],
                    dst_cols, colunas,
                    dst_schema=job["dst_schema"], dst_table=job["dst_table"])
            print(f"[COPY] Criando tabela de destino:\n{ddl}")
            cur.execute(ddl)
        elif job["criar_tabela"]:
            print(f"[COPY] Tabela {fqn} já existe — criação ignorada.")

        if job["truncar_antes"]:
            try:
                cur.execute(f"TRUNCATE TABLE {fqn}")
                print(f"[COPY] TRUNCATE TABLE {fqn} OK")
            except Exception as e:
                # Sem permissão de TRUNCATE (ou FK) → DELETE (mais lento)
                print(f"[COPY] TRUNCATE falhou ({e}) — usando DELETE (mais lento).")
                cur.execute(f"DELETE FROM {fqn}")
                print(f"[COPY] DELETE FROM {fqn} OK")
    finally:
        cur.close()


def _probe_server_side(src, job):
    """Probe de viabilidade do engine server-side (best-effort, ANTES de
    preparar o destino): a conexão de ORIGEM — que é onde o select_sql roda,
    inclusive no modo query — precisa enxergar a tabela de destino
    cross-database no mesmo servidor (``OBJECT_ID`` em 3 partes).

    Retorna None quando viável; senão uma string com o MOTIVO (o chamador
    loga o warning e cai para o fluxo streaming). Exceção: se OBJECT_ID vier
    NULL mas criar_tabela=1, considera viável — a tabela pode simplesmente
    ainda não existir (será criada por _preparar_destino antes da carga)."""
    fqn3 = (f"{bulk_copy.quote_ident(job['dst_database'])}."
            f"{bulk_copy.quote_ident(job['dst_schema'])}."
            f"{bulk_copy.quote_ident(job['dst_table'])}")
    try:
        cur = src.cursor()
        try:
            cur.execute("SELECT OBJECT_ID(%s, 'U')", (fqn3,))
            existe = cur.fetchone()[0] is not None
        finally:
            cur.close()
    except Exception as e:
        return f"probe do destino {fqn3} falhou na conexão de origem: {e}"
    if existe or job["criar_tabela"]:
        return None
    return (f"OBJECT_ID({fqn3}) retornou NULL na conexão de origem "
            "(sem permissão cross-database ou tabela inexistente)")


def _contar_origem(src, job) -> int:
    """rows_total via count_sql compilado pela API (sem parâmetros — o SQL
    vai cru para o pymssql, então '%' literal não precisa de escape). No modo
    query o count_sql já envolve a src_query em subquery (_q)."""
    cur = src.cursor()
    try:
        cur.execute(job["count_sql"])
        return int(cur.fetchone()[0] or 0)
    finally:
        cur.close()


# ---------------------------------------------------------------------------
# Cálculo das faixas
# ---------------------------------------------------------------------------

def _calcular_faixas(vmin, vmax, streams):
    """Divide [vmin, vmax] em até ``streams`` faixas semiabertas [a, b) — a
    ÚLTIMA fechada [a, b]. Retorna lista de pares (ini, fim).

    Tipos suportados: int/bigint (aritmética inteira), decimal (Decimal) e
    date/datetime (divisão por dias). Coluna TEXTO (str) é tratada ANTES,
    em _faixas_texto (modos HEX/HASH). Tipo não suportado → faixa única.
    """
    if vmin is None or vmax is None:
        return []
    if streams <= 1 or vmin == vmax:
        return [(vmin, vmax)]

    if isinstance(vmin, (datetime, date)):
        dias = (vmax - vmin).days
        if dias <= 0:
            return [(vmin, vmax)]
        bounds = [vmin + timedelta(days=(dias * i) // streams)
                  for i in range(streams + 1)]
    elif isinstance(vmin, bool):
        return [(vmin, vmax)]
    elif isinstance(vmin, int):
        span = vmax - vmin
        bounds = [vmin + (span * i) // streams for i in range(streams + 1)]
    elif isinstance(vmin, Decimal):
        span = Decimal(vmax) - vmin
        bounds = [vmin + (span * i) / streams for i in range(streams + 1)]
    else:
        return [(vmin, vmax)]

    bounds[0], bounds[-1] = vmin, vmax
    uniq = sorted(set(bounds))
    if len(uniq) < 2:
        return [(vmin, vmax)]
    return [(uniq[i], uniq[i + 1]) for i in range(len(uniq) - 1)]


# MIN/MAX inteiramente hexadecimais → modo HEX (faixas lexicográficas)
_HEX_RE = re.compile(r"^[0-9A-Fa-f]+$")


def _faixas_texto(vmin, vmax, streams):
    """Faixas de uma coluna de partição TEXTO (MIN/MAX chegam como str do
    pymssql — char/varchar/nchar/nvarchar). Retorna a lista de dicts de
    faixa (sem a faixa IS NULL, que o chamador acrescenta nos dois modos).

    - Modo HEX: MIN e MAX casam com ^[0-9A-Fa-f]+$ (ex.: PK CHAR(32) de hash
      MD5) → faixas LEXICOGRÁFICAS por prefixo hexadecimal de 2 chars
      (bulk_copy.faixas_hex, função pura) — semiabertas, última fechada no
      MAX real; comparação vira range seek em índice/PK (sargável).
    - Modo HASH (fallback genérico): texto NÃO-hex → faixas
      ABS(CHECKSUM(col)) % N = i (i = 0..N-1), com o par (i, N) guardado em
      faixa['hash'] e registradas como valor_ini='#HASH', valor_fim='i/N'.
      NÃO é sargável — cada stream varre a origem filtrando (aviso no log).

    Espaços à direita (padding de CHAR) são ignorados na detecção e nas
    fronteiras — o SQL Server também os ignora na comparação de strings."""
    vmin_s = (vmin or "").rstrip()
    vmax_s = (vmax or "").rstrip()
    if vmin_s and vmax_s and _HEX_RE.match(vmin_s) and _HEX_RE.match(vmax_s):
        pares = bulk_copy.faixas_hex(vmin_s, vmax_s, streams)
        print(f"[COPY] Partição texto em modo HEX: {len(pares)} faixa(s) "
              "lexicográficas por prefixo hexadecimal (sargável)")
        return [{"range_index": i, "ini": a, "fim": b, "ultima": ultima,
                 "is_null": False, "unica": False}
                for i, (a, b, ultima) in enumerate(pares)]
    n = max(1, int(streams or 1))
    print(f"[COPY] Aviso: partição texto NÃO-hexadecimal — modo HASH "
          f"(ABS(CHECKSUM) % {n}): as faixas NÃO são sargáveis e cada "
          "stream varre a origem filtrando. Prefira uma coluna numérica, "
          "de data ou de hash hexadecimal para range seek.")
    return [{"range_index": i, "ini": "#HASH", "fim": f"{i}/{n}",
             "ultima": False, "is_null": False, "unica": False,
             "hash": (i, n)}
            for i in range(n)]


def _particao_admite_null(src, job) -> bool:
    """True se a coluna de partição admitir NULL na ORIGEM (sys.columns).

    Quando a coluna do SELECT é transformada (alias sem coluna física 1:1)
    — ou no MODO QUERY, em que não há tabela de origem 1:1 — cai para um
    EXISTS na própria subquery compilada. Best-effort: em qualquer erro
    assume False (sem faixa IS NULL)."""
    part = job["particao_coluna"]
    origem = None
    if not job.get("src_query"):
        try:
            colunas = (json.loads(job["colunas_json"] or "{}") or {}).get("colunas") or []
            for c in colunas:
                if (c.get("destino") or c.get("origem")) == part and not c.get("transform"):
                    origem = c.get("origem")
                    break
        except Exception:
            origem = None

    cur = src.cursor()
    try:
        if origem:
            qdb = bulk_copy.quote_ident(job["src_database"])
            fqn = (f"{qdb}.{bulk_copy.quote_ident(job['src_schema'])}."
                   f"{bulk_copy.quote_ident(job['src_table'])}")
            cur.execute(
                f"SELECT c.is_nullable FROM {qdb}.sys.columns c "
                f"WHERE c.object_id = OBJECT_ID(%s) AND c.name = %s",
                (fqn, origem),
            )
            row = cur.fetchone()
            if row is not None:
                return bool(row[0])
        # Fallback: existe alguma linha com a partição NULL no SELECT compilado?
        cur.execute(
            f"SELECT CASE WHEN EXISTS (SELECT 1 FROM ({job['select_sql']}) AS src "
            f"WHERE {bulk_copy.quote_ident(part)} IS NULL) THEN 1 ELSE 0 END"
        )
        row = cur.fetchone()
        return bool(row and row[0])
    except Exception as e:
        print(f"[COPY] Aviso: não foi possível checar NULL da partição: {e}")
        return False
    finally:
        cur.close()


def _str100(v):
    """Valor de fronteira → NVARCHAR(100) legível (str; None preservado)."""
    return None if v is None else str(v)[:100]


def _montar_faixas(hook, src, job, exec_id, streams):
    """Calcula e persiste as faixas em dbo.etl_copy_exec_range.

    O MIN/MAX roda sobre a subquery do select_sql compilado (funciona igual
    no modo tabela e no MODO QUERY) e vai SEM parâmetros — o SQL segue cru
    para o pymssql, sem formatação % (nenhum escape de '%' necessário aqui).

    Retorna a lista de faixas com os valores TIPADOS em memória (int/Decimal/
    date/datetime; str no modo HEX de partição texto) para o WHERE
    parametrizado — valor_ini/valor_fim no banco são apenas a representação
    em texto para a UI. MIN/MAX string (pymssql devolve str para colunas
    char/varchar/nchar/nvarchar) → _faixas_texto decide entre HEX (faixas
    lexicográficas sargáveis) e HASH (ABS(CHECKSUM) % N, marcadas com
    valor_ini='#HASH' e o par (i, N) em faixa['hash'])."""
    part = (job["particao_coluna"] or "").strip()
    faixas = []
    if part:
        part_q = bulk_copy.quote_ident(part)
        cur = src.cursor()
        try:
            cur.execute(
                f"SELECT MIN({part_q}), MAX({part_q}) "
                f"FROM ({job['select_sql']}) AS src")
            vmin, vmax = cur.fetchone()
        finally:
            cur.close()
        print(f"[COPY] Partição [{part}]: MIN={vmin} MAX={vmax}")

        if isinstance(vmin, str) or isinstance(vmax, str):
            faixas = _faixas_texto(vmin, vmax, streams)
        else:
            pares = _calcular_faixas(vmin, vmax, streams)
            for i, (a, b) in enumerate(pares):
                faixas.append({"range_index": i, "ini": a, "fim": b,
                               "ultima": i == len(pares) - 1,
                               "is_null": False, "unica": False})
        if _particao_admite_null(src, job):
            faixas.append({"range_index": -1, "ini": None, "fim": None,
                           "ultima": False, "is_null": True, "unica": False})
        if not faixas:
            # Origem vazia (MIN/MAX NULL e sem NULLs) → faixa única
            faixas.append({"range_index": 0, "ini": None, "fim": None,
                           "ultima": True, "is_null": False, "unica": True})
    else:
        faixas.append({"range_index": 0, "ini": None, "fim": None,
                       "ultima": True, "is_null": False, "unica": True})

    for f in faixas:
        hook.run(
            "INSERT INTO dbo.etl_copy_exec_range "
            "(exec_id, range_index, valor_ini, valor_fim, status) "
            "VALUES (%s, %s, %s, %s, 'pendente')",
            parameters=(exec_id, f["range_index"],
                        _str100(f["ini"]), _str100(f["fim"])),
        )
    ids = {r[0]: r[1] for r in hook.get_records(
        "SELECT range_index, id FROM dbo.etl_copy_exec_range WHERE exec_id = %s",
        parameters=(exec_id,))}
    for f in faixas:
        f["id"] = ids.get(f["range_index"])
    return faixas


# ---------------------------------------------------------------------------
# Worker de faixa (roda em thread — conexões PRÓPRIAS)
# ---------------------------------------------------------------------------

def _sql_da_faixa(job, faixa):
    """SELECT da faixa: subquery sobre o select_sql compilado pela API —
    no MODO QUERY o select_sql é a própria src_query e o envelope é o mesmo.

    Quando há parâmetros (%s), o pymssql aplica formatação estilo % no SQL —
    qualquer ``%`` literal do select_sql (ex.: LIKE na query do usuário)
    precisa virar ``%%`` (o replace abaixo). Nas execuções SEM parâmetros
    (faixa única, IS NULL e modo HASH) o SQL vai cru, sem formatação — o
    ``%`` do módulo do hash NÃO precisa (nem pode) ser escapado.

    Faixas por intervalo (numéricas/data e modo HEX de texto) vão SEMPRE
    parametrizadas — as fronteiras (inclusive strings) nunca são concatenadas
    no SQL. No modo HASH o WHERE usa só inteiros construídos internamente
    (i, N em faixa['hash']) + IS NOT NULL, que mantém os NULLs exclusivos da
    faixa IS NULL (range_index=-1), como nas comparações por intervalo."""
    part_q = (bulk_copy.quote_ident(job["particao_coluna"])
              if job["particao_coluna"] else None)
    if faixa.get("unica"):
        return f"SELECT * FROM ({job['select_sql']}) AS src", None
    if faixa.get("is_null"):
        return (f"SELECT * FROM ({job['select_sql']}) AS src "
                f"WHERE {part_q} IS NULL"), None
    if faixa.get("hash"):
        i, n = faixa["hash"]
        return (f"SELECT * FROM ({job['select_sql']}) AS src "
                f"WHERE {part_q} IS NOT NULL "
                f"AND ABS(CHECKSUM({part_q})) % {int(n)} = {int(i)}"), None
    escaped = job["select_sql"].replace("%", "%%")
    op_fim = "<=" if faixa.get("ultima") else "<"
    sql = (f"SELECT * FROM ({escaped}) AS src "
           f"WHERE {part_q} >= %s AND {part_q} {op_fim} %s")
    return sql, (faixa["ini"], faixa["fim"])


def _sql_da_faixa_bcp(job, faixa):
    """SELECT da faixa para o engine bcp_native — MESMA lógica do
    _sql_da_faixa, com duas diferenças obrigatórias:

      - o bcp NÃO tem parâmetros: as fronteiras de intervalo vão INLINE como
        literais T-SQL SEGUROS (bulk_copy.sql_literal — aspas duplicadas,
        ISO para datas, str para números, caractere de controle rejeitado);
      - AQUI NÃO existe a formatação % do pymssql: o select_sql segue CRU
        (nenhum escape ``%`` → ``%%``) — o SQL vai inteiro no argv do bcp.
    """
    part_q = (bulk_copy.quote_ident(job["particao_coluna"])
              if job["particao_coluna"] else None)
    if faixa.get("unica"):
        return f"SELECT * FROM ({job['select_sql']}) AS src"
    if faixa.get("is_null"):
        return (f"SELECT * FROM ({job['select_sql']}) AS src "
                f"WHERE {part_q} IS NULL")
    if faixa.get("hash"):
        i, n = faixa["hash"]
        return (f"SELECT * FROM ({job['select_sql']}) AS src "
                f"WHERE {part_q} IS NOT NULL "
                f"AND ABS(CHECKSUM({part_q})) % {int(n)} = {int(i)}")
    op_fim = "<=" if faixa.get("ultima") else "<"
    return (f"SELECT * FROM ({job['select_sql']}) AS src "
            f"WHERE {part_q} >= {bulk_copy.sql_literal(faixa['ini'])} "
            f"AND {part_q} {op_fim} {bulk_copy.sql_literal(faixa['fim'])}")


def _insert_da_faixa(job, faixa, dst_columns):
    """INSERT...SELECT de UMA faixa do engine server-side (montado por
    bulk_copy.montar_insert_select — destino em 3 partes, WITH (TABLOCK) e
    lista explícita de colunas na ordem do SELECT compilado).

    MESMA lógica/escapes do _sql_da_faixa: quando a faixa vai parametrizada
    (%s), o pymssql aplica formatação estilo % no SQL inteiro — qualquer
    ``%`` literal do select_sql precisa virar ``%%``; sem parâmetros
    (faixa única / IS NULL / modo HASH) o SQL segue cru — o ``%`` do módulo
    do hash fica literal, sem escape. Fronteiras de intervalo (inclusive as
    strings do modo HEX) vão SEMPRE como parâmetros."""
    part_q = (bulk_copy.quote_ident(job["particao_coluna"])
              if job["particao_coluna"] else None)
    if faixa.get("unica"):
        select_sql, where, params = job["select_sql"], None, None
    elif faixa.get("is_null"):
        select_sql, where, params = job["select_sql"], f"{part_q} IS NULL", None
    elif faixa.get("hash"):
        i, n = faixa["hash"]
        select_sql = job["select_sql"]  # sem parâmetros → SQL cru, sem escape
        where = (f"{part_q} IS NOT NULL "
                 f"AND ABS(CHECKSUM({part_q})) % {int(n)} = {int(i)}")
        params = None
    else:
        select_sql = job["select_sql"].replace("%", "%%")
        op_fim = "<=" if faixa.get("ultima") else "<"
        where = f"{part_q} >= %s AND {part_q} {op_fim} %s"
        params = (faixa["ini"], faixa["fim"])
    sql = bulk_copy.montar_insert_select(
        job["dst_database"], job["dst_schema"], job["dst_table"],
        dst_columns, select_sql, where_faixa=where)
    return sql, params


def _exec_prog(prog, sql, params):
    """UPDATE de progresso best-effort (nunca derruba a cópia)."""
    try:
        cur = prog.cursor()
        cur.execute(sql, params)
        cur.close()
    except Exception as e:
        print(f"[COPY] Aviso: update de progresso falhou: {e}")


def _status_exec(prog, exec_id):
    """Status atual da execução (para checar 'cancelando'). None em erro."""
    try:
        cur = prog.cursor()
        cur.execute("SELECT status FROM dbo.etl_copy_exec WHERE id = %s", (exec_id,))
        row = cur.fetchone()
        cur.close()
        return row[0] if row else None
    except Exception:
        return None


def _copiar_faixa(faixa, job, exec_id, alvo, src_air, dst_air):
    """Copia UMA faixa, com conexões PRÓPRIAS de origem, destino e progresso.

    ``alvo`` = contexto de bulk_copy.prepare_bulk_target (engine efetivo,
    table_fqn, colunas e column_ids), resolvido UMA vez na task principal —
    no engine server-side, contexto mínimo {"engine", "columns"}; no engine
    bcp_native, ``alvo["bcp"]`` traz {"path", "flags"} do binário e a cópia
    da faixa é delegada a bulk_copy.copiar_faixa_bcp (pipe de processos,
    sem conexões pymssql de dados — só a de progresso).

    Engine server_side_insert: a faixa vira UMA instrução INSERT...SELECT
    executada DENTRO do SQL Server, numa única conexão pymssql na ORIGEM
    (autocommit; query_timeout=0 — a instrução pode rodar dezenas de
    minutos). Nada trafega pelo worker; o progresso é UMA atualização ao
    final da faixa (cursor.rowcount) e o CANCELAMENTO tem granularidade de
    FAIXA: o status 'cancelando' é checado antes de iniciar cada faixa —
    uma instrução já em andamento NÃO é interrompida.

    Retorna {"range_id", "range_index", "status", "rows", "erro_msg"} — nunca
    levanta exceção (o desfecho vai no dicionário e é persistido na faixa)."""
    resultado = {"range_id": faixa["id"], "range_index": faixa["range_index"],
                 "status": "erro", "rows": 0, "erro_msg": None}
    prog = src = dst = None
    try:
        prog = _hook().get_conn()
        prog.autocommit(True)  # incrementos atômicos, sem transação pendurada

        if _status_exec(prog, exec_id) == "cancelando":
            resultado["status"] = "cancelado"
            return resultado

        _exec_prog(prog,
                   "UPDATE dbo.etl_copy_exec_range "
                   "SET status='executando', iniciado_em=GETDATE() WHERE id=%s",
                   (faixa["id"],))

        if alvo["engine"] == bulk_copy.ENGINE_SERVER_SIDE:
            # ── Server-side: INSERT...SELECT dentro do SQL Server ──────────
            # Conexão ÚNICA na ORIGEM (o select_sql roda no database de
            # origem; o destino vai qualificado em 3 partes). query_timeout=0
            # garante que a instrução longa não é morta por timeout.
            src = bulk_copy.open_src_conn(src_air, job["src_database"],
                                          query_timeout=0)
            sql, params = _insert_da_faixa(job, faixa, alvo["columns"])
            cur = src.cursor()
            try:
                if params:
                    cur.execute(sql, params)
                else:
                    cur.execute(sql)
                # rowcount do cursor: o pymssql preenche para INSERT (um
                # SELECT @@ROWCOUNT separado perderia o valor no autocommit).
                copiadas = int(cur.rowcount if cur.rowcount is not None else -1)
            finally:
                cur.close()
            if copiadas < 0:
                print(f"[COPY] Faixa {faixa['range_index']}: rowcount "
                      "indisponível após o INSERT...SELECT — registrando 0.")
                copiadas = 0
            # UMA atualização de progresso por faixa (não há lotes no cliente)
            _exec_prog(prog,
                       "UPDATE dbo.etl_copy_exec_range "
                       "SET rows_copied = rows_copied + %s WHERE id = %s",
                       (copiadas, faixa["id"]))
            _exec_prog(prog,
                       "UPDATE dbo.etl_copy_exec "
                       "SET rows_copied = rows_copied + %s WHERE id = %s",
                       (copiadas, exec_id))
            resultado["rows"]   = copiadas
            resultado["status"] = "concluido"
            print(f"[COPY] Faixa {faixa['range_index']}: concluido "
                  f"({copiadas} linha(s), server-side)")
            return resultado

        if alvo["engine"] == bulk_copy.ENGINE_BCP:
            # ── bcp nativo: pipe `bcp queryout → bcp in` (C nas 2 pontas) ──
            # Fronteiras INLINE (o bcp não tem parâmetros); progresso por
            # linha "rows sent" do escritor; cancelamento termina o par;
            # o "N rows copied." final reconcilia o total da faixa.
            sql = _sql_da_faixa_bcp(job, faixa)

            def _on_lote(n):
                _exec_prog(prog,
                           "UPDATE dbo.etl_copy_exec_range "
                           "SET rows_copied = rows_copied + %s WHERE id = %s",
                           (n, faixa["id"]))
                _exec_prog(prog,
                           "UPDATE dbo.etl_copy_exec "
                           "SET rows_copied = rows_copied + %s WHERE id = %s",
                           (n, exec_id))

            r = bulk_copy.copiar_faixa_bcp(
                alvo["bcp"], sql,
                src_air, job["src_database"],
                dst_air, job["dst_database"],
                job["dst_schema"], job["dst_table"], job["batch_size"],
                on_lote=_on_lote,
                deve_cancelar=lambda: _status_exec(prog, exec_id) == "cancelando")
            resultado["rows"]     = r["rows"]
            resultado["status"]   = r["status"]
            resultado["erro_msg"] = r.get("erro_msg")
            print(f"[COPY] Faixa {faixa['range_index']}: {r['status']} "
                  f"({r['rows']} linha(s), bcp nativo)")
            return resultado

        src = bulk_copy.open_src_conn(src_air, job["src_database"])
        dst = bulk_copy.open_dst_conn(dst_air, job["dst_database"], alvo["engine"],
                                      charset=alvo.get("charset"))

        sql, params = _sql_da_faixa(job, faixa)

        cur = src.cursor()
        try:
            if params:
                cur.execute(sql, params)
            else:
                cur.execute(sql)

            lotes = copiadas = 0
            cancelada = False
            while True:
                rows = cur.fetchmany(job["batch_size"])
                if not rows:
                    break
                n = bulk_copy.bulk_write(dst, alvo, rows, job["batch_size"])
                copiadas += n
                lotes += 1
                # Progresso incremental atômico (best-effort)
                _exec_prog(prog,
                           "UPDATE dbo.etl_copy_exec_range "
                           "SET rows_copied = rows_copied + %s WHERE id = %s",
                           (n, faixa["id"]))
                _exec_prog(prog,
                           "UPDATE dbo.etl_copy_exec "
                           "SET rows_copied = rows_copied + %s WHERE id = %s",
                           (n, exec_id))
                if lotes % CHECK_CANCEL_A_CADA_LOTES == 0 \
                        and _status_exec(prog, exec_id) == "cancelando":
                    print(f"[COPY] Faixa {faixa['range_index']}: cancelamento "
                          f"solicitado — abortando após {copiadas} linha(s).")
                    cancelada = True
                    break
        finally:
            cur.close()

        resultado["rows"]   = copiadas
        resultado["status"] = "cancelado" if cancelada else "concluido"
        print(f"[COPY] Faixa {faixa['range_index']}: {resultado['status']} "
              f"({copiadas} linha(s), {lotes} lote(s))")
    except Exception as e:
        resultado["erro_msg"] = str(e)[:4000]
        print(f"[COPY] Faixa {faixa['range_index']} ERRO: {e}")
    finally:
        for c in (src, dst):
            try:
                if c is not None:
                    c.close()
            except Exception:
                pass
        # Desfecho da faixa (rows absoluto reconcilia os incrementos best-effort)
        try:
            if prog is not None:
                _exec_prog(prog,
                           "UPDATE dbo.etl_copy_exec_range "
                           "SET status=%s, rows_copied=%s, erro_msg=%s, "
                           "concluido_em=GETDATE() WHERE id=%s",
                           (resultado["status"], resultado["rows"],
                            resultado["erro_msg"], faixa["id"]))
        finally:
            try:
                if prog is not None:
                    prog.close()
            except Exception:
                pass
    return resultado


# ---------------------------------------------------------------------------
# Finalização / notificação
# ---------------------------------------------------------------------------

def _fmt_int(n) -> str:
    """Inteiro com separador de milhar pt-BR (1.234.567)."""
    return f"{int(n or 0):,}".replace(",", ".")


def _fmt_duracao(seg) -> str:
    seg = int(seg or 0)
    if seg >= 3600:
        return f"{seg // 3600}h {(seg % 3600) // 60}m {seg % 60}s"
    if seg >= 60:
        return f"{seg // 60}m {seg % 60}s"
    return f"{seg}s"


def _notificar(hook, job, status, rows, duracao_s, erro_msg):
    """INSERT best-effort em dbo.etl_notificacao para o solicitante."""
    matricula = job.get("matricula")
    if not matricula:
        return
    if status == "concluido":
        tipo, titulo = "success", "Cópia concluída"
        mensagem = f"{job['nome']}: {_fmt_int(rows)} linhas em {_fmt_duracao(duracao_s)}"
    elif status == "erro":
        tipo, titulo = "error", "Cópia falhou"
        mensagem = f"{job['nome']}: {erro_msg or 'erro na cópia'}"
    else:
        return  # cancelamento foi ação do próprio usuário — sem notificação
    try:
        hook.run(
            "INSERT INTO dbo.etl_notificacao (matricula, tipo, titulo, mensagem, link) "
            "VALUES (%s, %s, %s, %s, %s)",
            parameters=(str(matricula)[:64], tipo, titulo[:160],
                        mensagem[:800], "/copia-dados"),
        )
    except Exception as e:
        print(f"[COPY] Aviso: não foi possível notificar {matricula}: {e}")


# ---------------------------------------------------------------------------
# Task principal
# ---------------------------------------------------------------------------

def executar_copia(**context):
    conf = context["dag_run"].conf or {}
    exec_id = conf.get("exec_id")
    if not exec_id:
        raise ValueError(
            "Parâmetro 'exec_id' obrigatório no conf. Exemplo: {\"exec_id\": 123}")
    exec_id = int(exec_id)

    hook = _hook()
    job = _carregar_execucao(hook, exec_id)
    if job is None:
        raise ValueError(f"Execução {exec_id} não encontrada em dbo.etl_copy_exec")

    origem_rotulo = (f"{job['src_database']} (query SQL)" if job.get("src_query")
                     else f"{job['src_database']}.{job['src_schema']}.{job['src_table']}")
    print(f"[COPY] exec_id={exec_id} job='{job['nome']}' "
          f"{job['src_conn_id']}:{origem_rotulo}"
          f" → {job['dst_conn_id']}:{job['dst_database']}.{job['dst_schema']}.{job['dst_table']}")

    if job["exec_status"] == "cancelando":
        hook.run(
            "UPDATE dbo.etl_copy_exec SET status='cancelado', concluido_em=GETDATE() "
            "WHERE id = %s", parameters=(exec_id,))
        print("[COPY] Execução já estava 'cancelando' — finalizada como 'cancelado'.")
        return {"exec_id": exec_id, "status": "cancelado", "rows_copied": 0}

    if not job["select_sql"] or not job["count_sql"] or not job["dst_columns_json"]:
        raise ValueError(
            f"Job {job['job_id']} sem SQL compilado (select_sql/count_sql/"
            "dst_columns_json) — salve a cópia novamente pela tela.")

    t0 = time.monotonic()
    streams = max(1, min(8, int(job["streams"] or 4)))
    print(f"[COPY] streams={streams} batch_size={job['batch_size']}")
    hook.run(
        "UPDATE dbo.etl_copy_exec SET status='executando', iniciado_em=GETDATE(), "
        "streams=%s WHERE id = %s",
        parameters=(streams, exec_id))

    engine = None
    status_final = "erro"
    erro_msg = None
    rows_total = None
    resultados = []
    try:
        src_air = conn_resolver.get_conexao(job["src_conn_id"])
        dst_air = conn_resolver.get_conexao(job["dst_conn_id"])

        # Guarda de última linha (defesa em profundidade além da API/UI):
        # compara pelo HOST RESOLVIDO das connections — pega inclusive dois
        # conn_ids diferentes apontando para o mesmo servidor. Com
        # truncar_antes, origem == destino destruiria a tabela de origem.
        # MODO QUERY: não dá para saber estaticamente as tabelas lidas pela
        # query — a comparação é PULADA (fica só o aviso no log).
        def _norm(v):
            return str(v or "").strip().lower()
        if job.get("src_query"):
            print("[COPY] Aviso: fonte é query — garanta que ela não lê a "
                  "tabela de destino se usar truncar.")
        elif (
            _norm(src_air.host) == _norm(dst_air.host)
            and (src_air.port or 1433) == (dst_air.port or 1433)
            and _norm(job["src_database"]) == _norm(job["dst_database"])
            and _norm(job["src_schema"]) == _norm(job["dst_schema"])
            and _norm(job["src_table"]) == _norm(job["dst_table"])
        ):
            raise AirflowException(
                "Origem e destino resolvem para a MESMA tabela no mesmo "
                f"servidor ({src_air.host}:{src_air.port or 1433} / "
                f"{job['src_database']}.{job['src_schema']}.{job['src_table']}) "
                "— cópia abortada para não sobrescrever/truncar a própria origem.")

        # Engine: origem e destino no MESMO servidor (host:port das duas
        # connections, case-insensitive) → server-side, a cópia NÃO trafega
        # pelo worker; senão o melhor engine de escrita streaming disponível.
        if (_norm(src_air.host) == _norm(dst_air.host)
                and int(src_air.port or 1433) == int(dst_air.port or 1433)):
            engine = bulk_copy.ENGINE_SERVER_SIDE
            print("[COPY] Origem e destino no mesmo servidor — engine "
                  "server-side (INSERT...SELECT no próprio SQL Server)")
        else:
            engine = bulk_copy.resolve_engine()
            if engine == bulk_copy.ENGINE_BCP:
                # Probe de conexão/TLS do bcp nas DUAS pontas ANTES das
                # faixas: falha sistemática (binário quebrado, login, TLS/
                # certificado) → cai para o streaming pymssql NA EXECUÇÃO
                # INTEIRA, sem deixar a exec presa.
                motivo = bulk_copy.probe_bcp(
                    src_air, job["src_database"], dst_air, job["dst_database"])
                if motivo:
                    engine = bulk_copy.resolve_engine(incluir_bcp=False)
                    print(f"[COPY] Aviso: engine bcp_native inviável — "
                          f"{motivo} — usando {engine} na execução inteira.")
        print(f"[COPY] engine={engine}")
        hook.run("UPDATE dbo.etl_copy_exec SET engine=%s WHERE id = %s",
                 parameters=(engine, exec_id))

        src     = bulk_copy.open_src_conn(src_air, job["src_database"])
        dst_ctl = bulk_copy.open_src_conn(dst_air, job["dst_database"])
        try:
            if engine == bulk_copy.ENGINE_SERVER_SIDE:
                # Probe de viabilidade (best-effort): a conexão de origem
                # precisa enxergar o destino cross-database; senão cai para
                # o fluxo streaming normal, atualizando o engine gravado.
                motivo = _probe_server_side(src, job)
                if motivo:
                    engine = bulk_copy.resolve_engine()
                    print(f"[COPY] Aviso: engine server-side inviável — "
                          f"{motivo} — caindo para o fluxo streaming "
                          f"(engine={engine}).")
                    hook.run("UPDATE dbo.etl_copy_exec SET engine=%s WHERE id = %s",
                             parameters=(engine, exec_id))
            _preparar_destino(src, dst_ctl, job)
            if engine == bulk_copy.ENGINE_SERVER_SIDE:
                # Server-side: prepare_bulk_target e charset NÃO se aplicam
                # (nada trafega pelo cliente) — alvo mínimo com as colunas
                # do INSERT na ordem do SELECT compilado.
                alvo = {"engine": engine,
                        "columns": json.loads(job["dst_columns_json"])}
            else:
                # Alvo de escrita resolvido UMA vez por execução (ordinais/
                # column_ids do bulk_copy, charset do codepage do destino;
                # fallback por nome se necessário)
                alvo = bulk_copy.prepare_bulk_target(
                    dst_ctl, job["dst_schema"], job["dst_table"],
                    json.loads(job["dst_columns_json"]), engine,
                    charset_override=bulk_copy.charset_da_conexao(dst_air))
                if alvo.get("charset"):
                    print(f"[COPY] charset da carga bulk: {alvo['charset']}")
                if alvo["engine"] != engine:
                    print(f"[COPY] Engine ajustado {engine} → {alvo['engine']}: "
                          f"{alvo['motivo_fallback']}")
                    engine = alvo["engine"]
                    hook.run("UPDATE dbo.etl_copy_exec SET engine=%s WHERE id = %s",
                             parameters=(engine, exec_id))
            rows_total = _contar_origem(src, job)
            hook.run("UPDATE dbo.etl_copy_exec SET rows_total = %s WHERE id = %s",
                     parameters=(rows_total, exec_id))
            print(f"[COPY] rows_total={_fmt_int(rows_total)}")
            faixas = _montar_faixas(hook, src, job, exec_id, streams)
        finally:
            for c in (src, dst_ctl):
                try:
                    c.close()
                except Exception:
                    pass

        print(f"[COPY] {len(faixas)} faixa(s):")
        for f in faixas:
            rotulo = ("IS NULL" if f["is_null"]
                      else "única" if f["unica"]
                      else f"hash {f['fim']}" if f.get("hash")
                      else f"{f['ini']} → {f['fim']}"
                           + (" (fechada)" if f["ultima"] else ""))
            print(f"  #{f['range_index']}: {rotulo}")

        with ThreadPoolExecutor(max_workers=min(streams, len(faixas))) as pool:
            futuros = [pool.submit(_copiar_faixa, f, job, exec_id, alvo,
                                   src_air, dst_air) for f in faixas]
            for fut in as_completed(futuros):
                try:
                    resultados.append(fut.result())
                except Exception as e:  # defensivo — o worker já captura tudo
                    resultados.append({"range_index": None, "status": "erro",
                                       "rows": 0, "erro_msg": str(e)[:4000]})

        erros    = [r for r in resultados if r["status"] == "erro"]
        cancels  = [r for r in resultados if r["status"] == "cancelado"]
        if erros:
            status_final = "erro"
            erro_msg = erros[0].get("erro_msg") or "erro na cópia"
        elif cancels:
            status_final = "cancelado"
        else:
            status_final = "concluido"
    except Exception as e:
        status_final = "erro"
        erro_msg = str(e)[:4000]
        print(f"[COPY][ERRO] {e}")

    rows_copiadas = sum(int(r.get("rows") or 0) for r in resultados)
    duracao_s = int(time.monotonic() - t0)

    # Finalização — persiste SEMPRE, antes de qualquer raise
    try:
        hook.run(
            "UPDATE dbo.etl_copy_exec SET status=%s, rows_copied=%s, erro_msg=%s, "
            "concluido_em=GETDATE() WHERE id = %s",
            parameters=(status_final, rows_copiadas, erro_msg, exec_id))
    except Exception as e:
        print(f"[COPY] Aviso: falha ao gravar finalização da execução: {e}")

    _notificar(hook, job, status_final, rows_copiadas, duracao_s, erro_msg)

    print(f"[COPY] Finalizado: status={status_final} "
          f"rows={_fmt_int(rows_copiadas)} em {_fmt_duracao(duracao_s)}")

    if status_final == "erro":
        raise AirflowException(f"Cópia '{job['nome']}' falhou: {erro_msg}")

    return {
        "exec_id": exec_id, "copy_job_id": job["job_id"], "nome": job["nome"],
        "status": status_final, "engine": engine, "streams": streams,
        "rows_total": rows_total, "rows_copied": rows_copiadas,
        "duracao_s": duracao_s,
        "faixas": [{"range_index": r.get("range_index"), "status": r["status"],
                    "rows": int(r.get("rows") or 0)} for r in resultados],
    }


with DAG(
    dag_id=DAG_ID,
    default_args=default_args,
    description="Cópia de Dados — executa uma cópia registrada (conf: {\"exec_id\": N})",
    start_date=pendulum.datetime(2024, 1, 1, tz=LOCAL_TZ),
    schedule=None,
    catchup=False,
    tags=["etl", "copy"],
) as dag:

    PythonOperator(
        task_id="executar_copia",
        python_callable=executar_copia,
        do_xcom_push=True,
        execution_timeout=timedelta(hours=6),
    )
