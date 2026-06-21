"""api/routers/notificacoes.py — central de notificações por usuário (header)."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Body, Depends, HTTPException, Query

from db import get_db_conn
from deps import get_current_user

log = logging.getLogger("orquestra-api")

router = APIRouter()


@router.get("/notificacoes", tags=["notificacoes"])
def list_notificacoes(limit: int = Query(30, ge=1, le=100),
                      user: dict = Depends(get_current_user)):
    """Notificações mais recentes do usuário logado + contador de não-lidas.

    Degrada para lista vazia se a tabela ainda não existe (migration 032).
    """
    mat = user.get("matricula")
    if not mat:
        return {"data": [], "unread": 0}
    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM dbo.etl_notificacao WHERE matricula=? AND lida=0", (mat,))
        unread = int(cur.fetchone()[0] or 0)
        cur.execute(
            "SELECT TOP (?) id, tipo, titulo, mensagem, link, CAST(lida AS INT), "
            "CONVERT(VARCHAR(19), created_at, 120) "
            "FROM dbo.etl_notificacao WHERE matricula=? ORDER BY created_at DESC, id DESC",
            (limit, mat))
        rows = cur.fetchall()
        cur.close(); conn.close()
        data = [
            {"id": r[0], "tipo": r[1], "titulo": r[2], "mensagem": r[3],
             "link": r[4], "lida": bool(r[5]), "created_at": r[6]}
            for r in rows
        ]
        return {"data": data, "unread": unread}
    except Exception as e:
        log.warning("[NOTIF] list falhou (tabela ausente?): %s", e)
        return {"data": [], "unread": 0}


@router.post("/notificacoes/read", tags=["notificacoes"])
def mark_read(body: dict = Body(default={}), user: dict = Depends(get_current_user)):
    """Marca notificações como lidas. Body: { ids: [int] } ou { all: true }."""
    mat = user.get("matricula")
    if not mat:
        raise HTTPException(status_code=401, detail="sessão inválida")
    ids = body.get("ids")
    marcar_todas = bool(body.get("all")) or not ids
    try:
        conn = get_db_conn(); cur = conn.cursor()
        if marcar_todas:
            cur.execute("UPDATE dbo.etl_notificacao SET lida=1 WHERE matricula=? AND lida=0", (mat,))
        else:
            clean = [int(i) for i in ids if str(i).isdigit()][:200]
            if clean:
                ph = ",".join("?" * len(clean))
                cur.execute(
                    f"UPDATE dbo.etl_notificacao SET lida=1 WHERE matricula=? AND id IN ({ph})",
                    [mat] + clean)
        conn.commit(); cur.close(); conn.close()
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
