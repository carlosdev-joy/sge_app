"""api/services/agentes.py — catálogo e RBAC da tela Agentes (F1 da spec
docs/spec-agentes-datastage.md).

O que mora aqui:

  • **o catálogo**, em código, não em tabela (decisão da spec — sem CRUD nem
    valor hoje): cada agente declara `perfis_elegiveis` e `concessao`. O
    agente `datastage` é `concessao='manual_por_usuario'`: nunca concedido
    por perfil, sempre usuário a usuário, pelo admin — reforçado por
    `require_agente()`, que ignora o recurso se ele vier de
    `etl_perfil_permissao` (só conta em `permissoes_extra`, a fatia que
    `carregar_usuario` já separa como overrides por usuário).
  • **`require_agente()`**: a dependency FastAPI que guarda cada endpoint de
    agente. Admin passa sempre (`acao_admin`) — é o mesmo "sempre tem todos
    os menus e acessos" que `require_ds_console` já aplica a outra tela.
  • **`identidade_gateway()`**: função pura — cadastro do usuário
    (`etl_usuario.identidade_gateway`) se preenchido, senão o padrão
    `cvp-<matrícula em minúsculas>`. Nunca decide sozinha se manda ou não
    chamar o gateway (quem decide é o chamador, ao ver `None`).

`tela_agentes` (a tela em si) NÃO tem tratamento especial aqui: é checada
direto por `require_perm('tela_agentes')` nos routers, como qualquer outra
tela — só os AGENTES (`agente_*`) precisam desta política extra.
"""
from __future__ import annotations

import re
import time

from fastapi import Depends, HTTPException

from deps import PERM_ADMIN, get_current_user

# ── Catálogo (código, não tabela) ───────────────────────────────────────────

AGENTE_DATASTAGE = "datastage"

CATALOGO: dict[str, dict] = {
    AGENTE_DATASTAGE: {
        "id": AGENTE_DATASTAGE,
        "nome": "Mapeamento DataStage",
        "descricao": (
            "Explica fluxos DataStage existentes: jobs, tabelas, campos, "
            "parâmetros e lineage. Leitura ao vivo sem alterar o DataStage; "
            "pode extrair ISX (com acao_editar do usuário) e consultar DSX."
        ),
        # Recurso concedido usuário a usuário (nunca por perfil — ver
        # require_agente). Config liga/desliga em `agente_datastage_enabled`.
        "recurso": "agente_datastage",
        "recurso_curador": "agente_curador",
        "config_enabled": "agente_datastage_enabled",
        "perfis_elegiveis": ("desenvolvedor",),
        "concessao": "manual_por_usuario",
    },
}


def agente(agente_id: str) -> dict | None:
    return CATALOGO.get(agente_id)


# ── RBAC por agente ──────────────────────────────────────────────────────────

def require_agente(agente_id: str, curador: bool = False):
    """Dependency FastAPI que guarda os endpoints de um agente.

    Admin passa sempre (`acao_admin`), sem grant — é a mesma regra de
    `deps.require_ds_console`. Não-admin precisa das DUAS coisas: perfil
    elegível E o recurso em `permissoes_extra` (não em `permissoes`, que
    inclui o que vem do PERFIL — um `agente_datastage` marcado num perfil
    pela tela genérica de Admin › Perfis não deve dar acesso a ninguém além
    do admin; é a defesa em profundidade da spec, risco 26)."""
    ag = CATALOGO.get(agente_id)
    if ag is None:
        raise ValueError(f"agente desconhecido no catálogo: {agente_id!r}")
    recurso = ag["recurso_curador"] if curador else ag["recurso"]

    async def _dep(user: dict = Depends(get_current_user)) -> dict:
        if PERM_ADMIN in user.get("permissoes", []):
            return user
        if user.get("perfil") not in ag["perfis_elegiveis"]:
            raise HTTPException(status_code=403, detail={
                "code": "agente_nao_elegivel",
                "message": f"Perfil '{user.get('perfil')}' não pode usar este agente"})
        if recurso not in user.get("permissoes_extra", []):
            raise HTTPException(status_code=403, detail={
                "code": "agente_nao_liberado",
                "message": "Agente não liberado para este usuário — peça ao administrador"})
        return user

    return _dep


def elegivel_por_perfil(agente_id: str, perfil: str) -> bool:
    """Só a elegibilidade de PERFIL — sem olhar grant nenhum. Usada pelo
    Admin (`user_perm_set`) para recusar (422) conceder `agente_*` a um
    perfil que nunca poderia usá-lo — a mesma régua de `require_agente`, do
    lado de quem concede. `perfil == 'admin'` é sempre elegível (ele já usa
    o agente por `acao_admin`; recusar o grant explícito seria só atrito)."""
    ag = CATALOGO.get(agente_id)
    if ag is None:
        return False
    return perfil == "admin" or perfil in ag["perfis_elegiveis"]


def agente_do_recurso(recurso: str) -> dict | None:
    """`agente_datastage`/`agente_curador` → o agente dono do recurso, ou
    None se `recurso` não é um recurso de agente (ex.: `tela_jobs`)."""
    for ag in CATALOGO.values():
        if recurso in (ag["recurso"], ag["recurso_curador"]):
            return ag
    return None


