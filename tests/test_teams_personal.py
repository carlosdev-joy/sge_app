from dataclasses import replace
from unittest.mock import Mock

import pytest
from services.teams_personal import Configuration, ProviderError, preview, resolve

TENANT = '10000000-0000-0000-0000-000000000001'
APP = '20000000-0000-0000-0000-000000000001'
USER = '30000000-0000-0000-0000-000000000001'
OTHER = '30000000-0000-0000-0000-000000000002'
EMAIL = 'fixture@example.invalid'
CFG = Configuration(TENANT, APP, True, True, True)


def gateway():
    g = Mock()
    g.list_users.return_value = [dict(id=USER, mail=EMAIL, tenant_id=TENANT)]
    g.personal_conversation.return_value = dict(tenant_id=TENANT, app_id=APP,
                                               user_id=USER, scope='personal', id='conversation-fixture')
    return g


@pytest.mark.parametrize('field,value,code', [
    ('tenant_id', '', 'tenant_app_missing'), ('app_id', 'invalid', 'tenant_app_missing'),
    ('admin_approved', False, 'admin_approval_missing'),
    ('permissions_verified', False, 'permissions_unverified'),
    ('gateway_verified', False, 'gateway_unverified')])
def test_closed_readiness(field, value, code):
    g = gateway()
    assert preview(replace(CFG, **{field: value}), g, EMAIL).error_code == code
    g.list_users.assert_not_called()


def test_independent_channel_and_private_repr():
    target, error = resolve(CFG, gateway(), EMAIL)
    assert error is None and target.channel == 'teamsPersonal'
    assert USER not in repr(target) and TENANT not in repr(CFG)
    assert preview(CFG, gateway(), EMAIL).outcome == 'DryRun'


@pytest.mark.parametrize('email', [None, 4, 'invalid', 'a\n@example.invalid', 'a'*255+'@example.invalid'])
def test_bad_email_no_remote_lookup(email):
    g = gateway()
    assert resolve(CFG, g, email)[1] == 'invalid_destination'
    g.list_users.assert_not_called()


def test_missing_and_ambiguous_exact_identity():
    g = gateway()
    g.list_users.return_value = []
    assert resolve(CFG, g, EMAIL)[1] == 'user_not_found'
    g.list_users.return_value = [dict(id=i, mail=EMAIL, tenant_id=TENANT) for i in (USER, OTHER)]
    assert resolve(CFG, g, EMAIL)[1] == 'user_ambiguous'
    g.personal_conversation.assert_not_called()


def test_other_tenant_and_partial_match_rejected():
    g = gateway()
    g.list_users.return_value = [dict(id=USER, mail=EMAIL, tenant_id=APP),
                                dict(id=OTHER, mail='prefix'+EMAIL, tenant_id=TENANT)]
    assert resolve(CFG, g, EMAIL)[1] == 'user_not_found'


def test_upn_exact_case_insensitive_deduplicated():
    g = gateway()
    g.list_users.return_value = [dict(id=USER, userPrincipalName=EMAIL.upper(), tenant_id=TENANT)]*2
    assert resolve(CFG, g, EMAIL)[1] is None


@pytest.mark.parametrize('key,value', [('tenant_id', APP), ('app_id', TENANT),
    ('user_id', OTHER), ('scope', 'channel'), ('id', ''), ('id', 'x\ny'), ('id', None)])
def test_unbound_conversation(key, value):
    g = gateway()
    g.personal_conversation.return_value[key] = value
    assert resolve(CFG, g, EMAIL)[1] == 'conversation_unverified'


def test_app_not_installed():
    g = gateway()
    g.personal_conversation.return_value = None
    assert resolve(CFG, g, EMAIL)[1] == 'app_not_installed'


@pytest.mark.parametrize('stage', ['list_users', 'personal_conversation'])
@pytest.mark.parametrize('error,code', [(ProviderError(403), 'teams_forbidden'),
    (ProviderError(429), 'teams_throttled'), (RuntimeError('secret-remote-body'), 'teams_provider_unavailable')])
def test_remote_failures_sanitized(stage, error, code, caplog):
    g = gateway()
    getattr(g, stage).side_effect = error
    result = preview(CFG, g, EMAIL)
    assert result.error_code == code
    assert 'secret-remote-body' not in repr(result)+caplog.text

from urllib.parse import parse_qs, urlsplit
from services.teams_personal import GraphDirectoryGateway

CATALOG = '40000000-0000-0000-0000-000000000001'


def test_graph_documented_gets_and_encoding():
    get = Mock(side_effect=[(200, {'value': [dict(id=USER, mail=EMAIL)]}),
        (200, {'value': [dict(id='installation/encoded', teamsApp={'id': CATALOG}, teamsAppDefinition={'id': 'definition'})]}),
        (200, {'id': APP}), (200, dict(id='chat-fixture', chatType='oneOnOne'))])
    target, error = resolve(CFG, GraphDirectoryGateway(TENANT, APP, CATALOG, get), EMAIL)
    assert error is None and target.conversation_id == 'chat-fixture'
    calls = [c.args[0] for c in get.call_args_list]
    query = parse_qs(urlsplit(calls[0]).query)
    assert query['$filter'] == [f"mail eq '{EMAIL}' or userPrincipalName eq '{EMAIL}'"]
    assert calls[3].endswith('/installation%2Fencoded/chat')
    assert calls[2].endswith('/appDefinitions/definition/bot')


