import { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { apiFetch } from '../lib/api'
import { Button } from '../components/ui/Button'
import { Input, Select } from '../components/ui/Input'
import { Modal } from '../components/ui/Modal'
import { PageSpinner } from '../components/ui/Spinner'
import { toast } from '../components/ui/Toast'
import { Badge } from '../components/ui/Badge'
import type { Job } from '../types'
import { queryClient } from '../lib/queryClient'
import { Edit, Trash2, Plus } from 'lucide-react'
import { useForm } from 'react-hook-form'

const TIPOS = ['python', 'shell', 'sql', 'datastage', 'sensor', 'dummy']

function JobModal({ job, pipeline, onClose }: { job?: Job; pipeline: string; onClose: () => void }) {
  const { register, handleSubmit, watch, formState: { errors } } = useForm<Omit<Job, 'pipeline_name'>>({
    defaultValues: job ?? { job_name: '', ordem: 1, tipo: 'python', job_command: '', ativo: true, verbose_log: false }
  })

  const tipoAtual = watch('tipo')

  const mut = useMutation({
    mutationFn: (data: any) => apiFetch('/pipelines/jobs/register', {
      method: 'POST',
      body: JSON.stringify({ ...data, pipeline_name: pipeline, operacao: job ? 'upsert' : 'upsert' }),
    }),
    onSuccess: () => { toast.success('Job salvo'); queryClient.invalidateQueries({ queryKey: ['jobs'] }); onClose() },
    onError: (e: any) => toast.error(e.message),
  })

  return (
    <Modal open title={job ? `Editar Job: ${job.job_name}` : 'Novo Job'} onClose={onClose}>
      <form onSubmit={handleSubmit((d) => mut.mutate(d))} className="flex flex-col gap-4">
        <Input label="Nome do Job" {...register('job_name', { required: 'Obrigatório' })} error={errors.job_name?.message} />
        <div className="grid grid-cols-2 gap-3">
          <Input label="Ordem" type="number" {...register('ordem', { valueAsNumber: true })} />
          <Select label="Tipo" {...register('tipo')}>
            {TIPOS.map(t => <option key={t}>{t}</option>)}
          </Select>
        </div>
        <Input label="Comando / Path" {...register('job_command')} placeholder="ex: dags.meu_modulo.run" />

        <div className="flex flex-col gap-2">
          <label className="flex items-center gap-2 text-sm text-[#94a3b8]">
            <input type="checkbox" {...register('ativo')} className="accent-blue-500" />
            Ativo
          </label>

          {tipoAtual === 'datastage' && (
            <div className="mt-1 rounded-lg border border-[#2a2d3a] bg-[#12141c] p-3 flex flex-col gap-1">
              <label className="flex items-center gap-2 text-sm text-[#e2e8f0] cursor-pointer select-none">
                <input type="checkbox" {...register('verbose_log')} className="accent-amber-400" />
                <span className="font-medium">Log detalhado durante execução</span>
              </label>
              <p className="text-xs text-[#64748b] pl-5">
                Quando ativo, registra o progresso dos jobs filhos a cada 5 minutos enquanto o job roda.
                Útil para investigar lentidão em jobs do tipo SEQUENCE. Desative após a investigação
                para reduzir o uso de SSH no servidor DataStage.
              </p>
            </div>
          )}
        </div>

        <div className="flex justify-end gap-2 pt-2">
          <Button variant="secondary" type="button" onClick={onClose}>Cancelar</Button>
          <Button type="submit" loading={mut.isPending}>Salvar</Button>
        </div>
      </form>
    </Modal>
  )
}

export default function Jobs() {
  const [pipeline, setPipeline] = useState('')
  const [jobFilter, setJobFilter] = useState('')
  const [searched, setSearched] = useState('')
  const [editJob, setEditJob] = useState<Job | undefined>()
  const [showNew, setShowNew] = useState(false)

  const { data, isLoading } = useQuery<{ jobs: Job[] }>({
    queryKey: ['jobs', searched],
    queryFn: () => apiFetch(`/jobs?limit=200&filter_pipeline=${encodeURIComponent(searched)}`),
    enabled: !!searched,
  })

  const deleteMut = useMutation({
    mutationFn: (job: Job) => apiFetch('/pipelines/jobs/register', {
      method: 'POST',
      body: JSON.stringify({ job_name: job.job_name, pipeline_name: job.pipeline_name, operacao: 'delete' }),
    }),
    onSuccess: () => { toast.success('Job removido'); queryClient.invalidateQueries({ queryKey: ['jobs'] }) },
    onError: (e: any) => toast.error(e.message),
  })

  const jobs = (data?.jobs ?? []).filter(j =>
    !jobFilter || j.job_name.toLowerCase().includes(jobFilter.toLowerCase())
  )

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-lg font-bold text-[#e2e8f0]">Jobs</h1>
      <div className="bg-[#1a1d27] border border-[#2a2d3a] rounded-lg p-4 flex flex-wrap gap-3 items-end">
        <Input label="Pipeline *" value={pipeline} onChange={e => setPipeline(e.target.value)} placeholder="nome exato do pipeline" className="w-64" />
        <Input label="Filtrar job" value={jobFilter} onChange={e => setJobFilter(e.target.value)} placeholder="parte do nome" className="w-44" />
        <Button onClick={() => { setSearched(pipeline) }} disabled={!pipeline}>Buscar</Button>
        {searched && <Button variant="secondary" onClick={() => setShowNew(true)}><Plus size={13} /> Novo Job</Button>}
      </div>

      {!searched && (
        <div className="text-center py-12 text-[#94a3b8] text-sm">Informe um pipeline e clique em Buscar</div>
      )}

      {searched && isLoading && <PageSpinner />}

      {searched && !isLoading && (
        <div className="bg-[#1a1d27] border border-[#2a2d3a] rounded-lg overflow-hidden">
          <div className="px-4 py-2 border-b border-[#2a2d3a] text-xs text-[#94a3b8]">{jobs.length} jobs — Pipeline: <span className="text-[#e2e8f0] font-mono">{searched}</span></div>
          <table className="w-full text-sm">
            <thead><tr className="text-xs text-[#94a3b8] border-b border-[#2a2d3a]">
              <th className="px-4 py-2 text-left">#</th>
              <th className="px-4 py-2 text-left">Job</th>
              <th className="px-4 py-2 text-left">Ordem</th>
              <th className="px-4 py-2 text-left">Tipo</th>
              <th className="px-4 py-2 text-left">Comando</th>
              <th className="px-4 py-2 text-left">Status</th>
              <th className="px-4 py-2 text-left">Log</th>
              <th className="px-4 py-2 text-right">Ações</th>
            </tr></thead>
            <tbody>
              {jobs.map((j, i) => (
                <tr key={j.job_name} className="border-b border-[#2a2d3a]/50 hover:bg-[#2a2d3a]/30">
                  <td className="px-4 py-2 text-[#94a3b8] text-xs">{i + 1}</td>
                  <td className="px-4 py-2 text-[#e2e8f0] font-mono text-xs">{j.job_name}</td>
                  <td className="px-4 py-2 text-[#94a3b8]">{j.ordem}</td>
                  <td className="px-4 py-2"><Badge value={j.tipo} /></td>
                  <td className="px-4 py-2 text-[#94a3b8] font-mono text-xs max-w-xs truncate">{j.job_command}</td>
                  <td className="px-4 py-2"><Badge value={j.ativo ? 'ativo' : 'inativo'} /></td>
                  <td className="px-4 py-2">
                    {j.tipo === 'datastage' && j.verbose_log
                      ? <span className="inline-flex items-center gap-1 text-xs font-medium text-amber-400 bg-amber-400/10 px-2 py-0.5 rounded-full" title="Log detalhado ativo — registra progresso dos jobs filhos a cada 5 min">🔍 detalhado</span>
                      : <span className="text-xs text-[#3d4152]">—</span>
                    }
                  </td>
                  <td className="px-4 py-2 flex justify-end gap-1.5">
                    <Button variant="ghost" size="sm" onClick={() => setEditJob(j)}><Edit size={13} /></Button>
                    <Button variant="ghost" size="sm" onClick={() => { if (confirm(`Remover ${j.job_name}?`)) deleteMut.mutate(j) }}><Trash2 size={13} className="text-red-400" /></Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {(editJob || showNew) && (
        <JobModal
          job={editJob}
          pipeline={searched}
          onClose={() => { setEditJob(undefined); setShowNew(false) }}
        />
      )}
    </div>
  )
}
