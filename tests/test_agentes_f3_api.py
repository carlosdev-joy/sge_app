"""api/routers/agentes.py — o que a F3 (tela `/agentes`) acrescentou à API.

São duas adições pequenas, ambas para a tela não precisar adivinhar nem
repetir regra que o backend já sabe:

  1. **`GET /agentes/catalogo` devolve `cadastro_texto`** — o aviso que o
     admin escreveu em Admin › Agentes, para a tela mostrar a quem ainda não
     tem cadastro no gateway (critério 3 da F3).

     Por que no CATÁLOGO e não no `/agentes/status`, que é onde o estado da
     sonda aparece: o status tem um contrato que `test_agentes_rota.py`
     prende — um acerto de cache não abre conexão de banco nenhuma
     (`test_status_cache_hit_nao_toca_banco_nem_sonda`) e responde um corpo
     EXATO. Buscar o texto ali obrigaria a abrir conexão justamente no
     caminho que existe para não abrir. O catálogo, ao contrário, já lê a
     config para decidir quais agentes mostrar — o campo sai de graça.

     Quem decide MOSTRAR o texto é a tela, e só no estado `sem_cadastro`
     (`AvisoSonda`, preso por tests/test_agentes_f3_front.py):
     `gateway_indisponivel` é problema de rede, e mandar alguém pedir
     cadastro por causa disso é despachar um chamado para a fila errada.

     Esse campo é a ÚNICA fatia de `agentes_*` que um não-admin enxerga; o
     resto da config continua atrás de `get_admin_user`.

  2. **`GET /agentes/admin/config` devolve o catálogo com `perfis_elegiveis`**
     — a aba Admin › Agentes precisa saber a quem pode oferecer cada agente.
     Sem isso o front repetiria essa regra à mão, e uma 2ª lista de RBAC fora
     de sincronia é exatamente o defeito que `RBAC_RECURSOS` já custou uma vez
     (ver tests/test_rbac_recursos_admin.py).

Banco e sonda são dublês — nada toca rede nem SQL Server de verdade.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()
os.environ.setdefault("MSSQL_CONN_STR", "__mock__")
from api.main import app as _app  # noqa: F401,E402

from deps import PERM_ADMIN, get_current_user  # noqa: E402
from services import agentes as svc_agentes, ia_provedor  # noqa: E402

TEXTO_ADMIN = "Abra um chamado na fila IA-GATEWAY pedindo seu cadastro."


class _Cur:
    def __init__(self, config_agentes):
        self.config_agentes = config_agentes
        self._rows: list = []

    def execute(self, sql, params=None):
        params = tuple(params or ())
        s = sql.lower()
        if "select identidade_gateway from dbo.etl_usuario" in s:
            self._rows = [(None,)]
        elif "from dbo.etl_app_config" in s:
            # Discrimina pelo lado de AGENTES (`agentes_*`/`agente_*`): o
            # provedor pede outro conjunto de chaves, e testá-lo pelo nome
            # amarraria este dublê ao prefixo legado do módulo Caixa.
            if not any(str(p).startswith("agente") for p in params):
                # Chaves `ia_*` (pós-F0), não as legadas do módulo Caixa:
                # tests/test_ia_desacoplada.py vigia o prefixo antigo fora
                # dos lugares esperados, e um dublê novo não tem por que
                # nascer preso ao módulo que está saindo do repo.
                self._rows = [("ia_provider", "caixa_gateway"),
                              ("ia_base_url", "https://gw"),
                              ("ia_api_key_enc", "cifrado")]
            else:
                self._rows = list(self.config_agentes.items())
        else:
            self._rows = []

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)

    def close(self):
        pass


class _Conn:
    def __init__(self, cur):
        self._cur = cur

    def cursor(self):
        return self._cur

    def commit(self):
        pass

    def close(self):
        pass


@pytest.fixture
def ambiente():
    estado = {"perms": ["tela_agentes"], "extras": ["agente_datastage"]}
    _app.dependency_overrides[get_current_user] = lambda: {
        "matricula": "DEV1", "perfil": "desenvolvedor",
        "permissoes": estado["perms"], "permissoes_extra": estado["extras"]}
    cur = _Cur({"agentes_enabled": "1", "agente_datastage_enabled": "1",
                "agentes_gateway_campo_usuario": "header:X-User",
                "agentes_cadastro_texto": TEXTO_ADMIN})
    svc_agentes._sonda_cache.clear()
    with patch("routers.agentes.get_db_conn", return_value=_Conn(cur)):
        yield TestClient(_app), estado
    _app.dependency_overrides.pop(get_current_user, None)
    svc_agentes._sonda_cache.clear()


@pytest.fixture
def ambiente_sem_texto():
    _app.dependency_overrides[get_current_user] = lambda: {
        "matricula": "DEV1", "perfil": "desenvolvedor",
        "permissoes": ["tela_agentes"], "permissoes_extra": ["agente_datastage"]}
    cur = _Cur({"agentes_enabled": "1", "agente_datastage_enabled": "1"})
    svc_agentes._sonda_cache.clear()
    with patch("routers.agentes.get_db_conn", return_value=_Conn(cur)):
        yield TestClient(_app)
    _app.dependency_overrides.pop(get_current_user, None)
    svc_agentes._sonda_cache.clear()


# ═══════════ 1. cadastro_texto vem no catálogo ═══════════════════════════

def test_catalogo_devolve_o_texto_de_cadastro_configurado(ambiente):
    cliente, _estado = ambiente
    r = cliente.get("/agentes/catalogo")
    assert r.status_code == 200
    assert r.json()["cadastro_texto"] == TEXTO_ADMIN


def test_catalogo_sem_texto_configurado_cai_no_padrao(ambiente_sem_texto):
    """Sem a chave no banco, `carregar_config` aplica `CONFIG_DEFAULTS` — a
    tela recebe o aviso genérico ("solicite o cadastro..."), nunca string
    vazia nem `None`. É o padrão que a própria spec define para D-05
    enquanto o texto real do canal não é confirmado."""
    cliente = ambiente_sem_texto
    texto = cliente.get("/agentes/catalogo").json()["cadastro_texto"]
    assert texto == svc_agentes.CONFIG_DEFAULTS["agentes_cadastro_texto"]
    assert texto


def test_catalogo_continua_exigindo_tela_agentes(ambiente):
    cliente, estado = ambiente
    estado["perms"] = []
    assert cliente.get("/agentes/catalogo").status_code == 403


def test_status_nao_mudou_de_contrato(ambiente):
    """O corpo do `/agentes/status` continua exatamente `{estado, cache}` —
    `test_agentes_rota.py` compara o dicionário INTEIRO, e um campo novo ali
    quebraria a F1. O texto de cadastro não passa por aqui."""
    cliente, _estado = ambiente
    with patch.object(ia_provedor, "sondar_usuario",
                      new=_sonda(ia_provedor.SONDA_SEM_CADASTRO)):
        r = cliente.get("/agentes/status")
    assert r.status_code == 200
    assert set(r.json()) == {"estado", "cache"}
    assert TEXTO_ADMIN not in r.text


def test_status_cache_hit_continua_sem_abrir_conexao(ambiente):
    """A razão de o texto não morar no status: aqui não pode haver I/O."""
    cliente, _estado = ambiente
    svc_agentes.guardar_sonda("DEV1", "sem_cadastro")

    async def _explode(*_a, **_k):
        raise AssertionError("cache hit não devia chamar a sonda")
    with patch.object(ia_provedor, "sondar_usuario", new=_explode):
        r = cliente.get("/agentes/status")
    assert r.json() == {"estado": "sem_cadastro", "cache": True}


# ═══════════ 2. catálogo com perfis elegíveis (Admin › Agentes) ══════════

def test_config_admin_traz_o_catalogo_com_perfis_elegiveis(ambiente):
    cliente, estado = ambiente
    estado["perms"] = ["tela_agentes", PERM_ADMIN]
    r = cliente.get("/agentes/admin/config")
    assert r.status_code == 200
    agentes = r.json()["agentes"]
    assert len(agentes) == len(svc_agentes.CATALOGO)
    ds = next(a for a in agentes if a["id"] == "datastage")
    # Os campos que a aba do Admin usa para montar a lista de elegíveis.
    assert ds["recurso"] == "agente_datastage"
    assert ds["config_enabled"] == "agente_datastage_enabled"
    assert ds["perfis_elegiveis"] == list(
        svc_agentes.CATALOGO["datastage"]["perfis_elegiveis"])


def test_catalogo_admin_continua_atras_do_gate_de_admin(ambiente):
    cliente, _estado = ambiente  # perfil desenvolvedor, sem PERM_ADMIN
    assert cliente.get("/agentes/admin/config").status_code == 403


def _sonda(valor):
    """Dublê de `sondar_usuario` (async). Uma FUNÇÃO, não uma corotina já
    criada: cada chamada precisa de uma corotina nova — reaproveitar a mesma
    levanta "cannot reuse already awaited coroutine" na 2ª chamada (o caminho
    sem cache)."""
    async def _coro(*_a, **_k):
        return valor
    return _coro
