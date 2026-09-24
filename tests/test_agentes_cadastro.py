"""Cadastro de agentes pela tela (B1 de docs/spec-agentes-admin.md §4.1–§4.4).

O que se prende, e por quê:

  1. **Validação da criação/alteração** — id (formato, reservados, inclusive
     `curador`/`*_curador`), ferramentas só da allowlist (com `resolver_projeto`
     automático), acesso por perfil nunca com ferramenta de servidor, perfil
     `consulta` nunca, perfis existentes, textos sem marcador de protocolo.
  2. **Acesso numa régua só** (`motivo_sem_acesso`) — manual × perfil, tela
     exigida para agente do banco, curadoria só com ferramentas e grant.
  3. **Recursos sem colisão** — o mapa recurso → (agente, papel) é exato.
  4. **Interruptores** — `agentes_enabled` derruba todos; `ativo` o do banco.
  5. **Prompt pelo subconjunto** — partes fixas só com o que o agente tem.
  6. **Rotas** — criar (desativado, prompt v1 na mesma transação), alterar
     (parcial, combinação final validada), 409 para o agente do código, só
     admin; catálogo, histórico, status e prompt enxergam o agente do banco;
     `user_perm_set` valida o grant do agente do banco.
  7. **O DataStage não muda** — o prompt montado é o mesmo (os testes da A0/A1
     prendem o texto) e as regras de acesso dele também.
"""
from __future__ import annotations

import copy
import datetime as dt
import json
import os
import re
import sys
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()
os.environ.setdefault("MSSQL_CONN_STR", "__mock__")
from api.main import app as _app  # noqa: F401,E402

from deps import PERM_ADMIN, get_current_user  # noqa: E402
from services import agentes as svc  # noqa: E402
from services import agentes_registro as reg  # noqa: E402
from tests.test_agentes_prompt_versoes import _BancoPrompt, _CursorPrompt  # noqa: E402

PERFIS = {"admin", "desenvolvedor", "operador", "consulta", "analista"}


def _linha(agente_id="assistente", *, nome="Assistente", descricao="Tira dúvidas", acesso="manual",
           perfis=("desenvolvedor",), ferramentas=(), ativo=True):
    agora = dt.datetime(2026, 9, 23, 10, 0, 0)
    return (agente_id, nome, descricao, acesso, json.dumps(list(perfis)), json.dumps(list(ferramentas)),
            1 if ativo else 0, agora, "ADM1", agora, "ADM1")


def _reg(*linhas) -> dict[str, dict]:
    agentes = dict(svc.CATALOGO)
    for r in linhas:
        ag = reg.do_banco(r)
        agentes[ag["id"]] = ag
    return agentes


def _user(perfil="desenvolvedor", *, extras=(), tela=True, admin=False):
    perms = (["tela_agentes"] if tela else []) + ([PERM_ADMIN] if admin else [])
    return {"matricula": "U1", "perfil": perfil, "permissoes": perms, "permissoes_extra": list(extras)}


def _corpo(**kw):
    base = {"id": "assistente", "nome": "Assistente", "descricao": "Tira dúvidas da equipe",
            "acesso": "manual", "perfis": ["desenvolvedor"], "ferramentas": [],
            "prompt": "Você é o assistente da equipe de dados.", "motivo": "criação"}
    base.update(kw)
    return base


# ═══════════ 1. validação ═════════════════════════════════════════════════

@pytest.mark.parametrize("agente_id", ["ab", "A_maiusc", "1comeca_numero", "com-hifen", "x" * 31, "", None, 5])
def test_id_com_formato_invalido(agente_id):
    with pytest.raises(reg.AgenteInvalido) as e:
        reg.validar_criacao(_corpo(id=agente_id), PERFIS)
    assert e.value.code == "agente_id_invalido"


@pytest.mark.parametrize("agente_id", ["datastage", "admin", "catalogo", "status", "conversas", "propostas",
                                       "aprendizados", "curador", "foo_curador"])
def test_id_reservado(agente_id):
    with pytest.raises(reg.AgenteInvalido) as e:
        reg.validar_criacao(_corpo(id=agente_id), PERFIS)
    assert e.value.code == "agente_id_reservado"


