"""api/routers/lineage_isx.py — lineage automático via ISX (spec docs/spec-lineage-isx.md, F2).

  GET  /lineage/isx/localizar?pipeline_name&job_name — acha o job na API REST do DataStage
  POST /lineage/isx/extrair {pipeline_name, job_name, force?}  [acao_editar] — export + parse + grava
  GET  /lineage/isx/job?pipeline_name&job_name       — o que está no banco (cabeçalho + stages)
  GET  /lineage/isx/pipeline?pipeline_name           — estado ISX de cada job do pipeline

Regra do usuário: só há lineage ISX para job mapeado num pipeline (`etl_pipeline_job`);
o projeto DataStage vem de `etl_pipeline.project_name`. O trabalho bloqueante (REST,
SSH, parse) roda num executor dedicado com teto — mesmo desenho de routers/utilitarios.py.
Shape de erro: `detail` em pt-BR; 422 regra/nome; 404 job não achado no DataStage;
502 istool/SSH/REST (detalhe só no log); 503 não configurado; 504 teto.
"""
from __future__ import annotations

import asyncio
import logging
import time
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, Body, Depends, HTTPException, Query

from deps import PERM_EDITAR, get_current_user, require_perm
from services import lineage_isx as svc

log = logging.getLogger("orquestra-api")

router = APIRouter()

# Executor só do ISX, POR PROCESSO do uvicorn: 2 extrações simultâneas por worker
# (produção roda `--workers 2` → 4 JVMs do istool no servidor do DataStage, o teto
# da spec §3); a próxima espera na fila. Não toca o pool do `asyncio.to_thread`.
_EXECUTOR_ISX = ThreadPoolExecutor(max_workers=2, thread_name_prefix="orq-lineage-isx")
_TETO_EXTRAIR_S = 60     # spec §3: istool leva 3–5 s; sequence tenta .qjb e .sjb
_TETO_LOCALIZAR_S = 35   # BFS do engine tem 30 s; aqui um pouco mais para o 504 vir do engine

svc.aviso_arranque()


def _tardio(fut) -> None:
    exc = fut.exception() if not fut.cancelled() else None
    if exc is None:
        log.warning("Lineage ISX: a operação que estourou o teto TERMINOU depois do 504.")
    else:
        log.warning("Lineage ISX: a operação que estourou o teto falhou depois do 504: %r", exc)


async def _no_executor(fn, *args, teto: float):
    """`fn` bloqueante no executor dedicado; passado o teto, 504. O que ainda está
    na FILA é cancelado (não vai gastar uma JVM do istool para um resultado que
    ninguém vai ler); a thread já em curso não tem como ser morta — termina pelo
    timeout do canal SSH e o desfecho fica no log (`shield` mantém o future vivo).
    Um sucesso tardio se perde de propósito: o cabeçalho fica `erro` até a próxima
    chamada, que reextrai."""
    loop = asyncio.get_running_loop()
    fut = loop.run_in_executor(_EXECUTOR_ISX, fn, *args)
    try:
        return await asyncio.wait_for(asyncio.shield(fut), timeout=teto)
    except asyncio.TimeoutError:
        fut.add_done_callback(_tardio)
        fut.cancel()  # só surte efeito no que ainda não começou
        raise HTTPException(status_code=504, detail=f"A extração não terminou em {teto:g} s — tente de novo.")


def _http(e) -> HTTPException:
    """ISXError → HTTPException; `interno` só no log."""
    if e.interno:
        log.warning("Lineage ISX: %s (%s) — %s", e.detail, e.status, e.interno)
    return HTTPException(status_code=e.status, detail=e.detail)


def _nomes(pipeline_bruto, job_bruto) -> tuple[str, str]:
    E = svc.engine()
    pipeline = str(pipeline_bruto or "").strip()
    if not pipeline or len(pipeline) > 200:
        raise HTTPException(status_code=422, detail="pipeline_name é obrigatório.")
    try:
        job = E.validar_nome(job_bruto, "job_name")
    except E.ISXError as e:
        raise _http(e)
    return pipeline, job


