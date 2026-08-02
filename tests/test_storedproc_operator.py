"""
Testes do StoredProcOperator — o kwarg reservado ``params`` (achado §11-2 do
harness dev, docs/retomada-harness-dev.md).

Contrato:
  - os parâmetros da proc viajam em ``proc_params`` (kwarg e atributo próprios);
    ``params`` é RESERVADO do BaseOperator do Airflow — lista dava
    ``TypeError: params must be a mapping`` no IMPORT da DAG (sintoma 1);
  - em run com ``dag_run.conf`` NÃO-vazia o Airflow SOBRESCREVE ``self.params``
    com o dict mesclado da conf — a execução NÃO pode confundir os dois
    (sintoma 2: iterar o dict dava ``'str' object has no attribute 'get'``
    e derrubava TODO job storedproc disparado com conf, ex.: F3);
  - bind pymssql: placeholder ``%s`` e valores em TUPLA (``?`` é do pyodbc da
    api/ e daria "Incorrect syntax near '?'"); coerção pelo tipo declarado.

Airflow stubado via sys.modules (mesmo padrão do test_dag_factory_execucao.py /
test_python_script_operator.py); o BaseOperator falso REPRODUZ a validação real
do Airflow para ``params`` — é o que torna o sintoma 1 um guarda de verdade.
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

_ROOT = Path(__file__).parent.parent


def _ensure_module(name: str) -> types.ModuleType:
    mod = sys.modules.get(name)
    if mod is None:
        mod = types.ModuleType(name)
        sys.modules[name] = mod
        if "." in name:
            parent, _, child = name.rpartition(".")
            setattr(_ensure_module(parent), child, mod)
    return mod


class _BaseOperatorComoAirflow:
    """Reproduz o comportamento do BaseOperator REAL que causou o bug:
    ``params`` que não seja mapping explode no __init__ (sintoma 1)."""

    def __init__(self, *a, task_id=None, params=None, **k):
        if params is not None and not isinstance(params, dict):
            raise TypeError("params must be a mapping")
        self.task_id = task_id
        self.params = params or {}
        self.log = SimpleNamespace(info=lambda *a, **k: None,
                                   error=lambda *a, **k: None)


def _stub_airflow():
    _ensure_module("airflow")
    _ensure_module("airflow.models").BaseOperator = _BaseOperatorComoAirflow
    _ensure_module("airflow.providers.microsoft.mssql.hooks.mssql").MsSqlHook = type(
        "MsSqlHook", (), {})
    _ensure_module("airflow.providers.ssh.operators.ssh").SSHOperator = type(
        "SSHOperator", (), {"template_ext": (".sh",),
                            "__init__": lambda self, *a, **k: None})


@pytest.fixture()
def job_operators():
    _stub_airflow()
    path = _ROOT / "dags/utils/job_operators.py"
    spec = importlib.util.spec_from_file_location("job_operators_sp_test", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("utils", types.ModuleType("utils"))
    spec.loader.exec_module(mod)
    return mod


# ── Fakes pymssql (conexão resolvida pelo conn_resolver) ─────────────────────

class _FakeCursor:
    def __init__(self):
        self.execs = []          # (sql, vals)
        self.description = None
        self.rowcount = -1
        self.fechado = False

    def execute(self, sql, vals=None):
        self.execs.append((sql, vals))

    def nextset(self):
        return False

    def close(self):
        self.fechado = True


class _FakeConn:
    def __init__(self, cursor):
        self._cursor = cursor
        self.commits = 0
        self.fechada = False

    def cursor(self):
        return self._cursor

    def commit(self):
        self.commits += 1

    def close(self):
        self.fechada = True


def _instala_conn(monkeypatch):
    cur = _FakeCursor()
    conn = _FakeConn(cur)
    fake = types.ModuleType("utils.conn_resolver")
    fake.abrir_conexao_mssql = lambda conn_id, **kw: conn
    monkeypatch.setitem(sys.modules, "utils.conn_resolver", fake)
    return cur, conn


def _sobrescreve_params_como_a_conf(op, conf):
    """Simula o Airflow em run com conf não-vazia: self.params vira o dict
    mesclado (dag.params + conf) — exatamente o que o TaskInstance faz."""
    op.params = dict(conf)


# ── Sintoma 1: instanciação não pode tocar o kwarg reservado ─────────────────

def test_proc_params_lista_nao_vaza_para_o_base(job_operators):
    """Antes do fix, a lista ia parar no BaseOperator e o import da DAG morria
    com TypeError. Com proc_params, o base fica com o params dele intocado."""
    op = job_operators.StoredProcOperator(
        task_id="t", proc="dbo.sp_harness_marca", mssql_conn_id="SQL14_DMDB41",
        proc_params=[{"name": "@origem", "type": "VARCHAR", "value": "spfix"}])
    assert op.proc_params == [{"name": "@origem", "type": "VARCHAR", "value": "spfix"}]
    assert op.params == {}      # o reservado do Airflow segue mapping


# ── Sintoma 2: conf não-vazia sobrescreve self.params ────────────────────────

def test_exec_com_conf_usa_proc_params_e_ignora_self_params(job_operators, monkeypatch):
    """Run disparado com conf (ex.: F3 empurrando data_referencia): o Airflow
    troca self.params pelo dict da conf. A execução tem que usar SÓ os
    proc_params — antes iterava o dict (strings) e morria com AttributeError."""
    cur, conn = _instala_conn(monkeypatch)
    op = job_operators.StoredProcOperator(
        task_id="t", proc="dbo.sp_harness_marca", mssql_conn_id="SQL14_DMDB41",
        proc_params=[{"name": "@origem", "type": "VARCHAR", "value": "spfix"},
                     {"name": "qtd", "type": "INT", "value": "5"}])
    _sobrescreve_params_como_a_conf(op, {"data_referencia": "2026-07-20"})
    op.execute({})
    assert len(cur.execs) == 1
    sql, vals = cur.execs[0]
    # bind pymssql: %s + tupla; nome sem @ ganha o @; coerção INT aplicada
    assert sql == "EXEC dbo.sp_harness_marca @origem=%s, @qtd=%s"
    assert vals == ("spfix", 5)
    # nada da conf vazou para o EXEC
    assert "data_referencia" not in sql and "2026-07-20" not in vals
    assert conn.commits == 1
    assert cur.fechado and conn.fechada


def test_exec_sem_proc_params_com_conf_nao_itera_o_dict(job_operators, monkeypatch):
    """O caso que derrubava TODO job storedproc sem parâmetro fixo: proc_params
    vazio + self.params sobrescrito pela conf → EXEC simples, sem bind."""
    cur, _conn = _instala_conn(monkeypatch)
    op = job_operators.StoredProcOperator(
        task_id="t", proc="dbo.sp_harness_marca", mssql_conn_id="SQL14_DMDB41")
    _sobrescreve_params_como_a_conf(op, {"data_referencia": "2026-07-20"})
    op.execute({})               # antes: AttributeError 'str' ... 'get'
    assert cur.execs == [("EXEC dbo.sp_harness_marca", None)]


def test_exec_com_database_monta_nome_de_tres_partes(job_operators, monkeypatch):
    cur, _conn = _instala_conn(monkeypatch)
    op = job_operators.StoredProcOperator(
        task_id="t", proc="dbo.sp_x", mssql_conn_id="C", database="DB_VENDAS",
        proc_params=[{"name": "@a", "type": "VARCHAR", "value": "v"}])
    op.execute({})
    assert cur.execs[0][0] == "EXEC [DB_VENDAS].dbo.sp_x @a=%s"


# ── DECIMAL exato (achado da revisão: float() perdia precisão em silêncio) ──

def test_coerce_decimal_preserva_precisao(job_operators):
    import decimal
    _coerce = job_operators._coerce
    v = _coerce("0.12345678901234567", "DECIMAL")
    assert isinstance(v, decimal.Decimal)
    assert str(v) == "0.12345678901234567"   # float teria arredondado
    assert isinstance(_coerce("10.5", "MONEY"), decimal.Decimal)
    assert isinstance(_coerce("1.5", "FLOAT"), float)    # aproximado continua float


def test_coerce_decimal_invalido_cai_no_fallback_string(job_operators):
    assert job_operators._coerce("abc", "DECIMAL") == "abc"   # SQL falha ALTO
