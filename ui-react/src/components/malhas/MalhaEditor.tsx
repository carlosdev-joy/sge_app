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
  Activity, AlertCircle, AlertTriangle, ArrowRightLeft, ArrowUpDown,
  ChevronLeft, ChevronRight, Info, Link2,
  MousePointerClick, Plus, RefreshCw, Save, ShieldAlert, Trash2, Wrench,
} from 'lucide-react'
import { useColorMode } from '../etapas/useColorMode'
import { liveLayout, criaCiclo, type Orientacao } from '../etapas/layoutGrafo'
import { MalhaPipelineNode, type MalhaPipelineNodeData } from './MalhaPipelineNode'
import {
  STATUS_EXECUCAO, ORDEM_LEGENDA, estiloEvento,
  type ExecucaoPipeline, type MalhaExecucaoApi,
} from './statusExecucao'
// Mensagens de recusa ESPELHADAS do servidor — módulo compartilhado com o
// DependenciasModal da F5: cliente e servidor com o MESMO texto, num lugar só.
import { msgCiclo, MSG_SELF, msgRepublicar } from './mensagensDependencia'

const nodeTypes = { malhaPipeline: MalhaPipelineNode }

// ── Tipos do payload da API (/malhas/{name}) ────────────────────────────────
interface MalhaMembroApi {
  pipeline_name: string
  active: 0 | 1 | boolean
  criticidade: string | null
  schedule_type: string | null
  layout_x: number | null
  layout_y: number | null
}
interface MalhaArestaApi {
  pipeline_name: string   // o dependente (destino da seta)
  depende_de: string      // o predecessor (origem da seta)
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
  // Deploy parcial (migration 067 ausente): a API devolve "arestas": [] e liga
  // esta flag — o editor avisa e desliga a criação de arestas. Chave `arestas`
  // AUSENTE (API anterior à F8) degrada do mesmo jeito.
  migration_067_pendente?: boolean
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

// Aresta de dependência: depende_de → pipeline_name, sem rótulo (o sentido da
// seta já diz tudo — Control-M também não rotula).
function depEdge(a: MalhaArestaApi): Edge {
  return {
    id: `dep:${a.depende_de}->${a.pipeline_name}`,
    source: a.depende_de,
    target: a.pipeline_name,
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

// Cor do nó no minimapa: azul da casa p/ ativo, slate p/ inativo.
function miniMapColor(n: Node): string {
  return (n.data as MalhaPipelineNodeData | undefined)?.active ? '#1A5FA8' : '#94a3b8'
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

  // Espelho dos estados p/ callbacks estáveis (padrão do FluxoEditor).
  const nodesRef = useRef<Node[]>([])
  useEffect(() => { nodesRef.current = nodes }, [nodes])
  const edgesRef = useRef<Edge[]>([])
  useEffect(() => { edgesRef.current = edges }, [edges])

  // ── Grafo derivado da API (puro) ──────────────────────────────────────────
  // Arestas prontas + BASELINE de posições: o que o SERVIDOR conhece de cada
  // nó (layout salvo em etl_malha_pipeline, senão o auto-layout topológico do
  // liveLayout — colunas = ondas do grafo). É contra este baseline que o
  // "Salvar posições" decide se há algo a salvar.
  const grafo = useMemo(() => {
    if (!data) return null
    const membros = data.membros ?? []
    const arestas = Array.isArray(data.arestas) ? data.arestas : []
    const novasEdges = arestas.map(depEdge)
    // O auto-layout do baseline segue a orientação SALVA (a que o servidor
    // conhece) — o override local ainda-não-persistido não muda o baseline.
    const auto = liveLayout(
      membros.map(m => ({ id: m.pipeline_name })), novasEdges, new Map(),
      data.orientacao === 'vertical' ? 'vertical' : 'horizontal')
    const baseline = new Map<string, { x: number; y: number }>()
    for (const m of membros) {
      const salva = (m.layout_x != null && m.layout_y != null)
        ? { x: m.layout_x, y: m.layout_y }
        : null
      const base = salva ?? auto[m.pipeline_name] ?? { x: 0, y: 0 }
      baseline.set(m.pipeline_name, { x: Math.round(base.x), y: Math.round(base.y) })
    }
    return { membros, novasEdges, baseline }
  }, [data])

  // (Re)constrói nós/arestas a partir do grafo derivado. O rebuild PRESERVA a
  // posição atual de nó que já está no canvas (as arestas são persistidas na
  // hora, então todo refetch é seguro; só a posição é estado local até o
  // "Salvar posições"). Na visão de execução (F9) o mesmo rebuild anexa o
  // status da data como CAMADA no data do nó — membro sem linha em
  // etl_pipeline_execucao fica sem camada (exec: null), nunca com cor inventada.
  // A orientação entra no data de TODOS os nós (rebuild ao trocar): é ela que
  // decide onde os handles ancoram — a visão de Execução herda a mesma, porque
  // o grafo é o mesmo.
  useEffect(() => {
    if (!grafo) return
    const atuais = new Map(nodesRef.current.map(n => [n.id, n.position]))
    setNodes(grafo.membros.map(m => {
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
    }))
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
      if (travado || depsIndisponiveis) return
      const origem = conn.source   // depende_de
      const alvo = conn.target     // pipeline_name (o dependente)
      if (!origem || !alvo) return
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
    },
    [travado, depsIndisponiveis, criarDep],
  )

  // ── Excluir dependência (Delete/botão + confirmação) ──────────────────────
  // Nó NÃO se exclui aqui: tirar um pipeline da malha é papel do modal Membros
  // (e excluir uma aresta é outra coisa — apaga a dependência REAL).
  const handleBeforeDelete = useCallback(
    async ({ nodes: toDel, edges: toDelEdges }: { nodes: Node[]; edges: Edge[] }) => {
      if (travado) return false
      if (toDel.length > 0) {
        toast.info('Para retirar um pipeline da malha use o modal Membros — aqui o Delete só remove dependências (arestas).')
        return false
      }
      if (toDelEdges.length > 0) {
        setDelEdges(toDelEdges)
        return false   // cancela o delete nativo; a confirmação decide
      }
      return true
    },
    [travado],
  )

  const selEdges = useMemo(() => edges.filter(e => e.selected), [edges])

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
            posicoes: nodesRef.current.map(n => ({
              pipeline_name: n.id,
              layout_x: Math.round(n.position.x),
              layout_y: Math.round(n.position.y),
            })),
          }),
        }),
    onSuccess: (r) => {
      toast.success(`Posições salvas (${r.atualizados} pipeline${r.atualizados !== 1 ? 's' : ''}).`)
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
            Membros da F7 — sem duplicar o caminho). */}
        {!readOnly && !emExecucao && (
          <div className="flex w-60 shrink-0 flex-col gap-2 border-r border-edge bg-panel p-3">
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
            colorMode={colorMode}
            fitView
            fitViewOptions={{ padding: 0.25 }}
            proOptions={{ hideAttribution: true }}
            defaultEdgeOptions={{ type: 'smoothstep' }}
            nodesDraggable={!travado}
            nodesConnectable={!travado && !depsIndisponiveis}
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
                  {selEdges.length > 0 && (
                    <Button
                      variant="danger"
                      size="sm"
                      onClick={() => setDelEdges(selEdges)}
                      title="Excluir a(s) dependência(s) selecionada(s) — apaga a dependência real"
                    >
                      <Trash2 size={13} /> Excluir dependência
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
    </div>
  )
}
