// Registro central de navegação — fonte única da verdade da migração incremental
// e, agora, das rotas (App.tsx deriva as <Route>s deste registry) e do
// agrupamento por domínio (sidebar do shell v2).
//
// `migrated: true`  → a tela já roda em React; o link é interno (React Router) e a
//                     rota é montada em App.tsx (a partir de MIGRATED).
// `migrated: false` → a tela ainda vive na UI legada; o link aponta para `/` (raiz),
//                     devolvendo o usuário ao sistema antigo.
//
// Para migrar a próxima tela: implemente a página, registre o item aqui (com seu
// `group`) e mapeie o elemento em App.tsx. Nada mais precisa mudar no shell.

import type { LucideIcon } from 'lucide-react'
import {
  LayoutDashboard, Workflow, Boxes, ScrollText, Bell,
  ShieldCheck, Network, Settings, FileSearch, ClipboardList, BarChart3, Share2, Terminal,
} from 'lucide-react'
import { useAuthStore } from '../store/auth'

// Domínios da navegação, na ordem de exibição (cabeçalho de seção na sidebar).
// Nível 2: "Operação" (monitorar, diário) separada de "Construção" (cadastrar, dev).
export type NavGroup = 'Operação' | 'Construção' | 'Governança & Dados' | 'DataStage' | 'BI' | 'Administração'
export const NAV_GROUPS: NavGroup[] = ['Operação', 'Construção', 'Governança & Dados', 'DataStage', 'BI', 'Administração']

export interface NavItem {
  to: string          // rota React (basename /v2 já aplicado pelo router)
  label: string       // rótulo no shell clássico (e fallback do v2)
  labelV2?: string    // rótulo só no shell v2; clássico permanece em `label`
  icon: LucideIcon
  group: NavGroup     // domínio para agrupar na sidebar (shell v2)
  legacyHref: string  // para onde mandar quando ainda não migrada (UI legada)
  migrated: boolean
  adminOnly?: boolean
  perm?: string       // recurso RBAC (tela_*) exigido para exibir o item
  v2Only?: boolean    // só aparece no menu do shell v2 (o clássico não exibe)
}

export const NAV: NavItem[] = [
  { to: '/dashboard',  label: 'Dashboard',  icon: LayoutDashboard, group: 'Operação',   legacyHref: '/', migrated: true, perm: 'tela_dashboard' },
  { to: '/pipelines',  label: 'Pipelines',  icon: Workflow,        group: 'Construção', legacyHref: '/', migrated: true, perm: 'tela_pipelines' },
  { to: '/jobs',       label: 'Jobs',       labelV2: 'Etapas',                icon: Boxes,         group: 'Construção', legacyHref: '/', migrated: true, perm: 'tela_jobs' },
  { to: '/logs',       label: 'Logs',       icon: ScrollText,      group: 'Operação',   legacyHref: '/', migrated: true, perm: 'tela_logs' },
  { to: '/avisos',     label: 'Avisos',     icon: Bell,            group: 'Operação',   legacyHref: '/', migrated: true, v2Only: true },
  { to: '/governanca', label: 'Governança', labelV2: 'Catálogo & Lineage',    icon: ShieldCheck,   group: 'Governança & Dados', legacyHref: '/', migrated: true, perm: 'tela_governanca' },
  { to: '/malha',      label: 'Malha',      labelV2: 'Malha de Pipelines',    icon: Network,       group: 'Governança & Dados', legacyHref: '/', migrated: true, perm: 'tela_malha' },
  { to: '/impacto-campo', label: 'Impacto Campo', labelV2: 'Impacto de Campo', icon: FileSearch,   group: 'Governança & Dados', legacyHref: '/', migrated: true, perm: 'tela_impacto_campo' },
  { to: '/planos-ajuste', label: 'Planos Ajuste', labelV2: 'Planos de Ajuste', icon: ClipboardList, group: 'Governança & Dados', legacyHref: '/', migrated: true, perm: 'tela_plano_ajuste' },
  { to: '/malha-ds',   label: 'Malha DS',   labelV2: 'Estrutura (Malha DS)',  icon: Share2,        group: 'DataStage',  legacyHref: '/', migrated: true, perm: 'tela_malha_ds' },
  { to: '/ds-console', label: 'Console DS', labelV2: 'Console (dsjob)',       icon: Terminal,      group: 'DataStage',  legacyHref: '/', migrated: true, perm: 'tela_ds_console' },
  { to: '/powerbi',    label: 'Power BI',   icon: BarChart3,       group: 'BI',         legacyHref: '/', migrated: true, perm: 'tela_powerbi' },
  { to: '/admin',      label: 'Admin',      icon: Settings,        group: 'Administração', legacyHref: '/', migrated: true, adminOnly: true, perm: 'tela_admin' },
]

// Telas migradas (em React) — usado para montar rotas (App.tsx) e decidir fallback.
export const MIGRATED = NAV.filter((n) => n.migrated)

// Itens de um domínio, já filtrados por permissão (para a sidebar agrupada).
export interface NavGroupView {
  group: NavGroup
  items: NavItem[]
}

// Hook compartilhado pelos dois shells: filtra o NAV por RBAC (`canSee`) e
// devolve tanto a lista plana (header clássico) quanto o agrupamento por domínio
// com seções vazias removidas (sidebar v2). Mesma semântica do `canSee` original:
// item sem `perm`, ou usuário sem lista de permissões, é sempre visível.
export function useVisibleNav(): { visible: NavItem[]; groups: NavGroupView[] } {
  const perms = useAuthStore((s) => s.user?.permissoes) ?? []
  const canSee = (n: NavItem) => !n.perm || perms.length === 0 || perms.includes(n.perm)
  const all = NAV.filter(canSee)
  const visible = all.filter((n) => !n.v2Only)   // header clássico (lista plana) não mostra itens v2-only
  const groups = NAV_GROUPS
    .map((group) => ({ group, items: all.filter((n) => n.group === group) }))
    .filter((g) => g.items.length > 0)
  return { visible, groups }
}
