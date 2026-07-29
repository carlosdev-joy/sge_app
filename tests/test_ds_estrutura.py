"""
Análise de dependência dos jobs filhos (dags/utils/ds_estrutura.py).

O CASO REAL que motivou tudo: uma sequence monitorada termina com
"Finished OK" tendo um job filho ABORTADO. O DataStage não propaga a falha do
filho para o pai, o acompanhamento diário dá o dia como bom e o abort passa
despercebido.

Estes testes travam o veredito que a ferramenta não dá: sucesso REAL exige que
nenhum job abaixo tenha abortado.

Também cobrem as duas defesas contra alarme falso:
  • frequência — job condicional (que só roda alguns dias) não vira "faltou";
  • amostra mínima — nos primeiros dias a estrutura ainda está sendo aprendida,
    e cobrar ausência aí seria alarme sobre um mapa incompleto.
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import pytest

_DAGS = Path(__file__).parent.parent / "dags"
if str(_DAGS) not in sys.path:
    sys.path.insert(0, str(_DAGS))

from utils.ds_logsum import ABORTADO, EXECUTANDO, OK, DsRun, parse_logsum  # noqa: E402
from utils.ds_estrutura import (  # noqa: E402
    AMOSTRA_MINIMA, CODIGOS_DE_FALHA, Estrutura, FilhoEsperado, aprender,
    filhos_ausentes, filhos_que_falharam, resumo_dependencia, sucesso_real,
)

SUCESSO, AVISOS, ABORT, CRASH, PARADO = 1, 2, 3, 96, 97


def _run(filhos: dict, resultado: str = OK) -> DsRun:
    r = DsRun(inicio=datetime(2026, 7, 27, 2, 10), fim=datetime(2026, 7, 27, 2, 50),
              resultado=resultado, jobs_filhos=len(filhos))
    r.filhos = dict(filhos)
    r.filhos_abortados = [n for n, c in filhos.items() if c == ABORT]
    return r


def _estrutura(execucoes: int, filhos: dict[str, int]) -> Estrutura:
    return Estrutura(execucoes_aprendidas=execucoes,
                     filhos=[FilhoEsperado(n, c) for n, c in filhos.items()])


# ── O parser precisa entregar os filhos com status ──────────────────────────

def test_parser_expoe_o_status_de_cada_filho():
    log = """
   1001 STARTED       Mon Jul 27 02:10:00 2026
Starting Job SeqPai.
   1002 INFO          Mon Jul 27 02:20:00 2026
SeqPai..JobControl (@C): Job FilhoA has finished, status = 1 (Finished OK)
   1003 INFO          Mon Jul 27 02:30:00 2026
SeqPai..JobControl (@C): Job FilhoB has finished, status = 3 (Aborted)
   1004 STARTED       Mon Jul 27 02:50:00 2026
