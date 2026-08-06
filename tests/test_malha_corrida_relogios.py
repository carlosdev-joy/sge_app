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
     frente do worker: qualquer subtração em Python apareceria como erro de 3h;
  7. **o `WHERE` da Decisão 31 exercitado, e não só stubado** — os cenários da
     guardiã trocam `corrida_aberta_da_linha` inteira por um dublê (eles provam
     o que a guardiã FAZ com a resposta); quem responde tem bloco próprio, com
     um cursor que aplica só as cláusulas presentes no statement emitido. Sem
     ele, apagar `fechada_em IS NULL` — a corrida encerrada de anteontem
     protegendo as linhas dela para sempre — passaria verde;
  8. **o teto vencido com trabalho vivo nas TRÊS superfícies** — a guardiã não
     fecha e alarma uma vez; o card fica `ABERTA` com saúde `ATRASADA`; e a
     porta do disparo RECUSA. As três precisam concordar: bastava uma delas
     expirar para o disparo partir por cima de oito pipelines `EXECUTANDO`.

⚠️ **REGRA DE HONESTIDADE DO DUBLÊ**, e nesta fase ela tem um terceiro modo de
falso verde: *dublê que faz conta de tempo em Python esconde exatamente o
defeito que a fase caça*. Toda comparação de tempo aqui sai do relógio do
BANCO (`AGORA_BANCO`, 3h à frente do processo, como no dev), e toda guarda que
mora no `WHERE` só é aplicada pelo dublê se o SQL emitido a contiver
(`_guarda`, em `test_malha_corrida_porta`).

E onde "não aconteceu nada" é o aceite, o teste carrega o próprio CONTROLE: o
mesmo cenário SEM o hold tem de fechar como `FALHA` (ou fechar como
`NAO_LIBEROU`, conforme o bloco). Sem o controle, "não fechou" pode estar vindo
do cenário — e a guarda pode simplesmente não existir mais.

⚠️ **O alcance do `_guarda` é a DELEÇÃO, não a semântica** (medido por mutação
nesta fase): ele lê o TEXTO do statement, então apagar `AND n2.id <> ?` muda o
que o dublê faz e vira teste vermelho — mas *neutralizar* a mesma cláusula
(`... AND n2.id <> ? AND 1=0`) mantém o texto, e nem o dublê nem os pins de
texto a enxergam. Quem responde por isso é o banco de verdade: é uma das razões
de o smoke do §15 existir, e de ele ter de rodar antes de o interruptor ir a 1.
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
    AGORA_API, AGORA_BANCO as AGORA_BANCO_API, FakeDb, _dags_novo, _disparar,
    _malha_com_inicio, _patch_agora, _pipes, ODATE as ODATE_API)
from tests.test_malhas_f4_card import (  # noqa: E402
    FakeDb as FakeDbCard, _pipes as _pipes_card)
from tests.test_malhas_f10 import _cria_no, _monta_malha  # noqa: E402
from tests.test_malhas_f15 import FakeAirflowClient  # noqa: E402


@pytest.fixture(autouse=True)
def _sem_cache_do_interruptor():
    """O interruptor tem cache com TTL no processo da API. Sem zerá-lo entre
    os cenários, um teste herdaria a resposta do anterior — e provaria o cache,
    não a regra (o mesmo cuidado das suítes da F3 e da F4)."""
    mc.limpar_cache()
    yield
    mc.limpar_cache()


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


def test_no_segurado_ONTEM_credita_o_hold_INTEIRO_a_corrida_que_nasceu_hoje(
        client, auth_operador):
    """Aceite da fase: *nó segurado ontem, corrida abre hoje → nasce com os
    relógios parados*, visto pelo lado do CRÉDITO.

    O hold não começa quando a corrida abre — ele já estava lá. Quem mede é
    `MIN(retido_em)`, e ele é de ONTEM: a corrida que viveu presa desde o
    primeiro minuto recebe de volta o hold inteiro, e o teto passa a valer a
    partir do momento em que a malha foi de fato liberada.

    ⚠️ E recebe **mais** do que viveu, de propósito e por construção: a janela
    do crédito é `[MIN(retido_em), agora]` (§6.7, literal), não
    `[max(aberta_em, MIN(retido_em)), agora]`. Aqui o hold tem 14h e a corrida
    tem 9h — creditam-se as 14h. É o único lugar em que o crédito erra para
    MAIS (o comentário do módulo declara segura a direção OPOSTA para holds
    encavalados), e o efeito é adiar por 5h o único mecanismo anti-travamento
    da malha. Está PINADO aqui: se algum dia o crédito for limitado a
    `aberta_em`, é este teste que muda, com decisão do dono junto."""
    db = FakeDb(pipelines=_pipes(), com_082=True)
    ontem = AGORA_BANCO_API - timedelta(hours=14)      # 20:00 do dia anterior
    with _patch_db(db), _patch_agora():
        nos = _malha_com_dois_aguardes(client, db)
        c = db.abrir_corrida("M1", odate=ODATE_API, teto_horas=4,
                             aberta_em=AGORA_BANCO_API - timedelta(hours=9),
                             membros=["RAIZ_A", "RAIZ_B"])
        # o teto ORIGINAL já venceu há 5h — e não expirou, porque não correu
        assert c["teto_em"] < AGORA_BANCO_API
        db.nos[nos[0]]["retido_em"] = ontem
        db.nos[nos[0]]["retido_por"] = "C123456"
        r = _reter(client, nos[0], False)
    assert r.status_code == 200, r.text
    assert c["fechada_em"] is None
    assert c["teto_creditado_min"] == 14 * 60
    assert c["teto_em"] == AGORA_BANCO_API + timedelta(hours=9)
    assert r.json()["credito_teto"]["minutos"] == 14 * 60


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


