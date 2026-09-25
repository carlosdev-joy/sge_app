# 🧭 Admin reorganizado — sub-menu, busca e link por aba (v2.4.0)

**Compatibilidade:** sem dependência nova (nem pip, nem npm) | SQL Server | Airflow 2.x
**Migrations:** **126** (versão 2.4.0 em Admin › Versões) e **127** (pendências no Backlog) — etapa 6c, responder **s**
**Spec:** `docs/spec-admin-reestruturacao.md` (F1–F6, concluída)
**Manual:** `docs/MANUAL_USUARIO.md` §4 (navegação do Admin, ⌘K) e §4.1 (Parâmetros avançados)
**PRs:** #449 F1 · #450 F2 · #451 F3 · #452 F4 · #453 F5 · F6 (esta nota, ⌘K, migrations, smoke)

---

## 📋 Resumo

O Admin tinha **24 abas em 4 grupos**, "Sistema" sozinho com 12, e a aba Configurações era uma
tabela crua com 36 chaves de 8 assuntos. O mesmo assunto aparecia em vários lugares (IA em 5,
mensageria em 4, bancos em 3) e a aba não ficava no endereço: o F5 voltava para Configurações.

Agora o Admin tem um **sub-menu lateral com 6 grupos por assunto**, **busca** (inclusive pelo nome
do parâmetro) e **um endereço por aba**. Cada parâmetro fica na aba do seu assunto, e o que não é
administração saiu do Admin.

```
Administração
┌── sub-menu ─────────────────┐ ┌──────────────────────────────────────┐
│ [Buscar no admin…      /]   │ │ Comunicação › E-mail      Copiar link │
│ ACESSO                      │ │ Remetente, domínios permitidos, …     │
│   Usuários                  │ │ ───────────────────────────────────── │
│   Perfis e Permissões       │ │ [conteúdo da aba, intacto]            │
│   Roles do Airflow          │ │                                       │
│ INTELIGÊNCIA ARTIFICIAL     │ │                                       │
│ COMUNICAÇÃO                 │ │                                       │
│ ▌ E-mail                    │ │                                       │
│ …                           │ │                                       │
└─────────────────────────────┘ └──────────────────────────────────────┘
```

> **Impacto para o administrador:** achar a aba em 1 clique ou 1 busca; mandar o link de uma aba;
> o F5 não perde o lugar. **Impacto para a segurança:** o editor genérico deixou de gravar chave
> que tem tela própria (fechava o desvio das validações das abas), segredos saem mascarados em
> Parâmetros avançados e somem do `/config` público.

---

## 🗺️ Onde foi parar cada coisa

| Antes | Agora |
|---|---|
| Usuários & Perfis (uma aba) | Acesso › **Usuários** · **Perfis e Permissões** · **Roles do Airflow** |
| IA | Inteligência Artificial › **Provedor** |
| Triagem (dentro de ServiceNow) | Inteligência Artificial › **Triagem de chamados** |
| Sonda de descoberta | Integrações & Dados › ServiceNow › seção **Diagnóstico** |
| Notificações + "Testar Webhook" (em Configurações) | Comunicação › **Teams** (card *Webhook padrão*) |
| Servidor · Monitoramento | Integrações & Dados › **Bancos & Monitoramento** |
| Utilitários | Integrações & Dados › **Servidor DataStage (SFTP)** |
| Agendamento · Inventário de DAGs | Pipelines & Ambiente › **Calendários & Blackout** · **DAGs do sistema** |
| Configurações | Sistema › **Parâmetros avançados** — só chaves **sem tela própria** |
| Relatório SLA | `/performance` › seção **Aderência ao SLA** (fim da tela) |
| Guia de acessos do Power BI | `/powerbi` › seção recolhível **Como liberar acessos** |
| Fluxo DS | removida — é a aba **Fluxo (XML)** do Console DataStage |

Links e favoritos antigos (`/admin` com os ids velhos, `…/sla`, `…/fluxo_ds`) redirecionam.

---

## 🚚 O que entra

