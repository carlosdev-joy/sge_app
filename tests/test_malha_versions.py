"""F16 leitura: identidade exata e ausência nunca substituída pelo cadastro."""
from uuid import UUID

import pytest
from fastapi import HTTPException

from services import malha_versions as service


class Cursor:
    def __init__(self, results):
        self.results = iter(results)
        self.queries = []

    def execute(self, sql, params=()):
        self.queries.append((sql, params))
        self.result = next(self.results)
        return self

    def fetchone(self):
        return self.result

    def fetchall(self):
        return self.result


def schema():
    return [(1,)] * len(service.TABLES)


def test_schema_missing_is_named_503():
    cursor = Cursor([(None,)])
    with pytest.raises(HTTPException) as error:
        service.capability(cursor, 'Malha')
    assert error.value.status_code == 503
    assert '195_malha_versionada_schema' in error.value.detail


def test_legacy_capability_never_creates_opt_in():
    cursor = Cursor(schema() + [(1,), None])
    result = service.capability(cursor, 'Malha')
    assert result['mode'] == 'legacy_unversioned'
    assert result['effective_version_id'] is None
    assert result['authoring_available'] is False
    assert result['activation_available'] is False
    assert all(q.strip().startswith('SELECT') for q, _ in cursor.queries)


def test_absent_exact_version_is_404_without_latest():
    cursor = Cursor(schema() + [None])
    with pytest.raises(HTTPException) as error:
        service.version(cursor, 'Malha', UUID(int=1))
    assert error.value.status_code == 404
    assert len(cursor.queries) == len(service.TABLES) + 1
    assert cursor.queries[-1][1] == ('Malha', str(UUID(int=1)))


def test_legacy_corrida_has_no_current_version_reconstruction():
    cursor = Cursor(schema() + [(None, None)])
    result = service.corrida(cursor, 'Malha', 10)
    assert result['mode'] == 'legacy_unversioned'
    assert result['members'] is None
    assert len(cursor.queries) == len(service.TABLES) + 1
    assert cursor.queries[-1][1] == (10, 'Malha')


def test_corrida_of_another_malha_is_404():
    cursor = Cursor(schema() + [None])
    with pytest.raises(HTTPException) as error:
        service.corrida(cursor, 'Outra', 10)
    assert error.value.status_code == 404


def version_row():
    return (UUID(int=1), 1, 1, '{"members":[]}', '{}', 'a'*64, 'b'*64, 'autor', None)


def test_version_keeps_exact_member_reference():
    cursor = Cursor(schema() + [version_row(), [('Pipe', UUID(int=2), 'c'*64)]])
    result = service.version(cursor, 'Malha', UUID(int=1))
    assert result['members'] == [{'pipeline_name': 'Pipe', 'pipeline_version_id': str(UUID(int=2)), 'content_hash': 'c'*64}]
    assert result['definition_hash'] == 'a'*64
    assert result['layout_hash'] == 'b'*64


def test_corrida_divergent_hash_fails_closed():
    cursor = Cursor(schema() + [(UUID(int=1), 'd'*64)] + schema() + [version_row(), []])
    with pytest.raises(HTTPException) as error:
        service.corrida(cursor, 'Malha', 10)
    assert error.value.status_code == 409


def test_missing_malha_capability_is_404():
    cursor = Cursor(schema() + [None])
    with pytest.raises(HTTPException) as error:
        service.capability(cursor, 'Ausente')
    assert error.value.status_code == 404


def test_routes_require_auth_before_db(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from deps import get_current_user
    from routers import malha_versions as routes

    app = FastAPI()
    app.include_router(routes.router)

    def deny():
        raise HTTPException(401, 'Não autenticado')

    def forbidden_db():
        pytest.fail('Banco acessado sem autenticação')

    app.dependency_overrides[get_current_user] = deny
    monkeypatch.setattr(routes, 'get_db_conn', forbidden_db)
    with TestClient(app) as client:
        for path in ['/malhas/M/versionamento', '/malhas/M/versoes/'+str(UUID(int=1)),
                     '/malhas/M/corridas/1/definicao']:
            assert client.get(path).status_code == 401


def test_routes_validate_uuid_and_corrida_before_db(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from deps import get_current_user
    from routers import malha_versions as routes

    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[get_current_user] = lambda: {'usuario': 'fixture'}

    def forbidden_db():
        pytest.fail('Banco acessado com identificador inválido')

    monkeypatch.setattr(routes, 'get_db_conn', forbidden_db)
    with TestClient(app) as client:
        assert client.get('/malhas/M/versoes/latest').status_code == 422
        assert client.get('/malhas/M/corridas/invalida/definicao').status_code == 422
        assert client.get('/malhas/M/corridas/9223372036854775808/definicao').status_code == 422
        assert client.get('/malhas/M/corridas/0/definicao').status_code == 422
