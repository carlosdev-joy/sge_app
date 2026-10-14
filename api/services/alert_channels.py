"""F10: adapters internos. Não registrados em rota, DAG ou dispatcher.

Reutiliza MIME/sendmail e catálogo de grupos. Cutover real depende de autoridade
certificada e desligamento atômico do emissor legado; esta fase não o ativa.
"""
import hashlib
import json
import ssl
from contextlib import closing
from dataclasses import dataclass, field
from http.client import HTTPSConnection
from urllib.parse import urlsplit

from services import email_config, email_mime, ssh_datastage
from services.alert_outbox import destinations
from services.pipeline_alerts import captured_policy


@dataclass(frozen=True)
class Result:
    outcome: str
    error_code: str | None = None


@dataclass(frozen=True)
class Target:
    channel: str
    value: str = field(repr=False)

    @property
    def fingerprint(self):
        return hashlib.sha256((self.channel + ':' + self.value).encode()).hexdigest()


def resolve(cur, intent_id, *, personal_config=None, personal_gateway=None,
            personal_operational=False):
    """Destino exclusivamente do snapshot original; nunca active publication/default.

    Retorna também o evento confirmado armazenado, sem aceitar corpo do chamador.
    F9 continua restrita a fixtures/dry_run; nenhum resultado é inferido aqui.
    """
    row = cur.execute(
        'SELECT i.channel,i.destination_ref,i.policy_revision,e.event_type,'
        'e.pipeline_name,e.run_id,v.version_id,v.definition_json '
        'FROM dbo.etl_alert_intent i JOIN dbo.etl_alert_event e ON e.id=i.event_id '
        'JOIN dbo.etl_workspace_execucao x ON x.pipeline_name=e.pipeline_name AND x.run_id=e.run_id '
        'JOIN dbo.etl_workspace_versao v ON v.version_id=x.version_id WHERE i.id=?',
        (intent_id,)).fetchone()
    if not row:
        raise ValueError('unbound_destination')
    channel, reference, revision, event, pipeline, run, version, definition = row
    capture = captured_policy(json.loads(definition), str(version))
    if capture['policyRevision'] != revision or (channel, reference) not in destinations(capture, event):
        raise ValueError('snapshot_conflict')
    if channel == 'email':
        index = int(reference.rsplit(':', 1)[1])
        value = capture['policy']['recipients'][index]
        if not email_mime.validar_email(value):
            raise ValueError('invalid_destination')
    elif channel == 'teamsChannel':
        group = capture['policy']['teamsChannel']['groupId']
        found = cur.execute('SELECT webhook_url FROM dbo.etl_msg_grupo WHERE id=? AND ativo=1',
                            (group,)).fetchone()
        value = found[0] if found else None
        if not valid_webhook(value):
            raise ValueError('invalid_destination')
    elif channel == 'teamsPersonal':
        # Import local evita ciclo; readiness padrão permanece fechada.
        from services.teams_personal import Configuration, resolve as resolve_personal
        if personal_operational:
            from services import teams_config
            value = teams_config.load(cur)
            if teams_config.public_status(value)['readiness'] != 'ready':
                raise ValueError('personal_unavailable')
            personal_config = Configuration(value['tenant_id'], value['app_id'],
                                            value['admin_approved'], value['permissions_verified'],
                                            value['gateway_verified'])
            personal_gateway = teams_config.directory(value)
        index = int(reference.rsplit(':', 1)[1])
        recipient = capture['policy']['recipients'][index]
        personal, error = resolve_personal(personal_config or Configuration(), personal_gateway, recipient)
        if error:
            raise ValueError(error)
        return personal, {'event': event, 'pipeline': pipeline, 'run': run}
    else:
        raise ValueError('channel_unavailable')
    return Target(channel, value), {'event': event, 'pipeline': pipeline, 'run': run}


def valid_webhook(value):
    if not isinstance(value, str) or len(value) > 4000 or any(c.isspace() for c in value):
        return False
    try:
        url = urlsplit(value)
        host = url.hostname or ''
        # Apenas hosts do transporte Teams existente; nunca IP, localhost ou redirect.
        allowed = any(host.endswith(suffix) for suffix in (
            '.webhook.office.com', '.logic.azure.com', '.environment.api.powerplatform.com'))
        return (url.scheme == 'https' and allowed and url.port in (None, 443)
                and not url.username and not url.password and not url.fragment and bool(url.path.strip('/')))
    except ValueError:
        return False


