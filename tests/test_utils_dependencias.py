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

@pytest.fixture(autouse=True)
def _modo_data(dep):
    """Modo DATA em todos os testes deste arquivo, sem gastar consulta: o
    cache já preenchido faz `modo_sequencia` nem perguntar. Quem testa o modo
    SEQUÊNCIA limpa o cache e deixa o dublê responder."""
    dep._MODO_CACHE["modo"] = False
    yield
    dep.limpar_cache_modo()


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


# ── a TERCEIRA porta: corrida substituída não libera ─────────────────────────
# A F4 ensinou `reservar_corrida` e `ordenar_corrida` a ignorar corrida
# aposentada e ESQUECEU `liberado()`. O estrago, reproduzido no dev em
# 2026-08-03 com a cadeia A→B→C: reaberto o dia inteiro, a corrida APOSENTADA
# de B seguia dizendo SUCESSO na data, a guardiã liberava C no ciclo seguinte
# e C rodava com a saída ANTIGA de B — depois, quando B rerodava e publicava,
# o claim de C encontrava corrida viva e devolvia None: C nunca mais rodava
# com o dado novo. Estes testes falham no código anterior à correção.

def test_liberado_ignora_corrida_substituida(dep):
    """A cláusula está no NOT EXISTS — corrida aposentada não conta como
    SUCESSO. Sem ela, liberar o neto era questão de um ciclo da guardiã."""
    conn = _conn([{"rows": []}])
    dep.liberado(conn, "PIPE_C", date(2026, 8, 1))
    sql, params = conn._cur.execs[0]
    assert "AND e.substituida_em IS NULL" in sql
    assert "NOT EXISTS" in sql and "status = 'SUCESSO'" in sql
    assert params == ("PIPE_C", date(2026, 8, 1))


def test_as_tres_portas_concordam_sobre_corrida_substituida(dep):
    """Liberar, ordenar e reservar têm de olhar a MESMA corrida. Divergir
    produz disparo cedo (libera sem reservar) ou linha órfã (reserva sem
    liberar) — este teste é a amarração das três."""
    c1 = _conn([{"rows": []}])
    dep.liberado(c1, "P", date(2026, 8, 1))
    c2 = _conn([{"rowcount": 1}])
    dep.ordenar_corrida(c2, "P", date(2026, 8, 1), "r", "PAI")
    c3 = _conn([{"rows": []}, {"rowcount": 1}])
    dep.reservar_corrida(c3, "P", date(2026, 8, 1), "r", "PAI")
    sqls = ([c1._cur.execs[0][0]] + [c2._cur.execs[0][0]]
            + [s for s, _ in c3._cur.execs])
    assert all("substituida_em IS NULL" in s for s in sqls), sqls


def test_liberado_com_banco_sem_a_078_cai_no_legado(dep, capsys):
    """Deploy parcial ao contrário (dags/ novo, banco sem a migration): a
    referência à coluna daria Msg 207 e derrubaria o push de TODO pipeline
    com dependente. A cascata desce um nível de cada vez — 082 (retenção do
    Aguarde) → 078 (corrida substituída) → legado — e o comportamento final é
    o de antes, byte a byte, com log e nunca em silêncio."""
    erro_082 = Exception("Invalid column name 'retido_em'.")
    erro_078 = Exception("Invalid column name 'substituida_em'.")
    conn = _conn([erro_082, erro_078, {"rows": [("PIPE_A",)]}])
    ok, faltantes = dep.liberado(conn, "PIPE_C", date(2026, 8, 1))
    assert (ok, faltantes) == (False, ["PIPE_A"])
    assert len(conn._cur.execs) == 3
    ultimo = conn._cur.execs[2][0]
    assert "substituida_em" not in ultimo and "retido_em" not in ultimo
    assert "078" in capsys.readouterr().out


def test_liberado_sem_a_082_usa_o_predicado_de_antes(dep):
    """Banco COM a 078 e SEM a 082: uma queda só, e a trava do Aguarde
    simplesmente não existe — nunca 'não liberado para todo mundo'."""
    erro_082 = Exception("Invalid column name 'retido_em'.")
    conn = _conn([erro_082, {"rows": []}])
    assert dep.liberado(conn, "PIPE_C", date(2026, 8, 1)) == (True, [])
    assert len(conn._cur.execs) == 2
    assert "substituida_em" in conn._cur.execs[1][0]


def test_aguarde_retido_vira_faltante_nomeado(dep):
    """Com a 082, a 2ª coluna traz o id do Aguarde SEGURADO — e o faltante
    fala da TRAVA, não do predecessor (que pode estar concluído)."""
    conn = _conn([{"rows": [("PIPE_A", 16)]}])
    ok, faltantes = dep.liberado(conn, "PIPE_C", date(2026, 8, 1))
    assert ok is False
    assert faltantes == ["Aguarde #16 SEGURADO na malha (libere no diagrama)"]


def test_sem_retencao_o_faltante_continua_sendo_o_predecessor(dep):
    conn = _conn([{"rows": [("PIPE_A", None)]}])
    assert dep.liberado(conn, "PIPE_C", date(2026, 8, 1)) == (False, ["PIPE_A"])


def test_liberado_nao_engole_erro_que_nao_seja_da_078(dep, capsys):
    """Deadlock/timeout continuam sendo D21 (não liberado com sentinel), e
    NÃO viram uma segunda consulta silenciosa contra o banco."""
    conn = _conn([Exception("deadlock victim")])
    ok, faltantes = dep.liberado(conn, "PIPE_C", date(2026, 8, 1))
    assert ok is False and faltantes[0].startswith("erro na consulta:")
    assert len(conn._cur.execs) == 1
    assert "[DEP]" in capsys.readouterr().out


def test_observadores_de_malha_tambem_ignoram_corrida_substituida(dep):
    """Mesma lente na condição dos observadores (F14): anunciar 'malha
    concluída' contando uma entrada aposentada seria avisar o fim de um dia
    que voltou a correr."""
    conn = _conn([{"rows": [(2,)]}])
    dep.pipelines_todos_sucesso(conn, ["A", "B"], date(2026, 8, 1))
    sql, _ = conn._cur.execs[0]
    assert "e.substituida_em IS NULL" in sql
    conn2 = _conn([Exception("Invalid column name 'substituida_em'."),
                   {"rows": [(2,)]}])
    assert dep.pipelines_todos_sucesso(conn2, ["A", "B"], date(2026, 8, 1)) is True
    assert "substituida_em" not in conn2._cur.execs[1][0]


