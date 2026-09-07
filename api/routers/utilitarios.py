"""api/routers/utilitarios.py — tela Utilitários: arquivos no servidor por SFTP.

Spec: docs/spec-utilitarios-arquivos.md (F1 = leitura + cadastro do admin).

  GET  /utilitarios/config                    — servidores, raízes ativas, extensões, teto, pode_gravar
  POST /utilitarios/arquivo/ler               — {servidor, diretorio, nome, ultimas_linhas?, codificacao?}
  POST /utilitarios/arquivo/gravar            — {servidor, diretorio, nome, extensao, conteudo, codificacao?, sobrescrever?}  [+ acao_editar]
  GET  /utilitarios/pasta/listar              — ?servidor&caminho?&mostrar_ocultos → entradas da pasta (sem caminho: as raízes)
  GET  /utilitarios/admin/raizes              — todas (inclusive inativas)            [admin]
  POST /utilitarios/admin/raizes              — {servidor, caminho} → {id}            [admin]
  PATCH /utilitarios/admin/raizes/{id}        — {ativo?, caminho?}                     [admin]
  POST /utilitarios/admin/raizes/{id}/testar  — stat no servidor                       [admin]
  GET  /utilitarios/admin/extensoes                                                    [admin]
  POST /utilitarios/admin/extensoes           — {extensao}                             [admin]
  DELETE /utilitarios/admin/extensoes/{ext}                                            [admin]
  PUT  /utilitarios/admin/config              — {tamanho_max_kb, backup_ao_sobrescrever} [admin]

Permissão: `require_tela_utilitarios` (admin OU recurso tela_utilitarios). Gravar
(F4) exige também PERM_EDITAR — `pode_gravar` no /config já diz isso à tela.

Política e SFTP vivem em `services/ssh_arquivos.py`; aqui fica o banco (raízes,
extensões, config, auditoria) e a tradução ArquivoError → HTTP. Todo acesso SSH
roda num executor DEDICADO com teto de tempo — o paramiko é bloqueante, e N
leituras presas não podem esgotar o `to_thread` que o resto da API compartilha.
A conexão com o banco é aberta e fechada em volta de cada consulta: nunca fica
presa esperando o SSH.

Auditoria: TODA saída de /arquivo/ler grava uma linha (ok / negado / erro),
inclusive as 422 de validação — quem tenta `..` e erra a sintaxe também fica no
rastro. O detalhe interno (host, erro cru do paramiko) vai ao log e à auditoria;
a resposta leva só a mensagem genérica.

Degradação: sem a migration 105, `/config` responde 503 nomeando a migration e a
tela mostra o aviso; o resto do Orquestra não é afetado.
"""
from __future__ import annotations

import asyncio
import logging
import os
import posixpath
import re
import tempfile
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

from functools import partial

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query, Request
from fastapi.responses import StreamingResponse
from starlette.requests import ClientDisconnect

from db import get_db_conn
from deps import PERM_EDITAR, get_admin_user, require_tela_utilitarios
from services import ssh_arquivos as svc

log = logging.getLogger("orquestra-api")

router = APIRouter()

K_TETO = "utilitarios_arquivo_max_kb"
K_BACKUP = "utilitarios_arquivo_backup"
_INT_RE = re.compile(r"^-?\d+$")
_TABELAS = ("etl_utilitario_raiz", "etl_utilitario_extensao", "etl_utilitario_arquivo_log")
_ID_MAX = 2_147_483_647  # INT do SQL Server

# Executor só dos Utilitários: 4 conexões SSH simultâneas no máximo; a 5ª espera
# na fila (e cai no teto de tempo se demorar). Nada disto toca o pool padrão do
# `asyncio.to_thread`, usado por reconciliação, monitor e execuções.
_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="orq-utilitarios-ssh")
_TIMEOUT_S = 90
# Transferências (spec docs/spec-utilitarios-transferencia.md): 50 MB por SFTP
# leva mais que uma leitura de texto — teto próprio, abaixo dos 300 s do nginx.
_TIMEOUT_TRANSFERENCIA_S = 240
# No máximo 2 transferências por worker ao mesmo tempo: a 3ª ouve "ocupado" na
# hora em vez de esperar na fila do executor, e sobram 2 threads para ler,
# listar e gravar — fora a janela de até 60 s depois de um 504, em que a thread
# presa ainda ocupa o executor com a vaga já devolvida. É por worker do
# uvicorn, não por instância, e limita o SFTP, não respostas em voo (spec §8).
_VAGAS_TRANSFERENCIA = threading.BoundedSemaphore(2)
# O arquivo transferido passa por um spool: até 8 MB em memória, o resto em
# arquivo temporário do container — nunca 50 MB numa `bytes` por pedido.
_SPOOL_MEMORIA = 8 * 1024 * 1024
# Upload: quanto tempo o corpo pode ficar SEM chegar um pedaço. O uvicorn não
# tem timeout de leitura de corpo; sem isto um cliente gotejando direto na
# porta 8000 seguraria spool e conexão por horas (revisão da F3).
_TIMEOUT_CORPO_S = 60


def _desfecho_tardio(fut) -> None:
    """A thread presa num 504 terminou depois: fica no log, não some."""
    exc = fut.exception() if not fut.cancelled() else None
    if exc is None:
        log.warning("Utilitários: a operação SSH que estourou o teto TERMINOU depois do 504.")
    else:
        log.warning("Utilitários: a operação SSH que estourou o teto falhou depois do 504: %r", exc)


async def _no_servidor(fn, *args, timeout: float | None = None, tardio=None):
    """Roda `fn` (bloqueante, SSH) no executor dedicado, com teto de tempo.

    Passado o teto a requisição é liberada com 504; a thread presa termina por
    conta do timeout de canal (60 s) e do keepalive — não há como matá-la. O
    que ela fizer DEPOIS do 504 (gravar o arquivo, falhar) não some: `tardio`
    (ou o log, por padrão) recebe o future quando ela acaba — o `shield`
    mantém o future vivo depois do cancelamento do `wait_for`."""
    teto = _TIMEOUT_S if timeout is None else timeout
    loop = asyncio.get_running_loop()
    fut = loop.run_in_executor(_EXECUTOR, fn, *args)
    try:
        return await asyncio.wait_for(asyncio.shield(fut), timeout=teto)
    except asyncio.TimeoutError:
        fut.add_done_callback(tardio or _desfecho_tardio)
        raise svc.ArquivoError(504, f"O servidor não respondeu em {teto} s.")


# ── banco: helpers ───────────────────────────────────────────────────────────

def _fechar(conn, cur) -> None:
    for x in (cur, conn):
        try:
            x.close()
        except Exception:
            pass


