"""api/routers/maestro.py — Maestro, o assistente de parâmetros DataStage
(spec docs/spec-maestro-parametros.md, F1).

  GET  /maestro/status      {enabled, sugestoes}  — a tela mostra/oculta o avatar
  POST /maestro/conversar   uma rodada: histórico + contexto do editor → resposta,
                            status e a proposta validada (com prévia)
  GET  /maestro/historico   últimas conversas do usuário

Tudo atrás de `tela_jobs` — a permissão de Etapas e Fluxos (nav.ts): o Maestro
não grava parâmetro nenhum, só orienta. Provedor de IA: services/caixa_ia
(config caixa_ia_* de Admin › Caixa Seguro IA); interruptor próprio
`maestro_enabled` (migration 110). Regras e validação: services/maestro.
"""
from __future__ import annotations

import logging
import re
import time
import uuid
from datetime import date

from fastapi import APIRouter, Body, Depends, HTTPException

from db import get_db_conn
from deps import get_admin_user, require_perm
from services import caixa_ia, maestro
from services import job_params as jp

log = logging.getLogger("orquestra-api")

router = APIRouter()

_require_jobs = require_perm("tela_jobs")
_CONVERSA_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,36}$")
_INDISPONIVEL = ("Maestro temporariamente indisponível — contate o administrador "
                 "(Admin › Caixa Seguro IA › Verificar mostra a causa)")


def _abrir():
    conn = get_db_conn()
    return conn, conn.cursor()


def _fechar(conn, cur, commit: bool = False) -> None:
    try:
        if commit:
            conn.commit()
    finally:
        for x in (cur, conn):
            try:
                x.close()
            except Exception:  # noqa: BLE001
                pass


def _estado(cur) -> tuple[bool, bool, dict]:
    """(interruptor, tem_chave, cfg). A tela só mostra o avatar com os dois:
    interruptor ligado sem provedor seria um 503 permanente — e as duas causas
    têm donos diferentes (Admin › Maestro × Admin › Caixa Seguro IA), por isso
    o conversar as distingue em vez de dizer só 'desligado'."""
    cfg = caixa_ia.load_config(cur)
    return maestro.enabled(cur), bool(cfg.get("api_key_enc")), cfg


@router.get("/maestro/status", tags=["maestro"])
def maestro_status(_user: dict = Depends(_require_jobs)):
    """Flag para a tela (não expõe a config) + frases de abertura do catálogo.
    Degrada para enabled=False sem a 110 (o avatar some; nada quebra)."""
    conn, cur = _abrir()
    try:
        interruptor, tem_chave, _cfg = _estado(cur)
        if not (interruptor and tem_chave):
            return {"enabled": False, "sugestoes": []}
        try:
            catalogo = maestro.carregar_catalogo(cur)
        except maestro.MaestroIndisponivel:
            return {"enabled": False, "sugestoes": []}
        return {"enabled": True, "sugestoes": maestro.sugestoes(catalogo)}
    finally:
        _fechar(conn, cur)


def _validar_corpo(body: dict) -> tuple[str, list[dict], dict, date]:
    """(conversa_id, mensagens, contexto, referencia) ou 422 estruturado."""
    erros: list[str] = []
    conversa_id = str(body.get("conversa_id") or "").strip()
    if not conversa_id:
        conversa_id = str(uuid.uuid4())
    elif not _CONVERSA_ID_RE.match(conversa_id):
        erros.append("conversa_id inválido (8 a 36 caracteres: letras, números, - e _)")

    mensagens = body.get("mensagens")
    if not isinstance(mensagens, list) or not mensagens:
        erros.append("mensagens é obrigatório (lista de {role, content})")
        mensagens = []
    limpas: list[dict] = []
    for m in mensagens[-maestro.MAX_HISTORICO:]:
        if not isinstance(m, dict):
            erros.append("cada mensagem deve ser um objeto {role, content}")
            continue
        conteudo = m.get("content")
        if not isinstance(conteudo, str):
            erros.append("content deve ser texto")
            continue
        papel = str(m.get("role") or "").strip().lower()
        if papel == "user":
            if len(conteudo) > maestro.MAX_MENSAGEM:
                erros.append(f"mensagem excede {maestro.MAX_MENSAGEM} caracteres")
                continue
        else:
            # Resposta anterior do Maestro: truncar, nunca recusar (uma resposta
            # longa mataria a conversa inteira — ver MAX_MENSAGEM_HISTORICO).
            conteudo = conteudo[:maestro.MAX_MENSAGEM_HISTORICO]
        limpas.append({"role": m.get("role"), "content": conteudo})
    if limpas and (str(limpas[-1].get("role") or "").lower() != "user"
                   or not str(limpas[-1].get("content") or "").strip()):
        erros.append("a última mensagem deve ser do usuário (role=user) e não pode ser vazia")

    contexto = body.get("contexto")
    if contexto is None:
        contexto = {}
    elif not isinstance(contexto, dict):
        erros.append("contexto deve ser um objeto")
        contexto = {}
    params = contexto.get("params")
    if params is not None and not isinstance(params, list):
        erros.append("contexto.params deve ser uma lista")
    referencia_raw = contexto.get("referencia")
    referencia = date.today()
    if referencia_raw not in (None, ""):
        parsed = jp.parse_data(referencia_raw)
        if parsed is None:
            erros.append("contexto.referencia inválida — use AAAA-MM-DD")
        else:
            referencia = parsed
    for chave in ("pipeline_name", "job_name"):
        v = contexto.get(chave)
        if v is not None and not isinstance(v, str):
            erros.append(f"contexto.{chave} deve ser texto")
    if erros:
        raise HTTPException(status_code=422, detail={"code": "maestro_corpo_invalido", "errors": erros})
    return conversa_id, limpas, contexto, referencia


