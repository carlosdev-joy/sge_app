"""api/routers/pipelines.py — GET /pipelines, POST /pipelines/register, GET /malha."""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from datetime import date, datetime, timezone, timedelta
from typing import Optional

import httpx
from fastapi import APIRouter, Body, Depends, HTTPException, Query

from db import get_db_conn
from deps import (
    AIRFLOW_URL, AIRFLOW_USER, AIRFLOW_PASSWORD,
    PERM_EDITAR, PERM_EXECUTAR,
    get_current_user, require_perm,
)
from services.notify import add_notificacao
from services.dag_reconcile import enqueue as enqueue_dag_pendente

log = logging.getLogger("orquestra-api")

router = APIRouter()

LOCAL_TZ = timezone(timedelta(hours=-3))  # America/Sao_Paulo

# dag_id no Airflow == pipeline_name exato; valida antes de interpolar na URL.
_DAG_ID_RE = re.compile(r"^[A-Za-z0-9_.\-]+$")
FACTORY_DAG_ID = "etl_dag_factory"


def _fmt_dt(v):
    if v is None:
        return None
    if hasattr(v, "strftime"):
        return v.strftime("%Y-%m-%d %H:%M:%S")
    return str(v)


async def _sync_airflow_pause(dag_id: str, paused: bool) -> dict:
    """Alinha o estado da DAG no Airflow ao status do pipeline no Orquestra.

    Inativar pipeline (active=0) → pausa a DAG (is_paused=True), tirando-a do
    agendamento; ativar (active=1) → despausa. Se a DAG ainda não existe no
    Airflow, nada a fazer. É best-effort: falha de rede/Airflow NÃO aborta o
    cadastro — o resultado volta no payload para a UI avisar o operador.

    Retorna: {"attempted", "exists", "is_paused", "error"}.
    """
    result: dict = {"attempted": True, "exists": None, "is_paused": None, "error": None}
    if not _DAG_ID_RE.match(dag_id or ""):
        result.update(attempted=False, error="dag_id inválido")
        return result
    try:
        async with httpx.AsyncClient(
            base_url=AIRFLOW_URL, auth=(AIRFLOW_USER, AIRFLOW_PASSWORD), timeout=15
        ) as client:
            g = await client.get(f"/api/v1/dags/{dag_id}")
            if g.status_code == 404:
                result["exists"] = False
                return result
            if not g.is_success:
                result["error"] = f"GET dag retornou {g.status_code}"
                return result
            result["exists"] = True
            cur_paused = bool(g.json().get("is_paused", True))
            if cur_paused != paused:
                p = await client.patch(
                    f"/api/v1/dags/{dag_id}",
                    json={"is_paused": paused},
                    headers={"Content-Type": "application/json"},
                )
                if not p.is_success:
                    result["is_paused"] = cur_paused
                    result["error"] = f"PATCH is_paused {p.status_code}: {p.text[:200]}"
                    return result
                try:
                    cur_paused = bool(p.json().get("is_paused", paused))
                except Exception:
                    cur_paused = paused
                log.info("[PIPELINE] DAG %s is_paused=%s sincronizado no Airflow", dag_id, cur_paused)
            result["is_paused"] = cur_paused
            return result
    except Exception as e:
        result["error"] = str(e)
        log.warning("[PIPELINE] sync Airflow dag=%s falhou: %s", dag_id, e)
        return result


# ── Helpers para register_pipeline ───────────────────────────────────────────

AUDIT_FIELDS = {
    "active", "scheduled_time", "schedule_type", "schedule_hour", "schedule_minute",
    "schedule_dow", "schedule_dom", "envia_msg_inicio", "envia_msg_fim", "envia_msg_erro",
    "project_name", "domain", "tags", "depends_on", "criticidade", "sla_minutos",
    "ambiente", "max_active_runs", "retries_count", "retry_delay_seconds", "pool_name", "descricao",
    "runbook_md",
}


def _build_cron(schedule_type, hour, minute, dow, dom):
    st = (schedule_type or "daily").strip().lower()
    h, m = int(hour or 0), int(minute or 0)
    if st == "hourly":   return f"{m} * * * *"
    if st == "daily":    return f"{m} {h} * * *"
    if st == "weekly":   return f"{m} {h} * * {int(dow or 1)}"
    if st == "monthly":  return f"{m} {h} {int(dom or 1)} * *"
    if st == "biweekly":                       # quinzenal: dia D e D+15
        d = int(dom or 1)
        return f"{m} {h} {d},{d + 15} * *"
    return f"{m} {h} * * *"


_TIME_RE = re.compile(r"^(\d{1,2}):(\d{1,2})$")


