import { useState, useRef, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Bell, Megaphone } from 'lucide-react'
import { apiFetch } from '../../../lib/api'
import { toast } from '../../ui/Toast'
import { Button } from '../../ui/Button'
import { renderMarkdown } from '../../../lib/markdown'

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

export function NotificationsBell() {
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
