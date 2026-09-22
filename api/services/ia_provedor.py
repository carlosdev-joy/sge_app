"""api/services/ia_provedor.py — provedor de IA compartilhado do Orquestra.

F0 da spec docs/spec-agentes-datastage.md: até 21/09/2026 este módulo se
chamava `caixa_ia.py` e vivia só sob o módulo Caixa Seguro. A configuração é
uma só (provedor, modelo, base_url, chave, proxy) e SEMPRE foi compartilhada —
o Maestro e a triagem de chamados já a liam por aqui —, mas o nome do módulo e
das chaves sugeria o contrário. O módulo Caixa vai sair do Orquestra para
outra ferramenta em breve; a camada de IA fica e passa a servir também os
agentes (docs/spec-agentes-datastage.md) e o que vier depois.

Config em dbo.etl_app_config, chaves `ia_*` (novas) com fallback para as
`caixa_ia_*` (antigas — nenhuma delas é apagada aqui; ver `_LEGADO` abaixo e a
migration 117_ia_provedor_config.sql), gerida em Admin > IA (ações
`ia_get/ia_set/ia_test/ia_verificar`; as `caixa_ia_*` seguem respondendo como
aliases). A chave de API é cifrada com o mesmo Fernet das conexões
(services/conn_crypto, ORQUESTRA_CONN_KEY).

Exceção: `caixa_ia_enabled` NÃO migra — é o interruptor PRÓPRIO dos
assistentes do Caixa Seguro (Diego/Lari/Léo, `routers/caixa_chat.py`), não da
camada de IA (o Maestro tem `maestro_enabled`; a triagem,
`chamados_triagem_habilitada`). Continua com esse nome porque é do módulo
Caixa, e vai com ele quando o módulo sair.

Provedores:
  - anthropic      → SDK oficial `anthropic` (Messages API). Modelo padrão
                     claude-opus-4-8; adaptive thinking (recomendado).
  - openai_compat  → endpoint /chat/completions OpenAI-compatível via httpx
                     (OpenAI, LiteLLM, gateways etc.); exige base_url.
  - caixa_gateway  → o gateway de IA interno da Caixa. Mesma rota
                     /chat/completions, mas autentica por `x-api-key` e
                     responde no formato Anthropic (`content[0].text`) — não
                     cabia em nenhum dos dois acima. Exige base_url. O NOME do
                     provedor não muda: ele nomeia o DESTINO (o gateway da
                     Caixa), não este módulo — os valores gravados em config
                     continuam os mesmos.

A POC Lovable usava o gateway da Lovable (OpenAI-compatível) com
google/gemini-2.5-flash, temperature 0.7 e max_tokens 1000 — o provedor
openai_compat reproduz esses parâmetros.
"""
from __future__ import annotations

import os

import httpx
from fastapi import HTTPException

from db import get_db_conn
from services.conn_crypto import decrypt_password

# Chaves NOVAS (neutras) em dbo.etl_app_config — o provedor compartilhado por
# Maestro, triagem, assistentes do Caixa (por ora) e agentes.
K_PROVIDER = "ia_provider"     # 'anthropic' | 'openai_compat' | 'caixa_gateway'
K_MODEL    = "ia_model"
K_BASE_URL = "ia_base_url"     # openai_compat e caixa_gateway
K_API_KEY  = "ia_api_key_enc"  # Fernet
# '1' faz a chamada respeitar HTTPS_PROXY/NO_PROXY do ambiente. O padrão é '0'
# porque o gateway da Caixa é intranet: com o proxy corporativo no caminho, a
# chamada volta com erro de conexão — o MESMO sintoma de gateway fora do ar.
K_USA_PROXY = "ia_usa_proxy"
# Última verificação de conexão, em JSON curto. Existe para a resposta ficar NA
# TELA: um toast some, e "isso está conectando?" precisa de resposta que
# sobreviva ao refresh.
K_ULTIMA_VERIF = "ia_ultima_verificacao"

