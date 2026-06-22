import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  ReactFlow, Background, Controls, Handle, Position,
  type Node, type Edge, type NodeProps,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { Modal } from '../ui/Modal'
import { Select } from '../ui/Input'
import { CheckCircle2, XCircle, AlertTriangle, RotateCcw, Clock, HelpCircle } from 'lucide-react'

// Diagrama do run de uma sequence (estilo CTRL-M): a sequence + seus filhos diretos,
// com o status real daquele run. Clicar num filho faz o drill-down (abre o log dele).
// Os dados vêm do logsum já parseado no console — sem chamada nova ao backend.

export type DsGraphStatus = 'ok' | 'warning' | 'aborted' | 'reset' | 'running' | 'unknown'
export interface DsGraphNode { job: string; status: DsGraphStatus; label: string }
export interface DsRunGraph { result: 'ok' | 'aborted' | 'running' | 'unknown'; start?: string; end?: string; children: DsGraphNode[] }

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

interface JobNodeData { label: string; status: DsGraphStatus; sub?: string; isRoot?: boolean; drillJob?: string }

function JobNode({ data }: NodeProps) {
  const d = data as unknown as JobNodeData
  const s = STATUS[d.status] ?? STATUS.unknown
  const Icon = s.Icon
  return (
    <div
      className={`rounded-lg border px-3 py-2 shadow-sm min-w-[180px] max-w-[260px] ${s.box} ${d.drillJob ? 'cursor-pointer hover:ring-2 hover:ring-[#1A5FA8]' : ''}`}
      title={d.drillJob ? `Abrir o log de ${d.label} (drill-down)` : d.label}
    >
      {!d.isRoot && <Handle type="target" position={Position.Left} className="!bg-edge !border-edge" />}
      <div className="flex items-center gap-1.5">
        <Icon size={14} className={`${s.text} shrink-0`} />
        <span className="font-mono text-[11px] text-ink break-all leading-tight">{d.label}</span>
      </div>
      {d.sub && <div className={`text-[10px] mt-0.5 ${s.text}`}>{d.sub}</div>}
      <Handle type="source" position={Position.Right} className="!bg-edge !border-edge" />
    </div>
  )
}

const nodeTypes = { job: JobNode }

export function DsRunGraphModal({
  open, onClose, rootJob, graphRuns, onDrill,
}: {
  open: boolean
  onClose: () => void
  rootJob: string
  graphRuns: DsRunGraph[]
  onDrill: (job: string) => void
}) {
  // Default: run abortado mais recente; senão, o último run.
  const defaultIdx = useMemo(() => {
    for (let i = graphRuns.length - 1; i >= 0; i--) if (graphRuns[i].result === 'aborted') return i
    return graphRuns.length - 1
  }, [graphRuns])
  const [sel, setSel] = useState<number | null>(null)
  useEffect(() => { setSel(null) }, [rootJob])  // ao drillar, volta pro default do novo job
  const idx = sel ?? defaultIdx
  const g = graphRuns[idx]

  const { nodes, edges } = useMemo(() => {
    if (!g) return { nodes: [] as Node[], edges: [] as Edge[] }
    const rootStatus: DsGraphStatus = g.result === 'ok' ? 'ok' : g.result === 'aborted' ? 'aborted'
      : g.result === 'running' ? 'running' : 'unknown'
    const n: Node[] = [{
      id: '__root__', type: 'job',
      position: { x: 0, y: Math.max(0, (g.children.length - 1) * 35) },
      data: { label: rootJob, status: rootStatus, sub: statusLabel(rootStatus), isRoot: true } as unknown as Record<string, unknown>,
    }]
    const e: Edge[] = []
    g.children.forEach((c, i) => {
      const id = `c${i}`
      n.push({
        id, type: 'job', position: { x: 340, y: i * 72 },
        data: { label: c.job, status: c.status, sub: c.label || statusLabel(c.status), drillJob: c.job } as unknown as Record<string, unknown>,
      })
      e.push({
        id: `e${i}`, source: '__root__', target: id,
        animated: c.status === 'aborted',
        style: { stroke: c.status === 'aborted' ? '#ef4444' : c.status === 'warning' ? '#f59e0b' : '#94a3b8' },
      })
    })
    return { nodes: n, edges: e }
  }, [g, rootJob])

  const onNodeClick = useCallback((_: unknown, node: Node) => {
    const job = (node.data as unknown as JobNodeData).drillJob
    if (job) onDrill(job)
  }, [onDrill])

  return (
    <Modal open={open} onClose={onClose} title={`Diagrama do run — ${rootJob}`} size="2xl">
      <div className="flex flex-col gap-3">
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
          {/* legenda */}
          <span className="ml-auto flex flex-wrap items-center gap-2 text-[11px] text-dim">
            <span className="inline-flex items-center gap-1"><CheckCircle2 size={12} className="text-green-600 dark:text-green-400" />Concluído</span>
            <span className="inline-flex items-center gap-1"><AlertTriangle size={12} className="text-amber-600 dark:text-yellow-400" />Avisos</span>
            <span className="inline-flex items-center gap-1"><XCircle size={12} className="text-red-600 dark:text-red-400" />Abortado</span>
            <span className="inline-flex items-center gap-1"><Clock size={12} className="text-blue-600 dark:text-blue-400" />Em execução</span>
          </span>
        </div>

        {g && g.children.length > 0 ? (
          <>
            <p className="text-[11px] text-dim">Clique num job filho para abrir o log dele (drill-down) — os abortados têm a seta vermelha.</p>
            <div className="rounded-lg border border-edge bg-canvas" style={{ height: '60vh' }}>
              <ReactFlow
                nodes={nodes} edges={edges} nodeTypes={nodeTypes} onNodeClick={onNodeClick}
                fitView nodesDraggable={false} nodesConnectable={false} elementsSelectable={false}
                minZoom={0.2}
              >
                <Background />
                <Controls showInteractive={false} />
              </ReactFlow>
            </div>
          </>
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
