"""
F2 da spec de operação no nível de etapa (docs/spec-operacao-nivel-etapa.md):

  • a ponte de identidade run_id ↔ ts_nodash numa peça só
    (api/services/execucao_identidade.py) — os DOIS sentidos, o caso AMBÍGUO
    (duas corridas no mesmo ODATE) e os casos IMPOSSÍVEIS;
  • o endpoint GET /pipelines/{p}/execucao — com execução, sem execução,
    degradado sem a migration 067;
  • NÃO-REGRESSÃO do rerun: o corpo do clearTaskInstances enviado ao Airflow
    tem de continuar byte a byte o mesmo depois da extração da ponte.

Dublês: FakeDb/FakeCur locais (o SQL desta fase é próprio) e um client HTTP
falso para o Airflow. Nada toca rede nem banco — mesmo padrão de
test_dependencias_f5_malhas.py.
"""
from __future__ import annotations

import os
import sys
from datetime import date, datetime, time, timedelta
from unittest.mock import MagicMock, patch

import pytest

if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()
os.environ.setdefault("MSSQL_CONN_STR", "__mock__")
from api.main import app as _app  # noqa: F401  (ordem de import — ver test_copias.py)

from deps import PERM_EXECUTAR, get_current_user
from services import data_referencia as dref
from services import execucao_identidade as ident

_D = date(2026, 8, 3)

# Corrida REAL colhida no ambiente dev em 2026-08-03 — a prova viva da ponte:
#   etl_pipeline_execucao.execution_id = RUN_ORQ  (run_id do Airflow)
#   dag_run.logical_date               = LOGICAL
#   etl_job_execution.execution_id     = TS       (ts_nodash da logical date)
# Repare que o '20260803T094924' embutido no RUN_ORQ é relógio LOCAL (UTC-3) e
# NÃO é o ts_nodash — é a armadilha que ts_nodash_do_run_id recusa.
RUN_ORQ = "manual__2026-08-03__DEV_F10_A__20260803T094924510486"
LOGICAL = "2026-08-03T12:49:24.715592+00:00"
TS = "20260803T124924"


# ═══════════════════════════════ conversões puras ════════════════════════════

@pytest.mark.parametrize("iso,esperado", [
    ("2026-07-05T03:00:00+00:00", "20260705T030000"),
    ("2026-07-05T03:00:00.123456+00:00", "20260705T030000"),
    ("2026-07-05T03:00:00Z", "20260705T030000"),
    ("", ""),
    (None, ""),
])
def test_ts_nodash(iso, esperado):
    assert ident.ts_nodash(iso) == esperado


def test_ts_nodash_e_a_mesma_funcao_do_router():
    """A extração não pode ter deixado uma SEGUNDA implementação para trás:
    o nome antigo do router é o MESMO objeto do service."""
    import routers.execucoes as E
    assert E._iso_to_ts_nodash is ident.ts_nodash
    assert E._escolhe_dag_run is ident.escolhe_dag_run


@pytest.mark.parametrize("run_id,esperado", [
    # Formas geradas pelo PRÓPRIO Airflow — a logical date está na string.
    ("scheduled__2026-08-03T06:00:00+00:00", "20260803T060000"),
    ("manual__2026-08-03T03:15:32.404876+00:00", "20260803T031532"),
    ("backfill__2026-08-03T06:00:00+00:00", "20260803T060000"),
    ("scheduled__2026-08-03T06:00:00Z", "20260803T060000"),
    # Espaço nas pontas é tolerado (strip) — VARCHAR do banco não deveria
    # trazer, mas tolerar aqui não abre porta para chute nenhum.
    (" scheduled__2026-08-03T06:00:00+00:00 ", "20260803T060000"),
])
def test_ts_nodash_do_run_id_traduz_o_que_e_do_airflow(run_id, esperado):
    assert ident.ts_nodash_do_run_id(run_id) == esperado


@pytest.mark.parametrize("run_id", [
    # ⚠️ A ARMADILHA: run_ids gerados pelo Orquestra. O timestamp embutido é
    # relógio LOCAL e o '2026-08-03' do meio é o ODATE — traduzir daria um
    # ts_nodash 3 horas errado. Tem de devolver None ("pergunte ao Airflow").
    RUN_ORQ,
    "dep__2026-08-03__DEV_F10_A__20260803T094949928683",
    "manual__2026-08-03__DEV_F10_B__20260803T094925362361",
    # Lixo e formas parciais.
    "", None, "manual__", "manual__2026-08-03", "20260803T124924",
    "copy_123_20260803T094924", "scheduled__2026-08-03T06:00",
    "prefixo_qualquer__2026-08-03T06:00:00+00:00",
])
def test_ts_nodash_do_run_id_recusa_o_que_nao_e_do_airflow(run_id):
    assert ident.ts_nodash_do_run_id(run_id) is None


def test_run_id_do_orquestra_nao_vira_ts_nodash_errado():
    """Prova explícita da armadilha: se a regex fosse frouxa, sairia
    '20260803T094924' (local) em vez de '20260803T124924' (UTC)."""
    assert ident.ts_nodash_do_run_id(RUN_ORQ) != "20260803T094924"
    assert ident.ts_nodash_do_run_id(RUN_ORQ) is None
    # O caminho CERTO é o dag_run.
    fechada = ident.completa_com_airflow(
        ident.identidade_vazia(ident.RUN_ID_NAO_TRADUZIVEL, run_id=RUN_ORQ),
        [{"dag_run_id": RUN_ORQ, "logical_date": LOGICAL, "state": "success"}])
    assert fechada["ts_nodash"] == TS
    assert fechada["resolvido"] is True


# ═════════════════ janela do ODATE × services.data_referencia ════════════════

@pytest.mark.parametrize("virada", [None, "00:00", "06:00", "20:00", "23:30"])
def test_janela_odate_e_a_inversa_de_calcular(virada):
    """PARIDADE: todo instante DENTRO da janela pertence ao ODATE, e os
    instantes imediatamente FORA (nas duas bordas) não pertencem."""
    ini, fim = ident.janela_odate(_D, virada)
    assert ini < fim
    for dentro in (ini, ini + timedelta(minutes=1),
                   fim - timedelta(seconds=1),
                   ini + (fim - ini) / 2):
        assert dref.calcular(dentro, virada) == _D, dentro
    for fora in (ini - timedelta(seconds=1), fim, fim + timedelta(minutes=1)):
        assert dref.calcular(fora, virada) != _D, fora


