"""api/routers/jobs.py — GET /jobs, POST/DELETE /pipelines/jobs, POST /pipelines/jobs/reorder."""
from __future__ import annotations

import json
import logging
import re
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException

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


VALID_JOB_TYPES = {"datastage", "shell", "python", "storedproc", "decisao"}
VALID_PARAM_TYPES = {"INT", "VARCHAR", "DATE", "BIT", "DECIMAL", "DATETIME"}
_PARAM_NAME_RE = re.compile(r"^@?[A-Za-z_][A-Za-z0-9_]*$")
# job_name vira literal de string no código da DAG gerada e argumento de shell no
# dsjob — allowlist bloqueia aspas/;/$/quebra-de-linha (anti code/command injection).
_JOB_NAME_RE = re.compile(r"^[A-Za-z0-9_.\- ]+$")
# nome de banco-alvo (storedproc, mesmo servidor) — vira nome de 3 partes
# [banco].schema.proc; allowlist bloqueia ] e demais chars perigosos (anti-injection).
_DB_NAME_RE = re.compile(r"^[A-Za-z0-9_.\-$#@ ]+$")

# ── Nó de Decisão (migration 043) ──────────────────────────────────────────
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_COND_OPERADORES = {"=", "<>", ">", ">=", "<", "<="}
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


