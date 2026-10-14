"""Reconciliação operacional fechada por padrão, sem publicar runs legados."""
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest

from services import alert_producer as producer


@pytest.mark.asyncio
async def test_disabled_loop_never_scans_or_uses_network(monkeypatch):
    monkeypatch.delenv('EOC_ALERT_PRODUCER_DRY_RUN', raising=False)
    work = MagicMock(side_effect=AssertionError('não executar'))
    monkeypatch.setattr(producer, '_work', work)
    await producer.reconcile_loop()
    work.assert_not_called()


def test_pending_runs_rotates_original_cohort_and_commits(monkeypatch):
    from services import alert_dispatcher
    conn, cur = MagicMock(), MagicMock()
    cur.execute.return_value = cur
    cur.fetchall.return_value = [('key', 'original', 'original-run')]

    @contextmanager
    def bounded():
        yield conn, cur

    monkeypatch.setattr(alert_dispatcher, 'bounded_conn', bounded)
    monkeypatch.setattr(producer, 'require_schema', lambda cur: None)
    assert producer.pending_runs() == [('original', 'original-run')]
    query = cur.execute.call_args_list[0].args[0]
    assert 'etl_alert_run_snapshot' in query
    assert 'c.pending_clear IS NULL' in query
    assert 'e.cycle_generation=c.generation' in query
    assert query.count('COLLATE Latin1_General_100_BIN2') == 2
    conn.commit.assert_called_once()


@pytest.mark.asyncio
async def test_no_pending_does_not_open_airflow(monkeypatch):
    from routers import airflow
    monkeypatch.setattr(producer, 'pending_runs', lambda: [])
    factory = MagicMock(side_effect=AssertionError('sem rede'))
    monkeypatch.setattr(airflow, 'get_airflow_client', factory)
    assert await producer.reconcile_once() == 0


@pytest.mark.asyncio
async def test_bad_authority_does_not_starve_next_original_run(monkeypatch):
    from routers import airflow
    monkeypatch.setattr(producer, 'pending_runs', lambda: [('own', 'a'), ('own', 'b')])
    client_context = MagicMock()
    client_context.__aenter__ = AsyncMock(return_value=MagicMock())
    client_context.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(airflow, 'get_airflow_client', lambda: client_context)
    read = AsyncMock(side_effect=[RuntimeError('private'), {'created': True}])
    monkeypatch.setattr(producer, 'reconcile_terminal', read)
    assert await producer.reconcile_once() == 1
    assert read.await_count == 2