def test_janela_odate_virada_padrao_e_o_dia_do_calendario():
    assert ident.janela_odate(_D, "00:00") == (
        datetime(2026, 8, 3, 0, 0), datetime(2026, 8, 4, 0, 0))


def test_janela_odate_virada_20h_atravessa_a_meia_noite():
    """O caso que motivou a spec: 31/07 23:30 e 01/08 00:40 são a MESMA corrida."""
    ini, fim = ident.janela_odate(date(2026, 8, 1), "20:00")
    assert ini == datetime(2026, 7, 31, 20, 0)
    assert fim == datetime(2026, 8, 1, 20, 0)


# ═══════════════════════════ escolhe_dag_run / dag_run_por_id ════════════════

_RUNS = [
    {"dag_run_id": "r_hoje", "logical_date": "2026-07-05T06:00:00+00:00",
     "state": "running"},
    {"dag_run_id": "r_ontem", "logical_date": "2026-07-04T06:00:00+00:00",
     "state": "failed"},
]


def test_escolhe_dag_run_preserva_fallback_legado():
    assert ident.escolhe_dag_run(_RUNS, "20260704T060000")["dag_run_id"] == "r_ontem"
    assert ident.escolhe_dag_run(_RUNS, "20260705T060000")["dag_run_id"] == "r_hoje"
    assert ident.escolhe_dag_run(_RUNS, "20990101T000000")["dag_run_id"] == "r_ontem"


def test_dag_run_por_id_e_match_exato_sem_fallback():
    assert ident.dag_run_por_id(_RUNS, "r_ontem")["dag_run_id"] == "r_ontem"
    assert ident.dag_run_por_id(_RUNS, "r_inexistente") is None
    assert ident.dag_run_por_id(_RUNS, "") is None
    assert ident.dag_run_por_id([], "r_ontem") is None


# ══════════════════════════════ dublê de banco ═══════════════════════════════

class FakeCur:
    """Dispatcher de SQL por prefixo normalizado. Levanta para SQL não previsto
    — teste que passa por engano é pior que teste que falha."""

    def __init__(self, db):
        self.db = db
        self._rows = []
        self.rowcount = -1

    def execute(self, sql, params=()):  # noqa: C901 — dispatcher de dublê
        db = self.db
        s = " ".join(str(sql).split())
        self._rows = []

        if s.startswith("SELECT OBJECT_ID('dbo.etl_pipeline_execucao'"):
            self._rows = [(1 if db.com_067 else None,)]
            return
        if s.startswith("SELECT pipeline_name FROM dbo.etl_pipeline WHERE"):
            alvo = str(params[0] or "").casefold()
            for p in db.pipelines:
                if p.casefold() == alvo:
                    self._rows = [(p,)]
            return
        if s.startswith("SELECT config_value FROM dbo.etl_app_config"):
            self._rows = [(db.virada,)] if db.virada is not None else []
            return
        if s.startswith("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS"):
            cols = ["job_name", "job_type", "execution_order"]
            if db.com_038:
                cols.append("depends_on_jobs")
            self._rows = [(c,) for c in cols]
            return
        if s.startswith("SELECT job_name, ISNULL(job_type"):
            if not db.com_038 and "depends_on_jobs" in s:
                raise RuntimeError("Invalid column name 'depends_on_jobs'")
            alvo = str(params[0] or "").casefold()
            self._rows = [
                (j["job_name"], j.get("job_type") or "datastage",
                 j.get("ordem"), j.get("deps") if db.com_038 else None)
                for j in db.desenho if j["pipeline"].casefold() == alvo]
            return
        if s.startswith("SELECT execution_id, status, inicio, fim, "
                        "disparado_por, motivo FROM dbo.etl_pipeline_execucao"):
            if not db.com_067:
                raise RuntimeError("Invalid object name 'etl_pipeline_execucao'")
            pipe, dref_ = params
            self._rows = [
                (c["run_id"], c["status"], c["inicio"], c["fim"],
                 c.get("disparado_por"), c.get("motivo"))
                for c in db.corridas
                if c["pipeline"].casefold() == str(pipe).casefold()
                and c["data_referencia"] == dref_]
            return
        if s.startswith("SELECT data_referencia, status, inicio, fim, "
                        "disparado_por, motivo FROM dbo.etl_pipeline_execucao"):
            if not db.com_067:
                raise RuntimeError("Invalid object name 'etl_pipeline_execucao'")
            pipe, run_id = params
            self._rows = [
                (c["data_referencia"], c["status"], c["inicio"], c["fim"],
                 c.get("disparado_por"), c.get("motivo"))
                for c in db.corridas
                if c["pipeline"].casefold() == str(pipe).casefold()
                and c["run_id"] == run_id]
            return
        if s.startswith("SELECT execution_id, status, inicio, fim, "
                        "disparado_por, motivo, data_referencia"):
            if not db.com_067:
                raise RuntimeError("Invalid object name 'etl_pipeline_execucao'")
            pipe, d_ini, d_fim = params
            self._rows = [
                (c["run_id"], c["status"], c["inicio"], c["fim"],
                 c.get("disparado_por"), c.get("motivo"), c["data_referencia"])
                for c in db.corridas
                if c["pipeline"].casefold() == str(pipe).casefold()
                and d_ini <= c["data_referencia"] <= d_fim]
            return
        if s.startswith("SELECT job_name, task_id, status, start_time"):
            ts, pipe = params
            self._rows = [
                (e["job_name"], e.get("task_id") or e["job_name"], e["status"],
                 e.get("inicio"), e.get("fim"), e.get("dur"),
                 e.get("status_code"), e.get("attempt"), e.get("log_file"),
                 e.get("host"))
                for e in db.etapas
                if e["ts"] == ts
                and e["pipeline"].casefold() == str(pipe).casefold()]
            return
        if s.startswith("SELECT execution_id, MIN(start_time) FROM dbo.etl_job_execution"):
            pipe, ini, fim = params
            agrupado = {}
            for e in db.etapas:
                if e["pipeline"].casefold() != str(pipe).casefold():
                    continue
                if e.get("inicio") is None or not (ini <= e["inicio"] < fim):
                    continue
                atual = agrupado.get(e["ts"])
                if atual is None or e["inicio"] < atual:
                    agrupado[e["ts"]] = e["inicio"]
            self._rows = sorted(agrupado.items())
            return
        raise AssertionError(f"SQL não previsto no dublê: {s[:160]}")

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def close(self):
        pass


