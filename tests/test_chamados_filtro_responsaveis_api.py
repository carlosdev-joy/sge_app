"""O recorte por responsável da aba de Indicadores aceita VÁRIOS nomes.

    "no responsavel no indicadores, permitir filtrar com checkbox, podendo
     filtrar mais de uma opção por exemplo."

Este filtro é o único da aba e vale para TODAS as agregações dela — aging,
tipo × estado, fluxo, carga, categorias, histórico. Um filtro que alcança
metade das contas produz uma aba onde o aging fala de uma pessoa e o fluxo de
todas, com os dois números parecendo certos. Por isso ele mora numa função só,
e por isso ela é testada sozinha.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "api"))

mod = importlib.import_module("routers.chamados")
SR = mod.SEM_RESPONSAVEL


# ═══════════ 1. sem recorte ═════════════════════════════════════════════════

@pytest.mark.parametrize("vazio", [None, [], "", "   ", ["", "  "]])
def test_sem_nome_nao_ha_recorte(vazio) -> None:
    """Cláusula vazia é o que faz a aba falar da fila inteira. Um `AND ()`
    solto seria erro de sintaxe e derrubaria a aba toda."""
    assert mod._filtro_responsavel(vazio) == ("", [])


# ═══════════ 2. um nome ═════════════════════════════════════════════════════

def test_um_nome_vira_parametro_e_nao_texto_na_query() -> None:
    """Nome interpolado no SQL é injeção esperando acontecer — e nomes têm
    apóstrofo (D'Ávila)."""
    sql, params = mod._filtro_responsavel(["Ana"])
    assert params == ["Ana"]
    assert "Ana" not in sql
    assert sql.count("?") == 1


def test_a_forma_antiga_de_string_unica_continua_valendo() -> None:
    """A URL antiga mandava `?responsavel=Ana`, e um link salvo por alguém
    não pode passar a devolver a fila inteira em silêncio."""
    assert mod._filtro_responsavel("Ana") == mod._filtro_responsavel(["Ana"])


# ═══════════ 3. vários nomes ════════════════════════════════════════════════

def test_dois_nomes_geram_dois_parametros() -> None:
    sql, params = mod._filtro_responsavel(["Ana", "Bruno"])
    assert params == ["Ana", "Bruno"]
    assert sql.count("?") == 2
    assert "IN (?, ?)" in sql


def test_os_nomes_se_somam_com_OU_e_nao_com_E() -> None:
    """`atribuido_a = 'Ana' AND atribuido_a = 'Bruno'` não casa com ninguém —
    e a aba mostraria zeros, que parecem "estas pessoas não têm chamados"."""
    sql, _ = mod._filtro_responsavel(["Ana", "Bruno"])
    assert " AND " not in sql.replace(" AND (", "(", 1), (
        "só o AND que abre a cláusula; entre os nomes é IN/OR")


def test_nome_repetido_nao_duplica_o_parametro() -> None:
    """Marcar duas vezes o mesmo nome (ou um clique duplo) não pode mudar a
    contagem de `?` — o pyodbc casa por POSIÇÃO, e um `?` a mais desalinha
    todos os parâmetros das consultas que já tinham os seus."""
    sql, params = mod._filtro_responsavel(["Ana", "Ana"])
    assert params == ["Ana"]
    assert sql.count("?") == 1


def test_espacos_ao_redor_do_nome_sao_aparados() -> None:
    assert mod._filtro_responsavel([" Ana "])[1] == ["Ana"]


# ═══════════ 4. "sem responsável" é condição, não valor ═════════════════════

def test_sem_responsavel_nao_vira_parametro() -> None:
    """O banco guarda NULL ou vazio. Comparar com a string "sem responsável"
    — que é rótulo de TELA — não acharia ninguém, e a aba mostraria zeros."""
    sql, params = mod._filtro_responsavel([SR])
    assert params == []
    assert sql.count("?") == 0
    assert "IS NULL" in sql


def test_sem_responsavel_cobre_o_vazio_alem_do_nulo() -> None:
    """O espelho guarda ora NULL, ora string de espaços."""
    sql, _ = mod._filtro_responsavel([SR])
    assert "NULLIF(LTRIM(RTRIM(atribuido_a)), '')" in sql


def test_nome_e_sem_responsavel_juntos_perguntam_pelos_DOIS() -> None:
    """Marcar "Ana" e "sem responsável" pergunta pelos dois conjuntos. Ligados
    por E, seria a interseção vazia — e a tela mostraria nada com cara de
    resposta."""
    sql, params = mod._filtro_responsavel(["Ana", SR])
    assert params == ["Ana"]
    assert " OR " in sql
    assert "IN (?)" in sql and "IS NULL" in sql


# ═══════════ 5. a forma da cláusula ═════════════════════════════════════════

@pytest.mark.parametrize("nomes", [["Ana"], ["Ana", "Bruno"], [SR], ["Ana", SR]])
def test_a_clausula_vem_parentizada(nomes) -> None:
    """⚠️ Sem os parênteses, `AND a OR b` faz o OR engolir todo o WHERE que
    veio antes — inclusive `ativo = 1` e o recorte de trabalhos. A aba passaria
    a contar chamados encerrados sem que nada na tela mudasse de aparência."""
    sql, _ = mod._filtro_responsavel(nomes)
    corpo = sql.strip()
    assert corpo.startswith("AND ("), corpo
    assert corpo.endswith(")"), corpo


@pytest.mark.parametrize("nomes", [["Ana"], ["Ana", "Bruno"], [SR], ["Ana", SR]])
def test_a_clausula_comeca_e_termina_com_espaco(nomes) -> None:
    """Ela é concatenada no meio de uma query montada por pedaços: sem os
    espaços, vira `WHERE ativo = 1AND (…)`."""
    sql, _ = mod._filtro_responsavel(nomes)
    assert sql.startswith(" ") and sql.endswith(" ")
