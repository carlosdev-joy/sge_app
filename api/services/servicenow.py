"""api/services/servicenow.py — configuração da integração com o ServiceNow.

Config em dbo.etl_app_config (chaves `servicenow_*`), gerida em Admin >
ServiceNow. A senha é cifrada com o mesmo Fernet das conexões
(services/conn_crypto, ORQUESTRA_CONN_KEY) — a MESMA chave precisa estar no
orquestra-api e nos containers do Airflow, porque a DAG de sync decifra a
credencial para executar.

Por que a credencial mora aqui e não numa Airflow Connection: a tela de Admin
já edita e mascara valores de `etl_app_config`, e a DAG já lê config do banco.
Um lugar só, com RBAC e auditoria de quem mudou (decisão registrada na spec).

O `url` guardado é a instância; `grupos` é a lista de grupos de atribuição
separada por `;` (a fila da engenharia pode ser mais de um).
"""
from __future__ import annotations

import os

from fastapi import HTTPException

from db import get_db_conn

# Chaves em dbo.etl_app_config (migration 088)
K_URL         = "servicenow_url"
K_USUARIO     = "servicenow_usuario"
K_SENHA       = "servicenow_senha_enc"   # Fernet
K_GRUPOS      = "servicenow_grupos"
K_HABILITADO  = "servicenow_habilitado"  # '1' | '0'

TODAS_AS_CHAVES = (K_URL, K_USUARIO, K_SENHA, K_GRUPOS, K_HABILITADO)

# Tabelas do ServiceNow que o espelho cobre.
TABELAS = ("incident", "sc_req_item", "sc_task", "change_request")


def url_valida(url: str) -> str:
    """Só instância https de *.service-now.com.

    Guarda anti-SSRF: quem chama faz GET autenticado para onde este valor
    mandar — e o valor vem de um campo de formulário.
    """
    u = (url or "").strip().rstrip("/")
    if not u.startswith("https://"):
        raise HTTPException(status_code=422, detail="URL deve começar com https://")
    host = u[len("https://"):].split("/")[0]
    if not host.endswith(".service-now.com"):
        raise HTTPException(status_code=422,
                            detail="só instâncias *.service-now.com são aceitas")
    return u


def parse_grupos(bruto: str) -> list[str]:
    """'A; B ;;C' → ['A', 'B', 'C']. Sem grupo = sem filtro de fila."""
    return [g.strip() for g in (bruto or "").split(";") if g.strip()]


def load_config(cur=None) -> dict:
    """Lê a config servicenow_* de etl_app_config.

    Degrada graciosamente (habilitado=False, campos vazios) se a tabela ou as
    chaves ainda não existirem — ambiente sem a migration 088 não pode
    derrubar o Admin inteiro, só mostrar a integração desconfigurada.
    """
    own_conn = cur is None
    conn = None
    cfg = {"url": "", "usuario": "", "senha_enc": "", "grupos": "",
           "habilitado": False}
    try:
        if own_conn:
            conn = get_db_conn(); cur = conn.cursor()
        marcadores = ",".join("?" for _ in TODAS_AS_CHAVES)
        cur.execute(
            f"SELECT config_key, config_value FROM dbo.etl_app_config "
            f"WHERE config_key IN ({marcadores})", list(TODAS_AS_CHAVES))
        linhas = dict(cur.fetchall())
        cfg["url"]        = (linhas.get(K_URL) or "").strip().rstrip("/")
        cfg["usuario"]    = (linhas.get(K_USUARIO) or "").strip()
        cfg["senha_enc"]  = (linhas.get(K_SENHA) or "").strip()
        cfg["grupos"]     = (linhas.get(K_GRUPOS) or "").strip()
        cfg["habilitado"] = (linhas.get(K_HABILITADO) or "").strip() == "1"
    except Exception:
        pass  # tabela/chaves ausentes → config vazia, dita na tela
    finally:
        if own_conn and conn is not None:
            try:
                cur.close(); conn.close()
            except Exception:
                pass
    return cfg


def configurado(cfg: dict) -> bool:
    """Tem o mínimo para executar um sync: instância, usuário e senha."""
    return bool(cfg.get("url") and cfg.get("usuario") and cfg.get("senha_enc"))


def credencial_executora(cfg: dict) -> tuple[str, str, str]:
    """(url, usuario, senha_em_claro) para quem vai chamar a API.

    Falha com mensagem que NOMEIA o que falta: "integração não configurada"
    e "chave de cifra ausente" são problemas diferentes com o mesmo sintoma
    (sync que não roda), e quem opera precisa saber qual dos dois é.
    """
    from services.conn_crypto import decrypt_password
    if not configurado(cfg):
        faltando = [nome for nome, valor in
                    (("URL da instância", cfg.get("url")),
                     ("usuário", cfg.get("usuario")),
                     ("senha", cfg.get("senha_enc"))) if not valor]
        raise HTTPException(
            status_code=422,
            detail=("ServiceNow não configurado — falta " + ", ".join(faltando)
                    + ". Preencha em Admin > ServiceNow."))
    return cfg["url"], cfg["usuario"], decrypt_password(cfg["senha_enc"])


def proxy_efetivo(cli, url: str) -> dict:
    """O proxy que o httpx REALMENTE vai usar para esta URL.

    Lê do transporte já resolvido em vez de reimplementar a regra: com
    trust_env (o padrão) o httpx monta HTTPS_PROXY/HTTP_PROXY e aplica o
    NO_PROXY sozinho, e uma segunda implementação aqui divergiria em
    silêncio. Existe para a tela conseguir dizer POR QUE não há proxy —
    variável ausente e host isento são causas opostas com o mesmo sintoma.
    """
    import httpx
    configurado_env = (os.environ.get("HTTPS_PROXY")
                       or os.environ.get("https_proxy") or "").strip()
    try:
        pool = getattr(cli._transport_for_url(httpx.URL(url)), "_pool", None)
        alvo = getattr(pool, "_proxy_url", None)
    except Exception:            # API interna do httpx mudou — não derruba a sonda
        return {"em_uso": None, "motivo": "não foi possível determinar"}
    if alvo:
        return {"em_uso": str(alvo), "motivo": None}
    if configurado_env:
        return {"em_uso": None,
                "motivo": f"host isento pelo NO_PROXY (HTTPS_PROXY={configurado_env})"}
    return {"em_uso": None,
            "motivo": "HTTPS_PROXY não definida no container — conexão direta"}
