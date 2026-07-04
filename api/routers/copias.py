"""api/routers/copias.py — Módulo "Cópia de Dados" (tabelas entre servidores MSSQL).

Endpoints:
  GET  /copias/conexoes                 — connections mssql do Airflow (proxy)
  GET  /copias/introspect/databases     — bancos de uma connection (direto/cache/airflow)
  GET  /copias/introspect/tables        — tabelas + nº de linhas de um banco
  GET  /copias/introspect/columns       — colunas de uma tabela + partição sugerida
  POST /copias/preview                  — amostra (TOP 50) do SELECT transformado
  GET  /copias                          — lista cópias salvas (com última execução)
  POST /copias                          — cria/atualiza cópia (compila via copy_sql)
  GET  /copias/{id}                     — detalhe completo
  DELETE /copias/{id}                   — soft delete (ativo=0)
  POST /copias/{id}/executar            — dispara a DAG etl_copy_exec (409 se
                                          houver exec ativa ou DAG pausada)
  GET  /copias/{id}/execucoes           — histórico de execuções
  GET  /copias/exec/{exec_id}           — progresso (polling da UI)
  POST /copias/exec/{exec_id}/cancelar  — cancela ('cancelado' direto se o
                                          dagRun não iniciou; senão 'cancelando')

Credenciais: só Airflow Connections (conn_id) — a API NUNCA vê senha. A
introspecção "direta" usa a credencial do PRÓPRIO app (padrão _swap_conn_str
de routers/jobs.py) com allowlist anti-SSRF; o fallback é RPC pela DAG
etl_copy_introspect com cache em dbo.etl_copy_catalogo. Tudo degrada
graciosamente se as tabelas da migration 052 ainda não existirem.
"""
from __future__ import annotations

import ast
import asyncio
import datetime as _dt
import json
import logging
import re
import time

from fastapi import APIRouter, Body, Depends, HTTPException

from db import get_db_conn
from deps import (
    PERM_EDITAR, PERM_EXECUTAR,
    get_current_user, require_perm,
)
from routers.airflow import get_airflow_client
# Helpers reusados de routers/jobs.py (crédito: padrão criado lá para o
# preview SQL de decisão): allowlist anti-SSRF de hosts MSSQL do Airflow,
# swap de SERVER/DATABASE na conn str do app, conexão pronta com READ
# UNCOMMITTED + timeout, serialização JSON-safe e timeout configurável.
from routers.jobs import (
    _get_preview_timeout_s, _json_safe, _list_mssql_hosts,
    _open_swapped_conn,
)
from services import copy_sql
from services.conn_native import abrir_conexao_nativa

log = logging.getLogger("orquestra-api")

router = APIRouter()

_CONN_ID_RE = re.compile(r"^[A-Za-z0-9_.\-]{1,100}$")
_STATUS_ATIVOS = ("pendente", "executando", "cancelando")
_INTROSPECT_DAG = "etl_copy_introspect"
_EXEC_DAG = "etl_copy_exec"
_CACHE_TTL_HORAS = 24
# Tipos elegíveis para sugestão de coluna de partição (PK numérica/data —
# mesmos tipos que a DAG sabe dividir em faixas; numeric = sinônimo de decimal).
_PARTICAO_TIPOS = {"int", "bigint", "decimal", "numeric", "date", "datetime"}
# Tipos TEXTO que a DAG também sabe dividir (fallback quando não há PK
# numérica/data): MIN/MAX hexadecimais (ex.: PK CHAR(32) de hash MD5) viram
# faixas lexicográficas sargáveis; demais textos, faixas por hash calculado.
_PARTICAO_TIPOS_TEXTO = {"char", "varchar", "nchar", "nvarchar"}


def _fmt_dt(v):
    if v is None:
        return None
    if hasattr(v, "strftime"):
        return v.strftime("%Y-%m-%d %H:%M:%S")
    return str(v)


def _valid_ident(nome: str) -> bool:
    try:
        copy_sql.quote_ident(nome)
        return True
    except ValueError:
        return False


def _origem_igual_destino(src_conn_id, src_database, src_schema, src_table,
                          dst_conn_id, dst_database, dst_schema, dst_table) -> bool:
    """True se origem e destino apontam para a MESMA tabela (comparação
    case-insensitive — collation padrão do SQL Server é CI). Copiar sobre a
    própria origem com truncar_antes truncaria a fonte dos dados."""
    def _n(v):
        return (v or "").strip().lower()
    return (_n(src_conn_id) == _n(dst_conn_id)
            and _n(src_database) == _n(dst_database)
            and _n(src_schema) == _n(dst_schema)
            and _n(src_table) == _n(dst_table))


_MSG_ORIGEM_DESTINO_IGUAIS = (
    "origem e destino apontam para a MESMA tabela (conexão, banco, schema e "
    "tabela iguais) — executar a cópia poderia truncar/sobrescrever a própria "
    "origem. Ajuste a conexão, o banco, o schema ou a tabela de destino.")


# ── Resolução de connection no Airflow (host/port) + allowlist ──────────────

def _conexao_da_tabela(conn_id: str) -> dict | None:
    """host/port de dbo.etl_conexao (fonte da verdade — migration 054), SEM a
    senha. None se ausente; degrada para None se a tabela não existir."""
    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute("SELECT host, port FROM dbo.etl_conexao WHERE conn_id = ?",
                    (conn_id,))
        row = cur.fetchone()
        cur.close(); conn.close()
        if row and (row[0] or "").strip():
            return {"host": row[0].strip(), "port": row[1], "schema": ""}
    except Exception as e:
        log.warning("copias: leitura de etl_conexao falhou (%s) — "
                    "fallback Airflow", e)
    return None


async def _resolver_conexao(conn_id: str) -> dict:
    """Resolve host/port/schema de uma conexão MSSQL: dbo.etl_conexao
    primeiro (Orquestra); fallback Airflow REST para conexões ainda não
    migradas (GET /api/v1/connections/{conn_id} — a senha NÃO vem na
    resposta). Levanta HTTPException clara se não existir/não for mssql."""
    if not _CONN_ID_RE.match(conn_id or ""):
        raise HTTPException(status_code=422, detail="conn_id inválido")
    local = _conexao_da_tabela(conn_id)
    if local is not None:
        return local
    try:
        async with get_airflow_client() as client:
            r = await client.get(f"/api/v1/connections/{conn_id}")
    except Exception as e:
        raise HTTPException(status_code=502,
                            detail=f"Erro ao consultar a connection no Airflow: {e}")
    if r.status_code == 404:
        raise HTTPException(status_code=404,
                            detail=f"connection '{conn_id}' não encontrada no Airflow")
    if not r.is_success:
        raise HTTPException(status_code=502, detail="Erro ao consultar o Airflow")
    data = r.json()
    if (data.get("conn_type") or "").lower() != "mssql":
        raise HTTPException(status_code=400,
                            detail=f"connection '{conn_id}' não é do tipo mssql")
    host = (data.get("host") or "").strip()
    if not host:
        raise HTTPException(status_code=400,
                            detail=f"connection '{conn_id}' está sem host cadastrado")
    return {"host": host, "port": data.get("port"), "schema": data.get("schema") or ""}


async def _server_da_conexao(conn_id: str) -> str:
    """host[,port] da connection, após checagem na allowlist anti-SSRF
    (host precisa ser host de alguma connection mssql — _list_mssql_hosts)."""
    info = await _resolver_conexao(conn_id)
    allowed = await _list_mssql_hosts()
    if info["host"] not in allowed:
        log.warning("copias: host %r (conn %s) fora da allowlist — recusado.",
                    info["host"], conn_id)
        raise HTTPException(
            status_code=400,
            detail=f"host '{info['host']}' não está cadastrado como conexão MSSQL")
    port = info.get("port")
    return f"{info['host']},{int(port)}" if port else info["host"]


