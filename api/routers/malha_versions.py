"""F16: consulta autenticada, sem qualquer superfície de mutação."""
from contextlib import closing
from uuid import UUID

from fastapi import APIRouter, Depends, Path

from db import get_db_conn
from deps import get_current_user
from services import malha_versions

router = APIRouter(tags=['malhas'], dependencies=[Depends(get_current_user)])


@router.get('/malhas/{malha_name}/versionamento')
def capability(malha_name: str):
    with closing(get_db_conn()) as conn:
        return malha_versions.capability(conn.cursor(), malha_name)


@router.get('/malhas/{malha_name}/versoes/{version_id}')
def version(malha_name: str, version_id: UUID):
    with closing(get_db_conn()) as conn:
        return malha_versions.version(conn.cursor(), malha_name, version_id)


@router.get('/malhas/{malha_name}/corridas/{corrida_id}/definicao')
def corrida(malha_name: str, corrida_id: int = Path(ge=1, le=9223372036854775807)):
    with closing(get_db_conn()) as conn:
        return malha_versions.corrida(conn.cursor(), malha_name, corrida_id)
