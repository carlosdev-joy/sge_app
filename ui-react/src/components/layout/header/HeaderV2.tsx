import { useLocation } from 'react-router-dom'
import { Menu } from 'lucide-react'
import { NAV } from '../../../lib/nav'
import { Brand } from './Brand'
import { HeaderControls } from './HeaderControls'

// Header fino do shell v2: hambúrguer (mobile) + identidade (marca) + título da
// página atual (breadcrumb leve, derivado do NAV) + controles globais. A
// navegação vive na sidebar. Reusa Brand e HeaderControls; superfície ORQ Navy fixa nos dois temas.
export function HeaderV2({ onMenuClick }: { onMenuClick?: () => void } = {}) {
  const { pathname } = useLocation()
  const current = NAV.find((n) => pathname === n.to || pathname.startsWith(n.to + '/'))

  return (
    <header
      className="shrink-0 text-white bg-[rgb(var(--brand-navy))]"
    >
      <div className="flex items-center gap-1.5 px-2 sm:gap-3 sm:px-4 h-[52px]">
        {onMenuClick && (
          <button
            type="button"
            onClick={onMenuClick}
            className="md:hidden shrink-0 flex items-center justify-center w-10 h-10 text-white/80 hover:text-white rounded hover:bg-white/10 transition-colors"
            aria-label="Abrir menu"
          >
            <Menu size={20} />
          </button>
        )}
        <Brand />
        {current && (
          <div className="hidden lg:flex items-center gap-2 min-w-0 ml-2">
            <span aria-hidden="true" className="text-white/30">/</span>
            <span className="text-sm font-medium text-white/90 truncate">{current.label}</span>
          </div>
        )}
        <div className="flex-1 min-w-0" />
        <HeaderControls />
      </div>
      {/* filete laranja institucional CAIXA */}
      <div className="h-1 bg-gradient-to-r from-[#F26B00] via-[#FF9D4D] to-[#F26B00]" />
    </header>
  )
}
