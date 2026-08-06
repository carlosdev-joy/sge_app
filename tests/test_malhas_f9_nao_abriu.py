"""
F9 da spec `docs/spec-malha-execucao.md` — o lado do SERVIDOR: a corrida que
NÃO ABRIU (Decisão 58) e o relógio do fechamento (Decisão 45).

O DEFEITO que esta suíte trava
──────────────────────────────
O Início não disparou às 01:00 (DAG pausada, Airflow fora, agendamento
quebrado). Às 8h o operador abre `/malha` e vê a corrida de ONTEM: verde,
"concluída", com carimbo de frescor recente. **A malha que não rodou é a única
que não aparece em lugar nenhum** — toda a camada de visibilidade pressupõe
"a corrida existe", e a peça que sabe o que DEVERIA ter acontecido (o
agendamento) nunca foi comparada com o relógio.

Por que o cálculo é do SERVIDOR, e o teste prova isso
─────────────────────────────────────────────────────
O dublê põe o banco **3h à frente** do processo (`AGORA_BANCO` 10:00 ×
`AGORA_API` 07:00) — o desvio MEDIDO no dev. Com ele:

  • o ATRASO exibido tem de ser o real (o horário previsto e o "agora" na mesma
    régua). Uma implementação que comparasse a hora do cron com o relógio do
    BANCO publicaria 3h de atraso inventado — e o card acusaria a malha todo
    dia, no horário em que ela está saudável;
  • a pergunta "alguma corrida abriu depois do previsto?" é comparada com
    `aberta_em`, que é coluna carimbada por `GETDATE()`. Aí o previsto TEM de
    ser convertido para a régua do banco antes da comparação (o `desvio_banco`
    da guardiã). Sem a conversão, uma corrida que abriu 10 min depois do
    horário pareceria ter aberto 2h50 ANTES dele — e o card diria "não abriu"
    de uma malha que abriu.

As duas contas erradas dão certo num ambiente sem desvio. É por isso que o
dublê tem desvio.

As quatro travas contra o alarme falso, cada uma com um teste
─────────────────────────────────────────────────────────────
1. **só malha que JÁ TEVE corrida** — a trava do DIA DO DEPLOY: o interruptor
   `malha_corrida_ativa` nasce em `0`, ninguém abre corrida, e sem a trava as 40
   malhas amanheceriam âmbar gritando "não abriu" sobre uma configuração;
2. **só malha ATIVA**;
3. **só gatilho que existe hoje** — sábado de uma malha "só dias úteis" não é
   atraso, é sábado;
4. **folga configurável** — o scheduler não dispara no segundo do relógio.
"""
from __future__ import annotations

import os
import sys
from datetime import date, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()
os.environ.setdefault("MSSQL_CONN_STR", "__mock__")
from api.main import app as _app  # noqa: F401  (ordem de import)

from deps import PERM_EDITAR, PERM_EXECUTAR, get_current_user
from routers import malhas as router
from services import malha_corrida as mc
from tests.test_malha_corrida_porta import AGORA_API, AGORA_BANCO
from tests.test_malhas_f4_card import FakeCur as FakeCurF4, FakeDb as FakeDbF4
from tests.test_malhas_f4_card import _card, _patch, _patch_agora
from tests.test_malhas_f10 import _monta_malha

ODATE = date(2026, 8, 5)          # quarta-feira
ONTEM = date(2026, 8, 4)


# ═════════════════ dublê: o da F4 + o relógio da Decisão 58 ══════════════════

class FakeCur(FakeCurF4):
    """Acrescenta UMA resposta: o statement que traz, de uma vez, o relógio do
    BANCO e a folga configurável.

    Ele é a razão de esta suíte existir com dublê próprio: nas outras o SQL cai
    no `raise AssertionError` do dublê base, o router degrada (aditivo nunca
    derruba a lista) e `corrida_esperada` simplesmente não sai. Aqui ele
    responde — e responde com o relógio DESLOCADO."""

    def execute(self, sql, params=()):
        s = " ".join(str(sql).split())
        if s.startswith("SELECT GETDATE(), (SELECT TOP 1 config_value"):
            self.db.sqls.append(s)
            self._rows = [(self.db.agora_banco,
                           self.db.config.get(router.CHAVE_FOLGA_NAO_ABRIU))]
            self.rowcount = -1
            return
        return super().execute(sql, params)


class FakeDb(FakeDbF4):
    pass


FakeDb.cursor = lambda self: _cursor(self)


def _cursor(db):
    import copy
    db._snapshot = copy.deepcopy(db._estado())
    return FakeCur(db)


