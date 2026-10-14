"""EOC-F3 (2.22.2): a execução contextual confere a publicação confirmada exibida.

Contrato do adaptador Python: par em campos próprios (fora de `conf`), validação
estrita, hash do pedido cobrindo o par, parâmetros da procedure, recusa 409
marcada como publicação e nada enviado ao Airflow sem reserva. A comparação sob
bloqueio é da procedure (migration 172): aqui ela aparece pelo erro que o SQL
Server devolve, e a ordem das conferências é verificada no texto da migration.
A leitura do par no contexto (.NET) é conferida aqui pelo texto de SqlDraftRepository:
contrato de forma, não prova de comportamento. O comportamento em banco real
(confirmada com active_hash diferente de content_hash expõe o par; pendente não)
fica em PublicationSqlTests (bancada SQL/.NET), assim como a procedure.

Replay (a procedure reconhece o mesmo pedido) nunca reenvia: só é sucesso com a
corrida exata confirmada por GET no Airflow; sem isso, 503 e a reserva fica para
a reconciliação. O ack cercado, a recusa do comando encerrado em 'erro' e a
repetição concorrente do mesmo pedido têm prova em banco real em PublicationSqlTests.
"""
import asyncio
import re
import sys
from pathlib import Path

import httpx
import pytest
from fastapi import HTTPException

HERE = Path(__file__).resolve()


def _api_dir() -> Path:
    for parent in HERE.parents:
        for candidate in (parent, parent / "api"):
            if (candidate / "services" / "workspace_operations.py").is_file():
                return candidate
    raise RuntimeError("api/services/workspace_operations.py não encontrado")


API = _api_dir()
if str(API) not in sys.path:
    sys.path.insert(0, str(API))

from services import workspace_operations as ops  # noqa: E402

MIGRATION = API.parent / "sql" / "migrations" / "172_workspace_reserva_publicacao_esperada.sql"
REPOSITORY = API.parent / "backend-dotnet" / "Orquestra.Infrastructure" / "Drafts" / "SqlDraftRepository.cs"
RUN = "workspace__0f8e2c1a-7b3d-4c5e-9a1b-2c3d4e5f6a7b"
VERSION = "3F2504E0-4F89-11D3-9A0C-0305E82C3301"
HASH = "AB" * 32
TOKEN = "11111111-2222-3333-4444-555555555555"
RUN_PATH = "/api/v1/dags/p/dagRuns/" + RUN
AUTH ={"matricula": "u1", "permissoes": ["tela_pipelines", "tela_jobs", "tela_logs", "acao_executar"]}
PUBLICATION_REFUSALS = [
    "Publicacao alterada desde a exibicao.",
    "Publicacao nao confirmada.",
    "Execucao exige a publicacao confirmada exibida.",
    "Pipeline sem publicacao do workspace.",
]


def body(**extra):
    return {"conf": {"data_referencia": "2026-10-13"}, "dag_run_id": RUN,
            "expected_version_id": VERSION, "expected_content_hash": HASH, **extra}


def sql_error(message, number):
    # Forma do texto do pyodbc: o número do erro do SQL Server vem entre parênteses.
    return Exception(f"('42000', '[42000] [Microsoft][ODBC Driver 18 for SQL Server][SQL Server]{message} ({number}) (SQLExecDirectW)')")


class FakeConnection:
    """Conexão de teste: registra comandos e devolve a linha (ou o erro) da procedure."""

    def __init__(self, row=(TOKEN, 0), error=None):
        self.row, self.error, self.calls, self.commits, self.rollbacks = row, error, [], 0, 0

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        pass

    def reservations(self):
        return [params for sql, params in self.calls if "sp_workspace_reserve_run" in sql]

    def writes(self):
        return [(sql, params) for sql, params in self.calls if "sp_workspace_reserve_run" not in sql]

    def apply(self, sql, params):
        """Efeito do comando no banco de teste; por padrão, nenhum."""


