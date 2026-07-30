"""
Varredura dos níveis abaixo do job supervisionado (expansão profunda).

CASO REAL, observado no painel em 2026-07-29 e reproduzido aqui:

    BI_PRESTAMISTA.SeqSsdPrs_CargaDiaria ....... "Concluído"   (supervisionado)
      └── SeqSsdPrs_Dim ....................... "concluído"    (nível 1)
            └── SeqSsdPrs_DimSocios ........... "Concluído"    (nível 2)
                  └── SsdPrs_DimSocios_01_ext .. ABORTED       (nível 3)

Dois pontos que estes testes travam:

  1. **A varredura tem de ser em LARGURA.** Nenhum job do nível 1 aparece
     falhado — descer apenas pela cadeia de aborts (como faz o "Causa-raiz" do
     console) não encontraria nada.
  2. **O veredito tem de olhar todos os níveis.** Enquanto olhava só os filhos
     diretos, o dia inteiro era dado como bom.
"""
from __future__ import annotations

import importlib.util
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_ROOT = Path(__file__).parent.parent
_DAGS = _ROOT / "dags"
if str(_DAGS) not in sys.path:
    sys.path.insert(0, str(_DAGS))

_STUBS = [
    "airflow", "airflow.models", "airflow.operators", "airflow.operators.python",
    "airflow.providers", "airflow.providers.ssh", "airflow.providers.ssh.hooks",
    "airflow.providers.ssh.hooks.ssh",
    "airflow.providers.microsoft", "airflow.providers.microsoft.mssql",
    "airflow.providers.microsoft.mssql.hooks", "airflow.providers.microsoft.mssql.hooks.mssql",
    "pendulum",
]
for _m in _STUBS:
    sys.modules.setdefault(_m, MagicMock())
sys.modules["airflow"].DAG = MagicMock()
sys.modules["airflow"].DAG.return_value.__enter__ = lambda self: self
sys.modules["airflow"].DAG.return_value.__exit__ = lambda self, *a: False