async def _dag_exec_pausada() -> bool:
    """True se a DAG etl_copy_exec está pausada no Airflow (DAGs nascem
    pausadas neste deploy). Best-effort: se a consulta falhar por rede/Airflow
    fora, retorna False e o disparo segue normalmente."""
    try:
        async with get_airflow_client() as client:
            r = await client.get(f"/api/v1/dags/{_EXEC_DAG}")
        if r.is_success:
            return bool(r.json().get("is_paused"))
    except Exception as e:
        log.warning("copias: consulta da DAG %s falhou (%s) — seguindo com o "
                    "disparo mesmo assim", _EXEC_DAG, e)
    return False


async def _dag_run_iniciou(dag_run_id) -> bool:
    """True se o dagRun já saiu da fila (running/success/failed) — usado pelo
    cancelamento para decidir entre finalizar direto ('cancelado') ou pedir
    cancelamento à DAG ('cancelando').

    Sem dag_run_id registrado ou dagRun inexistente no Airflow (404) ⇒ False
    (nada rodou — pode finalizar direto). Falha de rede/resposta inesperada ⇒
    True (conservador: mantém o fluxo 'cancelando')."""
    if not dag_run_id:
        return False
    try:
        async with get_airflow_client() as client:
            r = await client.get(f"/api/v1/dags/{_EXEC_DAG}/dagRuns/{dag_run_id}")
        if r.status_code == 404:
            return False
        if r.is_success:
            estado = (r.json().get("state") or "").lower()
            return estado not in ("queued", "none", "no_status", "")
    except Exception as e:
        log.warning("copias: consulta do dagRun %s falhou (%s) — mantendo o "
                    "fluxo 'cancelando'", dag_run_id, e)
    return True


# ── Fallback RPC: introspecção via DAG etl_copy_introspect ───────────────────

def _cache_lookup(conn_id: str, database: str, payload_tipo: str, objeto: str):
    """Payload cacheado (< 24h) em dbo.etl_copy_catalogo, ou None. Degrada."""
    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute(
            "SELECT payload_json FROM dbo.etl_copy_catalogo "
            "WHERE conn_id=? AND database_name=? AND payload_tipo=? AND objeto=? "
            f"AND atualizado_em > DATEADD(hour, -{_CACHE_TTL_HORAS}, GETDATE())",
            (conn_id, database or "", payload_tipo, objeto or ""))
        row = cur.fetchone()
        cur.close(); conn.close()
        if row and row[0]:
            return json.loads(row[0])
    except Exception as e:
        log.warning("copias: leitura do cache etl_copy_catalogo falhou: %s", e)
    return None


def _cache_store(conn_id: str, database: str, payload_tipo: str, objeto: str,
                 payload: dict) -> None:
    """Grava/atualiza o cache (MERGE). Best-effort — nunca propaga erro."""
    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute(
            "MERGE dbo.etl_copy_catalogo AS t "
            "USING (SELECT ? AS conn_id, ? AS database_name, ? AS payload_tipo, "
            "              ? AS objeto) AS s "
            "ON t.conn_id = s.conn_id AND t.database_name = s.database_name "
            "   AND t.payload_tipo = s.payload_tipo AND t.objeto = s.objeto "
            "WHEN MATCHED THEN UPDATE SET payload_json = ?, atualizado_em = GETDATE() "
            "WHEN NOT MATCHED THEN INSERT "
            "  (conn_id, database_name, payload_tipo, objeto, payload_json) "
            "  VALUES (s.conn_id, s.database_name, s.payload_tipo, s.objeto, ?);",
            (conn_id, database or "", payload_tipo, objeto or "",
             json.dumps(payload, ensure_ascii=False),
             json.dumps(payload, ensure_ascii=False)))
        conn.commit(); cur.close(); conn.close()
    except Exception as e:
        log.warning("copias: gravação do cache etl_copy_catalogo falhou: %s", e)


_ACOES_SEM_CACHE = ("preview", "query_columns")  # resultado depende da query


def _parse_xcom_value(valor):
    """Payload (dict) do XCom lido pela REST API do Airflow — None se ilegível.

    A REST API devolve o value STRINGIFICADO: um dict retornado pela task vira
    ``str(dict)`` — repr Python com aspas SIMPLES (``{'databases': [...]}``,
    não é JSON; incidente 2026-07-04, primeira conexão a exercitar o ramo via
    DAG). Aceita, nesta ordem: dict nativo, JSON e repr Python via
    ``ast.literal_eval`` (só literais — seguro, nunca executa código)."""
    if isinstance(valor, dict):
        return valor
    if not isinstance(valor, str) or not valor.strip():
        return None
    try:
        out = json.loads(valor)
        return out if isinstance(out, dict) else None
    except (ValueError, TypeError):
        pass
    try:
        out = ast.literal_eval(valor)
        return out if isinstance(out, dict) else None
    except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
        return None


async def _introspect_via_dag(acao: str, conn_id: str, database: str = "",
                              schema: str = "", table: str = "",
                              select_sql: str | None = None,
                              src_query: str | None = None,
                              timeout_s: int = 90) -> tuple[dict, str]:
    """RPC de introspecção pela DAG etl_copy_introspect (worker conecta com a
    credencial da connection via BaseHook — a API nunca vê senha).

    1. Cache etl_copy_catalogo (< 24h) → retorna direto ("cache"), exceto
       preview/query_columns (dependem da query enviada).
    2. POST dagRun com conf; poll a cada 2s até success/failed (timeout → 504);
       lê o XCom return_value da task 'introspect'; grava cache (MERGE).
    Retorna (payload, via)."""
    objeto = f"{schema}.{table}" if acao == "columns" else ""
    if acao not in _ACOES_SEM_CACHE:
        cached = _cache_lookup(conn_id, database, acao, objeto)
        if cached is not None:
            return cached, "cache"

    conf: dict = {"acao": acao, "conn_id": conn_id}
    if database:
        conf["database"] = database
    if schema:
        conf["schema"] = schema
    if table:
        conf["table"] = table
    if select_sql:
        conf["select_sql"] = select_sql
    if src_query:
        conf["src_query"] = src_query
    run_id = f"introspect_{acao}_{_dt.datetime.now().strftime('%Y%m%dT%H%M%S%f')}"

    try:
        async with get_airflow_client() as client:
            r = await client.post(
                f"/api/v1/dags/{_INTROSPECT_DAG}/dagRuns",
                json={"dag_run_id": run_id, "conf": conf})
            if not r.is_success:
                raise HTTPException(
                    status_code=502,
                    detail=("Airflow recusou o dagRun de introspecção "
                            f"({r.status_code}) — verifique se a DAG "
                            f"{_INTROSPECT_DAG} existe e está ativa"))
            estado = ""
            limite = time.monotonic() + max(5, timeout_s)
            while time.monotonic() < limite:
                await asyncio.sleep(2)
                rs = await client.get(
                    f"/api/v1/dags/{_INTROSPECT_DAG}/dagRuns/{run_id}")
                if not rs.is_success:
                    continue
                estado = (rs.json().get("state") or "").lower()
                if estado in ("success", "failed"):
                    break
            if estado not in ("success", "failed"):
                raise HTTPException(
                    status_code=504,
                    detail=(f"A introspecção via Airflow excedeu {timeout_s}s — "
                            f"verifique se a DAG {_INTROSPECT_DAG} está ativa e "
                            "com worker disponível"))
            if estado == "failed":
                raise HTTPException(
                    status_code=502,
                    detail=("A introspecção falhou no Airflow — veja o log da "
                            f"task 'introspect' do run {run_id}"))
            rx = await client.get(
                f"/api/v1/dags/{_INTROSPECT_DAG}/dagRuns/{run_id}"
                "/taskInstances/introspect/xcomEntries/return_value")
            if not rx.is_success:
                raise HTTPException(
                    status_code=502,
                    detail="Não foi possível ler o resultado (XCom) da introspecção")
            valor = rx.json().get("value")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502,
                            detail=f"Erro na introspecção via Airflow: {e}")

    payload = _parse_xcom_value(valor)
    if not isinstance(payload, dict):
        raise HTTPException(status_code=502,
                            detail="Resposta inesperada da introspecção (XCom inválido)")
    if acao not in _ACOES_SEM_CACHE:
        _cache_store(conn_id, database, acao, objeto, payload)
    return payload, "airflow"


