"""Entrada da tela /agentes em cards e tempos da consulta a banco no admin.

As funções puras da galeria (capacidades, busca, chave do último agente) rodam
DE VERDADE pelo harness `tests/js/agentes_banco_harness.cjs`. Aqui, o fonte:

  1. **Galeria** — sem `?agente=` a tela abre nos cards; escolher empurra uma
     entrada NOVA no histórico (o "voltar" volta aos cards); o antigo seletor
     virou "Trocar agente"; aviso do gateway antes da escolha; carregamento em
     esqueleto; lista vazia continua explicando.
  2. **Card** — botão de verdade (teclado), nome + descrição + o que consulta,
     "usado por último" e "conversa em andamento"; movimento só no gesto e
     desligado com `prefers-reduced-motion`; ordem do catálogo (sem reordenar).
  3. **Admin** — os dois tempos da consulta a banco na seção Gateway e limites,
     com as faixas do backend.
"""
from __future__ import annotations

import re
from pathlib import Path

from tests.test_agentes_f3_front import _COR_UTIL, _TOM_PERMITIDO, codigo

RAIZ = Path(__file__).resolve().parents[1]
FRONT = RAIZ / "ui-react" / "src"
PAGINA = FRONT / "pages" / "Agentes.tsx"
GALERIA = FRONT / "components" / "agentes" / "GaleriaAgentes.tsx"
ABA = FRONT / "components" / "admin" / "AgentesTab.tsx"
SQL = RAIZ / "api" / "services" / "agentes_sql.py"


def test_sem_agente_na_url_abre_os_cards():
    fonte = codigo(PAGINA)
    assert "const agente = useMemo(() => agentes.find(a => a.id === agenteParam) ?? null" in fonte
    assert "if (!agente) {" in fonte and "<GaleriaAgentes" in fonte
    assert "agentes[0]" not in fonte  # não entra sozinho no primeiro agente
    assert "if (agentes.length === 0) {" in fonte and "data-agentes-vazio" in fonte


def test_escolher_empurra_historico_e_trocar_volta():
    fonte = codigo(PAGINA)
    escolher = re.search(r"function escolher\(id: string\) \{(.*?)\n  \}", fonte, re.S).group(1)
    assert "marcarUltimo(matricula, id)" in escolher and "setParams(p)" in escolher
    assert "replace" not in escolher  # entrada NOVA: o "voltar" do navegador volta aos cards
    assert "p.delete('agente')" in fonte and "onClick={voltarAosCards}" in fonte
    assert "<select" not in fonte  # o seletor virou o botão "Trocar agente"
    assert "{agentes.length > 1 ? 'Trocar agente' : 'Agentes'}" in fonte


def test_aviso_do_gateway_antes_da_escolha_e_esqueleto():
    fonte = codigo(PAGINA)
    assert "aviso={sonda && SONDA[sonda]?.bloqueia ? (" in fonte
    assert "if (catalogo.isLoading) return <GaleriaCarregando />" in fonte


def test_card_e_botao_com_o_que_o_agente_consulta():
    fonte = codigo(GALERIA)
    assert '<button\n      type="button"\n      onClick={onEscolher}' in fonte
    assert "{agente.nome}" in fonte and "{agente.descricao}" in fonte
    assert "capacidadesDoAgente(agente)" in fonte and "ROTULO_CAPACIDADE[c]" in fonte
    assert "data-agentes-card-ultimo" in fonte and "data-agentes-card-andamento" in fonte
    assert "focus-visible:ring-2" in fonte


def test_movimento_so_no_gesto_e_respeita_reducao():
    fonte = codigo(GALERIA)
    assert "motion-reduce:transition-none" in fonte and "motion-reduce:hover:translate-y-0" in fonte
    assert "animate-" not in fonte.replace("motion-safe:animate-pulse", "")  # nada de entrada coreografada
    assert "motion-safe:animate-pulse" in fonte  # o esqueleto só pulsa com movimento permitido
    # o rótulo sr-only da busca vive num invólucro posicionado (test_casca_rolagem_por_foco)
    assert '<div className="relative w-full sm:w-72">' in fonte and 'role="status"' in fonte


def test_ordem_do_catalogo_e_busca_so_com_muitos():
    fonte = codigo(GALERIA)
    assert ".sort(" not in fonte
    assert "const comBusca = agentes.length >= BUSCA_A_PARTIR_DE" in fonte
    assert "if (e.key === 'Enter' && visiveis.length === 1) onEscolher(visiveis[0].id)" in fonte


def test_so_tokens_de_cor_e_tons_com_par_escuro():
    for arq in (GALERIA, PAGINA):
        fonte = codigo(arq)
        achados = [m.group(0) for m in _COR_UTIL.finditer(fonte)
                   if m.group(0) != "text-white" and not _TOM_PERMITIDO.fullmatch(m.group(0))]
        assert not achados, (arq.name, sorted(set(achados)))
    fonte = codigo(GALERIA)
    assert "dark:bg-emerald-400/15 dark:text-emerald-300" in fonte
    assert "bg-emerald-600 dark:bg-emerald-400" in fonte


def test_tempos_do_banco_no_admin_com_as_faixas_do_backend():
    aba = codigo(ABA)
    sql = SQL.read_text(encoding="utf-8")
    faixas = dict(re.findall(r"(CONEXAO|CONSULTA)_PADRAO_S, \1_MIN_S, \1_MAX_S = (\d+, \d+, \d+)", sql))
    _, cmin, cmax = faixas["CONEXAO"].split(", ")
    _, qmin, qmax = faixas["CONSULTA"].split(", ")
    assert f"type=\"number\" min={{{cmin}}} max={{{cmax}}}" in aba and "editar('agentes_banco_conexao_s'" in aba
    assert f"type=\"number\" min={{{qmin}}} max={{{qmax}}}" in aba and "editar('agentes_banco_consulta_s'" in aba
