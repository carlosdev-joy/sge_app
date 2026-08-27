# Estado Atual do Frontend — Mapa de Desenvolvimento

**Data:** 2026-08-23  
**Situação:** Source defasado em relação à produção. Reconstrução necessária.

---

## Arquitetura de Entrega

```
Desenvolvimento  →  Build  →  Deploy  →  Produção (nginx)
/opt/git/sge_app/ui-react/src/     →  npm run build  →  /opt/airflow/ui-react/dist/
```

- **Source:** `/opt/git/sge_app/ui-react/src/`
- **Build output:** `/opt/git/sge_app/ui-react/dist/` (local, temporário)
- **Deploy destino:** `/opt/airflow/ui-react/dist/` (servido pelo nginx na porta 8090)
- **Build tool:** Vite 5.4.21, Node 20.18
- **Base path:** `/` (nginx serve direto da raiz)
- **React Router:** `basename="/v2"` no bundle atual em produção

---

## O Problema

O bundle em produção (`/opt/airflow/ui-react/dist/assets/index-EwPETJTf.js`, 705 KB)
contém telas que **não existem no source** (`/opt/git/sge_app/ui-react/src/`).

Essas telas foram construídas em sessões anteriores e compiladas num build que foi
deployado, mas os arquivos `.tsx` fonte **não foram preservados**.

Um novo `npm run build` a partir do source atual **apagaria essas telas** do bundle.

---

## O Que Existe no Source (sincronizado)

| Arquivo | Status | Rota |
|---------|--------|------|
| `src/pages/Login.tsx` | ✅ source ok | `/login` |
| `src/pages/Admin.tsx` | ✅ source ok (com aba ServiceNow parcial) | `/admin` |
| `src/components/ui/` (Badge, Button, Card, Input, Modal, Spinner, Tabs, Toast) | ✅ source ok | — |
| `src/components/layout/` (AppShell, Header) | ✅ source ok | — |
| `src/lib/api.ts` | ✅ source ok | — |
| `src/lib/nav.ts` | ⚠️ desatualizado | — |
| `src/lib/queryClient.ts` | ✅ source ok | — |
| `src/store/auth.ts` | ✅ source ok | — |
| `src/App.tsx` | ⚠️ desatualizado (faltam rotas) | — |

---

## O Que Existe em Produção mas NÃO no Source

Estas telas estão no bundle compilado mas não têm arquivo `.tsx` correspondente:

### 1. `AdminServiceNow` — `/admin/servicenow`
- **Tamanho no bundle:** ~387 KB (inclui recharts e dependências)
- **Abas:** Conexão | Grupos | Sincronização | Acesso
- **Aba Conexão:** campos URL, usuário, senha, toggle habilitado, botão Testar
- **Aba Grupos:** tabela de grupos ativos/inativos, adicionar/verificar grupo
- **Aba Sincronização:** últimos 20 ciclos (delta/full), botão "Forçar delta agora"
- **Aba Acesso:** multiselect de perfis para acesso à tela
- **Endpoints consumidos:** `GET/PUT /admin/servicenow/config`, `POST /admin/servicenow/testar`,
  `GET/POST /admin/servicenow/grupos`, `GET /admin/servicenow/ciclos`,
  `POST /admin/servicenow/disparar-delta`
- **Arquivo a criar:** `src/pages/AdminServiceNow.tsx`

### 2. `ChamadosIndicadoresHistorico` — `/chamados/indicadores/historico`
- **Tamanho no bundle:** ~7 KB
- **Funcionalidade:** seletor de período (hoje/30d/histórico), 4 gráficos Recharts,
  tabela de analistas, tabela de grupos
- **Endpoint consumido:** `GET /chamados/indicadores/historico?periodo=...`
- **Arquivo a criar:** `src/pages/ChamadosIndicadoresHistorico.tsx`

### 3. Nav atualizado (no bundle, não no source)
- Item `{ to: "/chamados/indicadores/historico", label: "Indicadores", migrated: true, adminOnly: true }`
- Item Admin com aba ServiceNow que faz navigate para `/admin/servicenow`

---

## O Que Está no Source mas NÃO no Bundle de Produção

Estas páginas têm **implementação completa** no source (React + React Query + componentes UI,
mesmo padrão de Admin/Pipelines), mas estão com `migrated: false` no `nav.ts` —
ou seja, o link na nav aponta para `/` (UI legada) em vez de abrir a tela React.

Bastaria virar `migrated: true` em `nav.ts`, montar a rota em `App.tsx` e buildar.

| Arquivo | Linhas | `migrated` | Situação |
|---------|--------|------------|----------|
| `src/pages/Pipelines.tsx` | 238 | `false` | completo — wizard multi-step, tabela paginada |
| `src/pages/Dashboard.tsx` | 167 | `false` | completo — KPI cards, badges |
| `src/pages/Jobs.tsx` | 166 | `false` | completo — tabela com filtros e mutations |
| `src/pages/DSMonitor.tsx` | 164 | `false` | completo |
| `src/pages/Governanca.tsx` | 141 | `false` | completo |
| `src/pages/Logs.tsx` | 194 | `false` | completo |
| `src/pages/Malha.tsx` | 178 | `false` | completo |

---

## Telas Planejadas (Spec A) — Ainda não Implementadas

| Tela | Arquivo alvo | Situação |
|------|-------------|---------|
| Modal de detalhes do chamado | `src/components/ChamadoDetalheModal.tsx` | não existe no source nem no bundle |
| Regra visual INC (borda vermelha) | `src/lib/chamado.ts` (função `isINCAtivo`) | não existe |
| Kanban de chamados | `src/pages/Chamados.tsx` | não existe |

---

## Plano de Reconstrução (Ordem)

Para sincronizar source e produção sem quebrar o que está funcionando:

1. **Recriar `src/pages/AdminServiceNow.tsx`** — a tela mais complexa, já funcional em produção
2. **Recriar `src/pages/ChamadosIndicadoresHistorico.tsx`** — tela menor, já funcional
3. **Atualizar `src/lib/nav.ts`** — adicionar item Indicadores
4. **Atualizar `src/App.tsx`** — adicionar rotas `/admin/servicenow` e `/chamados/indicadores/historico`
5. **Atualizar `src/pages/Admin.tsx`** — aba ServiceNow que navega para a rota dedicada
6. **Build + deploy** — `npm run build` + copiar dist para `/opt/airflow/ui-react/dist/`
7. **Desenvolver novas telas** (Subsistema B): Modal, Regra INC, Kanban

---

## Comando de Build e Deploy

```bash
cd /opt/git/sge_app/ui-react
npm run build
cp -r dist/* /opt/airflow/ui-react/dist/
```

> **Atenção:** O `vite.config.ts` tem `emptyOutDir: true` — o build limpa o dist local
> antes de gerar. O deploy copia para o destino de produção.

---

## Dependências Relevantes no Bundle

- `react` + `react-dom` — framework
- `react-router-dom` — roteamento (basename="/v2")
- `@tanstack/react-query` — data fetching
- `zustand` — state management (auth)
- `lucide-react` — ícones
- `recharts` — gráficos (Indicadores Históricos)
