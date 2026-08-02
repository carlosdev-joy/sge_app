"""
F6 — geração com SUCESSO zera a pendência de publicação (dag_config_pendente_em).

Pendência registrada no desenho da F5 §7.2: quem zera o carimbo é o
reconciliador da API ao concluir a publicação via UI — um `force_all`
administrativo por fora da API regenerava a DAG mas deixava o badge
"publicação pendente" mentindo até a próxima publicação. A F6 ensina o
factory a zerar, com três guardas testadas aqui:

  1. só zera quando a geração do pipeline CONCLUIU com sucesso (arquivo
     gravado + dag_criada=1) — upsert que falha não zera nada;
  2. só apaga carimbos <= momento do lote (relógio do PRÓPRIO banco, via
     SELECT GETDATE() antes da SP): mudança de cadastro feita DURANTE a
     geração continua pendente — mesma régua do dag_reconcile;
  3. degradação supplement-style: sem a migration 073 o guard COL_LENGTH no
     próprio SQL vira no-op, e QUALQUER falha na limpeza é print, nunca
     reprova uma geração que deu certo.

Mesma infra dos vizinhos (test_dag_factory_grafia.py): Airflow stubado via
sys.modules, gerar_dags completo com hook/cursor falsos devolvendo os result
sets da SP.
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

# Sentinela do relógio do banco: é o valor que o UPDATE tem que carregar.
_MOMENTO_LOTE = datetime(2026, 8, 2, 12, 0, 0)


@pytest.fixture(scope="module")
def factory():
    path = _ROOT / "dags/etl_dag_factory.py"
    spec = importlib.util.spec_from_file_location(
        "etl_dag_factory_pendente_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_PIPE_COLS = ["pipeline_name", "project_name", "domain", "tags", "scheduled_time",
              "envia_msg_inicio", "envia_msg_fim", "envia_msg_erro"]
_JOB_COLS = ["pipeline_name", "job_name", "job_type", "job_command", "execution_order"]
_ADV_COLS = ["pipeline_name", "criticidade", "sla_minutos", "ambiente",
             "max_active_runs", "retries_count", "retry_delay_seconds",
             "pool_name", "descricao", "dag_start_date", "runbook_md"]

_PIPE_ROW = ("PIPE_PEND", "BI_CVP", "T", "ETL", "06:00:00", 0, 0, 1)
_JOB_ROW = ("PIPE_PEND", "JobA", "datastage", "ds.job", 1)


class _FakeCursor:
    def __init__(self, pipe_rows, job_rows, getdate_falha=False):
        self._pipe_rows, self._job_rows = pipe_rows, job_rows
        self._getdate_falha = getdate_falha
        self.sqls = []
        self._sets = []
        self.description = None
        self._rows = []

    def execute(self, sql, params=None):
        s = " ".join(str(sql).split())
        self.sqls.append(s)
        if "SELECT GETDATE()" in s:
            if self._getdate_falha:
                raise RuntimeError("sem relogio")
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
    """`falha_em`: substring de SQL cuja chamada de hook.run deve explodir —
    é como se provam as duas degradações (upsert × limpeza)."""

    def __init__(self, cursor, falha_em=None):
        self._cursor = cursor
        self._falha_em = falha_em
        self.runs = []

    def get_conn(self):
        cur = self._cursor
        return SimpleNamespace(cursor=lambda: cur, commit=lambda: None,
                               close=lambda: None)

    def run(self, sql, parameters=None, **_kw):
        s = " ".join(str(sql).split())
        if self._falha_em and self._falha_em in s:
            raise RuntimeError(f"falha comandada em: {self._falha_em}")
        self.runs.append((s, parameters))


def _rodar(factory, monkeypatch, tmp_path, falha_em=None, getdate_falha=False,
           conf=None):
    cur = _FakeCursor([_PIPE_ROW], [_JOB_ROW], getdate_falha=getdate_falha)
    hook = _FakeHook(cur, falha_em=falha_em)
    monkeypatch.setattr(factory, "MsSqlHook", lambda **_kw: hook)
    monkeypatch.setattr(factory, "_get_output_root", lambda: str(tmp_path))
    ctx = {"dag_run": SimpleNamespace(conf=conf or {}, run_id="pendente_test_run")}
    factory.gerar_dags(**ctx)
    return hook


def _updates_pendente(hook):
    return [(s, p) for s, p in hook.runs if "dag_config_pendente_em" in s]


def _ultimo_log(hook):
    merges = [(s, p) for s, p in hook.runs if "etl_factory_log" in s]
    _, params = merges[-1]
    return params[1], json.loads(params[5])


# ── 1. geração com sucesso zera o carimbo, com as duas guardas no SQL ────────

def test_sucesso_zera_pendencia_com_guard_e_momento(factory, monkeypatch, tmp_path):
    hook = _rodar(factory, monkeypatch, tmp_path)
    estado, detalhes = _ultimo_log(hook)
    assert estado == "SUCCESS" and detalhes["erros"] == []

    ups = _updates_pendente(hook)
    assert len(ups) == 1, "exatamente um UPDATE de pendência por pipeline gerado"
    sql, params = ups[0]
    # guard de coluna no próprio SQL: sem a 073 o statement é no-op
    assert "IF COL_LENGTH('dbo.etl_pipeline','dag_config_pendente_em') IS NOT NULL" in sql
    # só apaga carimbo <= momento do lote (régua do dag_reconcile)
    assert "dag_config_pendente_em <= %s" in sql
    assert params == ("PIPE_PEND", _MOMENTO_LOTE)

    # a limpeza vem DEPOIS do upsert que confirma a geração no cadastro
    idx_upsert = next(i for i, (s, _) in enumerate(hook.runs)
                      if "sp_etl_pipeline_upsert" in s)
    idx_limpa = next(i for i, (s, _) in enumerate(hook.runs)
                     if "dag_config_pendente_em" in s)
    assert idx_limpa > idx_upsert


# ── 2. upsert que falha NÃO zera (geração não concluiu com sucesso) ──────────

def test_upsert_falho_nao_zera_pendencia(factory, monkeypatch, tmp_path):
    cur = _FakeCursor([_PIPE_ROW], [_JOB_ROW])
    hook = _FakeHook(cur, falha_em="sp_etl_pipeline_upsert")
    monkeypatch.setattr(factory, "MsSqlHook", lambda **_kw: hook)
    monkeypatch.setattr(factory, "_get_output_root", lambda: str(tmp_path))
    ctx = {"dag_run": SimpleNamespace(conf={}, run_id="pendente_test_run2")}
    with pytest.raises(factory._ErrosPorPipeline):
        factory.gerar_dags(**ctx)
    assert _updates_pendente(hook) == []
    estado, detalhes = _ultimo_log(hook)
    assert estado == "FAILED"
    assert any("erro ao atualizar banco" in e for e in detalhes["erros"])


# ── 3. falha na LIMPEZA nunca reprova a geração (supplement-style) ───────────

def test_falha_na_limpeza_degrada_com_print(factory, monkeypatch, tmp_path, capsys):
    hook = _rodar(factory, monkeypatch, tmp_path,
                  falha_em="dag_config_pendente_em")
    estado, detalhes = _ultimo_log(hook)
    assert estado == "SUCCESS" and detalhes["erros"] == []
    assert "dag_config_pendente_em nao zerado" in capsys.readouterr().out


# ── 4. sem carimbo do lote não se zera nada (defensivo, nunca esconder) ──────

def test_sem_carimbo_do_lote_nao_zera(factory, monkeypatch, tmp_path, capsys):
    hook = _rodar(factory, monkeypatch, tmp_path, getdate_falha=True)
    estado, detalhes = _ultimo_log(hook)
    assert estado == "SUCCESS" and detalhes["erros"] == []
    assert _updates_pendente(hook) == []
    assert "carimbo do lote indisponivel" in capsys.readouterr().out


# ── 5. fluxo da UI (aguardar_ativacao): quem zera é o RECONCILIADOR ─────────

def test_fluxo_da_ui_nao_zera_a_pendencia(factory, monkeypatch, tmp_path):
    """Achado da revisão da F6: no fluxo Gerar DAG da UI, import error e
    TIMEOUT deliberadamente NÃO limpam a pendência ("pendência escondida não é
    recuperável") — o factory zerar aqui anularia o gating do reconciliador.
    Com aguardar_ativacao no conf, o factory NÃO toca no carimbo."""
    hook = _rodar(factory, monkeypatch, tmp_path,
                  conf={"pipeline_name": "PIPE_PEND", "aguardar_ativacao": True})
    estado, detalhes = _ultimo_log(hook)
    assert estado in ("SUCCESS", "GERADA") and detalhes["erros"] == []
    assert _updates_pendente(hook) == [], \
        "no fluxo da UI o clear é exclusivo do reconciliador"
