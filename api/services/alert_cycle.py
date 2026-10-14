"""Fence durável para Clear. Módulo interno; não ativa capacidade/rotas/envio.

Um Clear é reservado e commitado ANTES do POST. Pending/Unknown bloqueiam
autoridade; crash ou timeout nunca autorizam repetir POST ou inferir geração
pelo polling. Somente resposta inequívoca confirma/rejeita a operação.
O produtor deve usar locked_cycle na MESMA transação do evento/intenção.
"""
import hashlib
import json
from uuid import UUID, uuid4
from urllib.parse import quote
from contextlib import contextmanager

from fastapi import HTTPException
from db import managed_conn


@contextmanager
def cycle_connection(factory=None):
    if factory is None:
        with managed_conn() as pair:
            yield pair
        return
    conn = factory()
    cur = None
    try:
        cur = conn.cursor()
        yield conn, cur
    finally:
        if cur is not None:
            cur.close()
        conn.close()


def unavailable():
    return HTTPException(503, {'code': 'alert_cycle_unavailable',
                              'detail': 'Geração indisponível; confira migration 188_eoc_f13_geracao_clear.'})


def conflict(code):
    return HTTPException(409, {'code': code, 'detail': 'Ciclo de alerta não reconciliado.'})


def run_key(pipeline, run):
    for value, limit in ((pipeline, 200), (run, 250)):
        if (not isinstance(value, str) or not value
                or any(ord(c) < 32 or ord(c) == 127 for c in value)):
            raise conflict('alert_cycle_identity')
        try:
            if len(value.encode('utf-16-le')) // 2 > limit:
                raise conflict('alert_cycle_identity')
        except UnicodeError:
            raise conflict('alert_cycle_identity') from None
    return hashlib.sha256(json.dumps([pipeline, run], ensure_ascii=False,
                                    separators=(',', ':')).encode()).hexdigest()


def locked_cycle(cur, pipeline, run):
    """Não cria coorte implicitamente. Lock transacional compartilhado com Clear.

    Retorna (key, generation, pending_clear), ou None para run não matriculado.
    O chamador só pode produzir se pending_clear for NULL, com este lock retido.
    """
    key = run_key(pipeline, run)
    schema = cur.execute("SELECT OBJECT_ID('dbo.etl_alert_cycle','U'),"
                         "OBJECT_ID('dbo.etl_alert_clear','U')").fetchone()
    if not schema or not all(schema):
        raise unavailable()
    lock = cur.execute(
        "IF @@TRANCOUNT=0 BEGIN TRANSACTION; DECLARE @r INT; "
        "EXEC @r=sys.sp_getapplock @Resource=?,@LockMode='Exclusive',"
        "@LockOwner='Transaction',@LockTimeout=10000; SELECT @r",
        ('eoc-cycle:' + key,)).fetchone()
    if not lock or lock[0] < 0:
        raise unavailable()
    row = cur.execute(
        "SELECT pipeline_name,run_id,generation,pending_clear FROM dbo.etl_alert_cycle "
        "WITH (UPDLOCK) WHERE run_key=?", (key,)).fetchone()
    if row is None:
        return None
    if row[0] != pipeline or row[1] != run:
        raise conflict('alert_cycle_identity')
    return key, row[2], row[3]


def begin_clear(pipeline, run, *, original=None, from_execution=False, connection_factory=None):
    """Reserva somente runs da coorte. Não matricula legado/backfill.

    None indica legado. Reserva existente recusa inclusive após restart: nenhum
    worker ganha permissão para repetir POST com a mesma intenção ambígua.
    """
    try:
        with cycle_connection(connection_factory) as (conn, cur):
            if from_execution:
                cur.execute("SELECT OBJECT_ID('dbo.etl_alert_cycle','U')")
                schema = cur.fetchone()
                if not schema or not schema[0]:
                    conn.commit()
                    return None  # banco anterior à migration188: legado
            cycle = locked_cycle(cur, pipeline, run)
            if cycle is None:
                if original is not None:
                    raise conflict('alert_enrollment_legacy_replay')
                conn.commit()
                return None
            key, generation, pending = cycle
            if pending is not None:
                raise conflict('alert_clear_pending')
            if generation >= 2147483647:
                raise conflict('alert_generation_exhausted')
            if from_execution:
                row = cur.execute(
                    "SELECT v.version_id,v.definition_json FROM dbo.etl_workspace_execucao e "
                    "JOIN dbo.etl_workspace_versao v ON v.version_id=e.version_id "
                    "WHERE e.pipeline_name=? AND e.run_id=?", (pipeline, run)).fetchone()
                if not row:
                    raise conflict('alert_enrollment_original_conflict')
                original = (str(row[0]), json.loads(row[1]))
            if original is not None:
                # Snapshot e reserva compartilham a conexão/lock até commit.
                # Validar numa conexão anterior permitiria outro Clear entre
                # a conferência da geração e a alteração dos parâmetros.
                from services.alert_enrollment import validate_reprocess_snapshot
                version_id, definition = original
                validate_reprocess_snapshot(cur, pipeline, run, version_id, definition)
            operation = str(uuid4())
            cur.execute("INSERT dbo.etl_alert_clear (id,run_key,base_generation) VALUES (?,?,?)",
                        (operation, key, generation))
            cur.execute("UPDATE dbo.etl_alert_cycle SET pending_clear=?,updated_at=SYSUTCDATETIME() "
                        "WHERE run_key=?", (operation, key))
            conn.commit()
            return operation
    except HTTPException:
        raise
    except Exception:
        raise unavailable() from None


