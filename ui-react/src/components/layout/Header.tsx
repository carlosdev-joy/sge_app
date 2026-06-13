import { NavLink, useNavigate } from 'react-router-dom'
import { useAuthStore } from '../../store/auth'
import { apiFetch } from '../../lib/api'
import { LogOut, User } from 'lucide-react'

const NAV = [
  { to: '/dashboard',   label: 'Dashboard',   icon: '◫' },
  { to: '/pipelines',   label: 'Pipelines',   icon: '≡' },
  { to: '/jobs',        label: 'Jobs',         icon: '⬡' },
  { to: '/logs',        label: 'Logs',         icon: '≣' },
  { to: '/ds-monitor',  label: 'DS Monitor',   icon: '⬡' },
  { to: '/governanca',  label: 'Governança',   icon: '◈' },
  { to: '/malha',       label: 'Malha',        icon: '⊞' },
]

export function Header() {
  const { user, logout, isAdmin } = useAuthStore()
  const navigate = useNavigate()

  const handleLogout = async () => {
    try { await apiFetch('/auth/logout', { method: 'POST' }) } catch {}
    logout()
    navigate('/login')
  }

  return (
    <header className="bg-[#1a1d27] border-b border-[#2a2d3a] flex items-center px-4 h-12 shrink-0 gap-1">
      <div className="font-bold text-blue-400 text-sm tracking-widest mr-4 whitespace-nowrap">⬡ ORQUESTRA</div>
      <nav className="flex items-center gap-0.5 flex-1 overflow-x-auto">
        {NAV.map((n) => (
          <NavLink
            key={n.to}
            to={n.to}
            className={({ isActive }) =>
              `px-3 py-1.5 rounded text-xs font-medium whitespace-nowrap transition-colors ${isActive ? 'bg-blue-600/20 text-blue-400' : 'text-[#94a3b8] hover:text-[#e2e8f0] hover:bg-[#2a2d3a]'}`
            }
          >
            {n.label}
          </NavLink>
        ))}
        {isAdmin() && (
          <NavLink
            to="/admin"
            className={({ isActive }) =>
              `px-3 py-1.5 rounded text-xs font-medium whitespace-nowrap transition-colors ${isActive ? 'bg-blue-600/20 text-blue-400' : 'text-[#94a3b8] hover:text-[#e2e8f0] hover:bg-[#2a2d3a]'}`
            }
          >
            ⚙ Admin
          </NavLink>
        )}
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