class DurableCommand(FakeConnection):
    """Uma identidade de comando como a 172 a guarda, para o mesmo pedido: a primeira
    reserva grava 'reservado'; repetir devolve o mesmo token como replay. O ack só tem
    efeito com o WHERE de ACKNOWLEDGE_COMMAND (este token, 'reservado', ativo)."""

    def __init__(self, estado=None, ativa=1, run_id=RUN):
        super().__init__()
        self.key, self.estado, self.ativa = ("p", run_id), estado, ativa

    def apply(self, sql, params):
        if "sp_workspace_reserve_run" in sql:
            self.row = (TOKEN, int(self.estado is not None))
            if self.estado is None:
                self.key, self.estado = params[:2], "reservado"
        elif sql == ops.ACKNOWLEDGE_COMMAND and params == (*self.key, TOKEN) and (self.estado, self.ativa) == ("reservado", 1):
            self.estado = "enviado"


class FakeCursor:
    def __init__(self, connection):
        self.connection = connection

    def execute(self, sql, params=()):
        self.connection.calls.append((sql, tuple(params)))
        if self.connection.error is not None and "sp_workspace_reserve_run" in sql:
            raise self.connection.error
        self.connection.apply(sql, tuple(params))
        return self

    def fetchone(self):
        return self.connection.row

    def close(self):
        pass


@pytest.fixture
def database(monkeypatch):
    monkeypatch.setenv("WORKSPACE_PUBLICATIONS_ENABLED", "true")
    state = {"connection": FakeConnection()}
    monkeypatch.setattr(ops, "get_db_conn", lambda: state["connection"])
    return state


# ── Par esperado ────────────────────────────────────────────────────────────

def test_sem_par_a_decisao_fica_com_a_procedure():
    assert ops.expected_publication({"conf": {}, "dag_run_id": RUN}) is None


def test_par_completo_sai_em_minusculas():
    assert ops.expected_publication(body()) == (VERSION.lower(), HASH.lower())


@pytest.mark.parametrize("missing", ops.PUBLICATION_FIELDS)
def test_par_incompleto_e_recusado(missing):
    payload = body()
    del payload[missing]
    with pytest.raises(HTTPException) as caught:
        ops.expected_publication(payload)
    assert caught.value.status_code == 422


@pytest.mark.parametrize("version,content", [
    ("{" + VERSION + "}", HASH),
    (VERSION.replace("-", ""), HASH),
    (VERSION + "\n", HASH),
    (" " + VERSION, HASH),
    (VERSION, HASH[:-1]),
    (VERSION, HASH + "0"),
    (VERSION, "g" * 64),
    (VERSION, HASH[:-1] + "\n"),
    (VERSION, HASH + "\n"),
    (VERSION.lower() + "\n", HASH),
    (VERSION, "٣" * 64),  # dígitos não ASCII
    (None, HASH),
    (VERSION, None),
    (VERSION, 123),
    (["x"], HASH),
])
def test_par_malformado_e_recusado(version, content):
    with pytest.raises(HTTPException) as caught:
        ops.expected_publication(body(expected_version_id=version, expected_content_hash=content))
    assert caught.value.status_code == 422


@pytest.mark.parametrize("field", ops.PUBLICATION_FIELDS)
def test_par_dentro_de_conf_e_recusado(field):
    with pytest.raises(HTTPException) as caught:
        ops.expected_publication(body(conf={"data_referencia": "2026-10-13", field: VERSION}))
    assert caught.value.status_code == 422


def test_metadados_internos_nao_seguem_ao_airflow():
    sent = ops.airflow_run_body(body(logical_date="2026-10-13T00:00:00Z"))
    assert sent == {"conf": {"data_referencia": "2026-10-13"}, "dag_run_id": RUN, "logical_date": "2026-10-13T00:00:00Z"}


# ── Reserva ─────────────────────────────────────────────────────────────────

def test_reserva_leva_o_par_a_procedure(database):
    assert ops.reserve_run("p", RUN, body(), "u1", expected=ops.expected_publication(body())) == (TOKEN, False)
    sql, params = database["connection"].calls[-1]
    assert "@expected_version=?,@expected_hash=?" in sql
    assert params[-2:] == (VERSION.lower(), HASH.lower())
    assert database["connection"].commits == 1