def _consulta_direta(server: str, database: str, sql: str, params=(),
                     timeout_s: int = 15, conn_id: str = ""):
    """Caminho rápido: roda um SELECT de catálogo DIRETO da API.

    Com ``conn_id`` de conexão NATIVA (dbo.etl_conexao), usa a credencial da
    PRÓPRIA conexão — a mesma das cargas: enxerga os mesmos objetos e o
    resultado é sempre FRESCO (sem o cache de 24h do RPC, que escondia
    tabelas recém-criadas). Sem conn_id (ou conexão legada), credencial do
    APP (_open_swapped_conn). Levanta HTTPException(400) em falha (o
    chamador decide se cai para o RPC via DAG)."""
    conn = cur = None
    if conn_id:
        try:
            par = abrir_conexao_nativa(conn_id, database, timeout_s)
            if par is not None:
                conn, cur = par
        except RuntimeError as e:
            raise HTTPException(status_code=400, detail=str(e))
    if conn is None:
        conn, cur = _open_swapped_conn(server, database, timeout_s)
    try:
        cur.execute(sql, params) if params else cur.execute(sql)
        rows = cur.fetchall()
        cur.close(); conn.close()
        return rows
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        raise HTTPException(status_code=400,
                            detail=f"Erro na consulta de catálogo: {e}")


# ── Introspecção (wizard) ────────────────────────────────────────────────────

@router.get("/copias/conexoes", tags=["copias"])
async def list_conexoes(_auth: dict = Depends(get_current_user)):
    """Connections MSSQL para os selects de origem/destino do wizard — UNIÃO
    de dbo.etl_conexao (fonte da verdade — migration 054) com as Airflow
    Connections legadas ainda não migradas (mesmo padrão de _list_mssql_hosts
    e do conn_list do Admin). Cada fonte degrada para vazio de forma
    independente; conn_id repetido fica com o registro do Orquestra."""
    conns: dict[str, dict] = {}
    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute("SELECT conn_id, host, port, descricao FROM dbo.etl_conexao "
                    "WHERE conn_type = 'mssql'")
        for r in cur.fetchall():
            cid = (r[0] or "").strip()
            if cid:
                conns[cid] = {"conn_id": cid, "host": (r[1] or "").strip(),
                              "port": r[2], "schema": "",
                              "description": r[3] or ""}
        cur.close(); conn.close()
    except Exception as e:
        log.warning("copias: leitura de etl_conexao falhou (%s) — listando "
                    "só as connections do Airflow", e)
    try:
        async with get_airflow_client() as client:
            r = await client.get("/api/v1/connections?limit=100")
            if r.is_success:
                for c in r.json().get("connections", []):
                    cid = c.get("connection_id")
                    if c.get("conn_type") == "mssql" and cid and cid not in conns:
                        conns[cid] = {"conn_id": cid, "host": c.get("host", ""),
                                      "port": c.get("port"),
                                      "schema": c.get("schema", ""),
                                      "description": c.get("description", "")}
    except Exception as e:
        log.warning("copias: erro ao listar conexões MSSQL do Airflow: %s", e)
    return {"connections": sorted(conns.values(),
                                  key=lambda c: c["conn_id"].lower())}


@router.get("/copias/introspect/databases", tags=["copias"])
async def introspect_databases(conn_id: str = "",
                               _auth: dict = Depends(require_perm(PERM_EDITAR))):
    """Bancos ONLINE e acessíveis do servidor da connection.

    Caminho rápido: resolve host/port via Airflow REST e conecta com a
    credencial do app em 'master' (query copiada de GET /jobs/databases).
    Fallback (falha de auth/timeout): RPC via DAG, com cache."""
    conn_id = (conn_id or "").strip()
    if not conn_id:
        raise HTTPException(status_code=422, detail="conn_id é obrigatório")
    server = await _server_da_conexao(conn_id)
    try:
        rows = _consulta_direta(
            server, "master",
            "SELECT d.name FROM sys.databases d "
            "WHERE d.state_desc = 'ONLINE' AND HAS_DBACCESS(d.name) = 1 "
            "ORDER BY d.name", conn_id=conn_id)
        return {"databases": [r[0] for r in rows], "via": "direto"}
    except HTTPException as e:
        log.info("copias: introspect databases direto falhou (%s) — fallback DAG",
                 e.detail)
    payload, via = await _introspect_via_dag("databases", conn_id)
    return {"databases": payload.get("databases", []), "via": via}


@router.get("/copias/introspect/tables", tags=["copias"])
async def introspect_tables(conn_id: str = "", database: str = "",
                            _auth: dict = Depends(require_perm(PERM_EDITAR))):
    """Tabelas do banco com nº de linhas (sys.partitions, heap/clustered)."""
    conn_id = (conn_id or "").strip()
    database = (database or "").strip()
    if not conn_id or not database:
        raise HTTPException(status_code=422, detail="conn_id e database são obrigatórios")
    if not _valid_ident(database):
        raise HTTPException(status_code=422, detail="database inválido")
    server = await _server_da_conexao(conn_id)
    try:
        rows = _consulta_direta(
            server, database,
            "SELECT s.name, t.name, SUM(p.rows) "
            "FROM sys.tables t "
            "JOIN sys.schemas s ON s.schema_id = t.schema_id "
            "JOIN sys.partitions p ON p.object_id = t.object_id "
            "  AND p.index_id IN (0, 1) "
            "GROUP BY s.name, t.name "
            "ORDER BY s.name, t.name", conn_id=conn_id)
        tables = [{"schema": r[0], "name": r[1], "rows": int(r[2] or 0)} for r in rows]
        return {"tables": tables, "via": "direto"}
    except HTTPException as e:
        log.info("copias: introspect tables direto falhou (%s) — fallback DAG", e.detail)
    payload, via = await _introspect_via_dag("tables", conn_id, database)
    return {"tables": payload.get("tables", []), "via": via}


def _particao_sugerida(columns: list[dict]):
    """Primeira coluna PK de tipo int/bigint/decimal/date/datetime; sem
    nenhuma, cai para a primeira PK de TEXTO (char/varchar/nchar/nvarchar —
    a DAG divide por faixas hex quando MIN/MAX são hexadecimais, senão por
    hash calculado). None quando não há PK elegível."""
    pk_texto = None
    for c in columns:
        if not c.get("is_pk"):
            continue
        tipo = str(c.get("type") or "").lower()
        if tipo in _PARTICAO_TIPOS:
            return c["name"]
        if pk_texto is None and tipo in _PARTICAO_TIPOS_TEXTO:
            pk_texto = c["name"]
    return pk_texto


