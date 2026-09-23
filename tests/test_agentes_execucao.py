"""Execução dos agentes criados pela tela (B2 de docs/spec-agentes-admin.md §4.3).

O que se prende, e por quê:

  1. **Só conversa** — uma chamada ao gateway, prompt só com o domínio e as
     regras genéricas; bloco de ferramenta/proposta/aprendizado que o modelo
     mande é tirado do texto e nada executa nem grava (critério 4).
  2. **Subconjunto** — ferramenta fora do conjunto do agente é recusada antes
     de tocar o servidor (critério 5); o prompt lista só as dele.
  3. **Por agente** — aprendizados, guarda e fila do curador com o id do agente.
  4. **Rotas genéricas** — acesso pela régua única, interruptor, prompt
     indisponível, stream.
  5. **Conversa presa ao agente** — `conversa_id` de outro agente é 404
     (critério 8), nos dois sentidos.
  6. **Propostas e curadoria por agente** — a rota de um agente não decide a
     fila de outro (critérios 8 e 9); o fato aprovado guarda quem propôs.
  7. **O DataStage não muda** — rotas e acesso de antes (critério 6).
"""
from __future__ import annotations

import json
import os
import sys
from unittest.mock import MagicMock

import pytest

if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()
os.environ.setdefault("MSSQL_CONN_STR", "__mock__")

from deps import PERM_ADMIN  # noqa: E402
from services import agentes as svc  # noqa: E402
from services import agentes_ferramentas as af  # noqa: E402
from services import ia_provedor  # noqa: E402
from tests._banco_agentes_f6 import BancoF6  # noqa: E402
from tests.test_agentes_cadastro import LIGADO, _corpo, cadastro  # noqa: E402,F401 — fixture

SO_CONVERSA = ()
SO_BASE = ("resolver_projeto", "base")


class _Provedor:
    def __init__(self, respostas):
        self.respostas = list(respostas)
        self.chamadas: list[dict] = []

    async def __call__(self, cfg, sistema, historico, identidade=None, campo_identidade=None):
        self.chamadas.append({"sistema": sistema, "historico": list(historico)})
        return self.respostas.pop(0), "modelo-teste"


def _pedido(ferramenta, **args):
    return "```json\n" + json.dumps({"ferramenta": ferramenta, "args": args}) + "\n```"


@pytest.fixture
def espioes(monkeypatch):
    """Registra o que a orquestração pediu à base de aprendizados e ao
    despachante — sem banco nem servidor."""
    log = {"recuperar": [], "registrar": [], "executar": [], "erro_conhecido": []}
    monkeypatch.setattr(svc, "_recuperar_seguro", lambda _a, _p, _proj, agente="datastage": (
        log["recuperar"].append(agente) or []))
    monkeypatch.setattr(svc, "_registrar_seguro", lambda _a, apr, agente="datastage": log["registrar"].append(agente))
    monkeypatch.setattr(svc, "_erro_conhecido_seguro", lambda _a, n, _args, _p, agente="datastage": (
        log["erro_conhecido"].append(agente)))

    async def _executar(_abrir, nome, args, **kw):
        log["executar"].append((nome, kw.get("agente")))
        return {"texto": f"leitura de {nome}"}, None
    monkeypatch.setattr(svc, "_executar_ferramenta", _executar)
    monkeypatch.setattr(af, "projeto_tem_dsx", lambda n: False)
    return log


async def _conversar(monkeypatch, provedor, **kw):
    monkeypatch.setattr(ia_provedor, "chat_conversa", provedor)
    base = dict(projeto_atual=None, provedor_cfg={}, identidade="cvp-u1", campo_identidade=None,
                ssh_max=10, matricula="U1", dominio="Você é o assistente de teste.")
    base.update(kw)
    return await svc.conversar(BancoF6().abrir, mensagens=[{"role": "user", "content": "oi"}], **base)


# ═══════════ 1. só conversa ═══════════════════════════════════════════════

