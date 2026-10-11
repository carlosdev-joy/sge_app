from copy import deepcopy
from uuid import uuid4

import pytest
from fastapi import HTTPException
from routers import workspace_publication as routes


@pytest.fixture
def body(monkeypatch):
    monkeypatch.setattr(routes, 'ENABLED', lambda: True)
    return {'taskId': 'file', 'nodes': [
        {'job_name': 'file', 'job_type': 'valida_arquivo', 'depends_on_jobs': []},
        {'job_name': 'target', 'job_type': 'sql', 'depends_on_jobs': ['file']},
    ], 'catalog': [{'param_name': 'DIR', 'param_type': 'Pathname', 'param_source': 'fixo', 'param_value': '/draft/new'}],
        'config': {'ssh_conn_id': 'SSH', 'timeout_segundos': 60, 'entradas': [{
            'entrada_id': str(uuid4()), 'ordem': 0, 'tipo': 'arquivo', 'arquivo': 'data.csv',
            'diretorio_literal': '', 'param_name': 'DIR', 'alvo': 'target',
            'se_nao_existe': 'pular', 'se_zero_linhas': 'executar', 'ignorar_cabecalho': False,
        }]}}


ACTOR = {'permissoes': ['tela_pipelines', 'tela_jobs']}


def test_preview_uses_local_catalog_without_database_or_remote_io(body, monkeypatch):
    import db
    monkeypatch.setattr(db, 'get_db_conn', lambda: pytest.fail('Static preview must not access database'))
    original = deepcopy(body)
    result = routes.preview_workspace_file(body, ACTOR)
    assert result['entradas'][0]['caminho'] == '/draft/new/data.csv'
    assert result['entradas'][0]['cenarios'] == {'ausente': 'pular', 'vazio': 'liberar', 'dados': 'liberar', 'erro_tecnico': 'bloquear'}
    assert body == original


@pytest.mark.parametrize('catalog', [None, [None], [{'param_type': 'Encrypted', 'param_value': 'PROTECTED'}],
    [{'param_type': 'Pathname', 'param_source': 'fixo', 'secretReference': {}}]])
def test_preview_refuses_secret_or_malformed_catalog(body, catalog):
    body['catalog'] = catalog
    with pytest.raises(HTTPException) as error:
        routes.preview_workspace_file(body, ACTOR)
    assert error.value.status_code == 422
    assert 'PROTECTED' not in str(error.value.detail)


def test_preview_refuses_cycle_and_missing_destination(body):
    body['nodes'][0]['depends_on_jobs'] = ['target']
    with pytest.raises(HTTPException) as error:
        routes.preview_workspace_file(body, ACTOR)
    assert error.value.status_code == 422
    body['nodes'][0]['depends_on_jobs'] = []
    body['config']['entradas'][0]['alvo'] = 'absent'
    with pytest.raises(HTTPException) as error:
        routes.preview_workspace_file(body, ACTOR)
    assert error.value.status_code == 422


def test_preview_requires_workspace_and_consult_permissions(body, monkeypatch):
    with pytest.raises(HTTPException) as error:
        routes.preview_workspace_file(body, {'permissoes': ['tela_pipelines']})
    assert error.value.status_code == 403
    monkeypatch.setattr(routes, 'ENABLED', lambda: False)
    with pytest.raises(HTTPException) as error:
        routes.preview_workspace_file(body, ACTOR)
    assert error.value.status_code == 503


def test_preview_refuses_invalid_unicode_and_oversize(body):
    body['extra'] = '\ud800'
    with pytest.raises(HTTPException) as error:
        routes.preview_workspace_file(body, ACTOR)
    assert error.value.status_code == 422
    body['extra'] = 'x' * 1_000_001
    with pytest.raises(HTTPException) as error:
        routes.preview_workspace_file(body, ACTOR)
    assert error.value.status_code == 422


@pytest.mark.asyncio
async def test_preview_route_enforces_auth_and_edit_permission(body):
    from fastapi import FastAPI
    import httpx
    from deps import get_current_user
    app = FastAPI()
    app.include_router(routes.router)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        response = await client.post('/workspace-adapter/valida-arquivo/preview', json=body)
        assert response.status_code == 401
        app.dependency_overrides[get_current_user] = lambda: {'permissoes': ['tela_pipelines', 'tela_jobs']}
        response = await client.post('/workspace-adapter/valida-arquivo/preview', json=body)
        assert response.status_code == 403
        app.dependency_overrides[get_current_user] = lambda: {'permissoes': ['acao_editar', 'tela_pipelines']}
        response = await client.post('/workspace-adapter/valida-arquivo/preview', json=body)
        assert response.status_code == 403