def _info_do_job(cur, pipeline: str, job: str) -> dict:
    """Projeto e tipo do job pelo pipeline. Devolve também `job_name` e
    `pipeline_name` na GRAFIA DO BANCO: a colação é case-insensitive, mas o
    DataStage distingue caixa — daqui em diante valem os nomes canônicos."""
    svc.exigir_tabela(cur)
    info = svc.job_do_pipeline(cur, pipeline, job)
    if info is None:
        raise HTTPException(
            status_code=422,
            detail=f"O job {job} não está mapeado no pipeline {pipeline} — o lineage ISX só existe "
                   "para jobs de um pipeline do Orquestra (cadastre o job no pipeline primeiro).")
    if not info["ds_project"]:
        raise HTTPException(
            status_code=422,
            detail=f"O pipeline {pipeline} não tem projeto DataStage (project_name) cadastrado.")
    return info


def _cfg():
    try:
        return svc.config()
    except Exception as e:  # noqa: BLE001 — ISXError do engine (503) ou HTTPException (500)
        if isinstance(e, HTTPException):
            raise
        raise _http(e)


@router.get("/lineage/isx/localizar", tags=["lineage"])
async def isx_localizar(pipeline_name: str = Query(...), job_name: str = Query(...),
                        _auth: dict = Depends(get_current_user)):
    """Acha o job na árvore de pastas do projeto pela API REST (com a pasta já
    conhecida, confere direto). Só leitura — nada é gravado."""
    pipeline, job = _nomes(pipeline_name, job_name)
    with svc.banco() as (_conn, cur):
        info = _info_do_job(cur, pipeline, job)
        pipeline, job = info["pipeline_name"], info["job_name"]
        cab = svc.cabecalho(cur, pipeline, job)
    cfg = _cfg()
    try:
        meta = await _no_executor(svc.localizar, cfg, info["ds_project"], job,
                                  (cab or {}).get("ds_folder_path"), teto=_TETO_LOCALIZAR_S)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        if hasattr(e, "status") and hasattr(e, "detail"):
            raise _http(e)
        log.exception("Lineage ISX: falha inesperada ao localizar %s/%s", pipeline, job)
        raise HTTPException(status_code=500, detail="Falha inesperada ao consultar a API REST do DataStage.")
    return {"encontrado": meta is not None, "pipeline_name": pipeline, "job_name": job,
            "ds_project": info["ds_project"], **(meta or {})}


