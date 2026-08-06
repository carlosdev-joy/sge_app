"""
F10 de `docs/spec-malha-execucao.md` — **a suíte de ACEITE**, um teste por
bullet da §10/### F10, cada um nomeado pelo que prova.

── O que esta suíte acrescenta às outras duas da fase ────────────────────────
`test_malha_corrida_agregado_f10.py` prova o SERVIDOR (a consulta de conjunto,
o raio, a cascata, o ordenamento) e `test_malhas_f10_painel.py` prova os
módulos PUROS do front. Restava o pedaço mais caro de provar e o mais fácil de
fingir: **o que a tela renderiza**.

Quatro aceites desta fase moram em JSX — `Encerrar corrida…` presente e
HABILITADO em `ABERTA·OK`, `ABERTA·COM_FALHA` e `ABERTA·SEM_PROGRESSO`; a
confirmação dizendo que os pipelines CONTINUAM rodando; `Agora (2)` com badge
neutro; a barra de limite existindo só com `teto_horas`. Até aqui eles eram
provados por `grep` no `.tsx`, e é exatamente esse o modo de falso verde que a
F7 já pagou nesta spec: **afirmar a MENSAGEM e não o COMPORTAMENTO**. Uma
string existe no arquivo mesmo quando está num ramo que nunca renderiza; o
`grep` fica verde e a tela, muda.

Aqui os componentes são RENDERIZADOS de verdade (`tests/js/minireact.cjs` —
hooks e laço de re-render em ~150 linhas, sem runner novo e sem rede, porque o
deploy é offline com wheels) e CLICADOS: a confirmação do encerramento só
existe depois do clique, e nenhum `grep` alcança isso.

── A guarda contra o outro modo de falso verde (o da F8) ────────────────────
"Dublê que fabrica dado que o servidor real nunca produz" tem teste próprio
aqui: `test_o_duble_do_front_nao_inventa_campo_que_o_servidor_nao_manda`
compara chave a chave o objeto do dublê JS com o payload de verdade do
`GET /malhas/{m}/execucao`.

Sem Node ou sem `node_modules`, a bancada SALTA em vez de falhar — e o salto é
visível no `-rs`. Os testes de servidor deste arquivo não dependem do Node.

⚠️ O interruptor `malha_corrida_ativa` fica DESLIGADO (o estado do dev e o do
dia do deploy): a LEITURA da corrida não depende dele, e a fase tem de ser
testável assim.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from datetime import timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest

if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()
os.environ.setdefault("MSSQL_CONN_STR", "__mock__")
from api.main import app as _app  # noqa: F401  (ordem de import — ver test_copias.py)

from routers import malhas as malhas_router
from tests.test_malha_corrida_agregado_f10 import (FakeDb, _corrida_em_cadeia,
                                                   _pendentes)
from tests.test_malha_corrida_porta import AGORA_BANCO
from tests.test_malhas_f4_card import (ODATE, _patch, _patch_agora, _pipes,
                                       auth)                     # noqa: F401
from tests.test_malhas_f10 import _cria_no, _monta_malha

RAIZ = Path(__file__).resolve().parents[1]
HARNESS = RAIZ / "tests" / "js" / "f10_aceite_harness.cjs"
SUCRASE = RAIZ / "ui-react" / "node_modules" / "sucrase"

_MOTIVO_SALTO = ("front não instalado nesta máquina (node ≥ 18 ou "
                 "ui-react/node_modules/sucrase ausente) — os aceites de "
                 "servidor deste arquivo continuam valendo")
_MAJOR_MINIMO = 18


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
def tela() -> dict:
    """A bancada de render. Roda UMA vez por módulo — transpilar a árvore do
    `src/` custa ~1 s e nenhum cenário depende de outro."""
    node = _node()
    if node is None:
        pytest.skip(_MOTIVO_SALTO)
    r = subprocess.run([node, str(HARNESS)], capture_output=True, text=True,
                       cwd=str(RAIZ), timeout=180)
    assert r.returncode == 0, f"bancada de render falhou:\n{r.stderr}"
    return json.loads(r.stdout)


def _cena(tela: dict, nome: str) -> dict:
    dado = tela[nome]
    assert "erro" not in dado, f"{nome} levantou no front:\n{dado.get('erro')}"
    return dado


# ═══ aceite 5 — `Encerrar corrida…` em TODA corrida ABERTA (Decisão 62) ══════

def test_encerrar_corrida_esta_presente_e_habilitado_nas_tres_saudes(tela):
    """O aceite, literal e RENDERIZADO: `ABERTA · OK`, `ABERTA · COM_FALHA` e
    `ABERTA · SEM_PROGRESSO`, os três com o botão presente **e habilitado**.

    Não é detalhe de redação: os dois casos em que mais se precisa encerrar são
    justamente `SEM_PROGRESSO` (o DagRun morreu e nada mais vai se mexer) e
    `COM_FALHA` (já se decidiu que a madrugada acabou). Um botão que só nasce
    depois do teto vencido reintroduz o problema que a Decisão 32 existe para
    matar — e um botão que aparece CINZA é a mesma porta trancada com outra
    roupa, e por isso `habilitado` é asserção separada de `presente`."""
    d = _cena(tela, "encerrar_em_toda_corrida_aberta")
    for saude in ("OK", "COM_FALHA", "SEM_PROGRESSO", "ATRASADA"):
        assert d[f"ABERTA:{saude}"] == {"presente": True, "habilitado": True}, \
            saude


def test_corrida_fechada_nao_oferece_encerrar_e_sem_permissao_ele_aparece_travado(tela):
    """Os dois lados que dão sentido ao aceite acima.

    Em corrida FECHADA não há ciclo para encerrar — oferecer o botão seria
    prometer um gesto que não existe. E sem `acao_executar` ele aparece
    DESABILITADO com o motivo no `title`: esconder a saída de emergência faria
    o operador procurá-la onde ela não está, às 3h."""
    d = _cena(tela, "encerrar_em_toda_corrida_aberta")
    for status in ("CONCLUIDA", "FALHA", "EXPIRADA", "CANCELADA"):
        assert d[status]["presente"] is False, status
    assert d["sem_permissao"]["presente"] is True
    assert d["sem_permissao"]["habilitado"] is False
    assert "permissão" in (d["sem_permissao"]["title"] or "")


def test_a_confirmacao_do_encerramento_diz_que_os_pipelines_continuam_rodando(tela):
    """O aceite literal — e ele só existe DEPOIS DO CLIQUE, que é a razão de
    esta bancada renderizar e clicar em vez de dar `grep` no arquivo.

    "Encerrar" não é "matar", e essa é exatamente a dúvida que faz o operador
    NÃO apertar o botão às 3h. A frase responde antes do clique seguinte, e o
    número dos vivos é nominal ("os 2 pipelines"), não genérico."""
    d = _cena(tela, "confirmacao_do_encerramento")
    for nome in ("ok", "com_falha", "sem_progresso"):
        cena = d[nome]
        # Antes do clique a frase NÃO está na tela: se estivesse, o teste
        # passaria por a string existir no arquivo — o falso verde da F7.
        assert cena["antes_tem_frase"] is False, nome
        assert "Nenhum pipeline é interrompido" in cena["texto"], nome
        assert "CONTINUAM rodando" in cena["texto"], nome
        assert "libera o disparo da próxima corrida" in cena["texto"], nome
        # Decisão 32: motivo obrigatório — confirmar nasce travado.
        assert cena["confirmar_travado_sem_motivo"] is True, nome
    # O que MUDA por estado é só o texto (Decisão 62), e ele muda de verdade:
    assert "sem sinal" in d["sem_progresso"]["texto"]
    assert "falha detectada" in d["com_falha"]["texto"]
    assert "sem sinal" not in d["ok"]["texto"]


# ═══ aceite 4 — `Agora (2)` com dois saudáveis → badge NEUTRO ════════════════

def test_a_aba_agora_com_dois_pipelines_saudaveis_tem_badge_neutro(tela):
    """`Agora (2)` são dois pipelines rodando BEM. Com o vermelho que a
    `ui/Tabs` pinta por padrão em todo badge, o operador leria "2 problemas" às
    3h — e o painel estaria gritando por uma corrida saudável.

    O contraste é parte da prova: se `Travando` também saísse neutro, "neutro"
    não significaria nada. As duas classes têm de ser DIFERENTES, e só a de
    `Travando` pode ser vermelha."""
    d = _cena(tela, "badge_da_aba_agora")
    assert "bg-red-" not in d["agora"], d["agora"]
    assert "bg-red-100" in d["travando_com_travado"]
    assert d["agora"] != d["travando_com_travado"]


# ═══ aceite 6 — a barra de limite e o crédito que não é silencioso (D61) ═════

def test_malha_sem_teto_configurado_nao_desenha_barra_de_limite(tela):
    """Decisão 61: `teto_horas` é `NULL` por padrão e cai no global de 24h, que
    é **anti-travamento, não SLA**. Uma barra em 80% às 20h numa malha que
    sempre fecha em 3h faria escalar por nada.

    Sem teto configurado a faixa desenha UMA barra — a do progresso — e o prazo
    que ela mostra é o do PRÓXIMO GATILHO, que é o fato que decide o
    escalonamento ("enquanto esta não fechar, ela não abre")."""
    d = _cena(tela, "barra_de_limite")
    rotulos = [b["label"] for b in d["sem_teto"]]
    assert rotulos == ["progresso da corrida, em pipelines concluídos"], rotulos
    assert "limite de segurança" not in d["texto_sem_teto"]
    assert d["gatilho_sem_teto"] is True
    assert "enquanto esta não fechar, ela não abre" in d["texto_sem_teto"]


def test_malha_com_teto_configurado_desenha_a_barra_sem_anunciar_percentual(tela):
    """Com `teto_horas` na malha a barra aparece — e ela passa pela
    `ui/Progress`, que é o que impede o defeito da §9.11: `role="progressbar"`
    com `valuenow`/`valuemax` faz o LEITOR DE TELA calcular e anunciar o
    percentual sozinho (o `57%` que a Decisão 56 proíbe em toda superfície).

    A defesa é o `aria-valuetext`, que tem precedência sobre o cálculo — e o
    texto diz **limite**, nunca "progresso" e nunca contagem de pipelines."""
    d = _cena(tela, "barra_de_limite")
    rotulos = [b["label"] for b in d["com_teto"]]
    assert "limite de segurança da corrida" in rotulos, rotulos
    limite = next(b for b in d["com_teto"]
                  if b["label"] == "limite de segurança da corrida")
    assert limite["valuetext"], (
        "a barra de limite ficou sem `aria-valuetext` — o leitor de tela volta "
        "a anunciar o percentual que a Decisão 56 proíbe")
    assert "limite" in limite["valuetext"]
    assert "%" not in limite["valuetext"]
    assert "pipeline" not in limite["valuetext"]
    # E a barra do PROGRESSO continua anunciando `x de y`, nunca percentual.
    progresso = next(b for b in d["com_teto"] if b["label"].startswith("progresso"))
    assert "4 de 7" in progresso["valuetext"] and "%" not in progresso["valuetext"]


def test_soltar_um_hold_de_6h_nao_faz_a_barra_recuar_em_silencio(tela):
    """O aceite literal da Decisão 61. Soltar um hold empurra `teto_em`, e a
    barra de limite **anda para trás**: às 03:00 ela está em 80%, alguém solta
    um hold de 6 h e ela cai para 55% sozinha.

    Uma barra de prazo que recua sem explicação destrói a confiança em todas as
    outras da tela. O crédito vem colado nela, NOMEADO e com a quantidade — e
    sem crédito nenhum a frase não aparece, porque ela existe para explicar um
    número que mudou."""
    d = _cena(tela, "barra_de_limite")
    assert "creditados por retenção" in d["credito"]
    assert "+6h" in d["credito"]
    # Sem crédito a frase é ruído, e não aparece.
    assert "creditados por retenção" not in d["sem_credito"]


# ═══ aceite 7 (+§18/12b) — duas corridas no mesmo dia, UMA navegação ═════════

def test_duas_corridas_no_mesmo_dia_viram_dois_blocos_num_so_mecanismo(tela):
    """Decisão 42: a `sequencia` existe justamente para o dia com mais de uma
    corrida. A faixa desenha UM bloco por corrida, sem agrupar por data —
    agrupar esconderia a primeira madrugada depois de um redisparo às 5h, que é
    exatamente o ciclo que o operador quer ver.

    E trocar aplica a LENTE (`?corrida={id}`), nunca a data: é o que impede as
    duas de se sobreporem no mesmo canvas. O `title` de cada bloco distingue as
    duas por SEQUÊNCIA em português ("2ª corrida de 05/08"), sem `#N`
    (Decisão 74)."""
    d = _cena(tela, "dia_com_varias_corridas")
    assert d["blocos"] == 2, d["blocos"]
    assert d["titulos"] == ["2ª corrida de 05/08 · em andamento · aberta 05:20",
                            "corrida de 05/08 · concluída · aberta 01:10"]
    for t in d["titulos"]:
        assert "#" not in t
    # Clicar no bloco troca de CORRIDA (o id), não de data.
    assert d["trocou_para"] == [12]


def test_o_dia_com_varias_corridas_manda_escolher_uma_em_vez_de_ficar_mudo(tela):
    """Pendência 12b da §18, que é desta fase.

    Quando o operador navega por DATA e aquele dia teve mais de uma corrida, a
    API OMITE o bloco `corrida` de propósito — descrever uma corrida sobre a
    lista do dia inteiro é a mesma mentira que a F4 matou — e manda
    `corridas_no_dia: N`. Até aqui o front só deixava de mostrar a faixa:
    honesto, e MUDO. O operador via o canvas do dia sem faixa e não tinha como
    saber que estava olhando duas madrugadas empilhadas no mesmo desenho."""
    d = _cena(tela, "dia_com_varias_corridas")
    assert d["diz_quantas"] is True, d["texto"]
    assert d["manda_escolher"] is True, d["texto"]
    assert "mistura" in d["texto"], (
        "a frase não diz que o DESENHO abaixo mistura as duas — sem isso o "
        "operador lê o canvas do dia como se fosse de um ciclo só")
    # E ela não vaza para a lente sem ciclo nenhum: lá o texto é o de sempre.
    assert "este dia teve" not in d["mudo"]
    assert "nenhuma corrida registrada" in d["mudo"]


# ═══ aceite 9 — um clique até o problema, sem sair da lente ══════════════════

def test_clicar_numa_linha_de_travando_pede_o_realce_do_pipeline_certo(tela):
    """Um clique até o problema (§9.5), a metade que mora no PAINEL: tanto o
    corpo da linha quanto o botão `realçar cadeia` chamam `onFocar` com o nome
    do pipeline daquela linha — e não com o primeiro da lista, que é o defeito
    clássico de handler montado fora do `map`.

    ⚠️ O que este teste **não** prova, de propósito: que o editor centraliza o
    nó e não troca de modo. Isso é do `focarPipeline` do `MalhaEditor`, que só
    existe montado com o React Flow, e tem régua própria em
    `test_malhas_f10_painel.py::test_clicar_numa_linha_acende_a_cadeia_e_
    centraliza_sem_sair_da_lente`. Dizer aqui que "centraliza" seria o docstring
    contradizendo o cenário — o modo de falso verde da F9.

    E a linha carrega o RAIO (Decisão 63): `↳ falhou: CARGA_A` não diz se atrás
    dela há 1 ou 17 pipelines parados, nem se algum é `ALTA`, que é exatamente
    o que decide acordar alguém."""
    d = _cena(tela, "um_clique_ate_o_problema")
    # Dois cliques (a linha e o botão), os dois no MESMO pipeline.
    assert d["focados"] == ["CARGA_A", "CARGA_A"]
    assert "4 pipelines parados atrás (1 de criticidade alta)" in d["texto"]
    assert "ALTA" in d["texto"]                       # o chip de criticidade
    # De quem o `nao_liberou` espera — a resposta do MESMO predicado do motor.
    assert "esperando CARGA_A" in d["texto"]


def test_as_quatro_classes_nunca_viram_um_contador_unico_de_pendentes(tela):
    """Decisão 21/§9.15#10: `falhou`, `nao_liberou`, `nao_partiu` e `orfa` são
    problemas com DONOS diferentes e AÇÕES diferentes. Somá-los em "3
    pendentes" é a simplificação que apaga a única informação acionável.

    A prova é por AÇÃO, não por texto: `falhou` ganha `reexecutar`,
    `nao_liberou` não ganha (reexecutar quem só espera não conserta nada), e
    `nao_partiu` não vira sequer linha vermelha — às 01:10 ele é o estado
    normal de todo membro de toda corrida recém-aberta."""
    d = _cena(tela, "um_clique_ate_o_problema")
    assert not re.search(r"\d+\s+pendentes", d["texto"]), d["texto"]
    falhou, nao_liberou, nao_partiu = d["botoes_por_linha"]
    assert falhou == 2, "o `falhou` perdeu `realçar cadeia` ou `reexecutar`"
    assert nao_liberou == 1, "o `nao_liberou` ganhou um `reexecutar` que não "\
        "conserta nada — quem espera não tem o que reexecutar"
    assert nao_partiu == 0, "`nao_partiu` virou linha de alarme"
    assert "ainda não começou" in d["texto"]           # ele aparece, quieto


# ═══ aceite 10 — `↻ reexecutar` com a frase do efeito, ou não existe ═════════

def test_reexecutar_carrega_a_frase_do_efeito_na_corrida_em_voo(tela):
    """Decisão 65: o gesto mais delicado do modelo não pode virar um clique de
    3h no escuro. A frase vem no próprio botão, ANTES do clique, e diz as duas
    coisas que mudam por baixo do operador: em qual corrida a reexecução entra
    e que o relógio de fechamento **não** reinicia por este gesto."""
    d = _cena(tela, "um_clique_ate_o_problema")
    assert d["rerun"] == ["CARGA_A"], "o clique não chamou a prévia"
    frase = d["title_reexecutar"][0]
    assert "entra na corrida" in frase
    assert "NÃO reinicia" in frase


def test_sem_a_frase_o_botao_de_reexecutar_nao_existe(tela):
    """A outra metade da Decisão 65, e a que importa: "sem a frase, o botão não
    existe" — não é um botão desabilitado, não é um botão com `title` genérico.

    Sem ciclo ABERTO em foco a frase não pode ser escrita com certeza, o editor
    não passa o callback, e a linha fica só com `realçar cadeia`."""
    d = _cena(tela, "reexecutar_sem_frase_nao_existe")
    assert d["botoes"] == 0, d["texto"]
    assert "realçar cadeia" in d["texto"], (
        "sumiu o gesto que continua valendo — a linha ficou sem ação nenhuma")


# ═══ aceite 11 — a aresta de quem espera ≠ "não rodou" ══════════════════════

def test_a_aresta_de_quem_espera_deixa_de_ser_igual_a_nao_rodou(tela):
    """"Não rodou" tem DOIS rostos no desenho, e a aresta de quem espera não
    pode ser igual a nenhum dos dois:

      • predecessor pronto e o destino sem linha nenhuma → azul ANIMADO, "a
        corrida está avançando aqui". Era exatamente onde
        `AGUARDANDO_DEPENDENCIA` caía, porque `estadoDoPipeline` devolvia
        `null`: a tela prometia MOVIMENTO em cima de um pipeline parado;
      • nenhuma ponta com linha → trecho inerte, o cinza da Montagem.

    O estado próprio é âmbar tracejado e **não anima** — ele é, por definição,
    o trecho parado."""
    d = _cena(tela, "aresta_de_quem_espera")
    assert d["estado_de_quem_espera"] == "esperando"
    assert d["estado_da_aresta"] == "esperando"
    assert d["igual_a_avancando"] is False
    assert d["igual_a_inerte"] is False
    assert d["espera"]["style"]["strokeDasharray"]
    assert d["espera"]["animated"] is False, (
        "a aresta de quem espera voltou a animar — animação sobre espera é a "
        "tela prometendo movimento que não está acontecendo")
    assert d["avancando"]["animated"] is True     # o contraste continua vivo


def test_a_aresta_diz_por_extenso_o_que_a_cor_dela_significa(tela):
    """Cor nunca é canal único nesta casa. `ROTULO_FLUXO` estava DECLARADO e
    não era consumido em lugar nenhum do front: a cor da linha era a única
    coisa a dizer o que ela significava, ilegível para quem não distingue âmbar
    de vermelho. O rótulo acessível da aresta sai de lá, e é o mesmo texto da
    legenda do rodapé."""
    d = _cena(tela, "aresta_de_quem_espera")
    assert d["rotulo"] == "esperando outro pipeline"
    assert d["aria"] == "CARGA_A → CARGA_C: esperando outro pipeline"
    legenda = (RAIZ / "ui-react" / "src" / "components" / "malhas"
               / "MalhaEditor.tsx").read_text(encoding="utf-8")
    assert "ROTULO_FLUXO.esperando" in legenda, (
        "a legenda do rodapé não bebe de ROTULO_FLUXO — desenho e legenda "
        "passam a poder divergir de vocabulário")


# ═══ aceite 8 — malha SEM nó Fim: o evento do ciclo na aba `Eventos` ═════════

def _malha_sem_no_fim(client, db):
    """A malha das 3 em 4: membros e nenhum componente. Sem nó Fim, o evento do
    ciclo não tem nó para morar — ele mora no marcador `#corrida:{id}`."""
    return _corrida_em_cadeia(client, db)


def test_malha_sem_no_fim_leva_o_evento_do_ciclo_para_a_aba_eventos(client, auth):
    """Decisão 49, e o aceite literal da fase.

    São **3 de 4** malhas no dev. O painel só exibe evento cuja chave resolve
    para um nó DESTA malha ou para um membro dela; qualquer outra chave é um
    `continue` silencioso. Sem o resolvedor do marcador, o evento MAIS GRAVE do
    produto — a malha que falhou — não apareceria exatamente na tela em que se
    olha às 3h, e numa malha sem nó Fim ele não tem outra porta."""
    db = FakeDb(pipelines=_pipes())
    with _patch(db), _patch_agora():
        c = _malha_sem_no_fim(client, db)
        assert not [n for n in db.nos.values()
                    if n.get("malha") == "M1" and n.get("tipo") == "fim"], \
            "o cenário ganhou um nó Fim e deixou de provar o caso das 3 em 4"
        db.eventos.append({
            "pipeline_name": malhas_router.MARCADOR_CORRIDA.format(c["id"]),
            "data_referencia": ODATE, "tipo": "MALHA_FALHOU",
            "detectado_em": AGORA_BANCO - timedelta(minutes=52),
            "detalhe": "malha M1 falhou", "notificado_em": None})
        painel = client.get(f"/malhas/M1/execucao?corrida={c['id']}").json()
    assert [e["tipo"] for e in painel["eventos_corrida"]] == ["MALHA_FALHOU"]
    # E ele NÃO vaza para as outras duas listas: o sujeito do evento é a
    # corrida, e a corrida não é um pipeline nem um nó.
    assert malhas_router.MARCADOR_CORRIDA.format(c["id"]) not in \
        [e["pipeline_name"] for e in painel["eventos"]]
    assert painel["eventos_no"] == []


def test_o_marcador_de_OUTRA_corrida_nao_entra_na_aba_desta(client, auth):
    """O outro lado do resolvedor, e ele é o que impede a mentira nova: o
    marcador é `#corrida:{id}`, e o `{id}` é o da LENTE. Aceitar qualquer
    marcador faria a corrida das 05:20 exibir o `MALHA_FALHOU` da corrida da
    01:10 — o mesmo defeito que a faixa da F4 matou, reaberto pela porta dos
    eventos, e agora com data igual (as duas são do mesmo ODATE)."""
    db = FakeDb(pipelines=_pipes())
    with _patch(db), _patch_agora():
        c = _malha_sem_no_fim(client, db)
        db.eventos.append({
            "pipeline_name": malhas_router.MARCADOR_CORRIDA.format(c["id"] + 77),
            "data_referencia": ODATE, "tipo": "MALHA_FALHOU",
            "detectado_em": AGORA_BANCO - timedelta(minutes=52),
            "detalhe": "de outra corrida", "notificado_em": None})
        painel = client.get(f"/malhas/M1/execucao?corrida={c['id']}").json()
    assert painel["eventos_corrida"] == []
    # E ele não cai em nenhuma das outras listas: chave que não resolve some.
    assert all("#corrida" not in e["pipeline_name"] for e in painel["eventos"])


def test_o_marcador_de_no_de_OUTRA_malha_continua_sem_aparecer(client, auth):
    """A regra que já valia (F14) e que o resolvedor novo não pode afrouxar:
    `#no:{id}` de nó que não é desta malha não aparece aqui. Se ele passasse, o
    painel de uma malha exibiria o evento do Fim de outra — a mesma família de
    mentira, com a chave certa e a malha errada."""
    db = FakeDb(pipelines=_pipes())
    with _patch(db), _patch_agora():
        c = _malha_sem_no_fim(client, db)
        _monta_malha(client, "M2", ["VIVO"])
        no_alheio = _cria_no(client, "M2", "fim")
        db.eventos.append({
            "pipeline_name": f"#no:{no_alheio}", "data_referencia": ODATE,
            "tipo": "MALHA_CONCLUIDA",
            "detectado_em": AGORA_BANCO - timedelta(minutes=10),
            "detalhe": "fim da M2", "notificado_em": None})
        painel = client.get(f"/malhas/M1/execucao?corrida={c['id']}").json()
    assert painel["eventos_no"] == []
    assert painel["eventos_corrida"] == []


# ═══ o RAIO não pode enxergar fora DESTA corrida (Decisão 63 × Decisão 52) ══

def test_o_raio_nao_atravessa_o_snapshot_da_corrida_de_ONTEM(client, auth):
    """⚠️ Este teste nasceu de uma MUTAÇÃO QUE SOBREVIVEU.

    `test_o_raio_nao_atravessa_a_fronteira_da_corrida` afirma no docstring que
    o raio não sai do snapshot — mas o cenário dele (um pipeline de fora
    dependendo de um membro) é garantido pelo `FROM etl_malha_execucao_membro`,
    e não pelo recorte que o docstring descreve. Apagar
    `mm.malha_execucao_id = ?` da consulta do grafo deixava a suíte inteira
    verde. É o modo de falso verde da F9 — o cenário contradiz o próprio
    docstring — e ele deixava a guarda mais importante da consulta sem régua.

    O cenário que a exercita é banal e acontece toda semana: **um pipeline sai
    da malha entre ontem e hoje**. `etl_pipeline_dependencia` é GLOBAL (não tem
    corrida), então a aresta `D → C` continua cadastrada mesmo com `C` fora do
    snapshot de hoje. Sem o recorte, o grafo puxa o `C` de ONTEM, a travessia
    atravessa por ele e chega em `D` — e a linha de `Travando` diz *"2 pipelines
    parados atrás"* onde há **1**.

    Inflar o raio não é erro de arredondamento: é o número que decide se alguém
    é acordado às 3h."""
    db = FakeDb(pipelines=_pipes())
    with _patch(db), _patch_agora():
        _monta_malha(client, "M1", ["A", "B", "C"])
        # Ontem: A, B, C e OK1. Hoje o C saiu da malha.
        ontem = db.abrir_corrida("M1", odate=ODATE,
                                 aberta_em=AGORA_BANCO - timedelta(hours=9),
                                 membros=["A", "B", "C", "OK1"],
                                 status="CONCLUIDA")
        hoje = db.abrir_corrida("M1", odate=ODATE,
                                aberta_em=AGORA_BANCO - timedelta(hours=1),
                                membros=["A", "B", "OK1"])
        assert ontem["id"] != hoje["id"]
        db.depende("B", "A")
        db.depende("C", "B")      # C não é membro de hoje
        db.depende("OK1", "C")    # …e OK1 só chega em A ATRAVÉS de C
        db.execucao("A", "FALHA", inicio=AGORA_BANCO - timedelta(minutes=30),
                    fim=AGORA_BANCO - timedelta(minutes=29), corrida=hoje["id"])
        painel = client.get(f"/malhas/M1/execucao?corrida={hoje['id']}").json()
    pend = _pendentes(painel)
    assert pend["A"]["classe"] == "falhou"
    assert pend["A"]["alcance"] == 1, (
        "o raio saiu do snapshot desta corrida: só `B` está parado atrás de "
        "`A` hoje — `OK1` só o alcança passando por `C`, que não é membro "
        f"desta corrida (pendentes: { {k: v['alcance'] for k, v in pend.items()} })")
    # E `OK1` continua sendo um pendente desta corrida — ele não sumiu da aba;
    # o que ele não é é "parado atrás de A".
    assert "OK1" in pend and pend["OK1"]["alcance"] == 0


def test_o_raio_nao_passa_por_membro_que_nao_estava_ativo_na_abertura(client,
                                                                      auth):
    """A Decisão 52 dentro do raio: o snapshot é o da ABERTURA, e um membro que
    já estava inativo quando a corrida abriu não é passagem para nada.

    ⚠️ Este teste também nasceu de mutação, e o achado é fino: as DUAS guardas
    que sustentam isto (`mm.ativo_na_abertura = 1` no `WHERE` e
    `m2.ativo_na_abertura = 1` dentro do `EXISTS`) são REDUNDANTES uma com a
    outra para este número — apagar qualquer uma sozinha não muda resposta
    nenhuma, e por isso nenhuma mutação simples as pega. Apagar **as duas**
    muda: a travessia passa a atravessar o membro inativo e chega em quem só
    era alcançável por ele.

    Redundância não é motivo para não ter régua — é motivo para a régua medir o
    FATO (o número na tela) em vez de medir uma cláusula. É o que este teste
    faz, e é por isso que ele fica verde com qualquer uma das duas guardas de
    pé e vermelho sem as duas."""
    db = FakeDb(pipelines=_pipes())
    with _patch(db), _patch_agora():
        _monta_malha(client, "M1", ["A", "B", "C"])
        c = db.abrir_corrida("M1", odate=ODATE,
                             aberta_em=AGORA_BANCO - timedelta(hours=1),
                             membros=["A", "B", "C"])
        # `B` já estava INATIVO no cadastro quando a corrida abriu: ele entra no
        # snapshot com a marca, e fora da contagem (Decisão 52).
        for m in db.membros_corrida:
            if m["malha_execucao_id"] == c["id"] and m["pipeline_name"] == "B":
                m["ativo_na_abertura"] = 0
        db.depende("B", "A")
        db.depende("C", "B")      # `C` só alcança `A` ATRAVÉS do inativo `B`
        db.execucao("A", "FALHA", inicio=AGORA_BANCO - timedelta(minutes=30),
                    fim=AGORA_BANCO - timedelta(minutes=29), corrida=c["id"])
        painel = client.get(f"/malhas/M1/execucao?corrida={c['id']}").json()
    pend = _pendentes(painel)
    assert "B" not in pend, "o membro inativo na abertura virou pendente"
    assert pend["A"]["alcance"] == 0, (
        "o raio atravessou um membro que não estava ativo na abertura — `C` "
        "não está parado por `A` nesta corrida")
    assert painel["corrida"]["membros_total"] == 2      # Decisão 52, o mesmo eixo


# ═══ a guarda contra o falso verde da F8 — o dublê não inventa dado ══════════

def test_o_duble_do_front_nao_inventa_campo_que_o_servidor_nao_manda(tela, client,
                                                                     auth):
    """⚠️ O modo de falso verde que a F8 desta mesma spec já pagou: **dublê que
    fabrica dado que o servidor real nunca produz**. A bancada fica verde, a
    faixa fica em branco na madrugada, e ninguém descobre até o incidente.

    A régua é bilateral de propósito:

      • campo NO DUBLÊ e não no payload = a bancada está provando uma tela que
        o servidor não alimenta;
      • campo no PAYLOAD e não no dublê = a bancada nunca exercitou aquele
        campo, e o front pode estar lendo `undefined` como zero justamente na
        janela entre o `dist/` (etapa 3 do deploy) e a `api/` (etapa 7).
    """
    db = FakeDb(pipelines=_pipes())
    with _patch(db), _patch_agora():
        c = _corrida_em_cadeia(client, db)
        painel = client.get(f"/malhas/M1/execucao?corrida={c['id']}").json()
    real = set(painel["corrida"])
    duble = set(tela["__fixture_corrida"])
    assert duble == real, (
        f"só no dublê: {sorted(duble - real)}; só no servidor: "
        f"{sorted(real - duble)}")
    assert set(tela["__fixture_pendente"]) == set(_pendentes(painel)["A"])


# ═══ revisão adversarial da F10 — três defeitos achados e travados ══════════

def test_o_banner_de_hold_nao_depende_de_haver_ciclo(tela):
    """Decisão 66/2 — a condição é `retido_em` em algum nó, e NADA MAIS.

    O banner nasceu dentro do ramo que só existe com `corrida`, e isso o
    apagava exatamente no caso que ele existe para cobrir: **Início SEGURADO**.
    O Início segurado é o que IMPEDE a corrida de abrir — então, no momento em
    que o operador mais precisa ler "a malha está parada porque alguém a
    segurou às 02:40", não havia ciclo nenhum e o banner não saía. A tela dizia
    "nenhuma corrida registrada nesta lente" e calava sobre o cadeado.

    É também o que torna a Decisão 66/2 testável com `malha_corrida_ativa = 0`
    (o estado do dev e o do dia do deploy), onde não existe corrida no banco."""
    d = _cena(tela, "hold_com_e_sem_ciclo")
    assert "1 nó segurado desde 02:40 (por C123456)" in d["sem_ciclo"]
    assert "1 nó segurado desde 02:40 (por C123456)" in d["com_ciclo"]
    # O gesto vem junto: soltar dali mesmo, sem sair da lente.
    assert d["botao_soltar_sem_ciclo"] == 1 and d["soltou"] == [5]
    # A CONSEQUÊNCIA muda com o estado, porque as duas frases são diferentes:
    # sem ciclo o que está travado é a PARTIDA, não o avanço.
    assert "não parte no horário agendado" in d["sem_ciclo"]
    assert "a corrida não avança" in d["com_ciclo"]
    # E o contraste: sem nó segurado não há banner nenhum.
    assert "segurado" not in d["sem_no_segurado"]


def test_o_carimbo_de_frescor_cala_quando_nao_houve_resposta(tela):
    """Decisão 60, pelo avesso.

    `respostaEm` é o `dataUpdatedAt` do react-query, e ele vale **0** enquanto
    nenhuma resposta chegou — inclusive DEPOIS DE UM ERRO, quando a faixa
    continua na tela (`isLoading` já é `false`). Carimbar esse zero produzia
    "⚠ dado sem atualizar há 466702h": o carimbo de frescor mentindo sobre o
    próprio frescor, que é o defeito que a Decisão 60 existe para matar."""
    d = _cena(tela, "carimbo_sem_resposta")
    assert "atualizado" not in d["sem_resposta"]
    assert "dado sem atualizar" not in d["sem_resposta"]
    assert "466" not in d["sem_resposta"]
    # E o carimbo continua funcionando quando HÁ resposta — nos dois estados.
    assert "· atualizado agora" in d["com_resposta"]
    assert "⚠ dado sem atualizar há 5 min" in d["velho"]


def test_nem_orfa_nem_DagRun_chegam_ao_texto_do_encerramento():
    """Decisão 74 — o aceite verificável da §9.11, na frase que o operador lê
    às 3h antes de apertar o botão mais delicado da tela.

    A confirmação de `ABERTA · SEM_PROGRESSO` dizia *"é o sintoma de execução
    órfã (o DagRun morreu sem fechar a linha)"*: dois nomes de máquina numa
    frase só, num texto de decisão. O fato é o mesmo e cabe em português —
    *"um pipeline que terminou sem registrar o fim"*, que é a tradução que a
    própria §9.11 fixa para `orfa`."""
    fonte = (RAIZ / "ui-react" / "src" / "components" / "malhas"
             / "CabecalhoCorrida.tsx").read_text(encoding="utf-8")
    visivel = "\n".join(l for l in fonte.splitlines()
                        if not l.lstrip().startswith(("//", "*", "/*")))
    for termo in ("DagRun", "órfã", "dag_run", "quiescência", "ODATE"):
        assert termo not in visivel, f"'{termo}' virou texto de interface"
    assert "terminou sem registrar o fim" in visivel
