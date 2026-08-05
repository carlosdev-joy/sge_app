"""
F3 — liberação por condição e disparo push (docs/retomada-f3-desenho.md;
suíte docs/retomada-aceitacao.md, itens D01–D08, D12–D17, D19–D23, D55).

O que se guarda aqui, na ordem do desenho:

  §1  taxonomia _origem_disparo + dia operacional: regras de HORA só para
      agenda (D03), regras de DIA para toda origem julgando o dia
      operacional (D04/D05/D06/D07), blackout no relógio de propósito (D08);
  §2  push dentro do _registrar_sucesso, DEPOIS do commit do SUCESSO, com
      try/except por candidato — falha no disparo nunca derruba o pai (D23);
  §4  geração: supplement da 067 com contrato None×{} (D36), recusa ruidosa
      sem migration (D40), schedule=None + consts RESTRICAO_DIA (D37/D38);
  §5  remoção do sensor e do consumo de Dataset MANTENDO o outlet (D01);
  §7  conf com herança dupla data_referencia + dia_operacional (D12).

Lição E (PR #229): as FOLHAS do grafo gerado são byte-idênticas às da F2 —
a F3 não cria task, não muda trigger rule e não pendura nada no publish.
Mesma técnica dos vizinhos: Airflow stubado via sys.modules, geração como
função pura, helpers EXECUTADOS (exec do fonte com utils reais/stubados).
"""
from __future__ import annotations

import ast
import importlib.util
import json
import sys
from contextlib import contextmanager
from datetime import date, datetime
from itertools import zip_longest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

_AIRFLOW_STUBS = [
    "airflow", "airflow.models", "airflow.operators", "airflow.operators.python",
    "airflow.operators.empty", "airflow.datasets", "airflow.utils",
    "airflow.utils.trigger_rule", "airflow.utils.state",
    "airflow.api", "airflow.api.client", "airflow.api.client.local_client",
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
    return _load_module("etl_dag_factory_f3_test", "dags/etl_dag_factory.py")


_DREF_REAL = _load_module("utils_data_referencia_f3_test", "dags/utils/data_referencia.py")
_DEPS_REAL = _load_module("utils_dependencias_f3_test", "dags/utils/dependencias.py")


# F5 (spec-malha-execucao) — a corrida DESLIGADA: o estado de todo banco sem a
# 085 e do dev com o interruptor em 0. Dublê explícito, nunca MagicMock: num
# mock, `_corrida.odate(...)['ambiguo']` devolve um mock — que é VERDADEIRO — e
# o push recusaria TODO dependente por "ODATE ambíguo" sem corrida nenhuma
# existir. (O caminho com a corrida LIGADA é testado em
# tests/test_dag_factory_odate_corrida.py, com o dublê ligado.)
_CORRIDA_DESLIGADA = SimpleNamespace(
    corrida_ativa=lambda *a, **kw: False,
    odate=lambda *a, **kw: {"data": None, "corrida_id": None, "ambiguo": False,
                            "degrau": None, "detalhe": None},
    corrida_aberta_do_pipeline=lambda *a, **kw: {"corridas": [], "odate": None,
                                                 "ambiguo": False},
)


@contextmanager
def _ambiente_utils(dependencias=_DEPS_REAL, malha_corrida=_CORRIDA_DESLIGADA):
    """utils.* stubados; data_referencia sempre REAL; dependencias REAL por
    padrão ou um dublê por teste (o push importa por nome de módulo).

    ``utils.malha_corrida`` entra como ATRIBUTO do pacote stubado, e não só no
    sys.modules: o fonte gerado faz ``from utils import malha_corrida``, que num
    MagicMock puro devolve um filho mock em silêncio."""
    pacote_utils = MagicMock()
    pacote_utils.malha_corrida = malha_corrida
    util_mods = {
        "utils": pacote_utils,
        "utils.datastage_operator": MagicMock(),
        "utils.conditions": MagicMock(),
        "utils.job_operators": MagicMock(),
        "utils.data_referencia": _DREF_REAL,
        "utils.dependencias": dependencias,
        "utils.malha_corrida": malha_corrida,
    }
    saved = {m: sys.modules.get(m) for m in util_mods}
    try:
        sys.modules.update(util_mods)
        yield
    finally:
        for m, prev in saved.items():
            if prev is None:
                sys.modules.pop(m, None)
            else:
                sys.modules[m] = prev


@contextmanager
def _cliente_trigger(falha=None):
    """Dublê do local_client do Airflow: grava cada trigger_dag ou levanta
    `falha` — é assim que se prova a devolução (D16) e o pai verde (D23)."""
    disparos = []

    class Client:  # noqa: D401 — espelho da assinatura real
        def __init__(self, *a, **kw):
            pass

        def trigger_dag(self, dag_id, run_id, conf):
            if falha is not None:
                raise falha
            disparos.append({"dag_id": dag_id, "run_id": run_id, "conf": conf})

    mod = SimpleNamespace(Client=Client)
    anterior = sys.modules.get("airflow.api.client.local_client")
    sys.modules["airflow.api.client.local_client"] = mod
    try:
        yield disparos
    finally:
        sys.modules["airflow.api.client.local_client"] = anterior


# ─────────────────────────── pipeline/jobs/fonte ────────────────────────────

def _pipeline(**overrides):
    base = {
        "pipeline_name": "PIPE_F3", "project_name": "BI_CVP", "domain": "TESTE",
        "tags": "ETL", "scheduled_time": "06:00:00",
        "envia_msg_inicio": 0, "envia_msg_fim": 1, "envia_msg_erro": 1,
        "ambiente": "PROD", "schedule_type": "daily",
    }
    base.update(overrides)
    return base


def _job(name, jtype="datastage", order=1, depends=None, cond=None, aguarde=None):
    j = {"job_name": name, "job_type": jtype, "job_command": "ds.job",
         "execution_order": order}
    if depends is not None:
        j["depends_on_jobs"] = depends
    if cond is not None:
        j["condition_json"] = json.dumps(cond)
    if aguarde is not None:
        j["aguarde_json"] = json.dumps(aguarde)
    return j


def _src(factory, jobs=None, **over):
    return factory._generate_dag_source(
        _pipeline(**over), jobs or [_job("JobA"), _job("JobB", order=2)])


def _exec_ns(src, dependencias=_DEPS_REAL):
    ns = {}
    with _ambiente_utils(dependencias):
        exec(compile(src, "<dag>", "exec"), ns)
    return ns


class _Momento:
    def __init__(self, dt):
        self._dt = dt

    def in_timezone(self, tz):
        return self._dt


def _ctx(run_id="scheduled__2026-08-01T06:00:00+00:00", conf=None,
         momento=datetime(2026, 8, 1, 6, 0)):
    dag_run = SimpleNamespace(conf=conf or {}, run_id=run_id)
    return {
        "run_id": run_id,
        "ts_nodash": "20260801T060000",
        "dag_run": dag_run,
        "data_interval_end": _Momento(momento) if momento is not None else None,
        "logical_date": None,
    }


_RUN_DEP = "dep__2026-08-01__PIPE_PAI__20260801T120000000000"
_RUN_GUARDIA = "guardia__2026-08-01__guardia__20260801T120000000000"


# ─────────────────────────── hook e conn de mentira ─────────────────────────

class _Cursor:
    def __init__(self):
        self.execs = []
        self.calendario = None
        self.rowcount = -1
        self._rows = []

    def execute(self, sql, params=None):
        s = " ".join(str(sql).split())
        self.execs.append((s, params))
        if "etl_calendario" in s:
            self._rows = [(1,)] if self.calendario else []
        else:
            self._rows = []
        self.rowcount = 1 if s.startswith("UPDATE") else -1

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)


