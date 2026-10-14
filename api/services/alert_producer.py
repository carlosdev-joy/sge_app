"""Produtor terminal interno sob fence da coorte ORIGINAL.

Registrado no lifespan com opt-in desligado. A fila mantém dry_run obrigatório
até certificação externa dos destinos. Não recebe
um envelope de resultado do chamador e não importa publicações atuais.
"""
import asyncio
import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import HTTPException

from services.alert_cycle import cycle_connection, locked_cycle, conflict
from services.alert_observation import terminal_observation
from services.alert_outbox import require_schema, destinations, unavailable
from services.pipeline_alerts import captured_policy, delivery_identity, event_contract

log = logging.getLogger('orquestra-api')


def enabled():
    from services import alert_runtime
    return os.getenv('EOC_ALERT_PRODUCER_DRY_RUN', '') == '1' or alert_runtime.enabled()


def pending_runs(limit=25):
    """Somente coorte reservada; sem inferir runs ou política atual.

    Ordenação circular por updated_at impede run inconclusivo monopolizar lote.
    A leitura não reserva envio nem cria matrícula/backfill.
    """
    from services.alert_dispatcher import bounded_conn
    with bounded_conn() as (conn, cur):
        require_schema(cur)
        rows = cur.execute('''SELECT TOP (?) c.run_key,c.pipeline_name,c.run_id
            FROM dbo.etl_alert_cycle c WITH (UPDLOCK,READPAST,ROWLOCK)
            JOIN dbo.etl_alert_run_snapshot s ON s.run_key=c.run_key
            WHERE c.pending_clear IS NULL AND NOT EXISTS (
                SELECT 1 FROM dbo.etl_alert_event e WHERE
                e.pipeline_name COLLATE Latin1_General_100_BIN2=c.pipeline_name
                AND e.run_id COLLATE Latin1_General_100_BIN2=c.run_id
                AND e.cycle_generation=c.generation)
            ORDER BY c.updated_at,c.run_key''', (limit,)).fetchall()
        for key, _, _ in rows:
            cur.execute('UPDATE dbo.etl_alert_cycle SET updated_at=SYSUTCDATETIME() '
                        'WHERE run_key=?', (key,))
        conn.commit()
        return [(pipeline, run) for _, pipeline, run in rows]


async def reconcile_once():
    from routers.airflow import get_airflow_client
    runs = pending_runs()
    if not runs:
        return 0
    count = 0
    async with get_airflow_client() as client:
        for pipeline, run in runs:
            try:
                result = await reconcile_terminal(client, pipeline, run)
                count += bool(result.get('created'))
            except Exception:
                log.warning('[ALERT-PRODUCER] observação indisponível; intenção preservada')
    return count


def _work():
    # SQL síncrono e awaits da autoridade ficam fora do event loop da API.
    return asyncio.run(reconcile_once())


async def reconcile_loop():
    if not enabled():
        return
    while True:
        work = asyncio.create_task(asyncio.to_thread(_work))
        try:
            await asyncio.shield(work)
        except asyncio.CancelledError:
            try:
                await work
            except Exception:
                pass
            raise
        except Exception:
            log.warning('[ALERT-PRODUCER] ciclo indisponível; coorte preservada')
        await asyncio.sleep(30)


def original_snapshot(cur, key):
    row = cur.execute(
        'SELECT snapshot_json,snapshot_hash FROM dbo.etl_alert_run_snapshot '
        'WITH (UPDLOCK) WHERE run_key=?', (key,)).fetchone()
    if not row:
        raise conflict('alert_producer_snapshot')
    try:
        document = json.loads(row[0])
        if hashlib.sha256(row[0].encode()).hexdigest() != row[1]:
            raise ValueError()
        capture = captured_policy({'alertPolicy': document['policy']}, document['versionId'])
        if (capture['policyRevision'] != document['policyRevision']
                or 'warningSources' not in document):
            raise ValueError()
        from services.alert_enrollment import snapshot
        canonical = snapshot(document['versionId'], {'alertPolicy': document['policy']},
                             expected_tasks=document['expectedTasks'],
                             processing_tasks=document['processingTasks'],
                             warning_sources=document['warningSources'], delivery_mode=document.get('deliveryMode'))
        if canonical != (row[0], row[1]):
            raise ValueError()
        return document, capture
    except (ValueError, TypeError, KeyError, UnicodeError):
        raise conflict('alert_producer_snapshot') from None


