"""RBAC_RECURSOS (lib/rbacRecursos.ts) × NAV (lib/nav.ts) — o teste anti-drift do menu de perfis.

O registro de navegação (`ui-react/src/lib/nav.ts`) declara, por tela, o recurso
RBAC exigido para exibi-la (`perm: 'tela_*'`). Quem **concede** esse recurso é o
Admin, em "Perfis e Permissões" e no modal de permissões extras por usuário —
e ambos desenham seus checkboxes a partir de uma segunda lista, escrita à mão:
`RBAC_RECURSOS` em `ui-react/src/lib/rbacRecursos.ts` (até a F1 de
docs/spec-admin-reestruturacao.md morava em `pages/Admin.tsx`), renderizada
pelas abas `components/admin/abas/UsuariosTab.tsx` (modal de extras) e
`components/admin/abas/PerfisTab.tsx` (matriz de perfis — separada na F3).

Duas listas, mantidas em arquivos diferentes, sem nada prendendo uma à outra.
Foi assim que `tela_chamados` (PR #307) subiu com a tela funcionando, a migration
088 concedendo o recurso a admin/desenvolvedor/operador — e **nenhum interruptor
na tela de perfis**: quem herdou da migration via a tela, e o admin não tinha
como conceder a mais ninguém nem revogar de ninguém. Uma permissão órfã não dá
erro em lugar nenhum; ela simplesmente não aparece, e o Admin lê a lista curta
como se fosse a lista inteira.

O que estes testes prendem:

  1. **Toda `perm` do NAV tem entrada em RBAC_RECURSOS** — tela nova sem
     interruptor é permissão que o admin não governa.
  2. **Todo `tela_*` de RBAC_RECURSOS existe no NAV** — entrada órfã é
     checkbox que concede acesso a tela nenhuma (recurso renomeado/removido).
  3. **Sem rótulo duplicado e sem recurso repetido** — dois checkboxes com o
     mesmo texto, ou o mesmo recurso duas vezes, tornam a tela ambígua.

Leitura por regex sobre o fonte TypeScript: o front não tem runtime de teste
neste repo (padrão de `tests/js/*.cjs` é para componentes), e estas duas listas
são literais estáticos — regex é suficiente e não exige toolchain de node.
"""
from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
NAV_TS = RAIZ / "ui-react" / "src" / "lib" / "nav.ts"
# As listas (definição) e a aba que as RENDERIZA vivem em arquivos separados
# desde a F1 de docs/spec-admin-reestruturacao.md (extração do pages/Admin.tsx).
RBAC_TS = RAIZ / "ui-react" / "src" / "lib" / "rbacRecursos.ts"
USUARIOS_TSX = RAIZ / "ui-react" / "src" / "components" / "admin" / "abas" / "UsuariosTab.tsx"
# Matriz de perfis: aba própria desde a F3 de docs/spec-admin-reestruturacao.md.
PERFIS_TSX = RAIZ / "ui-react" / "src" / "components" / "admin" / "abas" / "PerfisTab.tsx"


def _perms_do_nav() -> set[str]:
    """Recursos exigidos pelos itens do NAV (`perm: 'tela_x'`)."""
    fonte = NAV_TS.read_text(encoding="utf-8")
    bloco = re.search(r"export const NAV: NavItem\[\] = \[(.*?)\n\]", fonte, re.S)
    assert bloco, "NAV não encontrado em lib/nav.ts — o registro mudou de forma?"
    perms = set(re.findall(r"perm:\s*'([^']+)'", bloco.group(1)))
    assert perms, "nenhuma `perm` lida do NAV — a regex ficou para trás"
    return perms


def _recursos_do_admin() -> list[tuple[str, str]]:
    """Pares (recurso, rótulo) oferecidos pelo Admin, na ordem da tela."""
    fonte = RBAC_TS.read_text(encoding="utf-8")
    bloco = re.search(
        r"const RBAC_RECURSOS: \[string, string\]\[\] = \[(.*?)\n\]", fonte, re.S)
    assert bloco, "RBAC_RECURSOS não encontrado em lib/rbacRecursos.ts"
    pares = re.findall(r"\['([^']+)',\s*'([^']*)'\]", bloco.group(1))
    assert pares, "nenhum recurso lido de RBAC_RECURSOS — a regex ficou para trás"
    return pares


