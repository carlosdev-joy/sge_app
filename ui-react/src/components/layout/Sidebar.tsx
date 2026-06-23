import { NavLink } from 'react-router-dom'
import { PanelLeftClose, PanelLeftOpen } from 'lucide-react'
import { useVisibleNav } from '../../lib/nav'
import { useSidebarCollapsed } from '../../lib/sidebar'

// Sidebar do shell v2: navegação agrupada por domínio (useVisibleNav), com modo
// expandido (ícone + label + cabeçalho de seção) e colapsado (só ícone + tooltip).
// Superfície semântica (bg-panel/border-edge/text-dim) — não o gradiente do header;
// estado ativo em azul com par claro+escuro (regra de ouro de cores).
export function Sidebar() {
  const { groups } = useVisibleNav()
  const [collapsed, toggle] = useSidebarCollapsed()

  const itemClass = (active: boolean) =>
    [
      'flex items-center rounded-md text-sm font-medium transition-colors',
      collapsed ? 'justify-center w-10 h-10 mx-auto' : 'gap-3 px-3 py-2',
      active
        ? 'bg-blue-50 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300'
        : 'text-dim hover:bg-edge/40 hover:text-ink',
    ].join(' ')

  return (
    <aside
      className={`shrink-0 h-full bg-panel border-r border-edge flex flex-col transition-[width] duration-200 ${collapsed ? 'w-16' : 'w-60'}`}
    >
      {/* Recolher / expandir */}
      <div className={`flex items-center h-12 border-b border-edge ${collapsed ? 'justify-center' : 'justify-end px-2'}`}>
        <button
          onClick={toggle}
          className="text-dim hover:text-ink hover:bg-edge/40 rounded-md p-1.5 transition-colors"
          title={collapsed ? 'Expandir menu' : 'Recolher menu'}
          aria-label={collapsed ? 'Expandir menu' : 'Recolher menu'}
        >
          {collapsed ? <PanelLeftOpen size={18} /> : <PanelLeftClose size={18} />}
        </button>
      </div>

      {/* Grupos + itens */}
      <nav className="flex-1 overflow-y-auto py-2">
        {groups.map((g, i) => (
          <div key={g.group} className={!collapsed && i > 0 ? 'mt-3' : ''}>
            {!collapsed && (
              <div className="px-3 pb-1 text-[10px] font-semibold uppercase tracking-wider text-dim">
                {g.group}
              </div>
            )}
            {collapsed && i > 0 && <div className="mx-3 my-2 border-t border-edge" />}
            <ul className="space-y-0.5 px-2">
              {g.items.map((n) => {
                const Icon = n.icon
                const content = (
                  <>
                    <Icon size={18} className="shrink-0" />
                    {!collapsed && <span className="truncate">{n.label}</span>}
                  </>
                )
                return (
                  <li key={n.to}>
                    {n.migrated ? (
                      <NavLink
                        to={n.to}
                        title={collapsed ? n.label : undefined}
                        className={({ isActive }) => itemClass(isActive)}
                      >
                        {content}
                      </NavLink>
                    ) : (
                      <a
                        href={n.legacyHref}
                        title={collapsed ? n.label : undefined}
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
  )
}
