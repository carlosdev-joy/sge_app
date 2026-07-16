// Registro central de navegação — fonte única da verdade das rotas (App.tsx deriva
// as <Route>s deste registry) e do agrupamento por domínio (sidebar do shell).
//
// Para adicionar uma tela: implemente a página, registre o item aqui (com seu
// `group`) e mapeie o elemento em App.tsx. Nada mais precisa mudar no shell.

import type { LucideIcon } from 'lucide-react'
import {
  LayoutDashboard, Workflow, Blocks, ScrollText, Bell, ShieldAlert,
  Library, Network, Settings, Crosshair, ClipboardList, BarChart3, Terminal,
  Rocket, Gauge, Copy, Cable, OctagonX, GitBranch, ShieldCheck,
} from 'lucide-react'
import { useAuthStore } from '../store/auth'

// Domínios da navegação, na ordem de exibição (cabeçalho de seção na sidebar).
// "Operação" (monitorar, diário) separada de "Construção" (cadastrar, dev).
export type NavGroup = 'Operação' | 'Construção' | 'Governança & Dados' | 'BI' | 'Caixa Seguro' | 'Administração'
export const NAV_GROUPS: NavGroup[] = ['Operação', 'Construção', 'Governança & Dados', 'BI', 'Caixa Seguro', 'Administração']

export interface NavItem {
  to: string          // rota React
  label: string       // rótulo no menu
  icon: LucideIcon
  group: NavGroup     // domínio para agrupar na sidebar
  perm?: string       // recurso RBAC (tela_*) exigido para exibir o item
}

export const NAV: NavItem[] = [
  { to: '/dashboard',     label: 'Dashboard',          icon: LayoutDashboard, group: 'Operação',           perm: 'tela_dashboard' },
  { to: '/gestao-falhas', label: 'Gestão de Falhas',   icon: ShieldAlert,     group: 'Operação',           perm: 'tela_logs' },
  { to: '/logs',          label: 'Logs',               icon: ScrollText,      group: 'Operação',           perm: 'tela_logs' },
  { to: '/ds-console',    label: 'Console DataStage',  icon: Terminal,        group: 'Operação',           perm: 'tela_ds_console' },
  { to: '/performance',   label: 'Performance',        icon: Gauge,           group: 'Operação',           perm: 'tela_performance' },
  { to: '/finalizacao',   label: 'Finalizar Pipeline', icon: OctagonX,        group: 'Operação',           perm: 'tela_finalizacao' },
  { to: '/avisos',        label: 'Avisos',             icon: Bell,            group: 'Operação' },
  { to: '/pipelines',     label: 'Pipelines',          icon: Workflow,        group: 'Construção',         perm: 'tela_pipelines' },
  { to: '/jobs',          label: 'Etapas',             icon: Blocks,          group: 'Construção',         perm: 'tela_jobs' },
  // Mesma permissão de Etapas: /fluxos é o MESMO editor em tela dedicada
  // (decisão revisada em docs/DESIGN_navegacao_regroup.md).
  { to: '/fluxos',        label: 'Fluxos',             icon: GitBranch,       group: 'Construção',         perm: 'tela_jobs' },
  { to: '/publicacao',    label: 'Publicação',         icon: Rocket,          group: 'Construção',         perm: 'tela_logs' },
  { to: '/governanca',    label: 'Catálogo & Lineage', icon: Library,         group: 'Governança & Dados', perm: 'tela_governanca' },
  { to: '/malha',         label: 'Malha de Pipelines', icon: Network,         group: 'Governança & Dados', perm: 'tela_malha' },
  { to: '/impacto-campo', label: 'Impacto de Campo',   icon: Crosshair,       group: 'Governança & Dados', perm: 'tela_impacto_campo' },
  { to: '/planos-ajuste', label: 'Planos de Ajuste',   icon: ClipboardList,   group: 'Governança & Dados', perm: 'tela_plano_ajuste' },
  { to: '/copia-dados',   label: 'Cópia de Dados',     icon: Copy,            group: 'Governança & Dados', perm: 'tela_copia_dados' },
  { to: '/inventario',    label: 'Inventário de Consumidores', icon: Cable,   group: 'Governança & Dados', perm: 'tela_inventario' },
  { to: '/powerbi',       label: 'Power BI',           icon: BarChart3,       group: 'BI',                 perm: 'tela_powerbi' },
  // Seção Caixa Seguro (src/caixa) — telas nativas em rotas próprias no
  // App.tsx (F9 da migração); navegação interna pelo MenuButton.
  { to: '/caixa-seguro',  label: 'Busca & Vendas',     icon: ShieldCheck,     group: 'Caixa Seguro',       perm: 'tela_caixa_seguro' },
  { to: '/admin',         label: 'Admin',              icon: Settings,        group: 'Administração',      perm: 'tela_admin' },
]

// Itens de um domínio, já filtrados por permissão (para a sidebar agrupada).
export interface NavGroupView {
  group: NavGroup
  items: NavItem[]
}

// Regra de visibilidade RBAC — compartilhada entre a sidebar (useVisibleNav),
// o guard de rota (RequirePerm no App.tsx) e o redirect pós-login. Recurso sem
// exigência, ou usuário sem lista de permissões, é sempre visível; a proteção
// de dados continua sendo o 403 do backend.
export const canAccess = (perm: string | undefined, perms: string[]) =>
  !perm || perms.length === 0 || perms.includes(perm)

// Primeira tela visível na ordem do NAV — destino pós-login e fallback quando
// uma rota é negada (ex.: usuário só-Caixa Seguro não cai em /dashboard).
// /avisos não exige permissão, então sempre existe destino.
export function firstVisiblePath(perms: string[] | null | undefined): string {
  const p = perms ?? []
  return NAV.find((n) => canAccess(n.perm, p))?.to ?? '/avisos'
}

// Filtra o NAV por RBAC (`canAccess`) e agrupa por domínio, removendo seções vazias.
export function useVisibleNav(): NavGroupView[] {
  const perms = useAuthStore((s) => s.user?.permissoes) ?? []
  const all = NAV.filter((n) => canAccess(n.perm, perms))
  return NAV_GROUPS
    .map((group) => ({ group, items: all.filter((n) => n.group === group) }))
    .filter((g) => g.items.length > 0)
}
