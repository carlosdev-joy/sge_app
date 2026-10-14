"""Configuração F11 cifrada, administrada; leitura nunca envia mensagens."""
import json

from services.conn_crypto import decrypt_password, encrypt_password
from services.teams_personal import Configuration, GraphDirectoryGateway, _uuid
from services.teams_transport import AuthenticatedTransport

KEY = 'teams_personal_config_enc'


class ConfigurationError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def validate(body):
    if not isinstance(body, dict):
        raise ConfigurationError('invalid_configuration')
    fields = {'tenant_id', 'app_id', 'catalog_app_id', 'client_secret',
              'admin_approved', 'permissions_verified', 'gateway_verified'}
    if set(body) != fields:
        raise ConfigurationError('invalid_configuration')
    if any(not _uuid(body[k]) for k in ('tenant_id', 'app_id', 'catalog_app_id')):
        raise ConfigurationError('invalid_configuration')
    secret = body['client_secret']
    if (not isinstance(secret, str) or not 1 <= len(secret) <= 4096
            or any(ord(c) < 32 or ord(c) > 126 for c in secret)):
        raise ConfigurationError('credential_invalid')
    if any(type(body[k]) is not bool for k in
           ('admin_approved', 'permissions_verified', 'gateway_verified')):
        raise ConfigurationError('invalid_configuration')
    return dict(body)


def save(cur, body, actor):
    value = validate(body)
    try:
        encrypted = encrypt_password(json.dumps(value, separators=(',', ':'), ensure_ascii=True))
    except Exception:
        raise ConfigurationError('encryption_unavailable') from None
    # etl_app_config.config_value VARCHAR(1000): medir DEPOIS do Fernet.
    if len(encrypted) > 1000:
        raise ConfigurationError('configuration_too_large')
    cur.execute(
        'MERGE dbo.etl_app_config WITH (HOLDLOCK) AS t '
        'USING (SELECT ? AS k) AS s ON t.config_key=s.k '
        'WHEN MATCHED THEN UPDATE SET config_value=?,updated_by=?,updated_at=GETDATE() '
        'WHEN NOT MATCHED THEN INSERT (config_key,config_value,descricao,updated_by,updated_at) '
        'VALUES (?,?,?,?,GETDATE());',
        (KEY, encrypted, actor, KEY, encrypted, 'Teams pessoal — configuração cifrada', actor))


def load(cur):
    try:
        cur.execute('SELECT config_value FROM dbo.etl_app_config WHERE config_key=?', (KEY,))
        row = cur.fetchone()
    except Exception:
        raise ConfigurationError('configuration_store_unavailable') from None
    if not row:
        return None
    try:
        return validate(json.loads(decrypt_password(row[0])))
    except Exception:
        raise ConfigurationError('configuration_unreadable') from None


def public_status(value):
    if value is None:
        return {'configured': False, 'readiness': 'tenant_app_missing', 'delivery_enabled': False}
    cfg = Configuration(value['tenant_id'], value['app_id'], value['admin_approved'],
                        value['permissions_verified'], value['gateway_verified'])
    return {'configured': True, 'readiness': cfg.readiness(), 'delivery_enabled': False}


def directory(value):
    """Bootstrap autenticado de lookup, apenas quando os gates administrativos fecham.

    Não expõe credencial, ativa dispatcher nem cria instalação/conversa.
    Referência Connector aprovada ainda é necessária antes de envio.
    """
    if public_status(value)['readiness'] != 'ready':
        raise ConfigurationError('administrative_readiness_required')
    transport = AuthenticatedTransport(value['tenant_id'], value['app_id'], value['client_secret'])
    return GraphDirectoryGateway(value['tenant_id'], value['app_id'],
                                 value['catalog_app_id'], transport.graph_get)
