"""
F12 de `docs/spec-malha-execucao.md` (§9.5, §9.7 e §10 "### F12") — a **SUÍTE DE
ACEITE**, um teste por bullet, cada um nomeado pelo que prova.

── O que ela acrescenta às outras quatro suítes da fase ─────────────────────
`test_malhas_f12_tipicos.py` e `test_malhas_f12_historico.py` provam o
SERVIDOR; `test_malhas_f12_front.py` e `test_malhas_f12_historico_front.py`
provam os módulos e os componentes do front a partir de objetos escritos à mão.
Restavam as duas juntas — e é aí que moram os dois modos de falso verde mais
caros desta spec:

  1. **dublê que fabrica dado que o servidor real nunca produz** (o da F8). Um
     `{"tipicos": {"completo": true, "itens": […]}}` escrito no teste sempre
     casa com o componente que o mesmo teste exercita. Aqui NADA é escrito à
     mão: cada cenário é montado no dublê do banco, perguntado a
     `GET /malhas`, `GET /malhas/{m}`, `GET /malhas/{m}/execucao` e
     `GET /malhas/{m}/corridas`, e entregue à tela **exatamente como o router o
     serializou**;
  2. **dublê mais PERMISSIVO que o contrato** (o da F10), na forma que esta
     fase específica convida: o percentual da Decisão 56b e os `tipicos[]` da
     Decisão 64 são calculados/lidos no `MalhaEditor` e DESCEM por prop. Uma
     bancada que chame `CabecalhoCorrida` já com `percentualTempo` pronto prova
     o componente e não prova a tela — apagar `percentualTempo={percentualTempo}`
     do editor deixaria a faixa muda com a suíte inteira verde. Por isso o que
     se renderiza aqui é o **`MalhaEditor` inteiro** e a **página `/malha`
     inteira**, e o número aparece porque o código de produção o passou.

── O ACEITE QUE MANDA NESTA FASE, e por que ele é de AUSÊNCIA ───────────────
⚠️ **Esta é a única fase da spec que depende de corrida REAL gravada.** Antes do
smoke o histórico é literalmente ZERO — e um número sem amostra é o que esta
spec inteira existe para não produzir. Por isso o primeiro teste daqui é o do
DIA 1, nas DUAS superfícies: com zero corridas fechadas nenhuma frase desta fase
é renderizada e nada quebra. **`n = 0` é ausência, nunca "0%".**

As provas de ausência varrem tudo o que se lê — texto, `title` e todo `aria-*`.
É por `title` e por `aria-valuetext` que um número escapa sem ninguém ver: foi
assim que o percentual de CONTAGEM da Decisão 56 quase voltou pela porta da
acessibilidade na F9.

⚠️ **Nada toca o banco**: o servidor é dublê e o front roda no Node. Sem `node`
ou sem `ui-react/node_modules`, as bancadas SALTAM (visível no `-rs`) — nunca
passam em silêncio; os aceites de servidor deste arquivo continuam valendo.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import date, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()
os.environ.setdefault("MSSQL_CONN_STR", "__mock__")
from api.main import app as _app  # noqa: F401  (ordem de import — ver test_copias.py)

from deps import PERM_EDITAR, PERM_EXECUTAR, get_current_user
from routers import malhas as malhas_router
from services import malha_corrida as mc
from tests.test_malha_corrida_porta import AGORA_API, AGORA_BANCO
from tests.test_malhas_f4_card import ODATE, _patch, _pipes
from tests.test_malhas_f10 import _monta_malha
from tests.test_malhas_f12_tipicos import ABERTURA, FakeDb
from tests.test_malhas_f9_aceite import (HARNESS as HARNESS_PAGINA, RAIZ,
                                         _MOTIVO_SALTO, _node)

HARNESS_PAINEL = RAIZ / "tests" / "js" / "f12_aceite_harness.cjs"

# ── Os dois relógios, e o desvio entre eles É parte do aceite ───────────────
# O processo da API marca 07:00 e o SQL Server responde 10:00 — o desvio MEDIDO
# no dev (Decisão 60). Todo carimbo montado abaixo está na régua do BANCO,
# porque é o banco que os carimba em produção; o relógio LOCAL da tela é o da
# API. `há 12 min` só dá 12 se as duas pontas forem respeitadas — com
# `Date.now() − inicio` daria "−2h48".

def _epoch_ms(dt: datetime) -> int:
    """Instante LOCAL do navegador, em ms.

    Fixado em UTC de propósito: a bancada compara este número consigo mesmo
    (frescor) e com carimbos do banco lidos pelo mesmo caminho — o que
    importa é a DIFERENÇA, e ancorar em UTC a torna independente do fuso da
    máquina que roda a suíte."""
    from datetime import timezone
    return int(dt.replace(tzinfo=timezone.utc).timestamp() * 1000)


# 2026-08-04 é TERÇA; 2026-08-05, quarta; 2026-08-08, sábado.
TERCA = date(2026, 8, 4)
SABADO = date(2026, 8, 8)

_EXTRAS = ["CARGA_C", "CARGA_D", "CARGA_E", "PESADO",
           "R1", "R2", "R3", "R4", "R5",
           # o cenário `com_dispensados`: 4 que rodam + 3 dispensados pela
           # regra do dia, todos com o mesmo tempo típico
           "D1", "D2", "D3", "D4", "P1", "P2", "P3"]


def _cadastro():
    """O cadastro da F4 mais os nomes que os cenários desta fase usam."""
    base = _pipes()
    modelo = dict(next(iter(base.values())))
    for nome in _EXTRAS:
        base[nome] = dict(modelo)
    return base


def _sessao():
    return {"matricula": "OPER1", "perfil": "operador",
            "permissoes": [PERM_EDITAR, PERM_EXECUTAR, "tela_malha"]}


@pytest.fixture(scope="module")
def auth_modulo(app):
    """A sessão de um operador — o perfil de quem está de plantão às 3h."""
    app.dependency_overrides[get_current_user] = lambda: _sessao()
    yield
    app.dependency_overrides.pop(get_current_user, None)


def _com_duble(client, monta, *, agora_api=AGORA_API, agora_banco=AGORA_BANCO):
    """Monta o cenário no dublê e devolve o que o ROUTER de verdade respondeu.

    O `monta` recebe `(db, client)` e devolve a corrida da lente. O que sai
    daqui é o payload literal dos quatro endpoints — nenhuma mão no meio."""
    db = FakeDb(pipelines=_cadastro(), agora_banco=agora_banco)
    mc.limpar_cache()
    malhas_router.limpar_cache_tipicos()
    try:
        with _patch(db), patch("routers.malhas._agora", return_value=agora_api):
            corrida = monta(db, client)
            cid = corrida["id"] if corrida else None
            lista = client.get("/malhas")
            detalhe = client.get("/malhas/M1")
            execucao = client.get(
                "/malhas/M1/execucao" + (f"?corrida={cid}" if cid else ""))
            corridas = client.get("/malhas/M1/corridas")
            for r in (lista, detalhe, execucao, corridas):
                assert r.status_code == 200, r.text
            return {
                "malhas": lista.json(),
                "malha": detalhe.json(),
                "malha-execucao": execucao.json(),
                "malha-corridas": corridas.json(),
                "corrida": cid,
                "malha_name": "M1",
                "agora_ms": _epoch_ms(agora_api),
            }
    finally:
        mc.limpar_cache()
        malhas_router.limpar_cache_tipicos()


# ═══════════════════════ os cenários, um a um ═══════════════════════════════
#
# Cada função monta UM estado do mundo. Elas são o insumo dos dois bancos de
# prova (o painel e a lista), e nenhuma delas escreve payload: escrevem LINHAS
# de banco, que é o que existe às 3h.

def _posso_esperar(db, client):
    """A pergunta da Decisão 64 na forma literal do aceite.

    `CARGA_B` e `CARGA_D` têm 23 execuções de 18 min; `CARGA_E` tem **3** — e é
    ela que prova que o piso é duro. Os três estão rodando: 12 min, 41 min e
    3 min, contados do carimbo do BANCO."""
    _monta_malha(client, "M1", ["CARGA_B", "CARGA_D", "CARGA_E"])
    c = db.abrir_corrida("M1", odate=ODATE, aberta_em=ABERTURA,
                         membros=["CARGA_B", "CARGA_D", "CARGA_E"])
    db.historico("CARGA_B", 23, 18)
    db.historico("CARGA_D", 23, 18)
    db.historico("CARGA_E", 3, 7)
    db.execucao("CARGA_B", "EXECUTANDO", corrida=c["id"],
                inicio=AGORA_BANCO - timedelta(minutes=12))
    db.execucao("CARGA_D", "EXECUTANDO", corrida=c["id"],
                inicio=AGORA_BANCO - timedelta(minutes=41))
    db.execucao("CARGA_E", "EXECUTANDO", corrida=c["id"],
                inicio=AGORA_BANCO - timedelta(minutes=3))
    return c


def _tempo_e_nao_pipelines(db, client):
    """O cenário que a própria Decisão 56b descreve, montado no banco.

    Seis membros: cinco de 5 min já concluídos e um de **3h** que ainda não
    partiu. `5 de 6` é 83% dos PIPELINES e 12% do TRABALHO — e é 12 que o
    percentual diz."""
    membros = ["R1", "R2", "R3", "R4", "R5", "PESADO"]
    _monta_malha(client, "M1", membros)
    c = db.abrir_corrida("M1", odate=ODATE, aberta_em=ABERTURA, membros=membros)
    for nome in membros[:-1]:
        db.historico(nome, 8, 5)
        db.execucao(nome, "SUCESSO", corrida=c["id"],
                    inicio=ABERTURA + timedelta(minutes=1),
                    fim=ABERTURA + timedelta(minutes=6))
    db.historico("PESADO", 8, 180)
    return c


def _com_dispensados(db, client):
    """O sábado da malha que roda de segunda a sexta: 4 membros concluídos e 3
    dispensados pela regra do dia, todos com o MESMO tempo típico.

    Com os dispensados no denominador, o percentual empacava em 57% — e a faixa
    escrevia `4 de 7 · fechando · ≈ 57% do tempo típico` com a barra CHEIA: três
    números na mesma linha contando histórias diferentes. O tempo típico de
    quem não roda hoje não é trabalho de hoje."""
    membros = ["D1", "D2", "D3", "D4", "P1", "P2", "P3"]
    _monta_malha(client, "M1", membros)
    c = db.abrir_corrida("M1", odate=ODATE, aberta_em=ABERTURA, membros=membros)
    for nome in membros:
        db.historico(nome, 8, 10)
    for nome in membros[:4]:
        db.execucao(nome, "SUCESSO", corrida=c["id"],
                    inicio=ABERTURA + timedelta(minutes=1),
                    fim=ABERTURA + timedelta(minutes=11))
    for nome in membros[4:]:
        db.execucao(nome, "PULADO", corrida=c["id"],
                    inicio=ABERTURA + timedelta(minutes=1))
    return c


def _atrasada(db, client):
    """Limite de segurança vencido com trabalho vivo: a saúde vira `ATRASADA`,
    e é o ÚNICO estado em que o percentual passa de 100."""
    membros = ["CARGA_B", "CARGA_D"]
    _monta_malha(client, "M1", membros)
    c = db.abrir_corrida("M1", odate=ODATE, aberta_em=ABERTURA, membros=membros,
                         teto_horas=1)
    db.historico("CARGA_B", 23, 18)
    db.historico("CARGA_D", 23, 18)
    db.execucao("CARGA_B", "SUCESSO", corrida=c["id"],
                inicio=ABERTURA + timedelta(minutes=1),
                fim=ABERTURA + timedelta(minutes=19))
    db.execucao("CARGA_D", "EXECUTANDO", corrida=c["id"],
                inicio=AGORA_BANCO - timedelta(minutes=32))
    return c


def _terminal(db, client):
    """Corrida CONCLUÍDA, com histórico sobrando: o estado já diz tudo, e um
    `≈ 94%` ao lado de "concluída" só levantaria a dúvida dos 6%."""
    membros = ["CARGA_B", "CARGA_D"]
    _monta_malha(client, "M1", membros)
    c = db.abrir_corrida("M1", odate=ODATE, aberta_em=ABERTURA, membros=membros,
                         status="CONCLUIDA")
    c["fechada_em"] = ABERTURA + timedelta(hours=2, minutes=52)
    c["fechada_por"] = "no_fim:#9"
    for nome in membros:
        db.historico(nome, 23, 18)
        db.execucao(nome, "SUCESSO", corrida=c["id"],
                    inicio=ABERTURA + timedelta(minutes=1),
                    fim=ABERTURA + timedelta(minutes=19))
    return c


def _fechando(db, client):
    """Todos os membros concluídos e a corrida CONTINUA ABERTA (a carência de
    quiescência ainda corre).

    É o estado em que o numerador do percentual EMPATA com o denominador — e
    onde `100%` seria a palavra "pronto" dita por um número."""
    membros = ["CARGA_B", "CARGA_D"]
    _monta_malha(client, "M1", membros)
    c = db.abrir_corrida("M1", odate=ODATE, aberta_em=ABERTURA, membros=membros)
    for nome in membros:
        db.historico(nome, 23, 18)
        db.execucao(nome, "SUCESSO", corrida=c["id"],
                    inicio=ABERTURA + timedelta(minutes=1),
                    fim=ABERTURA + timedelta(minutes=19))
    return c


def _dia_1(db, client):
    """O dia do deploy: a primeira corrida da malha, e mais nada no banco.

    Nem corrida fechada (não há histórico), nem execução em
    `etl_job_execution` (não há duração típica). É o estado real antes do
    smoke da fase."""
    _monta_malha(client, "M1", ["CARGA_B", "CARGA_D"])
    return db.abrir_corrida("M1", odate=ODATE, aberta_em=ABERTURA,
                            membros=["CARGA_B", "CARGA_D"])


def _cancelada(db, client):
    """Encerrada na mão, com motivo — o item de auditoria da Decisão 67, e o
    que precisa ser explicável no fechamento do mês sem abrir o banco."""
    membros = ["CARGA_B", "CARGA_D"]
    _monta_malha(client, "M1", membros)
    c = db.abrir_corrida("M1", odate=ODATE, aberta_em=ABERTURA,
                         membros=membros, status="CANCELADA")
    c["fechada_em"] = datetime(2026, 8, 5, 5, 20)
    c["fechada_por"] = "manual:C123456"
    c["motivo"] = ("encerrada por C123456: carga do dia 03 remarcada para a "
                   "tarde")
    db.execucao("CARGA_B", "SUCESSO", corrida=c["id"],
                inicio=ABERTURA + timedelta(minutes=1),
                fim=ABERTURA + timedelta(minutes=19))
    return c


def _implicita(db, client):
    """As 3 de 4 malhas sem nó Início: o ODATE é "o que a primeira raiz achou",
    e a tela não pode apresentar isso com a autoridade de um agendamento."""
    membros = ["CARGA_C", "CARGA_D"]
    _monta_malha(client, "M1", membros)
    c = db.abrir_corrida("M1", odate=ODATE, aberta_em=ABERTURA, membros=membros)
    c["origem"] = "implicita"
    c["aberta_por"] = "implicita:CARGA_C"
    c["ancora_pipeline"] = "CARGA_C"
    db.execucao("CARGA_C", "EXECUTANDO", corrida=c["id"],
                inicio=AGORA_BANCO - timedelta(minutes=9))
    return c


def _teams_preso(db, client):
    """Webhook com 401 por URL rotacionada: a guardiã loga e segue, o evento
    fica sem carimbo, e a malha falha em silêncio para todo o plantão."""
    membros = ["CARGA_B", "CARGA_D"]
    _monta_malha(client, "M1", membros)
    db.canal_teams = True
    c = db.abrir_corrida("M1", odate=ODATE, aberta_em=ABERTURA, membros=membros)
    db.execucao("CARGA_B", "FALHA", corrida=c["id"],
                inicio=ABERTURA + timedelta(minutes=1),
                fim=ABERTURA + timedelta(minutes=7))
    db.execucao("CARGA_D", "EXECUTANDO", corrida=c["id"],
                inicio=AGORA_BANCO - timedelta(minutes=20))
    db.eventos.append({
        "pipeline_name": malhas_router.MARCADOR_CORRIDA.format(c["id"]),
        "data_referencia": ODATE, "tipo": "MALHA_FALHOU",
        "detectado_em": datetime(2026, 8, 5, 3, 7),
        "detalhe": "malha M1 falhou", "notificado_em": None})
    return c


def _fechada(db, malha, odate, status, *, aberta=None, fechada_por="guardia",
             motivo=None, tentativas=1, reaberta_por=None, membros=("CARGA_B",)):
    ab = aberta or datetime(odate.year, odate.month, odate.day, 1, 10)
    linha = db.abrir_corrida(malha, odate=odate, aberta_em=ab,
                             membros=list(membros), status=status)
    linha["fechada_em"] = ab + timedelta(hours=2, minutes=52)
    linha["fechada_por"] = fechada_por
    linha["motivo"] = motivo
    linha["tentativas"] = tentativas
    linha["reaberta_por"] = reaberta_por
    return linha


def _faixa_com_historico(db, client):
    """A faixa das últimas corridas com o que ela precisa para virar
    DIAGNÓSTICO — quatro madrugadas com quatro desfechos diferentes:

      • 01/08 `EXPIRADA` — ninguém falhou; `CARGA_A` **nunca chegou a
        iniciar**. É o caso em que "travou" só pode vir da ausência de linha;
      • 02/08 `CONCLUIDA` — limpa, e ela existe para provar que a faixa não
        inventa culpado;
      • 03/08 `FALHA` — `CARGA_A` falhou às 03:07;
      • 04/08 `CANCELADA` — encerrada à mão, reaberta uma vez, com motivo.

    E a corrente ABERTA em cima delas, com um membro que ainda não partiu: nos
    primeiros minutos isso é o estado normal, e não veredito."""
    membros = ["CARGA_A", "CARGA_B"]
    _monta_malha(client, "M1", membros)
    nunca = _fechada(db, "M1", date(2026, 8, 1), "EXPIRADA", membros=membros)
    db.execucao("CARGA_B", "SUCESSO", odate=date(2026, 8, 1),
                corrida=nunca["id"], inicio=datetime(2026, 8, 1, 1, 20),
                fim=datetime(2026, 8, 1, 2, 0))
    limpa = _fechada(db, "M1", date(2026, 8, 2), "CONCLUIDA", membros=membros)
    for p in membros:
        db.execucao(p, "SUCESSO", odate=date(2026, 8, 2), corrida=limpa["id"],
                    inicio=datetime(2026, 8, 2, 1, 20),
                    fim=datetime(2026, 8, 2, 3, 55))
    travada = _fechada(db, "M1", date(2026, 8, 3), "FALHA", membros=membros)
    db.execucao("CARGA_A", "FALHA", odate=date(2026, 8, 3),
                corrida=travada["id"], inicio=datetime(2026, 8, 3, 1, 20),
                fim=datetime(2026, 8, 3, 3, 7))
    db.execucao("CARGA_B", "SUCESSO", odate=date(2026, 8, 3),
                corrida=travada["id"], inicio=datetime(2026, 8, 3, 1, 20),
                fim=datetime(2026, 8, 3, 2, 0))
    encerrada = _fechada(
        db, "M1", date(2026, 8, 4), "CANCELADA", membros=membros,
        fechada_por="manual:C123456", tentativas=2, reaberta_por="manual:C999",
        motivo="encerrada por C123456: carga do dia 03 remarcada para a tarde")
    for p in membros:
        db.execucao(p, "SUCESSO", odate=date(2026, 8, 4),
                    corrida=encerrada["id"], inicio=datetime(2026, 8, 4, 1, 20),
                    fim=datetime(2026, 8, 4, 2, 0))
    c = db.abrir_corrida("M1", odate=ODATE, aberta_em=ABERTURA, membros=membros)
    db.execucao("CARGA_A", "EXECUTANDO", corrida=c["id"],
                inicio=AGORA_BANCO - timedelta(minutes=9))
    return c


def _historico_limpo(db, client):
    """Três madrugadas anteriores, todas concluídas — o histórico EXISTE e não
    tem notícia. É o contraponto do `falhou X das últimas Y`."""
    membros = ["CARGA_B"]
    _monta_malha(client, "M1", membros)
    for i in (3, 2, 1):
        _fechada(db, "M1", ODATE - timedelta(days=i), "CONCLUIDA",
                 membros=membros)
    c = db.abrir_corrida("M1", odate=ODATE, aberta_em=ABERTURA,
                         membros=membros)
    db.execucao("CARGA_B", "EXECUTANDO", corrida=c["id"],
                inicio=AGORA_BANCO - timedelta(minutes=9))
    return c


def _terca_atipica(db, client):
    """Alguém inativou os membros numa TERÇA: a corrida fecha `SEM_TRABALHO` e,
    sem histórico, o card fica cinza e mudo — indistinguível de um sábado."""
    membros = ["CARGA_B", "CARGA_D"]
    _monta_malha(client, "M1", membros)
    for semanas in range(4, 0, -1):
        dia = TERCA - timedelta(days=7 * semanas)
        _fechada(db, "M1", dia, "CONCLUIDA", membros=membros)
    hoje = db.abrir_corrida("M1", odate=TERCA,
                            aberta_em=datetime(2026, 8, 4, 1, 0),
                            membros=membros, status="SEM_TRABALHO")
    hoje["fechada_em"] = datetime(2026, 8, 4, 1, 2)
    for p in membros:
        db.execucao(p, "PULADO", odate=TERCA, corrida=hoje["id"],
                    inicio=datetime(2026, 8, 4, 1, 1),
                    fim=datetime(2026, 8, 4, 1, 1))
    return hoje


def _sabado_legitimo(db, client):
    """A MESMA malha, no sábado: os quatro sábados anteriores também não
    tiveram trabalho. Cinza e muda — alarme de sábado toda semana treina o
    operador a ignorar o alarme (Decisão 26)."""
    membros = ["CARGA_B", "CARGA_D"]
    _monta_malha(client, "M1", membros)
    for semanas in range(4, 0, -1):
        dia = SABADO - timedelta(days=7 * semanas)
        _fechada(db, "M1", dia, "SEM_TRABALHO", membros=membros)
    hoje = db.abrir_corrida("M1", odate=SABADO,
                            aberta_em=datetime(2026, 8, 8, 1, 0),
                            membros=membros, status="SEM_TRABALHO")
    hoje["fechada_em"] = datetime(2026, 8, 8, 1, 2)
    for p in membros:
        db.execucao(p, "PULADO", odate=SABADO, corrida=hoje["id"],
                    inicio=datetime(2026, 8, 8, 1, 1),
                    fim=datetime(2026, 8, 8, 1, 1))
    return hoje


def _falhou_2_de_7(db, client):
    """Sete madrugadas com trabalho, duas delas ruins — mais dois dias sem
    trabalho no meio, que NÃO podem entrar no denominador (não tiveram chance
    de falhar)."""
    membros = ["CARGA_B"]
    _monta_malha(client, "M1", membros)
    desfechos = ["CONCLUIDA", "FALHA", "CONCLUIDA", "SEM_TRABALHO",
                 "CONCLUIDA", "EXPIRADA", "SEM_TRABALHO", "CONCLUIDA",
                 "CONCLUIDA", "CONCLUIDA"]
    for i, status in enumerate(reversed(desfechos)):
        _fechada(db, "M1", ODATE - timedelta(days=i + 1), status,
                 membros=membros)
    c = db.abrir_corrida("M1", odate=ODATE, aberta_em=ABERTURA,
                         membros=membros)
    db.execucao("CARGA_B", "EXECUTANDO", corrida=c["id"],
                inicio=AGORA_BANCO - timedelta(minutes=9))
    return c


# ═══════════════════════ os dois bancos de prova ════════════════════════════

@pytest.fixture(scope="module")
def cenarios(client, auth_modulo) -> dict:
    """Todos os cenários, perguntados aos ENDPOINTS de verdade.

    Um dicionário `{nome: {payloads dos quatro endpoints}}`. É ele que
    alimenta as duas bancadas — e é a razão de nenhuma delas poder inventar
    campo: o que a tela recebe é o que o router emitiu."""
    return {
        "posso_esperar": _com_duble(client, _posso_esperar),
        "tempo_e_nao_pipelines": _com_duble(client, _tempo_e_nao_pipelines),
        "com_dispensados": _com_duble(client, _com_dispensados),
        "atrasada": _com_duble(client, _atrasada),
        "fechando": _com_duble(client, _fechando),
        "terminal": _com_duble(client, _terminal),
        "dia_1": _com_duble(client, _dia_1),
        "cancelada": _com_duble(client, _cancelada),
        "implicita": _com_duble(client, _implicita),
        "teams_preso": _com_duble(client, _teams_preso),
        "faixa_com_historico": _com_duble(client, _faixa_com_historico),
        "historico_limpo": _com_duble(client, _historico_limpo),
        "terca_atipica": _com_duble(client, _terca_atipica, agora_api=datetime(2026, 8, 4, 7, 0),
            agora_banco=datetime(2026, 8, 4, 10, 0)),
        "sabado_legitimo": _com_duble(client, _sabado_legitimo, agora_api=datetime(2026, 8, 8, 7, 0),
            agora_banco=datetime(2026, 8, 8, 10, 0)),
        "falhou_2_de_7": _com_duble(client, _falhou_2_de_7),
    }


# Qual aba cada cenário abre por CLIQUE. `Agora` é onde a duração típica
# aparece; nos demais o que se prova está na faixa, que não depende de aba.
_ABA = {"posso_esperar": "Agora", "implicita": "Agora"}


def _rodar(harness, entrada: dict) -> dict:
    node = _node()
    if node is None:
        pytest.skip(_MOTIVO_SALTO)
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(entrada, f, default=str)
        caminho = f.name
    try:
        r = subprocess.run([node, str(harness), caminho], capture_output=True,
                           text=True, cwd=str(RAIZ), timeout=300)
        assert r.returncode == 0, f"bancada falhou:\n{r.stderr}"
        return json.loads(r.stdout)
    finally:
        os.unlink(caminho)


@pytest.fixture(scope="module")
def painel(cenarios) -> dict:
    """O `MalhaEditor` RENDERIZADO, cenário a cenário, com o payload de verdade.

    Uma chamada de Node para todos: preparar a árvore de módulos é o caro, e
    repeti-la por teste transformaria a suíte num teste de transpilador."""
    entrada = {nome: dict(c, aba=_ABA.get(nome)) for nome, c in cenarios.items()}
    return _rodar(HARNESS_PAINEL, entrada)


@pytest.fixture(scope="module")
def lista(cenarios) -> dict:
    """A página `/malha` RENDERIZADA — o card, que é a superfície de varredura
    das 8h. Reusa a bancada da F9 sem tocá-la: o que muda é o payload."""
    entrada = {nome: {"payload": c["malhas"], "agora_ms": c["agora_ms"]}
               for nome, c in cenarios.items()}
    return _rodar(HARNESS_PAGINA, entrada)


def _cena(banco: dict, nome: str) -> dict:
    dado = banco[nome]
    assert "__erro__" not in dado, \
        f"{nome} levantou na bancada:\n{dado.get('__erro__')}"
    return dado


def _card(lista: dict, nome: str) -> dict:
    cena = _cena(lista, nome)
    assert not cena["erros"], f"componente levantou em {nome}: {cena['erros']}"
    cards = [c for c in cena["cards"] if c["malha"] == "M1"]
    assert len(cards) == 1, f"esperava 1 card de M1 em {nome}"
    return cards[0]


# ═════════════ ACEITE 1 — o dia 1: `n = 0` é ausência, nunca "0%" ═══════════

# Tudo o que esta fase escreve na tela. Nenhuma destas frases pode existir sem
# corrida fechada gravada — e a lista é a régua das provas de ausência.
_FRASES_DA_FASE = ("típico", "n=", "% do tempo típico", "falhou ",
                   "das últimas", "ciclo anterior", "tiveram trabalho",
                   "⚠ 2x")


def test_dia_1_o_painel_nao_renderiza_frase_nenhuma_desta_fase(painel):
    """*"histórico com **zero** corridas fechadas (dia 1) → nenhuma das frases
    desta fase é renderizada, e nada quebra"*.

    Antes do smoke da fase o histórico é literalmente ZERO. A varredura é sobre
    TUDO o que se lê — texto, `title` e `aria-*` —, porque é por `title` que um
    número escapa sem ninguém ver.

    ⚠️ O cenário tem corrida ABERTA e membros: o que falta é **passado**. Um
    teste que provasse isto com a tela vazia provaria outra coisa."""
    cena = _cena(painel, "dia_1")
    for frase in _FRASES_DA_FASE:
        assert frase not in cena["lido"], \
            f"a frase {frase!r} apareceu no dia 1:\n{cena['lido']}"


def test_dia_1_o_card_nao_renderiza_frase_nenhuma_desta_fase(lista):
    """A outra superfície do mesmo aceite. O card das 8h é onde `falhou 2 das
    últimas 7 corridas` moraria — e no dia 1 ele não tem o que dizer."""
    card = _card(lista, "dia_1")
    for frase in _FRASES_DA_FASE:
        assert frase not in card["lido"], \
            f"a frase {frase!r} apareceu no card do dia 1:\n{card['lido']}"


def test_dia_1_nada_quebra_a_tela_continua_contando_o_que_ja_contava(
        painel, lista, cenarios):
    """"…e **nada quebra**" é a outra metade do aceite, e é ela que separa
    "a frase não saiu" de "a tela morreu".

    A corrida continua sendo descrita: estado, `x de y`, denominador do
    snapshot e a barra com o `aria` de sempre — tudo o que a F9/F10/F11 já
    entregavam, byte a byte."""
    cena = _cena(painel, "dia_1")
    assert "em andamento" in cena["texto"]
    assert cena["linha_da_contagem"][0] == "0 de 2 pipelines concluídos"
    assert cena["barras"] and cena["barras"][0]["valuetext"]
    card = _card(lista, "dia_1")
    assert "em andamento" in card["texto"]
    assert "2 membros neste ciclo" in card["texto"]
    # E o servidor não publicou número sem amostra: a chave `historico` NÃO
    # existe (ausência), e `tipicos` veio apurado e VAZIO — que são coisas
    # diferentes e precisam continuar sendo.
    resposta = cenarios["dia_1"]["malha-execucao"]
    assert "historico" not in resposta
    assert resposta["tipicos"]["itens"] == []
    assert resposta["tipicos"]["completo"] is False


# ═════════ ACEITE 2 — `há 12 min · típico 18 min (n=23)`, e o piso duro ═════

def test_membro_com_23_execucoes_mostra_o_decorrido_o_tipico_e_o_n(painel):
    """*"membro com 23 execuções históricas → `há 12 min · típico 18 min
    (n=23)`"*.

    O aceite literal, renderizado: o decorrido sai dos DOIS carimbos do banco
    (`inicio` → `apurado_em`) somados ao relógio local, e o típico com o `n`
    ao lado saiu de `etl_job_execution` pelo endpoint de verdade."""
    linhas = {l["texto"].split(" ")[0]: l
              for l in _cena(painel, "posso_esperar")["linhas"]}
    assert "rodando há 12 min · típico 18 min (n=23)" in linhas["CARGA_B"]["texto"]


def test_membro_com_3_execucoes_mostra_SO_o_decorrido(painel):
    """*"membro com **3** execuções → **só** o decorrido, sem "típico" e sem
    `n` (o piso é duro, e o `n` nunca aparece sem o número ao lado)"*.

    O piso mora no `HAVING` do servidor: `CARGA_E` nem chega ao payload, e por
    isso não há como a tela publicar `(n=3)` ao lado de nada."""
    linha = next(l for l in _cena(painel, "posso_esperar")["linhas"]
                 if l["texto"].startswith("CARGA_E"))
    assert "rodando há 3 min" in linha["texto"]
    assert "típico" not in linha["texto"]
    assert "n=" not in linha["texto"]


def test_o_piso_duro_e_do_SERVIDOR_e_nao_da_tela(cenarios):
    """A mesma regra, do outro lado do fio: o membro com 3 execuções não vem no
    payload. Provar só na tela deixaria a porta aberta para o número atravessar
    a rede e ser escondido no CSS — e aí ele volta no primeiro `title`."""
    tipicos = cenarios["posso_esperar"]["malha-execucao"]["tipicos"]
    assert tipicos["piso_n"] == 5
    assert {i["pipeline"] for i in tipicos["itens"]} == {"CARGA_B", "CARGA_D"}
    assert all(i["n"] == 23 for i in tipicos["itens"])


# ═════════ ACEITE 3 — a marca `⚠ 2x`, e ela NÃO é alarme ═══════════════════

def test_membro_rodando_41_min_com_p50_de_18_ganha_a_marca_ambar(painel):
    """*"membro rodando há 41 min com `p50 = 18 min` → marca âmbar `⚠ 2x`"*.

    O múltiplo é TRUNCADO (41/18 = 2,3× diz `2x`): arredondar para cima diria
    `3x` de algo que ainda não é o triplo, ao lado de um relógio que o operador
    confere na mesma linha."""
    linhas = {l["texto"].split(" ")[0]: l
              for l in _cena(painel, "posso_esperar")["linhas"]}
    d = linhas["CARGA_D"]
    assert d["marca"] == "⚠ 2x"
    assert "rodando há 41 min · típico 18 min (n=23)" in d["texto"]
    # Âmbar, e com par claro+escuro (docs/ui-temas-cores.md).
    assert "amber-50" in d["marca_classe"] and "dark:" in d["marca_classe"]


def test_a_marca_nao_existe_para_quem_esta_dentro_do_tipico(painel):
    """O contraste que dá sentido à marca: `CARGA_B` roda há 12 min com o
    mesmo p50 de 18 e não ganha nada. Sem esta metade, "a marca aparece"
    poderia ser "a marca aparece sempre"."""
    linhas = {l["texto"].split(" ")[0]: l
              for l in _cena(painel, "posso_esperar")["linhas"]}
    assert linhas["CARGA_B"]["marca"] is None
    assert linhas["CARGA_E"]["marca"] is None


def test_a_marca_e_leitura_de_tela_e_nao_vira_evento(painel, cenarios):
    """*"e a marca **não** vira alarme no Teams (é leitura de tela, não
    evento)"*.

    Duas provas, porque a afirmação tem duas metades: o `title` da marca diz o
    que ela é — em português, sem prometer nada —, e o payload do ciclo NÃO
    ganhou evento nenhum por causa dela. Um alarme por "está demorando" tocaria
    toda madrugada, e alarme que toca sempre é alarme que ninguém lê."""
    d = next(l for l in _cena(painel, "posso_esperar")["linhas"]
             if l["texto"].startswith("CARGA_D"))
    assert "leitura de tela, não alarme" in d["marca_title"]
    resposta = cenarios["posso_esperar"]["malha-execucao"]
    assert resposta["eventos_corrida"] == []
    assert resposta["eventos"] == []


# ═════════ ACEITE 4 — nem ETA, nem previsão de conclusão ═══════════════════

_PROIBIDAS = ("ETA", "previsão", "previsto para", "estimativa", "estimado",
              "provavelmente", "tendência", "vai falhar", "vai atrasar",
              "deve terminar", "conclusão prevista")
# ⚠️ `previsto` SOZINHO fica de fora, e o motivo é um texto que a spec MANDA
# existir: `nada previsto` é o `SEM_TRABALHO` da Decisão 57 — ele fala do que
# não foi AGENDADO para hoje, não do que vai acontecer. Proibir a palavra crua
# tiraria da tela a frase do sábado legítimo para proteger o operador de uma
# promessa que ela não faz.

# ⚠️ A NEGAÇÃO é exceção declarada, e não brecha.
#
# O `title` do percentual diz, com todas as letras, *"não é previsão de
# conclusão"* — e essa frase é o oposto do defeito que a regra combate: ela
# existe para o operador NÃO ler o número como promessa. Uma proibição cega
# empurraria o código a APAGAR a única frase que protege quem lê, para ficar
# verde. O que se proíbe é AFIRMAR o futuro; dizer que não se afirma é a
# fronteira da Decisão 68 escrita na tela.
_NEGACAO = re.compile(r"(não|nunca|nem|sem)\s+(é|e|ser|vira|significa|"
                      r"promete|dá|da)?\s*$", re.IGNORECASE)


def _promessas(lido: str) -> list[str]:
    """As ocorrências AFIRMATIVAS de palavra de futuro no que a tela mostra."""
    achados = []
    for palavra in _PROIBIDAS:
        for m in re.finditer(rf"\b{re.escape(palavra)}\b", lido, re.IGNORECASE):
            antes = lido[max(0, m.start() - 40):m.start()]
            if not _NEGACAO.search(antes):
                achados.append(lido[max(0, m.start() - 60):m.end() + 40])
    return achados


def test_nenhum_texto_da_interface_chama_o_numero_de_ETA_ou_de_previsao(
        painel, lista):
    """*"o número de duração **não** é chamado de ETA nem de previsão de
    conclusão da corrida em nenhum texto da interface"*.

    A varredura é sobre o que a tela RENDERIZOU em todos os cenários — texto,
    `title` e `aria-*`, nas duas superfícies —, e não sobre o fonte: uma
    palavra proibida escondida num `title` que nenhum `grep` de literal alcança
    é exatamente o modo de falso verde que esta suíte existe para fechar.

    A fronteira é a da Decisão 68 vista do outro lado: somar durações típicas
    de membros não dá previsão de conclusão de uma corrida que roda em paralelo
    e com dependências."""
    for banco, rotulo in ((painel, "painel"), (lista, "lista")):
        for nome in banco:
            promessas = _promessas(_cena(banco, nome)["lido"])
            assert not promessas, \
                f"promessa de futuro no {rotulo} de {nome}: {promessas}"


def test_a_regua_das_palavras_proibidas_nao_e_cega(painel):
    """A régua acima só vale se ela souber a diferença entre AFIRMAR e NEGAR.

    Este teste prova as duas metades do detector com o texto de verdade: a
    frase que a tela escreve (*"não é previsão de conclusão"*) passa, e a
    mesma frase sem o "não" reprova. Sem isto, um detector que aceitasse tudo
    ficaria verde para sempre e a proteção seria decorativa."""
    lido = _cena(painel, "tempo_e_nao_pipelines")["lido"]
    assert "não é previsão de conclusão" in lido, \
        "o cenário deixou de exercitar a frase que a exceção existe para aceitar"
    assert _promessas(lido) == []
    assert _promessas(lido.replace("não é previsão", "é previsão"))


# ═════════ ACEITE 5 — `SEM_TRABALHO`: a terça âmbar × o sábado mudo ════════

# As duas pílulas em disputa, copiadas de `malhas/statusExecucao.ts`
# (`CHIP_AMBAR` e `CHIP_SLATE`). A régua é a CLASSE INTEIRA, e não a palavra
# "amber": o card já tem âmbar em outros lugares (a criticidade `MEDIA`, por
# exemplo), e procurar a cor solta acharia o vizinho e não a pílula.
_CHIP_AMBAR = ("bg-amber-50 text-amber-700 border-amber-300 "
               "dark:bg-amber-900/30 dark:text-amber-300 dark:border-amber-800")
_CHIP_SLATE = ("bg-slate-100 text-slate-600 border-slate-300 "
               "dark:bg-slate-800 dark:text-slate-300 dark:border-slate-600")


def test_terca_sem_trabalho_depois_de_4_tercas_com_trabalho_fica_AMBAR(lista):
    """*"malha que rodou nas últimas 4 terças e hoje (terça) sai `SEM_TRABALHO`
    → card **âmbar** com "as últimas 4 terças tiveram trabalho""*.

    É o único jeito de a tela pegar membros inativados por engano: sem isto o
    card fica cinza e mudo, indistinguível de um sábado legítimo.

    Cor **e** palavra, as duas: cor nunca é canal único (Decisão 59), e um
    âmbar sem a frase seria um alarme sem causa."""
    card = _card(lista, "terca_atipica")
    assert "sem trabalho hoje" in card["texto"]
    assert "as últimas 4 terças tiveram trabalho" in card["texto"]
    assert _CHIP_AMBAR in card["classes"]
    assert _CHIP_SLATE not in card["classes"]


def test_no_sabado_a_MESMA_malha_continua_cinza_e_muda(lista):
    """*"no sábado, a mesma malha continua **cinza e muda**"*.

    A metade que importa: um alarme de sábado toda semana treina o operador a
    ignorar o alarme (Decisão 26) — e aí ele ignora também a terça, que era a
    única que interessava. O contraste é com o teste acima, e o cenário é a
    MESMA malha no MESMO estado (`SEM_TRABALHO`); o que muda é o DIA."""
    card = _card(lista, "sabado_legitimo")
    assert "sem trabalho hoje" in card["texto"]
    assert "tiveram trabalho" not in card["lido"]
    assert _CHIP_SLATE in card["classes"]
    assert _CHIP_AMBAR not in card["classes"]


def test_o_sem_trabalho_atipico_continua_sem_barra(lista):
    """Decisão 57 continua valendo por cima da Decisão 68: o que muda é a COR,
    não o desenho. Uma barra em 0% num dia atípico leria "falhou tudo", que é
    outra coisa — e a barra só volta quando houver trabalho a medir."""
    assert _card(lista, "terca_atipica")["barra"] is None
    assert _card(lista, "sabado_legitimo")["barra"] is None


# ═════════ ACEITE 6 — `CANCELADA`: quem encerrou, quando e por quê ═════════

def test_cancelada_o_card_diz_quem_encerrou_quando_e_o_motivo(lista):
    """*"corrida `CANCELADA` → card e faixa dizem `encerrada por C123456 às
    05:20 — motivo: "…"`"*.

    Sem isto, fechar o mês com três corridas canceladas e não conseguir
    explicar nenhuma **sem abrir o banco** (Decisão 67)."""
    card = _card(lista, "cancelada")
    assert "encerrada por C123456 às 05:20" in card["texto"]
    assert 'motivo: "carga do dia 03 remarcada para a tarde"' in card["texto"]
    # O prefixo que o servidor compõe (`encerrada por C123456: …`) não aparece
    # duas vezes: quem e quando já saem na linha estruturada acima.
    assert card["texto"].count("C123456") == 1


def test_cancelada_a_faixa_do_painel_diz_o_mesmo(painel):
    """A mesma auditoria na outra superfície. Card e faixa discordando sobre a
    mesma corrida é o defeito que a camada inteira existe para não cometer."""
    texto = _cena(painel, "cancelada")["texto"]
    assert "encerrada por C123456 às 05:20" in texto
    assert 'motivo: "carga do dia 03 remarcada para a tarde"' in texto


def test_a_lista_de_corridas_traz_a_coluna_da_auditoria(cenarios):
    """*"…e a lista de `GET /corridas` traz a coluna"*.

    `reaberta_por` morava só no payload do card: a lista dizia "reaberta 1x"
    sem dizer POR QUEM — meia auditoria, que na hora de explicar não vale mais
    que nenhuma."""
    corridas = cenarios["faixa_com_historico"]["malha-corridas"]["corridas"]
    encerrada = next(c for c in corridas if c["status"] == "CANCELADA")
    assert encerrada["fechada_por"] == "manual:C123456"
    assert encerrada["motivo"].endswith("remarcada para a tarde")
    assert encerrada["reaberta_por"] == "manual:C999"
    assert encerrada["tentativas"] == 2


def test_a_auditoria_chega_ao_title_do_bloco_da_faixa(painel):
    """A terceira superfície da Decisão 67: o `title` de cada bloco da faixa.

    É o que transforma dez quadradinhos coloridos em diagnóstico — e é onde a
    corrida encerrada à mão precisa se explicar, porque ali ela é só um
    retângulo âmbar."""
    blocos = _cena(painel, "faixa_com_historico")["blocos"]
    encerrado = [b for b in blocos
                 if b["title"] and "encerrada por C123456" in b["title"]]
    assert len(encerrado) == 1, [b["title"] for b in blocos]
    titulo = encerrado[0]["title"]
    assert 'motivo: "carga do dia 03 remarcada para a tarde"' in titulo
    assert "reaberta 1x por C999" in titulo


def test_o_bloco_da_faixa_nomeia_QUEM_TRAVOU_a_madrugada(painel):
    """*"`title` dos blocos da faixa com o membro que travou"* (Decisão 68).

    Três madrugadas seguidas travando no MESMO membro é problema crônico e
    espera o horário comercial; nove verdes e uma vermelha é novidade e
    escala. Sem o nome, a faixa responde "foi ruim" e para aí."""
    porDia = {re.search(r"\d{2}/\d{2}", b["title"]).group(0): b["title"]
              for b in _cena(painel, "faixa_com_historico")["blocos"]}
    assert "travou: CARGA_A" in porDia["03/08"]
    # E a madrugada LIMPA não inventa culpado: `null` no payload é "apurei e
    # ninguém travou", e a faixa cala.
    assert "travou:" not in porDia["02/08"]


def test_o_bloco_nomeia_tambem_quem_NUNCA_CHEGOU_A_INICIAR(painel, cenarios):
    """A madrugada em que **ninguém falhou** e mesmo assim nada terminou.

    `01/08` expirou com `CARGA_B` concluído e `CARGA_A` sem uma única linha em
    `etl_pipeline_execucao`: a DAG não partiu. Numa corrida FECHADA isso deixou
    de ser "o estado normal dos primeiros segundos" e virou VEREDITO — é o nome
    que o operador procura de manhã, e é o único caminho para ele.

    ⚠️ Este é o caso que só existe pela AUSÊNCIA de linha: a classe
    `nao_partiu` nunca é atribuída pelo agregado, ela nasce de `classe is None`.
    Sem essa normalização o payload sairia com `travou: null` — que a faixa lê
    como "apurei e ninguém travou", uma noite limpa afirmada sobre a noite em
    que nada rodou."""
    porDia = {re.search(r"\d{2}/\d{2}", b["title"]).group(0): b["title"]
              for b in _cena(painel, "faixa_com_historico")["blocos"]}
    assert "travou: CARGA_A" in porDia["01/08"]
    expirada = next(c for c in cenarios["faixa_com_historico"]["malha-corridas"]
                    ["corridas"] if c["status"] == "EXPIRADA")
    assert expirada["travou"] == {"pipeline": "CARGA_A", "classe": "nao_partiu"}


def test_a_corrida_ABERTA_nao_acusa_quem_ainda_nao_partiu(painel, cenarios):
    """O contrapeso, e ele é o que impede a correção acima de virar alarme
    falso diário.

    A corrida corrente abriu há minutos com `CARGA_B` ainda sem linha. Numa
    corrida em voo isso é o estado NORMAL — toda malha nasce assim —, e nomear
    culpado ali acusaria todas as noites, em todas as malhas, sobre ciclos
    perfeitamente saudáveis. É a mesma razão pela qual `nao_partiu` não ganha
    chip vermelho no card."""
    porDia = {re.search(r"\d{2}/\d{2}", b["title"]).group(0): b["title"]
              for b in _cena(painel, "faixa_com_historico")["blocos"]}
    assert "travou:" not in porDia["05/08"]
    corrente = next(c for c in cenarios["faixa_com_historico"]["malha-corridas"]
                    ["corridas"] if c["status"] == "ABERTA")
    assert corrente["travou"] is None
    # E a informação não sumiu: o painel continua dizendo quem não partiu, com
    # a palavra certa. O que não existe é o VEREDITO.
    pendentes = cenarios["faixa_com_historico"]["malha-execucao"]["corrida"][
        "pendentes"]
    assert [(p["pipeline"], p["classe"]) for p in pendentes] == \
        [("CARGA_B", "nao_partiu")]


# ═════════ ACEITE 7 — `origem = implicita`: o ODATE sem autoridade ═════════

def test_origem_implicita_o_card_diz_sem_no_inicio(lista):
    """*"malha `origem = implicita` → o card diz `sem nó Início`"* (Decisão 44).

    Nas 3 de 4 malhas sem Início o ODATE é "o que a primeira raiz achou", e na
    lista essa corrida é hoje indistinguível de uma agendada."""
    card = _card(lista, "implicita")
    assert "sem nó Início" in card["texto"]


def test_origem_implicita_a_faixa_diz_de_qual_RAIZ_veio_a_data(painel):
    """*"…e a faixa diz de qual raiz veio a data de referência"*.

    O card diz que não houve agendamento; a faixa nomeia quem carimbou o dia.
    São duas informações diferentes, e a segunda é a que permite ir conferir."""
    texto = _cena(painel, "implicita")["texto"]
    assert "data de referência definida pela primeira raiz a partir" in texto
    assert "CARGA_C" in texto


def test_a_corrida_agendada_nao_ganha_nenhuma_dessas_linhas(lista, painel):
    """O contraste. `origem = 'inicio'` é o caso normal e fica MUDO: uma linha
    em todo card para dizer "abriu como sempre abre" é ruído em 40 cards — e
    seria uma frase desta fase aparecendo onde ela não tem o que dizer."""
    assert "sem nó Início" not in _card(lista, "posso_esperar")["lido"]
    assert "primeira raiz a partir" not in _cena(painel, "posso_esperar")["lido"]


# ═════════ ACEITE 8 — o webhook com 401: banner VERMELHO na faixa ══════════

def test_aviso_preso_na_fila_do_teams_vira_banner_VERMELHO_na_faixa(painel):
    """*"webhook do Teams com 401 → banner **vermelho** na faixa, `aviso ao
    Teams na fila desde 03:07`, e não uma linha escondida numa aba"*.

    É o pior cenário de plantão: a guardiã loga o 401 e segue, a malha falha em
    silêncio para todo mundo, e o operador com esta tela aberta é o único que
    pode saber.

    Três asserções, porque a frase tem três partes: o TOM (vermelho, não
    âmbar), o TEXTO com a hora, e o LUGAR — o banner é irmão da faixa e está na
    tela ANTES de qualquer clique em aba (nenhuma aba foi clicada neste
    cenário)."""
    cena = _cena(painel, "teams_preso")
    assert cena["aba_clicada"] is None
    vermelhos = [b for b in cena["banners"] if b["tom"] == "erro"]
    assert len(vermelhos) == 1, cena["banners"]
    assert "aviso ao Teams na fila desde 03:07" in vermelhos[0]["texto"]
    assert "ninguém foi avisado ainda" in vermelhos[0]["texto"]


def test_sem_aviso_preso_o_banner_vermelho_nao_existe(painel):
    """O contraponto que impede o banner de virar decoração permanente: a
    corrida saudável do mesmo relógio não tem banner de erro nenhum. Um alarme
    que acende sempre é o alarme que a Decisão 26 proíbe."""
    assert [b for b in _cena(painel, "posso_esperar")["banners"]
            if b["tom"] == "erro"] == []


# ═════════ ACEITE 9 — o percentual da Decisão 56b: TEMPO, nunca contagem ═══

def test_o_percentual_mede_TEMPO_e_nao_contagem_de_pipelines(painel):
    """O argumento inteiro da Decisão 56b, montado no banco: cinco pipelines de
    5 min já concluídos e um de **3 h** que nem partiu.

    `5 de 6` é 83% dos PIPELINES e 12% do TRABALHO. O percentual diz **12**,
    que é a verdade — e é a diferença entre o operador ir dormir e não ir."""
    cena = _cena(painel, "tempo_e_nao_pipelines")
    assert cena["linha_da_contagem"][0] == "5 de 6 pipelines concluídos"
    assert "≈ 12% do tempo típico" in cena["texto"]
    assert "83" not in cena["lido"]


def test_membro_DISPENSADO_sai_do_denominador_do_tempo(painel):
    """O tempo típico de quem não roda hoje não é trabalho de hoje.

    Com os dispensados dentro, uma corrida de 7 com 3 dispensados NUNCA passava
    de 57%: a faixa escrevia `4 de 7 · fechando · ≈ 57% do tempo típico` com a
    barra CHEIA — três números na mesma linha contando histórias diferentes, na
    fase cujo trabalho é justamente fazer o número dizer a verdade.

    ⚠️ É deliberadamente DIFERENTE do denominador da contagem, que não encolhe
    (Decisão 52): lá o motivo é o progresso não poder andar para trás quando a
    guardiã marca `PULADO` num ciclo seguinte. Aqui o número é secundário, traz
    `≈`, e a expectativa de trabalho diminuiu de verdade — encolher é o que o
    torna verdadeiro."""
    cena = _cena(painel, "com_dispensados")
    assert cena["linha_da_contagem"][0].startswith("4 de 7")
    # 57% era o número velho: 4 de 7 fatias iguais, com os dispensados no
    # denominador. O trabalho de HOJE eram 4 membros, e os 4 terminaram.
    assert "≈ 57% do tempo típico" not in cena["texto"], \
        "os dispensados voltaram ao denominador — o número não pode subir"


def test_o_percentual_e_sempre_o_SEGUNDO_numero_da_faixa(painel):
    """*"Ele nunca substitui o `x de y`, que continua sendo o número primário e
    o primeiro a ser lido. O percentual é o SEGUNDO"*.

    A ordem é a do DOM — que é a ordem em que o leitor de tela anuncia —, e não
    a do CSS. Por isso a régua é a sequência dos pedaços da linha, e não a
    presença deles."""
    pedacos = _cena(painel, "tempo_e_nao_pipelines")["linha_da_contagem"]
    assert pedacos[0] == "5 de 6 pipelines concluídos"
    assert pedacos[1] == "· ≈ 12% do tempo típico"


def test_o_prefixo_e_o_sufixo_sao_parte_do_dado(painel):
    """*"Prefixo `≈` e sufixo `do tempo típico`, sempre. Nunca `60%` solto,
    nunca "concluído""*.

    O `≈` remove a promessa de precisão que um número daria a uma mediana; o
    sufixo diz de que grandeza se está falando. Um `12%` sozinho seria o
    percentual de contagem de volta, com minutos por baixo e a mesma leitura
    errada por cima."""
    texto = _cena(painel, "tempo_e_nao_pipelines")["texto"]
    assert "≈ 12% do tempo típico" in texto
    assert not re.search(r"(?<!≈ )\b12% (?!do tempo típico)", texto)
    assert "% concluído" not in texto


def test_faltando_amostra_em_UM_membro_o_percentual_some_por_completo(painel):
    """*"Só aparece com `n ≥ 5` em TODOS os membros do snapshot. Faltando
    histórico em um só, o percentual some (não é estimado, não é "aproximado
    com ressalva")"*.

    O cenário é o `posso_esperar`: `CARGA_E` tem 3 execuções. O percentual
    inteiro deixa de existir — e o que FICA é o `x de y` e a duração típica dos
    outros dois, que continuam medidos."""
    cena = _cena(painel, "posso_esperar")
    assert "do tempo típico" not in cena["lido"]
    assert "%" not in cena["lido"]
    assert cena["linha_da_contagem"][0] == "0 de 3 pipelines concluídos"
    assert "típico 18 min (n=23)" in cena["texto"]


def test_corrida_terminal_nao_tem_percentual_nenhum(painel):
    """*"…e **sem percentual nenhum** em corrida terminal: lá o estado já diz
    tudo"*.

    Um `≈ 94%` ao lado de "concluída" só levantaria a dúvida de onde foram
    parar os 6% — e a corrida acabou."""
    cena = _cena(painel, "terminal")
    assert "concluído" in cena["texto"]
    assert "do tempo típico" not in cena["lido"]
    assert "%" not in cena["lido"]


def test_corrida_ATRASADA_passa_de_100_e_nao_e_truncada(painel):
    """*"Corrida `ATRASADA` mostra o percentual mesmo passando de 100% do
    típico — aí ele vira `≈ 140% do tempo típico`, que é exatamente o sinal de
    atraso, e **não** é truncado em 100: truncar esconderia o que o operador
    precisa ver"*.

    O cenário: limite vencido, um membro concluído em 18 min e outro rodando há
    32 — 50 minutos sobre um típico de 36."""
    cena = _cena(painel, "atrasada")
    assert "fora do prazo" in cena["texto"]
    assert "≈ 138% do tempo típico" in cena["texto"]


def test_o_teto_e_99_enquanto_a_corrida_nao_terminou(painel):
    """*"`Math.floor`, teto em 99 enquanto a corrida não for terminal"*.

    O cenário é o do `fechando`: os dois membros já concluíram, o numerador
    empata com o denominador — e a corrida CONTINUA `ABERTA`, esperando a
    quiescência. `100%` aqui seria a palavra "pronto" dita por um número, sobre
    um ciclo que ainda pode receber um rerun; é o arredondamento `99,6 → 100`
    que a Decisão 56(i) denuncia, chegando pelo caminho exato."""
    cena = _cena(painel, "fechando")
    assert "≈ 99% do tempo típico" in cena["texto"]
    assert "100%" not in cena["lido"]
    # E o estado continua sendo o honesto: barra cheia NÃO é "concluída".
    assert "em andamento" in cena["texto"]
    assert "concluída" not in cena["texto"]


def test_a_barra_nunca_anuncia_percentual_de_CONTAGEM(painel):
    """A Decisão 56 não volta pela porta da acessibilidade.

    `role="progressbar"` com `aria-valuenow=4` e `aria-valuemax=7` faz o leitor
    de tela calcular e anunciar **"57%"** sozinho — o percentual de CONTAGEM,
    que mede a coisa errada. Por isso a barra carrega `aria-valuetext`, e ele
    é `x de y` em pipelines, sem "%", em TODOS os cenários."""
    for nome in painel:
        for barra in _cena(painel, nome)["barras"]:
            assert barra["valuetext"], f"barra sem aria-valuetext em {nome}"
            assert "%" not in barra["valuetext"], nome
            assert "%" not in (barra["label"] or ""), nome


def test_o_card_da_lista_nao_recebe_o_segundo_numero(lista):
    """*"O percentual … some antes dele em qualquer aperto de espaço (card
    estreito, mobile)"*.

    No card cabe um número só, e o que fica é o primário. O cenário é o mesmo
    em que a faixa MOSTRA o percentual — é isso que torna a ausência aqui uma
    decisão, e não um acidente de dado faltando."""
    card = _card(lista, "tempo_e_nao_pipelines")
    assert "5 de 6" in card["texto"]
    assert "%" not in card["lido"]
    assert "tempo típico" not in card["lido"]


def test_nenhuma_superficie_publica_percentual_de_CONTAGEM(painel, lista):
    """A varredura final da Decisão 56, nas duas telas e em todos os cenários:
    **não existe `%` de pipelines em superfície nenhuma**, `title` e `aria-*`
    incluídos.

    O único `%` tolerado é o do TEMPO, e ele é reconhecível pelo sufixo. Um
    `%` sem "do tempo típico" ao lado é, por construção, o percentual de
    contagem — que é o que esta regra proíbe."""
    for banco, rotulo in ((painel, "painel"), (lista, "lista")):
        for nome in banco:
            lido = _cena(banco, nome)["lido"]
            for m in re.finditer("%", lido):
                depois = lido[m.end():m.end() + len(" do tempo típico")]
                assert depois == " do tempo típico", \
                    f"'%' sem lastro de TEMPO no {rotulo} de {nome}: " \
                    f"{lido[max(0, m.start() - 60):m.end() + 30]!r}"


# ═════════ ACEITE 10 — o histórico factual do card e da faixa ══════════════

def test_o_card_conta_as_falhas_com_o_denominador_do_SERVIDOR(lista, cenarios):
    """`falhou 2 dos últimos 7 ciclos` — a frase que responde "está pior que
    antes?" sem obrigar o gestor a abrir malha por malha às 8h.

    O denominador vem PRONTO do servidor: a malha tem dois dias `SEM_TRABALHO`
    no meio, e eles não entram (não tiveram chance de falhar). Uma tela que
    deduzisse "das últimas 7" da janela pedida diria 7 sobre 5 madrugadas."""
    card = _card(lista, "falhou_2_de_7")
    assert "falhou 2 dos últimos 7 ciclos" in card["texto"]
    historico = next(m for m in cenarios["falhou_2_de_7"]["malhas"]["malhas"]
                     if m["malha_name"] == "M1")["historico"]
    assert historico["consideradas"] == 7 and historico["falhou"] == 2


def test_a_faixa_diz_o_que_aconteceu_na_corrida_ANTERIOR(painel):
    """`corrida anterior: 04/08 · encerrada por C123456 · 01:10 → 04:02` — a
    resposta mais direta a "está pior que ontem?".

    Ela exige `n = 1`, e não o piso `n ≥ 5` da duração típica: isto é FATO
    registrado, não mediana."""
    texto = _cena(painel, "faixa_com_historico")["texto"]
    assert "ciclo anterior: 04/08" in texto
    assert "01:10 → 04:02" in texto


def test_o_historico_se_cala_quando_nao_tem_noticia(lista, cenarios):
    """Zero falhas no período não vira "falhou 0 das últimas 3 corridas": uma
    linha em 40 cards para dizer que está tudo como sempre esteve é ruído, e o
    card já diz o estado da corrente. O histórico só fala quando tem notícia.

    ⚠️ O cenário tem histórico DE VERDADE (três corridas fechadas): o que falta
    é NOTÍCIA. Provar isto com uma malha sem histórico provaria o dia 1 outra
    vez, e o silêncio viria da razão errada."""
    historico = next(m for m in cenarios["historico_limpo"]["malhas"]["malhas"]
                     if m["malha_name"] == "M1")["historico"]
    assert historico["consideradas"] == 3 and historico["falhou"] == 0
    card = _card(lista, "historico_limpo")
    assert "falhou" not in card["lido"]
    assert "das últimas" not in card["lido"]


# ═════════ a honestidade da bancada ════════════════════════════════════════

def test_a_bancada_nao_inventa_campo_que_o_servidor_nao_manda(painel, cenarios):
    """A trava contra o modo de falso verde da F8.

    A bancada do front recebe o payload do router **inteiro e literal** — não
    há objeto escrito à mão em lugar nenhum desta suíte. Este teste fixa isso:
    as chaves que a tela consultou são exatamente os três endpoints, e o bloco
    `tipicos` que ela leu é o mesmo objeto que o `GET /execucao` devolveu.

    Sem ele, alguém poderia "consertar" um cenário vermelho acrescentando um
    campo na entrada da bancada — e a suíte voltaria ao verde descrevendo uma
    API que não existe."""
    cena = _cena(painel, "posso_esperar")
    consultadas = {c[0] for c in cena["chaves"]}
    assert consultadas == {"malha", "malha-execucao", "malha-corridas"}
    entrada = cenarios["posso_esperar"]["malha-execucao"]
    assert set(entrada["tipicos"]) == {
        "piso_n", "janela_dias", "limite_execucoes", "membros",
        "com_historico", "completo", "itens"}


def test_todo_cenario_renderiza_sem_excecao_nas_duas_telas(painel, lista):
    """"…e nada quebra" vale para a fase inteira, não só para o dia 1.

    Um componente que levanta vira DADO nas duas bancadas (nó `erro:` na
    lista, `__erro__` no painel) justamente para que a exceção seja um teste
    vermelho — e não um cenário que desaparece da saída."""
    for nome in painel:
        _cena(painel, nome)
    for nome in lista:
        assert not _cena(lista, nome)["erros"], nome
