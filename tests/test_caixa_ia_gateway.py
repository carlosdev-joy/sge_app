"""Provedor do gateway de IA da Caixa e a verificação de conexão (F1).

O que estes testes prendem, e por que cada um existe:

  1. **O dialeto do gateway não é o do openai_compat.** Ele autentica por
     `x-api-key` (e não `Authorization: Bearer`) e responde `content[0].text`
     (e não `choices[0].message.content`), apesar de a rota se chamar
     `/chat/completions`. Um provedor que mande o header errado leva 401, e um
     que leia o campo errado dá "resposta vazia" com o gateway funcionando.

  2. **O proxy não pode entrar no caminho por acidente.** O container tem
     HTTPS_PROXY no ambiente e o httpx, com `trust_env` (padrão), o respeita.
     O gateway é intranet: a chamada precisa nascer com `trust_env=False`,
     senão volta erro de conexão — o MESMO sintoma de gateway fora do ar, que
     manda o operador caçar rede em vez de configuração.

  3. **O diagnóstico nomeia a etapa.** "Falhou" genérico não diz se o dono do
     problema é a configuração, o time de acesso ou o time de rede. Cada
     modo de falha aqui é medido pela etapa que ele reporta.

  4. **A verificação nunca estoura.** Um diagnóstico que levanta exceção não
     diagnostica nada: toda falha volta como `ok: False` preenchido.

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
from services import caixa_ia  # noqa: E402

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
    """A chave real é Fernet; aqui o decrypt é substituído."""
    monkeypatch.setattr(caixa_ia, "decrypt_password", lambda _v: CHAVE)


class _ClienteFake:
    """Substitui httpx.AsyncClient guardando como foi construído e chamado."""

    ultima: "_ClienteFake | None" = None

    def __init__(self, resposta, **kwargs):
        self._resposta = resposta
        self.kwargs = kwargs
        self.pedido: dict = {}
        _ClienteFake.ultima = self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_a):
        return False

    async def post(self, url, headers=None, json=None):
        self.pedido = {"url": url, "headers": headers or {}, "json": json or {}}
        if isinstance(self._resposta, Exception):
            raise self._resposta
        return self._resposta


def _resposta(payload, status=200, texto_cru=None):
    req = httpx.Request("POST", f"{BASE}/chat/completions")
    if texto_cru is not None:
        return httpx.Response(status, text=texto_cru, request=req)
    return httpx.Response(status, json=payload, request=req)


def _instala(monkeypatch, resposta):
    monkeypatch.setattr(caixa_ia.httpx, "AsyncClient",
                        lambda **kw: _ClienteFake(resposta, **kw))


# ── 1. dialeto do gateway ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_le_formato_anthropic(monkeypatch):
    _instala(monkeypatch, _resposta({"content": [{"type": "text", "text": "OK"}]}))
    texto, modelo = await caixa_ia.chat(_cfg(), "sistema", "mensagem")
    assert texto == "OK"
    assert modelo == "claude-sonnet-4-6"


@pytest.mark.asyncio
async def test_le_formato_openai_como_fallback(monkeypatch):
    """Se o gateway trocar de dialeto, a leitura não pode morrer junto."""
    _instala(monkeypatch, _resposta(
        {"choices": [{"message": {"content": "OK"}}]}))
    texto, _ = await caixa_ia.chat(_cfg(), "sistema", "mensagem")
    assert texto == "OK"


@pytest.mark.asyncio
async def test_autentica_por_x_api_key(monkeypatch):
    _instala(monkeypatch, _resposta({"content": [{"text": "OK"}]}))
    await caixa_ia.chat(_cfg(), "sistema", "mensagem")
    headers = _ClienteFake.ultima.pedido["headers"]
    assert headers["x-api-key"] == CHAVE
    assert "Authorization" not in headers


@pytest.mark.asyncio
async def test_system_viaja_dentro_da_mensagem(monkeypatch):
    """Campo `system` que o gateway ignorasse perderia a instrução em
    silêncio; por isso ele entra no corpo da própria mensagem."""
    _instala(monkeypatch, _resposta({"content": [{"text": "OK"}]}))
    await caixa_ia.chat(_cfg(), "INSTRUCAO-DO-SISTEMA", "PERGUNTA")
    corpo = _ClienteFake.ultima.pedido["json"]
    assert len(corpo["messages"]) == 1
    assert "INSTRUCAO-DO-SISTEMA" in corpo["messages"][0]["content"]
    assert "PERGUNTA" in corpo["messages"][0]["content"]


@pytest.mark.asyncio
async def test_url_recebe_chat_completions(monkeypatch):
    _instala(monkeypatch, _resposta({"content": [{"text": "OK"}]}))
    await caixa_ia.chat(_cfg(), "s", "m")
    assert _ClienteFake.ultima.pedido["url"] == f"{BASE}/chat/completions"


# ── 2. proxy ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_nao_usa_proxy_por_padrao(monkeypatch):
    _instala(monkeypatch, _resposta({"content": [{"text": "OK"}]}))
    await caixa_ia.chat(_cfg(), "s", "m")
    assert _ClienteFake.ultima.kwargs["trust_env"] is False


@pytest.mark.asyncio
async def test_usa_proxy_quando_configurado(monkeypatch):
    _instala(monkeypatch, _resposta({"content": [{"text": "OK"}]}))
    await caixa_ia.chat(_cfg(usa_proxy=True), "s", "m")
    assert _ClienteFake.ultima.kwargs["trust_env"] is True


def test_proxy_do_ambiente_reporta_variavel(monkeypatch):
    for v in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
        monkeypatch.delenv(v, raising=False)
    assert caixa_ia.proxy_do_ambiente() == ""
    monkeypatch.setenv("HTTPS_PROXY", "http://webproxy.empresa:8080")
    assert caixa_ia.proxy_do_ambiente() == "http://webproxy.empresa:8080"


# ── 3. diagnóstico: cada falha nomeia a sua etapa ────────────────────────

@pytest.mark.asyncio
async def test_diagnostico_sucesso(monkeypatch):
    _instala(monkeypatch, _resposta({"content": [{"text": "OK"}]}))
    d = await caixa_ia.diagnosticar(_cfg())
    assert d["ok"] is True
    assert d["etapa"] == "ok"
    assert d["resposta"] == "OK"
    assert "anthropic" in d["formato"]
    assert d["latencia_ms"] is not None
    assert d["endpoint"] == f"{BASE}/chat/completions"


@pytest.mark.asyncio
async def test_diagnostico_sem_chave_nao_chama_rede(monkeypatch):
    def _explode(**_kw):
        raise AssertionError("não deveria abrir conexão sem chave")
    monkeypatch.setattr(caixa_ia.httpx, "AsyncClient", _explode)
    d = await caixa_ia.diagnosticar(_cfg(api_key_enc=""))
    assert d["ok"] is False
    assert d["etapa"] == "config"
    assert "chave" in d["mensagem"].lower()


@pytest.mark.asyncio
async def test_diagnostico_sem_base_url(monkeypatch):
    d = await caixa_ia.diagnosticar(_cfg(base_url=""))
    assert d["ok"] is False
    assert d["etapa"] == "config"
    assert "base url" in d["mensagem"].lower()


@pytest.mark.asyncio
async def test_diagnostico_host_inalcancavel_fala_de_rota(monkeypatch):
    _instala(monkeypatch, httpx.ConnectError("nome não resolvido"))
    d = await caixa_ia.diagnosticar(_cfg())
    assert d["etapa"] == "rede"
    assert "rota" in d["mensagem"].lower() or "resolveu" in d["mensagem"].lower()


@pytest.mark.asyncio
async def test_diagnostico_com_proxy_culpa_o_proxy(monkeypatch):
    """Mesmo erro de conexão, causa diferente: quando o proxy ESTÁ no caminho
    a mensagem tem de apontá-lo, senão o operador vai depurar a rede.

    O gatilho é o proxy que o transporte resolveu — não a opção marcada na
    tela. Com NO_PROXY isentando o host, a opção está ligada e o proxy não
    entra em campo; culpá-lo ali seria mandar o operador para o lugar errado.
    """
    monkeypatch.setenv("HTTPS_PROXY", "http://webproxy.empresa:8080")
    monkeypatch.setattr(
        "services.servicenow.proxy_efetivo",
        lambda _cli, _url: {"em_uso": "http://webproxy.empresa:8080", "motivo": None})
    _instala(monkeypatch, httpx.ConnectError("recusado"))
    d = await caixa_ia.diagnosticar(_cfg(usa_proxy=True))
    assert d["etapa"] == "rede"
    assert "proxy" in d["mensagem"].lower()


@pytest.mark.asyncio
async def test_diagnostico_401_fala_de_chave(monkeypatch):
    _instala(monkeypatch, _resposta({"erro": "nao autorizado"}, status=401))
    d = await caixa_ia.diagnosticar(_cfg())
    assert d["etapa"] == "http"
    assert d["http_status"] == 401
    assert "chave" in d["mensagem"].lower()


@pytest.mark.asyncio
async def test_diagnostico_407_fala_de_proxy(monkeypatch):
    _instala(monkeypatch, _resposta({}, status=407))
    d = await caixa_ia.diagnosticar(_cfg())
    assert d["etapa"] == "http"
    assert "proxy" in d["mensagem"].lower()


@pytest.mark.asyncio
async def test_diagnostico_404_fala_de_base_url(monkeypatch):
    _instala(monkeypatch, _resposta({}, status=404))
    d = await caixa_ia.diagnosticar(_cfg())
    assert d["etapa"] == "http"
    assert "base url" in d["mensagem"].lower()


@pytest.mark.asyncio
async def test_diagnostico_resposta_nao_json(monkeypatch):
    """Portal de proxy devolve HTML com 200 — conectar não é conectar certo."""
    _instala(monkeypatch, _resposta(None, texto_cru="<html>bloqueado</html>"))
    d = await caixa_ia.diagnosticar(_cfg())
    assert d["ok"] is False
    assert d["etapa"] == "formato"
    assert "json" in d["mensagem"].lower()


@pytest.mark.asyncio
async def test_diagnostico_json_sem_texto_lista_as_chaves(monkeypatch):
    _instala(monkeypatch, _resposta({"resultado": "algo", "id": 1}))
    d = await caixa_ia.diagnosticar(_cfg())
    assert d["ok"] is False
    assert d["etapa"] == "formato"
    assert "resultado" in d["mensagem"]


@pytest.mark.asyncio
async def test_diagnostico_nunca_levanta(monkeypatch):
    """Erro inesperado vira laudo, não exceção — e a etapa alcançada
    SOBREVIVE. Trocá-la por 'inesperado' apagaria a informação mais útil do
    laudo (onde o processo parou), que é o motivo de ele existir."""
    _instala(monkeypatch, RuntimeError("pane geral"))
    d = await caixa_ia.diagnosticar(_cfg())
    assert d["ok"] is False
    assert d["etapa"] == "rede", "o erro estourou durante a chamada de rede"
    assert "pane geral" in d["mensagem"]


@pytest.mark.asyncio
async def test_erro_antes_de_qualquer_etapa_vira_inesperado(monkeypatch):
    """Só quando nem a primeira etapa foi alcançada o rótulo genérico vale."""
    monkeypatch.setattr(caixa_ia, "_verificar_gateway",
                        MagicMock(side_effect=RuntimeError("pane precoce")))
    d = await caixa_ia.diagnosticar(_cfg())
    assert d["etapa"] == "inesperado"


# ── 4. contrato do provedor na configuração ──────────────────────────────

def test_gateway_esta_na_lista_de_provedores():
    assert "caixa_gateway" in caixa_ia.PROVIDERS
    assert "caixa_gateway" in caixa_ia.PROVIDERS_COM_BASE_URL
    assert caixa_ia.DEFAULT_MODEL["caixa_gateway"] == "claude-sonnet-4-6"


def test_extrai_texto_reconhece_os_dois_dialetos():
    t, f = caixa_ia.extrai_texto({"content": [{"type": "text", "text": " oi "}]})
    assert (t, "anthropic" in f) == ("oi", True)
    t, f = caixa_ia.extrai_texto({"choices": [{"message": {"content": "oi"}}]})
    assert (t, "openai" in f) == ("oi", True)
    assert caixa_ia.extrai_texto({"nada": 1}) == ("", "")


# ── 5. o que a revisão adversarial pegou ─────────────────────────────────
# Cada teste aqui nasceu de um defeito real encontrado na revisão da F1: são
# todos casos em que o laudo apontava o dono ERRADO do problema — que é a
# única coisa que esta feature existe para fazer bem.

@pytest.mark.asyncio
async def test_chave_ilegivel_e_etapa_propria(monkeypatch):
    """ORQUESTRA_CONN_KEY trocada levanta ANTES de qualquer rede. Sem etapa
    própria, o laudo dizia 'o provedor recusou' sobre requisição que nunca
    saiu do servidor."""
    from fastapi import HTTPException

    def _falha(_v):
        raise HTTPException(status_code=500, detail="Senha cifrada ilegível")
    monkeypatch.setattr(caixa_ia, "decrypt_password", _falha)
    d = await caixa_ia.diagnosticar(_cfg())
    assert d["etapa"] == "chave"
    assert d["ok"] is False


@pytest.mark.asyncio
async def test_corpo_escalar_continua_na_etapa_formato(monkeypatch):
    """Gateway que responde `5` com HTTP 200: o diagnóstico correto é
    'formato'. Antes, o list(payload) estourava e a etapa virava
    'inesperado', jogando fora o status HTTP e a etapa alcançada."""
    _instala(monkeypatch, _resposta(5))
    d = await caixa_ia.diagnosticar(_cfg())
    assert d["etapa"] == "formato"
    assert d["http_status"] == 200
    assert "int" in d["mensagem"]


@pytest.mark.asyncio
async def test_proxy_vem_do_transporte_e_nao_da_configuracao(monkeypatch):
    """A opção marcada não prova que o proxy foi usado: o NO_PROXY isenta o
    host mesmo com trust_env ligado. Quem responde é o transporte montado."""
    monkeypatch.setenv("HTTPS_PROXY", "http://webproxy.empresa:8080")
    monkeypatch.setattr(
        "services.servicenow.proxy_efetivo",
        lambda _cli, _url: {"em_uso": None, "motivo": "host isento pelo NO_PROXY"})
    _instala(monkeypatch, _resposta({"content": [{"text": "OK"}]}))
    d = await caixa_ia.diagnosticar(_cfg(usa_proxy=True))
    assert d["ok"] is True
    assert d["proxy_em_uso"] is None
    assert "NO_PROXY" in d["proxy_motivo"]


@pytest.mark.asyncio
async def test_proxy_em_uso_e_reportado(monkeypatch):
    monkeypatch.setattr(
        "services.servicenow.proxy_efetivo",
        lambda _cli, _url: {"em_uso": "http://webproxy.empresa:8080", "motivo": None})
    _instala(monkeypatch, _resposta({"content": [{"text": "OK"}]}))
    d = await caixa_ia.diagnosticar(_cfg(usa_proxy=True))
    assert d["proxy_em_uso"] == "http://webproxy.empresa:8080"


@pytest.mark.asyncio
async def test_https_recusado_menciona_certificado(monkeypatch):
    """Com trust_env desligado o httpx ignora SSL_CERT_FILE, e um handshake
    recusado chega como ConnectError. Culpar DNS aí manda o operador para o
    time errado."""
    _instala(monkeypatch, httpx.ConnectError("handshake"))
    d = await caixa_ia.diagnosticar(_cfg(base_url="https://gw.empresa.intranet/api"))
    assert d["etapa"] == "rede"
    assert "certificado" in d["mensagem"].lower()


def test_verificacao_tls_usa_ssl_cert_file(monkeypatch, tmp_path):
    """A CA corporativa precisa continuar valendo mesmo sem trust_env."""
    ca = tmp_path / "corp-ca.pem"
    ca.write_text("-----BEGIN CERTIFICATE-----\n")
    monkeypatch.delenv("SSL_CERT_DIR", raising=False)
    monkeypatch.setenv("SSL_CERT_FILE", str(ca))
    assert caixa_ia._verificacao_tls() == str(ca)
    monkeypatch.delenv("SSL_CERT_FILE")
    assert caixa_ia._verificacao_tls() is True


@pytest.mark.asyncio
async def test_cliente_do_gateway_leva_o_verify(monkeypatch, tmp_path):
    ca = tmp_path / "ca.pem"
    ca.write_text("x")
    monkeypatch.setenv("SSL_CERT_FILE", str(ca))
    _instala(monkeypatch, _resposta({"content": [{"text": "OK"}]}))
    await caixa_ia.chat(_cfg(), "s", "m")
    assert _ClienteFake.ultima.kwargs["verify"] == str(ca)