def test_o_credito_ZERA_a_memoria_do_alarme_de_atraso(client, auth_operador):
    """`atraso_visto_em = NULL` no mesmo `UPDATE` do crédito.

    A memória do alarme é por corrida — é ela que impede o mesmo
    `MALHA_ATRASADA` de sair 200 vezes num dia. Mas o alarme já emitido falava
    de um teto que ACABOU DE MUDAR DE LUGAR: sem zerar a memória, o atraso NOVO
    (o do teto novo, horas depois) ficaria mudo para sempre, e o ciclo que de
    fato estourasse o limite passaria despercebido."""
    db = FakeDb(pipelines=_pipes(), com_082=True)
    with _patch_db(db), _patch_agora():
        nos = _malha_com_dois_aguardes(client, db)
        c = db.abrir_corrida("M1", odate=ODATE_API, teto_horas=4,
                             aberta_em=AGORA_BANCO_API - timedelta(hours=7),
                             membros=["RAIZ_A", "RAIZ_B"])
        # a guardiã já tinha alarmado este ciclo, antes do hold
        c["atraso_visto_em"] = AGORA_BANCO_API - timedelta(hours=1)
        db.nos[nos[0]]["retido_em"] = AGORA_BANCO_API - timedelta(hours=6)
        r = _reter(client, nos[0], False)
    assert r.status_code == 200, r.text
    assert c["atraso_visto_em"] is None, \
        "o proximo MALHA_ATRASADA desta corrida nasceria mudo"


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


def test_o_INICIO_segurado_NAO_para_os_relogios_da_corrida_em_andamento(
        client, auth_operador):
    """§6.7, literal: *"Hold do Início não para corrida aberta — está certo:
    ele segura a PARTIDA"*. E é a mesma frase que a resposta do endpoint
    promete ao operador: *"a corrida em andamento SEGUE"*.

    ⚠️ O DEFEITO QUE ESTE TESTE MATA (medido no dev, com a 085 real): o hold da
    corrida era `MIN(retido_em)` sobre TODO `etl_malha_no`, e o Início é uma
    linha dessa tabela. Segurar o Início às 22h para a malha não partir de
    madrugada congelava o teto da corrida ABERTA — ela nunca fechava (nem por
    quiescência, nem por teto), o disparo ficava bloqueado enquanto o cadeado
    estivesse lá, e soltar dias depois creditava os mesmos dias ao teto. O
    toast dizia uma coisa e o motor fazia a oposta.

    ⚠️ O CONTROLE está no mesmo teste: o Aguarde segurado, no cenário
    IDÊNTICO, TEM de parar os relógios — senão "não parou" viria de a guarda
    não existir mais, e não do recorte."""
    def _cenario(tipo_do_no):
        db = FakeDb(pipelines=_pipes(), com_082=True)
        with _patch_db(db), _patch_agora():
            _monta_malha(client, "M1", ["RAIZ_A"])
            no = _cria_no(client, "M1", tipo_do_no)
            db.nos[no]["retido_em"] = AGORA_BANCO_API - timedelta(hours=6)
            db.nos[no]["retido_por"] = "C123456"
            hold = mc.hold_da_malha(db.conectar().cursor(), "M1")
        return hold

    assert _cenario("inicio")["retido"] is False, \
        "o Inicio segurado congelou o teto da corrida em andamento"
    controle = _cenario("aguarde")
    assert controle["retido"] is True and controle["nos"] == 1, \
        "o cenario de controle nao trava — o teste acima nao provava nada"


