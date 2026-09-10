---
name: organizacao
description: Padrões operacionais do usuário para QUALQUER repo (web, app, automação) — fluxo git com branch por fase, commit convencional pt-BR, PR rico e merge SEMPRE autorizado pelo usuário; memória persistente por marco; migrations (T-SQL idempotente no Orquestra, MCP no Supabase); deploy com wheels offline; docs e backlog. Use ao iniciar/encerrar uma sessão de trabalho, criar branch, commitar, abrir PR, "fechar a feature", "encerrar por hoje", preparar deploy, registrar pendências, ou quando pedirem "workflow", "git flow", "commit", "pull request", "wrap up", "handoff", "checklist de encerramento". Aplica-se a Orquestra, LC Decorações, NexxaFarma e n8n LC Segurança.
---

# Organização — padrões operacionais de qualquer repo

## Quando usar
- Início de qualquer feature/fase: criar branch, decidir escopo do PR.
- Antes de commitar/abrir PR em qualquer projeto (Orquestra, LC Decorações, NexxaFarma).
- Ao fechar um marco ou encerrar a sessão de trabalho ("terminamos por hoje", "fecha isso").
- Ao preparar deploy ou registrar pendências/backlog para retomar depois.

## Processo

### 1. Branch e commits
1. Uma branch por fase/feature (`feat/...`, `fix/...`); fases F1..Fn = 1 PR por fase (padrão do gerador-spec).
2. Commits convencionais **em pt-BR**: `feat: adiciona X`, `fix: corrige Y`, `chore:`, `refactor:`. Mensagem termina com `Co-Authored-By: Claude ... <noreply@anthropic.com>`.
3. Se o repo versiona build (Orquestra versiona `dist/`): rodar o build e **commitar o dist junto** com a mudança de front — nunca deixar dist defasado do src.

### 2. Validação antes do PR
4. Front: `tsc` + `eslint` **comparando com baseline do HEAD** — critério é zero erros NOVOS, não zero absoluto — + build. Back: `pytest` na raiz (`tests/`). Detalhe da técnica: skill **testes-automatizados**.
5. Rodar **verify** (exercitar o fluxo de verdade) e **REVISÃO ADVERSARIAL multi-agente** (/code-review em nível alto) antes de todo PR — no histórico ela pegou bugs reais que a suíte não pegou.
6. Se a feature toca auth, dados pessoais, secrets ou entrada de usuário: skill **seguranca** / security-review antes do PR.

### 3. PR e merge
7. PR com descrição rica em 3 blocos: **O que muda** (por arquivo/área), **Validação** (comandos rodados + resultado vs baseline), **Deploy** (migrations? wheels? passos manuais? risco?).
8. **O USUÁRIO SEMPRE AUTORIZA O MERGE.** Apresentar o PR pronto e PARAR. Nunca `gh pr merge` sem ordem explícita nesta conversa. Nunca self-merge "porque passou tudo".

### 4. Migrations
9. Orquestra: T-SQL **idempotente** (IF NOT EXISTS / OBJECT_ID guard), numerada sequencialmente em `sql/migrations/`, aplicada na **etapa 6c do deploy.sh** (com confirmação). Conferir o último número antes de criar a próxima.
10. LC Decorações / NexxaFarma: migration via **mcp__claude_ai_Supabase__apply_migration** (nunca execute_sql para DDL), no projeto certo (LC = mozcfazauzbkcwfdispu, Nexxa = ziqnfhwkzqkvhkezkmok).

### 5. Deploy (Orquestra)
11. pip é OFFLINE (`--no-index --find-links=wheels`): toda dep Python nova exige `.whl` baixada em `api/wheels/` e **commitada** — sem isso o compose quebra em produção.
12. Antes de deployar: conferir `main == produção` (git log vs o que está rodando); se houver drift, resolver antes.
13. Migration nova ⇒ garantir que a etapa 6c vai rodar; se o deploy for parcial (só dags/, só front), dizer explicitamente o que fica pendente.

