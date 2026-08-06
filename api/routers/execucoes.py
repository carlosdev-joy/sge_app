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
# O registro da CORRIDA de malha (F8 — §6.9/#3): o rerun com cascata reabre o
# ciclo que acabou de aposentar, na mesma transação do carimbo.
from services import malha_corrida as mc
# Cascata, reabertura de corrida e auditoria do rerun (F4 — §4 e decisão 1 §7).
from services import rerun as rerun_svc
# Pausa de etapa em runtime, liberação e cancelamento (F5 — §5 Bloco C, decisão 3).
from services import espera as espera_svc

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


async def _resolve_alvo_rerun(pipeline: str, *, exec_id: str, dag_run_id: str,
                              data_referencia: str, gesto: str = "reexecutar") -> tuple:
    """Resolve (pipeline, …) → ``(oficial, dag_run_id, ident, data_ref)`` para
    o gesto destrutivo da F4. **Recusa em vez de escolher** quando não sabe.

    As três portas, por ordem de precisão — e cada uma existe por um motivo:

      1. ``dag_run_id`` explícito → o operador JÁ escolheu (o canvas mostra o
         aviso de ambiguidade da F3 e deixa clicar numa candidata). Usa como
         veio; a ambiguidade já foi resolvida por gente.
      2. ``execution_id`` (ts_nodash) → o caminho HISTÓRICO do modal de Logs e
         do Dashboard, preservado byte a byte: casa o dag_run pela logical date
         com ``_escolhe_dag_run``. É uma corrida concreta, não há o que
         desambiguar.
      3. ``data_referencia`` (ODATE) → a linguagem da malha, entrada nova da
         F4. Aqui **e só aqui** cabe ambiguidade: o mesmo pipeline pode ter
         rodado N vezes no dia. Usa ``resolve_por_odate(estrito=True)``, o modo
         que a F2 criou exatamente para isto — com mais de uma corrida devolve
         NÃO resolvido e o gesto responde 409 com a lista, para a tela
         perguntar. Nunca "a mais recente": limpar tasks do run errado é
         destrutivo e irreversível.

    Recusa também identidade ``degradado=True`` (sem a migration 067 a
    associação corrida↔ODATE é aproximada, e o docstring do serviço de
    identidade já registra que aproximação não alimenta gesto destrutivo).
    """
    conn = cur = None
    try:
        conn = get_db_conn(); cur = conn.cursor()
        oficial = ident_svc.pipeline_oficial(cur, pipeline)
        if oficial is None:
            raise HTTPException(status_code=404,
                                detail=f"Pipeline não encontrado: '{pipeline}'")
        virada = deps_svc.virada_global(cur)
        data_ref = None
        if data_referencia:
            try:
                data_ref = datetime.strptime(data_referencia, "%Y-%m-%d").date()
            except ValueError:
                raise HTTPException(
                    status_code=422,
                    detail=f"data_referencia inválida: '{data_referencia}' "
                           "(use o formato YYYY-MM-DD)")
        if dag_run_id:
            ident = ident_svc.resolve_por_run_id(cur, oficial, dag_run_id)
        elif exec_id:
            ident = ident_svc.resolve_por_ts_nodash(cur, oficial, exec_id)
        else:
            if data_ref is None:
                data_ref = dref.calcular(datetime.now(), virada)
            ident = ident_svc.resolve_por_odate(cur, oficial, data_ref,
                                                virada=virada, estrito=True)
        if data_ref is None:
            data_ref = ident.get("data_referencia")
    finally:
        for f in (getattr(cur, "close", None), getattr(conn, "close", None)):
            try:
                f and f()
            except Exception:
                pass

    if ident.get("motivo") == ident_svc.AMBIGUO:
        raise HTTPException(
            status_code=409,
            detail={
                "erro": "corrida_ambigua",
                # `gesto` existe porque esta resolução é compartilhada: dizer
                # "reexecutar" para quem clicou em PAUSAR seria a tela falando
                # de outra coisa (visto na prova de UI). O default preserva,
                # palavra por palavra, a mensagem que a F4 já entregava.
                "mensagem": (f"Há {len(ident.get('candidatos') or [])} corridas de "
                             f"'{oficial}' nesta data de referência. Escolha qual "
                             f"{gesto} — {gesto} é um gesto sobre UMA corrida e "
                             "não se escolhe por você."
                             if gesto != "reexecutar" else
                             f"Há {len(ident.get('candidatos') or [])} corridas de "
                             f"'{oficial}' nesta data de referência. Escolha qual "
                             "reexecutar — reexecutar é destrutivo e não se "
                             "escolhe por você."),
                "candidatos": _ident_json(ident).get("candidatos"),
            })
    if ident.get("degradado"):
        raise HTTPException(
            status_code=409,
            detail={"erro": "identidade_degradada",
                    "mensagem": ("A corrida foi identificada por APROXIMAÇÃO "
                                 "(migration 067 pendente). Reexecutar exige "
                                 "identidade exata.")})
    if ident.get("motivo") == ident_svc.SEM_LINHA_NA_DATA:
        raise HTTPException(
            status_code=404,
            detail=f"Nenhuma corrida de '{oficial}' na data de referência.")
    return oficial, ident, data_ref


# A frase do aviso por razão — o operador precisa saber O QUE consertar, e as
# duas metades do deploy têm conserto diferente (rodar migration × deployar
# dags/). Falar sempre em "migration 078" era a mentira do deploy parcial.
AVISO_CASCATA_INDISPONIVEL = {
    "migration_078_pendente":
        "migration 078 pendente — nenhuma corrida pôde ser reaberta; "
        "os dependentes NÃO vão rodar de novo",
    rerun_svc.CAP_AUSENTE:
        "o motor de dependências deployado (dags/) ainda não entende corrida "
        "reaberta — nenhuma corrida foi aposentada; os dependentes NÃO vão "
        "rodar de novo. Deploy de dags/ pendente",
    rerun_svc.CAP_DESCONHECIDA:
        "não foi possível confirmar se o motor deployado (dags/) entende "
        "corrida reaberta — nada foi aposentado, para não deixar corrida "
        "carimbada sem reprocesso a caminho",
}


# ── F8: o efeito do rerun sobre o CICLO da malha (§6.9/#3) ──────────────────
#
# Nada aqui é importado no topo do módulo de propósito: `routers.malhas` importa
# `routers.pipelines` e meia dúzia de serviços, e um import de router para router
# no topo é a forma mais barata de criar um ciclo de import que só aparece no
# arranque do container. Dentro da função, o custo é um lookup em `sys.modules`.


def _corrida_operavel(cur, malha: str):
    """O portão do §11.1, emprestado do router de malhas — MESMA função, nunca
    uma segunda cópia da regra.

    Reabrir corrida que o `dags/` deployado não sabe fechar é o mesmo estrago de
    ABRIR uma: ela ficaria aberta até o teto e, enquanto isso, bloquearia o
    disparo da malha. Com o interruptor desligado (o estado de hoje), o rerun
    responde exatamente como antes desta fase."""
    from routers.malhas import _corrida_operavel as portao
    return portao(cur, malha)


def _frase_da_corrida(c: dict, sufixo: str) -> str:
    """Decisão 74 — a corrida se chama pela DATA, nunca pelo `#id`. O `#12` é
    chave de banco; quem lê às 3h procura "a corrida de 2026-08-04".

    O rótulo vem de `_rotulo_corrida`, o MESMO da tela de malhas: duas grafias
    do mesmo ciclo (uma no toast do rerun, outra no painel) fariam o operador
    achar que são dois."""
    from routers.malhas import _rotulo_corrida
    return f"a {_rotulo_corrida(c)} da malha '{c.get('malha_name')}' {sufixo}"


