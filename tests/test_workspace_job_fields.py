from pathlib import Path
import subprocess


def test_draft_form_preserves_unknown_fields_and_protected_references():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(['node', 'tests/js/workspace_job_fields_harness.cjs'], cwd=root, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
