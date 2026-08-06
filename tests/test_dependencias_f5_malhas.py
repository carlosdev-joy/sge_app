"""
F5 da retomada — o lado de routers/malhas.py:

  • POST/DELETE /dependencias ligam dag_config_pendente do DEPENDENTE (nunca
    do pai) na mesma transação, com guard da migration 073 (Decisão 6/D30);
  • GET /malhas/{name}/execucao ganha `faltantes` ADITIVO para corrida em
    AGUARDANDO_DEPENDENCIA/NAO_LIBEROU, vindo do PORT do predicado do motor
    (D32) — contrato F9 anterior intacto (testes da F9 seguem verdes).

Dublê: FakeDb da F9 ESTENDIDO com o NOT EXISTS do port (avaliado de verdade
sobre o estado) e com a coluna da 073 ligável por teste.
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
from tests.test_malhas_f9 import FakeCur as FakeCurF9, FakeDb as FakeDbF9

_D = date(2026, 8, 1)


class FakeDb(FakeDbF9):
    """FakeDb da F9 + avaliação do predicado do port + coluna da 073."""

    def __init__(self, pipelines=None, com_tabelas=True, com_067=True,
                 config=None, com_073=False):
        super().__init__(pipelines=pipelines, com_tabelas=com_tabelas,
                         com_067=com_067, config=config)
        self.com_073 = com_073

    def cursor(self):
        return FakeCur(self)


class FakeCur(FakeCurF9):
    def _faltantes(self, pipeline, data_ref):
        """O predicado, avaliado DE VERDADE sobre o estado do dublê."""
        db = self.db
        for d in db.dependencias:
            if d["pipeline"].casefold() != str(pipeline).casefold():
                continue
            tem_sucesso = any(
                e["pipeline"].casefold() == d["depende_de"].casefold()
                and e["data_referencia"] == data_ref
                and e["status"] == "SUCESSO"
                for e in db.execucoes)
            if not tem_sucesso:
                yield d["depende_de"]

    def execute(self, sql, params=()):  # noqa: C901 — dispatcher de dublê
        db = self.db
        s = " ".join(str(sql).split())
        # O predicado do PORT (services.dependencias.faltantes) — avaliado DE
        # VERDADE: predecessor sem SUCESSO na data entra nos faltantes.
        if s.startswith("SELECT dd.depende_de FROM dbo.etl_pipeline_dependencia dd") \
                and "NOT EXISTS" in s:
            if not db.com_067:
                raise RuntimeError("Invalid object name (migration 067 ausente)")
            pipeline, data_ref = params
            self._rows = [(f,) for f in self._faltantes(pipeline, data_ref)]
            self.rowcount = -1
            return
        # F10 — a forma de CONJUNTO do MESMO predicado (uma consulta para N
        # pipelines). O dublê a avalia pelo mesmo caminho de propósito: se as
        # duas formas divergirem, é aqui que a diferença aparece, e não na
        # madrugada. `params` = (…nomes…, data_ref).
        if s.startswith("SELECT dd.pipeline_name, dd.depende_de "
                        "FROM dbo.etl_pipeline_dependencia dd") \
                and "NOT EXISTS" in s:
            if not db.com_067:
                raise RuntimeError("Invalid object name (migration 067 ausente)")
            *nomes, data_ref = params
            self._rows = [(p, f) for p in nomes
                          for f in self._faltantes(p, data_ref)]
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
    return {
        "PIPE_A": {"active": 1, "criticidade": "Alta", "schedule_type": "daily",
                   "depends_on": None, "dag_criada": 1, "dag_config_pendente": 0},
        "PIPE_B": {"active": 1, "criticidade": "Media", "schedule_type": "daily",
                   "depends_on": None, "dag_criada": 1, "dag_config_pendente": 0},
        "PIPE_NOVO": {"active": 1, "criticidade": "Baixa", "schedule_type": "daily",
                      "depends_on": None, "dag_criada": 0, "dag_config_pendente": 0},
    }


def _delete(client, json):
    return client.request("DELETE", "/dependencias", json=json)


def _monta_malha(client, nome, membros):
    assert client.post("/malhas", json={"malha_name": nome}).status_code == 200
    for p in membros:
        assert client.post(f"/malhas/{nome}/pipelines",
                           json={"pipeline_name": p}).status_code == 200


def _exec(pipeline, status, execution_id="run_1", inicio=None, motivo=None):
    return {"pipeline": pipeline, "data_referencia": _D, "status": status,
            "inicio": inicio, "fim": None, "disparado_por": "agenda",
            "motivo": motivo, "execution_id": execution_id}


# ── Decisão 6/D30: flag nas duas portas de escrita de dependência ────────────

def test_post_dependencia_liga_flag_do_dependente_nunca_do_pai(client, auth_editor):
    db = FakeDb(pipelines=_pipes(), com_073=True)
    with _patch_db(db):
        r = client.post("/dependencias",
                        json={"pipeline_name": "PIPE_A", "depende_de": "PIPE_B"})
    assert r.status_code == 200
    assert r.json() == {"ok": True, "ja_existia": False, "dag_config_pendente": True}
    assert db.pipelines["PIPE_A"]["dag_config_pendente"] == 1   # o filho muda de schedule
    assert db.pipelines["PIPE_B"]["dag_config_pendente"] == 0   # o pai lê a tabela ao vivo


def test_post_dependencia_dag_nunca_publicada_nao_liga(client, auth_editor):
    db = FakeDb(pipelines=_pipes(), com_073=True)
    with _patch_db(db):
        r = client.post("/dependencias",
                        json={"pipeline_name": "PIPE_NOVO", "depende_de": "PIPE_B"})
    assert r.status_code == 200
    assert r.json()["dag_config_pendente"] is False
    assert db.pipelines["PIPE_NOVO"]["dag_config_pendente"] == 0


def test_post_dependencia_ja_existente_nao_liga(client, auth_editor):
    db = FakeDb(pipelines=_pipes(), com_073=True)
    with _patch_db(db):
        client.post("/dependencias",
                    json={"pipeline_name": "PIPE_A", "depende_de": "PIPE_B"})
        db.pipelines["PIPE_A"]["dag_config_pendente"] = 0   # publicou no meio
        r = client.post("/dependencias",
                        json={"pipeline_name": "pipe_a", "depende_de": "PIPE_B"})
    assert r.json() == {"ok": True, "ja_existia": True, "dag_config_pendente": False}
    assert db.pipelines["PIPE_A"]["dag_config_pendente"] == 0


def test_delete_dependencia_liga_flag_do_dependente(client, auth_editor):
    db = FakeDb(pipelines=_pipes(), com_073=True)
    with _patch_db(db):
        client.post("/dependencias",
                    json={"pipeline_name": "PIPE_A", "depende_de": "PIPE_B"})
        db.pipelines["PIPE_A"]["dag_config_pendente"] = 0   # publicou no meio
        r = _delete(client, {"pipeline_name": "PIPE_A", "depende_de": "PIPE_B"})
    assert r.status_code == 200
    assert r.json() == {"ok": True, "dag_config_pendente": True}
    assert db.pipelines["PIPE_A"]["dag_config_pendente"] == 1
    assert db.pipelines["PIPE_B"]["dag_config_pendente"] == 0


def test_sem_073_portas_seguem_funcionando(client, auth_editor):
    """Guard da 073: sem a coluna, a escrita da dependência acontece normal e a
    flag simplesmente não existe (comportamento = hoje)."""
    db = FakeDb(pipelines=_pipes(), com_073=False)
    with _patch_db(db):
        r = client.post("/dependencias",
                        json={"pipeline_name": "PIPE_A", "depende_de": "PIPE_B"})
    assert r.status_code == 200
    assert r.json() == {"ok": True, "ja_existia": False, "dag_config_pendente": False}
    assert db.dependencias == [{"pipeline": "PIPE_A", "depende_de": "PIPE_B"}]


# ── D32: faltantes ADITIVO na visão de execução ──────────────────────────────

def test_execucao_aguardando_ganha_faltantes_do_port(client, auth_editor):
    db = FakeDb(pipelines=_pipes())
    db.dependencias = [{"pipeline": "PIPE_A", "depende_de": "PIPE_B"}]
    db.execucoes = [_exec("PIPE_A", "AGUARDANDO_DEPENDENCIA", execution_id="dep__1")]
    with _patch_db(db):
        _monta_malha(client, "M1", ["PIPE_A", "PIPE_B"])
        r = client.get("/malhas/M1/execucao?data_referencia=2026-08-01")
    assert r.status_code == 200
    execs = {e["pipeline_name"]: e for e in r.json()["execucoes"]}
    assert execs["PIPE_A"]["status"] == "AGUARDANDO_DEPENDENCIA"
    assert execs["PIPE_A"]["faltantes"] == ["PIPE_B"]


def test_execucao_nao_liberou_ganha_faltantes(client, auth_editor):
    db = FakeDb(pipelines=_pipes())
    db.dependencias = [{"pipeline": "PIPE_A", "depende_de": "PIPE_B"}]
    db.execucoes = [_exec("PIPE_A", "NAO_LIBEROU", execution_id="guardia__1",
                          motivo="fechada pela guardiã")]
    with _patch_db(db):
        _monta_malha(client, "M1", ["PIPE_A", "PIPE_B"])
        r = client.get("/malhas/M1/execucao?data_referencia=2026-08-01")
    execs = {e["pipeline_name"]: e for e in r.json()["execucoes"]}
    assert execs["PIPE_A"]["faltantes"] == ["PIPE_B"]


def test_execucao_sucesso_nao_ganha_faltantes(client, auth_editor):
    """Contrato F9 intacto: campo novo SÓ nos dois status de espera — nas
    demais linhas a resposta é a de sempre, chave a chave."""
    db = FakeDb(pipelines=_pipes())
    db.dependencias = [{"pipeline": "PIPE_A", "depende_de": "PIPE_B"}]
    db.execucoes = [_exec("PIPE_A", "SUCESSO",
                          inicio=datetime(2026, 8, 1, 6, 0))]
    with _patch_db(db):
        _monta_malha(client, "M1", ["PIPE_A", "PIPE_B"])
        r = client.get("/malhas/M1/execucao?data_referencia=2026-08-01")
    assert r.json()["execucoes"] == [{
        "pipeline_name": "PIPE_A", "status": "SUCESSO",
        "inicio": "2026-08-01 06:00:00", "fim": None,
        "disparado_por": "agenda", "motivo": None,
    }]


def test_execucao_pulado_intercalado_faltantes_vazio(client, auth_editor):
    """A linha AGUARDANDO existe, mas o predecessor JÁ tem SUCESSO na data
    (PULADO intercalado): faltantes [] — painel e motor na mesma história."""
    db = FakeDb(pipelines=_pipes())
    db.dependencias = [{"pipeline": "PIPE_A", "depende_de": "PIPE_B"}]
    db.execucoes = [
        _exec("PIPE_A", "AGUARDANDO_DEPENDENCIA", execution_id="dep__1"),
        _exec("PIPE_B", "SUCESSO", execution_id="run_06",
              inicio=datetime(2026, 8, 1, 6, 0)),
        _exec("PIPE_B", "PULADO", execution_id="run_12",
              inicio=datetime(2026, 8, 1, 12, 0)),
    ]
    with _patch_db(db):
        _monta_malha(client, "M1", ["PIPE_A", "PIPE_B"])
        r = client.get("/malhas/M1/execucao?data_referencia=2026-08-01")
    execs = {e["pipeline_name"]: e for e in r.json()["execucoes"]}
    assert execs["PIPE_A"]["faltantes"] == []
    assert execs["PIPE_B"]["status"] == "PULADO"   # exibição: o mais recente