Finished Job SeqPai.
"""
    run = parse_logsum(log)[0]
    # A sequence disse OK...
    assert run.resultado == OK
    # ...mas o filho abortado está lá, e é isso que permite desmentir o OK.
    assert run.filhos == {"FilhoA": 1, "FilhoB": 3}


# ── Sucesso real ────────────────────────────────────────────────────────────

def test_sequence_ok_com_todos_os_filhos_ok_e_sucesso_real():
    assert sucesso_real(_run({"A": SUCESSO, "B": SUCESSO})) is True


def test_sequence_ok_com_filho_abortado_NAO_e_sucesso():
    # O caso de produção: o DataStage esconde isso, aqui não passa.
    assert sucesso_real(_run({"A": SUCESSO, "B": ABORT})) is False


def test_filho_com_avisos_nao_invalida_o_sucesso():
    assert sucesso_real(_run({"A": SUCESSO, "B": AVISOS})) is True


def test_sequence_abortada_nunca_e_sucesso():
    assert sucesso_real(_run({"A": SUCESSO}, resultado=ABORTADO)) is False


def test_sequence_em_execucao_nao_e_sucesso():
    assert sucesso_real(_run({"A": SUCESSO}, resultado=EXECUTANDO)) is False


@pytest.mark.parametrize("codigo,falha", [
    (SUCESSO, False), (AVISOS, False), (ABORT, True),
    (CRASH, False), (PARADO, False), (-1, False),
])
def test_apenas_abort_conta_como_falha_hoje(codigo, falha):
    # Decisão do usuário: só o abort (3) alerta. Crash e parado são GRAVADOS e
    # aparecem no painel, mas não geram card — ampliar é acrescentar o código
    # em CODIGOS_DE_FALHA.
    assert (filhos_que_falharam(_run({"X": codigo})) == ["X"]) is falha


def test_codigos_de_falha_e_explicitamente_so_o_abort():
    assert CODIGOS_DE_FALHA == frozenset({ABORT})


def test_filhos_que_falharam_vem_ordenado():
    run = _run({"Zulu": ABORT, "Alfa": ABORT, "Bravo": SUCESSO})
    assert filhos_que_falharam(run) == ["Alfa", "Zulu"]


# ── Aprendizado da estrutura ────────────────────────────────────────────────

def test_execucao_boa_ensina_a_estrutura():
    ok, nomes = aprender(_run({"A": SUCESSO, "B": SUCESSO}))
    assert ok is True
    assert nomes == ["A", "B"]


def test_execucao_com_filho_abortado_NAO_ensina():
    # Aprender de um dia ruim gravaria a falha como se fosse o fluxo normal.
    ok, nomes = aprender(_run({"A": SUCESSO, "B": ABORT}))
    assert ok is False and nomes == []


def test_execucao_sem_filhos_nao_ensina():
    assert aprender(_run({})) == (False, [])


def test_sequence_abortada_nao_ensina():
    assert aprender(_run({"A": SUCESSO}, resultado=ABORTADO))[0] is False


# ── Frequência e amostra mínima ─────────────────────────────────────────────

def test_estrutura_nova_nao_cobra_ausencia():
    # Com menos execuções que a amostra mínima, o mapa ainda está se formando.
    estrutura = _estrutura(AMOSTRA_MINIMA - 1, {"A": 2, "B": 2})
    assert estrutura.madura is False
    assert filhos_ausentes(_run({"A": SUCESSO}), estrutura) == []


def test_job_sempre_presente_ausente_vira_alerta():
    estrutura = _estrutura(10, {"A": 10, "B": 10})
    assert filhos_ausentes(_run({"A": SUCESSO}), estrutura) == ["B"]


def test_job_condicional_nao_vira_alerta():
    # "B" só roda em 2 de 10 execuções (job mensal, ramo condicional): a
    # ausência dele é normal e não pode acordar ninguém.
    estrutura = _estrutura(10, {"A": 10, "B": 2})
    assert filhos_ausentes(_run({"A": SUCESSO}), estrutura) == []


def test_frequencia_no_limite_ainda_e_cobrada():
    estrutura = _estrutura(10, {"A": 10, "B": 8})     # 80%
    assert filhos_ausentes(_run({"A": SUCESSO}), estrutura) == ["B"]


def test_frequencia_logo_abaixo_do_limite_nao_e_cobrada():
    estrutura = _estrutura(10, {"A": 10, "B": 7})     # 70%
    assert filhos_ausentes(_run({"A": SUCESSO}), estrutura) == []


def test_estrutura_vazia_nao_cobra_nada():
    assert filhos_ausentes(_run({"A": SUCESSO}), Estrutura()) == []


def test_frequencia_de_job_desconhecido_e_zero():
    assert _estrutura(10, {"A": 10}).frequencia("NaoExiste") == 0.0


# ── Resumo para painel e mensagens ──────────────────────────────────────────

def test_resumo_separa_ok_falhou_e_ausente():
    estrutura = _estrutura(10, {"A": 10, "B": 10, "C": 10})
    resumo = resumo_dependencia(_run({"A": SUCESSO, "B": ABORT}), estrutura)

    assert resumo["total_filhos"] == 2
    assert resumo["filhos_ok"] == ["A"]
    assert resumo["filhos_falharam"] == ["B"]
    assert resumo["filhos_ausentes"] == ["C"]
    assert resumo["sequence_disse_ok"] is True      # o que o DataStage reportou
    assert resumo["sucesso_real"] is False          # o que de fato aconteceu


def test_resumo_de_execucao_boa():
    estrutura = _estrutura(10, {"A": 10, "B": 10})
    resumo = resumo_dependencia(_run({"A": SUCESSO, "B": AVISOS}), estrutura)
    assert resumo["sucesso_real"] is True
    assert resumo["filhos_falharam"] == []
    assert sorted(resumo["filhos_ok"]) == ["A", "B"]
