"""Agente Terminal, F1 (front com dados simulados) — spec docs/spec-agente-terminal.md.

A lógica pura roda de verdade em `tests/js/agente_terminal_harness.cjs`; aqui, a fiação
(a prévia só abre com os dois parâmetros) e as regras de UX que não podem regredir.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
FRONT = RAIZ / "ui-react" / "src"
PAGINA = FRONT / "pages" / "Agentes.tsx"
COMP = FRONT / "components" / "agentes"


def codigo(p: Path) -> str:
    fonte = re.sub(r"/\*.*?\*/", " ", p.read_text(encoding="utf-8"), flags=re.S)
    return "\n".join(l for l in fonte.splitlines() if not l.strip().startswith("//"))


def test_harness_da_logica_pura_roda_no_node():
    node = shutil.which("node")
    if not node or not (RAIZ / "ui-react/node_modules/sucrase").is_dir():
        pytest.skip("front não instalado nesta máquina")
    r = subprocess.run([node, str(RAIZ / "tests/js/agente_terminal_harness.cjs")],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr or r.stdout
    assert r.stdout.strip() == "ok"


def test_previa_so_abre_com_agente_terminal_e_simulado():
    fonte = codigo(PAGINA)
    assert "params.get('agente') === 'terminal' && params.get('simulado') === '1'" in fonte
    assert "<AgentesReal />" in fonte  # sem os parâmetros, a tela real é a de sempre


def test_simulador_nao_fala_com_a_rede():
    for nome in ("TerminalSimulado.tsx", "TerminalChat.tsx", "ComandoBloco.tsx", "ConfirmarComando.tsx"):
        assert "apiFetch" not in codigo(COMP / nome), nome
    assert "apiFetch" not in codigo(FRONT / "lib" / "terminalSimulado.ts")


def test_enter_no_campo_nao_confirma_comando():
    chat = codigo(COMP / "TerminalChat.tsx")
    # o Enter do textarea só ENVIA a mensagem; confirmar é botão próprio do card
    assert "onDecidir" not in re.search(r"onKeyDown=\{[^}]*\}[^}]*\}", chat, re.S).group(0)
    card = codigo(COMP / "ConfirmarComando.tsx")
    assert "data-terminal-confirmar-botao" in card
    assert "onKeyDown" not in card


def test_sem_permissao_de_escrita_o_card_nao_tem_botoes():
    card = codigo(COMP / "ConfirmarComando.tsx")
    assert "podeEscrever ? (" in card
    assert "data-terminal-sem-escrita" in card


def test_terminal_tem_aria_log_e_selo_com_texto():
    chat = codigo(COMP / "TerminalChat.tsx")
    assert 'role="log"' in chat and 'aria-live="polite"' in chat
    assert "Somente leitura" in chat and "Escrita habilitada" in chat


def test_cores_de_paleta_com_par_claro_escuro_fora_do_terminal():
    """O corpo do terminal é fixo escuro (doc §4); o cabeçalho usa par claro+escuro."""
    chat = codigo(COMP / "TerminalChat.tsx")
    assert "bg-green-50" in chat and "dark:bg-green-900/30" in chat
    assert "bg-amber-50" in chat and "dark:bg-amber-900/30" in chat


def test_previa_nasce_somente_leitura():
    """QA F1 (M1): escrita só com `escrita=1` explícito — o padrão é o seguro."""
    assert "podeEscrever={params.get('escrita') === '1'}" in codigo(PAGINA)


def test_decidir_descarta_resultado_apos_nova_conversa():
    """QA F1 (I1): confirmar + 'Nova conversa' não pode ressuscitar o comando."""
    sim = codigo(COMP / "TerminalSimulado.tsx")
    corpo = sim.split("function decidir", 1)[1].split("function nova", 1)[0]
    assert "const minha = conversa.current" in corpo
    assert "if (minha !== conversa.current) return" in corpo
    assert "podeDecidir(alvo.comando" in corpo  # mesma régua da tela (M3)
    assert "setDecidindo(new Set())" in sim.split("function nova", 1)[1]


def test_foco_e_relogio_seguem_a_proposta_viva():
    """QA F1 (I2/I3): campo não rouba o foco do card; relógio atualiza ao ligar."""
    chat = codigo(COMP / "TerminalChat.tsx")
    assert "estadoEfetivo(m.comando, agora) === 'proposto'" in chat
    assert "if (!enviando && !bloqueado && !temProposta) campo.current?.focus()" in chat
    ligar = chat.split("if (!temProposta) return", 1)[1].split("setInterval", 1)[0]
    assert "setAgora(new Date())" in ligar


def test_texto_secundario_do_terminal_tem_contraste():
    """QA F1 (I4): nada de gray-500 em texto sobre o corpo escuro (<4,5:1)."""
    assert "text-gray-500" not in codigo(COMP / "ComandoBloco.tsx").replace("text-gray-500 select-none", "")


def test_enviar_nao_invalida_decisao_pendente():
    """QA F1 rodada 2 (N1): só `nova()` incrementa o contador; enviar durante a
    confirmação não pode deixar o card preso em "Executando…"."""
    sim = codigo(COMP / "TerminalSimulado.tsx")
    assert len(re.findall(r"conversa\.current\+\+", sim)) == 1
    assert "conversa.current++" in sim.split("function nova", 1)[1]
    assert "++conversa.current" not in sim
    assert "geracao" not in sim
