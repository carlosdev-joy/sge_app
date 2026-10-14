"""Administração F11 write-only; somente lookup faz GET Graph, nunca envio."""
from fastapi import APIRouter, Body, Depends, HTTPException

from db import get_db_conn
from deps import get_admin_user
from services import teams_config
from services import teams_binding
from services.teams_personal import Configuration, resolve

router = APIRouter()


def _operation(body=None, actor=None):
    conn = cur = None
    try:
        # Validar antes de tocar o banco, sem incluir valores em erros.
        if body is not None:
            teams_config.validate(body)
        conn = get_db_conn()
        cur = conn.cursor()
        if body is not None:
            teams_config.save(cur, body, actor)
            conn.commit()
            return teams_config.public_status(body)
        return teams_config.public_status(teams_config.load(cur))
    except teams_config.ConfigurationError as exc:
        validation = {'invalid_configuration', 'credential_invalid', 'configuration_too_large'}
        raise HTTPException(status_code=422 if exc.code in validation else 503,
                            detail=exc.code) from None
    except Exception:
        raise HTTPException(status_code=503, detail='teams_configuration_unavailable') from None
    finally:
        for resource in (cur, conn):
            if resource is not None:
                try:
                    resource.close()
                except Exception:
                    pass


@router.get('/teams-personal/admin/config', tags=['admin'])
def config_get(_admin: dict = Depends(get_admin_user)):
    return _operation()


@router.post('/teams-personal/admin/config', tags=['admin'])
def config_save(body: dict = Body(...), _admin: dict = Depends(get_admin_user)):
    return _operation(body, _admin['matricula'])


def _binding_operation(body, actor, lookup=False):
    conn = cur = None
    try:
        if lookup and (set(body) != {'email'} or not isinstance(body['email'], str)):
            raise teams_config.ConfigurationError('invalid_destination')
        conn = get_db_conn()
        cur = conn.cursor()
        value = teams_config.load(cur)
        if lookup:
            gateway = teams_config.directory(value)
            cfg = Configuration(value['tenant_id'], value['app_id'], value['admin_approved'],
                                value['permissions_verified'], value['gateway_verified'])
            target, error = resolve(cfg, gateway, body['email'])
            if error:
                return {'readiness': error, 'delivery_enabled': False}
            bound = teams_binding.provider(cur, value, target) is not None
            return {'readiness': 'ready' if bound else 'connector_reference_missing',
                    'target_fingerprint': target.fingerprint, 'delivery_enabled': False}
        target = teams_binding.save(cur, body, value, actor)
        conn.commit()
        return {'reference_configured': True, 'target_fingerprint': target.fingerprint,
                'delivery_enabled': False}
    except teams_config.ConfigurationError as exc:
        raise HTTPException(status_code=422 if exc.code in ('invalid_binding', 'invalid_destination') else 503,
                            detail=exc.code) from None
    except Exception:
        raise HTTPException(status_code=503, detail='binding_store_unavailable_migration_184') from None
    finally:
        for resource in (cur, conn):
            if resource is not None:
                try:
                    resource.close()
                except Exception:
                    pass


@router.post('/teams-personal/admin/reference', tags=['admin'])
def reference_save(body: dict = Body(...), _admin: dict = Depends(get_admin_user)):
    return _binding_operation(body, _admin['matricula'])


@router.post('/teams-personal/admin/lookup', tags=['admin'])
def lookup(body: dict = Body(...), _admin: dict = Depends(get_admin_user)):
    return _binding_operation(body, _admin['matricula'], lookup=True)
