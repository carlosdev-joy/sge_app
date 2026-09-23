"""api/routers/agentes.py — tela Agentes: catálogo, status do gateway por
usuário, config do admin e a conversa com o agente DataStage (F1+F2 da spec
docs/spec-agentes-datastage.md).

  GET  /agentes/catalogo               agentes que o usuário logado pode abrir
  GET  /agentes/status                 estado da sonda de cadastro no gateway (cacheado)
  GET  /agentes/admin/config           config de Agentes (admin)
  POST /agentes/admin/config           grava config de Agentes (admin)
  POST /agentes/datastage/conversar    uma rodada com o agente DataStage (F2)

`tela_agentes` é checada por `require_perm` puro — como qualquer outra tela
(perfil ∪ overrides). O que É especial é o acesso a CADA AGENTE
(`agente_datastage`, `agente_curador`): ver `services/agentes.require_agente`.

A conversa persiste em `etl_agente_conversa`/`etl_agente_mensagem` (migration
117), mas NÃO segura uma conexão de banco durante a rodada com o modelo — a
orquestração (`services.agentes.conversar`) abre conexões curtas, uma por
ferramenta, e só este router mantém uma conexão de cada vez (antes e depois
da rodada), nunca durante.
"""
from __future__ import annotations

import json
import re
import uuid

from fastapi import APIRouter, Body, Depends, HTTPException, Query

from db import get_db_conn
from deps import PERM_EDITAR, get_admin_user, require_perm
from services import agentes as svc
from services import agentes_ferramentas as af
from services import ia_provedor

router = APIRouter()

_require_tela = require_perm("tela_agentes")
_require_datastage = svc.require_agente(svc.AGENTE_DATASTAGE)

_RE_CAMPO = re.compile(r"^(header|body):.+$")
_RE_CONVERSA_ID = re.compile(r"^[A-Za-z0-9_-]{8,36}$")
_MAX_MENSAGEM = 4000  # mesmo teto do Maestro (MAX_MENSAGEM em maestro.py)


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
    # `cadastro_texto` viaja AQUI, e não no `/agentes/status`, por dois
    # motivos: o catálogo já lê a config (custo zero) e o status tem um
    # contrato que não pode mudar — `test_status_cache_hit_nao_toca_banco_nem_sonda`
    # prende que um acerto de cache não abre conexão nenhuma, e buscar o
    # texto ali obrigaria a abrir. É o mesmo dado, no lugar que já o tinha.
    #
    # Ele vem sempre, não só quando o usuário está sem cadastro: quem decide
    # MOSTRAR é a tela, e só no estado `sem_cadastro` (`AvisoSonda`, preso
    # por tests/test_agentes_f3_front.py). Não é segredo — é o aviso que o
    # admin escreveu justamente para ser lido por quem precisa se cadastrar.
    return {"agentes": svc.catalogo_do_usuario(user, cfg),
            "cadastro_texto": cfg.get("agentes_cadastro_texto") or None}


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
    # O catálogo vai junto com `recurso`/`perfis_elegiveis` porque a aba
    # Admin › Agentes precisa saber A QUEM pode oferecer cada agente. Sem
    # isso o front teria de repetir essa regra à mão — e uma 2ª lista de
    # RBAC fora de sincronia é exatamente o defeito que `RBAC_RECURSOS` já
    # custou uma vez (tests/test_rbac_recursos_admin.py existe por isso).
    catalogo = [{"id": ag["id"], "nome": ag["nome"], "recurso": ag["recurso"],
                 "recurso_curador": ag["recurso_curador"],
                 "config_enabled": ag["config_enabled"],
                 "perfis_elegiveis": list(ag["perfis_elegiveis"])}
                for ag in svc.CATALOGO.values()]
    return {"sucesso": True, "config": cfg, "agentes": catalogo}


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


