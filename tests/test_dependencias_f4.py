"""
Testes da F4 de docs/spec-dependencias-pipelines.md — guardiã, janela e alertas.

Airflow stubado via sys.modules; as regras da guardiã são puras e o ciclo é
exercitado com hook falso.
"""
from __future__ import annotations

import importlib.util
import sys
from datetime import date, datetime, time
from pathlib import Path
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


def _load(name, relpath):
    spec = importlib.util.spec_from_file_location(name, _ROOT / relpath)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def dep():
    return _load("dependencias_f4_test", "dags/utils/dependencias.py")


@pytest.fixture(scope="module")
def guardia():
    return _load("guardia_test", "dags/etl_dependencia_guardia.py")


# ────────────────────────────── Janela estourada ───────────────────────────

def test_sem_limite_nunca_estoura(dep):
    """Deadline é opt-in (decisão do usuário): sem valor, não alerta."""
    assert dep.passou_do_limite(None, datetime(2026, 8, 1, 23, 59)) is False
    assert dep.precisa_alertar_janela(None, datetime(2026, 8, 1, 23, 59),
                                      "AGUARDANDO_DEPENDENCIA") is False


def test_antes_do_limite_nao_alerta(dep):
    assert dep.precisa_alertar_janela(time(11, 0), datetime(2026, 8, 1, 10, 30),
                                      "AGUARDANDO_DEPENDENCIA") is False


def test_depois_do_limite_ainda_parado_alerta(dep):
    assert dep.precisa_alertar_janela(time(11, 0), datetime(2026, 8, 1, 11, 1),
                                      "AGUARDANDO_DEPENDENCIA") is True


def test_corrida_nem_ordenada_tambem_alerta(dep):
    """Nenhum predecessor rodou o dia inteiro — o silêncio do defeito 5."""
    assert dep.precisa_alertar_janela(time(11, 0), datetime(2026, 8, 1, 12, 0),
                                      None) is True


def test_corrida_que_ja_saiu_nao_alerta(dep):
    for status in ("EXECUTANDO", "SUCESSO", "FALHA", "PULADO"):
        assert dep.precisa_alertar_janela(time(11, 0), datetime(2026, 8, 1, 12, 0),
                                          status) is False, status


def test_limite_como_texto_do_banco(dep):
    assert dep.passou_do_limite("11:00:00", datetime(2026, 8, 1, 11, 30)) is True
    assert dep.passou_do_limite("11:00", datetime(2026, 8, 1, 10, 0)) is False


# ─────────────────────────── Data de referência divergente ─────────────────

def test_divergencia_detectada(dep):
    """O insumo existe, só que carimbado com outro dia."""
    status = {"PAI_A": "SUCESSO", "PAI_B": None}
    datas = {"PAI_B": "2026-07-31"}
    assert dep.detectar_divergencia(status, datas) == [("PAI_B", "2026-07-31")]


def test_sem_execucao_em_lugar_nenhum_nao_e_divergencia(dep):
    """Predecessor que simplesmente não rodou é 'não liberou', não divergência."""
    assert dep.detectar_divergencia({"PAI_B": None}, {}) == []


def test_predecessor_ok_na_data_nao_entra(dep):
    assert dep.detectar_divergencia({"PAI_A": "SUCESSO"}, {"PAI_A": "2026-07-30"}) == []


# ───────────────────────────────── Card ────────────────────────────────────

def test_card_cita_pipeline_e_data(guardia):
    card = guardia.montar_card({
        "tipo": "JANELA_ESTOUROU", "pipeline": "PIPE_C", "data_ref": "2026-08-01",
        "detalhe": "Não liberou até 11:00: PIPE_B", "detectado_em": "2026-08-01 11:05:00",
    })
    texto = str(card)
    assert "PIPE_C" in texto and "2026-08-01" in texto and "PIPE_B" in texto
    assert card["attachments"][0]["content"]["type"] == "AdaptiveCard"


def test_card_de_tipo_desconhecido_nao_quebra(guardia):
    card = guardia.montar_card({"tipo": "COISA_NOVA", "pipeline": "P"})
    assert card["attachments"][0]["content"]["body"]


# ──────────────────────────── Ciclo da guardiã ─────────────────────────────

class FakeHook:
    """Hook falso: responde às consultas pelo trecho de SQL."""

    def __init__(self, dependentes, status_preds, execucao=None, datas_outras=None):
        self.dependentes = dependentes
        self.status_preds = status_preds
        self.execucao = execucao
        self.datas_outras = datas_outras or []
        self.escritas = []

    def get_records(self, sql, parameters=None):
        if "etl_pipeline_dependencia d ON" in sql:
            return [(d["nome"], d.get("hora_virada"), d.get("nao_iniciar_antes"),
                     d.get("hora_limite")) for d in self.dependentes]
        if "d.depende_de" in sql:
            return [(k, v) for k, v in self.status_preds.items()]
        if "DISTINCT CONVERT(VARCHAR(10), data_referencia" in sql:
            return [(d,) for d in self.datas_outras]
        if "etl_dependencia_evento WHERE notificado_em" in sql:
            return []
        return []

    def get_first(self, sql, parameters=None):
        if "dependencia_hora_virada" in sql:
            return ("00:00",)
        if "TOP 1 status FROM dbo.etl_pipeline_execucao" in sql:
            return (self.execucao,) if self.execucao else None
        if "etl_msg_grupo" in sql:
            return None
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


def _rodar(guardia, hook, monkeypatch, agora):
    """Roda um ciclo com o relógio fixado.

    `pendulum` é stub neste ambiente, então o módulo inteiro é trocado por um
    objeto cujo now() devolve um datetime real — que já tem year/month/day e
    .time(), tudo que o ciclo usa.
    """
    from types import SimpleNamespace

    monkeypatch.setattr(guardia, "MsSqlHook", lambda **kw: hook)
    monkeypatch.setattr(guardia, "pendulum", SimpleNamespace(now=lambda tz=None: agora))
    return guardia.guardar()


