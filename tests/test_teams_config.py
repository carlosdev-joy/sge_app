import pytest
from cryptography.fernet import Fernet
from services import teams_config as m


def body():
    return dict(tenant_id='11111111-1111-1111-1111-111111111111',
                app_id='22222222-2222-2222-2222-222222222222',
                catalog_app_id='33333333-3333-3333-3333-333333333333',
                client_secret='synthetic', admin_approved=False,
                permissions_verified=False, gateway_verified=False)


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


def test_roundtrip_ciphertext_and_public_closed(monkeypatch):
    monkeypatch.setenv('ORQUESTRA_CONN_KEY', Fernet.generate_key().decode())
    cur = Cursor()
    payload = body()
    m.save(cur, payload, 'fixture-admin')
    assert payload['client_secret'] not in cur.saved
    assert payload['tenant_id'] not in cur.saved
    assert m.load(cur) == payload
    assert m.public_status(m.load(cur)) == dict(configured=True,
        readiness='admin_approval_missing', delivery_enabled=False)
    assert not any(k in m.public_status(payload) for k in payload)


@pytest.mark.parametrize('field,value', [('admin_approved', 'true'),
    ('gateway_verified', 1), ('tenant_id', None), ('client_secret', 12),
    ('client_secret', 'bad\nsecret')])
def test_invalid_payload_does_not_write(field, value):
    payload = body()
    payload[field] = value
    cur = Cursor()
    with pytest.raises(m.ConfigurationError):
        m.save(cur, payload, 'fixture-admin')
    assert not cur.calls


def test_missing_key_sanitized(monkeypatch):
    monkeypatch.delenv('ORQUESTRA_CONN_KEY', raising=False)
    cur = Cursor()
    with pytest.raises(m.ConfigurationError, match='^encryption_unavailable$'):
        m.save(cur, body(), 'fixture-admin')
    assert not cur.calls


def test_encrypted_column_limit(monkeypatch):
    monkeypatch.setenv('ORQUESTRA_CONN_KEY', Fernet.generate_key().decode())
    payload = body()
    payload['client_secret'] = 'x' * 1000
    cur = Cursor()
    with pytest.raises(m.ConfigurationError, match='^configuration_too_large$'):
        m.save(cur, payload, 'fixture-admin')
    assert not cur.calls


def test_corrupt_store_sanitized(monkeypatch):
    monkeypatch.setenv('ORQUESTRA_CONN_KEY', Fernet.generate_key().decode())
    cur = Cursor()
    cur.saved = 'corrupt-synthetic'
    with pytest.raises(m.ConfigurationError, match='^configuration_unreadable$'):
        m.load(cur)


def test_no_configuration_no_bootstrap():
    assert m.public_status(m.load(Cursor()))['configured'] is False
    with pytest.raises(m.ConfigurationError, match='administrative_readiness_required'):
        m.directory(None)


def test_bootstrap_without_network():
    payload = body()
    payload.update(admin_approved=True, permissions_verified=True, gateway_verified=True)
    gateway = m.directory(payload)
    assert gateway.tenant_id == payload['tenant_id']
    assert m.public_status(payload)['delivery_enabled'] is False