@router.get("/copias/introspect/columns", tags=["copias"])
async def introspect_columns(conn_id: str = "", database: str = "",
                             schema: str = "dbo", table: str = "",
                             _auth: dict = Depends(require_perm(PERM_EDITAR))):
    """Colunas da tabela (tipo, tamanho, nullable, identity, PK) + sugestão
    de coluna de partição para o passo de Performance do wizard."""
    conn_id = (conn_id or "").strip()
    database = (database or "").strip()
    schema = (schema or "dbo").strip() or "dbo"
    table = (table or "").strip()
    if not conn_id or not database or not table:
        raise HTTPException(status_code=422,
                            detail="conn_id, database e table são obrigatórios")
    for rotulo, valor in (("database", database), ("schema", schema), ("table", table)):
        if not _valid_ident(valor):
            raise HTTPException(status_code=422, detail=f"{rotulo} inválido")
    server = await _server_da_conexao(conn_id)
    try:
        objeto = f"{copy_sql.quote_ident(schema)}.{copy_sql.quote_ident(table)}"
        rows = _consulta_direta(
            server, database,
            "SELECT c.name, tp.name, c.max_length, c.precision, c.scale, "
            "       c.is_nullable, c.is_identity, "
            "       CASE WHEN pk.column_id IS NOT NULL THEN 1 ELSE 0 END "
            "FROM sys.columns c "
            "JOIN sys.types tp ON tp.user_type_id = c.user_type_id "
            "LEFT JOIN ( "
            "    SELECT ic.object_id, ic.column_id "
            "    FROM sys.indexes i "
            "    JOIN sys.index_columns ic ON ic.object_id = i.object_id "
            "      AND ic.index_id = i.index_id "
            "    WHERE i.is_primary_key = 1 "
            ") pk ON pk.object_id = c.object_id AND pk.column_id = c.column_id "
            "WHERE c.object_id = OBJECT_ID(?) "
            "ORDER BY c.column_id",
            (objeto,), conn_id=conn_id)
        columns = [
            {"name": r[0], "type": r[1], "max_length": int(r[2] or 0),
             "precision": int(r[3] or 0), "scale": int(r[4] or 0),
             "is_nullable": bool(r[5]), "is_identity": bool(r[6]),
             "is_pk": bool(r[7])}
            for r in rows
        ]
        if columns:
            return {"columns": columns, "particao_sugerida": _particao_sugerida(columns),
                    "via": "direto"}
        # Tabela não encontrada com a credencial do APP: pode ser só falta de
        # visibilidade de catálogo — tenta o fallback via DAG (credencial da
        # connection) antes de responder 404 definitivo.
        log.info("copias: introspect columns direto não encontrou %s.%s em %s — "
                 "fallback DAG", schema, table, database)
    except HTTPException as e:
        log.info("copias: introspect columns direto falhou (%s) — fallback DAG", e.detail)
    payload, via = await _introspect_via_dag("columns", conn_id, database, schema, table)
    columns = payload.get("columns", [])
    if not columns:
        raise HTTPException(status_code=404,
                            detail=f"tabela {schema}.{table} não encontrada em {database}")
    return {"columns": columns,
            "particao_sugerida": payload.get("particao_sugerida")
            or _particao_sugerida(columns),
            "via": via}


def _tipo_basico_pyodbc(type_code):
    """Nome legível do tipo de uma coluna do cursor.description do pyodbc
    (type_code é a classe Python — str/int/Decimal/datetime/...)."""
    if type_code is None:
        return None
    return getattr(type_code, "__name__", None) or str(type_code)


@router.post("/copias/introspect/query-columns", tags=["copias"])
async def introspect_query_columns(body: dict = Body(default={}),
                                   _auth: dict = Depends(require_perm(PERM_EDITAR))):
    """Colunas do result set de uma query livre (MODO QUERY do wizard).

    Body: {src_conn_id, src_database, src_query}. Valida a query
    (validate_src_query → 422) e roda SELECT TOP 0 * FROM (<query>) AS _q
    pelo caminho rápido (cursor.description dá nome + tipo básico); se a
    CONEXÃO direta falhar, cai para o RPC via DAG (acao=query_columns).
    Erro de execução da query → 422 com a mensagem do SQL Server (útil para
    o usuário corrigir a query)."""
    src_conn_id = (body.get("src_conn_id") or "").strip()
    src_database = (body.get("src_database") or "").strip()
    if not src_conn_id or not src_database:
        raise HTTPException(status_code=422,
                            detail="src_conn_id e src_database são obrigatórios")
    try:
        src_query = copy_sql.validate_src_query(body.get("src_query"))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    server = await _server_da_conexao(src_conn_id)
    timeout_s = _get_preview_timeout_s()
    conn = cur = None
    try:
        par = abrir_conexao_nativa(src_conn_id, src_database, timeout_s)
        if par is not None:
            conn, cur = par
    except RuntimeError as e:
        log.info("copias: query-columns com credencial da conexão falhou (%s) "
                 "— tentando credencial do app", e)
    if conn is None:
        try:
            conn, cur = _open_swapped_conn(server, src_database, timeout_s)
        except HTTPException as e:
            log.info("copias: query-columns direto falhou ao conectar (%s) — "
                     "fallback DAG", e.detail)
    if conn is not None:
        try:
            cur.execute(f"SELECT TOP 0 * FROM (\n{src_query}\n) AS _q")
            columns = [{"name": d[0], "type": _tipo_basico_pyodbc(d[1])}
                       for d in (cur.description or [])]
            cur.close(); conn.close()
            return {"columns": columns, "via": "direto"}
        except Exception as e:
            try:
                conn.close()
            except Exception:
                pass
            # Query alcançou o servidor e falhou lá — mensagem do SQL Server
            # ajuda o usuário a corrigir (não é caso de fallback via DAG).
            raise HTTPException(status_code=422,
                                detail=f"A query falhou na origem: {e}")
    payload, via = await _introspect_via_dag(
        "query_columns", src_conn_id, src_database,
        src_query=src_query, timeout_s=90)
    return {"columns": payload.get("columns", []), "via": via}


@router.post("/copias/preview", tags=["copias"])
async def copias_preview(body: dict = Body(default={}),
                         _auth: dict = Depends(require_perm(PERM_EDITAR))):
    """Amostra de 50 linhas do SELECT transformado (passo Colunas do wizard).

    Body: {src_conn_id, src_database, src_schema, src_table, src_filtro,
    colunas, src_query}. Compila com copy_sql (422 se inválido) e roda
    SELECT TOP 50 * FROM (<select_sql>) AS _prev pelo caminho rápido; em falha
    de conexão/execução cai para o RPC via DAG (acao=preview).

    MODO QUERY (src_query presente): ignora schema/tabela/filtro/colunas e a
    amostra roda sobre a própria query (validada por validate_src_query)."""
    src_conn_id = (body.get("src_conn_id") or "").strip()
    src_database = (body.get("src_database") or "").strip()
    src_schema = (body.get("src_schema") or "dbo").strip() or "dbo"
    src_table = (body.get("src_table") or "").strip()
    src_query = (body.get("src_query") or "").strip()
    if not src_conn_id:
        raise HTTPException(status_code=422, detail="src_conn_id é obrigatório")
    if src_query:
        try:
            select_sql = copy_sql.validate_src_query(src_query)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
    else:
        try:
            comp = copy_sql.compile_job({
                "src_database": src_database, "src_schema": src_schema,
                "src_table": src_table, "src_filtro": body.get("src_filtro"),
                "colunas": body.get("colunas"),
            })
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
        select_sql = comp["select_sql"]

    server = await _server_da_conexao(src_conn_id)
    preview_sql = f"SELECT TOP 50 * FROM (\n{select_sql}\n) AS _prev"
    timeout_s = _get_preview_timeout_s()
    conn = cur = None
    try:
        par = abrir_conexao_nativa(src_conn_id, src_database, timeout_s)
        if par is not None:
            conn, cur = par
    except RuntimeError as e:
        log.info("copias: preview com credencial da conexão falhou (%s) — "
                 "tentando credencial do app", e)
    try:
        if conn is None:
            conn, cur = _open_swapped_conn(server, src_database, timeout_s)
        try:
            cur.execute(preview_sql)
            columns = [d[0] for d in (cur.description or [])]
            rows = [[_json_safe(v) for v in r] for r in cur.fetchall()]
            cur.close(); conn.close()
            return {"columns": columns, "rows": rows, "via": "direto"}
        except Exception as e:
            try:
                conn.close()
            except Exception:
                pass
            raise HTTPException(status_code=400,
                                detail=f"Erro ao executar a amostra: {e}")
    except HTTPException as e:
        log.info("copias: preview direto falhou (%s) — fallback DAG", e.detail)
    payload, via = await _introspect_via_dag(
        "preview", src_conn_id, src_database, src_schema, src_table,
        select_sql=select_sql, timeout_s=90)
    return {"columns": payload.get("columns", []),
            "rows": payload.get("rows", []), "via": via}