def _efeito_na_corrida(cur, oficial: str, alvos: list, data_ref, usuario: str,
                       saida: dict) -> None:
    """Reabre o ciclo que o rerun acabou de aposentar — ou registra que ele NÃO
    foi reaberto e por quê (§6.9/#3).

    Roda na transação de `_aplicar_cascata`, que é a MESMA que carimbou
    `substituida_em`: a spec exige as duas coisas no mesmo commit, senão ou o
    rerun rola inteiro de volta por um 2601, ou a corrida não reabre e ninguém
    percebe.

    Três desfechos, e os três são DITOS:

      • corrida `CONCLUIDA`/`FALHA` e nenhuma outra aberta da malha → reabre,
        `tentativas += 1`, e os eventos do desfecho anulado são descartados
        (é o que deixa a segunda `MALHA_CONCLUIDA` do dia existir);
      • já há OUTRA corrida aberta da malha (o plantão do dia 04 reprocessando
        o dia 03) → **não reabre** — a linha preserva o `malha_execucao_id`
        original (Decisão 9) —, grava `MALHA_REPROCESSO` na corrida antiga e a
        do dia 04 não é tocada. O desenho não passa por cima do próprio índice
        único;
      • a corrida em questão está ABERTA → não há o que reabrir; o aviso diz
        que a reexecução ENTRA nela e que o relógio de fechamento não reinicia
        (Decisão 65).

    Nunca levanta: o clear JÁ aconteceu no Airflow. Falha vira aviso.
    """
    from routers.malhas import _evento_da_corrida
    if not mc.tabela_085_presente(cur):
        return
    corridas = mc.corridas_das_linhas(cur, [oficial, *alvos], data_ref)
    for c in corridas:
        try:
            operavel, motivo_portao = _corrida_operavel(cur, c["malha_name"])
            if not operavel:
                log.info("[RERUN] ciclo da malha '%s' não operado pela API "
                         "(%s) — o rerun segue como antes da F8",
                         c["malha_name"], motivo_portao)
                continue
            if c["status"] == mc.STATUS_ABERTA:
                # Decisão 65: o botão só existe com a frase do efeito. Aqui ela
                # é dita depois porque o gesto já aconteceu — a prévia diz antes.
                saida["avisos"].append(_frase_da_corrida(
                    c, "está em andamento: esta reexecução é contada nela, e o "
                       "relógio de fechamento do ciclo NÃO reinicia por este "
                       "gesto"))
                continue
            detalhe = (f"reexecucao de {oficial} em "
                       f"{_iso_data(data_ref)} por {usuario}")
            if mc.reabrir_corrida(cur, c["id"], f"rerun:{usuario}", detalhe):
                recarregada = mc.corrida(cur, c["id"]) or c
                saida["corridas_reabertas"].append({
                    "malha": c["malha_name"],
                    "data_referencia": _iso_data(c["data_referencia"]),
                    "tentativas": recarregada.get("tentativas"),
                })
                saida["avisos"].append(_frase_da_corrida(
                    c, f"voltou a ABERTA (tentativa "
                       f"{recarregada.get('tentativas')}) — ela fecha de novo "
                       "quando o reprocesso terminar"))
                log.info("[RERUN] corrida #%s da malha '%s' reaberta por %s",
                         c["id"], c["malha_name"], usuario)
                continue
            # Não reabriu. As duas causas têm conserto e leitura DIFERENTES, e
            # por isso a mensagem não pode ser uma só: "há outro ciclo em voo" é
            # temporário e esperado; "este ciclo é fim de linha" é definitivo.
            outra = mc.corrida_aberta(cur, c["malha_name"])
            if outra is not None and int(outra["id"]) != int(c["id"]):
                porque = ("há outro ciclo desta malha em andamento (o de "
                          + _iso_data(outra["data_referencia"]) +
                          ") — o reprocesso roda, mas fora do ciclo antigo")
            else:
                porque = (f"o ciclo foi encerrado como {c['status']} e não "
                          "volta — o reprocesso roda fora dele")
            _evento_da_corrida(cur, c, "MALHA_REPROCESSO",
                               f"{detalhe}: corrida NAO reaberta ({porque})")
            saida["corridas_com_reprocesso"].append({
                "malha": c["malha_name"],
                "data_referencia": _iso_data(c["data_referencia"]),
                "status": c["status"],
            })
            saida["avisos"].append(_frase_da_corrida(c, "NÃO foi reaberta: "
                                                    + porque))
        except Exception as e:  # noqa: BLE001 — o clear já aconteceu
            log.warning("[RERUN] efeito na corrida da malha '%s' não aplicado: "
                        "%s", c.get("malha_name"), e)
            saida["avisos"].append(
                f"o ciclo da malha '{c.get('malha_name')}' não pôde ser "
                f"atualizado por este reprocesso ({e}) — confira a tela da "
                f"malha")


def _iso_data(v) -> str:
    return v.strftime("%Y-%m-%d") if hasattr(v, "strftime") else str(v)


# A frase da prévia NUNCA pode prometer mais do que `_efeito_na_corrida` faz —
# e ele faz menos do que a leitura ingênua sugere, por DUAS razões que a prévia
# tem de conhecer:
#
#   1. o portão do §11.1. Com o interruptor em `0` (o estado de hoje), com a
#      085 ausente, com o `dags/` deployado sem a capacidade ou com a guardiã
#      sem heartbeat, o efeito é PULADO em silêncio — e o modal ficaria dizendo
#      "este ciclo volta a ficar ABERTO" para um gesto que não toca em corrida
#      nenhuma. É a mesma régua de "sem certeza, sem frase" que já governa o
#      `None`: a certeza aqui inclui poder operar;
#   2. a CASCATA. `_efeito_na_corrida` só roda dentro de `if cascata:` e com
#      `marcar_substituidas` tendo aposentado alguma corrida (`n > 0`) — e a
#      opção que nasce marcada no modal é "apenas este pipeline". Sem a segunda
#      frase, a promessa da reabertura apareceria justamente na opção em que ela
#      nunca acontece.
#
# Por isso a prévia devolve DUAS leituras do mesmo ciclo, e quem escolhe é a
# tela, que é quem sabe qual opção está marcada. As frases moram aqui (e não no
# front) pelo motivo de sempre: duas grafias do mesmo efeito fariam o operador
# achar que são dois efeitos.
def _previa_da_corrida(cur, oficial: str, data_ref) -> dict | None:
    """A frase da Decisão 65, dita ANTES do clique: em que ciclo esta
    reexecução cai, e o que acontece com ele — em CADA uma das duas opções.

    `None` quando não há corrida nenhuma (pipeline fora de malha, banco sem a
    085, leitura indisponível) **ou quando a API não pode operar a corrida**
    (§11.1) — e aí o modal fica como era antes desta fase, que é a degradação
    certa: sem certeza, sem frase."""
    try:
        if not mc.tabela_085_presente(cur):
            return None
        corridas = mc.corridas_das_linhas(cur, [oficial], data_ref)
        if not corridas:
            return None
        c = corridas[0]
        operavel, motivo_portao = _corrida_operavel(cur, c["malha_name"])
        if not operavel:
            log.info("[RERUN] prévia do ciclo da malha '%s' omitida (%s) — o "
                     "rerun não vai tocar na corrida, e a tela não promete",
                     c["malha_name"], motivo_portao)
            return None
        if c["status"] == mc.STATUS_ABERTA:
            # A linha reexecutada já é deste ciclo (`reviver_corrida` preserva o
            # `malha_execucao_id`), então a leitura é a MESMA com e sem cascata.
            efeito = ("em_andamento", "esta reexecução entra neste ciclo, que "
                      "está em andamento; o relógio de fechamento não reinicia "
                      "por este gesto")
            sem_cascata = efeito
        elif c["status"] in mc.REABREM and \
                mc.corrida_aberta(cur, c["malha_name"]) is None:
            efeito = ("reabre", "este ciclo já encerrado volta a ficar ABERTO e "
                      "fecha de novo quando o reprocesso terminar")
            sem_cascata = ("nao_toca", "este ciclo já encerrado NÃO volta a "
                           "abrir por este gesto — só a reexecução COM os "
                           "dependentes o reabre; sozinha, ela roda fora dele")
        else:
            efeito = ("fora_do_ciclo", "este ciclo NÃO volta a abrir — o "
                      "reprocesso roda fora dele, e fica registrado nele")
            sem_cascata = ("nao_toca", "este ciclo NÃO volta a abrir, e sem os "
                           "dependentes o reprocesso nem fica registrado nele")
        return {"malha": c["malha_name"],
                "data_referencia": _iso_data(c["data_referencia"]),
                "status": c["status"], "efeito": efeito[0],
                "mensagem": efeito[1],
                # ADITIVAS: front antigo lê só `mensagem` e continua desenhando
                # a frase da cascata — que era o comportamento desta fase.
                "efeito_sem_cascata": sem_cascata[0],
                "mensagem_sem_cascata": sem_cascata[1]}
    except Exception as e:  # noqa: BLE001 — prévia degrada, nunca derruba
        log.warning("[RERUN] prévia do ciclo de '%s' indisponível: %s",
                    oficial, e)
        return None


