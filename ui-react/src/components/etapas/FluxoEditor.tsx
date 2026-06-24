// Editor interativo de fluxo de etapas — canvas React Flow conectado à API.
// Carrega o grafo do pipeline (GET /pipelines/{p}/fluxo), permite mover nós,
// editar dependências NORMAIS (arrastar p/ conectar, deletar aresta), CRIAR nós
// (paleta arrastar-para-criar), EDITAR a condição/ramos de decisões, EXCLUIR nós
// e persiste tudo (POST /pipelines/{p}/fluxo) materializando o grafo.
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  ReactFlow,
  ReactFlowProvider,
  Background,
  Controls,
  MiniMap,
  Panel,
  MarkerType,
  useReactFlow,
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
import { Input, Select, Textarea } from '../ui/Input'
import { Modal } from '../ui/Modal'
import { toast } from '../ui/Toast'
import { Save, RefreshCw, AlertCircle, GitBranch, Trash2 } from 'lucide-react'
import { EtapaNode, type EtapaNodeData } from './EtapaNode'
import { DecisaoNode, type DecisaoNodeData, type NodeCondition } from './DecisaoNode'
import { TYPE_META, TYPE_ORDER, CREATABLE_TYPES, type EtapaType } from './types'
import { COND_OPERADORES, defaultCondition, toNodeCondition, conditionLabel } from './condition'
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
const SIM_STYLE = { stroke: '#22c55e' }
const NAO_STYLE = { stroke: '#94a3b8' }
const SIM_LABEL_STYLE = { fill: '#15803d', fontSize: 11, fontWeight: 700 }
const NAO_LABEL_STYLE = { fill: '#64748b', fontSize: 11, fontWeight: 700 }

function buildNodes(apiNodes: FluxoNode[]): Node[] {
  const auto = autoLayout(apiNodes)
  return apiNodes.map((n) => {
    const hasPos = n.layout_x != null && n.layout_y != null
    const position = hasPos
      ? { x: n.layout_x as number, y: n.layout_y as number }
      : auto[n.job_name] ?? { x: 0, y: 0 }
    if (n.job_type === 'decisao') {
      const cond = toNodeCondition(n.condition)
      const data: DecisaoNodeData = { name: n.job_name, condition: cond, label: conditionLabel(cond) }
      return { id: n.job_name, type: 'decisao' as const, position, data }
    }
    const data: EtapaNodeData = {
      name: n.job_name,
      type: toEtapaType(n.job_type),
      command: n.job_command ?? null,   // CRU (nullable) — fallback só na exibição
      order: n.execution_order,
    }
    return { id: n.job_name, type: 'etapa' as const, position, data }
  })
}

// Aresta de ramo (sim/não) a partir de uma decisão.
function branchEdge(decisao: string, ramo: 'sim' | 'nao', alvo: string): Edge {
  return {
    id: `ramo:${decisao}:${ramo}:${alvo}`,
    source: decisao,
    sourceHandle: ramo,
    target: alvo,
    type: 'smoothstep',
    markerEnd: EDGE_ARROW,
    data: { branch: true, ramo },
    style: ramo === 'sim' ? SIM_STYLE : NAO_STYLE,
    label: ramo === 'sim' ? 'sim' : 'não',
    labelStyle: ramo === 'sim' ? SIM_LABEL_STYLE : NAO_LABEL_STYLE,
  }
}

function buildEdges(apiNodes: FluxoNode[]): Edge[] {
  const edges: Edge[] = []
  const isDecisao = new Set(apiNodes.filter(n => n.job_type === 'decisao').map(n => n.job_name))

  // Arestas NORMAIS (dep): dep → job, a partir de depends_on_jobs.
  for (const n of apiNodes) {
    for (const dep of n.depends_on_jobs || []) {
      if (isDecisao.has(dep)) continue   // origem decisão = ramo, não dep
      edges.push({
        id: `dep:${dep}->${n.job_name}`,
        source: dep,
        target: n.job_name,
        type: 'smoothstep',
        markerEnd: EDGE_ARROW,
      })
    }
  }

  // Arestas de RAMO de decisão (editáveis na Etapa 2): D → membros.
  for (const d of apiNodes) {
    if (d.job_type !== 'decisao' || !d.condition) continue
    for (const m of d.condition.ramo_verdadeiro || []) edges.push(branchEdge(d.job_name, 'sim', m))
    for (const m of d.condition.ramo_falso || []) edges.push(branchEdge(d.job_name, 'nao', m))
  }
  return edges
}

