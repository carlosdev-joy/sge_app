"""api/routers/chamados.py — Tela de Chamados da Engenharia (ServiceNow).

GET /chamados            — espelho paginado + frescor + flags de degradação
GET /chamados/indicadores — agregados para a aba Indicadores
"""
from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query

from db import get_db_conn
from deps import get_current_user, require_perm

log = logging.getLogger("orquestra-api")

router = APIRouter()

PERM_CHAMADOS = "tela_chamados"


def _fmt_dt(v) -> str | None:
    if v is None:
        return None
    if hasattr(v, "strftime"):
        return v.strftime("%Y-%m-%d %H:%M:%S")
    return str(v)[:19]


def _frescor(terminado_em) -> dict:
    """Retorna info de frescor e flag de alerta (> 2 ciclos sem sync)."""
    if terminado_em is None:
        return {"texto": "nunca sincronizado", "alerta": True, "horas": None}
    agora = datetime.now()
    delta = agora - terminado_em
    horas = delta.total_seconds() / 3600
    if horas < 1:
        texto = f"sincronizado há {int(delta.total_seconds() / 60)} min"
    elif horas < 24:
        texto = f"sincronizado há {int(horas)}h"
    else:
        texto = f"sincronizado há {int(horas / 24)}d"
    return {"texto": texto, "alerta": horas > 6, "horas": round(horas, 1)}


@router.get("/chamados", tags=["chamados"])
def listar_chamados(
    tipo:        str = Query("", description="incident|ritm|task|change"),
    estado:      str = Query("", description="novo|andamento|aguardando|resolvido|outros"),
    atribuido_a: str = Query("", description="filtro por responsável"),
    prioridade:  str = Query("", description="filtro por prioridade"),
    q:           str = Query("", description="busca por número ou título"),
    _auth: dict = Depends(require_perm(PERM_CHAMADOS)),
):
    """Retorna chamados ativos agrupados por estado_kanban + metadados de frescor."""
    try:
        conn = get_db_conn()
        cur  = conn.cursor()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Banco indisponível: {e}")

    # ── Verificar se migration 088 existe ────────────────────────────────
    try:
        cur.execute("SELECT TOP 1 id FROM dbo.etl_chamado WHERE 1=0")
    except Exception:
        cur.close(); conn.close()
        return {
            "degradado": True,
            "motivo": "sistema em atualização — migration 088 pendente",
            "chamados": [], "frescor": None,
        }

    # ── Último ciclo de sync ──────────────────────────────────────────────
    try:
        cur.execute(
            "SELECT TOP 1 terminado_em, status, erro "
            "FROM dbo.etl_chamado_sync WHERE status IN ('OK','ERRO') "
            "ORDER BY id DESC"
        )
        sync_row = cur.fetchone()
    except Exception:
        sync_row = None

    frescor_info = _frescor(sync_row[0] if sync_row else None)
    sync_status  = sync_row[1] if sync_row else None
    sync_erro    = sync_row[2] if sync_row else None

    # ── Query de chamados ─────────────────────────────────────────────────
    sql = (
        "SELECT sys_id, numero, tipo, titulo, estado_origem, estado_kanban, "
        "       prioridade, atribuido_a, grupo, aberto_em, atualizado_em, url "
        "FROM dbo.etl_chamado WHERE ativo = 1"
    )
    params: list = []

    if tipo:
        sql += " AND tipo = ?"
        params.append(tipo)
    if estado:
        sql += " AND estado_kanban = ?"
        params.append(estado)
    if atribuido_a:
        sql += " AND atribuido_a LIKE ?"
        params.append(f"%{atribuido_a}%")
    if prioridade:
        sql += " AND prioridade LIKE ?"
        params.append(f"%{prioridade}%")
    if q:
        sql += " AND (numero LIKE ? OR titulo LIKE ?)"
        params.append(f"%{q}%")
        params.append(f"%{q}%")

    sql += " ORDER BY aberto_em DESC"

    try:
        cur.execute(sql, params)
        rows = cur.fetchall()
    except Exception as e:
        cur.close(); conn.close()
        raise HTTPException(status_code=500, detail=f"Erro ao consultar chamados: {e}")

    agora = datetime.now()
    chamados = []
    for r in rows:
        aberto_em = r[9]
        idade_dias = (agora - aberto_em).days if aberto_em else None
        chamados.append({
            "sys_id":        r[0],
            "numero":        r[1],
            "tipo":          r[2],
            "titulo":        r[3],
            "estado_origem": r[4],
            "estado_kanban": r[5],
            "prioridade":    r[6],
            "atribuido_a":   r[7],
            "grupo":         r[8],
            "aberto_em":     _fmt_dt(aberto_em),
            "atualizado_em": _fmt_dt(r[10]),
            "url":           r[11],
            "idade_dias":    idade_dias,
        })

    cur.close(); conn.close()

    # Contagem por coluna kanban
    colunas = ["novo", "andamento", "aguardando", "resolvido", "outros"]
    contagem = {c: sum(1 for x in chamados if x["estado_kanban"] == c) for c in colunas}

    return {
        "degradado":   False,
        "frescor":     frescor_info,
        "sync_status": sync_status,
        "sync_erro":   sync_erro,
        "total":       len(chamados),
        "contagem":    contagem,
        "chamados":    chamados,
    }


