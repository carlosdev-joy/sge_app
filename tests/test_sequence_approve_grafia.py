"""
Canonização da grafia no import .dsx (POST /sequence/approve).

Origem do incidente 2026-08-01: a sp_etl_seq_import_approve grava os jobs com
COALESCE(pipeline_name_override, seq_name). Quando o pipeline JÁ existia com
outra grafia, o upsert do cabeçalho atualiza a linha registrada (colação CI),
mas os jobs nascem com a grafia NOVA do import — e a dag_factory
(case-sensitive) passa a enxergar um "pipeline sem nenhuma etapa".

A correção grava a grafia REGISTRADA como pipeline_name_override ANTES do EXEC
da SP, para que jobs/lineage nasçam com a grafia oficial.

Padrão de test_finalizacao.py: TestClient do conftest, get_db_conn mockado em
routers.sequence e autenticação via dependency_overrides.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()
os.environ.setdefault("MSSQL_CONN_STR", "__mock__")
from api.main import app as _app  # noqa: F401  (ordem de import — ver test_copias.py)

from deps import PERM_EDITAR, get_current_user

IMPORT_ID      = 7
GRAFIA_IMPORT  = "SeqSsdVida6Sinistro"    # seq_name vinda do .dsx
GRAFIA_OFICIAL = "SEQSSDVIDA6SINISTRO"    # registrada em etl_pipeline


class _FakeCursorSeq:
    """Simula o staging do import: o COALESCE devolve o override quando o
    UPDATE de canonização rodou (estado mantido em ``override``), como o banco
    faria dentro da mesma transação."""

    def __init__(self, seq_name: str, oficial: str | None):
        self.seq_name = seq_name
        self.oficial = oficial
        self.override: str | None = None
        self.executed: list[tuple[str, tuple]] = []
        self._last = ""

    def execute(self, sql, params=None):
        self._last = sql
        p = tuple(params) if params is not None else ()
        self.executed.append((sql, p))
        if "SET pipeline_name_override = ?" in sql:
            self.override = p[0]

    def fetchone(self):
        if "SELECT id, seq_name, project_name, status" in self._last:
            return (IMPORT_ID, self.seq_name, "PROJ_X", "pendente_aprovacao")
        if "COALESCE(pipeline_name_override, seq_name)" in self._last:
            return (self.override or self.seq_name,)
        if "FROM dbo.etl_pipeline WHERE pipeline_name" in self._last:
            return (self.oficial,) if self.oficial else None
        return None

    def fetchall(self):
        return []

    def close(self):
        pass


def _mock_conn(cur):
    conn = MagicMock()
    conn.cursor.return_value = cur
    return conn


@pytest.fixture
def auth_editar(app):
    app.dependency_overrides[get_current_user] = lambda: {
        "matricula": "DEV1", "perfil": "desenvolvedor", "permissoes": [PERM_EDITAR],
    }
    yield
    app.dependency_overrides.pop(get_current_user, None)


def _approve(client, cur, body=None):
    with patch("routers.sequence.get_db_conn", return_value=_mock_conn(cur)):
        return client.post("/sequence/approve", json={"import_id": IMPORT_ID, **(body or {})})


def test_approve_canoniza_antes_da_sp(client, auth_editar):
    """Pipeline já registrado com outra grafia → o override recebe a grafia
    REGISTRADA antes do EXEC da SP (é ela que a SP usa para gravar os jobs)."""
    cur = _FakeCursorSeq(GRAFIA_IMPORT, oficial=GRAFIA_OFICIAL)
    r = _approve(client, cur)
    assert r.status_code == 200
    assert r.json()["pipeline_name"] == GRAFIA_OFICIAL

    i_upd = next(i for i, (s, p) in enumerate(cur.executed)
                 if "SET pipeline_name_override = ?" in s
                 and p == (GRAFIA_OFICIAL, IMPORT_ID))
    i_exec = next(i for i, (s, _) in enumerate(cur.executed)
                  if "sp_etl_seq_import_approve" in s)
    assert i_upd < i_exec, "a canonização precisa acontecer ANTES da SP gravar os jobs"


def test_approve_pos_sp_usa_grafia_oficial(client, auth_editar):
    """Os UPDATEs de etl_pipeline após a SP (flags/start_date) também saem com
    a grafia registrada — o COALESCE relido já devolve o override canonizado."""
    cur = _FakeCursorSeq(GRAFIA_IMPORT, oficial=GRAFIA_OFICIAL)
    assert _approve(client, cur).status_code == 200
    upd_pipeline = [(s, p) for s, p in cur.executed
                    if s.startswith("UPDATE dbo.etl_pipeline SET")]
    assert upd_pipeline
    assert all(p[-1] == GRAFIA_OFICIAL for _, p in upd_pipeline)


def test_approve_sem_registro_previo_mantem_grafia_do_import(client, auth_editar):
    """Pipeline novo (a SP o cria) → a grafia do import é a oficial e nenhum
    override de canonização é gravado."""
    cur = _FakeCursorSeq(GRAFIA_IMPORT, oficial=None)
    r = _approve(client, cur)
    assert r.status_code == 200
    assert r.json()["pipeline_name"] == GRAFIA_IMPORT
    assert not any("SET pipeline_name_override = ?" in s for s, _ in cur.executed)


def test_approve_grafia_identica_nao_grava_override(client, auth_editar):
    """Grafia igual à registrada → sem UPDATE inútil no staging."""
    cur = _FakeCursorSeq(GRAFIA_OFICIAL, oficial=GRAFIA_OFICIAL)
    r = _approve(client, cur)
    assert r.status_code == 200
    assert r.json()["pipeline_name"] == GRAFIA_OFICIAL
    assert not any("SET pipeline_name_override = ?" in s for s, _ in cur.executed)
