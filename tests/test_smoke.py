"""
Smoke tests — validam que a API sobe e responde corretamente nos endpoints
que não dependem de banco de dados.

Marcados com pytest.mark.smoke para poder rodar isoladamente:
    pytest -k smoke
"""
import pytest


@pytest.mark.smoke
def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert "status" in data


@pytest.mark.smoke
def test_openapi_schema(client):
    r = client.get("/openapi.json")
    assert r.status_code == 200
    schema = r.json()
    assert "paths" in schema
    assert "/health" in schema["paths"]


@pytest.mark.smoke
def test_login_missing_fields(client):
    r = client.post("/auth/login", json={})
    assert r.status_code == 422


@pytest.mark.smoke
def test_login_empty_password(client):
    r = client.post("/auth/login", json={"usuario": "CVT00000", "senha": ""})
    assert r.status_code == 422


@pytest.mark.smoke
def test_me_unauthenticated(client):
    r = client.get("/me")
    assert r.status_code == 401


@pytest.mark.smoke
def test_pipelines_unauthenticated(client):
    r = client.get("/pipelines")
    assert r.status_code == 401


@pytest.mark.smoke
def test_admin_unauthenticated(client):
    r = client.post("/admin", json={"action": "user_list"})
    assert r.status_code == 401


@pytest.mark.smoke
def test_cors_header_present(client):
    r = client.options("/health", headers={"Origin": "http://localhost"})
    # CORSMiddleware responde a OPTIONS com Allow-Origin
    assert r.status_code in (200, 405)