def _pipes(**over):
    """Cadastro dos pipelines. O agendamento default é **diário 01:00** — o
    horário da spec, e o que faz `AGORA_API` (07:00) já tê-lo vencido."""
    base = {"active": 1, "criticidade": "Media", "depends_on": None,
            "scheduled_time": "01:00:00", "schedule_type": "daily",
            "schedule_hour": 1, "schedule_minute": 0, "schedule_dow": 1,
            "schedule_dom": 1, "horarios_especificos": None,
            "dias_semana": None, "dias_horarios_mes": None,
            "somente_dias_uteis": 0, "calendario_nome": None,
            "hora_virada": None, "agenda_no": None, "dag_criada": 1}
    base.update(over)
    return {nome: dict(base) for nome in ("A", "B")}


@pytest.fixture(autouse=True)
def _sem_cache():
    mc.limpar_cache()
    yield
    mc.limpar_cache()


@pytest.fixture
def auth(app):
    app.dependency_overrides[get_current_user] = lambda: {
        "matricula": "OPER1", "perfil": "operador",
        "permissoes": [PERM_EDITAR, PERM_EXECUTAR, "tela_malha"],
    }
    yield
    app.dependency_overrides.pop(get_current_user, None)


def _com_corrida_de_ontem(db, client, status="CONCLUIDA", montar=True):
    """A malha que RODOU ontem e não abriu hoje — o cenário da Decisão 58.

    A corrida de ontem é o que dá direito ao aviso (trava 1): ela é a prova de
    que o registro funciona para esta malha."""
    if montar:
        _monta_malha(client, "M1", ["A", "B"])
    return db.abrir_corrida("M1", odate=ONTEM,
                            aberta_em=datetime(2026, 8, 4, 1, 10),
                            membros=["A", "B"], status=status)


# ═════════════════════════ o estado que faltava ══════════════════════════════

def test_card_diz_nao_abriu_quando_o_gatilho_venceu_e_ninguem_abriu(client, auth):
    """O aceite literal: DAG do Início pausada, 01:00 vencido, nenhuma corrida
    de hoje. O card deixa de mostrar a de ontem como se fosse a resposta."""
    db = FakeDb(pipelines=_pipes())
    with _patch(db), _patch_agora():
        _com_corrida_de_ontem(db, client)
        card = _card(client.get("/malhas"))

    e = card["corrida_esperada"]
    assert e["previsto_para"] == "01:00"
    assert e["data_referencia"] == "2026-08-05"
    # 01:00 → 07:00 no relógio do PROCESSO. Se a conta usasse o relógio do
    # banco (10:00) contra o horário do cron, sairia 540 — 3h de atraso
    # inventado pelo desvio, todo dia, na malha saudável.
    assert e["atrasada_min"] == 360
    assert e["bloqueada_por_corrida_aberta"] is False
    # A corrida de ONTEM continua no payload: ela é o contexto ("está pior que
    # ontem?"), não a manchete.
    assert card["corrida"]["data_referencia"] == "2026-08-04"


def test_corrida_que_abriu_no_horario_nao_vira_alarme(client, auth):
    """A malha rodou: `aberta_em` (régua do BANCO) é depois do previsto
    convertido para a mesma régua. Sem a conversão, 01:10 local viraria "antes
    das 01:00 do banco" e o card acusaria a malha que abriu no horário."""
    db = FakeDb(pipelines=_pipes())
    with _patch(db), _patch_agora():
        _com_corrida_de_ontem(db, client)
        # 01:10 no relógio local = 04:10 na régua do banco (desvio de 3h).
        db.abrir_corrida("M1", odate=ODATE,
                         aberta_em=datetime(2026, 8, 5, 4, 10),
                         membros=["A", "B"])
        card = _card(client.get("/malhas"))

    assert "corrida_esperada" not in card
    assert card["corrida"]["data_referencia"] == "2026-08-05"


def test_desvio_do_banco_nao_inventa_atraso_nem_esconde_corrida(client, auth):
    """A prova do desvio nas DUAS pontas, num teste só: a corrida abriu
    exatamente no limite (previsto + desvio) e o aviso some; um minuto ANTES
    dela ele existe, com o atraso medido na régua certa."""
    db = FakeDb(pipelines=_pipes())
    with _patch(db), _patch_agora():
        _com_corrida_de_ontem(db, client)
        # previsto local 01:00 → 04:00 no banco. Abrir 1 min ANTES disso é uma
        # corrida de outro ciclo (madrugada anterior), não a de hoje.
        db.abrir_corrida("M1", odate=ODATE,
                         aberta_em=datetime(2026, 8, 5, 3, 59),
                         membros=["A", "B"])
        antes = _card(client.get("/malhas"))
    assert antes["corrida_esperada"]["atrasada_min"] == 360

    db2 = FakeDb(pipelines=_pipes())
    with _patch(db2), _patch_agora():
        _com_corrida_de_ontem(db2, client)
        db2.abrir_corrida("M1", odate=ODATE,
                          aberta_em=datetime(2026, 8, 5, 4, 0),
                          membros=["A", "B"])
        no_ponto = _card(client.get("/malhas"))
    assert "corrida_esperada" not in no_ponto


