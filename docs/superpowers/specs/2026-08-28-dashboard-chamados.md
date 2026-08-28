# Spec — Dashboard de Chamados ServiceNow

**Status:** Implementado em produção (bundle direto). Esta spec documenta o comportamento atual para permitir reimplementação limpa em React/TypeScript.

**Bundle de produção:** `ui-react/dist/assets/index-CeXrH6tU.js`
**Arquivo de entrada:** aba "Dashboard" dentro da tela `/chamados` (componente `Chamados.tsx`, tab id `"dashboard"`)
**Componente principal:** `DshPanel` (injetado diretamente no bundle, sem fonte `.tsx`)

---

## 1. Visão geral

O Dashboard de Chamados é uma aba dentro da tela de Chamados que exibe indicadores operacionais do time em tempo real. Os dados vêm de dois endpoints:

| Endpoint | Uso | Cache |
|---|---|---|
| `GET /chamados` | Fonte principal — lista completa dos chamados | `staleTime: 0` (sempre refetch) |
| `GET /chamados/dashboard?visao=geral` | Fluxo do dia (entradas/saídas) | `staleTime: 30000` |

**Todos os filtros de visão são client-side** — não há parâmetro de visão na chamada ao `/chamados`. A filtragem acontece em `useMemo` sobre a lista completa retornada.

---

## 2. Seletor de visão

Botões no topo da tela. Estado: `p` (string). Reset do card selecionado (`sel`) ao trocar visão.

| Valor `p` | Label | Filtro aplicado |
|---|---|---|
| `"geral"` | Geral | Todos os chamados (exceto tasks filhas: `tipo==="task" && pai_sys_id`) |
| `"proprio"` | Meu painel | Chamados com `atribuido_a` preenchido (não vazio/nulo) |
| `"diaadia"` | Dia a dia | `categoria_diaadia === "dia a dia"` |
| `"iniciativa"` | Iniciativas | `categoria_diaadia === "iniciativa"` |

> **Nota:** "Meu painel" filtra por `atribuido_a` preenchido — **não** pelo usuário logado. Comportamento atual de produção.

Indicador textual no canto direito: `Total na fila: N chamados` (baseado em `ativos.length`).

---

## 3. Grupos computados

A partir do array `todos` (após filtro de visão), calcula-se `D` com `useMemo`:

### 3.1 Definições

```
ativos        = todos onde ativo !== false E estado_kanban !== "encerrado"
naoResolvidos = ativos onde estado_kanban !== "resolvido" E !== "outros"
```

### 3.2 Grupos da fila ativa

| Chave `D` | Filtro | Cor do card |
|---|---|---|
| `backlog` | `estado_kanban === "novo"` | Roxo (`purple`) |
| `andamento` | `estado_kanban === "andamento"` | Amarelo (`yellow`) |
| `pendentes` | `estado_kanban === "aguardando"` | Laranja (`orange`) |
| `resolvidas` | `todos` onde `estado_kanban === "resolvido"` (inclui encerrados) | Verde (`green`) |

### 3.3 Grupos de alertas de prazo

Calculados sobre `naoResolvidos` (exclui resolvido, encerrado e outros):

| Chave `D` | Label | Critério | Cor do card |
|---|---|---|---|
| `vencem_hoje` | Vencem hoje | `prazo` existe E `prazoDate >= hoje E prazoDate <= hoje` (mesmo dia) | Rosa (`pink`) |
| `vencem_semana` | Vencem esta semana | `prazo` existe E `prazoDate > hoje E prazoDate <= fimSemana` | Laranja (`orange`) |
| `vencidas` | Vencidas | `prazo` existe E `prazoDate < hoje` | Vermelho (`red`) |

**`fimSemana`** = próxima sexta-feira a partir de hoje (se hoje já é sexta, avança para a sexta seguinte):

```js
var d = new Date(hoje)
d.setDate(d.getDate() + (5 - d.getDay() + 7) % 7 || 7)
// getDay(): 0=dom, 1=seg, ..., 5=sex, 6=sab
// (5 - getDay() + 7) % 7 = dias até sexta; se resultado é 0 (hoje é sexta) usa 7
```

### 3.4 Outros valores em `D`

- `D.total_fila` = `ativos.length`
- `D.fluxo_hoje` = `fluxoData.fluxo_hoje || { entradas: 0, saidas: 0 }`

---

## 4. Layout

### 4.1 Estrutura geral