def _validate_dias_horarios_mes(raw):
    """Valida e normaliza o JSON de dias_horarios_mes (schedule_type 'monthly_days_times').

    Formato esperado: [{"dia": 1, "horarios": ["09:00"]}, ...] — 1 a 5 dias
    (1-28, sem repetir), cada um com 1 a 5 horários HH:MM (sem repetir no
    mesmo dia). Retorna a string JSON normalizada (dias e horários
    ordenados) ou None se raw for vazio.
    """
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        raise HTTPException(status_code=422, detail="dias_horarios_mes deve ser um JSON válido")
    if not isinstance(data, list) or not (1 <= len(data) <= 5):
        raise HTTPException(status_code=422, detail="dias_horarios_mes deve ter entre 1 e 5 dias")
    seen_days: set[int] = set()
    normalized = []
    for entry in data:
        if not isinstance(entry, dict) or "dia" not in entry or "horarios" not in entry:
            raise HTTPException(status_code=422, detail="Cada entrada de dias_horarios_mes precisa de 'dia' e 'horarios'")
        dia = entry["dia"]
        if not isinstance(dia, int) or isinstance(dia, bool) or not (1 <= dia <= 28):
            raise HTTPException(status_code=422, detail=f"Dia do mês inválido: {dia!r} (use 1-28)")
        if dia in seen_days:
            raise HTTPException(status_code=422, detail=f"Dia {dia} duplicado em dias_horarios_mes")
        seen_days.add(dia)
        horarios = entry["horarios"]
        if not isinstance(horarios, list) or not (1 <= len(horarios) <= 5):
            raise HTTPException(status_code=422, detail=f"Dia {dia} deve ter entre 1 e 5 horários")
        seen_times: set[str] = set()
        norm_times = []
        for t in horarios:
            if not isinstance(t, str):
                raise HTTPException(status_code=422, detail=f"Horário inválido no dia {dia}: {t!r}")
            m = _TIME_RE.match(t.strip())
            if not m:
                raise HTTPException(status_code=422, detail=f"Horário inválido no dia {dia}: '{t}' (use HH:MM)")
            hh, mm = int(m.group(1)), int(m.group(2))
            if not (0 <= hh <= 23 and 0 <= mm <= 59):
                raise HTTPException(status_code=422, detail=f"Horário fora do intervalo no dia {dia}: '{t}'")
            norm = f"{hh:02d}:{mm:02d}"
            if norm in seen_times:
                raise HTTPException(status_code=422, detail=f"Horário duplicado no dia {dia}: '{norm}'")
            seen_times.add(norm)
            norm_times.append(norm)
        normalized.append({"dia": dia, "horarios": sorted(norm_times)})
    normalized.sort(key=lambda e: e["dia"])
    return json.dumps(normalized)


def _get_valid_projects(cur):
    try:
        cur.execute("SELECT project_name FROM dbo.etl_project WHERE ativo=1")
        rows = cur.fetchall()
        if rows:
            return {r[0] for r in rows}
    except Exception:
        pass
    return {"BI_CVP", "BI_VIDA", "BI_PRESTAMISTA", "BI_PREVIDENCIA"}


def _hora_ou_nulo(valor):
    """'08:00' → '08:00:00' para o SQL Server; vazio/inválido → None.

    Silencia valor inválido em vez de recusar o cadastro inteiro: os três campos
    de horário são opcionais e um lixo digitado num deles não pode impedir de
    salvar o resto do pipeline.
    """
    texto = str(valor or "").strip()
    if not texto:
        return None
    partes = texto.split(":")
    if len(partes) < 2:
        return None
    try:
        h, m = int(partes[0]), int(partes[1])
    except ValueError:
        return None
    if not (0 <= h <= 23 and 0 <= m <= 59):
        return None
    return f"{h:02d}:{m:02d}:00"


def _dependencias_de(cur, pipeline_name):
    """Predecessores diretos de um pipeline.

    Lê da tabela (migration 067) e cai no CSV `depends_on` enquanto ela não
    existir — deploy que leva a API antes da migration continua validando pelo
    caminho antigo em vez de aceitar tudo.
    """
    try:
        cur.execute(
            "SELECT depende_de FROM dbo.etl_pipeline_dependencia "
            "WHERE pipeline_name = ? AND tipo = 'PIPELINE'", (pipeline_name,))
        return [str(r[0]).strip() for r in cur.fetchall() if r[0]]
    except Exception:
        cur.execute("SELECT depends_on FROM dbo.etl_pipeline WHERE pipeline_name = ?", (pipeline_name,))
        row = cur.fetchone()
        raw = (str(row[0]).strip() if row and row[0] else "")
        return [d.strip() for d in raw.split(",") if d.strip()]


def _check_circular(cur, pipeline_name, depends_on_list):
    """Recusa dependência que fecha ciclo, olhando TODOS os caminhos.

    A versão anterior seguia apenas a PRIMEIRA dependência de cada nó
    (`raw.split(",")[0]`), então um ciclo que passasse pela segunda em diante
    passava batido: com A dependendo de 'X,B' e B de A, gravar B→A era aceito.
    Um ciclo travaria as duas pontas para sempre — nenhuma jamais libera a outra.

    Agora é uma busca em largura sobre o grafo inteiro, a partir de cada
    predecessor proposto. `visitados` é global à busca (e não por caminho):
    grafo em diamante convergiria de novo no mesmo nó e o custo explodiria à toa.
    """
    for dep in depends_on_list:
        if not dep:
            continue
        visitados, fila = set(), [dep]
        while fila:
            atual = fila.pop(0)
            if atual == pipeline_name:
                raise ValueError(
                    f"Dependência circular: '{pipeline_name}' → '{dep}' fecha um ciclo "
                    f"(o caminho volta para '{pipeline_name}')")
            if atual in visitados:
                continue
            visitados.add(atual)
            # Teto de segurança: malha grande não pode transformar um POST de
            # cadastro em varredura sem fim.
            if len(visitados) > 500:
                break
            fila.extend(_dependencias_de(cur, atual))


def _validar_existencia(cur, depends_on_list):
    """Todos os predecessores precisam existir. Devolve os que não existem.

    Sem isto, um nome digitado errado era aceito e virava espera infinita em
    produção: no modo sensor o pipeline falhava só depois de 1h; no modo Dataset
    ele nunca disparava e ninguém era avisado. A FK da migration 067 fecha a
    porta no banco; esta função existe para o usuário receber 422 com o nome
    errado em vez de um erro de constraint.
    """
    faltando = []
    for dep in depends_on_list:
        if not dep:
            continue
        cur.execute("SELECT 1 FROM dbo.etl_pipeline WHERE pipeline_name = ?", (dep,))
        if not cur.fetchone():
            faltando.append(dep)
    return faltando


