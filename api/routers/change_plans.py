"""api/routers/change_plans.py — Planos de ajuste de campos (worklist operacional).

A partir da busca de impacto por campo, o usuário monta um plano com as
ocorrências a alterar (job + stage + coluna) e acompanha o andamento item a
item (status + data/hora + responsável). Só rastreia — a alteração em si é
feita no DataStage.

Endpoints:
  GET    /change-plans                          — lista planos + progresso
  POST   /change-plans                          — cria plano (com itens opcionais)
  GET    /change-plans/{plan_id}                — plano + itens
  POST   /change-plans/{plan_id}/items          — adiciona itens (dedup)
  PATCH  /change-plans/{plan_id}/items/{item_id}— atualiza item (status/alvo/obs)
  DELETE /change-plans/{plan_id}/items/{item_id}— remove item
  POST   /change-plans/{plan_id}/finalize       — finaliza o plano
  DELETE /change-plans/{plan_id}                — remove plano (e itens)
"""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException

from db import managed_conn
from deps import PERM_EDITAR, get_current_user, require_perm

router = APIRouter()

ITEM_STATUS = {"pendente", "em_andamento", "concluido"}


def _fmt_dt(v):
    if v is None:
        return None
    if hasattr(v, "strftime"):
        return v.strftime("%Y-%m-%d %H:%M:%S")
    return str(v)


def _quem(user: dict) -> str:
    """Identificação curta do usuário para os campos *_by."""
    nome = " ".join(filter(None, [user.get("primeiro_nome"), user.get("ultimo_nome")])).strip()
    return nome or user.get("matricula") or "?"


# Campos do item, na ordem do SELECT (reuso no serializador)
_ITEM_COLS = (
    "id, plan_id, dsx_file, project_name, job_name, stage_name, stage_type, "
    "direction, object_name, column_name, datatype_atual, precision_val, scale_val, "
    "datatype_alvo, status, observacao, assigned_to, started_at, done_at, done_by, "
    "created_at, updated_at"
)


def _item_to_dict(r) -> dict:
    return {
        "id": r[0], "plan_id": r[1], "dsx_file": r[2], "project_name": r[3],
        "job_name": r[4], "stage_name": r[5], "stage_type": r[6], "direction": r[7],
        "object_name": r[8], "column_name": r[9], "datatype_atual": r[10],
        "precision": r[11], "scale": r[12], "datatype_alvo": r[13], "status": r[14],
        "observacao": r[15], "assigned_to": r[16], "started_at": _fmt_dt(r[17]),
        "done_at": _fmt_dt(r[18]), "done_by": r[19],
        "created_at": _fmt_dt(r[20]), "updated_at": _fmt_dt(r[21]),
    }


def _insert_itens(cur, plan_id: int, itens: list[dict]) -> int:
    """Insere itens com dedup por (plan_id, job_name, stage_name, column_name)."""
    inseridos = 0
    for it in itens or []:
        job = (it.get("job_name") or "").strip()
        col = (it.get("column_name") or it.get("name") or "").strip()
        if not job or not col:
            continue
        stage = it.get("stage_name")
        cur.execute(
            """INSERT INTO dbo.etl_field_change_item
                 (plan_id, dsx_file, project_name, job_name, stage_name, stage_type,
                  direction, object_name, column_name, datatype_atual, precision_val,
                  scale_val, datatype_alvo, observacao, assigned_to)
               SELECT ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?
               WHERE NOT EXISTS (
                   SELECT 1 FROM dbo.etl_field_change_item
                   WHERE plan_id=? AND job_name=?
                     AND ISNULL(stage_name,'')=ISNULL(?, '') AND column_name=?
               )""",
            [plan_id, it.get("dsx_file"), it.get("project_name"), job, stage,
             it.get("stage_type"), it.get("direction"), it.get("object_name"), col,
             it.get("datatype_atual") or it.get("type_name"),
             it.get("precision"), it.get("scale"), it.get("datatype_alvo"),
             it.get("observacao"), it.get("assigned_to"),
             plan_id, job, stage, col],
        )
        inseridos += cur.rowcount or 0
    return inseridos


