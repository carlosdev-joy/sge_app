// Editor interativo de fluxo de etapas (Etapa 1) — canvas React Flow conectado
// à API. Carrega o grafo do pipeline (GET /pipelines/{p}/fluxo), permite mover
// nós e editar as dependências NORMAIS (arrastar p/ conectar, deletar aresta),
// e persiste tudo (POST /pipelines/{p}/fluxo) materializando o grafo. As arestas
// de RAMO de decisão (sim/não) são exibidas read-only — editar ramos é a Etapa 2.
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  Panel,
  MarkerType,
  useNodesState,
  useEdgesState,
  applyNodeChanges,
  addEdge,
  type Node,
  type Edge,
  type Connection,
  type NodeChange,
  type EdgeChange,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { apiFetch } from '../../lib/api'
import { Button } from '../ui/Button'
import { Modal } from '../ui/Modal'
import { toast } from '../ui/Toast'
import { Save, RefreshCw, AlertCircle } from 'lucide-react'
import { EtapaNode, type EtapaNodeData } from './EtapaNode'
import { DecisaoNode } from './DecisaoNode'
import { TYPE_META, TYPE_ORDER, type EtapaType } from './types'
import { useColorMode } from './useColorMode'

const nodeTypes = { etapa: EtapaNode, decisao: DecisaoNode }

// ── Tipos do payload da API (/fluxo) ────────────────────────────────────────
interface Condition {
  ramo_verdadeiro?: string[]
  ramo_falso?: string[]
  [k: string]: unknown
}
interface FluxoNode {
  job_name: string
  job_type: string
  job_command: string | null
  execution_order: number
  depends_on_jobs: string[]
  condition: Condition | null
  layout_x: number | null
  layout_y: number | null
}
interface FluxoResp { nodes: FluxoNode[] }

// ── Layout automático em camadas por execution_order ────────────────────────
// x = (ordem-1)*280; nós da mesma ordem empilham em y = i*140.
const COL_W = 280
const ROW_H = 140
function autoLayout(apiNodes: FluxoNode[]): Record<string, { x: number; y: number }> {
  const byOrder = new Map<number, FluxoNode[]>()
  for (const n of apiNodes) {
    const o = n.execution_order ?? 1
    if (!byOrder.has(o)) byOrder.set(o, [])
    byOrder.get(o)!.push(n)
  }
  const orders = Array.from(byOrder.keys()).sort((a, b) => a - b)
  const pos: Record<string, { x: number; y: number }> = {}
  orders.forEach((o, col) => {
    byOrder.get(o)!.forEach((n, i) => {
      pos[n.job_name] = { x: col * COL_W, y: i * ROW_H }
    })
  })
  return pos
}

// Mapeia o job_type da API para um EtapaType conhecido (fallback p/ datastage).
function toEtapaType(t: string): EtapaType {
  return (TYPE_ORDER as string[]).includes(t) ? (t as EtapaType) : 'datastage'
}

// ── Construção de nós/arestas a partir do payload ───────────────────────────
const EDGE_ARROW = { type: MarkerType.ArrowClosed, width: 16, height: 16 }

function buildNodes(apiNodes: FluxoNode[]): Node[] {
  // Usa posição salva (ambos não-nulos) ou auto-layout.
  const auto = autoLayout(apiNodes)
  return apiNodes.map((n) => {
    const hasPos = n.layout_x != null && n.layout_y != null
    const position = hasPos
      ? { x: n.layout_x as number, y: n.layout_y as number }
      : auto[n.job_name] ?? { x: 0, y: 0 }
    if (n.job_type === 'decisao') {
      return {
        id: n.job_name,
        type: 'decisao' as const,
        position,
        data: { name: n.job_name, condition: n.job_command || 'decisão' },
      }
    }
    const data: EtapaNodeData = {
      name: n.job_name,
      type: toEtapaType(n.job_type),
      command: n.job_command || '—',
      order: n.execution_order,
    }
    return { id: n.job_name, type: 'etapa' as const, position, data }
  })
}

