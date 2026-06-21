"""api/routers/comunicados.py — comunicados do admin (broadcast + auditoria).

Fluxo:
  • Admin compõe um comunicado (simples → sininho/toast, ou banner → pop-up) e
    escolhe o público (todos / por perfil / usuários específicos). No envio a
    audiência é expandida em recibos (etl_comunicado_destinatario).
  • Usuário recebe via /comunicados/inbox (consumido pelo sininho). Cada recibo
    registra entregue → visto → confirmado, permitindo auditoria pelo admin.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Body, Depends, HTTPException, Path

from db import get_db_conn
from deps import get_admin_user, get_current_user

log = logging.getLogger("orquestra-api")

router = APIRouter()

_TIPOS = {"info", "success", "warning", "error"}
_FORMATOS = {"simples", "banner"}
_PUBLICOS = {"todos", "perfil", "usuarios"}


# ── Admin: compor / listar / auditar ────────────────────────────────────────

@router.post("/admin/comunicados", tags=["comunicados"])
def criar_comunicado(body: dict = Body(default={}), _admin: dict = Depends(get_admin_user)):
    """Cria um comunicado e expande o público em destinatários (recibos)."""
    titulo   = (body.get("titulo") or "").strip()
    mensagem = (body.get("mensagem") or "").strip()
    tipo     = (body.get("tipo") or "info").strip()
    formato  = (body.get("formato") or "simples").strip()
    link     = (body.get("link") or "").strip() or None
    pub_tipo = (body.get("publico_tipo") or "").strip()
    perfis   = [str(p).strip() for p in (body.get("perfis") or []) if str(p).strip()]
    matriculas = [str(m).strip().upper() for m in (body.get("matriculas") or []) if str(m).strip()]
    expira_em = (body.get("expira_em") or "").strip() or None

    if not titulo or not mensagem:
        raise HTTPException(status_code=422, detail="titulo e mensagem são obrigatórios")
    if tipo not in _TIPOS:
        tipo = "info"
    if formato not in _FORMATOS:
        formato = "simples"
    if pub_tipo not in _PUBLICOS:
        raise HTTPException(status_code=422, detail="publico_tipo inválido (todos|perfil|usuarios)")
    if pub_tipo == "perfil" and not perfis:
        raise HTTPException(status_code=422, detail="selecione ao menos um perfil")
    if pub_tipo == "usuarios" and not matriculas:
        raise HTTPException(status_code=422, detail="selecione ao menos um usuário")

    if pub_tipo == "todos":
        pub_desc = "Todos os usuários ativos"
    elif pub_tipo == "perfil":
        pub_desc = "Perfis: " + ", ".join(perfis)
    else:
        pub_desc = f"{len(set(matriculas))} usuário(s) específico(s)"

    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute(
            "INSERT INTO dbo.etl_comunicado "
            "(titulo, mensagem, tipo, formato, link, publico_tipo, publico_desc, criado_por, expira_em) "
            "OUTPUT INSERTED.id "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (titulo[:160], mensagem, tipo, formato, (link[:300] if link else None),
             pub_tipo, pub_desc[:300], _admin["matricula"], expira_em))
        cid = int(cur.fetchone()[0])

        # Expande a audiência em recibos
        if pub_tipo == "todos":
            cur.execute(
                "INSERT INTO dbo.etl_comunicado_destinatario (comunicado_id, matricula) "
                "SELECT ?, matricula FROM dbo.etl_usuario WHERE ativo = 1", (cid,))
        elif pub_tipo == "perfil":
            ph = ",".join("?" * len(perfis))
            cur.execute(
                "INSERT INTO dbo.etl_comunicado_destinatario (comunicado_id, matricula) "
                f"SELECT ?, matricula FROM dbo.etl_usuario WHERE ativo = 1 AND perfil_nome IN ({ph})",
                [cid] + perfis)
        else:  # usuarios
            for mat in sorted(set(matriculas)):
                cur.execute(
                    "INSERT INTO dbo.etl_comunicado_destinatario (comunicado_id, matricula) VALUES (?, ?)",
                    (cid, mat))

        cur.execute("SELECT COUNT(*) FROM dbo.etl_comunicado_destinatario WHERE comunicado_id = ?", (cid,))
        total = int(cur.fetchone()[0] or 0)
        conn.commit(); cur.close(); conn.close()
        return {"ok": True, "id": cid, "total_destinatarios": total, "publico_desc": pub_desc}
    except HTTPException:
        raise
    except Exception as e:
        log.exception("[COMUNICADO] criar falhou")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/admin/comunicados", tags=["comunicados"])
def listar_comunicados(_admin: dict = Depends(get_admin_user)):
    """Lista comunicados com estatísticas agregadas de entrega/leitura."""
    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute(
            "SELECT c.id, c.titulo, c.tipo, c.formato, c.publico_tipo, c.publico_desc, "
            "       c.criado_por, CONVERT(VARCHAR(19), c.criado_em, 120), c.ativo, "
            "       CONVERT(VARCHAR(19), c.expira_em, 120), "
            "       COUNT(d.id), "
            "       SUM(CASE WHEN d.visto_em IS NOT NULL THEN 1 ELSE 0 END), "
            "       SUM(CASE WHEN d.confirmado_em IS NOT NULL THEN 1 ELSE 0 END) "
            "FROM dbo.etl_comunicado c "
            "LEFT JOIN dbo.etl_comunicado_destinatario d ON d.comunicado_id = c.id "
            "GROUP BY c.id, c.titulo, c.tipo, c.formato, c.publico_tipo, c.publico_desc, "
            "         c.criado_por, c.criado_em, c.ativo, c.expira_em "
            "ORDER BY c.criado_em DESC")
        data = [
            {"id": r[0], "titulo": r[1], "tipo": r[2], "formato": r[3],
             "publico_tipo": r[4], "publico_desc": r[5], "criado_por": r[6],
             "criado_em": r[7], "ativo": bool(r[8]), "expira_em": r[9],
             "total": int(r[10] or 0), "vistos": int(r[11] or 0), "confirmados": int(r[12] or 0)}
            for r in cur.fetchall()
        ]
        cur.close(); conn.close()
        return {"data": data}
    except Exception as e:
        log.warning("[COMUNICADO] listar falhou (tabela ausente?): %s", e)
        return {"data": []}


@router.get("/admin/comunicados/{cid}", tags=["comunicados"])
def detalhe_comunicado(cid: int = Path(...), _admin: dict = Depends(get_admin_user)):
    """Detalhe do comunicado + recibo por usuário (quem viu/confirmou e quando)."""
    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute(
            "SELECT id, titulo, mensagem, tipo, formato, link, publico_tipo, publico_desc, "
            "       criado_por, CONVERT(VARCHAR(19), criado_em, 120), ativo, "
            "       CONVERT(VARCHAR(19), expira_em, 120) "
            "FROM dbo.etl_comunicado WHERE id = ?", (cid,))
        h = cur.fetchone()
        if not h:
            cur.close(); conn.close()
            raise HTTPException(status_code=404, detail="comunicado não encontrado")
        comunicado = {
            "id": h[0], "titulo": h[1], "mensagem": h[2], "tipo": h[3], "formato": h[4],
            "link": h[5], "publico_tipo": h[6], "publico_desc": h[7], "criado_por": h[8],
            "criado_em": h[9], "ativo": bool(h[10]), "expira_em": h[11],
        }
        cur.execute(
            "SELECT d.matricula, u.primeiro_nome, u.ultimo_nome, u.perfil_nome, "
            "       CONVERT(VARCHAR(19), d.entregue_em, 120), "
            "       CONVERT(VARCHAR(19), d.visto_em, 120), "
            "       CONVERT(VARCHAR(19), d.confirmado_em, 120) "
            "FROM dbo.etl_comunicado_destinatario d "
            "LEFT JOIN dbo.etl_usuario u ON u.matricula = d.matricula "
            "WHERE d.comunicado_id = ? "
            "ORDER BY CASE WHEN d.confirmado_em IS NOT NULL THEN 0 "
            "              WHEN d.visto_em IS NOT NULL THEN 1 ELSE 2 END, d.matricula", (cid,))
        destinatarios = [
            {"matricula": r[0],
             "nome": " ".join([p for p in [r[1], r[2]] if p]) or r[0],
             "perfil": r[3], "entregue_em": r[4], "visto_em": r[5], "confirmado_em": r[6]}
            for r in cur.fetchall()
        ]
        cur.close(); conn.close()
        return {"comunicado": comunicado, "destinatarios": destinatarios}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/admin/comunicados/{cid}/toggle", tags=["comunicados"])
def toggle_comunicado(cid: int = Path(...), _admin: dict = Depends(get_admin_user)):
    """Encerra/reativa um comunicado (ativo ⇄ inativo)."""
    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute(
            "UPDATE dbo.etl_comunicado SET ativo = CASE WHEN ativo = 1 THEN 0 ELSE 1 END "
            "OUTPUT INSERTED.ativo WHERE id = ?", (cid,))
        row = cur.fetchone()
        if not row:
            cur.close(); conn.close()
            raise HTTPException(status_code=404, detail="comunicado não encontrado")
        conn.commit(); novo = bool(row[0]); cur.close(); conn.close()
        return {"ok": True, "ativo": novo}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Usuário: inbox / visto / confirmar ──────────────────────────────────────

@router.get("/comunicados/inbox", tags=["comunicados"])
def inbox(user: dict = Depends(get_current_user)):
    """Comunicados ativos do usuário + estado do recibo. `banners` = pop-ups
    ainda não confirmados (formato banner). Degrada vazio se a tabela faltar."""
    mat = user.get("matricula")
    if not mat:
        return {"data": [], "banners": [], "unread": 0}
    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute(
            "SELECT c.id, c.tipo, c.titulo, c.mensagem, c.formato, c.link, "
            "       CONVERT(VARCHAR(19), c.criado_em, 120), "
            "       CASE WHEN d.visto_em IS NULL THEN 0 ELSE 1 END, "
            "       CASE WHEN d.confirmado_em IS NULL THEN 0 ELSE 1 END "
            "FROM dbo.etl_comunicado_destinatario d "
            "JOIN dbo.etl_comunicado c ON c.id = d.comunicado_id "
            "WHERE d.matricula = ? AND c.ativo = 1 "
            "  AND (c.expira_em IS NULL OR c.expira_em > GETDATE()) "
            "ORDER BY c.criado_em DESC", (mat,))
        data = []
        banners = []
        unread = 0
        for r in cur.fetchall():
            item = {
                "id": r[0], "tipo": r[1], "titulo": r[2], "mensagem": r[3],
                "formato": r[4], "link": r[5], "created_at": r[6],
                "visto": bool(r[7]), "confirmado": bool(r[8]),
            }
            data.append(item)
            if not item["visto"]:
                unread += 1
            if item["formato"] == "banner" and not item["confirmado"]:
                banners.append(item)
        cur.close(); conn.close()
        return {"data": data, "banners": banners, "unread": unread}
    except Exception as e:
        log.warning("[COMUNICADO] inbox falhou (tabela ausente?): %s", e)
        return {"data": [], "banners": [], "unread": 0}


@router.post("/comunicados/visto", tags=["comunicados"])
def marcar_visto(body: dict = Body(default={}), user: dict = Depends(get_current_user)):
    """Marca comunicados como vistos (apareceram no sininho/toast/banner)."""
    mat = user.get("matricula")
    if not mat:
        raise HTTPException(status_code=401, detail="sessão inválida")
    ids = [int(i) for i in (body.get("ids") or []) if str(i).isdigit()][:500]
    if not ids:
        return {"ok": True}
    try:
        conn = get_db_conn(); cur = conn.cursor()
        ph = ",".join("?" * len(ids))
        cur.execute(
            "UPDATE dbo.etl_comunicado_destinatario "
            "SET visto_em = COALESCE(visto_em, GETDATE()) "
            f"WHERE matricula = ? AND visto_em IS NULL AND comunicado_id IN ({ph})",
            [mat] + ids)
        conn.commit(); cur.close(); conn.close()
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/comunicados/{cid}/confirmar", tags=["comunicados"])
def confirmar(cid: int = Path(...), user: dict = Depends(get_current_user)):
    """Marca o comunicado como confirmado (usuário abriu/clicou 'Entendi')."""
    mat = user.get("matricula")
    if not mat:
        raise HTTPException(status_code=401, detail="sessão inválida")
    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute(
            "UPDATE dbo.etl_comunicado_destinatario "
            "SET confirmado_em = COALESCE(confirmado_em, GETDATE()), "
            "    visto_em = COALESCE(visto_em, GETDATE()) "
            "WHERE comunicado_id = ? AND matricula = ?", (cid, mat))
        conn.commit(); cur.close(); conn.close()
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