def test_ferramentas_so_da_allowlist_e_resolver_projeto_automatico():
    with pytest.raises(reg.AgenteInvalido) as e:
        reg.validar_criacao(_corpo(ferramentas=["dsjob", "rm_rf"]), PERFIS)
    assert e.value.code == "ferramentas_invalidas"
    assert reg.validar_criacao(_corpo(ferramentas=["base"]), PERFIS)["ferramentas"] == ["resolver_projeto", "base"]
    assert reg.validar_criacao(_corpo(ferramentas=["isx_extrair", "base", "base"]), PERFIS)["ferramentas"] == \
        ["resolver_projeto", "base", "isx_extrair"]
    assert reg.validar_criacao(_corpo(ferramentas=[]), PERFIS)["ferramentas"] == []


@pytest.mark.parametrize("ferramentas", [["dsjob"], ["isx_extrair"], ["dsx_consulta"], ["base", "dsjob"]])
def test_acesso_por_perfil_nunca_com_ferramenta_de_servidor(ferramentas):
    with pytest.raises(reg.AgenteInvalido) as e:
        reg.validar_criacao(_corpo(acesso="perfil", ferramentas=ferramentas), PERFIS)
    assert e.value.code == "acesso_perfil_com_servidor"


@pytest.mark.parametrize("ferramentas", [[], ["base"], ["resolver_projeto"]])
def test_acesso_por_perfil_sem_servidor_passa(ferramentas):
    assert reg.validar_criacao(_corpo(acesso="perfil", ferramentas=ferramentas), PERFIS)["acesso"] == "perfil"


@pytest.mark.parametrize("perfis, code", [
    (["consulta"], "perfil_nao_permitido"), (["desenvolvedor", "consulta"], "perfil_nao_permitido"),
    (["inexistente"], "perfil_desconhecido"), ([], "perfis_obrigatorios"), (None, "perfis_obrigatorios"),
    ([""], "perfis_obrigatorios"), ([1], "perfis_obrigatorios"),
])
def test_perfis_invalidos(perfis, code):
    with pytest.raises(reg.AgenteInvalido) as e:
        reg.validar_criacao(_corpo(perfis=perfis), PERFIS)
    assert e.value.code == code


@pytest.mark.parametrize("campo, valor, code", [
    ("nome", "", "nome_obrigatorio"), ("nome", "x" * 101, "nome_grande"), ("nome", "😀" * 51, "nome_grande"),
    ("descricao", "x" * 501, "descricao_grande"), ("descricao", 'use {"ferramenta": "x"}', "texto_com_marcador"),
    ("acesso", "todos", "acesso_invalido"), ("acesso", None, "acesso_invalido"),
    ("prompt", "", "prompt_vazio"), ("prompt", "senha=Abc123", "prompt_com_segredo"),
    ("motivo", "x", "motivo_obrigatorio"),
])
def test_campos_invalidos(campo, valor, code):
    with pytest.raises(reg.AgenteInvalido) as e:
        reg.validar_criacao(_corpo(**{campo: valor}), PERFIS)
    assert e.value.code == code


def test_alteracao_parcial_valida_a_combinacao_final():
    atual = reg.do_banco(_linha(ferramentas=["resolver_projeto", "dsjob"]))
    with pytest.raises(reg.AgenteInvalido) as e:
        reg.validar_alteracao(atual, {"acesso": "perfil"}, PERFIS)
    assert e.value.code == "acesso_perfil_com_servidor"
    novo = reg.validar_alteracao(atual, {"acesso": "perfil", "ferramentas": []}, PERFIS)
    assert novo["acesso"] == "perfil" and novo["ferramentas"] == [] and novo["nome"] == "Assistente"


@pytest.mark.parametrize("body, code", [
    ({"id": "outro"}, "campo_nao_alteravel"), ({"criado_por": "X"}, "campo_nao_alteravel"),
    ({}, "nada_para_alterar"), ({"ativo": "1"}, "ativo_invalido"), ({"ativo": 1}, "ativo_invalido"),
    ({"perfis": ["consulta"]}, "perfil_nao_permitido"),
])
def test_alteracao_invalida(body, code):
    with pytest.raises(reg.AgenteInvalido) as e:
        reg.validar_alteracao(reg.do_banco(_linha()), body, PERFIS)
    assert e.value.code == code


def test_linha_editada_a_mao_no_banco_nao_amplia_nada():
    """Ferramenta fora da allowlist e o perfil `consulta` gravados direto no
    banco são descartados na carga — a regra do código manda."""
    ag = reg.do_banco(_linha(perfis=("desenvolvedor", "consulta"), ferramentas=("dsjob", "shell_livre")))
    assert ag["ferramentas"] == ("resolver_projeto", "dsjob") and ag["perfis_elegiveis"] == ("desenvolvedor",)