function buildEdges(apiNodes: FluxoNode[]): Edge[] {
  const edges: Edge[] = []
  const isDecisao = new Set(apiNodes.filter(n => n.job_type === 'decisao').map(n => n.job_name))

  // Arestas NORMAIS (editáveis): dep → job, a partir de depends_on_jobs.
  for (const n of apiNodes) {
    for (const dep of n.depends_on_jobs || []) {
      // Se a origem é uma decisão, a ligação real é via ramo (abaixo), não dep.
      if (isDecisao.has(dep)) continue
      edges.push({
        id: `dep:${dep}->${n.job_name}`,
        source: dep,
        target: n.job_name,
        type: 'smoothstep',
        markerEnd: EDGE_ARROW,
      })
    }
  }

  // Arestas de RAMO de decisão (read-only nesta etapa): D → membros.
  for (const d of apiNodes) {
    if (d.job_type !== 'decisao' || !d.condition) continue
    const sim = d.condition.ramo_verdadeiro || []
    const nao = d.condition.ramo_falso || []
    for (const m of sim) {
      edges.push({
        id: `ramo:${d.job_name}:sim:${m}`,
        source: d.job_name,
        sourceHandle: 'sim',
        target: m,
        type: 'smoothstep',
        markerEnd: EDGE_ARROW,
        deletable: false,
        data: { branch: true },
        style: { stroke: '#22c55e' },
        label: 'sim',
        labelStyle: { fill: '#15803d', fontSize: 11, fontWeight: 700 },
      })
    }
    for (const m of nao) {
      edges.push({
        id: `ramo:${d.job_name}:nao:${m}`,
        source: d.job_name,
        sourceHandle: 'nao',
        target: m,
        type: 'smoothstep',
        markerEnd: EDGE_ARROW,
        deletable: false,
        data: { branch: true },
        style: { stroke: '#94a3b8' },
        label: 'não',
        labelStyle: { fill: '#64748b', fontSize: 11, fontWeight: 700 },
      })
    }
  }
  return edges
}

const isBranch = (e: Edge) => !!(e.data as { branch?: boolean } | undefined)?.branch

// ── Legenda de cores (canto inferior-esquerdo) ──────────────────────────────
function Legenda() {
  return (
    <div className="rounded-lg border border-edge bg-panel/95 p-2.5 shadow-md backdrop-blur">
      <p className="px-0.5 pb-1.5 text-[10px] font-semibold uppercase tracking-wide text-dim">
        Legenda
      </p>
      <div className="grid grid-cols-2 gap-x-3 gap-y-1 px-0.5">
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
      <div className="mt-2 border-t border-edge pt-1.5">
        <span className="flex items-center gap-1.5 text-[10px] text-dim">
          <span className="h-0.5 w-4 rounded bg-green-500" /> ramo sim
          <span className="ml-2 h-0.5 w-4 rounded bg-slate-400" /> ramo não
        </span>
        <p className="mt-1 px-0.5 text-[10px] text-dim">
          Paleta de etapas (arrastar p/ criar): <span className="italic">em breve</span>
        </p>
      </div>
    </div>
  )
}

interface Props {
  pipeline: string
}

