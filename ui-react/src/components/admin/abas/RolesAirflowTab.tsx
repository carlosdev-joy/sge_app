import { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { Button } from '../../ui/Button'
import { Input, Select } from '../../ui/Input'
import { toast } from '../../ui/Toast'
import { queryClient } from '../../../lib/queryClient'
import { adminPost } from '../comum'
import { ConfirmModal } from '../ComumUI'
import { Q_ADMIN_PERFIS, buscarPerfis, nomesDePerfis, type PerfilRow } from '../acesso'
import { Edit2, Trash2, Save } from 'lucide-react'

// ── Mapeamento Airflow Role → Perfil ────────────────────────────
// Decisão explícita da spec (docs/spec-admin-reestruturacao.md, F3): esta
// seção era o 3º e último bloco da aba "Usuários & Perfis"
// (abas/UsuariosTab.tsx). Virou aba própria em Acesso › Roles do Airflow com o
// conteúdo intacto — não devolver.
interface RoleMapRow { role_airflow: string; perfil_nome: string; ordem_prioridade: number; descricao?: string; ativo: number }

export function RolesAirflowTab() {
  const [rmForm, setRmForm] = useState({ role_airflow: '', perfil_nome: '', ordem_prioridade: 99, descricao: '', ativo: true })
  const [deleteRm, setDeleteRm] = useState<string | null>(null)

  // Mesma query da aba Perfis (cache compartilhado — ver components/admin/acesso.ts).
  const { data: perfis } = useQuery<{ perfis: PerfilRow[] }>({ queryKey: Q_ADMIN_PERFIS, queryFn: buscarPerfis })
  const { data: roleMap } = useQuery<{ dados: RoleMapRow[] }>({ queryKey: ['admin-rolemap'], queryFn: () => adminPost('role_map_list') })

  const rmSave = useMutation({
    mutationFn: (p: typeof rmForm) => adminPost('role_map_upsert', p),
    onSuccess: () => { toast.success('Mapeamento salvo'); queryClient.invalidateQueries({ queryKey: ['admin-rolemap'] }); setRmForm({ role_airflow: '', perfil_nome: '', ordem_prioridade: 99, descricao: '', ativo: true }) },
    onError: (e: Error) => toast.error(e.message),
  })
  const rmDelete = useMutation({
    mutationFn: (role_airflow: string) => adminPost('role_map_delete', { role_airflow }),
    onSuccess: () => { toast.success('Mapeamento removido'); queryClient.invalidateQueries({ queryKey: ['admin-rolemap'] }); setDeleteRm(null) },
    onError: (e: Error) => toast.error(e.message),
  })

  const perfilNames = nomesDePerfis(perfis?.perfis ?? [])

  return (
    <div className="flex flex-col gap-6">
      {/* Mapeamento Airflow Role → Perfil */}
      <div className="flex flex-col gap-3">
        <h3 className="text-sm font-semibold text-ink">Mapeamento de Roles (Airflow → Perfil)</h3>
        <div className="bg-panel border border-edge rounded-lg overflow-hidden shadow-sm">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs text-dim border-b border-edge bg-canvas/50">
                <th className="px-4 py-2.5 text-left font-semibold">Role Airflow</th>
                <th className="px-4 py-2.5 text-left font-semibold">Perfil</th>
                <th className="px-4 py-2.5 text-center font-semibold">Prioridade</th>
                <th className="px-4 py-2.5 text-left font-semibold">Descrição</th>
                <th className="px-4 py-2.5 text-center font-semibold">Ativo</th>
                <th className="px-4 py-2.5 w-20"></th>
              </tr>
            </thead>
            <tbody>
              {(roleMap?.dados ?? []).map(r => (
                <tr key={r.role_airflow} className="border-b border-edge/50 hover:bg-canvas/50 transition-colors">
                  <td className="px-4 py-2.5 font-medium text-xs text-ink">{r.role_airflow}</td>
                  <td className="px-4 py-2.5"><code className="text-xs text-[#1A5FA8] dark:text-blue-400">{r.perfil_nome}</code></td>
                  <td className="px-4 py-2.5 text-center text-xs text-dim">{r.ordem_prioridade}</td>
                  <td className="px-4 py-2.5 text-xs text-dim">{r.descricao}</td>
                  <td className="px-4 py-2.5 text-center text-xs">{r.ativo ? '✅' : '⏸'}</td>
                  <td className="px-4 py-2.5">
                    <div className="flex items-center gap-1 justify-end">
                      <button onClick={() => setRmForm({ role_airflow: r.role_airflow, perfil_nome: r.perfil_nome, ordem_prioridade: r.ordem_prioridade, descricao: r.descricao ?? '', ativo: !!r.ativo })} className="text-slate-400 hover:text-[#1A5FA8] dark:hover:text-blue-400 p-1 rounded" title="Editar"><Edit2 size={13} /></button>
                      <button onClick={() => setDeleteRm(r.role_airflow)} className="text-slate-400 hover:text-red-500 dark:hover:text-red-400 p-1 rounded" title="Remover"><Trash2 size={13} /></button>
                    </div>
                  </td>
                </tr>
              ))}
              {(roleMap?.dados ?? []).length === 0 && <tr><td colSpan={6} className="px-4 py-6 text-center text-xs text-dim">Nenhum mapeamento cadastrado.</td></tr>}
            </tbody>
          </table>
        </div>
        <div className="bg-panel border border-edge rounded-lg p-4 shadow-sm flex flex-wrap gap-3 items-end">
          <Input label="Role Airflow" value={rmForm.role_airflow} onChange={e => setRmForm(f => ({ ...f, role_airflow: e.target.value }))} className="w-44" />
          <Select label="Perfil" value={rmForm.perfil_nome} onChange={e => setRmForm(f => ({ ...f, perfil_nome: e.target.value }))} className="w-36">
            <option value="">selecione</option>
            {perfilNames.map(p => <option key={p} value={p}>{p}</option>)}
          </Select>
          <Input label="Prioridade" type="number" value={String(rmForm.ordem_prioridade)} onChange={e => setRmForm(f => ({ ...f, ordem_prioridade: parseInt(e.target.value) || 99 }))} className="w-24" />
          <Input label="Descrição" value={rmForm.descricao} onChange={e => setRmForm(f => ({ ...f, descricao: e.target.value }))} className="w-44" />
          <label className="flex items-center gap-1.5 text-xs text-ink mb-2"><input type="checkbox" checked={rmForm.ativo} onChange={e => setRmForm(f => ({ ...f, ativo: e.target.checked }))} /> Ativo</label>
          <Button onClick={() => rmSave.mutate(rmForm)} loading={rmSave.isPending} disabled={!rmForm.role_airflow.trim() || !rmForm.perfil_nome}><Save size={13} /> Salvar Mapeamento</Button>
        </div>
      </div>

      <ConfirmModal open={!!deleteRm} title="Remover Mapeamento" message={`Remover o mapeamento do role "${deleteRm}"?`} danger confirmLabel="Remover" onConfirm={() => deleteRm && rmDelete.mutate(deleteRm)} onCancel={() => setDeleteRm(null)} />
    </div>
  )
}
