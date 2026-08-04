"""
Reconciliador em MODO VERIFICAÇÃO (migration 080) — a conferência que a
republicação de malha deixa agendada.

Republicar uma malha gera N DAGs num run só e quem zera o carimbo de publicação
pendente é a própria factory. Faltava alguém CONFERIR o desfecho: um arquivo
com erro de CARGA (NameError, import quebrado — a classe do GOTCHA "consts
antes dos helpers") faz o Airflow manter a versão ANTERIOR ativa, e sem
conferência a tela anunciaria "publicado e em dia" com a DAG velha rodando —
o pior desfecho, porque é silencioso.

O item em modo verificação:
  • não notifica sucesso (seriam N avisos por clique) e não mexe no carimbo
    (quem publicou foi a factory — limpar aqui apagaria carimbo de edição que
    a geração já não incluiu);
  • notifica ERRO e REACENDE o carimbo quando a DAG não é importável;
  • só é avaliado DEPOIS que o run da factory fecha: perguntar antes
    responderia sobre a DAG que está sendo substituída.

Cobrem esses três pontos + a degradação sem a 080 (o enqueue recusa em vez de
gravar um pendente comum, que limparia o carimbo antes da hora).
"""
from __future__ import annotations

import sys
from datetime import datetime
from unittest.mock import MagicMock

import pytest

if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()

import services.dag_reconcile as dr


_INICIO = datetime(2026, 8, 4, 10, 0, 0)


class _Cur:
    """Cursor de log com estado mínimo: carimbos por pipeline, presença da
    coluna da 080 e o estado do run da factory."""

    def __init__(self, estado):
        self.e = estado
        self._ultimo = None

    def execute(self, sql, params=()):
        s = " ".join(str(sql).split())
        params = tuple(params)
        self.e["log"].append((s, params))
        self._ultimo = None
        if "COL_LENGTH('dbo.etl_dag_pendente', 'modo_verificacao')" in s:
            self._ultimo = (8,) if self.e.get("com_080", True) else (None,)
        elif s.startswith("SELECT estado FROM dbo.etl_factory_log"):
            estado_run = self.e.get("estado_run")
            self._ultimo = (estado_run,) if estado_run else None
        elif s.startswith("UPDATE dbo.etl_pipeline SET dag_config_pendente_em = NULL"):
            nome, inicio = params
            atual = self.e["carimbos"].get(nome)
            if atual is not None and atual <= inicio:
                self.e["carimbos"][nome] = None
        elif s.startswith("UPDATE dbo.etl_pipeline SET dag_config_pendente_em = GETDATE()"):
            nome = params[0]
            if self.e["carimbos"].get(nome) is None:
                self.e["carimbos"][nome] = "reaceso"

    def fetchone(self):
        return self._ultimo

    def close(self):
        pass


class _Conn:
    def __init__(self, estado):
        self.e = estado

    def cursor(self):
        return _Cur(self.e)

    def commit(self):
        pass

    def close(self):
        pass


@pytest.fixture
def estado(monkeypatch):
    e = {"log": [], "carimbos": {"PIPE_A": None}, "com_080": True,
         "estado_run": "SUCCESS", "notificacoes": []}
    monkeypatch.setattr(dr, "get_db_conn", lambda: _Conn(e))
    monkeypatch.setattr(dr, "add_notificacao",
                        lambda mat, titulo, msg, sev, url: e["notificacoes"].append(
                            (titulo, sev)))
    return e


def _row(**kw):
    base = {"id": 1, "pipeline_name": "PIPE_A", "matricula": "OPER1",
            "desired_paused": False, "idade_s": 5,
            "dag_run_id": "orquestra_malha_1", "criado_em": _INICIO,
            "modo_verificacao": True}
    base.update(kw)
    return base


# ── sucesso silencioso, carimbo intocado ────────────────────────────────────

def test_verificacao_ok_nao_notifica_nem_mexe_no_carimbo(estado):
    estado["carimbos"]["PIPE_A"] = datetime(2026, 8, 4, 9, 50, 0)
    dr._finalize(_row(), found=True, import_trace=None)
    assert estado["notificacoes"] == []
    # o clear é da factory: o carimbo dessa edição continua de pé aqui
    assert not any("dag_config_pendente_em = NULL" in s for s, _ in estado["log"])
    assert estado["carimbos"]["PIPE_A"] == datetime(2026, 8, 4, 9, 50, 0)