# ═══════════ 2. acesso numa régua só ══════════════════════════════════════

def test_acesso_manual_exige_grant():
    ag = reg.do_banco(_linha(acesso="manual"))
    assert svc.motivo_sem_acesso(_user(), ag)[0] == "agente_nao_liberado"
    assert svc.motivo_sem_acesso(_user(extras=["agente_assistente"]), ag) is None


def test_acesso_por_perfil_dispensa_grant_so_para_perfil_elegivel():
    ag = reg.do_banco(_linha(acesso="perfil", perfis=("desenvolvedor", "analista")))
    assert svc.motivo_sem_acesso(_user("analista"), ag) is None
    assert svc.motivo_sem_acesso(_user("operador"), ag)[0] == "agente_nao_elegivel"
    assert svc.motivo_sem_acesso(_user("consulta"), ag)[0] == "agente_nao_elegivel"


def test_agente_do_banco_exige_a_tela_agentes():
    ag = reg.do_banco(_linha(acesso="perfil"))
    assert svc.motivo_sem_acesso(_user(tela=False), ag)[0] == "agente_sem_tela"
    # o DataStage continua como antes: a tela é conferida pela rota, não aqui
    assert svc.motivo_sem_acesso(_user(tela=False, extras=["agente_datastage"]), svc.CATALOGO["datastage"]) is None


def test_admin_passa_sempre():
    ag = reg.do_banco(_linha(acesso="manual"))
    assert svc.motivo_sem_acesso(_user("admin", tela=False, admin=True), ag) is None


def test_curadoria_so_com_ferramentas_e_grant():
    so_conversa = reg.do_banco(_linha())
    assert so_conversa["recurso_curador"] is None
    assert svc.motivo_sem_acesso(_user(extras=["agente_assistente", "agente_assistente_curador"]),
                                 so_conversa, curador=True)[0] == "agente_nao_liberado"
    com = reg.do_banco(_linha(ferramentas=("resolver_projeto", "base")))
    assert com["recurso_curador"] == "agente_assistente_curador"
    assert svc.motivo_sem_acesso(_user(extras=["agente_assistente_curador"]), com, curador=True) is None
    # por perfil não dá curadoria: o grant do curador é sempre manual
    por_perfil = reg.do_banco(_linha(acesso="perfil", ferramentas=("resolver_projeto", "base")))
    assert svc.motivo_sem_acesso(_user(), por_perfil, curador=True)[0] == "agente_nao_liberado"


def test_datastage_mantem_as_regras_de_sempre():
    ds = svc.CATALOGO["datastage"]
    assert svc.motivo_sem_acesso(_user(), ds)[0] == "agente_nao_liberado"
    assert svc.motivo_sem_acesso(_user("operador", extras=["agente_datastage"]), ds)[0] == "agente_nao_elegivel"
    assert svc.motivo_sem_acesso(_user(extras=["agente_datastage"]), ds) is None
    assert svc.motivo_sem_acesso(_user(extras=["agente_curador"]), ds, curador=True) is None


# ═══════════ 3. recursos sem colisão ══════════════════════════════════════

def test_mapa_de_recursos_exato():
    agentes = _reg(_linha("assistente", ferramentas=("base",)), _linha("outro"))
    mapa = svc.mapa_de_recursos(agentes)
    assert mapa["agente_curador"][0]["id"] == "datastage" and mapa["agente_curador"][1] == "curador"
    assert mapa["agente_assistente"][1] == "uso"
    assert mapa["agente_assistente_curador"][1] == "curador"
    assert "agente_outro_curador" not in mapa  # só conversa: sem curadoria
    assert svc.agente_do_recurso("agente_outro", agentes)["id"] == "outro"
    assert svc.agente_do_recurso("tela_jobs", agentes) is None


def test_recurso_repetido_e_erro_de_carga():
    agentes = _reg(_linha("assistente"))
    agentes["dup"] = {**agentes["assistente"], "id": "dup"}
    with pytest.raises(ValueError):
        svc.mapa_de_recursos(agentes)


def test_elegibilidade_para_o_grant():
    agentes = _reg(_linha(perfis=("analista",)))
    assert svc.elegivel_por_perfil("assistente", "analista", agentes)
    assert not svc.elegivel_por_perfil("assistente", "desenvolvedor", agentes)
    assert svc.elegivel_por_perfil("assistente", "admin", agentes)
    assert not svc.elegivel_por_perfil("assistente", "consulta", agentes)


