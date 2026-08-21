"""api/routers/admin.py — POST /admin, POST /admin/freeze, POST /admin/test-webhook."""
from __future__ import annotations

import asyncio
import datetime as _dt
import json
import logging
import os
import re
import time

import httpx
import pyodbc
from fastapi import APIRouter, Body, Depends, HTTPException

from db import get_db_conn
from deps import (
    PERM_ADMIN,
    AIRFLOW_URL, AIRFLOW_USER, AIRFLOW_PASSWORD,
    get_current_user, get_admin_user,
)
from routers.airflow import get_airflow_client
# Reuso do caminho de introspecção do módulo Cópia de Dados (conn_test de
# conexão ainda não migrada): resolução host/porta + allowlist, consulta
# direta com a credencial do app e fallback RPC pela DAG (BaseHook).
from routers.copias import _consulta_direta, _introspect_via_dag, _server_da_conexao
from services import servicenow
from services.conn_crypto import decrypt_password, encrypt_password

log = logging.getLogger("orquestra-api")

router = APIRouter()

FREEZE_MOTIVO = "Congelamento manual do ambiente"

# Fragmentos de nome de chave que marcam um valor como segredo em
# dbo.etl_app_config. No nível do módulo (e não dentro do handler) para poder
# ser testado: é a única barreira entre um segredo e a listagem de config.
_PADROES_SEGREDO = ("teams_webhook", "caixa_ia_api_key", "secret",
                    "password", "token", "senha")


def mask_secret(key: str, val):
    """Valor de config → mascarado quando a CHAVE indica segredo.

    `senha` está na lista por causa de servicenow_senha_enc, a credencial
    executora do sync: sem ela a chave não casaria com nenhum outro padrão e
    o token cifrado sairia inteiro no config_list.
    """
    k = (key or "").lower()
    if val and any(p in k for p in _PADROES_SEGREDO):
        return ("•••• " + str(val)[-4:]) if len(str(val)) > 4 else "••••"
    return val

# ── Conexões de Dados (Airflow Connections mssql) ────────────────────────────
# conn_id restrito (sem ponto — mais rígido que o de copias) e host sem
# ';'/'{'/'}' (anti-injeção em connection string ODBC). host\instância é aceito.
_CONN_ID_RE = re.compile(r"^[A-Za-z0-9_\-]{1,100}$")
_HOST_RE = re.compile(r"^[A-Za-z0-9_.\-\\]{1,200}$")


def _sem_senha(texto, *segredos) -> str:
    """Remove qualquer ocorrência dos segredos de um texto de erro/resposta."""
    out = str(texto or "")
    for s in segredos:
        if s:
            out = out.replace(str(s), "••••")
    return out


def _odbc_quote(v: str) -> str:
    """Valor entre chaves para connection string ODBC ('}' duplicado) — evita
    que senha/login/database com ';' injete pares na conn string."""
    return "{" + str(v).replace("}", "}}") + "}"


def _melhor_driver_odbc() -> str:
    """Melhor 'ODBC Driver N for SQL Server' instalado no container da API.
    Crédito: réplica mínima de dags/utils/bulk_copy._melhor_driver_odbc —
    ordem lexicográfica funciona para 'ODBC Driver 11/13/17/18'."""
    try:
        drivers = sorted(d for d in pyodbc.drivers() if "ODBC Driver" in d)
        if drivers:
            return drivers[-1]
    except Exception:
        pass
    return "ODBC Driver 18 for SQL Server"


def _porta_valida(port_raw) -> int:
    """Valida a porta (int 1..65535); ausente/vazia → 1433 (padrão MSSQL)."""
    if port_raw in (None, ""):
        return 1433
    try:
        port = int(str(port_raw).strip())
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="port deve ser um número inteiro")
    if not 1 <= port <= 65535:
        raise HTTPException(status_code=422, detail="port deve estar entre 1 e 65535")
    return port


def _extra_dict(extra) -> dict:
    """Extra JSON de uma connection do Airflow como dict (tolerante: extra
    vazio/inválido/não-objeto → {})."""
    try:
        if isinstance(extra, dict):
            return extra
        if isinstance(extra, str) and extra.strip():
            val = json.loads(extra)
            if isinstance(val, dict):
                return val
    except Exception:
        pass
    return {}


def _fmt_dt(v):
    if v is None:
        return None
    if hasattr(v, "strftime"):
        return v.strftime("%Y-%m-%d %H:%M:%S")
    return str(v)


def _get_app_config_value(key: str) -> str | None:
    """Lê um parâmetro único de dbo.etl_app_config. Retorna None se ausente/erro."""
    try:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute("SELECT config_value FROM dbo.etl_app_config WHERE config_key=?", (key,))
        row = cur.fetchone()
        cur.close(); conn.close()
        val = (row[0] or "").strip() if row else ""
        return val or None
    except Exception as e:
        log.warning("etl_app_config leitura de '%s' falhou: %s", key, e)
        return None