### 6. Memória, docs e backlog
14. Ao fim de CADA marco (PR aberto/mergeado, deploy, decisão importante): atualizar `/root/.claude/projects/-root/memory/` — arquivo do projeto + linha no MEMORY.md — com **status atual, gotchas descobertos e pendências de deploy**.
15. Specs e auditorias vivem em `docs/` do repo do projeto (ex.: `docs/spec-<feature>.md` via gerador-spec, `docs/auditoria-ux.md` no LC Decorações). Memória aponta para o doc, não duplica.
16. Item não-feito = backlog NA MEMÓRIA com contexto suficiente para retomar do zero: o quê, por quê, onde parou, próximo passo concreto (ex.: "PENDENTE desligar etl.yml no GH (PAT sem Actions)").

## Checklist de encerramento de sessão
- [ ] Working tree limpa ou mudanças commitadas na branch da fase (nada solto em main)
- [ ] Se mexeu no front do Orquestra: `dist/` rebuildada e commitada
- [ ] Se adicionou dep Python no Orquestra: wheel em `api/wheels/` commitada
- [ ] Migrations criadas são idempotentes e numeradas sem colisão
- [ ] PR aberto tem os 3 blocos (o que muda / validação / deploy) — e merge NÃO foi feito sem autorização
- [ ] Memória atualizada: status do marco, gotchas novos, pendências de deploy/smokes
- [ ] Backlog registrado com contexto de retomada (não só "falta X")
- [ ] Se deployou: smokes pós-deploy rodados ou registrados como PENDENTES na memória

## Integrações
- **gerador-spec**: no início — quebra a feature em fases F1..Fn, cada uma virando um PR deste fluxo.
- **testes-automatizados**: passo 4 — baseline tsc/eslint/pytest e smokes pós-deploy.
- **verify** e **/code-review** (nível alto, multi-agente): passo 5, obrigatórios antes do PR; **/simplify** opcional antes da revisão.
- **seguranca** / **security-review**: passo 6, quando a feature toca auth/dados/secrets/entrada.
- **mcp__claude_ai_Supabase__apply_migration**: migrations LC Decorações e NexxaFarma.
- **n8n** + **n8n-mcp-skills**: mudanças em workflows LC Segurança seguem essas skills; esta skill só cobre o registro na memória.

## Armadilhas conhecidas deste ambiente
- **deploy.sh do Orquestra só aplica migrations desde o PR #164** (etapa 6c). Em deploy antigo/parcial, migration pode ficar para trás — sempre confirmar que 6c rodou (o gotcha original: /finalizacao foi ao ar com migrate.py manual).
- **pip offline**: `pip install` "funcionou local" não prova nada — sem a wheel em `api/wheels/` o build de produção falha. Wheel é código versionado.
- **dist/ commitada**: conflito de merge em `dist/` se resolve rebuildar, nunca editando o bundle na mão.
- A revisão adversarial já pegou nesta base: overlay branco por especificidade CSS, `overflow-hidden` matando `position:sticky`, comentário CSS com `*/` interno quebrando o lightningcss, `err.status` vs `err.message` no apiFetch, coluna VARCHAR estourando. Não pular a revisão por "mudança pequena". Canônico: delegar ao agent `qa-adversarial` (ou `/code-review` high — um dos dois, nunca ambos na mesma mudança).
- **Baseline, não zero**: o repo tem erros pré-existentes de tsc/eslint; exigir zero absoluto trava o PR à toa, ignorar o diff com o HEAD deixa regressão passar.
- Smokes pós-deploy esquecidos somem — se não rodar na hora, registrar checklist item a item na memória (padrão do arquivo orquestra-fluxo-etapas).

## O que NÃO fazer
- NUNCA mergear PR (nem `gh pr merge`, nem merge local em main) sem autorização explícita do usuário na conversa atual.
- Não commitar direto na main; não misturar duas fases num PR só.
- Não escrever migration destrutiva ou não-idempotente; não aplicar DDL no Supabase via execute_sql.
- Não encerrar sessão sem atualizar a memória — "está no histórico do chat" não conta como registro.
- Não duplicar conteúdo de docs/ dentro da memória, nem o contrário: memória = índice + estado; docs = conteúdo.
- Não criar processo novo de review/teste aqui: usar as skills existentes (code-review, verify, testes-automatizados, seguranca).