def test_modulo_declara_a_capacidade_que_a_api_le(dep):
    """O contrato com a API (deploy parcial '078 sim / dags não'): a
    declaração só pode existir enquanto as três portas de fato filtram —
    senão a API volta a prometer uma cascata que o motor não cumpre."""
    assert "rerun_cascata_078" in dep.CAPACIDADES


def test_predicado_sem_ordenacao_nem_criado_em(dep):
    """D15: o mascaramento por criado_em não volta pela porta dos fundos —
    nenhuma SQL sobre etl_pipeline_execucao ordena nem usa COALESCE, e
    `criado_em` só aparece como COLUNA devolvida — pela varredura AGUARDANDO
    da guardiã (a idade da linha, F4 §6) ou pelo universo dos observadores
    (o carimbo do nó em etl_malha_no, corte anti-retroativo da F14) — jamais
    num predicado, COALESCE ou ordenação. ORDER BY no módulo existe apenas
    FORA da tabela de execução (fila de eventos por detectado_em e escolha
    de canal, F4 §8).
    (Docstrings podem citar o antipadrão; as consultas, jamais.)

    ⚠️ A F6 trouxe DUAS construções que este teste barrava por atacado, e a
    proibição foi ESTREITADA para o que ela de fato protege — nunca afrouxada:

      • `COALESCE` só é proibido sobre a ESCOLHA DA LINHA de execução. O corte
        em três degraus (§8) coalesce INSTANTES de corte (`aberta_em`,
        `aberta_em` da malha que assinou, janela) — nenhum deles é `inicio` nem
        `criado_em`, e é isso que o teste passa a exigir literalmente;
      • `ORDER BY` num SQL que toca `etl_pipeline_execucao` só é aceito quando
        ordena a tabela de CORRIDAS (`etl_malha_execucao`) — o `TOP 1` do
        degrau 2, que a regra da casa D15 manda ser explícito. Ordenar a
        execução continua proibido.
    """
    import ast as _ast
    fonte = (_ROOT / "dags/utils/dependencias.py").read_text(encoding="utf-8")
    sqls = [n.value for n in _ast.walk(_ast.parse(fonte))
            if isinstance(n, _ast.Constant) and isinstance(n.value, str)
            and "dbo.etl_" in n.value]
    assert sqls, "esperava SQLs citando dbo.etl_* no módulo"
    _ORDER_DA_CORRIDA = "ORDER BY me2.aberta_em DESC, me2.id DESC"
    for sql in sqls:
        if "COALESCE" in sql:
            # O antipadrão B2/D14/D15 é COALESCE sobre inicio/criado_em: era ele
            # que escolhia "a linha mais recente" em vez de perguntar EXISTS.
            depois = sql[sql.index("COALESCE"):]
            assert "inicio" not in depois and "criado_em" not in depois, sql
        if "dbo.etl_pipeline_execucao" in sql:
            assert ("ORDER BY" not in sql
                    or sql.count("ORDER BY") == sql.count(_ORDER_DA_CORRIDA)), sql
        if "ORDER BY" in sql:
            assert ("ORDER BY e.detectado_em" in sql or "etl_msg_grupo" in sql
                    or _ORDER_DA_CORRIDA in sql), sql
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
    # 1ª consulta é a sonda da 075 (guarda de existência do marcador — F14),
    # a 2ª é a sonda da 085 (guarda do marcador '#corrida:' — F2); a fila em
    # si é a 3ª. As duas sondas são baratas e respondem sobre o BANCO, não
    # sobre o deploy — é o que permite a mesma fila servir os três formatos
    # de evento sem quebrar quando uma migration ainda não entrou.
    linha = (7, "PIPE_C", "2026-08-01", "JANELA_ESTOUROU", "detalhe",
             "2026-08-01 08:00:00", None, None, None)
    conn = _conn([{"rows": [(1, 1, 1)]}, {"rows": [(1,)]}, {"rows": [linha]}])
    fila = dep.eventos_nao_notificados(conn, 50, 2)
    assert fila == [{"id": 7, "pipeline": "PIPE_C", "data_ref": "2026-08-01",
                     "tipo": "JANELA_ESTOUROU", "detalhe": "detalhe",
                     "detectado_em": "2026-08-01 08:00:00",
                     "malha": None, "sequencia": None, "corrida_id": None}]
    sql, params = conn._cur.execs[2]
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


# ── F11 (Decisão 69) — o endereço do app, e o que ele faz quando falta ──────

def test_endereco_do_app_lido_da_config(dep):
    conn = _conn([{"rows": [("https://orquestra.exemplo.com",)]}])
    assert dep.app_base_url(conn) == "https://orquestra.exemplo.com"
    sql, _ = conn._cur.execs[0]
    assert "etl_app_config" in sql and "app_base_url" in sql


@pytest.mark.parametrize("roteiro", [
    [{"rows": []}],                    # chave ausente (migration 086 não veio)
    [{"rows": [(None,)]}],             # linha existe, valor nulo
    [{"rows": [("   ",)]}],            # o default da 086: criada VAZIA
])
def test_endereco_ausente_devolve_vazio_e_nao_inventa(dep, roteiro):
    """`''` significa uma coisa só: **o card sai sem botão**. Nunca um host
    adivinhado — ele mandaria o plantão para um endereço que não responde, às
    3h, e queimaria a confiança no botão inteiro."""
    assert dep.app_base_url(_conn(roteiro)) == ""


