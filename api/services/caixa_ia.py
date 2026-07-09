"""api/services/caixa_ia.py — provedor LLM dos assistentes do Caixa Seguro.

Config em dbo.etl_app_config (chaves caixa_ia_*), gerida em Admin > Caixa
Seguro IA (actions caixa_ia_get/set/test). A chave de API é cifrada com o
mesmo Fernet das conexões (services/conn_crypto, ORQUESTRA_CONN_KEY).

Provedores:
  - anthropic      → SDK oficial `anthropic` (Messages API). Modelo padrão
                     claude-opus-4-8; adaptive thinking (recomendado).
  - openai_compat  → endpoint /chat/completions OpenAI-compatível via httpx
                     (OpenAI, LiteLLM, gateways etc.); exige base_url.

A POC Lovable usava o gateway da Lovable (OpenAI-compatível) com
google/gemini-2.5-flash, temperature 0.7 e max_tokens 1000 — o provedor
openai_compat reproduz esses parâmetros.
"""
from __future__ import annotations

import httpx
from fastapi import HTTPException

from db import get_db_conn
from services.conn_crypto import decrypt_password

# Chaves em dbo.etl_app_config
K_ENABLED  = "caixa_ia_enabled"      # '1' | '0'
K_PROVIDER = "caixa_ia_provider"     # 'anthropic' | 'openai_compat'
K_MODEL    = "caixa_ia_model"
K_BASE_URL = "caixa_ia_base_url"     # só openai_compat
K_API_KEY  = "caixa_ia_api_key_enc"  # Fernet

PROVIDERS = ("anthropic", "openai_compat")
DEFAULT_MODEL = {"anthropic": "claude-opus-4-8", "openai_compat": "gpt-4o-mini"}

# Com adaptive thinking (anthropic) os tokens de raciocínio contam dentro de
# max_tokens — 4096 evita resposta truncada; o texto final continua curto.
MAX_TOKENS = 4096
TIMEOUT_S = 60


def load_config(cur=None) -> dict:
    """Lê a config caixa_ia_* de etl_app_config. Degrada graciosamente
    (enabled=False) se a tabela não existir ou nada estiver configurado."""
    own_conn = cur is None
    conn = None
    cfg = {"enabled": False, "provider": "anthropic", "model": "",
           "base_url": "", "api_key_enc": ""}
    try:
        if own_conn:
            conn = get_db_conn(); cur = conn.cursor()
        cur.execute(
            "SELECT config_key, config_value FROM dbo.etl_app_config "
            "WHERE config_key IN (?,?,?,?,?)",
            [K_ENABLED, K_PROVIDER, K_MODEL, K_BASE_URL, K_API_KEY])
        rows = dict(cur.fetchall())
        cfg["enabled"] = (rows.get(K_ENABLED) or "").strip() == "1"
        provider = (rows.get(K_PROVIDER) or "anthropic").strip()
        cfg["provider"] = provider if provider in PROVIDERS else "anthropic"
        cfg["model"] = (rows.get(K_MODEL) or "").strip()
        cfg["base_url"] = (rows.get(K_BASE_URL) or "").strip().rstrip("/")
        cfg["api_key_enc"] = (rows.get(K_API_KEY) or "").strip()
    except Exception:
        pass
    finally:
        if own_conn and conn is not None:
            try:
                cur.close(); conn.close()
            except Exception:
                pass
    return cfg


def _api_key(cfg: dict) -> str:
    if not cfg.get("api_key_enc"):
        raise HTTPException(status_code=503,
                            detail="Assistentes IA sem chave de API configurada "
                                   "(Admin > Caixa Seguro IA)")
    return decrypt_password(cfg["api_key_enc"])


async def chat(cfg: dict, system_prompt: str, message: str) -> tuple[str, str]:
    """Envia uma mensagem ao provedor configurado.
    Retorna (resposta, modelo_usado). Levanta HTTPException em erro."""
    provider = cfg.get("provider") or "anthropic"
    model = cfg.get("model") or DEFAULT_MODEL[provider]
    api_key = _api_key(cfg)

    if provider == "anthropic":
        return await _chat_anthropic(api_key, model, system_prompt, message), model
    return await _chat_openai_compat(cfg, api_key, model, system_prompt, message), model


async def _chat_anthropic(api_key: str, model: str,
                          system_prompt: str, message: str) -> str:
    try:
        # import tardio: a lib só é exigida quando o provedor anthropic é usado
        from anthropic import AsyncAnthropic
        import anthropic as _anthropic
    except ImportError:
        raise HTTPException(status_code=500,
                            detail="Biblioteca 'anthropic' não instalada no "
                                   "orquestra-api (pip install anthropic)")
    client = AsyncAnthropic(api_key=api_key, timeout=TIMEOUT_S, max_retries=1)
    try:
        resp = await client.messages.create(
            model=model,
            max_tokens=MAX_TOKENS,
            thinking={"type": "adaptive"},
            system=system_prompt,
            messages=[{"role": "user", "content": message}],
        )
    except _anthropic.AuthenticationError:
        raise HTTPException(status_code=502, detail="Chave de API inválida (Anthropic)")
    except _anthropic.RateLimitError:
        raise HTTPException(status_code=429,
                            detail="Limite de requisições excedido no provedor de IA")
    except _anthropic.APIStatusError as e:
        raise HTTPException(status_code=502, detail=f"Erro do provedor de IA ({e.status_code})")
    except _anthropic.APIConnectionError:
        raise HTTPException(status_code=502, detail="Falha de conexão com o provedor de IA")
    finally:
        await client.close()
    if resp.stop_reason == "refusal":
        raise HTTPException(status_code=502,
                            detail="O provedor de IA recusou a solicitação")
    text = "".join(b.text for b in resp.content if b.type == "text").strip()
    if not text:
        raise HTTPException(status_code=502, detail="Provedor de IA retornou resposta vazia")
    return text


async def _chat_openai_compat(cfg: dict, api_key: str, model: str,
                              system_prompt: str, message: str) -> str:
    base_url = cfg.get("base_url")
    if not base_url:
        raise HTTPException(status_code=503,
                            detail="Provedor OpenAI-compatível sem base_url configurada "
                                   "(Admin > Caixa Seguro IA)")
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
            r = await client.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}",
                         "Content-Type": "application/json"},
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": message},
                    ],
                    "temperature": 0.7,
                    "max_tokens": MAX_TOKENS,
                },
            )
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="Falha de conexão com o provedor de IA")
    if r.status_code == 401:
        raise HTTPException(status_code=502, detail="Chave de API inválida (provedor)")
    if r.status_code == 429:
        raise HTTPException(status_code=429,
                            detail="Limite de requisições excedido no provedor de IA")
    if r.status_code == 402:
        raise HTTPException(status_code=402,
                            detail="Créditos insuficientes no provedor de IA")
    if r.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"Erro do provedor de IA ({r.status_code})")
    try:
        text = (r.json()["choices"][0]["message"]["content"] or "").strip()
    except Exception:
        raise HTTPException(status_code=502, detail="Resposta inesperada do provedor de IA")
    if not text:
        raise HTTPException(status_code=502, detail="Provedor de IA retornou resposta vazia")
    return text
