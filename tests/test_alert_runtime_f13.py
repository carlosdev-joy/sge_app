from contextlib import contextmanager
from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from services import alert_runtime, alert_dispatcher, alert_channels


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    alert_runtime.revoke()
    monkeypatch.delenv('EOC_ALERT_OPERATIONAL_TEST', raising=False)
    yield
    alert_runtime.revoke()


def test_flag_off_prevents_any_grant():
    with pytest.raises(HTTPException) as exc:
        alert_runtime.authorize(['a' * 64], 60)
    assert exc.value.status_code == 503
    assert alert_runtime.authorization() is None


def test_expiration_replacement_and_revocation_invalidate_inflight_grant(monkeypatch):
    monkeypatch.setenv('EOC_ALERT_OPERATIONAL_TEST', '1')
    clock = Mock(return_value=0)
    monkeypatch.setattr(alert_runtime.time, 'monotonic', clock)
    alert_runtime.authorize(['a' * 64], 60)
    first = alert_runtime.authorization()
    alert_runtime.require_current(first)
    alert_runtime.authorize(['b' * 64], 60)
    with pytest.raises(RuntimeError):
        alert_runtime.require_current(first)
    latest = alert_runtime.authorization()
    clock.return_value = 61
    assert alert_runtime.authorization() is None
    with pytest.raises(RuntimeError):
        alert_runtime.require_current(latest)


def test_loop_calls_real_adapter_only_with_live_grant(monkeypatch):
    monkeypatch.setenv('EOC_ALERT_OPERATIONAL_TEST', '1')
    alert_runtime.authorize(['a' * 64], 60)
    grant = alert_runtime.authorization()
    monkeypatch.setattr(alert_dispatcher, 'recover_one', lambda: False)
    monkeypatch.setattr(alert_dispatcher, 'claim_one', lambda: dict(dryRun=False))
    dispatch = Mock()
    monkeypatch.setattr(alert_dispatcher, 'dispatch_claim', dispatch)
    assert alert_dispatcher.dispatch_once()
    dispatch.assert_called_once_with(dict(dryRun=False), dry_run=False, grant=grant)


def test_lost_grant_after_claim_is_quarantined_without_provider(monkeypatch):
    monkeypatch.setattr(alert_dispatcher, 'recover_one', lambda: False)
    claim = dict(dryRun=False)
    monkeypatch.setattr(alert_dispatcher, 'claim_one', lambda: claim)
    finish, dispatch = Mock(), Mock()
    monkeypatch.setattr(alert_dispatcher, 'finish_result', finish)
    monkeypatch.setattr(alert_dispatcher, 'dispatch_claim', dispatch)
    alert_dispatcher.dispatch_once()
    dispatch.assert_not_called()
    finish.assert_called_once_with(claim, 'Unknown', 'test_destination_not_authorized')


def test_sql_filter_parenthesizes_operational_branch_and_matches_original_mode(monkeypatch):
    monkeypatch.setenv('EOC_ALERT_OPERATIONAL_TEST', '1')
    sql = alert_dispatcher._fixture_filter()
    assert sql.startswith('((') and sql.endswith('))')
    assert 'e.dry_run=0' in sql and 'operational-test' in sql
    assert 'policyRevision' in sql and 'BIN2' in sql


def test_unapproved_target_never_reaches_transport(monkeypatch):
    target = alert_channels.Target('email', 'fixture@example.invalid')
    monkeypatch.setattr(alert_channels, 'resolve', lambda *a, **k: (target, {'event':'failure','pipeline':'fixture','run':'fixture'}))
    send = Mock()
    monkeypatch.setattr(alert_channels.ssh_datastage, 'run_sendmail', send)
    result = alert_channels.deliver(Mock(), 'fixture', dry_run=False, authorized_test_fingerprints=frozenset(['a'*64]))
    assert result.error_code == 'test_destination_not_authorized'
    send.assert_not_called()
