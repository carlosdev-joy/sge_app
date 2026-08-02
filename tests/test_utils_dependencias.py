"""
F3 — utils/dependencias.py: predicados puros e protocolo de claim
(docs/retomada-f3-desenho.md §§3 e 6; suíte docs/retomada-aceitacao.md).

O módulo é a fonte única dos predicados de dependência: `dia_permitido`
(regras de DIA — D04/D05), `liberado` (contrato EXISTS — D14/D20/D21),
`reservar_corrida`/`ordenar_corrida`/`devolver_reserva` (claim por rowcount
com anti-corrida serializable — D13/D16/D18) e `montar_conf`/`novo_run_id`
(herança do ODATE + run_id que nasce antes da reserva).

Parte pura roda sem banco; parte de banco usa conn/cursor STUBADOS que
gravam cada SQL executada — o que se testa aqui é o protocolo (que SQL, com
que guardas, devolvendo o quê), não o SQL Server.
"""
from __future__ import annotations

import importlib.util
import json
import re
import sys
from datetime import date, datetime, time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

_AIRFLOW_STUBS = [
    "airflow", "airflow.models", "airflow.operators", "airflow.operators.python",
    "airflow.operators.empty", "airflow.datasets", "airflow.utils",
    "airflow.utils.trigger_rule", "airflow.utils.state",
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
def dep():
    return _load_module("utils_dependencias_test", "dags/utils/dependencias.py")


@pytest.fixture(scope="module")
def factory():
    return _load_module("etl_dag_factory_deps_test", "dags/etl_dag_factory.py")


# ───────────────────────── conn/cursor stubados ─────────────────────────────

class _Cursor:
    """Cursor pymssql de mentira: roteiro de respostas por execute, na ordem.

    Cada item do roteiro é {'rows': [...], 'rowcount': n} (ou uma exceção,
    que é levantada). Toda SQL executada fica em `execs` normalizada."""

    def __init__(self, roteiro=None):
        self.roteiro = list(roteiro or [])
        self.execs = []              # (sql normalizada, params)
        self._rows = []
        self.rowcount = -1

    def execute(self, sql, params=None):
        s = " ".join(str(sql).split())
        self.execs.append((s, params))
        passo = self.roteiro.pop(0) if self.roteiro else {}
        if isinstance(passo, Exception):
            raise passo
        self._rows = list(passo.get("rows", []))
        self.rowcount = passo.get("rowcount", -1)

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)


def _conn(roteiro=None):
    cur = _Cursor(roteiro)
    return SimpleNamespace(cursor=lambda: cur, _cur=cur)


# ═══════════════ 1. cron-dow → weekday (D05: domingo é domingo) ═════════════

def test_cron_dow_para_weekday_explicita(dep):
    """0 E 7 são domingo (weekday 6); 1 é segunda (weekday 0). O padrão
    int(x or 1) da 1ª execução transformava domingo em segunda."""
    assert dep.cron_dow_para_weekday(0) == 6
    assert dep.cron_dow_para_weekday(7) == 6
    assert dep.cron_dow_para_weekday(1) == 0
    assert dep.cron_dow_para_weekday(6) == 5


# ═════════════════ 2. matriz do dia_permitido (D04/D05) ═════════════════════

_DOMINGO = date(2026, 8, 2)
_SEGUNDA = date(2026, 8, 3)
_SABADO = date(2026, 8, 1)
_SEXTA = date(2026, 7, 31)


def test_weekly_dow_zero_e_domingo(dep):
    regras = {"schedule_type": "weekly", "schedule_dow": 0}
    assert dep.dia_permitido(regras, _DOMINGO) == (True, None)
    ok, motivo = dep.dia_permitido(regras, _SEGUNDA)
    assert ok is False and "fora do dia da semana agendado" in motivo


def test_weekly_sem_dow_usa_o_default_do_cron(dep):
    """dow ausente → segunda (o MESMO default do cron gerado), derivado com
    `is not None` — nunca int(x or 1)."""
    regras = {"schedule_type": "weekly", "schedule_dow": None}
    assert dep.dia_permitido(regras, _SEGUNDA)[0] is True
    assert dep.dia_permitido(regras, _DOMINGO)[0] is False


