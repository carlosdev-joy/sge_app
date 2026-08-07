"""
F12 da spec `docs/spec-malha-execucao.md` — o **histórico FACTUAL** (§9.7,
Decisão 68), a **auditoria completa** (Decisão 67) e o `travou` da faixa.

Esta suíte prova o SERVIDOR; o que o operador LÊ está em
`test_malhas_f12_historico_front.py`.

── A fronteira que esta fase existe para respeitar ─────────────────────────
**Contar desfechos PASSADOS não é previsão.** A proibição de backfill do §3 é
contra INVENTAR corrida retroativa; ler as corridas que de fato existiram é
fato registrado, e sai do mesmo `ix_malha_exec_malha` que esta camada já usa.

Nada aqui prevê nada, e é por isso que cada número vem com o próprio
denominador: `falhou 2 das últimas 7` é uma contagem com amostra declarada, e
`n = 0` é AUSÊNCIA — a chave nem existe no payload.

── ⚠️ O ACEITE QUE MANDA: o dia 1 ──────────────────────────────────────────
Esta é a única fase da spec que depende de corrida real gravada. Antes do smoke
o histórico é literalmente ZERO, e o primeiro teste daqui é esse: com nenhuma
corrida fechada, o payload sai SEM a chave `historico`, o card volta a ser o da
F11 byte a byte, e nada quebra.

── O que mais se prova aqui, e por que ────────────────────────────────────
  • **`SEM_TRABALHO` fica FORA da janela do "falhou X de Y"** — numa malha
    "seg a sex" dois dos últimos sete ciclos são sábado e domingo, e contá-los
    diria "falhou 2 das últimas 7" sobre 5 madrugadas que tiveram trabalho: o
    número certo com o denominador errado;
  • **`CANCELADA` não é falha, mas conta no denominador** — encerrar à mão é
    gesto humano deliberado, e somá-lo a "falhou" faria a malha em que o
    operador agiu certo parecer a malha que quebrou;
  • **a TERÇA atípica × o SÁBADO legítimo** — a comparação é com o MESMO dia
    da semana, e é ela que impede o alarme de sábado toda semana (Decisão 26);
  • **"anterior" é anterior À LENTE** — com `?corrida={id}` numa corrida antiga,
    chamar de anterior uma corrida POSTERIOR inverteria a resposta de "está
    pior que ontem?";
  • **degradação por AUSÊNCIA DE CHAVE** (Decisão 41): erro de leitura devolve
    200 sem `historico`, nunca 500 e nunca `historico: null`;
  • **o custo é CONSTANTE** — uma consulta de conjunto para a lista inteira, e
    a do dia da semana só quando existe malha `SEM_TRABALHO` agora.

⚠️ O interruptor `malha_corrida_ativa` fica DESLIGADO (o estado do dev e o do
dia do deploy): a LEITURA do histórico não depende dele.
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
from api.main import app as _app  # noqa: F401  (ordem de import — ver test_copias.py)

from routers import malhas as malhas_router
from tests.test_malha_corrida_agregado_f10 import FakeCur, FakeDb
from tests.test_malhas_f4_card import (ODATE, _card, _patch,  # noqa: F401
                                       _patch_agora, _pipes, auth)
from tests.test_malhas_f10 import _monta_malha

AGORA_BANCO = datetime(2026, 8, 5, 10, 0, 0)
# 2026-08-05 é uma QUARTA; 2026-08-04, terça; 2026-08-08, sábado.
TERCA = date(2026, 8, 4)
SABADO = date(2026, 8, 8)

MEMBROS = ["A", "B"]


def _fechada(db, malha, odate, status, *, seq_dia=None, aberta=None,
             fechada_por="guardia", motivo=None, tentativas=1,
             reaberta_por=None):
    """Uma corrida JÁ FECHADA no histórico da malha.

    Escrever a linha direto é o certo: o cenário é "isto aconteceu nas
    madrugadas anteriores", e fabricá-lo pela API misturaria o que se prova com
    o que se prepara."""
    ab = aberta or datetime(odate.year, odate.month, odate.day, 1, 10)
    linha = db.abrir_corrida(malha, odate=odate, aberta_em=ab,
                             membros=MEMBROS, status=status)
    linha["fechada_em"] = ab + timedelta(hours=2, minutes=52)
    linha["fechada_por"] = fechada_por
    linha["motivo"] = motivo
    linha["tentativas"] = tentativas
    linha["reaberta_por"] = reaberta_por
    if seq_dia is not None:
        linha["sequencia"] = seq_dia
    return linha


def _historico(resp, malha="M1"):
    return _card(resp, malha).get("historico")


# ═════════════════ O ACEITE DO DIA 1 — histórico ZERO ══════════════════════

def test_dia_1_o_payload_sai_SEM_a_chave_historico(client, auth):
    """*"histórico com **zero** corridas fechadas (dia 1) → nenhuma das frases
    desta fase é renderizada, e nada quebra"*.

    A corrida de hoje está ABERTA e é a primeira da malha: não existe corrida
    anterior a que comparar. A chave `historico` NÃO SAI — ausência, nunca
    `{"falhou": 0, "consideradas": 0}`, que seria um número sem amostra com
    cara de medida."""
    db = FakeDb(pipelines=_pipes())
    with _patch(db), _patch_agora():
        _monta_malha(client, "M1", MEMBROS)
        db.abrir_corrida("M1", odate=ODATE,
                         aberta_em=AGORA_BANCO - timedelta(hours=2),
                         membros=MEMBROS)
        resp = client.get("/malhas")
    card = _card(resp)
    assert "historico" not in card
    # E o resto do card continua inteiro: "nada quebra" é a outra metade.
    assert card["corrida"]["status"] == "ABERTA"
    assert card["corrida"]["membros_total"] == 2


def test_dia_1_a_lente_do_painel_tambem_se_cala(client, auth):
    db = FakeDb(pipelines=_pipes())
    with _patch(db), _patch_agora():
        _monta_malha(client, "M1", MEMBROS)
        c = db.abrir_corrida("M1", odate=ODATE,
                             aberta_em=AGORA_BANCO - timedelta(hours=2),
                             membros=MEMBROS)
        resp = client.get(f"/malhas/M1/execucao?corrida={c['id']}")
    assert resp.status_code == 200
    assert "historico" not in resp.json()


# ═════════════════ `falhou X das últimas Y` ════════════════════════════════

def test_a_janela_conta_desfechos_e_declara_o_denominador(client, auth):
    """7 ciclos fechados antes da corrente, 2 delas com desfecho ruim."""
    db = FakeDb(pipelines=_pipes())
    with _patch(db), _patch_agora():
        _monta_malha(client, "M1", MEMBROS)
        for i, status in enumerate(["CONCLUIDA", "FALHA", "CONCLUIDA",
                                    "EXPIRADA", "CONCLUIDA", "CONCLUIDA",
                                    "CONCLUIDA"]):
            _fechada(db, "M1", ODATE - timedelta(days=i + 1), status)
        db.abrir_corrida("M1", odate=ODATE,
                         aberta_em=AGORA_BANCO - timedelta(hours=2),
                         membros=MEMBROS)
        h = _historico(client.get("/malhas"))
    assert h["falhou"] == 2
    assert h["consideradas"] == 7
    assert h["janela"] == malhas_router.JANELA_HISTORICO


def test_sem_trabalho_nao_entra_na_janela(client, auth):
    """Numa malha "seg a sex", dois dos últimos sete ciclos são fim de semana.

    Contá-los no denominador diria "falhou 1 das últimas 7" sobre 5 madrugadas
    que de fato tiveram trabalho — dia sem trabalho não teve CHANCE de falhar,
    e um denominador inflado é o mesmo defeito da barra que não encolhe."""
    db = FakeDb(pipelines=_pipes())
    with _patch(db), _patch_agora():
        _monta_malha(client, "M1", MEMBROS)
        _fechada(db, "M1", ODATE - timedelta(days=1), "FALHA")
        _fechada(db, "M1", ODATE - timedelta(days=2), "SEM_TRABALHO")
        _fechada(db, "M1", ODATE - timedelta(days=3), "SEM_TRABALHO")
        _fechada(db, "M1", ODATE - timedelta(days=4), "CONCLUIDA")
        db.abrir_corrida("M1", odate=ODATE, aberta_em=AGORA_BANCO,
                         membros=MEMBROS)
        h = _historico(client.get("/malhas"))
    assert h["consideradas"] == 2, "os dois dias sem trabalho entraram na conta"
    assert h["falhou"] == 1


def test_cancelada_nao_e_falha_mas_conta_no_denominador(client, auth):
    """Encerrar à mão é gesto humano deliberado: somá-lo a "falhou" faria a
    malha em que o operador AGIU CERTO parecer a malha que quebrou.

    Ela continua no denominador — foi uma corrida com trabalho —, e o motivo
    dela aparece na auditoria da Decisão 67, que é o lugar dela."""
    db = FakeDb(pipelines=_pipes())
    with _patch(db), _patch_agora():
        _monta_malha(client, "M1", MEMBROS)
        _fechada(db, "M1", ODATE - timedelta(days=1), "CANCELADA",
                 fechada_por="manual:C123456",
                 motivo="encerrada por C123456: carga refeita por fora")
        _fechada(db, "M1", ODATE - timedelta(days=2), "CONCLUIDA")
        db.abrir_corrida("M1", odate=ODATE, aberta_em=AGORA_BANCO,
                         membros=MEMBROS)
        h = _historico(client.get("/malhas"))
    assert h["falhou"] == 0
    assert h["consideradas"] == 2


def test_a_corrente_nunca_conta_contra_si_mesma(client, auth):
    """A corrida em foco sai da janela: uma corrida que acabou de falhar não
    pode ser contada como "histórico" dela própria — o card já diz o estado
    dela na linha de cima, e o histórico responde outra pergunta."""
    db = FakeDb(pipelines=_pipes())
    with _patch(db), _patch_agora():
        _monta_malha(client, "M1", MEMBROS)
        _fechada(db, "M1", ODATE - timedelta(days=1), "CONCLUIDA")
        _fechada(db, "M1", ODATE, "FALHA", aberta=AGORA_BANCO)
        h = _historico(client.get("/malhas"))
    assert h["falhou"] == 0
    assert h["consideradas"] == 1


# ═════════════════ `corrida anterior: …` (a faixa) ═════════════════════════

def test_a_anterior_e_a_de_ontem_com_as_duas_pontas(client, auth):
    db = FakeDb(pipelines=_pipes())
    with _patch(db), _patch_agora():
        _monta_malha(client, "M1", MEMBROS)
        _fechada(db, "M1", ODATE - timedelta(days=1), "CONCLUIDA")
        db.abrir_corrida("M1", odate=ODATE, aberta_em=AGORA_BANCO,
                         membros=MEMBROS)
        h = _historico(client.get("/malhas"))
    a = h["anterior"]
    assert a["data_referencia"] == "2026-08-04"
    assert a["status"] == "CONCLUIDA"
    assert a["aberta_em"].startswith("2026-08-04 01:10")
    assert a["fechada_em"].startswith("2026-08-04 04:02")


def test_com_a_lente_numa_corrida_antiga_a_anterior_e_a_ANTERIOR_A_ELA(
        client, auth):
    """⚠️ O defeito que este teste existe para pegar.

    Clicar num bloco antigo da faixa é o gesto normal (`?corrida={id}`). Com um
    simples "a primeira da lista que não é a corrente", a faixa escreveria
    "ciclo anterior: 05/08" embaixo da corrida de 03/08 — chamando de
    anterior o que veio DEPOIS, e invertendo a resposta de "está pior que
    ontem?"."""
    db = FakeDb(pipelines=_pipes())
    with _patch(db), _patch_agora():
        _monta_malha(client, "M1", MEMBROS)
        _fechada(db, "M1", ODATE - timedelta(days=3), "CONCLUIDA")
        alvo = _fechada(db, "M1", ODATE - timedelta(days=2), "FALHA")
        _fechada(db, "M1", ODATE - timedelta(days=1), "CONCLUIDA")
        db.abrir_corrida("M1", odate=ODATE, aberta_em=AGORA_BANCO,
                         membros=MEMBROS)
        resp = client.get(f"/malhas/M1/execucao?corrida={alvo['id']}")
    h = resp.json()["historico"]
    assert h["anterior"]["data_referencia"] == "2026-08-02"


