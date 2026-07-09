---
description: >
  Scaffolding de tela ou componente novo no frontend do ORQUESTRA (React/Vite/Tailwind).
  Use quando o usuário pedir "nova tela", "nova página", "novo componente", "nova aba",
  "adicionar em Admin", ou qualquer UI nova — garante tema claro+escuro, estados de
  loading/vazio/erro, permissões e degradação graciosa desde o início.
argument-hint: "<nome_da_tela>"
---

# Nova tela/componente — ORQUESTRA

Padrão completo de cores: `docs/ui-temas-cores.md`. Bons exemplos para copiar:
`pages/Dashboard.tsx` (KPIs + STATUS map), `components/ui/Badge.tsx` (variantes
light/dark), `components/ui/InfoBanner.tsx` (callout).

## 1. Dados
- `@tanstack/react-query` + `apiFetch` (`src/lib/api.ts`). Nunca `fetch` cru.
- **Degradação graciosa**: o endpoint pode 500/tabela ausente → a tela mostra estado
  vazio amigável, NUNCA quebra. Trate `isError` explicitamente.
- Query keys nomeadas e específicas (`['tela', filtro]`); invalidar após mutação.
- Se a tela é um EDITOR (estado local editável), proteja contra refetch em background:
  `refetchOnWindowFocus: false` + guard de `dirty` — *bug real: refetch sobrescrevia
  edição não salva do canvas de fluxo.*

## 2. Visual (regras inegociáveis)
- Superfície/texto neutro: SÓ tokens semânticos `bg-canvas`/`bg-panel`/`text-ink`/
  `text-dim`/`border-edge` (trocam de tema sozinhos).
- Cor de paleta SEMPRE em par claro+`dark:` (seção 2 do guia). NUNCA `bg-*-900` ou
  `text-*-200/300` como classe base.
- Reutilize `src/components/ui/` (Button, Input, Select, Textarea, Modal, Badge, Tabs).
  Toasts: `toast.success | error | info`. Ícones: `lucide-react`.
- Textos em pt-BR, no tom das telas vizinhas.

## 3. Estados obrigatórios
- [ ] Loading (skeleton ou spinner discreto)
- [ ] Vazio (mensagem orientando o próximo passo)
- [ ] Erro (mensagem genérica + toast; detalhe só no console)
- [ ] Sucesso de ação → toast + invalidateQueries

## 4. Permissões
- Botão de criar/editar/executar/excluir escondido para quem não tem a permissão
  (padrão Viewer mode). Cheque como as telas vizinhas leem o perfil/permissão.
- O backend é a barreira real (`require_perm`) — a UI só esconde.

## 5. Registro e validação
- Rota/menu: registrar a página no router e no menu lateral seguindo o padrão existente.
- `npm run build` em `ui-react/` (tsc + vite) e **recommitar `dist/`** (é versionado).
- Greps de regressão de tema (esperado: vazio, fora das superfícies fixas da seção 4
  do guia):
  ```bash
  grep -rnoE "[^:]bg-(green|red|amber|yellow|blue|orange|emerald|purple)-900" ui-react/src --include=*.tsx
  grep -rnoE "[^:]text-(green|red|amber|blue|purple)-(200|300)" ui-react/src --include=*.tsx
  ```
- Testar visualmente nos DOIS temas (botão de tema no header).
