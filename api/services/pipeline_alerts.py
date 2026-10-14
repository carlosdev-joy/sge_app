"""F7: contrato puro de política/evento. Não importa transporte nem emite mensagens."""
from __future__ import annotations

import copy
import hashlib
import json
import re
from datetime import datetime, timezone
from uuid import UUID
from fastapi import HTTPException

EVENTS = ('success', 'warning', 'failure')
EMAIL = re.compile(r"[A-Za-z0-9.!#$%&'*+/=?^_{}|~-]+@[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)+\Z")


def disabled_policy():
    """Default explícito para autoria nova; ausência preserva o legado."""
    return dict(schemaVersion=1, events=[], recipients=[], email=False,
                teamsPersonal=False, teamsChannel=None, attemptMode='terminal')


def invalid(field):
    # Nunca incluir endereço, referência protegida ou conteúdo de entrada.
    raise HTTPException(422, {'code': 'alert_policy_invalid', 'field': field,
                              'detail': 'Configuração de alertas inválida; confira o campo indicado.'})


def policy(value):
    """Campos desconhecidos falham fechado, sem descartar o documento original."""
    if not isinstance(value, dict) or set(value) != {'schemaVersion', 'events', 'recipients', 'email', 'teamsPersonal', 'teamsChannel', 'attemptMode'}:
        invalid('alertPolicy')
    if type(value['schemaVersion']) is not int or value['schemaVersion'] != 1:
        invalid('schemaVersion')
    events = value['events']
    if not isinstance(events, list) or any(type(x) is not str or x not in EVENTS for x in events) or len(events) != len(set(events)):
        invalid('events')
    recipients = value['recipients']
    if not isinstance(recipients, list) or len(recipients) > 100:
        invalid('recipients')
    normalized = []
    for address in recipients:
        if not isinstance(address, str) or len(address) > 320 or len(address.split('@')[0]) > 64 or not EMAIL.fullmatch(address):
            invalid('recipients')
        local, domain = address.split('@')
        if local.startswith('.') or local.endswith('.') or '..' in local or any(len(label) > 63 for label in domain.split('.')):
            invalid('recipients')
        address = address.lower()
        if address not in normalized:
            normalized.append(address)
    if type(value['email']) is not bool or type(value['teamsPersonal']) is not bool:
        invalid('channels')
    channel = value['teamsChannel']
    # Referência ao cadastro existente; nunca URL/webhook/token dentro do draft.
    if channel is not None and (not isinstance(channel, dict) or set(channel) != {'groupId'} or type(channel['groupId']) is not int or not 1 <= channel['groupId'] <= 2147483647):
        invalid('teamsChannel')
    if value['attemptMode'] != 'terminal':
        invalid('attemptMode')
    if (value['email'] or value['teamsPersonal']) and not normalized:
        invalid('recipients')
    result = copy.deepcopy(value)
    result['events'] = [x for x in EVENTS if x in events]
    result['recipients'] = normalized
    return result