# ═════════════════ `SEM_TRABALHO` em dia atípico ═══════════════════════════

def _sem_trabalho_hoje(db, client, dia, passadas):
    """A malha sai `SEM_TRABALHO` em `dia`, com `passadas` ocorrências do MESMO
    dia da semana (uma por semana, para trás) nos status dados."""
    _monta_malha(client, "M1", MEMBROS)
    for i, status in enumerate(passadas):
        _fechada(db, "M1", dia - timedelta(days=7 * (i + 1)), status)
    return _fechada(db, "M1", dia, "SEM_TRABALHO")


def test_terca_sem_trabalho_depois_de_4_tercas_com_trabalho_vira_ambar(
        client, auth):
    """*"malha que rodou nas últimas 4 terças e hoje (terça) sai
    `SEM_TRABALHO` → card **âmbar**"*.

    O caso que SÓ o histórico enxerga: alguém inativa membros numa terça e o
    card fica cinza e mudo, indistinguível de um sábado legítimo."""
    db = FakeDb(pipelines=_pipes())
    with _patch(db), _patch_agora():
        _sem_trabalho_hoje(db, client, TERCA, ["CONCLUIDA"] * 4)
        h = _historico(client.get("/malhas"))
    assert h["dia_semana"]["atipico"] is True
    assert h["dia_semana"]["com_trabalho"] == 4
    assert h["dia_semana"]["encontradas"] == 4


