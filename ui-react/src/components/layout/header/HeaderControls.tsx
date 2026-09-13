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
          type="button"
          aria-label="Abrir busca global"
          onClick={() => setCmdOpen(true)}
          className="hidden xl:flex h-9 min-w-9 items-center justify-center gap-1.5 text-white/80 hover:text-white text-[11px] border border-white/20 hover:border-white/40 rounded px-2 transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-white"
          title="Busca global (Ctrl+K)"
        >
          <span>⌘K</span>
        </button>
        <button
          type="button"
          onClick={() => setTheme(toggleTheme())}
          className="w-10 h-10 md:w-9 md:h-9 flex items-center justify-center text-white/80 hover:text-white transition-colors rounded hover:bg-white/10 focus-visible:outline focus-visible:outline-2 focus-visible:outline-white"
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
