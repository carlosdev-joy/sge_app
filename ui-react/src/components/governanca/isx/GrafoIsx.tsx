// Grafo do fluxo de um job (flow_json): um nó por stage, colorido pela direção,
// arestas com o nome do link; clicar no nó abre o painel do stage. Leiaute em
// camadas vem de lib/lineageIsx.leiaute (puro, testado na bancada); aqui é só
// @xyflow/react — o mesmo do editor de fluxo e do grafo da sequence do Console.
import { useMemo } from 'react'
import { ReactFlow, Background, Controls, Handle, Position, type Node, type Edge, type NodeProps } from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { useColorMode } from '../../etapas/useColorMode'
import { COR_DIRECAO, leiaute, type Direcao, type FluxoIsx, type StageIsx } from '../../../lib/lineageIsx'

interface DadosNo { nome: string; tipo: string; direcao: Direcao; selecionado: boolean; onSelecionar: (nome: string) => void }

function NoStage({ data }: NodeProps) {
  const d = data as unknown as DadosNo
  const cor = COR_DIRECAO[d.direcao]
  return (
    <div
      role="button" tabIndex={0} data-no-stage={d.nome} data-direcao={d.direcao}
      onClick={() => d.onSelecionar(d.nome)}
      onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); d.onSelecionar(d.nome) } }}
      className={`relative border-2 rounded-lg px-3 py-2 shadow-sm min-w-[160px] max-w-[240px] cursor-pointer bg-panel ${cor.borda} ${d.selecionado ? 'ring-2 ring-[#1A5FA8]/50' : ''}`}>
      <Handle type="target" position={Position.Left} className="!bg-edge !border-edge" />
      <div className="font-mono text-[11px] text-ink break-all leading-tight">{d.nome}</div>
      <div className={`text-[10px] mt-0.5 ${cor.texto}`}>{cor.rotulo}{d.tipo ? ` · ${d.tipo}` : ''}</div>
      <Handle type="source" position={Position.Right} className="!bg-edge !border-edge" />
    </div>
  )
}

const nodeTypes = { stage: NoStage }

interface Props {
  stages: StageIsx[]
  flow: FluxoIsx[]
  selecionado: string | null
  onSelecionar: (stage: string) => void
}

export function GrafoIsx({ stages, flow, selecionado, onSelecionar }: Props) {
  // Controls/Background/MiniMap do xyflow não leem o tema do app: precisam do colorMode
  // (o mesmo hook do FluxoEditor/MalhaEditor), senão ficam brancos no tema escuro.
  const colorMode = useColorMode()
  const { nos, arestas } = useMemo(() => leiaute(stages, flow), [stages, flow])
  const rfNodes: Node[] = useMemo(() => nos.map(n => ({
    id: n.id, type: 'stage', position: { x: n.x, y: n.y },
    data: { nome: n.nome, tipo: n.tipo, direcao: n.direcao, selecionado: n.id === selecionado, onSelecionar } as unknown as Record<string, unknown>,
  })), [nos, selecionado, onSelecionar])
  const rfEdges: Edge[] = useMemo(() => arestas.map(a => ({
    id: a.id, source: a.de, target: a.para, label: a.rotulo || undefined,
    style: { stroke: '#94a3b8', strokeWidth: 1.5 },
    labelStyle: { fill: 'rgb(var(--ink))', fontSize: 10 },
    labelBgStyle: { fill: 'rgb(var(--panel))', fillOpacity: 0.9 },
    labelBgPadding: [4, 2] as [number, number],
    labelBgBorderRadius: 4,
  })), [arestas])

  return (
    <div className="border border-edge bg-canvas rounded-lg" style={{ height: '52vh' }} data-grafo-isx data-nos={nos.length}>
      <ReactFlow nodes={rfNodes} edges={rfEdges} nodeTypes={nodeTypes} colorMode={colorMode}
        fitView nodesDraggable={false} nodesConnectable={false} minZoom={0.2}>
        <Background />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  )
}
