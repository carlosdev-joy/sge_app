"""api/routers/mensagens.py — catálogo de mensagens do nó de notificação (Teams).

Dois recursos (migration 049):
  • Grupos (etl_msg_grupo)    — canal/webhook do Teams. O webhook_url NUNCA é
    retornado cru nas leituras (campo sensível); expõe apenas has_webhook:bool,
    no mesmo espírito do mascaramento de segredos em routers/infra.py.
  • Templates (etl_msg_template) — mensagem editável com placeholders
    {pipeline} {job} {linhas} {status} {data}; pode sugerir um grupo (grupo_id).

Leitura: get_current_user. Escrita: require_perm(PERM_EDITAR). Toda leitura
degrada para vazio se a tabela não existir (try/except → []).
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query

from db import get_db_conn
from deps import PERM_EDITAR, get_current_user, require_perm

log = logging.getLogger("orquestra-api")

router = APIRouter()


# ── Grupos (canais/webhooks do Teams) ──────────────────────────────────────

@router.get("/msg/grupos", tags=["mensagens"])
def listar_grupos(_user: dict = Depends(get_current_user)):
    """Lista grupos. Não retorna webhook_url cru — apenas has_webhook:bool."""
    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute(
            "SELECT id, nome, descricao, webhook_url, ativo, "
            "       CONVERT(VARCHAR(19), created_at, 120), "
            "       CONVERT(VARCHAR(19), updated_at, 120) "
            "FROM dbo.etl_msg_grupo ORDER BY nome")
        data = [
            {"id": r[0], "nome": r[1], "descricao": r[2],
             "has_webhook": bool(r[3] and str(r[3]).strip()),
             "ativo": bool(r[4]), "created_at": r[5], "updated_at": r[6]}
            for r in cur.fetchall()
        ]
        cur.close(); conn.close()
        return {"data": data}
    except Exception as e:
        log.warning("[MSG] listar_grupos falhou (tabela ausente?): %s", e)
        return {"data": []}


@router.get("/msg/grupos/{gid}", tags=["mensagens"])
def detalhe_grupo(gid: int = Path(...), _user: dict = Depends(get_current_user)):
    """Detalhe de um grupo (sem expor o webhook_url cru — apenas has_webhook)."""
    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute(
            "SELECT id, nome, descricao, webhook_url, ativo, "
            "       CONVERT(VARCHAR(19), created_at, 120), "
            "       CONVERT(VARCHAR(19), updated_at, 120) "
            "FROM dbo.etl_msg_grupo WHERE id = ?", (gid,))
        r = cur.fetchone()
        cur.close(); conn.close()
    except Exception as e:
        log.warning("[MSG] detalhe_grupo falhou (tabela ausente?): %s", e)
        raise HTTPException(status_code=404, detail="grupo não encontrado")
    if not r:
        raise HTTPException(status_code=404, detail="grupo não encontrado")
    return {"id": r[0], "nome": r[1], "descricao": r[2],
            "has_webhook": bool(r[3] and str(r[3]).strip()),
            "ativo": bool(r[4]), "created_at": r[5], "updated_at": r[6]}


@router.post("/msg/grupos", tags=["mensagens"])
def criar_grupo(body: dict = Body(default={}), _auth: dict = Depends(require_perm(PERM_EDITAR))):
    """Cria um grupo (canal Teams). nome é obrigatório; webhook_url é aceito na escrita."""
    nome = (body.get("nome") or "").strip()
    if not nome:
        raise HTTPException(status_code=422, detail="nome é obrigatório")
    descricao = (body.get("descricao") or "").strip() or None
    webhook = (body.get("webhook_url") or "").strip() or None
    ativo = 0 if body.get("ativo") is False else 1
    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute(
            "INSERT INTO dbo.etl_msg_grupo (nome, descricao, webhook_url, ativo) "
            "OUTPUT INSERTED.id VALUES (?, ?, ?, ?)",
            (nome[:120], (descricao[:400] if descricao else None), webhook, ativo))
        gid = int(cur.fetchone()[0])
        conn.commit(); cur.close(); conn.close()
        return {"ok": True, "id": gid}
    except HTTPException:
        raise
    except Exception as e:
        log.exception("[MSG] criar_grupo falhou")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/msg/grupos/{gid}", tags=["mensagens"])
def atualizar_grupo(gid: int = Path(...), body: dict = Body(default={}),
                    _auth: dict = Depends(require_perm(PERM_EDITAR))):
    """Atualiza um grupo. webhook_url só é alterado quando a chave vem no payload
    (um payload sem a chave preserva o webhook atual; "" limpa)."""
    nome = (body.get("nome") or "").strip()
    if not nome:
        raise HTTPException(status_code=422, detail="nome é obrigatório")
    sets = ["nome=?", "descricao=?", "ativo=?", "updated_at=GETDATE()"]
    vals = [nome[:120],
            ((body.get("descricao") or "").strip()[:400] or None),
            (0 if body.get("ativo") is False else 1)]
    if "webhook_url" in body:
        sets.insert(2, "webhook_url=?")
        vals.insert(2, (body.get("webhook_url") or "").strip() or None)
    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute(
            f"UPDATE dbo.etl_msg_grupo SET {', '.join(sets)} WHERE id=?",
            (*vals, gid))
        rows = cur.rowcount
        conn.commit(); cur.close(); conn.close()
    except Exception as e:
        log.exception("[MSG] atualizar_grupo falhou")
        raise HTTPException(status_code=500, detail=str(e))
    if rows == 0:
        raise HTTPException(status_code=404, detail="grupo não encontrado")
    return {"ok": True, "id": gid}


@router.delete("/msg/grupos/{gid}", tags=["mensagens"])
def remover_grupo(gid: int = Path(...), _auth: dict = Depends(require_perm(PERM_EDITAR))):
    """Remove um grupo."""
    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute("DELETE FROM dbo.etl_msg_grupo WHERE id=?", (gid,))
        rows = cur.rowcount
        conn.commit(); cur.close(); conn.close()
    except Exception as e:
        log.exception("[MSG] remover_grupo falhou")
        raise HTTPException(status_code=500, detail=str(e))
    if rows == 0:
        raise HTTPException(status_code=404, detail="grupo não encontrado")
    return {"ok": True, "id": gid}


# ── Templates (mensagens editáveis com placeholders) ───────────────────────

@router.get("/msg/templates", tags=["mensagens"])
def listar_templates(grupo_id: int | None = Query(None),
                     _user: dict = Depends(get_current_user)):
    """Lista templates (opcionalmente filtra por grupo_id)."""
    try:
        conn = get_db_conn(); cur = conn.cursor()
        if grupo_id is not None:
            cur.execute(
                "SELECT id, grupo_id, nome, titulo, corpo, ativo, "
                "       CONVERT(VARCHAR(19), created_at, 120), "
                "       CONVERT(VARCHAR(19), updated_at, 120) "
                "FROM dbo.etl_msg_template WHERE grupo_id = ? ORDER BY nome",
                (grupo_id,))
        else:
            cur.execute(
                "SELECT id, grupo_id, nome, titulo, corpo, ativo, "
                "       CONVERT(VARCHAR(19), created_at, 120), "
                "       CONVERT(VARCHAR(19), updated_at, 120) "
                "FROM dbo.etl_msg_template ORDER BY nome")
        data = [
            {"id": r[0], "grupo_id": r[1], "nome": r[2], "titulo": r[3],
             "corpo": r[4], "ativo": bool(r[5]), "created_at": r[6], "updated_at": r[7]}
            for r in cur.fetchall()
        ]
        cur.close(); conn.close()
        return {"data": data}
    except Exception as e:
        log.warning("[MSG] listar_templates falhou (tabela ausente?): %s", e)
        return {"data": []}


def _parse_grupo_id(raw) -> int | None:
    """grupo_id opcional → int|None (vazio/None = null)."""
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return None
    try:
        return int(raw)
    except (ValueError, TypeError):
        raise HTTPException(status_code=422, detail="grupo_id deve ser inteiro ou nulo")


@router.post("/msg/templates", tags=["mensagens"])
def criar_template(body: dict = Body(default={}), _auth: dict = Depends(require_perm(PERM_EDITAR))):
    """Cria um template. nome e corpo são obrigatórios; grupo_id é opcional."""
    nome = (body.get("nome") or "").strip()
    corpo = (body.get("corpo") or "").strip()
    if not nome or not corpo:
        raise HTTPException(status_code=422, detail="nome e corpo são obrigatórios")
    grupo_id = _parse_grupo_id(body.get("grupo_id"))
    titulo = (body.get("titulo") or "").strip() or None
    ativo = 0 if body.get("ativo") is False else 1
    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute(
            "INSERT INTO dbo.etl_msg_template (grupo_id, nome, titulo, corpo, ativo) "
            "OUTPUT INSERTED.id VALUES (?, ?, ?, ?, ?)",
            (grupo_id, nome[:120], (titulo[:200] if titulo else None), corpo, ativo))
        tid = int(cur.fetchone()[0])
        conn.commit(); cur.close(); conn.close()
        return {"ok": True, "id": tid}
    except HTTPException:
        raise
    except Exception as e:
        log.exception("[MSG] criar_template falhou")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/msg/templates/{tid}", tags=["mensagens"])
def atualizar_template(tid: int = Path(...), body: dict = Body(default={}),
                       _auth: dict = Depends(require_perm(PERM_EDITAR))):
    """Atualiza um template. nome e corpo são obrigatórios."""
    nome = (body.get("nome") or "").strip()
    corpo = (body.get("corpo") or "").strip()
    if not nome or not corpo:
        raise HTTPException(status_code=422, detail="nome e corpo são obrigatórios")
    grupo_id = _parse_grupo_id(body.get("grupo_id"))
    titulo = (body.get("titulo") or "").strip() or None
    ativo = 0 if body.get("ativo") is False else 1
    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute(
            "UPDATE dbo.etl_msg_template "
            "SET grupo_id=?, nome=?, titulo=?, corpo=?, ativo=?, updated_at=GETDATE() "
            "WHERE id=?",
            (grupo_id, nome[:120], (titulo[:200] if titulo else None), corpo, ativo, tid))
        rows = cur.rowcount
        conn.commit(); cur.close(); conn.close()
    except HTTPException:
        raise
    except Exception as e:
        log.exception("[MSG] atualizar_template falhou")
        raise HTTPException(status_code=500, detail=str(e))
    if rows == 0:
        raise HTTPException(status_code=404, detail="template não encontrado")
    return {"ok": True, "id": tid}


@router.delete("/msg/templates/{tid}", tags=["mensagens"])
def remover_template(tid: int = Path(...), _auth: dict = Depends(require_perm(PERM_EDITAR))):
    """Remove um template."""
    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute("DELETE FROM dbo.etl_msg_template WHERE id=?", (tid,))
        rows = cur.rowcount
        conn.commit(); cur.close(); conn.close()
    except Exception as e:
        log.exception("[MSG] remover_template falhou")
        raise HTTPException(status_code=500, detail=str(e))
    if rows == 0:
        raise HTTPException(status_code=404, detail="template não encontrado")
    return {"ok": True, "id": tid}
