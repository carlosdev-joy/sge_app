"""caixa_ia.chat_conversa — a conversa multi-rodada que o Maestro usa (F1 da
spec docs/spec-maestro-parametros.md).

O que se prende:

  1. **`chat` não mudou de comportamento.** Uma mensagem só continua indo ao
     gateway da Caixa como antes (o corpo é byte a byte o de sempre) — os
     assistentes do Caixa não podem sentir a F1.
  2. **Alternância.** A Messages API do Anthropic recusa dois `user` seguidos;
     `normalizar_mensagens` junta papéis iguais, descarta o que vem antes do
     primeiro `user` e exige terminar em `user` (422, não 500 do provedor).
  3. **Cada provedor recebe o histórico do seu jeito.** Anthropic e
     OpenAI-compatível recebem a lista; o gateway da Caixa recebe o transcrito
     rotulado numa mensagem só (ele só aceita uma).

Nada toca rede: o transporte é substituído por dublês.
"""
from __future__ import annotations

import os
import sys
import types
from unittest.mock import MagicMock

import httpx
import pytest
from fastapi import HTTPException

if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()
os.environ.setdefault("MSSQL_CONN_STR", "__mock__")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))

from services import caixa_ia  # noqa: E402

BASE = "http://gateway.empresa.intranet/api/claude"


@pytest.fixture(autouse=True)
def _chave(monkeypatch):
    monkeypatch.setattr(caixa_ia, "decrypt_password", lambda _v: "chave")


def _cfg(provider="caixa_gateway", **extra):
    cfg = {"enabled": True, "provider": provider, "model": "", "base_url": BASE,
           "api_key_enc": "cifrado", "usa_proxy": False, "ultima_verificacao": ""}
    cfg.update(extra)
    return cfg


class _Cliente:
    ultima = None

    def __init__(self, resposta, **kwargs):
        self._resposta, self.kwargs, self.pedido = resposta, kwargs, {}
        _Cliente.ultima = self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_a):
        return False

    async def post(self, url, headers=None, json=None):
        self.pedido = {"url": url, "headers": headers or {}, "json": json or {}}
        return self._resposta


def _resp(payload):
    return httpx.Response(200, json=payload, request=httpx.Request("POST", f"{BASE}/chat/completions"))


HIST = [{"role": "user", "content": "mês anterior"},
        {"role": "assistant", "content": "Quais nomes?"},
        {"role": "user", "content": "pDataIni e pDataFim"}]


# ═══════════ 1. normalização ═════════════════════════════════════════════════

def test_normalizar_junta_papeis_iguais_e_descarta_o_que_vem_antes_do_user():
    msgs = caixa_ia.normalizar_mensagens([
        {"role": "assistant", "content": "olá"},            # antes do 1º user: fora
        {"role": "system", "content": "x"}, "lixo", None,    # ignorados
        {"role": "USER", "content": " a "}, {"role": "user", "content": "b"},
        {"role": "assistant", "content": "r"}, {"role": "assistant", "content": ""},
        {"role": "user", "content": "c"}])
    assert msgs == [{"role": "user", "content": "a\n\nb"}, {"role": "assistant", "content": "r"},
                    {"role": "user", "content": "c"}]


@pytest.mark.parametrize("mensagens", [[], None, [{"role": "assistant", "content": "só eu"}],
                                       [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}],
                                       [{"role": "user", "content": "   "}]])
def test_normalizar_exige_terminar_em_user(mensagens):
    with pytest.raises(HTTPException) as e:
        caixa_ia.normalizar_mensagens(mensagens)
    assert e.value.status_code == 422


def test_transcrever_uma_mensagem_vai_como_esta_e_historico_rotulado():
    assert caixa_ia.transcrever([{"role": "user", "content": "PERGUNTA"}]) == "PERGUNTA"
    assert caixa_ia.transcrever(HIST) == ("Usuário: mês anterior\n\nAssistente: Quais nomes?\n\n"
                                          "Usuário: pDataIni e pDataFim")


# ═══════════ 2. gateway da Caixa ═════════════════════════════════════════════