def test_endereco_indisponivel_NUNCA_derruba_o_ciclo(dep):
    """Esta leitura acontece dentro do ciclo da guardiã: um DENY de SELECT em
    etl_app_config não pode custar o alerta das 3h. A função engole a própria
    exceção e devolve o vazio — que é o card de sempre."""
    conn = _conn([Exception("SELECT permission denied on etl_app_config")])
    assert dep.app_base_url(conn) == ""


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
    temporal permitida é a idade das ÓRFÃS (§4.2 e §4.3).

    São DUAS varreduras por idade, e só duas, cada uma sobre um lado do
    `inicio`: `reservas_orfas` (claim que nunca virou corrida, `inicio IS
    NULL`) e `corridas_em_execucao` (corrida que começou e cujo DagRun morreu
    sem fechar nada, `inicio IS NOT NULL` — a F5). Qualquer DATEADD novo sobre
    a tabela que não seja uma dessas duas é varredura histórica voltando pela
    porta dos fundos."""
    import ast as _ast
    fonte = (_ROOT / "dags/utils/dependencias.py").read_text(encoding="utf-8")
    assert "_datas_em_aberto" not in fonte
    sqls = [n.value for n in _ast.walk(_ast.parse(fonte))
            if isinstance(n, _ast.Constant) and isinstance(n.value, str)
            and "dbo.etl_pipeline_execucao" in n.value]
    com_idade = [sql for sql in sqls if "DATEADD" in sql]
    for sql in com_idade:
        assert "EXECUTANDO" in sql, sql
        assert ("inicio IS NULL" in sql or "inicio IS NOT NULL" in sql), sql
    assert len(com_idade) == 2, com_idade


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


def test_evento_sem_corrida_e_byte_a_byte_o_de_antes_da_085(dep):
    """F2 — `malha_execucao_id=None` (todo evento de dependência comum) tem de
    produzir EXATAMENTE o statement anterior à 085.

    É o que garante que a F2 não muda o comportamento de nenhuma das cinco
    responsabilidades antigas da guardiã: a coluna nova não aparece no INSERT
    nem no NOT EXISTS, e os parâmetros são os sete de sempre. Um `ISNULL(...)`
    que vazasse para este caminho passaria a exigir a coluna num banco que
    ainda não a tem — a célula 2 da matriz §11.1, em que `dags/` é novo e a
    migration não entrou."""
    conn = _conn([{"rowcount": 1}])
    assert dep.gravar_evento(conn, "PIPE_C", date(2026, 8, 1),
                             "JANELA_ESTOUROU", "d") is True
    sql, params = conn._cur.execs[0]
    assert "malha_execucao_id" not in sql
    assert params == ("PIPE_C", date(2026, 8, 1), "JANELA_ESTOUROU", "d",
                      "PIPE_C", date(2026, 8, 1), "JANELA_ESTOUROU")


def test_evento_da_corrida_poe_a_corrida_na_CHAVE_e_nao_so_na_coluna(dep):
    """F2 — o evento que pertence a uma corrida tem de dizer a QUAL, e a
    idempotência passa a ser por (pipeline, dia, tipo, **corrida**).

    Sem a corrida no `NOT EXISTS`, o segundo ciclo da mesma malha no mesmo dia
    ficaria MUDO: a chave (pipeline, dia, tipo) já existiria e o `MALHA_FALHOU`
    da corrida #13 nunca sairia. E o `ISNULL(..., -1)` dos dois lados não é
    enfeite — em índice único do SQL Server dois NULLs são IGUAIS, mas em
    predicado `= NULL` nunca é verdadeiro: sem ele o NOT EXISTS aprovaria a
    linha e o INSERT morreria no 2601 do `ux_dep_evento_corrida`, DENTRO da
    transação do chamador — que aqui é a transação que fecha a corrida."""
    conn = _conn([{"rowcount": 1}])
    assert dep.gravar_evento(conn, "#corrida:12", date(2026, 8, 1),
                             "MALHA_FALHOU", "d", malha_execucao_id=12) is True
    sql, params = conn._cur.execs[0]
    assert "(pipeline_name, data_referencia, tipo, detalhe, malha_execucao_id)" in sql
    assert ("AND ISNULL(malha_execucao_id, -1) = ISNULL(CAST(%s AS BIGINT), -1)"
            in sql)
    # o id viaja duas vezes: uma para gravar, outra para casar a chave inteira
    assert params == ("#corrida:12", date(2026, 8, 1), "MALHA_FALHOU", "d", 12,
                      "#corrida:12", date(2026, 8, 1), "MALHA_FALHOU", 12)
    # opt-out do Teams continua valendo com corrida (o MALHA_SEM_TRABALHO do
    # sábado nasce carimbado de notificado)
    conn = _conn([{"rowcount": 1}])
    dep.gravar_evento(conn, "#corrida:12", date(2026, 8, 1),
                      "MALHA_SEM_TRABALHO", "d", notificar=False,
                      malha_execucao_id=12)
    sql, _ = conn._cur.execs[0]
    assert "notificado_em" in sql and "malha_execucao_id" in sql


def test_evento_da_corrida_sem_a_085_ainda_grava_o_ALERTA(dep):
    """Célula 2 da matriz §11.1 — `dags/` novo, migration ainda não aplicada.

    Perder o alerta porque a coluna nova não existe seria pior que o problema
    que a coluna resolve: o evento é gravado na forma antiga, com log, e a
    corrida some do registro — não o aviso. A degradação é ESTREITA: só o erro
    que NOMEIA a coluna da 085 desvia; qualquer outro (deadlock, timeout,
    violação de FK) sobe, porque engolir esses devolvendo "gravei" faria o
    fechador seguir achando que o card saiu."""
    sem_coluna = Exception("Invalid column name 'malha_execucao_id'.")
    conn = _conn([sem_coluna, {"rowcount": 1}])
    assert dep.gravar_evento(conn, "#corrida:12", date(2026, 8, 1),
                             "MALHA_FALHOU", "d", malha_execucao_id=12) is True
    assert len(conn._cur.execs) == 2
    assert "malha_execucao_id" not in conn._cur.execs[1][0]

    outro = Exception("Transaction (Process ID 58) was deadlocked")
    conn = _conn([outro])
    with pytest.raises(Exception, match="deadlocked"):
        dep.gravar_evento(conn, "#corrida:12", date(2026, 8, 1),
                          "MALHA_FALHOU", "d", malha_execucao_id=12)


def test_a_fila_RESOLVE_o_marcador_da_corrida(dep):
    """§10/F2 — "o evento aparece no painel (marcador `#corrida:{id}`
    resolvido)".

    O marcador precisa de um TERCEIRO ramo, e não de uma exceção do primeiro:
    caindo no ramo do pipeline comum, o `EXISTS` em `etl_pipeline` nunca
    casaria (não existe pipeline chamado `#corrida:12`) e **nenhum card do
    ciclo de malha chegaria ao Teams** — em silêncio, com o evento gravado e
    visível no painel. É a mesma classe do achado 2 da F14, com o marcador
    novo.

    O `LEFT JOIN` é do CARD, não do filtro: o card publica a MALHA e a ordinal
    do dia (a corrida se chama pela data, nunca pelo id), e sem estas duas
    colunas o evento mais grave do produto sairia com o sujeito "malha não
    identificada"."""
    linha = (9, "#corrida:12", "2026-08-01", "MALHA_FALHOU", "detalhe",
             "2026-08-01 08:00:00", "Carga_Vida", 2, 12)
    conn = _conn([{"rows": [(1, 1, 1)]}, {"rows": [(1,)]}, {"rows": [linha]}])
    fila = dep.eventos_nao_notificados(conn, 50, 2)
    assert fila[0]["malha"] == "Carga_Vida" and fila[0]["sequencia"] == 2
    # F11 (Decisão 69): o id da corrida é a LENTE do botão do card
    # (`?corrida={id}`) — viaja na URL e nunca no texto (Decisão 74).
    assert fila[0]["corrida_id"] == 12
    sql, _ = conn._cur.execs[2]
    assert ("OR (e.pipeline_name LIKE '#corrida:%%' AND EXISTS "
            "(SELECT 1 FROM dbo.etl_malha_execucao mx "
            "WHERE e.pipeline_name = '#corrida:' + "
            "CAST(mx.id AS VARCHAR(20))))") in sql
    assert ("LEFT JOIN dbo.etl_malha_execucao c ON c.id = e.malha_execucao_id"
            in sql)
    # A corrida tem PRECEDÊNCIA sobre o nó na resolução da malha (é a fonte
    # mais específica); o nó é o fallback de quem não tem corrida nenhuma.
    assert "COALESCE(c.malha_name, n2.malha_name), c.sequencia" in sql


