"""
DataStageOperator × parâmetros da etapa (F2 da spec
docs/spec-parametros-job-datastage.md). O que se prende:

  · ZERO parâmetros cadastrados → comando byte a byte o de sempre, nenhum
    `-lparams`, nenhuma leitura do ODATE;
  · com parâmetros: `-lparams` antes do `-run`, N `-param` (fixo, data de
    referência com cálculo, Encrypted decifrado), log com descrição, ODATE lido
    de etl_pipeline_execucao pelo run_id;
  · o valor Encrypted NUNCA aparece em log, mensagem de erro ou params_json —
    mas VAI no comando real;
  · não declarado no `-lparams` → falha ANTES do `-run` listando o que o job
    declara; `-lparams` com erro → falha antes do `-run`;
  · ODATE ausente (sem linha e sem conf) → falha antes do `-run`; conf válido
    serve de fallback;
  · sem a migration 107 (Invalid column name) → comando de sempre, com aviso;
  · banco fora → falha antes do `-run` (nunca dispara "sem os parâmetros");
  · execute(): params_json gravado logo após o QUEUED, mascarado;
  · chamada direta a _trigger_run (sem contexto) → caminho legado intacto.

Airflow stubado como nos vizinhos (tests/test_ds_operator_erro_disparo.py).
"""
from __future__ import annotations

import json
import logging
import sys
import types
from datetime import date
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
from utils.datastage_operator import DataStageOperator  # noqa: E402

JOBINFO_PARADO = "Job Status\t: Not running (99)\nJob Wave Number\t: 3\n"
LPARAMS = "pDataIni\npDataFim\npAmb\npSenha\npEsp\npData\npD\nStatus code = 0\n"
SAIDA_REPERROR = "Error running job\nStatus code = -99 DSJE_REPERROR"


class _Exec:
    def __init__(self, respostas: dict, default=(0, "", "")):
        self.respostas, self.default, self.chamadas = respostas, default, []

    def __call__(self, cmd, timeout=120):
        self.chamadas.append(cmd)
        for trecho, resp in self.respostas.items():
            if trecho in cmd:
                return resp
        return self.default


class _Hook:
    """Dublê do MsSqlHook: linhas da etapa (e do pipeline, F4), a linha do ODATE
    e o registro dos UPDATEs. Sem a 108 (`pipeline=None`) a leitura dos
    defaults falha como o SQL Server falharia — tabela inexistente."""

    def __init__(self, etapa=None, odate=date(2026, 9, 9), erro_records=None, erro_first=None,
                 pipeline=None):
        self.etapa, self.odate, self.pipeline = etapa or [], odate, pipeline
        self.erro_records, self.erro_first = erro_records, erro_first
        self.records_calls, self.first_calls, self.runs = [], [], []

    def get_records(self, sql, parameters=None):
        self.records_calls.append((sql, parameters))
        if self.erro_records:
            raise self.erro_records
        if "dbo.etl_pipeline_param " in sql:
            if self.pipeline is None:
                raise Exception("(208, b\"Invalid object name 'dbo.etl_pipeline_param'\")")
            return self.pipeline
        return self.etapa

    def get_first(self, sql, parameters=None):
        self.first_calls.append((sql, parameters))
        if self.erro_first:
            raise self.erro_first
        return (self.odate,) if self.odate is not None else None

    def run(self, sql, parameters=None):
        self.runs.append((sql, parameters))


def _linha(nome, tipo="String", origem="fixo", valor=None, meses=None, ancora=None, dias=None, formato=None):
    return (nome, tipo, valor, origem, meses, ancora, dias, formato)


def _op(hook=None, **kwargs):
    base = dict(project="BI_VIDA", job_name="SeqCarga", queue_name="HighPriorityJobs",
                pipeline_name="PIPE_VIDA", poll_interval=0)
    base.update(kwargs)
    op = DataStageOperator(**base)
    op.log = logging.getLogger("test-ds-params")
    op._db_hook = lambda: hook if hook is not None else _Hook()
    op._run_ctx = {"run_id": "scheduled__2026-09-09T06:00:00+00:00", "ds": "2026-09-09",
                   "conf": {}, "pipeline": "PIPE_VIDA"}
    return op