def _tabelas_ok(cur) -> bool:
    cur.execute(
        "SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES "
        "WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME IN (?, ?, ?)", list(_TABELAS))
    row = cur.fetchone()
    return bool(row and int(row[0]) == len(_TABELAS))


def _exigir_tabelas(cur) -> None:
    if not _tabelas_ok(cur):
        raise HTTPException(
            status_code=503,
            detail="Utilitários indisponíveis: migration 105 pendente "
                   "(tabelas etl_utilitario_* ausentes).")


def _teto_kb(bruto) -> int:
    try:
        v = int(str(bruto).strip())
    except (TypeError, ValueError):
        return svc.TETO_PADRAO_KB
    return max(1, min(v, svc.TETO_MAX_KB))


def _carregar_config(cur) -> dict:
    """Raízes ATIVAS, extensões e as duas chaves de etl_app_config."""
    cur.execute(
        "SELECT id, servidor, caminho FROM dbo.etl_utilitario_raiz "
        "WHERE ativo = 1 ORDER BY servidor, caminho")
    raizes = [{"id": r[0], "servidor": r[1], "caminho": r[2]} for r in cur.fetchall()]
    cur.execute("SELECT extensao FROM dbo.etl_utilitario_extensao ORDER BY extensao")
    extensoes = [r[0] for r in cur.fetchall()]
    cfg: dict = {}
    try:
        cur.execute(
            "SELECT config_key, config_value FROM dbo.etl_app_config "
            "WHERE config_key IN (?, ?)", [K_TETO, K_BACKUP])
        cfg = {r[0]: r[1] for r in cur.fetchall()}
    except Exception:
        cfg = {}  # chaves ausentes → defaults da spec
    return {
        "raizes": raizes,
        "extensoes": extensoes,
        "tamanho_max_kb": _teto_kb(cfg.get(K_TETO)),
        "backup_ao_sobrescrever": (cfg.get(K_BACKUP) or "1").strip() != "0",
        # Constante (não vem do banco): a tela recusa arquivo grande ANTES de enviar.
        "transferencia_max_kb": svc.TRANSFERENCIA_MAX_BYTES // 1024,
    }


def _config_do_banco() -> dict:
    conn = get_db_conn()
    cur = conn.cursor()
    try:
        _exigir_tabelas(cur)
        return _carregar_config(cur)
    finally:
        _fechar(conn, cur)


def _auditar(*, usuario: str, servidor: str, acao: str, caminho: str, resultado: str,
             tamanho=None, sha256=None, detalhe=None, duracao_ms=None) -> None:
    """Best-effort: auditoria que falha não derruba a leitura — mas avisa no log.

    Cortes em unidades UTF-16 (o que NVARCHAR conta): `[:1000]` em code points
    deixaria passar um caminho de 600 emojis, o INSERT estouraria e a auditoria
    da tentativa sumiria em silêncio."""
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        try:
            cur.execute(
                "INSERT INTO dbo.etl_utilitario_arquivo_log "
                "(usuario, servidor, acao, caminho, tamanho_bytes, sha256, resultado, detalhe, duracao_ms) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [svc.cortar_utf16(str(usuario or "?"), 100),
                 svc.cortar_utf16(str(servidor or "?"), 50),
                 acao,
                 svc.cortar_utf16(caminho or "", svc.LIMITE_CAMINHO),
                 tamanho, sha256, resultado,
                 svc.cortar_utf16(detalhe or "", 500) or None,
                 duracao_ms])
            conn.commit()
        finally:
            _fechar(conn, cur)
    except Exception:
        log.warning("Utilitários: falha ao auditar %s %s (%s)", acao, caminho, resultado, exc_info=True)


def _ms(t0: float) -> int:
    return int((time.time() - t0) * 1000)


def _inteiro(valor, campo: str, minimo: int, maximo: int) -> int:
    """Inteiro de verdade: bool não é inteiro, 2048.9 não é inteiro, "2048" é."""
    if isinstance(valor, bool):
        raise HTTPException(status_code=422, detail=f"'{campo}' precisa ser um inteiro.")
    if isinstance(valor, float):
        if not valor.is_integer():
            raise HTTPException(status_code=422, detail=f"'{campo}' precisa ser um inteiro.")
        valor = int(valor)
    elif isinstance(valor, str):
        s = valor.strip()
        if not _INT_RE.match(s):
            raise HTTPException(status_code=422, detail=f"'{campo}' precisa ser um inteiro.")
        valor = int(s)
    elif not isinstance(valor, int):
        raise HTTPException(status_code=422, detail=f"'{campo}' precisa ser um inteiro.")
    if valor < minimo or valor > maximo:
        raise HTTPException(
            status_code=422, detail=f"'{campo}' precisa estar entre {minimo} e {maximo}.")
    return valor


# ── config da tela ───────────────────────────────────────────────────────────

@router.get("/utilitarios/config")
async def utilitarios_config(user: dict = Depends(require_tela_utilitarios)):
    cfg = _config_do_banco()
    return {
        "servidores": svc.servidores_disponiveis(),
        "raizes": cfg["raizes"],
        "extensoes": cfg["extensoes"],
        "tamanho_max_kb": cfg["tamanho_max_kb"],
        "backup_ao_sobrescrever": cfg["backup_ao_sobrescrever"],
        "transferencia_max_kb": cfg["transferencia_max_kb"],
        "pode_gravar": PERM_EDITAR in user.get("permissoes", []),
    }


# ── ler arquivo ──────────────────────────────────────────────────────────────

def _ultimas_linhas_valido(bruto) -> int | None:
    if isinstance(bruto, bool):
        raise HTTPException(status_code=422, detail="'ultimas_linhas' precisa ser um inteiro.")
    if bruto in (None, "", 0, "0"):
        return None
    return _inteiro(bruto, "ultimas_linhas", 1, svc.ULTIMAS_LINHAS_MAX)


def _ler_sync(servidor: str, caminho: str, raizes: list[str], teto_bytes: int,
              ultimas: int | None, codificacao: str | None) -> dict:
    with svc.conexao_sftp(servidor) as sftp:
        return svc.ler_arquivo(sftp, caminho, raizes, teto_bytes=teto_bytes,
                               ultimas=ultimas, codificacao=codificacao)


