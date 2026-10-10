from pathlib import Path
import re
import shutil
import subprocess
import pytest
ROOT = Path(__file__).resolve().parents[1]
def test_dialogs_confirmation_queue_and_live_guards():
    if not shutil.which('node') or not (ROOT/'ui-react/node_modules/sucrase').is_dir():
        pytest.skip('Node/sucrase indisponível')
    result = subprocess.run(['node','tests/js/application_dialogs_harness.cjs'],cwd=ROOT,capture_output=True,text=True,timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr

def test_application_sources_do_not_reintroduce_browser_dialogs():
    forbidden = re.compile(r'\b(?:window\s*\.\s*)?(?:alert|confirm|prompt)\s*\(')
    found = []
    for source in (ROOT/'ui-react/src').rglob('*'):
        if source.suffix in ('.ts','.tsx'):
            # Calls only: domain descriptions of model prompts are unrelated.
            for number,line in enumerate(source.read_text().splitlines(),1):
                if forbidden.search(line) and not line.lstrip().startswith(('//','*','/*')):
                    found.append(f'{source.relative_to(ROOT)}:{number}')
    assert not found, found