@router.post("/admin", tags=["admin"])
async def admin_manage(body: dict = Body(default={}), _admin: dict = Depends(get_admin_user)):
    """Operações administrativas restritas (etl_admin_manage).

    actions: config_upsert | config_delete | pipeline_delete |
             dag_file_delete | regenerate_all_dags
    """
    action       = (body.get("action") or "").strip()
    requested_by = _admin["matricula"]  # usa a matrícula autenticada como audit trail

    if not action:
        raise HTTPException(status_code=422, detail="action é obrigatório")

    try:
        conn = get_db_conn(); cur = conn.cursor()

        if action == "config_list":
            cur.execute("SELECT config_key, config_value FROM dbo.etl_app_config ORDER BY config_key")
            data = {k: mask_secret(k, v) for k, v in cur.fetchall()}
            cur.close(); conn.close()
            return {"sucesso": True, "config": data}

        elif action == "config_upsert":
            key   = (body.get("config_key")   or "").strip()
            value = (body.get("config_value") or "").strip()
            desc  = (body.get("descricao")    or "").strip() or None
            if not key or not value:
                raise HTTPException(status_code=422, detail="config_key e config_value obrigatórios")
            cur.execute(
                "MERGE dbo.etl_app_config AS t "
                "USING (SELECT ? AS k, ? AS v, ? AS d) AS s ON t.config_key = s.k "
                "WHEN MATCHED THEN UPDATE SET config_value=?, descricao=COALESCE(?,t.descricao), "
                "  updated_by=?, updated_at=GETDATE() "
                "WHEN NOT MATCHED THEN INSERT (config_key,config_value,descricao,updated_by,updated_at) "
                "  VALUES (s.k, s.v, s.d, ?, GETDATE());",
                [key, value, desc, value, desc, requested_by, requested_by],
            )
            conn.commit(); cur.close(); conn.close()
            return {"sucesso": True, "mensagem": f'Parâmetro "{key}" salvo.', "detalhes": {"key": key, "value": value}}

        elif action == "config_delete":
            key = (body.get("config_key") or "").strip()
            if not key:
                raise HTTPException(status_code=422, detail="config_key obrigatório")
            cur.execute("DELETE FROM dbo.etl_app_config WHERE config_key = ?", (key,))
            conn.commit(); cur.close(); conn.close()
            return {"sucesso": True, "mensagem": f'Parâmetro "{key}" removido.'}

        # ── Diagnóstico: bancos do mesmo servidor (mesma credencial do app) ──
        elif action == "server_databases":
            cur.execute("SELECT @@SERVERNAME")
            row = cur.fetchone()
            server_name = row[0] if row else None
            cur.execute(
                "SELECT d.name, d.state_desc, d.recovery_model_desc, "
                "       CONVERT(VARCHAR(19), d.create_date, 120), "
                "       (SELECT CAST(SUM(mf.size) * 8.0 / 1024 AS DECIMAL(18,1)) "
                "          FROM sys.master_files mf WHERE mf.database_id = d.database_id) "
                "FROM sys.databases d ORDER BY d.name")
            dbs = [{"name": r[0], "state": r[1], "recovery": r[2], "create_date": r[3],
                    "size_mb": (float(r[4]) if r[4] is not None else None)}
                   for r in cur.fetchall()]
            cur.close(); conn.close()
            return {"sucesso": True, "server": server_name, "databases": dbs, "total": len(dbs)}

        # ── Gestão de usuários e perfis (RBAC) ─────────────────────────────
        elif action == "user_list":
            cur.execute(
                "SELECT u.matricula, u.perfil_nome, u.primeiro_nome, u.ultimo_nome, "
                "       u.email, u.ativo, u.primeiro_login, u.ultimo_login "
                "FROM dbo.etl_usuario u ORDER BY u.matricula")
            data = [{"matricula": r[0], "perfil": r[1], "primeiro_nome": r[2],
                     "ultimo_nome": r[3], "email": r[4], "ativo": bool(r[5]),
                     "primeiro_login": _fmt_dt(r[6]), "ultimo_login": _fmt_dt(r[7])}
                    for r in cur.fetchall()]
            cur.close(); conn.close()
            return {"sucesso": True, "usuarios": data}

        elif action == "user_upsert":
            mat    = (body.get("matricula") or "").strip().upper()
            perfil = (body.get("perfil") or "consulta").strip()
            ativo  = 1 if body.get("ativo", True) else 0
            if not mat:
                raise HTTPException(status_code=422, detail="matricula obrigatória")
            cur.execute("SELECT 1 FROM dbo.etl_perfil WHERE perfil_nome = ?", [perfil])
            if not cur.fetchone():
                raise HTTPException(status_code=422, detail=f"Perfil '{perfil}' não existe")
            cur.execute("SELECT 1 FROM dbo.etl_usuario WHERE matricula = ?", [mat])
            if cur.fetchone():
                cur.execute(
                    "UPDATE dbo.etl_usuario SET perfil_nome = ?, ativo = ? WHERE matricula = ?",
                    [perfil, ativo, mat])
            else:
                cur.execute(
                    "INSERT INTO dbo.etl_usuario (matricula, perfil_nome, ativo, criado_por) "
                    "VALUES (?, ?, ?, ?)", [mat, perfil, ativo, requested_by])
            # perfil mudou → invalida sessões para forçar recarga de permissões
            cur.execute("DELETE FROM dbo.etl_sessao WHERE matricula = ? AND matricula <> ?",
                        [mat, requested_by])
            conn.commit(); cur.close(); conn.close()
            return {"sucesso": True, "mensagem": f"Usuário {mat} → perfil '{perfil}'."}

        elif action == "user_delete":
            mat = (body.get("matricula") or "").strip().upper()
            if not mat:
                raise HTTPException(status_code=422, detail="matricula obrigatória")
            if mat == requested_by:
                raise HTTPException(status_code=422, detail="Não é possível excluir o próprio usuário")
            cur.execute("DELETE FROM dbo.etl_sessao WHERE matricula = ?", [mat])
            cur.execute("DELETE FROM dbo.etl_usuario WHERE matricula = ?", [mat])
            n = cur.rowcount
            conn.commit(); cur.close(); conn.close()
            return {"sucesso": True, "mensagem": f"Usuário {mat} removido." if n else f"Usuário {mat} não encontrado."}

        # ── Assistentes IA do Caixa Seguro (config caixa_ia_* em etl_app_config) ──
        elif action == "caixa_ia_get":
            from services import caixa_ia
            cfg = caixa_ia.load_config(cur)
            cur.close(); conn.close()
            return {"sucesso": True, "config": {
                "enabled": cfg["enabled"], "provider": cfg["provider"],
                "model": cfg["model"], "base_url": cfg["base_url"],
                "api_key_set": bool(cfg["api_key_enc"]),
            }}

        elif action == "caixa_ia_set":
            from services import caixa_ia
            from services.conn_crypto import encrypt_password as _enc
            enabled  = "1" if body.get("enabled") else "0"
            provider = (body.get("provider") or "anthropic").strip()
            if provider not in caixa_ia.PROVIDERS:
                raise HTTPException(status_code=422,
                                    detail=f"provider deve ser um de {caixa_ia.PROVIDERS}")
            model    = (body.get("model") or "").strip()
            if len(model) > 100:
                raise HTTPException(status_code=422,
                                    detail="model excede 100 caracteres "
                                           "(limite da coluna modelo do log de conversas)")
            base_url = (body.get("base_url") or "").strip().rstrip("/")
            if base_url and not base_url.lower().startswith(("http://", "https://")):
                raise HTTPException(status_code=422, detail="base_url deve ser http(s)")
            api_key  = body.get("api_key")  # None = manter a atual; "" ignora
            if body.get("enabled") and provider == "openai_compat" and not base_url:
                raise HTTPException(status_code=422,
                                    detail="base_url é obrigatória no provedor OpenAI-compatível")

            valores = {caixa_ia.K_ENABLED: enabled, caixa_ia.K_PROVIDER: provider,
                       caixa_ia.K_MODEL: model, caixa_ia.K_BASE_URL: base_url}
            if isinstance(api_key, str) and api_key.strip():
                token = _enc(api_key.strip())
                if len(token) > 1000:  # etl_app_config.config_value é VARCHAR(1000)
                    raise HTTPException(status_code=422,
                                        detail="Chave de API longa demais — o valor "
                                               "cifrado excede os 1000 caracteres de "
                                               "etl_app_config.config_value")
                valores[caixa_ia.K_API_KEY] = token
            elif body.get("clear_api_key"):
                valores[caixa_ia.K_API_KEY] = ""
            for k, v in valores.items():
                cur.execute(
                    "MERGE dbo.etl_app_config AS t "
                    "USING (SELECT ? AS k) AS s ON t.config_key = s.k "
                    "WHEN MATCHED THEN UPDATE SET config_value=?, updated_by=?, updated_at=GETDATE() "
                    "WHEN NOT MATCHED THEN INSERT (config_key, config_value, descricao, updated_by, updated_at) "
                    "  VALUES (s.k, ?, 'Assistentes IA do Caixa Seguro', ?, GETDATE());",
                    [k, v, requested_by, v, requested_by])
            # exige chave configurada para ligar
            if enabled == "1":
                cfg = caixa_ia.load_config(cur)
                if not cfg["api_key_enc"]:
                    conn.rollback(); cur.close(); conn.close()
                    raise HTTPException(status_code=422,
                                        detail="Informe a chave de API antes de ativar os assistentes")
            conn.commit(); cur.close(); conn.close()
            return {"sucesso": True, "mensagem": "Configuração dos assistentes IA salva."}

        elif action == "caixa_ia_test":
            from services import caixa_ia
            cfg = caixa_ia.load_config(cur)
            cur.close(); conn.close()
            if not cfg["api_key_enc"]:
                raise HTTPException(status_code=422, detail="Configure a chave de API antes de testar")
            inicio = time.monotonic()
            resposta, modelo = await caixa_ia.chat(
                cfg,
                "Você é um verificador de conectividade. Responda APENAS a palavra OK.",
                "Teste de conexão do ORQUESTRA — responda OK.")
            ms = int((time.monotonic() - inicio) * 1000)
            return {"sucesso": True,
                    "mensagem": f"Provedor respondeu em {ms} ms (modelo {modelo}).",
                    "detalhes": {"resposta": resposta[:200], "duracao_ms": ms}}

        # ── ServiceNow: credencial executora do sync (config servicenow_*) ────
        # Mesmo tratamento das caixa_ia_*: senha cifrada com o Fernet das
        # conexões, nunca devolvida em claro, e a gravação não exige redigitar
        # a senha para mudar só a URL ou o grupo.
        elif action == "servicenow_get":
            cfg = servicenow.load_config(cur)
            # Lido ANTES do close — o cursor não sobrevive ao return.
            cur.execute("SELECT config_key, config_value FROM dbo.etl_app_config "
                        "WHERE config_key LIKE 'chamados_triagem%'")
            triagem_cfg = {k: (v or "").strip() for k, v in cur.fetchall()}
            cur.close(); conn.close()
            return {"sucesso": True, "config": {
                "url": cfg["url"], "usuario": cfg["usuario"],
                "grupos": cfg["grupos"], "habilitado": cfg["habilitado"],
                # Proxy volta em claro de propósito: não é segredo, e é a
                # primeira coisa a conferir quando o sync dá erro de rede.
                "proxy": cfg["proxy"],
                # A senha NUNCA volta, nem cifrada — a tela só precisa saber
                # se existe uma para decidir entre "Salvar" e "Trocar senha".
                "tem_senha": bool(cfg["senha_enc"]),
                "configurado": servicenow.configurado(cfg),
                # Triagem por IA (migration 093). Interruptor PRÓPRIO, e não
                # `caixa_ia_enabled`: aquele governa os assistentes do Caixa
                # Seguro, e amarrar os dois faria desligar o Diego desligar a
                # triagem de chamados, sem que ninguém tivesse pedido.
                "triagem_habilitada": triagem_cfg.get("chamados_triagem_habilitada") == "1",
                "triagem_lote": triagem_cfg.get("chamados_triagem_lote") or "20",
            }}

        elif action == "servicenow_set":
            url = servicenow.url_valida(body.get("url") or "")
            usuario = (body.get("usuario") or "").strip()
            grupos = (body.get("grupos") or "").strip()
            proxy = servicenow.proxy_valido(body.get("proxy") or "")
            habilitado = "1" if body.get("habilitado") else "0"
            senha = body.get("senha")   # None/"" = manter a atual
            if len(usuario) > 100:
                raise HTTPException(status_code=422,
                                    detail="usuário excede 100 caracteres")
            if len(grupos) > 900:
                raise HTTPException(status_code=422,
                                    detail="lista de grupos longa demais para "
                                           "etl_app_config.config_value")
            # Triagem por IA: só entra em `valores` quando o campo VEIO no
            # corpo. Gravar "0" por ausência desligaria a triagem em silêncio
            # a cada salvamento feito por um bundle antigo em cache ou por um
            # payload parcial — o mesmo cuidado que a senha já tem aqui.
            #
            # O teto de quantidade NÃO garante o tempo do ciclo (o gateway
            # pode estar lento); quem protege o dagrun_timeout é o orçamento
            # de ORCAMENTO_TRIAGEM_S dentro da própria task.
            triagem_valores = {}
            if "triagem_habilitada" in body:
                triagem_valores["chamados_triagem_habilitada"] = (
                    "1" if body.get("triagem_habilitada") else "0")
            if "triagem_lote" in body:
                try:
                    triagem_valores["chamados_triagem_lote"] = str(
                        max(1, min(int(body.get("triagem_lote") or 20), 200)))
                except (TypeError, ValueError):
                    raise HTTPException(status_code=422,
                                        detail="triagem_lote precisa ser um número")

            valores = {**triagem_valores,
                       servicenow.K_URL: url, servicenow.K_USUARIO: usuario,
                       servicenow.K_GRUPOS: grupos,
                       servicenow.K_PROXY: proxy,
                       servicenow.K_HABILITADO: habilitado}
            if isinstance(senha, str) and senha.strip():
                token = encrypt_password(senha.strip())
                if len(token) > 1000:   # config_value é VARCHAR(1000)
                    raise HTTPException(status_code=422,
                                        detail="Senha longa demais — o valor cifrado "
                                               "excede os 1000 caracteres de "
                                               "etl_app_config.config_value")
                valores[servicenow.K_SENHA] = token
            for k, v in valores.items():
                cur.execute(
                    "MERGE dbo.etl_app_config AS t "
                    "USING (SELECT ? AS k) AS s ON t.config_key = s.k "
                    "WHEN MATCHED THEN UPDATE SET config_value=?, updated_by=?, updated_at=GETDATE() "
                    "WHEN NOT MATCHED THEN INSERT (config_key, config_value, descricao, updated_by, updated_at) "
                    "  VALUES (s.k, ?, 'Integracao ServiceNow (chamados)', ?, GETDATE());",
                    [k, v, requested_by, v, requested_by])
            # Ligar sem credencial completa deixaria o sync agendado falhando
            # de hora em hora — a recusa aqui é mais barata que o log vermelho.
            if habilitado == "1":
                cfg = servicenow.load_config(cur)
                if not servicenow.configurado(cfg):
                    conn.rollback(); cur.close(); conn.close()
                    raise HTTPException(
                        status_code=422,
                        detail="Informe URL, usuário e senha antes de habilitar o sync")
            conn.commit(); cur.close(); conn.close()
            return {"sucesso": True, "mensagem": "Configuração do ServiceNow salva."}

        # ── Permissões extras por usuário (etl_usuario_permissao, migration 060) ──
        elif action == "user_perm_list":
            try:
                cur.execute(
                    "SELECT matricula, recurso FROM dbo.etl_usuario_permissao "
                    "ORDER BY matricula, recurso")
                rows = cur.fetchall()
            except Exception:
                rows = []  # tabela ainda não existe (pré-060)
            data: dict = {}
            for mat, rec in rows:
                data.setdefault(mat, []).append(rec)
            cur.close(); conn.close()
            return {"sucesso": True, "permissoes": data}

        elif action == "user_perm_set":
            mat = (body.get("matricula") or "").strip().upper()
            permissoes = body.get("permissoes")
            if not mat:
                raise HTTPException(status_code=422, detail="matricula obrigatória")
            if not isinstance(permissoes, list):
                raise HTTPException(status_code=422, detail="permissoes deve ser uma lista")
            cur.execute("SELECT 1 FROM dbo.etl_usuario WHERE matricula = ?", [mat])
            if not cur.fetchone():
                raise HTTPException(status_code=422,
                                    detail=f"Usuário {mat} não cadastrado (adicione-o antes)")
            cur.execute("DELETE FROM dbo.etl_usuario_permissao WHERE matricula = ?", [mat])
            recursos = sorted({str(r).strip() for r in permissoes if str(r).strip()})
            for rec in recursos:
                cur.execute(
                    "INSERT INTO dbo.etl_usuario_permissao (matricula, recurso, criado_por) "
                    "VALUES (?, ?, ?)", [mat, rec, requested_by])
            # permissões mudaram → invalida sessões para forçar recarga
            cur.execute("DELETE FROM dbo.etl_sessao WHERE matricula = ? AND matricula <> ?",
                        [mat, requested_by])
            conn.commit(); cur.close(); conn.close()
            return {"sucesso": True,
                    "mensagem": f"Permissões extras de {mat} atualizadas "
                                f"({len(recursos)} recurso(s))."}

        elif action == "perfil_list":
            cur.execute("SELECT perfil_nome, descricao FROM dbo.etl_perfil ORDER BY perfil_nome")
            perfis = [{"perfil_nome": r[0], "descricao": r[1]} for r in cur.fetchall()]
            cur.execute("SELECT perfil_nome, recurso FROM dbo.etl_perfil_permissao")
            perms: dict = {}
            for pn, rec in cur.fetchall():
                perms.setdefault(pn, []).append(rec)
            for p in perfis:
                p["permissoes"] = sorted(perms.get(p["perfil_nome"], []))
            cur.close(); conn.close()
            return {"sucesso": True, "perfis": perfis}

        elif action == "perfil_upsert":
            nome = (body.get("perfil_nome") or "").strip().lower()
            desc = (body.get("descricao") or "").strip() or None
            permissoes = body.get("permissoes")
            if not nome:
                raise HTTPException(status_code=422, detail="perfil_nome obrigatório")
            cur.execute("SELECT 1 FROM dbo.etl_perfil WHERE perfil_nome = ?", [nome])
            if cur.fetchone():
                if desc is not None:
                    cur.execute("UPDATE dbo.etl_perfil SET descricao = ? WHERE perfil_nome = ?",
                                [desc, nome])
            else:
                cur.execute("INSERT INTO dbo.etl_perfil (perfil_nome, descricao, criado_por) "
                            "VALUES (?, ?, ?)", [nome, desc, requested_by])
            if isinstance(permissoes, list):
                # trava de segurança: o perfil 'admin' nunca perde acao_admin
                if nome == "admin" and PERM_ADMIN not in permissoes:
                    permissoes = permissoes + [PERM_ADMIN]
                cur.execute("DELETE FROM dbo.etl_perfil_permissao WHERE perfil_nome = ?", [nome])
                for rec in permissoes:
                    rec = str(rec).strip()
                    if rec:
                        cur.execute(
                            "INSERT INTO dbo.etl_perfil_permissao (perfil_nome, recurso, criado_por) "
                            "VALUES (?, ?, ?)", [nome, rec, requested_by])
            conn.commit(); cur.close(); conn.close()
            return {"sucesso": True, "mensagem": f"Perfil '{nome}' salvo."}

        elif action == "perfil_delete":
            nome = (body.get("perfil_nome") or "").strip().lower()
            if not nome:
                raise HTTPException(status_code=422, detail="perfil_nome obrigatório")
            if nome in ("admin", "consulta"):
                raise HTTPException(status_code=422, detail=f"Perfil '{nome}' é protegido e não pode ser excluído")
            cur.execute("SELECT COUNT(*) FROM dbo.etl_usuario WHERE perfil_nome = ?", [nome])
            em_uso = cur.fetchone()[0]
            if em_uso:
                raise HTTPException(status_code=422,
                                    detail=f"Perfil '{nome}' está em uso por {em_uso} usuário(s)")
            cur.execute("DELETE FROM dbo.etl_perfil WHERE perfil_nome = ?", [nome])
            conn.commit(); cur.close(); conn.close()
            return {"sucesso": True, "mensagem": f"Perfil '{nome}' removido."}

        elif action == "pipeline_delete":
            pipeline_name = (body.get("pipeline_name") or "").strip()
            if not pipeline_name:
                raise HTTPException(status_code=422, detail="pipeline_name obrigatório")
            cur.execute(
                "SELECT total_jobs, total_lineage, dag_criada FROM dbo.vw_pipeline_dependencies "
                "WHERE pipeline_name = ?", (pipeline_name,)
            )
            deps = cur.fetchone()
            if not deps:
                raise HTTPException(status_code=404, detail=f"Pipeline '{pipeline_name}' não encontrado")
            cur.execute("EXEC dbo.sp_etl_pipeline_delete ?, ?", (pipeline_name, requested_by))
            conn.commit(); cur.close(); conn.close()
            return {"sucesso": True,
                    "mensagem": f'Pipeline "{pipeline_name}" removido.',
                    "detalhes": {"pipeline_name": pipeline_name,
                                 "jobs_removidos": deps[0], "lineage_removidos": deps[1],
                                 "dag_existia": bool(deps[2])}}

        elif action == "dag_file_delete":
            import glob as _glob
            pipeline_name = (body.get("pipeline_name") or "").strip()
            if not pipeline_name:
                raise HTTPException(status_code=422, detail="pipeline_name obrigatório")
            cur.close(); conn.close()
            dag_id    = pipeline_name.lower()
            dags_base = os.environ.get("DAGS_FOLDER", "/opt/airflow/dags")
            candidates = [
                os.path.join(dags_base, dag_id + ".py"),
                os.path.join(dags_base, pipeline_name + ".py"),
            ]
            candidates += _glob.glob(os.path.join(dags_base, "**", dag_id + ".py"), recursive=True)
            removed = [p for p in set(candidates) if os.path.isfile(p)]
            for p in removed:
                os.remove(p)
            return {"sucesso": True, "mensagem": f"{len(removed)} arquivo(s) removido(s).",
                    "detalhes": {"arquivos_removidos": removed}}

        elif action == "dag_airflow_delete":
            # Remove a DAG do Airflow (pausa + DELETE metadata) e apaga o arquivo .py.
            # Server-side: o React não possui a auth básica do Airflow, então o backend
            # — que já tem AIRFLOW_USER/PASSWORD — executa a limpeza completa.
            import glob as _glob
            pipeline_name = (body.get("pipeline_name") or "").strip()
            if not pipeline_name:
                raise HTTPException(status_code=422, detail="pipeline_name obrigatório")
            cur.close(); conn.close()

            dag_id = pipeline_name
            resultado = {"dag_pausada": False, "dag_removida": False, "arquivos_removidos": []}
            try:
                async with httpx.AsyncClient(
                    base_url=AIRFLOW_URL, auth=(AIRFLOW_USER, AIRFLOW_PASSWORD), timeout=15
                ) as client:
                    # 1. pausa a DAG (evita execuções enquanto remove)
                    try:
                        rp = await client.patch(f"/api/v1/dags/{dag_id}",
                                                json={"is_paused": True})
                        resultado["dag_pausada"] = rp.is_success
                    except Exception as e:
                        log.warning("Falha ao pausar DAG %s: %s", dag_id, e)
                    # 2. remove a DAG do metadata do scheduler
                    try:
                        rd = await client.delete(f"/api/v1/dags/{dag_id}")
                        resultado["dag_removida"] = rd.is_success or rd.status_code == 404
                    except Exception as e:
                        log.warning("Falha ao deletar DAG %s do Airflow: %s", dag_id, e)
            except Exception as e:
                log.warning("Cliente Airflow indisponível: %s", e)

            # 3. remove o arquivo .py do DAGS_FOLDER
            dags_base = os.environ.get("DAGS_FOLDER", "/opt/airflow/dags")
            candidates = [
                os.path.join(dags_base, pipeline_name.lower() + ".py"),
                os.path.join(dags_base, pipeline_name + ".py"),
            ]
            candidates += _glob.glob(
                os.path.join(dags_base, "**", pipeline_name.lower() + ".py"), recursive=True)
            removed = [p for p in set(candidates) if os.path.isfile(p)]
            for p in removed:
                try:
                    os.remove(p)
                except Exception as e:
                    log.warning("Falha ao remover arquivo %s: %s", p, e)
            resultado["arquivos_removidos"] = removed
            return {"sucesso": True,
                    "mensagem": f'DAG "{dag_id}" removida do Airflow.',
                    "detalhes": resultado}

        elif action == "factory_trigger":
            # Dispara a etl_dag_factory no Airflow (passo 2 da regeneração de DAGs).
            import time as _time
            filter_project = (body.get("filter_project") or "").strip()
            force_all = bool(body.get("force_all", True))
            cur.close(); conn.close()
            run_id = f"orq_regen_factory_{int(_time.time() * 1000)}"
            try:
                async with httpx.AsyncClient(
                    base_url=AIRFLOW_URL, auth=(AIRFLOW_USER, AIRFLOW_PASSWORD), timeout=20
                ) as client:
                    rf = await client.post(
                        "/api/v1/dags/etl_dag_factory/dagRuns",
                        json={"dag_run_id": run_id,
                              "conf": {"force_all": force_all,
                                       "filter_project": filter_project,
                                       "requested_by": requested_by}})
                    if not rf.is_success:
                        raise HTTPException(status_code=502,
                                            detail=f"Airflow rejeitou: HTTP {rf.status_code} — {rf.text[:200]}")
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(status_code=502, detail=f"Erro ao disparar factory: {e}")
            return {"sucesso": True,
                    "mensagem": "etl_dag_factory disparada.",
                    "detalhes": {"dag_run_id": run_id, "filter_project": filter_project or "(todos)"}}

        elif action == "regenerate_all_dags":
            filter_project = (body.get("filter_project") or "").strip()
            if filter_project:
                cur.execute(
                    "SELECT COUNT(*) FROM dbo.etl_pipeline WHERE project_name=? AND dag_criada=1",
                    (filter_project,)
                )
                n = cur.fetchone()[0] or 0
                cur.execute(
                    "UPDATE dbo.etl_pipeline SET dag_criada=0, updated_at=GETDATE() "
                    "WHERE project_name=? AND dag_criada=1", (filter_project,)
                )
            else:
                cur.execute("SELECT COUNT(*) FROM dbo.etl_pipeline WHERE dag_criada=1")
                n = cur.fetchone()[0] or 0
                cur.execute("UPDATE dbo.etl_pipeline SET dag_criada=0, updated_at=GETDATE() WHERE dag_criada=1")
            conn.commit(); cur.close(); conn.close()
            return {"sucesso": True, "mensagem": f"{n} pipeline(s) marcados para regeneração.",
                    "detalhes": {"pipelines_marcados": n, "filter_project": filter_project or "(todos)"}}

        # ── role_map_list ──────────────────────────────────────────────────────
        elif action == "role_map_list":
            cur.execute(
                "SELECT role_airflow, perfil_nome, ordem_prioridade, descricao, ativo "
                "FROM dbo.etl_airflow_role_perfil ORDER BY ordem_prioridade, role_airflow"
            )
            cols = [c[0] for c in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]
            cur.close(); conn.close()
            return {"sucesso": True, "dados": rows}

        # ── role_map_upsert ────────────────────────────────────────────────────
        elif action == "role_map_upsert":
            role        = (body.get("role_airflow")     or "").strip()
            perfil      = (body.get("perfil_nome")      or "").strip().lower()
            prioridade  = int(body.get("ordem_prioridade") or 99)
            descricao   = (body.get("descricao")        or "").strip() or None
            ativo       = bool(body.get("ativo", True))
            if not role:
                raise HTTPException(status_code=422, detail="role_airflow obrigatório")
            if not perfil:
                raise HTTPException(status_code=422, detail="perfil_nome obrigatório")
            cur.execute("SELECT 1 FROM dbo.etl_perfil WHERE perfil_nome = ?", [perfil])
            if not cur.fetchone():
                raise HTTPException(status_code=422,
                                    detail=f"Perfil '{perfil}' não existe")
            cur.execute("""
                MERGE dbo.etl_airflow_role_perfil AS t
                USING (SELECT ? AS r) AS s ON t.role_airflow = s.r
                WHEN MATCHED THEN UPDATE SET
                    perfil_nome=?, ordem_prioridade=?, descricao=?,
                    ativo=?, atualizado_em=GETDATE(), atualizado_por=?
                WHEN NOT MATCHED THEN INSERT
                    (role_airflow, perfil_nome, ordem_prioridade, descricao, ativo, criado_por)
                    VALUES (?, ?, ?, ?, ?, ?);
            """, [role, perfil, prioridade, descricao, 1 if ativo else 0, requested_by,
                  role, perfil, prioridade, descricao, 1 if ativo else 0, requested_by])
            conn.commit(); cur.close(); conn.close()
            return {"sucesso": True, "mensagem": f"Mapeamento '{role}' → '{perfil}' salvo."}

        # ── role_map_delete ────────────────────────────────────────────────────
        elif action == "role_map_delete":
            role = (body.get("role_airflow") or "").strip()
            if not role:
                raise HTTPException(status_code=422, detail="role_airflow obrigatório")
            cur.execute("DELETE FROM dbo.etl_airflow_role_perfil WHERE role_airflow = ?", [role])
            conn.commit(); cur.close(); conn.close()
            return {"sucesso": True, "mensagem": f"Mapeamento '{role}' removido."}

        # ── Conexões de Dados: fonte da verdade = dbo.etl_conexao ─────────────
        # As credenciais agora vivem no ORQUESTRA (senha cifrada com Fernet —
        # services/conn_crypto, chave ORQUESTRA_CONN_KEY). O Airflow aparece
        # apenas como fallback de leitura para conexões ainda não migradas
        # (action conn_migrate). A senha NUNCA aparece em resposta, log ou
        # mensagem de erro.
        elif action == "conn_list":
            conns: list[dict] = []
            vistos: set[str] = set()
            try:
                cur.execute(
                    "SELECT conn_id, host, port, login, descricao, extra_json, origem "
                    "FROM dbo.etl_conexao ORDER BY conn_id")
                for r in cur.fetchall():
                    vistos.add(r[0])
                    conns.append(
                        {"conn_id": r[0], "host": r[1] or "", "port": r[2],
                         "schema": "", "login": r[3] or "",
                         "description": r[4] or "",
                         "extra_charset": _extra_dict(r[5]).get("charset") or None,
                         "origem": "orquestra"})
            except Exception as e:
                log.warning("conn_list: leitura de etl_conexao falhou (%s) — "
                            "seguindo só com o Airflow", e)
            cur.close(); conn.close()
            # Conexões que ainda só existem no Airflow (pendentes de migração)
            # — best-effort: Airflow fora do ar não derruba a listagem.
            try:
                async with get_airflow_client() as client:
                    r = await client.get("/api/v1/connections?limit=100")
                    if r.is_success:
                        for c in r.json().get("connections", []):
                            cid = c.get("connection_id")
                            if (c.get("conn_type") or "").lower() != "mssql" \
                                    or not cid or cid in vistos:
                                continue
                            extra = c.get("extra")
                            if "extra" not in c:
                                # Airflow 2.x não devolve 'extra' na lista
                                # (campo sensível — só no GET por id).
                                try:
                                    rd = await client.get(f"/api/v1/connections/{cid}")
                                    if rd.is_success:
                                        extra = rd.json().get("extra")
                                except Exception as e:
                                    log.warning("conn_list: detalhe de '%s' falhou: %s",
                                                cid, e)
                            conns.append(
                                {"conn_id": cid,
                                 "host": c.get("host") or "",
                                 "port": c.get("port"),
                                 "schema": c.get("schema") or "",
                                 "login": c.get("login") or "",
                                 "description": c.get("description") or "",
                                 "extra_charset": _extra_dict(extra).get("charset") or None,
                                 "origem": "airflow"})
            except Exception as e:
                log.warning("conn_list: consulta ao Airflow falhou (%s) — "
                            "listando só as conexões do Orquestra", e)
            conns.sort(key=lambda c: c["conn_id"])
            return {"sucesso": True, "connections": conns}

        elif action == "conn_upsert":
            conn_id     = (body.get("conn_id") or "").strip()
            host        = (body.get("host") or "").strip()
            login       = (body.get("login") or "").strip()
            password    = body.get("password") or ""   # nunca logar/ecoar
            description = (body.get("description") or "").strip()
            charset     = (body.get("charset") or "").strip()
            if not _CONN_ID_RE.match(conn_id):
                raise HTTPException(
                    status_code=422,
                    detail="conn_id inválido — use letras, números, '_' ou '-' (máx. 100)")
            if not host:
                raise HTTPException(status_code=422, detail="host é obrigatório")
            if not _HOST_RE.match(host):
                raise HTTPException(
                    status_code=422,
                    detail="host inválido — use letras, números, '.', '-', '_' ou '\\'")
            port = _porta_valida(body.get("port"))
            cur.execute("SELECT extra_json FROM dbo.etl_conexao WHERE conn_id = ?",
                        (conn_id,))
            row = cur.fetchone()
            if row is None:
                # ── criação ────────────────────────────────────────────────
                if not login:
                    raise HTTPException(status_code=422,
                                        detail="login é obrigatório ao criar")
                if not password:
                    raise HTTPException(
                        status_code=422,
                        detail=("password é obrigatório ao criar — para trazer "
                                "uma conexão do Airflow sem redigitar a senha, "
                                "use 'Migrar do Airflow'"))
                extra_json = json.dumps({"charset": charset}) if charset else None
                cur.execute(
                    "INSERT INTO dbo.etl_conexao "
                    "  (conn_id, conn_type, host, port, login, senha_enc, "
                    "   descricao, extra_json, origem, criado_por) "
                    "VALUES (?, 'mssql', ?, ?, ?, ?, ?, ?, 'orquestra', ?)",
                    (conn_id, host, port, login, encrypt_password(password),
                     description or None, extra_json, requested_by))
                conn.commit(); cur.close(); conn.close()
                log.info("conn_upsert: conexão '%s' criada por %s", conn_id, requested_by)
                return {"sucesso": True, "criada": True,
                        "mensagem": f"Conexão '{conn_id}' criada no Orquestra."}
            # ── atualização — só altera o que veio no body ─────────────────
            sets   = ["host = ?", "atualizado_por = ?", "atualizado_em = GETDATE()"]
            params: list = [host, requested_by]
            if "port" in body:
                sets.append("port = ?"); params.append(port)
            if login:
                sets.append("login = ?"); params.append(login)
            if "description" in body:
                sets.append("descricao = ?"); params.append(description or None)
            if password:  # em branco/ausente = mantém a senha atual
                sets.append("senha_enc = ?"); params.append(encrypt_password(password))
            if "charset" in body:
                extra_atual = _extra_dict(row[0])
                extra_novo = dict(extra_atual)
                if charset:
                    extra_novo["charset"] = charset
                else:  # charset vazio remove a chave, preservando as demais
                    extra_novo.pop("charset", None)
                if extra_novo != extra_atual:
                    sets.append("extra_json = ?")
                    params.append(json.dumps(extra_novo) if extra_novo else None)
            params.append(conn_id)
            cur.execute(f"UPDATE dbo.etl_conexao SET {', '.join(sets)} "
                        "WHERE conn_id = ?", params)
            conn.commit(); cur.close(); conn.close()
            log.info("conn_upsert: conexão '%s' atualizada por %s", conn_id, requested_by)
            return {"sucesso": True, "criada": False,
                    "mensagem": f"Conexão '{conn_id}' atualizada no Orquestra."}

        elif action == "conn_delete":
            conn_id = (body.get("conn_id") or "").strip()
            if not _CONN_ID_RE.match(conn_id):
                raise HTTPException(status_code=422, detail="conn_id inválido")
            # GUARDA: recusa excluir connection referenciada por Cópias de
            # Dados ativas ou por jobs de pipeline (nó SQL). Degrada
            # graciosamente se as tabelas não existirem neste ambiente.
            refs: list[str] = []
            try:
                cur.execute(
                    "SELECT nome FROM dbo.etl_copy_job "
                    "WHERE ativo = 1 AND (src_conn_id = ? OR dst_conn_id = ?)",
                    (conn_id, conn_id))
                refs += [f'Cópia de Dados "{r[0]}"' for r in cur.fetchall()]
            except Exception as e:
                log.warning("conn_delete: checagem etl_copy_job falhou (%s) — ignorando", e)
            try:
                cur.execute(
                    "SELECT pipeline_name, job_name FROM dbo.etl_pipeline_job "
                    "WHERE mssql_conn_id = ?", (conn_id,))
                refs += [f'job "{r[1]}" do pipeline "{r[0]}"' for r in cur.fetchall()]
            except Exception as e:
                log.warning("conn_delete: checagem etl_pipeline_job falhou (%s) — ignorando", e)
            if refs:
                cur.close(); conn.close()
                extras = f" (+{len(refs) - 10} outra(s))" if len(refs) > 10 else ""
                raise HTTPException(
                    status_code=409,
                    detail=(f"A conexão '{conn_id}' está em uso e não pode ser "
                            f"excluída: {'; '.join(refs[:10])}{extras}"))
            try:
                cur.execute("DELETE FROM dbo.etl_conexao WHERE conn_id = ?", (conn_id,))
                apagadas = cur.rowcount
                conn.commit()
            except Exception as e:
                apagadas = 0
                log.warning("conn_delete: exclusão em etl_conexao falhou (%s) — "
                            "tentando o Airflow", e)
            cur.close(); conn.close()
            if apagadas:
                log.info("conn_delete: conexão '%s' removida do Orquestra por %s",
                         conn_id, requested_by)
                return {"sucesso": True,
                        "mensagem": f"Conexão '{conn_id}' removida do Orquestra."}
            # Não estava na tabela — pode ser uma conexão legada só do Airflow.
            try:
                async with get_airflow_client() as client:
                    rd = await client.delete(f"/api/v1/connections/{conn_id}")
            except Exception as e:
                raise HTTPException(status_code=502,
                                    detail=f"Erro ao comunicar com o Airflow: {e}")
            if rd.status_code == 404:
                raise HTTPException(status_code=404,
                                    detail=f"conexão '{conn_id}' não encontrada")
            if not rd.is_success:
                raise HTTPException(
                    status_code=502,
                    detail=f"Airflow recusou a exclusão (HTTP {rd.status_code})")
            log.info("conn_delete: connection '%s' removida do Airflow por %s",
                     conn_id, requested_by)
            return {"sucesso": True,
                    "mensagem": f"Connection '{conn_id}' removida do Airflow."}

        elif action == "conn_test":
            cur.close(); conn.close()
            password = body.get("password") or ""
            if password:
                # ── modo (a): senha em mãos — conexão DIRETA da API (pyodbc,
                # mesmo perfil msodbcsql18 de _open_swapped_conn/jobs.py), com
                # a conn string montada só com os dados do form (NUNCA reusa a
                # credencial do app). timeout 5s + SELECT 1.
                host  = (body.get("host") or "").strip()
                login = (body.get("login") or "").strip()
                database = (body.get("database") or "").strip() or "master"
                if not host or not _HOST_RE.match(host):
                    raise HTTPException(status_code=422,
                                        detail="host é obrigatório (e sem caracteres especiais)")
                if not login:
                    raise HTTPException(status_code=422, detail="login é obrigatório")
                port = _porta_valida(body.get("port"))
                conn_str = (
                    f"DRIVER={{{_melhor_driver_odbc()}}};SERVER={host},{port};"
                    f"DATABASE={_odbc_quote(database)};UID={_odbc_quote(login)};"
                    f"PWD={_odbc_quote(password)};TrustServerCertificate=yes"
                )
                try:
                    cx = pyodbc.connect(conn_str, timeout=5)
                    try:
                        c2 = cx.cursor()
                        c2.execute("SELECT 1")
                        c2.fetchone()
                        c2.close()
                    finally:
                        cx.close()
                except Exception as e:
                    return {"ok": False,
                            "mensagem": (f"Falha na conexão com '{host},{port}': "
                                         f"{_sem_senha(e, password)[:400]}")}
                return {"ok": True,
                        "mensagem": (f"Conexão OK — SELECT 1 executado em "
                                     f"{host},{port} (banco '{database}').")}

            # ── modo (b): sem senha — testa a conexão SALVA.
            # Se está em dbo.etl_conexao, decifra a senha e testa DIRETO da
            # API com a credencial real (pyodbc, timeout 5s + SELECT 1).
            # Conexão legada (só no Airflow): caminho antigo — consulta com a
            # credencial do app e fallback DAG (BaseHook no worker).
            conn_id = (body.get("conn_id") or "").strip()
            if not conn_id:
                raise HTTPException(
                    status_code=422,
                    detail="informe conn_id (teste da conexão salva) ou host+login+password (teste direto)")
            row = None
            try:
                conn2 = get_db_conn(); cur2 = conn2.cursor()
                cur2.execute(
                    "SELECT host, port, login, senha_enc FROM dbo.etl_conexao "
                    "WHERE conn_id = ?", (conn_id,))
                row = cur2.fetchone()
                cur2.close(); conn2.close()
            except Exception as e:
                log.warning("conn_test: leitura de etl_conexao falhou (%s)", e)
            if row is not None:
                host, port, login, senha_enc = row[0], row[1] or 1433, row[2], row[3]
                senha = decrypt_password(senha_enc)
                conn_str = (
                    f"DRIVER={{{_melhor_driver_odbc()}}};SERVER={host},{int(port)};"
                    f"DATABASE=master;UID={_odbc_quote(login)};"
                    f"PWD={_odbc_quote(senha)};TrustServerCertificate=yes"
                )
                try:
                    cx = pyodbc.connect(conn_str, timeout=5)
                    try:
                        c2 = cx.cursor()
                        c2.execute("SELECT COUNT(*) FROM sys.databases d "
                                   "WHERE d.state_desc = 'ONLINE' "
                                   "AND HAS_DBACCESS(d.name) = 1")
                        n_dbs = c2.fetchone()[0]
                        c2.close()
                    finally:
                        cx.close()
                except Exception as e:
                    return {"ok": False, "via": "orquestra",
                            "mensagem": (f"Teste da conexão '{conn_id}' falhou "
                                         f"({host},{int(port)}): "
                                         f"{_sem_senha(e, senha)[:400]}")}
                return {"ok": True, "via": "orquestra",
                        "mensagem": (f"Conexão OK — '{host},{int(port)}' respondeu "
                                     f"com a credencial cadastrada "
                                     f"({n_dbs} banco(s) acessíveis).")}
            try:
                server = await _server_da_conexao(conn_id)
            except HTTPException as e:
                return {"ok": False, "via": "airflow-rest",
                        "mensagem": f"Falha ao resolver a connection '{conn_id}': {e.detail}"}
            try:
                rows = _consulta_direta(
                    server, "master",
                    "SELECT d.name FROM sys.databases d "
                    "WHERE d.state_desc = 'ONLINE' AND HAS_DBACCESS(d.name) = 1")
                return {"ok": True, "via": "direto",
                        "mensagem": (f"Conexão OK — servidor '{server}' respondeu "
                                     f"({len(rows)} banco(s) acessíveis).")}
            except HTTPException as e:
                log.info("conn_test: caminho direto falhou (%s) — fallback DAG", e.detail)
            try:
                payload, via = await _introspect_via_dag("databases", conn_id, timeout_s=60)
                dbs = payload.get("databases", [])
                obs = " (resultado do cache de introspecção, < 24h)" if via == "cache" else ""
                return {"ok": True, "via": via,
                        "mensagem": (f"Conexão OK via Airflow — {len(dbs)} banco(s) "
                                     f"listados com a credencial da connection.{obs}")}
            except HTTPException as e:
                return {"ok": False, "via": "airflow",
                        "mensagem": f"Teste da connection '{conn_id}' falhou: {e.detail}"}

        elif action == "conn_migrate":
            # Migra as Airflow Connections mssql para dbo.etl_conexao COM a
            # senha: só o worker enxerga a senha em texto (BaseHook/metadados),
            # então a cópia roda na DAG etl_admin_manage — o worker cifra com
            # a ORQUESTRA_CONN_KEY e grava direto na tabela. A senha nunca
            # trafega pela API. Conexões já migradas são preservadas.
            cur.close(); conn.close()
            run_id = f"conn_migrate_{_dt.datetime.now().strftime('%Y%m%dT%H%M%S%f')}"
            try:
                async with get_airflow_client() as client:
                    r = await client.post(
                        "/api/v1/dags/etl_admin_manage/dagRuns",
                        json={"dag_run_id": run_id,
                              "conf": {"action": "conn_migrate",
                                       "requested_by": requested_by}})
                    if not r.is_success:
                        raise HTTPException(
                            status_code=502,
                            detail=("Airflow recusou o dagRun de migração "
                                    f"({r.status_code}) — verifique se a DAG "
                                    "etl_admin_manage existe e está ativa"))
                    estado = ""
                    limite = time.monotonic() + 60
                    while time.monotonic() < limite:
                        await asyncio.sleep(2)
                        rs = await client.get(
                            f"/api/v1/dags/etl_admin_manage/dagRuns/{run_id}")
                        if not rs.is_success:
                            continue
                        estado = (rs.json().get("state") or "").lower()
                        if estado in ("success", "failed"):
                            break
                    if estado not in ("success", "failed"):
                        raise HTTPException(
                            status_code=504,
                            detail=("A migração excedeu 60s — verifique a DAG "
                                    "etl_admin_manage e o worker"))
                    if estado == "failed":
                        raise HTTPException(
                            status_code=502,
                            detail=("A migração falhou no Airflow — veja o log "
                                    f"da task 'admin_manage' do run {run_id} "
                                    "(ORQUESTRA_CONN_KEY configurada no worker?)"))
                    rx = await client.get(
                        f"/api/v1/dags/etl_admin_manage/dagRuns/{run_id}"
                        "/taskInstances/admin_manage/xcomEntries/return_value")
                    valor = rx.json().get("value") if rx.is_success else None
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(status_code=502,
                                    detail=f"Erro na migração via Airflow: {e}")
            try:
                payload = json.loads(valor) if isinstance(valor, str) else valor
            except (ValueError, TypeError):
                payload = None
            if not isinstance(payload, dict):
                payload = {"sucesso": True,
                           "mensagem": "Migração concluída (resultado indisponível no XCom)."}
            log.info("conn_migrate: executada por %s — %s",
                     requested_by, payload.get("mensagem"))
            return payload

        else:
            raise HTTPException(status_code=422, detail=f"Action desconhecida: '{action}'")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro DB: {e}")