def _gravar_dependencias(cur, pipeline_name, depends_on_list, usuario=None):
    """Sincroniza etl_pipeline_dependencia com a lista informada (replace-all).

    Degrada em silêncio se a migration 067 ainda não rodou: nesse caso o CSV
    `depends_on` — que continua sendo escrito em espelho até a F6 — segue como
    única fonte, e o cadastro não quebra num deploy parcial.
    """
    try:
        cur.execute(
            "DELETE FROM dbo.etl_pipeline_dependencia "
            "WHERE pipeline_name = ? AND tipo = 'PIPELINE'", (pipeline_name,))
        for dep in depends_on_list:
            if dep:
                cur.execute(
                    "INSERT INTO dbo.etl_pipeline_dependencia "
                    "(pipeline_name, depende_de, tipo, criado_por) VALUES (?,?, 'PIPELINE', ?)",
                    (pipeline_name, dep, (usuario or "")[:100] or None))
        return True
    except Exception as e:
        log.warning("[PIPELINE] dependências não gravadas na tabela (migration 067 aplicada?): %s", e)
        return False


def _read_pipeline_record(cur, pipeline_name):
    base_cols = """active, scheduled_time, schedule_type, schedule_hour, schedule_minute,
                  schedule_dow, schedule_dom, envia_msg_inicio, envia_msg_fim, envia_msg_erro,
                  project_name, domain, tags, depends_on, criticidade, sla_minutos, ambiente,
                  max_active_runs, retries_count, retry_delay_seconds, pool_name, descricao"""
    try:
        cur.execute(
            f"SELECT {base_cols}, runbook_md FROM dbo.etl_pipeline WHERE pipeline_name = ?",
            (pipeline_name,),
        )
    except Exception:
        # runbook_md pode não existir ainda (migration 013)
        cur.execute(
            f"SELECT {base_cols} FROM dbo.etl_pipeline WHERE pipeline_name = ?",
            (pipeline_name,),
        )
    row = cur.fetchone()
    if row is None:
        return None
    cols = [d[0] for d in cur.description]
    return dict(zip(cols, row))


def _write_audit(cur, pipeline_name, changed_by, old, new_vals):
    for field in AUDIT_FIELDS:
        old_val = str(old.get(field, "") or "")
        new_val = str(new_vals.get(field, "") or "")
        if old_val != new_val:
            cur.execute(
                "INSERT INTO dbo.etl_pipeline_audit "
                "(pipeline_name, changed_by, field_name, old_value, new_value, changed_at) "
                "VALUES (?, ?, ?, ?, ?, GETDATE())",
                (pipeline_name, changed_by, field, old_val, new_val),
            )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/pipelines/projects", tags=["pipelines"])
def list_pipeline_projects():
    """Lista projetos disponíveis para uso em formulários."""
    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute("SELECT project_name FROM dbo.etl_project WHERE ativo=1 ORDER BY project_name")
        rows = cur.fetchall()
        cur.close(); conn.close()
        if rows:
            return {"projects": [r[0] for r in rows]}
    except Exception:
        pass
    return {"projects": ["BI_CVP", "BI_VIDA", "BI_PRESTAMISTA", "BI_PREVIDENCIA"]}


@router.get("/pipelines/domains", tags=["pipelines"])
def list_pipeline_domains():
    """Domínios já cadastrados (distintos) — para autocompletar no formulário e
    evitar variações parecidas na base."""
    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute("SELECT DISTINCT domain FROM dbo.etl_pipeline "
                    "WHERE domain IS NOT NULL AND LTRIM(RTRIM(domain)) <> '' "
                    "ORDER BY domain")
        rows = cur.fetchall()
        cur.close(); conn.close()
        return {"domains": [r[0] for r in rows]}
    except Exception:
        return {"domains": []}