def test_sem_par_a_procedure_recebe_nulos(database):
    ops.reserve_run("p", RUN, {"conf": {}, "dag_run_id": RUN}, "u1")
    assert database["connection"].reservations()[0][-2:] == (None, None)


def test_mesmo_uuid_com_outro_par_e_outro_pedido(database):
    other = body(expected_content_hash="cd" * 32)
    ops.reserve_run("p", RUN, body(), "u1", expected=ops.expected_publication(body()))
    ops.reserve_run("p", RUN, other, "u1", expected=ops.expected_publication(other))
    first, second = database["connection"].reservations()
    assert first[1] == second[1] == RUN
    assert first[2] != second[2]  # request_hash: a procedure recusa a identidade reutilizada


@pytest.mark.parametrize("message", PUBLICATION_REFUSALS)
def test_recusa_de_publicacao_e_409_marcada(database, message):
    database["connection"] = FakeConnection(error=sql_error(message, 51172))
    with pytest.raises(HTTPException) as caught:
        ops.reserve_run("p", RUN, body(), "u1", expected=ops.expected_publication(body()))
    assert caught.value.status_code == 409
    assert caught.value.headers == {"X-Workspace-Conflict": "publication"}
    assert (database["connection"].commits, database["connection"].rollbacks) == (0, 1)


def test_identidade_reutilizada_segue_409_sem_marca(database):
    database["connection"] = FakeConnection(error=sql_error("Identidade de comando reutilizada.", 51146))
    with pytest.raises(HTTPException) as caught:
        ops.reserve_run("p", RUN, body(), "u1", expected=ops.expected_publication(body()))
    assert caught.value.status_code == 409
    assert not caught.value.headers


def test_procedure_sem_os_parametros_novos_falha_fechada(database):
    database["connection"] = FakeConnection(error=sql_error("Procedure or function sp_workspace_reserve_run has too many arguments specified.", 8144))
    with pytest.raises(HTTPException) as caught:
        ops.reserve_run("p", RUN, body(), "u1", expected=ops.expected_publication(body()))
    assert caught.value.status_code == 503


def test_publicacoes_desligadas_com_par_falham_fechadas(monkeypatch):
    # Sem procedure não há com o que comparar: o par alegado não autoriza o envio.
    monkeypatch.setenv("WORKSPACE_PUBLICATIONS_ENABLED", "false")
    monkeypatch.setattr(ops, "get_db_conn", lambda: pytest.fail("não deve consultar o banco"))
    with pytest.raises(HTTPException) as caught:
        ops.reserve_run("p", RUN, body(), "u1", expected=(VERSION.lower(), HASH.lower()))
    assert caught.value.status_code == 503


def test_publicacoes_desligadas_sem_par_seguem_legado(monkeypatch):
    monkeypatch.setenv("WORKSPACE_PUBLICATIONS_ENABLED", "false")
    monkeypatch.setattr(ops, "get_db_conn", lambda: pytest.fail("não deve consultar o banco"))
    assert ops.reserve_run("p", RUN, {"conf": {}, "dag_run_id": RUN}, "u1") == (None, False)


# ── Endpoint /pipeline-runs ─────────────────────────────────────────────────

class FakeAirflow:
    """Cliente do Airflow de teste: só GET. Resposta (status, corpo) ou exceção."""

    def __init__(self, answer=(404, {"detail": "DAGRun not found"})):
        self.answer, self.paths = answer, []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, path):
        self.paths.append(path)
        if isinstance(self.answer, Exception):
            raise self.answer
        status, payload = self.answer
        return httpx.Response(status, text=payload) if isinstance(payload, str) else httpx.Response(status, json=payload)


def invoke(payload, pipeline="p"):
    from routers import execucoes
    return execucoes.workspace_pipeline_run(pipeline_name=pipeline, body=payload, auth=AUTH, authorization="Bearer t")


