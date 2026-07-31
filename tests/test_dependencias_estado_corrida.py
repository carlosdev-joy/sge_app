"""
Correção B da revisão adversarial: estado da corrida com chave estável.

Quatro defeitos, todos levando ao mesmo lugar — corrida que nunca fecha e
dependente que nunca libera, em silêncio:

  1. push/guardiã inseriam com execution_id NULL e a DAG atualizava por
     ts_nodash → duas linhas, a reserva presa em EXECUTANDO para sempre;
  2. PULADO gravava `inicio` e mascarava o SUCESSO da mesma data;
  3. EXECUTANDO commitado antes do trigger_dag → trigger falho = corrida presa,
     sem redisparo e sem alerta;
  4. decisão-raiz com ramo vazio deixava o fechamento SKIPPED.
"""
from __future__ import annotations

import ast
import importlib.util
import json
import sys
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pytest

for _mod in [
    "airflow", "airflow.decorators", "airflow.models", "airflow.operators",
    "airflow.operators.python", "airflow.operators.empty", "airflow.operators.bash",
    "airflow.providers.microsoft.mssql.hooks.mssql", "airflow.utils",
    "airflow.utils.trigger_rule", "airflow.sensors.external_task", "airflow.datasets",
    "pendulum", "airflow.providers.ssh.hooks.ssh", "airflow.utils.dates",
    "airflow.exceptions",
]:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

_ROOT = Path(__file__).parent.parent
_DAGS = _ROOT / "dags"
if str(_DAGS) not in sys.path:
    sys.path.insert(0, str(_DAGS))


def _load(name, relpath):
    spec = importlib.util.spec_from_file_location(name, _ROOT / relpath)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def factory():
    return _load("etl_dag_factory_estado_test", "dags/etl_dag_factory.py")


@pytest.fixture(scope="module")
def dep():
    return _load("dependencias_estado_test", "dags/utils/dependencias.py")


def _src(factory, **over):
    base = {
        "pipeline_name": "PIPE_X", "project_name": "BI_CVP", "domain": "T",
        "tags": "ETL", "scheduled_time": "07:00:00", "envia_msg_inicio": 0,
        "envia_msg_fim": 0, "envia_msg_erro": 1, "ambiente": "PROD",
        "schedule_type": "daily",
    }
    base.update(over)
    jobs = over.pop("_jobs", None) or [
        {"job_name": "A", "job_type": "python", "job_command": "m", "execution_order": 1}]
    return factory._generate_dag_source(base, jobs)


# ───────────────── 1. Adoção da reserva (uma linha por corrida) ────────────

def test_registro_adota_a_reserva_do_push(factory):
    """A linha criada pelo push tem execution_id NULL; a DAG precisa adotá-la."""
    src = _src(factory)
    bloco = src[src.index("def _registrar_execucao"):src.index("def registrar_inicio")]
    assert "execution_id IS NULL" in bloco
    assert "SET execution_id=%s" in bloco
    # A adoção vem DEPOIS da tentativa pelo próprio execution_id e ANTES do INSERT.
    i_update = bloco.index("AND execution_id=%s")
    i_adocao = bloco.index("execution_id IS NULL")
    i_insert = bloco.index("INSERT INTO dbo.etl_pipeline_execucao")
    assert i_update < i_adocao < i_insert


def test_pulado_nao_grava_inicio(factory):
    """PULADO com `inicio` ficava 'mais recente' e escondia o SUCESSO do dia."""
    src = _src(factory)
    bloco = src[src.index("def _registrar_execucao"):src.index("def registrar_inicio")]
    assert "CASE WHEN %s = 'PULADO' THEN NULL ELSE %s END" in bloco


# ───────────────── 2. SUCESSO na data vale, mesmo não sendo o último ───────

def test_sucesso_na_data_vale_mesmo_com_pulado_depois(dep):
    """Pipeline com horários 08:30/09:00 recebe disparos de cron às 08:00 e 09:30.

    Os dois viram PULADO. Antes, o PULADO das 09:30 era 'o mais recente' e
    escondia o SUCESSO das 09:00 — o dependente esperava para sempre.
    """
    hook = MagicMock()
    hook.get_records.return_value = [("PAI_A", "SUCESSO")]
    resultado = dep.status_dos_predecessores(hook, "FILHO", date(2026, 8, 1))
    assert resultado == {"PAI_A": "SUCESSO"}
    sql = hook.get_records.call_args[0][0]
    # É o EXISTS que implementa "houve sucesso na data", não o TOP 1.
    assert "EXISTS" in sql and "s.status = 'SUCESSO'" in sql
    assert sql.index("EXISTS") < sql.index("TOP 1")


