"""Endpoint integrado sem sockets: reserva, compensação e ambiguidade."""
import asyncio
from unittest.mock import MagicMock
from contextlib import contextmanager
from uuid import uuid4
import pytest
from fastapi import HTTPException
from services import alert_cycle as cycle
from tests.test_alert_cycle_f13 import database, KEY, PIPELINE, RUN, mutations


@pytest.mark.parametrize('state,pending,expected', [
    ('Pending', 'own', True), ('Rejected', None, True),
    ('Rejected', 'new', False), ('Unknown', 'own', False),
    ('Confirmed', None, False), ('Pending', 'new', False)])
def test_compensation_inside_lock_never_deletes_new_operation(monkeypatch, state, pending, expected):
    operation = str(uuid4())
    conn, cur = database(monkeypatch, pending=operation if pending == 'own' else pending,
                         operation=(KEY, 1, state))
    compensate = MagicMock(side_effect=lambda cursor: conn.commit.assert_not_called())
    assert cycle.reject_unsent_clear(PIPELINE, RUN, operation, compensate=compensate) is expected
    if expected:
        compensate.assert_called_once_with(cur)
        conn.commit.assert_called_once()
    else:
        compensate.assert_not_called()
        assert not mutations(cur)


def test_compensation_db_failure_never_commits_release(monkeypatch):
    operation = str(uuid4())
    conn, cur = database(monkeypatch, pending=operation, operation=(KEY, 1, 'Pending'))
    assert cycle.reject_unsent_clear(PIPELINE, RUN, operation,
                                    compensate=MagicMock(side_effect=RuntimeError())) is False
    conn.commit.assert_not_called()


@pytest.mark.parametrize('schema,cohort,refused', [(None, None, False), (1,None,False),(1,'key',True)])
def test_execution_id_cannot_bypass_existing_cohort(monkeypatch, schema, cohort, refused):
    conn=MagicMock(); cur=conn.cursor.return_value;cur.execute.return_value=cur
    cur.fetchone.side_effect=[(schema,), (cohort,) if cohort else None]
    if refused:
        with pytest.raises(HTTPException) as exc:
            cycle.begin_rerun_clear(PIPELINE, '', connection_factory=lambda:conn)
        assert exc.value.detail['code']=='alert_clear_run_required'
        conn.commit.assert_not_called()
    else:
        assert cycle.begin_rerun_clear(PIPELINE, '', connection_factory=lambda:conn) is None
    assert not mutations(cur)


@pytest.fixture
def endpoint(monkeypatch):
    import routers.execucoes as route
    from services import workspace_operations as ops
    events=[];conn=MagicMock()
    async def resolve(*args, **kw):
        return PIPELINE, {'dag_run_id':RUN}, None
    monkeypatch.setattr(route,'_resolve_alvo_rerun',resolve)
    monkeypatch.setattr(route,'get_db_conn',lambda:conn)
    monkeypatch.setattr(route.ps,'original',lambda *args:None)
    monkeypatch.setattr(ops,'check_managed_run',lambda *args,**kw:None)
    monkeypatch.setattr(ops,'reserve_run',lambda *args,**kw:('token',False))
    monkeypatch.setattr(ops,'acknowledge_run',lambda *args:events.append('ack'))
    monkeypatch.setattr(route.rerun_params,'validar_overrides',lambda *args:(events.append('validate') or [{'job_name':'j','param_name':'p','param_value':'own'}],[]))
    monkeypatch.setattr(route.rerun_params,'gravar_overrides',lambda *args:events.append('write'))
    monkeypatch.setattr(route.rerun_params,'apagar_overrides',lambda *args:events.append('delete'))
    monkeypatch.setattr(cycle,'begin_rerun_clear',lambda *args,**kw:events.append('reserve') or 'operation')
    monkeypatch.setattr(route,'_aplicar_cascata',lambda *args,**kw:dict(dependentes_reabertos=[],corridas_substituidas=[],corridas_irmas_aposentadas=[],auditado=True,avisos=[]))
    return route,events


@pytest.mark.asyncio
@pytest.mark.parametrize('outcome', ['success','Rejected','Unknown','Cancelled','local'])
async def test_endpoint_clear_reserved_before_overrides_and_unknown_preserved(monkeypatch,endpoint,outcome):
    route,events=endpoint
    async def clear(*args,**kw):
        assert kw['clear_operation']=='operation'
        events.append('clear')
        if outcome=='Cancelled':raise asyncio.CancelledError()
        if outcome!='success':raise HTTPException(502,'fixture')
        return {'dag_run_id':RUN,'tasks_limpas':1}
    monkeypatch.setattr(route,'_clear_no_airflow',clear)
    def reject(*args,compensate=None):
        events.append('reject')
        if outcome in ('Rejected','local'):
            compensate(MagicMock())
            return True
        return False
    monkeypatch.setattr(cycle,'reject_unsent_clear',reject)
    body={'pipeline_name':PIPELINE,'dag_run_id':RUN,'task_id':'j','parametros':[{'job_name':'j','param_name':'p','param_value':'own'}]}
    if outcome=='success':
        result=await route.rerun_from_task(body,{'matricula':'fixture'})
        assert result['ok'] is True
    else:
        with pytest.raises(asyncio.CancelledError if outcome=='Cancelled' else HTTPException):
            await route.rerun_from_task(body,{'matricula':'fixture'})
    assert events[:4]==['validate','reserve','write','clear']
    assert ('delete' in events)==(outcome in ('Rejected','local'))


@pytest.mark.asyncio
async def test_no_parameters_cohort_delete_failure_never_sends(monkeypatch, endpoint):
    route, events = endpoint
    clear = MagicMock()
    monkeypatch.setattr(route, '_clear_no_airflow', clear)
    monkeypatch.setattr(route.rerun_params, 'apagar_overrides', MagicMock(side_effect=RuntimeError('fixture')))
    reject = MagicMock(return_value=True)
    monkeypatch.setattr(cycle, 'reject_unsent_clear', reject)
    with pytest.raises(HTTPException) as exc:
        await route.rerun_from_task({'pipeline_name':PIPELINE,'dag_run_id':RUN,'task_id':'j'}, {'matricula':'fixture'})
    assert exc.value.status_code == 503
    clear.assert_not_called()
    reject.assert_called_once()


@pytest.mark.asyncio
async def test_no_parameters_cohort_reserves_before_delete(monkeypatch, endpoint):
    route, events = endpoint
    async def clear(*args, **kw):
        assert kw['clear_operation'] == 'operation'
        events.append('clear')
        return {'dag_run_id':RUN, 'tasks_limpas':1}
    monkeypatch.setattr(route, '_clear_no_airflow', clear)
    await route.rerun_from_task({'pipeline_name':PIPELINE,'dag_run_id':RUN,'task_id':'j'}, {'matricula':'fixture'})
    assert events[:3] == ['reserve','delete','clear']