def test_no_sabado_a_MESMA_malha_continua_cinza_e_muda(client, auth):
    """*"no sábado, a mesma malha continua **cinza e muda**"*.

    É a metade que importa: um alarme de sábado toda semana treinaria o
    operador a ignorar o alarme (Decisão 26) — e, com ele, a terça, que era a
    única que importava."""
    db = FakeDb(pipelines=_pipes())
    with _patch(db), _patch_agora():
        _sem_trabalho_hoje(db, client, SABADO, ["SEM_TRABALHO"] * 4)
        h = _historico(client.get("/malhas"))
    assert h["dia_semana"]["atipico"] is False
    assert h["dia_semana"]["com_trabalho"] == 0


def test_tres_ocorrencias_nao_bastam_para_acusar(client, auth):
    """Quatro é um mês de terças. Com três, não se afirma nada: "as últimas 2
    terças tiveram trabalho" não é evidência de nada num calendário com
    feriado, e uma frase com número errado é pior que silêncio."""
    db = FakeDb(pipelines=_pipes())
    with _patch(db), _patch_agora():
        _sem_trabalho_hoje(db, client, TERCA, ["CONCLUIDA"] * 3)
        h = _historico(client.get("/malhas"))
    assert h["dia_semana"]["atipico"] is False
    assert h["dia_semana"]["encontradas"] == 3


