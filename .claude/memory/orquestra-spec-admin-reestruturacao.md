---
name: orquestra-spec-admin-reestruturacao
description: "Spec Reestruturação do Admin do Orquestra — 24 abas → sub-menu lateral com 6 grupos, busca e link por aba; CONCLUÍDA 25/09/2026 (F1–F6, #449–#454, v2.4.0); deploy em produção PENDENTE"
metadata:
  type: project
---

Spec em `/opt/orquestra-dev/docs/spec-admin-reestruturacao.md`. Aprovada em 24/09/2026 com execução autônoma QA→PR→merge.

**Estado (25/09/2026):** CONCLUÍDA — F1–F6 mergeadas (#449–#454). **Deploy em produção: PENDENTE.**
- **F1 #449:** uma aba por arquivo em `ui-react/src/components/admin/abas/`.
- **F2 #450:** casca nova.
  - Registro central `ui-react/src/lib/adminNav.ts`: 6 grupos com `chavesConfig` (dono de cada chave), busca, `idsAntigos` e `SAIDAS_ADMIN`.
  - `AdminShell` com `/admin/<grupo>/<aba>`, aba carregada por lazy e última aba no localStorage.
- **F3 #451:**
  - Acesso dividido em 3 abas.
  - Triagem movida para IA; Diagnóstico agora dentro do ServiceNow.
  - Card "Webhook padrão" em Teams; Bancos & Monitoramento juntos.
- **F4 #452:** SLA foi para `/performance#sla`, o guia do Power BI para `/powerbi`, e o Fluxo DS para `/ds-console?aba=seqflow`. `LinkAdmin`/`rotuloAdmin` substituem as migalhas de navegação.
- **F5 #453:**
  - Parâmetros avançados mostra só as chaves órfãs.
  - `config_upsert`/`config_delete` devolvem 422 para chave com dono ou chave não-ASCII.
  - Rotas novas: `teams_webhook_set` e o `servicenow_set` parcial (só triagem).
  - Correções de segurança: `/config` público sem segredos; `etl_admin_manage` só admin no proxy.

**Deploy (quando o usuário pedir):**
- Sobe `dist` + API + `dags/utils/email_*`, com restart do worker só para as mensagens de texto.
- Migrations 126 (versão 2.4.0, +1 no 2º número da maior versão registrada) e 127 (10 itens de backlog, tag `admin-reestruturacao`), aplicadas pela etapa 6c do `deploy.sh` (responder **s**).
- **F6 #454:** grupo "Administração" no ⌘K, smoke em `scripts/smoke_admin.sh` e release note em `docs/release-notes/admin-reestruturacao.md`.
- ⚠️ Antes: rodar em produção `SELECT config_key FROM dbo.etl_app_config WHERE config_key LIKE '%[^A-Za-z0-9_.-]%'`.

**Why:** o admin estava moroso; as coisas "se perderam entre os menus".

**How to apply:**
- **Tela nova no admin:** entra em `ABAS_ADMIN` do `adminNav.ts`. Se ela grava chaves de `etl_app_config`, declarar `chavesConfig` E espelhar em `api/services/admin_config_donos.py` (`tests/test_admin_config_donos.py` prende os dois).
- **Padrões de segredo:** a fonte única é `PADROES_SEGREDO` em `admin_config_donos.py`.
- **Migalha "Admin › X":** usar `rotuloAdmin`/`LinkAdmin`, nunca texto solto. `test_admin_nav_registro.py` verifica o front, `api/` e `dags/`.
- **Pendências:** vão para o Backlog de produção via migration ([[regra-orquestra-pendencias-no-backlog]]).
- **Relacionados:** [[orquestra-rbac-recursos-lista-dupla]] (RBAC_RECURSOS está em `lib/rbacRecursos.ts`) e [[regra-nao-mudar-ordem-da-tela]].