def test_corrida_de_ontem_ainda_aberta_diz_que_e_ela_que_segura(client, auth):
    """A porta está trancada por dentro: a corrida de ontem continua ABERTA e é
    ela que impede a de hoje de nascer (o índice de corrida única).

    Muda a AÇÃO — não é "o Airflow morreu", é "alguém precisa fechar a de
    ontem" —, e por isso é campo do payload, não texto adivinhado na tela."""
    db = FakeDb(pipelines=_pipes())
    with _patch(db), _patch_agora():
        _com_corrida_de_ontem(db, client, status="ABERTA")
        card = _card(client.get("/malhas"))

    assert card["corrida_esperada"]["bloqueada_por_corrida_aberta"] is True
    assert card["corrida"]["status"] == "ABERTA"


# ═══════════════════ as quatro travas contra o alarme falso ══════════════════

def test_dia_do_deploy_a_lista_inteira_fica_muda(client, auth):
    """TRAVA 1 — a mais importante das quatro.

    Com o interruptor em `0` (o estado do dia do deploy) ninguém abre corrida.
    Sem esta trava, TODA malha com gatilho vencido amanheceria com "não abriu"
    em âmbar e o operador chegaria de manhã com 100% da lista gritando sobre
    uma configuração. A corrida anterior é o que dá direito ao aviso."""
    db = FakeDb(pipelines=_pipes())
    assert db.config[mc.CHAVE_ATIVA] == "0"
    with _patch(db), _patch_agora():
        _monta_malha(client, "M1", ["A", "B"])       # nenhuma corrida, nunca
        card = _card(client.get("/malhas"))

    assert "corrida_esperada" not in card
    assert "corrida" not in card
    # E o relógio do banco nem chega a ser lido: sem candidato, zero consulta.
    assert not [s for s in db.sqls if s.startswith("SELECT GETDATE(),")]


def test_malha_inativa_nao_acusa_atraso(client, auth):
    """TRAVA 2 — malha inativada não dispara nada, por definição. Acusá-la de
    atraso é pedir ao operador que conserte o que ele desligou."""
    db = FakeDb(pipelines=_pipes())
    with _patch(db), _patch_agora():
        _com_corrida_de_ontem(db, client)
        assert client.patch("/malhas/M1", json={"ativo": False}).status_code == 200
        card = _card(client.get("/malhas"))

    assert "corrida_esperada" not in card


def test_sabado_de_malha_so_dias_uteis_nao_e_atraso(client, auth):
    """TRAVA 3 — o gatilho que não existe HOJE não vence hoje.

    08/08/2026 é sábado. Com `somente_dias_uteis`, o horário não é previsto no
    fim de semana — e o card que gritasse todo sábado é o alarme falso semanal
    que treina o operador a ignorar o alarme (Decisões 26/27)."""
    sabado = datetime(2026, 8, 8, 7, 0)
    db = FakeDb(pipelines=_pipes(somente_dias_uteis=1),
                agora_banco=sabado + timedelta(hours=3))
    with _patch(db), patch("routers.malhas._agora", return_value=sabado):
        _monta_malha(client, "M1", ["A", "B"])
        db.abrir_corrida("M1", odate=date(2026, 8, 7),
                         aberta_em=datetime(2026, 8, 7, 4, 10),
                         membros=["A", "B"], status="CONCLUIDA")
        card = _card(client.get("/malhas"))

    assert "corrida_esperada" not in card


def test_folga_segura_a_latencia_normal_do_scheduler(client, auth):
    """TRAVA 4 — o Airflow não dispara no segundo do relógio, e a corrida só
    nasce quando a primeira raiz parte. Dentro da folga, silêncio."""
    quase = datetime(2026, 8, 5, 1, 10)         # 10 min depois do previsto
    db = FakeDb(pipelines=_pipes(), agora_banco=quase + timedelta(hours=3))
    with _patch(db), patch("routers.malhas._agora", return_value=quase):
        _com_corrida_de_ontem(db, client)
        dentro = _card(client.get("/malhas"))
    assert "corrida_esperada" not in dentro

    # ...e a folga é CONFIGURÁVEL: com 5 min, os mesmos 10 já acusam.
    db2 = FakeDb(pipelines=_pipes(), agora_banco=quase + timedelta(hours=3))
    db2.config[router.CHAVE_FOLGA_NAO_ABRIU] = "5"
    with _patch(db2), patch("routers.malhas._agora", return_value=quase):
        _com_corrida_de_ontem(db2, client)
        fora = _card(client.get("/malhas"))
    assert fora["corrida_esperada"]["atrasada_min"] == 10


