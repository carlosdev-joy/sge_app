"""Transporte F11 OAuth/Connector REST; fechado, sem proxy, redirect ou retry."""
import http.client
import json
import ssl
from contextlib import contextmanager
from contextvars import ContextVar
from urllib.parse import quote, urlencode, urlsplit

from services.teams_personal import PersonalTarget, ProviderError, _uuid

_MAX_BODY = 1024 * 1024
_request_fence = ContextVar('teams_request_fence', default=None)


@contextmanager
def fenced_requests(before_send):
    """Fence RAM por execução; revalidada após TLS, inclusive após OAuth."""
    token = _request_fence.set(before_send)
    try:
        yield
    finally:
        _request_fence.reset(token)


def _https(host, method, path, body=None, headers=None):
    conn = http.client.HTTPSConnection(host, timeout=10, context=ssl.create_default_context())
    conn.set_debuglevel(0)
    try:
        fence = _request_fence.get()
        if fence is not None:
            conn.connect()
            fence()
        conn.request(method, path, body=body, headers=headers or {})
        response = conn.getresponse()
        # Rejeição explícita preservada sem ler corpo remoto nem Location.
        if not 200 <= response.status < 300:
            return response.status, {}
        raw = response.read(_MAX_BODY + 1)
        if len(raw) > _MAX_BODY:
            raise ProviderError(502)
        try:
            value = json.loads(raw)
        except (ValueError, UnicodeError):
            raise ProviderError(502) from None
        if not isinstance(value, dict):
            raise ProviderError(502)
        return response.status, value
    except ProviderError:
        raise
    except Exception:
        raise ProviderError(502) from None
    finally:
        conn.close()


class AuthenticatedTransport:
    """Credencial apenas RAM; OAuth single-tenant em endpoint fixo Microsoft.

    Tokens opacos obtidos diretamente via TLS do endpoint tenant-bound, nunca
    JWT decodificado como prova de assinatura. Sem cache/disco/log/retry.
    """
    def __init__(self, tenant_id, app_id, client_secret):
        if not _uuid(tenant_id) or not _uuid(app_id):
            raise ValueError('invalid_configuration')
        if not isinstance(client_secret, str) or not 1 <= len(client_secret) <= 4096:
            raise ValueError('credential_missing')
        self.tenant_id = tenant_id
        self.app_id = app_id
        self._secret = client_secret

    def _token(self, resource):
        status, body = _https('login.microsoftonline.com', 'POST',
                              '/' + self.tenant_id + '/oauth2/v2.0/token',
                              urlencode({'grant_type': 'client_credentials',
                                         'client_id': self.app_id, 'client_secret': self._secret,
                                         'scope': resource + '/.default'}),
                              {'Content-Type': 'application/x-www-form-urlencoded'})
        token = body.get('access_token')
        if (status != 200 or body.get('token_type', '').lower() != 'bearer'
                or not isinstance(token, str) or not 1 <= len(token) <= 32768
                or any(c.isspace() or ord(c) < 32 or ord(c) > 126 for c in token)):
            raise ProviderError(status if status != 200 else 502)
        return token

    def graph_get(self, path):
        if (not isinstance(path, str) or not path.startswith('/v1.0/')
                or '#' in path or any(ord(c) < 32 for c in path)):
            raise ProviderError(400)
        token = self._token('https://graph.microsoft.com')
        return _https('graph.microsoft.com', 'GET', path,
                      headers={'Authorization': 'Bearer ' + token})


class ConnectorProvider:
    """Uma referência pessoal aprovada, obtida de atividade validada/admin.

    Graph chat ID não é presumido como conversation ID Connector. O operador
    deve vincular os dois explicitamente; URL é origem pública Teams aprovada.
    Nenhum bootstrap por atividade HTTP não autenticada é exposto aqui.
    """
    def __init__(self, transport, target, service_url, connector_conversation_id):
        if (not isinstance(target, PersonalTarget) or target.channel != 'teamsPersonal'
                or target.tenant_id != transport.tenant_id or target.app_id != transport.app_id):
            raise ValueError('invalid_binding')
        parsed = urlsplit(service_url)
        if (parsed.scheme != 'https' or parsed.hostname != 'smba.trafficmanager.net'
                or parsed.netloc != 'smba.trafficmanager.net' or parsed.query or parsed.fragment
                or parsed.path not in ('/teams/', '/amer/', '/emea/', '/apac/')):
            raise ValueError('unapproved_service_url')
        if (not isinstance(connector_conversation_id, str)
                or not 1 <= len(connector_conversation_id) <= 512
                or any(c.isspace() or ord(c) < 32 for c in connector_conversation_id)):
            raise ValueError('invalid_binding')
        self._transport = transport
        self._fingerprint = target.fingerprint
        self._prefix = parsed.path
        self._conversation = connector_conversation_id

    def __call__(self, target, text):
        if (not isinstance(target, PersonalTarget) or target.fingerprint != self._fingerprint
                or not isinstance(text, str) or not 1 <= len(text) <= 4000):
            raise ProviderError(400)
        token = self._transport._token('https://api.botframework.com')
        payload = {'type': 'message', 'text': text, 'textFormat': 'plain',
                   'from': {'id': self._transport.app_id},
                   'conversation': {'id': self._conversation, 'isGroup': False,
                                    'tenantId': self._transport.tenant_id},
                   'channelData': {'tenant': {'id': self._transport.tenant_id}}}
        status, _ = _https('smba.trafficmanager.net', 'POST',
                          self._prefix + 'v3/conversations/' + quote(self._conversation, safe='') + '/activities',
                          json.dumps(payload).encode(),
                          {'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
        return status
