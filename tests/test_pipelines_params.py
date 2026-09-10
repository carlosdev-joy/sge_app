"""
Parâmetros DataStage no nível do PIPELINE (F4 da spec
docs/spec-parametros-job-datastage.md) — routers/pipelines.py.

  1. GET /pipelines/{p}/parametros: Encrypted sai mascarado (`***` + tem_valor),
     campos de cálculo saem inteiros; sem a migration 108 devolve lista vazia e
     `disponivel: false` (a tela esconde a seção) — nunca 500.
  2. _gravar_parametros_pipeline: replace-all (DELETE + um INSERT por linha, com
     `?` — árvore api/) na ordem do editor, com origem/cálculo/Encrypted.
  3. A validação é a MESMA da etapa (_preparar_params_ds importado de
     routers.jobs): origem obrigatória, Encrypted `***` sem token = erro.

DB por dublê (padrão test_dependencias_f5: `patch("routers.pipelines.get_db_conn")`);
auth via dependency_overrides. Nada toca banco real.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()
os.environ.setdefault("MSSQL_CONN_STR", "__mock__")
from api.main import app  # noqa: E402

from deps import get_current_user  # noqa: E402
import routers.pipelines as P  # noqa: E402


class _Cursor:
    """Cursor de mentira: responde por trecho do SQL e registra os executes."""

    def __init__(self, tem_tabela=True, linhas=None):
        self.tem_tabela, self.linhas = tem_tabela, linhas or []
        self.executados: list[tuple[str, tuple]] = []
        self._ultimo = ""

    def execute(self, sql, params=None):
        self.executados.append((sql, tuple(params or ())))
        self._ultimo = sql

    def fetchone(self):
        if "INFORMATION_SCHEMA.TABLES" in self._ultimo:
            return (1 if self.tem_tabela else 0,)
        return None

    def fetchall(self):
        if "FROM dbo.etl_pipeline_param" in self._ultimo and "SELECT param_name, param_type, param_value, param_order" in self._ultimo:
            return self.linhas
        return []

    def close(self):
        pass


class _Conn:
    def __init__(self, cur):
        self._cur = cur

    def cursor(self):
        return self._cur

    def close(self):
        pass


@pytest.fixture
def cliente():
    from fastapi.testclient import TestClient
    app.dependency_overrides[get_current_user] = lambda: {
        "matricula": "U1", "perfil": "desenvolvedor", "permissoes": ["tela_pipelines"]}
    yield TestClient(app)
    app.dependency_overrides.pop(get_current_user, None)


# ═══════════ 1. GET ═════════════════════════════════════════════════════════

def test_get_parametros_mascara_encrypted_e_devolve_calculo(cliente):
    cur = _Cursor(linhas=[
        ("pAmb", "String", "PRD", 0, "fixo", None, None, None, None),
        ("pSenha", "Encrypted", "token-fernet", 1, "fixo", None, None, None, None),
        ("pDataFim", "Date", None, 2, "data_referencia", -1, "fim_mes", None, "%Y%m%d"),
    ])
    with patch("routers.pipelines.get_db_conn", return_value=_Conn(cur)):
        r = cliente.get("/pipelines/PIPE_VIDA/parametros")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["disponivel"] is True
    por = {p["param_name"]: p for p in d["parametros"]}
    assert por["pAmb"]["param_value"] == "PRD" and por["pAmb"]["param_source"] == "fixo"
    assert por["pSenha"]["param_value"] == "***" and por["pSenha"]["tem_valor"] is True
    assert "token" not in r.text
    assert (por["pDataFim"]["param_offset_meses"], por["pDataFim"]["param_ancora"], por["pDataFim"]["param_formato"]) \
        == (-1, "fim_mes", "%Y%m%d")
    # consulta pelo pipeline, com `?` (pyodbc)
    sql, params = next(e for e in cur.executados if "FROM dbo.etl_pipeline_param" in e[0])
    assert params == ("PIPE_VIDA",) and "%s" not in sql


def test_get_parametros_sem_migration_108_degrada(cliente):
    cur = _Cursor(tem_tabela=False)
    with patch("routers.pipelines.get_db_conn", return_value=_Conn(cur)):
        r = cliente.get("/pipelines/PIPE_VIDA/parametros")
    assert r.status_code == 200
    assert r.json() == {"parametros": [], "disponivel": False}


# ═══════════ 2. gravação ════════════════════════════════════════════════════

def test_gravar_parametros_e_replace_all_na_ordem():
    cur = _Cursor()
    linhas, erros = P._preparar_params_ds([
        {"param_name": "pAmb", "param_type": "String", "param_source": "fixo", "param_value": "PRD"},
        {"param_name": "pDataFim", "param_type": "Date", "param_source": "data_referencia",
         "param_offset_meses": -1, "param_ancora": "fim_mes"},
    ], {})
    assert erros == []
    P._gravar_parametros_pipeline(cur, "PIPE_VIDA", linhas)
    sqls = [e[0] for e in cur.executados]
    assert sqls[0].startswith("DELETE FROM dbo.etl_pipeline_param") and cur.executados[0][1] == ("PIPE_VIDA",)
    assert len(sqls) == 3 and all(s.startswith("INSERT INTO dbo.etl_pipeline_param") for s in sqls[1:])
    assert cur.executados[1][1] == ("PIPE_VIDA", "pAmb", "String", "PRD", "fixo", None, None, None, None, 0)
    assert cur.executados[2][1] == ("PIPE_VIDA", "pDataFim", "Date", None, "data_referencia", -1, "fim_mes", None, None, 1)
    assert all("%s" not in s for s in sqls)


# ═══════════ 3. a validação é a da etapa ════════════════════════════════════

def test_validacao_e_a_mesma_da_etapa():
    _, erros = P._preparar_params_ds([{"param_name": "pAmb", "param_type": "String", "param_value": "x"}], {})
    assert erros and "origem obrigatória" in erros[0]
    _, erros = P._preparar_params_ds(
        [{"param_name": "pSenha", "param_type": "Encrypted", "param_source": "fixo", "param_value": "***"}], {})
    assert erros and "Encrypted sem valor gravado" in erros[0]
    linhas, erros = P._preparar_params_ds(
        [{"param_name": "pSenha", "param_type": "Encrypted", "param_source": "fixo", "param_value": "***"}],
        {"pSenha": "token-gravado"})
    assert erros == [] and linhas[0]["param_value"] == "token-gravado"


def test_tokens_encrypted_do_pipeline_le_a_tabela_108():
    cur = _Cursor()
    cur.fetchall = lambda: [("pSenha", "tok"), ("pVazio", None)]
    assert P._tokens_encrypted_pipeline(cur, "PIPE") == {"pSenha": "tok"}
    assert cur.executados[0][1] == ("PIPE",) and "param_type='Encrypted'" in cur.executados[0][0]