@pytest.fixture
def endpoint(monkeypatch, database):
    from routers import airflow
    sent = []

    async def trigger(name, payload, user=None):
        sent.append((name, payload))
        return {"dag_run_id": payload["dag_run_id"], "state": "queued"}

    monkeypatch.setattr(airflow, "trigger_dag_run", trigger)
    # Sem a fixture airflow_get, consultar o Airflow é falha do teste.
    monkeypatch.setattr(airflow, "get_airflow_client", lambda: pytest.fail("não deve consultar o Airflow"))

    def call(payload, pipeline="p"):
        return asyncio.run(invoke(payload, pipeline))

    return call, sent


@pytest.fixture
def airflow_get(monkeypatch, endpoint):
    from routers import airflow
    client = FakeAirflow()
    monkeypatch.setattr(airflow, "get_airflow_client", lambda: client)
    return client


def test_envio_ao_airflow_sem_metadados_internos(endpoint, database):
    call, sent = endpoint
    assert call(body()) == {"dag_run_id": RUN, "state": "queued"}
    assert sent == [("p", {"conf": {"data_referencia": "2026-10-13"}, "dag_run_id": RUN})]
    assert database["connection"].reservations()[0][-2:] == (VERSION.lower(), HASH.lower())
    assert database["connection"].writes() == [(ops.ACKNOWLEDGE_COMMAND, ("p", RUN, TOKEN))]


@pytest.mark.parametrize("message", PUBLICATION_REFUSALS)
def test_publicacao_mudou_ou_pendente_antes_da_reserva_nao_envia(endpoint, database, message):
    call, sent = endpoint
    database["connection"] = FakeConnection(error=sql_error(message, 51172))
    with pytest.raises(HTTPException) as caught:
        call(body())
    assert caught.value.status_code == 409
    assert caught.value.headers == {"X-Workspace-Conflict": "publication"}
    assert sent == []


@pytest.mark.parametrize("payload", [
    {k: v for k, v in body().items() if k != "expected_content_hash"},
    body(expected_version_id="nao-e-guid"),
    body(expected_content_hash="AB" * 31),
    body(conf={"expected_version_id": VERSION}),
    body(conf={"expected_content_hash": HASH}),
])
def test_par_incompleto_malformado_ou_em_conf_nao_reserva_nem_envia(endpoint, database, payload):
    call, sent = endpoint
    with pytest.raises(HTTPException) as caught:
        call(payload)
    assert caught.value.status_code == 422
    assert database["connection"].calls == [] and sent == []


def test_replay_com_par_ou_corpo_divergente_nao_envia(endpoint, database):
    call, sent = endpoint
    database["connection"] = FakeConnection(error=sql_error("Identidade de comando reutilizada.", 51146))
    with pytest.raises(HTTPException) as caught:
        call(body(expected_content_hash="cd" * 32))
    assert caught.value.status_code == 409 and sent == []


# ── Replay: só a corrida exata confirmada no Airflow é sucesso ──────────────

UNCONFIRMED = [
    (404, {"detail": "DAGRun not found"}),
    (500, {"detail": "erro interno"}),
    (502, "Bad Gateway"),
    (503, {"detail": "indisponível"}),
    (401, {"detail": "Unauthorized"}),
    httpx.ReadTimeout("timed out"),
    httpx.ConnectError("connection refused"),
    (200, "<html>proxy</html>"),
    (200, [{"dag_id": "p", "dag_run_id": RUN, "state": "queued"}]),
    (200, {"dag_id": "p", "dag_run_id": RUN + "x", "state": "queued"}),
    (200, {"dag_id": "outro", "dag_run_id": RUN, "state": "queued"}),
    (200, {"dag_run_id": RUN, "state": "queued"}),
    (200, {"dag_id": "p", "dag_run_id": RUN, "state": None}),
    (200, {"dag_id": "p", "dag_run_id": RUN, "state": "reserved"}),
    (200, {"dag_id": "p", "dag_run_id": RUN, "state": ["queued"]}),
]


