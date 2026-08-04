"""
Rename de job que difere APENAS na CAIXA (incidente 2026-08-01).

O job no DataStage chama-se ``SSDVidaCobranca01BaixaProcessamentoCobranca``; o
Orquestra tinha cadastrado ``SsdVida…``. O DataStage é case-sensitive nos nomes
de job — o disparo falhou com "Cannot find job … Status code = -1004". Ao tentar
corrigir, a tela devolvia 422 "já existe um job 'SSDVida…' no pipeline": a guarda
de unicidade fazia ``SELECT COUNT(*) … WHERE job_name=?`` com o nome NOVO e, sob
a colação CI do SQL Server, casava com a PRÓPRIA linha.

Dois testes aqui FALHAM no código anterior à correção:
  - ``test_rename_so_caixa_e_aceito``     (era 422)
  - ``test_rename_so_caixa_usa_update_in_place`` (a cópia estouraria a PK)

Padrão de test_sequence_approve_grafia.py: TestClient do conftest, get_db_conn
mockado no router e autenticação via dependency_overrides. O cursor falso imita
a colação CASE-INSENSITIVE do SQL Server — é ela que cria o problema.
"""
from __future__ import annotations

import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()
os.environ.setdefault("MSSQL_CONN_STR", "__mock__")
from api.main import app as _app  # noqa: F401  (ordem de import — ver test_copias.py)

from deps import PERM_EDITAR, get_current_user

PIPE = "DEV_F10_A"
COLS_JOB = ["pipeline_name", "job_name", "execution_order", "job_type", "depends_on_jobs",
            "condition_json"]


@pytest.fixture(scope="module")
def J():
    import routers.jobs as _j
    return _j


class _FakeCursorJobs:
    """Cursor falso sobre etl_pipeline_job com colação CASE-INSENSITIVE.

    ``jobs`` é a lista [(job_name, depends_on_jobs, condition_json)] do pipeline.
    O ponto do dublê: todo WHERE por job_name casa IGNORANDO A CAIXA, exatamente
    como o SQL Server faz — é o que torna o bug reproduzível fora do banco."""

    def __init__(self, jobs):
        self.jobs = [list(j) for j in jobs]
        self.executed: list[tuple[str, tuple]] = []
        self._last = ""
        self._last_params: tuple = ()
        self.rowcount = 1

    # helpers ---------------------------------------------------------------
    def _idx(self, nome):
        alvo = (nome or "").strip().casefold()
        for i, j in enumerate(self.jobs):
            if (j[0] or "").strip().casefold() == alvo:
                return i
        return None

    def sqls(self) -> str:
        return "\n".join(s for s, _ in self.executed)

    # DB-API ----------------------------------------------------------------
    def execute(self, sql, params=None):
        self._last = sql
        self._last_params = tuple(params) if params is not None else ()
        self.executed.append((sql, self._last_params))
        p = self._last_params

        if sql.startswith("UPDATE dbo.etl_pipeline_job SET job_name="):
            i = self._idx(p[2])
            if i is not None:
                self.jobs[i][0] = p[0]
        elif sql.startswith("INSERT INTO dbo.etl_pipeline_job "):
            i = self._idx(p[2])
            if i is not None:
                origem = self.jobs[i]
                # O banco real recusaria: sob CI a chave (pipeline, job_name) da
                # linha nova é a MESMA da antiga quando só a caixa muda.
                if (origem[0] or "").casefold() == (p[0] or "").casefold():
                    raise RuntimeError(
                        "Violation of PRIMARY KEY constraint 'PK_etl_pipeline_job'")
                self.jobs.append([p[0], origem[1], origem[2]])
        elif sql.startswith("DELETE FROM dbo.etl_pipeline_job "):
            i = self._idx(p[1])
            if i is not None:
                self.jobs.pop(i)
        elif sql.startswith("UPDATE dbo.etl_pipeline_job SET depends_on_jobs="):
            i = self._idx(p[2])
            if i is not None:
                self.jobs[i][1] = p[0]
        elif sql.startswith("UPDATE dbo.etl_pipeline_job SET condition_json="):
            i = self._idx(p[2])
            if i is not None:
                self.jobs[i][2] = p[0]

    def fetchone(self):
        s = self._last
        if "FROM INFORMATION_SCHEMA.TABLES" in s:
            return (1,)
        if "FROM INFORMATION_SCHEMA.COLUMNS" in s:
            return (1,)
        if "status='RUNNING'" in s:
            return (0,)
        return (0,)

    def fetchall(self):
        s = self._last
        if s.startswith("SELECT job_name FROM dbo.etl_pipeline_job"):
            return [(j[0],) for j in self.jobs]
        if "FROM sys.columns" in s:
            return [(c,) for c in COLS_JOB]
        if s.startswith("SELECT job_name, depends_on_jobs"):
            return [(j[0], j[1]) for j in self.jobs if j[1] is not None]
        if s.startswith("SELECT job_name, condition_json"):
            return [(j[0], j[2]) for j in self.jobs if j[2] is not None]
        return []

    def close(self):
        pass