class _Hook:
    def __init__(self, tem_067=True, virada=None, blackout=None, calendario=None):
        self.cursor = _Cursor()
        self.cursor.calendario = calendario
        self.tem_067 = tem_067
        self.virada = virada
        self.blackout = blackout
        self.commits = 0
        self.rollbacks = 0
        self.closes = 0

    def get_first(self, sql, parameters=None):
        s = " ".join(str(sql).split())
        if "OBJECT_ID" in s:
            return (1,) if self.tem_067 else (None,)
        if "hora_virada" in s:
            return (self.virada,)
        if "etl_blackout" in s:
            return self.blackout
        return None

    def get_conn(self):
        hook = self

        def _commit():
            hook.commits += 1

        def _rollback():
            hook.rollbacks += 1

        def _close():
            hook.closes += 1

        return SimpleNamespace(cursor=lambda: hook.cursor, commit=_commit,
                               rollback=_rollback, close=_close)

    def run(self, *a, **kw):
        pass


def _instala_hook(ns, hook):
    ns["MsSqlHook"] = lambda **_kw: hook
    return hook


def _dep_fake(**over):
    """Dublê de utils.dependencias para os testes do PUSH: as funções de
    banco são unitárias em test_utils_dependencias.py; aqui se testa a
    ORQUESTRAÇÃO do pusher gerado. montar_conf/novo_run_id/dia_permitido são
    os REAIS (conf e run_id de verdade)."""
    f = SimpleNamespace()
    f.chamadas = []

    def dependentes_de(conn, pai):
        f.chamadas.append(("dependentes_de", pai))
        return list(over.get("dependentes", ["PIPE_C"]))

    def config_dependente(conn, filho):
        f.chamadas.append(("config", filho))
        cfg = over.get("config", {"regras_dia": {}, "nao_iniciar_antes": None})
        return cfg(filho) if callable(cfg) else cfg

    def liberado(conn, filho, data_ref, corrida=None):
        # F6 — a assinatura ganhou a corrida da LINHA avaliada. O dublê tem de
        # aceitá-la: com a assinatura antiga, o fonte gerado cairia na rede de
        # `TypeError` e os testes do push passariam sem NUNCA exercitar a
        # chamada de verdade (teste verde pelo motivo errado).
        f.chamadas.append(("liberado", filho, data_ref, corrida))
        lib = over.get("liberado", (True, []))
        return lib(filho) if callable(lib) else lib

    def reservar_corrida(conn, filho, data_ref, novo_run_id, origem):
        f.chamadas.append(("reservar", filho, data_ref, novo_run_id, origem))
        modo = over.get("reservar", "novo")
        if modo == "novo":
            return novo_run_id
        if modo == "perde":
            return None
        return modo          # run_id de linha adotada

    def ordenar_corrida(conn, filho, data_ref, run_id, origem):
        f.chamadas.append(("ordenar", filho, data_ref, run_id, origem))
        return True

    def devolver_reserva(conn, filho, data_ref, run_id, veio_de_adocao):
        f.chamadas.append(("devolver", filho, data_ref, run_id, veio_de_adocao))

    f.dependentes_de = dependentes_de
    f.config_dependente = config_dependente
    f.liberado = liberado
    f.reservar_corrida = reservar_corrida
    f.ordenar_corrida = ordenar_corrida
    f.devolver_reserva = devolver_reserva
    f.dia_permitido = over.get("dia_permitido", _DEPS_REAL.dia_permitido)
    f.montar_conf = _DEPS_REAL.montar_conf
    f.novo_run_id = _DEPS_REAL.novo_run_id
    f.calendario_bloqueia = _DEPS_REAL.calendario_bloqueia

    # F4 (spec-malha-data-unica): a trava de datas divergentes no push. Por
    # default os predecessores estão na MESMA data (nada diverge) — quem testa
    # a trava injeta `datas_pred`. Os predicados puros são os REAIS: divergir
    # é regra, e regra duplicada no dublê esconderia mudança.
    def datas_dos_predecessores(conn, filho, agora):
        f.chamadas.append(("datas_pred", filho))
        d = over.get("datas_pred", {})
        return d(filho) if callable(d) else dict(d)

    def gravar_evento(conn, pipeline, data_ref, tipo, detalhe, notificar=True):
        f.chamadas.append(("evento", pipeline, data_ref, tipo, detalhe))
        return True

    f.datas_dos_predecessores = datas_dos_predecessores
    f.datas_divergentes = _DEPS_REAL.datas_divergentes
    f.detalhe_divergencia = _DEPS_REAL.detalhe_divergencia
    f.gravar_evento = over.get("gravar_evento", gravar_evento)
    return f


# ─────────────────────── parser das dep_lines geradas ───────────────────────

def _nomes(seg):
    seg = seg.strip()
    if seg.startswith("["):
        return [t.strip() for t in seg[1:seg.index("]")].split(",") if t.strip()]
    return [seg]


def _arestas(src):
    ar = []
    for l in (l.strip() for l in src.splitlines() if ">>" in l):
        partes = l.split(">>")
        for a, b in zip(partes, partes[1:]):
            for x in _nomes(a):
                for y in _nomes(b):
                    ar.append((x, y))
    return ar


def _folhas(src):
    ar = _arestas(src)
    todos = {n for e in ar for n in e}
    return todos - {a for a, _ in ar}


def _bloco_task(src, inicio):
    i = src.index(inicio)
    return src[i:src.index("\n    )", i)]


# ═══════════ 1. Compilação/import das combinações com dependência ═══════════

_COND_BIN = {"tipo": "contagem", "tabela": "dbo.T", "operador": ">", "valor": 1,
             "ramo_verdadeiro": ["JobB"], "ramo_falso": ["JobC"]}