def test_feriado_no_calendario_nao_vira_atraso(client, auth):
    """A quinta trava, que só existe no servidor: o calendário de feriados.

    Feriado é exatamente o dia em que nada roda. E quando o calendário não
    responde, o silêncio também vale — acusar atraso no Natal por causa de um
    lock é o alarme falso mais caro que esta tela poderia inventar."""
    db = FakeDb(pipelines=_pipes(calendario_nome="BR"))
    with _patch(db), _patch_agora():
        _com_corrida_de_ontem(db, client)
        card = _card(client.get("/malhas"))

    assert "corrida_esperada" not in card


# ═════════════ Decisão 45 — o relógio do FECHAMENTO no payload ═══════════════

def test_corrida_cheia_traz_a_regra_e_a_hora_do_fechamento(client, auth):
    """`quiescencia_min` (a REGRA) e `quiescencia_ate` (a HORA), nessa ordem.

    Sem os dois, o card com todos os membros prontos teria de escolher entre
    calar (e o operador reportar bug às 04:03, com tudo verde e a malha ainda
    "em andamento") ou dizer "concluída" 15 minutos antes de a corrida fechar.

    A soma é do BANCO (`DATEADD`): somá-la em Python devolveria um instante na
    régua errada — aqui, 3h adiantado."""
    db = FakeDb(pipelines=_pipes())
    with _patch(db), _patch_agora():
        _monta_malha(client, "M1", ["A", "B"])
        c = db.abrir_corrida("M1", odate=ODATE,
                             aberta_em=datetime(2026, 8, 5, 4, 10),
                             membros=["A", "B"])
        for p in ("A", "B"):
            db.execucao(p, "SUCESSO", inicio=datetime(2026, 8, 5, 4, 20),
                        fim=datetime(2026, 8, 5, 7, 2), corrida=c["id"])
        corrida = _card(client.get("/malhas"))["corrida"]

    assert corrida["status"] == "ABERTA"
    assert (corrida["membros_ok"], corrida["membros_total"]) == (2, 2)
    assert corrida["quiescencia_min"] == mc.QUIESCENCIA_MIN_PADRAO
    # 07:02 (último movimento, régua do banco) + 15 min.
    assert corrida["quiescencia_ate"] == "2026-08-05 07:17:00"


def test_sem_movimento_nenhum_nao_ha_hora_de_fechamento(client, auth):
    """Corrida recém-aberta, nenhum membro com linha: `quiescencia_ate` é
    `null`. A carência conta do último MOVIMENTO — inventar "por volta de" a
    partir da abertura seria promessa, não medida."""
    db = FakeDb(pipelines=_pipes())
    with _patch(db), _patch_agora():
        _monta_malha(client, "M1", ["A", "B"])
        db.abrir_corrida("M1", odate=ODATE, aberta_em=AGORA_BANCO,
                         membros=["A", "B"])
        corrida = _card(client.get("/malhas"))["corrida"]

    assert corrida["quiescencia_ate"] is None
    assert corrida["quiescencia_min"] == mc.QUIESCENCIA_MIN_PADRAO


def test_orcamento_de_consultas_nao_muda_por_causa_do_aviso(client, auth):
    """O bloco da corrida continua custando DUAS consultas para a lista
    inteira, e o aviso acrescenta UMA — o relógio —, nunca uma por malha.

    Um `_relogio_e_folga` por candidato seria N+1 exatamente na madrugada em
    que várias malhas não abriram."""
    db = FakeDb(pipelines=_pipes())
    with _patch(db), _patch_agora():
        for nome in ("M1", "M2", "M3"):
            _monta_malha(client, nome, ["A", "B"])
            db.abrir_corrida(nome, odate=ONTEM,
                             aberta_em=datetime(2026, 8, 4, 1, 10),
                             membros=["A", "B"], status="CONCLUIDA")
        db.sqls.clear()
        resp = client.get("/malhas")

    assert all(m.get("corrida_esperada") for m in resp.json()["malhas"])
    assert len([s for s in db.sqls if "etl_malha_execucao" in s]) == 2
    assert len([s for s in db.sqls if s.startswith("SELECT GETDATE(),")]) == 1


