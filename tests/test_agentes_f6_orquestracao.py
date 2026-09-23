"""services/agentes.conversar — a FIAÇÃO da F6 (spec docs/spec-agentes-datastage.md).

  • Critério 1: a mesma chamada que já falhou (numa conversa anterior, com o
    erro validado) NÃO roda de novo — 0 chamadas — e o aprendizado vai ao
    contexto do modelo.
  • Guarda da conversa: o que falhou numa pergunta não roda na seguinte
    (o router devolve as chamadas via `falhas_anteriores`) nem de novo na
    mesma pergunta. Falha passageira pode repetir.
  • Recuperação: validado vai ao prompt de sistema; rascunho nunca.
  • Sugestões do modelo viram rascunho; grafia de projeto vira aprendizado
    de busca.
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
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))

from services import agentes as svc  # noqa: E402
from services import agentes_aprendizado as ap  # noqa: E402
from services import agentes_ferramentas as af  # noqa: E402
from services import ia_provedor  # noqa: E402
from tests._banco_agentes_f6 import BancoF6  # noqa: E402


class _Provedor:
    def __init__(self, respostas):
        self.respostas = list(respostas)
        self.chamadas = []

    async def __call__(self, cfg, sistema, historico, identidade=None, campo_identidade=None):
        self.chamadas.append({"sistema": sistema, "historico": list(historico)})
        return self.respostas.pop(0), "modelo-teste"


def _pedido(ferramenta, **args):
    return "```json\n" + json.dumps({"ferramenta": ferramenta, "args": args}) + "\n```"


class _ISXErro(Exception):
    def __init__(self, status, detail):
        super().__init__(detail)
        self.status, self.detail = status, detail


@pytest.fixture
def banco(monkeypatch):
    b = BancoF6()
    monkeypatch.setattr(af, "projeto_tem_dsx", lambda nome: False)
    return b


async def _conversar(banco, provedor, monkeypatch, pergunta="explique o JobX", **kw):
    monkeypatch.setattr(ia_provedor, "chat_conversa", provedor)
    padrao = dict(projeto_atual="BI_CVP", provedor_cfg={}, identidade="cvp-dev1", campo_identidade=None,
                  ssh_max=10, acao_editar=True, matricula="DEV1")
    padrao.update(kw)
    return await svc.conversar(banco.abrir, mensagens=[{"role": "user", "content": pergunta}], **padrao)


def _isx_xml_invalido(monkeypatch, chamadas):
    async def _executor(fn, *args, teto):
        chamadas.append(1)
        raise _ISXErro(422, "XML da definição do job inválido (reference to invalid character number 3 at line 7).")
    monkeypatch.setattr(af, "isx_no_executor", _executor)
    monkeypatch.setattr(af.lineage_isx, "config", lambda: "CFG")


# ═══════════ 1. critério 1 — entre conversas ══════════════════════════════

@pytest.mark.asyncio
async def test_erro_de_conversa_anterior_nao_repete_e_vai_ao_contexto(banco, monkeypatch):
    chamadas: list = []
    _isx_xml_invalido(monkeypatch, chamadas)
    # 1ª conversa: falha e vira aprendizado validado
    p1 = _Provedor([_pedido("isx_extrair", job_name="JobXML"), "o job tem XML inválido"])
    r1 = await _conversar(banco, p1, monkeypatch)
    assert chamadas == [1]
    [a] = banco.aprendizados.values()
    assert a["tipo"] == "erro" and a["estado"] == "validado"
    assert r1["artefatos"][0]["falhou"] == "xml_invalido"

    # 2ª conversa (nova, sem falhas_anteriores): a mesma chamada NÃO roda
    p2 = _Provedor([_pedido("isx_extrair", job_name="JobXML"), "não extraí de novo"])
    r2 = await _conversar(banco, p2, monkeypatch)
    assert chamadas == [1], "a 2ª ocorrência não pode chamar o servidor"
    dado = p2.chamadas[1]["historico"][-1]["content"]
    assert "Não repeti esta chamada" in dado and "XML da definição do job inválido" in dado
    assert r2["artefatos"][0]["repetida"] is True
    assert a["id"] in {u["id"] for u in r2["aprendizados_usados"]}


@pytest.mark.asyncio
async def test_erro_conhecido_nao_bloqueia_outro_job(banco, monkeypatch):
    chamadas: list = []
    _isx_xml_invalido(monkeypatch, chamadas)
    await _conversar(banco, _Provedor([_pedido("isx_extrair", job_name="JobXML"), "ok"]), monkeypatch)
    await _conversar(banco, _Provedor([_pedido("isx_extrair", job_name="OutroJob"), "ok"]), monkeypatch)
    assert chamadas == [1, 1]


# ═══════════ 2. guarda da conversa ════════════════════════════════════════

def _dsjob_falha(chamadas):
    async def _fake(comando, projeto, job, *, teto_sessoes, espera_max_s):
        chamadas.append((comando, job))
        return {"exit_code": 255, "stdout": "", "stderr": "job inexistente", "saida_redigida": ""}
    return _fake


@pytest.mark.asyncio
async def test_mesma_chamada_nao_roda_duas_vezes_na_mesma_pergunta(banco, monkeypatch):
    chamadas: list = []
    monkeypatch.setattr(af, "ferramenta_dsjob", _dsjob_falha(chamadas))
    # impede a guarda ENTRE conversas de mascarar o teste: só a da conversa vale aqui
    monkeypatch.setattr(ap, "erro_conhecido", lambda *a, **k: None)
    p = _Provedor([_pedido("dsjob", comando="lstages", job_name="JobX"),
                   _pedido("dsjob", comando="lstages", job_name="JobX"), "desisto"])
    r = await _conversar(banco, p, monkeypatch)
    assert chamadas == [("lstages", "JobX")]
    assert "já falhou nesta conversa" in p.chamadas[2]["historico"][-1]["content"]
    assert r["artefatos"][1]["repetida"] is True


@pytest.mark.asyncio
async def test_falha_de_pergunta_anterior_vem_do_router_e_nao_repete(banco, monkeypatch):
    chamadas: list = []
    monkeypatch.setattr(af, "ferramenta_dsjob", _dsjob_falha(chamadas))
    monkeypatch.setattr(ap, "erro_conhecido", lambda *a, **k: None)
    anterior = ap.chave_da_chamada("dsjob", {"comando": "lstages", "job_name": "JobX"}, "BI_CVP")
    p = _Provedor([_pedido("dsjob", comando="lstages", job_name="JobX"), "ok"])
    await _conversar(banco, p, monkeypatch, falhas_anteriores={anterior})
    assert chamadas == []


@pytest.mark.asyncio
async def test_a_chave_da_falha_vai_no_artefato_para_a_proxima_pergunta(banco, monkeypatch):
    monkeypatch.setattr(af, "ferramenta_dsjob", _dsjob_falha([]))
    r = await _conversar(banco, _Provedor([_pedido("dsjob", comando="lstages", job_name="JobX"), "ok"]), monkeypatch)
    art = r["artefatos"][0]
    assert art["falhou"] == "dsjob_falhou"
    assert art["chamada"] == ap.chave_da_chamada("dsjob", {"comando": "lstages", "job_name": "JobX"}, "BI_CVP")


@pytest.mark.asyncio
async def test_falha_passageira_pode_repetir_e_nao_vira_aprendizado(banco, monkeypatch):
    chamadas: list = []

    async def _ocupado(comando, projeto, job, *, teto_sessoes, espera_max_s):
        chamadas.append(1)
        raise af.ServidorOcupado("Servidor DataStage ocupado — tente de novo em instantes.")
    monkeypatch.setattr(af, "ferramenta_dsjob", _ocupado)
    p = _Provedor([_pedido("dsjob", comando="lstages", job_name="JobX"),
                   _pedido("dsjob", comando="lstages", job_name="JobX"), "ok"])
    r = await _conversar(banco, p, monkeypatch)
    assert chamadas == [1, 1]
    assert banco.aprendizados == {}
    assert not any(a.get("falhou") or a.get("repetida") for a in r["artefatos"])


@pytest.mark.asyncio
async def test_ssh_nao_configurado_vira_aprendizado_de_acesso(banco, monkeypatch):
    async def _sem_ssh(comando, projeto, job, *, teto_sessoes, espera_max_s):
        from services.ssh_datastage import DsConsoleError
        raise DsConsoleError("SSH do DataStage não configurado no servidor.")
    monkeypatch.setattr(af, "ferramenta_dsjob", _sem_ssh)
    monkeypatch.setattr(af, "ssh_configured", lambda: False)
    await _conversar(banco, _Provedor([_pedido("dsjob", comando="lstages", job_name="JobX"), "ok"]), monkeypatch)
    [a] = banco.aprendizados.values()
    assert a["tipo"] == "acesso" and a["estado"] == "validado"


@pytest.mark.asyncio
async def test_falha_ao_registrar_nao_derruba_a_rodada(banco, monkeypatch):
    monkeypatch.setattr(af, "ferramenta_dsjob", _dsjob_falha([]))

    def _explode(*a, **k):
        raise RuntimeError("tabela ausente")
    monkeypatch.setattr(ap, "registrar", _explode)
    monkeypatch.setattr(ap, "recuperar", _explode)
    monkeypatch.setattr(ap, "erro_conhecido", _explode)
    r = await _conversar(banco, _Provedor([_pedido("dsjob", comando="lstages", job_name="JobX"), "pronto"]),
                         monkeypatch)
    assert r["status"] == "ok" and r["texto"] == "pronto"


# ═══════════ 3. recuperação vai ao prompt (critério 3) ════════════════════

@pytest.mark.asyncio
async def test_validado_vai_ao_prompt_e_rascunho_nao(banco, monkeypatch):
    banco.novo_aprendizado(estado="validado", titulo="Ler o JobX pelo report", corpo="use report")
    banco.novo_aprendizado(estado="rascunho", titulo="JobX rascunho secreto", corpo="não pode aparecer")
    p = _Provedor(["resposta"])
    r = await _conversar(banco, p, monkeypatch, pergunta="como leio o JobX?")
    sistema = p.chamadas[0]["sistema"]
    assert "Ler o JobX pelo report" in sistema and "<aprendizados>" in sistema
    assert "rascunho secreto" not in sistema
    assert [u["titulo"] for u in r["aprendizados_usados"]] == ["Ler o JobX pelo report"]
    assert next(a for a in banco.aprendizados.values() if a["estado"] == "validado")["ultimo_uso_em"]


@pytest.mark.asyncio
async def test_sem_aprendizado_relevante_o_prompt_fica_como_antes(banco, monkeypatch):
    p = _Provedor(["resposta"])
    await _conversar(banco, p, monkeypatch, pergunta="oi")
    assert "<aprendizados>" not in p.chamadas[0]["sistema"]


# ═══════════ 4. sugestões e busca ═════════════════════════════════════════

@pytest.mark.asyncio
async def test_sugestao_do_modelo_vira_rascunho_e_nao_entra_na_proxima_conversa(banco, monkeypatch):
    bloco = json.dumps({"aprendizados": [{"tipo": "leitura", "titulo": "Ler JobX pelo lparams",
                                          "corpo": "o lparams do JobX mostra a data de corte"}]})
    r = await _conversar(banco, _Provedor([f"Pronto.\n```json\n{bloco}\n```"]), monkeypatch)
    assert r["texto"] == "Pronto." and r["aprendizados_sugeridos"] == ["Ler JobX pelo lparams"]
    [a] = banco.aprendizados.values()
    assert a["estado"] == "rascunho" and a["origem"] == "interpretacao"
    p2 = _Provedor(["ok"])
    await _conversar(banco, p2, monkeypatch, pergunta="e o JobX?")
    assert "Ler JobX pelo lparams" not in p2.chamadas[0]["sistema"]


@pytest.mark.asyncio
async def test_sugestao_e_proposta_no_mesmo_bloco_final(banco, monkeypatch):
    bloco1 = json.dumps({"aprendizados": [{"tipo": "leitura", "titulo": "t", "corpo": "c"}]})
    r = await _conversar(banco, _Provedor([f"Texto.\n```json\n{bloco1}\n```"]), monkeypatch)
    assert "```" not in r["texto"]


@pytest.mark.asyncio
async def test_grafia_de_projeto_vira_aprendizado_de_busca(banco, monkeypatch):
    monkeypatch.setattr(af, "resolver_projeto", lambda cur, nome=None, **kw: {
        "estado": "quase", "projeto": None, "sugerido": "BI_CVP", "tem_dsx": False, "sugestoes": []})
    p = _Provedor([_pedido("resolver_projeto", projeto="bi_cvp"), "confirme o nome"])
    await _conversar(banco, p, monkeypatch, projeto_atual=None)
    [a] = banco.aprendizados.values()
    assert a["tipo"] == "busca" and a["estado"] == "validado" and "BI_CVP" in a["titulo"]


def test_prompt_explica_sugestao_de_aprendizado():
    p = svc._prompt_sistema("BI_CVP")
    assert '"aprendizados"' in p and "curador" in p
    assert svc._prompt_sistema("BI_CVP", contexto_aprendizados="<aprendizados>x</aprendizados>").endswith(
        "</aprendizados>\n")



@pytest.mark.asyncio
async def test_eco_de_nao_configurado_no_comando_nao_vira_aprendizado(banco, monkeypatch):
    """Segurança F6: o modelo escolhe `comando` = "não configurado"."""
    monkeypatch.setattr(af, "ssh_configured", lambda: True)
    await _conversar(banco, _Provedor([_pedido("dsjob", comando="não configurado", job_name="JobX"), "ok"]),
                     monkeypatch)
    assert banco.aprendizados == {}


@pytest.mark.asyncio
async def test_isx_por_pipeline_guarda_vale_mesmo_com_projeto_da_conversa_diferente(banco, monkeypatch):
    """QA F6 #3: conversa A sem projeto, conversa B com projeto — mesma chamada."""
    chamadas: list = []
    _isx_xml_invalido(monkeypatch, chamadas)
    monkeypatch.setattr(af, "isx_info_do_job", lambda cur, p, j: {
        "pipeline_name": p, "job_name": j, "ds_project": "BI_CVP", "job_type": "datastage"})
    monkeypatch.setattr(af.lineage_isx, "cabecalho", lambda cur, p, j: None)
    monkeypatch.setattr(af.lineage_isx, "conta_linhas", lambda cur, p, j: 0)
    monkeypatch.setattr(af.lineage_isx, "mapa_tipos", lambda cur: {})
    pedido = _pedido("isx_extrair", pipeline_name="PIPE", job_name="JobXML")
    await _conversar(banco, _Provedor([pedido, "ok"]), monkeypatch, projeto_atual=None)
    await _conversar(banco, _Provedor([pedido, "ok"]), monkeypatch, projeto_atual="BI_CVP")
    assert chamadas == [1]


@pytest.mark.asyncio
async def test_proposta_e_aprendizado_no_mesmo_bloco_ambos_valem(banco, monkeypatch):
    """QA F6 #1: regressão da F5 — a proposta sumia em silêncio."""
    async def _dsjob(comando, projeto, job, *, teto_sessoes, espera_max_s):
        return {"exit_code": 0, "stdout": "LerClientes\n", "stderr": "", "saida_redigida": "LerClientes\n"}
    monkeypatch.setattr(af, "ferramenta_dsjob", _dsjob)
    bloco = json.dumps({
        "propostas": [{"job_name": "JobX", "tipo": "stage", "chave": "LerClientes", "valor": "lê clientes",
                       "evidencia": "LerClientes"}],
        "aprendizados": [{"tipo": "leitura", "titulo": "lstages basta", "corpo": "para stages use lstages"}]})
    r = await _conversar(banco, _Provedor([_pedido("dsjob", comando="lstages", job_name="JobX"),
                                           f"Pronto.\n```json\n{bloco}\n```"]), monkeypatch)
    assert len(r["propostas"]) == 1 and r["aprendizados_sugeridos"] == ["lstages basta"]
    assert r["texto"] == "Pronto."
