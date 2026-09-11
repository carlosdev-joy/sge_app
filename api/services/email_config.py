"""api/services/email_config.py — a configuração global do e-mail em
dbo.etl_app_config (chaves email_*, migration 111), gerida em Admin › E-mail.

Sem segredo: o relay não exige autenticação e o remetente é público. Por isso
nada aqui é cifrado — e nada aqui pode virar comando: os valores só entram em
cabeçalhos MIME (services/email_mime) ou em comparações de caminho.
"""
from __future__ import annotations

import json

from services import email_mime as em

K_HABILITADO = "email_habilitado"
K_REMETENTE = "email_remetente"
K_LIMITE_MB = "email_limite_anexo_mb"
K_RAIZES = "email_anexo_raizes"
K_DOMINIOS = "email_dominios_permitidos"
CHAVES = (K_HABILITADO, K_REMETENTE, K_LIMITE_MB, K_RAIZES, K_DOMINIOS)

DESCRICAO = "E-mail do Orquestra (Admin > E-mail)"
LIMITE_VALOR = 1000   # dbo.etl_app_config.config_value VARCHAR(1000)


def _lista_json(valor) -> list[str]:
    try:
        dados = json.loads(valor or "[]")
    except (TypeError, ValueError):
        return []
    return [str(x) for x in dados] if isinstance(dados, list) else []


def load_config(cur) -> dict:
    """{enabled, remetente, limite_mb, raizes, dominios, disponivel, erro}. Sem
    as chaves (migration 111 pendente) → desligado e `disponivel=False` — a
    tela diz que falta a migration. Banco fora do ar NÃO é "migration pendente":
    volta `erro` preenchido para o diagnóstico ser o certo."""
    cfg = {"enabled": False, "remetente": "", "limite_mb": em.LIMITE_ANEXO_MB_PADRAO,
           "raizes": [], "dominios": [], "disponivel": False, "erro": None}
    try:
        cur.execute(
            "SELECT config_key, config_value FROM dbo.etl_app_config "
            "WHERE config_key IN (?,?,?,?,?)", list(CHAVES))
        rows = dict(cur.fetchall())
    except Exception as e:
        cfg["erro"] = f"{type(e).__name__}: {str(e)[:300]}"
        return cfg
    if K_HABILITADO not in rows:
        return cfg
    cfg["disponivel"] = True
    cfg["enabled"] = str(rows.get(K_HABILITADO) or "").strip() == "1"
    cfg["remetente"] = str(rows.get(K_REMETENTE) or "").strip()
    limite, _ = em.validar_limite_anexo(rows.get(K_LIMITE_MB))
    cfg["limite_mb"] = limite or em.LIMITE_ANEXO_MB_PADRAO
    cfg["raizes"] = _lista_json(rows.get(K_RAIZES))
    cfg["dominios"] = _lista_json(rows.get(K_DOMINIOS))
    return cfg


def validar_config(body: dict) -> tuple[dict, list[str]]:
    """O que o admin manda → (valores normalizados por chave, erros).
    Ligar exige remetente válido (senão o canal 'ligado' não envia nada)."""
    erros: list[str] = []
    if not isinstance(body, dict):
        return {}, ["corpo inválido"]
    enabled = _bool(body.get("enabled"))
    if enabled is None:
        erros.append("enabled deve ser true/false")
        enabled = False
    remetente_raw = str(body.get("remetente") or "").strip()
    remetente = em.validar_email(remetente_raw) if remetente_raw else ""
    if remetente_raw and not remetente:
        erros.append("remetente inválido (um endereço de e-mail, sem quebras de linha)")
    if enabled and not remetente:
        erros.append("informe o remetente antes de ligar o canal de e-mail")
    limite, erro = em.validar_limite_anexo(body.get("limite_mb", em.LIMITE_ANEXO_MB_PADRAO))
    if erro:
        erros.append(erro)
    raizes, erros_r = em.validar_raizes(body.get("raizes"))
    erros.extend(erros_r)
    dominios, erros_d = em.validar_dominios(body.get("dominios"))
    erros.extend(erros_d)
    # `config_value` é VARCHAR(1000): o JSON das listas tem de caber, senão o
    # MERGE estoura com "String or binary data would be truncated" (500 opaco).
    # `ensure_ascii` padrão: JSON só-ASCII não depende da colação da coluna.
    raizes_json = json.dumps(raizes)
    dominios_json = json.dumps(dominios)
    if len(raizes_json) > LIMITE_VALOR:
        erros.append(f"raízes: lista longa demais ({len(raizes_json)} caracteres em JSON; limite {LIMITE_VALOR})")
    if len(dominios_json) > LIMITE_VALOR:
        erros.append(f"domínios: lista longa demais ({len(dominios_json)} caracteres em JSON; limite {LIMITE_VALOR})")
    valores = {
        K_HABILITADO: "1" if enabled else "0",
        K_REMETENTE: remetente or "",
        K_LIMITE_MB: str(limite or em.LIMITE_ANEXO_MB_PADRAO),
        K_RAIZES: raizes_json,
        K_DOMINIOS: dominios_json,
    }
    return valores, erros


def _bool(valor) -> bool | None:
    """Só booleano ou '0'/'1'/'true'/'false' (a API direta mandaria "false" e
    `bool("false")` ligaria o canal)."""
    if isinstance(valor, bool):
        return valor
    if valor is None:
        return False
    if isinstance(valor, (int, float)) and valor in (0, 1):
        return bool(valor)
    s = str(valor).strip().lower()
    if s in ("1", "true", "sim"):
        return True
    if s in ("0", "false", "nao", "não", ""):
        return False
    return None


def save_config(cur, valores: dict, requested_by: str) -> None:
    """MERGE por chave — o mesmo gesto das caixa_ia_* no admin."""
    for k, v in valores.items():
        if k not in CHAVES:
            continue
        cur.execute(
            "MERGE dbo.etl_app_config AS t USING (SELECT ? AS k) AS s ON t.config_key = s.k "
            "WHEN MATCHED THEN UPDATE SET config_value=?, updated_by=?, updated_at=GETDATE() "
            "WHEN NOT MATCHED THEN INSERT (config_key, config_value, descricao, updated_by, updated_at) "
            "  VALUES (s.k, ?, ?, ?, GETDATE());",
            (k, v, (requested_by or "")[:100], v, DESCRICAO, (requested_by or "")[:100]))
