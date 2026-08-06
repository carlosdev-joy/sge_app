"""
Testes da F14 — Notificação e Fim pela guardiã: o LADO DA API
(docs/malha-componentes-desenho.md §5/§6/§9).

Duas frentes (a guardiã em si é testada em test_dependencia_guardia_dag.py e
as perguntas novas do módulo em test_utils_dependencias.py):

  • validação RICA do config por tipo em POST/PATCH /malhas/{m}/nos — a
    pendência declarada da F13: Notificação {titulo?, mensagem?} (strings),
    Fim {notificar_teams?: bool} (card do Teams OPT-IN, Decisão 14); chave
    desconhecida é 422 nomeando, nunca silêncio. Início/Aguarde seguem SEM
    schema aqui (decisão registrada: o agendamento do Início mora na MALHA —
    Decisão 8 — e o Aguarde não tem configuração);

  • GET /malhas/{m}/execucao devolvendo os eventos de nó (marcador #no:{id}
    RESOLVIDO para o id — risco 6: o único leitor do marcador é este
    endpoint) e `malha_concluida` (evento MALHA_CONCLUIDA do nó Fim), com a
    degradação sem a 075 (flag + arrays vazios, visão intacta).

Dublês: o FakeDb da F10 (nós/arestas da 075) para os gestos de config; o da
F9 (execução/eventos da 067) ESTENDIDO com a sonda da 075 e etl_malha_no
para a visão de execução.
"""
from __future__ import annotations

import os
import sys
from datetime import date, datetime
from unittest.mock import MagicMock, patch

import pytest

if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()
os.environ.setdefault("MSSQL_CONN_STR", "__mock__")
from api.main import app as _app  # noqa: F401  (ordem de import — ver test_copias.py)

from deps import PERM_EDITAR, get_current_user
from tests.test_malhas_f10 import FakeDb as FakeDbF10
from tests.test_malhas_f9 import FakeCur as FakeCurF9, FakeDb as FakeDbF9


# ── dublê da visão de execução + nós da 075 ──────────────────────────────────

class FakeDbExec(FakeDbF9):
    """FakeDb da F9 + sonda da 075 e etl_malha_no (só o que o endpoint de
    execução lê: _nos_da_malha). com_075=False simula o deploy parcial."""

    def __init__(self, pipelines=None, com_tabelas=True, com_067=True,
                 config=None, com_075=True):
        super().__init__(pipelines=pipelines, com_tabelas=com_tabelas,
                         com_067=com_067, config=config)
        self.com_075 = com_075
        # {"id", "malha", "tipo", "config_json", "layout_x", "layout_y"}
        self.nos_desenho: list[dict] = []

    def cursor(self):
        return FakeCurExec(self)


class FakeCurExec(FakeCurF9):
    def execute(self, sql, params=()):  # noqa: C901 — dispatcher de dublê
        db = self.db
        s = " ".join(str(sql).split())
        self._rows = []
        self.rowcount = -1

        if "OBJECT_ID('dbo.etl_malha_no'" in s:
            self._rows = [(1, 1)] if db.com_075 else [(None, None)]
            return
        if s.startswith("SELECT id, tipo, config_json, layout_x, layout_y "
                        "FROM dbo.etl_malha_no"):
            k = (params[0] or "").casefold()
            self._rows = sorted(
                (n["id"], n["tipo"], n.get("config_json"),
                 n.get("layout_x"), n.get("layout_y"))
                for n in db.nos_desenho if n["malha"].casefold() == k)
            return

        super().execute(sql, params)


# ── fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def auth_editor(app):
    app.dependency_overrides[get_current_user] = lambda: {
        "matricula": "DEV1", "perfil": "desenvolvedor",
        "permissoes": [PERM_EDITAR, "tela_malha"],
    }
    yield
    app.dependency_overrides.pop(get_current_user, None)


def _patch_db(db):
    return patch("routers.malhas.get_db_conn", return_value=db)


def _pipes():
    return {
        "PIPE_A": {"active": 1, "criticidade": "Alta", "schedule_type": "daily",
                   "depends_on": None},
        "PIPE_B": {"active": 1, "criticidade": "Media", "schedule_type": "daily",
                   "depends_on": None},
    }


def _monta_malha(client, nome, membros=()):
    assert client.post("/malhas", json={"malha_name": nome}).status_code == 200
    for p in membros:
        assert client.post(f"/malhas/{nome}/pipelines",
                           json={"pipeline_name": p}).status_code == 200


def _cria_no(client, malha, tipo, config=None):
    r = client.post(f"/malhas/{malha}/nos", json={"tipo": tipo,
                                                  "config": config})
    return r


