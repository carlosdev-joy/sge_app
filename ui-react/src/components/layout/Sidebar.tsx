import { NavLink } from 'react-router-dom'
import { PanelLeftClose, PanelLeftOpen, X } from 'lucide-react'
import { useVisibleNav } from '../../lib/nav'
import { useSidebarCollapsed } from '../../lib/sidebar'
import { useMediaQuery } from '../../lib/useMediaQuery'
import { useRef } from 'react'
import { useOverlay, trapTabKey } from '../ui/overlay'

// Sidebar do shell v2: navegação agrupada por domínio (useVisibleNav).
// - Desktop (md+): em fluxo, colapsável (ícone+label ↔ só ícone+tooltip), persistido.
// - Mobile: drawer off-canvas (fixed) que entra por cima do conteúdo, com backdrop;
//   sempre expandida (labels). Aberto/fechado é controlado pelo AppShellV2.
// Superfície semântica (bg-panel/border-edge/text-dim); ativo em azul (par claro+escuro).
export function Sidebar({ mobileOpen, onClose }: { mobileOpen: boolean; onClose: () => void }) {
  const groups = useVisibleNav()
  const [collapsed, toggle] = useSidebarCollapsed()
  const isDesktop = useMediaQuery('(min-width: 768px)')
  const compact = collapsed && isDesktop   // só-ícones só no desktop colapsado
  const panelRef = useRef<HTMLElement>(null)
  useOverlay(mobileOpen && !isDesktop, onClose, panelRef)

  const itemClass = (active: boolean) =>
    [
      'flex items-center rounded-md text-sm font-medium transition-colors',
      compact ? 'justify-center w-10 h-11 mx-auto' : 'gap-3 px-3 py-2 min-h-11',
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
        ref={panelRef}
        role={!isDesktop && mobileOpen ? 'dialog' : undefined}
        aria-modal={!isDesktop && mobileOpen ? true : undefined}
        aria-label="Menu principal"
        tabIndex={-1}
        inert={!isDesktop && !mobileOpen}
        onKeyDown={event => { if (!isDesktop && mobileOpen) trapTabKey(event, panelRef.current) }}
        className={`bg-panel border-r border-edge flex flex-col shrink-0
          fixed inset-y-0 left-0 z-50 transition-all duration-200
          md:static md:z-auto md:translate-x-0
          ${mobileOpen ? 'translate-x-0' : '-translate-x-full'}
          ${compact ? 'w-14' : 'w-56'}`}
      >
        {/* Topo: recolher (desktop) / fechar (mobile) */}
        <div className={`flex items-center h-12 border-b border-edge px-2 ${compact ? 'justify-center' : 'justify-end'}`}>
          {isDesktop && <button
            onClick={toggle}
            type="button"
            className="ui-button ui-button-small ui-icon-button hidden md:inline-flex text-dim hover:text-ink hover:bg-edge/40 rounded-md p-1.5 transition-colors"
            title={collapsed ? 'Expandir menu' : 'Recolher menu'}
            aria-label={collapsed ? 'Expandir menu' : 'Recolher menu'}
          >
            {collapsed ? <PanelLeftOpen size={18} /> : <PanelLeftClose size={18} />}
          </button>}
          {!isDesktop && <button
            onClick={onClose}
            type="button"
            className="ui-button ui-button-small ui-icon-button md:hidden inline-flex text-dim hover:text-ink hover:bg-edge/40 rounded-md p-1.5 transition-colors"
            aria-label="Fechar menu"
          >
            <X size={18} />
          </button>}
        </div>

        {/* Grupos + itens */}
        <nav aria-label="Destinos da plataforma" className="min-h-0 flex-1 overflow-y-auto py-2">
          {groups.map((g, i) => (
            <div key={g.group} className={!compact && i > 0 ? 'mt-3' : ''}>
              {/* Cabeçalho de seção só para grupos com 2+ itens (evita seção de 1 item) */}
              {!compact && g.items.length > 1 && (
                <div className="px-3 pb-1 text-xs font-semibold text-dim">
                  {g.group}
                </div>
              )}
              {compact && i > 0 && <div className="mx-3 my-2 border-t border-edge" />}
              <ul className="space-y-0.5 px-2">
                {g.items.map((n) => {
                  const Icon = n.icon
                  const label = n.label
                  const content = (
                    <>
                      <Icon size={18} className="shrink-0" />
                      {!compact && <span className="min-w-0 break-words">{label}</span>}
                    </>
                  )
                  return (
                    <li key={n.to}>
                      <NavLink
                        to={n.to}
                        aria-label={label}
                        title={compact ? label : undefined}
                        className={({ isActive }) => itemClass(isActive)}
                      >
                        {content}
                      </NavLink>
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
