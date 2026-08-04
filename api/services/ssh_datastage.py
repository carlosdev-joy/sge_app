"""
api/services/ssh_datastage.py — execução de comandos `dsjob` (read-only) no
servidor Unix do DataStage via SSH, para o "Console DataStage" do Admin.

Diferente das DAGs (que usam o SSHHook do Airflow), aqui o backend abre uma
conexão SSH própria (paramiko) por requisição — consulta síncrona e curta, não
precisa sobreviver a restart. As credenciais vêm de variáveis de ambiente
(degradação graciosa: se não configuradas, o endpoint avisa em vez de quebrar).

Segurança: project/job são validados por allowlist estrita (`^[A-Za-z0-9_.]+$`,
mesmo padrão de `dags/utils/datastage_operator.py`) ANTES de qualquer
interpolação no shell, e só um conjunto fixo de subcomandos read-only é exposto.
Nunca há comando livre.
"""
from __future__ import annotations

import logging
import os
import re
import shlex
import time

log = logging.getLogger("orquestra-api")

# Caminho do DataStage Engine (mesmo default do operador). Config de servidor,
# não entrada de usuário — não interpolável por terceiros.
DS_DSHOME = os.getenv("DS_DSHOME", "/opt/IBM/InformationServer/Server/DSEngine")

# Allowlist anti-injeção (idêntica a _SAFE_JOB_RE do operador).
_SAFE_RE = re.compile(r"^[A-Za-z0-9_.]+$")

# Subcomandos read-only expostos no console. needs_job=True exige nome do job.
DSJOB_COMMANDS: dict[str, dict] = {
    "jobinfo": {"flag": "-jobinfo", "needs_job": True,  "timeout": 30,  "label": "Status do job"},
    "logsum":  {"flag": "-logsum",  "needs_job": True,  "timeout": 120, "label": "Resumo do log do run"},
    "logdetail": {"flag": "-logdetail", "needs_job": True, "timeout": 120, "label": "Detalhe do log (erros completos)"},
    "ljobs":   {"flag": "-ljobs",   "needs_job": False, "timeout": 30,  "label": "Listar jobs do projeto"},
    "lstages": {"flag": "-lstages", "needs_job": True,  "timeout": 30,  "label": "Stages do job"},
    "lparams": {"flag": "-lparams", "needs_job": True,  "timeout": 30,  "label": "Parâmetros do job"},
    "report":  {"flag": "-report",  "needs_job": True,  "timeout": 60,  "label": "Relatório do job (detalhado)"},
}


class DsConsoleError(Exception):
    """Erro de validação/configuração — vira HTTP 422 no endpoint."""


def parse_ljobs(stdout: str | None) -> list[str]:
    """Nomes de job na saída de ``dsjob -ljobs <PROJETO>`` — um por linha.

    Descarta o rodapé ``Status code = N``, o marcador ``<none>`` (projeto vazio)
    e qualquer linha que não seja um nome de job válido (mensagens de erro do
    dsjob costumam ter espaços/parênteses e caem fora da allowlist ``_SAFE_RE``).
    Função PURA — o parse é testável sem SSH. Preserva a ordem e a CAIXA
    original: é justamente a caixa que o DataStage cobra."""
    if not stdout:
        return []
    jobs: list[str] = []
    vistos: set[str] = set()
    for raw in stdout.splitlines():
        linha = raw.strip()
        if not linha or linha.lower() == "<none>":
            continue
        if re.match(r"^status code\s*=", linha, re.IGNORECASE):
            continue
        if not _SAFE_RE.match(linha):
            continue
        if linha not in vistos:
            vistos.add(linha)
            jobs.append(linha)
    return jobs


def ssh_configured() -> bool:
    """True se as variáveis mínimas de SSH estão presentes no ambiente."""
    return bool(os.getenv("DS_SSH_HOST") and os.getenv("DS_SSH_USER"))


def _validate_name(value: str | None, field: str) -> str:
    if not value or not _SAFE_RE.match(value):
        raise DsConsoleError(
            f"{field} inválido: use apenas letras, números, '_' e '.' (sem espaços ou símbolos).")
    return value


