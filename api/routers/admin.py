"""api/routers/admin.py — POST /admin, POST /admin/freeze, POST /admin/test-webhook."""
from __future__ import annotations

import logging
import os

import httpx
from fastapi import APIRouter, Body, Depends, HTTPException

from db import get_db_conn
from deps import (
    PERM_ADMIN,
    get_current_user, get_admin_user,
)

log = logging.getLogger("orquestra-api")

router = APIRouter()

FREEZE_MOTIVO = "Congelamento manual do ambiente"


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
            data = {k: v for k, v in cur.fetchall()}
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
