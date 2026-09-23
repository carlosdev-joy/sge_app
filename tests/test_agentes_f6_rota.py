"""api/routers/agentes.py — a parte HTTP da F6 (spec docs/spec-agentes-datastage.md).

  • Critério 4: sem `agente_curador`, 403 nos endpoints da curadoria (o admin
    passa por `acao_admin`, como em todo agente).
  • Validação do corpo/consulta (estado e ação) antes de tocar o banco; 404 e
    409 nomeados.
  • `conversar` relê as chamadas que falharam na conversa (`artefatos_json`)
    e as passa à orquestração — é assim que a guarda atravessa perguntas.
"""
from __future__ import annotations

import json
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
from services import agentes as svc  # noqa: E402
from services import agentes_aprendizado as ap  # noqa: E402
from tests._banco_agentes_f6 import BancoF6, _CursorF6  # noqa: E402


class _BancoRota(BancoF6):
    def __init__(self):
        self.conversas: dict[str, dict] = {}
        self.mensagens: dict[str, list] = {}
        super().__init__()

    def cursor(self):
        return _CursorRota(self)


class _CursorRota(_CursorF6):
    def execute(self, sql, params=None):
        b = self.b
        p = list(params or ())
        s = " ".join(sql.lower().split())
        self._rows, self.rowcount = [], -1
        if "from dbo.etl_app_config" in s:
            self._rows = [] if any(str(x).startswith("ia_") for x in p) else [
                ("agentes_enabled", "1"), ("agente_datastage_enabled", "1")]
        elif "select identidade_gateway from dbo.etl_usuario" in s:
            self._rows = [(None,)]
        elif "from dbo.etl_agente_conversa" in s and "select projeto, matricula" in s:
            c = b.conversas.get(p[0])
            self._rows = [(c["projeto"], c["matricula"], 0)] if c else []
        elif s.startswith("insert into dbo.etl_agente_conversa"):
            b.conversas[p[0]] = {"projeto": None, "matricula": p[2]}
        elif s.startswith("update dbo.etl_agente_conversa"):
            b.conversas[p[1]]["projeto"] = p[0]
        elif s.startswith("insert into dbo.etl_agente_mensagem"):
            b.mensagens.setdefault(p[0], []).append(
                {"papel": p[1], "conteudo": p[2], "artefatos": p[4] if len(p) > 4 else None})
        elif s.startswith("select artefatos_json from dbo.etl_agente_mensagem"):
            self._rows = [(m["artefatos"],) for m in b.mensagens.get(p[0], [])
                          if m["papel"] == "assistant" and m["artefatos"] and '"falhou"' in m["artefatos"]]
        elif s.startswith("select papel, conteudo from dbo.etl_agente_mensagem"):
            self._rows = [(m["papel"], m["conteudo"]) for m in b.mensagens.get(p[0], [])]
        else:
            super().execute(sql, params)


@pytest.fixture
def ambiente():
    estado = {"perms": ["tela_agentes"], "matricula": "DEV1", "perfil": "desenvolvedor",
              "extras": ["agente_datastage", "agente_curador"]}
    _app.dependency_overrides[get_current_user] = lambda: {
        "matricula": estado["matricula"], "perfil": estado["perfil"],
        "permissoes": estado["perms"], "permissoes_extra": estado["extras"]}
    banco = _BancoRota()
    with patch("routers.agentes.get_db_conn", side_effect=lambda: banco):
        yield TestClient(_app), banco, estado
    _app.dependency_overrides.pop(get_current_user, None)


# ═══════════ 1. critério 4 — só o curador ═════════════════════════════════

def test_sem_agente_curador_e_403_nos_dois_endpoints(ambiente):
    cliente, banco, estado = ambiente
    estado["extras"] = ["agente_datastage"]  # usa o agente, mas não é curador
    i = banco.novo_aprendizado(estado="rascunho")
    assert cliente.get("/agentes/aprendizados").status_code == 403
    assert cliente.post(f"/agentes/aprendizados/{i}/decidir", json={"acao": "validar"}).status_code == 403
    assert banco.aprendizados[i]["estado"] == "rascunho"


def test_curador_de_perfil_nao_elegivel_e_403(ambiente):
    cliente, _banco, estado = ambiente
    estado["perfil"] = "consulta"
    r = cliente.get("/agentes/aprendizados")
    assert r.status_code == 403 and r.json()["detail"]["code"] == "agente_nao_elegivel"


def test_admin_passa_sem_concessao(ambiente):
    cliente, banco, estado = ambiente
    estado.update(perfil="admin", extras=[], perms=["tela_agentes", PERM_ADMIN])
    banco.novo_aprendizado(estado="rascunho", titulo="semente x")
    r = cliente.get("/agentes/aprendizados")
    assert r.status_code == 200 and r.json()["aprendizados"][0]["titulo"] == "semente x"