def build_dsjob_command(command: str, project: str, job: str | None = None,
                        max_lines: int = 200, event_id=None) -> tuple[str, int]:
    """
    Monta o comando `dsjob` (sem o source do dsenv) e devolve (cmd, timeout).

    Função pura, sem SSH — testável isoladamente. Valida project/job por
    allowlist antes de interpolar. Lança DsConsoleError em entrada inválida.
    """
    spec = DSJOB_COMMANDS.get(command)
    if not spec:
        raise DsConsoleError(f"Comando não suportado: {command!r}")

    _validate_name(project, "Projeto")

    # -logdetail tem assinatura própria: exige o id do evento (pegue no logsum).
    #   dsjob -logdetail -full <project> <job> <event_id>
    if command == "logdetail":
        _validate_name(job, "Job")
        try:
            ev = int(event_id)
        except (TypeError, ValueError):
            raise DsConsoleError(
                "Informe o id do evento (número) — pegue no resumo do log (logsum).")
        if ev < 0:
            raise DsConsoleError("Id do evento inválido.")
        cmd = (f"{DS_DSHOME}/bin/dsjob -logdetail -full "
               f"{shlex.quote(project)} {shlex.quote(job)} {ev}")  # type: ignore[arg-type]
        return cmd, spec["timeout"]

    parts = [f"{DS_DSHOME}/bin/dsjob", spec["flag"]]

    if command == "logsum":
        try:
            n = int(max_lines)
        except (TypeError, ValueError):
            n = 200
        n = max(1, min(n, 2000))  # limita volume
        parts += ["-max", str(n)]

    parts.append(shlex.quote(project))
    if spec["needs_job"]:
        _validate_name(job, "Job")
        parts.append(shlex.quote(job))  # type: ignore[arg-type]

    # -report exige o tipo de relatório como último argumento (BASIC|DETAIL|XML).
    if command == "report":
        parts.append("DETAIL")

    return " ".join(parts), spec["timeout"]


def run_dsjob(command: str, project: str, job: str | None = None,
              max_lines: int = 200, event_id=None) -> dict:
    """
    Executa o `dsjob` no Unix via SSH e devolve {exit_code, stdout, stderr, duration_ms}.

    Lança DsConsoleError (config/validação) ou Exception (falha de SSH).
    """
    if not ssh_configured():
        raise DsConsoleError(
            "SSH do DataStage não configurado no servidor. "
            "Defina DS_SSH_HOST e DS_SSH_USER (e DS_SSH_PASSWORD ou DS_SSH_KEY_FILE) no ambiente da API.")

    dsjob_cmd, timeout = build_dsjob_command(command, project, job, max_lines, event_id)

    import paramiko  # import tardio: lib só é necessária em runtime, não nos testes

    host = os.getenv("DS_SSH_HOST")
    port = int(os.getenv("DS_SSH_PORT", "22"))
    user = os.getenv("DS_SSH_USER")
    password = os.getenv("DS_SSH_PASSWORD") or None
    key_file = os.getenv("DS_SSH_KEY_FILE") or None

    full_cmd = f"source {DS_DSHOME}/dsenv >/dev/null 2>&1; {dsjob_cmd}"

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    t0 = time.time()
    try:
        client.connect(
            hostname=host, port=port, username=user,
            password=password, key_filename=key_file,
            timeout=10, banner_timeout=15, auth_timeout=15,
        )
        _, stdout, stderr = client.exec_command(full_cmd, timeout=timeout)
        exit_code = stdout.channel.recv_exit_status()
        out = stdout.read().decode(errors="replace").strip()
        err = stderr.read().decode(errors="replace").strip()
    finally:
        client.close()

    return {
        # cap alto: logsum/logdetail podem ter centenas de eventos e o que importa
        # (abort) costuma estar no FIM — truncar curto cortaria justamente isso.
        "exit_code": exit_code,
        "stdout": out[:200000],
        "stderr": err[:8000],
        "duration_ms": int((time.time() - t0) * 1000),
    }
