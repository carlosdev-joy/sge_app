"""
Testes do DataStageOperator (espelho puro do DataStage).

- Mantém a cobertura do parser de jobs filhos (_parse_child_jobs), usado no
  _finish para registrar os filhos de uma SEQUENCE no log final.
- Garante que o refactor "espelho puro" removeu a manipulação do DataStage: o
  operador não tem mais RESET/retry nem a heurística de filho abortado — ele só
  reflete o status real do job (running→running, aborted→FAILED, warning→warning).

Airflow não está instalado no ambiente de teste — stubamos o mínimo necessário
antes de importar o operador.
"""
from __future__ import annotations

import logging
import sys
import types
from pathlib import Path


def _ensure_module(name: str) -> types.ModuleType:
    """Pega ou cria o módulo em sys.modules e o liga ao pai (evita o erro
    ''airflow' is not a package' quando outro teste já stubou um 'airflow' mínimo)."""
    mod = sys.modules.get(name)
    if mod is None:
        mod = types.ModuleType(name)
        sys.modules[name] = mod
        if "." in name:
            parent, _, child = name.rpartition(".")
            setattr(_ensure_module(parent), child, mod)
    return mod


def _stub_airflow():
    # BaseOperator real (o operador faz subclass), AirflowException e SSHHook.
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
from utils.datastage_operator import DataStageOperator  # noqa: E402


def _op():
    op = DataStageOperator(project="BI_VIDA", job_name="SeqExecCargaVida")
    op.log = logging.getLogger("test-ds")
    return op


# logsum de UM run com um filho OK e um filho ABORTED.
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


def test_parse_child_jobs_so_considera_run_atual():
    # Só o run atual conta (após o último 'Starting Job'); o run atual terminou OK.
    children = _op()._parse_child_jobs(LOGSUM_ABORT_ANTIGO_OK_ATUAL)
    by_name = {c["name"]: c for c in children}
    assert by_name["SeqSsdVidaGeralDiario"]["status_code"] == 1


def test_espelho_puro_sem_manipulacao_do_datastage():
    """O refactor removeu RESET/retry e a heurística de filho abortado: o operador
    apenas espelha o status, sem manipular o job no DataStage."""
    op = _op()
    for attr in ("_reset", "_reset_job", "_detect_aborted_children",
                 "_badstate_children", "max_ds_retries", "mirror_child_abort"):
        assert not hasattr(op, attr), f"esperado que '{attr}' tivesse sido removido"
    import utils.datastage_operator as mod
    assert not hasattr(mod, "_abort_decision")
