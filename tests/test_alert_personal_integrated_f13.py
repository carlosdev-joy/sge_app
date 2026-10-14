"""Integração do destino pessoal sem sockets, tenant ou mensagens reais."""
import json
from unittest.mock import Mock

import pytest

from services import alert_channels as c, teams_binding, teams_config
from services.pipeline_alerts import captured_policy
from services.teams_personal import PersonalTarget, ProviderError

TENANT = '11111111-1111-1111-1111-111111111111'
APP = '22222222-2222-2222-2222-222222222222'
USER = '33333333-3333-3333-3333-333333333333'
TARGET = PersonalTarget(TENANT, APP, USER, 'synthetic-graph-chat')
CONFIG = dict(tenant_id=TENANT, app_id=APP, catalog_app_id=APP, client_secret='synthetic',
              admin_approved=True, permissions_verified=True, gateway_verified=True)


def setup(monkeypatch):
    version = '44444444-4444-4444-4444-444444444444'
    definition = {'alertPolicy': dict(schemaVersion=1, events=['failure'],
        recipients=['fixture@example.invalid'], email=False, teamsPersonal=True,
        teamsChannel=None, attemptMode='terminal')}
    policy = captured_policy(definition, version)
    cur = Mock()
    cur.execute.return_value = cur
    cur.fetchone.return_value = ('teamsPersonal', policy['policyRevision'] + ':recipient:0',
        policy['policyRevision'], 'failure', '__eoc_f13_fixture', '__eoc_f13_run', version,
        json.dumps(definition))
    load = Mock(return_value=CONFIG)
    gateway = Mock()
    gateway.list_users.return_value = [dict(id=USER, mail='fixture@example.invalid', tenant_id=TENANT)]
    gateway.personal_conversation.return_value = dict(tenant_id=TENANT, app_id=APP, user_id=USER,
                                                    scope='personal', id=TARGET.conversation_id)
    directory = Mock(return_value=gateway)
    send = Mock(return_value=202)
    provider = Mock(return_value=send)
    monkeypatch.setattr(teams_config, 'load', load)
    monkeypatch.setattr(teams_config, 'directory', directory)
    monkeypatch.setattr(teams_binding, 'provider', provider)
    monkeypatch.setattr(c, 'HTTPSConnection', Mock(side_effect=AssertionError('webhook forbidden')))
    monkeypatch.setattr(c.ssh_datastage, 'run_sendmail', Mock(side_effect=AssertionError('email forbidden')))
    return cur, load, directory, provider, send


def test_personal_dry_run_does_not_read_secret_or_lookup(monkeypatch):
    cur, load, directory, provider, send = setup(monkeypatch)
    assert c.deliver(cur, 'intent').outcome == 'Failed'  # readiness padrão fechada
    for call in (load, directory, provider, send):
        call.assert_not_called()


@pytest.mark.parametrize('fingerprint', [None, 'wrong'])
def test_personal_wrong_authorization_never_loads_provider_or_sends(monkeypatch, fingerprint):
    cur, _, _, provider, send = setup(monkeypatch)
    assert c.deliver(cur, 'intent', dry_run=False,
                     authorized_test_fingerprint=fingerprint).error_code == 'test_destination_not_authorized'
    provider.assert_not_called()
    send.assert_not_called()


@pytest.mark.parametrize('status,outcome', [(202, 'Accepted'), (403, 'Failed'), (429, 'Failed'), (500, 'Unknown')])
def test_personal_exact_binding_and_no_webhook_fallback(monkeypatch, status, outcome):
    cur, _, _, provider, send = setup(monkeypatch)
    send.return_value = status
    result = c.deliver(cur, 'intent', dry_run=False, authorized_test_fingerprint=TARGET.fingerprint)
    assert result.outcome == outcome
    provider.assert_called_once_with(cur, CONFIG, TARGET)
    assert send.call_count == 1
    assert send.call_args.args[0] == TARGET
    assert 'failure' in send.call_args.args[1]
    assert 'synthetic' not in repr(result)


def test_personal_missing_binding_never_sends(monkeypatch):
    cur, _, _, provider, send = setup(monkeypatch)
    provider.return_value = None
    assert c.deliver(cur, 'intent', dry_run=False,
                     authorized_test_fingerprint=TARGET.fingerprint).outcome == 'Failed'
    send.assert_not_called()


def test_personal_closed_admin_gate_never_looks_up(monkeypatch):
    cur, load, directory, provider, send = setup(monkeypatch)
    load.return_value = dict(CONFIG, permissions_verified=False)
    assert c.deliver(cur, 'intent', dry_run=False,
                     authorized_test_fingerprint=TARGET.fingerprint).outcome == 'Failed'
    for call in (directory, provider, send):
        call.assert_not_called()


def test_personal_uncertain_provider_no_exception_leak(monkeypatch):
    cur, _, _, _, send = setup(monkeypatch)
    send.side_effect = ProviderError(502)
    result = c.deliver(cur, 'intent', dry_run=False, authorized_test_fingerprint=TARGET.fingerprint)
    assert result == c.Result('Unknown', 'teams_transport_uncertain')
    assert send.call_count == 1


def test_revoked_readiness_between_lookup_and_provider_blocks_send(monkeypatch):
    cur, load, _, provider, send = setup(monkeypatch)
    load.side_effect = [CONFIG, dict(CONFIG, admin_approved=False)]
    assert c.deliver(cur, 'intent', dry_run=False,
                     authorized_test_fingerprint=TARGET.fingerprint).outcome == 'Failed'
    provider.assert_not_called()
    send.assert_not_called()
