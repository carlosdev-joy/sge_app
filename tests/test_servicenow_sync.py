"""Miolo do sync dos chamados (dags/utils/servicenow_sync.py).

O dev NÃO alcança o ServiceNow da empresa — a prova real é o smoke §7 em
produção. Aqui prendemos o CONTRATO, que é o que dá para provar sem rede:

  1. **Estado desconhecido cai em 'outros' e APARECE.** Um estado novo criado
     no ServiceNow não pode fazer o chamado sumir da tela: some da fila sem
     ninguém notar é pior que aparecer na coluna errada (risco #3 da spec).
  2. **Título trunca COM reticência.** Truncar calado já mordeu (VARCHAR
     estourado, PR #161); o corte precisa ficar visível no card.
  3. **O filtro por grupo nunca fica vazio.** Query sem filtro traria a fila
     da empresa inteira para dentro do espelho.
  4. **Estado terminal sai da fila** mesmo quando a origem ainda diz
     `active=true` — acontece, e o kanban não pode ficar entulhado.
  5. **Data ilegível não derruba o ciclo** — o chamado entra sem data.
  6. **O MERGE tem os parâmetros na ordem certa** — chave, UPDATE, INSERT.
     Um deslocamento aqui grava título na coluna de prioridade em silêncio.

Nada toca rede nem Airflow: só as funções puras do módulo de utilidade.
"""
from __future__ import annotations

import datetime as _dt
import sys
from pathlib import Path

import pytest

# dags/ não é pacote instalável: o import espelha o que o worker faz.
RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "dags"))

from utils.servicenow_sync import (  # noqa: E402
    CAMPOS, COLUNAS_KANBAN, ESTADOS, TABELAS, TITULO_MAX,
    K_PROXY, mapear_estado, normalizar, proxy_da_config, query_do_grupo,
    truncar_titulo,
    upsert_params, upsert_sql,
)

URL = "https://cvpsnprod.service-now.com"


def _registro(**kw):
    """Registro cru no formato display_value=all da Table API."""
    base = {
        "sys_id": {"display_value": "abc123", "value": "abc123"},
        "number": {"display_value": "INC0012345", "value": "INC0012345"},
        "short_description": {"display_value": "Falha na carga", "value": "Falha na carga"},
        "state": {"display_value": "In Progress", "value": "2"},
        "priority": {"display_value": "3 - Moderate", "value": "3"},
        "assigned_to": {"display_value": "Fulano de Tal", "value": "u1"},
        "assignment_group": {"display_value": "Engenharia", "value": "g1"},
        "opened_at": {"display_value": "13/08/2026", "value": "2026-08-13 10:00:00"},
        "sys_updated_on": {"display_value": "13/08/2026", "value": "2026-08-13 11:00:00"},
        "closed_at": {"display_value": "", "value": ""},
        "active": {"display_value": "true", "value": "true"},
    }
    base.update(kw)
    return base


# ═══════════ 1. o estado desconhecido não pode sumir ════════════════════════

def test_estado_desconhecido_vira_outros():
    assert mapear_estado("incident", "999") == "outros"
    assert mapear_estado("incident", None) == "outros"
    assert mapear_estado("incident", "") == "outros"


def test_tabela_desconhecida_vira_outros():
    assert mapear_estado("tabela_que_nao_existe", "1") == "outros"


def test_chamado_com_estado_novo_continua_no_espelho():
    """O que importa: ele APARECE, na coluna 'outros'."""
    linha = normalizar(_registro(state={"display_value": "Aguardando Vendor",
                                        "value": "42"}),
                       "incident", "incident", URL)
    assert linha["estado_kanban"] == "outros"
    assert linha["ativo"] == 1, "estado desconhecido não pode tirar da fila"
    assert linha["estado_origem"] == "Aguardando Vendor", (
        "o valor cru precisa sobreviver para o operador entender a coluna")


def test_todo_estado_mapeado_cai_numa_coluna_valida():
    """Nenhum valor do dict pode apontar para coluna que a tela não tem."""
    validos = set(COLUNAS_KANBAN) | {"encerrado"}
    for tabela, mapa in ESTADOS.items():
        for estado, coluna in mapa.items():
            assert coluna in validos, f"{tabela}/{estado} → '{coluna}' inválida"


