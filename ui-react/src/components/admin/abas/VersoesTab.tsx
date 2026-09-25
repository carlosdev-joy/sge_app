import { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { apiFetch } from '../../../lib/api'
import { Button } from '../../ui/Button'
import { Input, Textarea } from '../../ui/Input'
import { Modal } from '../../ui/Modal'
import { PageSpinner } from '../../ui/Spinner'
import { toast } from '../../ui/Toast'
import { queryClient } from '../../../lib/queryClient'
import { ConfirmModal, Markdown } from '../ComumUI'
import {
  Edit2, Trash2, Plus, ChevronDown, ChevronUp, Save, Eye,
} from 'lucide-react'

// ── Versões ─────────────────────────────────────────────────────
interface VersaoRow { id: number; versao: string; titulo: string; descricao_md?: string; criado_em?: string; criado_por?: string }
export function VersoesTab() {
  const [expanded, setExpanded] = useState<Set<number>>(new Set())
  const [showForm, setShowForm] = useState(false)
  const [editId, setEditId] = useState<number | null>(null)
  const [form, setForm] = useState({ versao: '', titulo: '', descricao_md: '' })
  const [previewMode, setPreviewMode] = useState(false)
  const [deleteConfirm, setDeleteConfirm] = useState<VersaoRow | null>(null)

  const { data, isLoading } = useQuery<{ data: VersaoRow[] }>({
    queryKey: ['versoes'],
    queryFn: () => apiFetch('/versao'),
  })

  const saveMut = useMutation({
    mutationFn: (v: { id?: number; versao: string; titulo: string; descricao_md: string }) =>
      apiFetch('/versao/register', {
        method: 'POST',
        body: JSON.stringify({ action: v.id ? 'update' : 'create', ...v }),
      }),
    onSuccess: () => {
      toast.success(editId ? 'Versão atualizada' : 'Versão criada')
      queryClient.invalidateQueries({ queryKey: ['versoes'] })
      closeForm()
    },
    onError: (e: any) => toast.error(e.message),
  })

  const deleteMut = useMutation({
    mutationFn: (id: number) => apiFetch('/versao/register', { method: 'POST', body: JSON.stringify({ action: 'delete', id }) }),
    onSuccess: () => { toast.success('Versão removida'); queryClient.invalidateQueries({ queryKey: ['versoes'] }); setDeleteConfirm(null) },
    onError: (e: any) => toast.error(e.message),
  })

  const openNew = () => { setEditId(null); setForm({ versao: '', titulo: '', descricao_md: '' }); setPreviewMode(false); setShowForm(true) }
  const openEdit = (v: VersaoRow) => { setEditId(v.id); setForm({ versao: v.versao, titulo: v.titulo, descricao_md: v.descricao_md ?? '' }); setPreviewMode(false); setShowForm(true) }
  const closeForm = () => { setShowForm(false); setEditId(null) }

  const toggleExpand = (id: number) => setExpanded(prev => { const s = new Set(prev); s.has(id) ? s.delete(id) : s.add(id); return s })

  const rows = data?.data ?? []

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-dim">Clique em uma versão para expandir. Edite o texto em markdown.</p>
        <Button size="sm" onClick={openNew}><Plus size={13} /> Nova Versão</Button>
      </div>

      {isLoading ? <PageSpinner /> : (
        <div className="flex flex-col gap-2">
          {rows.length === 0 && <div className="text-center py-10 text-sm text-dim bg-panel border border-edge rounded-lg">Nenhuma versão registrada.</div>}
          {rows.map(v => {
            const isOpen = expanded.has(v.id)
            return (
              <div key={v.id} className="bg-panel border border-edge rounded-lg overflow-hidden shadow-sm transition-shadow hover:shadow-md">
                <button onClick={() => toggleExpand(v.id)} className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-canvas/60 transition-colors">
                  <span className="inline-flex items-center px-2 py-0.5 rounded bg-[#1A5FA8]/10 text-[#1A5FA8] dark:bg-blue-900/40 dark:text-blue-300 font-bold font-mono text-xs border border-[#1A5FA8]/20 dark:border-blue-700">v{v.versao}</span>
                  <span className="text-ink font-medium text-sm flex-1 text-left">{v.titulo}</span>
                  <span className="text-xs text-dim hidden sm:block">{(v.criado_em ?? '').substring(0, 10)} · {v.criado_por ?? 'admin'}</span>
                  {isOpen ? <ChevronUp size={14} className="text-dim shrink-0" /> : <ChevronDown size={14} className="text-dim shrink-0" />}
                </button>
                {isOpen && (
                  <div className="border-t border-edge px-4 py-4 bg-canvas/30">
                    {v.descricao_md ? <Markdown text={v.descricao_md} /> : <p className="text-sm text-dim italic">Sem descrição.</p>}
                    <div className="flex gap-2 pt-3 mt-3 border-t border-edge/50">
                      <Button variant="secondary" size="sm" onClick={() => openEdit(v)}><Edit2 size={12} /> Editar</Button>
                      <Button variant="ghost" size="sm" onClick={() => setDeleteConfirm(v)}><Trash2 size={12} className="text-red-500" /><span className="text-red-500">Excluir</span></Button>
                    </div>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      {showForm && (
        <Modal open title={editId ? 'Editar Versão' : 'Nova Versão'} onClose={closeForm} size="lg">
          <div className="flex flex-col gap-4">
            <div className="grid grid-cols-2 gap-3">
              <Input label="Versão" value={form.versao} onChange={e => setForm(f => ({ ...f, versao: e.target.value }))} placeholder="2.5.0" />
              <Input label="Título" value={form.titulo} onChange={e => setForm(f => ({ ...f, titulo: e.target.value }))} />
            </div>
            <div>
              <div className="flex items-center gap-1 mb-2">
                <button onClick={() => setPreviewMode(false)} className={`px-3 py-1 text-xs rounded ${!previewMode ? 'bg-[#1A5FA8] text-white' : 'bg-canvas text-dim border border-edge'}`}>Editar</button>
                <button onClick={() => setPreviewMode(true)} className={`px-3 py-1 text-xs rounded flex items-center gap-1 ${previewMode ? 'bg-[#1A5FA8] text-white' : 'bg-canvas text-dim border border-edge'}`}><Eye size={12} /> Visualizar</button>
              </div>
              {previewMode ? (
                <div className="border border-edge rounded-md p-3 min-h-[10rem] bg-canvas/30">
                  {form.descricao_md.trim() ? <Markdown text={form.descricao_md} /> : <span className="text-xs text-dim">Nenhum conteúdo para visualizar.</span>}
                </div>
              ) : (
                <Textarea value={form.descricao_md} onChange={e => setForm(f => ({ ...f, descricao_md: e.target.value }))} rows={8} placeholder="## Novidades&#10;- Item 1&#10;- Item 2" />
              )}
            </div>
            <div className="flex justify-end gap-2">
              <Button variant="secondary" onClick={closeForm}>Cancelar</Button>
              <Button onClick={() => saveMut.mutate({ id: editId ?? undefined, ...form })} loading={saveMut.isPending} disabled={!form.versao || !form.titulo}><Save size={13} /> Salvar</Button>
            </div>
          </div>
        </Modal>
      )}

      <ConfirmModal
        open={!!deleteConfirm}
        title="Excluir Versão"
        message={`Remover a versão v${deleteConfirm?.versao} — "${deleteConfirm?.titulo}"? Esta ação é irreversível.`}
        danger confirmLabel="Excluir"
        onConfirm={() => deleteConfirm && deleteMut.mutate(deleteConfirm.id)}
        onCancel={() => setDeleteConfirm(null)}
      />
    </div>
  )
}
