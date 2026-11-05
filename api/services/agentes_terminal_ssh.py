"""api/services/agentes_terminal_ssh.py — servidores e execução remota do agente Terminal (F3 da spec
docs/spec-agente-terminal.md).

**Registro PRÓPRIO de servidores** — não é `ssh_arquivos.SERVIDORES`: aquele alimenta o seletor de
servidor da tela de Utilitários, e acrescentar o Airflow lá daria a quem usa Utilitários um servidor que
nunca pediu. Aqui cada servidor é configurado por variáveis de ambiente (sem segredo no Git):

    datastage → DS_SSH_HOST/PORT/USER/PASSWORD/KEY_FILE   (as mesmas do Console DataStage)
    airflow   → AF_SSH_HOST/PORT/USER/PASSWORD/KEY_FILE   (novas; sem elas o servidor "não está configurado")
    pastas de leitura → TERMINAL_RAIZES_<ID> (lista separada por vírgula; padrão em agentes_terminal_classe)
    containers para `docker logs/stats` → TERMINAL_CONTAINERS_<ID> (lista; sem ela, qualquer container do host)
    known_hosts → <PREFIXO>_SSH_KNOWN_HOSTS, ou DS_SSH_KNOWN_HOSTS. **Obrigatório**: sem ele a conexão FALHA
        (a senha seguiria para um host impostor). Só no DEV: TERMINAL_SSH_AUTO_ADD=1 aceita qualquer host key.

⚠️ A CONTA SSH É O TETO REAL: o que o Terminal consegue ler/escrever é o que ESSA conta consegue, não o que o
classificador permite (ele só restringe). É uma conta de serviço COMPARTILHADA — um desenvolvedor lê o que a conta
enxerga, mesmo que ele próprio não tenha esse acesso. Use conta de menor privilégio, SEM o grupo `docker` (equivale
a root no host) e, se precisar de `docker logs`, limite os containers em TERMINAL_CONTAINERS_<ID>.

A execução é síncrona (paramiko) e roda em `asyncio.to_thread`, atrás do `SEMAFORO_SSH` — o mesmo teto de
sessões do DataStage. Limites: tempo total e bytes lidos. **Fechar o canal NÃO mata o processo remoto** (sem pty não
há SIGHUP: `grep`/`find` sem saída seguiriam rodando órfãos). Por isso o comando vai embrulhado em
`timeout -k 2 N` quando o servidor tem o `timeout` do coreutils (fallback: roda sem — servidores sem `timeout`,
ex. AIX, dependem só do fechamento do canal; documentado no release note). stdin é fechado de imediato (comando que
lê a entrada padrão termina em vez de pendurar).
"""
from __future__ import annotations

import asyncio
import os
import posixpath
import re
import shlex
import time
from dataclasses import dataclass

from services import agentes_ferramentas as af
from services.agentes_terminal_classe import RAIZES_PADRAO

TIMEOUT_PADRAO_S = 30
MAX_BYTES_PADRAO = 64 * 1024  # corte duro da leitura do canal (a saída ao modelo é bem menor)
_DEFINICOES = {
    "datastage": ("DS_SSH", "Servidor DataStage"),
    "airflow": ("AF_SSH", "Servidor Orquestra/Airflow"),
}


@dataclass(frozen=True)
class ServidorTerminal:
    id: str
    label: str
    host: str
    port: int
    user: str
    password: str | None
    key_file: str | None
    known_hosts: str | None
    raizes: tuple[str, ...]
    containers: tuple[str, ...] | None = None  # allowlist de `docker logs/stats`; None = qualquer


@dataclass
class ResultadoExec:
    stdout: str
    stderr: str
    exit_code: int | None
    truncada: bool
    estourou_tempo: bool
    duracao_ms: int


class TerminalSshErro(Exception):
    """Falha de configuração/conexão, com mensagem que o modelo e o usuário podem ler (sem segredo)."""


