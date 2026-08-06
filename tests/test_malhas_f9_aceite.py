"""
F9 da spec `docs/spec-malha-execucao.md` — a SUÍTE DE ACEITE, bullet a bullet.

Cada teste deste arquivo é um item da lista de aceite da §10/F9, e leva o nome
do que ele prova. O que ele NÃO é: uma segunda cópia de
`test_malhas_f9_card.py` (as derivações puras) nem de `test_ui_base_f9.py` (os
componentes de base). A diferença está em duas escolhas, e as duas existem por
causa de defeitos que esta spec já pagou:

── 1. O cenário é o PAYLOAD DA API DE VERDADE ───────────────────────────────
Nenhum objeto de corrida é escrito à mão aqui. Cada cenário é montado no dublê
do servidor (o mesmo de `test_malhas_f4_card.py` / `test_malhas_f9_nao_abriu.py`),
perguntado por `GET /malhas` e serializado para a bancada do front tal como
saiu do router.

O defeito que isto trava é o da F8 — **dublê que fabrica um dado que o servidor
real nunca produz**. Um `{"quiescencia_ate": "…"}` escrito no teste casa com o
componente porque a mesma pessoa escreveu os dois; se a API mandar o campo com
outro nome (ou parar de mandá-lo), o card cala a frase de fechamento e a suíte
de componente continua verde. Aqui ela fica vermelha, porque o `%s` que alimenta
a tela é o que o servidor emitiu.

── 2. A prova é de COMPORTAMENTO, não de mensagem ───────────────────────────
O defeito da F7 — **teste que afirma a mensagem e não o comportamento** — é o
modo de falso verde mais provável desta fase, porque metade do aceite é texto.
Por isso:

  • "`Acompanhar` existe e funciona" não é `grep` no fonte: a bancada acha o
    botão na árvore RENDERIZADA, chama o `onClick` dele e lê o parâmetro de URL
    que saiu; e a mesma página, reaberta com aquele parâmetro, é conferida no
    que o `MalhaEditor` RECEBE. Um botão decorativo falha aqui;
  • "não abriu ordena primeiro" não é a expressão do `sort`: é a ORDEM em que
    os cards saíram da renderização, com um cenário em que a ordem alfabética é
    a oposta da ordem correta;
  • "nenhuma barra" é a ausência do nó com `role="progressbar"` na árvore — uma
    barra com `total = 0` passa por qualquer teste de string;
  • as provas de ausência varrem a PÁGINA inteira: texto, `title` e todo
    `aria-*` (é por `aria-valuetext` que o percentual entraria sem ninguém ver).

⚠️ **Nada toca o banco**: o servidor é dublê e o front roda no Node. O único
requisito de ambiente é `node ≥ 18` com `ui-react/node_modules` instalado —
sem ele a suíte SALTA (visível no `-rs`), nunca passa em silêncio.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()
os.environ.setdefault("MSSQL_CONN_STR", "__mock__")
from api.main import app as _app  # noqa: F401  (ordem de import)

from deps import PERM_EDITAR, PERM_EXECUTAR, get_current_user
from services import malha_corrida as mc
from tests.test_malha_corrida_porta import AGORA_API
from tests.test_malhas_f4_card import _patch, _patch_agora
from tests.test_malhas_f9_nao_abriu import FakeDb
from tests.test_malhas_f10 import _monta_malha

RAIZ = Path(__file__).resolve().parents[1]
HARNESS = RAIZ / "tests" / "js" / "f9_pagina_harness.cjs"
SRC = RAIZ / "ui-react" / "src"
SUCRASE = RAIZ / "ui-react" / "node_modules" / "sucrase"

_MOTIVO_SALTO = ("front não instalado nesta máquina (node ≥ 18 ou "
                 "ui-react/node_modules/sucrase ausente)")
_MAJOR_MINIMO = 18

ODATE = date(2026, 8, 5)          # quarta-feira
ONTEM = date(2026, 8, 4)
SABADO = date(2026, 8, 8)
# O relógio LOCAL da bancada do front. Vale um valor fixo qualquer: o frescor e
# o decorrido são o relógio local CONSIGO MESMO (Decisão 60), e o que a tela
# escreve depende da DIFERENÇA `agora − respostaEm`, que aqui é zero.
AGORA_LOCAL_MS = 1_754_390_000_000

# Todos os pipelines dos cenários. O agendamento é **diário 01:00** — o horário
# da spec, e o que faz `AGORA_API` (07:00) já tê-lo vencido.
_NOMES = ["A", "B", "C", "D", "E", "F", "G", "H"]


def _pipes(**over):
    base = {"active": 1, "criticidade": "Media", "depends_on": None,
            "scheduled_time": "01:00:00", "schedule_type": "daily",
            "schedule_hour": 1, "schedule_minute": 0, "schedule_dow": 1,
            "schedule_dom": 1, "horarios_especificos": None,
            "dias_semana": None, "dias_horarios_mes": None,
            "somente_dias_uteis": 0, "calendario_nome": None,
            "hora_virada": None, "agenda_no": None, "dag_criada": 1}
    base.update(over)
    return {nome: dict(base) for nome in _NOMES}


# ═══════════════════════ o servidor: cenário por cenário ═════════════════════
#
# Convenção de relógio, e ela é o ponto do arquivo: o dublê põe o BANCO 3 h à
# frente do processo da API (10:00 × 07:00) — o desvio MEDIDO no dev. Todo
# carimbo escrito aqui (`aberta_em`, `inicio`, `fim`) está na régua do BANCO,
# porque é o banco que os carimba em produção. Uma corrida que abriu 01:10 na
# hora local é `04:10` aqui.

def _payload(client, monta, *, agora_api=AGORA_API, agora_banco=None,
             com_085=True, pipes=None):
    """Monta o cenário no dublê e devolve `GET /malhas` como o front o receberia."""
    db = FakeDb(pipelines=pipes or _pipes(), com_085=com_085,
                agora_banco=agora_banco or (agora_api + timedelta(hours=3)))
    mc.limpar_cache()
    try:
        with _patch(db), patch("routers.malhas._agora", return_value=agora_api):
            monta(db, client)
            resp = client.get("/malhas")
            assert resp.status_code == 200, resp.text
            return resp.json()
    finally:
        mc.limpar_cache()


def _sabado_sem_trabalho(db, client):
    """Sábado legítimo: os 3 membros não rodam hoje, e a corrida fecha
    `SEM_TRABALHO` — o estado em que a barra não pode existir."""
    _monta_malha(client, "M1", ["A", "B", "C"])
    c = db.abrir_corrida("M1", odate=SABADO,
                         aberta_em=datetime(2026, 8, 8, 4, 0),
                         membros=["A", "B", "C"], status="SEM_TRABALHO")
    for p in ("A", "B", "C"):
        db.execucao(p, "PULADO", odate=SABADO,
                    inicio=datetime(2026, 8, 8, 4, 1),
                    fim=datetime(2026, 8, 8, 4, 1), corrida=c["id"])


def _corrida_cheia_ainda_aberta(db, client):
    """Todos os membros concluídos e a corrida CONTINUA ABERTA — o estado em
    que a barra fecha sem que nada tenha acabado."""
    _monta_malha(client, "M1", ["A", "B", "C"])
    c = db.abrir_corrida("M1", odate=ODATE, aberta_em=datetime(2026, 8, 5, 4, 10),
                         membros=["A", "B", "C"])
    for p in ("A", "B", "C"):
        db.execucao(p, "SUCESSO", inicio=datetime(2026, 8, 5, 4, 20),
                    fim=datetime(2026, 8, 5, 7, 2), corrida=c["id"])


def _corrida_cheia_com_dispensado(db, client):
    """3 concluídos + 1 dispensado = os 4 do snapshot. A barra fecha e o
    denominador NÃO encolhe (Decisão 52)."""
    _monta_malha(client, "M1", ["A", "B", "C", "D"])
    c = db.abrir_corrida("M1", odate=ODATE, aberta_em=datetime(2026, 8, 5, 4, 10),
                         membros=["A", "B", "C", "D"])
    for p in ("A", "B", "C"):
        db.execucao(p, "SUCESSO", inicio=datetime(2026, 8, 5, 4, 20),
                    fim=datetime(2026, 8, 5, 7, 2), corrida=c["id"])
    db.execucao("D", "PULADO", inicio=datetime(2026, 8, 5, 4, 15),
                fim=datetime(2026, 8, 5, 4, 15), corrida=c["id"])


def _expirada(db, client):
    """Limite de segurança vencido com trabalho preso: 2 de 4 concluídos, 1 em
    falha, 1 que nunca partiu."""
    _monta_malha(client, "M1", ["A", "B", "C", "D"])
    c = db.abrir_corrida("M1", odate=ODATE, aberta_em=datetime(2026, 8, 5, 4, 10),
                         membros=["A", "B", "C", "D"], status="EXPIRADA")
    for p in ("A", "B"):
        db.execucao(p, "SUCESSO", inicio=datetime(2026, 8, 5, 4, 20),
                    fim=datetime(2026, 8, 5, 4, 50), corrida=c["id"])
    db.execucao("C", "FALHA", inicio=datetime(2026, 8, 5, 4, 30),
                fim=datetime(2026, 8, 5, 4, 35), corrida=c["id"])


def _cancelada(db, client):
    """Encerrada na mão, com motivo — o item de auditoria da Decisão 67."""
    _monta_malha(client, "M1", ["A", "B", "C", "D"])
    c = db.abrir_corrida("M1", odate=ODATE, aberta_em=datetime(2026, 8, 5, 4, 10),
                         membros=["A", "B", "C", "D"], status="CANCELADA")
    c["fechada_por"] = "manual:C123456"
    c["motivo"] = "encerrada por C123456: carga do dia 03 remarcada para a tarde"
    c["fechada_em"] = datetime(2026, 8, 5, 8, 20)
    for p in ("A", "B"):
        db.execucao(p, "SUCESSO", inicio=datetime(2026, 8, 5, 4, 20),
                    fim=datetime(2026, 8, 5, 4, 50), corrida=c["id"])


def _nao_abriu_entre_malhas_que_rodaram(db, client):
    """Duas malhas, e a ordem alfabética é a ORDEM ERRADA.

    `AAA_RODOU` abriu no horário e concluiu; `ZZ_PAROU` não abriu hoje (o
    Início não disparou) e só tem a corrida de ontem. O servidor devolve por
    nome — quem tem de subir `ZZ_PAROU` para o topo é a tela."""
    _monta_malha(client, "AAA_RODOU", ["A", "B"])
    _monta_malha(client, "ZZ_PAROU", ["C", "D"])
    ok = db.abrir_corrida("AAA_RODOU", odate=ODATE,
                          aberta_em=datetime(2026, 8, 5, 4, 10),
                          membros=["A", "B"], status="CONCLUIDA")
    for p in ("A", "B"):
        db.execucao(p, "SUCESSO", inicio=datetime(2026, 8, 5, 4, 20),
                    fim=datetime(2026, 8, 5, 4, 50), corrida=ok["id"])
    ontem = db.abrir_corrida("ZZ_PAROU", odate=ONTEM,
                             aberta_em=datetime(2026, 8, 4, 4, 10),
                             membros=["C", "D"], status="CONCLUIDA")
    for p in ("C", "D"):
        db.execucao(p, "SUCESSO", odate=ONTEM,
                    inicio=datetime(2026, 8, 4, 4, 20),
                    fim=datetime(2026, 8, 4, 7, 2), corrida=ontem["id"])


def _dia_do_deploy(db, client):
    """O interruptor `malha_corrida_ativa` em `0`: NINGUÉM abre corrida.

    É o estado do dia do deploy, e a fase tem de ser testável assim. A malha
    tem execução — o que ela não tem é ciclo."""
    assert db.config[mc.CHAVE_ATIVA] == "0"
    _monta_malha(client, "M1", ["A", "B"])
    db.execucao("A", "SUCESSO", inicio=datetime(2026, 8, 5, 4, 20),
                fim=datetime(2026, 8, 5, 4, 50))


# ═══════════════════════════ a bancada do front ══════════════════════════════

def _node() -> str | None:
    caminho = shutil.which("node")
    if not caminho or not SUCRASE.is_dir():
        return None
    try:
        v = subprocess.run([caminho, "-v"], capture_output=True, text=True,
                           timeout=30).stdout.strip()
        return caminho if int(v.lstrip("v").split(".")[0]) >= _MAJOR_MINIMO \
            else None
    except Exception:      # noqa: BLE001 — sonda de ambiente degrada em salto
        return None


@pytest.fixture(scope="module")
def auth_modulo(app):
    """A sessão de um operador — o perfil de quem está de plantão às 3h."""
    app.dependency_overrides[get_current_user] = lambda: {
        "matricula": "OPER1", "perfil": "operador",
        "permissoes": [PERM_EDITAR, PERM_EXECUTAR, "tela_malha"],
    }
    yield
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture(scope="module")
def payloads(client, auth_modulo) -> dict:
    """Todos os cenários, perguntados ao ROUTER de verdade.

    Cada valor é a resposta literal de `GET /malhas` — é ela que vai para a
    tela na bancada seguinte, sem nenhuma mão no meio."""
    p = {
        "sabado": _payload(client, _sabado_sem_trabalho,
                           agora_api=datetime(2026, 8, 8, 7, 0)),
        "fechando": _payload(client, _corrida_cheia_ainda_aberta),
        "fechando_com_dispensado": _payload(client, _corrida_cheia_com_dispensado),
        "expirada": _payload(client, _expirada),
        "cancelada": _payload(client, _cancelada),
        "nao_abriu": _payload(client, _nao_abriu_entre_malhas_que_rodaram),
        # O MESMO cenário, com o banco na hora do processo. O aceite exige que
        # o atraso EXIBIDO não mude quando o relógio do banco muda.
        "nao_abriu_sem_desvio": _payload(
            client, _nao_abriu_entre_malhas_que_rodaram,
            agora_banco=AGORA_API),
        "dia_do_deploy": _payload(client, _dia_do_deploy),
        "sem_085": _payload(client, _dia_do_deploy, com_085=False),
    }
    # Front novo × API VELHA. A resposta da API anterior a esta fase é esta
    # mesma, MENOS as três chaves que a fase acrescentou — e é assim que ela é
    # construída, em vez de escrita à mão: o que se prova é a reação do front à
    # AUSÊNCIA delas, e derivar a ausência do payload real impede o teste de
    # "esquecer" de tirar uma chave que a API velha também não manda.
    velha = json.loads(json.dumps(p["fechando"]))
    velha.pop("corrida_suportada", None)
    velha.pop("migration_085_pendente", None)
    for m in velha["malhas"]:
        m.pop("corrida", None)
        m.pop("corrida_esperada", None)
    p["api_velha"] = velha
    return p


@pytest.fixture(scope="module")
def tela(payloads) -> dict:
    """A LISTA DE MALHAS renderizada, cenário a cenário, no código de produção.

    Uma chamada de Node para todos os cenários: preparar a árvore de módulos é
    o caro, e repeti-lo por teste transformaria a suíte num teste de
    transpilador."""
    node = _node()
    if node is None:
        pytest.skip(_MOTIVO_SALTO)
    cenarios = {nome: {"payload": pl, "agora_ms": AGORA_LOCAL_MS}
                for nome, pl in payloads.items()}
    # A mesma página, reaberta com o parâmetro que o clique em `Acompanhar`
    # produz — é aqui que se vê se a URL vira LENTE ou fica de enfeite.
    cenarios["lente_na_url"] = {
        "payload": payloads["fechando"], "agora_ms": AGORA_LOCAL_MS,
        "url": "malha=M1&modo=execucao&corrida=7",
    }
    cenarios["url_estragada"] = {
        "payload": payloads["fechando"], "agora_ms": AGORA_LOCAL_MS,
        "url": "malha=M1&modo=execucao&corrida=abacaxi",
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


def _cenario(tela: dict, nome: str) -> dict:
    """O cenário renderizado — com as travas que impedem esta suíte de mentir.

    ⚠️ Metade dos aceites da fase é prova de AUSÊNCIA, e prova de ausência tem
    um modo de falso verde próprio: se a bancada parar de coletar texto (um
    seletor que deixou de casar, uma árvore que não renderizou), TODAS elas
    passam de uma vez, em silêncio, e a suíte fica verde sobre uma tela em
    branco. Por isso todo cenário passa por aqui, e aqui se exige que exista
    página: a âncora da tela e, quando o cenário tem malha, pelo menos um
    card."""
    dado = tela[nome]
    assert "__erro__" not in dado, \
        f"{nome} levantou na bancada:\n{dado.get('__erro__')}"
    # "zero exceção" é aceite da fase, e vale para TODO cenário: um componente
    # que levanta vira nó `erro:` em vez de derrubar o processo, justamente
    # para que a falha seja reportada aqui e não vire "cenário sem cards".
    assert dado["erros"] == [], f"{nome} renderizou com exceção: {dado['erros']}"
    assert "Malha de Pipelines" in dado["texto"] or dado["editor"], (
        f"{nome} não renderizou página nenhuma — uma prova de ausência sobre "
        "uma tela em branco passa sempre")
    if not dado["editor"]:
        assert dado["cards"], f"{nome} renderizou a página sem nenhum card"
    return dado


def _card(cenario: dict, malha: str = "M1") -> dict:
    return next(c for c in cenario["cards"] if c["malha"] == malha)


def _sem_acento(s: str) -> str:
    for de, para in (("í", "i"), ("á", "a"), ("ã", "a"), ("ç", "c"),
                     ("é", "e"), ("ú", "u"), ("ó", "o")):
        s = s.replace(de, para)
    return s


def _nao_diz_concluida(texto: str, onde: str):
    """"concluída" é a palavra proibida; "concluídos" é o vocabulário CORRETO.

    A distinção é o feminino: `concluída` descreve a CORRIDA (e só pode sair de
    `status = 'CONCLUIDA'` vindo do banco, §9.15/#15), enquanto
    `4 de 7 pipelines concluídos`, masculino plural, descreve os PIPELINES e é a
    frase que a spec manda escrever. Um teste que proibisse o radical proibiria
    a frase certa; um que só olhasse `concluída` deixaria passar `concluida`
    escrito torto."""
    baixo = texto.lower()
    assert "concluída" not in baixo, onde
    assert "concluida" not in _sem_acento(baixo), onde


# ══════════════ ACEITE 1 — sábado com todos dispensados ══════════════════════

def test_sabado_com_todos_dispensados_nao_tem_barra_nem_a_palavra_concluida(tela):
    """Aceite: *"sábado com todos os membros dispensados → nenhuma barra, texto
    'nada previsto', e a palavra 'concluída' ausente"*.

    Os três pedaços são um só defeito visto de três lados: 0% leria como
    "falhou tudo", barra cheia como "rodou tudo" e "concluída" como "a
    madrugada foi bem" — e num sábado legítimo nenhum dos três aconteceu.
    Alarme falso semanal treina o operador a ignorar o alarme (Decisões
    26/27), e uma tranquilização falsa semanal treina o oposto."""
    c = _cenario(tela, "sabado")
    card = _card(c)
    # NENHUMA barra: a ausência é do nó com `role="progressbar"`, não de uma
    # string. Uma barra com `total = 0` passaria por qualquer teste de texto.
    assert card["barra"] is None
    assert "nada previsto" in card["textos"]
    assert "os 3 membros não rodam hoje (regra de dia)" in card["textos"]
    assert "sem trabalho hoje" in card["textos"]
    # nem "0 de 3", nem "3 de 3"
    assert not [t for t in card["textos"] if re.search(r"\d+ de \d+", t)]
    _nao_diz_concluida(c["lido"], "a página inteira do sábado")
    assert "%" not in c["lido"]


# ══════════════ ACEITE 2 — barra cheia numa corrida ABERTA ═══════════════════

def test_barra_cheia_em_corrida_aberta_diz_fechando_e_nunca_100_nem_concluida(tela):
    """Aceite: *"corrida ABERTA com `ok === total − dispensados` → barra cheia,
    rótulo `7 de 7 · fechando — fecha 15 min após o último movimento; se nada
    mais mexer, por volta de 04:17`, e nem '100%' nem 'concluída' em lugar
    nenhum"*.

    É a mentira de sempre antecipada em 15 minutos: o último pipeline fica
    verde às 07:02 e a corrida só fecha às 07:17. A frase diz a REGRA antes da
    hora — anunciar só o horário produziria o chamado falso das 07:18, porque a
    carência REINICIA a cada movimento."""
    c = _cenario(tela, "fechando")
    card = _card(c)
    assert card["barra"]["valuenow"] == card["barra"]["valuemax"] == 3
    assert "3 de 3 · fechando" in card["textos"]
    assert ("↳ fecha 15 min após o último movimento; se nada mais mexer, "
            "por volta de 07:17") in card["texto"]
    # ── a prova de AUSÊNCIA, sobre a PÁGINA inteira ──────────────────────────
    assert "100%" not in c["lido"] and "%" not in c["lido"]
    _nao_diz_concluida(c["lido"], "a página com a barra cheia")
    # o rótulo do ciclo continua sendo o do banco: ABERTA
    assert "em andamento" in card["textos"]


def test_barra_cheia_com_dispensado_nao_encolhe_o_denominador(tela):
    """A mesma barra cheia, agora com um membro que não roda hoje: `3 de 4`, e
    jamais `3 de 3`.

    Com `total − dispensados` como denominador, três membros barrados por regra
    de dia fariam o número SUBIR sem nada ter acontecido — o card mentindo com
    matemática nova (Decisão 52)."""
    c = _cenario(tela, "fechando_com_dispensado")
    card = _card(c)
    assert "3 de 4 · fechando" in card["textos"]
    assert card["barra"]["valuenow"] == 3 and card["barra"]["valuemax"] == 4
    assert ("4 membros nesta corrida · 1 não roda hoje (regra de dia)"
            in card["textos"])
    # a barra FECHA mesmo assim: o trilho hachurado ocupa o resto
    assert card["barra"]["larguras"] == ["75%", "25%"]
    assert "%" not in c["lido"]
    _nao_diz_concluida(c["lido"], "a página com dispensado")


# ══════════════ ACEITE 3 — o grep da Decisão 56 e da Decisão 74 ══════════════

# Os arquivos que desenham a corrida. `ui/Progress.tsx` entra: é lá que mora o
# único `%` legítimo do produto (a largura em CSS), e é justamente por isso que
# ele precisa estar sob a regra — a varredura abaixo separa CSS de texto.
COMPONENTES_DE_CORRIDA = [
    "components/malhas/statusExecucao.ts",
    "components/malhas/CorridaBadge.tsx",
    "components/malhas/CorridaProgresso.tsx",
    "components/malhas/tempoCorrida.ts",
    "components/ui/Progress.tsx",
    "pages/Malha.tsx",
]

# Literal de string/template e texto solto de JSX — o que vira PIXEL na tela.
# Comentário e nome de variável ficam de fora de propósito (§9.11: "casar em
# comentário e em nome de variável é esperado"), e os arquivos desta camada
# explicam em prosa justamente as regras que proíbem `%` e `#N`: varrer o texto
# inteiro provaria o contrário do que se quer provar.
#
# ⚠️ A extração é um VARREDOR de estados, e não um regex de literais. Foi a
# própria suíte que exigiu a troca: um regex de aspas casa o fechamento de uma
# string com a abertura da SEGUINTE assim que uma delas contém uma barra
# invertida ou um apóstrofo, e o "literal" resultante engolia meia tela de
# código — trazendo junto o `#1A5FA8` de um `className` e transformando a
# proibição da Decisão 74 num falso vermelho.
_HEX = re.compile(r"#[0-9A-Fa-f]{3,8}\b")


def _textos_exibiveis(caminho: Path) -> list[str]:
    """Todo texto que pode virar PIXEL: literais de string/template e o texto
    solto entre tags JSX. Comentários (de linha e de bloco) ficam de fora.

    Cor hexadecimal (`#1A5FA8`, a cor da casa) é removida de cada trecho: ela
    casa com `#\\d` e não é texto de interface — é o valor de um `className`.
    Deixá-la faria a regra proibir a paleta, e uma regra que grita no lugar
    errado é desligada na primeira semana."""
    fonte = caminho.read_text(encoding="utf-8")
    saida: list[str] = []
    i, n = 0, len(fonte)
    while i < n:
        ch = fonte[i]
        if ch == "/" and i + 1 < n and fonte[i + 1] == "/":
            i = fonte.find("\n", i)
            if i < 0:
                break
        elif ch == "/" and i + 1 < n and fonte[i + 1] == "*":
            fim = fonte.find("*/", i + 2)
            i = n if fim < 0 else fim + 2
        elif ch in "'\"`":
            fim, j = ch, i + 1
            while j < n and fonte[j] != fim:
                j += 2 if fonte[j] == "\\" else 1
            saida.append(fonte[i + 1:j])
            i = j + 1
        else:
            i += 1
    # Texto solto entre tags JSX (`>4 de 7<`) — o que nenhum literal pega.
    saida += re.findall(r">([^<>{}\n]{2,})<", fonte)
    return [_HEX.sub("", t) for t in saida]


def test_nenhum_percentual_exibido_nos_componentes_de_corrida(tela):
    """Aceite: *"`grep` nos componentes de corrida não casa nenhum percentual
    **exibido** (Decisão 56)"* — escrito como TESTE, não como conferência.

    "4 de 7" lido como "57%" é percentual de um trabalho que não existe: os
    pipelines têm durações diferentes, e numa malha em que o último leva 3h e
    os cinco primeiros 5 min, `5 de 6` é 83% dos pipelines e 12% do trabalho. O
    percentual que o usuário pediu mede TEMPO e é da F12.

    A única exceção é nominal e verificada: a largura CSS de `ui/Progress`, que
    é DESENHO. Ela é reconhecida pela forma exata (`${…}%` dentro de `width`), e
    a prova de que ela não vaza para o que se lê é a varredura da página
    renderizada, logo abaixo."""
    for rel in COMPONENTES_DE_CORRIDA:
        for texto in _textos_exibiveis(SRC / rel):
            if "%" not in texto:
                continue
            assert re.fullmatch(r"\$\{[^}]+\}%", texto.strip()), (
                f"percentual EXIBIDO em {rel}: {texto!r}")

    # ...e o CSS não chega ao que se lê, em nenhum dos estados renderizados.
    # `_cenario` (e não `tela.items()` cru) porque é ele que garante que houve
    # tela: varrer um cenário que não renderizou passaria sempre.
    for nome in tela:
        assert "%" not in _cenario(tela, nome)["lido"], nome


def test_nenhum_numero_de_maquina_chega_a_interface(tela):
    """Aceite: *"`grep -nE '#[0-9]'` não casa texto de interface (Decisão 74)"*.

    Três numerações disputam essa notação — `id`, `sequencia` e o
    `aberta_por='inicio:#12'` —, e `#12` numa malha diária lê-se como "12ª
    tentativa hoje", que é falso. O rótulo humano é `corrida de 05/08`, e só a
    partir da segunda do dia, `2ª corrida de 05/08`."""
    for rel in COMPONENTES_DE_CORRIDA:
        for texto in _textos_exibiveis(SRC / rel):
            assert not re.search(r"#\d", texto), f"'#N' exibido em {rel}: {texto!r}"

    for nome in tela:
        assert not re.search(r"#\d", _cenario(tela, nome)["lido"]), nome
    # e o rótulo humano está lá, no lugar do número de máquina
    assert "corrida de 05/08" in _card(_cenario(tela, "fechando"))["textos"]


# ══════════════ ACEITE 4 — EXPIRADA e CANCELADA ══════════════════════════════

def test_expirada_congela_a_barra_e_diz_parou_em(tela):
    """Aceite: *"`EXPIRADA` e `CANCELADA` → barra congelada com `opacity-60` e o
    rótulo 'parou em 4 de 7'"*.

    O número que ficou não é progresso: é onde ela parou. E "concluído" não
    aparece em nenhum dos três desfechos interrompidos — invariante 4 do §16,
    nunca inventar verde."""
    c = _cenario(tela, "expirada")
    card = _card(c)
    assert "parou em 2 de 4" in card["textos"]
    assert "opacity-60" in card["classes"]
    # o travado fica FORA do comprimento da barra (Decisão 54): 2 verdes de 4,
    # e o que falhou vira chip
    assert card["barra"]["valuenow"] == 2 and card["barra"]["valuemax"] == 4
    assert card["barra"]["larguras"] == ["50%"]
    assert "1 travado" in card["textos"]
    assert "encerrada sem terminar" in card["textos"]
    _nao_diz_concluida(c["lido"], "a página da corrida expirada")


def test_cancelada_diz_quem_encerrou_e_por_que(tela):
    """Aceite: *"`CANCELADA` mostra **quem** encerrou e o **motivo**"* (Decisão
    67).

    `fechada_por` e `motivo` são gravados desde a F3 e nunca foram mostrados:
    fechar o mês com três corridas canceladas e não conseguir explicar nenhuma
    sem abrir o banco é o defeito que isto mata."""
    c = _cenario(tela, "cancelada")
    card = _card(c)
    assert "parou em 2 de 4" in card["textos"]
    assert "encerrada por C123456 às 08:20" in card["textos"]
    assert ('motivo: "carga do dia 03 remarcada para a tarde"'
            in card["textos"])
    # âmbar de CONTORNO, e não cinza: é ação humana e item de auditoria
    assert "amber" in card["classes"]
    assert "opacity-60" in card["classes"]
    _nao_diz_concluida(c["lido"], "a página da corrida cancelada")


# ══════════════ ACEITE 5 — a corrida que NÃO ABRIU ═══════════════════════════

def test_o_card_que_nao_abriu_e_ambar_e_vem_primeiro_na_lista(tela):
    """Aceite: *"DAG do Início pausada, horário previsto vencido, nenhuma
    corrida com o ODATE do dia → card `não abriu`, âmbar, **primeiro** na
    ordenação da lista"*.

    O cenário é escolhido para que a ordem alfabética seja a ERRADA:
    `AAA_RODOU` rodou bem e `ZZ_PAROU` não abriu. Numa grade de 40 cards em
    ordem alfabética, a malha que não rodou é justamente a que some — e sem
    este estado o card dela mostraria a corrida de ONTEM, verde, com carimbo de
    frescor recente."""
    c = _cenario(tela, "nao_abriu")
    assert c["ordem"] == ["ZZ_PAROU", "AAA_RODOU"], (
        "a lista manteve a ordem do servidor: a malha que não rodou ficou "
        "escondida no meio das que rodaram")
    parou = _card(c, "ZZ_PAROU")
    assert "não abriu" in parou["textos"]
    assert "amber" in parou["classes"]
    assert "nenhuma corrida de 05/08" in parou["textos"]
    # sem barra: não há o que preencher
    assert parou["barra"] is None
    # a corrida de ONTEM não some — vira contexto, não manchete
    assert "↳ anterior: corrida de 04/08 · concluída" in parou["texto"]
    # e a que rodou continua contando a própria história
    assert _card(c, "AAA_RODOU")["barra"]["valuenow"] == 2
    # contador próprio na stats bar, em âmbar (Decisão 58)
    pilula = next(s for s in c["stats"] if "não abriu" in s["texto"])
    assert pilula["texto"] == "1 não abriu"
    assert "amber" in pilula["classes"]


def test_a_tela_que_nao_abriu_continua_se_atualizando_sozinha(tela):
    """Decisão 73 — `não abriu` entra no MESMO predicado do polling da corrida
    em voo, e o teste PERGUNTA à função, não lê o fonte.

    "Não abriu" é um estado de RELÓGIO: *"previsto para 01:00 · há 7h12"*
    cresce a cada minuto. Sem polling, a tela congela naquele número enquanto
    alguém dispara a malha na mão do outro lado — e como o MESMO predicado
    governa o alarme de dado velho, o card mais grave da manhã seria o único a
    envelhecer em silêncio, sem o `⚠ dado de HH:MM`."""
    assert _cenario(tela, "nao_abriu")["polling"] == 20_000
    # ...e o contrapeso: sem nada em movimento a tela NÃO fica batendo na API.
    # Ligar polling incondicional é pagar as 24 h por causa das 4 da madrugada.
    assert _cenario(tela, "dia_do_deploy")["polling"] is False


def test_o_atraso_exibido_nao_muda_quando_o_relogio_do_banco_e_deslocado(tela,
                                                                         payloads):
    """Aceite: *"com o relógio do banco deslocado 3 h, o atraso exibido continua
    correto (o cálculo é da API, Decisão 58)"*.

    A prova é a comparação de DOIS cenários idênticos em tudo menos no relógio
    do banco: um com o desvio de 3 h medido no dev, outro com o banco na hora
    do processo. O atraso é o mesmo nos dois — na API e na tela.

    Uma implementação que comparasse o horário do cron com o relógio do BANCO
    publicaria 9h onde são 6h, e o card acusaria a malha todo dia, no horário em
    que ela está saudável."""
    def esperada(nome):
        malha = next(m for m in payloads[nome]["malhas"]
                     if m["malha_name"] == "ZZ_PAROU")
        return malha["corrida_esperada"]

    com_desvio, sem_desvio = esperada("nao_abriu"), esperada("nao_abriu_sem_desvio")
    assert com_desvio["atrasada_min"] == sem_desvio["atrasada_min"] == 360
    assert com_desvio["previsto_para"] == sem_desvio["previsto_para"] == "01:00"

    for nome in ("nao_abriu", "nao_abriu_sem_desvio"):
        card = _card(_cenario(tela, nome), "ZZ_PAROU")
        assert "não abriu· previsto para 01:00 · há 6h" in card["texto"], nome


# ══════════════ ACEITE 6 — front novo × API velha ════════════════════════════

def test_api_velha_faz_o_card_dizer_que_falta_informacao_sem_exceção(tela):
    """Aceite: *"front novo × API velha (payload sem `corrida`) → card com
    '(membro mais recente)' **e** a linha `⚠ sem dados de corrida — sistema em
    atualização`, zero exceção no console"*.

    O `deploy.sh` publica o `dist/` na etapa 3 e reconstrói a `api/` só na 7:
    nesse intervalo o front novo conversa com a API velha. Sem um marcador
    POSITIVO de versão, o front concluiria "está tudo certo" e degradaria em
    silêncio — que é o oposto de degradar DIZENDO."""
    c = _cenario(tela, "api_velha")          # `_cenario` já exige zero exceção
    card = _card(c)
    assert card["barra"] is None
    assert "(membro mais recente" in card["texto"]
    assert "sem dados de corrida — sistema em atualização" in card["textos"]
    _nao_diz_concluida(c["lido"], "a página contra a API velha")
    # ...e o botão da fase continua de pé: degradar não é perder a navegação
    assert card["acompanhar_existe"] and not card["acompanhar_desabilitado"]


def test_banco_sem_a_085_diz_a_mesma_frase_que_a_api_velha(tela):
    """A outra metade da Decisão 41, e esta é servida pelo router DE VERDADE: o
    banco sem a migration 085.

    São causas diferentes com a mesma consequência para quem lê a tela, e por
    isso a frase é a mesma. Provar as duas separadamente é o que impede alguém
    de consertar uma e deixar a outra muda."""
    c = _cenario(tela, "sem_085")
    card = _card(c)
    assert card["barra"] is None
    assert "sem dados de corrida — sistema em atualização" in card["textos"]
    _nao_diz_concluida(c["lido"], "a página sem a 085")


# ══════════════ ACEITE 7 — `Acompanhar` com o interruptor em 0 ═══════════════

def test_com_o_interruptor_em_zero_o_acompanhar_existe_e_leva_a_execucao(tela):
    """Aceite: *"com o interruptor `malha_corrida_ativa = 0` (o estado do dia do
    deploy) → `Acompanhar` **existe e funciona**, levando à lente de execução da
    data corrente — a fase é testável sem nenhuma corrida no banco"*.

    Este é o teste que NÃO pode ser um `grep`: o botão é achado na árvore
    renderizada e CLICADO, e o que se afirma é o parâmetro de URL que saiu do
    outro lado. Sem corrida, ele vai sem `corrida=` — e é isso que faz o painel
    abrir na data corrente, que já funciona hoje."""
    c = _cenario(tela, "dia_do_deploy")
    card = _card(c)
    assert card["barra"] is None                    # não há ciclo nenhum
    assert card["acompanhar_existe"]
    assert not card["acompanhar_desabilitado"]
    assert card["acompanhar_navegou"] == [{"malha": "M1", "modo": "execucao"}]


def test_com_corrida_o_acompanhar_leva_a_lente_daquela_corrida(tela):
    """Com ciclo registrado, o clique leva `corrida=` junto.

    Sem o id, o painel abriria na corrida CORRENTE do servidor: quem clicou num
    card que mostrava a de ontem cairia na de hoje, e a tela responderia outra
    pergunta."""
    c = _cenario(tela, "fechando")
    card = _card(c)
    navegou = card["acompanhar_navegou"]
    assert len(navegou) == 1
    assert navegou[0]["malha"] == "M1" and navegou[0]["modo"] == "execucao"
    assert navegou[0]["corrida"].isdigit()


def test_as_posicoes_dos_botoes_do_card_sao_fixas_entre_estados(tela):
    """Decisão 72, a outra metade: botão que muda de lugar entre estados faz
    clicar em "Diagrama" no card 1 e acertar "Membros" no card 2.

    A mesma ordem em TODOS os estados desta fase — com corrida, sem corrida,
    degradado e "não abriu" —, e o que não cabe num estado é desabilitado, nunca
    removido."""
    ordem = ["Acompanhar", "Diagrama", "Membros", "Renomear", "Inativar"]
    for nome in ("fechando", "sabado", "expirada", "cancelada",
                 "dia_do_deploy", "api_velha", "sem_085"):
        card = _card(_cenario(tela, nome))
        assert [b["rotulo"] for b in card["botoes"]] == ordem, nome
    parou = _card(_cenario(tela, "nao_abriu"), "ZZ_PAROU")
    assert [b["rotulo"] for b in parou["botoes"]] == ordem


def test_a_lente_da_url_chega_ao_painel_de_execucao(tela):
    """O outro lado do clique: reabrir a página com o parâmetro que ele produz.

    Sem isto, `Acompanhar` poderia estar "funcionando" só até a barra de
    endereço — a URL trocaria e o painel abriria na corrida corrente do
    servidor, que é outra pergunta."""
    c = _cenario(tela, "lente_na_url")
    assert c["editor"] == [{"malha": "M1", "modoInicial": "execucao",
                            "dataInicial": None, "corridaInicial": 7}]
    # ...e o parâmetro estragado não vira `NaN` numa query string: cai na
    # corrida corrente, que é o comportamento de sempre.
    ruim = _cenario(tela, "url_estragada")
    assert ruim["editor"][0]["corridaInicial"] is None
    assert ruim["editor"][0]["modoInicial"] == "execucao"


# ══════════════ ACEITE 8 — a acessibilidade da barra ═════════════════════════

def test_a_barra_do_card_tem_role_e_aria_em_pt_br(tela):
    """Aceite: *"a barra tem `role="progressbar"`, `aria-valuenow`,
    `aria-valuemax` e `aria-label` em pt-BR — as 4 barras existentes não têm
    nenhum dos dois"*.

    E o `aria-valuetext`, que não está na letra do aceite e é a metade que
    quase escapa: sem ele, o leitor de tela DERIVA `valuenow/valuemax` e anuncia
    "100%" sozinho — o percentual de contagem proibido pela Decisão 56 entrando
    pela porta da acessibilidade, invisível em qualquer inspeção visual."""
    barra = _card(_cenario(tela, "fechando"))["barra"]
    assert barra["role"] == "progressbar"
    assert barra["valuemin"] == 0
    assert barra["valuenow"] == 3 and barra["valuemax"] == 3
    assert barra["ariaLabel"] == "progresso da corrida, em pipelines concluídos"
    # pt-BR de verdade, com acentuação
    assert "progresso" in barra["ariaLabel"] and "concluídos" in barra["ariaLabel"]
    assert barra["valuetext"] == "3 de 3 pipelines concluídos"
    assert "%" not in barra["valuetext"]


def test_a_barra_do_dashboard_tambem_ganhou_os_atributos(tela):
    """A mesma `ui/Progress` é a barra de "Rodando agora" do Dashboard (§9.8), e
    ela entra nesta PR porque é o molde que esta camada copiaria.

    Aqui se prova o CHAMADOR: a barra do Dashboard passa `ariaLabel` e
    `valorTexto` próprios. O número que ela desenha é conferido contra o SQL
    Server em `test_dashboard_rodando_agora_f9.py` — as duas metades do mesmo
    defeito, cada uma provada onde ela mora."""
    fonte = (SRC / "pages" / "Dashboard.tsx").read_text(encoding="utf-8")
    assert "ariaLabel={`jobs concluídos do pipeline ${e.pipeline}`}" in fonte
    assert "valorTexto={`${e.jobs_ok} de ${e.total_jobs} jobs concluídos" in fonte
    # a barra ad-hoc que dizia 0% saiu de cena junto com o número errado
    assert "const pct = e.total_jobs > 0" not in fonte


# ══════════════ o que o SERVIDOR precisa entregar para tudo acima ════════════

def test_o_destino_do_acompanhar_responde_sem_corrida_nenhuma(client,
                                                              auth_modulo):
    """A segunda metade de "existe e FUNCIONA": o clique leva a
    `?modo=execucao` **sem** `corrida=`, e essa lente tem de responder no dia do
    deploy — com o interruptor em `0` e nenhuma corrida no banco.

    Um botão que navega para uma tela que devolve 500 "existe" e não funciona;
    é por isso que a prova do front (o clique) e a do servidor (a resposta)
    são um par, e nenhuma das duas basta sozinha."""
    db = FakeDb(pipelines=_pipes())
    mc.limpar_cache()
    try:
        with _patch(db), _patch_agora():
            _dia_do_deploy(db, client)
            r = client.get("/malhas/M1/execucao")
    finally:
        mc.limpar_cache()
    assert r.status_code == 200, r.text
    corpo = r.json()
    # A lente sem corrida cai na data corrente — o comportamento que já existe
    # hoje, e é ele que torna a fase testável sem ciclo nenhum.
    assert corpo["data_referencia"] == "2026-08-05"
    assert corpo.get("corrida") in (None, {})


def test_o_payload_traz_a_regra_e_a_hora_do_fechamento(payloads):
    """O contrato que sustenta o aceite 2, conferido no que a API EMITE.

    A frase "fecha 15 min após o último movimento; se nada mais mexer, por
    volta de 07:17" tem duas metades e as duas vêm do servidor: a REGRA
    (`quiescencia_min`) e a HORA (`quiescencia_ate`, somada com `DATEADD` no
    BANCO). Somar em Python devolveria um instante 3 h adiantado — e a tela
    prometeria um horário que não é o do fechamento."""
    corrida = payloads["fechando"]["malhas"][0]["corrida"]
    assert corrida["status"] == "ABERTA"
    assert (corrida["membros_ok"], corrida["membros_total"]) == (3, 3)
    assert corrida["quiescencia_min"] == mc.QUIESCENCIA_MIN_PADRAO
    # 07:02 (último movimento, régua do banco) + 15 min
    assert corrida["quiescencia_ate"] == "2026-08-05 07:17:00"


def test_o_marcador_de_versao_sai_em_toda_resposta(payloads):
    """`corrida_suportada` é o marcador POSITIVO de versão da API (Decisão 41).

    Ele não pode depender do estado do banco: sem a 085 a resposta continua
    dizendo "esta API sabe responder sobre ciclo", e quem diz que o CICLO não
    está disponível é a outra flag. Confundir as duas faria o front tratar um
    banco desatualizado como um servidor desatualizado — e vice-versa, que é o
    caso silencioso."""
    for nome in ("fechando", "dia_do_deploy", "sem_085"):
        assert payloads[nome]["corrida_suportada"] is True, nome
    assert payloads["sem_085"]["migration_085_pendente"] is True
    assert "migration_085_pendente" not in payloads["fechando"]
