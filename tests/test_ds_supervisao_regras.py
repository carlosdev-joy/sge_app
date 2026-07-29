"""
Regras da supervisão de jobs DataStage (dags/utils/ds_supervisao_regras.py).

É aqui que mora o risco da feature: classificar o dia errado significa acordar
alguém de madrugada à toa, ou — pior — ficar calado num job que não rodou.

Os casos que os testes travam:
  • janela que cruza a meia-noite pertence ao dia em que COMEÇA;
  • ATRASO enquanto o dia está aberto, NAO_EXECUTOU quando ele fecha;
  • dia fora dos dias da semana e data anterior à vigência não geram nada;
  • o card de situação inicial sai mesmo quando está tudo certo.
"""
from __future__ import annotations

import sys
from datetime import date, datetime, time
from pathlib import Path

import pytest

_DAGS = Path(__file__).parent.parent / "dags"
if str(_DAGS) not in sys.path:
    sys.path.insert(0, str(_DAGS))

from utils.ds_logsum import ABORTADO, OK, DsRun  # noqa: E402
from utils.ds_supervisao_regras import (  # noqa: E402
    ABORTOU, ATRASO, ESTRUTURA, NAO_EXECUTOU, SITUACAO_INICIAL,
    JobSupervisionado, avaliar, avaliar_dia, datas_candidatas, descrever_dia,
    dias_ativos, evento_estrutura, evento_situacao_inicial, janela_do_dia,
    roda_no_dia, runs_do_dia,
)

# 2026-07-27 é uma segunda-feira; 2026-08-01, um sábado.
SEGUNDA = date(2026, 7, 27)
SABADO  = date(2026, 8, 1)


def job(**kwargs) -> JobSupervisionado:
    base = dict(
        id=1, project="BI_CVP", job_name="SeqSsdVida7Peps",
        janela_inicio=time(2, 0), janela_fim=time(3, 0), tolerancia_min=0,
        dias_semana="1,2,3,4,5", vigencia_inicio=date(2026, 7, 1), max_linhas=200,
    )
    base.update(kwargs)
    return JobSupervisionado(**base)


def run(inicio: datetime, fim: datetime | None = None, resultado: str = OK,
        filhos_abortados: list[str] | None = None) -> DsRun:
    r = DsRun(inicio=inicio, fim=fim, resultado=resultado, jobs_filhos=1)
    r.filhos_abortados = filhos_abortados or []
    return r


# ── Dias da semana ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("csv,esperado", [
    ("1,2,3,4,5", {1, 2, 3, 4, 5}),
    ("6,7", {6, 7}),
    (" 1 , 1 , 2 ", {1, 2}),
    ("", set()),
    ("abc,0,9", set()),          # lixo é ignorado, não explode
    ("1,abc,3", {1, 3}),
])
def test_dias_ativos(csv, esperado):
    assert dias_ativos(csv) == esperado


def test_roda_no_dia_respeita_o_cadastro():
    j = job(dias_semana="1,2,3,4,5")
    assert roda_no_dia(j, SEGUNDA) is True
    assert roda_no_dia(j, SABADO) is False


# ── Janela ──────────────────────────────────────────────────────────────────

def test_janela_normal():
    inicio, fim, limite = janela_do_dia(job(), SEGUNDA)
    assert inicio == datetime(2026, 7, 27, 2, 0)
    assert fim == datetime(2026, 7, 27, 3, 0)
    assert limite == fim                      # sem tolerância


def test_janela_com_tolerancia():
    _i, fim, limite = janela_do_dia(job(tolerancia_min=30), SEGUNDA)
    assert (limite - fim).total_seconds() == 1800


def test_janela_que_cruza_a_meia_noite_termina_no_dia_seguinte():
    inicio, fim, _l = janela_do_dia(job(janela_inicio=time(23, 0), janela_fim=time(1, 0)), SEGUNDA)
    assert inicio == datetime(2026, 7, 27, 23, 0)
    assert fim == datetime(2026, 7, 28, 1, 0)


def test_janela_de_24h_nao_colapsa():
    # início == fim seria janela de duração zero; tratamos como dia inteiro.
    inicio, fim, _l = janela_do_dia(job(janela_inicio=time(2, 0), janela_fim=time(2, 0)), SEGUNDA)
    assert fim - inicio == (datetime(2026, 7, 28, 2, 0) - datetime(2026, 7, 27, 2, 0))


# ── Datas candidatas ────────────────────────────────────────────────────────

def test_datas_candidatas_traz_ontem_e_hoje():
    agora = datetime(2026, 7, 28, 10, 0)      # terça de manhã
    assert datas_candidatas(job(), agora) == [date(2026, 7, 27), date(2026, 7, 28)]