# ═══════════ 1. NAV → Admin: toda tela tem interruptor ══════════════════════

def test_toda_perm_do_nav_esta_em_rbac_recursos():
    """Tela nova sem entrada aqui = permissão sem interruptor no Admin: quem já
    tem (pela migration) enxerga, e o admin não consegue conceder nem revogar."""
    faltam = _perms_do_nav() - {rec for rec, _ in _recursos_do_admin()}
    assert not faltam, (
        f"Recursos exigidos pelo NAV que não aparecem em RBAC_RECURSOS "
        f"(ui-react/src/lib/rbacRecursos.ts): {sorted(faltam)} — cadastre o par "
        f"['recurso', 'Rótulo'] para o admin poder habilitar a tela por perfil")


# ═══════════ 2. Admin → NAV: nada de checkbox órfão ═════════════════════════

def test_todo_recurso_de_tela_do_admin_existe_no_nav():
    """`tela_*` sem item no NAV = checkbox que concede acesso a tela nenhuma."""
    telas_admin = {rec for rec, _ in _recursos_do_admin() if rec.startswith("tela_")}
    orfaos = telas_admin - _perms_do_nav()
    assert not orfaos, (
        f"Recursos 'tela_*' em RBAC_RECURSOS sem item correspondente no NAV "
        f"(ui-react/src/lib/nav.ts): {sorted(orfaos)} — tela removida/renomeada?")


# ═══════════ 3. a lista em si: sem repetição, sem ambiguidade ═══════════════

def test_rbac_recursos_sem_duplicatas():
    pares = _recursos_do_admin()
    recursos = [rec for rec, _ in pares]
    duplicados = sorted({r for r in recursos if recursos.count(r) > 1})
    assert not duplicados, f"Recursos repetidos em RBAC_RECURSOS: {duplicados}"

    rotulos = [lbl for _, lbl in pares]
    ambiguos = sorted({l for l in rotulos if rotulos.count(l) > 1})
    assert not ambiguos, (
        f"Rótulos repetidos em RBAC_RECURSOS: {ambiguos} — dois checkboxes com "
        f"o mesmo texto e efeitos diferentes")


def test_chamados_tem_interruptor_no_admin():
    """Regressão direta do defeito: a tela de Chamados (PR #307) subiu com a
    migration 088 concedendo `tela_chamados`, mas sem checkbox no Admin."""
    recursos = dict(_recursos_do_admin())
    assert "tela_chamados" in recursos, (
        "tela_chamados sumiu de RBAC_RECURSOS — o Admin volta a não conseguir "
        "habilitar a tela de Chamados por perfil")
    assert recursos["tela_chamados"].strip(), "tela_chamados sem rótulo na tela"


# ═══════════ 4. agente_* nunca na matriz de PERFIS (risco 26 da spec) ═══════
#
# docs/spec-agentes-datastage.md: cada agente é concedido usuário a usuário,
# NUNCA por perfil — mesmo o admin marcando por engano na tela de perfis não
# pode dar acesso a ninguém (require_agente, em services/agentes.py, só
# reconhece o recurso vindo de `permissoes_extra`). A defesa em código é
# `require_agente`; esta é a defesa na TELA: `agente_*` simplesmente não
# aparece como checkbox onde daria pra marcá-lo num perfil inteiro.

def _variavel_do_map_que_precede(fonte: str, marcador: str, janela: int = 600) -> str:
    """Lê o `.map(` que alimenta o bloco JSX identificado por `marcador`
    (um trecho único daquele bloco, tipo uma chamada que só existe ali) —
    a variável (`RBAC_RECURSOS` ou `RBAC_RECURSOS_PERFIS`) que o CÓDIGO
    realmente renderiza, não uma reconstrução em Python que poderia bater
    por coincidência e não provar nada sobre a tela de verdade (foi o que a
    revisão adversarial da F1 achou: o teste antigo passava mesmo revertendo
    o `.map()` para `RBAC_RECURSOS` cru — só conferia a EXISTÊNCIA da
    `const`, nunca quem a consome)."""
    pos = fonte.find(marcador)
    assert pos != -1, f"marcador {marcador!r} não encontrado — o JSX mudou de forma?"
    trecho = fonte[max(0, pos - janela):pos]
    achados = re.findall(r"(RBAC_RECURSOS(?:_PERFIS)?)\.map\(", trecho)
    assert achados, (f"nenhum '<algo>.map(' encontrado nos {janela} caracteres antes de "
                     f"{marcador!r} — aumente `janela` ou confira se o JSX foi reestruturado")
    return achados[-1]  # o mais próximo do marcador


