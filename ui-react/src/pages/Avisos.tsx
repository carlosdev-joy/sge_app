import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Bell, Megaphone, CheckCheck } from 'lucide-react'
import { apiFetch } from '../lib/api'
import { Spinner } from '../components/ui/Spinner'

// Central de avisos do shell v2 — versão em página cheia do sininho do header
// (NotificationsBell): funde notificações do sistema + comunicados da equipe num
// feed único, ordenado por data. Reusa os mesmos endpoints e ações de leitura.

interface Notif {
  id: number; tipo: 'info' | 'success' | 'warning' | 'error'
  titulo: string; mensagem: string | null; link: string | null
  lida: boolean; created_at: string | null
}
interface Comunicado {
  id: number; tipo: 'info' | 'success' | 'warning' | 'error'
  titulo: string; mensagem: string | null; formato: 'simples' | 'banner'
  link: string | null; created_at: string | null; visto: boolean; confirmado: boolean
}
interface FeedItem {
  key: string; kind: 'notif' | 'comunicado'; id: number; tipo: string
  titulo: string; mensagem: string | null; link: string | null
  lida: boolean; created_at: string | null
}

// Pontos de status — cor sólida, legível nos dois temas (igual ao sininho).
const NOTIF_DOT: Record<string, string> = {
  success: 'bg-green-500', info: 'bg-blue-500', warning: 'bg-amber-500', error: 'bg-red-500',
}

function fmtTime(iso: string | null): string {
  if (!iso || iso.length < 16) return ''
  return `${iso.substring(8, 10)}/${iso.substring(5, 7)}/${iso.substring(0, 4)} ${iso.substring(11, 16)}`
}

export default function Avisos() {
  const qc = useQueryClient()
  const navigate = useNavigate()

  const { data, isLoading } = useQuery<{ data: Notif[]; unread: number }>({
    queryKey: ['notificacoes', 'page'],
    queryFn: () => apiFetch('/notificacoes?limit=100'),
    refetchInterval: 30_000,
    refetchOnWindowFocus: true,
  })
  const { data: comData, isLoading: comLoading } = useQuery<{ data: Comunicado[]; banners: Comunicado[]; unread: number }>({
    queryKey: ['comunicados-inbox'],
    queryFn: () => apiFetch('/comunicados/inbox'),
    refetchInterval: 30_000,
    refetchOnWindowFocus: true,
  })

  const notifs = data?.data ?? []
  const coms = comData?.data ?? []

  const feed: FeedItem[] = [
    ...notifs.map((n) => ({ key: 'n' + n.id, kind: 'notif' as const, id: n.id, tipo: n.tipo,
      titulo: n.titulo, mensagem: n.mensagem, link: n.link, lida: n.lida, created_at: n.created_at })),
    ...coms.map((c) => ({ key: 'c' + c.id, kind: 'comunicado' as const, id: c.id, tipo: c.tipo,
      titulo: c.titulo, mensagem: c.mensagem, link: c.link, lida: c.confirmado, created_at: c.created_at })),
  ].sort((a, b) => (b.created_at ?? '').localeCompare(a.created_at ?? ''))

  const notifUnread = data?.unread ?? 0

  const markRead = useMutation({
    mutationFn: () => apiFetch('/notificacoes/read', { method: 'POST', body: JSON.stringify({ all: true }) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['notificacoes'] }),
  })
  const confirmar = useMutation({
    mutationFn: (id: number) => apiFetch(`/comunicados/${id}/confirmar`, { method: 'POST' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['comunicados-inbox'] }),
  })
  const markVisto = useMutation({
    mutationFn: (ids: number[]) => apiFetch('/comunicados/visto', { method: 'POST', body: JSON.stringify({ ids }) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['comunicados-inbox'] }),
  })

  // Abrir a página conta como "visto" para os comunicados (limpa o badge), igual
  // ao abrir o sininho. "Confirmado" continua sendo ação explícita ao clicar.
  useEffect(() => {
    const unseen = coms.filter((c) => !c.visto).map((c) => c.id)
    if (unseen.length) markVisto.mutate(unseen)
  }, [comData])  // eslint-disable-line react-hooks/exhaustive-deps

  function onClickItem(it: FeedItem) {
    if (it.kind === 'comunicado' && !it.lida) confirmar.mutate(it.id)
    if (it.link) navigate(it.link)
  }

  const loading = isLoading || comLoading

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold text-ink flex items-center gap-2">
            <Bell size={20} className="text-[#1A5FA8]" /> Avisos
          </h1>
          <p className="text-sm text-dim mt-1">Notificações do sistema e comunicados da equipe.</p>
        </div>
        {notifUnread > 0 && (
          <button
            onClick={() => markRead.mutate()}
            className="shrink-0 inline-flex items-center gap-1.5 text-xs text-blue-700 dark:text-blue-400 hover:underline"
          >
            <CheckCheck size={14} /> Marcar todas como lidas
          </button>
        )}
      </div>

      {loading ? (
        <div className="flex justify-center h-40 items-center"><Spinner size={36} /></div>
      ) : feed.length === 0 ? (
        <div className="bg-panel border border-edge rounded-lg">
          <p className="text-sm text-dim text-center py-10">Nenhum aviso no momento.</p>
        </div>
      ) : (
        <div className="bg-panel border border-edge rounded-lg overflow-hidden">
          <ul>
            {feed.map((it) => {
              const clickable = it.link || (it.kind === 'comunicado' && !it.lida)
              return (
                <li
                  key={it.key}
                  onClick={() => onClickItem(it)}
                  className={`flex gap-3 px-4 py-3 border-b border-edge/60 last:border-0 transition-colors
                    ${it.lida ? 'opacity-70' : 'bg-blue-500/5'} ${clickable ? 'cursor-pointer hover:bg-edge/30' : ''}`}
                >
                  <span className={`mt-1.5 w-2 h-2 rounded-full shrink-0 ${NOTIF_DOT[it.tipo] ?? 'bg-blue-500'}`} />
                  <div className="min-w-0 flex-1">
                    <div className="text-sm font-medium text-ink flex items-center gap-1.5">
                      {it.kind === 'comunicado' && <Megaphone size={13} className="text-dim shrink-0" />}
                      <span className="break-words">{it.titulo}</span>
                      {!it.lida && <span className="ml-1 shrink-0 w-1.5 h-1.5 rounded-full bg-blue-500" title="Não lido" />}
                    </div>
                    {it.mensagem && (
                      <div className="text-[13px] text-dim mt-1 break-words whitespace-pre-wrap">{it.mensagem}</div>
                    )}
                    <div className="text-[11px] text-dim/70 mt-1">{fmtTime(it.created_at)}</div>
                  </div>
                </li>
              )
            })}
          </ul>
        </div>
      )}
    </div>
  )
}
