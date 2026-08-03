"""
Testes do PORTÃO da etapa em espera (dags/utils/espera.py) — F5 da spec
docs/spec-operacao-nivel-etapa.md, §5 Bloco C.

O portão roda dentro do ``log_start`` de TODA etapa de TODO pipeline. Os
cenários aqui são, nesta ordem de importância:

  1. **caminho normal** — sem pausa e sem tabela, o portão devolve None e não
     levanta nada. É o teste que representa 100% das execuções de produção;
  2. espera de verdade (``AirflowRescheduleException``) e liberação;
  3. teto estourado → falha explicada + evento de alerta;
  4. degradação: tabela ausente, erro de banco, Variable maluca.

Como o Airflow não está instalado no ambiente de teste, ``airflow.exceptions``
e ``airflow.utils.timezone`` são stubados com peças REAIS (uma classe de
exceção de verdade e um utcnow de verdade) — stubar com MagicMock não serviria:
``raise MagicMock()`` nem é Python válido, e o teste passaria por engano.
"""
from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock

import pytest

_ROOT = Path(__file__).parent.parent


# ─────────────────────── stubs de Airflow (peças reais) ──────────────────────

class _AirflowRescheduleException(Exception):
    def __init__(self, reschedule_date):
        super().__init__(f"reschedule ate {reschedule_date}")
        self.reschedule_date = reschedule_date


class _AirflowFailException(Exception):
    """Dublê da exceção que o Airflow trata com force_fail=True (sem retry)."""


def _instala_stubs():
    for nome in ("airflow", "airflow.models", "airflow.providers",
                 "airflow.providers.microsoft",
                 "airflow.providers.microsoft.mssql",
                 "airflow.providers.microsoft.mssql.hooks",
                 "airflow.providers.microsoft.mssql.hooks.mssql"):
        sys.modules.setdefault(nome, MagicMock())
    exc = ModuleType("airflow.exceptions")
    exc.AirflowRescheduleException = _AirflowRescheduleException
    exc.AirflowFailException = _AirflowFailException
    sys.modules["airflow.exceptions"] = exc
    utils = sys.modules.get("airflow.utils") or ModuleType("airflow.utils")
    sys.modules["airflow.utils"] = utils
    tz = ModuleType("airflow.utils.timezone")
    tz.utcnow = lambda: datetime.now(timezone.utc)
    sys.modules["airflow.utils.timezone"] = tz
    utils.timezone = tz


_instala_stubs()


@pytest.fixture(scope="module")
def espera():
    caminho = _ROOT / "dags/utils/espera.py"
    spec = importlib.util.spec_from_file_location("utils_espera_test", caminho)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ────────────────────────────── banco de mentira ─────────────────────────────

class FakeCursor:
    def __init__(self, conn):
        self.conn = conn

    def execute(self, sql, params=None):
        self.conn.sqls.append((sql, params))
        if self.conn.erro is not None:
            raise self.conn.erro
        if sql.lstrip().upper().startswith("SELECT"):
            self._resultado = self.conn.select
        else:
            self._resultado = None
        self.rowcount = self.conn.rowcount

    def fetchone(self):
        return self._resultado


class FakeConn:
    """pymssql de mentira: uma linha de SELECT, um rowcount e um erro opcional."""

    def __init__(self, select=None, rowcount=1, erro=None):
        self.select = select
        self.rowcount = rowcount
        self.erro = erro
        self.sqls: list = []
        self.commits = 0
        self.fechada = False

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        self.commits += 1

    def close(self):
        self.fechada = True


class FakeHook:
    def __init__(self, conn):
        self._conn = conn

    def get_conn(self):
        if isinstance(self._conn, Exception):
            raise self._conn
        return self._conn