def test_a_fila_RESOLVE_a_malha_do_NO_e_nao_so_a_da_corrida(dep):
    """Pendência 11 do §18 — o card do nó Fim publicava `#no:38`.

    O evento dos componentes do desenho (Fim, Notificação) é gravado com o
    marcador `'#no:{id}'` e **sem** `malha_execucao_id`: a resolução que a F2
    deu à fila era só a da corrida, então `malha` vinha `None` e o card do
    celular saía com sujeito `#no:38` e fato `Pipeline: #no:38` — nome de
    máquina na tela, contra a Decisão 74.

    O segundo `LEFT JOIN` resolve o marcador em `etl_malha_no.malha_name`. Ele
    é do CARD, não do filtro: a guarda de existência do nó continua sendo o
    `EXISTS` do `WHERE`, e um evento de nó apagado segue fora do canal."""
    linha = (11, "#no:38", "2026-08-04", "MALHA_CONCLUIDA", "detalhe",
             "2026-08-04 04:02:00", "Carga_Vida", None, None)
    conn = _conn([{"rows": [(1, 1, 1)]}, {"rows": [(1,)]}, {"rows": [linha]}])
    fila = dep.eventos_nao_notificados(conn, 50, 2)
    assert fila[0]["malha"] == "Carga_Vida"
    # Sem corrida: o botão do card leva à lente de execução da malha, e não a
    # uma corrida inventada (§9.8 — degradação por ausência).
    assert fila[0]["corrida_id"] is None
    sql, _ = conn._cur.execs[2]
    assert ("LEFT JOIN dbo.etl_malha_no n2 ON e.pipeline_name = '#no:' + "
            "CAST(n2.id AS VARCHAR(20))") in sql


def test_a_fila_sem_a_085_mantem_o_ramo_da_corrida_INERTE(dep):
    """A mesma degradação da 075, um ramo adiante: sem a tabela não há corrida
    para conferir — e também não há como um evento `#corrida:` ter sido gravado
    neste banco. O ramo vira `1 = 1` (inerte, não quebrado), as duas colunas
    saem NULL para a FORMA do resultado não mudar com o banco, e a fila dos
    eventos comuns segue intacta."""
    conn = _conn([{"rows": [(1, 1, 1)]}, {"rows": [(None,)]},
                  {"rows": [(9, "PIPE_C", "2026-08-01", "NAO_LIBEROU", "d",
                             "2026-08-01 08:00:00", None, None, None)]}])
    fila = dep.eventos_nao_notificados(conn, 50, 2)
    # a forma do dicionário é a MESMA com e sem a 085 — quem monta o card não
    # pode ter de perguntar em que banco está
    assert set(fila[0]) == {"id", "pipeline", "data_ref", "tipo", "detalhe",
                            "detectado_em", "malha", "sequencia", "corrida_id"}
    sql, _ = conn._cur.execs[2]
    assert "etl_malha_execucao" not in sql
    assert "NULL, NULL" in sql
    # F11: com a 075 no banco, a malha ainda é resolvida — pelo NÓ. É a fonte
    # que não depende da 085, e é justamente a dos eventos de componente.
    assert "n2.malha_name, NULL, NULL" in sql
    assert "EXISTS (SELECT 1 FROM dbo.etl_pipeline p" in sql


def test_a_fila_sem_075_e_sem_085_nao_monta_COALESCE_de_dois_NULL(dep):
    """A borda que o SQL Server recusa em COMPILAÇÃO, e não em execução:
    `COALESCE(NULL, NULL)` levanta "at least one of the arguments must not be
    the NULL constant" — e as duas pontas SÃO literais num banco sem a 075 e
    sem a 085 (o cenário de um deploy só de `api/`). A coluna é montada por
    composição justamente para esse banco: sai um `NULL` solto, a fila dos
    eventos comuns continua de pé e a forma do resultado não muda."""
    conn = _conn([{"rows": [(1, None, 1)]}, {"rows": [(None,)]},
                  {"rows": [(9, "PIPE_C", "2026-08-01", "NAO_LIBEROU", "d",
                             "2026-08-01 08:00:00", None, None, None)]}])
    fila = dep.eventos_nao_notificados(conn, 50, 2)
    assert fila[0]["malha"] is None and fila[0]["corrida_id"] is None
    sql, _ = conn._cur.execs[2]
    assert "COALESCE" not in sql
    assert "etl_malha_no" not in sql and "etl_malha_execucao" not in sql


