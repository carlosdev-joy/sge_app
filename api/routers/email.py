"""api/routers/email.py — Notificação por e-mail, F1 (spec
docs/spec-notificacao-email.md): a configuração global e o envio de teste.

  GET  /email/status              {enabled, limite_mb, raizes, dominios, disponivel}
                                  (qualquer usuário autenticado — a tela do nó
                                  precisa saber as raízes e o limite, F2)
  GET  /email/admin/config        a config inteira (admin)
  POST /email/admin/config        grava (admin; ligar exige remetente)
  POST /email/admin/testar        monta uma mensagem MIME e entrega ao sendmail
                                  do servidor do DataStage via SSH; laudo na
                                  resposta e uma linha em etl_email_log (admin)
  GET  /email/log                 últimos envios (autenticado; ?pipeline=)

O envio de verdade das corridas é o EmailOperator (dags/utils, F2). Aqui só o
que o Admin precisa. Nada do usuário chega a uma linha de comando: o
`run_sendmail` executa um comando fixo e passa a mensagem pelo stdin.
"""
from __future__ import annotations

import json
import logging
import re
import time

from fastapi import APIRouter, Body, Depends, HTTPException

from db import get_db_conn
from deps import get_admin_user, get_current_user
from services import email_config, email_modelos, ssh_datastage
from services import email_mime as em
from services.ssh_arquivos import cortar_utf16

log = logging.getLogger("orquestra-api")

router = APIRouter()

_SEM_TABELA_RE = re.compile(r"Invalid object name", re.I)
_NOME_REPETIDO_RE = re.compile(r"duplicate key|UNIQUE KEY|ux_etl_email_modelo_nome", re.I)
ERRO_SEM_111 = "E-mail indisponível: migration 111 pendente (chaves email_* e dbo.etl_email_log)."
ERRO_SEM_112 = ("Catálogo de modelos indisponível: migration 112 pendente "
                "(dbo.etl_email_modelo).")
PIPELINE_TESTE = "_teste_admin"


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


def _exigir_config(cfg: dict) -> None:
    """Banco fora do ar NÃO é 'migration pendente': cada um com sua mensagem."""
    if cfg.get("erro"):
        raise HTTPException(status_code=503, detail=f"E-mail: falha ao ler a configuração ({cfg['erro']})")
    if not cfg["disponivel"]:
        raise HTTPException(status_code=503, detail=ERRO_SEM_111)


def _publica(cfg: dict) -> dict:
    return {"enabled": bool(cfg["enabled"]) and bool(cfg["remetente"]), "limite_mb": cfg["limite_mb"],
            "raizes": cfg["raizes"], "dominios": cfg["dominios"], "disponivel": cfg["disponivel"]}


@router.get("/email/status", tags=["email"])
def email_status(_user: dict = Depends(get_current_user)):
    conn, cur = _abrir()
    try:
        return _publica(email_config.load_config(cur))
    finally:
        _fechar(conn, cur)


@router.get("/email/admin/config", tags=["email-admin"])
def email_admin_config(_user: dict = Depends(get_admin_user)):
    conn, cur = _abrir()
    try:
        cfg = email_config.load_config(cur)
        _exigir_config(cfg)
        return {"config": {**cfg, "ssh_configurado": ssh_datastage.ssh_configured(),
                           "ssh_host": (ssh_datastage.os.getenv("DS_SSH_HOST") or "") if ssh_datastage.ssh_configured() else ""}}
    finally:
        _fechar(conn, cur)


@router.post("/email/admin/config", tags=["email-admin"])
def email_admin_config_set(body: dict = Body(default={}), user: dict = Depends(get_admin_user)):
    valores, erros = email_config.validar_config(body)
    if erros:
        raise HTTPException(status_code=422, detail={"code": "email_config_invalida", "errors": erros})
    conn, cur = _abrir()
    try:
        cfg = email_config.load_config(cur)
        _exigir_config(cfg)
        email_config.save_config(cur, valores, user["matricula"])
        _fechar(conn, cur, commit=True)
    except HTTPException:
        _fechar(conn, cur)
        raise
    except Exception:
        _fechar(conn, cur)
        raise
    conn, cur = _abrir()
    try:
        return {"config": email_config.load_config(cur)}
    finally:
        _fechar(conn, cur)