def _cenarios_dep(factory):
    dep = {"_deps_tabela": ["PIPE_PAI"], "depends_on": "PIPE_PAI"}
    return {
        "dep_simples": _src(factory, **dep),
        "dep_multipla": _src(factory, _deps_tabela=["PIPE_A", "PIPE_B"],
                             depends_on="PIPE_A,PIPE_B"),
        "dep_decisao": _src(factory, jobs=[
            _job("JobA"),
            _job("Dec", jtype="decisao", order=2, depends="JobA", cond=_COND_BIN),
            _job("JobB", order=3, depends=""), _job("JobC", order=4, depends=""),
        ], **dep),
        "dep_aguarde": _src(factory, jobs=[
            _job("JobA"), _job("JobB"),
            _job("Enc", jtype="aguarde", order=2, depends="JobA,JobB",
                 aguarde={"politica": "todas_terminarem"}),
            _job("Limpa", jtype="shell", order=3, depends="Enc"),
        ], **dep),
        "dep_monthly": _src(factory, schedule_type="monthly", schedule_dom=5, **dep),
        "dep_weekly_dom0": _src(factory, schedule_type="weekly", schedule_dow=0, **dep),
        "dep_dias_semana": _src(factory, dias_semana="1,3,5", **dep),
        "dep_dias_mes": _src(factory, schedule_type="monthly_days_times",
                             dias_horarios_mes='[{"dia": 1, "horarios": ["09:00"]}]',
                             **dep),
        "dep_horarios": _src(factory, horarios_especificos="09:00,10:30", **dep),
    }


def test_combinacoes_com_dependencia_compilam_e_importam(factory):
    for nome, src in _cenarios_dep(factory).items():
        ast.parse(src)
        _exec_ns(src)
        assert "def _disparar_dependentes(" in src, nome
        assert "def _origem_disparo(" in src, nome
        assert "def _dia_operacional(" in src, nome


def test_sem_067_sem_csv_compila_no_cron(factory):
    """Sem a 067 e sem CSV: geração de sempre — nada muda para quem nunca
    teve dependência."""
    src = _src(factory)          # _deps_tabela ausente = None
    ast.parse(src)
    _exec_ns(src)
    assert 'schedule="0 6 * * *",' in src


# ═══════════════ 2. Folhas intactas (lição E — o motivo do revert) ══════════

def test_folhas_byte_identicas_a_f2(factory):
    """O conjunto de folhas do grafo com dependência é IDÊNTICO ao do mesmo
    pipeline sem dependência: a F3 não cria folha, não muda trigger rule e o
    publish segue sendo quem carrega a falha."""
    cen = _cenarios_dep(factory)
    esperado = {"t_publish_dataset", "t_teams_end", "t_teams_error", "t_reg_falha"}
    for nome in ("dep_simples", "dep_multipla", "dep_monthly", "dep_weekly_dom0"):
        assert _folhas(cen[nome]) == esperado, nome
    sem_dep = _src(factory)
    assert _folhas(cen["dep_simples"]) == _folhas(sem_dep)


def test_nada_downstream_do_publish_dataset(factory):
    for nome, src in _cenarios_dep(factory).items():
        for a, _b in _arestas(src):
            assert a != "t_publish_dataset", nome


def test_trigger_rules_intactas_no_dependente(factory):
    cen = _cenarios_dep(factory)
    src = cen["dep_simples"]
    assert "trigger_rule" not in _bloco_task(src, "t_publish_dataset = PythonOperator(")
    assert "trigger_rule=TriggerRule.ONE_FAILED" in _bloco_task(src, "t_reg_falha = PythonOperator(")
    assert "trigger_rule=TriggerRule.ALL_DONE" in _bloco_task(src, "t_teams_end = PythonOperator(")
    src_dec = cen["dep_decisao"]
    assert ("trigger_rule=TriggerRule.NONE_FAILED_MIN_ONE_SUCCESS"
            in _bloco_task(src_dec, "t_publish_dataset = PythonOperator("))


def test_grafo_identico_so_muda_a_linha_do_gatilho(factory):
    """Prova mais forte que a das folhas: o bloco `with DAG` inteiro (tasks +
    fiação) do dependente é byte-idêntico ao do mesmo pipeline sem
    dependência — a ÚNICA linha diferente é a do gatilho."""
    com_dep = _src(factory, _deps_tabela=["PIPE_PAI"], depends_on="PIPE_PAI")
    sem_dep = _src(factory)
    bloco_a = sem_dep[sem_dep.index("with DAG("):]
    bloco_b = com_dep[com_dep.index("with DAG("):]
    difs = [(la, lb) for la, lb in
            zip_longest(bloco_a.splitlines(), bloco_b.splitlines())
            if la != lb]
    assert len(difs) == 1
    assert difs[0][0].strip().startswith('schedule="0 6 * * *"')
    assert difs[0][1].strip().startswith("schedule=None,")


def test_push_nao_vira_task_nova(factory):
    """O disparo vive DENTRO do callable do publish (§2.1) — nenhuma task
    nova, nenhum operador novo no grafo."""
    src = _src(factory, _deps_tabela=["PIPE_PAI"])
    assert 'task_id="disparar' not in src
    assert src.count("PythonOperator(") == _src(factory).count("PythonOperator(")


# ═══════════════ 3. Geração: schedule, consts e contrato None×{} ════════════

def test_dependente_schedule_none_sem_sensor_nem_dataset(factory):
    """D01: dependência (tabela) → sem gatilho próprio, sem polling, sem
    consumo de Dataset; o outlet fica (ponte para DAG antiga)."""
    for nome, src in _cenarios_dep(factory).items():
        linhas = [l.strip() for l in src.splitlines()
                  if l.strip().startswith("schedule=")]
        assert len(linhas) == 1 and linhas[0].startswith("schedule=None,"), nome
        assert "ExternalTaskSensor" not in src, nome
        assert "schedule=[Dataset(" not in src, nome
        assert "DEPENDS_ON_DAG_ID" not in src, nome
        assert "outlets=[Dataset(DATASET_URI)]" in src, nome


def test_tabela_vazia_com_csv_e_orfao_e_recusa(factory):
    """Contrato {} (D36) REVISTO pela revisão adversarial: remoção legítima de
    dependência via API limpa tabela E CSV na mesma transação — logo "tabela
    vazia + CSV preenchido" só pode ser órfão legado (a carga da 067 descartou
    predecessor fora de etl_pipeline, ex.: DAG externa do sensor antigo).
    Gerar cron puro perderia a dependência EM SILÊNCIO; recusa ruidosa."""
    with pytest.raises(ValueError, match="sem correspondencia"):
        _src(factory, _deps_tabela=[], depends_on="PIPE_PAI")


