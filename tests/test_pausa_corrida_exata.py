"""
Correção 2.21.1 — **a pausa (e os outros gestos de `_resolve_alvo_rerun`)
resolvem o ts_nodash pela corrida EXATA do Airflow**.

O defeito, medido no smoke nativo da F5 no DEV (2.21.0, PR #502): o Executar
guiado gera `workspace__<uuid>`; `POST /execucoes/pausas` com esse
`dag_run_id` respondia 409 `corrida_sem_execution_id`, embora o Airflow tivesse
a corrida com logical date válida. `_resolve_alvo_rerun` resolvia só pelo
banco (`resolve_por_run_id`) e nunca completava com o Airflow; o GET da
execução completava, a pausa não.

O que estes testes prendem:
  • run_id não traduzível → UMA leitura `GET /dags/{dag}/dagRuns/{run_id}`
    (codificada), e a pausa nasce com o ts_nodash da logical date;
  • falha, timeout, 404, corpo ilegível, corrida/DAG discordantes e logical
    date inválida → a recusa de sempre (409), sem INSERT e sem fallback para
    a lista de corridas;
  • run_id traduzível, execution_id, ODATE ambíguo, sem corrida, modo
    degradado e falta de permissão → nenhuma leitura nova;
  • prévia e reexecução: o dag_run_id pedido continua o mesmo, e a leitura
    que falha não cria recusa nova.

Dublês locais; nada toca rede nem banco.
"""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import date, datetime
from unittest.mock import MagicMock, patch

import pytest

if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()
os.environ.setdefault("MSSQL_CONN_STR", "__mock__")
from api.main import app as _app  # noqa: F401,E402  (ordem de import — ver test_copias.py)

import httpx  # noqa: E402

from deps import PERM_EXECUTAR, get_current_user  # noqa: E402
from services import espera as esp  # noqa: E402
from services import execucao_identidade as ident  # noqa: E402
from tests.test_rerun_etapa_f4 import (  # noqa: E402
    _ClientFake, _DbRerun, _RespFake, _corrida,
)

# Os valores do smoke nativo (sem dado de cliente: pipeline e corrida próprios).
PIPE = "__workspace_ux_f5_c1038ef910"
WS_RUN = "workspace__fe69c368-2fc5-44c4-8f87-a2d8c9980e31"
LOGICAL = "2026-10-11T18:41:07.123456+00:00"
TS = "20261011T184107"
URL_EXATA = f"/api/v1/dags/{PIPE}/dagRuns/{WS_RUN}"


@pytest.fixture(scope="module")
def E():
    import routers.execucoes as _e
    return _e


def _dag_run(run_id=WS_RUN, dag_id=PIPE, logical=LOGICAL, **extra):
    corpo = {"dag_run_id": run_id, "dag_id": dag_id, "logical_date": logical,
             "execution_date": logical, "state": "running",
             # `conf` pode trazer parâmetros: nunca vai para o log.
             "conf": {"segredo": "nao-logar"}}
    corpo.update(extra)
    return corpo


# ═══════════════════════════════════════════════════════════════════════════
# 1. FUNÇÕES PURAS — a logical date e as guardas da corrida exata
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("logical,esperado", [
    ("2026-10-11T18:41:07.123456+00:00", TS),
    ("2026-10-11T18:41:07+00:00", TS),
    ("2026-10-11T18:41:07Z", TS),
    ("2026-10-11T18:41:07.1-00:00", TS),
    ("  2026-10-11T18:41:07+00:00  ", TS),
])
def test_logical_date_utc_vira_ts_nodash(logical, esperado):
    assert ident.ts_nodash_de_logical_date(logical) == esperado


@pytest.mark.parametrize("logical", [
    None, "", "lixo", 20261011, ["2026-10-11T18:41:07+00:00"],
    "2026-10-11T18:41:07",              # sem fuso: o corte daria hora ambígua
    "2026-10-11T15:41:07-03:00",        # outro fuso: o corte daria hora LOCAL
    "2026-10-11T18:41:07+01:00",
    "2026-10-11 18:41:07+00:00",        # separador espaço
    "2026-13-11T18:41:07+00:00",        # mês 13
    "2026-02-30T00:00:00+00:00",        # dia inexistente
    "2026-10-11T24:00:00+00:00",
    "2026-10-11T18:41+00:00",           # sem segundos
    "2026-10-11T18:41:07.+00:00",
    "2026-10-11T18:41:07+00:00x",
])
def test_logical_date_invalida_nao_vira_ts_nodash(logical):
    assert ident.ts_nodash_de_logical_date(logical) is None


