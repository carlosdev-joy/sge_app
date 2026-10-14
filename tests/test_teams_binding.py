import pytest
from cryptography.fernet import Fernet
from services import teams_binding as m
from tests.test_teams_config import body as configuration


def reference():
    cfg = configuration()
    return dict(tenant_id=cfg['tenant_id'], app_id=cfg['app_id'],
                user_id='44444444-4444-4444-4444-444444444444',
                conversation_id='graph-fixture', service_url='https://smba.trafficmanager.net/teams/',
                connector_conversation_id='connector-fixture', reference_verified=True)


class Cursor:
    def __init__(self):
        self.saved = None
        self.calls = []

    def execute(self, sql, params):
        self.calls.append((sql, params))
        if sql.startswith('MERGE'):
            self.saved = params[1]

    def fetchone(self):
        return (self.saved,) if self.saved else None


def test_roundtrip_bootstrap_no_network(monkeypatch):
    monkeypatch.setenv('ORQUESTRA_CONN_KEY', Fernet.generate_key().decode())
    cur = Cursor()
    ref = reference()
    target = m.save(cur, ref, configuration(), 'fixture-admin')
    assert ref['connector_conversation_id'] not in cur.saved
    assert ref['user_id'] not in cur.saved
    assert m.provider(cur, configuration(), target) is not None
    assert cur.calls[0][1][2] == 'fixture-admin'


@pytest.mark.parametrize('field,value', [('reference_verified', 1), ('user_id', None),
    ('tenant_id', '55555555-5555-5555-5555-555555555555'), ('service_url', 'https://evil.test/'),
    ('service_url', None), ('connector_conversation_id', ''), ('conversation_id', 'bad\nvalue')])
def test_rejected_before_write(field, value):
    ref = reference()
    ref[field] = value
    cur = Cursor()
    with pytest.raises(m.ConfigurationError, match='^invalid_binding$'):
        m.save(cur, ref, configuration(), 'fixture-admin')
    assert not cur.calls


def test_wrong_snapshot_cannot_load(monkeypatch):
    monkeypatch.setenv('ORQUESTRA_CONN_KEY', Fernet.generate_key().decode())
    cur = Cursor()
    m.save(cur, reference(), configuration(), 'fixture-admin')
    ref = reference()
    ref['conversation_id'] = 'different-run-snapshot'
    target = m.validate(ref, configuration())
    with pytest.raises(m.ConfigurationError, match='^binding_unreadable$'):
        m.provider(cur, configuration(), target)


def test_missing_and_store_unavailable():
    target = m.validate(reference(), configuration())
    assert m.provider(Cursor(), configuration(), target) is None
    class Missing:
        def execute(self, *args):
            raise RuntimeError('private-fixture')
    with pytest.raises(m.ConfigurationError, match='^binding_store_unavailable_migration_184$'):
        m.provider(Missing(), configuration(), target)


def test_maximum_reference_roundtrip(monkeypatch):
    monkeypatch.setenv('ORQUESTRA_CONN_KEY', Fernet.generate_key().decode())
    ref = reference()
    ref['conversation_id'] = 'g' * 512
    ref['connector_conversation_id'] = 'c' * 512
    cur = Cursor()
    target = m.save(cur, ref, configuration(), 'fixture-admin')
    assert len(cur.saved) > 1000
    assert m.provider(cur, configuration(), target) is not None


def test_user_uuid_casing_matches_graph_snapshot(monkeypatch):
    monkeypatch.setenv('ORQUESTRA_CONN_KEY', Fernet.generate_key().decode())
    ref = reference()
    ref['user_id'] = 'ABCDEFAB-ABCD-ABCD-ABCD-ABCDEFABCDEF'
    cur = Cursor()
    target = m.save(cur, ref, configuration(), 'fixture-admin')
    ref['user_id'] = ref['user_id'].lower()
    resolved = m.validate(ref, configuration())
    assert target.fingerprint == resolved.fingerprint
    assert m.provider(cur, configuration(), resolved) is not None