class FakeDb:
    def __init__(self, *, pipelines=("DEV_F10_A",), corridas=(), etapas=(),
                 desenho=(), com_067=True, com_038=True, virada="00:00"):
        self.pipelines = list(pipelines)
        self.corridas = [dict(c) for c in corridas]
        self.etapas = [dict(e) for e in etapas]
        self.desenho = [dict(d) for d in desenho]
        self.com_067 = com_067
        self.com_038 = com_038
        self.virada = virada

    def cursor(self):
        return FakeCur(self)

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


def _corrida(run_id, *, pipeline="DEV_F10_A", data_referencia=_D,
             status="SUCESSO", inicio=datetime(2026, 8, 3, 12, 49, 32),
             fim=datetime(2026, 8, 3, 12, 49, 49), disparado_por="manual"):
    return {"run_id": run_id, "pipeline": pipeline,
            "data_referencia": data_referencia, "status": status,
            "inicio": inicio, "fim": fim, "disparado_por": disparado_por,
            "motivo": None}


def _etapa(job, ts=TS, *, pipeline="DEV_F10_A", status="SUCCESS",
           inicio=datetime(2026, 8, 3, 9, 49, 37), dur=8):
    return {"job_name": job, "ts": ts, "pipeline": pipeline, "status": status,
            "inicio": inicio, "fim": inicio + timedelta(seconds=dur),
            "dur": dur, "attempt": None}


def _no(job, *, pipeline="DEV_F10_A", ordem=1, deps=None, tipo="http"):
    return {"job_name": job, "pipeline": pipeline, "ordem": ordem,
            "deps": deps, "job_type": tipo}


# ═══════════════ sentido A: (pipeline, ODATE) → ts_nodash / dag_run ══════════

def test_resolve_por_odate_traduz_run_id_do_airflow_sem_rede():
    db = FakeDb(corridas=[_corrida("scheduled__2026-08-03T06:00:00+00:00")])
    r = ident.resolve_por_odate(db.cursor(), "DEV_F10_A", _D)
    assert r["resolvido"] is True
    assert r["ts_nodash"] == "20260803T060000"
    assert r["run_id"] == r["dag_run_id"] == "scheduled__2026-08-03T06:00:00+00:00"
    assert r["ambiguo"] is False and r["degradado"] is False
    assert r["motivo"] is None
    assert ident.precisa_airflow(r) is False


def test_resolve_por_odate_run_id_do_orquestra_pede_airflow():
    """O caso COMUM da malha: o run_id não carrega a logical date, então a
    identidade volta NÃO resolvida — com o motivo explícito, nunca com um
    ts_nodash chutado."""
    db = FakeDb(corridas=[_corrida(RUN_ORQ)])
    r = ident.resolve_por_odate(db.cursor(), "DEV_F10_A", _D)
    assert r["resolvido"] is False
    assert r["ts_nodash"] is None
    assert r["motivo"] == ident.RUN_ID_NAO_TRADUZIVEL
    assert r["run_id"] == RUN_ORQ
    assert ident.precisa_airflow(r) is True
    # ... e fecha com o dag_run.
    fechada = ident.completa_com_airflow(
        r, [{"dag_run_id": RUN_ORQ, "logical_date": LOGICAL, "state": "success"}])
    assert fechada["resolvido"] is True
    assert fechada["ts_nodash"] == TS
    assert fechada["logical_date"] == LOGICAL
    assert ident.ORIGEM_AIRFLOW in fechada["origem"]


def test_resolve_por_odate_sem_linha_na_data():
    db = FakeDb(corridas=[_corrida(RUN_ORQ, data_referencia=date(2026, 8, 1))])
    r = ident.resolve_por_odate(db.cursor(), "DEV_F10_A", _D)
    assert r["resolvido"] is False
    assert r["motivo"] == ident.SEM_LINHA_NA_DATA
    assert r["candidatos"] == []
    assert ident.precisa_airflow(r) is False


def test_resolve_por_odate_ambiguo_escolhe_mas_declara():
    """DUAS corridas no mesmo ODATE (rerun manual + disparo da malha): escolhe a
    MESMA que o painel da malha escolheria e DECLARA a escolha."""
    cedo = _corrida("scheduled__2026-08-03T06:00:00+00:00",
                    inicio=datetime(2026, 8, 3, 6, 0, 5), disparado_por="agenda")
    tarde = _corrida("scheduled__2026-08-03T18:00:00+00:00",
                     inicio=datetime(2026, 8, 3, 18, 0, 5), disparado_por="manual")
    db = FakeDb(corridas=[cedo, tarde])
    r = ident.resolve_por_odate(db.cursor(), "DEV_F10_A", _D)
    assert r["resolvido"] is True
    assert r["ambiguo"] is True
    assert r["regra"] == ident.REGRA_MAIS_RECENTE
    assert r["ts_nodash"] == "20260803T180000"          # a MAIS RECENTE
    assert len(r["candidatos"]) == 2                    # as duas, declaradas
    assert {c["disparado_por"] for c in r["candidatos"]} == {"agenda", "manual"}


def test_resolve_por_odate_ambiguo_bate_com_a_regra_do_painel_da_malha():
    """A vencedora tem de ser LITERALMENTE a de services.dependencias
    .mais_recente_da_data — descer para outra corrida faria o drill-down
    divergir do painel de cima (o defeito D14/D15)."""
    from services import dependencias as deps_svc
    linhas = [
        {"execution_id": "scheduled__2026-08-03T06:00:00+00:00",
         "inicio": datetime(2026, 8, 3, 6, 0, 5)},
        {"execution_id": "scheduled__2026-08-03T18:00:00+00:00",
         "inicio": datetime(2026, 8, 3, 18, 0, 5)},
    ]
    esperado = deps_svc.mais_recente_da_data(linhas)["execution_id"]
    db = FakeDb(corridas=[
        _corrida(linhas[0]["execution_id"], inicio=linhas[0]["inicio"]),
        _corrida(linhas[1]["execution_id"], inicio=linhas[1]["inicio"])])
    assert ident.resolve_por_odate(db.cursor(), "DEV_F10_A", _D)["run_id"] == esperado


