import { NavLink } from 'react-router-dom'
import { useVisibleNav } from '../../lib/nav'
import { Brand } from './header/Brand'
import { HeaderControls } from './header/HeaderControls'

// Header clássico (shell atual): identidade + navegação horizontal + controles
// globais. As peças (Brand, HeaderControls e os blocos de notificações/perfil/
// changelog em components/layout/header/) são reusadas pelo header fino do v2.
export function Header() {
  const { visible } = useVisibleNav()

  const tabClass = (active: boolean) =>
    `flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium whitespace-nowrap transition-colors ${
      active
        ? 'bg-white/20 text-white'
        : 'text-white/75 hover:bg-white/15 hover:text-white'
    }`

  return (
    <header
      className="shrink-0 text-white"
      style={{ background: 'linear-gradient(135deg, #1A5FA8 0%, #0F4C88 55%, #0D3D6B 100%)' }}
    >
      <div className="flex items-center gap-3 px-4 h-[52px]">
        <Brand />

        {/* Nav horizontal (clássico) */}
        <nav className="flex items-center gap-0.5 flex-1 overflow-x-auto ml-2">
          {visible.map((n) => {
            const Icon = n.icon
            const content = (<><Icon size={13} /><span>{n.label}</span></>)
            return n.migrated ? (
              <NavLink key={n.to} to={n.to} className={({ isActive }) => tabClass(isActive)}>
                {content}
              </NavLink>
            ) : (
              <a key={n.to} href={n.legacyHref} className={tabClass(false)}>
                {content}
              </a>
            )
          })}
        </nav>

        <HeaderControls />
      </div>
    </header>
  )
}
