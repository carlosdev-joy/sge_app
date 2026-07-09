"""api/routers/caixa_chat.py — assistentes IA do Caixa Seguro (Diego/Lari/Léo).

Substitui as edge functions Supabase da POC Lovable (diego-chat/lari-chat/
leo-chat → gateway Lovable). System prompts portados de supabase/functions/*.

  POST /caixa/chat/{assistente}            — envia mensagem, retorna {response}
  GET  /caixa/chat/status                  — {enabled} p/ o front exibir/ocultar
  GET  /caixa/chat/{assistente}/historico  — últimas conversas do usuário

Tudo atrás de tela_caixa_seguro (RBAC F1). Config e provedor em
services/caixa_ia.py; log em dbo.etl_caixa_chat_log (migration 061).
"""
from __future__ import annotations

import json
import logging
import time

from fastapi import APIRouter, Body, Depends, HTTPException

from db import get_db_conn
from deps import require_perm
from services import caixa_ia

log = logging.getLogger("orquestra-api")

router = APIRouter()

ASSISTENTES = ("diego", "lari", "leo")

_require_caixa = require_perm("tela_caixa_seguro")

# Limites defensivos (o front manda mensagens curtas + contexto pequeno)
_MAX_MENSAGEM = 4000
_MAX_CONTEXTO = 8000


def _system_prompt(assistente: str, context: dict | None) -> str:
    ctx = (json.dumps(context, ensure_ascii=False, indent=2)
           if context else "Nenhum contexto fornecido")

    if assistente == "diego":
        product = "Seguro de Vida" if (context or {}).get("productType") == "vida" \
            else "Prestamista"
        return f"""Você é o Diego, um assistente virtual especializado em análise de dados de {product}.
Você ajuda os usuários a entender dados de propostas, emissões, declínios e gerar análises personalizadas.

Contexto da página atual:
{ctx}

Suas capacidades:
- Responder perguntas sobre status de propostas
- Explicar motivos de declínio e pendências
- Fornecer insights sobre dados de vendas e emissões
- Analisar comparativos entre produtos
- Sugerir análises relevantes
- Ser amigável e profissional

Quando o usuário pedir para gerar gráficos ou relatórios, explique os dados disponíveis e como podem ser visualizados."""

    if assistente == "lari":
        return f"""Você é Lari, uma assistente virtual especializada em Seguro Prestamista.
Você ajuda a equipe comercial com análises, insights e recomendações sobre produtos de Prestamista.

Contexto da página atual:
{ctx}

Seja profissional, prestativa e forneça informações precisas e acionáveis sobre Prestamista.
Quando apropriado, mencione benefícios específicos do produto e estratégias de venda."""

    return f"""Você é o Léo, um assistente virtual especializado em análise de dados de Previdência.
Você ajuda os usuários a entender dados de propostas, pendências documentais e gerar gráficos personalizados.

Contexto da página atual:
{ctx}

Suas capacidades:
- Responder perguntas sobre status de propostas
- Explicar pendências documentais e seus tipos
- Fornecer insights sobre dados de captação
- Sugerir análises relevantes
- Ser amigável e profissional

Quando o usuário pedir para gerar gráficos ou relatórios, explique os dados disponíveis e como podem ser visualizados."""


def _log_conversa(assistente: str, matricula: str, mensagem: str,
                  resposta: str | None, contexto: dict | None, modelo: str | None,
                  duracao_ms: int, status: str, erro: str | None) -> None:
    """Best-effort: falha no log nunca derruba a resposta ao usuário."""
    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute(
            "INSERT INTO dbo.etl_caixa_chat_log "
            "(assistente, matricula, mensagem, resposta, contexto, modelo, "
            " duracao_ms, status, erro) VALUES (?,?,?,?,?,?,?,?,?)",
            [assistente, matricula, mensagem, resposta,
             json.dumps(contexto, ensure_ascii=False) if contexto else None,
             modelo, duracao_ms, status, (erro or None) and str(erro)[:1000]])
        conn.commit(); cur.close(); conn.close()
    except Exception as e:
        log.warning("caixa_chat: falha ao registrar conversa (%s)", e)