def test_sem_sucesso_devolve_o_status_mais_recente(dep):
    """'Falhou' precisa ser distinguível de 'nem rodou' na mensagem."""
    hook = MagicMock()
    hook.get_records.return_value = [("PAI_A", "FALHA"), ("PAI_B", None)]
    r = dep.status_dos_predecessores(hook, "FILHO", date(2026, 8, 1))
    assert r == {"PAI_A": "FALHA", "PAI_B": None}
    _, pendentes = dep.avaliar_liberacao(r)
    assert pendentes == ["PAI_A", "PAI_B"]


def test_consulta_amarrada_a_data_nos_dois_ramos(dep):
    hook = MagicMock()
    hook.get_records.return_value = []
    dep.status_dos_predecessores(hook, "FILHO", date(2026, 8, 1))
    params = hook.get_records.call_args[1]["parameters"]
    # data_referencia entra no EXISTS e no TOP 1; o nome do pipeline por último.
    assert params == (date(2026, 8, 1), date(2026, 8, 1), "FILHO")


# ───────────────── 3. Trigger falho devolve a reserva ──────────────────────

def test_trigger_falho_devolve_a_reserva_para_a_guardia(factory):
    """Sem isto a corrida ficava presa em EXECUTANDO: a guardiã só age sobre
    AGUARDANDO_DEPENDENCIA, e o alerta também ignora EXECUTANDO."""
    src = _src(factory)
    bloco = src[src.index("def _disparar_dag"):]
    assert "trigger falhou" in bloco
    reversao = bloco[bloco.index("except Exception as e:"):]
    assert "SET status='AGUARDANDO_DEPENDENCIA'" in reversao
    # Só a RESERVA volta atrás — corrida real (com execution_id) não é revertida.
    assert "AND status='EXECUTANDO' AND execution_id IS NULL" in reversao


# ───────────────── 4. Fechamento com ramo vazio ────────────────────────────

def test_fechamento_roda_com_all_done(factory):
    src = _src(factory)
    bloco = src[src.index("t_exec_fim = PythonOperator("):]
    assert "TriggerRule.ALL_DONE" in bloco[:250]


def test_fechamento_nao_sobrescreve_estado_terminal(factory):
    """Com ALL_DONE o fechamento sempre roda; a guarda é que protege PULADO/FALHA."""
    src = _src(factory)
    bloco = src[src.index("def registrar_fim"):src.index("def _marcar_falha")
                if "_marcar_falha" in src else src.index("def registrar_falha")]
    assert "apenas_se_executando=True" in bloco
    reg = src[src.index("def _registrar_execucao"):src.index("def registrar_inicio")]
    assert "AND status = 'EXECUTANDO'" in reg
    # E não insere linha nova quando a guarda barra.
    assert "if _cur.rowcount == 0 and not apenas_se_executando:" in reg


def test_decisao_raiz_com_ramo_vazio_compila_e_fecha(factory):
    """O shape que deixava a corrida presa: decisão na raiz, um ramo vazio."""
    jobs = [
        {"job_name": "D", "job_type": "decisao", "job_command": "m", "execution_order": 1,
         "condition_json": json.dumps({"tipo": "contagem", "tabela": "dbo.T",
                                       "operador": ">", "valor": 1,
                                       "ramo_verdadeiro": ["B"], "ramo_falso": []})},
        {"job_name": "B", "job_type": "python", "job_command": "m",
         "execution_order": 2, "depends_on_jobs": ""},
    ]
    src = factory._generate_dag_source(
        {"pipeline_name": "PIPE_DEC", "project_name": "BI_CVP", "domain": "T",
         "tags": "ETL", "scheduled_time": "07:00:00", "envia_msg_inicio": 0,
         "envia_msg_fim": 0, "envia_msg_erro": 1, "ambiente": "PROD",
         "schedule_type": "daily"}, jobs)
    ast.parse(src)
    bloco = src[src.index("t_exec_fim = PythonOperator("):]
    assert "TriggerRule.ALL_DONE" in bloco[:250]


# ───────────────── 5. Disparo: guarda de estado e erro por filho ───────────

def test_disparo_exige_que_a_propria_corrida_tenha_sido_sucesso(factory):
    """Com ALL_DONE no fechamento, quem decide é o estado real da corrida."""
    src = _src(factory)
    bloco = src[src.index("def disparar_dependentes"):src.index("def _disparar_dag")]
    assert "dependentes nao liberados" in bloco
    assert "!= 'SUCESSO'" in bloco


def test_erro_em_um_dependente_nao_cancela_os_outros(factory):
    """O try estava FORA do laço: o primeiro erro abortava todos os demais."""
    src = _src(factory)
    bloco = src[src.index("def disparar_dependentes"):src.index("def _disparar_dag")]
    i_for = bloco.index("for _filho in _filhos:")
    assert "try:" in bloco[i_for:], "o laço precisa do try por item"
    assert "nao disparado" in bloco[i_for:]


def test_dag_gerada_continua_compilando(factory):
    for extra in ({}, {"depends_on": "PAI"}, {"envia_msg_fim": 1, "envia_msg_erro": 1}):
        ast.parse(_src(factory, **extra))