# ── Execuções (declaradas antes de /copias/{id} p/ não colidir na rota) ──────

@router.get("/copias/exec/{exec_id}", tags=["copias"])
def get_exec_progresso(exec_id: int, _auth: dict = Depends(get_current_user)):
    """Progresso de uma execução (polling da UI): totais, taxa, ETA e faixas."""
    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute(
            "SELECT e.id, e.copy_job_id, j.nome, e.status, e.rows_total, "
            "       e.rows_copied, e.engine, e.streams, e.erro_msg, "
            "       e.iniciado_em, e.concluido_em, e.dag_run_id "
            "FROM dbo.etl_copy_exec e "
            "LEFT JOIN dbo.etl_copy_job j ON j.id = e.copy_job_id "
            "WHERE e.id = ?", (exec_id,))
        row = cur.fetchone()
        if not row:
            cur.close(); conn.close()
            raise HTTPException(status_code=404, detail="Execução não encontrada")
        ranges = []
        try:
            cur.execute(
                "SELECT range_index, valor_ini, valor_fim, status, rows_copied, "
                "       erro_msg, iniciado_em, concluido_em "
                "FROM dbo.etl_copy_exec_range WHERE exec_id = ? "
                "ORDER BY range_index", (exec_id,))
            ranges = [
                {"range_index": r[0], "valor_ini": r[1], "valor_fim": r[2],
                 "status": r[3], "rows_copied": int(r[4] or 0), "erro_msg": r[5],
                 "iniciado_em": _fmt_dt(r[6]), "concluido_em": _fmt_dt(r[7])}
                for r in cur.fetchall()
            ]
        except Exception:
            ranges = []
        cur.close(); conn.close()
    except HTTPException:
        raise
    except Exception as e:
        log.warning("get_exec_progresso degradou: %s", e)
        raise HTTPException(status_code=404, detail="Execução não encontrada")

    rows_total = int(row[4]) if row[4] is not None else None
    rows_copied = int(row[5] or 0)
    iniciado_em, concluido_em = row[9], row[10]
    rate = None
    eta_s = None
    if iniciado_em is not None:
        fim = concluido_em or _dt.datetime.now()
        try:
            segundos = max(1, int((fim - iniciado_em).total_seconds()))
            rate = round(rows_copied / segundos, 1)
            if rows_total and rate > 0 and concluido_em is None:
                eta_s = int(max(0, rows_total - rows_copied) / rate)
        except Exception:
            rate = None
    return {
        "id": int(row[0]), "copy_job_id": int(row[1]) if row[1] is not None else None,
        "nome": row[2], "status": row[3], "rows_total": rows_total,
        "rows_copied": rows_copied, "engine": row[6],
        "streams": int(row[7]) if row[7] is not None else None,
        "erro_msg": row[8], "iniciado_em": _fmt_dt(iniciado_em),
        "concluido_em": _fmt_dt(concluido_em), "dag_run_id": row[11],
        "rate_rows_s": rate, "eta_s": eta_s, "ranges": ranges,
    }


@router.post("/copias/exec/{exec_id}/cancelar", tags=["copias"])
async def cancelar_exec(exec_id: int,
                        _auth: dict = Depends(require_perm(PERM_EXECUTAR))):
    """Pede o cancelamento. Execução 'pendente' cujo dagRun ainda não iniciou
    (queued/no_status no Airflow, ou nunca disparado) é finalizada DIRETO como
    'cancelado' (concluido_em=GETDATE()) — não há DAG rodando para observar.
    Nos demais casos ativos, status → 'cancelando' (a DAG observa e finaliza
    como 'cancelado'). Se a execução já terminou, apenas devolve o status."""
    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute("SELECT status, dag_run_id FROM dbo.etl_copy_exec WHERE id = ?",
                    (exec_id,))
        row = cur.fetchone()
        if not row:
            cur.close(); conn.close()
            raise HTTPException(status_code=404, detail="Execução não encontrada")
        status, dag_run_id = row[0], row[1]
        cur.close(); conn.close()
    except HTTPException:
        raise
    except Exception as e:
        log.warning("cancelar_exec falhou: %s", e)
        raise HTTPException(
            status_code=400,
            detail="Não foi possível cancelar (tabelas da migration 052 ausentes?)")

    if status not in ("pendente", "executando"):
        return {"id": exec_id, "status": status}

    finalizar_direto = (status == "pendente"
                        and not await _dag_run_iniciou(dag_run_id))
    try:
        conn = get_db_conn(); cur = conn.cursor()
        if finalizar_direto:
            # Só finaliza se AINDA estiver 'pendente' (a DAG pode ter começado
            # entre a leitura e o UPDATE); senão cai no fluxo 'cancelando'.
            cur.execute(
                "UPDATE dbo.etl_copy_exec SET status = 'cancelado', "
                "concluido_em = GETDATE() WHERE id = ? AND status = 'pendente'",
                (exec_id,))
            status = "cancelado" if cur.rowcount else "cancelando"
        else:
            status = "cancelando"
        if status == "cancelando":
            cur.execute(
                "UPDATE dbo.etl_copy_exec SET status = 'cancelando' "
                "WHERE id = ? AND status IN ('pendente', 'executando')",
                (exec_id,))
        conn.commit(); cur.close(); conn.close()
        return {"id": exec_id, "status": status}
    except Exception as e:
        log.warning("cancelar_exec falhou: %s", e)
        raise HTTPException(
            status_code=400,
            detail="Não foi possível cancelar (tabelas da migration 052 ausentes?)")


# ── CRUD de cópias ───────────────────────────────────────────────────────────

