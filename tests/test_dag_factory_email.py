"""
Testes do nó `email` gerado pelo etl_dag_factory (spec
docs/spec-notificacao-email.md, F2).

⛔ O teste-âncora deste arquivo é ``test_ancora_factory_nao_embute_a_config``.
Ele guarda a promessa que o usuário vai cobrar: **mudar destinatário, assunto
ou anexo na tela vale já na próxima corrida, sem republicar a DAG**. O nó de
notificação Teams faz o contrário — embute grupo_id/mensagem como literais no
código gerado — e é por isso que mexer nele hoje exige regerar as DAGs. Se
alguém "otimizar" o `_email_block` embutindo a config, este teste quebra antes
de chegar em produção.

Mesmo padrão dos demais testes de factory: Airflow stubado antes do import,
`_generate_dag_source` é pura, e a fonte gerada é EXECUTADA para pegar
NameError de tempo de carga (o que o ast.parse não pega).
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


@pytest.fixture(scope="module")
def factory():
    path = _ROOT / "dags/etl_dag_factory.py"
    spec = importlib.util.spec_from_file_location("etl_dag_factory_email_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _pipeline(**overrides):
    base = {
        "pipeline_name": "PIPE_EMAIL", "project_name": "BI_CVP", "domain": "TESTE",
        "tags": "ETL", "scheduled_time": "06:00:00",
        "envia_msg_inicio": 0, "envia_msg_fim": 1, "envia_msg_erro": 1,
        "ambiente": "PROD", "schedule_type": "daily",
    }
    base.update(overrides)
    return base


def _job(name, jtype="datastage", order=1, depends=None, notify=None, cond=None, ssh=None):
    j = {"job_name": name, "job_type": jtype, "job_command": "ds.job",
         "execution_order": order}
    if depends is not None:
        j["depends_on_jobs"] = depends
    if notify is not None:
        j["notify_json"] = json.dumps(notify)
    if cond is not None:
        j["condition_json"] = json.dumps(cond)
    if ssh is not None:
        j["ssh_conn_id"] = ssh
    return j


CONFIG_NO = {
    "assunto": "Carga {pipeline} concluída - {data}",
    "corpo": "Foram {linhas} linhas.",
    "html": False,
    "destinatarios": ["ana@cvp.com.br"],
    "incluir_pipeline": True,
    "anexo": {"raiz": "/dados/saida", "nome": "relatorio_{odate}.xlsx"},
}


def _cenario(**kw):
    """Carga e, depois dela, o aviso por e-mail — o caso da spec."""
    return [
        _job("CargaVida", order=1),
        _job("AvisaEquipe", jtype="email", order=2, depends="CargaVida", notify=CONFIG_NO, **kw),
    ]


def _exec_source(src):
    util_mods = ("utils", "utils.datastage_operator", "utils.conditions",
                 "utils.job_operators", "utils.email_operator")
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


# ── âncora ──────────────────────────────────────────────────────────────────

def test_ancora_factory_nao_embute_a_config(factory):
    """A DAG gerada não pode conter assunto, corpo, destinatário nem anexo:
    tudo isso é lido do banco pelo operador, em tempo de corrida."""
    src = factory._generate_dag_source(_pipeline(), _cenario())
    for segredo in ("ana@cvp.com.br", "Carga {pipeline} concluída", "Foram {linhas} linhas",
                    "relatorio_{odate}.xlsx", "/dados/saida", "incluir_pipeline"):
        assert segredo not in src, f"config embutida na DAG: {segredo!r}"
    # o que ENTRA é só a identidade do nó
    assert "t_email_AvisaEquipe = EmailOperator(" in src
    assert "job_name='AvisaEquipe'" in src and "pipeline_name=PIPELINE_NAME" in src


# ── geração ─────────────────────────────────────────────────────────────────

def test_dag_com_no_de_email_compila_e_importa(factory):
    src = factory._generate_dag_source(_pipeline(), _cenario())
    ast.parse(src)
    _exec_source(src)


def test_importa_o_operador_so_quando_ha_no_de_email(factory):
    com = factory._generate_dag_source(_pipeline(), _cenario())
    sem = factory._generate_dag_source(_pipeline(), [_job("CargaVida", order=1)])
    assert "from utils.email_operator import EmailOperator" in com
    assert "email_operator" not in sem


def test_no_de_email_nao_tem_t_start_nem_t_end(factory):
    """É efeito colateral, como a notificação: sem lineage em etl_job_execution."""
    src = factory._generate_dag_source(_pipeline(), _cenario())
    assert "t_start_AvisaEquipe" not in src and "t_end_AvisaEquipe" not in src
    assert "t_end_CargaVida" in src        # a etapa de verdade continua com o dela


def test_no_de_email_fica_fora_de_end_tasks_e_de_flow_jobs(factory):
    src = factory._generate_dag_source(_pipeline(), _cenario())
    bloco = src[src.index("end_tasks"):src.index("end_tasks") + 400]
    assert "t_end_AvisaEquipe" not in bloco
    flow = src[src.index("FLOW_JOBS"):src.index("FLOW_JOBS") + 200]
    assert "AvisaEquipe" not in flow and "CargaVida" in flow


def test_liga_no_upstream_e_converge_no_fechamento(factory):
    src = factory._generate_dag_source(_pipeline(), _cenario())
    assert "t_end_CargaVida >> t_email_AvisaEquipe" in src
    # sem isso, um e-mail na PONTA do fluxo ficaria fora do grafo de fechamento
    assert "t_email_AvisaEquipe >> t_publish_dataset" in src
    assert "t_email_AvisaEquipe >> t_reg_falha" in src
    assert "t_email_AvisaEquipe >> t_teams_end" in src


def test_usa_a_conexao_ssh_do_no_quando_informada(factory):
    src = factory._generate_dag_source(_pipeline(), _cenario(ssh="ssh_outro_host"))
    assert 'ssh_conn_id="ssh_outro_host"' in src
    padrao = factory._generate_dag_source(_pipeline(), _cenario())
    assert "ssh_conn_id=SSH_CONN_ID," in padrao


def test_email_no_ramo_de_uma_decisao_usa_trigger_rule_tolerante(factory):
    """O ramo não escolhido chega SKIPPED; com ALL_SUCCESS o e-mail do outro
    ramo nunca rodaria."""
    cond = {"job_name": "Decide", "tipo": "valor_sql", "ramo_verdadeiro": ["AvisaEquipe"],
            "ramo_falso": [], "operador": ">", "valor": "0",
            "mssql_conn_id": "SQL14_DMDB41", "sql": "SELECT 1"}
    jobs = [
        _job("CargaVida", order=1),
        _job("Decide", jtype="decisao", order=2, depends="CargaVida", cond=cond),
        _job("AvisaEquipe", jtype="email", order=3, notify=CONFIG_NO),
    ]
    src = factory._generate_dag_source(_pipeline(), jobs)
    bloco = src[src.index("t_email_AvisaEquipe = EmailOperator("):]
    assert "TriggerRule.NONE_FAILED_MIN_ONE_SUCCESS" in bloco[:400]
    _exec_source(src)


def test_dois_nos_de_email_no_mesmo_pipeline(factory):
    jobs = [
        _job("CargaVida", order=1),
        _job("AvisaEquipe", jtype="email", order=2, depends="CargaVida", notify=CONFIG_NO),
        _job("AvisaGestor", jtype="email", order=3, depends="AvisaEquipe", notify=CONFIG_NO),
    ]
    src = factory._generate_dag_source(_pipeline(), jobs)
    assert "t_email_AvisaEquipe >> t_email_AvisaGestor" in src   # _end_ref conhece o tipo
    _exec_source(src)


def test_nome_com_espaco_vira_identificador_valido(factory):
    jobs = [_job("CargaVida", order=1),
            _job("Avisa Equipe BI", jtype="email", order=2, depends="CargaVida", notify=CONFIG_NO)]
    src = factory._generate_dag_source(_pipeline(), jobs)
    assert "t_email_Avisa_Equipe_BI = EmailOperator(" in src
    assert "task_id='Avisa Equipe BI'" in src        # o task_id preserva o nome real
    ast.parse(src)


def test_config_gravada_corrompida_nao_impede_a_geracao(factory):
    """O factory nem lê a config; JSON quebrado é problema do operador (que
    falha com mensagem), nunca do gerador."""
    job = _job("AvisaEquipe", jtype="email", order=2, depends="CargaVida")
    job["notify_json"] = "{lixo"
    src = factory._generate_dag_source(_pipeline(), [_job("CargaVida", order=1), job])
    ast.parse(src)
    assert "t_email_AvisaEquipe = EmailOperator(" in src


# ── não-regressão ───────────────────────────────────────────────────────────

def test_pipeline_sem_email_nao_muda(factory):
    jobs = [_job("JobA", order=1), _job("JobB", order=2)]
    src = factory._generate_dag_source(_pipeline(), jobs)
    assert "t_email_" not in src and "EmailOperator" not in src
    assert "t_end_JobA >> t_start_JobB" in src


def test_notificacao_teams_segue_intacta_ao_lado_do_email(factory):
    notify_teams = {"grupo_id": 3, "template_id": None, "mensagem": "fim"}
    jobs = [
        _job("CargaVida", order=1),
        _job("Card", jtype="notificacao", order=2, depends="CargaVida", notify=notify_teams),
        _job("AvisaEquipe", jtype="email", order=3, depends="CargaVida", notify=CONFIG_NO),
    ]
    src = factory._generate_dag_source(_pipeline(), jobs)
    assert "t_notif_Card = PythonOperator(" in src
    assert "t_email_AvisaEquipe = EmailOperator(" in src
    # F3: o nó Teams também deixou de embutir a config (grupo/modelo/mensagem)
    assert "_grupo_id = 3" not in src and "fim" not in src.split("def _notify_Card")[1][:300]
    _exec_source(src)


# ── âncora do roteamento por decisão (achado da revisão da F2) ──────────────

def test_ancora_decisao_roteia_nos_especiais_pelo_proprio_task_id(factory):
    """⛔ Um nó SEM t_start (e-mail, sql, aguarde, notificação) não tem task
    `log_start_<nome>`. Se o branch apontar para ela, o BranchPythonOperator
    levanta "'branch_task_ids' must contain only valid task_ids": a DECISÃO
    falha e derruba o pipeline na primeira corrida depois de publicar — e o
    e-mail, que era o ponto do ramo, nunca sai."""
    cond = {"job_name": "Decide", "tipo": "valor_sql", "comparacao": "numero",
            "ramo_verdadeiro": ["OkEtapa"], "ramo_falso": ["AvisaEmail", "AvisaTeams", "Consulta", "Espera"],
            "operador": ">", "valor": "0", "source_job": "Consulta", "mssql_conn_id": "SQL14_DMDB41"}
    notify_teams = {"grupo_id": 3, "template_id": None, "mensagem": "fim"}
    jobs = [
        _job("CargaVida", order=1),
        _job("Decide", jtype="decisao", order=2, depends="CargaVida", cond=cond),
        _job("OkEtapa", order=3),
        _job("AvisaEmail", jtype="email", order=3, notify=CONFIG_NO),
        _job("AvisaTeams", jtype="notificacao", order=3, notify=notify_teams),
        _job("Consulta", jtype="sql", order=3),
        _job("Espera", jtype="aguarde", order=3),
    ]
    src = factory._generate_dag_source(_pipeline(), jobs)
    ramo = src[src.index("return ["):src.index("return [") + 220]
    # etapa comum entra pelo log_start_; nó especial entra pelo próprio nome
    assert "'log_start_OkEtapa'" in ramo
    for especial in ("AvisaEmail", "AvisaTeams", "Consulta", "Espera"):
        assert f"'log_start_{especial}'" not in ramo, f"{especial} roteado por task inexistente"
        assert f"'{especial}'" in ramo
    _exec_source(src)


def test_decisao_so_com_etapas_comuns_segue_igual(factory):
    """Não-regressão: fluxo sem nó especial no ramo gera o mesmo de antes."""
    cond = {"job_name": "Decide", "tipo": "contagem", "ramo_verdadeiro": ["A"], "ramo_falso": ["B"],
            "operador": ">", "valor": "0", "tabela": "dbo.x", "mssql_conn_id": "SQL14_DMDB41"}
    jobs = [_job("Decide", jtype="decisao", order=1, cond=cond),
            _job("A", order=2), _job("B", order=2)]
    src = factory._generate_dag_source(_pipeline(), jobs)
    assert "['log_start_A']" in src and "['log_start_B']" in src


# ── âncora do skip (achado da revisão da F4) ────────────────────────────────

def test_ancora_canal_desligado_nao_arrasta_o_resto_do_fluxo(factory):
    """⛔ O canal desligado no Admin faz o nó levantar AirflowSkipException.

    Com a trigger rule padrão (ALL_SUCCESS), esse pulo desce por tudo que vem
    depois — INCLUSIVE o `publish_dataset`. E publish pulado significa: a
    corrida não registra SUCESSO, o Dataset não é publicado e a cascata de
    pipelines dependentes NÃO dispara. Tudo isso com as tasks verdes ou
    puladas, ou seja, sem ninguém perceber.

    Desligar o canal é justamente o gesto que o manual recomenda para suspender
    envios, e o roteiro de smoke manda fazer — não pode ter esse efeito."""
    jobs = [
        _job("CargaVida", order=1),
        _job("AvisaEquipe", jtype="email", order=2, depends="CargaVida", notify=CONFIG_NO),
        _job("CargaDois", order=3, depends="AvisaEquipe"),
    ]
    src = factory._generate_dag_source(_pipeline(), jobs)

    publish = src[src.index('task_id="publish_dataset"'):]
    assert "NONE_FAILED_MIN_ONE_SUCCESS" in publish[:400], (
        "publish_dataset seria PULADO junto com o nó de e-mail: sem SUCESSO da "
        "corrida e sem disparar os dependentes")

    filho = src[src.index("t_start_CargaDois = "):]
    assert "NONE_FAILED_MIN_ONE_SUCCESS" in filho[:400], (
        "a etapa seguinte ao nó de e-mail seria pulada junto")
    _exec_source(src)


def test_nos_a_jusante_de_email_em_cadeia_tambem_toleram(factory):
    """O pulo desce por toda a cadeia, não só pelo filho direto."""
    jobs = [
        _job("A", order=1),
        _job("Avisa", jtype="email", order=2, depends="A", notify=CONFIG_NO),
        _job("B", order=3, depends="Avisa"),
        _job("C", order=4, depends="B"),
    ]
    src = factory._generate_dag_source(_pipeline(), jobs)
    for nome in ("t_start_B", "t_start_C"):
        bloco = src[src.index(f"{nome} = "):]
        assert "NONE_FAILED_MIN_ONE_SUCCESS" in bloco[:400], f"{nome} seria arrastado pelo pulo"


def test_pipeline_sem_email_nao_ganha_trigger_rule_tolerante(factory):
    """Não-regressão: sem nó de e-mail (nem decisão/notificação/SQL), o publish
    e as etapas seguem com a regra padrão."""
    jobs = [_job("A", order=1), _job("B", order=2, depends="A")]
    src = factory._generate_dag_source(_pipeline(), jobs)
    publish = src[src.index('task_id="publish_dataset"'):src.index('task_id="publish_dataset"') + 300]
    assert "NONE_FAILED_MIN_ONE_SUCCESS" not in publish
    filho = src[src.index("t_start_B = "):src.index("t_start_B = ") + 300]
    assert "NONE_FAILED_MIN_ONE_SUCCESS" not in filho
