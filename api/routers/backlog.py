"""api/routers/backlog.py — backlog do produto (gestão no Admin + skill /backlog)."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query

from db import get_db_conn
from deps import get_current_user, get_admin_user

log = logging.getLogger("orquestra-api")

router = APIRouter()

_TIPOS  = {"feature", "bug", "debt", "spike"}
_AREAS  = {"backend", "frontend", "datastage", "deploy", "infra", "outro"}
_PRIOS  = {"P0", "P1", "P2", "P3"}
_STATUS = {"ideia", "refinado", "em_andamento", "concluido", "descartado"}

_COLS = (
    "id, titulo, descricao, tipo, area, prioridade, status, estimativa, "
    "responsavel, ref_pr, tags, criado_por, "
    "CONVERT(VARCHAR(19), criado_em, 120), CONVERT(VARCHAR(19), atualizado_em, 120), "
    "CONVERT(VARCHAR(19), concluido_em, 120)"
)


def _row(r) -> dict:
    return {
        "id": r[0], "titulo": r[1], "descricao": r[2], "tipo": r[3], "area": r[4],
        "prioridade": r[5], "status": r[6], "estimativa": r[7], "responsavel": r[8],
        "ref_pr": r[9], "tags": r[10], "criado_por": r[11], "criado_em": r[12],
        "atualizado_em": r[13], "concluido_em": r[14],
    }


@router.get("/backlog", tags=["backlog"])
def listar(status: str | None = Query(None), tipo: str | None = Query(None),
           area: str | None = Query(None), q: str | None = Query(None),
           user: dict = Depends(get_current_user)):
    """Lista o backlog (com filtros) + contagem por status. Degrada vazio se a
    tabela ainda não existir (migration 035)."""
    try:
        conn = get_db_conn(); cur = conn.cursor()
        where, params = [], []
        if status:
            where.append("status = ?"); params.append(status)
        if tipo:
            where.append("tipo = ?"); params.append(tipo)
        if area:
            where.append("area = ?"); params.append(area)
        if q:
            where.append("(titulo LIKE ? OR descricao LIKE ?)"); params += [f"%{q}%", f"%{q}%"]
        wsql = (" WHERE " + " AND ".join(where)) if where else ""
        cur.execute(
            f"SELECT {_COLS} FROM dbo.etl_backlog{wsql} "
            "ORDER BY CASE prioridade WHEN 'P0' THEN 0 WHEN 'P1' THEN 1 "
            "         WHEN 'P2' THEN 2 ELSE 3 END, criado_em DESC", params)
        data = [_row(r) for r in cur.fetchall()]
        cur.execute("SELECT status, COUNT(*) FROM dbo.etl_backlog GROUP BY status")
        stats = {s: 0 for s in _STATUS}
        for s, n in cur.fetchall():
            if s in stats:
                stats[s] = int(n or 0)
        cur.close(); conn.close()
        return {"data": data, "stats": stats, "total": len(data)}
    except Exception as e:
        log.warning("[BACKLOG] listar falhou (tabela ausente?): %s", e)
        return {"data": [], "stats": {s: 0 for s in _STATUS}, "total": 0}


@router.post("/backlog", tags=["backlog"])
def criar(body: dict = Body(default={}), admin: dict = Depends(get_admin_user)):
    titulo = (body.get("titulo") or "").strip()
    if not titulo:
        raise HTTPException(status_code=422, detail="titulo é obrigatório")
    tipo = (body.get("tipo") or "feature").strip()
    tipo = tipo if tipo in _TIPOS else "feature"
    area = (body.get("area") or "").strip() or None
    if area and area not in _AREAS:
        area = "outro"
    prio = (body.get("prioridade") or "P2").strip()
    prio = prio if prio in _PRIOS else "P2"
    status = (body.get("status") or "ideia").strip()
    status = status if status in _STATUS else "ideia"
    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute(
            "INSERT INTO dbo.etl_backlog "
            "(titulo, descricao, tipo, area, prioridade, status, estimativa, "
            " responsavel, ref_pr, tags, criado_por) OUTPUT INSERTED.id "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (titulo[:200], (body.get("descricao") or None), tipo, area, prio, status,
             ((body.get("estimativa") or "").strip()[:16] or None),
             ((body.get("responsavel") or "").strip()[:64] or None),
             ((body.get("ref_pr") or "").strip()[:60] or None),
             ((body.get("tags") or "").strip()[:200] or None),
             admin.get("matricula")))
        nid = int(cur.fetchone()[0])
        conn.commit(); cur.close(); conn.close()
        return {"ok": True, "id": nid}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/backlog/{bid}", tags=["backlog"])
def atualizar(bid: int = Path(...), body: dict = Body(default={}),
              admin: dict = Depends(get_admin_user)):
    campos, params = [], []

    def setc(col: str, val):
        campos.append(f"{col} = ?"); params.append(val)

    if "titulo" in body:
        t = (body.get("titulo") or "").strip()
        if not t:
            raise HTTPException(status_code=422, detail="titulo não pode ficar vazio")
        setc("titulo", t[:200])
    if "descricao" in body:
        setc("descricao", body.get("descricao") or None)
    if "tipo" in body and body["tipo"] in _TIPOS:
        setc("tipo", body["tipo"])
    if "area" in body:
        a = (body.get("area") or "").strip() or None
        setc("area", (a if (a is None or a in _AREAS) else "outro"))
    if "prioridade" in body and body["prioridade"] in _PRIOS:
        setc("prioridade", body["prioridade"])
    if "estimativa" in body:
        setc("estimativa", ((body.get("estimativa") or "").strip()[:16] or None))
    if "responsavel" in body:
        setc("responsavel", ((body.get("responsavel") or "").strip()[:64] or None))
    if "ref_pr" in body:
        setc("ref_pr", ((body.get("ref_pr") or "").strip()[:60] or None))
    if "tags" in body:
        setc("tags", ((body.get("tags") or "").strip()[:200] or None))
    if "status" in body and body["status"] in _STATUS:
        setc("status", body["status"])
        campos.append("concluido_em = GETDATE()" if body["status"] == "concluido"
                      else "concluido_em = NULL")

    if not campos:
        return {"ok": True}
    campos.append("atualizado_em = GETDATE()")
    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute(f"UPDATE dbo.etl_backlog SET {', '.join(campos)} WHERE id = ?",
                    params + [bid])
        n = cur.rowcount
        conn.commit(); cur.close(); conn.close()
        if not n:
            raise HTTPException(status_code=404, detail="item não encontrado")
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/backlog/{bid}", tags=["backlog"])
def excluir(bid: int = Path(...), admin: dict = Depends(get_admin_user)):
    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute("DELETE FROM dbo.etl_backlog WHERE id = ?", (bid,))
        n = cur.rowcount
        conn.commit(); cur.close(); conn.close()
        return {"ok": bool(n)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
