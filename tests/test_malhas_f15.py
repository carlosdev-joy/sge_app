"""
Testes da F15 — disparo MANUAL da malha (POST /malhas/{m}/disparo).

O escopo de servidor da F15 (a camada de execução dos nós no front é validada
por tsc/eslint/build + smoke de tela): o endpoint dispara as RAÍZES ligadas ao
Início com o MESMO ODATE via trigger REST do Airflow — o conf é o schema da
casa (montar_conf do push: data_referencia herdada pela cadeia,
dia_operacional = HOJE porque manual julga HOJE — F3, disparado_por para
auditoria) e a cascata anda pelo push. NENHUM executor novo: o Airflow é
chamado pelo MESMO client do proxy (routers.airflow.get_airflow_client),
aqui dublado.

Cobrem: rota registrada; 401/403 (acao_executar, a permissão do trigger de
pipeline); 503 sem a 075; 404 malha; 422 de data inválida / malha sem Início /
Início sem raízes; dry_run devolvendo raízes + ODATE + avisos SEM tocar o
Airflow; ODATE default pela virada da MALHA (Decisão 9) com fallback na
virada global; conf correto no write (data_referencia pedida, dia_operacional
HOJE, disparado_por com malha e matrícula, run_id com prefixo 'manual');
erro POR RAIZ (uma falha não impede as outras — ok=False com a lista); e os
avisos honestos de DAG não publicada / malha inativa.

Dublês: o FakeDb da F13 (nós + arestas + colunas de agenda da 075) ESTENDIDO
com etl_app_config, o ativo da malha e a fotografia active/dag_criada por
raiz; o client do Airflow é um dublê async que registra cada POST.
"""
from __future__ import annotations

import os
import sys
from datetime import date, datetime
from unittest.mock import MagicMock, patch

import pytest

# Replica o mock de pyodbc do conftest (garante o import de api.main mesmo se
# este arquivo for coletado antes do conftest configurar o ambiente).
if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()
os.environ.setdefault("MSSQL_CONN_STR", "__mock__")
from api.main import app as _app  # noqa: F401  (ordem de import — ver test_copias.py)

from deps import PERM_EDITAR, PERM_EXECUTAR, get_current_user
from tests.test_malhas_f10 import _aresta, _cria_no, _monta_malha
from tests.test_malhas_f13 import FakeCur as FakeCurF13, FakeDb as FakeDbF13


# ── dublê: F13 + app_config / ativo da malha / fotografia da raiz ────────────

class FakeDb(FakeDbF13):
    """FakeDb da F13 + o que o disparo lê: etl_app_config (virada global), o
    CAST(ativo) da malha, a fotografia active/dag_criada por raiz e
    etl_pipeline_execucao (contagem de corridas na data — o aviso do bônus)."""

    def __init__(self, pipelines=None, config=None, **kw):
        super().__init__(pipelines=pipelines, **kw)
        self.config = {} if config is None else config
        # {"pipeline", "data_referencia" (date), "execution_id", "status", ...}
        self.execucoes: list[dict] = []

    def cursor(self):
        super().cursor()            # mantém o snapshot da F13
        return FakeCur(self)


class FakeCur(FakeCurF13):
    def execute(self, sql, params=()):  # noqa: C901 — dispatcher de dublê
        db = self.db
        s = " ".join(str(sql).split())
        params = tuple(params)

        if s.startswith("SELECT config_value FROM dbo.etl_app_config"):
            self._rows = ([(db.config[params[0]],)]
                          if params[0] in db.config else [])
            self.rowcount = -1
            return
        if s.startswith("SELECT CAST(ativo AS INT) FROM dbo.etl_malha"):
            k = db._malha_key(params[0])
            self._rows = [(int(db.malhas[k].get("ativo", 1)),)] if k else []
            self.rowcount = -1
            return
        if s.startswith("SELECT CAST(active AS INT), CAST(dag_criada AS INT)"):
            k = db._pipeline_key(params[0])
            if k is None:
                self._rows = []
            else:
                p = db.pipelines[k]
                self._rows = [(int(p.get("active") or 0),
                               int(p.get("dag_criada") or 0))]
            self.rowcount = -1
            return
        # tabelas de execução da 067 (guard do aviso de corrida existente)
        if "OBJECT_ID('dbo.etl_pipeline_execucao'" in s:
            self._rows = [(1, 1)] if db.com_067 else [(None, None)]
            self.rowcount = -1
            return
        if s.startswith("SELECT COUNT(*) FROM dbo.etl_pipeline_execucao"):
            if not db.com_067:
                raise RuntimeError("Invalid object name 'dbo.etl_pipeline_execucao'")
            cf = (params[0] or "").casefold()
            self._rows = [(sum(1 for e in db.execucoes
                               if e["pipeline"].casefold() == cf
                               and e["data_referencia"] == params[1]),)]
            self.rowcount = -1
            return
        # ── GET /execucao (só o necessário para comparar a régua do ODATE) ──
        if s.startswith("SELECT p.pipeline_name FROM dbo.etl_malha_pipeline mp"):
            k = db._malha_key(params[0])
            out = []
            for m in db.membros:
                if k and m["malha"].casefold() == k.casefold():
                    pk = db._pipeline_key(m["pipeline"])
                    if pk is not None:
                        out.append((pk,))
            self._rows = sorted(out)
            self.rowcount = -1
            return
        if s.startswith("SELECT pipeline_name, status, inicio"):
            self._rows = [
                (e["pipeline"], e["status"], e.get("inicio"), e.get("fim"),
                 e.get("disparado_por"), e.get("motivo"), e["execution_id"])
                for e in db.execucoes if e["data_referencia"] == params[0]]
            self.rowcount = -1
            return
        if s.startswith("SELECT pipeline_name, tipo, detectado_em"):
            self._rows = []          # sem eventos nestes cenários
            self.rowcount = -1
            return

        super().execute(sql, params)