# ═══════════ 2. truncamento visível ═════════════════════════════════════════

def test_titulo_longo_trunca_com_reticencia():
    saida = truncar_titulo("x" * 500)
    assert len(saida) == TITULO_MAX
    assert saida.endswith("…"), "o corte precisa ficar visível"


def test_titulo_curto_fica_intacto():
    assert truncar_titulo("Falha na carga") == "Falha na carga"


def test_titulo_no_limite_exato_nao_trunca():
    assert truncar_titulo("y" * TITULO_MAX) == "y" * TITULO_MAX


def test_titulo_com_acento_e_emoji_respeita_o_limite_da_coluna():
    """NVARCHAR(n) conta unidades UTF-16, não caracteres Python.

    Este teste media `len()` e passava — enquanto o texto gerado ocupava MAIS
    de 400 unidades no banco, porque 🔥 fora do BMP vale 2. O `len()` == 400
    era um verde que não provava o que dizia provar: quem cobra é o SQL
    Server, com Msg 8152 no meio do ciclo.
    """
    from utils.servicenow_sync import unidades_utf16
    saida = truncar_titulo("ção🔥" * 200)
    assert unidades_utf16(saida) <= TITULO_MAX
    assert len(saida) < TITULO_MAX, (
        "com emoji, cabem MENOS caracteres que o limite da coluna")


def test_titulo_vazio_nao_quebra():
    assert truncar_titulo(None) == ""


# ═══════════ 3. o filtro de grupo nunca some ════════════════════════════════

def test_sem_grupo_a_query_e_recusada():
    """Sem filtro o sync traria a fila da empresa inteira."""
    with pytest.raises(ValueError, match="nenhum grupo"):
        query_do_grupo([])


def test_query_de_um_grupo():
    assert query_do_grupo(["Engenharia"]) == "assignment_group.name=Engenharia"


def test_query_de_varios_grupos_usa_or():
    q = query_do_grupo(["Engenharia", "Sustentação"])
    assert q == "assignment_group.name=Engenharia^ORassignment_group.name=Sustentação"


# ═══════════ 4. quem sai da fila ════════════════════════════════════════════

def test_estado_terminal_sai_da_fila_mesmo_com_active_true():
    """Estado terminal com active=true acontece — o kanban não pode entulhar."""
    linha = normalizar(_registro(state={"display_value": "Closed", "value": "7"},
                                 active={"display_value": "true", "value": "true"}),
                       "incident", "incident", URL)
    assert linha["ativo"] == 0
    assert linha["estado_kanban"] == "resolvido", (
        "'encerrado' não é coluna do kanban — vira resolvido no espelho")


def test_inativo_na_origem_sai_da_fila():
    linha = normalizar(_registro(active={"display_value": "false", "value": "false"}),
                       "incident", "incident", URL)
    assert linha["ativo"] == 0


def test_chamado_aberto_fica_na_fila():
    linha = normalizar(_registro(), "incident", "incident", URL)
    assert linha["ativo"] == 1
    assert linha["estado_kanban"] == "andamento"


# ═══════════ 5. dados ruins não derrubam o ciclo ════════════════════════════

def test_data_ilegivel_vira_none_sem_excecao():
    linha = normalizar(_registro(opened_at={"display_value": "", "value": "ontem"}),
                       "incident", "incident", URL)
    assert linha["aberto_em"] is None


def test_data_valida_vira_datetime():
    linha = normalizar(_registro(), "incident", "incident", URL)
    assert linha["aberto_em"] == _dt.datetime(2026, 8, 13, 10, 0, 0)


def test_data_so_com_dia_e_aceita():
    linha = normalizar(_registro(closed_at={"display_value": "", "value": "2026-08-13"}),
                       "incident", "incident", URL)
    assert linha["encerrado_em"] == _dt.datetime(2026, 8, 13)