@router.post("/admin/freeze", tags=["agenda"])
async def freeze_ambiente(body: dict = Body(default={}), _admin: dict = Depends(get_admin_user)):
    """Congela/descongela o ambiente inteiro.

    Implementado como blackout global aberto (fim 9999) — toda DAG gerada
    verifica blackout na task check_agenda e se auto-pula enquanto vigente.
    Body: { acao: 'congelar' | 'descongelar' }
    """
    rb = _admin["matricula"]
    acao = (body.get("acao") or "").strip().lower()
    if acao not in ("congelar", "descongelar"):
        raise HTTPException(status_code=422, detail="acao deve ser 'congelar' ou 'descongelar'")
    try:
        conn = get_db_conn(); cur = conn.cursor()
        if acao == "congelar":
            cur.execute(
                "SELECT TOP 1 id FROM dbo.etl_blackout "
                "WHERE ativo=1 AND escopo IS NULL AND motivo=? AND GETDATE() BETWEEN inicio AND fim",
                (FREEZE_MOTIVO,))
            if cur.fetchone():
                cur.close(); conn.close()
                return {"sucesso": True, "mensagem": "Ambiente já está congelado.", "congelado": True}
            cur.execute(
                "INSERT INTO dbo.etl_blackout (inicio, fim, escopo, motivo, ativo, criado_por) "
                "VALUES (GETDATE(), '9999-12-31', NULL, ?, 1, ?)", (FREEZE_MOTIVO, rb))
            conn.commit(); cur.close(); conn.close()
            return {"sucesso": True, "mensagem": "Ambiente congelado — nenhuma DAG gerada iniciará execução.",
                    "congelado": True}
        else:
            cur.execute(
                "UPDATE dbo.etl_blackout SET ativo=0, encerrado_por=?, encerrado_em=GETDATE() "
                "WHERE ativo=1 AND escopo IS NULL AND motivo=?", (rb, FREEZE_MOTIVO))
            n = cur.rowcount
            conn.commit(); cur.close(); conn.close()
            return {"sucesso": True,
                    "mensagem": "Ambiente descongelado." if n else "Ambiente não estava congelado.",
                    "congelado": False}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _test_webhook_impl(requested_by: str, _req):
    # ── 1. Resolver qual URL será usada ────────────────────────────────────
    key_ack     = "teams_webhook_url_ack"
    key_default = "teams_webhook_url"

    val_ack     = _get_app_config_value(key_ack)
    val_default = _get_app_config_value(key_default)
    val_env     = os.getenv("TEAMS_WEBHOOK_URL_CVP", "")

    diag = {
        "resolucao": {
            key_ack:     "✓ preenchida" if val_ack     else "✗ vazia/ausente",
            key_default: "✓ preenchida" if val_default else "✗ vazia/ausente",
            "env_TEAMS_WEBHOOK_URL_CVP": "✓ presente" if val_env else "✗ ausente",
        }
    }

    webhook_url = val_ack or val_default or val_env
    if not webhook_url:
        diag["erro"] = "Nenhum webhook configurado. Preencha teams_webhook_url_ack em Admin > Configurações."
        return diag

    diag["url_usada"] = webhook_url[:40] + "..." + webhook_url[-20:] if len(webhook_url) > 64 else webhook_url
    diag["fonte"] = key_ack if val_ack else (key_default if val_default else "env")

    # ── 2. Disparar card de teste ───────────────────────────────────────────
    payload = {
        "type": "message",
        "attachments": [{
            "contentType": "application/vnd.microsoft.card.adaptive",
            "content": {
                "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                "type": "AdaptiveCard", "version": "1.4",
                "body": [
                    {"type": "TextBlock",
                     "text": "🔔 ORQUESTRA — Teste de webhook",
                     "size": "Large", "weight": "Bolder", "wrap": True, "color": "Accent"},
                    {"type": "TextBlock",
                     "text": f"Testado por {requested_by} via Admin > Configurações.",
                     "wrap": True, "isSubtle": True},
                    {"type": "FactSet", "facts": [
                        {"title": "Chave usada",  "value": diag["fonte"]},
                        {"title": "URL (parcial)", "value": diag["url_usada"]},
                    ]},
                ],
            },
        }],
    }

    try:
        resp = _req.post(webhook_url, json=payload, timeout=15)
        diag["http_status"]   = resp.status_code
        diag["http_response"] = resp.text[:300] or "(vazio)"
        diag["ok"] = resp.status_code in (200, 202)
        if not diag["ok"]:
            diag["erro"] = f"Teams rejeitou: HTTP {resp.status_code} — {resp.text[:200]}"
    except Exception as e:
        diag["ok"]   = False
        diag["erro"] = f"Erro de conexão: {e}"

    return diag