def test_sem_067_com_csv_recusa_ruidosamente(factory):
    """D40: sem a tabela, pipeline com dependência NÃO é gerado — nem
    schedule=None mudo, nem regressão a cron. O erro cita a migration e o
    arquivo anterior fica preservado (a gravação só ocorre após gerar)."""
    with pytest.raises(ValueError) as exc:
        _src(factory, depends_on="PIPE_PAI")          # _deps_tabela = None
    msg = str(exc.value)
    assert "migration 067" in msg and "PIPE_PAI" in msg
    assert "nao gerada" in msg


def test_contrato_none_x_dict_do_supplement(factory, capsys):
    """_dependencias_da_tabela: None = tabela ausente; {} = vazia (verdade);
    dict com chave CI = dependências; erro de leitura → None com log alto."""
    class _Cur:
        def __init__(self, obj, rows=None, explode=False):
            self._obj = obj
            self._rows = rows or []
            self._explode = explode
            self._ultimo = None

        def execute(self, sql, params=None):
            if self._explode:
                raise RuntimeError("banco fora")
            self._ultimo = [(self._obj,)] if "OBJECT_ID" in sql else self._rows

        def fetchone(self):
            return self._ultimo[0] if self._ultimo else None

        def fetchall(self):
            return list(self._ultimo)

    assert factory._dependencias_da_tabela(_Cur(None)) is None
    assert factory._dependencias_da_tabela(_Cur(1, [])) == {}
    mapa = factory._dependencias_da_tabela(
        _Cur(1, [("Pipe_C", "PIPE_A"), ("PIPE_C", "PIPE_B"), ("PIPE_D", "PIPE_A")]))
    assert mapa == {"PIPE_C": ["PIPE_A", "PIPE_B"], "PIPE_D": ["PIPE_A"]}
    assert factory._dependencias_da_tabela(_Cur(1, explode=True)) is None
    assert "etl_pipeline_dependencia falhou" in capsys.readouterr().out
    # e o supplement está de fato ligado na geração (chave que o gerador lê)
    fonte = (_ROOT / "dags/etl_dag_factory.py").read_text(encoding="utf-8")
    assert fonte.count('"_deps_tabela"') >= 1 and '_deps_tabela' in fonte


def test_restricao_dia_como_const_antes_dos_helpers(factory):
    """D37/D05: a restrição vira constante gerada (dow=0 preservado como 0) e
    sai ANTES dos helpers — helper em const seria NameError no import."""
    src = _src(factory, schedule_type="weekly", schedule_dow=0,
               _deps_tabela=["PIPE_PAI"])
    assert "'schedule_dow': 0" in src
    assert src.index("RESTRICAO_DIA = ") < src.index("def _now_str")
    # daily com dependência: const presente e explicitamente sem restrição
    src2 = _src(factory, _deps_tabela=["PIPE_PAI"])
    assert "RESTRICAO_DIA = None" in src2
    # sem dependência: a const nem existe (fonte byte-idêntico à F2)
    assert "RESTRICAO_DIA" not in _src(factory)


def test_default_args_sem_helpers_no_dependente(factory):
    """D56 continua valendo com os helpers novos da F3."""
    src = _src(factory, _deps_tabela=["PIPE_PAI"])
    bloco = src[src.index("default_args"):]
    bloco = bloco[:bloco.index("}")]
    for proibido in ("_disparar_dependentes", "_origem_disparo", "_dia_operacional",
                     "_registrar", "_check_agenda", "on_failure_callback"):
        assert proibido not in bloco


# ═══════════ 4. Taxonomia e agenda: hora só em cron, dia sempre ═════════════

def test_origem_disparo_taxonomia_explicita(factory):
    ns = _exec_ns(_src(factory, _deps_tabela=["PIPE_PAI"]))
    origem = ns["_origem_disparo"]
    assert origem(_ctx(run_id="scheduled__2026-08-01T06:00:00+00:00")) == "agenda"
    assert origem(_ctx(run_id=_RUN_DEP)) == "dep"
    assert origem(_ctx(run_id=_RUN_GUARDIA)) == "guardia"
    assert origem(_ctx(run_id="manual__2026-08-01T09:00:00")) == "manual"
    assert origem(_ctx(run_id="dataset_triggered__2026-08-01T09:00:00+00:00")) == "dataset"
    # desconhecida degrada para manual: nunca julga hora, sempre julga dia
    assert origem(_ctx(run_id="api__qualquer_coisa")) == "manual"


def test_d03_horarios_especificos_nao_pulam_evento(factory):
    """D03 — o assassino nº 1 da 1ª execução: dep__/guardia__ não começam
    com 'manual' e caíam na regra de horário → PULADO em 100% dos disparos."""
    src = _src(factory, horarios_especificos="09:00,10:30",
               _deps_tabela=["PIPE_PAI"])
    ns = _exec_ns(src)
    _instala_hook(ns, _Hook())
    with _ambiente_utils():
        # 11:00 não está na lista: evento passa, agenda pula, manual passa
        assert ns["_check_agenda_regras"](
            _ctx(run_id=_RUN_DEP, momento=datetime(2026, 8, 1, 11, 0)))[0] is True
        assert ns["_check_agenda_regras"](
            _ctx(run_id=_RUN_GUARDIA, momento=datetime(2026, 8, 1, 11, 0)))[0] is True
        assert ns["_check_agenda_regras"](
            _ctx(run_id="manual__x", momento=datetime(2026, 8, 1, 11, 0)))[0] is True
        ok, motivo = ns["_check_agenda_regras"](
            _ctx(momento=datetime(2026, 8, 1, 11, 0)))
    assert ok is False and motivo == "horario 11:00 fora dos horarios configurados"


def test_d04_dia_do_mes_sobrevive_ao_evento(factory):
    """D04 — monthly_days_times: a HORA não se aplica a evento, mas o DIA
    sim (senão o fechamento do dia 1 rodaria em qualquer push)."""
    src = _src(factory, schedule_type="monthly_days_times",
               dias_horarios_mes='[{"dia": 1, "horarios": ["09:00"]}]',
               _deps_tabela=["PIPE_PAI"])
    ns = _exec_ns(src)
    _instala_hook(ns, _Hook())
    with _ambiente_utils():
        # dia certo (1), hora "errada" (11:00): evento RODA
        ok, _ = ns["_check_agenda_regras"](
            _ctx(run_id=_RUN_DEP, conf={"dia_operacional": "2026-08-01"},
                 momento=datetime(2026, 8, 1, 11, 0)))
        assert ok is True
        # dia errado (2): evento PULA pela restrição de dia
        ok, motivo = ns["_check_agenda_regras"](
            _ctx(run_id=_RUN_DEP, conf={"dia_operacional": "2026-08-02"},
                 momento=datetime(2026, 8, 2, 11, 0)))
        assert ok is False and motivo == "dia 2 fora dos dias do mes configurados"
        # agenda no dia errado mantém o motivo antigo de dia+hora (D58)
        ok, motivo = ns["_check_agenda_regras"](
            _ctx(momento=datetime(2026, 8, 2, 9, 0)))
        assert ok is False and "fora da configuracao de dia e hora do mes" in motivo


