"""
F7 da corrida de malha — **os relógios**: hold, teto e atraso
(`docs/spec-malha-execucao.md` §6.6/§6.7, Decisões 29, 30, 31, 34, 35 e 61; §18
pendências 12, 14 e 20).

Esta é a última fase antes de `malha_corrida_ativa` poder ir a `1`. Tudo o que
ficar mal resolvido aqui vira comportamento na primeira madrugada.

O QUE ESTA SUÍTE PROTEGE — cada bloco nomeia o defeito que evita:

  1. **o hold é DERIVADO, nunca materializado** (Decisão 30). O teste que
     separa as duas formas é cruel de propósito: com DOIS Aguardes segurados,
     soltar UM não pode destravar os relógios. Um espelho na corrida ("esta
     está retida") seria limpo pelo primeiro `soltar` e o teto voltaria a
     correr com a malha ainda travada;
  2. **o crédito ao soltar o ÚLTIMO nó** — soltar após 6h de hold numa malha
     com teto de 4h empurra o teto em 6h, e a corrida NÃO expirou. E o crédito
     vira EVENTO (Decisão 61): uma barra de prazo que anda para trás em
     silêncio destrói a confiança em todas as outras;
  3. **`MALHA_ATRASADA` × `MALHA_EXPIRADA`** — o teto vencido COM alguém vivo é
     ALARME; sem ninguém vivo é desfecho. Fechar com 8 membros `EXECUTANDO`
     liberaria o disparo por cima deles, e as linhas que terminassem depois
     carregariam id de corrida fechada: mentira estável que refresh nenhum
     corrige. Fechamento mensal com 26h de carga legítima e teto padrão de 24h
     é o caso real;
  4. **Decisão 31 / pendência 12** — `_fechar_dia_anterior` fecha como
     `NAO_LIBEROU` linha de corrida ABERTA que atravesse o dia operacional, e
     esses membros viram pendentes: **a guardiã levando a própria corrida a
     FALHA**. E o mesmo com nó segurado, que é defeito que existe HOJE;
  5. **pendência 14** — a guardiã é a QUARTA porta de disparo e chamava
     `montar_conf` sem `malha_execucao_id`. A data não sofria; a PROVENIÊNCIA
     se perdia justamente no caso que a F5 existe para tratar. E a recusa por
     ODATE ambíguo (Decisão 34) não valia nesta porta;
  6. **nenhuma conta de tempo em Python** — hold, teto e atraso são todos
     relógio, e nesta fase isso é o ASSUNTO. O SQL Server do dev está ~3h à
     frente do worker: qualquer subtração em Python apareceria como erro de 3h.
"""
from __future__ import annotations

import ast
import inspect
import logging
import os
import sys
from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest

if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()
os.environ.setdefault("MSSQL_CONN_STR", "__mock__")
from api.main import app as _app  # noqa: F401,E402  (ordem de import)

from services import malha_corrida as mc  # noqa: E402
from deps import PERM_EDITAR, PERM_EXECUTAR, get_current_user  # noqa: E402

from tests.test_dependencia_guardia_dag import (  # noqa: E402
    AGORA, GUARDIA, HOJE, _cfg, _linha, _mundo)
from tests.test_malha_corrida_guardia import (  # noqa: E402
    AGORA_BANCO, ODATE, _corrida, _corrida_dict, _estado)
from tests.test_malha_corrida_porta import (  # noqa: E402
    AGORA_API, AGORA_BANCO as AGORA_BANCO_API, FakeDb, _patch_agora, _pipes,
    ODATE as ODATE_API)
from tests.test_malhas_f4_card import FakeDb as FakeDbCard  # noqa: E402
from tests.test_malhas_f10 import _cria_no, _monta_malha  # noqa: E402


# ═══════════════════════════════════════════════════════════════════════════
# 1. O HOLD é DERIVADO de MIN(retido_em) — nunca materializado
# ═══════════════════════════════════════════════════════════════════════════

