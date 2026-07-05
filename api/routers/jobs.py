"""api/routers/jobs.py — GET /jobs, POST/DELETE /pipelines/jobs, POST /pipelines/jobs/reorder."""
from __future__ import annotations

import datetime as _dt
import decimal as _decimal
import json
import logging
import re
from typing import Optional

import pyodbc
from fastapi import APIRouter, Body, Depends, HTTPException

import db
from db import get_db_conn
from deps import (
    PERM_EDITAR,
    get_current_user, require_perm,
)
from routers.airflow import get_airflow_client

log = logging.getLogger("orquestra-api")

router = APIRouter()


def _fmt_dt(v):
    if v is None:
        return None
    if hasattr(v, "strftime"):
        return v.strftime("%Y-%m-%d %H:%M:%S")
    return str(v)


VALID_JOB_TYPES = {"datastage", "shell", "python", "storedproc", "decisao", "notificacao", "sql"}
VALID_PARAM_TYPES = {"INT", "VARCHAR", "DATE", "BIT", "DECIMAL", "DATETIME"}
_PARAM_NAME_RE = re.compile(r"^@?[A-Za-z_][A-Za-z0-9_]*$")
# job_name vira literal de string no código da DAG gerada e argumento de shell no
# dsjob — allowlist bloqueia aspas/;/$/quebra-de-linha (anti code/command injection).
_JOB_NAME_RE = re.compile(r"^[A-Za-z0-9_.\- ]+$")
# job_name também vira task_id no Airflow, que rejeita ESPAÇO (validate_key
# ^[\w.-]+$) — um nome com espaço publica DAG que quebra no import. Jobs NOVOS
# usam o estrito; os já salvos com espaço são tolerados (grandfather) para não
# travar o re-save de fluxos legados.
_JOB_NAME_STRICT_RE = re.compile(r"^[A-Za-z0-9_.\-]+$")
# nome de banco-alvo (storedproc, mesmo servidor) — vira nome de 3 partes
# [banco].schema.proc; allowlist bloqueia ] e demais chars perigosos (anti-injection).
_DB_NAME_RE = re.compile(r"^[A-Za-z0-9_.\-$#@ ]+$")

# ── Nó de Decisão (migration 043) ──────────────────────────────────────────
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_COND_OPERADORES = {"=", "<>", ">", ">=", "<", "<="}
_COND_COMPARACOES = {"texto", "data", "numero"}
_COND_DML_RE = re.compile(
    r"\b(INSERT|UPDATE|DELETE|MERGE|DROP|ALTER|CREATE|TRUNCATE|EXEC|EXECUTE|"
    r"GRANT|REVOKE|INTO)\b",
    re.IGNORECASE,
)


def _valid_table_ident(tabela: str) -> bool:
    """db.schema.tabela: 1–3 partes, cada uma identificador válido (anti-injeção)."""
    parts = (tabela or "").strip().split(".")
    if not 1 <= len(parts) <= 3:
        return False
    return all(_IDENT_RE.match(p) for p in parts)


def _valid_select(sql: str) -> bool:
    """SQL read-only: começa com SELECT/WITH, sem ';' e sem DML."""
    s = (sql or "").strip().rstrip(";").strip()
    if not s or ";" in s:
        return False
    head = s.lstrip("(").lstrip().upper()
    if not (head.startswith("SELECT") or head.startswith("WITH")):
        return False
    return not _COND_DML_RE.search(s)


def _validate_select_strict(sql: str) -> str:
    """Mesma validação read-only de ``_valid_select``, mas devolve o SQL limpo e
    levanta ValueError com mensagem clara (para virar 422). Usado pelo preview."""
    if not sql or not isinstance(sql, str):
        raise ValueError("SQL vazio")
    s = sql.strip().rstrip(";").strip()
    if not s:
        raise ValueError("SQL vazio")
    if ";" in s:
        raise ValueError("SQL não pode conter ';' (apenas um SELECT)")
    head = s.lstrip("(").lstrip().upper()
    if not (head.startswith("SELECT") or head.startswith("WITH")):
        raise ValueError("SQL precisa começar com SELECT/WITH (read-only)")
    if _COND_DML_RE.search(s):
        raise ValueError("SQL contém comando não permitido (read-only)")
    return s


def _validate_sql_node(cfg) -> list[str]:
    """Valida a config (sql_json) de um nó SQL. Retorna lista de erros (vazia = ok).

    Contrato: {sql:str, mssql_conn_id:str, database:str}. ``sql`` precisa ser
    read-only (mesma regra do preview/decisão query — SELECT/WITH, sem ';' nem
    DML). ``mssql_conn_id`` é obrigatório; quando a lista de conexões está
    disponível (parâmetro injetado pelo chamador), exige que pertença a ela
    (mesmo padrão do nó storedproc/decisão). ``database`` é opcional, mas se vier
    deve ser texto."""
    if not isinstance(cfg, dict):
        return ["configuração do nó SQL (sql_json) ausente ou inválida"]
    errs: list[str] = []
    if not _valid_select(cfg.get("sql") or ""):
        errs.append("SQL do nó SQL deve ser read-only (SELECT/WITH, sem ';' nem DML)")
    cid = (cfg.get("mssql_conn_id") or "").strip()
    if not cid:
        errs.append("mssql_conn_id do nó SQL é obrigatório")
    db_val = cfg.get("database")
    if db_val is not None and not isinstance(db_val, str):
        errs.append("database do nó SQL deve ser texto")
    return errs


def _validate_sql_node_conn(cfg, mssql_conn_ids) -> list[str]:
    """``_validate_sql_node`` + checagem de que a conexão existe no Airflow
    (quando a lista foi resolvida). Separado para o validador puro continuar
    testável sem ir ao Airflow."""
    errs = _validate_sql_node(cfg)
    if isinstance(cfg, dict):
        cid = (cfg.get("mssql_conn_id") or "").strip()
        if cid and mssql_conn_ids is not None and cid not in mssql_conn_ids:
            errs.append(f"conexão MSSQL '{cid}' do nó SQL não encontrada no Airflow")
    return errs


def _normalize_sql_node(cfg: dict) -> dict:
    """Normaliza sql_json para persistência (sql/mssql_conn_id/database como str).

    Mantém a CHAVE 'sql' presente (presença de chave é o que o round-trip do
    GET /fluxo / get_pipeline_job usa para devolver o SELECT por nó)."""
    return {
        "sql": (cfg.get("sql") if isinstance(cfg.get("sql"), str) else ""),
        "mssql_conn_id": (cfg.get("mssql_conn_id") or "").strip(),
        "database": ((cfg.get("database") or "").strip()
                     if isinstance(cfg.get("database"), str) else ""),
    }


def _validate_condition(cond, known_jobs, self_name, mssql_conn_ids) -> list[str]:
    """Valida a condição de um nó de decisão. Retorna lista de erros (vazia = ok)."""
    if not isinstance(cond, dict):
        return ["condição (condition_json) ausente ou inválida"]
    errs: list[str] = []
    tipo = str(cond.get("tipo") or "").strip().lower()
    if tipo not in ("contagem", "query", "linhas_job", "valor_sql"):
        errs.append("tipo da condição deve ser 'contagem', 'query', 'linhas_job' ou 'valor_sql'")
    if str(cond.get("operador") or "").strip() not in _COND_OPERADORES:
        errs.append("operador inválido (use =, <>, >, >=, <, <=)")
    valor = cond.get("valor")
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        errs.append("valor da condição é obrigatório")
    if tipo == "linhas_job":
        # Decisão por linhas processadas: compara rows_out de um job a montante
        # (lido por execução de etl_ds_job_log) contra um limiar numérico.
        jn = str(cond.get("job_name") or "").strip()
        if not jn:
            errs.append("job_name da condição (linhas_job) é obrigatório")
        elif jn == self_name:
            errs.append("job_name da condição (linhas_job) não pode ser a própria decisão")
        elif jn not in known_jobs:
            errs.append(f"job_name '{jn}' da condição (linhas_job) não existe no pipeline")
        # child_job é OPCIONAL: quando preenchido, a decisão usa as linhas daquele
        # job FILHO (de runtime, dentro do SEQUENCE job_name) em vez do total. Não
        # precisa existir em known_jobs — é um filho do DataStage, não um job do
        # pipeline. Só validamos o tipo (string).
        cj = cond.get("child_job")
        if cj is not None and not isinstance(cj, str):
            errs.append("child_job da condição (linhas_job) deve ser texto")
        if valor is not None and not (
            isinstance(valor, (int, float)) or str(valor).strip().lstrip("-").isdigit()
        ):
            errs.append("valor da condição (linhas_job) deve ser numérico")
    elif tipo == "contagem":
        if not _valid_table_ident(cond.get("tabela") or ""):
            errs.append("tabela da condição inválida (use db.schema.tabela)")
        db = (cond.get("database") or "").strip()
        if db and not _IDENT_RE.match(db):
            errs.append("database da condição inválido")
        if valor is not None and not (
            isinstance(valor, (int, float)) or str(valor).strip().lstrip("-").isdigit()
        ):
            errs.append("valor da condição (contagem) deve ser numérico")
    elif tipo == "query":
        if not _valid_select(cond.get("sql") or ""):
            errs.append("SQL da condição deve ser read-only (SELECT/WITH, sem ';' nem DML)")
    elif tipo == "valor_sql":
        # Decisão por valor publicado: lê o XCom escalar de um nó SQL a montante
        # (source_job) e compara via compara_tipado. Não roda SQL aqui — só roteia.
        sj = str(cond.get("source_job") or "").strip()
        if not sj:
            errs.append("source_job da condição (valor_sql) é obrigatório")
        elif sj == self_name:
            errs.append("source_job da condição (valor_sql) não pode ser a própria decisão")
        elif sj not in known_jobs:
            errs.append(f"source_job '{sj}' da condição (valor_sql) não existe no pipeline")
        comp = str(cond.get("comparacao") or "").strip().lower()
        if comp not in _COND_COMPARACOES:
            errs.append("comparacao da condição (valor_sql) é obrigatória (use 'texto', 'data' ou 'numero')")
    # comparacao é NOVO e OPCIONAL (ausente = comportamento legado do compara).
    # Quando presente em query/contagem, validamos o enum {texto,data,numero}.
    # (valor_sql exige comparacao acima — aqui só revalida o enum, sem duplicar.)
    if tipo in ("query", "contagem"):
        comp = cond.get("comparacao")
        if comp is not None and str(comp).strip():
            if str(comp).strip().lower() not in _COND_COMPARACOES:
                errs.append("comparacao inválida (use 'texto', 'data' ou 'numero')")
    cid = (cond.get("mssql_conn_id") or "").strip()
    if cid and mssql_conn_ids is not None and cid not in mssql_conn_ids:
        errs.append(f"conexão MSSQL '{cid}' da condição não encontrada no Airflow")
    ramo_v, ramo_f = cond.get("ramo_verdadeiro") or [], cond.get("ramo_falso") or []
    if not isinstance(ramo_v, list) or not isinstance(ramo_f, list):
        errs.append("ramos (ramo_verdadeiro/ramo_falso) devem ser listas")
        return errs
    if not ramo_v and not ramo_f:
        errs.append("a decisão precisa de ao menos um job em algum ramo")
    ambos = {str(m).strip() for m in ramo_v} & {str(m).strip() for m in ramo_f}
    if ambos:
        errs.append("job(s) em ambos os ramos (sim e não): " + ", ".join(sorted(ambos)))
    for ramo_nome, ramo in (("verdadeiro", ramo_v), ("falso", ramo_f)):
        for m in ramo:
            mn = str(m).strip()
            if mn == self_name:
                errs.append(f"ramo {ramo_nome}: não pode referenciar a própria decisão")
            elif mn not in known_jobs:
                errs.append(f"ramo {ramo_nome}: job '{mn}' não existe no pipeline")
    return errs


