"""Regressões do grafo de origens e marcadores de tabela, sem envio real."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]


def test_origens_diretas_e_avisos_acompanham_alteracoes_do_grafo():
    node = shutil.which("node")
    if not node or not (RAIZ / "ui-react/node_modules/sucrase").is_dir():
        pytest.skip("front não instalado nesta máquina")
    resultado = subprocess.run(
        [node, str(RAIZ / "tests/js/email_tabela_origem_harness.cjs")],
        capture_output=True, text=True, cwd=RAIZ, timeout=60,
    )
    assert resultado.returncode == 0, resultado.stderr
    assert json.loads(resultado.stdout)["ok"]
