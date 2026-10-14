"""Warning exige prova positiva da tentativa corrente, não histórico do job."""
from copy import deepcopy
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.alert_observation import attempt_warning, terminal_observation
from services.alert_enrollment import compiled_warning_sources

P, R = '__eoc_f13_warning_pipeline', '__eoc_f13_warning_run'


def fixture():
    row = dict(dag_id=P, dag_run_id=R, task_id='job', state='success',
               try_number=2, map_index=-1, start_date='2026-10-14T10:00:00Z',
               end_date='2026-10-14T10:01:00Z')
    proof = dict(pipeline=P, run=R, task='job', tryNumber=2, mapIndex=-1,
                 startDate=row['start_date'], endDate=row['end_date'], statusCode=2)
    return row, proof


@pytest.mark.parametrize('code,expected', [(1, False), (2, True)])
def test_exact_attempt(code, expected):
    row, proof = fixture()
    proof['statusCode'] = code
    assert attempt_warning(proof, row, P, R) is expected
    assert attempt_warning(repr(proof), row, P, R) is expected


@pytest.mark.parametrize('field,value', [
    ('pipeline', 'other'), ('run', 'other'), ('task', 'other'),
    ('tryNumber', 1), ('tryNumber', True), ('tryNumber', '2'),
    ('mapIndex', 0), ('mapIndex', -1.0), ('statusCode', True),
    ('statusCode', 3), ('statusCode', None),
    ('startDate', '2026-10-14T09:00:00Z'), ('endDate', '2026-10-14T10:00:30Z'),
    ('startDate', '2026-10-14T10:00:00'), ('endDate', 'invalid'),
])
def test_stale_or_invalid_proof(field, value):
    row, proof = fixture()
    proof[field] = value
    assert attempt_warning(proof, row, P, R) is None


def test_same_try_after_clear_is_not_old_evidence():
    row, proof = fixture()
    row['start_date'] = '2026-10-14T11:00:00Z'
    row['end_date'] = '2026-10-14T11:01:00Z'
    assert attempt_warning(proof, row, P, R) is None


@pytest.mark.parametrize('field,value', [('try_number', True), ('map_index', False),
                                        ('state', 'failed'), ('start_date', None)])
def test_airflow_row_must_be_exact(field, value):
    row, proof = fixture()
    row[field] = value
    assert attempt_warning(proof, row, P, R) is None


def test_timezone_equivalence():
    row, proof = fixture()
    proof['startDate'] = '2026-10-14T07:00:00-03:00'
    assert attempt_warning(proof, row, P, R) is True


async def observe(*, code=2, stale=False, changing=False, helper_state='success', absent=False):
    row, proof = fixture()
    proof['statusCode'] = code
    if stale:
        proof['tryNumber'] = 1
    helper = dict(row, task_id='log_end_job', state=helper_state)
    run = dict(dag_id=P, dag_run_id=R, state='success', end_date=row['end_date'])
    page = dict(total_entries=2, task_instances=[row, helper])
    xcom = dict(dag_id=P, dag_run_id=R, task_id='log_end_job',
                key='eoc_result_attempt', value=repr(proof))
    second = deepcopy(page)
    if changing:
        second['task_instances'][0]['try_number'] = 3
    def response(payload):
        result = MagicMock(is_success=not absent)
        result.json.return_value = payload
        return result
    payloads = [run, page, xcom, second, run]
    client = MagicMock(get=AsyncMock(side_effect=[response(x) for x in payloads]))
    return await terminal_observation(client, P, R, expected_tasks=('job', 'log_end_job'),
                                      processing_tasks=('job',),
                                      warning_sources={'job': 'log_end_job'})


@pytest.mark.asyncio
@pytest.mark.parametrize('code,result', [(1, 'success'), (2, 'warning')])
async def test_warning_integrated_between_stable_reads(code, result):
    observed = await observe(code=code)
    assert observed['processingResult'] == result
    assert observed['warningEvidenceRequired'] is False


@pytest.mark.asyncio
@pytest.mark.parametrize('kwargs', [dict(stale=True), dict(changing=True),
                                   dict(helper_state='failed'), dict(absent=True)])
async def test_unproven_success_is_not_certified(kwargs):
    assert await observe(**kwargs) is None


def test_original_compiler_mapping_not_name_guess():
    source = '''with DAG() as dag:
    job = DataStageOperator(task_id="actual")
    a = PythonOperator(task_id="arbitrary", python_callable=log_end,
                       op_kwargs={"upstream_task_id": "actual"})
    b = PythonOperator(task_id="log_end_fake", python_callable=_notify_custom)
'''
    assert compiled_warning_sources(source, ['arbitrary', 'actual', 'log_end_fake'],
                                    ['actual', 'log_end_fake']) == {'actual': 'arbitrary'}


def test_compiler_rejects_duplicate_sources():
    from fastapi import HTTPException
    source = '''with DAG() as dag:
    job = DataStageOperator(task_id="job")
    a = PythonOperator(task_id="a", python_callable=log_end, op_kwargs={"upstream_task_id": "job"})
    b = PythonOperator(task_id="b", python_callable=log_end, op_kwargs={"upstream_task_id": "job"})
'''
    with pytest.raises(HTTPException):
        compiled_warning_sources(source, ['a', 'b', 'job'], ['job'])