# Chaves ANTIGAS (pré-F0). A 117 as copia para as de cima; load_config() lê a
# nova e cai para a antiga quando a nova está vazia; ia_set (admin.py) grava
# nas duas durante a transição — ver `espelhar_legado`. Nunca apagadas aqui:
# a limpeza é uma migration futura, só depois de confirmar dags/+worker.
_LEGADO = {K_PROVIDER: "caixa_ia_provider", K_MODEL: "caixa_ia_model",
           K_BASE_URL: "caixa_ia_base_url", K_API_KEY: "caixa_ia_api_key_enc",
           K_USA_PROXY: "caixa_ia_usa_proxy",
           K_ULTIMA_VERIF: "caixa_ia_ultima_verificacao"}

# O interruptor dos assistentes do Caixa Seguro — NÃO faz parte do provedor
# compartilhado (ver o docstring do módulo). Continua com o nome antigo.
K_ENABLED = "caixa_ia_enabled"

PROVIDERS = ("anthropic", "openai_compat", "caixa_gateway")
DEFAULT_MODEL = {"anthropic": "claude-opus-4-8", "openai_compat": "gpt-4o-mini",
                 "caixa_gateway": "claude-sonnet-4-6"}
# Provedores que não funcionam sem base_url.
PROVIDERS_COM_BASE_URL = ("openai_compat", "caixa_gateway")

# Com adaptive thinking (anthropic) os tokens de raciocínio contam dentro de
# max_tokens — 4096 evita resposta truncada; o texto final continua curto.
MAX_TOKENS = 4096
TIMEOUT_S = 60


def espelhar_legado(valores: dict) -> dict:
    """`{K_PROVIDER: v, ...}` → o mesmo dict acrescido das chaves ANTIGAS
    equivalentes, com o mesmo valor. Usado por `ia_set` (admin.py) para que a
    gravação valha tanto para quem já lê `ia_*` quanto para quem (a triagem no
    worker, por exemplo, se o deploy de `dags/` atrasar) ainda lê `caixa_ia_*`.
    `K_ENABLED` não tem par legado — é passado como está, se vier no dict."""
    espelhado = dict(valores)
    for nova, antiga in _LEGADO.items():
        if nova in valores:
            espelhado[antiga] = valores[nova]
    return espelhado


def load_config(cur=None) -> dict:
    """Lê a config de etl_app_config: chave `ia_*` quando preenchida, senão a
    `caixa_ia_*` equivalente (fallback — nenhuma migration é pré-requisito
    para continuar funcionando). Degrada graciosamente (enabled=False) se a
    tabela não existir ou nada estiver configurado."""
    own_conn = cur is None
    conn = None
    cfg = {"enabled": False, "provider": "anthropic", "model": "",
           "base_url": "", "api_key_enc": "", "usa_proxy": False,
           "ultima_verificacao": ""}
    try:
        if own_conn:
            conn = get_db_conn(); cur = conn.cursor()
        chaves = [K_ENABLED, K_PROVIDER, K_MODEL, K_BASE_URL, K_API_KEY,
                  K_USA_PROXY, K_ULTIMA_VERIF, *_LEGADO.values()]
        marcadores = ",".join("?" * len(chaves))
        cur.execute(
            "SELECT config_key, config_value FROM dbo.etl_app_config "
            f"WHERE config_key IN ({marcadores})", chaves)
        rows = dict(cur.fetchall())

        def _pref(nova: str) -> str:
            valor = (rows.get(nova) or "").strip()
            return valor if valor else (rows.get(_LEGADO[nova]) or "").strip()

        cfg["enabled"] = (rows.get(K_ENABLED) or "").strip() == "1"
        provider = (_pref(K_PROVIDER) or "anthropic")
        cfg["provider"] = provider if provider in PROVIDERS else "anthropic"
        cfg["model"] = _pref(K_MODEL)
        cfg["base_url"] = _pref(K_BASE_URL).rstrip("/")
        cfg["api_key_enc"] = _pref(K_API_KEY)
        cfg["usa_proxy"] = _pref(K_USA_PROXY) == "1"
        cfg["ultima_verificacao"] = _pref(K_ULTIMA_VERIF)
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
                                   "(Admin > IA)")
    return decrypt_password(cfg["api_key_enc"])


