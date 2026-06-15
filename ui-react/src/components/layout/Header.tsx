import { useState, useRef, useEffect } from 'react'
import { NavLink } from 'react-router-dom'
import { useAuthStore } from '../../store/auth'
import { apiFetch } from '../../lib/api'
import { NAV } from '../../lib/nav'
import { getTheme, toggleTheme } from '../../lib/theme'
import { LogOut, Sun, Moon, Shield, Mail, Hash, Key, Building2, ChevronDown } from 'lucide-react'

const APP_VERSION = '2.1'

// ── Avatar com iniciais ────────────────────────────────────────────────────

function initials(primeiro?: string | null, ultimo?: string | null, matricula?: string): string {
  if (primeiro && ultimo) return (primeiro[0] + ultimo[0]).toUpperCase()
  if (primeiro) return primeiro.substring(0, 2).toUpperCase()
  return (matricula ?? '??').substring(0, 2).toUpperCase()
}

// ── Perfil dropdown ────────────────────────────────────────────────────────

function ProfileDropdown({ onLogout }: { onLogout: () => void }) {
  const { user } = useAuthStore()
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function handler(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const ini = initials(user?.primeiro_nome, user?.ultimo_nome, user?.matricula)
  const nomeCompleto = [user?.primeiro_nome, user?.ultimo_nome].filter(Boolean).join(' ') || user?.matricula || '—'

  const perfilLabel: Record<string, string> = {
    admin:    'Administrador',
    editar:   'Editor',
    executar: 'Operador',
    consulta: 'Consulta',
  }

  const permColors: Record<string, string> = {
    admin:    'bg-purple-500/20 text-purple-200 border-purple-500/40',
    editar:   'bg-blue-500/20   text-blue-200   border-blue-500/40',
    executar: 'bg-green-500/20  text-green-200  border-green-500/40',
    consulta: 'bg-slate-500/20  text-slate-300  border-slate-500/40',
  }
  const perfilColor = permColors[user?.perfil ?? 'consulta'] ?? permColors.consulta

  return (
    <div ref={ref} className="relative">
      {/* Avatar button */}
      <button
        onClick={() => setOpen(v => !v)}
        className="flex items-center gap-1.5 rounded-lg px-1 py-0.5 hover:bg-white/10 transition-colors"
        title={nomeCompleto}
        aria-expanded={open}
      >
        <span className="w-7 h-7 rounded-full bg-white/20 border border-white/30 flex items-center justify-center text-[11px] font-bold text-white select-none">
          {ini}
        </span>
        <span className="text-xs text-white/80 hidden sm:block max-w-[96px] truncate">{user?.primeiro_nome ?? user?.matricula}</span>
        <ChevronDown size={11} className={`text-white/50 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>

      {/* Dropdown panel */}
      {open && (
        <div className="absolute right-0 top-[calc(100%+6px)] w-72 rounded-xl shadow-2xl border border-white/10 overflow-hidden z-50"
          style={{ background: 'linear-gradient(160deg, #1A5FA8 0%, #0D3D6B 100%)' }}>

          {/* Header do card */}
          <div className="px-4 py-4 border-b border-white/10">
            <div className="flex items-center gap-3">
              <span className="w-12 h-12 rounded-full bg-white/20 border-2 border-white/30 flex items-center justify-center text-lg font-bold text-white select-none flex-shrink-0">
                {ini}
              </span>
              <div className="min-w-0">
                <div className="text-sm font-semibold text-white truncate">{nomeCompleto}</div>
                <div className="text-[11px] text-white/60 truncate">{user?.matricula}</div>
                <span className={`inline-flex items-center mt-1 px-2 py-0.5 rounded-full text-[10px] font-bold border ${perfilColor}`}>
                  {perfilLabel[user?.perfil ?? 'consulta'] ?? user?.perfil}
                </span>
              </div>
            </div>
          </div>

          {/* Detalhes */}
          <div className="px-4 py-3 flex flex-col gap-2">
            <ProfileRow icon={<Hash size={11} />} label="Matrícula" value={user?.matricula} />
            <ProfileRow icon={<Mail size={11} />} label="E-mail" value={user?.email} />
            <ProfileRow icon={<Shield size={11} />} label="Perfil" value={perfilLabel[user?.perfil ?? ''] ?? user?.perfil} />
            {user?.area && (
              <ProfileRow icon={<Building2 size={11} />} label="Área" value={user.area} />
            )}
            {user?.permissoes && user.permissoes.length > 0 && (
              <div className="flex items-start gap-2 text-[11px]">
                <span className="text-white/40 mt-0.5 flex-shrink-0"><Key size={11} /></span>
                <span className="text-white/40 flex-shrink-0 w-20">Permissões</span>
                <div className="flex flex-wrap gap-1">
                  {user.permissoes.map(p => (
                    <span key={p} className="px-1.5 py-0.5 rounded bg-white/10 text-white/70 text-[10px] font-mono">{p}</span>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Footer */}
          <div className="px-4 py-2.5 border-t border-white/10 flex items-center justify-between">
            <span className="text-[10px] text-white/30">ORQUESTRA v{APP_VERSION}</span>
            <button
              onClick={() => { setOpen(false); onLogout() }}
              className="flex items-center gap-1.5 text-xs text-white/60 hover:text-white transition-colors px-2 py-1 rounded hover:bg-white/10"
            >
              <LogOut size={12} /> Sair
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

function ProfileRow({ icon, label, value }: { icon: React.ReactNode; label: string; value?: string | null }) {
  return (
    <div className="flex items-center gap-2 text-[11px]">
      <span className="text-white/40 flex-shrink-0">{icon}</span>
      <span className="text-white/40 flex-shrink-0 w-20">{label}</span>
      <span className="text-white/80 truncate">{value || '—'}</span>
    </div>
  )
}

// ── Header ─────────────────────────────────────────────────────────────────

export function Header() {
  const { logout, isAdmin } = useAuthStore()
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

        {/* Logo + brand + versão */}
        <a href="/" className="shrink-0 flex items-center gap-2.5" title="Voltar ao sistema">
          <img
            src="https://rseofspzecpjtqzcbaol.supabase.co/storage/v1/object/public/mundolc/Vertical_Branco.png"
            className="h-9 w-auto"
            alt="Caixa Vida e Previdência"
          />
          <span className="flex flex-col leading-tight">
            <span className="flex items-baseline gap-1.5">
              <span className="text-xs font-semibold tracking-widest uppercase opacity-95">ORQUESTRA</span>
              <span className="text-[9px] opacity-40 font-mono">v{APP_VERSION}</span>
            </span>
            <span className="text-[10px] opacity-60 tracking-wide">Gestão de Pipelines</span>
          </span>
        </a>

        {/* Nav */}
        <nav className="flex items-center gap-0.5 flex-1 overflow-x-auto ml-2">
          {NAV.map((n) => {
            if (n.adminOnly && !isAdmin()) return null
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

        {/* Direita: tema + avatar/perfil */}
        <div className="flex items-center gap-2 shrink-0">
          <button
            onClick={() => setTheme(toggleTheme())}
            className="text-white/70 hover:text-white transition-colors p-1 rounded hover:bg-white/10"
            title={theme === 'dark' ? 'Mudar para tema claro' : 'Mudar para tema escuro'}
            aria-label="Alternar tema"
          >
            {theme === 'dark' ? <Sun size={15} /> : <Moon size={15} />}
          </button>
          <ProfileDropdown onLogout={handleLogout} />
        </div>

      </div>
    </header>
  )
}
