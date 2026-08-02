"""
Testes do nó Aguarde (ponto de encontro entre pernas paralelas) gerado pelo
etl_dag_factory.

Mesmo princípio dos demais testes de factory: módulos do Airflow stubados via
sys.modules antes do import; _generate_dag_source é função pura (gera string a
partir de dicts). Como nos testes de notificação e nó SQL, EXECUTAMOS a fonte
gerada (com utils stubados) para pegar NameError de tempo de carga — o que o
Airflow faria ao importar o .py, e que o ast.parse não pega.

⛔ O teste-âncora deste arquivo é ``test_ancora_end_tasks_intactas_em_todas_
terminarem``. Ele guarda o invariante de segurança da spec: com a política
'todas_terminarem' o Aguarde roda mesmo quando uma perna falha, e é justamente
esse tipo de regra que, numa task TERMINAL, fez todo pipeline falho aparecer
VERDE no Airflow (o que motivou a reversão da spec de dependências, PR #229).
Aqui isso não acontece porque o t_end de cada perna continua em end_tasks e
ligado ao fechamento — quem decide o estado do DagRun são as FOLHAS do grafo.
Se alguém refatorar isso, este teste quebra antes de chegar em produção.
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
    return _load_module("etl_dag_factory_aguarde_test", "dags/etl_dag_factory.py")


def _pipeline(**overrides):
    base = {
        "pipeline_name": "PIPE_AGUARDE", "project_name": "BI_CVP", "domain": "TESTE",
        "tags": "ETL", "scheduled_time": "06:00:00",
        "envia_msg_inicio": 0, "envia_msg_fim": 1, "envia_msg_erro": 1,
        "ambiente": "PROD", "schedule_type": "daily",
    }
    base.update(overrides)
    return base


def _job(name, jtype="datastage", order=1, depends=None, aguarde=None, cond=None):
    j = {"job_name": name, "job_type": jtype, "job_command": "ds.job",
         "execution_order": order}
    if depends is not None:
        j["depends_on_jobs"] = depends
    if aguarde is not None:
        j["aguarde_json"] = json.dumps(aguarde)
    if cond is not None:
        j["condition_json"] = json.dumps(cond)
    return j


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


def _duas_pernas(politica=None, limpeza=True):
    """O cenário da spec: JobA e JobB em paralelo, um Aguarde esperando os dois,
    e a limpeza dos arquivos compartilhados depois dele."""
    cfg = {"politica": politica} if politica else {}
    jobs = [
        _job("JobA", order=1),
        _job("JobB", order=1),
        _job("Encontro", jtype="aguarde", order=2, depends="JobA,JobB", aguarde=cfg),
    ]
    if limpeza:
        jobs.append(_job("LimpaArquivos", jtype="shell", order=3, depends="Encontro"))
    return jobs


# ───────────────────────── Estrutura do nó gerado ──────────────────────────

def test_aguarde_compila_e_importa(factory):
    src = factory._generate_dag_source(_pipeline(), _duas_pernas())
    ast.parse(src)
    _exec_source(src)
    assert "t_wait_Encontro = EmptyOperator(" in src


def test_aguarde_nao_tem_t_end_proprio(factory):
    """É nó especial: fica fora de end_tasks (não tem lineage a registrar)."""
    src = factory._generate_dag_source(_pipeline(), _duas_pernas())
    assert "t_end_Encontro" not in src
    assert "t_start_Encontro" not in src


def test_aguarde_espera_as_duas_pernas(factory):
    src = factory._generate_dag_source(_pipeline(), _duas_pernas())
    assert "[t_end_JobA, t_end_JobB] >> t_wait_Encontro" in src


def test_job_posterior_referencia_o_wait(factory):
    """Quem vem depois do Aguarde referencia t_wait_*, não t_end_* — que não
    existe e daria NameError no import da DAG."""
    src = factory._generate_dag_source(_pipeline(), _duas_pernas())
    assert "t_wait_Encontro >> t_start_LimpaArquivos" in src
    _exec_source(src)


# ───────────────────────── Política → trigger rule ─────────────────────────

def test_politica_default_exige_sucesso(factory):
    src = factory._generate_dag_source(_pipeline(), _duas_pernas())
    bloco = src[src.index("t_wait_Encontro = EmptyOperator("):]
    bloco = bloco[:bloco.index(")")]
    assert "TriggerRule.ALL_SUCCESS" in bloco


def test_politica_explicita_todas_sucesso(factory):
    src = factory._generate_dag_source(_pipeline(), _duas_pernas("todas_sucesso"))
    bloco = src[src.index("t_wait_Encontro = EmptyOperator("):]
    bloco = bloco[:bloco.index(")")]
    assert "TriggerRule.ALL_SUCCESS" in bloco


def test_politica_todas_terminarem(factory):
    src = factory._generate_dag_source(_pipeline(), _duas_pernas("todas_terminarem"))
    bloco = src[src.index("t_wait_Encontro = EmptyOperator("):]
    bloco = bloco[:bloco.index(")")]
    assert "TriggerRule.ALL_DONE" in bloco


def test_politica_desconhecida_cai_no_conservador(factory):
    """Defesa em profundidade: a API já rejeita, mas uma linha gravada à mão no
    banco não pode virar 'segue mesmo com falha' por acidente."""
    src = factory._generate_dag_source(_pipeline(), _duas_pernas("quando_der"))
    bloco = src[src.index("t_wait_Encontro = EmptyOperator("):]
    bloco = bloco[:bloco.index(")")]
    assert "TriggerRule.ALL_SUCCESS" in bloco


def test_aguarde_json_corrompido_nao_derruba_a_geracao(factory):
    jobs = _duas_pernas()
    jobs[2]["aguarde_json"] = "{isso nao e json"
    src = factory._generate_dag_source(_pipeline(), jobs)
    ast.parse(src)
    bloco = src[src.index("t_wait_Encontro = EmptyOperator("):]
    assert "TriggerRule.ALL_SUCCESS" in bloco[:bloco.index(")")]


# ───────────────────── Aguarde a jusante de uma Decisão ────────────────────

def _com_decisao(politica=None):
    """Decisão roteia para JobB; o Aguarde junta a perna do ramo com a perna
    fixa. O ramo NÃO escolhido chega SKIPPED no Aguarde."""
    cfg = {"politica": politica} if politica else {}
    cond = {"tipo": "linhas_job", "job_name": "JobA", "operador": ">", "valor": "0",
            "ramo_verdadeiro": ["JobB"], "ramo_falso": ["JobC"]}
    return [
        _job("JobA", order=1),
        _job("Dec", jtype="decisao", order=2, depends="JobA", cond=cond),
        _job("JobB", order=3),
        _job("JobC", order=3),
        _job("Encontro", jtype="aguarde", order=4, depends="JobB,JobC", aguarde=cfg),
        _job("LimpaArquivos", jtype="shell", order=5, depends="Encontro"),
    ]


def test_aguarde_apos_decisao_tolera_skip(factory):
    """Com ALL_SUCCESS, o ramo não escolhido (SKIPPED) travaria a junção para
    sempre — por isso a variante tolerante a skip."""
    src = factory._generate_dag_source(_pipeline(), _com_decisao())
    bloco = src[src.index("t_wait_Encontro = EmptyOperator("):]
    bloco = bloco[:bloco.index(")")]
    assert "TriggerRule.NONE_FAILED_MIN_ONE_SUCCESS" in bloco
    ast.parse(src)
    _exec_source(src)


def test_aguarde_apos_decisao_com_todas_terminarem(factory):
    """A política explícita ganha da tolerância a skip — ALL_DONE já cobre o
    ramo pulado."""
    src = factory._generate_dag_source(_pipeline(), _com_decisao("todas_terminarem"))
    bloco = src[src.index("t_wait_Encontro = EmptyOperator("):]
    bloco = bloco[:bloco.index(")")]
    assert "TriggerRule.ALL_DONE" in bloco


def test_aguarde_converge_no_flow_close_com_decisao(factory):
    src = factory._generate_dag_source(_pipeline(), _com_decisao())
    assert "t_wait_Encontro >> t_flow_close" in src


# ══════════════════════ TESTE-ÂNCORA DO INVARIANTE ═════════════════════════

def test_ancora_end_tasks_intactas_em_todas_terminarem(factory):
    """⛔ INVARIANTE: todo t_end de job real continua em end_tasks e ligado ao
    publish_dataset, mesmo com o Aguarde em 'todas_terminarem'.

    É isso que faz a limpeza rodar SEM esconder a falha: t_end_JobA falha (o
    log_end levanta quando o status é FAILED), o Aguarde roda assim mesmo e
    libera a limpeza, mas t_end_JobA continua sendo upstream do publish_dataset
    — que fica UPSTREAM_FAILED e derruba o DagRun.

    Se o Aguarde algum dia passar a INTERMEDIAR essa aresta (end_tasks →
    t_wait → publish), o pipeline falho volta a aparecer verde. Foi exatamente
    esse mecanismo que motivou a reversão da spec de dependências (PR #229).
    """
    src = factory._generate_dag_source(_pipeline(), _duas_pernas("todas_terminarem"))
    # as dep_lines saem indentadas dentro do bloco `with DAG(...)`
    linhas = [ln.strip() for ln in src.splitlines()]

    # 1) as duas pernas E a limpeza continuam em end_tasks
    linha_end = next(ln for ln in linhas if ln.startswith("end_tasks = ["))
    for perna in ("t_end_JobA", "t_end_JobB", "t_end_LimpaArquivos"):
        assert perna in linha_end, f"{perna} saiu de end_tasks — o DagRun deixaria de ficar vermelho"

    # 2) end_tasks vai DIRETO ao publish_dataset, sem o Aguarde no meio
    ligacao = next(ln for ln in linhas
                   if ln.endswith(">> t_publish_dataset") and ln.startswith("["))
    assert "t_end_JobA" in ligacao and "t_end_JobB" in ligacao
    assert "t_wait_" not in ligacao, "o Aguarde não pode intermediar o fechamento"

    # 3) o card de erro continua pendurado nas pernas (ONE_FAILED enxerga só
    #    upstream DIRETO — pendurar no Aguarde deixaria a task cega)
    erro = next(ln for ln in linhas
                if ln.endswith(">> t_teams_error") and ln.startswith("["))
    assert "t_end_JobA" in erro and "t_end_JobB" in erro


def test_ancora_publish_nao_vira_all_done(factory):
    """O publish_dataset não pode herdar a tolerância do Aguarde: ele é FOLHA,
    e uma regra tolerante ali é o que pinta de verde um pipeline falho."""
    src = factory._generate_dag_source(_pipeline(), _duas_pernas("todas_terminarem"))
    bloco = src[src.index("t_publish_dataset = EmptyOperator("):]
    bloco = bloco[:bloco.index(")")]
    assert "ALL_DONE" not in bloco


# ─────────────────────────── Casos de borda ────────────────────────────────

def test_aguarde_na_ponta_do_fluxo_converge(factory):
    """Sem nada depois dele, o Aguarde ainda converge no fechamento em vez de
    ficar pendurado fora do grafo."""
    src = factory._generate_dag_source(_pipeline(), _duas_pernas(limpeza=False))
    assert "t_wait_Encontro >> t_publish_dataset" in src
    ast.parse(src)
    _exec_source(src)


def test_aguardes_encadeados(factory):
    jobs = [
        _job("JobA", order=1), _job("JobB", order=1),
        _job("Enc1", jtype="aguarde", order=2, depends="JobA,JobB"),
        _job("JobC", order=3, depends="Enc1"),
        _job("Enc2", jtype="aguarde", order=4, depends="Enc1,JobC"),
        _job("Fim", jtype="shell", order=5, depends="Enc2"),
    ]
    src = factory._generate_dag_source(_pipeline(), jobs)
    ast.parse(src)
    _exec_source(src)
    assert "[t_wait_Enc1, t_end_JobC] >> t_wait_Enc2" in src


def test_aguarde_com_tres_pernas(factory):
    jobs = [
        _job("JobA", order=1), _job("JobB", order=1), _job("JobC", order=1),
        _job("Encontro", jtype="aguarde", order=2, depends="JobA,JobB,JobC"),
        _job("Limpa", jtype="shell", order=3, depends="Encontro"),
    ]
    src = factory._generate_dag_source(_pipeline(), jobs)
    ast.parse(src)
    _exec_source(src)
    assert "[t_end_JobA, t_end_JobB, t_end_JobC] >> t_wait_Encontro" in src


def test_aguarde_ativa_modo_explicito(factory):
    """Um pipeline que tem Aguarde sai do modo ondas — senão a junção seria
    decidida por execution_order e o nó não teria efeito nenhum."""
    jobs = _duas_pernas()
    src = factory._generate_dag_source(_pipeline(), jobs)
    assert "t_wait_Encontro" in src
    assert "[t_end_JobA, t_end_JobB] >> t_wait_Encontro" in src


def test_notificacao_depois_do_aguarde(factory):
    """Nó especial dependendo de nó especial: a notificação referencia t_wait_*."""
    jobs = [
        _job("JobA", order=1), _job("JobB", order=1),
        _job("Encontro", jtype="aguarde", order=2, depends="JobA,JobB"),
        _job("Avisa", jtype="notificacao", order=3, depends="Encontro"),
    ]
    jobs[3]["notify_json"] = json.dumps({"grupo_id": 1, "template_id": None, "mensagem": "ok"})
    src = factory._generate_dag_source(_pipeline(), jobs)
    ast.parse(src)
    _exec_source(src)
    assert "t_wait_Encontro >> t_notif_Avisa" in src


# ──────────────── Matriz de combinações (compila E importa) ────────────────

@pytest.mark.parametrize("politica", [None, "todas_sucesso", "todas_terminarem"])
@pytest.mark.parametrize("com_decisao", [False, True])
@pytest.mark.parametrize("com_notificacao", [False, True])
def test_matriz_de_combinacoes(factory, politica, com_decisao, com_notificacao):
    """12 combinações: 3 políticas × com/sem decisão × com/sem notificação.

    Cada uma precisa gerar código que o Airflow conseguiria importar. É aqui
    que aparece NameError de referência a task inexistente — o ast.parse
    sozinho não pega, porque a string compila.
    """
    jobs = _com_decisao(politica) if com_decisao else _duas_pernas(politica)
    if com_notificacao:
        aviso = _job("Avisa", jtype="notificacao", order=9, depends="Encontro")
        aviso["notify_json"] = json.dumps(
            {"grupo_id": 1, "template_id": None, "mensagem": "fim"})
        jobs.append(aviso)
    src = factory._generate_dag_source(_pipeline(), jobs)
    ast.parse(src)
    _exec_source(src)
    assert "t_wait_Encontro = EmptyOperator(" in src


# ───────────────────────── Não-regressão ───────────────────────────────────

def test_pipeline_sem_aguarde_nao_muda(factory):
    """A DAG de um pipeline sem o nó novo não pode ganhar nada."""
    jobs = [_job("JobA", order=1), _job("JobB", order=2)]
    src = factory._generate_dag_source(_pipeline(), jobs)
    assert "t_wait_" not in src
    assert "EmptyOperator" in src  # o publish_dataset segue lá


def test_pipeline_sem_aguarde_segue_em_ondas(factory):
    """Sem deps explícitas nem nós especiais, o encadeamento por execution_order
    continua sendo o usado."""
    jobs = [_job("JobA", order=1), _job("JobB", order=2)]
    src = factory._generate_dag_source(_pipeline(), jobs)
    assert "t_end_JobA >> t_start_JobB" in src


def test_default_args_nao_referencia_helper(factory):
    """Guarda o gotcha do factory: no arquivo gerado as constantes saem ANTES
    dos helpers, então helper em default_args dá NameError no import."""
    src = factory._generate_dag_source(_pipeline(), _duas_pernas("todas_terminarem"))
    bloco = src[src.index("default_args"):]
    bloco = bloco[:bloco.index("}")]
    for proibido in ("teams_", "log_start", "log_end", "_flow_close", "_notify_"):
        assert proibido not in bloco