def test_primeira_falha_e_replay_sem_corrida_no_airflow_nunca_e_sucesso(endpoint, database, airflow_get, monkeypatch):
    from routers import airflow
    call, sent = endpoint
    database["connection"] = command = DurableCommand()

    async def unavailable(name, payload, user=None):
        sent.append((name, payload))
        raise HTTPException(502, "Erro ao disparar")

    monkeypatch.setattr(airflow, "trigger_dag_run", unavailable)
    with pytest.raises(HTTPException) as first:
        call(body())
    assert first.value.status_code == 503 and len(sent) == 1
    # Repetir o mesmo pedido: a procedure reconhece o replay; só GET, nunca sucesso sem a corrida.
    for _ in range(2):
        with pytest.raises(HTTPException) as replay:
            call(body())
        assert replay.value.status_code == 503 and "não foi confirmada no Airflow" in replay.value.detail
    assert len(sent) == 1 and airflow_get.paths == [RUN_PATH, RUN_PATH]
    assert (command.estado, command.ativa) == ("reservado", 1) and command.writes() == []


@pytest.mark.parametrize("estado,ativa", [("reservado", 1), ("enviado", 1), ("success", 0)])
@pytest.mark.parametrize("answer", UNCONFIRMED)
def test_replay_sem_confirmacao_exata_nao_reenvia_nem_libera(endpoint, database, airflow_get, answer, estado, ativa):
    call, sent = endpoint
    database["connection"] = command = DurableCommand(estado, ativa)
    airflow_get.answer = answer
    with pytest.raises(HTTPException) as caught:
        call(body())
    assert caught.value.status_code == 503
    assert sent == [] and airflow_get.paths == [RUN_PATH]
    # Nem ack nem liberação: o comando segue como estava para a reconciliação.
    assert (command.estado, command.ativa) == (estado, ativa) and command.writes() == []


@pytest.mark.parametrize("estado,ativa,depois", [("reservado", 1, "enviado"), ("enviado", 1, "enviado"), ("success", 0, "success")])
@pytest.mark.parametrize("state", ops.RUN_STATES)
def test_replay_confirmado_devolve_estado_real_e_ack_cercado(endpoint, database, airflow_get, state, estado, ativa, depois):
    call, sent = endpoint
    database["connection"] = command = DurableCommand(estado, ativa)
    airflow_get.answer = (200, {"dag_id": "p", "dag_run_id": RUN, "state": state, "conf": {"data_referencia": "2026-10-13"}})
    for _ in range(2):
        assert call(body()) == {"dag_run_id": RUN, "state": state}
        assert (command.estado, command.ativa) == (depois, ativa)
    assert sent == [] and airflow_get.paths == [RUN_PATH, RUN_PATH]
    # Ack só pelo texto cercado, com o token da reserva; repetir não muda o comando.
    assert command.writes() == [(ops.ACKNOWLEDGE_COMMAND, ("p", RUN, TOKEN))] * 2


def test_replay_consulta_a_identidade_exata_codificada(endpoint, database, airflow_get):
    call, sent = endpoint
    special = "workspace__a/b ç+1"
    database["connection"] = command = DurableCommand("reservado", run_id=special)
    airflow_get.answer = (200, {"dag_id": "p", "dag_run_id": special, "state": "running"})
    assert call(body(dag_run_id=special)) == {"dag_run_id": special, "state": "running"}
    assert airflow_get.paths == ["/api/v1/dags/p/dagRuns/workspace__a%2Fb%20%C3%A7%2B1"] and command.estado == "enviado"
    # Outra corrida (identidade truncada pelo caminho) não confirma esta.
    command.estado = "reservado"
    airflow_get.answer = (200, {"dag_id": "p", "dag_run_id": "workspace__a", "state": "running"})
    with pytest.raises(HTTPException) as caught:
        call(body(dag_run_id=special))
    assert caught.value.status_code == 503 and command.estado == "reservado" and sent == []


@pytest.mark.parametrize("pipeline,status", [("etl_admin_manage", 403), ("p x", 400)])
def test_replay_mantem_os_gates_do_disparo_antes_de_consultar(endpoint, database, pipeline, status):
    call, sent = endpoint
    database["connection"] = command = DurableCommand("reservado")
    with pytest.raises(HTTPException) as caught:
        call(body(), pipeline=pipeline)
    assert caught.value.status_code == status
    assert sent == [] and command.writes() == [] and command.estado == "reservado"


