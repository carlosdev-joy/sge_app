"""
Mensagem de erro do DataStageOperator quando o job NÃO EXISTE no projeto
(incidente 2026-08-01).

Log real de produção:

    [DS] trigger rc=255 | ERROR: Failed to open job
    (DSOpenJob) Cannot find job SsdVidaCobranca01BaixaProcessamentoCobranca
    Status code = -1004

…e o operador dizia apenas ``Failed to trigger '<job>'``, que soa como problema
de disparo/fila. Duas coisas erradas:

1. O motivo verdadeiro era outro — o job não existe no projeto, porque o
   DataStage DIFERENCIA maiúsculas de minúsculas nos nomes de job (o job real é
   ``SSDVida…``) e o SQL Server, não.
2. O operador JÁ SABIA antes de disparar: ``_trigger_or_attach`` chama
   ``_jobinfo()`` primeiro e recebeu o MESMO "Cannot find job" — o parse ignorava
   e caía em status 99, seguindo para o trigger (duas sessões SSH antes do erro).

Airflow não está instalado no ambiente de teste — stubamos o mínimo, no mesmo
padrão de tests/test_ds_operator.py.
"""
from __future__ import annotations

import logging
import sys
import types
from pathlib import Path

import pytest


def _ensure_module(name: str) -> types.ModuleType:
    mod = sys.modules.get(name)
    if mod is None:
        mod = types.ModuleType(name)
        sys.modules[name] = mod
        if "." in name:
            parent, _, child = name.rpartition(".")
            setattr(_ensure_module(parent), child, mod)
    return mod


def _stub_airflow():
    _ensure_module("airflow")
    if not hasattr(_ensure_module("airflow.exceptions"), "AirflowException"):
        _ensure_module("airflow.exceptions").AirflowException = type(
            "AirflowException", (Exception,), {})
    if not hasattr(_ensure_module("airflow.models"), "BaseOperator"):
        _ensure_module("airflow.models").BaseOperator = type(
            "BaseOperator", (), {"__init__": lambda self, *a, **k: None})
    _ensure_module("airflow.providers")
    _ensure_module("airflow.providers.ssh")
    _ensure_module("airflow.providers.ssh.hooks")
    if not hasattr(_ensure_module("airflow.providers.ssh.hooks.ssh"), "SSHHook"):
        _ensure_module("airflow.providers.ssh.hooks.ssh").SSHHook = type("SSHHook", (), {})


_stub_airflow()

sys.path.insert(0, str(Path(__file__).parent.parent / "dags"))
from airflow.exceptions import AirflowException  # noqa: E402
from utils.datastage_operator import (  # noqa: E402
    DataStageOperator, _classifica_erro_dsjob, nomes_parecidos,
)

# Saída EXATA do incidente (o dsjob escreve o erro na saída padrão).
SAIDA_JOB_INEXISTENTE = (
    "ERROR: Failed to open job\n"
    "(DSOpenJob) Cannot find job SsdVidaCobranca01BaixaProcessamentoCobranca\n"
    "Status code = -1004"
)
LJOBS = (
    "SSDVidaCobranca01BaixaProcessamentoCobranca\n"
    "SSDVidaCobranca02Contabilizacao\n"
    "BiCvp_Extract_01\n"
    "Status code = 0\n"
)


def _op(job="SsdVidaCobranca01BaixaProcessamentoCobranca", project="BI_VIDA"):
    op = DataStageOperator(project=project, job_name=job)
    op.log = logging.getLogger("test-ds-erro")
    return op


class _Exec:
    """Dublê de ``_exec``: devolve a resposta casada pelo trecho do comando e
    registra a ordem das chamadas (para provar que o -ljobs só acontece no
    caminho de erro)."""

    def __init__(self, respostas: dict, default=(0, "", "")):
        self.respostas = respostas
        self.default = default
        self.chamadas: list[str] = []

    def __call__(self, cmd, timeout=120):
        self.chamadas.append(cmd)
        for trecho, resp in self.respostas.items():
            if trecho in cmd:
                return resp
        return self.default


# ───────────────────────── classificação (função pura) ──────────────────────

def test_classifica_job_inexistente_pela_saida_do_incidente():
    assert _classifica_erro_dsjob(SAIDA_JOB_INEXISTENTE) == "job_inexistente"
    # Só o código de status também basta (o texto varia por versão).
    assert _classifica_erro_dsjob("Status code = -1004") == "job_inexistente"


def test_classifica_projeto_e_estado():
    assert _classifica_erro_dsjob(
        "ERROR: Failed to open project (DSOpenProject)") == "projeto"
    assert _classifica_erro_dsjob(
        "Error running job\nStatus code = -1002") == "projeto"
    assert _classifica_erro_dsjob(
        "ERROR: Failed to run job (DSRunJob) DSJE_BADSTATE") == "estado"
    assert _classifica_erro_dsjob(
        "Job is not in the right state to be run") == "estado"


def test_classifica_none_quando_nao_reconhece():
    assert _classifica_erro_dsjob("") is None
    assert _classifica_erro_dsjob("Job Status : RUNNING (0)") is None
    assert _classifica_erro_dsjob("qualquer coisa esquisita") is None