# ── dublê do client REST do Airflow (async, como o httpx do proxy) ──────────

class _RespostaAirflow:
    def __init__(self, status=200, payload=None, texto=""):
        self.status_code = status
        self._payload = payload or {}
        self.text = texto

    @property
    def is_success(self):
        return 200 <= self.status_code < 300

    def json(self):
        return self._payload


class FakeAirflowClient:
    """Registra cada POST em `chamadas` [{dag_id, body}]. `falhas` mapeia
    dag_id → status HTTP de recusa (404/500...); `explodir` derruba a chamada
    com exceção de rede."""

    def __init__(self, falhas=None, explodir=()):
        self.chamadas: list[dict] = []
        self.falhas = falhas or {}
        self.explodir = set(explodir)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, json=None, headers=None):
        dag_id = url.split("/api/v1/dags/")[1].split("/")[0]
        self.chamadas.append({"dag_id": dag_id, "body": json})
        if dag_id in self.explodir:
            raise RuntimeError("conexão recusada (teste)")
        status = self.falhas.get(dag_id)
        if status is not None:
            return _RespostaAirflow(status=status, texto="recusado (teste)")
        return _RespostaAirflow(payload={"dag_run_id": json["dag_run_id"]})


def _patch_airflow(fake):
    return patch("routers.malhas.get_airflow_client", return_value=fake)


# ── fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def auth_operador(app):
    """Editor + executor: monta a malha E dispara (o disparo exige
    acao_executar, a MESMA permissão do trigger de pipeline)."""
    app.dependency_overrides[get_current_user] = lambda: {
        "matricula": "OPER1", "perfil": "operador",
        "permissoes": [PERM_EDITAR, PERM_EXECUTAR, "tela_malha"],
    }
    yield
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def auth_sem_executar(app):
    """Editor SEM acao_executar — o disparo é 403."""
    app.dependency_overrides[get_current_user] = lambda: {
        "matricula": "DEV1", "perfil": "desenvolvedor",
        "permissoes": [PERM_EDITAR, "tela_malha"],
    }
    yield
    app.dependency_overrides.pop(get_current_user, None)


def _patch_db(db):
    return patch("routers.malhas.get_db_conn", return_value=db)


def _pipes():
    base = {"active": 1, "criticidade": "Media", "depends_on": None,
            "scheduled_time": "07:30:00", "schedule_type": "daily",
            "schedule_hour": 7, "schedule_minute": 30, "schedule_dow": 1,
            "schedule_dom": 1, "horarios_especificos": None,
            "dias_semana": None, "dias_horarios_mes": None,
            "somente_dias_uteis": 0, "calendario_nome": None,
            "hora_virada": None, "agenda_no": None}
    return {
        "RAIZ_A": {**base, "dag_criada": 1},
        "RAIZ_B": {**base, "dag_criada": 1},
        "RAIZ_C": {**base, "dag_criada": 0},          # DAG nunca publicada
        "PIPE_MEIO": {**base, "dag_criada": 1},       # membro fora do Início
    }


def _malha_com_inicio(client, nome="M1", raizes=("RAIZ_A", "RAIZ_B")):
    """Malha com Início ligado às raízes + um membro solto (PIPE_MEIO nunca
    entra no disparo — a prova de 'raízes certas')."""
    _monta_malha(client, nome, [*raizes, "PIPE_MEIO"])
    inicio = _cria_no(client, nome, "inicio")
    for p in raizes:
        r = _aresta(client, nome, {"no": inicio}, {"pipeline": p})
        assert r.status_code == 200, r.text
    return inicio


