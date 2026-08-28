"""Dois defeitos achados em produção logo depois do deploy.

    "faça a correção do solicitante na lista do dashboard, esta todos como
     vazia, e além disso o informativo do sincronização frescor esta em
     produção com 117h, imagino que ele aponte para uma dag que não é a que
     rodamos com frequencia (delta né) … ou a mais recente entre elas deve ser
     informada"

## 1. A coluna Solicitante saía vazia em TODA linha do painel

Defeito de POSIÇÃO, do tipo mais silencioso que existe. O `_COLS` da rota
passou a trazer `demandante` no lugar de `tipo_demanda`, e a tela passou a ler
`c.demandante` — mas a linha do meio, que monta o dicionário a partir da tupla,
continuou gravando na chave `tipo_demanda`.

Nada quebrou: a consulta funcionou, a rota respondeu 200, o JSON veio completo.
A tela lia um campo que não existia, e em JavaScript campo ausente é
`undefined` — que passa direto pelo `c.demandante || 'sem solicitante'` e
RENDERIZA O TEXTO DE AUSÊNCIA como se fosse a verdade do dado. A tela estava
afirmando "sem solicitante" sobre 55 chamados que têm um.

⚠️ `tsc` não pega: a tupla do banco não tem tipo. O teste do front não pega: o
dublê monta o objeto à mão. Só um teste que atravessa a rota INTEIRA pega.

## 2. O frescor lia a tabela da DAG errada

O módulo tem duas gerações de motor convivendo:

| DAG | ritmo | grava em |
|---|---|---|
| `etl_servicenow_sync`  | 15 min  | `etl_chamado_sync` |
| `etl_servicenow_delta` | **5 min** | `etl_chamado_ciclo` |
| `etl_servicenow_full`  | diária  | **as duas** |

O carimbo lia SÓ a `etl_chamado_sync`. Onde a `sync` foi desligada em favor da
`delta` — que é o desenho novo —, a tela passou a dizer "sincronizado há 117h"
com o espelho sendo atualizado a cada 5 minutos.

O número não estava errado sobre a tabela que ele lia: ele respondia a pergunta
errada. E o dano não é cosmético — `atrasado` alimenta o aviso âmbar de
"integração parada", e alarme que dispara sozinho todo dia é o que ensina a
ignorar o dia em que ela realmente parar.
"""
from __future__ import annotations

import datetime as dt
import importlib
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "api"))

mod = importlib.import_module("routers.chamados")


# ═══════════ 1. o frescor escolhe o ciclo mais recente ══════════════════════

class CursorDoFrescor:
    """Dublê que responde diferente para cada uma das duas tabelas."""

    def __init__(self, nova=None, antiga=None,
                 explode_nova=False, explode_antiga=False):
        self.nova = nova
        self.antiga = antiga
        self.explode_nova = explode_nova
        self.explode_antiga = explode_antiga
        self._alvo = None

    def execute(self, sql, params=None):
        if "etl_chamado_ciclo" in sql:
            self._alvo = "nova"
            if self.explode_nova:
                raise RuntimeError("Invalid object name 'dbo.etl_chamado_ciclo'")
        else:
            self._alvo = "antiga"
            if self.explode_antiga:
                raise RuntimeError("Invalid object name 'dbo.etl_chamado_sync'")

    def fetchone(self):
        return self.nova if self._alvo == "nova" else self.antiga


def _linha_nova(iniciado, idade_min, status="OK", terminado=True, qtd=3443):
    # id, iniciado_em, terminado_em, status, qtd_chamados, qtd_desativados,
    # erro, modo, idade_min
    return (10, iniciado, iniciado if terminado else None, status, qtd, 0,
            None, "delta", idade_min)


def _linha_antiga(iniciado, idade_min, status="OK"):
    # id, iniciado_em, terminado_em, status, qtd_incident, qtd_ritm, qtd_task,
    # qtd_change, qtd_desativados, erro, idade_min
    return (7, iniciado, iniciado, status, 2, 55, 34, 0, 0, None, idade_min)


AGORA = dt.datetime(2026, 8, 28, 20, 0, 0)
HA_5_MIN = AGORA - dt.timedelta(minutes=5)
HA_117_H = AGORA - dt.timedelta(hours=117)


