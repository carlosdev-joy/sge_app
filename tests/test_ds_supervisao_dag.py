"""
Carga da DAG etl_ds_supervisao_monitor com Airflow stubado.

Airflow não está instalado no ambiente de teste (as DAGs rodam no servidor), mas
o erro mais caro dessa fase é justamente o de *import time*: uma DAG que não
carrega no scheduler não aparece na lista e a supervisão fica muda sem ninguém
perceber. Este teste exercita o módulo inteiro — imports, leitura de Variables e
montagem do objeto DAG — com stubs, para esse erro aparecer aqui e não em
produção.

Também cobre a gravação de eventos com cursor falso: o INSERT ... WHERE NOT
EXISTS é o que garante 1 card por ocorrência, e a conferência contra
etl_ds_job_log é o que evita falso NAO_EXECUTOU quando o log rotaciona.
"""
from __future__ import annotations

import importlib.util
import sys
from datetime import date, datetime, time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_ROOT = Path(__file__).parent.parent
_DAGS = _ROOT / "dags"
if str(_DAGS) not in sys.path:
    sys.path.insert(0, str(_DAGS))

_STUBS = [
    "airflow", "airflow.models", "airflow.operators", "airflow.operators.python",
    "airflow.providers", "airflow.providers.ssh", "airflow.providers.ssh.hooks",
    "airflow.providers.ssh.hooks.ssh",
    "airflow.providers.microsoft", "airflow.providers.microsoft.mssql",
    "airflow.providers.microsoft.mssql.hooks", "airflow.providers.microsoft.mssql.hooks.mssql",
    "pendulum",
]
for _m in _STUBS:
    sys.modules.setdefault(_m, MagicMock())

# `with DAG(...) as dag:` exige um context manager de verdade.
sys.modules["airflow"].DAG = MagicMock()
sys.modules["airflow"].DAG.return_value.__enter__ = lambda self: self
sys.modules["airflow"].DAG.return_value.__exit__ = lambda self, *a: False


