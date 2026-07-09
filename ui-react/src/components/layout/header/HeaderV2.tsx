import { useLocation } from 'react-router-dom'
import { Menu } from 'lucide-react'
import { NAV } from '../../../lib/nav'
import { Brand } from './Brand'
import { HeaderControls } from './HeaderControls'

// Header fino do shell v2: hambúrguer (mobile) + identidade (marca) + título da
// página atual (breadcrumb leve, derivado do NAV) + controles globais. A
// navegação vive na sidebar. Reusa Brand e HeaderControls; superfície gradiente.
export function HeaderV2({ onMenuClick }: { onMenuClick?: () => void } = {}) {
  const { pathname } = useLocation()
  const current = NAV.find((n) => pathname === n.to || pathname.startsWith(n.to + '/'))

  return (
    <header
      className="shrink-0 text-white"
      style={{ background: 'linear-gradient(135deg, #1A5FA8 0%, #0F4C88 55%, #0D3D6B 100%)' }}
    >
      <div className="flex items-center gap-3 px-4 h-[52px]">
        {onMenuClick && (
          <button
            onClick={onMenuClick}
            className="md:hidden -ml-1 text-white/80 hover:text-white p-1 rounded hover:bg-white/10 transition-colors"
            aria-label="Abrir menu"
          >
            <Menu size={20} />
          </button>
        )}
        <Brand />
        {current && (
          <div className="hidden sm:flex items-center gap-2 min-w-0 ml-2">
            <span className="text-white/30">/</span>
            <span className="text-sm font-medium text-white/90 truncate">{current.label}</span>
          </div>
        )}
        <div className="flex-1" />
        <HeaderControls />
      </div>
      {/* filete laranja institucional CAIXA */}
      <div className="h-1 bg-gradient-to-r from-[#F26B00] via-[#FF9D4D] to-[#F26B00]" />
    </header>
  )
}
