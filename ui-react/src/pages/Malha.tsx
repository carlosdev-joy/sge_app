import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '../lib/api'
import { PageSpinner } from '../components/ui/Spinner'
import { Download, RefreshCw, LayoutGrid, AlignLeft, Network, X } from 'lucide-react'

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

const CRIT_STYLES: Record<string, string> = {
  CRITICA: 'bg-pink-100 text-pink-800 border border-pink-200 dark:bg-pink-900/40 dark:text-pink-300 dark:border-pink-800',
  ALTA:    'bg-red-100 text-red-700 border border-red-200 dark:bg-red-900/40 dark:text-red-300 dark:border-red-800',
  MEDIA:   'bg-amber-100 text-amber-700 border border-amber-200 dark:bg-amber-900/40 dark:text-amber-300 dark:border-amber-800',
  BAIXA:   'bg-green-100 text-green-700 border border-green-200 dark:bg-green-900/40 dark:text-green-300 dark:border-green-800',
}
function CritBadge({ crit }: { crit: string }) {
  const upper = crit?.toUpperCase() ?? 'MEDIA'
  return (
    <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase ${CRIT_STYLES[upper] ?? CRIT_STYLES['MEDIA']}`}>
      {upper}
    </span>
  )
}

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
  const schedule = item.scheduled_time ?? item.schedule_type ?? null

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
        const schedule = item.scheduled_time ?? item.schedule_type ?? null
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

// ─── Main page ───────────────────────────────────────────────────────────────

type ViewMode = 'cards' | 'diagram'

export default function Malha() {
  const [view, setView] = useState<ViewMode>('cards')
  const [search, setSearch] = useState('')
  const [projeto, setProjeto] = useState('')
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
    if (crit) items = items.filter(p => p.criticidade?.toUpperCase() === crit)
    if (status === '1') items = items.filter(p => p.active === 1)
    if (status === '0') items = items.filter(p => p.active === 0)
    return items
  }, [allPipelines, search, projeto, crit, status])

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

      <div>
        <h1 className="text-xl font-bold text-ink">Malha de Pipelines</h1>
        <p className="text-sm text-dim mt-0.5">Visualize e exporte a estrutura de execução de todos os pipelines</p>
      </div>

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
      ) : (
        <div className="bg-panel border border-edge rounded-lg overflow-hidden">
          <DiagramView items={filtered} />
        </div>
      )}
    </div>
  )
}
