"""Crash, ambiguidade e geração; nenhuma rede ou dado de cliente."""
from contextlib import contextmanager
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from services import alert_cycle as cycle

PIPELINE, RUN = '__eoc_f13_pipeline', '__eoc_f13_run'
KEY = cycle.run_key(PIPELINE, RUN)


def database(monkeypatch, *, generation=1, pending=None, enrolled=True, operation=None):
    conn, cur = MagicMock(), MagicMock()
    cur.execute.return_value = cur
    rows = [(1, 1), (0,), (PIPELINE, RUN, generation, pending) if enrolled else None]
    if operation is not None:
        rows.append(operation)
    cur.fetchone.side_effect = rows
    @contextmanager
    def managed():
        try:
            yield conn, cur
        finally:
            conn.close()
    monkeypatch.setattr(cycle, 'managed_conn', managed)
    return conn, cur


def mutations(cur):
    return [call.args for call in cur.execute.call_args_list
            if call.args[0].startswith(('INSERT', 'UPDATE'))]


def test_reservation_committed_before_caller_can_send(monkeypatch):
    conn, cur = database(monkeypatch)
    operation = cycle.begin_clear(PIPELINE, RUN)
    assert operation and len(mutations(cur)) == 2
    assert mutations(cur)[0][1] == (operation, KEY, 1)
    assert mutations(cur)[1][1] == (operation, KEY)
    conn.commit.assert_called_once()
    conn.close.assert_called_once()


def test_legacy_is_not_enrolled_or_backfilled(monkeypatch):
    conn, cur = database(monkeypatch, enrolled=False)
    assert cycle.begin_clear(PIPELINE, RUN) is None
    assert mutations(cur) == []


@pytest.mark.parametrize('generation', [1, 4, 2147483646])
@pytest.mark.parametrize('outcome,increment', [('Confirmed', 1), ('Rejected', 0), ('Unknown', 0)])
def test_finish_atomic_generation_and_unknown_keeps_fence(monkeypatch, generation, outcome, increment):
    operation = str(uuid4())
    conn, cur = database(monkeypatch, generation=generation, pending=operation,
                         operation=(KEY, generation, 'Pending'))
    assert cycle.finish_clear(PIPELINE, RUN, operation, outcome) == generation + increment
    writes = mutations(cur)
    assert writes[0][1] == (outcome, operation)
    if outcome == 'Unknown':
        assert len(writes) == 1  # pending_clear nunca é liberado por timeout.
    else:
        assert writes[1][1] == (generation + increment, KEY)
    conn.commit.assert_called_once()


def test_crash_pending_never_authorizes_second_post(monkeypatch):
    conn, cur = database(monkeypatch, pending=str(uuid4()))
    with pytest.raises(HTTPException) as error:
        cycle.begin_clear(PIPELINE, RUN)
    assert error.value.detail['code'] == 'alert_clear_pending'
    conn.commit.assert_not_called()
    assert mutations(cur) == []


@pytest.mark.parametrize('state,expected', [('Confirmed', 2), ('Rejected', 1)])
def test_replay_old_completion_does_not_clear_new_pending(monkeypatch, state, expected):
    operation = str(uuid4())
    conn, cur = database(monkeypatch, generation=7, pending=str(uuid4()),
                         operation=(KEY, 1, state))
    assert cycle.finish_clear(PIPELINE, RUN, operation, state) == expected
    assert mutations(cur) == []


@pytest.mark.parametrize('stored,outcome', [('Confirmed', 'Rejected'), ('Rejected', 'Confirmed')])
def test_contradictory_final_response_rejected(monkeypatch, stored, outcome):
    operation = str(uuid4())
    conn, cur = database(monkeypatch, operation=(KEY, 1, stored))
    with pytest.raises(HTTPException):
        cycle.finish_clear(PIPELINE, RUN, operation, outcome)
    assert mutations(cur) == []


@pytest.mark.parametrize('generation,pending,key', [(2, 'same', KEY), (1, 'other', KEY), (1, 'same', 'wrong')])
def test_stale_or_cross_run_cannot_advance_or_unlock(monkeypatch, generation, pending, key):
    operation = str(uuid4())
    conn, cur = database(monkeypatch, generation=generation,
                         pending=operation if pending == 'same' else str(uuid4()),
                         operation=(key, 1, 'Pending'))
    with pytest.raises(HTTPException):
        cycle.finish_clear(PIPELINE, RUN, operation, 'Confirmed')
    assert mutations(cur) == []
    conn.commit.assert_not_called()


def test_unknown_can_only_release_after_explicit_confirmation(monkeypatch):
    operation = str(uuid4())
    conn, cur = database(monkeypatch, pending=operation, operation=(KEY, 1, 'Unknown'))
    assert cycle.finish_clear(PIPELINE, RUN, operation, 'Confirmed') == 2
    assert len(mutations(cur)) == 2


def test_exhausted_generation_blocks_before_post(monkeypatch):
    conn, cur = database(monkeypatch, generation=2147483647)
    with pytest.raises(HTTPException):
        cycle.begin_clear(PIPELINE, RUN)
    assert mutations(cur) == []


@pytest.mark.parametrize('rows', [[(None, 1)], [(1, 1), (-1,)]])
def test_missing_schema_or_lock_timeout_no_writes(monkeypatch, rows):
    conn, cur = database(monkeypatch)
    cur.fetchone.side_effect = rows
    with pytest.raises(HTTPException) as error:
        cycle.begin_clear(PIPELINE, RUN)
    assert error.value.status_code == 503
    assert mutations(cur) == []


