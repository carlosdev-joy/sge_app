"""Parser de linhas do `dsjob -report DETAIL` (DataStageOperator._parse_output_rows).

Trava o formato server clássico REAL do ambiente (Stage/Link, "N rows"), que o
parser antigo (só "Output ... Rows = N") não casava — por isso o {linhas} da
notificação vinha vazio.

Airflow é stubado via sys.modules; BaseOperator vira classe REAL porque o
operador a subclasseia (MagicMock não é base válida).
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

_STUBS = [
    "airflow", "airflow.exceptions", "airflow.models",
    "airflow.providers", "airflow.providers.ssh", "airflow.providers.ssh.hooks",
    "airflow.providers.ssh.hooks.ssh",
    "airflow.providers.microsoft", "airflow.providers.microsoft.mssql",
    "airflow.providers.microsoft.mssql.hooks", "airflow.providers.microsoft.mssql.hooks.mssql",
]
for _m in _STUBS:
    sys.modules.setdefault(_m, MagicMock())
# BaseOperator é subclasseada pelo operador → precisa ser uma classe de verdade.
sys.modules["airflow.models"].BaseOperator = type(
    "BaseOperator", (), {"__init__": lambda self, *a, **k: None})
sys.modules["airflow.exceptions"].AirflowException = type("AirflowException", (Exception,), {})

_ROOT = Path(__file__).parent.parent
_spec = importlib.util.spec_from_file_location(
    "datastage_operator_rows_test", _ROOT / "dags/utils/datastage_operator.py")
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
_Op = _mod.DataStageOperator


def _parse(report):
    # _parse_output_rows usa só self._ROWS_OUT_PATTERNS (atributo de classe).
    obj = types.SimpleNamespace(_ROWS_OUT_PATTERNS=_Op._ROWS_OUT_PATTERNS)
    return _Op._parse_output_rows(obj, report)


# Saída crua REAL do relatório do usuário (BI_CVP / BiCvp_Assistencia_00_ext_mkt_cloud).
REAL_REPORT = """********************************************************
STATUS REPORT FOR JOB: BiCvp_Assistencia_00_ext_mkt_cloud
Generated: 2026-06-24 17:14:16
Job start time=2026-06-24 17:09:27
Job end time=2026-06-24 17:10:44
Job elapsed time=00:01:17
Job status=1 (Finished OK)
Stage: EXT_SEGURADOS_VGAP, 6866540 rows input
Stage start time=2026-06-24 17:09:27, end time=2026-06-24 17:10:44, elapsed=00:01:17
Link: LnkSegurados_VGAP, 6866540 rows
Status code = 0
"""


def test_parse_formato_real_server():
    # stage 6866540 + link 6866540 → MÁXIMO 6866540 (somar daria 13M, errado).
    assert _parse(REAL_REPORT) == 6866540


def test_parse_milhar_com_virgula():
    assert _parse("Link: LnkX, 1,234,567 rows") == 1234567


def test_parse_multiplos_links_usa_maximo():
    rep = "Link: A, 100 rows\nLink: B, 5000 rows\nStage: S, 5000 rows output\n"
    assert _parse(rep) == 5000


def test_parse_sem_contagem_retorna_none():
    # SEQUENCE / relatório sem stage/link → None (cai no fallback dos filhos).
    assert _parse("STATUS REPORT FOR JOB: SEQ_X\nJob status=1 (Finished OK)\n") is None
    assert _parse("") is None


def test_parse_layout_alternativo_output_rows():
    # Layouts de outras versões ainda casam.
    assert _parse("Output Link 'L': Rows = 4321") == 4321
