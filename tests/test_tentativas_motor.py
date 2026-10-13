"""Correção 2.21.2 — tentativas do motor (Airflow) na investigação da etapa.

Defeito reproduzido com dublês (fixture própria do root no DEV, sem acesso
aqui): Shell paralelo com retries=1 falha duas vezes. O Airflow registra
try_number=2/max_tries=1; a telemetria SQL fica em attempt=1/total=1 porque
o ciclo operacional é contado pelo log_start, fora do retry da tarefa. A tela
passava o número SQL como try_number e só oferecia o log 1.

`GET /pipeline-task-attempts` lê no Airflow a instância e o histórico da
tarefa EXATA (pipeline oficial, corrida resolvida, task_id da corrida) e nunca
usa o número SQL. Cobertura: permissão e entrada antes de qualquer leitura,
identidade da corrida/tarefa, codificação dos segmentos, fila sem início,
up_for_retry, histórico ausente, tarefa mapeada, linhas alheias, campos
sensíveis fora da resposta, erro/timeout/corpo grande/fila de consultas com 503
sanitizado e o log antigo inalterado. O teto do corpo é provado com httpx real:
a leitura para no bloco que o ultrapassa, fecha a resposta e cancela a outra.
"""
import asyncio
import contextlib
import gzip
import json
import time
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import HTTPException

from routers import airflow, execucoes
from services import tentativas_motor

PERMS = {"permissoes": ["tela_pipelines", "tela_jobs", "tela_logs"]}
DAG, RUN, TASK = "__workspace_ux_f5_teste", "workspace__0b9f6c1e-0000-4000-8000-000000000001", "ShellParalelo"
BASE = f"/api/v1/dags/{DAG}/dagRuns/{RUN}/taskInstances/{TASK}"


def _execucao(run=RUN, task=TASK, resolvido=True, pipeline=DAG):
    # Linha SQL da etapa: ciclo operacional 1 de 1, mesmo com dois try do motor.
    return {"pipeline_name": pipeline, "identidade": {"resolvido": resolvido, "run_id": run, "dag_run_id": run},
            "etapas": [{"job_name": task, "task_id": task, "status": "FAILED", "attempt": 1, "total_tentativas": 1, "tentativas": []},
                       {"job_name": "log_start", "task_id": f"log_start_{task}", "status": "SUCCESS", "attempt": 1, "total_tentativas": 1, "tentativas": []}]}


def _ti(n, state, **extra):
    row = {"dag_id": DAG, "dag_run_id": RUN, "task_id": TASK, "map_index": -1, "try_number": n, "max_tries": 1,
           "state": state, "start_date": f"2026-10-11T19:0{n}:00.000000+00:00", "end_date": f"2026-10-11T19:0{n}:02.000000+00:00",
           "duration": 2.0, "hostname": "worker-a", "pid": 4242, "queue": "default", "pool": "default_pool",
           "executor_config": {"segredo": "synthetic-private-executor"}, "rendered_fields": {"bash_command": "echo synthetic-private-rendered"},
           "note": "synthetic-private-note"}
    row.update(extra)
    return row


class Client:
    def __init__(self, routes, delay=0.0, fail=None):
        self.routes, self.delay, self.fail, self.calls = routes, delay, fail, []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    @contextlib.asynccontextmanager
    async def stream(self, method, path, **kwargs):
        self.calls.append(path)
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.fail:
            raise self.fail
        status, body = self.routes.get(path, (404, {"detail": "not found"}))
        if isinstance(body, bytes):
            yield httpx.Response(status, content=body)
        else:
            yield httpx.Response(status, json=body)


def _call(monkeypatch, routes=None, execution=None, client=None, **kwargs):
    read = AsyncMock(return_value=execution if execution is not None else _execucao())
    monkeypatch.setattr(execucoes, "get_pipeline_execucao", read)
    client = client or Client(routes or {})
    monkeypatch.setattr(airflow, "get_airflow_client", lambda: client)
    response = asyncio.run(execucoes.workspace_task_attempts(
        kwargs.pop("pipeline_name", DAG), kwargs.pop("run_id", RUN), kwargs.pop("task_id", TASK), auth=kwargs.pop("auth", PERMS)))
    return json.loads(response.body), response, client, read


