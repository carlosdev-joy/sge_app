"""Operação do publicado: mantém gate F4, não concede escrita de configuração."""
import os
import json
import hashlib
from fastapi import HTTPException
from db import get_db_conn


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


def reserve_run(pipeline: str, run_id: str, body: dict, actor: str, *, reprocess: bool = False):
    if os.getenv("WORKSPACE_PUBLICATIONS_ENABLED", "false").lower() != "true":
        return None, False
    checksum = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
    connection = cursor = None
    try:
        connection = get_db_conn(); cursor = connection.cursor()
        row = cursor.execute("EXEC dbo.sp_workspace_reserve_run @name=?,@run_id=?,@request_hash=?,@actor=?,@reprocess=?", (pipeline, run_id, checksum, actor, int(reprocess))).fetchone()
        connection.commit()
        return str(row[0]) if row[0] else None, bool(row[1])
    except Exception as error:
        if connection:
            connection.rollback()
        if "51146" in str(error) or "2601" in str(error) or "2627" in str(error):
            raise HTTPException(409, "Existe comando/execução pendente ou a corrida não pertence à versão atual") from None
        raise HTTPException(503, "Reserva da operação indisponível; aplique migration 146") from None
    finally:
        if cursor: cursor.close()
        if connection: connection.close()


def acknowledge_run(pipeline: str, run_id: str, token: str | None):
    if not token:
        return
    connection = get_db_conn(); cursor = connection.cursor()
    try:
        cursor.execute("UPDATE dbo.etl_workspace_comando SET estado='enviado',atualizada_em=SYSUTCDATETIME() WHERE pipeline_name=? AND run_id=? AND command_token=? AND estado='reservado' AND ativa=1", (pipeline, run_id, token))
        connection.commit()
    finally:
        cursor.close(); connection.close()


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
