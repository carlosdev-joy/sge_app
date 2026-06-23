import { useState, useRef, useEffect } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import { useAuthStore } from '../../store/auth'
import { apiFetch } from '../../lib/api'
import { useVisibleNav } from '../../lib/nav'
import { getTheme, toggleTheme } from '../../lib/theme'
import { useAppVersion } from '../../lib/version'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { LogOut, Sun, Moon, Shield, Mail, Hash, Building2, ChevronDown, X, Tag, Bell, Megaphone } from 'lucide-react'
import { CommandPalette } from '../ui/CommandPalette'
import { toast } from '../ui/Toast'
import { Button } from '../ui/Button'
import { renderMarkdown } from '../../lib/markdown'
import { Logo } from './Logo'

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

// ── Notifications bell ─────────────────────────────────────────────────────

interface Notif {
  id: number
  tipo: 'info' | 'success' | 'warning' | 'error'
  titulo: string
  mensagem: string | null
  link: string | null
  lida: boolean
  created_at: string | null
}

interface Comunicado {
  id: number
  tipo: 'info' | 'success' | 'warning' | 'error'
  titulo: string
  mensagem: string | null
  formato: 'simples' | 'banner'
  link: string | null
  created_at: string | null
  visto: boolean
  confirmado: boolean
}

interface FeedItem {
  key: string
  kind: 'notif' | 'comunicado'
  id: number
  tipo: 'info' | 'success' | 'warning' | 'error'
  titulo: string
  mensagem: string | null
  link: string | null
  lida: boolean
  created_at: string | null
}

const NOTIF_DOT: Record<string, string> = {
  success: 'bg-green-500', info: 'bg-blue-500', warning: 'bg-amber-500', error: 'bg-red-500',
}
const BANNER_BAR: Record<string, string> = {
  info: 'bg-blue-600', success: 'bg-green-600', warning: 'bg-amber-600', error: 'bg-red-600',
}

function fmtNotifTime(iso: string | null): string {
  if (!iso || iso.length < 16) return ''
  return `${iso.substring(8, 10)}/${iso.substring(5, 7)} ${iso.substring(11, 16)}`
}

function toastFor(tipo: string, txt: string) {
  if (tipo === 'error' || tipo === 'warning') toast.error(txt)
  else if (tipo === 'success') toast.success(txt)
  else toast.info(txt)
}

// Banner pop-up — comunicado complexo; reaparece até o usuário confirmar.
function ComunicadoBanner({ banner, onConfirm }: { banner: Comunicado; onConfirm: (id: number) => void }) {
  const navigate = useNavigate()
  return (
    <div className="fixed inset-0 z-[10000] flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />
      <div className="relative bg-panel border border-edge rounded-2xl shadow-2xl w-full max-w-lg flex flex-col max-h-[85vh] overflow-hidden">
        <div className={`px-5 py-3 flex items-center gap-2 text-white ${BANNER_BAR[banner.tipo] ?? BANNER_BAR.info}`}>
          <Megaphone size={18} className="shrink-0" />
          <h2 className="text-sm font-bold">{banner.titulo}</h2>
        </div>
        <div className="overflow-y-auto px-5 py-4">
          <div
            className="text-sm text-ink leading-relaxed break-words [&_a]:text-blue-400 [&_a]:underline [&_ul]:list-disc [&_ul]:pl-5 [&_strong]:font-semibold"
            dangerouslySetInnerHTML={{ __html: renderMarkdown(banner.mensagem ?? '') }}
          />
        </div>
        <div className="px-5 py-3 border-t border-edge flex items-center justify-between gap-2">
          {banner.link ? (
            <button
              onClick={() => { onConfirm(banner.id); navigate(banner.link!) }}
              className="text-xs text-blue-400 hover:text-blue-300 underline underline-offset-2"
            >
              Abrir link
            </button>
          ) : <span />}
          <Button size="sm" onClick={() => onConfirm(banner.id)}>Entendi</Button>
        </div>
      </div>
    </div>
  )
}