class _CurHold:
    """Cursor de dublê que responde `SQL_HOLD_DA_MALHA` a partir de uma LISTA
    de nós — e recalcula a cada chamada, como o banco faz."""

    def __init__(self, nos, agora=AGORA_BANCO_API):
        self.nos = nos
        self.agora = agora
        self.sqls: list[str] = []
        self._row = None

    def execute(self, sql, params=()):
        self.sqls.append(" ".join(str(sql).split()))
        retidos = sorted((n for n in self.nos if n.get("retido_em")),
                         key=lambda n: (n["retido_em"], n["id"]))
        if not retidos:
            self._row = (0, None, None, None)
            return
        desde = retidos[0]["retido_em"]
        self._row = (len(retidos), desde,
                     int((self.agora - desde).total_seconds() // 60),
                     retidos[0].get("retido_por"))

    def fetchone(self):
        return self._row


def test_hold_sai_do_MIN_e_dois_aguardes_segurados_sao_UM_hold():
    """`MIN(retido_em)` e não `MAX`: o hold começou no PRIMEIRO nó segurado.

    Com A segurado às 01:00 e B às 01:30, o hold tem 2 nós, começou às 01:00 e
    quem aparece nomeado é quem segurou o mais antigo — porque é ele que o
    operador precisa procurar."""
    a = AGORA_BANCO_API - timedelta(hours=2)
    b = AGORA_BANCO_API - timedelta(hours=1)
    cur = _CurHold([{"id": 9, "retido_em": b, "retido_por": "C2"},
                    {"id": 4, "retido_em": a, "retido_por": "C1"}])
    hold = mc.hold_da_malha(cur, "M1")
    assert hold["retido"] is True
    assert hold["nos"] == 2
    assert hold["desde"] == a
    assert hold["minutos"] == 120        # do BANCO, via DATEDIFF
    assert hold["por"] == "C1"


def test_soltar_UM_de_DOIS_aguardes_NAO_destrava_os_relogios():
    """⚠️ O TESTE QUE UM ESPELHO MATERIALIZADO REPROVARIA.

    É por isto que a spec manda DERIVAR: com uma coluna "retida" na corrida, o
    primeiro `soltar` a limparia e o teto voltaria a correr com a malha ainda
    travada — a corrida expirando por causa da trava que o operador pôs.
    Derivado, a resposta continua sendo "retida" enquanto sobrar um nó."""
    nos = [{"id": 4, "retido_em": AGORA_BANCO_API - timedelta(hours=2),
            "retido_por": "C1"},
           {"id": 9, "retido_em": AGORA_BANCO_API - timedelta(hours=1),
            "retido_por": "C2"}]
    cur = _CurHold(nos)
    assert mc.hold_da_malha(cur, "M1")["retido"] is True
    nos[0]["retido_em"] = None           # soltou UM
    hold = mc.hold_da_malha(cur, "M1")
    assert hold["retido"] is True, "soltar um de dois destravou os relogios"
    assert hold["nos"] == 1
    nos[1]["retido_em"] = None           # soltou o ÚLTIMO
    assert mc.hold_da_malha(cur, "M1")["retido"] is False


def test_sem_a_082_nao_ha_retencao_e_com_erro_de_leitura_ha():
    """As duas degradações são OPOSTAS e as duas estão certas: sem a coluna não
    existe nó retido (nada trava); com a coluna presente e a consulta falhando,
    "não consegui perguntar" nunca vira "pode fechar"."""
    class _Sem:
        def execute(self, *a, **k):
            raise Exception("(207) Invalid column name 'retido_em'.")

    class _Timeout:
        def execute(self, *a, **k):
            raise Exception("Lock request time out period exceeded.")

    assert mc.hold_da_malha(_Sem(), "M1")["retido"] is False
    lido = mc.hold_da_malha(_Timeout(), "M1")
    assert lido["retido"] is True
    # `desde=None` com `retido=True` é deliberado: quem escreve na tela não
    # pode inventar um instante que a consulta não devolveu.
    assert lido["desde"] is None and lido["minutos"] == 0


# ═══════════════════════════════════════════════════════════════════════════
# 2. O crédito do teto ao soltar o ÚLTIMO nó (e o EVENTO da Decisão 61)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture
def auth_operador(app):
    """Quem monta a malha E opera (o mesmo par da suíte da porta): segurar/
    soltar é `acao_executar`, montar é `acao_editar`, e o cenário precisa dos
    dois para existir."""
    app.dependency_overrides[get_current_user] = lambda: {
        "matricula": "C123456", "perfil": "operador",
        "permissoes": [PERM_EDITAR, PERM_EXECUTAR, "tela_malha"],
    }
    yield
    app.dependency_overrides.pop(get_current_user, None)


def _patch_db(db):
    return patch("routers.malhas.get_db_conn", side_effect=db.conectar)


def _malha_com_dois_aguardes(client, db, nome="M1"):
    _monta_malha(client, nome, ["RAIZ_A", "RAIZ_B"])
    return [_cria_no(client, nome, "aguarde"), _cria_no(client, nome, "aguarde")]


def _reter(client, no_id, reter, malha="M1"):
    return client.post(f"/malhas/{malha}/nos/{no_id}/retencao",
                       json={"reter": reter})


def test_soltar_apos_6h_de_hold_empurra_o_teto_de_4h_e_a_corrida_NAO_expirou(
        client, auth_operador):
    """O aceite literal da fase: teto de 4h, 6h de hold, e no fim a corrida
    continua ABERTA com o limite 6h adiante.

    Sem o crédito, a malha destravada às 07:00 encontraria a própria corrida
    EXPIRADA às 05:00 — punida pelo tempo em que ela estava, por decisão
    humana, proibida de andar."""
    db = FakeDb(pipelines=_pipes(), com_082=True)
    with _patch_db(db), _patch_agora():
        nos = _malha_com_dois_aguardes(client, db)
        c = db.abrir_corrida("M1", odate=ODATE_API, teto_horas=4,
                             aberta_em=AGORA_BANCO_API - timedelta(hours=7),
                             membros=["RAIZ_A", "RAIZ_B"])
        teto_antes = c["teto_em"]
        # segurado 6h atrás (uma hora depois de a corrida abrir)
        db.nos[nos[0]]["retido_em"] = AGORA_BANCO_API - timedelta(hours=6)
        db.nos[nos[0]]["retido_por"] = "C123456"
        r = _reter(client, nos[0], False)
    assert r.status_code == 200, r.text
    assert c["fechada_em"] is None, "a corrida expirou apesar do hold"
    assert c["teto_creditado_min"] == 360
    assert c["teto_em"] == teto_antes + timedelta(hours=6)
    assert r.json()["credito_teto"]["minutos"] == 360
    # Decisão 61 — o crédito vira EVENTO: a barra não pode recuar em silêncio.
    creditos = [e for e in db.eventos
                if e["tipo"] == mc.EVENTO_TETO_CREDITADO]
    assert len(creditos) == 1
    assert creditos[0]["pipeline_name"] == f"#corrida:{c['id']}"
    # E NÃO vai ao Teams: o gesto é humano e síncrono (o operador acabou de
    # clicar e leu o toast); um card seria o eco do próprio clique dele às 3h.
    assert creditos[0].get("notificado_em") is not None


def test_soltar_UM_de_DOIS_nao_credita_nada_e_o_relogio_segue_parado(
        client, auth_operador):
    """A cláusula `NOT EXISTS (... n2.id <> ?)` do UPDATE, provada pelo efeito:
    com outro Aguarde ainda segurado o teto não anda um minuto — e não anda
    porque o hold NÃO ACABOU, não porque alguém esqueceu de creditar. O
    crédito virá inteiro quando o último for solto."""
    db = FakeDb(pipelines=_pipes(), com_082=True)
    with _patch_db(db), _patch_agora():
        nos = _malha_com_dois_aguardes(client, db)
        c = db.abrir_corrida("M1", odate=ODATE_API, teto_horas=4,
                             aberta_em=AGORA_BANCO_API - timedelta(hours=7),
                             membros=["RAIZ_A", "RAIZ_B"])
        teto_antes = c["teto_em"]
        for no in nos:
            db.nos[no]["retido_em"] = AGORA_BANCO_API - timedelta(hours=6)
            db.nos[no]["retido_por"] = "C123456"
        r1 = _reter(client, nos[0], False)
        assert r1.status_code == 200 and "credito_teto" not in r1.json()
        assert c["teto_em"] == teto_antes and c["teto_creditado_min"] == 0
        r2 = _reter(client, nos[1], False)
    assert "credito_teto" in r2.json()
    assert c["teto_em"] == teto_antes + timedelta(hours=6)


def test_hold_de_menos_de_um_minuto_nao_gera_credito_nem_evento(
        client, auth_operador):
    """"+0h creditados" seria ruído com forma de fato — e o clique errado
    seguido do desfazer imediato é o gesto mais comum de todos."""
    db = FakeDb(pipelines=_pipes(), com_082=True)
    with _patch_db(db), _patch_agora():
        nos = _malha_com_dois_aguardes(client, db)
        db.abrir_corrida("M1", odate=ODATE_API, teto_horas=4,
                         aberta_em=AGORA_BANCO_API - timedelta(hours=1),
                         membros=["RAIZ_A", "RAIZ_B"])
        db.nos[nos[0]]["retido_em"] = AGORA_BANCO_API - timedelta(seconds=20)
        r = _reter(client, nos[0], False)
    assert r.status_code == 200 and "credito_teto" not in r.json()
    assert not [e for e in db.eventos if e["tipo"] == mc.EVENTO_TETO_CREDITADO]


def test_soltar_continua_funcionando_sem_a_085(client, auth_operador):
    """Perder o crédito adia o teto para o valor original; falhar o `soltar`
    deixaria a malha TRAVADA — o oposto do gesto. A degradação escolhe o lado
    certo."""
    db = FakeDb(pipelines=_pipes(), com_082=True, com_085=False)
    with _patch_db(db), _patch_agora():
        nos = _malha_com_dois_aguardes(client, db)
        db.nos[nos[0]]["retido_em"] = AGORA_BANCO_API - timedelta(hours=6)
        r = _reter(client, nos[0], False)
    assert r.status_code == 200
    assert db.nos[nos[0]]["retido_em"] is None
    assert "credito_teto" not in r.json()


def test_segurar_o_INICIO_com_corrida_aberta_diz_o_que_o_botao_NAO_faz(
        client, auth_operador):
    """Decisão 45 (a regra dita ANTES) + Decisão 74 (sem `#N` na interface).

    Segurar o Início é o gesto mais mal-entendido da tela: parece "parar a
    malha" e não para — ele segura a PARTIDA. Sem a frase, o operador segura o
    Início às 3h achando que travou o ciclo em voo, e o ciclo continua."""
    db = FakeDb(pipelines=_pipes(), com_082=True)
    with _patch_db(db), _patch_agora():
        _monta_malha(client, "M1", ["RAIZ_A"])
        inicio = _cria_no(client, "M1", "inicio")
        db.abrir_corrida("M1", odate=ODATE_API, membros=["RAIZ_A"])
        r = _reter(client, inicio, True)
    aviso = r.json()["aviso"]
    assert "próxima corrida não parte" in aviso
    assert "SEGUE" in aviso
    assert "#" not in aviso, "numero de corrida nao aparece na interface (D74)"


def test_sem_corrida_aberta_segurar_o_inicio_nao_inventa_aviso(
        client, auth_operador):
    """Aditivo é aditivo: sem ciclo em voo a resposta é a de antes da fase,
    byte a byte."""
    db = FakeDb(pipelines=_pipes(), com_082=True)
    with _patch_db(db), _patch_agora():
        _monta_malha(client, "M1", ["RAIZ_A"])
        inicio = _cria_no(client, "M1", "inicio")
        r = _reter(client, inicio, True)
    assert "aviso" not in r.json()


# ═══════════════════════════════════════════════════════════════════════════
# 3. O teto com nó segurado NÃO expira na porta, e o card não acusa atraso
# ═══════════════════════════════════════════════════════════════════════════

def test_com_no_segurado_a_porta_do_disparo_NAO_expira_a_corrida(
        client, auth_operador):
    """Decisão 29 × Decisão 30: a expiração preguiçosa é a ÚNICA que não passa
    pela guardiã, então sem esta guarda um Aguarde segurado às 22h faria o
    disparo das 01:00 expirar a corrida que o operador travou de propósito."""
    db = FakeDb(pipelines=_pipes(), com_082=True)
    with _patch_db(db), _patch_agora():
        nos = _malha_com_dois_aguardes(client, db)
        c = db.abrir_corrida("M1", odate=ODATE_API, teto_horas=1,
                             aberta_em=AGORA_BANCO_API - timedelta(hours=5),
                             membros=["RAIZ_A", "RAIZ_B"])
        db.nos[nos[0]]["retido_em"] = AGORA_BANCO_API - timedelta(hours=4)
        expirou = __import__("routers.malhas", fromlist=["x"])._expirar_na_porta(
            db.conectar().cursor(), c, "C123456")
    assert expirou is False
    assert c["fechada_em"] is None and c["status"] == "ABERTA"


def test_o_card_nao_pinta_ATRASADA_enquanto_ha_no_segurado(
        client, auth_operador):
    """O teto vencido com hold é um teto que NÃO CORREU. Pintar âmbar aqui
    mandaria o operador investigar um atraso que ele próprio criou — e o
    treinaria a ignorar o âmbar no dia em que ele for real."""
    db = FakeDbCard(pipelines=_pipes(), com_082=True)
    with _patch_db(db), _patch_agora():
        nos = _malha_com_dois_aguardes(client, db)
        db.abrir_corrida("M1", odate=ODATE_API, teto_horas=1,
                         aberta_em=AGORA_BANCO_API - timedelta(hours=5),
                         membros=["RAIZ_A", "RAIZ_B"])
        sem_hold = _corrida_do_card(client)
        db.nos[nos[0]]["retido_em"] = AGORA_BANCO_API - timedelta(hours=4)
        db.nos[nos[0]]["retido_por"] = "C123456"
        com_hold = _corrida_do_card(client)
    assert sem_hold["teto_vencido"] is True
    assert sem_hold["saude"] == "ATRASADA"
    assert com_hold["teto_vencido"] is False
    assert com_hold["saude"] != "ATRASADA"
    # E a tela sabe DIZER por que os relógios pararam — um cadeado mudo seria
    # a mesma família de mentira que a barra que recua sem explicação.
    assert com_hold["retido_nos"] == 1
    assert com_hold["retido_por"] == "C123456"
    assert com_hold["retido_desde"] is not None


def _corrida_do_card(client, malha="M1"):
    resp = client.get("/malhas").json()
    return next(m for m in resp["malhas"] if m["malha_name"] == malha)["corrida"]


def test_a_barra_de_limite_so_existe_quando_a_MALHA_configurou_o_teto(
        client, auth_operador):
    """Decisão 61 — o teto é ANTI-TRAVAMENTO, não SLA. O default global de 24h
    vale para toda malha; desenhar uma barra em 80% às 20h numa malha que
    sempre fecha em 3h faria escalar por nada. Quem configurou na malha
    configurou porque quer ver."""
    db = FakeDbCard(pipelines=_pipes(), com_082=True)
    with _patch_db(db), _patch_agora():
        _monta_malha(client, "M1", ["RAIZ_A"])
        db.abrir_corrida("M1", odate=ODATE_API, teto_horas=24, membros=["RAIZ_A"])
        global_ = _corrida_do_card(client)
        db.malhas[db._malha_key("M1")]["teto_horas"] = 6
        proprio = _corrida_do_card(client)
    assert global_["teto_configurado"] is False and global_["teto_horas"] is None
    assert proprio["teto_configurado"] is True and proprio["teto_horas"] == 6
    # O denominador da barra vem do BANCO (aberta_em → teto_em) e já traz o
    # crédito de hold dentro, porque é `teto_em` que se move.
    assert proprio["teto_total_min"] == 24 * 60


def test_patch_grava_o_teto_da_malha_e_recusa_valor_fora_do_dominio(
        client, auth_operador, app):
    """`teto_horas = 0` faria a corrida nascer com `teto_em = aberta_em` — isto
    é, EXPIRADA no ato de abrir. A API recusa com o MESMO domínio do módulo da
    corrida; divergir faria a borda recusar o que o motor deixa passar."""
    from deps import PERM_EDITAR
    app.dependency_overrides[get_current_user] = lambda: {
        "matricula": "DEV1", "perfil": "desenvolvedor",
        "permissoes": [PERM_EDITAR, "tela_malha"]}
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db), _patch_agora():
        _monta_malha(client, "M1", ["RAIZ_A"])
        ok = client.patch("/malhas/M1", json={"teto_horas": 48})
        lido = client.get("/malhas/M1").json()
        zero = client.patch("/malhas/M1", json={"teto_horas": 0})
        nulo = client.patch("/malhas/M1", json={"teto_horas": None})
    assert ok.status_code == 200 and ok.json()["teto_horas"] == 48
    assert lido["teto_horas"] == 48
    assert zero.status_code == 422
    assert nulo.status_code == 200 and nulo.json()["teto_horas"] is None


