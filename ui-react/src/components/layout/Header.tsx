import { useState, useRef, useEffect } from 'react'
import { NavLink } from 'react-router-dom'
import { useAuthStore } from '../../store/auth'
import { apiFetch } from '../../lib/api'
import { NAV } from '../../lib/nav'
import { getTheme, toggleTheme } from '../../lib/theme'
import { useAppVersion } from '../../lib/version'
import { useQuery } from '@tanstack/react-query'
import { LogOut, Sun, Moon, Shield, Mail, Hash, Building2, ChevronDown, X, Tag } from 'lucide-react'
import { CommandPalette } from '../ui/CommandPalette'

// ── helpers ────────────────────────────────────────────────────────────────

function initials(primeiro?: string | null, ultimo?: string | null, matricula?: string): string {
  if (primeiro && ultimo) return (primeiro[0] + ultimo[0]).toUpperCase()
  if (primeiro) return primeiro.substring(0, 2).toUpperCase()
  return (matricula ?? '??').substring(0, 2).toUpperCase()
}

function fmtDate(iso: string | null | undefined) {
  if (!iso) return ''
  return iso.substring(0, 10).split('-').reverse().join('/')
}

// ── Changelog Modal ────────────────────────────────────────────────────────

interface VersaoEntry {
  id: number
  versao: string
  titulo: string
  descricao_md: string | null
  criado_em: string | null
  criado_por: string | null
}

function ChangelogModal({ onClose }: { onClose: () => void }) {
  const { data, isLoading } = useQuery<{ total: number; data: VersaoEntry[] }>({
    queryKey: ['versao'],
    queryFn: () => apiFetch('/versao'),
    staleTime: 300_000,
  })

  // close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [onClose])

  return (
    <div className="fixed inset-0 z-[9999] flex items-center justify-center p-4" onClick={e => { if (e.target === e.currentTarget) onClose() }}>
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" />
      <div className="relative bg-panel border border-edge rounded-2xl shadow-2xl w-full max-w-xl flex flex-col max-h-[80vh]">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-edge shrink-0">
          <div>
            <h2 className="text-sm font-bold text-ink">Histórico de versões</h2>
            <p className="text-[11px] text-dim mt-0.5">ORQUESTRA — Gestão de Pipelines</p>
          </div>
          <button onClick={onClose} className="text-dim hover:text-ink p-1 rounded hover:bg-edge/50 transition-colors">
            <X size={16} />
          </button>
        </div>

        {/* Content */}
        <div className="overflow-y-auto flex-1 px-5 py-4">
          {isLoading && (
            <div className="py-12 text-center text-dim text-sm">Carregando histórico…</div>
          )}
          {!isLoading && (!data?.data || data.data.length === 0) && (
            <div className="py-12 text-center text-dim text-sm">Nenhum registro de versão cadastrado.</div>
          )}
          {!isLoading && data?.data && data.data.length > 0 && (
            <div className="flex flex-col gap-5">
              {data.data.map((v, i) => (
                <div key={v.id} className="relative pl-6">
                  {/* Timeline line */}
                  {i < data.data.length - 1 && (
                    <div className="absolute left-[7px] top-5 bottom-[-1.25rem] w-px bg-edge/50" />
                  )}
                  {/* Dot */}
                  <div className={`absolute left-0 top-1 w-3.5 h-3.5 rounded-full border-2 flex items-center justify-center ${i === 0 ? 'bg-blue-500 border-blue-400' : 'bg-canvas border-edge'}`} />

                  <div className="flex items-start justify-between gap-2 mb-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold border ${i === 0 ? 'bg-blue-500/15 text-blue-400 border-blue-500/40' : 'bg-edge text-dim border-edge'}`}>
                        <Tag size={9} /> v{v.versao}
                      </span>
                      <span className="text-sm font-semibold text-ink">{v.titulo}</span>
                    </div>
                    <span className="text-[10px] text-dim whitespace-nowrap flex-shrink-0">{fmtDate(v.criado_em)}</span>
                  </div>

                  {v.descricao_md && (
                    <div className="text-xs text-dim leading-relaxed whitespace-pre-line mt-1 pl-0.5">
                      {v.descricao_md}
                    </div>
                  )}

                  {v.criado_por && (
                    <div className="text-[10px] text-dim/50 mt-1">por {v.criado_por}</div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-5 py-3 border-t border-edge shrink-0 flex justify-end">
          <button onClick={onClose} className="text-xs text-dim hover:text-ink px-3 py-1.5 rounded border border-edge hover:bg-edge/50 transition-colors">
            Fechar
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Profile row helper ─────────────────────────────────────────────────────

function ProfileRow({ icon, label, value }: { icon: React.ReactNode; label: string; value?: string | null }) {
  return (
    <div className="flex items-center gap-2 text-[11px]">
      <span className="text-white/40 flex-shrink-0">{icon}</span>
      <span className="text-white/40 flex-shrink-0 w-20">{label}</span>
      <span className="text-white/80 truncate">{value || '—'}</span>
    </div>
  )
}

// ── Profile dropdown ───────────────────────────────────────────────────────

function ProfileDropdown({ onLogout }: { onLogout: () => void }) {
  const { user } = useAuthStore()
  const appVersion = useAppVersion()
  const [open, setOpen]           = useState(false)
  const [showChangelog, setShowChangelog] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

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
      <div ref={ref} className="relative">
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

        {open && (
          <div className="absolute right-0 top-[calc(100%+6px)] w-72 rounded-xl shadow-2xl border border-white/10 overflow-hidden z-50"
            style={{ background: 'linear-gradient(160deg, #1A5FA8 0%, #0D3D6B 100%)' }}>

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
                onClick={() => { setOpen(false); setShowChangelog(true) }}
                className="text-[10px] text-white/40 hover:text-white/70 transition-colors underline underline-offset-2"
                title="Ver histórico de versões"
              >
                ORQUESTRA v{appVersion}
              </button>
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

      {showChangelog && <ChangelogModal onClose={() => setShowChangelog(false)} />}
    </>
  )
}

// ── Header ─────────────────────────────────────────────────────────────────

export function Header() {
  const { logout, user } = useAuthStore()
  const appVersion = useAppVersion()
  const [theme, setTheme] = useState(getTheme())
  const [cmdOpen, setCmdOpen] = useState(false)
  const perms = user?.permissoes ?? []
  const canSee = (n: typeof NAV[number]) => !n.perm || perms.length === 0 || perms.includes(n.perm)

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
              <span className="text-[9px] opacity-40 font-mono">v{appVersion}</span>
            </span>
            <span className="text-[10px] opacity-60 tracking-wide">Gestão de Pipelines</span>
          </span>
        </a>

        {/* Nav */}
        <nav className="flex items-center gap-0.5 flex-1 overflow-x-auto ml-2">
          {NAV.map((n) => {
            if (!canSee(n)) return null
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

        {/* Direita: ⌘K + tema + avatar */}
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
          <ProfileDropdown onLogout={handleLogout} />
        </div>

      </div>

      <CommandPalette open={cmdOpen} onClose={() => setCmdOpen(false)} />
    </header>
  )
}