def _carregar_dag():
    spec = importlib.util.spec_from_file_location(
        "etl_ds_supervisao_monitor_test", _DAGS / "etl_ds_supervisao_monitor.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


DAG_MOD = _carregar_dag()

from utils.ds_supervisao_regras import (  # noqa: E402
    ATRASO, NAO_EXECUTOU, JobSupervisionado, EventoDetectado,
)


def _job(**kw) -> JobSupervisionado:
    base = dict(id=7, project="BI_CVP", job_name="SeqSsdVida7Peps",
                janela_inicio=time(2, 0), janela_fim=time(3, 0), tolerancia_min=0,
                dias_semana="1,2,3,4,5", vigencia_inicio=date(2026, 7, 1))
    base.update(kw)
    return JobSupervisionado(**base)


# ── Carga do módulo ─────────────────────────────────────────────────────────

def test_dag_carrega_sem_erro():
    assert DAG_MOD.DAG_ID == "etl_ds_supervisao_monitor"


def test_dag_usa_fuso_de_sao_paulo():
    assert DAG_MOD.LOCAL_TZ == "America/Sao_Paulo"


def test_janela_de_log_e_de_sete_dias():
    assert DAG_MOD.DIAS_DE_LOG == 7


def test_allowlist_do_comando_remoto_e_a_mesma_do_console():
    assert DAG_MOD._SAFE_DS_RE.match("BI_CVP") is not None
    assert DAG_MOD._SAFE_DS_RE.match("Seq.Job_1") is not None
    for perigoso in ("com espaço", "job;rm -rf /", "job$(id)", "job|cat", "job&&ls"):
        assert DAG_MOD._SAFE_DS_RE.match(perigoso) is None


def test_var_int_le_o_valor_configurado(monkeypatch):
    monkeypatch.setattr(DAG_MOD.Variable, "get", lambda *a, **k: "5")
    assert DAG_MOD._var_int("DS_SUPERVISAO_INTERVAL_MINUTES", 15) == 5


def test_var_int_cai_no_default_em_valor_nao_numerico(monkeypatch):
    # Variable configurada errado no Airflow não pode derrubar a DAG na carga.
    monkeypatch.setattr(DAG_MOD.Variable, "get", lambda *a, **k: "a cada 15 min")
    assert DAG_MOD._var_int("DS_SUPERVISAO_INTERVAL_MINUTES", 15) == 15


def test_var_cai_no_default_quando_a_variable_nao_existe(monkeypatch):
    def _explode(*a, **k):
        raise KeyError("Variable DS_MONITOR_SSH_CONN_ID does not exist")

    monkeypatch.setattr(DAG_MOD.Variable, "get", _explode)
    assert DAG_MOD._var("DS_MONITOR_SSH_CONN_ID", "ssh_lnxprd021") == "ssh_lnxprd021"


# ── Gravação de eventos ─────────────────────────────────────────────────────

class CursorFalso:
    """Cursor mínimo: guarda os SQL executados e simula rowcount."""

    def __init__(self, rowcount: int = 1, fetch=None):
        self.sqls: list[tuple[str, tuple]] = []
        self.rowcount = rowcount
        self._fetch = fetch

    def execute(self, sql, params=()):
        self.sqls.append((" ".join(sql.split()), tuple(params)))

    def fetchone(self):
        return self._fetch


def test_evento_novo_e_inserido_com_guarda_de_duplicidade():
    cur = CursorFalso(rowcount=1)
    ev = EventoDetectado(tipo=ATRASO, data_ref=date(2026, 7, 27), detalhe="atrasou")
    novos = DAG_MOD._gravar_eventos(cur, _job(), [ev], MagicMock())

    assert novos == 1
    sql, _params = cur.sqls[0]
    # É o WHERE NOT EXISTS que substitui o tratamento de chave duplicada.
    assert "INSERT INTO dbo.etl_ds_supervisao_evento" in sql
    assert "WHERE NOT EXISTS" in sql


def test_evento_repetido_nao_conta_como_novo():
    # rowcount 0 = o WHERE NOT EXISTS barrou: o mesmo problema já estava gravado.
    cur = CursorFalso(rowcount=0)
    ev = EventoDetectado(tipo=ATRASO, data_ref=date(2026, 7, 27), detalhe="atrasou")
    assert DAG_MOD._gravar_eventos(cur, _job(), [ev], MagicMock()) == 0


def test_nao_executou_e_descartado_se_o_orquestra_registrou_execucao():
    # etl_ds_job_log tem linha do dia → o log do DataStage rotacionou, o job rodou.
    cur = CursorFalso(rowcount=1, fetch=(1,))
    ev = EventoDetectado(tipo=NAO_EXECUTOU, data_ref=date(2026, 7, 27), detalhe="não rodou")
    assert DAG_MOD._gravar_eventos(cur, _job(), [ev], MagicMock()) == 0
    assert all("INSERT" not in sql for sql, _ in cur.sqls)


def test_nao_executou_e_gravado_quando_nao_ha_registro_no_orquestra():
    cur = CursorFalso(rowcount=1, fetch=None)
    ev = EventoDetectado(tipo=NAO_EXECUTOU, data_ref=date(2026, 7, 27), detalhe="não rodou")
    assert DAG_MOD._gravar_eventos(cur, _job(), [ev], MagicMock()) == 1


def test_falha_ao_gravar_um_evento_nao_derruba_os_outros():
    class CursorQuebrado(CursorFalso):
        def execute(self, sql, params=()):
            super().execute(sql, params)
            if "atrasou" in str(params):
                raise RuntimeError("deadlock")

    cur = CursorQuebrado(rowcount=1)
    eventos = [
        EventoDetectado(tipo=ATRASO, data_ref=date(2026, 7, 27), detalhe="atrasou"),
        EventoDetectado(tipo=ATRASO, data_ref=date(2026, 7, 26), detalhe="outro"),
    ]
    assert DAG_MOD._gravar_eventos(cur, _job(), eventos, MagicMock()) == 1


# ── Conferência contra a telemetria do Orquestra ────────────────────────────

def test_rodou_pelo_orquestra_degrada_para_falso_em_erro():
    class CursorExplode(CursorFalso):
        def execute(self, sql, params=()):
            raise RuntimeError("tabela ausente")

    # Deixar de avisar é pior que avisar demais: na dúvida, o alerta segue.
    assert DAG_MOD._rodou_pelo_orquestra(CursorExplode(), _job(), date(2026, 7, 27)) is False


# ── Gravação de runs ────────────────────────────────────────────────────────

def test_run_existente_faz_update_e_nao_duplica():
    from utils.ds_logsum import OK, DsRun

    cur = CursorFalso(rowcount=1)          # UPDATE encontrou linha
    r = DsRun(inicio=datetime(2026, 7, 27, 2, 10), fim=datetime(2026, 7, 27, 2, 50),
              resultado=OK, jobs_filhos=2)
    assert DAG_MOD._gravar_runs(cur, 7, [r], _job(), MagicMock()) == 1
    assert len(cur.sqls) == 1
    assert cur.sqls[0][0].startswith("UPDATE dbo.etl_ds_supervisao_run")


def test_run_novo_cai_no_insert_depois_do_update_vazio():
    from utils.ds_logsum import OK, DsRun

    cur = CursorFalso(rowcount=0)          # UPDATE não achou nada
    r = DsRun(inicio=datetime(2026, 7, 27, 2, 10), fim=datetime(2026, 7, 27, 2, 50),
              resultado=OK, jobs_filhos=2)
    DAG_MOD._gravar_runs(cur, 7, [r], _job(), MagicMock())
    assert len(cur.sqls) == 2
    assert "INSERT INTO dbo.etl_ds_supervisao_run" in cur.sqls[1][0]


def test_run_de_madrugada_e_gravado_no_dia_da_janela():
    from utils.ds_logsum import OK, DsRun

    cur = CursorFalso(rowcount=1)
    j = _job(janela_inicio=time(23, 0), janela_fim=time(1, 0))
    r = DsRun(inicio=datetime(2026, 7, 28, 0, 30), fim=datetime(2026, 7, 28, 0, 50),
              resultado=OK, jobs_filhos=1)
    DAG_MOD._gravar_runs(cur, 7, [r], j, MagicMock())
    _sql, params = cur.sqls[0]
    # data_ref do UPDATE é a segunda (27), dia em que a janela começou.
    assert date(2026, 7, 27) in params


def test_run_sem_hora_e_ignorado():
    from utils.ds_logsum import DsRun

    cur = CursorFalso(rowcount=1)
    assert DAG_MOD._gravar_runs(cur, 7, [DsRun(inicio=None)], _job(), MagicMock()) == 0
    assert cur.sqls == []


# ── Expurgo ─────────────────────────────────────────────────────────────────

def test_expurgo_apaga_run_e_evento_mas_nao_o_cadastro():
    cur = CursorFalso(rowcount=3)
    DAG_MOD._expurgar(cur, 365, MagicMock())
    tabelas = [sql for sql, _ in cur.sqls]
    assert any("etl_ds_supervisao_run" in s for s in tabelas)
    assert any("etl_ds_supervisao_evento" in s for s in tabelas)
    assert not any("etl_ds_supervisao_job" in s for s in tabelas)


@pytest.mark.parametrize("retencao", [90, 365])
def test_expurgo_usa_a_retencao_configurada(retencao):
    cur = CursorFalso(rowcount=0)
    DAG_MOD._expurgar(cur, retencao, MagicMock())
    _sql, params = cur.sqls[0]
    corte = params[0]
    assert (date.today() - corte).days == retencao


# ── Notificação ao Teams (F4) ───────────────────────────────────────────────

def _linha_pendente(eid=1, tipo="ABORTOU", webhook="https://webhook/SEGREDO", canal="Homologação"):
    # Espelha o SELECT de _notificar_pendentes.
    return (eid, tipo, "2026-07-27", "detalhe", "mensagem pronta",
            "BI_CVP", "SeqVida", "Carga de vida", "02:00:00", "03:00:00",
            webhook, canal)


class CursorFila(CursorFalso):
    """Cursor cujo fetchall devolve a fila de pendentes uma única vez."""

    def __init__(self, pendentes, rowcount=1):
        super().__init__(rowcount=rowcount)
        self._pendentes = list(pendentes)

    def fetchall(self):
        fila, self._pendentes = self._pendentes, []
        return fila


def _patch_envio(monkeypatch, ok=True, motivo="HTTP 200"):
    chamadas = []

    def _fake(webhook, card, timeout=15):
        chamadas.append((webhook, card))
        return ok, motivo

    import utils.ds_teams as ds_teams
    monkeypatch.setattr(ds_teams, "enviar_card", _fake)
    return chamadas


def test_envio_bem_sucedido_marca_notificado_em(monkeypatch):
    chamadas = _patch_envio(monkeypatch, ok=True)
    cur = CursorFila([_linha_pendente()])
    enviados = DAG_MOD._notificar_pendentes(cur, MagicMock())

    assert enviados == 1
    assert len(chamadas) == 1
    updates = [s for s, _ in cur.sqls if s.startswith("UPDATE dbo.etl_ds_supervisao_evento")]
    assert len(updates) == 1
    assert "notificado_em = GETDATE()" in updates[0]


def test_falha_de_envio_nao_marca_notificado_em(monkeypatch):
    # É o que garante o reenvio no ciclo seguinte.
    _patch_envio(monkeypatch, ok=False, motivo="webhook respondeu HTTP 500")
    cur = CursorFila([_linha_pendente()])
    enviados = DAG_MOD._notificar_pendentes(cur, MagicMock())

    assert enviados == 0
    assert not any(s.startswith("UPDATE") for s, _ in cur.sqls)


def test_motivo_da_falha_vai_ao_log_sem_a_url(monkeypatch):
    _patch_envio(monkeypatch, ok=False, motivo="webhook respondeu HTTP 500")
    log = MagicMock()
    DAG_MOD._notificar_pendentes(CursorFila([_linha_pendente()]), log)

    registrado = " ".join(str(c) for c in log.warning.call_args_list)
    assert "SEGREDO" not in registrado
    assert "Homologação" in registrado          # o canal é citado pelo NOME


def test_sem_pendentes_nao_chama_o_webhook(monkeypatch):
    chamadas = _patch_envio(monkeypatch)
    assert DAG_MOD._notificar_pendentes(CursorFila([]), MagicMock()) == 0
    assert chamadas == []


def test_query_de_pendentes_filtra_canal_ativo_e_nao_notificado(monkeypatch):
    _patch_envio(monkeypatch)
    cur = CursorFila([])
    DAG_MOD._notificar_pendentes(cur, MagicMock(), limite=10, janela_dias=3)
    sql, params = cur.sqls[0]

    assert "e.notificado_em IS NULL" in sql
    assert "g.ativo = 1" in sql
    assert "webhook_url IS NOT NULL" in sql
    assert params == (10, 3)                   # limite do lote e janela de dias


def test_lote_cheio_e_registrado_em_vez_de_truncar_calado(monkeypatch):
    _patch_envio(monkeypatch)
    log = MagicMock()
    pendentes = [_linha_pendente(eid=i) for i in range(3)]
    DAG_MOD._notificar_pendentes(CursorFila(pendentes), log, limite=3)

    registrado = " ".join(str(c) for c in log.info.call_args_list)
    assert "próximo ciclo" in registrado


def test_erro_ao_listar_pendentes_nao_derruba_o_ciclo(monkeypatch):
    _patch_envio(monkeypatch)

    class CursorQuebrado(CursorFalso):
        def execute(self, sql, params=()):
            raise RuntimeError("timeout no banco")

    assert DAG_MOD._notificar_pendentes(CursorQuebrado(), MagicMock()) == 0


def test_falha_ao_gravar_notificado_em_nao_interrompe_o_lote(monkeypatch):
    _patch_envio(monkeypatch, ok=True)

    class CursorUpdateQuebrado(CursorFila):
        def execute(self, sql, params=()):
            super().execute(sql, params)
            if sql.strip().upper().startswith("UPDATE"):
                raise RuntimeError("deadlock")

    cur = CursorUpdateQuebrado([_linha_pendente(eid=1), _linha_pendente(eid=2)])
    # Enviou os dois; nenhum marcado — o próximo ciclo reenvia (duplicar é
    # ruim, perder é pior) e o log guarda o rastro.
    assert DAG_MOD._notificar_pendentes(cur, MagicMock()) == 0