@router.get("/caixa/chat/status", tags=["caixa-seguro"])
async def chat_status(_user: dict = Depends(_require_caixa)):
    """Flag p/ o front exibir/ocultar os assistentes (não expõe a config)."""
    cfg = caixa_ia.load_config()
    return {"enabled": bool(cfg["enabled"])}


@router.get("/caixa/chat/{assistente}/historico", tags=["caixa-seguro"])
async def chat_historico(assistente: str, user: dict = Depends(_require_caixa)):
    """Últimas 50 conversas do usuário com o assistente (mesma shape que o
    front da POC consumia do Supabase: id, message, response, context, created_at)."""
    if assistente not in ASSISTENTES:
        raise HTTPException(status_code=404, detail="Assistente desconhecido")
    dados: list[dict] = []
    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute(
            "SELECT TOP 50 id, mensagem, resposta, contexto, "
            "       CONVERT(VARCHAR(33), criado_em, 126) "
            "FROM dbo.etl_caixa_chat_log "
            "WHERE assistente = ? AND matricula = ? AND status = 'ok' "
            "ORDER BY criado_em DESC",
            [assistente, user["matricula"]])
        for r in cur.fetchall():
            ctx = None
            if r[3]:
                try:
                    ctx = json.loads(r[3])
                except Exception:
                    ctx = None
            dados.append({"id": r[0], "message": r[1], "response": r[2],
                          "context": ctx, "created_at": r[4]})
        cur.close(); conn.close()
    except Exception as e:
        log.warning("caixa_chat: histórico indisponível (%s)", e)  # pré-061
    return {"conversas": dados}


@router.post("/caixa/chat/{assistente}", tags=["caixa-seguro"])
async def chat_enviar(assistente: str, body: dict = Body(default={}),
                      user: dict = Depends(_require_caixa)):
    if assistente not in ASSISTENTES:
        raise HTTPException(status_code=404, detail="Assistente desconhecido")

    message = body.get("message")
    if not isinstance(message, str) or not message.strip():
        raise HTTPException(status_code=422, detail="message é obrigatório")
    message = message.strip()
    if len(message) > _MAX_MENSAGEM:
        raise HTTPException(status_code=422,
                            detail=f"message excede {_MAX_MENSAGEM} caracteres")
    context = body.get("context")
    if context is not None and not isinstance(context, dict):
        raise HTTPException(status_code=422, detail="context deve ser um objeto")
    if context and len(json.dumps(context, ensure_ascii=False)) > _MAX_CONTEXTO:
        context = {"aviso": "contexto truncado (excedeu o limite)"}

    cfg = caixa_ia.load_config()
    if not cfg["enabled"]:
        raise HTTPException(status_code=503,
                            detail="Assistentes IA desativados (Admin > Caixa Seguro IA)")

    system_prompt = _system_prompt(assistente, context)
    inicio = time.monotonic()
    try:
        resposta, modelo = await caixa_ia.chat(cfg, system_prompt, message)
    except HTTPException as e:
        _log_conversa(assistente, user["matricula"], message, None, context,
                      cfg.get("model") or None,
                      int((time.monotonic() - inicio) * 1000), "erro", e.detail)
        if e.status_code == 500:
            # 500 aqui é problema de configuração (ORQUESTRA_CONN_KEY, lib
            # ausente) — assunto de admin; o usuário do chat não vê internals.
            # O admin vê o detalhe real via caixa_ia_test.
            log.error("caixa_chat: falha interna do provedor/cripto: %s", e.detail)
            raise HTTPException(status_code=503,
                                detail="Assistentes IA temporariamente indisponíveis "
                                       "— contate o administrador")
        raise
    _log_conversa(assistente, user["matricula"], message, resposta, context,
                  modelo, int((time.monotonic() - inicio) * 1000), "ok", None)
    return {"response": resposta}
