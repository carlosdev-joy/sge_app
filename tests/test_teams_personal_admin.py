from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from deps import get_current_user
from routers import teams_personal as r
from services import teams_config


@pytest.mark.parametrize('method', ['get', 'post'])
def test_non_admin_cannot_read_or_write(monkeypatch, method):
    app = FastAPI()
    app.include_router(r.router)
    app.dependency_overrides[get_current_user] = lambda: {
        'matricula': 'fixture-consulta', 'permissoes': [], 'perfil': 'consulta'}
    monkeypatch.setattr(r, 'get_db_conn', lambda: pytest.fail('database forbidden'))
    client = TestClient(app)
    response = (client.get('/teams-personal/admin/config') if method == 'get'
                else client.post('/teams-personal/admin/config', json={}))
    assert response.status_code == 403


def test_invalid_input_before_database(monkeypatch):
    monkeypatch.setattr(r, 'get_db_conn', lambda: pytest.fail('database forbidden'))
    with pytest.raises(r.HTTPException) as exc:
        r._operation({'client_secret': 'synthetic'}, 'fixture-admin')
    assert exc.value.status_code == 422
    assert exc.value.detail == 'invalid_configuration'


def test_database_error_sanitized():
    from unittest.mock import patch
    with patch.object(r, 'get_db_conn', side_effect=RuntimeError('synthetic-private-db')):
        with pytest.raises(r.HTTPException) as exc:
            r._operation()
    assert exc.value.status_code == 503
    assert exc.value.detail == 'teams_configuration_unavailable'


def test_resources_closed_when_read_fails(monkeypatch):
    from unittest.mock import MagicMock
    conn = MagicMock()
    monkeypatch.setattr(r, 'get_db_conn', lambda: conn)
    monkeypatch.setattr(teams_config, 'load', lambda cur: (_ for _ in ()).throw(
        teams_config.ConfigurationError('configuration_unreadable')))
    with pytest.raises(r.HTTPException):
        r._operation()
    conn.close.assert_called_once()
    conn.cursor.return_value.close.assert_called_once()
    conn.commit.assert_not_called()


def test_post_response_actor_commit_without_reread(monkeypatch):
    from unittest.mock import MagicMock
    from tests.test_teams_config import body
    conn = MagicMock()
    monkeypatch.setattr(r, 'get_db_conn', lambda: conn)
    saved = MagicMock()
    monkeypatch.setattr(teams_config, 'save', saved)
    monkeypatch.setattr(teams_config, 'load', lambda cur: pytest.fail('no reread after commit'))
    result = r._operation(body(), 'fixture-session-actor')
    assert result['delivery_enabled'] is False
    saved.assert_called_once_with(conn.cursor.return_value, body(), 'fixture-session-actor')
    conn.commit.assert_called_once()


@pytest.mark.parametrize('path', ['reference', 'lookup'])
def test_non_admin_cannot_bind_or_lookup(monkeypatch, path):
    app = FastAPI()
    app.include_router(r.router)
    app.dependency_overrides[get_current_user] = lambda: {
        'matricula': 'fixture-consulta', 'permissoes': [], 'perfil': 'consulta'}
    monkeypatch.setattr(r, 'get_db_conn', lambda: pytest.fail('database forbidden'))
    assert TestClient(app).post('/teams-personal/admin/' + path, json={}).status_code == 403


def test_lookup_unconfigured_no_network(monkeypatch):
    from unittest.mock import MagicMock
    conn = MagicMock()
    monkeypatch.setattr(r, 'get_db_conn', lambda: conn)
    monkeypatch.setattr(teams_config, 'load', lambda cur: None)
    with pytest.raises(r.HTTPException) as exc:
        r._binding_operation({'email': 'fixture@example.test'}, 'fixture-admin', lookup=True)
    assert exc.value.detail == 'administrative_readiness_required'
    conn.commit.assert_not_called()
    conn.close.assert_called_once()


def test_reference_post_session_actor_no_reread(monkeypatch):
    from unittest.mock import MagicMock
    from tests.test_teams_config import body
    from tests.test_teams_binding import reference
    conn = MagicMock()
    monkeypatch.setattr(r, 'get_db_conn', lambda: conn)
    monkeypatch.setattr(teams_config, 'load', lambda cur: body())
    saved = MagicMock(return_value=MagicMock(fingerprint='synthetic-fingerprint'))
    monkeypatch.setattr(r.teams_binding, 'save', saved)
    result = r.reference_save(reference(), {'matricula': 'fixture-session-admin'})
    assert result == {'reference_configured': True, 'target_fingerprint': 'synthetic-fingerprint',
                      'delivery_enabled': False}
    assert saved.call_args.args[-1] == 'fixture-session-admin'
    conn.commit.assert_called_once()
    conn.close.assert_called_once()


@pytest.mark.parametrize('bound', [True, False])
def test_lookup_resolution_binding_without_send(monkeypatch, bound):
    from unittest.mock import MagicMock
    from tests.test_teams_config import body
    conn = MagicMock()
    cfg = body()
    cfg.update(admin_approved=True, permissions_verified=True, gateway_verified=True)
    monkeypatch.setattr(r, 'get_db_conn', lambda: conn)
    monkeypatch.setattr(teams_config, 'load', lambda cur: cfg)
    gateway = object()
    monkeypatch.setattr(teams_config, 'directory', lambda value: gateway)
    target = MagicMock(fingerprint='fixture-fingerprint')
    monkeypatch.setattr(r, 'resolve', lambda config, g, email: (target, None))
    provider = MagicMock() if bound else None
    monkeypatch.setattr(r.teams_binding, 'provider', lambda *args: provider)
    result = r._binding_operation({'email': 'fixture@example.test'}, 'fixture-admin', lookup=True)
    assert result['readiness'] == ('ready' if bound else 'connector_reference_missing')
    assert result['delivery_enabled'] is False
    if provider:
        provider.assert_not_called()
    conn.commit.assert_not_called()
