// MalhaEditor — diagrama de montagem da malha (F8 da spec de dependências, §4b).
// Irmão do FluxoEditor (React Flow), NÃO parametrização dele: aqui o nó é um
// PIPELINE membro da malha e a aresta é uma DEPENDÊNCIA REAL e GLOBAL da
// etl_pipeline_dependencia (migration 067) — desenhar a aresta É cadastrar a
// dependência (POST /dependencias), e excluí-la apaga a dependência de verdade
// em TODAS as malhas (daí a confirmação explícita). O layout dos nós persiste
// por malha em etl_malha_pipeline (PUT /malhas/{name}/layout) — botão "Salvar
// posições" habilita só quando alguma posição mudou (salvar sem mudança é no-op).
// F9: toggle Montagem | Execução. No modo Execução a malha abre numa DATA DE
// REFERÊNCIA (default = ODATE corrente calculado no servidor pela virada
// global), colore os nós pelo status de etl_pipeline_execucao (polling 30s),
// lista os eventos da guardiã (etl_dependencia_evento) e TRAVA a edição —
// reusa o mesmo mecanismo do readOnly da F8. Em produção, antes da retomada
// F2–F4, nada alimenta essas tabelas: a visão mostra o estado vazio HONESTO.
// Orientação (migration 074): o diagrama desenha horizontal (esquerda →
// direita, default) ou vertical (cima → baixo) POR MALHA — a preferência
// persiste no servidor junto do layout (PATCH /malhas/{name}) e trocar
// reorganiza as posições na direção nova; a visão de Execução herda a mesma
// orientação (é o mesmo grafo) e a consulta vê a salva sem poder trocar.
// F12 (docs/malha-componentes-desenho.md §10): os QUATRO componentes de malha
// no canvas — Início, Aguarde, Notificação e Fim (etl_malha_no, migration 075),
// misturados aos nós-pipeline. A paleta arrasta-para-criar (POST /nos); as
// arestas de NÓ são gestos com efeito de COMPILAÇÃO (F11): todo gesto composto
// roda dry_run ANTES do write e o modal de confirmação mostra o efeito
// (criar/remover/transferir/republicar/manuais) — erros[] (ciclo) BLOQUEIAM
// com o texto literal do servidor, e o espelho client-side (criaCiclo sobre o
// preview_expandido do dry_run) cobre o vão, sem nunca ser a autoridade
// (Decisão 15). Aresta compilada por nó de OUTRA malha chega anotada
// (compilada_por) e desenha com CADEADO, somente leitura aqui — a recusa usa
// a mesma mensagem do 422 (Decisão 4). Avisos de desenho (§2.2): banner
// persistente alimentado pelo GET + toast no gesto que os cria.
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
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
  type Node,
  type Edge,
  type Connection,
  type NodeChange,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { apiFetch } from '../../lib/api'
import { Button } from '../ui/Button'
import { Modal } from '../ui/Modal'
import { toast } from '../ui/Toast'
import { Autocomplete } from '../ui/Autocomplete'
import { PageSpinner } from '../ui/Spinner'
import {
  Activity, AlertCircle, AlertTriangle, Anchor, ArrowRightLeft, ArrowUpDown,
  ChevronLeft, ChevronRight, Info, Link2, Lock, Minus,
  MousePointerClick, Plus, RefreshCw, Save, ShieldAlert, Trash2, Wrench,
} from 'lucide-react'
import { useColorMode } from '../etapas/useColorMode'
import { liveLayout, criaCiclo, type Orientacao } from '../etapas/layoutGrafo'
import { MalhaPipelineNode, type MalhaPipelineNodeData } from './MalhaPipelineNode'
import {
  InicioNode, AguardeNode, NotificacaoNode, FimNode,
  type MalhaComponenteNodeData,
} from './MalhaComponenteNodes'
import { COMPONENTE_META, type TipoComponente } from './componenteMeta'
import {
  STATUS_EXECUCAO, ORDEM_LEGENDA, estiloEvento,
  type ExecucaoPipeline, type MalhaExecucaoApi,
} from './statusExecucao'
// Mensagens de recusa ESPELHADAS do servidor — módulo compartilhado com o
// DependenciasModal da F5: cliente e servidor com o MESMO texto, num lugar só.
import { msgCiclo, MSG_SELF, msgRepublicar, msgLinhaAssinada } from './mensagensDependencia'

// Nó-pipeline (F8) + os quatro componentes (F12). GOTCHA React Flow: aresta
// cujo source/target não casa com id de nó é DESCARTADA em silêncio — todos os
// ids (pipelines E componentes) entram no MESMO setNodes, antes das edges.
const nodeTypes = {
  malhaPipeline: MalhaPipelineNode,
  malhaInicio: InicioNode,
  malhaAguarde: AguardeNode,
  malhaNotificacao: NotificacaoNode,
  malhaFim: FimNode,
}

// ── Tipos do payload da API (/malhas/{name}) ────────────────────────────────
interface MalhaMembroApi {
  pipeline_name: string
  active: 0 | 1 | boolean
  criticidade: string | null
  schedule_type: string | null
  layout_x: number | null
  layout_y: number | null
}
// Proveniência de linha compilada (F11): o nó Aguarde dono e a malha dele.
interface CompiladaPor {
  malha: string | null
  no: number
}
interface MalhaArestaApi {
  pipeline_name: string   // o dependente (destino da seta)
  depende_de: string      // o predecessor (origem da seta)
  // F11 (§7.4): linha COMPILADA por nó de OUTRA malha — desenha com cadeado,
  // somente leitura aqui (a exclusão é 422 nomeando a dona).
  compilada_por?: CompiladaPor
}
// Nó especial do desenho (F10 — etl_malha_no).
interface MalhaNoApi {
  id: number
  tipo: string
  config: Record<string, unknown> | null
  layout_x: number | null
  layout_y: number | null
  // Upstream expandido pelo SERVIDOR (§3.2) — o front nunca expande.
  upstream: string[]
}
// Aresta de nó do desenho (F10 — etl_malha_aresta).
interface MalhaArestaNoApi {
  id: number
  origem_no: number | null
  origem_pipeline: string | null
  destino_no: number | null
  destino_pipeline: string | null
}
// Aviso de desenho (§2.2): {no, nivel 'forte'|'leve', mensagem}. no=null =
// aviso do compilador, sem nó específico.
interface AvisoDesenho {
  no: number | null
  nivel: string
  mensagem: string
}
interface MalhaDetalheApi {
  malha_name: string
  descricao: string | null
  ativo: 0 | 1 | boolean
  // Orientação do diagrama (migration 074) — preferência POR MALHA que viaja
  // com o layout persistido. Chave ausente (API/banco antigos) = horizontal.
  orientacao?: string
  membros: MalhaMembroApi[]
  // Contrato da F8: dependências (tipo PIPELINE) onde AMBAS as pontas são
  // membros da malha.
  arestas?: MalhaArestaApi[]
  // F10: nós especiais e arestas de nó do desenho + avisos §2.2. Chave ausente
  // (API anterior) degrada como a migration_075_pendente.
  nos?: MalhaNoApi[]
  arestas_no?: MalhaArestaNoApi[]
  avisos?: AvisoDesenho[]
  // Deploy parcial (migration 067 ausente): a API devolve "arestas": [] e liga
  // esta flag — o editor avisa e desliga a criação de arestas. Chave `arestas`
  // AUSENTE (API anterior à F8) degrada do mesmo jeito.
  migration_067_pendente?: boolean
  // Deploy parcial (migration 075 ausente): nós/arestas de nó vazios + flag —
  // o resto da malha segue intacto e a paleta de componentes desliga.
  migration_075_pendente?: boolean
}

// ── Contrato do gesto (dry_run — desenho §7.2) ──────────────────────────────
interface EfeitoDep { dependente: string; predecessor: string }
interface EfeitoGesto {
  dependencias_criar: EfeitoDep[]
  dependencias_remover: EfeitoDep[]
  dependencias_transferir: (EfeitoDep & { para_malha: string; para_no: number })[]
  ja_existentes_manuais: EfeitoDep[]
  agendamentos: { pipeline: string; de: string; para: string }[]
  republicar: string[]
}
interface GestoResposta {
  efeito: EfeitoGesto
  avisos: AvisoDesenho[]
  erros: string[]
  // Conjunto PÓS-gesto {pipeline_name, depende_de} — é sobre ele que o espelho
  // client-side do ciclo (criaCiclo) roda (§3.3).
  preview_expandido?: { pipeline_name: string; depende_de: string }[]
}
interface GestoWriteResposta {
  ok: boolean
  ja_existia?: boolean
  arestas_removidas?: number
  avisos: AvisoDesenho[]
  efeito: EfeitoGesto
}

// Ponta de aresta de nó no contrato §9: {no: id} XOR {pipeline: nome}.
type PontaGesto = { no: number } | { pipeline: string }

// Gesto aguardando confirmação no modal (alimentado pelo dry_run).
interface GestoPendente {
  acao: 'criar-aresta' | 'remover-aresta' | 'remover-no'
  rotulo: string          // ex.: "DEV_F10_B → Aguarde #8"
  origem?: PontaGesto
  destino?: PontaGesto
  arestaId?: number
  noId?: number
  resposta: GestoResposta
  // Ciclo do ESPELHO client-side quando o servidor não devolveu erro —
  // defensivo; o texto é o mesmo (msgCiclo).
  cicloLocal?: string | null
}

// ── Helpers da visão de execução (F9) ───────────────────────────────────────
// Soma dias a um 'YYYY-MM-DD' em UTC puro — sem passar por fuso local (Date
// com string ISO curta interpreta UTC; misturar com métodos locais deslocaria
// o dia em fusos negativos como o de Brasília).
function somaDia(iso: string, delta: number): string {
  const [a, m, d] = iso.split('-').map(Number)
  return new Date(Date.UTC(a, m - 1, d + delta)).toISOString().slice(0, 10)
}

function horaCurta(iso: string | null): string | null {
  if (!iso) return null
  const d = new Date(iso)
  return isNaN(d.getTime())
    ? iso
    : d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })
}

