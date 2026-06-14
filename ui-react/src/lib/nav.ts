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
  Activity, ShieldCheck, Network, Settings, FileSearch, ClipboardList,
} from 'lucide-react'

export interface NavItem {
  to: string          // rota React (basename /v2 já aplicado pelo router)
  label: string
  icon: LucideIcon
  legacyHref: string  // para onde mandar quando ainda não migrada (UI legada)
  migrated: boolean
  adminOnly?: boolean
}

export const NAV: NavItem[] = [
  { to: '/dashboard',  label: 'Dashboard',  icon: LayoutDashboard, legacyHref: '/', migrated: false },
  { to: '/pipelines',  label: 'Pipelines',  icon: Workflow,        legacyHref: '/', migrated: false },
  { to: '/jobs',       label: 'Jobs',       icon: Boxes,           legacyHref: '/', migrated: true },
  { to: '/logs',       label: 'Logs',       icon: ScrollText,      legacyHref: '/', migrated: true },
  { to: '/ds-monitor', label: 'DS Monitor', icon: Activity,        legacyHref: '/', migrated: false },
  { to: '/governanca', label: 'Governança', icon: ShieldCheck,     legacyHref: '/', migrated: true },
  { to: '/malha',      label: 'Malha',      icon: Network,         legacyHref: '/', migrated: true },
  { to: '/impacto-campo', label: 'Impacto Campo', icon: FileSearch,    legacyHref: '/', migrated: true },
  { to: '/planos-ajuste', label: 'Planos Ajuste', icon: ClipboardList, legacyHref: '/', migrated: true },
  { to: '/admin',      label: 'Admin',      icon: Settings,        legacyHref: '/', migrated: true, adminOnly: true },
]

// Telas migradas (em React) — usado para montar rotas e decidir fallback.
export const MIGRATED = NAV.filter((n) => n.migrated)
