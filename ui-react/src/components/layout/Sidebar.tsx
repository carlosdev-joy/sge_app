import { NavLink } from 'react-router-dom'
import { PanelLeftClose, PanelLeftOpen, X } from 'lucide-react'
import { useVisibleNav } from '../../lib/nav'
import { useSidebarCollapsed } from '../../lib/sidebar'
import { useMediaQuery } from '../../lib/useMediaQuery'

// Sidebar do shell v2: navegação agrupada por domínio (useVisibleNav).
// - Desktop (md+): em fluxo, colapsável (ícone+label ↔ só ícone+tooltip), persistido.
// - Mobile: drawer off-canvas (fixed) que entra por cima do conteúdo, com backdrop;
//   sempre expandida (labels). Aberto/fechado é controlado pelo AppShellV2.
// Superfície semântica (bg-panel/border-edge/text-dim); ativo em azul (par claro+escuro).
export function Sidebar({ mobileOpen, onClose }: { mobileOpen: boolean; onClose: () => void }) {
  const { groups } = useVisibleNav()
  const [collapsed, toggle] = useSidebarCollapsed()
  const isDesktop = useMediaQuery('(min-width: 768px)')
  const compact = collapsed && isDesktop   // só-ícones só no desktop colapsado

  const itemClass = (active: boolean) =>
    [
      'flex items-center rounded-md text-sm font-medium transition-colors',
      compact ? 'justify-center w-10 h-10 mx-auto' : 'gap-3 px-3 py-2',
      active
        ? 'bg-blue-50 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300'
        : 'text-dim hover:bg-edge/40 hover:text-ink',
    ].join(' ')

  return (
    <>
      {/* Backdrop (mobile) */}
      {mobileOpen && (
        <div className="fixed inset-0 z-40 bg-black/50 md:hidden" onClick={onClose} aria-hidden />
      )}

      <aside
        className={`bg-panel border-r border-edge flex flex-col shrink-0
          fixed inset-y-0 left-0 z-50 transition-all duration-200
          md:static md:z-auto md:translate-x-0
          ${mobileOpen ? 'translate-x-0' : '-translate-x-full'}
          ${compact ? 'w-16' : 'w-60'}`}
      >
        {/* Topo: recolher (desktop) / fechar (mobile) */}
        <div className={`flex items-center h-12 border-b border-edge px-2 ${compact ? 'justify-center' : 'justify-end'}`}>
          <button
            onClick={toggle}
            className="hidden md:inline-flex text-dim hover:text-ink hover:bg-edge/40 rounded-md p-1.5 transition-colors"
            title={collapsed ? 'Expandir menu' : 'Recolher menu'}
            aria-label={collapsed ? 'Expandir menu' : 'Recolher menu'}
          >
            {collapsed ? <PanelLeftOpen size={18} /> : <PanelLeftClose size={18} />}
          </button>
          <button
            onClick={onClose}
            className="md:hidden inline-flex text-dim hover:text-ink hover:bg-edge/40 rounded-md p-1.5 transition-colors"
            aria-label="Fechar menu"
          >
            <X size={18} />
          </button>
        </div>

        {/* Grupos + itens */}
        <nav className="flex-1 overflow-y-auto py-2">
          {groups.map((g, i) => (
            <div key={g.group} className={!compact && i > 0 ? 'mt-3' : ''}>
              {/* Cabeçalho de seção só para grupos com 2+ itens (evita seção de 1 item) */}
              {!compact && g.items.length > 1 && (
                <div className="px-3 pb-1 text-[10px] font-semibold uppercase tracking-wider text-dim">
                  {g.group}
                </div>
              )}
              {compact && i > 0 && <div className="mx-3 my-2 border-t border-edge" />}
              <ul className="space-y-0.5 px-2">
                {g.items.map((n) => {
                  const Icon = n.icon
                  const label = n.labelV2 ?? n.label   // rótulo do v2; cai no clássico se ausente
                  const content = (
                    <>
                      <Icon size={18} className="shrink-0" />
                      {!compact && <span className="truncate">{label}</span>}
                    </>
                  )
                  return (
                    <li key={n.to}>
                      {n.migrated ? (
                        <NavLink
                          to={n.to}
                          title={compact ? label : undefined}
                          className={({ isActive }) => itemClass(isActive)}
                        >
                          {content}
                        </NavLink>
                      ) : (
                        <a
                          href={n.legacyHref}
                          title={compact ? label : undefined}
                          className={itemClass(false)}
                        >
                          {content}
                        </a>
                      )}
                    </li>
                  )
                })}
              </ul>
            </div>
          ))}
        </nav>
      </aside>
    </>
  )
}
