"""api/routers/utilitarios.py — tela Utilitários: arquivos no servidor por SFTP.

Spec: docs/spec-utilitarios-arquivos.md (F1 = leitura + cadastro do admin).

  GET  /utilitarios/config                    — servidores, raízes ativas, extensões, teto, pode_gravar
  POST /utilitarios/arquivo/ler               — {servidor, diretorio, nome, ultimas_linhas?, codificacao?}
  GET  /utilitarios/admin/raizes              — todas (inclusive inativas)            [admin]
  POST /utilitarios/admin/raizes              — {servidor, caminho} → {id}            [admin]
  PATCH /utilitarios/admin/raizes/{id}        — {ativo}                                [admin]
  POST /utilitarios/admin/raizes/{id}/testar  — stat no servidor                       [admin]
  GET  /utilitarios/admin/extensoes                                                    [admin]
  POST /utilitarios/admin/extensoes           — {extensao}                             [admin]
  DELETE /utilitarios/admin/extensoes/{ext}                                            [admin]
  PUT  /utilitarios/admin/config              — {tamanho_max_kb, backup_ao_sobrescrever} [admin]

Permissão: `require_tela_utilitarios` (admin OU recurso tela_utilitarios). Gravar
(F4) exige também PERM_EDITAR — `pode_gravar` no /config já diz isso à tela.

Política e SFTP vivem em `services/ssh_arquivos.py`; aqui fica o banco (raízes,
extensões, config, auditoria) e a tradução ArquivoError → HTTP. Todo acesso SSH
roda em `asyncio.to_thread` — o paramiko é bloqueante. A conexão com o banco é
aberta e fechada em volta de cada consulta: nunca fica presa esperando o SSH.

Degradação: sem a migration 105, `/config` responde 503 nomeando a migration e a
tela mostra o aviso; o resto do Orquestra não é afetado.
"""
from __future__ import annotations

import asyncio
import logging
import re
import time

from fastapi import APIRouter, Body, Depends, HTTPException

from db import get_db_conn
from deps import PERM_EDITAR, get_admin_user, require_tela_utilitarios
from services import ssh_arquivos as svc

log = logging.getLogger("orquestra-api")

router = APIRouter()

K_TETO = "utilitarios_arquivo_max_kb"
K_BACKUP = "utilitarios_arquivo_backup"
_EXT_RE = re.compile(r"^[a-z0-9]{1,15}$")
_TABELAS = ("etl_utilitario_raiz", "etl_utilitario_extensao", "etl_utilitario_arquivo_log")


# ── banco: helpers ───────────────────────────────────────────────────────────

def _fechar(conn, cur) -> None:
    for x in (cur, conn):
        try:
            x.close()
        except Exception:
            pass


def _tabelas_ok(cur) -> bool:
    cur.execute(
        "SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES "
        "WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME IN (?, ?, ?)", list(_TABELAS))
    row = cur.fetchone()
    return bool(row and int(row[0]) == len(_TABELAS))


def _exigir_tabelas(cur) -> None:
    if not _tabelas_ok(cur):
        raise HTTPException(
            status_code=503,
            detail="Utilitários indisponíveis: migration 105 pendente "
                   "(tabelas etl_utilitario_* ausentes).")


def _teto_kb(bruto) -> int:
    try:
        v = int(str(bruto).strip())
    except (TypeError, ValueError):
        return svc.TETO_PADRAO_KB
    return max(1, min(v, svc.TETO_MAX_KB))