def test_resolve_por_odate_estrito_recusa_ambiguidade():
    """Modo do gesto destrutivo (rerun da F4): com duas candidatas, NÃO resolve
    — devolve a lista para o gesto perguntar."""
    db = FakeDb(corridas=[
        _corrida("scheduled__2026-08-03T06:00:00+00:00"),
        _corrida("scheduled__2026-08-03T18:00:00+00:00")])
    r = ident.resolve_por_odate(db.cursor(), "DEV_F10_A", _D, estrito=True)
    assert r["resolvido"] is False
    assert r["motivo"] == ident.AMBIGUO
    assert r["ambiguo"] is True
    assert len(r["candidatos"]) == 2
    assert r["ts_nodash"] is None
    assert ident.precisa_airflow(r) is False


def test_resolve_por_odate_estrito_passa_quando_ha_uma_so():
    db = FakeDb(corridas=[_corrida("scheduled__2026-08-03T06:00:00+00:00")])
    r = ident.resolve_por_odate(db.cursor(), "DEV_F10_A", _D, estrito=True)
    assert r["resolvido"] is True and r["ambiguo"] is False


# ════════════════════ sentido A': (pipeline, run_id) → ts_nodash ═════════════

def test_resolve_por_run_id_do_airflow_traduz_e_enriquece():
    db = FakeDb(corridas=[_corrida("scheduled__2026-08-03T06:00:00+00:00")])
    r = ident.resolve_por_run_id(db.cursor(), "DEV_F10_A",
                                 "scheduled__2026-08-03T06:00:00+00:00")
    assert r["resolvido"] is True
    assert r["ts_nodash"] == "20260803T060000"
    assert r["data_referencia"] == _D          # ODATE veio da 067
    assert r["candidatos"][0]["status"] == "SUCESSO"
    assert ident.ORIGEM_067 in r["origem"]


def test_resolve_por_run_id_do_orquestra_fica_incompleto_mas_com_odate():
    """Run_id do Orquestra: o ODATE sai da 067, mas o ts_nodash só do Airflow —
    e o motivo tem de continuar dizendo isso (não pode ser apagado ao enxertar
    a corrida)."""
    db = FakeDb(corridas=[_corrida(RUN_ORQ)])
    r = ident.resolve_por_run_id(db.cursor(), "DEV_F10_A", RUN_ORQ)
    assert r["resolvido"] is False
    assert r["ts_nodash"] is None
    assert r["motivo"] == ident.RUN_ID_NAO_TRADUZIVEL
    assert r["data_referencia"] == _D
    assert ident.precisa_airflow(r) is True


def test_resolve_por_run_id_desconhecido_na_067():
    db = FakeDb(corridas=[_corrida(RUN_ORQ)])
    r = ident.resolve_por_run_id(db.cursor(), "DEV_F10_A",
                                 "scheduled__2026-08-03T06:00:00+00:00")
    assert r["resolvido"] is True              # a string traduz
    assert r["data_referencia"] is None        # mas não há corrida registrada
    assert r["candidatos"] == []


def test_resolve_por_run_id_sem_067_degrada():
    db = FakeDb(com_067=False)
    r = ident.resolve_por_run_id(db.cursor(), "DEV_F10_A",
                                 "scheduled__2026-08-03T06:00:00+00:00")
    assert r["degradado"] is True
    assert r["ts_nodash"] == "20260803T060000"
    assert r["data_referencia"] is None


def test_resolve_por_run_id_vazio():
    db = FakeDb()
    r = ident.resolve_por_run_id(db.cursor(), "DEV_F10_A", "")
    assert r["resolvido"] is False and r["run_id"] is None


def test_aplica_corrida_none_nao_apaga_o_que_ja_se_sabe():
    base = ident.identidade_vazia(None, resolvido=True, ts_nodash=TS,
                                  run_id=RUN_ORQ, logical_date=LOGICAL,
                                  origem=ident.ORIGEM_AIRFLOW)
    r = ident.aplica_corrida(base, None)
    assert r["ts_nodash"] == TS and r["logical_date"] == LOGICAL
    assert r["data_referencia"] is None


def test_corrida_por_run_id_sem_067_devolve_none():
    db = FakeDb(com_067=False)
    assert ident.corrida_por_run_id(db.cursor(), "DEV_F10_A", RUN_ORQ) is None
    assert ident.corrida_por_run_id(FakeDb().cursor(), "DEV_F10_A", "") is None


# ════════════════════ sentido B: ts_nodash → linha da 067 ════════════════════

def test_resolve_por_ts_nodash_acha_a_corrida_pelo_run_id_do_airflow():
    db = FakeDb(corridas=[_corrida("scheduled__2026-08-03T06:00:00+00:00")])
    r = ident.resolve_por_ts_nodash(db.cursor(), "DEV_F10_A", "20260803T060000")
    assert r["resolvido"] is True
    assert r["run_id"] == "scheduled__2026-08-03T06:00:00+00:00"
    assert r["data_referencia"] == _D
    assert r["motivo"] is None


def test_resolve_por_ts_nodash_com_run_id_ja_resolvido_no_airflow():
    """Run_id do Orquestra: a string não traduz, mas o chamador que já perguntou
    ao Airflow entrega o run_id e o casamento vira igualdade pura."""
    db = FakeDb(corridas=[_corrida(RUN_ORQ)])
    sem = ident.resolve_por_ts_nodash(db.cursor(), "DEV_F10_A", TS)
    # `resolvido` é sobre o ts_nodash (que veio pronto) — o que faltou foi o
    # lado da 067; ver a nota de semântica em identidade_vazia.
    assert sem["resolvido"] is True
    assert sem["run_id"] is None
    assert sem["motivo"] == ident.SEM_EXECUCAO_PARA_TS
    assert len(sem["candidatos"]) == 1          # mostra o que existia
    com = ident.resolve_por_ts_nodash(db.cursor(), "DEV_F10_A", TS,
                                      run_id=RUN_ORQ)
    assert com["resolvido"] is True
    assert com["run_id"] == RUN_ORQ
    assert com["data_referencia"] == _D


