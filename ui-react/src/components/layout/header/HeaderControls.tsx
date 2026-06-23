import { useState, useEffect } from 'react'
import { Sun, Moon } from 'lucide-react'
import { useAuthStore } from '../../../store/auth'
import { apiFetch } from '../../../lib/api'
import { getTheme, toggleTheme } from '../../../lib/theme'
import { CommandPalette } from '../../ui/CommandPalette'
import { NotificationsBell } from './NotificationsBell'
import { ProfileDropdown } from './ProfileDropdown'

// Controles globais do header (sobre superfície gradiente, white-on-blue):
// busca ⌘K, troca de tema, sino de notificações e perfil. Bloco único reusado
// pelo header clássico e pelo header fino do shell v2.
export function HeaderControls() {
  const { logout } = useAuthStore()
  const [theme, setTheme] = useState(getTheme())
  const [cmdOpen, setCmdOpen] = useState(false)

  // Global Ctrl+K / Cmd+K listener
  useEffect(() => {
    function handler(e: KeyboardEvent) {
      if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault()
        setCmdOpen((v) => !v)
      }
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [])

  const handleLogout = async () => {
    try { await apiFetch('/auth/logout', { method: 'POST' }) } catch {}
    logout()
    window.location.href = '/login'
  }

  return (
    <>
      <div className="flex items-center gap-2 shrink-0">
        <button
          onClick={() => setCmdOpen(true)}
          className="hidden sm:flex items-center gap-1.5 text-white/60 hover:text-white text-[11px] border border-white/20 hover:border-white/40 rounded px-2 py-0.5 transition-colors"
          title="Busca global (Ctrl+K)"
        >
          <span>⌘K</span>
        </button>
        <button
          onClick={() => setTheme(toggleTheme())}
          className="text-white/70 hover:text-white transition-colors p-1 rounded hover:bg-white/10"
          title={theme === 'dark' ? 'Mudar para tema claro' : 'Mudar para tema escuro'}
          aria-label="Alternar tema"
        >
          {theme === 'dark' ? <Sun size={15} /> : <Moon size={15} />}
        </button>
        <NotificationsBell />
        <ProfileDropdown onLogout={handleLogout} />
      </div>

      <CommandPalette open={cmdOpen} onClose={() => setCmdOpen(false)} />
    </>
  )
}