# ═══════════════════════════════════════════════════════════════════════════
# 4. MALHA_ATRASADA (vivo) × MALHA_EXPIRADA (sem vivo) — na guardiã
# ═══════════════════════════════════════════════════════════════════════════

def _fechou(monkeypatch):
    """Captura `(desfecho, motivo)` de cada `fechar_corrida`."""
    fechadas: list = []
    monkeypatch.setattr(
        GUARDIA.mc, "fechar_corrida",
        lambda conn, cid, desfecho, quem, motivo=None:
            fechadas.append((cid, desfecho, motivo)) or True)
    return fechadas


def _eventos(monkeypatch):
    gravados: list = []
    monkeypatch.setattr(
        GUARDIA.dep, "gravar_evento",
        lambda conn, p, d, t, det, **kw: gravados.append((p, t, det)) or True)
    return gravados


def test_teto_vencido_com_8_membros_EXECUTANDO_alarma_e_NAO_fecha(monkeypatch):
    """⚠️ O ACEITE MAIS IMPORTANTE DA FASE.

    Fechamento mensal com 26h de carga legítima e teto padrão de 24h é o caso
    real. Fechar aqui liberaria o disparo por cima de 8 pipelines `EXECUTANDO`,
    e as linhas que terminassem depois carregariam id de corrida FECHADA —
    mentira estável que nenhum refresh corrige.

    A corrida continua ABERTA, o evento sai UMA vez, e o disparo segue
    bloqueado (o bloqueio É a corrida aberta)."""
    vivos = [f"CARGA_{i}" for i in range(8)]
    c = _corrida_dict(teto_em=AGORA_BANCO - timedelta(hours=2))
    _mundo(monkeypatch)
    _corrida(monkeypatch,
             corridas_abertas=lambda conn: [c],
             estado=lambda conn, cc, dispensa_sem_linha=None: _estado(
                 vivos=vivos, linhas=8, membros=8),
             relogios=lambda conn, cc, car, qui: {"teto_vencido": True,
                                                  "partida_vencida": True,
                                                  "quiescente": True})
    fechadas = _fechou(monkeypatch)
    eventos = _eventos(monkeypatch)
    GUARDIA.ciclo()
    GUARDIA.ciclo()           # 200 ciclos por dia: o card sai UMA vez
    assert fechadas == [], "o teto matou trabalho vivo"
    atrasos = [e for e in eventos if e[1] == "MALHA_ATRASADA"]
    assert len(atrasos) == 1
    assert "8 pipeline(s) ainda em execucao" in atrasos[0][2]
    assert "disparo segue bloqueado" in atrasos[0][2]
    assert not [e for e in eventos if e[1] == "MALHA_EXPIRADA"]


