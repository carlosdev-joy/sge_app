"""RBAC_RECURSOS (Admin.tsx) × NAV (lib/nav.ts) — o teste anti-drift do menu de perfis.

O registro de navegação (`ui-react/src/lib/nav.ts`) declara, por tela, o recurso
RBAC exigido para exibi-la (`perm: 'tela_*'`). Quem **concede** esse recurso é o
Admin, em "Perfis e Permissões" e no modal de permissões extras por usuário —
e ambos desenham seus checkboxes a partir de uma segunda lista, escrita à mão:
`RBAC_RECURSOS` em `ui-react/src/pages/Admin.tsx`.

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
ADMIN_TSX = RAIZ / "ui-react" / "src" / "pages" / "Admin.tsx"


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
    fonte = ADMIN_TSX.read_text(encoding="utf-8")
    bloco = re.search(
        r"const RBAC_RECURSOS: \[string, string\]\[\] = \[(.*?)\n\]", fonte, re.S)
    assert bloco, "RBAC_RECURSOS não encontrado em pages/Admin.tsx"
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
        f"(ui-react/src/pages/Admin.tsx): {sorted(faltam)} — cadastre o par "
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