@router.post("/utilitarios/arquivo/ler")
async def utilitarios_ler_arquivo(body: dict = Body(...),
                                  user: dict = Depends(require_tela_utilitarios)):
    t0 = time.time()
    usuario = str(user.get("matricula") or "?")
    diretorio = body.get("diretorio")
    nome = body.get("nome")
    pedido_bruto = f"{str(diretorio or '').rstrip('/')}/{str(nome or '')}"
    servidor = str(body.get("servidor") or "datastage")

    # Validação do pedido — 422 também é auditado: quem tenta e erra a sintaxe fica no rastro.
    try:
        servidor = svc.servidor_valido(body.get("servidor"))
        ultimas = _ultimas_linhas_valido(body.get("ultimas_linhas"))
        codificacao = svc.codificacao_valida(body.get("codificacao"))
        if not isinstance(diretorio, str) or not isinstance(nome, str):
            # `str(["x"])` viraria o nome "['x']" — texto ou nada.
            raise HTTPException(status_code=422, detail="'diretorio' e 'nome' precisam ser texto.")
    except svc.ArquivoError as e:
        _auditar(usuario=usuario, servidor=servidor, acao="ler", caminho=pedido_bruto,
                 resultado=e.resultado, detalhe=e.interno or e.detail, duracao_ms=_ms(t0))
        raise HTTPException(status_code=e.status, detail=e.detail)
    except HTTPException as e:
        _auditar(usuario=usuario, servidor=servidor, acao="ler", caminho=pedido_bruto,
                 resultado="erro", detalhe=str(e.detail), duracao_ms=_ms(t0))
        raise

    cfg = _config_do_banco()
    raizes = [r["caminho"] for r in cfg["raizes"] if r["servidor"] == servidor]
    if not raizes:
        _auditar(usuario=usuario, servidor=servidor, acao="ler", caminho=pedido_bruto,
                 resultado="negado", detalhe="nenhum diretório-raiz ativo para o servidor",
                 duracao_ms=_ms(t0))
        raise HTTPException(
            status_code=403,
            detail="Nenhum diretório liberado para este servidor — cadastre uma raiz em "
                   "Admin › Utilitários.")

    # Validação e conferência LEXICAL antes de qualquer SSH.
    try:
        caminho, _raiz = svc.preparar_leitura(diretorio, nome, raizes)
    except svc.ArquivoError as e:
        _auditar(usuario=usuario, servidor=servidor, acao="ler", caminho=pedido_bruto,
                 resultado=e.resultado, detalhe=e.interno or e.detail, duracao_ms=_ms(t0))
        raise HTTPException(status_code=e.status, detail=e.detail)

    teto_bytes = cfg["tamanho_max_kb"] * 1024
    try:
        resultado = await _no_servidor(
            _ler_sync, servidor, caminho, raizes, teto_bytes, ultimas, codificacao)
    except svc.ArquivoError as e:
        _auditar(usuario=usuario, servidor=servidor, acao="ler", caminho=caminho,
                 resultado=e.resultado, detalhe=e.interno or e.detail, duracao_ms=_ms(t0))
        raise HTTPException(status_code=e.status, detail=e.detail)
    except Exception as e:
        log.exception("Utilitários: falha inesperada ao ler %s", caminho)
        _auditar(usuario=usuario, servidor=servidor, acao="ler", caminho=caminho,
                 resultado="erro", detalhe=f"inesperado: {e!r}", duracao_ms=_ms(t0))
        raise HTTPException(
            status_code=502, detail="Falha ao ler o arquivo — detalhe registrado no log da API.")

    resultado["duracao_ms"] = _ms(t0)
    detalhe = f"últimas {ultimas} linhas (truncado)" if resultado["truncado"] else None
    _auditar(usuario=usuario, servidor=servidor, acao="ler", caminho=resultado["caminho"],
             resultado="ok", tamanho=resultado["tamanho_bytes"], detalhe=detalhe,
             duracao_ms=resultado["duracao_ms"])
    return resultado


# ── baixar arquivo (transferência — spec docs/spec-utilitarios-transferencia.md) ──

def _baixar_sync(servidor: str, caminho: str, raizes: list[str], teto_bytes: int, destino) -> dict:
    with svc.conexao_sftp(servidor) as sftp:
        return svc.baixar_arquivo(sftp, caminho, raizes, teto_bytes=teto_bytes, destino=destino)


def _servir_spool(spool):
    """Gerador da resposta: entrega o spool em blocos e o fecha no fim — também
    quando o cliente desiste no meio (o `finally` roda no `close()` do gerador).
    Se o cliente sumir ANTES do 1º bloco, o gerador nunca inicia e o `finally`
    não roda: aí o arquivo fecha no descarte do objeto (e o `TemporaryFile` do
    spool já nasce sem nome no Linux — não sobra órfão no disco)."""
    try:
        while True:
            bloco = spool.read(svc.BLOCO_TRANSFERENCIA)
            if not bloco:
                break
            yield bloco
    finally:
        spool.close()


@router.get("/utilitarios/arquivo/baixar")
async def utilitarios_baixar_arquivo(servidor: str = Query("datastage"),
                                     diretorio: str | None = Query(None),
                                     nome: str | None = Query(None),
                                     user: dict = Depends(require_tela_utilitarios)):
    """Download de um arquivo abaixo de uma raiz — QUALQUER arquivo, binário
    incluído (sem o teste de texto do `ler`), até TRANSFERENCIA_MAX_BYTES. Mesma
    permissão da leitura: ter a tela.

    O arquivo desce inteiro para um spool ANTES de a resposta começar: o
    Content-Length é exato, o sha256 vai à auditoria e a vaga SSH é liberada
    cedo (o nginx bufferizaria a resposta de qualquer forma). `ok` na auditoria
    = a API leu o arquivo do servidor; a entrega ao navegador não é confirmável
    daqui. Erros saem em JSON `{detail}` como o resto da API."""
    t0 = time.time()
    usuario = str(user.get("matricula") or "?")
    pedido_bruto = f"{str(diretorio or '').rstrip('/')}/{str(nome or '')}"
    servidor = str(servidor or "datastage")

    def negar(status: int, detalhe: str, resultado: str = "erro", caminho: str = pedido_bruto,
              detail=None):
        _auditar(usuario=usuario, servidor=servidor, acao="baixar", caminho=caminho,
                 resultado=resultado, detalhe=detalhe, duracao_ms=_ms(t0))
        raise HTTPException(status_code=status, detail=detail if detail is not None else detalhe)

    # `detail=e.detail` sempre: o `interno` (erro cru, host:porta) é da
    # auditoria, nunca da resposta — mesmo que hoje nenhum erro pré-SSH o tenha.
    try:
        servidor = svc.servidor_valido(servidor)
    except svc.ArquivoError as e:
        negar(e.status, e.interno or e.detail, e.resultado, detail=e.detail)

    cfg = _config_do_banco()
    raizes = [r["caminho"] for r in cfg["raizes"] if r["servidor"] == servidor]
    if not raizes:
        negar(403, "Nenhum diretório liberado para este servidor — cadastre uma raiz em "
                   "Admin › Utilitários.", "negado")
    # Validação e conferência LEXICAL antes de qualquer SSH (403 sem revelar existência).
    try:
        caminho, _raiz = svc.preparar_leitura(diretorio, nome, raizes)
    except svc.ArquivoError as e:
        negar(e.status, e.interno or e.detail, e.resultado, detail=e.detail)

    if not _VAGAS_TRANSFERENCIA.acquire(blocking=False):
        negar(503, "Há transferências em andamento — tente de novo em instantes.", caminho=caminho)
    spool = tempfile.SpooledTemporaryFile(max_size=_SPOOL_MEMORIA)
    try:
        try:
            resultado = await _no_servidor(
                _baixar_sync, servidor, caminho, raizes, svc.TRANSFERENCIA_MAX_BYTES, spool,
                timeout=_TIMEOUT_TRANSFERENCIA_S)
        finally:
            _VAGAS_TRANSFERENCIA.release()
    except svc.ArquivoError as e:
        # Fechar o spool também derruba a thread que ficou presa num 504: o
        # próximo `write` dela falha em vez de encher o disco por mais 50 MB.
        spool.close()
        negar(e.status, e.interno or e.detail, e.resultado, caminho=caminho, detail=_detalhe_http(e))
    except Exception as e:
        spool.close()
        log.exception("Utilitários: falha inesperada ao baixar %s", caminho)
        negar(502, f"inesperado: {e!r}", caminho=caminho,
              detail="Falha ao baixar o arquivo — detalhe registrado no log da API.")

    resultado["duracao_ms"] = _ms(t0)
    _auditar(usuario=usuario, servidor=servidor, acao="baixar", caminho=resultado["caminho"],
             resultado="ok", tamanho=resultado["tamanho_bytes"], sha256=resultado["sha256"],
             duracao_ms=resultado["duracao_ms"])
    spool.seek(0)
    cabecalhos = {
        # O nome PEDIDO (validado), não o real: com link, o real é o alvo.
        "Content-Disposition": svc.content_disposition(posixpath.basename(caminho)),
        "Content-Length": str(resultado["tamanho_bytes"]),
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
        "X-Orquestra-Sha256": resultado["sha256"],
    }
    return StreamingResponse(_servir_spool(spool), media_type="application/octet-stream",
                             headers=cabecalhos)