@router.post("/admin/test-webhook", tags=["admin"])
async def test_webhook(body: dict = Body(default={}), _admin: dict = Depends(get_admin_user)):
    """Testa envio ao Teams e devolve diagnóstico completo (uso exclusivo Admin)."""
    import traceback

    requested_by = _admin["matricula"]
    try:
        return _test_webhook_impl(requested_by, httpx)
    except Exception:
        # Nunca deixa virar 500 sem JSON — devolve o traceback para o Admin
        return {"ok": False, "erro": "Exceção interna no teste",
                "traceback": traceback.format_exc()[-1500:]}


# ═══════════════════════════════════════════════════════════════════════════
# Inventário das DAGs do SISTEMA — GET /admin/dags/inventario
#
# O catálogo (funcionalidade/frequência em pt-BR) mora AQUI, no código: é
# documentação viva, versionada junto das DAGs que descreve. O Airflow entra
# como fonte do ESTADO ao vivo (presente/pausada/agendamento real) — e o
# cruzamento é o valor do inventário: catalogada AUSENTE no Airflow é drift a
# investigar; presente e NÃO catalogada é catálogo desatualizado (as duas
# aparecem, nenhuma é escondida). As DAGs de pipeline (geradas pela fábrica em
# dags/generated/) ficam FORA — o lugar delas é a tela Pipelines.
# ═══════════════════════════════════════════════════════════════════════════

