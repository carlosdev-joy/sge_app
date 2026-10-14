"""F9B: limites, estado incerto, fence e lifecycle (SQL real no smoke)."""
import asyncio
from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest
from services import alert_dispatcher as d


@pytest.mark.parametrize('response,sequence,expected', [
    (None, 1, ('DryRun', None, None, None)),
    (d.MockResponse(200), 1, ('Accepted', None, None, None)),
    (d.MockResponse(timeout=True), 1, ('Unknown', 'mock_timeout', None, None)),
    (d.MockResponse(500), 1, ('Failed', 'mock_500', None, 30)),
    (d.MockResponse(500), 4, ('Failed', 'mock_500', None, None)),
    (d.MockResponse(429, 90), 2, ('Failed', 'mock_429', 90, 90)),
    (d.MockResponse(429, 10**20), 1, ('Failed', 'mock_429', 86400, 86400)),
    (d.MockResponse(400), 1, ('Failed', 'mock_rejected', None, None)),
])
def test_outcomes(response, sequence, expected):
    assert d.classify(response, sequence) == expected


@pytest.mark.parametrize('value', [None, 'secret-token', 'NaN', float('inf'), -1, {}])
def test_retry_after_invalid_is_not_persisted(value):
    assert d.classify(d.MockResponse(429, value), 1) == ('Failed', 'mock_429', None, 30)


def test_no_transport_callback():
    with pytest.raises(ValueError):
        d.classify(lambda: 'real send', 1)


def fake_db(monkeypatch, row, *, fail_attempt=False):
    conn, cur = MagicMock(), MagicMock()
    conn.cursor.return_value = cur
    cur.execute.return_value = cur
    cur.fetchone.side_effect = [(1, 2, 3), row]
    cur.rowcount = 1
    if fail_attempt:
        def execute(sql, *args):
            if 'INSERT dbo.etl_alert_attempt' in sql:
                raise RuntimeError('private driver error')
            return cur
        cur.execute.side_effect = execute
    @contextmanager
    def managed():
        try:
            yield conn, cur
        finally:
            conn.close()
    monkeypatch.setattr(d, 'managed_conn', managed)
    return conn, cur


def test_failed_attempt_insert_never_commits(monkeypatch):
    conn, _ = fake_db(monkeypatch, ('id', 0), fail_attempt=True)
    with pytest.raises(RuntimeError):
        d.claim_one()
    conn.commit.assert_not_called()
    conn.close.assert_called_once()


def test_stale_ack_never_updates_attempt_or_intent(monkeypatch):
    _, cur = fake_db(monkeypatch, None)
    assert not d.finish({'intentId': 'id', 'leaseToken': 'old', 'sequence': 1}, d.MockResponse(200))
    assert not any('UPDATE' in c.args[0] for c in cur.execute.call_args_list)


@pytest.mark.parametrize('outcome,code', [
    ('Failed', 'teams_forbidden'), ('Failed', 'teams_throttled'),
    ('Unknown', 'teams_transport_uncertain'), ('Failed', 'invalid_message'),
])
def test_personal_result_persisted_without_retry(monkeypatch, outcome, code):
    conn, cur = fake_db(monkeypatch, ('id',))
    cur.rowcount = 1
    assert d.finish_result({'intentId': 'id', 'leaseToken': 'current', 'sequence': 1},
                           outcome, code)
    updates = [call for call in cur.execute.call_args_list if 'UPDATE' in call.args[0]]
    assert updates[0].args[1][:2] == (outcome, code)
    assert updates[1].args[1][0] == outcome
    conn.commit.assert_called_once()


def test_stale_claim_never_resolves_adapter(monkeypatch):
    from services import alert_channels
    fake_db(monkeypatch, None)
    adapter = MagicMock()
    monkeypatch.setattr(alert_channels, 'deliver', adapter)
    assert not d.dispatch_claim({'intentId': 'id', 'leaseToken': 'old', 'sequence': 1})
    adapter.assert_not_called()