@router.get("/change-plans", tags=["change-plans"])
def list_plans(_auth: dict = Depends(get_current_user)):
    with managed_conn() as (conn, cur):
        cur.execute("""
            SELECT p.id, p.nome, p.descricao, p.status, p.created_by, p.created_at,
                   p.finalized_at, p.finalized_by,
                   (SELECT COUNT(*) FROM dbo.etl_field_change_item i WHERE i.plan_id=p.id) AS total,
                   (SELECT COUNT(*) FROM dbo.etl_field_change_item i WHERE i.plan_id=p.id AND i.status='concluido') AS concluidos
            FROM dbo.etl_field_change_plan p
            ORDER BY p.created_at DESC
        """)
        rows = cur.fetchall()
    return {"planos": [{
        "id": r[0], "nome": r[1], "descricao": r[2], "status": r[3],
        "created_by": r[4], "created_at": _fmt_dt(r[5]),
        "finalized_at": _fmt_dt(r[6]), "finalized_by": r[7],
        "total_itens": r[8], "concluidos": r[9],
    } for r in rows]}


@router.post("/change-plans", tags=["change-plans"])
def create_plan(body: dict = Body(default={}), user: dict = Depends(require_perm(PERM_EDITAR))):
    nome = (body.get("nome") or "").strip()
    if not nome:
        raise HTTPException(status_code=422, detail="O nome do plano é obrigatório.")
    with managed_conn() as (conn, cur):
        cur.execute(
            """INSERT INTO dbo.etl_field_change_plan (nome, descricao, created_by)
               OUTPUT INSERTED.id VALUES (?, ?, ?)""",
            [nome, body.get("descricao"), _quem(user)])
        plan_id = int(cur.fetchone()[0])
        inseridos = _insert_itens(cur, plan_id, body.get("itens") or [])
        conn.commit()
    return {"sucesso": True, "id": plan_id, "inseridos": inseridos}


@router.get("/change-plans/{plan_id}", tags=["change-plans"])
def get_plan(plan_id: int, _auth: dict = Depends(get_current_user)):
    with managed_conn() as (conn, cur):
        cur.execute(
            """SELECT id, nome, descricao, status, created_by, created_at, updated_at,
                      finalized_at, finalized_by
               FROM dbo.etl_field_change_plan WHERE id = ?""", [plan_id])
        p = cur.fetchone()
        if not p:
            raise HTTPException(status_code=404, detail="Plano não encontrado.")
        cur.execute(
            f"SELECT {_ITEM_COLS} FROM dbo.etl_field_change_item "
            "WHERE plan_id = ? ORDER BY job_name, stage_name, column_name", [plan_id])
        itens = [_item_to_dict(r) for r in cur.fetchall()]
    return {"plano": {
        "id": p[0], "nome": p[1], "descricao": p[2], "status": p[3],
        "created_by": p[4], "created_at": _fmt_dt(p[5]), "updated_at": _fmt_dt(p[6]),
        "finalized_at": _fmt_dt(p[7]), "finalized_by": p[8],
    }, "itens": itens}


@router.post("/change-plans/{plan_id}/items", tags=["change-plans"])
def add_items(plan_id: int, body: dict = Body(default={}), _auth: dict = Depends(require_perm(PERM_EDITAR))):
    with managed_conn() as (conn, cur):
        cur.execute("SELECT status FROM dbo.etl_field_change_plan WHERE id = ?", [plan_id])
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Plano não encontrado.")
        if row[0] == "finalizado":
            raise HTTPException(status_code=409, detail="Plano finalizado não aceita novos itens.")
        inseridos = _insert_itens(cur, plan_id, body.get("itens") or [])
        cur.execute("UPDATE dbo.etl_field_change_plan SET updated_at = SYSDATETIME() WHERE id = ?", [plan_id])
        conn.commit()
    return {"sucesso": True, "inseridos": inseridos}