def test_monthly_so_no_dia_do_mes(dep):
    regras = {"schedule_type": "monthly", "schedule_dom": 5}
    assert dep.dia_permitido(regras, date(2026, 8, 5)) == (True, None)
    ok, motivo = dep.dia_permitido(regras, date(2026, 8, 30))
    assert ok is False and motivo == "dia 30 fora do agendamento mensal (dia 5)"


def test_biweekly_d_e_d_mais_15(dep):
    regras = {"schedule_type": "biweekly", "schedule_dom": 3}
    assert dep.dia_permitido(regras, date(2026, 8, 3))[0] is True
    assert dep.dia_permitido(regras, date(2026, 8, 18))[0] is True
    ok, motivo = dep.dia_permitido(regras, date(2026, 8, 4))
    assert ok is False and "quinzenal (dias 3 e 18)" in motivo


def test_dias_semana_csv_com_zero_e_range(dep):
    # '0' = domingo no CSV do cron
    assert dep.dia_permitido({"dias_semana": "0"}, _DOMINGO)[0] is True
    assert dep.dia_permitido({"dias_semana": "0"}, _SEGUNDA)[0] is False
    # range '1-5' = segunda a sexta
    assert dep.dia_permitido({"dias_semana": "1-5"}, _SEXTA)[0] is True
    ok, motivo = dep.dia_permitido({"dias_semana": "1-5"}, _SABADO)
    assert ok is False and "fora dos dias da semana configurados" in motivo
    # '*' e vazio: sem restrição
    assert dep.dia_permitido({"dias_semana": "*"}, _SABADO)[0] is True
    assert dep.dia_permitido({"dias_semana": ""}, _SABADO)[0] is True


def test_dias_do_mes_de_monthly_days_times(dep):
    """O outro tipo que a correção A esqueceu (D04): a parte de DIA do
    dias_horarios_mes sobrevive como lista de dias."""
    regras = {"schedule_type": "monthly_days_times",
              "dias_horarios_mes_dias": [1, 15]}
    assert dep.dia_permitido(regras, date(2026, 8, 1))[0] is True
    assert dep.dia_permitido(regras, date(2026, 8, 15))[0] is True
    ok, motivo = dep.dia_permitido(regras, date(2026, 8, 2))
    assert ok is False and motivo == "dia 2 fora dos dias do mes configurados"


def test_somente_dias_uteis_soma_com_as_demais(dep):
    """Fim de semana bloqueia com o MESMO motivo do check_agenda (D58), e é
    um AND com a restrição de agendamento."""
    ok, motivo = dep.dia_permitido({"somente_dias_uteis": True}, _SABADO)
    assert ok is False and motivo == "fim de semana e pipeline somente dias uteis"
    # weekly domingo + dias úteis: passa no weekly, cai no dias úteis
    regras = {"schedule_type": "weekly", "schedule_dow": 0,
              "somente_dias_uteis": True}
    ok, motivo = dep.dia_permitido(regras, _DOMINGO)
    assert ok is False and motivo == "fim de semana e pipeline somente dias uteis"


def test_sem_restricao_permite_qualquer_dia(dep):
    assert dep.dia_permitido({}, _SABADO) == (True, None)
    assert dep.dia_permitido(None, _DOMINGO) == (True, None)
    assert dep.dia_permitido({"schedule_type": "daily"}, _SEGUNDA) == (True, None)


# ═══════════ 3. montar_conf e novo_run_id (herança + contrato F2) ═══════════

def test_montar_conf_serializa_as_tres_chaves(dep):
    conf = dep.montar_conf(date(2026, 8, 1), date(2026, 7, 31), "PIPE_PAI")
    assert conf == {"data_referencia": "2026-08-01",
                    "dia_operacional": "2026-07-31",
                    "disparado_por": "PIPE_PAI"}


def test_novo_run_id_formato_e_limite(dep):
    """dep__{data}__{pai[:60]}__{carimbo}: ≤ 250 (VARCHAR da 072) mesmo com
    nome de pai enorme; truncagem é em 60, nunca em 50 (colidiria prefixos
    no índice único)."""
    rid = dep.novo_run_id("dep", date(2026, 8, 1), "PIPE_PAI")
    assert rid.startswith("dep__2026-08-01__PIPE_PAI__")
    assert re.fullmatch(r"dep__2026-08-01__PIPE_PAI__\d{8}T\d{12}", rid)
    gigante = "P" * 200
    rid2 = dep.novo_run_id("dep", date(2026, 8, 1), gigante)
    assert len(rid2) <= 250
    assert ("P" * 60 + "__") in rid2 and ("P" * 61) not in rid2
    # prefixo reservado à F4
    assert dep.novo_run_id("guardia", date(2026, 8, 1), "X").startswith("guardia__")