def test_datas_candidatas_pula_dia_nao_supervisionado():
    agora = datetime(2026, 8, 1, 10, 0)       # sábado
    # Sexta (31/07) entra; sábado não.
    assert datas_candidatas(job(), agora) == [date(2026, 7, 31)]


def test_datas_candidatas_ignora_dia_anterior_a_vigencia():
    agora = datetime(2026, 7, 28, 10, 0)
    assert datas_candidatas(job(vigencia_inicio=date(2026, 7, 28)), agora) == [date(2026, 7, 28)]


def test_datas_candidatas_nao_cobra_janela_que_nao_comecou():
    agora = datetime(2026, 7, 28, 1, 0)       # 01h, antes da janela das 02h
    assert date(2026, 7, 28) not in datas_candidatas(job(), agora)


def test_vigencia_futura_nao_gera_nada():
    agora = datetime(2026, 7, 28, 10, 0)
    j = job(vigencia_inicio=date(2026, 8, 15))
    assert datas_candidatas(j, agora) == []
    assert avaliar(j, [], agora) == []


# ── Atribuição de runs ao dia ───────────────────────────────────────────────

def test_run_dentro_da_janela_pertence_ao_dia():
    r = run(datetime(2026, 7, 27, 2, 30), datetime(2026, 7, 27, 2, 50))
    assert runs_do_dia(job(), SEGUNDA, [r]) == [r]


def test_run_atrasado_ainda_pertence_ao_dia():
    # Começou 3h depois do fim da janela: é o run daquele dia, atrasado.
    r = run(datetime(2026, 7, 27, 6, 0), datetime(2026, 7, 27, 6, 20))
    assert runs_do_dia(job(), SEGUNDA, [r]) == [r]


def test_run_do_dia_seguinte_nao_vaza_para_o_dia_anterior():
    r = run(datetime(2026, 7, 28, 2, 30), datetime(2026, 7, 28, 2, 50))
    assert runs_do_dia(job(), SEGUNDA, [r]) == []


def test_run_de_madrugada_pertence_ao_dia_em_que_a_janela_comecou():
    j = job(janela_inicio=time(23, 0), janela_fim=time(1, 0))
    r = run(datetime(2026, 7, 28, 0, 30), datetime(2026, 7, 28, 0, 50))
    assert runs_do_dia(j, SEGUNDA, [r]) == [r]        # segunda 23h → terça 00h30
    assert runs_do_dia(j, date(2026, 7, 28), [r]) == []


# ── Classificação ───────────────────────────────────────────────────────────

def test_dia_com_run_ok_nao_gera_evento():
    r = run(datetime(2026, 7, 27, 2, 10), datetime(2026, 7, 27, 2, 50))
    assert avaliar_dia(job(), SEGUNDA, [r], datetime(2026, 7, 27, 8, 0)) == []


def test_run_abortado_gera_evento_com_chave_do_horario():
    r = run(datetime(2026, 7, 27, 2, 10), datetime(2026, 7, 27, 2, 15),
            resultado=ABORTADO, filhos_abortados=["SsdVidaCarga"])
    eventos = avaliar_dia(job(), SEGUNDA, [r], datetime(2026, 7, 27, 8, 0))
    assert len(eventos) == 1
    assert eventos[0].tipo == ABORTOU
    assert eventos[0].chave_ocorrencia == "2026-07-27 02:10:00"
    assert "SsdVidaCarga" in eventos[0].detalhe
    assert eventos[0].run_inicio == r.inicio


def test_dois_abortos_no_mesmo_dia_sao_ocorrencias_distintas():
    r1 = run(datetime(2026, 7, 27, 2, 10), datetime(2026, 7, 27, 2, 15), resultado=ABORTADO)
    r2 = run(datetime(2026, 7, 27, 4, 10), datetime(2026, 7, 27, 4, 15), resultado=ABORTADO)
    eventos = avaliar_dia(job(), SEGUNDA, [r1, r2], datetime(2026, 7, 27, 8, 0))
    assert len(eventos) == 2
    assert len({e.chave_ocorrencia for e in eventos}) == 2


def test_sem_run_dentro_do_prazo_nao_alerta():
    # 02h30: a janela vai até 03h, ainda dá tempo.
    assert avaliar_dia(job(), SEGUNDA, [], datetime(2026, 7, 27, 2, 30)) == []


def test_sem_run_depois_do_limite_gera_atraso():
    eventos = avaliar_dia(job(), SEGUNDA, [], datetime(2026, 7, 27, 3, 15))
    assert [e.tipo for e in eventos] == [ATRASO]
    assert "não iniciou até 03:00" in eventos[0].detalhe


