"""api/routers/execucoes.py — GET /execucoes, POST /execucoes/rerun, POST /execucoes/ack, GET /execucoes/duracao-media."""
from __future__ import annotations

import asyncio
import logging
import os
from collections import Counter
from datetime import datetime, timedelta
from typing import Optional

import httpx
from fastapi import APIRouter, Body, Depends, HTTPException, Query

from db import get_db_conn
from deps import (
    AIRFLOW_URL, AIRFLOW_USER, AIRFLOW_PASSWORD,
    PERM_EXECUTAR,
    get_current_user, require_perm,
)
from services.notify import add_notificacao
# Validação de dag_id do proxy (uma autoridade só, como malhas.py já faz).
from routers.airflow import _DAG_ID_RE
# Ponte de identidade run_id ↔ ts_nodash (F2 — docs/spec-operacao-nivel-etapa.md).
from services import data_referencia as dref
from services import dependencias as deps_svc
from services import execucao_identidade as ident_svc

log = logging.getLogger("orquestra-api")

router = APIRouter()

MAX_LIMIT = 200


def _fmt_dt(v):
    if v is None:
        return None
    if hasattr(v, "strftime"):
        return v.strftime("%Y-%m-%d %H:%M:%S")
    return str(v)


# A ponte de identidade run_id ↔ ts_nodash vive numa peça SÓ desde a F2 da spec
# de operação no nível de etapa (services/execucao_identidade.py). Os dois nomes
# abaixo continuam existindo como ALIAS porque são caminho de produção (rerun e
# reconciliação) e têm teste próprio (tests/test_execucoes_rerun.py) — delegar
# em vez de reescrever mantém o comportamento byte a byte e deixa uma
# autoridade só para a regra.
_iso_to_ts_nodash = ident_svc.ts_nodash
_escolhe_dag_run = ident_svc.escolhe_dag_run


def get_airflow_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=AIRFLOW_URL,
        auth=(AIRFLOW_USER, AIRFLOW_PASSWORD),
        timeout=15,
    )


def _get_app_config_value(key: str) -> str | None:
    """Lê um parâmetro único de dbo.etl_app_config. Retorna None se ausente/erro."""
    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute("SELECT config_value FROM dbo.etl_app_config WHERE config_key=?", (key,))
        row = cur.fetchone()
        cur.close(); conn.close()
        val = (row[0] or "").strip() if row else ""
        return val or None
    except Exception as e:
        log.warning("etl_app_config leitura de '%s' falhou: %s", key, e)
        return None


def _alvo_blocks(itens: list[str]) -> list[dict]:
    """Monta um Container de TextBlocks, um por alvo distinto (pipeline/job),
    com contagem (×N) quando o mesmo alvo aparece mais de uma vez. Cada item
    em seu próprio TextBlock garante quebra de linha correta no Teams."""
    counts = Counter(lbl for lbl in itens if lbl)
    return [{
        "type": "Container", "spacing": "Small",
        "items": [
            {"type": "TextBlock", "wrap": True, "spacing": "None",
             "text": f"• {lbl}" + (f"  (×{n})" if n > 1 else "")}
            for lbl, n in counts.items()
        ],
    }]


def _detalhes_section(detail_facts: list[dict], key: str) -> list[dict]:
    """Expansor 'Ver mais detalhes' / 'Ver menos' (Action.ToggleVisibility).

    Recebe os fatos secundários (matrícula, execution id, nota, ticket…) e
    devolve os elementos de body que escondem esses fatos num Container e
    alternam sua visibilidade por dois ActionSets que trocam de rótulo. Mantém
    o card enxuto no glance, revelando o detalhe sob demanda — sem backend.

    Retorna [] quando não há nada a esconder (não polui o card com botão vazio).
    O `key` torna os ids únicos dentro do card (ex.: 'ack' / 'resolve').
    """
    detail_facts = [f for f in detail_facts if f.get("value")]
    if not detail_facts:
        return []
    det_id, more_id, less_id = f"det_{key}", f"more_{key}", f"less_{key}"
    targets = [det_id, more_id, less_id]
    return [
        {"type": "Container", "id": det_id, "isVisible": False, "spacing": "Small",
         "items": [{"type": "FactSet", "facts": detail_facts}]},
        {"type": "ActionSet", "id": more_id, "spacing": "Small",
         "actions": [{"type": "Action.ToggleVisibility",
                      "title": "Ver mais detalhes", "targetElements": targets}]},
        {"type": "ActionSet", "id": less_id, "isVisible": False, "spacing": "Small",
         "actions": [{"type": "Action.ToggleVisibility",
                      "title": "Ver menos", "targetElements": targets}]},
    ]


def _teams_ack_card(pipeline: str, exec_id: str, ack_by: str, display_name: str,
                    ack_at: str, note: str | None, webhook_var: str,
                    itens: list[str] | None = None) -> None:
    """Posta card no Teams informando que alguém assumiu a falha.

    `pipeline` é o rótulo exibido (nome do pipeline ou, para falhas de malha,
    o nome do job). Quando `itens` é fornecido (assunção em massa), o card
    lista cada alvo assumido — com contagem quando repetido — em vez de exibir
    um único pipeline/exec_id.

    Ordem de resolução do webhook:
      1. dbo.etl_app_config chave 'teams_webhook_url_ack' (canal dedicado a acks)
      2. dbo.etl_app_config chave 'teams_webhook_url'     (canal padrão/geral)
      3. variável de ambiente TEAMS_WEBHOOK_URL_CVP
    """
    webhook_url = _get_app_config_value("teams_webhook_url_ack") \
        or _get_app_config_value("teams_webhook_url") \
        or os.getenv("TEAMS_WEBHOOK_URL_CVP", "")
    if not webhook_url:
        log.warning("[ACK] webhook do Teams não configurado — cadastre o parâmetro "
                    "'teams_webhook_url_ack' em Admin > Configurações. Notificação ignorada.")
        return

    identity = f"{display_name} ({ack_by})" if display_name and display_name != ack_by else ack_by

    body_elements = [
        {"type": "TextBlock", "text": "👁 Falha assumida para análise",
         "size": "Large", "weight": "Bolder", "wrap": True, "color": "Accent"},
    ]

    # Fatos primários (visíveis no glance) e secundários (atrás de "Ver mais detalhes").
    detail_facts: list[dict] = [{"title": "Matrícula", "value": ack_by}]
    if itens:
        total = len([i for i in itens if i])
        body_elements.append(
            {"type": "TextBlock",
             "text": f"{identity} assumiu {total} falha(s) para análise:",
             "wrap": True, "spacing": "None", "isSubtle": True})
        body_elements.extend(_alvo_blocks(itens))
        facts = [
            {"title": "Responsável", "value": identity},
            {"title": "Assumido em", "value": ack_at or "agora"},
        ]
    else:
        body_elements.append(
            {"type": "TextBlock",
             "text": f"{identity} está investigando a falha em {pipeline}.",
             "wrap": True, "spacing": "None", "isSubtle": True})
        facts = [
            {"title": "Pipeline / Job", "value": pipeline},
            {"title": "Responsável",    "value": identity},
            {"title": "Assumido em",    "value": ack_at or "agora"},
        ]
        if exec_id and exec_id != "—":
            detail_facts.append({"title": "Execution ID", "value": exec_id})

    if note:
        detail_facts.append({"title": "Observação", "value": note})

    body_elements.append({"type": "FactSet", "spacing": "Medium", "facts": facts})
    body_elements.extend(_detalhes_section(detail_facts, "ack"))

    payload = {
        "type": "message",
        "attachments": [{
            "contentType": "application/vnd.microsoft.card.adaptive",
            "content": {
                "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                "type": "AdaptiveCard", "version": "1.4",
                "body": body_elements,
            },
        }],
    }
    try:
        resp = httpx.post(webhook_url, json=payload, timeout=10)
        log.info("[ACK] Teams status=%s body=%.120s", resp.status_code, resp.text)
    except Exception as e:
        log.warning("[ACK] Falha ao enviar Teams: %s", e)