```
[Seletor de visão]          [Total na fila: N chamados]

── Fila ativa ──────────────────────────────────────────
[Backlog] [Em andamento] [Pendentes] [Resolvidos]   ← grid 4 colunas

[Backlog/resp. 🍕] [Andamento/prazo 🍕] [Fluxo do dia]  ← grid 3 colunas

── Alertas de prazo ─────────────────────────────────────
[Vencem hoje] [Vencem esta semana] [Vencidas]        ← grid 3 colunas

[Painel expandido quando card clicado]
```

### 4.2 Cards clicáveis (`cardBtn`)

Cada card é um `<button>` que, ao clicar, define `sel = card.id` (toggle: segundo clique fecha). Comportamento:

- Borda ativa: `ring-2 ring-[#1A5FA8]`
- Hover: `scale-[1.02]`
- Conteúdo: número grande + label + sublabel

### 4.3 Gráficos de pizza (`DE_Pizza`)

SVG puro com círculos `stroke-dasharray`. Props:

```ts
interface PizzaSlice { val: number; color: string; label: string }
interface DE_PizzaProps { slices: PizzaSlice[]; size?: number } // size padrão: 80
```

Se `total === 0`: exibe texto "sem dados".

Legenda inline à direita do SVG: bolinha colorida + label + valor.

#### Pizza "Backlog por responsável"

| Fatia | Cor | Critério |
|---|---|---|
| Com responsável | `#6366f1` (indigo) | `atribuido_a` preenchido |
| Sem responsável | `#f87171` (vermelho) | `atribuido_a` vazio/nulo |

#### Pizza "Em andamento por prazo"

| Fatia | Cor | Critério |
|---|---|---|
| Dentro do prazo | `#34d399` (verde) | `prazo` existe E `prazoDate >= hoje` |
| Sem prazo | `#94a3b8` (cinza) | `prazo` ausente |
| Fora do prazo | `#f87171` (vermelho) | `prazo` existe E `prazoDate < hoje` |

### 4.4 Fluxo do dia

Painel 3x1 (terceira coluna do grid de pizzas). Exibe:
- **Entradas** (bullet azul `bg-blue-400`): `fluxo.entradas`
- **Saídas** (bullet verde `bg-emerald-400`): `fluxo.saidas`
- Barra proporcional: azul + verde, altura `h-1.5`, proporção pelo total

Fonte: `GET /chamados/dashboard?visao=geral` → campo `fluxo_hoje.entradas` e `fluxo_hoje.saidas`.

---

## 5. Painel expandido (lista de chamados)

Exibido abaixo dos alertas quando `sel !== null`.

- Header: label do card selecionado + botão `✕ Fechar`
- Se lista vazia: "Nenhum chamado nesta categoria."
- Caso contrário: `<DE_DshLista lista={lista} showPrazo={...} />`
- `showPrazo = true` apenas para: `vencem_hoje`, `vencem_semana`, `vencidas`

---

## 6. Componente `DE_DshLista`

Lista de chamados dentro do painel expandido.

```ts
interface DE_DshListaProps {
  lista: Chamado[]
  showPrazo: boolean
}
```

### 6.1 Por item

```
┌─────────────────────────────────────────────────────────┐
│ INC0001234  João da Silva                               │
│ Prazo: 25/08/26  [3 dias de atraso]        [+ Detalhes]│
│ Título do chamado truncado                  [ServiceNow ↗]│
└─────────────────────────────────────────────────────────┘
```

### 6.2 Indicador de prazo (quando `showPrazo === true` e `prazoLabel` existe)

```
diffDias = Math.round((hoje - prazoDate) / (1000*60*60*24))
```

| Condição | Mensagem | Cor |
|---|---|---|
| `diffDias > 0` | `N dia(s) de atraso` | `text-red-400` |
| `diffDias === 0` | `vence hoje` | `text-orange-400` |
| `diffDias < 0` | `faltam N dia(s)` | `text-emerald-400` |

### 6.3 Botão "Detalhes"

Ao clicar: abre `DE_Modal` passando `sysId` e `numero` do chamado. O modal busca detalhes em `GET /chamados/{sys_id}`.

### 6.4 Link ServiceNow

Exibido apenas se `c.url` está preenchido. Abre em nova aba (`target="_blank"`).

---

## 7. Componente `DE_Modal`

Modal de detalhes do chamado, aberto a partir do `DE_DshLista`.

```ts
interface DE_ModalProps {
  sysId: string
  numero: string
  onClose: () => void
}
```

Busca `GET /chamados/{sysId}` via React Query. Exibe:
- Cabeçalho: número, título, estado, tipo
- Campos: atribuído, grupo, categoria, criado em, atualizado em, prazo
- Notas de trabalho (`DE_NotaItem`) e anexos (`DE_AnexoItem`) se houver

