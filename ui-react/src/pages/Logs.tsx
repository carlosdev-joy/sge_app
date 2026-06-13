import { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { apiFetch } from '../lib/api'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { Input, Select } from '../components/ui/Input'
import { Modal } from '../components/ui/Modal'
import { PageSpinner } from '../components/ui/Spinner'
import { toast } from '../components/ui/Toast'
import type { Execucao, FactoryRun } from '../types'
import { format, parseISO, subDays } from 'date-fns'
import { RefreshCw, RotateCcw, CheckSquare, FileText, ChevronDown, ChevronUp } from 'lucide-react'
import { Tabs } from '../components/ui/Tabs'
import { queryClient } from '../lib/queryClient'

const PROJETOS = ['', 'BI_CVP', 'BI_VIDA', 'BI_PREVIDENCIA', 'BI_PRESTAMISTA']
const STATUS_OPTS = ['', 'SUCCESS', 'FAILED', 'WARNING', 'RUNNING']

function durStr(s?: number) {
  if (!s) return '-'
  const m = Math.floor(s / 60), sec = s % 60
  return m > 0 ? `${m}m ${sec}s` : `${sec}s`
}

function ExecDetail({ execId, onClose }: { execId: string; onClose: () => void }) {
  const { data, isLoading } = useQuery({
    queryKey: ['exec', execId],
    queryFn: () => apiFetch<any>(`/execucoes?execution_id=${execId}&limit=1`),
  })
  return (
    <Modal open title={`Execução ${execId}`} onClose={onClose} size="xl">
      {isLoading ? <PageSpinner /> : (
        <pre className="text-xs text-[#94a3b8] bg-[#0f1117] rounded p-3 overflow-auto max-h-96">
          {JSON.stringify(data, null, 2)}
        </pre>
      )}
    </Modal>
  )
}

function FactoryRuns() {
  const [expanded, setExpanded] = useState<string | null>(null)
  const { data, isLoading } = useQuery<{ runs: FactoryRun[] }>({
    queryKey: ['factory-runs'],
    queryFn: () => apiFetch('/factory/runs?limit=20'),
  })
  const { data: log } = useQuery<{ log: string }>({
    queryKey: ['factory-log', expanded],
    queryFn: () => apiFetch(`/factory/runs/${expanded}/log?raw=true`),
    enabled: !!expanded,
  })
  if (isLoading) return <PageSpinner />
  return (
    <div className="flex flex-col gap-2">
      {(data?.runs ?? []).map((r) => (
        <div key={r.dag_run_id} className="bg-[#1a1d27] border border-[#2a2d3a] rounded-lg overflow-hidden">
          <button
            className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-[#2a2d3a]/30 transition-colors"
            onClick={() => setExpanded(expanded === r.dag_run_id ? null : r.dag_run_id)}
          >
            <Badge value={r.status} />
            <span className="text-xs text-[#e2e8f0] font-mono flex-1">{r.dag_run_id}</span>
            <span className="text-xs text-[#94a3b8]">{r.inicio ? format(parseISO(r.inicio), 'dd/MM HH:mm') : '-'}</span>
            {expanded === r.dag_run_id ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          </button>
          {expanded === r.dag_run_id && log && (
            <pre className="text-xs text-[#94a3b8] bg-[#0f1117] p-4 overflow-auto max-h-80">{log.log}</pre>
          )}
        </div>
      ))}
    </div>
  )
}

export default function Logs() {
  const [tab, setTab] = useState('execucoes')
  const [filters, setFilters] = useState({ projeto: '', pipeline: '', status: '', data_ini: '', exec_id: '' })
  const [page, setPage] = useState(0)
  const [detail, setDetail] = useState<string | null>(null)
  const LIMIT = 50

  const q = new URLSearchParams({ limit: String(LIMIT), offset: String(page * LIMIT) })
  if (filters.projeto) q.set('projeto', filters.projeto)
  if (filters.pipeline) q.set('pipeline', filters.pipeline)
  if (filters.status) q.set('status', filters.status)
  if (filters.data_ini) q.set('data_ini', filters.data_ini)
  if (filters.exec_id) q.set('execution_id', filters.exec_id)

  const { data, isLoading, refetch } = useQuery<{ execucoes: Execucao[]; total: number }>({
    queryKey: ['execucoes', filters, page],
    queryFn: () => apiFetch(`/execucoes?${q}`),
    enabled: tab === 'execucoes',
  })

  const rerunMut = useMutation({
    mutationFn: (execution_id: string) => apiFetch('/execucoes/rerun', { method: 'POST', body: JSON.stringify({ execution_id }) }),
    onSuccess: () => { toast.success('Reexecução disparada'); queryClient.invalidateQueries({ queryKey: ['execucoes'] }) },
    onError: (e: any) => toast.error(e.message),
  })
  const ackMut = useMutation({
    mutationFn: (execution_id: string) => apiFetch('/execucoes/ack', { method: 'POST', body: JSON.stringify({ execution_id }) }),
    onSuccess: () => { toast.success('Falha reconhecida'); queryClient.invalidateQueries({ queryKey: ['execucoes'] }) },
    onError: (e: any) => toast.error(e.message),
  })

  const setQuick = (days: number, status = 'FAILED') => {
    setFilters(f => ({ ...f, status, data_ini: format(subDays(new Date(), days), 'yyyy-MM-dd') }))
    setPage(0)
  }

  return (
    <div className="flex flex-col gap-4">
      <Tabs
        tabs={[{ id: 'execucoes', label: 'Execuções' }, { id: 'factory', label: 'Regeneração de DAGs' }]}
        active={tab} onChange={setTab}
      />

      {tab === 'execucoes' && (
        <>
          {/* Filters */}
          <div className="bg-[#1a1d27] border border-[#2a2d3a] rounded-lg p-4 flex flex-wrap gap-3 items-end">
            <Select label="Projeto" value={filters.projeto} onChange={(e) => setFilters(f => ({ ...f, projeto: e.target.value }))} className="w-44">
              <option value="">Todos</option>
              {PROJETOS.filter(Boolean).map(p => <option key={p}>{p}</option>)}
            </Select>
            <Input label="Pipeline" value={filters.pipeline} onChange={(e) => setFilters(f => ({ ...f, pipeline: e.target.value }))} placeholder="nome do pipeline" className="w-52" />
            <Select label="Status" value={filters.status} onChange={(e) => setFilters(f => ({ ...f, status: e.target.value }))} className="w-36">
              <option value="">Todos</option>
              {STATUS_OPTS.filter(Boolean).map(s => <option key={s}>{s}</option>)}
            </Select>
            <Input label="Data (a partir de)" type="date" value={filters.data_ini} onChange={(e) => setFilters(f => ({ ...f, data_ini: e.target.value }))} className="w-44" />
            <Input label="Execution ID" value={filters.exec_id} onChange={(e) => setFilters(f => ({ ...f, exec_id: e.target.value }))} placeholder="exec-..." className="w-52" />
            <div className="flex gap-2 ml-auto flex-wrap">
              <Button variant="secondary" size="sm" onClick={() => setQuick(1)}>Falhas 24h</Button>
              <Button variant="secondary" size="sm" onClick={() => setQuick(7)}>Falhas semana</Button>
              <Button variant="secondary" size="sm" onClick={() => { setFilters({ projeto:'',pipeline:'',status:'',data_ini:'',exec_id:'' }); setPage(0) }}>Limpar</Button>
              <Button size="sm" onClick={() => { setPage(0); refetch() }}><RefreshCw size={13} /></Button>
            </div>
          </div>

          {isLoading ? <PageSpinner /> : (
            <div className="bg-[#1a1d27] border border-[#2a2d3a] rounded-lg overflow-hidden">
              <div className="px-4 py-2 border-b border-[#2a2d3a] text-xs text-[#94a3b8]">
                {data?.total ?? 0} resultados
              </div>
              <table className="w-full text-sm">
                <thead><tr className="text-xs text-[#94a3b8] border-b border-[#2a2d3a]">
                  <th className="px-4 py-2 text-left">Execution ID</th>
                  <th className="px-4 py-2 text-left">Pipeline</th>
                  <th className="px-4 py-2 text-left">Projeto</th>
                  <th className="px-4 py-2 text-left">Status</th>
                  <th className="px-4 py-2 text-left">Duração</th>
                  <th className="px-4 py-2 text-left">Início</th>
                  <th className="px-4 py-2 text-right">Ações</th>
                </tr></thead>
                <tbody>
                  {(data?.execucoes ?? []).map((e) => (
                    <tr key={e.execution_id} className="border-b border-[#2a2d3a]/50 hover:bg-[#2a2d3a]/30">
                      <td className="px-4 py-2 font-mono text-xs text-blue-400 cursor-pointer hover:underline" onClick={() => setDetail(e.execution_id)}>
                        {e.execution_id.slice(0, 24)}…
                      </td>
                      <td className="px-4 py-2 text-[#e2e8f0] text-xs font-mono">{e.pipeline_name}</td>
                      <td className="px-4 py-2 text-[#94a3b8]">{e.projeto}</td>
                      <td className="px-4 py-2"><Badge value={e.status} /></td>
                      <td className="px-4 py-2 text-[#94a3b8]">{durStr(e.duracao_segundos)}</td>
                      <td className="px-4 py-2 text-[#94a3b8] text-xs">{e.inicio ? format(parseISO(e.inicio), 'dd/MM HH:mm:ss') : '-'}</td>
                      <td className="px-4 py-2 text-right flex justify-end gap-1.5">
                        <Button variant="ghost" size="sm" title="Detalhes" onClick={() => setDetail(e.execution_id)}><FileText size={13} /></Button>
                        {e.status === 'FAILED' && <>
                          <Button variant="ghost" size="sm" title="Reexecutar" onClick={() => rerunMut.mutate(e.execution_id)}><RotateCcw size={13} /></Button>
                          {!e.ack && <Button variant="ghost" size="sm" title="Acknowledge" onClick={() => ackMut.mutate(e.execution_id)}><CheckSquare size={13} /></Button>}
                        </>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {/* Pagination */}
              <div className="px-4 py-2 flex items-center gap-2 border-t border-[#2a2d3a]">
                <Button variant="ghost" size="sm" disabled={page === 0} onClick={() => setPage(p => p - 1)}>← Anterior</Button>
                <span className="text-xs text-[#94a3b8]">Página {page + 1}</span>
                <Button variant="ghost" size="sm" disabled={(data?.execucoes?.length ?? 0) < LIMIT} onClick={() => setPage(p => p + 1)}>Próxima →</Button>
              </div>
            </div>
          )}
        </>
      )}

      {tab === 'factory' && <FactoryRuns />}

      {detail && <ExecDetail execId={detail} onClose={() => setDetail(null)} />}
    </div>
  )
}