# Ordem de exibição das categorias — o front respeita a ordem recebida.
CATEGORIAS_DAGS = [
    "Núcleo", "Monitoramento e alertas", "Consultas da aplicação (RPC)",
    "Cadastro e gestão", "Cópia de Dados", "Linhagem e importação",
    "não catalogada",
]

_RPC = "sob demanda — RPC da aplicação (resultado via XCom)"
_APP = "sob demanda — disparada pela aplicação"

CATALOGO_DAGS: dict = {
    # ── Núcleo ──────────────────────────────────────────────────────────────
    "etl_dag_factory": {
        "categoria": "Núcleo",
        "funcionalidade": "Fábrica de DAGs: gera e republica a DAG de cada "
            "pipeline a partir do cadastro (aceita lista de alvos e force_all)",
        "frequencia": "sob demanda — Publicar DAGs, Republicar pipelines e "
            "gestos da aplicação",
    },
    "etl_dependencia_guardia": {
        "categoria": "Núcleo",
        "funcionalidade": "Guardiã de dependências e do ciclo da malha: ordena "
            "o dia, redispara dependentes, abre/fecha o ciclo, vigia deadline "
            "e avisa no Teams",
        "frequencia": "a cada 5 min (Variable "
            "DEPENDENCIA_GUARDIA_INTERVAL_MINUTES)",
    },
    # ── Monitoramento e alertas ─────────────────────────────────────────────
    "etl_servicenow_sync": {
        "categoria": "Monitoramento e alertas",
        "funcionalidade": "Espelha os chamados do ServiceNow do(s) grupo(s) da "
            "engenharia (incidentes, RITMs, tarefas e mudanças) para a tela de "
            "Chamados; cada tabela sincroniza independente e o ciclo fica "
            "registrado em etl_chamado_sync",
        "frequencia": "a cada 15 min (só com servicenow_habilitado=1 em "
            "Admin > ServiceNow)",
    },
    "etl_ds_supervisao_monitor": {
        "categoria": "Monitoramento e alertas",
        "funcionalidade": "Supervisão DataStage: coleta o logsum dos jobs "
            "cadastrados, varre a árvore de filhos em largura e classifica o "
            "dia (abortou, sucesso falso, não executou…)",
        "frequencia": "a cada 15 min (Variable DS_SUPERVISAO_INTERVAL_MINUTES)",
    },
    "etl_ds_monitor_centralizado": {
        "categoria": "Monitoramento e alertas",
        "funcionalidade": "Monitor centralizado DataStage: acompanha os jobs "
            "em execução disparados pelo Orquestra e grava o log de etapas",
        "frequencia": "a cada 3 min (Variable MONITOR_INTERVAL_MINUTES)",
    },
    "etl_datastage_monitor": {
        "categoria": "Monitoramento e alertas",
        "funcionalidade": "Monitora um job DataStage específico em execução "
            "(conf {project, job_name})",
        "frequencia": _APP,
    },
    "etl_performance_monitor": {
        "categoria": "Monitoramento e alertas",
        "funcionalidade": "Monitor de performance: snapshots de execuções "
            "longas (3h/6h/12h) que alimentam os alertas do Dashboard",
        "frequencia": "de hora em hora (0 * * * *)",
    },
    "orquestra_sla_monitor": {
        "categoria": "Monitoramento e alertas",
        "funcionalidade": "Sentinela de SLA: alerta no Teams quando uma "
            "execução estoura ou ameaça o SLA",
        "frequencia": "a cada 5 min (*/5 * * * *)",
    },
    "orquestra_daily_report": {
        "categoria": "Monitoramento e alertas",
        "funcionalidade": "Relatório diário no Teams: resumo da janela noturna",
        "frequencia": "diária às 07:00 (0 7 * * *)",
    },
    # ── Consultas da aplicação (RPC) ────────────────────────────────────────
    "etl_app_config_query": {
        "categoria": "Consultas da aplicação (RPC)",
        "funcionalidade": "Busca parâmetros de configuração do Orquestra no banco",
        "frequencia": _RPC,
    },
    "etl_catalogo_query": {
        "categoria": "Consultas da aplicação (RPC)",
        "funcionalidade": "Catálogo de dados: busca por tabela/arquivo e ranking",
        "frequencia": _RPC,
    },
    "etl_job_execution_query": {
        "categoria": "Consultas da aplicação (RPC)",
        "funcionalidade": "Consulta paginada de logs de execução",
        "frequencia": _RPC,
    },
    "etl_lineage_query": {
        "categoria": "Consultas da aplicação (RPC)",
        "funcionalidade": "Consulta de linhagem (job e pipeline) para a Governança",
        "frequencia": _RPC,
    },
    "etl_pipeline_query": {
        "categoria": "Consultas da aplicação (RPC)",
        "funcionalidade": "Consulta paginada do cadastro de pipelines",
        "frequencia": _RPC,
    },
    "etl_pipeline_audit_query": {
        "categoria": "Consultas da aplicação (RPC)",
        "funcionalidade": "Consulta da auditoria de alterações de pipelines",
        "frequencia": _RPC,
    },
    "etl_pipeline_job_query": {
        "categoria": "Consultas da aplicação (RPC)",
        "funcionalidade": "Consulta paginada de jobs (etapas) de pipeline",
        "frequencia": _RPC,
    },
    "etl_versao_query": {
        "categoria": "Consultas da aplicação (RPC)",
        "funcionalidade": "Consulta do histórico de versões do Orquestra",
        "frequencia": _RPC,
    },
    # ── Cadastro e gestão ───────────────────────────────────────────────────
    "etl_admin_manage": {
        "categoria": "Cadastro e gestão",
        "funcionalidade": "Operações administrativas restritas (limpezas e "
            "gestos de manutenção disparados pelo Admin)",
        "frequencia": _APP,
    },
    "etl_pipeline_register": {
        "categoria": "Cadastro e gestão",
        "funcionalidade": "Cria e atualiza o cadastro de um pipeline",
        "frequencia": _APP,
    },
    "etl_pipeline_job_register": {
        "categoria": "Cadastro e gestão",
        "funcionalidade": "Cria e atualiza os jobs (etapas) de um pipeline",
        "frequencia": _APP,
    },
    "etl_pipeline_job_reorder": {
        "categoria": "Cadastro e gestão",
        "funcionalidade": "Reordena as etapas de um pipeline",
        "frequencia": _APP,
    },
    "etl_versao_register": {
        "categoria": "Cadastro e gestão",
        "funcionalidade": "CRUD do histórico de versões do Orquestra",
        "frequencia": _APP,
    },
    # ── Cópia de Dados ──────────────────────────────────────────────────────
    "etl_copy_exec": {
        "categoria": "Cópia de Dados",
        "funcionalidade": "Executa uma cópia de dados registrada entre "
            "servidores SQL (conf {exec_id})",
        "frequencia": _APP,
    },
    "etl_copy_introspect": {
        "categoria": "Cópia de Dados",
        "funcionalidade": "Introspecção de origem/destino da Cópia de Dados "
            "(bancos, tabelas, colunas)",
        "frequencia": _RPC,
    },
    # ── Linhagem e importação ───────────────────────────────────────────────
    "etl_lineage_extract_dsx": {
        "categoria": "Linhagem e importação",
        "funcionalidade": "Extrai a linhagem de um job DataStage a partir do "
            "arquivo .dsx",
        "frequencia": _APP,
    },
    "etl_lineage_normalize": {
        "categoria": "Linhagem e importação",
        "funcionalidade": "Normaliza a linhagem legada (object_name = tabela real)",
        "frequencia": _APP,
    },
    "etl_sequence_import_parse": {
        "categoria": "Linhagem e importação",
        "funcionalidade": "Importa uma sequence DataStage: extrai jobs, ordem "
            "e linhagem para aprovação",
        "frequencia": _APP,
    },
    "etl_sequence_import_approve": {
        "categoria": "Linhagem e importação",
        "funcionalidade": "Aprova a importação da sequence: move o staging "
            "para as tabelas principais",
        "frequencia": _APP,
    },
}
# `orquestra_teste.py` fica FORA de propósito: não é DAG — é o script usado
# como job_command no wizard (mora em dags/ só para os workers o enxergarem).