# ═══════════ 4. interruptores e catálogo ══════════════════════════════════

LIGADO = {"agentes_enabled": "1", "agente_datastage_enabled": "1"}


def test_interruptores_do_agente_do_banco():
    agentes = _reg(_linha(ativo=True), _linha("parado", ativo=False))
    assert svc.agente_ligado(LIGADO, "assistente", agentes)
    assert not svc.agente_ligado(LIGADO, "parado", agentes)
    assert not svc.agente_ligado({**LIGADO, "agentes_enabled": "0"}, "assistente", agentes)
    assert not svc.agente_ligado(LIGADO, "nao_existe", agentes)


def test_catalogo_hibrido():
    agentes = _reg(_linha(acesso="perfil", ferramentas=()), _linha("parado", acesso="perfil", ativo=False))
    ids = [a["id"] for a in svc.catalogo_do_usuario(_user(extras=["agente_datastage"]), LIGADO, agentes)]
    assert ids == ["datastage", "assistente"]
    item = next(a for a in svc.catalogo_do_usuario(_user(), LIGADO, agentes) if a["id"] == "assistente")
    assert item["ferramentas"] == [] and item["curador"] is False
    assert svc.catalogo_do_usuario(_user(tela=False), LIGADO, agentes) == []
    assert svc.catalogo_do_usuario(_user(admin=True), {**LIGADO, "agentes_enabled": "0"}, agentes) == []


def test_sem_registro_o_catalogo_e_o_de_antes():
    assert [a["id"] for a in svc.catalogo_do_usuario(_user(admin=True), LIGADO)] == ["datastage"]


# ═══════════ 5. prompt pelo subconjunto ═══════════════════════════════════

def test_so_conversa_so_tem_as_regras_genericas():
    antes, depois = svc.partes_fixas("P", False, ())
    assert antes == ""
    assert depois.startswith("## Regras que valem sempre") and "DataStage" not in depois
    assert "ferramenta" not in depois.lower().replace("não tem ferramentas", "")
    assert "senha, token ou credencial" in depois


def test_so_base_nao_tem_propostas_mas_tem_a_regra_de_credencial():
    antes, depois = svc.partes_fixas(None, False, ("resolver_projeto", "base"))
    assert "Antes de usar 'base', pergunte" in antes
    assert "Ferramentas disponíveis: resolver_projeto, base." in depois
    assert "Comandos do dsjob" not in depois and "## Propostas" not in depois
    assert "Nunca peça, repita nem proponha senha, token ou credencial." in depois


def test_subconjunto_cita_so_o_que_tem():
    antes, depois = svc.partes_fixas(None, True, ("resolver_projeto", "base", "dsjob"))
    assert "Antes de usar 'base' ou 'dsjob', pergunte" in antes
    assert "isx_extrair" not in antes + depois and "dsx_consulta" not in antes + depois
    assert "O job_name precisa ser um job que dsjob\nLERAM" in depois
    antes, _ = svc.partes_fixas("P", True, ("resolver_projeto", "base"))
    assert ".dsx" not in antes  # sem dsx_consulta, não oferece o .dsx


# ═══════════ 6. rotas ═════════════════════════════════════════════════════

class _BancoCadastro(_BancoPrompt):
    def __init__(self):
        self.agentes_db: dict[str, tuple] = {}
        self.perfis = set(PERFIS)
        super().__init__()

    def _fixar(self):
        super()._fixar()
        self._salvo_ag = copy.deepcopy(getattr(self, "agentes_db", {}))

    def rollback(self):
        super().rollback()
        self.agentes_db = copy.deepcopy(self._salvo_ag)

    def cursor(self):
        return _CursorCadastro(self)