def test_o_frescor_escolhe_o_ciclo_mais_recente() -> None:
    """⚠️ O DEFEITO RELATADO. A `delta` roda a cada 5 minutos e a tela dizia
    117h porque lia a tabela da DAG antiga, desligada."""
    cur = CursorDoFrescor(nova=_linha_nova(HA_5_MIN, 5),
                          antiga=_linha_antiga(HA_117_H, 7020))
    ciclo = mod._ultimo_ciclo(cur)
    assert ciclo["idade_minutos"] == 5
    assert ciclo["fonte"] == "delta"


def test_a_tabela_antiga_ainda_vence_quando_e_a_mais_recente() -> None:
    """A escolha é por DATA, não por tabela preferida. Onde a `sync` ainda
    roda e a `delta` não foi ligada, o carimbo tem de vir dela."""
    cur = CursorDoFrescor(nova=_linha_nova(HA_117_H, 7020),
                          antiga=_linha_antiga(HA_5_MIN, 5))
    ciclo = mod._ultimo_ciclo(cur)
    assert ciclo["idade_minutos"] == 5
    assert ciclo["fonte"] == "sync"


def test_a_escolha_nao_depende_do_FORMATO_da_data(monkeypatch) -> None:
    """A comparação usa o `datetime` CRU, não a string formatada.

    ⚠️ CORREÇÃO DE UMA JUSTIFICATIVA MINHA QUE ESTAVA ERRADA. A primeira versão
    deste teste dizia que comparar o texto ordenaria por dia do mês — e a
    sabotagem que trocava o cru pelo formatado PASSOU. Fui ver: `_fmt_dt` é
    `str(v)[:19]`, ou seja ISO (`2026-09-05 08:00:00`), e ISO ordena como texto
    na mesma ordem que como data. A justificativa era falsa; o teste, vazio.

    O que importa de verdade é a INDEPENDÊNCIA: hoje o formato é ISO por acaso
    do `str()` de um datetime. No dia em que alguém trocar `_fmt_dt` por um
    formato brasileiro — que é o formato da casa em toda a tela — a comparação
    por texto passaria a ordenar por dia do mês, em silêncio. Este teste força
    esse dia a acontecer agora."""
    monkeypatch.setattr(mod, "_fmt_dt",
                        lambda v: v.strftime("%d/%m/%Y %H:%M") if v else None)
    fim_do_mes = dt.datetime(2026, 8, 28, 20, 0, 0)        # "28/08/…"
    inicio_do_seguinte = dt.datetime(2026, 9, 5, 8, 0, 0)  # "05/09/…" — menor!
    cur = CursorDoFrescor(nova=_linha_nova(inicio_do_seguinte, 10),
                          antiga=_linha_antiga(fim_do_mes, 11000))
    assert mod._ultimo_ciclo(cur)["idade_minutos"] == 10, (
        "escolheu o ciclo mais VELHO — a comparação caiu no texto formatado")


def test_sem_a_tabela_nova_o_carimbo_continua_de_pe() -> None:
    """A `etl_chamado_ciclo` chegou na migration 096. Onde ela ainda não
    passou, faltar a tabela não pode calar a outra — seria trocar um carimbo
    velho por carimbo NENHUM, e aí a tela não sabe nem dizer que está velha."""
    cur = CursorDoFrescor(antiga=_linha_antiga(HA_5_MIN, 5), explode_nova=True)
    ciclo = mod._ultimo_ciclo(cur)
    assert ciclo is not None
    assert ciclo["idade_minutos"] == 5


def test_sem_a_tabela_antiga_o_carimbo_continua_de_pe() -> None:
    """A `sync` pode ser descontinuada — é o caminho previsto."""
    cur = CursorDoFrescor(nova=_linha_nova(HA_5_MIN, 5), explode_antiga=True)
    assert mod._ultimo_ciclo(cur)["idade_minutos"] == 5


def test_sem_nenhuma_das_duas_devolve_None() -> None:
    """`None` é o que a tela traduz em "nunca sincronizado" — diferente de
    "sincronizado há muito tempo"."""
    cur = CursorDoFrescor(explode_nova=True, explode_antiga=True)
    assert mod._ultimo_ciclo(cur) is None
    assert mod._ultimo_ciclo(CursorDoFrescor()) is None