---

## 8. Badge de prazo no Kanban (`vE`)

Em cada card Kanban (`vE`), exibido **somente quando**:
- `e.prazo` está preenchido
- `e.estado_kanban !== "resolvido"` E `!== "encerrado"`

```
diffDias = Math.round((hoje - prazoDate) / (1000*60*60*24))
```

| Condição | Badge | Cor de fundo / texto / borda |
|---|---|---|
| `diffDias > 0` | `Nd atraso` | Vermelho (`red-100 / red-400 / red-300`) |
| `diffDias === 0` | `hoje` | Laranja (`orange-100 / orange-400 / orange-300`) |
| `diffDias < 0` | `faltam Nd` | Verde (`emerald-100 / emerald-400 / emerald-300`) |

Dark mode: `dark:bg-*-950/40 dark:border-*-800`.

Layout inline: `prazo:` (dim) + data formatada `dd/mm/aa` + badge colorido.

---

## 9. Contador de idade e badge no kanban — regra de ocultação

Para chamados com `estado_kanban === "resolvido"` ou `=== "encerrado"`:
- **Ocultar** o contador `idade_dias` (ícone relógio + dias parado)
- **Ocultar** o badge de prazo

Motivo: não faz sentido indicar "parado há X dias" ou mostrar prazo vencido para chamados já finalizados.

---

## 10. Filtro de categoria no Kanban

O `<select>` de categorias exibe apenas as categorias que têm **ao menos um chamado** com aquele `categoria_diaadia` na fila atual:

```js
(Z_cats ?? [])
  .filter(cat => g.some(ch => ch.categoria_diaadia === cat.slug))
  .map(cat => <option value={cat.slug}>{cat.label}</option>)
```

`Z_cats` vem de `GET /chamados/categorias`. `g` é a lista de chamados do estado Kanban atual.

---

## 11. Regra de exclusão de tasks — detalhamento crítico

Esta é a regra que garante que os totais batem certinho. **Implementar errado aqui quebra todos os contadores.**

### 11.1 A regra exata (frontend)

```js
// Filtro aplicado ANTES de qualquer visão ou grupo
const chs = (rawData.chamados || []).filter(e => !(e.tipo === "task" && e.pai_sys_id))
```

Leitura: **excluir** um registro somente se ele for `tipo="task"` **E** tiver `pai_sys_id` preenchido. Qualquer outra combinação é incluída.

### 11.2 Tabela de decisão — o que é incluído ou excluído

| `tipo` | `pai_sys_id` | Incluído? | Motivo |
|---|---|---|---|
| `"incident"` | `null` | ✅ | Incident normal |
| `"ritm"` | `null` | ✅ | RITM independente (maioria) |
| `"ritm"` | preenchido | ✅ | RITM com pai (ex: RITM0100279 cujo pai não existe em `etl_chamado`) — **a regra não exclui ritm** |
| `"task"` | preenchido | ❌ | SCTASK filha de um RITM — excluída da fila principal |
| `"task"` | `null` | ✅ | Task órfã sem RITM pai — **seria incluída** (hipotético, não ocorre hoje) |
| `"change"` | qualquer | ✅ | Tipo mudança |

**A condição é AND**: ambas precisam ser verdadeiras para excluir. Trocar por OR ou verificar só `tipo` quebra o cálculo.

### 11.3 Estado atual de produção (verificado em 2026-08-28)

```
Total em etl_chamado (ativo=1):   97
  → incident:  1  (todas sem pai)
  → ritm:     59  (58 sem pai + 1 com pai fora do banco)
  → task:     37  (todas com pai = todas excluídas da fila principal)

Após filtro frontend:             60  (1 + 59 = 60)
```

Os 37 SCTASKs são excluídas da fila principal — aparecem **somente** dentro do card RITM pai, na seção expandida de tarefas.

### 11.4 Onde o mesmo filtro é aplicado

O filtro `!(tipo==="task" && pai_sys_id)` é aplicado **em dois lugares** independentes:

| Contexto | Variável | Uso |
|---|---|---|
| Dashboard (`DshPanel`) | `todos` (via `useMemo`) | Base de todos os grupos e contadores |
| Kanban | `g` (via `useMemo`) | Lista base do kanban, filtros de coluna e dropdowns |

Ambos partem do mesmo `GET /chamados` — que retorna **todos** os tipos incluindo tasks. O filtro é exclusivamente client-side.

