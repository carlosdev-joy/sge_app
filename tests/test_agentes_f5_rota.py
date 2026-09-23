"""api/routers/agentes.py — a parte HTTP da F5 (spec docs/spec-agentes-datastage.md).

  1. `POST /agentes/datastage/conversar` grava as propostas válidas na MESMA
     transação da resposta, devolve cada uma com `id` e guarda os ids em
     `artefatos_json` — sem misturá-los à lista de ferramentas que a tela
     mostra em "Consultei:".
  2. `GET /agentes/conversas/{id}` devolve, em cada resposta, as propostas
     com o estado ATUAL (a decisão pode ter vindo depois).
  3. `POST /agentes/propostas/{id}/decidir`: só o dono (outro usuário → 404
     igual ao de inexistente), idempotente, 409 nomeado para decisão
     oposta ou proposta vencida, 422 para decisão inválida, e o mesmo gate
     de `require_agente` do chat.
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

from deps import get_current_user  # noqa: E402
from services import agentes as svc  # noqa: E402
from services import agentes_conhecimento as ac  # noqa: E402
from tests._banco_agentes_f5 import BancoF5, _Cursor  # noqa: E402


class _BancoRota(BancoF5):
    """O banco da F5 + o mínimo de conversa/mensagem/config que a rota lê."""

    def __init__(self):
        self.conversas: dict[str, dict] = {}
        self.mensagens: dict[str, list] = {}
        super().__init__()

    def cursor(self):
        return _CursorRota(self)


class _CursorRota(_Cursor):
    def execute(self, sql, params=None):
        b = self.b
        p = list(params or ())
        s = " ".join(sql.lower().split())
        self._rows, self.rowcount = [], -1
        if "from dbo.etl_app_config" in s:
            self._rows = [("agentes_enabled", "1"), ("agente_datastage_enabled", "1")] \
                if not any(str(x).startswith("ia_") for x in p) else []
        elif "select identidade_gateway from dbo.etl_usuario" in s:
            self._rows = [(None,)]
        elif "from dbo.etl_agente_conversa" in s and "select projeto, matricula" in s:
            c = b.conversas.get(p[0])
            self._rows = [(c["projeto"], c["matricula"], 0)] if c else []
        elif "from dbo.etl_agente_conversa" in s and "select agente" in s:
            c = b.conversas.get(p[0])
            self._rows = [("datastage", "t", c["projeto"], None, None, c["matricula"], 0)] if c else []
        elif s.startswith("insert into dbo.etl_agente_conversa"):
            b.conversas[p[0]] = {"projeto": None, "matricula": p[2]}
        elif s.startswith("update dbo.etl_agente_conversa"):
            b.conversas[p[1]]["projeto"] = p[0]
        elif s.startswith("insert into dbo.etl_agente_mensagem"):
            b.mensagens.setdefault(p[0], []).append(
                (p[1], p[2], p[3] if len(p) > 3 else None, p[4] if len(p) > 4 else None, None))
        elif "from dbo.etl_agente_mensagem" in s and "select papel, conteudo, status" in s:
            self._rows = list(b.mensagens.get(p[0], []))
        elif "from dbo.etl_agente_mensagem" in s:
            self._rows = [(m[0], m[1]) for m in b.mensagens.get(p[0], [])]
        else:
            super().execute(sql, params)


@pytest.fixture
def ambiente(monkeypatch):
    estado = {"perms": ["tela_agentes"], "matricula": "DEV1", "perfil": "desenvolvedor",
              "extras": ["agente_datastage"]}
    _app.dependency_overrides[get_current_user] = lambda: {
        "matricula": estado["matricula"], "perfil": estado["perfil"],
        "permissoes": estado["perms"], "permissoes_extra": estado["extras"]}
    banco = _BancoRota()
    with patch("routers.agentes.get_db_conn", side_effect=lambda: banco):
        yield TestClient(_app), banco, estado
    _app.dependency_overrides.pop(get_current_user, None)


def _prop(**over):
    base = {"ds_project": "BI_CVP", "job_name": "JobX", "tipo": "lineage", "chave": "fluxo",
            "valor_json": '"carrega clientes"', "motivo": "m", "evidencia": "LerClientes GravarSaida"}
    base.update(over)
    return base


def _fake_conversar(**extra):
    async def _fake(abrir_conn, **kw):
        return {"status": "ok", "texto": "O JobX carrega clientes.", "projeto": "BI_CVP",
                "artefatos": [{"ferramenta": "dsjob", "args": {"comando": "lstages", "job_name": "JobX"}}],
                **extra}
    return _fake


# ═══════════ 1. conversar grava as propostas ══════════════════════════════

def test_conversar_grava_propostas_e_devolve_com_id(ambiente, monkeypatch):
    cliente, banco, _ = ambiente
    monkeypatch.setattr(svc, "conversar", _fake_conversar(propostas=[_prop()], propostas_recusadas=["x"]))
    r = cliente.post("/agentes/datastage/conversar", json={"mensagem": "explique o JobX"})
    assert r.status_code == 200
    body = r.json()
    [p] = body["propostas"]
    assert p["id"] in banco.propostas and p["estado"] == "pendente" and p["valor"] == "carrega clientes"
    assert body["propostas_recusadas"] == ["x"]
    # a linha "Consultei:" continua recebendo só ferramentas
    assert body["artefatos"] == [{"ferramenta": "dsjob", "args": {"comando": "lstages", "job_name": "JobX"}}]
    # o dono da proposta é a sessão, e ela fica ligada à conversa
    prop = banco.propostas[p["id"]]
    assert prop["matricula"] == "DEV1" and prop["conversa_id"] == body["conversa_id"]
    # e o id foi guardado na mensagem do assistente
    artefatos = json.loads(banco.mensagens[body["conversa_id"]][-1][3])
    assert {"proposta_id": p["id"]} in artefatos
    # nenhuma interpretação vira fato sem decisão (critério 2)
    assert banco.fatos == []


def test_conversar_sem_proposta_nao_mexe_na_tabela(ambiente, monkeypatch):
    cliente, banco, _ = ambiente
    monkeypatch.setattr(svc, "conversar", _fake_conversar())
    r = cliente.post("/agentes/datastage/conversar", json={"mensagem": "oi"})
    assert r.status_code == 200 and r.json()["propostas"] == [] and r.json()["propostas_recusadas"] == []
    assert not any("etl_agente_proposta" in sql.lower() for sql, _ in banco.execs)


def test_conversar_passa_a_validade_configurada(ambiente, monkeypatch):
    cliente, _banco, _ = ambiente
    recebido = {}

    async def _fake(abrir_conn, **kw):
        recebido.update(kw)
        return {"status": "ok", "texto": "t", "projeto": None, "artefatos": []}
    monkeypatch.setattr(svc, "conversar", _fake)
    cliente.post("/agentes/datastage/conversar", json={"mensagem": "oi"})
    assert recebido["validade_fatos_dias"] == 7


# ═══════════ 2. retomar mostra as propostas com o estado atual ════════════

def test_retomar_traz_as_propostas_da_resposta_com_estado_atual(ambiente, monkeypatch):
    cliente, banco, _ = ambiente
    monkeypatch.setattr(svc, "conversar", _fake_conversar(propostas=[_prop()]))
    body = cliente.post("/agentes/datastage/conversar", json={"mensagem": "explique"}).json()
    pid = body["propostas"][0]["id"]
    assert cliente.post(f"/agentes/propostas/{pid}/decidir", json={"decisao": "aprovar"}).status_code == 200

    d = cliente.get(f"/agentes/conversas/{body['conversa_id']}").json()
    user, assistente = d["mensagens"]
    assert "propostas" not in user
    assert assistente["artefatos"] == body["artefatos"]  # sem o {"proposta_id"}
    [p] = assistente["propostas"]
    assert p["id"] == pid and p["estado"] == "aprovada" and p["decidida_por"] == "DEV1"


# ═══════════ 3. decidir ═══════════════════════════════════════════════════

def test_aprovar_grava_o_fato_e_devolve_a_proposta(ambiente):
    cliente, banco, _ = ambiente
    pid = banco.nova_proposta()
    r = cliente.post(f"/agentes/propostas/{pid}/decidir", json={"decisao": "aprovar"})
    assert r.status_code == 200
    assert r.json()["proposta"]["estado"] == "aprovada"
    assert [f["origem"] for f in banco.fatos] == [ac.ORIGEM_INTERPRETACAO]


def test_aprovar_duas_vezes_e_inofensivo(ambiente):
    cliente, banco, _ = ambiente
    pid = banco.nova_proposta()
    cliente.post(f"/agentes/propostas/{pid}/decidir", json={"decisao": "aprovar"})
    r = cliente.post(f"/agentes/propostas/{pid}/decidir", json={"decisao": "aprovar"})
    assert r.status_code == 200 and r.json()["proposta"]["ja_decidida"] is True
    assert len(banco.fatos) == 1


def test_recusar_nao_grava_fato(ambiente):
    cliente, banco, _ = ambiente
    pid = banco.nova_proposta()
    r = cliente.post(f"/agentes/propostas/{pid}/decidir", json={"decisao": "recusar"})
    assert r.status_code == 200 and r.json()["proposta"]["estado"] == "recusada"
    assert banco.fatos == []


def test_proposta_de_outro_usuario_e_404_igual_a_inexistente(ambiente):
    cliente, banco, _ = ambiente
    pid = banco.nova_proposta(matricula="OUTRO")
    alheia = cliente.post(f"/agentes/propostas/{pid}/decidir", json={"decisao": "aprovar"})
    inexistente = cliente.post("/agentes/propostas/9999/decidir", json={"decisao": "aprovar"})
    assert alheia.status_code == inexistente.status_code == 404
    assert alheia.json() == inexistente.json()
    assert banco.propostas[pid]["estado"] == "pendente" and banco.fatos == []


def test_decisao_oposta_e_409_nomeado(ambiente):
    cliente, banco, _ = ambiente
    pid = banco.nova_proposta()
    cliente.post(f"/agentes/propostas/{pid}/decidir", json={"decisao": "recusar"})
    r = cliente.post(f"/agentes/propostas/{pid}/decidir", json={"decisao": "aprovar"})
    assert r.status_code == 409
    detalhe = r.json()["detail"]
    assert detalhe["code"] == "proposta_ja_decidida" and detalhe["proposta"]["estado"] == "recusada"


def test_proposta_vencida_e_409_expirada(ambiente):
    cliente, banco, _ = ambiente
    pid = banco.nova_proposta(idade_dias=40)
    r = cliente.post(f"/agentes/propostas/{pid}/decidir", json={"decisao": "aprovar"})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "proposta_expirada"


@pytest.mark.parametrize("corpo", [{}, {"decisao": "talvez"}, {"decisao": ""}])
def test_decisao_invalida_e_422_sem_tocar_o_banco(ambiente, corpo):
    cliente, banco, _ = ambiente
    r = cliente.post("/agentes/propostas/1/decidir", json=corpo)
    assert r.status_code == 422 and r.json()["detail"]["code"] == "decisao_invalida"
    assert banco.execs == []


def test_decidir_exige_o_agente_liberado(ambiente):
    cliente, banco, estado = ambiente
    pid = banco.nova_proposta()
    estado["extras"] = []
    r = cliente.post(f"/agentes/propostas/{pid}/decidir", json={"decisao": "aprovar"})
    assert r.status_code == 403
    assert banco.fatos == []


def test_matricula_do_corpo_e_ignorada(ambiente):
    cliente, banco, _ = ambiente
    pid = banco.nova_proposta(matricula="OUTRO")
    r = cliente.post(f"/agentes/propostas/{pid}/decidir", json={"decisao": "aprovar", "matricula": "OUTRO"})
    assert r.status_code == 404