class _CursorCadastro(_CursorPrompt):
    def execute(self, sql, params=None):
        b = self.b
        p = list(params or ())
        s = " ".join(sql.lower().split())
        if s.startswith("select conversa_id, agente, titulo"):  # lista do histórico: vazia basta
            self._rows = []
            return
        if re.search(r"\bdbo\.etl_agente\b(?!_)", s):  # a tabela do cadastro, não as etl_agente_*
            b.execs.append((sql, tuple(p)))
            self._rows, self.rowcount = [], -1
            if s.startswith("select") and "where agente_id = ?" in s:
                self._rows = [b.agentes_db[p[0]]] if p[0] in b.agentes_db else []
            elif s.startswith("select"):
                self._rows = list(b.agentes_db.values())
            elif s.startswith("insert"):
                if p[0] in b.agentes_db:
                    raise RuntimeError("Violation of PRIMARY KEY constraint 'PK_etl_agente'. (2627)")
                agora = b.agora()
                # Com a 122: bancos_json e mascarar_dados depois de ferramentas_json.
                bancos, mascarar, por = (p[6], p[7], p[8]) if "bancos_json" in s else (None, 1, p[6])
                b.agentes_db[p[0]] = (p[0], p[1], p[2], p[3], p[4], p[5], 0, agora, por, agora, por,
                                      bancos, mascarar)
            else:  # update
                if "bancos_json" in s:
                    nome, desc, acesso, perfis, ferr, bancos, mascarar, ativo, por, agente_id = p
                else:
                    nome, desc, acesso, perfis, ferr, ativo, por, agente_id = p
                    bancos, mascarar = None, 1
                r = b.agentes_db[agente_id]
                b.agentes_db[agente_id] = (agente_id, nome, desc, acesso, perfis, ferr, ativo, r[7], r[8],
                                           b.agora(), por, bancos, mascarar)
            return
        if s == "select perfil_nome from dbo.etl_perfil":
            self._rows = [(x,) for x in sorted(b.perfis)]
            return
        return super().execute(sql, params)


@pytest.fixture
def cadastro():
    estado = {"perms": ["tela_agentes", PERM_ADMIN], "matricula": "ADM1", "perfil": "admin", "extras": []}
    _app.dependency_overrides[get_current_user] = lambda: {
        "matricula": estado["matricula"], "perfil": estado["perfil"],
        "permissoes": estado["perms"], "permissoes_extra": estado["extras"]}
    banco = _BancoCadastro()
    with patch("routers.agentes.get_db_conn", side_effect=lambda: banco):
        yield TestClient(_app), banco, estado
    _app.dependency_overrides.pop(get_current_user, None)


def _como(estado, perfil="desenvolvedor", extras=(), tela=True):
    estado.update({"perfil": perfil, "extras": list(extras), "matricula": "U1",
                   "perms": ["tela_agentes"] if tela else []})


def test_criar_nasce_desativado_com_prompt_v1_na_mesma_transacao(cadastro):
    cliente, banco, _ = cadastro
    r = cliente.post("/agentes/admin/agentes", json=_corpo())
    assert r.status_code == 200
    ag = r.json()["agente"]
    assert ag["id"] == "assistente" and ag["origem"] == "banco" and ag["ativo"] is False
    assert ag["recurso"] == "agente_assistente" and ag["recurso_curador"] is None
    [p] = banco.prompts
    assert p == {**p, "agente_id": "assistente", "versao": 1, "texto": "Você é o assistente da equipe de dados.",
                 "motivo": "criação", "criado_por": "ADM1"}
    lista = cliente.get("/agentes/admin/agentes").json()
    assert [a["id"] for a in lista["agentes"]] == ["datastage", "assistente"]
    assert lista["agentes"][0]["origem"] == "codigo"
    assert lista["ferramentas"] == list(svc.FERRAMENTAS_DATASTAGE)


def test_criar_repetido_e_409_e_invalido_nao_grava_nada(cadastro):
    cliente, banco, _ = cadastro
    assert cliente.post("/agentes/admin/agentes", json=_corpo()).status_code == 200
    r = cliente.post("/agentes/admin/agentes", json=_corpo(nome="Outro"))
    assert r.status_code == 409 and r.json()["detail"]["code"] == "agente_existe"
    r = cliente.post("/agentes/admin/agentes", json=_corpo(id="novo", prompt="senha=Abc123"))
    assert r.status_code == 422 and r.json()["detail"]["code"] == "prompt_com_segredo"
    r = cliente.post("/agentes/admin/agentes", json=_corpo(id="datastage"))
    assert r.status_code == 422 and r.json()["detail"]["code"] == "agente_id_reservado"
    assert list(banco.agentes_db) == ["assistente"] and len(banco.prompts) == 1


def test_falha_no_prompt_desfaz_o_agente(cadastro):
    cliente, banco, _ = cadastro
    banco.erro_no_insert = RuntimeError("deadlock (1205)")  # INSERT do prompt falha
    r = TestClient(_app, raise_server_exceptions=False).post("/agentes/admin/agentes", json=_corpo())
    assert r.status_code == 500
    assert banco.agentes_db == {} and banco.prompts == []


