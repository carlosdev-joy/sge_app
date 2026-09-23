"""Curadoria no front (F6 da spec docs/spec-agentes-datastage.md).

Leitura do fonte TS por regex, como os testes de front da F3–F5.

  1. A aba de curadoria só aparece para quem o catálogo diz que é curador
     (critério 4 — a regra está no backend, a tela só não oferece).
  2. O curador decide com a evidência à vista; ações por estado espelham as
     transições do backend.
  3. Admin › Agentes concede `agente_curador` pela MESMA mutação que já
     protege o `user_perm_set` (lê as atuais e reenvia o conjunto).
  4. O chat mostra quando uma chamada falhou ou não foi repetida, e quantos
     aprendizados foram considerados.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
FRONT = RAIZ / "ui-react" / "src"
CURADORIA = FRONT / "components" / "agentes" / "CuradoriaAprendizados.tsx"
PAGINA = FRONT / "pages" / "Agentes.tsx"
CHAT = FRONT / "components" / "agentes" / "ChatAgente.tsx"
LIB = FRONT / "lib" / "agentes.ts"
ADMIN_TAB = FRONT / "components" / "admin" / "AgentesTab.tsx"

sys.path.insert(0, str(RAIZ / "api"))


def codigo(p: Path) -> str:
    assert p.exists(), f"arquivo da F6 não existe: {p.relative_to(RAIZ)}"
    fonte = re.sub(r"/\*.*?\*/", " ", p.read_text(encoding="utf-8"), flags=re.S)
    return "\n".join(l for l in fonte.splitlines() if not l.strip().startswith("//"))


def test_curadoria_so_para_quem_e_curador():
    fonte = codigo(PAGINA)
    assert re.search(r"\{agente\.curador && \(", fonte)
    assert "curadoriaAberta && agente.curador ?" in fonte
    assert "<CuradoriaAprendizados" in fonte


def test_curadoria_usa_os_endpoints_do_backend():
    fonte = codigo(CURADORIA)
    assert "`/agentes/aprendizados?estado=${estado}`" in fonte
    assert "`/agentes/aprendizados/${id}/decidir`" in fonte and "JSON.stringify({ acao })" in fonte
    assert "codigoDoErro(e) === 'transicao_invalida'" in fonte
    assert "qc.invalidateQueries({ queryKey: ['agentes-aprendizados'] })" in fonte


def test_curador_ve_a_evidencia():
    fonte = codigo(CURADORIA)
    assert "data-agentes-aprendizado-evidencia" in fonte and "a.evidencia" in fonte
    assert "sm:grid-cols-2" in fonte


def test_acoes_do_front_espelham_as_transicoes_do_backend():
    from services import agentes_aprendizado as ap
    fonte = codigo(LIB)
    bloco = re.search(r"export const ACOES_APRENDIZADO[^=]*=\s*\{(.*?)\n\}", fonte, re.S).group(1)
    front = {e: set(re.findall(r"'(\w+)'", acoes)) for e, acoes in re.findall(r"(\w+): \[([^\]]*)\]", bloco)}
    back: dict[str, set] = {e: set() for e in ap.ESTADOS}
    for acao, (origens, _destino) in ap.TRANSICOES.items():
        for o in origens:
            back[o].add(acao)
    assert front == back


def test_estados_do_front_espelham_o_backend():
    from services import agentes_aprendizado as ap
    fonte = codigo(LIB)
    bloco = re.search(r"export const ESTADOS_APRENDIZADO[^=]*=\s*\[(.*?)\n\]", fonte, re.S).group(1)
    assert re.findall(r"estado: '(\w+)'", bloco) == list(ap.ESTADOS)


def test_admin_concede_curador_pela_mesma_mutacao():
    fonte = codigo(ADMIN_TAB)
    assert "recurso: ag.recurso_curador" in fonte and "recurso: ag.recurso," in fonte
    assert "recurso: papel.recurso, conceder: true" in fonte
    assert "recurso: papel.recurso, conceder: false" in fonte
    # a proteção do user_perm_set continua sendo a única via
    assert fonte.count("adminPost('user_perm_set'") == 1
    assert "ag.perfis_elegiveis.includes(u.perfil)" in fonte


def test_chat_mostra_falha_e_nao_repeticao():
    fonte = codigo(CHAT)
    assert "(não repetida)" in fonte and "(falhou)" in fonte
    assert "data-agentes-aprendizados-usados" in fonte and "data-agentes-aprendizados-sugeridos" in fonte


def test_pagina_repassa_aprendizados_da_resposta():
    fonte = codigo(PAGINA)
    assert "r.aprendizados_usados.map(a => a.titulo)" in fonte
    assert "aprendizadosSugeridos: r.aprendizados_sugeridos?.length" in fonte


def test_data_futura_nao_usa_quando():
    """`quando` só trata o passado: `revalidar_em` futuro sairia como "hoje"."""
    fonte = codigo(CURADORIA)
    assert "dataCurta(a.revalidar_em)" in fonte and "quando(a.revalidar_em)" not in fonte


def test_sem_cor_fixa_nova():
    for p in (CURADORIA,):
        hexes = set(re.findall(r"#[0-9A-Fa-f]{6}", codigo(p)))
        assert hexes <= {"#1A5FA8"}, hexes