async def chat(cfg: dict, system_prompt: str, message: str) -> tuple[str, str]:
    """Envia UMA mensagem ao provedor configurado (os assistentes do Caixa).
    Retorna (resposta, modelo_usado). Levanta HTTPException em erro."""
    return await chat_conversa(cfg, system_prompt, [{"role": "user", "content": message}])


def normalizar_mensagens(mensagens) -> list[dict]:
    """`[{role, content}]` → só user/assistant com conteúdo, começando e
    terminando em user. Papéis iguais seguidos são juntados numa mensagem: a
    Messages API do Anthropic exige alternância e recusaria a conversa inteira
    por duas mensagens do usuário em sequência."""
    saida: list[dict] = []
    for m in mensagens or []:
        if not isinstance(m, dict):
            continue
        papel = str(m.get("role") or "").strip().lower()
        conteudo = str(m.get("content") or "").strip()
        if papel not in ("user", "assistant") or not conteudo:
            continue
        if saida and saida[-1]["role"] == papel:
            saida[-1] = {"role": papel, "content": saida[-1]["content"] + "\n\n" + conteudo}
        else:
            saida.append({"role": papel, "content": conteudo})
    while saida and saida[0]["role"] != "user":
        saida.pop(0)
    if not saida or saida[-1]["role"] != "user":
        raise HTTPException(status_code=422,
                            detail="a conversa precisa terminar com uma mensagem do usuário")
    return saida


def transcrever(mensagens: list[dict]) -> str:
    """O gateway da Caixa só recebe UMA mensagem (ver _corpo_gateway). Uma
    mensagem só vai como está — o corpo fica idêntico ao de `chat`; com
    histórico, vai o transcrito rotulado, terminando no pedido do usuário."""
    if len(mensagens) == 1:
        return mensagens[0]["content"]
    linhas = []
    for m in mensagens:
        rotulo = "Usuário" if m["role"] == "user" else "Assistente"
        linhas.append(f"{rotulo}: {m['content']}")
    return "\n\n".join(linhas)


async def chat_conversa(cfg: dict, system_prompt: str, mensagens,
                        identidade: str | None = None,
                        campo_identidade: str | None = None) -> tuple[str, str]:
    """Conversa multi-rodada (o Maestro, a triagem, os agentes): `mensagens` =
    [{role, content}] com o histórico, terminando na mensagem do usuário.
    Retorna (resposta, modelo).

    `identidade`/`campo_identidade` (F1 da spec docs/spec-agentes-datastage.md,
    os agentes): identificador POR USUÁRIO a mandar ao gateway, e ONDE mandar
    (`'header:NOME'` ou `'body:CAMPO'` — quem decide o valor de
    `campo_identidade` é o chamador, lendo `agentes_gateway_campo_usuario` de
    `etl_app_config`; este módulo não conhece esse nome de config, só recebe
    o resultado). Vale SÓ para o provedor `caixa_gateway` — os outros dois
    não têm esse conceito. Sem os dois parâmetros (o padrão, e o que Maestro/
    triagem/Caixa Seguro continuam usando), o comportamento é EXATAMENTE o de
    antes da F1."""
    msgs = normalizar_mensagens(mensagens)
    provider = cfg.get("provider") or "anthropic"
    model = cfg.get("model") or DEFAULT_MODEL[provider]
    api_key = _api_key(cfg)

    if provider == "anthropic":
        return await _chat_anthropic(api_key, model, system_prompt, msgs), model
    if provider == "caixa_gateway":
        return await _chat_caixa_gateway(cfg, api_key, model, system_prompt, transcrever(msgs),
                                         identidade, campo_identidade), model
    return await _chat_openai_compat(cfg, api_key, model, system_prompt, msgs), model