def test_d04_d05_restricao_nos_cinco_tipos(factory):
    """weekly (dow=0=domingo!), monthly, biweekly, dias_semana e
    monthly_days_times — todos julgam o dia operacional sob evento."""
    casos = [
        (dict(schedule_type="weekly", schedule_dow=0),
         "2026-08-02", "2026-08-03"),                      # domingo ok, segunda não
        (dict(schedule_type="monthly", schedule_dom=5),
         "2026-08-05", "2026-08-06"),
        (dict(schedule_type="biweekly", schedule_dom=3),
         "2026-08-18", "2026-08-04"),
        (dict(dias_semana="1,3,5"),
         "2026-08-05", "2026-08-01"),                      # quarta ok, sábado não
        (dict(schedule_type="monthly_days_times",
              dias_horarios_mes='[{"dia": 1, "horarios": ["09:00"]}]'),
         "2026-08-01", "2026-08-02"),
    ]
    for over, dia_ok, dia_nok in casos:
        ns = _exec_ns(_src(factory, _deps_tabela=["PIPE_PAI"], **over))
        _instala_hook(ns, _Hook())
        with _ambiente_utils():
            ok, _ = ns["_check_agenda_regras"](
                _ctx(run_id=_RUN_DEP, conf={"dia_operacional": dia_ok}))
            assert ok is True, (over, dia_ok)
            ok, motivo = ns["_check_agenda_regras"](
                _ctx(run_id=_RUN_DEP, conf={"dia_operacional": dia_nok}))
            assert ok is False and motivo, (over, dia_nok)


def test_d06_dias_uteis_julga_o_dia_operacional_herdado(factory):
    """D06: pai sexta 23:30 → filho sábado 00:10 na MESMA corrida LIBERA —
    o filho julga o dia operacional herdado (sexta), não o relógio
    (pendulum.now congelado no sábado prova a independência)."""
    ns = _exec_ns(_src(factory, somente_dias_uteis=1, _deps_tabela=["PIPE_PAI"]))
    _instala_hook(ns, _Hook())
    ns["pendulum"] = SimpleNamespace(now=lambda tz: datetime(2026, 8, 1, 0, 10))
    with _ambiente_utils():
        ok, _ = ns["_check_agenda_regras"](
            _ctx(run_id=_RUN_DEP,
                 conf={"data_referencia": "2026-07-31", "dia_operacional": "2026-07-31"},
                 momento=datetime(2026, 8, 1, 0, 10)))
        assert ok is True                       # sexta herdada → roda
        # sem herança, o momento lógico É sábado → PULADO honesto
        ok, motivo = ns["_check_agenda_regras"](
            _ctx(run_id=_RUN_DEP, momento=datetime(2026, 8, 1, 0, 10)))
        assert ok is False and motivo == "fim de semana e pipeline somente dias uteis"


def test_d07_virada_20h_nao_pula_a_propria_corrida(factory):
    """D07/N4: virada 20:00, disparo sexta 23:30 carimba SÁBADO como
    data_referencia — e a regra de dia útil NÃO pode pular (julga o dia
    operacional = sexta, o dia em que a malha RODA)."""
    ns = _exec_ns(_src(factory, somente_dias_uteis=1))
    hook = _instala_hook(ns, _Hook(virada="20:00"))
    ctx = _ctx(momento=datetime(2026, 7, 31, 23, 30))     # sexta 23:30
    with _ambiente_utils():
        assert ns["_data_referencia"](ctx) == date(2026, 8, 1)   # rótulo: sábado
        ok, _ = ns["_check_agenda_regras"](ctx)
        assert ok is True                                        # dia julgado: sexta


def test_d08_blackout_continua_no_relogio(factory):
    """Blackout mede o AGORA de propósito (freeze operacional), em qualquer
    origem — a consulta gerada segue com GETDATE()."""
    src = _src(factory, _deps_tabela=["PIPE_PAI"])
    assert "GETDATE() BETWEEN inicio AND fim" in src
    ns = _exec_ns(src)
    _instala_hook(ns, _Hook(blackout=("Freeze",)))
    with _ambiente_utils():
        ok, motivo = ns["_check_agenda_regras"](_ctx(run_id=_RUN_DEP))
    assert ok is False and motivo == "blackout vigente: Freeze"


def test_calendario_parametrizado_pelo_dia_operacional(factory):
    """O calendário deixa de olhar CAST(GETDATE()): consulta parametrizada
    com o dia operacional (aqui, herdado do conf)."""
    src = _src(factory, calendario_nome="FERIADOS", _deps_tabela=["PIPE_PAI"])
    assert "CAST(GETDATE()" not in src
    ns = _exec_ns(src)
    hook = _instala_hook(ns, _Hook(calendario=("Natal",)))
    with _ambiente_utils():
        ok, motivo = ns["_check_agenda_regras"](
            _ctx(run_id=_RUN_DEP, conf={"dia_operacional": "2026-07-31"}))
    assert ok is False and motivo == "data bloqueada no calendario FERIADOS"
    sql, params = hook.cursor.execs[-1]
    assert "etl_calendario" in sql and "GETDATE" not in sql
    assert params == ("FERIADOS", date(2026, 7, 31))


# ═════════════════ 5. _dia_operacional: cadeia de precedência ═══════════════

def test_dia_operacional_conf_valido_prevalece(factory):
    ns = _exec_ns(_src(factory, _deps_tabela=["PIPE_PAI"]))
    with _ambiente_utils():
        d = ns["_dia_operacional"](_ctx(conf={"dia_operacional": "2026-07-30",
                                              "data_referencia": "2026-07-31"}))
    assert d == date(2026, 7, 30)


def test_dia_operacional_aproxima_pela_data_referencia(factory, capsys):
    """Trigger manual que só passou a data: aproximação com log — melhor um
    dia aproximado e visível que um relógio silencioso."""
    ns = _exec_ns(_src(factory, _deps_tabela=["PIPE_PAI"]))
    with _ambiente_utils():
        d = ns["_dia_operacional"](_ctx(conf={"data_referencia": "2026-07-31"}))
    assert d == date(2026, 7, 31)
    assert "aproximando pela data_referencia" in capsys.readouterr().out


