"""
Testes para a validação de dias_horarios_mes (schedule_type 'monthly_days_times').
Função pura — não depende de banco de dados.
"""
from __future__ import annotations

import json
import os
import sys
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

# api/main.py precisa ser importado antes de qualquer import direto de um
# router individual (ex: routers.pipelines): devido ao "pythonpath=api" do
# pytest.ini, importar um router isolado primeiro inicializa a árvore de
# routers fora da ordem que api.main usa, corrompendo o app real para o
# resto da sessão de testes (outros testes passam a receber 500). Replica
# o mock de pyodbc do conftest.py para garantir que esse import funcione
# mesmo se este arquivo for coletado antes do conftest configurar o ambiente.
if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()
os.environ.setdefault("MSSQL_CONN_STR", "__mock__")
from api.main import app as _app  # noqa: F401

from deps import get_current_user, PERM_EDITAR
from routers.pipelines import _validate_dias_horarios_mes


def test_none_returns_none():
    assert _validate_dias_horarios_mes(None) is None


def test_empty_string_returns_none():
    assert _validate_dias_horarios_mes("") is None
    assert _validate_dias_horarios_mes("   ") is None


def test_valid_single_day_single_time():
    raw = '[{"dia": 1, "horarios": ["09:00"]}]'
    assert _validate_dias_horarios_mes(raw) == '[{"dia": 1, "horarios": ["09:00"]}]'


def test_valid_multiple_days_normalizes_order():
    raw = ('[{"dia": 28, "horarios": ["10:00"]}, {"dia": 1, "horarios": ["9:0"]}, '
           '{"dia": 15, "horarios": ["18:00", "14:00"]}]')
    result = _validate_dias_horarios_mes(raw)
    assert result == (
        '[{"dia": 1, "horarios": ["09:00"]}, '
        '{"dia": 15, "horarios": ["14:00", "18:00"]}, '
        '{"dia": 28, "horarios": ["10:00"]}]'
    )


def test_max_5_days_5_horarios_accepted():
    dias = [{"dia": d, "horarios": [f"{h:02d}:00" for h in range(5)]} for d in [1, 5, 10, 15, 20]]
    assert _validate_dias_horarios_mes(json.dumps(dias)) is not None


def test_invalid_json_raises_422():
    with pytest.raises(HTTPException) as exc:
        _validate_dias_horarios_mes("not json")
    assert exc.value.status_code == 422


def test_day_zero_raises_422():
    with pytest.raises(HTTPException) as exc:
        _validate_dias_horarios_mes('[{"dia": 0, "horarios": ["09:00"]}]')
    assert exc.value.status_code == 422


def test_day_29_raises_422():
    with pytest.raises(HTTPException) as exc:
        _validate_dias_horarios_mes('[{"dia": 29, "horarios": ["09:00"]}]')
    assert exc.value.status_code == 422


def test_duplicate_day_raises_422():
    with pytest.raises(HTTPException) as exc:
        _validate_dias_horarios_mes('[{"dia": 1, "horarios": ["09:00"]}, {"dia": 1, "horarios": ["10:00"]}]')
    assert exc.value.status_code == 422


def test_invalid_time_format_raises_422():
    with pytest.raises(HTTPException) as exc:
        _validate_dias_horarios_mes('[{"dia": 1, "horarios": ["25:00"]}]')
    assert exc.value.status_code == 422


def test_invalid_time_text_raises_422():
    with pytest.raises(HTTPException) as exc:
        _validate_dias_horarios_mes('[{"dia": 1, "horarios": ["amanha"]}]')
    assert exc.value.status_code == 422


def test_duplicate_time_same_day_raises_422():
    with pytest.raises(HTTPException) as exc:
        _validate_dias_horarios_mes('[{"dia": 1, "horarios": ["09:00", "09:00"]}]')
    assert exc.value.status_code == 422


def test_more_than_5_days_raises_422():
    dias = [{"dia": d, "horarios": ["09:00"]} for d in [1, 2, 3, 4, 5, 6]]
    with pytest.raises(HTTPException) as exc:
        _validate_dias_horarios_mes(json.dumps(dias))
    assert exc.value.status_code == 422


def test_more_than_5_horarios_raises_422():
    horarios = [f"{h:02d}:00" for h in range(6)]
    with pytest.raises(HTTPException) as exc:
        _validate_dias_horarios_mes(json.dumps([{"dia": 1, "horarios": horarios}]))
    assert exc.value.status_code == 422


def test_empty_horarios_list_raises_422():
    with pytest.raises(HTTPException) as exc:
        _validate_dias_horarios_mes('[{"dia": 1, "horarios": []}]')
    assert exc.value.status_code == 422


def test_empty_array_raises_422():
    with pytest.raises(HTTPException) as exc:
        _validate_dias_horarios_mes("[]")
    assert exc.value.status_code == 422


@pytest.fixture
def auth_override(app):
    """Substitui get_current_user por um usuário com permissão de edição.

    Necessário porque autenticar via header Bearer real exigiria uma sessão
    válida em dbo.etl_sessao — aqui sobrescrevemos a dependency diretamente
    no app, contornando a autenticação para isolar a lógica do endpoint.
    """
    app.dependency_overrides[get_current_user] = lambda: {
        "matricula": "TESTER", "perfil": "admin", "permissoes": [PERM_EDITAR],
    }
    yield
    app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.api
def test_register_monthly_days_times_requires_dias_horarios_mes(client, auth_override):
    """schedule_type='monthly_days_times' com dias_horarios_mes PRESENTE e
    vazio -> 422 antes de qualquer chamada a get_db_conn (por isso este teste
    não precisa mockar o banco). A chave AUSENTE virou PATCH-parcial (achado 3
    da revisão da F5) e é validada contra o valor vigente no banco — coberta
    em tests/test_dependencias_f5.py.
    """
    r = client.post(
        "/pipelines/register",
        json={
            "pipeline_name": "TESTE_MDT", "scheduled_time": "09:00:00",
            "schedule_type": "monthly_days_times", "project_name": "BI_CVP", "domain": "TESTE",
            "dias_horarios_mes": None,
        },
    )
    assert r.status_code == 422
    assert "dias_horarios_mes" in r.json()["detail"]


@pytest.mark.api
def test_register_monthly_days_times_invalid_dia_returns_error(client, auth_override):
    """dias_horarios_mes com dia fora do intervalo -> 422 com mensagem específica."""
    r = client.post(
        "/pipelines/register",
        json={
            "pipeline_name": "TESTE_MDT", "scheduled_time": "09:00:00",
            "schedule_type": "monthly_days_times", "project_name": "BI_CVP", "domain": "TESTE",
            "dias_horarios_mes": '[{"dia": 99, "horarios": ["09:00"]}]',
        },
    )
    assert r.status_code == 422
    assert "Dia do mês inválido" in r.json()["detail"]
