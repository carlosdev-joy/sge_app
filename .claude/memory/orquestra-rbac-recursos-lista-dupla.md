---
name: orquestra-rbac-recursos-lista-dupla
description: "⚠️ GOTCHA Orquestra: o cadastro de perfis desenha os checkboxes de RBAC_RECURSOS (Admin.tsx), uma SEGUNDA lista à mão — tela nova que só entra no NAV vira permissão sem interruptor, que o admin não consegue conceder nem revogar"
metadata: 
  node_type: memory
  type: project
  originSessionId: b6fa286c-27e3-404c-8ac0-af606e0cefb3
  modified: 2026-08-13T18:59:09.519Z
---

**Sintoma:** a tela nova aparece e funciona para quem a migration contemplou,
mas em **Admin → Perfis e Permissões** não existe checkbox dela. O admin não
consegue habilitar para mais ninguém, nem revogar de ninguém. Nada dá erro — a
lista curta se apresenta como se fosse a lista inteira.

**Causa: são DUAS listas, em arquivos diferentes, sem nada prendendo uma à outra.**

| lista | arquivo | papel |
|---|---|---|
| `NAV` | `ui-react/src/lib/nav.ts` | declara `perm: 'tela_x'` por rota — **exige** o recurso |
| `RBAC_RECURSOS` | `ui-react/src/pages/Admin.tsx` (topo) | pares `['recurso','Rótulo']` — **concede** o recurso |

`RBAC_RECURSOS` alimenta os **dois** pontos de concessão: o card de cada perfil
e o modal de permissões extras por usuário. Recurso ausente dali não tem
interruptor em lugar nenhum.

**Checklist de tela nova atrás de permissão — são QUATRO lugares, não dois:**
1. `NAV` (`lib/nav.ts`) — item + `perm`
2. `App.tsx` — elemento da rota
3. **`RBAC_RECURSOS` (`pages/Admin.tsx`) — o esquecido**
4. migration concedendo o recurso aos perfis-semente (`etl_perfil_permissao`)

**Aconteceu com `tela_chamados`** (PR #307 + migration 088, 2026-08-13):
1/2/4 feitos, 3 esquecido. Corrigido na **PR #310** (`4cc38c0`, MERGEADA
2026-08-13; ⚠️ deploy ainda não confirmado), que também criou `tests/test_rbac_recursos_admin.py` — o anti-drift que prende
NAV ↔ RBAC_RECURSOS nas duas direções (conferido por mutação: falha com a linha
removida). A partir dele, o esquecimento passa a quebrar a suíte.

**Nenhuma permissão se perde por isso.** Tanto o save de perfil quanto o de
permissões extras partem, no front, do conjunto que veio do banco — o recurso
sem checkbox sobrevive a um "Salvar". O estrago é de **governança**, não de
dados. E o backend (`api/routers/admin.py`) não valida recurso contra lista
fixa: aceita qualquer string, então nunca reclama da ausência.

**Não confundir com [[orquestra-permissao-nova-exige-relogin]]:** lá o
interruptor existe e o cache do `localStorage` é que está velho (correção =
logout+login). Aqui o interruptor **não existe**. Ordem de diagnóstico quando a
tela não aparece: relogin → checkbox existe no Admin? → `etl_perfil_permissao`
no banco → bundle.

Ver [[orquestra-spec-chamados-servicenow]], [[orquestra-sge-app]].