def test_sem_truncagem_em_50_no_modulo(dep):
    fonte = (_ROOT / "dags/utils/dependencias.py").read_text(encoding="utf-8")
    assert "[:50]" not in fonte


# ═════════════ 4. liberado — contrato EXISTS (D14/D20/D21) ══════════════════

def test_liberado_todas_com_sucesso(dep):
    conn = _conn([{"rows": []}])
    assert dep.liberado(conn, "PIPE_C", date(2026, 8, 1)) == (True, [])
    sql, params = conn._cur.execs[0]
    assert "NOT EXISTS" in sql and "status = 'SUCESSO'" in sql
    assert "tipo = 'PIPELINE'" in sql
    assert params == ("PIPE_C", date(2026, 8, 1))


def test_liberado_devolve_os_faltantes(dep):
    """FALHA/EXECUTANDO/PULADO/ausência/SUCESSO em outra data são todos o
    mesmo caso para o predicado: NÃO existe SUCESSO na data → faltante."""
    conn = _conn([{"rows": [("PIPE_A",), ("PIPE_B",)]}])
    assert dep.liberado(conn, "PIPE_C", date(2026, 8, 1)) == (False, ["PIPE_A", "PIPE_B"])


def test_liberado_excecao_nao_vira_pode_disparar(dep, capsys):
    """D21: erro de consulta → NÃO liberado, com log [DEP]."""
    conn = _conn([RuntimeError("banco fora")])
    ok, faltantes = dep.liberado(conn, "PIPE_C", date(2026, 8, 1))
    assert ok is False
    assert faltantes and faltantes[0].startswith("erro na consulta:")
    assert "[DEP]" in capsys.readouterr().out


def test_predicado_sem_ordenacao_nem_criado_em(dep):
    """D15: o mascaramento por criado_em não volta pela porta dos fundos —
    nenhuma ordenação e nenhum criado_em/COALESCE em NENHUMA SQL do módulo
    (docstrings podem citar o antipadrão; as consultas, jamais)."""
    import ast as _ast
    fonte = (_ROOT / "dags/utils/dependencias.py").read_text(encoding="utf-8")
    assert "ORDER BY" not in fonte
    sqls = [n.value for n in _ast.walk(_ast.parse(fonte))
            if isinstance(n, _ast.Constant) and isinstance(n.value, str)
            and "dbo.etl_" in n.value]
    assert sqls, "esperava SQLs citando dbo.etl_* no módulo"
    for sql in sqls:
        assert "criado_em" not in sql, sql
        assert "COALESCE" not in sql, sql


# ═══════════════════ 5. dependentes_de e calendário ═════════════════════════

def test_dependentes_de_so_pipeline_ativo(dep):
    conn = _conn([{"rows": [("PIPE_C",), ("PIPE_D",)]}])
    assert dep.dependentes_de(conn, "PIPE_PAI") == ["PIPE_C", "PIPE_D"]
    sql, params = conn._cur.execs[0]
    assert "d.depende_de = %s" in sql
    assert "d.tipo = 'PIPELINE'" in sql and "p.active = 1" in sql
    assert params == ("PIPE_PAI",)


def test_calendario_bloqueia_parametrizado_pelo_dia(dep):
    """A consulta leva o DIA OPERACIONAL como parâmetro — nunca
    CAST(GETDATE()) (D06)."""
    conn = _conn([{"rows": [(1,)]}])
    assert dep.calendario_bloqueia(conn, "FERIADOS", date(2026, 7, 31)) is True
    sql, params = conn._cur.execs[0]
    assert "GETDATE" not in sql and "data = %s" in sql
    assert params == ("FERIADOS", date(2026, 7, 31))
    conn2 = _conn([{"rows": []}])
    assert dep.calendario_bloqueia(conn2, "FERIADOS", date(2026, 7, 31)) is False