@router.patch("/change-plans/{plan_id}/items/{item_id}", tags=["change-plans"])
def update_item(plan_id: int, item_id: int, body: dict = Body(default={}),
                user: dict = Depends(require_perm(PERM_EDITAR))):
    sets: list[str] = []
    params: list = []

    if "datatype_alvo" in body:
        sets.append("datatype_alvo = ?"); params.append(body.get("datatype_alvo"))
    if "observacao" in body:
        sets.append("observacao = ?"); params.append(body.get("observacao"))
    if "assigned_to" in body:
        sets.append("assigned_to = ?"); params.append(body.get("assigned_to"))

    if "status" in body:
        status = (body.get("status") or "").strip()
        if status not in ITEM_STATUS:
            raise HTTPException(status_code=422, detail=f"status inválido: {status}")
        sets.append("status = ?"); params.append(status)
        if status == "em_andamento":
            sets.append("started_at = COALESCE(started_at, SYSDATETIME())")
            sets.append("done_at = NULL"); sets.append("done_by = NULL")
        elif status == "concluido":
            sets.append("started_at = COALESCE(started_at, SYSDATETIME())")
            sets.append("done_at = SYSDATETIME()")
            sets.append("done_by = ?"); params.append(_quem(user))
        else:  # pendente
            sets.append("done_at = NULL"); sets.append("done_by = NULL")

    if not sets:
        raise HTTPException(status_code=422, detail="Nada para atualizar.")

    sets.append("updated_at = SYSDATETIME()")
    params += [item_id, plan_id]
    with managed_conn() as (conn, cur):
        cur.execute(
            f"UPDATE dbo.etl_field_change_item SET {', '.join(sets)} "
            "WHERE id = ? AND plan_id = ?", params)
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Item não encontrado.")
        cur.execute(f"SELECT {_ITEM_COLS} FROM dbo.etl_field_change_item WHERE id = ?", [item_id])
        item = _item_to_dict(cur.fetchone())
        conn.commit()
    return {"sucesso": True, "item": item}


@router.delete("/change-plans/{plan_id}/items/{item_id}", tags=["change-plans"])
def delete_item(plan_id: int, item_id: int, _auth: dict = Depends(require_perm(PERM_EDITAR))):
    with managed_conn() as (conn, cur):
        cur.execute(
            "DELETE FROM dbo.etl_field_change_item WHERE id = ? AND plan_id = ?",
            [item_id, plan_id])
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Item não encontrado.")
        conn.commit()
    return {"sucesso": True}


@router.post("/change-plans/{plan_id}/finalize", tags=["change-plans"])
def finalize_plan(plan_id: int, body: dict = Body(default={}),
                  user: dict = Depends(require_perm(PERM_EDITAR))):
    reabrir = str(body.get("reabrir", "false")).lower() in ("true", "1", "yes")
    with managed_conn() as (conn, cur):
        if reabrir:
            cur.execute(
                """UPDATE dbo.etl_field_change_plan
                   SET status='aberto', finalized_at=NULL, finalized_by=NULL,
                       updated_at=SYSDATETIME() WHERE id = ?""", [plan_id])
        else:
            cur.execute(
                """UPDATE dbo.etl_field_change_plan
                   SET status='finalizado', finalized_at=SYSDATETIME(),
                       finalized_by=?, updated_at=SYSDATETIME() WHERE id = ?""",
                [_quem(user), plan_id])
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Plano não encontrado.")
        conn.commit()
    return {"sucesso": True, "status": "aberto" if reabrir else "finalizado"}


@router.delete("/change-plans/{plan_id}", tags=["change-plans"])
def delete_plan(plan_id: int, _auth: dict = Depends(require_perm(PERM_EDITAR))):
    with managed_conn() as (conn, cur):
        cur.execute("DELETE FROM dbo.etl_field_change_plan WHERE id = ?", [plan_id])
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Plano não encontrado.")
        conn.commit()
    return {"sucesso": True}