def test_uma_terca_sem_trabalho_no_meio_ja_derruba_a_acusacao(client, auth):
    """A regra é "as últimas 4 **tiveram** trabalho" — TODAS. Uma terça sem
    trabalho no meio já significa que este dia não é tão previsível assim, e o
    silêncio volta a ser a resposta certa."""
    db = FakeDb(pipelines=_pipes())
    with _patch(db), _patch_agora():
        _sem_trabalho_hoje(db, client, TERCA,
                           ["CONCLUIDA", "SEM_TRABALHO", "CONCLUIDA",
                            "CONCLUIDA"])
        h = _historico(client.get("/malhas"))
    assert h["dia_semana"]["atipico"] is False
    assert h["dia_semana"]["com_trabalho"] == 3


def test_a_propria_corrida_de_hoje_nao_se_absolve(client, auth):
    """⚠️ A corrente é `SEM_TRABALHO` e é do MESMO dia da semana das outras.

    Sem excluí-la, ela entraria como uma das quatro terças "passadas" — o
    `SEM_TRABALHO` de hoje se auto-absolvendo, em silêncio, exatamente no caso
    que a regra existe para acusar."""
    db = FakeDb(pipelines=_pipes())
    with _patch(db), _patch_agora():
        corrente = _sem_trabalho_hoje(db, client, TERCA, ["CONCLUIDA"] * 4)
        h = _historico(client.get("/malhas"))
    assert h["dia_semana"]["encontradas"] == 4
    assert h["dia_semana"]["atipico"] is True
    assert corrente["status"] == "SEM_TRABALHO"