def test_soltar_o_INICIO_nao_credita_teto_e_nao_impede_o_credito_do_AGUARDE(
        client, auth_operador):
    """As DUAS pontas do `SQL_CREDITAR_HOLD`, e as duas pelo mesmo motivo.

      • soltar o Início não credita nada — ele nunca parou o ciclo, e creditar
        empurraria o único mecanismo anti-travamento da malha por um tempo em
        que ela estava andando;
      • um Início segurado não pode BARRAR o crédito do último Aguarde solto —
        senão o `NOT EXISTS` do "último nó" enxergaria um nó que não conta, e o
        operador que soltou a trava de verdade sairia sem o crédito dela."""
    db = FakeDb(pipelines=_pipes(), com_082=True)
    with _patch_db(db), _patch_agora():
        _monta_malha(client, "M1", ["RAIZ_A", "RAIZ_B"])
        inicio = _cria_no(client, "M1", "inicio")
        aguarde = _cria_no(client, "M1", "aguarde")
        c = db.abrir_corrida("M1", odate=ODATE_API, teto_horas=4,
                             aberta_em=AGORA_BANCO_API - timedelta(hours=7),
                             membros=["RAIZ_A", "RAIZ_B"])
        teto_antes = c["teto_em"]
        for no in (inicio, aguarde):
            db.nos[no]["retido_em"] = AGORA_BANCO_API - timedelta(hours=6)
            db.nos[no]["retido_por"] = "C123456"
        r_inicio = _reter(client, inicio, False)
        assert "credito_teto" not in r_inicio.json(), \
            "soltar o Inicio creditou tempo em que a corrida NAO estava parada"
        assert c["teto_em"] == teto_antes and c["teto_creditado_min"] == 0
        # e agora com o Início SEGURADO de novo: ele não pode barrar o crédito
        # do Aguarde, que é quem de fato travou o ciclo.
        db.nos[inicio]["retido_em"] = AGORA_BANCO_API - timedelta(hours=6)
        r_aguarde = _reter(client, aguarde, False)
    assert r_aguarde.json()["credito_teto"]["minutos"] == 360
    assert c["teto_em"] == teto_antes + timedelta(hours=6)


def test_o_card_nao_diz_relogios_parados_por_causa_do_INICIO(
        client, auth_operador):
    """A terceira superfície do mesmo recorte: o `teto_vencido` do card e o
    contador de nós segurados saem do MESMO `tipo <> 'inicio'` do motor.

    Divergir aqui é o card pintando "os relógios estão parados" numa corrida
    que a guardiã está fechando neste exato ciclo — a família de mentira que
    esta spec inteira existe para matar.

    ⚠️ O CONTROLE (o Aguarde, no cenário idêntico) vem junto: sem ele,
    `retido_nos == 0` poderia estar vindo de o card ter parado de ler o hold."""
    def _cenario(tipo_do_no):
        db = FakeDbCard(pipelines=_pipes(), com_082=True)
        with _patch_db(db), _patch_agora():
            _monta_malha(client, "M1", ["RAIZ_A", "RAIZ_B"])
            no = _cria_no(client, "M1", tipo_do_no)
            db.abrir_corrida("M1", odate=ODATE_API, teto_horas=1,
                             aberta_em=AGORA_BANCO_API - timedelta(hours=5),
                             membros=["RAIZ_A", "RAIZ_B"])
            db.nos[no]["retido_em"] = AGORA_BANCO_API - timedelta(hours=4)
            db.nos[no]["retido_por"] = "C123456"
            return _corrida_do_card(client)

    com_inicio = _cenario("inicio")
    assert com_inicio["retido_nos"] == 0, \
        "o card contou o Inicio como no que trava a corrida"
    assert com_inicio["teto_vencido"] is True, \
        "o Inicio segurado escondeu do card o limite JA vencido"
    com_aguarde = _cenario("aguarde")
    assert com_aguarde["retido_nos"] == 1 and \
        com_aguarde["teto_vencido"] is False, \
        "o cenario de controle nao para o card — o teste acima nao provava nada"


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