def begin_reprocess_clear(pipeline, run, version_id, definition):
    """Reserva a coorte original antes de qualquer escrita de overrides.

    Não lê a publicação atual, não matricula legado e não faz POST. O chamador
    deve obter versão/definição da execução original, não do corpo HTTP.
    Uma falha local posterior exige rejeição explícita antes de liberar fence;
    depois da rede, somente prova inequívoca permite essa rejeição.
    """
    return begin_clear(pipeline, run, original=(version_id, definition))


def finish_clear(pipeline, run, operation, outcome):
    """Confirmed/Rejected só por prova inequívoca do transporte.

    Unknown/Pending sobrevivem crash e não expiram. Recuperação de Unknown exige
    prova externa específica; ausência de tarefa running não prova recusa.
    Repetir confirmação é idempotente; resposta de reserva velha não solta outra.
    """
    if outcome not in ('Confirmed', 'Rejected', 'Unknown'):
        raise conflict('alert_clear_outcome')
    try:
        operation = str(UUID(str(operation)))
    except (ValueError, TypeError, AttributeError):
        raise conflict('alert_clear_operation') from None
    try:
        with managed_conn() as (conn, cur):
            cycle = locked_cycle(cur, pipeline, run)
            if cycle is None:
                raise conflict('alert_cycle_missing')
            key, generation, pending = cycle
            row = cur.execute("SELECT run_key,base_generation,state FROM dbo.etl_alert_clear "
                              "WITH (UPDLOCK) WHERE id=?", (operation,)).fetchone()
            if row is None or row[0] != key:
                raise conflict('alert_clear_operation')
            base, state = row[1], row[2]
            if state in ('Confirmed', 'Rejected'):
                if state != outcome:
                    raise conflict('alert_clear_outcome_conflict')
                conn.commit()
                return base + (state == 'Confirmed')
            if str(pending).lower() != operation or base != generation:
                raise conflict('alert_clear_stale')
            cur.execute("UPDATE dbo.etl_alert_clear SET state=?,updated_at=SYSUTCDATETIME() WHERE id=?",
                        (outcome, operation))
            if outcome != 'Unknown':
                generation += outcome == 'Confirmed'
                cur.execute("UPDATE dbo.etl_alert_cycle SET generation=?,pending_clear=NULL,"
                            "updated_at=SYSUTCDATETIME() WHERE run_key=?", (generation, key))
            conn.commit()
            return generation
    except HTTPException:
        raise
    except Exception:
        raise unavailable() from None


async def post_clear(client, pipeline, run, body):
    """Clear de coorte já matriculada; chamador resolveu identidade e corpo.

    Reserva antes da rede. Qualquer exceção, cancelamento ou resposta sem prova
    inequívoca mantém Unknown/Pending. Nunca repete o POST automaticamente.
    O chamador legado só deve usar este caminho após verificar a coorte.
    """
    validate_clear_body(run, body)
    operation = begin_clear(pipeline, run)
    if operation is None:
        raise conflict('alert_cycle_missing')
    return await _post_clear(client, pipeline, run, body, operation)


def validate_clear_body(run, body):
    if (not isinstance(body, dict) or body.get('dag_run_id') != run
            or body.get('dry_run') is not False
            or any(body.get(k) is not False for k in
                   ('include_past', 'include_future', 'include_upstream'))):
        raise conflict('alert_clear_scope')


