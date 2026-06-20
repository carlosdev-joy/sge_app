"""api/routers/auth.py — Autenticação, sessões e RBAC."""
from __future__ import annotations

import base64
import hashlib
import secrets

from fastapi import APIRouter, Body, Depends, Header, HTTPException

from db import get_db_conn
from deps import (
    AIRFLOW_URL, AIRFLOW_USER, AIRFLOW_PASSWORD,
    PERM_ADMIN, PERM_EDITAR, PERM_EXECUTAR,
    airflow_check_credentials, airflow_user_details,
    carregar_usuario, get_current_user, get_admin_user,
    require_perm, resolve_perfil_by_roles, session_ttl_hours,
)

import logging

log = logging.getLogger("orquestra-api")

router = APIRouter()


@router.post("/auth/login", tags=["auth"])
async def auth_login(body: dict = Body(default={})):
    """Login: valida credencial no Airflow, registra/atualiza o usuário em
    etl_usuario (dados do Airflow no 1º acesso) e emite token de sessão."""
    usuario = (body.get("usuario") or "").strip()
    senha   = body.get("senha") or ""
    if not usuario or not senha:
        raise HTTPException(status_code=422, detail="usuario e senha são obrigatórios")

    basic = "Basic " + base64.b64encode(f"{usuario}:{senha}".encode()).decode()
    await airflow_check_credentials(basic)

    matricula = usuario.upper()
    detalhes = await airflow_user_details(usuario, basic)

    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    ttl_h = session_ttl_hours()

    try:
        conn = get_db_conn(); cur = conn.cursor()
        # upsert usuário — preenche dados do Airflow no 1º login, atualiza nos demais
        cur.execute("SELECT matricula FROM dbo.etl_usuario WHERE matricula = ?", [matricula])
        if cur.fetchone():
            cur.execute(
                "UPDATE dbo.etl_usuario SET ultimo_login = GETDATE(), "
                "primeiro_nome = COALESCE(?, primeiro_nome), "
                "ultimo_nome   = COALESCE(?, ultimo_nome), "
                "email         = COALESCE(?, email) "
                "WHERE matricula = ?",
                [detalhes.get("first_name"), detalhes.get("last_name"),
                 detalhes.get("email"), matricula])
        else:
            # 1º login: resolve perfil pelo role Airflow; fallback = 'consulta'
            perfil_inicial = (
                resolve_perfil_by_roles(cur, detalhes.get("roles") or [])
                or "consulta"
            )
            cur.execute(
                "INSERT INTO dbo.etl_usuario "
                "(matricula, perfil_nome, primeiro_nome, ultimo_nome, email, "
                " primeiro_login, ultimo_login, criado_por) "
                "VALUES (?, ?, ?, ?, ?, GETDATE(), GETDATE(), 'auto-login')",
                [matricula, perfil_inicial, detalhes.get("first_name"),
                 detalhes.get("last_name"), detalhes.get("email")])
        # grava sessão e remove sessões expiradas do usuário
        cur.execute("DELETE FROM dbo.etl_sessao WHERE matricula = ? AND expira_em < GETDATE()",
                    [matricula])
        cur.execute(
            "INSERT INTO dbo.etl_sessao (token_hash, matricula, expira_em) "
            "VALUES (?, ?, DATEADD(HOUR, ?, GETDATE()))",
            [token_hash, matricula, ttl_h])
        conn.commit()
        usuario_info = carregar_usuario(cur, matricula)
        cur.close(); conn.close()
    except HTTPException:
        raise
    except Exception as e:
        log.exception("Erro no login")
        raise HTTPException(status_code=500, detail=f"Erro ao criar sessão: {e}")

    return {"token": token, "expira_em_horas": ttl_h, "usuario": usuario_info}


@router.post("/auth/logout", tags=["auth"])
async def auth_logout(
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    """Encerra a sessão (revoga o token)."""
    if authorization and authorization.startswith("Bearer "):
        token_hash = hashlib.sha256(authorization[7:].encode()).hexdigest()
        try:
            conn = get_db_conn(); cur = conn.cursor()
            cur.execute("DELETE FROM dbo.etl_sessao WHERE token_hash = ?", [token_hash])
            conn.commit(); cur.close(); conn.close()
        except Exception:
            pass
    return {"sucesso": True}


@router.get("/me", tags=["auth"])
async def get_me(user: dict = Depends(get_current_user)):
    """Dados do usuário autenticado (matricula, nome, perfil, permissões)."""
    return user


# REMOVIDO (segurança C5): /auth/airflow-header entregava o Basic da service
# account ao navegador de qualquer usuário logado → bypass do RBAC. O front não
# usa (fala com o Airflow só pelo proxy server-side da API). Nunca reexpor a
# credencial de serviço ao cliente.