def _disparar(client, malha, body=None):
    return client.post(f"/malhas/{malha}/disparo", json=body or {})


# ── registro da rota e permissões ────────────────────────────────────────────

def test_rota_disparo_registrada(client):
    r = client.get("/openapi.json")
    assert r.status_code == 200
    assert "/malhas/{malha_name}/disparo" in r.json().get("paths", {})


def test_sem_auth_401(client):
    assert _disparar(client, "M1").status_code == 401


def test_sem_acao_executar_403(client, auth_sem_executar):
    """Disparo é EXECUÇÃO (não edição): a permissão é a mesma do trigger de
    pipeline — acao_executar; editor sem ela recebe 403."""
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        assert _disparar(client, "M1").status_code == 403


# ── degradação e validações ──────────────────────────────────────────────────

def test_sem_075_503(client, auth_operador):
    db = FakeDb(pipelines=_pipes(), com_075=False)
    with _patch_db(db):
        r = _disparar(client, "M1")
    assert r.status_code == 503
    assert "075" in r.json()["detail"]


def test_malha_inexistente_404(client, auth_operador):
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        r = _disparar(client, "NAO_EXISTE")
    assert r.status_code == 404


def test_data_invalida_422(client, auth_operador):
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        r = _disparar(client, "M1", {"data_referencia": "05/08/2026"})
    assert r.status_code == 422
    assert "YYYY-MM-DD" in r.json()["detail"]


def test_malha_sem_inicio_422(client, auth_operador):
    db = FakeDb(pipelines=_pipes())
    fake = FakeAirflowClient()
    with _patch_db(db), _patch_airflow(fake):
        _monta_malha(client, "M1", ["RAIZ_A"])
        r = _disparar(client, "M1")
    assert r.status_code == 422
    assert "Início" in r.json()["detail"]
    assert fake.chamadas == []


def test_inicio_sem_raizes_422(client, auth_operador):
    db = FakeDb(pipelines=_pipes())
    fake = FakeAirflowClient()
    with _patch_db(db), _patch_airflow(fake):
        _monta_malha(client, "M1", ["RAIZ_A"])
        _cria_no(client, "M1", "inicio")
        r = _disparar(client, "M1")
    assert r.status_code == 422
    assert "raiz" in r.json()["detail"]
    assert fake.chamadas == []


# ── dry_run: o que será disparado, sem tocar o Airflow ──────────────────────

def test_dry_run_raizes_certas_sem_airflow(client, auth_operador):
    """dry_run lista SÓ as raízes ligadas ao Início (membro solto fora),
    com a data pedida — e o Airflow não recebe UMA chamada."""
    db = FakeDb(pipelines=_pipes())
    fake = FakeAirflowClient()
    with _patch_db(db), _patch_airflow(fake):
        _malha_com_inicio(client)
        r = _disparar(client, "M1", {"dry_run": True,
                                     "data_referencia": "2026-08-05"})
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["data_referencia"] == "2026-08-05"
    assert [x["pipeline"] for x in corpo["raizes"]] == ["RAIZ_A", "RAIZ_B"]
    assert fake.chamadas == []


def test_dry_run_avisa_raiz_com_dependencia(client, auth_operador):
    """Revisão da F15 (§2.2): raiz que ganhou dependência por outra porta é
    AVISADA antes do gesto — o trigger manual não consulta liberado(), então
    a corrida parte POR CIMA do predecessor. Aviso por raiz, nunca bloqueio;
    `tipo` estável para o front filtrar sem casar texto."""
    db = FakeDb(pipelines=_pipes())
    fake = FakeAirflowClient()
    with _patch_db(db), _patch_airflow(fake):
        _malha_com_inicio(client)
        # dependência criada pela porta de sempre (F8), depois de a raiz já
        # estar assinada — o caso da contradição
        assert client.post("/dependencias", json={
            "pipeline_name": "RAIZ_A", "depende_de": "PIPE_MEIO"},
        ).status_code == 200
        r = _disparar(client, "M1", {"dry_run": True,
                                     "data_referencia": "2026-08-05"})
    assert r.status_code == 200, r.text
    corpo = r.json()
    info = {x["pipeline"]: x for x in corpo["raizes"]}
    assert info["RAIZ_A"]["tem_dependencia"] is True
    assert info["RAIZ_B"]["tem_dependencia"] is False
    avisos = [a for a in corpo["avisos"] if a.get("tipo") == "contradicao"]
    assert len(avisos) == 1
    assert "RAIZ_A" in avisos[0]["mensagem"]
    assert "POR CIMA" in avisos[0]["mensagem"]
    assert fake.chamadas == []


