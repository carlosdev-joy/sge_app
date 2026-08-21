"""Derivações do chamado (dags/utils/chamado_derivacoes.py) — F3.

Estas três leituras vinham do painel da estação e agora são coluna. O que os
testes prendem:

  1. **Nada fica sem tipo.** Quem não casa com padrão nenhum recebe
     'Demanda técnica'. String vazia faria a soma do gráfico por tipo não
     fechar com o total da fila, e ninguém saberia dizer se faltou dado ou
     faltou classificação.
  2. **"Sem marcação" ≠ "geral".** Chamado que ninguém classificou devolve
     vazio; chamado marcado como dia a dia sem categoria devolve 'geral'.
     Colapsar os dois inventaria classificação que ninguém fez.
  3. **O journal não vira categoria.** As work notes concatenam entradas: sem
     cortar na primeira linha, a "categoria" viraria o histórico inteiro.
  4. **Objeto repetido conta uma vez** e a ordem do texto é preservada.

Nada aqui toca rede, banco ou Airflow.
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "dags"))

from utils.chamado_derivacoes import (  # noqa: E402
    CATEGORIA_GERAL, OBJETOS_LIMITE, TIPO_MAX, TIPO_PADRAO,
    categoria_diaadia, derivar, objetos_citados, tipo_demanda,
)


# ═══════════ 1. tipo de demanda ═════════════════════════════════════════════

def test_tipo_vem_do_titulo():
    assert tipo_demanda("Inclusão de coluna na DM_123") == "Inclusão de coluna/campo"
    assert tipo_demanda("Extração de dados para auditoria") == "Extração de dados"
    assert tipo_demanda("Enriquecimento BUCC") == "Enriquecimento de dados"


def test_tipo_aceita_titulo_sem_acento():
    """Quem abre chamado digita sem acento com frequência; exigir o acento
    jogaria esses chamados no rótulo genérico."""
    assert tipo_demanda("Inclusao de coluna na tabela") == "Inclusão de coluna/campo"
    assert tipo_demanda("Extracao de dados") == "Extração de dados"


def test_catalogo_e_a_segunda_chance():
    """Título genérico + catálogo específico: o catálogo salva a
    classificação."""
    assert tipo_demanda("Solicitação de dados", "Extração de dados") == "Extração de dados"


def test_titulo_manda_sobre_catalogo():
    assert tipo_demanda("Restauração do servidor", "Consulta de dados") == \
        "Restauração banco/servidor"


def test_desconhecido_recebe_rotulo_e_nao_vazio():
    """Vazio quebraria a soma do gráfico contra o total da fila."""
    assert tipo_demanda("Coisa que ninguém previu") == TIPO_PADRAO
    assert tipo_demanda("") == TIPO_PADRAO
    assert tipo_demanda(None) == TIPO_PADRAO


def test_tipo_cabe_na_coluna():
    for titulo in ("Inclusão de coluna", "processamento de arquivo", "bucc", "x"):
        assert len(tipo_demanda(titulo)) <= TIPO_MAX


# ═══════════ 2. categoria "dia a dia" ═══════════════════════════════════════

def test_categoria_com_rotulo():
    assert categoria_diaadia("dia a dia - bug") == "bug"
    assert categoria_diaadia("Dia a Dia - Ajuste Pontual") == "ajuste pontual"


def test_categoria_aceita_travessao_longo():
    """Quem digita no ServiceNow usa hífen e en-dash; aceitar só um jogaria
    metade das marcações no balde genérico."""
    assert categoria_diaadia("dia a dia – bug") == "bug"


def test_marcacao_sem_categoria_vira_geral():
    assert categoria_diaadia("resolvido no dia a dia") == CATEGORIA_GERAL


def test_sem_marcacao_fica_vazio():
    """Vazio e 'geral' são estados diferentes: um é 'ninguém classificou', o
    outro é 'classificado como dia a dia, sem categoria'."""
    assert categoria_diaadia("Chamado seguindo o rito normal") == ""
    assert categoria_diaadia("") == ""
    assert categoria_diaadia(None) == ""


def test_categoria_para_na_primeira_linha():
    """O journal concatena entradas — sem o corte, a categoria viraria o
    histórico inteiro do chamado."""
    notas = "dia a dia - bug\n2026-08-13 Fulano escreveu:\noutra coisa qualquer"
    assert categoria_diaadia(notas) == "bug"


def test_categoria_perde_o_ponto_final():
    assert categoria_diaadia("dia a dia - melhoria.") == "melhoria"


# ═══════════ 3. objetos técnicos citados ════════════════════════════════════

def test_objetos_reconhece_a_nomenclatura_do_ambiente():
    texto = "Favor incluir coluna em DMDB41..TB_CLIENTE e atualizar a VW_SALDO"
    assert objetos_citados(texto) == "DMDB41..TB_CLIENTE, VW_SALDO"


def test_objeto_repetido_conta_uma_vez():
    texto = "A TB_CLIENTE precisa de ajuste; depois valide TB_CLIENTE de novo"
    assert objetos_citados(texto) == "TB_CLIENTE"


def test_objetos_respeitam_o_limite():
    texto = " ".join(f"TB_UM{i}" for i in range(10))
    assert len(objetos_citados(texto).split(", ")) == OBJETOS_LIMITE


def test_nome_com_digito_nao_e_recortado():
    """O regex do painel era `TB_[A-Z_]+`: `TB_CLIENTE2` virava `TB_CLIENTE`,
    que é OUTRA tabela existente. Apontar para o objeto errado em silêncio é
    pior do que não capturar nada."""
    assert objetos_citados("ajustar TB_CLIENTE2") == "TB_CLIENTE2"
    assert objetos_citados("ver DM_123_VIDA2 hoje") == "DM_123_VIDA2"


def test_descricao_sem_objeto_fica_vazia():
    assert objetos_citados("preciso de um relatório novo") == ""
    assert objetos_citados(None) == ""


# ═══════════ 4. a ponte com o sync ══════════════════════════════════════════

def test_derivar_devolve_as_tres_colunas():
    saida = derivar({
        "titulo": "Extração de dados do prestamista",
        "catalogo": "Consulta de dados",
        "work_notes": "dia a dia - bug",
        "descricao": "puxar de DM_123_VIDA",
    })
    assert saida == {
        "tipo_demanda": "Extração de dados",
        "categoria_diaadia": "bug",
        "objetos": "DM_123_VIDA",
    }


def test_derivar_com_campos_ausentes_nao_quebra():
    """Chamado sem descrição nem work notes é caso comum — e a 091 nasce com
    as colunas NULL para tudo que já estava no espelho."""
    saida = derivar({})
    assert saida["tipo_demanda"] == TIPO_PADRAO
    assert saida["categoria_diaadia"] == ""
    assert saida["objetos"] == ""


def test_normalizar_ja_traz_as_derivacoes():
    """A derivação acontece na INGESTÃO: se normalizar() não a fizer, as
    colunas ficam NULL com o ciclo verde."""
    from utils.servicenow_sync import CAMPOS_UPSERT, normalizar
    registro = {
        "sys_id": {"value": "abc", "display_value": "abc"},
        "number": {"display_value": "RITM0001", "value": "RITM0001"},
        "short_description": {"display_value": "Inclusão de coluna na DM_9",
                              "value": "Inclusão de coluna na DM_9"},
        "state": {"display_value": "Em aberto", "value": "1"},
        "active": {"display_value": "true", "value": "true"},
        "description": {"display_value": "mexer em DM_9_TESTE", "value": "mexer em DM_9_TESTE"},
        "work_notes": {"display_value": "dia a dia - melhoria", "value": "dia a dia - melhoria"},
    }
    linha = normalizar(registro, "sc_req_item", "ritm", "https://x.service-now.com")
    assert linha["tipo_demanda"] == "Inclusão de coluna/campo"
    assert linha["categoria_diaadia"] == "melhoria"
    assert linha["objetos"] == "DM_9_TESTE"
    for campo in ("tipo_demanda", "categoria_diaadia", "objetos"):
        assert campo in CAMPOS_UPSERT, f"{campo} precisa entrar no MERGE"


# ═══════════ 5. o que a revisão adversarial pegou ═══════════════════════════

def test_travessao_no_fim_da_linha_nao_captura_a_linha_seguinte():
    """`\\s*` depois do travessão casava quebra de linha: a frase inteira do
    técnico virava 'categoria' e enchia o gráfico de barras de uso único."""
    notas = "dia a dia -\nFavor verificar a tabela DM_123 conforme combinado"
    assert categoria_diaadia(notas) == CATEGORIA_GERAL


def test_marcacao_com_categoria_vazia_vira_geral():
    """'dia a dia - .' é marcação SEM categoria, não ausência de marcação."""
    assert categoria_diaadia("dia a dia - .") == CATEGORIA_GERAL


def test_objeto_precisa_de_borda_a_esquerda():
    """Sem borda à esquerda, `DBTB_VENDAS` virava `TB_VENDAS` — nome de outro
    objeto, que existe. O mesmo defeito do sufixo, do outro lado."""
    assert objetos_citados("reprocessar DBTB_VENDAS hoje") == ""
    assert objetos_citados("ver ADM_123_X depois") == ""
    assert objetos_citados("ajustar sub_vw_teste") == ""
    # E o caso legítimo continua capturado:
    assert objetos_citados("ajustar a TB_VENDAS hoje") == "TB_VENDAS"
