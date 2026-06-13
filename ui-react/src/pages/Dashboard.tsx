import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '../lib/api'
import { KpiCard } from '../components/ui/Card'
import { Badge } from '../components/ui/Badge'
import { PageSpinner } from '../components/ui/Spinner'
import { Select } from '../components/ui/Input'
import { Button } from '../components/ui/Button'
import { RefreshCw } from 'lucide-react'
import type { DashboardData, GanttItem } from '../types'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts'
import { format, parseISO } from 'date-fns'

const PROJETOS = ['Todos', 'BI_CVP', 'BI_VIDA', 'BI_PREVIDENCIA', 'BI_PRESTAMISTA']
const STATUS_COLOR: Record<string, string> = {
  SUCCESS: '#22c55e', FAILED: '#ef4444', WARNING: '#f59e0b', RUNNING: '#4f8ef7', PENDING: '#6b7280'
}

function GanttChart({ items }: { items: GanttItem[] }) {
  const data = items.slice(0, 30).map((it) => ({
    name: it.pipeline_name.length > 22 ? it.pipeline_name.slice(0, 22) + '…' : it.pipeline_name,
    dur: it.duracao_segundos ?? 60,
    status: it.status,
  }))
  return (
    <ResponsiveContainer width="100%" height={Math.max(200, data.length * 28)}>
      <BarChart data={data} layout="vertical" margin={{ left: 160, right: 20, top: 4, bottom: 4 }}>
        <XAxis type="number" tick={{ fill: '#94a3b8', fontSize: 11 }} tickFormatter={(v) => `${Math.round(v / 60)}m`} />
        <YAxis type="category" dataKey="name" tick={{ fill: '#94a3b8', fontSize: 11 }} width={160} />
        <Tooltip
          contentStyle={{ background: '#1a1d27', border: '1px solid #2a2d3a', borderRadius: 6 }}
          labelStyle={{ color: '#e2e8f0' }}
          formatter={(v: any) => [`${Math.round(Number(v) / 60)} min`, 'Duração']}
        />
        <Bar dataKey="dur" radius={2}>
          {data.map((d, i) => <Cell key={i} fill={STATUS_COLOR[d.status] ?? '#6b7280'} />)}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}

export default function Dashboard() {
  const [projeto, setProjeto] = useState('Todos')
  const [date, setDate] = useState(format(new Date(), 'yyyy-MM-dd'))
  const [autoRefresh, setAutoRefresh] = useState(false)

  const params = new URLSearchParams()
  if (projeto !== 'Todos') params.set('projeto', projeto)
  params.set('data_ref', date)

  const { data, isLoading, refetch } = useQuery<DashboardData>({
    queryKey: ['dashboard', projeto, date],
    queryFn: () => apiFetch(`/dashboard?${params}`),
    refetchInterval: autoRefresh ? 60_000 : false,
  })

  const { data: gantt } = useQuery<{ items: GanttItem[] }>({
    queryKey: ['gantt', projeto, date],
    queryFn: () => apiFetch(`/dashboard/gantt?${params}`),
    refetchInterval: autoRefresh ? 60_000 : false,
  })

  return (
    <div className="flex flex-col gap-6">
      {/* Toolbar */}
      <div className="flex items-center gap-3 flex-wrap">
        <h1 className="text-lg font-bold text-[#e2e8f0] mr-2">Dashboard</h1>
        <Select value={projeto} onChange={(e) => setProjeto(e.target.value)} className="w-44">
          {PROJETOS.map((p) => <option key={p}>{p}</option>)}
        </Select>
        <input
          type="date"
          value={date}
          onChange={(e) => setDate(e.target.value)}
          className="bg-[#1a1d27] border border-[#2a2d3a] text-[#e2e8f0] rounded-md px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
        />
        <label className="flex items-center gap-2 text-xs text-[#94a3b8] cursor-pointer">
          <input type="checkbox" checked={autoRefresh} onChange={(e) => setAutoRefresh(e.target.checked)} className="accent-blue-500" />
          Auto-refresh (1min)
        </label>
        <Button variant="secondary" size="sm" onClick={() => refetch()} className="ml-auto">
          <RefreshCw size={13} /> Atualizar
        </Button>
      </div>

      {isLoading ? <PageSpinner /> : data && (
        <>
          {/* KPIs */}
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-7 gap-3">
            <KpiCard label="Total" value={data.total} color="blue" />
            <KpiCard label="Sucesso %" value={`${data.taxa_sucesso?.toFixed(1) ?? 0}%`} color="green" />
            <KpiCard label="Falhas" value={data.falha} color="red" />
            <KpiCard label="Avisos" value={data.aviso} color="yellow" />
            <KpiCard label="Rodando" value={data.rodando} color="blue" />
            <KpiCard label="Críticas" value={data.falhas_criticas} color="red" />
            <KpiCard label="Fila DS" value={data.fila_datastage ?? 0} color="purple" />
          </div>

          {/* Gantt */}
          {gantt?.items && gantt.items.length > 0 && (
            <div className="bg-[#1a1d27] border border-[#2a2d3a] rounded-lg p-4">
              <h3 className="text-sm font-semibold text-[#e2e8f0] mb-3">Linha do Tempo</h3>
              <GanttChart items={gantt.items} />
            </div>
          )}

          {/* Failures */}
          {data.falhas && data.falhas.length > 0 && (
            <div className="bg-[#1a1d27] border border-[#2a2d3a] rounded-lg overflow-hidden">
              <div className="px-4 py-3 border-b border-[#2a2d3a]">
                <h3 className="text-sm font-semibold text-red-400">Falhas Recentes ({data.falhas.length})</h3>
              </div>
              <table className="w-full text-sm">
                <thead><tr className="text-xs text-[#94a3b8] border-b border-[#2a2d3a]">
                  <th className="px-4 py-2 text-left">Pipeline</th>
                  <th className="px-4 py-2 text-left">Projeto</th>
                  <th className="px-4 py-2 text-left">Status</th>
                  <th className="px-4 py-2 text-left">Início</th>
                </tr></thead>
                <tbody>
                  {data.falhas.slice(0, 10).map((f) => (
                    <tr key={f.execution_id} className="border-b border-[#2a2d3a]/50 hover:bg-[#2a2d3a]/30">
                      <td className="px-4 py-2 text-[#e2e8f0] font-mono text-xs">{f.pipeline_name}</td>
                      <td className="px-4 py-2 text-[#94a3b8]">{f.projeto}</td>
                      <td className="px-4 py-2"><Badge value={f.status} /></td>
                      <td className="px-4 py-2 text-[#94a3b8] text-xs">{f.inicio ? format(parseISO(f.inicio), 'HH:mm:ss') : '-'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Pipeline Status Table */}
          {data.pipelines && data.pipelines.length > 0 && (
            <div className="bg-[#1a1d27] border border-[#2a2d3a] rounded-lg overflow-hidden">
              <div className="px-4 py-3 border-b border-[#2a2d3a]">
                <h3 className="text-sm font-semibold text-[#e2e8f0]">Status por Pipeline</h3>
              </div>
              <table className="w-full text-sm">
                <thead><tr className="text-xs text-[#94a3b8] border-b border-[#2a2d3a]">
                  <th className="px-4 py-2 text-left">Pipeline</th>
                  <th className="px-4 py-2 text-left">Projeto</th>
                  <th className="px-4 py-2 text-left">Status</th>
                  <th className="px-4 py-2 text-left">Criticidade</th>
                  <th className="px-4 py-2 text-left">Última Exec.</th>
                </tr></thead>
                <tbody>
                  {data.pipelines.map((p) => (
                    <tr key={p.pipeline_name} className="border-b border-[#2a2d3a]/50 hover:bg-[#2a2d3a]/30">
                      <td className="px-4 py-2 text-[#e2e8f0] font-mono text-xs">{p.pipeline_name}</td>
                      <td className="px-4 py-2 text-[#94a3b8]">{p.projeto}</td>
                      <td className="px-4 py-2"><Badge value={p.status} /></td>
                      <td className="px-4 py-2">{p.criticidade && <Badge value={p.criticidade} />}</td>
                      <td className="px-4 py-2 text-[#94a3b8] text-xs">{p.ultima_execucao ? format(parseISO(p.ultima_execucao), 'dd/MM HH:mm') : '-'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  )
}
