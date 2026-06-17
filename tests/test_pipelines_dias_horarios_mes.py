"""
Testes para a validação de dias_horarios_mes (schedule_type 'monthly_days_times').
Função pura — não depende de banco de dados.
"""
from __future__ import annotations

import json

import pytest
from fastapi import HTTPException

from api.routers.pipelines import _validate_dias_horarios_mes


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