def _linha(**over):
    # A última coluna é o DATEDIFF que o BANCO calcula (`parado_min`) — o
    # front-end desta função é a consulta real, e ela mede o tempo no MESMO
    # relógio que escreveu o carimbo (ver o defeito do -179 min).
    base = (1, "PENDENTE", None, 30, None, "conferir numero", "M123", 0, 0)
    campos = ["id", "estado", "aguardando_desde", "teto_minutos",
              "data_referencia", "motivo", "solicitado_por", "verificacoes",
              "parado_min"]
    valores = dict(zip(campos, base))
    valores.update(over)
    return tuple(valores[c] for c in campos)


# ═══════════════ 1. o caminho normal — 100% das execuções ════════════════════

def test_sem_pausa_o_portao_devolve_none(espera):
    """O teste que representa a produção inteira: nenhuma linha na tabela, o
    portão sai de imediato e o log_start segue como sempre."""
    conn = FakeConn(select=None)
    assert espera.portao(FakeHook(conn), "PIPE", "Etapa1", "20260803T060000") is None
    assert conn.commits == 0          # nada é escrito no caminho normal
    assert conn.fechada is True       # e a conexão não vaza


def test_tabela_ausente_abre_o_portao_com_aviso(espera, caplog):
    """Sem a migration 079 o portão DESLIGA — nunca derruba a DAG."""
    espera._avisou_ausente = False
    conn = FakeConn(erro=Exception("Invalid object name 'dbo.etl_etapa_pausa'."))
    assert espera.portao(FakeHook(conn), "PIPE", "Etapa1", "20260803T060000") is None
    assert any("079" in r.getMessage() for r in caplog.records)


def test_erro_de_banco_abre_o_portao(espera):
    """Erro transitório também degrada para 'segue' — a alternativa seria
    derrubar um pipeline de produção por causa do recurso novo."""
    conn = FakeConn(erro=Exception("Login timeout expired"))
    assert espera.portao(FakeHook(conn), "PIPE", "Etapa1", "20260803T060000") is None


def test_hook_quebrado_nao_derruba(espera):
    hook = FakeHook(Exception("connection refused"))
    assert espera.portao(hook, "PIPE", "Etapa1", "20260803T060000") is None


# ═════════════════════════ 2. a espera de verdade ════════════════════════════

def test_primeira_chegada_reagenda(espera):
    conn = FakeConn(select=_linha())
    with pytest.raises(_AirflowRescheduleException) as ex:
        espera.portao(FakeHook(conn), "PIPE", "Etapa1", "20260803T060000")
    assert ex.value.reschedule_date > datetime.now(timezone.utc)
    # carimbou a chegada (UPDATE) e gravou o evento de espera
    assert any("UPDATE dbo.etl_etapa_pausa" in s for s, _ in conn.sqls)
    assert conn.fechada is True


def test_primeira_chegada_nao_estoura_o_teto(espera):
    """Teto de 1 minuto com aguardando_desde ainda NULL: o relógio começa
    agora, não antes. Sem isso, toda pausa de teto curto morreria na chegada."""
    conn = FakeConn(select=_linha(teto_minutos=1, parado_min=None))
    with pytest.raises(_AirflowRescheduleException):
        espera.portao(FakeHook(conn), "PIPE", "Etapa1", "20260803T060000")


def test_espera_em_andamento_dentro_do_teto_reagenda(espera):
    conn = FakeConn(select=_linha(aguardando_desde=datetime(2026, 8, 3, 9, 50),
                                  teto_minutos=60, parado_min=10))
    with pytest.raises(_AirflowRescheduleException):
        espera.portao(FakeHook(conn), "PIPE", "Etapa1", "20260803T060000")


def test_liberada_segue(espera):
    """Liberar é sumir da consulta (o SELECT filtra estado='PENDENTE'): a
    etapa passa na verificação seguinte sem nenhum tratamento especial."""
    conn = FakeConn(select=None)
    assert espera.portao(FakeHook(conn), "PIPE", "Etapa1", "20260803T060000") is None


# ═══════════════════════ 3. o teto e o alerta ════════════════════════════════

