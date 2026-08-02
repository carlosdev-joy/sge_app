"""
F2 — registro de execução por data de referência (docs/retomada-f2-desenho.md).

Cada corrida de pipeline grava UMA linha em dbo.etl_pipeline_execucao com a
chave completa (pipeline, data_referencia, execution_id=run_id): EXECUTANDO ou
PULADO nascem no wrapper do check_agenda, FALHA na task registrar_falha
(fiação espelho do teams_error), SUCESSO no próprio publish_dataset — que
mantém task_id, trigger rule e outlets. Os testes guardam os defeitos da
reversão (PR #229) que a F2 fecha:

  • B1  — duas linhas por corrida (chave ts_nodash × NULL que nunca casavam);
  • N1  — DagRun VERDE em pipeline que falhou (folha com regra tolerante);
  • N7  — PULADO "mais recente" mascarando SUCESSO (COALESCE em criado_em);
  • D56 — helper em default_args = NameError no import (consts saem antes);
  • D58 — os 5 caminhos de saída do check_agenda gravam PULADO com motivo;
  • D59 — o registro NUNCA derruba a carga (degradação sem a migration 067).

Mesmo princípio dos demais testes de factory: módulos do Airflow stubados via
sys.modules antes do import; _generate_dag_source é função pura. Os helpers
gerados são EXECUTADOS (exec do fonte com utils stubados e o módulo REAL de
utils/data_referencia), não caçados por substring.
"""
from __future__ import annotations

import ast
import importlib.util
import json
import sys
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

