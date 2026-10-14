import json
from uuid import uuid4
from unittest.mock import Mock

import pytest

from services import alert_channels as c
from services.pipeline_alerts import captured_policy


POLICY = dict(schemaVersion=1, events=['failure'], recipients=['fixture@example.invalid'],
              email=True, teamsPersonal=False, teamsChannel={'groupId': 7}, attemptMode='terminal')
WEBHOOK = 'https://fixture.webhook.office.com/test'


def cursor(channel='email', definition=None):
    version = str(uuid4())
    definition = definition or {'alertPolicy': POLICY}
    capture = captured_policy(definition, version)
    suffix = 'recipient:0' if channel == 'email' else 'group:7'
    cur = Mock()
    row = (channel, capture['policyRevision'] + ':' + suffix, capture['policyRevision'],
           'failure', '__eoc_f9_fixture', '__eoc_f9_run', version, json.dumps(definition))
    cur.execute.return_value = cur
    cur.fetchone.side_effect = [row, (WEBHOOK,)] if channel == 'teamsChannel' else [row]
    return cur, row


def test_original_snapshot_and_explicit_group():
    cur, _ = cursor('teamsChannel')
    target, context = c.resolve(cur, str(uuid4()))
    assert target.value == WEBHOOK and context['event'] == 'failure'
    assert cur.execute.call_args.args[1] == (7,)
    assert 'ativo=1' in cur.execute.call_args.args[0]
    assert WEBHOOK not in repr(target)
    assert 'active' not in cur.execute.call_args_list[0].args[0]


@pytest.mark.parametrize('value', [None, '', 'http://a.webhook.office.com/test',
    'https://evil.test/', 'https://webhook.office.com.evil.test/t',
    'https://localhost/t', 'https://a.webhook.office.com:444/t',
    'https://user:secret@a.webhook.office.com/t', 'https://a.webhook.office.com/t#secret',
    'https://a.webhook.office.com/\nsecret', 'https://a.webhook.office.com'])
def test_webhook_rejects_invalid_without_default(value):
    assert not c.valid_webhook(value)


@pytest.mark.parametrize('value', ['https://a.webhook.office.com/t',
                                  'https://a.logic.azure.com/workflows/test?sig=fixture',
                                  'https://a.environment.api.powerplatform.com:443/powerautomate/automations/direct/cu/20/workflows/test/triggers/manual/paths/invoke?sig=fixture'])
def test_allowed_hosts(value):
    assert c.valid_webhook(value)


@pytest.mark.parametrize('channel', ['email', 'teamsChannel'])
def test_dry_run_and_no_authorization_never_send(monkeypatch, channel):
    send = Mock(side_effect=AssertionError('no transport'))
    monkeypatch.setattr(c.ssh_datastage, 'run_sendmail', send)
    monkeypatch.setattr(c, 'HTTPSConnection', send)
    cur, _ = cursor(channel)
    assert c.deliver(cur, str(uuid4())).outcome == 'DryRun'
    cur, _ = cursor(channel)
    assert c.deliver(cur, str(uuid4()), dry_run=False).error_code == 'test_destination_not_authorized'
    send.assert_not_called()


def test_snapshot_conflict_blocks_transport(monkeypatch):
    cur, row = cursor()
    cur.fetchone.side_effect = [(*row[:2], 'wrong-revision', *row[3:])]
    send = Mock(); monkeypatch.setattr(c.ssh_datastage, 'run_sendmail', send)
    assert c.deliver(cur, str(uuid4()), dry_run=False).error_code == 'invalid_destination'
    send.assert_not_called()


@pytest.mark.parametrize('group', [None, ('',), ('https://evil.test/secret',)])
def test_bad_group_never_falls_back(group):
    cur, row = cursor('teamsChannel');cur.fetchone.side_effect = [row, group]
    assert c.deliver(cur, str(uuid4())).outcome == 'Failed'
    assert len(cur.execute.call_args_list) == 2


@pytest.mark.parametrize('exit_code,outcome', [(0, 'Accepted'), (1, 'Failed'), (-1, 'Unknown')])
def test_email_reuses_mime_sendmail_no_stderr_leak(monkeypatch, exit_code, outcome):
    monkeypatch.setattr(c.email_config, 'load_config', lambda _: dict(enabled=True, disponivel=True,
        erro=None, remetente='orquestra@example.invalid', dominios=[]))
    send = Mock(return_value=dict(exit_code=exit_code, stderr='private-secret', host='private-host'))
    monkeypatch.setattr(c.ssh_datastage, 'run_sendmail', send)
    cur, _ = cursor()
    authorized = c.Target('email', POLICY['recipients'][0]).fingerprint
    result = c.deliver(cur, str(uuid4()), dry_run=False, authorized_test_fingerprint=authorized)
    assert result.outcome == outcome and 'private' not in repr(result)
    assert send.call_args.kwargs['timeout'] == 15
    assert b'To: fixture@example.invalid' in send.call_args.args[0]


@pytest.mark.parametrize('status,outcome', [(200, 'Accepted'), (202, 'Accepted'),
                                           (302, 'Failed'), (429, 'Failed'), (500, 'Failed')])
def test_teams_outcomes_no_redirect_retry_or_received(monkeypatch, status, outcome):
    client = Mock();client.getresponse.return_value.status = status
    factory = Mock(return_value=client);monkeypatch.setattr(c, 'HTTPSConnection', factory)
    cur, _ = cursor('teamsChannel')
    result = c.deliver(cur, str(uuid4()), dry_run=False,
                       authorized_test_fingerprint=c.Target('teamsChannel', WEBHOOK).fingerprint)
    assert result.outcome == outcome
    assert factory.call_args.args == ('fixture.webhook.office.com', 443)
    assert factory.call_args.kwargs['timeout'] == 15
    import ssl
    context = factory.call_args.kwargs['context']
    assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname
    client.set_debuglevel.assert_called_once_with(0)
    assert client.request.call_count == 1
    assert client.request.call_args.args == ('POST', '/test')
    client.close.assert_called_once()
    assert WEBHOOK not in repr(result)


def test_ambiguous_email_exception_unknown_never_exposes_exception(monkeypatch):
    monkeypatch.setattr(c.email_config, 'load_config', lambda _: dict(enabled=True, disponivel=True,
        erro=None, remetente='orquestra@example.invalid', dominios=[]))
    monkeypatch.setattr(c.ssh_datastage, 'run_sendmail', Mock(side_effect=TimeoutError('private-secret')))
    cur, _ = cursor()
    r = c.deliver(cur, str(uuid4()), dry_run=False,
                  authorized_test_fingerprint=c.Target('email', POLICY['recipients'][0]).fingerprint)
    assert r == c.Result('Unknown', 'transport_uncertain')


def test_channel_disabled_blocks_email(monkeypatch):
    monkeypatch.setattr(c.email_config, 'load_config', lambda _: dict(enabled=False, disponivel=True,
        erro=None, remetente='orquestra@example.invalid', dominios=[]))
    send = Mock();monkeypatch.setattr(c.ssh_datastage, 'run_sendmail', send)
    cur, _ = cursor()
    assert c.deliver(cur, str(uuid4()), dry_run=False,
        authorized_test_fingerprint=c.Target('email', POLICY['recipients'][0]).fingerprint).outcome == 'Failed'
    send.assert_not_called()