def test_corrida_normal_nao_pergunta_pelo_dia_da_semana(client, auth):
    """Sem candidato, ZERO consulta a mais: o recorte por dia da semana só
    existe para o `SEM_TRABALHO` corrente, que é raro por construção."""
    db = FakeDb(pipelines=_pipes())
    with _patch(db), _patch_agora():
        _monta_malha(client, "M1", MEMBROS)
        _fechada(db, "M1", ODATE - timedelta(days=1), "CONCLUIDA")
        db.abrir_corrida("M1", odate=ODATE, aberta_em=AGORA_BANCO,
                         membros=MEMBROS)
        db.sqls.clear()
        h = _historico(client.get("/malhas"))
    assert "dia_semana" not in h
    assert not [s for s in db.sqls if "% 7 = ?" in s]


def test_o_recorte_por_dia_da_semana_nao_usa_DATEPART(client, auth):
    """`DATEPART(WEEKDAY)` depende de `SET DATEFIRST`, que varia com o idioma
    da conexão — e a instalação da Caixa pode estar em pt-BR. O
    `DATEDIFF(DAY, '19000101', d) % 7` é determinístico e independe de
    configuração de sessão."""
    db = FakeDb(pipelines=_pipes())
    with _patch(db), _patch_agora():
        _sem_trabalho_hoje(db, client, TERCA, ["CONCLUIDA"] * 4)
        db.sqls.clear()
        client.get("/malhas")
    do_dia = [s for s in db.sqls if "% 7 = ?" in s]
    assert len(do_dia) == 1, do_dia
    assert "DATEPART" not in do_dia[0]


# ═════════════════ degradação: aditivo nunca derruba a tela ════════════════

def test_erro_na_leitura_do_historico_devolve_200_sem_a_chave(client, auth):
    """Decisão 41 — a degradação é por AUSÊNCIA DE CAMPO.

    A lista de malhas é a tela de ENTRADA: um lock em `etl_malha_execucao` às
    3h não pode transformá-la em 500, e o card sem histórico é exatamente o
    card da F11 — não um terceiro comportamento inventado."""
    db = FakeDb(pipelines=_pipes())

    class SemHistorico(FakeCur):
        def execute(self, sql, params=()):
            s = " ".join(str(sql).split())
            if s.startswith("SELECT malha_name, id, data_referencia"):
                raise RuntimeError("lock timeout em etl_malha_execucao")
            return super().execute(sql, params)

    with _patch(db), _patch_agora(), \
            patch.object(FakeDb, "cursor", lambda self: SemHistorico(self)):
        _monta_malha(client, "M1", MEMBROS)
        _fechada(db, "M1", ODATE - timedelta(days=1), "FALHA")
        db.abrir_corrida("M1", odate=ODATE, aberta_em=AGORA_BANCO,
                         membros=MEMBROS)
        resp = client.get("/malhas")
    assert resp.status_code == 200
    card = _card(resp)
    assert "historico" not in card
    assert card["corrida"]["status"] == "ABERTA"


