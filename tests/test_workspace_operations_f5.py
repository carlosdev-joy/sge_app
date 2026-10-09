import asyncio
import json
import shutil
import subprocess
from pathlib import Path
from unittest.mock import AsyncMock
import pytest
from fastapi import HTTPException
from routers import execucoes, airflow
from services import workspace_operations as ops

PERMS = {"permissoes": ["tela_pipelines", "tela_jobs", "tela_logs", "acao_executar"]}


def test_contextual_navigation_rename_and_confirmed_snapshot():
    root = Path(__file__).resolve().parents[1]
    if not shutil.which("node") or not (root / "ui-react/node_modules/sucrase").is_dir():
        pytest.skip("Node/sucrase indisponível")
    result = subprocess.run(["node", "tests/js/workspace_f5_harness.cjs"], cwd=root, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("missing", ["tela_pipelines", "tela_jobs", "tela_logs"])
def test_logs_deny_missing_screen_before_loading_execution(monkeypatch, missing):
    read = AsyncMock(); monkeypatch.setattr(execucoes, "get_pipeline_execucao", read)
    with pytest.raises(HTTPException) as error:
        asyncio.run(execucoes.workspace_task_log("pipeline", "run", "task", auth={"permissoes": [p for p in PERMS["permissoes"] if p != missing]}))
    assert error.value.status_code == 403
    read.assert_not_called()


def test_logs_require_exact_resolved_run_and_task(monkeypatch):
    read = AsyncMock(return_value={"identidade": {"resolvido": True, "dag_run_id": "another"}, "etapas": [{"task_id": "task"}]})
    monkeypatch.setattr(execucoes, "get_pipeline_execucao", read)
    with pytest.raises(HTTPException) as error:
        asyncio.run(execucoes.workspace_task_log("pipeline", "requested", "task", auth=PERMS))
    assert error.value.status_code == 404


def test_execution_alias_preserves_explicit_run_id(monkeypatch):
    read = AsyncMock(return_value={"etapas": []}); monkeypatch.setattr(execucoes, "get_pipeline_execucao", read)
    asyncio.run(execucoes.get_workspace_pipeline_execution("ação/A %25", run_id="manual__2026-10-09", _auth=PERMS))
    read.assert_awaited_once_with("ação/A %25", data_referencia=None, run_id="manual__2026-10-09", _auth=PERMS)


@pytest.mark.parametrize("body", [{"conf": []}, {"conf": "bad"}, {"dag_run_id": 123}, {"logical_date": {}}, {"url": "http://external"}, {"conf": {"x": "a" * 65536}}])
def test_invalid_run_payload_never_dispatches(monkeypatch, body):
    send = AsyncMock(); monkeypatch.setattr(airflow, "trigger_dag_run", send)
    with pytest.raises(HTTPException) as error:
        asyncio.run(execucoes.workspace_pipeline_run("pipeline", body, auth=PERMS, authorization="Bearer synthetic"))
    assert error.value.status_code == 422
    send.assert_not_called()


def test_run_keeps_conf_and_fixed_identity_but_redacts_failure(monkeypatch):
    monkeypatch.setattr(ops, "reserve_run", lambda *a, **kw: (None, False))
    send = AsyncMock(return_value={"dag_run_id": "manual", "state": "queued"}); monkeypatch.setattr(airflow, "trigger_dag_run", send)
    body = {"conf": {"mode": "full", "data_referencia": "2026-10-09"}, "dag_run_id": "manual"}
    assert asyncio.run(execucoes.workspace_pipeline_run("pipeline", body, auth=PERMS, authorization="Bearer synthetic"))["state"] == "queued"
    send.assert_awaited_once_with("pipeline", body, user=PERMS)
    send.side_effect = HTTPException(500, "synthetic-private-config")
    with pytest.raises(HTTPException) as error:
        asyncio.run(execucoes.workspace_pipeline_run("pipeline", body, auth=PERMS, authorization="Bearer synthetic"))
    assert error.value.status_code == 503
    assert "synthetic-private" not in error.value.detail


class Cursor:
    def __init__(self, results): self.results = iter(results); self.calls = []; self.closed = False
    def execute(self, sql, params=()): self.calls.append((sql, params)); return self
    def fetchone(self): return next(self.results)
    def close(self): self.closed = True


class Connection:
    def __init__(self, cursor): self.c = cursor; self.closed = False
    def cursor(self): return self.c
    def close(self): self.closed = True


@pytest.mark.parametrize("bound", [None, ("old-version", "hash"), ("version", "old-hash")])
def test_old_or_unknown_managed_run_denied_before_clear(monkeypatch, bound):
    monkeypatch.setenv("WORKSPACE_PUBLICATIONS_ENABLED", "true")
    cur = Cursor([(1,), ("version", "hash", None), bound]); conn = Connection(cur)
    monkeypatch.setattr(ops, "get_db_conn", lambda: conn)
    with pytest.raises(HTTPException) as error: ops.check_managed_run("pipeline", "run", reprocess=True)
    assert error.value.status_code == 409
    assert conn.closed and cur.closed
    assert cur.calls[-1][1] == ("pipeline", "run")


def test_current_managed_run_allowed_and_legacy_unchanged(monkeypatch):
    monkeypatch.setenv("WORKSPACE_PUBLICATIONS_ENABLED", "true")
    for results in [[(1,), ("version", "hash", None), ("VERSION", "hash")], [(1,), None]]:
        cur = Cursor(results); monkeypatch.setattr(ops, "get_db_conn", lambda: Connection(cur))
        ops.check_managed_run("pipeline", "run", reprocess=True)
    monkeypatch.setenv("WORKSPACE_PUBLICATIONS_ENABLED", "false")
    monkeypatch.setattr(ops, "get_db_conn", lambda: pytest.fail("Flag desligada não consulta SQL"))
    ops.check_managed_run("pipeline", "run", reprocess=True)


@pytest.mark.parametrize("header", [None, "Basic synthetic"])
def test_direct_execution_alias_cannot_bypass_bearer_requirement(monkeypatch, header):
    send = AsyncMock(); monkeypatch.setattr(airflow, "trigger_dag_run", send)
    with pytest.raises(HTTPException) as error:
        asyncio.run(execucoes.workspace_pipeline_run("pipeline", {}, auth=PERMS, authorization=header))
    assert error.value.status_code == 401
    send.assert_not_called()