@router.post("/maestro/conversar", tags=["maestro"])
async def maestro_conversar(body: dict = Body(default={}), user: dict = Depends(_require_jobs)):
    conversa_id, mensagens, contexto, referencia = _validar_corpo(body)
    pipeline = (contexto.get("pipeline_name") or "").strip()[:200] or None
    job = (contexto.get("job_name") or "").strip()[:200] or None
    editor = maestro.sanear_editor(contexto.get("params") or [])
    pergunta = mensagens[-1]["content"].strip()

    # 1) Tudo que é banco ANTES do provedor, numa conexão só e fechada antes
    #    de esperar a rede: o provedor pode levar dezenas de segundos.
    conn, cur = _abrir()
    try:
        interruptor, tem_chave, cfg = _estado(cur)
        if not interruptor:
            raise HTTPException(status_code=503,
                                detail="Maestro desligado (Admin › Acessos & Comunicação › Maestro)")
        if not tem_chave:
            raise HTTPException(status_code=503,
                                detail="Maestro ligado, mas sem provedor de IA configurado "
                                       "(Admin › Caixa Seguro IA: chave de API)")
        try:
            catalogo = maestro.carregar_catalogo(cur)
        except maestro.MaestroIndisponivel as e:
            raise HTTPException(status_code=503, detail=str(e))
        declarados = maestro.parametros_declarados(cur, pipeline, job)
        defaults = maestro.defaults_pipeline(cur, pipeline)
    finally:
        _fechar(conn, cur)

    ctx = {"pipeline_name": pipeline, "job_name": job, "declarados": declarados,
           "defaults": defaults, "editor": editor, "referencia": referencia.isoformat()}
    system = maestro.system_prompt(catalogo, ctx)
    codigos = {c["codigo"] for c in catalogo}

    # 2) O provedor.
    inicio = time.monotonic()
    try:
        texto, modelo = await caixa_ia.chat_conversa(cfg, system, mensagens)
    except HTTPException as e:
        duracao = int((time.monotonic() - inicio) * 1000)
        _registrar_silencioso(conversa_id=conversa_id, matricula=user["matricula"], pipeline=pipeline,
                              job=job, mensagem=pergunta, resposta=None, status=maestro.STATUS_ERRO,
                              cenario=None, params=None, motivo=str(e.detail)[:600],
                              modelo=cfg.get("model") or None, duracao_ms=duracao)
        if e.status_code == 500:
            # Configuração (ORQUESTRA_CONN_KEY, lib ausente) é assunto de admin;
            # o usuário do chat não vê internals (mesma regra do caixa_chat).
            log.error("maestro: falha interna do provedor/cripto: %s", e.detail)
            raise HTTPException(status_code=503, detail=_INDISPONIVEL)
        raise
    duracao = int((time.monotonic() - inicio) * 1000)

    # 3) A régua decide o status final — não o modelo.
    resposta, proposta = maestro.extrair_proposta(texto)
    resultado = maestro.avaliar(proposta, referencia, declarados, codigos)

    _registrar_silencioso(conversa_id=conversa_id, matricula=user["matricula"], pipeline=pipeline,
                          job=job, mensagem=pergunta, resposta=resposta, status=resultado["status"],
                          cenario=resultado["cenario"], params=resultado["params"],
                          motivo=resultado["motivo"], modelo=modelo, duracao_ms=duracao)

    return {
        "conversa_id": conversa_id,
        "resposta": resposta,
        "status": resultado["status"],
        "cenario": resultado["cenario"],
        "motivo": resultado["motivo"],
        "proposta": {"params": resultado["params"]} if resultado["params"] else None,
        "previa": resultado["previa"],
        "avisos": resultado["avisos"],
        "orientacao": maestro.ORIENTACAO_ADMIN if resultado["status"] == maestro.STATUS_NAO_ATENDIDO else None,
        "referencia": referencia.isoformat(),
    }