def _teams_resolved_card(pipeline: str, exec_id: str, resolved_by: str, display_name: str,
                          resolved_at: str, resolution_note: str | None, snow_ticket: str | None,
                          webhook_var: str, itens: list[str] | None = None) -> None:
    """Posta card no Teams informando que a falha foi resolvida.

    `pipeline` é o rótulo exibido (nome do pipeline ou, para falhas de malha,
    o nome do job). Quando `itens` é fornecido (resolução em massa), o card
    lista cada alvo resolvido — com contagem quando repetido — em vez de exibir
    um único pipeline/exec_id.

    Ordem de resolução do webhook:
      1. dbo.etl_app_config chave 'teams_webhook_url_resolved' (canal dedicado a resoluções)
      2. dbo.etl_app_config chave 'teams_webhook_url'          (canal padrão/geral)
      3. variável de ambiente TEAMS_WEBHOOK_URL_CVP
    """
    webhook_url = _get_app_config_value("teams_webhook_url_resolved") \
        or _get_app_config_value("teams_webhook_url") \
        or os.getenv(webhook_var, "")
    if not webhook_url:
        log.warning("[RESOLVE] webhook do Teams não configurado — cadastre o parâmetro "
                    "'teams_webhook_url_resolved' em Admin > Configurações. Notificação ignorada.")
        return

    identity = f"{display_name} ({resolved_by})" if display_name and display_name != resolved_by else resolved_by

    body_elements = [
        {"type": "TextBlock", "text": "✅ Falha resolvida",
         "size": "Large", "weight": "Bolder", "wrap": True, "color": "Good"},
    ]

    # Fatos primários (visíveis no glance) e secundários (atrás de "Ver mais detalhes").
    detail_facts: list[dict] = [{"title": "Matrícula", "value": resolved_by}]
    if itens:
        total = len([i for i in itens if i])
        body_elements.append(
            {"type": "TextBlock",
             "text": f"{identity} marcou {total} falha(s) como resolvida(s):",
             "wrap": True, "spacing": "None", "isSubtle": True})
        body_elements.extend(_alvo_blocks(itens))
        facts = [
            {"title": "Resolvido por", "value": identity},
            {"title": "Resolvido em",  "value": resolved_at or "agora"},
        ]
    else:
        body_elements.append(
            {"type": "TextBlock",
             "text": f"{identity} marcou a falha em {pipeline} como resolvida.",
             "wrap": True, "spacing": "None", "isSubtle": True})
        facts = [
            {"title": "Pipeline / Job", "value": pipeline},
            {"title": "Resolvido por",  "value": identity},
            {"title": "Resolvido em",   "value": resolved_at or "agora"},
        ]
        if exec_id and exec_id != "—":
            detail_facts.append({"title": "Execution ID", "value": exec_id})

    if resolution_note:
        detail_facts.append({"title": "Nota de resolução", "value": resolution_note})
    if snow_ticket:
        detail_facts.append({"title": "Ticket ServiceNow", "value": snow_ticket})

    body_elements.append({"type": "FactSet", "spacing": "Medium", "facts": facts})
    body_elements.extend(_detalhes_section(detail_facts, "resolve"))

    payload = {
        "type": "message",
        "attachments": [{
            "contentType": "application/vnd.microsoft.card.adaptive",
            "content": {
                "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                "type": "AdaptiveCard", "version": "1.4",
                "body": body_elements,
            },
        }],
    }
    try:
        resp = httpx.post(webhook_url, json=payload, timeout=10)
        log.info("[RESOLVE] Teams status=%s body=%.120s", resp.status_code, resp.text)
    except Exception as e:
        log.warning("[RESOLVE] Falha ao enviar Teams: %s", e)


def _merge_fila_por_execucao(cur, conn, data: list[dict]) -> None:
    """Soma queued_seconds de etl_ds_job_log por (execution_id, pipeline) e injeta
    em data[i]['fila_total_segundos']. Degrada silenciosamente se a tabela/coluna
    não existir.

    Agrupa também por pipeline_name (além de execution_id) porque o
    execution_id (derivado de ts_nodash) pode colidir entre pipelines
    diferentes disparados no mesmo timestamp.
    """
    exec_ids = list({d["execution_id"] for d in data if d.get("execution_id")})
    if not exec_ids:
        return
    placeholders = ",".join("?" * len(exec_ids))
    try:
        cur.execute(f"""
            SELECT execution_id, pipeline_name, SUM(CAST(queued_seconds AS bigint))
            FROM dbo.etl_ds_job_log
            WHERE queued_seconds IS NOT NULL AND queued_seconds > 0
              AND execution_id IN ({placeholders})
            GROUP BY execution_id, pipeline_name
        """, exec_ids)
        fila = {(row[0], row[1]): int(row[2] or 0) for row in cur.fetchall()}
        for d in data:
            d["fila_total_segundos"] = fila.get((d["execution_id"], d.get("pipeline")), 0)
    except Exception:
        try: conn.rollback()
        except Exception: pass


def _merge_fila_por_job(cur, conn, data: list[dict]) -> None:
    """Soma queued_seconds por (execution_id, pipeline, job_name) e injeta em
    data[i]['fila_segundos']. Degrada silenciosamente.

    Inclui pipeline_name no agrupamento pelo mesmo motivo descrito em
    _merge_fila_por_execucao: execution_id isoladamente pode colidir entre
    pipelines distintos.
    """
    exec_ids = list({d["execution_id"] for d in data if d.get("execution_id")})
    if not exec_ids:
        return
    placeholders = ",".join("?" * len(exec_ids))
    try:
        cur.execute(f"""
            SELECT execution_id, pipeline_name, job_name, SUM(CAST(queued_seconds AS bigint))
            FROM dbo.etl_ds_job_log
            WHERE queued_seconds IS NOT NULL AND queued_seconds > 0
              AND execution_id IN ({placeholders})
            GROUP BY execution_id, pipeline_name, job_name
        """, exec_ids)
        fila = {(row[0], row[1], row[2]): int(row[3] or 0) for row in cur.fetchall()}
        for d in data:
            d["fila_segundos"] = fila.get((d["execution_id"], d.get("pipeline"), d["job_name"]), 0)
    except Exception:
        try: conn.rollback()
        except Exception: pass