def _ident_ws(run_id=WS_RUN, **extra):
    base = ident.identidade_vazia(ident.RUN_ID_NAO_TRADUZIVEL, run_id=run_id,
                                  dag_run_id=run_id)
    base.update(extra)
    return base


def test_corrida_exata_fecha_a_identidade():
    r = ident.completa_com_dag_run_exato(_ident_ws(), PIPE, _dag_run())
    assert r["resolvido"] is True and r["ts_nodash"] == TS
    assert r["motivo"] is None and r["logical_date"] == LOGICAL
    assert r["run_id"] == r["dag_run_id"] == WS_RUN
    assert "airflow" in r["origem"].split("+")


_LOGICAL_COM_ESPACOS = "  2026-10-11T18:41:07+00:00  "


@pytest.mark.parametrize("campo", ["logical_date", "execution_date"])
def test_corrida_exata_com_espacos_fecha_com_o_ts_validado(campo):
    """⛔ QA da 2.21.1: a guarda validava `logical.strip()`, mas a conclusão
    delegava o corpo cru e o `ts_nodash` legado cortava 19 caracteres com os
    espaços — `'  20261011T1841'`, que o portão nunca reconhece."""
    run = _dag_run(logical=None, execution_date=None)
    run[campo] = _LOGICAL_COM_ESPACOS
    r = ident.completa_com_dag_run_exato(_ident_ws(), PIPE, run)
    assert r["resolvido"] is True and r["ts_nodash"] == TS
    assert r["logical_date"] == _LOGICAL_COM_ESPACOS.strip()
    assert run[campo] == _LOGICAL_COM_ESPACOS          # o corpo lido não muda
    # o conversor legado continua cru — quem normaliza é o caminho exato
    assert ident.ts_nodash(_LOGICAL_COM_ESPACOS) == "  20261011T1841"


def test_corrida_exata_recusa_se_a_conclusao_diverge_do_ts_validado(monkeypatch):
    """Rede de segurança: se a regra comum fechar com outro ts_nodash, a
    identidade volta intacta em vez de gravar um alvo que o portão não vê."""
    real = ident.completa_com_airflow
    monkeypatch.setattr(ident, "completa_com_airflow",
                        lambda i, runs: {**real(i, runs), "ts_nodash": "  20261011T1841"})
    r = ident.completa_com_dag_run_exato(_ident_ws(), PIPE, _dag_run())
    assert r["ts_nodash"] is None and r["resolvido"] is False
    assert r["motivo"] == ident.RUN_ID_NAO_TRADUZIVEL


@pytest.mark.parametrize("run", [
    _dag_run(run_id="workspace__00000000-0000-0000-0000-000000000000"),
    _dag_run(run_id=""),
    {k: v for k, v in _dag_run().items() if k != "dag_run_id"},
], ids=["outra_corrida", "run_id_vazio", "sem_run_id"])
def test_corrida_exata_recusa_corrida_discordante(run):
    r = ident.completa_com_dag_run_exato(_ident_ws(), PIPE, run)
    assert r["ts_nodash"] is None and r["resolvido"] is False
    assert r["motivo"] == ident.RUN_ID_NAO_TRADUZIVEL


@pytest.mark.parametrize("dag_id", ["OUTRO_PIPE", PIPE.upper(), "", None],
                         ids=["outra_dag", "outra_caixa", "vazio", "ausente"])
def test_corrida_exata_recusa_outra_dag(dag_id):
    """O mesmo run_id em outra DAG é outra corrida — e o Airflow distingue
    caixa no dag_id."""
    r = ident.completa_com_dag_run_exato(_ident_ws(), PIPE, _dag_run(dag_id=dag_id))
    assert r["ts_nodash"] is None and r["motivo"] == ident.RUN_ID_NAO_TRADUZIVEL


@pytest.mark.parametrize("logical", ["2026-10-11T18:41:07", "lixo", None,
                                     "2026-10-11T15:41:07-03:00"])
def test_corrida_exata_recusa_logical_date_invalida(logical):
    run = _dag_run(logical=logical)
    run["execution_date"] = logical
    r = ident.completa_com_dag_run_exato(_ident_ws(), PIPE, run)
    assert r["ts_nodash"] is None and r["motivo"] == ident.RUN_ID_NAO_TRADUZIVEL


