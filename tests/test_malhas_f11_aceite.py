"""
F11 da spec `docs/spec-malha-execucao.md` (§9.8 e §10 "### F11") — a SUÍTE DE
ACEITE dos caminhos até a corrida, bullet a bullet.

A pergunta que a fase responde: **uma tela ótima que ninguém alcança às 3h vale
menos que uma tela boa com caminho até ela.** Antes dela era *impossível* saber
qual malha está rodando sem abrir uma a uma e trocar o modo.

Este arquivo cobre os caminhos que passam pela LISTA (o filtro por estado de
corrida, os contadores clicáveis, o orçamento de consultas) **e a chegada do
card do Teams na tela** — o único ponto em que as duas árvores se encontram, e
por isso o único lugar em que a prova de ponta a ponta pode existir. Os outros
dois caminhos têm suíte própria, porque são só de uma árvore:

  • o card do Teams — `tests/test_ds_teams.py` (o botão e a degradação por
    ausência) e `tests/test_dependencia_guardia_dag.py` (a config chegando ao
    card pelo ciclo da guardiã);
  • a resolução da malha no banco — `tests/test_malha_corrida_f11_vivo.py`.

Herda as duas escolhas metodológicas da suíte da F9, e pelos mesmos motivos:
o cenário é o **payload da API de verdade** (nunca um objeto escrito à mão), e
a prova é de **comportamento** — a régua do contador sai da árvore renderizada,
não de um `grep` no `.tsx`.

⚠️ **Nada toca o banco**: o servidor é dublê e o front roda no Node.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from datetime import date, datetime, timedelta
from urllib.parse import urlparse

import pytest

from deps import PERM_EDITAR, PERM_EXECUTAR, get_current_user
from services import malha_corrida as mc
from tests.test_malhas_f9_nao_abriu import FakeDb
from tests.test_malhas_f4_card import _patch
from tests.test_malhas_f10 import _monta_malha
from tests.test_malhas_f9_aceite import (
    AGORA_LOCAL_MS, HARNESS, RAIZ, SRC as SRC_UI, _MOTIVO_SALTO, _node,
)
from unittest.mock import patch

# ── O relógio do cenário, e ele É o aceite ──────────────────────────────────
# "às 08:00 de 04/08 o contador NÃO pode mostrar `0` por filtrar ODATE = hoje":
# as corridas da madrugada carimbam a referência 03/08 e fecham na madrugada do
# dia 04. Um contador que perguntasse "quantas concluíram HOJE" responderia
# zero — e um que somasse toda malha concluída, de qualquer referência,
# responderia um número que não bate com relatório nenhum por ODATE.
MANHA = datetime(2026, 8, 4, 8, 0)            # o relógio do processo da API
REFERENCIA = date(2026, 8, 3)                 # o ODATE da madrugada
ANTERIOR = date(2026, 8, 2)                   # a referência de quem ficou para trás
MADRUGADA = datetime(2026, 8, 4, 4, 10)       # `aberta_em` na régua do BANCO

# I..L existem para o cenário `abortada_e_horaria` — o dublê só aceita
# pipeline cadastrado, e a malha que ABORTOU precisa de membros próprios.
_NOMES = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L"]


def _pipes_noturnos():
    """Gatilho às 23:00 — DEPOIS do relógio do cenário.

    É o que mantém o cenário limpo: às 08:00 o horário de hoje ainda não
    venceu, então nenhuma malha ganha `corrida_esperada` e o que se conta é
    exatamente o que se quer contar. Com um gatilho já vencido, toda malha
    seria simultaneamente "concluída (ref. 03/08)" e "não abriu (04/08)" — as
    duas coisas verdadeiras ao mesmo tempo, e o teste mediria a soma."""
    base = {"active": 1, "criticidade": "Media", "depends_on": None,
            "scheduled_time": "23:00:00", "schedule_type": "daily",
            "schedule_hour": 23, "schedule_minute": 0, "schedule_dow": 1,
            "schedule_dom": 1, "horarios_especificos": None,
            "dias_semana": None, "dias_horarios_mes": None,
            "somente_dias_uteis": 0, "calendario_nome": None,
            "hora_virada": None, "agenda_no": None, "dag_criada": 1}
    return {nome: dict(base) for nome in _NOMES}


def _payload(client, monta, *, agora_api=MANHA, pipes=None, medir=None):
    """O payload de `GET /malhas` como o servidor de verdade o devolve.

    `medir` recebe o dublê do banco depois da resposta — é por onde o teste do
    orçamento lê os statements que o endpoint de fato gastou."""
    db = FakeDb(pipelines=pipes or _pipes_noturnos(), com_085=True,
                agora_banco=agora_api + timedelta(hours=3))
    mc.limpar_cache()
    try:
        with _patch(db), patch("routers.malhas._agora", return_value=agora_api):
            monta(db, client)
            db.sqls.clear()          # o custo do REFETCH, não o da montagem
            resp = client.get("/malhas")
            assert resp.status_code == 200, resp.text
            if medir is not None:
                medir(db)
            return resp.json()
    finally:
        mc.limpar_cache()


# ═══════════════════════ o cenário da manhã seguinte ═════════════════════════

CONCLUIDAS = 12


def _madrugada(db, client):
    """A manhã de 04/08: 12 malhas concluíram a corrida de referência 03/08,
    uma ficou presa em 02/08, uma ainda roda e uma falhou.

    Os números são os do aceite literal — `12 concluídas na madrugada
    (referência 03/08)` —, e a 13ª concluída existe para provar a outra metade
    da régua: ela **não** entra na conta, porque é de outra referência, e o
    número tem de bater exatamente com o relatório do ODATE declarado."""
    for i in range(CONCLUIDAS):
        nome = f"OK_{i:02d}"
        _monta_malha(client, nome, ["A", "B"])
        c = db.abrir_corrida(nome, odate=REFERENCIA, aberta_em=MADRUGADA,
                             membros=["A", "B"], status="CONCLUIDA")
        for p in ("A", "B"):
            db.execucao(p, "SUCESSO", odate=REFERENCIA,
                        inicio=MADRUGADA + timedelta(minutes=10),
                        fim=MADRUGADA + timedelta(minutes=40), corrida=c["id"])
    # A que ficou para trás: concluída, mas de uma referência ANTERIOR.
    _monta_malha(client, "ATRASADA_NA_REF", ["C", "D"])
    velha = db.abrir_corrida("ATRASADA_NA_REF", odate=ANTERIOR,
                             aberta_em=datetime(2026, 8, 3, 4, 10),
                             membros=["C", "D"], status="CONCLUIDA")
    for p in ("C", "D"):
        db.execucao(p, "SUCESSO", odate=ANTERIOR,
                    inicio=datetime(2026, 8, 3, 4, 20),
                    fim=datetime(2026, 8, 3, 4, 50), corrida=velha["id"])
    # A que ainda roda: 1 de 2 pronto.
    _monta_malha(client, "RODANDO", ["E", "F"])
    viva = db.abrir_corrida("RODANDO", odate=REFERENCIA, aberta_em=MADRUGADA,
                            membros=["E", "F"])
    db.execucao("E", "SUCESSO", odate=REFERENCIA,
                inicio=MADRUGADA + timedelta(minutes=10),
                fim=MADRUGADA + timedelta(minutes=40), corrida=viva["id"])
    db.execucao("F", "EXECUTANDO", odate=REFERENCIA,
                inicio=MADRUGADA + timedelta(minutes=45), corrida=viva["id"])
    # A que falhou, e FECHOU em falha.
    _monta_malha(client, "QUEBROU", ["G", "H"])
    ruim = db.abrir_corrida("QUEBROU", odate=REFERENCIA, aberta_em=MADRUGADA,
                            membros=["G", "H"], status="FALHA")
    db.execucao("G", "SUCESSO", odate=REFERENCIA,
                inicio=MADRUGADA + timedelta(minutes=10),
                fim=MADRUGADA + timedelta(minutes=40), corrida=ruim["id"])
    db.execucao("H", "FALHA", odate=REFERENCIA,
                inicio=MADRUGADA + timedelta(minutes=15),
                fim=MADRUGADA + timedelta(minutes=20), corrida=ruim["id"])


def _tarde_de_reprocesso(db, client):
    """Uma corrida concluída que NÃO fechou de madrugada (abriu 13:10, fechou
    14:10). A frase "na madrugada" não pode sair sobre ela."""
    _monta_malha(client, "M1", ["A", "B"])
    tarde = datetime(2026, 8, 4, 13, 10)
    c = db.abrir_corrida("M1", odate=REFERENCIA, aberta_em=tarde,
                         membros=["A", "B"], status="CONCLUIDA")
    for p in ("A", "B"):
        db.execucao(p, "SUCESSO", odate=REFERENCIA,
                    inicio=tarde + timedelta(minutes=10),
                    fim=tarde + timedelta(minutes=40), corrida=c["id"])


def _abortada_e_horaria(db, client):
    """A mesma manhã de 04/08 do cenário anterior, com as DUAS bordas que a
    revisão da F11 achou:

      • uma malha cuja corrida **ABORTOU** — desfecho vermelho cheio, e que não
        casava filtro nenhum, não tinha contador e não aparecia no Dashboard:
        a corrida que aborta à 01:00 ficava INVISÍVEL às 8h em todas as
        superfícies;
      • uma malha **horária** que já fechou a corrida da referência SEGUINTE às
        07:30. Com a régua pelo MÁXIMO, essa única corrida sequestrava a
        pílula: "1 concluída (referência 04/08)", com as 12 da madrugada caindo
        em `foraDaReferencia`. O número continuava batendo com o relatório do
        ODATE declarado — e a pergunta que o contador existe para responder,
        "a madrugada rodou?", passava a ser respondida com 1."""
    _madrugada(db, client)
    _monta_malha(client, "ABORTOU", ["I", "J"])
    db.abrir_corrida("ABORTOU", odate=REFERENCIA, aberta_em=MADRUGADA,
                     membros=["I", "J"], status="ABORTADA")
    _monta_malha(client, "HORARIA", ["K", "L"])
    nova = db.abrir_corrida("HORARIA", odate=date(2026, 8, 4),
                            aberta_em=datetime(2026, 8, 4, 7, 0),
                            membros=["K", "L"], status="CONCLUIDA")
    for pipe in ("K", "L"):
        db.execucao(pipe, "SUCESSO", odate=date(2026, 8, 4),
                    inicio=datetime(2026, 8, 4, 7, 5),
                    fim=datetime(2026, 8, 4, 7, 30), corrida=nova["id"])


def _so_rodando(db, client):
    """Uma corrida ABERTA e NENHUMA concluída — o cenário em que a palavra
    "concluída" não pode aparecer em lugar nenhum da página (nem num
    `<option>`)."""
    _monta_malha(client, "M1", ["A", "B"])
    viva = db.abrir_corrida("M1", odate=REFERENCIA, aberta_em=MADRUGADA,
                            membros=["A", "B"])
    db.execucao("A", "SUCESSO", odate=REFERENCIA,
                inicio=MADRUGADA + timedelta(minutes=10),
                fim=MADRUGADA + timedelta(minutes=40), corrida=viva["id"])
    db.execucao("B", "EXECUTANDO", odate=REFERENCIA,
                inicio=MADRUGADA + timedelta(minutes=45), corrida=viva["id"])


def _nada_em_movimento(db, client):
    """Uma malha concluída e mais nada: nenhuma corrida aberta, nenhum
    "não abriu". É o cenário do ZERO REFETCH da Decisão 73."""
    _monta_malha(client, "M1", ["A", "B"])
    c = db.abrir_corrida("M1", odate=REFERENCIA, aberta_em=MADRUGADA,
                         membros=["A", "B"], status="CONCLUIDA")
    for p in ("A", "B"):
        db.execucao(p, "SUCESSO", odate=REFERENCIA,
                    inicio=MADRUGADA + timedelta(minutes=10),
                    fim=MADRUGADA + timedelta(minutes=40), corrida=c["id"])


# ══════════════════════════════ as fixtures ══════════════════════════════════

@pytest.fixture(scope="module")
def auth_modulo(app):
    app.dependency_overrides[get_current_user] = lambda: {
        "matricula": "OPER1", "perfil": "operador",
        "permissoes": [PERM_EDITAR, PERM_EXECUTAR, "tela_malha"],
    }
    yield
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture(scope="module")
def payloads(client, auth_modulo) -> dict:
    return {
        "madrugada": _payload(client, _madrugada),
        "reprocesso_a_tarde": _payload(client, _tarde_de_reprocesso,
                                       agora_api=datetime(2026, 8, 4, 15, 0)),
        "abortada_e_horaria": _payload(client, _abortada_e_horaria),
        "so_rodando": _payload(client, _so_rodando),
        "nada_em_movimento": _payload(client, _nada_em_movimento),
    }


def _corrida_de(payload: dict, malha: str) -> dict:
    """A corrida que a API publicou para esta malha — a fonte de todo id que
    este arquivo usa. Nenhum número de corrida é escrito à mão: um id inventado
    faria o botão do card e a lente da tela combinarem entre si e com mais
    ninguém."""
    card = next(m for m in payload["malhas"] if m["malha_name"] == malha)
    return card["corrida"]


BASE_DO_APP = "https://orquestra.exemplo.com"


def _url_do_botao_do_card(payload: dict):
    """O endereço que o card de `MALHA_FALHOU` de fato publica no celular.

    Montado pelo `montar_card_malha` de produção, para o evento da malha que de
    fato falhou, com o id de corrida que a API de fato devolveu — nada aqui é
    escrito à mão. É a ponta de lá do aceite *"botão que abre
    `?malha=X&modo=execucao&corrida=N` e cai **direto** na corrida certa"*; a
    ponta de cá é a página, que recebe esta mesma query string."""
    from utils.ds_teams import montar_card_malha
    corrida = _corrida_de(payload, "QUEBROU")
    card = montar_card_malha(
        {"tipo": "MALHA_FALHOU", "malha": "QUEBROU", "data_ref": "2026-08-03",
         "detalhe": "H falhou 04:30", "detectado_em": "2026-08-04 04:30:00",
         "corrida_id": corrida["id"]},
        BASE_DO_APP)
    acoes = card["attachments"][0]["content"].get("actions") or []
    assert acoes, "o card de MALHA_FALHOU saiu SEM botão com a base configurada"
    return urlparse(acoes[0]["url"]), corrida["id"]


@pytest.fixture(scope="module")
def tela(payloads) -> dict:
    node = _node()
    if node is None:
        pytest.skip(_MOTIVO_SALTO)
    cenarios = {nome: {"payload": pl, "agora_ms": AGORA_LOCAL_MS}
                for nome, pl in payloads.items()}

    # ── o clique que FILTRA (aceite: "o filtro responde da LISTA") ──────────
    # Mesmo payload da manhã; a bancada aperta a pílula e REDESENHA a página
    # com o estado que o clique pediu — as duas passadas que o React faria.
    cenarios["clicou_rodando"] = {
        "payload": payloads["madrugada"], "agora_ms": AGORA_LOCAL_MS,
        "apertar": "rodando agora",
    }

    # ── o card do Teams chegando NA TELA ────────────────────────────────────
    # A query string é a do BOTÃO DO CARD, e o cenário abre a página com ela —
    # é o teste atravessando as duas árvores. Se qualquer uma das pontas mudar
    # o molde, este cenário abre a tela errada.
    url, _cid = _url_do_botao_do_card(payloads["madrugada"])
    cenarios["veio_do_card_do_teams"] = {
        "payload": payloads["madrugada"], "agora_ms": AGORA_LOCAL_MS,
        "url": url.query,
    }
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(cenarios, f)
        caminho = f.name
    try:
        r = subprocess.run([node, str(HARNESS), caminho], capture_output=True,
                           text=True, cwd=str(RAIZ), timeout=180)
        assert r.returncode == 0, f"bancada do front falhou:\n{r.stderr}"
        return json.loads(r.stdout)
    finally:
        os.unlink(caminho)


# ══════════════ a bancada do DASHBOARD (§9.8, Decisão 70) ═══════════════════

HARNESS_DASH = RAIZ / "tests" / "js" / "f11_dashboard_harness.cjs"

# O payload da lista, guardado em módulo para os testes do painel poderem ler
# o id de corrida que a API publicou (o mesmo que o clique tem de levar).
_PAYLOAD_ATUAL: dict = {}


def _deps_do_dashboard(client) -> dict:
    """`GET /pipelines/dependencias/estado` como o router de verdade o devolve.

    Dois dependentes esperando, e eles são o aceite inteiro deste painel:
    `PIPE_UMA` está em UMA malha (o link tem de abrir aquela malha) e
    `PIPE_DUAS` está em DUAS (o link tem de cair na lista — escolher uma seria
    abrir a malha errada com cara de certa)."""
    from tests.test_dependencias_f5 import FakePipeDb, _linha_pipeline
    from tests.test_malhas_f11 import _patch_pipes_db
    db = FakePipeDb(
        pipelines={n: _linha_pipeline(pipeline_name=n)
                   for n in ("PIPE_UMA", "PIPE_DUAS", "PAI_X")},
        malhas_do_pipeline={"PIPE_UMA": ["Carga_Vida"],
                            "PIPE_DUAS": ["Carga_Vida", "Carga_Prev"]})
    db.dependencias = [{"pipeline": "PIPE_UMA", "depende_de": "PAI_X"},
                       {"pipeline": "PIPE_DUAS", "depende_de": "PAI_X"}]
    with _patch_pipes_db(db):
        r = client.get("/pipelines/dependencias/estado"
                       f"?data_referencia={REFERENCIA.isoformat()}")
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(scope="module")
def painel(payloads, client, auth_modulo) -> dict:
    node = _node()
    if node is None:
        pytest.skip(_MOTIVO_SALTO)
    _PAYLOAD_ATUAL.update(payloads)
    deps = _deps_do_dashboard(client)
    cenarios = {
        "dash_madrugada": {"agora_ms": AGORA_LOCAL_MS,
                           "malhas": payloads["madrugada"], "deps": deps},
        "dash_parado": {"agora_ms": AGORA_LOCAL_MS,
                        "malhas": payloads["nada_em_movimento"], "deps": deps},
    }
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(cenarios, f)
        caminho = f.name
    try:
        r = subprocess.run([node, str(HARNESS_DASH), caminho],
                           capture_output=True, text=True, cwd=str(RAIZ),
                           timeout=180)
        assert r.returncode == 0, f"bancada do Dashboard falhou:\n{r.stderr}"
        return json.loads(r.stdout)
    finally:
        os.unlink(caminho)


def _painel(painel: dict, nome: str) -> dict:
    dado = painel[nome]
    assert "__erro__" not in dado, \
        f"{nome} levantou na bancada:\n{dado.get('__erro__')}"
    assert dado["erros"] == [], f"{nome} renderizou com exceção: {dado['erros']}"
    return dado


def _sao(tela: dict, nome: str) -> dict:
    """A página renderizou sem levantar. Sem o `cards` obrigatório — o cenário
    do deep-link do card do Teams abre o DIAGRAMA, e ali não há card nenhum."""
    dado = tela[nome]
    assert "__erro__" not in dado, \
        f"{nome} levantou na bancada:\n{dado.get('__erro__')}"
    assert dado["erros"] == [], f"{nome} renderizou com exceção: {dado['erros']}"
    return dado


def _cenario(tela: dict, nome: str) -> dict:
    dado = _sao(tela, nome)
    assert dado["cards"], f"{nome} renderizou a página sem nenhum card"
    return dado


def _pilula(cenario: dict, trecho: str) -> dict:
    achadas = [s for s in cenario["stats"] if trecho in s["texto"]]
    assert len(achadas) == 1, (
        f"esperava UMA pílula com {trecho!r}; achei {len(achadas)}: "
        f"{[s['texto'] for s in cenario['stats']]}")
    return achadas[0]


def _filtro_de_corrida(cenario: dict) -> dict:
    achados = [f for f in cenario["filtros"]
               if f["aria"] == "Filtrar pelo estado do ciclo"]
    assert len(achados) == 1, f"filtros na tela: {cenario['filtros']}"
    return achados[0]


# ═════════ ACEITE — o contador declara a RÉGUA, e o número bate ═════════════

def test_o_contador_de_concluidas_declara_a_referencia_e_nao_mostra_zero(tela):
    """O aceite literal: *"`12 concluídas na madrugada (referência 03/08)` — às
    08:00 de 04/08 ele **não** mostra `0` por filtrar ODATE = hoje, nem um
    número que não bate com nenhum relatório por ODATE"*.

    Os três defeitos que a frase mata, na ordem em que apareceriam:
      • **0 por filtrar hoje** — a madrugada carimba a referência de ONTEM;
      • **um número sem régua** — "12 concluídas" de que dia? A pílula seria
        verdadeira e ininterpretável;
      • **um número que soma referências** — a malha que concluiu 02/08 e parou
        entraria na conta, e aí ela não bate com relatório nenhum por ODATE."""
    c = _cenario(tela, "madrugada")
    pilula = _pilula(c, "concluíd")
    assert pilula["texto"] == "12 concluídas na madrugada (referência 03/08)"
    # e a que ficou em 02/08 NÃO entrou na conta — o número é de UM ODATE só
    assert "13" not in pilula["texto"]


def test_a_corrida_que_ABORTOU_nao_fica_invisivel(tela):
    """O modo de falha silencioso que a revisão da F11 achou.

    `ABORTADA` é vermelho cheio — "não chegou a começar" — e é alcançável (a
    guardiã fecha assim a corrida que passou da carência sem nenhuma execução).
    Ela não casava filtro nenhum, não tinha contador e não aparecia no
    Dashboard: a corrida que aborta à 01:00 ficava invisível às 8h em TODAS as
    superfícies. É o defeito que esta spec inteira existe para acabar, com
    roupa nova — e a tela não pode reintroduzi-lo justamente na fase que se
    chama "onde o ciclo chega antes da tela de Malha".

    Ela entra em "Com falha" porque é lá que o operador procura o que exige
    ação agora."""
    c = _cenario(tela, "abortada_e_horaria")
    pilula = _pilula(c, "falha")
    # a que FECHOU em falha + a que ABORTOU
    assert pilula["texto"].startswith("2 ")
    nomes = {card["malha"] for card in c["cards"]}
    assert "ABORTOU" in nomes


def test_uma_corrida_de_outra_referencia_nao_sequestra_a_regua(tela):
    """A régua das concluídas é a data da MAIORIA, não a mais recente.

    Com o máximo, uma única malha horária que fechou às 07:30 já com a
    referência do dia seguinte virava a pílula inteira: "1 concluída
    (referência 04/08)", e as 12 da madrugada caíam em `foraDaReferencia`. O
    número continuava batendo com o relatório daquele ODATE — e a pergunta que
    o contador existe para responder, *"a madrugada rodou?"*, passava a ser
    respondida com **1**."""
    c = _cenario(tela, "abortada_e_horaria")
    pilula = _pilula(c, "concluíd")
    assert "12 concluídas" in pilula["texto"]
    assert "referência 03/08" in pilula["texto"]
    assert "04/08" not in pilula["texto"]


def test_o_contador_e_um_botao_de_estado_e_nao_um_enfeite(tela):
    """Decisão 75 — contador que age como filtro é `<button>` com
    `aria-pressed` (molde de `PainelRealce`). Sem isso o leitor de tela anuncia
    "12 concluídas" sem dizer que ESTE é o filtro ligado; e sem o `onClick`, o
    caminho mais curto de "a madrugada rodou?" para "quais rodaram" não
    existe."""
    c = _cenario(tela, "madrugada")
    for trecho, estado in (("concluíd", "concluida"),
                           ("rodando agora", "rodando"),
                           ("com falha", "falha")):
        pilula = _pilula(c, trecho)
        assert pilula["clicavel"], f"a pílula {trecho!r} não é botão"
        assert pilula["pressionado"] is False   # existe e está DESLIGADO
        # O clique de verdade: o valor pedido ao `setState`. Um contador
        # clicável e inerte sairia daqui com `[]`.
        assert pilula["clique"] == [estado], (
            f"clicar em {trecho!r} pediu {pilula['clique']}, não {estado!r}")


def test_os_contadores_contam_por_ESTADO_e_nao_por_particao(tela):
    """§9.15/#10 — `falhou`, `fora do prazo` e `rodando` têm donos diferentes e
    não viram um número só. E a contagem é sobre o conjunto de ANTES do filtro
    por estado: contar sobre o próprio resultado faria os outros contadores
    irem a zero e sumirem no primeiro clique, e aí não haveria como trocar de
    filtro pela stats bar."""
    c = _cenario(tela, "madrugada")
    assert _pilula(c, "rodando agora")["texto"] == "1 rodando agora"
    assert _pilula(c, "com falha")["texto"] == "1 com falha"
    # 15 malhas na tela: 12 + a de 02/08 + a que roda + a que falhou
    assert len(c["cards"]) == 15


def test_na_madrugada_nao_e_dito_sobre_corrida_que_fechou_a_tarde(tela):
    """A régua tem duas metades, e a segunda é uma afirmação sobre o RELÓGIO.
    Dizer "na madrugada" sobre uma corrida que fechou às 14:10 seria inventar
    um fato para caber numa frase bonita — a referência continua declarada, a
    hora some."""
    c = _cenario(tela, "reprocesso_a_tarde")
    pilula = _pilula(c, "concluíd")
    assert pilula["texto"] == "1 concluída (referência 03/08)"
    assert "madrugada" not in pilula["texto"]


# ═════════ ACEITE — o filtro responde DA LISTA ══════════════════════════════

def test_o_filtro_de_corrida_existe_AO_LADO_do_de_situacao(tela):
    """O aceite: *"filtro por estado de corrida ao lado do filtro
    Ativas/Inativas"*. Ao LADO, e não no lugar: "ativa" é situação de
    CADASTRO e "rodando agora" é estado de CICLO — o plantão cruza os dois
    ("que malha ATIVA não rodou?")."""
    c = _cenario(tela, "madrugada")
    arias = [f["aria"] for f in c["filtros"]]
    assert "Filtrar por situação da malha" in arias
    assert "Filtrar pelo estado do ciclo" in arias


def test_os_cinco_estados_estao_no_filtro_na_ordem_da_gravidade(tela):
    """A ordem é a mesma no `<select>` e na stats bar: dois lugares com a mesma
    lista em ordens diferentes fazem o olho procurar duas vezes."""
    c = _cenario(tela, "madrugada")
    opcoes = [o["rotulo"] for o in _filtro_de_corrida(c)["opcoes"]]
    assert opcoes == ["Todos os ciclos", "Rodando agora", "Com falha",
                      "Fora do prazo", "Não abriram", "Concluídas (ref. 03/08)"]


def test_o_filtro_de_concluidas_tambem_declara_a_regua(tela):
    """`Concluídas` sozinho não diz de que dia — e o rótulo dele é a única
    superfície que o operador vê ANTES de aplicar o filtro."""
    c = _cenario(tela, "madrugada")
    rotulos = [o["rotulo"] for o in _filtro_de_corrida(c)["opcoes"]]
    assert "Concluídas (ref. 03/08)" in rotulos


def test_sem_corrida_concluida_a_palavra_proibida_nao_entra_por_um_option(tela):
    """Decisão 41 e §9.15/#15 — "concluída" não se escreve sem
    `status = 'CONCLUIDA'` vindo do banco, e a proibição é da PÁGINA inteira,
    não do card. Um `<option>` fixo furaria a regra por uma porta que ninguém
    olharia: a varredura de ausência da F9 lê texto, `title` e `aria-*`, e um
    rótulo de filtro está em todos os três.

    Por isso a opção só existe quando existe corrida concluída — que é também
    quando ela tem régua para declarar. Um filtro que só pode devolver zero é
    um controle morto; um que anuncia uma referência inexistente é pior."""
    c = _cenario(tela, "so_rodando")
    rotulos = [o["rotulo"] for o in _filtro_de_corrida(c)["opcoes"]]
    assert "Rodando agora" in rotulos
    assert not [r for r in rotulos if "onclu" in r]
    baixo = c["lido"].lower()
    assert "concluída" not in baixo and "concluida" not in baixo
    # e o contador correspondente também não existe (regra da Decisão 58,
    # agora valendo para os cinco estados)
    assert not [s for s in c["stats"] if "onclu" in s["texto"]]


# ═════════ ACEITE — polling condicional (Decisão 73) ════════════════════════

def test_sem_corrida_aberta_nem_nao_abriu_a_lista_NAO_faz_refetch(tela):
    """*"sem corrida aberta nem `não abriu` visível → **zero** refetch"*.

    Perguntado à função (`refetchInterval` é chamada com o payload do
    cenário), não lido no fonte: um `refetchInterval` que devolvesse 20 s aqui
    seria a tela batendo na API a cada 20 s, 24 h por dia, por causa das 4 da
    madrugada — e o endpoint faz duas consultas de conjunto por chamada."""
    assert _cenario(tela, "nada_em_movimento")["polling"] is False


def test_com_corrida_aberta_a_lista_se_atualiza_a_cada_20s(tela):
    """O contrapeso: com algo em voo a tela anda sozinha. O predicado é a
    LISTA INTEIRA — uma corrida em voo escondida por um filtro continua sendo
    uma corrida em voo, e filtrar por "Concluídas" não pode congelar o relógio
    da que está falhando do outro lado do filtro."""
    assert _cenario(tela, "madrugada")["polling"] == 20_000


# ═════════ ACEITE — o Dashboard (§9.8, Decisão 70) ══════════════════════════
#
# Duas provas de árvores diferentes, e as duas precisam existir:
#   • a MALHA do dependente vem do servidor (é ela que faz o link parar de
#     despejar o operador na lista) — provada contra o router;
#   • o Dashboard consome o MESMO payload da lista, com a MESMA chave de cache
#     e a MESMA cadência — provado no fonte, porque é uma afirmação sobre
#     ACOPLAMENTO: duas chaves iguais é o que garante "zero consulta nova", e
#     nenhuma árvore renderizada mostra isso.

def test_o_estado_de_dependencia_diz_a_malha_quando_ela_e_UNICA(client,
                                                                auth_modulo):
    """O link do painel "Aguardando dependência" era `navigate('/malha')`, sem
    malha e sem modo: quem clicava numa linha que nomeia o pipeline e o
    predecessor caía numa grade de 40 cards em ordem alfabética.

    A malha vem por subconsulta correlacionada na consulta que já existia —
    nenhum round-trip novo na tela mais vista do produto."""
    from tests.test_dependencias_f5 import FakePipeDb, _linha_pipeline
    from tests.test_malhas_f11 import _patch_pipes_db
    db = FakePipeDb(
        pipelines={"PIPE_A": _linha_pipeline(pipeline_name="PIPE_A"),
                   "PAI_X": _linha_pipeline(pipeline_name="PAI_X")},
        malhas_do_pipeline={"PIPE_A": ["Carga_Vida"]})
    db.dependencias = [{"pipeline": "PIPE_A", "depende_de": "PAI_X"}]
    with _patch_pipes_db(db):
        r = client.get("/pipelines/dependencias/estado?data_referencia=2026-08-01")
    assert r.status_code == 200, r.text
    item = next(i for i in r.json()["data"] if i["pipeline_name"] == "PIPE_A")
    assert item["malha"] == "Carga_Vida"


@pytest.mark.parametrize("malhas,por_que", [
    (["M1", "M2"], "em duas malhas: escolher uma abriria a malha ERRADA com "
                   "cara de certa, e o Orquestra permite o mesmo pipeline em "
                   "várias de propósito"),
    ([], "em nenhuma malha: não há o que abrir"),
])
def test_sem_malha_UNICA_a_chave_nao_sai(client, auth_modulo, malhas, por_que):
    """Ausência de CAMPO, nunca `null` interpretável — o front cai no caminho
    seguinte (a malha que compilou a dependência) e, sem ele, no link de hoje.
    Melhor a lista do que a malha errada."""
    from tests.test_dependencias_f5 import FakePipeDb, _linha_pipeline
    from tests.test_malhas_f11 import _patch_pipes_db
    db = FakePipeDb(
        pipelines={"PIPE_A": _linha_pipeline(pipeline_name="PIPE_A"),
                   "PAI_X": _linha_pipeline(pipeline_name="PAI_X")},
        malhas_do_pipeline={"PIPE_A": malhas})
    db.dependencias = [{"pipeline": "PIPE_A", "depende_de": "PAI_X"}]
    with _patch_pipes_db(db):
        r = client.get("/pipelines/dependencias/estado?data_referencia=2026-08-01")
    assert r.status_code == 200, r.text
    item = next(i for i in r.json()["data"] if i["pipeline_name"] == "PIPE_A")
    assert "malha" not in item, por_que


def test_sem_a_070_o_estado_de_dependencia_continua_de_pe(client, auth_modulo):
    """Deploy parcial: sem `etl_malha_pipeline` o SQL nasce com o literal
    `NULL` e a chave some. A tela mais vista do produto não vira 500 por causa
    de um link."""
    from tests.test_dependencias_f5 import FakePipeDb, _linha_pipeline
    from tests.test_malhas_f11 import _patch_pipes_db
    db = FakePipeDb(
        pipelines={"PIPE_A": _linha_pipeline(pipeline_name="PIPE_A"),
                   "PAI_X": _linha_pipeline(pipeline_name="PAI_X")},
        com_070=False, malhas_do_pipeline={"PIPE_A": ["Carga_Vida"]})
    db.dependencias = [{"pipeline": "PIPE_A", "depende_de": "PAI_X"}]
    with _patch_pipes_db(db):
        r = client.get("/pipelines/dependencias/estado?data_referencia=2026-08-01")
    assert r.status_code == 200, r.text
    item = next(i for i in r.json()["data"] if i["pipeline_name"] == "PIPE_A")
    assert "malha" not in item


# ── O Dashboard, RENDERIZADO (e não `grep`) ─────────────────────────────────
#
# ⚠️ Esta seção nasceu de duas mutações que SOBREVIVERAM à versão anterior
# destes testes, que era `grep` no `.tsx`:
#   • apagar `<CorridasDeMalhaCard />` do JSX — o bloco existe, compila e nunca
#     é montado;
#   • `malhaDoDependente` devolvendo sempre `null` — o link volta a despejar o
#     operador na lista, que é exatamente o defeito que a fase conserta.
# As duas passavam. É o modo de falso verde que a F10 pagou nesta spec: `grep`
# provando texto que nenhum ramo renderiza. Agora a página é renderizada e os
# cliques são apertados — o que se afirma é PARA ONDE o operador vai.


def test_o_dashboard_MOSTRA_a_corrida_e_o_clique_cai_nela(painel):
    """Decisão 70 — o Dashboard é a tela em que o plantonista de fato cai, e
    ela era CEGA para o ciclo: mostra pipeline a pipeline, e a pergunta das 3h
    é "que MALHA está rodando, e ela está bem"."""
    c = _painel(painel, "dash_madrugada")
    # INVERSÃO (2026-08-09, formato Supervisão): TODAS as 15 malhas ativas
    # entram — as 12 concluídas inclusive, porque durante a migração
    # DataStage → Orquestra "está tudo bem" precisa ser AFIRMADO por uma linha
    # com rótulo, não deduzido da ausência. A GRAVIDADE continua mandando na
    # ordem: primeiro a que não abriu (o pior modo de falha, e o mais
    # silencioso), depois a que falhou, depois a que roda saudável — e a
    # confirmação positiva fecha a lista, em ordem alfabética estável.
    nomes = [l["malha"] for l in c["corridas"]]
    assert nomes[:3] == ["ATRASADA_NA_REF", "QUEBROU", "RODANDO"]
    assert nomes[3:] == [f"OK_{i:02d}" for i in range(CONCLUIDAS)]
    # O resumo do cabeçalho conta pelo MESMO predicado que pinta as linhas:
    # não abriu + falhou = 2; a que roda saudável não é problema.
    assert "2 de 15 com problema" in (c["cabecalho"] or "")
    corrida = _corrida_de(_PAYLOAD_ATUAL["madrugada"], "RODANDO")
    linha = next(l for l in c["corridas"] if l["malha"] == "RODANDO")
    assert linha["navegou"] == \
        f"/malha?malha=RODANDO&modo=execucao&corrida={corrida['id']}"
    # O rótulo é `x de y`, e o substantivo é pipelines (Decisão 56): `1 de 2`
    # lido como `50%` seria percentual de um trabalho que não existe — os
    # pipelines têm durações diferentes. Nenhuma linha desta região traz `%`
    # nem `#N` (Decisão 74: a corrida se chama pela data, o id só viaja na URL).
    assert "1 de 2" in linha["texto"]
    for l in c["corridas"]:
        assert "%" not in l["texto"], l["texto"]
        assert not re.search(r"#\d", l["texto"]), l["texto"]


def test_o_dashboard_le_a_MESMA_chave_e_a_MESMA_cadencia_da_lista(painel, tela):
    """"Zero consulta nova" (Decisão 70) é uma afirmação sobre ACOPLAMENTO: só
    é verdade se as duas telas usarem a MESMA chave de cache. Com chaves
    diferentes o react-query manteria dois payloads e dois pollings da mesma
    rota, e o "mesmo payload da lista" viraria o DOBRO do custo.

    Perguntado às duas bancadas, e não ao fonte: a chave que o Dashboard
    registrou, e a cadência que a função DELE devolve para o mesmo payload —
    comparada com a que a lista devolveu para o mesmo payload."""
    c = _painel(painel, "dash_madrugada")
    das_malhas = [q for q in c["consultas"] if q["chave"] == ["malhas"]]
    assert len(das_malhas) == 1, f"consultas do Dashboard: {c['consultas']}"
    assert das_malhas[0]["cadencia"] == _cenario(tela, "madrugada")["polling"]

    parado = _painel(painel, "dash_parado")
    das_malhas = [q for q in parado["consultas"] if q["chave"] == ["malhas"]]
    assert das_malhas[0]["cadencia"] is False
    # INVERSÃO (2026-08-09, formato Supervisão): sem nada em voo o painel NÃO
    # some mais — fica a confirmação positiva ("1 sem problema"), que é o
    # aceite da migração DataStage → Orquestra. O que NÃO mudou é o custo:
    # painel visível com ZERO refetch (a cadência `False` logo acima é a
    # Decisão 73 intacta — visível ≠ pollando).
    assert parado["tem_card_de_corrida"] is True
    assert [l["malha"] for l in parado["corridas"]] == ["M1"]
    assert "1 sem problema" in (parado["cabecalho"] or "")


def test_o_link_de_dependencia_leva_a_malha_certa_com_modo_E_data(painel):
    """O aceite: o link *"passando a levar malha **e** modo"*.

    Era `navigate('/malha')`: quem clicava numa linha que nomeia o pipeline e o
    predecessor caía numa grade de cards em ordem alfabética e tinha de achar a
    malha, abrir, trocar o modo e escolher a data. Agora leva à malha, na lente
    de execução e na data de referência que a própria linha declara."""
    c = _painel(painel, "dash_madrugada")
    por_texto = {l["texto"].split()[0]: l for l in c["dependencias"]}
    assert set(por_texto) == {"PIPE_UMA", "PIPE_DUAS"}
    assert por_texto["PIPE_UMA"]["navegou"] == \
        "/malha?malha=Carga_Vida&modo=execucao&data=2026-08-03"


def test_pipeline_em_DUAS_malhas_cai_na_lista_e_o_titulo_DIZ_por_que(painel):
    """Melhor a lista do que a malha errada com cara de certa. E o operador
    precisa saber por que caiu na lista — senão o link parece quebrado."""
    c = _painel(painel, "dash_madrugada")
    linha = next(l for l in c["dependencias"] if l["texto"].startswith("PIPE_DUAS"))
    assert linha["navegou"] == "/malha"
    assert "não está numa malha só" in (linha["title"] or "")


# ═════════ ACEITE — do card do celular à corrida certa, sem escala ══════════

def test_o_botao_do_card_do_teams_cai_DIRETO_na_corrida_certa(tela, payloads):
    """O primeiro bullet do aceite, inteiro e nas DUAS pontas.

    *"card de `MALHA_FALHOU` no Teams → botão que abre
    `?malha=X&modo=execucao&corrida=N` e cai **direto** na corrida certa"*.

    Metade dele já estaria provada pelo `test_ds_teams` (a URL que o card
    publica) e metade pelo aceite da F10 (a página lê `?corrida=`). Ficaria de
    fora exatamente o que o operador vive às 3h: as duas pontas usando o MESMO
    molde. Um `&run=` de um lado e um `?corrida=` do outro deixam as duas
    suítes verdes e o botão abrindo a lista.

    Aqui a query string entregue à página é literalmente a do botão do card, e
    o id de corrida é o que a API devolveu para aquela malha — nada escrito à
    mão. O que se afirma no fim é a LENTE que o editor recebeu, não um texto."""
    url, corrida_id = _url_do_botao_do_card(payloads["madrugada"])
    # a rota, antes da lente: `/malha` é a tela, e um `/malhas` no molde do
    # card levaria a um 404 no celular sem que nenhum teste de URL notasse
    assert url.path == "/malha"
    assert url.query == f"malha=QUEBROU&modo=execucao&corrida={corrida_id}"

    c = _sao(tela, "veio_do_card_do_teams")
    assert c["editor"] == [{
        "malha": "QUEBROU", "modoInicial": "execucao",
        "dataInicial": None, "corridaInicial": corrida_id,
    }], "a página abriu com outra lente (ou não abriu o diagrama)"
    # e a lista NÃO é o que se vê: o botão do card não passa pela grade de 40
    # cards em ordem alfabética — que é o caminho que esta fase existe para
    # encurtar
    assert c["cards"] == []


def test_a_corrida_da_lente_e_a_do_EVENTO_e_nao_a_corrente_da_malha(payloads):
    """Decisão 69, a parte que só se vê comparando dois ids: o botão aponta
    para a corrida DAQUELE evento.

    Às 3h chega o card de um ciclo específico; abrir "a corrida corrente da
    malha" responderia a pergunta errada — e no dia seguinte, quando alguém
    reabrisse o card no histórico do Teams, ele levaria à corrida da noite
    seguinte com cara de ser a do alerta."""
    from utils.ds_teams import url_da_corrida
    corrente = _corrida_de(payloads["madrugada"], "QUEBROU")["id"]
    antiga = corrente - 7
    assert url_da_corrida(BASE_DO_APP, "QUEBROU", antiga).endswith(
        f"&corrida={antiga}")


# ═════════ ACEITE — o filtro RESPONDE (a lista encolhe) ═════════════════════

def test_o_filtro_rodando_agora_responde_DA_LISTA(tela):
    """*"filtro `Rodando agora` responde da lista, sem abrir malha por malha —
    hoje é **impossível** saber qual malha está rodando sem abrir uma a uma e
    trocar o modo"*.

    "Responder" é a LISTA ENCOLHER, e não o botão pedir um valor. A bancada
    aperta o contador de verdade, anota o estado que o clique pediu e redesenha
    a página com ele — as duas passadas que o React faria. Um contador clicável
    e inerte não semeia nada e a segunda passada mostra as 15 malhas de novo."""
    c = _sao(tela, "clicou_rodando")
    assert c["pedido"] == ["rodando"], \
        f"o clique pediu {c['pedido']} — o contador está decorativo?"
    # ANTES: as 15 da manhã. DEPOIS: só a que está com a corrida ABERTA.
    assert len(c["antes"]["ordem"]) == 15
    assert c["ordem"] == ["RODANDO"]
    # e o contador fica LIGADO — sem `aria-pressed` verdadeiro o leitor de tela
    # anuncia "1 rodando agora" sem dizer que este é o filtro em vigor
    assert _pilula(c, "rodando agora")["pressionado"] is True


def test_com_o_filtro_ligado_os_OUTROS_contadores_continuam_na_tela(tela):
    """Contar sobre o resultado do próprio filtro faria os outros contadores
    irem a zero e sumirem no primeiro clique — e aí não haveria como trocar de
    filtro pela stats bar, que é o gesto que esta fase entrega. Com "Rodando
    agora" ligado, "12 concluídas" continua lá, com o mesmo número."""
    c = _sao(tela, "clicou_rodando")
    assert _pilula(c, "concluíd")["texto"] == \
        "12 concluídas na madrugada (referência 03/08)"
    assert _pilula(c, "com falha")["texto"] == "1 com falha"