def _previa_afetados(oficial: str, data_ref) -> dict:
    """Bloco `cascata` da prévia — quem é atingido em CADA opção (decisão 1)."""
    conn = cur = None
    corrida_previa = None
    try:
        conn = get_db_conn(); cur = conn.cursor()
        if not deps_svc.tabela_067(cur):
            return {"disponivel": False, "razao": "migration_067_pendente",
                    "dependentes": [], "com_corrida": [], "sem_corrida": [],
                    "corridas": {}, "truncado": False}
        info = rerun_svc.afetados(cur, oficial, data_ref)
        corrida_previa = _previa_da_corrida(cur, oficial, data_ref)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        log.warning("[RERUN] previa de afetados de '%s' falhou: %s", oficial, e)
        # (a razão fica "erro_na_consulta" — o modal já a traduz)
        return {"disponivel": False, "razao": "erro_na_consulta",
                "dependentes": [], "com_corrida": [], "sem_corrida": [],
                "corridas": {}, "truncado": False}
    finally:
        for f in (getattr(cur, "close", None), getattr(conn, "close", None)):
            try:
                f and f()
            except Exception:
                pass
    corridas = {
        k: [{**c, "inicio": _fmt_dt(c.get("inicio")), "fim": _fmt_dt(c.get("fim")),
             "substituida_em": _fmt_dt(c.get("substituida_em"))} for c in v]
        for k, v in (info.get("corridas") or {}).items()
    }
    return {
        "disponivel": not info.get("cascata_indisponivel"),
        # A razão vem do serviço: são TRÊS motivos possíveis (banco sem a 078,
        # dags/ deployado que não entende o carimbo, e capacidade do dags/
        # desconhecida) e cada um tem conserto diferente. Fixar a string aqui
        # foi o que fez a API dizer "migration 078 pendente" para um ambiente
        # com a 078 aplicada e o dags/ velho.
        "razao": info.get("razao_indisponivel"),
        "dependentes": info.get("dependentes") or [],
        "com_corrida": info.get("com_corrida") or [],
        "sem_corrida": info.get("sem_corrida") or [],
        "corridas": corridas,
        "truncado": bool(info.get("truncado")),
        # ADITIVO (F8): `None` quando o pipeline não é membro de ciclo nenhum,
        # ou quando o banco/interruptor não permitem responder com certeza.
        # Front antigo ignora a chave; front novo só desenha a frase quando ela
        # existe — "sem certeza, sem frase" (Decisão 65).
        "corrida": corrida_previa,
    }


@router.get("/pipelines/{pipeline_name}/corrida", tags=["execucoes"])
def corrida_do_pipeline(pipeline_name: str,
                        data_referencia: str | None = None,
                        _auth: dict = Depends(get_current_user)):
    """O ciclo de malha em que um disparo AVULSO deste pipeline vai cair
    (§6.9/#5) — a frase que o modal de "Executar agora" diz **antes**.

    Disparo avulso **nunca abre e nunca reabre** corrida. O que ele faz é
    ADERIR: o degrau 3 do §7 faz o pipeline herdar o ODATE do ciclo em voo, e a
    linha nasce contada nele. Sem esta frase, o operador dispara "só este
    pipeline" às 3h e o número da malha muda sozinho na tela ao lado — ou, pior,
    ele dispara para OUTRA data e a execução fica fora do ciclo sem que nada
    diga isso.

    Três respostas possíveis, e cada uma tem uma consequência diferente:

      • `conta` — há ciclo aberto e a data bate: a execução será contada nele;
      • `fora_do_ciclo` — o ODATE pedido é outro: **não** vincula, e a execução
        fica fora do ciclo (Decisão 23 exige o ODATE nos dois ramos);
      • `ambiguo` — o pipeline é membro de DUAS corridas abertas com ODATEs
        diferentes: a execução será **recusada** com data divergente
        (Decisão 34 — dois ODATEs nunca viram escolha).

    `corrida: null` é a resposta normal de pipeline fora de malha, de banco sem
    a 085 e de leitura indisponível: o modal fica como era antes desta fase.
    Leitura pura, sem escrita nenhuma — por isso `get_current_user` basta.

    ⚠️ **O interruptor decide as TRÊS frases, não só a primeira.** Quem faz o
    disparo avulso aderir ao ciclo é `mc.odate()`, e a primeira linha dele é
    `if not corrida_ativa(cur): return vazio`. Com o interruptor em `0` (o
    estado de hoje) a execução NÃO é contada, NÃO fica "fora do ciclo" e — o
    pior dos três — NÃO é recusada por data divergente: ela roda como antes da
    spec, calculando a própria data. Anunciar uma recusa que não vai acontecer
    é a única das três frases que faz o operador desistir de um disparo
    legítimo às 3h, então o portão vem antes de todas elas.
    """
    pipeline = (pipeline_name or "").strip()
    vazio = {"corrida": None, "efeito": None, "mensagem": None}
    if not pipeline:
        return vazio
    conn = cur = None
    try:
        conn = get_db_conn(); cur = conn.cursor()
        if not mc.tabela_085_presente(cur) or not mc.corrida_ativa(cur):
            return vazio
        info = mc.corrida_aberta_do_pipeline(cur, pipeline)
        abertas = info.get("corridas") or []
        if not abertas:
            return vazio
        c = abertas[0]
        rotulo = _iso_data(c["data_referencia"])
        if info.get("ambiguo"):
            malhas = ", ".join(sorted({str(x["malha_name"]) for x in abertas}))
            return {
                "corrida": {"malha": c["malha_name"],
                            "data_referencia": rotulo, "status": c["status"]},
                "efeito": "ambiguo",
                "mensagem": (f"Este pipeline é membro de ciclos em andamento "
                             f"com datas de referência DIFERENTES ({malhas}). "
                             f"Um disparo agora será recusado por data "
                             f"divergente — encerre ou aguarde um dos ciclos "
                             f"antes de disparar."),
            }
        pedida = (data_referencia or "").strip()
        if pedida and pedida != rotulo:
            return {
                "corrida": {"malha": c["malha_name"],
                            "data_referencia": rotulo, "status": c["status"]},
                "efeito": "fora_do_ciclo",
                "mensagem": (f"A malha '{c['malha_name']}' tem um ciclo em "
                             f"andamento na data {rotulo}. Como esta execução "
                             f"pede a data {pedida}, ela ficará FORA desse "
                             f"ciclo — não conta para o fechamento dele."),
            }
        return {
            "corrida": {"malha": c["malha_name"], "data_referencia": rotulo,
                        "status": c["status"]},
            "efeito": "conta",
            "mensagem": (f"Este pipeline é membro da malha "
                         f"'{c['malha_name']}', que tem um ciclo em andamento "
                         f"na data {rotulo}. Esta execução será CONTADA nesse "
                         f"ciclo — ela não abre um ciclo novo."),
        }
    except Exception as e:  # noqa: BLE001 — leitura degrada larga
        log.warning("[MALHA] ciclo aberto de '%s' indisponível: %s", pipeline, e)
        return vazio
    finally:
        for f in (getattr(cur, "close", None), getattr(conn, "close", None)):
            try:
                f and f()
            except Exception:
                pass


@router.get("/pipelines/{pipeline_name}/rerun/previa", tags=["execucoes"])
async def previa_rerun(
    pipeline_name: str,
    task_id: str,
    data_referencia: str | None = None,
    execution_id: str | None = None,
    run_id: str | None = None,
    _auth: dict = Depends(require_perm(PERM_EXECUTAR)),
):
    """O que o modal de confirmação da F4 mostra ANTES de reexecutar.

    Decisão 1 do §7 — "sempre perguntar, mostrando quais pipelines seriam
    afetados em cada caso". Esta rota devolve os dois lados do dilema:

      • `etapas` — as etapas DESTE pipeline que serão reexecutadas. **Não é
        estimativa**: é o `dry_run: true` do próprio `clearTaskInstances`, com
        o MESMO corpo do clear de verdade (`rerun.corpo_clear`). Um modal que
        promete N e um clear que limpa M seria a mentira mais fácil desta fase.
      • `cascata` — o fecho a jusante, separado entre quem RODOU no ODATE
        (`com_corrida`: será reaberto e roda de novo) e quem NÃO rodou
        (`sem_corrida`: não há corrida a reabrir).

    Exige `PERM_EXECUTAR` como o gesto: a prévia revela a topologia de execução
    e é o primeiro passo do mesmo ato.
    """
    task_id = (task_id or "").strip()
    if not task_id:
        raise HTTPException(status_code=422, detail="task_id é obrigatório")

    oficial, ident, data_ref = await _resolve_alvo_rerun(
        pipeline_name,
        exec_id=(execution_id or "").strip(),
        dag_run_id=(run_id or "").strip(),
        data_referencia=(data_referencia or "").strip())

    dag_run_id = ident.get("dag_run_id") or ident.get("run_id")
    etapas_info = {"etapas": [], "tasks_de_apoio": 0, "total_tasks": 0}
    airflow_indisponivel = False
    # None = não deu para perguntar; o modal só avisa no True (ver _dag_pausada).
    dag_pausada = None
    if not dag_run_id:
        airflow_indisponivel = True
    elif not _DAG_ID_RE.match(oficial or ""):
        airflow_indisponivel = True
    else:
        try:
            async with get_airflow_client() as client:
                dag_pausada = await _dag_pausada(client, oficial)
                tarefas = rerun_svc.task_ids_do_clear(
                    task_id, await _tasks_da_dag(client, oficial))
                r = await client.post(
                    f"/api/v1/dags/{oficial}/clearTaskInstances",
                    json=rerun_svc.corpo_clear(dag_run_id, task_id, dry_run=True,
                                               task_ids=tarefas))
            if r.is_success:
                conn = cur = None
                try:
                    conn = get_db_conn(); cur = conn.cursor()
                    desenho = ident_svc.etapas_do_desenho(cur, oficial)
                finally:
                    for f in (getattr(cur, "close", None),
                              getattr(conn, "close", None)):
                        try:
                            f and f()
                        except Exception:
                            pass
                etapas_info = rerun_svc.etapas_do_clear(
                    r.json().get("task_instances", []), desenho)
            else:
                airflow_indisponivel = True
                log.warning("[RERUN] dry_run de %s devolveu %s — %s",
                            oficial, r.status_code, r.text[:200])
        except Exception as e:  # noqa: BLE001 — prévia degrada, nunca derruba
            airflow_indisponivel = True
            log.warning("[RERUN] dry_run de %s falhou: %s", oficial, e)

    return {
        "pipeline_name": oficial,
        "task_id": task_id,
        "data_referencia": (data_ref.strftime("%Y-%m-%d")
                            if hasattr(data_ref, "strftime") else data_ref),
        "identidade": _ident_json(ident),
        "dag_run_id": dag_run_id,
        "airflow_indisponivel": airflow_indisponivel,
        # O gesto RECUSA com 409 quando a DAG está pausada; a prévia diz isso
        # antes, para o modal não oferecer um botão que só pode dar erro.
        "dag_pausada": dag_pausada,
        **etapas_info,
        "cascata": _previa_afetados(oficial, data_ref) if data_ref else {
            "disponivel": False, "razao": "sem_data_referencia",
            "dependentes": [], "com_corrida": [], "sem_corrida": [],
            "corridas": {}, "truncado": False},
    }


