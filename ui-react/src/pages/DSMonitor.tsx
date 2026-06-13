import { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { apiFetch } from '../lib/api'
import { Button } from '../components/ui/Button'
import { Input, Select } from '../components/ui/Input'
import { Badge } from '../components/ui/Badge'
import { Card } from '../components/ui/Card'
import { PageSpinner } from '../components/ui/Spinner'
import { toast } from '../components/ui/Toast'
import { Tabs } from '../components/ui/Tabs'
import type { DSStatus } from '../types'
import { format, parseISO } from 'date-fns'
import { RefreshCw } from 'lucide-react'

const PROJETOS_DS = ['BI_CVP', 'BI_VIDA', 'BI_PREVIDENCIA', 'BI_PRESTAMISTA']

function JobMonitor() {
  const [projeto, setProjeto] = useState('')
  const [jobName, setJobName] = useState('')
  const [monitored, setMonitored] = useState<{ projeto: string; job: string } | null>(null)
  const [poll, setPoll] = useState(30)

  const monitorMut = useMutation({
    mutationFn: () => apiFetch('/datastage/monitor', {
      method: 'POST',
      body: JSON.stringify({ projeto, job_name: jobName, poll_interval: poll }),
    }),
    onSuccess: () => { setMonitored({ projeto, job: jobName }); toast.success('Monitoramento iniciado') },
    onError: (e: any) => toast.error(e.message),
  })

  const { data: status, isLoading, refetch } = useQuery<DSStatus>({
    queryKey: ['ds-status', monitored],
    queryFn: () => apiFetch(`/datastage/status?project=${monitored!.projeto}&job_name=${encodeURIComponent(monitored!.job)}`),
    enabled: !!monitored,
    refetchInterval: poll * 1000,
  })

  return (
    <div className="flex flex-col gap-4">
      <div className="bg-[#1a1d27] border border-[#2a2d3a] rounded-lg p-4 flex flex-wrap gap-3 items-end">
        <Select label="Projeto" value={projeto} onChange={e => setProjeto(e.target.value)} className="w-44">
          <option value="">Selecione…</option>
          {PROJETOS_DS.map(p => <option key={p}>{p}</option>)}
        </Select>
        <Input label="Job DataStage" value={jobName} onChange={e => setJobName(e.target.value)} placeholder="ex: J_CARGA_VIDA" className="w-64" />
        <Input label="Poll (s)" type="number" value={poll} onChange={e => setPoll(Number(e.target.value))} className="w-24" min={15} max={300} />
        <Button onClick={() => monitorMut.mutate()} loading={monitorMut.isPending} disabled={!projeto || !jobName}>
          Monitorar
        </Button>
        {monitored && <Button variant="secondary" onClick={() => refetch()}><RefreshCw size={13} /></Button>}
      </div>

      {monitored && (
        isLoading ? <PageSpinner /> : status ? (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <Card title="Status Atual">
              <div className="flex flex-col gap-3">
                <div className="flex items-center gap-3">
                  <Badge value={status.status} />
                  {status.wave != null && <span className="text-xs text-[#94a3b8]">Wave {status.wave}</span>}
                  {status.pid && <span className="text-xs text-[#94a3b8]">PID {status.pid}</span>}
                </div>
                {status.atualizado && <span className="text-xs text-[#94a3b8]">Atualizado: {format(parseISO(status.atualizado), 'HH:mm:ss')}</span>}
              </div>
            </Card>
            {status.filhos && status.filhos.length > 0 && (
              <Card title="Jobs Filhos">
                <table className="w-full text-xs">
                  <thead><tr className="text-[#94a3b8] border-b border-[#2a2d3a]">
                    <th className="py-1 text-left">Job</th>
                    <th className="py-1 text-left">Status</th>
                    <th className="py-1 text-left">Exit</th>
                  </tr></thead>
                  <tbody>
                    {status.filhos.map((f, i) => (
                      <tr key={i} className="border-b border-[#2a2d3a]/40">
                        <td className="py-1 font-mono text-[#e2e8f0]">{f.nome}</td>
                        <td className="py-1"><Badge value={f.status} /></td>
                        <td className="py-1 text-[#94a3b8]">{f.exit_code ?? '-'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </Card>
            )}
            {status.historico && status.historico.length > 0 && (
              <Card title="Histórico de Estados" className="lg:col-span-2">
                <div className="flex flex-col gap-1">
                  {status.historico.map((h, i) => (
                    <div key={i} className="flex items-center gap-3 text-xs">
                      <span className="text-[#94a3b8] w-20 shrink-0">{format(parseISO(h.ts), 'HH:mm:ss')}</span>
                      <Badge value={h.status} />
                    </div>
                  ))}
                </div>
              </Card>
            )}
          </div>
        ) : null
      )}
    </div>
  )
}

function PipelineMonitor() {
  const [projeto, setProjeto] = useState('')
  const [pipeline, setPipeline] = useState('')
  const [loaded, setLoaded] = useState<{ projeto: string; pipeline: string } | null>(null)

  const { data, isLoading, refetch } = useQuery<{ jobs: any[] }>({
    queryKey: ['ds-pipeline', loaded],
    queryFn: () => apiFetch(`/jobs?limit=200&filter_pipeline=${encodeURIComponent(loaded!.pipeline)}`),
    enabled: !!loaded,
  })

  return (
    <div className="flex flex-col gap-4">
      <div className="bg-[#1a1d27] border border-[#2a2d3a] rounded-lg p-4 flex flex-wrap gap-3 items-end">
        <Select label="Projeto" value={projeto} onChange={e => setProjeto(e.target.value)} className="w-44">
          <option value="">Selecione…</option>
          {PROJETOS_DS.map(p => <option key={p}>{p}</option>)}
        </Select>
        <Input label="Pipeline" value={pipeline} onChange={e => setPipeline(e.target.value)} className="w-64" placeholder="nome do pipeline" />
        <Button onClick={() => setLoaded({ projeto, pipeline })} disabled={!projeto || !pipeline}>Carregar</Button>
        {loaded && <Button variant="secondary" onClick={() => refetch()}><RefreshCw size={13} /></Button>}
      </div>

      {loaded && (isLoading ? <PageSpinner /> : (
        <div className="bg-[#1a1d27] border border-[#2a2d3a] rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead><tr className="text-xs text-[#94a3b8] border-b border-[#2a2d3a]">
              <th className="px-4 py-2 text-left">#</th>
              <th className="px-4 py-2 text-left">Job DataStage</th>
              <th className="px-4 py-2 text-left">Tipo</th>
              <th className="px-4 py-2 text-left">Ordem</th>
            </tr></thead>
            <tbody>
              {(data?.jobs ?? []).filter(j => j.tipo === 'datastage').map((j, i) => (
                <tr key={j.job_name} className="border-b border-[#2a2d3a]/50">
                  <td className="px-4 py-2 text-[#94a3b8] text-xs">{i + 1}</td>
                  <td className="px-4 py-2 text-[#e2e8f0] font-mono text-xs">{j.job_name}</td>
                  <td className="px-4 py-2"><Badge value={j.tipo} /></td>
                  <td className="px-4 py-2 text-[#94a3b8]">{j.ordem}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
    </div>
  )
}

export default function DSMonitor() {
  const [tab, setTab] = useState('job')
  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-lg font-bold text-[#e2e8f0]">DS Monitor</h1>
      <Tabs tabs={[{ id: 'job', label: 'Por Job' }, { id: 'pipeline', label: 'Por Pipeline' }]} active={tab} onChange={setTab} />
      {tab === 'job' ? <JobMonitor /> : <PipelineMonitor />}
    </div>
  )
}
