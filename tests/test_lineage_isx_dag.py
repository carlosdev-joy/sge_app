"""Lineage ISX — F3 (spec docs/spec-lineage-isx.md): a DAG de lote `etl_lineage_extract_isx`.

Airflow não está instalado no ambiente de teste (padrão de tests/test_ds_supervisao_dag.py):
o módulo é carregado com stubs para o erro de *import time* aparecer aqui, e as
funções puras/tasks são exercitadas com hook, Connection, Variable e `requests`
falsos. A DAG nunca toca o banco para gravar: só lê a lista de jobs e chama a API.
"""
from __future__ import annotations

import importlib.util
import sys
import threading
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_ROOT = Path(__file__).parent.parent
_DAGS = _ROOT / "dags"
if str(_DAGS) not in sys.path:
    sys.path.insert(0, str(_DAGS))

_STUBS = [
    "airflow", "airflow.models", "airflow.hooks", "airflow.hooks.base",
    "airflow.operators", "airflow.operators.python",
    "airflow.providers", "airflow.providers.microsoft", "airflow.providers.microsoft.mssql",
    "airflow.providers.microsoft.mssql.hooks", "airflow.providers.microsoft.mssql.hooks.mssql",
    "pendulum",
]
for _m in _STUBS:
    sys.modules.setdefault(_m, MagicMock())
sys.modules["airflow"].DAG = MagicMock()
sys.modules["airflow"].DAG.return_value.__enter__ = lambda self: self
sys.modules["airflow"].DAG.return_value.__exit__ = lambda self, *a: False


