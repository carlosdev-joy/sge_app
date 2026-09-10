---
name: orquestra-permissao-nova-exige-relogin
description: "⚠️ GOTCHA Orquestra: tela nova com permissão nova NÃO aparece para quem já estava logado — as permissões vivem no localStorage e só atualizam no login; a correção é logout+login, não redeploy"
metadata: 
  node_type: memory
  type: project
  originSessionId: e7ce0814-6877-4a9a-acac-aed0cda2239e
  modified: 2026-08-13T18:40:00.707Z
---

**Sintoma:** deploy sai verde, a migration concede o recurso RBAC, o bundle
novo está no servidor — e a tela nova **não aparece no menu**. Fácil de
diagnosticar como "o deploy não pegou" e redeployar em vão.

**Causa:** as permissões do usuário são gravadas no `localStorage` do
navegador **no momento do login** (`zustand/persist`, chave `orquestra-auth`,
em `ui-react/src/store/auth.ts`). O `setAuth` é chamado em **um único lugar**:
`ui-react/src/pages/Login.tsx`. Não existe endpoint de refresh de permissões
nem revalidação em runtime. O menu filtra por essa lista em cache
(`ui-react/src/lib/nav.ts`, `canAccess(n.perm, perms)`).

Quem já estava logado quando a migration rodou continua com a lista ANTIGA.

**Correção: logout + login.** Não é redeploy, não é migration, não é cache do
navegador (o hash do bundle muda a cada build e invalida sozinho).

**Confirmado na prática em 2026-08-13** com a tela `/chamados`
(`tela_chamados`, migration 088): o usuário não via a tela, fez logout+login
e ela apareceu.

**Ordem de diagnóstico** quando uma tela nova não aparece:
1. logout + login (resolve na maioria das vezes);
2. `SELECT perfil_nome FROM dbo.etl_perfil_permissao WHERE recurso='<recurso>'`
   — vazio = a migration do RBAC não rodou (etapa 6c do deploy responde NÃO
   por padrão; ver [[orquestra-grafia-pipeline-name]] sobre o 6c);
3. só então suspeitar do bundle.

Vale para QUALQUER tela nova atrás de permissão — é estrutural, não um bug
pontual. Ao entregar uma feature com recurso RBAC novo, avise no texto da PR
e no roteiro de deploy que o primeiro acesso exige relogin.

Ver [[orquestra-spec-chamados-servicenow]], [[orquestra-sge-app]].
