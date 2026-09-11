"""
Testes do nó de Notificação (Teams) gerado pelo etl_dag_factory.

Mesmo princípio dos demais testes de factory: módulos do Airflow stubados via
sys.modules antes do import; _generate_dag_source é função pura (gera string a
partir de dicts).

Regressão principal (test_job_que_depende_de_notificacao_usa_t_notif): um job que
DEPENDE de um nó de notificação deve referenciar t_notif_<dep> — a notificação
NÃO tem t_end_ próprio. Antes gerava `NameError: name 't_end_<notif>' is not
defined` quando o Airflow importava a DAG (o ast.parse da factory não pega, pois
é erro de tempo de carga). Por isso os testes EXECUTAM a fonte (com utils
stubados), espelhando o import real do Airflow.
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
    return _load_module("etl_dag_factory_notif_test", "dags/etl_dag_factory.py")


def _pipeline(**overrides):
    base = {
        "pipeline_name": "PIPE_NOTIF", "project_name": "BI_CVP", "domain": "TESTE",
        "tags": "ETL", "scheduled_time": "06:00:00",
        "envia_msg_inicio": 0, "envia_msg_fim": 1, "envia_msg_erro": 1,
        "ambiente": "PROD", "schedule_type": "daily",
    }
    base.update(overrides)
    return base


def _job(name, jtype="datastage", order=1, depends=None, notify=None):
    j = {"job_name": name, "job_type": jtype, "job_command": "ds.job",
         "execution_order": order}
    if depends is not None:
        j["depends_on_jobs"] = depends
    if notify is not None:
        j["notify_json"] = json.dumps(notify)
    return j


_NOTIFY = {"grupo_id": 1, "template_id": None, "mensagem": "linhas {linhas}"}


def _exec_source(src):
    """Importa DE FATO a DAG gerada — pega NameError de tempo de carga, que é o
    que o Airflow faria ao importar o arquivo .py. Stuba ``utils.*`` SÓ durante o
    exec (e restaura), para não poluir a coleção de outros testes que importam o
    ``utils`` real (ex.: utils.dsx_engine)."""
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


def test_notificacao_terminal_compila_e_importa(factory):
    jobs = [_job("JobA"),
            _job("Notif", jtype="notificacao", order=2, depends="JobA", notify=_NOTIFY)]
    src = factory._generate_dag_source(_pipeline(), jobs)
    ast.parse(src)
    _exec_source(src)
    assert "t_notif_Notif = PythonOperator(" in src
    # notificação não entra em end_tasks (não tem t_end_ próprio)
    assert "t_end_Notif" not in src


def test_job_que_depende_de_notificacao_usa_t_notif(factory):
    """Regressão: JobB depende da notificação Notif → o wiring usa t_notif_Notif,
    NÃO t_end_Notif (inexistente → NameError no import do Airflow)."""
    jobs = [
        _job("JobA"),
        _job("Notif", jtype="notificacao", order=2, depends="JobA", notify=_NOTIFY),
        _job("JobB", order=3, depends="Notif"),
    ]
    src = factory._generate_dag_source(_pipeline(), jobs)
    ast.parse(src)
    _exec_source(src)  # NameError de carga aqui se regredir
    assert "t_notif_Notif >> t_start_JobB" in src
    assert "t_end_Notif" not in src


def test_notificacao_depende_de_notificacao(factory):
    """N2 depende de N1 (ambas notificação) → N1 conclui em t_notif_N1."""
    jobs = [
        _job("JobA"),
        _job("N1", jtype="notificacao", order=2, depends="JobA", notify=_NOTIFY),
        _job("N2", jtype="notificacao", order=3, depends="N1", notify=_NOTIFY),
    ]
    src = factory._generate_dag_source(_pipeline(), jobs)
    ast.parse(src)
    _exec_source(src)
    assert "t_notif_N1 >> t_notif_N2" in src


# ── F3: config do nó lida em runtime ────────────────────────────────────────

def test_ancora_dag_nao_embute_canal_modelo_nem_mensagem(factory):
    """⛔ Âncora da F3 (spec docs/spec-notificacao-email.md).

    Até aqui o factory escrevia `_grupo_id = 7`, `_template_id = 42` e a
    mensagem inteira dentro do código gerado: trocar o texto do card na tela
    não mudava nada até alguém regerar a DAG — e ninguém sabia disso. Agora o
    bloco emite só a identidade do nó, e o helper lê `notify_json` do banco no
    disparo, como o nó de e-mail já faz desde a F2.
    """
    cfg = {"grupo_id": 7, "template_id": 42, "mensagem": "Carga {pipeline} terminou"}
    jobs = [_job("Carga", order=1),
            _job("Avisa", jtype="notificacao", order=2, depends="Carga", notify=cfg)]
    src = factory._generate_dag_source(_pipeline(), jobs)

    bloco = src[src.index("def _notify_Avisa"):src.index("t_notif_Avisa = PythonOperator(")]
    for vazado in ("_grupo_id", "_template_id", "_mensagem", "42", "Carga {pipeline} terminou"):
        assert vazado not in bloco, f"config do nó ainda embutida na DAG: {vazado!r}"
    assert "_resolve_e_envia_notificacao(_job, _up_jobs, _exec_id, context)" in bloco

    # e o helper passou a buscar a config por (pipeline, job)
    assert "SELECT notify_json FROM dbo.etl_pipeline_job" in src
    assert "parameters=(PIPELINE_NAME, job)," in src
    _exec_source(src)


def _helper(factory, **hook_resp):
    """Executa o fonte gerado e devolve (helper, cards postados, hook de mentira).

    Verificar o comportamento pela EXECUÇÃO, não por `in src`: um teste que só
    procura texto passaria com a trava guardando a condição errada — foi
    exatamente o que a revisão adversarial desta fase pegou."""
    src = factory._generate_dag_source(
        _pipeline(), [_job("Avisa", jtype="notificacao", order=1,
                           notify={"grupo_id": 1, "template_id": None, "mensagem": "oi {pipeline}"})])
    cards, posts = [], []

    class _Hook:
        def __init__(self, *a, **k):
            pass

        def get_first(self, sql, parameters=None):
            if "notify_json" in sql:
                if hook_resp.get("erro_cfg"):
                    raise Exception(hook_resp["erro_cfg"])
                return hook_resp.get("notify_json", (None,))
            if "etl_msg_grupo" in sql:
                if hook_resp.get("erro_grupo"):
                    raise Exception(hook_resp["erro_grupo"])
                return hook_resp.get("grupo", None)
            return None

    ns = {}
    exec(compile(src, "<dag>", "exec"), ns)
    ns["MsSqlHook"] = _Hook
    ns["_teams_post_card"] = lambda **k: cards.append(k)
    ns["requests"] = type("R", (), {"post": staticmethod(lambda *a, **k: posts.append((a, k)) or
                                                        type("Resp", (), {"status_code": 200})())})
    return ns["_resolve_e_envia_notificacao"], cards, posts


def test_ancora_canal_que_nao_resolve_nao_cai_no_webhook_padrao(factory):
    """⛔ Âncora. Grupo apagado, inativo ou sem webhook: antes o card ia para o
    webhook padrão do Variable — task VERDE, aviso no canal errado, e quem
    deveria receber não recebia. É o falso verde que a revisão desta fase
    encontrou. Agora o card não é enviado e o log da task diz o motivo."""
    import json as _json
    cfg = (_json.dumps({"grupo_id": 7, "template_id": None, "mensagem": "oi"}),)
    for cenario in ({"grupo": None},                  # grupo apagado ou inativo
                    {"grupo": ("",)},                 # webhook_url vazio
                    {"erro_grupo": "timeout"}):       # erro ao consultar o grupo
        helper, cards, posts = _helper(factory, notify_json=cfg, **cenario)
        helper("Avisa", [], "20260911T060000", {"ti": None})
        assert cards == [], f"card foi para o webhook padrão em {cenario}"
        assert posts == [], f"card postado sem canal resolvido em {cenario}"


def test_ancora_nada_disso_derruba_a_corrida(factory):
    """⛔ Âncora. O card é aviso LATERAL e esta task nunca reprovou pipeline.
    Fazer isso agora travaria o Dataset e a cascata de dependentes por causa de
    um aviso — o nó apagado ou renomeado sem republicar viraria pipeline
    vermelho. Nenhum destes cenários pode levantar."""
    import json as _json
    cenarios = [
        {"notify_json": (None,)},                                   # nó apagado/renomeado
        {"erro_cfg": "Login timeout expired"},                      # banco de metadados fora
        {"notify_json": ("{lixo",)},                                # JSON corrompido
        {"notify_json": (_json.dumps(["lista"]),)},                 # JSON que não é objeto
        {"notify_json": (_json.dumps({"mensagem": "x"}),)},         # sem grupo_id
    ]
    for c in cenarios:
        helper, cards, posts = _helper(factory, **c)
        helper("Avisa", [], "20260911T060000", {"ti": None})        # não levanta
        assert cards == [] and posts == [], f"postou sem config em {c}"


def test_card_sai_com_a_config_lida_do_banco(factory):
    """O caminho feliz: grupo com webhook, mensagem vinda da tabela."""
    import json as _json
    cfg = (_json.dumps({"grupo_id": 7, "template_id": None, "mensagem": "oi {pipeline}"}),)
    helper, cards, posts = _helper(factory, notify_json=cfg, grupo=("https://webhook.exemplo/x",))
    helper("Avisa", [], "20260911T060000", {"ti": None})
    assert len(posts) == 1, "o card não foi postado no webhook do grupo"
    url, payload = posts[0][0][0], posts[0][1]["json"]
    assert url == "https://webhook.exemplo/x"
    # a mensagem veio da TABELA e o {pipeline} foi resolvido
    assert "oi PIPE_NOTIF" in str(payload)
    assert cards == []          # não caiu no webhook padrão do Variable


def test_jobs_a_montante_seguem_no_codigo_gerado(factory):
    """`_up_jobs` é TOPOLOGIA (as dependências já estão na DAG), não config:
    continua embutido, e é dele que sai o {linhas}."""
    jobs = [_job("Carga", order=1),
            _job("Avisa", jtype="notificacao", order=2, depends="Carga",
                 notify={"grupo_id": 1, "template_id": None, "mensagem": ""})]
    src = factory._generate_dag_source(_pipeline(), jobs)
    assert "_up_jobs = ['Carga']" in src