def _carregar_config(cur) -> dict:
    """Raízes ATIVAS, extensões e as duas chaves de etl_app_config."""
    cur.execute(
        "SELECT id, servidor, caminho FROM dbo.etl_utilitario_raiz "
        "WHERE ativo = 1 ORDER BY servidor, caminho")
    raizes = [{"id": r[0], "servidor": r[1], "caminho": r[2]} for r in cur.fetchall()]
    cur.execute("SELECT extensao FROM dbo.etl_utilitario_extensao ORDER BY extensao")
    extensoes = [r[0] for r in cur.fetchall()]
    cfg: dict = {}
    try:
        cur.execute(
            "SELECT config_key, config_value FROM dbo.etl_app_config "
            "WHERE config_key IN (?, ?)", [K_TETO, K_BACKUP])
        cfg = {r[0]: r[1] for r in cur.fetchall()}
    except Exception:
        cfg = {}  # chaves ausentes → defaults da spec
    return {
        "raizes": raizes,
        "extensoes": extensoes,
        "tamanho_max_kb": _teto_kb(cfg.get(K_TETO)),
        "backup_ao_sobrescrever": (cfg.get(K_BACKUP) or "1").strip() != "0",
    }


def _config_do_banco() -> dict:
    conn = get_db_conn()
    cur = conn.cursor()
    try:
        _exigir_tabelas(cur)
        return _carregar_config(cur)
    finally:
        _fechar(conn, cur)


def _auditar(*, usuario: str, servidor: str, acao: str, caminho: str, resultado: str,
             tamanho=None, sha256=None, detalhe=None, duracao_ms=None) -> None:
    """Best-effort: auditoria que falha não derruba a leitura — mas avisa no log."""
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        try:
            cur.execute(
                "INSERT INTO dbo.etl_utilitario_arquivo_log "
                "(usuario, servidor, acao, caminho, tamanho_bytes, sha256, resultado, detalhe, duracao_ms) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [usuario, servidor, acao, (caminho or "")[:svc.LIMITE_CAMINHO], tamanho, sha256,
                 resultado, (detalhe or "")[:500] or None, duracao_ms])
            conn.commit()
        finally:
            _fechar(conn, cur)
    except Exception:
        log.warning("Utilitários: falha ao auditar %s %s (%s)", acao, caminho, resultado, exc_info=True)


def _ms(t0: float) -> int:
    return int((time.time() - t0) * 1000)


# ── config da tela ───────────────────────────────────────────────────────────

@router.get("/utilitarios/config")
async def utilitarios_config(user: dict = Depends(require_tela_utilitarios)):
    cfg = _config_do_banco()
    return {
        "servidores": svc.servidores_disponiveis(),
        "raizes": cfg["raizes"],
        "extensoes": cfg["extensoes"],
        "tamanho_max_kb": cfg["tamanho_max_kb"],
        "backup_ao_sobrescrever": cfg["backup_ao_sobrescrever"],
        "pode_gravar": PERM_EDITAR in user.get("permissoes", []),
    }


# ── ler arquivo ──────────────────────────────────────────────────────────────

def _ultimas_linhas_valido(bruto) -> int | None:
    if bruto in (None, "", 0, "0"):
        return None
    try:
        n = int(bruto)
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="'ultimas_linhas' precisa ser um inteiro.")
    if n < 1 or n > svc.ULTIMAS_LINHAS_MAX:
        raise HTTPException(
            status_code=422,
            detail=f"'ultimas_linhas' precisa estar entre 1 e {svc.ULTIMAS_LINHAS_MAX}.")
    return n


def _ler_sync(servidor: str, caminho: str, raizes: list[str], teto_bytes: int,
              ultimas: int | None, codificacao: str | None) -> dict:
    with svc.conexao_sftp(servidor) as sftp:
        return svc.ler_arquivo(sftp, caminho, raizes, teto_bytes=teto_bytes,
                               ultimas=ultimas, codificacao=codificacao)