def registrar_log(cur, *, pipeline: str, job: str, dag_run_id: str | None, execution_id: str | None,
                  remetente: str, destinatarios: list[str], assunto: str, anexo_path: str | None,
                  anexo_bytes: int | None, status: str, erro: str | None, duracao_ms: int | None,
                  criado_por: str | None) -> None:
    cur.execute(
        "INSERT INTO dbo.etl_email_log (pipeline_name, job_name, dag_run_id, execution_id, remetente, "
        " destinatarios, assunto, anexo_path, anexo_bytes, status, erro, duracao_ms, criado_por) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (pipeline[:200], job[:200], dag_run_id, execution_id, remetente[:200],
         json.dumps(destinatarios, ensure_ascii=False), cortar_utf16(assunto, em.LIMITE_ASSUNTO),
         anexo_path, anexo_bytes, status[:20], cortar_utf16(erro, 1000) if erro else None, duracao_ms,
         (criado_por or None) and criado_por[:100]))


@router.post("/email/admin/testar", tags=["email-admin"])
def email_admin_testar(body: dict = Body(default={}), user: dict = Depends(get_admin_user)):
    """Envia um e-mail de teste ao próprio usuário (ou ao `para` informado) pelo
    mesmo caminho da corrida: MIME → SSH → sendmail. O laudo volta na resposta
    e fica em etl_email_log (pipeline '_teste_admin')."""
    conn, cur = _abrir()
    try:
        cfg = email_config.load_config(cur)
    finally:
        _fechar(conn, cur)
    _exigir_config(cfg)
    if not cfg["remetente"]:
        raise HTTPException(status_code=422, detail={"code": "email_sem_remetente",
                                                    "errors": ["Informe e salve o remetente antes de testar"]})
    para_raw = body.get("para") or user.get("email") or ""
    destinatarios, erros = em.validar_destinatarios(para_raw, cfg["dominios"])
    if erros or not destinatarios:
        raise HTTPException(status_code=422, detail={"code": "email_destinatario_invalido", "errors": erros or [
            "Seu usuário não tem e-mail cadastrado — informe o destinatário do teste em `para`"]})
    assunto = f"[Orquestra] Teste de e-mail — {time.strftime('%d/%m/%Y %H:%M')}"
    corpo = ("Este é um e-mail de teste do Orquestra.\n\n"
             f"Remetente configurado: {cfg['remetente']}\nDisparado por: {user.get('matricula')}\n"
             "Se você recebeu esta mensagem, o canal de e-mail (servidor do DataStage → relay) está funcionando.")
    try:
        mensagem = em.montar_mensagem(cfg["remetente"], destinatarios, assunto, corpo)
    except ValueError as e:   # remetente gravado à mão fora da régua
        raise HTTPException(status_code=422, detail={"code": "email_config_invalida",
                                                    "errors": [f"a configuração gravada não monta uma mensagem válida: {e}"]})
    laudo = {"ok": False, "etapa": "ssh", "mensagem": "", "host": "", "exit_code": None,
             "stderr": "", "duration_ms": None, "destinatarios": destinatarios, "remetente": cfg["remetente"]}
    status, erro = "falhou", None
    try:
        r = ssh_datastage.run_sendmail(mensagem, cfg["remetente"])
        laudo.update(host=r["host"], exit_code=r["exit_code"], stderr=r["stderr"], duration_ms=r["duration_ms"])
        if r["exit_code"] == 0:
            laudo.update(ok=True, etapa="ok", mensagem=f"sendmail aceitou a mensagem em {r['host']}.")
            status = "enviado"
        else:
            laudo.update(etapa="sendmail", mensagem=f"sendmail devolveu rc={r['exit_code']}: {r['stderr'] or 'sem detalhe'}")
            erro = f"rc={r['exit_code']}: {r['stderr']}"
    except ssh_datastage.DsConsoleError as e:
        laudo.update(etapa="config", mensagem=str(e))
        erro = str(e)
    except Exception as e:  # noqa: BLE001 — falha de rede/SSH: laudo, não 500
        laudo.update(etapa="ssh", mensagem=f"Não conectou ao servidor do DataStage: {type(e).__name__}: {e}")
        erro = f"{type(e).__name__}: {e}"
    try:
        conn, cur = _abrir()
        try:
            registrar_log(cur, pipeline=PIPELINE_TESTE, job="testar", dag_run_id=None, execution_id=None,
                          remetente=cfg["remetente"], destinatarios=destinatarios, assunto=assunto,
                          anexo_path=None, anexo_bytes=None, status=status, erro=erro,
                          duracao_ms=laudo["duration_ms"], criado_por=user.get("matricula"))
            _fechar(conn, cur, commit=True)
        except Exception:
            _fechar(conn, cur)
            raise
    except Exception as e:  # noqa: BLE001
        log.warning("email: falha ao registrar o teste (%s)", e)
        laudo["persistido"] = False
    return {"laudo": laudo}