def test_no_segurado_ONTEM_faz_a_corrida_de_hoje_NASCER_com_o_teto_parado(
        client, auth_operador):
    """Aceite da fase: *nó segurado ontem, corrida abre hoje → nasce com os
    relógios parados*, visto pelo lado da TELA.

    A diferença para o teste do hold posto DURANTE o ciclo é a que importa no
    plantão: aqui a retenção é anterior ao nascimento da corrida, e mesmo assim
    o teto dela nunca correu. Sem isto, a corrida da madrugada abriria com o
    limite queimando por cima de uma malha travada às 20h do dia anterior e
    estaria vermelha antes de alguém acordar — punida pelo tempo em que estava,
    por decisão humana, proibida de andar.

    O cenário é montado com o teto ORIGINAL já vencido pelo relógio do banco
    (aberta 01:00, teto de 4h, agora 10:00): o que segura o card não é o
    relógio, é a retenção."""
    db = FakeDbCard(pipelines=_pipes_card(), com_082=True)
    ontem = AGORA_BANCO_API - timedelta(hours=14)
    with _patch_db(db), _patch_agora():
        _monta_malha(client, "M1", ["P0", "P1"])
        no = _cria_no(client, "M1", "aguarde")
        db.nos[no]["retido_em"] = ontem
        db.nos[no]["retido_por"] = "C123456"
        c = db.abrir_corrida("M1", odate=ODATE_API, teto_horas=4,
                             aberta_em=AGORA_BANCO_API - timedelta(hours=9),
                             membros=["P0", "P1"])
        db.execucao("P0", "SUCESSO", inicio=AGORA_BANCO_API - timedelta(hours=8),
                    fim=AGORA_BANCO_API - timedelta(hours=7), corrida=c["id"])
        db.execucao("P1", "SUCESSO", inicio=AGORA_BANCO_API - timedelta(hours=8),
                    fim=AGORA_BANCO_API - timedelta(hours=7), corrida=c["id"])
        card = _corrida_do_card(client)
    assert card["status"] == "ABERTA"
    assert card["teto_vencido"] is False, "o teto correu com a malha travada"
    assert card["saude"] != "ATRASADA"
    # e a tela sabe DESDE QUANDO: o instante é de ontem e vem do banco
    assert card["retido_nos"] == 1
    assert card["retido_desde"].startswith(ontem.strftime("%Y-%m-%d"))
    assert card["retido_por"] == "C123456"


def test_teto_vencido_com_8_membros_EXECUTANDO_fica_ABERTA_e_pinta_ATRASADA(
        client, auth_operador):
    """O aceite mais importante da fase, visto pela TELA: o teto vencido com
    trabalho vivo é ALARME, e alarme tem cor — não desfecho.

    Fechamento mensal com 26h de carga legítima e teto padrão de 24h é o caso
    real. O ciclo continua `ABERTA` (ninguém foi encerrado), a SAÚDE vira
    `ATRASADA` (o eixo do prazo, §6.1) e os oito continuam contados como vivos:
    é a diferença entre "está demorando" e "acabou mal", que o card precisa
    saber dizer sem inventar um desfecho."""
    db = FakeDbCard(pipelines=_pipes_card(), com_082=True)
    vivos = [f"P{i}" for i in range(8)]
    with _patch_db(db), _patch_agora():
        _monta_malha(client, "M1", vivos)
        c = db.abrir_corrida("M1", odate=ODATE_API, teto_horas=24,
                             aberta_em=AGORA_BANCO_API - timedelta(hours=26),
                             membros=vivos)
        for p in vivos:
            db.execucao(p, "EXECUTANDO",
                        inicio=AGORA_BANCO_API - timedelta(hours=20),
                        corrida=c["id"])
        card = _corrida_do_card(client)
    assert card["status"] == "ABERTA"
    assert card["teto_vencido"] is True
    assert card["saude"] == "ATRASADA"
    assert card["membros_vivos"] == 8
    assert c["fechada_em"] is None, "a leitura do card fechou a corrida"