def _carregar():
    spec = importlib.util.spec_from_file_location("etl_lineage_extract_isx_test", _DAGS / "etl_lineage_extract_isx.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


M = _carregar()

LINHAS = [("PIPE_VIDA", "SsdVidaDimePessoa02Ftp", "BI_VIDA"), ("PIPE_VIDA", "SeqSsdVidaDime", "BI_VIDA"),
          ("PIPE_VIDA", "JobRaiz", "BI_VIDA"), ("PIPE_VIDA", "CopyOfSsdVida", "BI_VIDA"),
          ("PIPE_CVP", "JobCvp", "BI_CVP")]


# ── dublês ───────────────────────────────────────────────────────────────────

class _Resp:
    def __init__(self, status, corpo):
        self.status_code = status
        self._corpo = corpo
        self.text = str(corpo)

    def json(self):
        if isinstance(self._corpo, str):
            raise ValueError("não é JSON")
        return self._corpo


class FakeSessao:
    """Responde por job: {job: (status, corpo) | Exception}. Conta threads simultâneas."""

    def __init__(self, respostas, demora=0.0):
        self.respostas = respostas
        self.demora = demora
        self.pedidos: list[dict] = []
        self.auths: set = set()
        self.urls: set = set()
        self.simultaneas = 0
        self.pico = 0
        self._lock = threading.Lock()

    def post(self, url, json=None, auth=None, timeout=None):
        with self._lock:
            self.simultaneas += 1
            self.pico = max(self.pico, self.simultaneas)
            self.pedidos.append(dict(json))
            self.auths.add(auth)
            self.urls.add(url)
        try:
            if self.demora:
                import time
                time.sleep(self.demora)
            r = self.respostas.get(json["job_name"], (200, {"cache_hit": False}))
            if isinstance(r, Exception):
                raise r
            assert timeout == M.TIMEOUT_JOB_S
            return _Resp(*r)
        finally:
            with self._lock:
                self.simultaneas -= 1

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _Ti:
    def __init__(self, lista):
        self.lista = lista

    def xcom_pull(self, task_ids):
        assert task_ids == "listar_jobs"
        return self.lista


def _ctx(conf=None, lista=None):
    dag_run = MagicMock()
    dag_run.conf = conf
    return {"dag_run": dag_run, "ti": _Ti(lista)}


@pytest.fixture
def airflow_falso(monkeypatch):
    hook = MagicMock()
    hook.get_records.return_value = list(LINHAS)
    monkeypatch.setattr(M, "MsSqlHook", MagicMock(return_value=hook))
    conn = MagicMock(login="svc_orq", password="s3nh4", host="orquestra-api", port=8000)
    monkeypatch.setattr(M.BaseHook, "get_connection", MagicMock(return_value=conn))
    monkeypatch.setattr(M.Variable, "get", MagicMock(return_value="http://orquestra-api:8000/"))
    return hook


# ── carga ────────────────────────────────────────────────────────────────────

def test_dag_carrega_e_tem_as_duas_tasks():
    assert M.DAG_ID == "etl_lineage_extract_isx" and M.MAX_WORKERS == 4 and M.TIMEOUT_JOB_S == 90
    assert M.ORIGEM == "dag:etl_lineage_extract_isx" and M.API_CONN_ID == "orquestra_api"
    # os stubs de sys.modules são compartilhados com os outros testes de DAG da suíte:
    # olha os objetos que ESTE módulo usou, filtrando pelo dag_id/task_id
    chamadas = [c.kwargs for c in M.PythonOperator.call_args_list
                if c.kwargs.get("task_id") in ("listar_jobs", "extrair_em_lote")]
    assert {c["task_id"] for c in chamadas} == {"listar_jobs", "extrair_em_lote"}
    assert all(c["do_xcom_push"] for c in chamadas)
    kw = [c.kwargs for c in M.DAG.call_args_list if c.kwargs.get("dag_id") == M.DAG_ID][-1]
    assert kw["schedule"] is None and kw["max_active_runs"] == 1 and "isx" in kw["tags"]


# ── puras ────────────────────────────────────────────────────────────────────

def test_filtrar_jobs_exclui_copias_e_respeita_o_filtro():
    todos = M.filtrar_jobs(LINHAS)
    assert [j["job_name"] for j in todos] == ["SsdVidaDimePessoa02Ftp", "SeqSsdVidaDime", "JobRaiz", "JobCvp"]
    assert todos[0] == {"pipeline_name": "PIPE_VIDA", "job_name": "SsdVidaDimePessoa02Ftp", "ds_project": "BI_VIDA"}
    assert [j["job_name"] for j in M.filtrar_jobs(LINHAS, incluir_copias=True)] == [l[1] for l in LINHAS]
    assert [j["job_name"] for j in M.filtrar_jobs(LINHAS, jobs=["jobraiz", " JobCvp "])] == ["JobRaiz", "JobCvp"]
    assert M.filtrar_jobs([("P", "", "X"), ("P", None, "X")]) == []


def test_classificar_e_resumir():
    assert M.classificar(200, {"cache_hit": True}) == ("cache", "")
    assert M.classificar(200, {"cache_hit": False, "stages": []}) == ("extraido", "")
    assert M.classificar(404, {"detail": "Job X não encontrado"}) == ("erro", "HTTP 404: Job X não encontrado")
    assert M.classificar(502, "<html>bad gateway</html>") == ("erro", "HTTP 502: <html>bad gateway</html>")
    assert M.classificar(None, "ConnectionError: x") == ("erro", "ConnectionError: x")
    r = M.resumir([{"pipeline_name": "P", "job_name": "A", "classe": "extraido"},
                   {"pipeline_name": "P", "job_name": "B", "classe": "cache"},
                   {"pipeline_name": "P", "job_name": "C", "classe": "erro", "status": 404, "detail": "x"}], 12.34)
    assert r == {"total": 3, "extraidos": 1, "cache": 1, "duracao_s": 12.3,
                 "erros": [{"pipeline_name": "P", "job_name": "C", "status": 404, "detail": "x"}]}


# ── listar_jobs ──────────────────────────────────────────────────────────────

def test_listar_jobs_por_pipeline_usa_placeholder_pymssql(airflow_falso):
    lista = M.listar_jobs(**_ctx({"pipeline_name": " PIPE_VIDA ", "jobs": ["JobRaiz"]}))
    sql, kwargs = airflow_falso.get_records.call_args.args[0], airflow_falso.get_records.call_args.kwargs
    assert "j.pipeline_name = %s" in sql and "?" not in sql and kwargs["parameters"] == ["PIPE_VIDA"]
    assert "ISNULL(p.project_name, '')" in sql and "ORDER BY j.pipeline_name, j.execution_order" in sql
    # só jobs DataStage (nós http/decisão/aguarde não existem no DataStage) e pipelines ativos
    assert "LOWER(ISNULL(j.job_type, 'datastage')) = 'datastage'" in sql and "ISNULL(p.active, 1) = 1" in sql
    assert [j["job_name"] for j in lista] == ["JobRaiz"]
    M.listar_jobs(**_ctx({"pipeline_name": "PIPE_VIDA", "incluir_inativos": True}))
    assert "ISNULL(p.active, 1) = 1" not in airflow_falso.get_records.call_args.args[0]


def test_listar_jobs_todos_e_pipeline_vazio(airflow_falso):
    lista = M.listar_jobs(**_ctx({}))
    assert "%s" not in airflow_falso.get_records.call_args.args[0]
    assert len(lista) == 4 and "CopyOfSsdVida" not in [j["job_name"] for j in lista]
    airflow_falso.get_records.return_value = []
    assert M.listar_jobs(**_ctx({})) == []                                  # nada a fazer, sem erro
    with pytest.raises(ValueError, match="nenhum job"):
        M.listar_jobs(**_ctx({"pipeline_name": "PIPE_SEM_JOBS"}))           # pipeline explícito vazio = erro de configuração


# ── extrair_em_lote ──────────────────────────────────────────────────────────

def test_lote_extrai_cache_e_erro_sem_abortar(airflow_falso, monkeypatch):
    sessao = FakeSessao({
        "SsdVidaDimePessoa02Ftp": (200, {"cache_hit": False, "stages": [1, 2, 3]}),
        "SeqSsdVidaDime": (200, {"cache_hit": True}),
        "JobRaiz": (404, {"detail": "Job JobRaiz não encontrado no projeto BI_VIDA do DataStage"}),
        "JobCvp": ConnectionError("boom"),
    })
    monkeypatch.setattr(M, "_sessao", lambda: sessao)
    lista = M.filtrar_jobs(LINHAS)
    resumo = M.extrair_em_lote(**_ctx({"force": True}, lista))
    assert (resumo["total"], resumo["extraidos"], resumo["cache"]) == (4, 1, 1)
    assert [(e["job_name"], e["status"]) for e in resumo["erros"]] == [("JobRaiz", 404), ("JobCvp", None)]
    assert "não encontrado" in resumo["erros"][0]["detail"] and "ConnectionError" in resumo["erros"][1]["detail"]
    # cada pedido: pipeline+job, force do conf, origem da DAG; credencial da Connection; URL da Variable sem barra final
    assert all(p["force"] is True and p["origem"] == "dag:etl_lineage_extract_isx" for p in sessao.pedidos)
    assert {p["job_name"] for p in sessao.pedidos} == {l[1] for l in LINHAS if not l[1].startswith("CopyOf")}
    assert sessao.auths == {("svc_orq", "s3nh4")} and sessao.urls == {"http://orquestra-api:8000/lineage/isx/extrair"}


def test_lote_roda_em_ate_4_threads(airflow_falso, monkeypatch):
    sessao = FakeSessao({}, demora=0.15)
    monkeypatch.setattr(M, "_sessao", lambda: sessao)
    lista = [{"pipeline_name": "P", "job_name": f"J{i}", "ds_project": "X"} for i in range(10)]
    resumo = M.extrair_em_lote(**_ctx({}, lista))
    assert resumo["extraidos"] == 10 and 2 <= sessao.pico <= 4 and resumo["duracao_s"] < 1.2


def test_lote_sem_nenhuma_resposta_falha_a_task(airflow_falso, monkeypatch):
    monkeypatch.setattr(M, "_sessao", lambda: FakeSessao({"A": (401, {"detail": "Credenciais inválidas"}),
                                                          "B": (401, {"detail": "Credenciais inválidas"})}))
    lista = [{"pipeline_name": "P", "job_name": "A", "ds_project": "X"}, {"pipeline_name": "P", "job_name": "B", "ds_project": "X"}]
    with pytest.raises(RuntimeError, match="credencial de serviço"):
        M.extrair_em_lote(**_ctx({}, lista))
    # um só erro 404 no meio de sucessos NÃO falha a task (erro individual não aborta)
    monkeypatch.setattr(M, "_sessao", lambda: FakeSessao({"A": (404, {"detail": "x"})}))
    assert M.extrair_em_lote(**_ctx({}, lista))["extraidos"] == 1
    # lista vazia: resumo zerado, sem tocar a API
    assert M.extrair_em_lote(**_ctx({}, []))["total"] == 0


def test_credencial_sem_connection_ou_sem_variable(airflow_falso, monkeypatch):
    monkeypatch.setattr(M.BaseHook, "get_connection", MagicMock(return_value=MagicMock(login="", password="")))
    with pytest.raises(ValueError, match="orquestra_api"):
        M._credencial_api()  # noqa: SLF001
    # host na Connection (AIRFLOW_CONN_ORQUESTRA_API) manda: a Variable, editável por um Op, não redireciona a credencial
    conn = MagicMock(login="svc", password="p", host="orquestra-api", port=8000, schema="http")
    monkeypatch.setattr(M.BaseHook, "get_connection", MagicMock(return_value=conn))
    monkeypatch.setattr(M.Variable, "get", MagicMock(return_value="http://host-do-op:8000"))
    assert M._credencial_api() == ("http://orquestra-api:8000", "svc", "p")  # noqa: SLF001
    conn.schema = "https"
    assert M._credencial_api()[0] == "https://orquestra-api:8000"  # noqa: SLF001
    # sem host: Variable; sem Variable: padrão da factory
    conn.host = ""
    assert M._credencial_api()[0] == "http://host-do-op:8000"  # noqa: SLF001
    monkeypatch.setattr(M.Variable, "get", MagicMock(return_value=""))
    assert M._credencial_api()[0] == "http://orquestra-api:8000"  # noqa: SLF001


def test_dag_nao_grava_no_banco_e_nao_importa_o_engine():
    fonte = (_DAGS / "etl_lineage_extract_isx.py").read_text(encoding="utf-8")
    # o import errado (`airflow.models.BaseHook`) passa nos stubs e quebra no scheduler 2.11
    assert "from airflow.hooks.base import BaseHook" in fonte and "airflow.models import BaseHook" not in fonte
    assert "trust_env = False" in fonte                                   # nunca pelo proxy: o Basic iria junto
    compose = (_ROOT / "docker-compose.yaml").read_text(encoding="utf-8")
    assert "AIRFLOW_CONN_ORQUESTRA_API: '${AIRFLOW_CONN_ORQUESTRA_API:-}'" in compose
    assert "AIRFLOW_CONN_ORQUESTRA_API=" in (_ROOT / ".env.dev.example").read_text(encoding="utf-8")
    assert "AIRFLOW_VAR_" not in compose                                  # AIRFLOW_VAR_X vazia SOBRESCREVE a Variable do banco
    for proibido in ("INSERT INTO", "UPDATE ", "DELETE FROM", "MERGE ", "isx_engine", "paramiko", "SSHHook", "?"):
        assert proibido not in fonte.split('"""', 2)[2] if proibido == "?" else proibido not in fonte, proibido
    assert "%s" in fonte and "get_records" in fonte
