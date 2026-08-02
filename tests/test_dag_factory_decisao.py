"""
Testes do nó de Decisão (ramificação condicional) gerado pelo etl_dag_factory.

Mesmo princípio dos demais testes de factory: os módulos do Airflow são stubados
via sys.modules antes do import — _generate_dag_source é função pura (gera string
a partir de dicts). Além da DAG gerada, testa também os helpers puros de
utils/conditions.py (validação anti-injeção e comparação), que não importam
Airflow no nível de módulo (MsSqlHook é importado lazy dentro de eval_condition).
"""
from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_AIRFLOW_STUBS = [
    "airflow", "airflow.models", "airflow.operators", "airflow.operators.python",
    "airflow.providers", "airflow.providers.microsoft", "airflow.providers.microsoft.mssql",
    "airflow.providers.microsoft.mssql.hooks", "airflow.providers.microsoft.mssql.hooks.mssql",
    "pendulum",
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
    return _load_module("etl_dag_factory_dec_test", "dags/etl_dag_factory.py")


@pytest.fixture(scope="module")
def conditions():
    return _load_module("conditions_test", "dags/utils/conditions.py")


def _pipeline(**overrides):
    base = {
        "pipeline_name": "PIPE_DECISAO", "project_name": "BI_CVP", "domain": "TESTE",
        "tags": "ETL", "scheduled_time": "06:00:00",
        "envia_msg_inicio": 0, "envia_msg_fim": 1, "envia_msg_erro": 1,
        "ambiente": "PROD", "schedule_type": "daily",
    }
    base.update(overrides)
    return base


def _job(name, jtype="python", order=1, depends=None, cond=None, cmd=None):
    j = {"job_name": name, "job_type": jtype, "job_command": cmd or "pkg.mod",
         "execution_order": order}
    if depends is not None:
        j["depends_on_jobs"] = depends
    if cond is not None:
        import json
        j["condition_json"] = json.dumps(cond)
    return j


def _contagem_cond():
    return {
        "tipo": "contagem", "tabela": "dbo.FatoVendas", "operador": ">", "valor": 10000,
        "ramo_verdadeiro": ["JobB"], "ramo_falso": ["JobC"],
    }


# ───────────────────────────── DAG gerada ──────────────────────────────────

def test_decisao_gera_branch_operator_e_compila(factory):
    jobs = [
        _job("JobA", order=1),
        _job("Decisao", jtype="decisao", order=2, depends="JobA", cond=_contagem_cond()),
        _job("JobB", order=3, depends=""),
        _job("JobC", order=4, depends=""),
    ]
    src = factory._generate_dag_source(_pipeline(), jobs)
    ast.parse(src)  # SyntaxError se inválido
    assert "from utils.conditions import eval_condition" in src
    assert "BranchPythonOperator" in src
    assert "def _decide_Decisao(" in src
    assert "t_dec_Decisao = BranchPythonOperator(" in src
    # branch retorna os t_start (log_start_*) do ramo escolhido
    assert "return ['log_start_JobB'] if resultado else ['log_start_JobC']" in src


def test_decisao_wiring_arestas(factory):
    jobs = [
        _job("JobA", order=1),
        _job("Decisao", jtype="decisao", order=2, depends="JobA", cond=_contagem_cond()),
        _job("JobB", order=3, depends=""),
        _job("JobC", order=4, depends=""),
    ]
    src = factory._generate_dag_source(_pipeline(), jobs)
    # decisão depende de JobA; membros descem da decisão
    assert "t_end_JobA >> t_dec_Decisao" in src
    assert "t_dec_Decisao >> t_start_JobB >> t_job_JobB >> t_end_JobB" in src
    assert "t_dec_Decisao >> t_start_JobC >> t_job_JobC >> t_end_JobC" in src
    # a decisão NÃO entra em end_tasks (não tem t_end próprio)
    assert "t_end_Decisao" not in src


def test_pegadinha_trigger_rules(factory):
    """A pegadinha nº1 do Airflow: junções não podem ser puladas por engano."""
    jobs = [
        _job("JobA", order=1),
        _job("Decisao", jtype="decisao", order=2, depends="JobA", cond=_contagem_cond()),
        _job("JobB", order=3, depends=""),
        _job("JobC", order=4, depends=""),
    ]
    src = factory._generate_dag_source(_pipeline(), jobs)
    # t_start dos membros alcançáveis: NONE_FAILED_MIN_ONE_SUCCESS
    assert src.count("trigger_rule=TriggerRule.NONE_FAILED_MIN_ONE_SUCCESS") >= 2
    # t_end dos membros alcançáveis: NONE_SKIPPED (propaga skip, mantém fail-fast)
    assert "trigger_rule=TriggerRule.NONE_SKIPPED" in src
    # publish_dataset tolera ramos pulados (trigger_rule dentro do seu bloco)
    # F2: o publish virou PythonOperator (grava SUCESSO) mantendo task_id,
    # trigger rule e outlets — o assert segue sobre o bloco novo.
    _i = src.index("t_publish_dataset = PythonOperator(")
    bloco_pub = src[_i:_i + 220]
    assert "TriggerRule.NONE_FAILED_MIN_ONE_SUCCESS" in bloco_pub


def test_job_fora_do_ramo_inalterado(factory):
    """JobA não é alcançável a partir da decisão → t_end segue ALL_DONE."""
    jobs = [
        _job("JobA", order=1),
        _job("Decisao", jtype="decisao", order=2, depends="JobA", cond=_contagem_cond()),
        _job("JobB", order=3, depends=""),
        _job("JobC", order=4, depends=""),
    ]
    src = factory._generate_dag_source(_pipeline(), jobs)
    bloco_a = src.split("t_end_JobA = PythonOperator(")[1].split(")")[0]
    assert "TriggerRule.ALL_DONE" in bloco_a
    assert "NONE_SKIPPED" not in bloco_a


def test_fecho_transitivo_jusante(factory):
    """JobD depende de JobB (membro do ramo) → também é alcançável."""
    cond = _contagem_cond()
    jobs = [
        _job("JobA", order=1),
        _job("Decisao", jtype="decisao", order=2, depends="JobA", cond=cond),
        _job("JobB", order=3, depends=""),
        _job("JobC", order=4, depends=""),
        _job("JobD", order=5, depends="JobB"),
    ]
    src = factory._generate_dag_source(_pipeline(), jobs)
    bloco_d = src.split("t_end_JobD = PythonOperator(")[1].split(")")[0]
    assert "TriggerRule.NONE_SKIPPED" in bloco_d


def test_decisao_tipo_query_compila(factory):
    cond = {
        "tipo": "query", "sql": "SELECT MAX(flag) FROM dbo.Controle",
        "operador": "=", "valor": 1,
        "ramo_verdadeiro": ["JobB"], "ramo_falso": [],
    }
    jobs = [
        _job("JobA", order=1),
        _job("Decisao", jtype="decisao", order=2, depends="JobA", cond=cond),
        _job("JobB", order=3, depends=""),
        _job("JobC", order=4, depends="JobA"),
    ]
    src = factory._generate_dag_source(_pipeline(), jobs)
    ast.parse(src)
    assert "SELECT MAX(flag) FROM dbo.Controle" in src
    # ramo_falso vazio → retorna lista vazia
    assert "return ['log_start_JobB'] if resultado else []" in src


def test_pipeline_sem_decisao_nao_muda(factory):
    """Sem decisão: nenhum import/trigger novo (não-regressão)."""
    jobs = [_job("JobA", order=1), _job("JobB", order=2)]
    src = factory._generate_dag_source(_pipeline(), jobs)
    ast.parse(src)
    assert "BranchPythonOperator" not in src
    assert "from utils.conditions import" not in src
    assert "NONE_SKIPPED" not in src
    assert "NONE_FAILED_MIN_ONE_SUCCESS" not in src


# ─────────────────────── helpers de conditions.py ──────────────────────────

def test_safe_table_aceita_validas(conditions):
    assert conditions._safe_table("dbo.FatoVendas") == "[dbo].[FatoVendas]"
    assert conditions._safe_table("Tabela") == "[Tabela]"
    assert conditions._safe_table("BI.dbo.X") == "[BI].[dbo].[X]"


@pytest.mark.parametrize("ruim", [
    "dbo.Fato; DROP TABLE x", "dbo.Fato--", "a.b.c.d", "", "dbo.[Fato]",
    "1tabela", "dbo.Fato Vendas",
])
def test_safe_table_rejeita_injecao(conditions, ruim):
    with pytest.raises(ValueError):
        conditions._safe_table(ruim)


def test_validate_select_aceita(conditions):
    assert conditions._validate_select("SELECT 1") == "SELECT 1"
    assert conditions._validate_select("  select count(*) from x ;  ").lower().startswith("select")


@pytest.mark.parametrize("ruim", [
    "DELETE FROM x", "UPDATE x SET a=1", "SELECT 1; DROP TABLE x",
    "INSERT INTO x VALUES (1)", "EXEC sp_who", "", "DROP TABLE x",
    "SELECT * INTO y FROM x",
])
def test_validate_select_rejeita(conditions, ruim):
    with pytest.raises(ValueError):
        conditions._validate_select(ruim)


def test_compara_numerico_e_texto(conditions):
    assert conditions.compara(10001, ">", 10000) is True
    assert conditions.compara(5, ">", 10) is False
    assert conditions.compara("1", "=", 1) is True          # numérico coerção
    assert conditions.compara("ABC", "=", "ABC") is True     # texto
    assert conditions.compara("ABC", "<>", "XYZ") is True
    assert conditions.compara(10, "<=", 10) is True


def test_compara_operador_invalido(conditions):
    with pytest.raises(ValueError):
        conditions.compara(1, "LIKE", 1)


# ─────────────────────────── compara_tipado ────────────────────────────────

def test_compara_tipado_numero(conditions):
    assert conditions.compara_tipado("10001", ">", "10000", "numero") is True
    assert conditions.compara_tipado(5, ">", 10, "numero") is False
    assert conditions.compara_tipado(3.5, "=", "3.5", "numero") is True
    # Conversão falha → vira 0.0 (não quebra): "abc"=0.0, "0"=0.0 → iguais.
    assert conditions.compara_tipado("abc", "=", "0", "numero") is True


def test_compara_tipado_texto(conditions):
    assert conditions.compara_tipado("ABC", "=", "ABC", "texto") is True
    assert conditions.compara_tipado("ABC", "<>", "XYZ", "texto") is True
    # número comparado como texto: "10" vs "9" são strings ("10" < "9").
    assert conditions.compara_tipado(10, "<", 9, "texto") is True


def test_compara_tipado_data_literal(conditions):
    import datetime as _d
    assert conditions.compara_tipado("2026-06-24", "=", "2026-06-24", "data") is True
    assert conditions.compara_tipado("2026-06-25", ">", "2026-06-24", "data") is True
    # date/datetime do pyodbc são normalizados a date (ignora hora).
    assert conditions.compara_tipado(
        _d.datetime(2026, 6, 24, 13, 0, 0), "=", "2026-06-24", "data") is True
    assert conditions.compara_tipado(
        _d.date(2026, 6, 24), "<", "2026-06-25", "data") is True


def test_compara_tipado_data_token_hoje(conditions):
    import datetime as _d
    hoje = _d.date.today()
    assert conditions.compara_tipado(hoje, "=", "HOJE", "data") is True
    assert conditions.compara_tipado(hoje, "=", "hoje", "data") is True
    assert conditions.compara_tipado(
        hoje - _d.timedelta(days=1), "<", "HOJE", "data") is True


def test_compara_tipado_data_invalida_nao_quebra(conditions):
    # Valor não parseável → False (logado), nunca exceção.
    assert conditions.compara_tipado("xx/yy/zzzz", "=", "2026-06-24", "data") is False
    assert conditions.compara_tipado("2026-06-24", "=", "nao-data", "data") is False


def test_compara_tipado_ausente_delega_legado(conditions):
    # comparacao None/'' → comportamento do compara legado (auto-coerção numérica).
    assert conditions.compara_tipado("1", "=", 1, None) is True
    assert conditions.compara_tipado("ABC", "=", "ABC", "") is True


def test_compara_tipado_operador_invalido(conditions):
    with pytest.raises(ValueError):
        conditions.compara_tipado(1, "LIKE", 1, "numero")


def test_ds_log_first_escopa_por_pipeline(conditions):
    """A leitura de rows_out/child_jobs deve incluir pipeline_name no WHERE quando
    disponível — o execution_id (ts_nodash) pode colidir entre pipelines."""
    cap = {}

    class FakeHook:
        def get_first(self, sql, parameters=None):
            cap["sql"] = " ".join(sql.split())
            cap["params"] = parameters
            return None

    h = FakeHook()
    # com execução + pipeline → escopa pelos três
    conditions._ds_log_first(h, "rows_out", "JobA", "20260624T050000", "PIPE_X")
    assert "WHERE execution_id=%s AND pipeline_name=%s AND job_name=%s" in cap["sql"]
    assert cap["params"] == ("20260624T050000", "PIPE_X", "JobA")
    # sem pipeline (back-compat) → não inclui o escopo
    conditions._ds_log_first(h, "rows_out", "JobA", "20260624T050000", "")
    assert "pipeline_name" not in cap["sql"]
    assert cap["params"] == ("20260624T050000", "JobA")
    # sem execution_id → melhor esforço só por job_name
    conditions._ds_log_first(h, "child_jobs", "JobA", None, "PIPE_X")
    assert cap["params"] == ("JobA",)
    assert "child_jobs" in cap["sql"]


# ───────────────────────── on_error (fail-loud) ─────────────────────────────

def test_decisao_on_error_falhar_vai_para_o_codigo_gerado(factory):
    """O condition_json inteiro (incl. on_error) é embutido no _decide_* gerado
    — é assim que eval_condition sabe que deve falhar alto."""
    cond = {**_contagem_cond(), "on_error": "falhar"}
    jobs = [_job("JobA"), _job("Decisao", jtype="decisao", order=2, cond=cond),
            _job("JobB", order=3), _job("JobC", order=3)]
    src = factory._generate_dag_source(_pipeline(), jobs)
    assert "'on_error': 'falhar'" in src


def test_decisao_sem_on_error_nao_inventa_chave(factory):
    """condition_json legado (sem on_error) → DAG regenerada NÃO ganha a chave
    (comportamento degrade preservado até o re-save carimbar)."""
    jobs = [_job("JobA"), _job("Decisao", jtype="decisao", order=2, cond=_contagem_cond()),
            _job("JobB", order=3), _job("JobC", order=3)]
    src = factory._generate_dag_source(_pipeline(), jobs)
    assert "'on_error'" not in src


# ───────────────────── SKIPPED de 1ª classe (flow_close) ────────────────────

def test_pipeline_com_decisao_gera_flow_close(factory):
    """Com decisão, a DAG ganha t_flow_close (ALL_DONE) que registra SKIPPED
    para jobs pulados pelo ramo não escolhido — antes sumiam do Logs."""
    jobs = [_job("JobA"), _job("Decisao", jtype="decisao", order=2, cond=_contagem_cond()),
            _job("JobB", order=3), _job("JobC", order=3)]
    src = factory._generate_dag_source(_pipeline(), jobs)
    assert "def _flow_close(**context):" in src
    assert 't_flow_close = PythonOperator(' in src
    assert '"SKIPPED"' in src or "'SKIPPED'" in src
    # FLOW_JOBS só tem os executáveis (a decisão fica de fora)
    assert "FLOW_JOBS     = ['JobA', 'JobB', 'JobC']" in src
    # fecha antes do card de fim (o teams_end enxerga os SKIPPED gravados)
    assert "t_flow_close >> t_teams_end" in src


def test_pipeline_sem_decisao_nao_gera_flow_close(factory):
    jobs = [_job("JobA"), _job("JobB", order=2)]
    src = factory._generate_dag_source(_pipeline(), jobs)
    assert "t_flow_close" not in src


# ─────────────── flow_close: import real + fiação com nós especiais ──────────

def _exec_source(src):
    """Importa DE FATO a DAG gerada — pega NameError de tempo de carga (o que o
    Airflow faria ao importar o .py). Stuba ``utils.*`` e os módulos extras do
    Airflow (fora da lista deste arquivo) SÓ durante o exec."""
    import sys as _sys
    from unittest.mock import MagicMock as _MM
    extra_mods = (
        "utils", "utils.datastage_operator", "utils.conditions", "utils.job_operators",
        "airflow.operators.empty", "airflow.datasets", "airflow.utils",
        "airflow.utils.trigger_rule", "airflow.utils.state", "requests",
    )
    saved = {m: _sys.modules.get(m) for m in extra_mods}
    try:
        for m in extra_mods:
            _sys.modules[m] = _MM()
        exec(compile(src, "<dag>", "exec"), {})
    finally:
        for m, prev in saved.items():
            if prev is None:
                _sys.modules.pop(m, None)
            else:
                _sys.modules[m] = prev


def test_flow_close_compila_executa_e_liga_nos_especiais(factory):
    """Cenário completo: decisão + notificação + nó SQL. A fonte gerada precisa
    IMPORTAR (exec) e o flow_close tem de convergir ends + nós especiais e
    fechar antes do teams_end."""
    import ast as _ast
    import json as _json
    notify = {"grupo_id": 1, "template_id": None, "mensagem": "oi"}
    sqlcfg = {"sql": "SELECT 1", "mssql_conn_id": "CX", "database": "BI"}
    jobs = [
        _job("JobA"),
        {"job_name": "NoSQL", "job_type": "sql", "job_command": None,
         "execution_order": 2, "depends_on_jobs": "JobA",
         "sql_json": _json.dumps(sqlcfg)},
        _job("Decisao", jtype="decisao", order=3,
             cond={"tipo": "valor_sql", "source_job": "NoSQL", "comparacao": "numero",
                   "operador": ">", "valor": 0,
                   "ramo_verdadeiro": ["JobB"], "ramo_falso": ["AVISA"]}),
        _job("JobB", order=4),
        {"job_name": "AVISA", "job_type": "notificacao", "job_command": None,
         "execution_order": 4, "notify_json": _json.dumps(notify)},
    ]
    src = factory._generate_dag_source(_pipeline(), jobs)
    _ast.parse(src)
    _exec_source(src)
    assert "t_flow_close = PythonOperator(" in src
    # converge ends E nós especiais; fecha antes do card de fim
    assert ">> t_flow_close" in src
    assert "t_notif_AVISA >> t_flow_close" in src
    assert "t_sql_NoSQL >> t_flow_close" in src
    assert "t_flow_close >> t_teams_end" in src
    # FLOW_JOBS exclui decisão/notificação/sql
    assert "FLOW_JOBS     = ['JobA', 'JobB']" in src


def test_flow_close_sem_teams_end_compila(factory):
    """envia_msg_fim=0: flow_close existe sem a aresta para teams_end e a
    fonte continua importável (sem NameError de t_teams_end)."""
    import ast as _ast
    jobs = [_job("JobA"), _job("Decisao", jtype="decisao", order=2, cond=_contagem_cond()),
            _job("JobB", order=3), _job("JobC", order=3)]
    src = factory._generate_dag_source(_pipeline(envia_msg_fim=0), jobs)
    _ast.parse(src)
    _exec_source(src)
    assert "t_flow_close = PythonOperator(" in src
    assert "t_flow_close >> t_teams_end" not in src


# ─────────────── wall-clock nos cards gerados (regressão) ────────────────────

def test_teams_end_usa_relogio_de_parede(factory):
    """teams_end/teams_error medem DATEDIFF(MIN(start), MAX(end)) — a SOMA de
    duration_seconds inflava pipelines com jobs paralelos."""
    jobs = [_job("JobA"), _job("JobB", order=2)]
    src = factory._generate_dag_source(_pipeline(), jobs)
    assert src.count("DATEDIFF(SECOND, MIN(start_time), MAX(COALESCE(end_time, GETDATE())))") >= 2
    assert "COALESCE(SUM(duration_seconds)" not in src