async def test_chat_de_uma_mensagem_manda_o_corpo_de_sempre(monkeypatch):
    monkeypatch.setattr(caixa_ia.httpx, "AsyncClient",
                        lambda **kw: _Cliente(_resp({"content": [{"type": "text", "text": "OK"}]}), **kw))
    texto, modelo = await caixa_ia.chat(_cfg(), "INSTRUCAO", "PERGUNTA")
    assert texto == "OK" and modelo == caixa_ia.DEFAULT_MODEL["caixa_gateway"]
    assert _Cliente.ultima.pedido["json"] == {
        "model": modelo, "messages": [{"role": "user", "content": "INSTRUCAO\n\nPERGUNTA"}],
        "max_tokens": caixa_ia.MAX_TOKENS}
    assert _Cliente.ultima.pedido["headers"]["x-api-key"] == "chave"


async def test_chat_conversa_no_gateway_manda_o_transcrito_numa_mensagem(monkeypatch):
    monkeypatch.setattr(caixa_ia.httpx, "AsyncClient",
                        lambda **kw: _Cliente(_resp({"content": [{"type": "text", "text": "R"}]}), **kw))
    texto, _ = await caixa_ia.chat_conversa(_cfg(), "SYS", HIST)
    assert texto == "R"
    msgs = _Cliente.ultima.pedido["json"]["messages"]
    assert len(msgs) == 1 and msgs[0]["role"] == "user"
    assert msgs[0]["content"] == "SYS\n\n" + caixa_ia.transcrever(HIST)
    assert _Cliente.ultima.kwargs["trust_env"] is False


# ═══════════ 3. OpenAI-compatível ════════════════════════════════════════════

async def test_chat_conversa_openai_compat_manda_system_mais_a_lista(monkeypatch):
    monkeypatch.setattr(caixa_ia.httpx, "AsyncClient",
                        lambda **kw: _Cliente(_resp({"choices": [{"message": {"content": "R"}}]}), **kw))
    texto, modelo = await caixa_ia.chat_conversa(_cfg("openai_compat"), "SYS", HIST)
    assert texto == "R" and modelo == caixa_ia.DEFAULT_MODEL["openai_compat"]
    corpo = _Cliente.ultima.pedido["json"]
    assert corpo["messages"] == [{"role": "system", "content": "SYS"}, *HIST]
    assert _Cliente.ultima.pedido["headers"]["Authorization"] == "Bearer chave"


# ═══════════ 4. Anthropic (SDK) ══════════════════════════════════════════════

class _Bloco:
    def __init__(self, text):
        self.type, self.text = "text", text


class _Resposta:
    stop_reason = "end_turn"
    content = [_Bloco("R")]


class _SdkFake:
    chamadas: list[dict] = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.messages = self

    async def create(self, **kwargs):
        _SdkFake.chamadas.append(kwargs)
        return _Resposta()

    async def close(self):
        pass


@pytest.fixture
def sdk_anthropic(monkeypatch):
    mod = types.ModuleType("anthropic")
    mod.AsyncAnthropic = _SdkFake
    for nome in ("AuthenticationError", "RateLimitError", "APIStatusError", "APIConnectionError"):
        setattr(mod, nome, type(nome, (Exception,), {}))
    monkeypatch.setitem(sys.modules, "anthropic", mod)
    _SdkFake.chamadas.clear()
    return mod


async def test_chat_conversa_anthropic_manda_a_lista_alternada(sdk_anthropic):
    texto, modelo = await caixa_ia.chat_conversa(_cfg("anthropic"), "SYS", HIST)
    assert texto == "R" and modelo == caixa_ia.DEFAULT_MODEL["anthropic"]
    chamada = _SdkFake.chamadas[0]
    assert chamada["system"] == "SYS" and chamada["messages"] == HIST
    assert chamada["thinking"] == {"type": "adaptive"}


async def test_chat_anthropic_de_uma_mensagem_continua_igual(sdk_anthropic):
    await caixa_ia.chat(_cfg("anthropic"), "SYS", "PERGUNTA")
    assert _SdkFake.chamadas[0]["messages"] == [{"role": "user", "content": "PERGUNTA"}]


async def test_chat_conversa_valida_antes_de_exigir_a_chave():
    """Conversa malformada é 422 do chamador — não um 503 'sem chave'."""
    with pytest.raises(HTTPException) as e:
        await caixa_ia.chat_conversa(_cfg(api_key_enc=""), "SYS", [{"role": "assistant", "content": "x"}])
    assert e.value.status_code == 422