def persist_observation(cur, pipeline, run, generation, capture, observation, *, dry_run=True):
    """Chamador retém locked_cycle até commit. Evento e fan-out são atômicos."""
    if (observation is None or observation.get('warningEvidenceRequired') is not False
            or observation.get('pipeline') != pipeline or observation.get('run') != run):
        raise conflict('alert_producer_observation')
    try:
        source_at = datetime.fromisoformat(observation['sourceAt'].replace('Z', '+00:00'))
        if source_at.tzinfo is None or source_at.utcoffset() is None:
            raise ValueError()
        source_at = source_at.astimezone(timezone.utc).isoformat()
        result = observation['processingResult']
        event = event_contract(dict(schemaVersion=1, pipeline=pipeline, run=run,
                                    cycleGeneration=generation, event=result,
                                    policyRevision=capture['policyRevision'],
                                    source='airflow-task-instances/eoc-attempt',
                                    sourceStatus={'success':'SUCCESS', 'warning':'WARNING',
                                                  'failure':'FAILED'}[result],
                                    sourceAt=source_at,
                                    receivedAt=datetime.now(timezone.utc).isoformat()))
    except (ValueError, TypeError, KeyError):
        raise conflict('alert_producer_observation') from None
    # Um resultado terminal por geração; resultado diferente indica alteração
    # externa não reconciliada. Nunca gerar um novo fan-out silenciosamente.
    previous = cur.execute(
        'SELECT id,event_key FROM dbo.etl_alert_event WITH (UPDLOCK) '
        'WHERE pipeline_name=? AND run_id=? AND cycle_generation=? AND policy_revision=?',
        (pipeline, run, generation, capture['policyRevision'])).fetchall()
    if previous:
        if len(previous) != 1 or previous[0][1] != event['eventKey']:
            raise conflict('alert_producer_terminal_changed')
        return {'eventId': str(UUID(str(previous[0][0]))), 'created': False, 'dryRun': dry_run}
    event_id = str(uuid4())
    utc = lambda value: datetime.fromisoformat(value.replace('Z', '+00:00')).replace(tzinfo=None)
    cur.execute(
        'INSERT dbo.etl_alert_event (id,event_key,policy_revision,pipeline_name,run_id,'
        'cycle_generation,event_type,source,source_status,source_at,received_at,dry_run) '
        'VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
        (event_id, event['eventKey'], capture['policyRevision'], pipeline, run, generation,
         result, event['source'], event['sourceStatus'], utc(event['sourceAt']), utc(event['receivedAt']), int(dry_run)))
    targets = destinations(capture, result)
    for channel, reference in targets:
        cur.execute(
            'INSERT dbo.etl_alert_intent (id,event_id,policy_revision,channel,destination_ref,delivery_key) '
            'VALUES (?,?,?,?,?,?)',
            (str(uuid4()), event_id, capture['policyRevision'], channel, reference,
             delivery_identity(event['eventKey'], channel, reference)))
    return {'eventId': event_id, 'created': True, 'count': len(targets), 'dryRun': dry_run}


async def reconcile_terminal(client, pipeline, run, *, connection_factory=None):
    """Leitura estável e gravação sob o mesmo lock que Clear; sem rede de provider.

    Não matricula ciclos antigos. Timeout/erro reverte a transação.
    Clear Pending/Unknown impede publicação mesmo quando Airflow está verde.
    """
    try:
        with cycle_connection(connection_factory) as (conn, cur):
            cycle = locked_cycle(cur, pipeline, run)
            if cycle is None:
                conn.commit()
                return {'created': False, 'reason': 'legacy'}
            key, generation, pending = cycle
            if pending is not None:
                raise conflict('alert_clear_pending')
            require_schema(cur)
            document, capture = original_snapshot(cur, key)
            observation = await asyncio.wait_for(terminal_observation(
                client, pipeline, run, expected_tasks=document['expectedTasks'],
                processing_tasks=document['processingTasks'],
                warning_sources=document['warningSources']), timeout=5)
            if observation is None:
                conn.commit()
                return {'created': False, 'reason': 'authority_inconclusive'}
            result = persist_observation(cur, pipeline, run, generation, capture, observation,
                                         dry_run=document.get('deliveryMode') != 'operational-test')
            conn.commit()
            return result
    except HTTPException:
        raise
    except Exception:
        raise unavailable() from None
