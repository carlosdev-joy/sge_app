"""
Testes do nó SQL (roda SELECT + publica o valor escalar no XCom) e da condição de
decisão 'valor_sql' (lê esse XCom e compara), gerados pelo etl_dag_factory.

Mesmo princípio dos demais testes de factory: módulos do Airflow stubados via
sys.modules antes do import; _generate_dag_source é função pura (gera string a
partir de dicts). Como no teste de notificação, EXECUTAMOS a fonte gerada (com
utils stubados) para pegar NameError de tempo de carga — o que o Airflow faria ao
importar o .py (o ast.parse da factory não pega erros de carga, ex.: t_end_<sql>
inexistente referenciado por um job a jusante).
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
    "airflow.utils.trigger_rule", "airflow.utils.state",
    "airflow.providers", "airflow.providers.microsoft", "airflow.providers.microsoft.mssql",
    "airflow.providers.microsoft.mssql.hooks", "airflow.providers.microsoft.mssql.hooks.mssql",
    "pendulum", "requests",
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
def factory():
    return _load_module("etl_dag_factory_sql_test", "dags/etl_dag_factory.py")


@pytest.fixture(scope="module")
def conditions():
    return _load_module("conditions_sql_test", "dags/utils/conditions.py")


def _pipeline(**overrides):
    base = {
        "pipeline_name": "PIPE_SQL", "project_name": "BI_CVP", "domain": "TESTE",
        "tags": "ETL", "scheduled_time": "06:00:00",
        "envia_msg_inicio": 0, "envia_msg_fim": 1, "envia_msg_erro": 1,
        "ambiente": "PROD", "schedule_type": "daily",
    }
    base.update(overrides)
    return base


def _job(name, jtype="datastage", order=1, depends=None, sql=None, cond=None):
    j = {"job_name": name, "job_type": jtype, "job_command": "ds.job",
         "execution_order": order}
    if depends is not None:
        j["depends_on_jobs"] = depends
    if sql is not None:
        j["sql_json"] = json.dumps(sql)
    if cond is not None:
        j["condition_json"] = json.dumps(cond)
    return j


_SQL_CFG = {"sql": "SELECT MAX(dt) FROM dbo.Controle",
            "mssql_conn_id": "SQL14_DMDB41", "database": "BI"}


def _valor_sql_cond(source="NoSQL"):
    return {
        "tipo": "valor_sql", "source_job": source, "comparacao": "data",
        "operador": ">=", "valor": "HOJE",
        "ramo_verdadeiro": ["JobB"], "ramo_falso": ["JobC"],
    }


def _exec_source(src):
    """Importa DE FATO a DAG gerada — pega NameError de tempo de carga (o que o
    Airflow faria ao importar o .py). Stuba ``utils.*`` SÓ durante o exec."""
    util_mods = ("utils", "utils.datastage_operator", "utils.conditions", "utils.job_operators")
    saved = {m: sys.modules.get(m) for m in util_mods}
    try:
        for m in util_mods:
            sys.modules[m] = MagicMock()
        exec(compile(src, "<dag>", "exec"), {})
    finally:
        for m, prev in saved.items():
            if prev is None:
                sys.modules.pop(m, None)
            else:
                sys.modules[m] = prev


# ───────────────────────────── DAG gerada ──────────────────────────────────

def test_sql_node_compila_e_importa(factory):
    jobs = [_job("JobA"),
            _job("NoSQL", jtype="sql", order=2, depends="JobA", sql=_SQL_CFG)]
    src = factory._generate_dag_source(_pipeline(), jobs)
    ast.parse(src)
    _exec_source(src)
    # callable gerado que RODA o SELECT e RETORNA o valor (vira XCom default)
    assert "def _sql_NoSQL(**context):" in src
    assert "t_sql_NoSQL = PythonOperator(" in src
    assert "_resolve_e_roda_sql(" in src
    # nó SQL não tem t_end_ próprio (fica fora de end_tasks)
    assert "t_end_NoSQL" not in src
    # o SELECT do usuário viaja literal no código gerado
    assert "SELECT MAX(dt) FROM dbo.Controle" in src


def test_sql_node_mais_decisao_valor_sql(factory):
    """Pipeline completo: SQL publica o valor, a decisão valor_sql lê via ti e
    roteia. Compila E importa sem NameError de carga."""
    jobs = [
        _job("JobA"),
        _job("NoSQL", jtype="sql", order=2, depends="JobA", sql=_SQL_CFG),
        _job("Decisao", jtype="decisao", order=3, depends="NoSQL", cond=_valor_sql_cond("NoSQL")),
        _job("JobB", jtype="python", order=4, depends=""),
        _job("JobC", jtype="python", order=5, depends=""),
    ]
    src = factory._generate_dag_source(_pipeline(), jobs)
    ast.parse(src)
    _exec_source(src)  # NameError de carga aqui se regredir
    # a decisão depende do nó SQL → referencia t_sql_NoSQL (NÃO t_end_NoSQL)
    assert "t_sql_NoSQL >> t_dec_Decisao" in src
    assert "t_end_NoSQL" not in src
    # o decide passa ti ao eval_condition (valor_sql lê o XCom do source_job)
    assert "ti=_ti" in src
    assert "from utils.conditions import eval_condition" in src
    # wiring do upstream do nó SQL
    assert "t_end_JobA >> t_sql_NoSQL" in src


def test_job_que_depende_de_sql_usa_t_sql(factory):
    """Regressão (espelha notificação): um job que DEPENDE de um nó SQL referencia
    t_sql_<dep>, não t_end_<dep> (inexistente → NameError no import do Airflow)."""
    jobs = [
        _job("JobA"),
        _job("NoSQL", jtype="sql", order=2, depends="JobA", sql=_SQL_CFG),
        _job("JobB", jtype="python", order=3, depends="NoSQL"),
    ]
    src = factory._generate_dag_source(_pipeline(), jobs)
    ast.parse(src)
    _exec_source(src)
    assert "t_sql_NoSQL >> t_start_JobB" in src
    assert "t_end_NoSQL" not in src


def test_sql_node_convergencia_fechamento(factory):
    """Nó SQL (sem t_end) converge no publish_dataset, como a notificação."""
    jobs = [_job("JobA"),
            _job("NoSQL", jtype="sql", order=2, depends="JobA", sql=_SQL_CFG)]
    src = factory._generate_dag_source(_pipeline(), jobs)
    assert "t_sql_NoSQL >> t_publish_dataset" in src


def test_pipeline_sem_sql_nao_muda(factory):
    """Sem nó SQL: nenhuma task t_sql_* nem callable _sql_* gerados (não-regressão).

    O helper _resolve_e_roda_sql vive em helpers_lines (sempre emitido, como o
    _resolve_e_envia_notificacao da notificação) — o que importa é que NENHUM nó
    SQL seja materializado quando o pipeline não tem nenhum."""
    jobs = [_job("JobA"), _job("JobB", order=2)]
    src = factory._generate_dag_source(_pipeline(), jobs)
    ast.parse(src)
    _exec_source(src)
    assert "t_sql_" not in src
    assert "def _sql_" not in src


# ─────────────────────── eval_condition('valor_sql') ───────────────────────

class _FakeTI:
    """TaskInstance mínimo: xcom_pull(task_ids=...) devolve o valor configurado."""
    def __init__(self, valores):
        self._valores = valores
        self.pulls = []

    def xcom_pull(self, task_ids=None, **kwargs):
        self.pulls.append(task_ids)
        return self._valores.get(task_ids)


def _cond_valor_sql(**over):
    base = {"tipo": "valor_sql", "source_job": "NoSQL", "comparacao": "numero",
            "operador": ">", "valor": 10}
    base.update(over)
    return base


def test_eval_valor_sql_le_xcom_e_compara(conditions):
    ti = _FakeTI({"NoSQL": 42})
    resultado, valor = conditions.eval_condition(
        _cond_valor_sql(), "SQL14_DMDB41", ti=ti)
    assert resultado is True
    assert valor == 42
    assert ti.pulls == ["NoSQL"]


def test_eval_valor_sql_comparacao_falsa(conditions):
    ti = _FakeTI({"NoSQL": 5})
    resultado, valor = conditions.eval_condition(
        _cond_valor_sql(operador=">", valor=10), "SQL14_DMDB41", ti=ti)
    assert resultado is False
    assert valor == 5


def test_eval_valor_sql_comparacao_data(conditions):
    import datetime as _d
    hoje = _d.date.today()
    ti = _FakeTI({"NoSQL": hoje})
    resultado, valor = conditions.eval_condition(
        _cond_valor_sql(comparacao="data", operador="=", valor="HOJE"),
        "SQL14_DMDB41", ti=ti)
    assert resultado is True


def test_eval_valor_sql_sem_ti_degrada_false(conditions):
    # Sem ti → não dá para ler o XCom: valor None → comparação tipada False.
    resultado, valor = conditions.eval_condition(
        _cond_valor_sql(), "SQL14_DMDB41", ti=None)
    assert resultado is False
    assert valor is None


def test_eval_valor_sql_xcom_ausente_degrada_false(conditions):
    # source_job sem valor no XCom → None → False (não levanta).
    ti = _FakeTI({})  # xcom_pull devolve None
    resultado, valor = conditions.eval_condition(
        _cond_valor_sql(comparacao="data", operador="=", valor="HOJE"),
        "SQL14_DMDB41", ti=ti)
    assert resultado is False
    assert valor is None


def test_eval_valor_sql_nao_abre_hook(conditions, monkeypatch):
    """valor_sql não deve tocar o banco — resolve só pelo XCom. Garante que o
    MsSqlHook lazy não é instanciado (o ramo retorna antes)."""
    ti = _FakeTI({"NoSQL": "7"})
    resultado, valor = conditions.eval_condition(
        _cond_valor_sql(comparacao="numero", operador="=", valor=7),
        "SQL14_DMDB41", ti=ti)
    assert resultado is True
    assert valor == "7"
