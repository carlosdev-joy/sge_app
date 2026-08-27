# Task 7 Report — Modal de Detalhes do Chamado

**Status:** DONE_WITH_CONCERNS

## Arquivos Criados

| Arquivo | Ação |
|---------|------|
| `/opt/git/sge_app/ui-react/src/components/ChamadoDetalheModal.tsx` | Criado |
| `/opt/git/sge_app/ui-react/src/components/ChamadoKanbanCard.tsx` | Criado (ver concern) |

## Resultado do `tsc --noEmit`

```
(sem erros — saída vazia)
```

TypeScript compilou sem erros ou avisos.

## O que foi implementado

### `ChamadoDetalheModal.tsx`

- Props: `{ sys_id: string | null, onClose: () => void }`
- Consome `GET /chamados/{sys_id}/detalhe` via `apiFetch` (padrão do projeto — fetch nativo, não axios)
- Fecha com ✕, clique no backdrop, ou tecla Escape
- Cabeçalho: `bg-red-950/40 border-red-800/50` para INC ativo (tipo='incident' + estado NOT IN resolvido/encerrado)
- Badge "INC" vermelho no cabeçalho quando INC ativo
- Badge "SLA" laranja quando `sla_vencido=true`
- Exibe: número, título, analista, grupo, estado, aberto_em, descrição, notas (ordem cronológica), anexos
- Imagens: renderizam inline com toggle "ver/fechar"
- Outros tipos: link `<a download>` para download
- URL proxy de anexos: relativo `/chamados/{sys_id}/anexos/{sys_id_anexo}` (sem base URL)
- Tema dark do projeto: `bg-[#1a1d27]`, `border-[#2a2d3a]`, `text-[#e2e8f0]`
- Usa componentes do projeto: `Button` (rodapé), ícones lucide-react (X, ExternalLink, Paperclip, FileText)
- NÃO usa `Modal` existente (evita conflito de `size`/`title` — o cabeçalho do modal tem lógica condicional de cor INC que requer controle total do markup)

### `ChamadoKanbanCard.tsx`

- Exporta interface `ChamadoCard` com todos os campos necessários
- Regra INC: `border-l-4 border-l-red-500` quando tipo='incident' + estado_kanban NOT IN ('resolvido','encerrado')
- `onClick` → abre `ChamadoDetalheModal` com `sys_id`
- `onCardClick` prop opcional para callback externo (analytics, etc.)
- Exibe: número, badges INC/SLA/📎, título (2 linhas), analista, data abertura
- Acessibilidade: `role="button"`, `tabIndex`, `onKeyDown` (Enter)

## Concern

**Kanban não existe ainda no React app.**

O plano dizia "modificar o componente de card do kanban existente", mas o kanban (board de chamados) ainda está na **UI legada** (raiz/PHP/legacy). O React app (`/v2`) ainda não tem tela de kanban — apenas Admin e AdminServiceNow estão migrados (ver `App.tsx`).

**Decisão tomada:** Criado `ChamadoKanbanCard.tsx` como componente standalone pronto para uso quando o kanban for migrado para React. O modal `ChamadoDetalheModal.tsx` é independente e pode ser importado em qualquer componente futuro.

**Para ativar quando o kanban for migrado:**
```tsx
import { ChamadoKanbanCard, ChamadoCard } from '../components/ChamadoKanbanCard'

// No board kanban, para cada chamado:
<ChamadoKanbanCard chamado={chamado} />
```

**A regra de borda INC e o modal estão completamente implementados** — só aguardam a existência de uma tela kanban React para serem integrados.

## Adaptações ao padrão do projeto

- Usa `apiFetch<T>` em vez de `api.get()` (o plano usa padrão axios que não existe no projeto)
- Usa tema dark (`bg-[#1a1d27]` etc.) em vez de classes Tailwind light do plano
- Usa ícones `lucide-react` (já disponível no projeto) em vez de emoji para ✕
- Usa `Button` do projeto no rodapé
- NÃO criou dependências novas