# ── catálogo de modelos (migration 112, spec de modelos e navegação) ────────

def _exigir_catalogo(cur) -> None:
    if not email_modelos.tabela_existe(cur):
        raise HTTPException(status_code=503, detail=ERRO_SEM_112)


@router.get("/email/modelos", tags=["email"])
def email_modelos_ativos(_user: dict = Depends(get_current_user)):
    """Os modelos que o painel do nó oferece. Sem a 112, lista vazia e o painel
    cai no corpo livre — a tela do nó não quebra por causa do catálogo."""
    conn, cur = _abrir()
    try:
        if not email_modelos.tabela_existe(cur):
            return {"modelos": [], "disponivel": False, "exigir_modelo": False}
        cfg = email_config.load_config(cur)
        return {"modelos": email_modelos.listar(cur, apenas_ativos=True),
                "disponivel": True,
                "exigir_modelo": _exigir_modelo(cur),
                "dominios": cfg.get("dominios") or []}
    finally:
        _fechar(conn, cur)


def _exigir_modelo(cur) -> bool:
    """Interruptor `email_exigir_modelo`: ligado, a opção *Corpo livre* some da
    lista do nó. Ausente (ou sem a 112) = desligado."""
    try:
        cur.execute("SELECT config_value FROM dbo.etl_app_config WHERE config_key = ?",
                    ("email_exigir_modelo",))
        linha = cur.fetchone()
        return bool(linha) and str(linha[0] or "").strip() == "1"
    except Exception:  # noqa: BLE001
        return False


@router.get("/email/admin/modelos", tags=["email-admin"])
def email_admin_modelos(_user: dict = Depends(get_admin_user)):
    conn, cur = _abrir()
    try:
        _exigir_catalogo(cur)
        return {"modelos": email_modelos.listar(cur, com_corpo=False),
                "exigir_modelo": _exigir_modelo(cur)}
    finally:
        _fechar(conn, cur)


@router.get("/email/admin/modelos/{modelo_id}", tags=["email-admin"])
def email_admin_modelo(modelo_id: int, _user: dict = Depends(get_admin_user)):
    conn, cur = _abrir()
    try:
        _exigir_catalogo(cur)
        modelo = email_modelos.obter(cur, modelo_id)
        if not modelo:
            raise HTTPException(status_code=404, detail="Modelo não encontrado")
        return {"modelo": modelo, "pipelines": email_modelos.pipelines_que_usam(cur, modelo_id)}
    finally:
        _fechar(conn, cur)


@router.post("/email/admin/modelos", tags=["email-admin"])
def email_admin_modelo_criar(body: dict = Body(default={}), user: dict = Depends(get_admin_user)):
    valores, erros = email_modelos.validar(body)
    if erros:
        raise HTTPException(status_code=422, detail={"code": "email_modelo_invalido", "errors": erros})
    conn, cur = _abrir()
    try:
        _exigir_catalogo(cur)
        try:
            novo_id = email_modelos.criar(cur, valores, user["matricula"])
        except Exception as e:  # noqa: BLE001 — nome repetido é 409, não 500
            if _NOME_REPETIDO_RE.search(str(e)):
                raise HTTPException(status_code=409,
                                    detail=f"Já existe um modelo chamado '{valores['nome']}'")
            raise
        _fechar(conn, cur, commit=True)
    except HTTPException:
        _fechar(conn, cur); raise
    except Exception:
        _fechar(conn, cur); raise
    conn, cur = _abrir()
    try:
        return {"modelo": email_modelos.obter(cur, novo_id)}
    finally:
        _fechar(conn, cur)


@router.put("/email/admin/modelos/{modelo_id}", tags=["email-admin"])
def email_admin_modelo_editar(modelo_id: int, body: dict = Body(default={}),
                              _user: dict = Depends(get_admin_user)):
    valores, erros = email_modelos.validar(body)
    if erros:
        raise HTTPException(status_code=422, detail={"code": "email_modelo_invalido", "errors": erros})
    conn, cur = _abrir()
    try:
        _exigir_catalogo(cur)
        if not email_modelos.obter(cur, modelo_id):
            raise HTTPException(status_code=404, detail="Modelo não encontrado")
        try:
            email_modelos.atualizar(cur, modelo_id, valores)
        except Exception as e:  # noqa: BLE001
            if _NOME_REPETIDO_RE.search(str(e)):
                raise HTTPException(status_code=409,
                                    detail=f"Já existe um modelo chamado '{valores['nome']}'")
            raise
        _fechar(conn, cur, commit=True)
    except HTTPException:
        _fechar(conn, cur); raise
    except Exception:
        _fechar(conn, cur); raise
    conn, cur = _abrir()
    try:
        return {"modelo": email_modelos.obter(cur, modelo_id)}
    finally:
        _fechar(conn, cur)