@pytest.mark.parametrize("run", [None, [], "texto", [_dag_run()]])
def test_corrida_exata_recusa_corpo_que_nao_e_objeto(run):
    assert ident.completa_com_dag_run_exato(_ident_ws(), PIPE, run)["ts_nodash"] is None


def test_corrida_exata_nao_muta_a_entrada():
    entrada = _ident_ws(candidatos=[{"run_id": WS_RUN}])
    copia = {**entrada, "candidatos": list(entrada["candidatos"])}
    saida = ident.completa_com_dag_run_exato(entrada, PIPE, _dag_run())
    assert entrada == copia and saida is not entrada
    recusada = ident.completa_com_dag_run_exato(entrada, PIPE, None)
    assert recusada == copia and recusada is not entrada
    assert recusada["candidatos"] is not entrada["candidatos"]


# ═══════════════════════════════════════════════════════════════════════════
# 2. DUBLÊS — banco do POST de pausa e Airflow que grava cada leitura
# ═══════════════════════════════════════════════════════════════════════════

class _DbPausa:
    """Cadastro, identidade (067 ou modo degradado), desenho e escritas da
    pausa. `corridas_run` = linhas da 067 por run_id; `corridas_dia` = as do
    ODATE consultado."""

    def __init__(self, *, pipeline=PIPE, tem_067=True, corridas_run=None,
                 corridas_dia=(), job_execution=()):
        self.pipeline = pipeline
        self.tem_067 = tem_067
        self.corridas_run = dict(corridas_run or {})
        self.corridas_dia = list(corridas_dia)
        self.job_execution = list(job_execution)
        self.escritas: list = []
        self.sqls: list = []

    def cursor(self):
        return _CurPausa(self)

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


class _CurPausa:
    def __init__(self, db):
        self.db = db
        self._rows: list = []
        self.rowcount = 0

    def execute(self, sql, params=()):  # noqa: C901 — dispatcher de dublê
        db = self.db
        s = " ".join(str(sql).split())
        db.sqls.append((s, params))
        self._rows, self.rowcount = [], 0
        if s.startswith("SELECT pipeline_name FROM dbo.etl_pipeline WHERE"):
            self._rows = [(db.pipeline,)]
        elif s.startswith("SELECT config_value FROM dbo.etl_app_config"):
            self._rows = [("00:00",)]
        elif s.startswith("SELECT OBJECT_ID('dbo.etl_pipeline_execucao'"):
            self._rows = [(1 if db.tem_067 else None,)]
        elif s.startswith("SELECT COL_LENGTH('dbo.etl_pipeline_execucao', 'substituida_em')"):
            self._rows = [(8,)]
        elif s.startswith("SELECT data_referencia, status, inicio, fim, "
                          "disparado_por, motivo FROM dbo.etl_pipeline_execucao"):
            linha = db.corridas_run.get(params[1])
            self._rows = [linha] if linha else []
        elif s.startswith("SELECT execution_id, status, inicio, fim, disparado_por, "
                          "motivo, substituida_em FROM dbo.etl_pipeline_execucao"):
            self._rows = list(db.corridas_dia)
        elif s.startswith("SELECT execution_id, status, inicio, fim, disparado_por, "
                          "motivo, data_referencia, substituida_em FROM dbo.etl_pipeline_execucao"):
            self._rows = []                       # sentido inverso: nada casa
        elif s.startswith("SELECT execution_id, MIN(start_time) FROM dbo.etl_job_execution"):
            self._rows = list(db.job_execution)
        elif s.startswith("SELECT OBJECT_ID('dbo.etl_etapa_pausa'"):
            self._rows = [(1,)]
        elif s.startswith("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS"):
            self._rows = [("job_name",), ("job_type",), ("execution_order",),
                          ("depends_on_jobs",)]
        elif s.startswith("SELECT job_name, ISNULL(job_type"):
            self._rows = [("Carga", "sql", 1, None), ("Finalizar", "shell", 2, "Carga")]
        elif s.startswith("SELECT job_name FROM dbo.etl_job_execution"):
            self._rows = []                       # nenhuma etapa iniciou
        elif s.startswith("SELECT sla_minutos"):
            self._rows = [(None,)]
        elif s.startswith("INSERT INTO dbo.etl_etapa_pausa"):
            db.escritas.append((s, params))
            self.rowcount = 1
        elif s.startswith("SELECT TOP (1) id FROM dbo.etl_etapa_pausa"):
            self._rows = [(77,)]
        elif s.startswith("INSERT INTO dbo.etl_pipeline_audit"):
            db.escritas.append((s, params))
            self.rowcount = 1
        elif s.startswith("SELECT id, job_name, task_id, estado"):
            self._rows = []
        else:
            raise AssertionError(f"SQL não previsto no dublê: {s[:140]}")

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def close(self):
        pass