def test_o_segundo_clique_no_contador_ligado_volta_a_mostrar_tudo(tela):
    """Um filtro sem volta é um beco: quem clica em "1 rodando agora" às 3h
    precisa voltar à varredura sem recarregar a página. O contador ligado pede
    `''` — o mesmo botão, o gesto inverso."""
    c = _sao(tela, "clicou_rodando")
    assert _pilula(c, "rodando agora")["clique"] == [""]


def test_a_lista_INTEIRA_custa_UMA_consulta_na_tela(tela):
    """A outra metade do "sem abrir malha por malha": o custo.

    Um filtro que respondesse "abrindo" cada malha apareceria aqui como 15
    chaves de consulta — uma por card — e nenhuma asserção de texto pegaria
    isso. A página monta UMA consulta, a da lista, e o filtro é client-side
    sobre o payload que já está em mãos."""
    for nome in ("madrugada", "clicou_rodando"):
        c = _sao(tela, nome)
        assert c["chaves"] == [["malhas"]], \
            f"{nome} montou consultas demais: {c['chaves']}"


# ═════════ ACEITE — o orçamento de consultas (Decisão 73) ═══════════════════

def test_lista_de_40_malhas_custa_DUAS_consultas_por_refetch(client,
                                                             auth_modulo):
    """*"lista com 40 malhas → **duas** consultas por refetch (medido)"*.

    Medido, e no cenário DESTA fase: com o polling condicional a lista se
    refaz a cada 20 s enquanto houver corrida em voo, e uma consulta por malha
    seria 40 idas ao banco a cada 20 s, em plena madrugada, por operador com a
    aba aberta. O `db.sqls` é zerado depois da montagem — o que se conta é o
    REFETCH, não o cadastro."""
    gastos = {}

    def montar(quantas):
        def monta(db, client_):
            for i in range(quantas):
                nome = f"M{i:03d}"
                _monta_malha(client_, nome, ["A", "B"])
                c = db.abrir_corrida(nome, odate=REFERENCIA,
                                     aberta_em=MADRUGADA, membros=["A", "B"])
                db.execucao("A", "SUCESSO", odate=REFERENCIA,
                            inicio=MADRUGADA + timedelta(minutes=10),
                            fim=MADRUGADA + timedelta(minutes=40),
                            corrida=c["id"])
        return monta

    for quantas in (4, 40):
        pl = _payload(client, montar(quantas),
                      medir=lambda db, q=quantas: gastos.__setitem__(
                          q, list(db.sqls)))
        assert len(pl["malhas"]) == quantas
        assert sum(1 for m in pl["malhas"] if m.get("corrida")) == quantas

    da_corrida = [s for s in gastos[40] if "etl_malha_execucao" in s]
    # ⚠️ Eram DUAS até a F11; a F12 acrescentou a terceira — o histórico
    # factual da Decisão 68 (`falhou 2 das últimas 7 corridas`), também de
    # CONJUNTO, com `ROW_NUMBER() OVER (PARTITION BY malha_name)`. Ela ficou
    # fora da consulta (A) de propósito, para poder falhar sozinha: dobrada num
    # `OUTER APPLY`, um erro na leitura do histórico levaria junto o bloco
    # `corrida` inteiro, e o card perderia o CICLO por causa de uma frase de
    # contexto. O que este aceite protege — custo constante, nunca por malha —
    # continua provado pela comparação de 4 × 40 logo abaixo.
    assert len(da_corrida) == 3, "\n".join(da_corrida)
    assert sum(1 for s in da_corrida
               if "ROW_NUMBER() OVER (PARTITION BY malha_name" in s) == 1
    # E o TOTAL não cresce: a contagem das consultas do bloco não basta
    # sozinha — ela ficaria verde com um probe de tabela por malha ao lado.
    assert len(gastos[4]) == len(gastos[40]), (
        f"4 malhas gastaram {len(gastos[4])} statements e 40 gastaram "
        f"{len(gastos[40])} — entrou um N+1")