@pytest.mark.asyncio
async def test_so_conversa_uma_chamada_e_nada_executa(monkeypatch, espioes):
    resposta = ("Aqui vai a resposta.\n" + _pedido("dsjob", comando="ljobs")
                + '\n```json\n{"propostas": [{"job_name": "X"}]}\n```')
    p = _Provedor([resposta])
    r = await _conversar(monkeypatch, p, agente="assistente", ferramentas=SO_CONVERSA)
    assert len(p.chamadas) == 1
    sistema = p.chamadas[0]["sistema"]
    assert sistema.startswith("Você é o assistente de teste.")
    assert "## Como usar as ferramentas" not in sistema and "## Contexto desta conversa" not in sistema
    assert "## Propostas" not in sistema and "DataStage" not in sistema
    assert r["status"] == "ok" and r["texto"] == "Aqui vai a resposta."
    assert r["propostas"] == [] and r["artefatos"] == [] and r["projeto"] is None
    assert espioes["executar"] == [] and espioes["registrar"] == [] and espioes["recuperar"] == []


@pytest.mark.asyncio
async def test_so_conversa_resposta_so_com_bloco_vira_texto_padrao(monkeypatch, espioes):
    r = await _conversar(monkeypatch, _Provedor([_pedido("dsjob")]), agente="assistente", ferramentas=SO_CONVERSA)
    assert r["texto"] == "Não tenho mais nada a acrescentar." and espioes["executar"] == []


@pytest.mark.asyncio
async def test_so_conversa_gateway_recusou(monkeypatch, espioes):
    async def _recusa(*a, **k):
        raise ia_provedor.GatewayRecusou("x")
    monkeypatch.setattr(ia_provedor, "chat_conversa", _recusa)
    r = await svc.conversar(BancoF6().abrir, mensagens=[{"role": "user", "content": "oi"}], projeto_atual=None,
                            provedor_cfg={}, identidade="i", campo_identidade=None, ssh_max=1,
                            agente="assistente", ferramentas=SO_CONVERSA, dominio="d")
    assert r["status"] == "gateway_recusou"


# ═══════════ 2–3. subconjunto e por agente ════════════════════════════════

@pytest.mark.asyncio
async def test_ferramenta_fora_do_conjunto_e_recusada_sem_tocar_o_servidor(monkeypatch, espioes):
    p = _Provedor([_pedido("dsjob", comando="ljobs"), _pedido("isx_extrair", job_name="J"), "sem acesso a isso"])
    r = await _conversar(monkeypatch, p, agente="assistente", ferramentas=SO_BASE, projeto_atual="BI_CVP")
    assert espioes["executar"] == []
    assert [a.get("recusada") for a in r["artefatos"]] == ["fora_do_agente", "fora_do_agente"]
    dado = p.chamadas[1]["historico"][-1]["content"]
    assert "não está disponível para este agente" in dado and "resolver_projeto, base" in dado
    assert "Ferramentas disponíveis: resolver_projeto, base." in p.chamadas[0]["sistema"]
    assert "Comandos do dsjob" not in p.chamadas[0]["sistema"]


@pytest.mark.asyncio
async def test_ferramenta_do_conjunto_executa_com_o_agente(monkeypatch, espioes):
    p = _Provedor([_pedido("base", job_name="JobX"), "pronto"])
    await _conversar(monkeypatch, p, agente="assistente", ferramentas=SO_BASE, projeto_atual="BI_CVP")
    assert espioes["executar"] == [("base", "assistente")]
    assert espioes["recuperar"] == ["assistente"]


@pytest.mark.asyncio
async def test_ferramenta_desconhecida_segue_o_caminho_de_sempre(monkeypatch, espioes):
    """Nome que nem existe na allowlist vai ao despachante, como antes —
    ele devolve a mensagem de ferramenta desconhecida."""
    p = _Provedor([_pedido("rm_rf"), "ok"])
    await _conversar(monkeypatch, p, agente="assistente", ferramentas=SO_BASE)
    assert espioes["executar"] == [("rm_rf", "assistente")]


@pytest.mark.asyncio
async def test_datastage_por_padrao(monkeypatch, espioes):
    p = _Provedor([_pedido("dsjob", comando="ljobs"), "pronto"])
    await _conversar(monkeypatch, p, projeto_atual="BI_CVP")
    assert espioes["executar"] == [("dsjob", "datastage")] and espioes["recuperar"] == ["datastage"]
    assert "Ferramentas disponíveis: " + ", ".join(svc.FERRAMENTAS_DATASTAGE) + "." in p.chamadas[0]["sistema"]


