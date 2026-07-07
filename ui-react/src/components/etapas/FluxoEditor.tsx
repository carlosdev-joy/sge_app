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
import { Modal } from '../ui/Modal'
import { toast } from '../ui/Toast'
import {
  Save, RefreshCw, AlertCircle, GitBranch, Trash2, BellRing, Database,
  ChevronLeft, ChevronRight, ChevronUp, ChevronDown, Maximize2, Minimize2,
  MousePointerClick, Search, X,
} from 'lucide-react'
import { EtapaNode, type EtapaNodeData } from './EtapaNode'
import { DecisaoNode, casoCor, type CasoSwitch, type DecisaoNodeData, type NodeCondition } from './DecisaoNode'
import { NotificacaoNode, type NotificacaoNodeData } from './NotificacaoNode'
import { SqlNode, type SqlNodeData } from './SqlNode'
import { TYPE_META, TYPE_ORDER, CREATABLE_TYPES, type EtapaType } from './types'
import { defaultCondition, toNodeCondition, conditionLabel } from './condition'
import { useColorMode } from './useColorMode'
import { jobTypeFieldsErrors, type JobFieldsType, type JobParam } from './JobTypeFields'
import {
  type Condition, type NotifyConfig, type SqlConfig, type MsgGrupo,
  defaultNotify, toNotifyConfig, notifyLabel, defaultSql, toSqlConfig, sqlLabel,
} from './fluxoTypes'
import { PropriedadesPanel } from './paineis/PropriedadesPanel'

const nodeTypes = { etapa: EtapaNode, decisao: DecisaoNode, notificacao: NotificacaoNode, sql: SqlNode }

// ── Dock inferior de propriedades (fase 3 do redesign) ──────────────────────
type DockEstado = 'colapsado' | 'aberto' | 'max'
const DOCK_LS_ESTADO = 'orq.fluxo.dock.estado'
const DOCK_LS_ALTURA = 'orq.fluxo.dock.altura'
const DOCK_MIN_H = 180
const DOCK_MAX_H = 560

// ── Tipos do payload da API (/fluxo) ────────────────────────────────────────
// (Condition/NotifyConfig/SqlConfig e o catálogo MsgGrupo/MsgTemplate moram em
// ./fluxoTypes — compartilhados com os painéis de propriedades.)
interface FluxoNode {
  job_name: string
  job_type: string
  job_command: string | null
  execution_order: number
  depends_on_jobs: string[]
  condition: Condition | null
  notify: NotifyConfig | null
  // Config do nó SQL — chave `sql_node` na API (o backend usa sql_node; o campo
  // interno do config é `sql`, a query, daí o nome externo distinto).
  sql_node: SqlConfig | null
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
  const realEdges = edges.filter((e) => e && e.source && e.target)
  const pos: Record<string, { x: number; y: number }> = {}

  // Sem conectores no desenho → não há grafo: cai no layout por execution_order.
  if (realEdges.length === 0) {
    const byOrd = new Map<number, string[]>()
    for (const n of nodes) {
      const o = savedOrder.get(n.id) ?? 1
      if (!byOrd.has(o)) byOrd.set(o, [])
      byOrd.get(o)!.push(n.id)
    }
    Array.from(byOrd.keys()).sort((a, b) => a - b).forEach((o, ci) => {
      byOrd.get(o)!.forEach((id, ri) => { pos[id] = { x: ci * COL_W, y: ri * ROW_H } })
    })
    return pos
  }