def test_ciclo_sem_termino_e_marcado_como_em_andamento() -> None:
    """"nunca terminou" é worker morto no meio; "terminou com erro" é a
    integração recusando. A tela diz coisas diferentes para cada um."""
    cur = CursorDoFrescor(nova=_linha_nova(HA_5_MIN, 5, terminado=False))
    assert mod._ultimo_ciclo(cur)["em_andamento"] is True


def test_o_atraso_e_calculado_sobre_o_ciclo_ESCOLHIDO() -> None:
    """⚠️ O `atrasado` alimenta o aviso âmbar de "integração parada". Calculado
    sobre a tabela errada, ele dispara todo dia — e alarme que dispara sozinho
    é o que ensina a ignorar o dia em que a integração realmente parar."""
    recente = CursorDoFrescor(nova=_linha_nova(HA_5_MIN, 5),
                              antiga=_linha_antiga(HA_117_H, 7020))
    assert mod._ultimo_ciclo(recente)["atrasado"] is False

    parado = CursorDoFrescor(nova=_linha_nova(HA_117_H, 7020),
                             antiga=_linha_antiga(HA_117_H, 7020))
    assert mod._ultimo_ciclo(parado)["atrasado"] is True, (
        "quando as DUAS estão velhas, o alarme PRECISA disparar")


def test_o_ciclo_diz_de_qual_motor_veio(cen=None) -> None:
    """Sem isso, "sincronizado há 5 min" não deixa distinguir qual DAG está
    viva — que foi a pergunta que levou uma hora para responder."""
    cur = CursorDoFrescor(nova=_linha_nova(HA_5_MIN, 5))
    assert mod._ultimo_ciclo(cur)["fonte"] == "delta"


# ═══════════ 2. o solicitante chega à lista do painel ═══════════════════════

def test_o_painel_devolve_o_solicitante_na_chave_que_a_tela_le() -> None:
    """⚠️ O DEFEITO. O `_COLS_PAINEL` trazia `demandante` na posição 9 e o
    dicionário gravava em `tipo_demanda`. A tela lia `c.demandante`, não
    achava, e `undefined || 'sem solicitante'` renderizava o texto de AUSÊNCIA
    em toda linha — afirmando "sem solicitante" sobre chamados que têm um.

    O teste exercita a MONTAGEM, não a lista: uma asserção só sobre os nomes
    das colunas provaria que o SELECT está certo e não que o dicionário
    acompanhou — que é exatamente o que quebrou."""
    linha = (
        "sys1", "RITM0103367", "Ajuste em tabela",
        "Kenzo Matsuzaki", "andamento",
        dt.datetime(2026, 9, 2, 10, 0), dt.datetime(2026, 8, 20, 9, 0),
        "https://sn/x", 0,
        "Thieser Leal de Sousa",                       # ← posição 9
        "kenzo@cvp", None, dt.datetime(2026, 8, 28, 12, 0),
    )
    saida = mod._linha_do_painel(linha)
    assert saida["demandante"] == "Thieser Leal de Sousa"


def test_a_posicao_9_do_select_e_o_demandante() -> None:
    """A outra metade da correspondência: se a COLUNA sair de lugar, a chave
    passa a receber outro valor sem que nada falhe."""
    colunas = [c.strip() for c in mod._COLS_PAINEL.split(",")]
    assert colunas[9] == "demandante"


def test_a_quantidade_de_colunas_bate_com_a_montagem() -> None:
    """13 colunas, índices 0..12. Uma coluna a mais no SELECT sem a chave
    correspondente entra no JSON como nada — e uma a menos faz o
    `_linha_do_painel` estourar IndexError na primeira linha."""
    assert len([c.strip() for c in mod._COLS_PAINEL.split(",")]) == 13


def test_o_painel_nao_traz_mais_tipo_demanda() -> None:
    """Ele repetia o título e saiu para dar lugar ao solicitante."""
    assert "tipo_demanda" not in mod._COLS_PAINEL
    linha = tuple(range(13))
    assert "tipo_demanda" not in mod._linha_do_painel(linha)


def test_solicitante_ausente_vira_string_vazia_e_nao_None() -> None:
    """A tela decide o texto de ausência ("sem solicitante"). Mandar `None`
    daria `null` no JSON, e a distinção entre "não tem" e "não veio" ficaria
    a cargo de quem lê."""
    linha = list(range(13))
    linha[9] = None
    assert mod._linha_do_painel(tuple(linha))["demandante"] == ""
