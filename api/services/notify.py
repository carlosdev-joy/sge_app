"""api/services/notify.py — registro de notificações por usuário.

Helper único usado por vários routers para logar uma ação na central de
notificações do header (tabela dbo.etl_notificacao). É best-effort: nunca
levanta exceção para o chamador — se a tabela ainda não existir (migration 032
não aplicada) ou o banco falhar, apenas registra um warning e segue.
"""
from __future__ import annotations

import logging

from db import get_db_conn

log = logging.getLogger("orquestra-api")

_TIPOS = {"info", "success", "warning", "error"}


def add_notificacao(matricula: str | None, titulo: str,
                    mensagem: str | None = None, tipo: str = "info",
                    link: str | None = None) -> None:
    """Insere uma notificação para `matricula`. Best-effort (não propaga erro)."""
    if not matricula or not titulo:
        return
    tipo = tipo if tipo in _TIPOS else "info"
    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute(
            "INSERT INTO dbo.etl_notificacao (matricula, tipo, titulo, mensagem, link) "
            "VALUES (?, ?, ?, ?, ?)",
            (str(matricula)[:64], tipo, titulo[:160],
             (mensagem[:800] if mensagem else None), (link[:300] if link else None)),
        )
        conn.commit(); cur.close(); conn.close()
    except Exception as e:
        log.warning("[NOTIF] não foi possível registrar notificação p/ %s: %s", matricula, e)