@router.get("/copias", tags=["copias"])
def list_copias(_auth: dict = Depends(get_current_user)):
    """Lista as cópias salvas (ativas) com a última execução de cada uma —
    ``usa_query`` indica o modo query (fonte = src_query, migration 053).
    Degrada para lista vazia se as tabelas da migration 052 não existirem."""
    sql_base = (
        "SELECT j.id, j.nome, j.src_conn_id, j.src_database, j.src_schema, "
        "       j.src_table, j.dst_conn_id, j.dst_database, j.dst_schema, "
        "       j.dst_table, j.criar_tabela, j.truncar_antes, j.particao_coluna, "
        "       j.streams, j.batch_size, j.criado_por, j.criado_em, "
        "       j.atualizado_em, "
        "       e.id, e.status, e.rows_copied, e.rows_total, e.criado_em{extra} "
        "FROM dbo.etl_copy_job j "
        "OUTER APPLY (SELECT TOP 1 id, status, rows_copied, rows_total, criado_em "
        "             FROM dbo.etl_copy_exec WHERE copy_job_id = j.id "
        "             ORDER BY id DESC) e "
        "WHERE j.ativo = 1 ORDER BY j.nome")
    try:
        conn = get_db_conn(); cur = conn.cursor()
        try:
            cur.execute(sql_base.format(
                extra=", CASE WHEN j.src_query IS NOT NULL "
                      "AND LEN(j.src_query) > 0 THEN 1 ELSE 0 END"))
        except Exception as e:
            # Ambiente sem a 053: refaz sem a coluna (usa_query = False)
            log.warning("list_copias: coluna src_query indisponível "
                        "(migration 053 aplicada?): %s", e)
            cur.execute(sql_base.format(extra=""))
        data = []
        for r in cur.fetchall():
            ultima = None
            if r[18] is not None:
                ultima = {"id": int(r[18]), "status": r[19],
                          "rows_copied": int(r[20] or 0),
                          "rows_total": int(r[21]) if r[21] is not None else None,
                          "criado_em": _fmt_dt(r[22])}
            data.append({
                "id": int(r[0]), "nome": r[1],
                "src_conn_id": r[2], "src_database": r[3], "src_schema": r[4],
                "src_table": r[5], "dst_conn_id": r[6], "dst_database": r[7],
                "dst_schema": r[8], "dst_table": r[9],
                "criar_tabela": bool(r[10]), "truncar_antes": bool(r[11]),
                "particao_coluna": r[12], "streams": int(r[13] or 0),
                "batch_size": int(r[14] or 0), "criado_por": r[15],
                "criado_em": _fmt_dt(r[16]), "atualizado_em": _fmt_dt(r[17]),
                "usa_query": bool(r[23]) if len(r) > 23 else False,
                "ultima_exec": ultima,
            })
        cur.close(); conn.close()
        return {"data": data}
    except Exception as e:
        log.warning("list_copias degradou (migration 052 aplicada?): %s", e)
        return {"data": []}


@router.post("/copias", tags=["copias"])
def save_copia(body: dict = Body(default={}),
               _auth: dict = Depends(require_perm(PERM_EDITAR))):
    """Cria ou atualiza (body com ``id``) uma cópia. Valida tudo, compila as
    transformações com copy_sql e persiste select_sql/count_sql/dst_columns_json.

    MODO QUERY (``src_query`` presente): a fonte é a query livre — src_table
    pode vir vazio, o filtro do wizard é zerado, transforms devem ser nulos
    (compile_job valida) e a checagem estática origem==destino de TABELA é
    pulada (não dá para saber as tabelas lidas pela query — a DAG loga aviso)."""
    copia_id = body.get("id")
    nome = (body.get("nome") or "").strip()
    src_conn_id = (body.get("src_conn_id") or "").strip()
    dst_conn_id = (body.get("dst_conn_id") or "").strip()
    src_database = (body.get("src_database") or "").strip()
    dst_database = (body.get("dst_database") or "").strip()
    src_schema = (body.get("src_schema") or "dbo").strip() or "dbo"
    dst_schema = (body.get("dst_schema") or "dbo").strip() or "dbo"
    src_table = (body.get("src_table") or "").strip()
    dst_table = (body.get("dst_table") or "").strip()
    src_filtro = (body.get("src_filtro") or "").strip() or None
    src_query = (body.get("src_query") or "").strip() or None
    particao_coluna = (body.get("particao_coluna") or "").strip() or None
    criar_tabela = bool(body.get("criar_tabela", False))
    truncar_antes = bool(body.get("truncar_antes", False))
    colunas = body.get("colunas")

    if src_query:
        src_filtro = None  # modo query: o filtro do wizard é ignorado/zerado

    if not nome:
        raise HTTPException(status_code=422, detail="nome é obrigatório")
    if len(nome) > 200:
        raise HTTPException(status_code=422, detail="nome excede 200 caracteres")
    for rotulo, cid in (("src_conn_id", src_conn_id), ("dst_conn_id", dst_conn_id)):
        if not cid:
            raise HTTPException(status_code=422, detail=f"{rotulo} é obrigatório")
        if not _CONN_ID_RE.match(cid):
            raise HTTPException(status_code=422, detail=f"{rotulo} inválido")
    campos_ident = [("src_database", src_database), ("src_schema", src_schema),
                    ("dst_database", dst_database), ("dst_schema", dst_schema),
                    ("dst_table", dst_table)]
    if not src_query:  # modo query: src_table pode vir vazio (não é usado no SQL)
        campos_ident.insert(2, ("src_table", src_table))
    for rotulo, valor in campos_ident:
        if not valor:
            raise HTTPException(status_code=422, detail=f"{rotulo} é obrigatório")
        if not _valid_ident(valor):
            raise HTTPException(status_code=422, detail=f"{rotulo} inválido")
    if particao_coluna and not _valid_ident(particao_coluna):
        raise HTTPException(status_code=422, detail="particao_coluna inválida")
    # Origem == destino: no modo query não dá para comparar tabelas
    # estaticamente — a guarda fica por conta do aviso na UI e do log da DAG.
    if not src_query and _origem_igual_destino(
            src_conn_id, src_database, src_schema, src_table,
            dst_conn_id, dst_database, dst_schema, dst_table):
        raise HTTPException(status_code=422, detail=_MSG_ORIGEM_DESTINO_IGUAIS)
    try:
        streams = int(body.get("streams", 4))
        batch_size = int(body.get("batch_size", 50000))
    except (ValueError, TypeError):
        raise HTTPException(status_code=422, detail="streams e batch_size devem ser inteiros")
    if not 1 <= streams <= 8:
        raise HTTPException(status_code=422, detail="streams deve estar entre 1 e 8")
    if not 1000 <= batch_size <= 200000:
        raise HTTPException(status_code=422,
                            detail="batch_size deve estar entre 1000 e 200000")
    if not isinstance(colunas, list) or not colunas:
        raise HTTPException(status_code=422, detail="colunas (lista não vazia) é obrigatório")

    try:
        comp = copy_sql.compile_job({
            "src_database": src_database, "src_schema": src_schema,
            "src_table": src_table, "src_filtro": src_filtro,
            "src_query": src_query, "colunas": colunas,
        })
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    # particao_coluna referencia o nome de DESTINO (alias do select compilado)
    # — a DAG aplica as faixas sobre os aliases da subquery (<select_sql>).
    if particao_coluna:
        dst_lower = {c.lower() for c in comp["dst_columns"]}
        if particao_coluna.lower() not in dst_lower:
            raise HTTPException(
                status_code=422,
                detail=(f"particao_coluna '{particao_coluna}' não está entre as "
                        "colunas de destino incluídas na cópia — use o nome de "
                        "destino de uma coluna incluída "
                        f"({', '.join(comp['dst_columns'])})"))

    matricula = (_auth.get("matricula") or "").strip() or None
    colunas_json = json.dumps({"colunas": colunas}, ensure_ascii=False)
    dst_columns_json = json.dumps(comp["dst_columns"], ensure_ascii=False)

    try:
        conn = get_db_conn(); cur = conn.cursor()
        # Nome único entre as cópias ATIVAS (índice filtrado UX_copy_job_nome
        # WHERE ativo = 1 — validamos antes p/ erro claro; soft delete libera o nome)
        if copia_id is not None:
            cur.execute("SELECT id FROM dbo.etl_copy_job "
                        "WHERE nome = ? AND ativo = 1 AND id <> ?",
                        (nome, int(copia_id)))
        else:
            cur.execute("SELECT id FROM dbo.etl_copy_job WHERE nome = ? AND ativo = 1",
                        (nome,))
        if cur.fetchone():
            cur.close(); conn.close()
            raise HTTPException(status_code=422,
                                detail=f"já existe uma cópia ativa com o nome '{nome}'")

        # Persistência com a coluna src_query (migration 053). Degradação
        # graciosa (padrão do repo): se o UPDATE/INSERT com a coluna falhar e a
        # cópia NÃO usa query, refaz sem a coluna; se usa query, erro claro.
        _MSG_SEM_053 = ("Não foi possível salvar a cópia com query SQL como "
                        "fonte — a coluna src_query não existe (aplique a "
                        "migration 053)")
        if copia_id is not None:
            cur.execute("SELECT id FROM dbo.etl_copy_job WHERE id = ?", (int(copia_id),))
            if not cur.fetchone():
                cur.close(); conn.close()
                raise HTTPException(status_code=404, detail="Cópia não encontrada")
            upd_ini = ("UPDATE dbo.etl_copy_job SET nome=?, src_conn_id=?, "
                       "src_database=?, src_schema=?, src_table=?, src_filtro=?, ")
            upd_fim = ("dst_conn_id=?, dst_database=?, "
                       "dst_schema=?, dst_table=?, criar_tabela=?, truncar_antes=?, "
                       "particao_coluna=?, streams=?, batch_size=?, colunas_json=?, "
                       "select_sql=?, count_sql=?, dst_columns_json=?, ativo=1, "
                       "atualizado_por=?, atualizado_em=GETDATE() WHERE id=?")
            params_ini = (nome, src_conn_id, src_database, src_schema, src_table,
                          src_filtro)
            params_fim = (dst_conn_id, dst_database, dst_schema, dst_table,
                          int(criar_tabela), int(truncar_antes), particao_coluna,
                          streams, batch_size, colunas_json, comp["select_sql"],
                          comp["count_sql"], dst_columns_json, matricula,
                          int(copia_id))
            try:
                cur.execute(upd_ini + "src_query=?, " + upd_fim,
                            params_ini + (src_query,) + params_fim)
            except Exception as e:
                if src_query is not None:
                    log.warning("save_copia: coluna src_query indisponível? %s", e)
                    cur.close(); conn.close()
                    raise HTTPException(status_code=400, detail=_MSG_SEM_053)
                cur.execute(upd_ini + upd_fim, params_ini + params_fim)
            novo_id = int(copia_id)
        else:
            ins_cols = ("nome, src_conn_id, src_database, src_schema, src_table, "
                        "src_filtro, dst_conn_id, dst_database, dst_schema, "
                        "dst_table, criar_tabela, truncar_antes, particao_coluna, "
                        "streams, batch_size, colunas_json, select_sql, count_sql, "
                        "dst_columns_json, criado_por")
            params = (nome, src_conn_id, src_database, src_schema, src_table,
                      src_filtro, dst_conn_id, dst_database, dst_schema, dst_table,
                      int(criar_tabela), int(truncar_antes), particao_coluna,
                      streams, batch_size, colunas_json, comp["select_sql"],
                      comp["count_sql"], dst_columns_json, matricula)
            try:
                cur.execute(
                    f"INSERT INTO dbo.etl_copy_job ({ins_cols}, src_query) "
                    "OUTPUT INSERTED.id "
                    f"VALUES ({', '.join(['?'] * (len(params) + 1))})",
                    params + (src_query,))
            except Exception as e:
                if src_query is not None:
                    log.warning("save_copia: coluna src_query indisponível? %s", e)
                    cur.close(); conn.close()
                    raise HTTPException(status_code=400, detail=_MSG_SEM_053)
                cur.execute(
                    f"INSERT INTO dbo.etl_copy_job ({ins_cols}) "
                    "OUTPUT INSERTED.id "
                    f"VALUES ({', '.join(['?'] * len(params))})",
                    params)
            novo_id = int(cur.fetchone()[0])
        conn.commit(); cur.close(); conn.close()
    except HTTPException:
        raise
    except Exception as e:
        log.warning("save_copia falhou: %s", e)
        raise HTTPException(
            status_code=400,
            detail="Não foi possível salvar a cópia (tabelas da migration 052 ausentes?)")
    return {"id": novo_id, "nome": nome, "select_sql": comp["select_sql"],
            "count_sql": comp["count_sql"], "dst_columns": comp["dst_columns"]}