@router.get("/chamados/indicadores", tags=["chamados"])
def indicadores_chamados(_auth: dict = Depends(require_perm(PERM_CHAMADOS))):
    """Agregados para a aba Indicadores: aging, tipo×estado, entradas×saídas."""
    try:
        conn = get_db_conn()
        cur  = conn.cursor()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Banco indisponível: {e}")

    try:
        cur.execute("SELECT TOP 1 id FROM dbo.etl_chamado WHERE 1=0")
    except Exception:
        cur.close(); conn.close()
        return {"degradado": True, "motivo": "migration 088 pendente"}

    try:
        # Aging por faixa (dias)
        cur.execute("""
            SELECT
                SUM(CASE WHEN DATEDIFF(DAY, aberto_em, GETDATE()) <= 3  THEN 1 ELSE 0 END),
                SUM(CASE WHEN DATEDIFF(DAY, aberto_em, GETDATE()) BETWEEN 4 AND 7  THEN 1 ELSE 0 END),
                SUM(CASE WHEN DATEDIFF(DAY, aberto_em, GETDATE()) BETWEEN 8 AND 14 THEN 1 ELSE 0 END),
                SUM(CASE WHEN DATEDIFF(DAY, aberto_em, GETDATE()) > 14 THEN 1 ELSE 0 END)
            FROM dbo.etl_chamado WHERE ativo = 1
        """)
        ag = cur.fetchone()
        aging = {
            "ate_3d":  ag[0] or 0,
            "4_a_7d":  ag[1] or 0,
            "8_a_14d": ag[2] or 0,
            "acima_14d": ag[3] or 0,
        }

        # Abertos por tipo × estado_kanban
        cur.execute("""
            SELECT tipo, estado_kanban, COUNT(*)
            FROM dbo.etl_chamado WHERE ativo = 1
            GROUP BY tipo, estado_kanban
            ORDER BY tipo, estado_kanban
        """)
        por_tipo_estado: dict = {}
        for tipo, estado, qtd in cur.fetchall():
            por_tipo_estado.setdefault(tipo, {})[estado] = qtd

        # Carga por responsável (top 20)
        cur.execute("""
            SELECT TOP 20 atribuido_a, COUNT(*) AS qtd
            FROM dbo.etl_chamado WHERE ativo = 1 AND atribuido_a IS NOT NULL AND atribuido_a != ''
            GROUP BY atribuido_a
            ORDER BY qtd DESC
        """)
        carga_responsavel = [{"responsavel": r[0], "qtd": r[1]} for r in cur.fetchall()]

        # Entradas × saídas nos últimos 14 dias
        cur.execute("""
            SELECT
                CONVERT(DATE, aberto_em) AS dia,
                COUNT(*) AS entradas
            FROM dbo.etl_chamado
            WHERE aberto_em >= DATEADD(DAY, -14, GETDATE())
            GROUP BY CONVERT(DATE, aberto_em)
            ORDER BY dia
        """)
        entradas = {str(r[0]): r[1] for r in cur.fetchall()}

        cur.execute("""
            SELECT
                CONVERT(DATE, encerrado_em) AS dia,
                COUNT(*) AS saidas
            FROM dbo.etl_chamado
            WHERE encerrado_em >= DATEADD(DAY, -14, GETDATE())
            GROUP BY CONVERT(DATE, encerrado_em)
            ORDER BY dia
        """)
        saidas = {str(r[0]): r[1] for r in cur.fetchall()}

        # Consolidar por dia (últimos 14)
        from datetime import date, timedelta
        dias = [(date.today() - timedelta(days=i)).isoformat() for i in range(13, -1, -1)]
        fluxo = [{"dia": d, "entradas": entradas.get(d, 0), "saidas": saidas.get(d, 0)} for d in dias]

        cur.close(); conn.close()
        return {
            "degradado":        False,
            "aging":            aging,
            "por_tipo_estado":  por_tipo_estado,
            "carga_responsavel":carga_responsavel,
            "fluxo_14d":        fluxo,
        }

    except Exception as e:
        cur.close(); conn.close()
        raise HTTPException(status_code=500, detail=f"Erro ao calcular indicadores: {e}")
