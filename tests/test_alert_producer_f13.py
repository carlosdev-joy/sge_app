"""Produtor não aceita envelope HTTP: consulta autoridade sob fence original."""
import json
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from services import alert_producer as producer
from services.alert_enrollment import snapshot
from services.pipeline_alerts import disabled_policy, captured_policy

P, R = '__eoc_f13_producer_pipeline', '__eoc_f13_producer_run'
V = str(uuid4())


def original():
    policy = disabled_policy()
    policy.update(events=['success', 'warning', 'failure'], recipients=['fixture@example.invalid'],
                  email=True, teamsPersonal=True, teamsChannel={'groupId': 17})
    encoded = snapshot(V, {'alertPolicy': policy}, expected_tasks=['job', 'end'],
                       processing_tasks=['job'], warning_sources={'job': 'end'})
    return encoded, captured_policy({'alertPolicy': policy}, V)


def observation(result='warning'):
    return dict(pipeline=P, run=R, processingResult=result,
                sourceAt='2026-10-14T12:00:00Z', warningEvidenceRequired=False)


def setup(monkeypatch, *, cycle=('key', 2, None), observed=None):
    stored, capture = original()
    conn = MagicMock()
    cur = conn.cursor.return_value
    cur.execute.return_value = cur
    cur.fetchall.return_value = []
    cur.fetchone.side_effect = [(1, 1, 1), stored]
    lock = MagicMock(return_value=cycle)
    monkeypatch.setattr(producer, 'locked_cycle', lock)
    read = AsyncMock(return_value=observation() if observed is None else observed)
    monkeypatch.setattr(producer, 'terminal_observation', read)
    return conn, cur, lock, read, capture


def inserts(cur):
    return [call for call in cur.execute.call_args_list if call.args[0].startswith('INSERT')]


@pytest.mark.asyncio
async def test_source_read_under_same_original_fence_and_atomic_fanout(monkeypatch):
    conn, cur, lock, read, capture = setup(monkeypatch)
    result = await producer.reconcile_terminal(MagicMock(), P, R, connection_factory=lambda: conn)
    assert result['created'] and result['count'] == 3 and result['dryRun']
    conn.commit.assert_called_once()
    lock.assert_called_once_with(cur, P, R)
    assert read.call_args.kwargs['warning_sources'] == {'job': 'end'}
    writes = inserts(cur)
    assert len(writes) == 4
    assert writes[0].args[1][2:7] == (capture['policyRevision'], P, R, 2, 'warning')
    assert [w.args[1][3] for w in writes[1:]] == ['email', 'teamsPersonal', 'teamsChannel']
    assert all('fixture@example.invalid' not in str(w.args) for w in writes)
    cur.close.assert_called_once()
    conn.close.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize('pending', ['Pending', 'Unknown'])
async def test_pending_clear_never_reads_or_produces(monkeypatch, pending):
    conn, cur, _, read, _ = setup(monkeypatch, cycle=('key', 2, pending))
    with pytest.raises(HTTPException) as error:
        await producer.reconcile_terminal(MagicMock(), P, R, connection_factory=lambda: conn)
    assert error.value.detail['code'] == 'alert_clear_pending'
    read.assert_not_called()
    conn.commit.assert_not_called()
    assert not inserts(cur)
    conn.close.assert_called_once()


@pytest.mark.asyncio
async def test_legacy_never_enrolled_by_polling(monkeypatch):
    conn, cur, _, read, _ = setup(monkeypatch, cycle=None)
    result = await producer.reconcile_terminal(MagicMock(), P, R, connection_factory=lambda: conn)
    assert result['reason'] == 'legacy'
    assert not inserts(cur)
    read.assert_not_called()


@pytest.mark.asyncio
async def test_inconclusive_does_not_create_false_success(monkeypatch):
    conn, cur, _, read, _ = setup(monkeypatch)
    read.return_value = None
    result = await producer.reconcile_terminal(MagicMock(), P, R, connection_factory=lambda: conn)
    assert result['reason'] == 'authority_inconclusive'
    assert not inserts(cur)


@pytest.mark.asyncio
async def test_read_failure_rolls_back_without_private_error(monkeypatch):
    conn, cur, _, read, _ = setup(monkeypatch)
    read.side_effect = RuntimeError('private-fixture-token')
    with pytest.raises(HTTPException) as error:
        await producer.reconcile_terminal(MagicMock(), P, R, connection_factory=lambda: conn)
    assert 'private-fixture-token' not in str(error.value.detail)
    conn.commit.assert_not_called()
    assert not inserts(cur)
    conn.close.assert_called_once()


@pytest.mark.asyncio
async def test_fanout_error_has_no_partial_commit(monkeypatch):
    conn, cur, _, _, _ = setup(monkeypatch)
    def execute(sql, params=None):
        if sql.startswith('INSERT dbo.etl_alert_intent'):
            raise RuntimeError('driver-private')
        return cur
    cur.execute.side_effect = execute
    with pytest.raises(HTTPException):
        await producer.reconcile_terminal(MagicMock(), P, R, connection_factory=lambda: conn)
    conn.commit.assert_not_called()
    conn.close.assert_called_once()


@pytest.mark.parametrize('result', ['success', 'warning', 'failure'])
def test_terminal_replay_no_new_intentions(result):
    cur = MagicMock(); cur.execute.return_value = cur
    _, capture = original()
    cur.fetchall.return_value = []
    first = producer.persist_observation(cur, P, R, 3, capture, observation(result))
    event_key = inserts(cur)[0].args[1][1]
    cur.reset_mock(); cur.execute.return_value = cur
    cur.fetchall.return_value = [(first['eventId'], event_key)]
    second = producer.persist_observation(cur, P, R, 3, capture, observation(result))
    assert second['created'] is False and not inserts(cur)


def test_changed_terminal_in_same_generation_requires_reconciliation():
    cur = MagicMock(); cur.execute.return_value = cur
    _, capture = original()
    cur.fetchall.return_value = [(str(uuid4()), 'different-event')]
    with pytest.raises(HTTPException) as error:
        producer.persist_observation(cur, P, R, 3, capture, observation('failure'))
    assert error.value.detail['code'] == 'alert_producer_terminal_changed'
    assert not inserts(cur)


@pytest.mark.parametrize('mutation', ['digest', 'warning-map', 'policy-revision'])
def test_original_snapshot_corruption_never_uses_current_policy(mutation):
    cur = MagicMock(); cur.execute.return_value = cur
    encoded, _ = original()
    if mutation == 'digest':
        row = (encoded[0], '0'*64)
    else:
        import hashlib
        doc = json.loads(encoded[0])
        if mutation == 'warning-map':
            doc.pop('warningSources')
        else:
            doc['policyRevision'] = 'other'
        raw = json.dumps(doc, sort_keys=True, separators=(',', ':'))
        row = (raw, hashlib.sha256(raw.encode()).hexdigest())
    cur.fetchone.return_value = row
    with pytest.raises(HTTPException):
        producer.original_snapshot(cur, 'key')
