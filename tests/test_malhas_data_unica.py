"""
Data de referência ÚNICA por malha — F2 da docs/spec-malha-data-unica.md.

Motivação (incidente de produção, malha Carga_Vida, 2026-08-04): a hora de
VIRADA decide o ODATE de quem roda por agenda. Com membros da mesma malha em
viradas diferentes, a corrida sai partida — parte num ODATE, parte em outro — e
o Aguarde libera com metade dos dados do dia anterior.

A malha passa a ter a régua: `etl_malha.hora_virada` (migration 081) é copiada
para TODOS os membros ao salvar. É o mesmo movimento que o Início já fazia para
as raízes, estendido à malha inteira — porque qualquer membro que ainda dispare
por agenda calcula a própria data.

Cobrem: a compilação da virada (quem diverge é alinhado E carimbado para
republicação, quem já estava alinhado não é tocado), a virada nula (segue a
global), as recusas de valor inválido, a marca `equalizar_data` da F3, o
detalhe expondo virada/equalização/divergentes e a degradação sem a 081.
"""
from __future__ import annotations

import os
import sys
from datetime import time
from unittest.mock import MagicMock, patch

import pytest

if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()
os.environ.setdefault("MSSQL_CONN_STR", "__mock__")
from api.main import app as _app  # noqa: F401

from deps import PERM_EDITAR, get_current_user
from tests.test_malhas import FakeCur as FakeCurBase, FakeDb as FakeDbBase


class FakeDb(FakeDbBase):
    """FakeDb da F7 + as colunas da 081 na malha e a hora_virada do pipeline.

    com_081=False simula o deploy parcial: a API degrada com
    migration_081_pendente e NÃO grava — o campo não pode virar decoração."""

    def __init__(self, pipelines=None, com_081=True, com_virada_pipe=True, **kw):
        super().__init__(pipelines=pipelines, **kw)
        self.com_081 = com_081
        self.com_virada_pipe = com_virada_pipe
        self.com_073 = True          # o carimbo de republicação é objeto de teste

    def cursor(self):
        return FakeCur(self)


def _hhmm(v):
    """O SQL Server compara TIME com o literal 'HH:MM:SS' coagindo os dois — o
    dublê precisa fazer o mesmo, senão time(20,0) e '20:00:00' pareceriam
    valores diferentes e todo membro entraria como divergente."""
    if v is None:
        return None
    if hasattr(v, "strftime"):
        return v.strftime("%H:%M")
    return str(v).strip()[:5]


class FakeCur(FakeCurBase):
    def execute(self, sql, params=()):  # noqa: C901 — dispatcher de dublê
        db = self.db
        s = " ".join(str(sql).split())
        params = tuple(params)

        if s.startswith("UPDATE dbo.etl_malha SET hora_virada"):
            if not db.com_081:
                raise RuntimeError("Invalid column name 'hora_virada'")
            k = db._malha_key(params[1])
            if k:
                db.malhas[k]["hora_virada"] = params[0]
            self.rowcount = 1 if k else 0
            return
        if s.startswith("UPDATE dbo.etl_malha SET equalizar_data"):
            if not db.com_081:
                raise RuntimeError("Invalid column name 'equalizar_data'")
            k = db._malha_key(params[1])
            if k:
                db.malhas[k]["equalizar_data"] = params[0]
            self.rowcount = 1 if k else 0
            return
        # Membros FORA da régua (o SELECT com os três NULL-checks do router).
        if s.startswith("SELECT p.pipeline_name FROM dbo.etl_malha_pipeline mp "
                        "JOIN dbo.etl_pipeline p") and "p.hora_virada" in s:
            k = db._malha_key(params[0])
            alvo = params[1]
            out = []
            for m in db.membros:
                if not (k and m["malha"].casefold() == k.casefold()):
                    continue
                pk = db._pipeline_key(m["pipeline"])
                if pk is None:
                    continue
                if _hhmm(db.pipelines[pk].get("hora_virada")) != _hhmm(alvo):
                    out.append((pk,))
            self._rows = sorted(out)
            self.rowcount = -1
            return
        if s.startswith("UPDATE dbo.etl_pipeline SET hora_virada"):
            k = db._pipeline_key(params[1])
            if k:
                db.pipelines[k]["hora_virada"] = params[0]
            self.rowcount = 1 if k else 0
            return
        if s.startswith("UPDATE dbo.etl_pipeline SET dag_config_pendente_em"):
            k = db._pipeline_key(params[0])
            if k is not None and int(db.pipelines[k].get("dag_criada") or 0) == 1:
                db.pipelines[k]["dag_config_pendente"] = 1
                self.rowcount = 1
            else:
                self.rowcount = 0
            return
        # membros do detalhe COM a hora_virada aditiva
        if "FROM dbo.etl_malha_pipeline mp JOIN dbo.etl_pipeline p" in s \
                and "p.hora_virada" in s and "WHERE mp.malha_name = ?" in s:
            k = db._malha_key(params[0])
            out = []
            for m in db.membros:
                if not (k and m["malha"].casefold() == k.casefold()):
                    continue
                pk = db._pipeline_key(m["pipeline"])
                if pk is None:
                    continue
                p = db.pipelines[pk]
                cols = [pk, p.get("active", 1), p.get("criticidade") or "Media",
                        p.get("schedule_type"), m["layout_x"], m["layout_y"],
                        int(p.get("dag_criada") or 0)]
                if "p.dag_config_pendente_em" in s:
                    cols.append(p.get("dag_config_pendente") or None)
                cols.append(p.get("hora_virada"))
                out.append(tuple(cols))
            self._rows = sorted(out)
            self.rowcount = -1
            return

        super().execute(sql, params)


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
    base = {"active": 1, "criticidade": "Media", "schedule_type": "daily",
            "depends_on": None, "dag_criada": 1}
    return {
        "PIPE_A": {**base, "hora_virada": time(20, 0)},
        "PIPE_B": {**base, "hora_virada": None},        # segue a global
        "PIPE_C": {**base, "hora_virada": time(20, 0)},
    }


