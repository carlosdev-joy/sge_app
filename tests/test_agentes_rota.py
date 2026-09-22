"""api/routers/agentes.py — GET /agentes/catalogo, /agentes/status,
GET+POST /agentes/admin/config (F1 da spec docs/spec-agentes-datastage.md).

O que estes testes prendem, e por que cada um existe:

  1. **`tela_agentes` é um gate comum** — `require_perm` puro, sem bypass:
     sem o recurso, 403, mesmo para quem tem `acao_admin` (o admin só passa
     porque a migration 117 semeia `tela_agentes` no perfil dele, não porque
     o código o isenta aqui).

  2. **`/agentes/status` nunca chama a rede sem precisar**: cache hit não
     toca banco nem a sonda; a identidade que vai à sonda é a resolvida
     (cadastro do usuário OU o padrão), nunca o que vier no corpo da
     requisição (não existe — a matrícula é sempre da sessão).

  3. **`/agentes/admin/config` valida antes de gravar** — campo malformado,
     número fora do intervalo — e só grava as chaves que vieram no corpo
     (parcial), sem apagar as que não vieram.

Banco e a sonda são dublês; nada toca rede nem SQL Server de verdade.
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


class _Cur:
    """Responde por trecho do SQL — mesmo padrão de test_maestro_rota.py."""

    def __init__(self, *, identidade_cadastro=None, config_agentes=None, config_provedor=None,
                migracao_117_aplicada=True):
        self.identidade_cadastro = identidade_cadastro
        self.config_agentes = config_agentes or {}
        self.config_provedor = config_provedor or {}
        # False simula o banco ANTES da migration 117 — a coluna não existe
        # (achado da revisão adversarial: a API pode subir antes da 6c).
        self.migracao_117_aplicada = migracao_117_aplicada
        self.execs: list[tuple[str, tuple]] = []
        self._rows: list = []
        self.commits = 0

    def execute(self, sql, params=None):
        params = tuple(params or ())
        self.execs.append((sql, params))
        s = sql.lower()
        if "select identidade_gateway from dbo.etl_usuario" in s:
            if not self.migracao_117_aplicada:
                raise Exception("Invalid column name 'identidade_gateway'.")  # pré-117
            self._rows = [(self.identidade_cadastro,)]
        elif "from dbo.etl_app_config" in s:
            # Discrimina pelo conjunto de chaves pedido: ia_provedor pede
            # ia_*/caixa_ia_*; services.agentes pede agentes_*/agente_*.
            if any(str(p).startswith(("ia_", "caixa_ia_")) for p in params):
                fonte = self.config_provedor
            else:
                fonte = self.config_agentes
            self._rows = list(fonte.items())
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
        self._cur, self.commits = cur, 0

    def cursor(self):
        return self._cur

    def commit(self):
        self.commits += 1

    def close(self):
        pass


@pytest.fixture
def ambiente(monkeypatch):
    estado = {"perms": ["tela_agentes"], "matricula": "DEV1", "perfil": "desenvolvedor",
             "extras": ["agente_datastage"]}
    _app.dependency_overrides[get_current_user] = lambda: {
        "matricula": estado["matricula"], "perfil": estado["perfil"],
        "permissoes": estado["perms"], "permissoes_extra": estado["extras"]}
    cur = _Cur(config_agentes={"agentes_enabled": "1", "agente_datastage_enabled": "1"},
              config_provedor={"caixa_ia_provider": "caixa_gateway", "caixa_ia_base_url": "https://gw",
                                "caixa_ia_api_key_enc": "cifrado"})
    conn = _Conn(cur)
    svc_agentes._sonda_cache.clear()
    with patch("routers.agentes.get_db_conn", return_value=conn):
        yield TestClient(_app), cur, estado
    _app.dependency_overrides.pop(get_current_user, None)
    svc_agentes._sonda_cache.clear()


# ═══════════ 1. gate ══════════════════════════════════════════════════════

def test_sem_tela_agentes_e_403_em_tudo(ambiente):
    cliente, _cur, estado = ambiente
    estado["perms"] = []
    assert cliente.get("/agentes/catalogo").status_code == 403
    assert cliente.get("/agentes/status").status_code == 403


def test_sem_admin_403_na_config(ambiente):
    cliente, *_ = ambiente
    assert cliente.get("/agentes/admin/config").status_code == 403
    assert cliente.post("/agentes/admin/config", json={"agentes_enabled": True}).status_code == 403


# ═══════════ 2. catálogo ═════════════════════════════════════════════════

def test_catalogo_delega_para_o_servico(ambiente):
    cliente, _cur, _estado = ambiente
    r = cliente.get("/agentes/catalogo")
    assert r.status_code == 200
    agentes = r.json()["agentes"]
    assert len(agentes) == 1 and agentes[0]["id"] == "datastage"


def test_catalogo_vazio_sem_grant(ambiente):
    cliente, _cur, estado = ambiente
    estado["extras"] = []
    assert cliente.get("/agentes/catalogo").json()["agentes"] == []


# ═══════════ 3. status ═══════════════════════════════════════════════════

def test_status_agente_desconhecido_e_404(ambiente):
    cliente, *_ = ambiente
    assert cliente.get("/agentes/status?agente=nao-existe").status_code == 404


def test_status_cache_hit_nao_toca_banco_nem_sonda(ambiente, monkeypatch):
    cliente, cur, estado = ambiente
    svc_agentes.guardar_sonda(estado["matricula"], "ok")

    async def _explode(*a, **k):
        raise AssertionError("sondar_usuario não devia ter sido chamada — cache deveria bastar")
    monkeypatch.setattr(ia_provedor, "sondar_usuario", _explode)
    r = cliente.get("/agentes/status")
    assert r.status_code == 200
    assert r.json() == {"estado": "ok", "cache": True}
    assert not any("etl_usuario" in e[0].lower() or "etl_app_config" in e[0].lower() for e in cur.execs)


@pytest.mark.asyncio
async def test_status_cache_miss_resolve_identidade_e_chama_a_sonda(ambiente, monkeypatch):
    cliente, cur, estado = ambiente
    cur.identidade_cadastro = None  # sem cadastro → cai no padrão cvp-<matrícula>
    cur.config_agentes["agentes_gateway_campo_usuario"] = "header:x-user-matricula"

    chamadas = []

    async def _sonda(cfg, identidade, campo, identidade_app=None):
        chamadas.append({"identidade": identidade, "campo": campo})
        return ia_provedor.SONDA_OK
    monkeypatch.setattr(ia_provedor, "sondar_usuario", _sonda)

    r = cliente.get("/agentes/status")
    assert r.status_code == 200
    assert r.json() == {"estado": "ok", "cache": False}
    assert chamadas == [{"identidade": "cvp-dev1", "campo": "header:x-user-matricula"}]
    # e ficou em cache para a próxima
    assert svc_agentes.sonda_cacheada(estado["matricula"]) == "ok"


@pytest.mark.asyncio
async def test_status_usa_o_cadastro_quando_preenchido(ambiente, monkeypatch):
    cliente, cur, _estado = ambiente
    cur.identidade_cadastro = "usuario.custom@caixa"
    cur.config_agentes["agentes_gateway_campo_usuario"] = "header:x-user-matricula"
    chamadas = []

    async def _sonda(cfg, identidade, campo, identidade_app=None):
        chamadas.append(identidade)
        return ia_provedor.SONDA_SEM_CADASTRO
    monkeypatch.setattr(ia_provedor, "sondar_usuario", _sonda)
    cliente.get("/agentes/status")
    assert chamadas == ["usuario.custom@caixa"]


def test_status_gateway_indisponivel_nao_fica_em_cache(ambiente, monkeypatch):
    cliente, cur, estado = ambiente
    cur.config_agentes["agentes_gateway_campo_usuario"] = "header:x"

    async def _sonda(*a, **k):
        return ia_provedor.SONDA_GATEWAY_INDISPONIVEL
    monkeypatch.setattr(ia_provedor, "sondar_usuario", _sonda)
    r = cliente.get("/agentes/status")
    assert r.json()["estado"] == "gateway_indisponivel"
    assert svc_agentes.sonda_cacheada(estado["matricula"]) is None


@pytest.mark.asyncio
async def test_status_sem_a_migration_117_degrada_para_o_padrao_nao_500(ambiente, monkeypatch):
    """Achado da revisão adversarial da F1: a API pode subir antes da
    migration 117 (deploy.sh aplica dist/+API antes de perguntar sobre
    migrations, etapa 6c). Sem a coluna, 'sem cadastro próprio' é a leitura
    certa — cai no padrão cvp-<matrícula> — e a rota continua 200, nunca 500."""
    cliente, cur, estado = ambiente
    cur.migracao_117_aplicada = False
    cur.config_agentes["agentes_gateway_campo_usuario"] = "header:x-user-matricula"
    chamadas = []

    async def _sonda(cfg, identidade, campo, identidade_app=None):
        chamadas.append(identidade)
        return ia_provedor.SONDA_OK
    monkeypatch.setattr(ia_provedor, "sondar_usuario", _sonda)
    r = cliente.get("/agentes/status")
    assert r.status_code == 200
    assert chamadas == [f"cvp-{estado['matricula'].lower()}"]  # o padrão, não um cadastro custom


# ═══════════ 4. admin/config ═════════════════════════════════════════════

@pytest.fixture
def admin_ambiente(ambiente):
    cliente, cur, estado = ambiente
    estado["perfil"], estado["perms"] = "admin", [PERM_ADMIN, "tela_agentes"]
    return cliente, cur, estado


def test_admin_config_get(admin_ambiente):
    cliente, _cur, _estado = admin_ambiente
    r = cliente.get("/agentes/admin/config")
    assert r.status_code == 200
    assert r.json()["config"]["agentes_enabled"] == "1"


def test_admin_config_set_grava_so_o_que_veio(admin_ambiente):
    cliente, cur, _estado = admin_ambiente
    r = cliente.post("/agentes/admin/config", json={"agentes_ssh_max": 20})
    assert r.status_code == 200
    merges = [e for e in cur.execs if e[0].lower().startswith("merge dbo.etl_app_config")]
    assert len(merges) == 1
    assert merges[0][1][0] == "agentes_ssh_max" and merges[0][1][1] == "20"


@pytest.mark.parametrize("corpo,campo_esperado", [
    ({"agentes_gateway_campo_usuario": "invalido"}, "agentes_gateway_campo_usuario"),
    ({"agentes_ssh_max": 0}, "agentes_ssh_max"),
    ({"agentes_ssh_max": 999}, "agentes_ssh_max"),
    ({"agentes_ssh_max": "abc"}, "agentes_ssh_max"),
    ({"agentes_fato_validade_dias": 0}, "agentes_fato_validade_dias"),
    ({"agentes_cadastro_texto": "x" * 501}, "agentes_cadastro_texto"),
])
def test_admin_config_valida_cada_campo(admin_ambiente, corpo, campo_esperado):
    cliente, cur, _estado = admin_ambiente
    r = cliente.post("/agentes/admin/config", json=corpo)
    assert r.status_code == 422
    assert campo_esperado in " ".join(r.json()["detail"]["errors"])
    assert not any(e[0].lower().startswith("merge") for e in cur.execs)


def test_admin_config_campo_valido_header_e_body(admin_ambiente):
    cliente, cur, _estado = admin_ambiente
    for valor in ("header:x-user", "body:usuario"):
        cur.execs.clear()
        r = cliente.post("/agentes/admin/config", json={"agentes_gateway_campo_usuario": valor})
        assert r.status_code == 200
        merges = [e for e in cur.execs if e[0].lower().startswith("merge")]
        assert merges[0][1][1] == valor


def test_admin_config_corpo_vazio_e_422(admin_ambiente):
    cliente, *_ = admin_ambiente
    r = cliente.post("/agentes/admin/config", json={})
    assert r.status_code == 422