# ═══════════ 2. listar e decidir ══════════════════════════════════════════

def test_lista_por_estado_com_evidencia(ambiente):
    cliente, banco, _ = ambiente
    banco.novo_aprendizado(estado="rascunho", titulo="a")
    banco.novo_aprendizado(estado="validado", titulo="b")
    r = cliente.get("/agentes/aprendizados?estado=validado")
    assert [a["titulo"] for a in r.json()["aprendizados"]] == ["b"]
    assert "evidencia" in r.json()["aprendizados"][0]


def test_estado_invalido_e_422(ambiente):
    cliente, banco, _ = ambiente
    r = cliente.get("/agentes/aprendizados?estado=todos")
    assert r.status_code == 422 and r.json()["detail"]["code"] == "estado_invalido"
    assert banco.execs == []


def test_validar_registra_o_curador_da_sessao(ambiente):
    cliente, banco, _ = ambiente
    i = banco.novo_aprendizado(estado="rascunho")
    r = cliente.post(f"/agentes/aprendizados/{i}/decidir", json={"acao": "validar", "matricula": "FORJADA"})
    assert r.status_code == 200
    assert r.json()["aprendizado"]["estado"] == "validado" and banco.aprendizados[i]["validado_por"] == "DEV1"


@pytest.mark.parametrize("corpo", [{}, {"acao": "apagar"}, {"acao": ""}])
def test_acao_invalida_e_422(ambiente, corpo):
    cliente, banco, _ = ambiente
    r = cliente.post("/agentes/aprendizados/1/decidir", json=corpo)
    assert r.status_code == 422 and r.json()["detail"]["code"] == "acao_invalida"
    assert banco.execs == []


def test_transicao_invalida_e_409_com_o_estado_atual(ambiente):
    cliente, banco, _ = ambiente
    i = banco.novo_aprendizado(estado="rejeitado")
    r = cliente.post(f"/agentes/aprendizados/{i}/decidir", json={"acao": "validar"})
    assert r.status_code == 409
    d = r.json()["detail"]
    assert d["code"] == "transicao_invalida" and d["aprendizado"]["estado"] == "rejeitado"


def test_inexistente_e_404(ambiente):
    cliente, _banco, _ = ambiente
    r = cliente.post("/agentes/aprendizados/999/decidir", json={"acao": "validar"})
    assert r.status_code == 404 and r.json()["detail"]["code"] == "aprendizado_nao_encontrado"


# ═══════════ 3. conversar leva as falhas da conversa ══════════════════════

def test_conversar_releva_as_falhas_da_conversa_para_a_orquestracao(ambiente, monkeypatch):
    cliente, _banco, _ = ambiente
    chave = ap.chave_da_chamada("dsjob", {"comando": "lstages", "job_name": "JobX"}, "BI_CVP")
    recebido: list = []

    async def _fake(abrir_conn, **kw):
        recebido.append(kw.get("falhas_anteriores"))
        arts = [] if len(recebido) > 1 else [
            {"ferramenta": "dsjob", "args": {"comando": "lstages", "job_name": "JobX"},
             "falhou": "dsjob_falhou", "chamada": chave}]
        return {"status": "ok", "texto": "t", "projeto": "BI_CVP", "artefatos": arts,
                "aprendizados_usados": [{"id": 1, "titulo": "x"}], "aprendizados_sugeridos": ["s"]}
    monkeypatch.setattr(svc, "conversar", _fake)
    r1 = cliente.post("/agentes/datastage/conversar", json={"mensagem": "explique o JobX"}).json()
    assert r1["aprendizados_usados"] == [{"id": 1, "titulo": "x"}] and r1["aprendizados_sugeridos"] == ["s"]
    cliente.post("/agentes/datastage/conversar", json={"mensagem": "de novo", "conversa_id": r1["conversa_id"]})
    assert recebido == [set(), {chave}]


def test_artefato_invalido_na_conversa_nao_derruba(ambiente, monkeypatch):
    cliente, banco, _ = ambiente
    banco.conversas["conversa-quebrada-1"] = {"projeto": "BI_CVP", "matricula": "DEV1"}
    banco.mensagens["conversa-quebrada-1"] = [
        {"papel": "assistant", "conteudo": "x", "artefatos": 'isto não é json "falhou"'}]
    recebido: list = []

    async def _fake(abrir_conn, **kw):
        recebido.append(kw.get("falhas_anteriores"))
        return {"status": "ok", "texto": "t", "projeto": "BI_CVP", "artefatos": []}
    monkeypatch.setattr(svc, "conversar", _fake)
    r = cliente.post("/agentes/datastage/conversar", json={"mensagem": "oi", "conversa_id": "conversa-quebrada-1"})
    assert r.status_code == 200 and recebido == [set()]