def _registrar_silencioso(**campos) -> None:
    """Best-effort: falha no registro nunca derruba a resposta ao usuário
    (mesma regra do log do Caixa) — mas vai para o log da API."""
    try:
        conn, cur = _abrir()
        try:
            maestro.registrar(cur, **campos)
            _fechar(conn, cur, commit=True)
        except Exception:
            _fechar(conn, cur)
            raise
    except Exception as e:  # noqa: BLE001
        log.warning("maestro: falha ao registrar a rodada (%s)", e)


@router.get("/maestro/historico", tags=["maestro"])
def maestro_historico(user: dict = Depends(_require_jobs)):
    conn, cur = _abrir()
    try:
        try:
            return {"conversas": maestro.historico(cur, user["matricula"])}
        except maestro.MaestroIndisponivel as e:
            raise HTTPException(status_code=503, detail=str(e))
    finally:
        _fechar(conn, cur)


# ═══════════ Admin (F3): interruptor, catálogo e pedidos ═════════════════════
# Tudo atrás de get_admin_user (acao_admin). Fica neste router, e não no
# admin.py de 1.300 linhas, pelo mesmo motivo dos utilitários: o domínio é um.

def _503(e: maestro.MaestroIndisponivel) -> HTTPException:
    return HTTPException(status_code=503, detail=str(e))


@router.get("/maestro/admin/config", tags=["maestro-admin"])
def maestro_admin_config(_user: dict = Depends(get_admin_user)):
    """O que a aba mostra ao abrir: interruptor, provedor (sem a chave) e contagens."""
    conn, cur = _abrir()
    try:
        interruptor, tem_chave, cfg = _estado(cur)
        try:
            numeros = maestro.contagens(cur)
        except maestro.MaestroIndisponivel as e:
            raise _503(e)
        return {"enabled": interruptor, "ativo": interruptor and tem_chave,
                "provedor": {"provider": cfg.get("provider") or "anthropic",
                             "model": cfg.get("model") or caixa_ia.DEFAULT_MODEL.get(cfg.get("provider") or "anthropic", ""),
                             "api_key_set": tem_chave},
                "retencao_dias": maestro.RETENCAO_CONVERSAS_DIAS, **numeros}
    finally:
        _fechar(conn, cur)


@router.post("/maestro/admin/config", tags=["maestro-admin"])
def maestro_admin_config_set(body: dict = Body(default={}), user: dict = Depends(get_admin_user)):
    """Liga/desliga. Ligar exige o provedor com chave (Admin › Caixa Seguro IA):
    ligado sem provedor seria um avatar que nunca aparece e um 503 permanente."""
    ligado = bool(body.get("enabled"))
    conn, cur = _abrir()
    try:
        _interruptor, tem_chave, _cfg = _estado(cur)
        if ligado and not tem_chave:
            raise HTTPException(status_code=422, detail={
                "code": "provedor_sem_chave",
                "errors": ["Configure o provedor de IA com a chave de API em Admin › Caixa Seguro IA antes de ligar o Maestro"]})
        maestro.gravar_enabled(cur, ligado, user["matricula"])
        _fechar(conn, cur, commit=True)
        return {"enabled": ligado}
    except HTTPException:
        _fechar(conn, cur)
        raise
    except Exception:
        _fechar(conn, cur)
        raise


@router.get("/maestro/admin/cenarios", tags=["maestro-admin"])
def maestro_admin_cenarios(_user: dict = Depends(get_admin_user)):
    conn, cur = _abrir()
    try:
        try:
            return {"cenarios": maestro.listar_cenarios(cur)}
        except maestro.MaestroIndisponivel as e:
            raise _503(e)
    finally:
        _fechar(conn, cur)