def test_alterar_parcial_ativar_e_combinacao_invalida(cadastro):
    cliente, banco, _ = cadastro
    cliente.post("/agentes/admin/agentes", json=_corpo(ferramentas=["dsjob"]))
    r = cliente.put("/agentes/admin/agentes/assistente", json={"ativo": True, "nome": "Novo nome"})
    assert r.status_code == 200 and r.json()["agente"]["ativo"] is True and r.json()["agente"]["nome"] == "Novo nome"
    assert r.json()["agente"]["ferramentas"] == ["resolver_projeto", "dsjob"]
    antes = copy.deepcopy(banco.agentes_db)
    r = cliente.put("/agentes/admin/agentes/assistente", json={"acesso": "perfil"})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "acesso_perfil_com_servidor"
    assert banco.agentes_db == antes


def test_alterar_datastage_e_409_e_desconhecido_404(cadastro):
    cliente, _, _ = cadastro
    r = cliente.put("/agentes/admin/agentes/datastage", json={"ativo": False})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "agente_do_codigo"
    assert cliente.put("/agentes/admin/agentes/nao_existe", json={"ativo": True}).status_code == 404
    assert cliente.put("/agentes/admin/agentes/Nao-Existe", json={"ativo": True}).status_code == 404


def test_cadastro_so_admin(cadastro):
    cliente, banco, estado = cadastro
    _como(estado, extras=["agente_datastage"])
    assert cliente.get("/agentes/admin/agentes").status_code == 403
    assert cliente.post("/agentes/admin/agentes", json=_corpo()).status_code == 403
    assert cliente.put("/agentes/admin/agentes/assistente", json={"ativo": True}).status_code == 403
    assert banco.agentes_db == {}


def test_catalogo_da_rota_enxerga_o_agente_ativo(cadastro):
    cliente, banco, estado = cadastro
    banco.config.update(LIGADO)
    cliente.post("/agentes/admin/agentes", json=_corpo(acesso="perfil"))
    _como(estado)
    assert [a["id"] for a in cliente.get("/agentes/catalogo").json()["agentes"]] == []  # nasce desativado
    _como(estado, "admin")
    estado["perms"] = ["tela_agentes", PERM_ADMIN]
    cliente.put("/agentes/admin/agentes/assistente", json={"ativo": True})
    _como(estado)
    assert [a["id"] for a in cliente.get("/agentes/catalogo").json()["agentes"]] == ["assistente"]
    banco.config["agentes_enabled"] = "0"
    assert cliente.get("/agentes/catalogo").json()["agentes"] == []


def test_historico_e_status_aceitam_o_agente_do_banco(cadastro):
    cliente, _, estado = cadastro
    cliente.post("/agentes/admin/agentes", json=_corpo())
    assert cliente.get("/agentes/conversas", params={"agente": "assistente"}).status_code == 200
    assert cliente.get("/agentes/conversas", params={"agente": "nao_existe"}).status_code == 404
    svc.guardar_sonda("ADM1", "ok")
    try:
        assert cliente.get("/agentes/status", params={"agente": "assistente"}).json() == {"estado": "ok", "cache": True}
    finally:
        svc.invalidar_sonda("ADM1")
    assert cliente.get("/agentes/status", params={"agente": "nao_existe"}).status_code == 404


def test_status_do_datastage_com_cache_continua_sem_abrir_conexao(cadastro):
    cliente, _, _ = cadastro
    svc.guardar_sonda("ADM1", "ok")
    try:
        with patch("routers.agentes.get_db_conn", side_effect=AssertionError("não pode abrir conexão")):
            assert cliente.get("/agentes/status", params={"agente": "datastage"}).json()["cache"] is True
    finally:
        svc.invalidar_sonda("ADM1")


def test_prompt_do_agente_do_banco(cadastro):
    cliente, _, _ = cadastro
    cliente.post("/agentes/admin/agentes", json=_corpo())
    url = "/agentes/admin/agentes/assistente/prompt"
    r = cliente.get(url).json()
    assert r["ativa"]["versao"] == 1 and r["ativa"]["padrao"] is False
    assert r["parte_fixa"]["antes"] == "" and "DataStage" not in r["parte_fixa"]["depois"]
    versoes = cliente.get(url + "/versoes").json()["versoes"]
    assert [v["versao"] for v in versoes] == [1]  # sem "padrão do código"
    assert cliente.get(url + "/versoes/0").status_code == 404
    r = cliente.post(url + "/restaurar", json={"versao": 0, "motivo": "motivo", "versao_base": 1})
    assert r.status_code == 404
    r = cliente.put(url, json={"texto": "Versão dois.", "motivo": "ajuste", "versao_base": 1})
    assert r.status_code == 200 and r.json()["ativa"]["versao"] == 2


