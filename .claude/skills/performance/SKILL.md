---
name: performance
description: Auditoria e otimização de performance em projetos web, app e automação — bundle size, code-splitting, lazy routes, re-renders, Web Vitals (LCP/INP/CLS), queries N+1, índices SQL Server e Supabase, RLS custosa, paginação e cache. Use quando o usuário pedir para otimizar, acelerar, "deixar mais rápido", investigar lentidão, reduzir bundle, melhorar latência ou auditar performance ("optimize", "slow", "performance audit", "speed up", "bundle size", "profiling", "Web Vitals"). Cobre Orquestra (React 19 + FastAPI + SQL Server), LC Decorações e NexxaFarma (Next.js + Supabase). Regra de ouro: nunca otimizar sem medir antes e depois.
---

## Quando usar

- Usuário reporta lentidão (tela, endpoint, query, build) ou pede otimização/auditoria de performance.
- Warning de chunk grande no build do Orquestra (chunk conhecido de 2,7MB no rolldown) ou bundle crescendo.
- p95 de API alto, query SQL Server lenta, advisor do Supabase acusando índice ausente ou RLS custosa.
- Web Vitals ruins (LCP/INP/CLS) em LC Decorações / NexxaFarma.
- **Fora de escopo**: workflow n8n lento → delegar às skills `n8n` e `n8n-mcp-skills:n8n-workflow-patterns` / `n8n-code-javascript`. NÃO tratar n8n aqui.

## Processo

1. **Definir sintoma + métrica-alvo em número** ("lista de execuções demora" → "p95 do GET /execucoes < 500ms"). Sem número, não há otimização — há achismo.
2. **Medir ANTES** (guardar os números brutos):
   - Front: `npm run build` em modo produção (tamanhos por chunk do rolldown), `npx lighthouse <url> --preset=desktop` contra build de produção servida (nunca o dev server do Vite), React DevTools Profiler para re-renders.
   - Back (Orquestra): `SET STATISTICS TIME, IO ON` + plano de execução real no SQL Server; cronometrar o endpoint com parâmetros REAIS de produção (parameter sniffing muda o plano).
   - Supabase: `mcp__claude_ai_Supabase__get_advisors` (performance) + `EXPLAIN ANALYZE` via `execute_sql`.
3. **Formular UMA hipótese** ("o N+1 no loop de etapas gera 200 queries", "o editor de fluxo entra no chunk inicial").
4. **Mudar UMA coisa.** Um commit `perf:` por mudança. Alvos típicos:
   - Front: `React.lazy` + `Suspense` por rota pesada (editor de fluxo, /caixa-seguro, telas com gráficos); `staleTime` no TanStack Query para dados quase estáticos (conexões, catálogos, permissões) e `refetchOnWindowFocus: false` em listagens pesadas; imagens com dimensões explícitas + `loading="lazy"`; `memo`/`useMemo` SÓ no componente que o Profiler apontou.
   - Rolldown/code-split: quebrar chunk quando ele passa ~250–300KB gzip E não pertence à rota inicial. Preferir lazy route; `manualChunks`/`advancedChunks` só para vendor pesado compartilhado (charts, editor). Rota inicial nunca vira lazy.
   - Back: eliminar N+1 com JOIN único ou `IN (...)`; paginação `TOP N` / `OFFSET-FETCH` ordenado (nunca tabela inteira pro front paginar); índice composto no padrão do projeto (ex.: `IX_caixa_chat_matricula`) via migration T-SQL IDEMPOTENTE (`IF NOT EXISTS` em `sys.indexes`) em `sql/migrations`; evitar `SELECT *`; reaproveitar conexão pyodbc dentro do request (abrir/fechar por query custa caro).
   - Supabase: índice nas colunas filtradas por policy; reescrever RLS com `(select auth.uid())` em vez de `auth.uid()` por linha; aplicar via `apply_migration`.
5. **Medir DEPOIS** com exatamente a mesma metodologia e os mesmos parâmetros.
6. **Registrar antes/depois** no corpo do PR (tabela: métrica, antes, depois, delta) e na memória se for aprendizado estrutural. Commit convencional pt-BR (`perf(front): lazy route do editor de fluxo`).
7. **Validação padrão do usuário**: tsc + eslint (comparar com baseline do HEAD — zero erros NOVOS) + build + pytest na raiz; rodar `verify` no fluxo afetado; revisão adversarial multi-agente antes do PR. O usuário SEMPRE autoriza o merge.

### Orçamentos padrão (usar como critério de aceite)

| Métrica | Orçamento |
|---|---|
| Bundle inicial por rota nova | < 300KB gzip |
| Resposta de API | < 500ms p95 |
| LCP | < 2,5s |
| INP | < 200ms |
| CLS | < 0,1 |
| Queries por request | sem N+1 (contagem constante, não O(linhas)) |