def test_replay_durante_o_envio_original_nao_duplica(endpoint, database, airflow_get, monkeypatch):
    from routers import airflow
    _, sent = endpoint
    database["connection"] = command = DurableCommand()

    async def scenario():
        released = asyncio.Event()

        async def slow(name, payload, user=None):
            sent.append((name, payload))
            await released.wait()
            return {"dag_run_id": payload["dag_run_id"], "state": "queued"}

        monkeypatch.setattr(airflow, "trigger_dag_run", slow)
        original = asyncio.create_task(invoke(body()))
        while not sent and not original.done():
            await asyncio.sleep(0)
        # O original reservou e está no POST: a repetição só consulta, não reenvia.
        with pytest.raises(HTTPException) as replay:
            await invoke(body())
        released.set()
        return replay.value, await original

    refused, result = asyncio.run(scenario())
    assert refused.status_code == 503 and result == {"dag_run_id": RUN, "state": "queued"}
    assert len(sent) == 1 and airflow_get.paths == [RUN_PATH] and command.estado == "enviado"
    # Depois do envio, a repetição confirma a corrida e devolve o estado real.
    airflow_get.answer = (200, {"dag_id": "p", "dag_run_id": RUN, "state": "running"})
    assert asyncio.run(invoke(body())) == {"dag_run_id": RUN, "state": "running"}
    assert len(sent) == 1


def test_comando_encerrado_em_erro_recusa_replay_e_pede_nova_corrida(endpoint, database):
    call, sent = endpoint
    database["connection"] = FakeConnection(error=sql_error("Comando encerrado sem confirmacao: crie uma nova corrida.", 51146))
    with pytest.raises(HTTPException) as caught:
        call(body())
    assert caught.value.status_code == 409 and "abra uma nova solicitação" in caught.value.detail
    assert not caught.value.headers and sent == [] and database["connection"].rollbacks == 1


def test_recusa_do_reprocessamento_segue_a_mensagem_de_antes(database):
    database["connection"] = FakeConnection(error=sql_error("Comando sem confirmacao: crie uma nova corrida.", 51146))
    with pytest.raises(HTTPException) as caught:
        ops.reserve_run("p", RUN, {"conf": {}, "dag_run_id": RUN}, "u1", reprocess=True)
    assert caught.value.status_code == 409
    assert caught.value.detail == "Existe comando/execução pendente ou a corrida não pertence à versão atual"


def test_publicacoes_desligadas_com_par_nao_reserva_nem_envia(endpoint, database, monkeypatch):
    call, sent = endpoint
    monkeypatch.setenv("WORKSPACE_PUBLICATIONS_ENABLED", "false")
    with pytest.raises(HTTPException) as caught:
        call(body())
    assert caught.value.status_code == 503
    assert database["connection"].reservations() == [] and sent == []


def test_publicacoes_desligadas_sem_par_envia_como_legado(endpoint, database, monkeypatch):
    call, sent = endpoint
    monkeypatch.setenv("WORKSPACE_PUBLICATIONS_ENABLED", "false")
    call({"conf": {"data_referencia": "2026-10-13"}, "dag_run_id": RUN})
    assert database["connection"].reservations() == []
    assert sent == [("p", {"conf": {"data_referencia": "2026-10-13"}, "dag_run_id": RUN})]


# ── Leitura do par no contexto (.NET, contrato de texto) ────────────────────

def _context_source():
    text = REPOSITORY.read_text(encoding="utf-8")
    start = text.index("public Task<PipelineContext> ContextAsync(")
    end = text.index("private sealed record ManagedRead(", start)
    helper = text.index("private static async Task<ManagedRead?> ManagedPublication(")
    return text[start:end], text[helper:text.index("\n    }\n", helper)]


def test_contexto_le_gerido_antes_do_legado_e_nao_mistura_fontes():
    context, _ = _context_source()
    managed = context.index("await ManagedPublication(")
    assert managed < context.index("LegacyFlowReader.ReadAsync(")
    # O legado só é lido quando não há linha gerida.
    assert "else if (stages)" in context[managed:context.index("LegacyFlowReader.ReadAsync(")]
    # Par só sai junto com o desenho da mesma leitura, e só com permissão de etapas.
    assert context.count("versionId = pair.VersionId, contentHash = pair.ContentHash") == 1
    assert "if (stages) published = managed.Pair is { } pair" in context
    assert "if (!stages) draft = null;" in context