def _normalize_condition(cond: dict) -> dict:
    """Normaliza a condição antes de persistir em condition_json.

    Salvamos o dict INTEIRO (não fazemos cherry-pick de campos), então qualquer
    chave do contrato sobrevive ao round-trip (GET /fluxo / get_pipeline_job leem
    o JSON inteiro de volta). Para ``linhas_job`` garantimos explicitamente que
    ``job_name`` e ``child_job`` fiquem presentes e limpos (string), pois são as
    chaves que dirigem a decisão por linhas (total vs. por job filho). ``child_job``
    vazio/ausente = usa o total (rows_out); preenchido = linhas daquele filho."""
    if not isinstance(cond, dict):
        return cond
    out = dict(cond)
    tipo = str(out.get("tipo") or "").strip().lower()
    if tipo == "linhas_job":
        out["job_name"] = str(out.get("job_name") or "").strip()
        out["child_job"] = str(out.get("child_job") or "").strip()
    return out


def _validate_notify(cfg) -> list[str]:
    """Valida a config (notify_json) de um nó de notificação. Lista de erros (vazia = ok).

    Contrato: {grupo_id:int, template_id:int|null, mensagem:str}. grupo_id é
    obrigatório; template_id é opcional (canal/mensagem do catálogo); mensagem é
    override opcional (se vazio, o runtime usa o corpo do template)."""
    if not isinstance(cfg, dict):
        return ["configuração de notificação (notify_json) ausente ou inválida"]
    errs: list[str] = []
    gid = cfg.get("grupo_id")
    if gid is None or (isinstance(gid, str) and not str(gid).strip()):
        errs.append("grupo_id da notificação é obrigatório")
    elif not (isinstance(gid, int) and not isinstance(gid, bool)) and not str(gid).strip().isdigit():
        errs.append("grupo_id da notificação deve ser inteiro")
    tid = cfg.get("template_id")
    if tid is not None and not (isinstance(tid, str) and not str(tid).strip()):
        if not (isinstance(tid, int) and not isinstance(tid, bool)) and not str(tid).strip().isdigit():
            errs.append("template_id da notificação deve ser inteiro ou nulo")
    msg = cfg.get("mensagem")
    if msg is not None and not isinstance(msg, str):
        errs.append("mensagem da notificação deve ser texto")
    return errs


def _normalize_notify(cfg: dict) -> dict:
    """Normaliza notify_json para persistência (grupo_id/template_id int, mensagem str)."""
    gid = cfg.get("grupo_id")
    tid = cfg.get("template_id")
    msg = cfg.get("mensagem")
    return {
        "grupo_id": int(gid),
        "template_id": (None if tid is None or (isinstance(tid, str) and not str(tid).strip())
                        else int(tid)),
        "mensagem": (msg if isinstance(msg, str) else ""),
    }


def _graph_has_cycle(adj: dict[str, set[str]]) -> bool:
    """DFS com cores — detecta ciclo no grafo dirigido (deps + arestas do branch)."""
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {n: WHITE for n in adj}

    def visit(u: str) -> bool:
        color[u] = GRAY
        for v in adj.get(u, ()):  # ignora arestas para fora do conjunto
            if v not in color:
                continue
            if color[v] == GRAY or (color[v] == WHITE and visit(v)):
                return True
        color[u] = BLACK
        return False

    return any(color[n] == WHITE and visit(n) for n in list(adj))


async def _list_mssql_conn_ids() -> set[str] | None:
    """conn_ids MSSQL cadastrados — UNIÃO de dbo.etl_conexao (fonte da
    verdade, migration 054) com as Airflow Connections legadas. None se
    QUALQUER fonte falhar (não bloqueia o save — validação best-effort:
    uma conexão nativa não pode ser recusada só porque a tabela ou o
    Airflow estavam indisponíveis no momento)."""
    ids: set[str] = set()
    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute("SELECT conn_id FROM dbo.etl_conexao WHERE conn_type = 'mssql'")
        ids |= {(r[0] or "").strip() for r in cur.fetchall() if (r[0] or "").strip()}
        cur.close(); conn.close()
    except Exception:
        return None
    try:
        async with get_airflow_client() as client:
            r = await client.get("/api/v1/connections?limit=100")
            if not r.is_success:
                return None
            data = r.json()
            ids |= {c["connection_id"] for c in data.get("connections", [])
                    if c.get("conn_type") == "mssql"}
    except Exception:
        return None
    return ids


async def _list_mssql_hosts() -> set[str]:
    """Hosts (campo ``host``) das conexões MSSQL cadastradas — união de
    dbo.etl_conexao (fonte da verdade, migration 054) com as Airflow
    Connections legadas ainda não migradas.

    Allowlist anti-SSRF: o preview / databases por servidor só aceita um host que
    JÁ esteja cadastrado como conexão MSSQL. Cada fonte degrada para vazio de
    forma independente (ambas fora → set() → qualquer host é recusado, fail-safe)."""
    hosts: set[str] = set()
    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute("SELECT host FROM dbo.etl_conexao")
        hosts |= {(r[0] or "").strip() for r in cur.fetchall() if (r[0] or "").strip()}
        cur.close(); conn.close()
    except Exception:
        pass
    try:
        async with get_airflow_client() as client:
            r = await client.get("/api/v1/connections?limit=100")
            if r.is_success:
                hosts |= {
                    (c.get("host") or "").strip()
                    for c in r.json().get("connections", [])
                    if c.get("conn_type") == "mssql" and (c.get("host") or "").strip()
                }
    except Exception:
        pass
    return hosts


def _swap_conn_str(host: str, database: str) -> str:
    """Deriva uma connection string apontando para (host, database) a partir da
    ``MSSQL_CONN_STR`` do app, preservando DRIVER/UID/PWD/demais pares e trocando
    apenas SERVER e DATABASE. Levanta ValueError se a base não estiver configurada.

    Parse simples de pares ``CHAVE=VALOR;`` (formato pyodbc). Chaves comparadas
    case-insensitive; SERVER e DATABASE são sobrescritos (inseridos se ausentes)."""
    base = (db.MSSQL_CONN_STR or "").strip()
    if not base:
        raise ValueError("MSSQL_CONN_STR não configurada")
    pares: list[tuple[str, str]] = []
    for chunk in base.split(";"):
        if not chunk.strip():
            continue
        if "=" not in chunk:
            pares.append((chunk.strip(), ""))
            continue
        k, v = chunk.split("=", 1)
        pares.append((k.strip(), v.strip()))
    out: list[str] = []
    viu_server = viu_db = False
    for k, v in pares:
        kl = k.lower()
        if kl in ("server", "address", "addr", "network address"):
            out.append(f"SERVER={host}"); viu_server = True
        elif kl in ("database", "initial catalog"):
            out.append(f"DATABASE={database}"); viu_db = True
        else:
            out.append(f"{k}={v}" if v != "" else k)
    if not viu_server:
        out.append(f"SERVER={host}")
    if not viu_db:
        out.append(f"DATABASE={database}")
    return ";".join(out) + ";"


def _json_safe(v):
    """Serializa um valor de célula pyodbc para algo JSON-serializável.
    Datas/datetimes → ISO; Decimal → str; bytes → hex; resto str (None preservado)."""
    if v is None or isinstance(v, (str, int, float, bool)):
        return v
    if isinstance(v, (_dt.datetime, _dt.date, _dt.time)):
        return v.isoformat()
    if isinstance(v, _decimal.Decimal):
        return str(v)
    if isinstance(v, (bytes, bytearray)):
        return bytes(v).hex()
    return str(v)


# ── Decisão SQL: comparação tipada ──────────────────────────────────────────
# Réplica FIEL de dags/utils/conditions.py (compara/_coerce_num/_aplica_operador/
# _to_date/compara_tipado). A API só tem `api/` no pythonpath (pytest pythonpath=api),
# então não importa de `dags/`. MANTER EM SINCRONIA com conditions.compara_tipado:
# qualquer mudança na lógica de comparação lá deve ser refletida aqui (e vice-versa).
_CMP_OPERADORES = {"=", "==", "<>", "!=", ">", ">=", "<", "<="}


def _cmp_coerce_num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _cmp_compara(obtido, operador, limite) -> bool:
    """Compara ``valor_obtido <operador> valor_limite``. Numérico quando ambos
    convertem para número; senão, comparação textual."""
    operador = str(operador or "").strip()
    if operador not in _CMP_OPERADORES:
        raise ValueError(f"operador inválido: {operador!r}")
    a, b = _cmp_coerce_num(obtido), _cmp_coerce_num(limite)
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


def _cmp_aplica_operador(a, b, operador) -> bool:
    """Aplica ``a <operador> b`` com valores já normalizados (operador já validado)."""
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


