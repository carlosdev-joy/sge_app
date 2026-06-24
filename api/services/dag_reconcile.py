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
import json
import logging
import os
import re

import httpx

from db import get_db_conn
from deps import AIRFLOW_URL, AIRFLOW_USER, AIRFLOW_PASSWORD
from services.notify import add_notificacao

log = logging.getLogger("orquestra-api")

_DAG_ID_RE = re.compile(r"^[A-Za-z0-9_.\-]+$")
_IMPORT_ERR_MAX = 12000  # corta o stack_trace (cabe em NVARCHAR(MAX)/JSON sem estourar)
RECONCILE_INTERVAL_S = int(os.getenv("DAG_RECONCILE_INTERVAL_S", "10"))
PENDENTE_TIMEOUT_S   = int(os.getenv("DAG_PENDENTE_TIMEOUT_S", "900"))  # 15 min
GERADA_TIMEOUT_S     = int(os.getenv("DAG_GERADA_TIMEOUT_S", str(PENDENTE_TIMEOUT_S)))


# ── import errors do Airflow ────────────────────────────────────────────────
# A factory valida o .py com ast.parse, mas isso só pega erro de SINTAXE. Erros
# em tempo de carga (NameError, import quebrado, etc.) só aparecem quando o
# scheduler do Airflow tenta importar o arquivo: ele mantém a versão antiga da
# DAG ATIVA, porém com has_import_errors=true. Logo "DAG existe + despausada" não
# é garantia de DAG executável. Antes de declarar SUCCESS consultamos
# GET /api/v1/importErrors e, se houver trace p/ {pipeline}.py, tratamos como FALHA.

def _match_import_error(payload: dict | None, pipeline: str) -> str | None:
    """Extrai do JSON de /api/v1/importErrors o stack_trace do arquivo
    {pipeline}.py, ou None. Best-effort: qualquer formato inesperado → None.
    Matching por filename (o Airflow devolve o caminho absoluto do arquivo)."""
    if not payload or not pipeline:
        return None
    try:
        suf_unix = "/" + pipeline + ".py"
        suf_win  = "\\" + pipeline + ".py"
        for ie in (payload.get("import_errors") or []):
            fn = (ie.get("filename") or "")
            if fn.endswith(suf_unix) or fn.endswith(suf_win) or fn == pipeline + ".py":
                trace = ie.get("stack_trace") or ie.get("stacktrace") or ""
                trace = str(trace).strip()
                if trace:
                    return trace[:_IMPORT_ERR_MAX]
                return "Erro de importação no Airflow (sem stack trace disponível)."
    except Exception as e:
        log.debug("[DAG-RECONCILE] parse importErrors p/ %s: %s", pipeline, e)
    return None


async def _import_error_async(client: httpx.AsyncClient, pipeline: str) -> str | None:
    """Variante async (caminho _process_one). Rede/parse falhou → None."""
    if not pipeline:
        return None
    try:
        r = await client.get("/api/v1/importErrors", params={"limit": 100})
        if r.is_success:
            return _match_import_error(r.json(), pipeline)
    except Exception as e:
        log.debug("[DAG-RECONCILE] importErrors async %s: %s", pipeline, e)
    return None


def _import_error_sync(client: httpx.Client, pipeline: str) -> str | None:
    """Variante síncrona (caminho recheck_geradas). Rede/parse falhou → None."""
    if not pipeline:
        return None
    try:
        r = client.get("/api/v1/importErrors", params={"limit": 100})
        if r.is_success:
            return _match_import_error(r.json(), pipeline)
    except Exception as e:
        log.debug("[DAG-RECONCILE] importErrors sync %s: %s", pipeline, e)
    return None


# ── fila (DB síncrono) ──────────────────────────────────────────────────────

