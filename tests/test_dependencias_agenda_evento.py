"""
Correção A da revisão adversarial: separar agenda por RELÓGIO de liberação por
EVENTO.

Estes testes EXECUTAM o `check_agenda` gerado, em vez de procurar strings no
código. Foi essa a lacuna que deixou os defeitos passarem: a suíte provava que a
DAG compilava e que o wiring estava certo, nunca que a regra de agenda ainda
fazia sentido depois que o dependente perdeu o cron.

Defeitos reproduzidos aqui (todos falhavam antes da correção):
  • dependente com horários específicos era PULADO em 100% dos disparos;
  • dependente mensal/semanal perdia a restrição de DIA e rodava todo dia;
  • dias úteis e calendário mediam o relógio, matando a corrida que atravessa
    a meia-noite.
"""
from __future__ import annotations

import ast
import importlib.util
import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

for _mod in [
    "airflow", "airflow.decorators", "airflow.models", "airflow.operators",
    "airflow.operators.python", "airflow.operators.empty", "airflow.operators.bash",
    "airflow.providers.microsoft.mssql.hooks.mssql", "airflow.utils",
    "airflow.utils.trigger_rule", "airflow.sensors.external_task", "airflow.datasets",
    "pendulum", "airflow.providers.ssh.hooks.ssh", "airflow.utils.dates",
    "airflow.exceptions",
]:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

_ROOT = Path(__file__).parent.parent