# ── enviar arquivo (transferência F3 — spec docs/spec-utilitarios-transferencia.md) ──

def _enviar_sync(servidor: str, caminho: str, raizes: list[str], origem, tamanho: int,
                 sobrescrever: bool, backup: bool, marca: str) -> dict:
    with svc.conexao_sftp(servidor) as sftp:
        return svc.enviar_arquivo(sftp, caminho, raizes, origem, tamanho, sobrescrever=sobrescrever,
                                  backup=backup, marca=marca)


def _tamanho_declarado(request: Request) -> int:
    """O Content-Length, ANTES de ler um byte do corpo. Sem ele (corpo chunked)
    é 411: o teto tem de valer antes de o corpo ocupar disco; inválido é 422.
    (Atrás do nginx, que bufferiza e reenvia com Content-Length, o 411 não
    acontece; ele vale para quem fala direto com a API.)"""
    bruto = request.headers.get("content-length")
    if bruto is None:
        raise svc.ArquivoError(
            411, "Envie o Content-Length: o tamanho do arquivo precisa vir antes do corpo.")
    try:
        n = int(bruto.strip())
    except ValueError:
        raise svc.ArquivoError(422, "Content-Length inválido.") from None
    if n < 0:
        raise svc.ArquivoError(422, "Content-Length inválido.")
    return n


async def _proximo_pedaco(iterador, teto_s: float) -> bytes | None:
    """Um pedaço do corpo, ou None no fim; 408 se nada chegar em `teto_s`."""
    try:
        return await asyncio.wait_for(iterador.__anext__(), timeout=teto_s)
    except StopAsyncIteration:
        return None
    except asyncio.TimeoutError:
        raise svc.ArquivoError(
            408, f"O envio parou: nenhum dado chegou em {teto_s:g} s — tente de novo.") from None


async def _drenar(request: Request) -> None:
    """Consome (e descarta) o corpo antes de uma resposta de erro.

    Responder com corpo pendente faz o uvicorn fechar o socket com bytes não
    lidos; o nginx, ainda escrevendo o corpo para o upstream, troca a resposta
    por um `502 Bad Gateway` em HTML (revisão da F3, provado com a imagem de
    produção). Só vale quando o corpo cabe (Content-Length dentro do teto): um
    corpo acima do teto ou sem tamanho não é drenado — ali o 413/411 sai na
    hora e a corrida é documentada."""
    try:
        iterador = request.stream().__aiter__()
        while await _proximo_pedaco(iterador, _TIMEOUT_CORPO_S) is not None:
            pass
    except Exception:  # noqa: BLE001 — a resposta que importa é a do erro original
        pass