def _monta(client, nome="M1", membros=("PIPE_A", "PIPE_B", "PIPE_C")):
    assert client.post("/malhas", json={"malha_name": nome}).status_code == 200
    for p in membros:
        assert client.post(f"/malhas/{nome}/pipelines",
                           json={"pipeline_name": p}).status_code == 200


# ── compilação da virada ────────────────────────────────────────────────────

def test_virada_da_malha_alinha_os_membros_divergentes(client, auth_editor):
    """PIPE_B está fora da régua: recebe a virada e é carimbado para
    republicação (a DAG publicada ainda carrega a virada antiga)."""
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        _monta(client)
        r = client.patch("/malhas/M1", json={"hora_virada": "20:00"})
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["hora_virada"] == "20:00"
    assert corpo["equalizados"] == ["PIPE_B"]
    # o driver grava o literal do SQL Server (TIME aceita 'HH:MM:SS')
    assert _hhmm(db.malhas["M1"]["hora_virada"]) == "20:00"
    assert _hhmm(db.pipelines["PIPE_B"]["hora_virada"]) == "20:00"
    # quem já estava na régua NÃO é tocado — carimbar a malha inteira a cada
    # salvamento ensinaria o operador a ignorar o aviso de republicação
    assert db.pipelines["PIPE_B"].get("dag_config_pendente") == 1
    assert db.pipelines["PIPE_A"].get("dag_config_pendente") is None
    assert db.pipelines["PIPE_C"].get("dag_config_pendente") is None


def test_virada_nula_devolve_todos_para_a_global(client, auth_editor):
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        _monta(client)
        r = client.patch("/malhas/M1", json={"hora_virada": None})
    assert r.status_code == 200, r.text
    assert r.json()["hora_virada"] is None
    assert r.json()["equalizados"] == ["PIPE_A", "PIPE_C"]
    assert db.pipelines["PIPE_A"]["hora_virada"] is None
    assert db.pipelines["PIPE_B"]["hora_virada"] is None  # já era


def test_malha_ja_alinhada_nao_carimba_ninguem(client, auth_editor):
    pipes = _pipes()
    pipes["PIPE_B"]["hora_virada"] = time(20, 0)
    db = FakeDb(pipelines=pipes)
    with _patch_db(db):
        _monta(client)
        r = client.patch("/malhas/M1", json={"hora_virada": "20:00"})
    assert r.status_code == 200, r.text
    assert r.json()["equalizados"] == []
    assert all(p.get("dag_config_pendente") is None
               for p in db.pipelines.values())


def test_hora_virada_invalida_422(client, auth_editor):
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        _monta(client)
        r = client.patch("/malhas/M1", json={"hora_virada": "25:99"})
    assert r.status_code == 422
    assert "hora_virada" in r.json()["detail"]
    assert db.malhas["M1"].get("hora_virada") is None   # nada foi gravado


# ── marca da equalização automática (F3) ────────────────────────────────────

def test_equalizar_data_grava(client, auth_editor):
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        _monta(client)
        r = client.patch("/malhas/M1", json={"equalizar_data": 1})
    assert r.status_code == 200, r.text
    assert r.json()["equalizar_data"] == 1
    assert db.malhas["M1"]["equalizar_data"] == 1


def test_equalizar_data_valor_invalido_422(client, auth_editor):
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        _monta(client)
        r = client.patch("/malhas/M1", json={"equalizar_data": "talvez"})
    assert r.status_code == 422


# ── detalhe ─────────────────────────────────────────────────────────────────

def test_detalhe_expoe_virada_e_divergentes(client, auth_editor):
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        _monta(client)
        client.patch("/malhas/M1", json={"equalizar_data": 1})
        db.malhas["M1"]["hora_virada"] = time(20, 0)   # régua salva
        r = client.get("/malhas/M1")
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["hora_virada"] == "20:00"
    assert corpo["equalizar_data"] == 1
    # PIPE_B segue a global e está fora da régua da malha
    assert corpo["virada_divergente"] == ["PIPE_B"]
    membros = {m["pipeline_name"]: m for m in corpo["membros"]}
    assert membros["PIPE_A"]["hora_virada"] == "20:00"
    assert membros["PIPE_B"]["hora_virada"] is None


# ── degradação sem a 081 ────────────────────────────────────────────────────

def test_sem_081_nao_grava_e_avisa(client, auth_editor):
    """Campo que não persiste é pior que campo ausente: a resposta diz que a
    migration falta, e o banco não é tocado."""
    db = FakeDb(pipelines=_pipes(), com_081=False)
    with _patch_db(db):
        _monta(client)
        r = client.patch("/malhas/M1", json={"hora_virada": "20:00"})
    assert r.status_code == 200, r.text
    assert r.json().get("migration_081_pendente") is True
    assert "hora_virada" not in r.json()
    assert db.malhas["M1"].get("hora_virada") is None
    assert db.pipelines["PIPE_B"]["hora_virada"] is None


def test_sem_081_detalhe_nao_promete_regua(client, auth_editor):
    db = FakeDb(pipelines=_pipes(), com_081=False)
    with _patch_db(db):
        _monta(client)
        r = client.get("/malhas/M1")
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert "hora_virada" not in corpo
    assert "virada_divergente" not in corpo
