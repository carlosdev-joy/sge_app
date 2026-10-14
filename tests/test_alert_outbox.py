"""Contrato F9A: nenhum envelope de cliente autoriza emissão."""
import json
from contextlib import contextmanager
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from services import alert_outbox as outbox
from services.pipeline_alerts import captured_policy, disabled_policy


def fixture():
    policy = disabled_policy()
    policy.update(events=['failure'], recipients=['fixture@example.invalid'], email=True,
                  teamsPersonal=True, teamsChannel={'groupId': 1})
    version = str(uuid4())
    definition = {'alertPolicy': policy}
    capture = captured_policy(definition, version)
    event = dict(schemaVersion=1, pipeline='__eoc_f9_pipeline', run='__eoc_f9_run', cycleGeneration=1,
                 event='failure', policyRevision=capture['policyRevision'], source='eoc-f9-fixture',
                 sourceStatus='FAILED', sourceAt='2026-10-14T10:00:00Z', receivedAt='2026-10-14T10:00:01Z')
    return version, definition, capture, event


def test_gate_never_accepts_client_authority():
    with pytest.raises(HTTPException) as error:
        outbox.enqueue_result({'authoritative': True})
    assert error.value.status_code == 503
    assert error.value.detail['code'] == 'alert_authority_unavailable'


@pytest.mark.parametrize('field,value', [('pipeline', 'customer'), ('run', 'customer'), ('source', 'factory')])
def test_dry_run_refuses_non_fixture_before_db(monkeypatch, field, value):
    *_, event = fixture()
    event[field] = value
    db = MagicMock()
    monkeypatch.setattr(outbox, 'managed_conn', db)
    with pytest.raises(HTTPException) as error:
        outbox.enqueue_dry_run(event)
    assert error.value.status_code == 409
    db.assert_not_called()


def test_reference_fanout_and_no_private_data():
    _, definition, capture, event = fixture()
    refs = outbox.destinations(capture, 'failure')
    assert len(refs) == len(set(refs)) == 3
    assert '@' not in json.dumps(refs)
    assert outbox.destinations(capture, 'success') == []
    definition['alertPolicy']['recipients'].append('second@example.invalid')
    capture = captured_policy(definition, str(uuid4()))
    assert len(outbox.destinations(capture, 'failure')) == 5


def db_fixture(monkeypatch, *, previous=None, fail_insert=False):
    version, definition, capture, event = fixture()
    conn, cur = MagicMock(), MagicMock()
    conn.cursor.return_value = cur
    cur.execute.return_value = cur
    cur.fetchone.side_effect = [(1, 2, 3), (version, json.dumps(definition)), (0,), previous]
    if fail_insert:
        def execute(sql, *args):
            if 'INSERT dbo.etl_alert_intent' in sql:
                raise RuntimeError('private-connection-string')
            return cur
        cur.execute.side_effect = execute
    @contextmanager
    def managed():
        try:
            yield conn, cur
        finally:
            conn.close()
    monkeypatch.setattr(outbox, 'managed_conn', managed)
    return conn, cur, event


def test_commit_once_after_all_intents(monkeypatch):
    conn, cur, event = db_fixture(monkeypatch)
    result = outbox.enqueue_dry_run(event)
    assert result['created'] and result['count'] == 3 and result['dryRun']
    assert sum('INSERT dbo.etl_alert_intent' in call.args[0] for call in cur.execute.call_args_list) == 3
    conn.commit.assert_called_once()
    conn.close.assert_called_once()


def test_replay_never_adds_intents(monkeypatch):
    conn, cur, event = db_fixture(monkeypatch, previous=(str(uuid4()),))
    assert not outbox.enqueue_dry_run(event)['created']
    assert not any('INSERT' in call.args[0] for call in cur.execute.call_args_list)


def test_partial_fanout_failure_never_commits_and_is_sanitized(monkeypatch):
    conn, cur, event = db_fixture(monkeypatch, fail_insert=True)
    with pytest.raises(HTTPException) as error:
        outbox.enqueue_dry_run(event)
    conn.commit.assert_not_called()
    conn.close.assert_called_once()
    assert error.value.status_code == 503
    assert 'private' not in str(error.value.detail)


def test_wrong_original_revision_fails_closed(monkeypatch):
    conn, cur, event = db_fixture(monkeypatch)
    event['policyRevision'] = str(uuid4()) + ':' + '0' * 64
    with pytest.raises(HTTPException) as error:
        outbox.enqueue_dry_run(event)
    assert error.value.detail['code'] == 'alert_revision_conflict'
    conn.commit.assert_not_called()


def test_schema_missing_names_migration():
    cur = MagicMock()
    cur.execute.return_value.fetchone.return_value = (1, None, 3)
    with pytest.raises(HTTPException) as error:
        outbox.require_schema(cur)
    assert error.value.status_code == 503 and '179_' in error.value.detail['detail']


def test_lock_timeout_never_inserts_or_commits(monkeypatch):
    conn, cur, event = db_fixture(monkeypatch)
    version, definition, _, _ = fixture()
    event['policyRevision'] = captured_policy(definition, version)['policyRevision']
    cur.fetchone.side_effect = [(1, 2, 3), (version, json.dumps(definition)), (-1,)]
    with pytest.raises(HTTPException) as error:
        outbox.enqueue_dry_run(event)
    assert error.value.status_code == 503
    conn.commit.assert_not_called()
    assert not any('INSERT' in call.args[0] for call in cur.execute.call_args_list)