@router.put("/utilitarios/arquivo/enviar")
async def utilitarios_enviar_arquivo(request: Request,
                                     servidor: str = Query("datastage"),
                                     diretorio: str | None = Query(None),
                                     nome: str | None = Query(None),
                                     sobrescrever: bool = Query(False),
                                     user: dict = Depends(require_tela_utilitarios)):
    """Upload de um arquivo do PC para abaixo de uma raiz. Corpo CRU
    (`application/octet-stream`, sem multipart — o build da API é pip offline);
    nome e pasta na query; o nome é mantido como está e só a extensão (a
    última) precisa estar na lista do admin. Exige a tela E `acao_editar`.

    Ordem: permissão → validação lexical → Content-Length (413 acima do teto
    SEM ler o corpo) → o corpo desce para um spool contando bytes (400/413 se
    não bater com o declarado, 408 se parar de chegar) → só então a VAGA de
    transferência (ela mede o SFTP, não a rede) e a thread SSH: `.tmp` + backup
    + rename atômico + modo preservado, o mesmo miolo da gravação de texto.
    Erros antes do corpo drenam o corpo antes de responder (ver `_drenar`).
    Corpo vazio cria arquivo de 0 bytes."""
    t0 = time.time()
    usuario = str(user.get("matricula") or "?")
    pedido_bruto = f"{str(diretorio or '').rstrip('/')}/{str(nome or '')}"
    servidor = str(servidor or "datastage")

    def negar(status: int, detalhe: str, resultado: str = "erro", caminho: str = pedido_bruto,
              detail=None):
        _auditar(usuario=usuario, servidor=servidor, acao="enviar", caminho=caminho,
                 resultado=resultado, detalhe=detalhe, duracao_ms=_ms(t0))
        raise HTTPException(status_code=status, detail=detail if detail is not None else detalhe)

    # O tamanho declarado é lido primeiro (sem tocar o corpo): é ele que diz se
    # o corpo pode ser drenado antes de uma recusa (cabe no teto) ou se a recusa
    # sai na hora. A recusa por Content-Length ausente/inválido só é emitida
    # DEPOIS da permissão: quem não pode enviar ouve 403, não 411.
    teto = svc.TRANSFERENCIA_MAX_BYTES
    erro_tamanho: svc.ArquivoError | None = None
    tamanho = -1
    try:
        tamanho = _tamanho_declarado(request)
    except svc.ArquivoError as e:
        erro_tamanho = e
    drenavel = erro_tamanho is None and tamanho <= teto

    async def recusar(status: int, detalhe: str, resultado: str = "erro", caminho: str = pedido_bruto,
                      detail=None):
        if drenavel:
            await _drenar(request)
        negar(status, detalhe, resultado, caminho, detail)

    if PERM_EDITAR not in user.get("permissoes", []):
        await recusar(403, "Enviar arquivo exige a permissão de cadastrar/editar (acao_editar).", "negado")
    try:
        servidor = svc.servidor_valido(servidor)
    except svc.ArquivoError as e:
        await recusar(e.status, e.interno or e.detail, e.resultado, detail=e.detail)

    cfg = _config_do_banco()
    raizes = [r["caminho"] for r in cfg["raizes"] if r["servidor"] == servidor]
    if not raizes:
        await recusar(403, "Nenhum diretório liberado para este servidor — cadastre uma raiz em "
                           "Admin › Utilitários.", "negado")
    try:
        caminho, _raiz = svc.preparar_envio(diretorio, nome, raizes, cfg["extensoes"])
    except svc.ArquivoError as e:
        await recusar(e.status, e.interno or e.detail, e.resultado, detail=e.detail)

    # 411/422 do Content-Length e o 413 cedo: sem ler (nem drenar) o corpo.
    if erro_tamanho is not None:
        negar(erro_tamanho.status, erro_tamanho.detail, caminho=caminho)
    if not drenavel:
        negar(413, f"Arquivo de {svc.formatar_tamanho(tamanho)} ({tamanho} bytes), acima do teto de "
                   f"{svc.formatar_tamanho(teto)} para envio.", caminho=caminho)

    def tardio(fut) -> None:
        # A thread SSH terminou DEPOIS do 504: o arquivo pode ter sido gravado
        # com a tela dizendo que falhou. Fica na auditoria, fora do loop.
        exc = fut.exception() if not fut.cancelled() else None
        detalhe = ("concluído após o 504 — o arquivo FOI gravado" if exc is None
                   else f"falhou após o 504: {exc!r}")
        _desfecho_tardio(fut)
        asyncio.get_running_loop().run_in_executor(None, partial(
            _auditar, usuario=usuario, servidor=servidor, acao="enviar", caminho=caminho,
            resultado="ok" if exc is None else "erro", detalhe=detalhe, duracao_ms=_ms(t0)))

    spool = tempfile.SpooledTemporaryFile(max_size=_SPOOL_MEMORIA)
    vaga = False
    recebidos = 0
    try:
        try:
            iterador = request.stream().__aiter__()
            while True:
                pedaco = await _proximo_pedaco(iterador, _TIMEOUT_CORPO_S)
                if pedaco is None:
                    break
                if not pedaco:
                    continue
                recebidos += len(pedaco)
                if recebidos > tamanho:
                    # Inalcançável no HTTP/1.1 real (h11/httptools enquadram pelo
                    # Content-Length); fica como cinto para outros transportes.
                    raise svc.ArquivoError(
                        413, f"O corpo passou do tamanho declarado no Content-Length ({tamanho} bytes).")
                spool.write(pedaco)
            if recebidos != tamanho:
                raise svc.ArquivoError(
                    400, f"Corpo incompleto: chegaram {recebidos} de {tamanho} bytes — tente de novo.")
            spool.seek(0)
            # A vaga só agora, com o corpo inteiro em mãos: ela limita o SFTP,
            # não a rede — um cliente lento não segura vaga (revisão da F3).
            if not _VAGAS_TRANSFERENCIA.acquire(blocking=False):
                raise svc.ArquivoError(503, "Há transferências em andamento — tente de novo em instantes.")
            vaga = True
            # Única por pedido (pid + aleatório): duas threads do mesmo worker no
            # mesmo instante não podem disputar o mesmo `.tmp`.
            marca = f"{os.getpid()}-{uuid.uuid4().hex[:8]}"
            resultado = await _no_servidor(
                _enviar_sync, servidor, caminho, raizes, spool, tamanho, bool(sobrescrever),
                cfg["backup_ao_sobrescrever"], marca, timeout=_TIMEOUT_TRANSFERENCIA_S, tardio=tardio)
        finally:
            if vaga:
                _VAGAS_TRANSFERENCIA.release()
            # Também derruba a thread presa num 504: o próximo `read` dela falha.
            spool.close()
    except ClientDisconnect:
        # Quem cancela no meio não recebe resposta nenhuma; o que importa é o
        # rastro legível, sem traceback enterrando erros reais no log.
        negar(400, f"o cliente desistiu após {recebidos} de {tamanho} bytes", caminho=caminho)
    except svc.ArquivoError as e:
        negar(e.status, e.interno or e.detail, e.resultado, caminho=caminho, detail=_detalhe_http(e))
    except Exception as e:
        log.exception("Utilitários: falha inesperada ao enviar %s", caminho)
        negar(502, f"inesperado: {e!r}", caminho=caminho,
              detail="Falha ao enviar o arquivo — detalhe registrado no log da API.")

    resultado["duracao_ms"] = _ms(t0)
    partes = ["criado" if resultado["criado"] else "sobrescrito"]
    if resultado["backup"]:
        partes.append(f"backup {resultado['backup']}")
    _auditar(usuario=usuario, servidor=servidor, acao="enviar", caminho=resultado["caminho"],
             resultado="ok", tamanho=resultado["tamanho_bytes"], sha256=resultado["sha256"],
             detalhe="; ".join(partes), duracao_ms=resultado["duracao_ms"])
    return resultado


# ── listar pasta (F6 — navegador) ────────────────────────────────────────────

def _listar_sync(servidor: str, caminho: str, raizes: list[str], mostrar_ocultos: bool) -> dict:
    with svc.conexao_sftp(servidor) as sftp:
        return svc.listar_pasta(sftp, caminho, raizes, mostrar_ocultos=mostrar_ocultos)