def test_ordena_a_corrida_quando_um_predecessor_ja_rodou(guardia, monkeypatch):
    """A linha do dia nasce quando a corrida começou em algum predecessor."""
    hook = FakeHook(
        dependentes=[{"nome": "PIPE_C", "hora_virada": None,
                      "nao_iniciar_antes": None, "hora_limite": None}],
        status_preds={"PAI_A": "SUCESSO", "PAI_B": None},
        execucao=None)
    _rodar(guardia, hook, monkeypatch, datetime(2026, 8, 1, 10, 0))
    inseriu = [s for s, _ in hook.escritas if "INSERT INTO dbo.etl_pipeline_execucao" in s]
    assert inseriu, "corrida nao foi ordenada"
    assert "AGUARDANDO_DEPENDENCIA" in inseriu[0]


def test_nao_ordena_quando_nenhum_predecessor_rodou(guardia, monkeypatch):
    """Sem corrida iniciada, não inventa linha — evita ordenar dia não previsto."""
    hook = FakeHook(
        dependentes=[{"nome": "PIPE_C", "hora_virada": None,
                      "nao_iniciar_antes": None, "hora_limite": None}],
        status_preds={"PAI_A": None, "PAI_B": None},
        execucao=None)
    _rodar(guardia, hook, monkeypatch, datetime(2026, 8, 1, 10, 0))
    assert not [s for s, _ in hook.escritas if "INSERT INTO dbo.etl_pipeline_execucao" in s]


def test_dispara_quando_o_push_do_predecessor_nao_chegou(guardia, monkeypatch):
    hook = FakeHook(
        dependentes=[{"nome": "PIPE_C", "hora_virada": None,
                      "nao_iniciar_antes": None, "hora_limite": None}],
        status_preds={"PAI_A": "SUCESSO", "PAI_B": "SUCESSO"},
        execucao="AGUARDANDO_DEPENDENCIA")
    _rodar(guardia, hook, monkeypatch, datetime(2026, 8, 1, 10, 0))
    tomou = [s for s, _ in hook.escritas if "status='EXECUTANDO'" in s]
    assert tomou, "guardia nao cobriu o push perdido"
    assert "status='AGUARDANDO_DEPENDENCIA'" in tomou[0], "faltou a protecao de corrida"


def test_nao_dispara_antes_da_janela(guardia, monkeypatch):
    """Liberado às 07:00 com janela 08:00: a guardiã espera."""
    hook = FakeHook(
        dependentes=[{"nome": "PIPE_C", "hora_virada": None,
                      "nao_iniciar_antes": "08:00:00", "hora_limite": None}],
        status_preds={"PAI_A": "SUCESSO"},
        execucao="AGUARDANDO_DEPENDENCIA")
    _rodar(guardia, hook, monkeypatch, datetime(2026, 8, 1, 7, 0))
    assert not [s for s, _ in hook.escritas if "status='EXECUTANDO'" in s]


def test_janela_estourada_gera_evento_e_nao_falha_o_pipeline(guardia, monkeypatch):
    hook = FakeHook(
        dependentes=[{"nome": "PIPE_C", "hora_virada": None,
                      "nao_iniciar_antes": None, "hora_limite": "11:00:00"}],
        status_preds={"PAI_A": "SUCESSO", "PAI_B": None},
        execucao="AGUARDANDO_DEPENDENCIA")
    _rodar(guardia, hook, monkeypatch, datetime(2026, 8, 1, 11, 30))
    eventos = [p for s, p in hook.escritas if "INSERT INTO dbo.etl_dependencia_evento" in s]
    assert eventos, "evento de janela nao gravado"
    assert eventos[0][2] == "JANELA_ESTOUROU"
    assert "PAI_B" in eventos[0][3]
    # Em nenhum momento a corrida é marcada como FALHA.
    assert not [s for s, _ in hook.escritas if "'FALHA'" in s]


def test_um_pipeline_com_erro_nao_para_a_varredura(guardia, monkeypatch):
    """Malha grande: um pipeline problemático não pode cegar os outros.

    O erro é injetado na consulta de predecessores do RUIM — não em um valor
    tolerado pelo parser, senão o `except` do laço nunca seria exercitado.
    """
    class HookQueFalhaNoRuim(FakeHook):
        def get_records(self, sql, parameters=None):
            if "d.depende_de" in sql and parameters and parameters[1] == "RUIM":
                raise RuntimeError("timeout na consulta do RUIM")
            return super().get_records(sql, parameters)

    hook = HookQueFalhaNoRuim(
        dependentes=[{"nome": "RUIM", "hora_virada": None, "nao_iniciar_antes": None,
                      "hora_limite": None},
                     {"nome": "PIPE_C", "hora_virada": None, "nao_iniciar_antes": None,
                      "hora_limite": None}],
        status_preds={"PAI_A": "SUCESSO"},
        execucao="AGUARDANDO_DEPENDENCIA")
    resultado = _rodar(guardia, hook, monkeypatch, datetime(2026, 8, 1, 10, 0))
    assert resultado["pipelines"] == 2
    # O RUIM estourou, mas o PIPE_C foi processado assim mesmo.
    assert resultado["disparados"] == 1


def test_sem_a_migration_o_ciclo_termina_limpo(guardia, monkeypatch):
    hook = MagicMock()
    hook.get_records.side_effect = RuntimeError("Invalid object name")
    monkeypatch.setattr(guardia, "MsSqlHook", lambda **kw: hook)
    assert guardia.guardar() == {"pipelines": 0}