def _cmp_to_date(v):
    """Normaliza ``v`` para ``date`` (nível de dia). Aceita date/datetime/string;
    token ``HOJE`` → hoje; string tenta ``YYYY-MM-DD`` (prefixo de ISO datetime).
    Não parseável → None."""
    if v is None:
        return None
    if isinstance(v, _dt.datetime):
        return v.date()
    if isinstance(v, _dt.date):
        return v
    s = str(v).strip()
    if not s:
        return None
    if s.upper() == "HOJE":
        return _dt.date.today()
    head = re.split(r"[ T]", s, 1)[0]
    try:
        return _dt.datetime.strptime(head, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _compara_tipado(obtido, operador, valor, comparacao) -> bool:
    """Compara ``obtido <operador> valor`` honrando o tipo ``comparacao``
    ∈ {'numero','data','texto'} (ou desconhecido → delega ao compara legado).

    NUNCA levanta por erro de parse — só ``operador`` inválido pode levantar.
    Réplica fiel de conditions.compara_tipado (ver nota acima)."""
    comp = str(comparacao or "").strip().lower()
    if comp not in _COND_COMPARACOES:
        return _cmp_compara(obtido, operador, valor)
    operador = str(operador or "").strip()
    if operador not in _CMP_OPERADORES:
        raise ValueError(f"operador inválido: {operador!r}")
    try:
        if comp == "numero":
            a = _cmp_coerce_num(obtido)
            b = _cmp_coerce_num(valor)
            a = 0.0 if a is None else a
            b = 0.0 if b is None else b
            return _cmp_aplica_operador(a, b, operador)
        if comp == "data":
            a = _cmp_to_date(obtido)
            b = _cmp_to_date(valor)
            if a is None or b is None:
                log.info("[decisao-simular data] não foi possível resolver data "
                         "(obtido=%r→%r, valor=%r→%r) — resultado False.", obtido, a, valor, b)
                return False
            return _cmp_aplica_operador(a, b, operador)
        # 'texto'
        a = "" if obtido is None else str(obtido)
        b = "" if valor is None else str(valor)
        return _cmp_aplica_operador(a, b, operador)
    except ValueError:
        raise
    except Exception as exc:  # noqa: BLE001 — degrada sem levantar
        log.info("[decisao-simular %s] erro ao comparar (obtido=%r, valor=%r, op=%r): %s "
                 "— resultado False.", comp, obtido, valor, operador, exc)
        return False


# ── Config de fluxo: timeout do preview SQL (etl_app_config) ─────────────────
_PREVIEW_TIMEOUT_DEFAULT = 15
_PREVIEW_TIMEOUT_MIN = 1
_PREVIEW_TIMEOUT_MAX = 120
_PREVIEW_TIMEOUT_KEY = "sql_preview_timeout_s"


def _clamp_preview_timeout(v: int) -> int:
    return max(_PREVIEW_TIMEOUT_MIN, min(_PREVIEW_TIMEOUT_MAX, int(v)))


def _get_preview_timeout_s() -> int:
    """Lê o timeout (s) do preview SQL de dbo.etl_app_config (key sql_preview_timeout_s),
    com fallback 15 e clamp 1..120. Degrada para o default se a tabela faltar/erro."""
    try:
        from routers.admin import _get_app_config_value
        raw = _get_app_config_value(_PREVIEW_TIMEOUT_KEY)
        if raw is None:
            return _PREVIEW_TIMEOUT_DEFAULT
        return _clamp_preview_timeout(int(str(raw).strip()))
    except (ValueError, TypeError):
        return _PREVIEW_TIMEOUT_DEFAULT
    except Exception as e:  # noqa: BLE001 — degrada para o default
        log.warning("leitura de %s falhou: %s — usando default %ss.",
                    _PREVIEW_TIMEOUT_KEY, e, _PREVIEW_TIMEOUT_DEFAULT)
        return _PREVIEW_TIMEOUT_DEFAULT


@router.get("/jobs/flow-config", tags=["jobs"])
def get_flow_config(_auth: dict = Depends(get_current_user)):
    """Config de fluxo (parâmetros operacionais do editor de pipelines).

    Hoje: {sql_preview_timeout_s: int} — timeout (s) do preview/simulação SQL,
    lido de dbo.etl_app_config (default 15, clamp 1..120). Degrada para o default."""
    return {"sql_preview_timeout_s": _get_preview_timeout_s()}


@router.put("/jobs/flow-config", tags=["jobs"])
def put_flow_config(
    body: dict = Body(default={}),
    _auth: dict = Depends(require_perm(PERM_EDITAR)),
):
    """Atualiza a config de fluxo. Body: {sql_preview_timeout_s: int} (clamp 1..120).

    Persiste em dbo.etl_app_config (MERGE, mesmo padrão de admin config_upsert).
    Degrada com erro claro (400) se a tabela não existir — nunca 500 cru."""
    raw = body.get("sql_preview_timeout_s")
    if raw is None:
        raise HTTPException(status_code=422, detail="sql_preview_timeout_s é obrigatório")
    try:
        val = _clamp_preview_timeout(int(raw))
    except (ValueError, TypeError):
        raise HTTPException(status_code=422, detail="sql_preview_timeout_s deve ser inteiro")
    requested_by = (_auth.get("matricula") or "").strip() or None
    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute(
            "MERGE dbo.etl_app_config AS t "
            "USING (SELECT ? AS k, ? AS v, ? AS d) AS s ON t.config_key = s.k "
            "WHEN MATCHED THEN UPDATE SET config_value=?, descricao=COALESCE(?,t.descricao), "
            "  updated_by=?, updated_at=GETDATE() "
            "WHEN NOT MATCHED THEN INSERT (config_key,config_value,descricao,updated_by,updated_at) "
            "  VALUES (s.k, s.v, s.d, ?, GETDATE());",
            [_PREVIEW_TIMEOUT_KEY, str(val), "Timeout (s) do preview/simulação SQL",
             str(val), "Timeout (s) do preview/simulação SQL", requested_by, requested_by],
        )
        conn.commit(); cur.close(); conn.close()
    except Exception as e:  # noqa: BLE001 — sem 500 cru
        log.warning("put_flow_config falhou ao salvar %s: %s", _PREVIEW_TIMEOUT_KEY, e)
        raise HTTPException(
            status_code=400,
            detail="Não foi possível salvar a configuração de fluxo (etl_app_config indisponível).")
    return {"sql_preview_timeout_s": val}


@router.get("/jobs", tags=["jobs"])
def list_jobs(
    offset: int = 0,
    limit: int = 50,
    filter_pipeline: Optional[str] = None,
    filter_job_name: Optional[str] = None,
    filter_job_type: Optional[str] = None,
):
    """Lista jobs de pipeline. Substitui etl_pipeline_job_query."""
    limit  = min(200, max(1, limit))
    offset = max(0, offset)
    fp = (filter_pipeline or "").strip()
    fj = (filter_job_name or "").strip()
    ft = (filter_job_type or "").strip()

    try:
        conn = get_db_conn()
        cur  = conn.cursor()

        # Detecta quais colunas opcionais existem na tabela
        cur.execute("""
            SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME='etl_pipeline_job'
        """)
        existing_cols = {r[0].lower() for r in cur.fetchall()}

        def _sel(col: str, alias: str, cast_int: bool = False) -> str:
            if col.lower() in existing_cols:
                return f"CAST(j.{col} AS INT) AS {alias}" if cast_int else f"j.{col} AS {alias}"
            return f"NULL AS {alias}"

        where: list[str] = []
        params: list = []
        if fp:
            where.append("j.pipeline_name = ?")
            params.append(fp)
        if fj:
            where.append("j.job_name LIKE ?")
            params.append(f"%{fj}%")
        if ft:
            where.append("j.job_type = ?")
            params.append(ft)

        where_sql = ("WHERE " + " AND ".join(where)) if where else ""

        cur.execute(f"SELECT COUNT(*) FROM dbo.etl_pipeline_job j {where_sql}", params)
        total = cur.fetchone()[0]

        data_sql = f"""
            SELECT
                j.pipeline_name,
                p.project_name,
                j.job_name,
                CAST(j.execution_order AS INT) AS execution_order,
                {_sel('job_type',    'job_type')},
                {_sel('job_command', 'job_command')},
                {_sel('active',      'active', cast_int=True)},
                {_sel('created_at',  'created_at')},
                {_sel('updated_at',  'updated_at')},
                {_sel('ssh_conn_id',  'ssh_conn_id')},
                {_sel('verbose_log', 'verbose_log', cast_int=True)},
                {_sel('mssql_conn_id', 'mssql_conn_id')}
            FROM dbo.etl_pipeline_job j
            LEFT JOIN dbo.etl_pipeline p ON p.pipeline_name = j.pipeline_name
            {where_sql}
            ORDER BY j.pipeline_name, j.execution_order, j.job_name
            OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
        """
        data_params = list(params) + [offset, limit]
        cur.execute(data_sql, data_params)
        data = [
            {
                "pipeline_name":  r[0], "project_name": r[1], "job_name": r[2],
                "execution_order": r[3], "job_type": r[4], "job_command": r[5],
                "active": r[6], "created_at": _fmt_dt(r[7]), "updated_at": _fmt_dt(r[8]),
                "ssh_conn_id": r[9], "verbose_log": bool(r[10]), "mssql_conn_id": r[11],
            }
            for r in cur.fetchall()
        ]
        cur.close(); conn.close()
        pages = 0 if total == 0 else -(-total // limit)
        return {"total": total, "offset": offset, "limit": limit, "pages": pages,
                "table": "etl_pipeline_job", "data": data}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/jobs/databases", tags=["jobs"])
async def list_job_databases(
    host: Optional[str] = None,
    _auth: dict = Depends(require_perm(PERM_EDITAR)),
):
    """Bancos disponíveis para o seletor de banco-alvo dos jobs.

    Sem ``?host`` (padrão): bancos do MESMO servidor da conexão do ORQUESTRA
    (credencial do próprio app via get_db_conn — não expõe senha).

    Com ``?host=<host>``: bancos daquele SERVIDOR MSSQL. O host precisa estar
    cadastrado como conexão MSSQL no Airflow (allowlist anti-SSRF); conecta-se
    com a credencial do app trocando SERVER no conn str. Host não cadastrado →
    [] (não conecta em servidor arbitrário).

    Degrada para lista vazia se a consulta ao catálogo falhar."""
    host = (host or "").strip()
    if host:
        allowed = await _list_mssql_hosts()
        if host not in allowed:
            log.warning("list_job_databases: host %r não cadastrado — recusado.", host)
            return {"server": None, "databases": []}
        # Banco neutro só para abrir a sessão; o catálogo é server-wide.
        try:
            conn_str = _swap_conn_str(host, "master")
        except ValueError as e:
            log.warning("list_job_databases (host=%s) sem conn str: %s", host, e)
            return {"server": None, "databases": []}
        try:
            conn = pyodbc.connect(conn_str, timeout=5)
            cur = conn.cursor()
            cur.execute(
                "SELECT d.name FROM sys.databases d "
                "WHERE d.state_desc = 'ONLINE' AND HAS_DBACCESS(d.name) = 1 "
                "ORDER BY d.name")
            databases = [r[0] for r in cur.fetchall()]
            cur.close(); conn.close()
            return {"server": host, "databases": databases}
        except Exception as e:
            log.warning("list_job_databases (host=%s) degradou: %s", host, e)
            return {"server": None, "databases": []}
    # Sem host: comportamento atual (servidor do app).
    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute("SELECT @@SERVERNAME")
        srow = cur.fetchone()
        server_name = srow[0] if srow else None
        # Apenas bancos ONLINE e acessíveis ao usuário da conexão.
        cur.execute(
            "SELECT d.name FROM sys.databases d "
            "WHERE d.state_desc = 'ONLINE' AND HAS_DBACCESS(d.name) = 1 "
            "ORDER BY d.name")
        databases = [r[0] for r in cur.fetchall()]
        cur.close(); conn.close()
        return {"server": server_name, "databases": databases}
    except Exception as e:
        log.warning("list_job_databases degradou: %s", e)
        return {"server": None, "databases": []}


@router.post("/jobs/sql-preview", tags=["jobs"])
async def sql_preview(
    body: dict = Body(default={}),
    _auth: dict = Depends(get_current_user),
):
    """Roda um SELECT read-only do usuário (decisão tipo 'query') e devolve uma
    amostra de até 100 linhas, para o autor conferir o resultado antes de salvar.

    Body: {host: str, database: str, sql: str}.

    Segurança:
      - ``sql`` precisa ser read-only (SELECT/WITH, sem ';' nem DML) — 422 senão.
      - ``host`` precisa estar cadastrado como conexão MSSQL no Airflow (allowlist
        anti-SSRF) — 400 senão. Conecta com a credencial do app (swap SERVER/
        DATABASE no conn str), timeout curto.

    Resposta: {columns: [str], rows: [[json-safe]], total: int, truncated: bool}.
    Erros de conexão/SQL → 400 com mensagem clara (nunca 500 cru)."""
    host = (body.get("host") or "").strip()
    database = (body.get("database") or "").strip()
    sql_raw = body.get("sql") or ""

    if not host:
        raise HTTPException(status_code=422, detail="host é obrigatório")
    if not database:
        raise HTTPException(status_code=422, detail="database é obrigatório")
    if not _IDENT_RE.match(database):
        raise HTTPException(status_code=422, detail="database inválido")
    # Read-only de verdade (mesma validação da condição). 422 se inválido.
    try:
        sql = _validate_select_strict(sql_raw)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    allowed = await _list_mssql_hosts()
    if host not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"host '{host}' não está cadastrado como conexão MSSQL")

    try:
        conn_str = _swap_conn_str(host, database)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Limita a 100 linhas envolvendo o SELECT do usuário numa subquery.
    # SELECT TOP 100 * FROM (<sql>) — robusto; se o SELECT do usuário tiver ORDER
    # BY sem TOP/OFFSET, o SQL Server recusa a subquery, então o erro vira 400
    # claro (preview com mensagem) em vez de 500.
    preview_sql = f"SELECT TOP 100 * FROM (\n{sql}\n) AS _prev"
    # Timeout de execução agora vem da config de fluxo (etl_app_config), não fixo.
    _PREVIEW_TIMEOUT_S = _get_preview_timeout_s()
    try:
        conn = pyodbc.connect(conn_str, timeout=5)
        # Timeout de EXECUÇÃO (não só de conexão): o driver cancela a query no
        # servidor se passar disso — evita deixar um SELECT pesado pendurado.
        conn.timeout = _PREVIEW_TIMEOUT_S
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Falha ao conectar em '{host}': {e}")
    try:
        cur = conn.cursor()
        # Leitura sem tomar/esperar lock (preview é descartável; dirty read ok) —
        # não bloqueia gravações nem fica preso esperando lock de outra sessão.
        cur.execute("SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED")
        cur.execute(preview_sql)
        columns = [d[0] for d in (cur.description or [])]
        fetched = cur.fetchall()
        rows = [[_json_safe(v) for v in r] for r in fetched]
        cur.close(); conn.close()
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        msg = str(e)
        if "timeout" in msg.lower() or "HYT00" in msg or "HYT01" in msg:
            raise HTTPException(
                status_code=400,
                detail=(f"A consulta excedeu o tempo limite de {_PREVIEW_TIMEOUT_S}s na "
                        "pré-visualização e foi cancelada no servidor. Refine o SELECT "
                        "(filtros, menos colunas) para conferir a amostra."))
        raise HTTPException(status_code=400, detail=f"Erro ao executar o SELECT: {e}")
    total = len(rows)
    return {
        "columns": columns,
        "rows": rows,
        "total": total,
        "truncated": total >= 100,
    }


def _open_swapped_conn(host: str, database: str, timeout_s: int):
    """Abre uma conexão pyodbc para (host, database) com a credencial do app
    (swap SERVER/DATABASE), isolation READ UNCOMMITTED e ``timeout_s`` de execução.
    Levanta HTTPException(400) com mensagem clara em falha de conn str/conexão.
    Mesmo perfil de conexão do /jobs/sql-preview."""
    try:
        conn_str = _swap_conn_str(host, database)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    try:
        conn = pyodbc.connect(conn_str, timeout=5)
        conn.timeout = timeout_s
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Falha ao conectar em '{host}': {e}")
    try:
        cur = conn.cursor()
        cur.execute("SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED")
        return conn, cur
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        raise HTTPException(status_code=400, detail=f"Falha ao iniciar a sessão em '{host}': {e}")


@router.post("/jobs/decisao-simular", tags=["jobs"])
async def decisao_simular(
    body: dict = Body(default={}),
    _auth: dict = Depends(get_current_user),
):
    """Simula a decisão de um nó SQL: roda o SELECT do usuário, pega o escalar
    (primeira coluna da primeira linha) e aplica a comparação tipada — devolve para
    qual ramo (sim/nao) a execução iria, sem salvar nada.

    Body: {host, database, sql, comparacao, operador, valor}.

    Segurança (mesma do /jobs/sql-preview):
      - ``sql`` read-only (SELECT/WITH, sem ';' nem DML) — 422 senão.
      - ``host`` cadastrado como conexão MSSQL no Airflow (allowlist anti-SSRF) — 400 senão.
      - ``database`` identificador válido. ``comparacao`` ∈ {texto,data,numero},
        ``operador`` válido. Timeout de execução vem da config de fluxo.

    Resposta: {valor_obtido: str|null, resultado: bool, ramo: 'sim'|'nao'}.
    Erros de conexão/SQL/timeout → 400 com mensagem clara (nunca 500 cru)."""
    host = (body.get("host") or "").strip()
    database = (body.get("database") or "").strip()
    sql_raw = body.get("sql") or ""
    comparacao = str(body.get("comparacao") or "").strip().lower()
    operador = str(body.get("operador") or "").strip()
    valor = body.get("valor")

    if not host:
        raise HTTPException(status_code=422, detail="host é obrigatório")
    if not database:
        raise HTTPException(status_code=422, detail="database é obrigatório")
    if not _IDENT_RE.match(database):
        raise HTTPException(status_code=422, detail="database inválido")
    try:
        sql = _validate_select_strict(sql_raw)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    if comparacao not in _COND_COMPARACOES:
        raise HTTPException(status_code=422, detail="comparacao deve ser 'texto', 'data' ou 'numero'")
    if operador not in _COND_OPERADORES:
        raise HTTPException(status_code=422, detail="operador inválido (use =, <>, >, >=, <, <=)")

    allowed = await _list_mssql_hosts()
    if host not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"host '{host}' não está cadastrado como conexão MSSQL")

    timeout_s = _get_preview_timeout_s()
    conn, cur = _open_swapped_conn(host, database, timeout_s)
    try:
        cur.execute(sql)
        row = cur.fetchone()
        cur.close(); conn.close()
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        msg = str(e)
        if "timeout" in msg.lower() or "HYT00" in msg or "HYT01" in msg:
            raise HTTPException(
                status_code=400,
                detail=(f"A consulta excedeu o tempo limite de {timeout_s}s na simulação "
                        "e foi cancelada no servidor. Refine o SELECT (filtros, menos "
                        "colunas) para simular a decisão."))
        raise HTTPException(status_code=400, detail=f"Erro ao executar o SELECT: {e}")

    obtido = row[0] if row else None
    try:
        resultado = _compara_tipado(obtido, operador, valor, comparacao)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    # Contrato: valor_obtido é str|null (None quando vazio). _json_safe normaliza
    # datas/decimais/bytes; o str() final fixa o tipo da resposta como string.
    safe = _json_safe(obtido)
    return {
        "valor_obtido": None if safe is None else str(safe),
        "resultado": resultado,
        "ramo": "sim" if resultado else "nao",
    }