_ILEGIVEL = object()


class _Resp:
    def __init__(self, corpo, status=200):
        self._corpo, self.status_code = corpo, status
        self.text = "corpo-nao-deve-ir-para-o-log"

    @property
    def is_success(self):
        return 200 <= self.status_code < 300

    def json(self):
        if self._corpo is _ILEGIVEL:
            raise ValueError("JSON inválido")
        return self._corpo


class _Airflow:
    """Airflow de mentira para a pausa: só leitura, e cada GET fica gravado."""

    def __init__(self, corpo=None, *, status=200, erro=None, atraso=None):
        self.corpo = _dag_run() if corpo is None else corpo
        self.status, self.erro, self.atraso = status, erro, atraso
        self.gets: list = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, params=None):
        self.gets.append((url, params))
        if self.atraso:
            await asyncio.sleep(self.atraso)
        if self.erro:
            raise self.erro
        return _Resp(self.corpo, self.status)

    async def post(self, url, json=None):  # pragma: no cover — a pausa não posta
        raise AssertionError("a pausa não escreve no Airflow")


@pytest.fixture
def cliente(client, app):
    app.dependency_overrides[get_current_user] = lambda: {
        "matricula": "DEV1", "perfil": "desenvolvedor",
        "permissoes": [PERM_EXECUTAR, "tela_malha"],
    }
    yield client
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def cliente_sem_perm(client, app):
    app.dependency_overrides[get_current_user] = lambda: {
        "matricula": "CONS", "perfil": "consulta", "permissoes": ["tela_malha"],
    }
    yield client
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture(autouse=True)
def _portao_ok(monkeypatch):
    monkeypatch.setattr(esp, "estado_portao", lambda cur, p: esp.PORTAO_OK)


def _linha_067(odate=date(2026, 10, 11)):
    return (odate, "EXECUTANDO", datetime(2026, 10, 11, 15, 41, 7), None,
            "workspace", None)


def _post_pausa(cliente, db, af, **body):
    corpo = {"pipeline_name": PIPE, "job_name": "Finalizar"}
    corpo.update(body)
    with patch("routers.execucoes.get_db_conn", return_value=db), \
         patch("routers.execucoes.get_airflow_client", return_value=af):
        return cliente.post("/execucoes/pausas", json=corpo)


def _insert_pausa(db):
    """(pipeline, execution_id, job, task, run_id, data_ref) do INSERT."""
    ins = [p for s, p in db.escritas if s.startswith("INSERT INTO dbo.etl_etapa_pausa")]
    assert len(ins) == 1
    return ins[0][:6]


# ═══════════════════════════════════════════════════════════════════════════
# 3. O DEFEITO — workspace__<uuid> pausa com o ts_nodash do Airflow
# ═══════════════════════════════════════════════════════════════════════════

def test_pausa_com_run_id_workspace_usa_a_corrida_exata(cliente):
    """⛔ O smoke F5: antes, 409 `corrida_sem_execution_id`."""
    db = _DbPausa(corridas_run={WS_RUN: _linha_067()})
    af = _Airflow()
    r = _post_pausa(cliente, db, af, dag_run_id=WS_RUN,
                    data_referencia="2026-10-11")
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["ok"] is True and corpo["execution_id"] == TS
    assert corpo["pipeline_name"] == PIPE and corpo["job_name"] == "Finalizar"
    assert _insert_pausa(db) == (PIPE, TS, "Finalizar", "Finalizar", WS_RUN,
                                 date(2026, 10, 11))
    # UMA leitura, da corrida exata, sem parâmetros de listagem
    assert af.gets == [(URL_EXATA, None)]


def test_pausa_com_logical_date_com_espacos_grava_o_ts_do_portao(cliente):
    """A pausa grava o execution_id que o portão da etapa compara — nunca o
    corte cru da logical date com espaços."""
    db = _DbPausa(corridas_run={WS_RUN: _linha_067()})
    af = _Airflow(_dag_run(logical=_LOGICAL_COM_ESPACOS))
    r = _post_pausa(cliente, db, af, dag_run_id=WS_RUN,
                    data_referencia="2026-10-11")
    assert r.status_code == 200, r.text
    assert r.json()["execution_id"] == TS
    assert _insert_pausa(db) == (PIPE, TS, "Finalizar", "Finalizar", WS_RUN,
                                 date(2026, 10, 11))
    assert af.gets == [(URL_EXATA, None)]


