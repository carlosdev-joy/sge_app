from contextlib import contextmanager
from uuid import uuid4
from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from services import sla_recovery
from routers.sla_recovery import Recovery, recover_sla


def fixture(monkeypatch, previous=None, state='Unknown'):
    conn, cur = Mock(), Mock()
    cur.execute.return_value = cur
    cur.fetchone.side_effect = [(1, 1), (0,), previous, (state, '{"schemaVersion":1}')]
    @contextmanager
    def managed():
        yield conn, cur
    monkeypatch.setattr(sla_recovery, 'managed_conn', managed)
    return conn, cur


def test_unknown_requires_deliberate_confirmation_before_db(monkeypatch):
    connection = Mock()
    monkeypatch.setattr(sla_recovery, 'managed_conn', connection)
    with pytest.raises(HTTPException) as error:
        sla_recovery.recover(1, uuid4(), 'fixture', 'Unknown', 'manual_verification', False)
    assert error.value.status_code == 409
    connection.assert_not_called()


def test_recovery_reuses_original_payload_and_preserves_attempts(monkeypatch):
    conn, cur = fixture(monkeypatch)
    result = sla_recovery.recover(1, uuid4(), 'fixture', 'Unknown', 'manual_verification', True)
    assert result['created']
    writes = [call.args[0] for call in cur.execute.call_args_list]
    assert any('INSERT dbo.etl_sla_recovery' in sql for sql in writes)
    assert any("delivery_state='Pending'" in sql for sql in writes)
    assert all('SET intent_json' not in sql and 'DELETE' not in sql for sql in writes)
    conn.commit.assert_called_once()


def test_same_request_replay_is_noop_even_after_worker_consumes(monkeypatch):
    previous = (1, 'Unknown', 'fixture', 'manual_verification', True)
    conn, cur = fixture(monkeypatch, previous=previous)
    assert not sla_recovery.recover(1, uuid4(), 'fixture', 'Unknown', 'manual_verification', True)['created']
    assert not any('UPDATE' in call.args[0] for call in cur.execute.call_args_list)
    conn.commit.assert_called_once()


@pytest.mark.parametrize('previous', [(2, 'Unknown', 'fixture', 'manual_verification', True),
                                      (1, 'Unknown', 'another', 'manual_verification', True)])
def test_request_cannot_be_reused_for_different_identity(monkeypatch, previous):
    conn, _ = fixture(monkeypatch, previous=previous)
    with pytest.raises(HTTPException) as error:
        sla_recovery.recover(1, uuid4(), 'fixture', 'Unknown', 'manual_verification', True)
    assert error.value.status_code == 409
    conn.commit.assert_not_called()


@pytest.mark.parametrize('state', ['Sending', 'Pending', 'Accepted', 'Legacy', 'Failed'])
def test_stale_expected_state_never_changes_queue(monkeypatch, state):
    conn, _ = fixture(monkeypatch, state=state)
    with pytest.raises(HTTPException) as error:
        sla_recovery.recover(1, uuid4(), 'fixture', 'Unknown', 'manual_verification', True)
    assert error.value.status_code == 409
    conn.commit.assert_not_called()


def test_actor_comes_from_admin_context(monkeypatch):
    call = Mock(return_value={})
    monkeypatch.setattr('routers.sla_recovery.recover', call)
    request = Recovery(request_id=uuid4(), expected_state='Failed', reason='provider_restored')
    recover_sla(1, request, {'matricula': 'server_actor'})
    assert call.call_args.args[2] == 'server_actor'
    with pytest.raises(ValueError):
        Recovery(request_id=uuid4(), expected_state='Failed', reason='provider_restored', actor='forged')