@router.get("/pipelines/projects/all", tags=["pipelines"])
def list_all_pipeline_projects(_auth: dict = Depends(require_perm(PERM_EDITAR))):
    """Lista todos os projetos (ativos e inativos) para gerenciamento no admin."""
    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute("SELECT project_name, CAST(ativo AS INT) AS ativo FROM dbo.etl_project ORDER BY project_name")
        rows = cur.fetchall()
        cur.close(); conn.close()
        return {"projects": [{"project_name": r[0], "ativo": bool(r[1])} for r in rows]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/pipelines/projects", tags=["pipelines"])
def upsert_pipeline_project(body: dict = Body(default={}), _auth: dict = Depends(require_perm(PERM_EDITAR))):
    """Cria ou atualiza um projeto."""
    project_name = (body.get("project_name") or "").strip().upper()
    ativo = int(body.get("ativo", 1))
    if not project_name:
        raise HTTPException(status_code=422, detail="project_name é obrigatório")
    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute("SELECT COUNT(1) FROM dbo.etl_project WHERE project_name=?", (project_name,))
        exists = cur.fetchone()[0] > 0
        if exists:
            cur.execute("UPDATE dbo.etl_project SET ativo=? WHERE project_name=?", (ativo, project_name))
        else:
            cur.execute("INSERT INTO dbo.etl_project (project_name, ativo) VALUES (?, ?)", (project_name, ativo))
        conn.commit(); cur.close(); conn.close()
        return {"ok": True, "project_name": project_name, "ativo": bool(ativo)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/pipelines/projects/{project_name}", tags=["pipelines"])
def delete_pipeline_project(project_name: str, _auth: dict = Depends(require_perm(PERM_EDITAR))):
    """Remove um projeto (somente se não houver pipelines vinculados)."""
    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute("SELECT COUNT(1) FROM dbo.etl_pipeline WHERE project_name=?", (project_name,))
        count = cur.fetchone()[0]
        if count > 0:
            raise HTTPException(status_code=409, detail=f"Projeto possui {count} pipeline(s). Inative-o em vez de excluir.")
        cur.execute("DELETE FROM dbo.etl_project WHERE project_name=?", (project_name,))
        conn.commit(); cur.close(); conn.close()
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pipelines", tags=["pipelines"])
def list_pipelines(
    offset: int = 0,
    limit: int = 20,
    filter_name: Optional[str] = None,
    filter_project: Optional[str] = None,
    filter_active: Optional[int] = None,
):
    """Lista pipelines cadastrados (paginado). Substitui etl_pipeline_query."""
    limit = min(100, max(1, limit))
    offset = max(0, offset)
    fname = (filter_name or "").strip()
    fproj = (filter_project or "").strip()

    where = []
    params_count: list = []
    params_data: list  = []

    if fname:
        where.append("pipeline_name LIKE ?")
        params_count.append(f"%{fname}%")
        params_data.append(f"%{fname}%")
    if fproj:
        where.append("project_name = ?")
        params_count.append(fproj)
        params_data.append(fproj)
    if filter_active is not None:
        where.append("active = ?")
        params_count.append(int(filter_active))
        params_data.append(int(filter_active))

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    try:
        conn = get_db_conn()
        cur  = conn.cursor()

        cur.execute(f"SELECT COUNT(*) FROM dbo.etl_pipeline {where_sql}", params_count)
        total = cur.fetchone()[0]

        # runbook_md pode não existir ainda (migration 013) — degrada para NULL
        cur.execute("""
            SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME='etl_pipeline' AND COLUMN_NAME='runbook_md'
        """)
        runbook_col = "runbook_md" if cur.fetchone()[0] else "NULL AS runbook_md"

        # colunas da migration 017 (scheduling avançado) — degradam para defaults
        cur.execute("""
            SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME='etl_pipeline' AND COLUMN_NAME='calendario_nome'
        """)
        if cur.fetchone()[0]:
            sched_cols = ("calendario_nome, CAST(somente_dias_uteis AS INT) AS somente_dias_uteis, "
                          "CAST(trigger_por_dependencia AS INT) AS trigger_por_dependencia")
        else:
            sched_cols = ("NULL AS calendario_nome, 0 AS somente_dias_uteis, "
                          "0 AS trigger_por_dependencia")

        # colunas da migration 018 (horários múltiplos) — degradam para NULL
        cur.execute("""
            SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME='etl_pipeline' AND COLUMN_NAME='horarios_especificos'
        """)
        if cur.fetchone()[0]:
            sched_cols += ", horarios_especificos, dias_semana"
        else:
            sched_cols += ", NULL AS horarios_especificos, NULL AS dias_semana"

        # coluna da migration 024 (dia + hora específico) — degrada para NULL
        cur.execute("""
            SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME='etl_pipeline' AND COLUMN_NAME='dias_horarios_mes'
        """)
        if cur.fetchone()[0]:
            sched_cols += ", dias_horarios_mes"
        else:
            sched_cols += ", NULL AS dias_horarios_mes"

        # colunas da migration 031 (motivo de inativação) — degradam para NULL
        cur.execute("""
            SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME='etl_pipeline' AND COLUMN_NAME='motivo_inativacao'
        """)
        if cur.fetchone()[0]:
            inativ_cols = ("motivo_inativacao, inativado_por, "
                           "CONVERT(VARCHAR(19), inativado_em, 120) AS inativado_em")
        else:
            inativ_cols = ("NULL AS motivo_inativacao, NULL AS inativado_por, "
                           "NULL AS inativado_em")

        data_sql = f"""
            SELECT
                pipeline_name, project_name, domain, tags,
                CONVERT(VARCHAR(8), scheduled_time, 108) AS scheduled_time,
                schedule_type,
                CAST(schedule_hour   AS INT) AS schedule_hour,
                CAST(schedule_minute AS INT) AS schedule_minute,
                CAST(schedule_dow    AS INT) AS schedule_dow,
                CAST(schedule_dom    AS INT) AS schedule_dom,
                CAST(active          AS INT) AS active,
                CAST(dag_criada      AS INT) AS dag_criada,
                CAST(envia_msg_inicio AS INT) AS envia_msg_inicio,
                CAST(envia_msg_fim    AS INT) AS envia_msg_fim,
                CAST(envia_msg_erro   AS INT) AS envia_msg_erro,
                depends_on,
                CONVERT(VARCHAR(10), dag_start_date, 120) AS dag_start_date,
                descricao,
                ISNULL(criticidade, 'Media')   AS criticidade,
                sla_minutos,
                ISNULL(ambiente, 'PROD')       AS ambiente,
                ISNULL(CAST(max_active_runs    AS INT), 1)   AS max_active_runs,
                ISNULL(CAST(retries_count      AS INT), 1)   AS retries_count,
                ISNULL(CAST(retry_delay_seconds AS INT), 300) AS retry_delay_seconds,
                pool_name, {runbook_col}, {sched_cols}, {inativ_cols}, last_execution, created_at, updated_at
            FROM dbo.etl_pipeline
            {where_sql}
            ORDER BY project_name, domain, pipeline_name
            OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
        """
        params_data.extend([offset, limit])
        cur.execute(data_sql, params_data)
        cols = [
            "pipeline_name", "project_name", "domain", "tags", "scheduled_time",
            "schedule_type", "schedule_hour", "schedule_minute", "schedule_dow", "schedule_dom",
            "active", "dag_criada", "envia_msg_inicio", "envia_msg_fim", "envia_msg_erro",
            "depends_on", "dag_start_date", "descricao", "criticidade", "sla_minutos",
            "ambiente", "max_active_runs", "retries_count", "retry_delay_seconds",
            "pool_name", "runbook_md", "calendario_nome", "somente_dias_uteis",
            "trigger_por_dependencia", "horarios_especificos", "dias_semana",
            "dias_horarios_mes", "motivo_inativacao", "inativado_por", "inativado_em",
            "last_execution", "created_at", "updated_at",
        ]
        data = []
        for row in cur.fetchall():
            rec = dict(zip(cols, row))
            rec["last_execution"] = _fmt_dt(rec["last_execution"])
            rec["created_at"]     = _fmt_dt(rec["created_at"])
            rec["updated_at"]     = _fmt_dt(rec["updated_at"])
            data.append(rec)
        cur.close(); conn.close()

        pages = max(1, -(-total // limit))
        return {"total": total, "offset": offset, "limit": limit, "pages": pages, "data": data}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/pipelines/register", tags=["pipelines"])
async def register_pipeline(body: dict = Body(default={}), _auth: dict = Depends(require_perm(PERM_EDITAR))):
    """Cria ou atualiza um pipeline (etl_pipeline_register)."""
    pipeline    = (body.get("pipeline_name") or "").strip()
    horario     = (body.get("scheduled_time") or "").strip()
    if not pipeline or not horario:
        raise HTTPException(status_code=422, detail="pipeline_name e scheduled_time são obrigatórios")

    project          = body.get("project_name", "BI_CVP")
    active           = int(body.get("active",           1))
    envia_msg_inicio = int(body.get("envia_msg_inicio", 1))
    envia_msg_fim    = int(body.get("envia_msg_fim",    1))
    envia_msg_erro   = int(body.get("envia_msg_erro",   1))
    dag_criada       = int(body.get("dag_criada",       0))
    domain           = body.get("domain", "Geral")
    tags             = body.get("tags", "")
    depends_on_raw   = (body.get("depends_on") or "").strip()
    depends_on_list  = [d.strip() for d in depends_on_raw.split(",") if d.strip()]
    depends_on       = ",".join(depends_on_list) or None
    changed_by       = (body.get("changed_by") or "system").strip()
    dag_start_date   = (body.get("dag_start_date") or "").strip() or None
    schedule_type    = body.get("schedule_type")
    schedule_hour    = body.get("schedule_hour")
    schedule_minute  = body.get("schedule_minute")
    schedule_dow     = body.get("schedule_dow")
    schedule_dom     = body.get("schedule_dom")
    descricao        = (body.get("descricao") or "").strip() or None
    criticidade      = (body.get("criticidade") or "Media").strip()
    sla_minutos      = int(body["sla_minutos"]) if body.get("sla_minutos") is not None else None
    ambiente         = (body.get("ambiente") or "PROD").strip()
    max_active_runs  = int(body.get("max_active_runs",  1))
    retries_count    = int(body.get("retries_count",    1))
    retry_delay_secs = int(body.get("retry_delay_seconds", 300))
    pool_name        = (body.get("pool_name") or "").strip() or None
    runbook_md       = (body.get("runbook_md") or "").strip() or None
    # Migration 031 — motivo obrigatório ao inativar (por que o fluxo ficou indisponível)
    motivo_inativacao = (body.get("motivo_inativacao") or "").strip() or None
    # Fase 4 — scheduling avançado
    calendario_nome  = (body.get("calendario_nome") or "").strip() or None
    # Migration 067 — janela e virada do dia. Em branco vira NULL: "sem regra" é
    # diferente de "regra às 00:00".
    hora_virada             = _hora_ou_nulo(body.get("hora_virada"))
    nao_iniciar_antes       = _hora_ou_nulo(body.get("nao_iniciar_antes"))
    hora_limite_dependencia = _hora_ou_nulo(body.get("hora_limite_dependencia"))
    somente_dias_uteis      = int(body.get("somente_dias_uteis", 0))
    trigger_por_dependencia = int(body.get("trigger_por_dependencia", 0))
    # Migration 018 — horários múltiplos
    horarios_raw = (body.get("horarios_especificos") or "").strip()
    horarios_especificos = None
    if horarios_raw:
        _hrs = []
        for t in horarios_raw.split(","):
            t = t.strip()
            if not t:
                continue
            tp = t.split(":")
            try:
                hh, mm = int(tp[0]), int(tp[1]) if len(tp) > 1 else 0
            except ValueError:
                raise HTTPException(status_code=422, detail=f"Horário inválido: '{t}' (use HH:MM)")
            if not (0 <= hh <= 23 and 0 <= mm <= 59):
                raise HTTPException(status_code=422, detail=f"Horário fora do intervalo: '{t}'")
            _hrs.append(f"{hh:02d}:{mm:02d}")
        horarios_especificos = ",".join(sorted(set(_hrs))) or None
    dias_semana = (body.get("dias_semana") or "").strip() or None
    # Migration 024 — agendamento "Dia + Hora Específico"
    dias_horarios_mes = _validate_dias_horarios_mes(body.get("dias_horarios_mes"))
    if schedule_type == "monthly_days_times" and not dias_horarios_mes:
        raise HTTPException(status_code=422, detail="dias_horarios_mes é obrigatório para schedule_type 'monthly_days_times'")

    if pipeline in depends_on_list:
        raise HTTPException(status_code=422, detail="Pipeline não pode depender de si mesmo")

    if active == 0 and not motivo_inativacao:
        raise HTTPException(
            status_code=422,
            detail="Informe o motivo da inativação (por que o fluxo ficará indisponível).")

    try:
        conn = get_db_conn(); cur = conn.cursor()
        valid_projects = _get_valid_projects(cur)
        if project not in valid_projects:
            raise HTTPException(status_code=422, detail=f"project_name inválido: '{project}'")
        # Existência ANTES do ciclo: um nome inexistente não tem grafo para
        # percorrer, e o erro útil é "esse pipeline não existe", não "ciclo".
        faltando = _validar_existencia(cur, depends_on_list)
        if faltando:
            raise HTTPException(
                status_code=422,
                detail="Pipeline inexistente em 'depende de': "
                       + ", ".join(f"'{n}'" for n in faltando))
        _check_circular(cur, pipeline, depends_on_list)
        old_record = _read_pipeline_record(cur, pipeline)
        is_new = old_record is None

        cur.execute(
            "EXEC dbo.sp_etl_pipeline_upsert "
            "@pipeline_name=?, @scheduled_time=?, @schedule_type=?, @schedule_hour=?, "
            "@schedule_minute=?, @schedule_dow=?, @schedule_dom=?, @active=?, "
            "@envia_msg_inicio=?, @envia_msg_fim=?, @envia_msg_erro=?, @dag_criada=?, "
            "@project_name=?, @domain=?, @tags=?",
            (pipeline, horario, schedule_type, schedule_hour, schedule_minute, schedule_dow,
             schedule_dom, active, envia_msg_inicio, envia_msg_fim, envia_msg_erro,
             dag_criada, project, domain, tags),
        )
        cur.execute(
            "UPDATE dbo.etl_pipeline SET depends_on=?, dag_start_date=?, updated_at=GETDATE() "
            "WHERE pipeline_name=?",
            (depends_on, dag_start_date, pipeline),
        )
        # A tabela é a fonte da verdade a partir da 067; o CSV acima segue como
        # espelho até a F6, porque Malha.tsx e o gerador de DAGs ainda leem dele.
        _gravar_dependencias(cur, pipeline, depends_on_list, _auth.get("matricula") if isinstance(_auth, dict) else None)
        try:
            cur.execute(
                "UPDATE dbo.etl_pipeline SET descricao=?, criticidade=?, sla_minutos=?, ambiente=?, "
                "max_active_runs=?, retries_count=?, retry_delay_seconds=?, pool_name=?, runbook_md=?, "
                "updated_at=GETDATE() WHERE pipeline_name=?",
                (descricao, criticidade, sla_minutos, ambiente,
                 max_active_runs, retries_count, retry_delay_secs, pool_name, runbook_md, pipeline),
            )
        except Exception:
            # runbook_md pode não existir ainda (migration 013) — grava sem o campo
            cur.execute(
                "UPDATE dbo.etl_pipeline SET descricao=?, criticidade=?, sla_minutos=?, ambiente=?, "
                "max_active_runs=?, retries_count=?, retry_delay_seconds=?, pool_name=?, "
                "updated_at=GETDATE() WHERE pipeline_name=?",
                (descricao, criticidade, sla_minutos, ambiente,
                 max_active_runs, retries_count, retry_delay_secs, pool_name, pipeline),
            )
        try:
            cur.execute(
                "UPDATE dbo.etl_pipeline SET calendario_nome=?, somente_dias_uteis=?, "
                "trigger_por_dependencia=?, updated_at=GETDATE() WHERE pipeline_name=?",
                (calendario_nome, somente_dias_uteis, trigger_por_dependencia, pipeline),
            )
        except Exception:
            pass  # colunas da migration 017 podem não existir ainda — degrada sem erro
        try:
            # Janela e virada (migration 067). Vazio vira NULL: em branco
            # significa "sem regra", e gravar '00:00' criaria uma janela que o
            # usuário não pediu.
            cur.execute(
                "UPDATE dbo.etl_pipeline SET hora_virada=?, nao_iniciar_antes=?, "
                "hora_limite_dependencia=?, updated_at=GETDATE() WHERE pipeline_name=?",
                (hora_virada, nao_iniciar_antes, hora_limite_dependencia, pipeline),
            )
        except Exception:
            pass  # migration 067 pendente — degrada sem erro
        try:
            cur.execute(
                "UPDATE dbo.etl_pipeline SET horarios_especificos=?, dias_semana=?, "
                "updated_at=GETDATE() WHERE pipeline_name=?",
                (horarios_especificos, dias_semana, pipeline),
            )
        except Exception:
            pass  # colunas da migration 018 podem não existir ainda — degrada sem erro
        try:
            cur.execute(
                "UPDATE dbo.etl_pipeline SET dias_horarios_mes=?, "
                "updated_at=GETDATE() WHERE pipeline_name=?",
                (dias_horarios_mes, pipeline),
            )
        except Exception:
            pass  # coluna da migration 024 pode não existir ainda — degrada sem erro
        try:
            # Migration 031 — grava o motivo ao inativar; limpa ao reativar.
            if active == 0:
                cur.execute(
                    "UPDATE dbo.etl_pipeline SET motivo_inativacao=?, inativado_por=?, "
                    "inativado_em=GETDATE(), updated_at=GETDATE() WHERE pipeline_name=?",
                    (motivo_inativacao, changed_by, pipeline),
                )
            else:
                cur.execute(
                    "UPDATE dbo.etl_pipeline SET motivo_inativacao=NULL, inativado_por=NULL, "
                    "inativado_em=NULL, updated_at=GETDATE() WHERE pipeline_name=?",
                    (pipeline,),
                )
        except Exception:
            pass  # colunas da migration 031 podem não existir ainda — degrada sem erro
        new_vals = {
            "active": active, "scheduled_time": horario, "schedule_type": schedule_type,
            "schedule_hour": schedule_hour, "schedule_minute": schedule_minute,
            "schedule_dow": schedule_dow, "schedule_dom": schedule_dom,
            "envia_msg_inicio": envia_msg_inicio, "envia_msg_fim": envia_msg_fim,
            "envia_msg_erro": envia_msg_erro, "project_name": project, "domain": domain,
            "tags": tags, "depends_on": depends_on, "criticidade": criticidade,
            "sla_minutos": sla_minutos, "ambiente": ambiente, "max_active_runs": max_active_runs,
            "retries_count": retries_count, "retry_delay_seconds": retry_delay_secs,
            "pool_name": pool_name, "descricao": descricao, "runbook_md": runbook_md,
        }
        if is_new:
            for field, val in new_vals.items():
                cur.execute(
                    "INSERT INTO dbo.etl_pipeline_audit "
                    "(pipeline_name, changed_by, field_name, old_value, new_value, changed_at) "
                    "VALUES (?, ?, ?, ?, ?, GETDATE())",
                    (pipeline, changed_by, field, None, str(val) if val is not None else ""),
                )
        else:
            _write_audit(cur, pipeline, changed_by, old_record, new_vals)
        conn.commit()
        cur.close(); conn.close()
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro DB: {e}")

    # Espelha o status no Airflow: inativar pausa a DAG, ativar despausa. Só faz
    # sentido se a DAG já existe (pipeline novo ainda não tem DAG). Best-effort.
    dag_sync = None
    if not is_new:
        dag_sync = await _sync_airflow_pause(pipeline, paused=(active == 0))

    # Notifica a mudança de status (inativar/ativar) na central do usuário.
    if not is_new and old_record is not None:
        try:
            old_active = int(old_record.get("active") or 0)
        except (TypeError, ValueError):
            old_active = 0
        if old_active != active:
            dag_paused = (dag_sync or {}).get("is_paused")
            if active == 0:
                msg = (f"Motivo: {motivo_inativacao}. " if motivo_inativacao else "")
                msg += "DAG pausada no Airflow." if dag_paused else ""
                await asyncio.to_thread(add_notificacao, changed_by,
                                        f"Pipeline {pipeline} inativado", msg.strip() or None,
                                        "warning", "/pipelines")
            else:
                msg = "DAG reativada no Airflow." if dag_paused is False else None
                await asyncio.to_thread(add_notificacao, changed_by,
                                        f"Pipeline {pipeline} ativado", msg,
                                        "success", "/pipelines")

    return {"ok": True, "pipeline_name": pipeline, "is_new": is_new,
            "cron": _build_cron(schedule_type, schedule_hour, schedule_minute, schedule_dow, schedule_dom),
            "dag_sync": dag_sync}


def _pipeline_active(pname: str) -> int:
    """Lê o status active do pipeline (404 se não existe)."""
    conn = get_db_conn(); cur = conn.cursor()
    cur.execute("SELECT CAST(active AS INT) FROM dbo.etl_pipeline WHERE pipeline_name=?", (pname,))
    row = cur.fetchone(); cur.close(); conn.close()
    if row is None:
        raise HTTPException(status_code=404, detail="pipeline não encontrado")
    return int(row[0] or 0)


@router.post("/pipelines/{pipeline_name}/gerar-dag", tags=["pipelines"])
async def gerar_dag(pipeline_name: str,
                    _auth: dict = Depends(require_perm(PERM_EXECUTAR))):
    """Gera/regenera a DAG do pipeline e garante o estado final correto.

    Dispara a etl_dag_factory (que escreve o arquivo da DAG no servidor) e
    PERSISTE a intenção de ativação em dbo.etl_dag_pendente. Um reconciliador
    (loop na API) espera a DAG aparecer no Airflow, a coloca no estado certo
    (DAGs nascem pausadas) e notifica quem disparou. Como a intenção fica no
    banco, um restart da API no meio da janela não perde o passo — o loop retoma
    a fila ao subir. Assim o Orquestra só considera a DAG pronta quando ela está
    disponível e no estado certo — sem ficar "ativa no Orquestra e pausada no
    Airflow".
    """
    pname = (pipeline_name or "").strip()
    if not _DAG_ID_RE.match(pname):
        raise HTTPException(status_code=400, detail="pipeline_name inválido")
    desired_paused = (_pipeline_active(pname) == 0)

    run_id = f"orquestra_ui_{int(time.time() * 1000)}"
    try:
        async with httpx.AsyncClient(
            base_url=AIRFLOW_URL, auth=(AIRFLOW_USER, AIRFLOW_PASSWORD), timeout=20
        ) as client:
            r = await client.post(
                f"/api/v1/dags/{FACTORY_DAG_ID}/dagRuns",
                json={"dag_run_id": run_id, "conf": {"pipeline_name": pname, "aguardar_ativacao": True}},
                headers={"Content-Type": "application/json"},
            )
            if not r.is_success:
                raise HTTPException(status_code=502,
                                    detail=f"Falha ao disparar a factory: {r.status_code} {r.text[:200]}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Erro ao disparar a factory: {e}")

    # Persiste a intenção: o reconciliador (loop na API) conclui a ativação e
    # notifica ao final — resiliente a restart da API (a intenção fica no banco).
    await asyncio.to_thread(enqueue_dag_pendente, pname, desired_paused, _auth.get("matricula"), run_id)
    return {"ok": True, "pipeline_name": pname, "dag_run_id": run_id,
            "desired_active": (not desired_paused)}


@router.get("/pipelines/dependencias/estado", tags=["pipelines"])
def estado_dependencias(date_ref: str | None = Query(None),
                        _auth: dict = Depends(get_current_user)):
    """Como está a malha de dependências numa data de referência.

    Responde a pergunta que hoje só existe no banco: por que aquele pipeline
    ainda não rodou. Devolve, por dependente, o status da corrida e QUAIS
    predecessores estão pendentes — "aguardando dependência" sem dizer de quem
    manda o operador abrir o SQL.

    Degrada para lista vazia sem a migration 067: a tela some, o resto do
    Malha continua.
    """
    dr = (date_ref or "").strip() or date.today().isoformat()
    try:
        dia = datetime.strptime(dr[:10], "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail=f"date_ref inválido: '{dr}' — use AAAA-MM-DD")

    try:
        conn = get_db_conn(); cur = conn.cursor()
    except Exception as e:
        log.warning("[DEP] estado sem banco: %s", e)
        return {"date_ref": dia.isoformat(), "data": []}

    try:
        cur.execute(
            "SELECT d.pipeline_name, d.depende_de, "
            "       (SELECT TOP 1 e.status FROM dbo.etl_pipeline_execucao e "
            "         WHERE e.pipeline_name = d.depende_de AND e.data_referencia = ? "
            "         ORDER BY COALESCE(e.inicio, e.criado_em) DESC, e.id DESC), "
            "       (SELECT TOP 1 x.status FROM dbo.etl_pipeline_execucao x "
            "         WHERE x.pipeline_name = d.pipeline_name AND x.data_referencia = ? "
            "         ORDER BY COALESCE(x.inicio, x.criado_em) DESC, x.id DESC) "
            "FROM dbo.etl_pipeline_dependencia d "
            "JOIN dbo.etl_pipeline p ON p.pipeline_name = d.pipeline_name "
            "WHERE d.tipo = 'PIPELINE' AND p.active = 1 "
            "ORDER BY d.pipeline_name, d.depende_de", (dia, dia))
        linhas = cur.fetchall()

        cur.execute(
            "SELECT pipeline_name, tipo, detalhe FROM dbo.etl_dependencia_evento "
            "WHERE data_referencia = ?", (dia,))
        eventos = {}
        for r in cur.fetchall():
            eventos.setdefault(str(r[0]), []).append({"tipo": r[1], "detalhe": r[2]})
    except Exception as e:
        log.warning("[DEP] estado indisponível (migration 067 aplicada?): %s", e)
        return {"date_ref": dia.isoformat(), "data": []}
    finally:
        try:
            cur.close(); conn.close()
        except Exception:
            pass

    por_pipeline: dict = {}
    for nome, predecessor, status_pred, status_proprio in linhas:
        item = por_pipeline.setdefault(str(nome), {
            "pipeline_name": str(nome), "status": status_proprio,
            "predecessores": [], "pendentes": [],
        })
        item["predecessores"].append({"nome": str(predecessor), "status": status_pred})
        if status_pred != "SUCESSO":
            item["pendentes"].append(str(predecessor))

    dados = []
    for item in por_pipeline.values():
        item["eventos"] = eventos.get(item["pipeline_name"], [])
        # Liberado = nenhum pendente. Espelha utils/dependencias.avaliar_liberacao,
        # mas aqui é só leitura: a decisão de disparar continua sendo da DAG.
        item["liberado"] = not item["pendentes"]
        dados.append(item)

    return {"date_ref": dia.isoformat(), "data": dados}


@router.post("/pipelines/{pipeline_name}/dag-sync", tags=["pipelines"])
async def pipeline_dag_sync(pipeline_name: str, _auth: dict = Depends(require_perm(PERM_EXECUTAR))):
    """Reconcilia o is_paused da DAG ao status do pipeline e reporta se já está
    pronta. Idempotente — usado pela UI como polling após gerar a DAG, e seguro
    de chamar repetidamente. ready=True quando a DAG existe e está no estado certo.
    """
    pname = (pipeline_name or "").strip()
    if not _DAG_ID_RE.match(pname):
        raise HTTPException(status_code=400, detail="pipeline_name inválido")
    desired_paused = (_pipeline_active(pname) == 0)
    sync = await _sync_airflow_pause(pname, paused=desired_paused)
    ready = (bool(sync.get("exists")) and sync.get("error") is None
             and sync.get("is_paused") == desired_paused)
    return {**sync, "ready": ready, "active_orquestra": (not desired_paused)}


@router.get("/malha", tags=["pipelines"])
def get_malha():
    """Retorna todos os pipelines com seus jobs embutidos para a visualização de malha."""
    try:
        conn = get_db_conn()
        cur  = conn.cursor()

        cur.execute("""
            SELECT pipeline_name, project_name, domain, tags,
                   CONVERT(VARCHAR(8), scheduled_time, 108) AS scheduled_time,
                   schedule_type,
                   CAST(active AS INT) AS active,
                   depends_on,
                   descricao,
                   ISNULL(criticidade, 'Media') AS criticidade,
                   sla_minutos,
                   ISNULL(ambiente, 'PROD') AS ambiente,
                   last_execution
            FROM dbo.etl_pipeline
            ORDER BY project_name, domain, pipeline_name
        """)
        pipe_cols = ["pipeline_name", "project_name", "domain", "tags",
                     "scheduled_time", "schedule_type", "active", "depends_on",
                     "descricao", "criticidade", "sla_minutos", "ambiente",
                     "last_execution"]
        pipelines: dict[str, dict] = {}
        for row in cur.fetchall():
            rec = dict(zip(pipe_cols, row))
            rec["last_execution"] = _fmt_dt(rec.get("last_execution"))
            rec["jobs"] = []
            pipelines[rec["pipeline_name"]] = rec

        cur.execute("""
            SELECT pipeline_name, job_name,
                   CAST(execution_order AS INT) AS execution_order,
                   job_type, job_command
            FROM dbo.etl_pipeline_job
            ORDER BY pipeline_name, execution_order, job_name
        """)
        for pname, jname, order, jtype, cmd in cur.fetchall():
            if pname in pipelines:
                pipelines[pname]["jobs"].append({
                    "job_name":        jname or "",
                    "execution_order": int(order or 0),
                    "job_type":        jtype or "",
                    "command":         cmd  or "",
                })

        cur.close(); conn.close()
        return {"data": list(pipelines.values())}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
