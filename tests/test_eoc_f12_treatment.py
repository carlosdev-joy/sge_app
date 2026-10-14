"""F12: tratamento independente, ator servidor e identidade sem retarget."""
import asyncio
from datetime import datetime
import pytest
from fastapi import HTTPException
from services import failure_treatment as t
from routers import execucoes as r

AUTH = dict(matricula='operador', primeiro_nome='Nome', ultimo_nome='Servidor')
BODY = dict(execution_id='run_1', pipeline='pipe_1', user='forjado', display_name='Forjado')


class Cursor:
    def __init__(self, row=None, exists=True, ready=True):
        self.row, self.exists, self.ready = row, exists, ready
        self.calls = []
        self.last = ''

    def execute(self, sql, params=()):
        self.calls.append((sql, params)); self.last = sql
        if sql.startswith('INSERT dbo.etl_failure_ack('):
            self.row = [params[2], params[3], datetime(2026, 10, 14), None, None, None, None, None, params[-1], b'\x00'*7+b'\x01']
        elif sql.startswith('DELETE FROM dbo.etl_failure_ack'):
            self.row = None
        elif sql.startswith('UPDATE dbo.etl_failure_ack SET resolved_by=?'):
            self.row[3:8] = [params[0], params[1], datetime(2026, 10, 14), params[2], params[3]]
        elif sql.startswith('UPDATE dbo.etl_failure_ack SET resolved_by=NULL'):
            self.row[3:8] = [None]*5
        elif sql.startswith('UPDATE dbo.etl_failure_ack SET priority'):
            self.row[8] = params[0]
        if sql.startswith('UPDATE dbo.etl_failure_ack'):
            self.row[9] = (int.from_bytes(self.row[9], 'big')+1).to_bytes(8, 'big')
        return self

    def fetchone(self):
        if self.last.startswith('SELECT CASE'): return (int(self.ready),)
        if self.last.startswith('SELECT TOP 1 1'): return (1,) if self.exists else None
        return self.row


def test_actor_is_server_and_ack_is_idempotent_without_transport():
    c = Cursor()
    first = t.mutate(c, BODY, AUTH, 'ack')
    second = t.mutate(c, BODY, AUTH, 'ack')
    assert first['ack_by'] == 'operador' and first['display_name'] == 'Nome Servidor'
    assert first['changed'] and not second['changed']
    assert len([sql for sql, _ in c.calls if sql.startswith('INSERT dbo.etl_failure_ack_history')]) == 1
    assert not any('UPDATE dbo.etl_job_execution' in sql for sql, _ in c.calls)
    assert 'WITH (UPDLOCK,HOLDLOCK)' in c.calls[1][0]


def test_conflicting_owner_is_409():
    c = Cursor(['outro', 'Outro', None, None, None, None, None, None, 'normal', b'\x00'*7+b'\x01'])
    with pytest.raises(HTTPException) as e: t.mutate(c, BODY, AUTH, 'ack')
    assert e.value.status_code == 409
    assert not any(sql.startswith(('INSERT', 'UPDATE')) for sql, _ in c.calls)


def test_unknown_legacy_does_not_retarget():
    c = Cursor(exists=False)
    with pytest.raises(HTTPException) as e: t.mutate(c, BODY, AUTH, 'resolve')
    assert e.value.status_code == 409
    assert c.calls[-1][1] == ('run_1', 'pipe_1')
    assert not any('LIKE' in sql or sql.startswith('INSERT') for sql, _ in c.calls)


def test_resolve_keeps_failed_and_preserves_original_resolution():
    c = Cursor()
    result = t.mutate(c, {**BODY, 'resolution_note': 'corrigido'}, AUTH, 'resolve')
    assert result['processing_status'] == 'FAILED' and result['communication_status'] == 'independente'
    assert not t.mutate(c, {**BODY, 'resolution_note': 'corrigido'}, AUTH, 'resolve')['changed']
    with pytest.raises(HTTPException) as e: t.mutate(c, {**BODY, 'resolution_note': 'alterar'}, AUTH, 'resolve')
    assert e.value.status_code == 409
    with pytest.raises(HTTPException) as e: t.mutate(c, {**BODY, 'remove': True}, AUTH, 'ack')
    assert e.value.status_code == 409
    assert t.mutate(c, {**BODY, 'remove': True}, AUTH, 'resolve')['changed']
    assert t.mutate(c, {**BODY, 'remove': True}, AUTH, 'ack')['changed']
    assert len([sql for sql, _ in c.calls if sql.startswith('INSERT dbo.etl_failure_ack_history')]) == 3


@pytest.mark.parametrize('field,value', [('execution_id', 123), ('pipeline', {}), ('execution_id', 'a'*101), ('pipeline', 'á'), ('note', '😀'*251), ('remove', 'false'), ('priority', ['alta'])])
def test_validation(field, value):
    with pytest.raises(HTTPException) as e: t.mutate(Cursor(), {**BODY, field: value}, AUTH, 'ack')
    assert e.value.status_code == 422


def test_migration_absent_503():
    with pytest.raises(HTTPException) as e: t.mutate(Cursor(ready=False), BODY, AUTH, 'ack')
    assert e.value.status_code == 503 and '186' in e.value.detail