@router.post("/pipelines/jobs/register", tags=["jobs"])
async def register_pipeline_jobs(body: dict = Body(default={}), _auth: dict = Depends(require_perm(PERM_EDITAR))):
    """Registra/atualiza jobs e lineage de um pipeline (etl_pipeline_job_register)."""
    pipeline_name = (body.get("pipeline_name") or "").strip()
    if not pipeline_name:
        raise HTTPException(status_code=422, detail="pipeline_name é obrigatório")
    # Wizard de pipeline salva jobs antes do lineage estar completo
    require_lineage = bool(body.get("require_lineage", True))

    jobs_raw = body.get("jobs")
    if jobs_raw:
        if not isinstance(jobs_raw, list) or len(jobs_raw) == 0:
            raise HTTPException(status_code=422, detail="jobs deve ser lista não vazia")
        jobs = jobs_raw
    else:
        job_name = body.get("job_name")
        order    = body.get("execution_order")
        if not job_name or order is None:
            raise HTTPException(status_code=422, detail="Informe jobs[] ou job_name+execution_order")
        jobs = [{"job_name": job_name, "execution_order": int(order),
                 "job_type": body.get("job_type", "datastage"),
                 "job_command": body.get("job_command"),
                 "ssh_conn_id": body.get("ssh_conn_id"),
                 "verbose_log": body.get("verbose_log", False),
                 "mssql_conn_id": body.get("mssql_conn_id"),
                 "params": body.get("params", []),
                 "origens": body.get("origens", []),
                 "destinos": body.get("destinos", [])}]

    mssql_conn_ids = await _list_mssql_conn_ids()

    erros = []
    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME='etl_pipeline_job' "
            "AND COLUMN_NAME='depends_on_jobs'")
        _has_dep_col = bool(cur.fetchone()[0])
        cur.execute(
            "SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME='etl_pipeline_job' "
            "AND COLUMN_NAME='mssql_database'")
        _has_db_col = bool(cur.fetchone()[0])
        cur.execute(
            "SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME='etl_pipeline_job' "
            "AND COLUMN_NAME='condition_json'")
        _has_cond_col = bool(cur.fetchone()[0])
        cur.execute(
            "SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME='etl_pipeline_job' "
            "AND COLUMN_NAME='notify_json'")
        _has_notify_col = bool(cur.fetchone()[0])
        cur.execute(
            "SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME='etl_pipeline_job' "
            "AND COLUMN_NAME='sql_json'")
        _has_sql_col = bool(cur.fetchone()[0])

        # Jobs conhecidos do pipeline (request + já existentes) — usado para
        # validar os ramos da decisão e detectar ciclos incluindo as arestas
        # do branch.
        req_names = {(j.get("job_name") or "").strip() for j in jobs
                     if (j.get("job_name") or "").strip()}
        db_names: set[str] = set()
        try:
            cur.execute("SELECT job_name FROM dbo.etl_pipeline_job WHERE pipeline_name=?",
                        (pipeline_name,))
            db_names = {r[0] for r in cur.fetchall()}
        except Exception:
            db_names = set()
        known_jobs = req_names | db_names
        # Arestas para o detector de ciclo (apenas nós presentes no request).
        cycle_adj: dict[str, set[str]] = {n: set() for n in req_names}

        for idx, job in enumerate(jobs):
            cond_json_str = None     # preenchido só p/ jobs de decisão (persiste depois)
            notify_json_str = None   # preenchido só p/ jobs de notificação (persiste depois)
            sql_json_str = None      # preenchido só p/ nós SQL (persiste depois)
            j_name      = (job.get("job_name") or "").strip()
            j_order     = job.get("execution_order")
            j_type      = (job.get("job_type") or "datastage").lower().strip()
            j_cmd       = job.get("job_command") or None
            j_mssql_cid = (job.get("mssql_conn_id") or "").strip() or None
            j_mssql_db  = (job.get("mssql_database") or "").strip() or None
            j_params    = job.get("params") or []
            origens     = job.get("origens",  [])
            destinos    = job.get("destinos", [])
            transfs     = job.get("transformacoes", [])

            if not j_name or j_order is None:
                erros.append(f"Item {idx}: job_name e execution_order obrigatórios"); continue
            if not _JOB_NAME_RE.match(j_name):
                erros.append(f"Item {idx} ({j_name}): nome de job inválido — use apenas letras, números, _ . -"); continue
            if j_name not in db_names and not _JOB_NAME_STRICT_RE.match(j_name):
                erros.append(f"Item {idx} ({j_name}): nome de job novo não pode ter espaço "
                             "(vira task_id no Airflow, que o rejeita no import da DAG)"); continue
            if j_type not in VALID_JOB_TYPES:
                erros.append(f"Item {idx} ({j_name}): job_type '{j_type}' inválido"); continue
            # Nó de Decisão é roteador, Notificação é efeito colateral e o nó SQL
            # roda um SELECT e publica o valor: nenhum dos três tem lineage
            # (origem/destino) nem comando (o SQL vive em sql_json).
            is_decisao = (j_type == "decisao")
            is_notificacao = (j_type == "notificacao")
            is_sql = (j_type == "sql")
            sem_lineage = is_decisao or is_notificacao or is_sql
            if not origens and not transfs and require_lineage and not sem_lineage:
                erros.append(f"Item {idx} ({j_name}): ao menos 1 origem é obrigatória"); continue
            if not destinos and not transfs and require_lineage and not sem_lineage:
                erros.append(f"Item {idx} ({j_name}): ao menos 1 destino é obrigatório"); continue
            if j_mssql_cid and mssql_conn_ids is not None and j_mssql_cid not in mssql_conn_ids:
                erros.append(f"Item {idx} ({j_name}): conexão MSSQL '{j_mssql_cid}' não encontrada no Airflow"); continue
            if j_mssql_db and not _DB_NAME_RE.match(j_mssql_db):
                erros.append(f"Item {idx} ({j_name}): nome de banco '{j_mssql_db}' inválido"); continue

            # Decisão: valida a condição e registra as arestas do branch p/ ciclo.
            if is_decisao:
                raw_cond = job.get("condition")
                if not isinstance(raw_cond, dict):
                    rc = job.get("condition_json")
                    try:
                        raw_cond = json.loads(rc) if rc else None
                    except (ValueError, TypeError):
                        raw_cond = None
                cond_errs = _validate_condition(raw_cond, known_jobs, j_name, mssql_conn_ids)
                if cond_errs:
                    erros.extend(f"Item {idx} ({j_name}): {e}" for e in cond_errs); continue
                # Persiste o dict INTEIRO (job_name + child_job inclusos p/ linhas_job)
                # — round-trip garantido no GET /fluxo / get_pipeline_job.
                cond_json_str = json.dumps(_normalize_condition(raw_cond), ensure_ascii=False)
                for m in (raw_cond.get("ramo_verdadeiro") or []) + (raw_cond.get("ramo_falso") or []):
                    mn = str(m).strip()
                    if j_name in cycle_adj and mn in cycle_adj:
                        cycle_adj[j_name].add(mn)   # decisão → membro do ramo

            # Notificação: valida a config (notify_json) — grupo_id obrigatório.
            if is_notificacao:
                raw_notify = job.get("notify")
                if not isinstance(raw_notify, dict):
                    rn = job.get("notify_json")
                    try:
                        raw_notify = json.loads(rn) if rn else None
                    except (ValueError, TypeError):
                        raw_notify = None
                notify_errs = _validate_notify(raw_notify)
                if notify_errs:
                    erros.extend(f"Item {idx} ({j_name}): {e}" for e in notify_errs); continue
                notify_json_str = json.dumps(_normalize_notify(raw_notify), ensure_ascii=False)

            # Nó SQL: valida a config (sql_json) — SELECT read-only + conexão.
            if is_sql:
                raw_sql = job.get("sql_node")
                if not isinstance(raw_sql, dict):
                    rs = job.get("sql_json")
                    try:
                        raw_sql = json.loads(rs) if rs else None
                    except (ValueError, TypeError):
                        raw_sql = None
                sql_errs = _validate_sql_node_conn(raw_sql, mssql_conn_ids)
                if sql_errs:
                    erros.extend(f"Item {idx} ({j_name}): {e}" for e in sql_errs); continue
                sql_json_str = json.dumps(_normalize_sql_node(raw_sql), ensure_ascii=False)

            params_validos = []
            if j_type == "storedproc" and j_params:
                nomes_vistos = set()
                param_erro = False
                for pi, p in enumerate(j_params):
                    p_name = (p.get("param_name") or "").strip()
                    p_type = (p.get("param_type") or "").strip().upper()
                    if not p_name or not _PARAM_NAME_RE.match(p_name):
                        erros.append(f"Item {idx} ({j_name}) parâmetro #{pi+1}: nome inválido"); param_erro = True; continue
                    if p_type not in VALID_PARAM_TYPES:
                        erros.append(f"Item {idx} ({j_name}) parâmetro #{pi+1} ({p_name}): tipo inválido"); param_erro = True; continue
                    key = p_name.lstrip("@").lower()
                    if key in nomes_vistos:
                        erros.append(f"Item {idx} ({j_name}): parâmetro '{p_name}' duplicado"); param_erro = True; continue
                    nomes_vistos.add(key)
                    params_validos.append((p_name, p_type, p.get("param_value"), pi))
                if param_erro:
                    continue

            try:
                verbose = 1 if job.get("verbose_log") else 0
                cur.execute(
                    "EXEC dbo.sp_etl_pipeline_job_upsert "
                    "@pipeline_name=?, @job_name=?, @execution_order=?, @job_type=?, @job_command=?, "
                    "@ssh_conn_id=?, @verbose_log=?, @mssql_conn_id=?",
                    (pipeline_name, j_name, int(j_order), j_type, j_cmd,
                     job.get("ssh_conn_id") or None, verbose, j_mssql_cid),
                )
                cur.execute(
                    "EXEC dbo.sp_etl_pipeline_job_param_clear @pipeline_name=?, @job_name=?",
                    (pipeline_name, j_name),
                )
                for p_name, p_type, p_value, p_order in params_validos:
                    cur.execute(
                        "EXEC dbo.sp_etl_pipeline_job_param_insert "
                        "@pipeline_name=?, @job_name=?, @param_name=?, @param_type=?, @param_value=?, @param_order=?",
                        (pipeline_name, j_name, p_name, p_type, p_value, p_order),
                    )
                # Dependência por job (opt-in) — grava CSV dos predecessores.
                _dep = job.get("depends_on_jobs")
                if isinstance(_dep, list):
                    _dep_list = [str(d).strip() for d in _dep if str(d).strip()]
                else:
                    _dep_list = [d.strip() for d in str(_dep or "").split(",") if d.strip()]
                _dep_str = ",".join(_dep_list)
                # Arestas predecessor → job para o detector de ciclo.
                for d in _dep_list:
                    if d in cycle_adj and j_name in cycle_adj:
                        cycle_adj[d].add(j_name)
                if _has_dep_col:
                    cur.execute(
                        "UPDATE dbo.etl_pipeline_job SET depends_on_jobs=? "
                        "WHERE pipeline_name=? AND job_name=?",
                        ((_dep_str or None), pipeline_name, j_name))
                # Banco-alvo por job storedproc (opt-in) — grava no MESMO servidor.
                if _has_db_col:
                    cur.execute(
                        "UPDATE dbo.etl_pipeline_job SET mssql_database=? "
                        "WHERE pipeline_name=? AND job_name=?",
                        ((j_mssql_db if j_type == "storedproc" else None), pipeline_name, j_name))
                # Condição do nó de decisão (opt-in) — NULL para os demais tipos.
                if _has_cond_col:
                    cur.execute(
                        "UPDATE dbo.etl_pipeline_job SET condition_json=? "
                        "WHERE pipeline_name=? AND job_name=?",
                        (cond_json_str, pipeline_name, j_name))
                # Config do nó de notificação (opt-in) — NULL para os demais tipos.
                if _has_notify_col:
                    cur.execute(
                        "UPDATE dbo.etl_pipeline_job SET notify_json=? "
                        "WHERE pipeline_name=? AND job_name=?",
                        (notify_json_str, pipeline_name, j_name))
                # Config do nó SQL (opt-in) — NULL para os demais tipos.
                if _has_sql_col:
                    cur.execute(
                        "UPDATE dbo.etl_pipeline_job SET sql_json=? "
                        "WHERE pipeline_name=? AND job_name=?",
                        (sql_json_str, pipeline_name, j_name))
            except Exception as e:
                erros.append(f"Item {idx} ({j_name}): erro ao gravar job — {e}"); continue

            for direction, objects in [("origem", origens), ("transformacao", transfs), ("destino", destinos)]:
                for oi, obj in enumerate(objects):
                    obj_name = (obj.get("object_name") or "").strip()
                    if not obj_name:
                        erros.append(f"Item {idx} ({j_name}) {direction}[{oi}]: object_name obrigatório"); continue
                    try:
                        cur.execute(
                            "EXEC dbo.sp_etl_job_lineage_upsert "
                            "@pipeline_name=?, @job_name=?, @direction=?, @object_type=?, @object_name=?, "
                            "@stage_name=?, @stage_type_raw=?, @database_name=?, @sql_expression=?, "
                            "@file_path=?, @dsx_source_file=?, @extracted_at=?, @extraction_method=?",
                            (pipeline_name, j_name, direction,
                             (obj.get("object_type") or "Tabela").strip(), obj_name,
                             obj.get("stage_name"), obj.get("stage_type_raw"),
                             obj.get("database_name"), obj.get("sql_expression"),
                             obj.get("file_path"), obj.get("dsx_source_file"),
                             obj.get("extracted_at"), obj.get("extraction_method")),
                        )
                    except Exception as e:
                        erros.append(f"Item {idx} ({j_name}) {direction} '{obj_name}': {e}")

        # Ciclo no grafo do pipeline (deps + arestas do branch) — só faz sentido
        # quando o request traz o conjunto de jobs (wizard envia jobs[]).
        if not erros and jobs_raw and _graph_has_cycle(cycle_adj):
            erros.append("ciclo detectado entre os jobs (dependências/ramos da decisão)")

        if erros:
            conn.rollback()
            raise HTTPException(status_code=422, detail={"errors": erros})
        conn.commit()
        cur.close(); conn.close()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro DB: {e}")
    return {"ok": True, "pipeline_name": pipeline_name, "jobs_registered": len(jobs)}