@router.post("/lineage/isx/extrair", tags=["lineage"])
async def isx_extrair(body: dict = Body(default={}), user: dict = Depends(require_perm(PERM_EDITAR))):
    """Export pelo istool + parse + gravação, com cache pelo `lastModified` da API.
    `force` reextrai. O cabeçalho registra a tentativa mesmo quando falha."""
    pipeline, job = _nomes(body.get("pipeline_name"), body.get("job_name"))
    forcar = str(body.get("force", "false")).lower() in ("true", "1", "yes", "sim")
    usuario = str(user.get("matricula") or "?")
    t0 = time.time()
    with svc.banco() as (_conn, cur):
        info = _info_do_job(cur, pipeline, job)
        pipeline, job = info["pipeline_name"], info["job_name"]
        cab = svc.cabecalho(cur, pipeline, job)
        tem_linhas = svc.conta_linhas(cur, pipeline, job) > 0
        mapa = svc.mapa_tipos(cur)
    cfg = _cfg()
    projeto = info["ds_project"]

    meta = None
    try:
        meta, resultado, cache_hit = await _no_executor(
            svc.extrair, cfg, projeto, job, cab, tem_linhas, forcar, mapa, teto=_TETO_EXTRAIR_S)
    except HTTPException as e:
        if e.status_code == 504:
            _registrar_erro(pipeline, job, projeto, None, e.detail, usuario, t0)
        raise
    except Exception as e:  # noqa: BLE001
        if hasattr(e, "status") and hasattr(e, "detail"):
            # 503 (não configurado) não é tentativa contra o DataStage; o resto é.
            if e.status != 503:
                _registrar_erro(pipeline, job, projeto, getattr(e, "meta", None), e.detail, usuario, t0)
            raise _http(e)
        log.exception("Lineage ISX: falha inesperada ao extrair %s/%s", pipeline, job)
        _registrar_erro(pipeline, job, projeto, None, "Falha inesperada na extração — ver log da API.", usuario, t0)
        raise HTTPException(status_code=500, detail="Falha inesperada na extração — detalhe registrado no log da API.")

    with svc.banco() as (conn, cur):
        if not cache_hit:
            try:
                linhas = svc.gravar(conn, cur, pipeline=pipeline, job=job, projeto=projeto, meta=meta,
                                    resultado=resultado, usuario=usuario, duracao_ms=svc.ms(t0))
            except Exception as e:  # noqa: BLE001
                if hasattr(e, "status") and hasattr(e, "detail"):   # 409: outra extração do mesmo job
                    raise _http(e)
                log.exception("Lineage ISX: falha ao gravar %s/%s", pipeline, job)
                raise HTTPException(status_code=500, detail=f"Falha ao gravar o lineage: {type(e).__name__}.")
            log.info("Lineage ISX: %s/%s extraído por %s — %d stages em %d ms (%s)",
                     pipeline, job, usuario, linhas, svc.ms(t0), resultado.get("caminho_istool"))
        resposta = svc.montar(cur, pipeline, job)
    if resposta is None:
        raise HTTPException(status_code=500, detail="Extração gravada, mas o cabeçalho não foi encontrado.")
    resposta["cache_hit"] = cache_hit
    resposta["duracao_ms"] = svc.ms(t0)
    return resposta


def _registrar_erro(pipeline: str, job: str, projeto: str, meta, frase: str, usuario: str, t0: float) -> None:
    try:
        with svc.banco() as (conn, cur):
            svc.registrar_erro(conn, cur, pipeline=pipeline, job=job, projeto=projeto, meta=meta,
                               frase=frase, usuario=usuario, duracao_ms=svc.ms(t0))
    except Exception:  # noqa: BLE001 — best-effort
        log.warning("Lineage ISX: não registrou o erro de %s/%s", pipeline, job, exc_info=True)


@router.get("/lineage/isx/job", tags=["lineage"])
def isx_job(pipeline_name: str = Query(...), job_name: str = Query(...),
            _auth: dict = Depends(get_current_user)):
    """O lineage ISX gravado para o job (cabeçalho + stages). Só banco."""
    pipeline, job = _nomes(pipeline_name, job_name)
    with svc.banco() as (_conn, cur):
        svc.exigir_tabela(cur)
        resposta = svc.montar(cur, pipeline, job)
    if resposta is None:
        raise HTTPException(status_code=404, detail=f"O job {job} ainda não tem extração ISX no pipeline {pipeline}.")
    return resposta


@router.get("/lineage/isx/pipeline", tags=["lineage"])
def isx_pipeline(pipeline_name: str = Query(...), _auth: dict = Depends(get_current_user)):
    """Um item por job do pipeline com o estado da extração ISX. Só banco."""
    pipeline = str(pipeline_name or "").strip()
    if not pipeline:
        raise HTTPException(status_code=422, detail="pipeline_name é obrigatório.")
    with svc.banco() as (_conn, cur):
        svc.exigir_tabela(cur)
        resposta = svc.estado_pipeline(cur, pipeline)
    if resposta is None:
        raise HTTPException(status_code=404, detail=f"Pipeline {pipeline} não encontrado.")
    return resposta