def _exec_ok(lparams=LPARAMS):
    return _Exec({"-jobinfo": (0, JOBINFO_PARADO, ""), "-lparams": (0, lparams, ""),
                  "-run": (0, "Job started", "")})


def _cmd_run(ex):
    return next(c for c in ex.chamadas if " -run " in c)


# ═══════════ zero parâmetros: comando de sempre ═════════════════════════════

def test_sem_parametro_o_comando_e_o_de_sempre_e_nada_extra_e_chamado():
    hook = _Hook(etapa=[])
    op = _op(hook)
    op._exec = _exec_ok()
    op._trigger_run("2026-09-09")
    assert _cmd_run(op._exec) == (
        "/opt/IBM/InformationServer/Server/DSEngine/bin/dsjob -run -mode NORMAL "
        "-queue HighPriorityJobs 'BI_VIDA' 'SeqCarga'")
    assert not any("-lparams" in c for c in op._exec.chamadas)
    assert hook.first_calls == []           # ODATE não foi lido
    assert op._params_enviados == []


def test_chamada_direta_sem_contexto_e_o_caminho_legado():
    """Sem execute() não há contexto: nenhum banco, nenhum -lparams — e o
    execution_date_param legado continua saindo."""
    op = DataStageOperator(project="P", job_name="J", execution_date_param="pDataRef")
    op.log = logging.getLogger("t")
    op._exec = _exec_ok()
    op._trigger_run("2026-08-02")
    assert "-param pDataRef=2026-08-02 'P' 'J'" in _cmd_run(op._exec)
    assert not any("-lparams" in c for c in op._exec.chamadas)


# ═══════════ com parâmetros ═════════════════════════════════════════════════

def test_caso_mensal_da_spec_vai_no_comando_e_no_log(caplog):
    hook = _Hook(etapa=[
        _linha("pDataIni", "Date", "data_referencia", meses=-1, ancora="inicio_mes"),
        _linha("pDataFim", "Date", "data_referencia", meses=-1, ancora="fim_mes"),
        _linha("pAmb", valor="PRD"),
    ])
    op = _op(hook)
    op._exec = _exec_ok()
    with caplog.at_level(logging.INFO):
        op._trigger_run("2026-09-09")
    cmd = _cmd_run(op._exec)
    assert cmd == (
        "/opt/IBM/InformationServer/Server/DSEngine/bin/dsjob -run -mode NORMAL "
        "-queue HighPriorityJobs -param pDataIni=2026-08-01 -param pDataFim=2026-08-31 "
        "-param pAmb=PRD 'BI_VIDA' 'SeqCarga'")
    # -lparams ANTES do -run
    idx = [i for i, c in enumerate(op._exec.chamadas) if "-lparams" in c or " -run " in c]
    assert "-lparams" in op._exec.chamadas[idx[0]]
    # ODATE lido pela chave (pipeline, run_id), pela MESMA linha que o pipeline
    # usa (TOP 1 … ORDER BY id, o degrau 0 de malha_corrida.SQL_ODATE_DO_RUN)
    assert hook.first_calls[0][1] == ("PIPE_VIDA", "scheduled__2026-09-09T06:00:00+00:00")
    sql_odate = hook.first_calls[0][0]
    assert "etl_pipeline_execucao" in sql_odate and "TOP 1" in sql_odate and "ORDER BY id" in sql_odate
    # o rastro no log, com a descrição do cálculo
    assert "[DS] parâmetros: pDataIni=2026-08-01 (etapa · referência 2026-09-09 → -1 mês → início do mês → 2026-08-01)" in caplog.text
    assert "pDataFim=2026-08-31 (etapa · referência 2026-09-09 → -1 mês → fim do mês → 2026-08-31)" in caplog.text
    assert "pAmb=PRD (etapa · fixo)" in caplog.text
    assert [p["name"] for p in op._params_enviados] == ["pDataIni", "pDataFim", "pAmb"]


