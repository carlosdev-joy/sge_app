"""`{coluna:…}` na tela: seletor, prévia, avisos e catálogo (bancada local)."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]


def test_seletor_previa_e_avisos_de_coluna():
    node = shutil.which("node")
    if not node or not (RAIZ / "ui-react/node_modules/sucrase").is_dir():
        pytest.skip("front não instalado nesta máquina")
    resultado = subprocess.run(
        [node, str(RAIZ / "tests/js/email_coluna_harness.cjs")],
        capture_output=True, text=True, cwd=RAIZ, timeout=60,
    )
    assert resultado.returncode == 0, resultado.stderr
    assert json.loads(resultado.stdout)["ok"]