def test_pausa_sem_linha_na_067_resgata_o_odate_pelo_ts(cliente):
    """Pausar segundos depois do disparo: a 067 ainda não tem a linha e o
    corpo não mandou data — o ODATE sai do ts_nodash, como já fazia."""
    db = _DbPausa(corridas_run={})
    af = _Airflow()
    r = _post_pausa(cliente, db, af, dag_run_id=WS_RUN)
    assert r.status_code == 200, r.text
    assert _insert_pausa(db)[1:] == (TS, "Finalizar", "Finalizar", WS_RUN,
                                     date(2026, 10, 11))
    assert len(af.gets) == 1


def test_odate_com_corrida_unica_nao_traduzivel_le_essa_corrida(cliente):
    """Porta do ODATE (modo estrito): a única corrida do dia tem run_id do
    Orquestra, cujo relógio embutido é LOCAL (09:49). O ts_nodash vem da
    logical date do Airflow (12:49), nunca da string — a armadilha da F2."""
    run = "manual__2026-08-03__PIPE__20260803T094924510486"
    db = _DbPausa(corridas_dia=[(run, "EXECUTANDO", datetime(2026, 8, 3, 9, 49),
                                 None, "manual", None, None)])
    af = _Airflow(_dag_run(run_id=run, logical="2026-08-03T12:49:24.715592+00:00"))
    r = _post_pausa(cliente, db, af, data_referencia="2026-08-03")
    assert r.status_code == 200, r.text
    assert _insert_pausa(db)[1:] == ("20260803T124924", "Finalizar", "Finalizar",
                                     run, date(2026, 8, 3))
    assert af.gets == [(f"/api/v1/dags/{PIPE}/dagRuns/{run}", None)]


# ═══════════════════════════════════════════════════════════════════════════
# 4. QUANDO NÃO DÁ — a recusa de sempre, sem INSERT e sem outra corrida
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("af,motivo", [
    (_Airflow(erro=httpx.ConnectError("fora do ar")), ident.RUN_ID_NAO_TRADUZIVEL),
    (_Airflow(status=500), ident.RUN_ID_NAO_TRADUZIVEL),
    (_Airflow(status=403), ident.RUN_ID_NAO_TRADUZIVEL),
    (_Airflow(status=404), ident.SEM_DAG_RUN),
    (_Airflow(_ILEGIVEL), ident.RUN_ID_NAO_TRADUZIVEL),
    (_Airflow(_dag_run(run_id="workspace__11111111-1111-1111-1111-111111111111")),
     ident.RUN_ID_NAO_TRADUZIVEL),
    (_Airflow(_dag_run(dag_id="OUTRO_PIPE")), ident.RUN_ID_NAO_TRADUZIVEL),
    (_Airflow(_dag_run(logical="2026-10-11T18:41:07")), ident.RUN_ID_NAO_TRADUZIVEL),
    (_Airflow(_dag_run(logical="lixo")), ident.RUN_ID_NAO_TRADUZIVEL),
    (_Airflow({"dag_runs": [_dag_run()]}), ident.RUN_ID_NAO_TRADUZIVEL),
], ids=["rede", "http500", "http403", "http404", "corpo_ilegivel",
        "run_id_discordante", "outra_dag", "logical_sem_fuso",
        "logical_lixo", "lista_no_lugar_do_objeto"])
def test_pausa_recusa_quando_a_corrida_exata_nao_confirma(cliente, af, motivo):
    db = _DbPausa(corridas_run={WS_RUN: _linha_067()})
    r = _post_pausa(cliente, db, af, dag_run_id=WS_RUN,
                    data_referencia="2026-10-11")
    assert r.status_code == 409
    det = r.json()["detail"]
    assert det["erro"] == "corrida_sem_execution_id"
    assert det["motivo"] == motivo
    assert db.escritas == []
    # nenhuma segunda tentativa, nenhuma leitura da LISTA de corridas
    assert af.gets == [(URL_EXATA, None)]