def test_malhas_ativas_com_desenho_nao_traz_malha_INATIVA(dep):
    """§6.2/§6.9/#8 — o universo das portas 2 e 3.

    Duas guardas nesta função, e as duas são do WHERE (por isso se conferem no
    TEXTO da consulta, não no dublê):

      • `etl_malha.ativo = 1` nas TRÊS consultas: malha inativa **não abre**
        corrida nova. A corrida já aberta segue até fechar, e é por isso que o
        FECHADOR não usa esta lista — ele varre `corridas_abertas()`, que não
        filtra por `ativo`. Órfã eterna é o pior resultado possível, porque
        corrida aberta bloqueia disparo;
      • a malha entra pelos MEMBROS, não pelos nós: `nos_observadores` só
        devolve malha que TEM Notificação/Fim, e a porta 3 existe justamente
        para as malhas sem componente nenhum (3 de 4 no dev). Reusar aquela
        consulta deixaria a maioria das malhas sem abertura automática."""
    conn = _conn([
        {"rows": [("M2", "PIPE_Z"), ("M1", "PIPE_B"), ("M1", "PIPE_A")]},
        {"rows": [("M1", 1, "inicio")]},
        {"rows": [("M1", 1, None, None, "PIPE_A")]},
    ])
    saida = dep.malhas_ativas_com_desenho(conn)
    assert [m["malha"] for m in saida] == ["M1", "M2"]      # determinístico
    assert saida[0]["membros"] == ["PIPE_A", "PIPE_B"]      # e ordenado
    assert saida[0]["nos"] == [{"id": 1, "tipo": "inicio"}]
    assert saida[0]["arestas"] == [{"origem_no": 1, "origem_pipeline": None,
                                    "destino_no": None,
                                    "destino_pipeline": "PIPE_A"}]
    # a malha sem componente nenhum continua no universo — é a porta 3
    assert saida[1]["nos"] == [] and saida[1]["arestas"] == []
    for sql, _ in conn._cur.execs:
        assert "JOIN dbo.etl_malha m" in sql and "m.ativo = 1" in sql


def test_fila_exige_existencia_do_pipeline_e_do_no(dep):
    """Achado 2 da revisão da F14: com a FK derrubada (076), a FILA é quem
    confere existência — evento comum exige o pipeline em etl_pipeline;
    marcador '#no:{id}' exige o nó em etl_malha_no (075 presente). Evento
    órfão fica na tabela (histórico), só não vira card."""
    conn = _conn([{"rows": [(1, 1, 1)]}, {"rows": [(1,)]}, {"rows": []}])
    dep.eventos_nao_notificados(conn, 50, 2)
    sql, _ = conn._cur.execs[2]
    assert ("e.pipeline_name NOT LIKE '#no:%%' "
            "AND e.pipeline_name NOT LIKE '#corrida:%%' AND EXISTS "
            "(SELECT 1 FROM dbo.etl_pipeline p "
            "WHERE p.pipeline_name = e.pipeline_name)") in sql
    assert ("EXISTS (SELECT 1 FROM dbo.etl_malha_no n "
            "WHERE e.pipeline_name = '#no:' + CAST(n.id AS VARCHAR(20)))") in sql


def test_fila_sem_075_nao_toca_etl_malha_no(dep):
    """Sem a 075 não há como conferir o marcador — e a fila dos eventos
    COMUNS não pode quebrar por isso: a guarda do nó vira 1=1 e nenhuma
    consulta cita etl_malha_no."""
    conn = _conn([{"rows": [(1, None, 1)]}, {"rows": [(1,)]}, {"rows": []}])
    dep.eventos_nao_notificados(conn, 50, 2)
    sql, _ = conn._cur.execs[2]
    assert "etl_malha_no" not in sql
    assert "1 = 1" in sql
    # a guarda de pipeline continua mesmo sem a 075
    assert "EXISTS (SELECT 1 FROM dbo.etl_pipeline p" in sql


# ═════════ §4.3 (F5) — a corrida que COMEÇOU e nunca fechou ═════════════════
#
# Complemento exato de `reservas_orfas`: aquela cobre `inicio IS NULL` (claim
# que nunca virou corrida); esta cobre `inicio IS NOT NULL` — o `dagrun_timeout`
# estourado que pula `registrar_falha`/`flow_close` e deixa EXECUTANDO para
# sempre, bloqueando todos os dependentes. Falha no `main` de hoje.

def test_corridas_em_execucao_e_o_espelho_das_reservas_orfas(dep):
    conn = _conn([{"rows": [("PIPE_C", _SEGUNDA, "dep__c",
                             datetime(2026, 8, 3, 6, 0))]}])
    saida = dep.corridas_em_execucao(conn, 15)
    assert saida == [("PIPE_C", _SEGUNDA, "dep__c", datetime(2026, 8, 3, 6, 0))]
    sql, params = conn._cur.execs[0]
    assert "status = 'EXECUTANDO'" in sql
    assert "inicio IS NOT NULL" in sql          # o lado que faltava
    assert "DATEADD(minute, -%s, GETDATE())" in sql
    assert params == (15,)


def test_fechar_orfa_em_execucao_so_toca_corrida_que_comecou(dep):
    """A guarda de status+inicio é a trava contra quem estiver fechando de
    verdade no mesmo instante — e contra rebaixar uma reserva órfã."""
    conn = _conn([{"rowcount": 1}])
    assert dep.fechar_orfa_em_execucao(conn, "PIPE_C", _SEGUNDA, "dep__c",
                                       "motivo honesto") is True
    sql, params = conn._cur.execs[0]
    assert "SET status='FALHA'" in sql
    assert "AND status='EXECUTANDO' AND inicio IS NOT NULL" in sql
    assert "fim=GETDATE()" in sql
    assert params[0] == "motivo honesto"


def test_fechar_orfa_perdeu_a_corrida_devolve_false(dep):
    conn = _conn([{"rowcount": 0}])
    assert dep.fechar_orfa_em_execucao(conn, "P", _SEGUNDA, "r", "m") is False


def test_fechar_orfa_nunca_grava_sucesso(dep):
    """A guardiã não inventa verde: esta função só sabe escrever FALHA."""
    import inspect
    src = inspect.getsource(dep.fechar_orfa_em_execucao)
    assert "SUCESSO" not in src.split('"""')[-1]