# ═══════════ 4–6. rotas ═══════════════════════════════════════════════════

def _criar(cliente, estado, **kw):
    """Cria e ativa como admin; devolve o estado para o chamador trocar de usuário."""
    estado.update(perfil="admin", extras=[], matricula="ADM1", perms=["tela_agentes", PERM_ADMIN])
    assert cliente.post("/agentes/admin/agentes", json=_corpo(**kw)).status_code == 200
    assert cliente.put(f"/agentes/admin/agentes/{kw.get('id', 'assistente')}", json={"ativo": True}).status_code == 200


def _como(estado, perfil="desenvolvedor", extras=(), tela=True):
    estado.update(perfil=perfil, extras=list(extras), matricula="U1", perms=["tela_agentes"] if tela else [])


@pytest.fixture
def chat(cadastro, monkeypatch):
    cliente, banco, estado = cadastro
    banco.config.update(LIGADO)
    recebido: list = []

    async def _fake(abrir_conn, **kw):
        recebido.append(kw)
        return {"status": "ok", "texto": "resposta", "projeto": None, "artefatos": []}
    monkeypatch.setattr(svc, "conversar", _fake)
    return cliente, banco, estado, recebido


def test_rota_generica_usa_o_prompt_e_as_ferramentas_do_agente(chat):
    cliente, banco, estado, recebido = chat
    _criar(cliente, estado, acesso="perfil")
    _como(estado)
    r = cliente.post("/agentes/assistente/conversar", json={"mensagem": "oi"})
    assert r.status_code == 200
    kw = recebido[-1]
    assert kw["agente"] == "assistente" and kw["ferramentas"] == ()
    assert kw["dominio"] == "Você é o assistente da equipe de dados."
    assert banco.conversas[r.json()["conversa_id"]]["agente"] == "assistente"


