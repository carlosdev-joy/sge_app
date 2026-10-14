"""Referência Connector aprovada por admin, cifrada e vinculada ao snapshot exato."""
import json

from services.conn_crypto import encrypt_password, decrypt_password
from services.teams_config import ConfigurationError
from services.teams_personal import PersonalTarget, _uuid
from services.teams_transport import AuthenticatedTransport, ConnectorProvider


def validate(body, config):
    fields = {'tenant_id', 'app_id', 'user_id', 'conversation_id', 'service_url',
              'connector_conversation_id', 'reference_verified'}
    if (not isinstance(body, dict) or set(body) != fields or config is None
            or body['reference_verified'] is not True
            or any(not _uuid(body[k]) for k in ('tenant_id', 'app_id', 'user_id'))
            or body['tenant_id'] != config['tenant_id'] or body['app_id'] != config['app_id']
            or not isinstance(body['conversation_id'], str)
            or not 1 <= len(body['conversation_id']) <= 512
            or any(c.isspace() or ord(c) < 32 for c in body['conversation_id'])):
        raise ConfigurationError('invalid_binding')
    # Graph resolve normaliza o object ID antes de compor o snapshot.
    target = PersonalTarget(body['tenant_id'], body['app_id'], body['user_id'].lower(), body['conversation_id'])
    try:
        transport = AuthenticatedTransport(config['tenant_id'], config['app_id'], config['client_secret'])
        ConnectorProvider(transport, target, body['service_url'], body['connector_conversation_id'])
    except Exception:
        raise ConfigurationError('invalid_binding') from None
    return target


def save(cur, body, config, actor):
    target = validate(body, config)
    try:
        encrypted = encrypt_password(json.dumps(body, separators=(',', ':'), ensure_ascii=True))
    except Exception:
        raise ConfigurationError('encryption_unavailable') from None
    cur.execute(
        'MERGE dbo.etl_teams_personal_binding WITH (HOLDLOCK) AS t '
        'USING (SELECT ? AS k) AS s ON t.target_fingerprint=s.k '
        'WHEN MATCHED THEN UPDATE SET reference_enc=?,updated_by=?,updated_at=SYSUTCDATETIME() '
        'WHEN NOT MATCHED THEN INSERT (target_fingerprint,reference_enc,updated_by) VALUES (?,?,?);',
        (target.fingerprint, encrypted, actor, target.fingerprint, encrypted, actor))
    return target


def provider(cur, config, target):
    try:
        cur.execute('SELECT reference_enc FROM dbo.etl_teams_personal_binding WHERE target_fingerprint=?',
                    (target.fingerprint,))
        row = cur.fetchone()
    except Exception:
        raise ConfigurationError('binding_store_unavailable_migration_184') from None
    if not row:
        return None
    try:
        body = json.loads(decrypt_password(row[0]))
        stored = validate(body, config)
        if stored.fingerprint != target.fingerprint:
            raise ValueError('binding_mismatch')
        transport = AuthenticatedTransport(config['tenant_id'], config['app_id'], config['client_secret'])
        return ConnectorProvider(transport, target, body['service_url'], body['connector_conversation_id'])
    except Exception:
        raise ConfigurationError('binding_unreadable') from None