def test_teto_vencido_com_8_membros_EXECUTANDO_NAO_libera_o_disparo(
        client, auth_operador):
    """A outra metade do mesmo aceite: *o disparo segue bloqueado*.

    A expiração preguiçosa da porta (Decisão 29) é a única que não passa pela
    guardiã — e é justamente por isso que ela tem de conferir a Decisão 25. Se
    o teto vencido bastasse, o disparo das 08:00 expiraria a corrida e partiria
    por cima de OITO pipelines `EXECUTANDO`; as linhas que terminassem depois
    carregariam id de corrida FECHADA, que é a mentira estável que nenhum
    refresh corrige.

    A F3 já provou a trava com UM membro removido do desenho; o que se
    acrescenta aqui é o número do aceite e o fato de que nenhum dos oito é
    tocado — nem por um trigger, nem por um evento de encerramento."""
    db = FakeDb(pipelines=_pipes(), com_082=True)
    fake = FakeAirflowClient()
    vivos = [f"CARGA_{i}" for i in range(8)]
    with _patch_db(db), patch("routers.malhas.get_airflow_client",
                              return_value=fake), _dags_novo(), _patch_agora():
        _malha_com_inicio(client)
        presa = db.abrir_corrida(
            "M1", odate=ODATE_API, teto_horas=24,
            aberta_em=AGORA_BANCO_API - timedelta(hours=26), membros=vivos)
        for i, p in enumerate(vivos):
            # membros do SNAPSHOT que já não estão no desenho de hoje: o
            # bloqueio do ciclo não os enxerga, e quem tem de recusar é o
            # portão da corrida.
            db.execucoes.append({"pipeline": p, "data_referencia": ODATE_API,
                                 "execution_id": f"run_vivo_{i}",
                                 "status": "EXECUTANDO",
                                 "inicio": AGORA_BANCO_API - timedelta(hours=20),
                                 "malha_execucao_id": presa["id"],
                                 "substituida_em": None})
        r = _disparar(client)
    assert r.status_code == 422, r.text
    assert db.por_id(presa["id"])["status"] == "ABERTA"
    assert "MALHA_EXPIRADA" not in db.tipos_de_evento()
    assert fake.chamadas == [], "disparou por cima de trabalho vivo"


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


def test_estado_ILEGIVEL_nao_fecha_a_corrida_como_ABORTADA(monkeypatch):
    """⚠️ O MESMO FURO DA F3, na única leitura que ainda não o tratava.

    `mc.estado()` degrada LARGA: lock timeout em `etl_pipeline_execucao` (a
    maior tabela do schema, e às 3h a mais disputada) faz a função logar e
    devolver os BALDES VAZIOS. Lido como fato, isso é `linhas == 0` — e
    `linhas == 0` com a carência de partida vencida fecha a corrida como
    `ABORTADA`, *"a corrida não chegou a começar"*, com card no Teams, por cima
    de oito pipelines `EXECUTANDO`. Depois disso o disparo parte, e as linhas
    que terminarem carregam id de corrida FECHADA.

    `_expirar_na_porta` já recusava por este exato motivo, com este exato
    discriminador (`membros == 0`): o snapshot nasce no MESMO commit da
    abertura, logo zero membros só acontece quando a leitura não respondeu.

    ⚠️ O CONTROLE está no mesmo teste: com o snapshot LIDO e realmente sem
    linha nenhuma, a `ABORTADA` continua saindo — a guarda não pode ter
    desligado o desfecho, só a leitura que não aconteceu."""
    def _cenario(membros_lidos: int):
        c = _corrida_dict()
        _mundo(monkeypatch)
        _corrida(monkeypatch,
                 corridas_abertas=lambda conn: [c],
                 ha_no_retido=lambda conn, m: False,
                 estado=lambda conn, cc, dispensa_sem_linha=None: _estado(
                     linhas=0, membros=membros_lidos),
                 relogios=lambda conn, cc, car, qui: {"teto_vencido": False,
                                                      "partida_vencida": True,
                                                      "quiescente": False})
        fechadas = _fechou(monkeypatch)
        eventos = _eventos(monkeypatch)
        GUARDIA.ciclo()
        return fechadas, eventos

    fechadas, eventos = _cenario(membros_lidos=0)      # a leitura FALHOU
    assert fechadas == [], \
        f"a guardia fechou a corrida com o estado ilegivel: {fechadas}"
    assert not [e for e in eventos if e[1] == "MALHA_ABORTADA"]

    fechadas, eventos = _cenario(membros_lidos=8)      # a leitura RESPONDEU
    assert [f[1] for f in fechadas] == ["ABORTADA"], \
        "o cenario de controle nao fecha — o teste acima nao provava nada"
    assert [e[1] for e in eventos] == ["MALHA_ABORTADA"]


