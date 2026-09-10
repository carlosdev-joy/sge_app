---
name: gerador-spec
description: Transforma o resultado de uma entrevista de requisitos (ou um pedido direto) numa especificação executável com fases F1..Fn mergeáveis, cada uma com PR própria, critérios de aceite e validação. Use quando o usuário pedir para "especificar", "criar spec/especificação", "planejar feature", "quebrar em fases", "write a spec", "plan this feature", "break into phases/milestones", ou quando uma entrevista de descoberta acabou de terminar e precisa virar plano. Aplica-se a projetos web e app (Orquestra, LC Decorações, NexxaFarma) e automações (n8n LC Segurança). A spec é salva em docs/spec-<feature>.md no repo do projeto e resumida na memória persistente.
---

## Quando usar
- Ao fim de uma entrevista de descoberta de feature, para consolidar as respostas num plano executável.
- Quando o usuário descrever uma feature nova e pedir plano, spec, fases ou "como você faria isso".
- Antes de começar QUALQUER feature multi-PR — o fluxo do usuário é sempre fases F1..Fn com PR por fase e merge autorizado por ele.
- NÃO usar para bugfix pontual de 1 PR: nesse caso vá direto ao código com validação + revisão adversarial.

## Processo
1. **Identifique o projeto e a stack real** (nunca invente stack genérica):
   - **Orquestra** (`/opt/orquestra-dev`, repo `carlosdev-joy/sge_app`): React 19 + Tailwind 3.4 + Vite/rolldown (tokens semânticos `canvas/panel/edge/ink` claro+escuro definidos em `ui-react/src/index.css` + `tailwind.config.js`, consumidos por `components/ui/*`), FastAPI + pyodbc/SQL Server, Airflow para orquestração. Seção `/caixa-seguro` tem tema shadcn/Radix escopado em `.caixa-theme`.
   - **LC Decorações / NexxaFarma**: Next.js + Supabase cloud (migrations via MCP Supabase).
   - **Automações LC Segurança**: n8n em swarm de produção — a spec referencia workflows, mas a construção é da skill `n8n` + pack `n8n-mcp-skills`.
2. **Leia o código antes de propor arquitetura**: grep/Read nos módulos que a feature toca. Arquitetura proposta cita arquivos e padrões EXISTENTES (ex.: `apiFetch`, tabelas `etl_*`, `deploy.sh`), não abstrações.
3. **Escreva a spec usando o template abaixo**, na íntegra — sem pular seções. Escopo OUT é obrigatório e explícito.
4. **Quebre em fases F1..Fn** seguindo estas regras invioláveis:
   - Cada fase é pequena, mergeável sozinha e deixa a main funcional (nada de "meia feature quebrada na main").
   - Cada fase = entregável concreto + PR própria + critérios de aceite verificáveis + validação (tsc + eslint comparado com baseline do HEAD [zero erros NOVOS] + build + pytest) + revisão adversarial multi-agente ANTES da PR.
   - Ordem típica: F1 = fundação (migration + modelo + endpoint mínimo) → F2..Fn-1 = UI/lógica incremental → Fn = polimento + smoke.
   - Migrations SQL Server sempre idempotentes (guarda `IF NOT EXISTS` / `IF COL_LENGTH(...) IS NULL`) em `sql/migrations`, aplicadas na etapa 6c do `deploy.sh`.
5. **Riscos com mitigação**: pelo menos 3, específicos (dado, deploy, UX, permissão) — nada de "risco de atraso".
6. **Plano de smoke pós-deploy**: checklist letrada (a, b, c...) de ações manuais no ambiente real, no estilo que o usuário já usa (ex.: smokes do fluxo/etapas).
7. **Salve e registre**: escreva em `docs/spec-<feature>.md` no repo do projeto; adicione/atualize um tópico na memória persistente (`/root/.claude/projects/-root/memory/`) apontando para a spec e o estado (rascunho/aprovada/em execução).
8. **Apresente ao usuário** um resumo de 10-15 linhas (visão + fases + riscos-chave) e pergunte o que ajustar antes de aprovar. O usuário autoriza o início — assim como autoriza todo merge.

## Template da spec (copie na íntegra para docs/spec-<feature>.md)
```markdown
# Spec: <Feature> — <Projeto>
Data: AAAA-MM-DD · Status: rascunho | aprovada | em execução (Fx) | concluída

## 1. Visão
2-4 frases: problema, para quem, o que muda quando estiver pronto.

## 2. Escopo
**IN:** bullets do que ENTRA.
**OUT (explícito):** bullets do que NÃO entra nesta feature (e onde fica, se backlog).

## 3. Arquitetura proposta
- Front: componentes/rotas novas e existentes tocadas (caminhos reais).
- Back: endpoints/serviços (caminhos reais em api/).
- Dados: tabelas/views/procs; conexões usadas.
- Orquestração/automação: DAGs Airflow ou workflows n8n, se houver.
- Decisões e alternativas descartadas (1 linha cada).

## 4. Modelo de dados
Tabelas/colunas/tipos + nome do arquivo de migration (NNN_descricao.sql, idempotente).
Atenção a larguras VARCHAR e collation vindas da origem.

## 5. Fases
### F1 — <nome curto>
- Entregável: ...
- Inclui: bullets de tarefas.
- Critérios de aceite: bullets verificáveis (dado X, quando Y, então Z).
- Validação: tsc + eslint (baseline HEAD, zero erros novos) + build + pytest.
- Revisão adversarial multi-agente antes da PR. PR: `feat: <descricao em pt-BR>`.
### F2 — ... (repetir o bloco)

## 6. Riscos e mitigações
| # | Risco | Impacto | Mitigação |
|---|-------|---------|-----------|

## 7. Smoke pós-deploy
a) ... b) ... c) ... (ações manuais no ambiente real, com resultado esperado)

## 8. Pendências e decisões em aberto
Perguntas que ainda dependem do usuário.
```

