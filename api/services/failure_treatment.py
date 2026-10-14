"""Adapter transacional sobre etl_failure_ack; efeitos de comunicação após commit."""
from __future__ import annotations

from datetime import datetime, timezone
import re
from urllib.parse import urlencode
from fastapi import HTTPException
from services.ssh_arquivos import cortar_utf16


def text(body, key, maximum, required=False):
    value = body.get(key)
    if value is None and not required:
        return None
    if not isinstance(value, str):
        raise HTTPException(422, f'{key}: informe um texto válido')
    value = value.strip()
    try:
        size = len(value.encode('utf-16-le')) // 2
    except UnicodeError:
        raise HTTPException(422, f'{key}: texto inválido')
    if size > maximum or any(ord(c) < 32 and c not in '\n\t' for c in value):
        raise HTTPException(422, f'{key}: texto inválido ou muito longo')
    if required and not value:
        raise HTTPException(422, f'{key} é obrigatório')
    return value or None


def identity(body):
    # Chaves legadas são VARCHAR: recusar unicode para não convertê-lo para '?'.
    pair = (text(body, 'execution_id', 100, True), text(body, 'pipeline', 200, True))
    if any(not value.isascii() or any(ord(c) < 32 for c in value) for value in pair):
        raise HTTPException(422, 'Identidade de execução inválida')
    return pair


def actor(auth):
    user = text(auth, 'matricula', 64, True)
    name = ' '.join(str(auth.get(k) or '').strip() for k in ('primeiro_nome', 'ultimo_nome')).strip()
    return user, cortar_utf16(name or user, 200)


def ready(cur):
    cur.execute("SELECT CASE WHEN OBJECT_ID('dbo.etl_failure_ack_history','U') IS NOT NULL "
                "AND COL_LENGTH('dbo.etl_failure_ack','priority') IS NOT NULL "
                "AND COL_LENGTH('dbo.etl_failure_ack','treatment_version') IS NOT NULL THEN 1 ELSE 0 END")
    row = cur.fetchone()
    if not row or not row[0]:
        raise HTTPException(503, 'Tratamento indisponível: aplique a migration 186')


def exact_link(eid, pipeline):
    return '/logs?' + urlencode({'execution_id': eid, 'pipeline': pipeline, 'exact': '1'})