# ═══════════ 1. validação rica do config por tipo (POST /nos) ════════════════

def test_notificacao_config_valido_e_gravado(client, auth_editor):
    db = FakeDbF10(pipelines=_pipes())
    with _patch_db(db):
        _monta_malha(client, "M1")
        r = _cria_no(client, "M1", "notificacao",
                     {"titulo": "Onda 1 OK", "mensagem": "todas com sucesso"})
    assert r.status_code == 200
    nid = r.json()["id"]
    assert '"titulo"' in db.nos[nid]["config_json"]


@pytest.mark.parametrize("config,trecho", [
    ({"foo": 1}, "chave(s) desconhecida(s): foo"),
    ({"titulo": 5}, "'titulo' da Notificação deve ser texto"),
    ({"mensagem": ["x"]}, "'mensagem' da Notificação deve ser texto"),
])
def test_notificacao_config_invalido_422(client, auth_editor, config, trecho):
    db = FakeDbF10(pipelines=_pipes())
    with _patch_db(db):
        _monta_malha(client, "M1")
        r = _cria_no(client, "M1", "notificacao", config)
    assert r.status_code == 422
    assert trecho in r.json()["detail"]
    assert db.nos == {}                     # 422 ANTES de qualquer escrita


def test_fim_config_valido_e_optin(client, auth_editor):
    db = FakeDbF10(pipelines=_pipes())
    with _patch_db(db):
        _monta_malha(client, "M1")
        r = _cria_no(client, "M1", "fim", {"notificar_teams": True})
    assert r.status_code == 200


@pytest.mark.parametrize("config,trecho", [
    ({"notificar_teams": "sim"}, "deve ser booleano"),
    ({"titulo": "x"}, "chave(s) desconhecida(s): titulo"),
])
def test_fim_config_invalido_422(client, auth_editor, config, trecho):
    db = FakeDbF10(pipelines=_pipes())
    with _patch_db(db):
        _monta_malha(client, "M1")
        r = _cria_no(client, "M1", "fim", config)
    assert r.status_code == 422
    assert trecho in r.json()["detail"]


def test_inicio_e_aguarde_seguem_sem_schema_de_config(client, auth_editor):
    """Decisão registrada: o agendamento do Início mora na MALHA (Decisão 8)
    e o Aguarde não tem configuração — config estrutural (dict) passa."""
    db = FakeDbF10(pipelines=_pipes())
    with _patch_db(db):
        _monta_malha(client, "M1")
        assert _cria_no(client, "M1", "inicio",
                        {"qualquer": "coisa"}).status_code == 200
        assert _cria_no(client, "M1", "aguarde",
                        {"outra": 1}).status_code == 200


# ═══════════ 2. validação rica no PATCH (tipo vem da LINHA) ══════════════════

def test_patch_config_valida_pelo_tipo_da_linha(client, auth_editor):
    db = FakeDbF10(pipelines=_pipes())
    with _patch_db(db):
        _monta_malha(client, "M1")
        nid = _cria_no(client, "M1", "fim").json()["id"]
        ok = client.patch(f"/malhas/M1/nos/{nid}",
                          json={"config": {"notificar_teams": True}})
        ruim = client.patch(f"/malhas/M1/nos/{nid}",
                            json={"config": {"titulo": "x"}})
    assert ok.status_code == 200
    assert ruim.status_code == 422
    assert "chave(s) desconhecida(s): titulo" in ruim.json()["detail"]
    assert '"notificar_teams"' in db.nos[nid]["config_json"]  # o 422 não gravou


def test_patch_config_none_limpa_sem_validar(client, auth_editor):
    db = FakeDbF10(pipelines=_pipes())
    with _patch_db(db):
        _monta_malha(client, "M1")
        nid = _cria_no(client, "M1", "notificacao",
                       {"titulo": "T"}).json()["id"]
        r = client.patch(f"/malhas/M1/nos/{nid}", json={"config": None})
    assert r.status_code == 200
    assert db.nos[nid]["config_json"] is None


# ═══════════ 3. execução: eventos de nó (#no:*) + malha_concluida ════════════

_D = date(2026, 8, 1)
_TS = datetime(2026, 8, 1, 8, 30, 0)


def _no(db, nid, tipo, malha="M1"):
    db.nos_desenho.append({"id": nid, "malha": malha, "tipo": tipo,
                           "config_json": None, "layout_x": None,
                           "layout_y": None})


def _evento(db, pipeline, tipo, detalhe="d", detectado_em=_TS, data_ref=_D):
    db.eventos.append({"pipeline": pipeline, "data_referencia": data_ref,
                       "tipo": tipo, "detalhe": detalhe,
                       "detectado_em": detectado_em})


