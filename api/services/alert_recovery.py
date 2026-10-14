"""Reenvio deliberado preserva evento, política e histórico; nunca envia nesta operação."""
from uuid import UUID

from fastapi import HTTPException
from services.alert_dispatcher import bounded_conn, MAX_ATTEMPTS, _fixture_filter
from services.alert_outbox import require_schema


def recover(intent_id, request_id, actor, expected_state, expected_sequence, reason, duplicate_risk_ack):
    try:
        intent_id, request_id = str(UUID(str(intent_id))), str(UUID(str(request_id)))
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(422, 'alert_recovery_invalid') from None
    if (expected_state not in ('Failed', 'Unknown', 'DryRun')
            or type(expected_sequence) is not int or not 1 <= expected_sequence < MAX_ATTEMPTS
            or not isinstance(actor, str) or not actor or len(actor.encode('utf-16-le')) > 200
            or reason not in ('configuration_corrected', 'provider_restored', 'manual_verification')
            or type(duplicate_risk_ack) is not bool):
        raise HTTPException(422, 'alert_recovery_invalid')
    if expected_state == 'Unknown' and not duplicate_risk_ack:
        raise HTTPException(409, 'alert_duplicate_risk_confirmation_required')
    with bounded_conn() as (conn, cur):
        require_schema(cur)
        schema = cur.execute("SELECT OBJECT_ID('dbo.etl_alert_recovery','U')").fetchone()
        if not schema or not schema[0]:
            raise HTTPException(503, 'alert_recovery_requires_migration_190')
        lock = cur.execute("IF @@TRANCOUNT=0 BEGIN TRANSACTION; DECLARE @r INT; "
                           "EXEC @r=sys.sp_getapplock @Resource=?,@LockMode='Exclusive',"
                           "@LockOwner='Transaction',@LockTimeout=5000; SELECT @r",
                           ('alert-recovery:' + request_id,)).fetchone()
        if not lock or lock[0] < 0:
            raise HTTPException(503, 'alert_recovery_busy')
        prior = cur.execute('SELECT intent_id,previous_state,expected_sequence,actor,reason,duplicate_risk_ack '
                            'FROM dbo.etl_alert_recovery WHERE request_id=?', (request_id,)).fetchone()
        identity = (intent_id, expected_state, expected_sequence, actor, reason, duplicate_risk_ack)
        if prior:
            previous = (str(UUID(str(prior[0]))), *tuple(prior)[1:])
            if previous != identity:
                raise HTTPException(409, 'alert_recovery_request_conflict')
            conn.commit()
            return {'requestId': request_id, 'created': False}
        row = cur.execute(
            'SELECT i.id FROM dbo.etl_alert_intent i WITH (UPDLOCK,ROWLOCK) '
            'JOIN dbo.etl_alert_event e ON e.id=i.event_id WHERE i.id=? AND i.state=? '
            'AND i.attempt_count=? AND ' + _fixture_filter(),
            (intent_id, expected_state, expected_sequence)).fetchone()
        if not row:
            raise HTTPException(409, 'alert_recovery_state_conflict')
        cur.execute('INSERT dbo.etl_alert_recovery '
                    '(request_id,intent_id,previous_state,expected_sequence,actor,reason,duplicate_risk_ack) '
                    'VALUES (?,?,?,?,?,?,?)', (request_id, *identity))
        # Preservar o resultado da tentativa anterior; nova claim usa sequência+1.
        cur.execute("UPDATE dbo.etl_alert_intent SET state='Pending',lease_token=NULL,lease_until=NULL,"
                    'next_attempt_at=SYSUTCDATETIME(),updated_at=SYSUTCDATETIME() WHERE id=?', (intent_id,))
        conn.commit()
        return {'requestId': request_id, 'created': True}