### 11.5 Como as tasks aparecem na tela

As SCTASKs **não somem** da interface — elas aparecem dentro do card do RITM pai:

```
[Card RITM0092677]
  SCTASK0094713  ...  aguardando
```

Isso acontece via chamada separada: `GET /chamados/{sys_id}/tasks` (habilitada somente quando `e.tipo === "ritm"`). O endpoint busca todos os registros com `pai_sys_id = sys_id`, incluindo inativos.

Campos retornados pelo endpoint de tasks:
`sys_id`, `numero`, `tipo`, `titulo`, `estado_kanban`, `prioridade`, `atribuido_a`, `grupo`, `aberto_em`, `atualizado_em`, `encerrado_em`, `ativo`, `url`, `sync_em`

Renderização de cada task no card:
- Número em azul (link para ServiceNow se `url` preenchido)
- Título truncado
- `estado_kanban` à direita
- Exibidas somente tasks com `ativo = true` (`wE_lista = tasks.filter(t => t.ativo)`)

### 11.6 Consequência nos contadores do dashboard

Os grupos calculados em `D` usam a variável `todos` (já filtrada). Portanto:

- **backlog, andamento, pendentes, resolvidas** → nunca contam tasks filhas
- **vencem_hoje, vencem_semana, vencidas** → nunca contam tasks filhas
- **total_fila** = `ativos.length` onde `ativos = todos.filter(ativo && !encerrado)`

Verificação cruzada com banco (2026-08-28):

| Contador | Valor esperado |
|---|---|
| total_fila | 60 |
| backlog | 24 |
| andamento | 7 |
| pendentes | 6 |
| resolvidos | 1598 (todos — inclui encerrados) |
| vencem_hoje | 14 |
| vencem_semana | 0 |
| vencidas | 2 |

### 11.7 Regra de "Meu painel" sobre tasks

No modo `p === "proprio"`:

```js
chs.filter(e => e.atribuido_a && e.atribuido_a.trim())
```

`chs` já foi filtrado removendo tasks com pai. Portanto "Meu painel" mostra RITMs e incidents com responsável preenchido — **nunca tasks individuais**.

---

## 12. API — campos necessários por chamado

> Nota: a seção 11 acima descreve como o campo `pai_sys_id` é consumido pelo frontend. A API retorna o campo conforme documentado abaixo.

O endpoint `GET /chamados` deve retornar por chamado:

| Campo | Tipo | Uso |
|---|---|---|
| `sys_id` | string | Chave, link para modal |
| `numero` | string | Exibição (`INC0001234`) |
| `titulo` | string | Descrição curta |
| `tipo` | string | `"incident"`, `"ritm"`, `"task"` |
| `pai_sys_id` | string\|null | Exclusão de tasks filhas |
| `estado_kanban` | string | `"novo"`, `"andamento"`, `"aguardando"`, `"resolvido"`, `"encerrado"`, `"outros"` |
| `atribuido_a` | string\|null | Responsável (nome) |
| `atribuido_a_email` | string\|null | Email (usado em outros contextos) |
| `prazo` | string\|null | ISO 8601 datetime |
| `categoria_diaadia` | string\|null | `"dia a dia"`, `"iniciativa"` ou null |
| `idade_dias` | number | Dias desde abertura |
| `ativo` | boolean | Se false, excluído dos ativos |
| `url` | string\|null | Link direto no ServiceNow |
| `veredito` | string\|null | Resultado triagem IA |

---

## 12. API — fluxo do dia

`GET /chamados/dashboard?visao=geral` retorna:

```json
{
  "fluxo_hoje": {
    "entradas": 3,
    "saidas": 1
  }
}
```

`entradas` = chamados criados hoje. `saidas` = chamados resolvidos/encerrados hoje.

---

## 13. Dependências de reimplementação

Para reimplementar como `DashboardChamados.tsx` limpo:

```
react + @tanstack/react-query   — já no projeto
tailwindcss                     — já no projeto
Nenhuma lib externa nova necessária (pizza é SVG puro)
```

Componentes auxiliares a criar separadamente ou inline:
- `DE_Pizza` — SVG donut sem biblioteca
- `DE_DshLista` — lista com badge de prazo
- `DE_Modal` — modal de detalhes (já existe parcialmente como `ChamadoDetalheModal.tsx`)

---

## 14. Estados de loading e erro

- Durante loading (`isLoading === true`): cards mostram `"…"` no lugar do número
- Sem chamados na categoria selecionada: `"Nenhum chamado nesta categoria."`
- Pizza com total 0: `"sem dados"`
