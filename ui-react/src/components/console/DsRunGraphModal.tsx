import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  ReactFlow, Background, Controls, Handle, Position,
  type Node, type Edge, type NodeProps,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { Modal } from '../ui/Modal'
import { Select } from '../ui/Input'
import { dsParseTime, dsFmtDuration } from '../../lib/dsTime'
import { CheckCircle2, XCircle, AlertTriangle, RotateCcw, Clock, HelpCircle, ArrowRight, ArrowDown, ArrowLeft, ChevronRight, Loader2, Timer, Crosshair } from 'lucide-react'

// Diagrama do run de uma sequence (estilo CTRL-M): a sequence + seus filhos diretos,
// com o status real daquele run. Clicar num filho faz o drill-down (abre o log dele).
// Os dados vêm do logsum já parseado no console — sem chamada nova ao backend.

export type DsGraphStatus = 'ok' | 'warning' | 'aborted' | 'reset' | 'running' | 'unknown'
export interface DsGraphNode { job: string; status: DsGraphStatus; label: string; time?: string; start?: string; end?: string }
export interface DsRunGraph { result: 'ok' | 'aborted' | 'running' | 'unknown'; start?: string; end?: string; children: DsGraphNode[] }

type Dir = 'LR' | 'TB'
const FILTERABLE: DsGraphStatus[] = ['ok', 'warning', 'aborted', 'running']

const STATUS: Record<DsGraphStatus, { Icon: typeof CheckCircle2; box: string; text: string }> = {
  ok:      { Icon: CheckCircle2,  box: 'bg-green-50 border-green-300 dark:bg-green-900/30 dark:border-green-700',   text: 'text-green-700 dark:text-green-300' },
  warning: { Icon: AlertTriangle, box: 'bg-amber-50 border-amber-300 dark:bg-yellow-900/30 dark:border-yellow-700', text: 'text-amber-700 dark:text-yellow-300' },
  aborted: { Icon: XCircle,       box: 'bg-red-50 border-red-300 dark:bg-red-900/30 dark:border-red-700',           text: 'text-red-700 dark:text-red-300' },
  reset:   { Icon: RotateCcw,     box: 'bg-blue-50 border-blue-300 dark:bg-blue-900/30 dark:border-blue-700',       text: 'text-blue-700 dark:text-blue-300' },
  running: { Icon: Clock,         box: 'bg-blue-50 border-blue-300 dark:bg-blue-900/30 dark:border-blue-700',       text: 'text-blue-700 dark:text-blue-300' },
  unknown: { Icon: HelpCircle,    box: 'bg-slate-50 border-slate-300 dark:bg-gray-800 dark:border-gray-700',        text: 'text-slate-600 dark:text-gray-300' },
}

function statusLabel(s: DsGraphStatus): string {
  return s === 'ok' ? 'Concluído' : s === 'warning' ? 'Avisos' : s === 'aborted' ? 'Abortado'
    : s === 'reset' ? 'Resetado' : s === 'running' ? 'Em execução' : '—'
}

interface JobNodeData {
  label: string; status: DsGraphStatus; sub?: string; time?: string
  isRoot?: boolean; drillJob?: string; targetTime?: string; dir?: Dir; critical?: boolean
}