def claim_clear_send(pipeline, run, operation):
    """Permissão de envio única: Unknown persistido antes da rede.

    Crash entre claim e POST é conservador: a intenção permanece bloqueada.
    Nenhum replay do mesmo token ganha nova permissão de envio.
    """
    try:
        operation = str(UUID(str(operation)))
    except (ValueError, TypeError, AttributeError):
        raise conflict('alert_clear_operation') from None
    try:
        with managed_conn() as (conn, cur):
            cycle = locked_cycle(cur, pipeline, run)
            if cycle is None:
                raise conflict('alert_cycle_missing')
            key, generation, pending = cycle
            row = cur.execute(
                "SELECT run_key,base_generation,state FROM dbo.etl_alert_clear "
                "WITH (UPDLOCK) WHERE id=?", (operation,)).fetchone()
            if (not row or row[0] != key or row[1] != generation
                    or str(pending).lower() != operation):
                raise conflict('alert_clear_stale')
            if row[2] != 'Pending':
                raise conflict('alert_clear_already_sent')
            cur.execute("UPDATE dbo.etl_alert_clear SET state='Unknown',"
                        "updated_at=SYSUTCDATETIME() WHERE id=?", (operation,))
            conn.commit()
    except HTTPException:
        raise
    except Exception:
        raise unavailable() from None


async def post_reserved_clear(client, pipeline, run, body, operation):
    """Envia uma reserva original já commitada antes dos overrides."""
    validate_clear_body(run, body)
    claim_clear_send(pipeline, run, operation)
    return await _post_clear(client, pipeline, run, body, operation)


async def _post_clear(client, pipeline, run, body, operation):
    try:
        response = await client.post(
            f"/api/v1/dags/{quote(pipeline, safe='')}/clearTaskInstances", json=body)
        # 5xx/proxy podem ocorrer depois do efeito no Airflow. Mesmo um 2xx
        # sem corpo válido não certifica o contrato de Clear.
        if response.is_success:
            payload = response.json()
            if (not isinstance(payload, dict)
                    or not isinstance(payload.get('task_instances'), list)
                    or not payload['task_instances']
                    or any(not isinstance(row, dict)
                           or row.get('dag_id') != pipeline
                           or row.get('dag_run_id') != run
                           or not isinstance(row.get('task_id'), str)
                           or not row['task_id']
                           for row in payload['task_instances'])):
                raise ValueError('invalid_clear_response')
            outcome = 'Confirmed'
        elif response.status_code in (400, 401, 403, 404, 405, 422):
            outcome = 'Rejected'
        else:
            outcome = 'Unknown'
    except BaseException:
        # Cancelamento também é ambíguo. Falha de persistência deixa Pending,
        # que continua bloqueando a autoridade e futuras reservas.
        finish_clear(pipeline, run, operation, 'Unknown')
        raise
    finish_clear(pipeline, run, operation, outcome)
    return response


def reject_unsent_clear(pipeline, run, operation, *, compensate=None):
    """Libera somente Pending; Unknown/Confirmed nunca autorizam compensação.

    Retorna True só quando há prova durável de que o POST não foi autorizado
    ou foi recusado. Falha de banco preserva fence e overrides.
    """
    try:
        operation = str(UUID(str(operation)))
        with managed_conn() as (conn, cur):
            cycle = locked_cycle(cur, pipeline, run)
            if cycle is None:
                return False
            key, generation, pending = cycle
            row = cur.execute(
                "SELECT run_key,base_generation,state FROM dbo.etl_alert_clear "
                "WITH (UPDLOCK) WHERE id=?", (operation,)).fetchone()
            if not row or row[0] != key or row[1] != generation:
                return False
            if row[2] == 'Rejected':
                if pending is not None:
                    return False
                if compensate is not None:
                    compensate(cur)
                conn.commit()
                return True
            if row[2] != 'Pending' or str(pending).lower() != operation:
                return False
            cur.execute("UPDATE dbo.etl_alert_clear SET state='Rejected',"
                        "updated_at=SYSUTCDATETIME() WHERE id=?", (operation,))
            cur.execute("UPDATE dbo.etl_alert_cycle SET pending_clear=NULL,"
                        "updated_at=SYSUTCDATETIME() WHERE run_key=?", (key,))
            if compensate is not None:
                compensate(cur)
            conn.commit()
            return True
    except Exception:
        return False


def begin_rerun_clear(pipeline, run, *, connection_factory=None):
    """Coorte persistida é autoridade mesmo se a flag de matrícula foi desligada.

    Consulta a execução original sob o lock da reserva. Sem coorte permanece
    legado; coorte sem versão original falha fechado, sem alterar overrides.
    """
    if not run:
        try:
            with cycle_connection(connection_factory) as (conn, cur):
                cur.execute("SELECT OBJECT_ID('dbo.etl_alert_cycle','U')")
                schema = cur.fetchone()
                if schema and schema[0]:
                    cur.execute("SELECT TOP(1) run_key FROM dbo.etl_alert_cycle "
                                "WHERE pipeline_name=?", (pipeline,))
                    row = cur.fetchone()
                    if row:
                        raise conflict('alert_clear_run_required')
                conn.commit()
                return None
        except HTTPException:
            raise
        except Exception:
            raise unavailable() from None
    return begin_clear(pipeline, run, from_execution=True, connection_factory=connection_factory)
