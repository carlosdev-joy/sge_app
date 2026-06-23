# Design — Nova experiência do ORQUESTRA (app shell + editor de fluxo)

Status: **proposta para avaliação**. Abrange três frentes interligadas e uma
estratégia de entrega isolada (versão paralela validável antes do rollout geral,
no espírito da migração UI legado → React).

> Decisões já tomadas (sessões anteriores): o nó de Decisão (ramificação
> condicional) está implementado (migration 043, factory, backend, UI lista).
> Este doc propõe **expor** melhor essa e as demais capacidades.

---

## 1. Objetivo e princípios

Tornar a ferramenta **mais visível, fácil de navegar e de entender**, sem
big-bang e sem regressão:

- **Dual-view, fonte única de verdade.** Nada de duplicar dado: a lista atual e o
  novo canvas operam sobre o **mesmo** modelo (`JobEntry[]` / colunas do banco).
- **Degrada graciosamente.** Coerente com a regra da casa: sem a coluna nova, sem
  a flag, sem o canvas — tudo continua funcionando.
- **Reaproveitar o que já existe.** `nav.ts` (registry), React Flow (já instalado
  e em uso), tokens semânticos de tema, RBAC por tela.
- **Rollout reversível.** Liberar para um grupo, validar, e só então virar padrão
  — com caminho de volta a um clique.

---

## 2. Diagnóstico do atual

### 2.1 App shell e navegação
- `components/layout/AppShell.tsx` (17 linhas): `Header` + `<main><Outlet/></main>`
  + toasts. **Não há sidebar** — toda a navegação está no header.
- `components/layout/Header.tsx` (**594 linhas**): concentra logo, **nav horizontal
  inteira**, busca (⌘K/CommandPalette), troca de tema, sino de notificações
  (+comunicados), perfil e changelog. Fundo fixo gradiente azul (exceção de tema).
- `lib/nav.ts`: **registry central** `NAV: NavItem[]` (12 itens, `to`/`label`/
  `icon`/`perm`/`migrated`/`legacyHref`), porém **lista plana, sem agrupamento**.
- `App.tsx`: `react-router-dom` v6, **sem `basename`**; as `<Route>`s são
  declaradas **duplicando** o que já está em `NAV`.
- **Desktop-first**: nav vira `overflow-x-auto` (rola lateral) em vez de
  hambúrguer; sem drawer mobile, sem colapso.

Problemas: header faz coisas demais; 12 itens planos sem hierarquia dificultam a
descoberta; não há economia de espaço (ícones) nem caminho mobile.

### 2.2 Edição de jobs (lista + pílulas)
A topologia do pipeline é **inferida**, nunca **mostrada**: ordem (`execution_order`),
dependências (pílulas "Depende de") e ramos da decisão (pílulas verdadeiro/falso)
vivem em três lugares que não conversam visualmente. O branch — recurso mais novo
e poderoso — é o mais difícil de operar e auditar nesse formato.

### 2.3 O que JÁ ajuda (de-risca a proposta)
- O backend **já é um grafo**: `depends_on_jobs` (CSV) + `condition_json` (ramos);
  a factory já gera DAG com paralelismo, dependências e branch.
- **React Flow (`@xyflow/react` v12) já está instalado e em produção** em
  `components/console/DsSeqFlowGraph.tsx` e `DsRunGraphModal.tsx` (auto-layout em
  camadas, arestas temáticas, handles) — custo zero de biblioteca, precedente
  interno copiável.
- `nav.ts` central + RBAC por tela (`canSee` em `Header.tsx`) prontos para
  reuso.

---

## 3. Novo app shell

### 3.1 Sidebar colapsável (ícones + tooltip), reagrupada por domínio
Mover a navegação do header para uma **barra lateral**:
- **Expandida**: ícone + label, agrupados por domínio com cabeçalho de seção.
- **Colapsada** (hambúrguer): só `n.icon`, com **tooltip** do `n.label`. Estado
  persistido em `localStorage` (padrão de `lib/theme.ts`).
- **Superfície semântica** (`bg-panel`/`border-edge`/`text-ink`/`text-dim`) — não
  o gradiente fixo do header; estado ativo via tokens, não classes brancas.
- **Drawer off-canvas no mobile** (ganho "de brinde" que o shell atual não tem).

Reagrupamento proposto dos 12 itens (campo novo `group` em `NavItem`):

| Grupo | Itens |
|---|---|
| **Operação** | Dashboard · Pipelines · Jobs · Logs |
| **Governança** | Governança · Malha · Impacto Campo · Planos Ajuste |
| **Console DataStage** | Malha DS · Console DS |
| **BI** | Power BI |
| **Administração** | Admin |

(ordem/labels a calibrar com os usuários — ver §7.)

### 3.2 Header minimalista (só o essencial/visual)
Header fino, sem a nav: **identidade visual** (logo + título/breadcrumb da página
atual) à esquerda; à direita apenas **controles globais** — busca (⌘K), troca de
tema, sino de notificações e perfil. Para isso, **extrair** de `Header.tsx` os
blocos `NotificationsBell`, `ProfileDropdown`, `ChangelogModal`, `CommandPalette`
em subcomponentes reutilizáveis (ambos os shells reusam; o arquivo de 594 linhas
encolhe).