@router.post("/utilitarios/arquivo/ler")
async def utilitarios_ler_arquivo(body: dict = Body(...),
                                  user: dict = Depends(require_tela_utilitarios)):
    t0 = time.time()
    usuario = str(user.get("matricula") or "?")
    try:
        servidor = svc.servidor_valido(body.get("servidor"))
    except svc.ArquivoError as e:
        raise HTTPException(status_code=e.status, detail=e.detail)
    diretorio = body.get("diretorio")
    nome = body.get("nome")
    ultimas = _ultimas_linhas_valido(body.get("ultimas_linhas"))
    codificacao = (body.get("codificacao") or None)
    pedido_bruto = f"{str(diretorio or '').rstrip('/')}/{str(nome or '')}"

    cfg = _config_do_banco()
    raizes = [r["caminho"] for r in cfg["raizes"] if r["servidor"] == servidor]
    if not raizes:
        _auditar(usuario=usuario, servidor=servidor, acao="ler", caminho=pedido_bruto,
                 resultado="negado", detalhe="nenhum diretório-raiz ativo para o servidor",
                 duracao_ms=_ms(t0))
        raise HTTPException(
            status_code=403,
            detail="Nenhum diretório liberado para este servidor — cadastre uma raiz em "
                   "Admin › Utilitários.")

    # Validação e conferência LEXICAL antes de qualquer SSH.
    try:
        caminho, _raiz = svc.preparar_leitura(diretorio, nome, raizes)
    except svc.ArquivoError as e:
        _auditar(usuario=usuario, servidor=servidor, acao="ler", caminho=pedido_bruto,
                 resultado=e.resultado, detalhe=e.detail, duracao_ms=_ms(t0))
        raise HTTPException(status_code=e.status, detail=e.detail)

    teto_bytes = cfg["tamanho_max_kb"] * 1024
    try:
        resultado = await asyncio.to_thread(
            _ler_sync, servidor, caminho, raizes, teto_bytes, ultimas, codificacao)
    except svc.ArquivoError as e:
        _auditar(usuario=usuario, servidor=servidor, acao="ler", caminho=caminho,
                 resultado=e.resultado, detalhe=e.detail, duracao_ms=_ms(t0))
        raise HTTPException(status_code=e.status, detail=e.detail)
    except Exception as e:
        log.exception("Utilitários: falha inesperada ao ler %s", caminho)
        _auditar(usuario=usuario, servidor=servidor, acao="ler", caminho=caminho,
                 resultado="erro", detalhe=f"inesperado: {e}", duracao_ms=_ms(t0))
        raise HTTPException(status_code=502, detail=f"Falha ao ler o arquivo: {e}")

    resultado["duracao_ms"] = _ms(t0)
    detalhe = None
    if resultado["truncado"]:
        detalhe = f"últimas {ultimas} linhas (truncado)"
    _auditar(usuario=usuario, servidor=servidor, acao="ler", caminho=resultado["caminho"],
             resultado="ok", tamanho=resultado["tamanho_bytes"], detalhe=detalhe,
             duracao_ms=resultado["duracao_ms"])
    return resultado


# ── admin: raízes ────────────────────────────────────────────────────────────

def _fmt_dt(v):
    if v is None:
        return None
    return v.strftime("%Y-%m-%d %H:%M:%S") if hasattr(v, "strftime") else str(v)


@router.get("/utilitarios/admin/raizes")
async def admin_raizes_listar(_admin: dict = Depends(get_admin_user)):
    conn = get_db_conn()
    cur = conn.cursor()
    try:
        _exigir_tabelas(cur)
        cur.execute(
            "SELECT id, servidor, caminho, ativo, criado_por, criado_em "
            "FROM dbo.etl_utilitario_raiz ORDER BY servidor, ativo DESC, caminho")
        return [
            {"id": r[0], "servidor": r[1], "caminho": r[2], "ativo": bool(r[3]),
             "criado_por": r[4], "criado_em": _fmt_dt(r[5])}
            for r in cur.fetchall()
        ]
    finally:
        _fechar(conn, cur)


