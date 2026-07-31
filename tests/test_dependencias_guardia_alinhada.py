"""
Correção D da revisão adversarial: alinhar a guardiã com a execução.

Cinco defeitos:
  1. DATA_DIVERGENTE disparava todo dia para todo dependente — a guardiã achava
     o sucesso NORMAL de ontem e chamava de divergência;
  2. a data examinada vinha da virada do DEPENDENTE, mas a corrida é carimbada
     com a virada do PREDECESSOR — rede de segurança cega na corrida que
     atravessa a meia-noite;
  3. predecessor PULADO fazia ordenar uma corrida que nunca resolvia, e ainda
     gerava JANELA_ESTOUROU todo fim de semana;
  4. a mensagem dizia "nenhum predecessor executou" quando TODOS executaram;
  5. Variable mal preenchida gerava cron inválido e derrubava a DAG inteira.
"""
from __future__ import annotations

import importlib.util
import sys
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

for _mod in [
    "airflow", "airflow.decorators", "airflow.models", "airflow.operators",
    "airflow.operators.python", "airflow.operators.empty",
    "airflow.providers.microsoft.mssql.hooks.mssql", "airflow.utils",
    "airflow.utils.trigger_rule", "airflow.api", "airflow.api.client",
    "airflow.api.client.local_client", "pendulum",
]:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

_ROOT = Path(__file__).parent.parent
_DAGS = _ROOT / "dags"
if str(_DAGS) not in sys.path:
    sys.path.insert(0, str(_DAGS))


