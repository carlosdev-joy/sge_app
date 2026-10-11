from pathlib import Path
import subprocess

def test_catalog_preserves_protected_references_and_import_is_atomic():
 root=Path(__file__).resolve().parents[1]
 result=subprocess.run(['node','tests/js/workspace_catalog_harness.cjs'],cwd=root,capture_output=True,text=True,timeout=30)
 assert result.returncode==0,result.stdout+result.stderr
