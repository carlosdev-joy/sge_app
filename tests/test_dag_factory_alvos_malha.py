"""
Factory com LISTA de alvos (`conf["pipelines"]`) — o lote da republicação de
malha.

Até aqui a factory só sabia isolar UM alvo (`conf["pipeline_name"]`): pendência
de terceiro virava aviso e o run continuava do lado do pipeline pedido. A
republicação de uma malha pede o mesmo tratamento para N pipelines de uma vez.

O defeito que motivou isto foi visto AO VIVO no dev: a malha SMOKE_F12 foi
republicada, os três membros geraram com sucesso e o run terminou **FAILED**
porque um pipeline de fora da malha (pendente e sem etapas) entrou no lote da
sp_etl_pipelines_pendentes_criar, que é global. Na tela de Publicação, um gesto
que deu certo aparecia vermelho.

Cobrem: o parse defensivo do conf (`_nomes_do_conf`); a liberação
(dag_criada=0) de CADA alvo; o rótulo de escopo no log; pendência de terceiro
como AVISO com o run em SUCCESS; e alvo que não entrou no lote como ERRO
nomeado (o silêncio de "0 geradas" continua proibido).

Mesma infra dos vizinhos (test_dag_factory_pendente_publicacao.py): Airflow
stubado via sys.modules e gerar_dags completo com hook/cursor falsos.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

_AIRFLOW_STUBS = [
    "airflow", "airflow.models", "airflow.operators", "airflow.operators.python",
    "airflow.operators.empty", "airflow.datasets", "airflow.utils",
    "airflow.utils.trigger_rule", "airflow.utils.state",
    "airflow.providers", "airflow.providers.microsoft", "airflow.providers.microsoft.mssql",
    "airflow.providers.microsoft.mssql.hooks", "airflow.providers.microsoft.mssql.hooks.mssql",
    "pendulum", "requests", "httpx",
]
for _mod in _AIRFLOW_STUBS:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

_ROOT = Path(__file__).parent.parent
_MOMENTO_LOTE = datetime(2026, 8, 4, 9, 0, 0)


@pytest.fixture(scope="module")
def factory():
    path = _ROOT / "dags/etl_dag_factory.py"
    spec = importlib.util.spec_from_file_location(
        "etl_dag_factory_alvos_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_PIPE_COLS = ["pipeline_name", "project_name", "domain", "tags", "scheduled_time",
              "envia_msg_inicio", "envia_msg_fim", "envia_msg_erro"]
_JOB_COLS = ["pipeline_name", "job_name", "job_type", "job_command", "execution_order"]
_ADV_COLS = ["pipeline_name", "criticidade", "sla_minutos", "ambiente",
             "max_active_runs", "retries_count", "retry_delay_seconds",
             "pool_name", "descricao", "dag_start_date", "runbook_md"]


def _pipe(nome):
    return (nome, "BI_CVP", "T", "ETL", "06:00:00", 0, 0, 1)


def _job(pipe):
    return (pipe, "JobA", "datastage", "ds.job", 1)


class _FakeCursor:
    """Guarda (sql, params) de cada execute — é assim que se prova QUEM foi
    liberado para regeneração."""

    def __init__(self, pipe_rows, job_rows):
        self._pipe_rows, self._job_rows = pipe_rows, job_rows
        self.chamadas: list[tuple] = []
        self._sets = []
        self.description = None
        self._rows = []

    def execute(self, sql, params=None):
        s = " ".join(str(sql).split())
        self.chamadas.append((s, params))
        if "SELECT GETDATE()" in s:
            self._sets, self.description, self._rows = [], [("d",)], [(_MOMENTO_LOTE,)]
        elif "sp_etl_pipelines_pendentes_criar" in s:
            self._sets = [(_PIPE_COLS, self._pipe_rows), (_JOB_COLS, self._job_rows)]
            self._pop_set()
        elif "INFORMATION_SCHEMA.COLUMNS" in s:
            self._sets, self.description, self._rows = [], [("c",)], [(0,)]
        elif "FROM dbo.etl_pipeline WHERE pipeline_name IN" in s:
            self._sets, self.description, self._rows = [], [(c,) for c in _ADV_COLS], []
        else:
            self._sets, self.description, self._rows = [], None, []

    def _pop_set(self):
        cols, rows = self._sets.pop(0)
        self.description = [(c,) for c in cols]
        self._rows = list(rows)

    def fetchall(self):
        rows, self._rows = self._rows, []
        return rows

    def fetchone(self):
        return self._rows[0] if self._rows else (0,)

    def nextset(self):
        if self._sets:
            self._pop_set()
            return True
        return False

    def close(self):
        pass


class _FakeHook:
    def __init__(self, cursor):
        self._cursor = cursor
        self.runs = []

    def get_conn(self):
        cur = self._cursor
        return SimpleNamespace(cursor=lambda: cur, commit=lambda: None,
                               close=lambda: None)

    def run(self, sql, parameters=None, **_kw):
        self.runs.append((" ".join(str(sql).split()), parameters))


def _rodar(factory, monkeypatch, tmp_path, pipes, jobs, conf):
    cur = _FakeCursor(pipes, jobs)
    hook = _FakeHook(cur)
    monkeypatch.setattr(factory, "MsSqlHook", lambda **_kw: hook)
    monkeypatch.setattr(factory, "_get_output_root", lambda: str(tmp_path))
    ctx = {"dag_run": SimpleNamespace(conf=conf, run_id="alvos_test_run")}
    erro = None
    try:
        factory.gerar_dags(**ctx)
    except Exception as e:      # noqa: BLE001 — o teste inspeciona o desfecho
        erro = e
    return hook, cur, erro


def _log_final(hook):
    """Último MERGE em etl_factory_log: (estado, geradas, erros, detalhes)."""
    merges = [(s, p) for s, p in hook.runs if "etl_factory_log" in s]
    _, params = merges[-1]
    # A cauda do MERGE é o INSERT: (run_id, estado, escopo, pipeline_name,
    # geradas, erros, detalhes_json)
    run_id, estado, escopo, _pname, geradas, erros, detalhes = params[-7:]
    return {"estado": estado, "escopo": escopo, "geradas": geradas,
            "erros": erros, "detalhes": json.loads(detalhes)}


def _liberados(cur):
    return [p[0] for s, p in cur.chamadas
            if s.startswith("UPDATE dbo.etl_pipeline SET dag_criada=0")]


# ── parse do conf ───────────────────────────────────────────────────────────

def test_nomes_do_conf_normaliza(factory):
    f = factory._nomes_do_conf
    assert f(None) == []
    assert f([]) == []
    assert f("PIPE_A") == ["PIPE_A"]                    # string solta
    assert f(["  PIPE_A  ", "PIPE_B"]) == ["PIPE_A", "PIPE_B"]
    assert f(["PIPE_A", 7, None, {"x": 1}]) == ["PIPE_A"]   # lixo descartado
    # dedup case-insensitive: a colação do banco é CI — cobrar duas vezes o
    # mesmo pipeline inventaria um "não entrou no lote" que não existe
    assert f(["PIPE_A", "pipe_a", "PIPE_B"]) == ["PIPE_A", "PIPE_B"]
    assert f(["", "   "]) == []


# ── liberação + escopo ──────────────────────────────────────────────────────

def test_libera_cada_alvo_e_rotula_o_escopo(factory, monkeypatch, tmp_path):
    hook, cur, erro = _rodar(
        factory, monkeypatch, tmp_path,
        pipes=[_pipe("PIPE_A"), _pipe("PIPE_B")],
        jobs=[_job("PIPE_A"), _job("PIPE_B")],
        conf={"pipelines": ["PIPE_A", "PIPE_B"], "escopo_rotulo": "Malha M1"})
    assert erro is None
    assert _liberados(cur) == ["PIPE_A", "PIPE_B"]
    log = _log_final(hook)
    assert log["estado"] == "SUCCESS" and log["geradas"] == 2
    assert log["escopo"] == "Malha M1 (2 pipeline(s))"


def test_escopo_sem_rotulo_ainda_diz_quantos(factory, monkeypatch, tmp_path):
    hook, _cur, erro = _rodar(
        factory, monkeypatch, tmp_path,
        pipes=[_pipe("PIPE_A")], jobs=[_job("PIPE_A")],
        conf={"pipelines": ["PIPE_A"]})
    assert erro is None
    assert _log_final(hook)["escopo"] == "Pipelines selecionados (1 pipeline(s))"


# ── isolamento de terceiros (o defeito visto no dev) ────────────────────────

def test_terceiro_quebrado_nao_reprova_o_run_da_malha(factory, monkeypatch, tmp_path):
    """PIPE_FORA está pendente e não tem etapas — entra no lote da SP (que é
    global) e falharia. Como não é alvo, vira AVISO: o run da malha fecha
    SUCCESS, com os alvos gerados."""
    hook, _cur, erro = _rodar(
        factory, monkeypatch, tmp_path,
        pipes=[_pipe("PIPE_A"), _pipe("PIPE_FORA")],
        jobs=[_job("PIPE_A")],                       # PIPE_FORA sem nenhum job
        conf={"pipelines": ["PIPE_A"], "escopo_rotulo": "Malha M1"})
    assert erro is None, "erro de terceiro não pode derrubar a task"
    log = _log_final(hook)
    assert log["estado"] == "SUCCESS"
    assert log["geradas"] == 1 and log["erros"] == 0
    avisos = [s for s in log["detalhes"]["steps"] if s["tipo"] == "aviso"]
    assert any("PIPE_FORA" in a["msg"] and "outro pipeline" in a["msg"]
               for a in avisos)


def test_membro_quebrado_continua_reprovando(factory, monkeypatch, tmp_path):
    """O isolamento vale só para terceiros: defeito de um MEMBRO é erro de
    primeira classe — o operador precisa ver vermelho no que é dele."""
    _hook, _cur, erro = _rodar(
        factory, monkeypatch, tmp_path,
        pipes=[_pipe("PIPE_A"), _pipe("PIPE_B")],
        jobs=[_job("PIPE_A")],                       # PIPE_B (alvo) sem job
        conf={"pipelines": ["PIPE_A", "PIPE_B"], "escopo_rotulo": "Malha M1"})
    assert erro is not None
    assert "PIPE_B" in str(erro)


def test_alvo_fora_do_lote_e_erro_nomeado(factory, monkeypatch, tmp_path):
    """Membro inativado/excluído entre o clique e a execução: a SP não o
    devolve. Sem esta cobrança o run fecharia verde sem uma linha sobre ele."""
    hook, _cur, erro = _rodar(
        factory, monkeypatch, tmp_path,
        pipes=[_pipe("PIPE_A")], jobs=[_job("PIPE_A")],
        conf={"pipelines": ["PIPE_A", "PIPE_SUMIU"], "escopo_rotulo": "Malha M1"})
    assert erro is not None and "PIPE_SUMIU" in str(erro)
    log = _log_final(hook)
    assert log["estado"] == "FAILED"
    assert log["geradas"] == 1          # o membro saudável foi gerado assim mesmo
    assert any("PIPE_SUMIU" in e for e in log["detalhes"]["erros"])


# ── compatibilidade: pipeline_name segue funcionando ────────────────────────

def test_pipeline_name_continua_isolando_terceiro(factory, monkeypatch, tmp_path):
    hook, cur, erro = _rodar(
        factory, monkeypatch, tmp_path,
        pipes=[_pipe("PIPE_A"), _pipe("PIPE_FORA")],
        jobs=[_job("PIPE_A")],
        conf={"pipeline_name": "PIPE_A"})
    assert erro is None
    assert _liberados(cur) == ["PIPE_A"]
    log = _log_final(hook)
    assert log["estado"] == "SUCCESS"
    assert log["escopo"] == "Pipeline específico: PIPE_A"