def test_pausa_recusa_por_timeout_sem_esperar_o_client(cliente, E, monkeypatch):
    monkeypatch.setattr(E, "_TIMEOUT_CORRIDA_EXATA_S", 0.05)
    db = _DbPausa(corridas_run={WS_RUN: _linha_067()})
    af = _Airflow(atraso=5)
    r = _post_pausa(cliente, db, af, dag_run_id=WS_RUN)
    assert r.status_code == 409
    assert r.json()["detail"]["motivo"] == ident.RUN_ID_NAO_TRADUZIVEL
    assert db.escritas == [] and len(af.gets) == 1


def test_teto_da_leitura_exata_e_menor_que_o_do_client(E):
    assert 0 < E._TIMEOUT_CORRIDA_EXATA_S < 15


def test_falha_nao_vaza_corpo_nem_conf_no_log(cliente, caplog):
    db = _DbPausa(corridas_run={WS_RUN: _linha_067()})
    with caplog.at_level("WARNING"):
        _post_pausa(cliente, db, _Airflow(status=500), dag_run_id=WS_RUN)
        _post_pausa(cliente, db, _Airflow(_dag_run(dag_id="OUTRO")), dag_run_id=WS_RUN)
    texto = caplog.text
    assert "corpo-nao-deve-ir-para-o-log" not in texto and "nao-logar" not in texto


# ═══════════════════════════════════════════════════════════════════════════
# 5. SEM LEITURA NOVA — traduzível, execution_id, gates e RBAC preservados
# ═══════════════════════════════════════════════════════════════════════════

def test_run_id_traduzivel_nao_le_o_airflow(cliente):
    run = "manual__2026-08-03T12:49:24+00:00"
    db = _DbPausa(corridas_run={run: _linha_067(date(2026, 8, 3))})
    af = _Airflow()
    r = _post_pausa(cliente, db, af, dag_run_id=run)
    assert r.status_code == 200, r.text
    assert r.json()["execution_id"] == "20260803T124924"
    assert af.gets == []


def test_execution_id_nao_le_o_airflow(cliente):
    db = _DbPausa()
    af = _Airflow()
    r = _post_pausa(cliente, db, af, execution_id="20261011T184107")
    assert r.status_code == 200, r.text
    assert _insert_pausa(db)[1] == "20261011T184107"
    assert af.gets == []


def test_odate_ambiguo_recusa_antes_de_ler_o_airflow(cliente):
    linhas = [(f"manual__2026-08-03__PIPE__2026080{i}T0000000", "SUCESSO",
               datetime(2026, 8, 3, i), None, "manual", None, None) for i in (1, 2)]
    db = _DbPausa(corridas_dia=linhas)
    af = _Airflow()
    r = _post_pausa(cliente, db, af, data_referencia="2026-08-03")
    assert r.status_code == 409
    det = r.json()["detail"]
    assert det["erro"] == "corrida_ambigua" and len(det["candidatos"]) == 2
    assert "pausar" in det["mensagem"]
    assert af.gets == [] and db.escritas == []


def test_odate_sem_corrida_e_404_sem_ler_o_airflow(cliente):
    db = _DbPausa(corridas_dia=[])
    af = _Airflow()
    r = _post_pausa(cliente, db, af, data_referencia="2026-08-03")
    assert r.status_code == 404
    assert af.gets == [] and db.escritas == []


def test_modo_degradado_recusa_sem_ler_o_airflow(cliente):
    """Sem a 067 a identidade é aproximada — não alimenta gesto, nem com a
    leitura exata disponível."""
    db = _DbPausa(tem_067=False)
    af = _Airflow()
    r = _post_pausa(cliente, db, af, dag_run_id=WS_RUN)
    assert r.status_code == 409
    assert r.json()["detail"]["erro"] == "identidade_degradada"
    assert af.gets == [] and db.escritas == []


def test_data_referencia_invalida_e_422_sem_ler_o_airflow(cliente):
    db = _DbPausa(corridas_run={WS_RUN: _linha_067()})
    af = _Airflow()
    r = _post_pausa(cliente, db, af, dag_run_id=WS_RUN, data_referencia="11/10/2026")
    assert r.status_code == 422
    assert af.gets == [] and db.escritas == []


def test_dag_id_invalido_nao_le_o_airflow(cliente):
    db = _DbPausa(pipeline="nome com espaço", corridas_run={WS_RUN: _linha_067()})
    af = _Airflow()
    r = _post_pausa(cliente, db, af, dag_run_id=WS_RUN)
    assert r.status_code == 409
    assert r.json()["detail"]["erro"] == "corrida_sem_execution_id"
    assert af.gets == [] and db.escritas == []