@router.post("/pipelines/jobs/reorder", tags=["jobs"])
async def reorder_pipeline_jobs(body: dict = Body(default={}), _auth: dict = Depends(require_perm(PERM_EDITAR))):
    """Reordena jobs sem tocar em lineage (etl_pipeline_job_reorder)."""
    pipeline_name = (body.get("pipeline_name") or "").strip()
    if not pipeline_name:
        raise HTTPException(status_code=422, detail="pipeline_name é obrigatório")

    jobs_raw = body.get("jobs")
    if jobs_raw:
        if not isinstance(jobs_raw, list) or len(jobs_raw) == 0:
            raise HTTPException(status_code=422, detail="jobs deve ser lista não vazia")
        jobs = jobs_raw
    else:
        job_name = body.get("job_name")
        order    = body.get("execution_order")
        if not job_name or order is None:
            raise HTTPException(status_code=422, detail="Informe jobs[] ou job_name+execution_order")
        jobs = [{"job_name": job_name, "execution_order": int(order)}]

    erros = []
    for idx, j in enumerate(jobs):
        name  = (j.get("job_name") or "").strip()
        order = j.get("execution_order")
        if not name or order is None:
            erros.append(f"Item {idx}: job_name e execution_order obrigatórios")
        elif int(order) < 1:
            erros.append(f"Item {idx} ({name}): execution_order deve ser >= 1")
    if erros:
        raise HTTPException(status_code=422, detail={"errors": erros})

    try:
        conn = get_db_conn(); cur = conn.cursor()
        for j in jobs:
            cur.execute(
                "EXEC dbo.sp_etl_pipeline_job_reorder @pipeline_name=?, @job_name=?, @execution_order=?",
                (pipeline_name, j["job_name"].strip(), int(j["execution_order"])),
            )
        conn.commit()
        cur.close(); conn.close()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro DB: {e}")
    return {"ok": True, "pipeline_name": pipeline_name, "jobs_reordered": len(jobs)}


