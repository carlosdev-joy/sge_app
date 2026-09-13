import { useState, useRef, useEffect, useId } from 'react'
import { useAuthStore } from '../../../store/auth'
import { useAppVersion } from '../../../lib/version'
import { LogOut, Shield, Mail, Hash, Building2, ChevronDown } from 'lucide-react'
import { ChangelogModal } from './ChangelogModal'

function initials(primeiro?: string | null, ultimo?: string | null, matricula?: string): string {
  if (primeiro && ultimo) return (primeiro[0] + ultimo[0]).toUpperCase()
  if (primeiro) return primeiro.substring(0, 2).toUpperCase()
  return (matricula ?? '??').substring(0, 2).toUpperCase()
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

export function ProfileDropdown({ onLogout }: { onLogout: () => void }) {
  const { user } = useAuthStore()
  const appVersion = useAppVersion()
  const [open, setOpen]           = useState(false)
  const [showChangelog, setShowChangelog] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const panelId = useId()

  useEffect(() => {
    function handler(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const ini        = initials(user?.primeiro_nome, user?.ultimo_nome, user?.matricula)
  const nomeCompleto = [user?.primeiro_nome, user?.ultimo_nome].filter(Boolean).join(' ') || user?.matricula || '—'

  const perfilLabel: Record<string, string> = {
    admin: 'Administrador', editar: 'Editor', executar: 'Operador', consulta: 'Consulta',
  }
  const permColors: Record<string, string> = {
    admin:    'bg-purple-500/20 text-purple-200 border-purple-500/40',
    editar:   'bg-blue-500/20   text-blue-200   border-blue-500/40',
    executar: 'bg-green-500/20  text-green-200  border-green-500/40',
    consulta: 'bg-slate-500/20  text-slate-300  border-slate-500/40',
  }
  const perfilColor = permColors[user?.perfil ?? 'consulta'] ?? permColors.consulta

  return (
    <>
      <div ref={ref} className="relative" onKeyDown={e => {
        if (open && e.key === 'Escape') {
          e.preventDefault()
          e.stopPropagation()
          setOpen(false)
          triggerRef.current?.focus()
        }
      }}>
        <button
          ref={triggerRef}
          type="button"
          aria-haspopup="dialog"
          aria-controls={open ? panelId : undefined}
          aria-label={`Abrir perfil de ${nomeCompleto}`}
          onClick={() => setOpen(v => !v)}
          className="flex items-center justify-center gap-1.5 min-w-10 h-10 md:min-w-9 md:h-9 rounded-lg px-1 hover:bg-white/10 transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-white"
          title={nomeCompleto}
          aria-expanded={open}
        >
          <span className="w-7 h-7 rounded-full bg-white/20 border border-white/30 flex items-center justify-center text-[11px] font-bold text-white select-none">
            {ini}
          </span>
          <span className="text-xs text-white/80 hidden md:block max-w-[96px] truncate">{user?.primeiro_nome ?? user?.matricula}</span>
          <ChevronDown size={11} className={`text-white/50 transition-transform ${open ? 'rotate-180' : ''}`} />
        </button>

        {open && (
          <div id={panelId} role="dialog" aria-label="Perfil do usuário" className="fixed inset-x-2 top-[58px] md:absolute md:inset-x-auto md:right-0 md:top-[calc(100%+6px)] md:w-72 max-h-[calc(100svh-66px)] rounded-xl shadow-2xl border border-white/10 overflow-y-auto z-50"
            style={{ background: 'rgb(var(--brand-navy))' }}>

            {/* Avatar + nome */}
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
              <ProfileRow icon={<Hash size={11} />}     label="Matrícula" value={user?.matricula} />
              <ProfileRow icon={<Mail size={11} />}     label="E-mail"    value={user?.email} />
              <ProfileRow icon={<Shield size={11} />}   label="Perfil"    value={perfilLabel[user?.perfil ?? ''] ?? user?.perfil} />
              {user?.area && (
                <ProfileRow icon={<Building2 size={11} />} label="Área" value={user.area} />
              )}
            </div>

            {/* Footer: versão clicável + sair */}
            <div className="px-4 py-2.5 border-t border-white/10 flex items-center justify-between">
              <button
                type="button"
                onClick={() => {
                  // O item de versão desmonta ao fechar o dropdown. O overlay
                  // deve devolver foco ao trigger estável quando for fechado.
                  triggerRef.current?.focus()
                  setOpen(false)
                  setShowChangelog(true)
                }}
                className="text-[10px] text-white/40 hover:text-white/70 transition-colors underline underline-offset-2"
                title="Ver histórico de versões"
              >
                ORQ v{appVersion}
              </button>
              <button
                type="button"
                onClick={() => { setOpen(false); onLogout() }}
                className="flex items-center gap-1.5 text-xs text-white/60 hover:text-white transition-colors px-2 py-1 rounded hover:bg-white/10"
              >
                <LogOut size={12} /> Sair
              </button>
            </div>
          </div>
        )}
      </div>

      {showChangelog && <ChangelogModal onClose={() => setShowChangelog(false)} />}
    </>
  )
}