def test_pausa_sem_permissao_nao_toca_banco_nem_airflow(cliente_sem_perm):
    db = MagicMock()
    af = _Airflow()
    r = _post_pausa(cliente_sem_perm, db, af, dag_run_id=WS_RUN)
    assert r.status_code == 403
    db.cursor.assert_not_called()
    assert af.gets == []


async def test_run_id_e_dag_id_vao_codificados_no_caminho(E):
    """run_id fora do padrão com `/` e `+` não muda de rota no Airflow — e a
    resposta tem de devolver o MESMO run_id para valer."""
    run = "dep__2026-08-03__PAI/../x+y"
    af = _Airflow(_dag_run(run_id=run))
    with patch("routers.execucoes.get_airflow_client", return_value=af):
        r = await E._completa_corrida_exata(PIPE, _ident_ws(run_id=run))
    assert af.gets == [(f"/api/v1/dags/{PIPE}/dagRuns/dep__2026-08-03__PAI%2F..%2Fx%2By",
                        None)]
    assert r["ts_nodash"] == TS and r["dag_run_id"] == run


@pytest.mark.parametrize("entrada", [
    ident.identidade_vazia(None, resolvido=True, ts_nodash=TS, run_id=WS_RUN,
                           dag_run_id=WS_RUN),
    _ident_ws(degradado=True),
    _ident_ws(motivo=ident.AMBIGUO),
    _ident_ws(motivo=ident.SEM_LINHA_NA_DATA),
    _ident_ws(motivo=ident.MIGRATION_067_PENDENTE),
    ident.identidade_vazia(ident.SEM_EXECUCAO_PARA_TS, resolvido=True, ts_nodash=TS),
    ident.identidade_vazia(ident.RUN_ID_NAO_TRADUZIVEL),
], ids=["ts_conhecido", "degradado", "ambiguo", "sem_linha", "sem_067",
        "so_ts_sentido_inverso", "sem_run_id"])
async def test_leitura_exata_so_quando_falta_o_ts_de_um_run_id(E, entrada):
    af = _Airflow()
    with patch("routers.execucoes.get_airflow_client", return_value=af):
        r = await E._completa_corrida_exata(PIPE, entrada)
    assert af.gets == [] and r is entrada


def test_gestos_compartilham_a_leitura_pelo_helper(E):
    """A completude mora em `_resolve_alvo_rerun` — prévia, reexecução e pausa
    a recebem pelo MESMO caminho, depois das recusas existentes."""
    import inspect
    src = inspect.getsource(E._resolve_alvo_rerun)
    assert "_completa_corrida_exata(oficial, ident)" in src
    for recusa in ('"corrida_ambigua"', '"identidade_degradada"', "SEM_LINHA_NA_DATA"):
        assert src.index(recusa) < src.index("_completa_corrida_exata(oficial, ident)")


# ═══════════════════════════════════════════════════════════════════════════
# 6. OS OUTROS CONSUMIDORES — prévia e reexecução
# ═══════════════════════════════════════════════════════════════════════════

_RUN_DEV = f"workspace__{'ab' * 4}-0000-4000-8000-{'cd' * 6}"


class _AirflowRerun(_ClientFake):
    """O Airflow da F4 (tasks, is_paused, clear) + a corrida exata."""

    def __init__(self, *, exata=None, erro=None, **kw):
        super().__init__(**kw)
        self.exata, self.erro = exata, erro
        self.gets: list = []

    async def get(self, url, params=None):
        self.gets.append(url)
        if "/dagRuns/" in url:
            if self.erro:
                raise self.erro
            return _RespFake(self.exata)
        return await super().get(url, params)


def _exatas(af):
    return [u for u in af.gets if "/dagRuns/" in u]


@pytest.fixture
def _rerun_legado(monkeypatch):
    """As mesmas condições autouse de tests/test_rerun_etapa_f4.py: o motor
    deste repo para a sonda de capacidade e o schema sem snapshot (130)."""
    from pathlib import Path
    from services import rerun as rr
    monkeypatch.setenv("DAGS_FOLDER", str(Path(__file__).parent.parent / "dags"))
    monkeypatch.setattr("services.param_snapshot.ativo", lambda cur, pipeline: False)
    rr._cache_capacidade.clear()
    yield
    rr._cache_capacidade.clear()


