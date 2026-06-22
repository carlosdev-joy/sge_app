// Registro central de navegação — fonte única da verdade da migração incremental.
//
// `migrated: true`  → a tela já roda em React; o link é interno (React Router) e a
//                     rota é montada em App.tsx.
// `migrated: false` → a tela ainda vive na UI legada; o link aponta para `/` (raiz),
//                     devolvendo o usuário ao sistema antigo.
//
// Para migrar a próxima tela: implemente a página, monte a rota em App.tsx e
// vire `migrated` para true aqui. Nada mais precisa mudar no shell.

import type { LucideIcon } from 'lucide-react'
import {
  LayoutDashboard, Workflow, Boxes, ScrollText,
  ShieldCheck, Network, Settings, FileSearch, ClipboardList, BarChart3, Share2, Terminal,
} from 'lucide-react'

export interface NavItem {
  to: string          // rota React (basename /v2 já aplicado pelo router)
  label: string
  icon: LucideIcon
  legacyHref: string  // para onde mandar quando ainda não migrada (UI legada)
  migrated: boolean
  adminOnly?: boolean
  perm?: string       // recurso RBAC (tela_*) exigido para exibir o item
}

export const NAV: NavItem[] = [
  { to: '/dashboard',  label: 'Dashboard',  icon: LayoutDashboard, legacyHref: '/', migrated: true, perm: 'tela_dashboard' },
  { to: '/pipelines',  label: 'Pipelines',  icon: Workflow,        legacyHref: '/', migrated: true, perm: 'tela_pipelines' },
  { to: '/jobs',       label: 'Jobs',       icon: Boxes,           legacyHref: '/', migrated: true, perm: 'tela_jobs' },
  { to: '/logs',       label: 'Logs',       icon: ScrollText,      legacyHref: '/', migrated: true, perm: 'tela_logs' },
  { to: '/governanca', label: 'Governança', icon: ShieldCheck,     legacyHref: '/', migrated: true, perm: 'tela_governanca' },
  { to: '/malha',      label: 'Malha',      icon: Network,         legacyHref: '/', migrated: true, perm: 'tela_malha' },
  { to: '/impacto-campo', label: 'Impacto Campo', icon: FileSearch,    legacyHref: '/', migrated: true, perm: 'tela_impacto_campo' },
  { to: '/planos-ajuste', label: 'Planos Ajuste', icon: ClipboardList, legacyHref: '/', migrated: true, perm: 'tela_plano_ajuste' },
  { to: '/powerbi',    label: 'Power BI',  icon: BarChart3,       legacyHref: '/', migrated: true, perm: 'tela_powerbi' },
  { to: '/malha-ds',   label: 'Malha DS',   icon: Share2,          legacyHref: '/', migrated: true, perm: 'tela_malha_ds' },
  { to: '/ds-console', label: 'Console DS',  icon: Terminal,        legacyHref: '/', migrated: true, perm: 'tela_ds_console' },
  { to: '/admin',      label: 'Admin',      icon: Settings,        legacyHref: '/', migrated: true, adminOnly: true, perm: 'tela_admin' },
]

// Telas migradas (em React) — usado para montar rotas e decidir fallback.
export const MIGRATED = NAV.filter((n) => n.migrated)