def test_dry_run_avisa_corrida_ja_existente_na_data(client, auth_operador):
    """Bônus da revisão: a malha rodou de manhã e o operador dispara à tarde
    — os DEPENDENTES são protegidos pelo claim, a RAIZ não. Aviso por raiz
    (com a contagem), sem bloquear: o gesto continua sendo do operador."""
    db = FakeDb(pipelines=_pipes())
    fake = FakeAirflowClient()
    with _patch_db(db), _patch_airflow(fake):
        _malha_com_inicio(client)
        db.execucoes.append({
            "pipeline": "RAIZ_A", "data_referencia": date(2026, 8, 5),
            "execution_id": "manual__x", "status": "SUCESSO", "inicio": None,
            "fim": None, "disparado_por": "agenda", "motivo": None})
        r = _disparar(client, "M1", {"dry_run": True,
                                     "data_referencia": "2026-08-05"})
    assert r.status_code == 200, r.text
    corpo = r.json()
    info = {x["pipeline"]: x for x in corpo["raizes"]}
    assert info["RAIZ_A"]["corridas_na_data"] == 1
    assert info["RAIZ_B"]["corridas_na_data"] == 0
    avisos = [a for a in corpo["avisos"] if a.get("tipo") == "corrida_existente"]
    assert len(avisos) == 1
    assert "RAIZ_A" in avisos[0]["mensagem"] and "2026-08-05" in avisos[0]["mensagem"]
    assert fake.chamadas == []


def test_get_detalhe_marca_aviso_de_contradicao(client, auth_operador):
    """Revisão da F15: o aviso de contradição do GET detalhe carrega
    `tipo: 'contradicao'` — chave ESTÁVEL para a visão de Execução mostrá-lo
    (é lá que vive o disparo manual) sem o front casar TEXTO. A mensagem
    continua tendo uma fonte só: o servidor."""
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        _malha_com_inicio(client)
        assert client.post("/malhas/M1/agendamento", json={"agendamento": {
            "schedule_type": "daily", "schedule_hour": 6}},
        ).status_code == 200
        assert client.post("/dependencias", json={
            "pipeline_name": "RAIZ_A", "depende_de": "PIPE_MEIO"},
        ).status_code == 200
        r = client.get("/malhas/M1")
    assert r.status_code == 200, r.text
    corpo = r.json()
    contradicoes = [a for a in corpo["avisos"] if a.get("tipo") == "contradicao"]
    assert len(contradicoes) == 1
    assert "RAIZ_A" in contradicoes[0]["mensagem"]
    # e o membro segue marcado (o badge no card do pipeline)
    membro = next(m for m in corpo["membros"] if m["pipeline_name"] == "RAIZ_A")
    assert membro["agenda_contradicao"] is True


def test_dry_run_avisa_dag_nao_publicada_e_malha_inativa(client, auth_operador):
    db = FakeDb(pipelines=_pipes())
    fake = FakeAirflowClient()
    with _patch_db(db), _patch_airflow(fake):
        _malha_com_inicio(client, raizes=("RAIZ_A", "RAIZ_C"))
        client.patch("/malhas/M1", json={"ativo": 0})
        r = _disparar(client, "M1", {"dry_run": True,
                                     "data_referencia": "2026-08-05"})
    assert r.status_code == 200, r.text
    msgs = " | ".join(a["mensagem"] for a in r.json()["avisos"])
    assert "RAIZ_C" in msgs and "publicada" in msgs
    assert "malha inativa" in msgs
    assert fake.chamadas == []


def test_odate_default_pela_virada_global(client, auth_operador):
    """Sem data no body, o ODATE sai da virada GLOBAL: às 21:00 com virada
    20:00, o rótulo é o dia SEGUINTE."""
    db = FakeDb(pipelines=_pipes(),
                config={"dependencia_hora_virada": "20:00"})
    fake = FakeAirflowClient()
    with _patch_db(db), _patch_airflow(fake):
        _malha_com_inicio(client)
        with patch("routers.malhas._agora",
                   return_value=datetime(2026, 8, 5, 21, 0)):
            r = _disparar(client, "M1", {"dry_run": True})
    assert r.status_code == 200, r.text
    assert r.json()["data_referencia"] == "2026-08-06"


