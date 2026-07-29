"""
Mensagens configuráveis dos alertas da supervisão (dags/utils/ds_mensagens.py).

Dois riscos cobertos aqui:

  1. **Divergência de catálogo.** As variáveis existem em dois lugares — no
     módulo da DAG (que interpola) e no router da API (que mostra na tela) —
     porque API e Airflow rodam em containers separados e não compartilham
     código. Se as listas divergirem, a tela oferece uma variável que a coleta
     não sabe substituir, e o placeholder cru chega ao canal do Teams.
  2. **Texto do usuário derrubando o alerta.** Mensagem com variável inexistente
     ou chave solta não pode explodir a interpolação: o alerta torto ainda é
     melhor que alerta nenhum.
"""
from __future__ import annotations

import os
import sys
from datetime import date, datetime, time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_ROOT = Path(__file__).parent.parent
_DAGS = _ROOT / "dags"
if str(_DAGS) not in sys.path:
    sys.path.insert(0, str(_DAGS))

if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()
os.environ.setdefault("MSSQL_CONN_STR", "__mock__")
from api.main import app as _app  # noqa: F401,E402

from utils.ds_logsum import ABORTADO, OK, DsRun  # noqa: E402
from utils.ds_mensagens import (  # noqa: E402
    MENSAGENS_PADRAO, NOMES_VARIAVEIS, VARIAVEIS, interpolar, montar_contexto,
    montar_mensagem, variaveis_desconhecidas,
)
from utils.ds_supervisao_regras import (  # noqa: E402
    ABORTOU, ATRASO, ESTRUTURA, NAO_EXECUTOU, SITUACAO_INICIAL, JobSupervisionado,
)

SEGUNDA = date(2026, 7, 27)


def _job(**kw) -> JobSupervisionado:
    base = dict(id=1, project="BI_CVP", job_name="SeqSsdVida7Peps",
                janela_inicio=time(2, 0), janela_fim=time(3, 0), tolerancia_min=15,
                dias_semana="1,2,3,4,5", vigencia_inicio=SEGUNDA,
                descricao="Carga diária de vida")
    base.update(kw)
    return JobSupervisionado(**base)


def _run(inicio, fim=None, resultado=OK):
    return DsRun(inicio=inicio, fim=fim, resultado=resultado, jobs_filhos=1)


# ── Paridade entre os catálogos da DAG e da API ─────────────────────────────

def test_catalogo_de_variaveis_e_identico_na_api_e_na_dag():
    from routers.ds_supervisao import VARIAVEIS_MENSAGEM

    assert VARIAVEIS == VARIAVEIS_MENSAGEM, (
        "Catálogos divergiram: a tela ofereceria variável que a coleta não substitui. "
        "Atualize dags/utils/ds_mensagens.py e api/routers/ds_supervisao.py juntos."
    )


def test_tipos_de_mensagem_batem_com_os_tipos_de_evento():
    from routers.ds_supervisao import TIPOS_MENSAGEM

    assert set(TIPOS_MENSAGEM) == set(MENSAGENS_PADRAO)
    assert set(TIPOS_MENSAGEM) == {ABORTOU, NAO_EXECUTOU, ATRASO, ESTRUTURA, SITUACAO_INICIAL}


def test_todo_tipo_de_alerta_tem_mensagem_padrao():
    for tipo in (ABORTOU, NAO_EXECUTOU, ATRASO, ESTRUTURA, SITUACAO_INICIAL):
        assert MENSAGENS_PADRAO[tipo].strip()


def test_mensagens_padrao_so_usam_variaveis_do_catalogo():
    for tipo, texto in MENSAGENS_PADRAO.items():
        assert variaveis_desconhecidas(texto) == [], f"{tipo} usa variável fora do catálogo"


# ── Interpolação ────────────────────────────────────────────────────────────

def test_interpolar_substitui_o_que_conhece():
    assert interpolar("{job} às {inicio}", {"job": "SeqA", "inicio": "02:10"}) == "SeqA às 02:10"


def test_interpolar_mantem_variavel_desconhecida_literal():
    # Erro de digitação não pode impedir o alerta de sair; o texto torto mostra
    # ao usuário exatamente o que corrigir.
    assert interpolar("{job} {tolerancia_min}", {"job": "SeqA"}) == "SeqA {tolerancia_min}"


@pytest.mark.parametrize("texto", ["", None])
def test_interpolar_tolera_texto_vazio(texto):
    assert interpolar(texto, {"job": "SeqA"}) == ""


def test_interpolar_nao_se_perde_com_chave_solta():
    assert interpolar("100% de { chaves } soltas {job}", {"job": "X"}) == "100% de { chaves } soltas X"


def test_variaveis_desconhecidas_lista_ordenada_e_sem_repeticao():
    assert variaveis_desconhecidas("{zzz} {aaa} {zzz} {job}") == ["aaa", "zzz"]


# ── Contexto ────────────────────────────────────────────────────────────────