function JobNode({ data }: NodeProps) {
  const d = data as unknown as JobNodeData
  const s = STATUS[d.status] ?? STATUS.unknown
  const Icon = s.Icon
  const targetPos = d.dir === 'TB' ? Position.Top : Position.Left
  const sourcePos = d.dir === 'TB' ? Position.Bottom : Position.Right
  return (
    <div
      className={`rounded-lg border px-3 py-2 shadow-sm min-w-[180px] max-w-[260px] ${s.box} ${d.critical ? 'ring-2 ring-violet-500' : ''} ${d.drillJob ? 'cursor-pointer hover:ring-2 hover:ring-[#1A5FA8]' : ''}`}
      title={d.drillJob ? `Abrir o log de ${d.label} (drill-down)` : d.label}
    >
      {!d.isRoot && <Handle type="target" position={targetPos} className="!bg-edge !border-edge" />}
      <div className="flex items-center gap-1.5">
        <Icon size={14} className={`${s.text} shrink-0`} />
        <span className="font-mono text-[11px] text-ink break-all leading-tight">{d.label}</span>
      </div>
      {d.sub && <div className={`text-[10px] mt-0.5 ${s.text}`}>{d.sub}</div>}
      {d.time && <div className="text-[10px] mt-0.5 text-dim font-mono">{d.time}</div>}
      {d.critical && <div className="text-[10px] mt-0.5 text-violet-600 dark:text-violet-400 font-medium inline-flex items-center gap-0.5"><Timer size={10} /> gargalo</div>}
      <Handle type="source" position={sourcePos} className="!bg-edge !border-edge" />
    </div>
  )
}

const nodeTypes = { job: JobNode }

