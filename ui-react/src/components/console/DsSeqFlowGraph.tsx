import { useMemo } from 'react'
import {
  ReactFlow, Background, Controls, Handle, Position,
  type Node, type Edge, type NodeProps,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'

// Diagrama do fluxo REAL de uma Sequence, lido do export XML do DataStage.
// Mostra as atividades (nós) e as dependências/condições (arestas) — idêntico
// ao desenho da sequence no Designer. Os dados vêm do endpoint /datastage/seq-flow;
// aqui só fazemos o layout em camadas (longest-path) e a renderização.

export interface SeqFlowNode { id: string; name: string; type: string; jobname?: string | null }
export interface SeqFlowEdge { source: string; target: string; label: string; cond: string; expr?: string | null }

interface FlowNodeData { name: string; type: string; jobname?: string | null }

// Cor da borda/realce por tipo de atividade (par claro + escuro sempre).
function typeAccent(type: string): string {
  const t = (type || '').toLowerCase()
  if (t.includes('job')) return 'border-blue-300 dark:border-blue-700'
  if (t.includes('sequencer')) return 'border-violet-300 dark:border-violet-700'
  if (t.includes('terminator') || t.includes('exce')) return 'border-red-300 dark:border-red-700'
  if (t.includes('comando') || t.includes('rotina') || t.includes('vari')) return 'border-amber-300 dark:border-amber-700'
  return 'border-edge'
}

function FlowNode({ data }: NodeProps) {
  const d = data as unknown as FlowNodeData
  const showJob = d.jobname && d.jobname !== d.name
  return (
    <div className={`bg-panel border rounded-lg px-3 py-2 shadow-sm min-w-[150px] max-w-[240px] ${typeAccent(d.type)}`}>
      <Handle type="target" position={Position.Left} className="!bg-edge !border-edge" />
      <div className="font-mono text-[11px] text-ink break-all leading-tight">{d.name}</div>
      <div className="text-[10px] text-dim mt-0.5">{d.type}</div>
      {showJob && <div className="font-mono text-[10px] text-dim break-all mt-0.5">→ {d.jobname}</div>}
      <Handle type="source" position={Position.Right} className="!bg-edge !border-edge" />
    </div>
  )
}

const nodeTypes = { flow: FlowNode }

// Estilo da aresta por condição (cores fixas hex — válidas nos dois temas).
function edgeStyle(cond: string): { style: React.CSSProperties; animated: boolean } {
  if (cond === 'falhou') return { style: { stroke: '#ef4444', strokeWidth: 1.5 }, animated: false }
  if (cond === 'condicional' || cond === 'custom' || cond === 'retorno')
    return { style: { stroke: '#f59e0b', strokeWidth: 1.5 }, animated: true }
  return { style: { stroke: '#94a3b8', strokeWidth: 1.5 }, animated: false }
}

export function DsSeqFlowGraph({ nodes, edges }: { nodes: SeqFlowNode[]; edges: SeqFlowEdge[] }) {
  const { rfNodes, rfEdges } = useMemo(() => {
    const ids = new Set(nodes.map(n => n.id))
    // arestas válidas (source/target presentes nos nós)
    const validEdges = edges.filter(e => ids.has(e.source) && ids.has(e.target))

    // 1) adjacência + grau de entrada
    const succ = new Map<string, string[]>()
    const indeg = new Map<string, number>()
    for (const n of nodes) { succ.set(n.id, []); indeg.set(n.id, 0) }
    for (const e of validEdges) {
      succ.get(e.source)!.push(e.target)
      indeg.set(e.target, (indeg.get(e.target) ?? 0) + 1)
    }

    // 2) nível por longest-path (Kahn topológico)
    const level = new Map<string, number>()
    for (const n of nodes) level.set(n.id, 0)
    const rem = new Map(indeg)
    const queue: string[] = nodes.filter(n => (indeg.get(n.id) ?? 0) === 0).map(n => n.id)
    if (queue.length === 0) nodes.forEach(n => queue.push(n.id))  // grafo só com ciclos: começa por todos
    const cap = nodes.length * nodes.length + nodes.length + 10  // proteção contra ciclo
    let it = 0
    while (queue.length && it < cap) {
      it++
      const u = queue.shift()!
      for (const v of succ.get(u) ?? []) {
        level.set(v, Math.max(level.get(v) ?? 0, (level.get(u) ?? 0) + 1))
        const r = (rem.get(v) ?? 0) - 1
        rem.set(v, r)
        if (r === 0) queue.push(v)
      }
    }
    // nós não nivelados (presos em ciclo) ficam no nível 0 — já é o default.

    // 3) posição: x = nível * 300; y = índice no nível * 96
    const byLevel = new Map<number, string[]>()
    for (const n of nodes) {
      const lv = level.get(n.id) ?? 0
      if (!byLevel.has(lv)) byLevel.set(lv, [])
      byLevel.get(lv)!.push(n.id)
    }
    const pos = new Map<string, { x: number; y: number }>()
    const maxRows = Math.max(1, ...[...byLevel.values()].map(a => a.length))
    for (const [lv, list] of byLevel) {
      const offset = (maxRows - list.length) * 96 / 2  // centraliza verticalmente cada coluna
      list.forEach((id, i) => pos.set(id, { x: lv * 300, y: offset + i * 96 }))
    }

    const rfNodes: Node[] = nodes.map(n => ({
      id: n.id,
      type: 'flow',
      position: pos.get(n.id) ?? { x: 0, y: 0 },
      data: { name: n.name, type: n.type, jobname: n.jobname ?? null } as unknown as Record<string, unknown>,
    }))

    const rfEdges: Edge[] = validEdges.map((e, i) => {
      const { style, animated } = edgeStyle(e.cond)
      return {
        id: `e${i}`,
        source: e.source,
        target: e.target,
        label: e.label || undefined,
        animated,
        style,
        labelStyle: { fill: 'rgb(var(--ink))', fontSize: 10 },
        labelBgStyle: { fill: 'rgb(var(--panel))', fillOpacity: 0.9 },
        labelBgPadding: [4, 2] as [number, number],
        labelBgBorderRadius: 4,
        data: e.expr ? { expr: e.expr } : undefined,
      }
    })

    return { rfNodes, rfEdges }
  }, [nodes, edges])

  return (
    <div className="border border-edge bg-canvas rounded-lg" style={{ height: '62vh' }}>
      <ReactFlow
        nodes={rfNodes} edges={rfEdges} nodeTypes={nodeTypes}
        fitView nodesDraggable={false} nodesConnectable={false}
        minZoom={0.2}
      >
        <Background />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  )
}
