from pathlib import Path
import subprocess


def test_specialized_forms_and_atomic_decision_graph():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(['node', 'tests/js/workspace_specialized_harness.cjs'], cwd=root, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