def test_aguarde_segurado_por_30h_NAO_leva_a_corrida_a_FALHA_pela_quiescencia(
        monkeypatch):
    """A segunda metade do aceite das 30h, e o defeito é literal: com o Aguarde
    retido, `liberado()` devolve False para o dependente **por construção**.
    Isso é "nenhum vivo, nenhum liberado" — que é exatamente a forma de uma
    corrida quiescente com pendentes —, e sem a guarda a guardiã fecharia como
    `FALHA` por causa da trava que o próprio operador pôs.

    ⚠️ O CONTROLE está no mesmo teste de propósito: sem o hold, o cenário
    IDÊNTICO fecha como `FALHA`. Um teste que só afirmasse "não fechou" passaria
    verde num cenário que não fecharia de jeito nenhum — e é assim que uma
    guarda deixa de existir sem ninguém notar."""
    from utils import dependencias as dep_real
    retido = dep_real.MSG_AGUARDE_RETIDO.format(7)

    def _cenario(com_hold: bool):
        c = _corrida_dict()
        # `liberado()` é o REAL do ponto de vista da guardiã: o que o dublê
        # devolve é o que o predicado devolve com um Aguarde segurado.
        _mundo(monkeypatch,
               liberado=lambda conn, p, d, corrida=None: (False, [retido]))
        _corrida(monkeypatch,
                 corridas_abertas=lambda conn: [c],
                 ha_no_retido=lambda conn, m: com_hold,
                 hold_da_malha=lambda conn, m: {
                     "retido": com_hold, "nos": 1 if com_hold else 0,
                     "desde": AGORA_BANCO - timedelta(hours=30),
                     "minutos": 30 * 60, "por": "C123456"},
                 # a quiescência AVALIA de verdade: é `_quiescencia_liberada`
                 # (a função real) quem pergunta pelo dependente que espera.
                 aguardando_do_snapshot=lambda conn, cc: ["PIPE_DEP"],
                 estado=lambda conn, cc, dispensa_sem_linha=None: _estado(
                     ok=["RAIZ_A"],
                     pendentes=[{"pipeline": "PIPE_DEP",
                                 "classe": "aguardando"}],
                     linhas=2, membros=2),
                 relogios=lambda conn, cc, car, qui: {"teto_vencido": False,
                                                      "partida_vencida": True,
                                                      "quiescente": True})
        fechadas = _fechou(monkeypatch)
        eventos = _eventos(monkeypatch)
        GUARDIA.ciclo()
        return fechadas, eventos

    fechadas, eventos = _cenario(com_hold=True)
    assert fechadas == [], "a guardia fechou a corrida por causa do hold"
    assert not [e for e in eventos if e[1] == "MALHA_FALHOU"]

    fechadas, eventos = _cenario(com_hold=False)
    assert [f[1] for f in fechadas] == ["FALHA"], \
        "o cenario de controle nao fecha — o teste acima nao provava nada"
    assert [e[1] for e in eventos] == ["MALHA_FALHOU"]


# ═══════════════════════════════════════════════════════════════════════════
# 5. Decisão 31 (pendência 12) — `_fechar_dia_anterior`
# ═══════════════════════════════════════════════════════════════════════════