def test_odate_31_de_marco():
    hook = _Hook(etapa=[_linha("pDataFim", "Date", "data_referencia", meses=-1, ancora="fim_mes")],
                 odate=date(2026, 3, 31))
    op = _op(hook)
    op._exec = _exec_ok()
    op._trigger_run("2026-03-31")
    assert "-param pDataFim=2026-02-28 " in _cmd_run(op._exec)


def test_valor_com_espaco_e_aspa_vai_quotado_e_integro():
    hook = _Hook(etapa=[_linha("pEsp", valor="a b'c")])
    op = _op(hook)
    op._exec = _exec_ok()
    op._trigger_run("2026-09-09")
    assert """-param 'pEsp=a b'"'"'c' 'BI_VIDA'""" in _cmd_run(op._exec)


def test_encrypted_vai_no_comando_mas_nunca_no_log_nem_no_erro(monkeypatch, caplog):
    from cryptography.fernet import Fernet
    key = Fernet.generate_key()
    monkeypatch.setenv("ORQUESTRA_CONN_KEY", key.decode())
    token = Fernet(key).encrypt(b"segredo!").decode()
    hook = _Hook(etapa=[_linha("pSenha", "Encrypted", valor=token), _linha("pAmb", valor="PRD")])
    op = _op(hook, verbose_log=True)     # verbose loga o comando no caminho feliz
    op._exec = _exec_ok()
    with caplog.at_level(logging.INFO):
        op._trigger_run("2026-09-09")
    # o `!` não é seguro para o shell → o shlex quota o par inteiro
    assert "-param 'pSenha=segredo!' -param pAmb=PRD" in _cmd_run(op._exec)
    assert "segredo" not in caplog.text
    assert "pSenha=*** (etapa · fixo (Encrypted))" in caplog.text
    assert "[DS] comando:" in caplog.text and "pSenha=***" in caplog.text
    # no caminho de erro (DSJE_REPERROR), a mensagem cita o comando MASCARADO
    op2 = _op(hook)
    op2._exec = _Exec({"-jobinfo": (0, JOBINFO_PARADO, ""), "-lparams": (0, LPARAMS, ""),
                       "-run": (255, SAIDA_REPERROR, ""), "-logsum": (0, "", "")})
    with pytest.raises(AirflowException) as e:
        op2._trigger_run("2026-09-09")
    msg = str(e.value)
    assert "segredo" not in msg
    assert "-param pSenha=***" in msg and "Comando:" in msg


# ═══════════ falhas ANTES do -run ═══════════════════════════════════════════

def test_nao_declarado_falha_antes_do_run_listando_o_que_o_job_declara():
    hook = _Hook(etapa=[_linha("pdataini", valor="x")])
    op = _op(hook)
    op._exec = _exec_ok()
    with pytest.raises(AirflowException) as e:
        op._trigger_run("2026-09-09")
    msg = str(e.value)
    assert "NÃO declara" in msg and "pdataini" in msg and "pAmb, pD, pData, pDataFim, pDataIni" in msg
    assert "NÃO foi disparada" in msg
    assert not any(" -run " in c for c in op._exec.chamadas)


def test_lparams_com_erro_falha_antes_do_run():
    hook = _Hook(etapa=[_linha("pAmb", valor="PRD")])
    op = _op(hook)
    op._exec = _Exec({"-jobinfo": (0, JOBINFO_PARADO, ""),
                      "-lparams": (1, "", "algo deu errado"),
                      "-run": (0, "Job started", "")})
    with pytest.raises(AirflowException) as e:
        op._trigger_run("2026-09-09")
    assert "dsjob -lparams" in str(e.value) and "algo deu errado" in str(e.value)
    assert not any(" -run " in c for c in op._exec.chamadas)


def test_lparams_com_job_inexistente_usa_o_diagnostico_do_dsjob():
    hook = _Hook(etapa=[_linha("pAmb", valor="PRD")])
    op = _op(hook)
    op._exec = _Exec({"-jobinfo": (0, JOBINFO_PARADO, ""),
                      "-lparams": (255, "Cannot find job SeqCarga\nStatus code = -1004", ""),
                      "-ljobs": (0, "SEQCARGA\n", "")})
    with pytest.raises(AirflowException) as e:
        op._trigger_run("2026-09-09")
    assert "NÃO EXISTE no projeto" in str(e.value)