def test_erro_no_dia_da_semana_mantem_o_resto_do_historico(client, auth):
    """A pergunta do dia atípico é a MAIS aditiva de todas: se ela falhar, o
    `SEM_TRABALHO` segue cinza (o comportamento de antes desta fase) e o
    "falhou X de Y" continua na tela."""
    db = FakeDb(pipelines=_pipes())

    class SemDia(FakeCur):
        def execute(self, sql, params=()):
            s = " ".join(str(sql).split())
            if s.startswith("SELECT malha_name, id, status FROM ("):
                raise RuntimeError("lock timeout")
            return super().execute(sql, params)

    with _patch(db), _patch_agora(), \
            patch.object(FakeDb, "cursor", lambda self: SemDia(self)):
        _sem_trabalho_hoje(db, client, TERCA, ["CONCLUIDA"] * 4)
        resp = client.get("/malhas")
    h = _historico(resp)
    assert resp.status_code == 200
    assert "dia_semana" not in h
    assert h["consideradas"] == 4


# ═════════════════ auditoria na LISTA de corridas (Decisão 67) ═════════════

def test_a_lista_de_corridas_traz_reaberta_por(client, auth):
    """`reaberta 1x` sem dizer POR QUEM é meia auditoria: na hora de explicar o
    fechamento do mês, ela não vale mais que nenhuma. O campo existia no
    payload do CARD e não existia na LISTA."""
    db = FakeDb(pipelines=_pipes())
    with _patch(db), _patch_agora():
        _monta_malha(client, "M1", MEMBROS)
        _fechada(db, "M1", ODATE - timedelta(days=1), "CANCELADA",
                 fechada_por="manual:C123456",
                 motivo="encerrada por C123456: carga remarcada",
                 tentativas=2, reaberta_por="manual:C999999")
        resp = client.get("/malhas/M1/corridas")
    c = resp.json()["corridas"][0]
    assert c["reaberta_por"] == "manual:C999999"
    assert c["fechada_por"] == "manual:C123456"
    assert c["motivo"] == "encerrada por C123456: carga remarcada"
    assert c["origem"] == "inicio"
    assert c["tentativas"] == 2


def test_a_lista_de_corridas_nomeia_quem_travou(client, auth):
    """Decisão 68 — o `title` do bloco da faixa: `04/08 · falhou · 2h41 ·
    travou: CARGA_A`.

    É o que transforma dez quadradinhos coloridos em diagnóstico. E o nome sai
    da MESMA classificação do card (o módulo gêmeo), nunca de um parse do
    texto que a guardiã escreveu no `motivo`."""
    db = FakeDb(pipelines=_pipes())
    ontem = ODATE - timedelta(days=1)
    with _patch(db), _patch_agora():
        _monta_malha(client, "M1", MEMBROS)
        c = _fechada(db, "M1", ontem, "FALHA")
        db.execucao("A", "SUCESSO", odate=ontem,
                    inicio=datetime(2026, 8, 4, 1, 15),
                    fim=datetime(2026, 8, 4, 1, 40), corrida=c["id"])
        db.execucao("B", "FALHA", odate=ontem,
                    inicio=datetime(2026, 8, 4, 1, 45),
                    fim=datetime(2026, 8, 4, 2, 0), corrida=c["id"])
        resp = client.get("/malhas/M1/corridas")
    linha = resp.json()["corridas"][0]
    assert linha["travou"] == {"pipeline": "B", "classe": "falhou"}