@router.get("/utilitarios/pasta/listar")
async def utilitarios_listar_pasta(servidor: str = Query("datastage"),
                                   caminho: str | None = Query(None),
                                   mostrar_ocultos: bool = Query(False),
                                   user: dict = Depends(require_tela_utilitarios)):
    """Nível zero (sem `caminho`) = as raízes ativas do servidor, sem tocar o SSH.
    Com `caminho`, as entradas da pasta (abaixo de uma raiz), auditadas como
    `listar` — quem navega deixa rastro como quem lê."""
    t0 = time.time()
    usuario = str(user.get("matricula") or "?")
    try:
        servidor = svc.servidor_valido(servidor)
    except svc.ArquivoError as e:
        _auditar(usuario=usuario, servidor=str(servidor), acao="listar", caminho=str(caminho or ""),
                 resultado="erro", detalhe=e.detail, duracao_ms=_ms(t0))
        raise HTTPException(status_code=e.status, detail=e.detail)
    cfg = _config_do_banco()
    raizes = [r["caminho"] for r in cfg["raizes"] if r["servidor"] == servidor]

    if caminho is None or not str(caminho).strip():
        return {
            "caminho": None, "caminho_real": None, "raiz": None, "pai": None,
            "entradas": [{"nome": r, "tipo": "raiz", "tamanho_bytes": None, "modificado_em": None} for r in raizes],
            "ocultos_omitidos": 0, "truncado": False, "links_nao_resolvidos": 0,
        }
    if not raizes:
        _auditar(usuario=usuario, servidor=servidor, acao="listar", caminho=str(caminho),
                 resultado="negado", detalhe="nenhum diretório-raiz ativo para o servidor",
                 duracao_ms=_ms(t0))
        raise HTTPException(
            status_code=403,
            detail="Nenhum diretório liberado para este servidor — cadastre uma raiz em "
                   "Admin › Utilitários.")
    try:
        pasta, _raiz = svc.preparar_pasta(caminho, raizes)
    except svc.ArquivoError as e:
        _auditar(usuario=usuario, servidor=servidor, acao="listar", caminho=str(caminho),
                 resultado=e.resultado, detalhe=e.interno or e.detail, duracao_ms=_ms(t0))
        raise HTTPException(status_code=e.status, detail=e.detail)
    try:
        resultado = await _no_servidor(_listar_sync, servidor, pasta, raizes, bool(mostrar_ocultos))
    except svc.ArquivoError as e:
        _auditar(usuario=usuario, servidor=servidor, acao="listar", caminho=pasta,
                 resultado=e.resultado, detalhe=e.interno or e.detail, duracao_ms=_ms(t0))
        raise HTTPException(status_code=e.status, detail=e.detail)
    except Exception as e:
        log.exception("Utilitários: falha inesperada ao listar %s", pasta)
        _auditar(usuario=usuario, servidor=servidor, acao="listar", caminho=pasta,
                 resultado="erro", detalhe=f"inesperado: {e!r}", duracao_ms=_ms(t0))
        raise HTTPException(status_code=502, detail="Falha ao listar a pasta — detalhe registrado no log da API.")
    detalhe = f"{len(resultado['entradas'])} entradas"
    if resultado["truncado"]:
        detalhe += " (lista truncada)"
    if resultado["ocultos_omitidos"]:
        detalhe += f", {resultado['ocultos_omitidos']} ocultos omitidos"
    if resultado["caminho_real"] != resultado["caminho"]:
        # O rastro guarda o real; o link que o usuário atravessou fica no detalhe.
        detalhe += f", pedido: {resultado['caminho']}"
    _auditar(usuario=usuario, servidor=servidor, acao="listar", caminho=resultado["caminho_real"],
             resultado="ok", detalhe=detalhe, duracao_ms=_ms(t0))
    resultado["duracao_ms"] = _ms(t0)
    return resultado


# ── gravar arquivo (F4) ──────────────────────────────────────────────────────

def _gravar_sync(servidor: str, caminho: str, raizes: list[str], dados: bytes,
                 sobrescrever: bool, backup: bool, marca: str) -> dict:
    with svc.conexao_sftp(servidor) as sftp:
        return svc.gravar_arquivo(sftp, caminho, raizes, dados, sobrescrever=sobrescrever,
                                  backup=backup, marca=marca)


def _detalhe_http(e: svc.ArquivoError):
    """`detail` string, ou dict {mensagem, ...extra} quando a resposta leva dados
    além da frase (o 409 da gravação diz o que já existe)."""
    if e.extra:
        return {"mensagem": e.detail, **e.extra}
    return e.detail


@router.post("/utilitarios/arquivo/gravar")
async def utilitarios_gravar_arquivo(body: dict = Body(...),
                                     user: dict = Depends(require_tela_utilitarios)):
    """Cria ou sobrescreve um arquivo de texto abaixo de uma raiz. Exige a tela
    E `acao_editar` (operador só lê). Extensão da lista do admin; conteúdo em
    UTF-8 ou Latin-1 com CRLF→LF e `\\n` final; 409 sem `sobrescrever`; cópia
    de segurança e escrita atômica ficam no serviço."""
    t0 = time.time()
    usuario = str(user.get("matricula") or "?")
    servidor = str(body.get("servidor") or "datastage")
    diretorio, nome, extensao = body.get("diretorio"), body.get("nome"), body.get("extensao")
    pedido_bruto = f"{str(diretorio or '').rstrip('/')}/{str(nome or '')}.{str(extensao or '')}"

    def negar(status: int, detalhe: str, resultado: str = "erro", caminho: str = pedido_bruto,
              detail=None):
        _auditar(usuario=usuario, servidor=servidor, acao="gravar", caminho=caminho,
                 resultado=resultado, detalhe=detalhe, duracao_ms=_ms(t0))
        raise HTTPException(status_code=status, detail=detail if detail is not None else detalhe)

    if PERM_EDITAR not in user.get("permissoes", []):
        negar(403, "Gravar exige a permissão de cadastrar/editar (acao_editar).", "negado")

    # Validação do pedido (auditada, como na leitura).
    try:
        servidor = svc.servidor_valido(body.get("servidor"))
        cod = svc.codificacao_valida(body.get("codificacao")) or "utf-8"
    except svc.ArquivoError as e:
        negar(e.status, e.interno or e.detail, e.resultado, detail=e.detail)
    conteudo = body.get("conteudo")
    if not isinstance(conteudo, str):
        negar(422, "'conteudo' precisa ser texto.")
    if not all(isinstance(v, str) for v in (diretorio, nome, extensao)):
        negar(422, "'diretorio', 'nome' e 'extensao' precisam ser texto.")
    sobrescrever = body.get("sobrescrever", False)
    if not isinstance(sobrescrever, bool):
        negar(422, "'sobrescrever' precisa ser true ou false.")

    cfg = _config_do_banco()
    raizes = [r["caminho"] for r in cfg["raizes"] if r["servidor"] == servidor]
    if not raizes:
        negar(403, "Nenhum diretório liberado para este servidor — cadastre uma raiz em "
                   "Admin › Utilitários.", "negado")
    try:
        caminho, _raiz = svc.preparar_gravacao(diretorio, nome, extensao, raizes, cfg["extensoes"])
    except svc.ArquivoError as e:
        negar(e.status, e.interno or e.detail, e.resultado, detail=e.detail)

    texto = svc.normalizar_conteudo(conteudo)
    if "\0" in texto:
        negar(415, "O conteúdo tem bytes nulos — os Utilitários só gravam texto.", caminho=caminho)
    try:
        dados = svc.codificar_conteudo(texto, cod)
    except svc.ArquivoError as e:
        negar(e.status, e.detail, caminho=caminho)
    teto_bytes = cfg["tamanho_max_kb"] * 1024
    if len(dados) > teto_bytes:
        negar(413, f"Conteúdo de {svc.formatar_tamanho(len(dados))}, acima do teto de "
                   f"{svc.formatar_tamanho(teto_bytes)}.", caminho=caminho)

    # Única por pedido: pid + milissegundo não separa duas threads do mesmo
    # worker no mesmo instante, e o `.tmp` dos dois seria o mesmo arquivo.
    marca = f"{os.getpid()}-{uuid.uuid4().hex[:8]}"
    try:
        resultado = await _no_servidor(
            _gravar_sync, servidor, caminho, raizes, dados, sobrescrever,
            cfg["backup_ao_sobrescrever"], marca)
    except svc.ArquivoError as e:
        negar(e.status, e.interno or e.detail, e.resultado, caminho=caminho, detail=_detalhe_http(e))
    except Exception as e:
        log.exception("Utilitários: falha inesperada ao gravar %s", caminho)
        negar(502, f"inesperado: {e!r}", caminho=caminho,
              detail="Falha ao gravar o arquivo — detalhe registrado no log da API.")

    resultado["codificacao"] = cod
    resultado["linhas"] = svc.contar_linhas(texto)
    resultado["duracao_ms"] = _ms(t0)
    partes = ["criado" if resultado["criado"] else "sobrescrito"]
    if resultado["backup"]:
        partes.append(f"backup {resultado['backup']}")
    _auditar(usuario=usuario, servidor=servidor, acao="gravar", caminho=resultado["caminho"],
             resultado="ok", tamanho=resultado["tamanho_bytes"], sha256=resultado["sha256"],
             detalhe="; ".join(partes), duracao_ms=resultado["duracao_ms"])
    return resultado