def test_teto_vencido_SEM_ninguem_vivo_expira_e_nao_emite_concluida(monkeypatch):
    """A outra metade: sem vivo, o teto é a rede que impede a corrida órfã de
    congelar a malha para sempre. E `MALHA_CONCLUIDA` **não sai** — teste de
    AUSÊNCIA (Decisão 24)."""
    c = _corrida_dict(teto_em=AGORA_BANCO - timedelta(hours=2))
    _mundo(monkeypatch)
    _corrida(monkeypatch,
             corridas_abertas=lambda conn: [c],
             estado=lambda conn, cc, dispensa_sem_linha=None: _estado(
                 ok=["RAIZ_A"], linhas=1, membros=1),
             relogios=lambda conn, cc, car, qui: {"teto_vencido": True,
                                                  "partida_vencida": True,
                                                  "quiescente": False})
    fechadas = _fechou(monkeypatch)
    eventos = _eventos(monkeypatch)
    GUARDIA.ciclo()
    assert [f[1] for f in fechadas] == ["EXPIRADA"]
    assert [e[1] for e in eventos] == ["MALHA_EXPIRADA"]
    assert not [e for e in eventos if e[1] == "MALHA_CONCLUIDA"]


def test_com_no_segurado_o_teto_vencido_nao_alarma_nem_expira(monkeypatch):
    """Decisão 30 nas DUAS pontas do desfecho: o hold suspende o alarme e o
    fechamento. Alarmar seria acusar o operador do atraso que ele criou de
    propósito; expirar seria puni-lo por isso."""
    c = _corrida_dict(teto_em=AGORA_BANCO - timedelta(hours=2))
    _mundo(monkeypatch)
    _corrida(monkeypatch,
             corridas_abertas=lambda conn: [c],
             ha_no_retido=lambda conn, m: True,
             estado=lambda conn, cc, dispensa_sem_linha=None: _estado(
                 vivos=["RAIZ_A"], linhas=1, membros=1),
             relogios=lambda conn, cc, car, qui: {"teto_vencido": True,
                                                  "partida_vencida": True,
                                                  "quiescente": True})
    fechadas = _fechou(monkeypatch)
    eventos = _eventos(monkeypatch)
    GUARDIA.ciclo()
    assert fechadas == []
    assert not [e for e in eventos if e[1] in ("MALHA_ATRASADA",
                                               "MALHA_EXPIRADA")]


