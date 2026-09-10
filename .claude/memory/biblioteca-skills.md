---
name: biblioteca-skills
description: "Biblioteca pessoal de skills + agents do usuário em ~/.claude (nível global, vale p/ todos os projetos deste ambiente)"
metadata: 
  node_type: memory
  type: reference
  originSessionId: 80171faf-30f5-47aa-9006-0fee8285796c
---

Criada em 2026-07-09 uma biblioteca de skills de nível de usuário em `/root/.claude/skills/` e agents em `/root/.claude/agents/`, válida para TODOS os projetos ([[orquestra-sge-app]], LC Decorações, NexxaFarma, n8n LC Segurança). Gerada e verificada por workflow multi-agente (13 escritores + 3 verificadores).

**11 skills novas** (+ a pré-existente [[n8n-mcp-tooling]] `n8n`, intacta): `entrevista-projeto` (descoberta em blocos antes de qualquer projeto) → `gerador-spec` (spec F1..Fn em docs/spec-<feature>.md) · `novo-projeto` (fio condutor greenfield que encadeia o resto) · `seguranca`, `performance`, `design-impactante-corporativo` (orquestra ui-ux-pro-max+dataviz, NÃO duplica), `testes-automatizados` (baseline vs HEAD, nunca zero absoluto), `automacoes` (roteia n8n/Airflow/cron/Actions/schedule), `inovacao`, `organizacao` (git flow, memória, deploy wheels offline), `apps-mobile` (Android+iOS do zero, PWA/Expo/Flutter).

**2 agents** (delegáveis, read-only, sem Write/Edit): `qa-adversarial` (verificador que REFUTA implementação antes da PR — o padrão que pegou os bugs reais deste ambiente) e `auditor-seguranca` (auditoria OWASP/LGPD sob demanda; audita CÓDIGO, sinaliza checagens ao-vivo p/ o Claude principal rodar via MCP).

**Princípios de design da biblioteca:** cada skill DELEGA aos plugins existentes (ui-ux-pro-max, dataviz, claude-api, n8n-mcp-skills) e às embutidas (/code-review, verify, security-review, /simplify) em vez de reimplementar; os gotchas REAIS do ambiente estão codificados nas skills (pip offline/wheels em api/wheels, etapa 6c do deploy.sh, dist/ commitada, tokens canvas/panel/edge/ink em index.css+tailwind.config, .caixa-theme×border por especificidade, overflow-clip vs sticky, */ no comentário CSS quebra lightningcss, err.status vs err.message do apiFetch, VARCHAR×token Fernet). Revisão canônica pré-PR = agent qa-adversarial (ou /code-review high — um dos dois).

Ativação: automática por semelhança com a `description` (por isso as descriptions têm gatilhos pt+en e tipos de projeto), ou manual via `/<nome>`. Para editar/estender: `Write` direto no arquivo (frontmatter YAML só name+description; agents aceitam +tools).