def _aplicar_cascata(oficial: str, data_ref, task_id: str, dag_run_id: str,
                     usuario: str, cascata: bool, tasks_limpas: int) -> dict:
    """Reabertura dos dependentes + auditoria — DEPOIS de o Airflow aceitar o
    clear. A ordem importa: auditar/reabrir antes e o clear falhar deixaria
    corridas aposentadas sem reprocesso nenhum a caminho.

    Também carimba o PRÓPRIO pipeline como EXECUTANDO na 067. Ele está mesmo
    executando de novo — e enquanto a linha dele disser SUCESSO um push de
    outro pai (ou a guardiã) pode liberar um dependente com o dado velho, que
    é justamente o que a decisão 1 proíbe. O `publish_dataset` reescreve para
    SUCESSO ao concluir e o caminho de falha grava FALHA, então a marca não
    fica pendurada.

    ⚠️ E o MESMO UPDATE **ressuscita** a corrida (`substituida_em`/
    `substituida_por` = NULL): reexecutar uma corrida que um rerun anterior
    aposentou produzia SUCESSO carimbado — invisível para `liberado()` e para
    `pipelines_todos_sucesso()`, bloqueando todo dependente do dia sem nada na
    tela. Ver `rerun.reviver_corrida`.

    ⚠️ O `rowcount` desse UPDATE é CONFERIDO. Ele passava em silêncio: com um
    `execution_id` que não casasse (corrida fora da 067, grafia divergente,
    linha apagada à mão), a marca simplesmente não acontecia — e é ela que
    protege o filho direto. Zero linha agora vira aviso na resposta e log, no
    mesmo idioma do resto: o gesto aconteceu, o alcance foi menor, e isso é
    dito. E as demais corridas vivas do pipeline no ODATE são aposentadas
    (`aposentar_irmas`) — sem isso um SUCESSO irmão sobrevivente libera o
    dependente sozinho.

    Nada aqui levanta: o clear JÁ aconteceu. Falhas viram log e o campo
    `avisos` da resposta.
    """
    saida = {"corridas_substituidas": 0, "dependentes_reabertos": [],
             "corridas_irmas_aposentadas": 0, "auditado": False, "avisos": [],
             # F8 — o efeito sobre o CICLO da malha. Listas (e não um objeto):
             # o pipeline pode ser membro de N malhas (§6.9/#6), e o gesto pode
             # reabrir um ciclo e apenas registrar reprocesso em outro.
             "corridas_reabertas": [], "corridas_com_reprocesso": []}
    conn = cur = None
    try:
        conn = get_db_conn(); cur = conn.cursor()
        if data_ref is not None and deps_svc.tabela_067(cur):
            try:
                # `reviver_corrida` (e não um UPDATE inline): além de marcar
                # EXECUTANDO, ela LIMPA `substituida_em`/`substituida_por` da
                # corrida reexecutada — reexecutar uma corrida já aposentada
                # produzia um SUCESSO invisível para sempre (defeito
                # documentado na função).
                if rerun_svc.reviver_corrida(cur, oficial, data_ref,
                                             dag_run_id) < 1:
                    log.warning("[RERUN] corrida de '%s' em %s (run_id=%s) NAO "
                                "marcada como EXECUTANDO: nenhuma linha casou",
                                oficial, data_ref, dag_run_id)
                    saida["avisos"].append(
                        "a corrida deste pipeline não pôde ser marcada como em "
                        "execução (nenhuma linha com este identificador de "
                        "corrida na data) — dependentes podem partir com o dado "
                        "anterior enquanto o reprocesso roda")
            except Exception as e:  # noqa: BLE001
                saida["avisos"].append(f"corrida do pipeline não marcada como EXECUTANDO: {e}")
            try:
                irmas = rerun_svc.aposentar_irmas(cur, oficial, data_ref,
                                                  dag_run_id, usuario)
                saida["corridas_irmas_aposentadas"] = irmas
                if irmas:
                    log.info("[RERUN] %d corrida(s) irma(s) de '%s' em %s "
                             "aposentada(s)", irmas, oficial, data_ref)
                    saida["avisos"].append(
                        f"{irmas} outra(s) corrida(s) deste pipeline nesta data "
                        "foram aposentadas — só a reexecutada vale a partir de "
                        "agora")
            except Exception as e:  # noqa: BLE001
                saida["avisos"].append(
                    f"outras corridas do pipeline na data não aposentadas: {e}")
            if cascata:
                info = rerun_svc.afetados(cur, oficial, data_ref)
                alvos = info.get("com_corrida") or []
                n = rerun_svc.marcar_substituidas(cur, alvos, data_ref, usuario)
                saida["corridas_substituidas"] = n
                # ⚠️ `dependentes_reabertos` só lista o que foi REABERTO DE FATO.
                # Encontrado na prova do fallback (dev, 2026-08-03): com a
                # migration 078 ausente a lista vinha cheia e
                # `corridas_substituidas` vinha 0 — a resposta dizia
                # "2 dependentes reabertos" e o aviso dizia que nenhum rodaria
                # de novo. O toast do front conta esta lista; ele anunciaria
                # uma cascata que não aconteceu.
                saida["dependentes_reabertos"] = alvos if n > 0 else []
                # F8 §6.9/#3 — o CICLO da malha, na MESMA transação do carimbo.
                # O gatilho é `rowcount > 0`: sem corrida aposentada não houve
                # reprocesso a jusante, e reabrir um ciclo por um gesto que não
                # vai fazer nada rodar de novo o deixaria aberto até o teto,
                # bloqueando o disparo da malha por nada.
                if n > 0:
                    _efeito_na_corrida(cur, oficial, alvos, data_ref, usuario,
                                       saida)
                if info.get("cascata_indisponivel"):
                    saida["avisos"].append(
                        AVISO_CASCATA_INDISPONIVEL.get(
                            info.get("razao_indisponivel"),
                            "cascata indisponível neste ambiente — nenhuma corrida "
                            "pôde ser reaberta; os dependentes NÃO vão rodar de novo"))
                if info.get("truncado"):
                    saida["avisos"].append(
                        "fecho de dependentes truncado no teto de segurança — "
                        "pode haver pipeline a jusante não reaberto")
        elif cascata:
            saida["avisos"].append(
                "migration 067 pendente (ou data de referência desconhecida) — "
                "cascata indisponível")
        saida["auditado"] = rerun_svc.registrar_auditoria(
            cur, oficial, usuario,
            {"dag_run_id": dag_run_id,
             "data_referencia": (data_ref.strftime("%Y-%m-%d")
                                 if hasattr(data_ref, "strftime") else data_ref),
             "task_id": task_id, "cascata": cascata,
             "dependentes_reabertos": saida["dependentes_reabertos"],
             "corridas_substituidas": saida["corridas_substituidas"],
             "tasks_limpas": tasks_limpas})
        conn.commit()
    except Exception as e:  # noqa: BLE001 — o clear já aconteceu; nunca levantar
        log.warning("[RERUN] pós-clear de '%s' falhou: %s", oficial, e)
        saida["avisos"].append(f"pós-clear parcial: {e}")
        try:
            conn and conn.rollback()
        except Exception:
            pass
    finally:
        for f in (getattr(cur, "close", None), getattr(conn, "close", None)):
            try:
                f and f()
            except Exception:
                pass
    return saida


