"""Reenvio auditado interno exclusivamente dry-run F9, sem endpoint ou transporte."""
from uuid import UUID

from fastapi import HTTPException
from services.alert_dispatcher import bounded_conn, MAX_ATTEMPTS, _fixture_filter
from services.alert_outbox import require_schema


def replay_dry_run(intent_id, *, actor, reason, expected_sequence):
    """Ator de contexto confiável do harness; futura rota exige auth/RBAC próprios.

    Unknown/Accepted/Leased jamais reenviados. Compare-and-set e auditoria no mesmo
    commit preservam tentativas anteriores e bloqueiam duplo clique concorrente.
    """
    try:
        intent_id = str(UUID(str(intent_id)))
    except (TypeError, ValueError, AttributeError):
        raise HTTPException(422, 'Intenção inválida') from None
    for text, limit in ((actor, 100), (reason, 500)):
        if (not isinstance(text, str) or not text.strip() or any(ord(c) < 32 for c in text)
                or len(text.encode('utf-16-le')) // 2 > limit):
            raise HTTPException(422, 'Ator e motivo são obrigatórios e limitados')
    if type(expected_sequence) is not int or not 1 <= expected_sequence < MAX_ATTEMPTS:
        raise HTTPException(409, 'Limite de tentativas ou sequência inválida')
    with bounded_conn() as (conn, cur):
        require_schema(cur)
        schema = cur.execute("SELECT COL_LENGTH('dbo.etl_alert_attempt','replay_actor'),"
                             "COL_LENGTH('dbo.etl_alert_attempt','replay_reason'),"
                             "COL_LENGTH('dbo.etl_alert_attempt','replay_at')").fetchone()
        if not schema or not all(schema):
            raise HTTPException(503, 'Reenvio indisponível; confira migration 182_eoc_f10_reenvio')
        row = cur.execute(
            "SELECT i.id FROM dbo.etl_alert_intent i WITH (UPDLOCK,ROWLOCK) "
            "JOIN dbo.etl_alert_event e ON e.id=i.event_id WHERE i.id=? "
            "AND i.state IN ('Failed','DryRun') AND i.attempt_count=? AND " + _fixture_filter(),
            (intent_id, expected_sequence)).fetchone()
        if not row:
            raise HTTPException(409, 'Intenção não elegível para reenvio dry-run')
        cur.execute("UPDATE dbo.etl_alert_attempt SET replay_actor=?,replay_reason=?,replay_at=SYSUTCDATETIME() "
                    "WHERE intent_id=? AND sequence=? AND finished_at IS NOT NULL "
                    "AND outcome IN ('Failed','DryRun') AND replay_at IS NULL",
                    (actor.strip(), reason.strip(), intent_id, expected_sequence))
        if cur.rowcount != 1:
            raise HTTPException(409, 'Tentativa não elegível ou já reenviada')
        cur.execute("UPDATE dbo.etl_alert_intent SET state='Pending',next_attempt_at=SYSUTCDATETIME(),"
                    "updated_at=SYSUTCDATETIME() WHERE id=?", (intent_id,))
        conn.commit()
        return {'requeued': True, 'dryRun': True}