def test_publicacao_normal_continua_notificando_e_limpando(estado):
    """A verificação não pode mudar o fluxo do 'Publicar nova versão'."""
    estado["carimbos"]["PIPE_A"] = datetime(2026, 8, 4, 9, 50, 0)
    dr._finalize(_row(modo_verificacao=False), found=True, import_trace=None)
    assert [t for t, _ in estado["notificacoes"]] == ["DAG de PIPE_A pronta no Airflow"]
    assert estado["carimbos"]["PIPE_A"] is None


# ── erro de importação: o desfecho que a verificação existe para pegar ──────

def test_import_error_notifica_e_reacende_o_carimbo(estado):
    """A publicação NÃO valeu: o Airflow segue com a versão anterior. Sem
    reacender, o chip 'republicar' sumiria e ninguém saberia."""
    estado["carimbos"]["PIPE_A"] = None          # a factory já tinha limpado
    dr._finalize(_row(), found=True, import_trace="NameError: xpto")
    assert estado["notificacoes"] == [
        ("DAG de PIPE_A com erro de importação", "error")]
    assert estado["carimbos"]["PIPE_A"] == "reaceso"


def test_import_error_no_fluxo_normal_nao_reacende(estado):
    """No 'Publicar nova versão' ninguém limpou o carimbo — reacender ali
    seria escrever por cima de um estado que já está correto."""
    estado["carimbos"]["PIPE_A"] = None
    dr._finalize(_row(modo_verificacao=False), found=True,
                 import_trace="NameError: xpto")
    assert not any("dag_config_pendente_em = GETDATE()" in s
                   for s, _ in estado["log"])


# ── a espera pelo run da factory ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_espera_o_run_da_factory_fechar(estado):
    """Com o run em RUNNING, o item é adiado: consultar agora responderia
    sobre a DAG que está sendo substituída."""
    estado["estado_run"] = "RUNNING"
    client = MagicMock()
    client.get = MagicMock(side_effect=AssertionError("não pode consultar o Airflow ainda"))
    await dr._process_one(client, _row())
    assert any(s.startswith("UPDATE dbo.etl_dag_pendente SET tentativas=tentativas+1")
               for s, _ in estado["log"])


@pytest.mark.asyncio
async def test_run_travado_nao_espera_para_sempre(estado):
    """Passado o tempo limite, o item resolve mesmo com o run em RUNNING —
    senão um run travado seguraria a fila indefinidamente."""
    estado["estado_run"] = "RUNNING"

    class _Resp:
        status_code = 200
        is_success = True

        @staticmethod
        def json():
            return {"is_paused": False}

    class _Client:
        async def get(self, url, **kw):
            if "importErrors" in url:
                return _Resp2()
            return _Resp()

    class _Resp2:
        status_code = 200
        is_success = True

        @staticmethod
        def json():
            return {"import_errors": []}

    await dr._process_one(_Client(), _row(idade_s=dr.PENDENTE_TIMEOUT_S + 1))
    assert any(s.startswith("UPDATE dbo.etl_dag_pendente SET status=?")
               for s, _ in estado["log"])


# ── degradação sem a migration 080 ──────────────────────────────────────────

def test_sem_080_o_enqueue_recusa_a_verificacao(estado):
    """Gravar um pendente COMUM no lugar limparia o carimbo antes da hora e
    notificaria N vezes por clique — melhor não enfileirar e dizer no log."""
    estado["com_080"] = False
    assert dr.enqueue("PIPE_A", False, "OPER1", "run1", True) is False
    assert not any(s.startswith("INSERT INTO dbo.etl_dag_pendente")
                   for s, _ in estado["log"])


def test_sem_080_a_ativacao_normal_continua(estado):
    estado["com_080"] = False
    assert dr.enqueue("PIPE_A", False, "OPER1", "run1") is True
    inserts = [s for s, _ in estado["log"]
               if s.startswith("INSERT INTO dbo.etl_dag_pendente")]
    assert len(inserts) == 1
    assert "modo_verificacao" not in inserts[0]


def test_com_080_grava_a_coluna(estado):
    assert dr.enqueue("PIPE_A", False, "OPER1", "run1", True) is True
    inserts = [(s, p) for s, p in estado["log"]
               if s.startswith("INSERT INTO dbo.etl_dag_pendente")]
    assert len(inserts) == 1
    assert "modo_verificacao" in inserts[0][0]
    assert inserts[0][1][-1] == 1
