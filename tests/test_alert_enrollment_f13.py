"""Matrícula original: fixture própria, sem rede/envio ou dados de cliente."""
import json
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from services import alert_enrollment as enrollment
from services.pipeline_alerts import disabled_policy

VERSION = str(uuid4())
DEFINITION = {'alertPolicy': disabled_policy()}


def capture(**kwargs):
    return enrollment.snapshot(VERSION, DEFINITION, expected_tasks=['job', 'email'],
                               processing_tasks=['job'], **kwargs)


def test_canonical_original_is_detached_and_order_independent():
    definition = {'alertPolicy': disabled_policy()}
    first = enrollment.snapshot(VERSION, definition, expected_tasks=['b', 'a'], processing_tasks=['a'])
    second = enrollment.snapshot(VERSION.upper(), definition, expected_tasks=['a', 'b'], processing_tasks=['a'])
    assert first == second
    definition['alertPolicy']['events'].append('failure')
    assert json.loads(first[0])['policy']['events'] == []
    assert first != enrollment.snapshot(VERSION, definition, expected_tasks=['a', 'b'], processing_tasks=['a'])


@pytest.mark.parametrize('expected,processing', [([], ['a']), (['a'], []),
    ('a', ['a']), (['a'], 'a'), (['a', 'a'], ['a']), (['a'], ['a', 'a']),
    (['a'], ['b']), ([True], ['a']), (['a\n'], ['a\n']),
    (['x'*251], ['x'*251]), (['\ud800'], ['\ud800'])])
def test_invalid_inventory_fails_closed(expected, processing):
    with pytest.raises(HTTPException):
        enrollment.snapshot(VERSION, DEFINITION, expected_tasks=expected, processing_tasks=processing)


def database(monkeypatch, cycle=None, stored=None, schema=1):
    cur = MagicMock()
    cur.execute.return_value = cur
    cur.fetchone.side_effect = [(schema,), stored]
    lock = MagicMock(return_value=cycle)
    monkeypatch.setattr(enrollment, 'locked_cycle', lock)
    return cur, lock


def enroll(cur, definition=DEFINITION):
    return enrollment.enroll_reserved(cur, '__eoc_f13_pipeline', '__eoc_f13_run',
        VERSION, definition, expected_tasks=['job', 'email'], processing_tasks=['job'])


def writes(cur):
    return [x for x in cur.execute.call_args_list if x.args[0].startswith('INSERT')]


def test_new_cycle_and_snapshot_share_caller_transaction(monkeypatch):
    cur, lock = database(monkeypatch)
    assert enroll(cur) is True
    lock.assert_called_once_with(cur, '__eoc_f13_pipeline', '__eoc_f13_run')
    assert len(writes(cur)) == 2
    assert writes(cur)[1].args[1][1:] == capture()
    assert all('COMMIT' not in c.args[0] for c in cur.execute.call_args_list)


def test_replay_is_read_only_even_after_clear(monkeypatch):
    cur, _ = database(monkeypatch, cycle=('key', 4, 'pending'), stored=capture())
    assert enroll(cur) is True
    assert not writes(cur)


@pytest.mark.parametrize('mode', [None, 'operational-test'])
def test_execute_command_replay_keeps_original_mode_without_current_grant_or_artifact(monkeypatch, mode):
    original = capture(delivery_mode=mode)
    cur = MagicMock()
    cur.execute.return_value = cur
    cur.fetchone.side_effect = [(VERSION, 'old-content', 'old-artifact', 'execute', json.dumps(DEFINITION)), original]
    monkeypatch.setattr(enrollment, 'locked_cycle', lambda *args: ('original', 1, None))
    from services import alert_runtime
    grant = MagicMock(side_effect=AssertionError('replay must not read current grant'))
    monkeypatch.setattr(alert_runtime, 'authorization', grant)
    assert enrollment.enroll_command(cur, 'own', 'run', 'token', existing=True)['deliveryMode' if mode else 'versionId'] == (mode or VERSION)
    grant.assert_not_called()
    assert not writes(cur)


