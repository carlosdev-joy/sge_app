"""POST /admin — identidade no gateway (`user_identidade_set`) e a defesa do
`user_perm_set` contra conceder agente a perfil não elegível (F1 da spec
docs/spec-agentes-datastage.md).

O que estes testes prendem, e por que cada um existe:

  1. **Só admin grava `identidade_gateway`.** É dado que muda o que o
     gateway recebe por aquele usuário — sem o guard normal de `get_admin_user`
     qualquer um com acesso ao Admin poderia se passar por outra matrícula.

  2. **Formato e unicidade.** Vai em HEADER (`_corpo_gateway`) — espaço ou
     quebra de linha quebrariam a chamada; duplicado faria dois usuários
     "serem" a mesma pessoa para o gateway. A unicidade é conferida NA
     APLICAÇÃO (SEM índice único filtrado — gotcha QUOTED_IDENTIFIER).

  3. **Limpar o campo volta ao padrão**, não é erro: `identidade_gateway`
     NULL faz `services.agentes.identidade_gateway()` cair para
     `cvp-<matrícula>` de novo.

  4. **`user_perm_set` recusa (422) conceder `agente_*` a um perfil que
     `require_agente` rejeitaria depois** — risco 26 da spec: sem isso, o
     admin marcaria um checkbox que nunca funciona, e achar isso sem o teste
     seria só na tela, dias depois.

  5. **Recurso comum (não-agente) não é afetado** — o guard é específico de
     `agente_*`; nenhuma regressão no `user_perm_set` de sempre.

Nada aqui toca banco de verdade: um cursor dublê responde por trecho do SQL.
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


class _Cur:
    """Responde por trecho do SQL (case-insensitive), como test_maestro_rota.py."""

    def __init__(self, *, usuarios=None, identidades_existentes=None, migracao_117_aplicada=True):
        self.usuarios = usuarios or {}  # matricula -> perfil_nome
        self.identidades_existentes = identidades_existentes or {}  # identidade -> matricula
        # False simula o banco ANTES da migration 117 — a coluna não existe.
        self.migracao_117_aplicada = migracao_117_aplicada
        self.execs: list[tuple[str, tuple]] = []
        self._rows: list = []
        self.commits = 0

    def execute(self, sql, params=None):
        params = tuple(params or ())
        self.execs.append((sql, params))
        s = sql.lower()
        if "col_length" in s:
            self._rows = [(100,)] if self.migracao_117_aplicada else [(None,)]
        elif "select perfil_nome from dbo.etl_usuario" in s:
            mat = params[0]
            self._rows = [(self.usuarios[mat],)] if mat in self.usuarios else []
        elif "select 1 from dbo.etl_usuario where matricula" in s:
            mat = params[0]
            self._rows = [(1,)] if mat in self.usuarios else []
        elif "select 1 from dbo.etl_usuario where identidade_gateway" in s:
            valor, mat_excluida = params
            dono = self.identidades_existentes.get(valor)
            self._rows = [(1,)] if (dono and dono != mat_excluida) else []
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
        self._cur, self.commits, self.rollbacks = cur, 0, 0

    def cursor(self):
        return self._cur

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        pass


@pytest.fixture
def admin_client(app):
    app.dependency_overrides[get_current_user] = lambda: {
        "matricula": "ADMIN1", "perfil": "admin", "permissoes": [PERM_ADMIN], "permissoes_extra": []}
    yield TestClient(app)
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def naoadmin_client(app):
    app.dependency_overrides[get_current_user] = lambda: {
        "matricula": "DEV1", "perfil": "desenvolvedor", "permissoes": [], "permissoes_extra": []}
    yield TestClient(app)
    app.dependency_overrides.pop(get_current_user, None)


def _post(cliente, cur, body):
    with patch("routers.admin.get_db_conn", return_value=_Conn(cur)):
        return cliente.post("/admin", json=body)


# ═══════════ 1. user_identidade_set — guard de admin ════════════════════════

def test_sem_admin_e_403(naoadmin_client):
    cur = _Cur(usuarios={"DEV1": "desenvolvedor"})
    r = _post(naoadmin_client, cur, {"action": "user_identidade_set",
                                     "matricula": "DEV1", "identidade_gateway": "x"})
    assert r.status_code == 403


def test_sem_a_migration_117_e_503_nomeado_nao_500_cru(admin_client):
    """Achado da revisão adversarial da F1: `user_list` já degradava (checa
    COL_LENGTH); esta ação tinha ficado sem a mesma guarda e quebrava com
    500 cru se a API subisse antes da migration 117 (deploy.sh sincroniza
    dist/+API antes de perguntar sobre migrations). Trava o 503 nomeado."""
    cur = _Cur(usuarios={"DEV1": "desenvolvedor"}, migracao_117_aplicada=False)
    r = _post(admin_client, cur, {"action": "user_identidade_set",
                                  "matricula": "DEV1", "identidade_gateway": "x"})
    assert r.status_code == 503
    assert "117" in r.json()["detail"]
    # nada foi lido/gravado além da checagem de schema
    assert not any("etl_usuario where matricula" in e[0].lower() for e in cur.execs)


# ═══════════ 2. formato e unicidade ══════════════════════════════════════════

def test_usuario_nao_cadastrado_e_422(admin_client):
    cur = _Cur(usuarios={})
    r = _post(admin_client, cur, {"action": "user_identidade_set",
                                  "matricula": "FANTASMA", "identidade_gateway": "x"})
    assert r.status_code == 422


@pytest.mark.parametrize("valor", [
    "cvp jose",              # espaço
    "cvp\njose",              # quebra de linha
    "a" * 101,                # excede 100
    "",                       # vazio é tratado por outro caminho (limpar) — aqui força string vazia após strip
])
def test_formato_invalido_e_422(admin_client, valor):
    if valor == "":
        pytest.skip("string vazia é o caminho de LIMPAR, testado à parte")
    cur = _Cur(usuarios={"DEV1": "desenvolvedor"})
    r = _post(admin_client, cur, {"action": "user_identidade_set",
                                  "matricula": "DEV1", "identidade_gateway": valor})
    assert r.status_code == 422


def test_valor_valido_grava(admin_client):
    cur = _Cur(usuarios={"DEV1": "desenvolvedor"})
    r = _post(admin_client, cur, {"action": "user_identidade_set",
                                  "matricula": "DEV1", "identidade_gateway": "usuario.dev@caixa"})
    assert r.status_code == 200
    update = [e for e in cur.execs if e[0].lower().startswith("update dbo.etl_usuario")]
    assert update, "nenhum UPDATE emitido"
    assert update[0][1][0] == "usuario.dev@caixa"
    assert update[0][1][1] == "ADMIN1"  # identidade_gateway_por = quem gravou


def test_valor_duplicado_e_409(admin_client):
    cur = _Cur(usuarios={"DEV1": "desenvolvedor", "DEV2": "desenvolvedor"},
              identidades_existentes={"ja-usada": "DEV2"})
    r = _post(admin_client, cur, {"action": "user_identidade_set",
                                  "matricula": "DEV1", "identidade_gateway": "ja-usada"})
    assert r.status_code == 409


def test_mesmo_usuario_pode_regravar_o_proprio_valor(admin_client):
    """Não é duplicado consigo mesmo — `matricula <> ?` no SELECT de choque."""
    cur = _Cur(usuarios={"DEV1": "desenvolvedor"},
              identidades_existentes={"meu-valor": "DEV1"})
    r = _post(admin_client, cur, {"action": "user_identidade_set",
                                  "matricula": "DEV1", "identidade_gateway": "meu-valor"})
    assert r.status_code == 200


def test_limpar_volta_ao_padrao(admin_client):
    cur = _Cur(usuarios={"DEV1": "desenvolvedor"})
    r = _post(admin_client, cur, {"action": "user_identidade_set",
                                  "matricula": "DEV1", "identidade_gateway": ""})
    assert r.status_code == 200
    update = [e for e in cur.execs if e[0].lower().startswith("update dbo.etl_usuario")]
    assert update, "nenhum UPDATE emitido ao limpar"
    assert "identidade_gateway = null" in update[0][0].lower()


def test_salvar_invalida_a_sonda_cacheada(admin_client):
    from services import agentes as svc_agentes
    svc_agentes.guardar_sonda("DEV1", "ok")
    assert svc_agentes.sonda_cacheada("DEV1") == "ok"
    cur = _Cur(usuarios={"DEV1": "desenvolvedor"})
    r = _post(admin_client, cur, {"action": "user_identidade_set",
                                  "matricula": "DEV1", "identidade_gateway": "novo-valor"})
    assert r.status_code == 200
    assert svc_agentes.sonda_cacheada("DEV1") is None


# ═══════════ 3. user_perm_set — recusa agente para perfil não elegível ══════

def test_conceder_agente_a_perfil_elegivel_funciona(admin_client):
    cur = _Cur(usuarios={"DEV1": "desenvolvedor"})
    r = _post(admin_client, cur, {"action": "user_perm_set", "matricula": "DEV1",
                                  "permissoes": ["agente_datastage"]})
    assert r.status_code == 200
    inseridos = [e for e in cur.execs if e[0].lower().startswith("insert into dbo.etl_usuario_permissao")]
    assert inseridos and inseridos[0][1][1] == "agente_datastage"


def test_conceder_agente_a_perfil_nao_elegivel_e_422(admin_client):
    cur = _Cur(usuarios={"OPER1": "consulta"})
    r = _post(admin_client, cur, {"action": "user_perm_set", "matricula": "OPER1",
                                  "permissoes": ["agente_datastage"]})
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "agente_perfil_nao_elegivel"
    # nada foi gravado — a recusa é ANTES do DELETE/INSERT
    assert not any("delete from dbo.etl_usuario_permissao" in e[0].lower() for e in cur.execs)


def test_conceder_agente_a_admin_funciona():
    """admin é sempre elegível — grant explícito não é bloqueado, mesmo sendo
    redundante (o admin já usa o agente por acao_admin)."""
    app_ = _app
    app_.dependency_overrides[get_current_user] = lambda: {
        "matricula": "ADMIN1", "perfil": "admin", "permissoes": [PERM_ADMIN], "permissoes_extra": []}
    try:
        cur = _Cur(usuarios={"ADMIN2": "admin"})
        r = _post(TestClient(app_), cur, {"action": "user_perm_set", "matricula": "ADMIN2",
                                          "permissoes": ["agente_datastage"]})
        assert r.status_code == 200
    finally:
        app_.dependency_overrides.pop(get_current_user, None)


def test_conceder_recurso_comum_nao_e_afetado_pelo_guard(admin_client):
    """Não-regressão: um recurso que não é de agente nenhum segue liberável
    para qualquer perfil, como sempre foi."""
    cur = _Cur(usuarios={"OPER1": "consulta"})
    r = _post(admin_client, cur, {"action": "user_perm_set", "matricula": "OPER1",
                                  "permissoes": ["tela_jobs"]})
    assert r.status_code == 200