def test_resolve_por_ts_nodash_sem_nenhuma_corrida_na_067():
    """Produção pré-retomada: a 067 existe e está VAZIA. O drill-down por
    execution_id tem de seguir funcionando (ts conhecido), declarando que não
    achou a corrida."""
    db = FakeDb(corridas=[])
    r = ident.resolve_por_ts_nodash(db.cursor(), "DEV_F10_A", TS)
    assert r["resolvido"] is True and r["ts_nodash"] == TS
    assert r["run_id"] is None
    assert r["motivo"] == ident.SEM_EXECUCAO_PARA_TS
    assert r["candidatos"] == []


def test_resolve_por_ts_nodash_vazio_nao_resolve():
    db = FakeDb(corridas=[])
    assert ident.resolve_por_ts_nodash(db.cursor(), "DEV_F10_A", "")["resolvido"] is False


def test_resolve_por_ts_nodash_ts_torto_nao_estoura():
    """Entrada fora do formato não estoura nem vira consulta: o ts é mantido
    (é o que o chamador pediu) mas nada casa."""
    db = FakeDb(corridas=[])
    r = ident.resolve_por_ts_nodash(db.cursor(), "DEV_F10_A", "nao-e-ts")
    assert r["run_id"] is None
    assert r["motivo"] == ident.SEM_EXECUCAO_PARA_TS


def test_resolve_por_ts_nodash_janela_pega_odate_do_dia_anterior():
    """ODATE ∈ [data(ts)-1, data(ts)] — corrida cujo ODATE é o dia ANTERIOR à
    logical date tem de continuar visível."""
    db = FakeDb(corridas=[_corrida("scheduled__2026-08-03T06:00:00+00:00",
                                   data_referencia=date(2026, 8, 2))])
    r = ident.resolve_por_ts_nodash(db.cursor(), "DEV_F10_A", "20260803T060000")
    assert r["resolvido"] is True
    assert r["data_referencia"] == date(2026, 8, 2)


# ═══════════════════════════ completa_com_airflow ════════════════════════════

def test_completa_com_airflow_sem_dag_run_correspondente():
    """Corrida na 067 sem dag_run no Airflow (run expurgado / DAG recriada):
    motivo explícito, nunca um match por aproximação."""
    base = ident.identidade_vazia(ident.RUN_ID_NAO_TRADUZIVEL, run_id=RUN_ORQ)
    r = ident.completa_com_airflow(base, [
        {"dag_run_id": "outro_run", "logical_date": LOGICAL, "state": "success"}])
    assert r["resolvido"] is False
    assert r["motivo"] == ident.SEM_DAG_RUN


def test_completa_com_airflow_lista_vazia_nao_resolve():
    base = ident.identidade_vazia(ident.RUN_ID_NAO_TRADUZIVEL, run_id=RUN_ORQ)
    assert ident.completa_com_airflow(base, [])["resolvido"] is False
    assert ident.completa_com_airflow(base, None)["resolvido"] is False


def test_completa_com_airflow_sentido_inverso_exige_match_exato():
    """Com ts_nodash e sem run_id, só vale o MATCH EXATO — o fallback legado de
    escolhe_dag_run (1º terminado) resolveria pelo run ERRADO."""
    base = ident.identidade_vazia(None, resolvido=True, ts_nodash=TS)
    ok = ident.completa_com_airflow(base, [
        {"dag_run_id": RUN_ORQ, "logical_date": LOGICAL, "state": "success"}])
    assert ok["run_id"] == RUN_ORQ and ok["resolvido"] is True
    ruim = ident.completa_com_airflow(base, [
        {"dag_run_id": "r_outro", "logical_date": "2026-07-04T06:00:00+00:00",
         "state": "failed"}])
    assert ruim["motivo"] == ident.SEM_DAG_RUN
    assert ruim["run_id"] is None       # NÃO pegou o fallback legado
    assert ruim["dag_run_id"] is None   # ... logo a F4 não age


def test_completa_com_airflow_airflow_vence_divergencia():
    """ts derivado da string × ts do Airflow: vence o Airflow (autoridade)."""
    base = ident.identidade_vazia(
        None, resolvido=True, ts_nodash="20260803T060000",
        run_id="scheduled__2026-08-03T06:00:00+00:00")
    r = ident.completa_com_airflow(base, [
        {"dag_run_id": "scheduled__2026-08-03T06:00:00+00:00",
         "logical_date": "2026-08-03T09:00:00+00:00", "state": "success"}])
    assert r["ts_nodash"] == "20260803T090000"


def test_completa_com_airflow_nao_muta_a_entrada():
    base = ident.identidade_vazia(ident.RUN_ID_NAO_TRADUZIVEL, run_id=RUN_ORQ)
    ident.completa_com_airflow(
        base, [{"dag_run_id": RUN_ORQ, "logical_date": LOGICAL}])
    assert base["ts_nodash"] is None and base["resolvido"] is False


# ══════════════════════ degradação sem a migration 067 ═══════════════════════

def test_degradado_sem_067_resolve_pela_janela_do_odate():
    db = FakeDb(com_067=False, etapas=[
        _etapa("http_saude"),                     # start_time 03/08 09:49
        _etapa("outro", ts="20260801T060000",
               inicio=datetime(2026, 8, 1, 6, 0, 5))])   # fora da janela
    r = ident.resolve_por_odate(db.cursor(), "DEV_F10_A", _D, virada="00:00")
    assert r["resolvido"] is True
    assert r["degradado"] is True
    assert r["ts_nodash"] == TS
    assert r["run_id"] is None                    # não há de onde tirar
    assert r["origem"] == ident.ORIGEM_JOB_EXECUTION
    # Degradado NUNCA pede rede — decisão registrada em precisa_airflow.
    assert ident.precisa_airflow(r) is False
    assert r["ambiguo"] is False