def _raizes(servidor_id: str) -> tuple[str, ...]:
    bruto = (os.getenv(f"TERMINAL_RAIZES_{servidor_id.upper()}") or "").strip()
    if not bruto:
        return RAIZES_PADRAO
    saida = []
    for r in bruto.split(","):
        r = posixpath.normpath(re.sub(r"/+", "/", r.strip()))
        if r.startswith("/") and r != "/":  # "/" liberaria o servidor inteiro
            saida.append(r)
    return tuple(saida) or RAIZES_PADRAO


def _containers(servidor_id: str) -> tuple[str, ...] | None:
    bruto = (os.getenv(f"TERMINAL_CONTAINERS_{servidor_id.upper()}") or "").strip()
    if not bruto:
        return None  # variável ausente = sem restrição (documentado)
    # Variável PREENCHIDA com nomes inválidos ("web db" sem vírgula…) = erro de configuração: falha FECHADA (nenhum container).
    return tuple(n for n in (p.strip() for p in bruto.split(",")) if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", n))


def _um(servidor_id: str) -> ServidorTerminal | None:
    prefixo, label = _DEFINICOES[servidor_id]
    host = (os.getenv(f"{prefixo}_HOST") or "").strip()
    user = (os.getenv(f"{prefixo}_USER") or "").strip()
    if not host or not user:
        return None
    try:
        porta = int(os.getenv(f"{prefixo}_PORT") or 22)
    except ValueError:
        porta = 22
    known = (os.getenv(f"{prefixo}_KNOWN_HOSTS") or os.getenv("DS_SSH_KNOWN_HOSTS") or "").strip() or None
    return ServidorTerminal(
        id=servidor_id, label=label, host=host, port=porta, user=user,
        password=os.getenv(f"{prefixo}_PASSWORD") or None, key_file=os.getenv(f"{prefixo}_KEY_FILE") or None,
        known_hosts=known, raizes=_raizes(servidor_id), containers=_containers(servidor_id))


def servidores() -> dict[str, ServidorTerminal]:
    """Só os servidores CONFIGURADOS (host e usuário definidos)."""
    return {sid: s for sid in _DEFINICOES if (s := _um(sid)) is not None}


def listar() -> list[dict]:
    """Todos os servidores conhecidos, com o estado de configuração (sem host/usuário/segredo)."""
    configurados = servidores()
    return [{"id": sid, "label": _DEFINICOES[sid][1], "configurado": sid in configurados} for sid in _DEFINICOES]


def _conectar(srv: ServidorTerminal):
    import paramiko  # import tardio: só é necessário em runtime, não nos testes

    cliente = paramiko.SSHClient()
    if srv.known_hosts:
        if not os.path.isfile(srv.known_hosts):
            raise TerminalSshErro("O arquivo known_hosts configurado para o servidor não pode ser lido.")
        cliente.load_host_keys(srv.known_hosts)
        cliente.set_missing_host_key_policy(paramiko.RejectPolicy())
    elif (os.getenv("TERMINAL_SSH_AUTO_ADD") or "").strip() == "1":
        cliente.set_missing_host_key_policy(paramiko.AutoAddPolicy())  # só DEV: aceita qualquer host key
    else:
        raise TerminalSshErro("known_hosts não configurado para este servidor — por segurança a conexão não foi aberta "
                              "(defina <PREFIXO>_SSH_KNOWN_HOSTS; só no DEV, TERMINAL_SSH_AUTO_ADD=1).")
    try:
        cliente.connect(hostname=srv.host, port=srv.port, username=srv.user, password=srv.password,
                        key_filename=srv.key_file, allow_agent=False, look_for_keys=False,
                        timeout=10, banner_timeout=15, auth_timeout=15)
    except Exception as e:  # noqa: BLE001 — a mensagem do paramiko pode citar host/usuário: só o tipo vai adiante
        raise TerminalSshErro(f"Não foi possível conectar ao servidor ({type(e).__name__}).") from None
    return cliente


def embrulhar(linha: str, timeout_s: int) -> str:
    """Prefixa `timeout -k 2 N` (coreutils) para o processo REMOTO morrer ao estourar o tempo — fechar o canal sem
    pty não o mata. Texto FIXO nosso em volta de `linha` (que já vem com cada token re-citado); `sh -c` para não
    depender do shell de login da conta. Sem `timeout` no servidor, cai no comando puro."""
    n = max(1, int(timeout_s))
    interno = (f"if command -v timeout >/dev/null 2>&1; then exec timeout -k 2 {n} {linha}; else exec {linha}; fi")
    return f"/bin/sh -c {shlex.quote(interno)}"


def executar_bloqueante(srv: ServidorTerminal, linha: str, *, timeout_s: int = TIMEOUT_PADRAO_S,
                        max_bytes: int = MAX_BYTES_PADRAO) -> ResultadoExec:
    """Roda `linha` (já com cada token re-citado — ver `linha_de_execucao`) e devolve a saída, com os limites."""
    t0 = time.monotonic()
    cliente = _conectar(srv)
    out, err = bytearray(), bytearray()
    truncada = estourou = False
    codigo: int | None = None
    try:
        canal = cliente.get_transport().open_session(timeout=10)
        canal.settimeout(1.0)
        canal.exec_command(embrulhar(linha, timeout_s))
        canal.shutdown_write()  # stdin em EOF: nada fica esperando entrada
        limite = t0 + timeout_s
        while True:
            houve = False
            if canal.recv_ready():
                out += canal.recv(8192)
                houve = True
            if canal.recv_stderr_ready():
                err += canal.recv_stderr(8192)
                houve = True
            if len(out) + len(err) > max_bytes:
                truncada = True
                break
            if not houve:
                if canal.exit_status_ready() and not canal.recv_ready() and not canal.recv_stderr_ready():
                    break
                time.sleep(0.05)
            if time.monotonic() > limite:
                estourou = True
                break
        if canal.exit_status_ready():
            codigo = canal.recv_exit_status()
        canal.close()  # libera o canal; quem mata o processo remoto é o `timeout -k 2` do `embrulhar` (sem pty não há SIGHUP)
    finally:
        cliente.close()
    return ResultadoExec(
        stdout=bytes(out[:max_bytes]).decode("utf-8", "replace"),
        stderr=bytes(err[:max(0, max_bytes - len(out))]).decode("utf-8", "replace"),
        exit_code=codigo, truncada=truncada, estourou_tempo=estourou,
        duracao_ms=int((time.monotonic() - t0) * 1000))


async def executar(srv: ServidorTerminal, linha: str, *, teto_sessoes: int, espera_max_s: float,
                   timeout_s: int = TIMEOUT_PADRAO_S, max_bytes: int = MAX_BYTES_PADRAO) -> ResultadoExec:
    """`executar_bloqueante` atrás do semáforo de SSH, com a mesma proteção de cancelamento do `dsjob`:
    cancelar enquanto só está NA FILA é seguro; depois de obtida a vaga a sessão real não é interrompível,
    então só essa fase é protegida com `asyncio.shield` (o semáforo nunca "mente" uma vaga livre)."""
    gerenciador = await af.SEMAFORO_SSH(teto_sessoes, espera_max_s)  # pode levantar ServidorOcupado

    async def _com_a_vaga():
        async with gerenciador:
            return await asyncio.to_thread(executar_bloqueante, srv, linha, timeout_s=timeout_s, max_bytes=max_bytes)

    tarefa = asyncio.ensure_future(_com_a_vaga())
    try:
        return await asyncio.shield(tarefa)
    except asyncio.CancelledError:
        if not tarefa.cancelled():
            tarefa.add_done_callback(lambda t: None if t.cancelled() else t.exception())
        raise
