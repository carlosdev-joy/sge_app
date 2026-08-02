"""
Testes do fechamento do registro da factory (dbo.etl_factory_log).

Motivação: quando a task `gerar_dags` morria por uma exceção fora dos try/except
por-pipeline (conexão com o banco, a SP de pendentes, criação do diretório de
saída…), o registro ficava em RUNNING para sempre. Do lado do operador isso
aparece do pior jeito possível: a tela de Publicação não mostra causa nenhuma,
o arquivo não aparece no servidor, e o reconciliador só desiste 15 minutos
depois com um TIMEOUT que não explica nada.

O wrapper `gerar_dags_task` fecha o registro como FAILED, com a causa, antes de
deixar o erro subir.
"""
from __future__ import annotations

import importlib.util
import sys
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
    "pendulum", "requests",
]
for _mod in _AIRFLOW_STUBS:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

_ROOT = Path(__file__).parent.parent


@pytest.fixture(scope="module")
def factory():
    path = _ROOT / "dags/etl_dag_factory.py"
    spec = importlib.util.spec_from_file_location("etl_dag_factory_logfecha_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _ctx(**conf):
    return {"dag_run": SimpleNamespace(conf=conf, run_id="orquestra_ui_123")}


# ── O wrapper fecha o log quando a task morre no meio ────────────────────────

def test_excecao_inesperada_fecha_o_log(factory, monkeypatch):
    """O caso que produzia o RUNNING órfão: erro antes de qualquer geração."""
    chamadas = []
    monkeypatch.setattr(factory, "_fechar_log_em_falha",
                        lambda *a: chamadas.append(a))

    def _boom(**_kw):
        raise RuntimeError("conexão recusada pelo SQL Server")
    monkeypatch.setattr(factory, "gerar_dags", _boom)

    with pytest.raises(RuntimeError, match="conexão recusada"):
        factory.gerar_dags_task(**_ctx(pipeline_name="PIPE_X"))

    assert len(chamadas) == 1, "o log precisa ser fechado exatamente uma vez"
    run_id, escopo, pname, exc = chamadas[0]
    assert run_id == "orquestra_ui_123"
    assert pname == "PIPE_X"
    assert "PIPE_X" in escopo
    assert isinstance(exc, RuntimeError)


def test_erro_original_continua_subindo(factory, monkeypatch):
    """A task tem que ficar VERMELHA no Airflow — fechar o log não engole o erro."""
    monkeypatch.setattr(factory, "_fechar_log_em_falha", lambda *a: None)
    monkeypatch.setattr(factory, "gerar_dags",
                        MagicMock(side_effect=OSError("disco cheio")))
    with pytest.raises(OSError, match="disco cheio"):
        factory.gerar_dags_task(**_ctx())


def test_erros_por_pipeline_nao_sobrescrevem_o_detalhe(factory, monkeypatch):
    """gerar_dags já fechou o log com a lista de CADA pipeline que falhou —
    o wrapper não pode reescrever isso com uma mensagem genérica."""
    chamadas = []
    monkeypatch.setattr(factory, "_fechar_log_em_falha",
                        lambda *a: chamadas.append(a))
    monkeypatch.setattr(factory, "gerar_dags", MagicMock(
        side_effect=factory._ErrosPorPipeline("2 pipeline(s) com erro:\nA: x\nB: y")))

    with pytest.raises(factory._ErrosPorPipeline):
        factory.gerar_dags_task(**_ctx())
    assert chamadas == [], "o detalhe por pipeline seria perdido"


def test_sucesso_nao_fecha_como_falha(factory, monkeypatch):
    chamadas = []
    monkeypatch.setattr(factory, "_fechar_log_em_falha",
                        lambda *a: chamadas.append(a))
    monkeypatch.setattr(factory, "gerar_dags", MagicMock(return_value=None))
    factory.gerar_dags_task(**_ctx())
    assert chamadas == []


def test_fechar_log_e_best_effort(factory, monkeypatch):
    """Se nem o fechamento conseguir gravar, quem tem que chegar ao Airflow é o
    erro ORIGINAL — não um erro secundário do log."""
    monkeypatch.setattr(factory, "MsSqlHook",
                        MagicMock(side_effect=RuntimeError("banco fora")))
    # não levanta
    factory._fechar_log_em_falha("run_1", "escopo", "PIPE", ValueError("causa real"))


# ── Escopo (usado quando gerar_dags morre antes de montar o próprio) ─────────

def test_escopo_pipeline_especifico(factory):
    assert factory._escopo_de({"pipeline_name": "PIPE_A"}) == "Pipeline específico: PIPE_A"


def test_escopo_force_all_com_projeto(factory):
    esc = factory._escopo_de({"force_all": True, "filter_project": "BI_CVP"})
    assert "BI_CVP" in esc and "forçada" in esc


def test_escopo_force_all(factory):
    assert factory._escopo_de({"force_all": True}) == "Todos os pipelines (regeneração forçada)"


def test_escopo_default(factory):
    assert factory._escopo_de({}) == "Apenas pipelines pendentes de criação"


def test_escopo_tolera_conf_vazio(factory):
    """conf pode vir sem as chaves — o escopo não pode explodir justamente no
    caminho de tratamento de erro."""
    for conf in ({}, {"pipeline_name": ""}, {"force_all": False}, {"filter_project": ""}):
        assert isinstance(factory._escopo_de(conf), str)


def test_wrapper_tolera_dag_run_sem_conf(factory, monkeypatch):
    """DagRun sem conf (disparo manual pelo Airflow) não pode quebrar o
    tratamento de erro."""
    monkeypatch.setattr(factory, "_fechar_log_em_falha", lambda *a: None)
    monkeypatch.setattr(factory, "gerar_dags", MagicMock(side_effect=RuntimeError("x")))
    ctx = {"dag_run": SimpleNamespace(conf=None, run_id="r1")}
    with pytest.raises(RuntimeError):
        factory.gerar_dags_task(**ctx)


# ── A task da DAG usa o wrapper (e não o gerar_dags direto) ──────────────────

def test_task_usa_o_wrapper(factory):
    """Guarda contra alguém religar o callable antigo numa refatoração."""
    src = (_ROOT / "dags/etl_dag_factory.py").read_text(encoding="utf-8")
    assert "python_callable=gerar_dags_task," in src
    assert "python_callable=gerar_dags," not in src