# ═══════════════════════════════════════════════════════════════════════════
# 5. Decisão 31 (pendência 12) — `_fechar_dia_anterior`
# ═══════════════════════════════════════════════════════════════════════════

def _fechar_dia(monkeypatch, *, faltantes, corrida_da_linha=None,
                corrida_on=True):
    """Roda a responsabilidade 1 com UMA linha velha o bastante para fechar."""
    velha = _linha(criado_em=AGORA - timedelta(days=3))
    fechadas: list = []
    _mundo(monkeypatch,
           corridas_aguardando=lambda conn: [velha],
           predecessores_de=lambda conn, p: ["PIPE_A"],
           liberado=lambda conn, p, d, corrida=None: (False, faltantes),
           resumo_predecessores=lambda conn, p, d: {"PIPE_A": ["FALHA"]},
           fechar_nao_liberou=lambda conn, p, d, r, m:
               fechadas.append((p, m)) or True)
    _corrida(monkeypatch,
             corrida_ativa=lambda conn: corrida_on,
             corrida_aberta_da_linha=lambda conn, p, d: corrida_da_linha)
    eventos = _eventos(monkeypatch)
    GUARDIA.ciclo()
    return fechadas, eventos


def test_linha_de_corrida_ABERTA_nao_e_fechada_como_NAO_LIBEROU(monkeypatch):
    """Decisão 31 / pendência 12 da §18 — o defeito em que a guardiã levava a
    PRÓPRIA corrida a FALHA.

    O corte desta função é derivado da VIRADA (`criado_em < virada anterior`).
    Uma malha com teto de 48h, ou uma corrida que atravessa a virada seguinte
    (cadeia noturna longa + rerun), teria seus `AGUARDANDO_DEPENDENCIA`
    fechados **enquanto a corrida ainda é válida** — e esses membros virariam
    pendentes. A corrida passa a ser a autoridade sobre "este ciclo ainda não
    acabou"."""
    fechadas, _ = _fechar_dia(
        monkeypatch, faltantes=["PIPE_A"],
        corrida_da_linha={"id": 12, "malha_name": "M1",
                          "data_referencia": ODATE})
    assert fechadas == [], "a guardia fechou a linha da propria corrida aberta"


