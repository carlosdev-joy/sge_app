"""F8: contrato puro do formulário e consulta de capabilities sem edição."""
import subprocess
from pathlib import Path
import pytest
from unittest.mock import MagicMock
from fastapi import HTTPException


def test_notification_form_contract():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(['node', 'tests/js/workspace_alerts_harness.cjs'], cwd=root, text=True, capture_output=True, timeout=30)
    assert result.returncode == 0, result.stderr


def test_capabilities_consultation_without_admin_or_edit(monkeypatch):
    from routers import workspace_publication as route
    monkeypatch.setattr(route, 'ENABLED', lambda: True)
    result = route.workspace_alerts_capabilities({'permissoes': ['tela_pipelines', 'tela_jobs']})
    assert set(result) == {'result', 'email', 'teamsPersonal', 'teamsChannel'}
    assert all(not cap['available'] and cap['cause'] for cap in result.values())
    with pytest.raises(HTTPException) as denied:
        route.workspace_alerts_capabilities({'permissoes': ['editar']})
    assert denied.value.status_code == 403
    monkeypatch.setattr(route, 'ENABLED', lambda: False)
    with pytest.raises(HTTPException) as disabled:
        route.workspace_alerts_capabilities({'permissoes': ['tela_pipelines', 'tela_jobs']})
    assert disabled.value.status_code == 503


@pytest.mark.parametrize('upper', [False, True])
def test_known_notification_flags_match_physical_sql_names_without_accepting_unknown(upper):
    from services.workspace_publication import columns, sql_notification_fields, NOTIFICATION_FLAGS
    physical = [key.upper() if upper else key for key in NOTIFICATION_FLAGS]
    cursor = MagicMock()
    cursor.execute.return_value.fetchall.return_value = [(key,) for key in physical] + [('pipeline_name',)]
    assert columns(cursor, 'etl_pipeline') == NOTIFICATION_FLAGS | {'pipeline_name'}
    supplied = {key: False for key in NOTIFICATION_FLAGS}
    supplied['pipeline_name'] = 'FIXTURE'
    mapped = sql_notification_fields(cursor, 'etl_pipeline', supplied)
    assert set(mapped) == set(physical) | {'pipeline_name'}
    assert all(mapped[key] is False for key in physical)
    assert 'notify_on_failure' not in columns(cursor, 'etl_pipeline')


def test_uppercase_snapshot_is_preserved_and_conflicting_aliases_are_rejected():
    from services.workspace_publication import materialize, PublicationBlocked
    original = {'schemaVersion': 1, 'identity': {'pipelineName': 'FIXTURE'}, 'nodes': [], 'edges': [], 'metadata': {'legacyPipeline': {'ENVIA_MSG_ERRO': False, 'future_field': {'keep': True}}}}
    projection = materialize(original, {'nodes': {}}, {})
    assert projection['etl_pipeline'][0]['envia_msg_erro'] is False
    assert original['metadata']['legacyPipeline']['ENVIA_MSG_ERRO'] is False
    assert projection['etl_pipeline'][0]['future_field'] == {'keep': True}
    original['metadata']['legacyPipeline']['envia_msg_erro'] = True
    with pytest.raises(PublicationBlocked, match='conflitantes'):
        materialize(original, {'nodes': {}}, {})
