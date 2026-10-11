"""UX profissional do Pipeline — primeira entrega (cinco destinos e sessão contínua).

A bancada JS executa o código real de ui-react/src (sucrase + minireact):
aliases antigos, sessão entre destinos, cabeçalho da Execução, o
WorkspaceEditor alternando Montagem → Configuração → Execução → Montagem, a
investigação da Execução (etapa/tentativa da corrida exibida), o Modal inerte
em área oculta, o escopo de overlay composto (aba E grupo da Configuração) e a
guarda de navegação contra um History simulado. Foco, CSS,
overlays no DOM e o BrowserRouter real ficam para o QA em navegador.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _run():
    if not shutil.which("node") or not (ROOT / "ui-react/node_modules/sucrase").is_dir():
        pytest.skip("Node/sucrase indisponível")
    result = subprocess.run(["node", "tests/js/workspace_ux_contexto_harness.cjs"], cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_editor_session_survives_tabs_with_one_lease_and_same_fence():
    out = _run()
    assert out["passed"] is True
    assert out["sessao"] == {"posses": 1, "saves": 1, "fence": 41, "abas": ["montagem", "configuracao", "execucao", "montagem"]}
    assert out["leitura"] is True


def test_legacy_routes_are_all_aliased():
    assert _run()["aliases"] == 6


def test_execution_investigation_opens_only_attempts_of_the_shown_run():
    # F5: a investigação passou ao inspector operacional; detalhes em test_workspace_ux_execucao.
    out = _run()["execucao"]
    assert out["logTexto"] is True and out["outraCorrida"] is False and out["graficos"] == 1


def test_hidden_area_modal_stays_mounted_without_dialog_role():
    assert _run()["modalOculto"] is True


def test_configuration_overlay_scope_is_per_group_and_never_reactivates_hidden_tab():
    assert _run()["overlayGrupo"] == {"voltar": "inerte", "porGrupo": True, "abaOculta": "inerte", "herdadoInativo": "inerte", "reativa": "conservado", "posses": 1}


def test_navigation_guard_reverts_back_forward_until_confirmed():
    assert _run()["guarda"] == {"voltarSessao": "sem diálogo", "voltarSaida": "desfeito+confirmado", "cancelar": "conserva", "clique": True, "programatica": True}
