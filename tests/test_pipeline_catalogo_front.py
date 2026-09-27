import shutil
import subprocess
from pathlib import Path
import pytest


def test_catalogo_front_roundtrip_e_conflitos():
    root = Path(__file__).resolve().parents[1]
    if not shutil.which('node') or not (root / 'ui-react/node_modules/sucrase').is_dir():
        pytest.skip('Node/sucrase indisponível')
    result = subprocess.run(['node', str(root / 'tests/js/pipeline_catalogo_harness.cjs')],
                            cwd=root, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