def test_degradado_sem_067_ambiguo_declara_candidatos():
    db = FakeDb(com_067=False, etapas=[
        _etapa("a", ts="20260803T060000", inicio=datetime(2026, 8, 3, 6, 0, 5)),
        _etapa("b", ts="20260803T180000", inicio=datetime(2026, 8, 3, 18, 0, 5))])
    r = ident.resolve_por_odate(db.cursor(), "DEV_F10_A", _D, virada="00:00")
    assert r["ambiguo"] is True and r["degradado"] is True
    assert r["ts_nodash"] == "20260803T180000"
    assert len(r["candidatos"]) == 2
    estrito = ident.resolve_por_odate(db.cursor(), "DEV_F10_A", _D,
                                      virada="00:00", estrito=True)
    assert estrito["resolvido"] is False and estrito["motivo"] == ident.AMBIGUO


def test_degradado_sem_067_sem_execucao_na_janela():
    db = FakeDb(com_067=False, etapas=[])
    r = ident.resolve_por_odate(db.cursor(), "DEV_F10_A", _D)
    assert r["resolvido"] is False
    assert r["motivo"] == ident.SEM_LINHA_NA_DATA
    assert r["degradado"] is True


def test_degradado_por_ts_nodash_sinaliza_067_pendente():
    db = FakeDb(com_067=False)
    r = ident.resolve_por_ts_nodash(db.cursor(), "DEV_F10_A", TS)
    assert r["degradado"] is True
    assert r["motivo"] == ident.MIGRATION_067_PENDENTE
    assert r["ts_nodash"] == TS      # o ts_nodash em si continua válido


# ═════════════════════════ composição desenho × execução ═════════════════════

def test_compor_etapas_desenho_sem_execucao_fica_neutro():
    """Regra de honestidade do §3: etapa sem linha de execução é NEUTRA."""
    etapas = ident.compor_etapas(
        [{"job_name": "extrai", "job_type": "http", "execution_order": 1,
          "depends_on_jobs": []},
         {"job_name": "carrega", "job_type": "sql", "execution_order": 2,
          "depends_on_jobs": ["extrai"]}],
        [{"job_name": "extrai", "status": "SUCCESS", "duration_seconds": 8}])
    assert [e["job_name"] for e in etapas] == ["extrai", "carrega"]
    assert etapas[0]["status"] == "SUCCESS" and etapas[0]["sem_execucao"] is False
    assert etapas[1]["status"] is None and etapas[1]["sem_execucao"] is True
    assert etapas[1]["depends_on_jobs"] == ["extrai"]
    assert all(e["no_desenho"] for e in etapas)


def test_compor_etapas_execucao_fora_do_desenho_aparece():
    """O desenho é o de HOJE e a execução é a de ONTEM: etapa que rodou mas
    sumiu do desenho não pode desaparecer da resposta."""
    etapas = ident.compor_etapas(
        [{"job_name": "novo", "job_type": "http", "execution_order": 1,
          "depends_on_jobs": []}],
        [{"job_name": "aposentado", "status": "FAILED"}])
    assert [e["job_name"] for e in etapas] == ["novo", "aposentado"]
    assert etapas[0]["no_desenho"] is True and etapas[0]["sem_execucao"] is True
    assert etapas[1]["no_desenho"] is False and etapas[1]["status"] == "FAILED"


def test_compor_etapas_casa_grafia_divergente():
    """Colação CI do banco × dict case-sensitive do Python (incidente PR #236):
    'Http_Saude' na execução tem de casar com 'http_saude' no desenho."""
    etapas = ident.compor_etapas(
        [{"job_name": "http_saude", "execution_order": 1, "depends_on_jobs": []}],
        [{"job_name": "HTTP_SAUDE", "status": "SUCCESS"}])
    assert len(etapas) == 1
    assert etapas[0]["status"] == "SUCCESS"
    assert etapas[0]["no_desenho"] is True


def test_compor_etapas_tudo_vazio():
    assert ident.compor_etapas([], []) == []


# ═══════════════════════════ o endpoint (integração) ═════════════════════════

class _RespFake:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status
        self.is_success = 200 <= status < 300
        self.text = ""

    def json(self):
        return self._payload


class _ClientFake:
    """Dublê do httpx.AsyncClient usado como `async with`."""

    def __init__(self, runs=None, erro=None, status=200):
        self.runs = runs if runs is not None else []
        self.erro = erro
        self.status = status
        self.chamadas = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, params=None):
        self.chamadas.append(("GET", url, params))
        if self.erro:
            raise self.erro
        return _RespFake({"dag_runs": self.runs}, self.status)

    async def post(self, url, json=None, headers=None):
        self.chamadas.append(("POST", url, json))
        return _RespFake({"task_instances": [{"task_id": "t1"}]})


@pytest.fixture
def auth(app):
    app.dependency_overrides[get_current_user] = lambda: {
        "matricula": "DEV1", "perfil": "desenvolvedor",
        "permissoes": [PERM_EXECUTAR, "tela_malha"],
    }
    yield
    app.dependency_overrides.pop(get_current_user, None)


def _chama(client, db, runs=None, url="/pipelines/DEV_F10_A/execucao",
           erro=None, status=200):
    cli = _ClientFake(runs=runs, erro=erro, status=status)
    with patch("routers.execucoes.get_db_conn", return_value=db), \
         patch("routers.execucoes.get_airflow_client", return_value=cli):
        r = client.get(url)
    return r, cli


def _db_completo(**kw):
    base = dict(
        corridas=[_corrida(RUN_ORQ)],
        etapas=[_etapa("http_saude")],
        desenho=[_no("http_saude")],
    )
    base.update(kw)
    return FakeDb(**base)


def test_endpoint_com_execucao(client, auth):
    r, cli = _chama(client, _db_completo(),
                    runs=[{"dag_run_id": RUN_ORQ, "logical_date": LOGICAL,
                           "state": "success"}],
                    url=f"/pipelines/DEV_F10_A/execucao?data_referencia={_D}")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["pipeline_name"] == "DEV_F10_A"
    assert d["data_referencia"] == "2026-08-03"
    assert d["vazio"] is False and d["razao"] is None
    # A ponte, nos dois lados, na MESMA resposta:
    assert d["identidade"]["resolvido"] is True
    assert d["identidade"]["ts_nodash"] == TS
    assert d["identidade"]["run_id"] == RUN_ORQ
    assert d["identidade"]["dag_run_id"] == RUN_ORQ   # o que a F4 vai reexecutar
    assert d["identidade"]["logical_date"] == LOGICAL
    # A etapa, com o que a F3 precisa para desenhar:
    assert d["total_etapas"] == 1 and d["etapas_executadas"] == 1
    et = d["etapas"][0]
    assert et["job_name"] == "http_saude" and et["status"] == "SUCCESS"
    assert et["inicio"] == "2026-08-03 09:49:37" and et["duration_seconds"] == 8
    assert et["depends_on_jobs"] == [] and et["no_desenho"] is True
    # A corrida do pipeline (status da 067), sem segunda consulta:
    assert d["corrida"]["status"] == "SUCESSO"
    assert d["migration_067_pendente"] is False
    assert d["airflow_indisponivel"] is False


