"""
Testes da resolução de conexão NATIVA (dbo.etl_conexao) nos componentes SQL do
fluxo — nó SQL, decisão (contagem/query) e storedproc.

Antes, o runtime abria conexão via MsSqlHook (só Airflow Connections) e
ignorava as conexões nativas do Orquestra que o picker da UI já exibia.
Agora tudo passa por utils.conn_resolver.abrir_conexao_mssql (nativa primeiro,
Airflow como fallback — a mesma regra da Cópia de Dados).

Padrão dos testes de factory: Airflow stubado via sys.modules; módulos de
dags/ carregados por importlib; nada toca banco/rede.
"""
from __future__ import annotations

import ast
import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_AIRFLOW_STUBS = [
    "airflow", "airflow.models", "airflow.operators", "airflow.operators.python",
    "airflow.operators.empty", "airflow.datasets", "airflow.utils",
    "airflow.utils.trigger_rule", "airflow.utils.state", "airflow.hooks",
    "airflow.hooks.base",
    "airflow.providers", "airflow.providers.microsoft", "airflow.providers.microsoft.mssql",
    "airflow.providers.microsoft.mssql.hooks", "airflow.providers.microsoft.mssql.hooks.mssql",
    "pendulum", "requests", "pymssql",
]
for _mod in _AIRFLOW_STUBS:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

_ROOT = Path(__file__).parent.parent


def _load_module(name, relpath):
    path = _ROOT / relpath
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def conn_resolver():
    return _load_module("conn_resolver_nativa_test", "dags/utils/conn_resolver.py")


@pytest.fixture(scope="module")
def conditions():
    return _load_module("conditions_nativa_test", "dags/utils/conditions.py")


@pytest.fixture(scope="module")
def factory():
    return _load_module("etl_dag_factory_nativa_test", "dags/etl_dag_factory.py")


# ───────────────── abrir_conexao_mssql: precedência do database ─────────────

class _FakeConn:
    """Conexão 'resolvida' com a interface de atributos usada pelo helper."""
    def __init__(self, host="srv", port=1433, login="u", password="p",
                 schema=None, extra=None):
        self.conn_id = "CX"
        self.host = host
        self.port = port
        self.login = login
        self.password = password
        self.schema = schema
        self.extra = extra

    @property
    def extra_dejson(self):
        try:
            return json.loads(self.extra) if self.extra else {}
        except (ValueError, TypeError):
            return {}


def _pymssql_spy(conn_resolver, monkeypatch):
    calls = []
    fake = MagicMock()
    fake.connect = lambda **kw: calls.append(kw) or MagicMock()
    monkeypatch.setitem(sys.modules, "pymssql", fake)
    return calls


def test_database_explicito_vence(conn_resolver, monkeypatch):
    calls = _pymssql_spy(conn_resolver, monkeypatch)
    monkeypatch.setattr(conn_resolver, "get_conexao",
                        lambda cid: _FakeConn(schema="OUTRO"))
    conn_resolver.abrir_conexao_mssql("CX", database="BI_DW")
    assert calls[0]["database"] == "BI_DW"


def test_sem_database_usa_schema_da_conexao(conn_resolver, monkeypatch):
    calls = _pymssql_spy(conn_resolver, monkeypatch)
    monkeypatch.setattr(conn_resolver, "get_conexao",
                        lambda cid: _FakeConn(schema="DB_CONN"))
    conn_resolver.abrir_conexao_mssql("CX")
    assert calls[0]["database"] == "DB_CONN"


def test_nativa_sem_schema_usa_extra_database(conn_resolver, monkeypatch):
    calls = _pymssql_spy(conn_resolver, monkeypatch)
    nativa = conn_resolver.ConexaoOrquestra(
        conn_id="CX", host="srv", port=1433, login="u", password="p",
        extra='{"database": "DB_EXTRA"}')
    monkeypatch.setattr(conn_resolver, "get_conexao", lambda cid: nativa)
    conn_resolver.abrir_conexao_mssql("CX")
    assert calls[0]["database"] == "DB_EXTRA"