def _fechar_dia(monkeypatch, *, faltantes, corrida_da_linha=None,
                corrida_on=True, idade=timedelta(days=3)):
    """Roda a responsabilidade 1 com UMA linha velha o bastante para fechar.

    `corrida_da_linha` aceita um DICIONÁRIO (a resposta) ou um CALLABLE — e o
    callable existe para o cenário em que a pergunta não pode nem ser feita:
    stubar com um lambda que devolve `None` não distingue "perguntou e não há"
    de "não perguntou"."""
    velha = _linha(criado_em=AGORA - idade)
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
             corrida_aberta_da_linha=(
                 corrida_da_linha if callable(corrida_da_linha)
                 else (lambda conn, p, d: corrida_da_linha)))
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
    da Decisão 31 nem chega ao banco.

    ⚠️ O stub LEVANTA em vez de devolver `None`: "não perguntou" e "perguntou e
    não havia" produzem o mesmo fechamento, e só o primeiro é o contrato aqui.
    Com um lambda devolvendo `None`, este teste ficaria verde mesmo com o
    `if corrida_on` apagado do módulo — provaria o cenário, não a guarda."""
    def _proibido(conn, p, d):
        raise AssertionError("interruptor em 0 — a corrida nao pode ser "
                             "perguntada nesta funcao")

    fechadas, eventos = _fechar_dia(monkeypatch, faltantes=["PIPE_A"],
                                    corrida_on=False,
                                    corrida_da_linha=_proibido)
    assert [f[0] for f in fechadas] == ["PIPE_C"]
    assert "NAO_LIBEROU" in [e[1] for e in eventos]


def test_aguarde_segurado_por_30h_nao_vira_NAO_LIBEROU(monkeypatch):
    """Decisão 30 — **é a correção de um defeito que existe HOJE**, e é o
    aceite literal da fase (o Aguarde segurado há 30h).

    Com um Aguarde retido, `liberado()` devolve False por construção: é a trava
    que o operador pôs, não um predecessor que faltou. A linha atravessou o dia
    operacional inteiro (34h), então ela CHEGA ao fechamento — o que a salva é
    a leitura do faltante, não a idade. Fechar aqui é a guardiã desfazendo o
    gesto do operador depois de 24h, sem que ninguém tenha soltado nada."""
    from utils import dependencias as dep_real
    fechadas, eventos = _fechar_dia(
        monkeypatch, faltantes=[dep_real.MSG_AGUARDE_RETIDO.format(7)],
        idade=timedelta(hours=34))
    assert fechadas == []
    assert not [e for e in eventos if e[1] == "NAO_LIBEROU"]


def test_a_MESMA_linha_de_34h_fecha_quando_o_faltante_e_um_PREDECESSOR(
        monkeypatch):
    """O controle do teste acima, com a mesma idade: o que muda é só QUEM
    falta. Sem ele, "não fechou" poderia estar vindo do corte por idade — e a
    guarda da retenção podia não existir."""
    fechadas, eventos = _fechar_dia(monkeypatch, faltantes=["PIPE_A"],
                                    idade=timedelta(hours=34))
    assert [f[0] for f in fechadas] == ["PIPE_C"]
    assert "NAO_LIBEROU" in [e[1] for e in eventos]


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


# ── o WHERE da Decisão 31, exercitado (e não só stubado) ───────────────────
# Os testes acima trocam `corrida_aberta_da_linha` inteira por um dublê: eles
# provam o que a GUARDIÃ faz com a resposta. Quem responde é este bloco — e o
# cursor abaixo aplica SÓ as cláusulas que o statement emitido contiver, que é
# o único jeito de "apagar o `fechada_em IS NULL`" virar teste vermelho em vez
# de teste verde por conta própria.

class _CurCorridaDaLinha:
    """Cursor que interpreta `SQL_CORRIDA_ABERTA_DA_LINHA` sobre um mundo
    minúsculo: corridas, linhas de execução e o snapshot de membros.

    ⚠️ REGRA DE HONESTIDADE: `fechada_em IS NULL`, a porta do carimbo
    (`e.malha_execucao_id = me.id`), a porta do snapshot
    (`mm.malha_execucao_id = me.id`) e o recorte de ODATE da segunda porta são
    lidos do TEXTO. Aplicá-los por conta própria faria este dublê provar a si
    mesmo."""

    def __init__(self, corridas, linhas=(), membros=()):
        self.corridas = list(corridas)      # {id, malha_name, data_referencia,
        self.linhas = list(linhas)          #  fechada_em}
        self.membros = list(membros)        # (corrida_id, pipeline)
        self.sql = ""                       # (pipeline, data_ref, corrida_id)
        self._row = None

    def execute(self, sql, params=()):
        self.sql = " ".join(str(sql).split())
        pipeline, data_ref = params[0], params[1]
        so_abertas = "me.fechada_em IS NULL" in self.sql
        porta_carimbo = "e.malha_execucao_id = me.id" in self.sql
        porta_snapshot = "mm.malha_execucao_id = me.id" in self.sql
        odate_da_porta_2 = "me.data_referencia = " in self.sql
        achadas = []
        for c in sorted(self.corridas, key=lambda x: x["id"]):
            if so_abertas and c["fechada_em"] is not None:
                continue
            pelo_carimbo = porta_carimbo and any(
                l[0] == pipeline and l[1] == data_ref and l[2] == c["id"]
                for l in self.linhas)
            pelo_snapshot = porta_snapshot and any(
                m[0] == c["id"] and m[1] == pipeline for m in self.membros)
            if pelo_snapshot and odate_da_porta_2:
                pelo_snapshot = c["data_referencia"] == data_ref
            if pelo_carimbo or pelo_snapshot:
                achadas.append(c)
        self._row = ((achadas[0]["id"], achadas[0]["malha_name"],
                      achadas[0]["data_referencia"]) if achadas else None)

    def fetchone(self):
        return self._row


class _ConexaoDoCursor:
    """A divergência DELIBERADA entre as árvores: o canônico recebe `conn` (a
    task do Airflow abre a conexão e a fecha ao morrer), o port recebe `cur` (a
    API já carrega o cursor pela request inteira). O mesmo dublê serve aos
    dois — um dublê por árvore provaria a paridade entre dois dublês."""

    def __init__(self, cur):
        self._cur = cur

    def cursor(self):
        return self._cur


def _arvore(nome):
    """O módulo da corrida das DUAS árvores: `api/` (port, `?`) e `dags/`
    (canônico, `%s`). Quem CONSOME esta leitura é a guardiã, que roda no
    canônico — testar só o port deixaria de fora justamente o lado que fecha
    linha como NAO_LIBEROU."""
    return mc if nome == "api" else GUARDIA.mc


def _alvo(nome, cur):
    """O primeiro argumento na forma que cada árvore espera."""
    return cur if nome == "api" else _ConexaoDoCursor(cur)


_ABERTA_HOJE = {"id": 7, "malha_name": "M1", "data_referencia": ODATE,
                "fechada_em": None}


@pytest.mark.parametrize("arvore", ["api", "dags"])
def test_a_corrida_cobre_a_linha_PELO_CARIMBO_e_pela_PARTICIPACAO_no_snapshot(
        arvore):
    """As DUAS portas do `EXISTS`, e a segunda não é zelo: a linha do dependente
    NASCE no claim do pai, **sem** `malha_execucao_id` — só o registro do filho
    a carimba. Fechar por "não aponta para corrida nenhuma" mataria exatamente
    as linhas que ainda não partiram, que são as que a corrida está esperando."""
    mod = _arvore(arvore)
    # (a) a linha já carimbada
    cur = _CurCorridaDaLinha([_ABERTA_HOJE],
                             linhas=[("PIPE_C", ODATE, 7)])
    assert mod.corrida_aberta_da_linha(_alvo(arvore, cur), "PIPE_C",
                                       ODATE)["id"] == 7
    # (b) a linha AINDA sem carimbo, o pipeline no snapshot da corrida
    cur = _CurCorridaDaLinha([_ABERTA_HOJE],
                             linhas=[("PIPE_C", ODATE, None)],
                             membros=[(7, "PIPE_C")])
    achada = mod.corrida_aberta_da_linha(_alvo(arvore, cur), "PIPE_C", ODATE)
    assert achada["id"] == 7 and achada["malha_name"] == "M1"
    # (c) nem carimbo nem snapshot: não há corrida cobrindo esta linha
    cur = _CurCorridaDaLinha([_ABERTA_HOJE], linhas=[("PIPE_C", ODATE, None)])
    assert mod.corrida_aberta_da_linha(_alvo(arvore, cur), "PIPE_C",
                                       ODATE) is None


@pytest.mark.parametrize("arvore", ["api", "dags"])
def test_corrida_FECHADA_ou_de_OUTRO_ODATE_nao_cobre_a_linha(arvore):
    """As duas maneiras de a guarda virar paralisia permanente.

    Sem `fechada_em IS NULL`, a corrida encerrada de anteontem protegeria para
    sempre as linhas dela — e o `NAO_LIBEROU` (que é o D41 de quem não
    configurou deadline) nunca mais sairia. Sem o recorte de ODATE na porta do
    snapshot, a corrida de HOJE protegeria a linha de ONTEM do mesmo membro,
    que é o mesmo travamento com outra roupa."""
    mod = _arvore(arvore)
    ontem = ODATE - timedelta(days=1)
    fechada = {"id": 3, "malha_name": "M1", "data_referencia": ontem,
               "fechada_em": AGORA_BANCO}
    cur = _CurCorridaDaLinha([fechada], linhas=[("PIPE_C", ontem, 3)],
                             membros=[(3, "PIPE_C")])
    assert mod.corrida_aberta_da_linha(_alvo(arvore, cur), "PIPE_C",
                                       ontem) is None
    # a corrida ABERTA de hoje, com o mesmo membro no snapshot, não cobre a
    # linha de ontem
    cur = _CurCorridaDaLinha([_ABERTA_HOJE], membros=[(7, "PIPE_C")])
    assert mod.corrida_aberta_da_linha(_alvo(arvore, cur), "PIPE_C",
                                       ontem) is None


@pytest.mark.parametrize("arvore", ["api", "dags"])
def test_sem_a_085_a_leitura_e_None_e_o_erro_generico_ADIA_o_fechamento(arvore):
    """As duas degradações, que são OPOSTAS e as duas certas: sem a 085 o
    comportamento é o de antes desta spec, byte a byte (`None` = "não há
    corrida"); com a tabela lá e a consulta falhando, `{"id": None}` = "não
    consegui perguntar", e quem chama ADIA. Inverter a segunda é fechar linha
    como `NAO_LIBEROU` por causa de um lock timeout às 3h."""
    mod = _arvore(arvore)

    class _Sem085:
        def execute(self, *a, **k):
            raise Exception("[42S02] Invalid object name "
                            "'dbo.etl_malha_execucao'. (208)")

    class _Timeout:
        def execute(self, *a, **k):
            raise Exception("Lock request time out period exceeded.")

    assert mod.corrida_aberta_da_linha(_alvo(arvore, _Sem085()),
                                       "PIPE_C", ODATE) is None
    adiado = mod.corrida_aberta_da_linha(_alvo(arvore, _Timeout()),
                                         "PIPE_C", ODATE)
    assert adiado is not None and adiado["id"] is None


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