def test_dia_operacional_invalido_recalcula_sem_abortar(factory, capsys):
    ns = _exec_ns(_src(factory, _deps_tabela=["PIPE_PAI"]))
    with _ambiente_utils():
        d = ns["_dia_operacional"](_ctx(conf={"dia_operacional": "banana"},
                                        momento=datetime(2026, 8, 1, 6, 0)))
    assert d == date(2026, 8, 1)
    assert "herdado invalido" in capsys.readouterr().out


def test_dia_operacional_momento_logico_nunca_relogio(factory):
    ns = _exec_ns(_src(factory, _deps_tabela=["PIPE_PAI"]))
    ns["pendulum"] = SimpleNamespace(now=lambda tz: datetime(2026, 8, 2, 3, 0))
    with _ambiente_utils():
        assert ns["_dia_operacional"](
            _ctx(momento=datetime(2026, 8, 1, 23, 30))) == date(2026, 8, 1)
        # só sem momento nenhum no contexto cai no relógio
        assert ns["_dia_operacional"](_ctx(momento=None)) == date(2026, 8, 2)


# ═══════════════ 8. O push: ordem, blindagem e herança (D23/D12) ════════════

def test_push_depois_do_commit_do_sucesso_ordem_no_fonte(factory):
    """§2.1: gravar SUCESSO (commit próprio) e SÓ ENTÃO avaliar — no mesmo
    callable, commit → avaliar é sequência, não corrida."""
    src = _src(factory, _deps_tabela=["PIPE_PAI"])
    corpo = src[src.index("def _registrar_sucesso"):src.index("def _disparar_dependentes")]
    assert corpo.index("_registrar_execucao('SUCESSO', context)") \
        < corpo.index("_disparar_dependentes(context)")


def test_push_dispara_com_conf_de_heranca_dupla(factory):
    """O conf leva as TRÊS chaves (§7): data_referencia + dia_operacional +
    disparado_por — e o run_id do trigger é o MESMO da reserva."""
    ns = _exec_ns(_src(factory))
    _instala_hook(ns, _Hook())
    fake = _dep_fake(dependentes=["PIPE_C"])
    with _ambiente_utils(fake), _cliente_trigger() as disparos:
        ns["_disparar_dependentes"](_ctx())
    assert len(disparos) == 1
    d = disparos[0]
    assert d["dag_id"] == "PIPE_C"
    assert d["conf"] == {"data_referencia": "2026-08-01",
                         "dia_operacional": "2026-08-01",
                         "disparado_por": "PIPE_F3"}
    reserva = [c for c in fake.chamadas if c[0] == "reservar"][0]
    assert d["run_id"] == reserva[3]           # mesmo run_id da reserva


def test_push_cascata_repassa_o_conf_da_raiz(factory):
    """D12: no push do MEIO da cadeia, data_referencia e dia_operacional vêm
    do PRÓPRIO run (herdados da raiz) — sem recálculo, mesmo divergentes."""
    ns = _exec_ns(_src(factory))
    _instala_hook(ns, _Hook())
    fake = _dep_fake(dependentes=["PIPE_NETO"])
    ctx = _ctx(run_id=_RUN_DEP,
               conf={"data_referencia": "2026-07-31", "dia_operacional": "2026-07-30",
                     "disparado_por": "PIPE_AVO"})
    with _ambiente_utils(fake), _cliente_trigger() as disparos:
        ns["_disparar_dependentes"](ctx)
    assert disparos[0]["conf"]["data_referencia"] == "2026-07-31"
    assert disparos[0]["conf"]["dia_operacional"] == "2026-07-30"
    assert disparos[0]["conf"]["disparado_por"] == "PIPE_F3"   # o pai imediato


def test_push_run_id_dep_cabe_no_varchar_250(factory):
    """Run_id real (utils.dependencias.novo_run_id): prefixo dep__, nome do
    pai truncado em 60 (nunca 50) e comprimento ≤ 250 (migration 072)."""
    nome_gigante = "P" * 70
    ns = _exec_ns(_src(factory, pipeline_name=nome_gigante))
    _instala_hook(ns, _Hook())
    fake = _dep_fake()
    with _ambiente_utils(fake), _cliente_trigger() as disparos:
        ns["_disparar_dependentes"](_ctx())
    rid = disparos[0]["run_id"]
    assert rid.startswith("dep__2026-08-01__" + "P" * 60 + "__")
    assert len(rid) <= 250
    assert "[:50]" not in _src(factory, _deps_tabela=["PIPE_PAI"])


def test_d23_excecao_de_um_candidato_nao_cancela_os_demais(factory, capsys):
    """try/except POR item: o 1º explode, o 2º dispara — e o pai não vê
    exceção nenhuma."""
    ns = _exec_ns(_src(factory))
    hook = _instala_hook(ns, _Hook())

    def _cfg(filho):
        if filho == "PIPE_C1":
            raise RuntimeError("cadastro podre")
        return {"regras_dia": {}, "nao_iniciar_antes": None}

    fake = _dep_fake(dependentes=["PIPE_C1", "PIPE_C2"], config=_cfg)
    with _ambiente_utils(fake), _cliente_trigger() as disparos:
        ns["_disparar_dependentes"](_ctx())    # não levanta
    assert [d["dag_id"] for d in disparos] == ["PIPE_C2"]
    assert hook.rollbacks >= 1
    saida = capsys.readouterr().out
    assert "[DEP] avaliacao de PIPE_C1 falhou" in saida


def test_d23_d16_trigger_que_levanta_devolve_e_o_pai_segue(factory, capsys):
    """Disparo que LEVANTA (DAG removida, banco do Airflow fora): devolução
    da reserva (caminho b → DELETE) e pai verde — nunca exceção."""
    ns = _exec_ns(_src(factory))
    _instala_hook(ns, _Hook())
    fake = _dep_fake()
    with _ambiente_utils(fake), _cliente_trigger(falha=RuntimeError("DagNotFound")):
        ns["_disparar_dependentes"](_ctx())    # não levanta
    devolucoes = [c for c in fake.chamadas if c[0] == "devolver"]
    assert len(devolucoes) == 1
    assert devolucoes[0][4] is False           # veio_de_adocao: reserva nova
    assert "[DEP] disparo de PIPE_C falhou" in capsys.readouterr().out


def test_devolucao_de_linha_adotada_volta_a_aguardando(factory):
    """Claim que ADOTOU linha ordenada + trigger falhando → devolução com
    veio_de_adocao=True e o run_id DA LINHA (não o novo)."""
    ns = _exec_ns(_src(factory))
    _instala_hook(ns, _Hook())
    fake = _dep_fake(reservar="guardia__2026-08-01__X__1")
    with _ambiente_utils(fake), _cliente_trigger(falha=RuntimeError("boom")):
        ns["_disparar_dependentes"](_ctx())
    devolucoes = [c for c in fake.chamadas if c[0] == "devolver"]
    assert devolucoes == [("devolver", "PIPE_C", date(2026, 8, 1),
                           "guardia__2026-08-01__X__1", True)]