def test_endpoint_sem_execucao_no_odate_e_vazio_honesto(client, auth):
    """Vazio ≠ erro: 200, razão explícita e o DESENHO devolvido em estado
    neutro para o canvas da F3 abrir mesmo assim."""
    db = _db_completo(corridas=[], etapas=[],
                      desenho=[_no("etapa_1", ordem=1),
                               _no("etapa_2", ordem=2, deps="etapa_1")])
    r, cli = _chama(client, db,
                    url=f"/pipelines/DEV_F10_A/execucao?data_referencia={_D}")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["vazio"] is True
    assert d["razao"] == "sem_execucao_na_data"
    assert d["identidade"]["resolvido"] is False
    assert d["identidade"]["motivo"] == ident.SEM_LINHA_NA_DATA
    assert d["corrida"] is None
    assert d["etapas_executadas"] == 0
    assert [e["job_name"] for e in d["etapas"]] == ["etapa_1", "etapa_2"]
    assert all(e["status"] is None and e["sem_execucao"] for e in d["etapas"])
    assert d["etapas"][1]["depends_on_jobs"] == ["etapa_1"]
    assert cli.chamadas == []       # nem consultou o Airflow à toa


def test_endpoint_pipeline_inexistente_e_404(client, auth):
    r, _ = _chama(client, _db_completo(), url="/pipelines/NAO_EXISTE/execucao")
    assert r.status_code == 404


def test_endpoint_recusa_os_dois_parametros(client, auth):
    r, _ = _chama(
        client, _db_completo(),
        url=f"/pipelines/DEV_F10_A/execucao?data_referencia={_D}&execution_id={TS}")
    assert r.status_code == 422


def test_endpoint_data_invalida_e_422(client, auth):
    r, _ = _chama(client, _db_completo(),
                  url="/pipelines/DEV_F10_A/execucao?data_referencia=03-08-2026")
    assert r.status_code == 422


def test_endpoint_pelo_execution_id_sentido_inverso(client, auth):
    """O Dashboard tem o ts_nodash, não o ODATE — a MESMA porta responde."""
    db = _db_completo(corridas=[_corrida("scheduled__2026-08-03T06:00:00+00:00")],
                      etapas=[_etapa("http_saude", ts="20260803T060000")])
    r, _ = _chama(client, db,
                  url="/pipelines/DEV_F10_A/execucao?execution_id=20260803T060000")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["identidade"]["ts_nodash"] == "20260803T060000"
    assert d["identidade"]["run_id"] == "scheduled__2026-08-03T06:00:00+00:00"
    assert d["identidade"]["data_referencia"] == "2026-08-03"
    assert d["vazio"] is False and d["etapas_executadas"] == 1


def test_endpoint_pelo_execution_id_com_run_id_do_orquestra(client, auth):
    """O caso REAL do dev: o run_id não traduz pela string, então a 1ª passada
    não casa corrida nenhuma. Só a SEGUNDA passada (com o run_id que o Airflow
    revelou) recupera o ODATE — sem ela a resposta voltava com
    `data_referencia: null`. Defeito pego na prova viva."""
    db = _db_completo()
    r, cli = _chama(client, db,
                    runs=[{"dag_run_id": RUN_ORQ, "logical_date": LOGICAL,
                           "state": "success"}],
                    url=f"/pipelines/DEV_F10_A/execucao?execution_id={TS}")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["identidade"]["run_id"] == RUN_ORQ
    assert d["identidade"]["data_referencia"] == "2026-08-03"   # o que faltava
    assert d["data_referencia"] == "2026-08-03"
    assert d["identidade"]["logical_date"] == LOGICAL           # não se perdeu
    assert ident.ORIGEM_AIRFLOW in d["identidade"]["origem"]
    assert ident.ORIGEM_067 in d["identidade"]["origem"]
    assert d["identidade"]["motivo"] is None
    assert d["corrida"]["status"] == "SUCESSO"
    assert d["etapas_executadas"] == 1


def test_endpoint_pelo_execution_id_sem_corrida_na_067(client, auth):
    """Produção pré-retomada (067 vazia): o drill-down por execution_id tem de
    funcionar assim mesmo — etapas sim, ODATE/corrida não."""
    db = _db_completo(corridas=[])
    r, _ = _chama(client, db,
                  runs=[{"dag_run_id": RUN_ORQ, "logical_date": LOGICAL}],
                  url=f"/pipelines/DEV_F10_A/execucao?execution_id={TS}")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["etapas_executadas"] == 1 and d["vazio"] is False
    assert d["corrida"] is None
    assert d["data_referencia"] is None      # honesto: não dá para saber


def test_endpoint_degrada_sem_a_migration_067(client, auth):
    """Deploy parcial: responde o que a etl_job_execution permitir, declarando."""
    db = _db_completo(com_067=False, corridas=[])
    r, cli = _chama(client, db,
                    url=f"/pipelines/DEV_F10_A/execucao?data_referencia={_D}")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["migration_067_pendente"] is True
    assert d["identidade"]["degradado"] is True
    assert d["identidade"]["ts_nodash"] == TS
    assert d["identidade"]["run_id"] is None      # honesto: não dá para saber
    assert d["vazio"] is False and d["etapas_executadas"] == 1
    assert d["corrida"] is None
    assert cli.chamadas == []                     # degradado não chama Airflow


def test_endpoint_degrada_sem_a_migration_038(client, auth):
    """Sem depends_on_jobs (038) o desenho ainda vem — só sem arestas."""
    db = _db_completo(com_038=False)
    r, _ = _chama(client, db,
                  runs=[{"dag_run_id": RUN_ORQ, "logical_date": LOGICAL}],
                  url=f"/pipelines/DEV_F10_A/execucao?data_referencia={_D}")
    assert r.status_code == 200, r.text
    assert r.json()["etapas"][0]["depends_on_jobs"] == []


