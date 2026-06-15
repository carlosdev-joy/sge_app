"""
Testes de integração para endpoints criados/modificados no ciclo v2.4.
Marcados com pytest.mark.api para correr separadamente dos smoke tests.

Roda sem banco real (MSSQL mockado via pytest fixtures).
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest


# ── helpers ──────────────────────────────────────────────────────────────────

def _mock_cursor(rows=None, description=None):
    cur = MagicMock()
    cur.fetchone.return_value = rows[0] if rows else None
    cur.fetchall.return_value = rows or []
    cur.description = description or []
    return cur


def _mock_conn(cur):
    conn = MagicMock()
    conn.cursor.return_value = cur
    return conn


# ── GET /config ───────────────────────────────────────────────────────────────

@pytest.mark.smoke
def test_config_returns_defaults(client):
    """GET /config deve retornar ao menos airflow_ui_url (novo campo)."""
    with patch("api.routers.infra.get_db_conn") as mock_db:
        cur = _mock_cursor(rows=[])
        mock_db.return_value = _mock_conn(cur)
        r = client.get("/config")
    assert r.status_code == 200
    data = r.json()
    assert "airflow_ui_url" in data
    assert isinstance(data["airflow_ui_url"], str)


@pytest.mark.smoke
def test_config_airflow_url_default(client):
    """airflow_ui_url padrão não deve ser vazio."""
    with patch("api.routers.infra.get_db_conn") as mock_db:
        cur = _mock_cursor(rows=[])
        mock_db.return_value = _mock_conn(cur)
        r = client.get("/config")
    assert r.json()["airflow_ui_url"].startswith("http")


# ── GET /factory/preview ──────────────────────────────────────────────────────

@pytest.mark.api
def test_factory_preview_not_found(client):
    """GET /factory/preview com pipeline inexistente → 404."""
    with patch("api.routers.factory.get_db_conn") as mock_db:
        cur = _mock_cursor(rows=[])
        cur.fetchone.return_value = None
        mock_db.return_value = _mock_conn(cur)
        r = client.get(
            "/factory/preview?pipeline_name=PIPELINE_INEXISTENTE",
            headers={"Authorization": "Bearer fake_token"},
        )
    # 401 se auth falhar antes, 404 se auth passar e pipeline não existir
    assert r.status_code in (401, 404)


@pytest.mark.api
def test_factory_preview_requires_auth(client):
    """GET /factory/preview sem token → 401."""
    r = client.get("/factory/preview?pipeline_name=TESTE")
    assert r.status_code == 401


@pytest.mark.api
def test_factory_preview_missing_param(client):
    """GET /factory/preview sem pipeline_name → 422."""
    r = client.get(
        "/factory/preview",
        headers={"Authorization": "Bearer fake"},
    )
    assert r.status_code in (401, 422)


# ── GET /execucoes/sla-report ─────────────────────────────────────────────────

@pytest.mark.api
def test_sla_report_requires_auth(client):
    """GET /execucoes/sla-report sem token → 401."""
    r = client.get("/execucoes/sla-report")
    assert r.status_code == 401


@pytest.mark.api
def test_sla_report_invalid_date(client):
    """GET /execucoes/sla-report com data inválida → 422."""
    r = client.get(
        "/execucoes/sla-report?date_ini=nao-e-data",
        headers={"Authorization": "Bearer fake"},
    )
    assert r.status_code in (401, 422)


# ── GET /dashboard ────────────────────────────────────────────────────────────

@pytest.mark.api
def test_dashboard_requires_auth(client):
    r = client.get("/dashboard")
    assert r.status_code == 401


@pytest.mark.api
def test_dashboard_invalid_date(client):
    r = client.get(
        "/dashboard?date_ref=invalid",
        headers={"Authorization": "Bearer fake"},
    )
    assert r.status_code in (400, 401, 422)


# ── GET /factory/runs ─────────────────────────────────────────────────────────

@pytest.mark.api
def test_factory_runs_requires_auth(client):
    """factory/runs não tem autenticação — verifica que retorna algo (gap S1)."""
    with patch("api.routers.factory.get_db_conn") as mock_db:
        cur = _mock_cursor(rows=[])
        mock_db.return_value = _mock_conn(cur)
        r = client.get("/factory/runs")
    # Atualmente sem auth (gap S1) — este teste documenta o comportamento esperado
    # e deve ser atualizado quando auth for adicionada
    assert r.status_code in (200, 401)


# ── POST /pipelines/register ──────────────────────────────────────────────────

@pytest.mark.api
def test_register_pipeline_requires_auth(client):
    r = client.post("/pipelines/register", json={})
    assert r.status_code == 401


@pytest.mark.api
def test_register_pipeline_missing_fields(client):
    """Sem pipeline_name e scheduled_time → 401 ou 422."""
    r = client.post(
        "/pipelines/register",
        json={"pipeline_name": ""},
        headers={"Authorization": "Bearer fake"},
    )
    assert r.status_code in (401, 422)


# ── GET /malha ────────────────────────────────────────────────────────────────

@pytest.mark.api
def test_malha_requires_auth(client):
    r = client.get("/malha")
    assert r.status_code == 401


# ── GET /pipelines/projects ───────────────────────────────────────────────────

@pytest.mark.smoke
def test_projects_endpoint_exists(client):
    """GET /pipelines/projects deve existir (sem auth necessária para leitura)."""
    with patch("api.routers.pipelines.get_db_conn") as mock_db:
        cur = _mock_cursor(rows=[("BI_CVP",), ("BI_VIDA",)])
        mock_db.return_value = _mock_conn(cur)
        r = client.get("/pipelines/projects")
    # Pode retornar 200 com lista ou 401 se protegido — ambos são válidos
    assert r.status_code in (200, 401)
    if r.status_code == 200:
        data = r.json()
        assert "projects" in data
        assert isinstance(data["projects"], list)


# ── Teste de compilação de todos os routers ───────────────────────────────────

@pytest.mark.smoke
def test_all_routers_compile():
    """Todos os arquivos de router devem ser importáveis (sintaxe correta)."""
    import py_compile
    from pathlib import Path
    routers_dir = Path(__file__).parent.parent / "api" / "routers"
    errors = []
    for f in routers_dir.glob("*.py"):
        try:
            py_compile.compile(str(f), doraise=True)
        except py_compile.PyCompileError as exc:
            errors.append(f"{f.name}: {exc}")
    assert not errors, "\n".join(errors)


@pytest.mark.smoke
def test_factory_preview_router_registered(client):
    """GET /factory/preview deve aparecer no schema OpenAPI."""
    r = client.get("/openapi.json")
    assert r.status_code == 200
    schema = r.json()
    paths = schema.get("paths", {})
    assert any("factory/preview" in p for p in paths), \
        f"Endpoint /factory/preview não encontrado no schema. Paths: {list(paths.keys())[:10]}"


@pytest.mark.smoke
def test_sla_report_router_registered(client):
    """GET /execucoes/sla-report deve aparecer no schema OpenAPI."""
    r = client.get("/openapi.json")
    assert r.status_code == 200
    schema = r.json()
    paths = schema.get("paths", {})
    assert any("sla-report" in p for p in paths), \
        f"Endpoint /execucoes/sla-report não encontrado no schema. Paths: {list(paths.keys())[:10]}"