@router.post("/execucoes/rerun", tags=["execucoes"])
async def rerun_from_task(body: dict = Body(default={}),
                          auth: dict = Depends(require_perm(PERM_EXECUTAR))):
    """Limpa tasks a partir de um job específico e reexecuta o DAG.

    Body:
      pipeline_name    — nome do pipeline (= dag_id no Airflow)
      task_id          — task_id a partir da qual reexecutar (inclusive, com downstream)
      execution_id     — ts_nodash da execução (caminho histórico: Logs/Dashboard)
      dag_run_id       — dag_run_id real (opcional; a corrida escolhida à mão)
      data_referencia  — ODATE (F4: a linguagem da malha; exige identidade exata)
      cascata          — F4/decisão 1: reabre os dependentes para rodarem de novo
                         no MESMO ODATE. **Default False** — nunca em silêncio.

    ⚠️ **`cascata` não tem default "verdadeiro" nem heurística.** A decisão 1
    do §7 é "SEMPRE PERGUNTAR": quem chama já perguntou, e a resposta vem no
    corpo. Sem o campo, o comportamento é o de antes desta fase (só este
    pipeline) — que também é uma resposta legítima, só não é uma escolha
    silenciosa da API.

    ⚠️ **Não exige FALHA.** Retomar de uma etapa `SUCCESS` é legítimo: o
    operador corrigiu o dado de origem e quer refazer dali para frente (§4).
    """
    pipeline   = (body.get("pipeline_name") or "").strip()
    exec_id    = (body.get("execution_id")  or "").strip()
    task_id    = (body.get("task_id")       or "").strip()
    dag_run_id = (body.get("dag_run_id")    or "").strip()
    data_ref_s = (body.get("data_referencia") or "").strip()
    cascata    = bool(body.get("cascata"))

    if not pipeline or not task_id:
        raise HTTPException(status_code=422, detail="pipeline_name e task_id são obrigatórios")

    dag_id = pipeline  # no Airflow o dag_id = pipeline_name exato
    oficial, data_ref = pipeline, None

    # A resolução com recusa (modo estrito) só entra quando o chamador NÃO deu
    # uma corrida concreta. Com `execution_id` ou `dag_run_id` na mão o caminho
    # segue o histórico, byte a byte — Logs e Dashboard não mudam de
    # comportamento por causa desta fase.
    if cascata or data_ref_s or not (exec_id or dag_run_id):
        oficial, ident, data_ref = await _resolve_alvo_rerun(
            pipeline, exec_id=exec_id, dag_run_id=dag_run_id,
            data_referencia=data_ref_s)
        dag_id = oficial
        dag_run_id = dag_run_id or ident.get("dag_run_id") or ident.get("run_id") or ""
        if not dag_run_id:
            raise HTTPException(
                status_code=409,
                detail={"erro": "corrida_sem_dag_run",
                        "mensagem": ("Não foi possível identificar o dag_run "
                                     "desta corrida no Airflow — sem ele o clear "
                                     "atingiria todas as corridas da DAG.")})

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

        # 1.5. DAG pausada: RECUSA antes de mexer em qualquer coisa. O clear
        # seria aceito, o run voltaria para QUEUED e nada rodaria — e a corrida
        # ficaria EXECUTANDO travando os dependentes. Recusar é honesto e o
        # conserto é de um clique ("Ativar" na tela do pipeline). Só recusa
        # quando a resposta é um SIM: não saber não bloqueia (ver _dag_pausada).
        if await _dag_pausada(client, dag_id) is True:
            raise HTTPException(
                status_code=409,
                detail={"erro": "dag_pausada",
                        "mensagem": (f"O pipeline '{dag_id}' está PAUSADO no "
                                     "Airflow. Reexecutar agora limparia as "
                                     "tarefas sem nada rodar, e a corrida "
                                     "ficaria presa em execução bloqueando os "
                                     "dependentes. Ative o pipeline e "
                                     "reexecute.")})

        # 2. Limpar a task e downstream via clearTaskInstances — SEMPRE com o
        # dag_run_id: sem ele o Airflow limpa a task em TODOS os dag_runs da DAG
        # (e reset_dag_runs re-enfileira todos) — reprocessamento em massa.
        # O corpo vem de rerun.corpo_clear, o MESMO que a prévia usou com
        # dry_run: o que o modal prometeu é o que é executado. As tasks saem de
        # `task_ids_do_clear`, que acrescenta o marcador de início da etapa —
        # ver o defeito documentado lá (sem ele a etapa retomada mantinha o
        # start_time antigo e a tentativa nunca era contada).
        tarefas = rerun_svc.task_ids_do_clear(
            task_id, await _tasks_da_dag(client, dag_id))
        clear_body = rerun_svc.corpo_clear(dag_run_id, task_id, task_ids=tarefas)
        r2 = await client.post(
            f"/api/v1/dags/{dag_id}/clearTaskInstances",
            json=clear_body,
        )
        if not r2.is_success:
            raise HTTPException(status_code=502,
                detail=f"Airflow clearTaskInstances falhou: {r2.status_code} — {r2.text[:300]}")

        cleared = r2.json()
        tasks_limpas = len(cleared.get("task_instances", []))
        log.info("Rerun %s/%s a partir de %s — %s tasks limpas (cascata=%s)",
                 dag_id, dag_run_id, task_id, tasks_limpas, cascata)

    # 3. Reabertura dos dependentes (só com cascata) + auditoria. Fora do
    # `async with`: nenhuma conexão de banco é aberta enquanto o cliente HTTP
    # do Airflow está vivo.
    # `matricula` é o mesmo campo que finalizacao.py e pipelines.py gravam em
    # etl_pipeline_audit.changed_by — a auditoria do rerun entra na MESMA
    # coluna, com o MESMO vocabulário, e aparece no histórico do pipeline que
    # a tela de infra já lê.
    usuario = str((auth or {}).get("matricula") or "?")
    pos = _aplicar_cascata(oficial, data_ref, task_id, dag_run_id, usuario,
                           cascata, tasks_limpas)

    return {
        "ok": True,
        "pipeline_name": pipeline,
        "dag_id": dag_id,
        "dag_run_id": dag_run_id,
        "task_id": task_id,
        "tasks_cleared": tasks_limpas,
        "cascata": cascata,
        "dependentes_reabertos": pos["dependentes_reabertos"],
        "corridas_substituidas": pos["corridas_substituidas"],
        "corridas_irmas_aposentadas": pos["corridas_irmas_aposentadas"],
        "auditado": pos["auditado"],
        "avisos": pos["avisos"],
    }


async def _dag_pausada(client, dag_id: str):
    """A DAG está PAUSADA no Airflow? ``True``/``False``, ou ``None`` quando
    não deu para perguntar (Airflow fora, 404, resposta sem o campo).

    ⚠️ **DEFEITO CORRIGIDO: rerun em DAG pausada deixava a corrida pendurada.**
    Com a DAG pausada, o ``clearTaskInstances`` com ``reset_dag_runs`` devolve
    200 e re-enfileira o dag_run — que fica QUEUED **para sempre**, porque o
    scheduler não agenda DAG pausada. O gesto respondia "ok, 8 tarefas limpas",
    a corrida ficava EXECUTANDO (a marca do pós-clear) e **todo dependente
    parava atrás dela** — a classe do "órfão em RUNNING" já registrada no
    projeto, agora criada pelo próprio botão.

    ``None`` NÃO bloqueia: o gesto histórico (Logs/Dashboard) não pode ficar
    refém de uma pergunta a mais ao Airflow. Bloqueia só o que sabemos ser
    pausado.
    """
    try:
        r = await client.get(f"/api/v1/dags/{dag_id}")
        if not r.is_success:
            log.warning("[RERUN] estado de pausa de %s devolveu %s",
                        dag_id, r.status_code)
            return None
        valor = r.json().get("is_paused")
        return bool(valor) if valor is not None else None
    except Exception as e:  # noqa: BLE001
        log.warning("[RERUN] estado de pausa de %s indisponivel: %s", dag_id, e)
        return None


async def _tasks_da_dag(client, dag_id: str) -> list:
    """Lista de ``task_id`` da DAG — best-effort, ``[]`` em qualquer falha.

    Só serve a ``rerun.task_ids_do_clear`` (decidir se o ``log_start_<etapa>``
    existe). Lista vazia degrada para o comportamento histórico do clear em vez
    de derrubar o gesto: é melhor reexecutar como antes do que não reexecutar.
    """
    try:
        r = await client.get(f"/api/v1/dags/{dag_id}/tasks")
        if not r.is_success:
            log.warning("[RERUN] lista de tasks de %s devolveu %s", dag_id, r.status_code)
            return []
        return [str(t.get("task_id") or "") for t in r.json().get("tasks", [])]
    except Exception as e:  # noqa: BLE001
        log.warning("[RERUN] lista de tasks de %s indisponivel: %s", dag_id, e)
        return []