def test_config_dependente_mapeia_regras_e_janela(dep):
    row = ("weekly", 0, None, "", '[{"dia": 5, "horarios": ["09:00"]}]', 1,
           time(8, 0))
    conn = _conn([{"rows": [row]}])
    cfg = dep.config_dependente(conn, "PIPE_C")
    assert cfg["nao_iniciar_antes"] == time(8, 0)
    regras = cfg["regras_dia"]
    assert regras["schedule_dow"] == 0          # domingo preservado (D05)
    assert regras["somente_dias_uteis"] is True
    assert regras["dias_horarios_mes_dias"] == [5]
    conn2 = _conn([{"rows": []}])
    assert dep.config_dependente(conn2, "NAO_EXISTE") is None


def test_paridade_derivacao_factory_x_runtime(dep, factory):
    """Espírito do D29: o pusher (config_dependente) e o filho (const gerada
    por _derivar_restricao_dia) derivam as MESMAS regras das MESMAS colunas
    — o predicado julgado é um só."""
    casos = [
        {"schedule_type": "monthly", "schedule_dow": None, "schedule_dom": 5,
         "dias_semana": "", "dias_horarios_mes": None},
        {"schedule_type": "weekly", "schedule_dow": 0, "schedule_dom": None,
         "dias_semana": "", "dias_horarios_mes": None},
        {"schedule_type": "biweekly", "schedule_dow": None, "schedule_dom": 3,
         "dias_semana": "", "dias_horarios_mes": None},
        {"schedule_type": "daily", "schedule_dow": None, "schedule_dom": None,
         "dias_semana": "1,3,5", "dias_horarios_mes": None},
        {"schedule_type": "monthly_days_times", "schedule_dow": None,
         "schedule_dom": None, "dias_semana": "",
         "dias_horarios_mes": '[{"dia": 5, "horarios": ["09:00"]}, {"dia": 20, "horarios": ["10:00"]}]'},
    ]
    for caso in casos:
        pipeline = {"pipeline_name": "PIPE_C", "scheduled_time": "06:00:00",
                    "horarios_especificos": "", **caso}
        _cron, _hor, dias_mes = factory._build_cron(pipeline)
        derivada = factory._derivar_restricao_dia(pipeline, dias_mes)
        row = (caso["schedule_type"], caso["schedule_dow"], caso["schedule_dom"],
               caso["dias_semana"], caso["dias_horarios_mes"], 0, None)
        runtime = dep.config_dependente(_conn([{"rows": [row]}]), "PIPE_C")["regras_dia"]
        assert derivada is not None, caso
        for chave, valor in derivada.items():
            assert runtime[chave] == valor, (caso, chave)


# ══════════════ 6. claim: reservar/ordenar/devolver (D13/D16/D18) ═══════════

def test_claim_vitoria_por_adocao_devolve_o_run_id_da_linha(dep):
    """Caminho (a): linha AGUARDANDO_DEPENDENCIA adotada — o run_id do
    disparo é o execution_id QUE A LINHA JÁ TINHA (arbitragem do D18)."""
    conn = _conn([{"rows": [("guardia__2026-08-01__X__1",)]}])
    ganho = dep.reservar_corrida(conn, "PIPE_C", date(2026, 8, 1), "dep__novo", "PIPE_PAI")
    assert ganho == "guardia__2026-08-01__X__1"
    assert len(conn._cur.execs) == 1            # não chegou ao INSERT
    sql, params = conn._cur.execs[0]
    assert "AGUARDANDO_DEPENDENCIA" in sql and "OUTPUT inserted.execution_id" in sql
    assert "UPDLOCK" in sql and "HOLDLOCK" in sql
    assert params == ("PIPE_PAI", "PIPE_C", date(2026, 8, 1))


def test_claim_vitoria_por_insert_devolve_o_run_id_novo(dep):
    conn = _conn([{"rows": []}, {"rowcount": 1}])
    ganho = dep.reservar_corrida(conn, "PIPE_C", date(2026, 8, 1), "dep__novo", "PIPE_PAI")
    assert ganho == "dep__novo"
    sql, params = conn._cur.execs[1]
    assert sql.startswith("INSERT INTO dbo.etl_pipeline_execucao")
    assert "'EXECUTANDO'" in sql                # nasce EXECUTANDO, nunca NULL
    assert "status <> 'PULADO'" in sql          # PULADO não bloqueia o claim
    assert "UPDLOCK" in sql and "HOLDLOCK" in sql
    assert params == ("PIPE_C", date(2026, 8, 1), "dep__novo", "PIPE_PAI",
                      "PIPE_C", date(2026, 8, 1))


