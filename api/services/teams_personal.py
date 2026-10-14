"""F11: contrato de provider proativo Teams, sem rede/rota/worker ativados.

O gateway futuro deve autenticar Graph/Teams SDK e validar a origem da conversa.
Não instalar apps automaticamente, criar chats Graph ou usar permissões migration.
"""
from dataclasses import dataclass, field
from uuid import UUID
from urllib.parse import quote, urlencode
import hashlib

from services.alert_channels import Result
from services.email_mime import validar_email


def _uuid(value):
    try:
        return isinstance(value, str) and str(UUID(value)) == value.lower()
    except (ValueError, AttributeError):
        return False


@dataclass(frozen=True)
class Configuration:
    tenant_id: str = field(default='', repr=False)
    app_id: str = field(default='', repr=False)
    admin_approved: bool = False
    permissions_verified: bool = False
    gateway_verified: bool = False

    def readiness(self):
        if not _uuid(self.tenant_id) or not _uuid(self.app_id):
            return 'tenant_app_missing'
        if self.admin_approved is not True:
            return 'admin_approval_missing'
        if self.permissions_verified is not True:
            return 'permissions_unverified'
        if self.gateway_verified is not True:
            return 'gateway_unverified'
        return 'ready'


@dataclass(frozen=True)
class PersonalTarget:
    tenant_id: str = field(repr=False)
    app_id: str = field(repr=False)
    user_id: str = field(repr=False)
    conversation_id: str = field(repr=False)
    channel: str = 'teamsPersonal'

    @property
    def fingerprint(self):
        return hashlib.sha256('\0'.join((self.channel, self.tenant_id, self.app_id,
                                        self.user_id, self.conversation_id)).encode()).hexdigest()


class ProviderError(Exception):
    """Não inclui corpo remoto, e-mail, token ou IDs na mensagem."""
    def __init__(self, status):
        self.status = status
        super().__init__('teams_provider_error')


def _code(exc):
    if isinstance(exc, ProviderError):
        if exc.status == 403:
            return 'teams_forbidden'
        if exc.status == 429:
            return 'teams_throttled'
    return 'teams_provider_unavailable'


def resolve(config, gateway, email):
    """Gateway confiável: lookup exato/paginado, instalação e conversa app/user.

    list_users retorna candidatos com id/mail/userPrincipalName/tenant_id.
    personal_conversation retorna vínculo verificado tenant/app/user/scope/id.
    Ausência de vínculo nunca vira fallback de canal ou criação de chat.
    """
    readiness = config.readiness()
    if readiness != 'ready':
        return None, readiness
    if not isinstance(email, str) or len(email) > 254 or not validar_email(email):
        return None, 'invalid_destination'
    try:
        candidates = gateway.list_users(config.tenant_id, email)
        exact = {}
        for user in candidates:
            if (user['tenant_id'] == config.tenant_id and _uuid(user['id'])
                    and any(isinstance(user.get(key), str)
                            and user[key].casefold() == email.casefold()
                            for key in ('mail', 'userPrincipalName'))):
                exact[user['id'].lower()] = user
        if not exact:
            return None, 'user_not_found'
        if len(exact) != 1:
            return None, 'user_ambiguous'
        user_id = next(iter(exact))
        binding = gateway.personal_conversation(config.tenant_id, config.app_id, user_id)
        if binding is None:
            return None, 'app_not_installed'
        if (binding.get('tenant_id') != config.tenant_id
                or binding.get('app_id') != config.app_id
                or binding.get('user_id') != user_id or binding.get('scope') != 'personal'
                or not isinstance(binding.get('id'), str)
                or not 1 <= len(binding['id']) <= 512
                or any(c.isspace() or ord(c) < 32 for c in binding['id'])):
            return None, 'conversation_unverified'
        return PersonalTarget(config.tenant_id, config.app_id, user_id, binding['id']), None
    except Exception as exc:
        return None, _code(exc)


def preview(config, gateway, email):
    """Sem envio, inclusive quando todos os gates estão satisfeitos.

    Provider de transporte ainda indisponível nesta entrega. O dispatcher exige
    autoridade/fence/cutover F9/F10; readiness de identidade não o habilita.
    """
    target, error = resolve(config, gateway, email)
    if error:
        return Result('Failed', error)
    return Result('DryRun') if target else Result('Failed', 'conversation_unverified')


