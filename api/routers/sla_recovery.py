"""Fila SLA: recuperação deliberada por administrador; nunca executa provider aqui."""
from uuid import UUID
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, StrictBool
from pydantic import Field

from deps import get_admin_user
from services.sla_recovery import recover

router = APIRouter()


class Recovery(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: UUID
    expected_state: Literal['Failed', 'Unknown']
    reason: Literal['configuration_corrected', 'provider_restored', 'manual_verification']
    duplicate_risk_ack: StrictBool = False


@router.post('/sla-alerts/{alert_id}/recover', tags=['admin'])
def recover_sla(alert_id: int, body: Recovery, admin: dict = Depends(get_admin_user)):
    try:
        return recover(alert_id, body.request_id, admin['matricula'], body.expected_state,
                       body.reason, body.duplicate_risk_ack)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(503, 'sla_recovery_unavailable') from None


class AlertRecovery(Recovery):
    expected_state: Literal['Failed', 'Unknown', 'DryRun']
    expected_sequence: int = Field(strict=True, ge=1, le=3)


@router.post('/pipeline-alerts/intents/{intent_id}/recover', tags=['admin'])
def recover_alert(intent_id: UUID, body: AlertRecovery, admin: dict = Depends(get_admin_user)):
    from services.alert_recovery import recover as recover_intent
    try:
        return recover_intent(intent_id, body.request_id, admin['matricula'], body.expected_state,
                              body.expected_sequence, body.reason, body.duplicate_risk_ack)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(503, 'alert_recovery_unavailable') from None


class TestAuthorization(BaseModel):
    model_config = ConfigDict(extra='forbid')
    fingerprints: list[str] = Field(min_length=1, max_length=20)
    ttl_seconds: int = Field(strict=True, ge=1, le=3600)


@router.post('/pipeline-alerts/admin/test-authorization', tags=['admin'])
def authorize_test(body: TestAuthorization, _admin: dict = Depends(get_admin_user)):
    from services import alert_runtime
    from services.alert_dispatcher import bounded_conn
    from services.alert_outbox import require_schema
    if not alert_runtime.enabled():
        raise HTTPException(503, 'alert_operational_test_disabled')
    try:
        with bounded_conn() as (conn, cur):
            require_schema(cur)
            row = cur.execute("SELECT OBJECT_ID('dbo.etl_alert_cycle','U'),"
                              "OBJECT_ID('dbo.etl_alert_run_snapshot','U'),"
                              "OBJECT_ID('dbo.etl_alert_recovery','U'),"
                              "(SELECT COUNT(*) FROM sys.check_constraints WHERE "
                              "parent_object_id=OBJECT_ID('dbo.etl_alert_event') AND "
                              "parent_column_id=COLUMNPROPERTY(OBJECT_ID('dbo.etl_alert_event'),'dry_run','ColumnId'))").fetchone()
            if not row or not all(row[:3]) or row[3] != 0:
                raise HTTPException(503, 'alert_operational_test_requires_migrations_188_191')
            conn.commit()
        return alert_runtime.authorize(body.fingerprints, body.ttl_seconds)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(503, 'alert_operational_test_unavailable') from None


@router.delete('/pipeline-alerts/admin/test-authorization', tags=['admin'])
def revoke_test(_admin: dict = Depends(get_admin_user)):
    from services import alert_runtime
    alert_runtime.revoke()
    return {'revoked': True}