def _mock_conn(cur):
    conn = MagicMock()
    conn.cursor.return_value = cur
    return conn


@pytest.fixture
def auth_editar(app):
    _app.dependency_overrides[get_current_user] = lambda: {
        "matricula": "DEV1", "perfil": "desenvolvedor", "permissoes": [PERM_EDITAR],
    }
    yield
    _app.dependency_overrides.pop(get_current_user, None)


def _rename(client, cur, de, para, pipe=PIPE):
    with patch("routers.jobs.get_db_conn", return_value=_mock_conn(cur)):
        return client.post(f"/pipelines/jobs/{pipe}/{de}/rename",
                           json={"novo_nome": para})


# ───────────────────── helpers puros: casamento sem caixa ───────────────────

def test_mesmo_job_ignora_caixa_e_espacos(J):
    assert J._mesmo_job("SsdVida01", "SSDVIDA01")
    assert J._mesmo_job(" SsdVida01 ", "ssdvida01")
    assert not J._mesmo_job("SsdVida01", "SsdVida02")
    assert not J._mesmo_job(None, "SsdVida01")


def test_dep_csv_troca_mesmo_com_caixa_divergente(J):
    # CSV gravado com outra caixa que o cadastro — sem CI a referência ficaria
    # apontando para um job que não existe mais.
    assert J._rename_in_dep_csv("ssdvida01,JobB", "SsdVida01", "SSDVida01") \
        == "SSDVida01,JobB"


def test_dep_csv_none_quando_texto_nao_muda(J):
    # A grafia no CSV já é a nova → nada a fazer (evita UPDATE inútil).
    assert J._rename_in_dep_csv("SSDVida01,JobB", "SsdVida01", "SSDVida01") is None


def test_condition_troca_mesmo_com_caixa_divergente(J):
    cond = {
        "tipo": "contagem",
        "ramo_verdadeiro": ["ssdvida01"],
        "casos": [{"nome": "a", "operador": ">", "valor": 1, "ramo": ["SSDVIDA01"]}],
        "ramo_senao": ["SsdVida01"],
        "job_name": "sSdViDa01",
        "child_job": "SsdVida01",
    }
    assert J._rename_in_condition(cond, "SsdVida01", "SSDVida01") is True
    assert cond["ramo_verdadeiro"] == ["SSDVida01"]
    assert cond["casos"][0]["ramo"] == ["SSDVida01"]
    assert cond["ramo_senao"] == ["SSDVida01"]
    assert cond["job_name"] == "SSDVida01"
    # child_job é job-filho do DataStage — continua intocado.
    assert cond["child_job"] == "SsdVida01"


# ───────────────────────── endpoint: rename só de caixa ─────────────────────

def test_rename_so_caixa_e_aceito(client, auth_editar):
    """FALHA no código anterior: a guarda de unicidade casava com a própria
    linha sob colação CI e devolvia 422 'já existe um job'."""
    cur = _FakeCursorJobs([("SsdVida01", None, None)])
    r = _rename(client, cur, "SsdVida01", "SSDVida01")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["de"] == "SsdVida01" and body["para"] == "SSDVida01"
    assert body["so_caixa"] is True
    assert any("maiúsculas" in a for a in body["avisos"])
    assert [j[0] for j in cur.jobs] == ["SSDVida01"]