@router.get("/execucoes", tags=["execucoes"])
def list_execucoes(
    offset: int = 0,
    limit: int = 50,
    filter_project: Optional[str] = None,
    filter_pipeline: Optional[str] = None,
    filter_execution_id: Optional[str] = None,
    filter_status: Optional[str] = None,
    filter_hours_back: Optional[int] = None,
    filter_date_from: Optional[str] = None,
    filter_date_to: Optional[str] = None,
    detail_mode: bool = False,
):
    """Consulta paginada de execuções. Substitui etl_job_execution_query."""
    limit  = min(MAX_LIMIT, max(1, limit))
    offset = max(0, offset)
    fp  = (filter_project  or "").strip()
    fpl = (filter_pipeline or "").strip()
    fei = (filter_execution_id or "").strip()
    fst = (filter_status   or "").strip().upper()
    fdf = (filter_date_from or "").strip()
    fdt = (filter_date_to   or "").strip()
    fhb = filter_hours_back if (filter_hours_back and filter_hours_back > 0) else None

    where_parts: list[str] = []
    params: list = []

    if fp:
        where_parts.append("project = ?")
        params.append(fp)
    if fpl:
        where_parts.append("pipeline LIKE ?")
        params.append(f"%{fpl}%")
    if fei:
        where_parts.append("execution_id = ?")
        params.append(fei)
    if fhb:
        where_parts.append(f"start_time >= DATEADD(hour, -{fhb}, GETDATE())")
    elif fdf:
        where_parts.append("start_time >= ?")
        params.append(fdf + " 00:00:00")
    if fdt:
        try:
            dt_to = (datetime.strptime(fdt, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
            where_parts.append("start_time < ?")
            params.append(dt_to + " 00:00:00")
        except Exception:
            where_parts.append("start_time < ?")
            params.append(fdt + " 23:59:59")

    where_sql = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""

    status_expr = """
        CASE
            WHEN SUM(CASE WHEN status='FAILED'  THEN 1 ELSE 0 END) > 0 THEN 'FAILED'
            WHEN SUM(CASE WHEN status='WARNING' THEN 1 ELSE 0 END) > 0 THEN 'WARNING'
            WHEN SUM(CASE WHEN status='RUNNING' THEN 1 ELSE 0 END) > 0 THEN 'RUNNING'
            WHEN SUM(CASE WHEN status='SUCCESS' THEN 1 ELSE 0 END) > 0 THEN 'SUCCESS'
            WHEN SUM(CASE WHEN status='SKIPPED' THEN 1 ELSE 0 END) > 0 THEN 'SKIPPED'
            ELSE 'DESCONHECIDO'
        END
    """

    try:
        conn = get_db_conn()
        cur  = conn.cursor()

        if detail_mode:
            if fst:
                where_parts.append("status = ?")
                params.append(fst)
                where_sql = "WHERE " + " AND ".join(where_parts)

            cur.execute(f"SELECT COUNT(*) FROM dbo.etl_job_execution {where_sql}", params)
            total = cur.fetchone()[0]

            cur.execute(f"""
                SELECT execution_id, project, pipeline, job_name, status,
                       start_time, end_time, duration_seconds, status_code, log_file, task_id
                FROM dbo.etl_job_execution
                {where_sql}
                ORDER BY start_time DESC
                OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
            """, params + [offset, limit])
            data = [
                {
                    "execution_id": r[0], "project": r[1], "pipeline": r[2],
                    "job_name": r[3], "status": r[4],
                    "inicio": _fmt_dt(r[5]), "fim": _fmt_dt(r[6]),
                    "duration_seconds": int(r[7] or 0) if r[7] is not None else None,
                    "status_code": r[8], "log_file": r[9], "task_id": r[10],
                    "fila_segundos": None,
                }
                for r in cur.fetchall()
            ]
            # Tempo de fila por job (etl_ds_job_log) — graceful se tabela não existir
            if data:
                _merge_fila_por_job(cur, conn, data)
            cur.close(); conn.close()
            pages = 0 if total == 0 else -(-total // limit)
            return {
                "mode": "detail", "total": int(total), "offset": offset,
                "limit": limit, "pages": pages,
                "filters": {"project": fp, "pipeline": fpl, "execution_id": fei,
                            "status": fst, "date_from": fdf, "date_to": fdt},
                "data": data,
            }

        # Aggregated mode
        having_sql    = ""
        having_params: list = []
        if fst:
            having_sql = f"HAVING {status_expr} = ?"
            having_params.append(fst)

        cur.execute(f"""
            SELECT COUNT(*) FROM (
                SELECT execution_id, project, pipeline
                FROM dbo.etl_job_execution
                {where_sql}
                GROUP BY execution_id, project, pipeline
                {having_sql}
            ) t
        """, params + having_params)
        total = cur.fetchone()[0]

        agg_cte = f"""
            WITH agg AS (
                SELECT
                    execution_id, project, pipeline,
                    MIN(start_time)                    AS inicio,
                    MAX(end_time)                      AS fim,
                    COALESCE(SUM(duration_seconds), 0) AS duracao_total_segundos,
                    -- Relógio de parede: com jobs em PARALELO a soma acima excede o
                    -- tempo real da execução; RUNNING usa GETDATE() como fim.
                    DATEDIFF(SECOND, MIN(start_time),
                             MAX(COALESCE(end_time, GETDATE()))) AS duracao_wall_segundos,
                    COUNT(*)                           AS total_jobs,
                    SUM(CASE WHEN status='SUCCESS' THEN 1 ELSE 0 END) AS jobs_ok,
                    SUM(CASE WHEN status='FAILED'  THEN 1 ELSE 0 END) AS jobs_falha,
                    SUM(CASE WHEN status='WARNING' THEN 1 ELSE 0 END) AS jobs_warning,
                    SUM(CASE WHEN status='RUNNING' THEN 1 ELSE 0 END) AS jobs_running,
                    SUM(CASE WHEN status='SKIPPED' THEN 1 ELSE 0 END) AS jobs_skipped,
                    {status_expr} AS status_geral
                FROM dbo.etl_job_execution
                {where_sql}
                GROUP BY execution_id, project, pipeline
                {having_sql}
            )
        """
        # etl_failure_ack pode não existir ainda (migration 013) — degrada sem ack
        has_ack = True
        has_resolved = False
        try:
            cur.execute(agg_cte + """
                SELECT a.*, ack.ack_by, ack.display_name, ack.ack_at,
                       ack.resolved_by, ack.resolved_display_name, ack.resolved_at,
                       ack.resolution_note, ack.snow_ticket
                FROM agg a
                LEFT JOIN dbo.etl_failure_ack ack
                       ON ack.execution_id = a.execution_id AND ack.pipeline = a.pipeline
                ORDER BY a.inicio DESC
                OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
            """, params + having_params + [offset, limit])
            has_resolved = True
        except Exception:
            try: conn.rollback()
            except Exception: pass
            try:
                cur.execute(agg_cte + """
                    SELECT a.*, ack.ack_by, ack.display_name, ack.ack_at
                    FROM agg a
                    LEFT JOIN dbo.etl_failure_ack ack
                           ON ack.execution_id = a.execution_id AND ack.pipeline = a.pipeline
                    ORDER BY a.inicio DESC
                    OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
                """, params + having_params + [offset, limit])
            except Exception:
                has_ack = False
                try: conn.rollback()
                except Exception: pass
                cur.execute(agg_cte + """
                    SELECT a.* FROM agg a
                    ORDER BY a.inicio DESC
                    OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
                """, params + having_params + [offset, limit])
        data = [
            {
                "execution_id": r[0], "project": r[1], "pipeline": r[2],
                "inicio": _fmt_dt(r[3]), "fim": _fmt_dt(r[4]),
                "duracao_total_segundos": int(r[5] or 0),
                "duracao_wall_segundos": int(r[6] or 0),
                "total_jobs": int(r[7] or 0), "jobs_ok": int(r[8] or 0),
                "jobs_falha": int(r[9] or 0), "jobs_warning": int(r[10] or 0),
                "jobs_running": int(r[11] or 0), "jobs_skipped": int(r[12] or 0),
                "status_geral": r[13],
                "ack_by": r[14] if has_ack else None,
                "display_name": r[15] if has_ack else None,
                "ack_at": _fmt_dt(r[16]) if has_ack else None,
                "resolved_by": r[17] if has_resolved else None,
                "resolved_display_name": r[18] if has_resolved else None,
                "resolved_at": _fmt_dt(r[19]) if has_resolved else None,
                "resolution_note": r[20] if has_resolved else None,
                "snow_ticket": r[21] if has_resolved else None,
                "fila_total_segundos": None,
            }
            for r in cur.fetchall()
        ]
        # Tempo total de fila por execução (etl_ds_job_log) — graceful
        if data:
            _merge_fila_por_execucao(cur, conn, data)
        cur.close(); conn.close()
        pages = 0 if total == 0 else -(-total // limit)
        return {
            "total": int(total), "offset": offset, "limit": limit, "pages": pages,
            "filters": {"project": fp, "pipeline": fpl, "status": fst,
                        "hours_back": fhb, "date_from": fdf, "date_to": fdt},
            "data": data,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/execucoes/rerun", tags=["execucoes"])
async def rerun_from_task(body: dict = Body(default={}), _auth: dict = Depends(require_perm(PERM_EXECUTAR))):
    """Limpa tasks a partir de um job específico e reexecuta o DAG.

    Body:
      pipeline_name  — nome do pipeline (= dag_id no Airflow)
      execution_id   — execution_id da execução original (usado para localizar o dag_run_id)
      task_id        — task_id a partir da qual reexecutar (inclusive, com downstream)
      dag_run_id     — dag_run_id real (opcional; se não informado, tenta resolver via API)
    """
    pipeline   = (body.get("pipeline_name") or "").strip()
    exec_id    = (body.get("execution_id")  or "").strip()
    task_id    = (body.get("task_id")       or "").strip()
    dag_run_id = (body.get("dag_run_id")    or "").strip()

    if not pipeline or not task_id:
        raise HTTPException(status_code=422, detail="pipeline_name e task_id são obrigatórios")

    dag_id = pipeline  # no Airflow o dag_id = pipeline_name exato

    async with get_airflow_client() as client:
        # 1. Resolver dag_run_id se não fornecido
        if not dag_run_id:
            r = await client.get(f"/api/v1/dags/{dag_id}/dagRuns",
                                 params={"limit": 50, "order_by": "-execution_date"})
            if not r.is_success:
                raise HTTPException(status_code=502, detail=f"Airflow: {r.status_code}")
            runs = r.json().get("dag_runs", [])
            if not runs:
                raise HTTPException(status_code=404, detail="Nenhum dag_run encontrado para este pipeline")
            # Casa o run cuja logical date (ts_nodash) == execution_id da execução
            # clicada — sem isso, com runs paralelos/antigos o clear limpava o run
            # ERRADO (pegava o 1º terminado da lista). Sem match, mantém o
            # comportamento antigo como fallback.
            dag_run_id = _escolhe_dag_run(runs, exec_id)["dag_run_id"]

        # 2. Limpar a task e downstream via clearTaskInstances — SEMPRE com o
        # dag_run_id: sem ele o Airflow limpa a task em TODOS os dag_runs da DAG
        # (e reset_dag_runs re-enfileira todos) — reprocessamento em massa.
        clear_body = {
            "dry_run": False,
            "dag_run_id": dag_run_id,
            "task_ids": [task_id],
            "include_downstream": True,
            "include_future": False,
            "include_past": False,
            "include_upstream": False,
            "reset_dag_runs": True,
        }
        r2 = await client.post(
            f"/api/v1/dags/{dag_id}/clearTaskInstances",
            json=clear_body,
        )
        if not r2.is_success:
            raise HTTPException(status_code=502,
                detail=f"Airflow clearTaskInstances falhou: {r2.status_code} — {r2.text[:300]}")

        cleared = r2.json()
        log.info("Rerun %s/%s a partir de %s — %s tasks limpas",
                 dag_id, dag_run_id, task_id, len(cleared.get("task_instances", [])))

        return {
            "ok": True,
            "pipeline_name": pipeline,
            "dag_id": dag_id,
            "dag_run_id": dag_run_id,
            "task_id": task_id,
            "tasks_cleared": len(cleared.get("task_instances", [])),
        }


def _ident_json(ident: dict) -> dict:
    """Identidade pronta para JSON — datas viram texto no formato do resto da
    API (`_fmt_dt` / `YYYY-MM-DD`). Nenhuma chave é omitida: o consumidor lê
    sempre o mesmo molde, resolvido ou não."""
    out = dict(ident)
    dref_val = out.get("data_referencia")
    out["data_referencia"] = (dref_val.strftime("%Y-%m-%d")
                              if hasattr(dref_val, "strftime") else dref_val)
    out["candidatos"] = [
        {**c, "inicio": _fmt_dt(c.get("inicio")), "fim": _fmt_dt(c.get("fim"))}
        for c in (out.get("candidatos") or [])
    ]
    return out


@router.get("/pipelines/{pipeline_name}/execucao", tags=["execucoes"])
async def get_pipeline_execucao(
    pipeline_name: str,
    data_referencia: str | None = None,
    execution_id: str | None = None,
    _auth: dict = Depends(get_current_user),
):
    """Execução de UM pipeline no nível de ETAPA — a chamada do drill-down (F2).

    **Fala a linguagem da malha**: `(pipeline, ODATE)`, o mesmo par de
    `GET /malhas/{m}/execucao`. Uma chamada só devolve tudo que a F3 precisa
    para abrir o canvas de Etapas em modo Execução: a identidade resolvida
    (`ts_nodash` + `run_id`/`dag_run_id`, este último para a F4 reexecutar), a
    corrida do pipeline e as etapas com status, início, fim e duração.

    Parâmetros (mutuamente exclusivos):
      • `data_referencia=YYYY-MM-DD` — o ODATE. Ausente, usa o ODATE corrente
        calculado com a virada GLOBAL de `etl_app_config` (mesma semântica do
        painel da malha).
      • `execution_id=<ts_nodash>` — o **sentido inverso**, para quem já tem o
        execution_id da telemetria (Dashboard / modal de Logs) e não o ODATE.

    **Vazio ≠ erro.** Pipeline sem execução no ODATE responde 200 com
    `vazio: true`, `razao` preenchida e `etapas` trazendo o DESENHO com
    `status: null` e `sem_execucao: true` — o canvas desenha o grafo neutro em
    vez de quebrar (regra de honestidade do §3: etapa sem linha de execução é
    neutra, nunca verde). Só pipeline INEXISTENTE é 404.

    **Degradação.** Sem a migration 067 a resposta vem por aproximação sobre
    `etl_job_execution` (`identidade.degradado: true`); com o Airflow fora do ar
    a identidade pode ficar sem `run_id`/`ts_nodash` e a resposta traz
    `airflow_indisponivel: true` — em nenhum dos casos a tela fica sem resposta.

    O payload COMPLETO do canvas (layout, condition, params) continua vindo de
    `GET /pipelines/{p}/fluxo`; aqui vai só o mínimo do desenho (`job_type`,
    `execution_order`, `depends_on_jobs`) que dá sentido às etapas — não se
    duplica o editor.
    """
    if data_referencia and execution_id:
        raise HTTPException(
            status_code=422,
            detail="Informe data_referencia OU execution_id, nunca os dois")
    # Valida a data ANTES de abrir conexão (mesma regra do GET /malhas/…/execucao).
    data_ref = None
    if data_referencia is not None and str(data_referencia).strip() != "":
        try:
            data_ref = datetime.strptime(
                str(data_referencia).strip(), "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail=f"data_referencia inválida: '{data_referencia}' "
                       "(use o formato YYYY-MM-DD)")
    ts_pedido = (execution_id or "").strip()

    # ── Fase 1: tudo que o banco sabe (conexão aberta e FECHADA antes do await
    # do Airflow — nenhuma conexão fica presa durante I/O de rede).
    try:
        conn = get_db_conn(); cur = conn.cursor()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro DB: {e}")
    try:
        oficial = ident_svc.pipeline_oficial(cur, pipeline_name)
        if oficial is None:
            raise HTTPException(
                status_code=404,
                detail=f"Pipeline não encontrado: '{pipeline_name}'")
        tem_067 = ident_svc.tem_tabela_067(cur)
        virada = deps_svc.virada_global(cur)
        if ts_pedido:
            ident = ident_svc.resolve_por_ts_nodash(cur, oficial, ts_pedido)
        else:
            if data_ref is None:
                data_ref = dref.calcular(datetime.now(), virada)
            ident = ident_svc.resolve_por_odate(cur, oficial, data_ref,
                                                virada=virada)
        desenho = ident_svc.etapas_do_desenho(cur, oficial)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro DB: {e}")
    finally:
        try: cur.close()
        except Exception: pass
        try: conn.close()
        except Exception: pass

    # ── Fase 2: o Airflow, e SÓ quando ele é o único que sabe responder.
    # É o caso comum: os run_ids gerados pelo Orquestra
    # ('dep__…', 'manual__<odate>__…') não carregam a logical date, então o
    # ts_nodash só sai do dag_run. Falha aqui NUNCA derruba a resposta.
    airflow_indisponivel = False
    perguntar = ident_svc.precisa_airflow(ident)
    if perguntar and not _DAG_ID_RE.match(oficial or ""):
        # Nome que não é dag_id válido não tem DAG — a identidade fica
        # incompleta, mas o silêncio seria pior que a lacuna.
        log.warning("[EXEC-ETAPA] '%s' não é um dag_id válido — identidade "
                    "não completada pelo Airflow", oficial)
        perguntar = False
    if perguntar:
        try:
            async with get_airflow_client() as client:
                r = await client.get(
                    f"/api/v1/dags/{oficial}/dagRuns",
                    params={"limit": 100, "order_by": "-execution_date"})
            if r.is_success:
                ident = ident_svc.completa_com_airflow(
                    ident, r.json().get("dag_runs", []))
            else:
                airflow_indisponivel = True
                log.warning("[EXEC-ETAPA] Airflow devolveu %s para dagRuns de %s",
                            r.status_code, oficial)
        except Exception as e:
            airflow_indisponivel = True
            log.warning("[EXEC-ETAPA] leitura de dagRuns de %s falhou: %s",
                        oficial, e)

    # ── Fase 3: as etapas, agora que o ts_nodash é conhecido — e, no sentido
    # inverso, a SEGUNDA passada na 067 com o run_id que o Airflow acabou de
    # revelar. Sem ela a resposta voltava com `data_referencia: null` para quem
    # entra por execution_id: o run_id do Orquestra não é traduzível pela
    # string, então a 1ª passada não casa nenhuma corrida e o ODATE se perde.
    executadas = []
    if ident.get("ts_nodash"):
        conn = cur = None
        try:
            conn = get_db_conn(); cur = conn.cursor()
            if (ts_pedido and ident.get("run_id")
                    and ident.get("data_referencia") is None):
                ident = ident_svc.aplica_corrida(
                    ident,
                    ident_svc.corrida_por_run_id(cur, oficial, ident["run_id"]))
            executadas = ident_svc.etapas_executadas(
                cur, oficial, ident["ts_nodash"])
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Erro DB: {e}")
        finally:
            for f in (getattr(cur, "close", None), getattr(conn, "close", None)):
                try:
                    f and f()
                except Exception:
                    pass

    etapas = [
        {**e, "inicio": _fmt_dt(e.get("inicio")), "fim": _fmt_dt(e.get("fim"))}
        for e in ident_svc.compor_etapas(desenho, executadas)
    ]

    # A corrida do pipeline é a candidata VENCEDORA da identidade — não uma
    # segunda consulta com uma segunda regra de "mais recente" (D14/D15).
    corrida = None
    for c in (ident.get("candidatos") or []):
        if c.get("run_id") and c["run_id"] == ident.get("run_id"):
            corrida = {**c, "inicio": _fmt_dt(c.get("inicio")),
                       "fim": _fmt_dt(c.get("fim"))}
            break

    # `razao` só existe quando NÃO há etapas executadas — é a explicação do
    # vazio, nunca um erro disfarçado.
    razao = None
    if not executadas:
        if ident.get("motivo") == ident_svc.SEM_LINHA_NA_DATA:
            razao = "sem_execucao_na_data"
        elif ident.get("motivo"):
            razao = ident["motivo"]
        elif airflow_indisponivel:
            razao = "airflow_indisponivel"
        else:
            razao = "sem_etapas_registradas"

    ident_json = _ident_json(ident)
    return {
        "pipeline_name": oficial,
        # Pelo ODATE, é o pedido; pelo execution_id, é o que a 067 revelou (pode
        # ser null quando a corrida não está registrada — vazio honesto).
        "data_referencia": (data_ref.strftime("%Y-%m-%d") if data_ref
                            else ident_json["data_referencia"]),
        "identidade": ident_json,
        "corrida": corrida,
        "etapas": etapas,
        "total_etapas": len(etapas),
        "etapas_executadas": len(executadas),
        "vazio": not executadas,
        "razao": razao,
        "migration_067_pendente": not tem_067,
        "airflow_indisponivel": airflow_indisponivel,
    }


async def _estados_task_instances(dag_id: str, exec_id: str) -> dict:
    """task_id → {state, end_date} das task instances do dag_run cuja logical
    date (ts_nodash) casa EXATAMENTE com ``exec_id``. {} em qualquer falha ou
    sem match exato — melhor não reconciliar do que fechar pelo run errado.

    Pagina os taskInstances (o Airflow capa o limit por página em 100) — um
    fluxo de 40 etapas gera 120+ tasks com o trio de telemetria."""
    try:
        async with get_airflow_client() as client:
            r = await client.get(f"/api/v1/dags/{dag_id}/dagRuns",
                                 params={"limit": 50, "order_by": "-execution_date"})
            if not r.is_success:
                return {}
            runs = r.json().get("dag_runs", [])
            if not runs:
                return {}
            run = _escolhe_dag_run(runs, exec_id)
            logical = run.get("logical_date") or run.get("execution_date") or ""
            if _iso_to_ts_nodash(logical) != exec_id:
                return {}
            out: dict = {}
            offset = 0
            while True:
                r2 = await client.get(
                    f"/api/v1/dags/{dag_id}/dagRuns/{run['dag_run_id']}/taskInstances",
                    params={"limit": 100, "offset": offset})
                if not r2.is_success:
                    return out if offset else {}
                payload = r2.json()
                tis = payload.get("task_instances", [])
                for ti in tis:
                    st = (ti.get("state") or "").lower()
                    if st and ti.get("task_id"):
                        out[ti["task_id"]] = {"state": st,
                                              "end_date": ti.get("end_date")}
                offset += len(tis)
                if not tis or offset >= int(payload.get("total_entries") or 0):
                    break
            return out
    except Exception as e:
        log.warning("reconciliar: leitura de task instances falhou (%s)", e)
        return {}


def _end_date_local(iso) -> str | None:
    """end_date ISO (UTC) do Airflow → 'YYYY-MM-DD HH:MM:SS' no fuso local do
    banco (America/Sao_Paulo) — o resto da telemetria usa GETDATE() local."""
    if not iso:
        return None
    try:
        from datetime import timezone
        from zoneinfo import ZoneInfo
        dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(ZoneInfo("America/Sao_Paulo")).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


@router.post("/execucoes/reconciliar", tags=["execucoes"])
async def reconciliar_execucao(body: dict = Body(default={}), _auth: dict = Depends(require_perm(PERM_EXECUTAR))):
    """Fecha uma execução presa em RUNNING usando o status REAL da fonte.

    Espelho puro, em dois passos:
      1. DataStage: cruza com o etl_ds_job_log (monitor central via dsjob) e
         fecha o que já terminou lá (1=SUCCESS, 2=WARNING, 3=FAILED).
      2. Airflow REST (genérico — shell/python/storedproc/http e DS cujo log
         também travou): consulta o estado das task instances do dag_run casado
         pela logical date e fecha o que o Airflow já deu por terminado
         (success/failed/upstream_failed/skipped). Task ainda RUNNING não é
         tocada — para forçar, use a tela Finalizar Pipeline.

    Remédio manual, on-demand e idempotente. Body: execution_id, pipeline.
    """
    execution_id = (body.get("execution_id") or "").strip()
    pipeline = (body.get("pipeline") or "").strip()
    if not execution_id or not pipeline:
        raise HTTPException(status_code=400, detail="execution_id e pipeline são obrigatórios")
    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute(
            """
            UPDATE e SET
                e.status = CASE l.status_code WHEN 1 THEN 'SUCCESS' WHEN 2 THEN 'WARNING'
                                              WHEN 3 THEN 'FAILED' ELSE e.status END,
                e.end_time = COALESCE(l.updated_at, GETDATE()),
                e.duration_seconds = DATEDIFF(SECOND, e.start_time, COALESCE(l.updated_at, GETDATE())),
                e.updated_at = GETDATE()
            FROM dbo.etl_job_execution e
            JOIN dbo.etl_ds_job_log l
              ON l.execution_id = e.execution_id AND l.pipeline_name = e.pipeline
             AND l.job_name = e.job_name
            WHERE e.execution_id = ? AND e.pipeline = ?
              AND e.status = 'RUNNING' AND e.end_time IS NULL
              AND l.status_code IN (1, 2, 3)
            """,
            (execution_id, pipeline),
        )
        closed_ds = max(0, cur.rowcount if cur.rowcount is not None else 0)

        # Passo 2 — genérico via Airflow REST, para o que sobrou em RUNNING.
        closed_af = 0
        cur.execute(
            "SELECT job_name, task_id FROM dbo.etl_job_execution "
            "WHERE execution_id=? AND pipeline=? AND status='RUNNING' AND end_time IS NULL",
            (execution_id, pipeline))
        presos = cur.fetchall()
        if presos:
            estados = await _estados_task_instances(pipeline, execution_id)
            _TERMINAL = {"success": "SUCCESS", "failed": "FAILED",
                         "upstream_failed": "FAILED", "skipped": "SKIPPED"}
            for job_name, task_id in presos:
                ti = estados.get(task_id) or estados.get(job_name) or {}
                novo = _TERMINAL.get(ti.get("state") or "")
                if not novo:
                    continue
                # end_time REAL da task (Airflow, convertido p/ hora local) —
                # GETDATE() só como fallback; reconciliação tardia com o "agora"
                # inflaria a duração e contaminaria o P90 do SLA preditivo.
                fim_local = _end_date_local(ti.get("end_date"))
                cur.execute(
                    "UPDATE dbo.etl_job_execution SET status=?, "
                    "end_time=COALESCE(?, GETDATE()), "
                    "duration_seconds=CASE WHEN ?='SKIPPED' THEN 0 ELSE "
                    "DATEDIFF(SECOND, start_time, COALESCE(?, GETDATE())) END, "
                    "updated_at=GETDATE() "
                    "WHERE execution_id=? AND pipeline=? AND job_name=? AND task_id=? "
                    "AND status='RUNNING' AND end_time IS NULL",
                    (novo, fim_local, novo, fim_local,
                     execution_id, pipeline, job_name, task_id))
                closed_af += max(0, cur.rowcount or 0)

        conn.commit()
        cur.close(); conn.close()
        return {"closed": closed_ds + closed_af, "closed_datastage": closed_ds,
                "closed_airflow": closed_af,
                "execution_id": execution_id, "pipeline": pipeline}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/execucoes/ack", tags=["execucoes"])
async def ack_failure(body: dict = Body(default={}), _auth: dict = Depends(require_perm(PERM_EXECUTAR))):
    """Acknowledge de falha — operador assume o incidente e notifica o Teams.

    Body: execution_id, pipeline, user (matrícula), display_name (nome completo),
          note (opcional), remove (bool, desfaz)
    """
    exec_id      = (body.get("execution_id") or "").strip()
    pipeline     = (body.get("pipeline")     or "").strip()
    user         = (body.get("user")         or "").strip()
    display_name = (body.get("display_name") or "").strip() or None
    note         = (body.get("note")         or "").strip() or None
    # Rótulo amigável para a notificação (nome do job na malha; pipeline nos demais).
    # NÃO afeta a chave de persistência — só o texto exibido no Teams.
    label        = (body.get("label")        or "").strip() or None
    remove       = bool(body.get("remove", False))

    if not exec_id or not pipeline:
        raise HTTPException(status_code=422, detail="execution_id e pipeline são obrigatórios")
    if not remove and not user:
        raise HTTPException(status_code=422, detail="user é obrigatório")

    try:
        conn = get_db_conn(); cur = conn.cursor()
        if remove:
            if _ensure_resolve_columns(conn, cur):
                cur.execute(
                    "SELECT resolved_at FROM dbo.etl_failure_ack WHERE execution_id=? AND pipeline=?",
                    (exec_id, pipeline))
                row = cur.fetchone()
                if row and row[0] is not None:
                    cur.close(); conn.close()
                    raise HTTPException(
                        status_code=409,
                        detail="Falha já resolvida — desfaça a resolução antes de remover a assunção")
            cur.execute(
                "DELETE FROM dbo.etl_failure_ack WHERE execution_id=? AND pipeline=?",
                (exec_id, pipeline))
            conn.commit(); cur.close(); conn.close()
            return {"ok": True, "action": "removed"}

        # Idempotente: só insere se ainda não existe
        cur.execute("""
            IF NOT EXISTS (SELECT 1 FROM dbo.etl_failure_ack WHERE execution_id=? AND pipeline=?)
                INSERT INTO dbo.etl_failure_ack (execution_id, pipeline, ack_by, display_name, note)
                VALUES (?, ?, ?, ?, ?)
        """, (exec_id, pipeline, exec_id, pipeline, user, display_name, note))
        conn.commit()

        cur.execute(
            "SELECT ack_by, display_name, ack_at FROM dbo.etl_failure_ack "
            "WHERE execution_id=? AND pipeline=?",
            (exec_id, pipeline))
        row = cur.fetchone()
        cur.close(); conn.close()

        ack_by_db      = row[0] if row else user
        display_name_db = row[1] if row else display_name
        ack_at_db      = _fmt_dt(row[2]) if row else None

        # Notificar Teams — _teams_ack_card faz I/O de rede síncrono; roda em
        # thread separada para não bloquear o event loop de outras requisições.
        try:
            await asyncio.to_thread(
                _teams_ack_card,
                pipeline=label or pipeline, exec_id=exec_id,
                ack_by=ack_by_db, display_name=display_name_db or ack_by_db,
                ack_at=ack_at_db, note=note,
                webhook_var="TEAMS_WEBHOOK_URL_CVP",
            )
        except Exception as e:
            log.warning("[ACK] Teams ignorado: %s", e)

        try:
            await asyncio.to_thread(add_notificacao, ack_by_db,
                                    f"Falha assumida — {label or pipeline}",
                                    note, "info", "/logs")
        except Exception:
            pass

        return {"ok": True, "action": "acked",
                "ack_by": ack_by_db,
                "display_name": display_name_db or ack_by_db,
                "ack_at": ack_at_db}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


_resolve_cols_ready = False


def _ensure_resolve_columns(conn, cur) -> bool:
    """Garante colunas de resolução na etl_failure_ack. Retorna True se existem.

    Cacheia o estado "True" em memória do processo: colunas adicionadas por
    migration nunca são removidas, então uma vez confirmadas não há motivo
    para repetir a checagem em toda requisição (evita 5 round-trips extras
    por chamada em /execucoes/falhas, /falhas-summary e /resolve).
    """
    global _resolve_cols_ready
    if _resolve_cols_ready:
        return True
    _RESOLVE_COLS = [
        ("resolved_by",            "NVARCHAR(64)"),
        ("resolved_display_name",  "NVARCHAR(128)"),
        ("resolved_at",            "DATETIME"),
        ("resolution_note",        "NVARCHAR(500)"),
        ("snow_ticket",            "NVARCHAR(64)"),
    ]
    for col, ddl in _RESOLVE_COLS:
        try:
            cur.execute(
                "IF NOT EXISTS ("
                "  SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS"
                "  WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME='etl_failure_ack' AND COLUMN_NAME=?"
                ") EXEC('ALTER TABLE dbo.etl_failure_ack ADD " + col + " " + ddl + " NULL')",
                (col,))
            conn.commit()
        except Exception:
            try: conn.rollback()
            except Exception: pass
    # Verifica se resolved_at existe (proxy para todas)
    try:
        cur.execute(
            "SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME='etl_failure_ack' AND COLUMN_NAME='resolved_at'")
        ready = bool(cur.fetchone())
    except Exception:
        ready = False
    if ready:
        _resolve_cols_ready = True
    return ready


def _failure_cte(cutoff: str, filter_pipeline: str | None, filter_project: str | None):
    """Retorna (cte_sql, params) agregando execuções de pipeline com FAILED.

    Colunas `origem` (sempre 'pipeline') e `job_name` (sempre NULL) são mantidas
    por compatibilidade de shape da resposta."""
    where_parts = ["e.start_time >= ?"]
    params: list = [cutoff]
    if filter_pipeline:
        where_parts.append("e.pipeline LIKE ?")
        params.append(f"%{filter_pipeline}%")
    if filter_project:
        where_parts.append("e.project = ?")
        params.append(filter_project)
    where_sql = " AND ".join(where_parts)

    cte = f"""
        WITH agg AS (
            SELECT
                e.execution_id, e.project, e.pipeline,
                MIN(e.start_time)                    AS inicio,
                MAX(e.end_time)                      AS fim,
                COALESCE(SUM(e.duration_seconds), 0) AS duracao_total_segundos,
                COUNT(*)                             AS total_jobs,
                SUM(CASE WHEN e.status='FAILED'  THEN 1 ELSE 0 END) AS jobs_falha,
                SUM(CASE WHEN e.status='WARNING' THEN 1 ELSE 0 END) AS jobs_warning,
                CAST('pipeline' AS VARCHAR(10)) AS origem,
                CAST(NULL AS VARCHAR(300))      AS job_name
            FROM dbo.etl_job_execution e
            WHERE {where_sql}
            GROUP BY e.execution_id, e.project, e.pipeline
            HAVING SUM(CASE WHEN e.status='FAILED' THEN 1 ELSE 0 END) > 0
        )
    """
    return cte, params


@router.get("/execucoes/falhas-summary", tags=["execucoes"])
def get_falhas_summary(days: int = Query(7, ge=1, le=90)):
    """Retorna contadores de falhas para os cards de KPI (total, sem_ack, com_ack, resolvidas)."""
    try:
        conn = get_db_conn(); cur = conn.cursor()
        has_resolved = _ensure_resolve_columns(conn, cur)
        cutoff = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        cte, params = _failure_cte(cutoff, None, None)

        if has_resolved:
            cur.execute(cte + """
                SELECT
                    COUNT(DISTINCT a.execution_id + '|' + ISNULL(a.pipeline, '')) AS total,
                    COUNT(DISTINCT CASE WHEN ack.execution_id IS NULL
                          THEN a.execution_id + '|' + ISNULL(a.pipeline, '') END) AS sem_ack,
                    COUNT(DISTINCT CASE WHEN ack.execution_id IS NOT NULL
                          AND ack.resolved_at IS NULL THEN a.execution_id + '|' + ISNULL(a.pipeline, '') END) AS com_ack,
                    COUNT(DISTINCT CASE WHEN ack.resolved_at IS NOT NULL
                          THEN a.execution_id + '|' + ISNULL(a.pipeline, '') END) AS resolvidas
                FROM agg a
                LEFT JOIN dbo.etl_failure_ack ack
                       ON ack.execution_id = a.execution_id AND ack.pipeline = a.pipeline
            """, params)
        else:
            cur.execute(cte + """
                SELECT
                    COUNT(DISTINCT a.execution_id + '|' + ISNULL(a.pipeline, '')) AS total,
                    COUNT(DISTINCT CASE WHEN ack.execution_id IS NULL
                          THEN a.execution_id + '|' + ISNULL(a.pipeline, '') END) AS sem_ack,
                    COUNT(DISTINCT CASE WHEN ack.execution_id IS NOT NULL
                          THEN a.execution_id + '|' + ISNULL(a.pipeline, '') END) AS com_ack,
                    0 AS resolvidas
                FROM agg a
                LEFT JOIN dbo.etl_failure_ack ack
                       ON ack.execution_id = a.execution_id AND ack.pipeline = a.pipeline
            """, params)

        row = cur.fetchone()
        cur.close(); conn.close()
        return {
            "period_days": days,
            "total":     int(row[0] or 0) if row else 0,
            "sem_ack":   int(row[1] or 0) if row else 0,
            "com_ack":   int(row[2] or 0) if row else 0,
            "resolvidas":int(row[3] or 0) if row else 0,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/execucoes/resolve", tags=["execucoes"])
async def resolve_failure(body: dict = Body(default={}), auth: dict = Depends(require_perm(PERM_EXECUTAR))):
    """Marca uma falha como resolvida (ou desfaz com remove=true) e notifica o Teams.

    Body: execution_id, pipeline, resolution_note (opcional), snow_ticket (opcional), remove (bool)
    """
    exec_id         = (body.get("execution_id")    or "").strip()
    pipeline        = (body.get("pipeline")         or "").strip()
    resolution_note = (body.get("resolution_note") or "").strip() or None
    snow_ticket     = (body.get("snow_ticket")     or "").strip() or None
    remove          = bool(body.get("remove", False))
    matricula       = (body.get("user")            or "").strip() or auth.get("matricula", "")
    display_name    = (body.get("display_name")    or "").strip() or None
    # Rótulo amigável para a notificação (nome do job na malha; pipeline nos demais).
    label           = (body.get("label")           or "").strip() or None

    if not exec_id or not pipeline:
        raise HTTPException(status_code=422, detail="execution_id e pipeline são obrigatórios")

    try:
        conn = get_db_conn(); cur = conn.cursor()
        _ensure_resolve_columns(conn, cur)

        if remove:
            cur.execute(
                "UPDATE dbo.etl_failure_ack "
                "SET resolved_by=NULL, resolved_display_name=NULL, resolved_at=NULL, "
                "    resolution_note=NULL, snow_ticket=NULL "
                "WHERE execution_id=? AND pipeline=?",
                (exec_id, pipeline))
            conn.commit(); cur.close(); conn.close()
            return {"ok": True, "action": "unresolved"}

        # Garante ack existe antes de resolver (cria auto-ack se necessário)
        cur.execute(
            "IF NOT EXISTS (SELECT 1 FROM dbo.etl_failure_ack WHERE execution_id=? AND pipeline=?)"
            "  INSERT INTO dbo.etl_failure_ack (execution_id, pipeline, ack_by, display_name)"
            "  VALUES (?, ?, ?, ?)",
            (exec_id, pipeline, exec_id, pipeline, matricula, display_name))

        cur.execute(
            "UPDATE dbo.etl_failure_ack "
            "SET resolved_by=?, resolved_display_name=?, resolved_at=GETDATE(), "
            "    resolution_note=?, snow_ticket=? "
            "WHERE execution_id=? AND pipeline=?",
            (matricula, display_name, resolution_note, snow_ticket, exec_id, pipeline))
        conn.commit()

        cur.execute(
            "SELECT resolved_by, resolved_display_name, resolved_at, resolution_note, snow_ticket "
            "FROM dbo.etl_failure_ack WHERE execution_id=? AND pipeline=?",
            (exec_id, pipeline))
        row = cur.fetchone()
        cur.close(); conn.close()

        resolved_by_db           = row[0] if row else matricula
        resolved_display_name_db = row[1] if row else display_name
        resolved_at_db           = _fmt_dt(row[2]) if row else None
        resolution_note_db       = row[3] if row else resolution_note
        snow_ticket_db           = row[4] if row else snow_ticket

        # Notificar Teams — _teams_resolved_card faz I/O de rede síncrono; roda
        # em thread separada para não bloquear o event loop de outras requisições.
        try:
            await asyncio.to_thread(
                _teams_resolved_card,
                pipeline=label or pipeline, exec_id=exec_id,
                resolved_by=resolved_by_db, display_name=resolved_display_name_db or resolved_by_db,
                resolved_at=resolved_at_db, resolution_note=resolution_note_db,
                snow_ticket=snow_ticket_db,
                webhook_var="TEAMS_WEBHOOK_URL_CVP",
            )
        except Exception as e:
            log.warning("[RESOLVE] Teams ignorado: %s", e)

        try:
            await asyncio.to_thread(add_notificacao, resolved_by_db,
                                    f"Falha resolvida — {label or pipeline}",
                                    resolution_note_db, "success", "/logs")
        except Exception:
            pass

        return {
            "ok": True, "action": "resolved",
            "resolved_by":           resolved_by_db,
            "resolved_display_name": resolved_display_name_db,
            "resolved_at":           resolved_at_db,
            "resolution_note":       resolution_note_db,
            "snow_ticket":           snow_ticket_db,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/execucoes/resolve-bulk", tags=["execucoes"])
async def resolve_failures_bulk(body: dict = Body(default={}), auth: dict = Depends(require_perm(PERM_EXECUTAR))):
    """Resolve VÁRIAS falhas de uma vez com a MESMA nota/ticket (auto-ack em cada).

    Útil p/ fechar erros históricos em lote (ex.: falhas importadas de antes do
    Orquestra). Body: items: [{execution_id, pipeline}], resolution_note?,
    snow_ticket?, user? (matrícula), display_name?.
    """
    items = body.get("items") or []
    if not isinstance(items, list) or not items:
        raise HTTPException(status_code=422, detail="items (lista não vazia) é obrigatório")
    resolution_note = (body.get("resolution_note") or "").strip() or None
    snow_ticket     = (body.get("snow_ticket")     or "").strip() or None
    matricula       = (body.get("user")            or "").strip() or auth.get("matricula", "")
    display_name    = (body.get("display_name")    or "").strip() or None

    done = 0
    alvos: list[str] = []  # rótulos (job da malha / pipeline) das falhas resolvidas
    try:
        conn = get_db_conn(); cur = conn.cursor()
        _ensure_resolve_columns(conn, cur)
        for it in items:
            eid = (it.get("execution_id") or "").strip()
            pl  = (it.get("pipeline")     or "").strip()
            if not eid or not pl:
                continue
            cur.execute(
                "IF NOT EXISTS (SELECT 1 FROM dbo.etl_failure_ack WHERE execution_id=? AND pipeline=?)"
                "  INSERT INTO dbo.etl_failure_ack (execution_id, pipeline, ack_by, display_name)"
                "  VALUES (?, ?, ?, ?)",
                (eid, pl, eid, pl, matricula, display_name))
            cur.execute(
                "UPDATE dbo.etl_failure_ack "
                "SET resolved_by=?, resolved_display_name=?, resolved_at=GETDATE(), "
                "    resolution_note=?, snow_ticket=? "
                "WHERE execution_id=? AND pipeline=?",
                (matricula, display_name, resolution_note, snow_ticket, eid, pl))
            alvos.append((it.get("label") or pl).strip())
            done += 1
        conn.commit(); cur.close(); conn.close()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    # UM card-resumo no Teams (evita spam de N cards ao fechar histórico em lote),
    # listando cada pipeline/job resolvido para facilitar a identificação.
    if done:
        try:
            await asyncio.to_thread(
                _teams_resolved_card,
                pipeline="", exec_id="—",
                resolved_by=matricula, display_name=display_name or matricula,
                resolved_at=None, resolution_note=resolution_note, snow_ticket=snow_ticket,
                webhook_var="TEAMS_WEBHOOK_URL_CVP", itens=alvos,
            )
        except Exception as e:
            log.warning("[RESOLVE-BULK] Teams ignorado: %s", e)
        try:
            await asyncio.to_thread(add_notificacao, matricula,
                                    f"{done} falha(s) resolvidas em massa", None,
                                    "success", "/logs")
        except Exception:
            pass

    return {"ok": True, "resolved": done}


@router.post("/execucoes/ack-bulk", tags=["execucoes"])
async def ack_failures_bulk(body: dict = Body(default={}), auth: dict = Depends(require_perm(PERM_EXECUTAR))):
    """Assume VÁRIAS falhas de uma vez (idempotente: NÃO rouba assunção existente).

    Body: items: [{execution_id, pipeline}], note?, user? (matrícula), display_name?.
    Devolve quantas foram assumidas (acked) e quantas já tinham dono (skipped).
    """
    items = body.get("items") or []
    if not isinstance(items, list) or not items:
        raise HTTPException(status_code=422, detail="items (lista não vazia) é obrigatório")
    note         = (body.get("note")         or "").strip() or None
    matricula    = (body.get("user")         or "").strip() or auth.get("matricula", "")
    display_name = (body.get("display_name") or "").strip() or None
    if not matricula:
        raise HTTPException(status_code=422, detail="user (matrícula) é obrigatório")

    acked = skipped = 0
    alvos: list[str] = []  # rótulos (job da malha / pipeline) das falhas assumidas agora
    try:
        conn = get_db_conn(); cur = conn.cursor()
        for it in items:
            eid = (it.get("execution_id") or "").strip()
            pl  = (it.get("pipeline")     or "").strip()
            if not eid or not pl:
                continue
            cur.execute("SELECT 1 FROM dbo.etl_failure_ack WHERE execution_id=? AND pipeline=?", (eid, pl))
            if cur.fetchone():
                skipped += 1
                continue
            cur.execute(
                "INSERT INTO dbo.etl_failure_ack (execution_id, pipeline, ack_by, display_name, note) "
                "VALUES (?, ?, ?, ?, ?)",
                (eid, pl, matricula, display_name, note))
            alvos.append((it.get("label") or pl).strip())
            acked += 1
        conn.commit(); cur.close(); conn.close()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    if acked:
        try:
            await asyncio.to_thread(
                _teams_ack_card,
                pipeline="", exec_id="—",
                ack_by=matricula, display_name=display_name or matricula,
                ack_at=None, note=note, webhook_var="TEAMS_WEBHOOK_URL_CVP", itens=alvos,
            )
        except Exception as e:
            log.warning("[ACK-BULK] Teams ignorado: %s", e)
        try:
            await asyncio.to_thread(add_notificacao, matricula,
                                    f"{acked} falha(s) assumidas em massa", None,
                                    "info", "/logs")
        except Exception:
            pass

    return {"ok": True, "acked": acked, "skipped": skipped}


@router.get("/execucoes/falhas", tags=["execucoes"])
def list_falhas(
    days: int = Query(7, ge=1, le=90),
    status_ack: Optional[str] = Query(None),  # "sem_ack" | "com_ack" | "resolvida"
    filter_pipeline: Optional[str] = None,
    filter_project: Optional[str] = None,
    ack_by: Optional[str] = Query(None),   # matrícula: filtra "assumidas por mim"
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    """Lista execuções com falha no período com dados de ack e resolução (aba Gestão de Falhas)."""
    try:
        conn = get_db_conn(); cur = conn.cursor()
        has_resolved = _ensure_resolve_columns(conn, cur)
        cutoff = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        cte, params = _failure_cte(cutoff, filter_pipeline, filter_project)

        # Filtro por situação de ack/resolve — adicionado ao WHERE pós-CTE
        ack_filter = ""
        if status_ack == "sem_ack":
            ack_filter = "AND ack.execution_id IS NULL"
        elif status_ack == "com_ack":
            ack_filter = "AND ack.execution_id IS NOT NULL AND (ack.resolved_at IS NULL)" if has_resolved \
                         else "AND ack.execution_id IS NOT NULL"
        elif status_ack == "resolvida":
            ack_filter = "AND ack.execution_id IS NOT NULL AND ack.resolved_at IS NOT NULL" if has_resolved \
                         else "AND ack.execution_id IS NOT NULL"

        # Filtro "assumidas por mim" — só falhas com ack do usuário informado.
        ack_params: list = []
        if ack_by:
            ack_filter += " AND ack.ack_by = ?"
            ack_params.append(ack_by)

        cur.execute(cte + f"""
            SELECT COUNT(DISTINCT a.execution_id + '|' + ISNULL(a.pipeline, ''))
            FROM agg a
            LEFT JOIN dbo.etl_failure_ack ack
                   ON ack.execution_id = a.execution_id AND ack.pipeline = a.pipeline
            WHERE 1=1 {ack_filter}
        """, params + ack_params)
        total_row = cur.fetchone()
        total = int(total_row[0] or 0) if total_row else 0

        resolve_sel = ", ack.resolved_by, ack.resolved_display_name, ack.resolved_at, " \
                      "ack.resolution_note, ack.snow_ticket" \
                      if has_resolved else ""

        cur.execute(cte + f"""
            SELECT a.execution_id, a.project, a.pipeline,
                   a.inicio, a.fim, a.duracao_total_segundos,
                   a.total_jobs, a.jobs_falha, a.jobs_warning,
                   ack.ack_by, ack.display_name, ack.ack_at, ack.note
                   {resolve_sel}
                   , a.origem, a.job_name
            FROM agg a
            LEFT JOIN dbo.etl_failure_ack ack
                   ON ack.execution_id = a.execution_id AND ack.pipeline = a.pipeline
            WHERE 1=1 {ack_filter}
            ORDER BY a.inicio DESC
            OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
        """, params + ack_params + [offset, limit])

        rows = cur.fetchall()
        cur.close(); conn.close()

        # origem/job_name vêm após as colunas de resolução (5 quando has_resolved)
        ox = 13 + (5 if has_resolved else 0)

        data = []
        for r in rows:
            item: dict = {
                "execution_id": r[0], "project": r[1], "pipeline": r[2],
                "inicio": _fmt_dt(r[3]), "fim": _fmt_dt(r[4]),
                "duracao_total_segundos": int(r[5] or 0),
                "total_jobs": int(r[6] or 0), "jobs_falha": int(r[7] or 0),
                "jobs_warning": int(r[8] or 0),
                "ack_by": r[9], "display_name": r[10],
                "ack_at": _fmt_dt(r[11]), "note": r[12],
                "resolved_by":           r[13] if has_resolved else None,
                "resolved_display_name": r[14] if has_resolved else None,
                "resolved_at":           _fmt_dt(r[15]) if has_resolved else None,
                "resolution_note":       r[16] if has_resolved else None,
                "snow_ticket":           r[17] if has_resolved else None,
                "origem":   r[ox],
                "job_name": r[ox + 1],
            }
            data.append(item)

        return {"total": total, "offset": offset, "limit": limit, "data": data}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/execucoes/duracao-media", tags=["execucoes"])
def get_duracao_media(pipeline: str = Query(...), limit: int = Query(30, ge=5, le=200)):
    """Retorna duração média (P50) por job_name para um pipeline — usado para desvio de duração."""
    try:
        conn = get_db_conn(); cur = conn.cursor()
        # PERCENTILE_CONT é função de janela — não pode coexistir com GROUP BY
        # no mesmo nível; calculamos a janela em subquery e agregamos por fora.
        cur.execute(f"""
            SELECT job_name,
                   AVG(CAST(duration_seconds AS FLOAT)) AS avg_sec,
                   MAX(p50_sec) AS p50_sec,
                   COUNT(*) AS execucoes
            FROM (
                SELECT job_name, duration_seconds,
                       PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY duration_seconds)
                           OVER (PARTITION BY job_name) AS p50_sec
                FROM (
                    SELECT TOP {limit * 10} job_name, duration_seconds
                    FROM dbo.etl_job_execution
                    WHERE pipeline = ? AND status IN ('SUCCESS','WARNING')
                      AND duration_seconds IS NOT NULL AND duration_seconds > 0
                    ORDER BY start_time DESC
                ) base
            ) t
            GROUP BY job_name
        """, [pipeline])
        data = {r[0]: {"avg": round(r[1] or 0), "p50": round(r[2] or 0), "n": r[3]}
                for r in cur.fetchall()}
        cur.close(); conn.close()
        return {"pipeline": pipeline, "data": data}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── SLA Adherence Report (U6) ─────────────────────────────────────────────────

@router.get("/execucoes/sla-report", tags=["execucoes"])
def sla_report(
    date_ini: Optional[str] = Query(None, description="Data inicial YYYY-MM-DD (padrão: 30 dias atrás)"),
    date_fim: Optional[str] = Query(None, description="Data final YYYY-MM-DD (padrão: hoje)"),
    project:  Optional[str] = Query(None, description="Filtrar por projeto"),
    limit:    int           = Query(200, ge=1, le=1000),
    _auth: dict = Depends(get_current_user),
):
    """Aderência ao SLA por pipeline no período.

    Para cada pipeline com SLA definido, retorna:
    - total de execuções concluídas
    - execuções dentro do SLA
    - execuções que estouraram o SLA
    - percentual de aderência
    - duração média e máxima
    """
    from datetime import datetime as _dt
    try:
        fim_dt   = _dt.strptime(date_fim, "%Y-%m-%d") if date_fim else _dt.now()
        ini_dt   = _dt.strptime(date_ini, "%Y-%m-%d") if date_ini else fim_dt - timedelta(days=30)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"Data inválida: {e}")

    dt_ini = ini_dt.strftime("%Y-%m-%d 00:00:00")
    dt_fim = (fim_dt + timedelta(days=1)).strftime("%Y-%m-%d 00:00:00")
    where_proj = " AND e.project = ? " if project else ""

    try:
        conn = get_db_conn(); cur = conn.cursor()

        # Aggregated execution view: one row per (pipeline, execution_id)
        cur.execute(f"""
            WITH runs AS (
                SELECT e.execution_id, e.pipeline, e.project,
                    MIN(e.start_time)  AS inicio,
                    MAX(e.end_time)    AS fim,
                    SUM(CASE WHEN e.status IN ('SUCCESS','WARNING') THEN 1 ELSE 0 END) AS jobs_ok,
                    SUM(CASE WHEN e.status = 'FAILED'              THEN 1 ELSE 0 END) AS jobs_fail,
                    DATEDIFF(SECOND, MIN(e.start_time), MAX(COALESCE(e.end_time, GETDATE()))) AS dur_sec
                FROM dbo.etl_job_execution e
                WHERE e.start_time >= ? AND e.start_time < ?
                  AND e.status IN ('SUCCESS','WARNING','FAILED')
                  {where_proj}
                GROUP BY e.execution_id, e.pipeline, e.project
            ),
            run_status AS (
                SELECT execution_id, pipeline, project, inicio, fim, dur_sec,
                    CASE WHEN jobs_fail > 0 THEN 'FAILED'
                         WHEN jobs_ok  > 0 THEN 'SUCCESS'
                         ELSE 'UNKNOWN' END AS status_geral
                FROM runs
            )
            SELECT
                rs.pipeline,
                rs.project,
                p.criticidade,
                p.sla_minutos,
                COUNT(*)                                                             AS total_exec,
                SUM(CASE WHEN rs.status_geral IN ('SUCCESS') THEN 1 ELSE 0 END)     AS exec_sucesso,
                SUM(CASE WHEN rs.status_geral = 'FAILED' THEN 1 ELSE 0 END)         AS exec_falha,
                SUM(CASE WHEN p.sla_minutos IS NOT NULL
                          AND rs.dur_sec > p.sla_minutos * 60 THEN 1 ELSE 0 END)    AS exec_estouro_sla,
                AVG(CAST(rs.dur_sec AS float))                                       AS avg_dur_sec,
                MAX(rs.dur_sec)                                                      AS max_dur_sec,
                MIN(rs.inicio)                                                       AS primeira_exec,
                MAX(rs.inicio)                                                       AS ultima_exec
            FROM run_status rs
            JOIN dbo.etl_pipeline p ON p.pipeline_name = rs.pipeline
            WHERE COALESCE(p.ambiente, 'PROD') = 'PROD'
            GROUP BY rs.pipeline, rs.project, p.criticidade, p.sla_minutos
            ORDER BY
                CASE UPPER(COALESCE(p.criticidade,'')) WHEN 'ALTA' THEN 1 WHEN 'MEDIA' THEN 2 WHEN 'BAIXA' THEN 3 ELSE 4 END,
                COUNT(*) DESC
            OFFSET 0 ROWS FETCH NEXT ? ROWS ONLY
        """, [dt_ini, dt_fim] + ([project] if project else []) + [limit])

        cols = [d[0] for d in cur.description]
        rows = []
        for row in cur.fetchall():
            r = dict(zip(cols, row))
            total  = int(r["total_exec"] or 0)
            sla_m  = r["sla_minutos"]
            estou  = int(r["exec_estouro_sla"] or 0)
            sucesso = int(r["exec_sucesso"] or 0)
            aderencia = round((1 - estou / total) * 100, 1) if total and sla_m else None
            rows.append({
                "pipeline":      r["pipeline"],
                "project":       r["project"],
                "criticidade":   r["criticidade"] or "Media",
                "sla_minutos":   sla_m,
                "total_exec":    total,
                "exec_sucesso":  sucesso,
                "exec_falha":    int(r["exec_falha"] or 0),
                "exec_estouro_sla": estou,
                "aderencia_sla_pct": aderencia,
                "avg_dur_minutos": round((r["avg_dur_sec"] or 0) / 60, 1),
                "max_dur_minutos": round((r["max_dur_sec"] or 0) / 60, 1),
                "primeira_exec": _fmt_dt(r["primeira_exec"]),
                "ultima_exec":   _fmt_dt(r["ultima_exec"]),
            })

        cur.close(); conn.close()

        pipelines_com_sla = sum(1 for r in rows if r["sla_minutos"])
        aderencia_media = None
        vals = [r["aderencia_sla_pct"] for r in rows if r["aderencia_sla_pct"] is not None]
        if vals:
            aderencia_media = round(sum(vals) / len(vals), 1)

        return {
            "periodo": {"ini": dt_ini[:10], "fim": dt_fim[:10]},
            "filtros": {"project": project},
            "resumo": {
                "total_pipelines":        len(rows),
                "pipelines_com_sla":      pipelines_com_sla,
                "aderencia_media_pct":    aderencia_media,
            },
            "data": rows,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro DB: {e}")