@router.get("/copias/{copia_id}", tags=["copias"])
def get_copia(copia_id: int, _auth: dict = Depends(get_current_user)):
    """Detalhe completo de uma cópia (inclui colunas_json parseado e
    src_query — lida com degradação graciosa em ambiente sem a 053)."""
    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute(
            "SELECT id, nome, src_conn_id, src_database, src_schema, src_table, "
            "       src_filtro, dst_conn_id, dst_database, dst_schema, dst_table, "
            "       criar_tabela, truncar_antes, particao_coluna, streams, batch_size, "
            "       colunas_json, select_sql, count_sql, dst_columns_json, ativo, "
            "       criado_por, criado_em, atualizado_por, atualizado_em "
            "FROM dbo.etl_copy_job WHERE id = ?", (copia_id,))
        r = cur.fetchone()
        # src_query (migration 053) em consulta separada: ambiente sem a
        # coluna degrada para None sem perder o restante do detalhe.
        src_query = None
        if r:
            try:
                cur.execute("SELECT src_query FROM dbo.etl_copy_job WHERE id = ?",
                            (copia_id,))
                row_q = cur.fetchone()
                src_query = row_q[0] if row_q else None
            except Exception as e:
                log.warning("get_copia: coluna src_query indisponível "
                            "(migration 053 aplicada?): %s", e)
        cur.close(); conn.close()
    except Exception as e:
        log.warning("get_copia degradou: %s", e)
        raise HTTPException(status_code=404, detail="Cópia não encontrada")
    if not r:
        raise HTTPException(status_code=404, detail="Cópia não encontrada")

    def _parse(raw, default):
        try:
            return json.loads(raw) if raw else default
        except (ValueError, TypeError):
            return default

    colunas_doc = _parse(r[16], {})
    colunas = colunas_doc.get("colunas", []) if isinstance(colunas_doc, dict) else []
    return {
        "id": int(r[0]), "nome": r[1], "src_conn_id": r[2], "src_database": r[3],
        "src_schema": r[4], "src_table": r[5], "src_filtro": r[6],
        "src_query": src_query,
        "dst_conn_id": r[7], "dst_database": r[8], "dst_schema": r[9],
        "dst_table": r[10], "criar_tabela": bool(r[11]), "truncar_antes": bool(r[12]),
        "particao_coluna": r[13], "streams": int(r[14] or 0),
        "batch_size": int(r[15] or 0), "colunas": colunas,
        "select_sql": r[17], "count_sql": r[18],
        "dst_columns": _parse(r[19], []), "ativo": bool(r[20]),
        "criado_por": r[21], "criado_em": _fmt_dt(r[22]),
        "atualizado_por": r[23], "atualizado_em": _fmt_dt(r[24]),
    }


@router.delete("/copias/{copia_id}", tags=["copias"])
def delete_copia(copia_id: int, _auth: dict = Depends(require_perm(PERM_EDITAR))):
    """Soft delete (ativo=0) — preserva o histórico de execuções."""
    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute("UPDATE dbo.etl_copy_job SET ativo = 0, atualizado_por = ?, "
                    "atualizado_em = GETDATE() WHERE id = ?",
                    ((_auth.get("matricula") or "").strip() or None, copia_id))
        alterados = cur.rowcount
        conn.commit(); cur.close(); conn.close()
    except Exception as e:
        log.warning("delete_copia falhou: %s", e)
        raise HTTPException(
            status_code=400,
            detail="Não foi possível excluir (tabelas da migration 052 ausentes?)")
    if not alterados:
        raise HTTPException(status_code=404, detail="Cópia não encontrada")
    return {"ok": True, "id": copia_id}