def revision(value):
    """Revisão de conteúdo, imutável no snapshot da versão reservada para o run."""
    return hashlib.sha256(json.dumps(policy(value), sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()


def captured_policy(definition, version_id):
    """Chamador deve fornecer versão vinculada ao run, jamais a publicação atual."""
    try:
        version_id = str(UUID(str(version_id)))
    except (ValueError, TypeError, AttributeError):
        invalid('versionId')
    if not isinstance(definition, dict):
        invalid('definition')
    if 'alertPolicy' not in definition:
        return {'mode': 'legacy', 'policyRevision': None, 'policy': None}
    value = definition['alertPolicy']
    clean = policy(value)
    return {'mode': 'workspace', 'policyRevision': str(version_id).lower() + ':' + revision(clean), 'policy': clean}


def event_contract(value):
    """Valida o envelope, sem confirmar a fonte, persistir ou emitir o evento.

    A autoridade e a geração serão fornecidas pelo adapter de resultado da F9.
    Não há default de geração/data e erro de transporte não é resultado.
    """
    required = {'schemaVersion', 'pipeline', 'run', 'cycleGeneration', 'event',
                'policyRevision', 'source', 'sourceStatus', 'sourceAt', 'receivedAt'}
    if not isinstance(value, dict) or set(value) != required:
        invalid('event')
    if type(value['schemaVersion']) is not int or value['schemaVersion'] != 1:
        invalid('schemaVersion')
    for field, limit in (('pipeline', 200), ('run', 250), ('source', 100)):
        text = value[field]
        if not isinstance(text, str) or not text or any(ord(c) < 32 or ord(c) == 127 for c in text):
            invalid(field)
        try:
            if len(text.encode('utf-16-le')) // 2 > limit:
                invalid(field)
        except UnicodeError:
            invalid(field)
    revision_id = value['policyRevision']
    if not isinstance(revision_id, str) or not re.fullmatch(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}:[0-9a-f]{64}', revision_id):
        invalid('policyRevision')
    statuses = {'SUCCESS': 'success', 'SUCESSO': 'success', 'WARNING': 'warning',
                'FAILED': 'failure', 'FALHA': 'failure'}
    status = value['sourceStatus']
    if not isinstance(status, str) or statuses.get(status) != value['event']:
        invalid('sourceStatus')
    for field in ('sourceAt', 'receivedAt'):
        text = value[field]
        if not isinstance(text, str) or len(text) > 40 or not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)', text):
            invalid(field)
        try:
            timestamp = datetime.fromisoformat(text.replace('Z', '+00:00'))
            if timestamp.tzinfo != timezone.utc:
                invalid(field)
        except ValueError:
            invalid(field)
    result = copy.deepcopy(value)
    result['eventKey'] = event_identity(value['pipeline'], value['run'], value['cycleGeneration'],
                                        value['event'], revision_id)
    return result


def event_identity(pipeline, run, generation, event, policy_revision):
    if not all(isinstance(x, str) and 0 < len(x) <= 1000 for x in (pipeline, run, policy_revision)):
        invalid('identity')
    if type(generation) is not int or not 1 <= generation <= 2147483647 or event not in EVENTS:
        invalid('cycleGeneration')
    return hashlib.sha256(json.dumps([pipeline, run, generation, event, policy_revision], ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def delivery_identity(event_id, channel, destination_ref):
    if not isinstance(event_id, str) or not re.fullmatch('[0-9a-f]{64}', event_id) or channel not in ('email', 'teamsPersonal', 'teamsChannel'):
        invalid('deliveryIdentity')
    if not isinstance(destination_ref, str) or not 1 <= len(destination_ref) <= 1000:
        invalid('destinationRef')
    return hashlib.sha256(json.dumps([event_id, channel, destination_ref], separators=(',', ':')).encode()).hexdigest()


def capabilities():
    # Auditado: factory registra SUCESSO/FALHA, não Warning nem geração de Clear.
    # Não usar contagem UI ou falha de transporte como autoridade de resultado.
    return {
        'result': {'available': False, 'source': 'etl_pipeline_execucao/factory',
                   'cause': 'Fonte legada sem Warning agregado e sem geração operacional confiável para reprocesso.'},
        'email': {'available': False, 'source': 'email_operator', 'cause': 'Transporte de tarefa existente; dispatcher de alertas previsto na F9/F10.'},
        'teamsPersonal': {'available': False, 'source': None, 'cause': 'Identidade corporativa, consentimento e provider ainda não certificados (F11).'},
        'teamsChannel': {'available': False, 'source': 'etl_msg_grupo', 'cause': 'Adapter de canal existente; cutover e dispatcher previstos na F9/F10.'},
    }


def preview(value, event):
    clean = policy(value)
    if event not in EVENTS:
        invalid('event')
    selected = event in clean['events']
    count = len(clean['recipients']) if selected else 0
    deliveries = []
    for channel in ('email', 'teamsPersonal'):
        if clean[channel]:
            deliveries.extend({'channel': channel, 'recipientIndex': index, 'state': 'preview_only'} for index in range(count))
    if clean['teamsChannel'] is not None and selected:
        deliveries.append({'channel': 'teamsChannel', 'state': 'preview_only'})
    return {'schemaVersion': 1, 'simulation': True, 'dispatch': False,
            'destinationResolution': 'not_checked',
            'policyContentRevision': revision(clean), 'event': event,
            'deliveries': deliveries, 'count': len(deliveries), 'capabilities': capabilities()}


def policy_for_run(pipeline, run):
    """Somente o vínculo imutável do run, inclusive após nova publicação."""
    from services.workspace_operations import execution_version
    try:
        snapshot = execution_version(pipeline, run)
    except Exception:
        raise HTTPException(503, {'code': 'alert_snapshot_unavailable', 'detail': 'Versão original da corrida indisponível; tente novamente.'}) from None
    if snapshot is None:
        raise HTTPException(409, {'code': 'alert_run_unbound', 'detail': 'Corrida sem versão original reconciliada; alertas indisponíveis.'})
    return captured_policy(snapshot['definition'], snapshot['versionId'])