# ═══════════ user_perm_set enxerga o agente do banco ══════════════════════

def test_user_perm_set_valida_o_grant_do_agente_do_banco():
    from tests.test_admin_identidade_agentes import _Conn, _Cur

    class _CurComAgente(_Cur):
        def execute(self, sql, params=None):
            if "from dbo.etl_agente" in sql.lower() and "etl_agente_" not in sql.lower():
                self.execs.append((sql, tuple(params or ())))
                self._rows = [_linha(perfis=("analista",))]
                return
            super().execute(sql, params)

    _app.dependency_overrides[get_current_user] = lambda: {
        "matricula": "ADMIN1", "perfil": "admin", "permissoes": [PERM_ADMIN], "permissoes_extra": []}
    try:
        cliente = TestClient(_app)
        for perfil, esperado in (("desenvolvedor", 422), ("analista", 200)):
            cur = _CurComAgente(usuarios={"U1": perfil})
            with patch("routers.admin.get_db_conn", return_value=_Conn(cur)):
                r = cliente.post("/admin", json={"action": "user_perm_set", "matricula": "U1",
                                                 "permissoes": ["agente_assistente"]})
            assert r.status_code == esperado, (perfil, r.json())
            if esperado == 422:
                assert r.json()["detail"]["code"] == "agente_perfil_nao_elegivel"
    finally:
        _app.dependency_overrides.pop(get_current_user, None)


# ═══════════ revisão adversarial da B1 ════════════════════════════════════

@pytest.mark.parametrize("agente_id", ["datastage\n", "curador\n", "admin\n", "assistente\n", "\nassistente"])
def test_id_com_quebra_de_linha_e_invalido(agente_id):
    """`$` casa antes de um `\\n` final em Python: "datastage\\n" passava pelo
    formato e escapava dos reservados."""
    with pytest.raises(reg.AgenteInvalido) as e:
        reg.validar_criacao(_corpo(id=agente_id), PERFIS)
    assert e.value.code == "agente_id_invalido"


def test_rota_com_id_com_quebra_de_linha_nao_abre_conexao(cadastro):
    cliente, banco, _ = cadastro
    antes = banco.aberturas if hasattr(banco, "aberturas") else 0
    assert cliente.put("/agentes/admin/agentes/assistente%0A", json={"ativo": True}).status_code == 404
    assert cliente.get("/agentes/conversas", params={"agente": "assistente\n"}).status_code == 404
    assert getattr(banco, "aberturas", 0) == antes


def test_linha_a_mao_com_perfil_e_servidor_fecha_para_manual():
    ag = reg.do_banco(_linha(acesso="perfil", ferramentas=("dsjob",)))
    assert ag["acesso"] == "manual" and ag["ferramentas"] == ("resolver_projeto", "dsjob")
    assert svc.motivo_sem_acesso(_user(), ag)[0] == "agente_nao_liberado"  # sem grant, fora
    assert reg.do_banco(_linha(acesso="qualquer"))["acesso"] == "manual"


def test_desativar_sempre_passa_mesmo_com_linha_editada_a_mao():
    atual = reg.do_banco(_linha(perfis=("consulta",), acesso="perfil", ferramentas=("dsjob",)))
    assert atual["perfis_elegiveis"] == ()
    novo = reg.validar_alteracao(atual, {"ativo": False}, PERFIS)
    assert novo["ativo"] is False
    with pytest.raises(reg.AgenteInvalido):  # qualquer outra mudança continua validada
        reg.validar_alteracao(atual, {"ativo": True}, PERFIS)


@pytest.mark.parametrize("agente_id", ["curador", "x_curador", "datastage", "admin", "Maiuscula", "ab"])
def test_carga_ignora_id_invalido_ou_reservado_gravado_a_mao(agente_id):
    cur = MagicMock()
    cur.fetchall.return_value = [_linha(agente_id, ferramentas=("base",)), _linha("valido")]
    agentes = reg.carregar(cur)
    assert set(agentes) == {"datastage", "valido"}
    svc.mapa_de_recursos(agentes)  # não levanta: nada colide com o agente_curador do DataStage
    cur.fetchone.return_value = _linha(agente_id)
    assert agente_id == "datastage" or reg.um(cur, agente_id) is None


