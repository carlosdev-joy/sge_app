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


# ── F5: o Terminal REAL (a prévia `?simulado=1` saiu) ─────────────────────────────────────────────────────────────

AGENTE = COMP / "TerminalAgente.tsx"


def test_a_pagina_abre_o_terminal_real_para_o_agente_terminal_e_nao_ha_mais_previa():
    fonte = codigo(PAGINA)
    assert "agente.id === 'terminal' ? (" in fonte and "<TerminalAgente" in fonte and "<PainelConversa" in fonte
    assert "simulado" not in fonte and "TerminalSimulado" not in fonte
    assert not (COMP / "TerminalSimulado.tsx").exists()


def test_o_container_reaproveita_sonda_stream_e_fallback():
    fonte = codigo(AGENTE)
    assert "conversarPorStream(agente.id" in fonte and "rotaStreamAusente(e)" in fonte
    assert "<AvisoSonda" in fonte and "infoSonda?.bloqueia" in fonte
    assert "apiFetch" in fonte


def test_nova_conversa_descarta_resposta_atrasada():
    fonte = codigo(AGENTE)
    enviar = fonte.split("async function enviar", 1)[1].split("function comandoAtual", 1)[0]
    assert "const meu = ++pedidoRef.current" in enviar and "if (r === null || abandonado()) return" in enviar
    assert "pedidoRef.current++" in fonte.split("function nova", 1)[1]


def test_confirmar_manda_so_cmd_id_e_hash_e_reidrata_depois_de_erro():
    fonte = codigo(AGENTE)
    decidir = fonte.split("async function decidir", 1)[1].split("function nova", 1)[0]
    assert "{ cmd_id: cmdId, hash: atual.hash ?? '' }" in decidir and "comando:" not in decidir.split("const corpo", 1)[1].split("\n", 1)[0]
    assert "textoDoErroDeDecisao(codigoDoErro(e))" in decidir and "await reidratarCard(cmdId, conversa)" in decidir
    assert "if (!atual || decidindo.has(cmdId)) return" in decidir, "duplo clique = uma decisão"
    assert "/agentes/terminal/comandos/" in fonte


def test_a_escrita_so_aparece_para_quem_o_catalogo_libera():
    assert "podeEscrever={!!agente.escrita}" in codigo(AGENTE)


def test_o_card_rotula_o_motivo_como_alegacao_e_avisa_multilinha():
    card = codigo(COMP / "ConfirmarComando.tsx")
    assert "Alegação do assistente" in card and "data-terminal-multilinha" in card and "todas serão executadas" in card


def test_decisao_em_voo_so_e_descartada_por_nova_conversa_nao_por_enviar_ou_parar():
    """2ª rodada do QA da F5: o guarda da decisão é a CONVERSA (só "Nova conversa" troca), não o pedido (enviar/Parar)."""
    fonte = codigo(AGENTE)
    nova = fonte.split("function nova()", 1)[1].split("\n  }", 1)[0]
    parar = fonte.split("onParar={() => {", 1)[1].split("}}", 1)[0]
    enviar = fonte.split("async function enviar", 1)[1].split("async function", 1)[0] if "async function enviar" in fonte else ""
    assert "conversaRef.current++" in nova
    assert "conversaRef" not in parar and "conversaRef" not in enviar
    decidir = fonte.split("async function decidir", 1)[1].split("function nova", 1)[0]
    assert "const conversa = conversaRef.current" in decidir and "pedidoRef" not in decidir
    assert "res.estado === 'recusado'" in decidir, "recusa em voo não vira toast de 'confirmado'"
