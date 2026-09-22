"""api/routers/agentes.py — tela Agentes: catálogo, status do gateway por
usuário e config do admin (F1 da spec docs/spec-agentes-datastage.md).

  GET  /agentes/catalogo        agentes que o usuário logado pode abrir
  GET  /agentes/status          estado da sonda de cadastro no gateway (cacheado)
  GET  /agentes/admin/config    config de Agentes (admin)
  POST /agentes/admin/config    grava config de Agentes (admin)

`tela_agentes` é checada por `require_perm` puro — como qualquer outra tela
(perfil ∪ overrides). O que É especial é o acesso a CADA AGENTE
(`agente_datastage`, `agente_curador`): ver `services/agentes.require_agente`,
usado pelos endpoints de conversa que chegam na F2 — este arquivo só
distribui o catálogo, ainda sem `/agentes/{id}/conversar`.
"""
from __future__ import annotations

import re

from fastapi import APIRouter, Body, Depends, HTTPException, Query

from db import get_db_conn
from deps import get_admin_user, require_perm
from services import agentes as svc
from services import ia_provedor

router = APIRouter()

_require_tela = require_perm("tela_agentes")

_RE_CAMPO = re.compile(r"^(header|body):.+$")


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


@router.get("/agentes/catalogo", tags=["agentes"])
async def agentes_catalogo(user: dict = Depends(_require_tela)):
    """Agentes que ESTE usuário pode abrir: no catálogo, elegível (perfil e
    grant em `permissoes_extra` — admin sempre passa) e com os dois
    interruptores ligados. Vazio não é erro: é 'nenhum agente liberado
    ainda', o estado normal antes de o admin conceder o primeiro."""
    conn, cur = _abrir()
    try:
        cfg = svc.carregar_config(cur)
    finally:
        _fechar(conn, cur)
    return {"agentes": svc.catalogo_do_usuario(user, cfg)}


@router.get("/agentes/status", tags=["agentes"])
async def agentes_status(agente: str | None = Query(default=None),
                         user: dict = Depends(_require_tela)):
    """Estado da sonda de cadastro no gateway PARA ESTE USUÁRIO (não expõe
    config). `agente` é aceito por simetria com o catálogo mas a sonda é
    sobre o CADASTRO da matrícula — agente-agnóstica; um id desconhecido dá
    404 antes de qualquer chamada de rede."""
    if agente is not None and svc.agente(agente) is None:
        raise HTTPException(status_code=404, detail={
            "code": "agente_desconhecido", "message": f"Agente '{agente}' não existe"})
    matricula = (user.get("matricula") or "").strip()
    cacheado = svc.sonda_cacheada(matricula) if matricula else None
    if cacheado is not None:
        return {"estado": cacheado, "cache": True}
    conn, cur = _abrir()
    try:
        cadastro = None
        if matricula:
            # A coluna só existe a partir da 117 (F1). Sem ela, "sem cadastro
            # próprio" é a leitura correta (cai no padrão cvp-<matrícula>) —
            # diferente da ESCRITA (user_identidade_set, admin.py), que 503
            # nomeado: aqui não há nada de errado em degradar em silêncio,
            # porque o resultado (usar o padrão) já é o comportamento normal
            # de quem nunca configurou um cadastro.
            try:
                cur.execute("SELECT identidade_gateway FROM dbo.etl_usuario WHERE matricula = ?", [matricula])
                row = cur.fetchone()
                cadastro = row[0] if row else None
            except Exception:
                cadastro = None
        provedor_cfg = ia_provedor.load_config(cur)
        agentes_cfg = svc.carregar_config(cur)
    finally:
        _fechar(conn, cur)
    identidade = svc.identidade_gateway(matricula, cadastro)
    campo = agentes_cfg.get("agentes_gateway_campo_usuario") or None
    estado = await ia_provedor.sondar_usuario(provedor_cfg, identidade, campo)
    if matricula:
        svc.guardar_sonda(matricula, estado)
    return {"estado": estado, "cache": False}


@router.get("/agentes/admin/config", tags=["agentes-admin"])
async def agentes_admin_config_get(_admin: dict = Depends(get_admin_user)):
    conn, cur = _abrir()
    try:
        cfg = svc.carregar_config(cur)
    finally:
        _fechar(conn, cur)
    return {"sucesso": True, "config": cfg}


@router.post("/agentes/admin/config", tags=["agentes-admin"])
async def agentes_admin_config_set(body: dict = Body(default={}),
                                   admin: dict = Depends(get_admin_user)):
    valores: dict[str, str] = {}
    erros: list[str] = []

    for chave in ("agentes_enabled", "agente_datastage_enabled"):
        if chave in body:
            valores[chave] = "1" if body.get(chave) else "0"

    if "agentes_gateway_campo_usuario" in body:
        v = str(body.get("agentes_gateway_campo_usuario") or "").strip()
        if v and not _RE_CAMPO.match(v):
            erros.append("agentes_gateway_campo_usuario deve ser 'header:NOME' ou 'body:CAMPO'")
        else:
            valores["agentes_gateway_campo_usuario"] = v

    if "agentes_cadastro_texto" in body:
        v = str(body.get("agentes_cadastro_texto") or "").strip()
        if len(v) > 500:
            erros.append("agentes_cadastro_texto excede 500 caracteres")
        else:
            valores["agentes_cadastro_texto"] = v or svc.CONFIG_DEFAULTS["agentes_cadastro_texto"]

    if "agentes_ssh_max" in body:
        try:
            n = int(body.get("agentes_ssh_max"))
            if not (1 <= n <= 50):
                raise ValueError
            valores["agentes_ssh_max"] = str(n)
        except (TypeError, ValueError):
            erros.append("agentes_ssh_max deve ser um número inteiro entre 1 e 50")

    if "agentes_fato_validade_dias" in body:
        try:
            n = int(body.get("agentes_fato_validade_dias"))
            if not (1 <= n <= 365):
                raise ValueError
            valores["agentes_fato_validade_dias"] = str(n)
        except (TypeError, ValueError):
            erros.append("agentes_fato_validade_dias deve ser um número inteiro entre 1 e 365")

    if erros:
        raise HTTPException(status_code=422, detail={"code": "agentes_config_invalida", "errors": erros})
    if not valores:
        raise HTTPException(status_code=422, detail={"code": "agentes_config_vazia",
                                                      "message": "nada para salvar"})

    conn, cur = _abrir()
    try:
        for k, v in valores.items():
            cur.execute(
                "MERGE dbo.etl_app_config AS t "
                "USING (SELECT ? AS k) AS s ON t.config_key = s.k "
                "WHEN MATCHED THEN UPDATE SET config_value=?, updated_by=?, updated_at=GETDATE() "
                "WHEN NOT MATCHED THEN INSERT (config_key, config_value, descricao, updated_by, updated_at) "
                "  VALUES (s.k, ?, 'Tela Agentes', ?, GETDATE());",
                [k, v, admin["matricula"], v, admin["matricula"]])
        _fechar(conn, cur, commit=True)
    except Exception:
        _fechar(conn, cur)
        raise
    return {"sucesso": True, "mensagem": "Configuração de Agentes salva."}