def test_erro_do_banco_que_nao_e_tabela_ausente_nao_vira_404(cadastro):
    cliente, banco, _ = cadastro

    def _explode(*_a, **_k):
        raise RuntimeError("Transaction was deadlocked (1205)")
    with patch.object(reg, "um", side_effect=_explode):
        r = TestClient(_app, raise_server_exceptions=False).get("/agentes/conversas",
                                                                  params={"agente": "assistente"})
    assert r.status_code == 500
    with patch.object(reg, "um", side_effect=RuntimeError("Invalid object name 'dbo.etl_agente'. (208)")):
        assert cliente.get("/agentes/conversas", params={"agente": "assistente"}).status_code == 404


def test_linha_com_dsjob_sem_resolver_projeto_monta_prompt_coerente():
    ag = reg.do_banco(_linha(ferramentas=("dsjob",)))
    antes, depois = svc.partes_fixas(None, False, ag["ferramentas"])
    assert "resolver_projeto" in antes and "Ferramentas disponíveis: resolver_projeto, dsjob." in depois


def test_deadlock_com_process_id_208_nao_vira_404(cadastro):
    """A 1ª correção testava "208" no texto — que também aparece como
    "Process ID 208" numa mensagem de deadlock (revisão da B1, 2ª rodada)."""
    msg = "Transaction (Process ID 208) was deadlocked on lock resources with another process (1205)"
    with patch.object(reg, "um", side_effect=RuntimeError("40001", msg)):
        r = TestClient(_app, raise_server_exceptions=False).get("/agentes/conversas",
                                                                  params={"agente": "assistente"})
    assert r.status_code == 500
    cliente, _, _ = cadastro
    with patch.object(reg, "um", side_effect=RuntimeError("42S02", "[42S02] tabela não existe")):
        assert cliente.get("/agentes/conversas", params={"agente": "assistente"}).status_code == 404


@pytest.mark.parametrize("gravado", ["Assistente", "assistente ", "ASSISTENTE"])
def test_um_so_aceita_a_linha_com_id_identico(gravado):
    cur = MagicMock()
    cur.fetchone.return_value = _linha(gravado)
    assert reg.um(cur, "assistente") is None
    cur.fetchone.return_value = _linha("assistente")
    assert reg.um(cur, "assistente")["id"] == "assistente"


def test_user_perm_set_nao_trava_por_grant_antigo_que_ficou_inelegivel():
    """Revisão da B3: o admin tirou o perfil do usuário do agente; o grant
    antigo continua em etl_usuario_permissao. Salvar OUTRA permissão não
    pode ser recusado por causa dele — o grant não dá acesso (a régua de uso
    confere o perfil). Conceder o grant de NOVO a esse perfil continua 422."""
    from tests.test_admin_identidade_agentes import _Conn, _Cur

    class _CurComGrant(_Cur):
        def __init__(self, ja_tinha, **kw):
            super().__init__(**kw)
            self.ja_tinha = ja_tinha

        def execute(self, sql, params=None):
            s = sql.lower()
            if "from dbo.etl_agente" in s and "etl_agente_" not in s:
                self.execs.append((sql, tuple(params or ())))
                self._rows = [_linha(perfis=("desenvolvedor",))]
                return
            if "select recurso from dbo.etl_usuario_permissao" in s:
                self.execs.append((sql, tuple(params or ())))
                self._rows = [(r,) for r in self.ja_tinha]
                return
            super().execute(sql, params)

    _app.dependency_overrides[get_current_user] = lambda: {
        "matricula": "ADMIN1", "perfil": "admin", "permissoes": [PERM_ADMIN], "permissoes_extra": []}
    try:
        cliente = TestClient(_app)
        cur = _CurComGrant({"agente_assistente"}, usuarios={"U1": "analista"})
        with patch("routers.admin.get_db_conn", return_value=_Conn(cur)):
            r = cliente.post("/admin", json={"action": "user_perm_set", "matricula": "U1",
                                             "permissoes": ["agente_assistente", "tela_jobs"]})
        assert r.status_code == 200, r.json()
        cur = _CurComGrant(set(), usuarios={"U1": "analista"})
        with patch("routers.admin.get_db_conn", return_value=_Conn(cur)):
            r = cliente.post("/admin", json={"action": "user_perm_set", "matricula": "U1",
                                             "permissoes": ["agente_assistente"]})
        assert r.status_code == 422 and r.json()["detail"]["code"] == "agente_perfil_nao_elegivel"
    finally:
        _app.dependency_overrides.pop(get_current_user, None)