# ── admin: raízes ────────────────────────────────────────────────────────────

def _fmt_dt(v):
    if v is None:
        return None
    return v.strftime("%Y-%m-%d %H:%M:%S") if hasattr(v, "strftime") else str(v)


@router.get("/utilitarios/admin/raizes")
async def admin_raizes_listar(_admin: dict = Depends(get_admin_user)):
    conn = get_db_conn()
    cur = conn.cursor()
    try:
        _exigir_tabelas(cur)
        cur.execute(
            "SELECT id, servidor, caminho, ativo, criado_por, criado_em "
            "FROM dbo.etl_utilitario_raiz ORDER BY servidor, ativo DESC, caminho")
        return [
            {"id": r[0], "servidor": r[1], "caminho": r[2], "ativo": bool(r[3]),
             "criado_por": r[4], "criado_em": _fmt_dt(r[5])}
            for r in cur.fetchall()
        ]
    finally:
        _fechar(conn, cur)


@router.post("/utilitarios/admin/raizes")
async def admin_raizes_incluir(body: dict = Body(...), admin: dict = Depends(get_admin_user)):
    try:
        servidor = svc.servidor_valido(body.get("servidor"))
        caminho = svc.normalizar_raiz(body.get("caminho"))
    except svc.ArquivoError as e:
        raise HTTPException(status_code=e.status, detail=e.detail)
    conn = get_db_conn()
    cur = conn.cursor()
    try:
        _exigir_tabelas(cur)
        cur.execute(
            "SELECT id, ativo FROM dbo.etl_utilitario_raiz WHERE servidor = ? AND caminho = ?",
            [servidor, caminho])
        row = cur.fetchone()
        if row:
            estado = "ativa" if row[1] else "inativa"
            raise HTTPException(
                status_code=409,
                detail=f"Raiz já cadastrada para este servidor (id {row[0]}, {estado}).")
        cur.execute(
            "INSERT INTO dbo.etl_utilitario_raiz (servidor, caminho, ativo, criado_por) "
            "OUTPUT INSERTED.id VALUES (?, ?, 1, ?)",
            [servidor, caminho, str(admin.get("matricula") or "?")])
        novo = cur.fetchone()
        conn.commit()
        return {"id": int(novo[0]) if novo else None, "servidor": servidor, "caminho": caminho}
    finally:
        _fechar(conn, cur)


@router.patch("/utilitarios/admin/raizes/{raiz_id}")
async def admin_raizes_alterar(raiz_id: int = Path(..., ge=1, le=_ID_MAX),
                               body: dict = Body(...),
                               admin: dict = Depends(get_admin_user)):
    """Altera `ativo` e/ou `caminho` de uma raiz. Editar o caminho existe para o
    erro de digitação (`/opt/totalseg-pw`) não obrigar a desativar e recadastrar;
    o caminho novo passa pela mesma régua do cadastro e não pode repetir outra
    raiz do mesmo servidor."""
    ativo = body.get("ativo")
    caminho_bruto = body.get("caminho")
    if ativo is None and caminho_bruto is None:
        raise HTTPException(status_code=422, detail="Informe 'ativo' e/ou 'caminho'.")
    if ativo is not None and not isinstance(ativo, bool):
        raise HTTPException(status_code=422, detail="'ativo' precisa ser true ou false.")
    caminho: str | None = None
    if caminho_bruto is not None:
        if not isinstance(caminho_bruto, str):
            raise HTTPException(status_code=422, detail="'caminho' precisa ser texto.")
        try:
            caminho = svc.normalizar_raiz(caminho_bruto)
        except svc.ArquivoError as e:
            raise HTTPException(status_code=e.status, detail=e.detail)

    conn = get_db_conn()
    cur = conn.cursor()
    try:
        _exigir_tabelas(cur)
        cur.execute("SELECT servidor, caminho, ativo FROM dbo.etl_utilitario_raiz WHERE id = ?", [raiz_id])
        atual = cur.fetchone()
        if not atual:
            raise HTTPException(status_code=404, detail="Raiz não encontrada.")
        servidor, caminho_atual, ativo_atual = str(atual[0]), str(atual[1]), bool(atual[2])
        if caminho is not None and caminho != caminho_atual:
            cur.execute(
                "SELECT id, ativo FROM dbo.etl_utilitario_raiz "
                "WHERE servidor = ? AND caminho = ? AND id <> ?", [servidor, caminho, raiz_id])
            outra = cur.fetchone()
            if outra:
                estado = "ativa" if outra[1] else "inativa"
                raise HTTPException(
                    status_code=409,
                    detail=f"Já existe outra raiz com esse caminho neste servidor (id {outra[0]}, {estado}).")
        novo_caminho = caminho if caminho is not None else caminho_atual
        novo_ativo = ativo if ativo is not None else ativo_atual
        cur.execute("UPDATE dbo.etl_utilitario_raiz SET caminho = ?, ativo = ? WHERE id = ?",
                    [novo_caminho, 1 if novo_ativo else 0, raiz_id])
        conn.commit()
    finally:
        _fechar(conn, cur)
    if novo_caminho != caminho_atual:
        # A troca apaga o caminho antigo da lista; as leituras já auditadas
        # abaixo dele precisam de uma linha que explique de onde vieram.
        quem = str(admin.get("matricula") or "?")
        log.info("Utilitários: raiz %s alterada de %s para %s por %s", raiz_id, caminho_atual, novo_caminho, quem)
        _auditar(usuario=quem, servidor=servidor, acao="raiz", caminho=novo_caminho, resultado="ok",
                 detalhe=f"raiz {raiz_id}: caminho alterado de {caminho_atual}")
    return {"ok": True, "id": raiz_id, "servidor": servidor, "caminho": novo_caminho, "ativo": novo_ativo}


