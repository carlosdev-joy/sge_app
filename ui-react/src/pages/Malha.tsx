import { useState, useMemo, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { apiFetch } from '../lib/api'
import { useAuthStore } from '../store/auth'
import { PageSpinner } from '../components/ui/Spinner'
import { Button } from '../components/ui/Button'
import { Modal } from '../components/ui/Modal'
import { Input, Textarea } from '../components/ui/Input'
import { Autocomplete } from '../components/ui/Autocomplete'
import { toast } from '../components/ui/Toast'
import { CritBadge } from '../components/malhas/CritBadge'
import { MalhaEditor } from '../components/malhas/MalhaEditor'
import {
  Download, RefreshCw, LayoutGrid, AlignLeft, Network, X, GitFork,
  Plus, Edit, Users, Power, Trash2, AlertTriangle, Boxes,
} from 'lucide-react'

// ─── Types matching actual API response ─────────────────────────────────────

interface ApiJob {
  job_name: string
  execution_order: number
  job_type: string
  command: string
}

interface ApiPipeline {
  pipeline_name: string
  project_name: string
  domain: string
  tags: string
  scheduled_time: string | null
  schedule_type: string
  active: 0 | 1
  depends_on: string | null
  descricao: string | null
  criticidade: string
  sla_minutos: number | null
  ambiente: string
  last_execution: string | null
  jobs: ApiJob[]
}

interface MalhaResponse {
  data: ApiPipeline[]
}

// ─── Job type colors ─────────────────────────────────────────────────────────

const JOB_COLORS: Record<string, string> = {
  datastage:  '#1A5FA8',
  shell:      '#16a34a',
  python:     '#7c3aed',
  storedproc: '#b45309',
}
const jobColor = (type: string) => JOB_COLORS[type?.toLowerCase()] ?? '#64748b'

// ─── Criticality badge ───────────────────────────────────────────────────────
// (CritBadge migrou para components/malhas/CritBadge.tsx na F8 — compartilhado
// com o nó do MalhaEditor.)

// ─── Job chain visualization ─────────────────────────────────────────────────

function JobChain({ jobs }: { jobs: ApiJob[] }) {
  if (!jobs.length) return <span className="text-[11px] text-dim italic">Sem jobs cadastrados</span>

  const byOrder = new Map<number, ApiJob[]>()
  for (const j of jobs) {
    const arr = byOrder.get(j.execution_order) ?? []
    arr.push(j)
    byOrder.set(j.execution_order, arr)
  }
  const orders = [...byOrder.keys()].sort((a, b) => a - b)

  return (
    <div className="flex flex-wrap items-center gap-1">
      {orders.map((ord, i) => {
        const group = byOrder.get(ord)!
        return (
          <div key={ord} className="flex items-center gap-1">
            {i > 0 && <span className="text-dim text-xs">→</span>}
            {group.length === 1 ? (
              <div
                className="border rounded px-2 py-1 text-[10px] font-mono max-w-[120px]"
                style={{ borderColor: jobColor(group[0].job_type) }}
                title={`${group[0].job_type}: ${group[0].command}`}
              >
                <div className="truncate text-ink">{group[0].job_name}</div>
                <div className="text-[8px]" style={{ color: jobColor(group[0].job_type) }}>{group[0].job_type}</div>
              </div>
            ) : (
              <div className="flex flex-col gap-0.5">
                <div className="text-[9px] text-dim text-center">‖ paralelo</div>
                {group.map((j) => (
                  <div
                    key={j.job_name}
                    className="border rounded px-2 py-1 text-[10px] font-mono max-w-[120px]"
                    style={{ borderColor: jobColor(j.job_type) }}
                    title={`${j.job_type}: ${j.command}`}
                  >
                    <div className="truncate text-ink">{j.job_name}</div>
                    <div className="text-[8px]" style={{ color: jobColor(j.job_type) }}>{j.job_type}</div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

// ─── Pipeline card ───────────────────────────────────────────────────────────

function PipelineCard({ item }: { item: ApiPipeline }) {
  const [open, setOpen] = useState(false)
  const deps = item.depends_on ? item.depends_on.split(',').map(s => s.trim()).filter(Boolean) : []
  // Sob demanda não tem horário: mostrar o `scheduled_time` gravado (que é
  // só o default do formulário) faria o card prometer uma execução diária
  // que não existe.
  const schedule = item.schedule_type === 'on_demand'
    ? 'sob demanda'
    : (item.scheduled_time ?? item.schedule_type ?? null)

  return (
    <div className="bg-panel border border-edge rounded-lg overflow-hidden hover:shadow-md hover:border-[#1A5FA8]/40 transition-all">
      <div className="px-4 py-3 cursor-pointer" onClick={() => setOpen(o => !o)}>
        <div className="flex items-center gap-2 flex-wrap">
          <span className={`w-2 h-2 rounded-full shrink-0 ${item.active ? 'bg-green-400' : 'bg-slate-400'}`} />
          <span className="font-mono text-sm font-semibold text-ink flex-1 min-w-0 truncate">{item.pipeline_name}</span>
          <CritBadge crit={item.criticidade} />
          {item.active ? (
            <span className="text-[10px] text-green-600 dark:text-green-400 font-medium">● Ativo</span>
          ) : (
            <span className="text-[10px] text-dim">○ Inativo</span>
          )}
        </div>
        <div className="flex flex-wrap gap-x-3 gap-y-0.5 mt-1.5 text-[11px] text-dim">
          {schedule && <span>📅 {schedule}</span>}
          <span>⚙ {item.jobs.length} job{item.jobs.length !== 1 ? 's' : ''}</span>
          {item.sla_minutos != null && <span>⏱ SLA {item.sla_minutos}min</span>}
          <span>🖥 {item.ambiente}</span>
          {deps.length > 0 && (
            <span className="text-amber-600 dark:text-amber-400" title={`Depende de: ${deps.join(', ')}`}>
              🔗 dep ({deps.length})
            </span>
          )}
        </div>
        {item.descricao && (
          <p className="text-[11px] text-dim mt-1 line-clamp-2">{item.descricao}</p>
        )}
        <div className="text-[11px] text-[#1A5FA8] mt-1.5">
          {open ? '▴ ocultar fluxo' : '▾ ver fluxo de jobs'}
        </div>
      </div>

      {open && (
        <div className="px-4 pb-4 pt-2 border-t border-edge bg-canvas">
          <JobChain jobs={item.jobs} />
          {deps.length > 0 && (
            <div className="mt-2 text-[11px] text-amber-600 dark:text-amber-400">
              🔗 Aguarda: {deps.map(d => (
                <span key={d} className="font-mono ml-1">{d}</span>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ─── Diagram view (row per pipeline) ─────────────────────────────────────────

function DiagramView({ items }: { items: ApiPipeline[] }) {
  return (
    <div className="flex flex-col divide-y divide-edge">
      {items.map((item) => {
        const deps = item.depends_on ? item.depends_on.split(',').map(s => s.trim()).filter(Boolean) : []
        // Sob demanda não tem horário: mostrar o `scheduled_time` gravado (que é
  // só o default do formulário) faria o card prometer uma execução diária
  // que não existe.
  const schedule = item.schedule_type === 'on_demand'
    ? 'sob demanda'
    : (item.scheduled_time ?? item.schedule_type ?? null)
        return (
          <div key={item.pipeline_name} className="flex gap-4 py-3 px-4 hover:bg-canvas transition-colors">
            <div className="w-48 shrink-0">
              <div className="font-mono text-xs font-semibold text-ink truncate">{item.pipeline_name}</div>
              <div className="flex flex-wrap items-center gap-1 mt-0.5">
                <span className="text-[10px] text-dim">{item.project_name}</span>
                <span className="text-[10px] text-dim">·</span>
                <CritBadge crit={item.criticidade} />
                <span className="text-[10px] text-dim">·</span>
                {item.active ? (
                  <span className="text-[10px] text-green-600 dark:text-green-400">● Ativo</span>
                ) : (
                  <span className="text-[10px] text-dim">○ Inativo</span>
                )}
              </div>
              {schedule && <div className="text-[10px] text-dim mt-0.5">📅 {schedule}</div>}
              {item.sla_minutos != null && <div className="text-[10px] text-dim">⏱ SLA {item.sla_minutos}min</div>}
            </div>
            <div className="flex-1 min-w-0 overflow-x-auto">
              {deps.length > 0 && (
                <div className="text-[10px] text-amber-600 dark:text-amber-400 mb-1">
                  🔗 aguarda: {deps.join(', ')}
                </div>
              )}
              <JobChain jobs={item.jobs} />
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ─── CSV export ──────────────────────────────────────────────────────────────

function exportCsv(data: ApiPipeline[]) {
  if (!data.length) { alert('Nenhum dado para exportar.'); return }
  const esc = (v: string | number | null | undefined) => `"${String(v ?? '').replace(/"/g, '""')}"`
  const rows: string[] = []

  rows.push('PIPELINES')
  rows.push(['Pipeline','Projeto','Domínio','Criticidade','Ambiente','Status','Agendamento','SLA (min)','Nº Jobs','Depende de','Descrição'].map(esc).join(','))
  for (const p of data) {
    rows.push([
      p.pipeline_name, p.project_name, p.domain, p.criticidade, p.ambiente,
      p.active ? 'Ativo' : 'Inativo',
      p.scheduled_time ?? p.schedule_type ?? '',
      p.sla_minutos ?? '',
      p.jobs.length,
      p.depends_on ?? '',
      p.descricao ?? '',
    ].map(esc).join(','))
  }

  rows.push('')
  rows.push('JOBS')
  rows.push(['Pipeline','Job','Ordem','Tipo','Comando'].map(esc).join(','))
  for (const p of data) {
    for (const j of p.jobs) {
      rows.push([p.pipeline_name, j.job_name, j.execution_order, j.job_type, j.command].map(esc).join(','))
    }
  }

  const csv = '﻿' + rows.join('\r\n')
  const a = document.createElement('a')
  a.href = 'data:text/csv;charset=utf-8,' + encodeURIComponent(csv)
  a.download = `malha_${new Date().toISOString().slice(0, 10)}.csv`
  a.click()
}

// ─── Dependency Graph (U4) ───────────────────────────────────────────────────

const CRIT_NODE_COLORS: Record<string, string> = {
  CRITICA: '#be123c', ALTA: '#dc2626', MEDIA: '#d97706', BAIXA: '#16a34a',
}

function DependencyGraph({ items }: { items: ApiPipeline[] }) {
  const svgRef = useRef<SVGSVGElement>(null)

  // Build adjacency: pipeline → depends_on[]
  const edges = useMemo(() => {
    const arr: { from: string; to: string }[] = []
    for (const p of items) {
      if (!p.depends_on) continue
      for (const dep of p.depends_on.split(',').map(s => s.trim()).filter(Boolean)) {
        arr.push({ from: dep, to: p.pipeline_name })
      }
    }
    return arr
  }, [items])

  // Only show pipelines that participate in at least one dependency
  const connectedNames = useMemo(() => {
    const s = new Set<string>()
    for (const e of edges) { s.add(e.from); s.add(e.to) }
    return s
  }, [edges])

  const connectedItems = items.filter(p => connectedNames.has(p.pipeline_name))

  if (edges.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-center">
        <GitFork size={40} className="text-dim mb-3" />
        <p className="font-semibold text-ink">Nenhuma dependência entre pipelines</p>
        <p className="text-sm text-dim mt-1">Configure dependências no cadastro de pipeline para visualizá-las aqui.</p>
      </div>
    )
  }

  // Simple layered layout: assign topo-sort depth
  const depth = new Map<string, number>()
  const inDegree = new Map<string, number>()
  for (const n of connectedNames) inDegree.set(n, 0)
  for (const e of edges) inDegree.set(e.to, (inDegree.get(e.to) ?? 0) + 1)

  const queue = [...connectedNames].filter(n => (inDegree.get(n) ?? 0) === 0)
  for (const n of queue) depth.set(n, 0)
  while (queue.length) {
    const cur = queue.shift()!
    for (const e of edges.filter(e => e.from === cur)) {
      const d = (depth.get(cur) ?? 0) + 1
      if (!depth.has(e.to) || (depth.get(e.to) ?? 0) < d) depth.set(e.to, d)
      if ((inDegree.get(e.to) ?? 0) - 1 === 0) queue.push(e.to)
      inDegree.set(e.to, (inDegree.get(e.to) ?? 0) - 1)
    }
  }
  // Assign remaining (cycles) depth 0
  for (const n of connectedNames) if (!depth.has(n)) depth.set(n, 0)

  // Group by depth layer
  const byLayer = new Map<number, string[]>()
  for (const [n, d] of depth) {
    const arr = byLayer.get(d) ?? []
    arr.push(n)
    byLayer.set(d, arr)
  }
  const layers = [...byLayer.keys()].sort((a, b) => a - b)

  const NODE_W = 180; const NODE_H = 44; const H_GAP = 60; const V_GAP = 20
  const colX = layers.map((_, i) => i * (NODE_W + H_GAP) + 20)
  const positions = new Map<string, { x: number; y: number }>()
  for (const layer of layers) {
    const col = layers.indexOf(layer)
    const nodeList = byLayer.get(layer) ?? []
    nodeList.forEach((name, row) => {
      positions.set(name, { x: colX[col], y: row * (NODE_H + V_GAP) + 20 })
    })
  }

  const maxY = Math.max(...[...positions.values()].map(p => p.y)) + NODE_H + 20
  const maxX = Math.max(...[...positions.values()].map(p => p.x)) + NODE_W + 20

  return (
    <div className="overflow-auto bg-canvas rounded border border-edge p-2">
      <p className="text-[10px] text-dim mb-2 pl-1">
        {connectedItems.length} pipelines com dependências · {edges.length} ligações
      </p>
      <svg ref={svgRef} width={maxX} height={maxY} className="font-sans">
        <defs>
          <marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto">
            <path d="M0,0 L0,6 L8,3 z" fill="#94a3b8" />
          </marker>
        </defs>

        {/* Edges */}
        {edges.map((e, i) => {
          const from = positions.get(e.from)
          const to   = positions.get(e.to)
          if (!from || !to) return null
          const x1 = from.x + NODE_W
          const y1 = from.y + NODE_H / 2
          const x2 = to.x
          const y2 = to.y + NODE_H / 2
          const mx = (x1 + x2) / 2
          return (
            <g key={i}>
              <path
                d={`M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}`}
                fill="none" stroke="#94a3b8" strokeWidth="1.5"
                markerEnd="url(#arrow)"
              />
            </g>
          )
        })}

        {/* Nodes */}
        {connectedItems.map(p => {
          const pos = positions.get(p.pipeline_name)
          if (!pos) return null
          const color = CRIT_NODE_COLORS[(p.criticidade ?? '').toUpperCase()] ?? '#64748b'
          const active = p.active === 1
          return (
            <g key={p.pipeline_name}>
              <rect
                x={pos.x} y={pos.y}
                width={NODE_W} height={NODE_H}
                rx={6}
                fill={active ? '#1e293b' : '#334155'}
                stroke={active ? color : '#475569'}
                strokeWidth={active ? 1.5 : 1}
                opacity={active ? 1 : 0.6}
              />
              <circle cx={pos.x + 10} cy={pos.y + 10} r={4} fill={color} />
              <text x={pos.x + 20} y={pos.y + 14} fill="#f1f5f9" fontSize="10" fontWeight="600">
                {p.pipeline_name.length > 20 ? p.pipeline_name.slice(0, 18) + '…' : p.pipeline_name}
              </text>
              <text x={pos.x + 10} y={pos.y + 30} fill="#94a3b8" fontSize="9">
                {p.project_name ?? ''}{p.domain ? ` · ${p.domain}` : ''}
              </text>
              {!active && (
                <text x={pos.x + NODE_W - 10} y={pos.y + 14} fill="#64748b" fontSize="9" textAnchor="end">inativo</text>
              )}
            </g>
          )
        })}
      </svg>
    </div>
  )
}

// ─── Catálogo (inventário de pipelines) ──────────────────────────────────────
// Visão legada da tela, intacta atrás do toggle "Catálogo": migra para
// Catálogo & Lineage (/governanca) na F9 da spec de dependências.

type ViewMode = 'cards' | 'diagram' | 'graph'

function CatalogoView() {
  const [view, setView] = useState<ViewMode>('cards')
  const [search, setSearch] = useState('')
  const [projeto, setProjeto] = useState('')
  const [dominio, setDominio] = useState('')
  const [crit, setCrit] = useState('')
  const [status, setStatus] = useState('')
  const [bannerOpen, setBannerOpen] = useState(true)

  const { data, isLoading, isError, error, refetch } = useQuery<MalhaResponse>({
    queryKey: ['malha'],
    queryFn: () => apiFetch('/malha'),
    staleTime: 60_000,
  })

  const allPipelines = data?.data ?? []

  const projetos = useMemo(() => {
    const s = new Set(allPipelines.map(p => p.project_name))
    return [...s].sort()
  }, [allPipelines])

  const dominios = useMemo(() => {
    const s = new Set(allPipelines.map(p => p.domain).filter(Boolean))
    return [...s].sort() as string[]
  }, [allPipelines])

  const filtered = useMemo(() => {
    let items = allPipelines
    if (search) {
      const q = search.toLowerCase()
      items = items.filter(p =>
        p.pipeline_name.toLowerCase().includes(q) ||
        p.project_name.toLowerCase().includes(q) ||
        (p.domain ?? '').toLowerCase().includes(q)
      )
    }
    if (projeto) items = items.filter(p => p.project_name === projeto)
    if (dominio) items = items.filter(p => p.domain === dominio)
    if (crit) items = items.filter(p => p.criticidade?.toUpperCase() === crit)
    if (status === '1') items = items.filter(p => p.active === 1)
    if (status === '0') items = items.filter(p => p.active === 0)
    return items
  }, [allPipelines, search, projeto, dominio, crit, status])

  const byProject = useMemo(() => {
    const map = new Map<string, ApiPipeline[]>()
    for (const p of filtered) {
      const arr = map.get(p.project_name) ?? []
      arr.push(p)
      map.set(p.project_name, arr)
    }
    return [...map.entries()].sort(([a], [b]) => a.localeCompare(b))
  }, [filtered])

  const totalJobs = filtered.reduce((s, p) => s + p.jobs.length, 0)
  const comDeps = filtered.filter(p => p.depends_on).length
  const uniqueProjs = new Set(filtered.map(p => p.project_name)).size

  const inputCls = 'border border-edge bg-canvas text-ink text-sm rounded-md px-2.5 py-1.5 focus:outline-none focus:ring-2 focus:ring-[#1A5FA8]/40 placeholder:text-dim'

  return (
    <div className="flex flex-col gap-4">

      {bannerOpen && (
        <div className="flex items-start gap-3 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg px-4 py-3">
          <span className="text-base shrink-0">⊞</span>
          <div className="flex-1 text-[12px] leading-relaxed text-blue-800 dark:text-blue-200">
            <strong>Malha de execução:</strong> visualize os pipelines agrupados por projeto, com seus fluxos de jobs (serial e paralelo),
            dependências entre pipelines e metadados de agendamento e criticidade. Use a visão <strong>Diagrama</strong> para uma lista compacta linha a linha,
            ou exporte o inventário completo em CSV para análise no Excel.
          </div>
          <button onClick={() => setBannerOpen(false)} className="shrink-0 text-blue-400 hover:text-blue-700 dark:hover:text-blue-100 transition-colors">
            <X size={14} />
          </button>
        </div>
      )}

      {/* Toolbar */}
      <div className="flex flex-wrap gap-2 items-center">
        <input
          type="search"
          placeholder="Buscar pipeline ou projeto..."
          value={search}
          onChange={e => setSearch(e.target.value)}
          className={`${inputCls} w-56`}
        />
        <select value={projeto} onChange={e => setProjeto(e.target.value)} className={`${inputCls} w-44`}>
          <option value="">Todos os projetos</option>
          {projetos.map(p => <option key={p} value={p}>{p}</option>)}
        </select>
        <select value={dominio} onChange={e => setDominio(e.target.value)} className={`${inputCls} w-36`}>
          <option value="">Todos os domínios</option>
          {dominios.map(d => <option key={d} value={d}>{d}</option>)}
        </select>
        <select value={crit} onChange={e => setCrit(e.target.value)} className={`${inputCls} w-36`}>
          <option value="">Toda criticidade</option>
          <option value="CRITICA">Crítica</option>
          <option value="ALTA">Alta</option>
          <option value="MEDIA">Média</option>
          <option value="BAIXA">Baixa</option>
        </select>
        <select value={status} onChange={e => setStatus(e.target.value)} className={`${inputCls} w-28`}>
          <option value="">Todos</option>
          <option value="1">Ativos</option>
          <option value="0">Inativos</option>
        </select>
        <div className="flex gap-1 ml-auto">
          <button
            onClick={() => setView('cards')}
            title="Visão em cards agrupados por projeto"
            className={`inline-flex items-center gap-1 px-2.5 py-1.5 rounded-md text-sm font-medium transition-colors ${
              view === 'cards'
                ? 'bg-[#1A5FA8] text-white'
                : 'border border-edge bg-canvas text-dim hover:text-ink hover:bg-edge/40'
            }`}
          >
            <LayoutGrid size={13} /> Cards
          </button>
          <button
            onClick={() => setView('diagram')}
            title="Visão em diagrama com cadeias de jobs"
            className={`inline-flex items-center gap-1 px-2.5 py-1.5 rounded-md text-sm font-medium transition-colors ${
              view === 'diagram'
                ? 'bg-[#1A5FA8] text-white'
                : 'border border-edge bg-canvas text-dim hover:text-ink hover:bg-edge/40'
            }`}
          >
            <AlignLeft size={13} /> Diagrama
          </button>
          <button
            onClick={() => setView('graph')}
            title="Grafo de dependências entre pipelines"
            className={`inline-flex items-center gap-1 px-2.5 py-1.5 rounded-md text-sm font-medium transition-colors ${
              view === 'graph'
                ? 'bg-[#1A5FA8] text-white'
                : 'border border-edge bg-canvas text-dim hover:text-ink hover:bg-edge/40'
            }`}
          >
            <GitFork size={13} /> Grafo dep.
          </button>
          <button
            onClick={() => exportCsv(filtered)}
            title="Exportar inventário para CSV (abre no Excel)"
            className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-md text-sm font-medium border border-edge bg-canvas text-dim hover:text-ink hover:bg-edge/40 transition-colors"
          >
            <Download size={13} /> Exportar
          </button>
          <button
            onClick={() => refetch()}
            title="Atualizar dados"
            className="inline-flex items-center px-2.5 py-1.5 rounded-md text-sm border border-edge bg-canvas text-dim hover:text-ink hover:bg-edge/40 transition-colors"
          >
            <RefreshCw size={13} />
          </button>
        </div>
      </div>

      {/* Stats bar */}
      {!isLoading && !isError && (
        <div className="flex flex-wrap gap-2">
          {[
            { label: `${filtered.length}`, sub: `pipeline${filtered.length !== 1 ? 's' : ''} filtrados` },
            { label: `${filtered.filter(p => p.active).length}`, sub: 'ativos' },
            { label: `${totalJobs}`, sub: 'jobs' },
            { label: `${uniqueProjs}`, sub: 'projeto' + (uniqueProjs !== 1 ? 's' : '') },
            ...(comDeps > 0 ? [{ label: `${comDeps}`, sub: 'com dependências' }] : []),
          ].map(s => (
            <div key={s.sub} className="bg-panel border border-edge rounded px-3 py-1.5 flex items-center gap-1.5">
              <strong className="text-ink font-bold text-sm">{s.label}</strong>
              <span className="text-dim text-xs">{s.sub}</span>
            </div>
          ))}
        </div>
      )}

      {/* Content */}
      {isLoading ? (
        <PageSpinner />
      ) : isError ? (
        <div className="rounded-lg border border-red-200 bg-red-50 dark:bg-red-900/20 dark:border-red-800 px-4 py-3 text-sm text-red-700 dark:text-red-300">
          Erro ao carregar malha: {(error as Error)?.message ?? 'Erro desconhecido'}
        </div>
      ) : filtered.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <Network size={40} className="text-dim mb-3" />
          <p className="font-semibold text-ink">Nenhum pipeline encontrado</p>
          <p className="text-sm text-dim mt-1">Ajuste os filtros acima.</p>
        </div>
      ) : view === 'cards' ? (
        <div className="flex flex-col gap-6">
          {byProject.map(([proj, items]) => (
            <div key={proj}>
              <div className="text-xs font-semibold text-dim uppercase tracking-wider mb-2 flex items-center gap-2">
                📁 {proj} <span className="font-normal">({items.length})</span>
              </div>
              <div className="grid gap-2" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))' }}>
                {items.map(it => <PipelineCard key={it.pipeline_name} item={it} />)}
              </div>
            </div>
          ))}
        </div>
      ) : view === 'diagram' ? (
        <div className="bg-panel border border-edge rounded-lg overflow-hidden">
          <DiagramView items={filtered} />
        </div>
      ) : (
        <DependencyGraph items={filtered} />
      )}
    </div>
  )
}

// ─── Malhas (F7) — agrupadoras de pipelines ──────────────────────────────────
// Malha = agrupador nomeado de pipelines (análogo da sequence mestre do
// DataStage / SMART Folder do Control-M). Nesta fase existe a entidade, os
// membros e a lista; o diagrama de montagem (MalhaEditor) chega na F8.

interface ApiMalha {
  malha_name: string
  descricao: string | null
  ativo: 0 | 1 | boolean
  criado_em: string | null
  qtd_pipelines: number
  qtd_ativos: number
  criticidade: string | null // agregada = a mais alta entre os membros
}

interface MalhasResponse {
  malhas: ApiMalha[]
  // Deploy parcial (API nova + migration 070 não aplicada): a API degrada
  // devolvendo lista vazia + esta flag, em vez de 500.
  migration_pendente?: boolean
}

interface MalhaMembro {
  pipeline_name: string
  active: 0 | 1 | boolean
  criticidade: string | null
  schedule_type: string | null
  layout_x: number | null
  layout_y: number | null
}

interface MalhaDetalheResponse {
  malha: ApiMalha
  membros: MalhaMembro[]
}

function formataData(iso: string | null): string | null {
  if (!iso) return null
  const d = new Date(iso)
  return isNaN(d.getTime()) ? iso : d.toLocaleDateString('pt-BR')
}

// ─── Card de malha (mesma linguagem do PipelineCard) ─────────────────────────

function MalhaCard({ malha, onAbrir, onMembros, onRenomear, onToggle }: {
  malha: ApiMalha
  onAbrir: () => void
  onMembros: () => void
  onRenomear: () => void
  onToggle: () => void
}) {
  const ativa = !!malha.ativo
  const criado = formataData(malha.criado_em)
  return (
    <div className="bg-panel border border-edge rounded-lg px-4 py-3 flex flex-col gap-2 hover:shadow-md hover:border-[#1A5FA8]/40 transition-all">
      <div className="flex items-center gap-2 flex-wrap">
        <span className={`w-2 h-2 rounded-full shrink-0 ${ativa ? 'bg-green-400' : 'bg-slate-400'}`} />
        <span className="font-mono text-sm font-semibold text-ink flex-1 min-w-0 truncate">{malha.malha_name}</span>
        {malha.criticidade && <CritBadge crit={malha.criticidade} />}
        {ativa ? (
          <span className="text-[10px] text-green-600 dark:text-green-400 font-medium">● Ativa</span>
        ) : (
          <span className="text-[10px] text-dim">○ Inativa</span>
        )}
      </div>
      {malha.descricao && (
        <p className="text-[11px] text-dim line-clamp-2">{malha.descricao}</p>
      )}
      <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-[11px] text-dim">
        <span>⚙ {malha.qtd_pipelines} pipeline{malha.qtd_pipelines !== 1 ? 's' : ''} ({malha.qtd_ativos} ativo{malha.qtd_ativos !== 1 ? 's' : ''})</span>
        {criado && <span>📅 criada em {criado}</span>}
      </div>
      <div className="flex flex-wrap gap-1.5 pt-2 border-t border-edge mt-auto">
        <Button size="sm" onClick={onAbrir} title="Abrir o diagrama de montagem — desenhar uma aresta cadastra a dependência real">
          <Network size={12} /> Abrir diagrama
        </Button>
        <Button variant="secondary" size="sm" onClick={onMembros} title="Ver e editar os pipelines desta malha">
          <Users size={12} /> Membros
        </Button>
        <Button variant="ghost" size="sm" onClick={onRenomear} title="Renomear a malha e editar a descrição">
          <Edit size={12} /> Renomear
        </Button>
        <Button variant="ghost" size="sm" onClick={onToggle} title={ativa ? 'Inativar a malha' : 'Reativar a malha'}>
          <Power size={12} /> {ativa ? 'Inativar' : 'Reativar'}
        </Button>
      </div>
    </div>
  )
}

// ─── Modal: nova malha ───────────────────────────────────────────────────────

function NovaMalhaModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const qc = useQueryClient()
  const [nome, setNome] = useState('')
  const [descricao, setDescricao] = useState('')

  const criarMut = useMutation({
    mutationFn: () => apiFetch('/malhas', {
      method: 'POST',
      body: JSON.stringify({
        malha_name: nome.trim(),
        ...(descricao.trim() ? { descricao: descricao.trim() } : {}),
      }),
    }),
    onSuccess: () => {
      toast.success(`Malha "${nome.trim()}" criada.`)
      qc.invalidateQueries({ queryKey: ['malhas'] })
      setNome(''); setDescricao('')
      onClose()
    },
    // 422 da API (nome duplicado/inválido) chega como `detail` string em pt-BR.
    onError: (e: Error) => toast.error(e.message || 'Erro ao criar a malha'),
  })

  return (
    <Modal open={open} onClose={onClose} title="Nova malha">
      <div className="flex flex-col gap-3">
        <Input
          label="Nome"
          value={nome}
          onChange={e => setNome(e.target.value)}
          placeholder="ex: malha_fechamento_diario"
          ajuda="Identificador único da malha — os pipelines membros são adicionados depois, em Membros."
          autoFocus
        />
        <Textarea
          label="Descrição"
          value={descricao}
          onChange={e => setDescricao(e.target.value)}
          placeholder="opcional — o que esta malha orquestra"
          rows={3}
        />
        <div className="flex justify-end gap-2 pt-1">
          <Button variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button
            onClick={() => criarMut.mutate()}
            loading={criarMut.isPending}
            disabled={!nome.trim()}
          >
            <Plus size={14} /> Criar malha
          </Button>
        </div>
      </div>
    </Modal>
  )
}

// ─── Modal: renomear/editar malha ────────────────────────────────────────────

function RenomearMalhaModal({ malha, onClose }: { malha: ApiMalha; onClose: () => void }) {
  const qc = useQueryClient()
  const [nome, setNome] = useState(malha.malha_name)
  const [descricao, setDescricao] = useState(malha.descricao ?? '')

  const salvarMut = useMutation({
    mutationFn: (body: { novo_nome?: string; descricao?: string }) =>
      apiFetch(`/malhas/${encodeURIComponent(malha.malha_name)}`, {
        method: 'PATCH',
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      toast.success('Malha atualizada.')
      qc.invalidateQueries({ queryKey: ['malhas'] })
      onClose()
    },
    onError: (e: Error) => toast.error(e.message || 'Erro ao atualizar a malha'),
  })

  function salvar() {
    const body: { novo_nome?: string; descricao?: string } = {}
    const nomeTrim = nome.trim()
    if (nomeTrim && nomeTrim !== malha.malha_name) body.novo_nome = nomeTrim
    if (descricao.trim() !== (malha.descricao ?? '')) body.descricao = descricao.trim()
    if (Object.keys(body).length === 0) { onClose(); return } // nada mudou: no-op
    salvarMut.mutate(body)
  }

  return (
    <Modal open onClose={onClose} title="Renomear malha">
      <div className="flex flex-col gap-3">
        <Input
          label="Nome"
          value={nome}
          onChange={e => setNome(e.target.value)}
          autoFocus
        />
        <Textarea
          label="Descrição"
          value={descricao}
          onChange={e => setDescricao(e.target.value)}
          placeholder="opcional — o que esta malha orquestra"
          rows={3}
        />
        <div className="flex justify-end gap-2 pt-1">
          <Button variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button onClick={salvar} loading={salvarMut.isPending} disabled={!nome.trim()}>
            Salvar
          </Button>
        </div>
      </div>
    </Modal>
  )
}

// ─── Modal: membros da malha ─────────────────────────────────────────────────

function MembrosModal({ malhaName, onClose }: { malhaName: string; onClose: () => void }) {
  const qc = useQueryClient()
  const [busca, setBusca] = useState('')

  const { data, isLoading, isError, error } = useQuery<MalhaDetalheResponse>({
    queryKey: ['malha', malhaName],
    queryFn: () => apiFetch(`/malhas/${encodeURIComponent(malhaName)}`),
  })
  const membros = data?.membros ?? []

  function invalidar() {
    qc.invalidateQueries({ queryKey: ['malha', malhaName] })
    qc.invalidateQueries({ queryKey: ['malhas'] }) // contagens/criticidade dos cards
  }

  const addMut = useMutation({
    mutationFn: (pipeline_name: string) =>
      apiFetch(`/malhas/${encodeURIComponent(malhaName)}/pipelines`, {
        method: 'POST',
        body: JSON.stringify({ pipeline_name }),
      }),
    onSuccess: (_r, pipeline_name) => {
      toast.success(`Pipeline "${pipeline_name}" adicionado à malha.`)
      setBusca('')
      invalidar()
    },
    // 422 da API: pipeline inexistente / já membro — detail em pt-BR.
    onError: (e: Error) => toast.error(e.message || 'Erro ao adicionar o pipeline'),
  })

  const removerMut = useMutation({
    mutationFn: (pipeline_name: string) =>
      apiFetch(`/malhas/${encodeURIComponent(malhaName)}/pipelines/${encodeURIComponent(pipeline_name)}`, {
        method: 'DELETE',
      }),
    onSuccess: (_r, pipeline_name) => {
      toast.success(`Pipeline "${pipeline_name}" removido da malha.`)
      invalidar()
    },
    onError: (e: Error) => toast.error(e.message || 'Erro ao remover o pipeline'),
  })

  function remover(pipeline_name: string) {
    if (!confirm(`Remover "${pipeline_name}" da malha "${malhaName}"?\n\nO pipeline continua existindo — sai apenas desta malha.`)) return
    removerMut.mutate(pipeline_name)
  }

  return (
    <Modal open onClose={onClose} title={`Membros — ${malhaName}`} size="lg">
      <div className="flex flex-col gap-4">

        {/* Adicionar por busca (mesmo padrão de autocomplete da tela de Etapas) */}
        <div className="flex items-end gap-2">
          <Autocomplete
            label="Adicionar pipeline"
            value={busca}
            onChange={setBusca}
            onSelect={setBusca}
            fetchSuggestions={q =>
              apiFetch<{ data: { pipeline_name: string }[] }>(`/pipelines?limit=10&filter_name=${encodeURIComponent(q)}`)
                .then(r => r.data.map(p => p.pipeline_name))
            }
            placeholder="busque por nome..."
            className="flex-1"
          />
          <Button
            onClick={() => addMut.mutate(busca.trim())}
            loading={addMut.isPending}
            disabled={!busca.trim()}
          >
            <Plus size={14} /> Adicionar
          </Button>
        </div>

        {/* Lista de membros */}
        {isLoading ? (
          <PageSpinner />
        ) : isError ? (
          <div className="rounded-lg border border-red-200 bg-red-50 dark:bg-red-900/20 dark:border-red-800 px-4 py-3 text-sm text-red-700 dark:text-red-300">
            Erro ao carregar os membros: {(error as Error)?.message ?? 'Erro desconhecido'}
          </div>
        ) : membros.length === 0 ? (
          <p className="text-sm text-dim text-center py-6">
            Nenhum pipeline nesta malha ainda — adicione pelo campo acima.
          </p>
        ) : (
          <div className="flex flex-col gap-1.5">
            {membros.map(m => (
              <div key={m.pipeline_name} className="flex items-center gap-2 px-3 py-2 bg-canvas border border-edge rounded-md">
                <span className={`w-2 h-2 rounded-full shrink-0 ${m.active ? 'bg-green-400' : 'bg-slate-400'}`} />
                <span className="font-mono text-xs text-ink flex-1 min-w-0 truncate">{m.pipeline_name}</span>
                {m.criticidade && <CritBadge crit={m.criticidade} />}
                {m.schedule_type && (
                  <span className="text-[10px] text-dim">
                    {m.schedule_type === 'on_demand' ? 'sob demanda' : m.schedule_type}
                  </span>
                )}
                <button
                  onClick={() => remover(m.pipeline_name)}
                  title="Remover da malha"
                  className="text-dim hover:text-red-400 transition-colors shrink-0"
                >
                  <Trash2 size={13} />
                </button>
              </div>
            ))}
          </div>
        )}

        <p className="text-[11px] text-dim border-t border-edge pt-3">
          Aqui você define apenas <strong className="text-ink">quem participa</strong> da malha —
          o diagrama de montagem (nós, dependências e layout) chega na F8.
        </p>
      </div>
    </Modal>
  )
}

// ─── Visão Malhas (lista) ────────────────────────────────────────────────────

function MalhasView({ onAbrir }: { onAbrir: (malha: string) => void }) {
  const [showCriar, setShowCriar] = useState(false)
  const [renomear, setRenomear] = useState<ApiMalha | null>(null)
  const [membrosDe, setMembrosDe] = useState<string | null>(null)

  const qc = useQueryClient()
  const { data, isLoading, isError, error, refetch } = useQuery<MalhasResponse>({
    queryKey: ['malhas'],
    queryFn: () => apiFetch('/malhas'),
  })
  const malhas = data?.malhas ?? []
  const migrationPendente = data?.migration_pendente === true

  const toggleMut = useMutation({
    mutationFn: (m: ApiMalha) =>
      apiFetch(`/malhas/${encodeURIComponent(m.malha_name)}`, {
        method: 'PATCH',
        body: JSON.stringify({ ativo: !m.ativo }),
      }),
    onSuccess: (_r, m) => {
      toast.success(m.ativo ? `Malha "${m.malha_name}" inativada.` : `Malha "${m.malha_name}" reativada.`)
      qc.invalidateQueries({ queryKey: ['malhas'] })
    },
    onError: (e: Error) => toast.error(e.message || 'Erro ao alterar a malha'),
  })

  function alternar(m: ApiMalha) {
    const acao = m.ativo ? 'Inativar' : 'Reativar'
    if (!confirm(`${acao} a malha "${m.malha_name}"?`)) return
    toggleMut.mutate(m)
  }

  const ativas = malhas.filter(m => m.ativo).length
  const totalPipelines = malhas.reduce((s, m) => s + m.qtd_pipelines, 0)

  return (
    <div className="flex flex-col gap-4">

      {/* Aviso discreto de deploy parcial: API nova sem a migration 070. */}
      {migrationPendente && (
        <div className="flex items-center gap-2 text-[12px] text-amber-700 dark:text-amber-400 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg px-3 py-2">
          <AlertTriangle size={14} className="shrink-0" />
          <span>migration 070 pendente — as tabelas de malha ainda não existem neste ambiente; peça o deploy para criar malhas.</span>
        </div>
      )}

      {/* Toolbar */}
      <div className="flex flex-wrap gap-2 items-center">
        <div className="flex gap-1 ml-auto">
          <Button
            onClick={() => setShowCriar(true)}
            disabled={migrationPendente}
            title={migrationPendente ? 'Indisponível até a migration 070 ser aplicada' : 'Criar uma nova malha'}
          >
            <Plus size={14} /> Nova malha
          </Button>
          <button
            onClick={() => refetch()}
            title="Atualizar dados"
            className="inline-flex items-center px-2.5 py-1.5 rounded-md text-sm border border-edge bg-canvas text-dim hover:text-ink hover:bg-edge/40 transition-colors"
          >
            <RefreshCw size={13} />
          </button>
        </div>
      </div>

      {/* Stats bar (mesma linguagem das stats-pills do catálogo) */}
      {!isLoading && !isError && malhas.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {[
            { label: `${malhas.length}`, sub: `malha${malhas.length !== 1 ? 's' : ''}` },
            { label: `${ativas}`, sub: `ativa${ativas !== 1 ? 's' : ''}` },
            { label: `${totalPipelines}`, sub: `pipeline${totalPipelines !== 1 ? 's' : ''} agrupados` },
          ].map(s => (
            <div key={s.sub} className="bg-panel border border-edge rounded px-3 py-1.5 flex items-center gap-1.5">
              <strong className="text-ink font-bold text-sm">{s.label}</strong>
              <span className="text-dim text-xs">{s.sub}</span>
            </div>
          ))}
        </div>
      )}

      {/* Conteúdo */}
      {isLoading ? (
        <PageSpinner />
      ) : isError ? (
        <div className="rounded-lg border border-red-200 bg-red-50 dark:bg-red-900/20 dark:border-red-800 px-4 py-3 text-sm text-red-700 dark:text-red-300">
          Erro ao carregar malhas: {(error as Error)?.message ?? 'Erro desconhecido'}
        </div>
      ) : malhas.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <Boxes size={40} className="text-dim mb-3" />
          <p className="font-semibold text-ink">Nenhuma malha cadastrada</p>
          <p className="text-sm text-dim mt-1 max-w-md">
            Uma malha agrupa pipelines — o análogo da sequence mestre do DataStage.
            O diagrama de montagem chega na F8.
          </p>
          {!migrationPendente && (
            <Button className="mt-4" onClick={() => setShowCriar(true)}>
              <Plus size={14} /> Criar a primeira malha
            </Button>
          )}
        </div>
      ) : (
        <div className="grid gap-2" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))' }}>
          {malhas.map(m => (
            <MalhaCard
              key={m.malha_name}
              malha={m}
              onAbrir={() => onAbrir(m.malha_name)}
              onMembros={() => setMembrosDe(m.malha_name)}
              onRenomear={() => setRenomear(m)}
              onToggle={() => alternar(m)}
            />
          ))}
        </div>
      )}

      <NovaMalhaModal open={showCriar} onClose={() => setShowCriar(false)} />
      {renomear && (
        <RenomearMalhaModal
          key={renomear.malha_name}
          malha={renomear}
          onClose={() => setRenomear(null)}
        />
      )}
      {membrosDe && (
        <MembrosModal malhaName={membrosDe} onClose={() => setMembrosDe(null)} />
      )}
    </div>
  )
}

// ─── Main page ───────────────────────────────────────────────────────────────
// Default = Malhas (F7). O inventário legado fica no toggle "Catálogo" até
// migrar para Catálogo & Lineage (/governanca) na F9. Com `?malha=` na URL a
// página vira o diagrama de montagem em tela cheia (F8) — mesmo padrão de
// deep-link da tela Fluxos (?pipeline=).

type PageMode = 'malhas' | 'catalogo'

export default function Malha() {
  const [mode, setMode] = useState<PageMode>('malhas')
  const [searchParams, setSearchParams] = useSearchParams()
  const malhaAberta = (searchParams.get('malha') ?? '').trim()
  const [membrosAberto, setMembrosAberto] = useState(false)
  const user = useAuthStore(s => s.user)
  const isViewer = user?.perfil === 'consulta'

  const tabCls = (active: boolean) =>
    `inline-flex items-center gap-1 px-2.5 py-1.5 rounded-md text-sm font-medium transition-colors ${
      active
        ? 'bg-[#1A5FA8] text-white'
        : 'border border-edge bg-canvas text-dim hover:text-ink hover:bg-edge/40'
    }`

  // ── Diagrama de montagem em tela cheia (F8) ────────────────────────────────
  if (malhaAberta) {
    return (
      <div className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="flex items-center gap-2 text-lg font-semibold text-ink">
            <Boxes size={20} className="text-[#1A5FA8]" /> Malha
            <span className="font-mono text-base text-dim">· {malhaAberta}</span>
          </h1>
          <div className="ml-auto flex items-center gap-2">
            {!isViewer && (
              <Button
                variant="secondary" size="sm"
                onClick={() => setMembrosAberto(true)}
                title="Ver e remover os pipelines membros desta malha"
              >
                <Users size={13} /> Membros
              </Button>
            )}
            <Button variant="secondary" size="sm" onClick={() => setSearchParams({})} title="Voltar à lista de malhas">
              <X size={13} /> Voltar
            </Button>
          </div>
        </div>
        <div className="h-[calc(100vh-11rem)]">
          <MalhaEditor malha={malhaAberta} readOnly={isViewer} />
        </div>
        {membrosAberto && (
          <MembrosModal malhaName={malhaAberta} onClose={() => setMembrosAberto(false)} />
        )}
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-4">

      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h1 className="text-xl font-bold text-ink">Malha de Pipelines</h1>
          <p className="text-sm text-dim mt-0.5">
            {mode === 'malhas'
              ? 'Agrupe pipelines em malhas — a lente de montagem da orquestração'
              : 'Visualize e exporte a estrutura de execução de todos os pipelines'}
          </p>
        </div>
        <div className="flex gap-1">
          <button onClick={() => setMode('malhas')} title="Malhas — agrupadoras de pipelines" className={tabCls(mode === 'malhas')}>
            <Boxes size={13} /> Malhas
          </button>
          <button
            onClick={() => setMode('catalogo')}
            title="Inventário de pipelines — migra para Catálogo & Lineage na F9"
            className={tabCls(mode === 'catalogo')}
          >
            <LayoutGrid size={13} /> Catálogo (migra p/ Governança na F9)
          </button>
        </div>
      </div>

      {mode === 'malhas'
        ? <MalhasView onAbrir={n => setSearchParams({ malha: n })} />
        : <CatalogoView />}
    </div>
  )
}