def test_campos_longos_sao_cortados_no_limite_da_coluna():
    """Cada campo tem o tamanho da sua coluna na migration 088."""
    linha = normalizar(_registro(
        number={"display_value": "N" * 60, "value": "x"},
        priority={"display_value": "P" * 60, "value": "x"},
        assigned_to={"display_value": "A" * 300, "value": "x"},
        assignment_group={"display_value": "G" * 300, "value": "x"}),
        "incident", "incident", URL)
    assert len(linha["numero"]) <= 20
    assert len(linha["prioridade"]) <= 20
    assert len(linha["atribuido_a"]) <= 120
    assert len(linha["grupo"]) <= 120
    assert len(linha["url"]) <= 500


def test_registro_em_formato_plano_tambem_normaliza():
    """Sem display_value=all a API devolve string pura — não pode quebrar."""
    linha = normalizar({"sys_id": "abc", "number": "INC1", "state": "1",
                        "short_description": "Teste", "active": "true"},
                       "incident", "incident", URL)
    assert linha["sys_id"] == "abc"
    assert linha["estado_kanban"] == "novo"


# ═══════════ 6. o MERGE não pode deslocar parâmetro ═════════════════════════

def test_upsert_tem_parametro_para_cada_placeholder():
    """Deslocamento aqui grava título na coluna de prioridade em silêncio."""
    linha = normalizar(_registro(), "incident", "incident", URL)
    params = upsert_params(linha)
    assert upsert_sql().count("%s") == len(params), (
        "placeholders e parâmetros precisam bater exatamente")


def test_upsert_ordem_chave_update_insert():
    """1 chave + N do UPDATE + os MESMOS N do INSERT.

    O tamanho é derivado, não fixo: campo novo no espelho não pode fazer este
    teste falhar por contagem — ele existe para pegar DESLOCAMENTO, que é o
    defeito silencioso (grava título na coluna de prioridade sem erro nenhum).
    """
    linha = normalizar(_registro(), "incident", "incident", URL)
    p = upsert_params(linha)
    assert p[0] == linha["sys_id"], "o 1º parâmetro é a chave do MERGE"
    assert (len(p) - 1) % 2 == 0, "UPDATE e INSERT precisam ter o mesmo tamanho"
    n = (len(p) - 1) // 2
    assert p[1:1 + n] == p[1 + n:], "UPDATE e INSERT recebem os mesmos valores"
    assert p[1] == linha["numero"] and p[1 + n] == linha["numero"]
    # A ordem do MERGE segue a ordem das colunas no INSERT: se alguém inserir
    # um campo no meio de um e não do outro, o par acima ainda casaria — este
    # ancora as pontas nos valores que a coluna espera.
    #
    # A âncora é o NOME literal da última coluna, de propósito: derivá-la de
    # CAMPOS_UPSERT faria o teste concordar com qualquer reordenação. Campo
    # novo no fim ⇒ atualize esta linha conscientemente (foi o que a
    # migration 091 exigiu, quando o último campo deixou de ser pai_numero).
    assert p[n] == linha["objetos"], "o último campo do UPDATE é objetos"


def test_upsert_usa_placeholder_do_pymssql():
    """A árvore dags/ é pymssql: '?' aqui daria 'Incorrect syntax near ?'."""
    sql = upsert_sql()
    assert "%s" in sql and "?" not in sql


def test_url_do_chamado_aponta_para_o_registro():
    linha = normalizar(_registro(), "incident", "incident", URL)
    assert linha["url"].startswith(URL)
    assert "sys_id=abc123" in linha["url"]


def test_todas_as_tabelas_tem_mapa_de_estado():
    """Tabela sincronizada sem mapa jogaria TUDO em 'outros'."""
    for tabela, _tipo in TABELAS:
        assert tabela in ESTADOS, f"{tabela} sem mapeamento de estado"


# ═══════════ 7. a rota de saída (proxy corporativo) ═════════════════════════
# O worker do Airflow não herda o HTTPS_PROXY do orquestra-api, e por isso o
# primeiro sync real morreu com "Connection reset by peer" nas quatro tabelas
# em 1 segundo. A rota virou CONFIG (servicenow_proxy, migration 089) e não
# variável de ambiente: variável só entra em container novo, e recriar o
# worker mata as tasks em execução.