def test_sem_corrida_cobrindo_a_linha_o_fechamento_continua_acontecendo(
        monkeypatch):
    """A guarda nova não pode virar paralisia: sem corrida aberta, o
    `NAO_LIBEROU` de sempre continua sendo o D41 de quem não configurou
    deadline."""
    fechadas, eventos = _fechar_dia(monkeypatch, faltantes=["PIPE_A"])
    assert [f[0] for f in fechadas] == ["PIPE_C"]
    # `PREDECESSOR_FALHOU` vem junto porque o cenário tem um predecessor em
    # FALHA (responsabilidade 5, no mesmo ciclo) — o que se prova aqui é que o
    # NAO_LIBEROU continua saindo.
    assert "NAO_LIBEROU" in [e[1] for e in eventos]


def test_leitura_indisponivel_da_corrida_ADIA_o_fechamento(monkeypatch):
    """"Não consegui perguntar" nunca vira "pode fechar NAO_LIBEROU" — a mesma
    política do `ERRO_CONSULTA`, que esta função já aplica ao predicado."""
    fechadas, _ = _fechar_dia(
        monkeypatch, faltantes=["PIPE_A"],
        corrida_da_linha={"id": None, "malha_name": None,
                          "data_referencia": None})
    assert fechadas == []


def test_com_o_interruptor_em_zero_a_guarda_da_corrida_nao_e_perguntada(
        monkeypatch):
    """Byte a byte como antes da fase: com `malha_corrida_ativa = 0` a pergunta
    da Decisão 31 nem chega ao banco."""
    def _proibido(conn, p, d):
        raise AssertionError("interruptor em 0 — a corrida nao pode ser "
                             "perguntada nesta funcao")

    fechadas, _ = _fechar_dia(monkeypatch, faltantes=["PIPE_A"],
                              corrida_on=False)
    assert [f[0] for f in fechadas] == ["PIPE_C"]


