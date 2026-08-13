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
    COLUNAS_KANBAN, ESTADOS, TABELAS, TITULO_MAX,
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


def test_titulo_com_acento_e_emoji_conta_caracteres():
    """NVARCHAR guarda caractere, não byte — o limite é em caracteres."""
    texto = "ção🔥" * 200
    assert len(truncar_titulo(texto)) == TITULO_MAX


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
    linha = normalizar(_registro(), "incident", "incident", URL)
    p = upsert_params(linha)
    assert p[0] == linha["sys_id"], "o 1º parâmetro é a chave do MERGE"
    # 1 chave + 13 do UPDATE + 13 do INSERT
    assert len(p) == 27
    assert p[1:14] == p[14:27], "UPDATE e INSERT recebem os mesmos valores"
    assert p[1] == linha["numero"] and p[14] == linha["numero"]


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