def test_eventos_de_no_resolvidos_fora_do_array_de_membros(client, auth_editor):
    """O marcador #no:{id} é RESOLVIDO para o nó desta malha (eventos_no);
    membro segue em eventos; marcador de nó de OUTRA malha não aparece em
    lugar nenhum — a mesma regra do filtro por membro."""
    db = FakeDbExec(pipelines=_pipes())
    with _patch_db(db):
        _monta_malha(client, "M1", ["PIPE_A"])
        _no(db, 5, "notificacao")
        _evento(db, "PIPE_A", "JANELA_ESTOUROU")
        _evento(db, "#no:5", "MALHA_NOTIFICACAO", detalhe="Onda 1 OK")
        _evento(db, "#no:99", "MALHA_NOTIFICACAO")      # nó de outra malha
        r = client.get(f"/malhas/M1/execucao?data_referencia={_D}")
    assert r.status_code == 200
    body = r.json()
    assert [e["pipeline_name"] for e in body["eventos"]] == ["PIPE_A"]
    # F10: `notificado_em` é aditivo e vale para TODO evento — o de nó
    # observador também entra na fila do Teams.
    assert body["eventos_no"] == [{
        "no_id": 5, "tipo_no": "notificacao", "tipo": "MALHA_NOTIFICACAO",
        "criado_em": "2026-08-01 08:30:00", "mensagem": "Onda 1 OK",
        "notificado_em": None}]
    assert body["malha_concluida"] is None      # notificação não conclui


def test_malha_concluida_vem_do_evento_do_fim(client, auth_editor):
    db = FakeDbExec(pipelines=_pipes())
    with _patch_db(db):
        _monta_malha(client, "M1", ["PIPE_A"])
        _no(db, 5, "notificacao")
        _no(db, 9, "fim")
        _evento(db, "#no:5", "MALHA_NOTIFICACAO")
        _evento(db, "#no:9", "MALHA_CONCLUIDA",
                detalhe="Malha M1 concluída na data 2026-08-01 — 2 pipeline(s) com SUCESSO")
        r = client.get(f"/malhas/M1/execucao?data_referencia={_D}")
    assert r.status_code == 200
    body = r.json()
    assert body["malha_concluida"] == {"em": "2026-08-01 08:30:00"}
    assert {e["no_id"] for e in body["eventos_no"]} == {5, 9}


def test_evento_de_outra_data_nao_vaza(client, auth_editor):
    db = FakeDbExec(pipelines=_pipes())
    with _patch_db(db):
        _monta_malha(client, "M1", ["PIPE_A"])
        _no(db, 9, "fim")
        _evento(db, "#no:9", "MALHA_CONCLUIDA", data_ref=date(2026, 7, 31))
        r = client.get(f"/malhas/M1/execucao?data_referencia={_D}")
    body = r.json()
    assert body["eventos_no"] == [] and body["malha_concluida"] is None


def test_sem_075_execucao_degrada_com_flag_e_visao_intacta(client, auth_editor):
    """Deploy parcial sem a 075: eventos_no vazio + migration_075_pendente;
    os eventos de MEMBRO continuam — a visão não quebra (princípio 6). O
    evento #no:* fica invisível AQUI (sem a tabela não há como resolver o
    marcador), mas segue no banco."""
    db = FakeDbExec(pipelines=_pipes(), com_075=False)
    with _patch_db(db):
        _monta_malha(client, "M1", ["PIPE_A"])
        _evento(db, "PIPE_A", "JANELA_ESTOUROU")
        _evento(db, "#no:5", "MALHA_NOTIFICACAO")
        r = client.get(f"/malhas/M1/execucao?data_referencia={_D}")
    assert r.status_code == 200
    body = r.json()
    assert body["migration_075_pendente"] is True
    assert body["eventos_no"] == [] and body["malha_concluida"] is None
    assert [e["pipeline_name"] for e in body["eventos"]] == ["PIPE_A"]


def test_sem_067_resposta_inclui_chaves_novas_vazias(client, auth_editor):
    """O contrato do payload é estável: mesmo no degrade da 067 as chaves da
    F14 existem (front antigo ignora; front novo não quebra)."""
    db = FakeDbExec(pipelines=_pipes(), com_067=False)
    with _patch_db(db):
        _monta_malha(client, "M1", ["PIPE_A"])
        r = client.get(f"/malhas/M1/execucao?data_referencia={_D}")
    body = r.json()
    assert body["migration_067_pendente"] is True
    assert body["eventos_no"] == [] and body["malha_concluida"] is None