def test_aguarde_SEGURADO_nao_vira_NAO_LIBEROU_depois_de_24h(monkeypatch):
    """Decisão 30 — **é a correção de um defeito que existe HOJE**.

    Com um Aguarde retido, `liberado()` devolve False por construção: é a trava
    que o operador pôs, não um predecessor que faltou. Fechar aqui é a guardiã
    desfazendo o gesto dele depois de 24h, sem que ninguém tenha soltado nada.
    O faltante já DIZ que é retenção; o que faltava era alguém escutar."""
    from utils import dependencias as dep_real
    fechadas, eventos = _fechar_dia(
        monkeypatch, faltantes=[dep_real.MSG_AGUARDE_RETIDO.format(7)])
    assert fechadas == []
    assert not [e for e in eventos if e[1] == "NAO_LIBEROU"]


def test_a_marca_da_retencao_sai_da_propria_mensagem_nas_duas_arvores():
    """`MARCA_RETIDO` é DERIVADA de `MSG_AGUARDE_RETIDO` (e não escrita à mão)
    nas duas árvores: mudar a frase sem mudar a marca faria a guardiã voltar a
    fechar como NAO_LIBEROU em silêncio, porque o `startswith` continuaria
    compilando."""
    from services import dependencias as dep_api
    from utils import dependencias as dep_dags
    assert dep_dags.MARCA_RETIDO == dep_api.MARCA_RETIDO == "Aguarde "
    for mod in (dep_dags, dep_api):
        assert mod.eh_retencao(mod.MSG_AGUARDE_RETIDO.format(3)) is True
        assert mod.eh_retencao("PIPE_A") is False
        assert mod.eh_retencao(mod.ERRO_CONSULTA + " timeout") is False


# ═══════════════════════════════════════════════════════════════════════════
# 6. Pendência 14 — a QUARTA porta leva a corrida (e recusa por ambiguidade)
# ═══════════════════════════════════════════════════════════════════════════

def _rede(monkeypatch, odate_resposta, **kw):
    """Roda a rede de segurança com UMA linha liberada, capturando o conf."""
    disparos: list = []
    _mundo(monkeypatch,
           corridas_aguardando=lambda conn: [_linha()],
           liberado=lambda conn, p, d, corrida=None: (True, []),
           config_dependente=lambda conn, p: _cfg(),
           **kw)
    _corrida(monkeypatch, odate=odate_resposta)
    monkeypatch.setattr(GUARDIA, "_trigger",
                        lambda dag_id, run_id, conf:
                            disparos.append((dag_id, run_id, conf)))
    eventos = _eventos(monkeypatch)
    GUARDIA.ciclo()
    return disparos, eventos


def test_a_guardia_propaga_a_corrida_da_LINHA_no_conf(monkeypatch):
    """Pendência 14 da §18 — a QUARTA porta de disparo.

    A DATA nunca sofreu (o degrau 0 lê a linha que o claim acabou de carimbar),
    mas a PROVENIÊNCIA se perdia exatamente quando o pipeline é membro de duas
    corridas do MESMO ODATE — o caso que a F5 existe para tratar. O `run_id`
    entra na pergunta porque é ele que identifica a LINHA: sem ele a resposta
    seria "uma corrida provável da malha", que é justamente a escolha que a
    Decisão 34 proíbe."""
    perguntas: list = []

    def _odate(conn, p, run_id=None, conf_id=None, herdada=None):
        perguntas.append((p, run_id, herdada))
        return {"data": HOJE, "corrida_id": 77, "ambiguo": False,
                "degrau": "carimbo", "detalhe": None}

    disparos, _ = _rede(monkeypatch, _odate)
    assert len(disparos) == 1
    assert disparos[0][2]["malha_execucao_id"] == 77
    # a 1ª pergunta é a da AMBIGUIDADE (sem run_id, antes do claim); a 2ª é a
    # da proveniência, com o run_id que o claim carimbou.
    assert perguntas[0][1] is None
    assert perguntas[1][1] == disparos[0][1]
    assert perguntas[1][2] == HOJE


def test_sem_corrida_o_conf_sai_byte_a_byte_como_antes(monkeypatch):
    """A chave é ADITIVA: push fora de malha (a maioria) não muda de forma, e
    nenhum consumidor de conf precisa aprender chave nova."""
    disparos, _ = _rede(
        monkeypatch,
        lambda conn, p, run_id=None, conf_id=None, herdada=None: {
            "data": None, "corrida_id": None, "ambiguo": False,
            "degrau": None, "detalhe": None})
    assert set(disparos[0][2]) == {"data_referencia", "dia_operacional",
                                   "disparado_por"}


