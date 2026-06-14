import { NavLink } from 'react-router-dom'
import { useAuthStore } from '../../store/auth'
import { apiFetch } from '../../lib/api'
import { NAV } from '../../lib/nav'
import { LogOut, User } from 'lucide-react'

export function Header() {
  const { user, logout, isAdmin } = useAuthStore()

  const handleLogout = async () => {
    try { await apiFetch('/auth/logout', { method: 'POST' }) } catch {}
    logout()
    // Login centralizado na UI legada (raiz).
    window.location.href = '/'
  }

  const itemClass = (active: boolean) =>
    `px-3 py-1.5 rounded text-xs font-medium whitespace-nowrap transition-colors ${
      active ? 'bg-blue-600/20 text-blue-400' : 'text-[#94a3b8] hover:text-[#e2e8f0] hover:bg-[#2a2d3a]'
    }`

  return (
    <header className="bg-[#1a1d27] border-b border-[#2a2d3a] flex items-center px-4 h-12 shrink-0 gap-1">
      <div className="font-bold text-blue-400 text-sm tracking-widest mr-4 whitespace-nowrap">⬡ ORQUESTRA</div>
      <nav className="flex items-center gap-0.5 flex-1 overflow-x-auto">
        {NAV.map((n) => {
          if (n.adminOnly && !isAdmin()) return null
          // Tela migrada → navegação interna React. Tela legada → volta para a raiz.
          return n.migrated ? (
            <NavLink key={n.to} to={n.to} className={({ isActive }) => itemClass(isActive)}>
              {n.label}
            </NavLink>
          ) : (
            <a key={n.to} href={n.legacyHref} className={itemClass(false)} title="Abre no sistema atual">
              {n.label}
            </a>
          )
        })}
      </nav>
      <div className="flex items-center gap-2 ml-2">
        <span className="text-xs text-[#94a3b8] flex items-center gap-1">
          <User size={12} />{user?.primeiro_nome ?? user?.matricula}
        </span>
        <button onClick={handleLogout} className="text-[#94a3b8] hover:text-red-400 transition-colors p-1" title="Sair">
          <LogOut size={14} />
        </button>
      </div>
    </header>
  )
}