// Tooltip do nó com o resumo da execução (o card em si não muda — F9).
// F5 (D32): corrida aguardando anexa "aguardando: P1, P2" — os faltantes vêm
// do MESMO predicado do motor (port em api/services/dependencias.py).
function tituloExecucao(e: ExecucaoPipeline): string {
  const partes = [e.status]
  const ini = horaCurta(e.inicio)
  const fim = horaCurta(e.fim)
  if (ini) partes.push(`início ${ini}`)
  if (fim) partes.push(`fim ${fim}`)
  if (e.disparado_por) partes.push(`disparado por ${e.disparado_por}`)
  let linha = partes.join(' · ')
  if (e.faltantes && e.faltantes.length > 0) {
    linha += `\naguardando: ${e.faltantes.join(', ')}`
  }
  return e.motivo ? `${linha}\n${e.motivo}` : linha
}

// ── Construção de nós/arestas ───────────────────────────────────────────────
const EDGE_ARROW = { type: MarkerType.ArrowClosed, width: 16, height: 16 }

// Id do componente no canvas: "no:{id}" — o MESMO contrato do PUT /layout
// (§9); o prefixo não colide com pipeline real (':' não é dag_id válido).
const NO_PREFIX = 'no:'
const ehNo = (rfId: string) => rfId.startsWith(NO_PREFIX)
const noRfId = (id: number) => `${NO_PREFIX}${id}`
function pontaDoCanvas(rfId: string): PontaGesto {
  return ehNo(rfId)
    ? { no: Number(rfId.slice(NO_PREFIX.length)) }
    : { pipeline: rfId }
}

// Aresta de dependência: depende_de → pipeline_name, sem rótulo (o sentido da
// seta já diz tudo — Control-M também não rotula). Linha compilada por nó de
// OUTRA malha (compilada_por, §7.4) ganha o CADEADO: tracejada + Lock no meio,
// somente leitura aqui — quem manda é o desenho da malha dona.
function depEdge(a: MalhaArestaApi): Edge {
  const e: Edge = {
    id: `dep:${a.depende_de}->${a.pipeline_name}`,
    source: a.depende_de,
    target: a.pipeline_name,
    type: 'smoothstep',
    markerEnd: EDGE_ARROW,
  }
  if (a.compilada_por) {
    e.data = { compiladaPor: a.compilada_por }
    e.style = { strokeDasharray: '6 3' }
    e.label = (
      <span
        title={`Compilada pelo Aguarde #${a.compilada_por.no} da malha `
          + `'${a.compilada_por.malha}' — somente leitura aqui; edite pelo `
          + 'desenho da malha dona.'}
        className="inline-flex items-center justify-center rounded-full border border-edge bg-panel p-0.5 text-dim"
      >
        <Lock size={10} />
      </span>
    )
  }
  return e
}

// Aresta de NÓ do desenho (F10): id "ano:{id}" — a exclusão dela é gesto com
// dry_run, nunca o DELETE /dependencias do F8.
const ANO_PREFIX = 'ano:'
function noEdge(a: MalhaArestaNoApi): Edge | null {
  const source = a.origem_pipeline
    ?? (a.origem_no != null ? noRfId(a.origem_no) : null)
  const target = a.destino_pipeline
    ?? (a.destino_no != null ? noRfId(a.destino_no) : null)
  if (!source || !target) return null   // impossível pelo CHECK da 075; defensivo
  return {
    id: `${ANO_PREFIX}${a.id}`,
    source,
    target,
    type: 'smoothstep',
    markerEnd: EDGE_ARROW,
  }
}

function nodeData(m: MalhaMembroApi): MalhaPipelineNodeData {
  return {
    name: m.pipeline_name,
    active: !!m.active,
    criticidade: m.criticidade,
    // 'on_demand' é jargão do banco — o operador lê "sob demanda" (mesma
    // tradução do card da tela Malha).
    schedule: m.schedule_type === 'on_demand' ? 'sob demanda' : m.schedule_type,
  }
}

// Cor do nó no minimapa: azul da casa p/ pipeline ativo, slate p/ inativo e a
// cor de identidade p/ cada componente (mesma do chip da paleta).
function miniMapColor(n: Node): string {
  const d = n.data as (Partial<MalhaComponenteNodeData> & Partial<MalhaPipelineNodeData>) | undefined
  const tipo = d?.tipo as TipoComponente | undefined
  if (tipo && COMPONENTE_META[tipo]) return COMPONENTE_META[tipo].cor
  return d?.active ? '#1A5FA8' : '#94a3b8'
}

// ── Paleta de componentes (F12) ─────────────────────────────────────────────
// Arrastar-para-criar, no padrão da paleta das Etapas (mesmo MIME próprio).
const DND_MIME_NO = 'application/orquestra-malha-componente'
const COMPONENTES_ORDEM: TipoComponente[] = ['inicio', 'aguarde', 'notificacao', 'fim']

function ItemPaletaComponente({ tipo, desabilitado, motivo }: {
  tipo: TipoComponente
  desabilitado: boolean
  motivo?: string
}) {
  const meta = COMPONENTE_META[tipo]
  const onDragStart = (e: React.DragEvent) => {
    if (desabilitado) { e.preventDefault(); return }
    e.dataTransfer.setData(DND_MIME_NO, tipo)
    e.dataTransfer.effectAllowed = 'move'
  }
  return (
    <div
      draggable={!desabilitado}
      onDragStart={onDragStart}
      title={desabilitado ? motivo : `Arrastar para o canvas — ${meta.rotulo}`}
      className={[
        'group flex items-center gap-2 rounded-md border border-edge bg-canvas px-2 py-1.5 text-ink transition-colors',
        desabilitado
          ? 'cursor-not-allowed opacity-50'
          : 'cursor-grab hover:border-blue-300 hover:bg-edge/40 active:cursor-grabbing dark:hover:border-blue-800',
      ].join(' ')}
    >
      <span className={`flex h-7 w-7 shrink-0 items-center justify-center rounded ${meta.chip}`}>
        <meta.Icon size={16} strokeWidth={2.2} />
      </span>
      <span className="min-w-0 flex-1 truncate text-[11px] font-medium leading-none text-ink">
        {meta.rotulo}
      </span>
    </div>
  )
}

interface Props {
  malha: string
  readOnly?: boolean
}

// Wrapper com o provider (necessário p/ useReactFlow/fitView).
export function MalhaEditor(props: Props) {
  return (
    <ReactFlowProvider>
      <MalhaEditorInner {...props} />
    </ReactFlowProvider>
  )
}