async def _chat_anthropic(api_key: str, model: str,
                          system_prompt: str, mensagens: list[dict]) -> str:
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
            messages=mensagens,
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
                              system_prompt: str, mensagens: list[dict]) -> str:
    base_url = cfg.get("base_url")
    if not base_url:
        raise HTTPException(status_code=503,
                            detail="Provedor OpenAI-compatível sem base_url configurada "
                                   "(Admin > IA)")
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
            r = await client.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}",
                         "Content-Type": "application/json"},
                json={
                    "model": model,
                    "messages": [{"role": "system", "content": system_prompt}, *mensagens],
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


# ══════════════════════════════════════════════════════════════════════════
# Gateway de IA da Caixa (rede interna)
# ══════════════════════════════════════════════════════════════════════════

def proxy_do_ambiente() -> str:
    """O proxy que o ambiente do container impõe, se houver.

    Serve ao diagnóstico: 'sem proxy porque não há proxy' e 'sem proxy porque
    este provedor o ignora de propósito' são estados diferentes com a mesma
    aparência, e só o segundo é configuração correta para a intranet.
    """
    for v in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
        valor = (os.environ.get(v) or "").strip()
        if valor:
            return valor
    return ""


def _verificacao_tls():
    """O `verify` a usar quando o cliente roda com trust_env desligado.

    `trust_env=False` desliga mais coisa que o proxy: o httpx só honra
    SSL_CERT_FILE e SSL_CERT_DIR com trust_env ligado. Num gateway https com
    CA corporativa entregue por essas variáveis, o handshake falharia como
    `ConnectError` — e o laudo culparia DNS ou rota por um problema de
    certificado, mandando o operador para o time errado. Lendo as variáveis
    aqui, a confiança em CA fica igual à de quem usa trust_env, sem trazer o
    proxy junto.
    """
    arquivo = (os.environ.get("SSL_CERT_FILE") or "").strip()
    if arquivo and os.path.isfile(arquivo):
        return arquivo
    diretorio = (os.environ.get("SSL_CERT_DIR") or "").strip()
    if diretorio and os.path.isdir(diretorio):
        import ssl
        return ssl.create_default_context(capath=diretorio)
    return True


def extrai_texto(payload: dict) -> tuple[str, str]:
    """Devolve (texto, formato) da resposta do gateway.

    Aceita os dois dialetos porque a URL não diz qual virá: o endpoint se chama
    `/chat/completions` (nome do padrão OpenAI) mas hoje responde no formato
    Anthropic, `content[0].text`. Ler só um deles deixaria a integração refém
    de uma troca de versão do gateway que ninguém nos avisaria.
    """
    try:
        blocos = payload.get("content")
        if isinstance(blocos, list) and blocos:
            texto = "".join(b.get("text", "") for b in blocos
                            if isinstance(b, dict) and b.get("type", "text") == "text")
            if texto.strip():
                return texto.strip(), "anthropic (content[].text)"
    except Exception:
        pass
    try:
        texto = (payload["choices"][0]["message"]["content"] or "").strip()
        if texto:
            return texto, "openai (choices[].message.content)"
    except Exception:
        pass
    return "", ""


class GatewayRecusou(Exception):
    """401/403 do gateway QUANDO a chamada levava uma `identidade` por
    usuário (F1 da spec, os agentes): o código sozinho não diz se é o
    usuário que não está cadastrado ou a chave do APP que é inválida — quem
    chama decide isso fazendo uma segunda chamada de controle com a
    identidade do app (ver `sondar_usuario`). Sem `identidade` (Maestro,
    triagem, Caixa Seguro), 401/403 continua um `HTTPException` comum, como
    sempre foi — esta exceção só existe no caminho novo."""

    def __init__(self, status_code: int):
        self.status_code = status_code
        super().__init__(f"Gateway recusou ({status_code})")


def _corpo_gateway(model: str, system_prompt: str, message: str,
                   identidade: str | None = None,
                   campo_identidade: str | None = None) -> tuple[dict, dict]:
    """Monta (headers extras, corpo) do pedido.

    O system entra como prefixo da própria mensagem, e não em campo separado:
    é o que o painel da estação faz hoje contra este mesmo gateway, e um campo
    `system` que o gateway ignorasse levaria a instrução embora sem erro
    nenhum — falha silenciosa, a pior espécie.

    `identidade`/`campo_identidade`: se os dois vierem preenchidos, o
    identificador vai no lugar que `campo_identidade` descreve
    (`'header:NOME'` ou `'body:CAMPO'`); sem os dois (o caso de sempre),
    nada muda no corpo nem nos headers.
    """
    conteudo = f"{system_prompt}\n\n{message}" if system_prompt else message
    corpo = {"model": model,
            "messages": [{"role": "user", "content": conteudo}],
            "max_tokens": MAX_TOKENS}
    headers_extra: dict[str, str] = {}
    if identidade and campo_identidade:
        tipo, _, nome = campo_identidade.partition(":")
        if tipo == "header" and nome:
            headers_extra[nome] = identidade
        elif tipo == "body" and nome:
            corpo[nome] = identidade
    return headers_extra, corpo


async def _chat_caixa_gateway(cfg: dict, api_key: str, model: str,
                              system_prompt: str, message: str,
                              identidade: str | None = None,
                              campo_identidade: str | None = None) -> str:
    base_url = cfg.get("base_url")
    if not base_url:
        raise HTTPException(status_code=503,
                            detail="Gateway da Caixa sem base_url configurada "
                                   "(Admin > IA)")
    headers_extra, corpo = _corpo_gateway(model, system_prompt, message, identidade, campo_identidade)
    try:
        # trust_env=False por padrão: a rota é interna e o proxy corporativo
        # do container derrubaria a chamada. Quem precisar do proxy liga a
        # opção na config — o diagnóstico DIZ qual dos dois está valendo.
        async with httpx.AsyncClient(timeout=TIMEOUT_S,
                                     trust_env=bool(cfg.get("usa_proxy")),
                                     verify=_verificacao_tls()) as client:
            r = await client.post(
                f"{base_url}/chat/completions",
                headers={"x-api-key": api_key, "Content-Type": "application/json", **headers_extra},
                json=corpo,
            )
    except httpx.HTTPError:
        raise HTTPException(status_code=502,
                            detail="Falha de conexão com o gateway de IA da Caixa")
    if r.status_code in (401, 403):
        if identidade is not None:
            # Caminho dos agentes: o código sozinho é ambíguo (usuário sem
            # cadastro × chave do app inválida) — devolve a exceção própria
            # para quem chama decidir com a chamada de controle.
            raise GatewayRecusou(r.status_code)
        raise HTTPException(status_code=502,
                            detail=f"Gateway recusou a chave de API ({r.status_code})")
    if r.status_code == 404:
        raise HTTPException(status_code=502,
                            detail="Endpoint não encontrado no gateway (404) — "
                                   "confira a base_url")
    if r.status_code == 429:
        raise HTTPException(status_code=429,
                            detail="Limite de requisições excedido no gateway de IA")
    if r.status_code >= 400:
        raise HTTPException(status_code=502,
                            detail=f"Erro do gateway de IA ({r.status_code})")
    try:
        payload = r.json()
    except Exception:
        raise HTTPException(status_code=502,
                            detail="Gateway respondeu algo que não é JSON — "
                                   "há um intermediário no caminho?")
    texto, _formato = extrai_texto(payload)
    if not texto:
        raise HTTPException(status_code=502,
                            detail="Resposta do gateway em formato inesperado")
    return texto


# ══════════════════════════════════════════════════════════════════════════
# Verificação de conexão — o diagnóstico que a tela mostra
# ══════════════════════════════════════════════════════════════════════════
#
# Uma frase por ETAPA, e não um "falhou" genérico: config, chave, rede, HTTP e
# formato quebram pelo mesmo sintoma na tela ("não conectou") com causas e
# donos completamente diferentes — configuração, time de acesso, time de rede,
# time do gateway. Sem nomear a etapa, o operador depura no escuro.

VERIF_SYSTEM = "Você é um verificador de conectividade. Responda APENAS a palavra OK."
VERIF_USER = "Teste de conexão do ORQUESTRA — responda OK."
VERIF_TIMEOUT_S = 20


# ══════════════════════════════════════════════════════════════════════════
# Sonda de cadastro por usuário (F1 da spec docs/spec-agentes-datastage.md,
# os agentes) — diferente de `diagnosticar()`: aquela verifica o PROVEDOR
# (a chave do app); esta verifica se UM USUÁRIO está cadastrado no gateway.
# ══════════════════════════════════════════════════════════════════════════

SONDA_OK = "ok"                          # o usuário está cadastrado
SONDA_SEM_CADASTRO = "sem_cadastro"      # o usuário não está — controle com o app funcionou
SONDA_CHAVE_APP_INVALIDA = "chave_do_app_invalida"  # nem o controle com o app funcionou
SONDA_GATEWAY_INDISPONIVEL = "gateway_indisponivel"  # rede/formato/HTTP ≠ 401/403
SONDA_SEM_CONTRATO = "sem_contrato"      # ninguém configurou onde vai o identificador (D-01)
SONDA_SEM_MATRICULA = "sem_matricula"    # sessão sem matrícula — nunca chama o gateway
SONDA_PROVEDOR_INCOMPATIVEL = "provedor_incompativel"  # só caixa_gateway tem identidade por usuário
SONDA_DESLIGADO = "desligado"            # provedor sem chave/base_url — nem tenta

IDENTIDADE_APP = "cvp-orquestra"  # a identidade que Caixa Seguro/Maestro/triagem já usam


async def sondar_usuario(cfg: dict, identidade: str | None, campo_identidade: str | None,
                         identidade_app: str = IDENTIDADE_APP) -> str:
    """Uma chamada mínima para saber se `identidade` está cadastrada no
    gateway. NUNCA levanta — sempre devolve um dos `SONDA_*` acima; quem
    chama decide o cache (TTLs diferentes por estado — ver D-03 da spec) e o
    texto que a tela mostra.

    401/403 sozinho não diz QUEM foi recusado — por isso, quando a chamada
    com `identidade` leva `GatewayRecusou`, uma SEGUNDA chamada, agora com a
    identidade do APP (a mesma que Caixa Seguro/Maestro/triagem já usam),
    decide: controle OK ⇒ o usuário não está cadastrado; controle também
    recusado ⇒ é a chave do app que está errada, não o usuário."""
    if (cfg.get("provider") or "") != "caixa_gateway":
        return SONDA_PROVEDOR_INCOMPATIVEL
    if not cfg.get("api_key_enc") or not cfg.get("base_url"):
        return SONDA_DESLIGADO
    if not campo_identidade:
        return SONDA_SEM_CONTRATO
    if not identidade:
        return SONDA_SEM_MATRICULA
    try:
        await chat_conversa(cfg, VERIF_SYSTEM, [{"role": "user", "content": VERIF_USER}],
                            identidade=identidade, campo_identidade=campo_identidade)
        return SONDA_OK
    except GatewayRecusou:
        pass
    except Exception:  # rede/formato/erro inesperado — nunca derruba a sonda
        return SONDA_GATEWAY_INDISPONIVEL
    try:
        await chat_conversa(cfg, VERIF_SYSTEM, [{"role": "user", "content": VERIF_USER}],
                            identidade=identidade_app, campo_identidade=campo_identidade)
        return SONDA_SEM_CADASTRO
    except GatewayRecusou:
        return SONDA_CHAVE_APP_INVALIDA
    except Exception:
        return SONDA_GATEWAY_INDISPONIVEL


def _diag_base(cfg: dict) -> dict:
    provider = cfg.get("provider") or "anthropic"
    base_url = cfg.get("base_url") or ""
    if provider in PROVIDERS_COM_BASE_URL:
        endpoint = f"{base_url}/chat/completions" if base_url else ""
    else:
        endpoint = "https://api.anthropic.com (SDK oficial)"
    return {
        "ok": False,
        "etapa": "config",
        "mensagem": "",
        "provedor": provider,
        "modelo": cfg.get("model") or DEFAULT_MODEL.get(provider, ""),
        "endpoint": endpoint,
        "proxy_ambiente": proxy_do_ambiente(),
        "usa_proxy": bool(cfg.get("usa_proxy")),
        # Preenchidos com o proxy que o httpx REALMENTE resolveu, lendo o
        # transporte montado. Deduzir a partir da flag e do ambiente erra nos
        # dois sentidos: com NO_PROXY cobrindo o host, "usa proxy" vai direto;
        # e anthropic/openai_compat rodam com trust_env ligado, então passam
        # pelo proxy mesmo com a flag em 0.
        "proxy_em_uso": None,
        "proxy_motivo": None,
        "formato": "",
        "resposta": "",
        "http_status": None,
        "latencia_ms": None,
    }


def _anota_proxy(diag: dict, cliente, url: str) -> None:
    """Registra no laudo o proxy resolvido para esta URL.

    Reusa `services.servicenow.proxy_efetivo` de propósito: ele lê o
    transporte já montado pelo httpx, e o próprio docstring de lá avisa que
    uma segunda implementação da regra divergiria em silêncio.
    """
    try:
        from services.servicenow import proxy_efetivo
        resultado = proxy_efetivo(cliente, url)
        diag["proxy_em_uso"] = resultado.get("em_uso")
        diag["proxy_motivo"] = resultado.get("motivo")
    except Exception:
        diag["proxy_motivo"] = "não foi possível determinar"


async def diagnosticar(cfg: dict) -> dict:
    """Faz uma chamada real ao provedor configurado e descreve o que aconteceu.

    Nunca levanta: um diagnóstico que estoura não diagnostica nada. Toda falha
    volta como `ok: False` com a etapa e a mensagem preenchidas.
    """
    import time as _time

    diag = _diag_base(cfg)
    provider = diag["provedor"]

    if not cfg.get("api_key_enc"):
        diag["mensagem"] = ("Nenhuma chave de API salva. Preencha a chave e "
                            "salve antes de verificar.")
        return diag
    if provider in PROVIDERS_COM_BASE_URL and not cfg.get("base_url"):
        diag["mensagem"] = (f"O provedor {provider} exige a base URL do "
                            "endpoint. Preencha e salve.")
        return diag

    inicio = _time.monotonic()
    try:
        if provider == "caixa_gateway":
            await _verificar_gateway(cfg, diag)
        else:
            # Os outros provedores saem com trust_env ligado (padrão do httpx
            # e do SDK), então o proxy do ambiente VALE para eles — inclusive
            # o NO_PROXY. Quem responde qual é o proxy é o transporte.
            async with httpx.AsyncClient() as sonda:
                _anota_proxy(diag, sonda, cfg.get("base_url")
                             or "https://api.anthropic.com")
            texto, modelo = await chat(cfg, VERIF_SYSTEM, VERIF_USER)
            diag.update(ok=True, etapa="ok", modelo=modelo,
                        resposta=texto[:200], formato="SDK/provedor",
                        mensagem="Provedor respondeu.")
    except HTTPException as e:
        # A etapa que _verificar_gateway alcançou é o dado mais valioso do
        # laudo: sobrescrevê-la com um rótulo genérico joga fora justamente o
        # que esta função existe para dizer.
        if diag["etapa"] == "config":
            diag["etapa"] = "provedor"
        diag["mensagem"] = str(e.detail)
    except Exception as e:  # rede/erro inesperado nunca derruba a verificação
        if diag["etapa"] == "config":
            diag["etapa"] = "inesperado"
        diag["mensagem"] = f"{type(e).__name__}: {e}"
    diag["latencia_ms"] = int((_time.monotonic() - inicio) * 1000)
    return diag


async def _verificar_gateway(cfg: dict, diag: dict) -> None:
    """Chamada crua ao gateway, preenchendo `diag` etapa a etapa."""
    # A decifração vem ANTES de qualquer rede e tem etapa própria: uma
    # ORQUESTRA_CONN_KEY trocada levanta aqui, e sem esta marcação o laudo
    # diria "o provedor recusou" sobre uma requisição que nunca saiu do
    # servidor — culpando exatamente o time errado.
    diag["etapa"] = "chave"
    api_key = _api_key(cfg)
    model = diag["modelo"]
    base_url = cfg["base_url"]
    usa_proxy = bool(cfg.get("usa_proxy"))

    diag["etapa"] = "rede"
    try:
        async with httpx.AsyncClient(timeout=VERIF_TIMEOUT_S,
                                     trust_env=usa_proxy,
                                     verify=_verificacao_tls()) as client:
            _anota_proxy(diag, client, base_url)
            _, corpo = _corpo_gateway(model, VERIF_SYSTEM, VERIF_USER)
            r = await client.post(
                f"{base_url}/chat/completions",
                headers={"x-api-key": api_key, "Content-Type": "application/json"},
                json=corpo,
            )
    except httpx.ConnectTimeout:
        diag["mensagem"] = ("Tempo esgotado ao abrir a conexão. O host responde "
                            "por outra rota? Confira se o servidor enxerga a "
                            "intranet onde o gateway vive.")
        return
    except httpx.ReadTimeout:
        diag["mensagem"] = (f"O gateway aceitou a conexão mas não respondeu em "
                            f"{VERIF_TIMEOUT_S}s — problema no gateway, não na rede.")
        return
    except httpx.ConnectError as e:
        if diag["proxy_em_uso"]:
            diag["mensagem"] = (f"Não conectou usando o proxy "
                                f"{diag['proxy_em_uso']}. Para host interno, "
                                f"desmarque 'usar proxy corporativo'. ({e})")
        elif base_url.lower().startswith("https://"):
            # Em https o ConnectError também cobre handshake TLS recusado —
            # e mandar procurar DNS quando o problema é a CA corporativa faz
            # o operador depurar a rede por horas.
            diag["mensagem"] = (f"Não conectou ao host. Pode ser rota/DNS, ou o "
                                f"certificado do gateway não ser aceito — confira "
                                f"se a CA corporativa está no SSL_CERT_FILE do "
                                f"container. ({e})")
        else:
            diag["mensagem"] = (f"Não conectou ao host. Nome não resolveu ou não "
                                f"há rota até ele a partir do servidor. ({e})")
        return
    except httpx.HTTPError as e:
        diag["mensagem"] = f"Falha de rede: {type(e).__name__}: {e}"
        return

    diag["etapa"] = "http"
    diag["http_status"] = r.status_code
    if r.status_code in (401, 403):
        diag["mensagem"] = (f"O gateway recusou a chave de API ({r.status_code}). "
                            "A chave está correta e habilitada para este servidor?")
        return
    if r.status_code == 404:
        diag["mensagem"] = ("Endpoint não encontrado (404). A base URL deve ser a "
                            "raiz sem /chat/completions — este é acrescentado aqui.")
        return
    if r.status_code == 407:
        diag["mensagem"] = ("O proxy exigiu autenticação (407) — sinal de que a "
                            "chamada passou pelo proxy corporativo. Para host "
                            "interno, desmarque 'usar proxy corporativo'.")
        return
    if r.status_code >= 400:
        diag["mensagem"] = f"O gateway respondeu HTTP {r.status_code}."
        return

    diag["etapa"] = "formato"
    try:
        payload = r.json()
    except Exception:
        diag["mensagem"] = ("A resposta não é JSON. Costuma ser portal de proxy "
                            "ou página de erro no meio do caminho.")
        return
    texto, formato = extrai_texto(payload)
    if not texto:
        # `list(payload)` só funciona em objeto: um JSON escalar (`5`) ou uma
        # lista fariam a linha explodir e o laudo perderia a etapa 'formato'
        # — justamente o diagnóstico correto deste caso.
        if isinstance(payload, dict):
            recebido = f"Chaves recebidas: {list(payload)[:8]}"
        else:
            recebido = f"O corpo veio como {type(payload).__name__}, não objeto."
        diag["mensagem"] = ("Conectou e autenticou, mas a resposta não traz texto "
                            "nem em content[].text nem em choices[].message.content. "
                            + recebido)
        return

    diag.update(ok=True, etapa="ok", resposta=texto[:200], formato=formato,
                mensagem="Gateway respondeu.")