def test_config_sem_a_chave_e_rota_direta():
    """Ambiente sem a migration 089 não pode quebrar o sync: a ausência da
    chave significa 'direto', que é como o dev sempre rodou."""
    assert proxy_da_config({}) is None


def test_proxy_vazio_e_rota_direta():
    """O seed da 089 nasce vazio. Devolver '' em vez de None faria o httpx
    tentar um proxy de endereço vazio — falha de rede com cara de firewall,
    que é justamente o sintoma que este código existe para desambiguar."""
    assert proxy_da_config({K_PROXY: ""}) is None


def test_proxy_so_com_espacos_e_rota_direta():
    assert proxy_da_config({K_PROXY: "   "}) is None


def test_proxy_configurado_e_devolvido_sem_espacos():
    cfg = {K_PROXY: "  http://webproxycvp.adcorp.intranet/  "}
    assert proxy_da_config(cfg) == "http://webproxycvp.adcorp.intranet/"


def test_proxy_nao_atrapalha_as_outras_chaves():
    """A DAG lê tudo num SELECT LIKE 'servicenow%'. A chave nova entra no
    mesmo dicionário e não pode ser confundida com URL nem com senha."""
    cfg = {"servicenow_url": "https://x.service-now.com",
           K_PROXY: "http://proxy:8080"}
    assert proxy_da_config(cfg) == "http://proxy:8080"


def test_dag_imprime_a_rota_escolhida():
    """Proxy ausente e proxy errado dão o MESMO erro de rede. Sem esta linha
    no log, o diagnóstico volta a ser adivinhação."""
    fonte = (RAIZ / "dags" / "etl_servicenow_sync.py").read_text(encoding="utf-8")
    assert "conexão direta" in fonte and "via proxy" in fonte


# ═══════════ 8. parentesco RITM ↔ task (migration 090) ══════════════════════
# No ServiceNow todo RITM gera uma sc_task filha, e o espelho trazia as duas
# como cards independentes — a fila contava cada trabalho DUAS vezes (113
# itens para ~60 trabalhos). A ligação vem de `request_item`/`parent`, não do
# título: a task nasce como "RITM0096880 - <assunto>", mas isso é convenção de
# texto e quebra quando alguém mudar o padrão da instância.

def _task(**kw):
    """sc_task filha de um RITM, no formato display_value=all."""
    base = _registro(
        number={"display_value": "SCTASK0098628", "value": "SCTASK0098628"},
        short_description={"display_value": "RITM0096880 - Inclusão de coluna",
                           "value": "RITM0096880 - Inclusão de coluna"},
        request_item={"display_value": "RITM0096880",
                      "value": "74a24a128716479094b30e530cbb3539"},
    )
    base.update(kw)
    return base


def test_task_guarda_o_ritm_pai():
    linha = normalizar(_task(), "sc_task", "task", URL)
    assert linha["pai_numero"] == "RITM0096880", "o número é o que a tela mostra"
    assert linha["pai_sys_id"] == "74a24a128716479094b30e530cbb3539", (
        "o sys_id é o que dá join exato contra o espelho")


def test_request_item_manda_sobre_parent():
    """Numa sc_task de catálogo os dois vêm preenchidos, e é o request_item
    que aponta para o RITM — o parent pode ser outra coisa na hierarquia."""
    linha = normalizar(_task(parent={"display_value": "OUTRO0001", "value": "zzz"}),
                       "sc_task", "task", URL)
    assert linha["pai_numero"] == "RITM0096880"


def test_parent_vale_quando_nao_ha_request_item():
    """incident e change_request não têm request_item; usam parent."""
    reg = _registro(parent={"display_value": "INC0001", "value": "abc"})
    linha = normalizar(reg, "incident", "incident", URL)
    assert linha["pai_numero"] == "INC0001"
    assert linha["pai_sys_id"] == "abc"


def test_chamado_sem_pai_fica_vazio_nao_none():
    """RITM raiz não tem pai. Vazio (não None) porque a coluna é VARCHAR e o
    upsert grava direto — e '' distingue 'não tem' de 'não sei'."""
    linha = normalizar(_registro(), "incident", "incident", URL)
    assert linha["pai_sys_id"] == "" and linha["pai_numero"] == ""