@pytest.fixture(scope="module")
def guardia():
    spec = importlib.util.spec_from_file_location(
        "guardia_alinhada_test", _ROOT / "dags/etl_dependencia_guardia.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Hook:
    """Hook falso com as respostas por tipo de consulta."""

    def __init__(self, status_preds, execucao=None, datas_predecessores=(),
                 carimbos_outros=()):
        self.status_preds = status_preds
        self.execucao = execucao
        self.datas_predecessores = datas_predecessores
        self.carimbos_outros = carimbos_outros
        self.escritas = []

    def get_records(self, sql, parameters=None):
        if "DISTINCT e.data_referencia" in sql:
            return [(d,) for d in self.datas_predecessores]
        if "DISTINCT CONVERT(VARCHAR(10), data_referencia" in sql:
            return [(d,) for d in self.carimbos_outros]
        if "d.depende_de" in sql:
            return [(k, v) for k, v in self.status_preds.items()]
        return []

    def get_first(self, sql, parameters=None):
        if "TOP 1 status FROM dbo.etl_pipeline_execucao" in sql:
            return (self.execucao,) if self.execucao else None
        return None

    def get_conn(self):
        hook = self

        class Cur:
            rowcount = 1

            def execute(self, sql, params=None):
                hook.escritas.append((sql, params))

            def fetchone(self):
                return [0]

            def close(self):
                pass

        class Conn:
            def cursor(self):
                return Cur()

            def commit(self):
                pass

            def rollback(self):
                pass

            def close(self):
                pass

        return Conn()


def _pipe(**over):
    base = {"nome": "PIPE_C", "hora_virada": None,
            "nao_iniciar_antes": None, "hora_limite": None}
    base.update(over)
    return base


def _eventos(hook, tipo=None):
    saida = []
    for sql, params in hook.escritas:
        if "INSERT INTO dbo.etl_dependencia_evento" in sql:
            if tipo is None or params[2] == tipo:
                saida.append(params)
    return saida


# ───────────── 1. DATA_DIVERGENTE só quando é divergência de verdade ───────

def test_sucesso_normal_de_ontem_nao_gera_alerta(guardia):
    """Às 00:05 o predecessor ainda não rodou hoje — isso é NORMAL.

    Antes: a guardiã achava o sucesso de ontem na janela de ±3 dias e mandava
    um card por dependente, todo dia. O canal virava ruído.
    """
    hook = Hook(status_preds={"PAI_A": None}, execucao=None, carimbos_outros=())
    guardia._tratar_corrida(hook, _pipe(), date(2026, 8, 1),
                            datetime(2026, 8, 1, 0, 5), MagicMock())
    assert _eventos(hook, "DATA_DIVERGENTE") == []


def test_carimbo_recente_com_outra_data_gera_alerta(guardia):
    """Divergência real: rodou há pouco e saiu com outro dia."""
    hook = Hook(status_preds={"PAI_A": None}, execucao="AGUARDANDO_DEPENDENCIA",
                carimbos_outros=("2026-07-31",))
    guardia._tratar_corrida(hook, _pipe(), date(2026, 8, 1),
                            datetime(2026, 8, 1, 10, 0), MagicMock())
    eventos = _eventos(hook, "DATA_DIVERGENTE")
    assert eventos and "2026-07-31" in eventos[0][3]


def test_consulta_de_divergencia_olha_o_relogio_e_nao_a_janela_de_dias(guardia):
    """É `rodou nas últimas horas`, não `existe em ±3 dias`."""
    hook = MagicMock()
    hook.get_records.return_value = []
    guardia._carimbou_outra_data(hook, "PAI_A", date(2026, 8, 1))
    sql = hook.get_records.call_args[0][0]
    assert "DATEADD(hour" in sql and "GETDATE()" in sql
    assert "BETWEEN DATEADD(day" not in sql


# ───────────── 2. Datas examinadas incluem o que o pai carimbou ────────────

def test_datas_em_aberto_inclui_o_carimbo_do_predecessor(guardia):
    """Virada configurada só no pai não pode cegar a guardiã."""
    hook = Hook(status_preds={}, datas_predecessores=(date(2026, 7, 31),))
    datas = guardia._datas_em_aberto(hook, "PIPE_C", date(2026, 8, 1))
    assert datas == [date(2026, 7, 31), date(2026, 8, 1)]


def test_datas_em_aberto_sem_a_tabela_devolve_a_calculada(guardia):
    hook = MagicMock()
    hook.get_records.side_effect = RuntimeError("Invalid object name")
    assert guardia._datas_em_aberto(hook, "PIPE_C", date(2026, 8, 1)) == [date(2026, 8, 1)]


# ───────────── 3. Predecessor PULADO não ordena corrida ────────────────────

def test_predecessor_pulado_nao_ordena(guardia):
    """Sábado: o pai foi PULADO por dias úteis.

    Antes: a guardiã ordenava o dependente, a linha nunca resolvia (ele tem
    schedule=None) e ainda saía JANELA_ESTOUROU todo fim de semana.
    """
    hook = Hook(status_preds={"PAI_A": "PULADO"}, execucao=None)
    guardia._tratar_corrida(hook, _pipe(hora_limite="08:00:00"), date(2026, 8, 1),
                            datetime(2026, 8, 1, 9, 0), MagicMock())
    assert not [s for s, _ in hook.escritas
                if "INSERT INTO dbo.etl_pipeline_execucao" in s]


def test_predecessor_executando_ordena(guardia):
    """A corrida COMEÇOU de fato — aí sim o dependente é ordenado."""
    hook = Hook(status_preds={"PAI_A": "EXECUTANDO"}, execucao=None)
    r = guardia._tratar_corrida(hook, _pipe(), date(2026, 8, 1),
                                datetime(2026, 8, 1, 9, 0), MagicMock())
    assert r[0] == 1
    assert [s for s, _ in hook.escritas if "AGUARDANDO_DEPENDENCIA" in s]


def test_ordenacao_perdida_para_a_corrida_rele_o_estado(guardia, monkeypatch):
    """Se o push ordenou no mesmo instante, não assumir que fomos nós.

    Antes o ciclo seguia com `atual='AGUARDANDO_DEPENDENCIA'` e contava a
    ordenação, mesmo quando o INSERT tinha violado o índice — e daí podia
    gravar um JANELA_ESTOUROU falso sobre uma corrida que já estava rodando.
    """
    hook = Hook(status_preds={"PAI_A": "SUCESSO"}, execucao=None)
    monkeypatch.setattr(guardia, "_ordenar", lambda *a, **k: False)
    r = guardia._tratar_corrida(hook, _pipe(), date(2026, 8, 1),
                                datetime(2026, 8, 1, 9, 0), MagicMock())
    assert r[0] == 0, "não pode contar uma ordenação que não aconteceu"


# ───────────── 4. Mensagem coerente com a realidade ───────────────────────

def test_mensagem_de_janela_cita_os_pendentes(guardia):
    hook = Hook(status_preds={"PAI_A": "SUCESSO", "PAI_B": None},
                execucao="AGUARDANDO_DEPENDENCIA")
    guardia._tratar_corrida(hook, _pipe(hora_limite="11:00:00"), date(2026, 8, 1),
                            datetime(2026, 8, 1, 11, 30), MagicMock())
    ev = _eventos(hook, "JANELA_ESTOUROU")
    assert ev and "PAI_B" in ev[0][3]


def test_mensagem_nao_diz_que_ninguem_executou_quando_todos_executaram(guardia):
    """Todos SUCESSO e ainda parado: o disparo é que não aconteceu.

    A mensagem antiga afirmava o oposto da realidade.
    """
    hook = Hook(status_preds={"PAI_A": "SUCESSO"}, execucao="AGUARDANDO_DEPENDENCIA")
    # Janela às 23:00 impede o disparo, então cai no alerta com tudo liberado.
    guardia._tratar_corrida(hook, _pipe(hora_limite="11:00:00", nao_iniciar_antes="23:00:00"),
                            date(2026, 8, 1), datetime(2026, 8, 1, 11, 30), MagicMock())
    ev = _eventos(hook, "JANELA_ESTOUROU")
    assert ev
    assert "nenhum predecessor executou" not in ev[0][3]
    assert "disparo" in ev[0][3]


def test_sem_execucao_nenhuma_a_mensagem_continua_correta(guardia):
    hook = Hook(status_preds={"PAI_A": None}, execucao=None)
    guardia._tratar_corrida(hook, _pipe(hora_limite="11:00:00"), date(2026, 8, 1),
                            datetime(2026, 8, 1, 11, 30), MagicMock())
    ev = _eventos(hook, "JANELA_ESTOUROU")
    assert ev and "nenhum predecessor executou" in ev[0][3]


# ───────────── 5. Intervalo do cron protegido ─────────────────────────────

def test_intervalo_invalido_nao_derruba_a_dag(guardia):
    fonte = (_ROOT / "dags/etl_dependencia_guardia.py").read_text(encoding="utf-8")
    assert "max(1, min(59," in fonte


def test_janela_estourada_nao_marca_falha(guardia):
    """Decisão do usuário: alerta sim, falhar não."""
    hook = Hook(status_preds={"PAI_A": None}, execucao="AGUARDANDO_DEPENDENCIA")
    guardia._tratar_corrida(hook, _pipe(hora_limite="11:00:00"), date(2026, 8, 1),
                            datetime(2026, 8, 1, 12, 0), MagicMock())
    assert not [s for s, _ in hook.escritas if "'FALHA'" in s]