def _retry_failed_twice():
    # Airflow 2.10+: o retry arquiva a tentativa 1 no histórico (como failed) e a
    # instância corrente é a 2; /tries devolve as duas.
    return {BASE: (200, _ti(2, "failed")), BASE + "/tries": (200, {"task_instances": [_ti(1, "failed"), _ti(2, "failed")], "total_entries": 2})}


def test_fixture_retry_lists_engine_tries_not_the_sql_attempt(monkeypatch):
    out, response, client, read = _call(monkeypatch, _retry_failed_twice())
    assert [row["try_number"] for row in out["attempts"]] == [2, 1], "1..n do motor, a mais recente primeiro"
    assert out["try_number"] == 2 and out["max_tries"] == 1 and out["state"] == "failed"
    assert out["complete"] is True and out["available"] is True and out["source"] == "airflow"
    assert [row["current"] for row in out["attempts"]] == [True, False]
    assert all(row["has_log"] and row["started"] for row in out["attempts"])
    assert out["pipeline_name"] == DAG and out["run_id"] == RUN and out["task_id"] == TASK
    assert response.headers["cache-control"] == "no-store"
    assert sorted(client.calls) == [BASE, BASE + "/tries"]
    read.assert_awaited_once_with(DAG, run_id=RUN, _auth=PERMS)


def test_response_never_carries_rendered_fields_config_or_note(monkeypatch):
    out, response, _, _ = _call(monkeypatch, _retry_failed_twice())
    assert b"synthetic-private" not in response.body
    assert all(set(row) == {"try_number", "state", "start_date", "end_date", "duration", "hostname", "started", "has_log", "origin", "current"} for row in out["attempts"])


@pytest.mark.parametrize("missing", ["tela_pipelines", "tela_jobs", "tela_logs"])
def test_permission_denied_before_reading_execution_or_engine(monkeypatch, missing):
    read = AsyncMock(); monkeypatch.setattr(execucoes, "get_pipeline_execucao", read)
    monkeypatch.setattr(airflow, "get_airflow_client", lambda: pytest.fail("sem permissão não consulta o motor"))
    with pytest.raises(HTTPException) as error:
        asyncio.run(execucoes.workspace_task_attempts(DAG, RUN, TASK, auth={"permissoes": [p for p in PERMS["permissoes"] if p != missing]}))
    assert error.value.status_code == 403
    read.assert_not_called()


@pytest.mark.parametrize("args", [("", RUN, TASK), (DAG, "", TASK), (DAG, RUN, ""), ("x" * 201, RUN, TASK), (DAG, "r" * 301, TASK),
                                  (DAG, RUN, "t" * 251), (DAG, "run\nx", TASK), (DAG, RUN, "task\x00"), ("pipe\tx", RUN, TASK)])
def test_invalid_input_rejected_before_reading(monkeypatch, args):
    read = AsyncMock(); monkeypatch.setattr(execucoes, "get_pipeline_execucao", read)
    with pytest.raises(HTTPException) as error:
        asyncio.run(execucoes.workspace_task_attempts(*args, auth=PERMS))
    assert error.value.status_code == 422
    read.assert_not_called()


@pytest.mark.parametrize("execution", [
    _execucao(resolvido=False), _execucao(run="workspace__outra"), _execucao(task="OutraEtapa"),
    {"identidade": {"resolvido": True, "run_id": RUN}, "etapas": [{"job_name": TASK, "task_id": None}]},
])
def test_task_must_belong_to_the_exact_resolved_run(monkeypatch, execution):
    read = AsyncMock(return_value=execution); monkeypatch.setattr(execucoes, "get_pipeline_execucao", read)
    monkeypatch.setattr(airflow, "get_airflow_client", lambda: pytest.fail("etapa fora da corrida não consulta o motor"))
    with pytest.raises(HTTPException) as error:
        asyncio.run(execucoes.workspace_task_attempts(DAG, RUN, TASK, auth=PERMS))
    assert error.value.status_code == 404


