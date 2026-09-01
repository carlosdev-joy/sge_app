"""A sequência do Workflow em Busca & Vendas × a estrutura definida.

A ordem e os nomes dos cards não são detalhe estético: são a sequência que a
operação segue. Alguém que insira um status novo "no fim da lista, para não
mexer no resto" quebra a leitura da tela sem quebrar nada que dê erro.

Desde 2026-08-31 a sequência tem 8 cards e mora em `caixa/lib/workflow.ts` —
fonte ÚNICA, lida pelos dois pontos de "Workflow" da home:

  • `ProposalWorkflowSheet.tsx` — o painel do botão no cabeçalho;
  • `InlineWorkflow.tsx`        — o card colapsável abaixo da busca.

Antes cada um tinha a sua lista e o seu mock. Duas verdades na mesma tela é o
defeito que o bloco 5 daqui existe para impedir que volte.

O que estes testes prendem:

  1. **A ordem e os nomes**, exatamente como pedidos.
  2. **Todo card tem sinal**, e o sinal é um dos três — o círculo é o que diz
     se aquele número exige ação, atenção ou nada.
  3. **A contagem é DERIVADA da sequência**, nunca um dicionário à mão: a
     versão anterior fazia `if (counts[status] !== undefined) counts[status]++`
     sobre um dicionário escrito à parte, e o status esquecido ali fazia a
     proposta ser DESCARTADA sem erro — o card nascia zerado com dado na base,
     e isso passa por "ainda não tem proposta nesse status".
  4. **Nenhuma proposta órfã e nenhum card permanentemente zerado.**
  5. **Os dois componentes leem da mesma fonte.**
  6. **Sub-filtro só sobre propostas que têm o campo** — a comparação é por
     igualdade, e a proposta sem o campo some da tela sem aviso nenhum.

Leitura por regex sobre o TS/TSX: não há runtime de teste de front neste repo
para esta tela, e as listas são literais estáticos.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
CAIXA = RAIZ / "ui-react" / "src" / "caixa"
FONTE = CAIXA / "lib" / "workflow.ts"
INLINE = CAIXA / "components" / "InlineWorkflow.tsx"
SHEET = CAIXA / "components" / "ProposalWorkflowSheet.tsx"

# A sequência pedida, na ordem, com o sinal de cada etapa.
#   aviso    (amarelo)  — parada esperando alguém agir
#   perda    (vermelho) — negócio perdido
#   positivo (verde)    — avançou no funil
SEQUENCIA_PEDIDA = [
    ("pending_signature",        "Pendentes de Assinatura", "aviso"),
    ("awaiting_payment",         "Pendentes de Pagamento",  "aviso"),
    ("paid",                     "Assinadas e Pagas",       "positivo"),
    ("in_analysis",              "Em Análise",              "aviso"),
    ("emission_sent",            "Emitidas",                "positivo"),
    ("declined",                 "Rejeitadas",              "perda"),
    ("refund_scheduled",         "Devoluções de Prêmio",    "aviso"),
    ("sensitization_monitoring", "Sensibilizações",         "positivo"),
]


def _fonte() -> str:
    return FONTE.read_text(encoding="utf-8")


def _cards() -> list[tuple[str, str, str]]:
    """(value, label, sinal) de cada etapa, na ordem do arquivo."""
    bloco = re.search(
        r"export const SEQUENCIA_WORKFLOW: EtapaWorkflow\[\] = \[\s*(.*?)\n\];",
        _fonte(), re.S)
    assert bloco, "SEQUENCIA_WORKFLOW não encontrada em lib/workflow.ts"
    itens = re.findall(
        r'\{\s*value:\s*"([^"]+)",\s*label:\s*"([^"]+)",\s*sinal:\s*"([^"]+)"\s*\}',
        bloco.group(1))
    assert itens, "nenhuma etapa lida — a regex ficou para trás"
    return itens


def _propostas() -> list[str]:
    """Cada linha do mock, para ler status e sub-status."""
    bloco = re.search(r"export const propostasWorkflow: PropostaWorkflow\[\] = \[(.*?)\n\];",
                      _fonte(), re.S)
    assert bloco, "mock de propostas não encontrado"
    return [l for l in bloco.group(1).splitlines() if 'status:' in l and l.strip().startswith("{")]


# ═══════════ 1. a ordem e os nomes ══════════════════════════════════════════

def test_a_sequencia_segue_a_estrutura_pedida():
    """Ordem E nomes. Um card fora de lugar quebra a leitura do fluxo sem
    quebrar nada que dê erro."""
    atual = [(v, l) for v, l, _s in _cards()]
    esperado = [(v, l) for v, l, _s in SEQUENCIA_PEDIDA]
    assert atual == esperado


def test_a_sequencia_nao_ganhou_nem_perdeu_card():
    assert len(_cards()) == len(SEQUENCIA_PEDIDA) == 8


def test_todas_as_propostas_e_a_primeira_opcao_do_filtro():
    """"Todas as Propostas" é a opção do Select, não um card — e precisa vir
    primeiro, senão a tela abre filtrada."""
    for arquivo in (INLINE, SHEET):
        fonte = arquivo.read_text(encoding="utf-8")
        primeira = re.search(r'<option value="all">([^<]+)</option>', fonte)
        assert primeira, f"{arquivo.name}: opção 'all' sumiu do filtro"


# ═══════════ 2. o sinal de cada card ════════════════════════════════════════

@pytest.mark.parametrize("value,label,sinal", SEQUENCIA_PEDIDA)
def test_cada_card_tem_o_sinal_pedido(value, label, sinal):
    atual = {v: s for v, _l, s in _cards()}
    assert atual[value] == sinal, f"{label} deveria sinalizar '{sinal}'"


def test_nenhum_card_fica_sem_sinal():
    """Card sem sinal não diz se o número é bom ou ruim — e a tela existe
    justamente para responder isso de relance."""
    sem = [v for v, _l, s in _cards() if not s]
    assert not sem, f"cards sem sinal: {sem}"


def test_a_cor_nunca_vai_sozinha():
    """Regra da casa: cor é reforço, nunca o único portador da informação.

    TRÊS camadas — a forma do ícone (triângulo, seta caindo, certo), que
    funciona até impressa em preto e branco; o `aria-label`, para leitor de
    tela; e o `<title>`, para o tooltip do navegador.
    """
    fonte = INLINE.read_text(encoding="utf-8")
    assert "SINAL_TEXTO" in fonte
    assert "aria-label={SINAL_TEXTO[status.sinal]}" in fonte
    assert "<title>{SINAL_TEXTO[status.sinal]}</title>" in fonte


def test_cada_sinal_tem_icone_proprio():
    """Três sinais, três formas distintas. Dois sinais com o mesmo ícone
    deixariam a cor como única diferença — exatamente o que a regra acima
    existe para impedir."""
    bloco = re.search(r"const SINAL_ICONE.*?\};", INLINE.read_text(encoding="utf-8"), re.S)
    assert bloco, "SINAL_ICONE não encontrado"
    icones = re.findall(r"(\w+):\s*(\w+),", bloco.group(0))
    assert len(icones) == 3, f"esperados 3 sinais, achei {icones}"
    formas = [i[1] for i in icones]
    assert len(set(formas)) == 3, f"ícones repetidos entre sinais: {formas}"


def test_o_icone_e_discreto():
    """O número é a informação principal do card; o sinal qualifica. Ícone
    grande demais inverteria a hierarquia — e foi o pedido explícito."""
    assert "h-3.5 w-3.5" in INLINE.read_text(encoding="utf-8"), (
        "o ícone do sinal deveria ser pequeno (14px)")


def test_o_sinal_fica_no_canto_inferior_direito():
    """Padrão de card: posição fixa, o olho aprende onde procurar. E resolve
    um efeito colateral do layout anterior — número e ícone centralizados
    JUNTOS faziam o número mudar de lugar conforme tivesse 1 ou 2 dígitos."""
    fonte = INLINE.read_text(encoding="utf-8")
    assert "absolute bottom-1.5 right-1.5" in fonte
    assert 'className={`relative p-2 rounded-lg border-2' in fonte, (
        "sem `relative` no botão, o absolute se ancora no ancestral errado e "
        "o ícone vaza para fora do card")


def test_o_numero_fica_sozinho_no_centro():
    fonte = INLINE.read_text(encoding="utf-8")
    assert 'className="text-xl font-bold text-center mt-1 text-ink"' in fonte
    assert "flex items-center justify-center gap-2 mt-1" not in fonte


def test_o_sinal_nao_invade_a_faixa_do_rotulo():
    """O rótulo é o elemento de altura variável do card — "Pendentes de
    Assinatura" quebra em duas linhas, "Emitidas" não. Sinal no TOPO passaria
    por baixo do rótulo mais longo, sumindo justamente no card cujo nome mais
    precisa ser lido."""
    assert "absolute top-" not in INLINE.read_text(encoding="utf-8"), (
        "sinal na faixa do rótulo: risco de colisão com os nomes longos")


# ═══════════ 3. a contagem é derivada, não escrita à mão ════════════════════

def test_a_contagem_nasce_da_sequencia():
    """`contarPorStatus` zera uma chave POR ETAPA da sequência antes de somar.
    Enquanto for assim, é impossível esquecer um status e ver o card zerado
    com dado na base — que era o defeito silencioso do dicionário literal."""
    fonte = _fonte()
    bloco = re.search(r"export function contarPorStatus.*?\n\}", fonte, re.S)
    assert bloco, "contarPorStatus não encontrada"
    assert "SEQUENCIA_WORKFLOW.forEach" in bloco.group(0), (
        "a contagem voltou a depender de uma lista de chaves à parte")


def test_nenhum_componente_conta_por_conta_propria():
    """Contagem duplicada em componente é a porta de entrada da divergência:
    o card mostra um número e o filtro, outro."""
    for arquivo in (INLINE, SHEET):
        fonte = arquivo.read_text(encoding="utf-8")
        assert "contarPorStatus" in fonte, f"{arquivo.name} não usa contarPorStatus"
        assert "const counts: Record<string, number> = {" not in fonte, (
            f"{arquivo.name} voltou a montar o dicionário de contagem à mão")


# ═══════════ 4. órfãs e cards zerados ═══════════════════════════════════════

def test_nenhuma_proposta_fica_sem_card():
    """Proposta em status sem card não aparece em card nenhum e some de TODOS
    os filtros — só existe em "Todas as Propostas", onde ninguém procura por
    status."""
    no_mock = {re.search(r'status:\s*"(\w+)"', l).group(1) for l in _propostas()}
    com_card = {v for v, _l, _s in _cards()}
    orfas = no_mock - com_card
    assert not orfas, (
        f"propostas em status sem card na sequência: {sorted(orfas)} — elas "
        f"somem de todos os filtros. Converta para um status da sequência ou "
        f"adicione o card.")


def test_todo_card_tem_ao_menos_uma_proposta():
    """Card permanentemente zerado não deixa ver o layout nem exercitar o
    filtro. Quando os dados reais entrarem, este teste passa a valer sobre a
    consulta — e um card sempre em zero vira pergunta, não paisagem."""
    no_mock = {re.search(r'status:\s*"(\w+)"', l).group(1) for l in _propostas()}
    faltam = {v for v, _l, _s in _cards()} - no_mock
    assert not faltam, f"cards sem nenhuma proposta: {sorted(faltam)}"


# ═══════════ 5. uma fonte só para os dois "Workflow" da home ════════════════

@pytest.mark.parametrize("arquivo", [INLINE, SHEET], ids=["inline", "sheet"])
def test_os_dois_workflows_leem_a_mesma_fonte(arquivo):
    """Regressão do que existia até 2026-08-31: o painel do botão tinha 9
    status próprios ("Ag. Link Pagamento", "Cotação", "Rascunho") e 13
    propostas que não eram as da tela, enquanto o card inline tinha outros 10.
    Mesma tela, dois vocabulários."""
    fonte = arquivo.read_text(encoding="utf-8")
    assert "SEQUENCIA_WORKFLOW" in fonte and "propostasWorkflow" in fonte, (
        f"{arquivo.name} não lê a sequência de lib/workflow.ts")
    assert not re.search(r"^const (statusInfo|mockWorkflowProposals)", fonte, re.M), (
        f"{arquivo.name} voltou a declarar a própria lista de status/propostas")


def test_a_sequencia_nao_tem_status_orfao_de_rotulo_ou_cor():
    """Selo sem rótulo cai no nome técnico do status na tela ("in_analysis"),
    e sem cor cai no cinza de "status desconhecido"."""
    fonte = _fonte()
    for mapa in ("STATUS_LABEL_CURTO", "STATUS_COR"):
        bloco = re.search(rf"export const {mapa}.*?\n\}};", fonte, re.S)
        assert bloco, f"{mapa} não encontrado"
        declarados = set(re.findall(r"^\s+(\w+):", bloco.group(0), re.M))
        faltam = {v for v, _l, _s in _cards()} - declarados
        assert not faltam, f"status sem entrada em {mapa}: {sorted(faltam)}"


# ═══════════ 6. sub-filtro × proposta sem o campo ═══════════════════════════
# O filtro de sub-status compara IGUALDADE: proposta sem o campo some ao
# filtrar por qualquer opção, aparecendo só em "Todos os sub-status". Some da
# tela sem nenhum aviso — o defeito que já mordeu na devolução.

def _sub_filtros() -> dict[str, str]:
    """{status: campo} lido do mapa SUB_FILTRO do InlineWorkflow."""
    bloco = re.search(r"const SUB_FILTRO:.*?\n\};", INLINE.read_text(encoding="utf-8"), re.S)
    assert bloco, "SUB_FILTRO não encontrado"
    return dict(re.findall(r"(\w+):\s*\{\s*campo:\s*\"(\w+)\"", bloco.group(0)))


def test_o_sub_filtro_so_aponta_para_status_da_sequencia():
    com_card = {v for v, _l, _s in _cards()}
    fora = set(_sub_filtros()) - com_card
    assert not fora, f"sub-filtro para status que não tem card: {sorted(fora)}"


def test_toda_proposta_de_status_com_sub_filtro_tem_o_campo():
    for status, campo in _sub_filtros().items():
        linhas = [l for l in _propostas() if f'status: "{status}"' in l]
        assert linhas, f"nenhuma proposta em {status} no mock"
        sem = [l for l in linhas if f"{campo}:" not in l]
        assert not sem, (
            f"{len(sem)} proposta(s) em '{status}' sem `{campo}` — somem ao "
            f"filtrar por qualquer sub-status")


def test_a_rejeitada_ja_nasce_com_o_sub_status_da_devolucao():
    """O status do card não é só o do mock: "Gerenciar Devolução" move a
    proposta de `declined` para `refund_scheduled` EM TEMPO DE EXECUÇÃO. Ela
    chega ao card 7 e, sem `refundSubStatus`, some no primeiro filtro de
    sub-status — o mesmo defeito de sempre, agora pela porta do estado local.
    """
    campo = _sub_filtros().get("refund_scheduled")
    assert campo, "refund_scheduled perdeu o sub-filtro"
    origem = [l for l in _propostas() if 'status: "declined"' in l]
    assert origem, "nenhuma proposta rejeitada no mock"
    sem = [l for l in origem if f"{campo}:" not in l]
    assert not sem, (
        f"{len(sem)} proposta(s) rejeitada(s) sem `{campo}` — ao serem movidas "
        f"para a devolução, somem do filtro de sub-status")


def test_o_movimento_de_status_so_aponta_para_card_da_sequencia():
    """Estado local que aponta para status sem card faz a proposta desaparecer
    da tela no clique do botão — o pior momento para sumir."""
    fonte = INLINE.read_text(encoding="utf-8")
    destinos = set(re.findall(r'\[\w+(?:\.id)?\]:\s*"(\w+)"', fonte))
    com_card = {v for v, _l, _s in _cards()}
    fora = destinos - com_card
    assert not fora, f"movimento para status sem card: {sorted(fora)}"


def test_o_valor_do_card_e_um_premio_mensal():
    """O valor ao lado do produto é o PRÊMIO (a mensalidade) — é `VLR_PREMIO`
    nas propostas da carga, e a coluna da busca já se chama "Prêmio".

    As propostas de exemplo traziam valores na casa dos milhares (R$ 1.750,00
    para um seguro de vida), que são ordem de grandeza de renda ou de capital
    segurado. Resultado: a mesma tela mostrava mensalidade de verdade num card
    e valor de renda no card ao lado, sem nada indicando a diferença.

    O teto de R$ 1.000 é generoso de propósito: não existe prêmio mensal de
    seguro de vida em quatro dígitos nesta carteira, e o que se quer barrar é a
    volta dos milhares, não afinar centavos.
    """
    valores = re.findall(r'value: "R\$ ([\d.,]+)"', FONTE.read_text(encoding="utf-8"))
    assert valores, "nenhuma proposta de exemplo com valor — o leitor quebrou?"
    altos = [v for v in valores
             if float(v.replace(".", "").replace(",", ".")) >= 1000]
    assert not altos, (
        f"{len(altos)} proposta(s) de exemplo com valor de renda/capital no lugar "
        f"do prêmio: {altos[:5]}")