## Checklist (antes de entregar a spec)
- [ ] Stack citada é a REAL do projeto (conferida no código, não de memória).
- [ ] Escopo OUT preenchido com itens que o usuário poderia supor que entram.
- [ ] Toda fase cabe numa PR revisável (< ~500 linhas de diff útil como alvo) e deixa a main sã.
- [ ] Toda fase tem critérios de aceite verificáveis + bloco de validação + revisão adversarial.
- [ ] Migrations nomeadas, idempotentes, e citando a etapa 6c do deploy.sh (Orquestra) ou MCP Supabase (Next.js).
- [ ] Dependência Python nova? Fase inclui gerar wheel em `api/wheels/` (pip offline) e versionar no git.
- [ ] Mexe no front do Orquestra? Fase lembra que `dist/` é commitada e usa tokens `canvas/panel/edge/ink` (claro+escuro).
- [ ] Smoke pós-deploy letrado e executável manualmente.
- [ ] Spec salva em `docs/spec-<feature>.md` + memória persistente atualizada com id/estado.
- [ ] Resumo apresentado ao usuário com pergunta explícita de aprovação.

## Integrações
- **ui-ux-pro-max:ui-ux-pro-max** e **ui-ux-pro-max:ui-styling**: consultar na seção de arquitetura quando a feature tem UI relevante (layout, componentes shadcn/Radix, dark mode) — em especial `/caixa-seguro` (tema escopado `.caixa-theme`).
- **ui-ux-pro-max:design-system**: se a spec criar tokens/componentes novos no design system do Orquestra.
- **dataviz**: se a spec incluir gráficos, KPIs ou dashboards — a fase de UI deve citar o validador de paleta.
- **n8n** + **n8n-mcp-skills:n8n-workflow-patterns**: se a feature envolver automação no swarm LC Segurança — a spec só REFERENCIA o workflow; construção/validação é dessas skills.
- **claude-api**: se a feature usar LLM (ex.: assistentes IA do caixa-seguro) — consultar ANTES de fixar modelo/custo na spec.
- **/code-review**, **security-review** e **verify** (harness): citados no bloco de validação de cada fase como parte da revisão adversarial; **verify** para exercitar o fluxo de ponta a ponta antes da PR.
- **/simplify**: passar nas fases finais de polimento.

## Armadilhas conhecidas deste ambiente (incorporar aos riscos quando tocarem a área)
- **pip OFFLINE no deploy do Orquestra** (`--no-index --find-links=wheels`): dep nova sem wheel em `api/wheels/` quebra o build do compose em produção. Toda fase que adiciona dep Python inclui o wheel no diff.
- **deploy.sh só aplica migrations na etapa 6c** (adicionada na PR #164): specs anteriores a isso assumiam migrate.py manual — não repetir o erro; a spec cita 6c.
- **Migration não idempotente re-executa e quebra**: sempre `IF NOT EXISTS`/`IF COL_LENGTH`. Larguras VARCHAR da origem podem estourar no destino (bug real da cópia de dados, PR #161 — DDL com pad).
- **CSS**: especificidade já causou overlay branco em produção; `overflow-hidden` em ancestral mata `position: sticky`; comentário CSS contendo `*/` interno quebra o lightningcss. Fases de UI herdam esses três pontos nos critérios de aceite.
- **apiFetch**: erros carregam `err.status` vs `err.message` — contrato já causou bug; specs de endpoint novo definem o shape de erro esperado no front.
- **`dist/` commitada**: fase de front que esquece o rebuild da dist entrega PR "invisível" em produção.
- **Revisão adversarial não é opcional**: foi ela que pegou todos os bugs acima antes de produção. Nenhuma fase fecha sem ela.

## O que NÃO fazer
- NÃO propor stack, libs ou serviços que o projeto não usa (nada de Prisma no Orquestra, nada de Redux, nada de CDN externo).
- NÃO criar fase "big bang" que só funciona quando tudo estiver pronto — cada fase merge sozinha.
- NÃO fazer merge nem prometer merge automático: o usuário SEMPRE autoriza o merge de cada PR.
- NÃO duplicar o que skills existentes já cobrem: automação n8n é da skill `n8n`/`n8n-mcp-skills`; design é do `ui-ux-pro-max`; gráficos são do `dataviz`.
- NÃO escrever spec sem escopo OUT, sem riscos ou sem smoke — essas seções são as que evitam retrabalho.
- NÃO salvar a spec fora do repo do projeto (nem só na memória): o arquivo canônico é `docs/spec-<feature>.md`; a memória guarda apenas o resumo e o estado.
- NÃO começar a implementar antes de o usuário aprovar a spec.