_AIRFLOW_STUBS = [
    "airflow", "airflow.models", "airflow.operators", "airflow.operators.python",
    "airflow.operators.empty", "airflow.datasets", "airflow.utils",
    "airflow.utils.trigger_rule", "airflow.utils.state",
    "airflow.sensors", "airflow.sensors.external_task",
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
    return _load_module("etl_dag_factory_execucao_test", "dags/etl_dag_factory.py")


# Módulo REAL do cálculo do ODATE: o helper gerado _data_referencia o importa
# lazy (em tempo de CHAMADA), então ele entra no sys.modules só durante o exec
# e as chamadas, via _ambiente_utils.
_DREF_REAL = _load_module("utils_data_referencia_f2_test", "dags/utils/data_referencia.py")
# Módulo REAL das dependências (F3): o check_agenda gerado julga calendário e
# restrição de dia por ele, e o publish avalia dependentes por ele.
_DEPS_REAL = _load_module("utils_dependencias_f2_test", "dags/utils/dependencias.py")


@contextmanager
def _ambiente_utils():
    """Stuba ``utils.*`` (e aponta utils.data_referencia/utils.dependencias
    para os módulos REAIS) apenas durante o exec/chamada — mesmo padrão do
    _exec_source vizinho."""
    util_mods = {
        "utils": MagicMock(),
        "utils.datastage_operator": MagicMock(),
        "utils.conditions": MagicMock(),
        "utils.job_operators": MagicMock(),
        "utils.data_referencia": _DREF_REAL,
        "utils.dependencias": _DEPS_REAL,
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


def _pipeline(**overrides):
    base = {
        "pipeline_name": "PIPE_EXEC", "project_name": "BI_CVP", "domain": "TESTE",
        "tags": "ETL", "scheduled_time": "06:00:00",
        "envia_msg_inicio": 0, "envia_msg_fim": 1, "envia_msg_erro": 1,
        "ambiente": "PROD", "schedule_type": "daily",
    }
    base.update(overrides)
    return base


def _job(name, jtype="datastage", order=1, depends=None, cond=None,
         notify=None, sql=None, aguarde=None):
    j = {"job_name": name, "job_type": jtype, "job_command": "ds.job",
         "execution_order": order}
    if depends is not None:
        j["depends_on_jobs"] = depends
    if cond is not None:
        j["condition_json"] = json.dumps(cond)
    if notify is not None:
        j["notify_json"] = json.dumps(notify)
    if sql is not None:
        j["sql_json"] = json.dumps(sql)
    if aguarde is not None:
        j["aguarde_json"] = json.dumps(aguarde)
    return j


def _src(factory, jobs=None, **over):
    return factory._generate_dag_source(
        _pipeline(**over), jobs or [_job("JobA"), _job("JobB", order=2)])


def _exec_ns(src):
    """Importa DE FATO a DAG gerada (o que o Airflow faria) e devolve o
    namespace — os helpers gerados ficam chamáveis e substituíveis."""
    ns = {}
    with _ambiente_utils():
        exec(compile(src, "<dag>", "exec"), ns)
    return ns


# ─────────────────────── infra: contexto e hook falsos ──────────────────────

class _Momento:
    """data_interval_end/logical_date de mentira: só o que o código gerado usa."""

    def __init__(self, dt):
        self._dt = dt

    def in_timezone(self, tz):
        return self._dt


def _ctx(run_id="scheduled__2026-08-01T06:00:00+00:00", conf=None,
         momento=datetime(2026, 8, 1, 6, 0), tis=None):
    dag_run = SimpleNamespace(conf=conf or {}, run_id=run_id)
    if tis is not None:
        dag_run.get_task_instances = lambda: tis
    return {
        "run_id": run_id,
        "ts_nodash": "20260801T060000",
        "dag_run": dag_run,
        "data_interval_end": _Momento(momento) if momento is not None else None,
        "logical_date": None,
    }


class _CursorF2:
    def __init__(self, rowcount_update=1, select_row=None):
        self._rowcount_update = rowcount_update
        self._select_row = select_row    # resposta do SELECT da guarda de PULADO
        self._ultimo_select = None
        self.calendario = None           # F3: resposta de etl_calendario
        self.rowcount = -1
        self.execs = []          # (sql normalizada, params)

    def execute(self, sql, params=None):
        s = " ".join(str(sql).split())
        self.execs.append((s, params))
        self.rowcount = self._rowcount_update if s.startswith("UPDATE") else -1
        if "etl_calendario" in s:
            # F3: calendário julgado via utils.dependencias.calendario_bloqueia
            self._ultimo_select = (1,) if self.calendario else None
        else:
            self._ultimo_select = self._select_row if s.startswith("SELECT 1 FROM") else None

    def fetchone(self):
        return self._ultimo_select

    def fetchall(self):
        return []


class _HookF2:
    """MsSqlHook falso p/ os helpers gerados: OBJECT_ID, virada, blackout e
    calendário configuráveis; cursor grava toda SQL executada."""

    def __init__(self, tem_067=True, virada=None, blackout=None, calendario=None,
                 rowcount_update=1):
        self.cursor = _CursorF2(rowcount_update)
        self.cursor.calendario = calendario
        self.commits = 0
        self.tem_067 = tem_067
        self.virada = virada
        self.blackout = blackout
        self.calendario = calendario
        self.get_firsts = []

    def get_first(self, sql, parameters=None):
        s = " ".join(str(sql).split())
        self.get_firsts.append((s, parameters))
        if "OBJECT_ID" in s:
            return (1,) if self.tem_067 else (None,)
        if "hora_virada" in s:
            return (self.virada,)
        if "etl_blackout" in s:
            return self.blackout
        if "etl_calendario" in s:
            return self.calendario
        return None

    def get_conn(self):
        cur = self.cursor

        def _commit():
            self.commits += 1
        return SimpleNamespace(cursor=lambda: cur, commit=_commit, close=lambda: None)

    def run(self, sql, parameters=None, **_kw):
        pass


class _HookExplode:
    """Hook que levanta em TODA operação — banco fora do ar."""

    def get_first(self, *a, **kw):
        raise RuntimeError("banco fora")

    def get_conn(self):
        raise RuntimeError("banco fora")

    def run(self, *a, **kw):
        raise RuntimeError("banco fora")


def _instala_hook(ns, hook):
    ns["MsSqlHook"] = lambda **_kw: hook
    return hook


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


def _upstreams(src, alvo):
    return {a for a, b in _arestas(src) if b == alvo}


def _folhas(src):
    ar = _arestas(src)
    todos = {n for e in ar for n in e}
    return todos - {a for a, _ in ar}


def _bloco_task(src, inicio):
    """Bloco de instanciação de uma task gerada, até a linha do ``)`` de
    fechamento (o corte no primeiro ``)`` pararia dentro de Dataset(...))."""
    i = src.index(inicio)
    return src[i:src.index("\n    )", i)]


# ═══════════════ 1. Compilação/import das combinações (baseline) ════════════

_COND_BIN = {"tipo": "contagem", "tabela": "dbo.T", "operador": ">", "valor": 1,
             "ramo_verdadeiro": ["JobB"], "ramo_falso": ["JobC"]}
_COND_SWITCH = {"tipo": "contagem", "tabela": "dbo.T",
                "casos": [{"nome": "um", "ramo": ["JobB"]}], "ramo_senao": ["JobC"]}


def _cenarios(factory):
    return {
        "simples": _src(factory),
        "decisao": _src(factory, jobs=[
            _job("JobA"),
            _job("Dec", jtype="decisao", order=2, depends="JobA", cond=_COND_BIN),
            _job("JobB", order=3, depends=""), _job("JobC", order=4, depends=""),
        ]),
        "switch": _src(factory, jobs=[
            _job("JobA"),
            _job("Dec", jtype="decisao", order=2, depends="JobA", cond=_COND_SWITCH),
            _job("JobB", order=3, depends=""), _job("JobC", order=4, depends=""),
        ]),
        "notif_sql": _src(factory, jobs=[
            _job("JobA"),
            _job("Avisa", jtype="notificacao", order=2, depends="JobA",
                 notify={"grupo_id": 1, "template_id": None, "mensagem": "oi"}),
            _job("NoSQL", jtype="sql", order=3, depends="JobA", sql={"sql": "SELECT 1"}),
            _job("JobB", order=4, depends="JobA"),
        ]),
        "aguarde": _src(factory, jobs=[
            _job("JobA"), _job("JobB"),
            _job("Encontro", jtype="aguarde", order=2, depends="JobA,JobB",
                 aguarde={"politica": "todas_terminarem"}),
            _job("Limpa", jtype="shell", order=3, depends="Encontro"),
        ]),
        # F3: dependência vem da TABELA da 067 (_deps_tabela); o CSV é só o
        # espelho legado. O modo sensor/Dataset saiu do gerador.
        "dependencia": _src(factory, _deps_tabela=["PIPE_PAI"], depends_on="PIPE_PAI"),
        "horarios": _src(factory, horarios_especificos="09:00,10:30"),
        "dias_mes": _src(factory, schedule_type="monthly_days_times",
                         dias_horarios_mes='[{"dia": 1, "horarios": ["09:00"]}]'),
    }


def test_combinacoes_compilam_e_importam(factory):
    """Baseline da lição-mãe: toda combinação gera fonte que compila E importa
    (exec pega NameError de tempo de carga, que o ast.parse não vê)."""
    for nome, src in _cenarios(factory).items():
        ast.parse(src)
        _exec_ns(src)
        assert 'task_id="registrar_falha"' in src, nome
        assert "def _registrar_execucao(" in src, nome


# ═══════════════ 2. Chave: run_id desde o INSERT (defeito B1) ═══════════════

def test_registro_usa_run_id_nunca_ts_nodash(factory):
    """A DAG antiga atualizava por ts_nodash e o push inseria com NULL — as
    chaves nunca casavam e cada corrida virava DUAS linhas. O bloco de
    registro só pode usar context['run_id']; truncar ([:50]) colidiria
    prefixos no índice único (a migration 072 alarga a coluna)."""
    src = _src(factory)
    bloco = src[src.index("def _registrar_execucao"):src.index("def _registrar_falha")]
    assert "context['run_id']" in bloco
    assert "context['ts_nodash']" not in bloco
    assert "context.get('ts_nodash'" not in bloco
    assert "[:50]" not in src


def test_linha_nasce_no_wrapper_com_run_id(factory):
    """A linha nasce no check_agenda JÁ com o run_id como chave — nunca NULL
    (o índice único ux_pipe_exec trata dois NULL como duplicados)."""
    ns = _exec_ns(_src(factory))
    hook = _instala_hook(ns, _HookF2(rowcount_update=0))
    with _ambiente_utils():
        ok = ns["check_agenda"](**_ctx(run_id="manual__2026-08-01T09:00:00"))
    assert ok is True
    upd, ins = hook.cursor.execs
    assert upd[0].startswith("UPDATE dbo.etl_pipeline_execucao")
    assert ins[0].startswith("INSERT INTO dbo.etl_pipeline_execucao")
    # EXECUTANDO: inicio=GETDATE(), fim=NULL — no UPDATE (rerun limpo reseta a
    # janela) e no INSERT.
    assert "inicio=GETDATE(), fim=NULL" in upd[0]
    assert "VALUES (%s, %s, %s, %s, GETDATE(), NULL, %s, %s)" in ins[0]
    pipeline, data_ref, run_id, status, origem, motivo = ins[1]
    assert pipeline == "PIPE_EXEC"
    assert data_ref == date(2026, 8, 1)
    assert run_id == "manual__2026-08-01T09:00:00"
    assert status == "EXECUTANDO"
    assert origem == "manual"
    assert motivo is None
    assert hook.commits == 1


def test_upsert_atualiza_pela_chave_completa(factory):
    """Linha existente (Clear do run): UPDATE pela chave completa
    pipeline+data_ref+run_id, sem INSERT — a MESMA linha é reaproveitada."""
    ns = _exec_ns(_src(factory))
    hook = _instala_hook(ns, _HookF2(rowcount_update=1))
    with _ambiente_utils():
        ok = ns["check_agenda"](**_ctx())
    assert ok is True
    assert len(hook.cursor.execs) == 1
    sql, params = hook.cursor.execs[0]
    assert "WHERE pipeline_name=%s AND data_referencia=%s AND execution_id=%s" in sql
    assert params[-3:] == ("PIPE_EXEC", date(2026, 8, 1),
                           "scheduled__2026-08-01T06:00:00+00:00")


def test_disparado_por_cadeia_de_precedencia(factory):
    """conf['disparado_por'] > run_id 'manual*' > 'dataset_triggered*' > agenda."""
    ns = _exec_ns(_src(factory))
    dp = ns["_disparado_por"]
    assert dp(_ctx(conf={"disparado_por": "PIPE_PAI"})) == "PIPE_PAI"
    assert dp(_ctx(run_id="manual__2026-08-01T09:00:00")) == "manual"
    assert dp(_ctx(run_id="dataset_triggered__2026-08-01T09:00:00.123456+00:00")) == "dataset"
    assert dp(_ctx(run_id="scheduled__2026-08-01T06:00:00+00:00")) == "agenda"


# ═══════════ 3. PULADO: sem inicio/fim e com motivo por regra (D58) ═════════

def test_pulado_grava_sem_inicio_nem_fim(factory):
    """Pulado não começou nem terminou: inicio=NULL e fim=NULL — é a correção
    do COALESCE(inicio, criado_em) que elegia o PULADO como 'mais recente' e
    mascarava o SUCESSO do dia (defeito N7)."""
    ns = _exec_ns(_src(factory))
    hook = _instala_hook(ns, _HookF2(blackout=("Freeze mensal",), rowcount_update=0))
    with _ambiente_utils():
        ok = ns["check_agenda"](**_ctx())
    assert ok is False
    # Com a guarda de estado terminal, o rowcount 0 num PULADO gera um SELECT
    # de existência entre o UPDATE e o INSERT (linha inexistente → insere).
    upd, sel, ins = hook.cursor.execs
    assert "inicio=NULL, fim=NULL" in upd[0]
    assert sel[0].startswith("SELECT 1 FROM dbo.etl_pipeline_execucao")
    assert "VALUES (%s, %s, %s, %s, NULL, NULL, %s, %s)" in ins[0]
    assert ins[1][3] == "PULADO"
    assert ins[1][5] == "blackout vigente: Freeze mensal"
    # o PULADO carrega o run_id do PRÓPRIO run pulado: é outra linha, nunca
    # UPDATE sobre a linha SUCESSO de um run anterior (chaves diferentes)
    assert ins[1][2] == "scheduled__2026-08-01T06:00:00+00:00"


def test_motivo_especifico_das_cinco_saidas(factory):
    """Cada regra devolve a própria causa — a versão revertida generalizava
    numa string só e a guardiã não sabia dizer POR QUE pulou."""
    # 1) horários específicos
    ns = _exec_ns(_src(factory, horarios_especificos="09:00,10:30"))
    _instala_hook(ns, _HookF2())
    ok, motivo = ns["_check_agenda_regras"](_ctx(momento=datetime(2026, 8, 1, 11, 0)))
    assert ok is False and motivo == "horario 11:00 fora dos horarios configurados"

    # 2) dia + hora do mês
    ns = _exec_ns(_src(factory, schedule_type="monthly_days_times",
                       dias_horarios_mes='[{"dia": 1, "horarios": ["09:00"]}]'))
    _instala_hook(ns, _HookF2())
    ok, motivo = ns["_check_agenda_regras"](_ctx(momento=datetime(2026, 8, 2, 9, 0)))
    assert ok is False and motivo == "dia 2 as 09:00 fora da configuracao de dia e hora do mes"

    # 3) blackout
    ns = _exec_ns(_src(factory))
    _instala_hook(ns, _HookF2(blackout=("Freeze",)))
    ok, motivo = ns["_check_agenda_regras"](_ctx())
    assert ok is False and motivo == "blackout vigente: Freeze"

    # 4) fim de semana — F3: julga o DIA OPERACIONAL (momento lógico,
    # 2026-08-01 é sábado), não o relógio: pendulum.now congelado numa
    # segunda-feira prova que o relógio de parede não participa.
    ns = _exec_ns(_src(factory, somente_dias_uteis=1))
    _instala_hook(ns, _HookF2())
    ns["pendulum"] = SimpleNamespace(now=lambda tz: datetime(2026, 8, 3, 6, 0))
    ok, motivo = ns["_check_agenda_regras"](_ctx())
    assert ok is False and motivo == "fim de semana e pipeline somente dias uteis"

    # 5) calendário — F3: julgado pelo dia operacional via
    # utils.dependencias.calendario_bloqueia (por isso o _ambiente_utils)
    ns = _exec_ns(_src(factory, calendario_nome="FERIADOS"))
    _instala_hook(ns, _HookF2(calendario=("Natal",)))
    with _ambiente_utils():
        ok, motivo = ns["_check_agenda_regras"](_ctx())
    assert ok is False and motivo == "data bloqueada no calendario FERIADOS"


def test_liberado_devolve_true_sem_motivo(factory):
    ns = _exec_ns(_src(factory))
    _instala_hook(ns, _HookF2())
    ok, motivo = ns["_check_agenda_regras"](_ctx())
    assert ok is True and motivo is None


def test_decisao_devolvida_mesmo_com_hook_explodindo(factory, capsys):
    """A decisão do check_agenda é calculada ANTES do registro e devolvida
    INDEPENDENTEMENTE dele: banco fora do ar não pula (nem trava) a carga."""
    ns = _exec_ns(_src(factory))
    ns["MsSqlHook"] = lambda **_kw: _HookExplode()
    with _ambiente_utils():
        ok = ns["check_agenda"](**_ctx())
    assert ok is True
    saida = capsys.readouterr().out
    assert "[EXEC] Aviso: execucao nao registrada (migration 067 aplicada?)" in saida


# ══════════ 4. FALHA: task espelho do teams_error (D53/D57, lição E) ════════

def test_reg_falha_presente_mesmo_sem_card_de_erro(factory):
    """O registro é observabilidade, não notificação: existe com
    envia_msg_erro=0, com a mesma fiação que o card teria."""
    src = _src(factory, envia_msg_erro=0)
    assert "t_teams_error" not in src
    assert 'task_id="registrar_falha"' in src
    assert "TriggerRule.ONE_FAILED" in _bloco_task(src, "t_reg_falha = PythonOperator(")
    assert _upstreams(src, "t_reg_falha") == {"t_end_JobA", "t_end_JobB"}


def test_fiacao_espelho_do_teams_error_com_nos_especiais(factory):
    """ONE_FAILED só enxerga upstream DIRETO: o registrar_falha pendura nos
    MESMOS fins de ramo do teams_error — nunca no publish_dataset, que numa
    falha nem roda (a task ficaria cega)."""
    cen = _cenarios(factory)
    for nome in ("simples", "decisao", "notif_sql", "aguarde"):
        src = cen[nome]
        ups_falha = _upstreams(src, "t_reg_falha")
        assert ups_falha == _upstreams(src, "t_teams_error"), nome
        assert "t_publish_dataset" not in ups_falha, nome
    # nós especiais convergem de fato no espelho
    ups = _upstreams(cen["notif_sql"], "t_reg_falha")
    assert "t_notif_Avisa" in ups and "t_sql_NoSQL" in ups
    assert "t_wait_Encontro" in _upstreams(cen["aguarde"], "t_reg_falha")


def test_reg_falha_em_ondas_e_em_deps_explicitas(factory):
    """Os dois modos de fiação (execution_order e depends_on_jobs) ganham o
    mesmo registro de falha."""
    ondas = _src(factory)  # ordens 1 e 2, sem deps explícitas
    explicito = _src(factory, jobs=[_job("JobA"), _job("JobB", order=2, depends="JobA")])
    for src in (ondas, explicito):
        assert _upstreams(src, "t_reg_falha") == _upstreams(src, "t_teams_error")
        assert _upstreams(src, "t_reg_falha") == {"t_end_JobA", "t_end_JobB"}


def test_registrar_falha_grava_as_tasks_que_falharam(factory):
    ns = _exec_ns(_src(factory))
    hook = _instala_hook(ns, _HookF2(rowcount_update=1))
    tis = [SimpleNamespace(task_id="log_end_JobA", state="failed"),
           SimpleNamespace(task_id="JobB", state="success")]
    with _ambiente_utils():
        ns["_registrar_falha"](**_ctx(tis=tis))
    sql, params = hook.cursor.execs[0]
    assert params[0] == "FALHA"
    assert params[1] == "falha em: log_end_JobA"
    # FALHA fecha a corrida sem mexer no inicio da linha EXECUTANDO
    set_clause = sql.split("WHERE")[0]
    assert "fim=GETDATE()" in set_clause
    assert "inicio=" not in set_clause


def test_registrar_falha_sem_lista_usa_motivo_generico(factory):
    ns = _exec_ns(_src(factory))
    hook = _instala_hook(ns, _HookF2(rowcount_update=1))
    ctx = _ctx()
    ctx["dag_run"].get_task_instances = lambda: (_ for _ in ()).throw(RuntimeError("x"))
    with _ambiente_utils():
        ns["_registrar_falha"](**ctx)
    assert hook.cursor.execs[0][1][1] == "falha na execucao"


# ═════════ 5. SUCESSO no publish_dataset (mesma folha — anti-N1) ════════════

def test_publish_dataset_mantem_task_id_outlets_e_posicao(factory):
    """O publish vira PythonOperator gravando SUCESSO com o MESMO task_id,
    MESMOS outlets, MESMA regra (nenhuma nos fluxos sem decisão) e nada
    downstream dele — grafo topologicamente idêntico ao da main."""
    src = _src(factory)
    bloco = _bloco_task(src, "t_publish_dataset = PythonOperator(")
    assert 'task_id="publish_dataset"' in bloco
    assert "python_callable=_registrar_sucesso" in bloco
    assert "outlets=[Dataset(DATASET_URI)]" in bloco
    assert "trigger_rule" not in bloco          # sem decisão/notif/sql: sem regra
    assert "t_publish_dataset = EmptyOperator(" not in src
    assert _upstreams(src, "t_publish_dataset") == {"t_end_JobA", "t_end_JobB"}


def test_publish_dataset_regra_condicional_preservada(factory):
    """Com decisão a convergência tolerante continua a MESMA da main."""
    src = _cenarios(factory)["decisao"]
    bloco = _bloco_task(src, "t_publish_dataset = PythonOperator(")
    assert "trigger_rule=TriggerRule.NONE_FAILED_MIN_ONE_SUCCESS" in bloco


def test_nada_downstream_do_publish_dataset(factory):
    """Princípio nº1 da reversão: o estado do DagRun é decidido pelas FOLHAS.
    Nada pode ficar downstream do publish_dataset."""
    for nome, src in _cenarios(factory).items():
        for a, _b in _arestas(src):
            assert a != "t_publish_dataset", nome


def test_folha_nova_e_so_registrar_falha(factory):
    """Guarda estática da lição E: o conjunto de folhas da main ganha apenas
    t_reg_falha — e o publish_dataset segue folha."""
    src = _src(factory)  # f_fim=1, f_err=1
    assert _folhas(src) == {"t_publish_dataset", "t_teams_end", "t_teams_error",
                            "t_reg_falha"}
    src_min = _src(factory, envia_msg_fim=0, envia_msg_erro=0)
    assert _folhas(src_min) == {"t_publish_dataset", "t_reg_falha"}


def test_trigger_rules_existentes_intactas(factory):
    """Nenhuma trigger rule de task existente muda (byte-idênticas à main)."""
    src = _src(factory)
    assert "trigger_rule=TriggerRule.ALL_DONE" in _bloco_task(src, "t_teams_end = PythonOperator(")
    assert "trigger_rule=TriggerRule.ONE_FAILED" in _bloco_task(src, "t_teams_error = PythonOperator(")
    assert "trigger_rule=TriggerRule.ALL_DONE" in _bloco_task(src, "t_end_JobA = PythonOperator(")
    src_dec = _cenarios(factory)["decisao"]
    assert "trigger_rule=TriggerRule.ALL_DONE" in _bloco_task(src_dec, "t_flow_close = PythonOperator(")


def test_registrar_sucesso_fecha_sem_mexer_no_inicio(factory):
    ns = _exec_ns(_src(factory))
    hook = _instala_hook(ns, _HookF2(rowcount_update=1))
    with _ambiente_utils():
        ns["_registrar_sucesso"](**_ctx())
    sql, params = hook.cursor.execs[0]
    assert params[0] == "SUCESSO"
    set_clause = sql.split("WHERE")[0]
    assert "fim=GETDATE()" in set_clause
    assert "inicio=" not in set_clause


def test_registrar_sucesso_nunca_levanta(factory):
    """O callable do publish é degradado por construção: banco fora não pode
    derrubar a task que publica o Dataset."""
    ns = _exec_ns(_src(factory))
    ns["MsSqlHook"] = lambda **_kw: _HookExplode()
    with _ambiente_utils():
        ns["_registrar_sucesso"](**_ctx())   # não levanta


# ═══════ 6. flow_close fecha o ramo-vazio da decisão (caso-borda B4) ════════

def test_flow_close_fecha_ramo_vazio_so_com_decisao(factory):
    cen = _cenarios(factory)
    assert "decisao pulou todos os jobs" in cen["decisao"]
    for nome in ("simples", "notif_sql", "aguarde", "dependencia"):
        assert "decisao pulou todos os jobs" not in cen[nome], nome


def test_flow_close_exec_fecha_pulado_sem_falha(factory):
    """Ramo vazio: publish SKIPPED sem nenhuma falha → a corrida fecha PULADO
    (nada preso em EXECUTANDO). Com falha, quem fecha é o registrar_falha."""
    ns = _exec_ns(_cenarios(factory)["decisao"])
    hook = _instala_hook(ns, _HookF2(rowcount_update=1))
    tis = [SimpleNamespace(task_id="publish_dataset", state="skipped"),
           SimpleNamespace(task_id="JobB", state="skipped"),
           SimpleNamespace(task_id="JobA", state="success")]
    with _ambiente_utils():
        ns["_flow_close"](**_ctx(tis=tis))
    fechamentos = [p for _s, p in hook.cursor.execs if p and p[0] == "PULADO"]
    assert len(fechamentos) == 1
    assert fechamentos[0][1] == "decisao pulou todos os jobs"


def test_flow_close_nao_escreve_quando_houve_falha(factory):
    ns = _exec_ns(_cenarios(factory)["decisao"])
    hook = _instala_hook(ns, _HookF2(rowcount_update=1))
    tis = [SimpleNamespace(task_id="publish_dataset", state="skipped"),
           SimpleNamespace(task_id="JobA", state="failed")]
    with _ambiente_utils():
        ns["_flow_close"](**_ctx(tis=tis))
    assert not any(p and p[0] == "PULADO" for _s, p in hook.cursor.execs)


# ═══════════ 7. Herança de conf e momento LÓGICO (D10/D11, causa A) ═════════

def test_heranca_de_conf_valida_prevalece(factory):
    """conf['data_referencia'] é o carimbo do ODATE do predecessor (ou de um
    Trigger DAG w/ config) — vale mais que qualquer cálculo."""
    ns = _exec_ns(_src(factory))
    _instala_hook(ns, _HookF2(virada="20:00"))
    with _ambiente_utils():
        d = ns["_data_referencia"](_ctx(conf={"data_referencia": "2026-08-05"}))
    assert d == date(2026, 8, 5)


def test_heranca_invalida_recalcula_sem_abortar(factory, capsys):
    ns = _exec_ns(_src(factory))
    _instala_hook(ns, _HookF2())
    with _ambiente_utils():
        d = ns["_data_referencia"](_ctx(conf={"data_referencia": "banana"},
                                        momento=datetime(2026, 8, 1, 23, 30)))
    assert d == date(2026, 8, 1)
    assert "data_referencia herdada invalida" in capsys.readouterr().out


def test_momento_logico_nunca_relogio_de_parede(factory):
    """Atraso de fila que empurra a execução para depois da meia-noite não
    muda a data: o cálculo usa data_interval_end, não pendulum.now."""
    ns = _exec_ns(_src(factory))
    _instala_hook(ns, _HookF2())
    ns["pendulum"] = SimpleNamespace(now=lambda tz: datetime(2026, 8, 2, 3, 0))
    with _ambiente_utils():
        d = ns["_data_referencia"](_ctx(momento=datetime(2026, 8, 1, 23, 30)))
    assert d == date(2026, 8, 1)     # e não 02/08, a data do "relógio"


def test_sem_momento_no_contexto_cai_no_relogio(factory):
    ns = _exec_ns(_src(factory))
    _instala_hook(ns, _HookF2())
    ns["pendulum"] = SimpleNamespace(now=lambda tz: datetime(2026, 8, 2, 3, 0))
    with _ambiente_utils():
        d = ns["_data_referencia"](_ctx(momento=None))
    assert d == date(2026, 8, 2)


def test_virada_do_banco_desloca_a_data(factory):
    """O caso que motivou a spec: virada 20:00 faz 31/07 23:30 pertencer a
    01/08 (dia de negócio seguinte)."""
    ns = _exec_ns(_src(factory))
    _instala_hook(ns, _HookF2(virada="20:00"))
    with _ambiente_utils():
        d = ns["_data_referencia"](_ctx(momento=datetime(2026, 7, 31, 23, 30)))
    assert d == date(2026, 8, 1)


def test_virada_indisponivel_degrada_para_calendario(factory, capsys):
    """Sem a 067 (coluna inexistente) ou banco fora: virada 00:00 = data do
    calendário, o comportamento de sempre."""
    ns = _exec_ns(_src(factory))
    ns["MsSqlHook"] = lambda **_kw: _HookExplode()
    with _ambiente_utils():
        d = ns["_data_referencia"](_ctx(momento=datetime(2026, 7, 31, 23, 30)))
    assert d == date(2026, 7, 31)
    assert "hora de virada indisponivel" in capsys.readouterr().out


# ═════════════ 8. Degradação sem a migration 067 (D59, risco 3) ═════════════

def test_sem_067_loga_o_aviso_e_nao_escreve(factory, capsys):
    """Tabela ausente → aviso NOMEANDO a 067 e retorno limpo — distinto do
    erro genérico. Nenhum INSERT/UPDATE tentado (sem except mudo escondendo
    gravação zero com task verde)."""
    ns = _exec_ns(_src(factory))
    hook = _instala_hook(ns, _HookF2(tem_067=False))
    with _ambiente_utils():
        ns["_registrar_execucao"]("EXECUTANDO", _ctx())
    assert hook.cursor.execs == []
    assert hook.commits == 0
    assert "[EXEC] migration 067 ausente — execucao nao registrada" in capsys.readouterr().out


def test_excecao_no_registro_nunca_propaga(factory, capsys):
    ns = _exec_ns(_src(factory))
    ns["MsSqlHook"] = lambda **_kw: _HookExplode()
    with _ambiente_utils():
        ns["_registrar_execucao"]("SUCESSO", _ctx())   # não levanta
    assert "[EXEC] Aviso: execucao nao registrada (migration 067 aplicada?)" in capsys.readouterr().out


# ═════════ 9. default_args sem helpers (D56 — gotcha do NameError) ══════════

def test_default_args_nao_referencia_helper(factory):
    """No arquivo gerado as consts saem ANTES dos helpers: qualquer helper em
    default_args (ex.: on_failure_callback) é NameError no import do Airflow
    — que o pytest de geração não pega. Por isso FALHA/SUCESSO são tasks, não
    callbacks."""
    src = _src(factory)
    bloco = src[src.index("default_args"):]
    bloco = bloco[:bloco.index("}")]
    for proibido in ("teams_", "log_start", "log_end", "_flow_close", "_notify_",
                     "_registrar", "_data_referencia", "_disparado_por",
                     "_check_agenda", "on_failure_callback"):
        assert proibido not in bloco
    # a ordem consts → helpers é o que torna o gotcha um NameError real
    assert src.index("default_args") < src.index("def _now_str")


# ═════════════════ 10. Agendamento sob F3 (D01/D38) ═════════════════════════

def test_f3_dependente_sem_sensor_nem_consumo_de_dataset(factory):
    """F3 (D01): o dependente perde o gatilho próprio e o polling; o cron de
    quem NÃO tem dependência fica intacto (D38). O outlet do publish
    permanece nos dois — é a ponte para DAG antiga não regenerada."""
    cen = _cenarios(factory)
    assert "ExternalTaskSensor" not in cen["dependencia"]
    assert "schedule=[Dataset(" not in cen["dependencia"]
    assert "DEPENDS_ON_DAG_ID" not in cen["dependencia"]
    linhas_dep = [l.strip() for l in cen["dependencia"].splitlines()
                  if l.strip().startswith("schedule=")]
    assert len(linhas_dep) == 1 and linhas_dep[0].startswith("schedule=None,")
    linhas = [l.strip() for l in cen["simples"].splitlines()
              if l.strip().startswith("schedule=")]
    assert linhas == ['schedule="0 6 * * *",']
    for nome in ("simples", "dependencia"):
        assert "outlets=[Dataset(DATASET_URI)]" in cen[nome], nome


# ═════════ 10. guarda: PULADO não rebaixa estado terminal (revisão F2) ══════

def test_update_de_pulado_leva_a_guarda_terminal(factory):
    """O UPDATE de PULADO exige status não-terminal; EXECUTANDO e SUCESSO não.
    Cenário real: Clear de run SUCESSO num dia bloqueado por regra de relógio
    (fim de semana/blackout) — sem a guarda, o SUCESSO da data viraria PULADO."""
    ns = _exec_ns(_src(factory))
    hook = _instala_hook(ns, _HookF2())
    with _ambiente_utils():
        ns["_registrar_execucao"]("PULADO", _ctx(), motivo="fim de semana")
        ns["_registrar_execucao"]("EXECUTANDO", _ctx())
        ns["_registrar_execucao"]("SUCESSO", _ctx())
    updates = [s for s, _ in hook.cursor.execs if s.startswith("UPDATE")]
    assert "AND status NOT IN ('SUCESSO', 'FALHA')" in updates[0]
    assert "NOT IN" not in updates[1] and "NOT IN" not in updates[2]


def test_pulado_nao_rebaixa_linha_terminal_existente(factory, capsys):
    """UPDATE guardado não casa (linha existe como SUCESSO) → SELECT confirma
    a existência → NÃO insere (duplicaria a chave), loga e retorna."""
    ns = _exec_ns(_src(factory))
    hook = _instala_hook(ns, _HookF2(rowcount_update=0))
    hook.cursor._select_row = (1,)
    with _ambiente_utils():
        ns["_registrar_execucao"]("PULADO", _ctx(), motivo="blackout")
    sqls = [s for s, _ in hook.cursor.execs]
    assert not any(s.startswith("INSERT") for s in sqls), sqls
    assert "PULADO nao rebaixa estado terminal" in capsys.readouterr().out


def test_pulado_em_linha_inexistente_insere_normalmente(factory):
    """A guarda não pode impedir o caso legítimo: linha ainda não existe →
    INSERT do PULADO acontece."""
    ns = _exec_ns(_src(factory))
    hook = _instala_hook(ns, _HookF2(rowcount_update=0))
    with _ambiente_utils():
        ns["_registrar_execucao"]("PULADO", _ctx(), motivo="calendario")
    inserts = [(s, p) for s, p in hook.cursor.execs if s.startswith("INSERT")]
    assert len(inserts) == 1
    assert "PULADO" in str(inserts[0][1])
