---
paths:
  - "ui-react/**"
---

# Regras de frontend — ORQUESTRA

(Carregam só ao trabalhar em `ui-react/`.)

- **Cores: SEMPRE par claro + escuro.** Use tokens semânticos
  (`bg-panel`/`text-ink`/`text-dim`/`border-edge`/`bg-canvas`). Nunca `bg-*-900` ou
  `text-*-300` como classe base. Padrão completo em `docs/ui-temas-cores.md`.
- Dados via `@tanstack/react-query` + `apiFetch` (`src/lib/api.ts`).
- Reutilize `src/components/ui/` (Button, Input, Select, Textarea, Modal, Badge, Tabs).
  Toasts: `toast.success | error | info`.
- Valide com `npm run build` em `ui-react/` (recompila `dist/`, que é versionado).
