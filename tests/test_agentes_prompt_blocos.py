"""Prompt do agente montado em blocos (fase A0 de docs/spec-agentes-admin.md §3.1).

O prompt deixa de ser um texto único: um bloco de DOMÍNIO (que a fase A1 vai
ler de uma versão gravada pelo admin) seguido dos blocos FIXOS que o código
impõe. O que se prende aqui, e por quê:

  1. **O contexto da conversa vem ANTES do domínio e os blocos fixos DEPOIS, e
     sempre** — trocar o domínio não some com o protocolo, as regras nem o
     formato de propostas; e o modelo sabe do projeto resolvido antes de ler
     "resolver_projeto primeiro".
  2. **O domínio padrão não imita o protocolo nem carrega as regras de
     segurança** — senão editar/apagar o domínio mexeria no que o código impõe.
  3. **A lista de comandos do `dsjob` sai da allowlist** (anti-drift).
  4. **`FERRAMENTAS_DATASTAGE` é o que o despachante sabe executar** — é a tupla
     que a Fase B vai recortar em subconjuntos.
"""
from __future__ import annotations

import inspect
import os
import sys
from unittest.mock import MagicMock

if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()
os.environ.setdefault("MSSQL_CONN_STR", "__mock__")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))

from services import agentes as svc  # noqa: E402
from services import agentes_ferramentas as af  # noqa: E402

DOMINIO = svc.PROMPT_DOMINIO_PADRAO[svc.AGENTE_DATASTAGE]
CONTEXTO = "## Contexto desta conversa"
CABECALHOS_FIXOS = ("## Como usar as ferramentas", "## Regras que valem sempre", "## Propostas e aprendizados")
# O texto do protocolo que faz o modelo PEDIR ferramenta e entender a guarda —
# sem ele o agente para de consultar e nenhum outro teste percebe.
PROTOCOLO_OBRIGATORIO = (
    "Termine sua resposta com UM bloco JSON e NADA depois dele:",
    '{"ferramenta": "NOME", "args": {...}}',
    "Se não precisar de ferramenta, responda normalmente sem bloco.",
    "Chamadas que já falharam não são repetidas pelo Orquestra",
)
MARCADORES_DO_PROTOCOLO = ('"ferramenta":', '"propostas":', '"aprendizados":', "<ferramenta", "<aprendizados")


# ═══════════ 1. ordem e presença dos blocos ═══════════════════════════════

def test_ordem_contexto_dominio_e_blocos_fixos():
    p = svc._prompt_sistema("BI_CVP")
    assert p.startswith(CONTEXTO + "\n\nO projeto DataStage desta conversa já está resolvido: BI_CVP.")
    inicio_dominio = p.index(DOMINIO.strip())
    posicoes = [p.index(c) for c in CABECALHOS_FIXOS]
    assert posicoes == sorted(posicoes) and posicoes[0] > inicio_dominio + len(DOMINIO.strip())


def test_projeto_resolvido_aparece_antes_da_ordem_de_custo():
    """Revisão adversarial da A0: com o contexto depois do domínio, o modelo
    lia "resolver_projeto — primeiro passo obrigatório" sem saber que o
    projeto já estava resolvido e gastava uma rodada."""
    p = svc._prompt_sistema("BI_CVP")
    assert p.index("já está resolvido: BI_CVP") < p.index("## Ordem de custo")


def test_protocolo_de_ferramentas_completo():
    p = svc._prompt_sistema("BI_CVP", dominio="Outro domínio.")
    for trecho in PROTOCOLO_OBRIGATORIO:
        assert trecho in p, trecho


def test_trocar_o_dominio_mantem_todos_os_blocos_fixos():
    p = svc._prompt_sistema("BI_CVP", dominio="Você é um agente de teste.")
    assert "\n\nVocê é um agente de teste.\n\n## Como usar as ferramentas" in p
    assert "Ordem de custo" not in p  # o domínio padrão saiu inteiro
    for c in (CONTEXTO, *CABECALHOS_FIXOS):
        assert c in p
    assert "Você NUNCA altera o DataStage" in p
    assert "Nunca invente informação que não veio de uma ferramenta." in p
    assert "Nunca proponha\nsenha, token ou valor de parâmetro" in p
    assert "O projeto DataStage desta conversa já está resolvido: BI_CVP." in p


def test_dominio_vazio_nao_deixa_o_prompt_sem_protocolo():
    p = svc._prompt_sistema(None, dominio="   ")
    assert p.startswith(CONTEXTO)
    assert "AINDA NÃO tem um projeto DataStage resolvido" in p
    assert "\n\n\n" not in p  # o bloco vazio não deixa buraco
    assert "## Como usar as ferramentas" in p


def test_aprendizados_validados_continuam_por_ultimo():
    p = svc._prompt_sistema("BI_CVP", contexto_aprendizados="<aprendizados>x</aprendizados>",
                            dominio="Outro domínio.")
    assert p.endswith("\n\n<aprendizados>x</aprendizados>\n")


# ═══════════ 2. o que NÃO pode estar no domínio ═══════════════════════════

def test_dominio_padrao_nao_imita_o_protocolo():
    """A fase A1 vai recusar esses marcadores num domínio gravado pelo admin;
    o padrão precisa passar na mesma régua (senão restaurar a versão 0
    seria recusado)."""
    for m in MARCADORES_DO_PROTOCOLO:
        assert m not in DOMINIO, m


def test_regras_de_seguranca_nao_moram_no_dominio():
    assert "NUNCA altera o DataStage" not in DOMINIO
    assert "Nunca invente informação" not in DOMINIO
    assert "Nunca proponha" not in DOMINIO
    for c in (CONTEXTO, *CABECALHOS_FIXOS):
        assert c not in DOMINIO


# ═══════════ 3. anti-drift da allowlist ═══════════════════════════════════

def test_comandos_do_dsjob_saem_da_allowlist(monkeypatch):
    monkeypatch.setattr(af, "ALLOWLIST_DSJOB", ("ljobs", "comando_novo"))
    p = svc._prompt_sistema("BI_CVP")
    assert "Comandos do dsjob disponíveis: ljobs, comando_novo" in p
    assert "comando_novo" not in DOMINIO


def test_comandos_do_dsjob_so_aparecem_se_o_agente_tem_dsjob():
    assert "Comandos do dsjob" not in svc._bloco_protocolo(("resolver_projeto", "base"))
    assert "Ferramentas disponíveis: resolver_projeto, base." in svc._bloco_protocolo(("resolver_projeto", "base"))


# ═══════════ 4. a tupla de ferramentas ════════════════════════════════════

def test_ferramentas_datastage_sao_as_que_o_despachante_executa():
    """Cada nome precisa ter um RAMO no despachante (`nome == "x"`), não só
    aparecer num comentário ou mensagem. `dsjob` é o ramo final, depois do
    `if nome not in ("base", "dsjob")`."""
    fonte = inspect.getsource(svc._executar_ferramenta_interna)
    for nome in svc.FERRAMENTAS_DATASTAGE:
        if nome == "dsjob":
            assert 'if nome not in ("base", "dsjob"):' in fonte
        else:
            assert f'if nome == "{nome}"' in fonte, nome
    p = svc._prompt_sistema("BI_CVP")
    assert "Ferramentas disponíveis: " + ", ".join(svc.FERRAMENTAS_DATASTAGE) + "." in p
