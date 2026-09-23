"""Progresso (SSE) e duração no front — spec docs/spec-agentes-feedback-progresso.md.

A lógica (leitor de SSE com eventos partidos por BYTE, formatador de duração,
leitura do stream com erro/abandono/rota ausente) roda de verdade no harness
`tests/js/agentes_sse_harness.cjs`. Aqui, a fiação da página e do chat.
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
CHAT = FRONT / "components" / "agentes" / "ChatAgente.tsx"
STREAM = FRONT / "lib" / "agentesStream.ts"


def codigo(p: Path) -> str:
    fonte = re.sub(r"/\*.*?\*/", " ", p.read_text(encoding="utf-8"), flags=re.S)
    return "\n".join(l for l in fonte.splitlines() if not l.strip().startswith("//"))


def test_harness_do_sse_roda_no_node():
    node = shutil.which("node")
    if not node or not (RAIZ / "ui-react/node_modules/sucrase").is_dir():
        pytest.skip("front não instalado nesta máquina")
    r = subprocess.run([node, str(RAIZ / "tests/js/agentes_sse_harness.cjs")],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr or r.stdout
    assert r.stdout.strip() == "ok"


def test_stream_usa_fetch_com_autorizacao_nao_eventsource():
    fonte = codigo(STREAM)
    assert "apiFetchBruto(`/agentes/${agenteId}/conversar/stream`" in fonte
    assert "EventSource" not in fonte
    assert "decoder.decode(value, { stream: true })" in fonte


def test_pagina_cai_no_endpoint_json_so_quando_a_rota_nao_existe():
    fonte = codigo(PAGINA)
    assert "conversarPorStream(agente.id, corpo," in fonte
    assert "if (!rotaStreamAusente(e)) throw e" in fonte
    assert "apiFetch<RespostaConversa>(`/agentes/${agente.id}/conversar`, { method: 'POST', body: corpo })" in fonte


def test_status_so_da_conversa_atual_e_limpo_ao_trocar():
    fonte = codigo(PAGINA)
    assert "t => { if (!abandonado()) setStatusTexto(t) }" in fonte
    # limpo ao terminar, ao retomar e em nova conversa
    assert fonte.count("setStatusTexto(null)") >= 4


def test_duracao_da_resposta_ao_vivo_e_da_retomada():
    fonte = codigo(PAGINA)
    assert "duracaoMs: typeof r.duracao_ms === 'number' ? r.duracao_ms : undefined" in fonte
    assert "duracaoMs: m.papel === 'assistant' && typeof m.duracao_ms === 'number'" in fonte
    chat = codigo(CHAT)
    assert "formatarDuracao(m.duracaoMs)" in chat and "data-agentes-duracao" in chat


def test_chat_mostra_o_progresso_no_lugar_do_texto_fixo():
    chat = codigo(CHAT)
    assert "{statusTexto || `${nomeAgente} está consultando…`}" in chat
    assert 'aria-live="polite"' in chat  # o leitor de tela anuncia o progresso


# ═══════════ barra do topo (curadoria · histórico · nova conversa) ═══════════

def test_barra_do_topo_estruturada_na_mesma_ordem():
    fonte = codigo(PAGINA)
    # `group`, não `toolbar`: o padrão ARIA de toolbar promete navegação por
    # setas, que a barra não tem (Tab já alcança tudo) — apontado na revisão.
    barra = fonte[fonte.index('role="group" aria-label="Ações da conversa"'):]
    barra = barra[:barra.index("</div>")]
    assert 'aria-label="Ações da conversa"' in barra
    # mesma ordem de antes (regra: não reordenar a tela sem pedido)
    assert barra.index('rotulo="Curadoria"') < barra.index('rotulo="Histórico"') < barra.index('rotulo="Nova conversa"')
    # a curadoria continua só para curador
    assert "{agente.curador && (" in barra


def test_rotulo_fixo_e_estado_em_aria_pressed():
    fonte = codigo(PAGINA)
    assert "aria-pressed={alternavel ? ativo : undefined}" in fonte
    assert "'ocultar histórico'" not in fonte and "'voltar à conversa' : 'curadoria'" not in fonte
    assert "ativo={historicoAberto}" in fonte and "ativo={curadoriaAberta}" in fonte


def test_nova_conversa_nao_some_da_barra():
    fonte = codigo(PAGINA)
    assert "desabilitado={mensagens.length === 0}" in fonte
    assert "{mensagens.length > 0 && (" not in fonte


def test_barra_sem_cor_fixa_fora_da_marca():
    import re as _re
    fonte = codigo(PAGINA)
    bloco = fonte[fonte.index("function BotaoBarra"):fonte.index("let seq = 0")]
    assert set(_re.findall(r"#[0-9A-Fa-f]{6}", bloco)) <= {"#1A5FA8"}
    assert "dark:" in bloco and "focus-visible:ring-2" in bloco