def test_odate_ausente_sem_conf_falha_antes_do_run():
    hook = _Hook(etapa=[_linha("pData", "Date", "data_referencia")], odate=None)
    op = _op(hook)
    op._exec = _exec_ok()
    with pytest.raises(AirflowException) as e:
        op._trigger_run("2026-09-09")
    assert "data de referência indisponível" in str(e.value)
    assert not any(" -run " in c for c in op._exec.chamadas)


def test_odate_ausente_cai_no_conf_valido():
    hook = _Hook(etapa=[_linha("pData", "Date", "data_referencia", dias=-1)], odate=None)
    op = _op(hook)
    op._run_ctx["conf"] = {"data_referencia": "2026-09-05"}
    op._exec = _exec_ok()
    op._trigger_run("2026-09-09")
    assert "-param pData=2026-09-04 " in _cmd_run(op._exec)


def test_odate_com_banco_fora_tenta_o_conf_e_depois_falha(caplog):
    hook = _Hook(etapa=[_linha("pData", "Date", "data_referencia")], erro_first=OSError("timeout"))
    op = _op(hook)
    op._exec = _exec_ok()
    with caplog.at_level(logging.WARNING):
        with pytest.raises(AirflowException) as e:
            op._trigger_run("2026-09-09")
    assert "indisponível para o ODATE" in caplog.text
    assert "data de referência indisponível" in str(e.value)


def test_data_logica_vem_do_ds_do_contexto():
    hook = _Hook(etapa=[_linha("pD", "String", "data_logica", formato="%Y%m%d")], odate=None)
    op = _op(hook)
    op._exec = _exec_ok()
    op._trigger_run("2026-09-09")
    assert "-param pD=20260909 " in _cmd_run(op._exec)
    assert hook.first_calls == []          # data lógica não lê o banco


def test_sem_migration_107_comando_de_sempre_com_aviso(caplog):
    hook = _Hook(erro_records=Exception("(207, b\"Invalid column name 'param_source'\")"))
    op = _op(hook)
    op._exec = _exec_ok()
    with caplog.at_level(logging.WARNING):
        op._trigger_run("2026-09-09")
    assert "migration 107" in caplog.text
    assert " -run -mode NORMAL -queue HighPriorityJobs 'BI_VIDA' 'SeqCarga'" in _cmd_run(op._exec)
    assert not any("-lparams" in c for c in op._exec.chamadas)


def test_banco_fora_na_leitura_falha_antes_do_run():
    hook = _Hook(erro_records=OSError("banco fora"))
    op = _op(hook)
    op._exec = _exec_ok()
    with pytest.raises(AirflowException) as e:
        op._trigger_run("2026-09-09")
    assert "Não foi possível ler os parâmetros" in str(e.value) and "banco fora" in str(e.value)
    assert not any(" -run " in c for c in op._exec.chamadas)


def test_encrypted_sem_chave_no_worker_falha_antes_do_run(monkeypatch):
    monkeypatch.delenv("ORQUESTRA_CONN_KEY", raising=False)
    hook = _Hook(etapa=[_linha("pSenha", "Encrypted", valor="token")])
    op = _op(hook)
    op._exec = _exec_ok()
    with pytest.raises(AirflowException) as e:
        op._trigger_run("2026-09-09")
    assert "ORQUESTRA_CONN_KEY" in str(e.value)
    assert not any(" -run " in c for c in op._exec.chamadas)


# ═══════════ F4: defaults do pipeline ═══════════════════════════════════════

def test_default_do_pipeline_entra_so_onde_o_job_declara(caplog):
    """`pAmb` declarado → vai; `pFora` não declarado → ignorado E listado no log."""
    hook = _Hook(etapa=[], pipeline=[_linha("pAmb", valor="PRD"), _linha("pFora", valor="x")])
    op = _op(hook)
    op._exec = _exec_ok()
    with caplog.at_level(logging.INFO):
        op._trigger_run("2026-09-09")
    cmd = _cmd_run(op._exec)
    assert "-param pAmb=PRD " in cmd and "pFora" not in cmd
    assert "pAmb=PRD (pipeline · fixo)" in caplog.text
    assert "ignorados do pipeline (o job não declara): pFora" in caplog.text
    assert op._params_ignorados == ["pFora"]