def _dag_inventario_item(dag_id: str, cat: dict | None, viva: dict | None,
                         airflow_ok: bool) -> dict:
    """Uma linha do inventário — catálogo manda no texto, Airflow no estado."""
    item = {
        "dag_id": dag_id,
        "funcionalidade": (cat or {}).get("funcionalidade")
            or (viva or {}).get("description") or "—",
        "frequencia": (cat or {}).get("frequencia") or "—",
        "categoria": (cat or {}).get("categoria") or "não catalogada",
        "catalogada": cat is not None,
        # `None` = "não sei" (Airflow fora do ar) — o front mostra "—", nunca
        # "ausente": afirmar ausência sem ter perguntado seria drift inventado.
        "presente_no_airflow": (viva is not None) if airflow_ok else None,
        "pausada": bool(viva.get("is_paused")) if viva else None,
        "agendamento": None,
    }
    if viva:
        si = viva.get("schedule_interval")
        valor = si.get("value") if isinstance(si, dict) else si
        item["agendamento"] = valor or viva.get("timetable_description") or None
    return item


@router.get("/admin/dags/inventario", tags=["admin"])
async def dags_inventario(_admin: dict = Depends(get_admin_user)):
    """Inventário das DAGs de sistema: catálogo curado × estado ao vivo."""
    vivas: dict = {}
    airflow_ok = True
    try:
        async with get_airflow_client() as client:
            offset = 0
            while True:
                r = await client.get(
                    "/api/v1/dags",
                    params={"limit": 100, "offset": offset,
                            "only_active": "false"})
                r.raise_for_status()
                data = r.json()
                pagina = data.get("dags", [])
                for d in pagina:
                    if d.get("dag_id"):
                        vivas[d["dag_id"]] = d
                # Avança pelo TAMANHO REAL da página, não pelo limit pedido:
                # um AIRFLOW__API__MAXIMUM_PAGE_LIMIT abaixo de 100 devolveria
                # páginas menores, e pular 100 fixo perderia DAGs — que
                # apareceriam como "ausente no Airflow" falsamente.
                if not pagina:
                    break
                offset += len(pagina)
                if offset >= int(data.get("total_entries") or 0):
                    break
    except Exception as e:
        # Airflow fora do ar não derruba o inventário: o catálogo continua
        # valendo como documentação — só o ESTADO fica sem resposta, e isso
        # é DITO (`airflow_disponivel: false`), não silenciado.
        log.warning("[DAGS-INVENTARIO] Airflow indisponível: %s", e)
        airflow_ok = False

    itens = [_dag_inventario_item(d, CATALOGO_DAGS[d], vivas.get(d), airflow_ok)
             for d in CATALOGO_DAGS]
    if airflow_ok:
        for dag_id, viva in vivas.items():
            if dag_id in CATALOGO_DAGS:
                continue
            # DAG de pipeline (gerada pela fábrica) fica fora do inventário de
            # sistema — o lugar dela é a tela Pipelines.
            if "/generated/" in (viva.get("fileloc") or ""):
                continue
            itens.append(_dag_inventario_item(dag_id, None, viva, airflow_ok))

    ordem = {c: i for i, c in enumerate(CATEGORIAS_DAGS)}
    itens.sort(key=lambda i: (ordem.get(i["categoria"], len(ordem)),
                              i["dag_id"]))
    return {"airflow_disponivel": airflow_ok, "total": len(itens),
            "dags": itens}