def test_ODATE_ambiguo_RECUSA_o_disparo_nesta_porta_tambem(monkeypatch):
    """Decisão 34 — duas corridas abertas com ODATEs diferentes para o mesmo
    pipeline é RECUSA, nunca escolha. A recusa já valia nas outras três portas;
    aqui ela não valia, e escolher uma seria reintroduzir a doença com rótulo
    novo.

    A recusa vem ANTES do claim: reservar e não disparar deixaria a linha com
    `execution_id` de um run que nunca existiu."""
    reservas: list = []
    disparos, eventos = _rede(
        monkeypatch,
        lambda conn, p, run_id=None, conf_id=None, herdada=None: {
            "data": None, "corrida_id": None, "ambiguo": True,
            "degrau": "corrida",
            "detalhe": "MALHA_ODATE_AMBIGUO: PIPE_C e membro de corridas "
                       "abertas com ODATEs diferentes"},
        reservar_corrida=lambda conn, p, d, rid, o:
            reservas.append(rid) or rid)
    assert disparos == []
    assert reservas == [], "reservou antes de recusar"
    assert [e[1] for e in eventos] == ["DATA_DIVERGENTE"]
    assert "MALHA_ODATE_AMBIGUO" in eventos[0][2]


def test_a_falha_ao_resolver_a_corrida_NAO_impede_o_disparo(monkeypatch):
    """A guardiã NUNCA pode cair — ela faz o push de dependências de toda a
    casa. Disparar sem proveniência é infinitamente melhor que não disparar."""
    estado = {"n": 0}

    def _odate(conn, p, run_id=None, conf_id=None, herdada=None):
        estado["n"] += 1
        if estado["n"] == 1:             # a pergunta da ambiguidade responde
            return {"data": None, "corrida_id": None, "ambiguo": False,
                    "degrau": None, "detalhe": None}
        raise RuntimeError("lock timeout em etl_malha_execucao")

    disparos, _ = _rede(monkeypatch, _odate)
    assert len(disparos) == 1
    assert "malha_execucao_id" not in disparos[0][2]


# ═══════════════════════════════════════════════════════════════════════════
# 7. A invariante sintática: nenhuma conta de tempo em Python
# ═══════════════════════════════════════════════════════════════════════════

_FUNCOES_DE_RELOGIO = ("hold_da_malha", "creditar_hold",
                       "corrida_aberta_da_linha")


@pytest.mark.parametrize("nome", _FUNCOES_DE_RELOGIO)
def test_nenhuma_funcao_de_relogio_faz_conta_de_tempo_em_python(nome):
    """Decisão 10, e nesta fase ela é o ASSUNTO: hold, teto e atraso são todos
    relógio. O SQL Server do dev está ~3h à frente do worker (medido) — uma
    subtração em Python daria "segurado há -3h", e o crédito do teto sairia com
    três horas a mais ou a menos conforme o lado da conta.

    O teste é SINTÁTICO porque o defeito é sintático: qualquer `datetime.now()`
    ou aritmética entre carimbos dentro destas funções é o defeito."""
    fonte = inspect.getsource(getattr(mc, nome))
    arvore = ast.parse(fonte.lstrip())
    for no in ast.walk(arvore):
        if isinstance(no, ast.Call):
            alvo = getattr(no.func, "attr", getattr(no.func, "id", ""))
            assert alvo not in ("now", "utcnow", "today"), (nome, alvo)
        if isinstance(no, ast.BinOp) and isinstance(no.op, (ast.Sub, ast.Add)):
            # `+`/`-` entre nomes é o cheiro; o único aritmético legítimo aqui
            # é sobre INTEIROS vindos do banco (o `or 0` das colunas).
            assert not any(isinstance(x, ast.Attribute) for x in
                           (no.left, no.right)), nome


def test_o_SQL_do_credito_mede_o_hold_no_BANCO_e_so_com_o_ultimo_no():
    """As três cláusulas que fazem o crédito ser verdade, lidas no texto — é o
    contrato que a paridade compara entre as árvores."""
    sql = " ".join(mc.SQL_CREDITAR_HOLD.split())
    assert "DATEDIFF(MINUTE, MIN(n.retido_em), SYSDATETIME())" in sql
    assert "DATEADD(MINUTE, h.cred, me.teto_em)" in sql
    assert "h.cred > 0" in sql
    assert "n2.id <> ?" in sql
    assert "me.fechada_em IS NULL" in sql
    # O alarme de atraso já emitido falava de um teto que acabou de mudar de
    # lugar: sem zerar a memória, um atraso NOVO ficaria mudo para sempre.
    assert "atraso_visto_em = NULL" in sql


def test_o_hold_sai_do_MIN_e_nao_de_uma_coluna_da_corrida():
    """A prova de que o hold não é materializado: não existe coluna de hold no
    `_COLS` da corrida, e o SQL do hold lê `etl_malha_no`."""
    assert "retido" not in mc._COLS
    assert "MIN(n.retido_em)" in mc.SQL_HOLD_DA_MALHA
    assert "etl_malha_no" in mc.SQL_HOLD_DA_MALHA
