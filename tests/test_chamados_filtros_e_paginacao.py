"""Filtros do kanban, paginação das tabelas e o filtro múltiplo dos indicadores.

Pedidos do dono do produto:

    "filtro de tipo no kanban, não deve ter task, somente RITM, INCIDENTE e
     TODOS. criar um novo filtro para Categoria, que deverá preencher Dia a
     Dia, Iniciativas, Sem marcação e todos. os cards devem ter um badge
     visivel se é dia a dia ou iniciativa… e no responsavel também permitir
     filtrar sem atribuição."

    "criar nos resolvidos nos ultimos dias paginação… 10 chamados por pagina.
     todos os locais que tiverem as tabelas, pode aplicar este mesmo conceito."

    "no responsavel no indicadores, permitir filtrar com checkbox, podendo
     filtrar mais de uma opção."

⚠️ ESTE ARQUIVO RENDERIZA E CLICA. Paginação e marcação são estado que só
existe depois de um clique; e a regra de "quem entra na fila filtrada" foi
EXTRAÍDA de `pages/Chamados.tsx` para `lib/filtrosKanban` justamente para poder
ser interrogada — dentro da página, com react-query no módulo, nenhuma bancada
a alcança.

Sem Node ou sem `node_modules` a suíte SALTA em vez de falhar.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
HARNESS = RAIZ / "tests" / "js" / "tabela_copiar_harness.cjs"
SUCRASE = RAIZ / "ui-react" / "node_modules" / "sucrase"


def _node() -> str | None:
    caminho = shutil.which("node")
    if not caminho or not SUCRASE.is_dir():
        return None
    try:
        v = subprocess.run([caminho, "-v"], capture_output=True, text=True,
                           timeout=30).stdout.strip()
        return caminho if int(v.lstrip("v").split(".")[0]) >= 18 else None
    except Exception:      # noqa: BLE001 — sonda de ambiente degrada em salto
        return None


@pytest.fixture(scope="module")
def cen() -> dict:
    node = _node()
    if node is None:
        pytest.skip("front não instalado nesta máquina")
    r = subprocess.run([node, str(HARNESS)], capture_output=True, text=True,
                       cwd=str(RAIZ), timeout=120)
    assert r.returncode == 0, f"bancada do front falhou:\n{r.stderr}"
    return json.loads(r.stdout)


# ═══════════ 1. o seletor de Tipo não oferece Tarefa ════════════════════════

def test_o_seletor_de_tipo_nao_oferece_tarefa(cen: dict) -> None:
    """A tarefa não é um item da fila — é uma linha DENTRO do card do pedido.
    "Tarefa" no seletor ofereceria um recorte que a tela não representa."""
    tipos = cen["kanban"]["tipos_do_seletor"]
    assert "task" not in tipos
    assert tipos == ["incident", "ritm"], "e sem repetir o que aparece duas vezes"


def test_o_seletor_de_tipo_sai_dos_cards_e_nao_de_uma_lista_fixa(cen: dict) -> None:
    """Lista fixa mostraria opção que não filtra nada — ou esconderia a que
    filtra, quando a instância trouxer um tipo novo."""
    assert cen["kanban"]["tipos_sem_cards"] == []


def test_filtrar_por_tipo_olha_o_card_e_nao_a_tarefa(cen: dict) -> None:
    """Todo RITM tem tarefa dentro; casar pela filha faria "Tarefa" (ou
    qualquer tipo) devolver a fila inteira."""
    assert cen["kanban"]["tipo_nao_casa_pela_filha"] is False
    assert cen["kanban"]["tipo_do_card"] is True


# ═══════════ 2. o filtro de Categoria ═══════════════════════════════════════

def test_categoria_filtra_pelo_valor_marcado(cen: dict) -> None:
    k = cen["kanban"]
    assert k["cat_diaadia_acha"] is True
    assert k["cat_diaadia_recusa_iniciativa"] is False


def test_sem_marcacao_acha_o_que_ninguem_classificou(cen: dict) -> None:
    """É o recorte mais acionável dos três: a lista do que ainda precisa ser
    classificado pela equipe."""
    k = cen["kanban"]
    assert k["cat_sem_marcacao_acha"] is True
    assert k["cat_sem_marcacao_recusa_marcado"] is False


def test_a_categoria_e_a_do_CARD_e_nao_a_da_tarefa(cen: dict) -> None:
    """O badge mostra a categoria do card. Casar pela filha traria um card
    filtrado como "iniciativa" SEM badge nenhum — e quem filtrou concluiria
    que o badge está quebrado."""
    assert cen["kanban"]["cat_nao_casa_pela_filha"] is False


# ═══════════ 3. sem atribuição ══════════════════════════════════════════════

def test_sem_atribuicao_acha_o_que_ninguem_pegou(cen: dict) -> None:
    """Chamado sem dono não aparece na carga de ninguém e some da conversa."""
    k = cen["kanban"]
    assert k["sem_dono_acha"] is True
    assert k["sem_dono_recusa_atribuido"] is False


def test_sem_atribuicao_pergunta_pelo_dono_do_card(cen: dict) -> None:
    """Casado contra as filhas, um pedido ATRIBUÍDO com uma tarefa sem dono
    apareceria como se ninguém o tivesse pegado."""
    assert cen["kanban"]["sem_dono_ignora_filha"] is False


def test_responsavel_em_branco_conta_como_sem_atribuicao(cen: dict) -> None:
    """O espelho guarda ora NULL, ora string de espaços — e as duas coisas
    significam a mesma para quem olha a fila."""
    assert cen["kanban"]["sem_dono_aceita_vazio"] is True


def test_responsavel_nomeado_continua_alcancando_a_tarefa(cen: dict) -> None:
    """O responsável que só aparece numa tarefa precisa ser filtrável — foi
    assim antes desta fase e não pode regredir."""
    assert cen["kanban"]["resp_pela_filha"] is True
    assert cen["kanban"]["busca_pela_filha"] is True, "e a busca também"


# ═══════════ 4. os filtros se somam ═════════════════════════════════════════

def test_os_filtros_se_combinam_com_E(cen: dict) -> None:
    """Filtro que substitui o anterior em vez de somar devolve MAIS linhas do
    que o esperado — e ninguém percebe, porque a tela nunca fica vazia."""
    k = cen["kanban"]
    assert k["combinado_ok"] is True
    assert k["combinado_recusa"] is False


def test_sem_filtro_nada_e_escondido(cen: dict) -> None:
    k = cen["kanban"]
    assert k["sem_filtro_passa_tudo"] is True
    assert k["ativo_vazio"] is False
    assert k["ativo_com_categoria"] is True, "senão o botão Limpar não aparece"


# ═══════════ 5. paginação ═══════════════════════════════════════════════════

def test_a_primeira_pagina_mostra_dez(cen: dict) -> None:
    p = cen["paginacao"]["pagina1"]
    assert p["linhas"] == 10
    assert p["primeiro"] == "RITM0000000"
    assert "1 – 10 de 25" in p["texto"] or "1–10 de 25" in p["texto"], (
        "a régua diz o INTERVALO e o TOTAL: 'página 1 de 3' sozinho não "
        "responde 'quantos são?', que é a pergunta de quem abriu a lista")


def test_avancar_troca_o_conteudo(cen: dict) -> None:
    assert cen["paginacao"]["pagina2"]["primeiro"] == "RITM0000010"
    assert cen["paginacao"]["pagina2"]["linhas"] == 10


def test_a_ultima_pagina_traz_o_resto(cen: dict) -> None:
    p = cen["paginacao"]["pagina3"]
    assert p["linhas"] == 5, "25 itens, 10 por página: sobram 5"
    assert p["primeiro"] == "RITM0000020"


def test_os_botoes_desligam_nas_pontas(cen: dict) -> None:
    """Botão que parece clicável e não faz nada ensina a duvidar dos outros."""
    assert cen["paginacao"]["pagina1"]["anteriorDesligado"] is True
    assert cen["paginacao"]["pagina1"]["proximaDesligada"] is False
    assert cen["paginacao"]["pagina3"]["proximaDesligada"] is True
    assert cen["paginacao"]["pagina3"]["anteriorDesligado"] is False


def test_lista_curta_nao_ganha_regua(cen: dict) -> None:
    """Régua "1/1" em quatro linhas é ruído."""
    c = cen["paginacao"]["curta"]
    assert c["temRegua"] is False
    assert c["linhas"] == 4


def test_paginacao_desligada_mostra_tudo(cen: dict) -> None:
    d = cen["paginacao"]["desligada"]
    assert d["linhas"] == 25
    assert d["temRegua"] is False


def test_lista_que_encolhe_nao_deixa_a_tabela_vazia(cen: dict) -> None:
    """⚠️ O caso que morde: a página vive em estado e a lista muda por baixo
    dela (o usuário filtra, o bloco do painel troca). Obedecer uma página 3
    sobre uma lista de 4 itens renderiza tabela VAZIA — indistinguível de
    "não há nada aqui", e o usuário conclui a segunda."""
    e = cen["paginacao"]["encolheu"]
    assert e["linhas"] == 4
    assert e["primeiro"] == "RITM0000000"


@pytest.mark.parametrize("caso,esperado", [
    ("primeira", {"pagina": 0, "paginas": 3, "primeiro": 1, "ultimo": 10}),
    ("ultima", {"pagina": 2, "paginas": 3, "primeiro": 21, "ultimo": 25}),
    # Página além do fim é corrigida para a última que existe.
    ("alem_do_fim", {"pagina": 2, "paginas": 3, "primeiro": 21, "ultimo": 25}),
    ("negativa", {"pagina": 0, "paginas": 3, "primeiro": 1, "ultimo": 10}),
    # Lista vazia não tem "item 1 de 0".
    ("vazia", {"pagina": 0, "paginas": 1, "primeiro": 0, "ultimo": 0}),
    # Divisão exata não inventa uma página a mais, vazia.
    ("exata", {"pagina": 1, "paginas": 2, "primeiro": 11, "ultimo": 20}),
])
def test_a_aritmetica_da_pagina(cen: dict, caso: str, esperado: dict) -> None:
    f = cen["paginacao"]["fatias"][caso]
    assert {k: f[k] for k in esperado} == esperado


# ═══════════ 6. o filtro múltiplo dos indicadores ═══════════════════════════

def test_marcar_um_nome_soma_em_vez_de_substituir(cen: dict) -> None:
    """A gestão compara duas ou três pessoas. Com seletor único isso vira
    olhar uma, guardar o número de cabeça, olhar a outra — apagando justamente
    o número que se queria comparar."""
    assert cen["filtro_responsaveis"]["um"]["aoMarcarSemDono"] == [
        "Ana", "sem responsável"]


def test_desmarcar_tira_so_aquele_nome(cen: dict) -> None:
    assert cen["filtro_responsaveis"]["um"]["aoMarcarAna"] == []
    assert cen["filtro_responsaveis"]["puras"]["alternar_desmarca"] == ["Bruno"]


def test_o_gatilho_fechado_diz_quem_esta_filtrado(cen: dict) -> None:
    """Com a lista fechada, um filtro de três pessoas seria indistinguível de
    nenhum filtro — e um print da tela viraria "a fila tem 16 chamados"."""
    f = cen["filtro_responsaveis"]
    assert f["nenhum"]["resumo"] == "todos (22)"
    assert f["um"]["resumo"] == "Ana"
    assert f["dois"]["resumo"] == "Ana e Bruno"
    assert f["tres"]["resumo"] == "3 responsáveis"


def test_o_contador_aparece_so_quando_ha_recorte(cen: dict) -> None:
    f = cen["filtro_responsaveis"]
    assert f["nenhum"]["contagem"] is None
    assert f["dois"]["contagem"] == "2"


def test_as_marcas_refletem_a_escolha(cen: dict) -> None:
    """Caixa desmarcada num filtro em vigor faria o usuário marcar de novo — e
    o segundo clique DESLIGA o que ele queria ligar."""
    assert cen["filtro_responsaveis"]["dois"]["marcadas"] == ["Ana", "Bruno"]
    assert cen["filtro_responsaveis"]["nenhum"]["marcadas"] == []


def test_sem_responsavel_e_uma_opcao_da_lista(cen: dict) -> None:
    assert "sem responsável" in cen["filtro_responsaveis"]["um"]["opcoes"]


def test_limpar_devolve_a_fila_inteira(cen: dict) -> None:
    assert cen["filtro_responsaveis"]["um"]["aoLimpar"] == []


def test_lista_sem_ninguem_diz_isso(cen: dict) -> None:
    """Caixa vazia parece falha de carregamento."""
    assert "Nenhum responsável" in cen["filtro_responsaveis"]["vazio"]["texto"]


# ═══════════ 6b. a caixa FECHA — o defeito relatado ═════════════════════════
#
# "quando escolho qualquer opção o modal não some ao clicar fora, ele fica
#  travado ocupando a tela e só com atualização de tela que some mas ai não
#  consigo valir os dados."
#
# ⚠️ A primeira versão usava `<details>`, com o argumento de que ele dispensava
# tratar o clique-fora. O argumento estava ERRADO: `<details>` fecha só pelo
# próprio gatilho. A caixa ficava sobre o conteúdo — e o conteúdo é justamente
# o que a pessoa acabou de filtrar para ver.

def test_a_caixa_comeca_fechada(cen: dict) -> None:
    """Caixa aberta ao carregar a aba tampa os indicadores antes do primeiro
    clique."""
    assert cen["filtro_responsaveis"]["um"]["comecaFechada"] is True


def test_clicar_fora_fecha(cen: dict) -> None:
    """O gesto que faltava. Sem ele, a saída era recarregar a página — e o
    filtro se perdia junto, que é o que impedia conferir os dados."""
    f = cen["filtro_responsaveis"]["fechamento"]
    assert f["temFundo"] is True, "precisa existir uma camada que capture o clique"
    assert f["depoisDoFundo"] is False


def test_esc_fecha(cen: dict) -> None:
    """Quem está no teclado não tem "clicar fora"."""
    assert cen["filtro_responsaveis"]["fechamento"]["depoisDoEsc"] is False


def test_outra_tecla_nao_fecha(cen: dict) -> None:
    """Fechar em qualquer tecla derrubaria a caixa quando a pessoa navega com
    Tab ou Espaço entre as opções."""
    assert cen["filtro_responsaveis"]["fechamento"]["depoisDeOutraTecla"] is True


def test_o_botao_fechar_existe_e_funciona(cen: dict) -> None:
    """O clique fora funciona, mas não se anuncia — quem não o descobriu fica
    preso à caixa, que foi exatamente o relato."""
    f = cen["filtro_responsaveis"]["fechamento"]
    assert f["temBotaoFechar"] is True
    assert f["depoisDoBotaoFechar"] is False


def test_o_gatilho_alterna(cen: dict) -> None:
    assert cen["filtro_responsaveis"]["fechamento"]["depoisDoGatilhoDeNovo"] is False


def test_marcar_uma_opcao_NAO_fecha(cen: dict) -> None:
    """O filtro é de múltipla escolha: fechar a cada marca obrigaria a reabrir
    para cada nome, e o pedido era justamente comparar várias pessoas."""
    assert cen["filtro_responsaveis"]["fechamento"]["aoMarcarContinuaAberta"] is True


# ═══════════ 6c. incidente: destaque e topo da fila ═════════════════════════
#
# "quando for incidente o card deve ter um destaque e sempre deve estar no
#  inicio da fila que ele estiver, pois ele deve ser prioridade, ele só perde
#  este destaque e top da fila quando vai para resolvido."

@pytest.mark.parametrize("caso", [
    "destaca_incidente_novo", "destaca_incidente_andamento",
    "destaca_incidente_aguardando",
])
def test_incidente_em_curso_recebe_destaque(cen: dict, caso: str) -> None:
    """Incidente é INTERRUPÇÃO: alguma coisa que funcionava parou. No meio de
    pedidos de trabalho planejado ele some — e some justamente quando é o que
    deveria ser lido primeiro."""
    assert cen["kanban"][caso] is True


@pytest.mark.parametrize("caso", [
    "destaca_incidente_resolvido", "destaca_incidente_encerrado",
])
def test_incidente_terminado_perde_o_destaque(cen: dict, caso: str) -> None:
    """Alarme sobre trabalho FEITO não pede ação nenhuma — e é o que ensina a
    ignorar os outros, inclusive os que pedem. Mesma razão pela qual o rodapé
    cala idade e prazo no resolvido."""
    assert cen["kanban"][caso] is False


@pytest.mark.parametrize("caso", ["destaca_ritm", "destaca_task"])
def test_o_que_nao_e_incidente_nao_recebe_destaque(cen: dict, caso: str) -> None:
    """Destaque em tudo é destaque em nada."""
    assert cen["kanban"][caso] is False


def test_o_incidente_vai_para_o_topo_da_coluna(cen: dict) -> None:
    """Quem abre o kanban lê de cima para baixo e para quando acha o que
    procura — um incidente na décima posição de uma coluna que rola é um
    incidente que ninguém viu."""
    assert cen["kanban"]["ordem_incidente_sobe"] == ["I1", "R1", "R2", "R3"]


def test_a_ordem_dentro_de_cada_grupo_e_preservada(cen: dict) -> None:
    """Ordenação instável faz dois cards "iguais" trocarem de lugar entre
    renderizações — e a fila dança sob o olho de quem está lendo."""
    assert cen["kanban"]["ordem_estavel"] == ["I1", "I2", "R1", "R2", "R3"]


def test_na_coluna_de_resolvidos_o_incidente_nao_sobe(cen: dict) -> None:
    """Ele já terminou: subir ao topo daria a ele uma atenção que nada pede."""
    assert cen["kanban"]["ordem_resolvido_nao_sobe"] == ["R1", "I1", "R2"]


def test_ordenar_nao_altera_a_lista_recebida(cen: dict) -> None:
    """Mutar o array do `useMemo` faria a fila mudar de ordem entre
    renderizações sem que nada a tivesse reordenado."""
    assert cen["kanban"]["ordem_nao_muta"] == ["R1", "I1"]
    assert cen["kanban"]["ordem_vazia"] == 0


# ═══════════ 7. a URL que carrega o recorte ═════════════════════════════════

@pytest.mark.parametrize("caso,esperado", [
    ("url_vazia", "/chamados/indicadores"),
    ("url_um", "/chamados/indicadores?responsavel=Ana"),
    # ⚠️ Parâmetro REPETIDO, que é como o FastAPI monta uma lista. Juntar com
    # vírgula produziria UM nome chamado "Ana,Bruno", que não casa com ninguém
    # — e a resposta viria vazia parecendo "estas pessoas não têm chamados".
    ("url_dois", "/chamados/indicadores?responsavel=Ana&responsavel=Bruno"),
    # Nomes têm espaço e acento; "sem responsável" tem os dois.
    ("url_acentuada", "/chamados/indicadores?responsavel=sem%20respons%C3%A1vel"),
    ("url_ignora_brancos", "/chamados/indicadores?responsavel=Ana"),
])
def test_a_url_leva_os_nomes_ao_servidor(cen: dict, caso: str, esperado: str) -> None:
    assert cen["filtro_responsaveis"]["puras"][caso] == esperado


@pytest.mark.parametrize("caso,esperado", [
    ("aviso_nenhum", ""),
    ("aviso_um", "todos os números abaixo são apenas de Ana"),
    ("aviso_tres", "todos os números abaixo são apenas de Ana, Bruno e Caio"),
])
def test_o_aviso_nomeia_o_recorte(cen: dict, caso: str, esperado: str) -> None:
    """TODO número da aba muda com o filtro. A ausência de aviso é a afirmação
    de que os números são da fila inteira."""
    assert cen["filtro_responsaveis"]["puras"][caso] == esperado