@pytest.mark.usefixtures("_rerun_legado")
def test_previa_com_run_id_workspace_completa_e_mantem_o_dag_run(cliente):
    db = _DbRerun(corridas=[_corrida(_RUN_DEV)], grafo={"DEV_F10_A": []})
    af = _AirflowRerun(exata=_dag_run(run_id=_RUN_DEV, dag_id="DEV_F10_A"))
    with patch("routers.execucoes.get_db_conn", return_value=db), \
         patch("routers.execucoes.get_airflow_client", return_value=af):
        r = cliente.get(f"/pipelines/DEV_F10_A/rerun/previa?task_id=etapa_x&run_id={_RUN_DEV}")
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["dag_run_id"] == _RUN_DEV
    assert b["identidade"]["ts_nodash"] == TS and b["identidade"]["motivo"] is None
    assert af.posts[0][1]["dry_run"] is True
    assert af.posts[0][1]["dag_run_id"] == _RUN_DEV
    assert _exatas(af) == [f"/api/v1/dags/DEV_F10_A/dagRuns/{_RUN_DEV}"]


@pytest.mark.usefixtures("_rerun_legado")
def test_previa_com_leitura_exata_falhando_segue_como_antes(cliente):
    db = _DbRerun(corridas=[_corrida(_RUN_DEV)], grafo={"DEV_F10_A": []})
    af = _AirflowRerun(erro=httpx.ConnectError("fora"))
    with patch("routers.execucoes.get_db_conn", return_value=db), \
         patch("routers.execucoes.get_airflow_client", return_value=af):
        r = cliente.get(f"/pipelines/DEV_F10_A/rerun/previa?task_id=etapa_x&run_id={_RUN_DEV}")
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["dag_run_id"] == _RUN_DEV and b["airflow_indisponivel"] is False
    assert b["identidade"]["ts_nodash"] is None
    assert b["identidade"]["motivo"] == ident.RUN_ID_NAO_TRADUZIVEL


@pytest.mark.usefixtures("_rerun_legado")
@pytest.mark.parametrize("falha", [False, True], ids=["leitura_ok", "leitura_falha"])
def test_rerun_com_run_id_workspace_limpa_a_corrida_pedida(cliente, falha):
    """A reexecução não usa o ts_nodash: a leitura exata não pode criar recusa
    nova nem trocar o dag_run do clear."""
    db = _DbRerun(corridas=[_corrida(_RUN_DEV)], grafo={"DEV_F10_A": []})
    af = _AirflowRerun(exata=_dag_run(run_id=_RUN_DEV, dag_id="DEV_F10_A"),
                       erro=httpx.ReadTimeout("lento") if falha else None)
    with patch("routers.execucoes.get_db_conn", return_value=db), \
         patch("routers.execucoes.get_airflow_client", return_value=af):
        r = cliente.post("/execucoes/rerun", json={
            "pipeline_name": "DEV_F10_A", "task_id": "etapa_x",
            "dag_run_id": _RUN_DEV, "data_referencia": "2026-08-03",
            "cascata": True})
    assert r.status_code == 200, r.text
    assert r.json()["dag_run_id"] == _RUN_DEV
    clears = [c for u, c in af.posts if u.endswith("/clearTaskInstances")
              and not c.get("dry_run")]
    assert clears and all(c["dag_run_id"] == _RUN_DEV for c in clears)
    assert _exatas(af) == [f"/api/v1/dags/DEV_F10_A/dagRuns/{_RUN_DEV}"]


# ═══════════════════════════════════════════════════════════════════════════
# 7. A VERSÃO — migration 168, patch 2.21.1
# ═══════════════════════════════════════════════════════════════════════════

def test_migration_168_e_idempotente_e_sobe_so_o_patch():
    from pathlib import Path
    raiz = Path(__file__).resolve().parents[1]
    migs = sorted((raiz / "sql/migrations").glob("168_*.sql"))
    assert [m.name for m in migs] == ["168_versao_pausa_corrida_exata.sql"]
    sql = migs[0].read_text(encoding="utf-8")
    assert "N'Pausa de etapa pela corrida exata do Airflow'" in sql
    assert "ELSE IF EXISTS (SELECT 1 FROM dbo.etl_versao_ferramenta WHERE titulo = @titulo)" in sql
    assert "SET @nova = CONCAT(@maior, '.', @menor, '.', @patch + 1);" in sql
    assert "config_key = 'app_version'" in sql and "config_key = 'app_release_name'" in sql
    assert sql.rstrip().endswith("GO")
    assert (raiz / "docs/release-notes/2.21.1-pausa-corrida-exata.md").is_file()
