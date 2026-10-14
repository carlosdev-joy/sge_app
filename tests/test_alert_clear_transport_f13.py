import asyncio
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException
from services import alert_cycle as cycle

BODY = dict(dag_run_id='run', dry_run=False, include_past=False,
            include_future=False, include_upstream=False)


@pytest.mark.parametrize('status,outcome', [(200, 'Confirmed'), (400, 'Rejected'),
    (403, 'Rejected'), (404, 'Rejected'), (422, 'Rejected'), (500, 'Unknown'),
    (502, 'Unknown'), (429, 'Unknown'), (302, 'Unknown')])
def test_response(monkeypatch, status, outcome):
    begin, finish = Mock(return_value='op'), Mock()
    monkeypatch.setattr(cycle, 'begin_clear', begin)
    monkeypatch.setattr(cycle, 'finish_clear', finish)
    response = Mock(status_code=status, is_success=status == 200)
    response.json.return_value = {'task_instances': [dict(dag_id='dag', dag_run_id='run', task_id='t')]}
    client = Mock(post=AsyncMock(return_value=response))
    assert asyncio.run(cycle.post_clear(client, 'dag', 'run', BODY)) is response
    begin.assert_called_once_with('dag', 'run')
    finish.assert_called_once_with('dag', 'run', 'op', outcome)
    client.post.assert_awaited_once()


@pytest.mark.parametrize('error', [TimeoutError(), asyncio.CancelledError()])
def test_ambiguous_exception(monkeypatch, error):
    monkeypatch.setattr(cycle, 'begin_clear', Mock(return_value='op'))
    finish = Mock()
    monkeypatch.setattr(cycle, 'finish_clear', finish)
    client = Mock(post=AsyncMock(side_effect=error))
    with pytest.raises(type(error)):
        asyncio.run(cycle.post_clear(client, 'dag', 'run', BODY))
    finish.assert_called_once_with('dag', 'run', 'op', 'Unknown')
    client.post.assert_awaited_once()


@pytest.mark.parametrize('changes', [{'dag_run_id': 'other'}, {'dry_run': True},
    {'include_past': True}, {'include_future': True}, {'include_upstream': True}])
def test_scope_before_reservation(monkeypatch, changes):
    begin = Mock()
    monkeypatch.setattr(cycle, 'begin_clear', begin)
    with pytest.raises(HTTPException):
        asyncio.run(cycle.post_clear(Mock(), 'dag', 'run', BODY | changes))
    begin.assert_not_called()


def test_invalid_success_remains_unknown(monkeypatch):
    monkeypatch.setattr(cycle, 'begin_clear', Mock(return_value='op'))
    finish = Mock()
    monkeypatch.setattr(cycle, 'finish_clear', finish)
    response = Mock(is_success=True)
    response.json.return_value = {}
    with pytest.raises(ValueError):
        asyncio.run(cycle.post_clear(Mock(post=AsyncMock(return_value=response)), 'dag', 'run', BODY))
    finish.assert_called_once_with('dag', 'run', 'op', 'Unknown')


def test_no_enrollment_no_post(monkeypatch):
    monkeypatch.setattr(cycle, 'begin_clear', Mock(return_value=None))
    client = Mock(post=AsyncMock())
    with pytest.raises(HTTPException):
        asyncio.run(cycle.post_clear(client, 'dag', 'run', BODY))
    client.post.assert_not_awaited()


def test_reservation_failure_no_post(monkeypatch):
    monkeypatch.setattr(cycle, 'begin_clear', Mock(side_effect=RuntimeError('db')))
    client = Mock(post=AsyncMock())
    with pytest.raises(RuntimeError):
        asyncio.run(cycle.post_clear(client, 'dag', 'run', BODY))
    client.post.assert_not_awaited()


def test_order_and_finalization_failure_never_reposts(monkeypatch):
    events = []
    def reserve(*args):
        events.append('reserved_committed')
        return 'op'
    async def post(*args, **kwargs):
        events.append('post')
        response = Mock(is_success=True)
        response.json.return_value = {'task_instances': [dict(dag_id='dag', dag_run_id='run', task_id='t')]}
        return response
    def finish(*args):
        events.append('finish')
        raise RuntimeError('db')
    monkeypatch.setattr(cycle, 'begin_clear', reserve)
    monkeypatch.setattr(cycle, 'finish_clear', finish)
    with pytest.raises(RuntimeError):
        asyncio.run(cycle.post_clear(Mock(post=post), 'dag', 'run', BODY))
    assert events == ['reserved_committed', 'post', 'finish']


@pytest.mark.parametrize('rows', [[], [None], [{}],
    [dict(dag_id='other', dag_run_id='run', task_id='t')],
    [dict(dag_id='dag', dag_run_id='other', task_id='t')],
    [dict(dag_id='dag', dag_run_id='run', task_id='')]])
def test_malformed_or_foreign_success_never_confirms(monkeypatch, rows):
    monkeypatch.setattr(cycle, 'begin_clear', Mock(return_value='op'))
    finish = Mock()
    monkeypatch.setattr(cycle, 'finish_clear', finish)
    response = Mock(is_success=True)
    response.json.return_value = {'task_instances': rows}
    with pytest.raises(ValueError):
        asyncio.run(cycle.post_clear(Mock(post=AsyncMock(return_value=response)), 'dag', 'run', BODY))
    finish.assert_called_once_with('dag', 'run', 'op', 'Unknown')


def test_reserved_clear_never_reserves_again_and_claim_precedes_post(monkeypatch):
    events = []
    begin = Mock(side_effect=AssertionError('must not reserve twice'))
    monkeypatch.setattr(cycle, 'begin_clear', begin)
    monkeypatch.setattr(cycle, 'claim_clear_send', lambda *args: events.append('claim_committed'))
    monkeypatch.setattr(cycle, 'finish_clear', lambda *args: events.append(args[-1]))
    async def send(*args, **kwargs):
        events.append('post')
        response = Mock(is_success=True)
        response.json.return_value = {'task_instances': [dict(dag_id='dag', dag_run_id='run', task_id='t')]}
        return response
    asyncio.run(cycle.post_reserved_clear(Mock(post=send), 'dag', 'run', BODY, 'op'))
    assert events == ['claim_committed', 'post', 'Confirmed']
    begin.assert_not_called()


def test_reserved_clear_failed_claim_never_posts(monkeypatch):
    monkeypatch.setattr(cycle, 'claim_clear_send', Mock(side_effect=cycle.conflict('alert_clear_already_sent')))
    client = Mock(post=AsyncMock())
    with pytest.raises(HTTPException):
        asyncio.run(cycle.post_reserved_clear(client, 'dag', 'run', BODY, 'op'))
    client.post.assert_not_awaited()


def test_reserved_clear_invalid_scope_does_not_consume_send_claim(monkeypatch):
    claim = Mock()
    monkeypatch.setattr(cycle, 'claim_clear_send', claim)
    with pytest.raises(HTTPException):
        asyncio.run(cycle.post_reserved_clear(Mock(), 'dag', 'run', BODY | {'dry_run': True}, 'op'))
    claim.assert_not_called()