def test_default_ignorado_aparece_no_log_mesmo_sem_nada_a_enviar(caplog):
    """Job que não declara NENHUM default: nada vai no comando, mas o nome
    ignorado tem de aparecer no log (critério da F4 — nunca em silêncio)."""
    hook = _Hook(etapa=[], pipeline=[_linha("pAmbiente", valor="PRD")])
    op = _op(hook)
    op._exec = _Exec({"-jobinfo": (0, JOBINFO_PARADO, ""), "-lparams": (0, "pOutro\nStatus code = 0\n", ""),
                      "-run": (0, "Job started", "")})
    with caplog.at_level(logging.INFO):
        op._trigger_run("2026-09-09")
    assert _cmd_run(op._exec).endswith("-queue HighPriorityJobs 'BI_VIDA' 'SeqCarga'")
    assert "[DS] parâmetros: nenhum · ignorados do pipeline (o job não declara): pAmbiente" in caplog.text


def test_etapa_sobrepoe_o_default_do_pipeline():
    hook = _Hook(etapa=[_linha("pAmb", valor="HML")], pipeline=[_linha("pAmb", valor="PRD")])
    op = _op(hook)
    op._exec = _exec_ok()
    op._trigger_run("2026-09-09")
    cmd = _cmd_run(op._exec)
    assert "-param pAmb=HML " in cmd and "PRD" not in cmd
    assert op._params_enviados[0]["fonte"] == "etapa"


def test_so_default_de_pipeline_ainda_chama_lparams():
    hook = _Hook(etapa=[], pipeline=[_linha("pAmb", valor="PRD")])
    op = _op(hook)
    op._exec = _exec_ok()
    op._trigger_run("2026-09-09")
    assert any("-lparams" in c for c in op._exec.chamadas)


def test_sem_migration_108_os_defaults_sao_vazios_e_nada_muda():
    """Tabela do pipeline ausente (pré-F4) + etapa sem parâmetro = comando de sempre."""
    hook = _Hook(etapa=[], pipeline=None)
    op = _op(hook)
    op._exec = _exec_ok()
    op._trigger_run("2026-09-09")
    assert _cmd_run(op._exec).endswith("-queue HighPriorityJobs 'BI_VIDA' 'SeqCarga'")
    assert not any("-lparams" in c for c in op._exec.chamadas)


def test_default_de_pipeline_com_data_de_referencia():
    hook = _Hook(etapa=[], pipeline=[_linha("pDataFim", "Date", "data_referencia", meses=-1, ancora="fim_mes")])
    op = _op(hook)
    op._exec = _exec_ok()
    op._trigger_run("2026-09-09")
    assert "-param pDataFim=2026-08-31 " in _cmd_run(op._exec)
    assert op._params_enviados[0]["fonte"] == "pipeline"


# ═══════════ a mensagem do DSJE_REPERROR cita os parâmetros enviados ════════

def test_reperror_cita_os_parametros_resolvidos():
    hook = _Hook(etapa=[_linha("pAmb", valor="PRD")])
    op = _op(hook)
    op._exec = _Exec({"-jobinfo": (0, JOBINFO_PARADO, ""), "-lparams": (0, LPARAMS, ""),
                      "-run": (255, SAIDA_REPERROR, ""), "-logsum": (0, "", "")})
    with pytest.raises(AirflowException) as e:
        op._trigger_run("2026-09-09")
    msg = str(e.value)
    assert "'-param pAmb=PRD' (etapa)" in msg
    assert "conferidos no `dsjob -lparams`" in msg


# ═══════════ execute(): params_json após o QUEUED ═══════════════════════════

class _Ti:
    def __init__(self):
        self.task_id = "t"
        self.pushed = {}

    def xcom_pull(self, key=None, task_ids=None):
        return None

    def xcom_push(self, key=None, value=None):
        self.pushed[key] = value