def test_campo_de_pai_vazio_nao_vira_pai_fantasma():
    """A API devolve o campo com display/value em branco quando não há pai —
    gravar isso como pai criaria um vínculo para lugar nenhum."""
    linha = normalizar(_registro(request_item={"display_value": "", "value": ""},
                                 parent={"display_value": "", "value": ""}),
                       "sc_task", "task", URL)
    assert linha["pai_sys_id"] == "" and linha["pai_numero"] == ""


def test_a_api_e_consultada_pelos_campos_de_parentesco():
    """Sem pedir na query, a Table API não devolve — e o pai viria vazio para
    todo mundo, com o espelho parecendo dizer 'ninguém tem pai'."""
    assert "request_item" in CAMPOS and "parent" in CAMPOS


# ═══════════ 9. o estado CRU, ao lado do rótulo ═════════════════════════════
# `estado_origem` guarda "Pendente"; o mapa do kanban é por NÚMERO. Sem o
# número gravado, corrigir um estado que caiu em 'outros' exige ir à API — e
# quando dois números apontam para a mesma coluna (sc_task: '-5' e '1' → novo),
# nem a API resolve, porque o display não diz qual é qual.

def test_estado_cru_e_gravado_ao_lado_do_rotulo():
    linha = normalizar(_registro(state={"display_value": "Pendente", "value": "-5"}),
                       "sc_task", "task", URL)
    assert linha["estado_cru"] == "-5", "o número precisa sobreviver ao espelho"
    assert linha["estado_origem"] == "Pendente", "o rótulo continua, para a tela"


def test_estado_cru_negativo_nao_e_perdido():
    """'-5' tem sinal e o campo é VARCHAR: um corte ou conversão numérica aqui
    quebraria justamente o valor que estamos investigando."""
    linha = normalizar(_registro(state={"display_value": "X", "value": "-5"}),
                       "sc_task", "task", URL)
    assert linha["estado_cru"] == "-5"


def test_estado_ausente_nao_quebra():
    linha = normalizar(_registro(state={"display_value": "", "value": ""}),
                       "incident", "incident", URL)
    assert linha["estado_cru"] == ""
    assert linha["estado_kanban"] == "outros"


# ═══════════ 10. os estados MEDIDOS na instância (2026-08-13) ══════════════
# Valores lidos da coluna estado_cru do espelho de produção (migration 090),
# no grupo TI_CVP_GERESD_ED. Não são suposição: cada par abaixo apareceu com
# contagem própria na consulta de conferência. É o teste que impede alguém de
# "arrumar" o mapa de novo por dedução — foi assim que '-5' virou 'novo'.

ESTADOS_MEDIDOS = [
    # (tabela,        cru,   rótulo na origem,        coluna esperada)
    ("incident",      "6",   "Resolvido(a)",          "resolvido"),
    ("sc_req_item",   "1",   "Em aberto",             "novo"),
    ("sc_req_item",   "2",   "Trabalho em andamento", "andamento"),
    ("sc_req_item",   "6",   "Resolvido",             "resolvido"),
    ("sc_req_item",   "-5",  "Pendente",              "aguardando"),
    ("sc_task",       "1",   "Em aberto",             "novo"),
    ("sc_task",       "2",   "Trabalho em andamento", "andamento"),
    ("sc_task",       "-5",  "Pendente",              "aguardando"),
]


@pytest.mark.parametrize("tabela,cru,rotulo,esperado", ESTADOS_MEDIDOS)
def test_estado_medido_cai_na_coluna_certa(tabela, cru, rotulo, esperado):
    assert mapear_estado(tabela, cru) == esperado, (
        f"{tabela}/{cru} ({rotulo}) deveria cair em '{esperado}'")


def test_pendente_nao_volta_a_ser_novo():
    """A regressão que estamos consertando, nomeada.

    '-5' em sc_task apontava para 'novo': o chamado PARADO esperando aparecia
    como recém-chegado. É pior que cair em 'outros' — 'outros' admite que não
    sabe, e ninguém desconfia de um card na coluna Novo.
    """
    assert mapear_estado("sc_task", "-5") == "aguardando"
    assert mapear_estado("sc_task", "-5") != "novo"


