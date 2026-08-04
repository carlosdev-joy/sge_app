"""
SEGURAR o Aguarde — o hold do ponto de junção (migration 082).

O Aguarde é açúcar de compilação: ligar as pernas vira dependência normal na
067, e quem segura é o predicado. Não havia como dizer "pare AQUI e não solte
até eu mandar" — só inativando os pipelines à frente, um a um.

Segurado, o nó não solta ninguém, e isso vale nas TRÊS portas porque quem
obedece é o predicado canônico: push, guardiã e painel herdam a trava sem
saber que ela existe.

Cobrem: o gesto (segurar/liberar, permissão de EXECUÇÃO), a recusa de segurar
o que não é Aguarde, a degradação sem a 082 (503 — botão que não segura é pior
que botão ausente), o detalhe expondo o estado e a lista de quem está preso
atrás da trava.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()
os.environ.setdefault("MSSQL_CONN_STR", "__mock__")
from api.main import app as _app  # noqa: F401

from deps import PERM_EDITAR, PERM_EXECUTAR, get_current_user
from tests.test_malhas_f10 import FakeCur as FakeCurF10, FakeDb as FakeDbF10
from tests.test_malhas_f10 import _cria_no, _monta_malha


class FakeDb(FakeDbF10):
    def __init__(self, pipelines=None, com_082=True, **kw):
        super().__init__(pipelines=pipelines, **kw)
        self.com_082 = com_082
        # id do nó -> (retido_em, retido_por)
        self.retencao: dict = {}

    def cursor(self):
        return FakeCur(self)


class FakeCur(FakeCurF10):
    def execute(self, sql, params=()):  # noqa: C901 — dispatcher de dublê
        db = self.db
        s = " ".join(str(sql).split())
        params = tuple(params)

        if "COL_LENGTH('dbo.etl_malha_no', 'retido_em')" in s:
            self._rows = [(8, 64)] if db.com_082 else [(None, None)]
            self.rowcount = -1
            return
        if s.startswith("SELECT tipo FROM dbo.etl_malha_no WHERE id"):
            n = db.nos.get(params[0])
            self._rows = ([(n["tipo"],)] if n
                          and n["malha"].casefold() == (params[1] or "").casefold()
                          else [])
            self.rowcount = -1
            return
        if s.startswith("UPDATE dbo.etl_malha_no SET retido_em = GETDATE()"):
            db.retencao[params[1]] = (datetime(2026, 8, 4, 10, 0), params[0])
            self.rowcount = 1
            return
        if s.startswith("UPDATE dbo.etl_malha_no SET retido_em = NULL"):
            db.retencao.pop(params[0], None)
            self.rowcount = 1
            return
        if s.startswith("SELECT DISTINCT pipeline_name FROM dbo.etl_pipeline_dependencia "
                        "WHERE origem_no"):
            self._rows = sorted(
                (d["pipeline"],) for d in db.dependencias
                if d.get("origem_no") == params[0])
            self.rowcount = -1
            return
        # leitura dos nós COM as colunas da 082
        if s.startswith("SELECT id, tipo, config_json, layout_x, layout_y, "
                        "retido_em, retido_por"):
            k = (params[0] or "").casefold()
            out = []
            for nid, n in sorted(db.nos.items()):
                if n["malha"].casefold() != k:
                    continue
                ret = db.retencao.get(nid, (None, None))
                out.append((nid, n["tipo"], n["config_json"], n["layout_x"],
                            n["layout_y"], ret[0], ret[1]))
            self._rows = out
            self.rowcount = -1
            return

        super().execute(sql, params)


@pytest.fixture
def auth_operador(app):
    app.dependency_overrides[get_current_user] = lambda: {
        "matricula": "OPER1", "perfil": "operador",
        "permissoes": [PERM_EDITAR, PERM_EXECUTAR, "tela_malha"],
    }
    yield
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def auth_sem_executar(app):
    app.dependency_overrides[get_current_user] = lambda: {
        "matricula": "DEV1", "perfil": "desenvolvedor",
        "permissoes": [PERM_EDITAR, "tela_malha"],
    }
    yield
    app.dependency_overrides.pop(get_current_user, None)


def _patch_db(db):
    return patch("routers.malhas.get_db_conn", return_value=db)


def _pipes():
    base = {"active": 1, "criticidade": "Media", "schedule_type": "daily",
            "depends_on": None, "dag_criada": 1}
    return {"PIPE_A": dict(base), "PIPE_B": dict(base), "PIPE_C": dict(base)}


def _retencao(client, malha, no_id, reter=True):
    return client.post(f"/malhas/{malha}/nos/{no_id}/retencao",
                       json={"reter": reter})


def test_rota_registrada(client):
    r = client.get("/openapi.json")
    assert "/malhas/{malha_name}/nos/{no_id}/retencao" in r.json()["paths"]


def test_segurar_e_liberar_o_aguarde(client, auth_operador):
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        _monta_malha(client, "M1", ["PIPE_A", "PIPE_B"])
        no = _cria_no(client, "M1", "aguarde")
        r = _retencao(client, "M1", no)
        assert r.status_code == 200, r.text
        assert r.json()["retido"] is True
        assert r.json()["retido_por"] == "OPER1"
        assert no in db.retencao
        # o estado aparece no detalhe — o card precisa mostrar a trava
        det = client.get("/malhas/M1").json()
        aguarde = next(n for n in det["nos"] if n["id"] == no)
        assert aguarde["retido_em"] is not None
        assert aguarde["retido_por"] == "OPER1"
        # liberar devolve ao normal
        r2 = _retencao(client, "M1", no, reter=False)
        assert r2.status_code == 200 and r2.json()["retido"] is False
        assert no not in db.retencao


def test_segurar_exige_permissao_de_execucao(client, auth_sem_executar):
    """Segurar a malha é OPERAÇÃO — quem só edita o desenho não segura."""
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        assert _retencao(client, "M1", 1).status_code == 403


def test_so_o_aguarde_pode_ser_segurado(client, auth_operador):
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        _monta_malha(client, "M1", ["PIPE_A"])
        inicio = _cria_no(client, "M1", "inicio")
        r = _retencao(client, "M1", inicio)
    assert r.status_code == 422
    assert "Início" in r.json()["detail"]


def test_no_inexistente_404(client, auth_operador):
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        _monta_malha(client, "M1", ["PIPE_A"])
        r = _retencao(client, "M1", 999)
    assert r.status_code == 404


def test_sem_a_082_recusa_com_instrucao(client, auth_operador):
    """Botão que não segura é pior que botão ausente: 503 nomeando a
    migration, e nada é gravado."""
    db = FakeDb(pipelines=_pipes(), com_082=False)
    with _patch_db(db):
        _monta_malha(client, "M1", ["PIPE_A"])
        no = _cria_no(client, "M1", "aguarde")
        r = _retencao(client, "M1", no)
    assert r.status_code == 503
    assert "082" in r.json()["detail"]
    assert db.retencao == {}


def test_sem_a_082_o_detalhe_nao_promete_trava(client, auth_operador):
    db = FakeDb(pipelines=_pipes(), com_082=False)
    with _patch_db(db):
        _monta_malha(client, "M1", ["PIPE_A"])
        _cria_no(client, "M1", "aguarde")
        det = client.get("/malhas/M1").json()
    assert all("retido_em" not in n for n in det["nos"])


def test_liberar_diz_quem_estava_preso(client, auth_operador):
    """Quem estava atrás da trava não parte na hora: quem solta precisa saber
    que o disparo vem no próximo ciclo, não no clique."""
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        _monta_malha(client, "M1", ["PIPE_A", "PIPE_B", "PIPE_C"])
        no = _cria_no(client, "M1", "aguarde")
        db.dependencias.append({"pipeline": "PIPE_C", "depende_de": "PIPE_A",
                                "origem_no": no})
        r = _retencao(client, "M1", no, reter=False)
    assert r.status_code == 200, r.text
    assert r.json()["dependentes"] == ["PIPE_C"]
