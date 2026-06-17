"""api/services/powerbi_client.py — Cliente da REST API do Power BI.

Credenciais (tenant_id, client_id, client_secret, scope, token_url) NÃO ficam em
código nem em variável de ambiente: são parâmetros de sistema gravados em
dbo.etl_app_config (mesma tabela/mecanismo usado por teams_webhook_url etc.),
editáveis em Admin > Configurações.

Chaves esperadas em etl_app_config:
    powerbi_tenant_id      — Directory (tenant) ID do Azure AD
    powerbi_client_id      — Application (client) ID do app registration / service principal
    powerbi_client_secret  — Client secret do app registration (marcado como sensível)
    powerbi_scope          — opcional, default 'https://analysis.windows.net/powerbi/api/.default'
    powerbi_token_url       — opcional, default deriva de powerbi_tenant_id

O service principal só acessa workspaces onde foi adicionado como membro (API
padrão, prefixo /groups). Para os endpoints admin/* (inventário tenant-wide),
é necessário habilitar no Admin Portal do Power BI (Tenant settings > Developer
settings) "Allow service principals to use Power BI APIs" e "...read-only admin
APIs" para o security group desse app — sem isso, todo admin/* responde 401
mesmo com token válido.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Optional

import httpx
from fastapi import HTTPException

from db import get_db_conn

log = logging.getLogger("orquestra-api")

PBI_BASE_URL = "https://api.powerbi.com/v1.0/myorg"
DEFAULT_SCOPE = "https://analysis.windows.net/powerbi/api/.default"
TOKEN_EXPIRY_BUFFER_SEC = 60
HTTP_TIMEOUT = 30

CONFIG_KEYS = (
    "powerbi_tenant_id",
    "powerbi_client_id",
    "powerbi_client_secret",
    "powerbi_scope",
    "powerbi_token_url",
)

# Cache do token em memória do processo (client_credentials não tem refresh_token).
_token_cache: dict[str, Any] = {"access_token": None, "expires_at": 0.0}
_token_lock = asyncio.Lock()


def get_pbi_config() -> dict[str, Optional[str]]:
    """Lê os parâmetros de conexão do Power BI de dbo.etl_app_config."""
    values: dict[str, Optional[str]] = {k: None for k in CONFIG_KEYS}
    try:
        conn = get_db_conn(); cur = conn.cursor()
        placeholders = ",".join("?" for _ in CONFIG_KEYS)
        cur.execute(
            f"SELECT config_key, config_value FROM dbo.etl_app_config WHERE config_key IN ({placeholders})",
            list(CONFIG_KEYS),
        )
        for key, value in cur.fetchall():
            values[key] = (value or "").strip() or None
        cur.close(); conn.close()
    except Exception as e:
        log.warning("Falha ao ler configuração do Power BI em etl_app_config: %s", e)
    return values


def is_configured() -> bool:
    cfg = get_pbi_config()
    return bool(cfg["powerbi_tenant_id"] and cfg["powerbi_client_id"] and cfg["powerbi_client_secret"])


def _resolve_token_url(cfg: dict[str, Optional[str]]) -> str:
    if cfg.get("powerbi_token_url"):
        return cfg["powerbi_token_url"]
    return f"https://login.microsoftonline.com/{cfg['powerbi_tenant_id']}/oauth2/v2.0/token"


async def get_access_token(force_refresh: bool = False) -> str:
    """Retorna um access token válido, renovando via client_credentials se necessário."""
    now = time.time()
    if not force_refresh and _token_cache["access_token"] and now < _token_cache["expires_at"]:
        return _token_cache["access_token"]

    async with _token_lock:
        now = time.time()
        if not force_refresh and _token_cache["access_token"] and now < _token_cache["expires_at"]:
            return _token_cache["access_token"]

        cfg = get_pbi_config()
        if not (cfg["powerbi_tenant_id"] and cfg["powerbi_client_id"] and cfg["powerbi_client_secret"]):
            raise HTTPException(
                status_code=503,
                detail="Power BI não configurado. Preencha powerbi_tenant_id, powerbi_client_id e "
                       "powerbi_client_secret em Admin > Configurações.",
            )

        token_url = _resolve_token_url(cfg)
        scope = cfg.get("powerbi_scope") or DEFAULT_SCOPE
        data = {
            "grant_type": "client_credentials",
            "client_id": cfg["powerbi_client_id"],
            "client_secret": cfg["powerbi_client_secret"],
            "scope": scope,
        }
        try:
            async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
                resp = await client.post(token_url, data=data)
        except httpx.RequestError as e:
            raise HTTPException(status_code=502, detail=f"Erro de rede ao obter token do Power BI: {e}")

        if not resp.is_success:
            detail = resp.text[:300]
            raise HTTPException(
                status_code=502,
                detail=f"Falha ao obter token (HTTP {resp.status_code}) — verifique client_id/client_secret/tenant_id. {detail}",
            )

        body = resp.json()
        access_token = body.get("access_token")
        expires_in = int(body.get("expires_in", 3600))
        if not access_token:
            raise HTTPException(status_code=502, detail="Resposta de token do Power BI sem access_token.")

        _token_cache["access_token"] = access_token
        _token_cache["expires_at"] = time.time() + max(expires_in - TOKEN_EXPIRY_BUFFER_SEC, 30)
        return access_token


def _friendly_error(status_code: int, path: str, body_text: str) -> HTTPException:
    if status_code == 401:
        if path.startswith("admin/"):
            return HTTPException(
                status_code=424,
                detail=(
                    f"Power BI negou acesso (401) ao endpoint admin/{path[6:]}. Isso normalmente significa "
                    "que o Admin Portal do tenant ainda não liberou Admin API para este service principal "
                    "(Tenant settings > Developer settings > 'Allow service principals to use Power BI APIs' "
                    "e '...read-only admin APIs')."
                ),
            )
        return HTTPException(status_code=401, detail="Token do Power BI inválido ou expirado.")
    if status_code == 403:
        return HTTPException(
            status_code=424,
            detail=f"Power BI negou acesso (403) a '{path}'. O service principal provavelmente não é membro "
                   "desse workspace ou não tem permissão sobre esse recurso.",
        )
    if status_code == 404:
        return HTTPException(status_code=404, detail=f"Recurso não encontrado no Power BI: '{path}'.")
    if status_code == 429:
        return HTTPException(status_code=429, detail="Power BI aplicou rate limit (429). Tente novamente em alguns segundos.")
    return HTTPException(status_code=502, detail=f"Power BI retornou HTTP {status_code} em '{path}': {body_text[:300]}")


async def pbi_get(path: str, params: Optional[dict] = None, client: Optional[httpx.AsyncClient] = None) -> dict:
    """GET autenticado contra a API do Power BI. `path` é relativo a /v1.0/myorg/."""
    token = await get_access_token()
    url = f"{PBI_BASE_URL}/{path}"
    headers = {"Authorization": f"Bearer {token}"}

    async def _do(c: httpx.AsyncClient):
        return await c.get(url, params=params, headers=headers, timeout=HTTP_TIMEOUT)

    try:
        if client is not None:
            resp = await _do(client)
        else:
            async with httpx.AsyncClient() as c:
                resp = await _do(c)
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"Erro de rede ao chamar Power BI ({path}): {e}")

    if resp.status_code == 401:
        # token pode ter expirado entre a checagem de cache e a chamada — tenta 1x renovado
        token = await get_access_token(force_refresh=True)
        headers["Authorization"] = f"Bearer {token}"
        try:
            if client is not None:
                resp = await client.get(url, params=params, headers=headers, timeout=HTTP_TIMEOUT)
            else:
                async with httpx.AsyncClient() as c:
                    resp = await c.get(url, params=params, headers=headers, timeout=HTTP_TIMEOUT)
        except httpx.RequestError as e:
            raise HTTPException(status_code=502, detail=f"Erro de rede ao chamar Power BI ({path}): {e}")

    if not resp.is_success:
        raise _friendly_error(resp.status_code, path, resp.text)

    if not resp.text:
        return {}
    return resp.json()