## Checklist

- [ ] Métrica-alvo definida em número antes de tocar em código
- [ ] Medição ANTES salva (saída do build / lighthouse / STATISTICS IO / EXPLAIN)
- [ ] Exatamente UMA mudança neste commit
- [ ] Medição DEPOIS com mesma metodologia e parâmetros reais
- [ ] Delta registrado no PR (tabela antes/depois)
- [ ] Orquestra: `dist/` rebuildada e COMMITADA (produção não vê a otimização sem isso)
- [ ] Orquestra: índice novo é migration idempotente em `sql/migrations` (deploy.sh etapa 6c aplica)
- [ ] Orquestra: dep Python nova (se inevitável) tem wheel em `api/wheels/` versionada (pip é OFFLINE)
- [ ] Supabase: `get_advisors` re-rodado depois da mudança (advisor sumiu?)
- [ ] tsc + eslint sem erros novos vs baseline, build ok, pytest ok
- [ ] Revisão adversarial feita antes do PR; merge aguarda autorização do usuário

## Integrações

- `mcp__claude_ai_Supabase__get_advisors` / `execute_sql` / `apply_migration` — diagnóstico e correção em LC Decorações e NexxaFarma.
- `verify` — exercitar o fluxo real afetado após a otimização (lazy route carrega? paginação retorna os mesmos dados?).
- `/code-review` + revisão adversarial multi-agente — obrigatórios antes do PR, como em qualquer feature.
- `/simplify` — depois da otimização, para remover complexidade morta que sobrou (memo desnecessário, código duplicado).
- `dataviz` — se for apresentar os resultados antes/depois em gráfico ou dashboard.
- `ui-ux-pro-max:ui-ux-pro-max` — quando a otimização mexer em UI percebida (skeletons, loading states, Suspense fallbacks).
- `n8n` + `n8n-mcp-skills:*` — performance de workflows n8n é 100% delas; esta skill não cobre.

## Armadilhas conhecidas deste ambiente

- **Medir no dev server do Vite não vale nada**: sem minificação, sem split real, sem gzip. Sempre `npm run build` + servir a `dist/`.
- **`dist/` é commitada no Orquestra**: otimização de bundle sem rebuild+commit da dist = produção inalterada. E o diff gigante da dist após mudar code-split é esperado — não é erro.
- **Code-split muda a ordem de injeção de CSS**: já houve overlay branco por especificidade no tema escopado `.caixa-theme` (shadcn/Radix). Após quebrar chunk, smoke visual no /caixa-seguro e nos temas claro+escuro (tokens canvas/panel/edge/ink).
- **`overflow-hidden` mata `position:sticky`** e **comentário CSS com `*/` interno quebra o lightningcss** — dois bugs reais pegos pela revisão adversarial; cuidado ao aplicar `contain`/`content-visibility` por perf.
- **pip OFFLINE no deploy** (`--no-index --find-links=wheels`): lib de profiling nova exige wheel em `api/wheels/`. Preferir stdlib (`cProfile`, `time.perf_counter`) para não inflar o repo.
- **Parameter sniffing no SQL Server**: o plano medido com parâmetro "bonito" diverge do de produção. Medir com valores reais (matrícula/CPF de verdade, volumes reais — o módulo de cópia lida com 139M linhas).
- **VARCHAR estourando** já causou incidente (NUM_CPF_CNPJ): ao criar índice com colunas incluídas ou coluna computada, conferir larguras de origem.
- **Contrato do `apiFetch`** (`err.status` vs `err.message`): ao adicionar cache/retry/dedupe no fetch do front, não quebrar quem lê `err.status`.
- **Índice não é grátis**: custo de escrita nas cargas do ETL/cópia bulk. Ver o plano antes; índice composto segue o padrão do projeto (`IX_<tabela>_<colunas>`).

## O que NÃO fazer

- NUNCA otimizar sem medição antes/depois — "parece mais rápido" não fecha PR.
- Não mudar duas coisas no mesmo commit perf; o delta fica inatribuível.
- Não espalhar `memo`/`useMemo`/`useCallback` preventivamente — só onde o Profiler apontou.
- Não transformar a rota inicial em lazy (cria waterfall) nem quebrar chunk abaixo de ~250KB gzip só por estética.
- Não criar índice sem olhar o plano de execução, e não criar direto no banco — sempre migration idempotente.
- Não desabilitar RLS no Supabase "por performance" — otimizar a policy e indexar.
- Não fazer merge sem autorização explícita do usuário.
- Não duplicar as skills n8n para workflows lentos — delegar.
