"""Recusa HTTP antes dos efeitos; triggers SQL e gate do motor são a autoridade.

Instalada somente nos routers do cadastro/execução legado, nunca no adapter.
"""
import os
from fastapi import HTTPException, Request
from db import get_db_conn
from deps import get_current_user


async def legacy_workspace_guard(request: Request):
    if request.method in {"GET", "HEAD", "OPTIONS"} or os.getenv("WORKSPACE_PUBLICATIONS_ENABLED", "false").lower() != "true":
        return
    await get_current_user(request.headers.get("authorization"))
    names = {str(value) for key, value in request.path_params.items() if key in {"pipeline_name", "pipeline", "dag_id", "name"}}
    names.update(request.query_params.getlist("pipeline_name"))
    if request.headers.get("content-type", "").startswith("application/json"):
        try:
            body = await request.json()
        except ValueError:
            return
        def collect(value, depth=0):
            if depth > 8:
                raise HTTPException(422, "Estrutura excede limite de profundidade")
            if isinstance(value, dict):
                for key, item in value.items():
                    if key in {"pipeline_name", "pipeline", "dag_id"} and isinstance(item, str):
                        names.add(item)
                    elif key == "pipelines" and isinstance(item, list):
                        names.update(item for item in item if isinstance(item, str))
                    elif isinstance(item, (dict, list)):
                        collect(item, depth + 1)
            elif isinstance(value, list):
                for item in value:
                    collect(item, depth + 1)
        collect(body)
    if len(names) > 500:
        raise HTTPException(422, "Lote excede limite de pipelines")
    if not names:
        return
    runtime = "/airflow/" in request.url.path or "/execucoes/" in request.url.path or request.url.path.endswith("/pipeline-runs")
    connection = get_db_conn()
    cursor = connection.cursor()
    try:
        if not cursor.execute("SELECT OBJECT_ID('dbo.etl_workspace_pipeline','U')").fetchone()[0]:
            raise HTTPException(503, "Aplique migration 144 antes de habilitar publicações")
        for name in names:
            row = cursor.execute("SELECT pending_operation_id FROM dbo.etl_workspace_pipeline WHERE pipeline_name=?", (name,)).fetchone()
            if row and (not runtime or row[0] is not None):
                raise HTTPException(409, "Pipeline gerido pelo workspace; publique por ele e aguarde a confirmação antes de operar")
    finally:
        cursor.close()
        connection.close()