def test_contexto_par_vem_de_uma_unica_linha_gerida_confirmada():
    _, helper = _context_source()
    selects = re.findall(r'"SELECT p\.pipeline_name[^"]*"', helper)
    assert len(selects) == 1
    for column in ("p.version_id", "p.pending_operation_id", "p.active_hash", "v.version_id", "v.content_hash", "v.definition_json", "v.layout_json"):
        assert column in selects[0], column
    # Pendente nunca é par; versão lida tem de ser a do ponteiro; hash ativo presente.
    assert "row.IsDBNull(4)" in helper and "!row.IsDBNull(5)" in helper and "row.GetGuid(3) == row.GetGuid(6)" in helper
    assert "Hex64(row.GetString(5)) && Hex64(content)" in helper
    # active_hash (projeção nas tabelas SQL) e content_hash (desenho) são domínios distintos:
    # o hash ativo nunca é comparado com nada nesta leitura.
    assert not re.search(r"GetString\(5\)[^;\n]*(==|!=|Equals)|Equals\([^;\n]*GetString\(5\)", helper)
    # Coluna ou tabela ausente é erro honesto, nunca leitura legada.
    assert re.search(r'catch \(SqlException e\) when \(e\.Number is 208 or 207\) \{ throw new WorkspaceException\(503, "publication_schema_unavailable"', helper)


# ── Ordem das conferências na migration 172 ─────────────────────────────────

def _procedure():
    text = MIGRATION.read_text(encoding="utf-8")
    start = text.index("CREATE OR ALTER PROCEDURE dbo.sp_workspace_reserve_run")
    return text, text[start:text.index("\nGO", start)]


def test_migration_172_confere_o_par_antes_de_replay_insercao_ou_reativacao():
    _, procedure = _procedure()
    locked = procedure.index("dbo.etl_workspace_pipeline p WITH(UPDLOCK,HOLDLOCK)")
    pending = procedure.index("Publicacao nao confirmada")
    required = procedure.index("Execucao exige a publicacao confirmada exibida")
    compare = procedure.index("Publicacao alterada desde a exibicao")
    assert locked < pending < required < compare
    for marker in ("SELECT @token AS command_token,1 AS existing", "INSERT dbo.etl_workspace_comando", "UPDATE dbo.etl_workspace_comando"):
        positions = [match.start() for match in re.finditer(re.escape(marker), procedure)]
        assert positions and min(positions) > compare, marker
    # Replay ativo e inativo exigem o mesmo par gravado no comando.
    assert procedure.count("tipo='execute' AND version_id=@version AND content_hash=@hash") == 2
    assert "@expected_version UNIQUEIDENTIFIER=NULL,@expected_hash VARCHAR(128)=NULL" in procedure


def test_migration_172_recusa_replay_de_comando_encerrado_em_erro_sem_reativar():
    _, procedure = _procedure()
    inactive = procedure.index("-- Replay inativo")
    refusal = procedure.index("Comando encerrado sem confirmacao: crie uma nova corrida.")
    replay = procedure.index("SELECT @token AS command_token,1 AS existing", inactive)
    assert inactive < procedure.index("Identidade de comando reutilizada.") < refusal < replay
    assert "WITH(UPDLOCK,HOLDLOCK) WHERE pipeline_name=@name AND run_id=@run_id AND estado='erro'" in procedure[inactive:refusal]
    # Nada no ramo do replay inativo grava ou reativa o comando.
    assert "UPDATE" not in procedure[inactive:replay] and "INSERT" not in procedure[inactive:replay]


def test_migration_172_preserva_guardas_e_registra_versao_idempotente():
    text, _ = _procedure()
    assert "TRIGGER dbo.tr_workspace_command_publication" not in text
    assert "PROCEDURE dbo.sp_workspace_guard_run" not in text
    assert "WHERE titulo = @titulo" in text and "[SKIP]" in text