# ═══════════════════════════════════════════════════════════════════════════
# Sonda de diagnóstico do ServiceNow — POST /admin/servicenow/diagnostico
#
# BANCADA pré-spec (docs/spec-chamados-servicenow.md, PR #297): valida
# credencial, acesso às 4 tabelas de chamado, grupos e volumetria ANTES de a
# F1 existir. A credencial vive só na requisição: não é gravada em banco, em
# config nem em log — o handler não loga o body. Restrita a admin.
# ═══════════════════════════════════════════════════════════════════════════

_SN_TABELAS = list(servicenow.TABELAS)

# A lógica de domínio mora em services/servicenow.py (a DAG de sync também
# precisa dela). Os nomes antigos seguem aqui como apelido para não quebrar
# quem já importava de routers.admin.
_sn_url_valida = servicenow.url_valida
_sn_proxy_efetivo = servicenow.proxy_efetivo


@router.get("/admin/servicenow/config", tags=["admin"])
async def servicenow_config(_admin: dict = Depends(get_admin_user)):
    """Instância a exibir na sonda: a SALVA no banco tem precedência sobre o
    default de ambiente (SERVICENOW_URL) — quem configurou pelo Admin manda.

    Só a URL, e nunca a credencial: usuário/senha saem por `servicenow_get`,
    com a senha mascarada.
    """
    cfg = servicenow.load_config()
    return {"url": cfg["url"] or (os.environ.get("SERVICENOW_URL") or "").strip().rstrip("/")}


