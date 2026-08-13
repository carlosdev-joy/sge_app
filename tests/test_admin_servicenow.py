"""Sonda do ServiceNow no Admin — proxy corporativo e instância configurável.

O que estes testes prendem, e por quê cada um existe:

  1. **O NO_PROXY tem que valer.** A sonda NÃO passa `proxy=`/`proxies=` ao
     httpx: com `trust_env` (o padrão) ele lê HTTPS_PROXY/HTTP_PROXY do
     ambiente E aplica o NO_PROXY sozinho. Passar o parâmetro explicitamente
     — como duas versões anteriores faziam — FORÇA o proxy mesmo em host
     isento, e `proxies=` ainda deixa de existir no httpx 0.28+. Estes testes
     usam um `AsyncClient` de verdade e inspecionam o transporte resolvido:
     é a regra do httpx que está sendo medida, não uma reimplementação dela.

  2. **"Sem proxy" não pode passar por "com proxy".** Variável ausente e host
     isento produzem o mesmo sintoma na tela (conexão direta) por causas
     opostas — uma é esquecimento de `.env`, a outra é configuração correta.
     A sonda precisa dizer QUAL das duas, senão o operador depura no escuro.

  3. **A instância vem do ambiente**, não de literal no front: trocar de
     instância é ajuste de `.env`, sem rebuild da UI.

  4. **A guarda anti-SSRF continua de pé**: o endpoint faz GET autenticado
     para onde o body mandar, então só aceita https de *.service-now.com.

Nada aqui toca rede: a inspeção do proxy é feita sobre o transporte montado,
sem requisição, e a rota de config só lê variável de ambiente.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()
os.environ.setdefault("MSSQL_CONN_STR", "__mock__")
from api.main import app  # noqa: E402

from deps import PERM_ADMIN, get_current_user  # noqa: E402
from routers.admin import _sn_proxy_efetivo, _sn_url_valida  # noqa: E402

ALVO = "https://cvpsnprod.service-now.com"
PROXY = "http://webproxycvp.adcorp.intranet/"


@pytest.fixture
def admin_client():
    app.dependency_overrides[get_current_user] = lambda: {
        "matricula": "ADMIN1", "perfil": "admin", "permissoes": [PERM_ADMIN],
    }
    yield TestClient(app)
    app.dependency_overrides.pop(get_current_user, None)


def _limpa_proxy(monkeypatch):
    for v in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy",
              "NO_PROXY", "no_proxy", "ALL_PROXY", "all_proxy"):
        monkeypatch.delenv(v, raising=False)


# ═══════════ 1. o proxy do ambiente é aplicado sem parâmetro explícito ══════

def test_proxy_do_ambiente_e_aplicado(monkeypatch):
    """Sem passar proxy= ao httpx, HTTPS_PROXY do container já vale."""
    _limpa_proxy(monkeypatch)
    monkeypatch.setenv("HTTPS_PROXY", PROXY)
    cli = httpx.AsyncClient()
    r = _sn_proxy_efetivo(cli, ALVO)
    assert r["em_uso"], "HTTPS_PROXY definida deveria aplicar proxy no transporte"
    assert "webproxycvp" in r["em_uso"]
    assert r["motivo"] is None


# ═══════════ 2. o NO_PROXY é respeitado — a regressão que isto trava ════════

def test_no_proxy_isenta_o_host(monkeypatch):
    """Host coberto pelo NO_PROXY sai DIRETO, mesmo com HTTPS_PROXY definida.

    Passar proxy=/proxies= explicitamente quebraria exatamente isto: o httpx
    ignora o NO_PROXY quando o proxy vem por parâmetro.
    """
    _limpa_proxy(monkeypatch)
    monkeypatch.setenv("HTTPS_PROXY", PROXY)
    monkeypatch.setenv("NO_PROXY", "cvpsnprod.service-now.com")
    cli = httpx.AsyncClient()
    r = _sn_proxy_efetivo(cli, ALVO)
    assert r["em_uso"] is None, "NO_PROXY deveria isentar o host do proxy"
    assert "NO_PROXY" in (r["motivo"] or "")


# ═══════════ 3. a causa da conexão direta é dita, não adivinhada ════════════

def test_sem_variavel_o_motivo_aponta_o_env(monkeypatch):
    """Variável ausente e host isento têm o mesmo sintoma — o motivo separa."""
    _limpa_proxy(monkeypatch)
    cli = httpx.AsyncClient()
    r = _sn_proxy_efetivo(cli, ALVO)
    assert r["em_uso"] is None
    assert "HTTPS_PROXY" in (r["motivo"] or "")
    assert "NO_PROXY" not in (r["motivo"] or ""), (
        "sem variável nenhuma o motivo não pode culpar o NO_PROXY")


def test_motivo_degrada_sem_derrubar_a_sonda():
    """API interna do httpx mudou → 'não sei', nunca exceção: a sonda existe
    para diagnosticar, não pode morrer no diagnóstico do próprio diagnóstico."""
    class ClienteEstranho:
        def _transport_for_url(self, _url):
            raise RuntimeError("API interna mudou")
    r = _sn_proxy_efetivo(ClienteEstranho(), ALVO)
    assert r["em_uso"] is None
    assert r["motivo"]


# ═══════════ 3b. o HANDLER não pode voltar a passar proxy explícito ═════════
# Os testes acima medem a regra do httpx num client construído aqui — dariam
# verde mesmo se o handler voltasse a passar proxy=. Este prende o handler.

class _ClienteFalso:
    """Captura os kwargs do AsyncClient e corta a rede na primeira chamada."""
    kwargs: dict = {}

    def __init__(self, **kw):
        _ClienteFalso.kwargs = kw

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_a):
        return False

    async def get(self, *_a, **_k):
        raise httpx.ConnectError("rede cortada no teste")

    def _transport_for_url(self, _url):
        raise RuntimeError("cliente falso não resolve transporte")


def test_handler_nao_passa_proxy_ao_httpx(admin_client, monkeypatch):
    """A sonda deixa o proxy por conta do ambiente (trust_env).

    Qualquer `proxy=`, `proxies=` ou `mounts=` aqui reintroduz o bug: o
    NO_PROXY para de valer e o `proxies=` quebra no httpx 0.28+.
    """
    monkeypatch.setattr("routers.admin.httpx.AsyncClient", _ClienteFalso)
    r = admin_client.post("/admin/servicenow/diagnostico",
                          json={"url": ALVO, "usuario": "u", "senha": "s"})
    assert r.status_code == 200
    kw = _ClienteFalso.kwargs
    for proibido in ("proxy", "proxies", "mounts"):
        assert proibido not in kw, (
            f"AsyncClient recebeu {proibido}= — isso força o proxy e ignora o "
            f"NO_PROXY; deixe o httpx ler o ambiente sozinho")
    assert kw.get("trust_env", True) is True, (
        "trust_env=False faria o httpx ignorar HTTPS_PROXY do container")


def test_resposta_sempre_traz_o_bloco_proxy(admin_client, monkeypatch):
    """Mesmo quando a rede falha — é justamente aí que o operador precisa
    saber por onde a chamada tentou sair."""
    monkeypatch.setattr("routers.admin.httpx.AsyncClient", _ClienteFalso)
    corpo = admin_client.post("/admin/servicenow/diagnostico",
                              json={"url": ALVO, "usuario": "u", "senha": "s"}).json()
    assert "proxy" in corpo and corpo["proxy"] is not None
    assert corpo["auth"]["ok"] is False


# ═══════════ 4. a instância vem do ambiente ═════════════════════════════════

def test_config_devolve_a_instancia_do_ambiente(admin_client, monkeypatch):
    monkeypatch.setenv("SERVICENOW_URL", ALVO + "/")
    r = admin_client.get("/admin/servicenow/config")
    assert r.status_code == 200
    assert r.json()["url"] == ALVO, "a barra final deve ser normalizada"


def test_config_sem_variavel_devolve_vazio(admin_client, monkeypatch):
    monkeypatch.delenv("SERVICENOW_URL", raising=False)
    r = admin_client.get("/admin/servicenow/config")
    assert r.status_code == 200
    assert r.json()["url"] == ""


def test_config_nao_expoe_credencial(admin_client, monkeypatch):
    """Só a URL. Credencial nunca veio de env e não pode passar a vir."""
    monkeypatch.setenv("SERVICENOW_URL", ALVO)
    corpo = admin_client.get("/admin/servicenow/config").json()
    assert set(corpo) == {"url"}


# ═══════════ 5. a guarda anti-SSRF do endpoint ══════════════════════════════

@pytest.mark.parametrize("url", [
    "http://cvpsnprod.service-now.com",      # sem TLS
    "https://evil.com",                      # domínio de fora
    "https://service-now.com.evil.com",      # sufixo forjado
    "",                                      # vazio
])
def test_url_invalida_e_recusada(url):
    with pytest.raises(HTTPException) as e:
        _sn_url_valida(url)
    assert e.value.status_code == 422


def test_url_valida_normaliza_barra_final():
    assert _sn_url_valida(ALVO + "/") == ALVO