# ── interruptor do MODO SEQUÊNCIA (config dependencia_modo_sequencia) ───────
# Enquanto a operação amadurece a execução agendada, a data de referência pode
# atrapalhar: pai e filho em ODATEs diferentes travam (ou soltam) a cadeia por
# um motivo que o operador não vê. O modo troca a pergunta do predicado.

def test_modo_desligado_por_padrao(dep):
    """Ausente no banco = modo DATA. O interruptor nunca liga sozinho."""
    dep.limpar_cache_modo()
    conn = _conn([{"rows": []}])
    assert dep.modo_sequencia(conn) is False


def test_modo_ligado_com_1(dep):
    dep.limpar_cache_modo()
    assert dep.modo_sequencia(_conn([{"rows": [("1",)]}])) is True


def test_modo_erro_de_consulta_fica_no_modo_data(dep, capsys):
    """Config ilegível não pode virar mudança de regra silenciosa."""
    dep.limpar_cache_modo()
    assert dep.modo_sequencia(_conn([Exception("banco fora")])) is False
    assert "modo de liberacao indisponivel" in capsys.readouterr().out


def test_modo_e_lido_uma_vez_por_processo(dep):
    """A task avalia N dependentes: perguntar por filho seria N idas ao banco
    para uma resposta que não muda no meio do run."""
    dep.limpar_cache_modo()
    conn = _conn([{"rows": [("1",)]}, {"rows": [("0",)]}])
    assert dep.modo_sequencia(conn) is True
    assert dep.modo_sequencia(conn) is True      # 2ª vez não consulta
    assert len(conn._cur.execs) == 1


def test_sequencia_olha_o_ciclo_e_nao_o_odate(dep):
    """O SQL do modo não filtra por data_referencia — filtra pela janela.
    Vale para os DOIS degraus do modo (o de hoje e o da corrida)."""
    for sql in (dep.SQL_LIBERADO_SEQ_084, dep.SQL_LIBERADO_SEQ_085):
        assert "data_referencia" not in sql
        assert "ISNULL(e.fim, e.inicio) >=" in sql
        # e continua descartando corrida substituída e obedecendo a retenção
        assert "substituida_em IS NULL" in sql
        assert "retido_em IS NOT NULL" in sql
    assert "ISNULL(e.fim, e.inicio) >= %s" in dep.SQL_LIBERADO_SEQ_084


def test_liberado_em_modo_sequencia_usa_o_corte(dep, monkeypatch):
    """No modo, o parâmetro deixa de ser a data e passa a ser o instante do
    início do ciclo — o sucesso tem de ser DESTA rodada. Sem corrida em mãos,
    o 1º degrau vai NULL e o SQL resolve pelos degraus 2 e 3."""
    dep.limpar_cache_modo()
    dep._MODO_CACHE["modo"] = True
    corte = datetime(2026, 8, 4, 20, 0)
    monkeypatch.setattr(dep, "inicio_do_ciclo_corrente", lambda _c: corte)
    conn = _conn([{"rows": []}])
    assert dep.liberado(conn, "PIPE_C", date(2026, 8, 5)) == (True, [])
    sql, params = conn._cur.execs[0]
    assert "data_referencia" not in sql
    assert params == ("PIPE_C", None, corte)
    dep.limpar_cache_modo()


# ── F6 · o corte em TRÊS degraus (§8, Decisões 38 e 39) ─────────────────────
# O predicado é consultado em TRÊS portas (push, guardiã, API). Errar aqui não
# atrasa uma tela: ou solta o que devia segurar, ou segura a casa inteira.

def _seq(dep, monkeypatch, corte=datetime(2026, 8, 4, 13, 0)):
    """Liga o modo SEQUÊNCIA sem gastar consulta e fixa o corte da janela."""
    dep.limpar_cache_modo()
    dep._MODO_CACHE["modo"] = True
    monkeypatch.setattr(dep, "inicio_do_ciclo_corrente", lambda _c: corte)
    return corte


def test_corte_tem_os_tres_degraus_na_ordem_da_decisao_38(dep):
    """A ORDEM é a regra: corrida da linha → corrida da malha que assinou →
    janela. Trocar o 1º pelo 2º é trocar "o ciclo desta linha" por "a corrida
    aberta agora", que é o defeito que a Decisão 39 nomeia."""
    sql = dep.SQL_LIBERADO_SEQ_085
    corte = sql[sql.index("COALESCE"):]
    d1 = corte.index("dbo.etl_malha_execucao me ")
    d2 = corte.index("dbo.etl_malha_no n3")
    assert d1 < d2, "o degrau da LINHA tem de vir antes do degrau da MALHA"
    # 1) a corrida da linha é PARÂMETRO, e não tem `fechada_em IS NULL`: o
    #    corte não muda de significado porque a corrida fechou (Decisão 39).
    assert "WHERE me.id = CAST(%s AS BIGINT)" in corte
    assert "me.fechada_em" not in corte[d1:d2]
    # 2) a malha vem do NÓ que assinou a linha — determinada, sem ambiguidade
    #    de membro compartilhado — e a corrida dela tem de estar ABERTA.
    assert "WHERE n3.id = dd.origem_no" in corte
    assert "me2.fechada_em IS NULL" in corte
    # 3) TOP 1 com ORDER BY explícito (regra da casa D15).
    assert "TOP 1 me2.aberta_em" in corte
    assert "ORDER BY me2.aberta_em DESC, me2.id DESC" in corte