# ═══════════════════ F5 — etapa em espera (pausa de runtime) ═════════════════
#
# A tabela de pausas (migration 079) é o ESTADO; o portão que a obedece vive na
# DAG (dags/utils/espera.py, chamado pelo log_start de toda etapa). Aqui ficam
# os gestos: pedir, liberar, cancelar e listar — todos com PERM_EXECUTAR e
# auditoria em etl_pipeline_audit, no mesmo padrão da F4.
#
# ⚠️ Nenhum destes gestos republica DAG. É a decisão arquitetural do preâmbulo
# da spec: "a DAG é a planta, não o estado".

def _pausa_json(p: dict) -> dict:
    """Uma pausa pronta para JSON — datas no formato do resto da API."""
    d = p.get("data_referencia")
    return {
        **p,
        "data_referencia": (d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else d),
        "solicitado_em": _fmt_dt(p.get("solicitado_em")),
        "aguardando_desde": _fmt_dt(p.get("aguardando_desde")),
        "ultima_verificacao": _fmt_dt(p.get("ultima_verificacao")),
        "resolvido_em": _fmt_dt(p.get("resolvido_em")),
        "alertado_em": _fmt_dt(p.get("alertado_em")),
    }


def _pausas_da_execucao(pipeline: str, execution_id: str) -> list:
    """Lista as pausas de uma corrida — `[]` em qualquer indisponibilidade.

    Usada pelo endpoint próprio E embutida no payload do drill-down: o canvas
    precisa pintar "em espera" no mesmo ciclo em que pinta o status, sem uma
    segunda ida ao servidor a cada refetch.
    """
    if not execution_id:
        return []
    conn = cur = None
    try:
        conn = get_db_conn(); cur = conn.cursor()
        return [_pausa_json(p) for p in espera_svc.listar(cur, pipeline, execution_id)]
    except Exception as e:  # noqa: BLE001 — a tela nunca quebra por causa disto
        log.warning("[ESPERA] pausas de '%s/%s' indisponiveis: %s",
                    pipeline, execution_id, e)
        return []
    finally:
        for f in (getattr(cur, "close", None), getattr(conn, "close", None)):
            try:
                f and f()
            except Exception:
                pass


@router.post("/execucoes/pausas", tags=["execucoes"])
async def criar_pausa(body: dict = Body(default={}),
                      auth: dict = Depends(require_perm(PERM_EXECUTAR))):
    """Marca uma etapa que **ainda não iniciou** para parar e aguardar liberação.

    Body:
      pipeline_name    — nome do pipeline (= dag_id)
      job_name         — a etapa (aceita `task_id` como sinônimo)
      execution_id     — ts_nodash da corrida (caminho direto do drill-down)
      dag_run_id       — a corrida escolhida à mão (ambiguidade da F3)
      data_referencia  — ODATE; exige identidade exata (modo estrito)
      motivo           — texto livre do operador (opcional, mas recomendado)
      teto_minutos     — teto desta pausa; ausente usa `espera_teto_minutos`

    ⚠️ **O limite honesto do §5, verificado e não só explicado**: etapa que já
    tem linha em `etl_job_execution` nesta corrida já passou pelo portão. A
    resposta é 409 com a lista das etapas que ainda dá para pausar — nunca uma
    pausa que o operador acha que vai valer e não vale.
    """
    pipeline   = (body.get("pipeline_name") or "").strip()
    job_pedido = (body.get("job_name") or body.get("task_id") or "").strip()
    exec_id    = (body.get("execution_id") or "").strip()
    dag_run_id = (body.get("dag_run_id") or "").strip()
    data_ref_s = (body.get("data_referencia") or "").strip()
    motivo     = (body.get("motivo") or "").strip()[:1000] or None

    if not pipeline or not job_pedido:
        raise HTTPException(status_code=422,
                            detail="pipeline_name e job_name são obrigatórios")

    oficial, ident, data_ref = await _resolve_alvo_rerun(
        pipeline, exec_id=exec_id, dag_run_id=dag_run_id,
        data_referencia=data_ref_s, gesto="pausar")
    execution_id = str(ident.get("ts_nodash") or "").strip()
    if not execution_id:
        raise HTTPException(
            status_code=409,
            detail={"erro": "corrida_sem_execution_id",
                    "mensagem": ("Não foi possível identificar o execution_id "
                                 "(ts_nodash) desta corrida — sem ele o portão "
                                 "da etapa não tem como reconhecer a pausa.")})
    # O que vale contra o Airflow é o dag_run_id; guardá-lo agora é o que
    # permite CANCELAR a execução depois sem re-resolver identidade.
    run_airflow = (ident.get("dag_run_id") or ident.get("run_id") or "") or None
    # ODATE: pausar segundos depois de disparar a corrida pega a janela em que
    # o check_agenda ainda não gravou a linha da 067 — a identidade resolve o
    # run e não a data. Sem este resgate a pausa nasce sem ODATE e os eventos
    # dela não entram no painel (medido na prova viva).
    if data_ref is None:
        data_ref = espera_svc.data_do_execution_id(execution_id)

    conn = cur = None
    try:
        conn = get_db_conn(); cur = conn.cursor()
        if not espera_svc.tem_tabela(cur):
            raise HTTPException(
                status_code=409,
                detail={"erro": "migration_079_pendente",
                        "mensagem": ("A tabela de pausas (migration 079) ainda "
                                     "não foi aplicada neste ambiente.")})
        desenho = ident_svc.etapas_do_desenho(cur, oficial)
        nomes = {str(n.get("job_name") or "").strip().casefold():
                 str(n.get("job_name") or "").strip() for n in desenho}
        job_name = nomes.get(job_pedido.casefold())
        if not job_name:
            raise HTTPException(
                status_code=404,
                detail=f"Etapa '{job_pedido}' não existe no desenho de '{oficial}'")
        # ⚠️ **A DAG PUBLICADA tem portão?** O banco ter a 079 não basta: o
        # portão é emitido DENTRO do fonte gerado de cada DAG, e só existe
        # depois de o pipeline ser republicado (`force_all`). Sem esta
        # checagem a pausa nascia 200/OK em pipeline que passa direto — a
        # mentira mais cara desta fase. Ver `espera.estado_portao`.
        #
        # DECISÃO (registrada): **sem portão a pausa NÃO é criada.** O
        # caminho "criar com aviso forte" foi avaliado e recusado — uma pausa
        # que não segura nada fica PENDENTE para sempre, ninguém a libera
        # (não há o que liberar), e ela ainda vira ruído no canvas e no
        # histórico de auditoria. A regra da casa é não mostrar como garantido
        # o que não está; aqui o honesto é recusar e dizer o conserto, que é
        # de um clique ("gerar DAG novamente").
        #
        # DESCONHECIDO (fonte ilegível: mount ausente, permissão) NÃO recusa —
        # ele CRIA com aviso forte na resposta e na tela. Recusar por não
        # conseguir ler um arquivo tiraria a feature inteira de ambientes que
        # nunca serão provados errados; e o dano de uma pausa que não segura é
        # exatamente o que o aviso desfaz. É o único ponto em que este gesto
        # se afasta do `rerun` (lá o desconhecido bloqueia a cascata) — porque
        # lá o gesto principal sobrevive à recusa, e aqui ele é o gesto.
        portao = espera_svc.estado_portao(cur, oficial)
        if portao == espera_svc.PORTAO_AUSENTE:
            raise HTTPException(
                status_code=409,
                detail={"erro": espera_svc.PORTAO_AUSENTE,
                        "mensagem": espera_svc.MENSAGEM_PORTAO[portao],
                        "pipeline_name": oficial})
        iniciadas = espera_svc.etapas_iniciadas(cur, oficial, execution_id)
        if job_name.casefold() in iniciadas:
            raise HTTPException(
                status_code=409,
                detail={
                    "erro": "etapa_ja_iniciou",
                    "mensagem": (f"A etapa '{job_name}' já iniciou nesta "
                                 "execução — o portão dela ficou para trás. Só "
                                 "dá para pausar etapa que ainda não começou; "
                                 "escolha uma etapa seguinte."),
                    "etapas_pausaveis": [n["job_name"] for n in desenho
                                         if str(n.get("job_name") or "").strip().casefold()
                                         not in iniciadas],
                })
        teto = espera_svc.normaliza_teto(body.get("teto_minutos"),
                                         espera_svc.teto_padrao(cur))
        usuario = str((auth or {}).get("matricula") or "?")
        pausa_id = espera_svc.criar(
            cur, pipeline=oficial, execution_id=execution_id, job_name=job_name,
            task_id=job_name, run_id=run_airflow, data_ref=data_ref,
            motivo=motivo, teto=teto, usuario=usuario)
        ja_existia = pausa_id == 0
        if ja_existia:
            atual = [p for p in espera_svc.listar(cur, oficial, execution_id)
                     if p["job_name"].casefold() == job_name.casefold()
                     and p["estado"] == "PENDENTE"]
            pausa_id = atual[0]["id"] if atual else 0
        else:
            espera_svc.registrar_auditoria(
                cur, oficial, usuario, "pausar",
                {"execution_id": execution_id, "run_id": run_airflow,
                 "data_referencia": (data_ref.strftime("%Y-%m-%d")
                                     if hasattr(data_ref, "strftime") else data_ref),
                 "job_name": job_name, "pausa_id": pausa_id,
                 "motivo": motivo, "teto_minutos": teto})
        avisos = espera_svc.avisos_da_pausa(cur, oficial, teto)
        if portao == espera_svc.PORTAO_DESCONHECIDO:
            avisos.insert(0, espera_svc.MENSAGEM_PORTAO[portao])
        conn.commit()
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Erro DB: {e}")
    finally:
        for f in (getattr(cur, "close", None), getattr(conn, "close", None)):
            try:
                f and f()
            except Exception:
                pass

    return {"ok": True, "pausa_id": pausa_id, "ja_existia": ja_existia,
            "pipeline_name": oficial, "job_name": job_name,
            "execution_id": execution_id, "teto_minutos": teto,
            "portao": portao, "avisos": avisos,
            "pausas": _pausas_da_execucao(oficial, execution_id)}