def test_corrida_limpa_diz_que_ninguem_travou(client, auth):
    """`None` no valor é "apurei e não havia travado" — diferente da chave
    AUSENTE, que é "não apurei". A faixa escreve `travou: X` só na primeira
    leitura e cala nas outras duas, e confundi-las faria a tela afirmar "nada
    travou" sobre madrugadas que ela nem olhou."""
    db = FakeDb(pipelines=_pipes())
    ontem = ODATE - timedelta(days=1)
    with _patch(db), _patch_agora():
        _monta_malha(client, "M1", MEMBROS)
        c = _fechada(db, "M1", ontem, "CONCLUIDA")
        for p in MEMBROS:
            db.execucao(p, "SUCESSO", odate=ontem,
                        inicio=datetime(2026, 8, 4, 1, 15),
                        fim=datetime(2026, 8, 4, 1, 40), corrida=c["id"])
        resp = client.get("/malhas/M1/corridas")
    linha = resp.json()["corridas"][0]
    assert "travou" in linha and linha["travou"] is None


def test_o_travou_e_apurado_so_para_as_corridas_da_faixa(client, auth):
    """A faixa mostra dez blocos e o endpoint aceita `limite` até 200: apurar
    200 snapshots a cada 60 s pagaria por 190 nomes que ninguém vê.

    Fora do teto a chave `travou` simplesmente não sai — o mesmo contrato de
    ausência do resto desta camada."""
    db = FakeDb(pipelines=_pipes())
    with _patch(db), _patch_agora():
        _monta_malha(client, "M1", MEMBROS)
        for i in range(malhas_router._TRAVOU_MAX_CORRIDAS + 3):
            _fechada(db, "M1", ODATE - timedelta(days=i + 1), "CONCLUIDA")
        corridas = client.get("/malhas/M1/corridas?limite=30").json()["corridas"]
    com_chave = [c for c in corridas if "travou" in c]
    assert len(com_chave) == malhas_router._TRAVOU_MAX_CORRIDAS
    assert len(corridas) > len(com_chave)


def test_falha_ao_apurar_o_travou_nao_derruba_a_lista(client, auth):
    """A faixa volta ao `title` de antes desta fase: nenhum bloco some, nenhuma
    cor muda — o que falta é o nome."""
    db = FakeDb(pipelines=_pipes())
    with _patch(db), _patch_agora():
        _monta_malha(client, "M1", MEMBROS)
        _fechada(db, "M1", ODATE - timedelta(days=1), "FALHA")
        db.falhar_denominador = True
        resp = client.get("/malhas/M1/corridas")
    assert resp.status_code == 200
    assert "travou" not in resp.json()["corridas"][0]


# ═════════════════ o texto do SQL: as guardas que o dublê não inventa ══════

def test_a_janela_lida_e_maior_que_a_exibida():
    """A janela exibida é 7 e a LIDA é maior de propósito: descartada a
    corrente e os dias sem trabalho, uma malha "seg a sex" precisa de mais de
    sete linhas para preencher sete madrugadas com trabalho."""
    assert malhas_router._LEITURA_HISTORICO > malhas_router.JANELA_HISTORICO


def test_o_historico_le_so_corrida_FECHADA():
    """Ciclo em voo não é histórico: contá-la como desfecho diria "falhou"
    sobre uma madrugada que ainda pode fechar verde."""
    assert "WHERE fechada_em IS NOT NULL" in malhas_router._SQL_HISTORICO


def test_o_historico_e_uma_consulta_de_CONJUNTO():
    """`ROW_NUMBER() OVER (PARTITION BY malha_name)` — as últimas N de CADA
    malha numa consulta só. Uma leitura por malha seria N+1 na tela de
    entrada, que faz refetch a cada 20 s com corrida em voo."""
    assert "ROW_NUMBER() OVER (PARTITION BY malha_name" \
        in malhas_router._SQL_HISTORICO
    assert "ROW_NUMBER() OVER (PARTITION BY malha_name" \
        in malhas_router._SQL_HISTORICO_DIA