def test_odate_default_e_o_MESMO_do_painel(client, auth_operador):
    """Revisão da F15: UMA régua para o ODATE default. A virada da MALHA
    (20:00) NÃO pode mandar aqui enquanto o GET /execucao usa a global
    (00:00) — senão, às 21:00, o painel mostra D e o disparo carimba D+1: a
    tela contando uma história e o motor outra."""
    db = FakeDb(pipelines=_pipes(),
                config={"dependencia_hora_virada": "00:00"})
    fake = FakeAirflowClient()
    with _patch_db(db), _patch_airflow(fake):
        _malha_com_inicio(client)
        r = client.post("/malhas/M1/agendamento", json={"agendamento": {
            "schedule_type": "daily", "schedule_hour": 6,
            "hora_virada": "20:00"}})     # virada da MALHA divergente
        assert r.status_code == 200, r.text
        with patch("routers.malhas._agora",
                   return_value=datetime(2026, 8, 5, 21, 0)):
            painel = client.get("/malhas/M1/execucao")
            disparo = _disparar(client, "M1", {"dry_run": True})
    assert painel.status_code == 200, painel.text
    assert disparo.status_code == 200, disparo.text
    assert disparo.json()["data_referencia"] == painel.json()["data_referencia"]
    assert disparo.json()["data_referencia"] == "2026-08-05"   # a global manda


# ── write: disparo real (Airflow dublado) ───────────────────────────────────

def test_disparo_conf_da_casa(client, auth_operador):
    """As duas raízes partem com o MESMO conf da casa: data_referencia
    pedida (herdada pela cadeia — o filho não recalcula), dia_operacional =
    HOJE (F3: manual julga HOJE), disparado_por com malha e matrícula; e o
    run_id tem prefixo 'manual' (origem F3 'manual': não julga hora, julga
    dia)."""
    db = FakeDb(pipelines=_pipes())
    fake = FakeAirflowClient()
    with _patch_db(db), _patch_airflow(fake):
        _malha_com_inicio(client)
        with patch("routers.malhas._agora",
                   return_value=datetime(2026, 8, 6, 9, 0)):
            r = _disparar(client, "M1", {"data_referencia": "2026-08-05"})
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["ok"] is True
    assert corpo["data_referencia"] == "2026-08-05"
    assert [d["pipeline"] for d in corpo["disparadas"]] == ["RAIZ_A", "RAIZ_B"]
    assert corpo["falhas"] == []
    assert [c["dag_id"] for c in fake.chamadas] == ["RAIZ_A", "RAIZ_B"]
    for c in fake.chamadas:
        conf = c["body"]["conf"]
        assert conf["data_referencia"] == "2026-08-05"      # ODATE herdado
        assert conf["dia_operacional"] == "2026-08-06"      # HOJE (manual)
        assert conf["disparado_por"] == "malha:M1 (OPER1)"  # auditoria
        assert c["body"]["dag_run_id"].startswith("manual__2026-08-05__")


def test_disparo_erro_por_raiz_nao_impede_as_outras(client, auth_operador):
    """RAIZ_A recusada (404 do Airflow) e RAIZ_B disparada: ok=False, a falha
    nomeia a raiz com instrução, e a outra corrida ACONTECEU — erro por raiz,
    nunca tudo-ou-nada mudo."""
    db = FakeDb(pipelines=_pipes())
    fake = FakeAirflowClient(falhas={"RAIZ_A": 404})
    with _patch_db(db), _patch_airflow(fake):
        _malha_com_inicio(client)
        r = _disparar(client, "M1", {"data_referencia": "2026-08-05"})
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["ok"] is False
    assert [d["pipeline"] for d in corpo["disparadas"]] == ["RAIZ_B"]
    assert len(corpo["falhas"]) == 1
    assert corpo["falhas"][0]["pipeline"] == "RAIZ_A"
    assert "publique o pipeline" in corpo["falhas"][0]["erro"]
    assert len(fake.chamadas) == 2      # as DUAS foram tentadas


def test_disparo_excecao_de_rede_por_raiz(client, auth_operador):
    """Exceção de rede numa raiz vira falha nomeada — a outra segue."""
    db = FakeDb(pipelines=_pipes())
    fake = FakeAirflowClient(explodir={"RAIZ_B"})
    with _patch_db(db), _patch_airflow(fake):
        _malha_com_inicio(client)
        r = _disparar(client, "M1", {"data_referencia": "2026-08-05"})
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["ok"] is False
    assert [d["pipeline"] for d in corpo["disparadas"]] == ["RAIZ_A"]
    assert corpo["falhas"][0]["pipeline"] == "RAIZ_B"
    assert "Airflow" in corpo["falhas"][0]["erro"]