def _pausa_alvo(cur, pausa_id: int) -> dict:
    """A pausa do gesto, ou 404/409 — a checagem comum de liberar e cancelar."""
    if not espera_svc.tem_tabela(cur):
        raise HTTPException(
            status_code=409,
            detail={"erro": "migration_079_pendente",
                    "mensagem": "A tabela de pausas (migration 079) não existe."})
    pausa = espera_svc.por_id(cur, pausa_id)
    if pausa is None:
        raise HTTPException(status_code=404, detail=f"Pausa {pausa_id} não encontrada")
    if pausa["estado"] != "PENDENTE":
        raise HTTPException(
            status_code=409,
            detail={"erro": "pausa_ja_resolvida",
                    "estado": pausa["estado"],
                    "mensagem": (f"Esta pausa já está {pausa['estado'].lower()}"
                                 + (f" (por {pausa['resolvido_por']})"
                                    if pausa.get("resolvido_por") else "") + ".")})
    return pausa


@router.post("/execucoes/pausas/{pausa_id}/liberar", tags=["execucoes"])
def liberar_pausa(pausa_id: int, body: dict = Body(default={}),
                  auth: dict = Depends(require_perm(PERM_EXECUTAR))):
    """Libera a etapa: na próxima verificação do portão (até 1 min por padrão)
    a execução segue dali para frente.

    Não toca no Airflow: a task está em `up_for_reschedule` e volta sozinha —
    é justamente o que o modo `reschedule` compra. Mudar a linha é tudo.
    """
    obs = (body.get("observacao") or "").strip()[:1000] or None
    usuario = str((auth or {}).get("matricula") or "?")
    conn = cur = None
    try:
        conn = get_db_conn(); cur = conn.cursor()
        pausa = _pausa_alvo(cur, pausa_id)
        if not espera_svc.resolver(cur, pausa_id, "LIBERADA", usuario, obs):
            atual = espera_svc.por_id(cur, pausa_id) or {}
            raise HTTPException(
                status_code=409,
                detail={"erro": "pausa_ja_resolvida",
                        "estado": atual.get("estado"),
                        "mensagem": ("A pausa mudou de estado entre a leitura e "
                                     "a liberação (o teto pode ter estourado no "
                                     "mesmo instante).")})
        espera_svc.gravar_evento(
            cur, pausa["pipeline_name"],
            pausa.get("data_referencia")
            or espera_svc.data_do_execution_id(pausa["execution_id"]),
            espera_svc.EVENTO_LIBERADA,
            f"Etapa '{pausa['job_name']}' liberada por {usuario}"
            + (f": {obs}" if obs else ""))
        espera_svc.registrar_auditoria(
            cur, pausa["pipeline_name"], usuario, "liberar",
            {"execution_id": pausa["execution_id"], "run_id": pausa.get("run_id"),
             "data_referencia": (pausa["data_referencia"].strftime("%Y-%m-%d")
                                 if hasattr(pausa.get("data_referencia"), "strftime")
                                 else pausa.get("data_referencia")),
             "job_name": pausa["job_name"], "pausa_id": pausa_id,
             "observacao": obs})
        conn.commit()
        pipeline, execution_id = pausa["pipeline_name"], pausa["execution_id"]
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Erro DB: {e}")
    finally:
        for f in (getattr(cur, "close", None), getattr(conn, "close", None)):
            try:
                f and f()
            except Exception:
                pass
    return {"ok": True, "pausa_id": pausa_id, "estado": "LIBERADA",
            "pipeline_name": pipeline, "execution_id": execution_id,
            "pausas": _pausas_da_execucao(pipeline, execution_id)}


@router.post("/execucoes/pausas/{pausa_id}/cancelar", tags=["execucoes"])
async def cancelar_pausa(pausa_id: int, body: dict = Body(default={}),
                         auth: dict = Depends(require_perm(PERM_EXECUTAR))):
    """Desiste da corrida em vez de liberar: **falha o DagRun no Airflow** e só
    então marca a pausa como CANCELADA.

    ⚠️ **A ordem é a garantia.** Se o Airflow recusar, a resposta é 502 e a
    pausa continua PENDENTE — a etapa segue segura no portão. O contrário
    (marcar CANCELADA primeiro) abriria o portão para uma execução que ninguém
    cancelou de fato, porque o portão faz UMA pergunta só: "existe pausa
    pendente?".

    O DagRun fica FALHA, nunca "sucesso com etapas puladas": pipeline abortado
    pela metade não pode aparecer verde — a lição do sucesso falso que este
    projeto já pagou.
    """
    obs = (body.get("observacao") or "").strip()[:1000] or None
    usuario = str((auth or {}).get("matricula") or "?")
    conn = cur = None
    try:
        conn = get_db_conn(); cur = conn.cursor()
        pausa = _pausa_alvo(cur, pausa_id)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Erro DB: {e}")
    finally:
        for f in (getattr(cur, "close", None), getattr(conn, "close", None)):
            try:
                f and f()
            except Exception:
                pass

    dag_id = pausa["pipeline_name"]
    dag_run_id = (pausa.get("run_id") or "").strip()
    if not dag_run_id or not _DAG_ID_RE.match(dag_id or ""):
        raise HTTPException(
            status_code=409,
            detail={"erro": "corrida_sem_dag_run",
                    "mensagem": ("Esta pausa não guarda o dag_run da corrida — "
                                 "sem ele não dá para cancelar a execução no "
                                 "Airflow. Libere a pausa e pare a corrida pela "
                                 "tela do Airflow.")})
    async with get_airflow_client() as client:
        r = await client.patch(f"/api/v1/dags/{dag_id}/dagRuns/{dag_run_id}",
                               json={"state": "failed"})
    if not r.is_success:
        raise HTTPException(
            status_code=502,
            detail=(f"Airflow recusou cancelar a corrida: {r.status_code} — "
                    f"{r.text[:300]}. A pausa continua pendente e a etapa "
                    "segue segura."))

    fechou = False
    conn = cur = None
    try:
        conn = get_db_conn(); cur = conn.cursor()
        # A corrida JÁ foi falhada no Airflow: daqui para frente nada pode
        # levantar a ponto de deixar a linha pendente sem registro — mas se
        # levantar, o pior caso é uma pausa PENDENTE de uma corrida morta, que
        # não solta nada e aparece na tela para o operador cancelar de novo.
        espera_svc.resolver(cur, pausa_id, "CANCELADA", usuario, obs)
        # Quem cancela é quem FECHA: o PATCH do Airflow pula o `registrar_falha`
        # (ONE_FAILED), e sem isto a corrida ficaria EXECUTANDO para sempre —
        # o "órfão em RUNNING" que este projeto já pagou uma vez.
        fechou = espera_svc.fechar_corrida_cancelada(
            cur, pausa["pipeline_name"], dag_run_id, usuario)
        espera_svc.gravar_evento(
            cur, pausa["pipeline_name"],
            pausa.get("data_referencia")
            or espera_svc.data_do_execution_id(pausa["execution_id"]),
            espera_svc.EVENTO_CANCELADA,
            f"Execução cancelada por {usuario} na etapa '{pausa['job_name']}'"
            + (f": {obs}" if obs else ""))
        espera_svc.registrar_auditoria(
            cur, pausa["pipeline_name"], usuario, "cancelar",
            {"execution_id": pausa["execution_id"], "run_id": dag_run_id,
             "data_referencia": (pausa["data_referencia"].strftime("%Y-%m-%d")
                                 if hasattr(pausa.get("data_referencia"), "strftime")
                                 else pausa.get("data_referencia")),
             "job_name": pausa["job_name"], "pausa_id": pausa_id,
             "observacao": obs, "dagrun_falhado": True})
        conn.commit()
    except Exception as e:  # noqa: BLE001
        log.warning("[ESPERA] cancelamento da pausa %s: corrida falhada no "
                    "Airflow mas o registro falhou: %s", pausa_id, e)
    finally:
        for f in (getattr(cur, "close", None), getattr(conn, "close", None)):
            try:
                f and f()
            except Exception:
                pass

    return {"ok": True, "pausa_id": pausa_id, "estado": "CANCELADA",
            "pipeline_name": pausa["pipeline_name"], "dag_run_id": dag_run_id,
            "execution_id": pausa["execution_id"],
            "corrida_fechada": fechou,
            "pausas": _pausas_da_execucao(pausa["pipeline_name"],
                                          pausa["execution_id"])}


