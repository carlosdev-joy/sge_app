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
import { PlaceholderPicker } from '../ui/PlaceholderPicker'
import { Modal } from '../ui/Modal'
import { toast } from '../ui/Toast'
import {
  Save, RefreshCw, AlertCircle, GitBranch, Trash2, BellRing,
  PanelRightClose, ChevronLeft, ChevronRight, MousePointerClick, Search, X,
} from 'lucide-react'
import { EtapaNode, type EtapaNodeData } from './EtapaNode'
import { DecisaoNode, type DecisaoNodeData, type NodeCondition } from './DecisaoNode'
import { NotificacaoNode, type NotificacaoNodeData } from './NotificacaoNode'
import { TYPE_META, TYPE_ORDER, CREATABLE_TYPES, type EtapaType } from './types'
import { COND_OPERADORES, defaultCondition, toNodeCondition, conditionLabel } from './condition'
import { useColorMode } from './useColorMode'
import {
  JobTypeFields, type JobTypeFieldsValue, type JobFieldsType, type JobParam,
} from './JobTypeFields'

const nodeTypes = { etapa: EtapaNode, decisao: DecisaoNode, notificacao: NotificacaoNode }

// ── Tipos do payload da API (/fluxo) ────────────────────────────────────────
interface Condition {
  ramo_verdadeiro?: string[]
  ramo_falso?: string[]
  [k: string]: unknown
}
// Config do nó de notificação (round-trip com /fluxo no campo `notify`).
interface NotifyConfig {
  grupo_id: number | null
  template_id: number | null
  mensagem: string
}
interface FluxoNode {
  job_name: string
  job_type: string
  job_command: string | null
  execution_order: number
  depends_on_jobs: string[]
  condition: Condition | null
  notify: NotifyConfig | null
  layout_x: number | null
  layout_y: number | null
  // Campos por tipo (round-trip). O backend usa presença de chave — sempre reenviados.
  ssh_conn_id?: string | null
  verbose_log?: boolean
  mssql_conn_id?: string | null
  mssql_database?: string | null
  params?: { param_name: string; param_type: string; param_value: string | null; param_order?: number }[]
}
interface FluxoResp { nodes: FluxoNode[] }

// Catálogo de mensagens (Teams) — alimentam os Selects do nó de notificação.
interface MsgGrupo { id: number; nome: string; descricao: string | null; has_webhook?: boolean; ativo?: boolean }
interface MsgTemplate { id: number; grupo_id: number | null; nome: string; titulo: string | null }

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

// Layout sobre o grafo VIVO (nós + arestas atuais), não só os salvos: assim o
// "Reorganizar" reposiciona TAMBÉM os nós recém-adicionados (ex.: uma notificação
// que ainda não foi salva). Coluna = execution_order salvo, quando houver; para
// um nó novo, deriva de (maior coluna dos predecessores no grafo) + 1.
function liveLayout(
  nodes: Node[],
  edges: Edge[],
  savedOrder: Map<string, number>,
): Record<string, { x: number; y: number }> {
  const preds = new Map<string, string[]>()
  for (const n of nodes) preds.set(n.id, [])
  for (const e of edges) {
    if (preds.has(e.target) && preds.has(e.source)) preds.get(e.target)!.push(e.source)
  }
  const col = new Map<string, number>()
  const visiting = new Set<string>()
  const resolve = (id: string): number => {
    const cached = col.get(id)
    if (cached != null) return cached
    const saved = savedOrder.get(id)
    if (saved != null) { col.set(id, saved); return saved }
    if (visiting.has(id)) return 1   // guarda contra ciclo
    visiting.add(id)
    let c = 1
    for (const p of preds.get(id) ?? []) c = Math.max(c, resolve(p) + 1)
    visiting.delete(id)
    col.set(id, c)
    return c
  }
  for (const n of nodes) resolve(n.id)
  const byCol = new Map<number, string[]>()
  for (const n of nodes) {
    const c = col.get(n.id) ?? 1
    if (!byCol.has(c)) byCol.set(c, [])
    byCol.get(c)!.push(n.id)
  }
  const pos: Record<string, { x: number; y: number }> = {}
  Array.from(byCol.keys()).sort((a, b) => a - b).forEach((c, ci) => {
    byCol.get(c)!.forEach((id, ri) => {
      pos[id] = { x: ci * COL_W, y: ri * ROW_H }
    })
  })
  return pos
}

// Mapeia o job_type da API para um EtapaType conhecido (fallback p/ datastage).
function toEtapaType(t: string): EtapaType {
  return (TYPE_ORDER as string[]).includes(t) ? (t as EtapaType) : 'datastage'
}

// ── Notificação (Teams) ─────────────────────────────────────────────────────
// Config default de um nó de notificação recém-criado (grupo a escolher).
function defaultNotify(): NotifyConfig {
  return { grupo_id: null, template_id: null, mensagem: '' }
}

// Lê a config de notificação do payload da API (tolerante a null/parcial).
function toNotifyConfig(raw: NotifyConfig | null | undefined): NotifyConfig {
  if (!raw || typeof raw !== 'object') return defaultNotify()
  const gid = raw.grupo_id
  const tid = raw.template_id
  return {
    grupo_id: typeof gid === 'number' ? gid : (gid != null && `${gid}`.trim() ? Number(gid) : null),
    template_id: typeof tid === 'number' ? tid : (tid != null && `${tid}`.trim() ? Number(tid) : null),
    mensagem: typeof raw.mensagem === 'string' ? raw.mensagem : '',
  }
}

// Resumo curto p/ o card. Usa o nome do grupo quando disponível (gruposById),
// senão "Teams: #<id>"; sem grupo escolhido mostra "notificação".
function notifyLabel(cfg: NotifyConfig, gruposById?: Map<number, string>): string {
  if (cfg.grupo_id == null) return 'notificação'
  const nome = gruposById?.get(cfg.grupo_id)
  return `Teams: ${nome ?? `#${cfg.grupo_id}`}`
}

