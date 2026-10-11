"""UX profissional do Pipeline — F4.2 (inspector em subseções e desfazer/refazer local).

Duas bancadas com código real de ui-react/src:
- workspace_history_harness.cjs: módulos puros (patches diferenciais, histórico de
  50 passos, mescla por campo, segredos, atalhos), sem React.
- workspace_ux_contexto_harness.cjs, seções 14 e 15: WorkspaceEditor + NodeProperties
  com os formulários reais dos 11 tipos (minireact) e a guarda de saída real com
  alterações só no inspector. Foco real, CSS, React Flow
  e o efeito de troca de sessão de login ficam para o navegador.
"""
import json
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@lru_cache(maxsize=None)
def _executar(bancada):
    result = subprocess.run(["node", f"tests/js/{bancada}"], cwd=ROOT, capture_output=True, text=True, timeout=120)
    return result.returncode, result.stdout, result.stderr


def _run(bancada):
    if not shutil.which("node") or not (ROOT / "ui-react/node_modules/sucrase").is_dir():
        pytest.skip("Node/sucrase indisponível")
    code, stdout, stderr = _executar(bancada)
    assert code == 0, stderr[-3000:]
    return json.loads(stdout.strip().splitlines()[-1])


def _puro():
    return _run("workspace_history_harness.cjs")


def _editor():
    return _run("workspace_ux_contexto_harness.cjs")


def test_patches_roundtrip_every_eligible_operation_exactly():
    assert _puro()["patches"] == 13


def test_history_keeps_50_steps_ignores_noop_and_invalidates_redo():
    assert _puro()["historico"] == {"limite": 50, "noOp": 0, "redoInvalidado": True, "conflito": "recusado"}


def test_drag_gesture_and_typing_are_grouped():
    assert _puro()["gestos"] == {"arraste": 1, "multisselecao": 3, "digitacao": 1, "pausa": 2}


def test_protected_values_never_enter_history():
    assert _puro()["segredos"] == {"novaReferencia": "reinicia", "valorAberto": "fora", "valorAbertoAntes": 7, "remocaoLocal": "desfaz"}


def test_protected_value_in_previous_state_never_enters_history():
    """Mascarar, remover parâmetro/etapa ou editar outra coisa com valor aberto no antes (sentinela sintética) reinicia o histórico."""
    assert _puro()["segredos"]["valorAbertoAntes"] == 7


def test_inspector_merge_writes_only_changed_fields_and_refuses_conflicts():
    assert _puro()["mescla"] == {"outroCampo": "mantido", "clone": "aplica", "conflitos": 3, "ramos": "remapeados", "duplicada": "recusada", "ciclo": "recusado"}


def test_history_memory_is_bounded_with_300_nodes():
    assert _puro()["memoria"] == {"etapas": 300, "passos": 50, "menorQueUmQuintoDeUmaCopia": True}


def test_shortcuts_respect_text_fields_dialogs_and_inactive_view():
    assert _puro()["atalhos"] == {"desfazer": 2, "refazer": 2, "ignorados": 8}


def test_last_undo_redo_returns_focus_without_stealing_it():
    """Último passo: o botão desabilitado devolve o foco ao oposto (ou ao canvas); campo, diálogo e vista oculta ficam como estão."""
    assert _puro()["focoHistorico"] == {"restaurados": 6, "preservados": 7}


def test_diagnostic_focus_targets_known_field_or_first_editable_without_stealing():
    """Chave conhecida vai ao controle (SQL: Conexão MSSQL, não o Nome somente leitura); desconhecida, ao primeiro editável; consulta fica na subseção; foco movido, oculto ou diálogo encerram."""
    assert _puro()["focoDiagnostico"] == {"alvos": 9, "permitidos": 3, "preservados": 4}


def test_inspector_shows_real_forms_for_11_types_inline_with_preserved_staging():
    assert _editor()["inspector"] == {"tipos": 11, "semJson": True, "semModal": True, "staging": ["subsecao", "recolher", "configuracao", "salvar"], "mesclaAposSave": True, "trocaConfirma": True}


def test_specialized_apply_merges_only_the_step():
    assert _editor()["especializado"] == {"mescla": "so-etapa", "slaPosterior": "mantido", "arraste": "mantido", "desfazer": "so-aplicacao"}


def test_editor_undo_redo_is_local_and_guarded():
    assert _editor()["historicoEditor"] == {"desfazer": True, "refazer": True, "redoInvalidado": True, "arraste": 1, "atalhos": ["campo", "dialogo", "oculta"], "servidor": 0}


def test_focus_mode_uses_the_same_area_without_modal():
    assert _editor()["modoFocado"] == {"canvasConservado": True, "mesmoFormulario": True, "esc": True, "semModal": True}


def test_diagnostic_opens_matching_section_without_json():
    assert _editor()["diagnostico"] == {"configuracao": True, "lineage": True, "desconhecido": "configuracao", "semJson": True}


def test_protected_value_applies_reference_and_resets_history():
    assert _editor()["segredoEditor"] == {"referencia": True, "historicoReiniciado": True, "emClaro": False, "jsonProtegido": "recusado"}


def test_without_lease_apply_and_undo_are_unavailable():
    resultado = _editor()
    assert resultado["semPosse"] == {"aplicar": "recusado", "desfazer": "indisponivel", "formulario": "conservado"}
    assert resultado["leituraF42"] is True


def test_leaving_session_with_unapplied_inspector_changes_asks_and_cancel_keeps():
    assert _editor()["saidaComStaging"] == {"experiencia": "confirma", "definicao": "confirma", "voltar": "confirma", "cancelar": "conserva", "mesmaSessao": "sem diálogo", "salvar": "desabilitado", "recarregar": "confirma+descarta", "descartar": "confirma", "estadosSeparados": True}