def test_pendente_do_ritm_sai_de_outros():
    """Em sc_req_item o '-5' nem existia no mapa: 'Pendente' caía em 'outros'
    enquanto a coluna Aguardando ficava vazia."""
    assert mapear_estado("sc_req_item", "-5") == "aguardando"


def test_a_coluna_aguardando_tem_quem_a_ocupe():
    """Coluna que nunca recebe ninguém é coluna que não deveria existir — ou,
    como era o caso, sintoma de mapeamento errado. Cada tabela que o espelho
    cobre precisa ter ao menos um estado apontando para 'aguardando'."""
    for tabela, _tipo in TABELAS:
        destinos = set(ESTADOS[tabela].values())
        assert "aguardando" in destinos, (
            f"{tabela} não tem nenhum estado mapeado para 'aguardando'")


# ═══════════ 8. conteúdo do chamado (migration 091, F2) ═════════════════════
# Sem descrição e work notes não há triagem — nem por IA nem por heurística.
# O que estes testes prendem é o caminho do dado da API até a coluna, e as
# duas formas de perdê-lo em silêncio: campo que a origem não manda, e texto
# grande que estoura a coluna.

def test_campos_de_conteudo_sao_pedidos_a_api():
    """Coluna nova sem campo no sysparm_fields = coluna NULL para sempre,
    com o ciclo VERDE. O pedido à API é parte do contrato."""
    for campo in ("description", "work_notes", "cat_item", "requested_for",
                  "estimated_delivery", "due_date", "u_sla_expired"):
        assert campo in CAMPOS, f"{campo} precisa estar no sysparm_fields"


def test_conteudo_chega_ao_espelho():
    linha = normalizar(_registro(
        description={"display_value": "Preciso da tabela DM_123", "value": "Preciso da tabela DM_123"},
        work_notes={"display_value": "dia a dia - bug", "value": "dia a dia - bug"},
        cat_item={"display_value": "Extração de dados", "value": "c1"},
        requested_for={"display_value": "Jeferson Bortoletto", "value": "u9"},
        estimated_delivery={"display_value": "20/08/2026", "value": "2026-08-20 00:00:00"},
        due_date={"display_value": "22/08/2026", "value": "2026-08-22 00:00:00"},
        u_sla_expired={"display_value": "false", "value": "false"},
    ), "sc_req_item", "ritm", URL)
    assert linha["descricao"] == "Preciso da tabela DM_123"
    assert linha["work_notes"] == "dia a dia - bug"
    assert linha["catalogo"] == "Extração de dados"
    assert linha["demandante"] == "Jeferson Bortoletto"
    assert linha["prazo"] == _dt.datetime(2026, 8, 20, 0, 0)
    assert linha["vencimento"] == _dt.datetime(2026, 8, 22, 0, 0)
    assert linha["sla_vencido"] == 0


def test_conteudo_ausente_nao_quebra_e_vira_vazio():
    """incident não tem cat_item nem u_sla_expired: a Table API simplesmente
    omite o campo. Isso não pode derrubar a normalização."""
    linha = normalizar(_registro(), "incident", "incident", URL)
    assert linha["descricao"] == ""
    assert linha["catalogo"] == ""
    assert linha["prazo"] is None
    assert linha["sla_vencido"] is None, "ausente é None, nunca 0"


def test_sla_vencido_distingue_ausente_de_falso():
    """None ('ninguém mediu') e 0 ('mediu e está no prazo') são estados
    diferentes; colapsá-los faria a tela afirmar o que não sabe."""
    from utils.servicenow_sync import _booleano
    assert _booleano("true") == 1
    assert _booleano("false") == 0
    assert _booleano("") is None
    assert _booleano(None) is None


def test_texto_longo_e_cortado_com_reticencia():
    from utils.servicenow_sync import TEXTO_MAX, truncar_texto
    gigante = "x" * (TEXTO_MAX + 500)
    cortado = truncar_texto(gigante)
    assert len(cortado) == TEXTO_MAX
    assert cortado.endswith("…"), "o corte precisa ser visível"