@router.post("/utilitarios/admin/raizes")
async def admin_raizes_incluir(body: dict = Body(...), admin: dict = Depends(get_admin_user)):
    try:
        servidor = svc.servidor_valido(body.get("servidor"))
        caminho = svc.normalizar_raiz(body.get("caminho"))
    except svc.ArquivoError as e:
        raise HTTPException(status_code=e.status, detail=e.detail)
    conn = get_db_conn()
    cur = conn.cursor()
    try:
        _exigir_tabelas(cur)
        cur.execute(
            "SELECT id, ativo FROM dbo.etl_utilitario_raiz WHERE servidor = ? AND caminho = ?",
            [servidor, caminho])
        row = cur.fetchone()
        if row:
            estado = "ativa" if row[1] else "inativa"
            raise HTTPException(
                status_code=409,
                detail=f"Raiz já cadastrada para este servidor (id {row[0]}, {estado}).")
        cur.execute(
            "INSERT INTO dbo.etl_utilitario_raiz (servidor, caminho, ativo, criado_por) "
            "OUTPUT INSERTED.id VALUES (?, ?, 1, ?)",
            [servidor, caminho, str(admin.get("matricula") or "?")])
        novo = cur.fetchone()
        conn.commit()
        return {"id": int(novo[0]) if novo else None, "servidor": servidor, "caminho": caminho}
    finally:
        _fechar(conn, cur)


@router.patch("/utilitarios/admin/raizes/{raiz_id}")
async def admin_raizes_ativar(raiz_id: int, body: dict = Body(...),
                              _admin: dict = Depends(get_admin_user)):
    ativo = body.get("ativo")
    if not isinstance(ativo, bool):
        raise HTTPException(status_code=422, detail="'ativo' precisa ser true ou false.")
    conn = get_db_conn()
    cur = conn.cursor()
    try:
        _exigir_tabelas(cur)
        cur.execute("UPDATE dbo.etl_utilitario_raiz SET ativo = ? WHERE id = ?",
                    [1 if ativo else 0, raiz_id])
        if not cur.rowcount:
            raise HTTPException(status_code=404, detail="Raiz não encontrada.")
        conn.commit()
        return {"ok": True, "id": raiz_id, "ativo": ativo}
    finally:
        _fechar(conn, cur)


def _testar_sync(servidor: str, caminho: str) -> dict:
    with svc.conexao_sftp(servidor) as sftp:
        return svc.testar_raiz(sftp, caminho)


@router.post("/utilitarios/admin/raizes/{raiz_id}/testar")
async def admin_raizes_testar(raiz_id: int, admin: dict = Depends(get_admin_user)):
    t0 = time.time()
    conn = get_db_conn()
    cur = conn.cursor()
    try:
        _exigir_tabelas(cur)
        cur.execute("SELECT servidor, caminho FROM dbo.etl_utilitario_raiz WHERE id = ?", [raiz_id])
        row = cur.fetchone()
    finally:
        _fechar(conn, cur)
    if not row:
        raise HTTPException(status_code=404, detail="Raiz não encontrada.")
    servidor, caminho = str(row[0]), str(row[1])
    usuario = str(admin.get("matricula") or "?")
    try:
        resultado = await asyncio.to_thread(_testar_sync, servidor, caminho)
    except svc.ArquivoError as e:
        _auditar(usuario=usuario, servidor=servidor, acao="testar", caminho=caminho,
                 resultado="erro", detalhe=e.detail, duracao_ms=_ms(t0))
        raise HTTPException(status_code=e.status, detail=e.detail)
    _auditar(usuario=usuario, servidor=servidor, acao="testar", caminho=caminho,
             resultado="ok", detalhe=resultado.get("detalhe"), duracao_ms=_ms(t0))
    resultado["duracao_ms"] = _ms(t0)
    return resultado


# ── admin: extensões ─────────────────────────────────────────────────────────

def _extensao_valida(bruto) -> str:
    s = str(bruto or "").strip().lower().lstrip(".")
    if not _EXT_RE.match(s):
        raise HTTPException(
            status_code=422,
            detail="Extensão inválida: só letras minúsculas e números, sem ponto, até 15 caracteres.")
    return s


