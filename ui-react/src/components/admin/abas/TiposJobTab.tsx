import { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { apiFetch } from '../../../lib/api'
import { Button } from '../../ui/Button'
import { Input, Select } from '../../ui/Input'
import { Badge } from '../../ui/Badge'
import { Modal } from '../../ui/Modal'
import { PageSpinner } from '../../ui/Spinner'
import { toast } from '../../ui/Toast'
import { queryClient } from '../../../lib/queryClient'
import { ConfirmModal } from '../ComumUI'
import { Edit2, Trash2, Plus, Save } from 'lucide-react'

// ── Tipos de Job ────────────────────────────────────────────────
interface TipoJobRow { id: number; nome: string; descricao?: string; lineage_enabled: boolean; status: boolean }
export function TiposJobTab() {
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState<{ id?: number; nome: string; descricao: string; status: boolean; lineage_enabled: boolean }>({ nome: '', descricao: '', status: true, lineage_enabled: true })
  const [deleteConfirm, setDeleteConfirm] = useState<TipoJobRow | null>(null)

  const { data, isLoading } = useQuery<{ job_types: TipoJobRow[] }>({
    queryKey: ['tipos-job'],
    queryFn: () => apiFetch('/catalogo', { method: 'POST', body: JSON.stringify({ mode: 'list_job_types', include_inactive: true }) }),
  })

  const saveMut = useMutation({
    mutationFn: (f: typeof form) => apiFetch('/catalogo', {
      method: 'POST',
      body: JSON.stringify({ mode: 'save_job_type', data: { id: f.id ?? null, nome: f.nome, descricao: f.descricao, status: f.status, lineage_enabled: f.lineage_enabled } }),
    }),
    onSuccess: () => { toast.success('Tipo de job salvo'); queryClient.invalidateQueries({ queryKey: ['tipos-job'] }); setShowForm(false) },
    onError: (e: any) => toast.error(e.message),
  })

  const deleteMut = useMutation({
    mutationFn: (id: number) => apiFetch('/catalogo', { method: 'POST', body: JSON.stringify({ mode: 'delete_job_type', id }) }),
    onSuccess: () => { toast.success('Tipo removido'); queryClient.invalidateQueries({ queryKey: ['tipos-job'] }); setDeleteConfirm(null) },
    onError: (e: any) => toast.error(e.message),
  })

  const openNew = () => { setForm({ nome: '', descricao: '', status: true, lineage_enabled: true }); setShowForm(true) }
  const openEdit = (t: TipoJobRow) => { setForm({ id: t.id, nome: t.nome, descricao: t.descricao ?? '', status: t.status, lineage_enabled: t.lineage_enabled }); setShowForm(true) }

  const rows = data?.job_types ?? []

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <span className="text-sm text-dim">{rows.length} tipos cadastrados</span>
        <Button size="sm" onClick={openNew}><Plus size={13} /> Novo Tipo</Button>
      </div>
      {isLoading ? <PageSpinner /> : (
        <div className="bg-panel border border-edge rounded-lg overflow-hidden shadow-sm">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs text-dim border-b border-edge bg-canvas/50">
                <th className="px-4 py-2.5 text-left font-semibold">Nome</th>
                <th className="px-4 py-2.5 text-left font-semibold">Descrição</th>
                <th className="px-4 py-2.5 text-left font-semibold">Lineage</th>
                <th className="px-4 py-2.5 text-left font-semibold">Status</th>
                <th className="px-4 py-2.5 w-20"></th>
              </tr>
            </thead>
            <tbody>
              {rows.map(t => (
                <tr key={t.id} className="border-b border-edge/50 hover:bg-canvas/50 transition-colors">
                  <td className="px-4 py-2.5 font-mono text-xs font-medium text-ink">{t.nome}</td>
                  <td className="px-4 py-2.5 text-xs text-dim">{t.descricao}</td>
                  <td className="px-4 py-2.5"><Badge value={t.lineage_enabled ? 'sim' : 'não'} /></td>
                  <td className="px-4 py-2.5"><Badge value={t.status ? 'ativo' : 'inativo'} /></td>
                  <td className="px-4 py-2.5">
                    <div className="flex items-center gap-1 justify-end">
                      <button onClick={() => openEdit(t)} className="text-slate-400 hover:text-[#1A5FA8] dark:hover:text-blue-400 p-1 rounded" title="Editar"><Edit2 size={13} /></button>
                      <button onClick={() => setDeleteConfirm(t)} className="text-slate-400 hover:text-red-500 dark:hover:text-red-400 p-1 rounded" title="Excluir"><Trash2 size={13} /></button>
                    </div>
                  </td>
                </tr>
              ))}
              {rows.length === 0 && <tr><td colSpan={5} className="px-4 py-6 text-center text-xs text-dim">Nenhum tipo de job cadastrado.</td></tr>}
            </tbody>
          </table>
        </div>
      )}

      {showForm && (
        <Modal open title={form.id ? 'Editar Tipo de Job' : 'Novo Tipo de Job'} onClose={() => setShowForm(false)}>
          <div className="flex flex-col gap-4">
            <Input label="Nome" value={form.nome} onChange={e => setForm(f => ({ ...f, nome: e.target.value }))} autoFocus />
            <Input label="Descrição" value={form.descricao} onChange={e => setForm(f => ({ ...f, descricao: e.target.value }))} />
            <div className="grid grid-cols-2 gap-3">
              <Select label="Status" value={form.status ? '1' : '0'} onChange={e => setForm(f => ({ ...f, status: e.target.value === '1' }))}>
                <option value="1">Ativo</option>
                <option value="0">Inativo</option>
              </Select>
              <label className="flex items-center gap-2 text-sm text-ink mt-6">
                <input type="checkbox" checked={form.lineage_enabled} onChange={e => setForm(f => ({ ...f, lineage_enabled: e.target.checked }))} />
                Lineage habilitado
              </label>
            </div>
            <div className="flex justify-end gap-2">
              <Button variant="secondary" onClick={() => setShowForm(false)}>Cancelar</Button>
              <Button onClick={() => saveMut.mutate(form)} loading={saveMut.isPending} disabled={!form.nome.trim()}><Save size={13} /> Salvar</Button>
            </div>
          </div>
        </Modal>
      )}

      <ConfirmModal
        open={!!deleteConfirm}
        title="Excluir Tipo de Job"
        message={`Excluir o tipo "${deleteConfirm?.nome}"? Pipelines já cadastrados não serão afetados.`}
        danger confirmLabel="Excluir"
        onConfirm={() => deleteConfirm && deleteMut.mutate(deleteConfirm.id)}
        onCancel={() => setDeleteConfirm(null)}
      />
    </div>
  )
}