def test_relogio_do_banco_mudo_cala_o_aviso(client, auth):
    """Sem o relógio do BANCO não há aviso — e não há palpite.

    Cair no relógio do processo publicaria "atrasada há 3h" às 01:05 no dev,
    um alarme inventado pelo desvio. A lista continua de pé, com a corrida
    anterior no card: é o comportamento de antes desta fase, não um terceiro
    comportamento."""
    db = FakeDb(pipelines=_pipes())

    class SemRelogio(FakeCur):
        def execute(self, sql, params=()):
            s = " ".join(str(sql).split())
            if s.startswith("SELECT GETDATE(), (SELECT TOP 1 config_value"):
                raise RuntimeError("lock timeout em etl_app_config")
            return super().execute(sql, params)

    with _patch(db), _patch_agora(), \
            patch.object(FakeDb, "cursor", lambda self: SemRelogio(self)):
        _com_corrida_de_ontem(db, client)
        card = _card(client.get("/malhas"))

    assert "corrida_esperada" not in card
    assert card["corrida"]["data_referencia"] == "2026-08-04"


# ═══════════ o julgamento do agendamento, sem passar pelo endpoint ═══════════

def test_horarios_do_dia_espelha_a_regra_do_front():
    """`_horarios_do_dia` é o gêmeo de `horariosDoDia` (proximaExecucao.ts).

    As duas leem o MESMO JSON: se divergirem, o card acusa "não abriu" enquanto
    o rodapé do diagrama diz "próxima execução: hoje 01:00" sobre o mesmo
    agendamento e o mesmo relógio."""
    quarta, sabado = date(2026, 8, 5), date(2026, 8, 8)
    diario = {"schedule_type": "daily", "schedule_hour": 1, "schedule_minute": 0}
    assert router._horarios_do_dia(diario, quarta) == ["01:00"]

    # dow 0 = DOMINGO (D05) — 3 é quarta.
    semanal = {"schedule_type": "weekly", "schedule_hour": 2,
               "schedule_minute": 30, "schedule_dow": 3}
    assert router._horarios_do_dia(semanal, quarta) == ["02:30"]
    assert router._horarios_do_dia(semanal, sabado) == []

    custom = {"schedule_type": "custom", "horarios_especificos": "6:05,01:00",
              "dias_semana": "1,2,3"}
    assert router._horarios_do_dia(custom, quarta) == ["01:00", "06:05"]
    assert router._horarios_do_dia(custom, sabado) == []

    mensal = {"schedule_type": "monthly_days_times",
              "dias_horarios_mes": '[{"dia": 5, "horarios": ["03:00"]}]'}
    assert router._horarios_do_dia(mensal, quarta) == ["03:00"]

    # Cadência não é instante: `hourly` não promete horário nenhum, e tipo
    # desconhecido/`on_demand` também não.
    for st in ("hourly", "on_demand", "coisa_nova"):
        assert router._horarios_do_dia({"schedule_type": st}, quarta) == []
    # JSON estragado degrada para "não sei", nunca para exceção.
    assert router._horarios_do_dia(
        {"schedule_type": "monthly_days_times",
         "dias_horarios_mes": "{isto não é json"}, quarta) == []


def test_o_previsto_e_o_PRIMEIRO_gatilho_do_ciclo():
    """Malha com raízes às 01:00 e às 06:00: quem abre a corrida é a primeira.

    Eleger as 06:00 como "previsto" faria o card acusar "não abriu" às 06:15 de
    uma malha que abriu, rodou e está saudável desde a 01:10 — os membros das
    06:00 entram na corrida que já está aberta."""
    agora = datetime(2026, 8, 5, 7, 0)
    ags = [{"schedule_type": "daily", "schedule_hour": 6, "schedule_minute": 0},
           {"schedule_type": "daily", "schedule_hour": 1, "schedule_minute": 0}]
    assert router._primeiro_previsto(ags, agora) == datetime(2026, 8, 5, 1, 0)

    # Antes do primeiro horário do dia, o previsto é o de ONTEM — e é ele que a
    # corrida de ontem satisfaz sozinha. A janela de 24h é o que impede o
    # "atrasada há 6 dias" de uma malha semanal que rodou na terça.
    madrugada = datetime(2026, 8, 5, 0, 30)
    assert router._primeiro_previsto(ags, madrugada) == datetime(2026, 8, 4, 1, 0)
    semanal = [{"schedule_type": "weekly", "schedule_hour": 1,
                "schedule_minute": 0, "schedule_dow": 2}]   # terça
    assert router._primeiro_previsto(semanal, agora) is None