@router.post("/maestro/admin/cenarios/validar", tags=["maestro-admin"])
def maestro_admin_cenario_validar(body: dict = Body(default={}), _user: dict = Depends(get_admin_user)):
    """O "Simular" do editor de cenário: a régua da RECEITA + a prévia numa
    referência, com os marcadores no nome — sem gravar nada e sem banco.
    Só a receita: o admin simula antes de ter código/título prontos."""
    referencia = jp.parse_data(body.get("referencia")) if body.get("referencia") else date.today()
    if referencia is None:
        raise HTTPException(status_code=422, detail={"code": "cenario_invalido",
                                                    "errors": ["referencia inválida — use AAAA-MM-DD"]})
    corpo = body.get("cenario") if isinstance(body.get("cenario"), dict) else body
    receita = corpo.get("receita") if isinstance(corpo.get("receita"), dict) else corpo
    previa, erros = maestro.previa_da_receita(receita, referencia)
    return {"erros": erros, "previa": previa, "referencia": referencia.isoformat()}


def _salvar_cenario(body: dict, user: dict, cenario_id: int | None):
    dados, erros = maestro.validar_cenario(body)
    if erros:
        raise HTTPException(status_code=422, detail={"code": "cenario_invalido", "errors": erros})
    conn, cur = _abrir()
    try:
        try:
            salvo = maestro.salvar_cenario(cur, dados, user["matricula"], cenario_id)
        except maestro.CodigoExistente:
            raise HTTPException(status_code=409, detail={
                "code": "codigo_existente", "mensagem": f"Já existe um cenário com o código '{dados['codigo']}'"})
        except maestro.MaestroIndisponivel as e:
            raise _503(e)
        if salvo is None:
            raise HTTPException(status_code=404, detail="Cenário não encontrado")
        _fechar(conn, cur, commit=True)
        return {"cenario": salvo}
    except HTTPException:
        _fechar(conn, cur)
        raise
    except Exception:
        _fechar(conn, cur)
        raise


@router.post("/maestro/admin/cenarios", tags=["maestro-admin"])
def maestro_admin_cenario_criar(body: dict = Body(default={}), user: dict = Depends(get_admin_user)):
    return _salvar_cenario(body, user, None)


@router.post("/maestro/admin/cenarios/{cenario_id}", tags=["maestro-admin"])
def maestro_admin_cenario_editar(cenario_id: int, body: dict = Body(default={}),
                                 user: dict = Depends(get_admin_user)):
    return _salvar_cenario(body, user, cenario_id)


@router.post("/maestro/admin/cenarios/{cenario_id}/excluir", tags=["maestro-admin"])
def maestro_admin_cenario_excluir(cenario_id: int, _user: dict = Depends(get_admin_user)):
    conn, cur = _abrir()
    try:
        try:
            ok = maestro.excluir_cenario(cur, cenario_id)
        except maestro.MaestroIndisponivel as e:
            raise _503(e)
        if not ok:
            raise HTTPException(status_code=404, detail="Cenário não encontrado")
        _fechar(conn, cur, commit=True)
        return {"excluido": cenario_id}
    except HTTPException:
        _fechar(conn, cur)
        raise
    except Exception:
        _fechar(conn, cur)
        raise


@router.get("/maestro/admin/pedidos", tags=["maestro-admin"])
def maestro_admin_pedidos(tratados: bool = False, _user: dict = Depends(get_admin_user)):
    conn, cur = _abrir()
    try:
        try:
            return {"pedidos": maestro.listar_pedidos(cur, tratados=tratados)}
        except maestro.MaestroIndisponivel as e:
            raise _503(e)
    finally:
        _fechar(conn, cur)


@router.post("/maestro/admin/pedidos/{pedido_id}/tratar", tags=["maestro-admin"])
def maestro_admin_pedido_tratar(pedido_id: int, body: dict = Body(default={}),
                                user: dict = Depends(get_admin_user)):
    """`{tratado: true|false}` — carimba ou reabre um pedido não atendido."""
    tratado = bool(body.get("tratado", True))
    conn, cur = _abrir()
    try:
        try:
            ok = maestro.marcar_pedido(cur, pedido_id, tratado, user["matricula"])
        except maestro.MaestroIndisponivel as e:
            raise _503(e)
        if not ok:
            raise HTTPException(status_code=404, detail="Pedido não encontrado (ou não é um cenário não atendido)")
        _fechar(conn, cur, commit=True)
        return {"id": pedido_id, "tratado": tratado}
    except HTTPException:
        _fechar(conn, cur)
        raise
    except Exception:
        _fechar(conn, cur)
        raise