def _validate_condition(cond, known_jobs, self_name, mssql_conn_ids) -> list[str]:
    """Valida a condição de um nó de decisão. Retorna lista de erros (vazia = ok)."""
    if not isinstance(cond, dict):
        return ["condição (condition_json) ausente ou inválida"]
    errs: list[str] = []
    tipo = str(cond.get("tipo") or "").strip().lower()
    if tipo not in ("contagem", "query"):
        errs.append("tipo da condição deve ser 'contagem' ou 'query'")
    if str(cond.get("operador") or "").strip() not in _COND_OPERADORES:
        errs.append("operador inválido (use =, <>, >, >=, <, <=)")
    valor = cond.get("valor")
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        errs.append("valor da condição é obrigatório")
    if tipo == "contagem":
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
    cid = (cond.get("mssql_conn_id") or "").strip()
    if cid and mssql_conn_ids is not None and cid not in mssql_conn_ids:
        errs.append(f"conexão MSSQL '{cid}' da condição não encontrada no Airflow")
    ramo_v, ramo_f = cond.get("ramo_verdadeiro") or [], cond.get("ramo_falso") or []
    if not isinstance(ramo_v, list) or not isinstance(ramo_f, list):
        errs.append("ramos (ramo_verdadeiro/ramo_falso) devem ser listas")
        return errs
    if not ramo_v and not ramo_f:
        errs.append("a decisão precisa de ao menos um job em algum ramo")
    for ramo_nome, ramo in (("verdadeiro", ramo_v), ("falso", ramo_f)):
        for m in ramo:
            mn = str(m).strip()
            if mn == self_name:
                errs.append(f"ramo {ramo_nome}: não pode referenciar a própria decisão")
            elif mn not in known_jobs:
                errs.append(f"ramo {ramo_nome}: job '{mn}' não existe no pipeline")
    return errs


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
    """Conexões MSSQL cadastradas no Airflow. None se a chamada falhar (não bloqueia o save)."""
    try:
        async with get_airflow_client() as client:
            r = await client.get("/api/v1/connections?limit=100")
            if not r.is_success:
                return None
            data = r.json()
            return {c["connection_id"] for c in data.get("connections", []) if c.get("conn_type") == "mssql"}
    except Exception:
        return None


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
def list_job_databases(_auth: dict = Depends(require_perm(PERM_EDITAR))):
    """Bancos disponíveis no MESMO servidor da conexão do ORQUESTRA, para o
    seletor de banco-alvo dos jobs storedproc (fase 1: 1 servidor).

    Usa a credencial do próprio app (get_db_conn) — não expõe senha. Degrada
    para lista vazia se a consulta ao catálogo falhar."""
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
                erros.append(f"Item {idx} ({j_name}): nome de job inválido — use apenas letras, números, _ . - e espaço"); continue
            if j_type not in VALID_JOB_TYPES:
                erros.append(f"Item {idx} ({j_name}): job_type '{j_type}' inválido"); continue
            # Nó de Decisão é roteador: não tem lineage (origem/destino).
            is_decisao = (j_type == "decisao")
            if not origens and not transfs and require_lineage and not is_decisao:
                erros.append(f"Item {idx} ({j_name}): ao menos 1 origem é obrigatória"); continue
            if not destinos and not transfs and require_lineage and not is_decisao:
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
                cond_json_str = json.dumps(raw_cond, ensure_ascii=False)
                for m in (raw_cond.get("ramo_verdadeiro") or []) + (raw_cond.get("ramo_falso") or []):
                    mn = str(m).strip()
                    if j_name in cycle_adj and mn in cycle_adj:
                        cycle_adj[j_name].add(mn)   # decisão → membro do ramo

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
        cur.close(); conn.close()
        return {
            "pipeline_name": row[0], "job_name": row[1], "execution_order": row[2],
            "job_type": row[3], "job_command": row[4] or None, "active": bool(row[5]),
            "ssh_conn_id": row[6] or None, "verbose_log": bool(row[7]),
            "mssql_conn_id": row[8] or None, "params": params,
            "depends_on_jobs": depends_on_jobs,
            "mssql_database": mssql_database,
            "condition": condition,
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
        sel_lx = "j.layout_x" if "layout_x" in cols else "NULL"
        sel_ly = "j.layout_y" if "layout_y" in cols else "NULL"
        try:
            cur.execute(
                "SELECT j.job_name, ISNULL(j.job_type,'datastage'), j.job_command, "
                f"CAST(j.execution_order AS INT), {sel_deps}, {sel_cond}, {sel_lx}, {sel_ly} "
                "FROM dbo.etl_pipeline_job j WHERE j.pipeline_name=? "
                "ORDER BY j.execution_order, j.job_name",
                (pipeline_name,))
            rows = cur.fetchall()
        except Exception as e:
            # Tabela/coluna ausente → degrada para vazio (ex.: 038/043 não rodaram).
            log.warning("get_pipeline_fluxo degradou (%s): %s", pipeline_name, e)
            cur.close(); conn.close()
            return {"nodes": []}
        nodes = []
        for r in rows:
            condition = None
            if r[5]:
                try:
                    condition = json.loads(r[5])
                except (ValueError, TypeError):
                    condition = None
            lx = float(r[6]) if r[6] is not None else None
            ly = float(r[7]) if r[7] is not None else None
            nodes.append({
                "job_name": r[0],
                "job_type": r[1],
                "job_command": r[2] or None,
                "execution_order": r[3],
                "depends_on_jobs": _parse_dep_csv(r[4]),
                "condition": condition,
                "layout_x": lx,
                "layout_y": ly,
            })
        cur.close(); conn.close()
        return {"nodes": nodes}
    except Exception as e:
        log.warning("get_pipeline_fluxo erro inesperado (%s): %s", pipeline_name, e)
        return {"nodes": []}


@router.post("/pipelines/{pipeline_name}/fluxo", tags=["jobs"])
def save_pipeline_fluxo(
    pipeline_name: str,
    body: dict = Body(default={}),
    _auth: dict = Depends(require_perm(PERM_EDITAR)),
):
    """Persiste dependências e posições dos nós do editor de fluxo.

    UPDATE direcionado: SÓ depends_on_jobs e layout_x/y (NÃO toca job_type,
    job_command, condition_json, params, lineage ou execution_order). Cada
    job_name deve pertencer ao pipeline; detecta ciclo (400) reusando
    _graph_has_cycle. layout_x/y só são gravados se a 048 já rodou."""
    pipeline_name = (pipeline_name or "").strip()
    if not pipeline_name:
        raise HTTPException(status_code=422, detail="pipeline_name é obrigatório")

    nodes = body.get("nodes")
    if not isinstance(nodes, list):
        raise HTTPException(status_code=422, detail="nodes deve ser uma lista")

    try:
        conn = get_db_conn(); cur = conn.cursor()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro DB: {e}")
    try:
        # Jobs que realmente pertencem ao pipeline (valida ownership).
        try:
            cur.execute("SELECT job_name FROM dbo.etl_pipeline_job WHERE pipeline_name=?",
                        (pipeline_name,))
            owned = {r[0] for r in cur.fetchall()}
        except Exception as e:
            cur.close(); conn.close()
            raise HTTPException(status_code=500, detail=f"Erro DB: {e}")

        # Colunas opcionais: depends_on_jobs (038) e layout_x/y (048) podem não
        # existir — monta o SET dinamicamente (não falha em ambientes antigos).
        try:
            cur.execute(
                "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
                "WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME='etl_pipeline_job'")
            _cols = {r[0].lower() for r in cur.fetchall()}
        except Exception:
            _cols = set()
        has_deps = "depends_on_jobs" in _cols
        has_layout = "layout_x" in _cols and "layout_y" in _cols

        # Monta o grafo resultante (deps enviadas) — só arestas entre jobs do
        # pipeline; detecta ciclo antes de gravar.
        adj: dict[str, set[str]] = {n: set() for n in owned}
        updates = []  # (job_name, dep_csv|None, layout_x, layout_y)
        for node in nodes:
            if not isinstance(node, dict):
                continue
            j_name = (node.get("job_name") or "").strip()
            if not j_name or j_name not in owned:
                continue  # ignora jobs que não pertencem ao pipeline
            dep_raw = node.get("depends_on_jobs")
            if isinstance(dep_raw, list):
                dep_list = [str(d).strip() for d in dep_raw if str(d).strip()]
            else:
                dep_list = _parse_dep_csv(dep_raw)
            # Só mantém arestas para jobs do pipeline (predecessor → job).
            dep_list = [d for d in dep_list if d in owned]
            for d in dep_list:
                adj[d].add(j_name)
            dep_csv = ",".join(dep_list) or None
            lx = node.get("layout_x")
            ly = node.get("layout_y")
            try:
                lx = float(lx) if lx is not None else None
            except (ValueError, TypeError):
                lx = None
            try:
                ly = float(ly) if ly is not None else None
            except (ValueError, TypeError):
                ly = None
            updates.append((j_name, dep_csv, lx, ly))

        if _graph_has_cycle(adj):
            cur.close(); conn.close()
            raise HTTPException(
                status_code=400,
                detail="ciclo detectado entre as etapas (dependências)")

        for j_name, dep_csv, lx, ly in updates:
            sets, vals = [], []
            if has_deps:
                sets.append("depends_on_jobs=?"); vals.append(dep_csv)
            if has_layout:
                sets.append("layout_x=?"); sets.append("layout_y=?"); vals += [lx, ly]
            if not sets:
                continue  # nada a persistir neste ambiente (colunas ausentes)
            cur.execute(
                f"UPDATE dbo.etl_pipeline_job SET {', '.join(sets)} "
                "WHERE pipeline_name=? AND job_name=?",
                (*vals, pipeline_name, j_name))
        conn.commit()
        cur.close(); conn.close()
        return {"ok": True, "updated": len(updates)}
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