const isBranch = (e: Edge) => !!(e.data as { branch?: boolean } | undefined)?.branch
const edgeRamo = (e: Edge) => (e.data as { ramo?: 'sim' | 'nao' } | undefined)?.ramo

const NAME_RE = /^[A-Za-z0-9_.\- ]+$/

// Próximo nome livre seguindo um prefixo (NOVA_ETAPA_1, DECISAO_2, …).
function nextName(prefix: string, taken: Set<string>): string {
  let i = 1
  while (taken.has(`${prefix}_${i}`)) i++
  return `${prefix}_${i}`
}

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
      </div>
    </div>
  )
}

// ── Paleta arrastar-para-criar (lateral esquerda, topo) ─────────────────────
const DND_MIME = 'application/orquestra-etapa'

function Paleta() {
  const onDragStart = (e: React.DragEvent, tipo: string) => {
    e.dataTransfer.setData(DND_MIME, tipo)
    e.dataTransfer.effectAllowed = 'move'
  }
  return (
    <div className="w-[164px] rounded-lg border border-edge bg-panel/95 p-2 shadow-md backdrop-blur">
      <p className="px-0.5 pb-1.5 text-[10px] font-semibold uppercase tracking-wide text-dim">
        Adicionar etapa
      </p>
      <p className="px-0.5 pb-2 text-[10px] leading-tight text-dim/70">
        Arraste para o canvas.
      </p>
      <div className="flex flex-col gap-1.5">
        {CREATABLE_TYPES.map((t) => {
          const meta = TYPE_META[t]
          const Icon = meta.icon
          return (
            <div
              key={t}
              draggable
              onDragStart={(e) => onDragStart(e, t)}
              className="flex cursor-grab items-center gap-2 rounded-md border border-edge bg-canvas px-2 py-1.5 text-xs text-ink transition-colors hover:bg-edge/40 active:cursor-grabbing"
              title={`Arrastar para criar uma etapa ${meta.label}`}
            >
              <span className={`flex h-6 w-6 shrink-0 items-center justify-center rounded ${meta.chip}`}>
                <Icon size={13} strokeWidth={2.2} />
              </span>
              <span className="truncate font-medium">{meta.label}</span>
            </div>
          )
        })}
        <div
          draggable
          onDragStart={(e) => onDragStart(e, 'decisao')}
          className="flex cursor-grab items-center gap-2 rounded-md border border-indigo-200 bg-indigo-50 px-2 py-1.5 text-xs text-indigo-800 transition-colors hover:bg-indigo-100 active:cursor-grabbing dark:border-indigo-800 dark:bg-indigo-900/30 dark:text-indigo-200 dark:hover:bg-indigo-900/50"
          title="Arrastar para criar uma decisão"
        >
          <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded bg-indigo-500 text-white">
            <GitBranch size={13} strokeWidth={2.2} />
          </span>
          <span className="truncate font-medium">Decisão</span>
        </div>
      </div>
    </div>
  )
}

interface Props {
  pipeline: string
}

// Wrapper com o provider (necessário p/ useReactFlow/screenToFlowPosition).
export function FluxoEditor({ pipeline }: Props) {
  return (
    <ReactFlowProvider>
      <FluxoEditorInner pipeline={pipeline} />
    </ReactFlowProvider>
  )
}