### 3.3 Registry único (menu + rotas + permissão num lugar)
- Generalizar `nav.ts`: adicionar `group`; **derivar as `<Route>`s de `App.tsx` a
  partir do `NAV`** (hoje duplicado); extrair `canSee` (RBAC) para um
  `useVisibleNav()` que agrupa e filtra por permissão — compartilhado pelos dois
  shells.
- RBAC permanece **defendido nos dois lados** (front decide visibilidade do menu;
  backend protege endpoints com `require_perm`).

### 3.4 Tema e responsividade
- Tokens semânticos já existem (`tailwind.config.js`, `html.dark` + `localStorage`).
- A sidebar abre caminho natural para o mobile (drawer no `sm`).

**Esforço do shell**: extração dos blocos do header (**S**), sidebar + registry +
`useVisibleNav` (**M**), responsividade/drawer (**S**).

---

## 4. Editor de fluxo (canvas) — dentro do novo shell

Resultado da avaliação dos times (frontend/backend/produto). Recomendação:
**dual-view faseado, sem substituir a lista**, com padrão **canvas em cima +
painel de configuração embaixo** (estilo Informatica/SSIS).

- **Nós = jobs** (cor por tipo, reusando `typeBadgeColor`); **arestas =
  dependências**; **nó de Decisão com duas saídas rotuladas** verdadeiro (verde) /
  falso (vermelho). Aresta de dependência visualmente distinta da de ramo.
- **Auto-layout** reusando o longest-path de `DsSeqFlowGraph.tsx` (abre grafos do
  banco sem posição x/y).
- **Clicar no nó → painel de config** reusando os campos atuais do job (extrair o
  card do job, hoje inline em `PipelineFormModal.tsx`, num `JobConfigPanel`).
- **Validação visual** reusando `jobsHaveCycle` e `validateStep(3)`.

### Backend (mínimo, retrocompatível — a factory NÃO muda nas fases 1–2)
- **Posições**: migration `044` idempotente com `ui_pos_x/ui_pos_y` em
  `etl_pipeline_job` (a factory **ignora** — garante saída byte-idêntica).
  Persistência/leitura **opt-in** (flags `_has_*_col`, try/except), como 038/039/043.
- **Manter `depends_on_jobs` + `condition_json`** como fonte da verdade do grafo —
  **não** criar tabela de arestas agora (seria o item de maior risco; adiar; se um
  dia precisar, começar por uma VIEW derivada).
- **Endpoint de leitura agregada** `GET /pipelines/{name}/graph` → `{nodes, edges}`
  (deriva arestas de CSV+ramos no backend; centraliza a regra ondas-vs-explícito,
  evitando duplicá-la no front). Router novo → registrar em `api/main.py`.

### Fases do editor

| Fase | Escopo | Esforço | Toca a factory? |
|---|---|---|---|
| **0 — Refactor** | extrair `JobConfigPanel` (card de job) + util de auto-layout | S | não |
| **1 — Canvas read-only (MVP)** | nós/arestas, decisão V/F, clique→config; endpoint `/graph`; layout automático (sem salvar posição) | M | **não** |
| **2 — Edição no canvas** | arrastar cria dependência/ramo; validação visual; persistir posições (migration 044) | M/L | não |
| **3 — Avançado (sob demanda)** | switch (N ramos), overlay de status de execução ao vivo, tela cheia | L | só switch |

**Riscos e mitigações**: sincronização estado↔canvas (derivar nós/arestas com
`useMemo`, como nos componentes de console); **save "só de posição" não pode apagar
deps/condição** (o canvas reenvia o estado completo do nó + teste cobrindo);
refactor da Fase 0 é pré-requisito (modal já é grande); manter a lista como
fallback **acessível** (teclado/leitor de tela) e desktop-first do canvas.

---

## 5. Estratégia de rollout isolado (versão paralela validável)

Objetivo do usuário: ter **toda essa estrutura nova numa versão separada**,
validar, e **só então liberar para todos** — como na migração legado → React.

### Precedente reaproveitável
- Padrão `migrated` + `legacyHref` em `nav.ts` (fork em runtime no header).
- Esquema **nginx por path** `/` (legado) vs `/app` (React), documentado em
  `docs/AUDITORIA_TECNICA.md §3`. (O legado já foi desligado; o mecanismo, não.)
- **RBAC por tela** já decide visibilidade no front (`canSee`).
- O comentário "basename /v2" em `nav.ts` indica que um shell sob `/v2` já foi
  cogitado.

### Opções (da mais leve à mais isolada)

1. **Flag de shell no mesmo bundle (recomendado p/ validação).**
   `localStorage['orquestra_shell'] = 'v2'` (ou `?shell=v2`), no espírito de
   `theme.ts`, escolhe entre `AppShell` clássico e o novo. Liga/desliga
   instantâneo, reverte a um clique, **sem mudar deploy**. Ideal para o time de
   validação testar a estrutura nova convivendo com a atual.