export function FluxoEditor({ pipeline }: Props) {
  const qc = useQueryClient()
  const colorMode = useColorMode()
  const [nodes, setNodes] = useNodesState<Node>([])
  const [edges, setEdges, onEdgesChangeRF] = useEdgesState<Edge>([])
  const [dirty, setDirty] = useState(false)
  const [saving, setSaving] = useState(false)
  const [showPublish, setShowPublish] = useState(false)
  const [publishing, setPublishing] = useState(false)

  // Guarda os nós da API (job_type, ordem) para o cálculo de save e re-layout.
  const apiNodesRef = useRef<FluxoNode[]>([])
  // Conjunto de nós de decisão (origens cujas arestas viram ramos, não deps).
  const decisaoSet = useMemo(
    () => new Set(nodes.filter(n => n.type === 'decisao').map(n => n.id)),
    [nodes],
  )

  const { data, isLoading, isError, error } = useQuery<FluxoResp>({
    queryKey: ['fluxo', pipeline],
    queryFn: () => apiFetch(`/pipelines/${encodeURIComponent(pipeline)}/fluxo`),
    enabled: !!pipeline,
  })

  // Monta nós/arestas ao chegar o payload (ou ao trocar de pipeline).
  useEffect(() => {
    if (!data) return
    apiNodesRef.current = data.nodes
    setNodes(buildNodes(data.nodes))
    setEdges(buildEdges(data.nodes))
    setDirty(false)
  }, [data, setNodes, setEdges])

  // Mover/selecionar nó → aplica e marca dirty quando muda posição.
  const onNodesChange = useCallback(
    (changes: NodeChange<Node>[]) => {
      setNodes(nds => applyNodeChanges(changes, nds))
      if (changes.some(c => c.type === 'position' && c.dragging === false)) setDirty(true)
    },
    [setNodes],
  )

  // Conectar — só cria aresta NORMAL se a origem for um nó `etapa`.
  // Ignora origem `decisao` (ramos são Etapa 2) e evita duplicadas.
  const onConnect = useCallback(
    (conn: Connection) => {
      if (!conn.source || !conn.target) return
      if (decisaoSet.has(conn.source)) {
        toast.info('Conexões a partir de uma decisão (ramos sim/não) são editadas na Etapa 2.')
        return
      }
      const exists = edges.some(e => e.source === conn.source && e.target === conn.target)
      if (exists) return
      setEdges(eds =>
        addEdge(
          {
            id: `dep:${conn.source}->${conn.target}`,
            source: conn.source!,
            target: conn.target!,
            type: 'smoothstep',
            markerEnd: EDGE_ARROW,
          },
          eds,
        ),
      )
      setDirty(true)
    },
    [edges, decisaoSet, setEdges],
  )

  // Deletar arestas — bloqueia as de ramo (não deletáveis).
  const onEdgesChange = useCallback(
    (changes: EdgeChange<Edge>[]) => {
      const filtered = changes.filter(c => {
        if (c.type !== 'remove') return true
        const e = edges.find(x => x.id === c.id)
        return e ? !isBranch(e) : true
      })
      if (filtered.length !== changes.length) {
        toast.info('Arestas de ramo de decisão (sim/não) não podem ser removidas aqui.')
      }
      onEdgesChangeRF(filtered)
      if (filtered.some(c => c.type === 'remove')) setDirty(true)
    },
    [edges, onEdgesChangeRF],
  )

  const onEdgesDelete = useCallback(
    (deleted: Edge[]) => {
      // Reinsere qualquer aresta de ramo que tenha escapado (defensivo).
      const branch = deleted.filter(isBranch)
      if (branch.length) setEdges(eds => [...eds, ...branch])
    },
    [setEdges],
  )

  // Re-roda o auto-layout (recoloca os nós em camadas por ordem).
  const reorganizar = useCallback(() => {
    const pos = autoLayout(apiNodesRef.current)
    setNodes(nds => nds.map(n => (pos[n.id] ? { ...n, position: pos[n.id] } : n)))
    setDirty(true)
  }, [setNodes])

  // ── Salvar: materializa o grafo (todos os nós) com deps + posição ─────────
  async function salvar() {
    setSaving(true)
    try {
      const decisoes = new Set(nodes.filter(n => n.type === 'decisao').map(n => n.id))
      // depends_on_jobs[N] = origens das arestas NORMAIS que chegam em N,
      // EXCLUINDO arestas cuja origem é uma decisão (essas são ramos →
      // condition_json, não dependência).
      const depsByTarget = new Map<string, Set<string>>()
      for (const e of edges) {
        if (isBranch(e)) continue
        if (decisoes.has(e.source)) continue
        if (!depsByTarget.has(e.target)) depsByTarget.set(e.target, new Set())
        depsByTarget.get(e.target)!.add(e.source)
      }
      const payload = {
        nodes: nodes.map(n => ({
          job_name: n.id,
          depends_on_jobs: Array.from(depsByTarget.get(n.id) ?? []),
          layout_x: Math.round(n.position.x),
          layout_y: Math.round(n.position.y),
        })),
      }
      await apiFetch(`/pipelines/${encodeURIComponent(pipeline)}/fluxo`, {
        method: 'POST',
        body: JSON.stringify(payload),
      })
      toast.success('Fluxo salvo com sucesso.')
      setDirty(false)
      qc.invalidateQueries({ queryKey: ['fluxo', pipeline] })
      setShowPublish(true)
    } catch (e: any) {
      const msg = e?.message ?? ''
      if (msg.startsWith('400') || /ciclo|cycle/i.test(msg)) {
        toast.error('Ciclo detectado no fluxo — ajuste as dependências.')
      } else {
        toast.error(msg || 'Erro ao salvar o fluxo.')
      }
    } finally {
      setSaving(false)
    }
  }

  // Regenerar a DAG (mesmo endpoint do botão Publicar/gerar DAG).
  async function publicar() {
    setPublishing(true)
    try {
      await apiFetch(`/pipelines/${encodeURIComponent(pipeline)}/gerar-dag`, { method: 'POST' })
      toast.success('Geração da nova versão da DAG disparada.')
      setShowPublish(false)
    } catch (e: any) {
      toast.error(e?.message || 'Falha ao disparar a geração da DAG.')
    } finally {
      setPublishing(false)
    }
  }

  const miniMapColor = useMemo(
    () => (node: Node) => {
      if (node.type === 'decisao') return '#6366f1'
      const t = (node.data as { type?: EtapaType }).type
      return (t && TYPE_META[t]?.hex) || '#94a3b8'
    },
    [],
  )

  if (isLoading) {
    return (
      <div className="flex h-full w-full items-center justify-center rounded-xl border border-edge bg-canvas text-sm text-dim">
        Carregando fluxo…
      </div>
    )
  }
  if (isError) {
    return (
      <div className="flex h-full w-full flex-col items-center justify-center gap-2 rounded-xl border border-edge bg-canvas text-sm">
        <AlertCircle size={20} className="text-red-600 dark:text-red-400" />
        <span className="text-ink">Não foi possível carregar o fluxo.</span>
        <span className="text-xs text-dim">{(error as Error)?.message}</span>
      </div>
    )
  }
  if (nodes.length === 0) {
    return (
      <div className="flex h-full w-full flex-col items-center justify-center gap-1 rounded-xl border border-edge bg-canvas text-dim">
        <span className="text-3xl">⬡</span>
        <p className="text-sm font-medium">Nenhuma etapa neste pipeline</p>
        <p className="text-xs">Adicione etapas no modo Lista para montar o fluxo.</p>
      </div>
    )
  }

  return (
    <div className="relative h-full w-full overflow-hidden rounded-xl border border-edge bg-canvas">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onEdgesDelete={onEdgesDelete}
        onConnect={onConnect}
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

        {/* Barra de ações (topo) */}
        <Panel position="top-right">
          <div className="flex items-center gap-2 rounded-lg border border-edge bg-panel/95 px-2.5 py-2 shadow-md backdrop-blur">
            {dirty && (
              <span className="flex items-center gap-1 rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-[11px] font-semibold text-amber-700 dark:border-amber-800 dark:bg-amber-900/30 dark:text-amber-300">
                <span className="h-1.5 w-1.5 rounded-full bg-amber-500" />
                alterações não salvas
              </span>
            )}
            <Button
              variant="secondary"
              size="sm"
              onClick={reorganizar}
              title="Recoloca os nós em camadas por ordem"
            >
              <RefreshCw size={13} /> Reorganizar
            </Button>
            <Button size="sm" onClick={salvar} loading={saving} disabled={!dirty}>
              <Save size={13} /> Salvar fluxo
            </Button>
          </div>
        </Panel>

        <Panel position="bottom-left">
          <Legenda />
        </Panel>
      </ReactFlow>

      {/* Modal: publicar nova versão da DAG após salvar */}
      <Modal
        open={showPublish}
        onClose={() => setShowPublish(false)}
        title="Fluxo salvo"
        size="sm"
      >
        <div className="flex flex-col gap-4">
          <p className="text-sm text-dim">
            O fluxo do pipeline{' '}
            <span className="font-mono text-ink font-medium">{pipeline}</span> foi salvo.
            Deseja publicar uma nova versão da DAG agora?
          </p>
          <p className="rounded-lg border border-blue-200 bg-blue-50 px-3 py-2 text-xs text-blue-800 dark:border-blue-800/40 dark:bg-blue-900/15 dark:text-blue-300">
            A publicação dispara a geração da DAG (etl_dag_factory) no Airflow com as
            dependências e posições recém-salvas.
          </p>
          <div className="flex justify-end gap-2 border-t border-edge pt-3">
            <Button variant="secondary" onClick={() => setShowPublish(false)}>
              Agora não
            </Button>
            <Button onClick={publicar} loading={publishing}>
              Publicar nova versão
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  )
}