def test_matriz_de_perfis_RENDERIZA_com_RBAC_RECURSOS_PERFIS():
    """Lê o `.map()` que alimenta de verdade o bloco da matriz de perfis
    (ancorado em `togglePerm(p.perfil_nome`, exclusivo desse bloco) — não a
    definição da constante isolada."""
    fonte = PERFIS_TSX.read_text(encoding="utf-8")
    variavel = _variavel_do_map_que_precede(fonte, "togglePerm(p.perfil_nome")
    assert variavel == "RBAC_RECURSOS_PERFIS", (
        f"a matriz de perfis renderiza a partir de {variavel!r}, não de 'RBAC_RECURSOS_PERFIS' — "
        f"isso reabre o risco 26 (agente_* concedível a um perfil inteiro pela tela)")


def test_modal_de_usuario_RENDERIZA_com_RBAC_RECURSOS_completo():
    """O modal de permissões extras POR USUÁRIO precisa continuar oferecendo
    `agente_*` (é o único lugar da F1 onde dá para conceder um agente) —
    ancorado em `permDraft.has(rec)`, exclusivo desse bloco."""
    fonte = USUARIOS_TSX.read_text(encoding="utf-8")
    variavel = _variavel_do_map_que_precede(fonte, "checked={herdado || permDraft.has(rec)}")
    assert variavel == "RBAC_RECURSOS", (
        f"o modal de permissões extras passou a renderizar {variavel!r} — sem a lista "
        f"completa, não haveria como conceder agente_* a ninguém")


def _recursos_da_matriz_de_perfis() -> list[str]:
    """`RBAC_RECURSOS_PERFIS` — a lista que alimenta SÓ a matriz de perfis
    (lib/rbacRecursos.ts); é derivada de RBAC_RECURSOS, filtrando `agente_*`. Usada
    pelos testes de CONTEÚDO da lista — a prova de que é ELA quem é
    renderizada está nos dois testes acima."""
    fonte = RBAC_TS.read_text(encoding="utf-8")
    bloco = re.search(
        r"const RBAC_RECURSOS_PERFIS = RBAC_RECURSOS\.filter\((.*)$", fonte, re.MULTILINE)
    assert bloco, ("RBAC_RECURSOS_PERFIS não encontrado em lib/rbacRecursos.ts — a matriz de "
                   "perfis voltou a usar RBAC_RECURSOS direto? Isso reabriria o risco 26.")
    assert "agente_" in bloco.group(1), (
        "RBAC_RECURSOS_PERFIS não filtra mais por 'agente_' — confira o predicado do .filter()")
    return [rec for rec, _ in _recursos_do_admin() if not rec.startswith("agente_")]


def test_agente_recurso_nao_aparece_na_matriz_de_perfis():
    recursos_admin = dict(_recursos_do_admin())
    agentes = [rec for rec in recursos_admin if rec.startswith("agente_")]
    assert agentes, ("nenhum recurso 'agente_*' em RBAC_RECURSOS — este teste ficou sem "
                     "o que proteger; se os agentes foram renomeados, atualize o teste")
    matriz = set(_recursos_da_matriz_de_perfis())
    vazando = matriz & set(agentes)
    assert not vazando, (
        f"recurso(s) de agente na matriz de PERFIS: {sorted(vazando)} — um admin poderia "
        f"conceder o agente a um perfil inteiro pela tela, contrariando 'usuário a usuário' "
        f"(risco 26 de docs/spec-agentes-datastage.md)")


def test_tela_agentes_e_recurso_normal_na_matriz_de_perfis():
    """`tela_agentes` (diferente de `agente_*`) é um `tela_*` comum — deve
    aparecer na matriz de perfis como qualquer outra tela (é a correção da
    5ª rodada da spec: reverte o "nasce só no admin, nada mais" para o
    mecanismo padrão)."""
    assert "tela_agentes" in _recursos_da_matriz_de_perfis()