def _carregar_dag():
    spec = importlib.util.spec_from_file_location(
        "etl_ds_supervisao_niveis_test", _DAGS / "etl_ds_supervisao_monitor.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


DAG_MOD = _carregar_dag()

from utils.ds_estrutura import (  # noqa: E402
    Estrutura, filhos_que_falharam, jobs_da_arvore, resumo_dependencia, sucesso_real,
)
from utils.ds_logsum import nome_real, parse_logsum, run_da_execucao  # noqa: E402
from utils.ds_supervisao_regras import (  # noqa: E402
    SUCESSO_FALSO, JobSupervisionado, avaliar_dia,
)


# ── Logs do caso real ───────────────────────────────────────────────────────
# O pai reporta Finished OK e todos os filhos com status 1.
LOG_CARGA_DIARIA = """
   5001 STARTED       Wed Jul 29 05:20:00 2026
Starting Job SeqSsdPrs_CargaDiaria.
   5002 INFO          Wed Jul 29 05:20:01 2026
SeqSsdPrs_CargaDiaria..JobControl (@C): -> (SeqSsdPrs_Dim): Job run requested
   5003 INFO          Wed Jul 29 05:20:02 2026
SeqSsdPrs_CargaDiaria..JobControl (@C): -> (SeqSsdPrs_Arq): Job run requested
   5004 INFO          Wed Jul 29 12:00:00 2026
SeqSsdPrs_CargaDiaria..JobControl (@C): Job SeqSsdPrs_Dim has finished, status = 1 (Finished OK)
   5005 INFO          Wed Jul 29 12:30:00 2026
SeqSsdPrs_CargaDiaria..JobControl (@C): Job SeqSsdPrs_Arq has finished, status = 1 (Finished OK)
   5006 STARTED       Wed Jul 29 13:43:00 2026
Finished Job SeqSsdPrs_CargaDiaria.
"""

# Nível 1: também reporta OK, e o filho dele (nível 2) reporta OK.
LOG_DIM = """
   6001 STARTED       Wed Jul 29 05:20:05 2026
Starting Job SeqSsdPrs_Dim.
   6002 INFO          Wed Jul 29 05:20:06 2026
SeqSsdPrs_Dim..JobControl (@C): -> (SeqSsdPrs_DimSocios): Job run requested
   6003 INFO          Wed Jul 29 11:00:00 2026
SeqSsdPrs_Dim..JobControl (@C): Job SeqSsdPrs_DimSocios has finished, status = 1 (Finished OK)
   6004 STARTED       Wed Jul 29 12:00:00 2026
Finished Job SeqSsdPrs_Dim.
"""

# Nível 2: reporta OK — e ESCONDE o abort do filho.
LOG_DIMSOCIOS = """
   7001 STARTED       Wed Jul 29 05:20:09 2026
Starting Job SeqSsdPrs_DimSocios.
   7002 INFO          Wed Jul 29 05:20:10 2026
SeqSsdPrs_DimSocios..JobControl (@C): -> (SsdPrs_DimSocios_01_ext): Job run requested
   7003 INFO          Wed Jul 29 06:50:00 2026
SeqSsdPrs_DimSocios..JobControl (@C): Job SsdPrs_DimSocios_01_ext has finished, status = 3 (Aborted)
   7004 STARTED       Wed Jul 29 11:00:00 2026
Finished Job SeqSsdPrs_DimSocios.
"""

# Nível 3: job simples, sem filhos.
LOG_FOLHA = """
   8001 STARTED       Wed Jul 29 05:20:11 2026
Starting Job SsdPrs_DimSocios_01_ext.
   8002 FATAL         Wed Jul 29 06:50:00 2026
SsdPrs_DimSocios_01_ext..Transformer: aborted due to a fatal error
"""

LOGS = {
    "SeqSsdPrs_Dim": LOG_DIM,
    "SeqSsdPrs_DimSocios": LOG_DIMSOCIOS,
    "SsdPrs_DimSocios_01_ext": LOG_FOLHA,
    "SeqSsdPrs_Arq": "",          # job simples: logsum vazio
}


def _exec_logsum(alvo: str, _maxl: int) -> tuple[str, str]:
    texto = LOGS.get(alvo, "")
    return (texto, "") if texto else ("", "")


def _job() -> JobSupervisionado:
    from datetime import date, time
    return JobSupervisionado(
        id=1, project="BI_PRESTAMISTA", job_name="SeqSsdPrs_CargaDiaria",
        janela_inicio=time(5, 0), janela_fim=time(6, 0), tolerancia_min=0,
        dias_semana="1,2,3,4,5,6,7", vigencia_inicio=date(2026, 7, 1),
        descricao="Carga diária prestamista")


def _orcamento(chamadas=50, segundos=60):
    return DAG_MOD._Orcamento(chamadas, segundos)


# ── O problema, antes da correção ───────────────────────────────────────────

def test_sem_expansao_o_dia_parece_bom():
    """Documenta o comportamento antigo: é isso que o DataStage faz."""
    run = parse_logsum(LOG_CARGA_DIARIA)[0]
    assert run.resultado == "ok"
    assert run.filhos == {"SeqSsdPrs_Dim": 1, "SeqSsdPrs_Arq": 1}
    # Olhando só o nível 1, nada aparece — e o abort do nível 3 fica escondido.
    assert filhos_que_falharam(run) == []
    assert sucesso_real(run) is True


# ── A correção ──────────────────────────────────────────────────────────────

def test_expansao_encontra_o_abort_tres_niveis_abaixo():
    run = parse_logsum(LOG_CARGA_DIARIA)[0]
    arvore, chamadas = DAG_MOD._expandir_arvore(
        _exec_logsum, _job(), run, MagicMock(), 4, _orcamento())

    assert "SsdPrs_DimSocios_01_ext" in arvore, "o abort do nível 3 não foi encontrado"
    status, nivel, pai = arvore["SsdPrs_DimSocios_01_ext"]
    assert status == 3              # ABORTED
    assert nivel == 3
    assert pai == "SeqSsdPrs_DimSocios"
    assert chamadas > 0


def test_arvore_traz_todos_os_niveis_com_pai_correto():
    run = parse_logsum(LOG_CARGA_DIARIA)[0]
    arvore, _ = DAG_MOD._expandir_arvore(
        _exec_logsum, _job(), run, MagicMock(), 4, _orcamento())

    esperado = {
        "SeqSsdPrs_Dim":            (1, 1, "SeqSsdPrs_CargaDiaria"),
        "SeqSsdPrs_Arq":            (1, 1, "SeqSsdPrs_CargaDiaria"),
        "SeqSsdPrs_DimSocios":      (1, 2, "SeqSsdPrs_Dim"),
        "SsdPrs_DimSocios_01_ext":  (3, 3, "SeqSsdPrs_DimSocios"),
    }
    assert arvore == esperado


def test_veredito_com_arvore_desmente_o_datastage():
    run = parse_logsum(LOG_CARGA_DIARIA)[0]
    run.descendentes, _ = DAG_MOD._expandir_arvore(
        _exec_logsum, _job(), run, MagicMock(), 4, _orcamento())

    # A sequence disse OK...
    assert run.resultado == "ok"
    # ...mas o veredito real é falha, por causa do nível 3.
    assert filhos_que_falharam(run) == ["SsdPrs_DimSocios_01_ext"]
    assert sucesso_real(run) is False

    resumo = resumo_dependencia(run, Estrutura())
    assert resumo["sequence_disse_ok"] is True
    assert resumo["sucesso_real"] is False
    assert resumo["total_filhos"] == 4          # a árvore inteira, não só 2
    assert resumo["niveis_lidos"] == 3


def test_dia_gera_sucesso_falso_apontando_o_job_profundo():
    from datetime import date

    run = parse_logsum(LOG_CARGA_DIARIA)[0]
    run.descendentes, _ = DAG_MOD._expandir_arvore(
        _exec_logsum, _job(), run, MagicMock(), 4, _orcamento())

    eventos = avaliar_dia(_job(), date(2026, 7, 29), [run], datetime(2026, 7, 29, 20, 0))
    assert [e.tipo for e in eventos] == [SUCESSO_FALSO]
    assert "SsdPrs_DimSocios_01_ext" in eventos[0].detalhe


def test_a_varredura_em_largura_e_indispensavel():
    """Nenhum filho do nível 1 falhou — seguir só a cadeia de aborts não acha nada."""
    run = parse_logsum(LOG_CARGA_DIARIA)[0]
    assert [c for c, s in run.filhos.items() if s == 3] == []


# ── Profundidade ────────────────────────────────────────────────────────────

def test_profundidade_2_nao_alcanca_o_abort():
    run = parse_logsum(LOG_CARGA_DIARIA)[0]
    arvore, _ = DAG_MOD._expandir_arvore(
        _exec_logsum, _job(), run, MagicMock(), 2, _orcamento())
    assert "SeqSsdPrs_DimSocios" in arvore          # nível 2 alcançado
    assert "SsdPrs_DimSocios_01_ext" not in arvore  # nível 3 fora do limite


def test_profundidade_1_e_o_comportamento_antigo():
    run = parse_logsum(LOG_CARGA_DIARIA)[0]
    arvore, chamadas = DAG_MOD._expandir_arvore(
        _exec_logsum, _job(), run, MagicMock(), 1, _orcamento())
    assert set(arvore) == {"SeqSsdPrs_Dim", "SeqSsdPrs_Arq"}
    assert chamadas == 0          # nem chega a pedir log de filho


# ── Orçamento do ciclo ──────────────────────────────────────────────────────

def test_orcamento_de_chamadas_interrompe_e_marca_incompleto():
    run = parse_logsum(LOG_CARGA_DIARIA)[0]
    _arvore, chamadas = DAG_MOD._expandir_arvore(
        _exec_logsum, _job(), run, MagicMock(), 4, _orcamento(chamadas=1))
    # Negativo sinaliza expansão incompleta — o run NÃO é marcado como expandido
    # e o próximo ciclo retoma.
    assert chamadas < 0


def test_orcamento_esgotado_nao_faz_nenhuma_chamada():
    run = parse_logsum(LOG_CARGA_DIARIA)[0]
    orc = _orcamento(chamadas=0)
    assert orc.pode() is False
    _arvore, chamadas = DAG_MOD._expandir_arvore(
        _exec_logsum, _job(), run, MagicMock(), 4, orc)
    assert chamadas == 0


def test_orcamento_de_tempo_tambem_freia():
    orc = DAG_MOD._Orcamento(999, 0)      # 0s → já expirado (clamp para 1s mínimo)
    orc._fim = orc._time.monotonic() - 1  # força expirado
    assert orc.pode() is False


# ── Robustez ────────────────────────────────────────────────────────────────

def test_job_sem_log_nao_interrompe_a_varredura():
    # SeqSsdPrs_Arq devolve logsum vazio (job simples): a árvore segue nos outros.
    run = parse_logsum(LOG_CARGA_DIARIA)[0]
    arvore, _ = DAG_MOD._expandir_arvore(
        _exec_logsum, _job(), run, MagicMock(), 4, _orcamento())
    assert "SsdPrs_DimSocios_01_ext" in arvore


def test_erro_de_logsum_em_um_ramo_nao_derruba_os_outros():
    def _com_erro(alvo, maxl):
        if alvo == "SeqSsdPrs_Arq":
            return "", "dsjob retornou 255: job not found"
        return _exec_logsum(alvo, maxl)

    run = parse_logsum(LOG_CARGA_DIARIA)[0]
    arvore, _ = DAG_MOD._expandir_arvore(
        _com_erro, _job(), run, MagicMock(), 4, _orcamento())
    assert "SsdPrs_DimSocios_01_ext" in arvore


def test_ciclo_em_grafo_nao_causa_laco_infinito():
    # Sequence que se referencia (direta ou indiretamente) não pode travar a DAG.
    log_a = """
   9001 STARTED       Wed Jul 29 05:00:00 2026
Starting Job SeqA.
   9002 INFO          Wed Jul 29 05:00:01 2026
SeqA..JobControl (@C): -> (SeqB): Job run requested
   9003 STARTED       Wed Jul 29 06:00:00 2026
Finished Job SeqA.
"""
    log_b = """
   9101 STARTED       Wed Jul 29 05:00:02 2026
Starting Job SeqB.
   9102 INFO          Wed Jul 29 05:00:03 2026
SeqB..JobControl (@C): -> (SeqA): Job run requested
   9103 STARTED       Wed Jul 29 05:59:00 2026
Finished Job SeqB.
"""
    def _exec(alvo, _maxl):
        return ({"SeqA": log_a, "SeqB": log_b}.get(alvo, ""), "")

    run = parse_logsum(log_a)[0]
    arvore, _ = DAG_MOD._expandir_arvore(
        _exec, _job(), run, MagicMock(), 4, _orcamento(chamadas=20))
    assert set(arvore) == {"SeqB", "SeqA"}     # cada um visto uma única vez


def test_nome_com_prefixo_exec_e_normalizado_para_pedir_o_log():
    assert nome_real("SeqExecJob.CargaVida") == "CargaVida"
    assert nome_real("JobExecX.Outro") == "Outro"
    assert nome_real("SemPrefixo") == "SemPrefixo"


# ── Escolha do run do filho ─────────────────────────────────────────────────

def test_run_do_filho_e_o_da_execucao_do_pai_nao_o_mais_recente():
    """O filho tem runs de vários dias; sem recorte, o abort de ontem
    contaminaria o veredito de hoje."""
    log_dois_dias = LOG_DIMSOCIOS + """
   7101 STARTED       Thu Jul 30 05:20:09 2026
Starting Job SeqSsdPrs_DimSocios.
   7102 INFO          Thu Jul 30 06:00:00 2026
SeqSsdPrs_DimSocios..JobControl (@C): Job SsdPrs_DimSocios_01_ext has finished, status = 1 (Finished OK)
   7103 STARTED       Thu Jul 30 11:00:00 2026
Finished Job SeqSsdPrs_DimSocios.
"""
    runs = parse_logsum(log_dois_dias)
    assert len(runs) == 2

    escolhido = run_da_execucao(runs, datetime(2026, 7, 29, 5, 20),
                                datetime(2026, 7, 29, 13, 43))
    assert escolhido.inicio.day == 29
    assert escolhido.filhos["SsdPrs_DimSocios_01_ext"] == 3     # o abort de 29

    escolhido30 = run_da_execucao(runs, datetime(2026, 7, 30, 5, 20),
                                  datetime(2026, 7, 30, 13, 0))
    assert escolhido30.inicio.day == 30
    assert escolhido30.filhos["SsdPrs_DimSocios_01_ext"] == 1


def test_sem_run_na_janela_do_pai_devolve_none():
    runs = parse_logsum(LOG_DIMSOCIOS)
    assert run_da_execucao(runs, datetime(2026, 8, 15, 5, 0),
                           datetime(2026, 8, 15, 6, 0)) is None


def test_sem_hora_do_pai_usa_o_run_mais_recente():
    runs = parse_logsum(LOG_DIMSOCIOS)
    assert run_da_execucao(runs, None, None) is runs[-1]


# ── jobs_da_arvore ──────────────────────────────────────────────────────────

def test_jobs_da_arvore_usa_descendentes_quando_existem():
    run = parse_logsum(LOG_CARGA_DIARIA)[0]
    assert set(jobs_da_arvore(run)) == {"SeqSsdPrs_Dim", "SeqSsdPrs_Arq"}
    run.descendentes = {"X": (1, 1, "p"), "Y": (3, 2, "X")}
    assert jobs_da_arvore(run) == {"X": 1, "Y": 3}