def enqueue(pipeline_name: str, desired_paused: bool, matricula: str | None,
            dag_run_id: str | None = None) -> None:
    """Registra a intenção de ativar/notificar uma DAG recém-gerada (best-effort).
    `dag_run_id` liga o pendente ao run da factory (etl_factory_log)."""
    if not pipeline_name:
        return
    try:
        conn = get_db_conn(); cur = conn.cursor()
        # Mantém só um pendente ativo por pipeline: supersede os anteriores.
        cur.execute(
            "UPDATE dbo.etl_dag_pendente SET status='superseded', atualizado_em=GETDATE() "
            "WHERE pipeline_name=? AND status='pendente'", (pipeline_name,))
        cur.execute(
            "INSERT INTO dbo.etl_dag_pendente (pipeline_name, desired_paused, matricula, dag_run_id) "
            "VALUES (?, ?, ?, ?)",
            (pipeline_name[:200], 1 if desired_paused else 0,
             (str(matricula)[:64] if matricula else None),
             (str(dag_run_id)[:200] if dag_run_id else None)))
        conn.commit(); cur.close(); conn.close()
    except Exception as e:
        log.warning("[DAG-RECONCILE] enqueue falhou p/ %s: %s", pipeline_name, e)


def _fetch_pendentes() -> list[dict]:
    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute(
            "SELECT id, pipeline_name, desired_paused, matricula, "
            "       DATEDIFF(SECOND, criado_em, GETDATE()), dag_run_id "
            "FROM dbo.etl_dag_pendente WHERE status='pendente' ORDER BY criado_em")
        rows = [{"id": r[0], "pipeline_name": r[1], "desired_paused": bool(r[2]),
                 "matricula": r[3], "idade_s": int(r[4] or 0), "dag_run_id": r[5]}
                for r in cur.fetchall()]
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
            "    concluido_em=CASE WHEN ? IN ('concluido','timeout','erro') THEN GETDATE() ELSE concluido_em END "
            "WHERE id=? AND status='pendente'", (status, status, pendente_id))
        conn.commit(); cur.close(); conn.close()
    except Exception as e:
        log.warning("[DAG-RECONCILE] set_status %s=%s: %s", pendente_id, status, e)


def _update_factory_log(dag_run_id: str | None, estado: str,
                        step_tipo: str | None = None, step_msg: str | None = None,
                        trace: str | None = None) -> None:
    """Vira o registro da factory (GERADA → SUCCESS/TIMEOUT/ERRO) ao concluir a
    ativação e anexa um passo no detalhes_json (linha no log do run). Só altera
    quem está em 'GERADA' — não mexe em SUCCESS/FAILED de outros fluxos.

    `trace`: quando presente (import error), grava um step extra
    {"tipo":"import_error","msg":<stack_trace>}, adiciona o trace à lista `erros`
    do detalhes_json e incrementa a coluna `erros` (contador), para o
    /factory/runs sinalizar a falha."""
    if not dag_run_id:
        return
    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute(
            "SELECT detalhes_json FROM dbo.etl_factory_log WHERE dag_run_id=? AND estado='GERADA'",
            (dag_run_id,))
        row = cur.fetchone()
        if not row:
            cur.close(); conn.close(); return  # já finalizado ou outro fluxo
        if step_msg or trace:
            try:
                d = json.loads(row[0]) if row[0] else {}
            except Exception:
                d = {}
            d.setdefault("erros", d.get("erros", []))
            d.setdefault("steps", [])
            if step_msg:
                d["steps"].append({"tipo": step_tipo or "info", "msg": step_msg})
            if trace:
                d["steps"].append({"tipo": "import_error", "msg": trace})
                if trace not in d["erros"]:
                    d["erros"].append(trace)
            if trace:
                cur.execute(
                    "UPDATE dbo.etl_factory_log "
                    "SET estado=?, finalizado_em=GETDATE(), detalhes_json=?, erros=erros+1 "
                    "WHERE dag_run_id=? AND estado='GERADA'",
                    (estado, json.dumps(d, ensure_ascii=False), dag_run_id))
            else:
                cur.execute(
                    "UPDATE dbo.etl_factory_log SET estado=?, finalizado_em=GETDATE(), detalhes_json=? "
                    "WHERE dag_run_id=? AND estado='GERADA'",
                    (estado, json.dumps(d, ensure_ascii=False), dag_run_id))
        else:
            cur.execute(
                "UPDATE dbo.etl_factory_log SET estado=?, finalizado_em=GETDATE() "
                "WHERE dag_run_id=? AND estado='GERADA'", (estado, dag_run_id))
        conn.commit(); cur.close(); conn.close()
    except Exception as e:
        log.debug("[DAG-RECONCILE] factory_log %s=%s: %s", dag_run_id, estado, e)