def test_segments_are_encoded_and_the_official_dag_is_used(monkeypatch):
    run, task = "manual__a/b%#?x=1", "grupo.n4/../x"
    base = "/api/v1/dags/Pipe_Oficial/dagRuns/manual__a%2Fb%25%23%3Fx%3D1/taskInstances/grupo.n4%2F..%2Fx"
    current = {**_ti(1, "success"), "dag_id": "Pipe_Oficial", "dag_run_id": run, "task_id": task}
    out, _, client, _ = _call(monkeypatch, {base: (200, current), base + "/tries": (200, {"task_instances": [current]})},
                              execution=_execucao(run=run, task=task, pipeline="Pipe_Oficial"), pipeline_name="pipe_oficial", run_id=run, task_id=task)
    assert sorted(client.calls) == [base, base + "/tries"]
    assert out["pipeline_name"] == "pipe_oficial" and out["dag_id"] == "Pipe_Oficial"
    assert [row["try_number"] for row in out["attempts"]] == [1]


def test_queued_retry_has_no_start_no_log_and_no_invented_time(monkeypatch):
    # try_number é incrementado ao agendar: a 2 está na fila, sem início.
    queued = _ti(2, "queued", start_date=None, end_date=None, duration=None, hostname="")
    out, _, _, _ = _call(monkeypatch, {BASE: (200, queued), BASE + "/tries": (200, {"task_instances": [_ti(1, "failed"), queued]})})
    second, first = out["attempts"]
    assert second == {"try_number": 2, "state": "queued", "start_date": None, "end_date": None, "duration": None, "hostname": None,
                      "started": False, "has_log": False, "origin": "instancia", "current": True}
    assert first["state"] == "failed" and first["has_log"] and first["origin"] == "historico"


def test_up_for_retry_current_instance_governs_its_own_try(monkeypatch):
    # /tries omite a instância up_for_retry (já arquivada como failed); a corrente diz a verdade dela.
    current = _ti(1, "up_for_retry")
    out, _, _, _ = _call(monkeypatch, {BASE: (200, current), BASE + "/tries": (200, {"task_instances": [_ti(1, "failed")]})})
    assert [(row["try_number"], row["state"], row["current"]) for row in out["attempts"]] == [(1, "up_for_retry", True)]


def test_never_scheduled_task_has_no_attempts(monkeypatch):
    current = _ti(0, None, start_date=None, end_date=None, duration=None)
    out, _, _, _ = _call(monkeypatch, {BASE: (200, current), BASE + "/tries": (200, {"task_instances": []})})
    assert out["available"] is True and out["attempts"] == [] and out["reason"] == "sem_tentativas" and out["complete"] is True


def test_missing_history_endpoint_degrades_to_current_and_says_incomplete(monkeypatch):
    out, _, _, _ = _call(monkeypatch, {BASE: (200, _ti(2, "failed")), BASE + "/tries": (404, {"detail": "not found"})})
    assert [row["try_number"] for row in out["attempts"]] == [2]
    assert out["history"] is False and out["complete"] is False, "tentativa 1 não é fabricada"


def test_invalid_history_body_degrades_without_failing(monkeypatch):
    out, _, _, _ = _call(monkeypatch, {BASE: (200, _ti(1, "success")), BASE + "/tries": (200, b"<html>synthetic</html>")})
    assert out["history"] is False and out["complete"] is True and [row["try_number"] for row in out["attempts"]] == [1]


def test_missing_instance_is_reported_not_invented(monkeypatch):
    out, _, _, _ = _call(monkeypatch, {BASE + "/tries": (200, {"task_instances": [_ti(1, "success")]})})
    assert out["available"] is False and out["reason"] == "instancia_ausente" and out["attempts"] == []