def test_sem_nada_em_voo_a_lista_nao_bate_na_api_de_novo(tela):
    """O outro lado do mesmo aceite, e o que torna o polling barato: *"sem
    corrida aberta nem `não abriu` visível → **zero** refetch"*.

    `false`, e não um número grande: um intervalo de 5 min ainda seriam 288
    chamadas por dia por aba aberta, numa tela que hoje não tem polling
    nenhum — pagar o custo das 24 h por causa das 4 da madrugada."""
    assert _cenario(tela, "nada_em_movimento")["polling"] is False


# ═════════ ACEITE — a fase antiga não fala mais com o operador ══════════════

_FASE_ANTIGA = re.compile(r"chega na F")


def test_nenhum_texto_de_fase_antiga_sobrou_na_interface():
    """*"`grep -rn "chega na F" ui-react/src` volta vazio"*.

    Não é limpeza cosmética: "o diagrama de montagem chega na F8" era uma
    promessa exibida ao operador sobre uma fase que já está em produção há
    semanas. Texto de plano de obra na tela ensina a não acreditar no que a
    tela diz.

    A varredura é a do aceite, literal — a árvore inteira do `src/`, código e
    comentário: um comentário que promete fase é a próxima frase que alguém
    copia para dentro de um `<p>`."""
    achados = []
    for raiz, _dirs, arquivos in os.walk(SRC_UI):
        for nome in arquivos:
            if not nome.endswith((".ts", ".tsx", ".css", ".html")):
                continue
            caminho = os.path.join(raiz, nome)
            with open(caminho, encoding="utf-8") as f:
                for n, linha in enumerate(f, 1):
                    if _FASE_ANTIGA.search(linha):
                        achados.append(f"{caminho}:{n}: {linha.strip()}")
    assert achados == [], "\n".join(achados)
