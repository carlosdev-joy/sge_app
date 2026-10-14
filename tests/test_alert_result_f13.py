"""Agregado não promove Clear, inventário incompleto ou folha all_done a verde."""
import pytest

from services.alert_result import aggregate_result


def result(state='success', tasks=(('job', 'success'), ('end', 'success')), **kwargs):
    return aggregate_result(state, tasks, expected_tasks=('job', 'end'), **kwargs)


def test_success_and_proven_job_warning():
    assert result() == 'success'
    assert result(warning_tasks=('job',)) == 'warning'


@pytest.mark.parametrize('state', ['failed', 'upstream_failed'])
def test_successful_all_done_leaf_cannot_hide_failure(state):
    assert result(tasks=(('job', state), ('end', 'success'))) == 'failure'


@pytest.mark.parametrize('state', [None, 'running', 'scheduled', 'queued', 'up_for_retry',
                                   'up_for_reschedule', 'deferred', 'restarting', 'unknown'])
def test_clear_or_open_task_invalidates_stale_terminal_dag(state):
    assert result(tasks=(('job', state), ('end', 'success'))) is None


@pytest.mark.parametrize('tasks', [(), (('job', 'success'),),
    (('job', 'success'), ('job', 'success')),
    (('job', 'success'), ('other', 'success')),
    (('job', 'skipped'), ('end', 'removed'))])
def test_incomplete_duplicate_foreign_or_entirely_skipped_inventory(tasks):
    assert result(tasks=tasks) is None


def test_warning_must_belong_to_successful_original_task():
    assert result(warning_tasks=('foreign',)) is None
    assert result(tasks=(('job', 'skipped'), ('end', 'success')),
                  warning_tasks=('job',)) is None


@pytest.mark.parametrize('state', ['running', 'queued', None])
def test_nonterminal_dag_has_no_event(state):
    assert result(state) is None


def test_failed_dag_and_warning_never_becomes_warning():
    assert result('failed', warning_tasks=('job',)) == 'failure'
