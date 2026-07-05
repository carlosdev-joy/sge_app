"""Testes do POST /execucoes/reconciliar — passo 2 (genérico via Airflow REST).
Invariantes: terminal fecha (success→SUCCESS), running não é tocada,
logical_date sem match exato → nada fechado. Padrão de test_admin_conexoes.py.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


EXEC_ID = "20260704T060000"
LOGICAL_OK = "2026-07-04T06:00:00+00:00"
LOGICAL_ERRADA = "2026-07-04T07:00:00+00:00"


class _FakeResp:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    @property
    def is_success(self):
        return 200 <= self.status_code < 300

    def json(self):
        return self._payload


class _FakeAirflow:
    def __init__(self, logical, estados):
        self._logical = logical
        self._estados = estados

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, **kw):
        if url.endswith("/dagRuns"):
            return _FakeResp(200, {"dag_runs": [
                {"dag_run_id": "sched_1", "logical_date": self._logical, "state": "success"},
            ]})
        if url.endswith("/taskInstances"):
            return _FakeResp(200, {"task_instances": [
                {"task_id": k, "state": v} for k, v in self._estados.items()]})
        return _FakeResp(404, {})


class _FakeCur:
    """Cursor com rowcount inteiro e roteamento por prefixo do SQL."""

    def __init__(self, presos):
        self.rowcount = 0
        self.updates_passo2: list[tuple] = []
        self._presos = presos
        self._rows: list = []

    def execute(self, sql, params=None):
        s = " ".join(sql.split())
        if s.startswith("UPDATE dbo.etl_job_execution SET status=?"):
            self.updates_passo2.append(params)
            self.rowcount = 1
        elif "etl_ds_job_log" in s:          # passo 1 (join com o log do DS)
            self.rowcount = 0
        elif s.startswith("SELECT job_name, task_id"):
            self._rows = self._presos
            self.rowcount = -1

    def fetchall(self):
        return self._rows

    def close(self):
        pass


@pytest.fixture
def auth_executar(app):
    from deps import get_current_user
    app.dependency_overrides[get_current_user] = lambda: {
        "matricula": "OP1", "perfil": "operador",
        "permissoes": ["acao_executar"],
    }
    yield
    app.dependency_overrides.pop(get_current_user, None)


def _post(client, cur, fake_af):
    conn = MagicMock()
    conn.cursor.return_value = cur
    with patch("routers.execucoes.get_db_conn", return_value=conn), \
         patch("routers.execucoes.get_airflow_client", return_value=fake_af):
        return client.post("/execucoes/reconciliar",
                           json={"execution_id": EXEC_ID, "pipeline": "PIPE_X"})


def test_terminal_fecha_e_running_nao_e_tocada(client, auth_executar):
    cur = _FakeCur(presos=[("JobX", "JobX"), ("JobY", "JobY")])
    fake = _FakeAirflow(LOGICAL_OK, {"JobX": "success", "JobY": "running"})
    r = _post(client, cur, fake)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["closed_airflow"] == 1
    assert body["closed_datastage"] == 0
    # só JobX foi fechada — e com o status mapeado (success → SUCCESS)
    assert len(cur.updates_passo2) == 1
    assert cur.updates_passo2[0][0] == "SUCCESS"
    assert cur.updates_passo2[0][6] == "JobX"


def test_logical_date_sem_match_exato_nao_fecha_nada(client, auth_executar):
    cur = _FakeCur(presos=[("JobX", "JobX")])
    fake = _FakeAirflow(LOGICAL_ERRADA, {"JobX": "success"})
    r = _post(client, cur, fake)
    assert r.status_code == 200, r.text
    assert r.json()["closed_airflow"] == 0
    assert cur.updates_passo2 == []


def test_upstream_failed_vira_failed_e_skipped_vira_skipped(client, auth_executar):
    cur = _FakeCur(presos=[("JobA", "JobA"), ("JobB", "JobB")])
    fake = _FakeAirflow(LOGICAL_OK, {"JobA": "upstream_failed", "JobB": "skipped"})
    r = _post(client, cur, fake)
    assert r.status_code == 200, r.text
    assert r.json()["closed_airflow"] == 2
    novos = {p[6]: p[0] for p in cur.updates_passo2}
    assert novos == {"JobA": "FAILED", "JobB": "SKIPPED"}
