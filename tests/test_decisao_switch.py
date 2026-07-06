"""
Testes da Decisão v2 — SWITCH (N-way) — onda 3.

Cobre as três camadas:
  - validação/normalização no backend (routers.jobs — funções puras);
  - avaliação em runtime (utils/conditions.eval_switch — primeiro caso vence);
  - DAG gerada pela factory (BranchPythonOperator com mapa caso→t_start e
    retrocompatibilidade byte-a-byte do caminho binário).

Segue o padrão dos testes vizinhos: routers.jobs importado via fixture (não no
topo), módulos de dags/ carregados com o Airflow stubado em sys.modules.
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
def J():
    import routers.jobs as _j
    return _j


@pytest.fixture(scope="module")
def factory():
    return _load_module("etl_dag_factory_switch_test", "dags/etl_dag_factory.py")


@pytest.fixture(scope="module")
def conditions():
    return _load_module("conditions_switch_test", "dags/utils/conditions.py")


_JOBS = {"Decisao", "JobA", "JobB", "JobC", "JobD"}


def _cond_switch(**ov):
    base = {
        "tipo": "contagem", "tabela": "dbo.FatoVendas",
        "casos": [
            {"nome": "alto", "operador": ">", "valor": 10000, "ramo": ["JobB"]},
            {"nome": "zerado", "operador": "=", "valor": 0, "ramo": ["JobC"]},
        ],
        "ramo_senao": ["JobD"],
        "on_error": "falhar",
    }
    base.update(ov)
    return base


# ───────────────────────── validação (routers.jobs) ─────────────────────────

def test_switch_valido_sem_erros(J):
    assert J._validate_condition(_cond_switch(), _JOBS, "Decisao", None) == []


def test_switch_nao_exige_operador_valor_no_topo(J):
    cond = _cond_switch()
    assert "operador" not in cond and "valor" not in cond
    assert J._validate_condition(cond, _JOBS, "Decisao", None) == []


def test_switch_casos_vazio_ou_nao_lista(J):
    errs = J._validate_condition(_cond_switch(casos=[]), _JOBS, "Decisao", None)
    assert any("ao menos um caso" in e for e in errs)
    errs = J._validate_condition(_cond_switch(casos="x"), _JOBS, "Decisao", None)
    assert any("ao menos um caso" in e for e in errs)


def test_switch_limite_de_casos(J):
    casos = [{"nome": f"c{i}", "operador": "=", "valor": i, "ramo": ["JobB"] if i == 0 else []}
             for i in range(11)]
    errs = J._validate_condition(_cond_switch(casos=casos), _JOBS, "Decisao", None)
    assert any("no máximo 10" in e for e in errs)


def test_switch_nome_obrigatorio_reservado_repetido(J):
    casos = [
        {"operador": ">", "valor": 1, "ramo": ["JobB"]},                    # sem nome
        {"nome": "senao", "operador": "=", "valor": 0, "ramo": []},         # reservado
        {"nome": "x", "operador": "<", "valor": 5, "ramo": []},
        {"nome": "x", "operador": ">", "valor": 9, "ramo": []},             # repetido
    ]
    errs = J._validate_condition(_cond_switch(casos=casos), _JOBS, "Decisao", None)
    assert any("nome é obrigatório" in e for e in errs)
    assert any("reservado" in e for e in errs)
    assert any("repetido" in e for e in errs)


def test_switch_operador_e_valor_por_caso(J):
    casos = [
        {"nome": "a", "operador": "!!", "valor": 1, "ramo": ["JobB"]},
        {"nome": "b", "operador": ">", "valor": "", "ramo": []},
        {"nome": "c", "operador": ">", "valor": "abc", "ramo": []},  # contagem → numérico
    ]
    errs = J._validate_condition(_cond_switch(casos=casos), _JOBS, "Decisao", None)
    assert any("caso 'a': operador inválido" in e for e in errs)
    assert any("caso 'b': valor é obrigatório" in e for e in errs)
    assert any("caso 'c': valor deve ser numérico" in e for e in errs)


def test_switch_valor_texto_ok_em_valor_sql(J):
    cond = _cond_switch(
        tipo="valor_sql", source_job="JobA", comparacao="texto",
        casos=[{"nome": "a", "operador": "=", "valor": "APROVADO", "ramo": ["JobB"]}],
        ramo_senao=[],
    )
    cond.pop("tabela", None)
    assert J._validate_condition(cond, _JOBS, "Decisao", None) == []


def test_switch_membros_invalidos(J):
    casos = [
        {"nome": "a", "operador": ">", "valor": 1, "ramo": ["Decisao"]},   # a própria decisão
        {"nome": "b", "operador": "=", "valor": 0, "ramo": ["Fantasma"]},  # inexistente
    ]
    errs = J._validate_condition(_cond_switch(casos=casos, ramo_senao=[]), _JOBS, "Decisao", None)
    assert any("própria decisão" in e for e in errs)
    assert any("'Fantasma' não existe" in e for e in errs)


def test_switch_job_em_dois_ramos(J):
    casos = [
        {"nome": "a", "operador": ">", "valor": 1, "ramo": ["JobB"]},
        {"nome": "b", "operador": "=", "valor": 0, "ramo": ["JobB"]},
    ]
    errs = J._validate_condition(_cond_switch(casos=casos, ramo_senao=[]), _JOBS, "Decisao", None)
    assert any("mais de um ramo" in e for e in errs)


def test_switch_job_repetido_no_senao(J):
    errs = J._validate_condition(_cond_switch(ramo_senao=["JobB"]), _JOBS, "Decisao", None)
    assert any("mais de um ramo" in e for e in errs)


def test_switch_sem_nenhum_membro(J):
    casos = [{"nome": "a", "operador": ">", "valor": 1, "ramo": []}]
    errs = J._validate_condition(_cond_switch(casos=casos, ramo_senao=[]), _JOBS, "Decisao", None)
    assert any("ao menos um job em algum ramo" in e for e in errs)


def test_switch_caso_com_ramo_vazio_e_valido(J):
    # caso que "encerra o fluxo" quando casa — legítimo, desde que exista algum membro
    casos = [
        {"nome": "para", "operador": "=", "valor": 0, "ramo": []},
        {"nome": "segue", "operador": ">", "valor": 0, "ramo": ["JobB"]},
    ]
    assert J._validate_condition(
        _cond_switch(casos=casos, ramo_senao=[]), _JOBS, "Decisao", None) == []


def test_switch_nao_mistura_com_ramos_binarios(J):
    errs = J._validate_condition(
        _cond_switch(ramo_verdadeiro=["JobB"]), _JOBS, "Decisao", None)
    assert any("não pode ter ramo_verdadeiro/ramo_falso" in e for e in errs)


def test_switch_on_error(J):
    assert J._validate_condition(_cond_switch(on_error="senao"), _JOBS, "Decisao", None) == []
    errs = J._validate_condition(_cond_switch(on_error="ramo_falso"), _JOBS, "Decisao", None)
    assert any("on_error" in e for e in errs)


def test_binaria_continua_validando_igual(J):
    cond = {"tipo": "contagem", "tabela": "dbo.X", "operador": ">", "valor": 1,
            "ramo_verdadeiro": ["JobB"], "ramo_falso": []}
    assert J._validate_condition(cond, _JOBS, "Decisao", None) == []
    cond["on_error"] = "senao"   # 'senao' NÃO vale no modo binário
    errs = J._validate_condition(cond, _JOBS, "Decisao", None)
    assert any("on_error" in e for e in errs)


# ───────────────────────── normalize / membros ──────────────────────────────

def test_normalize_switch_limpa_e_carimba(J):
    out = J._normalize_condition(_cond_switch(
        casos=[{"nome": "  a  ", "operador": " > ", "valor": 1, "ramo": [" JobB ", ""]}],
        ramo_senao=[" JobD ", ""],
        ramo_verdadeiro=[], ramo_falso=[],
        on_error="",
    ))
    assert out["casos"] == [{"nome": "a", "operador": ">", "valor": 1, "ramo": ["JobB"]}]
    assert out["ramo_senao"] == ["JobD"]
    assert "ramo_verdadeiro" not in out and "ramo_falso" not in out
    assert out["on_error"] == "falhar"


def test_normalize_switch_preserva_senao(J):
    out = J._normalize_condition(_cond_switch(on_error="senao"))
    assert out["on_error"] == "senao"


def test_condition_branch_members(J):
    assert J._condition_branch_members(_cond_switch()) == ["JobB", "JobC", "JobD"]
    binaria = {"ramo_verdadeiro": ["JobA"], "ramo_falso": ["JobB"]}
    assert J._condition_branch_members(binaria) == ["JobA", "JobB"]
    assert J._condition_branch_members(None) == []


def test_ciclo_com_aresta_de_caso(J):
    # Decisão → JobB (via caso) e JobB → Decisao (via dependência) = ciclo
    adj = {"Decisao": set(), "JobB": {"Decisao"}}
    for m in J._condition_branch_members(_cond_switch(ramo_senao=[])):
        if m in adj:
            adj["Decisao"].add(m)
    assert J._graph_has_cycle(adj) is True


# ───────────────────────── runtime (eval_switch) ─────────────────────────────

class _FakeTI:
    def __init__(self, value):
        self._value = value

    def xcom_pull(self, task_ids=None):
        return self._value


def _cond_switch_valor_sql(valor_casos, on_error="falhar"):
    return {
        "tipo": "valor_sql", "source_job": "NoSQL", "comparacao": "numero",
        "casos": valor_casos, "ramo_senao": [], "on_error": on_error,
    }


def test_eval_switch_primeiro_caso_vence(conditions):
    cond = _cond_switch_valor_sql([
        {"nome": "alto", "operador": ">", "valor": 100},
        {"nome": "medio", "operador": ">", "valor": 10},   # 500 também casaria aqui
    ])
    caso, obtido = conditions.eval_switch(cond, "conn", ti=_FakeTI(500))
    assert caso == "alto" and obtido == 500


def test_eval_switch_ordem_importa(conditions):
    cond = _cond_switch_valor_sql([
        {"nome": "medio", "operador": ">", "valor": 10},
        {"nome": "alto", "operador": ">", "valor": 100},
    ])
    caso, _ = conditions.eval_switch(cond, "conn", ti=_FakeTI(500))
    assert caso == "medio"


def test_eval_switch_nenhum_casa_vai_para_senao(conditions):
    cond = _cond_switch_valor_sql([
        {"nome": "alto", "operador": ">", "valor": 100},
        {"nome": "zerado", "operador": "=", "valor": 0},
    ])
    caso, obtido = conditions.eval_switch(cond, "conn", ti=_FakeTI(50))
    assert caso == "senao" and obtido == 50


def test_eval_switch_fail_loud_sem_ti(conditions):
    cond = _cond_switch_valor_sql([{"nome": "a", "operador": ">", "valor": 1}])
    with pytest.raises(ValueError):
        conditions.eval_switch(cond, "conn", ti=None)


def test_eval_switch_on_error_senao_degrada(conditions):
    cond = _cond_switch_valor_sql(
        [{"nome": "a", "operador": ">", "valor": 1}], on_error="senao")
    caso, obtido = conditions.eval_switch(cond, "conn", ti=None)
    assert caso == "senao" and obtido is None


def test_eval_switch_comparacao_texto(conditions):
    cond = {
        "tipo": "valor_sql", "source_job": "NoSQL", "comparacao": "texto",
        "on_error": "falhar", "ramo_senao": [],
        "casos": [{"nome": "aprovado", "operador": "=", "valor": "OK"}],
    }
    caso, _ = conditions.eval_switch(cond, "conn", ti=_FakeTI("OK"))
    assert caso == "aprovado"


def test_eval_condition_binaria_inalterada(conditions):
    # regressão do refactor (_obter_valor): binária segue retornando (bool, valor)
    cond = {"tipo": "valor_sql", "source_job": "NoSQL", "comparacao": "numero",
            "operador": ">", "valor": 10, "on_error": "falhar"}
    resultado, obtido = conditions.eval_condition(cond, "conn", ti=_FakeTI(50))
    assert resultado is True and obtido == 50


# ───────────────────────── factory (DAG gerada) ──────────────────────────────

def _pipeline(**overrides):
    base = {
        "pipeline_name": "PIPE_SWITCH", "project_name": "BI_CVP", "domain": "TESTE",
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
        j["condition_json"] = json.dumps(cond)
    return j


def _jobs_switch(cond=None):
    return [
        _job("JobA", order=1),
        _job("Decisao", jtype="decisao", order=2, depends="JobA",
             cond=cond or {
                 "tipo": "contagem", "tabela": "dbo.FatoVendas",
                 "casos": [
                     {"nome": "alto", "operador": ">", "valor": 10000, "ramo": ["JobB"]},
                     {"nome": "zerado", "operador": "=", "valor": 0, "ramo": ["JobC"]},
                 ],
                 "ramo_senao": ["JobD"], "on_error": "falhar",
             }),
        _job("JobB", order=3, depends=""),
        _job("JobC", order=4, depends=""),
        _job("JobD", order=5, depends=""),
    ]


def test_switch_gera_branch_e_compila(factory):
    src = factory._generate_dag_source(_pipeline(), _jobs_switch())
    ast.parse(src)
    assert "from utils.conditions import eval_condition, eval_switch" in src
    assert "def _decide_Decisao(" in src
    assert "eval_switch(cond, MSSQL_CONN_ID" in src
    assert "t_dec_Decisao = BranchPythonOperator(" in src
    assert ("_ramos = {'alto': ['log_start_JobB'], 'zerado': ['log_start_JobC'], "
            "'senao': ['log_start_JobD']}") in src
    assert "return _ramos.get(_caso, [])" in src


def test_switch_wiring_e_trigger_rules(factory):
    src = factory._generate_dag_source(_pipeline(), _jobs_switch())
    assert "t_end_JobA >> t_dec_Decisao" in src
    for j in ("JobB", "JobC", "JobD"):
        assert f"t_dec_Decisao >> t_start_{j}" in src
    # membros de caso/senão são branch_reachable → trigger tolerante a skip
    assert src.count("NONE_FAILED_MIN_ONE_SUCCESS") >= 3
    # flow_close continua sendo emitido (registro de SKIPPED, onda 2)
    assert "flow_close" in src


def test_switch_ramo_senao_vazio(factory):
    cond = {
        "tipo": "contagem", "tabela": "dbo.X",
        "casos": [{"nome": "a", "operador": ">", "valor": 1, "ramo": ["JobB"]}],
        "ramo_senao": [], "on_error": "falhar",
    }
    jobs = [
        _job("Decisao", jtype="decisao", order=1, cond=cond),
        _job("JobB", order=2, depends=""),
    ]
    src = factory._generate_dag_source(_pipeline(), jobs)
    ast.parse(src)
    assert "'senao': []" in src   # senão vazio = encerra o fluxo (branch devolve [])


def test_binaria_nao_importa_eval_switch(factory):
    jobs = [
        _job("JobA", order=1),
        _job("Decisao", jtype="decisao", order=2, depends="JobA",
             cond={"tipo": "contagem", "tabela": "dbo.X", "operador": ">", "valor": 1,
                   "ramo_verdadeiro": ["JobB"], "ramo_falso": []}),
        _job("JobB", order=3, depends=""),
    ]
    src = factory._generate_dag_source(_pipeline(), jobs)
    assert "eval_switch" not in src
    assert "from utils.conditions import eval_condition\n" in src


def test_switch_membro_notificacao_sem_log_start(factory):
    cond = {
        "tipo": "contagem", "tabela": "dbo.X",
        "casos": [{"nome": "avisa", "operador": ">", "valor": 1, "ramo": ["Aviso"]}],
        "ramo_senao": ["JobB"], "on_error": "falhar",
    }
    jobs = [
        _job("Decisao", jtype="decisao", order=1, cond=cond),
        _job("Aviso", jtype="notificacao", order=2, depends=""),
        _job("JobB", order=3, depends=""),
    ]
    jobs[1]["notify_json"] = json.dumps({"grupo_id": 1, "mensagem": "oi"})
    src = factory._generate_dag_source(_pipeline(), jobs)
    ast.parse(src)
    # notificação entra pelo próprio task_id (sem log_start_)
    assert "_ramos = {'avisa': ['Aviso'], 'senao': ['log_start_JobB']}" in src