@pytest.mark.parametrize('cycle,stored', [(('key', 1, None), None),
    (('key', 1, None), ('changed', 'hash')), (None, ('orphan', 'hash'))])
def test_missing_or_changed_original_never_retargets(monkeypatch, cycle, stored):
    cur, _ = database(monkeypatch, cycle=cycle, stored=stored)
    with pytest.raises(HTTPException) as error:
        enroll(cur)
    assert error.value.status_code == 409
    assert not writes(cur)


def test_legacy_never_creates_cohort(monkeypatch):
    cur, lock = database(monkeypatch)
    assert enroll(cur, {}) is False
    lock.assert_called_once_with(cur, '__eoc_f13_pipeline', '__eoc_f13_run')
    cur.execute.assert_not_called()


def test_enrolled_run_cannot_return_to_legacy(monkeypatch):
    cur, _ = database(monkeypatch, cycle=('key', 1, None))
    with pytest.raises(HTTPException) as error:
        enroll(cur, {})
    assert error.value.detail['code'] == 'alert_enrollment_original_conflict'
    assert not writes(cur)


def test_missing_schema_blocks_before_insert(monkeypatch):
    cur, _ = database(monkeypatch, schema=None)
    with pytest.raises(HTTPException) as error:
        enroll(cur)
    assert error.value.status_code == 503
    assert not writes(cur)

MARKERS = {'workspace_version_id': VERSION, 'workspace_content_hash': 'a'*64,
           'workspace_projection_hash': 'b'*64}


def artifact(body):
    return 'WORKSPACE_MARKERS = ' + repr(MARKERS) + '\nwith DAG(dag_id="fixture") as dag:\n' + body


def test_compiler_inventory_includes_custom_reports_excludes_alert_transport():
    source = artifact('''    a = PythonOperator(task_id='sql', python_callable=_sql_x)
    b = EmailOperator(task_id='mail')
    c = PythonOperator(task_id='teams', python_callable=_notify_x)
    d = PythonOperator(task_id='failure', python_callable=_registrar_falha)
    a >> [b, c] >> d
''')
    assert enrollment.compiled_inventory(source, MARKERS) == (
        ['sql', 'mail', 'teams', 'failure'], ['sql', 'mail', 'teams'])


@pytest.mark.parametrize('body', [
    "    a = PythonOperator(task_id=task)\n",
    "    for i in range(2):\n        a = PythonOperator(task_id=str(i))\n",
    "    a = PythonOperator(task_id='x', **kwargs)\n",
    "    a = PythonOperator(task_id='x')\n    b = PythonOperator(task_id='x')\n",
    "    a = PythonOperator(task_id='x')\n    a >> make_task()\n",
])
def test_dynamic_or_incomplete_artifacts_fail_closed(body):
    with pytest.raises(HTTPException):
        enrollment.compiled_inventory(artifact(body), MARKERS)


def test_artifact_wrong_original_rejected():
    with pytest.raises(HTTPException):
        enrollment.compiled_inventory(artifact("    a = PythonOperator(task_id='x')\n"), {})


@pytest.mark.parametrize('fail', [False, True])
def test_reservation_enrollment_precedes_commit_and_failure_rolls_back(monkeypatch, fail):
    from services import workspace_operations as ops
    monkeypatch.setenv('WORKSPACE_PUBLICATIONS_ENABLED', 'true')
    monkeypatch.setenv('EOC_ALERT_ENROLLMENT_ENABLED', 'true')
    conn = MagicMock(); cur = conn.cursor.return_value
    cur.execute.return_value = cur
    cur.fetchone.return_value = ('fixture-token', False)
    monkeypatch.setattr(ops, 'get_db_conn', lambda: conn)
    def enroll(cursor, pipeline, run, token, *, existing):
        assert existing is False
        conn.commit.assert_not_called()
        assert cursor is cur and token == 'fixture-token'
        assert 'BEGIN TRANSACTION' in cur.execute.call_args_list[0].args[0]
        if fail:
            raise enrollment.conflict('fixture')
    monkeypatch.setattr(enrollment, 'enroll_command', enroll)
    if fail:
        with pytest.raises(HTTPException) as error:
            ops.reserve_run('fixture', 'run', {}, 'actor')
        assert error.value.status_code == 409
        conn.commit.assert_not_called(); conn.rollback.assert_called_once()
    else:
        assert ops.reserve_run('fixture', 'run', {}, 'actor') == ('fixture-token', False)
        conn.commit.assert_called_once(); conn.rollback.assert_not_called()