def test_stream_generico(chat):
    cliente, _, estado, recebido = chat
    _criar(cliente, estado, acesso="perfil")
    _como(estado)
    r = cliente.post("/agentes/assistente/conversar/stream", json={"mensagem": "oi"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    assert '"tipo": "resposta"' in r.text and recebido[-1]["agente"] == "assistente"


@pytest.mark.parametrize("cenario, status, code", [
    ("sem_tela", 403, "agente_sem_tela"), ("consulta", 403, "agente_nao_elegivel"),
    ("operador", 403, "agente_nao_elegivel"), ("desconhecido", 404, "agente_desconhecido"),
])
def test_acesso_na_rota_generica(chat, cenario, status, code):
    cliente, _, estado, recebido = chat
    _criar(cliente, estado, acesso="perfil")
    _como(estado, tela=cenario != "sem_tela",
          perfil={"consulta": "consulta", "operador": "operador"}.get(cenario, "desenvolvedor"))
    alvo = "nao_existe" if cenario == "desconhecido" else "assistente"
    r = cliente.post(f"/agentes/{alvo}/conversar", json={"mensagem": "oi"})
    assert r.status_code == status and r.json()["detail"]["code"] == code
    assert recebido == []


def test_manual_exige_o_grant(chat):
    cliente, _, estado, _r = chat
    _criar(cliente, estado, acesso="manual")
    _como(estado)
    assert cliente.post("/agentes/assistente/conversar", json={"mensagem": "oi"}).status_code == 403
    _como(estado, extras=["agente_assistente"])
    assert cliente.post("/agentes/assistente/conversar", json={"mensagem": "oi"}).status_code == 200


def test_desativado_ou_geral_desligado_e_503(chat):
    cliente, banco, estado, recebido = chat
    _criar(cliente, estado, acesso="perfil")
    cliente.put("/agentes/admin/agentes/assistente", json={"ativo": False})
    _como(estado)
    r = cliente.post("/agentes/assistente/conversar", json={"mensagem": "oi"})
    assert r.status_code == 503 and r.json()["detail"]["code"] == "agente_desligado"
    estado.update(perfil="admin", perms=["tela_agentes", PERM_ADMIN])  # o admin reativa
    cliente.put("/agentes/admin/agentes/assistente", json={"ativo": True})
    banco.config["agentes_enabled"] = "0"
    _como(estado)
    assert cliente.post("/agentes/assistente/conversar", json={"mensagem": "oi"}).status_code == 503
    assert recebido == []


def test_prompt_indisponivel_e_503_e_nao_cria_conversa(chat):
    cliente, banco, estado, recebido = chat
    _criar(cliente, estado, acesso="perfil")
    banco.prompts.clear()
    banco._fixar()
    _como(estado)
    r = cliente.post("/agentes/assistente/conversar", json={"mensagem": "oi"})
    assert r.status_code == 503 and r.json()["detail"]["code"] == "agente_prompt_indisponivel"
    assert banco.conversas == {} and recebido == []


def test_conversa_presa_ao_agente_nos_dois_sentidos(chat):
    cliente, _, estado, recebido = chat
    _criar(cliente, estado, acesso="perfil")
    _como(estado, extras=["agente_datastage"])
    cid_ds = cliente.post("/agentes/datastage/conversar", json={"mensagem": "oi"}).json()["conversa_id"]
    cid_as = cliente.post("/agentes/assistente/conversar", json={"mensagem": "oi"}).json()["conversa_id"]
    n = len(recebido)
    for rota, cid in (("/agentes/assistente/conversar", cid_ds), ("/agentes/datastage/conversar", cid_as)):
        r = cliente.post(rota, json={"mensagem": "de novo", "conversa_id": cid})
        assert r.status_code == 404 and r.json()["detail"]["code"] == "conversa_nao_encontrada"
    assert len(recebido) == n


def test_rota_do_datastage_continua_a_de_sempre(chat):
    """`/agentes/datastage/conversar` é a rota LITERAL (declarada antes): a
    régua é a `require_agente` de sempre — sem exigir a tela, como antes."""
    cliente, _, estado, recebido = chat
    _como(estado, extras=["agente_datastage"], tela=False)
    assert cliente.post("/agentes/datastage/conversar", json={"mensagem": "oi"}).status_code == 200
    assert recebido[-1]["agente"] == "datastage"
    assert recebido[-1]["ferramentas"] == svc.FERRAMENTAS_DATASTAGE


# ═══════════ 6. propostas e curadoria por agente ══════════════════════════

def test_proposta_se_decide_so_pela_rota_do_agente_dela(chat):
    cliente, banco, estado, _r = chat
    _criar(cliente, estado, acesso="perfil")
    _como(estado, extras=["agente_datastage"])
    p_as = banco.nova_proposta(matricula="U1", agente="assistente")
    p_ds = banco.nova_proposta(matricula="U1", agente="datastage")
    corpo = {"decisao": "aprovar"}
    assert cliente.post(f"/agentes/propostas/{p_as}/decidir", json=corpo).status_code == 404
    assert cliente.post(f"/agentes/assistente/propostas/{p_ds}/decidir", json=corpo).status_code == 404
    r = cliente.post(f"/agentes/assistente/propostas/{p_as}/decidir", json=corpo)
    assert r.status_code == 200 and r.json()["proposta"]["estado"] == "aprovada"
    [fato] = [f for f in banco.fatos if f["origem"] == "interpretacao_aprovada"]
    assert fato["agente"] == "assistente"
    assert cliente.post(f"/agentes/propostas/{p_ds}/decidir", json=corpo).status_code == 200


def _agente_com_curadoria(cliente, estado):
    _criar(cliente, estado, acesso="manual", ferramentas=["base"])


def test_curadoria_por_agente(chat):
    cliente, banco, estado, _r = chat
    _agente_com_curadoria(cliente, estado)
    a_as = banco.novo_aprendizado(estado="rascunho", agente="assistente", titulo="do assistente")
    a_ds = banco.novo_aprendizado(estado="rascunho", agente="datastage", titulo="do datastage")
    _como(estado, extras=["agente_assistente", "agente_assistente_curador"])
    r = cliente.get("/agentes/assistente/aprendizados")
    assert r.status_code == 200 and [a["titulo"] for a in r.json()["aprendizados"]] == ["do assistente"]
    assert cliente.post(f"/agentes/assistente/aprendizados/{a_ds}/decidir",
                        json={"acao": "validar"}).status_code == 404
    assert banco.aprendizados[a_ds]["estado"] == "rascunho"
    r = cliente.post(f"/agentes/assistente/aprendizados/{a_as}/decidir", json={"acao": "validar"})
    assert r.status_code == 200 and banco.aprendizados[a_as]["validado_por"] == "U1"


def test_curador_de_um_agente_nao_cura_outro(chat):
    cliente, banco, estado, _r = chat
    _agente_com_curadoria(cliente, estado)
    banco.novo_aprendizado(estado="rascunho", agente="assistente")
    # curador do DataStage, com uso do assistente, mas sem o curador do assistente
    _como(estado, extras=["agente_datastage", "agente_curador", "agente_assistente"])
    r = cliente.get("/agentes/assistente/aprendizados")
    assert r.status_code == 403 and r.json()["detail"]["code"] == "agente_nao_liberado"
    # curador do assistente sem o uso: também não
    _como(estado, extras=["agente_assistente_curador"])
    assert cliente.get("/agentes/assistente/aprendizados").status_code == 403


def test_agente_so_conversa_nao_tem_curadoria(chat):
    cliente, _, estado, _r = chat
    _criar(cliente, estado, acesso="perfil")
    _como(estado, extras=["agente_assistente_curador"])
    r = cliente.get("/agentes/assistente/aprendizados")
    assert r.status_code == 404 and r.json()["detail"]["code"] == "agente_sem_curadoria"


def test_curadoria_do_agente_desativado_e_503(chat):
    cliente, banco, estado, _r = chat
    _agente_com_curadoria(cliente, estado)
    cliente.put("/agentes/admin/agentes/assistente", json={"ativo": False})
    _como(estado, extras=["agente_assistente", "agente_assistente_curador"])
    r = cliente.get("/agentes/assistente/aprendizados")
    assert r.status_code == 503 and r.json()["detail"]["code"] == "agente_desligado"


def test_rotas_antigas_da_curadoria_continuam_do_datastage(chat):
    cliente, banco, estado, _r = chat
    _agente_com_curadoria(cliente, estado)
    banco.novo_aprendizado(estado="rascunho", agente="assistente", titulo="do assistente")
    banco.novo_aprendizado(estado="rascunho", agente="datastage", titulo="do datastage")
    _como(estado, extras=["agente_datastage", "agente_curador"])
    r = cliente.get("/agentes/aprendizados")
    assert [a["titulo"] for a in r.json()["aprendizados"]] == ["do datastage"]


# ═══════════ revisão adversarial da B2 ════════════════════════════════════

def test_aprovar_sem_a_migration_121_continua_funcionando(chat):
    """A coluna `etl_agente_fato.agente` é da 121. A API nova num banco sem
    ela (6c respondida com `n`) não pode quebrar o aprovar do DataStage."""
    cliente, banco, estado, _r = chat
    banco.migracao_121 = False
    _como(estado, extras=["agente_datastage"])
    pid = banco.nova_proposta(matricula="U1")
    r = cliente.post(f"/agentes/propostas/{pid}/decidir", json={"decisao": "aprovar"})
    assert r.status_code == 200 and r.json()["proposta"]["estado"] == "aprovada"
    [fato] = [f for f in banco.fatos if f["origem"] == "interpretacao_aprovada"]
    assert fato["agente"] is None


@pytest.mark.asyncio
async def test_aprendizado_de_busca_vai_para_o_agente_certo(monkeypatch):
    """`resolver_projeto` que acha o projeto por aproximação grava um
    aprendizado de busca — na fila do agente que chamou, não do DataStage."""
    registrados: list = []
    monkeypatch.setattr(svc, "_registrar_seguro", lambda _a, apr, agente="datastage": registrados.append(agente))
    monkeypatch.setattr(af, "resolver_projeto", lambda cur, nome, **k: {"estado": "quase", "sugerido": "BI_CVP"})
    monkeypatch.setattr(svc, "_com_cursor", lambda abrir, fn: fn(MagicMock()))
    dado, projeto = await svc._executar_ferramenta_interna(
        BancoF6().abrir, "resolver_projeto", {"projeto": "bi_cvp"}, projeto=None, ssh_max=1, espera_max_s=1,
        acao_editar=False, matricula="U1", extracoes_isx=0, resta_agora=lambda: 100, agente="assistente")
    assert "parecido com 'BI_CVP'" in dado["texto"] and projeto is None
    assert registrados == ["assistente"]