@router.post("/admin/servicenow/diagnostico", tags=["admin"])
async def servicenow_diagnostico(body: dict = Body(default={}),
                                 _admin: dict = Depends(get_admin_user)):
    """Sonda: auth → grupos → tabelas (estados reais) → volumetria do grupo.

    A credencial pode vir de dois lugares, e a diferença importa:
      - do BODY: credencial de teste, usada só nesta chamada e nunca gravada
        (é o modo de descobrir/validar uma credencial ANTES de salvar);
      - da CONFIG (`usar_config: true`): a credencial executora salva, a mesma
        que a DAG de sync usa — é assim que se testa o que roda de verdade.
    Sem o segundo modo, "a sonda passa" e "o sync funciona" seriam perguntas
    diferentes com a mesma resposta aparente.
    """
    if body.get("usar_config"):
        cfg = servicenow.load_config()
        url, usuario, senha = servicenow.credencial_executora(cfg)
        url = _sn_url_valida(url)
    else:
        url = _sn_url_valida(body.get("url") or "")
        usuario = (body.get("usuario") or "").strip()
        senha = body.get("senha") or ""
    grupo_busca = (body.get("grupo_busca") or "").strip()
    grupo_nome = (body.get("grupo_nome") or "").strip()
    if not usuario or not senha:
        raise HTTPException(status_code=422, detail="usuario e senha são obrigatórios")

    resultado: dict = {"url": url, "auth": None, "grupos": [],
                       "tabelas": {}, "grupo_contagem": None, "proxy": None,
                       "origem_credencial": "config" if body.get("usar_config") else "formulário"}
    # Proxy corporativo: NÃO passar parâmetro. O httpx com trust_env (padrão)
    # já lê HTTPS_PROXY/HTTP_PROXY do ambiente — e só assim o NO_PROXY é
    # respeitado. Passar proxy=/proxies= explicitamente FORÇA o proxy até em
    # host isento, e `proxies=` ainda some no httpx 0.28+. Quem injeta as
    # variáveis no container é o docker-compose.yaml (serviço orquestra-api).
    async with httpx.AsyncClient(auth=(usuario, senha), timeout=20,
                                 headers={"Accept": "application/json"}) as cli:
        resultado["proxy"] = _sn_proxy_efetivo(cli, url)
        # ── 1. autenticação (sys_user_group é a tabela mais inócua) ─────────
        try:
            r = await cli.get(f"{url}/api/now/table/sys_user_group",
                              params={"sysparm_limit": 1})
            resultado["auth"] = {"status": r.status_code, "ok": r.status_code == 200}
            if r.status_code == 401:
                resultado["auth"]["motivo"] = "credencial recusada (401)"
            elif r.status_code == 403:
                resultado["auth"]["motivo"] = ("autenticou, mas sem permissão de "
                                               "leitura em sys_user_group (403)")
        except httpx.HTTPError as e:
            resultado["auth"] = {"status": None, "ok": False,
                                 "motivo": f"falha de rede: {type(e).__name__}"}
            return resultado
        if resultado["auth"]["status"] == 401:
            return resultado  # sem credencial válida não há o que sondar

        # ── 2. grupos que casam com a busca (achar o nome exato) ────────────
        if grupo_busca:
            try:
                r = await cli.get(f"{url}/api/now/table/sys_user_group", params={
                    "sysparm_query": f"nameLIKE{grupo_busca}",
                    "sysparm_fields": "name,sys_id,active",
                    "sysparm_limit": 15})
                if r.status_code == 200:
                    resultado["grupos"] = r.json().get("result", [])
            except httpx.HTTPError:
                pass

        # ── 3. as 4 tabelas: acessível? estados REAIS? (pendência #3) ──────
        for t in _SN_TABELAS:
            item: dict = {"acessivel": False, "status": None,
                          "total_ativos": None, "estados_exemplo": []}
            try:
                r = await cli.get(f"{url}/api/now/table/{t}", params={
                    "sysparm_query": "active=true",
                    "sysparm_fields": "state",
                    "sysparm_display_value": "true",
                    "sysparm_limit": 15})
                item["status"] = r.status_code
                if r.status_code == 200:
                    item["acessivel"] = True
                    total = r.headers.get("X-Total-Count")
                    item["total_ativos"] = int(total) if total and total.isdigit() else None
                    estados = [x.get("state") for x in r.json().get("result", [])]
                    item["estados_exemplo"] = sorted({e for e in estados if e})
            except httpx.HTTPError as e:
                item["erro"] = type(e).__name__
            resultado["tabelas"][t] = item

        # ── 4. volumetria do grupo (nome exato, vindo do passo 2) ──────────
        if grupo_nome:
            cont: dict = {}
            for t in _SN_TABELAS:
                try:
                    r = await cli.get(f"{url}/api/now/table/{t}", params={
                        "sysparm_query": f"assignment_group.name={grupo_nome}^active=true",
                        "sysparm_fields": "number", "sysparm_limit": 1})
                    total = r.headers.get("X-Total-Count")
                    if r.status_code == 200:
                        cont[t] = int(total) if total and total.isdigit() else None
                    else:
                        cont[t] = None
                except httpx.HTTPError:
                    cont[t] = None
            resultado["grupo_contagem"] = {"grupo": grupo_nome, "por_tabela": cont}
    return resultado