def test_push_sem_067_loga_e_retorna(factory, capsys):
    ns = _exec_ns(_src(factory))
    _instala_hook(ns, _Hook(tem_067=False))
    fake = _dep_fake()
    with _ambiente_utils(fake), _cliente_trigger() as disparos:
        ns["_disparar_dependentes"](_ctx())
    assert disparos == [] and fake.chamadas == []
    assert "[DEP] migration 067 ausente" in capsys.readouterr().out


def test_push_claim_perdido_nao_dispara(factory, capsys):
    """§3.2: corrida já existe na data (2º SUCESSO do dia, FALHA a re-rodar
    via Clear...) → sem novo disparo, com log."""
    ns = _exec_ns(_src(factory))
    _instala_hook(ns, _Hook())
    fake = _dep_fake(reservar="perde")
    with _ambiente_utils(fake), _cliente_trigger() as disparos:
        ns["_disparar_dependentes"](_ctx())
    assert disparos == []
    assert "ja tem corrida" in capsys.readouterr().out


def test_push_aguardando_loga_faltantes_sem_claim(factory, capsys):
    """D19 (metade unitária): condição incompleta → nada de claim/disparo;
    quem completar por último dispara."""
    ns = _exec_ns(_src(factory))
    _instala_hook(ns, _Hook())
    fake = _dep_fake(liberado=(False, ["PIPE_B"]))
    with _ambiente_utils(fake), _cliente_trigger() as disparos:
        ns["_disparar_dependentes"](_ctx())
    assert disparos == []
    assert not [c for c in fake.chamadas if c[0] in ("reservar", "ordenar")]
    assert "[DEP] PIPE_C aguardando: PIPE_B" in capsys.readouterr().out


def test_push_pre_filtro_de_dia_sem_condicao_nem_claim(factory, capsys):
    """§2.2: dia não permitido no pré-filtro → nem EXISTS, nem claim — e o
    filho re-julgaria de qualquer forma (defesa em profundidade)."""
    ns = _exec_ns(_src(factory))
    _instala_hook(ns, _Hook())
    fake = _dep_fake(config={"regras_dia": {"schedule_type": "monthly",
                                            "schedule_dom": 5},
                             "nao_iniciar_antes": None})
    with _ambiente_utils(fake), _cliente_trigger() as disparos:
        ns["_disparar_dependentes"](_ctx())    # dia operacional = 2026-08-01
    assert disparos == []
    assert not [c for c in fake.chamadas if c[0] in ("liberado", "reservar")]
    assert "fora do dia" in capsys.readouterr().out


def test_d22_janela_ordena_sem_disparar(factory, capsys):
    """§3.4: liberado ANTES de nao_iniciar_antes → ordena AGUARDANDO (linha
    nasce com run_id) e NÃO dispara; depois da janela, claim + disparo."""
    from datetime import time as _time
    ns = _exec_ns(_src(factory))
    _instala_hook(ns, _Hook())
    fake = _dep_fake(config={"regras_dia": {},
                             "nao_iniciar_antes": _time(8, 0)})
    ns["pendulum"] = SimpleNamespace(now=lambda tz: datetime(2026, 8, 1, 7, 10))
    with _ambiente_utils(fake), _cliente_trigger() as disparos:
        ns["_disparar_dependentes"](_ctx())
    assert disparos == []
    ordens = [c for c in fake.chamadas if c[0] == "ordenar"]
    assert len(ordens) == 1 and ordens[0][3].startswith("dep__2026-08-01__")
    assert "antes da janela" in capsys.readouterr().out
    # depois da janela (08:05): dispara normalmente
    fake2 = _dep_fake(config={"regras_dia": {},
                              "nao_iniciar_antes": _time(8, 0)})
    ns["pendulum"] = SimpleNamespace(now=lambda tz: datetime(2026, 8, 1, 8, 5))
    with _ambiente_utils(fake2), _cliente_trigger() as disparos2:
        ns["_disparar_dependentes"](_ctx())
    assert len(disparos2) == 1
    assert not [c for c in fake2.chamadas if c[0] == "ordenar"]


def test_push_indisponivel_por_inteiro_nunca_levanta(factory, capsys):
    """Blindagem externa: até o hook explodindo em TUDO, o publish do pai
    não vê exceção — só o log [DEP]."""
    ns = _exec_ns(_src(factory))

    class _HookExplode:
        def get_first(self, *a, **kw):
            raise RuntimeError("banco fora")

        def get_conn(self):
            raise RuntimeError("banco fora")

    ns["MsSqlHook"] = lambda **_kw: _HookExplode()
    with _ambiente_utils(_dep_fake()):
        ns["_disparar_dependentes"](_ctx())    # não levanta
    assert "[DEP] disparo de dependentes indisponivel" in capsys.readouterr().out


def test_registrar_sucesso_chama_o_push_e_nunca_levanta(factory):
    """O caminho completo do publish: grava SUCESSO e dispara — com o
    Airflow client explodindo, a task do pai continua verde."""
    ns = _exec_ns(_src(factory))
    _instala_hook(ns, _Hook())
    fake = _dep_fake()
    with _ambiente_utils(fake), _cliente_trigger(falha=RuntimeError("x")):
        ns["_registrar_sucesso"](**_ctx())     # não levanta
    assert [c[0] for c in fake.chamadas if c[0] == "dependentes_de"] == ["dependentes_de"]


# ═══════════════ 9. Ausências guardadas (D15, princípio 7) ══════════════════

def test_nenhuma_ordenacao_por_criado_em_no_gerado(factory):
    """D15: nenhum ORDER BY do fonte gerado toca criado_em."""
    for nome, src in _cenarios_dep(factory).items():
        for linha in src.splitlines():
            if "ORDER BY" in linha:
                assert "criado_em" not in linha, (nome, linha)


def test_comentarios_gerados_sem_identificadores_proibidos(factory):
    """Princípio 7 (3× reincidente): comentário no código GERADO não cita
    identificador de trigger_rule/schedule/sensor — quebra assert de
    substring dos testes de não-regressão."""
    proibidos = ("TriggerRule", "trigger_rule", "ExternalTaskSensor", "schedule=")
    cen = dict(_cenarios_dep(factory))
    cen["sem_dep"] = _src(factory)
    for nome, src in cen.items():
        for linha in src.splitlines():
            if "#" not in linha:
                continue
            comentario = linha.split("#", 1)[1]
            for token in proibidos:
                assert token not in comentario, (nome, linha)


