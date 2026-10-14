"""Lease expira entre conexão/OAuth e mensagem: nunca emitir nem repetir."""
from contextlib import contextmanager
from unittest.mock import Mock

import pytest

from services import alert_channels, alert_dispatcher, ssh_datastage, teams_transport
from services.teams_personal import PersonalTarget, ProviderError


def expired():
    raise RuntimeError('synthetic_expired')


def test_ssh_expired_after_connect_never_executes_sendmail(monkeypatch):
    client = Mock()
    monkeypatch.setattr(ssh_datastage, 'ssh_configured', lambda: True)
    monkeypatch.setattr(ssh_datastage, 'comando_sendmail', lambda _: 'synthetic')
    monkeypatch.setattr(ssh_datastage, '_conectar', lambda: client)
    with pytest.raises(RuntimeError):
        ssh_datastage.run_sendmail(b'synthetic', 'fixture@example.invalid', before_send=expired)
    client.exec_command.assert_not_called()
    client.close.assert_called_once()


def _sendmail_client(monkeypatch):
    client = Mock()
    stdin, stdout, stderr = Mock(), Mock(), Mock()
    client.exec_command.return_value = (stdin, stdout, stderr)
    monkeypatch.setattr(ssh_datastage, 'ssh_configured', lambda: True)
    monkeypatch.setattr(ssh_datastage, 'comando_sendmail', lambda _: 'synthetic')
    monkeypatch.setattr(ssh_datastage, '_conectar', lambda: client)
    return client, stdout.channel


def test_fenced_sendmail_missing_exit_expires_without_blocking(monkeypatch):
    client, channel = _sendmail_client(monkeypatch)
    channel.recv_ready.return_value = False
    channel.recv_stderr_ready.return_value = False
    channel.exit_status_ready.return_value = False
    monkeypatch.setattr(ssh_datastage.time, 'monotonic', Mock(side_effect=[0, 0, 16]))
    monkeypatch.setattr(ssh_datastage.time, 'sleep', lambda _: None)
    with pytest.raises(TimeoutError, match='sendmail_budget_expired'):
        ssh_datastage.run_sendmail(b'synthetic', 'fixture@example.invalid', timeout=15, before_send=lambda: None)
    channel.recv_exit_status.assert_not_called()
    channel.close.assert_called_once()
    client.close.assert_called_once()


def test_fenced_sendmail_drains_full_channel_before_exit_with_bounded_error(monkeypatch):
    client, channel = _sendmail_client(monkeypatch)
    channel.recv_ready.side_effect = [True, False]
    channel.recv_stderr_ready.side_effect = [True, False]
    channel.recv_stderr.return_value = b'x' * 32768
    channel.exit_status_ready.return_value = True
    channel.recv_exit_status.return_value = 0
    result = ssh_datastage.run_sendmail(b'synthetic', 'fixture@example.invalid', before_send=lambda: None)
    channel.recv.assert_called_once_with(32768)
    assert result['exit_code'] == 0
    assert len(result['stderr']) == 2000
    client.close.assert_called_once()


def test_connector_expiry_after_oauth_blocks_activity_and_closes_connections(monkeypatch):
    oauth, activity = Mock(), Mock()
    response = oauth.getresponse.return_value
    response.status = 200
    response.read.return_value = b'{"access_token":"synthetic","token_type":"bearer"}'
    monkeypatch.setattr(teams_transport.http.client, 'HTTPSConnection', Mock(side_effect=[oauth, activity]))
    tenant = '11111111-1111-1111-1111-111111111111'
    app = '22222222-2222-2222-2222-222222222222'
    target = PersonalTarget(tenant, app, '33333333-3333-3333-3333-333333333333', 'synthetic')
    transport = teams_transport.AuthenticatedTransport(tenant, app, 'synthetic')
    provider = teams_transport.ConnectorProvider(transport, target, 'https://smba.trafficmanager.net/teams/', 'synthetic')
    fence = Mock(side_effect=[None, RuntimeError('synthetic_expired')])
    with teams_transport.fenced_requests(fence), pytest.raises(ProviderError):
        provider(target, 'synthetic')
    oauth.request.assert_called_once()
    activity.connect.assert_called_once()
    activity.request.assert_not_called()
    oauth.close.assert_called_once()
    activity.close.assert_called_once()
    assert teams_transport._request_fence.get() is None


def test_channel_expired_after_tls_never_posts(monkeypatch):
    target = alert_channels.Target('teamsChannel', 'https://fixture.webhook.office.com/synthetic')
    monkeypatch.setattr(alert_channels, 'resolve', lambda *a, **k: (target, dict(event='failure', pipeline='fixture', run='fixture')))
    connection = Mock()
    monkeypatch.setattr(alert_channels, 'HTTPSConnection', lambda *a, **k: connection)
    result = alert_channels.deliver(Mock(), 'intent', dry_run=False,
        authorized_test_fingerprint=target.fingerprint, before_send=expired)
    assert result == alert_channels.Result('Unknown', 'transport_uncertain')
    connection.connect.assert_called_once()
    connection.request.assert_not_called()
    connection.close.assert_called_once()


def test_dispatcher_checks_exact_claim_again_before_send(monkeypatch):
    conn, cur = Mock(), Mock()
    cur.execute.return_value = cur
    cur.fetchone.side_effect = [('intent',), None]
    @contextmanager
    def bounded():
        yield conn, cur
    monkeypatch.setattr(alert_dispatcher, 'bounded_conn', bounded)
    monkeypatch.setattr(alert_dispatcher, 'require_schema', lambda _: None)
    send = Mock()
    def adapter(cur, intent, **kwargs):
        try:
            kwargs['before_send']()
            send()
        except RuntimeError:
            return alert_channels.Result('Unknown', 'transport_uncertain')
    monkeypatch.setattr(alert_channels, 'deliver', adapter)
    finish = Mock(return_value=False)
    monkeypatch.setattr(alert_dispatcher, 'finish_result', finish)
    claim = dict(intentId='intent', leaseToken='synthetic', sequence=2)
    assert not alert_dispatcher.dispatch_claim(claim, dry_run=False, authorized_test_fingerprint='synthetic')
    send.assert_not_called()
    sql, params = cur.execute.call_args.args
    assert 'lease_until>SYSUTCDATETIME()' in sql
    assert params == ('intent', 'synthetic', 2)
    finish.assert_called_once_with(claim, 'Unknown', 'transport_uncertain')
    conn.commit.assert_called_once()