def deliver_target(target, send_proactive, text, *, dry_run=True, authorized_test_fingerprint=None):
    """Adapter Teams SDK proativo injetado pelo operador; nunca POST Graph chat.

    Destino previamente resolvido, callback tenant/app-bound. Ativação durável
    ainda depende de F9/F10. Accepted não confirma recebimento. Nenhum retry.
    """
    if not isinstance(target, PersonalTarget):
        return Result('Failed', 'invalid_destination')
    if dry_run is not False:
        return Result('DryRun')
    if not isinstance(authorized_test_fingerprint, str) or authorized_test_fingerprint != target.fingerprint:
        return Result('Failed', 'test_destination_not_authorized')
    if not isinstance(text, str) or not 1 <= len(text) <= 4000:
        return Result('Failed', 'invalid_message')
    try:
        status = send_proactive(target, text)
        if type(status) is not int:
            return Result('Unknown', 'teams_transport_uncertain')
        if 200 <= status < 300:
            return Result('Accepted')
        if status in (403, 429):
            return Result('Failed', _code(ProviderError(status)))
        return Result('Unknown', 'teams_transport_uncertain')
    except ProviderError as exc:
        # OAuth pode recusar antes do POST; rejeição explícita não é envio incerto.
        if exc.status in (403, 429):
            return Result('Failed', _code(exc))
        return Result('Unknown', 'teams_transport_uncertain')
    except Exception:
        return Result('Unknown', 'teams_transport_uncertain')


class GraphDirectoryGateway:
    """GETs documentados, transport injetado autenticado para um único tenant.

    get_json(path) retorna (status, JSON), sem logs, redirect ou proxy. Não aceita
    URLs remotas/paginação arbitrária: resposta incompleta fecha readiness.
    catalog_app_id é o ID no catálogo Teams, distinto do app/bot Entra.
    Nenhuma chamada aqui envia mensagem ou instala app.
    """
    def __init__(self, tenant_id, app_id, catalog_app_id, get_json):
        if not _uuid(tenant_id) or not _uuid(app_id) or not _uuid(catalog_app_id):
            raise ValueError('invalid_configuration')
        self.tenant_id = tenant_id
        self.app_id = app_id
        self.catalog_app_id = catalog_app_id
        self._get_json = get_json

    def _get(self, path):
        status, body = self._get_json(path)
        if type(status) is not int or status != 200:
            raise ProviderError(status)
        if not isinstance(body, dict) or body.get('@odata.nextLink'):
            raise ProviderError(502)
        return body

    def list_users(self, tenant_id, email):
        if tenant_id != self.tenant_id or not isinstance(email, str) or not validar_email(email):
            raise ProviderError(400)
        literal = email.replace("'", "''")
        query = urlencode({'$filter': f"mail eq '{literal}' or userPrincipalName eq '{literal}'",
                           '$select': 'id,mail,userPrincipalName', '$top': '999'})
        body = self._get('/v1.0/users?' + query)
        return [dict(user, tenant_id=self.tenant_id) for user in body['value']]

    def personal_conversation(self, tenant_id, app_id, user_id):
        if tenant_id != self.tenant_id or app_id != self.app_id or not _uuid(user_id):
            raise ProviderError(400)
        prefix = '/v1.0/users/' + user_id + '/teamwork/installedApps'
        body = self._get(prefix + '?' + urlencode({'$expand': 'teamsApp,teamsAppDefinition'}))
        installs = [item for item in body['value']
                    if item.get('teamsApp', {}).get('id') == self.catalog_app_id]
        if not installs:
            return None
        if len(installs) != 1 or not isinstance(installs[0].get('id'), str) or not installs[0]['id']:
            raise ProviderError(502)
        definition = installs[0].get('teamsAppDefinition', {}).get('id')
        if not isinstance(definition, str) or not definition:
            raise ProviderError(502)
        bot = self._get('/v1.0/appCatalogs/teamsApps/' + self.catalog_app_id
                        + '/appDefinitions/' + quote(definition, safe='') + '/bot')
        if bot.get('id') != self.app_id:
            raise ProviderError(502)
        chat = self._get(prefix + '/' + quote(installs[0]['id'], safe='') + '/chat')
        if chat.get('chatType') != 'oneOnOne':
            raise ProviderError(502)
        return dict(tenant_id=tenant_id, app_id=app_id, user_id=user_id,
                    scope='personal', id=chat.get('id'))