def test_claim_derrota_devolve_none(dep):
    """rowcount 0 no INSERT condicional = já há corrida na data (EXECUTANDO/
    SUCESSO/FALHA/AGUARDANDO) → não disparo. É a barreira contra redisparo
    N×/ODATE (D14) e contra redispara-FALHA automático (D17)."""
    conn = _conn([{"rows": []}, {"rowcount": 0}])
    assert dep.reservar_corrida(conn, "PIPE_C", date(2026, 8, 1),
                                "dep__novo", "PIPE_PAI") is None


def test_ordenar_corrida_idempotente(dep):
    """§3.4: ordena AGUARDANDO sem disparar; True só quando criou DE FATO
    (lição do D48) — segunda chamada devolve False sem erro."""
    conn = _conn([{"rowcount": 1}, {"rowcount": 0}])
    assert dep.ordenar_corrida(conn, "PIPE_C", date(2026, 8, 1), "dep__a", "PIPE_PAI") is True
    assert dep.ordenar_corrida(conn, "PIPE_C", date(2026, 8, 1), "dep__b", "PIPE_PAI") is False
    sql, _ = conn._cur.execs[0]
    assert "'AGUARDANDO_DEPENDENCIA'" in sql and "status <> 'PULADO'" in sql


def test_devolucao_do_insert_deleta_com_as_guardas(dep):
    """D16 no modelo com run_id: DELETE só de reserva NÃO adotada
    (status EXECUTANDO e inicio IS NULL) e pela chave completa."""
    conn = _conn([{"rowcount": 1}])
    dep.devolver_reserva(conn, "PIPE_C", date(2026, 8, 1), "dep__a",
                         veio_de_adocao=False)
    sql, params = conn._cur.execs[0]
    assert sql.startswith("DELETE FROM dbo.etl_pipeline_execucao")
    assert "status='EXECUTANDO' AND inicio IS NULL" in sql
    assert params == ("PIPE_C", date(2026, 8, 1), "dep__a")


def test_devolucao_da_adocao_volta_a_aguardando(dep):
    """Caminho (a): a linha adotada volta a AGUARDANDO_DEPENDENCIA (a
    guardiã redispara na F4) — mesma guarda, corrida iniciada não reverte."""
    conn = _conn([{"rowcount": 1}])
    dep.devolver_reserva(conn, "PIPE_C", date(2026, 8, 1), "guardia__x",
                         veio_de_adocao=True)
    sql, params = conn._cur.execs[0]
    assert sql.startswith("UPDATE dbo.etl_pipeline_execucao")
    assert "SET status='AGUARDANDO_DEPENDENCIA'" in sql
    assert "status='EXECUTANDO' AND inicio IS NULL" in sql
    assert params == ("PIPE_C", date(2026, 8, 1), "guardia__x")


# ═══════════════════ 7. auxiliares tolerantes ═══════════════════════════════

def test_dias_do_horarios_mes_tolerante(dep):
    assert dep._dias_do_horarios_mes('[{"dia": 5, "horarios": ["09:00"]}]') == [5]
    assert dep._dias_do_horarios_mes(
        '[{"dia": 20}, {"dia": 5}, {"sem_dia": 1}]') == [5, 20]
    assert dep._dias_do_horarios_mes("nao é json") is None
    assert dep._dias_do_horarios_mes("") is None
    assert dep._dias_do_horarios_mes(None) is None


def test_como_time_invalido_vira_none(dep):
    """"sem regra" ≠ "regra às 00:00" — inválido é None, nunca meia-noite."""
    assert dep._como_time("08:00") == time(8, 0)
    assert dep._como_time("08:00:30") == time(8, 0, 30)
    assert dep._como_time(time(9, 15)) == time(9, 15)
    assert dep._como_time(datetime(2026, 8, 1, 7, 30)) == time(7, 30)
    assert dep._como_time("banana") is None
    assert dep._como_time(None) is None
    assert dep._como_time("") is None