def test_tolerancia_adia_o_atraso():
    j = job(tolerancia_min=30)
    assert avaliar_dia(j, SEGUNDA, [], datetime(2026, 7, 27, 3, 15)) == []
    assert [e.tipo for e in avaliar_dia(j, SEGUNDA, [], datetime(2026, 7, 27, 3, 40))] == [ATRASO]


def test_dia_fechado_sem_run_vira_nao_executou():
    # 24h depois do início da janela: o dia acabou.
    eventos = avaliar_dia(job(), SEGUNDA, [], datetime(2026, 7, 28, 3, 0))
    assert [e.tipo for e in eventos] == [NAO_EXECUTOU]
    assert eventos[0].data_ref == SEGUNDA


def test_flags_desligadas_silenciam_o_alerta():
    r = run(datetime(2026, 7, 27, 2, 10), datetime(2026, 7, 27, 2, 15), resultado=ABORTADO)
    assert avaliar_dia(job(alerta_abortou=False), SEGUNDA, [r], datetime(2026, 7, 27, 8, 0)) == []
    assert avaliar_dia(job(alerta_atraso=False), SEGUNDA, [], datetime(2026, 7, 27, 3, 15)) == []
    assert avaliar_dia(job(alerta_nao_executou=False), SEGUNDA, [], datetime(2026, 7, 28, 3, 0)) == []


# ── Situação inicial ────────────────────────────────────────────────────────

def test_situacao_inicial_sai_mesmo_com_tudo_normal():
    j = job(vigencia_inicio=SEGUNDA)
    r = run(datetime(2026, 7, 27, 2, 10), datetime(2026, 7, 27, 2, 50))
    ev = evento_situacao_inicial(j, [r], datetime(2026, 7, 27, 8, 0))
    assert ev is not None
    assert ev.tipo == SITUACAO_INICIAL
    assert ev.data_ref == SEGUNDA
    assert ev.chave_ocorrencia == ""          # um por vigência
    assert "executou 02:10 → 02:50" in ev.detalhe


def test_situacao_inicial_avisa_quando_a_janela_ainda_nao_chegou():
    j = job(vigencia_inicio=SEGUNDA)
    ev = evento_situacao_inicial(j, [], datetime(2026, 7, 27, 1, 0))
    assert "janela ainda não começou" in ev.detalhe


def test_situacao_inicial_em_dia_nao_supervisionado_explica_a_configuracao():
    # Vigência num sábado com job de seg–sex: o card ainda sai, e é ele que
    # mostra ao usuário que a configuração não cobre aquele dia.
    j = job(vigencia_inicio=SABADO)
    ev = evento_situacao_inicial(j, [], datetime(2026, 8, 1, 10, 0))
    assert ev is not None
    assert "não roda neste dia da semana" in ev.detalhe


def test_situacao_inicial_nao_sai_antes_da_vigencia():
    j = job(vigencia_inicio=date(2026, 8, 15))
    assert evento_situacao_inicial(j, [], datetime(2026, 7, 28, 10, 0)) is None


def test_avaliar_junta_situacao_inicial_e_alertas():
    j = job(vigencia_inicio=SEGUNDA)
    eventos = avaliar(j, [], datetime(2026, 7, 27, 3, 30))
    tipos = [e.tipo for e in eventos]
    assert SITUACAO_INICIAL in tipos and ATRASO in tipos


# ── Estrutura ───────────────────────────────────────────────────────────────

def test_evento_estrutura_e_categoria_propria():
    ev = evento_estrutura(job(), SEGUNDA, "dsjob retornou 255: project not found")
    assert ev.tipo == ESTRUTURA
    assert ev.tipo != ABORTOU
    assert "BI_CVP.SeqSsdVida7Peps" in ev.detalhe
    assert "project not found" in ev.detalhe


def test_evento_estrutura_trunca_motivo_gigante():
    ev = evento_estrutura(job(), SEGUNDA, "x" * 5000)
    assert len(ev.detalhe) <= 1000            # cabe no NVARCHAR(1000) da coluna


# ── Descrição legível ───────────────────────────────────────────────────────

# ── Análise de dependência integrada ao dia (F5) ────────────────────────────

def _com_filhos(inicio, filhos, resultado=OK):
    r = run(inicio, inicio.replace(hour=inicio.hour + 1), resultado=resultado)
    r.filhos = dict(filhos)
    r.filhos_abortados = [n for n, c in filhos.items() if c == 3]
    r.jobs_filhos = len(filhos)
    return r