def test_foreign_rows_are_dropped_and_counted(monkeypatch):
    history = [_ti(1, "failed"), _ti(1, "success", task_id="log_start_ShellParalelo"), _ti(1, "success", dag_run_id="workspace__outra"),
               _ti(1, "success", dag_id="outro_dag"), _ti(1, "success", map_index=3), _ti(3, "success"), _ti(1, "success"), _ti(0, "failed"), "lixo"]
    out, _, _, _ = _call(monkeypatch, {BASE: (200, _ti(2, "running", end_date=None)), BASE + "/tries": (200, {"task_instances": history})})
    assert [(row["try_number"], row["state"]) for row in out["attempts"]] == [(2, "running"), (1, "failed")]
    assert out["ignored"] == 8 and out["complete"] is True


@pytest.mark.parametrize("current,reason", [
    ({**_ti(1, "success"), "map_index": 0}, "tarefa_mapeada"),
    ({**_ti(1, "success"), "dag_run_id": "workspace__outra"}, "instancia_divergente"),
    ({**_ti(1, "success"), "task_id": "outra"}, "instancia_divergente"),
    ({**_ti(1, "success"), "try_number": "2"}, "contador_invalido"),
])
def test_unsupported_or_foreign_instance_is_honest(monkeypatch, current, reason):
    out, _, _, _ = _call(monkeypatch, {BASE: (200, current), BASE + "/tries": (200, {"task_instances": [_ti(1, "success")]})})
    assert out["available"] is False and out["reason"] == reason and out["attempts"] == []


@pytest.mark.parametrize("routes,client_kwargs", [
    ({BASE: (500, {"detail": "synthetic-private-upstream"})}, {}),
    ({BASE: (401, {"detail": "synthetic-private-auth"})}, {}),
    # JSON válido acima de 1 MiB: só o teto do corpo recusa.
    ({BASE: (200, json.dumps({**_ti(1, "success"), "padding": "x" * (1024 * 1024)}).encode()),
      BASE + "/tries": (200, {"task_instances": []})}, {}),
    ({BASE: (200, ["lista"])}, {}),
    ({}, {"fail": httpx.ConnectError("synthetic-private-connect")}),
])
def test_engine_failures_are_sanitized_503(monkeypatch, routes, client_kwargs):
    with pytest.raises(HTTPException) as error:
        _call(monkeypatch, client=Client(routes, **client_kwargs))
    assert error.value.status_code == 503 and "synthetic-private" not in error.value.detail


def test_deadline_cancels_slow_engine_and_releases_the_slot(monkeypatch):
    monkeypatch.setattr(execucoes, "_ENGINE_ATTEMPTS_DEADLINE", 0.05)
    monkeypatch.setattr(execucoes, "_ENGINE_ATTEMPTS_SLOTS", asyncio.Semaphore(1))
    with pytest.raises(HTTPException) as error:
        _call(monkeypatch, client=Client(_retry_failed_twice(), delay=5))
    assert error.value.status_code == 503
    assert execucoes._ENGINE_ATTEMPTS_SLOTS._value == 1, "vaga devolvida após o prazo"


def test_busy_slots_refuse_quickly_without_calling_the_engine(monkeypatch):
    monkeypatch.setattr(execucoes, "_ENGINE_ATTEMPTS_SLOTS", asyncio.Semaphore(0))
    monkeypatch.setattr(execucoes, "_ENGINE_ATTEMPTS_WAIT", 0.01)
    client = Client(_retry_failed_twice())
    with pytest.raises(HTTPException) as error:
        _call(monkeypatch, client=client)
    assert error.value.status_code == 503 and "ocupada" in error.value.detail
    assert client.calls == []


def test_concurrency_limit_is_bounded():
    assert execucoes._ENGINE_ATTEMPTS_SLOTS._value == 4 and execucoes._ENGINE_ATTEMPTS_DEADLINE <= 8.0


BLOCK = 64 * 1024
CAP_BLOCKS = execucoes._ENGINE_ATTEMPTS_BYTES // BLOCK


