"""Propostas no front (F5 da spec docs/spec-agentes-datastage.md).

A lógica pura (`aplicarDecisao`, `valorDaProposta`) roda DE VERDADE pelo
harness `tests/js/agentes_propostas_harness.cjs`. O resto é leitura do fonte
por regex, como `test_agentes_f3_front.py`/`test_agentes_f4_front.py` — o repo
não tem runtime de teste para React.

O que se prende, e por quê:

  1. **A evidência fica ao lado do valor** no cartão (risco 15: aprovação no
     automático) — não atrás de um clique.
  2. **O cartão só pede decisão quando `pendente`**; decidida, vira registro.
  3. **A decisão vai ao endpoint certo com o verbo do backend** (`aprovar`/
     `recusar`), e o 409 `proposta_ja_decidida` sincroniza o cartão.
  4. **Retomar a conversa traz os cartões** com o estado do servidor.
  5. **Os tipos/estados do front espelham o backend** — duas listas que
     precisam concordar.
  6. **Sem cor fixa nova** fora do azul da marca e dos tons de estado com par
     claro/escuro.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
FRONT = RAIZ / "ui-react" / "src"
CARTAO = FRONT / "components" / "agentes" / "CartaoProposta.tsx"
CHAT = FRONT / "components" / "agentes" / "ChatAgente.tsx"
PAGINA = FRONT / "pages" / "Agentes.tsx"
LIB = FRONT / "lib" / "agentes.ts"

sys.path.insert(0, str(RAIZ / "api"))


def codigo(p: Path) -> str:
    assert p.exists(), f"arquivo da F5 não existe: {p.relative_to(RAIZ)}"
    fonte = re.sub(r"/\*.*?\*/", " ", p.read_text(encoding="utf-8"), flags=re.S)
    return "\n".join(l for l in fonte.splitlines() if not l.strip().startswith("//"))


def test_logica_pura_das_propostas_roda_no_node():
    node = shutil.which("node")
    if not node or not (RAIZ / "ui-react/node_modules/sucrase").is_dir():
        pytest.skip("front não instalado nesta máquina")
    r = subprocess.run([node, str(RAIZ / "tests/js/agentes_propostas_harness.cjs")],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr or r.stdout
    assert r.stdout.strip() == "ok"


# ═══════════ 1 e 2. o cartão ══════════════════════════════════════════════

def test_cartao_mostra_valor_e_evidencia_lado_a_lado():
    fonte = codigo(CARTAO)
    assert "sm:grid-cols-2" in fonte
    assert "data-agentes-proposta-valor" in fonte and "data-agentes-proposta-evidencia" in fonte
    assert "proposta.evidencia" in fonte and "valorDaProposta(proposta.valor)" in fonte


def test_botoes_so_quando_pendente():
    fonte = codigo(CARTAO)
    assert re.search(r"const pendente = proposta\.estado === 'pendente'", fonte)
    bloco = fonte[fonte.index("{pendente && ("):]
    assert "'aprovar'" in bloco and "'recusar'" in bloco
    assert bloco.count("disabled={decidindo}") == 2


def test_cartao_acessivel():
    fonte = codigo(CARTAO)
    assert 'role="group"' in fonte and "aria-labelledby={tituloId}" in fonte
    assert "aria-label={`Aprovar proposta:" in fonte and "aria-label={`Recusar proposta:" in fonte


def test_sem_cor_fixa_nova_no_cartao():
    fonte = codigo(CARTAO)
    hexes = set(re.findall(r"#[0-9A-Fa-f]{6}", fonte))
    assert hexes <= {"#1A5FA8"}, f"cor fixa fora da marca: {hexes}"
    # todo tom de estado colorido tem o par escuro
    for cor in re.findall(r"text-(amber|emerald)-\d{3}", fonte):
        assert f"dark:text-{cor}-" in fonte


# ═══════════ 3. a decisão ═════════════════════════════════════════════════

def test_decidir_chama_o_endpoint_com_o_verbo_do_backend():
    fonte = codigo(PAGINA)
    assert "`/agentes/propostas/${id}/decidir`" in fonte
    assert "JSON.stringify({ decisao })" in fonte
    assert re.search(r"type DecisaoProposta = 'aprovar' \| 'recusar'", codigo(LIB))


def test_409_ja_decidida_sincroniza_o_cartao():
    fonte = codigo(PAGINA)
    assert "codigoDoErro(e) === 'proposta_ja_decidida'" in fonte
    assert "aplicar(detalhe.proposta)" in fonte


def test_decisao_nao_regrava_storage_de_outra_conversa():
    """Achado durante a implementação: com `conversaId` do fechamento, trocar
    de conversa enquanto a decisão salvava gravaria as mensagens da conversa
    NOVA com o id da ANTIGA. A página só grava se a proposta estava na tela
    (`aplicarDecisao` devolve a mesma referência se não estava) e reaproveita
    o par id/projeto do que já está guardado."""
    fonte = codigo(PAGINA)
    assert "if (novas === m) return m" in fonte
    assert "const atual = lerGuardada(agente.id)" in fonte
    assert "guardar(agente.id, { ...atual, mensagens: novas })" in fonte


def test_chat_so_mostra_cartao_com_handler_e_informa_descartadas():
    fonte = codigo(CHAT)
    assert "onDecidir && m.propostas?.map" in fonte
    assert "data-agentes-propostas-recusadas" in fonte
    assert re.search(r"onDecidir=\{\(id, d\) => \{ void decidir\(id, d\) \}\}", codigo(PAGINA))


# ═══════════ 4. retomar ═══════════════════════════════════════════════════

def test_retomar_traz_as_propostas_das_respostas():
    fonte = codigo(PAGINA)
    assert re.search(r"propostas: m\.papel === 'assistant' && m\.propostas\?\.length \? m\.propostas : undefined",
                     fonte)
    assert re.search(r"propostas: r\.propostas\?\.length \? r\.propostas : undefined", fonte)


# ═══════════ 5. espelho front × backend ═══════════════════════════════════

def _chaves_de(nome: str) -> set[str]:
    bloco = re.search(rf"export const {nome}[^=]*=\s*\{{(.*?)\n\}}", codigo(LIB), re.S).group(1)
    return set(re.findall(r"^\s*(\w+):", bloco, re.M))


def test_tipos_do_front_espelham_os_do_backend():
    from services import agentes_conhecimento as ac
    assert _chaves_de("TIPOS_PROPOSTA") == set(ac.TIPOS_FATO)


def test_estados_do_front_espelham_os_do_backend():
    from services import agentes_conhecimento as ac
    estados = set(ac.DECISOES.values()) | {"pendente", "expirada"}
    assert _chaves_de("ESTADO_PROPOSTA") == estados