def _bump(pendente_id: int) -> None:
    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute("UPDATE dbo.etl_dag_pendente SET tentativas=tentativas+1, atualizado_em=GETDATE() "
                    "WHERE id=?", (pendente_id,))
        conn.commit(); cur.close(); conn.close()
    except Exception:
        pass


def _finalize(row: dict, found: bool, import_trace: str | None = None) -> None:
    """Grava a notificação + atualiza o status. Rodado em thread (DB síncrono).

    `import_trace`: se presente, a DAG existe no Airflow MAS tem erro de
    importação — NÃO é sucesso. Registra FALHA (estado ERRO + step import_error +
    trace) e notifica com severidade 'error'."""
    name = row["pipeline_name"]; mat = row["matricula"]; desired_paused = row["desired_paused"]
    if found and import_trace:
        add_notificacao(
            mat, f"DAG de {name} com erro de importação",
            "A DAG foi gerada mas o Airflow não conseguiu importá-la — ela NÃO pode "
            "ser executada. Veja o stack trace na tela de Publicação e corrija o fluxo.",
            "error", "/publicacao")
        _set_status(row["id"], "erro")
        _update_factory_log(row.get("dag_run_id"), "ERRO", "import_error",
                            "DAG com erro de importação no Airflow — não executável.",
                            trace=import_trace)
        log.warning("[DAG-RECONCILE] %s ATIVA porém com import error no Airflow", name)
    elif found:
        add_notificacao(
            mat, f"DAG de {name} pronta no Airflow",
            ("A DAG foi gerada e está pausada (pipeline inativo)."
             if desired_paused else
             "A DAG foi gerada e já está ativa para execução."),
            "success", "/pipelines")
        _set_status(row["id"], "concluido")
        _update_factory_log(row.get("dag_run_id"), "SUCCESS", "ativada",
                            "DAG criada e ativada no Airflow — pronta para execução.")
    elif row["idade_s"] >= PENDENTE_TIMEOUT_S:
        add_notificacao(
            mat, f"DAG de {name} ainda registrando",
            "A DAG foi criada no servidor, mas o Airflow ainda não a disponibilizou. "
            "Recarregue a lista de pipelines em alguns minutos.",
            "warning", "/pipelines")
        _set_status(row["id"], "timeout")
        _update_factory_log(row.get("dag_run_id"), "TIMEOUT", "timeout",
                            "A DAG foi gerada, mas não ficou ativa no Airflow no tempo limite.")
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
    # Antes de declarar SUCCESS: a DAG pode existir/estar ativa mas com erro de
    # importação (Airflow mantém a versão antiga ativa + has_import_errors). Nesse
    # caso o arquivo {name}.py aparece em /api/v1/importErrors — vira FALHA.
    import_trace = None
    if found:
        import_trace = await _import_error_async(client, name)
    await asyncio.to_thread(_finalize, row, found, import_trace)


async def reconcile_once() -> None:
    rows = await asyncio.to_thread(_fetch_pendentes)
    if not rows:
        return
    async with httpx.AsyncClient(
        base_url=AIRFLOW_URL, auth=(AIRFLOW_USER, AIRFLOW_PASSWORD), timeout=15
    ) as client:
        for row in rows:
            await _process_one(client, row)


