"""api/routers/pipelines.py — GET /pipelines, POST /pipelines/register, GET /malha."""
from __future__ import annotations

import json
import logging
import re
from datetime import timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException

from db import get_db_conn
from deps import (
    PERM_EDITAR,
    get_current_user, require_perm,
)

log = logging.getLogger("orquestra-api")

router = APIRouter()

LOCAL_TZ = timezone(timedelta(hours=-3))  # America/Sao_Paulo


def _fmt_dt(v):
    if v is None:
        return None
    if hasattr(v, "strftime"):
        return v.strftime("%Y-%m-%d %H:%M:%S")
    return str(v)


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


def _check_circular(cur, pipeline_name, depends_on_list):
    for dep in depends_on_list:
        if not dep:
            continue
        visited, current, hops = set(), dep, 0
        while current and hops < 50:
            if current == pipeline_name:
                raise ValueError(f"Dependência circular: '{pipeline_name}' → '{dep}'")
            if current in visited:
                break
            visited.add(current)
            cur.execute("SELECT depends_on FROM dbo.etl_pipeline WHERE pipeline_name = ?", (current,))
            row = cur.fetchone()
            raw = (str(row[0]).strip() if row and row[0] else None)
            current = raw.split(",")[0].strip() if raw else None
            hops += 1


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
                pool_name, {runbook_col}, {sched_cols}, last_execution, created_at, updated_at
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
            "dias_horarios_mes", "last_execution", "created_at", "updated_at",
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
    # Fase 4 — scheduling avançado
    calendario_nome  = (body.get("calendario_nome") or "").strip() or None
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

    try:
        conn = get_db_conn(); cur = conn.cursor()
        valid_projects = _get_valid_projects(cur)
        if project not in valid_projects:
            raise HTTPException(status_code=422, detail=f"project_name inválido: '{project}'")
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
    return {"ok": True, "pipeline_name": pipeline, "is_new": is_new,
            "cron": _build_cron(schedule_type, schedule_hour, schedule_minute, schedule_dow, schedule_dom)}


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