function FluxoEditorInner({ pipeline }: Props) {
  const qc = useQueryClient()
  const colorMode = useColorMode()
  const rf = useReactFlow()
  const wrapperRef = useRef<HTMLDivElement>(null)
  const [nodes, setNodes] = useNodesState<Node>([])
  const [edges, setEdges, onEdgesChangeRF] = useEdgesState<Edge>([])
  const [dirty, setDirty] = useState(false)
  const [saving, setSaving] = useState(false)
  const [showPublish, setShowPublish] = useState(false)
  const [publishing, setPublishing] = useState(false)

  // Conjunto acumulado de job_names existentes removidos no canvas.
  const deletedRef = useRef<Set<string>>(new Set())
  // job_names que vieram do GET (existentes — nome não-editável; alimentam `deleted`).
  const existingRef = useRef<Set<string>>(new Set())
  // Guarda os nós da API para o re-layout.
  const apiNodesRef = useRef<FluxoNode[]>([])

  // Conexões MSSQL p/ o seletor do editor de condição (igual ao PipelineFormModal).
  const { data: mssqlData } = useQuery<{ connections: { conn_id: string; host: string }[] }>({
    queryKey: ['mssql-connections'],
    queryFn: () => apiFetch('/airflow/connections/mssql'),
    staleTime: 300_000,
  })
  const mssqlConns = mssqlData?.connections ?? []

  const decisaoSet = useMemo(
    () => new Set(nodes.filter(n => n.type === 'decisao').map(n => n.id)),
    [nodes],
  )

  // ── Drawer de condição / modal de nova etapa ──────────────────────────────
  // `editId` != null → o modal edita um nó NOVO já no canvas (renomeia/atualiza).
  const [condNodeId, setCondNodeId] = useState<string | null>(null)
  const [novaEtapa, setNovaEtapa] = useState<{ editId?: string; tipo: EtapaType; name: string; command: string; x: number; y: number } | null>(null)
  const [delNodeId, setDelNodeId] = useState<string | null>(null)

  const { data, isLoading, isError, error } = useQuery<FluxoResp>({
    queryKey: ['fluxo', pipeline],
    queryFn: () => apiFetch(`/pipelines/${encodeURIComponent(pipeline)}/fluxo`),
    enabled: !!pipeline,
  })

  useEffect(() => {
    if (!data) return
    apiNodesRef.current = data.nodes
    existingRef.current = new Set(data.nodes.map(n => n.job_name))
    deletedRef.current = new Set()
    setNodes(buildNodes(data.nodes))
    setEdges(buildEdges(data.nodes))
    setDirty(false)
  }, [data, setNodes, setEdges])

  // Todos os nomes em uso (no canvas) — para gerar nomes default únicos.
  const nameSet = useCallback(() => new Set(nodes.map(n => n.id)), [nodes])
  const maxOrder = useCallback(() => {
    let m = 0
    for (const n of nodes) {
      const o = (n.data as { order?: number }).order
      if (typeof o === 'number' && o > m) m = o
    }
    return m
  }, [nodes])

  // Mover/selecionar nó → marca dirty quando muda posição.
  const onNodesChange = useCallback(
    (changes: NodeChange<Node>[]) => {
      setNodes(nds => applyNodeChanges(changes, nds))
      if (changes.some(c => c.type === 'position' && c.dragging === false)) setDirty(true)
    },
    [setNodes],
  )

  // Conectar — aresta NORMAL (dep) se a origem é etapa; aresta de RAMO se a
  // origem é decisão (handle sim/não). Exclusividade do ramo por decisão.
  const onConnect = useCallback(
    (conn: Connection) => {
      if (!conn.source || !conn.target) return

      // A partir de uma decisão → cria/refaz a aresta de ramo.
      if (decisaoSet.has(conn.source)) {
        const ramo = (conn.sourceHandle === 'nao' ? 'nao' : 'sim') as 'sim' | 'nao'
        if (conn.target === conn.source) {
          toast.error('Uma decisão não pode ramificar para si mesma.')
          return
        }
        setEdges(eds => {
          // Remove qualquer aresta de ramo DESTA decisão para ESTE alvo (exclusividade).
          const kept = eds.filter(e =>
            !(isBranch(e) && e.source === conn.source && e.target === conn.target),
          )
          return [...kept, branchEdge(conn.source!, ramo, conn.target!)]
        })
        setDirty(true)
        return
      }

      // Aresta NORMAL (dep) — evita duplicadas.
      const exists = edges.some(e => !isBranch(e) && e.source === conn.source && e.target === conn.target)
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

  // Deletar arestas — todas deletáveis agora (inclusive ramos).
  const onEdgesChange = useCallback(
    (changes: EdgeChange<Edge>[]) => {
      onEdgesChangeRF(changes)
      if (changes.some(c => c.type === 'remove')) setDirty(true)
    },
    [onEdgesChangeRF],
  )

  // ── Drag & drop da paleta: cria nó local na posição do drop ───────────────
  const onDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
  }, [])

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      const tipo = e.dataTransfer.getData(DND_MIME)
      if (!tipo) return
      const position = rf.screenToFlowPosition({ x: e.clientX, y: e.clientY })
      const x = Math.round(position.x)
      const y = Math.round(position.y)
      if (tipo === 'decisao') {
        // Decisão: cria já o nó (defaults) e abre o drawer para editar nome/condição.
        const name = nextName('DECISAO', nameSet())
        const cond = defaultCondition()
        const node: Node = {
          id: name,
          type: 'decisao',
          position: { x, y },
          data: { name, condition: cond, label: conditionLabel(cond), isNew: true } as DecisaoNodeData,
        }
        setNodes(nds => [...nds, node])
        setDirty(true)
        setCondNodeId(name)
        return
      }
      // Etapa: abre o modal "Nova etapa" pedindo nome + comando.
      const t = toEtapaType(tipo)
      setNovaEtapa({ tipo: t, name: nextName('NOVA_ETAPA', nameSet()), command: '', x, y })
    },
    [rf, nameSet, setNodes],
  )

  // Confirma a criação/edição de uma etapa nova (a partir do modal).
  function confirmarNovaEtapa() {
    if (!novaEtapa) return
    const name = novaEtapa.name.trim()
    if (!name) { toast.error('Informe um nome para a etapa.'); return }
    if (!NAME_RE.test(name)) { toast.error('Nome inválido — use apenas letras, números, espaço, _ . -'); return }
    const editId = novaEtapa.editId
    const command = novaEtapa.command.trim() || null

    // Edição de um nó NOVO já no canvas: renomeia (se mudou) + atualiza comando.
    if (editId) {
      if (name !== editId) {
        if (!renomearNovo(editId, name)) return
      }
      setNodes(nds => nds.map(n => n.id === name ? { ...n, data: { ...n.data, command } } : n))
      setDirty(true)
      setNovaEtapa(null)
      return
    }

    // Criação de etapa nova.
    if (nameSet().has(name)) { toast.error('Já existe um nó com esse nome.'); return }
    const data: EtapaNodeData = {
      name,
      type: novaEtapa.tipo,
      command,
      order: maxOrder() + 1,
      isNew: true,
    }
    const node: Node = { id: name, type: 'etapa', position: { x: novaEtapa.x, y: novaEtapa.y }, data }
    setNodes(nds => [...nds, node])
    setDirty(true)
    setNovaEtapa(null)
  }

  // Renomeia um nó NOVO (ainda não salvo): atualiza id, arestas e ramos.
  function renomearNovo(oldName: string, novo: string): boolean {
    const name = novo.trim()
    if (name === oldName) return true
    if (!name) { toast.error('Informe um nome.'); return false }
    if (!NAME_RE.test(name)) { toast.error('Nome inválido — use apenas letras, números, espaço, _ . -'); return false }
    if (nameSet().has(name)) { toast.error('Já existe um nó com esse nome.'); return false }
    // Troca id + nome (data) e remapeia arestas.
    setNodes(nds => nds.map(n => n.id === oldName
      ? { ...n, id: name, data: { ...n.data, name } }
      : n))
    setEdges(eds => eds.map(e => {
      let ne = e
      if (e.source === oldName) ne = { ...ne, source: name }
      if (e.target === oldName) ne = { ...ne, target: name }
      if (ne !== e) ne = { ...ne, id: ne.id.replace(oldName, name) }
      return ne
    }))
    setDirty(true)
    return true
  }

  // Atualiza a condição de uma decisão (merge) e o rótulo do nó.
  function patchCondition(nodeId: string, patch: Partial<NodeCondition>) {
    setNodes(nds => nds.map(n => {
      if (n.id !== nodeId || n.type !== 'decisao') return n
      const cur = (n.data as DecisaoNodeData).condition ?? defaultCondition()
      const next = { ...cur, ...patch }
      return { ...n, data: { ...n.data, condition: next, label: conditionLabel(next) } }
    }))
    setDirty(true)
  }

  // ── Excluir nó (confirmação) ──────────────────────────────────────────────
  function excluirNo(id: string) {
    if (existingRef.current.has(id)) deletedRef.current.add(id)
    setEdges(eds => eds.filter(e => e.source !== id && e.target !== id))
    setNodes(nds => nds.filter(n => n.id !== id))
    setDirty(true)
    setDelNodeId(null)
    if (condNodeId === id) setCondNodeId(null)
  }

  // Intercepta o delete nativo (tecla Delete/Backspace) para confirmar antes de
  // remover um nó. Deleção de arestas (toDel.nodes vazio) segue direto.
  const handleBeforeDelete = useCallback(
    async ({ nodes: toDel }: { nodes: Node[]; edges: Edge[] }) => {
      if (toDel.length > 0) {
        setDelNodeId(toDel[0].id)
        return false   // cancela o delete nativo; nossa confirmação cuida
      }
      return true
    },
    [],
  )

  // Re-roda o auto-layout.
  const reorganizar = useCallback(() => {
    const pos = autoLayout(apiNodesRef.current)
    setNodes(nds => nds.map(n => (pos[n.id] ? { ...n, position: pos[n.id] } : n)))
    setDirty(true)
  }, [setNodes])

  // ── Salvar: materializa o grafo (todos os nós) ────────────────────────────
  async function salvar() {
    setSaving(true)
    try {
      const decisoes = new Set(nodes.filter(n => n.type === 'decisao').map(n => n.id))

      // depends_on_jobs[N] = origens das arestas NORMAIS que chegam em N
      // (exclui arestas de ramo e arestas cuja origem é decisão).
      const depsByTarget = new Map<string, Set<string>>()
      // ramos por decisão (sim/não) a partir das arestas de ramo.
      const ramosByDecisao = new Map<string, { sim: string[]; nao: string[] }>()
      for (const e of edges) {
        if (isBranch(e)) {
          const ramo = edgeRamo(e) ?? 'sim'
          if (!ramosByDecisao.has(e.source)) ramosByDecisao.set(e.source, { sim: [], nao: [] })
          ramosByDecisao.get(e.source)![ramo].push(e.target)
          continue
        }
        if (decisoes.has(e.source)) continue
        if (!depsByTarget.has(e.target)) depsByTarget.set(e.target, new Set())
        depsByTarget.get(e.target)!.add(e.source)
      }

      const payloadNodes = nodes.map(n => {
        const d = n.data as Record<string, unknown>
        const isDecisao = n.type === 'decisao'
        let condition: Record<string, unknown> | null = null
        if (isDecisao) {
          const cur = (d.condition as NodeCondition | undefined) ?? defaultCondition()
          const ramos = ramosByDecisao.get(n.id) ?? { sim: [], nao: [] }
          condition = {
            tipo: cur.tipo,
            operador: cur.operador,
            valor: (cur.valor ?? '').toString().trim(),
            tabela: (cur.tabela || '').trim() || undefined,
            database: (cur.database || '').trim() || undefined,
            sql: (cur.sql || '').trim() || undefined,
            mssql_conn_id: (cur.mssql_conn_id || '').trim() || undefined,
            ramo_verdadeiro: ramos.sim,
            ramo_falso: ramos.nao,
          }
        }
        return {
          job_name: n.id,
          job_type: isDecisao ? 'decisao' : ((d.type as string) || 'datastage'),
          job_command: isDecisao ? null : ((d.command as string | null) ?? null),
          execution_order: (d.order as number) ?? 1,
          depends_on_jobs: Array.from(depsByTarget.get(n.id) ?? []),
          condition,
          layout_x: Math.round(n.position.x),
          layout_y: Math.round(n.position.y),
        }
      })

      const payload = {
        nodes: payloadNodes,
        deleted: Array.from(deletedRef.current),
      }
      await apiFetch(`/pipelines/${encodeURIComponent(pipeline)}/fluxo`, {
        method: 'POST',
        body: JSON.stringify(payload),
      })
      toast.success('Fluxo salvo com sucesso.')
      setDirty(false)
      deletedRef.current = new Set()
      qc.invalidateQueries({ queryKey: ['fluxo', pipeline] })
      setShowPublish(true)
    } catch (e: any) {
      const status: number | undefined = e?.status
      const msg = e?.message ?? ''
      if (status === 400 || /ciclo|cycle/i.test(msg)) {
        toast.error('Ciclo detectado no fluxo — ajuste as dependências.')
      } else if (status === 422) {
        // Erros de validação do backend: detail.errors[] — não trava o canvas,
        // mantém `dirty` para o usuário corrigir.
        const errs = extractValidationErrors(e)
        toast.error(errs.length ? `Validação: ${errs.slice(0, 3).join(' · ')}` : 'Fluxo inválido — verifique as decisões.')
      } else {
        toast.error(msg || 'Erro ao salvar o fluxo.')
      }
    } finally {
      setSaving(false)
    }
  }

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

  // Abrir drawer/modal ao dar duplo-clique num nó.
  const onNodeDoubleClick = useCallback((_: React.MouseEvent, node: Node) => {
    if (node.type === 'decisao') { setCondNodeId(node.id); return }
    // Etapa NOVA (ainda não salva): permite editar nome/comando.
    const d = node.data as EtapaNodeData
    if (d.isNew) {
      setNovaEtapa({ editId: node.id, tipo: d.type, name: node.id, command: d.command ?? '', x: Math.round(node.position.x), y: Math.round(node.position.y) })
    }
  }, [])

  // Ramos atuais da decisão aberta no drawer (derivados das arestas de ramo).
  const condRamos = useMemo(() => {
    if (!condNodeId) return { sim: [] as string[], nao: [] as string[] }
    const sim: string[] = []; const nao: string[] = []
    for (const e of edges) {
      if (!isBranch(e) || e.source !== condNodeId) continue
      ;(edgeRamo(e) === 'nao' ? nao : sim).push(e.target)
    }
    return { sim, nao }
  }, [edges, condNodeId])

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

  const selectedId = nodes.find(n => n.selected)?.id ?? null
  const condNode = condNodeId ? nodes.find(n => n.id === condNodeId) : null
  const condData = condNode ? (condNode.data as DecisaoNodeData) : null

  return (
    <div className="relative h-full w-full overflow-hidden rounded-xl border border-edge bg-canvas" ref={wrapperRef}>
      {nodes.length === 0 && (
        <div className="pointer-events-none absolute inset-0 z-10 flex flex-col items-center justify-center gap-1 text-dim">
          <span className="text-3xl">⬡</span>
          <p className="text-sm font-medium">Nenhuma etapa neste pipeline</p>
          <p className="text-xs">Arraste um tipo da paleta (à esquerda) para criar a primeira etapa.</p>
        </div>
      )}
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        onBeforeDelete={handleBeforeDelete}
        onNodeDoubleClick={onNodeDoubleClick}
        onDrop={onDrop}
        onDragOver={onDragOver}
        colorMode={colorMode}
        fitView
        fitViewOptions={{ padding: 0.25 }}
        proOptions={{ hideAttribution: true }}
        defaultEdgeOptions={{ type: 'smoothstep' }}
        deleteKeyCode={['Delete', 'Backspace']}
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

        {/* Paleta arrastar-para-criar (esquerda) */}
        <Panel position="top-left">
          <Paleta />
        </Panel>

        {/* Barra de ações (topo direita) */}
        <Panel position="top-right">
          <div className="flex items-center gap-2 rounded-lg border border-edge bg-panel/95 px-2.5 py-2 shadow-md backdrop-blur">
            {dirty && (
              <span className="flex items-center gap-1 rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-[11px] font-semibold text-amber-700 dark:border-amber-800 dark:bg-amber-900/30 dark:text-amber-300">
                <span className="h-1.5 w-1.5 rounded-full bg-amber-500" />
                alterações não salvas
              </span>
            )}
            {selectedId && (
              <Button
                variant="danger"
                size="sm"
                onClick={() => setDelNodeId(selectedId)}
                title="Excluir o nó selecionado"
              >
                <Trash2 size={13} /> Excluir
              </Button>
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

      {/* Modal: nova etapa (nome + comando + tipo) */}
      <Modal
        open={!!novaEtapa}
        onClose={() => setNovaEtapa(null)}
        title={novaEtapa?.editId ? 'Editar etapa' : 'Nova etapa'}
        size="md"
      >
        {novaEtapa && (
          <div className="flex flex-col gap-3">
            <div className="flex items-center gap-2">
              <span className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-md ${TYPE_META[novaEtapa.tipo].chip}`}>
                {(() => { const Icon = TYPE_META[novaEtapa.tipo].icon; return <Icon size={15} strokeWidth={2.2} /> })()}
              </span>
              <span className="text-sm font-medium text-ink">{TYPE_META[novaEtapa.tipo].label}</span>
            </div>
            <Input
              label="Nome da etapa *"
              value={novaEtapa.name}
              onChange={e => setNovaEtapa(s => s ? { ...s, name: e.target.value } : s)}
              placeholder="ex: CARGA_CLIENTES"
              className="font-mono"
            />
            <p className="-mt-2 text-[10px] text-dim">Letras, números, espaço, _ . - </p>
            <Textarea
              label="Comando / path (opcional)"
              value={novaEtapa.command}
              rows={2}
              onChange={e => setNovaEtapa(s => s ? { ...s, command: e.target.value } : s)}
              placeholder="ex: caminho do job, script, proc…"
              className="font-mono text-xs"
            />
            <div className="flex justify-end gap-2 border-t border-edge pt-3">
              <Button variant="secondary" onClick={() => setNovaEtapa(null)}>Cancelar</Button>
              <Button onClick={confirmarNovaEtapa}>
                {novaEtapa.editId ? 'Aplicar' : 'Criar etapa'}
              </Button>
            </div>
          </div>
        )}
      </Modal>

      {/* Drawer/modal: editar condição da decisão */}
      <Modal
        open={!!condNode}
        onClose={() => setCondNodeId(null)}
        title="Condição da decisão"
        size="lg"
      >
        {condNode && condData && (
          <DecisaoForm
            nodeId={condNode.id}
            name={condData.name}
            isNew={!!condData.isNew}
            condition={condData.condition}
            ramos={condRamos}
            mssqlConns={mssqlConns}
            onRename={novo => {
              const ok = renomearNovo(condNode.id, novo)
              if (ok && novo.trim() && novo.trim() !== condNode.id) setCondNodeId(novo.trim())
              return ok
            }}
            onPatch={patch => patchCondition(condNode.id, patch)}
            onClose={() => setCondNodeId(null)}
          />
        )}
      </Modal>

      {/* Confirmação de exclusão de nó */}
      <Modal
        open={!!delNodeId}
        onClose={() => setDelNodeId(null)}
        title="Excluir nó"
        size="sm"
      >
        <div className="flex flex-col gap-4">
          <p className="text-sm text-dim">
            Remover{' '}
            <span className="font-mono font-medium text-ink">{delNodeId}</span>{' '}
            do fluxo? As dependências e ramos ligados a ele também serão desligados.
          </p>
          {delNodeId && existingRef.current.has(delNodeId) && (
            <p className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-300">
              Este nó já existe no pipeline — será excluído ao salvar o fluxo.
            </p>
          )}
          <div className="flex justify-end gap-2 border-t border-edge pt-3">
            <Button variant="secondary" onClick={() => setDelNodeId(null)}>Cancelar</Button>
            <Button variant="danger" onClick={() => delNodeId && excluirNo(delNodeId)}>
              <Trash2 size={14} /> Excluir
            </Button>
          </div>
        </div>
      </Modal>

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

// Extrai detail.errors[] de um erro de apiFetch (detail anexado em api.ts).
function extractValidationErrors(e: any): string[] {
  const out: string[] = []
  const d = e?.detail
  if (d && Array.isArray(d.errors)) {
    d.errors.forEach((x: unknown) => { if (typeof x === 'string') out.push(x) })
  } else if (typeof d === 'string') {
    out.push(d)
  }
  return out
}

// ── Editor de condição (espelha o bloco de decisão do PipelineFormModal) ─────
interface DecisaoFormProps {
  nodeId: string
  name: string
  isNew: boolean
  condition: NodeCondition
  ramos: { sim: string[]; nao: string[] }
  mssqlConns: { conn_id: string; host: string }[]
  onRename: (novo: string) => boolean
  onPatch: (patch: Partial<NodeCondition>) => void
  onClose: () => void
}

function DecisaoForm({ nodeId, name, isNew, condition, ramos, mssqlConns, onRename, onPatch, onClose }: DecisaoFormProps) {
  const [nameDraft, setNameDraft] = useState(name)
  useEffect(() => { setNameDraft(name) }, [nodeId, name])
  const c = condition

  function commitName() {
    if (!isNew) return
    if (nameDraft.trim() === name) return
    if (!onRename(nameDraft)) setNameDraft(name)
  }

  return (
    <div className="flex flex-col gap-4">
      {/* Nome (editável só para decisão nova) */}
      <Input
        label={isNew ? 'Nome da decisão *' : 'Nome da decisão'}
        value={nameDraft}
        disabled={!isNew}
        onChange={e => setNameDraft(e.target.value)}
        onBlur={commitName}
        onKeyDown={e => { if (e.key === 'Enter') commitName() }}
        placeholder="ex: DECISAO_VOLUME"
        className={`font-mono ${!isNew ? 'opacity-60' : ''}`}
      />
      {!isNew && <p className="-mt-2 text-[10px] text-dim">O nome de um nó já salvo não é editável aqui.</p>}

      <div className="flex items-center gap-1.5">
        <GitBranch size={13} className="text-indigo-600 dark:text-indigo-300" />
        <span className="text-xs font-semibold text-ink">Expressão da condição</span>
        <span className="text-[11px] text-dim">— desvia o fluxo conforme o resultado</span>
      </div>

      <div className="grid grid-cols-[1fr_90px_1fr] gap-2">
        <Select label="Tipo" value={c.tipo} onChange={e => onPatch({ tipo: e.target.value as 'contagem' | 'query' })}>
          <option value="contagem">Contagem de registros</option>
          <option value="query">Valor de uma query</option>
        </Select>
        <Select label="Operador" value={c.operador} onChange={e => onPatch({ operador: e.target.value })} className="text-center">
          {COND_OPERADORES.map(op => <option key={op} value={op}>{op}</option>)}
        </Select>
        <Input
          label="Valor *"
          value={c.valor}
          onChange={e => onPatch({ valor: e.target.value })}
          placeholder={c.tipo === 'query' ? 'ex: 1' : 'ex: 10000'}
          className="font-mono"
        />
      </div>

      {c.tipo === 'contagem' ? (
        <div className="grid grid-cols-2 gap-2">
          <Input
            label="Tabela * (db.schema.tabela)"
            value={c.tabela ?? ''}
            onChange={e => onPatch({ tabela: e.target.value })}
            placeholder="db.schema.tabela"
            className="font-mono"
          />
          <Input
            label="Banco (opcional)"
            value={c.database ?? ''}
            onChange={e => onPatch({ database: e.target.value })}
            placeholder="ex: BI_DW"
            className="font-mono"
          />
        </div>
      ) : (
        <Textarea
          label="SQL (somente SELECT) *"
          value={c.sql ?? ''}
          rows={3}
          onChange={e => onPatch({ sql: e.target.value })}
          placeholder="ex: SELECT MAX(flag) FROM dbo.Controle WHERE ..."
          className="font-mono text-xs"
        />
      )}

      <Select
        label="Conexão MSSQL (opcional · padrão do projeto)"
        value={c.mssql_conn_id ?? ''}
        onChange={e => onPatch({ mssql_conn_id: e.target.value })}
      >
        <option value="">Conexão padrão</option>
        {mssqlConns.map(cn => (
          <option key={cn.conn_id} value={cn.conn_id}>{cn.conn_id}{cn.host ? ` (${cn.host})` : ''}</option>
        ))}
      </Select>

      {/* Ramos atuais (derivados das arestas) — read-only */}
      <div className="rounded-lg border border-edge bg-canvas p-3">
        <p className="mb-2 text-[11px] text-dim">
          Os ramos são definidos arrastando as arestas <b>sim</b> (direita) e <b>não</b> (baixo)
          da decisão até as etapas, direto no canvas.
        </p>
        <div className="grid grid-cols-2 gap-3">
          <div className="flex flex-col gap-1">
            <span className="text-[10px] font-medium text-green-700 dark:text-green-400">Se verdadeiro → rodar</span>
            <div className="flex flex-wrap gap-1">
              {ramos.sim.length === 0 && <span className="text-[10px] text-dim/70">nenhum</span>}
              {ramos.sim.map(m => (
                <span key={m} className="rounded-full border border-green-300 bg-green-100 px-2 py-0.5 text-[10px] font-medium text-green-700 dark:border-green-800 dark:bg-green-900/40 dark:text-green-300">
                  {m}
                </span>
              ))}
            </div>
          </div>
          <div className="flex flex-col gap-1">
            <span className="text-[10px] font-medium text-slate-600 dark:text-slate-300">Se falso → rodar</span>
            <div className="flex flex-wrap gap-1">
              {ramos.nao.length === 0 && <span className="text-[10px] text-dim/70">nenhum</span>}
              {ramos.nao.map(m => (
                <span key={m} className="rounded-full border border-slate-300 bg-slate-100 px-2 py-0.5 text-[10px] font-medium text-slate-600 dark:border-slate-700 dark:bg-slate-700 dark:text-slate-300">
                  {m}
                </span>
              ))}
            </div>
          </div>
        </div>
        {ramos.sim.length === 0 && ramos.nao.length === 0 && (
          <p className="mt-2 rounded border border-amber-200 bg-amber-50 px-2 py-1 text-[10px] text-amber-800 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-300">
            Ligue ao menos um job em algum ramo (arrastando as arestas) antes de salvar.
          </p>
        )}
      </div>

      <div className="flex justify-end gap-2 border-t border-edge pt-3">
        <Button onClick={onClose}>Concluir</Button>
      </div>
    </div>
  )
}