@router.get("/utilitarios/admin/extensoes")
async def admin_extensoes_listar(_admin: dict = Depends(get_admin_user)):
    conn = get_db_conn()
    cur = conn.cursor()
    try:
        _exigir_tabelas(cur)
        cur.execute("SELECT extensao, criado_por, criado_em FROM dbo.etl_utilitario_extensao ORDER BY extensao")
        return [{"extensao": r[0], "criado_por": r[1], "criado_em": _fmt_dt(r[2])} for r in cur.fetchall()]
    finally:
        _fechar(conn, cur)


@router.post("/utilitarios/admin/extensoes")
async def admin_extensoes_incluir(body: dict = Body(...), admin: dict = Depends(get_admin_user)):
    ext = _extensao_valida(body.get("extensao"))
    conn = get_db_conn()
    cur = conn.cursor()
    try:
        _exigir_tabelas(cur)
        cur.execute("SELECT 1 FROM dbo.etl_utilitario_extensao WHERE extensao = ?", [ext])
        if cur.fetchone():
            raise HTTPException(status_code=409, detail=f"Extensão '{ext}' já cadastrada.")
        cur.execute("INSERT INTO dbo.etl_utilitario_extensao (extensao, criado_por) VALUES (?, ?)",
                    [ext, str(admin.get("matricula") or "?")])
        conn.commit()
        return {"ok": True, "extensao": ext}
    finally:
        _fechar(conn, cur)


@router.delete("/utilitarios/admin/extensoes/{extensao}")
async def admin_extensoes_excluir(extensao: str, _admin: dict = Depends(get_admin_user)):
    ext = _extensao_valida(extensao)
    conn = get_db_conn()
    cur = conn.cursor()
    try:
        _exigir_tabelas(cur)
        cur.execute("DELETE FROM dbo.etl_utilitario_extensao WHERE extensao = ?", [ext])
        if not cur.rowcount:
            raise HTTPException(status_code=404, detail=f"Extensão '{ext}' não está cadastrada.")
        conn.commit()
        return {"ok": True, "extensao": ext}
    finally:
        _fechar(conn, cur)


# ── admin: config ────────────────────────────────────────────────────────────

@router.put("/utilitarios/admin/config")
async def admin_config_gravar(body: dict = Body(...), admin: dict = Depends(get_admin_user)):
    bruto = body.get("tamanho_max_kb")
    try:
        teto = int(bruto)
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="'tamanho_max_kb' precisa ser um inteiro (KB).")
    if teto < 1 or teto > svc.TETO_MAX_KB:
        raise HTTPException(
            status_code=422,
            detail=f"'tamanho_max_kb' precisa estar entre 1 e {svc.TETO_MAX_KB}.")
    backup = body.get("backup_ao_sobrescrever")
    if not isinstance(backup, bool):
        raise HTTPException(status_code=422, detail="'backup_ao_sobrescrever' precisa ser true ou false.")
    quem = str(admin.get("matricula") or "?")
    conn = get_db_conn()
    cur = conn.cursor()
    try:
        _exigir_tabelas(cur)
        for chave, valor in ((K_TETO, str(teto)), (K_BACKUP, "1" if backup else "0")):
            cur.execute(
                "MERGE dbo.etl_app_config AS t USING (SELECT ? AS k, ? AS v) AS s "
                "ON t.config_key = s.k "
                "WHEN MATCHED THEN UPDATE SET config_value = s.v, updated_by = ?, updated_at = GETDATE() "
                "WHEN NOT MATCHED THEN INSERT (config_key, config_value, updated_by, updated_at) "
                "VALUES (s.k, s.v, ?, GETDATE());",
                [chave, valor, quem, quem])
        conn.commit()
        return {"ok": True, "tamanho_max_kb": teto, "backup_ao_sobrescrever": backup}
    finally:
        _fechar(conn, cur)
