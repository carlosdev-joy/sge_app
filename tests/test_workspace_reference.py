from pathlib import Path
import subprocess

def test_workspace_reference_branch_layout_preserves_join_and_source():
 root=Path(__file__).resolve().parents[1]
 result=subprocess.run(['node','tests/js/workspace_reference_harness.cjs'],cwd=root,capture_output=True,text=True,timeout=30)
 assert result.returncode==0,result.stdout+result.stderr