def test_graph_incomplete_page_fails_closed():
    get = Mock(return_value=(200, {'value': [], '@odata.nextLink': 'https://private.invalid/token'}))
    result = preview(CFG, GraphDirectoryGateway(TENANT, APP, CATALOG, get), EMAIL)
    assert result.error_code == 'teams_provider_unavailable'
    assert get.call_count == 1


@pytest.mark.parametrize('status,code', [(403, 'teams_forbidden'), (429, 'teams_throttled'),
                                        (500, 'teams_provider_unavailable')])
def test_graph_status_sanitized(status, code):
    get = Mock(return_value=(status, {'error': 'private remote body'}))
    assert preview(CFG, GraphDirectoryGateway(TENANT, APP, CATALOG, get), EMAIL).error_code == code


def test_graph_no_installation_no_chat_request():
    get = Mock(side_effect=[(200, {'value': [dict(id=USER, mail=EMAIL)]}), (200, {'value': []})])
    assert preview(CFG, GraphDirectoryGateway(TENANT, APP, CATALOG, get), EMAIL).error_code == 'app_not_installed'
    assert get.call_count == 2


@pytest.mark.parametrize('chat', [dict(id='chat', chatType='group'), dict(chatType='oneOnOne')])
def test_graph_wrong_or_missing_chat(chat):
    get = Mock(side_effect=[(200, {'value': [dict(id=USER, mail=EMAIL)]}),
        (200, {'value': [dict(id='installation', teamsApp={'id': CATALOG}, teamsAppDefinition={'id': 'definition'})]}), (200, {'id': APP}), (200, chat)])
    assert preview(CFG, GraphDirectoryGateway(TENANT, APP, CATALOG, get), EMAIL).outcome == 'Failed'

from services.teams_personal import deliver_target


@pytest.mark.parametrize('status,outcome,code', [(200, 'Accepted', None),
    (202, 'Accepted', None), (403, 'Failed', 'teams_forbidden'), (429, 'Failed', 'teams_throttled'),
    (500, 'Unknown', 'teams_transport_uncertain'), (None, 'Unknown', 'teams_transport_uncertain')])
def test_proactive_adapter_outcomes(status, outcome, code):
    target, _ = resolve(CFG, gateway(), EMAIL)
    send = Mock(return_value=status)
    result = deliver_target(target, send, 'fixture', dry_run=False,
                            authorized_test_fingerprint=target.fingerprint)
    assert (result.outcome, result.error_code) == (outcome, code)
    send.assert_called_once_with(target, 'fixture')


def test_proactive_adapter_gate_and_uncertainty():
    target, _ = resolve(CFG, gateway(), EMAIL)
    send = Mock(side_effect=TimeoutError('private-token'))
    assert deliver_target(target, send, 'fixture').outcome == 'DryRun'
    assert deliver_target(target, send, 'fixture', dry_run=False).error_code == 'test_destination_not_authorized'
    send.assert_not_called()
    result = deliver_target(target, send, 'fixture', dry_run=False,
                            authorized_test_fingerprint=target.fingerprint)
    assert result.outcome == 'Unknown' and 'private-token' not in repr(result)
    assert send.call_count == 1


def test_graph_catalog_other_bot_is_not_verified():
    get = Mock(side_effect=[(200, {'value': [dict(id=USER, mail=EMAIL)]}),
        (200, {'value': [dict(id='installation', teamsApp={'id': CATALOG},
                              teamsAppDefinition={'id': 'definition'})]}), (200, {'id': OTHER})])
    assert preview(CFG, GraphDirectoryGateway(TENANT, APP, CATALOG, get), EMAIL).error_code == 'teams_provider_unavailable'
    assert get.call_count == 3


def test_intent_uses_captured_recipient_and_revision():
    import json
    from uuid import uuid4
    from services.alert_channels import resolve as resolve_intent
    from services.pipeline_alerts import captured_policy
    definition = {'alertPolicy': dict(schemaVersion=1, events=['failure'], recipients=[EMAIL],
        email=True, teamsPersonal=True, teamsChannel=None, attemptMode='terminal')}
    version = str(uuid4())
    capture = captured_policy(definition, version)
    revision = capture['policyRevision']
    cur = Mock()
    cur.execute.return_value = cur
    row = ('teamsPersonal', revision+':recipient:0', revision, 'failure',
           '__eoc_f11_fixture', '__eoc_f11_run', version, json.dumps(definition))
    cur.fetchone.return_value = row
    g = gateway()
    target, context = resolve_intent(cur, 'intent-fixture', personal_config=CFG, personal_gateway=g)
    assert target.channel == 'teamsPersonal' and context['run'] == '__eoc_f11_run'
    g.list_users.assert_called_once_with(TENANT, EMAIL)
    cur.fetchone.return_value = (*row[:2], 'wrong', *row[3:])
    g.reset_mock()
    with pytest.raises(ValueError, match='snapshot_conflict'):
        resolve_intent(cur, 'intent-fixture', personal_config=CFG, personal_gateway=g)
    g.list_users.assert_not_called()


def test_default_personal_readiness_closed():
    assert Configuration().readiness() == 'tenant_app_missing'