def _estrutura_madura(filhos: dict[str, int], execucoes: int = 10):
    from utils.ds_estrutura import Estrutura, FilhoEsperado
    return Estrutura(execucoes_aprendidas=execucoes,
                     filhos=[FilhoEsperado(n, c) for n, c in filhos.items()])


def test_sequence_ok_com_filho_abortado_gera_sucesso_falso():
    # O caso de produção: o DataStage deu "concluído" e escondeu o abort.
    from utils.ds_supervisao_regras import SUCESSO_FALSO

    r = _com_filhos(datetime(2026, 7, 27, 2, 10), {"CargaA": 1, "CargaB": 3})
    eventos = avaliar_dia(job(), SEGUNDA, [r], datetime(2026, 7, 27, 8, 0))

    assert [e.tipo for e in eventos] == [SUCESSO_FALSO]
    assert "CargaB" in eventos[0].detalhe
    assert eventos[0].run_inicio == r.inicio


def test_sequence_abortada_nao_vira_sucesso_falso():
    # Já é falha declarada — dois alertas para o mesmo problema seria ruído.
    from utils.ds_supervisao_regras import SUCESSO_FALSO

    r = _com_filhos(datetime(2026, 7, 27, 2, 10), {"CargaB": 3}, resultado=ABORTADO)
    tipos = [e.tipo for e in avaliar_dia(job(), SEGUNDA, [r], datetime(2026, 7, 27, 8, 0))]
    assert tipos == [ABORTOU]
    assert SUCESSO_FALSO not in tipos


def test_execucao_boa_de_verdade_nao_gera_evento():
    r = _com_filhos(datetime(2026, 7, 27, 2, 10), {"CargaA": 1, "CargaB": 2})
    estrutura = _estrutura_madura({"CargaA": 10, "CargaB": 10})
    assert avaliar_dia(job(), SEGUNDA, [r], datetime(2026, 7, 27, 8, 0), estrutura) == []


def test_job_do_fluxo_que_nao_rodou_gera_filho_ausente():
    from utils.ds_supervisao_regras import FILHO_AUSENTE

    r = _com_filhos(datetime(2026, 7, 27, 2, 10), {"CargaA": 1})
    estrutura = _estrutura_madura({"CargaA": 10, "CargaB": 10})
    eventos = avaliar_dia(job(), SEGUNDA, [r], datetime(2026, 7, 27, 8, 0), estrutura)

    assert [e.tipo for e in eventos] == [FILHO_AUSENTE]
    assert "CargaB" in eventos[0].detalhe


def test_sem_estrutura_aprendida_nao_cobra_ausencia():
    r = _com_filhos(datetime(2026, 7, 27, 2, 10), {"CargaA": 1})
    assert avaliar_dia(job(), SEGUNDA, [r], datetime(2026, 7, 27, 8, 0), None) == []


def test_flags_de_dependencia_desligadas_silenciam():
    r = _com_filhos(datetime(2026, 7, 27, 2, 10), {"CargaA": 1, "CargaB": 3})
    estrutura = _estrutura_madura({"CargaA": 10, "CargaB": 10, "CargaC": 10})

    assert avaliar_dia(job(alerta_sucesso_falso=False, alerta_filho_ausente=False),
                       SEGUNDA, [r], datetime(2026, 7, 27, 8, 0), estrutura) == []


def test_sucesso_falso_e_ausencia_podem_coexistir():
    from utils.ds_supervisao_regras import FILHO_AUSENTE, SUCESSO_FALSO

    r = _com_filhos(datetime(2026, 7, 27, 2, 10), {"CargaA": 1, "CargaB": 3})
    estrutura = _estrutura_madura({"CargaA": 10, "CargaB": 10, "CargaC": 10})
    tipos = {e.tipo for e in avaliar_dia(job(), SEGUNDA, [r],
                                         datetime(2026, 7, 27, 8, 0), estrutura)}
    assert tipos == {SUCESSO_FALSO, FILHO_AUSENTE}


def test_descrever_dia_cobre_os_cenarios():
    j = job()
    agora = datetime(2026, 7, 27, 8, 0)
    ok = run(datetime(2026, 7, 27, 2, 10), datetime(2026, 7, 27, 2, 50))
    assert "executou" in descrever_dia(j, SEGUNDA, [ok], agora)

    ab = run(datetime(2026, 7, 27, 2, 10), datetime(2026, 7, 27, 2, 15), resultado=ABORTADO)
    assert "ABORTOU" in descrever_dia(j, SEGUNDA, [ab], agora)

    assert "NÃO iniciou" in descrever_dia(j, SEGUNDA, [], agora)
    assert "não roda neste dia" in descrever_dia(j, SABADO, [], datetime(2026, 8, 1, 10, 0))