def _context():
    return {"ti": _Ti(), "ds": "2026-09-09", "ts_nodash": "20260909T060000",
            "dag": types.SimpleNamespace(dag_id="PIPE_VIDA"),
            "run_id": "scheduled__2026-09-09T06:00:00+00:00",
            "dag_run": types.SimpleNamespace(conf={})}


def test_execute_grava_params_json_mascarado_apos_o_queued(monkeypatch):
    from cryptography.fernet import Fernet
    key = Fernet.generate_key()
    monkeypatch.setenv("ORQUESTRA_CONN_KEY", key.decode())
    token = Fernet(key).encrypt(b"segredo!").decode()
    hook = _Hook(etapa=[_linha("pDataFim", "Date", "data_referencia", meses=-1, ancora="fim_mes"),
                        _linha("pSenha", "Encrypted", valor=token)])
    op = DataStageOperator(project="BI_VIDA", job_name="SeqCarga", pipeline_name="PIPE_VIDA",
                           poll_interval=0)
    op.log = logging.getLogger("t")
    op._db_hook = lambda: hook
    op._persist = lambda *a, **k: None
    op._exec = _Exec({"-jobinfo": (0, "Job Status\t: Finished OK (1)\nJob Wave Number\t: 4\n", ""),
                      "-lparams": (0, LPARAMS, ""), "-run": (0, "Job started", ""),
                      "-logsum": (0, "Starting Job SeqCarga.\n", ""), "-report": (0, "", "")})
    op.execute(_context())
    updates = [r for r in hook.runs if "params_json" in r[0]]
    assert len(updates) == 1
    sql, params = updates[0]
    assert "%s" in sql and params[1:] == ("20260909T060000", "PIPE_VIDA", "SeqCarga")
    doc = json.loads(params[0])
    assert doc == [
        {"name": "pDataFim", "valor": "2026-08-31", "fonte": "etapa",
         "descricao": "referência 2026-09-09 → -1 mês → fim do mês → 2026-08-31", "mascarado": False},
        {"name": "pSenha", "valor": "***", "fonte": "etapa", "descricao": "fixo (Encrypted)", "mascarado": True},
    ]
    assert "segredo" not in params[0]


def test_execute_sem_parametro_nao_grava_params_json():
    hook = _Hook(etapa=[])
    op = DataStageOperator(project="BI_VIDA", job_name="SeqCarga", pipeline_name="PIPE_VIDA", poll_interval=0)
    op.log = logging.getLogger("t")
    op._db_hook = lambda: hook
    op._persist = lambda *a, **k: None
    op._exec = _Exec({"-jobinfo": (0, "Job Status\t: Finished OK (1)\nJob Wave Number\t: 4\n", ""),
                      "-run": (0, "Job started", ""), "-logsum": (0, "", ""), "-report": (0, "", "")})
    op.execute(_context())
    assert not any("params_json" in r[0] for r in hook.runs)


def test_execute_monta_o_contexto_do_run_a_partir_do_context():
    hook = _Hook(etapa=[_linha("pD", "String", "data_referencia", dias=-1)], odate=None)
    op = DataStageOperator(project="BI_VIDA", job_name="SeqCarga", poll_interval=0)  # sem pipeline_name
    op.log = logging.getLogger("t")
    op._db_hook = lambda: hook
    op._persist = lambda *a, **k: None
    op._exec = _Exec({"-jobinfo": (0, "Job Status\t: Finished OK (1)\nJob Wave Number\t: 4\n", ""),
                      "-lparams": (0, "pD\n", ""), "-run": (0, "Job started", ""),
                      "-logsum": (0, "", ""), "-report": (0, "", "")})
    ctx = _context()
    ctx["dag_run"].conf = {"data_referencia": "2026-09-05"}
    op.execute(ctx)
    # pipeline caiu no dag_id; run_id e conf vieram do context
    assert hook.records_calls[0][1] == ("PIPE_VIDA", "SeqCarga")
    assert hook.first_calls[0][1] == ("PIPE_VIDA", "scheduled__2026-09-09T06:00:00+00:00")
    assert "-param pD=2026-09-04 " in _cmd_run(op._exec)