def recheck_geradas() -> None:
    """Revalida (síncrono, best-effort) os runs da factory em 'GERADA' — chamado
    ao abrir a tela de regeneração. Vira SUCCESS se a DAG já está no estado
    desejado no Airflow, ou TIMEOUT se passou do tempo limite. Evita 'GERADA'
    eterno caso o reconciliador não tenha fechado o registro (timeout, restart,
    pendente sem dag_run_id…)."""
    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute(
            "SELECT dag_run_id, pipeline_name, detalhes_json, "
            "       DATEDIFF(SECOND, iniciado_em, GETDATE()) "
            "FROM dbo.etl_factory_log WHERE estado='GERADA'")
        rows = cur.fetchall()
        if not rows:
            cur.close(); conn.close(); return
        with httpx.Client(base_url=AIRFLOW_URL, auth=(AIRFLOW_USER, AIRFLOW_PASSWORD), timeout=10) as client:
            for run_id, pname, detalhes, idade in rows:
                novo = None
                step = None
                import_trace = None
                if pname and _DAG_ID_RE.match(pname):
                    desired = None  # active=0 → pausada (True); active=1 → ativa (False)
                    try:
                        cur.execute("SELECT active FROM dbo.etl_pipeline WHERE pipeline_name=?", (pname,))
                        pr = cur.fetchone()
                        if pr is not None:
                            desired = (int(pr[0] or 0) == 0)
                    except Exception:
                        desired = None
                    try:
                        g = client.get(f"/api/v1/dags/{pname}")
                        if g.is_success:
                            cur_paused = bool(g.json().get("is_paused", True))
                            if desired is None or cur_paused == desired:
                                # A DAG existe/está ativa — mas pode ter erro de
                                # importação (Airflow mantém a versão antiga ativa).
                                # Só é SUCCESS se NÃO houver import error p/ o .py.
                                import_trace = _import_error_sync(client, pname)
                                if import_trace:
                                    novo = "ERRO"
                                else:
                                    novo = "SUCCESS"
                                    step = ("ativada", "DAG ativa no Airflow — pronta para execução.")
                    except Exception as e:
                        log.debug("[GERADA-RECHECK] poll %s: %s", pname, e)
                if novo is None and int(idade or 0) >= GERADA_TIMEOUT_S:
                    novo = "TIMEOUT"
                    step = ("timeout", "A DAG foi gerada, mas não ficou ativa no Airflow no tempo limite.")
                if novo:
                    novo_detalhes = detalhes
                    bump_erros = False
                    if step or import_trace:
                        try:
                            d = json.loads(detalhes) if detalhes else {}
                        except Exception:
                            d = {}
                        d.setdefault("erros", d.get("erros", []))
                        d.setdefault("steps", [])
                        if step:
                            d["steps"].append({"tipo": step[0], "msg": step[1]})
                        if import_trace:
                            d["steps"].append({"tipo": "import_error", "msg": import_trace})
                            if import_trace not in d["erros"]:
                                d["erros"].append(import_trace)
                            bump_erros = True
                        novo_detalhes = json.dumps(d, ensure_ascii=False)
                    if bump_erros:
                        cur.execute(
                            "UPDATE dbo.etl_factory_log "
                            "SET estado=?, finalizado_em=GETDATE(), detalhes_json=?, erros=erros+1 "
                            "WHERE dag_run_id=? AND estado='GERADA'", (novo, novo_detalhes, run_id))
                    else:
                        cur.execute(
                            "UPDATE dbo.etl_factory_log SET estado=?, finalizado_em=GETDATE(), detalhes_json=? "
                            "WHERE dag_run_id=? AND estado='GERADA'", (novo, novo_detalhes, run_id))
        conn.commit(); cur.close(); conn.close()
    except Exception as e:
        log.debug("[GERADA-RECHECK] %s", e)


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
