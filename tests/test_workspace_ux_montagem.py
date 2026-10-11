"""UX profissional do Pipeline — F4.1 (área útil do canvas, painéis e barra de publicação).

Roda a mesma bancada da entrega 1 (código real de ui-react/src, sucrase +
minireact). Aqui ficam os aceites da F4.1: moldura por rota, painéis recolhíveis
que conservam o trabalho, barra Salvar/Validar/Publicar com uma única instância de
publicação e seus gates, diagnóstico recolhível e fonte da Execução. Foco real,
CSS computado, zoom do React Flow e o portal no DOM ficam para o navegador.
"""
import json
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@lru_cache(maxsize=1)
def _executar():
    result = subprocess.run(["node", "tests/js/workspace_ux_contexto_harness.cjs"], cwd=ROOT, capture_output=True, text=True, timeout=60)
    return result.returncode, result.stdout, result.stderr


def _run():
    if not shutil.which("node") or not (ROOT / "ui-react/node_modules/sucrase").is_dir():
        pytest.skip("Node/sucrase indisponível")
    code, stdout, stderr = _executar()
    assert code == 0, stderr
    return json.loads(stdout.strip().splitlines()[-1])


def test_collapsing_panels_keeps_selection_view_search_and_unapplied_form():
    assert _run()["paineis"] == {"alternadores": 2, "conservado": ["selecao", "zoom", "busca", "staging"], "posses": 1, "saves": 1, "naoAplicado": True}


def test_header_bar_reuses_single_publication_instance_with_gates():
    assert _run()["publicacao"] == {
        "barra": ["Validar rascunho", "Publicar versão"], "instancias": 1, "validacoes": 3, "publicacoes": 1,
        "revisao": 8, "fence": 41, "diagnosticoAbreInspector": True, "semPermissao": "sem Publicar",
    }


def test_execution_names_its_source_and_never_the_draft():
    assert _run()["fonteExecucao"] is True