class Body(httpx.AsyncByteStream):
    """Corpo servido em blocos; registra quantos saíram, cancelamento e fechamento."""

    def __init__(self, blocks, hold=False, after=None):
        self.blocks, self.hold, self.after = list(blocks), hold, after
        self.served, self.cancelled, self.closed = 0, False, False
        self.entered = asyncio.Event()

    async def __aiter__(self):
        try:
            self.entered.set()
            if self.after:
                await self.after.entered.wait()
            if self.hold:
                await asyncio.sleep(3600)
            for block in self.blocks:
                self.served += 1
                yield block
        except asyncio.CancelledError:
            self.cancelled = True
            raise

    async def aclose(self):
        self.closed = True

    def state(self):
        return {"served": self.served, "cancelled": self.cancelled, "closed": self.closed}


def _stream_call(monkeypatch, current, tries, headers=None):
    # httpx real com transporte em memória: mesmo stream/decodificação/fechamento da produção.
    seen = []

    def handler(request):
        seen.append(request)
        body = tries if request.url.path.endswith("/tries") else current
        return httpx.Response(200, stream=body, headers=headers if body is current else None)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://airflow.invalid")
    monkeypatch.setattr(execucoes, "get_pipeline_execucao", AsyncMock(return_value=_execucao()))
    monkeypatch.setattr(airflow, "get_airflow_client", lambda: client)
    monkeypatch.setattr(execucoes, "_ENGINE_ATTEMPTS_SLOTS", asyncio.Semaphore(1))

    async def run():
        try:
            out, error = json.loads((await execucoes.workspace_task_attempts(DAG, RUN, TASK, auth=PERMS)).body), None
        except HTTPException as caught:
            out, error = None, caught
        # Estado no retorno do endpoint, antes de o asyncio.run cancelar tarefas que sobrarem.
        return out, error, {"current": current.state(), "tries": tries.state(), "client_closed": client.is_closed,
                            "slot": execucoes._ENGINE_ATTEMPTS_SLOTS._value, "requests": len(seen),
                            "encodings": {request.headers.get("accept-encoding") for request in seen}}

    start = time.monotonic()
    out, error, state = asyncio.run(run())
    state["elapsed"] = time.monotonic() - start
    return out, error, state


def _json_blocks(payload):
    raw = json.dumps(payload).encode()
    return [raw[i:i + BLOCK] for i in range(0, len(raw), BLOCK)]


def test_oversized_instance_stops_at_the_cap_closes_and_cancels_the_sibling(monkeypatch):
    tries = Body([], hold=True)
    current = Body([b"x" * BLOCK] * (CAP_BLOCKS * 4), after=tries)
    out, error, state = _stream_call(monkeypatch, current, tries)
    assert error.status_code == 503 and out is None
    assert state["current"] == {"served": CAP_BLOCKS + 1, "cancelled": False, "closed": True}, "para no bloco que passa de 1 MiB"
    assert state["tries"] == {"served": 0, "cancelled": True, "closed": True}, "a irmã é cancelada e fechada antes da resposta"
    assert state["client_closed"] and state["slot"] == 1 and state["elapsed"] < 2, "sem esperar o prazo de 8 s"
    assert state["encodings"] == {"identity"}


def test_oversized_history_stops_at_the_cap_and_degrades_to_the_instance(monkeypatch):
    current = Body(_json_blocks(_ti(2, "failed")))
    tries = Body([b"x" * BLOCK] * (CAP_BLOCKS * 4))
    out, error, state = _stream_call(monkeypatch, current, tries)
    assert error is None and [row["try_number"] for row in out["attempts"]] == [2]
    assert out["history"] is False and out["complete"] is False, "tentativa 1 não é fabricada"
    assert state["tries"] == {"served": CAP_BLOCKS + 1, "cancelled": False, "closed": True}
    assert state["current"]["closed"] and state["client_closed"] and state["slot"] == 1


