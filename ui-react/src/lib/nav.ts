// Registro central de navegação — fonte única da verdade da migração incremental.
//
// `migrated: true`  → a tela já roda em React; o link é interno (React Router) e a
//                     rota é montada em App.tsx.
// `migrated: false` → a tela ainda vive na UI legada; o link aponta para `/` (raiz),
//                     devolvendo o usuário ao sistema antigo.
//
// Para migrar a próxima tela: implemente a página, monte a rota em App.tsx e
// vire `migrated` para true aqui. Nada mais precisa mudar no shell.

export interface NavItem {
  to: string
  label: string
  legacyHref: string
  migrated: boolean
  adminOnly?: boolean
}

export const NAV: NavItem[] = [
  { to: '/dashboard',  label: 'Dashboard',  legacyHref: '/', migrated: false },
  { to: '/chamados',   label: 'Chamados',   legacyHref: '/', migrated: true },
  { to: '/pipelines',  label: 'Pipelines',  legacyHref: '/', migrated: false },
  { to: '/jobs',       label: 'Jobs',       legacyHref: '/', migrated: false },
  { to: '/logs',       label: 'Logs',       legacyHref: '/', migrated: false },
  { to: '/ds-monitor', label: 'DS Monitor', legacyHref: '/', migrated: false },
  { to: '/governanca', label: 'Governança', legacyHref: '/', migrated: false },
  { to: '/malha',      label: 'Malha',      legacyHref: '/', migrated: false },
  { to: '/admin',      label: '⚙ Admin',    legacyHref: '/', migrated: true, adminOnly: true },
]

// Telas migradas (em React) — usado para montar rotas e decidir fallback.
export const MIGRATED = NAV.filter((n) => n.migrated)
