"""api/routers/agenda.py — Calendários e blackouts."""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException

from db import get_db_conn
from deps import get_admin_user

log = logging.getLogger("orquestra-api")

router = APIRouter()

FREEZE_MOTIVO = "Congelamento manual do ambiente"


def _fmt_dt(v):
    if v is None:
        return None
    if hasattr(v, "strftime"):
        return v.strftime("%Y-%m-%d %H:%M:%S")
    return str(v)


@router.get("/agenda/calendarios", tags=["agenda"])
def list_calendarios():
    """Lista calendários (nome + qtde de datas + próxima data bloqueada)."""
    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute("""
            SELECT calendario_nome, COUNT(*) AS datas,
                   MIN(CASE WHEN data >= CAST(GETDATE() AS DATE) THEN data END) AS proxima
            FROM dbo.etl_calendario
            GROUP BY calendario_nome ORDER BY calendario_nome
        """)
        data = [{"calendario_nome": r[0], "datas": int(r[1] or 0),
                 "proxima": str(r[2]) if r[2] else None} for r in cur.fetchall()]
        cur.close(); conn.close()
        return {"calendarios": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/agenda/calendarios/{nome}", tags=["agenda"])
def get_calendario(nome: str):
    """Datas de um calendário."""
    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute(
            "SELECT data, descricao FROM dbo.etl_calendario "
            "WHERE calendario_nome = ? ORDER BY data", (nome,))
        data = [{"data": str(r[0]), "descricao": r[1]} for r in cur.fetchall()]
        cur.close(); conn.close()
        return {"calendario_nome": nome, "datas": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/agenda/calendarios", tags=["agenda"])
async def upsert_calendario(body: dict = Body(default={}), _admin: dict = Depends(get_admin_user)):
    """Adiciona datas a um calendário (cria se não existir).

    Body: { calendario_nome, datas: ["YYYY-MM-DD", ...], descricao }
    """
    rb = _admin["matricula"]
    nome = (body.get("calendario_nome") or "").strip()
    datas = body.get("datas") or []
    descricao = (body.get("descricao") or "").strip() or None
    if not nome or not datas:
        raise HTTPException(status_code=422, detail="calendario_nome e datas são obrigatórios")
    try:
        conn = get_db_conn(); cur = conn.cursor()
        inseridas = 0
        for d in datas:
            d = str(d).strip()[:10]
            if not d:
                continue
            cur.execute(
                "INSERT INTO dbo.etl_calendario (calendario_nome, data, descricao, created_by) "
                "SELECT ?, ?, ?, ? WHERE NOT EXISTS "
                "(SELECT 1 FROM dbo.etl_calendario WHERE calendario_nome=? AND data=?)",
                (nome, d, descricao, rb, nome, d))
            inseridas += cur.rowcount
        conn.commit(); cur.close(); conn.close()
        return {"sucesso": True, "calendario_nome": nome, "inseridas": inseridas}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/agenda/calendarios/{nome}", tags=["agenda"])
async def delete_calendario(nome: str, data: Optional[str] = None, _admin: dict = Depends(get_admin_user)):
    """Remove uma data (?data=YYYY-MM-DD) ou o calendário inteiro."""
    try:
        conn = get_db_conn(); cur = conn.cursor()
        if data:
            cur.execute("DELETE FROM dbo.etl_calendario WHERE calendario_nome=? AND data=?",
                        (nome, data))
        else:
            cur.execute("DELETE FROM dbo.etl_calendario WHERE calendario_nome=?", (nome,))
        removidas = cur.rowcount
        conn.commit(); cur.close(); conn.close()
        return {"sucesso": True, "removidas": removidas}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/agenda/blackouts", tags=["agenda"])
def list_blackouts(incluir_historico: int = 0):
    """Blackouts ativos (e histórico recente se incluir_historico=1) + estado de freeze."""
    try:
        conn = get_db_conn(); cur = conn.cursor()
        where = "WHERE ativo = 1" if not incluir_historico else \
                "WHERE ativo = 1 OR created_at >= DATEADD(DAY, -30, GETDATE())"
        cur.execute(f"""
            SELECT TOP 100 id, inicio, fim, escopo, motivo, ativo, criado_por, created_at,
                   CASE WHEN ativo = 1 AND GETDATE() BETWEEN inicio AND fim THEN 1 ELSE 0 END AS vigente
            FROM dbo.etl_blackout {where}
            ORDER BY ativo DESC, inicio DESC
        """)
        data = [{"id": r[0], "inicio": _fmt_dt(r[1]), "fim": _fmt_dt(r[2]),
                 "escopo": r[3], "motivo": r[4], "ativo": int(r[5] or 0),
                 "criado_por": r[6], "created_at": _fmt_dt(r[7]), "vigente": int(r[8] or 0)}
                for r in cur.fetchall()]
        cur.close(); conn.close()
        congelado = any(b["vigente"] and b["escopo"] is None and b["motivo"] == FREEZE_MOTIVO
                        for b in data)
        return {"blackouts": data, "ambiente_congelado": congelado}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/agenda/blackouts", tags=["agenda"])
async def create_blackout(body: dict = Body(default={}), _admin: dict = Depends(get_admin_user)):
    """Cria janela de blackout. Body: { inicio, fim, escopo, motivo }"""
    rb = _admin["matricula"]
    inicio = (body.get("inicio") or "").strip()
    fim    = (body.get("fim") or "").strip()
    escopo = (body.get("escopo") or "").strip() or None
    motivo = (body.get("motivo") or "").strip()
    if not inicio or not fim or not motivo:
        raise HTTPException(status_code=422, detail="inicio, fim e motivo são obrigatórios")
    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute(
            "INSERT INTO dbo.etl_blackout (inicio, fim, escopo, motivo, ativo, criado_por) "
            "VALUES (?, ?, ?, ?, 1, ?)", (inicio, fim, escopo, motivo, rb))
        conn.commit(); cur.close(); conn.close()
        return {"sucesso": True, "mensagem": "Blackout criado."}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/agenda/blackouts/{blackout_id}/encerrar", tags=["agenda"])
async def encerrar_blackout(blackout_id: int, body: dict = Body(default={}), _admin: dict = Depends(get_admin_user)):
    """Desativa um blackout antes do fim programado."""
    rb = _admin["matricula"]
    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute(
            "UPDATE dbo.etl_blackout SET ativo=0, encerrado_por=?, encerrado_em=GETDATE() "
            "WHERE id=? AND ativo=1", (rb, blackout_id))
        n = cur.rowcount
        conn.commit(); cur.close(); conn.close()
        if not n:
            raise HTTPException(status_code=404, detail="Blackout não encontrado ou já encerrado")
        return {"sucesso": True, "mensagem": "Blackout encerrado."}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
