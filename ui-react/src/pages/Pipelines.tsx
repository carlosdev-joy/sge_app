import { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { apiFetch } from '../lib/api'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { Input, Select, Textarea } from '../components/ui/Input'
import { Modal } from '../components/ui/Modal'
import { PageSpinner } from '../components/ui/Spinner'
import { toast } from '../components/ui/Toast'
import type { Pipeline } from '../types'
import { queryClient } from '../lib/queryClient'
import { Plus, Edit, RefreshCw, ChevronLeft, ChevronRight } from 'lucide-react'
import { useForm } from 'react-hook-form'

const PROJETOS = ['BI_CVP', 'BI_VIDA', 'BI_PREVIDENCIA', 'BI_PRESTAMISTA']
const CRITICIDADES = ['ALTA', 'MEDIA', 'BAIXA']
const AMBIENTES = ['PROD', 'HOM', 'DEV']
const FREQUENCIAS = ['daily', 'hourly', 'weekly', 'biweekly', 'monthly', 'custom']

const STEPS = ['Identificação', 'Agendamento', 'Status', 'Configuração', 'Jobs', 'Lineage', 'Revisão']

function PipelineWizard({ pipeline, onClose }: { pipeline?: Pipeline; onClose: () => void }) {
  const [step, setStep] = useState(0)
  const { register, handleSubmit, watch, getValues } = useForm<any>({
    defaultValues: pipeline ?? {
      pipeline_name: '', projeto: 'BI_CVP', dominio: '', criticidade: 'MEDIA',
      ativo: true, frequencia: 'daily', hora: '06:00', ambiente: 'PROD',
      sla_minutos: 60, descricao: '', tags: [],
    }
  })

  const mut = useMutation({
    mutationFn: (data: any) => apiFetch('/pipelines/register', { method: 'POST', body: JSON.stringify(data) }),
    onSuccess: () => { toast.success('Pipeline salvo'); queryClient.invalidateQueries({ queryKey: ['pipelines'] }); onClose() },
    onError: (e: any) => toast.error(e.message),
  })

  watch('pipeline_name')

  const StepContent = () => {
    switch (step) {
      case 0: return (
        <div className="flex flex-col gap-4">
          <Input label="Nome do Pipeline *" {...register('pipeline_name', { required: true })}
            onChange={e => { const v = e.target.value.toUpperCase().replace(/\s/g, '_'); e.target.value = v }}
            placeholder="EX: ETL_CARGA_VIDA" />
          <Select label="Projeto *" {...register('projeto')}>
            {PROJETOS.map(p => <option key={p}>{p}</option>)}
          </Select>
          <Input label="Domínio" {...register('dominio')} placeholder="ex: Vida, Previdência" />
        </div>
      )
      case 1: return (
        <div className="flex flex-col gap-4">
          <Select label="Frequência" {...register('frequencia')}>
            {FREQUENCIAS.map(f => <option key={f}>{f}</option>)}
          </Select>
          <Input label="Hora de início" type="time" {...register('hora')} />
          <Input label="Dependências (pipeline)" {...register('dependencias')} placeholder="outro_pipeline_name" />
          <Input label="Data de início DAG" type="date" {...register('dag_start_date')} />
        </div>
      )
      case 2: return (
        <div className="flex flex-col gap-4">
          <label className="flex items-center gap-2 text-sm text-ink">
            <input type="checkbox" {...register('ativo')} className="accent-blue-500" />
            Pipeline Ativo
          </label>
          <label className="flex items-center gap-2 text-sm text-dim">
            <input type="checkbox" {...register('notif_inicio')} className="accent-blue-500" />
            Notificação ao Iniciar (Teams)
          </label>
          <label className="flex items-center gap-2 text-sm text-dim">
            <input type="checkbox" {...register('notif_fim')} className="accent-blue-500" />
            Notificação ao Concluir (Teams)
          </label>
          <label className="flex items-center gap-2 text-sm text-dim">
            <input type="checkbox" {...register('notif_erro')} className="accent-blue-500" />
            Notificação de Erro (Teams)
          </label>
        </div>
      )
      case 3: return (
        <div className="flex flex-col gap-4">
          <Textarea label="Descrição" {...register('descricao')} rows={3} />
          <div className="grid grid-cols-2 gap-3">
            <Select label="Criticidade" {...register('criticidade')}>
              {CRITICIDADES.map(c => <option key={c}>{c}</option>)}
            </Select>
            <Select label="Ambiente" {...register('ambiente')}>
              {AMBIENTES.map(a => <option key={a}>{a}</option>)}
            </Select>
          </div>
          <div className="grid grid-cols-3 gap-3">
            <Input label="SLA (min)" type="number" {...register('sla_minutos', { valueAsNumber: true })} />
            <Input label="Max runs" type="number" {...register('max_active_runs', { valueAsNumber: true })} />
            <Input label="Retries" type="number" {...register('retries', { valueAsNumber: true })} />
          </div>
          <Input label="Pool Airflow" {...register('pool')} placeholder="default_pool" />
        </div>
      )
      case 4: return (
        <div className="text-sm text-dim">
          Jobs serão configurados após salvar o pipeline, na aba <span className="text-blue-400">Jobs</span>.
        </div>
      )
      case 5: return (
        <div className="text-sm text-dim">
          Lineage será configurado por job na aba <span className="text-blue-400">Governança</span>.
        </div>
      )
      case 6: {
        const vals = getValues()
        return (
          <div className="flex flex-col gap-3 text-sm">
            <div className="bg-canvas rounded-lg p-4 flex flex-col gap-2">
              {Object.entries(vals).filter(([,v]) => v !== '' && v !== null && v !== undefined).map(([k, v]) => (
                <div key={k} className="flex gap-3">
                  <span className="text-dim w-36 shrink-0 text-xs">{k}</span>
                  <span className="text-ink text-xs font-mono">{String(v)}</span>
                </div>
              ))}
            </div>
          </div>
        )
      }
      default: return null
    }
  }

  return (
    <Modal open title={pipeline ? `Editar: ${pipeline.pipeline_name}` : 'Novo Pipeline'} onClose={onClose} size="lg">
      {/* Stepper */}
      <div className="flex gap-1 mb-6 overflow-x-auto pb-1">
        {STEPS.map((s, i) => (
          <button key={i} onClick={() => setStep(i)}
            className={`px-2.5 py-1 rounded text-xs font-medium whitespace-nowrap transition-colors ${i === step ? 'bg-blue-600 text-white' : i < step ? 'bg-green-900/50 text-green-400' : 'bg-edge text-dim'}`}>
            {i + 1}. {s}
          </button>
        ))}
      </div>

      <div className="min-h-[200px]"><StepContent /></div>

      <div className="flex justify-between mt-6 pt-4 border-t border-edge">
        <Button variant="secondary" onClick={() => setStep(s => s - 1)} disabled={step === 0}>
          <ChevronLeft size={13} /> Anterior
        </Button>
        {step < STEPS.length - 1 ? (
          <Button onClick={() => setStep(s => s + 1)}>Próximo <ChevronRight size={13} /></Button>
        ) : (
          <Button onClick={handleSubmit(d => mut.mutate(d))} loading={mut.isPending}>Salvar Pipeline</Button>
        )}
      </div>
    </Modal>
  )
}

export default function Pipelines() {
  const [filters, setFilters] = useState({ nome: '', projeto: '', status: '' })
  const [editPipeline, setEditPipeline] = useState<Pipeline | undefined>()
  const [showNew, setShowNew] = useState(false)
  const [page, setPage] = useState(0)
  const LIMIT = 50

  const q = new URLSearchParams({ limit: String(LIMIT), offset: String(page * LIMIT) })
  if (filters.nome) q.set('nome', filters.nome)
  if (filters.projeto) q.set('projeto', filters.projeto)
  if (filters.status) q.set('ativo', filters.status === 'Ativo' ? 'true' : 'false')

  const { data, isLoading, refetch } = useQuery<{ pipelines: Pipeline[]; total: number }>({
    queryKey: ['pipelines', filters, page],
    queryFn: () => apiFetch(`/pipelines?${q}`),
  })

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap gap-3 items-end">
        <h1 className="text-lg font-bold text-ink">Pipelines</h1>
        <Input value={filters.nome} onChange={e => setFilters(f => ({ ...f, nome: e.target.value }))} placeholder="Buscar por nome…" className="w-52" />
        <Select value={filters.projeto} onChange={e => setFilters(f => ({ ...f, projeto: e.target.value }))} className="w-44">
          <option value="">Todos projetos</option>
          {PROJETOS.map(p => <option key={p}>{p}</option>)}
        </Select>
        <Select value={filters.status} onChange={e => setFilters(f => ({ ...f, status: e.target.value }))} className="w-32">
          <option value="">Todos</option><option>Ativo</option><option>Inativo</option>
        </Select>
        <Button variant="secondary" size="sm" onClick={() => refetch()}><RefreshCw size={13} /></Button>
        <Button size="sm" onClick={() => setShowNew(true)} className="ml-auto"><Plus size={13} /> Novo Pipeline</Button>
      </div>

      {isLoading ? <PageSpinner /> : (
        <div className="bg-panel border border-edge rounded-lg overflow-hidden">
          <div className="px-4 py-2 border-b border-edge text-xs text-dim">{data?.total ?? 0} pipelines</div>
          <table className="w-full text-sm">
            <thead><tr className="text-xs text-dim border-b border-edge">
              <th className="px-4 py-2 text-left">Pipeline</th>
              <th className="px-4 py-2 text-left">Projeto</th>
              <th className="px-4 py-2 text-left">Domínio</th>
              <th className="px-4 py-2 text-left">Criticidade</th>
              <th className="px-4 py-2 text-left">Status</th>
              <th className="px-4 py-2 text-left">Schedule</th>
              <th className="px-4 py-2 text-left">Jobs</th>
              <th className="px-4 py-2 text-left">SLA</th>
              <th className="px-4 py-2 text-right">Ações</th>
            </tr></thead>
            <tbody>
              {(data?.pipelines ?? []).map((p) => (
                <tr key={p.pipeline_name} className="border-b border-edge/50 hover:bg-edge/30">
                  <td className="px-4 py-2 text-ink font-mono text-xs">{p.pipeline_name}</td>
                  <td className="px-4 py-2 text-dim">{p.projeto}</td>
                  <td className="px-4 py-2 text-dim">{p.dominio}</td>
                  <td className="px-4 py-2">{p.criticidade && <Badge value={p.criticidade} />}</td>
                  <td className="px-4 py-2"><Badge value={p.ativo ? 'ativo' : 'inativo'} /></td>
                  <td className="px-4 py-2 text-dim font-mono text-xs">{p.schedule}</td>
                  <td className="px-4 py-2 text-dim">{p.job_count ?? '-'}</td>
                  <td className="px-4 py-2 text-dim">{p.sla_minutos ? `${p.sla_minutos}m` : '-'}</td>
                  <td className="px-4 py-2 text-right">
                    <Button variant="ghost" size="sm" onClick={() => setEditPipeline(p)}><Edit size={13} /></Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="px-4 py-2 flex items-center gap-2 border-t border-edge">
            <Button variant="ghost" size="sm" disabled={page === 0} onClick={() => setPage(p => p - 1)}>← Anterior</Button>
            <span className="text-xs text-dim">Pág. {page + 1}</span>
            <Button variant="ghost" size="sm" disabled={(data?.pipelines?.length ?? 0) < LIMIT} onClick={() => setPage(p => p + 1)}>Próxima →</Button>
          </div>
        </div>
      )}

      {(showNew || editPipeline) && (
        <PipelineWizard pipeline={editPipeline} onClose={() => { setShowNew(false); setEditPipeline(undefined) }} />
      )}
    </div>
  )
}
