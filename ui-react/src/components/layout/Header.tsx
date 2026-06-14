import { useState } from 'react'
import { NavLink } from 'react-router-dom'
import { useAuthStore } from '../../store/auth'
import { apiFetch } from '../../lib/api'
import { NAV } from '../../lib/nav'
import { getTheme, toggleTheme } from '../../lib/theme'
import { LogOut, User, Sun, Moon } from 'lucide-react'

export function Header() {
  const { user, logout, isAdmin } = useAuthStore()
  const [theme, setTheme] = useState(getTheme())

  const handleLogout = async () => {
    try { await apiFetch('/auth/logout', { method: 'POST' }) } catch {}
    logout()
    window.location.href = '/'
  }

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

        {/* Logo + brand → voltam ao sistema legado */}
        <a href="/" className="shrink-0 flex items-center gap-2.5" title="Voltar ao sistema">
          <img
            src="https://rseofspzecpjtqzcbaol.supabase.co/storage/v1/object/public/mundolc/Vertical_Branco.png"
            className="h-9 w-auto"
            alt="Caixa Vida e Previdência"
          />
          <span className="flex flex-col leading-tight">
            <span className="text-xs font-semibold tracking-widest uppercase opacity-95">ORQUESTRA</span>
            <span className="text-[10px] opacity-60 tracking-wide">Gestão de Pipelines</span>
          </span>
        </a>

        {/* Nav com ícones */}
        <nav className="flex items-center gap-0.5 flex-1 overflow-x-auto ml-2">
          {NAV.map((n) => {
            if (n.adminOnly && !isAdmin()) return null
            const Icon = n.icon
            const content = (
              <>
                <Icon size={13} />
                <span>{n.label}</span>
              </>
            )
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

        {/* Tema + usuário + logout */}
        <div className="flex items-center gap-2 shrink-0">
          <button
            onClick={() => setTheme(toggleTheme())}
            className="text-white/70 hover:text-white transition-colors p-1 rounded hover:bg-white/10"
            title={theme === 'dark' ? 'Mudar para tema claro' : 'Mudar para tema escuro'}
            aria-label="Alternar tema"
          >
            {theme === 'dark' ? <Sun size={15} /> : <Moon size={15} />}
          </button>
          <span className="flex items-center gap-1 text-xs text-white/70">
            <User size={12} />{user?.primeiro_nome ?? user?.matricula}
          </span>
          <button
            onClick={handleLogout}
            className="text-white/60 hover:text-white transition-colors p-1 rounded hover:bg-white/10"
            title="Sair"
          >
            <LogOut size={14} />
          </button>
        </div>

      </div>
    </header>
  )
}