def test_nativa_sem_database_cai_no_schema_da_airflow_homonima(conn_resolver, monkeypatch):
    """Ambiente híbrido: nativa migrada sem database herda o schema que as DAGs
    legadas assumiam da Airflow Connection de mesmo conn_id."""
    calls = _pymssql_spy(conn_resolver, monkeypatch)
    nativa = conn_resolver.ConexaoOrquestra(
        conn_id="CX", host="srv", port=1433, login="u", password="p", extra=None)
    monkeypatch.setattr(conn_resolver, "get_conexao", lambda cid: nativa)

    class _BH:
        @staticmethod
        def get_connection(cid):
            class _C:  # noqa: D401
                schema = "DB_AIRFLOW"
            return _C()
    monkeypatch.setattr(conn_resolver, "BaseHook", _BH)
    conn_resolver.abrir_conexao_mssql("CX")
    assert calls[0]["database"] == "DB_AIRFLOW"


def test_sem_database_nenhum_conecta_no_default_do_login(conn_resolver, monkeypatch):
    calls = _pymssql_spy(conn_resolver, monkeypatch)
    nativa = conn_resolver.ConexaoOrquestra(
        conn_id="CX", host="srv", port=1433, login="u", password="p", extra=None)
    monkeypatch.setattr(conn_resolver, "get_conexao", lambda cid: nativa)

    class _BH:
        @staticmethod
        def get_connection(cid):
            raise RuntimeError("não existe no Airflow")
    monkeypatch.setattr(conn_resolver, "BaseHook", _BH)
    conn_resolver.abrir_conexao_mssql("CX")
    assert "database" not in calls[0]


# ───────────────── eval_condition usa a resolução nativa ────────────────────

def _cond(tipo, **ov):
    base = {"tipo": tipo, "operador": ">", "valor": 5,
            "ramo_verdadeiro": ["JobB"], "ramo_falso": []}
    if tipo == "contagem":
        base["tabela"] = "dbo.FatoVendas"
    if tipo == "query":
        base["sql"] = "SELECT COUNT(*) FROM dbo.X"
    base.update(ov)
    return base


def test_contagem_resolve_pela_conexao_nativa(conditions, monkeypatch):
    chamadas = []
    monkeypatch.setattr(conditions, "_select_first_nativo",
                        lambda cid, sql, db=None: chamadas.append((cid, sql, db)) or (10,))
    resultado, obtido = conditions.eval_condition(
        _cond("contagem", mssql_conn_id="CX_NATIVA", database="BI"), "SQL14_DMDB41")
    assert resultado is True and obtido == 10
    assert chamadas[0][0] == "CX_NATIVA"
    assert chamadas[0][2] == "BI"


def test_query_com_database_opcional(conditions, monkeypatch):
    chamadas = []
    monkeypatch.setattr(conditions, "_select_first_nativo",
                        lambda cid, sql, db=None: chamadas.append((cid, sql, db)) or (3,))
    resultado, obtido = conditions.eval_condition(
        _cond("query", database="BI_DW"), "SQL14_DMDB41")
    assert obtido == 3
    assert chamadas[0][0] == "SQL14_DMDB41"   # sem mssql_conn_id → default
    assert chamadas[0][2] == "BI_DW"


def test_query_sem_database_passa_none(conditions, monkeypatch):
    chamadas = []
    monkeypatch.setattr(conditions, "_select_first_nativo",
                        lambda cid, sql, db=None: chamadas.append((cid, sql, db)) or (3,))
    conditions.eval_condition(_cond("query"), "SQL14_DMDB41")
    assert chamadas[0][2] == ""


# ───────────────── código gerado do nó SQL usa a nativa ─────────────────────

def test_sql_node_gerado_usa_abrir_conexao_mssql(factory):
    jobs = [{"job_name": "JobA", "job_type": "datastage", "job_command": "ds.job",
             "execution_order": 1},
            {"job_name": "NoSQL", "job_type": "sql", "job_command": None,
             "execution_order": 2, "depends_on_jobs": "JobA",
             "sql_json": json.dumps({"sql": "SELECT 1", "mssql_conn_id": "CX", "database": "BI"})}]
    pipeline = {"pipeline_name": "PIPE_CX", "project_name": "BI_CVP", "domain": "TESTE",
                "tags": "ETL", "scheduled_time": "06:00:00", "envia_msg_inicio": 0,
                "envia_msg_fim": 1, "envia_msg_erro": 1, "ambiente": "PROD",
                "schedule_type": "daily"}
    src = factory._generate_dag_source(pipeline, jobs)
    ast.parse(src)
    assert "from utils.conn_resolver import abrir_conexao_mssql" in src
    # o hook direto saiu do helper do nó SQL (a conexão agora é resolvida)
    assert "hook = MsSqlHook(mssql_conn_id=_cid)" not in src