// ── Construção de nós/arestas a partir do payload ───────────────────────────
const EDGE_ARROW = { type: MarkerType.ArrowClosed, width: 16, height: 16 }
const SIM_STYLE = { stroke: '#22c55e' }
const NAO_STYLE = { stroke: '#94a3b8' }
const SIM_LABEL_STYLE = { fill: '#15803d', fontSize: 11, fontWeight: 700 }
const NAO_LABEL_STYLE = { fill: '#64748b', fontSize: 11, fontWeight: 700 }
// Rótulo discreto das arestas NORMAIS de dependência ("Link_N"): texto minúsculo,
// neutro, sem fundo próprio — só pra dar o ar de designer (estilo IBM/DataStage).
const LINK_LABEL_STYLE = { fill: '#94a3b8', fontSize: 9, fontWeight: 500 }
const LINK_LABEL_BG = { fill: 'transparent' }

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
    if (n.job_type === 'notificacao') {
      const notify = toNotifyConfig(n.notify)
      const data: NotificacaoNodeData = { name: n.job_name, notify, label: notifyLabel(notify) }
      return { id: n.job_name, type: 'notificacao' as const, position, data }
    }
    const data: EtapaNodeData = {
      name: n.job_name,
      type: toEtapaType(n.job_type),
      command: n.job_command ?? null,   // CRU (nullable) — fallback só na exibição
      order: n.execution_order,
      // Campos por tipo (round-trip): preservados no data e reenviados no save.
      ssh_conn_id: n.ssh_conn_id ?? null,
      verbose_log: !!n.verbose_log,
      mssql_conn_id: n.mssql_conn_id ?? null,
      mssql_database: n.mssql_database ?? null,
      params: (n.params ?? []).map((p, i) => ({
        id: `p_${i}_${p.param_name}`,
        param_name: p.param_name,
        param_type: p.param_type,
        param_value: p.param_value ?? '',
      })),
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
  // Rótulo sutil "Link_N" (N por ordem de criação) — só visual, não afeta o save.
  let linkSeq = 0
  for (const n of apiNodes) {
    for (const dep of n.depends_on_jobs || []) {
      if (isDecisao.has(dep)) continue   // origem decisão = ramo, não dep
      linkSeq += 1
      edges.push({
        id: `dep:${dep}->${n.job_name}`,
        source: dep,
        target: n.job_name,
        type: 'smoothstep',
        markerEnd: EDGE_ARROW,
        label: `Link_${linkSeq}`,
        labelStyle: LINK_LABEL_STYLE,
        labelBgStyle: LINK_LABEL_BG,
        labelShowBg: false,
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
        <span className="flex items-center gap-1.5 text-[10px] text-dim">
          <span className="h-2 w-2 rounded-full bg-teal-500" />
          Notificação
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

// ── Paleta arrastar-para-criar (estilo IBM Cloud Pak / DataStage Designer) ────
const DND_MIME = 'application/orquestra-etapa'

type IconCmp = React.ComponentType<{ size?: number; strokeWidth?: number }>
interface PaletaNode { tipo: string; label: string; chip: string; Icon: IconCmp }
interface PaletaCategoria { titulo: string; nodes: PaletaNode[] }

// Categorias do palette — declarativas pra ficar fácil estender. "Execução"
// reúne os tipos criáveis (datastage/shell/python/storedproc…); "Fluxo" reúne
// os nós de controle (decisão e notificação).
const PALETA_CATEGORIAS: PaletaCategoria[] = [
  {
    titulo: 'Execução',
    nodes: CREATABLE_TYPES.map((t) => ({
      tipo: t,
      label: TYPE_META[t].label,
      chip: TYPE_META[t].chip,
      Icon: TYPE_META[t].icon,
    })),
  },
  {
    titulo: 'Fluxo',
    nodes: [
      { tipo: 'decisao', label: 'Decisão', chip: 'bg-indigo-500 text-white', Icon: GitBranch },
      { tipo: 'notificacao', label: 'Notificação', chip: 'bg-teal-500 text-white', Icon: BellRing },
    ],
  },
]

// Normaliza p/ busca acento-insensível (case + diacríticos simples).
function normalizeBusca(s: string): string {
  return s.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '')
}

// Um item arrastável da paleta. Aberto → linha (chip à esquerda + label à
// direita), estilo lista do designer. Colapsado → só o chip (faixa fininha).
function PaletaItem({
  tipo, label, chip, Icon, collapsed,
}: PaletaNode & { collapsed: boolean }) {
  const onDragStart = (e: React.DragEvent) => {
    e.dataTransfer.setData(DND_MIME, tipo)
    e.dataTransfer.effectAllowed = 'move'
  }
  if (collapsed) {
    return (
      <div
        draggable
        onDragStart={onDragStart}
        title={`Arrastar para criar — ${label}`}
        className="group flex cursor-grab items-center justify-center rounded-md border border-edge bg-canvas p-1 text-ink transition-colors hover:bg-edge/40 active:cursor-grabbing"
      >
        <span className={`flex h-7 w-7 shrink-0 items-center justify-center rounded ${chip}`}>
          <Icon size={16} strokeWidth={2.2} />
        </span>
      </div>
    )
  }
  return (
    <div
      draggable
      onDragStart={onDragStart}
      title={`Arrastar para criar — ${label}`}
      className="group flex cursor-grab items-center gap-2 rounded-md border border-edge bg-canvas px-2 py-1.5 text-ink transition-colors hover:border-blue-300 hover:bg-edge/40 active:cursor-grabbing dark:hover:border-blue-800"
    >
      <span className={`flex h-7 w-7 shrink-0 items-center justify-center rounded ${chip}`}>
        <Icon size={16} strokeWidth={2.2} />
      </span>
      <span className="min-w-0 flex-1 truncate text-[11px] font-medium leading-none text-ink">
        {label}
      </span>
    </div>
  )
}

function Paleta({
  open, onToggle,
}: { open: boolean; onToggle: () => void }) {
  const [busca, setBusca] = useState('')

  // Filtra os nós por label (case/acento-insensível). Categorias sem itens após
  // o filtro desaparecem. No modo colapsado a busca não se aplica (sem input).
  const categorias = useMemo(() => {
    const q = normalizeBusca(busca.trim())
    if (!open || !q) return PALETA_CATEGORIAS
    return PALETA_CATEGORIAS
      .map((c) => ({ ...c, nodes: c.nodes.filter((n) => normalizeBusca(n.label).includes(q)) }))
      .filter((c) => c.nodes.length > 0)
  }, [busca, open])

  return (
    <div
      className={[
        'flex max-h-[calc(100%-1rem)] flex-col overflow-hidden rounded-lg border border-edge bg-panel/95 shadow-md backdrop-blur',
        open ? 'w-[176px]' : 'w-[40px]',
      ].join(' ')}
    >
      {/* Cabeçalho com título + botão de colapsar/expandir */}
      <button
        type="button"
        onClick={onToggle}
        title={open ? 'Recolher paleta' : 'Expandir paleta'}
        className={[
          'flex shrink-0 items-center border-b border-edge text-[10px] font-semibold uppercase tracking-wide text-dim transition-colors hover:bg-edge/40 hover:text-ink',
          open ? 'justify-between px-2.5 py-2' : 'justify-center px-1 py-2',
        ].join(' ')}
      >
        {open ? (
          <>
            <span>Paleta</span>
            <ChevronLeft size={13} />
          </>
        ) : (
          <ChevronRight size={13} />
        )}
      </button>

      {/* Busca — só no estado aberto */}
      {open && (
        <div className="shrink-0 border-b border-edge p-2">
          <div className="relative">
            <Search
              size={13}
              className="pointer-events-none absolute left-2 top-1/2 -translate-y-1/2 text-dim"
            />
            <input
              value={busca}
              onChange={(e) => setBusca(e.target.value)}
              placeholder="Buscar nó…"
              className="w-full rounded-md border border-edge bg-canvas py-1 pl-7 pr-6 text-[11px] text-ink placeholder-dim focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
            {busca && (
              <button
                type="button"
                onClick={() => setBusca('')}
                title="Limpar busca"
                className="absolute right-1.5 top-1/2 -translate-y-1/2 rounded p-0.5 text-dim transition-colors hover:bg-edge/50 hover:text-ink"
              >
                <X size={12} />
              </button>
            )}
          </div>
        </div>
      )}

      {/* Itens por categoria */}
      <div className={['flex flex-col gap-2 overflow-y-auto', open ? 'p-2' : 'p-1'].join(' ')}>
        {open && categorias.length === 0 && (
          <p className="px-1 py-2 text-center text-[10px] text-dim">Nenhum nó encontrado.</p>
        )}
        {categorias.map((cat) => (
          <div key={cat.titulo} className="flex flex-col gap-1">
            {open && (
              <p className="px-0.5 text-[9px] font-semibold uppercase tracking-wide text-dim">
                {cat.titulo}
              </p>
            )}
            {cat.nodes.map((n) => (
              <PaletaItem key={n.tipo} {...n} collapsed={!open} />
            ))}
          </div>
        ))}
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
  // Paleta colapsável (estado local).
  const [paletaOpen, setPaletaOpen] = useState(true)

  // Conjunto acumulado de job_names existentes removidos no canvas.
  const deletedRef = useRef<Set<string>>(new Set())
  // job_names que vieram do GET (existentes — nome não-editável; alimentam `deleted`).
  const existingRef = useRef<Set<string>>(new Set())
  // Guarda os nós da API para o re-layout.
  const apiNodesRef = useRef<FluxoNode[]>([])

  // Conexões MSSQL p/ o editor de condição e p/ etapas storedproc (JobTypeFields).
  const { data: mssqlData } = useQuery<{ connections: { conn_id: string; host: string }[] }>({
    queryKey: ['mssql-connections'],
    queryFn: () => apiFetch('/airflow/connections/mssql'),
    staleTime: 300_000,
  })
  const mssqlConns = mssqlData?.connections ?? []

  // Conexões SSH p/ etapas shell (JobTypeFields).
  const { data: sshData } = useQuery<{ connections: { conn_id: string; host: string }[] }>({
    queryKey: ['ssh-connections'],
    queryFn: () => apiFetch('/airflow/connections/ssh'),
    staleTime: 300_000,
  })
  const sshConns = sshData?.connections ?? []

  // Bancos do mesmo servidor (seletor de banco-alvo de storedproc no JobTypeFields).
  const { data: dbData } = useQuery<{ server: string | null; databases: string[] }>({
    queryKey: ['job-databases'],
    queryFn: () => apiFetch('/jobs/databases'),
    staleTime: 300_000,
  })
  const dbServer = dbData?.server ?? null
  const dbDatabases = dbData?.databases ?? []

  // Grupos (canais Teams) p/ o nó de notificação — Select do painel e rótulo do card.
  // Degrada para [] se a tabela/endpoint não existir (try/except no backend).
  const { data: gruposData } = useQuery<{ data: MsgGrupo[] }>({
    queryKey: ['msg-grupos'],
    queryFn: () => apiFetch('/msg/grupos'),
    staleTime: 300_000,
  })
  const grupos = gruposData?.data ?? []
  const gruposById = useMemo(
    () => new Map(grupos.map(g => [g.id, g.nome] as const)),
    [grupos],
  )

  const decisaoSet = useMemo(
    () => new Set(nodes.filter(n => n.type === 'decisao').map(n => n.id)),
    [nodes],
  )

  // Jobs (etapas) do pipeline — alimentam o seletor "Job" da condição linhas_job.
  // Decisões (roteadores) e notificações (não geram linhas) ficam de fora.
  const jobNames = useMemo(
    () => nodes.filter(n => n.type !== 'decisao' && n.type !== 'notificacao').map(n => n.id),
    [nodes],
  )

  // ── Seleção (edita o nó selecionado AO VIVO no painel à direita) ───────────
  const [selectedId, setSelectedId] = useState<string | null>(null)
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

  // Enquadra o fluxo ao abrir / trocar de pipeline (foco direto no conteúdo).
  const fittedPipeRef = useRef<string | null>(null)
  useEffect(() => {
    if (!data || data.nodes.length === 0 || fittedPipeRef.current === pipeline) return
    fittedPipeRef.current = pipeline
    const t = setTimeout(() => rf.fitView({ padding: 0.2, duration: 250 }), 90)
    return () => clearTimeout(t)
  }, [data, pipeline, rf])

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

  // Mover/selecionar nó → marca dirty quando muda posição; sincroniza seleção.
  const onNodesChange = useCallback(
    (changes: NodeChange<Node>[]) => {
      setNodes(nds => applyNodeChanges(changes, nds))
      if (changes.some(c => c.type === 'position' && c.dragging === false)) setDirty(true)
      // Mantém `selectedId` em sincronia com o React Flow (clique no canvas/nó).
      for (const c of changes) {
        if (c.type !== 'select') continue
        if (c.selected) setSelectedId(c.id)
        else setSelectedId(prev => (prev === c.id ? null : prev))
      }
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
      // Próximo "Link_N" sequencial = nº de arestas normais já existentes + 1.
      const linkN = edges.filter(e => !isBranch(e)).length + 1
      setEdges(eds =>
        addEdge(
          {
            id: `dep:${conn.source}->${conn.target}`,
            source: conn.source!,
            target: conn.target!,
            type: 'smoothstep',
            markerEnd: EDGE_ARROW,
            label: `Link_${linkN}`,
            labelStyle: LINK_LABEL_STYLE,
            labelBgStyle: LINK_LABEL_BG,
            labelShowBg: false,
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
        // Decisão: cria o nó (defaults) e SELECIONA — o painel à direita já edita.
        const name = nextName('DECISAO', nameSet())
        const cond = defaultCondition()
        const node: Node = {
          id: name,
          type: 'decisao',
          position: { x, y },
          selected: true,
          data: { name, condition: cond, label: conditionLabel(cond), isNew: true } as DecisaoNodeData,
        }
        setNodes(nds => [...nds.map(n => n.selected ? { ...n, selected: false } : n), node])
        setDirty(true)
        setSelectedId(name)
        return
      }
      if (tipo === 'notificacao') {
        // Notificação Teams: cria o nó (defaults) e SELECIONA — o painel edita.
        const name = nextName('NOTIFICACAO', nameSet())
        const notify = defaultNotify()
        const node: Node = {
          id: name,
          type: 'notificacao',
          position: { x, y },
          selected: true,
          data: { name, notify, label: notifyLabel(notify, gruposById), isNew: true } as NotificacaoNodeData,
        }
        setNodes(nds => [...nds.map(n => n.selected ? { ...n, selected: false } : n), node])
        setDirty(true)
        setSelectedId(name)
        return
      }
      // Etapa: cria o nó (nome default único + comando vazio) e SELECIONA p/ preencher.
      const t = toEtapaType(tipo)
      const name = nextName('NOVA_ETAPA', nameSet())
      const data: EtapaNodeData = {
        name,
        type: t,
        command: null,
        order: maxOrder() + 1,
        ssh_conn_id: '',
        verbose_log: false,
        mssql_conn_id: '',
        mssql_database: '',
        params: [],
        isNew: true,
      }
      const node: Node = { id: name, type: 'etapa', position: { x, y }, selected: true, data }
      setNodes(nds => [...nds.map(n => n.selected ? { ...n, selected: false } : n), node])
      setDirty(true)
      setSelectedId(name)
    },
    [rf, nameSet, maxOrder, setNodes, gruposById],
  )

  // Atualiza o `data` de um nó (etapa) — usado pelo painel à direita ao vivo.
  function patchNodeData(nodeId: string, patch: Record<string, unknown>) {
    setNodes(nds => nds.map(n => n.id === nodeId ? { ...n, data: { ...n.data, ...patch } } : n))
    setDirty(true)
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
    setSelectedId(prev => (prev === oldName ? name : prev))
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

  // Atualiza a config de uma notificação (merge) e o rótulo do nó (nome do grupo).
  function patchNotify(nodeId: string, patch: Partial<NotifyConfig>) {
    setNodes(nds => nds.map(n => {
      if (n.id !== nodeId || n.type !== 'notificacao') return n
      const cur = (n.data as NotificacaoNodeData).notify ?? defaultNotify()
      const next = { ...cur, ...patch }
      return { ...n, data: { ...n.data, notify: next, label: notifyLabel(next, gruposById) } }
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
    setSelectedId(prev => (prev === id ? null : prev))
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

  // Re-roda o auto-layout sobre o grafo VIVO (inclui nós recém-adicionados,
  // ainda sem execution_order salvo — ex.: notificação recém-conectada).
  const reorganizar = useCallback(() => {
    const savedOrder = new Map<string, number>()
    for (const n of apiNodesRef.current) {
      if (n.execution_order != null) savedOrder.set(n.job_name, n.execution_order)
    }
    setNodes(nds => {
      const pos = liveLayout(nds, edges, savedOrder)
      return nds.map(n => (pos[n.id] ? { ...n, position: pos[n.id] } : n))
    })
    setDirty(true)
  }, [setNodes, edges])

  // ── Salvar: materializa o grafo (todos os nós) ────────────────────────────
  async function salvar() {
    setSaving(true)
    try {
      // Guard: nó de notificação exige um canal (grupo). O backend rejeita o
      // /fluxo inteiro se faltar — avisamos claro (nomeando os nós) antes de
      // chamar a API, em vez de deixar o save falhar com erro genérico.
      const notifSemCanal = nodes
        .filter(n => n.type === 'notificacao')
        .filter(n => (n.data as { notify?: { grupo_id: number | null } }).notify?.grupo_id == null)
        .map(n => n.id)
      if (notifSemCanal.length) {
        toast.error(`Escolha um canal na notificação: ${notifSemCanal.join(', ')}.`)
        setSaving(false)
        return
      }

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
        const isNotificacao = n.type === 'notificacao'
        let condition: Record<string, unknown> | null = null
        if (isDecisao) {
          const cur = (d.condition as NodeCondition | undefined) ?? defaultCondition()
          const ramos = ramosByDecisao.get(n.id) ?? { sim: [], nao: [] }
          if (cur.tipo === 'linhas_job') {
            // Decisão por linhas processadas: usa job a montante (e job filho
            // opcional). Omite os campos de tabela/sql/banco/conexão.
            condition = {
              tipo: cur.tipo,
              operador: cur.operador,
              valor: (cur.valor ?? '').toString().trim(),
              job_name: (cur.job_name || '').trim(),
              child_job: (cur.child_job || '').trim(),
              ramo_verdadeiro: ramos.sim,
              ramo_falso: ramos.nao,
            }
          } else {
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
        }
        const jobType = isDecisao ? 'decisao' : isNotificacao ? 'notificacao' : ((d.type as string) || 'datastage')
        const base = {
          job_name: n.id,
          job_type: jobType,
          job_command: (isDecisao || isNotificacao) ? null : ((d.command as string | null) ?? null),
          execution_order: (d.order as number) ?? 1,
          depends_on_jobs: Array.from(depsByTarget.get(n.id) ?? []),
          condition,
          layout_x: Math.round(n.position.x),
          layout_y: Math.round(n.position.y),
        }
        if (isDecisao) return base
        if (isNotificacao) {
          // Notificação: emite a chave `notify` (análogo ao `condition` da decisão);
          // não envia condition nem campos de etapa. grupo_id é obrigatório no backend.
          const cur = (d.notify as NotifyConfig | undefined) ?? defaultNotify()
          return {
            ...base,
            notify: {
              grupo_id: cur.grupo_id,
              template_id: cur.template_id ?? null,
              mensagem: (cur.mensagem ?? '').toString(),
            },
          }
        }
        // Etapa: inclui SEMPRE os campos por tipo (round-trip — presença de chave
        // no backend; ausência não zera). Lidos do `data` do nó.
        const rawParams = (d.params as JobParam[] | undefined) ?? []
        return {
          ...base,
          ssh_conn_id: (d.ssh_conn_id as string | null) ?? null,
          verbose_log: !!d.verbose_log,
          mssql_conn_id: (d.mssql_conn_id as string | null) ?? null,
          mssql_database: (d.mssql_database as string | null) ?? null,
          params: rawParams
            .filter(p => (p.param_name ?? '').trim())
            .map(p => ({
              param_name: p.param_name.trim(),
              param_type: p.param_type,
              param_value: p.param_value,
            })),
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
      if (node.type === 'notificacao') return '#14b8a6'
      const t = (node.data as { type?: EtapaType }).type
      return (t && TYPE_META[t]?.hex) || '#94a3b8'
    },
    [],
  )

  // Duplo-clique apenas garante a seleção (o painel à direita já edita ao vivo).
  const onNodeClick = useCallback((_: React.MouseEvent, node: Node) => {
    setSelectedId(node.id)
  }, [])

  // Fecha o painel de propriedades (desseleciona o nó) — botão "recolher".
  const closePanel = useCallback(() => {
    setNodes(nds => nds.map(n => (n.selected ? { ...n, selected: false } : n)))
    setSelectedId(null)
  }, [setNodes])

  // Ramos da decisão SELECIONADA (derivados das arestas de ramo) — read-only no painel.
  const selRamos = useMemo(() => {
    const sim: string[] = []; const nao: string[] = []
    if (!selectedId) return { sim, nao }
    for (const e of edges) {
      if (!isBranch(e) || e.source !== selectedId) continue
      ;(edgeRamo(e) === 'nao' ? nao : sim).push(e.target)
    }
    return { sim, nao }
  }, [edges, selectedId])

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

  const selNode = selectedId ? nodes.find(n => n.id === selectedId) ?? null : null

  return (
    <div className="flex h-full w-full overflow-hidden rounded-xl border border-edge bg-canvas">
      {/* Canvas (ocupa o resto; o painel à direita encolhe o canvas, não sobrepõe) */}
      <div className="relative min-w-0 flex-1" ref={wrapperRef}>
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
          onNodeClick={onNodeClick}
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

          {/* Paleta arrastar-para-criar (barra vertical fina, esquerda) */}
          <Panel position="top-left">
            <Paleta open={paletaOpen} onToggle={() => setPaletaOpen(o => !o)} />
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
      </div>

      {/* Painel de propriedades INLINE (à direita) — só quando há nó selecionado */}
      {selNode && (
        <PropriedadesPanel
          node={selNode}
          ramos={selRamos}
          jobNames={jobNames}
          sshConns={sshConns}
          mssqlConns={mssqlConns}
          dbServer={dbServer}
          dbDatabases={dbDatabases}
          grupos={grupos}
          onRename={renomearNovo}
          onPatchData={patchNodeData}
          onPatchCondition={patchCondition}
          onPatchNotify={patchNotify}
          onDelete={id => setDelNodeId(id)}
          onClose={closePanel}
        />
      )}

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

// ─────────────────────────────────────────────────────────────────────────────
// Painel de propriedades INLINE (à direita) — edita o nó selecionado ao vivo.
// Substitui os antigos modais "Nova etapa" e "Condição da decisão".
// ─────────────────────────────────────────────────────────────────────────────
interface PropriedadesPanelProps {
  node: Node | null
  ramos: { sim: string[]; nao: string[] }
  jobNames: string[]
  sshConns: { conn_id: string; host: string }[]
  mssqlConns: { conn_id: string; host: string }[]
  dbServer: string | null
  dbDatabases: string[]
  grupos: MsgGrupo[]
  onRename: (oldName: string, novo: string) => boolean
  onPatchData: (nodeId: string, patch: Record<string, unknown>) => void
  onPatchCondition: (nodeId: string, patch: Partial<NodeCondition>) => void
  onPatchNotify: (nodeId: string, patch: Partial<NotifyConfig>) => void
  onDelete: (id: string) => void
  onClose: () => void
}

function PropriedadesPanel({
  node, ramos, jobNames, sshConns, mssqlConns, dbServer, dbDatabases, grupos,
  onRename, onPatchData, onPatchCondition, onPatchNotify, onDelete, onClose,
}: PropriedadesPanelProps) {
  return (
    <aside className="flex w-[320px] shrink-0 flex-col overflow-y-auto border-l border-edge bg-panel">
      {/* Cabeçalho do painel — o botão recolhe (desseleciona o nó) */}
      <div className="sticky top-0 z-10 flex items-center gap-2 border-b border-edge bg-panel/95 px-3 py-2.5 backdrop-blur">
        <button
          onClick={onClose}
          title="Fechar / recolher propriedades"
          className="flex items-center justify-center rounded p-0.5 text-dim transition-colors hover:bg-edge/40 hover:text-ink"
        >
          <PanelRightClose size={15} />
        </button>
        <span className="text-xs font-semibold uppercase tracking-wide text-dim">Propriedades</span>
      </div>

      {!node ? (
        <PainelVazio />
      ) : node.type === 'decisao' ? (
        <PainelDecisao
          key={node.id}
          node={node}
          ramos={ramos}
          jobNames={jobNames}
          mssqlConns={mssqlConns}
          onRename={onRename}
          onPatchCondition={onPatchCondition}
          onDelete={onDelete}
        />
      ) : node.type === 'notificacao' ? (
        <PainelNotificacao
          key={node.id}
          node={node}
          grupos={grupos}
          onRename={onRename}
          onPatchNotify={onPatchNotify}
          onDelete={onDelete}
        />
      ) : (
        <PainelEtapa
          key={node.id}
          node={node}
          sshConns={sshConns}
          mssqlConns={mssqlConns}
          dbServer={dbServer}
          dbDatabases={dbDatabases}
          onRename={onRename}
          onPatchData={onPatchData}
          onDelete={onDelete}
        />
      )}
    </aside>
  )
}

// Estado-guia quando nada está selecionado.
function PainelVazio() {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-3 px-5 py-10 text-center">
      <MousePointerClick size={26} className="text-dim/60" />
      <p className="text-sm font-medium text-ink">Selecione um nó para editar suas propriedades</p>
      <p className="text-xs leading-relaxed text-dim">
        Clique em uma etapa ou decisão no canvas. Para criar um novo nó,
        <strong className="text-ink"> arraste </strong> um tipo da paleta (à esquerda) para o canvas.
      </p>
    </div>
  )
}

// Campo de nome reutilizado pelos dois painéis: editável só se `isNew`.
function NomeField({
  id, name, isNew, placeholder, onRename,
}: { id: string; name: string; isNew: boolean; placeholder: string; onRename: (oldName: string, novo: string) => boolean }) {
  const [draft, setDraft] = useState(name)
  useEffect(() => { setDraft(name) }, [id, name])

  function commit() {
    if (!isNew) return
    if (draft.trim() === name) return
    if (!onRename(id, draft)) setDraft(name)
  }

  return (
    <div className="flex flex-col gap-1">
      <Input
        label={isNew ? 'Nome *' : 'Nome'}
        value={draft}
        disabled={!isNew}
        onChange={e => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={e => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur() }}
        placeholder={placeholder}
        className={`font-mono text-xs ${!isNew ? 'opacity-60' : ''}`}
      />
      {!isNew
        ? <p className="text-[10px] text-dim/70">O nome de um nó já salvo não é editável aqui.</p>
        : <p className="text-[10px] text-dim/70">Letras, números, espaço, _ . -</p>}
    </div>
  )
}

// ── Painel de uma ETAPA ──────────────────────────────────────────────────────
interface PainelEtapaProps {
  node: Node
  sshConns: { conn_id: string; host: string }[]
  mssqlConns: { conn_id: string; host: string }[]
  dbServer: string | null
  dbDatabases: string[]
  onRename: (oldName: string, novo: string) => boolean
  onPatchData: (nodeId: string, patch: Record<string, unknown>) => void
  onDelete: (id: string) => void
}

function PainelEtapa({ node, sshConns, mssqlConns, dbServer, dbDatabases, onRename, onPatchData, onDelete }: PainelEtapaProps) {
  const d = node.data as EtapaNodeData
  const isNew = !!d.isNew
  const meta = TYPE_META[d.type]
  const Icon = meta.icon

  // Valor consumido pela fonte única de campos por tipo (JobTypeFields).
  const typeValue: JobTypeFieldsValue = {
    job_type: d.type as JobFieldsType,
    job_command: d.command ?? '',
    ssh_conn_id: d.ssh_conn_id ?? '',
    verbose_log: !!d.verbose_log,
    mssql_conn_id: d.mssql_conn_id ?? '',
    mssql_database: d.mssql_database ?? '',
    params: (d.params as JobParam[] | undefined) ?? [],
  }

  // Patch do JobTypeFields → mapeia job_command de volta p/ `command` (nullável).
  function patchType(patch: Partial<JobTypeFieldsValue>) {
    const out: Record<string, unknown> = { ...patch }
    if ('job_command' in patch) {
      out.command = (patch.job_command ?? '') === '' ? null : patch.job_command
      delete out.job_command
    }
    if ('job_type' in patch) delete out.job_type   // tipo só muda na criação
    onPatchData(node.id, out)
  }

  return (
    <div className="flex flex-1 flex-col gap-3 p-3">
      {/* Cabeçalho: chip do tipo */}
      <div className="flex items-center gap-2">
        <span className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-md ${meta.chip}`}>
          <Icon size={15} strokeWidth={2.2} />
        </span>
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-ink">{d.name}</p>
          <p className="text-[10px] text-dim">{meta.label}</p>
        </div>
      </div>

      <NomeField id={node.id} name={d.name} isNew={isNew} placeholder="ex: CARGA_CLIENTES" onRename={onRename} />

      {/* Tipo (editável só na criação) e Ordem */}
      <div className="grid grid-cols-2 gap-2">
        <Select
          label="Tipo"
          value={d.type}
          disabled={!isNew}
          onChange={e => onPatchData(node.id, { type: e.target.value as EtapaType })}
          className={`text-xs ${!isNew ? 'opacity-60' : ''}`}
        >
          {CREATABLE_TYPES.map(t => <option key={t} value={t}>{TYPE_META[t].label}</option>)}
        </Select>
        <div className="flex flex-col gap-1">
          <label className="text-xs font-medium text-dim">Ordem</label>
          <input
            type="number"
            min={1}
            value={d.order ?? ''}
            onChange={e => {
              const n = parseInt(e.target.value)
              onPatchData(node.id, { order: Number.isFinite(n) && n >= 1 ? n : 1 })
            }}
            className="rounded-md border border-edge bg-panel px-2 py-1 text-xs text-ink focus:outline-none focus:ring-1 focus:ring-blue-500"
          />
        </div>
      </div>
      {!isNew && <p className="-mt-1.5 text-[10px] text-dim/70">O tipo de um nó já salvo não é editável.</p>}

      <div className="border-t border-edge pt-2.5">
        {/* Campos por TIPO — fonte única (vale na Lista e no Fluxo), modo compacto */}
        <JobTypeFields
          value={typeValue}
          onChange={patchType}
          sshConns={sshConns}
          mssqlConns={mssqlConns}
          dbServer={dbServer}
          dbDatabases={dbDatabases}
          compact
        />
      </div>

      <div className="mt-auto border-t border-edge pt-3">
        <Button variant="danger" size="sm" className="w-full justify-center" onClick={() => onDelete(node.id)}>
          <Trash2 size={13} /> Excluir etapa
        </Button>
      </div>
    </div>
  )
}

// ── Painel de uma DECISÃO ────────────────────────────────────────────────────
interface PainelDecisaoProps {
  node: Node
  ramos: { sim: string[]; nao: string[] }
  jobNames: string[]
  mssqlConns: { conn_id: string; host: string }[]
  onRename: (oldName: string, novo: string) => boolean
  onPatchCondition: (nodeId: string, patch: Partial<NodeCondition>) => void
  onDelete: (id: string) => void
}

function PainelDecisao({ node, ramos, jobNames, mssqlConns, onRename, onPatchCondition, onDelete }: PainelDecisaoProps) {
  const d = node.data as DecisaoNodeData
  const isNew = !!d.isNew
  const c = d.condition ?? defaultCondition()
  const patch = (p: Partial<NodeCondition>) => onPatchCondition(node.id, p)
  // Jobs disponíveis para a condição "linhas processadas" (exclui a própria decisão).
  const jobsDisponiveis = jobNames.filter(j => j !== node.id)

  return (
    <div className="flex flex-1 flex-col gap-3 p-3">
      {/* Cabeçalho */}
      <div className="flex items-center gap-2">
        <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-indigo-500 text-white">
          <GitBranch size={15} strokeWidth={2.2} />
        </span>
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-ink">{d.name}</p>
          <p className="text-[10px] text-dim">Decisão (roteador)</p>
        </div>
      </div>

      <NomeField id={node.id} name={d.name} isNew={isNew} placeholder="ex: DECISAO_VOLUME" onRename={onRename} />

      {/* Editor de condição compacto (mesma lógica do DecisaoForm) */}
      <div className="border-t border-edge pt-2.5">
        <div className="mb-2 flex items-center gap-1.5">
          <GitBranch size={12} className="text-indigo-600 dark:text-indigo-300" />
          <span className="text-xs font-semibold text-ink">Expressão da condição</span>
        </div>

        <div className="flex flex-col gap-2">
          <div className="grid grid-cols-[1fr_64px] gap-2">
            <Select label="Tipo" value={c.tipo} onChange={e => patch({ tipo: e.target.value as NodeCondition['tipo'] })} className="text-xs">
              <option value="contagem">Contagem de registros</option>
              <option value="query">Valor de uma query</option>
              <option value="linhas_job">Linhas processadas</option>
            </Select>
            <Select label="Oper." value={c.operador} onChange={e => patch({ operador: e.target.value })} className="text-center text-xs">
              {COND_OPERADORES.map(op => <option key={op} value={op}>{op}</option>)}
            </Select>
          </div>

          <Input
            label="Valor *"
            type={c.tipo === 'linhas_job' ? 'number' : 'text'}
            value={c.valor}
            onChange={e => patch({ valor: e.target.value })}
            placeholder={c.tipo === 'query' ? 'ex: 1' : 'ex: 10000'}
            className="font-mono text-xs"
          />

          {c.tipo === 'linhas_job' ? (
            <>
              <div className="flex flex-col gap-1">
                <Select
                  label="Job *"
                  value={c.job_name ?? ''}
                  onChange={e => patch({ job_name: e.target.value })}
                  className="text-xs"
                >
                  <option value="">Selecione um job…</option>
                  {jobsDisponiveis.map(j => (
                    <option key={j} value={j}>{j}</option>
                  ))}
                  {/* Mantém o valor salvo visível mesmo se o job não estiver mais no fluxo */}
                  {c.job_name && !jobsDisponiveis.includes(c.job_name) && (
                    <option value={c.job_name}>{c.job_name} (fora do fluxo)</option>
                  )}
                </Select>
                {jobsDisponiveis.length === 0 && (
                  <p className="text-[10px] text-dim/70">Crie ao menos uma etapa para escolher o job.</p>
                )}
              </div>
              <div className="flex flex-col gap-1">
                <Input
                  label="Job filho (opcional)"
                  value={c.child_job ?? ''}
                  onChange={e => patch({ child_job: e.target.value })}
                  placeholder="ex: JB_CARGA_DETALHE"
                  className="font-mono text-xs"
                />
                <p className="text-[10px] text-dim/70">Vazio = usa o total do job.</p>
              </div>
            </>
          ) : c.tipo === 'contagem' ? (
            <>
              <Input
                label="Tabela * (db.schema.tabela)"
                value={c.tabela ?? ''}
                onChange={e => patch({ tabela: e.target.value })}
                placeholder="db.schema.tabela"
                className="font-mono text-xs"
              />
              <Input
                label="Banco (opcional)"
                value={c.database ?? ''}
                onChange={e => patch({ database: e.target.value })}
                placeholder="ex: BI_DW"
                className="font-mono text-xs"
              />
            </>
          ) : (
            <Textarea
              label="SQL (somente SELECT) *"
              value={c.sql ?? ''}
              rows={3}
              onChange={e => patch({ sql: e.target.value })}
              placeholder="ex: SELECT MAX(flag) FROM dbo.Controle WHERE ..."
              className="font-mono text-xs"
            />
          )}

          {/* Conexão MSSQL não se aplica à decisão por linhas processadas. */}
          {c.tipo !== 'linhas_job' && (
            <Select
              label="Conexão MSSQL (opcional)"
              value={c.mssql_conn_id ?? ''}
              onChange={e => patch({ mssql_conn_id: e.target.value })}
              className="text-xs"
            >
              <option value="">Conexão padrão</option>
              {mssqlConns.map(cn => (
                <option key={cn.conn_id} value={cn.conn_id}>{cn.conn_id}{cn.host ? ` (${cn.host})` : ''}</option>
              ))}
            </Select>
          )}
        </div>
      </div>

      {/* Ramos atuais (derivados das arestas) — read-only */}
      <div className="rounded-lg border border-edge bg-canvas p-2.5">
        <p className="mb-2 text-[10px] leading-relaxed text-dim">
          Os ramos são definidos arrastando os handles <b>sim</b> (direita) e <b>não</b> (baixo)
          da decisão até as etapas, direto no canvas.
        </p>
        <div className="flex flex-col gap-2">
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
            Ligue ao menos um job em algum ramo (arrastando) antes de salvar.
          </p>
        )}
      </div>

      <div className="mt-auto border-t border-edge pt-3">
        <Button variant="danger" size="sm" className="w-full justify-center" onClick={() => onDelete(node.id)}>
          <Trash2 size={13} /> Excluir decisão
        </Button>
      </div>
    </div>
  )
}

// ── Painel de uma NOTIFICAÇÃO (Teams) ────────────────────────────────────────
interface PainelNotificacaoProps {
  node: Node
  grupos: MsgGrupo[]
  onRename: (oldName: string, novo: string) => boolean
  onPatchNotify: (nodeId: string, patch: Partial<NotifyConfig>) => void
  onDelete: (id: string) => void
}

function PainelNotificacao({ node, grupos, onRename, onPatchNotify, onDelete }: PainelNotificacaoProps) {
  const d = node.data as NotificacaoNodeData
  const isNew = !!d.isNew
  const cfg = d.notify ?? defaultNotify()
  const patch = (p: Partial<NotifyConfig>) => onPatchNotify(node.id, p)
  const msgRef = useRef<HTMLTextAreaElement>(null)

  // Templates do grupo selecionado (Select "Modelo"). Sem grupo → não busca.
  // Degrada para [] se a tabela/endpoint não existir (try/except no backend).
  const { data: tplData } = useQuery<{ data: MsgTemplate[] }>({
    queryKey: ['msg-templates', cfg.grupo_id],
    queryFn: () => apiFetch(`/msg/templates?grupo_id=${cfg.grupo_id}`),
    enabled: cfg.grupo_id != null,
    staleTime: 300_000,
  })
  const templates = tplData?.data ?? []

  // Troca de grupo: zera o modelo (templates pertencem ao grupo).
  function onGrupoChange(e: React.ChangeEvent<HTMLSelectElement>) {
    const v = e.target.value
    patch({ grupo_id: v ? Number(v) : null, template_id: null })
  }

  return (
    <div className="flex flex-1 flex-col gap-3 p-3">
      {/* Cabeçalho */}
      <div className="flex items-center gap-2">
        <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-teal-500 text-white">
          <BellRing size={15} strokeWidth={2.2} />
        </span>
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-ink">{d.name}</p>
          <p className="text-[10px] text-dim">Notificação (Teams)</p>
        </div>
      </div>

      <NomeField id={node.id} name={d.name} isNew={isNew} placeholder="ex: AVISA_TIME" onRename={onRename} />

      {/* Config da notificação */}
      <div className="border-t border-edge pt-2.5">
        <div className="mb-2 flex items-center gap-1.5">
          <BellRing size={12} className="text-teal-600 dark:text-teal-300" />
          <span className="text-xs font-semibold text-ink">Mensagem do Teams</span>
        </div>

        <div className="flex flex-col gap-2">
          <div className="flex flex-col gap-1">
            <Select
              label="Grupo (canal) *"
              value={cfg.grupo_id != null ? String(cfg.grupo_id) : ''}
              onChange={onGrupoChange}
              className="text-xs"
            >
              <option value="">Selecione um canal…</option>
              {grupos.map(g => (
                <option key={g.id} value={g.id}>{g.nome}</option>
              ))}
              {/* Mantém o grupo salvo visível mesmo se ele não estiver mais na lista */}
              {cfg.grupo_id != null && !grupos.some(g => g.id === cfg.grupo_id) && (
                <option value={cfg.grupo_id}>#{cfg.grupo_id} (fora da lista)</option>
              )}
            </Select>
            {grupos.length === 0 && (
              <p className="text-[10px] text-dim/70">
                Nenhum canal cadastrado — crie um em Mensagens (Teams) antes de notificar.
              </p>
            )}
          </div>

          <div className="flex flex-col gap-1">
            <Select
              label="Modelo (opcional)"
              value={cfg.template_id != null ? String(cfg.template_id) : ''}
              onChange={e => patch({ template_id: e.target.value ? Number(e.target.value) : null })}
              disabled={cfg.grupo_id == null}
              className={`text-xs ${cfg.grupo_id == null ? 'opacity-60' : ''}`}
            >
              <option value="">Nenhum (mensagem livre)</option>
              {templates.map(t => (
                <option key={t.id} value={t.id}>{t.nome}</option>
              ))}
              {/* Mantém o modelo salvo visível mesmo se ele não estiver na lista atual */}
              {cfg.template_id != null && !templates.some(t => t.id === cfg.template_id) && (
                <option value={cfg.template_id}>#{cfg.template_id} (fora da lista)</option>
              )}
            </Select>
            {cfg.grupo_id == null
              ? <p className="text-[10px] text-dim/70">Escolha um canal para listar os modelos.</p>
              : templates.length === 0 && (
                <p className="text-[10px] text-dim/70">Nenhum modelo neste canal — use a mensagem abaixo.</p>
              )}
          </div>

          <div className="flex flex-col gap-1">
            <Textarea
              ref={msgRef}
              label="Mensagem (opcional)"
              value={cfg.mensagem ?? ''}
              rows={4}
              onChange={e => patch({ mensagem: e.target.value })}
              placeholder="ex: Pipeline {pipeline} concluído com status {status}."
              className="text-xs"
            />
            <p className="text-[10px] text-dim/70">Vazio = usa o corpo do modelo.</p>
            <PlaceholderPicker
              label="Inserir:"
              placeholders={['pipeline', 'job', 'linhas', 'status', 'data']}
              targetRef={msgRef}
              value={cfg.mensagem ?? ''}
              onChange={v => patch({ mensagem: v })}
            />
          </div>
        </div>
      </div>

      {/* Aviso quando falta o canal (grupo_id obrigatório no save). */}
      {cfg.grupo_id == null && (
        <p className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[10px] text-amber-800 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-300">
          Selecione um canal (grupo) antes de salvar o fluxo.
        </p>
      )}

      <div className="mt-auto border-t border-edge pt-3">
        <Button variant="danger" size="sm" className="w-full justify-center" onClick={() => onDelete(node.id)}>
          <Trash2 size={13} /> Excluir notificação
        </Button>
      </div>
    </div>
  )
}
