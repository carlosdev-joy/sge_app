import { useState, useRef, type ReactNode } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { apiFetch } from '../../../lib/api'
import { Button } from '../../ui/Button'
import { Input, Select } from '../../ui/Input'
import { Badge } from '../../ui/Badge'
import { Modal } from '../../ui/Modal'
import { PageSpinner } from '../../ui/Spinner'
import { toast } from '../../ui/Toast'
import { queryClient } from '../../../lib/queryClient'
import { renderMarkdown } from '../../../lib/markdown'
import { adminPost } from '../comum'
import { Eye, Megaphone, Bold, Italic, Code, List } from 'lucide-react'

// ── Comunicados ──────────────────────────────────────────────────
interface ComunicadoRow {
  id: number; titulo: string; tipo: string; formato: string
  publico_tipo: string; publico_desc: string; criado_por: string
  criado_em: string; ativo: boolean; expira_em: string | null
  total: number; vistos: number; confirmados: number
}
interface DestinatarioRow {
  matricula: string; nome: string; perfil: string | null
  entregue_em: string | null; visto_em: string | null; confirmado_em: string | null
}

const TIPO_OPTS = [
  { v: 'info', label: 'Informação (azul)' },
  { v: 'success', label: 'Sucesso (verde)' },
  { v: 'warning', label: 'Aviso (âmbar)' },
  { v: 'error', label: 'Crítico (vermelho)' },
]

const pct = (n: number, d: number) => (d > 0 ? Math.round((n / d) * 100) : 0)

const COM_BAR: Record<string, string> = { info: 'bg-blue-600', success: 'bg-green-600', warning: 'bg-amber-600', error: 'bg-red-600' }
const COM_DOT: Record<string, string> = { info: 'bg-blue-500', success: 'bg-green-500', warning: 'bg-amber-500', error: 'bg-red-500' }

// Botão da barra de formatação Markdown.
function MdBtn({ onClick, title, children }: { onClick: () => void; title: string; children: ReactNode }) {
  return (
    <button type="button" onClick={onClick} title={title}
      className="px-1.5 py-1 rounded text-dim hover:text-ink hover:bg-edge/60 transition-colors flex items-center justify-center min-w-[26px]">
      {children}
    </button>
  )
}

// Pré-visualização ao vivo — espelha como o usuário verá (banner ou sininho+toast).
function ComunicadoPreview({ tipo, titulo, mensagem, formato }: { tipo: string; titulo: string; mensagem: string; formato: string }) {
  const tituloView = titulo.trim() || 'Título do comunicado'
  const html = renderMarkdown(mensagem.trim() || 'A prévia da mensagem aparece aqui conforme você escreve.')
  const bar = COM_BAR[tipo] ?? COM_BAR.info
  const dot = COM_DOT[tipo] ?? COM_DOT.info
  const mdClass = 'text-sm text-ink break-words [&_a]:text-blue-400 [&_ul]:list-disc [&_li]:list-disc [&_li]:ml-4 [&_strong]:font-semibold'

  if (formato === 'banner') {
    return (
      <div className="rounded-xl border border-edge overflow-hidden shadow-sm">
        <div className={`px-3 py-2 flex items-center gap-2 text-white ${bar}`}>
          <Megaphone size={14} className="shrink-0" />
          <span className="text-xs font-bold truncate">{tituloView}</span>
        </div>
        <div className="p-3 bg-panel">
          <div className={mdClass} dangerouslySetInnerHTML={{ __html: html }} />
          <div className="mt-3 flex justify-end">
            <span className="text-[10px] px-2.5 py-1 rounded bg-[#1A5FA8] text-white font-medium">Entendi</span>
          </div>
        </div>
      </div>
    )
  }
  return (
    <div className="flex flex-col gap-2">
      <div className="rounded-lg border border-edge bg-panel p-2 flex gap-2">
        <span className={`mt-1 w-2 h-2 rounded-full shrink-0 ${dot}`} />
        <div className="min-w-0">
          <div className="text-xs font-medium text-ink flex items-center gap-1">
            <Megaphone size={11} className="text-dim shrink-0" />{tituloView}
          </div>
          <div className={`mt-0.5 ${mdClass} [&_*]:text-[11px] [&_*]:text-dim`} dangerouslySetInnerHTML={{ __html: html }} />
        </div>
      </div>
      <div className={`text-[11px] text-white rounded px-2 py-1 inline-flex items-center gap-1 w-fit max-w-full ${bar}`}>
        <span className="truncate">📢 {tituloView}</span>
      </div>
    </div>
  )
}