def mutate(cur, body, auth, action):
    eid, pipeline = identity(body)
    user, name = actor(auth)
    note = text(body, 'resolution_note' if action == 'resolve' else 'note', 500)
    ticket = text(body, 'snow_ticket', 64)
    remove = body.get('remove', False)
    if type(remove) is not bool:
        raise HTTPException(422, 'remove deve ser booleano')
    priority = body.get('priority', 'normal')
    if priority not in ('baixa', 'normal', 'alta', 'critica'):
        raise HTTPException(422, 'Prioridade inválida')
    ready(cur)
    # Serializa inclusive ausência da chave usando o índice único legado.
    cur.execute('SELECT ack_by, display_name, ack_at, resolved_by, resolved_display_name, '
                'resolved_at, resolution_note, snow_ticket, priority, treatment_version FROM dbo.etl_failure_ack '
                'WITH (UPDLOCK,HOLDLOCK) WHERE execution_id=? AND pipeline=?', (eid, pipeline))
    row = cur.fetchone()
    cur.execute("SELECT TOP 1 1 FROM dbo.etl_job_execution WHERE execution_id=? AND pipeline=? AND status='FAILED'", (eid, pipeline))
    if not cur.fetchone():
        # Nenhum fallback para run recente ou pipeline publicado.
        raise HTTPException(409, 'Ocorrência sem falha exata conhecida; não foi redirecionada')
    if row and row[0] != user:
        raise HTTPException(409, 'Ocorrência já assumida por outro responsável')
    if row and action != 'priority':
        priority = row[8]
    previous_version = bytes(row[9]) if row else None
    expected = body.get('expectedVersion')
    if expected is not None and (not isinstance(expected, str) or not re.fullmatch(r'[0-9a-f]{16}', expected)):
        raise HTTPException(422, 'expectedVersion inválida')
    if action == 'priority' and 'expectedVersion' not in body:
        raise HTTPException(422, 'expectedVersion é obrigatória para priorizar')
    # Consumidores legados continuam compatíveis. Clientes versionados enviam
    # null para ausência; repetição sem delta mantém idempotência, mesmo stale.
    repeat = ((action == 'ack' and not remove and row is not None)
              or (action == 'ack' and remove and row is None)
              or (action == 'resolve' and remove and (not row or row[5] is None))
              or (action == 'resolve' and not remove and row is not None
                  and row[5] is not None and row[6] == note and row[7] == ticket)
              or (action == 'priority' and row is not None and row[8] == priority))
    if 'expectedVersion' in body and expected != (previous_version.hex() if previous_version else None) and not repeat:
        raise HTTPException(409, 'Ocorrência alterada; atualize a lista antes de tratar')
    changed = False
    event = action
    if action == 'ack':
        if remove:
            if row and row[5] is not None:
                raise HTTPException(409, 'Desfaça a resolução antes de remover a assunção')
            if row:
                cur.execute('DELETE FROM dbo.etl_failure_ack WHERE execution_id=? AND pipeline=?', (eid, pipeline))
                changed, event = True, 'release'
        elif not row:
            cur.execute('INSERT dbo.etl_failure_ack(execution_id,pipeline,ack_by,display_name,note,priority) VALUES(?,?,?,?,?,?)',
                        (eid, pipeline, user, name, note, priority))
            changed = True
    elif action == 'resolve':
        if remove:
            if row and row[5] is not None:
                cur.execute('UPDATE dbo.etl_failure_ack SET resolved_by=NULL,resolved_display_name=NULL,resolved_at=NULL,resolution_note=NULL,snow_ticket=NULL WHERE execution_id=? AND pipeline=?', (eid, pipeline))
                changed, event = True, 'reopen'
        elif not row or row[5] is None:
            if not row:
                cur.execute('INSERT dbo.etl_failure_ack(execution_id,pipeline,ack_by,display_name,priority) VALUES(?,?,?,?,?)', (eid, pipeline, user, name, priority))
            cur.execute('UPDATE dbo.etl_failure_ack SET resolved_by=?,resolved_display_name=?,resolved_at=GETDATE(),resolution_note=?,snow_ticket=? WHERE execution_id=? AND pipeline=?', (user, name, note, ticket, eid, pipeline))
            changed = True
        elif row[6] != note or row[7] != ticket:
            raise HTTPException(409, 'Resolução já registrada; reabra antes de alterá-la')
    elif action == 'priority':
        if not row or row[5] is not None:
            raise HTTPException(409, 'Assuma uma ocorrência aberta antes de priorizá-la')
        if row[8] != priority:
            cur.execute('UPDATE dbo.etl_failure_ack SET priority=? WHERE execution_id=? AND pipeline=?', (priority, eid, pipeline))
            changed = True
    else:
        raise ValueError('ação de tratamento desconhecida')
    if changed:
        cur.execute('INSERT dbo.etl_failure_ack_history(execution_id,pipeline,action,actor,display_name,note,snow_ticket,priority,previous_version) VALUES(?,?,?,?,?,?,?,?,?)', (eid, pipeline, event, user, name, note, ticket, priority, previous_version))
    cur.execute('SELECT ack_by,display_name,ack_at,resolved_by,resolved_display_name,resolved_at,resolution_note,snow_ticket,priority,treatment_version FROM dbo.etl_failure_ack WHERE execution_id=? AND pipeline=?', (eid, pipeline))
    current = cur.fetchone()
    keys = ('ack_by', 'display_name', 'ack_at', 'resolved_by', 'resolved_display_name', 'resolved_at', 'resolution_note', 'snow_ticket', 'priority', 'version')
    result = dict(zip(keys, current)) if current else {}
    if current:
        result['version'] = bytes(current[9]).hex()
    for key in ('ack_at', 'resolved_at'):
        if isinstance(result.get(key), datetime):
            result[key] = result[key].isoformat()
    return dict(ok=True, action=event, changed=changed, execution_id=eid, pipeline=pipeline,
                note=note, processing_status='FAILED',
                communication_status='independente', execution_link=exact_link(eid, pipeline), **result)


def history(cur, eid, pipeline):
    ready(cur)
    cur.execute('SELECT TOP 200 id,action,actor,display_name,created_at,note,snow_ticket,priority,previous_version FROM dbo.etl_failure_ack_history WHERE execution_id=? AND pipeline=? ORDER BY id DESC', (eid, pipeline))
    keys = ('id', 'action', 'actor', 'display_name', 'created_at', 'note', 'snow_ticket', 'priority', 'previous_version')
    result = [dict(zip(keys, row)) for row in cur.fetchall()]
    for item in result:
        if item['previous_version'] is not None:
            item['previous_version'] = bytes(item['previous_version']).hex()
        if isinstance(item['created_at'], datetime):
            item['created_at'] = item['created_at'].replace(tzinfo=timezone.utc).isoformat()
    return result