def test_teto_estourado_falha_com_motivo(espera):
    conn = FakeConn(select=_linha(aguardando_desde=datetime(2026, 8, 3, 13, 59),
                                  teto_minutos=60, parado_min=61,
                                  data_referencia="2026-08-03"))
    with pytest.raises(_AirflowFailException) as ex:
        espera.portao(FakeHook(conn), "PIPE", "Etapa1", "20260803T060000")
    msg = str(ex.value)
    assert "Etapa1" in msg and "60 min" in msg and "reexecute" in msg
    assert any("estado = 'EXPIRADA'" in s for s, _ in conn.sqls)


def test_expirar_e_atomico(espera):
    """A transição carrega `AND estado = 'PENDENTE'`: o operador clicando
    Liberar no mesmo segundo não é sobrescrito pelo portão."""
    conn = FakeConn(rowcount=1)
    assert espera.expirar(conn, 7) is True
    sql = conn.sqls[-1][0]
    assert "AND estado = 'PENDENTE'" in sql


def test_expirar_perdeu_a_corrida(espera):
    conn = FakeConn(rowcount=0)
    assert espera.expirar(conn, 7) is False


def _stub_dependencias(monkeypatch, fn):
    """Troca `utils.dependencias` por um dublê — nos DOIS lugares.

    ``from utils import dependencias`` resolve por ATRIBUTO do pacote antes de
    olhar `sys.modules`, e outros testes desta suíte deixam `sys.modules['utils']`
    como MagicMock (os de factory stubam o Airflow e o utils inteiro). Trocar só
    a entrada de `sys.modules` passava sozinho e falhava na suíte completa — o
    tipo de teste que mente. Aqui o pacote é substituído por um módulo de
    verdade e o atributo é apontado para o dublê.
    """
    pacote = ModuleType("utils")
    falso = ModuleType("utils.dependencias")
    falso.gravar_evento = fn
    pacote.dependencias = falso
    monkeypatch.setitem(sys.modules, "utils", pacote)
    monkeypatch.setitem(sys.modules, "utils.dependencias", falso)


def test_evento_do_teto_usa_a_tabela_da_guardia(espera, monkeypatch):
    """O alerta sai pelo caminho da casa (etl_dependencia_evento, drenado ao
    Teams pela guardiã) — nenhum canal novo foi inventado."""
    chamadas = []
    _stub_dependencias(
        monkeypatch,
        lambda conn, p, d, t, det: chamadas.append((p, d, t, det)) or True)
    conn = FakeConn()
    assert espera.gravar_evento(conn, "PIPE", "2026-08-03",
                                espera.EVENTO_ESTOUROU, "detalhe") is True
    assert chamadas and chamadas[0][2] == "ESPERA_ESTOUROU"


def test_evento_sem_data_nao_grava(espera):
    assert espera.gravar_evento(FakeConn(), "PIPE", None, "X", "d") is False


def test_evento_que_falha_nao_derruba(espera, monkeypatch):
    def _boom(*a, **k):
        raise Exception("tabela de eventos fora do ar")
    _stub_dependencias(monkeypatch, _boom)
    assert espera.gravar_evento(FakeConn(), "PIPE", "2026-08-03", "X", "d") is False


# ═══════════════════ 4. configuração: teto e intervalo ═══════════════════════

def test_teto_da_linha_vence_a_variable(espera, monkeypatch):
    monkeypatch.setattr(espera, "_var_int", lambda *a, **k: 999)
    assert espera.teto_minutos({"teto_minutos": 45}) == 45


def test_teto_ausente_cai_na_variable(espera, monkeypatch):
    monkeypatch.setattr(espera, "_var_int", lambda *a, **k: 999)
    assert espera.teto_minutos({"teto_minutos": None}) == 999


def test_teto_fora_da_faixa_cai_na_variable(espera, monkeypatch):
    monkeypatch.setattr(espera, "_var_int", lambda *a, **k: 999)
    assert espera.teto_minutos({"teto_minutos": 0}) == 999
    assert espera.teto_minutos({"teto_minutos": 99999999}) == 999


