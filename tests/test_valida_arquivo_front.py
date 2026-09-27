import json
import subprocess
from pathlib import Path


def test_publicacao_rename_ordem_e_grafo_do_canvas():
    root = Path(__file__).resolve().parents[1]
    r = subprocess.run(['node', 'tests/js/valida_arquivo_harness.cjs'], cwd=root,
                       text=True, capture_output=True, timeout=60)
    assert r.returncode == 0, r.stderr
    assert all(json.loads(r.stdout).values())
