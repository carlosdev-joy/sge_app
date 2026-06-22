"""
Console DataStage — validação e montagem de comando `dsjob` (services/ssh_datastage.py).

Cobre só a parte pura/testável (build_dsjob_command): allowlist anti-injeção,
ordem das flags e exigência de job por comando. O SSH (paramiko) não é exercido
aqui — é runtime e não está instalado no ambiente de teste.
"""
from __future__ import annotations

import pytest

from services.ssh_datastage import (
    DS_DSHOME, DSJOB_COMMANDS, DsConsoleError, build_dsjob_command, ssh_configured,
)


def test_jobinfo_monta_comando_com_projeto_e_job():
    cmd, timeout = build_dsjob_command("jobinfo", "BI_VIDA", "SeqSsdVida7Peps")
    assert cmd == f"{DS_DSHOME}/bin/dsjob -jobinfo BI_VIDA SeqSsdVida7Peps"
    assert timeout == 30


def test_logsum_inclui_max_antes_de_projeto_e_job():
    cmd, _ = build_dsjob_command("logsum", "BI_VIDA", "Job1", max_lines=50)
    assert cmd == f"{DS_DSHOME}/bin/dsjob -logsum -max 50 BI_VIDA Job1"


def test_logsum_max_invalido_cai_no_default_e_clampa():
    cmd, _ = build_dsjob_command("logsum", "P", "J", max_lines="abc")  # type: ignore[arg-type]
    assert "-max 200" in cmd
    cmd2, _ = build_dsjob_command("logsum", "P", "J", max_lines=999999)
    assert "-max 2000" in cmd2


def test_ljobs_nao_exige_job():
    cmd, _ = build_dsjob_command("ljobs", "BI_VIDA")
    assert cmd == f"{DS_DSHOME}/bin/dsjob -ljobs BI_VIDA"


@pytest.mark.parametrize("command", ["jobinfo", "logsum", "links", "lstages", "lparams"])
def test_comandos_que_exigem_job_falham_sem_job(command):
    with pytest.raises(DsConsoleError):
        build_dsjob_command(command, "BI_VIDA", None)


@pytest.mark.parametrize("bad", ["BI VIDA", "BI;rm -rf /", "BI`whoami`", "BI$(id)", "BI&&ls", "../etc", ""])
def test_projeto_malicioso_e_rejeitado(bad):
    with pytest.raises(DsConsoleError):
        build_dsjob_command("ljobs", bad)


@pytest.mark.parametrize("bad", ["Seq Job", "Job;ls", "Job|cat", "Job&rm"])
def test_job_malicioso_e_rejeitado(bad):
    with pytest.raises(DsConsoleError):
        build_dsjob_command("jobinfo", "BI_VIDA", bad)


def test_comando_nao_suportado_rejeitado():
    with pytest.raises(DsConsoleError):
        build_dsjob_command("run", "BI_VIDA", "Job1")  # execução não é exposta


def test_dsjob_commands_tem_chaves_esperadas():
    assert set(DSJOB_COMMANDS) == {"jobinfo", "logsum", "ljobs", "links", "lstages", "lparams"}
    for spec in DSJOB_COMMANDS.values():
        assert {"flag", "needs_job", "timeout", "label"} <= set(spec)


def test_ssh_configured_reflete_env(monkeypatch):
    monkeypatch.delenv("DS_SSH_HOST", raising=False)
    monkeypatch.delenv("DS_SSH_USER", raising=False)
    assert ssh_configured() is False
    monkeypatch.setenv("DS_SSH_HOST", "lnxprd021")
    monkeypatch.setenv("DS_SSH_USER", "dsadm")
    assert ssh_configured() is True
