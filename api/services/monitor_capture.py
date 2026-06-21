"""api/services/monitor_capture.py — observabilidade de tabelas monitoradas.

Mede, ao vivo, métricas das tabelas registradas em etl_monitor_tabela
(total aproximado, última competência, qtde por dia, última escrita) e grava
snapshots em etl_monitor_snapshot. Um loop no lifespan captura periodicamente e
dispara alerta na central de notificações quando uma tabela fica atrasada ou tem
queda forte de volume.

Segurança: identificadores (database/schema/tabela/coluna) NÃO podem ser
parametrizados em SQL — são validados por regex estrita e colocados entre
colchetes. Consultas são cross-database no mesmo servidor (nome de 3 partes);
a credencial precisa de SELECT nas tabelas monitoradas.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from datetime import date, datetime

from db import get_db_conn
from services.notify import add_notificacao

log = logging.getLogger("orquestra-api")

_IDENT = re.compile(r"^[A-Za-z0-9_]+$")
_DATE_TYPES = {"date", "datetime", "datetime2", "smalldatetime", "datetimeoffset"}

CAPTURE_INTERVAL_S = int(os.getenv("MONITOR_CAPTURE_INTERVAL_S", "3600"))   # checagem
SNAPSHOT_EVERY_H   = int(os.getenv("MONITOR_SNAPSHOT_EVERY_H", "24"))       # 1 snapshot/dia
DEFAULT_DIAS       = int(os.getenv("MONITOR_DIAS", "30"))


def qi(ident: str) -> str:
    """Valida um identificador SQL e devolve entre colchetes. Levanta ValueError."""
    if not ident or not _IDENT.match(ident):
        raise ValueError(f"identificador inválido: {ident!r}")
    return f"[{ident}]"


def _read_rec(cur, tabela_id: int) -> dict | None:
    cur.execute(
        "SELECT id, database_name, schema_name, table_name, coluna_data, "
        "coluna_atualizacao, criticidade, sla_horas, criado_por "
        "FROM dbo.etl_monitor_tabela WHERE id = ?", (tabela_id,))
    r = cur.fetchone()
    if not r:
        return None
    return {"id": r[0], "database_name": r[1], "schema_name": r[2], "table_name": r[3],
            "coluna_data": r[4], "coluna_atualizacao": r[5], "criticidade": r[6],
            "sla_horas": r[7], "criado_por": r[8]}


def _measure(cur, rec: dict, dias: int) -> dict:
    db, sch, tbl, col = rec["database_name"], rec["schema_name"], rec["table_name"], rec["coluna_data"]
    qdb, qsch, qtbl, qcol = qi(db), qi(sch), qi(tbl), qi(col)
    full = f"{qdb}.{qsch}.{qtbl}"
    objname = f"{db}.{sch}.{tbl}"

    total = None
    try:
        cur.execute(
            f"SELECT SUM(ISNULL(p.row_count, 0)) FROM {qdb}.sys.dm_db_partition_stats p "
            f"WHERE p.object_id = OBJECT_ID(?) AND p.index_id IN (0, 1)", (objname,))
        row = cur.fetchone()
        total = int(row[0]) if row and row[0] is not None else None
    except Exception as e:
        log.debug("[MONITOR] total %s: %s", objname, e)

    cur.execute(f"SELECT CONVERT(VARCHAR(19), MAX({qcol}), 120) FROM {full}")
    ultima = cur.fetchone()[0]

    cur.execute(
        f"SELECT CONVERT(VARCHAR(10), CAST({qcol} AS DATE), 23) AS dia, COUNT_BIG(*) "
        f"FROM {full} WHERE {qcol} >= DATEADD(DAY, ?, CAST(GETDATE() AS DATE)) "
        f"GROUP BY CAST({qcol} AS DATE) ORDER BY dia", (-abs(int(dias)),))
    por_dia = [{"dia": r[0], "qtde": int(r[1])} for r in cur.fetchall()]
    qtde_ultimo = por_dia[-1]["qtde"] if por_dia else None

    last_write = None
    try:
        cur.execute(
            "SELECT CONVERT(VARCHAR(19), MAX(last_user_update), 120) "
            "FROM sys.dm_db_index_usage_stats "
            "WHERE database_id = DB_ID(?) AND object_id = OBJECT_ID(?)", (db, objname))
        last_write = cur.fetchone()[0]
    except Exception as e:
        log.debug("[MONITOR] last_write %s: %s", objname, e)

    return {"total_linhas": total, "ultima_data": ultima, "last_write": last_write,
            "qtde_ultimo_dia": qtde_ultimo, "por_dia": por_dia}


def medir(tabela_id: int, dias: int = DEFAULT_DIAS) -> dict:
    """Consulta ao vivo (não grava). Retorna métricas + ok, ou {erro}."""
    conn = get_db_conn(); cur = conn.cursor()
    try:
        rec = _read_rec(cur, tabela_id)
        if not rec:
            return {"erro": "tabela não registrada"}
        m = _measure(cur, rec, dias)
        m["ok"] = True
        return m
    except Exception as e:
        return {"erro": str(e)[:400]}
    finally:
        try:
            cur.close(); conn.close()
        except Exception:
            pass


def capturar(tabela_id: int, dias: int = DEFAULT_DIAS, notificar: bool = True) -> dict:
    """Mede e grava um snapshot. Alerta na transição para atraso/queda de volume."""
    conn = get_db_conn(); cur = conn.cursor()
    try:
        rec = _read_rec(cur, tabela_id)
        if not rec:
            return {"erro": "tabela não registrada"}
        cur.execute(
            "SELECT TOP 1 CONVERT(VARCHAR(19), ultima_data, 120), qtde_ultimo_dia "
            "FROM dbo.etl_monitor_snapshot WHERE tabela_id = ? ORDER BY captured_at DESC",
            (tabela_id,))
        prev = cur.fetchone()
        try:
            m = _measure(cur, rec, dias); erro = None
        except Exception as e:
            m = None; erro = str(e)[:400]
        if m is None:
            cur.execute("INSERT INTO dbo.etl_monitor_snapshot (tabela_id, erro) VALUES (?, ?)",
                        (tabela_id, erro))
            conn.commit()
            return {"erro": erro}
        cur.execute(
            "INSERT INTO dbo.etl_monitor_snapshot "
            "(tabela_id, total_linhas, ultima_data, last_write, qtde_ultimo_dia, por_dia) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (tabela_id, m["total_linhas"], m["ultima_data"], m["last_write"],
             m["qtde_ultimo_dia"], json.dumps(m["por_dia"], ensure_ascii=False)))
        conn.commit()
        if notificar:
            try:
                _maybe_alert(rec, m, prev)
            except Exception as e:
                log.debug("[MONITOR] alerta: %s", e)
        m["ok"] = True
        return m
    except Exception as e:
        return {"erro": str(e)[:400]}
    finally:
        try:
            cur.close(); conn.close()
        except Exception:
            pass


def _is_stale(ultima_data_str: str | None) -> bool:
    if not ultima_data_str:
        return True
    try:
        d = datetime.strptime(ultima_data_str[:10], "%Y-%m-%d").date()
    except Exception:
        return False
    return d < date.today()


def _maybe_alert(rec: dict, m: dict, prev) -> None:
    nome = f"{rec['database_name']}.{rec['schema_name']}.{rec['table_name']}"
    mat = rec.get("criado_por")
    stale_now = _is_stale(m["ultima_data"])
    stale_prev = _is_stale(prev[0]) if prev else False
    if stale_now and not stale_prev:
        add_notificacao(mat, f"Tabela {rec['table_name']} sem dados de hoje",
                        f"{nome}: última competência {m['ultima_data'] or '—'} (esperado hoje).",
                        "warning", "/admin")
    por_dia = m["por_dia"] or []
    if len(por_dia) >= 3:
        ult = por_dia[-1]["qtde"]
        ant = [x["qtde"] for x in por_dia[:-1]]
        avg = sum(ant) / len(ant) if ant else 0
        if avg > 0 and ult < 0.5 * avg:
            prev_q = prev[1] if prev else None
            if prev_q is None or prev_q >= 0.5 * avg:
                add_notificacao(mat, f"Queda de volume em {rec['table_name']}",
                                f"{nome}: {ult} registros no último dia vs média {avg:.0f}.",
                                "warning", "/admin")


def _ativas_para_capturar() -> list[int]:
    conn = get_db_conn(); cur = conn.cursor()
    try:
        cur.execute(
            "SELECT t.id FROM dbo.etl_monitor_tabela t WHERE t.ativo = 1 "
            "AND NOT EXISTS (SELECT 1 FROM dbo.etl_monitor_snapshot s "
            "  WHERE s.tabela_id = t.id AND s.captured_at > DATEADD(HOUR, ?, GETDATE()))",
            (-SNAPSHOT_EVERY_H,))
        return [r[0] for r in cur.fetchall()]
    except Exception as e:
        log.debug("[MONITOR] ativas (tabela ausente?): %s", e)
        return []
    finally:
        try:
            cur.close(); conn.close()
        except Exception:
            pass


async def capture_loop() -> None:
    """Loop perene — captura snapshots das tabelas ativas a cada SNAPSHOT_EVERY_H."""
    log.info("[MONITOR] loop iniciado (check=%ds, snapshot a cada %dh)",
             CAPTURE_INTERVAL_S, SNAPSHOT_EVERY_H)
    while True:
        try:
            ids = await asyncio.to_thread(_ativas_para_capturar)
            for tid in ids:
                await asyncio.to_thread(capturar, tid)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.warning("[MONITOR] tick falhou: %s", e)
        await asyncio.sleep(CAPTURE_INTERVAL_S)