@router.get("/pipelines/jobs/{pipeline_name}/{job_name}", tags=["jobs"])
def get_pipeline_job(
    pipeline_name: str,
    job_name: str,
    _auth: dict = Depends(get_current_user),
):
    """Retorna detalhes de um job específico."""
    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute(
            """SELECT j.pipeline_name, j.job_name, CAST(j.execution_order AS INT),
                      ISNULL(j.job_type,'datastage'), ISNULL(j.job_command,''),
                      CAST(ISNULL(j.active,1) AS INT), ISNULL(j.ssh_conn_id,''),
                      CAST(ISNULL(j.verbose_log,0) AS INT), ISNULL(j.mssql_conn_id,'')
               FROM dbo.etl_pipeline_job j
               WHERE j.pipeline_name=? AND j.job_name=?""",
            (pipeline_name, job_name),
        )
        row = cur.fetchone()
        if not row:
            cur.close(); conn.close()
            raise HTTPException(status_code=404, detail=f"Job '{job_name}' não encontrado no pipeline '{pipeline_name}'")
        cur.execute(
            """SELECT param_name, param_type, param_value, param_order
               FROM dbo.etl_pipeline_job_param
               WHERE pipeline_name=? AND job_name=?
               ORDER BY param_order""",
            (pipeline_name, job_name),
        )
        params = [{"param_name": r[0], "param_type": r[1], "param_value": r[2], "param_order": r[3]}
                   for r in cur.fetchall()]
        depends_on_jobs = None
        try:
            cur.execute(
                "SELECT depends_on_jobs FROM dbo.etl_pipeline_job "
                "WHERE pipeline_name=? AND job_name=?", (pipeline_name, job_name))
            dr = cur.fetchone()
            depends_on_jobs = (dr[0] if dr else None)
        except Exception:
            depends_on_jobs = None  # coluna pode não existir (migration 038)
        mssql_database = None
        try:
            cur.execute(
                "SELECT mssql_database FROM dbo.etl_pipeline_job "
                "WHERE pipeline_name=? AND job_name=?", (pipeline_name, job_name))
            mr = cur.fetchone()
            mssql_database = (mr[0] if mr else None)
        except Exception:
            mssql_database = None  # coluna pode não existir (migration 039)
        condition = None
        try:
            cur.execute(
                "SELECT condition_json FROM dbo.etl_pipeline_job "
                "WHERE pipeline_name=? AND job_name=?", (pipeline_name, job_name))
            cr = cur.fetchone()
            if cr and cr[0]:
                try:
                    condition = json.loads(cr[0])
                except (ValueError, TypeError):
                    condition = None
        except Exception:
            condition = None  # coluna pode não existir (migration 043)
        notify = None
        try:
            cur.execute(
                "SELECT notify_json FROM dbo.etl_pipeline_job "
                "WHERE pipeline_name=? AND job_name=?", (pipeline_name, job_name))
            nr = cur.fetchone()
            if nr and nr[0]:
                try:
                    notify = json.loads(nr[0])
                except (ValueError, TypeError):
                    notify = None
        except Exception:
            notify = None  # coluna pode não existir (migration 049)
        sql_node = None
        try:
            cur.execute(
                "SELECT sql_json FROM dbo.etl_pipeline_job "
                "WHERE pipeline_name=? AND job_name=?", (pipeline_name, job_name))
            sr = cur.fetchone()
            if sr and sr[0]:
                try:
                    sql_node = json.loads(sr[0])
                except (ValueError, TypeError):
                    sql_node = None
        except Exception:
            sql_node = None  # coluna pode não existir (migration 051)
        cur.close(); conn.close()
        return {
            "pipeline_name": row[0], "job_name": row[1], "execution_order": row[2],
            "job_type": row[3], "job_command": row[4] or None, "active": bool(row[5]),
            "ssh_conn_id": row[6] or None, "verbose_log": bool(row[7]),
            "mssql_conn_id": row[8] or None, "params": params,
            "depends_on_jobs": depends_on_jobs,
            "mssql_database": mssql_database,
            "condition": condition,
            "notify": notify,
            "sql_node": sql_node,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro DB: {e}")


@router.delete("/pipelines/jobs/{pipeline_name}/{job_name}", tags=["jobs"])
async def delete_pipeline_job(
    pipeline_name: str,
    job_name: str,
    _auth: dict = Depends(require_perm(PERM_EDITAR)),
):
    """Remove um job de pipeline (etl_pipeline_job) e sua lineage associada."""
    pipeline_name = pipeline_name.strip()
    job_name = job_name.strip()
    if not pipeline_name or not job_name:
        raise HTTPException(status_code=422, detail="pipeline_name e job_name são obrigatórios")
    try:
        conn = get_db_conn(); cur = conn.cursor()
        # Remove a lineage associada antes do job (evita órfãos e respeita FK, se existir).
        cur.execute(
            "DELETE FROM dbo.etl_job_lineage WHERE pipeline_name = ? AND job_name = ?",
            (pipeline_name, job_name),
        )
        cur.execute(
            "DELETE FROM dbo.etl_pipeline_job WHERE pipeline_name = ? AND job_name = ?",
            (pipeline_name, job_name),
        )
        rows = cur.rowcount
        if rows == 0:
            conn.rollback()
            cur.close(); conn.close()
            raise HTTPException(status_code=404, detail=f"Job '{job_name}' não encontrado no pipeline '{pipeline_name}'")
        conn.commit()
        cur.close(); conn.close()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro DB: {e}")
    return {"ok": True, "pipeline_name": pipeline_name, "job_name": job_name}


def _parse_dep_csv(raw) -> list[str]:
    """CSV de depends_on_jobs → lista (vazio = [])."""
    return [d.strip() for d in str(raw or "").split(",") if d.strip()]


@router.get("/pipelines/{pipeline_name}/fluxo", tags=["jobs"])
def get_pipeline_fluxo(
    pipeline_name: str,
    _auth: dict = Depends(get_current_user),
):
    """Grafo de etapas para o editor interativo de fluxo (canvas).

    Para cada etapa: dependências (CSV → lista), condição da decisão
    (condition_json → objeto) e posição salva (layout_x/y). Degrada para
    {"nodes": []} se a tabela não existir e para layout null se a 048 não
    rodou."""
    pipeline_name = (pipeline_name or "").strip()
    try:
        conn = get_db_conn(); cur = conn.cursor()
    except Exception as e:
        log.warning("get_pipeline_fluxo sem conexão: %s", e)
        return {"nodes": []}
    try:
        # Detecta colunas opcionais (como o GET /jobs faz): depends_on_jobs (mig
        # 038), condition_json (043) e layout_x/y (048) podem não existir — sem
        # essa checagem, um SELECT direto falha e um pipeline EXISTENTE aparece
        # VAZIO no canvas. Para as ausentes, seleciona NULL.
        try:
            cur.execute(
                "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
                "WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME='etl_pipeline_job'")
            cols = {r[0].lower() for r in cur.fetchall()}
        except Exception:
            cols = set()
        sel_deps = "j.depends_on_jobs" if "depends_on_jobs" in cols else "NULL"
        sel_cond = "j.condition_json" if "condition_json" in cols else "NULL"
        sel_notify = "j.notify_json" if "notify_json" in cols else "NULL"
        sel_sql = "j.sql_json" if "sql_json" in cols else "NULL"
        sel_lx = "j.layout_x" if "layout_x" in cols else "NULL"
        sel_ly = "j.layout_y" if "layout_y" in cols else "NULL"
        # Campos por tipo (round-trip do painel inline): ssh / verbose / mssql_*.
        sel_ssh = "j.ssh_conn_id" if "ssh_conn_id" in cols else "NULL"
        sel_verb = "j.verbose_log" if "verbose_log" in cols else "NULL"
        sel_mconn = "j.mssql_conn_id" if "mssql_conn_id" in cols else "NULL"
        sel_mdb = "j.mssql_database" if "mssql_database" in cols else "NULL"
        try:
            cur.execute(
                "SELECT j.job_name, ISNULL(j.job_type,'datastage'), j.job_command, "
                f"CAST(j.execution_order AS INT), {sel_deps}, {sel_cond}, {sel_lx}, {sel_ly}, "
                f"{sel_ssh}, {sel_verb}, {sel_mconn}, {sel_mdb}, {sel_notify}, {sel_sql} "
                "FROM dbo.etl_pipeline_job j WHERE j.pipeline_name=? "
                "ORDER BY j.execution_order, j.job_name",
                (pipeline_name,))
            rows = cur.fetchall()
        except Exception as e:
            # Tabela/coluna ausente → degrada para vazio (ex.: 038/043 não rodaram).
            log.warning("get_pipeline_fluxo degradou (%s): %s", pipeline_name, e)
            cur.close(); conn.close()
            return {"nodes": []}
        # Parâmetros (storedproc) — uma query agrupada por job. Se a TABELA não
        # existe → params vazio (feature ausente). Se existe mas a query falha
        # (ex.: timeout transitório), NÃO degrada para [] silenciosamente: deixa
        # propagar para o handler externo (→ {nodes: []}), senão o save seguinte
        # faria param_clear e apagaria os parâmetros REAIS de um storedproc.
        params_by_job: dict[str, list] = {}
        cur.execute(
            "SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES "
            "WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME='etl_pipeline_job_param'")
        if cur.fetchone()[0]:
            cur.execute(
                "SELECT job_name, param_name, param_type, param_value "
                "FROM dbo.etl_pipeline_job_param WHERE pipeline_name=? "
                "ORDER BY job_name, param_order", (pipeline_name,))
            for pr in cur.fetchall():
                params_by_job.setdefault(pr[0], []).append(
                    {"param_name": pr[1], "param_type": pr[2], "param_value": pr[3]})
        nodes = []
        for r in rows:
            condition = None
            if r[5]:
                try:
                    condition = json.loads(r[5])
                except (ValueError, TypeError):
                    condition = None
            notify = None
            if r[12]:
                try:
                    notify = json.loads(r[12])
                except (ValueError, TypeError):
                    notify = None
            sql_node = None
            if r[13]:
                try:
                    sql_node = json.loads(r[13])
                except (ValueError, TypeError):
                    sql_node = None
            lx = float(r[6]) if r[6] is not None else None
            ly = float(r[7]) if r[7] is not None else None
            nodes.append({
                "job_name": r[0],
                "job_type": r[1],
                "job_command": r[2] or None,
                "execution_order": r[3],
                "depends_on_jobs": _parse_dep_csv(r[4]),
                "condition": condition,
                "notify": notify,
                "sql_node": sql_node,
                "layout_x": lx,
                "layout_y": ly,
                "ssh_conn_id": r[8] or None,
                "verbose_log": bool(r[9]) if r[9] is not None else False,
                "mssql_conn_id": r[10] or None,
                "mssql_database": r[11] or None,
                "params": params_by_job.get(r[0], []),
            })
        cur.close(); conn.close()
        return {"nodes": nodes}
    except Exception as e:
        log.warning("get_pipeline_fluxo erro inesperado (%s): %s", pipeline_name, e)
        return {"nodes": []}


@router.post("/pipelines/{pipeline_name}/fluxo", tags=["jobs"])
async def save_pipeline_fluxo(
    pipeline_name: str,
    body: dict = Body(default={}),
    _auth: dict = Depends(require_perm(PERM_EDITAR)),
):
    """Persiste o fluxo do editor — reconciliação completa.

    Para cada nó: NOVOS são inseridos via sp_etl_pipeline_job_upsert (job_type/
    command/order/ssh/verbose/mssql_conn_id) + mssql_database. EXISTENTES recebem
    UPDATE direcionado SÓ dos campos cujas CHAVES vieram no payload (job_command,
    execution_order, ssh_conn_id, verbose_log, mssql_conn_id, mssql_database) —
    assim um frontend antigo que omite um campo não o zera; job_type, params e
    lineage do nó existente são preservados. Para TODOS grava, por-coluna:
    depends_on_jobs, condition_json (ramos+expressão da decisão; só em decisão) e
    layout_x/y. Os job_name em `deleted` são removidos (com a lineage). Valida a
    condição de cada decisão (_validate_condition) e detecta ciclo incluindo as
    arestas de ramo (_graph_has_cycle). Tudo transacional; degrada por-coluna em
    ambientes sem as colunas opcionais.

    Payload:
      nodes:   [{job_name, job_type, job_command, execution_order,
                 depends_on_jobs[], condition{...}|null, layout_x, layout_y}]
      deleted: [job_name, ...]   # opcional — nós removidos no canvas
    """
    pipeline_name = (pipeline_name or "").strip()
    if not pipeline_name:
        raise HTTPException(status_code=422, detail="pipeline_name é obrigatório")

    nodes = body.get("nodes")
    if not isinstance(nodes, list):
        raise HTTPException(status_code=422, detail="nodes deve ser uma lista")
    deleted_raw = body.get("deleted")
    deleted = ({str(d).strip() for d in deleted_raw if str(d).strip()}
               if isinstance(deleted_raw, list) else set())

    # Conexões MSSQL só importam se houver decisão OU nó SQL a validar (a decisão
    # pode trazer mssql_conn_id; o nó SQL exige um conn_id válido). Evita ida ao
    # Airflow quando nenhum dos dois está presente.
    _needs_conn = any(
        isinstance(n, dict) and (n.get("job_type") or "").lower().strip() in ("decisao", "sql")
        for n in nodes)
    mssql_conn_ids = await _list_mssql_conn_ids() if _needs_conn else None

    try:
        conn = get_db_conn(); cur = conn.cursor()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro DB: {e}")
    try:
        # Jobs que pertencem ao pipeline hoje (ownership / base da reconciliação).
        try:
            cur.execute("SELECT job_name FROM dbo.etl_pipeline_job WHERE pipeline_name=?",
                        (pipeline_name,))
            owned = {r[0] for r in cur.fetchall()}
        except Exception as e:
            cur.close(); conn.close()
            raise HTTPException(status_code=500, detail=f"Erro DB: {e}")

        # Colunas opcionais (degrada em ambientes sem 038/043/048).
        try:
            cur.execute(
                "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
                "WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME='etl_pipeline_job'")
            _cols = {r[0].lower() for r in cur.fetchall()}
        except Exception:
            _cols = set()
        has_deps = "depends_on_jobs" in _cols
        has_cond = "condition_json" in _cols
        has_notify = "notify_json" in _cols
        has_sql = "sql_json" in _cols
        has_layout = "layout_x" in _cols and "layout_y" in _cols
        has_db = "mssql_database" in _cols
        has_ssh = "ssh_conn_id" in _cols
        has_verb = "verbose_log" in _cols
        has_mconn = "mssql_conn_id" in _cols

        # Conjunto final de jobs (o canvas envia o estado completo do fluxo) —
        # base para validar ramos e filtrar dependências.
        known_jobs = {(n.get("job_name") or "").strip() for n in nodes
                      if isinstance(n, dict) and (n.get("job_name") or "").strip()}

        # Valida e prepara cada nó; monta o grafo (deps + ramos) para o ciclo.
        errors: list[str] = []
        cycle_adj: dict[str, set[str]] = {n: set() for n in known_jobs}
        prepared = []  # (j_name, is_new, order, type, cmd, ssh, verbose, mssql, mdb, params_present, params, dep_csv, cond_json|None, notify_json|None, sql_json|None, lx, ly)
        raw_by_name: dict[str, dict] = {}  # nó cru por nome (checa presença de chave no UPDATE)
        seen: set[str] = set()
        for idx, node in enumerate(nodes):
            if not isinstance(node, dict):
                continue
            j_name = (node.get("job_name") or "").strip()
            if not j_name:
                errors.append(f"nó #{idx}: job_name é obrigatório"); continue
            if j_name in seen:
                errors.append(f"{j_name}: job_name duplicado no fluxo"); continue
            seen.add(j_name)
            if not _JOB_NAME_RE.match(j_name):
                errors.append(f"{j_name}: nome inválido (use letras, números, _ . -)"); continue
            j_type = (node.get("job_type") or "datastage").lower().strip()
            if j_type not in VALID_JOB_TYPES:
                errors.append(f"{j_name}: job_type '{j_type}' inválido"); continue
            is_new = j_name not in owned
            if is_new and not _JOB_NAME_STRICT_RE.match(j_name):
                errors.append(f"{j_name}: nome de nó novo não pode ter espaço "
                              "(vira task_id no Airflow, que o rejeita no import da DAG)"); continue

            j_cmd = node.get("job_command") or None
            try:
                j_order = int(node.get("execution_order")) if node.get("execution_order") is not None else 1
            except (ValueError, TypeError):
                j_order = 1
            j_ssh = (node.get("ssh_conn_id") or "").strip() or None
            j_verbose = 1 if node.get("verbose_log") else 0
            j_mssql = (node.get("mssql_conn_id") or "").strip() or None
            j_mdb = (node.get("mssql_database") or "").strip() or None
            raw_by_name[j_name] = node

            # Params (storedproc): valida e prepara; só serão gravados se a CHAVE
            # 'params' veio no payload (protege os params de um storedproc existente).
            params_present = "params" in node
            j_params = []
            if j_type == "storedproc" and isinstance(node.get("params"), list):
                vistos_p: set[str] = set()
                for pi, p in enumerate(node["params"]):
                    if not isinstance(p, dict):
                        continue
                    p_name = (p.get("param_name") or "").strip()
                    if not p_name:
                        continue  # linha de param vazia → ignora
                    p_type = (p.get("param_type") or "").strip().upper()
                    if not _PARAM_NAME_RE.match(p_name):
                        errors.append(f"{j_name}: parâmetro '{p_name}' inválido"); continue
                    if p_type not in VALID_PARAM_TYPES:
                        errors.append(f"{j_name}: parâmetro '{p_name}' com tipo inválido"); continue
                    key = p_name.lstrip("@").lower()
                    if key in vistos_p:
                        errors.append(f"{j_name}: parâmetro '{p_name}' duplicado"); continue
                    vistos_p.add(key)
                    j_params.append((p_name, p_type, p.get("param_value"), pi))

            # Dependências NORMAIS (só entre jobs do fluxo) → arestas predecessor→job.
            dep_raw = node.get("depends_on_jobs")
            if isinstance(dep_raw, list):
                dep_list = [str(d).strip() for d in dep_raw if str(d).strip()]
            else:
                dep_list = _parse_dep_csv(dep_raw)
            dep_list = [d for d in dep_list if d in known_jobs and d != j_name]
            for d in dep_list:
                cycle_adj[d].add(j_name)
            dep_csv = ",".join(dep_list) or None

            # Condição da decisão — valida e registra as arestas de ramo p/ ciclo.
            cond_json_str = None
            if j_type == "decisao":
                raw_cond = node.get("condition")
                if not isinstance(raw_cond, dict):
                    errors.append(f"{j_name}: decisão sem condição (defina quando vai para sim/não)"); continue
                cond_errs = _validate_condition(raw_cond, known_jobs, j_name, mssql_conn_ids)
                if cond_errs:
                    errors.extend(f"{j_name}: {e}" for e in cond_errs); continue
                # Persiste o dict INTEIRO (job_name + child_job inclusos p/ linhas_job)
                # — round-trip garantido no GET /fluxo / get_pipeline_job.
                cond_json_str = json.dumps(_normalize_condition(raw_cond), ensure_ascii=False)
                for m in (raw_cond.get("ramo_verdadeiro") or []) + (raw_cond.get("ramo_falso") or []):
                    mn = str(m).strip()
                    if mn in cycle_adj:
                        cycle_adj[j_name].add(mn)   # decisão → membro do ramo

            # Notificação — valida a config (notify_json); grupo_id obrigatório.
            notify_json_str = None
            if j_type == "notificacao":
                raw_notify = node.get("notify")
                notify_errs = _validate_notify(raw_notify)
                if notify_errs:
                    errors.extend(f"{j_name}: {e}" for e in notify_errs); continue
                notify_json_str = json.dumps(_normalize_notify(raw_notify), ensure_ascii=False)

            # Nó SQL — valida a config (sql_json); SELECT read-only + conexão.
            sql_json_str = None
            if j_type == "sql":
                raw_sql = node.get("sql_node")
                sql_errs = _validate_sql_node_conn(raw_sql, mssql_conn_ids)
                if sql_errs:
                    errors.extend(f"{j_name}: {e}" for e in sql_errs); continue
                sql_json_str = json.dumps(_normalize_sql_node(raw_sql), ensure_ascii=False)

            lx, ly = node.get("layout_x"), node.get("layout_y")
            try:
                lx = float(lx) if lx is not None else None
            except (ValueError, TypeError):
                lx = None
            try:
                ly = float(ly) if ly is not None else None
            except (ValueError, TypeError):
                ly = None

            prepared.append((j_name, is_new, j_order, j_type, j_cmd, j_ssh,
                             j_verbose, j_mssql, j_mdb, params_present, j_params,
                             dep_csv, cond_json_str, notify_json_str, sql_json_str,
                             lx, ly))

        if errors:
            cur.close(); conn.close()
            raise HTTPException(status_code=422, detail={"errors": errors})

        if _graph_has_cycle(cycle_adj):
            cur.close(); conn.close()
            raise HTTPException(
                status_code=400,
                detail="ciclo detectado entre as etapas (dependências/ramos da decisão)")

        # ── Aplica (transacional) ─────────────────────────────────────────────
        # 1) Remove os jobs marcados (e a lineage) — só os que ainda existem e
        #    não voltaram no fluxo (proteção contra remoção acidental).
        removed = 0
        for d in deleted:
            if d in owned and d not in known_jobs:
                cur.execute("DELETE FROM dbo.etl_job_lineage WHERE pipeline_name=? AND job_name=?",
                            (pipeline_name, d))
                cur.execute("DELETE FROM dbo.etl_pipeline_job WHERE pipeline_name=? AND job_name=?",
                            (pipeline_name, d))
                removed += 1

        # 2) Materializa cada nó. NOVO → insere via sp_upsert (type/command/order/
        #    ssh/verbose/mssql_conn_id) + mssql_database. EXISTENTE → UPDATE
        #    direcionado SÓ dos campos cujas CHAVES vieram no payload (um frontend
        #    antigo que não envia um campo não o zera). job_type do existente é
        #    preservado (o painel não troca o tipo de um nó já salvo). Grava deps/
        #    condição (só decisão)/posição em TODOS (por-coluna).
        for (j_name, is_new, j_order, j_type, j_cmd, j_ssh, j_verbose,
             j_mssql, j_mdb, params_present, j_params, dep_csv, cond_json_str,
             notify_json_str, sql_json_str, lx, ly) in prepared:
            if is_new:
                cur.execute(
                    "EXEC dbo.sp_etl_pipeline_job_upsert "
                    "@pipeline_name=?, @job_name=?, @execution_order=?, @job_type=?, @job_command=?, "
                    "@ssh_conn_id=?, @verbose_log=?, @mssql_conn_id=?",
                    (pipeline_name, j_name, j_order, j_type, j_cmd, j_ssh, j_verbose, j_mssql))
                if has_db:
                    cur.execute("UPDATE dbo.etl_pipeline_job SET mssql_database=? "
                                "WHERE pipeline_name=? AND job_name=?",
                                (j_mdb, pipeline_name, j_name))
            else:
                node = raw_by_name.get(j_name, {})
                sets, vals = [], []
                if "job_command" in node:
                    sets.append("job_command=?"); vals.append(j_cmd)
                if "execution_order" in node:
                    sets.append("execution_order=?"); vals.append(j_order)
                if has_ssh and "ssh_conn_id" in node:
                    sets.append("ssh_conn_id=?"); vals.append(j_ssh)
                if has_verb and "verbose_log" in node:
                    sets.append("verbose_log=?"); vals.append(j_verbose)
                if has_mconn and "mssql_conn_id" in node:
                    sets.append("mssql_conn_id=?"); vals.append(j_mssql)
                if has_db and "mssql_database" in node:
                    sets.append("mssql_database=?"); vals.append(j_mdb)
                if sets:
                    cur.execute(
                        f"UPDATE dbo.etl_pipeline_job SET {', '.join(sets)} "
                        "WHERE pipeline_name=? AND job_name=?",
                        (*vals, pipeline_name, j_name))
            # Params (storedproc): só toca se a chave 'params' veio no payload
            # (um frontend que não envia params não apaga os existentes).
            if params_present and j_type == "storedproc":
                cur.execute("EXEC dbo.sp_etl_pipeline_job_param_clear "
                            "@pipeline_name=?, @job_name=?", (pipeline_name, j_name))
                for p_name, p_type, p_value, p_order in j_params:
                    cur.execute(
                        "EXEC dbo.sp_etl_pipeline_job_param_insert "
                        "@pipeline_name=?, @job_name=?, @param_name=?, @param_type=?, "
                        "@param_value=?, @param_order=?",
                        (pipeline_name, j_name, p_name, p_type, p_value, p_order))
            if has_deps:
                cur.execute("UPDATE dbo.etl_pipeline_job SET depends_on_jobs=? "
                            "WHERE pipeline_name=? AND job_name=?",
                            (dep_csv, pipeline_name, j_name))
            # Grava condition_json SÓ em decisão — nunca zera a condição de uma
            # etapa (o canvas não troca o tipo de um nó existente). Protege contra
            # um frontend antigo (sem job_type) apagar a condição de uma decisão.
            if has_cond and j_type == "decisao":
                cur.execute("UPDATE dbo.etl_pipeline_job SET condition_json=? "
                            "WHERE pipeline_name=? AND job_name=?",
                            (cond_json_str, pipeline_name, j_name))
            # Grava notify_json SÓ em notificação — análogo ao condition_json:
            # nunca zera a config de uma etapa de outro tipo (o canvas não troca o
            # tipo de um nó existente).
            if has_notify and j_type == "notificacao":
                cur.execute("UPDATE dbo.etl_pipeline_job SET notify_json=? "
                            "WHERE pipeline_name=? AND job_name=?",
                            (notify_json_str, pipeline_name, j_name))
            # Grava sql_json SÓ em nó SQL — análogo aos demais JSON por-tipo:
            # nunca zera a config de uma etapa de outro tipo.
            if has_sql and j_type == "sql":
                cur.execute("UPDATE dbo.etl_pipeline_job SET sql_json=? "
                            "WHERE pipeline_name=? AND job_name=?",
                            (sql_json_str, pipeline_name, j_name))
            if has_layout:
                cur.execute("UPDATE dbo.etl_pipeline_job SET layout_x=?, layout_y=? "
                            "WHERE pipeline_name=? AND job_name=?",
                            (lx, ly, pipeline_name, j_name))

        conn.commit()
        cur.close(); conn.close()
        return {"ok": True, "saved": len(prepared), "deleted": removed}
    except HTTPException:
        try:
            conn.rollback(); cur.close(); conn.close()
        except Exception:
            pass
        raise
    except Exception as e:
        try:
            conn.rollback(); cur.close(); conn.close()
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"Erro DB: {e}")
