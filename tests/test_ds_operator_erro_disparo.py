"""
Diagnóstico do DataStageOperator quando o DISPARO é recusado com erro genérico
(incidente 2026-08-02 — pipeline TESTE_DS, job SsdVidaDimePessoa02Ftp).

Log real de produção:

    [DS] trigger rc=255 | Error running job
    Status code = -99 DSJE_REPERROR
    airflow.exceptions.AirflowException: [DS] Failed to trigger
    'SsdVidaDimePessoa02Ftp': rc=255 | Error running job
    Status code = -99 DSJE_REPERROR

Diferente do incidente de ontem (PR #269): o job FOI ENCONTRADO — não é
"Cannot find job". O DataStage abriu o job e recusou o `-run` com o erro
genérico de repositório (DSJE_REPERROR, -99), que por definição não diz o
motivo. O motivo real (job não compilado, -param que o job não declara, -queue
inexistente, run travado, permissão) está no LOG DO JOB — que o operator já
sabia buscar (`_logsum`) e não buscava neste caminho: o `_logsum` só rodava no
monitoramento (ABORTED, verbose, fim).

O que estes testes fixam:
  · o log do job é anexado ao erro de disparo;
  · um `-logsum` que falha NÃO substitui o erro original (best-effort de verdade);
  · nenhum `-logsum` no caminho feliz (custo zero);
  · a mensagem do DSJE_REPERROR cita o comando e os valores que o Orquestra
    enviou (-queue / -param) — a informação que só ele tem;
  · saída sem marcador reconhecível continua caindo na mensagem genérica.

Airflow não está instalado no ambiente de teste — stubamos o mínimo, no mesmo
padrão de tests/test_ds_operator_erro_nome.py.
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
    DataStageOperator, _classifica_erro_dsjob,
)

# Saída LITERAL do incidente (o dsjob escreve o erro na saída padrão).
SAIDA_REPERROR = "Error running job\nStatus code = -99 DSJE_REPERROR"

# Um -logsum plausível do job recusado: é AQUI que está o motivo real.
LOGSUM = (
    "     8 STARTED       Sun Aug  2 04:00:11 2026\n"
    "Starting Job SsdVidaDimePessoa02Ftp.\n"
    "     9 FATAL         Sun Aug  2 04:00:11 2026\n"
    "SsdVidaDimePessoa02Ftp: Job has not been compiled since last modification.\n"
)

JOBINFO_PARADO = "Job Status\t: Not running (99)\nJob Wave Number\t: 3\n"


class _Exec:
    """Dublê de ``_exec``: devolve a resposta casada pelo trecho do comando e
    registra a ordem das chamadas (para provar quando o -logsum acontece)."""

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


def _op(**kwargs):
    base = dict(project="BI_VIDA", job_name="SsdVidaDimePessoa02Ftp",
                queue_name="HighPriorityJobs", execution_date_param="pDataRef",
                pipeline_name="TESTE_DS", poll_interval=0)
    base.update(kwargs)
    op = DataStageOperator(**base)
    op.log = logging.getLogger("test-ds-erro-disparo")
    return op


# ───────────────────────── classificação (função pura) ──────────────────────

def test_classifica_reperror_pela_saida_do_incidente():
    assert _classifica_erro_dsjob(SAIDA_REPERROR) == "repositorio"
    # O texto do marcador basta, e o código também.
    assert _classifica_erro_dsjob("DSJE_REPERROR") == "repositorio"
    assert _classifica_erro_dsjob("Status code = -99") == "repositorio"


def test_reperror_nao_engole_o_erro_do_proprio_dsjob():
    """-9999 é erro de sintaxe do dsjob, não do repositório: o `\\b` do -99
    impede o casamento por prefixo."""
    assert _classifica_erro_dsjob("Status code = -9999") is None
    assert _classifica_erro_dsjob("Status code = -999") is None


def test_marcador_especifico_vence_o_generico_do_repositorio():
    """O -99 é o balde genérico: se a saída também trouxer um marcador que diz
    de fato o que houve, esse ganha."""
    assert _classifica_erro_dsjob(
        "DSJE_BADSTATE\nStatus code = -99 DSJE_REPERROR") == "estado"
    assert _classifica_erro_dsjob(
        "Cannot find job X\nStatus code = -99") == "job_inexistente"


# ────────────────── disparo recusado: log do job na exceção ─────────────────

def test_erro_de_disparo_traz_o_log_do_job():
    op = _op()
    op._exec = _Exec({"-jobinfo": (0, JOBINFO_PARADO, ""),
                      "-run": (255, SAIDA_REPERROR, ""),
                      "-logsum": (0, LOGSUM, "")})
    with pytest.raises(AirflowException) as e:
        op._trigger_run("2026-08-02")
    msg = str(e.value)
    assert "Log do job" in msg
    # O motivo REAL, que só o log do DataStage tinha.
    assert "has not been compiled since last modification" in msg
    assert any("-logsum" in c for c in op._exec.chamadas)


def test_mensagem_do_reperror_cita_comando_fila_e_param():
    op = _op()
    op._exec = _Exec({"-jobinfo": (0, JOBINFO_PARADO, ""),
                      "-run": (255, SAIDA_REPERROR, ""),
                      "-logsum": (0, LOGSUM, "")})
    with pytest.raises(AirflowException) as e:
        op._trigger_run("2026-08-02")
    msg = str(e.value)
    assert "RECUSOU a execução" in msg
    assert "O job EXISTE e foi aberto" in msg
    assert "COMPILADO" in msg
    # Os valores que só o Orquestra sabe que mandou.
    assert "-queue HighPriorityJobs" in msg
    assert "pDataRef" in msg
    # E o comando exato, para conferir contra o job real.
    assert "Comando:" in msg and "-run -mode NORMAL" in msg
    # A mensagem genérica de antes NÃO aparece mais neste caso.
    assert "Failed to trigger" not in msg


def test_comando_logado_nao_tem_credencial():
    """O comando pode ir para o log do Airflow porque autenticação vem da
    conexão SSH e do dsenv — nada de usuário/senha na linha de comando."""
    op = _op()
    op._exec = _Exec({"-jobinfo": (0, JOBINFO_PARADO, ""),
                      "-run": (255, SAIDA_REPERROR, ""),
                      "-logsum": (0, LOGSUM, "")})
    with pytest.raises(AirflowException):
        op._trigger_run("2026-08-02")
    cmd = next(c for c in op._exec.chamadas if "-run" in c)
    for proibido in ("-user", "-password", "senha", "-server"):
        assert proibido not in cmd


def test_logsum_que_falha_nao_substitui_o_erro_original():
    """Best-effort de verdade: se o -logsum cair/expirar, o erro ORIGINAL sai
    íntegro — nunca trocado por um erro de diagnóstico."""
    op = _op()

    def _exec(cmd, timeout=120):
        if "-logsum" in cmd:
            raise OSError("SSH caiu no diagnóstico")
        if "-run" in cmd:
            return (255, SAIDA_REPERROR, "")
        return (0, JOBINFO_PARADO, "")

    op._exec = _exec
    with pytest.raises(AirflowException) as e:
        op._trigger_run("2026-08-02")
    msg = str(e.value)
    assert "RECUSOU a execução" in msg
    assert "DSJE_REPERROR" in msg          # a saída crua continua lá
    assert "Log do job" not in msg         # sem bloco de diagnóstico
    assert "SSH caiu no diagnóstico" not in msg


def test_logsum_vazio_diz_que_nao_veio_log():
    """Sem duplicar bloco vazio: quando o DataStage responde sem conteúdo,
    dizemos isso explicitamente."""
    op = _op()
    op._exec = _Exec({"-jobinfo": (0, JOBINFO_PARADO, ""),
                      "-run": (255, SAIDA_REPERROR, ""),
                      "-logsum": (0, "   \n", "")})
    with pytest.raises(AirflowException) as e:
        op._trigger_run("2026-08-02")
    assert "não devolveu log para este job" in str(e.value)


def test_logsum_anexado_respeita_o_teto_de_2000_chars():
    op = _op()
    gigante = "linha de log irrelevante\n" * 500     # ~12 500 chars
    op._exec = _Exec({"-jobinfo": (0, JOBINFO_PARADO, ""),
                      "-run": (255, SAIDA_REPERROR, ""),
                      "-logsum": (0, gigante, "")})
    with pytest.raises(AirflowException) as e:
        op._trigger_run("2026-08-02")
    corpo = str(e.value).split("Log do job", 1)[1]
    assert len(corpo) < 2200      # 2 000 do log + o cabeçalho da linha


def test_sem_logsum_no_caminho_feliz():
    """Custo zero quando o disparo dá certo: nenhum -logsum, nenhum -ljobs."""
    op = _op()
    op._exec = _Exec({"-jobinfo": (0, JOBINFO_PARADO, ""),
                      "-run": (0, "Job started", "")})
    op._trigger_run("2026-08-02")
    assert not any("-logsum" in c for c in op._exec.chamadas)
    assert not any("-ljobs" in c for c in op._exec.chamadas)


def test_job_inexistente_nao_gasta_logsum():
    """Job que não existe não tem log — ali o diagnóstico útil é o -ljobs."""
    op = _op()
    op._exec = _Exec({"-jobinfo": (0, JOBINFO_PARADO, ""),
                      "-run": (255, "Cannot find job X\nStatus code = -1004", ""),
                      "-ljobs": (0, "SSDVidaDimePessoa02Ftp\n", "")})
    with pytest.raises(AirflowException) as e:
        op._trigger_run("2026-08-02")
    assert "NÃO EXISTE no projeto" in str(e.value)
    assert not any("-logsum" in c for c in op._exec.chamadas)


def test_saida_nao_reconhecida_mantem_a_mensagem_generica():
    """Sem marcador confirmável não inventamos categoria — a mensagem genérica
    de antes continua valendo, agora com comando e log anexados."""
    op = _op()
    op._exec = _Exec({"-jobinfo": (0, JOBINFO_PARADO, ""),
                      "-run": (255, "", "algo totalmente novo"),
                      "-logsum": (0, LOGSUM, "")})
    with pytest.raises(AirflowException) as e:
        op._trigger_run("2026-08-02")
    msg = str(e.value)
    assert "Failed to trigger 'SsdVidaDimePessoa02Ftp': rc=255" in msg
    assert "algo totalmente novo" in msg
    assert "Comando:" in msg
    assert "Log do job" in msg


def test_sem_fila_e_sem_param_a_mensagem_diz_isso():
    """A mensagem cita o que ELE enviou — inclusive quando não enviou nada."""
    op = _op(queue_name=None, execution_date_param=None)
    op._exec = _Exec({"-jobinfo": (0, JOBINFO_PARADO, ""),
                      "-run": (255, SAIDA_REPERROR, ""),
                      "-logsum": (0, LOGSUM, "")})
    with pytest.raises(AirflowException) as e:
        op._trigger_run("2026-08-02")
    msg = str(e.value)
    assert "NÃO envia nenhum -param" in msg
    assert "NÃO envia -queue" in msg


# ───────── monitoramento: ramos que mandavam "ver o log" sem o log ──────────

class _Ti:
    def __init__(self):
        self.task_id = "t"
        self.pushed = {}

    def xcom_pull(self, key=None, task_ids=None):
        return None

    def xcom_push(self, key=None, value=None):
        self.pushed[key] = value


def _context():
    dag = types.SimpleNamespace(dag_id="TESTE_DS")
    return {"ti": _Ti(), "ds": "2026-08-02", "ts_nodash": "20260802T040000",
            "dag": dag}


def test_not_running_inesperado_traz_o_log_do_job():
    op = _op()
    op._exec = _Exec({"-jobinfo": (0, JOBINFO_PARADO, ""),
                      "-run": (0, "Job started", ""),
                      "-logsum": (0, LOGSUM, "")})
    with pytest.raises(AirflowException) as e:
        op.execute(_context())
    msg = str(e.value)
    assert "is NOT RUNNING unexpectedly" in msg
    assert "has not been compiled since last modification" in msg


def test_status_desconhecido_traz_o_log_do_job():
    op = _op()
    op._exec = _Exec({"-jobinfo": (0, "Job Status\t: Crashed (96)\n", ""),
                      "-run": (0, "Job started", ""),
                      "-logsum": (0, LOGSUM, "")})
    with pytest.raises(AirflowException) as e:
        op.execute(_context())
    msg = str(e.value)
    assert "Unknown status code 96" in msg
    assert "Log do job" in msg
