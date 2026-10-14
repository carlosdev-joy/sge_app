"""Recuperação administrativa explícita, sem provider, destino novo ou payload externo."""
from uuid import UUID

from fastapi import HTTPException
from db import managed_conn


def recover(alert_id, request_id, actor, expected_state, reason, duplicate_risk_ack):
    request_id = str(UUID(str(request_id)))
    if (type(alert_id) is not int or alert_id <= 0
            or expected_state not in ('Failed', 'Unknown')
            or reason not in ('configuration_corrected', 'provider_restored', 'manual_verification')
            or type(duplicate_risk_ack) is not bool
            or not isinstance(actor, str) or not actor or len(actor.encode('utf-16-le')) > 200):
        raise HTTPException(422, 'sla_recovery_invalid')
    if expected_state == 'Unknown' and not duplicate_risk_ack:
        raise HTTPException(409, 'sla_duplicate_risk_confirmation_required')
    with managed_conn() as (conn, cur):
        schema = cur.execute("SELECT OBJECT_ID('dbo.etl_sla_recovery','U'),"
                             "COL_LENGTH('dbo.etl_sla_alert','intent_json')").fetchone()
        if not schema or not all(schema):
            raise HTTPException(503, 'sla_recovery_requires_migration_190')
        # Mesmo alerta serializa recuperação e claim; pedido serializa replay
        # inclusive quando cliente tentar reutilizar UUID para outro alerta.
        lock = cur.execute("IF @@TRANCOUNT=0 BEGIN TRANSACTION; DECLARE @r INT; "
                           "EXEC @r=sys.sp_getapplock @Resource=?,@LockMode='Exclusive',"
                           "@LockOwner='Transaction',@LockTimeout=5000; SELECT @r",
                           ('sla-recovery:' + request_id,)).fetchone()
        if not lock or lock[0] < 0:
            raise HTTPException(503, 'sla_recovery_busy')
        previous = cur.execute('SELECT alert_id,previous_state,actor,reason,duplicate_risk_ack '
                               'FROM dbo.etl_sla_recovery WHERE request_id=?', (request_id,)).fetchone()
        identity = (alert_id, expected_state, actor, reason, duplicate_risk_ack)
        if previous:
            if tuple(previous) != identity:
                raise HTTPException(409, 'sla_recovery_request_conflict')
            conn.commit()
            return {'requestId': request_id, 'created': False}
        row = cur.execute('SELECT delivery_state,intent_json FROM dbo.etl_sla_alert '
                          'WITH (UPDLOCK,ROWLOCK) WHERE id=?', (alert_id,)).fetchone()
        if not row or row[0] != expected_state or not row[1]:
            raise HTTPException(409, 'sla_recovery_state_conflict')
        cur.execute('INSERT dbo.etl_sla_recovery '
                    '(request_id,alert_id,previous_state,actor,reason,duplicate_risk_ack) VALUES (?,?,?,?,?,?)',
                    (request_id, *identity))
        cur.execute("UPDATE dbo.etl_sla_alert SET delivery_state='Pending',claim_token=NULL,lease_until=NULL "
                    'WHERE id=?', (alert_id,))
        conn.commit()
        return {'requestId': request_id, 'created': True}