def test_corte_e_avaliado_UMA_VEZ_POR_LINHA_e_nao_por_execucao(dep):
    """⚠️ **Onde o corte é avaliado decide o PLANO, não o estilo.**

    Escrito como `ISNULL(e.fim, e.inicio) >= COALESCE(<subconsulta>, …)`, o
    lado direito da comparação deixa de ser um valor conhecido e vira expressão
    correlacionada: o SQL Server desiste do seek em `ix_pipe_exec_cond` — o
    índice que a docstring de `liberado()` diz servir — e passa a VARRER
    `etl_pipeline_execucao` inteira, resolvendo as duas subconsultas do
    COALESCE por linha CANDIDATA.

    Medido no dev com o esquema e os índices reais (malha de 40 membros, 57.640
    execuções, cache quente): 27,6 ms no SEQ_084, 227–346 ms com o COALESCE
    dentro do `NOT EXISTS`, 24–30 ms com ele num `CROSS APPLY`. Este predicado
    roda no push de CADA pai para CADA filho, na varredura da guardiã para CADA
    linha aguardando e no painel — um fator de 10 aqui é a janela da madrugada
    caber ou não caber.

    O que este teste tranca: o corte sai UMA VEZ POR LINHA de dependência e a
    comparação é contra a COLUNA calculada, nunca contra o COALESCE inline."""
    # (a árvore `api/` herda a forma pela paridade textual, que compara os dois
    # SQLs byte a byte a menos do placeholder)
    sql = dep.SQL_LIBERADO_SEQ_085
    assert "CROSS APPLY (SELECT corte = COALESCE(" in sql, (
        "o corte voltou para dentro do NOT EXISTS — o seek morre com ele")
    assert "ISNULL(e.fim, e.inicio) >= k.corte)" in sql
    # e o COALESCE aparece UMA vez só: duas seriam duas avaliações
    assert sql.count("COALESCE(") == 1
    # o filtro do dependente vem ANTES do APPLY, que é o que mantém a ordem
    # dos parâmetros (pipeline, corrida, janela) que as três portas falam
    assert sql.index("pipeline_name =") < sql.index("CROSS APPLY")


def test_corrida_da_linha_vira_o_primeiro_parametro(dep, monkeypatch):
    """A assinatura nova entrega o ciclo ao SQL, na posição do 1º degrau."""
    corte = _seq(dep, monkeypatch)
    conn = _conn([{"rows": []}])
    assert dep.liberado(conn, "PIPE_C", date(2026, 8, 5), 77) == (True, [])
    sql, params = conn._cur.execs[0]
    assert "dbo.etl_malha_execucao" in sql
    assert params == ("PIPE_C", 77, corte)
    dep.limpar_cache_modo()


def test_corrida_ilegivel_nao_trava_o_banco_inteiro(dep, monkeypatch, capsys):
    """Um id malformado é "não tenho corrida" (degrau 2 resolve), jamais uma
    exceção: levantar aqui viraria "não liberado" para todos os dependentes do
    ciclo — a catástrofe da cascata entrando pela outra ponta."""
    corte = _seq(dep, monkeypatch)
    conn = _conn([{"rows": []}])
    assert dep.liberado(conn, "PIPE_C", date(2026, 8, 5), "abc") == (True, [])
    assert conn._cur.execs[0][1] == ("PIPE_C", None, corte)
    assert "id de ciclo ilegivel" in capsys.readouterr().out
    dep.limpar_cache_modo()


def test_modo_data_ignora_a_corrida(dep):
    """Fora do modo SEQUÊNCIA nada muda: o SQL e os parâmetros são os de antes
    da fase, byte a byte, mesmo com corrida em mãos."""
    dep.limpar_cache_modo()
    dep._MODO_CACHE["modo"] = False
    conn = _conn([{"rows": []}])
    assert dep.liberado(conn, "PIPE_C", date(2026, 8, 5), 77) == (True, [])
    sql, params = conn._cur.execs[0]
    assert "etl_malha_execucao" not in sql
    assert params == ("PIPE_C", date(2026, 8, 5))
    dep.limpar_cache_modo()


def test_sem_a_085_a_cascata_cai_na_seq_084_e_nao_trava_o_banco(dep, monkeypatch,
                                                                capsys):
    """⚠️ O TESTE MAIS IMPORTANTE DA FASE (aceite §10/F6 e célula 2 da §11.1).

    `dags/` novo + migration 085 ausente é a combinação mais provável do
    deploy: a etapa 5 é padrão-NÃO e a 6c também. Sem a cascata, o "Invalid
    object name 'dbo.etl_malha_execucao'" sobe, `liberado()` devolve NÃO
    LIBERADO para o BANCO INTEIRO e a trava nova PARA A PRODUÇÃO — em vez de
    segurar um Aguarde."""
    corte = _seq(dep, monkeypatch)
    conn = _conn([
        Exception("Invalid object name 'dbo.etl_malha_execucao'."),
        {"rows": []},
    ])
    assert dep.liberado(conn, "PIPE_C", date(2026, 8, 5), 77) == (True, [])
    tentativas = conn._cur.execs
    assert len(tentativas) == 2, tentativas
    assert "dbo.etl_malha_execucao" in tentativas[0][0]
    # o degrau seguinte é o SEQ_084: modo SEQUÊNCIA preservado, corte pela
    # janela — NÃO a volta silenciosa para a data de referência.
    assert "dbo.etl_malha_execucao" not in tentativas[1][0]
    assert "data_referencia" not in tentativas[1][0]
    assert tentativas[1][1] == ("PIPE_C", corte)
    assert "migration 085 ausente" in capsys.readouterr().out
    dep.limpar_cache_modo()


def test_sem_a_085_o_erro_pode_ser_da_coluna_ou_da_tabela(dep, monkeypatch):
    """O banco reclama da COLUNA quando só ela falta e da TABELA quando a
    migration inteira não passou — reagir a uma só deixaria metade dos deploys
    parciais levantando exceção."""
    for msg in ("Invalid object name 'dbo.etl_malha_execucao'.",
                "Invalid column name 'malha_execucao_id'."):
        corte = _seq(dep, monkeypatch)
        conn = _conn([Exception(msg), {"rows": []}])
        assert dep.liberado(conn, "PIPE_C", date(2026, 8, 5), 77) == (True, [])
        assert len(conn._cur.execs) == 2, msg
    dep.limpar_cache_modo()