def deliver(cur, intent_id, *, dry_run=True, authorized_test_fingerprint=None,
            before_send=None, authorized_test_fingerprints=None):
    """Harness interno: opt-in real exige fingerprint exata de destino de teste.

    A autorização é fornecida pelo operador em RAM, nunca por configuração/API.
    Esta função não muda job/run nem faz retry. Exceção ambígua vira Unknown.
    O chamador futuro deve persistir claim/resultado e validar exclusão do legado.
    """
    try:
        target, context = resolve(cur, intent_id, personal_operational=dry_run is False)
        if dry_run is not False:
            return Result('DryRun')
        if authorized_test_fingerprints is not None and target.fingerprint in authorized_test_fingerprints:
            authorized_test_fingerprint = target.fingerprint
        if not isinstance(authorized_test_fingerprint, str) or authorized_test_fingerprint != target.fingerprint:
            return Result('Failed', 'test_destination_not_authorized')
        title = 'Orquestra — ' + context['event']
        # Conteúdo mínimo de evento; sem templates SQL/anexos dos nós customizados.
        text = 'Pipeline: ' + context['pipeline'] + '\nCorrida: ' + context['run']
        if target.channel == 'teamsPersonal':
            from services import teams_binding, teams_config
            from services.teams_personal import deliver_target
            # Referência aprovada exata; conversa Graph nunca vira webhook/canal.
            value = teams_config.load(cur)
            if teams_config.public_status(value)['readiness'] != 'ready':
                return Result('Failed', 'invalid_destination')
            provider = teams_binding.provider(cur, value, target)
            if provider is None:
                return Result('Failed', 'invalid_destination')
            from services.teams_transport import fenced_requests
            with fenced_requests(before_send):
                return deliver_target(target, provider, title + '\n' + text, dry_run=False,
                                      authorized_test_fingerprint=authorized_test_fingerprint)
        if target.channel == 'email':
            cfg = email_config.load_config(cur)
            addresses, errors = email_mime.validar_destinatarios([target.value], cfg['dominios'])
            if (not cfg['disponivel'] or not cfg['enabled'] or cfg['erro'] or errors
                    or not email_mime.validar_email(cfg['remetente'])):
                return Result('Failed', 'email_configuration_unavailable')
            # Texto do pipeline escapado antes do render MIME HTML existente.
            import html
            message = email_mime.montar_mensagem(cfg['remetente'], addresses, title,
                                                  '<pre>' + html.escape(text) + '</pre>')
            kwargs = {'before_send': before_send} if before_send is not None else {}
            response = ssh_datastage.run_sendmail(message, cfg['remetente'], timeout=15, **kwargs)
            code = response.get('exit_code')
            if type(code) is not int or code < 0:
                return Result('Unknown', 'transport_uncertain')
            return Result('Accepted') if code == 0 else Result('Failed', 'email_rejected')
        card = {'type': 'message', 'attachments': [{
            'contentType': 'application/vnd.microsoft.card.adaptive',
            'content': {'type': 'AdaptiveCard', 'version': '1.2', 'body': [
                {'type': 'TextBlock', 'text': title, 'wrap': True},
                {'type': 'TextBlock', 'text': text, 'wrap': True}]}}]}
        # Mesmo POST/card do emissor existente. HTTPX registra URL assinada em INFO;
        # http.client não usa esses loggers/proxies e não segue redirects.
        url = urlsplit(target.value)
        path = url.path + ('?' + url.query if url.query else '')
        with closing(HTTPSConnection(url.hostname, url.port or 443, timeout=15,
                                     context=ssl.create_default_context())) as client:
            client.set_debuglevel(0)
            # Connect pode consumir a lease: revalidar após TLS e antes do POST.
            if before_send is not None:
                client.connect()
                before_send()
            client.request('POST', path, body=json.dumps(card, ensure_ascii=False).encode('utf-8'),
                           headers={'Content-Type': 'application/json; charset=utf-8'})
            status = client.getresponse().status
        if 200 <= status < 300:
            return Result('Accepted')
        return Result('Failed', 'teams_rejected')
    except ValueError:
        return Result('Failed', 'invalid_destination')
    except Exception:
        # Não copiar exception, webhook, stderr, host SSH ou corpo para log/fila.
        # Mesmo falha de leitura/config é conservadora: nunca reenviar cegamente.
        return Result('Unknown', 'transport_uncertain')