@pytest.mark.parametrize("bruto,esperado", [
    (None, 60), ("", 60), ("abc", 60), ("5", 60), ("9999", 60), ("120", 120),
])
def test_intervalo_valida_a_variable(espera, monkeypatch, bruto, esperado):
    """Configuração errada não pode virar martelada de 1s nem espera eterna."""
    fake_var = SimpleNamespace(get=lambda nome, default_var=None: bruto)
    monkeypatch.setitem(sys.modules, "airflow.models",
                        SimpleNamespace(Variable=fake_var))
    assert espera.intervalo_segundos() == esperado


def test_variable_indisponivel_cai_no_padrao(espera, monkeypatch):
    class _Boom:
        @staticmethod
        def get(*a, **k):
            raise Exception("metastore fora do ar")
    monkeypatch.setitem(sys.modules, "airflow.models",
                        SimpleNamespace(Variable=_Boom))
    assert espera.intervalo_segundos() == espera.INTERVALO_PADRAO


# ═══════════════════════════ 5. detalhes de leitura ══════════════════════════

def test_consulta_filtra_estado_pendente(espera):
    conn = FakeConn(select=None)
    espera.pausa_pendente(conn, "PIPE", "20260803T060000", "Etapa1")
    sql, params = conn.sqls[-1]
    assert "estado = 'PENDENTE'" in sql
    assert params == ("PIPE", "20260803T060000", "Etapa1")
    assert sql.count("%s") == 3      # pymssql em dags/ — nunca '?'
    assert "?" not in sql


def test_data_do_evento_cai_no_ts_nodash(espera):
    assert espera.data_do_evento({}, "20260803T060000").isoformat() == "2026-08-03"


def test_data_do_evento_prefere_a_da_pausa(espera):
    assert espera.data_do_evento({"data_referencia": "2026-01-01"}, "20260803T0") \
        == "2026-01-01"


def test_data_do_evento_ts_invalido(espera):
    assert espera.data_do_evento({}, "lixo") is None


def test_teto_usa_excecao_que_o_airflow_nao_retenta(espera):
    """⛔ Sem isto o teto vira alerta INÓCUO.

    A factory emite `retries` no default_args (`int(retries_count or 1)`):
    quase todo pipeline tem retry. Como o teto marca a pausa EXPIRADA antes de
    falhar, um RuntimeError seria retentado, o portão não acharia mais pausa
    pendente e a etapa RODARIA — alerta emitido e execução seguindo, o oposto
    do que o §5 promete. AirflowFailException é tratada com force_fail=True.
    """
    assert isinstance(espera._falha_sem_retry("x"), _AirflowFailException)


def test_teto_degrada_para_runtimeerror_sem_airflow(espera, monkeypatch):
    """Sem o Airflow importável a falha continua acontecendo — só sem o
    superpoder de "não retentar". Levantar é o que não pode faltar."""
    exc = ModuleType("airflow.exceptions")
    monkeypatch.setitem(sys.modules, "airflow.exceptions", exc)
    assert isinstance(espera._falha_sem_retry("x"), RuntimeError)


def test_tempo_parado_vem_do_banco_nunca_do_worker(espera):
    """⛔ O defeito do "-179 min" (prova viva, dev 2026-08-03).

    `aguardando_desde` é escrito com GETDATE() do SQL Server; o worker roda em
    outro fuso (3h de diferença medidos neste dev). Subtrair um do outro dava
    tempo NEGATIVO — teto que nunca estoura e pipeline pendurado em silêncio.
    A consulta passa a trazer o DATEDIFF calculado pelo próprio banco.
    """
    conn = FakeConn(select=None)
    espera.pausa_pendente(conn, "P", "TS", "J")
    sql = conn.sqls[-1][0]
    assert "DATEDIFF(MINUTE, aguardando_desde, GETDATE())" in sql


def test_portao_nao_aceita_relogio_de_fora(espera):
    """Não há como injetar 'agora' no portão: a única fonte de tempo é o banco."""
    import inspect
    assert "agora" not in inspect.signature(espera.portao).parameters