2. **Gate por RBAC (beta para alguns).** Liberar o shell novo só a um recurso
   `tela_*`/perfil — controle por usuário, sem código de flag, reusa o que existe.
   Combina com (1): a flag fica disponível só para o grupo beta.
3. **Build sob `/v2` (isolamento máximo).** `BrowserRouter basename="/v2"` +
   `vite base:'/v2/'` + `location /v2/` no nginx (espelha o `try_files` atual).
   Dois `dist/` convivendo — exatamente o precedente da migração. Mais isolado,
   porém mais pesado de operar.

### Recomendação
Fazer a **(1)+(2)**: construir o novo shell + editor atrás de uma **flag** ligada
por **RBAC** a um grupo beta. Time valida com pipelines reais; quando estiver OK,
**vira o default** (flag passa a ligada para todos) com **reversão trivial**. A
opção (3) fica documentada como "isolamento total" caso se queira um ambiente
de fato separado — mas (1)+(2) entregam o "validar antes de liberar" com muito
menos custo e risco.

**Plano de corte/reversão**: default = clássico → beta liga flag → validação →
flip do default para v2 → janela de convivência (flag permite voltar) → remoção do
clássico quando estável.

---

## 6. Consolidado — fases, esforço, riscos

| Bloco | Entrega | Esforço | Risco |
|---|---|---|---|
| Shell — extrair blocos do header | header fino + peças reutilizáveis | S | baixo |
| Shell — sidebar + registry + `useVisibleNav` | menu lateral colapsável, agrupado | M | baixo |
| Shell — responsividade/drawer | mobile real | S | baixo |
| Rollout — flag + gate RBAC | versão paralela validável | S | baixo |
| Editor F0 — refactor | `JobConfigPanel` + util layout | S | baixo |
| Editor F1 — canvas read-only | grafo + decisão + config; `/graph` | M | baixo (factory intocada) |
| Editor F2 — edição + posições | arrastar arestas; migration 044 | M/L | médio (UX/validação) |
| Editor F3 — avançado | switch / overlay execução / tela cheia | L | médio-alto (switch toca factory) |

A factory e os pipelines existentes **não quebram** até a F3 (e só o switch a
tocaria) — mesmo princípio já provado para o nó de decisão (saída byte-idêntica
para pipelines sem decisão).

---

## 7. Métricas e validação enxuta

- **Teste com ~5 usuários** (operação/governança/plantão) antes de investir na
  edição por arraste (F2): dar um pipeline com branch e pedir "o que roda se a
  condição for verdadeira? qual job trava tudo se falhar?" — medir acerto/tempo na
  lista vs. no canvas read-only. Idem para o shell: achar uma tela por domínio.
- **Métricas pós-lançamento**: tempo de criação de pipeline com branch; taxa de
  correção/regeneração por erro de topologia; erros de ciclo/ramo barrados;
  adoção do toggle grafo↔lista e do shell v2 por persona; tempo de "entender
  pipeline alheio" (handover).
- **Gate**: só seguir para F2 (arraste) e para o flip de default do shell se a
  validação mostrar ganho real.

---

## 8. Decisões em aberto (para confirmar)

1. **Conteúdo do header novo**: manter ⌘K + tema + notificações + perfil no header
   (recomendado), ou mover algo desses para a sidebar?
2. **Forma da versão paralela**: flag+RBAC no mesmo bundle (recomendado) ou build
   isolado sob `/v2`?
3. **Agrupamento/ordem do menu**: validar os 5 grupos propostos (§3.1) com os
   usuários.
4. **Ordem de execução**: começar pelo **shell** (ganho transversal e rápido) ou
   pelo **editor de fluxo** (mais valor, mais esforço)? Recomendação: shell
   primeiro (S/M, de-risca a navegação e cria o lar do editor), editor em seguida.

---

## 9. Arquivos-âncora

- Shell: `ui-react/src/components/layout/AppShell.tsx`, `…/Header.tsx`,
  `ui-react/src/lib/nav.ts`, `ui-react/src/App.tsx`, `ui-react/src/lib/theme.ts`,
  `ui-react/src/store/auth.ts`, `ui-react/tailwind.config.js`.
- Editor: `ui-react/src/components/pipelines/PipelineFormModal.tsx` (card de job a
  extrair; `jobsHaveCycle`; `validateStep`), `ui-react/src/components/console/
  DsSeqFlowGraph.tsx` (precedente de canvas + auto-layout), `…/DsRunGraphModal.tsx`.
- Backend: `api/routers/jobs.py` (`register_pipeline_jobs`, `get_pipeline_job`),
  `api/main.py` (registrar `/graph`), `dags/etl_dag_factory.py` (**não tocar** F1–F2),
  `sql/migrations/038_*`/`043_*` (molde p/ `044`).
- Rollout: `config/nginx.conf`, `scripts/deploy_prod.sh`, `docs/AUDITORIA_TECNICA.md`
  (§3), `docs/ui-temas-cores.md`.
