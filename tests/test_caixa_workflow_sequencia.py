"""A sequência do Workflow em Busca & Vendas × o desenho aprovado.

A ordem e os nomes dos cards não são detalhe estético: são a sequência que a
operação segue. Alguém que insira um status novo "no fim da lista, para não
mexer no resto" quebra a leitura da tela sem quebrar nada que dê erro.

O que estes testes prendem:

  1. **A ordem e os nomes**, exatamente como no desenho (sequencia_wkf.png).
  2. **Todo card tem sinal**, e o sinal é um dos três — o círculo é o que diz
     se aquele número exige ação, atenção ou nada.
  3. **Todo status do card existe no dicionário de contagem.** Este é o
     defeito silencioso da mudança: o laço que conta faz
     `if (counts[status] !== undefined) counts[status]++`, então um status
     ausente do dicionário faz a proposta ser DESCARTADA sem erro — o card
     nasce zerado com dado no mock, e isso passa por "ainda não tem proposta
     nesse status".
  4. **Todo status da sequência tem ao menos uma proposta no mock.** Card
     permanentemente zerado não deixa ver o layout nem exercitar o filtro,
     e foi por isso que os dois status novos ganharam cópias.

Leitura por regex sobre o TSX: não há runtime de teste de front neste repo
para esta tela, e as listas são literais estáticos.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
TSX = RAIZ / "ui-react" / "src" / "caixa" / "components" / "InlineWorkflow.tsx"

# A sequência do desenho, na ordem, com o sinal de cada etapa.
#   atencao  (amarelo) — parada esperando alguém agir
#   sem_acao (verde)   — seguiu o fluxo
#   acao     (vermelho)— saiu do fluxo, precisa de tratativa
SEQUENCIA_DO_DESENHO = [
    ("pending_signature",         "Aguardando Assinatura",             "atencao"),
    ("signed_proposal",           "Proposta Assinada",                 "sem_acao"),
    ("awaiting_payment",          "Aguardando Pagamento",              "atencao"),
    ("paid",                      "Propostas Pagas",                   "sem_acao"),
    ("pending_documentation",     "Pendência Documental",              "atencao"),
    ("pending_dps",               "Pendência de DPS",                  "atencao"),
    ("emission_sent",             "Propostas Emitidas",                "sem_acao"),
    ("refund_scheduled",          "Propostas Declinadas",              "acao"),
    ("return_in_progress",        "Devolução em Andamento",            "atencao"),
    ("sensitization_monitoring",  "Monitoramento de Sensibilização",   "sem_acao"),
]


def _fonte() -> str:
    return TSX.read_text(encoding="utf-8")


def _status_info() -> list[tuple[str, str, str]]:
    """(value, label, sinal) de cada entrada de statusInfo, na ordem do arquivo."""
    bloco = re.search(
        r"const statusInfo: .*?\[\s*(.*?)\n\];", _fonte(), re.S)
    assert bloco, "statusInfo não encontrado em InlineWorkflow.tsx"
    itens = re.findall(
        r'\{\s*value:\s*"([^"]+)",\s*label:\s*"([^"]+)"(?:,\s*sinal:\s*"([^"]+)")?\s*\}',
        bloco.group(1))
    assert itens, "nenhuma entrada lida de statusInfo — a regex ficou para trás"
    return itens


def _cards() -> list[tuple[str, str, str]]:
    """A sequência SEM o 'all', que é a opção do filtro, não um card."""
    return [i for i in _status_info() if i[0] != "all"]


# ═══════════ 1. a ordem e os nomes ══════════════════════════════════════════

def test_a_sequencia_segue_o_desenho():
    """Ordem E nomes. Um card fora de lugar quebra a leitura do fluxo sem
    quebrar nada que dê erro."""
    atual = [(v, l) for v, l, _s in _cards()]
    esperado = [(v, l) for v, l, _s in SEQUENCIA_DO_DESENHO]
    assert atual == esperado


def test_todas_as_propostas_e_a_primeira_opcao_do_filtro():
    """'all' precisa continuar existindo e vir primeiro: é o estado inicial
    do Select, e a tela abriria filtrada se ele saísse da frente."""
    assert _status_info()[0][0] == "all"


def test_a_sequencia_nao_ganhou_nem_perdeu_card():
    assert len(_cards()) == len(SEQUENCIA_DO_DESENHO)


# ═══════════ 2. o sinal de cada card ════════════════════════════════════════

@pytest.mark.parametrize("value,label,sinal", SEQUENCIA_DO_DESENHO)
def test_cada_card_tem_o_sinal_do_desenho(value, label, sinal):
    atual = {v: s for v, _l, s in _cards()}
    assert atual[value] == sinal, f"{label} deveria sinalizar '{sinal}'"


def test_nenhum_card_fica_sem_sinal():
    """Card sem círculo não diz se o número é bom ou ruim — e a tela existe
    justamente para responder isso de relance."""
    sem = [v for v, _l, s in _cards() if not s]
    assert not sem, f"cards sem sinal: {sem}"


def test_a_cor_nunca_vai_sozinha():
    """Regra da casa: cor é reforço, nunca o único portador da informação.
    Sem title/aria-label o círculo não existe para quem não distingue as
    cores, usa leitor de tela ou imprime a página."""
    fonte = _fonte()
    assert "SINAL_TEXTO" in fonte
    assert 'aria-label={SINAL_TEXTO[status.sinal]}' in fonte
    assert 'title={SINAL_TEXTO[status.sinal]}' in fonte


# ═══════════ 3. o defeito silencioso: contagem que descarta ═════════════════

def test_todo_status_da_sequencia_conta():
    """`if (counts[status] !== undefined) counts[status]++` DESCARTA em
    silêncio o status que não estiver no dicionário: o card nasce zerado com
    dado no mock, e isso passa por "ainda não tem proposta nesse status".
    """
    bloco = re.search(r"const counts: Record<string, number> = \{(.*?)\n  \};",
                      _fonte(), re.S)
    assert bloco, "dicionário counts não encontrado"
    declarados = set(re.findall(r"(\w+):\s*(?:0|mockWorkflowProposals\.length)",
                                bloco.group(1)))
    faltam = {v for v, _l, _s in _cards()} - declarados
    assert not faltam, (
        f"status do card ausentes em `counts`: {sorted(faltam)} — o card "
        f"apareceria SEMPRE zerado, mesmo com proposta no mock")


# ═══════════ 4. card zerado não deixa ver a tela ════════════════════════════

def test_todo_status_da_sequencia_tem_proposta_no_mock():
    """Exceto os que o desenho mostra legitimamente em zero. Card sem nenhum
    registro não permite conferir layout nem exercitar o filtro."""
    fonte = _fonte()
    com_proposta = set(re.findall(r'status:\s*"(\w+)"', fonte))
    # Devolução em Andamento aparece como 0 no próprio desenho — é o estado
    # real da operação, não um esquecimento.
    esperado_zerado = {"return_in_progress"}
    faltam = {v for v, _l, _s in _cards()} - com_proposta - esperado_zerado
    assert not faltam, (
        f"status sem nenhuma proposta no mock: {sorted(faltam)} — o card "
        f"ficaria permanentemente zerado")


def test_os_dois_status_novos_ganharam_registro():
    """Regressão direta: 'Propostas Pagas' e 'Propostas Emitidas' entraram na
    sequência sem nenhuma proposta, e foi preciso copiar duas."""
    fonte = _fonte()
    assert 'status: "paid"' in fonte
    assert 'status: "emission_sent"' in fonte


# ═══════════ 5. proposta órfã — status no mock sem card na sequência ═══════
# Regra estabelecida ao converter a `approved`: quando um card sai do
# desenho, as propostas dele não podem ficar boiando. Órfã não aparece em
# card nenhum e some de TODOS os filtros — só existe em "Todas as
# Propostas", onde ninguém procura por status.

# VAZIO, e é para continuar vazio: hoje toda proposta do mock tem card na
# sequência. As duas que estavam em `declined` — status sem card, porque
# "Propostas Declinadas" aponta para `refund_scheduled` — foram convertidas.
#
# Se alguém precisar tolerar uma órfã de novo, o nome entra aqui COM o
# motivo. Órfã declarada é decisão; órfã esquecida é defeito; as duas têm a
# mesma aparência na tela, e só este conjunto separa uma da outra.
ORFAS_CONHECIDAS: set[str] = set()


def test_nenhuma_proposta_fica_sem_card():
    fonte = _fonte()
    bloco = re.search(r"const mockWorkflowProposals.*?\n\];", fonte, re.S)
    assert bloco, "mock de propostas não encontrado"
    no_mock = set(re.findall(r'status:\s*"(\w+)"', bloco.group(0)))
    com_card = {v for v, _l, _s in _cards()}
    orfas = no_mock - com_card - ORFAS_CONHECIDAS
    assert not orfas, (
        f"propostas em status sem card na sequência: {sorted(orfas)} — elas "
        f"somem de todos os filtros e só aparecem em 'Todas as Propostas'. "
        f"Converta para um status da sequência ou adicione o card.")


def test_a_proposta_que_era_approved_virou_paga():
    """Regressão da conversão: o card 'Ass. e Sensibilizado' saiu com o
    desenho, e a proposta dele foi para 'Propostas Pagas' em vez de ficar
    órfã. Um `approved` de volta no mock recria a órfã silenciosamente."""
    fonte = _fonte()
    bloco = re.search(r"const mockWorkflowProposals.*?\n\];", fonte, re.S)
    assert 'status: "approved"' not in bloco.group(0), (
        "voltou proposta em `approved`, que não tem card na sequência")
    assert 'status: "paid"' in bloco.group(0)


def test_nao_sobrou_nenhuma_orfa_tolerada():
    """O conjunto de exceções está vazio — e cada nome que voltar a entrar
    nele precisa vir com o motivo escrito ao lado, não como conveniência
    para fazer o teste acima passar."""
    assert ORFAS_CONHECIDAS == set()


def test_as_declinadas_estao_no_card_de_declinadas():
    """Regressão: `declined` não tem card na sequência. Uma proposta ali
    some de todos os filtros e só aparece em 'Todas as Propostas'."""
    fonte = _fonte()
    bloco = re.search(r"const mockWorkflowProposals.*?\n\];", fonte, re.S)
    assert 'status: "declined"' not in bloco.group(0), (
        "voltou proposta em `declined`, que não tem card — use "
        "`refund_scheduled`, que é o status por trás de 'Propostas Declinadas'")


def test_toda_proposta_de_devolucao_tem_sub_status():
    """O filtro de sub-status compara IGUALDADE: proposta sem
    `refundSubStatus` some ao filtrar por qualquer um deles, aparecendo só
    em 'Todos os sub-status'. Some da tela sem nenhum aviso."""
    fonte = _fonte()
    bloco = re.search(r"const mockWorkflowProposals.*?\n\];", fonte, re.S)
    linhas = [l for l in bloco.group(0).splitlines()
              if 'status: "refund_scheduled"' in l]
    assert linhas, "nenhuma proposta em refund_scheduled no mock"
    sem = [l for l in linhas if "refundSubStatus" not in l]
    assert not sem, (
        f"{len(sem)} proposta(s) de devolução sem refundSubStatus — somem "
        f"ao filtrar por sub-status")
