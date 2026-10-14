"""Contrato API do opt-in de erro Teams, sem alterações em nós de E-mail."""
import pytest


@pytest.mark.parametrize('policy', ['continuar', 'falhar'])
def test_policy_roundtrip(policy):
    from routers.jobs import _validate_notify, _normalize_notify
    cfg = {'grupo_id': 7, 'template_id': None, 'mensagem': 'fixture', 'on_error': policy}
    assert _validate_notify(cfg) == []
    assert _normalize_notify(cfg) == cfg


def test_legacy_config_preserved():
    from routers.jobs import _validate_notify, _normalize_notify
    cfg = {'grupo_id': 7, 'template_id': None, 'mensagem': 'fixture'}
    assert _validate_notify(cfg) == []
    assert _normalize_notify(cfg) == cfg


@pytest.mark.parametrize('policy', [None, True, 1, '', 'ignore', [], {}])
def test_invalid_policy_rejected(policy):
    from routers.jobs import _validate_notify
    assert any('on_error' in error for error in
               _validate_notify({'grupo_id': 7, 'on_error': policy}))
