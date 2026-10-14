"""Operação do publicado: mantém gate F4, não concede escrita de configuração."""
import os
import re
import json
import hashlib
from fastapi import HTTPException
from db import get_db_conn

# Par da publicação confirmada que a tela exibia ao abrir o pedido de execução.
# Campos próprios do corpo, fora de `conf`; conferido pela procedure de reserva e
# nunca enviado ao Airflow.
PUBLICATION_FIELDS = ("expected_version_id", "expected_content_hash")
_VERSION_ID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
_CONTENT_HASH = re.compile(r"[0-9a-fA-F]{64}")


def expected_publication(body: dict):
    """(versão, hash) esperados em minúsculas, ou None sem o par.

    Par incompleto, malformado ou dentro de `conf` é recusado antes de qualquer
    reserva. Sem o par, a procedure recusa pipeline gerenciado.
    """
    conf = body.get("conf")
    if isinstance(conf, dict) and any(field in conf for field in PUBLICATION_FIELDS):
        raise HTTPException(422, "A publicação esperada vai fora dos parâmetros da execução")
    if not any(field in body for field in PUBLICATION_FIELDS):
        return None
    version, content = (body.get(field) for field in PUBLICATION_FIELDS)
    if not (isinstance(version, str) and _VERSION_ID.fullmatch(version) and isinstance(content, str) and _CONTENT_HASH.fullmatch(content)):
        raise HTTPException(422, "Publicação esperada incompleta ou inválida")
    return version.lower(), content.lower()


def airflow_run_body(body: dict) -> dict:
    """Só conf, data lógica e identidade seguem ao Airflow; o par esperado é interno."""
    return {key: body[key] for key in ("conf", "logical_date", "dag_run_id") if key in body}


def check_managed_run(pipeline: str, run_id: str = "", *, reprocess: bool = False, cascata: bool = False):
    if os.getenv("WORKSPACE_PUBLICATIONS_ENABLED", "false").lower() != "true":
        return
    connection = get_db_conn()
    cursor = connection.cursor()
    try:
        if not cursor.execute("SELECT OBJECT_ID('dbo.etl_workspace_pipeline','U')").fetchone()[0]:
            raise HTTPException(503, "Operação indisponível; aplique migration 144")
        row = cursor.execute("SELECT p.version_id,v.content_hash,p.pending_operation_id FROM dbo.etl_workspace_pipeline p LEFT JOIN dbo.etl_workspace_versao v ON v.version_id=p.version_id WHERE p.pipeline_name=?", (pipeline,)).fetchone()
        if not row:
            return
        if row[2] is not None or row[0] is None:
            raise HTTPException(409, "Aguarde a confirmação da publicação antes de operar")
        if reprocess:
            bound = cursor.execute("SELECT version_id,content_hash FROM dbo.etl_workspace_execucao WHERE pipeline_name=? AND run_id=?", (pipeline, run_id)).fetchone()
            if cascata or not bound or str(bound[0]).lower() != str(row[0]).lower() or bound[1] != row[1]:
                raise HTTPException(409, "Reprocessamento exige corrida da versão publicada atual, sem cascata entre pipelines")
        else:
            active = cursor.execute("SELECT TOP 1 1 FROM dbo.etl_workspace_execucao WHERE pipeline_name=? AND ativa=1", (pipeline,)).fetchone()
            if active:
                raise HTTPException(409, "Já existe uma execução ativa deste pipeline")
            reservation = cursor.execute("SELECT TOP 1 1 FROM dbo.etl_pipeline_execucao WHERE pipeline_name=? AND status IN('EXECUTANDO','RUNNING','QUEUED','AGUARDANDO','AGUARDANDO_DEPENDENCIA')", (pipeline,)).fetchone()
            if reservation:
                raise HTTPException(409, "Existe uma execução ou reserva pendente deste pipeline")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(503, "Consulta da operação indisponível") from None
    finally:
        cursor.close()
        connection.close()


def reserve_run(pipeline: str, run_id: str, body: dict, actor: str, *, reprocess: bool = False, expected: tuple[str, str] | None = None):
    # Publicações desligadas: não há guarda nem procedure para conferir o par. Pedido
    # legado sem par segue sem reserva; pedido que alega uma publicação confirmada
    # falha fechado, porque o par do chamador sozinho não prova nada.
    if os.getenv("WORKSPACE_PUBLICATIONS_ENABLED", "false").lower() != "true":
        if expected is not None:
            raise HTTPException(503, "Conferência da publicação indisponível; nada foi reservado nem enviado")
        return None, False
    # O hash do pedido cobre o par: mesmo identificador com outra publicação é outro pedido.
    checksum = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
    version, content = expected or (None, None)
    connection = cursor = None
    try:
        connection = get_db_conn(); cursor = connection.cursor()
        enrollment_enabled = os.getenv("EOC_ALERT_ENROLLMENT_ENABLED", "false").lower() == "true"
        if enrollment_enabled:
            # O COMMIT interno da procedure encerra só o nível aninhado;
            # a transação externa conserva reserva + snapshot até o commit.
            cursor.execute("IF @@TRANCOUNT=0 BEGIN TRANSACTION")
        row = cursor.execute("EXEC dbo.sp_workspace_reserve_run @name=?,@run_id=?,@request_hash=?,@actor=?,@reprocess=?,@expected_version=?,@expected_hash=?", (pipeline, run_id, checksum, actor, int(reprocess), version, content)).fetchone()
        if enrollment_enabled and row[0]:
            from services.alert_enrollment import enroll_command
            enroll_command(cursor, pipeline, run_id, str(row[0]), existing=bool(row[1]))
        connection.commit()
        return str(row[0]) if row[0] else None, bool(row[1])
    except HTTPException:
        if connection:
            connection.rollback()
        raise
    except Exception as error:
        if connection:
            connection.rollback()
        if "51172" in str(error):
            # Publicação mudou, pendente ou não informada: nada reservado nem enviado.
            raise HTTPException(409, "A publicação confirmada mudou, está pendente ou não foi informada; nada foi reservado", headers={"X-Workspace-Conflict": "publication"}) from None
        if "51146" in str(error) and "Comando encerrado sem confirmacao" in str(error):
            # Comando encerrado em 'erro' (sem corrida no Airflow): o pedido não é repetido nem reativado.
            raise HTTPException(409, "Esta solicitação foi encerrada sem corrida confirmada no Airflow e não é repetida; abra uma nova solicitação para criar outra corrida") from None
        if "51146" in str(error) or "2601" in str(error) or "2627" in str(error):
            raise HTTPException(409, "Existe comando/execução pendente ou a corrida não pertence à versão atual") from None
        raise HTTPException(503, "Reserva da operação indisponível; aplique as migrations 146 e 172") from None
    finally:
        if cursor: cursor.close()
        if connection: connection.close()