@router.post("/agentes/datastage/conversar", tags=["agentes"])
async def agentes_datastage_conversar(body: dict = Body(default={}),
                                      user: dict = Depends(_require_datastage)):
    """Uma rodada com o agente DataStage. `require_agente` já garante:
    admin passa sempre; não-admin exige perfil `desenvolvedor` e o grant em
    `permissoes_extra` (nunca o que vier só do perfil)."""
    mensagem = str(body.get("mensagem") or "").strip()
    if not mensagem:
        raise HTTPException(status_code=422, detail={
            "code": "mensagem_obrigatoria", "message": "mensagem é obrigatória"})
    if len(mensagem) > _MAX_MENSAGEM:
        raise HTTPException(status_code=422, detail={
            "code": "mensagem_longa", "message": f"mensagem excede {_MAX_MENSAGEM} caracteres"})
    conversa_id = str(body.get("conversa_id") or "").strip()
    if conversa_id and not _RE_CONVERSA_ID.match(conversa_id):
        raise HTTPException(status_code=422, detail={
            "code": "conversa_id_invalido",
            "message": "conversa_id inválido (8 a 36 caracteres: letras, números, - e _)"})
    if not conversa_id:
        conversa_id = str(uuid.uuid4())
    # A identidade é SEMPRE a da sessão — nunca um valor do corpo. Uma
    # `matricula` forjada no corpo é simplesmente ignorada (critério 6 da F2).
    matricula = user["matricula"]

    conn, cur = _abrir()
    try:
        agentes_cfg = svc.carregar_config(cur)
        if agentes_cfg.get("agentes_enabled") != "1" or agentes_cfg.get("agente_datastage_enabled") != "1":
            raise HTTPException(status_code=503, detail={
                "code": "agente_desligado", "message": "Agente DataStage desligado"})
        cur.execute("SELECT projeto, matricula FROM dbo.etl_agente_conversa WHERE conversa_id = ?",
                    [conversa_id])
        row = cur.fetchone()
        if row is not None and row[1] != matricula:
            # 404, não 403: uma conversa alheia não deve nem confirmar que existe.
            raise HTTPException(status_code=404, detail={
                "code": "conversa_nao_encontrada", "message": "conversa não encontrada"})
        if row is None:
            cur.execute(
                "INSERT INTO dbo.etl_agente_conversa (conversa_id, agente, matricula, titulo) "
                "VALUES (?, ?, ?, ?)",
                [conversa_id, svc.AGENTE_DATASTAGE, matricula, mensagem[:200]])
            projeto_atual = None
            historico: list[dict] = []
        else:
            projeto_atual = row[0]
            cur.execute(
                "SELECT papel, conteudo FROM dbo.etl_agente_mensagem "
                "WHERE conversa_id = ? ORDER BY id", [conversa_id])
            historico = [{"role": r[0], "content": r[1]} for r in cur.fetchall()]
        provedor_cfg = ia_provedor.load_config(cur)
        cadastro = None
        try:
            cur.execute("SELECT identidade_gateway FROM dbo.etl_usuario WHERE matricula = ?", [matricula])
            row_id = cur.fetchone()
            cadastro = row_id[0] if row_id else None
        except Exception:
            cadastro = None  # coluna pode não existir ainda (migration 117) — cai no padrão
        conn.commit()
    except HTTPException:
        raise
    finally:
        # finally, não só except HTTPException/else: uma exceção do DRIVER
        # (deadlock, timeout, conexão caindo — não é HTTPException) não caía
        # em nenhum dos dois ramos antes e vazava a conexão (achado real da
        # revisão adversarial da F2). Confirmado com reprodução isolada:
        # try/except/else nunca roda o `except` de um tipo que não bate nem
        # o `else` quando uma exceção se propaga.
        _fechar(conn, cur)

    identidade = svc.identidade_gateway(matricula, cadastro)
    campo = agentes_cfg.get("agentes_gateway_campo_usuario") or None
    try:
        ssh_max = int(agentes_cfg.get("agentes_ssh_max") or 10)
    except (TypeError, ValueError):
        ssh_max = 10

    # Redigida ANTES de entrar no histórico que vai ao modelo e ANTES de
    # qualquer gravação — um segredo digitado no chat não chega a nenhum dos dois.
    mensagem_redigida = af.redigir(mensagem)
    # `acao_editar` é SEMPRE da sessão (F2b, isx_extrair) — nunca do corpo,
    # mesma régua da identidade (critério 6 da F2, estendido).
    acao_editar = PERM_EDITAR in user.get("permissoes", [])
    resultado = await svc.conversar(
        _abrir, mensagens=historico + [{"role": "user", "content": mensagem_redigida}],
        projeto_atual=projeto_atual, provedor_cfg=provedor_cfg,
        identidade=identidade, campo_identidade=campo, ssh_max=ssh_max,
        acao_editar=acao_editar, matricula=matricula)

    texto_redigido = af.redigir(resultado.get("texto") or "")
    conn, cur = _abrir()
    try:
        cur.execute(
            "INSERT INTO dbo.etl_agente_mensagem (conversa_id, papel, conteudo) VALUES (?, ?, ?)",
            [conversa_id, "user", mensagem_redigida])
        cur.execute(
            "INSERT INTO dbo.etl_agente_mensagem "
            "(conversa_id, papel, conteudo, status, artefatos_json) VALUES (?, ?, ?, ?, ?)",
            [conversa_id, "assistant", texto_redigido, resultado.get("status"),
             json.dumps(resultado.get("artefatos") or [], ensure_ascii=False)])
        cur.execute(
            "UPDATE dbo.etl_agente_conversa SET projeto = ?, ultima_msg_em = GETDATE() "
            "WHERE conversa_id = ?", [resultado.get("projeto"), conversa_id])
        conn.commit()
    finally:
        _fechar(conn, cur)

    return {"conversa_id": conversa_id, "status": resultado.get("status"),
            "texto": texto_redigido, "projeto": resultado.get("projeto"),
            "artefatos": resultado.get("artefatos") or []}
