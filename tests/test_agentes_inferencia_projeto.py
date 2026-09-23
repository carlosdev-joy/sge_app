"""Ajuste de produção de 23/09/2026 (commit fe3de8b da branch
`feat/agente-datastage-melhorias`): o agente infere o projeto pelo PREFIXO do
job (`SsdPrs_*` → BI_PRESTAMISTA) sem pedir confirmação, e quando o prefixo
não diz nada LISTA os projetos conhecidos em vez de dizer "não encontrado".

O que o código garante por baixo do prompt:
  • `resolver_projeto {"listar": true}` existe de verdade (base ∪ DSX, sem
    tocar o servidor DataStage);
  • inferir não fura a guarda do risco 28: o nome inferido ainda passa por
    `resolver_projeto`, que só resolve o que existe na base/DSX;
  • a mensagem do "quase" não contradiz mais o prompt;
  • o nome digitado aparece na mensagem de projeto desconhecido (bug da F2:
    saía "(nenhum)").
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
from services import agentes_ferramentas as af  # noqa: E402
from services import ia_provedor  # noqa: E402


class _Provedor:
    def __init__(self, respostas):
        self.respostas = list(respostas)
        self.chamadas = []

    async def __call__(self, cfg, sistema, historico, identidade=None, campo_identidade=None):
        self.chamadas.append({"sistema": sistema, "historico": list(historico)})
        return self.respostas.pop(0), "m"


def _abrir():
    class _C:
        def execute(self, *a, **k):
            pass

        def fetchall(self):
            return []

        def fetchone(self):
            return None

        def commit(self):
            pass

        def close(self):
            pass
    return _C(), _C()


def _pedido(ferramenta, **args):
    return "```json\n" + json.dumps({"ferramenta": ferramenta, "args": args}) + "\n```"


async def _rodar(monkeypatch, *respostas, projeto_atual=None):
    p = _Provedor(respostas)
    monkeypatch.setattr(ia_provedor, "chat_conversa", p)
    monkeypatch.setattr(af, "projeto_tem_dsx", lambda n: False)
    await svc.conversar(_abrir, mensagens=[{"role": "user", "content": "explique o SsdPrs_Ods_01"}],
                        projeto_atual=projeto_atual, provedor_cfg={}, identidade="x", campo_identidade=None,
                        ssh_max=10, matricula="DEV1")
    return p


@pytest.mark.parametrize("listar", [True, "true", "TRUE"])
@pytest.mark.asyncio
async def test_listar_devolve_os_projetos_conhecidos_sem_tocar_o_servidor(monkeypatch, listar):
    monkeypatch.setattr(af, "_projetos_da_base", lambda cur: ["BI_VIDA", "BI_PRESTAMISTA"])
    monkeypatch.setattr(af, "_projetos_com_dsx", lambda: ["BI_PRESTAMISTA", "BI_CVP"])

    def _explode(*a, **k):
        raise AssertionError("listar projetos não toca o servidor DataStage")
    monkeypatch.setattr(af, "run_dsjob", _explode)
    p = await _rodar(monkeypatch, _pedido("resolver_projeto", listar=listar), "Qual projeto?")
    dado = p.chamadas[1]["historico"][-1]["content"]
    assert "BI_CVP (tem .dsx), BI_PRESTAMISTA (tem .dsx), BI_VIDA" in dado
    assert "Peça ao usuário para escolher" in dado


@pytest.mark.asyncio
async def test_listar_nao_resolve_projeto_nenhum(monkeypatch):
    monkeypatch.setattr(af, "_projetos_da_base", lambda cur: ["BI_VIDA"])
    monkeypatch.setattr(af, "_projetos_com_dsx", lambda: [])
    p = await _rodar(monkeypatch, _pedido("resolver_projeto", listar=True),
                     _pedido("dsjob", comando="lstages", job_name="J"), "ok")
    assert "projeto DataStage desta conversa" in p.chamadas[2]["historico"][-1]["content"]  # dsjob recusado


@pytest.mark.parametrize("listar", [False, "false", "sim", 1])
def test_so_true_pede_listagem(listar):
    assert svc._pede_listagem({"listar": listar}) is False


def test_listagem_vazia_explica(monkeypatch):
    monkeypatch.setattr(af, "_projetos_da_base", lambda cur: [])
    monkeypatch.setattr(af, "_projetos_com_dsx", lambda: [])
    assert af.projetos_conhecidos(None) == []


def test_listagem_tem_teto(monkeypatch):
    monkeypatch.setattr(af, "_projetos_da_base", lambda cur: [f"P{i:03d}" for i in range(80)])
    monkeypatch.setattr(af, "_projetos_com_dsx", lambda: [])
    assert len(af.projetos_conhecidos(None)) == af.MAX_PROJETOS_LISTADOS


@pytest.mark.asyncio
async def test_projeto_inferido_ainda_passa_pela_validacao(monkeypatch):
    """Inferir pelo prefixo não resolve nada sozinho: um nome inferido que
    não existe na base/DSX continua desconhecido (guarda do risco 28)."""
    monkeypatch.setattr(af, "_projetos_da_base", lambda cur: ["BI_PRESTAMISTA"])
    monkeypatch.setattr(af, "_projetos_com_dsx", lambda: [])
    p = await _rodar(monkeypatch, _pedido("resolver_projeto", projeto="BI_VIDA"), "ok")
    dado = p.chamadas[1]["historico"][-1]["content"]
    assert "Não reconheço o projeto 'BI_VIDA'" in dado and "BI_PRESTAMISTA" in dado


@pytest.mark.asyncio
async def test_quase_nao_manda_mais_confirmar_sempre(monkeypatch):
    monkeypatch.setattr(af, "_projetos_da_base", lambda cur: ["BI_PRESTAMISTA"])
    monkeypatch.setattr(af, "_projetos_com_dsx", lambda: [])
    p = await _rodar(monkeypatch, _pedido("resolver_projeto", projeto="bi_prestamista"), "ok")
    dado = p.chamadas[1]["historico"][-1]["content"]
    assert "Se o prefixo do job confirma esse projeto" in dado and '"BI_PRESTAMISTA"' in dado
    assert "Confirme com o usuário e, se for" not in dado


def test_prompt_manda_inferir_pelo_prefixo_e_listar_sem_dizer_nao_encontrado():
    p = svc._prompt_sistema(None)
    assert "`SsdPrs_*` / `SeqSsdPrs_*` → BI_PRESTAMISTA" in p
    assert '{"listar": true}' in p and 'nunca diga "não encontrado"' in p


def test_frase_de_progresso_da_listagem():
    assert svc.texto_de_progresso("resolver_projeto", {"listar": True}, None) == "Listando os projetos conhecidos…"