def test_existing_command_without_cycle_never_backfills(monkeypatch):
    cur = MagicMock()
    cur.execute.return_value = cur
    cur.fetchone.return_value = (VERSION, 'a'*64, 'b'*64, 'execute', json.dumps(DEFINITION))
    lock = MagicMock(return_value=None)
    monkeypatch.setattr(enrollment, 'locked_cycle', lock)
    with pytest.raises(HTTPException) as error:
        enrollment.enroll_command(cur, 'fixture', 'old-run', 'token', existing=True)
    assert error.value.detail['code'] == 'alert_enrollment_legacy_replay'
    lock.assert_called_once_with(cur, 'fixture', 'old-run')
    assert not writes(cur)


def test_reprocess_snapshot_original_under_lock_without_writes(monkeypatch):
    encoded, digest = capture()
    cur = MagicMock(); cur.execute.return_value = cur
    cur.fetchone.return_value = (encoded, digest)
    monkeypatch.setattr(enrollment, 'locked_cycle', lambda *a: ('key', 2, None))
    original = enrollment.validate_reprocess_snapshot(cur, 'fixture', 'run', VERSION, DEFINITION)
    assert original['versionId'] == VERSION
    assert original['processingTasks'] == ['job']
    assert not writes(cur)


@pytest.mark.parametrize('cycle', [None, ('key', 1, 'pending')])
def test_reprocess_snapshot_missing_or_pending_never_reads_snapshot(monkeypatch, cycle):
    cur = MagicMock()
    monkeypatch.setattr(enrollment, 'locked_cycle', lambda *a: cycle)
    with pytest.raises(HTTPException):
        enrollment.validate_reprocess_snapshot(cur, 'fixture', 'run', VERSION, DEFINITION)
    cur.execute.assert_not_called()


@pytest.mark.parametrize('mutation', ['version', 'policy', 'hash', 'missing', 'json'])
def test_reprocess_snapshot_never_retargets(monkeypatch, mutation):
    encoded, digest = capture()
    cur = MagicMock(); cur.execute.return_value = cur
    definition, version = DEFINITION, VERSION
    if mutation == 'version': version = str(uuid4())
    if mutation == 'policy':
        definition = {'alertPolicy': disabled_policy()}
        definition['alertPolicy']['events'] = ['failure']
    if mutation == 'hash': digest = '0' * 64
    if mutation == 'json': encoded = '{}'
    cur.fetchone.return_value = None if mutation == 'missing' else (encoded, digest)
    monkeypatch.setattr(enrollment, 'locked_cycle', lambda *a: ('key', 2, None))
    with pytest.raises(HTTPException):
        enrollment.validate_reprocess_snapshot(cur, 'fixture', 'run', version, definition)
    assert not writes(cur)


def test_required_report_failure_is_main_failure():
    from services.alert_result import aggregate_result
    expected, processing = enrollment.compiled_inventory(artifact(
        "    a = PythonOperator(task_id='load', python_callable=_sql_x)\n"
        "    b = EmailOperator(task_id='report')\n"
        "    c = PythonOperator(task_id='transport', python_callable=teams_error)\n"
    ), MARKERS)
    assert processing == ['load', 'report']
    assert aggregate_result('success', [('load', 'success'), ('report', 'failed')],
                            expected_tasks=processing) == 'failure'
    assert aggregate_result('success', [('load', 'success'), ('report', 'success')],
                            expected_tasks=processing) == 'success'