@router.get("/copias/{copia_id}/execucoes", tags=["copias"])
def list_execucoes_copia(copia_id: int, limit: int = 20, offset: int = 0,
                         _auth: dict = Depends(get_current_user)):
    """Histórico paginado de execuções de uma cópia. Degrada para vazio."""
    limit = min(100, max(1, limit))
    offset = max(0, offset)
    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM dbo.etl_copy_exec WHERE copy_job_id = ?",
                    (copia_id,))
        total = int(cur.fetchone()[0] or 0)
        cur.execute(
            "SELECT id, dag_run_id, status, rows_total, rows_copied, streams, "
            "       engine, erro_msg, matricula, iniciado_em, concluido_em, criado_em "
            "FROM dbo.etl_copy_exec WHERE copy_job_id = ? "
            "ORDER BY id DESC OFFSET ? ROWS FETCH NEXT ? ROWS ONLY",
            (copia_id, offset, limit))
        data = []
        for r in cur.fetchall():
            duracao_s = None
            if r[9] is not None and r[10] is not None:
                try:
                    duracao_s = int((r[10] - r[9]).total_seconds())
                except Exception:
                    duracao_s = None
            data.append({
                "id": int(r[0]), "dag_run_id": r[1], "status": r[2],
                "rows_total": int(r[3]) if r[3] is not None else None,
                "rows_copied": int(r[4] or 0),
                "streams": int(r[5]) if r[5] is not None else None,
                "engine": r[6], "erro_msg": r[7], "matricula": r[8],
                "iniciado_em": _fmt_dt(r[9]), "concluido_em": _fmt_dt(r[10]),
                "criado_em": _fmt_dt(r[11]), "duracao_s": duracao_s,
            })
        cur.close(); conn.close()
        return {"total": total, "offset": offset, "limit": limit, "data": data}
    except Exception as e:
        log.warning("list_execucoes_copia degradou: %s", e)
        return {"total": 0, "offset": offset, "limit": limit, "data": []}


@router.post("/copias/{copia_id}/executar", tags=["copias"])
async def executar_copia(copia_id: int,
                         _auth: dict = Depends(require_perm(PERM_EXECUTAR))):
    """Dispara a cópia: cria etl_copy_exec (pendente) e aciona a DAG
    etl_copy_exec com conf {"exec_id": N}. 409 se já houver execução ativa
    (guarda atômica: INSERT ... SELECT ... WHERE NOT EXISTS) ou se a DAG
    estiver pausada no Airflow; 422 se origem e destino forem a mesma tabela."""
    matricula = (_auth.get("matricula") or "").strip() or None
    sql_job = ("SELECT id, nome, src_conn_id, src_database, src_schema, "
               "       src_table, dst_conn_id, dst_database, dst_schema, "
               "       dst_table{extra} "
               "FROM dbo.etl_copy_job WHERE id = ? AND ativo = 1")
    try:
        conn = get_db_conn(); cur = conn.cursor()
        try:
            cur.execute(sql_job.format(extra=", src_query"), (copia_id,))
            job = cur.fetchone()
        except Exception as e:
            # Ambiente sem a migration 053: refaz sem a coluna src_query
            log.warning("executar_copia: coluna src_query indisponível "
                        "(migration 053 aplicada?): %s", e)
            cur.execute(sql_job.format(extra=""), (copia_id,))
            job = cur.fetchone()
        cur.close(); conn.close()
    except Exception as e:
        log.warning("executar_copia falhou ao carregar a cópia: %s", e)
        raise HTTPException(
            status_code=400,
            detail="Não foi possível carregar a cópia (tabelas da migration 052 ausentes?)")
    if not job:
        raise HTTPException(status_code=404, detail="Cópia não encontrada")
    # Modo query: não dá para comparar tabelas estaticamente (a DAG loga o
    # aviso; a guarda por host da DAG também é pulada nesse modo).
    usa_query = len(job) > 10 and bool((job[10] or "").strip())
    if not usa_query and _origem_igual_destino(job[2], job[3], job[4], job[5],
                                               job[6], job[7], job[8], job[9]):
        raise HTTPException(status_code=422, detail=_MSG_ORIGEM_DESTINO_IGUAIS)

    # DAG pausada não consome o dagRun (fica 'pendente' para sempre) — avisa
    # antes de disparar. Best-effort: falha de rede não bloqueia o disparo.
    if await _dag_exec_pausada():
        raise HTTPException(
            status_code=409,
            detail=(f"A DAG {_EXEC_DAG} está pausada no Airflow — despause-a "
                    "na tela de DAGs do Airflow antes de executar (as DAGs "
                    "nascem pausadas neste deploy)"))

    try:
        conn = get_db_conn(); cur = conn.cursor()
        # Guarda atômica contra corrida: o INSERT só acontece se NÃO existir
        # execução ativa do mesmo job — tudo NA MESMA instrução (UPDLOCK/
        # HOLDLOCK seguram inserts concorrentes). 0 linhas inseridas ⇒ 409.
        cur.execute(
            "INSERT INTO dbo.etl_copy_exec (copy_job_id, status, matricula) "
            "OUTPUT INSERTED.id "
            "SELECT ?, 'pendente', ? "
            "WHERE NOT EXISTS (SELECT 1 FROM dbo.etl_copy_exec "
            "                  WITH (UPDLOCK, HOLDLOCK) "
            "                  WHERE copy_job_id = ? AND status IN (?, ?, ?))",
            (copia_id, matricula, copia_id, *_STATUS_ATIVOS))
        inserted = cur.fetchone()
        if not inserted:
            cur.execute(
                "SELECT TOP 1 id, status FROM dbo.etl_copy_exec "
                "WHERE copy_job_id = ? AND status IN (?, ?, ?) ORDER BY id DESC",
                (copia_id, *_STATUS_ATIVOS))
            ativa = cur.fetchone()
            cur.close(); conn.close()
            detalhe = ("Já existe uma execução ativa "
                       f"(id {int(ativa[0])}, status '{ativa[1]}') para esta cópia"
                       if ativa else "Já existe uma execução ativa para esta cópia")
            raise HTTPException(status_code=409, detail=detalhe)
        exec_id = int(inserted[0])
        conn.commit(); cur.close(); conn.close()
    except HTTPException:
        raise
    except Exception as e:
        log.warning("executar_copia falhou ao criar a execução: %s", e)
        raise HTTPException(
            status_code=400,
            detail="Não foi possível criar a execução (tabelas da migration 052 ausentes?)")

    dag_run_id = f"copy_{exec_id}_{_dt.datetime.now().strftime('%Y%m%dT%H%M%S')}"
    erro_airflow = None
    try:
        async with get_airflow_client() as client:
            r = await client.post(
                f"/api/v1/dags/{_EXEC_DAG}/dagRuns",
                json={"dag_run_id": dag_run_id, "conf": {"exec_id": exec_id}})
            if not r.is_success:
                erro_airflow = f"Airflow respondeu {r.status_code}: {r.text[:300]}"
    except Exception as e:
        erro_airflow = f"Erro ao acionar o Airflow: {e}"

    try:
        conn = get_db_conn(); cur = conn.cursor()
        if erro_airflow:
            cur.execute(
                "UPDATE dbo.etl_copy_exec SET status = 'erro', erro_msg = ?, "
                "concluido_em = GETDATE() WHERE id = ?",
                (erro_airflow[:2000], exec_id))
        else:
            cur.execute("UPDATE dbo.etl_copy_exec SET dag_run_id = ? WHERE id = ?",
                        (dag_run_id, exec_id))
        conn.commit(); cur.close(); conn.close()
    except Exception as e:
        log.warning("executar_copia: falha ao atualizar a execução %s: %s", exec_id, e)

    if erro_airflow:
        raise HTTPException(
            status_code=502,
            detail=f"Falha ao disparar a DAG {_EXEC_DAG}: {erro_airflow}")
    return {"exec_id": exec_id, "dag_run_id": dag_run_id, "status": "pendente"}