function MalhaEditorInner({ malha, readOnly = false }: Props) {
  const colorMode = useColorMode()
  const rf = useReactFlow()
  const qc = useQueryClient()

  const [nodes, setNodes] = useNodesState<Node>([])
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([])
  // Arestas aguardando a confirmação de exclusão (Delete ou botão).
  const [delEdges, setDelEdges] = useState<Edge[] | null>(null)
  const [excluindo, setExcluindo] = useState(false)
  // Gesto de componente aguardando confirmação no modal (dry_run já rodou).
  const [gesto, setGesto] = useState<GestoPendente | null>(null)
  const [gestoCarregando, setGestoCarregando] = useState(false)
  const [aplicandoGesto, setAplicandoGesto] = useState(false)
  const [prendendo, setPrendendo] = useState(false)
  // Busca da paleta (adicionar membro).
  const [busca, setBusca] = useState('')
  // F9: Montagem (default, editável) | Execução (leitura da data de referência).
  const [modo, setModo] = useState<'montagem' | 'execucao'>('montagem')
  // Data de referência pedida. null = sem query — o SERVIDOR devolve o ODATE
  // corrente (virada global de etl_app_config), e é ele que aparece no input.
  const [dataRef, setDataRef] = useState<string | null>(null)
  // Orientação: o servidor é a fonte (viaja com o layout — todos veem o mesmo
  // desenho); o override local dá resposta imediata ao toggle enquanto o PATCH
  // viaja. Carrega a malha DONA junto: trocar de malha invalida o override
  // sozinho, sem efeito de reset (lint react-hooks/set-state-in-effect).
  const [orientacaoLocal, setOrientacaoLocal] =
    useState<{ malha: string; valor: Orientacao } | null>(null)

  const { data, isLoading, isError, error } = useQuery<MalhaDetalheApi>({
    queryKey: ['malha', malha],
    queryFn: () => apiFetch(`/malhas/${encodeURIComponent(malha)}`),
    enabled: !!malha,
  })
  // Normalização defensiva: qualquer coisa que não seja 'vertical' (chave
  // ausente, payload antigo) é horizontal — o comportamento de sempre.
  const orientacaoServidor: Orientacao =
    data?.orientacao === 'vertical' ? 'vertical' : 'horizontal'
  const orientacao: Orientacao = (orientacaoLocal && orientacaoLocal.malha === malha)
    ? orientacaoLocal.valor
    : orientacaoServidor

  // ── Visão de execução (F9): status + eventos da data de referência ────────
  const emExecucao = modo === 'execucao'
  const execQuery = useQuery<MalhaExecucaoApi>({
    queryKey: ['malha-execucao', malha, dataRef],
    queryFn: () => apiFetch(
      `/malhas/${encodeURIComponent(malha)}/execucao` +
      (dataRef ? `?data_referencia=${encodeURIComponent(dataRef)}` : '')),
    enabled: !!malha && emExecucao,
    refetchInterval: 30_000,   // leitura de painel: acompanha o dia rodando
  })
  const execData = execQuery.data
  // A data exibida/navegada: a pedida ou a que o servidor calculou (ODATE).
  const dataExibida = dataRef ?? execData?.data_referencia ?? ''
  // Execução MAIS RECENTE por pipeline (o endpoint já entrega uma por membro —
  // regra do §6 risco 6 da spec).
  const execPorPipeline = useMemo(() => {
    const map = new Map<string, ExecucaoPipeline>()
    for (const e of execData?.execucoes ?? []) map.set(e.pipeline_name, e)
    return map
  }, [execData])
  const eventos = useMemo(
    () => [...(execData?.eventos ?? [])]
      .sort((a, b) => b.criado_em.localeCompare(a.criado_em)),
    [execData])
  // Edição travada na visão de execução — MESMO mecanismo do readOnly da F8.
  const travado = readOnly || emExecucao

  // Deploy parcial: migration 067 ausente (flag da API) ou API anterior à F8
  // (sem a chave `arestas`) — o diagrama abre só com os nós e avisa (nunca um
  // 500 na cara), e a criação de dependências fica desligada.
  const depsIndisponiveis = !!data
    && (data.migration_067_pendente === true || !Array.isArray(data.arestas))
  // Idem para a 075 (F12): sem ela não há componentes — a paleta desliga e o
  // aviso explica; o resto do diagrama segue como na F8.
  const nosIndisponiveis = !!data
    && (data.migration_075_pendente === true || !Array.isArray(data.nos))

  // Mapa id do nó → tipo (rótulos de gesto/aviso) e avisos persistentes §2.2.
  const tipoDoNo = useMemo(() => {
    const m = new Map<number, string>()
    for (const n of data?.nos ?? []) m.set(n.id, n.tipo)
    return m
  }, [data])
  const avisosDesenho = useMemo<AvisoDesenho[]>(
    () => (Array.isArray(data?.avisos) ? data.avisos : []), [data])

  // Rótulo curto de uma ponta/nó para mensagens ("Aguarde #8" / nome do pipe).
  const rotuloPontaGesto = useCallback((p: PontaGesto): string => {
    if ('pipeline' in p) return p.pipeline
    const t = tipoDoNo.get(p.no) as TipoComponente | undefined
    return `${t && COMPONENTE_META[t] ? COMPONENTE_META[t].rotulo : 'nó'} #${p.no}`
  }, [tipoDoNo])

  // Espelho dos estados p/ callbacks estáveis (padrão do FluxoEditor).
  const nodesRef = useRef<Node[]>([])
  useEffect(() => { nodesRef.current = nodes }, [nodes])
  const edgesRef = useRef<Edge[]>([])
  useEffect(() => { edgesRef.current = edges }, [edges])

  // ── Grafo derivado da API (puro) ──────────────────────────────────────────
  // Arestas prontas + BASELINE de posições: o que o SERVIDOR conhece de cada
  // nó (layout salvo em etl_malha_pipeline/etl_malha_no, senão o auto-layout
  // topológico do liveLayout — colunas = ondas do grafo, componentes
  // incluídos). É contra este baseline que o "Salvar posições" decide.
  const grafo = useMemo(() => {
    if (!data) return null
    const membros = data.membros ?? []
    const arestas = Array.isArray(data.arestas) ? data.arestas : []
    // Nó com tipo fora do domínio (SQL direto) é ignorado — as arestas dele
    // cairiam do desenho junto (degradação, nunca tela quebrada).
    const nos = (Array.isArray(data.nos) ? data.nos : [])
      .filter(n => n.tipo in COMPONENTE_META)
    const arestasNo = Array.isArray(data.arestas_no) ? data.arestas_no : []
    const novasEdges = [
      ...arestas.map(depEdge),
      ...arestasNo.map(noEdge).filter((e): e is Edge => e !== null),
    ]
    // Contagens de arestas de nó — o subtítulo honesto dos cards.
    const entradasNo = new Map<number, number>()
    const saidasNo = new Map<number, number>()
    for (const a of arestasNo) {
      if (a.destino_no != null) {
        entradasNo.set(a.destino_no, (entradasNo.get(a.destino_no) ?? 0) + 1)
      }
      if (a.origem_no != null) {
        saidasNo.set(a.origem_no, (saidasNo.get(a.origem_no) ?? 0) + 1)
      }
    }
    // O auto-layout do baseline segue a orientação SALVA (a que o servidor
    // conhece) — o override local ainda-não-persistido não muda o baseline.
    const auto = liveLayout(
      [...membros.map(m => ({ id: m.pipeline_name })),
       ...nos.map(n => ({ id: noRfId(n.id) }))],
      novasEdges, new Map(),
      data.orientacao === 'vertical' ? 'vertical' : 'horizontal')
    const baseline = new Map<string, { x: number; y: number }>()
    for (const m of membros) {
      const salva = (m.layout_x != null && m.layout_y != null)
        ? { x: m.layout_x, y: m.layout_y }
        : null
      const base = salva ?? auto[m.pipeline_name] ?? { x: 0, y: 0 }
      baseline.set(m.pipeline_name, { x: Math.round(base.x), y: Math.round(base.y) })
    }
    for (const n of nos) {
      const salva = (n.layout_x != null && n.layout_y != null)
        ? { x: n.layout_x, y: n.layout_y }
        : null
      const base = salva ?? auto[noRfId(n.id)] ?? { x: 0, y: 0 }
      baseline.set(noRfId(n.id), { x: Math.round(base.x), y: Math.round(base.y) })
    }
    return { membros, nos, novasEdges, baseline, entradasNo, saidasNo }
  }, [data])

  // (Re)constrói nós/arestas a partir do grafo derivado. O rebuild PRESERVA a
  // posição atual de nó que já está no canvas (as arestas são persistidas na
  // hora, então todo refetch é seguro; só a posição é estado local até o
  // "Salvar posições"). Na visão de execução (F9) o mesmo rebuild anexa o
  // status da data como CAMADA no data do nó — membro sem linha em
  // etl_pipeline_execucao fica sem camada (exec: null), nunca com cor inventada.
  // Os COMPONENTES (F12) entram no MESMO array de nós, antes do setEdges —
  // React Flow descarta aresta órfã em silêncio, e aqui nunca há órfã. Na
  // Execução eles ficam neutros (a camada de estado dos nós é a F15).
  // A orientação entra no data de TODOS os nós (rebuild ao trocar): é ela que
  // decide onde os handles ancoram — a visão de Execução herda a mesma, porque
  // o grafo é o mesmo.
  useEffect(() => {
    if (!grafo) return
    const atuais = new Map(nodesRef.current.map(n => [n.id, n.position]))
    setNodes([
      ...grafo.membros.map(m => {
        const exec = emExecucao ? execPorPipeline.get(m.pipeline_name) : undefined
        return {
          id: m.pipeline_name,
          type: 'malhaPipeline' as const,
          position: atuais.get(m.pipeline_name)
            ?? grafo.baseline.get(m.pipeline_name)
            ?? { x: 0, y: 0 },
          data: {
            ...nodeData(m),
            orientacao,
            exec: exec ? { status: exec.status, titulo: tituloExecucao(exec) } : null,
          },
        }
      }),
      ...grafo.nos.map(n => {
        const tipo = n.tipo as TipoComponente
        return {
          id: noRfId(n.id),
          type: COMPONENTE_META[tipo].nodeType,
          position: atuais.get(noRfId(n.id))
            ?? grafo.baseline.get(noRfId(n.id))
            ?? { x: 0, y: 0 },
          data: {
            noId: n.id,
            tipo,
            entradas: grafo.entradasNo.get(n.id) ?? 0,
            saidas: grafo.saidasNo.get(n.id) ?? 0,
            config: n.config,
            orientacao,
          } satisfies MalhaComponenteNodeData,
        }
      }),
    ])
    setEdges(grafo.novasEdges)
  }, [grafo, setNodes, setEdges, emExecucao, execPorPipeline, orientacao])

  // dirty = alguma posição difere do baseline do servidor (arredondado — é o
  // que o PUT envia). Mover um nó e devolvê-lo ao lugar volta a desabilitar o
  // botão: salvar sem mudança é no-op de verdade (aceite da F8). Depois do
  // PUT, o refetch traz o layout recém-salvo e o dirty cai sozinho.
  const dirty = useMemo(() => {
    if (!grafo) return false
    return nodes.some(n => {
      const b = grafo.baseline.get(n.id)
      return !b || Math.round(n.position.x) !== b.x || Math.round(n.position.y) !== b.y
    })
  }, [nodes, grafo])

  // Enquadra o diagrama ao abrir/trocar de malha.
  const fittedRef = useRef<string | null>(null)
  useEffect(() => {
    if (!data || fittedRef.current === malha) return
    fittedRef.current = malha
    const t = setTimeout(() => rf.fitView({ padding: 0.2, duration: 250 }), 90)
    return () => clearTimeout(t)
  }, [data, malha, rf])

  const onNodesChange = useCallback(
    (changes: NodeChange<Node>[]) => {
      setNodes(nds => applyNodeChanges(changes, nds))
    },
    [setNodes],
  )

  // ── Avisos e efeitos nos gestos (F12) ─────────────────────────────────────
  // Toast SÓ dos avisos que o gesto CRIOU (§2.2: "no momento de consequência")
  // — os que já estavam no banner não repetem; o banner persiste todos.
  const mostrarAvisos = useCallback((avisos: AvisoDesenho[] | undefined) => {
    const novos = (avisos ?? []).filter(a =>
      !avisosDesenho.some(b => b.no === a.no && b.mensagem === a.mensagem))
    novos.slice(0, 3).forEach(a => toast.info(a.mensagem))
    if (novos.length > 3) {
      toast.info(`+${novos.length - 3} avisos — veja o banner do desenho.`)
    }
  }, [avisosDesenho])

  // Resumo do efeito aplicado (o modal já mostrou a lista; o toast fecha o
  // laço) + republicação por dependente afetado (Decisão 6/D30).
  const resumoEfeito = useCallback((efeito: EfeitoGesto | undefined) => {
    if (!efeito) return
    const partes: string[] = []
    if (efeito.dependencias_criar.length > 0) {
      partes.push(`${efeito.dependencias_criar.length} criada(s)`)
    }
    if (efeito.dependencias_remover.length > 0) {
      partes.push(`${efeito.dependencias_remover.length} removida(s)`)
    }
    if (efeito.dependencias_transferir.length > 0) {
      partes.push(`${efeito.dependencias_transferir.length} transferida(s)`)
    }
    if (partes.length > 0) toast.info(`Dependências: ${partes.join(' · ')}.`)
    efeito.republicar.slice(0, 3).forEach(nome => toast.info(msgRepublicar(nome)))
    if (efeito.republicar.length > 3) {
      toast.info(`+${efeito.republicar.length - 3} DAGs precisam ser republicadas.`)
    }
  }, [])

  const invalidarPosGesto = useCallback(() => {
    // A compilação é GLOBAL (067): toda malha que contenha as pontas muda —
    // mesma regra do F8; pipelines p/ o badge de publicação pendente.
    qc.invalidateQueries({ queryKey: ['malha'] })
    qc.invalidateQueries({ queryKey: ['pipelines'] })
  }, [qc])

  // ── Gestos de aresta de nó / componente (dry_run → modal → write) ─────────
  const aplicarAresta = useCallback(async (
    origem: PontaGesto, destino: PontaGesto, rotulo: string,
  ) => {
    const r = await apiFetch<GestoWriteResposta>(
      `/malhas/${encodeURIComponent(malha)}/arestas`, {
        method: 'POST',
        body: JSON.stringify({ origem, destino }),
      })
    toast.success(r.ja_existia
      ? 'Essa ligação já existia — o desenho foi reconciliado.'
      : `Ligação criada: ${rotulo}`)
    resumoEfeito(r.efeito)
    mostrarAvisos(r.avisos)
    invalidarPosGesto()
  }, [malha, resumoEfeito, mostrarAvisos, invalidarPosGesto])

  const gestoCriarAresta = useCallback(async (
    origem: PontaGesto, destino: PontaGesto,
  ) => {
    if (gestoCarregando) return
    setGestoCarregando(true)
    try {
      // dry_run ANTES do write (§7.2): o efeito é dito, nada foi gravado.
      const r = await apiFetch<GestoResposta>(
        `/malhas/${encodeURIComponent(malha)}/arestas`, {
          method: 'POST',
          body: JSON.stringify({ origem, destino, dry_run: true }),
        })
      const ef = r.efeito
      const temEfeito = ef.dependencias_criar.length > 0
        || ef.dependencias_remover.length > 0
        || ef.dependencias_transferir.length > 0
        || ef.ja_existentes_manuais.length > 0
        || ef.republicar.length > 0
      // Espelho client-side do ciclo (§3.3): criaCiclo roda sobre o
      // preview_expandido que o dry_run devolve — a autoridade é o servidor
      // (erros[]); o espelho cobre o vão de um preview sem erro, com o MESMO
      // texto (msgCiclo).
      let cicloLocal: string | null = null
      if (r.erros.length === 0 && r.preview_expandido) {
        for (const par of ef.dependencias_criar) {
          const resto = r.preview_expandido
            .filter(p => !(p.pipeline_name === par.dependente
              && p.depende_de === par.predecessor))
            .map(p => ({ source: p.depende_de, target: p.pipeline_name }))
          if (criaCiclo(resto, par.predecessor, par.dependente)) {
            cicloLocal = msgCiclo(par.dependente, par.predecessor)
            break
          }
        }
      }
      const rotulo = `${rotuloPontaGesto(origem)} → ${rotuloPontaGesto(destino)}`
      if (r.erros.length === 0 && !cicloLocal && !temEfeito) {
        // Gesto sem efeito composto (ex.: pipeline → Notificação): aplica
        // direto, como a aresta do F8 — não há nada além do desenho a
        // consentir; os avisos saem no toast.
        await aplicarAresta(origem, destino, rotulo)
      } else {
        setGesto({ acao: 'criar-aresta', rotulo, origem, destino,
                   resposta: r, cicloLocal })
      }
    } catch (err) {
      // Gramática §2.1 / 503 de migration / 404 — o detail pt-BR do servidor.
      const httpErr = err as Error & { status?: number }
      toast.error(httpErr.message || 'Erro ao validar a ligação')
    } finally {
      setGestoCarregando(false)
    }
  }, [gestoCarregando, malha, rotuloPontaGesto, aplicarAresta])

  const aplicarRemocaoAresta = useCallback(async (arestaId: number, rotulo: string) => {
    const r = await apiFetch<GestoWriteResposta>(
      `/malhas/${encodeURIComponent(malha)}/arestas/${arestaId}`,
      { method: 'DELETE' })
    toast.success(`Ligação removida: ${rotulo}`)
    resumoEfeito(r.efeito)
    mostrarAvisos(r.avisos)
    invalidarPosGesto()
  }, [malha, resumoEfeito, mostrarAvisos, invalidarPosGesto])

  const gestoRemoverAresta = useCallback(async (edge: Edge) => {
    if (gestoCarregando) return
    const arestaId = Number(edge.id.slice(ANO_PREFIX.length))
    if (!Number.isFinite(arestaId)) return
    setGestoCarregando(true)
    try {
      const r = await apiFetch<GestoResposta>(
        `/malhas/${encodeURIComponent(malha)}/arestas/${arestaId}?dry_run=true`,
        { method: 'DELETE' })
      const rotulo = `${rotuloPontaGesto(pontaDoCanvas(edge.source))} → `
        + `${rotuloPontaGesto(pontaDoCanvas(edge.target))}`
      // Remoção SEMPRE confirma (mesma barra do F8) — mesmo com efeito zero o
      // modal diz isso com todas as letras.
      setGesto({ acao: 'remover-aresta', rotulo, arestaId, resposta: r })
    } catch (err) {
      const httpErr = err as Error & { status?: number }
      if (httpErr.status === 404) {
        // Já não existia (gesto concorrente) — o estado final é o mesmo.
        toast.info(httpErr.message || 'Ligação já não existia.')
        qc.invalidateQueries({ queryKey: ['malha', malha] })
      } else {
        toast.error(httpErr.message || 'Erro ao validar a remoção')
      }
    } finally {
      setGestoCarregando(false)
    }
  }, [gestoCarregando, malha, rotuloPontaGesto, qc])

  const aplicarRemocaoNo = useCallback(async (noId: number, rotulo: string) => {
    const r = await apiFetch<GestoWriteResposta>(
      `/malhas/${encodeURIComponent(malha)}/nos/${noId}`,
      { method: 'DELETE' })
    toast.success(`Componente excluído: ${rotulo}`
      + (r.arestas_removidas ? ` (${r.arestas_removidas} ligação(ões) saíram do desenho)` : ''))
    resumoEfeito(r.efeito)
    mostrarAvisos(r.avisos)
    invalidarPosGesto()
  }, [malha, resumoEfeito, mostrarAvisos, invalidarPosGesto])

  const gestoRemoverNo = useCallback(async (rfId: string) => {
    if (gestoCarregando) return
    const noId = Number(rfId.slice(NO_PREFIX.length))
    if (!Number.isFinite(noId)) return
    setGestoCarregando(true)
    try {
      const r = await apiFetch<GestoResposta>(
        `/malhas/${encodeURIComponent(malha)}/nos/${noId}?dry_run=true`,
        { method: 'DELETE' })
      setGesto({ acao: 'remover-no', rotulo: rotuloPontaGesto({ no: noId }),
                 noId, resposta: r })
    } catch (err) {
      const httpErr = err as Error & { status?: number }
      if (httpErr.status === 404) {
        toast.info(httpErr.message || 'Componente já não existia.')
        qc.invalidateQueries({ queryKey: ['malha', malha] })
      } else {
        toast.error(httpErr.message || 'Erro ao validar a exclusão do componente')
      }
    } finally {
      setGestoCarregando(false)
    }
  }, [gestoCarregando, malha, rotuloPontaGesto, qc])

  // Confirmar o gesto do modal: re-envia SEM dry_run. O servidor RECOMPUTA
  // sobre o estado corrente (a autoridade é ele, não o preview — §7.2); 404 é
  // tolerado no padrão do confirmarExclusao do F8.
  const confirmarGesto = useCallback(async () => {
    if (!gesto) return
    setAplicandoGesto(true)
    try {
      if (gesto.acao === 'criar-aresta' && gesto.origem && gesto.destino) {
        await aplicarAresta(gesto.origem, gesto.destino, gesto.rotulo)
      } else if (gesto.acao === 'remover-aresta' && gesto.arestaId != null) {
        await aplicarRemocaoAresta(gesto.arestaId, gesto.rotulo)
      } else if (gesto.acao === 'remover-no' && gesto.noId != null) {
        await aplicarRemocaoNo(gesto.noId, gesto.rotulo)
      }
    } catch (err) {
      const httpErr = err as Error & { status?: number }
      if (httpErr.status === 404) {
        toast.info(httpErr.message || 'Já não existia — o desenho foi atualizado.')
      } else {
        // 422 do write (edição concorrente mudou o efeito) — o toast reporta
        // o que o servidor de fato decidiu.
        toast.error(httpErr.message || 'Erro ao aplicar o gesto')
      }
      invalidarPosGesto()
    } finally {
      setAplicandoGesto(false)
      setGesto(null)
    }
  }, [gesto, aplicarAresta, aplicarRemocaoAresta, aplicarRemocaoNo, invalidarPosGesto])

  // ── Criar dependência (conectar) ──────────────────────────────────────────
  const criarDep = useMutation({
    mutationFn: (body: { pipeline_name: string; depende_de: string }) =>
      apiFetch<{ ok: boolean; ja_existia: boolean; dag_config_pendente?: boolean }>('/dependencias', {
        method: 'POST',
        body: JSON.stringify(body),
      }),
    onSuccess: (r, body) => {
      const id = `dep:${body.depende_de}->${body.pipeline_name}`
      setEdges(eds => eds.some(e => e.id === id)
        ? eds
        : [...eds, depEdge(body)])
      toast.success(r.ja_existia
        ? 'Essa dependência já existia — nada foi alterado.'
        : `Dependência criada: ${body.depende_de} → ${body.pipeline_name}`)
      // Decisão 6/D30: a DAG do DEPENDENTE ficou para trás (o schedule dela
      // muda) — o servidor persistiu a pendência; aqui só se avisa o gesto.
      if (r.dag_config_pendente) toast.info(msgRepublicar(body.pipeline_name))
      // Invalida TODAS as consultas de malha: a dependência é global e aparece
      // em qualquer malha que contenha as duas pontas (aceite da F8).
      qc.invalidateQueries({ queryKey: ['malha'] })
      qc.invalidateQueries({ queryKey: ['pipelines'] })   // badge "publicação pendente"
    },
    // 422 (ciclo/inexistente/self) e 503 (migration 067) chegam como detail
    // pt-BR — o servidor é a autoridade; o toast mostra o texto dele.
    onError: (e: Error) => toast.error(e.message || 'Erro ao criar a dependência'),
  })

  const onConnect = useCallback(
    (conn: Connection) => {
      if (travado) return
      const origem = conn.source
      const alvo = conn.target
      if (!origem || !alvo) return
      const envolveNo = ehNo(origem) || ehNo(alvo)
      if (!envolveNo) {
        // Aresta pipeline → pipeline: o F8 de sempre, intocado.
        if (depsIndisponiveis) return
        if (origem === alvo) {
          toast.error(MSG_SELF)
          return
        }
        if (edgesRef.current.some(e => e.source === origem && e.target === alvo)) {
          toast.info('Essa dependência já está no diagrama.')
          return
        }
        // Validação client-side com a MESMA mensagem do servidor. O grafo local
        // só enxerga arestas entre membros da malha — ciclo que passe por
        // pipeline de fora é recusado pelo 422 do servidor (mesmo texto).
        if (criaCiclo(edgesRef.current, origem, alvo)) {
          toast.error(msgCiclo(alvo, origem))
          return
        }
        criarDep.mutate({ pipeline_name: alvo, depende_de: origem })
        return
      }
      // Aresta de NÓ (F12): gesto com dry_run antes do write. A gramática já
      // vive nos handles (Início sem entrada, Notificação/Fim sem saída); o
      // que restar proibido chega como 422 do servidor, texto literal.
      if (nosIndisponiveis) return
      if (edgesRef.current.some(e => e.source === origem && e.target === alvo)) {
        toast.info('Essa ligação já está no desenho.')
        return
      }
      void gestoCriarAresta(pontaDoCanvas(origem), pontaDoCanvas(alvo))
    },
    [travado, depsIndisponiveis, nosIndisponiveis, criarDep, gestoCriarAresta],
  )

  // ── Excluir (Delete/botão): classifica a seleção antes de qualquer modal ──
  // Aresta COMPILADA por outra malha (cadeado): recusa client-side com a MESMA
  // mensagem do 422 do servidor (Decisão 4) — e o DELETE /dependencias segue
  // recusando por baixo se algum caminho chegar lá. Aresta de NÓ: gesto com
  // dry_run (uma por vez — cada uma tem o próprio efeito). Aresta direta:
  // fluxo de confirmação do F8, intocado.
  const solicitarExclusaoArestas = useCallback((lista: Edge[]) => {
    const compiladas: Edge[] = []
    const deNo: Edge[] = []
    const diretas: Edge[] = []
    for (const e of lista) {
      const cp = (e.data as { compiladaPor?: CompiladaPor } | undefined)?.compiladaPor
      if (cp) compiladas.push(e)
      else if (e.id.startsWith(ANO_PREFIX)) deNo.push(e)
      else diretas.push(e)
    }
    for (const e of compiladas.slice(0, 2)) {
      const cp = (e.data as { compiladaPor: CompiladaPor }).compiladaPor
      toast.error(msgLinhaAssinada(e.target, e.source, cp.malha, cp.no))
    }
    if (deNo.length > 0) {
      if (deNo.length > 1) {
        toast.info('Exclua as ligações de componente uma por vez — cada uma tem o próprio efeito.')
      }
      if (diretas.length > 0) {
        toast.info('As dependências diretas selecionadas não foram tocadas — exclua-as em outro gesto.')
      }
      void gestoRemoverAresta(deNo[0])
      return
    }
    if (diretas.length > 0) setDelEdges(diretas)
  }, [gestoRemoverAresta])

  // Delete de NÓ: pipeline continua indo pro modal Membros; COMPONENTE (F12)
  // é gesto destrutivo com dry_run + confirmação (§7.3).
  const handleBeforeDelete = useCallback(
    async ({ nodes: toDel, edges: toDelEdges }: { nodes: Node[]; edges: Edge[] }) => {
      if (travado) return false
      const componentes = toDel.filter(n => ehNo(n.id))
      const pipelines = toDel.filter(n => !ehNo(n.id))
      if (pipelines.length > 0) {
        toast.info('Para retirar um pipeline da malha use o modal Membros — aqui o Delete só remove ligações (arestas) e componentes.')
        return false
      }
      if (componentes.length > 0) {
        if (componentes.length > 1) {
          toast.info('Exclua um componente por vez — cada exclusão tem o próprio efeito.')
        }
        void gestoRemoverNo(componentes[0].id)
        return false
      }
      if (toDelEdges.length > 0) {
        solicitarExclusaoArestas(toDelEdges)
        return false   // cancela o delete nativo; a confirmação decide
      }
      return true
    },
    [travado, gestoRemoverNo, solicitarExclusaoArestas],
  )

  const selEdges = useMemo(() => edges.filter(e => e.selected), [edges])
  const selComponentes = useMemo(
    () => nodes.filter(n => n.selected && ehNo(n.id)), [nodes])

  async function confirmarExclusao() {
    if (!delEdges || delEdges.length === 0) return
    setExcluindo(true)
    let removidas = 0
    const republicar = new Set<string>()
    for (const e of delEdges) {
      try {
        const r = await apiFetch<{ ok: boolean; dag_config_pendente?: boolean }>('/dependencias', {
          method: 'DELETE',
          body: JSON.stringify({ pipeline_name: e.target, depende_de: e.source }),
        })
        if (r.dag_config_pendente && e.target) republicar.add(e.target)
        removidas += 1
        setEdges(eds => eds.filter(x => x.id !== e.id))
      } catch (err) {
        const httpErr = err as Error & { status?: number }
        if (httpErr.status === 404) {
          // Já não existia no servidor (excluída por outra tela/pessoa):
          // remove do desenho e segue — o estado final é o mesmo.
          setEdges(eds => eds.filter(x => x.id !== e.id))
          toast.info(httpErr.message || 'Dependência já não existia.')
        } else {
          // Inclui o 422 de linha assinada (F11/Decisão 4) que tenha escapado
          // da recusa client-side: o texto do servidor manda, a aresta fica.
          toast.error(httpErr.message || 'Erro ao excluir a dependência')
        }
      }
    }
    setExcluindo(false)
    setDelEdges(null)
    if (removidas > 0) {
      toast.success(removidas === 1
        ? 'Dependência excluída — ela saiu de todas as malhas.'
        : `${removidas} dependências excluídas — elas saíram de todas as malhas.`)
      // Decisão 6/D30: remover dependência também muda o schedule da DAG do
      // dependente — o servidor ligou a pendência; o toast aponta o gesto.
      republicar.forEach(nome => toast.info(msgRepublicar(nome)))
      qc.invalidateQueries({ queryKey: ['malha'] })
      qc.invalidateQueries({ queryKey: ['pipelines'] })   // badge "publicação pendente"
    }
  }

  // ── Layout: reorganizar e salvar posições ─────────────────────────────────
  // Recoloca os nós em camadas na orientação pedida (a corrente, por default).
  const reLayout = useCallback((o: Orientacao) => {
    setNodes(nds => {
      const pos = liveLayout(nds, edgesRef.current, new Map(), o)
      return nds.map(n => (pos[n.id] ? { ...n, position: pos[n.id] } : n))
    })
  }, [setNodes])
  const reorganizar = useCallback(() => reLayout(orientacao), [reLayout, orientacao])

  // ── Orientação (migration 074): PATCH + re-layout automático ──────────────
  const mudarOrientacao = useMutation({
    mutationFn: ({ nova }: { nova: Orientacao; anterior: Orientacao }) =>
      apiFetch<{ ok: boolean; orientacao?: string; migration_074_pendente?: boolean }>(
        `/malhas/${encodeURIComponent(malha)}`, {
          method: 'PATCH',
          body: JSON.stringify({ orientacao: nova }),
        }),
    onSuccess: (r) => {
      // Deploy parcial (074 pendente): a tela funciona na orientação nova, mas
      // ela não persistiu — aviso honesto em vez de silêncio.
      if (r.migration_074_pendente) {
        toast.info('migration 074 pendente — a orientação vale só nesta sessão, '
          + 'o servidor ainda não a persiste.')
      }
      // O refetch traz a orientação recém-salva; o override local vira redundante.
      qc.invalidateQueries({ queryKey: ['malha', malha] })
    },
    onError: (e: Error, { anterior }) => {
      // UMA fonte só para o revert: o valor EXIBIDO antes do clique — não o do
      // servidor (numa sessão degradada sem a 074 eles divergem, e reverter
      // orientação para um lado e desenho para o outro criava estado híbrido:
      // handles laterais com nós empilhados — achado da revisão adversarial).
      setOrientacaoLocal({ malha, valor: anterior })
      reLayout(anterior)
      toast.error(e.message || 'Erro ao trocar a orientação do diagrama')
    },
  })

  const trocarOrientacao = useCallback((nova: Orientacao) => {
    if (nova === orientacao || travado) return
    const anterior = orientacao
    setOrientacaoLocal({ malha, valor: nova })
    mudarOrientacao.mutate({ nova, anterior })
    // Re-layout imediato na direção nova (mesmo módulo do Reorganizar) — as
    // posições recalculadas só persistem pelo "Salvar posições" (fica dirty).
    reLayout(nova)
    toast.info('Posições reorganizadas — use "Salvar posições" para persistir.')
    // Enquadra o desenho já na direção nova (mesmo delay do fit de abertura).
    setTimeout(() => rf.fitView({ padding: 0.2, duration: 250 }), 90)
  }, [orientacao, travado, malha, mudarOrientacao, reLayout, rf])

  const salvarLayout = useMutation({
    mutationFn: () =>
      apiFetch<{ ok: boolean; atualizados: number }>(
        `/malhas/${encodeURIComponent(malha)}/layout`, {
          method: 'PUT',
          body: JSON.stringify({
            // n.id serve para os dois mundos: pipeline pelo nome e componente
            // como "no:{id}" — o contrato §9 do PUT aceita ambos.
            posicoes: nodesRef.current.map(n => ({
              pipeline_name: n.id,
              layout_x: Math.round(n.position.x),
              layout_y: Math.round(n.position.y),
            })),
          }),
        }),
    onSuccess: (r) => {
      toast.success(`Posições salvas (${r.atualizados} nó${r.atualizados !== 1 ? 's' : ''}).`)
      // O refetch traz o layout recém-salvo — o baseline derivado passa a bater
      // com o canvas e o botão volta a desabilitar até a próxima mudança real.
      qc.invalidateQueries({ queryKey: ['malha', malha] })
    },
    onError: (e: Error) => toast.error(e.message || 'Erro ao salvar as posições'),
  })

  // ── Paleta: adicionar membro (POST /malhas/{name}/pipelines, F7) ──────────
  const addMembro = useMutation({
    mutationFn: (pipeline_name: string) =>
      apiFetch<{ ok: boolean; pipeline_name: string; ja_membro: boolean }>(
        `/malhas/${encodeURIComponent(malha)}/pipelines`, {
          method: 'POST',
          body: JSON.stringify({ pipeline_name }),
        }),
    onSuccess: (r) => {
      toast.success(r.ja_membro
        ? `"${r.pipeline_name}" já é membro desta malha.`
        : `Pipeline "${r.pipeline_name}" entrou na malha.`)
      setBusca('')
      qc.invalidateQueries({ queryKey: ['malha', malha] })
      qc.invalidateQueries({ queryKey: ['malhas'] })   // contagens dos cards
    },
    onError: (e: Error) => toast.error(e.message || 'Erro ao adicionar o pipeline'),
  })

  // ── Paleta de componentes: arrastar-para-criar (POST /nos, F12) ───────────
  const addNo = useMutation({
    mutationFn: (v: { tipo: TipoComponente; x: number; y: number }) =>
      apiFetch<{ ok: boolean; id: number; avisos: AvisoDesenho[] }>(
        `/malhas/${encodeURIComponent(malha)}/nos`, {
          method: 'POST',
          body: JSON.stringify({ tipo: v.tipo, layout_x: v.x, layout_y: v.y }),
        }),
    onSuccess: (r, v) => {
      toast.success(`Componente ${COMPONENTE_META[v.tipo].rotulo} adicionado ao desenho.`)
      mostrarAvisos(r.avisos)
      qc.invalidateQueries({ queryKey: ['malha', malha] })
    },
    // Inclui o 422 de 2º Início/Fim (a paleta previne; o servidor decide).
    onError: (e: Error) => toast.error(e.message || 'Erro ao adicionar o componente'),
  })

  const onDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
  }, [])
  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    if (travado || nosIndisponiveis) return
    const tipo = e.dataTransfer.getData(DND_MIME_NO) as TipoComponente
    if (!tipo || !(tipo in COMPONENTE_META)) return
    const p = rf.screenToFlowPosition({ x: e.clientX, y: e.clientY })
    addNo.mutate({ tipo, x: Math.round(p.x), y: Math.round(p.y) })
  }, [travado, nosIndisponiveis, rf, addNo])

  // ── "Prender as pontas soltas" (§2.2): terminais membros → Fim ────────────
  // Terminal = pipeline sem saída para OUTRO pipeline, Aguarde ou Fim (saída
  // só para Notificação não conta — o aviso é escutar, não concluir). Ligar
  // ao Fim tem efeito zero na 067 — é o desenho da conclusão, em um clique.
  const fimNo = useMemo(
    () => grafo?.nos.find(n => n.tipo === 'fim') ?? null, [grafo])
  const pontasSoltas = useMemo(() => {
    if (!fimNo) return []
    const naoSolto = new Set<string>()
    for (const e of edges) {
      if (ehNo(e.source)) continue
      const alvoTipo = ehNo(e.target)
        ? tipoDoNo.get(Number(e.target.slice(NO_PREFIX.length)))
        : 'pipeline'
      if (alvoTipo !== 'notificacao') naoSolto.add(e.source)
    }
    return nodes
      .filter(n => n.type === 'malhaPipeline' && !naoSolto.has(n.id))
      .map(n => n.id)
      .sort()
  }, [fimNo, nodes, edges, tipoDoNo])

  async function prenderPontasSoltas() {
    if (!fimNo || pontasSoltas.length === 0 || prendendo) return
    setPrendendo(true)
    let ligadas = 0
    for (const p of pontasSoltas) {
      try {
        await apiFetch(`/malhas/${encodeURIComponent(malha)}/arestas`, {
          method: 'POST',
          body: JSON.stringify({ origem: { pipeline: p }, destino: { no: fimNo.id } }),
        })
        ligadas += 1
      } catch (err) {
        const httpErr = err as Error & { status?: number }
        toast.error(httpErr.message || `Erro ao ligar ${p} ao Fim`)
      }
    }
    setPrendendo(false)
    if (ligadas > 0) {
      toast.success(ligadas === 1
        ? '1 ponta solta presa ao Fim.'
        : `${ligadas} pontas soltas presas ao Fim.`)
      qc.invalidateQueries({ queryKey: ['malha', malha] })
    }
  }

  // ── Estados de borda ──────────────────────────────────────────────────────
  if (isLoading) {
    return (
      <div className="flex h-full w-full items-center justify-center rounded-xl border border-edge bg-canvas">
        <PageSpinner />
      </div>
    )
  }
  if (isError) {
    return (
      <div className="flex h-full w-full flex-col items-center justify-center gap-2 rounded-xl border border-edge bg-canvas text-sm">
        <AlertCircle size={20} className="text-red-600 dark:text-red-400" />
        <span className="text-ink">Não foi possível carregar a malha.</span>
        <span className="text-xs text-dim">{(error as Error)?.message}</span>
      </div>
    )
  }

  const modoBtnCls = (ativo: boolean) =>
    `inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-medium transition-colors ${
      ativo
        ? 'bg-[#1A5FA8] text-white'
        : 'border border-edge bg-canvas text-dim hover:text-ink hover:bg-edge/40'
    }`
  const navBtnCls =
    'inline-flex items-center px-1.5 py-1 rounded-md text-xs border border-edge bg-canvas ' +
    'text-dim hover:text-ink hover:bg-edge/40 transition-colors disabled:opacity-40 disabled:pointer-events-none'

  // Rótulo de nó p/ o banner de avisos ("Aguarde #8"), null p/ aviso geral.
  const rotuloNoAviso = (no: number | null): string | null => {
    if (no == null) return null
    return rotuloPontaGesto({ no })
  }

  const temInicio = !!grafo?.nos.some(n => n.tipo === 'inicio')
  const temFim = !!grafo?.nos.some(n => n.tipo === 'fim')

  // Efeito/erros do gesto pendente (modal).
  const gestoEf = gesto?.resposta.efeito
  const gestoErros = gesto
    ? [...gesto.resposta.erros,
       ...(gesto.cicloLocal && gesto.resposta.erros.length === 0
         ? [gesto.cicloLocal] : [])]
    : []
  const gestoTemEfeito = !!gestoEf && (
    gestoEf.dependencias_criar.length > 0
    || gestoEf.dependencias_remover.length > 0
    || gestoEf.dependencias_transferir.length > 0
    || gestoEf.ja_existentes_manuais.length > 0
    || gestoEf.republicar.length > 0)

  return (
    <div className="flex h-full w-full flex-col overflow-hidden rounded-xl border border-edge bg-canvas">
      {/* Barra superior (F9): Montagem | Execução + seletor de data de referência. */}
      <div className="flex flex-wrap items-center gap-2 border-b border-edge bg-panel px-3 py-2">
        <div className="flex gap-1">
          <button
            onClick={() => setModo('montagem')}
            title="Montar a malha: membros, dependências e layout"
            className={modoBtnCls(!emExecucao)}
          >
            <Wrench size={12} /> Montagem
          </button>
          <button
            onClick={() => setModo('execucao')}
            title="Ver a execução da malha numa data de referência (edição travada)"
            className={modoBtnCls(emExecucao)}
          >
            <Activity size={12} /> Execução
          </button>
        </div>
        {/* Orientação do diagrama (por malha, persiste no servidor com o
            layout). Consulta (readOnly) vê a orientação salva, mas não troca —
            o controle nem aparece. */}
        {!emExecucao && !readOnly && (
          <div className="ml-auto flex items-center gap-1.5">
            <span className="text-[11px] text-dim">Orientação</span>
            <div className="flex gap-1">
              <button
                onClick={() => trocarOrientacao('horizontal')}
                disabled={mudarOrientacao.isPending}
                title="Diagrama horizontal (esquerda → direita) — trocar reorganiza as posições na nova direção"
                className={modoBtnCls(orientacao === 'horizontal')}
              >
                <ArrowRightLeft size={12} /> horizontal
              </button>
              <button
                onClick={() => trocarOrientacao('vertical')}
                disabled={mudarOrientacao.isPending}
                title="Diagrama vertical (cima → baixo) — trocar reorganiza as posições na nova direção"
                className={modoBtnCls(orientacao === 'vertical')}
              >
                <ArrowUpDown size={12} /> vertical
              </button>
            </div>
          </div>
        )}
        {emExecucao && (
          <div className="ml-auto flex flex-wrap items-center gap-1.5">
            <span className="text-[11px] text-dim">Data de referência</span>
            <button
              onClick={() => setDataRef(somaDia(dataExibida, -1))}
              disabled={!dataExibida}
              title="Dia anterior"
              className={navBtnCls}
            >
              <ChevronLeft size={13} />
            </button>
            <input
              type="date"
              value={dataExibida}
              onChange={e => setDataRef(e.target.value || null)}
              className="rounded-md border border-edge bg-canvas px-2 py-1 text-xs text-ink focus:outline-none focus:ring-2 focus:ring-[#1A5FA8]/40"
            />
            <button
              onClick={() => setDataRef(somaDia(dataExibida, 1))}
              disabled={!dataExibida}
              title="Dia seguinte"
              className={navBtnCls}
            >
              <ChevronRight size={13} />
            </button>
            <button
              onClick={() => setDataRef(null)}
              disabled={dataRef === null}
              title="Voltar à data de referência corrente (ODATE, calculado pela virada global)"
              className={`${navBtnCls} px-2`}
            >
              hoje
            </button>
            {execQuery.isFetching && (
              <RefreshCw size={12} className="animate-spin text-dim" />
            )}
          </div>
        )}
      </div>

      {(depsIndisponiveis || (emExecucao && execData?.migration_067_pendente === true)) && (
        <div className="flex items-center gap-2 border-b border-amber-200 bg-amber-50 px-3 py-2 text-[12px] text-amber-700 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-400">
          <AlertTriangle size={14} className="shrink-0" />
          <span>
            migration 067 pendente — as dependências não estão disponíveis neste
            ambiente; o diagrama mostra só os pipelines, sem arestas, e a criação
            de dependências fica desabilitada.
          </span>
        </div>
      )}

      {/* F12: deploy parcial da 075 — a malha abre normal, sem componentes. */}
      {!emExecucao && nosIndisponiveis && (
        <div className="flex items-center gap-2 border-b border-amber-200 bg-amber-50 px-3 py-2 text-[12px] text-amber-700 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-400">
          <AlertTriangle size={14} className="shrink-0" />
          <span>
            migration 075 pendente — os componentes de malha (Início, Aguarde,
            Notificação e Fim) não estão disponíveis neste ambiente; o restante
            do diagrama funciona normalmente.
          </span>
        </div>
      )}

      {/* F12: banner PERSISTENTE de avisos do desenho (§2.2) — o GET repete a
          lista enquanto a situação durar; o toast do gesto mostra só os novos.
          A linha das pontas soltas é derivada do grafo vivo + o botão do §2.2. */}
      {!emExecucao && (avisosDesenho.length > 0
        || (temFim && pontasSoltas.length > 0)) && (
        <div className="max-h-28 overflow-y-auto border-b border-amber-200 bg-amber-50 px-3 py-1.5 dark:border-amber-800 dark:bg-amber-900/20">
          {avisosDesenho.map((a, i) => (
            <div
              key={`${a.no ?? 'g'}-${i}`}
              className="flex items-center gap-1.5 py-0.5 text-[11px] text-amber-700 dark:text-amber-400"
            >
              {a.nivel === 'forte'
                ? <AlertTriangle size={12} className="shrink-0" />
                : <Info size={12} className="shrink-0" />}
              <span>
                {rotuloNoAviso(a.no) && (
                  <strong>{rotuloNoAviso(a.no)}: </strong>
                )}
                {a.mensagem}
              </span>
            </div>
          ))}
          {temFim && pontasSoltas.length > 0 && (
            <div className="flex flex-wrap items-center gap-1.5 py-0.5 text-[11px] text-amber-700 dark:text-amber-400">
              <AlertTriangle size={12} className="shrink-0" />
              <span>
                <strong>Fim: </strong>
                {pontasSoltas.length === 1
                  ? `o pipeline terminal ${pontasSoltas[0]} ainda não está ligado ao Fim`
                  : `${pontasSoltas.length} pipelines terminais ainda não estão ligados ao Fim`}
              </span>
              {!travado && (
                <button
                  onClick={() => void prenderPontasSoltas()}
                  disabled={prendendo}
                  title={`Ligar ao Fim: ${pontasSoltas.join(', ')}`}
                  className="inline-flex items-center gap-1 rounded-md border border-amber-300 bg-amber-100 px-1.5 py-0.5 text-[10px] font-semibold text-amber-800 transition-colors hover:bg-amber-200 disabled:opacity-50 dark:border-amber-700 dark:bg-amber-900/40 dark:text-amber-300 dark:hover:bg-amber-900/60"
                >
                  <Anchor size={10} /> {prendendo ? 'prendendo…' : 'Prender as pontas soltas'}
                </button>
              )}
            </div>
          )}
        </div>
      )}

      {/* F9: estados honestos da visão de execução. Antes da retomada F2–F4
          nada grava em etl_pipeline_execucao — o vazio é esperado e dito. */}
      {emExecucao && execQuery.isError && (
        <div className="flex items-center gap-2 border-b border-red-200 bg-red-50 px-3 py-2 text-[12px] text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300">
          <AlertCircle size={14} className="shrink-0" />
          <span>
            Não foi possível carregar a execução desta data:{' '}
            {(execQuery.error as Error)?.message ?? 'erro desconhecido'}
          </span>
        </div>
      )}
      {emExecucao && execData && !execData.migration_067_pendente
        && execData.execucoes.length === 0 && (
        <div className="flex items-center gap-2 border-b border-blue-200 bg-blue-50 px-3 py-2 text-[12px] text-blue-800 dark:border-blue-800 dark:bg-blue-900/20 dark:text-blue-200">
          <Info size={14} className="shrink-0" />
          <span>
            Sem execuções registradas nesta data — o registro chega com a
            retomada das dependências (F2).
          </span>
        </div>
      )}

      <div className="flex min-h-0 flex-1">
        {/* Painel lateral de eventos da guardiã (F9) — só na visão de execução. */}
        {emExecucao && (
          <div className="flex w-64 shrink-0 flex-col border-r border-edge bg-panel">
            <div className="flex items-center gap-1.5 border-b border-edge px-3 py-2">
              <ShieldAlert size={13} className="shrink-0 text-dim" />
              <span className="text-xs font-semibold uppercase tracking-wider text-dim">
                Eventos da guardiã
              </span>
            </div>
            <div className="flex min-h-0 flex-1 flex-col gap-1.5 overflow-y-auto p-2">
              {eventos.length === 0 ? (
                <p className="px-1 py-4 text-center text-[11px] leading-relaxed text-dim">
                  Nenhum evento da guardiã nesta data.
                </p>
              ) : eventos.map((ev, i) => (
                <div key={`${ev.pipeline_name}-${ev.criado_em}-${i}`}
                  className="rounded-md border border-edge bg-canvas px-2 py-1.5">
                  <div className="flex items-center gap-1.5">
                    <span className={`rounded border px-1 py-px text-[9px] font-bold ${estiloEvento(ev.tipo)}`}>
                      {ev.tipo}
                    </span>
                    <span className="ml-auto text-[10px] text-dim">{horaCurta(ev.criado_em)}</span>
                  </div>
                  <div className="mt-0.5 truncate font-mono text-[10px] text-ink" title={ev.pipeline_name}>
                    {ev.pipeline_name}
                  </div>
                  {ev.mensagem && (
                    <p className="mt-0.5 text-[10px] leading-snug text-dim">{ev.mensagem}</p>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Paleta lateral: ADICIONAR membro (a remoção continua no modal
            Membros da F7 — sem duplicar o caminho) + componentes (F12). */}
        {!readOnly && !emExecucao && (
          <div className="flex w-60 shrink-0 flex-col gap-2 overflow-y-auto border-r border-edge bg-panel p-3">
            <span className="text-xs font-semibold uppercase tracking-wider text-dim">
              Adicionar pipeline
            </span>
            <Autocomplete
              value={busca}
              onChange={setBusca}
              onSelect={setBusca}
              fetchSuggestions={q =>
                apiFetch<{ data: { pipeline_name: string }[] }>(
                  `/pipelines?limit=10&filter_name=${encodeURIComponent(q)}`)
                  .then(r => r.data.map(p => p.pipeline_name))
              }
              placeholder="busque por nome..."
              onKeyDown={e => {
                if (e.key === 'Enter' && busca.trim()) addMembro.mutate(busca.trim())
              }}
            />
            <Button
              size="sm"
              onClick={() => addMembro.mutate(busca.trim())}
              loading={addMembro.isPending}
              disabled={!busca.trim()}
            >
              <Plus size={13} /> Adicionar à malha
            </Button>
            <p className="mt-1 text-[11px] leading-relaxed text-dim">
              O pipeline entra como <strong className="text-ink">membro</strong> e
              vira um nó no canvas. Ligue dois nós para criar a
              dependência <em>(origem → dependente)</em> — ela é <strong className="text-ink">real
              e global</strong>, não um desenho desta malha.
            </p>

            {/* Componentes de malha (F12): arrastar para o canvas cria o nó
                (POST /nos) — unicidade de Início/Fim prevenida aqui e
                garantida pelo 422 + índice filtrado no servidor. */}
            <div className="flex flex-col gap-1.5 border-t border-edge pt-2">
              <span className="text-xs font-semibold uppercase tracking-wider text-dim">
                Componentes
              </span>
              {nosIndisponiveis ? (
                <p className="text-[11px] leading-relaxed text-dim">
                  migration 075 pendente — os componentes ficam indisponíveis
                  neste ambiente.
                </p>
              ) : (
                <>
                  {COMPONENTES_ORDEM.map(tipo => {
                    const unico = (tipo === 'inicio' && temInicio)
                      || (tipo === 'fim' && temFim)
                    return (
                      <ItemPaletaComponente
                        key={tipo}
                        tipo={tipo}
                        desabilitado={unico}
                        motivo={unico
                          ? `A malha já tem um nó ${COMPONENTE_META[tipo].rotulo} — só pode haver um por malha`
                          : undefined}
                      />
                    )
                  })}
                  <p className="text-[11px] leading-relaxed text-dim">
                    Arraste para o canvas. Ligar pernas a um{' '}
                    <strong className="text-ink">Aguarde</strong> compila
                    dependências reais — o efeito é mostrado{' '}
                    <em>antes</em> de gravar.
                  </p>
                </>
              )}
            </div>

            <p className="border-t border-edge pt-2 text-[11px] leading-relaxed text-dim">
              Para <strong className="text-ink">retirar</strong> um pipeline da malha,
              use o modal <em>Membros</em> no card da malha.
            </p>
          </div>
        )}

        <div className="relative min-h-0 min-w-0 flex-1">
          {nodes.length === 0 && (
            <div className="pointer-events-none absolute inset-0 z-10 flex flex-col items-center justify-center gap-1 text-dim">
              <span className="text-3xl">⬡</span>
              <p className="text-sm font-medium">Nenhum pipeline nesta malha</p>
              {!readOnly && !emExecucao && (
                <p className="text-xs">Adicione o primeiro pela busca à esquerda.</p>
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
            onDrop={onDrop}
            onDragOver={onDragOver}
            colorMode={colorMode}
            fitView
            fitViewOptions={{ padding: 0.25 }}
            proOptions={{ hideAttribution: true }}
            defaultEdgeOptions={{ type: 'smoothstep' }}
            nodesDraggable={!travado}
            nodesConnectable={!travado && !(depsIndisponiveis && nosIndisponiveis)}
            edgesFocusable={!travado}
            deleteKeyCode={travado ? null : ['Delete', 'Backspace']}
          >
            <Background gap={18} size={1} />
            <Controls />
            <MiniMap pannable zoomable nodeColor={miniMapColor} className="!bg-panel" />

            {/* Barra de ações (topo direita) — selo nos modos de leitura. */}
            <Panel position="top-right">
              {emExecucao ? (
                <span className="flex items-center gap-1.5 rounded-lg border border-edge bg-panel/95 px-2.5 py-1.5 text-[11px] font-semibold text-dim shadow-md backdrop-blur">
                  <Activity size={12} /> visão de execução — edição travada
                </span>
              ) : readOnly ? (
                <span className="flex items-center gap-1.5 rounded-lg border border-edge bg-panel/95 px-2.5 py-1.5 text-[11px] font-semibold text-dim shadow-md backdrop-blur">
                  <MousePointerClick size={12} /> somente leitura
                </span>
              ) : (
                <div className="flex items-center gap-2 rounded-lg border border-edge bg-panel/95 px-2.5 py-2 shadow-md backdrop-blur">
                  {selComponentes.length === 1 && (
                    <Button
                      variant="danger"
                      size="sm"
                      onClick={() => void gestoRemoverNo(selComponentes[0].id)}
                      title="Excluir o componente do desenho — o efeito nas dependências é mostrado antes de gravar"
                    >
                      <Trash2 size={13} /> Excluir componente
                    </Button>
                  )}
                  {selEdges.length > 0 && (
                    <Button
                      variant="danger"
                      size="sm"
                      onClick={() => solicitarExclusaoArestas(selEdges)}
                      title="Excluir a(s) ligação(ões) selecionada(s) — o efeito real é mostrado antes"
                    >
                      <Trash2 size={13} />{' '}
                      {selEdges.some(e => e.id.startsWith(ANO_PREFIX))
                        ? 'Excluir ligação'
                        : 'Excluir dependência'}
                    </Button>
                  )}
                  {dirty && (
                    <span className="flex items-center gap-1 rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-[11px] font-semibold text-amber-700 dark:border-amber-800 dark:bg-amber-900/30 dark:text-amber-300">
                      <span className="h-1.5 w-1.5 rounded-full bg-amber-500" />
                      posições não salvas
                    </span>
                  )}
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={reorganizar}
                    title="Recoloca os nós em camadas pelas dependências"
                  >
                    <RefreshCw size={13} /> Reorganizar
                  </Button>
                  <Button
                    size="sm"
                    onClick={() => salvarLayout.mutate()}
                    loading={salvarLayout.isPending}
                    disabled={!dirty}
                    title={dirty
                      ? 'Persistir as posições dos nós nesta malha'
                      : 'Nenhuma posição mudou — nada a salvar'}
                  >
                    <Save size={13} /> Salvar posições
                  </Button>
                </div>
              )}
            </Panel>
          </ReactFlow>
        </div>
      </div>

      {/* Legenda fixa da visão de execução (F9) — os seis status do contrato. */}
      {emExecucao && (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-edge bg-panel px-3 py-1.5">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-dim">Legenda</span>
          {ORDEM_LEGENDA.map(s => {
            const e = STATUS_EXECUCAO[s]
            return (
              <span key={s} className="flex items-center gap-1 text-[10px] text-dim">
                <span className={`h-2 w-2 rounded-full ${e.dot} ${e.animado ? 'animate-pulse' : ''}`} />
                {e.rotulo}
              </span>
            )
          })}
          <span className="ml-auto text-[10px] text-dim">
            nó sem anel = sem execução registrada na data
          </span>
        </div>
      )}

      {/* Confirmação de exclusão de aresta — §4b: a dependência é GLOBAL. */}
      <Modal
        open={!!delEdges}
        onClose={() => setDelEdges(null)}
        title="Excluir dependência"
      >
        <div className="flex flex-col gap-3">
          <p className="text-sm text-ink">
            Isto apaga a dependência REAL entre os pipelines — ela some de todas
            as malhas. Continuar?
          </p>
          <div className="flex flex-col gap-1">
            {(delEdges ?? []).map(e => (
              <div key={e.id} className="flex items-center gap-2 rounded-md border border-edge bg-canvas px-3 py-1.5">
                <Link2 size={12} className="shrink-0 text-dim" />
                <span className="font-mono text-xs text-ink">
                  {e.source} <span className="text-dim">→</span> {e.target}
                </span>
              </div>
            ))}
          </div>
          <p className="text-[11px] text-dim">
            Lê-se "origem → dependente": o dependente deixa de esperar a origem
            em TODAS as malhas — não é só um ajuste visual deste diagrama.
          </p>
          <div className="flex justify-end gap-2 pt-1">
            <Button variant="secondary" onClick={() => setDelEdges(null)}>Cancelar</Button>
            <Button variant="danger" onClick={confirmarExclusao} loading={excluindo}>
              <Trash2 size={13} /> Excluir dependência
            </Button>
          </div>
        </div>
      </Modal>

      {/* F12: modal do GESTO de componente — o efeito §7.2 dito ANTES do
          write; erros[] (ciclo) bloqueiam com o texto literal do servidor. */}
      <Modal
        open={!!gesto}
        onClose={() => { if (!aplicandoGesto) setGesto(null) }}
        title={gesto?.acao === 'criar-aresta' ? 'Ligar componente'
          : gesto?.acao === 'remover-aresta' ? 'Remover ligação'
          : 'Excluir componente'}
        size="lg"
      >
        {gesto && (
          <div className="flex flex-col gap-3">
            <p className="text-sm text-ink">
              {gesto.acao === 'criar-aresta' && (
                <>Ligar <strong className="font-mono text-xs">{gesto.rotulo}</strong> — o
                efeito abaixo é aplicado ao confirmar:</>
              )}
              {gesto.acao === 'remover-aresta' && (
                <>Remover a ligação <strong className="font-mono text-xs">{gesto.rotulo}</strong> — o
                efeito abaixo é aplicado ao confirmar:</>
              )}
              {gesto.acao === 'remover-no' && (
                <>Excluir <strong>{gesto.rotulo}</strong> — as ligações dele saem do
                desenho e o efeito abaixo é aplicado ao confirmar:</>
              )}
            </p>

            {/* Erros BLOQUEIAM (ciclo, Decisão 15) — o texto é o do servidor,
                literal; nada foi gravado. */}
            {gestoErros.map((e, i) => (
              <div
                key={i}
                className="flex items-start gap-2 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-[12px] text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300"
              >
                <AlertCircle size={14} className="mt-0.5 shrink-0" />
                <span>{e}</span>
              </div>
            ))}
            {gestoErros.length > 0 && (
              <p className="text-[11px] text-dim">
                O gesto está bloqueado — nada foi gravado no desenho nem nas
                dependências.
              </p>
            )}

            {gestoErros.length === 0 && gestoEf && (
              <div className="flex max-h-[46vh] flex-col gap-2 overflow-y-auto">
                {!gestoTemEfeito && (
                  <p className="text-[12px] text-dim">
                    Nenhuma dependência real é afetada — só o desenho muda.
                  </p>
                )}
                {gestoEf.dependencias_criar.length > 0 && (
                  <div className="flex flex-col gap-1">
                    <p className="text-[11px] font-semibold uppercase tracking-wider text-dim">
                      Dependências a criar
                    </p>
                    {gestoEf.dependencias_criar.map(d => (
                      <div key={`c-${d.dependente}-${d.predecessor}`}
                        className="flex items-center gap-2 rounded-md border border-edge bg-canvas px-3 py-1.5">
                        <Plus size={12} className="shrink-0 text-green-600 dark:text-green-400" />
                        <span className="font-mono text-xs text-ink">
                          {d.predecessor} <span className="text-dim">→</span> {d.dependente}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
                {gestoEf.dependencias_remover.length > 0 && (
                  <div className="flex flex-col gap-1">
                    <p className="text-[11px] font-semibold uppercase tracking-wider text-dim">
                      Dependências a remover
                    </p>
                    {gestoEf.dependencias_remover.map(d => (
                      <div key={`r-${d.dependente}-${d.predecessor}`}
                        className="flex items-center gap-2 rounded-md border border-edge bg-canvas px-3 py-1.5">
                        <Minus size={12} className="shrink-0 text-red-600 dark:text-red-400" />
                        <span className="font-mono text-xs text-ink">
                          {d.predecessor} <span className="text-dim">→</span> {d.dependente}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
                {gestoEf.dependencias_transferir.length > 0 && (
                  <div className="flex flex-col gap-1">
                    <p className="text-[11px] font-semibold uppercase tracking-wider text-dim">
                      Assinaturas transferidas (a dependência continua)
                    </p>
                    {gestoEf.dependencias_transferir.map(d => (
                      <div key={`t-${d.dependente}-${d.predecessor}`}
                        className="flex items-center gap-2 rounded-md border border-edge bg-canvas px-3 py-1.5">
                        <ArrowRightLeft size={12} className="shrink-0 text-blue-600 dark:text-blue-400" />
                        <span className="min-w-0 font-mono text-xs text-ink">
                          {d.predecessor} <span className="text-dim">→</span> {d.dependente}
                          <span className="ml-1 font-sans text-[10px] text-dim">
                            passa à malha '{d.para_malha}' (nó #{d.para_no})
                          </span>
                        </span>
                      </div>
                    ))}
                  </div>
                )}
                {gestoEf.ja_existentes_manuais.length > 0 && (
                  <div className="flex flex-col gap-1">
                    <p className="text-[11px] font-semibold uppercase tracking-wider text-dim">
                      Já existiam (manuais — seguem do operador, não serão assinadas)
                    </p>
                    {gestoEf.ja_existentes_manuais.map(d => (
                      <div key={`m-${d.dependente}-${d.predecessor}`}
                        className="flex items-center gap-2 rounded-md border border-edge bg-canvas px-3 py-1.5">
                        <Info size={12} className="shrink-0 text-dim" />
                        <span className="font-mono text-xs text-ink">
                          {d.predecessor} <span className="text-dim">→</span> {d.dependente}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
                {gestoEf.republicar.length > 0 && (
                  <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-[11px] text-amber-700 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-400">
                    <strong>Republicação necessária:</strong>{' '}
                    {gestoEf.republicar.join(', ')} — depois de confirmar,
                    publique nova versão (Pipelines ▸ Publicar nova versão).
                  </div>
                )}
                {gesto.resposta.avisos.length > 0 && (
                  <div className="flex flex-col gap-0.5">
                    {gesto.resposta.avisos.map((a, i) => (
                      <div key={i} className="flex items-center gap-1.5 text-[11px] text-amber-700 dark:text-amber-400">
                        {a.nivel === 'forte'
                          ? <AlertTriangle size={12} className="shrink-0" />
                          : <Info size={12} className="shrink-0" />}
                        <span>
                          {rotuloNoAviso(a.no) && <strong>{rotuloNoAviso(a.no)}: </strong>}
                          {a.mensagem}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {gestoErros.length === 0 && (
              <p className="text-[11px] text-dim">
                O servidor recalcula o efeito ao confirmar — se algo mudou nesse
                meio tempo, o resultado real é reportado no aviso.
              </p>
            )}

            <div className="flex justify-end gap-2 pt-1">
              <Button
                variant="secondary"
                onClick={() => setGesto(null)}
                disabled={aplicandoGesto}
              >
                {gestoErros.length > 0 ? 'Fechar' : 'Cancelar'}
              </Button>
              {gestoErros.length === 0 && (
                <Button
                  variant={gesto.acao === 'criar-aresta' ? 'primary' : 'danger'}
                  onClick={() => void confirmarGesto()}
                  loading={aplicandoGesto}
                >
                  {gesto.acao === 'criar-aresta' && <><Link2 size={13} /> Ligar e aplicar</>}
                  {gesto.acao === 'remover-aresta' && <><Trash2 size={13} /> Remover ligação</>}
                  {gesto.acao === 'remover-no' && <><Trash2 size={13} /> Excluir componente</>}
                </Button>
              )}
            </div>
          </div>
        )}
      </Modal>
    </div>
  )
}