# ═══ 12. correções da revisão adversarial da F3 ═════════════════════════════

def test_dia_operacional_manual_e_hoje_nao_o_tick_do_cron(factory):
    """REGRESSÃO pega pela revisão: run MANUAL em DAG com cron recebe como
    data_interval_end o ÚLTIMO TICK (domingo num daily disparado segunda
    05:50) — julgar dias úteis contra ele pularia um manual legítimo. O dia
    de um manual sem conf é HOJE (o dia em que o operador ordenou)."""
    ns = _exec_ns(_src(factory, _deps_tabela=["PIPE_PAI"]))
    with _ambiente_utils():
        # pendulum.now congelado numa quarta; tick do contexto é o domingo
        ns["pendulum"] = SimpleNamespace(
            now=lambda tz: SimpleNamespace(date=lambda: date(2026, 8, 5)))
        d = ns["_dia_operacional"](_ctx(
            run_id="manual_orq_teste_123",
            momento=datetime(2026, 8, 2, 6, 0)))   # domingo = último tick
    assert d == date(2026, 8, 5), "manual julga HOJE, nunca o tick do cron"


def test_dia_operacional_agenda_continua_no_momento_logico(factory):
    """Não-regressão: run agendado segue julgando o momento lógico (tick),
    imune a atraso de fila — princípio D10 preservado."""
    ns = _exec_ns(_src(factory, _deps_tabela=["PIPE_PAI"]))
    with _ambiente_utils():
        ns["pendulum"] = SimpleNamespace(
            now=lambda tz: SimpleNamespace(date=lambda: date(2026, 8, 5)))
        d = ns["_dia_operacional"](_ctx(
            run_id="scheduled__2026-08-03T06:00:00+00:00",
            momento=datetime(2026, 8, 3, 6, 0)))
    assert d == date(2026, 8, 3)


def test_csv_orfao_sem_linha_na_067_recusa_ruidosamente(factory):
    """CSV depends_on legado sem correspondência na tabela: gerar cron puro
    perderia a dependência EM SILÊNCIO no force_all (o sensor morreu). Recusa
    com erro de 1ª classe; operador decide."""
    with pytest.raises(ValueError) as exc:
        _src(factory, _deps_tabela=[], depends_on="DAG_EXTERNA_X")
    msg = str(exc.value)
    assert "sem correspondencia" in msg and "DAG_EXTERNA_X" in msg


def test_csv_espelho_com_linha_na_067_gera_normalmente(factory):
    """O caso são (CSV espelho + tabela preenchida) segue gerando."""
    src = _src(factory, _deps_tabela=["PIPE_PAI"], depends_on="PIPE_PAI")
    assert "schedule=None" in src


def test_sem_csv_e_tabela_vazia_gera_cron_normal(factory):
    src = _src(factory, _deps_tabela=[])
    assert "schedule=" in src and "schedule=None" not in src


# ── F4 (spec-malha-data-unica): a trava de datas divergentes no PUSH ────────
# A guardiã já recusava ordenar com viradas divergentes (Decisão 5), mas quem
# dispara na cascata é o push — e ele liberava assim mesmo. Foi por aí que a
# malha Carga_Vida juntou, na mesma corrida, dados do dia 3 e do dia 4.

def test_push_recusa_com_predecessores_em_datas_diferentes(factory, capsys):
    ns = _exec_ns(_src(factory))
    _instala_hook(ns, _Hook())
    fake = _dep_fake(datas_pred={"PIPE_A": date(2026, 8, 3),
                                 "PIPE_B": date(2026, 8, 4)})
    with _ambiente_utils(fake), _cliente_trigger() as disparos:
        ns["_disparar_dependentes"](_ctx())
    assert disparos == [], "nada pode ser disparado sob divergência"
    # nem chega a perguntar pela liberação: a condição não fecha numa data só
    assert not any(c[0] == "liberado" for c in fake.chamadas)
    # e o operador fica sabendo, com o MESMO texto da guardiã
    evento = next(c for c in fake.chamadas if c[0] == "evento")
    assert evento[3] == "DATA_DIVERGENTE"
    assert "PIPE_A->2026-08-03" in evento[4] and "PIPE_B->2026-08-04" in evento[4]
    assert "NAO disparado" in capsys.readouterr().out


def test_push_segue_normal_com_datas_iguais(factory):
    """O caso são: uma data só entre os predecessores — nada muda."""
    ns = _exec_ns(_src(factory))
    _instala_hook(ns, _Hook())
    fake = _dep_fake(datas_pred={"PIPE_A": date(2026, 8, 4),
                                 "PIPE_B": date(2026, 8, 4)})
    with _ambiente_utils(fake), _cliente_trigger() as disparos:
        ns["_disparar_dependentes"](_ctx())
    assert len(disparos) == 1
    assert not any(c[0] == "evento" for c in fake.chamadas)


def test_push_sem_predecessores_nao_inventa_divergencia(factory):
    ns = _exec_ns(_src(factory))
    _instala_hook(ns, _Hook())
    fake = _dep_fake(datas_pred={})
    with _ambiente_utils(fake), _cliente_trigger() as disparos:
        ns["_disparar_dependentes"](_ctx())
    assert len(disparos) == 1


def test_push_falha_ao_ler_viradas_nao_trava_a_cascata(factory, capsys):
    """Erro de consulta aqui NÃO pode virar 'não dispara': isso pararia a
    malha inteira por um problema transitório de banco. Segue e loga — o
    oposto do liberado(), onde erro é não-liberado de propósito (D21)."""
    def _explode(filho):
        raise RuntimeError("timeout na consulta de viradas")
    ns = _exec_ns(_src(factory))
    _instala_hook(ns, _Hook())
    fake = _dep_fake(datas_pred=_explode)
    with _ambiente_utils(fake), _cliente_trigger() as disparos:
        ns["_disparar_dependentes"](_ctx())
    assert len(disparos) == 1
    assert "viradas de" in capsys.readouterr().out


def test_push_evento_que_falha_nao_derruba_o_laco(factory, capsys):
    def _evento_ruim(conn, pipeline, data_ref, tipo, detalhe, notificar=True):
        raise RuntimeError("evento indisponível")
    ns = _exec_ns(_src(factory))
    _instala_hook(ns, _Hook())
    fake = _dep_fake(datas_pred={"PIPE_A": date(2026, 8, 3),
                                 "PIPE_B": date(2026, 8, 4)},
                     gravar_evento=_evento_ruim)
    with _ambiente_utils(fake), _cliente_trigger() as disparos:
        ns["_disparar_dependentes"](_ctx())
    assert disparos == []
    assert "nao gravado" in capsys.readouterr().out