export function DsRunGraphModal({
  open, onClose, rootJob, graphRuns, onDrill, loading, targetTime, path, onNavigate, onAutoTrace, tracing,
}: {
  open: boolean
  onClose: () => void
  rootJob: string
  graphRuns: DsRunGraph[]
  onDrill: (job: string, targetTime?: string) => void
  loading?: boolean
  targetTime?: string | null
  path?: string[]
  onNavigate?: (index: number) => void
  onAutoTrace?: () => void
  tracing?: boolean
}) {
  // Default: no drill, casa com o horário de quem chamou (targetTime); ao abrir
  // (sem targetTime), o run MAIS RECENTE.
  const defaultIdx = useMemo(() => {
    const t = targetTime ? dsParseTime(targetTime)?.getTime() : null
    if (t != null) {
      let best = -1, bestDelta = Infinity, contained = false
      graphRuns.forEach((r, i) => {
        const s = dsParseTime(r.start)?.getTime()
        if (s == null) return
        const e = dsParseTime(r.end)?.getTime()
        if (s <= t && (e == null || t <= e)) { if (!contained) { contained = true; best = i } }
        else if (!contained) { const dlt = Math.abs(s - t); if (dlt < bestDelta) { bestDelta = dlt; best = i } }
      })
      if (best >= 0) return best
    }
    return graphRuns.length - 1
  }, [graphRuns, targetTime])

  const [sel, setSel] = useState<number | null>(null)
  const [dir, setDir] = useState<Dir>('LR')
  const [showCritical, setShowCritical] = useState(false)
  const [filter, setFilter] = useState<Set<DsGraphStatus>>(new Set())
  useEffect(() => { setSel(null) }, [rootJob, targetTime])  // ao drillar, volta pro default
  const idx = sel ?? defaultIdx
  const g = graphRuns[idx]

  const toggleFilter = (s: DsGraphStatus) => setFilter(prev => {
    const next = new Set(prev); next.has(s) ? next.delete(s) : next.add(s); return next
  })

  // Filhos visíveis (após filtro de status).
  const visible = useMemo(
    () => (g ? g.children.filter(c => filter.size === 0 || filter.has(c.status)) : []),
    [g, filter],
  )

  // Gargalo = filho visível de maior duração (start→end). -1 se ninguém tem duração.
  const critical = useMemo(() => {
    let cidx = -1, durMs = -1
    visible.forEach((c, i) => {
      const s = dsParseTime(c.start)?.getTime(), e = dsParseTime(c.end)?.getTime()
      if (s != null && e != null && e - s > durMs) { durMs = e - s; cidx = i }
    })
    return { idx: cidx, durMs }
  }, [visible])

  const { nodes, edges } = useMemo(() => {
    if (!g) return { nodes: [] as Node[], edges: [] as Edge[] }
    const rootStatus: DsGraphStatus = g.result === 'ok' ? 'ok' : g.result === 'aborted' ? 'aborted'
      : g.result === 'running' ? 'running' : 'unknown'
    const n = visible.length
    const rootPos = dir === 'TB' ? { x: Math.max(0, (n - 1) * 140), y: 0 } : { x: 0, y: Math.max(0, (n - 1) * 35) }
    const nodes: Node[] = [{
      id: '__root__', type: 'job', position: rootPos,
      data: { label: rootJob, status: rootStatus, sub: statusLabel(rootStatus), isRoot: true, dir } as unknown as Record<string, unknown>,
    }]
    const e: Edge[] = []
    visible.forEach((c, i) => {
      const id = `c${i}`
      const isCrit = showCritical && i === critical.idx
      const pos = dir === 'TB' ? { x: i * 280, y: 200 } : { x: 360, y: i * 78 }
      nodes.push({
        id, type: 'job', position: pos,
        data: { label: c.job, status: c.status, sub: c.label || statusLabel(c.status), time: c.time, drillJob: c.job, targetTime: c.start, dir, critical: isCrit } as unknown as Record<string, unknown>,
      })
      e.push({
        id: `e${i}`, source: '__root__', target: id,
        animated: c.status === 'aborted' || isCrit,
        style: isCrit ? { stroke: '#8b5cf6', strokeWidth: 3 }
          : { stroke: c.status === 'aborted' ? '#ef4444' : c.status === 'warning' ? '#f59e0b' : '#94a3b8' },
      })
    })
    return { nodes, edges: e }
  }, [g, rootJob, dir, showCritical, critical.idx, visible])

  const onNodeClick = useCallback((_: unknown, node: Node) => {
    const d = node.data as unknown as JobNodeData
    if (d.drillJob) onDrill(d.drillJob, d.targetTime || g?.start)
  }, [onDrill, g])

  const canBack = !!path && path.length > 1

  return (
    <Modal open={open} onClose={onClose} title={`Diagrama do run — ${rootJob}`} size="2xl">
      <div className="flex flex-col gap-3">
        {/* breadcrumb / voltar */}
        {canBack && (
          <div className="flex items-center gap-2 flex-wrap text-xs">
            <button onClick={() => onNavigate?.(path!.length - 2)}
              className="inline-flex items-center gap-1 px-2 py-1 rounded-lg border border-edge bg-panel text-ink hover:bg-edge/40">
              <ArrowLeft size={13} /> Voltar
            </button>
            <span className="text-dim">|</span>
            <div className="flex items-center gap-1 flex-wrap">
              {path!.map((j, i) => (
                <span key={i} className="inline-flex items-center gap-1">
                  {i > 0 && <ChevronRight size={12} className="text-dim shrink-0" />}
                  {i < path!.length - 1
                    ? <button onClick={() => onNavigate?.(i)} className="font-mono text-blue-700 dark:text-blue-400 hover:underline">{j}</button>
                    : <span className="font-mono text-ink font-medium">{j}</span>}
                </span>
              ))}
            </div>
          </div>
        )}

        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs text-dim">Run:</span>
          <Select value={String(idx)} onChange={ev => setSel(Number(ev.target.value))} className="w-auto">
            {graphRuns.map((r, i) => (
              <option key={i} value={i}>
                {statusLabel(r.result === 'ok' ? 'ok' : r.result === 'aborted' ? 'aborted' : r.result === 'running' ? 'running' : 'unknown')}
                {' · '}{r.start ?? '—'}{' · '}{r.children.length} job(s)
              </option>
            ))}
          </Select>
          {/* direção do desenho */}
          <div className="inline-flex rounded-lg border border-edge overflow-hidden">
            <button onClick={() => setDir('LR')} title="Esquerda → direita"
              className={`px-2 py-1.5 text-xs flex items-center gap-1 ${dir === 'LR' ? 'bg-[#1A5FA8] text-white' : 'bg-panel text-dim hover:text-ink'}`}>
              <ArrowRight size={13} /> Horizontal
            </button>
            <button onClick={() => setDir('TB')} title="Cima → baixo"
              className={`px-2 py-1.5 text-xs flex items-center gap-1 border-l border-edge ${dir === 'TB' ? 'bg-[#1A5FA8] text-white' : 'bg-panel text-dim hover:text-ink'}`}>
              <ArrowDown size={13} /> Vertical
            </button>
          </div>
          {/* caminho crítico (sob demanda) */}
          {critical.idx >= 0 && (
            <button onClick={() => setShowCritical(v => !v)}
              title="Destaca o job mais demorado deste nível (gargalo)"
              className={`px-2 py-1.5 text-xs rounded-lg border flex items-center gap-1 ${showCritical ? 'bg-violet-600 text-white border-violet-600' : 'bg-panel text-dim border-edge hover:text-ink'}`}>
              <Timer size={13} /> Caminho crítico{showCritical && critical.durMs >= 0 ? ` · ${dsFmtDuration(critical.durMs)}` : ''}
            </button>
          )}
          {/* causa-raiz: desce sozinho pela cadeia de abortados */}
          {onAutoTrace && (
            <button onClick={onAutoTrace} disabled={tracing}
              title="Desce sozinho pela cadeia de jobs abortados até o job folha (causa-raiz)"
              className={`px-2 py-1.5 text-xs rounded-lg border flex items-center gap-1 ${tracing ? 'bg-panel text-dim border-edge opacity-60' : 'bg-panel text-ink border-edge hover:bg-edge/40'}`}>
              {tracing ? <Loader2 size={13} className="animate-spin" /> : <Crosshair size={13} />} Causa-raiz
            </button>
          )}
        </div>

        {/* filtro por status */}
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-xs text-dim">Filtrar:</span>
          {FILTERABLE.map(st => {
            const cnt = g ? g.children.filter(c => c.status === st).length : 0
            const active = filter.has(st)
            const Icon = STATUS[st].Icon
            return (
              <button key={st} onClick={() => toggleFilter(st)} disabled={cnt === 0}
                className={`px-2 py-1 rounded-lg text-[11px] border inline-flex items-center gap-1 transition-colors
                  ${cnt === 0 ? 'opacity-40 cursor-default border-edge text-dim' :
                    active ? 'bg-[#1A5FA8] text-white border-[#1A5FA8]' : 'bg-panel text-ink border-edge hover:bg-edge/40'}`}>
                <Icon size={11} className={active ? '' : STATUS[st].text} /> {statusLabel(st)} ({cnt})
              </button>
            )
          })}
          {filter.size > 0 && (
            <button onClick={() => setFilter(new Set())} className="text-[11px] text-dim hover:text-ink underline ml-1">limpar</button>
          )}
        </div>

        {g && g.children.length > 0 ? (
          visible.length > 0 ? (
            <>
              <p className="text-[11px] text-dim">Clique num job filho para abrir o log dele (drill-down) — os abortados têm a seta vermelha.</p>
              <div className="relative rounded-lg border border-edge bg-canvas" style={{ height: '58vh' }}>
                <ReactFlow
                  key={dir}
                  nodes={nodes} edges={edges} nodeTypes={nodeTypes} onNodeClick={onNodeClick}
                  fitView nodesDraggable={false} nodesConnectable={false} elementsSelectable={false}
                  minZoom={0.2}
                >
                  <Background />
                  <Controls showInteractive={false} />
                </ReactFlow>
                {loading && (
                  <div className="absolute inset-0 z-10 flex items-center justify-center bg-canvas/70 backdrop-blur-[1px]">
                    <div className="flex items-center gap-2 text-sm text-ink bg-panel border border-edge rounded-lg px-4 py-2 shadow">
                      <Loader2 size={16} className="animate-spin text-[#1A5FA8]" /> Carregando o log do job…
                    </div>
                  </div>
                )}
              </div>
            </>
          ) : (
            <p className="text-sm text-dim p-4">Nenhum job com o filtro selecionado neste run.</p>
          )
        ) : (
          <p className="text-sm text-dim p-4">
            Este run não tem jobs filhos detectados — provavelmente é um <strong>job folha</strong>.
            Feche e veja o erro técnico no card <strong>"Erros e avisos"</strong> (clique no <strong>#id</strong> do FATAL para o logdetail).
          </p>
        )}
      </div>
    </Modal>
  )
}
