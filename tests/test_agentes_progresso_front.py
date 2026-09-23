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


# ═══════════ histórico: visual novo, sem corte (ajuste de 23/09) ═══════════

HISTORICO = FRONT / "components" / "agentes" / "HistoricoConversas.tsx"


def test_titulo_do_historico_sai_inteiro():
    """O relato: título e lista cortados. O título não tem mais `truncate`
    nem `line-clamp` (tem no máximo 200 caracteres) — só a etiqueta do
    projeto trunca, e o `title` fica acessível pelo texto inteiro."""
    fonte = codigo(HISTORICO)
    bloco = fonte[fonte.index("data-agentes-historico-titulo") - 300:fonte.index("data-agentes-historico-titulo")]
    assert "truncate" not in bloco and "line-clamp" not in bloco
    assert "break-words" in bloco


def test_painel_mais_largo_e_teto_maior_no_empilhado():
    fonte = codigo(HISTORICO)
    assert "sm:w-80" in fonte and "max-h-[50vh] sm:max-h-none" in fonte
    assert "max-h-56" not in fonte


def test_historico_agrupado_por_dia_com_cabecalho_fixo():
    fonte = codigo(HISTORICO)
    assert "grupoDaConversa(c.ultima_msg_em)" in fonte and "GRUPOS_HISTORICO.filter" in fonte
    assert "sticky top-0" in fonte and "data-agentes-historico-grupo={grupo}" in fonte
    assert "horaOuDia(c.ultima_msg_em)" in fonte


def test_curadoria_e_historico_se_excluem():
    """Relato de produção (23/09): Curadoria → Histórico deixava os DOIS
    destacados e só a curadoria na tela (ela ocupa o lugar do histórico)."""
    fonte = codigo(PAGINA)
    cur = fonte[fonte.index("function alternarCuradoria()"):fonte.index("function alternarHistorico()")]
    his = fonte[fonte.index("function alternarHistorico()"):]
    his = his[:his.index("\n  }\n")]
    assert "if (abrir) setHistoricoAberto(false)" in cur
    assert "if (abrir) setCuradoriaAberta(false)" in his
    assert "onClick={alternarCuradoria}" in fonte and "onClick={alternarHistorico}" in fonte
    # nenhum outro caminho liga os dois por conta própria
    assert "setCuradoriaAberta(v => !v)" not in fonte and "setHistoricoAberto(v => !v)" not in fonte