| Fase | O quê |
|---|---|
| **F1** #449 | `pages/Admin.tsx` (4.255 linhas) vira uma aba por arquivo em `components/admin/abas/`, sem mudança visual |
| **F2** #450 | Registro central `lib/adminNav.ts`, casca `AdminShell` (sub-menu 240 px sticky, busca combobox com `/`, ↑/↓, Enter, Esc; Copiar link; ErrorBoundary por aba; seletor + Sheet abaixo de 1024 px), Admin e abas em `React.lazy`, última aba lembrada |
| **F3** #451 | Remanejamentos: Acesso em 3 abas, Triagem em IA, Diagnóstico em ServiceNow, webhook padrão em Teams, Bancos & Monitoramento |
| **F4** #452 | SLA, Power BI e Fluxo DS fora do Admin; migalhas "Admin › …" de outras telas viram links; MANUAL |
| **F5** #453 | Parâmetros avançados só com chaves órfãs, agrupadas; `config_upsert`/`config_delete` recusam (422) chave com dono; rotas próprias de Teams e Triagem; segredos mascarados |
| **F6** | ⌘K com o grupo **Administração**; migrations 126/127; `scripts/smoke_admin.sh`; esta nota |

---

## ⌨️ ⌘K (Ctrl+K)

A busca geral de qualquer tela ganhou o grupo **Administração**, depois de Pipelines, Etapas e
Catálogo. É a **mesma busca** do sub-menu (registro `lib/adminNav.ts`, no navegador, sem API):
"e-mail" → *Comunicação › E-mail*, `teams_webhook` → *Comunicação › Teams*, "agentes" →
*Inteligência Artificial › Agentes*. Até 6 abas por busca; ↑/↓ e Enter como nos outros grupos.
Só aparece para quem tem `tela_admin`.

---

## 🚀 Deploy

| Passo | O quê |
|---|---|
| 6c | Migrations **126** e **127** → **s** (as duas rodam 2× sem duplicar; a 126 é chaveada pelo título, a 127 por título de cada item) |
| `api/` | **sim** (F3–F5: trava de chave com dono, `teams_webhook_set`, máscaras, `/config` sem segredo) |
| `dags/` | **sim** — textos de `dags/utils/email_*` e `etl_servicenow_sync.py` (F3/F4); ⚠️ `dags/utils/` exige **restart do worker** |
| `dist/` | **sim** |
| `.env` | nada novo |
| `config/` | **n** |
| Antes | Conferir a maior versão em produção (Admin › Versões): a 126 soma +1 no **segundo** número dela (2.3.2 → **2.4.0**) |

---

## ✅ Conferência pós-deploy

```sql
SELECT TOP 3 versao, titulo FROM dbo.etl_versao_ferramenta ORDER BY id DESC;   -- 2.4.0 no topo
SELECT config_value FROM dbo.etl_app_config WHERE config_key = 'app_version';   -- a mesma
SELECT COUNT(*) FROM dbo.etl_backlog WHERE tags = N'admin-reestruturacao';      -- 10
```

**Smoke automatizado** (só leitura e recusas; senha pelo ambiente):

```bash
ORQ_API=https://<servidor>/orquestra ORQ_UI=https://<servidor> \
ORQ_USUARIO=<admin> ORQ_SENHA='…' bash scripts/smoke_admin.sh
```

Confere login, `/config` sem segredo, `config_list` mascarado, 422 para `email_remetente`,
`teams_webhook_url` e chave *fullwidth*, 401 sem sessão e a SPA nos endereços novos — e imprime
o checklist manual da spec §8 (a–k), que precisa do navegador.

---

## 🧭 Próximos passos (Backlog — migration 127, tag `admin-reestruturacao`)

| Prioridade | Item |
|---|---|
| P2 bug | `servicenow.url_valida` aceita outro host via `#`/`?` e manda a senha por Basic auth |
| P2 debt | `/admin/test-webhook`: allowlist de hosts do Teams/Power Automate; sem trecho da URL (`sig`) nem traceback na resposta |
| P2 bug | DAG `etl_admin_manage` confia em `conf.requested_by` (rerun por `clearTaskInstances`, role Op) |
| P3 debt | DAGs geradas ainda citam "Admin > Acessos e Comunicacao > Notificacoes" — republicar |
| P3 feature | RBAC por aba: esconder/sinalizar abas que exigem `acao_admin` |
| P3 debt | Concessão de agente em dois lugares, ambos via `user_perm_set` (sobrescreve a lista) |
| P3 bug | Clicar "Admin" na sidebar dentro de uma aba empilha entrada no histórico |
| P3 bug | Chunk do Admin removido por deploy cai no ErrorBoundary global com erro cru |
| P3 bug | Badge "Canal padrão: não configurado" ignora a env `TEAMS_WEBHOOK_URL_CVP` |
| P3 debt | `servicenow_proxy` em claro e aceitando `usuário:senha@` na URL |