@router.get("/pipelines/{pipeline_name}/pausas", tags=["execucoes"])
def listar_pausas(pipeline_name: str,
                  data_referencia: str | None = None,
                  execution_id: str | None = None,
                  run_id: str | None = None,
                  _auth: dict = Depends(get_current_user)):
    """As pausas de UMA corrida — pendentes e resolvidas, em ordem de criação.

    Mesmas três portas de `GET /pipelines/{p}/execucao` (ODATE, ts_nodash ou
    run_id), pelo mesmo serviço de identidade da F2. Leitura: exige login, não
    `PERM_EXECUTAR` — quem só olha precisa enxergar que o processo está parado
    e por quê.
    """
    if sum(1 for v in (data_referencia, execution_id, run_id) if v) > 1:
        raise HTTPException(
            status_code=422,
            detail="Informe data_referencia OU execution_id OU run_id, "
                   "nunca mais de um")
    conn = cur = None
    try:
        conn = get_db_conn(); cur = conn.cursor()
        oficial = ident_svc.pipeline_oficial(cur, pipeline_name)
        if oficial is None:
            raise HTTPException(status_code=404,
                                detail=f"Pipeline não encontrado: '{pipeline_name}'")
        ts = (execution_id or "").strip()
        if not ts:
            virada = deps_svc.virada_global(cur)
            if run_id:
                ident = ident_svc.resolve_por_run_id(cur, oficial, run_id.strip())
            else:
                if data_referencia:
                    try:
                        data_ref = datetime.strptime(
                            str(data_referencia).strip(), "%Y-%m-%d").date()
                    except ValueError:
                        raise HTTPException(
                            status_code=422,
                            detail=f"data_referencia inválida: '{data_referencia}'")
                else:
                    data_ref = dref.calcular(datetime.now(), virada)
                ident = ident_svc.resolve_por_odate(cur, oficial, data_ref,
                                                    virada=virada)
            ts = str(ident.get("ts_nodash") or "").strip()
        pausas = ([_pausa_json(p) for p in espera_svc.listar(cur, oficial, ts)]
                  if ts else [])
        tem_079 = espera_svc.tem_tabela(cur)
        portao = espera_svc.estado_portao(cur, oficial)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Erro DB: {e}")
    finally:
        for f in (getattr(cur, "close", None), getattr(conn, "close", None)):
            try:
                f and f()
            except Exception:
                pass
    return {"pipeline_name": oficial, "execution_id": ts or None,
            "pausas": pausas, "total": len(pausas),
            "migration_079_pendente": not tem_079,
            # As DUAS metades do deploy da F5: banco (079) e DAG publicada
            # (portão). Dizer só a primeira foi o defeito.
            "portao": portao}


def _ident_json(ident: dict) -> dict:
    """Identidade pronta para JSON — datas viram texto no formato do resto da
    API (`_fmt_dt` / `YYYY-MM-DD`). Nenhuma chave é omitida: o consumidor lê
    sempre o mesmo molde, resolvido ou não."""
    out = dict(ident)
    dref_val = out.get("data_referencia")
    out["data_referencia"] = (dref_val.strftime("%Y-%m-%d")
                              if hasattr(dref_val, "strftime") else dref_val)
    out["candidatos"] = [
        {**c, "inicio": _fmt_dt(c.get("inicio")), "fim": _fmt_dt(c.get("fim")),
         # A corrida APOSENTADA por um rerun com cascata não pode aparecer no
         # aviso de ambiguidade com a mesma cara da corrida viva — a tela a
         # rotula por este campo.
         "substituida_em": _fmt_dt(c.get("substituida_em"))}
        for c in (out.get("candidatos") or [])
    ]
    return out


@router.get("/pipelines/{pipeline_name}/execucao", tags=["execucoes"])
async def get_pipeline_execucao(
    pipeline_name: str,
    data_referencia: str | None = None,
    execution_id: str | None = None,
    run_id: str | None = None,
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
      • `run_id=<run_id do Airflow>` — a corrida ESPECÍFICA. Aditivo da F3:
        quando o ODATE tem mais de uma corrida a resposta volta
        `identidade.ambiguo=true` com `candidatos[]`, e a tela precisa
        conseguir abrir uma candidata que NÃO é a vencedora. Pelo ts_nodash
        não dá: os run_ids gerados pelo Orquestra não são traduzíveis pela
        string (a armadilha do §2), então só o próprio run_id serve de chave.
        Reusa `resolve_por_run_id` da F2 — nenhuma regra nova.

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
    if sum(1 for v in (data_referencia, execution_id, run_id) if v) > 1:
        raise HTTPException(
            status_code=422,
            detail="Informe data_referencia OU execution_id OU run_id, "
                   "nunca mais de um")
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
    run_pedido = (run_id or "").strip()

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
        if run_pedido:
            ident = ident_svc.resolve_por_run_id(cur, oficial, run_pedido)
        elif ts_pedido:
            ident = ident_svc.resolve_por_ts_nodash(cur, oficial, ts_pedido)
        else:
            if data_ref is None:
                data_ref = dref.calcular(datetime.now(), virada)
            ident = ident_svc.resolve_por_odate(cur, oficial, data_ref,
                                                virada=virada)
        desenho = ident_svc.etapas_do_desenho(cur, oficial)
        # F5 — a DAG PUBLICADA deste pipeline obedece a pausa? O canvas precisa
        # saber ANTES do clique: oferecer "Pausar aqui" num pipeline sem portão
        # e só recusar no POST seria fazer o operador descobrir pela recusa.
        # Custo: um `os.stat` (o conteúdo é cacheado por mtime+tamanho).
        portao = espera_svc.estado_portao(cur, oficial)
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
    anteriores = []
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
            # F4: as tentativas SUPERADAS desta execução (migration 078). Sem a
            # tabela devolve [] e o payload é o da F3 — deploy parcial degrada.
            anteriores = ident_svc.tentativas_anteriores(
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
        {**e,
         "inicio": _fmt_dt(e.get("inicio")), "fim": _fmt_dt(e.get("fim")),
         "tentativas": [{**t, "inicio": _fmt_dt(t.get("inicio")),
                         "fim": _fmt_dt(t.get("fim"))}
                        for t in (e.get("tentativas") or [])]}
        for e in ident_svc.compor_etapas(desenho, executadas, anteriores)
    ]

    # A corrida do pipeline é a candidata VENCEDORA da identidade — não uma
    # segunda consulta com uma segunda regra de "mais recente" (D14/D15).
    corrida = None
    for c in (ident.get("candidatos") or []):
        if c.get("run_id") and c["run_id"] == ident.get("run_id"):
            corrida = {**c, "inicio": _fmt_dt(c.get("inicio")),
                       "fim": _fmt_dt(c.get("fim")),
                       "substituida_em": _fmt_dt(c.get("substituida_em"))}
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
    # F5 — as pausas desta corrida viajam JUNTO com as etapas. O canvas precisa
    # pintar "em espera" no MESMO ciclo em que pinta o status (e ele refaz esta
    # chamada a cada 30s); uma segunda rota só para isso dobraria o tráfego do
    # modo Execução e abriria janela para as duas leituras discordarem.
    # Sem a 079 a lista vem vazia — o payload é o da F4 e a tela não muda.
    pausas = _pausas_da_execucao(oficial, ident.get("ts_nodash") or "")
    return {
        "pipeline_name": oficial,
        # Pelo ODATE, é o pedido; pelo execution_id, é o que a 067 revelou (pode
        # ser null quando a corrida não está registrada — vazio honesto).
        "data_referencia": (data_ref.strftime("%Y-%m-%d") if data_ref
                            else ident_json["data_referencia"]),
        "identidade": ident_json,
        "corrida": corrida,
        "etapas": etapas,
        "pausas": pausas,
        # 'ok' | 'dag_sem_portao' | 'portao_desconhecido' — o que a tela usa
        # para não oferecer (ou para avisar antes de oferecer) a pausa.
        "portao": portao,
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