def test_endpoint_com_airflow_fora_do_ar_responde_declarando(client, auth):
    db = _db_completo()
    r, _ = _chama(client, db, erro=RuntimeError("connection refused"),
                  url=f"/pipelines/DEV_F10_A/execucao?data_referencia={_D}")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["airflow_indisponivel"] is True
    assert d["identidade"]["resolvido"] is False
    assert d["vazio"] is True
    assert d["razao"] == ident.RUN_ID_NAO_TRADUZIVEL
    # O desenho continua lá — o canvas abre neutro em vez de quebrar.
    assert [e["job_name"] for e in d["etapas"]] == ["http_saude"]


def test_endpoint_com_airflow_devolvendo_erro_http(client, auth):
    db = _db_completo()
    r, _ = _chama(client, db, status=503,
                  url=f"/pipelines/DEV_F10_A/execucao?data_referencia={_D}")
    assert r.status_code == 200
    assert r.json()["airflow_indisponivel"] is True


def test_endpoint_declara_ambiguidade_para_a_tela(client, auth):
    db = _db_completo(corridas=[
        _corrida("scheduled__2026-08-03T06:00:00+00:00",
                 inicio=datetime(2026, 8, 3, 6, 0, 5), disparado_por="agenda"),
        _corrida("scheduled__2026-08-03T18:00:00+00:00",
                 inicio=datetime(2026, 8, 3, 18, 0, 5), disparado_por="manual")],
        etapas=[_etapa("http_saude", ts="20260803T180000")])
    r, _ = _chama(client, db,
                  url=f"/pipelines/DEV_F10_A/execucao?data_referencia={_D}")
    d = r.json()
    assert d["identidade"]["ambiguo"] is True
    assert d["identidade"]["regra"] == ident.REGRA_MAIS_RECENTE
    assert len(d["identidade"]["candidatos"]) == 2
    # candidatos serializados (datas viram texto — nada de datetime cru no JSON)
    assert d["identidade"]["candidatos"][0]["inicio"].startswith("2026-08-03 ")


def test_endpoint_grafia_divergente_devolve_a_oficial(client, auth):
    """Canonização da PR #236: pede em minúsculas, responde na grafia oficial."""
    r, _ = _chama(client, _db_completo(),
                  runs=[{"dag_run_id": RUN_ORQ, "logical_date": LOGICAL}],
                  url=f"/pipelines/dev_f10_a/execucao?data_referencia={_D}")
    assert r.status_code == 200
    assert r.json()["pipeline_name"] == "DEV_F10_A"


# ═══════════════ NÃO-REGRESSÃO: o corpo do clear do rerun ════════════════════

_CLEAR_ESPERADO = {
    "dry_run": False,
    "dag_run_id": "scheduled__2026-08-03T06:00:00+00:00",
    "task_ids": ["etapa_x"],
    "include_downstream": True,
    "include_future": False,
    "include_past": False,
    "include_upstream": False,
    "reset_dag_runs": True,
}


def test_rerun_envia_o_mesmo_corpo_de_sempre(client, auth):
    """BLOQUEANTE: o rerun é caminho de produção. Depois de a ponte virar peça
    única, o dag_run escolhido e o corpo do clearTaskInstances têm de continuar
    IDÊNTICOS — inclusive o casamento por ts_nodash com runs paralelos."""
    cli = _ClientFake(runs=[
        {"dag_run_id": "scheduled__2026-08-03T18:00:00+00:00",
         "logical_date": "2026-08-03T18:00:00+00:00", "state": "running"},
        {"dag_run_id": "scheduled__2026-08-03T06:00:00+00:00",
         "logical_date": "2026-08-03T06:00:00+00:00", "state": "failed"},
    ])
    with patch("routers.execucoes.get_airflow_client", return_value=cli):
        r = client.post("/execucoes/rerun", json={
            "pipeline_name": "DEV_F10_A",
            "execution_id": "20260803T060000",
            "task_id": "etapa_x",
        })
    assert r.status_code == 200, r.text
    posts = [c for c in cli.chamadas if c[0] == "POST"]
    assert len(posts) == 1
    assert posts[0][1] == "/api/v1/dags/DEV_F10_A/clearTaskInstances"
    assert posts[0][2] == _CLEAR_ESPERADO
    # E a listagem de dagRuns continua com os MESMOS parâmetros de antes.
    gets = [c for c in cli.chamadas if c[0] == "GET"]
    assert gets[0][2] == {"limit": 50, "order_by": "-execution_date"}


def test_rerun_com_dag_run_id_explicito_nao_consulta_o_airflow(client, auth):
    cli = _ClientFake(runs=[])
    with patch("routers.execucoes.get_airflow_client", return_value=cli):
        r = client.post("/execucoes/rerun", json={
            "pipeline_name": "DEV_F10_A", "task_id": "etapa_x",
            "dag_run_id": "scheduled__2026-08-03T06:00:00+00:00",
        })
    assert r.status_code == 200, r.text
    assert [c for c in cli.chamadas if c[0] == "GET"] == []
    assert [c for c in cli.chamadas if c[0] == "POST"][0][2] == _CLEAR_ESPERADO


def test_rerun_sem_match_mantem_fallback_legado(client, auth):
    """Sem ts_nodash casando, continua valendo o 1º run terminado da lista —
    comportamento antigo preservado de propósito."""
    cli = _ClientFake(runs=[
        {"dag_run_id": "r_running", "logical_date": "2026-08-03T18:00:00+00:00",
         "state": "running"},
        {"dag_run_id": "r_failed", "logical_date": "2026-08-03T06:00:00+00:00",
         "state": "failed"},
    ])
    with patch("routers.execucoes.get_airflow_client", return_value=cli):
        r = client.post("/execucoes/rerun", json={
            "pipeline_name": "DEV_F10_A", "task_id": "etapa_x",
            "execution_id": "20990101T000000",
        })
    assert r.status_code == 200, r.text
    assert [c for c in cli.chamadas if c[0] == "POST"][0][2]["dag_run_id"] == "r_failed"
