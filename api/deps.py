"""
api/deps.py — Dependências compartilhadas: autenticação, RBAC e helpers Airflow.

Importado pelos routers e pelo main.py. Não importa de api.main para evitar
importações circulares.
"""
from __future__ import annotations

import base64
import hashlib
import os
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import Depends, Header, HTTPException

from db import get_db_conn

# ── Configuração via env ───────────────────────────────────────────────────────
AIRFLOW_URL      = os.getenv("AIRFLOW_URL",      "http://airflow-webserver:8080")
AIRFLOW_USER     = os.getenv("AIRFLOW_USER",     "airflow")
AIRFLOW_PASSWORD = os.getenv("AIRFLOW_PASSWORD", "airflow")

SESSION_TTL_HOURS_DEFAULT = 12

# Permissões RBAC (espelha etl_perfil_permissao)
PERM_EDITAR   = "acao_editar"
PERM_EXECUTAR = "acao_executar"
PERM_ADMIN    = "acao_admin"

# Cache Basic-Auth: sha256(header) → (matricula, "", expira)
_auth_cache: dict[str, tuple[str, str, datetime]] = {}
_AUTH_TTL_MINUTES = 5


# ── Helpers de usuário ─────────────────────────────────────────────────────────

def carregar_usuario(cur, matricula: str) -> dict:
    """Lê usuário + perfil + permissões. Retorna defaults se não cadastrado."""
    cur.execute(
        "SELECT u.matricula, u.perfil_nome, u.primeiro_nome, u.ultimo_nome, u.email, u.ativo "
        "FROM dbo.etl_usuario u WHERE u.matricula = ?", [matricula])
    row = cur.fetchone()
    if row:
        if not row[5]:
            raise HTTPException(status_code=403, detail="Usuário desativado no ORQUESTRA")
        info = {"matricula": row[0], "perfil": row[1],
                "primeiro_nome": row[2], "ultimo_nome": row[3], "email": row[4]}
    else:
        info = {"matricula": matricula, "perfil": "consulta",
                "primeiro_nome": None, "ultimo_nome": None, "email": None}
    cur.execute(
        "SELECT recurso FROM dbo.etl_perfil_permissao WHERE perfil_nome = ?", [info["perfil"]])
    info["permissoes"] = sorted(r[0] for r in cur.fetchall())
    return info


def session_ttl_hours() -> int:
    try:
        conn = get_db_conn()
        cur  = conn.cursor()
        cur.execute("SELECT config_value FROM dbo.etl_app_config WHERE config_key='session_ttl_hours'")
        row = cur.fetchone()
        cur.close(); conn.close()
        if row and str(row[0]).strip().isdigit():
            return int(row[0])
    except Exception:
        pass
    return SESSION_TTL_HOURS_DEFAULT


# ── Helpers Airflow ────────────────────────────────────────────────────────────

async def airflow_check_credentials(authorization: str) -> None:
    """Valida um header Basic contra o Airflow. Levanta 401/403/502."""
    async with httpx.AsyncClient(base_url=AIRFLOW_URL, timeout=5) as client:
        r = await client.get("/api/v1/dags?limit=1", headers={"Authorization": authorization})
        if r.status_code == 401:
            raise HTTPException(status_code=401, detail="Credenciais inválidas")
        if r.status_code == 403:
            raise HTTPException(status_code=403, detail="Sem permissão no Airflow")
        if not r.is_success:
            raise HTTPException(status_code=502, detail="Erro ao validar credenciais com Airflow")


async def airflow_user_details(username: str, authorization: str) -> dict:
    """Busca dados do usuário no Airflow (nome, email, roles). Falha silenciosa → {}."""
    def _parse(d: dict) -> dict:
        return {
            "first_name": d.get("first_name"),
            "last_name":  d.get("last_name"),
            "email":      d.get("email"),
            "roles":      [r["name"] for r in (d.get("roles") or []) if r.get("name")],
        }
    try:
        async with httpx.AsyncClient(base_url=AIRFLOW_URL, timeout=5) as client:
            r = await client.get(f"/api/v1/users/{username}",
                                 headers={"Authorization": authorization})
            if r.is_success:
                return _parse(r.json())
            r = await client.get(f"/api/v1/users/{username}",
                                 auth=(AIRFLOW_USER, AIRFLOW_PASSWORD))
            if r.is_success:
                return _parse(r.json())
    except Exception:
        pass
    return {}


