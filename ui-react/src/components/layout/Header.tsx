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
    window.location.href = '/'
  }

  const tabClass = (active: boolean) =>
    `px-3 py-1.5 rounded text-xs font-medium whitespace-nowrap transition-colors ${
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

        {/* Logo Caixa Vida e Previdência — PNG em public/images/logo-cvp.png.
            Quando o arquivo não existir o img fica oculto (onerror) e só o
            texto do brand aparece, igual ao fallback do legado. */}
        <a href="/" className="shrink-0 flex items-center" title="Voltar ao sistema">
          <img
            src="/v2/images/logo-cvp.svg"
            alt="CVP"
            className="h-9 w-auto"
            onError={(e) => { (e.currentTarget as HTMLImageElement).style.display = 'none' }}
          />
        </a>

        {/* Brand */}
        <a href="/" className="shrink-0 flex flex-col leading-tight mr-2" title="Voltar ao sistema">
          <span className="text-xs font-semibold tracking-widest uppercase opacity-95">ORQUESTRA</span>
          <span className="text-[10px] opacity-60 tracking-wide">Gestão de Pipelines</span>
        </a>

        {/* Nav */}
        <nav className="flex items-center gap-0.5 flex-1 overflow-x-auto">
          {NAV.map((n) => {
            if (n.adminOnly && !isAdmin()) return null
            return n.migrated ? (
              <NavLink key={n.to} to={n.to} className={({ isActive }) => tabClass(isActive)}>
                {n.label}
              </NavLink>
            ) : (
              <a key={n.to} href={n.legacyHref} className={tabClass(false)}>
                {n.label}
              </a>
            )
          })}
        </nav>

        {/* Usuário + logout */}
        <div className="flex items-center gap-2 shrink-0">
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
