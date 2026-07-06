"""
Testes do rename transacional de job (onda 3) — helpers puros de
api/routers/jobs.py que reescrevem as referências por nome (CSV de dependências
e condition_json). O endpoint em si segue o padrão transacional de
save_pipeline_fluxo (uma conexão, commit/rollback) e é exercitado em produção;
aqui garantimos a regra de substituição, que é onde mora o risco.

Mesmo padrão do test_jobs_decisao.py: routers.jobs importado via fixture.
"""
from __future__ import annotations

import pytest


@pytest.fixture(scope="module")
def J():
    import routers.jobs as _j
    return _j


# ───────────────────────── depends_on_jobs (CSV) ────────────────────────────

def test_dep_csv_troca_membro_exato(J):
    assert J._rename_in_dep_csv("JobA,JobB,JobC", "JobB", "JobZ") == "JobA,JobZ,JobC"


def test_dep_csv_none_quando_nao_ha_referencia(J):
    assert J._rename_in_dep_csv("JobA,JobC", "JobB", "JobZ") is None
    assert J._rename_in_dep_csv("", "JobB", "JobZ") is None
    assert J._rename_in_dep_csv(None, "JobB", "JobZ") is None


def test_dep_csv_nao_casa_prefixo(J):
    # "JobA" não pode tocar "JobA2" nem "JobA_X" (troca por membro exato).
    assert J._rename_in_dep_csv("JobA2,JobA_X", "JobA", "JobZ") is None


def test_dep_csv_normaliza_espacos(J):
    assert J._rename_in_dep_csv(" JobA , JobB ", "JobA", "JobZ") == "JobZ,JobB"


def test_dep_csv_membro_repetido(J):
    assert J._rename_in_dep_csv("JobA,JobA", "JobA", "JobZ") == "JobZ,JobZ"


# ───────────────────────── condition_json ───────────────────────────────────

def test_condition_binaria_ramos(J):
    cond = {"tipo": "contagem", "ramo_verdadeiro": ["JobA", "JobB"], "ramo_falso": ["JobC"]}
    assert J._rename_in_condition(cond, "JobA", "JobZ") is True
    assert cond["ramo_verdadeiro"] == ["JobZ", "JobB"]
    assert cond["ramo_falso"] == ["JobC"]


def test_condition_switch_casos_e_senao(J):
    cond = {
        "tipo": "contagem",
        "casos": [
            {"nome": "a", "operador": ">", "valor": 1, "ramo": ["JobA"]},
            {"nome": "b", "operador": "=", "valor": 0, "ramo": ["JobB", "JobA"]},
        ],
        "ramo_senao": ["JobA", "JobC"],
    }
    assert J._rename_in_condition(cond, "JobA", "JobZ") is True
    assert cond["casos"][0]["ramo"] == ["JobZ"]
    assert cond["casos"][1]["ramo"] == ["JobB", "JobZ"]
    assert cond["ramo_senao"] == ["JobZ", "JobC"]


def test_condition_linhas_job_e_source_job(J):
    cond = {"tipo": "linhas_job", "job_name": "JobA", "child_job": "JobA"}
    assert J._rename_in_condition(cond, "JobA", "JobZ") is True
    assert cond["job_name"] == "JobZ"
    # child_job é nome de job-filho do DataStage — NÃO muda.
    assert cond["child_job"] == "JobA"

    cond2 = {"tipo": "valor_sql", "source_job": "NoSQL"}
    assert J._rename_in_condition(cond2, "NoSQL", "NoSQL2") is True
    assert cond2["source_job"] == "NoSQL2"


def test_condition_sem_referencia_retorna_false(J):
    cond = {"tipo": "contagem", "ramo_verdadeiro": ["JobB"], "ramo_falso": []}
    assert J._rename_in_condition(cond, "JobA", "JobZ") is False
    assert cond["ramo_verdadeiro"] == ["JobB"]


def test_condition_nao_dict(J):
    assert J._rename_in_condition(None, "a", "b") is False
    assert J._rename_in_condition("x", "a", "b") is False


def test_rename_valida_nome_estrito(J):
    # O endpoint recusa nome com espaço (task_id no Airflow) — regra do strict.
    assert J._JOB_NAME_STRICT_RE.match("Job_Novo-1.a")
    assert not J._JOB_NAME_STRICT_RE.match("Job Novo")
    assert not J._JOB_NAME_STRICT_RE.match("")
