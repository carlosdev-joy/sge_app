"""Identidade por usuário e a sonda de cadastro no gateway — F1 da spec
docs/spec-agentes-datastage.md (a tela Agentes).

O que estes testes prendem, e por que cada um existe:

  1. **Sem `identidade`, nada muda.** Maestro, triagem e os assistentes do
     Caixa Seguro chamam `chat_conversa`/`_chat_caixa_gateway` sem passar
     `identidade` — o corpo, os headers e o tratamento de erro (inclusive o
     401/403 virando `HTTPException(502)`, não `GatewayRecusou`) precisam
     ficar BYTE A BYTE iguais ao que eram antes da F1 (critério 5 da fase).

  2. **`GatewayRecusou` só existe no caminho COM identidade.** É o sinal de
     "401/403 ambíguo" que só faz sentido quando alguém tentou se
     identificar como um usuário específico — sem isso, 401/403 é só "a
     chave do app está errada", como sempre foi.

  3. **A identidade vai para ONDE a config manda**, nunca num lugar fixo no
     código: `campo_identidade` = `'header:NOME'` ou `'body:CAMPO'`, e o
     valor sai exatamente ali. Sem os dois (identidade E campo), nada é
     acrescentado — nem um header vazio.

  4. **A sonda nunca levanta, e nunca faz a 2ª chamada sem precisar.** Cada
     causa (sem contrato, sem matrícula, provedor incompatível, desligado)
     tem que ser decidida ANTES de qualquer chamada de rede — um cliente
     HTTP dublê que quebra se for chamado prova isso.

  5. **A ambiguidade do 401/403 só se resolve com a chamada de controle.**
     Cadastro ausente e chave do app inválida têm o MESMO sintoma na 1ª
     chamada; só divergem na 2ª, feita com a identidade do app.

Nada aqui toca rede: o transporte do httpx é substituído por um mock.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

import httpx
import pytest

if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()
os.environ.setdefault("MSSQL_CONN_STR", "__mock__")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))
from services import ia_provedor  # noqa: E402

BASE = "http://gateway.empresa.intranet/api/claude"
CHAVE = "cvp-teste"


def _cfg(**extra) -> dict:
    cfg = {"enabled": True, "provider": "caixa_gateway",
           "model": "claude-sonnet-4-6", "base_url": BASE,
           "api_key_enc": "cifrado", "usa_proxy": False,
           "ultima_verificacao": ""}
    cfg.update(extra)
    return cfg


@pytest.fixture(autouse=True)
def _chave_em_claro(monkeypatch):
    monkeypatch.setattr(ia_provedor, "decrypt_password", lambda _v: CHAVE)


def _resposta(payload=None, status=200):
    req = httpx.Request("POST", f"{BASE}/chat/completions")
    if payload is None:
        payload = {"content": [{"type": "text", "text": "OK"}]}
    return httpx.Response(status, json=payload, request=req)


class _ClienteUmaResposta:
    """Substitui httpx.AsyncClient por UMA resposta fixa — para o cliente
    NUNCA ser chamado, passe `explode=True` (falha o teste se `post` rodar)."""

    def __init__(self, resposta=None, explode=False, **kwargs):
        self._resposta = resposta
        self._explode = explode
        self.kwargs = kwargs
        self.pedido: dict = {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_a):
        return False

    async def post(self, url, headers=None, json=None):
        if self._explode:
            raise AssertionError("o cliente HTTP não devia ter sido chamado")
        self.pedido = {"url": url, "headers": headers or {}, "json": json or {}}
        return self._resposta


class _ClienteSequencia:
    """Uma resposta (ou exceção) DIFERENTE por chamada, na ordem — para o
    cenário de duas chamadas da sonda (usuário, depois o controle do app)."""

    respostas: list = []  # classe: a instância é recriada a cada `AsyncClient(**kw)`
    pedidos: list = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_a):
        return False

    async def post(self, url, headers=None, json=None):
        type(self).pedidos.append({"url": url, "headers": headers or {}, "json": json or {}})
        item = type(self).respostas.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _instala_sequencia(monkeypatch, *respostas):
    _ClienteSequencia.respostas = list(respostas)
    _ClienteSequencia.pedidos = []
    monkeypatch.setattr(ia_provedor.httpx, "AsyncClient",
                        lambda **kw: _ClienteSequencia(**kw))


# ═══════════ 1. não-regressão: sem identidade, nada muda ═══════════════════

def _instala_uma(monkeypatch, resposta=None, explode=False):
    cliente = _ClienteUmaResposta(resposta, explode=explode)
    monkeypatch.setattr(ia_provedor.httpx, "AsyncClient", lambda **kw: cliente)
    return cliente


@pytest.mark.asyncio
async def test_sem_identidade_401_continua_httpexception_502(monkeypatch):
    """O critério mais importante da F1: quem NUNCA passou `identidade`
    (Maestro, triagem, Caixa Seguro) não pode começar a ver GatewayRecusou."""
    from fastapi import HTTPException
    _instala_uma(monkeypatch, _resposta(status=401))
    with pytest.raises(HTTPException) as exc:
        await ia_provedor.chat_conversa(_cfg(), "sys", [{"role": "user", "content": "oi"}])
    assert exc.value.status_code == 502
    assert "Gateway recusou a chave de API" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_sem_identidade_corpo_e_headers_identicos_a_antes(monkeypatch):
    cliente = _instala_uma(monkeypatch, _resposta())
    await ia_provedor.chat_conversa(_cfg(), "SISTEMA", [{"role": "user", "content": "PERGUNTA"}])
    assert cliente.pedido["headers"] == {"x-api-key": CHAVE, "Content-Type": "application/json"}
    assert cliente.pedido["json"] == {
        "model": "claude-sonnet-4-6",
        "messages": [{"role": "user", "content": "SISTEMA\n\nPERGUNTA"}],
        "max_tokens": ia_provedor.MAX_TOKENS,
    }


# ═══════════ 2. onde a identidade vai (_corpo_gateway) ══════════════════════

def test_corpo_gateway_sem_identidade_nao_muda_nada():
    headers, corpo = ia_provedor._corpo_gateway("m", "sys", "msg")
    assert headers == {}
    assert corpo == {"model": "m", "messages": [{"role": "user", "content": "sys\n\nmsg"}],
                     "max_tokens": ia_provedor.MAX_TOKENS}


def test_corpo_gateway_identidade_em_header():
    headers, corpo = ia_provedor._corpo_gateway("m", "sys", "msg", "cvp-cvp1234", "header:x-user-matricula")
    assert headers == {"x-user-matricula": "cvp-cvp1234"}
    assert "x-user-matricula" not in corpo


def test_corpo_gateway_identidade_em_body():
    headers, corpo = ia_provedor._corpo_gateway("m", "sys", "msg", "cvp-cvp1234", "body:usuario")
    assert headers == {}
    assert corpo["usuario"] == "cvp-cvp1234"


def test_corpo_gateway_identidade_sem_campo_nao_aplica():
    """Os dois são exigidos juntos — identidade sem campo configurado (D-01
    ainda não fechada) não inventa um lugar para mandá-la."""
    headers, corpo = ia_provedor._corpo_gateway("m", "sys", "msg", "cvp-cvp1234", None)
    assert headers == {}
    assert "cvp-cvp1234" not in str(corpo)


@pytest.mark.asyncio
async def test_com_identidade_401_vira_gateway_recusou(monkeypatch):
    cliente = _instala_uma(monkeypatch, _resposta(status=403))
    with pytest.raises(ia_provedor.GatewayRecusou) as exc:
        await ia_provedor.chat_conversa(_cfg(), "sys", [{"role": "user", "content": "oi"}],
                                        identidade="cvp-cvp1234", campo_identidade="header:x-user-matricula")
    assert exc.value.status_code == 403
    assert cliente.pedido["headers"]["x-user-matricula"] == "cvp-cvp1234"


# ═══════════ 3. sondar_usuario: decide sem rede quando dá ═══════════════════

@pytest.mark.asyncio
async def test_sonda_provedor_incompativel_sem_chamar_rede(monkeypatch):
    _instala_uma(monkeypatch, explode=True)
    estado = await ia_provedor.sondar_usuario(_cfg(provider="anthropic"), "cvp-x", "header:n")
    assert estado == ia_provedor.SONDA_PROVEDOR_INCOMPATIVEL


@pytest.mark.asyncio
async def test_sonda_desligado_sem_chave_sem_chamar_rede(monkeypatch):
    _instala_uma(monkeypatch, explode=True)
    estado = await ia_provedor.sondar_usuario(_cfg(api_key_enc=""), "cvp-x", "header:n")
    assert estado == ia_provedor.SONDA_DESLIGADO


@pytest.mark.asyncio
async def test_sonda_sem_contrato_sem_chamar_rede(monkeypatch):
    """D-01 não fechada: nenhum lugar configurado para o identificador."""
    _instala_uma(monkeypatch, explode=True)
    estado = await ia_provedor.sondar_usuario(_cfg(), "cvp-x", None)
    assert estado == ia_provedor.SONDA_SEM_CONTRATO


@pytest.mark.asyncio
async def test_sonda_sem_matricula_sem_chamar_rede(monkeypatch):
    _instala_uma(monkeypatch, explode=True)
    estado = await ia_provedor.sondar_usuario(_cfg(), None, "header:n")
    assert estado == ia_provedor.SONDA_SEM_MATRICULA


@pytest.mark.asyncio
async def test_sonda_ok_uma_chamada_so(monkeypatch):
    _instala_sequencia(monkeypatch, _resposta())
    estado = await ia_provedor.sondar_usuario(_cfg(), "cvp-cvp1234", "header:x-user-matricula")
    assert estado == ia_provedor.SONDA_OK
    assert len(_ClienteSequencia.pedidos) == 1
    assert _ClienteSequencia.pedidos[0]["headers"]["x-user-matricula"] == "cvp-cvp1234"


@pytest.mark.asyncio
async def test_sonda_sem_cadastro_duas_chamadas(monkeypatch):
    """1ª (usuário) 403, 2ª (app) 200 ⇒ o usuário não está cadastrado."""
    _instala_sequencia(monkeypatch, _resposta(status=403), _resposta())
    estado = await ia_provedor.sondar_usuario(_cfg(), "cvp-cvp1234", "header:x-user-matricula")
    assert estado == ia_provedor.SONDA_SEM_CADASTRO
    assert len(_ClienteSequencia.pedidos) == 2
    assert _ClienteSequencia.pedidos[0]["headers"]["x-user-matricula"] == "cvp-cvp1234"
    assert _ClienteSequencia.pedidos[1]["headers"]["x-user-matricula"] == ia_provedor.IDENTIDADE_APP


@pytest.mark.asyncio
async def test_sonda_chave_do_app_invalida_duas_chamadas(monkeypatch):
    """1ª (usuário) 401, 2ª (app) TAMBÉM 401 ⇒ o problema é a chave do app,
    não o cadastro do usuário — os dois falharam do mesmo jeito."""
    _instala_sequencia(monkeypatch, _resposta(status=401), _resposta(status=401))
    estado = await ia_provedor.sondar_usuario(_cfg(), "cvp-cvp1234", "header:x-user-matricula")
    assert estado == ia_provedor.SONDA_CHAVE_APP_INVALIDA


@pytest.mark.asyncio
async def test_sonda_gateway_indisponivel_na_primeira_chamada(monkeypatch):
    _instala_sequencia(monkeypatch, httpx.ConnectError("sem rota"))
    estado = await ia_provedor.sondar_usuario(_cfg(), "cvp-cvp1234", "header:x-user-matricula")
    assert estado == ia_provedor.SONDA_GATEWAY_INDISPONIVEL
    # Só UMA tentativa: erro de rede não é 401/403 ambíguo — não há por que
    # tentar de novo com a identidade do app.
    assert len(_ClienteSequencia.pedidos) == 1


@pytest.mark.asyncio
async def test_sonda_gateway_indisponivel_na_segunda_chamada(monkeypatch):
    """1ª recusa (403), 2ª cai de rede — não é 'sem cadastro', é 'não sei'."""
    _instala_sequencia(monkeypatch, _resposta(status=403), httpx.ConnectError("sem rota"))
    estado = await ia_provedor.sondar_usuario(_cfg(), "cvp-cvp1234", "header:x-user-matricula")
    assert estado == ia_provedor.SONDA_GATEWAY_INDISPONIVEL


@pytest.mark.asyncio
async def test_sonda_nunca_levanta_mesmo_com_erro_inesperado(monkeypatch):
    """A sonda roda a cada abertura da tela — um bug num detalhe qualquer não
    pode derrubar a tela inteira. Erro genuinamente inesperado também vira
    gateway_indisponivel, como diagnosticar() já faz para o mesmo tipo de
    chamada."""
    _instala_sequencia(monkeypatch, RuntimeError("algo bizarro"))
    estado = await ia_provedor.sondar_usuario(_cfg(), "cvp-cvp1234", "header:x-user-matricula")
    assert estado == ia_provedor.SONDA_GATEWAY_INDISPONIVEL