def test_body_exactly_at_the_cap_is_accepted(monkeypatch):
    row = {**_ti(1, "success"), "padding": ""}
    row["padding"] = "x" * (execucoes._ENGINE_ATTEMPTS_BYTES - len(json.dumps(row).encode()))
    blocks = _json_blocks(row)
    assert sum(map(len, blocks)) == execucoes._ENGINE_ATTEMPTS_BYTES
    out, error, _ = _stream_call(monkeypatch, Body(blocks), Body(_json_blocks({"task_instances": [_ti(1, "success")]})))
    assert error is None and [row["try_number"] for row in out["attempts"]] == [1] and out["history"] is True


def test_compressed_body_is_refused_before_decoding(monkeypatch):
    # Pedimos identity; um gzip pequeno que vira mais de 1 MiB nem é lido.
    bomb = gzip.compress(json.dumps({**_ti(1, "success"), "padding": "x" * (4 * 1024 * 1024)}).encode())
    current, tries = Body([bomb]), Body([], hold=True)
    out, error, state = _stream_call(monkeypatch, current, tries, headers={"Content-Encoding": "gzip"})
    assert error.status_code == 503 and state["current"]["served"] == 0 and state["current"]["closed"]
    assert state["tries"]["closed"] or state["requests"] == 1, "a irmã, se chegou a abrir, foi fechada"
    assert state["client_closed"] and state["slot"] == 1


def test_deadline_cancels_both_streams_and_releases_the_slot(monkeypatch):
    monkeypatch.setattr(execucoes, "_ENGINE_ATTEMPTS_DEADLINE", 0.05)
    current, tries = Body([], hold=True), Body([], hold=True)
    out, error, state = _stream_call(monkeypatch, current, tries)
    assert error.status_code == 503 and "synthetic" not in error.detail
    assert state["current"] == state["tries"] == {"served": 0, "cancelled": True, "closed": True}
    assert state["client_closed"] and state["slot"] == 1


def test_service_gap_count_is_exact_without_filling():
    out = tentativas_motor.montar(_ti(3, "failed"), [_ti(1, "failed")], dag_id=DAG, run_id=RUN, task_id=TASK)
    assert [row["try_number"] for row in out["attempts"]] == [3, 1] and out["complete"] is False


def test_legacy_log_endpoint_contract_unchanged(monkeypatch):
    # O log continua pelo try_number pedido (agora o do motor); a rota não mudou.
    read = AsyncMock(return_value=_execucao()); monkeypatch.setattr(execucoes, "get_pipeline_execucao", read)
    paths = []

    class Stream:
        def __init__(self, path): paths.append(path); self.is_success = True
        async def __aenter__(self): return self
        async def __aexit__(self, *exc): return False
        async def aiter_bytes(self):
            yield b"log da tentativa 2"

    class LogClient(Client):
        def stream(self, method, path, **kwargs): return Stream(path)

    monkeypatch.setattr(airflow, "get_airflow_client", lambda: LogClient({}))
    response = asyncio.run(execucoes.workspace_task_log(DAG, RUN, TASK, try_number=2, auth=PERMS))
    assert response.body == b"log da tentativa 2" and paths == [BASE + "/logs/2"]


def test_migration_169_is_idempotent_and_bumps_only_the_patch():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    migrations = sorted((root / "sql/migrations").glob("169_*.sql"))
    assert [m.name for m in migrations] == ["169_versao_tentativas_motor.sql"]
    sql = migrations[0].read_text(encoding="utf-8")
    assert "N'Tentativas do motor na investigação da etapa'" in sql
    assert "ELSE IF EXISTS (SELECT 1 FROM dbo.etl_versao_ferramenta WHERE titulo = @titulo)" in sql
    assert "SET @nova = CONCAT(@maior, '.', @menor, '.', @patch + 1);" in sql
    assert "config_key = 'app_version'" in sql and "config_key = 'app_release_name'" in sql
    assert sql.rstrip().endswith("GO")
    assert (root / "docs/release-notes/2.21.2-tentativas-motor.md").is_file()