def test_contexto_traz_janela_tolerancia_e_limite():
    ctx = montar_contexto(_job(), ATRASO, SEGUNDA, [], datetime(2026, 7, 27, 3, 30))
    assert ctx["janela_inicio"] == "02:00"
    assert ctx["janela_fim"] == "03:00"
    assert ctx["tolerancia"] == "15"
    assert ctx["limite"] == "03:15"          # fim + tolerância
    assert ctx["dias"] == "seg, ter, qua, qui, sex"
    assert ctx["projeto"] == "BI_CVP"
    assert ctx["descricao"] == "Carga diária de vida"


def test_contexto_sem_execucao_usa_travessao_em_vez_de_sumir():
    ctx = montar_contexto(_job(), NAO_EXECUTOU, SEGUNDA, [], datetime(2026, 7, 28, 4, 0))
    assert ctx["inicio"] == "—" and ctx["fim"] == "—" and ctx["duracao"] == "—"


def test_contexto_usa_o_run_indicado_e_nao_o_ultimo():
    primeiro = _run(datetime(2026, 7, 27, 2, 10), datetime(2026, 7, 27, 2, 15), ABORTADO)
    ultimo = _run(datetime(2026, 7, 27, 6, 0), datetime(2026, 7, 27, 6, 40))
    ctx = montar_contexto(_job(), ABORTOU, SEGUNDA, [primeiro, ultimo],
                          datetime(2026, 7, 27, 8, 0), run=primeiro)
    assert ctx["inicio"] == "02:10"          # o abort, não a execução seguinte
    assert ctx["fim"] == "02:15"


def test_contexto_sem_run_indicado_usa_a_ultima_execucao():
    ctx = montar_contexto(_job(), ABORTOU, SEGUNDA,
                          [_run(datetime(2026, 7, 27, 2, 10), datetime(2026, 7, 27, 2, 50))],
                          datetime(2026, 7, 27, 8, 0))
    assert ctx["inicio"] == "02:10" and ctx["duracao"] == "40 min"


def test_duracao_longa_sai_em_horas():
    ctx = montar_contexto(_job(), ABORTOU, SEGUNDA,
                          [_run(datetime(2026, 7, 27, 2, 0), datetime(2026, 7, 27, 4, 30))],
                          datetime(2026, 7, 27, 8, 0))
    assert ctx["duracao"] == "2h30m"


# ── Mensagem final ──────────────────────────────────────────────────────────

def test_mensagem_cadastrada_vence_o_padrao():
    texto = montar_mensagem(
        _job(), ATRASO, SEGUNDA, [], datetime(2026, 7, 27, 3, 30),
        mensagens={ATRASO: "Job {job} atrasou! Janela {janela_inicio}-{janela_fim}, "
                           "tolerância {tolerancia} min, limite {limite}."})
    assert texto == ("Job SeqSsdVida7Peps atrasou! Janela 02:00-03:00, "
                     "tolerância 15 min, limite 03:15.")


def test_mensagem_em_branco_cai_no_padrao():
    texto = montar_mensagem(_job(), ATRASO, SEGUNDA, [], datetime(2026, 7, 27, 3, 30),
                            mensagens={ATRASO: "   "})
    assert "não iniciou até 03:15" in texto


def test_sem_mensagem_cadastrada_usa_o_padrao_do_tipo():
    texto = montar_mensagem(_job(), NAO_EXECUTOU, SEGUNDA, [], datetime(2026, 7, 28, 4, 0))
    assert "não executou" in texto
    assert "02:00–03:00" in texto
    assert "{" not in texto                  # tudo interpolado


def test_mensagem_de_abort_traz_horarios_do_run():
    run = _run(datetime(2026, 7, 27, 2, 10), datetime(2026, 7, 27, 2, 15), ABORTADO)
    texto = montar_mensagem(_job(), ABORTOU, SEGUNDA, [run],
                            datetime(2026, 7, 27, 8, 0), run=run)
    assert "02:10" in texto and "02:15" in texto


def test_mensagem_de_situacao_inicial_descreve_o_dia():
    run = _run(datetime(2026, 7, 27, 2, 10), datetime(2026, 7, 27, 2, 50))
    texto = montar_mensagem(_job(), SITUACAO_INICIAL, SEGUNDA, [run],
                            datetime(2026, 7, 27, 8, 0))
    assert "Monitoramento iniciado" in texto
    assert "executou 02:10 → 02:50" in texto


def test_mensagem_do_usuario_com_variavel_invalida_ainda_e_enviada():
    texto = montar_mensagem(_job(), ATRASO, SEGUNDA, [], datetime(2026, 7, 27, 3, 30),
                            mensagens={ATRASO: "{job} falhou: {nao_existe}"})
    assert texto == "SeqSsdVida7Peps falhou: {nao_existe}"


def test_situacao_pode_ser_injetada_de_fora():
    texto = montar_mensagem(_job(), ESTRUTURA, SEGUNDA, [], datetime(2026, 7, 27, 8, 0),
                            situacao="projeto BI_XXX não existe")
    assert "projeto BI_XXX não existe" in texto


def test_todas_as_variaveis_do_catalogo_existem_no_contexto():
    ctx = montar_contexto(_job(), ATRASO, SEGUNDA, [], datetime(2026, 7, 27, 3, 30))
    faltando = [n for n in NOMES_VARIAVEIS if n not in ctx]
    assert faltando == [], f"variáveis anunciadas mas sem valor: {faltando}"
