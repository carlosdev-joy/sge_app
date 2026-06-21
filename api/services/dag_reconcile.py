"""api/services/dag_reconcile.py — reconciliador do despause/notificação do Gerar-DAG.

Quando o usuário gera/regenera uma DAG, a intenção (despausar quando a DAG
aparecer no Airflow + notificar quem disparou) é PERSISTIDA em dbo.etl_dag_pendente.
Um loop em segundo plano — iniciado no lifespan da API — varre a fila e conclui
cada item de forma idempotente.

Como a intenção mora no banco, um restart da API no meio da janela não perde
nada: ao subir, o loop relê a fila e retoma de onde parou. Substitui o antigo
BackgroundTask in-process, que sumia se a API reiniciasse.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re

import httpx

from db import get_db_conn
from deps import AIRFLOW_URL, AIRFLOW_USER, AIRFLOW_PASSWORD
from services.notify import add_notificacao

log = logging.getLogger("orquestra-api")

_DAG_ID_RE = re.compile(r"^[A-Za-z0-9_.\-]+$")
RECONCILE_INTERVAL_S = int(os.getenv("DAG_RECONCILE_INTERVAL_S", "10"))
PENDENTE_TIMEOUT_S   = int(os.getenv("DAG_PENDENTE_TIMEOUT_S", "900"))  # 15 min


# ── fila (DB síncrono) ──────────────────────────────────────────────────────

def enqueue(pipeline_name: str, desired_paused: bool, matricula: str | None) -> None:
    """Registra a intenção de ativar/notificar uma DAG recém-gerada (best-effort)."""
    if not pipeline_name:
        return
    try:
        conn = get_db_conn(); cur = conn.cursor()
        # Mantém só um pendente ativo por pipeline: supersede os anteriores.
        cur.execute(
            "UPDATE dbo.etl_dag_pendente SET status='superseded', atualizado_em=GETDATE() "
            "WHERE pipeline_name=? AND status='pendente'", (pipeline_name,))
        cur.execute(
            "INSERT INTO dbo.etl_dag_pendente (pipeline_name, desired_paused, matricula) "
            "VALUES (?, ?, ?)",
            (pipeline_name[:200], 1 if desired_paused else 0,
             (str(matricula)[:64] if matricula else None)))
        conn.commit(); cur.close(); conn.close()
    except Exception as e:
        log.warning("[DAG-RECONCILE] enqueue falhou p/ %s: %s", pipeline_name, e)


def _fetch_pendentes() -> list[dict]:
    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute(
            "SELECT id, pipeline_name, desired_paused, matricula, "
            "       DATEDIFF(SECOND, criado_em, GETDATE()) "
            "FROM dbo.etl_dag_pendente WHERE status='pendente' ORDER BY criado_em")
        rows = [{"id": r[0], "pipeline_name": r[1], "desired_paused": bool(r[2]),
                 "matricula": r[3], "idade_s": int(r[4] or 0)} for r in cur.fetchall()]
        cur.close(); conn.close()
        return rows
    except Exception as e:
        log.debug("[DAG-RECONCILE] fetch pendentes: %s", e)
        return []


def _set_status(pendente_id: int, status: str) -> None:
    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute(
            "UPDATE dbo.etl_dag_pendente "
            "SET status=?, atualizado_em=GETDATE(), "
            "    concluido_em=CASE WHEN ? IN ('concluido','timeout') THEN GETDATE() ELSE concluido_em END "
            "WHERE id=? AND status='pendente'", (status, status, pendente_id))
        conn.commit(); cur.close(); conn.close()
    except Exception as e:
        log.warning("[DAG-RECONCILE] set_status %s=%s: %s", pendente_id, status, e)


def _bump(pendente_id: int) -> None:
    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute("UPDATE dbo.etl_dag_pendente SET tentativas=tentativas+1, atualizado_em=GETDATE() "
                    "WHERE id=?", (pendente_id,))
        conn.commit(); cur.close(); conn.close()
    except Exception:
        pass


def _finalize(row: dict, found: bool) -> None:
    """Grava a notificação + atualiza o status. Rodado em thread (DB síncrono)."""
    name = row["pipeline_name"]; mat = row["matricula"]; desired_paused = row["desired_paused"]
    if found:
        add_notificacao(
            mat, f"DAG de {name} pronta no Airflow",
            ("A DAG foi gerada e está pausada (pipeline inativo)."
             if desired_paused else
             "A DAG foi gerada e já está ativa para execução."),
            "success", "/pipelines")
        _set_status(row["id"], "concluido")
    elif row["idade_s"] >= PENDENTE_TIMEOUT_S:
        add_notificacao(
            mat, f"DAG de {name} ainda registrando",
            "A DAG foi criada no servidor, mas o Airflow ainda não a disponibilizou. "
            "Recarregue a lista de pipelines em alguns minutos.",
            "warning", "/pipelines")
        _set_status(row["id"], "timeout")
    else:
        _bump(row["id"])


# ── loop de reconciliação (async) ───────────────────────────────────────────

async def _process_one(client: httpx.AsyncClient, row: dict) -> None:
    name = row["pipeline_name"]
    if not _DAG_ID_RE.match(name or ""):
        await asyncio.to_thread(_set_status, row["id"], "timeout")
        return
    found = False
    try:
        g = await client.get(f"/api/v1/dags/{name}")
        if g.is_success:
            cur_paused = bool(g.json().get("is_paused", True))
            if cur_paused != row["desired_paused"]:
                p = await client.patch(
                    f"/api/v1/dags/{name}",
                    json={"is_paused": row["desired_paused"]},
                    headers={"Content-Type": "application/json"})
                if p.is_success:
                    # Não declara sucesso pelo retorno do PATCH: re-lê o estado real
                    # no Airflow e só conclui quando is_paused == desejado (ativa).
                    g2 = await client.get(f"/api/v1/dags/{name}")
                    if g2.is_success and bool(g2.json().get("is_paused", True)) == row["desired_paused"]:
                        found = True
                        log.info("[DAG-RECONCILE] %s confirmada is_paused=%s", name, row["desired_paused"])
                # patch falhou ou estado ainda não bateu → tenta de novo no próximo tick
            else:
                found = True  # já no estado desejado, confirmado pelo GET
    except Exception as e:
        log.debug("[DAG-RECONCILE] poll %s: %s", name, e)
        found = False
    await asyncio.to_thread(_finalize, row, found)


async def reconcile_once() -> None:
    rows = await asyncio.to_thread(_fetch_pendentes)
    if not rows:
        return
    async with httpx.AsyncClient(
        base_url=AIRFLOW_URL, auth=(AIRFLOW_USER, AIRFLOW_PASSWORD), timeout=15
    ) as client:
        for row in rows:
            await _process_one(client, row)


async def reconcile_loop() -> None:
    """Loop perene — iniciado no lifespan da API e cancelado no shutdown."""
    log.info("[DAG-RECONCILE] loop iniciado (intervalo=%ds, timeout=%ds)",
             RECONCILE_INTERVAL_S, PENDENTE_TIMEOUT_S)
    while True:
        try:
            await reconcile_once()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.warning("[DAG-RECONCILE] tick falhou: %s", e)
        await asyncio.sleep(RECONCILE_INTERVAL_S)