function ComunicadoDetail({ id, onClose }: { id: number; onClose: () => void }) {
  const { data, isLoading } = useQuery<{ comunicado: ComunicadoRow & { mensagem: string }; destinatarios: DestinatarioRow[] }>({
    queryKey: ['comunicado-detail', id],
    queryFn: () => apiFetch(`/admin/comunicados/${id}`),
  })
  const dest = data?.destinatarios ?? []
  return (
    <Modal open onClose={onClose} title="Auditoria do comunicado" size="lg">
      {isLoading && <PageSpinner />}
      {data && (
        <div className="flex flex-col gap-4">
          <div>
            <div className="text-sm font-semibold text-ink">{data.comunicado.titulo}</div>
            <div className="text-xs text-dim mt-1 whitespace-pre-line break-words">{data.comunicado.mensagem}</div>
            <div className="text-[11px] text-dim/70 mt-2">{data.comunicado.publico_desc} · por {data.comunicado.criado_por} · {data.comunicado.criado_em}</div>
          </div>
          <div className="overflow-auto max-h-[50vh] border border-edge rounded-lg">
            <table className="w-full text-xs">
              <thead className="bg-edge/30 sticky top-0">
                <tr className="text-left text-dim">
                  <th className="px-3 py-2 font-medium">Usuário</th>
                  <th className="px-3 py-2 font-medium">Perfil</th>
                  <th className="px-3 py-2 font-medium">Entregue</th>
                  <th className="px-3 py-2 font-medium">Visto</th>
                  <th className="px-3 py-2 font-medium">Confirmado</th>
                </tr>
              </thead>
              <tbody>
                {dest.map(d => (
                  <tr key={d.matricula} className="border-t border-edge/40">
                    <td className="px-3 py-1.5"><span className="text-ink">{d.nome}</span> <span className="text-dim/60">{d.matricula}</span></td>
                    <td className="px-3 py-1.5 text-dim">{d.perfil ?? '—'}</td>
                    <td className="px-3 py-1.5 text-dim">{d.entregue_em ?? '—'}</td>
                    <td className="px-3 py-1.5">{d.visto_em ? <span className="text-blue-400">{d.visto_em}</span> : <span className="text-dim/40">—</span>}</td>
                    <td className="px-3 py-1.5">{d.confirmado_em ? <span className="text-green-500">{d.confirmado_em}</span> : <span className="text-dim/40">—</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </Modal>
  )
}

const EMPTY_COM = {
  titulo: '', mensagem: '', tipo: 'info', formato: 'simples', link: '',
  publico_tipo: 'todos', perfis: [] as string[], matriculas: [] as string[], expira_em: '',
}

export function ComunicadosTab() {
  const [form, setForm] = useState(EMPTY_COM)
  const [userFilter, setUserFilter] = useState('')
  const [detailId, setDetailId] = useState<number | null>(null)
  const msgRef = useRef<HTMLTextAreaElement>(null)

  const { data: listData, isLoading } = useQuery<{ data: ComunicadoRow[] }>({
    queryKey: ['comunicados-admin'],
    queryFn: () => apiFetch('/admin/comunicados'),
  })
  const { data: perfilData } = useQuery<{ perfis: { perfil_nome: string }[] }>({
    queryKey: ['perfil_list_com'],
    queryFn: () => adminPost('perfil_list'),
  })
  const { data: userData } = useQuery<{ usuarios: { matricula: string; primeiro_nome: string | null; ultimo_nome: string | null; perfil: string; ativo: boolean }[] }>({
    queryKey: ['user_list_com'],
    queryFn: () => adminPost('user_list'),
    enabled: form.publico_tipo === 'usuarios',
  })

  const perfis = perfilData?.perfis ?? []
  const usuarios = (userData?.usuarios ?? []).filter(u => u.ativo)
  const filteredUsers = usuarios.filter(u =>
    !userFilter || `${u.matricula} ${u.primeiro_nome ?? ''} ${u.ultimo_nome ?? ''}`.toLowerCase().includes(userFilter.toLowerCase()))

  const create = useMutation({
    mutationFn: () => apiFetch<{ total_destinatarios: number }>('/admin/comunicados', { method: 'POST', body: JSON.stringify(form) }),
    onSuccess: (r) => {
      toast.success(`Comunicado enviado a ${r.total_destinatarios} usuário(s).`)
      setForm(EMPTY_COM); setUserFilter('')
      queryClient.invalidateQueries({ queryKey: ['comunicados-admin'] })
    },
    onError: (e: Error) => toast.error(e?.message || 'Falha ao enviar comunicado'),
  })
  const toggle = useMutation({
    mutationFn: (id: number) => apiFetch(`/admin/comunicados/${id}/toggle`, { method: 'POST' }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['comunicados-admin'] }),
  })

  const togglePerfil = (p: string) => setForm(f => ({ ...f, perfis: f.perfis.includes(p) ? f.perfis.filter(x => x !== p) : [...f.perfis, p] }))
  const toggleUser = (m: string) => setForm(f => ({ ...f, matriculas: f.matriculas.includes(m) ? f.matriculas.filter(x => x !== m) : [...f.matriculas, m] }))

  // Editor Markdown — envolve a seleção ou prefixa a linha.
  function applyWrap(before: string, after: string, placeholder: string) {
    const ta = msgRef.current; if (!ta) return
    const s = ta.selectionStart ?? 0, e = ta.selectionEnd ?? 0
    const v = form.mensagem
    const sel = v.substring(s, e) || placeholder
    setForm(f => ({ ...f, mensagem: v.substring(0, s) + before + sel + after + v.substring(e) }))
    requestAnimationFrame(() => { ta.focus(); ta.setSelectionRange(s + before.length, s + before.length + sel.length) })
  }
  function applyLinePrefix(prefix: string) {
    const ta = msgRef.current; if (!ta) return
    const s = ta.selectionStart ?? 0
    const v = form.mensagem
    const ls = v.lastIndexOf('\n', s - 1) + 1
    setForm(f => ({ ...f, mensagem: v.substring(0, ls) + prefix + v.substring(ls) }))
    requestAnimationFrame(() => { ta.focus(); ta.setSelectionRange(s + prefix.length, s + prefix.length) })
  }

  const valid = form.titulo.trim() && form.mensagem.trim() &&
    (form.publico_tipo === 'todos' ||
      (form.publico_tipo === 'perfil' && form.perfis.length > 0) ||
      (form.publico_tipo === 'usuarios' && form.matriculas.length > 0))

  const rows = listData?.data ?? []

  return (
    <div className="flex flex-col gap-6">
      {/* Compositor */}
      <div className="bg-panel border border-edge rounded-lg p-5 shadow-sm flex flex-col gap-4">
        <div className="flex items-center gap-2">
          <Megaphone size={16} className="text-[#1A5FA8] dark:text-blue-400" />
          <h2 className="text-sm font-bold text-ink">Novo comunicado</h2>
        </div>

        <Input label="Título" value={form.titulo} maxLength={160}
          onChange={e => setForm(f => ({ ...f, titulo: e.target.value }))}
          placeholder="Ex.: Nova política de geração de DAGs" />
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <Select label="Severidade / cor" value={form.tipo} onChange={e => setForm(f => ({ ...f, tipo: e.target.value }))}>
            {TIPO_OPTS.map(o => <option key={o.v} value={o.v}>{o.label}</option>)}
          </Select>
          <div className="flex flex-col gap-1">
            <label className="text-xs text-dim font-medium">Formato</label>
            <div className="flex gap-1">
              {(['simples', 'banner'] as const).map(fm => (
                <button key={fm} type="button" onClick={() => setForm(f => ({ ...f, formato: fm }))}
                  className={`flex-1 px-2 py-1.5 rounded text-xs border transition-colors ${form.formato === fm ? 'bg-[#1A5FA8] text-white border-[#1A5FA8]' : 'border-edge text-dim hover:bg-edge/40'}`}>
                  {fm === 'simples' ? 'Sininho + toast' : 'Pop-up banner'}
                </button>
              ))}
            </div>
          </div>
          <Input label="Link (opcional)" value={form.link}
            onChange={e => setForm(f => ({ ...f, link: e.target.value }))} placeholder="/pipelines" />
        </div>

        {/* Editor Markdown + pré-visualização ao vivo */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
          <div className="flex flex-col gap-1">
            <label className="text-xs text-dim font-medium">Mensagem (Markdown)</label>
            <div className="flex flex-wrap items-center gap-0.5 border border-edge border-b-0 rounded-t-md px-1.5 py-1 bg-canvas">
              <MdBtn onClick={() => applyLinePrefix('# ')}  title="Título grande"><span className="text-[11px] font-bold">H1</span></MdBtn>
              <MdBtn onClick={() => applyLinePrefix('## ')} title="Título médio"><span className="text-[11px] font-bold">H2</span></MdBtn>
              <span className="w-px h-4 bg-edge mx-1" />
              <MdBtn onClick={() => applyWrap('**', '**', 'negrito')} title="Negrito"><Bold size={13} /></MdBtn>
              <MdBtn onClick={() => applyWrap('*', '*', 'itálico')}   title="Itálico"><Italic size={13} /></MdBtn>
              <MdBtn onClick={() => applyWrap('`', '`', 'código')}    title="Código"><Code size={13} /></MdBtn>
              <MdBtn onClick={() => applyLinePrefix('- ')}            title="Lista"><List size={13} /></MdBtn>
            </div>
            <textarea ref={msgRef} value={form.mensagem} rows={7}
              onChange={e => setForm(f => ({ ...f, mensagem: e.target.value }))}
              placeholder="Texto do comunicado…  Selecione um trecho e use os botões para formatar."
              className="bg-panel border border-edge rounded-b-md px-3 py-2 text-sm text-ink placeholder-dim focus:outline-none focus:ring-1 focus:ring-blue-500 resize-y" />
            <span className="text-[10px] text-dim/60">Dica: **negrito**, *itálico*, `código`, # título, - item de lista.</span>
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-xs text-dim font-medium">Pré-visualização — como o usuário verá</label>
            <div className="border border-edge rounded-md p-3 bg-canvas/40 min-h-[160px]">
              <ComunicadoPreview tipo={form.tipo} titulo={form.titulo} mensagem={form.mensagem} formato={form.formato} />
            </div>
          </div>
        </div>

        {/* Público-alvo */}
        <div className="flex flex-col gap-1">
          <label className="text-xs text-dim font-medium">Público-alvo</label>
          <div className="flex gap-1 mb-1">
            {([['todos', 'Todos'], ['perfil', 'Por perfil'], ['usuarios', 'Usuários específicos']] as const).map(([v, l]) => (
              <button key={v} type="button" onClick={() => setForm(f => ({ ...f, publico_tipo: v }))}
                className={`px-3 py-1.5 rounded text-xs border transition-colors ${form.publico_tipo === v ? 'bg-[#1A5FA8] text-white border-[#1A5FA8]' : 'border-edge text-dim hover:bg-edge/40'}`}>
                {l}
              </button>
            ))}
          </div>
          {form.publico_tipo === 'perfil' && (
            <div className="flex flex-wrap gap-2 p-2 border border-edge rounded-lg">
              {perfis.map(p => (
                <label key={p.perfil_nome} className="flex items-center gap-1.5 text-xs text-ink cursor-pointer px-2 py-1 rounded hover:bg-edge/40">
                  <input type="checkbox" checked={form.perfis.includes(p.perfil_nome)} onChange={() => togglePerfil(p.perfil_nome)} />
                  {p.perfil_nome}
                </label>
              ))}
            </div>
          )}
          {form.publico_tipo === 'usuarios' && (
            <div className="border border-edge rounded-lg p-2">
              <Input placeholder="Filtrar por nome ou matrícula…" value={userFilter} onChange={e => setUserFilter(e.target.value)} className="mb-2" />
              <div className="max-h-44 overflow-y-auto flex flex-col gap-0.5">
                {filteredUsers.map(u => (
                  <label key={u.matricula} className="flex items-center gap-2 text-xs text-ink cursor-pointer px-2 py-1 rounded hover:bg-edge/40">
                    <input type="checkbox" checked={form.matriculas.includes(u.matricula)} onChange={() => toggleUser(u.matricula)} />
                    <span className="font-medium">{[u.primeiro_nome, u.ultimo_nome].filter(Boolean).join(' ') || u.matricula}</span>
                    <span className="text-dim/60">{u.matricula}</span>
                    <Badge value={u.perfil} />
                  </label>
                ))}
                {filteredUsers.length === 0 && <div className="text-xs text-dim px-2 py-3 text-center">Nenhum usuário.</div>}
              </div>
              {form.matriculas.length > 0 && <div className="text-[11px] text-dim mt-1">{form.matriculas.length} selecionado(s)</div>}
            </div>
          )}
        </div>

        <div className="flex items-end justify-between gap-3">
          <Input label="Expira em (opcional)" type="date" value={form.expira_em}
            onChange={e => setForm(f => ({ ...f, expira_em: e.target.value }))} className="w-44" />
          <Button onClick={() => create.mutate()} loading={create.isPending} disabled={!valid}>
            <Megaphone size={13} /> Enviar comunicado
          </Button>
        </div>
      </div>

      {/* Lista / auditoria */}
      <div>
        <h2 className="text-sm font-bold text-ink mb-2">Comunicados enviados</h2>
        {isLoading && <PageSpinner />}
        {!isLoading && rows.length === 0 && <div className="text-xs text-dim py-6 text-center">Nenhum comunicado enviado ainda.</div>}
        <div className="flex flex-col gap-2">
          {rows.map(c => (
            <div key={c.id} className="bg-panel border border-edge rounded-lg p-3 shadow-sm">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-sm font-semibold text-ink truncate">{c.titulo}</span>
                    <Badge value={c.tipo} />
                    <span className="text-[10px] px-1.5 py-0.5 rounded-full border border-edge text-dim">{c.formato === 'banner' ? 'banner' : 'simples'}</span>
                    {!c.ativo && <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-slate-500/20 text-slate-400">encerrado</span>}
                  </div>
                  <div className="text-[11px] text-dim mt-1">{c.publico_desc} · {c.criado_em} · por {c.criado_por}</div>
                </div>
                <div className="flex items-center gap-1.5 shrink-0">
                  <Button size="sm" variant="secondary" onClick={() => setDetailId(c.id)}><Eye size={12} /> Detalhes</Button>
                  <Button size="sm" variant={c.ativo ? 'danger' : 'secondary'} onClick={() => toggle.mutate(c.id)}>{c.ativo ? 'Encerrar' : 'Reativar'}</Button>
                </div>
              </div>
              <div className="flex items-center gap-4 mt-2 text-[11px]">
                <span className="text-dim">Entregues: <span className="text-ink font-semibold">{c.total}</span></span>
                <span className="text-dim">Vistos: <span className="text-blue-400 font-semibold">{c.vistos}</span> ({pct(c.vistos, c.total)}%)</span>
                <span className="text-dim">Confirmados: <span className="text-green-500 font-semibold">{c.confirmados}</span> ({pct(c.confirmados, c.total)}%)</span>
                <div className="flex-1 h-1.5 bg-edge/50 rounded-full overflow-hidden max-w-[160px]">
                  <div className="h-full bg-green-500" style={{ width: `${pct(c.confirmados, c.total)}%` }} />
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {detailId != null && <ComunicadoDetail id={detailId} onClose={() => setDetailId(null)} />}
    </div>
  )
}
