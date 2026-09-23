"""api/services/agentes.py — catálogo, RBAC por agente e identidade no
gateway (F1 da spec docs/spec-agentes-datastage.md).

O que estes testes prendem, e por que cada um existe:

  1. **`identidade_gateway`**: cadastro sempre vence; sem cadastro, o padrão
     é a matrícula em MINÚSCULAS com o prefixo `cvp-` (o banco grava a
     matrícula em MAIÚSCULAS — `auth.py:38`); sem matrícula, `None` — nunca
     um fallback fixo tipo `cvp-orquestra`.

  2. **`require_agente`**: admin passa sempre; não-admin precisa de perfil
     elegível **e** do recurso em `permissoes_extra` — não basta estar em
     `permissoes` (que inclui o que vem do PERFIL). É a defesa em
     profundidade contra conceder por engano na tela de perfis (risco 26).

  3. **`catalogo_do_usuario`**: os DOIS interruptores (geral e do agente)
     precisam estar ligados; sem o geral, nem o admin vê nada — mesmo
     espírito de `maestro_enabled`.

  4. **`carregar_config`**: nunca levanta — degrada para os padrões se a
     tabela/migration não existir.

  5. **A cache da sonda**: TTL por estado, e o estado que significa "não sei
     o que houve" (fora do mapa de TTL) nunca é guardado — senão uma queda
     momentânea do gateway vira "sem cadastro" por minutos.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()
os.environ.setdefault("MSSQL_CONN_STR", "__mock__")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))

from deps import PERM_ADMIN  # noqa: E402
from services import agentes as svc  # noqa: E402


def _user(perfil, extras=None, admin=False):
    permissoes = [PERM_ADMIN] if admin else []
    return {"matricula": "U1", "perfil": perfil, "permissoes": permissoes,
            "permissoes_extra": list(extras or [])}


# ═══════════ 1. identidade_gateway ═══════════════════════════════════════════

def test_identidade_usa_o_cadastro_quando_preenchido():
    assert svc.identidade_gateway("CVP1234", "usuario.custom@caixa") == "usuario.custom@caixa"


def test_identidade_cadastro_com_espacos_e_cortado():
    assert svc.identidade_gateway("CVP1234", "  usuario.custom@caixa  ") == "usuario.custom@caixa"


def test_identidade_sem_cadastro_usa_matricula_em_minusculas():
    assert svc.identidade_gateway("CVP1234", None) == "cvp-cvp1234"
    assert svc.identidade_gateway("CVP1234", "") == "cvp-cvp1234"
    assert svc.identidade_gateway("CVP1234", "   ") == "cvp-cvp1234"


def test_identidade_sem_matricula_e_none():
    assert svc.identidade_gateway("", None) is None
    assert svc.identidade_gateway(None, None) is None  # type: ignore[arg-type]


def test_identidade_nunca_cai_para_cvp_orquestra():
    """Não existe caminho que devolva 'cvp-orquestra' — a função só conhece
    o cadastro e a matrícula do PRÓPRIO usuário."""
    for matricula, cadastro in [("", None), (None, None), ("X", None), ("X", "y")]:
        assert svc.identidade_gateway(matricula, cadastro) != "cvp-orquestra"


# ═══════════ 2. require_agente ═══════════════════════════════════════════════

@pytest.mark.asyncio
async def test_require_agente_admin_passa_sem_grant():
    dep = svc.require_agente(svc.AGENTE_DATASTAGE)
    user = _user("consulta", admin=True)  # nem perfil elegível, nem grant
    assert await dep(user=user) is user


@pytest.mark.asyncio
async def test_require_agente_desenvolvedor_com_grant_passa():
    dep = svc.require_agente(svc.AGENTE_DATASTAGE)
    user = _user("desenvolvedor", extras=["agente_datastage"])
    assert await dep(user=user) is user


@pytest.mark.asyncio
async def test_require_agente_desenvolvedor_sem_grant_e_403_liberado():
    dep = svc.require_agente(svc.AGENTE_DATASTAGE)
    with pytest.raises(HTTPException) as exc:
        await dep(user=_user("desenvolvedor", extras=[]))
    assert exc.value.status_code == 403
    assert exc.value.detail["code"] == "agente_nao_liberado"


@pytest.mark.asyncio
async def test_require_agente_perfil_nao_elegivel_e_403_mesmo_com_grant():
    dep = svc.require_agente(svc.AGENTE_DATASTAGE)
    with pytest.raises(HTTPException) as exc:
        await dep(user=_user("consulta", extras=["agente_datastage"]))
    assert exc.value.status_code == 403
    assert exc.value.detail["code"] == "agente_nao_elegivel"


@pytest.mark.asyncio
async def test_require_agente_ignora_recurso_vindo_so_do_perfil():
    """Defesa em profundidade (risco 26): o recurso em `permissoes` (que
    inclui o herdado do PERFIL) não basta — só `permissoes_extra` conta."""
    dep = svc.require_agente(svc.AGENTE_DATASTAGE)
    user = {"matricula": "U1", "perfil": "desenvolvedor",
            "permissoes": ["agente_datastage"],  # veio do perfil, não de um grant
            "permissoes_extra": []}
    with pytest.raises(HTTPException) as exc:
        await dep(user=user)
    assert exc.value.detail["code"] == "agente_nao_liberado"


@pytest.mark.asyncio
async def test_require_agente_curador_e_um_recurso_diferente():
    dep_curador = svc.require_agente(svc.AGENTE_DATASTAGE, curador=True)
    # tem o grant do agente mas NÃO o de curador → segue barrado
    with pytest.raises(HTTPException):
        await dep_curador(user=_user("desenvolvedor", extras=["agente_datastage"]))
    # com o grant de curador, passa
    ok = await dep_curador(user=_user("desenvolvedor", extras=["agente_curador"]))
    assert ok["matricula"] == "U1"


def test_require_agente_id_desconhecido_levanta_na_construcao():
    with pytest.raises(ValueError):
        svc.require_agente("nao-existe")


# ═══════════ 3. elegivel_por_perfil / agente_do_recurso ══════════════════════

@pytest.mark.parametrize("perfil,esperado", [
    ("desenvolvedor", True), ("admin", True),
    ("consulta", False), ("operador", False), ("perfil-que-nao-existe", False),
])
def test_elegivel_por_perfil(perfil, esperado):
    assert svc.elegivel_por_perfil(svc.AGENTE_DATASTAGE, perfil) is esperado


def test_elegivel_por_perfil_agente_desconhecido_e_falso():
    assert svc.elegivel_por_perfil("nao-existe", "admin") is False


def test_agente_do_recurso_reconhece_os_dois_recursos():
    assert svc.agente_do_recurso("agente_datastage")["id"] == svc.AGENTE_DATASTAGE
    assert svc.agente_do_recurso("agente_curador")["id"] == svc.AGENTE_DATASTAGE


def test_agente_do_recurso_recurso_comum_e_none():
    assert svc.agente_do_recurso("tela_jobs") is None
    assert svc.agente_do_recurso("acao_editar") is None


# ═══════════ 4. catalogo_do_usuario ═══════════════════════════════════════════

_CFG_LIGADO = {"agentes_enabled": "1", "agente_datastage_enabled": "1"}


@pytest.mark.parametrize("cfg, esperado", [
    (_CFG_LIGADO, True),
    ({"agentes_enabled": "0", "agente_datastage_enabled": "1"}, False),
    ({"agentes_enabled": "1", "agente_datastage_enabled": "0"}, False),
    ({"agentes_enabled": "1"}, False),   # chave ausente = desligado
    ({"agentes_enabled": "1", "agente_datastage_enabled": None}, False),
    ({}, False),
])
def test_agente_ligado_exige_os_dois_interruptores(cfg, esperado):
    """A regra única usada pelo catálogo, pelo chat e pela curadoria."""
    assert svc.agente_ligado(cfg, svc.AGENTE_DATASTAGE) is esperado


def test_agente_ligado_agente_desconhecido_e_false():
    assert svc.agente_ligado(_CFG_LIGADO, "nao_existe") is False


def test_catalogo_geral_desligado_admin_tambem_nao_ve_nada():
    cfg = {"agentes_enabled": "0", "agente_datastage_enabled": "1"}
    assert svc.catalogo_do_usuario(_user("admin", admin=True), cfg) == []


def test_catalogo_agente_desligado_fica_de_fora():
    cfg = {"agentes_enabled": "1", "agente_datastage_enabled": "0"}
    assert svc.catalogo_do_usuario(_user("desenvolvedor", extras=["agente_datastage"]), cfg) == []


def test_catalogo_admin_ve_com_tudo_ligado():
    lista = svc.catalogo_do_usuario(_user("admin", admin=True), _CFG_LIGADO)
    assert len(lista) == 1 and lista[0]["id"] == svc.AGENTE_DATASTAGE
    assert lista[0]["curador"] is True  # admin também é curador, sem grant


def test_catalogo_desenvolvedor_com_grant_ve_sem_grant_nao_ve():
    com_grant = svc.catalogo_do_usuario(_user("desenvolvedor", extras=["agente_datastage"]), _CFG_LIGADO)
    assert len(com_grant) == 1
    assert com_grant[0]["curador"] is False

    sem_grant = svc.catalogo_do_usuario(_user("desenvolvedor", extras=[]), _CFG_LIGADO)
    assert sem_grant == []


def test_catalogo_perfil_nao_elegivel_nao_ve_mesmo_com_grant_forcado():
    cfg_forcada = svc.catalogo_do_usuario(_user("consulta", extras=["agente_datastage"]), _CFG_LIGADO)
    assert cfg_forcada == []


def test_catalogo_curador_flag_reflete_o_grant():
    lista = svc.catalogo_do_usuario(
        _user("desenvolvedor", extras=["agente_datastage", "agente_curador"]), _CFG_LIGADO)
    assert lista[0]["curador"] is True


# ═══════════ 5. carregar_config ═══════════════════════════════════════════════

class _CurConfig:
    def __init__(self, linhas):
        self._linhas = linhas

    def execute(self, sql, params=None):
        pass

    def fetchall(self):
        return self._linhas


def test_carregar_config_usa_padroes_quando_vazio():
    cfg = svc.carregar_config(_CurConfig([]))
    assert cfg == svc.CONFIG_DEFAULTS


def test_carregar_config_sobrescreve_com_o_banco():
    cfg = svc.carregar_config(_CurConfig([("agentes_enabled", "1"), ("agentes_ssh_max", "5")]))
    assert cfg["agentes_enabled"] == "1"
    assert cfg["agentes_ssh_max"] == "5"
    assert cfg["agente_datastage_enabled"] == svc.CONFIG_DEFAULTS["agente_datastage_enabled"]


def test_carregar_config_ignora_valor_vazio_do_banco():
    """config_value = '' não deve VENCER o padrão — é 'não configurado'."""
    cfg = svc.carregar_config(_CurConfig([("agentes_ssh_max", "")]))
    assert cfg["agentes_ssh_max"] == svc.CONFIG_DEFAULTS["agentes_ssh_max"]


def test_carregar_config_nunca_levanta():
    class _Explode:
        def execute(self, *a, **k):
            raise RuntimeError("tabela ausente — migration 117 não rodou")
    assert svc.carregar_config(_Explode()) == svc.CONFIG_DEFAULTS


# ═══════════ 6. cache da sonda ════════════════════════════════════════════════

def test_sonda_cache_guarda_e_le():
    svc.guardar_sonda("T1", "ok")
    assert svc.sonda_cacheada("T1") == "ok"


def test_sonda_cache_estado_sem_ttl_nao_e_guardado():
    svc.guardar_sonda("T2", "gateway_indisponivel")
    assert svc.sonda_cacheada("T2") is None


def test_sonda_cache_expira(monkeypatch):
    agora = [1000.0]
    monkeypatch.setattr(svc.time, "monotonic", lambda: agora[0])
    svc.guardar_sonda("T3", "sem_cadastro")  # TTL 60s
    assert svc.sonda_cacheada("T3") == "sem_cadastro"
    agora[0] += 61
    assert svc.sonda_cacheada("T3") is None


def test_invalidar_sonda_limpa_a_entrada():
    svc.guardar_sonda("T4", "ok")
    assert svc.sonda_cacheada("T4") == "ok"
    svc.invalidar_sonda("T4")
    assert svc.sonda_cacheada("T4") is None


def test_invalidar_sonda_matricula_sem_cache_nao_quebra():
    svc.invalidar_sonda("NUNCA-TEVE-CACHE")  # não levanta
