import { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { Button } from '../../ui/Button'
import { Input } from '../../ui/Input'
import { Badge } from '../../ui/Badge'
import { toast } from '../../ui/Toast'
import { queryClient } from '../../../lib/queryClient'
import { RBAC_RECURSOS_PERFIS } from '../../../lib/rbacRecursos'
import { adminPost } from '../comum'
import { ConfirmModal } from '../ComumUI'
import { Q_ADMIN_PERFIS, buscarPerfis, type PerfilRow } from '../acesso'
import { Trash2, Plus, Save } from 'lucide-react'

// ── Perfis e Permissões ─────────────────────────────────────────
// Decisão explícita da spec (docs/spec-admin-reestruturacao.md, F3): esta
// seção era o 2º bloco da aba "Usuários & Perfis" (abas/UsuariosTab.tsx, entre
// a lista de usuários e o mapeamento de roles). Virou aba própria em
// Acesso › Perfis e Permissões com o conteúdo intacto — não devolver.
// A matriz renderiza RBAC_RECURSOS_PERFIS (sem agente_*): agente se concede
// usuário a usuário, no modal de Usuários (tests/test_rbac_recursos_admin.py).
export function PerfisTab() {
  // perfis: estado local de permissões editáveis por perfil
  const [permEdits, setPermEdits] = useState<Record<string, Set<string>>>({})
  const [newPerfil, setNewPerfil] = useState({ nome: '', descricao: '' })
  const [deletePerfil, setDeletePerfil] = useState<string | null>(null)

  const { data: perfis } = useQuery<{ perfis: PerfilRow[] }>({ queryKey: Q_ADMIN_PERFIS, queryFn: buscarPerfis })

  const perfilSave = useMutation({
    mutationFn: (p: { perfil_nome: string; permissoes?: string[]; descricao?: string }) => adminPost('perfil_upsert', p),
    onSuccess: (_, v) => { toast.success(`Perfil "${v.perfil_nome}" salvo`); queryClient.invalidateQueries({ queryKey: Q_ADMIN_PERFIS }); setPermEdits(prev => { const n = { ...prev }; delete n[v.perfil_nome]; return n }); setNewPerfil({ nome: '', descricao: '' }) },
    onError: (e: Error) => toast.error(e.message),
  })
  const perfilDelete = useMutation({
    mutationFn: (perfil_nome: string) => adminPost('perfil_delete', { perfil_nome }),
    onSuccess: () => { toast.success('Perfil removido'); queryClient.invalidateQueries({ queryKey: Q_ADMIN_PERFIS }); setDeletePerfil(null) },
    onError: (e: Error) => toast.error(e.message),
  })

  // helpers de permissão
  const permSet = (p: PerfilRow): Set<string> => permEdits[p.perfil_nome] ?? new Set(p.permissoes ?? [])
  const togglePerm = (perfil: string, rec: string, base: string[]) => {
    setPermEdits(prev => {
      const cur = new Set(prev[perfil] ?? base)
      if (cur.has(rec)) cur.delete(rec)
      else cur.add(rec)
      return { ...prev, [perfil]: cur }
    })
  }

  return (
    <div className="flex flex-col gap-6">
      {/* Perfis e permissões */}
      <div className="flex flex-col gap-3">
        <h3 className="text-sm font-semibold text-ink">Perfis e Permissões</h3>
        <div className="flex flex-col gap-3">
          {(perfis?.perfis ?? []).map(p => {
            const base = p.permissoes ?? []
            const set = permSet(p)
            const dirty = !!permEdits[p.perfil_nome]
            const protegido = p.perfil_nome === 'admin' || p.perfil_nome === 'consulta'
            return (
              <div key={p.perfil_nome} className="bg-panel border border-edge rounded-lg p-4 shadow-sm">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <Badge value={p.perfil_nome} />
                    <span className="text-xs text-dim">{p.descricao}</span>
                  </div>
                  <div className="flex items-center gap-1">
                    <Button size="sm" onClick={() => perfilSave.mutate({ perfil_nome: p.perfil_nome, permissoes: Array.from(set) })} loading={perfilSave.isPending} disabled={!dirty}><Save size={11} /> Salvar</Button>
                    {!protegido && <button onClick={() => setDeletePerfil(p.perfil_nome)} className="text-slate-400 hover:text-red-500 dark:hover:text-red-400 p-1 rounded" title="Excluir perfil"><Trash2 size={13} /></button>}
                  </div>
                </div>
                <div className="flex flex-wrap gap-x-4 gap-y-1.5">
                  {RBAC_RECURSOS_PERFIS.map(([rec, lbl]) => (
                    <label key={rec} className="flex items-center gap-1.5 text-xs text-ink cursor-pointer">
                      <input type="checkbox" checked={set.has(rec)} onChange={() => togglePerm(p.perfil_nome, rec, base)} />
                      {lbl}
                    </label>
                  ))}
                </div>
              </div>
            )
          })}
        </div>
        <div className="bg-panel border border-edge rounded-lg p-4 shadow-sm flex flex-wrap gap-3 items-end">
          <Input label="Novo perfil" value={newPerfil.nome} onChange={e => setNewPerfil(f => ({ ...f, nome: e.target.value.toLowerCase() }))} className="w-40" placeholder="ex: auditor" />
          <Input label="Descrição" value={newPerfil.descricao} onChange={e => setNewPerfil(f => ({ ...f, descricao: e.target.value }))} className="w-56" />
          <Button onClick={() => perfilSave.mutate({ perfil_nome: newPerfil.nome, descricao: newPerfil.descricao, permissoes: [] })} loading={perfilSave.isPending} disabled={!newPerfil.nome.trim()}><Plus size={13} /> Criar Perfil</Button>
        </div>
      </div>

      <ConfirmModal open={!!deletePerfil} title="Excluir Perfil" message={`Excluir o perfil "${deletePerfil}"? Só é possível se nenhum usuário o utiliza.`} danger confirmLabel="Excluir" onConfirm={() => deletePerfil && perfilDelete.mutate(deletePerfil)} onCancel={() => setDeletePerfil(null)} />
    </div>
  )
}