def _testar_sync(servidor: str, caminho: str) -> dict:
    with svc.conexao_sftp(servidor) as sftp:
        return svc.testar_raiz(sftp, caminho)


@router.post("/utilitarios/admin/raizes/{raiz_id}/testar")
async def admin_raizes_testar(raiz_id: int = Path(..., ge=1, le=_ID_MAX),
                              admin: dict = Depends(get_admin_user)):
    t0 = time.time()
    conn = get_db_conn()
    cur = conn.cursor()
    try:
        _exigir_tabelas(cur)
        cur.execute("SELECT servidor, caminho FROM dbo.etl_utilitario_raiz WHERE id = ?", [raiz_id])
        row = cur.fetchone()
    finally:
        _fechar(conn, cur)
    if not row:
        raise HTTPException(status_code=404, detail="Raiz não encontrada.")
    servidor, caminho = str(row[0]), str(row[1])
    usuario = str(admin.get("matricula") or "?")
    try:
        resultado = await _no_servidor(_testar_sync, servidor, caminho)
    except svc.ArquivoError as e:
        _auditar(usuario=usuario, servidor=servidor, acao="testar", caminho=caminho,
                 resultado="erro", detalhe=e.interno or e.detail, duracao_ms=_ms(t0))
        raise HTTPException(status_code=e.status, detail=e.detail)
    _auditar(usuario=usuario, servidor=servidor, acao="testar", caminho=caminho,
             resultado="ok", detalhe=resultado.get("detalhe"), duracao_ms=_ms(t0))
    resultado["duracao_ms"] = _ms(t0)
    return resultado


# ── admin: extensões ─────────────────────────────────────────────────────────

def _extensao_valida(bruto) -> str:
    s = str(bruto or "").strip().lower().lstrip(".")
    if not svc.EXTENSAO_RE.match(s):
        raise HTTPException(status_code=422, detail=svc.MSG_EXTENSAO_INVALIDA)
    return s


@router.get("/utilitarios/admin/extensoes")
async def admin_extensoes_listar(_admin: dict = Depends(get_admin_user)):
    conn = get_db_conn()
    cur = conn.cursor()
    try:
        _exigir_tabelas(cur)
        cur.execute("SELECT extensao, criado_por, criado_em FROM dbo.etl_utilitario_extensao ORDER BY extensao")
        return [{"extensao": r[0], "criado_por": r[1], "criado_em": _fmt_dt(r[2])} for r in cur.fetchall()]
    finally:
        _fechar(conn, cur)


@router.post("/utilitarios/admin/extensoes")
async def admin_extensoes_incluir(body: dict = Body(...), admin: dict = Depends(get_admin_user)):
    ext = _extensao_valida(body.get("extensao"))
    conn = get_db_conn()
    cur = conn.cursor()
    try:
        _exigir_tabelas(cur)
        cur.execute("SELECT 1 FROM dbo.etl_utilitario_extensao WHERE extensao = ?", [ext])
        if cur.fetchone():
            raise HTTPException(status_code=409, detail=f"Extensão '{ext}' já cadastrada.")
        cur.execute("INSERT INTO dbo.etl_utilitario_extensao (extensao, criado_por) VALUES (?, ?)",
                    [ext, str(admin.get("matricula") or "?")])
        conn.commit()
        return {"ok": True, "extensao": ext}
    finally:
        _fechar(conn, cur)


@router.delete("/utilitarios/admin/extensoes/{extensao}")
async def admin_extensoes_excluir(extensao: str, _admin: dict = Depends(get_admin_user)):
    ext = _extensao_valida(extensao)
    conn = get_db_conn()
    cur = conn.cursor()
    try:
        _exigir_tabelas(cur)
        cur.execute("DELETE FROM dbo.etl_utilitario_extensao WHERE extensao = ?", [ext])
        if not cur.rowcount:
            raise HTTPException(status_code=404, detail=f"Extensão '{ext}' não está cadastrada.")
        conn.commit()
        return {"ok": True, "extensao": ext}
    finally:
        _fechar(conn, cur)


# ── admin: config ────────────────────────────────────────────────────────────

@router.put("/utilitarios/admin/config")
async def admin_config_gravar(body: dict = Body(...), admin: dict = Depends(get_admin_user)):
    teto = _inteiro(body.get("tamanho_max_kb"), "tamanho_max_kb", 1, svc.TETO_MAX_KB)
    backup = body.get("backup_ao_sobrescrever")
    if not isinstance(backup, bool):
        raise HTTPException(status_code=422, detail="'backup_ao_sobrescrever' precisa ser true ou false.")
    quem = str(admin.get("matricula") or "?")
    conn = get_db_conn()
    cur = conn.cursor()
    try:
        _exigir_tabelas(cur)
        for chave, valor in ((K_TETO, str(teto)), (K_BACKUP, "1" if backup else "0")):
            cur.execute(
                "MERGE dbo.etl_app_config AS t USING (SELECT ? AS k, ? AS v) AS s "
                "ON t.config_key = s.k "
                "WHEN MATCHED THEN UPDATE SET config_value = s.v, updated_by = ?, updated_at = GETDATE() "
                "WHEN NOT MATCHED THEN INSERT (config_key, config_value, updated_by, updated_at) "
                "VALUES (s.k, s.v, ?, GETDATE());",
                [chave, valor, quem, quem])
        conn.commit()
        return {"ok": True, "tamanho_max_kb": teto, "backup_ao_sobrescrever": backup}
    finally:
        _fechar(conn, cur)
