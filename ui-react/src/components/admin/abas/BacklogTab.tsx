import { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { apiFetch } from '../../../lib/api'
import { Button } from '../../ui/Button'
import { Input, Select, Textarea } from '../../ui/Input'
import { Modal } from '../../ui/Modal'
import { PageSpinner } from '../../ui/Spinner'
import { toast } from '../../ui/Toast'
import { queryClient } from '../../../lib/queryClient'
import { ConfirmModal } from '../ComumUI'
import { Edit2, Trash2, Plus } from 'lucide-react'

// ── Backlog ──────────────────────────────────────────────────────
interface BacklogItem {
  id: number; titulo: string; descricao: string | null; tipo: string; area: string | null
  prioridade: string; status: string; estimativa: string | null; responsavel: string | null
  ref_pr: string | null; tags: string | null; criado_por: string | null
  criado_em: string | null; atualizado_em: string | null; concluido_em: string | null
}
const BL_TIPOS = ['feature', 'bug', 'debt', 'spike']
const BL_AREAS = ['backend', 'frontend', 'datastage', 'deploy', 'infra', 'outro']
const BL_PRIOS = ['P0', 'P1', 'P2', 'P3']
const BL_STATUS: { v: string; label: string }[] = [
  { v: 'ideia', label: 'Ideia' },
  { v: 'refinado', label: 'Refinado' },
  { v: 'em_andamento', label: 'Em andamento' },
  { v: 'concluido', label: 'Concluído' },
  { v: 'descartado', label: 'Descartado' },
]
const BL_STATUS_CLS: Record<string, string> = {
  ideia: 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300',
  refinado: 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300',
  em_andamento: 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300',
  concluido: 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300',
  descartado: 'bg-slate-100 text-slate-500 dark:bg-slate-800/60 dark:text-slate-400',
}
const BL_PRIO_CLS: Record<string, string> = {
  P0: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300',
  P1: 'bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-300',
  P2: 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300',
  P3: 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400',
}
const EMPTY_BL = { titulo: '', descricao: '', tipo: 'feature', area: 'backend', prioridade: 'P2', status: 'ideia', estimativa: '', responsavel: '', ref_pr: '', tags: '' }

function BacklogForm({ initial, onClose }: { initial: Partial<BacklogItem>; onClose: () => void }) {
  const [f, setF] = useState<Record<string, string>>({ ...EMPTY_BL, ...Object.fromEntries(Object.entries(initial).map(([k, v]) => [k, v == null ? '' : String(v)])) })
  const isEdit = !!initial?.id
  const set = (k: string) => (e: { target: { value: string } }) => setF(x => ({ ...x, [k]: e.target.value }))
  const save = useMutation({
    mutationFn: () => isEdit
      ? apiFetch(`/backlog/${initial.id}`, { method: 'PATCH', body: JSON.stringify(f) })
      : apiFetch('/backlog', { method: 'POST', body: JSON.stringify(f) }),
    onSuccess: () => { toast.success(isEdit ? 'Item atualizado.' : 'Item criado.'); queryClient.invalidateQueries({ queryKey: ['backlog'] }); onClose() },
    onError: (e: Error) => toast.error(e?.message || 'Falha ao salvar'),
  })
  return (
    <Modal open onClose={onClose} title={isEdit ? 'Editar item de backlog' : 'Novo item de backlog'} size="lg">
      <div className="flex flex-col gap-3">
        <Input label="Título *" value={f.titulo} maxLength={200} onChange={set('titulo')} placeholder="Resumo curto do item" />
        <Textarea label="Descrição" rows={3} value={f.descricao} onChange={set('descricao')} placeholder="Contexto, critérios de aceite…" />
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
          <Select label="Tipo" value={f.tipo} onChange={set('tipo')}>{BL_TIPOS.map(t => <option key={t} value={t}>{t}</option>)}</Select>
          <Select label="Área" value={f.area} onChange={set('area')}>{BL_AREAS.map(a => <option key={a} value={a}>{a}</option>)}</Select>
          <Select label="Prioridade" value={f.prioridade} onChange={set('prioridade')}>{BL_PRIOS.map(p => <option key={p} value={p}>{p}</option>)}</Select>
          <Select label="Status" value={f.status} onChange={set('status')}>{BL_STATUS.map(s => <option key={s.v} value={s.v}>{s.label}</option>)}</Select>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
          <Input label="Estimativa" value={f.estimativa} onChange={set('estimativa')} placeholder="ex.: 2d, M" />
          <Input label="Responsável" value={f.responsavel} onChange={set('responsavel')} placeholder="matrícula/nome" />
          <Input label="Ref. PR" value={f.ref_pr} onChange={set('ref_pr')} placeholder="#54" />
        </div>
        <Input label="Tags" value={f.tags} onChange={set('tags')} placeholder="separadas por vírgula" />
        <div className="flex justify-end gap-2 border-t border-edge pt-3">
          <Button variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button loading={save.isPending} disabled={!f.titulo.trim()} onClick={() => save.mutate()}>{isEdit ? 'Salvar' : 'Criar'}</Button>
        </div>
      </div>
    </Modal>
  )
}

export function BacklogTab() {
  const [filtros, setFiltros] = useState({ status: '', tipo: '', area: '', q: '' })
  const [form, setForm] = useState<Partial<BacklogItem> | null>(null)
  const [delItem, setDelItem] = useState<BacklogItem | null>(null)

  const { data, isLoading } = useQuery<{ data: BacklogItem[]; stats: Record<string, number>; total: number }>({
    queryKey: ['backlog', filtros],
    queryFn: () => {
      const p = new URLSearchParams()
      if (filtros.status) p.set('status', filtros.status)
      if (filtros.tipo) p.set('tipo', filtros.tipo)
      if (filtros.area) p.set('area', filtros.area)
      if (filtros.q) p.set('q', filtros.q)
      const qs = p.toString()
      return apiFetch(`/backlog${qs ? '?' + qs : ''}`)
    },
  })
  const items = data?.data ?? []
  const stats = data?.stats ?? {}

  const patchStatus = useMutation({
    mutationFn: (v: { id: number; status: string }) => apiFetch(`/backlog/${v.id}`, { method: 'PATCH', body: JSON.stringify({ status: v.status }) }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['backlog'] }),
    onError: (e: Error) => toast.error(e?.message || 'Falha ao mudar status'),
  })
  const del = useMutation({
    mutationFn: (id: number) => apiFetch(`/backlog/${id}`, { method: 'DELETE' }),
    onSuccess: () => { toast.success('Item removido.'); setDelItem(null); queryClient.invalidateQueries({ queryKey: ['backlog'] }) },
    onError: (e: Error) => toast.error(e?.message || 'Falha ao remover'),
  })
  const hasFilter = filtros.status || filtros.tipo || filtros.area || filtros.q

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex gap-1.5 flex-wrap">
          {BL_STATUS.map(s => (
            <button key={s.v} onClick={() => setFiltros(x => ({ ...x, status: x.status === s.v ? '' : s.v }))}
              className={`px-2.5 py-1 rounded-lg text-xs border transition-all ${filtros.status === s.v ? 'border-[#1A5FA8] ring-1 ring-[#1A5FA8]/40' : 'border-edge'} ${BL_STATUS_CLS[s.v]}`}>
              {s.label}: <strong>{stats[s.v] ?? 0}</strong>
            </button>
          ))}
        </div>
        <Button onClick={() => setForm({})}><Plus size={14} /> Novo item</Button>
      </div>

      <div className="flex gap-2 flex-wrap items-end">
        <Input placeholder="Buscar título/descrição…" value={filtros.q} onChange={e => setFiltros(x => ({ ...x, q: e.target.value }))} className="w-56" />
        <Select value={filtros.tipo} onChange={e => setFiltros(x => ({ ...x, tipo: e.target.value }))} className="w-32"><option value="">Todo tipo</option>{BL_TIPOS.map(t => <option key={t} value={t}>{t}</option>)}</Select>
        <Select value={filtros.area} onChange={e => setFiltros(x => ({ ...x, area: e.target.value }))} className="w-36"><option value="">Toda área</option>{BL_AREAS.map(a => <option key={a} value={a}>{a}</option>)}</Select>
        {hasFilter && <Button variant="secondary" size="sm" onClick={() => setFiltros({ status: '', tipo: '', area: '', q: '' })}>Limpar</Button>}
      </div>

      {isLoading && <PageSpinner />}
      {!isLoading && items.length === 0 && <div className="text-xs text-dim py-8 text-center">Nenhum item no backlog.</div>}

      {items.length > 0 && (
        <div className="overflow-x-auto border border-edge rounded-lg">
          <table className="w-full text-sm">
            <thead className="bg-edge/30 text-dim">
              <tr className="text-left">
                <th className="px-3 py-2 font-medium">Prio</th>
                <th className="px-3 py-2 font-medium">Tipo</th>
                <th className="px-3 py-2 font-medium">Título</th>
                <th className="px-3 py-2 font-medium">Área</th>
                <th className="px-3 py-2 font-medium">Status</th>
                <th className="px-3 py-2 font-medium">Resp.</th>
                <th className="px-3 py-2 font-medium"></th>
              </tr>
            </thead>
            <tbody>
              {items.map(it => (
                <tr key={it.id} className="border-t border-edge/40 hover:bg-edge/20">
                  <td className="px-3 py-2"><span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${BL_PRIO_CLS[it.prioridade] ?? ''}`}>{it.prioridade}</span></td>
                  <td className="px-3 py-2 text-dim text-xs">{it.tipo}</td>
                  <td className="px-3 py-2 min-w-[220px]">
                    <div className="text-ink font-medium">{it.titulo}</div>
                    {it.descricao && <div className="text-[11px] text-dim line-clamp-1">{it.descricao}</div>}
                  </td>
                  <td className="px-3 py-2 text-dim text-xs">{it.area ?? '—'}</td>
                  <td className="px-3 py-2">
                    <select value={it.status} onChange={e => patchStatus.mutate({ id: it.id, status: e.target.value })}
                      className="text-[11px] rounded px-1.5 py-1 border border-edge bg-panel text-ink focus:outline-none focus:ring-1 focus:ring-blue-500">
                      {BL_STATUS.map(s => <option key={s.v} value={s.v}>{s.label}</option>)}
                    </select>
                  </td>
                  <td className="px-3 py-2 text-dim text-xs">{it.responsavel ?? '—'}</td>
                  <td className="px-3 py-2">
                    <div className="flex items-center gap-1 justify-end">
                      <button onClick={() => setForm(it)} className="text-slate-400 hover:text-[#1A5FA8] dark:hover:text-blue-400 p-1 rounded" title="Editar"><Edit2 size={13} /></button>
                      <button onClick={() => setDelItem(it)} className="text-slate-400 hover:text-red-500 dark:hover:text-red-400 p-1 rounded" title="Excluir"><Trash2 size={13} /></button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {form !== null && <BacklogForm initial={form} onClose={() => setForm(null)} />}
      <ConfirmModal open={!!delItem} title="Remover item" danger confirmLabel="Remover"
        message={`Remover "${delItem?.titulo}" do backlog? Não pode ser desfeito.`}
        onConfirm={() => delItem && del.mutate(delItem.id)} onCancel={() => setDelItem(null)} />
    </div>
  )
}
