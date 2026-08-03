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
    nenhuma SQL sobre etl_pipeline_execucao ordena nem usa COALESCE, e
    `criado_em` só aparece como COLUNA devolvida — pela varredura AGUARDANDO
    da guardiã (a idade da linha, F4 §6) ou pelo universo dos observadores
    (o carimbo do nó em etl_malha_no, corte anti-retroativo da F14) — jamais
    num predicado, COALESCE ou ordenação. ORDER BY no módulo existe apenas
    FORA da tabela de execução (fila de eventos por detectado_em e escolha
    de canal, F4 §8).
    (Docstrings podem citar o antipadrão; as consultas, jamais.)"""
    import ast as _ast
    fonte = (_ROOT / "dags/utils/dependencias.py").read_text(encoding="utf-8")
    sqls = [n.value for n in _ast.walk(_ast.parse(fonte))
            if isinstance(n, _ast.Constant) and isinstance(n.value, str)
            and "dbo.etl_" in n.value]
    assert sqls, "esperava SQLs citando dbo.etl_* no módulo"
    for sql in sqls:
        assert "COALESCE" not in sql, sql
        if "dbo.etl_pipeline_execucao" in sql:
            assert "ORDER BY" not in sql, sql
        if "ORDER BY" in sql:
            assert "ORDER BY e.detectado_em" in sql or "etl_msg_grupo" in sql, sql
        if "criado_em" in sql:
            assert sql.index("criado_em") < sql.upper().index(" FROM "), sql
            assert ("AGUARDANDO_DEPENDENCIA" in sql
                    or "dbo.etl_malha_no" in sql), sql


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


# ═══════════ F4 §12.1 — candidatos_dia_operacional (puro, §2.3) ═════════════

def test_candidatos_virada_meia_noite_e_so_hoje(dep):
    agora = datetime(2026, 8, 3, 10, 0)
    assert dep.candidatos_dia_operacional(agora, time(0, 0)) == [date(2026, 8, 3)]


def test_candidatos_depois_da_virada_e_so_hoje(dep):
    """Sexta 21:00, virada 20:00 (D07): a corrida corrente é a de amanhã,
    ordenada HOJE — o único dia de origem possível é hoje."""
    agora = datetime(2026, 7, 31, 21, 0)
    assert dep.candidatos_dia_operacional(agora, time(20, 0)) == [date(2026, 7, 31)]


def test_candidatos_no_corredor_pos_meia_noite(dep):
    """Sábado 00:15, virada 20:00 (D06): o pai pode ter rodado ontem 23:30
    ou hoje 01:00 — os dois candidatos, o mais antigo primeiro (o chamador
    prefere o dia de origem provável)."""
    agora = datetime(2026, 8, 1, 0, 15)
    assert dep.candidatos_dia_operacional(agora, time(20, 0)) == [
        date(2026, 7, 31), date(2026, 8, 1)]


def test_candidatos_no_instante_exato_da_virada(dep):
    agora = datetime(2026, 7, 31, 20, 0)
    assert dep.candidatos_dia_operacional(agora, time(20, 0)) == [date(2026, 7, 31)]


# ═══════════════ F4 §12.2 — instante_deadline (puro, §5.1) ══════════════════

def test_deadline_virada_meia_noite_ancora_no_proprio_dia(dep):
    assert dep.instante_deadline(date(2026, 8, 1), time(9, 0), time(0, 0)) \
        == datetime(2026, 8, 1, 9, 0)


def test_deadline_limite_apos_a_virada_ancora_na_vespera(dep):
    """D=sábado, virada 20:00, limite 22:00 → sexta 22:00 (o trecho
    pré-meia-noite do dia operacional [(D-1)@20:00, D@20:00))."""
    assert dep.instante_deadline(date(2026, 8, 1), time(22, 0), time(20, 0)) \
        == datetime(2026, 7, 31, 22, 0)


def test_deadline_limite_antes_da_virada_ancora_no_dia(dep):
    """D=sábado, virada 20:00, limite 02:00 → sábado 02:00: a linha criada
    sexta 21:00 NÃO pode alertar sexta 21:05 (a âncora de DATA do §5.1)."""
    assert dep.instante_deadline(date(2026, 8, 1), time(2, 0), time(20, 0)) \
        == datetime(2026, 8, 1, 2, 0)


def test_deadline_igual_a_virada_fica_na_vespera(dep):
    assert dep.instante_deadline(date(2026, 8, 1), time(20, 0), time(20, 0)) \
        == datetime(2026, 7, 31, 20, 0)


# ═════════════ F4 — funções de banco da guardiã (§9 do desenho) ═════════════

def test_sonda_da_067_exige_as_tres_tabelas(dep):
    assert dep.tabelas_067_presentes(_conn([{"rows": [(1, 2, 3)]}])) is True
    assert dep.tabelas_067_presentes(_conn([{"rows": [(1, None, 3)]}])) is False
    assert dep.tabelas_067_presentes(_conn([{"rows": []}])) is False


def test_universo_do_new_day_so_ativos_com_dependencia(dep):
    conn = _conn([{"rows": [("PIPE_C",)]}])
    assert dep.dependentes_com_dependencia(conn) == ["PIPE_C"]
    sql, _ = conn._cur.execs[0]
    assert "DISTINCT" in sql and "p.active = 1" in sql
    assert "tipo = 'PIPELINE'" in sql


def test_predecessores_de_tipo_pipeline(dep):
    conn = _conn([{"rows": [("PIPE_A",), ("PIPE_B",)]}])
    assert dep.predecessores_de(conn, "PIPE_C") == ["PIPE_A", "PIPE_B"]
    sql, params = conn._cur.execs[0]
    assert "dd.tipo = 'PIPELINE'" in sql
    assert params == ("PIPE_C",)


def test_virada_efetiva_prefere_a_coluna_do_pipeline(dep):
    conn = _conn([{"rows": [(time(20, 0), "06:00")]}])
    assert dep.virada_efetiva(conn, "PIPE_PAI") == time(20, 0)
    sql, params = conn._cur.execs[0]
    assert "hora_virada" in sql and "dependencia_hora_virada" in sql
    assert "COALESCE" not in sql        # fallback em Python (D15 vale p/ o módulo)
    assert params == ("PIPE_PAI",)


def test_virada_efetiva_cai_na_config_global_e_no_default(dep):
    assert dep.virada_efetiva(_conn([{"rows": [(None, "06:00")]}]), "P") == time(6, 0)
    assert dep.virada_efetiva(_conn([{"rows": [(None, None)]}]), "P") == time(0, 0)
    assert dep.virada_efetiva(_conn([{"rows": []}]), "NAO_EXISTE") == time(0, 0)
    assert dep.virada_efetiva(_conn([{"rows": [(None, "lixo")]}]), "P") == time(0, 0)


def test_corridas_aguardando_devolve_criado_em_como_coluna(dep):
    linha = ("PIPE_C", date(2026, 8, 1), "guardia__x", datetime(2026, 8, 1, 6, 0))
    conn = _conn([{"rows": [linha]}])
    assert dep.corridas_aguardando(conn) == [linha]
    sql, _ = conn._cur.execs[0]
    assert "status = 'AGUARDANDO_DEPENDENCIA'" in sql
    assert "ORDER BY" not in sql        # varredura sem ordenação (D15/D45)


def test_resumo_predecessores_traz_todos_com_set_vazio_sem_linha(dep):
    conn = _conn([{"rows": [("PIPE_A", "SUCESSO"), ("PIPE_A", "PULADO"),
                            ("PIPE_B", None)]}])
    resumo = dep.resumo_predecessores(conn, "PIPE_C", date(2026, 8, 1))
    assert resumo == {"PIPE_A": {"SUCESSO", "PULADO"}, "PIPE_B": set()}
    sql, params = conn._cur.execs[0]
    assert "LEFT JOIN" in sql
    assert params == (date(2026, 8, 1), "PIPE_C")


def test_divergencia_de_execucao_exige_fim_dentro_do_dia_corrente(dep):
    """D42: a consulta pede fim >= virada corrente E data <> D E sem SUCESSO
    em D — o sucesso normal de ontem fica de fora por construção; o carimbo
    é `fim`, nunca criado_em (D15)."""
    inicio_dia = datetime(2026, 8, 1, 20, 0)
    conn = _conn([{"rows": [("PIPE_A", date(2026, 8, 3))]}])
    pares = dep.sucesso_recente_outra_data(conn, "PIPE_C", date(2026, 8, 2),
                                           inicio_dia)
    assert pares == [("PIPE_A", date(2026, 8, 3))]
    sql, params = conn._cur.execs[0]
    assert "e.fim >= %s" in sql and "e.data_referencia <> %s" in sql
    assert "criado_em" not in sql
    assert "NOT EXISTS" in sql and "s.status = 'SUCESSO'" in sql
    assert params == (inicio_dia, date(2026, 8, 2), "PIPE_C", date(2026, 8, 2))


def test_reservas_orfas_com_guarda_de_idade_e_inicio_nulo(dep):
    conn = _conn([{"rows": [("PIPE_C", date(2026, 8, 1), "guardia__x")]}])
    assert dep.reservas_orfas(conn, 10) == [("PIPE_C", date(2026, 8, 1), "guardia__x")]
    sql, params = conn._cur.execs[0]
    assert "status = 'EXECUTANDO'" in sql and "inicio IS NULL" in sql
    assert "DATEADD(minute, -%s, GETDATE())" in sql
    assert params == (10,)


def test_resgatar_reserva_so_com_a_dupla_guarda(dep):
    """§4.2: mesma guarda da devolução — corrida adotada (inicio carimbado)
    jamais é revertida."""
    conn = _conn([{"rowcount": 1}])
    assert dep.resgatar_reserva(conn, "PIPE_C", date(2026, 8, 1), "guardia__x") is True
    sql, params = conn._cur.execs[0]
    assert "SET status='AGUARDANDO_DEPENDENCIA'" in sql
    assert "status='EXECUTANDO' AND inicio IS NULL" in sql
    assert params == ("PIPE_C", date(2026, 8, 1), "guardia__x")
    conn2 = _conn([{"rowcount": 0}])
    assert dep.resgatar_reserva(conn2, "PIPE_C", date(2026, 8, 1), "x") is False


def test_fechar_nao_liberou_guarda_e_clip_do_motivo(dep):
    """§12.8: fecha SÓ linha ainda AGUARDANDO (as demais guardas — idade,
    não-liberada, sem EXECUTANDO — são do ciclo); motivo clipado no
    VARCHAR(500); rowcount 0 = não fechou (não se assume nada)."""
    conn = _conn([{"rowcount": 1}])
    assert dep.fechar_nao_liberou(conn, "PIPE_C", date(2026, 8, 1),
                                  "guardia__x", "m" * 600) is True
    sql, params = conn._cur.execs[0]
    assert "SET status='NAO_LIBEROU'" in sql
    assert "AND status='AGUARDANDO_DEPENDENCIA'" in sql
    assert params[0] == "m" * 500
    conn2 = _conn([{"rowcount": 0}])
    assert dep.fechar_nao_liberou(conn2, "PIPE_C", date(2026, 8, 1), "x", "m") is False


def test_nao_liberou_e_terminal_no_modulo(dep):
    """§6: NAO_LIBEROU é terminal — o único SQL do módulo que o cita é o
    UPDATE que o grava; nenhuma função o reabre."""
    import ast as _ast
    fonte = (_ROOT / "dags/utils/dependencias.py").read_text(encoding="utf-8")
    sqls = [n.value for n in _ast.walk(_ast.parse(fonte))
            if isinstance(n, _ast.Constant) and isinstance(n.value, str)
            and "NAO_LIBEROU" in n.value and "dbo.etl_" in n.value]
    assert sqls, "esperava o UPDATE do fechamento"
    assert all("SET status='NAO_LIBEROU'" in s for s in sqls)


def test_gravar_evento_idempotente_pela_chave(dep):
    """§12.9: 2ª chamada com a mesma chave (pipeline, data, tipo) devolve
    False (o WHERE NOT EXISTS barrou) — ciclo repetido não duplica (D49);
    detalhe clipado no VARCHAR(1000)."""
    conn = _conn([{"rowcount": 1}, {"rowcount": 0}])
    assert dep.gravar_evento(conn, "PIPE_C", date(2026, 8, 1),
                             "JANELA_ESTOUROU", "d" * 1200) is True
    assert dep.gravar_evento(conn, "PIPE_C", date(2026, 8, 1),
                             "JANELA_ESTOUROU", "d") is False
    sql, params = conn._cur.execs[0]
    assert "WHERE NOT EXISTS" in sql and "etl_dependencia_evento" in sql
    assert params[3] == "d" * 1000
    assert params[4:] == ("PIPE_C", date(2026, 8, 1), "JANELA_ESTOUROU")


def test_fila_de_notificacao_recente_e_em_ordem(dep):
    # 1ª consulta é a sonda da 075 (guarda de existência do marcador — F14);
    # a fila em si é a 2ª.
    linha = (7, "PIPE_C", "2026-08-01", "JANELA_ESTOUROU", "detalhe",
             "2026-08-01 08:00:00")
    conn = _conn([{"rows": [(1, 1, 1)]}, {"rows": [linha]}])
    fila = dep.eventos_nao_notificados(conn, 50, 2)
    assert fila == [{"id": 7, "pipeline": "PIPE_C", "data_ref": "2026-08-01",
                     "tipo": "JANELA_ESTOUROU", "detalhe": "detalhe",
                     "detectado_em": "2026-08-01 08:00:00"}]
    sql, params = conn._cur.execs[1]
    assert "notificado_em IS NULL" in sql
    assert "DATEADD(day, -%s, GETDATE())" in sql
    assert "ORDER BY e.detectado_em" in sql     # ordem do lote — nunca criado_em
    assert params == (50, 2)


def test_marcar_notificado_por_id(dep):
    conn = _conn([{"rowcount": 1}])
    dep.marcar_notificado(conn, 7)
    sql, params = conn._cur.execs[0]
    assert "SET notificado_em=GETDATE()" in sql
    assert params == (7,)


def test_canal_derivado_da_supervisao(dep):
    """§8: o grupo que a supervisão DE FATO usa — ativo, com webhook e com
    jobs ativos apontando para ele; sem elegível → None (degradação)."""
    conn = _conn([{"rows": [(3, "https://webhook/SEGREDO", "Canal BI")]}])
    canal = dep.canal_teams_supervisao(conn)
    assert canal == {"id": 3, "webhook_url": "https://webhook/SEGREDO",
                     "nome": "Canal BI"}
    sql, _ = conn._cur.execs[0]
    assert "etl_msg_grupo" in sql and "etl_ds_supervisao_job" in sql
    assert "g.ativo = 1" in sql and "TOP 1" in sql
    assert dep.canal_teams_supervisao(_conn([{"rows": []}])) is None


def test_config_dependente_ganha_hora_limite_aditiva(dep):
    """F4: a 8ª coluna vira a chave 'hora_limite' (o push a ignora); linha
    de 7 colunas — os stubs e o contrato da F3 — continua aceita, com
    hora_limite None (leitura tolerante)."""
    row8 = ("daily", None, None, "", None, 0, None, time(9, 30))
    cfg = dep.config_dependente(_conn([{"rows": [row8]}]), "PIPE_C")
    assert cfg["hora_limite"] == time(9, 30)
    row7 = ("daily", None, None, "", None, 0, None)
    cfg7 = dep.config_dependente(_conn([{"rows": [row7]}]), "PIPE_C")
    assert cfg7["hora_limite"] is None


def test_guarda_de_idade_ausencia_de_varredura_historica(dep):
    """D45 (§12.4, teste de ausência): nenhuma função do módulo seleciona
    "datas em aberto" de etl_pipeline_execucao por janela temporal para
    ORDENAR (o _datas_em_aberto de 48h da 1ª guardiã) — a única janela
    temporal permitida é a idade das reservas órfãs (§4.2)."""
    import ast as _ast
    fonte = (_ROOT / "dags/utils/dependencias.py").read_text(encoding="utf-8")
    assert "_datas_em_aberto" not in fonte
    sqls = [n.value for n in _ast.walk(_ast.parse(fonte))
            if isinstance(n, _ast.Constant) and isinstance(n.value, str)
            and "dbo.etl_pipeline_execucao" in n.value]
    for sql in sqls:
        if "DATEADD" in sql:
            assert "inicio IS NULL" in sql and "EXECUTANDO" in sql, sql


# ═══════════ F14 — observadores de malha (desenho de componentes §5/§6) ═════

def test_tabela_075_presente_exige_as_tres_tabelas(dep):
    assert dep.tabela_075_presente(_conn([{"rows": [(1, 2, 3)]}])) is True
    assert dep.tabela_075_presente(_conn([{"rows": [(1, None, 3)]}])) is False
    conn = _conn([{"rows": [(1, 2, 3)]}])
    dep.tabela_075_presente(conn)
    sql, _ = conn._cur.execs[0]
    for tabela in ("etl_malha", "etl_malha_no", "etl_malha_aresta"):
        assert f"'dbo.{tabela}'" in sql


def test_nos_observadores_agrupa_por_malha_e_filtra_tipos(dep):
    """Só notificacao/fim viram observador; cada um carrega o desenho INTEIRO
    da malha (insumo do expandir canônico); config quebrado degrada p/ None;
    malha ativa é filtro do SQL (m.ativo = 1 nas DUAS consultas)."""
    criado = datetime(2026, 8, 1, 10, 0)
    nos_rows = [
        ("M1", 1, "aguarde", None, criado),
        ("M1", 2, "notificacao", '{"titulo": "T"}', criado),
        ("M1", 3, "fim", "lixo{", criado),
        ("M2", 7, "inicio", None, criado),
    ]
    arestas_rows = [
        ("M1", None, "PIPE_A", 1, None),
        ("M1", 1, None, 2, None),
        ("M2", 7, None, None, "PIPE_B"),
    ]
    conn = _conn([{"rows": nos_rows}, {"rows": arestas_rows}])
    obs = dep.nos_observadores(conn)
    assert [(o["malha"], o["no_id"], o["tipo"]) for o in obs] == [
        ("M1", 2, "notificacao"), ("M1", 3, "fim")]
    assert obs[0]["config"] == {"titulo": "T"}
    assert obs[1]["config"] is None                 # ilegível degrada com log
    assert obs[0]["criado_em"] == criado            # corte anti-retroativo
    assert obs[0]["nos"] == [{"id": 1, "tipo": "aguarde"},
                             {"id": 2, "tipo": "notificacao"},
                             {"id": 3, "tipo": "fim"}]
    assert len(obs[0]["arestas"]) == 2              # só as arestas de M1
    for sql, _ in conn._cur.execs:
        assert "m.ativo = 1" in sql


def test_nos_observadores_malha_so_com_inicio_aguarde_nao_aparece(dep):
    conn = _conn([{"rows": [("M2", 7, "inicio", None, datetime(2026, 8, 1)),
                            ("M2", 8, "aguarde", None, datetime(2026, 8, 1))]},
                  {"rows": []}])
    assert dep.nos_observadores(conn) == []


def test_pipelines_todos_sucesso_matriz(dep):
    """O espelho da matriz de liberado (§13.7): todas com SUCESSO → True;
    uma falta (FALHA/outra data/ausência dão o MESMO count menor) → False;
    exceção → False (D21: erro nunca vira 'condição fechou')."""
    d = date(2026, 8, 3)
    assert dep.pipelines_todos_sucesso(
        _conn([{"rows": [(2,)]}]), ["PIPE_A", "PIPE_B"], d) is True
    assert dep.pipelines_todos_sucesso(
        _conn([{"rows": [(1,)]}]), ["PIPE_A", "PIPE_B"], d) is False
    assert dep.pipelines_todos_sucesso(
        _conn([RuntimeError("deadlock")]), ["PIPE_A"], d) is False


def test_pipelines_todos_sucesso_sql_e_contrato_exists(dep):
    """A consulta é o contrato EXISTS sobre nomes EXPLÍCITOS: status SUCESSO,
    data parametrizada, IN com um marcador por nome — nenhuma ordenação."""
    d = date(2026, 8, 3)
    conn = _conn([{"rows": [(2,)]}])
    dep.pipelines_todos_sucesso(conn, ["PIPE_B", "PIPE_A"], d)
    sql, params = conn._cur.execs[0]
    assert "COUNT(DISTINCT e.pipeline_name)" in sql
    assert "e.status = 'SUCESSO'" in sql
    assert "e.data_referencia = %s" in sql
    assert "IN (%s, %s)" in sql
    assert "ORDER BY" not in sql
    assert params == (d, "PIPE_A", "PIPE_B")


def test_pipelines_todos_sucesso_vazio_nunca_e_verdadeiro(dep):
    """Decisão 13 em runtime: lista vazia → False SEM consultar (o 'todos'
    vacuamente verdadeiro jamais emite)."""
    conn = _conn()
    assert dep.pipelines_todos_sucesso(conn, [], date(2026, 8, 3)) is False
    assert conn._cur.execs == []


def test_pipelines_todos_sucesso_dedup_casefold(dep):
    """Colação CI do banco × Python CS: grafias que o banco considera IGUAIS
    contam UMA vez no len — senão a condição nunca fecharia."""
    conn = _conn([{"rows": [(1,)]}])
    assert dep.pipelines_todos_sucesso(
        conn, ["PIPE_A", "pipe_a"], date(2026, 8, 3)) is True
    _, params = conn._cur.execs[0]
    assert len(params) == 2                         # data + UM nome


def test_gravar_evento_com_notificar_false_carimba_no_nascimento(dep):
    """Decisão 14 (card do Fim opt-in): notificar=False grava o evento JÁ
    com notificado_em — nunca entra na fila do Teams; a chave idempotente
    continua a mesma."""
    conn = _conn([{"rowcount": 1}])
    assert dep.gravar_evento(conn, "#no:9", date(2026, 8, 3),
                             "MALHA_CONCLUIDA", "d", notificar=False) is True
    sql, params = conn._cur.execs[0]
    assert "notificado_em" in sql and "GETDATE()" in sql
    assert "WHERE NOT EXISTS" in sql
    assert params[4:] == ("#no:9", date(2026, 8, 3), "MALHA_CONCLUIDA")


def test_gravar_evento_default_nao_carimba_notificado(dep):
    """O caminho default (notificar=True) segue byte-idêntico ao da F4: sem
    notificado_em no INSERT — a fila do Teams decide."""
    conn = _conn([{"rowcount": 1}])
    dep.gravar_evento(conn, "PIPE_C", date(2026, 8, 3), "NAO_LIBEROU", "d")
    sql, _ = conn._cur.execs[0]
    assert "notificado_em" not in sql


def test_fila_exige_existencia_do_pipeline_e_do_no(dep):
    """Achado 2 da revisão da F14: com a FK derrubada (076), a FILA é quem
    confere existência — evento comum exige o pipeline em etl_pipeline;
    marcador '#no:{id}' exige o nó em etl_malha_no (075 presente). Evento
    órfão fica na tabela (histórico), só não vira card."""
    conn = _conn([{"rows": [(1, 1, 1)]}, {"rows": []}])
    dep.eventos_nao_notificados(conn, 50, 2)
    sql, _ = conn._cur.execs[1]
    assert ("e.pipeline_name NOT LIKE '#no:%%' AND EXISTS "
            "(SELECT 1 FROM dbo.etl_pipeline p "
            "WHERE p.pipeline_name = e.pipeline_name)") in sql
    assert ("EXISTS (SELECT 1 FROM dbo.etl_malha_no n "
            "WHERE e.pipeline_name = '#no:' + CAST(n.id AS VARCHAR(20)))") in sql


def test_fila_sem_075_nao_toca_etl_malha_no(dep):
    """Sem a 075 não há como conferir o marcador — e a fila dos eventos
    COMUNS não pode quebrar por isso: a guarda do nó vira 1=1 e nenhuma
    consulta cita etl_malha_no."""
    conn = _conn([{"rows": [(1, None, 1)]}, {"rows": []}])
    dep.eventos_nao_notificados(conn, 50, 2)
    sql, _ = conn._cur.execs[1]
    assert "etl_malha_no" not in sql
    assert "1 = 1" in sql
    # a guarda de pipeline continua mesmo sem a 075
    assert "EXISTS (SELECT 1 FROM dbo.etl_pipeline p" in sql