@pytest.fixture(scope="module")
def factory():
    spec = importlib.util.spec_from_file_location(
        "etl_dag_factory_agenda_test", _ROOT / "dags/etl_dag_factory.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _gerar(factory, **over):
    base = {
        "pipeline_name": "PIPE_X", "project_name": "BI_CVP", "domain": "T",
        "tags": "ETL", "scheduled_time": "07:00:00", "schedule_hour": 7,
        "envia_msg_inicio": 0, "envia_msg_fim": 0, "envia_msg_erro": 1,
        "ambiente": "PROD", "schedule_type": "daily",
    }
    base.update(over)
    return factory._generate_dag_source(
        base, [{"job_name": "A", "job_type": "python", "job_command": "m",
                "execution_order": 1}])


def _carregar_check(src, data_referencia, calendario_bloqueia=False):
    """Executa as funções de agenda da DAG gerada, isoladas do resto.

    Monta um módulo só com as constantes e as funções relevantes — o `with DAG`
    não roda. `_data_referencia` é substituída pela data que o teste quer, que é
    o insumo das regras de dia de processamento.
    """
    arvore = ast.parse(src)
    querer_fn = {"_disparo_por_evento", "_check_agenda_regras", "check_agenda"}
    corpo = [
        n for n in arvore.body
        if (isinstance(n, ast.Assign)
            and any(getattr(t, "id", "") in {
                "HORARIOS_ESPECIFICOS", "DIAS_HORARIOS_MES", "RESTRICAO_DIA",
                "SOMENTE_DIAS_UTEIS", "CALENDARIO_NOME", "LOCAL_TZ",
                "MSSQL_CONN_ID", "PROJECT_NAME", "PIPELINE_NAME"} for t in n.targets))
        or (isinstance(n, ast.FunctionDef) and n.name in querer_fn)
    ]
    modulo = ast.Module(body=corpo, type_ignores=[])
    ast.fix_missing_locations(modulo)

    hook = MagicMock()
    # get_first: 1º uso é blackout (None = sem blackout), 2º é calendário.
    hook.get_first.side_effect = lambda *a, **k: (
        ("feriado",) if (calendario_bloqueia and "etl_calendario" in a[0]) else None)

    ns = {
        "MsSqlHook": lambda **kw: hook,
        "pendulum": SimpleNamespace(now=lambda tz=None: SimpleNamespace(weekday=lambda: 0)),
        "_data_referencia": lambda ctx: data_referencia,
        "_registrar_execucao": lambda *a, **k: None,
        "print": lambda *a, **k: None,
    }
    exec(compile(modulo, "<dag>", "exec"), ns)
    return ns


# ───────────────── Defeito: dependente com horários específicos ────────────

def test_disparo_por_dependencia_ignora_horarios_especificos(factory):
    """O pai conclui 08:04; a lista é ['08:00','14:00'].

    Antes: PULADO em 100% dos disparos, sem alerta, travando a cascata.
    """
    src = _gerar(factory, schedule_type="custom",
                 horarios_especificos="08:00,14:00", depends_on="PAI")
    ns = _carregar_check(src, date(2026, 8, 3))
    ctx = {"run_id": "dep__PAI__2026-08-03", "data_interval_end": None}
    assert ns["_check_agenda_regras"](**ctx) is True


def test_disparo_pela_guardia_tambem_ignora(factory):
    src = _gerar(factory, schedule_type="custom",
                 horarios_especificos="08:00", depends_on="PAI")
    ns = _carregar_check(src, date(2026, 8, 3))
    assert ns["_check_agenda_regras"](run_id="guardia__2026-08-03") is True


def test_pipeline_com_cron_mantem_o_filtro_de_horario(factory):
    """A regra continua valendo para quem é disparado pelo cron."""
    src = _gerar(factory, schedule_type="custom", horarios_especificos="08:00,14:00")
    ns = _carregar_check(src, date(2026, 8, 3))
    fora = SimpleNamespace(in_timezone=lambda tz: SimpleNamespace(
        strftime=lambda f: "09:37", day=3))
    assert ns["_check_agenda_regras"](run_id="scheduled__2026-08-03",
                                      data_interval_end=fora) is False
    dentro = SimpleNamespace(in_timezone=lambda tz: SimpleNamespace(
        strftime=lambda f: "08:00", day=3))
    assert ns["_check_agenda_regras"](run_id="scheduled__2026-08-03",
                                      data_interval_end=dentro) is True


# ──────────────── Defeito: restrição de DIA perdida com o cron ─────────────

def test_mensal_com_dependencia_so_roda_no_dia_configurado(factory):
    """Fechamento do dia 5 disparado por dependência.

    Antes: rodava em TODO dia em que o predecessor concluísse — 30x/mês.
    """
    src = _gerar(factory, schedule_type="monthly", schedule_dom=5, depends_on="PAI")
    ctx = {"run_id": "dep__PAI__x"}
    assert _carregar_check(src, date(2026, 8, 5))["_check_agenda_regras"](**ctx) is True
    assert _carregar_check(src, date(2026, 8, 6))["_check_agenda_regras"](**ctx) is False
    assert _carregar_check(src, date(2026, 8, 1))["_check_agenda_regras"](**ctx) is False


def test_semanal_com_dependencia_so_roda_no_dia_da_semana(factory):
    """schedule_dow=1 (segunda, convenção cron)."""
    src = _gerar(factory, schedule_type="weekly", schedule_dow=1, depends_on="PAI")
    ctx = {"run_id": "dep__PAI__x"}
    # 2026-08-03 é segunda; 2026-08-05 é quarta.
    assert _carregar_check(src, date(2026, 8, 3))["_check_agenda_regras"](**ctx) is True
    assert _carregar_check(src, date(2026, 8, 5))["_check_agenda_regras"](**ctx) is False


def test_quinzenal_com_dependencia_roda_nos_dois_dias(factory):
    src = _gerar(factory, schedule_type="biweekly", schedule_dom=3, depends_on="PAI")
    ctx = {"run_id": "dep__PAI__x"}
    for dia, esperado in ((3, True), (18, True), (10, False)):
        assert _carregar_check(src, date(2026, 8, dia))["_check_agenda_regras"](**ctx) is esperado, dia


def test_pipeline_com_cron_nao_ganha_restricao_redundante(factory):
    """Quem tem cron já é filtrado por ele — RESTRICAO_DIA fica None."""
    src = _gerar(factory, schedule_type="monthly", schedule_dom=5)
    assert "RESTRICAO_DIA = None" in src
    ns = _carregar_check(src, date(2026, 8, 20))
    assert ns["_check_agenda_regras"](run_id="scheduled__x") is True


def test_diario_com_dependencia_roda_todo_dia(factory):
    """Sem restrição de dia, dependência não inventa uma."""
    src = _gerar(factory, schedule_type="daily", depends_on="PAI")
    assert "RESTRICAO_DIA = None" in src
    ns = _carregar_check(src, date(2026, 8, 20))
    assert ns["_check_agenda_regras"](run_id="dep__PAI__x") is True


# ─────────── Defeito: dias úteis e calendário mediam o relógio ─────────────

def test_dias_uteis_olha_a_data_de_referencia_e_nao_o_relogio(factory):
    """Corrida de SEXTA liberada no SÁBADO de madrugada.

    Antes: `pendulum.now().weekday()` via sábado e matava a corrida — o caso
    exato que motivou a data de referência.
    """
    src = _gerar(factory, somente_dias_uteis=1, depends_on="PAI")
    ctx = {"run_id": "dep__PAI__x"}
    # data de referência = sexta 2026-07-31 → deve rodar
    assert _carregar_check(src, date(2026, 7, 31))["_check_agenda_regras"](**ctx) is True
    # data de referência = sábado → não roda
    assert _carregar_check(src, date(2026, 8, 1))["_check_agenda_regras"](**ctx) is False


def test_calendario_consulta_a_data_de_referencia(factory):
    src = _gerar(factory, calendario_nome="FERIADOS_BR", depends_on="PAI")
    ns = _carregar_check(src, date(2026, 8, 3), calendario_bloqueia=True)
    assert ns["_check_agenda_regras"](run_id="dep__PAI__x") is False
    ns2 = _carregar_check(src, date(2026, 8, 3), calendario_bloqueia=False)
    assert ns2["_check_agenda_regras"](run_id="dep__PAI__x") is True


def test_calendario_usa_parametro_e_nao_getdate(factory):
    """A query tinha CAST(GETDATE() AS DATE) fixo."""
    src = _gerar(factory, calendario_nome="FERIADOS_BR", depends_on="PAI")
    assert "CAST(GETDATE() AS DATE)" not in src
    assert "parameters=(CALENDARIO_NOME, _dref)" in src


def test_blackout_continua_medindo_o_relogio(factory):
    """Freeze operacional é sobre AGORA, não sobre o dia de processamento."""
    src = _gerar(factory, depends_on="PAI")
    bloco = src[src.index("etl_blackout"):]
    assert "GETDATE() BETWEEN inicio AND fim" in bloco[:200]


# ────────────────────────────── Sanidade ───────────────────────────────────

def test_todas_as_combinacoes_compilam(factory):
    combinacoes = [
        {}, {"depends_on": "PAI"},
        {"schedule_type": "monthly", "schedule_dom": 5, "depends_on": "PAI"},
        {"schedule_type": "weekly", "schedule_dow": 3, "depends_on": "PAI"},
        {"schedule_type": "biweekly", "schedule_dom": 2, "depends_on": "PAI"},
        {"schedule_type": "custom", "horarios_especificos": "08:00", "depends_on": "PAI"},
        {"schedule_type": "monthly_days_times",
         "dias_horarios_mes": '[{"dia": 5, "horarios": ["08:00"]}]', "depends_on": "PAI"},
        {"somente_dias_uteis": 1, "calendario_nome": "F", "depends_on": "PAI,PAI2"},
    ]
    for extra in combinacoes:
        ast.parse(_gerar(factory, **extra))
