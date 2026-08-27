import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { RefreshCw, Search, X, ExternalLink } from 'lucide-react'
import { apiFetch } from '../lib/api'
import type { Chamado } from '../lib/chamado'
import { isINCAtivo } from '../lib/chamado'
import { ChamadoDetalheModal } from '../components/ChamadoDetalheModal'
import { Spinner } from '../components/ui/Spinner'
import { Modal } from '../components/ui/Modal'

// ── Constantes ────────────────────────────────────────────────────────────────

const COLUNA_LABEL: Record<string, string> = {
  novo: 'Em aberto', andamento: 'Em andamento',
  aguardando: 'Aguardando', resolvido: 'Resolvido', outros: 'Outros',
}

const TIPO_LABEL: Record<string, string> = {
  incident: 'Incidente', ritm: 'RITM', task: 'Tarefa', change: 'Mudança',
}

const VEREDITO_STYLE: Record<string, { classe: string; curto: string }> = {
  'PODE INICIAR': {
    classe: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300',
    curto: 'pode iniciar',
  },
  'RETORNAR AO SOLICITANTE': {
    classe: 'bg-amber-100 text-amber-800 dark:bg-amber-950/60 dark:text-amber-300',
    curto: 'retornar',
  },
}

const IDADE_THRESHOLDS = [
  { min: 7, classe: 'text-red-600 dark:text-red-400 font-semibold', rotulo: 'parado' },
  { min: 3, classe: 'text-amber-600 dark:text-yellow-400 font-medium', rotulo: 'atenção' },
]

function idadeStyle(dias: number | null) {
  if (dias === null) return { classe: 'text-[#94a3b8]', rotulo: '' }
  for (const t of IDADE_THRESHOLDS) if (dias > t.min) return { classe: t.classe, rotulo: t.rotulo }
  return { classe: 'text-[#94a3b8]', rotulo: '' }
}

function idadeTitle(dias: number | null): string {
  if (dias === null) return 'sem data de abertura'
  if (dias <= 0) return 'aberto hoje'
  if (dias === 1) return 'aberto há 1 dia'
  return `parado há ${dias} dias`
}

// ── Tipos ─────────────────────────────────────────────────────────────────────

interface SyncStatus {
  status: string
  idade_minutos?: number
  atrasado?: boolean
  em_andamento?: boolean
  erro?: string | null
}

interface ChamadosResponse {
  chamados: Chamado[]
  colunas: string[]
  total: number
  ultimo_sync: SyncStatus | null
  alerta_fila_vazia?: string | null
  migration_ausente?: boolean
  derivacoes_pendentes?: boolean
}

