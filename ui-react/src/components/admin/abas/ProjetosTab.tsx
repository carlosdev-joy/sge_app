import { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { apiFetch } from '../../../lib/api'
import { Button } from '../../ui/Button'
import { Input } from '../../ui/Input'
import { Badge } from '../../ui/Badge'
import { toast } from '../../ui/Toast'
import { queryClient } from '../../../lib/queryClient'
import { ConfirmModal } from '../ComumUI'
import { Trash2, Plus, X, CheckCircle2 } from 'lucide-react'

// ── Projetos ────────────────────────────────────────────────────
interface ProjectRow { project_name: string; ativo: boolean }

export function ProjetosTab() {
  const [newName, setNewName] = useState('')
  const [delProject, setDelProject] = useState<string | null>(null)

  const { data, isLoading } = useQuery<{ projects: ProjectRow[] }>({
    queryKey: ['admin-projects-all'],
    queryFn: () => apiFetch('/pipelines/projects/all'),
  })

  const upsert = useMutation({
    mutationFn: (p: { project_name: string; ativo: number }) =>
      apiFetch('/pipelines/projects', { method: 'POST', body: JSON.stringify(p) }),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['admin-projects-all'] }); queryClient.invalidateQueries({ queryKey: ['pipeline-projects'] }); setNewName('') },
    onError: (e: any) => toast.error(e.message),
  })

  const del = useMutation({
    mutationFn: (name: string) => apiFetch(`/pipelines/projects/${encodeURIComponent(name)}`, { method: 'DELETE' }),
    onSuccess: () => { toast.success('Projeto excluído'); queryClient.invalidateQueries({ queryKey: ['admin-projects-all'] }); queryClient.invalidateQueries({ queryKey: ['pipeline-projects'] }); setDelProject(null) },
    onError: (e: any) => toast.error(e.message),
  })

  const projects = data?.projects ?? []

  return (
    <div className="flex flex-col gap-4">
      <div className="bg-panel border border-edge rounded-lg p-4 shadow-sm">
        <h3 className="text-sm font-semibold text-ink mb-1">Projetos cadastrados</h3>
        <p className="text-xs text-dim mb-3">Projetos disponíveis em todas as telas de cadastro (Pipelines, Jobs, etc.). Inative para ocultar sem excluir.</p>

        {isLoading && <p className="text-xs text-dim">Carregando...</p>}
        {!isLoading && projects.length === 0 && <p className="text-xs text-dim">Nenhum projeto cadastrado.</p>}

        <div className="flex flex-col gap-1 mb-4">
          {projects.map(p => (
            <div key={p.project_name} className="flex items-center gap-3 py-2 px-3 rounded-md hover:bg-edge/30 text-sm border-b border-edge/40 last:border-0">
              <span className={`font-mono font-medium ${p.ativo ? 'text-ink' : 'text-dim line-through'}`}>{p.project_name}</span>
              <Badge value={p.ativo ? 'success' : 'neutral'}>{p.ativo ? 'ativo' : 'inativo'}</Badge>
              <div className="ml-auto flex items-center gap-1">
                {p.ativo ? (
                  <button
                    onClick={() => upsert.mutate({ project_name: p.project_name, ativo: 0 })}
                    title="Inativar"
                    className="text-slate-400 hover:text-amber-500 p-1 rounded text-xs"
                  >
                    <X size={13} />
                  </button>
                ) : (
                  <button
                    onClick={() => upsert.mutate({ project_name: p.project_name, ativo: 1 })}
                    title="Reativar"
                    className="text-slate-400 hover:text-green-500 p-1 rounded text-xs"
                  >
                    <CheckCircle2 size={13} />
                  </button>
                )}
                <button
                  onClick={() => setDelProject(p.project_name)}
                  title="Excluir"
                  className="text-slate-400 hover:text-red-500 p-1 rounded"
                >
                  <Trash2 size={13} />
                </button>
              </div>
            </div>
          ))}
        </div>

        <div className="flex flex-wrap gap-3 items-end border-t border-edge pt-3">
          <Input
            label="Nome do Projeto"
            value={newName}
            onChange={e => setNewName(e.target.value.toUpperCase())}
            placeholder="ex: BI_CVP"
            className="w-48"
          />
          <Button
            onClick={() => upsert.mutate({ project_name: newName.trim(), ativo: 1 })}
            loading={upsert.isPending}
            disabled={!newName.trim()}
          >
            <Plus size={13} /> Adicionar Projeto
          </Button>
        </div>
      </div>

      <ConfirmModal
        open={!!delProject}
        title="Excluir Projeto"
        message={`Excluir o projeto "${delProject}"? Só é possível se não houver pipelines vinculados. Para ocultar, prefira inativar.`}
        danger
        confirmLabel="Excluir"
        onConfirm={() => delProject && del.mutate(delProject)}
        onCancel={() => setDelProject(null)}
      />
    </div>
  )
}