function NotificationsBell() {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const seenNotifRef = useRef<number | null>(null)   // baseline notificações (1ª carga)
  const seenComRef   = useRef<number | null>(null)   // baseline comunicados (1ª carga)
  const bannerVistoRef = useRef<Set<number>>(new Set())

  const { data } = useQuery<{ data: Notif[]; unread: number }>({
    queryKey: ['notificacoes'],
    queryFn: () => apiFetch('/notificacoes?limit=30'),
    refetchInterval: 30_000,
    refetchOnWindowFocus: true,
  })
  const { data: comData } = useQuery<{ data: Comunicado[]; banners: Comunicado[]; unread: number }>({
    queryKey: ['comunicados-inbox'],
    queryFn: () => apiFetch('/comunicados/inbox'),
    refetchInterval: 30_000,
    refetchOnWindowFocus: true,
  })

  const notifs = data?.data ?? []
  const coms   = comData?.data ?? []
  const banners = comData?.banners ?? []

  const feed: FeedItem[] = [
    ...notifs.map(n => ({ key: 'n' + n.id, kind: 'notif' as const, id: n.id, tipo: n.tipo,
      titulo: n.titulo, mensagem: n.mensagem, link: n.link, lida: n.lida, created_at: n.created_at })),
    ...coms.map(c => ({ key: 'c' + c.id, kind: 'comunicado' as const, id: c.id, tipo: c.tipo,
      titulo: c.titulo, mensagem: c.mensagem, link: c.link, lida: c.confirmado, created_at: c.created_at })),
  ].sort((a, b) => (b.created_at ?? '').localeCompare(a.created_at ?? ''))

  const unread = (data?.unread ?? 0) + (comData?.unread ?? 0)

  const markVisto = useMutation({
    mutationFn: (ids: number[]) => apiFetch('/comunicados/visto', { method: 'POST', body: JSON.stringify({ ids }) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['comunicados-inbox'] }),
  })
  const confirmar = useMutation({
    mutationFn: (id: number) => apiFetch(`/comunicados/${id}/confirmar`, { method: 'POST' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['comunicados-inbox'] }),
  })
  const markRead = useMutation({
    mutationFn: () => apiFetch('/notificacoes/read', { method: 'POST', body: JSON.stringify({ all: true }) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['notificacoes'] }),
  })

  // Toast para notificações novas (sistema) — baseline na 1ª carga.
  useEffect(() => {
    if (!data) return
    const maxId = notifs.reduce((m, n) => Math.max(m, n.id), 0)
    if (seenNotifRef.current === null) { seenNotifRef.current = maxId; return }
    const novas = notifs.filter(n => n.id > (seenNotifRef.current ?? 0))
    if (novas.length) {
      novas.slice(0, 3).reverse().forEach(n => toastFor(n.tipo, n.titulo + (n.mensagem ? ` — ${n.mensagem}` : '')))
      seenNotifRef.current = maxId
    }
  }, [data])  // eslint-disable-line react-hooks/exhaustive-deps

  // Toast para comunicados novos (simples). Banners são exibidos como pop-up.
  useEffect(() => {
    if (!comData) return
    const maxId = coms.reduce((m, c) => Math.max(m, c.id), 0)
    if (seenComRef.current === null) { seenComRef.current = maxId; return }
    const novas = coms.filter(c => c.id > (seenComRef.current ?? 0))
    if (novas.length) {
      const simples = novas.filter(c => c.formato !== 'banner')
      simples.slice(0, 3).reverse().forEach(c => toastFor(c.tipo, `📢 ${c.titulo}`))
      const ids = simples.map(c => c.id)
      if (ids.length) markVisto.mutate(ids)
      seenComRef.current = maxId
    }
  }, [comData])  // eslint-disable-line react-hooks/exhaustive-deps

  // Banner exibido conta como "visto" (uma vez por id).
  useEffect(() => {
    const b = banners[0]
    if (b && !bannerVistoRef.current.has(b.id)) {
      bannerVistoRef.current.add(b.id)
      markVisto.mutate([b.id])
    }
  }, [banners])  // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    function handler(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  function toggleOpen() {
    const next = !open
    setOpen(next)
    if (next) {
      const unseen = coms.filter(c => !c.visto).map(c => c.id)
      if (unseen.length) markVisto.mutate(unseen)
    }
  }

  function onClickItem(it: FeedItem) {
    if (it.kind === 'comunicado' && !it.lida) confirmar.mutate(it.id)
    if (it.link) { setOpen(false); navigate(it.link) }
  }

  return (
    <>
      <div ref={ref} className="relative">
        <button
          onClick={toggleOpen}
          className="relative text-white/70 hover:text-white transition-colors p-1 rounded hover:bg-white/10"
          title="Notificações" aria-label="Notificações" aria-expanded={open}
        >
          <Bell size={16} />
          {unread > 0 && (
            <span className="absolute -top-0.5 -right-0.5 min-w-[15px] h-[15px] px-1 rounded-full bg-red-500 text-white text-[9px] font-bold flex items-center justify-center">
              {unread > 9 ? '9+' : unread}
            </span>
          )}
        </button>

        {open && (
          <div className="absolute right-0 top-[calc(100%+6px)] w-80 rounded-xl shadow-2xl border border-edge bg-panel overflow-hidden z-50">
            <div className="flex items-center justify-between px-3 py-2 border-b border-edge">
              <span className="text-xs font-semibold text-ink">Notificações</span>
              {(data?.unread ?? 0) > 0 && (
                <button onClick={() => markRead.mutate()} className="text-[10px] text-blue-400 hover:text-blue-300">
                  Marcar todas como lidas
                </button>
              )}
            </div>
            <div className="max-h-[60vh] overflow-y-auto">
              {feed.length === 0 && (
                <div className="px-3 py-8 text-center text-xs text-dim">Nenhuma notificação.</div>
              )}
              {feed.map(it => (
                <div
                  key={it.key}
                  onClick={() => onClickItem(it)}
                  className={`flex gap-2 px-3 py-2 border-b border-edge/40 last:border-0 transition-colors
                    ${it.lida ? 'opacity-60' : 'bg-blue-500/5'} ${(it.link || it.kind === 'comunicado') ? 'cursor-pointer hover:bg-edge/30' : ''}`}
                >
                  <span className={`mt-1 w-2 h-2 rounded-full shrink-0 ${NOTIF_DOT[it.tipo] ?? 'bg-blue-500'}`} />
                  <div className="min-w-0 flex-1">
                    <div className="text-xs font-medium text-ink flex items-center gap-1">
                      {it.kind === 'comunicado' && <Megaphone size={11} className="text-dim shrink-0" />}
                      <span className="truncate">{it.titulo}</span>
                    </div>
                    {it.mensagem && <div className="text-[11px] text-dim mt-0.5 break-words line-clamp-3">{it.mensagem}</div>}
                    <div className="text-[10px] text-dim/60 mt-0.5">{fmtNotifTime(it.created_at)}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {banners.length > 0 && (
        <ComunicadoBanner banner={banners[0]} onConfirm={id => confirmar.mutate(id)} />
      )}
    </>
  )
}

// ── Header ─────────────────────────────────────────────────────────────────

export function Header() {
  const { logout } = useAuthStore()
  const appVersion = useAppVersion()
  const [theme, setTheme] = useState(getTheme())
  const [cmdOpen, setCmdOpen] = useState(false)
  const { visible } = useVisibleNav()

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
        <a href="/" className="shrink-0 flex items-center gap-3" title="Voltar ao sistema">
          <img
            src="/branding/logo-cvp.png"
            className="h-9 w-auto"
            alt="Caixa Vida e Previdência"
            onError={(e) => {
              const img = e.currentTarget
              if (!img.dataset.fallback) { img.dataset.fallback = '1'; img.src = '/images/logo-cvp.svg' }
            }}
          />
          <Logo variant="white" iconSize={28}>
            <span className="text-[9px] text-white/40 font-mono">v{appVersion}</span>
          </Logo>
        </a>

        {/* Nav */}
        <nav className="flex items-center gap-0.5 flex-1 overflow-x-auto ml-2">
          {visible.map((n) => {
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
          <NotificationsBell />
          <ProfileDropdown onLogout={handleLogout} />
        </div>

      </div>

      <CommandPalette open={cmdOpen} onClose={() => setCmdOpen(false)} />
    </header>
  )
}