def test_nomes_parecidos_prioriza_o_casamento_sem_caixa():
    jobs = ["SSDVidaCobranca01BaixaProcessamentoCobranca",
            "SSDVidaCobranca01BaixaProcessamentoCobrancaV2", "BiCvp_Extract_01"]
    parecidos = nomes_parecidos("SsdVidaCobranca01BaixaProcessamentoCobranca", jobs)
    assert parecidos[0] == "SSDVidaCobranca01BaixaProcessamentoCobranca"
    assert "BiCvp_Extract_01" not in parecidos
    assert nomes_parecidos("", jobs) == []
    assert nomes_parecidos("QualquerCoisa", []) == []


def test_nomes_parecidos_pega_erro_de_digitacao_no_meio():
    """Defeito achado na prova visual: com `startswith`/substring a lista saía
    VAZIA justo no erro mais comum — nenhum dos nomes é prefixo do outro."""
    jobs = ["SSDVidaCobranca01BaixaProcessamentoCobranca",
            "SSDVidaCobranca02Contabilizacao",
            "SSDVidaCadastro01CargaClientes",
            "BiCvp_Extract_Parcelas"]
    parecidos = nomes_parecidos("SSDVidaCobranca09Inexistente", jobs)
    # Ordenado por MAIOR prefixo comum; o sem relação fica de fora.
    assert parecidos[:2] == ["SSDVidaCobranca01BaixaProcessamentoCobranca",
                             "SSDVidaCobranca02Contabilizacao"]
    assert "SSDVidaCadastro01CargaClientes" in parecidos
    assert "BiCvp_Extract_Parcelas" not in parecidos


# ───────────────── _jobinfo: falha no PRIMEIRO ponto que sabe ───────────────

def test_jobinfo_falha_com_motivo_verdadeiro_antes_do_trigger():
    op = _op()
    op._exec = _Exec({"-jobinfo": (255, SAIDA_JOB_INEXISTENTE, ""),
                      "-ljobs": (0, LJOBS, "")})
    with pytest.raises(AirflowException) as e:
        op._trigger_or_attach("2026-08-01")
    msg = str(e.value)
    assert "NÃO EXISTE no projeto 'BI_VIDA'" in msg
    assert "DIFERENCIA maiúsculas de minúsculas" in msg
    # Sugestão acionável: a grafia certa aparece na mensagem.
    assert "SSDVidaCobranca01BaixaProcessamentoCobranca" in msg
    # E o disparo NÃO chegou a acontecer (antes, o operador seguia e falhava lá).
    assert not any("-run" in c for c in op._exec.chamadas)


def test_ljobs_so_roda_no_caminho_de_erro():
    """Custo zero quando está tudo certo: nenhum -ljobs no caminho feliz."""
    op = _op()
    op._exec = _Exec({"-jobinfo": (0, "Job Status\t: RUNNING (0)\nJob Wave Number\t: 42\n", "")})
    assert op._trigger_or_attach("2026-08-01") == 42
    assert not any("-ljobs" in c for c in op._exec.chamadas)


def test_mensagem_sai_mesmo_sem_a_lista_de_parecidos():
    """O -ljobs de diagnóstico é best-effort: se ele falhar, o erro REAL não
    pode ser trocado por um erro de diagnóstico."""
    op = _op()

    def _exec(cmd, timeout=120):
        if "-ljobs" in cmd:
            raise OSError("SSH caiu")
        return (255, SAIDA_JOB_INEXISTENTE, "")

    op._exec = _exec
    with pytest.raises(AirflowException) as e:
        op._jobinfo()
    msg = str(e.value)
    assert "NÃO EXISTE no projeto" in msg
    assert "Nomes parecidos" not in msg


# ─────────────────────── _trigger_run: erro classificado ────────────────────

def test_trigger_run_classifica_em_vez_do_generico():
    op = _op()
    # -jobinfo "limpo" (job não running) para o fluxo chegar no -run.
    op._exec = _Exec({"-jobinfo": (0, "Job Status\t: Not running (99)\n", ""),
                      "-run": (255, SAIDA_JOB_INEXISTENTE, ""),
                      "-ljobs": (0, LJOBS, "")})
    with pytest.raises(AirflowException) as e:
        op._trigger_run("2026-08-01")
    msg = str(e.value)
    assert "NÃO EXISTE no projeto 'BI_VIDA'" in msg
    assert "Failed to trigger" not in msg


def test_trigger_run_estado_invalido_tem_mensagem_propria():
    op = _op()
    op._exec = _Exec({"-run": (255, "", "ERROR: Failed to run job DSJE_BADSTATE")})
    with pytest.raises(AirflowException) as e:
        op._trigger_run("2026-08-01")
    msg = str(e.value)
    assert "estado que não aceita a operação" in msg
    assert "RESET" in msg


def test_trigger_run_erro_desconhecido_mantem_mensagem_generica():
    """Sem marcador reconhecível não inventamos categoria: a saída crua é tudo
    o que temos e continua sendo reportada."""
    op = _op()
    op._exec = _Exec({"-run": (255, "", "algo totalmente novo")})
    with pytest.raises(AirflowException) as e:
        op._trigger_run("2026-08-01")
    assert "Failed to trigger" in str(e.value)


def test_jobinfo_normal_nao_levanta():
    op = _op()
    op._exec = _Exec({"-jobinfo": (0, "Job Status\t: Finished OK (1)\nJob Wave Number\t: 7\n", "")})
    info = op._jobinfo()
    assert info["status_code"] == 1
    assert info["wave_number"] == 7