# Ack cercado: só o comando desta reserva (token), ainda 'reservado' e ativo, passa a
# 'enviado'. Repetir não muda nada e comando encerrado não é reaberto.
ACKNOWLEDGE_COMMAND = """UPDATE dbo.etl_workspace_comando SET estado='enviado',atualizada_em=SYSUTCDATETIME() WHERE pipeline_name=? AND run_id=? AND command_token=? AND estado='reservado' AND ativa=1"""
# Estados que o Airflow só informa para uma corrida que existe.
RUN_STATES = ("queued", "running", "success", "failed")


def acknowledge_run(pipeline: str, run_id: str, token: str | None):
    if not token:
        return
    connection = get_db_conn(); cursor = connection.cursor()
    try:
        cursor.execute(ACKNOWLEDGE_COMMAND, (pipeline, run_id, token))
        connection.commit()
    finally:
        cursor.close(); connection.close()


async def confirm_run(client, pipeline: str, run_id: str) -> str:
    """Estado real da corrida exata (pipeline e identificador) no Airflow.

    Só GET, nunca novo POST. Consulta indisponível, 404, estado desconhecido ou
    identidade divergente não confirmam: 503 sem tocar a reserva, que segue para
    a reconciliação.
    """
    from urllib.parse import quote
    try:
        response = await client.get("/api/v1/dags/" + quote(pipeline, safe="") + "/dagRuns/" + quote(run_id, safe=""))
        run = response.json() if response.is_success else None
    except Exception:
        run = None
    if not (isinstance(run, dict) and run.get("dag_id") == pipeline and run.get("dag_run_id") == run_id and run.get("state") in RUN_STATES):
        raise HTTPException(503, "A corrida desta solicitação não foi confirmada no Airflow; nada foi reenviado e a reserva segue para conferência. Tente novamente com o mesmo identificador; se a conferência não encontrar a corrida, abra uma nova solicitação")
    return run["state"]


def execution_version(pipeline: str, run_id: str):
    if not run_id or os.getenv("WORKSPACE_PUBLICATIONS_ENABLED", "false").lower() != "true":
        return None
    connection = get_db_conn(); cursor = connection.cursor()
    try:
        row = cursor.execute("SELECT v.version_id,v.numero,v.definition_json,v.layout_json FROM dbo.etl_workspace_execucao e JOIN dbo.etl_workspace_versao v ON v.version_id=e.version_id WHERE e.pipeline_name=? AND e.run_id=?", (pipeline, run_id)).fetchone()
        return {"versionId": str(row[0]), "number": row[1], "definition": json.loads(row[2]), "layout": json.loads(row[3])} if row else None
    finally:
        cursor.close(); connection.close()


async def reconcile_commands(client):
    from urllib.parse import quote
    connection = get_db_conn(); cursor = connection.cursor()
    try:
        if not cursor.execute("SELECT OBJECT_ID('dbo.etl_workspace_comando','U')").fetchone()[0]:
            return
        commands = [tuple(row) for row in cursor.execute("SELECT TOP(100) pipeline_name,run_id,command_token,estado,DATEDIFF(second,solicitada_em,SYSUTCDATETIME()) FROM dbo.etl_workspace_comando WHERE ativa=1 ORDER BY solicitada_em").fetchall()]
    finally:
        cursor.close(); connection.close()
    for name, run_id, token, previous, age in commands:
        response = await client.get("/api/v1/dags/" + quote(name, safe="") + "/dagRuns/" + quote(run_id, safe=""))
        state = response.json().get("state") if response.is_success else None
        next_state = None
        if state in {"queued", "running"}: next_state = "enviado"
        elif state in {"success", "failed"} and previous == "enviado": next_state = state
        elif age >= 90 and previous == "reservado" and (response.status_code == 404 or state in {"success", "failed"}): next_state = "erro"
        # Falha de consulta não libera a reserva; callback antigo não fecha comando novo.
        if next_state:
            connection = get_db_conn(); cursor = connection.cursor()
            try:
                cursor.execute("UPDATE dbo.etl_workspace_comando SET estado=?,ativa=?,atualizada_em=SYSUTCDATETIME() WHERE pipeline_name=? AND run_id=? AND command_token=? AND estado=? AND ativa=1", (next_state, int(next_state == "enviado"), name, run_id, str(token), previous))
                connection.commit()
            finally:
                cursor.close(); connection.close()