  // COM conectores → a COLUNA segue o GRAFO (caminho mais longo a partir das
  // raízes, pelos conectores do desenho), NÃO o execution_order. Assim um nó
  // ligado ENTRE dois outros (ex.: notificação) fica inline, na coluna do meio,
  // em vez de empilhar na coluna de um vizinho.
  const preds = new Map<string, string[]>()
  for (const n of nodes) preds.set(n.id, [])
  for (const e of realEdges) {
    if (preds.has(e.target) && preds.has(e.source)) preds.get(e.target)!.push(e.source)
  }
  const col = new Map<string, number>()
  const visiting = new Set<string>()
  const resolve = (id: string): number => {
    const cached = col.get(id)
    if (cached != null) return cached
    if (visiting.has(id)) return 0   // guarda contra ciclo
    visiting.add(id)
    let c = 0
    for (const p of preds.get(id) ?? []) c = Math.max(c, resolve(p) + 1)
    visiting.delete(id)
    col.set(id, c)
    return c
  }
  for (const n of nodes) resolve(n.id)
  const byCol = new Map<number, string[]>()
  for (const n of nodes) {
    const c = col.get(n.id) ?? 0
    if (!byCol.has(c)) byCol.set(c, [])
    byCol.get(c)!.push(n.id)
  }
  const cols = Array.from(byCol.keys()).sort((a, b) => a - b)
  // Centraliza verticalmente cada coluna em torno da linha média — desenho
  // equilibrado (uma cadeia linear fica numa única linha; ramos saem simétricos).
  const maxRows = Math.max(1, ...cols.map((c) => byCol.get(c)!.length))
  cols.forEach((c, ci) => {
    const ids = byCol.get(c)!
    const offset = (maxRows - ids.length) / 2
    ids.forEach((id, ri) => {
      pos[id] = { x: ci * COL_W, y: (ri + offset) * ROW_H }
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
const NAO_LABEL_STYLE = { fill: '#475569', fontSize: 11, fontWeight: 700 }
// Pílula de fundo do rótulo do ramo — deixa o "sim"/"não" legível no próprio
// ramo (substitui a legenda). Cores fixas (badge), legíveis nos dois temas.
const SIM_LABEL_BG = { fill: '#dcfce7', stroke: '#86efac' }
const NAO_LABEL_BG = { fill: '#e2e8f0', stroke: '#cbd5e1' }
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
    if (n.job_type === 'sql') {
      const sql = toSqlConfig(n.sql_node)
      const data: SqlNodeData = { name: n.job_name, sql, label: sqlLabel(sql) }
      return { id: n.job_name, type: 'sql' as const, position, data }
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

// Aresta de ramo a partir de uma decisão. `ramo` identifica a saída: 'sim'/'nao'
// (binária), 'senao' (padrão do switch) ou o NOME do caso (switch — passe
// `casoIdx` para colorir a aresta com a mesma cor do handle do caso).
function branchEdge(decisao: string, ramo: string, alvo: string, casoIdx?: number): Edge {
  const isCaso = casoIdx != null
  const cor = isCaso ? casoCor(casoIdx) : undefined
  const labelText = ramo === 'sim' ? 'sim' : ramo === 'nao' ? 'não' : ramo === 'senao' ? 'senão' : ramo
  return {
    id: `ramo:${decisao}:${ramo}:${alvo}`,
    source: decisao,
    sourceHandle: isCaso ? `caso:${ramo}` : ramo,
    target: alvo,
    type: 'smoothstep',
    markerEnd: EDGE_ARROW,
    data: { branch: true, ramo, ...(isCaso ? { casoIdx } : {}) },
    style: isCaso ? { stroke: cor } : ramo === 'sim' ? SIM_STYLE : NAO_STYLE,
    label: labelText,
    labelStyle: isCaso
      ? { fill: cor, fontSize: 11, fontWeight: 700 }
      : ramo === 'sim' ? SIM_LABEL_STYLE : NAO_LABEL_STYLE,
    labelShowBg: true,
    labelBgStyle: isCaso ? { fill: '#f8fafc', stroke: '#cbd5e1' } : ramo === 'sim' ? SIM_LABEL_BG : NAO_LABEL_BG,
    labelBgPadding: [6, 3] as [number, number],
    labelBgBorderRadius: 8,
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
    const casos = Array.isArray(d.condition.casos) ? d.condition.casos : null
    if (casos) {
      // SWITCH: uma cor/handle por caso + o senão (padrão) por baixo.
      casos.forEach((c, i) => {
        for (const m of c?.ramo || []) edges.push(branchEdge(d.job_name, String(c?.nome || ''), m, i))
      })
      for (const m of d.condition.ramo_senao || []) edges.push(branchEdge(d.job_name, 'senao', m))
      continue
    }
    for (const m of d.condition.ramo_verdadeiro || []) edges.push(branchEdge(d.job_name, 'sim', m))
    for (const m of d.condition.ramo_falso || []) edges.push(branchEdge(d.job_name, 'nao', m))
  }
  return edges
}

const isBranch = (e: Edge) => !!(e.data as { branch?: boolean } | undefined)?.branch
const edgeRamo = (e: Edge) => (e.data as { ramo?: string } | undefined)?.ramo

// Conectar source→target criaria um ciclo? Anda pelos SUCESSORES de `target`
// (arestas normais E de ramo — ambas são ordem de execução) procurando `source`.
// Espelho client-side do _graph_has_cycle do backend: feedback na hora da
// conexão, em vez de só no 400 do save (o backend segue como autoridade).
function criaCiclo(edges: Edge[], source: string, target: string): boolean {
  if (source === target) return true
  const succ = new Map<string, string[]>()
  for (const e of edges) {
    if (!succ.has(e.source)) succ.set(e.source, [])
    succ.get(e.source)!.push(e.target)
  }
  const stack = [target]
  const seen = new Set<string>()
  while (stack.length) {
    const cur = stack.pop()!
    if (cur === source) return true
    if (seen.has(cur)) continue
    seen.add(cur)
    for (const nxt of succ.get(cur) ?? []) stack.push(nxt)
  }
  return false
}

// SEM espaço: job_name vira task_id no Airflow, que rejeita espaço no import
// da DAG (nós legados com espaço seguem funcionando; só a criação é estrita).
const NAME_RE = /^[A-Za-z0-9_.\-]+$/

// Próximo nome livre seguindo um prefixo (NOVA_ETAPA_1, DECISAO_2, …).
function nextName(prefix: string, taken: Set<string>): string {
  let i = 1
  while (taken.has(`${prefix}_${i}`)) i++
  return `${prefix}_${i}`
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
      { tipo: 'sql', label: 'SQL', chip: 'bg-violet-500 text-white', Icon: Database },
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
  // Somente leitura (perfil consulta): esconde paleta/ações e bloqueia edição.
  // A autoridade continua sendo a API (PERM_EDITAR no POST /fluxo).
  readOnly?: boolean
}

// Wrapper com o provider (necessário p/ useReactFlow/screenToFlowPosition).
export function FluxoEditor({ pipeline, readOnly = false }: Props) {
  return (
    <ReactFlowProvider>
      <FluxoEditorInner pipeline={pipeline} readOnly={readOnly} />
    </ReactFlowProvider>
  )
}

function FluxoEditorInner({ pipeline, readOnly = false }: Props) {
  const qc = useQueryClient()
  const colorMode = useColorMode()
  const rf = useReactFlow()
  const wrapperRef = useRef<HTMLDivElement>(null)
  const [nodes, setNodes] = useNodesState<Node>([])
  const [edges, setEdges, onEdgesChangeRF] = useEdgesState<Edge>([])
  const [dirty, setDirty] = useState(false)
  const [saving, setSaving] = useState(false)
  const [showPublish, setShowPublish] = useState(false)

  // ── Dock inferior de propriedades (fase 3 do redesign) ────────────────────
  // 3 estados (padrão Informatica/ADF): 'colapsado' (barra 36px c/ resumo),
  // 'aberto' (altura arrastável) e 'max' (~70% = modo focado). Preferências
  // persistidas por usuário em localStorage.
  const [dockEstado, setDockEstado] = useState<DockEstado>(() => {
    try {
      const v = localStorage.getItem(DOCK_LS_ESTADO)
      return v === 'colapsado' || v === 'max' ? v : 'aberto'
    } catch { return 'aberto' }
  })
  const [dockAltura, setDockAltura] = useState<number>(() => {
    try {
      const v = parseInt(localStorage.getItem(DOCK_LS_ALTURA) || '', 10)
      return Number.isFinite(v) ? Math.min(Math.max(v, DOCK_MIN_H), DOCK_MAX_H) : 280
    } catch { return 280 }
  })
  useEffect(() => {
    try { localStorage.setItem(DOCK_LS_ESTADO, dockEstado) } catch { /* sem storage */ }
  }, [dockEstado])
  useEffect(() => {
    try { localStorage.setItem(DOCK_LS_ALTURA, String(dockAltura)) } catch { /* sem storage */ }
  }, [dockAltura])

  // Alça de redimensionar: pointer events na borda superior do dock.
  const dockDragRef = useRef<{ startY: number; startH: number } | null>(null)
  const iniciarDragDock = useCallback((e: React.PointerEvent) => {
    e.preventDefault()
    dockDragRef.current = { startY: e.clientY, startH: dockAltura }
    const onMove = (ev: PointerEvent) => {
      const d = dockDragRef.current
      if (!d) return
      setDockAltura(Math.min(Math.max(d.startH + (d.startY - ev.clientY), DOCK_MIN_H), DOCK_MAX_H))
    }
    const onUp = () => {
      dockDragRef.current = null
      window.removeEventListener('pointermove', onMove)
      window.removeEventListener('pointerup', onUp)
    }
    window.addEventListener('pointermove', onMove)
    window.addEventListener('pointerup', onUp)
  }, [dockAltura])
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
  // Decisões (roteadores), notificações e nós SQL (não geram linhas) ficam de fora.
  const jobNames = useMemo(
    () => nodes.filter(n => n.type !== 'decisao' && n.type !== 'notificacao' && n.type !== 'sql').map(n => n.id),
    [nodes],
  )

  // Nós SQL do fluxo — alimentam o seletor "Nó SQL" da condição valor_sql.
  const sqlNodeNames = useMemo(
    () => nodes.filter(n => n.type === 'sql').map(n => n.id),
    [nodes],
  )

  // ── Seleção (edita o nó selecionado AO VIVO no painel à direita) ───────────
  const [selectedId, setSelectedId] = useState<string | null>(null)
  // Nós aguardando confirmação de exclusão (multi-seleção + Delete traz vários).
  const [delNodeIds, setDelNodeIds] = useState<string[] | null>(null)
  // Arestas AVULSAS selecionadas junto (Ctrl+clique) que não tocam os nós a
  // excluir — também caem na confirmação, senão sobreviveriam em silêncio.
  const [delEdgeIds, setDelEdgeIds] = useState<string[]>([])

  const { data, isLoading, isError, error } = useQuery<FluxoResp>({
    queryKey: ['fluxo', pipeline],
    queryFn: () => apiFetch(`/pipelines/${encodeURIComponent(pipeline)}/fluxo`),
    enabled: !!pipeline,
  })

  // Espelho do dirty p/ o guard do rebuild (ref: fora das deps de propósito —
  // dirty mudar não pode disparar rebuild com data velha).
  const dirtyRef = useRef(false)
  useEffect(() => { dirtyRef.current = dirty }, [dirty])

  useEffect(() => {
    if (!data) return
    // Nunca reconstruir por cima de edições NÃO salvas: um refetch (foco na
    // janela, staleTime vencido, rename) descartaria o trabalho em silêncio.
    // O rebuild volta a valer no próximo data após salvar (dirty=false).
    if (dirtyRef.current) return
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
      if (readOnly) return
      if (!conn.source || !conn.target) return

      // Bloqueia na hora a conexão que fecharia um ciclo (dep OU ramo) —
      // o mesmo grafo que o backend valida no save.
      if (criaCiclo(edges, conn.source, conn.target)) {
        toast.error('Essa conexão criaria um ciclo no fluxo — ajuste as dependências.')
        return
      }

      // A partir de uma decisão → cria/refaz a aresta de ramo.
      if (decisaoSet.has(conn.source)) {
        if (conn.target === conn.source) {
          toast.error('Uma decisão não pode ramificar para si mesma.')
          return
        }
        // Resolve a saída pelo handle: 'sim'/'nao' (binária), 'senao' (padrão do
        // switch) ou 'caso:<nome>' (switch — casoIdx dá a cor da aresta).
        const h = conn.sourceHandle || ''
        let ramo: string = h === 'nao' || h === 'senao' ? h : 'sim'
        let casoIdx: number | undefined
        if (h.startsWith('caso:')) {
          const nome = h.slice('caso:'.length)
          const nd = nodes.find(n => n.id === conn.source)
          const casos = (nd?.data as DecisaoNodeData | undefined)?.condition?.casos
          const idx = (casos ?? []).findIndex(c => c.nome === nome)
          if (idx < 0) return
          ramo = nome
          casoIdx = idx
        }
        setEdges(eds => {
          // Remove qualquer aresta de ramo DESTA decisão para ESTE alvo (exclusividade).
          const kept = eds.filter(e =>
            !(isBranch(e) && e.source === conn.source && e.target === conn.target),
          )
          return [...kept, branchEdge(conn.source!, ramo, conn.target!, casoIdx)]
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
    [edges, nodes, decisaoSet, setEdges, readOnly],
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
      if (readOnly) return
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
      if (tipo === 'sql') {
        // Nó SQL: cria o nó (defaults) e SELECIONA — o painel edita a query.
        const name = nextName('SQL', nameSet())
        const sql = defaultSql()
        const node: Node = {
          id: name,
          type: 'sql',
          position: { x, y },
          selected: true,
          data: { name, sql, label: sqlLabel(sql), isNew: true } as SqlNodeData,
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
    [rf, nameSet, maxOrder, setNodes, gruposById, readOnly],
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
    if (!NAME_RE.test(name)) { toast.error('Nome inválido — use apenas letras, números, _ . - (sem espaço)'); return false }
    if (nameSet().has(name)) { toast.error('Já existe um nó com esse nome.'); return false }
    // Troca id + nome (data) e remapeia arestas.
    setNodes(nds => nds.map(n => n.id === oldName
      ? { ...n, id: name, data: { ...n.data, name } }
      : n))
    setEdges(eds => eds.map(e => {
      let ne = e
      if (e.source === oldName) ne = { ...ne, source: name }
      if (e.target === oldName) ne = { ...ne, target: name }
      // Id recomposto das partes (replace por substring casaria prefixos).
      if (ne !== e) {
        ne = {
          ...ne,
          id: isBranch(ne)
            ? `ramo:${ne.source}:${edgeRamo(ne) ?? 'sim'}:${ne.target}`
            : `dep:${ne.source}->${ne.target}`,
        }
      }
      return ne
    }))
    setSelectedId(prev => (prev === oldName ? name : prev))
    setDirty(true)
    return true
  }

  // ── Rename TRANSACIONAL (nó já salvo): confirmação → API → remap local ─────
  const [renamePedido, setRenamePedido] = useState<{ de: string; para: string } | null>(null)
  const [renameLoading, setRenameLoading] = useState(false)

  // Roteia o commit do NomeField: nó novo renomeia só localmente; nó salvo abre
  // a confirmação do rename transacional (backend atualiza TODAS as referências).
  function renomear(oldName: string, novo: string): boolean {
    const n = nodes.find(x => x.id === oldName)
    if ((n?.data as { isNew?: boolean } | undefined)?.isNew) return renomearNovo(oldName, novo)
    const name = novo.trim()
    if (name === oldName) return true
    if (!name) { toast.error('Informe um nome.'); return false }
    if (!NAME_RE.test(name)) { toast.error('Nome inválido — use apenas letras, números, _ . - (sem espaço)'); return false }
    if (nameSet().has(name)) { toast.error('Já existe um nó com esse nome.'); return false }
    if (deletedRef.current.has(name)) {
      toast.error(`"${name}" pertence a um job excluído ainda não salvo — salve o fluxo antes de reusar o nome.`)
      return false
    }
    setRenamePedido({ de: oldName, para: name })
    return false   // o input volta ao nome atual até o usuário confirmar
  }

  // Espelha o rename no estado local: id do nó, arestas e as condições de
  // OUTRAS decisões que citam o nome (source_job/job_name — os ramos são
  // derivados das arestas no save, então o remap das arestas já os cobre).
  function aplicarRenameLocal(oldName: string, name: string) {
    setNodes(nds => nds.map(n => {
      if (n.id === oldName) return { ...n, id: name, data: { ...n.data, name } }
      if (n.type !== 'decisao') return n
      const cond = (n.data as DecisaoNodeData).condition
      if (!cond || (cond.source_job !== oldName && cond.job_name !== oldName)) return n
      const next = {
        ...cond,
        source_job: cond.source_job === oldName ? name : cond.source_job,
        job_name: cond.job_name === oldName ? name : cond.job_name,
      }
      return { ...n, data: { ...n.data, condition: next, label: conditionLabel(next) } }
    }))
    setEdges(eds => eds.map(e => {
      let ne = e
      if (e.source === oldName) ne = { ...ne, source: name }
      if (e.target === oldName) ne = { ...ne, target: name }
      // Id recomposto das partes (replace por substring casaria prefixos: o
      // "JOB" de "JOB_2" — id dessincronizado e risco de key duplicada).
      if (ne !== e) {
        ne = {
          ...ne,
          id: isBranch(ne)
            ? `ramo:${ne.source}:${edgeRamo(ne) ?? 'sim'}:${ne.target}`
            : `dep:${ne.source}->${ne.target}`,
        }
      }
      return ne
    }))
    existingRef.current.delete(oldName)
    existingRef.current.add(name)
    // Mantém o snapshot da API coerente (reorganizar usa a ordem salva por nome).
    apiNodesRef.current = apiNodesRef.current.map(n =>
      n.job_name === oldName ? { ...n, job_name: name } : n)
    setSelectedId(prev => (prev === oldName ? name : prev))
  }

  // Reescreve as referências ao nome dentro do CACHE do TanStack (['fluxo']):
  // sem isso o cache diverge do servidor após o rename e o próximo refetch
  // (foco/staleTime) reconstruiria o canvas com dados velhos.
  function renomearNoCache(de: string, para: string) {
    qc.setQueryData<FluxoResp>(['fluxo', pipeline], old => {
      if (!old) return old
      return {
        nodes: old.nodes.map(n => {
          let cond = n.condition
          if (cond) {
            cond = JSON.parse(JSON.stringify(cond)) as Condition
            for (const k of ['ramo_verdadeiro', 'ramo_falso', 'ramo_senao'] as const) {
              const lista = cond[k]
              if (Array.isArray(lista)) cond[k] = lista.map(m => (m === de ? para : m))
            }
            if (Array.isArray(cond.casos)) {
              cond.casos = cond.casos.map(cs => ({
                ...cs, ramo: (cs.ramo ?? []).map(m => (m === de ? para : m)),
              }))
            }
            if (cond.source_job === de) cond.source_job = para
            if (cond.job_name === de) cond.job_name = para
          }
          return {
            ...n,
            job_name: n.job_name === de ? para : n.job_name,
            depends_on_jobs: (n.depends_on_jobs ?? []).map(m => (m === de ? para : m)),
            condition: cond,
          }
        }),
      }
    })
  }

  async function confirmarRename() {
    if (!renamePedido) return
    if (saving) { toast.error('Aguarde o salvamento em andamento terminar.'); return }
    setRenameLoading(true)
    try {
      const res = await apiFetch<{ avisos?: string[] }>(
        `/pipelines/jobs/${encodeURIComponent(pipeline)}/${encodeURIComponent(renamePedido.de)}/rename`,
        { method: 'POST', body: JSON.stringify({ novo_nome: renamePedido.para }) },
      )
      renomearNoCache(renamePedido.de, renamePedido.para)
      aplicarRenameLocal(renamePedido.de, renamePedido.para)
      toast.success(`Job renomeado para ${renamePedido.para}.`)
      for (const aviso of res?.avisos ?? []) toast.info(aviso)
      setRenamePedido(null)
    } catch (e: any) {
      toast.error(e?.message || 'Falha ao renomear o job.')
    } finally {
      setRenameLoading(false)
    }
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

  // ── SWITCH (N-way): operações sobre os casos — mantêm a condição E as
  // arestas em sincronia (o NOME do caso é a chave da aresta; o índice, a cor).
  function getCondDecisao(nodeId: string): NodeCondition | null {
    const n = nodes.find(x => x.id === nodeId && x.type === 'decisao')
    return n ? (((n.data as DecisaoNodeData).condition) ?? defaultCondition()) : null
  }

  // Reconstrói as arestas de caso desta decisão a partir da lista nova (rename,
  // remoção e reordenação mudam chave e/ou cor); arestas 'senao' ficam como estão.
  function sincronizarArestasCasos(nodeId: string, casos: CasoSwitch[], renome?: { de: string; para: string }) {
    setEdges(eds => eds.flatMap(e => {
      if (!(isBranch(e) && e.source === nodeId)) return [e]
      let ramo = edgeRamo(e) ?? ''
      if (ramo === 'senao') return [e]
      if (renome && ramo === renome.de) ramo = renome.para
      const idx = casos.findIndex(c => c.nome === ramo)
      if (idx < 0) return []   // caso removido → a aresta cai junto
      return [branchEdge(nodeId, ramo, e.target, idx)]
    }))
  }

  function alternarModoDecisao(nodeId: string, paraSwitch: boolean) {
    const cur = getCondDecisao(nodeId)
    if (!cur || paraSwitch === Array.isArray(cur.casos)) return
    if (paraSwitch) {
      // Binária → switch: a condição vira o 1º caso; sim → caso_1, não → senão.
      const casos: CasoSwitch[] = [{ nome: 'caso_1', operador: cur.operador || '>', valor: cur.valor ?? '', ramo: [] }]
      setEdges(eds => eds.map(e => {
        if (!(isBranch(e) && e.source === nodeId)) return e
        const ramo = edgeRamo(e)
        if (ramo === 'sim') return branchEdge(nodeId, 'caso_1', e.target, 0)
        if (ramo === 'nao') return branchEdge(nodeId, 'senao', e.target)
        return e
      }))
      patchCondition(nodeId, {
        casos, ramo_senao: [],
        on_error: cur.on_error === 'ramo_falso' ? 'senao' : 'falhar',
      })
      return
    }
    // Switch → binária: só com no máximo 1 caso (senão a conversão perderia ramos).
    const casos = cur.casos ?? []
    if (casos.length > 1) {
      toast.error('Para voltar ao modo binário, deixe no máximo 1 caso.')
      return
    }
    const nome0 = casos[0]?.nome
    setEdges(eds => eds.map(e => {
      if (!(isBranch(e) && e.source === nodeId)) return e
      const ramo = edgeRamo(e)
      if (nome0 && ramo === nome0) return branchEdge(nodeId, 'sim', e.target)
      if (ramo === 'senao') return branchEdge(nodeId, 'nao', e.target)
      return e
    }))
    patchCondition(nodeId, {
      casos: undefined, ramo_senao: undefined,
      operador: casos[0]?.operador || cur.operador || '>',
      valor: casos[0]?.valor ?? cur.valor ?? '',
      on_error: cur.on_error === 'senao' ? 'ramo_falso' : 'falhar',
    })
  }

  function adicionarCaso(nodeId: string) {
    const cur = getCondDecisao(nodeId)
    if (!cur || !Array.isArray(cur.casos)) return
    if (cur.casos.length >= 10) { toast.error('Máximo de 10 casos por decisão.'); return }
    const usados = new Set(cur.casos.map(c => c.nome))
    let seq = cur.casos.length + 1
    while (usados.has(`caso_${seq}`)) seq += 1
    patchCondition(nodeId, {
      casos: [...cur.casos, { nome: `caso_${seq}`, operador: '=', valor: '', ramo: [] }],
    })
  }

  function atualizarCaso(nodeId: string, idx: number, patch: Partial<CasoSwitch>): boolean {
    const cur = getCondDecisao(nodeId)
    if (!cur || !Array.isArray(cur.casos)) return false
    const antigo = cur.casos[idx]
    if (!antigo) return false
    if (patch.nome != null) {
      const nome = patch.nome.trim()
      if (!nome) { toast.error('Informe o nome do caso.'); return false }
      if (nome.length > 40) { toast.error('Nome do caso muito longo (máx. 40).'); return false }
      if (nome.toLowerCase() === 'senao') { toast.error("'senao' é reservado (é o ramo padrão)."); return false }
      // Case-insensitive — mesma regra do backend (evita 422 tardio no save).
      if (cur.casos.some((c, i) => i !== idx && c.nome.toLowerCase() === nome.toLowerCase())) {
        toast.error('Já existe um caso com esse nome.'); return false
      }
      patch = { ...patch, nome }
    }
    const casos = cur.casos.map((c, i) => (i === idx ? { ...c, ...patch } : c))
    patchCondition(nodeId, { casos })
    if (patch.nome != null && patch.nome !== antigo.nome) {
      sincronizarArestasCasos(nodeId, casos, { de: antigo.nome, para: patch.nome })
    }
    return true
  }

  function removerCaso(nodeId: string, idx: number) {
    const cur = getCondDecisao(nodeId)
    if (!cur || !Array.isArray(cur.casos)) return
    if (cur.casos.length <= 1) { toast.error('A decisão switch precisa de ao menos um caso.'); return }
    const casos = cur.casos.filter((_, i) => i !== idx)
    patchCondition(nodeId, { casos })
    sincronizarArestasCasos(nodeId, casos)
  }

  function moverCaso(nodeId: string, idx: number, delta: -1 | 1) {
    const cur = getCondDecisao(nodeId)
    if (!cur || !Array.isArray(cur.casos)) return
    const j = idx + delta
    if (j < 0 || j >= cur.casos.length) return
    const casos = [...cur.casos]
    ;[casos[idx], casos[j]] = [casos[j], casos[idx]]
    patchCondition(nodeId, { casos })
    sincronizarArestasCasos(nodeId, casos)
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

  // Atualiza a config de um nó SQL (merge em data.sql) e o rótulo do nó (banco).
  function patchSql(nodeId: string, patch: Partial<SqlConfig>) {
    setNodes(nds => nds.map(n => {
      if (n.id !== nodeId || n.type !== 'sql') return n
      const cur = (n.data as SqlNodeData).sql ?? defaultSql()
      const next = { ...cur, ...patch }
      return { ...n, data: { ...n.data, sql: next, label: sqlLabel(next) } }
    }))
    setDirty(true)
  }

  // ── Excluir nós (confirmação) — aceita a multi-seleção inteira ─────────────
  function excluirNos(ids: string[]) {
    const alvo = new Set(ids)
    const edgesAvulsas = new Set(delEdgeIds)
    for (const id of ids) {
      if (existingRef.current.has(id)) deletedRef.current.add(id)
    }
    setEdges(eds => eds.filter(e =>
      !alvo.has(e.source) && !alvo.has(e.target) && !edgesAvulsas.has(e.id)))
    setNodes(nds => nds.filter(n => !alvo.has(n.id)))
    setDirty(true)
    setDelNodeIds(null)
    setDelEdgeIds([])
    setSelectedId(prev => (prev && alvo.has(prev) ? null : prev))
  }

  // Intercepta o delete nativo (tecla Delete/Backspace) para confirmar antes de
  // remover nós — TODOS os selecionados, não só o primeiro. Guarda também as
  // arestas avulsas da seleção (não adjacentes aos nós), que o cancelamento do
  // delete nativo deixaria vivas. Deleção só de arestas segue direto.
  const handleBeforeDelete = useCallback(
    async ({ nodes: toDel, edges: toDelEdges }: { nodes: Node[]; edges: Edge[] }) => {
      if (readOnly) return false
      if (toDel.length > 0) {
        const ids = new Set(toDel.map(n => n.id))
        setDelNodeIds(toDel.map(n => n.id))
        setDelEdgeIds(toDelEdges
          .filter(e => !ids.has(e.source) && !ids.has(e.target))
          .map(e => e.id))
        return false   // cancela o delete nativo; nossa confirmação cuida
      }
      return true
    },
    [readOnly],
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

  // ── Destaque animado do caminho de uma decisão (botão "Simular") ──────────
  // Marca as arestas de ramo (decisaoId + ramo) como `animated` com um traço
  // verde grosso por ~5s e reverte ao estilo original. NÃO altera dados nem
  // marca `dirty` (highlight puramente visual). Guarda o timer p/ limpar.
  const simTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const simularDecisao = useCallback((decisaoId: string, ramo: string) => {
    // Estilo original de uma aresta de ramo (recomposto na reversão, sem rebuild):
    // caso do switch usa a cor do índice; sim verde; não/senão slate.
    const estiloRamo = (e: Edge) => {
      const d = e.data as { ramo?: string; casoIdx?: number } | undefined
      if (d?.casoIdx != null) return { stroke: casoCor(d.casoIdx) }
      return d?.ramo === 'sim' ? SIM_STYLE : NAO_STYLE
    }
    const isAlvo = (e: Edge) => isBranch(e) && e.source === decisaoId && edgeRamo(e) === ramo

    if (simTimerRef.current) { clearTimeout(simTimerRef.current); simTimerRef.current = null }

    setEdges(eds => eds.map(e =>
      isAlvo(e)
        ? { ...e, animated: true, style: { stroke: '#22c55e', strokeWidth: 3 } }
        : e,
    ))

    simTimerRef.current = setTimeout(() => {
      setEdges(eds => eds.map(e =>
        isAlvo(e) ? { ...e, animated: false, style: estiloRamo(e) } : e,
      ))
      simTimerRef.current = null
    }, 5000)
  }, [setEdges])

  // Limpa o timer do highlight ao desmontar (evita setEdges após unmount).
  useEffect(() => () => { if (simTimerRef.current) clearTimeout(simTimerRef.current) }, [])

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
      // ramos por decisão a partir das arestas de ramo — chave é o nome da
      // saída: 'sim'/'nao' (binária), 'senao' ou o nome do caso (switch).
      const ramosByDecisao = new Map<string, Map<string, string[]>>()
      for (const e of edges) {
        if (isBranch(e)) {
          const ramo = edgeRamo(e) ?? 'sim'
          if (!ramosByDecisao.has(e.source)) ramosByDecisao.set(e.source, new Map())
          const porRamo = ramosByDecisao.get(e.source)!
          porRamo.set(ramo, [...(porRamo.get(ramo) ?? []), e.target])
          continue
        }
        if (decisoes.has(e.source)) continue
        if (!depsByTarget.has(e.target)) depsByTarget.set(e.target, new Set())
        depsByTarget.get(e.target)!.add(e.source)
      }

      // Guard: decisão sem NENHUM membro de ramo (o backend rejeitaria o fluxo
      // inteiro com 422) — mesmo padrão do guard da notificação sem canal.
      const decisaoSemRamo = [...decisoes].filter(id => {
        const porRamo = ramosByDecisao.get(id)
        return !porRamo || [...porRamo.values()].every(lista => lista.length === 0)
      })
      if (decisaoSemRamo.length) {
        toast.error(`Ligue ao menos um job em algum ramo da decisão: ${decisaoSemRamo.join(', ')}.`)
        setSaving(false)
        return
      }

      // Guard: campos por tipo das ETAPAS (mesma régua do modal da Lista —
      // jobTypeFieldsErrors) — falha ANTES do 422 e nomeia o nó com problema.
      const etapaErros: string[] = []
      for (const n of nodes) {
        if (n.type !== 'etapa') continue
        const d = n.data as Record<string, unknown>
        const errs = jobTypeFieldsErrors({
          job_type: d.type as JobFieldsType,
          job_command: (d.command as string | null) ?? '',
          ssh_conn_id: (d.ssh_conn_id as string | null) ?? '',
          verbose_log: !!d.verbose_log,
          mssql_conn_id: (d.mssql_conn_id as string | null) ?? '',
          mssql_database: (d.mssql_database as string | null) ?? '',
          params: (d.params as JobParam[] | undefined) ?? [],
        })
        etapaErros.push(...errs.map(e => `${n.id}: ${e}`))
      }
      if (etapaErros.length) {
        const shown = etapaErros.slice(0, 4).join(' · ')
        const extra = etapaErros.length > 4 ? ` (+${etapaErros.length - 4})` : ''
        toast.error(`Corrija antes de salvar — ${shown}${extra}`)
        setSaving(false)
        return
      }

      const payloadNodes = nodes.map(n => {
        const d = n.data as Record<string, unknown>
        const isDecisao = n.type === 'decisao'
        const isNotificacao = n.type === 'notificacao'
        const isSql = n.type === 'sql'
        let condition: Record<string, unknown> | null = null
        if (isDecisao) {
          const cur = (d.condition as NodeCondition | undefined) ?? defaultCondition()
          const ramosMap = ramosByDecisao.get(n.id) ?? new Map<string, string[]>()
          const ramos = { sim: ramosMap.get('sim') ?? [], nao: ramosMap.get('nao') ?? [] }
          // on_error explícito em todos os tipos — round-trip do que o painel
          // exibe (o backend valida/carimba de novo no save).
          const onError = cur.on_error === 'ramo_falso' ? 'ramo_falso' : 'falhar'
          if (Array.isArray(cur.casos)) {
            // SWITCH: casos na ordem do painel (ordem = prioridade de avaliação);
            // o ramo de cada caso e o senão vêm das arestas do canvas.
            const fonte = cur.tipo === 'linhas_job'
              ? { job_name: (cur.job_name || '').trim(), child_job: (cur.child_job || '').trim() }
              : cur.tipo === 'valor_sql'
                ? { source_job: (cur.source_job || '').trim(), comparacao: cur.comparacao || 'texto' }
                : {
                    tabela: (cur.tabela || '').trim() || undefined,
                    database: (cur.database || '').trim() || undefined,
                    sql: (cur.sql || '').trim() || undefined,
                    mssql_conn_id: (cur.mssql_conn_id || '').trim() || undefined,
                  }
            condition = {
              tipo: cur.tipo,
              ...fonte,
              casos: cur.casos.map(c => ({
                nome: (c.nome || '').trim(),
                operador: c.operador,
                valor: (c.valor ?? '').toString().trim(),
                ramo: ramosMap.get(c.nome) ?? [],
              })),
              ramo_senao: ramosMap.get('senao') ?? [],
              on_error: cur.on_error === 'senao' ? 'senao' : 'falhar',
            }
          } else if (cur.tipo === 'linhas_job') {
            // Decisão por linhas processadas: usa job a montante (e job filho
            // opcional). Omite os campos de tabela/sql/banco/conexão.
            condition = {
              tipo: cur.tipo,
              operador: cur.operador,
              valor: (cur.valor ?? '').toString().trim(),
              job_name: (cur.job_name || '').trim(),
              child_job: (cur.child_job || '').trim(),
              on_error: onError,
              ramo_verdadeiro: ramos.sim,
              ramo_falso: ramos.nao,
            }
          } else if (cur.tipo === 'valor_sql') {
            // Decisão lê o valor de um nó SQL a montante. Envia source_job +
            // comparacao (texto|data|numero); omite tabela/sql/banco/conexão.
            condition = {
              tipo: cur.tipo,
              source_job: (cur.source_job || '').trim(),
              comparacao: cur.comparacao || 'texto',
              operador: cur.operador,
              valor: (cur.valor ?? '').toString().trim(),
              on_error: onError,
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
              on_error: onError,
              ramo_verdadeiro: ramos.sim,
              ramo_falso: ramos.nao,
            }
          }
        }
        const jobType = isDecisao ? 'decisao'
          : isNotificacao ? 'notificacao'
          : isSql ? 'sql'
          : ((d.type as string) || 'datastage')
        const base = {
          job_name: n.id,
          job_type: jobType,
          job_command: (isDecisao || isNotificacao || isSql) ? null : ((d.command as string | null) ?? null),
          execution_order: (d.order as number) ?? 1,
          depends_on_jobs: Array.from(depsByTarget.get(n.id) ?? []),
          condition,
          layout_x: Math.round(n.position.x),
          layout_y: Math.round(n.position.y),
        }
        if (isDecisao) return base
        if (isSql) {
          // Nó SQL: emite a chave `sql_node` (o backend lê/devolve sql_node); não
          // envia condition nem campos de etapa. A query roda no banco/conexão.
          const cur = (d.sql as SqlConfig | undefined) ?? defaultSql()
          return {
            ...base,
            sql_node: {
              sql: (cur.sql ?? '').toString(),
              mssql_conn_id: cur.mssql_conn_id ?? null,
              database: cur.database ?? null,
              on_error: cur.on_error === 'nulo' ? 'nulo' : 'falhar',
            },
          }
        }
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
      // Marca tudo como persistido JÁ (sem esperar o refetch): se o refetch
      // atrasar/falhar, um nó recém-salvo com isNew=true iria pro caminho de
      // rename local (sem transação) e duplicaria o job no próximo save.
      existingRef.current = new Set(payloadNodes.map(p => p.job_name))
      setNodes(nds => nds.map(n =>
        (n.data as { isNew?: boolean }).isNew ? { ...n, data: { ...n.data, isNew: false } } : n))
      qc.invalidateQueries({ queryKey: ['fluxo', pipeline] })
      setShowPublish(true)
    } catch (e: any) {
      const status: number | undefined = e?.status
      const msg = e?.message ?? ''
      if (status === 400 || /ciclo|cycle/i.test(msg)) {
        toast.error('Ciclo detectado no fluxo — ajuste as dependências.')
      } else if (status === 422) {
        // Erros de validação do backend: detail.errors[] — não trava o canvas,
        // mantém `dirty` para o usuário corrigir. Deixa CLARO que NÃO foi salvo e
        // mostra os erros (loga todos no console p/ diagnóstico).
        const errs = extractValidationErrors(e)
        if (errs.length) {
          console.warn('[fluxo] NÃO foi salvo — erros de validação:', errs)
          const shown = errs.slice(0, 5).join(' · ')
          const extra = errs.length > 5 ? ` (+${errs.length - 5} — veja o console)` : ''
          toast.error(`NÃO salvo (${errs.length} erro${errs.length > 1 ? 's' : ''}): ${shown}${extra}`)
        } else {
          toast.error('NÃO salvo — fluxo inválido. Verifique as decisões/nós.')
        }
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
      if (node.type === 'sql') return '#8b5cf6'
      const t = (node.data as { type?: EtapaType }).type
      return (t && TYPE_META[t]?.hex) || '#94a3b8'
    },
    [],
  )

  // Clique seleciona (e reabre o dock se estiver colapsado — padrão Informatica:
  // selecionar um nó é intenção de editar). Duplo-clique = abrir MAXIMIZADO
  // (modo focado, padrão DataStage/n8n).
  const onNodeClick = useCallback((_: React.MouseEvent, node: Node) => {
    setSelectedId(node.id)
    setDockEstado(e => (e === 'colapsado' ? 'aberto' : e))
  }, [])
  const onNodeDouble = useCallback((_: React.MouseEvent, node: Node) => {
    setSelectedId(node.id)
    setDockEstado('max')
  }, [])

  // Fecha o painel de propriedades (desseleciona o nó) — botão "recolher".
  const closePanel = useCallback(() => {
    setNodes(nds => nds.map(n => (n.selected ? { ...n, selected: false } : n)))
    setSelectedId(null)
  }, [setNodes])

  // Esc fecha o painel (padrão unânime do benchmark: DataStage/n8n/NiFi). Num
  // input, o 1º Esc só tira o foco; com um modal aberto, quem trata é o Modal.
  const temModalAberto = !!(delNodeIds?.length) || !!renamePedido || showPublish
  useEffect(() => {
    if (!selectedId || temModalAberto) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      const t = e.target as HTMLElement | null
      if (t && /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName)) {
        (t as HTMLInputElement).blur()
        return
      }
      closePanel()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [selectedId, temModalAberto, closePanel])

  // Ramos da decisão SELECIONADA (derivados das arestas de ramo) — read-only no
  // painel. Chave = nome da saída: 'sim'/'nao' (binária), 'senao' ou nome do caso.
  const selRamos = useMemo(() => {
    const porRamo: Record<string, string[]> = {}
    if (!selectedId) return porRamo
    for (const e of edges) {
      if (!isBranch(e) || e.source !== selectedId) continue
      const r = edgeRamo(e) ?? 'sim'
      if (!porRamo[r]) porRamo[r] = []
      porRamo[r].push(e.target)
    }
    return porRamo
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
    <div className="flex h-full w-full flex-col overflow-hidden rounded-xl border border-edge bg-canvas">
      {/* Canvas com a LARGURA TOTAL (fase 3: as propriedades moram no dock
          inferior — o canvas não é mais espremido lateralmente) */}
      <div className="relative min-h-0 min-w-0 flex-1" ref={wrapperRef}>
        {nodes.length === 0 && (
          <div className="pointer-events-none absolute inset-0 z-10 flex flex-col items-center justify-center gap-1 text-dim">
            <span className="text-3xl">⬡</span>
            <p className="text-sm font-medium">Nenhuma etapa neste pipeline</p>
            {!readOnly && (
              <p className="text-xs">Arraste um tipo da paleta (à esquerda) para criar a primeira etapa.</p>
            )}
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
          onNodeDoubleClick={onNodeDouble}
          onDrop={onDrop}
          onDragOver={onDragOver}
          colorMode={colorMode}
          fitView
          fitViewOptions={{ padding: 0.25 }}
          proOptions={{ hideAttribution: true }}
          defaultEdgeOptions={{ type: 'smoothstep' }}
          nodesDraggable={!readOnly}
          nodesConnectable={!readOnly}
          edgesFocusable={!readOnly}
          deleteKeyCode={readOnly ? null : ['Delete', 'Backspace']}
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
          {!readOnly && (
            <Panel position="top-left">
              <Paleta open={paletaOpen} onToggle={() => setPaletaOpen(o => !o)} />
            </Panel>
          )}

          {/* Barra de ações (topo direita) — no modo leitura vira só um selo */}
          <Panel position="top-right">
            {readOnly ? (
              <span className="flex items-center gap-1.5 rounded-lg border border-edge bg-panel/95 px-2.5 py-1.5 text-[11px] font-semibold text-dim shadow-md backdrop-blur">
                <MousePointerClick size={12} /> somente leitura
              </span>
            ) : (
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
            )}
          </Panel>
        </ReactFlow>
      </div>

      {/* Dock inferior de propriedades (fase 3) — 3 estados: colapsado (36px
          com o resumo do nó), aberto (altura arrastável) e max (modo focado).
          Sem seleção vira uma barra-guia fina — nunca some (padrão do
          benchmark Informatica/ADF). */}
      <div
        className={[
          'relative flex shrink-0 flex-col border-t border-edge bg-panel',
          selNode && dockEstado === 'max' ? 'h-[70%]' : '',
          selNode && dockEstado === 'aberto' ? 'max-h-[60%]' : '',
        ].join(' ')}
        style={selNode && dockEstado === 'aberto' ? { height: dockAltura } : undefined}
      >
        {selNode && dockEstado === 'aberto' && (
          <div
            onPointerDown={iniciarDragDock}
            title="Arraste para redimensionar"
            className="absolute -top-1 left-0 right-0 z-10 h-2.5 cursor-row-resize"
          />
        )}

        {/* Header do dock: resumo do nó selecionado + controles de estado */}
        <div className="flex h-9 shrink-0 items-center gap-2 border-b border-edge px-3">
          {selNode ? (
            <>
              <span
                className="h-2.5 w-2.5 shrink-0 rounded-full"
                style={{ background: miniMapColor(selNode) }}
              />
              <span className="truncate font-mono text-xs font-semibold text-ink">{selNode.id}</span>
              <span className="shrink-0 text-[11px] text-dim">
                · {selNode.type === 'decisao' ? 'Decisão'
                  : selNode.type === 'notificacao' ? 'Notificação'
                  : selNode.type === 'sql' ? 'Consulta SQL'
                  : (TYPE_META as Record<string, { label: string }>)[
                      String((selNode.data as { type?: string }).type ?? '')
                    ]?.label ?? 'Etapa'}
              </span>
              {!!(selNode.data as { label?: string }).label && (
                <span className="hidden truncate text-[11px] text-dim/80 sm:inline">
                  · {(selNode.data as { label?: string }).label}
                </span>
              )}
              {readOnly && (
                <span className="shrink-0 rounded-full border border-edge px-2 py-0.5 text-[10px] font-semibold text-dim">
                  somente leitura
                </span>
              )}
              <div className="ml-auto flex shrink-0 items-center gap-0.5 text-dim">
                {dockEstado !== 'max' ? (
                  <button
                    onClick={() => setDockEstado('max')}
                    title="Maximizar (modo focado) — duplo-clique no nó também abre assim"
                    className="rounded p-1 hover:bg-edge/40 hover:text-ink"
                  >
                    <Maximize2 size={13} />
                  </button>
                ) : (
                  <button
                    onClick={() => setDockEstado('aberto')}
                    title="Restaurar tamanho"
                    className="rounded p-1 hover:bg-edge/40 hover:text-ink"
                  >
                    <Minimize2 size={13} />
                  </button>
                )}
                {dockEstado === 'colapsado' ? (
                  <button
                    onClick={() => setDockEstado('aberto')}
                    title="Expandir propriedades"
                    className="rounded p-1 hover:bg-edge/40 hover:text-ink"
                  >
                    <ChevronUp size={14} />
                  </button>
                ) : (
                  <button
                    onClick={() => setDockEstado('colapsado')}
                    title="Recolher para a barra (o resumo do nó permanece)"
                    className="rounded p-1 hover:bg-edge/40 hover:text-ink"
                  >
                    <ChevronDown size={14} />
                  </button>
                )}
                <button
                  onClick={closePanel}
                  title="Fechar propriedades (Esc)"
                  className="rounded p-1 hover:bg-edge/40 hover:text-ink"
                >
                  <X size={14} />
                </button>
              </div>
            </>
          ) : (
            <>
              <MousePointerClick size={13} className="shrink-0 text-dim/70" />
              <span className="truncate text-[11px] text-dim">
                Selecione um nó no canvas para editar as propriedades — duplo-clique abre maximizado.
              </span>
              <span className="ml-auto hidden shrink-0 font-mono text-[11px] text-dim/70 md:inline">
                {pipeline}
              </span>
            </>
          )}
        </div>

        {/* Conteúdo do painel (só quando aberto/max) */}
        {selNode && dockEstado !== 'colapsado' && (
          <div className="min-h-0 flex-1 overflow-y-auto">
            <PropriedadesPanel
              node={selNode}
              nodes={nodes}
              ramos={selRamos}
              jobNames={jobNames}
              sqlNodeNames={sqlNodeNames}
              sshConns={sshConns}
              mssqlConns={mssqlConns}
              dbServer={dbServer}
              dbDatabases={dbDatabases}
              grupos={grupos}
              readOnly={readOnly}
              onRename={renomear}
              onPatchData={patchNodeData}
              onPatchCondition={patchCondition}
              onPatchNotify={patchNotify}
              onPatchSql={patchSql}
              onSimular={simularDecisao}
              onDelete={id => setDelNodeIds([id])}
              onAlternarModo={alternarModoDecisao}
              onAddCaso={adicionarCaso}
              onUpdateCaso={atualizarCaso}
              onRemoveCaso={removerCaso}
              onMoveCaso={moverCaso}
            />
          </div>
        )}
      </div>

      {/* Confirmação de exclusão de nó(s) — lista TODOS os selecionados */}
      <Modal
        open={!!delNodeIds?.length}
        onClose={() => { setDelNodeIds(null); setDelEdgeIds([]) }}
        title={delNodeIds && delNodeIds.length > 1 ? `Excluir ${delNodeIds.length} nós` : 'Excluir nó'}
        size="sm"
      >
        <div className="flex flex-col gap-4">
          <p className="text-sm text-dim">
            Remover{' '}
            {(delNodeIds ?? []).map((id, i) => (
              <span key={id}>
                {i > 0 && ', '}
                <span className="font-mono font-medium text-ink">{id}</span>
              </span>
            ))}{' '}
            do fluxo? As dependências e ramos ligados também serão desligados.
            {delEdgeIds.length > 0 && (
              <span> {delEdgeIds.length} conexão(ões) selecionada(s) também serão removidas.</span>
            )}
          </p>
          {(delNodeIds ?? []).some(id => existingRef.current.has(id)) && (
            <p className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-300">
              {delNodeIds && delNodeIds.length > 1
                ? 'Nós que já existem no pipeline serão excluídos ao salvar o fluxo.'
                : 'Este nó já existe no pipeline — será excluído ao salvar o fluxo.'}
            </p>
          )}
          <div className="flex justify-end gap-2 border-t border-edge pt-3">
            <Button variant="secondary" onClick={() => { setDelNodeIds(null); setDelEdgeIds([]) }}>Cancelar</Button>
            <Button variant="danger" onClick={() => delNodeIds?.length && excluirNos(delNodeIds)}>
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

      {/* Modal: confirmação do rename TRANSACIONAL de um nó já salvo */}
      <Modal
        open={!!renamePedido}
        onClose={() => setRenamePedido(null)}
        title="Renomear job"
        size="sm"
      >
        <div className="flex flex-col gap-4">
          <p className="text-sm text-dim">
            Renomear{' '}
            <span className="font-mono font-medium text-ink">{renamePedido?.de}</span>
            {' '}para{' '}
            <span className="font-mono font-medium text-ink">{renamePedido?.para}</span>?
          </p>
          <p className="rounded-lg border border-blue-200 bg-blue-50 px-3 py-2 text-xs text-blue-800 dark:border-blue-800/40 dark:bg-blue-900/15 dark:text-blue-300">
            O rename é transacional: dependências, condições (ramos/decisões),
            lineage e o histórico de execuções são atualizados juntos.
          </p>
          <p className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-300">
            Depois, <b>republique a DAG</b> — o task_id no Airflow deriva do nome
            (rerun e reconciliação usam o task_id). Pipelines com execução em
            andamento não podem ser renomeados.
          </p>
          <div className="flex justify-end gap-2 border-t border-edge pt-3">
            <Button variant="secondary" onClick={() => setRenamePedido(null)}>
              Cancelar
            </Button>
            <Button onClick={confirmarRename} loading={renameLoading}>
              Renomear
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
