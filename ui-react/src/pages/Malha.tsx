import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '../lib/api'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { Input, Select } from '../components/ui/Input'
import { PageSpinner } from '../components/ui/Spinner'
import type { MalhaItem } from '../types'
import { ChevronDown, ChevronUp, RefreshCw, LayoutGrid, Network } from 'lucide-react'
import { ReactFlow, Background, Controls, MiniMap } from '@xyflow/react'
import type { Node, Edge } from '@xyflow/react'
import '@xyflow/react/dist/style.css'

const PROJETOS = ['Todos', 'BI_CVP', 'BI_VIDA', 'BI_PREVIDENCIA', 'BI_PRESTAMISTA']
const CRIT = ['Todos', 'ALTA', 'MEDIA', 'BAIXA']

function PipelineCard({ item }: { item: MalhaItem }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="bg-[#1a1d27] border border-[#2a2d3a] rounded-lg overflow-hidden">
      <div className="px-4 py-3 flex items-center gap-3 cursor-pointer hover:bg-[#2a2d3a]/30" onClick={() => setOpen(o => !o)}>
        <div className={`w-2 h-2 rounded-full shrink-0 ${item.ativo ? 'bg-green-400' : 'bg-gray-500'}`} />
        <span className="font-mono text-sm text-[#e2e8f0] flex-1">{item.pipeline_name}</span>
        {item.criticidade && <Badge value={item.criticidade} />}
        {item.sla_minutos && <span className="text-xs text-[#94a3b8]">SLA {item.sla_minutos}m</span>}
        <span className="text-xs text-[#94a3b8]">{item.jobs.length} jobs</span>
        {item.schedule && <span className="text-xs text-[#94a3b8] font-mono">{item.schedule}</span>}
        {open ? <ChevronUp size={14} className="text-[#94a3b8]" /> : <ChevronDown size={14} className="text-[#94a3b8]" />}
      </div>
      {open && (
        <div className="px-4 pb-4 pt-1 border-t border-[#2a2d3a]">
          <div className="flex flex-wrap gap-2 mt-2">
            {item.jobs.sort((a, b) => a.ordem - b.ordem).map((j) => (
              <div key={j.job_name} className="flex items-center gap-1.5 bg-[#0f1117] border border-[#2a2d3a] rounded px-2 py-1">
                <span className="text-xs text-[#94a3b8]">{j.ordem}.</span>
                <span className="font-mono text-xs text-[#e2e8f0]">{j.job_name}</span>
                <Badge value={j.tipo} />
              </div>
            ))}
          </div>
          {item.dependencias && item.dependencias.length > 0 && (
            <div className="mt-3 text-xs text-[#94a3b8]">
              Depende de: {item.dependencias.map(d => <span key={d} className="font-mono text-blue-400 ml-1">{d}</span>)}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function DiagramView({ items }: { items: MalhaItem[] }) {
  const nodes: Node[] = items.map((it, i) => ({
    id: it.pipeline_name,
    data: { label: it.pipeline_name },
    position: { x: (i % 5) * 220, y: Math.floor(i / 5) * 100 },
    style: {
      background: '#1a1d27', border: '1px solid #2a2d3a', color: '#e2e8f0',
      borderRadius: 6, fontSize: 11, padding: 8,
    },
  }))

  const edges: Edge[] = items.flatMap((it) =>
    (it.dependencias ?? []).map((dep) => ({
      id: `${dep}->${it.pipeline_name}`,
      source: dep,
      target: it.pipeline_name,
      style: { stroke: '#4f8ef7' },
      animated: false,
    }))
  )

  return (
    <div style={{ height: 600 }}>
      <ReactFlow nodes={nodes} edges={edges} fitView>
        <Background color="#2a2d3a" />
        <Controls />
        <MiniMap style={{ background: '#0f1117' }} />
      </ReactFlow>
    </div>
  )
}

export default function Malha() {
  const [view, setView] = useState<'cards' | 'diagram'>('cards')
  const [search, setSearch] = useState('')
  const [projeto, setProjeto] = useState('Todos')
  const [crit, setCrit] = useState('Todos')
  const [status, setStatus] = useState('Todos')

  const { data, isLoading, refetch } = useQuery<{ pipelines: MalhaItem[] }>({
    queryKey: ['malha'],
    queryFn: () => apiFetch('/malha'),
    staleTime: 60_000,
  })

  const filtered = useMemo(() => {
    let items = data?.pipelines ?? []
    if (search) items = items.filter(p => p.pipeline_name.toLowerCase().includes(search.toLowerCase()))
    if (projeto !== 'Todos') items = items.filter(p => p.projeto === projeto)
    if (crit !== 'Todos') items = items.filter(p => p.criticidade === crit)
    if (status === 'Ativos') items = items.filter(p => p.ativo)
    if (status === 'Inativos') items = items.filter(p => !p.ativo)
    return items
  }, [data, search, projeto, crit, status])

  const byProject = useMemo(() => {
    const map = new Map<string, MalhaItem[]>()
    for (const p of filtered) {
      const g = map.get(p.projeto) ?? []
      g.push(p)
      map.set(p.projeto, g)
    }
    return map
  }, [filtered])

  const total = data?.pipelines?.length ?? 0
  const ativos = (data?.pipelines ?? []).filter(p => p.ativo).length

  return (
    <div className="flex flex-col gap-4">
      {/* Toolbar */}
      <div className="flex flex-wrap gap-3 items-end">
        <h1 className="text-lg font-bold text-[#e2e8f0]">Malha</h1>
        <Input value={search} onChange={e => setSearch(e.target.value)} placeholder="Buscar pipeline…" className="w-52" />
        <Select value={projeto} onChange={e => setProjeto(e.target.value)} className="w-44">
          {PROJETOS.map(p => <option key={p}>{p}</option>)}
        </Select>
        <Select value={crit} onChange={e => setCrit(e.target.value)} className="w-32">
          {CRIT.map(c => <option key={c}>{c}</option>)}
        </Select>
        <Select value={status} onChange={e => setStatus(e.target.value)} className="w-32">
          <option>Todos</option><option>Ativos</option><option>Inativos</option>
        </Select>
        <div className="flex gap-1 ml-auto">
          <Button variant={view === 'cards' ? 'primary' : 'secondary'} size="sm" onClick={() => setView('cards')}><LayoutGrid size={13} /></Button>
          <Button variant={view === 'diagram' ? 'primary' : 'secondary'} size="sm" onClick={() => setView('diagram')}><Network size={13} /></Button>
          <Button variant="secondary" size="sm" onClick={() => refetch()}><RefreshCw size={13} /></Button>
        </div>
      </div>

      {/* Stats */}
      <div className="flex gap-4 flex-wrap text-sm">
        {[
          { label: 'Total', value: total },
          { label: 'Ativos', value: ativos },
          { label: 'Inativos', value: total - ativos },
          { label: 'Filtrados', value: filtered.length },
          { label: 'Projetos', value: byProject.size },
        ].map(s => (
          <div key={s.label} className="bg-[#1a1d27] border border-[#2a2d3a] rounded px-3 py-1.5 flex items-center gap-2">
            <span className="text-[#94a3b8] text-xs">{s.label}:</span>
            <span className="text-[#e2e8f0] font-bold">{s.value}</span>
          </div>
        ))}
      </div>

      {isLoading ? <PageSpinner /> : view === 'cards' ? (
        <div className="flex flex-col gap-6">
          {Array.from(byProject.entries()).map(([proj, items]) => (
            <div key={proj}>
              <div className="text-xs font-semibold text-[#94a3b8] uppercase tracking-wider mb-2 flex items-center gap-2">
                {proj} <span className="text-[#4a4d5a]">({items.length})</span>
              </div>
              <div className="flex flex-col gap-2">
                {items.map(it => <PipelineCard key={it.pipeline_name} item={it} />)}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="bg-[#1a1d27] border border-[#2a2d3a] rounded-lg overflow-hidden">
          <DiagramView items={filtered} />
        </div>
      )}
    </div>
  )
}
