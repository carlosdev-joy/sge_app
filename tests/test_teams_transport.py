import pytest
from services import teams_transport as m
from services.teams_personal import PersonalTarget, ProviderError, deliver_target

TENANT = '11111111-1111-1111-1111-111111111111'
APP = '22222222-2222-2222-2222-222222222222'
USER = '33333333-3333-3333-3333-333333333333'


def fixture():
    return m.AuthenticatedTransport(TENANT, APP, 'synthetic'), PersonalTarget(TENANT, APP, USER, 'graph-chat')


def test_oauth_and_send_bound(monkeypatch):
    calls = []
    def request(host, method, path, body=None, headers=None):
        calls.append((host, method, path, body, headers))
        if host == 'login.microsoftonline.com':
            return 200, {'access_token': 'synthetic-token', 'token_type': 'Bearer'}
        return 201, {'id': 'synthetic-activity'}
    monkeypatch.setattr(m, '_https', request)
    transport, target = fixture()
    provider = m.ConnectorProvider(transport, target, 'https://smba.trafficmanager.net/teams/', 'connector-chat')
    assert deliver_target(target, provider, 'teste').outcome == 'DryRun'
    assert not calls
    result = deliver_target(target, provider, 'teste', dry_run=False, authorized_test_fingerprint=target.fingerprint)
    assert result.outcome == 'Accepted'
    assert len(calls) == 2
    assert TENANT in calls[0][2]
    assert 'api.botframework.com' in calls[0][3]
    assert 'connector-chat' in calls[1][2] and 'graph-chat' not in calls[1][2]


@pytest.mark.parametrize('url', ['http://smba.trafficmanager.net/teams/', 'https://evil.test/teams/',
    'https://smba.trafficmanager.net.evil/teams/', 'https://user@smba.trafficmanager.net/teams/',
    'https://smba.trafficmanager.net:443/teams/', 'https://smba.trafficmanager.net/teams/?x=1'])
def test_reject_service_urls(url):
    transport, target = fixture()
    with pytest.raises(ValueError):
        m.ConnectorProvider(transport, target, url, 'chat')


def test_wrong_target_never_gets_token(monkeypatch):
    transport, target = fixture()
    provider = m.ConnectorProvider(transport, target, 'https://smba.trafficmanager.net/teams/', 'chat')
    monkeypatch.setattr(m, '_https', lambda *a, **kw: pytest.fail('network forbidden'))
    with pytest.raises(ProviderError):
        provider(PersonalTarget(TENANT, APP, USER, 'other-chat'), 'teste')


@pytest.mark.parametrize('body', [{}, {'access_token': 'bad\r\nheader', 'token_type': 'Bearer'},
    {'access_token': 'x', 'token_type': 'Basic'}])
def test_invalid_token_closed(monkeypatch, body):
    transport, _ = fixture()
    monkeypatch.setattr(m, '_https', lambda *a, **kw: (200, body))
    with pytest.raises(ProviderError):
        transport.graph_get('/v1.0/users')


@pytest.mark.parametrize('status', [403, 429, 500, 302])
def test_send_failure_no_retry(monkeypatch, status):
    transport, target = fixture()
    calls = []
    def request(host, *a, **kw):
        calls.append(host)
        return (200, {'access_token': 'token', 'token_type': 'Bearer'}) if host == 'login.microsoftonline.com' else (status, {})
    monkeypatch.setattr(m, '_https', request)
    provider = m.ConnectorProvider(transport, target, 'https://smba.trafficmanager.net/teams/', 'chat')
    result = deliver_target(target, provider, 'teste', dry_run=False, authorized_test_fingerprint=target.fingerprint)
    assert result.outcome == ('Failed' if status in (403, 429) else 'Unknown')
    assert len(calls) == 2


@pytest.mark.parametrize('status,code', [(403, 'teams_forbidden'), (429, 'teams_throttled')])
def test_oauth_rejection_explained_without_message_attempt(monkeypatch, status, code):
    transport, target = fixture()
    calls = []

    def request(host, *args, **kwargs):
        calls.append(host)
        return status, {}

    monkeypatch.setattr(m, '_https', request)
    provider = m.ConnectorProvider(transport, target, 'https://smba.trafficmanager.net/teams/', 'chat')
    result = deliver_target(target, provider, 'fixture', dry_run=False,
                            authorized_test_fingerprint=target.fingerprint)
    assert (result.outcome, result.error_code) == ('Failed', code)
    assert calls == ['login.microsoftonline.com']


@pytest.mark.parametrize('status,raw', [(302, b'private'), (403, b'x' * (m._MAX_BODY + 1)), (429, b'x' * (m._MAX_BODY + 1)), (200, b'not-json'), (200, b'[]'), (200, b'x' * (m._MAX_BODY + 1))], ids=['redirect', 'forbidden_large', 'throttled_large', 'invalid_json', 'array_json', 'oversized'])
def test_https_closed_response(monkeypatch, status, raw):
    instances = []
    class Connection:
        def __init__(self, host, timeout, context):
            assert timeout == 10 and context.verify_mode == 2 and context.check_hostname
            self.closed = False
            instances.append(self)
        def request(self, *args, **kwargs):
            pass
        def set_debuglevel(self, level):
            assert level == 0
        def getresponse(self):
            return self
        def read(self, maximum):
            assert maximum == m._MAX_BODY + 1
            return raw
        def close(self):
            self.closed = True
    Connection.status = status
    monkeypatch.setattr(m.http.client, 'HTTPSConnection', Connection)
    if status in (302, 403, 429):
        assert m._https('graph.microsoft.com', 'GET', '/v1.0/users') == (status, {})
    else:
        with pytest.raises(ProviderError) as error:
            m._https('graph.microsoft.com', 'GET', '/v1.0/users')
        assert str(error.value) == 'teams_provider_error'
    assert len(instances) == 1 and instances[0].closed


@pytest.mark.parametrize('method,body,headers', [
    ('POST', 'client_secret=synthetic-private-secret', {}),
    ('GET', None, {'Authorization': 'Bearer synthetic-private-token'}),
])
def test_global_http_debug_cannot_print_credentials(monkeypatch, capsys, method, body, headers):
    import io

    class MemorySocket:
        def sendall(self, data):
            pass

        def makefile(self, mode):
            return io.BytesIO(b'HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\n{}')

        def close(self):
            pass

    monkeypatch.setattr(m.http.client.HTTPSConnection, 'debuglevel', 1)
    monkeypatch.setattr(m.http.client.HTTPSConnection, 'connect',
                        lambda conn: setattr(conn, 'sock', MemorySocket()))
    assert m._https('graph.microsoft.com', method, '/synthetic', body, headers) == (200, {})
    captured = capsys.readouterr()
    assert captured.out == '' and captured.err == ''
