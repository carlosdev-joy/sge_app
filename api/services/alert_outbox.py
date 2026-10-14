"""F9A: persistência atômica interna. Nenhum endpoint, provider ou resultado inferido."""
from datetime import datetime
from uuid import uuid4

from fastapi import HTTPException
from db import managed_conn
from services.pipeline_alerts import event_contract, captured_policy, delivery_identity


def unavailable():
    return HTTPException(503, {'code': 'alert_outbox_unavailable',
                              'detail': 'Fila de alertas indisponível; confira a migration 179_eoc_f9_fila_alertas.'})


def require_schema(cur):
    row = cur.execute("SELECT OBJECT_ID('dbo.etl_alert_event','U'),"
                      "OBJECT_ID('dbo.etl_alert_intent','U'),"
                      "OBJECT_ID('dbo.etl_alert_attempt','U')").fetchone()
    if not row or not all(row):
        raise unavailable()


def enqueue_result(*_args, **_kwargs):
    """Gate explícito: envelope validado não constitui autoridade de resultado."""
    raise HTTPException(503, {'code': 'alert_authority_unavailable',
                             'detail': 'Fonte agregada e geração de reprocesso ainda não certificadas.'})


def destinations(capture, event):
    """Referências ao snapshot; nunca copiar e-mail, webhook ou token para a fila."""
    policy = capture['policy']
    if not policy or event not in policy['events']:
        return []
    prefix = capture['policyRevision']
    result = [(channel, prefix + ':recipient:' + str(index))
              for channel in ('email', 'teamsPersonal') if policy[channel]
              for index in range(len(policy['recipients']))]
    if policy['teamsChannel']:
        result.append(('teamsChannel', prefix + ':group:' + str(policy['teamsChannel']['groupId'])))
    return result


def enqueue_dry_run(envelope):
    """Harness interno para fixtures próprias, sem rota HTTP ou publicação/run real.

    Consulta o vínculo original dentro da mesma transação. Não aceita política do
    chamador. dry_run é gravado e também imposto por CHECK no banco nesta etapa.
    """
    event = event_contract(envelope)
    if not all(event[key].startswith('__eoc_f9_') for key in ('pipeline', 'run')) or event['source'] != 'eoc-f9-fixture':
        raise HTTPException(409, {'code': 'alert_fixture_required', 'detail': 'Dry-run restrito a fixtures próprias F9.'})
    try:
        with managed_conn() as (conn, cur):
            require_schema(cur)
            snapshot = cur.execute(
                "SELECT v.version_id,v.definition_json FROM dbo.etl_workspace_execucao e "
                "JOIN dbo.etl_workspace_versao v ON v.version_id=e.version_id "
                "WHERE e.pipeline_name=? AND e.run_id=?", (event['pipeline'], event['run'])).fetchone()
            if snapshot is None:
                raise HTTPException(409, {'code': 'alert_run_unbound', 'detail': 'Fixture sem versão original vinculada.'})
            import json
            capture = captured_policy(json.loads(snapshot[1]), str(snapshot[0]))
            if capture['policyRevision'] != event['policyRevision']:
                raise HTTPException(409, {'code': 'alert_revision_conflict', 'detail': 'Revisão diferente da original da corrida.'})
            targets = destinations(capture, event['event'])
            # Range locks de chaves ausentes em índices distintos podem deadlockar.
            # Serializar por evento antes de ler/inserir, sem lock de range global.
            lock = cur.execute(
                "IF @@TRANCOUNT=0 BEGIN TRANSACTION; DECLARE @r INT; "
                "EXEC @r=sys.sp_getapplock @Resource=?,@LockMode='Exclusive',"
                "@LockOwner='Transaction',@LockTimeout=10000; SELECT @r",
                ('eoc-alert:' + event['eventKey'],)).fetchone()
            if not lock or lock[0] < 0:
                raise unavailable()
            previous = cur.execute(
                "SELECT id FROM dbo.etl_alert_event WITH (UPDLOCK) WHERE event_key=?",
                (event['eventKey'],)).fetchone()
            if previous:
                conn.commit()
                return {'eventId': str(previous[0]), 'created': False, 'count': len(targets), 'dryRun': True}
            event_id = str(uuid4())
            utc = lambda field: datetime.fromisoformat(event[field].replace('Z', '+00:00')).replace(tzinfo=None)
            cur.execute(
                "INSERT dbo.etl_alert_event (id,event_key,policy_revision,pipeline_name,run_id,cycle_generation,"
                "event_type,source,source_status,source_at,received_at,dry_run) VALUES (?,?,?,?,?,?,?,?,?,?,?,1)",
                (event_id, event['eventKey'], capture['policyRevision'], event['pipeline'], event['run'],
                 event['cycleGeneration'], event['event'], event['source'], event['sourceStatus'], utc('sourceAt'), utc('receivedAt')))
            for channel, reference in targets:
                cur.execute(
                    "INSERT dbo.etl_alert_intent (id,event_id,policy_revision,channel,destination_ref,delivery_key) "
                    "VALUES (?,?,?,?,?,?)", (str(uuid4()), event_id, capture['policyRevision'], channel,
                                            reference, delivery_identity(event['eventKey'], channel, reference)))
            conn.commit()
            return {'eventId': event_id, 'created': True, 'count': len(targets), 'dryRun': True}
    except HTTPException:
        raise
    except Exception:
        # Conexão fechada sem commit reverte todo fan-out; nunca expor driver/dados.
        raise unavailable() from None