interface TaskRitm {
  sys_id: string
  numero: string
  titulo: string | null
  estado_kanban: string
  url?: string | null
  ativo: boolean
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function syncStatusDisplay(s: SyncStatus | null) {
  if (!s) return { texto: 'nunca sincronizado', tom: 'warning' }
  if (s.em_andamento) return { texto: 'sincronização em andamento', tom: 'info' }
  const t = s.idade_minutos ?? 0
  const n = t < 60 ? `sincronizado há ${t} min` : `sincronizado há ${Math.floor(t / 60)}h`
  if (s.status === 'OK') return { texto: n, tom: s.atrasado ? 'warning' : 'success' }
  return { texto: `${n} — com erro`, tom: 'error' }
}

function filtroBusca(c: Chamado, q: string): boolean {
  const lq = q.trim().toLowerCase()
  if (!lq) return true
  return [c.numero, c.titulo, c.atribuido_a, c.estado_origem].some(
    f => (f ?? '').toLowerCase().includes(lq)
  )
}

// ── Subcomponentes ────────────────────────────────────────────────────────────

function AlertaBanner({ tom, children }: { tom: string; children: React.ReactNode }) {
  const cores: Record<string, string> = {
    error: 'border-red-700 bg-red-900/20 text-red-300',
    warning: 'border-amber-700 bg-amber-900/20 text-amber-300',
    info: 'border-blue-700 bg-blue-900/20 text-blue-300',
    success: 'border-green-700 bg-green-900/20 text-green-300',
  }
  return (
    <div className={`rounded-md border px-3 py-2 text-xs ${cores[tom] ?? cores.info}`}>
      {children}
    </div>
  )
}

function BadgeNeutro({ children }: { children: React.ReactNode }) {
  return (
    <span className="px-1.5 py-0.5 rounded text-[10px] bg-[#1a1d27] border border-[#2a2d3a] text-[#94a3b8]">
      {children}
    </span>
  )
}

function BadgeINC() {
  return (
    <span className="px-1.5 py-0.5 rounded text-[10px] bg-red-100 text-red-700 dark:bg-red-950/60 dark:text-red-300 font-semibold">
      INC
    </span>
  )
}

function KanbanCard({
  c,
  onOpenDetalhe,
  onOpenVeredito,
}: {
  c: Chamado
  onOpenDetalhe: (sysId: string) => void
  onOpenVeredito: (c: Chamado) => void
}) {
  const inc = isINCAtivo(c)
  const vStyle = c.veredito ? VEREDITO_STYLE[c.veredito] : undefined
  const iStyle = idadeStyle(c.idade_dias ?? null)

  const { data: tasksData } = useQuery<{ tasks: TaskRitm[] }>({
    queryKey: ['tasks', c.sys_id],
    queryFn: () => apiFetch(`/chamados/${c.sys_id}/tasks`),
    enabled: c.tipo === 'ritm',
    staleTime: 60_000,
  })
  const tasks = (tasksData?.tasks ?? []).filter(t => t.ativo)

  return (
    <div
      className={[
        'bg-[#12141e] border border-[#2a2d3a] rounded-md p-2.5 flex flex-col gap-1.5 shadow-sm',
        inc ? 'border-l-4 border-l-red-500' : '',
      ].join(' ')}
    >
      <div className="flex items-center justify-between gap-2">
        <button
          type="button"
          onClick={() => onOpenDetalhe(c.sys_id)}
          className="font-mono text-xs font-semibold text-[#e2e8f0] hover:text-blue-400 transition-colors text-left"
          title="Ver detalhes"
        >
          {c.numero}
        </button>
        {c.url && (
          <a
            href={c.url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-blue-600 dark:text-blue-400 shrink-0"
            title="Abrir no ServiceNow"
          >
            <ExternalLink size={12} />
          </a>
        )}
      </div>

      <button
        type="button"
        onClick={() => onOpenDetalhe(c.sys_id)}
        className="text-xs text-[#e2e8f0] leading-snug text-left hover:text-blue-400 transition-colors"
      >
        {c.titulo ?? '(sem título)'}
      </button>

      <div className="flex flex-wrap items-center gap-1">
        <BadgeNeutro>{TIPO_LABEL[c.tipo] ?? c.tipo}</BadgeNeutro>
        {inc && <BadgeINC />}
        {c.prioridade && <BadgeNeutro>{c.prioridade}</BadgeNeutro>}
        {c.estado_origem && (
          <span className="text-[10px] text-[#64748b]" title={`Estado na origem: ${c.estado_origem}`}>
            {c.estado_origem}
          </span>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-1 text-[10px]">
        {c.tipo_demanda && (
          <span
            className="px-1.5 py-0.5 rounded bg-[#1a1d27] border border-[#2a2d3a] text-[#94a3b8]"
            title={`Tipo deduzido${c.catalogo ? ` · catálogo: ${c.catalogo}` : ''}`}
          >
            {c.tipo_demanda}
          </span>
        )}
        {c.categoria_diaadia === 'dia a dia' && (
          <span className="px-1.5 py-0.5 rounded bg-blue-500/10 border border-blue-500/30 text-blue-400">
            dia a dia
          </span>
        )}
        {c.categoria_diaadia === 'iniciativa' && (
          <span className="px-1.5 py-0.5 rounded bg-purple-500/10 border border-purple-500/30 text-purple-400">
            iniciativa
          </span>
        )}
        {c.objetos && (
          <span className="font-mono text-[#94a3b8] truncate max-w-full" title={`Objetos: ${c.objetos}`}>
            {c.objetos}
          </span>
        )}
        {c.sla_vencido && (
          <span className="px-1.5 py-0.5 rounded bg-red-100 dark:bg-red-950/60 text-red-700 dark:text-red-300">
            SLA vencido
          </span>
        )}
        {vStyle && (
          <button
            type="button"
            onClick={() => onOpenVeredito(c)}
            className={`px-1.5 py-0.5 rounded ${vStyle.classe}`}
            title={c.triagem_origem === 'heuristica' ? 'Veredito por regra de texto — clique para ver' : 'Veredito IA — clique para ver'}
          >
            {vStyle.curto}
            {c.triagem_origem === 'heuristica' && <span aria-hidden> ~</span>}
          </button>
        )}
      </div>

      {tasks.length > 0 && (
        <div className="mt-1 border-t border-[#2a2d3a]/50 pt-1.5 flex flex-col gap-1">
          <span className="text-[10px] text-[#64748b] uppercase tracking-wide">Tasks ({tasks.length})</span>
          {tasks.map(tk => (
            <div key={tk.sys_id} className="flex items-start justify-between gap-1 bg-[#1a1d27] rounded px-1.5 py-1">
              <div className="flex flex-col gap-0.5 min-w-0">
                <span className="font-mono text-[10px] text-blue-500">
                  {tk.url
                    ? <a href={tk.url} target="_blank" rel="noopener noreferrer">{tk.numero}</a>
                    : tk.numero
                  }
                </span>
                <span className="text-[10px] text-[#e2e8f0] leading-snug truncate" title={tk.titulo ?? undefined}>
                  {tk.titulo ?? '(sem título)'}
                </span>
              </div>
              <span className="text-[10px] text-[#94a3b8] shrink-0 ml-1">{tk.estado_kanban}</span>
            </div>
          ))}
        </div>
      )}

      <div className="flex items-center justify-between gap-2 text-[11px] text-[#94a3b8]">
        <span
          className="truncate"
          title={c.demandante
            ? `Responsável: ${c.atribuido_a ?? 'sem responsável'} · Demandante: ${c.demandante}`
            : c.atribuido_a ?? 'sem responsável'
          }
        >
          {c.atribuido_a ?? 'sem responsável'}
        </span>
        <span
          title={idadeTitle(c.idade_dias ?? null)}
          className={`shrink-0 flex items-center gap-1 ${iStyle.classe}`}
        >
          {iStyle.rotulo && <span className="uppercase tracking-wide text-[9px]">{iStyle.rotulo}</span>}
          {c.idade_dias === null ? '—' : `${c.idade_dias}d`}
        </span>
      </div>
    </div>
  )
}

// ── Aba Indicadores ───────────────────────────────────────────────────────────

function AbaIndicadores() {
  const responsavel = ''
  const { data, isLoading, isError, error } = useQuery<any>({
    queryKey: ['chamados-indicadores', responsavel],
    queryFn: () => apiFetch(responsavel
      ? `/chamados/indicadores?responsavel=${encodeURIComponent(responsavel)}`
      : '/chamados/indicadores'
    ),
    staleTime: 0,
  })

  if (isLoading) return <div className="flex justify-center py-10"><Spinner /></div>
  if (isError) return (
    <AlertaBanner tom="error">
      Erro ao carregar indicadores: {(error as Error).message}
    </AlertaBanner>
  )

  const d = data ?? {}
  return (
    <div className="flex flex-col gap-4">
      {d.analistas && d.analistas.length > 0 && (
        <div className="flex flex-col gap-2">
          <h2 className="text-xs font-semibold text-[#94a3b8] uppercase tracking-wider">Por analista</h2>
          <div className="overflow-x-auto rounded-lg border border-[#2a2d3a]">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-[#2a2d3a] text-[#94a3b8]">
                  <th className="text-left px-3 py-2">Analista</th>
                  <th className="text-right px-3 py-2">Ativos</th>
                  <th className="text-right px-3 py-2">SLA vencidos</th>
                  <th className="text-right px-3 py-2">Idade média</th>
                </tr>
              </thead>
              <tbody>
                {d.analistas.map((a: any) => (
                  <tr key={a.atribuido_a_email} className="border-b border-[#2a2d3a] last:border-0">
                    <td className="px-3 py-2 text-[#e2e8f0]">{a.atribuido_a}</td>
                    <td className="px-3 py-2 text-right">{a.total_ativos}</td>
                    <td className="px-3 py-2 text-right">{a.sla_vencidos}</td>
                    <td className="px-3 py-2 text-right">{a.idade_media_dias ?? '—'}d</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
      {(!d.analistas || d.analistas.length === 0) && (
        <p className="text-sm text-[#64748b]">Sem dados de indicadores disponíveis.</p>
      )}
    </div>
  )
}

// ── Aba Dashboard ─────────────────────────────────────────────────────────────

function AbaDashboard() {
  const { data, isLoading, isError, error } = useQuery<any>({
    queryKey: ['chamados-dashboard', 'geral'],
    queryFn: () => apiFetch('/chamados/dashboard?visao=geral'),
    staleTime: 0,
  })

  if (isLoading) return <div className="flex justify-center py-10"><Spinner /></div>
  if (isError) return (
    <AlertaBanner tom="error">
      Erro ao carregar dashboard: {(error as Error).message}
    </AlertaBanner>
  )

  const d = data ?? {}
  const metricas = [
    { label: 'Backlog', valor: d.backlog, desc: 'abertos há +14 dias' },
    { label: 'Abertas hoje', valor: d.abertas, desc: 'chamados abertos hoje' },
    { label: 'Em andamento', valor: d.andamento, desc: 'em análise' },
    { label: 'Sem analista', valor: d.sem_analista, desc: 'sem responsável' },
  ].filter(m => m.valor !== undefined)

  return (
    <div className="flex flex-col gap-4">
      {metricas.length > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {metricas.map(m => (
            <div key={m.label} className="rounded-lg border border-[#2a2d3a] bg-[#12141e] p-3">
              <div className="text-2xl font-bold text-[#e2e8f0]">{m.valor ?? '—'}</div>
              <div className="text-xs font-medium text-[#94a3b8] mt-0.5">{m.label}</div>
              <div className="text-[10px] text-[#64748b]">{m.desc}</div>
            </div>
          ))}
        </div>
      )}
      {metricas.length === 0 && (
        <p className="text-sm text-[#64748b]">Sem dados de dashboard disponíveis.</p>
      )}
    </div>
  )
}

// ── Modal de Veredito/Triagem ─────────────────────────────────────────────────

function TriagemModal({ c, onClose }: { c: Chamado; onClose: () => void }) {
  const heuristica = c.triagem_origem === 'heuristica'
  const { data: sugestoesData } = useQuery<any>({
    queryKey: ['chamados-sugestoes'],
    queryFn: () => apiFetch('/chamados/sugestoes'),
    staleTime: 300_000,
  })
  const sugestao = sugestoesData?.sugestoes?.find((s: any) => s.tipo_demanda === c.tipo_demanda)

  return (
    <Modal open onClose={onClose} title={`Triagem · ${c.numero}`} size="lg">
      <div className="flex flex-col gap-3 text-xs">
        <div className={`rounded-md px-3 py-2 ${heuristica ? 'bg-amber-50 dark:bg-amber-950/40 text-amber-900 dark:text-amber-200' : 'bg-[#1a1d27] text-[#e2e8f0]'}`}>
          {heuristica ? (
            <>
              <strong>Análise automática por regra de texto</strong> — a IA não respondeu, então este veredito vem de heurística.
              {c.triagem_erro && <span className="block text-[11px] mt-1">Motivo: {c.triagem_erro}</span>}
            </>
          ) : (
            <><strong>Análise por IA</strong>{c.triagem_em ? ` · ${c.triagem_em}` : ''}</>
          )}
        </div>
        {c.resumo && <p className="text-[#e2e8f0]">{c.resumo}</p>}
        {c.lacunas && c.lacunas.length > 0 && (
          <div>
            <h4 className="text-[11px] font-semibold text-[#94a3b8] uppercase tracking-wide">Lacunas identificadas</h4>
            <ul className="list-disc pl-4 text-[#e2e8f0]">
              {c.lacunas.map((l, i) => <li key={i}>{l}</li>)}
            </ul>
          </div>
        )}
        {c.perguntas && (
          <div>
            <div className="flex items-center justify-between gap-2">
              <h4 className="text-[11px] font-semibold text-[#94a3b8] uppercase tracking-wide">Perguntas sugeridas</h4>
              <button
                type="button"
                onClick={() => navigator.clipboard?.writeText(c.perguntas!)}
                className="text-[10px] px-2 py-0.5 rounded border border-[#2a2d3a] text-[#94a3b8] hover:text-[#e2e8f0]"
              >
                Copiar
              </button>
            </div>
            <pre className="whitespace-pre-wrap text-[#e2e8f0] font-sans">{c.perguntas}</pre>
          </div>
        )}
        {!c.resumo && (!c.lacunas || !c.lacunas.length) && !c.perguntas && (
          <p className="text-[#64748b]">Este chamado ainda não tem laudo de triagem.</p>
        )}
        {sugestao && sugestao.responsavel !== c.atribuido_a && (
          <p className="text-[11px] text-[#64748b] border-t border-[#2a2d3a] pt-2">
            Quem mais resolveu &quot;{c.tipo_demanda}&quot; nos últimos {sugestoesData?.dias ?? 90} dias:{' '}
            <strong className="text-[#e2e8f0]">{sugestao.responsavel}</strong> ({sugestao.resolvidos}). É histórico, não atribuição.
          </p>
        )}
      </div>
    </Modal>
  )
}

// ── Componente principal ───────────────────────────────────────────────────────

export default function Chamados() {
  const { data: resp, isLoading, isError, error, refetch, isFetching } =
    useQuery<ChamadosResponse>({
      queryKey: ['chamados'],
      queryFn: () => apiFetch('/chamados'),
    })

  const { data: catData } = useQuery<{ sugestoes: { slug: string; label: string }[] }>({
    queryKey: ['sn-categorias'],
    queryFn: () => apiFetch('/chamados/categorias'),
    staleTime: 300_000,
  })

  const [aba, setAba] = useState<'fila' | 'indicadores' | 'dashboard'>('fila')
  const [busca, setBusca] = useState('')
  const [filtroTipo, setFiltroTipo] = useState('')
  const [filtroResponsavel, setFiltroResponsavel] = useState('')
  const [filtroPrioridade, setFiltroPrioridade] = useState('')
  const [filtroCategoria, setFiltroCategoria] = useState('')
  const [detalheAberto, setDetalheAberto] = useState<string | null>(null)
  const [veredtoAberto, setVeredtoAberto] = useState<Chamado | null>(null)

  const chamadosBase = useMemo(
    () => (resp?.chamados ?? []).filter(c => !(c.tipo === 'task' && c.pai_sys_id)),
    [resp]
  )

  const opcoes = useMemo(() => {
    const uniq = <T,>(arr: T[]) => [...new Set(arr)].sort()
    return {
      tipos: uniq(chamadosBase.map(c => c.tipo).filter(Boolean) as string[]),
      responsaveis: uniq(chamadosBase.map(c => c.atribuido_a).filter(Boolean) as string[]),
      prioridades: uniq(chamadosBase.map(c => c.prioridade).filter(Boolean) as string[]),
    }
  }, [chamadosBase])

  const chamadosFiltrados = useMemo(() => chamadosBase.filter(c =>
    (!filtroTipo || c.tipo === filtroTipo) &&
    (!filtroResponsavel || (filtroResponsavel === '__sem__' ? !c.atribuido_a : c.atribuido_a === filtroResponsavel)) &&
    (!filtroPrioridade || c.prioridade === filtroPrioridade) &&
    (!filtroCategoria || (filtroCategoria === 'sem marcacao' ? !c.categoria_diaadia : c.categoria_diaadia === filtroCategoria)) &&
    filtroBusca(c, busca)
  ), [chamadosBase, filtroTipo, filtroResponsavel, filtroPrioridade, filtroCategoria, busca])

  const temFiltro = !!(busca || filtroTipo || filtroResponsavel || filtroPrioridade || filtroCategoria)

  function limparFiltros() {
    setBusca(''); setFiltroTipo(''); setFiltroResponsavel(''); setFiltroPrioridade(''); setFiltroCategoria('')
  }

  const sync = syncStatusDisplay(resp?.ultimo_sync ?? null)

  const syncTomClass: Record<string, string> = {
    success: 'text-green-400', warning: 'text-amber-400', error: 'text-red-400', info: 'text-blue-400',
  }

  if (isLoading) return (
    <div className="flex justify-center py-20"><Spinner /></div>
  )
  if (isError) return (
    <div className="p-4">
      <AlertaBanner tom="error">
        Não foi possível carregar os chamados: {(error as Error).message}
      </AlertaBanner>
    </div>
  )

  const S = resp!

  return (
    <div className="p-4 flex flex-col gap-4">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <h1 className="text-lg font-semibold text-[#e2e8f0]">Chamados da Engenharia</h1>
          <span className="px-1.5 py-0.5 rounded text-[10px] bg-[#1a1d27] border border-[#2a2d3a] text-[#94a3b8]">
            {temFiltro ? `${chamadosFiltrados.length} de ${chamadosBase.length}` : `${chamadosBase.length} na fila`}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className={`text-xs ${syncTomClass[sync.tom] ?? 'text-[#94a3b8]'}`}>{sync.texto}</span>
          <button
            onClick={() => refetch()}
            disabled={isFetching}
            className="text-[#94a3b8] hover:text-[#e2e8f0] disabled:opacity-50"
            title="Recarregar"
          >
            <RefreshCw size={14} className={isFetching ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>

      <div className="flex border-b border-[#2a2d3a]">
        {(['fila', 'indicadores', 'dashboard'] as const).map(id => (
          <button
            key={id}
            onClick={() => setAba(id)}
            className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors whitespace-nowrap ${
              aba === id ? 'border-blue-500 text-blue-400' : 'border-transparent text-[#94a3b8] hover:text-[#e2e8f0]'
            }`}
          >
            {id === 'fila' ? 'Fila' : id === 'indicadores' ? 'Indicadores' : 'Dashboard'}
          </button>
        ))}
      </div>

      {S.migration_ausente && (
        <AlertaBanner tom="warning">
          Sistema em atualização — o espelho de chamados ainda não está disponível neste ambiente.
        </AlertaBanner>
      )}
      {S.ultimo_sync?.erro && (
        <AlertaBanner tom="warning">
          A última sincronização reportou erro: {S.ultimo_sync.erro} — a fila abaixo pode estar desatualizada.
        </AlertaBanner>
      )}
      {aba === 'fila' && S.alerta_fila_vazia && (
        <AlertaBanner tom={S.ultimo_sync?.status === 'OK' ? 'info' : 'warning'}>
          {S.alerta_fila_vazia}
        </AlertaBanner>
      )}
      {S.derivacoes_pendentes && (
        <AlertaBanner tom="warning">
          A fila está sendo servida, mas os campos de triagem e classificação ainda não existem no banco.
        </AlertaBanner>
      )}

      {aba === 'fila' && !S.migration_ausente && S.total > 0 && (
        <>
          <div className="bg-[#1a1d27] border border-[#2a2d3a] rounded-lg p-3 flex flex-wrap items-end gap-3">
            <div className="relative">
              <input
                value={busca}
                onChange={e => setBusca(e.target.value)}
                placeholder="número, título ou responsável"
                className="w-64 pl-7 pr-3 py-1.5 text-xs bg-[#12141e] border border-[#2a2d3a] rounded-md text-[#e2e8f0] placeholder-[#64748b] focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
              <Search size={13} className="absolute left-2 bottom-2 text-[#64748b] pointer-events-none" />
            </div>

            <div className="flex flex-col gap-0.5">
              <label className="text-[10px] text-[#94a3b8]">Tipo</label>
              <select value={filtroTipo} onChange={e => setFiltroTipo(e.target.value)}
                className="w-40 text-xs bg-[#12141e] border border-[#2a2d3a] rounded-md px-2 py-1.5 text-[#e2e8f0] focus:outline-none">
                <option value="">todos</option>
                {opcoes.tipos.map(t => <option key={t} value={t}>{TIPO_LABEL[t] ?? t}</option>)}
              </select>
            </div>

            <div className="flex flex-col gap-0.5">
              <label className="text-[10px] text-[#94a3b8]">Categoria</label>
              <select value={filtroCategoria} onChange={e => setFiltroCategoria(e.target.value)}
                className="w-44 text-xs bg-[#12141e] border border-[#2a2d3a] rounded-md px-2 py-1.5 text-[#e2e8f0] focus:outline-none">
                <option value="">todas</option>
                {(catData?.sugestoes ?? []).map((c: any) => <option key={c.slug} value={c.slug}>{c.label}</option>)}
                <option value="sem marcacao">Sem marcação</option>
              </select>
            </div>

            <div className="flex flex-col gap-0.5">
              <label className="text-[10px] text-[#94a3b8]">Responsável</label>
              <select value={filtroResponsavel} onChange={e => setFiltroResponsavel(e.target.value)}
                className="w-52 text-xs bg-[#12141e] border border-[#2a2d3a] rounded-md px-2 py-1.5 text-[#e2e8f0] focus:outline-none">
                <option value="">todos</option>
                <option value="__sem__">⚠ Sem responsável</option>
                {opcoes.responsaveis.map(r => <option key={r} value={r}>{r}</option>)}
              </select>
            </div>

            <div className="flex flex-col gap-0.5">
              <label className="text-[10px] text-[#94a3b8]">Prioridade</label>
              <select value={filtroPrioridade} onChange={e => setFiltroPrioridade(e.target.value)}
                className="w-44 text-xs bg-[#12141e] border border-[#2a2d3a] rounded-md px-2 py-1.5 text-[#e2e8f0] focus:outline-none">
                <option value="">todas</option>
                {opcoes.prioridades.map(p => <option key={p} value={p}>{p}</option>)}
              </select>
            </div>

            {temFiltro && (
              <button type="button" onClick={limparFiltros}
                className="flex items-center gap-1 text-xs text-[#94a3b8] hover:text-[#e2e8f0] px-2 py-1.5">
                <X size={13} /> Limpar
              </button>
            )}
          </div>

          {temFiltro && chamadosFiltrados.length === 0 && S.total > 0 && (
            <AlertaBanner tom="info">
              Nenhum chamado casa com os filtros atuais — a fila tem {S.total} chamado(s). Limpe os filtros para vê-la inteira.
            </AlertaBanner>
          )}

          <div className="grid gap-3 grid-cols-1 sm:grid-cols-2 xl:grid-cols-5">
            {S.colunas.map(coluna => {
              const cards = chamadosFiltrados.filter(c => c.estado_kanban === coluna)
              return (
                <div key={coluna} className="flex flex-col gap-2 min-w-0">
                  <div className="flex items-center justify-between px-1">
                    <h2 className="text-xs font-semibold text-[#94a3b8] uppercase tracking-wider">
                      {COLUNA_LABEL[coluna] ?? coluna}
                    </h2>
                    <span className="text-xs text-[#94a3b8]">{cards.length}</span>
                  </div>
                  <div className="flex flex-col gap-2">
                    {cards.length === 0
                      ? <p className="text-[11px] text-[#64748b] px-1 py-2">nenhum</p>
                      : cards.map(c => (
                          <KanbanCard
                            key={c.sys_id}
                            c={c}
                            onOpenDetalhe={sysId => setDetalheAberto(sysId)}
                            onOpenVeredito={c => setVeredtoAberto(c)}
                          />
                        ))
                    }
                  </div>
                </div>
              )
            })}
          </div>
        </>
      )}

      {aba === 'dashboard' && <AbaDashboard />}
      {aba === 'indicadores' && !S.migration_ausente && <AbaIndicadores />}

      {detalheAberto && (() => {
        const c = chamadosBase.find(x => x.sys_id === detalheAberto)
        return (
          <ChamadoDetalheModal
            sysId={detalheAberto}
            numero={c?.numero ?? detalheAberto}
            onClose={() => setDetalheAberto(null)}
          />
        )
      })()}
      {veredtoAberto && (
        <TriagemModal c={veredtoAberto} onClose={() => setVeredtoAberto(null)} />
      )}
    </div>
  )
}
