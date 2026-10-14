from copy import deepcopy
from unittest.mock import AsyncMock, MagicMock

import pytest
from services.alert_observation import terminal_observation

PIPELINE, RUN = '__eoc_f13_pipeline', '__eoc_f13_run'


def fixture():
    run = dict(dag_id=PIPELINE, dag_run_id=RUN, state='success', end_date='2026-10-14T12:00:00Z')
    tasks = [dict(dag_id=PIPELINE, dag_run_id=RUN, task_id=name, state='success',
                  map_index=-1, try_number=1) for name in ('job', 'notify')]
    return run, dict(total_entries=2, task_instances=tasks)


async def observe(run, page, *, second=None, after=None):
    payloads = [run, page, deepcopy(page) if second is None else second,
                deepcopy(run) if after is None else after]
    client = MagicMock()
    def response(payload):
        result = MagicMock(is_success=True)
        result.json.return_value = payload
        return result
    client.get = AsyncMock(side_effect=[response(x) for x in payloads])
    return await terminal_observation(client, PIPELINE, RUN,
                                      expected_tasks=('job', 'notify'), processing_tasks=('job',))


@pytest.mark.asyncio
async def test_stable_processing_requires_warning_proof():
    result = await observe(*fixture())
    assert result['processingResult'] == 'success'
    assert result['warningEvidenceRequired'] is True
    assert result['tasks'] == [('job', 'success')]


@pytest.mark.asyncio
async def test_communication_failure_independent():
    run, page = fixture()
    run['state'] = 'failed'
    page['task_instances'][1]['state'] = 'failed'
    assert (await observe(run, page))['processingResult'] == 'success'


@pytest.mark.asyncio
@pytest.mark.parametrize('state', ['upstream_failed', 'skipped', 'removed'])
@pytest.mark.parametrize('communication_state', ['failed', 'upstream_failed'])
async def test_communication_blocking_processing_requires_causal_proof(state, communication_state):
    run, page = fixture()
    run['state'] = 'failed'
    page['task_instances'][0]['state'] = state
    page['task_instances'][1]['state'] = communication_state
    assert await observe(run, page) is None


@pytest.mark.asyncio
async def test_actual_processing_failure_survives_communication_failure():
    run, page = fixture()
    run['state'] = 'failed'
    for row in page['task_instances']:
        row['state'] = 'failed'
    assert (await observe(run, page))['processingResult'] == 'failure'


@pytest.mark.asyncio
@pytest.mark.parametrize('blocked_state', ['skipped', 'upstream_failed', 'removed'])
async def test_failed_processing_not_hidden_by_another_blocked_job(blocked_state):
    run, page = fixture()
    run['state'] = 'failed'
    page['task_instances'][0]['state'] = 'failed'
    page['task_instances'][1]['state'] = 'failed'
    page['task_instances'].append(dict(page['task_instances'][0], task_id='blocked', state=blocked_state))
    page['total_entries'] = 3
    client = MagicMock()
    def response(payload):
        value = MagicMock(is_success=True)
        value.json.return_value = payload
        return value
    client.get = AsyncMock(side_effect=[response(x) for x in (run, page, deepcopy(page), deepcopy(run))])
    result = await terminal_observation(client, PIPELINE, RUN,
                                       expected_tasks=('job', 'blocked', 'notify'),
                                       processing_tasks=('job', 'blocked'))
    assert result['processingResult'] == 'failure'


@pytest.mark.asyncio
async def test_processing_failure_not_hidden_by_success_leaf():
    run, page = fixture()
    page['task_instances'][0]['state'] = 'failed'
    assert (await observe(run, page))['processingResult'] == 'failure'


@pytest.mark.asyncio
async def test_unexplained_dag_failure_not_green():
    run, page = fixture()
    run['state'] = 'failed'
    assert await observe(run, page) is None


@pytest.mark.asyncio
@pytest.mark.parametrize('field,value', [('state', 'running'), ('dag_run_id', 'other'),
                                        ('dag_id', 'other'), ('map_index', 0), ('task_id', 'notify')])
async def test_incomplete_wrong_run_or_dynamic_mapping_fail_closed(field, value):
    run, page = fixture()
    page['task_instances'][0][field] = value
    assert await observe(run, page) is None


@pytest.mark.asyncio
@pytest.mark.parametrize('value', [1, 3, True, None])
async def test_pagination_total_exact(value):
    run, page = fixture()
    page['total_entries'] = value
    assert await observe(run, page) is None


@pytest.mark.asyncio
@pytest.mark.parametrize('value', [None, True, False, -1.0, '-1', 'missing'])
async def test_static_mapping_requires_explicit_integer_proof(value):
    run, page = fixture()
    for row in page['task_instances']:
        if value == 'missing':
            row.pop('map_index')
        else:
            row['map_index'] = value
    assert await observe(run, page) is None


@pytest.mark.asyncio
@pytest.mark.parametrize('target', ['task', 'run'])
async def test_change_during_read_invalidates_observation(target):
    run, page = fixture()
    second, after = deepcopy(page), deepcopy(run)
    if target == 'task':
        second['task_instances'][0]['try_number'] = 2
    else:
        after['end_date'] = '2026-10-14T13:00:00Z'
    assert await observe(run, page, second=second, after=after) is None


@pytest.mark.asyncio
async def test_private_transport_error_never_escapes():
    client = MagicMock()
    client.get = AsyncMock(side_effect=RuntimeError('private-token'))
    assert await terminal_observation(client, PIPELINE, RUN,
                                      expected_tasks=('job',), processing_tasks=('job',)) is None


@pytest.mark.asyncio
async def test_paginated_inventory_not_truncated():
    run, page = fixture()
    one = dict(total_entries=2, task_instances=page['task_instances'][:1])
    two = dict(total_entries=2, task_instances=page['task_instances'][1:])
    client = MagicMock()
    def response(payload):
        r = MagicMock(is_success=True)
        r.json.return_value = payload
        return r
    client.get = AsyncMock(side_effect=[response(x) for x in (run, one, two, one, two, run)])
    result = await terminal_observation(client, PIPELINE, RUN,
                                       expected_tasks=('job', 'notify'), processing_tasks=('job',))
    assert result['processingResult'] == 'success'
    offsets = [c.kwargs['params']['offset'] for c in client.get.call_args_list if 'params' in c.kwargs]
    assert offsets == [0, 1, 0, 1]


@pytest.mark.asyncio
@pytest.mark.parametrize('dag_state', ['success', 'failed'])
async def test_compiled_required_report_failure_reaches_main_alert(dag_state):
    from services.alert_enrollment import compiled_inventory
    markers = {'workspace_version_id': 'fixture'}
    source = ('WORKSPACE_MARKERS = ' + repr(markers) + '\n'
              'with DAG(dag_id="fixture") as dag:\n'
              '    a = PythonOperator(task_id="job", python_callable=_sql_load)\n'
              '    b = EmailOperator(task_id="notify")\n')
    expected, processing = compiled_inventory(source, markers)
    run, page = fixture()
    run['state'] = dag_state
    page['task_instances'][1]['state'] = 'failed'
    client = MagicMock()
    def response(payload):
        value = MagicMock(is_success=True)
        value.json.return_value = payload
        return value
    client.get = AsyncMock(side_effect=[response(x) for x in
                           (run, page, deepcopy(page), deepcopy(run))])
    result = await terminal_observation(client, PIPELINE, RUN,
                                       expected_tasks=expected, processing_tasks=processing)
    assert result['processingResult'] == 'failure'