def test_descricao_gigante_cabe_na_coluna():
    """NVARCHAR(4000): estourar aqui é erro de gravação no meio do ciclo."""
    from utils.servicenow_sync import TEXTO_MAX
    enorme = "detalhe " * 2000
    linha = normalizar(_registro(
        description={"display_value": enorme, "value": enorme},
        work_notes={"display_value": enorme, "value": enorme},
    ), "incident", "incident", URL)
    assert len(linha["descricao"]) <= TEXTO_MAX
    assert len(linha["work_notes"]) <= TEXTO_MAX


def test_upsert_grava_os_campos_novos():
    """O MERGE precisa carregar as colunas da 091 — campo normalizado que não
    entra no upsert é trabalho jogado fora, e a coluna fica NULL."""
    from utils.servicenow_sync import CAMPOS_UPSERT
    for campo in ("descricao", "work_notes", "catalogo", "demandante",
                  "prazo", "vencimento", "sla_vencido"):
        assert campo in CAMPOS_UPSERT
        assert f"{campo}=%s" in upsert_sql(), f"{campo} ausente no UPDATE"


def test_normalizar_entrega_todos_os_campos_do_upsert():
    """A ponte entre normalizar() e CAMPOS_UPSERT: campo listado num e não no
    outro dá KeyError no meio do ciclo, com metade da fila já gravada."""
    from utils.servicenow_sync import CAMPOS_UPSERT
    linha = normalizar(_registro(), "incident", "incident", URL)
    faltando = [c for c in CAMPOS_UPSERT if c not in linha]
    assert not faltando, f"normalizar() não devolve: {faltando}"


# ═══════════ 9. o limite é da COLUNA, não do Python ═════════════════════════

def test_truncamento_conta_unidades_utf16():
    """NVARCHAR(n) conta unidades UTF-16: emoji fora do BMP ocupa DUAS. Medir
    com len() deixa passar 4000 caracteres que ocupam 4300 unidades, e o SQL
    Server responde Msg 8152 no meio do ciclo — com o texto colado do Teams
    que a migration 091 diz esperar."""
    from utils.servicenow_sync import TEXTO_MAX, truncar_texto, unidades_utf16
    texto = "a" * 3500 + "🙂" * 300 + "b" * 500
    saida = truncar_texto(texto)
    assert unidades_utf16(saida) <= TEXTO_MAX
    assert saida.endswith("…")


def test_truncamento_nao_parte_emoji_ao_meio():
    """Cortar dentro de um par substituto produz texto inválido no banco."""
    from utils.servicenow_sync import truncar_texto, unidades_utf16
    saida = truncar_texto("🙂" * 50, limite=11)
    assert unidades_utf16(saida) <= 11
    assert saida.encode("utf-16-le").decode("utf-16-le") == saida


def test_titulo_com_emoji_respeita_o_limite_da_coluna():
    from utils.servicenow_sync import TITULO_MAX, unidades_utf16
    assert unidades_utf16(truncar_titulo("ção🔥" * 200)) <= TITULO_MAX


# ═══════════ estados terminais do sc_req_item ═══════════════════════════════
# Portado da F1: a correção que produção já tinha e a main não.

def test_ritm_closed_complete_e_terminal_e_nao_aguardando():
    """`state=3` em sc_req_item é "Closed Complete": CONCLUÍDO.

    A main mapeava para 'aguardando'. Medido no espelho do dev em 2026-08-28:
    **1472 RITMs** "Encerrado concluído" carregavam esse rótulo. Eles têm
    ativo=0, então não poluíam a FILA — o estrago estava nas contas que
    agrupam por estado_kanban sobre o espelho inteiro (histórico, entradas ×
    saídas, resolvidos do período), onde chamado concluído era somado como
    chamado esperando alguém.

    'encerrado' é FORA_DO_KANBAN: sai da fila e continua no espelho, que é
    exatamente o que um pedido concluído deve fazer.
    """
    assert mapear_estado("sc_req_item", "3") == "encerrado"
    assert mapear_estado("sc_req_item", 3) == "encerrado"