def test_adapter_result_persisted_after_commit_and_always_dry_run(monkeypatch):
    from services import alert_channels
    conn, _ = fake_db(monkeypatch, ('id',))
    adapter = MagicMock(return_value=alert_channels.Result('Failed', 'invalid_destination'))
    monkeypatch.setattr(alert_channels, 'deliver', adapter)
    claim = {'intentId': 'id', 'leaseToken': 'current', 'sequence': 1}
    def finish(*args):
        conn.commit.assert_called_once()
        assert args == (claim, 'Failed', 'invalid_destination')
        return True
    monkeypatch.setattr(d, 'finish_result', finish)
    assert d.dispatch_claim(claim)
    adapter.assert_called_once()
    assert adapter.call_args.kwargs == {'dry_run': True}


@pytest.mark.parametrize('outcome,code,retry,delay', [
    ('Pending', None, None, None),
    ('Failed', 'private-token', None, None),
    ('Unknown', None, None, 30),
    ('Failed', None, True, 30),
    ('Failed', None, None, -1),
])
def test_invalid_result_rejected_before_sql(monkeypatch, outcome, code, retry, delay):
    db = MagicMock()
    monkeypatch.setattr(d, 'bounded_conn', db)
    with pytest.raises(ValueError):
        d.finish_result({}, outcome, code, retry, delay)
    db.assert_not_called()


def test_flag_off_no_sql(monkeypatch):
    monkeypatch.delenv('EOC_ALERT_DISPATCHER_DRY_RUN', raising=False)
    run = MagicMock()
    monkeypatch.setattr(d, 'dispatch_once', run)
    asyncio.run(d.reconcile_loop())
    run.assert_not_called()


def test_shutdown_waits_for_inflight_sql(monkeypatch):
    import threading
    started, release, finished = threading.Event(), threading.Event(), threading.Event()
    def work():
        started.set()
        assert release.wait(5)
        finished.set()
    monkeypatch.setenv('EOC_ALERT_DISPATCHER_DRY_RUN', '1')
    monkeypatch.setattr(d, 'dispatch_once', work)
    async def check():
        task = asyncio.create_task(d.reconcile_loop())
        while not started.is_set():
            await asyncio.sleep(.001)
        task.cancel()
        await asyncio.sleep(.01)
        assert not task.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert finished.is_set()
    asyncio.run(check())


def test_cohort_dispatch_is_explicit_dry_run_opt_in(monkeypatch):
    monkeypatch.delenv('EOC_ALERT_DISPATCHER_COHORT_DRY_RUN', raising=False)
    assert 'etl_alert_cycle' not in d._fixture_filter()
    monkeypatch.setenv('EOC_ALERT_DISPATCHER_COHORT_DRY_RUN', 'true')
    assert 'etl_alert_cycle' not in d._fixture_filter()
    monkeypatch.setenv('EOC_ALERT_DISPATCHER_COHORT_DRY_RUN', '1')
    query = d._fixture_filter()
    assert query.startswith('e.dry_run=1 AND (')
    assert "e.source=N'airflow-task-instances/eoc-attempt'" in query
    assert 's.run_key=c.run_key' in query
    assert 'c.pipeline_name=e.pipeline_name COLLATE Latin1_General_100_BIN2 AND c.run_id=e.run_id COLLATE Latin1_General_100_BIN2' in query
    assert "JSON_VALUE(s.snapshot_json,'$.policyRevision') COLLATE Latin1_General_100_BIN2=e.policy_revision" in query
    assert 'c.generation=e.cycle_generation' not in query


@pytest.mark.parametrize('operation,row', [('claim_one', ('id', 0)),
                                          ('recover_one', ('id', 'token', 1))])
def test_cohort_filter_shared_by_claim_and_recovery(monkeypatch, operation, row):
    monkeypatch.setenv('EOC_ALERT_DISPATCHER_COHORT_DRY_RUN', '1')
    _, cur = fake_db(monkeypatch, row)
    getattr(d, operation)()
    selection = next(c.args[0] for c in cur.execute.call_args_list
                     if 'SELECT TOP (1)' in c.args[0])
    assert d._fixture_filter() in selection