def test_partial_write_failure_never_commits_or_leaks(monkeypatch):
    conn, cur = database(monkeypatch)
    def execute(sql, *args):
        if sql.startswith('UPDATE'):
            raise RuntimeError('private-token')
        return cur
    cur.execute.side_effect = execute
    with pytest.raises(HTTPException) as error:
        cycle.begin_clear(PIPELINE, RUN)
    assert 'private' not in str(error.value.detail)
    conn.commit.assert_not_called()
    conn.close.assert_called_once()


@pytest.mark.parametrize('pipeline,run', [('', RUN), (PIPELINE, '\ud800'), ('x' * 201, RUN), (PIPELINE, 'a\n')])
def test_bad_identity_fails_without_driver_data(pipeline, run):
    with pytest.raises(HTTPException):
        cycle.run_key(pipeline, run)


def test_identity_preserves_case_and_delimiters():
    assert cycle.run_key('a:b', 'c') != cycle.run_key('a', 'b:c')
    assert cycle.run_key('A', RUN) != cycle.run_key('a', RUN)


def test_original_validation_and_reservation_share_lock_until_commit(monkeypatch):
    from services import alert_enrollment
    conn, cur = database(monkeypatch)
    events = []
    definition = {'original': True}
    def validate(cursor, pipeline, run, version, document):
        assert cursor is cur
        assert (pipeline, run, version, document) == (PIPELINE, RUN, 'version', definition)
        assert mutations(cur) == []
        conn.commit.assert_not_called()
        events.append('validated')
    monkeypatch.setattr(alert_enrollment, 'validate_reprocess_snapshot', validate)
    conn.commit.side_effect = lambda: events.append('committed')
    operation = cycle.begin_reprocess_clear(PIPELINE, RUN, 'version', definition)
    assert events == ['validated', 'committed']
    assert mutations(cur)[0][1] == (operation, KEY, 1)


@pytest.mark.parametrize('code', ['alert_enrollment_original_conflict', 'alert_clear_pending'])
def test_original_snapshot_failure_never_reserves_or_commits(monkeypatch, code):
    from services import alert_enrollment
    conn, cur = database(monkeypatch)
    def invalid(*args):
        raise cycle.conflict(code)
    monkeypatch.setattr(alert_enrollment, 'validate_reprocess_snapshot', invalid)
    with pytest.raises(HTTPException) as error:
        cycle.begin_reprocess_clear(PIPELINE, RUN, 'version', {})
    assert error.value.detail['code'] == code
    assert mutations(cur) == []
    conn.commit.assert_not_called()
    conn.close.assert_called_once()


def test_reprocess_legacy_cannot_gain_clear_fence(monkeypatch):
    conn, cur = database(monkeypatch, enrolled=False)
    with pytest.raises(HTTPException) as error:
        cycle.begin_reprocess_clear(PIPELINE, RUN, 'version', {})
    assert error.value.detail['code'] == 'alert_enrollment_legacy_replay'
    assert mutations(cur) == []
    conn.commit.assert_not_called()


def test_concurrent_pending_blocks_original_validation_and_writes(monkeypatch):
    from services import alert_enrollment
    conn, cur = database(monkeypatch, pending=str(uuid4()))
    validator = MagicMock()
    monkeypatch.setattr(alert_enrollment, 'validate_reprocess_snapshot', validator)
    with pytest.raises(HTTPException) as error:
        cycle.begin_reprocess_clear(PIPELINE, RUN, 'version', {})
    assert error.value.detail['code'] == 'alert_clear_pending'
    validator.assert_not_called()
    assert mutations(cur) == []
    conn.commit.assert_not_called()


def test_send_claim_persists_unknown_before_network_permission(monkeypatch):
    operation = str(uuid4())
    conn, cur = database(monkeypatch, pending=operation, operation=(KEY, 1, 'Pending'))
    cycle.claim_clear_send(PIPELINE, RUN, operation)
    assert len(mutations(cur)) == 1
    assert "state='Unknown'" in mutations(cur)[0][0]
    assert mutations(cur)[0][1] == (operation,)
    conn.commit.assert_called_once()


@pytest.mark.parametrize('state', ['Unknown', 'Confirmed', 'Rejected'])
def test_send_claim_replay_never_authorizes_second_send(monkeypatch, state):
    operation = str(uuid4())
    conn, cur = database(monkeypatch, pending=operation, operation=(KEY, 1, state))
    with pytest.raises(HTTPException) as error:
        cycle.claim_clear_send(PIPELINE, RUN, operation)
    assert error.value.detail['code'] == 'alert_clear_already_sent'
    assert mutations(cur) == []
    conn.commit.assert_not_called()


@pytest.mark.parametrize('key,base,pending', [('other', 1, True), (KEY, 2, True), (KEY, 1, False)])
def test_send_claim_foreign_generation_or_operation_is_fenced(monkeypatch, key, base, pending):
    operation = str(uuid4())
    conn, cur = database(monkeypatch, pending=operation if pending else str(uuid4()),
                         operation=(key, base, 'Pending'))
    with pytest.raises(HTTPException):
        cycle.claim_clear_send(PIPELINE, RUN, operation)
    assert mutations(cur) == []
    conn.commit.assert_not_called()