def catalogo_do_usuario(user: dict, config: dict[str, str]) -> list[dict]:
    """Agentes que `user` pode abrir: no catálogo, elegível (perfil+grant,
    admin sempre), e com os DOIS interruptores ligados (`agentes_enabled`
    geral e o do próprio agente). `config` é `{config_key: config_value}` já
    lido de etl_app_config (mesmas chaves que `_carregar_config` devolve)."""
    if (config.get("agentes_enabled") or "0") != "1":
        return []  # geral desligado: ninguém vê nada, nem o admin (padrão maestro_enabled)
    saida = []
    is_admin = PERM_ADMIN in user.get("permissoes", [])
    extras = set(user.get("permissoes_extra", []))
    for ag in CATALOGO.values():
        if (config.get(ag["config_enabled"]) or "0") != "1":
            continue
        liberado = is_admin or (
            user.get("perfil") in ag["perfis_elegiveis"] and ag["recurso"] in extras)
        if not liberado:
            continue
        saida.append({"id": ag["id"], "nome": ag["nome"], "descricao": ag["descricao"],
                      "curador": is_admin or ag["recurso_curador"] in extras})
    return saida


# ── Identidade no gateway (D-16) ────────────────────────────────────────────

# Vai em header (a maioria dos gateways não aceita espaço/quebra de linha em
# valor de header): letras, números e um punhado de separadores comuns em
# identificador corporativo (login, e-mail, matrícula com prefixo).
RE_IDENTIDADE_GATEWAY = re.compile(r"^[A-Za-z0-9._@-]{1,100}$")


CONFIG_DEFAULTS: dict[str, str] = {
    "agentes_enabled": "0",
    "agente_datastage_enabled": "0",
    # 'header:NOME' | 'body:CAMPO' — vazio = D-01 ainda não fechada, e a
    # sonda devolve sem_contrato sem chamar o gateway (ver ia_provedor).
    "agentes_gateway_campo_usuario": "",
    "agentes_cadastro_texto": "Solicite o cadastro no gateway de IA ao administrador.",
    "agentes_ssh_max": "10",
    "agentes_fato_validade_dias": "7",
}


def carregar_config(cur) -> dict[str, str]:
    """Lê as chaves `agentes_*`/`agente_*_enabled` de etl_app_config, com os
    padrões de `CONFIG_DEFAULTS` quando ausentes. Degrada graciosamente
    (tudo desligado) se a tabela ou a migration 117 ainda não existirem —
    mesmo espírito de `ia_provedor.load_config`."""
    valores = dict(CONFIG_DEFAULTS)
    try:
        chaves = list(CONFIG_DEFAULTS)
        marcadores = ",".join("?" * len(chaves))
        cur.execute(
            f"SELECT config_key, config_value FROM dbo.etl_app_config WHERE config_key IN ({marcadores})",
            chaves)
        for k, v in cur.fetchall():
            if v is not None and str(v).strip():
                valores[k] = str(v).strip()
    except Exception:
        pass
    return valores


def identidade_gateway(matricula: str, cadastro: str | None) -> str | None:
    """O identificador a enviar ao gateway: o CADASTRO do usuário
    (`etl_usuario.identidade_gateway`) se preenchido; senão o padrão
    `cvp-<matrícula em minúsculas>` (o banco grava a matrícula em MAIÚSCULAS
    — `auth.py:38` — por isso o `.lower()` aqui é obrigatório). Sem
    matrícula, devolve None: quem chama NUNCA cai para `cvp-orquestra` (isso
    faria o usuário agir como o app e anularia a autorização por usuário)."""
    if cadastro and cadastro.strip():
        return cadastro.strip()
    mat = (matricula or "").strip()
    if not mat:
        return None
    return f"cvp-{mat.lower()}"


# ── Cache da sonda (D-03: TTL por estado) ───────────────────────────────────
#
# Em memória do processo, por matrícula (a sonda é sobre o CADASTRO do
# usuário no gateway — não muda por agente). `ok` guarda por mais tempo
# porque cadastro não vai e volta; `sem_cadastro` guarda pouco para o botão
# "verificar de novo" fazer sentido logo depois que a pessoa se cadastra;
# `gateway_indisponivel` (e qualquer estado fora do mapa) NUNCA é cacheado —
# uma queda momentânea do gateway não pode virar "sem cadastro" por 10 min.
_TTL_POR_ESTADO_S = {"ok": 600, "sem_cadastro": 60}

_sonda_cache: dict[str, tuple[str, float]] = {}


def sonda_cacheada(matricula: str) -> str | None:
    item = _sonda_cache.get(matricula)
    if item is None:
        return None
    estado, expira_em = item
    if time.monotonic() >= expira_em:
        _sonda_cache.pop(matricula, None)
        return None
    return estado


def guardar_sonda(matricula: str, estado: str) -> None:
    ttl = _TTL_POR_ESTADO_S.get(estado)
    if not ttl:
        _sonda_cache.pop(matricula, None)
        return
    _sonda_cache[matricula] = (estado, time.monotonic() + ttl)


def invalidar_sonda(matricula: str) -> None:
    """Chamado quando o admin muda `identidade_gateway` de alguém (ação
    `user_identidade_set`, admin.py): o estado cacheado descrevia o
    identificador ANTIGO."""
    _sonda_cache.pop(matricula, None)
