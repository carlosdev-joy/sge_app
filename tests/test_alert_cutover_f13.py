"""Cutover exato por matrícula transacional, sem publicação atual/fallback."""
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from tests.test_dag_factory_notificacao import factory, _pipeline, _job

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('eoc_cutover', ROOT / 'dags/utils/alert_cutover.py')
cutover = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cutover)


def test_old_run_remains_legacy_and_query_is_exact():
    hook = Mock()
    hook.get_first.side_effect = [(1, 2), None]
    assert cutover.principal_owner(hook, 'fixture', 'old') == 'legacy'
    query = hook.get_first.call_args
    assert query.kwargs['parameters'] == ('fixture', 'old')
    assert 'BIN2' in query.args[0]
    assert 'publicacao' not in query.args[0]


@pytest.mark.parametrize('length', [250, 251, 300])
def test_long_valid_legacy_run_is_not_suppressed(length):
    hook = Mock()
    hook.get_first.side_effect = [(1, 2), None]
    run = 'x' * length
    assert cutover.principal_owner(hook, 'fixture', run) == 'legacy'
    assert hook.get_first.call_args.kwargs['parameters'] == ('fixture', run)


@pytest.mark.parametrize('mode,owner', [(None, 'legacy'), ('operational-test', 'outbox'), ('invalid', 'unavailable')])
def test_enrolled_run_owns_all_principal_events_only_in_original_operational_mode(mode, owner):
    document = dict(policyRevision='synthetic-original', policy=dict(events=['failure']))
    if mode is not None:
        document['deliveryMode'] = mode
    encoded = json.dumps(document)
    hook = Mock()
    hook.get_first.side_effect = [(1, 2), (encoded, hashlib.sha256(encoded.encode()).hexdigest())]
    assert cutover.principal_owner(hook, 'fixture', 'new') == owner


@pytest.mark.parametrize('schema,row', [
    ((None, None), None), ((1, None), None),
    ((1, 2), (None, None)), ((1, 2), ('{}', 'bad-hash')),
])
def test_incomplete_or_corrupt_schema_never_falls_back(schema, row):
    hook = Mock()
    hook.get_first.side_effect = [schema, row]
    assert cutover.principal_owner(hook, 'fixture', 'new') == 'unavailable'


def test_sql_error_never_returns_legacy():
    hook = Mock()
    hook.get_first.side_effect = RuntimeError('synthetic-private')
    assert cutover.principal_owner(hook, 'fixture', 'new') == 'unavailable'


@pytest.mark.parametrize('name', ['teams_start', 'teams_end', 'teams_error'])
def test_generated_principal_is_suppressed_before_any_transport(factory, name):
    source = factory._generate_dag_source(_pipeline(), [_job('Carga')])
    tree = ast.parse(source)
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    transport, hook = Mock(), Mock()
    namespace = dict(_legacy_principal_allowed=lambda _: False, _teams_post_card=transport, MsSqlHook=hook)
    exec(compile(ast.Module(body=[function], type_ignores=[]), '<fixture>', 'exec'), namespace)
    namespace[name](dag_run=SimpleNamespace(dag_id='fixture', run_id='new'))
    transport.assert_not_called()
    hook.assert_not_called()


def test_custom_notification_does_not_use_principal_cutover(factory):
    tree = ast.parse(factory._generate_dag_source(_pipeline(), [_job('Carga')]))
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_resolve_e_envia_notificacao')
    assert '_legacy_principal_allowed' not in ast.unparse(function)
