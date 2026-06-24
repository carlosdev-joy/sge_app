// Canvas React Flow (MOCKUP) — estilo designer de workflow da Informatica.
// Dados de exemplo hardcoded (não conecta à API). Foco em qualidade visual:
// node cards por tipo, nó de decisão em diamante, arestas de dependência,
// paleta de tipos + legenda, e os controles (minimapa/zoom/background).
import { useEffect, useMemo, useState } from 'react'
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  Panel,
  MarkerType,
  type Node,
  type Edge,
  type ColorMode,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { EtapaNode } from './EtapaNode'
import { DecisaoNode } from './DecisaoNode'
import { TYPE_META, TYPE_ORDER, type EtapaType } from './types'

const nodeTypes = { etapa: EtapaNode, decisao: DecisaoNode }

// ── Hook: tema vivo (claro/escuro) observando html.dark ─────────────────────
// O app alterna o tema por classe em document.documentElement (ver lib/theme.ts);
// o MutationObserver mantém o colorMode do React Flow em sincronia.
function useColorMode(): ColorMode {
  const read = (): ColorMode =>
    document.documentElement.classList.contains('dark') ? 'dark' : 'light'
  const [mode, setMode] = useState<ColorMode>(read)
  useEffect(() => {
    const obs = new MutationObserver(() => setMode(read()))
    obs.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['class'],
    })
    return () => obs.disconnect()
  }, [])
  return mode
}

// ── Dados de exemplo (mini-pipeline realista) ───────────────────────────────
const initialNodes: Node[] = [
  {
    id: 'n1',
    type: 'etapa',
    position: { x: 0, y: 60 },
    data: { name: 'Extract_Clientes', type: 'datastage', command: 'BiCvp.Extract_01', order: 1 },
  },
  {
    id: 'n2',
    type: 'etapa',
    position: { x: 260, y: 60 },
    data: { name: 'Stage_Clientes', type: 'datastage', command: 'BiCvp.Stage_Clientes', order: 2 },
  },
  {
    id: 'n3',
    type: 'decisao',
    position: { x: 540, y: 78 },
    data: { name: 'Valida_Volume', condition: 'volume > 1M ?' },
  },
  {
    id: 'n4',
    type: 'etapa',
    position: { x: 760, y: -10 },
    data: { name: 'Load_Full', type: 'storedproc', command: 'dbo.sp_load_full', order: 4 },
  },
  {
    id: 'n5',
    type: 'etapa',
    position: { x: 760, y: 150 },
    data: { name: 'Load_Incremental', type: 'python', command: 'etl.load_incremental', order: 4 },
  },
  {
    id: 'n6',
    type: 'etapa',
    position: { x: 1040, y: 70 },
    data: { name: 'Notifica_Fim', type: 'shell', command: '/opt/scripts/notify.sh', order: 5 },
  },
]

const EDGE_BASE = {
  type: 'smoothstep' as const,
  markerEnd: { type: MarkerType.ArrowClosed, width: 16, height: 16 },
}

const initialEdges: Edge[] = [
  { id: 'e1', source: 'n1', target: 'n2', ...EDGE_BASE },
  { id: 'e2', source: 'n2', target: 'n3', ...EDGE_BASE },
  {
    id: 'e3',
    source: 'n3',
    sourceHandle: 'sim',
    target: 'n4',
    label: 'sim',
    ...EDGE_BASE,
    style: { stroke: '#22c55e' },
    labelStyle: { fill: '#15803d', fontSize: 11, fontWeight: 700 },
  },
  {
    id: 'e4',
    source: 'n3',
    sourceHandle: 'nao',
    target: 'n5',
    label: 'não',
    ...EDGE_BASE,
    style: { stroke: '#94a3b8' },
    labelStyle: { fill: '#64748b', fontSize: 11, fontWeight: 700 },
  },
  { id: 'e5', source: 'n4', target: 'n6', ...EDGE_BASE },
  { id: 'e6', source: 'n5', target: 'n6', ...EDGE_BASE },
]

// ── Paleta de tipos (top-left) ──────────────────────────────────────────────
function Paleta() {
  return (
    <div className="w-52 rounded-lg border border-edge bg-panel/95 p-2.5 shadow-md backdrop-blur">
      <p className="px-0.5 pb-1.5 text-[11px] font-semibold uppercase tracking-wide text-dim">
        Tipos de etapa
      </p>
      <p className="px-0.5 pb-2 text-[10px] text-dim">
        arraste para o canvas
      </p>
      <div className="flex flex-col gap-1">
        {TYPE_ORDER.map((t: EtapaType) => {
          const meta = TYPE_META[t]
          const Icon = meta.icon
          return (
            <div
              key={t}
              className="flex cursor-grab items-center gap-2 rounded-md border border-transparent px-1.5 py-1 hover:border-edge hover:bg-edge/30 active:cursor-grabbing"
            >
              <span className={`flex h-6 w-6 items-center justify-center rounded ${meta.chip}`}>
                <Icon size={13} strokeWidth={2.2} />
              </span>
              <span className="text-xs font-medium text-ink">{meta.label}</span>
            </div>
          )
        })}
      </div>

      {/* Legenda de cores */}
      <div className="mt-2.5 border-t border-edge pt-2">
        <p className="px-0.5 pb-1.5 text-[10px] font-semibold uppercase tracking-wide text-dim">
          Legenda
        </p>
        <div className="grid grid-cols-2 gap-x-2 gap-y-1 px-0.5">
          {TYPE_ORDER.map((t) => (
            <span key={t} className="flex items-center gap-1.5 text-[10px] text-dim">
              <span className={`h-2 w-2 rounded-full ${TYPE_META[t].dot}`} />
              {TYPE_META[t].label}
            </span>
          ))}
          <span className="flex items-center gap-1.5 text-[10px] text-dim">
            <span className="h-2 w-2 rotate-45 rounded-[1px] bg-indigo-500" />
            Decisão
          </span>
        </div>
      </div>
    </div>
  )
}

export function EtapasCanvas() {
  const colorMode = useColorMode()

  const miniMapColor = useMemo(
    () => (node: Node) => {
      if (node.type === 'decisao') return '#6366f1'
      const t = (node.data as { type?: EtapaType }).type
      return (t && TYPE_META[t]?.hex) || '#94a3b8'
    },
    [],
  )

  return (
    <div className="h-full w-full overflow-hidden rounded-xl border border-edge bg-canvas">
      <ReactFlow
        nodes={initialNodes}
        edges={initialEdges}
        nodeTypes={nodeTypes}
        colorMode={colorMode}
        fitView
        fitViewOptions={{ padding: 0.25 }}
        proOptions={{ hideAttribution: true }}
        defaultEdgeOptions={{ type: 'smoothstep' }}
      >
        <Background gap={18} size={1} />
        <Controls />
        <MiniMap
          pannable
          zoomable
          nodeColor={miniMapColor}
          nodeStrokeWidth={2}
          className="!bg-panel"
        />
        <Panel position="top-left">
          <Paleta />
        </Panel>
      </ReactFlow>
    </div>
  )
}