def resolve_perfil_by_roles(cur, roles: list[str]) -> str | None:
    """Perfil ORQUESTRA de maior prioridade para os roles do Airflow. None se nenhum mapeado."""
    if not roles:
        return None
    placeholders = ",".join(["?" for _ in roles])
    cur.execute(
        f"SELECT TOP 1 perfil_nome FROM dbo.etl_airflow_role_perfil "
        f"WHERE role_airflow IN ({placeholders}) AND ativo = 1 "
        f"ORDER BY ordem_prioridade ASC",
        roles,
    )
    row = cur.fetchone()
    return row[0] if row else None


# ── FastAPI Dependencies ───────────────────────────────────────────────────────

async def get_current_user(
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict:
    """Dependency: valida Bearer (sessão) ou Basic (compatibilidade).
    Retorna dict {matricula, perfil, permissoes, ...}."""
    if not authorization:
        raise HTTPException(status_code=401, detail="Autenticação necessária")

    if authorization.startswith("Bearer "):
        token_hash = hashlib.sha256(authorization[7:].encode()).hexdigest()
        try:
            conn = get_db_conn()
            cur  = conn.cursor()
            cur.execute(
                "SELECT matricula FROM dbo.etl_sessao "
                "WHERE token_hash = ? AND expira_em > GETDATE()", [token_hash])
            row = cur.fetchone()
            if not row:
                cur.close(); conn.close()
                raise HTTPException(status_code=401, detail="Sessão expirada ou inválida")
            info = carregar_usuario(cur, row[0])
            cur.close(); conn.close()
            return info
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Erro ao validar sessão: {e}")

    if authorization.startswith("Basic "):
        cache_key = hashlib.sha256(authorization.encode()).hexdigest()
        now = datetime.now(timezone.utc)
        cached = _auth_cache.get(cache_key)
        if cached and now < cached[2]:
            matricula = cached[0]
        else:
            await airflow_check_credentials(authorization)
            try:
                matricula = base64.b64decode(authorization[6:]).decode("utf-8") \
                    .split(":", 1)[0].strip().upper()
            except Exception:
                raise HTTPException(status_code=401, detail="Header de autenticação inválido")
            _auth_cache[cache_key] = (matricula, "", now + timedelta(minutes=_AUTH_TTL_MINUTES))
        try:
            conn = get_db_conn()
            cur  = conn.cursor()
            info = carregar_usuario(cur, matricula)
            cur.close(); conn.close()
            return info
        except HTTPException:
            raise
        except Exception:
            return {"matricula": matricula, "perfil": "consulta", "permissoes": [],
                    "primeiro_nome": None, "ultimo_nome": None, "email": None}

    raise HTTPException(status_code=401, detail="Esquema de autenticação não suportado")


def require_perm(recurso: str):
    """Factory de dependency: exige que o perfil do usuário tenha o recurso."""
    async def _dep(user: dict = Depends(get_current_user)) -> dict:
        if recurso not in user.get("permissoes", []):
            raise HTTPException(
                status_code=403,
                detail=f"Perfil '{user.get('perfil')}' não possui a permissão '{recurso}'")
        return user
    return _dep


async def get_admin_user(user: dict = Depends(get_current_user)) -> dict:
    """Dependency: requer permissão de admin."""
    if PERM_ADMIN not in user.get("permissoes", []):
        raise HTTPException(
            status_code=403,
            detail=f"Perfil '{user.get('perfil')}' não tem acesso administrativo")
    return user


async def require_ds_console(user: dict = Depends(get_current_user)) -> dict:
    """
    Dependency do Console DataStage: libera para admin (acao_admin) OU para quem
    tem o recurso 'tela_ds_console' (configurável por perfil em Admin > Usuários
    & Perfis). Assim o acesso deixa de ser só de administrador.
    """
    perms = user.get("permissoes", [])
    if PERM_ADMIN in perms or "tela_ds_console" in perms:
        return user
    raise HTTPException(
        status_code=403,
        detail="Sem acesso ao Console DataStage (recurso 'tela_ds_console').")