@router.delete("/email/admin/modelos/{modelo_id}", tags=["email-admin"])
def email_admin_modelo_excluir(modelo_id: int, _user: dict = Depends(get_admin_user)):
    """Apagar modelo EM USO é recusado.

    É a lição do catálogo de cards do Teams, onde apagar o template faz o envio
    cair em silêncio para a mensagem embutida. Aqui, quem quer tirar um modelo
    de circulação **desativa** — quem já usa continua enviando e ele some da
    lista de escolha."""
    conn, cur = _abrir()
    try:
        _exigir_catalogo(cur)
        if not email_modelos.obter(cur, modelo_id):
            raise HTTPException(status_code=404, detail="Modelo não encontrado")
        usados = email_modelos.pipelines_que_usam(cur, modelo_id)
        if usados:
            raise HTTPException(
                status_code=409,
                detail={"code": "email_modelo_em_uso", "pipelines": usados,
                        "errors": [f"Modelo em uso em {len(usados)} fluxo(s): "
                                   + ", ".join(usados[:10])
                                   + (" …" if len(usados) > 10 else "")
                                   + ". Desative o modelo em vez de excluir — quem já usa "
                                     "continua enviando e ele some da lista de escolha."]})
        email_modelos.excluir(cur, modelo_id)
        _fechar(conn, cur, commit=True)
        return {"excluido": modelo_id}
    except HTTPException:
        _fechar(conn, cur); raise
    except Exception:
        _fechar(conn, cur); raise


@router.get("/email/log", tags=["email"])
def email_log(pipeline: str | None = None, execution_id: str | None = None,
              limite: int = 50, _user: dict = Depends(get_current_user)):
    """Últimos envios. `execution_id` filtra NO BANCO os envios de uma corrida —
    sem ele, a tela de execução teria de filtrar em memória sobre os N últimos
    do pipeline, e o bloco sumiria das corridas antigas."""
    limite = max(1, min(int(limite or 50), 200))
    conn, cur = _abrir()
    try:
        try:
            colunas = ("id, pipeline_name, job_name, dag_run_id, execution_id, remetente, "
                       "destinatarios, assunto, anexo_path, anexo_bytes, status, erro, duracao_ms, "
                       "criado_por, CONVERT(VARCHAR(19), criado_em, 120)")
            if pipeline and execution_id:
                cur.execute(
                    f"SELECT TOP ({limite}) {colunas} FROM dbo.etl_email_log "
                    "WHERE pipeline_name = ? AND execution_id = ? "
                    "ORDER BY criado_em DESC, id DESC", (pipeline[:200], execution_id[:100]))
            elif execution_id:
                cur.execute(
                    f"SELECT TOP ({limite}) {colunas} FROM dbo.etl_email_log "
                    "WHERE execution_id = ? ORDER BY criado_em DESC, id DESC", (execution_id[:100],))
            elif pipeline:
                cur.execute(
                    f"SELECT TOP ({limite}) {colunas} FROM dbo.etl_email_log WHERE pipeline_name = ? "
                    "ORDER BY criado_em DESC, id DESC", (pipeline[:200],))
            else:
                cur.execute(
                    f"SELECT TOP ({limite}) id, pipeline_name, job_name, dag_run_id, execution_id, remetente, "
                    "destinatarios, assunto, anexo_path, anexo_bytes, status, erro, duracao_ms, criado_por, "
                    "CONVERT(VARCHAR(19), criado_em, 120) FROM dbo.etl_email_log "
                    "ORDER BY criado_em DESC, id DESC")
            rows = cur.fetchall()
        except Exception as e:
            if _SEM_TABELA_RE.search(str(e)):
                raise HTTPException(status_code=503, detail=ERRO_SEM_111)
            raise
    finally:
        _fechar(conn, cur)
    cols = ("id", "pipeline_name", "job_name", "dag_run_id", "execution_id", "remetente", "destinatarios",
            "assunto", "anexo_path", "anexo_bytes", "status", "erro", "duracao_ms", "criado_por", "criado_em")
    saida = []
    for r in rows:
        d = dict(zip(cols, r))
        try:
            d["destinatarios"] = json.loads(d["destinatarios"] or "[]")
        except (TypeError, ValueError):
            d["destinatarios"] = []
        saida.append(d)
    return {"envios": saida}
