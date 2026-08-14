"""POST /chamados/sincronizar — o botão "Sincronizar agora" da tela.

O botão dispara a DAG do sync fora do quarto de hora. O que estes testes
prendem são as RECUSAS, porque cada uma existe para impedir um "disparado com
sucesso" seguido de nada acontecendo:

  1. **DAG pausada no Airflow** — a API do Airflow ACEITA criar a run, devolve
     200, e a run fica parada para sempre. É o caso mais traiçoeiro: sucesso
     na tela, servidor inerte.
  2. **integração desligada** — a DAG sai no interruptor sem tocar em nada.
  3. **credencial incompleta** — o ciclo abre, falha na 1ª chamada, grava ERRO.
  4. **DAG inexistente** — deploy das DAGs não aplicado.

E o carimbo de quem disparou: sem `conf.disparado_por`, todo ciclo aparece
como "schedule" e o histórico não distingue o agendado do provocado.

Nada toca Airflow nem banco: o cliente HTTP é dublê.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()
os.environ.setdefault("MSSQL_CONN_STR", "__mock__")
from api.main import app  # noqa: E402

from deps import PERM_EXECUTAR, get_current_user  # noqa: E402

CFG_OK = {"url": "https://x.service-now.com", "usuario": "svc",
          "senha_enc": "token", "grupos": "G", "habilitado": True, "proxy": ""}


class RespostaFalsa:
    def __init__(self, status=200, corpo=None, texto=""):
        self.status_code = status
        self._corpo = corpo if corpo is not None else {}
        self.text = texto

    @property
    def is_success(self):
        return 200 <= self.status_code < 300

    def json(self):
        return self._corpo


class ClienteAirflowFalso:
    """Dublê do httpx.AsyncClient: registra o que foi postado."""

    def __init__(self, dag=None, post=None):
        self.dag = dag if dag is not None else RespostaFalsa(200, {"is_paused": False})
        self.post_resp = post if post is not None else RespostaFalsa(
            200, {"dag_run_id": "manual__2026-08-13T22:00:00"})
        self.postado: list = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, **kw):
        return self.dag

    async def post(self, url, **kw):
        self.postado.append((url, kw))
        return self.post_resp


@pytest.fixture
def executor():
    app.dependency_overrides[get_current_user] = lambda: {
        "matricula": "C123456", "perfil": "operador",
        "permissoes": ["tela_chamados", PERM_EXECUTAR]}
    yield TestClient(app)
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def cenario(monkeypatch):
    estado = {"cfg": dict(CFG_OK), "airflow": ClienteAirflowFalso()}
    monkeypatch.setattr("services.servicenow.load_config", lambda cur=None: estado["cfg"])
    monkeypatch.setattr("routers.airflow.get_airflow_client", lambda: estado["airflow"])
    return estado


# ═══════════ 1. o caminho feliz ════════════════════════════════════════════

def test_dispara_e_devolve_o_run_id(executor, cenario):
    r = executor.post("/chamados/sincronizar")
    assert r.status_code == 200
    assert r.json()["dag_run_id"] == "manual__2026-08-13T22:00:00"


def test_carimba_quem_disparou(executor, cenario):
    """Sem isto todo ciclo aparece como 'schedule' e o histórico não separa o
    agendado do provocado por gente."""
    executor.post("/chamados/sincronizar")
    _url, kw = cenario["airflow"].postado[0]
    assert kw["json"]["conf"]["disparado_por"] == "manual:C123456"


def test_a_mensagem_nao_promete_dado_na_hora(executor, cenario):
    """O ciclo leva minutos. Um 'pronto!' faria o operador recarregar, não ver
    mudança e concluir que falhou."""
    msg = executor.post("/chamados/sincronizar").json()["mensagem"].lower()
    assert "minuto" in msg


# ═══════════ 2. as recusas — cada uma evita um sucesso mentiroso ═══════════

def test_dag_pausada_e_recusada(executor, cenario):
    """O Airflow aceitaria criar a run e ela ficaria na fila para sempre."""
    cenario["airflow"] = ClienteAirflowFalso(dag=RespostaFalsa(200, {"is_paused": True}))
    r = executor.post("/chamados/sincronizar")
    assert r.status_code == 409
    assert "pausada" in r.json()["detail"].lower()
    assert not cenario["airflow"].postado, "não pode disparar com a DAG pausada"


def test_integracao_desligada_e_recusada(executor, cenario):
    cenario["cfg"]["habilitado"] = False
    r = executor.post("/chamados/sincronizar")
    assert r.status_code == 422
    assert "desabilitada" in r.json()["detail"].lower()


def test_sem_credencial_e_recusado(executor, cenario):
    cenario["cfg"]["senha_enc"] = ""
    r = executor.post("/chamados/sincronizar")
    assert r.status_code == 422
    assert "não configurado" in r.json()["detail"].lower()


def test_dag_inexistente_diz_que_o_deploy_pode_faltar(executor, cenario):
    cenario["airflow"] = ClienteAirflowFalso(dag=RespostaFalsa(404))
    r = executor.post("/chamados/sincronizar")
    assert r.status_code == 502
    assert "deploy" in r.json()["detail"].lower()


def test_airflow_recusando_o_disparo_vira_502_com_o_motivo(executor, cenario):
    cenario["airflow"] = ClienteAirflowFalso(
        post=RespostaFalsa(400, texto="dag_run_id already exists"))
    r = executor.post("/chamados/sincronizar")
    assert r.status_code == 502
    assert "already exists" in r.json()["detail"]


def test_airflow_fora_do_ar_nao_vaza_stacktrace(executor, cenario):
    class Explode(ClienteAirflowFalso):
        async def get(self, url, **kw):
            raise RuntimeError("connection refused")
    cenario["airflow"] = Explode()
    r = executor.post("/chamados/sincronizar")
    assert r.status_code == 502
    assert "Airflow" in r.json()["detail"]


# ═══════════ 3. RBAC ═══════════════════════════════════════════════════════

def test_quem_so_ve_a_tela_nao_dispara():
    """`tela_chamados` é leitura. Disparar é ação — exige acao_executar."""
    app.dependency_overrides[get_current_user] = lambda: {
        "matricula": "U9", "perfil": "consulta", "permissoes": ["tela_chamados"]}
    try:
        r = TestClient(app).post("/chamados/sincronizar")
        assert r.status_code == 403
    finally:
        app.dependency_overrides.pop(get_current_user, None)