def test_o_terminal_do_ritm_nao_contaminou_as_outras_tabelas():
    """Cada tabela tem seu próprio mapa — `3` significa coisas diferentes.

    Em sc_task, `3` é "Closed Complete" e o espelho o trata como 'resolvido'
    (fica na fila, na coluna Resolvido); em incident, `3` é "On Hold". Aplicar
    a correção do RITM às outras moveria card em silêncio.
    """
    assert mapear_estado("sc_task", "3") == "resolvido"
    assert mapear_estado("incident", "3") == "aguardando"


def test_ritm_closed_incomplete_tambem_e_terminal():
    """`4` é "Closed Incomplete": encerrado SEM entregar — e encerrado é final.

    Ficava em 'aguardando' pelo mesmo motivo que o `3`. Depois de corrigir só
    o `3`, a coluna caiu de 1568 para 96 no espelho do dev — e **84 dos 96**
    eram estes. Produção também erra este: a correção de lá parou no `3`.
    """
    assert mapear_estado("sc_req_item", "4") == "encerrado"


def test_o_que_sobra_em_aguardando_e_o_que_a_palavra_quer_dizer():
    """`-5` é "Pendente" — pedido vivo, parado esperando alguém. É o único que
    deve pintar a coluna Aguardando; foram 12 no espelho do dev, contra os 96
    de antes desta correção."""
    assert mapear_estado("sc_req_item", "-5") == "aguardando"
    assert mapear_estado("sc_req_item", "2") == "andamento"
    assert mapear_estado("sc_req_item", "1") == "novo"


def test_o_estado_nao_visto_fica_como_estava():
    """`5` não apareceu no espelho, e mexer em estado que não se viu é palpite
    — o mesmo palpite que pôs o `3` e o `4` em 'aguardando'."""
    assert mapear_estado("sc_req_item", "5") == "aguardando"


# ═══════════ O SOLICITANTE ══════════════════════════════════════════════════
#
# "uma informação que precisamos colocar no card… o nome do solicitante."
#
# ⚠️ O nome do campo MUDA POR TABELA: a `sc_req_item` guarda em
# `requested_for`, o `incident` em `caller_id`. Lendo só o primeiro, todo
# incidente ficava sem solicitante — medido em dev antes da correção: 0 de 2
# incidentes preenchidos, contra 55 de 55 RITMs.

def _ref(nome):
    """Referência como a Table API devolve: display_value + value."""
    return {"display_value": nome, "value": "sys_user_abc"}


def test_o_ritm_traz_o_solicitante_de_requested_for():
    linha = normalizar(_registro(requested_for=_ref("Thieser Leal de Sousa")),
                       "sc_req_item", "ritm", "https://x.service-now.com")
    assert linha["demandante"] == "Thieser Leal de Sousa"


def test_o_incidente_traz_o_solicitante_de_caller_id():
    """O DEFEITO. `incident` não tem `requested_for`."""
    linha = normalizar(_registro(caller_id=_ref("Tiago Henrique Gatto")),
                       "incident", "incident", "https://x.service-now.com")
    assert linha["demandante"] == "Tiago Henrique Gatto"


def test_requested_for_tem_precedencia_sobre_caller_id():
    """Onde os dois existem, quem PEDIU é o `requested_for` — o `caller_id`
    pode ser quem ligou para abrir em nome de outra pessoa."""
    linha = normalizar(
        _registro(requested_for=_ref("Quem Pediu"), caller_id=_ref("Quem Ligou")),
        "sc_req_item", "ritm", "https://x.service-now.com")
    assert linha["demandante"] == "Quem Pediu"


def test_sem_nenhum_dos_dois_o_solicitante_fica_vazio():
    """A tarefa não tem o campo. Vazio é resposta — a tela DIZ "sem
    solicitante" em vez de inventar um."""
    linha = normalizar(_registro(), "sc_task", "task", "https://x.service-now.com")
    assert linha["demandante"] == ""


def test_o_campo_do_solicitante_e_pedido_na_consulta():
    """Normalizar certo não basta: se `caller_id` não estiver na lista de
    `sysparm_fields`, a API nunca o devolve e a normalização recebe vazio —
    com a DAG verde e a coluna em branco."""
    assert "caller_id" in CAMPOS
    assert "requested_for" in CAMPOS