def test_priority_requires_owner_and_open_occurrence():
    c = Cursor()
    with pytest.raises(HTTPException) as e: t.mutate(c, {**BODY, 'priority': 'alta', 'expectedVersion': c.row[9].hex() if c.row else None}, AUTH, 'priority')
    assert e.value.status_code == 409
    t.mutate(c, BODY, AUTH, 'ack')
    assert t.mutate(c, {**BODY, 'priority': 'alta', 'expectedVersion': c.row[9].hex() if c.row else None}, AUTH, 'priority')['priority'] == 'alta'
    assert not t.mutate(c, {**BODY, 'priority': 'alta', 'expectedVersion': c.row[9].hex() if c.row else None}, AUTH, 'priority')['changed']
    t.mutate(c, BODY, AUTH, 'resolve')
    history = [params for sql, params in c.calls if sql.startswith('INSERT dbo.etl_failure_ack_history')]
    assert history[-1][-2] == 'alta'


def test_exact_link_escapes_identity():
    from urllib.parse import parse_qs, urlsplit
    link = t.exact_link('run&2', 'pipe%_1')
    assert parse_qs(urlsplit(link).query) == dict(execution_id=['run&2'], pipeline=['pipe%_1'], exact=['1'])


def test_bulk_rolls_back_conflict_and_closes(monkeypatch):
    class Connection:
        rolled = closed = committed = False
        def cursor(self): return self
        def rollback(self): self.rolled = True
        def commit(self): self.committed = True
        def close(self): self.closed = True
    c = Connection(); monkeypatch.setattr(r, 'get_db_conn', lambda: c)
    seen = []
    def mutate(cur, body, auth, action):
        seen.append(body['execution_id'])
        if len(seen) == 2: raise HTTPException(409, 'conflito')
        return dict(changed=True)
    monkeypatch.setattr(t, 'mutate', mutate)
    with pytest.raises(HTTPException) as e:
        r._treat_bulk(dict(items=[dict(BODY, execution_id='b'), dict(BODY, execution_id='a')]), AUTH, 'resolve')
    assert e.value.status_code == 409 and c.rolled and c.closed and not c.committed
    assert seen == ['a', 'b']


def test_first_change_notifies_once_and_repeat_does_not(monkeypatch):
    c = Cursor(); sent = []
    monkeypatch.setattr(r, '_teams_ack_card', lambda **kw: sent.append(('ack', kw)))
    monkeypatch.setattr(r, '_teams_resolved_card', lambda **kw: sent.append(('resolve', kw)))
    monkeypatch.setattr(r, 'add_notificacao', lambda *args: sent.append(('personal', args)))
    monkeypatch.setattr(r, '_treat_failure', lambda body, auth, action: t.mutate(c, body, auth, action))
    assert asyncio.run(r.ack_failure(BODY, AUTH))['ok']
    assert len(sent) == 2 and sent[0][1]['ack_by'] == AUTH['matricula']
    asyncio.run(r.ack_failure(BODY, AUTH)); assert len(sent) == 2
    asyncio.run(r.resolve_failure(BODY, AUTH)); assert len(sent) == 4
    asyncio.run(r.resolve_failure(BODY, AUTH)); assert len(sent) == 4
    asyncio.run(r.resolve_failure({**BODY, 'remove': True}, AUTH)); assert len(sent) == 4


def test_two_tabs_of_same_owner_conflict_on_stale_priority():
    c = Cursor(); first = t.mutate(c, BODY, AUTH, 'ack')
    first_change = t.mutate(c, {**BODY, 'priority': 'alta', 'expectedVersion': first['version']}, AUTH, 'priority')
    with pytest.raises(HTTPException) as e:
        t.mutate(c, {**BODY, 'priority': 'critica', 'expectedVersion': first['version']}, AUTH, 'priority')
    assert e.value.status_code == 409 and first_change['version'] != first['version']
    assert t.mutate(c, {**BODY, 'priority': 'alta', 'expectedVersion': first['version']}, AUTH, 'priority')['changed'] is False


def test_changed_bulk_summary_after_commit_only(monkeypatch):
    calls = []
    one = t.mutate(Cursor(), BODY, AUTH, 'ack')
    two = {**one, 'execution_id': 'run_2', 'changed': False}
    monkeypatch.setattr(r, '_treat_bulk', lambda *args: dict(ok=True, acked=1, results=[one, two]))
    monkeypatch.setattr(r, '_teams_ack_card', lambda **kw: calls.append(kw))
    monkeypatch.setattr(r, 'add_notificacao', lambda *args: calls.append(args))
    result = asyncio.run(r.ack_failures_bulk(dict(items=[BODY]), AUTH))
    assert len(calls) == 2 and calls[0]['itens'] == ['pipe_1'] and 'results' not in result



def test_server_long_name_and_history_utc():
    user, name = t.actor(dict(AUTH, primeiro_nome='A'*100, ultimo_nome='B'*100))
    assert user == 'operador' and len(name.encode('utf-16-le')) // 2 == 200
    class HistoryCursor(Cursor):
        def fetchall(self):
            return [(1, 'ack', 'operador', name, datetime(2026, 10, 14, 12), None, None, 'alta', None)]
    assert t.history(HistoryCursor(), 'run_1', 'pipe_1')[0]['created_at'] == '2026-10-14T12:00:00+00:00'
