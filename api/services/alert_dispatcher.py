"""F9B: dispatcher persistente exclusivamente dry-run, sem transporte externo."""
import asyncio
import logging
import math
import os
from dataclasses import dataclass
from contextlib import contextmanager
from uuid import uuid4

from db import managed_conn
from services.alert_outbox import require_schema

MAX_ATTEMPTS = 4
LEASE_SECONDS = 60
INTERVAL_SECONDS = 30
log = logging.getLogger('orquestra-api')
QUERY_TIMEOUT_SECONDS = 10
LOCK_TIMEOUT_MS = 5000


@contextmanager
def bounded_conn():
    with managed_conn() as (conn, _cur):
        # timeout de connect não limita consulta. Configurar antes do novo cursor.
        conn.timeout = QUERY_TIMEOUT_SECONDS
        cur = conn.cursor()
        try:
            cur.execute('SET LOCK_TIMEOUT ' + str(LOCK_TIMEOUT_MS))
            yield conn, cur
        finally:
            cur.close()


@dataclass(frozen=True)
class MockResponse:
    """Resultado simulado interno; nunca inclui destino/corpo ou exceção privada."""
    status: int | None = None
    retry_after: object = None
    timeout: bool = False


def classify(response, sequence):
    if response is None:
        return 'DryRun', None, None, None
    if type(response) is not MockResponse:
        raise ValueError('Somente resposta mock interna')
    if response.timeout:
        return 'Unknown', 'mock_timeout', None, None
    if response.status == 200:
        return 'Accepted', None, None, None
    retry_after = None
    if response.status == 429:
        try:
            value = float(response.retry_after)
            if math.isfinite(value) and value >= 0:
                retry_after = min(86400, math.ceil(value))
        except (TypeError, ValueError, OverflowError):
            pass
    retry = response.status in (429, 500) and sequence < MAX_ATTEMPTS
    delay = max(min(3600, 30 * 2 ** (sequence - 1)), retry_after or 0) if retry else None
    code = {429: 'mock_429', 500: 'mock_500'}.get(response.status, 'mock_rejected')
    return 'Failed', code, retry_after, delay


def _fixture_filter():
    return "e.dry_run=1 AND e.source=N'eoc-f9-fixture' " \
           "AND LEFT(e.pipeline_name,9)=N'__eoc_f9_' AND LEFT(e.run_id,9)=N'__eoc_f9_'"


def recover_one():
    """Lease vencida pode ter enviado: encerrar Unknown, nunca retornar Pending."""
    with bounded_conn() as (conn, cur):
        require_schema(cur)
        row = cur.execute(
            "SELECT TOP (1) i.id,i.lease_token,i.attempt_count FROM dbo.etl_alert_intent i "
            "WITH (UPDLOCK,READPAST,ROWLOCK) JOIN dbo.etl_alert_event e ON e.id=i.event_id "
            "WHERE i.state='Leased' AND i.lease_until<=SYSUTCDATETIME() AND " + _fixture_filter() +
            " ORDER BY i.lease_until,i.id").fetchone()
        if not row:
            conn.commit()
            return False
        cur.execute("UPDATE dbo.etl_alert_attempt SET outcome='Unknown',error_code='lease_expired',"
                    "finished_at=SYSUTCDATETIME() WHERE intent_id=? AND lease_token=? AND sequence=? "
                    "AND outcome IS NULL", tuple(row))
        cur.execute("UPDATE dbo.etl_alert_intent SET state='Unknown',lease_token=NULL,lease_until=NULL,"
                    "updated_at=SYSUTCDATETIME() WHERE id=?", (row[0],))
        conn.commit()
        return True


def claim_one():
    """Lock de intenção antes de tentativa; commit único antes de simulação."""
    with bounded_conn() as (conn, cur):
        require_schema(cur)
        row = cur.execute(
            "SELECT TOP (1) i.id,i.attempt_count FROM dbo.etl_alert_intent i "
            "WITH (UPDLOCK,READPAST,ROWLOCK) JOIN dbo.etl_alert_event e ON e.id=i.event_id "
            "WHERE i.state='Pending' AND i.next_attempt_at<=SYSUTCDATETIME() "
            "AND i.attempt_count<? AND " + _fixture_filter() + " ORDER BY i.next_attempt_at,i.id",
            (MAX_ATTEMPTS,)).fetchone()
        if not row:
            conn.commit()
            return None
        intent_id, sequence, token = str(row[0]), row[1] + 1, str(uuid4())
        cur.execute("UPDATE dbo.etl_alert_intent SET state='Leased',attempt_count=?,lease_token=?,"
                    "lease_until=DATEADD(second,?,SYSUTCDATETIME()),updated_at=SYSUTCDATETIME() WHERE id=?",
                    (sequence, token, LEASE_SECONDS, intent_id))
        cur.execute("INSERT dbo.etl_alert_attempt (id,intent_id,sequence,lease_token) VALUES (?,?,?,?)",
                    (str(uuid4()), intent_id, sequence, token))
        conn.commit()
        return {'intentId': intent_id, 'sequence': sequence, 'leaseToken': token}


def finish(claim, response=None):
    outcome, code, retry_after, delay = classify(response, claim['sequence'])
    with bounded_conn() as (conn, cur):
        require_schema(cur)
        row = cur.execute(
            "SELECT i.id FROM dbo.etl_alert_intent i WITH (UPDLOCK,ROWLOCK) "
            "JOIN dbo.etl_alert_event e ON e.id=i.event_id WHERE i.id=? AND i.state='Leased' "
            "AND i.lease_token=? AND i.attempt_count=? AND i.lease_until>SYSUTCDATETIME() AND " + _fixture_filter(),
            (claim['intentId'], claim['leaseToken'], claim['sequence'])).fetchone()
        if not row:
            conn.commit()
            return False
        cur.execute("UPDATE dbo.etl_alert_attempt SET outcome=?,error_code=?,retry_after_seconds=?,"
                    "finished_at=SYSUTCDATETIME() WHERE intent_id=? AND lease_token=? AND sequence=? "
                    "AND outcome IS NULL", (outcome, code, retry_after, claim['intentId'],
                                            claim['leaseToken'], claim['sequence']))
        if cur.rowcount != 1:
            raise RuntimeError('Tentativa durável ausente')
        cur.execute("UPDATE dbo.etl_alert_intent SET state=?,lease_token=NULL,lease_until=NULL,"
                    "next_attempt_at=DATEADD(second,?,SYSUTCDATETIME()),updated_at=SYSUTCDATETIME() WHERE id=?",
                    ('Pending' if delay is not None else outcome, delay or 0, claim['intentId']))
        conn.commit()
        return True


def dispatch_once():
    recover_one()
    claim = claim_one()
    if claim:
        finish(claim)  # Sem callback/provider: termina DryRun; mocks só no harness.
    return bool(claim)


def enabled():
    return os.getenv('EOC_ALERT_DISPATCHER_DRY_RUN', '') == '1'


async def reconcile_loop():
    if not enabled():
        return
    while True:
        work = asyncio.create_task(asyncio.to_thread(dispatch_once))
        try:
            await asyncio.shield(work)
        except asyncio.CancelledError:
            # Não abandonar thread SQL no shutdown; nenhuma thread faz envio.
            try:
                await work
            except Exception:
                pass
            raise
        except Exception:
            log.warning('[ALERT-DISPATCHER] ciclo dry-run indisponível; fila preservada')
        await asyncio.sleep(INTERVAL_SECONDS)