def test_sem_a_082_o_modo_sequencia_volta_para_a_data(dep, monkeypatch, capsys):
    """Degrau seguinte da cascata: sem `etl_malha_no` nenhum SQL do modo roda,
    e a liberação volta a olhar a data de referência — em VOZ ALTA. Um banco
    anterior à 082 com o interruptor ligado só existe em deploy fora de ordem;
    travar seria pior que degradar, e degradar em silêncio seria pior que os
    dois."""
    _seq(dep, monkeypatch)
    conn = _conn([
        Exception("Invalid object name 'dbo.etl_malha_execucao'."),
        Exception("Invalid object name 'dbo.etl_malha_no'."),
        {"rows": []},
    ])
    assert dep.liberado(conn, "PIPE_C", date(2026, 8, 5), 77) == (True, [])
    execs = conn._cur.execs
    assert len(execs) == 3
    assert "data_referencia = %s" in execs[2][0]
    assert execs[2][1] == ("PIPE_C", date(2026, 8, 5))
    saida = capsys.readouterr().out
    # o log CITA o objeto que falta: "modo SEQUENCIA indisponivel" sem dizer
    # por quê mandaria o plantonista adivinhar qual migration pular.
    assert "modo SEQUENCIA indisponivel" in saida
    assert "dbo.etl_malha_no" in saida
    dep.limpar_cache_modo()


def test_sem_a_078_o_modo_sequencia_tambem_degrada_em_vez_de_travar(dep,
                                                                    monkeypatch):
    """Os DOIS SQLs do modo citam `substituida_em` — num banco anterior à 078
    nenhum roda. A cascata precisa reconhecer essa marca também, senão o erro
    sobe e volta a catástrofe: não-liberado para o banco inteiro."""
    _seq(dep, monkeypatch)
    conn = _conn([
        Exception("Invalid column name 'substituida_em'."),   # SEQ_085
        Exception("Invalid column name 'substituida_em'."),   # 082 (por data)
        Exception("Invalid column name 'substituida_em'."),   # 078
        {"rows": []},                                         # legado
    ])
    assert dep.liberado(conn, "PIPE_C", date(2026, 8, 5), 77) == (True, [])
    assert "substituida_em" not in conn._cur.execs[-1][0]
    dep.limpar_cache_modo()


def test_seq_085_direto_para_a_data_quando_falta_a_tabela_de_nos(dep, monkeypatch):
    """Sem `etl_malha_no`, o SEQ_084 falharia pelo MESMO motivo — a cascata
    pula o degrau inútil em vez de gastar uma ida ao banco para reprovar."""
    _seq(dep, monkeypatch)
    conn = _conn([
        Exception("Invalid object name 'dbo.etl_malha_no'."),
        {"rows": []},
    ])
    assert dep.liberado(conn, "PIPE_C", date(2026, 8, 5), 77) == (True, [])
    execs = conn._cur.execs
    assert len(execs) == 2
    assert "data_referencia = %s" in execs[1][0]
    dep.limpar_cache_modo()


def test_erro_desconhecido_no_modo_sequencia_nao_degrada(dep, monkeypatch):
    """Deadlock e timeout continuam PROPAGANDO para o try/except do `liberado`
    (D21: NÃO liberado com o sentinel) — degradar em silêncio um erro de banco
    é a classe que a cascata NÃO pode virar."""
    _seq(dep, monkeypatch)
    conn = _conn([Exception("deadlock victim")])
    lib, falt = dep.liberado(conn, "PIPE_C", date(2026, 8, 5), 77)
    assert lib is False
    assert falt[0].startswith(dep.ERRO_CONSULTA)
    assert len(conn._cur.execs) == 1, "não pode ter tentado outro degrau"
    dep.limpar_cache_modo()


def test_a_janela_continua_existindo_para_dependencia_avulsa(dep):
    """Decisão 38, degrau 3: a janela NÃO está depreciada. Dependência criada à
    mão pelo POST /dependencias tem `origem_no IS NULL` — os degraus 1 e 2 não
    respondem por ela, e sem a janela TODA dependência avulsa quebraria."""
    corte = dep.SQL_LIBERADO_SEQ_085
    corte = corte[corte.index("COALESCE"):]
    # o último argumento do COALESCE é o parâmetro da janela, e ele é o único
    # que não depende de tabela nenhuma.
    assert corte.rstrip().endswith("%s))") or "%s)" in corte
    assert dep.janela_sequencia_horas.__doc__.count("FALLBACK") >= 1
    assert "não está depreciada" in dep.janela_sequencia_horas.__doc__ \
        or "não** está depreciada" in dep.janela_sequencia_horas.__doc__
    assert "FALLBACK" in dep.inicio_do_ciclo_corrente.__doc__ \
        or "fallback" in dep.inicio_do_ciclo_corrente.__doc__


def test_janela_do_modo_sequencia_atravessa_a_meia_noite(dep, monkeypatch):
    """O caso que motivou a janela: malha começa 23h do dia 03 e o filho é
    avaliado 01h do dia 04. Com corte na VIRADA (00:00), o pai que concluiu
    23h30 ficaria de fora e a cadeia travaria em silêncio — o problema que o
    ODATE existe para resolver. Com janela, o corte é 13h do dia 03 e o pai
    continua valendo."""
    dep.limpar_cache_modo()
    monkeypatch.setattr(dep, "agora_do_banco",
                        lambda _c: datetime(2026, 8, 4, 1, 0))
    conn = _conn([{"rows": [("12",)]}])
    corte = dep.inicio_do_ciclo_corrente(conn)
    assert corte == datetime(2026, 8, 3, 13, 0)
    assert corte < datetime(2026, 8, 3, 23, 30)   # o pai das 23h30 ENTRA
    dep.limpar_cache_modo()


def test_janela_barra_a_rodada_anterior(dep, monkeypatch):
    """24h depois, o mesmo sucesso já não vale: a rodada de hoje não é
    liberada pelo sucesso de ontem."""
    monkeypatch.setattr(dep, "agora_do_banco",
                        lambda _c: datetime(2026, 8, 5, 1, 0))
    conn = _conn([{"rows": [("12",)]}])
    assert dep.inicio_do_ciclo_corrente(conn) > datetime(2026, 8, 3, 23, 30)


def test_janela_fora_do_dominio_volta_ao_padrao(dep):
    """0 travaria tudo; 10000 deixaria o sucesso da semana passada liberar."""
    assert dep.janela_sequencia_horas(_conn([{"rows": [("0",)]}])) == 12
    assert dep.janela_sequencia_horas(_conn([{"rows": [("10000",)]}])) == 12
    assert dep.janela_sequencia_horas(_conn([{"rows": [("abc",)]}])) == 12
    assert dep.janela_sequencia_horas(_conn([{"rows": [("6",)]}])) == 6
