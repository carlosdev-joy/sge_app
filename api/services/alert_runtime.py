"""Autorização temporária de testes: somente RAM, flag OFF e destino exato.

Não constitui autorização de mensagens de negócio. O administrador instala
uma janela curta para destinos de teste explicitamente autorizados.
"""
import os
import re
import time
from dataclasses import dataclass
from threading import Lock

from fastapi import HTTPException


@dataclass(frozen=True)
class Grant:
    fingerprints: frozenset[str]
    expires: float


_lock = Lock()
_grant = None


def enabled():
    return os.getenv('EOC_ALERT_OPERATIONAL_TEST', '') == '1'


def authorization():
    with _lock:
        grant = _grant
    return grant if enabled() and grant and time.monotonic() < grant.expires else None


def authorize(fingerprints, ttl):
    global _grant
    if not enabled():
        raise HTTPException(503, 'alert_operational_test_disabled')
    if (not isinstance(fingerprints, (list, tuple)) or not 1 <= len(fingerprints) <= 20
            or any(not isinstance(v, str) or re.fullmatch(r'[0-9a-f]{64}', v) is None for v in fingerprints)
            or type(ttl) is not int or not 1 <= ttl <= 3600):
        raise HTTPException(422, 'alert_test_authorization_invalid')
    with _lock:
        _grant = Grant(frozenset(fingerprints), time.monotonic() + ttl)
    return {'authorizedDestinations': len(_grant.fingerprints), 'expiresInSeconds': ttl,
            'scope': 'test_only', 'persisted': False}


def revoke():
    global _grant
    with _lock:
        _grant = None


def require_current(grant):
    # Mesmo objeto impede que uma troca de autorização valide trabalho antigo.
    if authorization() is not grant:
        raise RuntimeError('alert_test_authorization_expired')
