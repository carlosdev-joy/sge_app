"""api/routers/monitor.py — monitoramento de tabelas (registro + browse + métricas)."""
from __future__ import annotations

import json
import logging
import re

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query

from db import get_db_conn
from deps import get_admin_user
from services.monitor_capture import medir, capturar

log = logging.getLogger("orquestra-api")

router = APIRouter()

_IDENT = re.compile(r"^[A-Za-z0-9_]+$")
_DATE_TYPES = {"date", "datetime", "datetime2", "smalldatetime", "datetimeoffset"}


def _vi(ident: str) -> str:
    if not ident or not _IDENT.match(ident):
        raise HTTPException(status_code=400, detail=f"identificador inválido: {ident!r}")
    return f"[{ident}]"


# ── Browse: tabelas e colunas de um banco (para o cadastro) ─────────────────

@router.get("/admin/monitor/tabelas", tags=["monitor"])
def listar_tabelas_do_banco(database: str = Query(...), _admin: dict = Depends(get_admin_user)):
    qdb = _vi(database)
    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute(
            f"SELECT s.name, t.name, SUM(ISNULL(p.row_count, 0)) "
            f"FROM {qdb}.sys.tables t "
            f"JOIN {qdb}.sys.schemas s ON s.schema_id = t.schema_id "
            f"LEFT JOIN {qdb}.sys.dm_db_partition_stats p "
            f"  ON p.object_id = t.object_id AND p.index_id IN (0, 1) "
            f"GROUP BY s.name, t.name ORDER BY s.name, t.name")
        data = [{"schema": r[0], "tabela": r[1], "linhas": int(r[2] or 0)} for r in cur.fetchall()]
        cur.close(); conn.close()
        return {"data": data, "total": len(data)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/admin/monitor/colunas", tags=["monitor"])
def listar_colunas(database: str = Query(...), schema: str = Query("dbo"),
                   tabela: str = Query(...), _admin: dict = Depends(get_admin_user)):
    qdb = _vi(database); _vi(schema); _vi(tabela)
    objname = f"{database}.{schema}.{tabela}"
    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute(
            f"SELECT c.name, ty.name FROM {qdb}.sys.columns c "
            f"JOIN {qdb}.sys.types ty ON ty.user_type_id = c.user_type_id "
            f"WHERE c.object_id = OBJECT_ID(?) ORDER BY c.column_id", (objname,))
        cols = [{"nome": r[0], "tipo": r[1], "is_data": (r[1] in _DATE_TYPES)} for r in cur.fetchall()]
        cur.close(); conn.close()
        return {"data": cols}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Registro de tabelas monitoradas (CRUD) ──────────────────────────────────

@router.get("/admin/monitor", tags=["monitor"])
def listar_monitor(_admin: dict = Depends(get_admin_user)):
    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute(
            "SELECT t.id, t.database_name, t.schema_name, t.table_name, t.coluna_data, "
            "       t.coluna_atualizacao, t.criticidade, t.sla_horas, t.ativo, t.descricao, "
            "       s.total_linhas, CONVERT(VARCHAR(19), s.ultima_data, 120), "
            "       CONVERT(VARCHAR(19), s.last_write, 120), s.qtde_ultimo_dia, s.por_dia, "
            "       CONVERT(VARCHAR(19), s.captured_at, 120), s.erro "
            "FROM dbo.etl_monitor_tabela t "
            "OUTER APPLY (SELECT TOP 1 * FROM dbo.etl_monitor_snapshot z "
            "             WHERE z.tabela_id = t.id ORDER BY captured_at DESC) s "
            "ORDER BY t.database_name, t.schema_name, t.table_name")
        data = []
        for r in cur.fetchall():
            snap = None
            if r[15]:
                snap = {"total_linhas": r[10], "ultima_data": r[11], "last_write": r[12],
                        "qtde_ultimo_dia": r[13],
                        "por_dia": (json.loads(r[14]) if r[14] else []),
                        "captured_at": r[15], "erro": r[16]}
            data.append({"id": r[0], "database_name": r[1], "schema_name": r[2],
                         "table_name": r[3], "coluna_data": r[4], "coluna_atualizacao": r[5],
                         "criticidade": r[6], "sla_horas": r[7], "ativo": bool(r[8]),
                         "descricao": r[9], "snapshot": snap})
        cur.close(); conn.close()
        return {"data": data}
    except Exception as e:
        log.warning("[MONITOR] listar falhou (tabela ausente?): %s", e)
        return {"data": []}


@router.post("/admin/monitor", tags=["monitor"])
def registrar(body: dict = Body(default={}), admin: dict = Depends(get_admin_user)):
    db  = (body.get("database_name") or "").strip()
    sch = (body.get("schema_name") or "dbo").strip()
    tbl = (body.get("table_name") or "").strip()
    col = (body.get("coluna_data") or "").strip()
    for v in (db, sch, tbl, col):
        _vi(v)
    colat = (body.get("coluna_atualizacao") or "").strip() or None
    if colat:
        _vi(colat)
    crit = (body.get("criticidade") or "").strip() or None
    try:
        sla = int(body.get("sla_horas")) if body.get("sla_horas") not in (None, "") else None
    except (TypeError, ValueError):
        sla = None
    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute(
            "INSERT INTO dbo.etl_monitor_tabela "
            "(database_name, schema_name, table_name, coluna_data, coluna_atualizacao, "
            " criticidade, sla_horas, descricao, criado_por) OUTPUT INSERTED.id "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (db, sch, tbl, col, colat, crit, sla,
             (body.get("descricao") or None), admin.get("matricula")))
        nid = int(cur.fetchone()[0])
        conn.commit(); cur.close(); conn.close()
        return {"ok": True, "id": nid}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/admin/monitor/{mid}", tags=["monitor"])
def editar(mid: int = Path(...), body: dict = Body(default={}), _admin: dict = Depends(get_admin_user)):
    campos, params = [], []

    def setc(col, val):
        campos.append(f"{col} = ?"); params.append(val)

    if body.get("coluna_data"):
        c = body["coluna_data"].strip(); _vi(c); setc("coluna_data", c)
    if "coluna_atualizacao" in body:
        cv = (body.get("coluna_atualizacao") or "").strip() or None
        if cv:
            _vi(cv)
        setc("coluna_atualizacao", cv)
    if "criticidade" in body:
        setc("criticidade", (body.get("criticidade") or None))
    if "sla_horas" in body:
        try:
            setc("sla_horas", int(body["sla_horas"]) if body["sla_horas"] not in (None, "") else None)
        except (TypeError, ValueError):
            pass
    if "descricao" in body:
        setc("descricao", (body.get("descricao") or None))
    if "ativo" in body:
        setc("ativo", 1 if body["ativo"] else 0)
    if not campos:
        return {"ok": True}
    campos.append("atualizado_em = GETDATE()")
    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute(f"UPDATE dbo.etl_monitor_tabela SET {', '.join(campos)} WHERE id = ?",
                    params + [mid])
        n = cur.rowcount
        conn.commit(); cur.close(); conn.close()
        if not n:
            raise HTTPException(status_code=404, detail="não encontrado")
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/admin/monitor/{mid}", tags=["monitor"])
def excluir(mid: int = Path(...), _admin: dict = Depends(get_admin_user)):
    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute("DELETE FROM dbo.etl_monitor_snapshot WHERE tabela_id = ?", (mid,))
        cur.execute("DELETE FROM dbo.etl_monitor_tabela WHERE id = ?", (mid,))
        n = cur.rowcount
        conn.commit(); cur.close(); conn.close()
        return {"ok": bool(n)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Métricas: ao vivo, capturar snapshot, histórico ─────────────────────────

@router.get("/admin/monitor/{mid}/live", tags=["monitor"])
def live(mid: int = Path(...), dias: int = Query(30, ge=1, le=180), _admin: dict = Depends(get_admin_user)):
    return medir(mid, dias)


@router.post("/admin/monitor/{mid}/capturar", tags=["monitor"])
def capturar_agora(mid: int = Path(...), dias: int = Query(30, ge=1, le=180), _admin: dict = Depends(get_admin_user)):
    return capturar(mid, dias)


@router.get("/admin/monitor/{mid}/historico", tags=["monitor"])
def historico(mid: int = Path(...), limit: int = Query(60, ge=1, le=365), _admin: dict = Depends(get_admin_user)):
    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute(
            "SELECT TOP (?) CONVERT(VARCHAR(19), captured_at, 120), total_linhas, "
            "       CONVERT(VARCHAR(19), ultima_data, 120), qtde_ultimo_dia, erro "
            "FROM dbo.etl_monitor_snapshot WHERE tabela_id = ? ORDER BY captured_at DESC",
            (limit, mid))
        data = [{"captured_at": r[0], "total_linhas": r[1], "ultima_data": r[2],
                 "qtde_ultimo_dia": r[3], "erro": r[4]} for r in cur.fetchall()]
        cur.close(); conn.close()
        return {"data": data}
    except Exception as e:
        log.warning("[MONITOR] historico falhou: %s", e)
        return {"data": []}
