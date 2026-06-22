"""
Espelhamento de ABORT do DataStage (datastage_operator.py).

Garante que, quando um job FILHO do run atual aborta (status_code=3) enquanto a
SEQUENCE (pai) ainda reporta RUNNING, o operador detecta isso para propagar o
ABORTED (em vez de ficar "RUNNING" para sempre). Também garante que um ABORT de
um run ANTIGO do -logsum não vaza (delimitação pelo último 'Starting Job') e que
um filho que abortou mas foi re-executado com sucesso não é considerado abortado.

Airflow não está instalado no ambiente de teste — os módulos necessários são
stubados antes de importar o operador.
"""
from __future__ import annotations

import logging
import sys
import types
from pathlib import Path


def _ensure_module(name: str) -> types.ModuleType:
    """Pega ou cria o módulo em sys.modules e o liga ao pai (registrar o nome
    completo evita o erro ''airflow' is not a package' quando outro teste já
    stubou um 'airflow' mínimo antes do nosso)."""
    mod = sys.modules.get(name)
    if mod is None:
        mod = types.ModuleType(name)
        sys.modules[name] = mod
        if "." in name:
            parent, _, child = name.rpartition(".")
            setattr(_ensure_module(parent), child, mod)
    return mod


def _stub_airflow():
    # Convive com os stubs de outros testes (a ordem de coleta é alfabética e
    # outro teste pode registrar 'airflow.models' como MagicMock antes do nosso).
    # Por isso FORÇAMOS os 3 símbolos que o operador precisa — BaseOperator real
    # (o operador faz subclass; um MagicMock como base quebra), AirflowException e
    # SSHHook. Sobrescrever só esses atributos é inofensivo aos outros testes, que
    # não os usam.
    _ensure_module("airflow")
    _ensure_module("airflow.exceptions").AirflowException = type(
        "AirflowException", (Exception,), {})
    _ensure_module("airflow.models").BaseOperator = type(
        "BaseOperator", (), {"__init__": lambda self, *a, **k: None})
    _ensure_module("airflow.providers")
    _ensure_module("airflow.providers.ssh")
    _ensure_module("airflow.providers.ssh.hooks")
    _ensure_module("airflow.providers.ssh.hooks.ssh").SSHHook = type("SSHHook", (), {})


_stub_airflow()

sys.path.insert(0, str(Path(__file__).parent.parent / "dags"))
from utils.datastage_operator import DataStageOperator, _abort_decision  # noqa: E402

from datetime import datetime, timedelta  # noqa: E402


def _op():
    op = DataStageOperator(project="BI_VIDA", job_name="SeqExecCargaVida")
    op.log = logging.getLogger("test-ds")
    return op


# logsum de UM run com um filho OK e um filho ABORTED (cenário do print).
LOGSUM_RUN_COM_ABORT = """
Starting Job SeqExecCargaVida.
BATCH ... -> (ControleVerificaTerminoCargaVida): Job run requested
Job ControleVerificaTerminoCargaVida has finished, status = 1 (Finished OK)
BATCH ... -> (SeqSsdVidaGeralDiario): Job run requested
Job SeqSsdVidaGeralDiario has finished, status = 3 (Aborted)
"""

# logsum com um run ANTIGO abortado seguido do run ATUAL bem-sucedido.
LOGSUM_ABORT_ANTIGO_OK_ATUAL = """
Starting Job SeqExecCargaVida.
BATCH ... -> (SeqSsdVidaGeralDiario): Job run requested
Job SeqSsdVidaGeralDiario has finished, status = 3 (Aborted)
Starting Job SeqExecCargaVida.
BATCH ... -> (SeqSsdVidaGeralDiario): Job run requested
Job SeqSsdVidaGeralDiario has finished, status = 1 (Finished OK)
"""


def test_parse_child_jobs_pega_status_por_filho():
    children = _op()._parse_child_jobs(LOGSUM_RUN_COM_ABORT)
    by_name = {c["name"]: c for c in children}
    assert by_name["ControleVerificaTerminoCargaVida"]["status_code"] == 1
    assert by_name["SeqSsdVidaGeralDiario"]["status_code"] == 3


def test_detect_aborted_children_acha_filho_abortado():
    op = _op()
    op._logsum = lambda: LOGSUM_RUN_COM_ABORT
    aborted, children, logsum = op._detect_aborted_children()
    assert aborted == ["SeqSsdVidaGeralDiario"]
    assert logsum == LOGSUM_RUN_COM_ABORT


def test_detect_ignora_abort_de_run_antigo():
    # Só o run atual conta (após o último 'Starting Job'); o run atual terminou OK.
    op = _op()
    op._logsum = lambda: LOGSUM_ABORT_ANTIGO_OK_ATUAL
    aborted, _children, _logsum = op._detect_aborted_children()
    assert aborted == []


def test_detect_sem_filho_abortado_retorna_vazio():
    op = _op()
    op._logsum = lambda: (
        "Starting Job SeqExecCargaVida.\n"
        "BATCH ... -> (InsereNumCarga): Job run requested\n"
        "Job InsereNumCarga has finished, status = 1 (Finished OK)\n"
    )
    aborted, _children, _logsum = op._detect_aborted_children()
    assert aborted == []


def test_detect_best_effort_em_erro_de_ssh():
    # Falha ao buscar -logsum não pode derrubar o polling — devolve vazio.
    op = _op()
    def _boom():
        raise RuntimeError("ssh caiu")
    op._logsum = _boom
    assert op._detect_aborted_children() == ([], [], "")


# ── carência (_abort_decision) ────────────────────────────────────────────────

NOW = datetime(2026, 6, 22, 12, 0, 0)
GRACE = 600  # 10 min


def test_decision_sem_filho_abortado_nao_propaga():
    children = [{"name": "A", "status_code": 1}, {"name": "B", "status_code": 1}]
    propagate, stuck, aborted = _abort_decision(children, None, NOW, GRACE)
    assert propagate is False and stuck is None and aborted == []


def test_decision_filho_abortado_mas_outro_rodando_nao_e_travado():
    # B ainda em execução (status_code None) → sequence progredindo → relógio zerado.
    children = [{"name": "A", "status_code": 3}, {"name": "B", "status_code": None}]
    propagate, stuck, aborted = _abort_decision(children, NOW - timedelta(hours=1), NOW, GRACE)
    assert propagate is False
    assert stuck is None            # não travado → zera o relógio
    assert aborted == ["A"]


def test_decision_travado_primeira_vez_inicia_relogio():
    # Filho abortado e todos finalizados → travado agora; inicia o relógio, não propaga.
    children = [{"name": "A", "status_code": 3}, {"name": "B", "status_code": 1}]
    propagate, stuck, aborted = _abort_decision(children, None, NOW, GRACE)
    assert propagate is False
    assert stuck == NOW
    assert aborted == ["A"]


def test_decision_travado_dentro_da_carencia_nao_propaga():
    children = [{"name": "A", "status_code": 3}, {"name": "B", "status_code": 1}]
    started = NOW - timedelta(seconds=300)   # 5 min < 10 min
    propagate, stuck, _ = _abort_decision(children, started, NOW, GRACE)
    assert propagate is False
    assert stuck == started                  # mantém o relógio


def test_decision_travado_apos_carencia_propaga():
    children = [{"name": "A", "status_code": 3}, {"name": "B", "status_code": 1}]
    started = NOW - timedelta(seconds=601)   # > 10 min
    propagate, stuck, aborted = _abort_decision(children, started, NOW, GRACE)
    assert propagate is True
    assert aborted == ["A"]
