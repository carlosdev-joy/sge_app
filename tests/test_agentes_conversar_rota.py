"""POST /agentes/datastage/conversar (F2 da spec docs/spec-agentes-datastage.md).

O que estes testes prendem, e por que cada um existe:

  1. **O gate de `require_agente` vale aqui também** — sem elegibilidade, 403;
     com a tela mas o agente desligado, 503, sem chamar `conversar()` (e
     portanto sem tocar o provedor nem o servidor).

  2. **A conversa persiste, e só o DONO a continua.** Uma 2ª mensagem no
     mesmo `conversa_id` reaproveita o histórico gravado; um `conversa_id`
     de outra matrícula dá 404 (nunca confirma que existe).

  3. **A identidade é SEMPRE a da sessão.** Uma `matricula` forjada no
     corpo da requisição não influencia nem o histórico lido nem a
     identidade mandada ao provedor (critério 6 da F2).

  4. **Validação do corpo**: mensagem vazia/longa demais, `conversa_id` fora
     do formato — 422, sem chegar a abrir conexão de orquestração nenhuma.

A orquestração em si (`services.agentes.conversar`) já é testada em
`test_agentes_orquestracao.py`; aqui ela é um DUBLÊ — o que importa é a
FIAÇÃO: gate, persistência, resolução de identidade/config.
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

from deps import get_current_user  # noqa: E402
from services import agentes as svc  # noqa: E402


class _Cur:
    """Responde por trecho do SQL — mesmo padrão dos demais testes de agentes."""

    def __init__(self, *, config_agentes=None, config_provedor=None,
                identidade_cadastro=None, conversas=None, mensagens=None):
        self.config_agentes = config_agentes or {"agentes_enabled": "1", "agente_datastage_enabled": "1"}
        self.config_provedor = config_provedor or {}
        self.identidade_cadastro = identidade_cadastro
        # conversa_id -> {"projeto": str|None, "matricula": str}
        self.conversas = conversas or {}
        # conversa_id -> [(papel, conteudo), ...]
        self.mensagens = mensagens or {}
        self.execs: list[tuple[str, tuple]] = []
        self._rows: list = []

    def execute(self, sql, params=None):
        params = tuple(params or ())
        self.execs.append((sql, params))
        s = sql.lower()
        if "select identidade_gateway from dbo.etl_usuario" in s:
            self._rows = [(self.identidade_cadastro,)]
        elif "from dbo.etl_app_config" in s:
            if any(str(p).startswith(("ia_", "caixa_ia_")) for p in params):
                self._rows = list(self.config_provedor.items())
            else:
                self._rows = list(self.config_agentes.items())
        elif "select projeto, matricula" in s and "etl_agente_conversa" in s:
            # A F4 acrescentou a idade em dias (DATEDIFF) a este SELECT — o
            # router recusa conversa vencida. `idade_dias` default 0 = conversa
            # de hoje, que é o caso de todos os testes deste arquivo.
            conversa_id = params[0]
            c = self.conversas.get(conversa_id)
            self._rows = [(c["projeto"], c["matricula"], c.get("idade_dias", 0))] if c else []
        elif "insert into dbo.etl_agente_conversa" in s:
            conversa_id, _agente, matricula, _titulo = params
            self.conversas[conversa_id] = {"projeto": None, "matricula": matricula, "idade_dias": 0}
            self.mensagens.setdefault(conversa_id, [])
        elif "select papel, conteudo from dbo.etl_agente_mensagem" in s:
            conversa_id = params[0]
            self._rows = list(self.mensagens.get(conversa_id, []))
        elif "insert into dbo.etl_agente_mensagem" in s:
            conversa_id = params[0]
            papel = params[1]
            conteudo = params[2]
            self.mensagens.setdefault(conversa_id, []).append((papel, conteudo))
        elif "update dbo.etl_agente_conversa" in s:
            projeto, conversa_id = params
            if conversa_id in self.conversas:
                self.conversas[conversa_id]["projeto"] = projeto
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
        self.commits = 0
        self.closes = 0

    def cursor(self):
        return self._cur

    def commit(self):
        self.commits += 1

    def close(self):
        self.closes += 1


class _CurQueExplode(_Cur):
    """Simula uma exceção do DRIVER (deadlock, timeout de rede) — não é
    HTTPException. Achado real da revisão adversarial da F2: só esse tipo
    escapava do `except HTTPException: ... else: ...` sem fechar a conexão.
    Só explode na leitura da conversa — a config precisa carregar normal
    (senão `carregar_config` absorve a exceção e o fluxo nem chega lá:
    ela tem seu próprio `try/except: pass`, é degradação esperada, não o
    vazamento que este teste prova)."""

    def __init__(self):
        super().__init__(config_agentes={"agentes_enabled": "1", "agente_datastage_enabled": "1"})

    def execute(self, sql, params=None):
        s = " ".join(sql.lower().split())
        if "select projeto, matricula" in s and "etl_agente_conversa" in s:
            raise RuntimeError("falha de driver simulada")
        return super().execute(sql, params)


@pytest.fixture
def ambiente(monkeypatch):
    estado = {"perms": ["tela_agentes"], "matricula": "DEV1", "perfil": "desenvolvedor",
             "extras": ["agente_datastage"]}
    _app.dependency_overrides[get_current_user] = lambda: {
        "matricula": estado["matricula"], "perfil": estado["perfil"],
        "permissoes": estado["perms"], "permissoes_extra": estado["extras"]}
    cur = _Cur()
    conn = _Conn(cur)
    with patch("routers.agentes.get_db_conn", return_value=conn):
        yield TestClient(_app), cur, estado
    _app.dependency_overrides.pop(get_current_user, None)


def _resultado_padrao(**over):
    base = {"status": "ok", "texto": "Resposta do agente.", "projeto": None, "artefatos": []}
    base.update(over)
    return base


# ═══════════ 1. gate ══════════════════════════════════════════════════════

def test_sem_grant_e_403_sem_chamar_conversar(ambiente, monkeypatch):
    cliente, _cur, estado = ambiente
    estado["extras"] = []

    async def _explode(*a, **k):
        raise AssertionError("conversar() não devia ter sido chamada — 403 antes")
    monkeypatch.setattr(svc, "conversar", _explode)
    r = cliente.post("/agentes/datastage/conversar", json={"mensagem": "oi"})
    assert r.status_code == 403


def test_agente_desligado_e_503_sem_chamar_conversar(ambiente, monkeypatch):
    cliente, cur, _estado = ambiente
    cur.config_agentes["agente_datastage_enabled"] = "0"

    async def _explode(*a, **k):
        raise AssertionError("conversar() não devia ter sido chamada — 503 antes")
    monkeypatch.setattr(svc, "conversar", _explode)
    r = cliente.post("/agentes/datastage/conversar", json={"mensagem": "oi"})
    assert r.status_code == 503
    assert r.json()["detail"]["code"] == "agente_desligado"


# ═══════════ 2. validação do corpo ═══════════════════════════════════════

def test_mensagem_vazia_e_422(ambiente):
    cliente, *_ = ambiente
    assert cliente.post("/agentes/datastage/conversar", json={"mensagem": ""}).status_code == 422
    assert cliente.post("/agentes/datastage/conversar", json={}).status_code == 422


def test_mensagem_longa_demais_e_422(ambiente):
    cliente, *_ = ambiente
    r = cliente.post("/agentes/datastage/conversar", json={"mensagem": "x" * 4001})
    assert r.status_code == 422


def test_conversa_id_invalido_e_422(ambiente):
    cliente, *_ = ambiente
    r = cliente.post("/agentes/datastage/conversar", json={"mensagem": "oi", "conversa_id": "a"})
    assert r.status_code == 422


# ═══════════ 3. persistência e continuidade ═══════════════════════════════

def test_primeira_mensagem_cria_conversa_e_grava_as_duas_mensagens(ambiente, monkeypatch):
    cliente, cur, estado = ambiente

    async def _fake(abrir_conn, **kw):
        return _resultado_padrao(projeto="BI_CVP", artefatos=[{"ferramenta": "resolver_projeto"}])
    monkeypatch.setattr(svc, "conversar", _fake)
    r = cliente.post("/agentes/datastage/conversar", json={"mensagem": "quero saber do job X"})
    assert r.status_code == 200
    body = r.json()
    assert body["projeto"] == "BI_CVP" and body["status"] == "ok"
    conversa_id = body["conversa_id"]
    assert conversa_id in cur.conversas
    assert cur.conversas[conversa_id]["matricula"] == estado["matricula"]
    assert [p for p, _ in cur.mensagens[conversa_id]] == ["user", "assistant"]


def test_segunda_mensagem_reaproveita_o_historico(ambiente, monkeypatch):
    cliente, cur, estado = ambiente
    conversa_id = "conversa-existente-123"
    cur.conversas[conversa_id] = {"projeto": "BI_CVP", "matricula": estado["matricula"]}
    cur.mensagens[conversa_id] = [("user", "primeira pergunta"), ("assistant", "primeira resposta")]

    recebido = {}

    async def _fake(abrir_conn, *, mensagens, projeto_atual, **kw):
        recebido["mensagens"] = mensagens
        recebido["projeto_atual"] = projeto_atual
        return _resultado_padrao(projeto=projeto_atual)
    monkeypatch.setattr(svc, "conversar", _fake)
    r = cliente.post("/agentes/datastage/conversar",
                     json={"mensagem": "e agora?", "conversa_id": conversa_id})
    assert r.status_code == 200
    assert recebido["projeto_atual"] == "BI_CVP"
    conteudos = [m["content"] for m in recebido["mensagens"]]
    assert "primeira pergunta" in conteudos and "primeira resposta" in conteudos
    assert conteudos[-1] == "e agora?"


def test_conversa_de_outro_usuario_e_404(ambiente, monkeypatch):
    cliente, cur, _estado = ambiente
    conversa_id = "conversa-de-outra-pessoa1"
    cur.conversas[conversa_id] = {"projeto": None, "matricula": "OUTRO_USUARIO"}

    async def _explode(*a, **k):
        raise AssertionError("conversar() não devia ter sido chamada — 404 antes")
    monkeypatch.setattr(svc, "conversar", _explode)
    r = cliente.post("/agentes/datastage/conversar",
                     json={"mensagem": "oi", "conversa_id": conversa_id})
    assert r.status_code == 404


# ═══════════ 4. identidade sempre da sessão ═══════════════════════════════

def test_matricula_forjada_no_corpo_e_ignorada(ambiente, monkeypatch):
    cliente, cur, estado = ambiente
    cur.identidade_cadastro = None  # sem cadastro custom → padrão cvp-<matrícula da sessão>
    recebido = {}

    async def _fake(abrir_conn, *, identidade, **kw):
        recebido["identidade"] = identidade
        return _resultado_padrao()
    monkeypatch.setattr(svc, "conversar", _fake)
    r = cliente.post("/agentes/datastage/conversar",
                     json={"mensagem": "oi", "matricula": "MATRICULA-FORJADA-999"})
    assert r.status_code == 200
    assert recebido["identidade"] == f"cvp-{estado['matricula'].lower()}"
    assert "forjada" not in recebido["identidade"].lower()


# ═══════════ 5. achado da revisão adversarial da F2 — vazamento de conexão ══

def test_excecao_generica_do_driver_ainda_fecha_a_conexao(ambiente):
    """Antes, só `except HTTPException` fechava a conexão explicitamente (e
    `else` cobria o caminho feliz) — uma exceção de driver (RuntimeError,
    deadlock, timeout) não batia em nenhum dos dois e vazava conn/cur. Agora
    um `finally` cobre todos os casos."""
    cliente, _cur, _estado = ambiente
    conn = _Conn(_CurQueExplode())
    with patch("routers.agentes.get_db_conn", return_value=conn):
        with pytest.raises(RuntimeError):
            cliente.post("/agentes/datastage/conversar", json={"mensagem": "oi"})
    assert conn.closes >= 1