def test_rename_so_caixa_usa_update_in_place(client, auth_editar):
    """FALHA no código anterior: a estratégia CÓPIA faria INSERT+DELETE e o
    dublê levanta violação de PK (é o que o banco faria sob CI)."""
    cur = _FakeCursorJobs([("SsdVida01", None, None)])
    r = _rename(client, cur, "SsdVida01", "SSDVida01")
    assert r.status_code == 200, r.text
    sqls = cur.sqls()
    assert "UPDATE dbo.etl_pipeline_job SET job_name=?" in sqls
    assert "INSERT INTO dbo.etl_pipeline_job (" not in sqls
    assert "DELETE FROM dbo.etl_pipeline_job" not in sqls


def test_rename_so_caixa_preserva_o_contrato_inteiro(client, auth_editar):
    """Tudo o que o rename já atualizava continua sendo atualizado no caminho
    novo: params, CSV dos irmãos, condition_json, lineage, histórico e ds log."""
    cond = json.dumps({"tipo": "contagem", "ramo_verdadeiro": ["ssdvida01"]})
    cur = _FakeCursorJobs([
        ("SsdVida01", None, None),
        ("Irmao", "ssdvida01,Outro", None),
        ("Decisao", None, cond),
    ])
    r = _rename(client, cur, "SsdVida01", "SSDVida01")
    assert r.status_code == 200, r.text
    sqls = cur.sqls()
    assert "UPDATE dbo.etl_pipeline_job_param SET job_name=?" in sqls
    assert "UPDATE dbo.etl_job_lineage SET job_name=?" in sqls
    assert "UPDATE dbo.etl_job_execution SET job_name=?" in sqls
    assert "UPDATE dbo.etl_ds_job_log SET job_name=?" in sqls
    assert "INSERT INTO dbo.etl_pipeline_audit" in sqls
    # CSV e condição do irmão acompanharam a grafia nova.
    irmao = next(j for j in cur.jobs if j[0] == "Irmao")
    assert irmao[1] == "SSDVida01,Outro"
    decisao = next(j for j in cur.jobs if j[0] == "Decisao")
    assert json.loads(decisao[2])["ramo_verdadeiro"] == ["SSDVida01"]


def test_rename_canoniza_a_grafia_gravada(client, auth_editar):
    """A rota casa sob CI com qualquer caixa: pedir o rename usando a grafia
    ERRADA no path ainda renomeia a linha real (e o 'de' devolvido é a oficial)."""
    cur = _FakeCursorJobs([("SsdVida01", None, None)])
    r = _rename(client, cur, "SSDVIDA01", "Ssd_Vida_01")
    assert r.status_code == 200, r.text
    assert r.json()["de"] == "SsdVida01"
    assert r.json()["so_caixa"] is False


def test_rename_igual_ao_atual_continua_422(client, auth_editar):
    cur = _FakeCursorJobs([("SsdVida01", None, None)])
    r = _rename(client, cur, "SsdVida01", "SsdVida01")
    assert r.status_code == 422
    assert "igual ao atual" in r.json()["detail"]


def test_rename_colisao_real_continua_422(client, auth_editar):
    """A guarda continua barrando o conflito de verdade — inclusive quando o
    outro job difere só na caixa (sob CI as duas grafias não coexistem)."""
    cur = _FakeCursorJobs([("SsdVida01", None, None), ("Outro", None, None)])
    r = _rename(client, cur, "SsdVida01", "OUTRO")
    assert r.status_code == 422
    assert "já existe um job" in r.json()["detail"]


def test_rename_comum_continua_usando_copia(client, auth_editar):
    """Regressão: renome que muda mais que a caixa segue pela estratégia CÓPIA
    (INSERT + UPDATE dos params + DELETE), como antes."""
    cur = _FakeCursorJobs([("SsdVida01", None, None)])
    r = _rename(client, cur, "SsdVida01", "NovoNome")
    assert r.status_code == 200, r.text
    assert r.json()["so_caixa"] is False
    sqls = cur.sqls()
    assert "INSERT INTO dbo.etl_pipeline_job (" in sqls
    assert "DELETE FROM dbo.etl_pipeline_job" in sqls
    assert [j[0] for j in cur.jobs] == ["NovoNome"]


def test_rename_job_inexistente_404(client, auth_editar):
    cur = _FakeCursorJobs([("Outro", None, None)])
    r = _rename(client, cur, "SsdVida01", "SSDVida01")
    assert r.status_code == 404
