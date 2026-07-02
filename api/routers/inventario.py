"""api/routers/inventario.py — Inventário de Consumidores (endpoints → objetos).

Cadastro documental de quais endpoints/serviços consomem quais views/procs/
tabelas de um banco (caso motivador: BUCC, incidente de 2026-07-02). Em
alterações de schema, os consumidores registrados aqui são ajustados PRIMEIRO
e o banco por último.

Tabelas: dbo.etl_inventario_endpoint / dbo.etl_inventario_objeto (migration 055).
RBAC: leitura para qualquer usuário autenticado (degrada graciosamente se a
migration ainda não rodou); escrita exige o recurso 'tela_inventario'
(admin/desenvolvedor — mesmo recurso que exibe a tela no menu).
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Body, Depends, HTTPException, Path

from db import get_db_conn
from deps import get_current_user, require_perm

log = logging.getLogger("orquestra-api")

router = APIRouter()

PERM_INVENTARIO = "tela_inventario"

_TIPOS_OBJETO = {"view", "proc", "tabela"}
_STATUS_VALIDACAO = {"pendente", "validado", "com_erro"}


def _fmt_dt(v):
    return str(v)[:19] if v else None


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/inventario/endpoints", tags=["inventario"])
def listar_endpoints(q: str = "", banco: str = "",
                     _auth: dict = Depends(get_current_user)):
    """Lista endpoints ativos com seus objetos agregados. Filtros: ?q= (LIKE
    em endpoint/consumidor/objeto) e ?banco=. Degrada para lista vazia se as
    tabelas da migration 055 ainda não existirem."""
    q = (q or "").strip()
    banco = (banco or "").strip()
    try:
        conn = get_db_conn(); cur = conn.cursor()
        sql = (
            "SELECT e.id, e.endpoint, e.plataforma, e.consumidor, e.banco, "
            "       e.descricao, e.responsavel, e.criado_por, e.criado_em, "
            "       e.atualizado_por, e.atualizado_em "
            "FROM dbo.etl_inventario_endpoint e WHERE e.ativo = 1")
        params: list = []
        if q:
            like = f"%{q}%"
            sql += (" AND (e.endpoint LIKE ? OR e.consumidor LIKE ? "
                    "OR EXISTS (SELECT 1 FROM dbo.etl_inventario_objeto o "
                    "           WHERE o.endpoint_id = e.id AND o.objeto LIKE ?))")
            params += [like, like, like]
        if banco:
            sql += " AND e.banco = ?"
            params.append(banco)
        sql += " ORDER BY e.endpoint"
        cur.execute(sql, params)
        endpoints = [
            {"id": r[0], "endpoint": r[1], "plataforma": r[2], "consumidor": r[3],
             "banco": r[4], "descricao": r[5], "responsavel": r[6],
             "criado_por": r[7], "criado_em": _fmt_dt(r[8]),
             "atualizado_por": r[9], "atualizado_em": _fmt_dt(r[10]),
             "objetos": []}
            for r in cur.fetchall()
        ]
        if endpoints:
            por_id = {e["id"]: e for e in endpoints}
            ph = ",".join("?" * len(por_id))
            cur.execute(
                "SELECT id, endpoint_id, objeto, tipo, status_validacao, observacao "
                f"FROM dbo.etl_inventario_objeto WHERE endpoint_id IN ({ph}) "
                "ORDER BY objeto", list(por_id.keys()))
            for r in cur.fetchall():
                por_id[r[1]]["objetos"].append(
                    {"id": r[0], "objeto": r[2], "tipo": r[3],
                     "status_validacao": r[4], "observacao": r[5]})
        cur.close(); conn.close()
        return {"data": endpoints}
    except Exception as e:
        log.warning("[INVENTARIO] listar falhou (tabela ausente?): %s", e)
        return {"data": []}


@router.post("/inventario/endpoints", tags=["inventario"])
def salvar_endpoint(body: dict = Body(default={}),
                    user: dict = Depends(require_perm(PERM_INVENTARIO))):
    """Cria (sem id) ou atualiza (com id) um endpoint do inventário."""
    eid        = body.get("id")
    endpoint   = (body.get("endpoint") or "").strip()
    plataforma = (body.get("plataforma") or "").strip() or None
    consumidor = (body.get("consumidor") or "").strip() or None
    banco      = (body.get("banco") or "").strip() or "BUCC"
    descricao  = (body.get("descricao") or "").strip() or None
    responsavel = (body.get("responsavel") or "").strip() or None

    if not endpoint:
        raise HTTPException(status_code=422, detail="endpoint é obrigatório")
    if eid is not None and not str(eid).isdigit():
        raise HTTPException(status_code=422, detail="id inválido")

    try:
        conn = get_db_conn(); cur = conn.cursor()
        # Unicidade do nome apenas entre os ATIVOS (índice filtrado da 055).
        if eid is None:
            cur.execute("SELECT id FROM dbo.etl_inventario_endpoint "
                        "WHERE endpoint = ? AND ativo = 1", (endpoint,))
        else:
            cur.execute("SELECT id FROM dbo.etl_inventario_endpoint "
                        "WHERE endpoint = ? AND ativo = 1 AND id <> ?",
                        (endpoint, int(eid)))
        if cur.fetchone():
            cur.close(); conn.close()
            raise HTTPException(status_code=422,
                                detail=f"já existe um endpoint ativo com o nome '{endpoint}'")

        if eid is None:
            cur.execute(
                "INSERT INTO dbo.etl_inventario_endpoint "
                "(endpoint, plataforma, consumidor, banco, descricao, responsavel, criado_por) "
                "OUTPUT INSERTED.id VALUES (?, ?, ?, ?, ?, ?, ?)",
                (endpoint[:200], plataforma, consumidor, banco[:128], descricao,
                 responsavel, user["matricula"]))
            new_id = int(cur.fetchone()[0])
            conn.commit(); cur.close(); conn.close()
            return {"ok": True, "id": new_id, "criado": True}

        eid = int(eid)
        cur.execute("SELECT id FROM dbo.etl_inventario_endpoint WHERE id = ? AND ativo = 1", (eid,))
        if not cur.fetchone():
            cur.close(); conn.close()
            raise HTTPException(status_code=404, detail="endpoint não encontrado")
        cur.execute(
            "UPDATE dbo.etl_inventario_endpoint "
            "SET endpoint = ?, plataforma = ?, consumidor = ?, banco = ?, "
            "    descricao = ?, responsavel = ?, "
            "    atualizado_por = ?, atualizado_em = GETDATE() "
            "WHERE id = ?",
            (endpoint[:200], plataforma, consumidor, banco[:128], descricao,
             responsavel, user["matricula"], eid))
        conn.commit(); cur.close(); conn.close()
        return {"ok": True, "id": eid, "criado": False}
    except HTTPException:
        raise
    except Exception as e:
        log.exception("[INVENTARIO] salvar endpoint falhou")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/inventario/endpoints/{eid}", tags=["inventario"])
def excluir_endpoint(eid: int = Path(...),
                     user: dict = Depends(require_perm(PERM_INVENTARIO))):
    """Soft delete do endpoint (ativo=0) — os objetos ficam preservados."""
    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute("SELECT id FROM dbo.etl_inventario_endpoint WHERE id = ? AND ativo = 1", (eid,))
        if not cur.fetchone():
            cur.close(); conn.close()
            raise HTTPException(status_code=404, detail="endpoint não encontrado")
        cur.execute(
            "UPDATE dbo.etl_inventario_endpoint "
            "SET ativo = 0, atualizado_por = ?, atualizado_em = GETDATE() WHERE id = ?",
            (user["matricula"], eid))
        conn.commit(); cur.close(); conn.close()
        return {"ok": True, "id": eid}
    except HTTPException:
        raise
    except Exception as e:
        log.exception("[INVENTARIO] excluir endpoint falhou")
        raise HTTPException(status_code=500, detail=str(e))


# ── Objetos consumidos ───────────────────────────────────────────────────────

@router.post("/inventario/endpoints/{eid}/objetos", tags=["inventario"])
def adicionar_objeto(eid: int = Path(...), body: dict = Body(default={}),
                     user: dict = Depends(require_perm(PERM_INVENTARIO))):
    """Adiciona um objeto (view/proc/tabela) consumido pelo endpoint."""
    objeto = (body.get("objeto") or "").strip()
    tipo = (body.get("tipo") or "view").strip().lower()
    status = (body.get("status_validacao") or "pendente").strip().lower()
    observacao = (body.get("observacao") or "").strip() or None

    if not objeto:
        raise HTTPException(status_code=422, detail="objeto é obrigatório")
    if tipo not in _TIPOS_OBJETO:
        raise HTTPException(status_code=422,
                            detail="tipo inválido (view|proc|tabela)")
    if status not in _STATUS_VALIDACAO:
        raise HTTPException(status_code=422,
                            detail="status_validacao inválido (pendente|validado|com_erro)")

    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute("SELECT id FROM dbo.etl_inventario_endpoint WHERE id = ? AND ativo = 1", (eid,))
        if not cur.fetchone():
            cur.close(); conn.close()
            raise HTTPException(status_code=404, detail="endpoint não encontrado")
        cur.execute(
            "INSERT INTO dbo.etl_inventario_objeto "
            "(endpoint_id, objeto, tipo, status_validacao, observacao, criado_por) "
            "OUTPUT INSERTED.id VALUES (?, ?, ?, ?, ?, ?)",
            (eid, objeto[:300], tipo, status, observacao, user["matricula"]))
        new_id = int(cur.fetchone()[0])
        conn.commit(); cur.close(); conn.close()
        return {"ok": True, "id": new_id}
    except HTTPException:
        raise
    except Exception as e:
        log.exception("[INVENTARIO] adicionar objeto falhou")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/inventario/objetos/{oid}", tags=["inventario"])
def atualizar_objeto(oid: int = Path(...), body: dict = Body(default={}),
                     user: dict = Depends(require_perm(PERM_INVENTARIO))):
    """Atualiza status_validacao e/ou observacao de um objeto do inventário."""
    sets: list[str] = []
    params: list = []
    if "status_validacao" in body:
        status = (body.get("status_validacao") or "").strip().lower()
        if status not in _STATUS_VALIDACAO:
            raise HTTPException(status_code=422,
                                detail="status_validacao inválido (pendente|validado|com_erro)")
        sets.append("status_validacao = ?")
        params.append(status)
    if "observacao" in body:
        observacao = (body.get("observacao") or "").strip() or None
        sets.append("observacao = ?")
        params.append(observacao)
    if not sets:
        raise HTTPException(status_code=422,
                            detail="informe status_validacao e/ou observacao")

    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute("SELECT id FROM dbo.etl_inventario_objeto WHERE id = ?", (oid,))
        if not cur.fetchone():
            cur.close(); conn.close()
            raise HTTPException(status_code=404, detail="objeto não encontrado")
        cur.execute(
            f"UPDATE dbo.etl_inventario_objeto SET {', '.join(sets)} WHERE id = ?",
            params + [oid])
        conn.commit(); cur.close(); conn.close()
        return {"ok": True, "id": oid}
    except HTTPException:
        raise
    except Exception as e:
        log.exception("[INVENTARIO] atualizar objeto falhou")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/inventario/objetos/{oid}", tags=["inventario"])
def remover_objeto(oid: int = Path(...),
                   _auth: dict = Depends(require_perm(PERM_INVENTARIO))):
    """Remove um objeto do inventário."""
    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute("SELECT id FROM dbo.etl_inventario_objeto WHERE id = ?", (oid,))
        if not cur.fetchone():
            cur.close(); conn.close()
            raise HTTPException(status_code=404, detail="objeto não encontrado")
        cur.execute("DELETE FROM dbo.etl_inventario_objeto WHERE id = ?", (oid,))
        conn.commit(); cur.close(); conn.close()
        return {"ok": True, "id": oid}
    except HTTPException:
        raise
    except Exception as e:
        log.exception("[INVENTARIO] remover objeto falhou")
        raise HTTPException(status_code=500, detail=str(e))
