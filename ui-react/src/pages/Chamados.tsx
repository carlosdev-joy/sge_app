import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { ExternalLink, RefreshCw, AlertTriangle, Inbox, Clock } from 'lucide-react'
import { apiFetch } from '../lib/api'
import { Input } from '../components/ui/Input'

// ── Tipos ────────────────────────────────────────────────────────────────────

interface Chamado {
  sys_id: string
  numero: string
  tipo: string
  titulo: string
  estado_origem: string
  estado_kanban: string
  prioridade: string
  atribuido_a: string
  grupo: string
  aberto_em: string
  atualizado_em: string
  url: string
  idade_dias: number | null
}

interface Frescor {
  texto: string
  alerta: boolean
  horas: number | null
}

interface ChamadosResp {
  degradado: boolean
  motivo?: string
  frescor: Frescor | null
  sync_status: string | null
  sync_erro: string | null
  total: number
  contagem: Record<string, number>
  chamados: Chamado[]
}

// ── Constantes ───────────────────────────────────────────────────────────────

const COLUNAS: { key: string; label: string }[] = [
  { key: 'novo',       label: 'Novo' },
  { key: 'andamento',  label: 'Em andamento' },
  { key: 'aguardando', label: 'Aguardando' },
  { key: 'resolvido',  label: 'Resolvido' },
  { key: 'outros',     label: 'Outros' },
]

const TIPO_LABEL: Record<string, string> = {
  incident: 'INC',
  ritm:     'RITM',
  task:     'TASK',
  change:   'CHG',
}

const TIPO_COR: Record<string, string> = {
  incident: 'bg-red-100 text-red-700 border border-red-300 dark:bg-red-900/40 dark:text-red-300 dark:border-red-800',
  ritm:     'bg-blue-100 text-blue-700 border border-blue-300 dark:bg-blue-900/40 dark:text-blue-300 dark:border-blue-800',
  task:     'bg-purple-100 text-purple-700 border border-purple-300 dark:bg-purple-900/40 dark:text-purple-300 dark:border-purple-800',
  change:   'bg-amber-100 text-amber-700 border border-amber-300 dark:bg-amber-900/40 dark:text-amber-300 dark:border-amber-800',
}

const PRIORIDADE_COR: Record<string, string> = {
  '1 - Critical': 'text-red-700 dark:text-red-400',
  '2 - High':     'text-orange-600 dark:text-orange-400',
  '3 - Moderate': 'text-amber-600 dark:text-amber-400',
  '4 - Low':      'text-green-700 dark:text-green-400',
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function idadeCor(dias: number | null): string {
  if (dias === null) return 'text-dim'
  if (dias > 7) return 'text-red-700 dark:text-red-400'
  if (dias > 3) return 'text-amber-600 dark:text-amber-400'
  return 'text-dim'
}

function idadeLabel(dias: number | null): string {
  if (dias === null) return '—'
  if (dias === 0) return 'hoje'
  if (dias === 1) return '1d'
  return `${dias}d`
}

// ── Card do chamado ───────────────────────────────────────────────────────────

function CardChamado({ c }: { c: Chamado }) {
  const tipoCor  = TIPO_COR[c.tipo] ?? 'bg-gray-100 text-gray-700 border border-gray-300 dark:bg-gray-800 dark:text-gray-300 dark:border-gray-700'
  const priCor   = PRIORIDADE_COR[c.prioridade] ?? 'text-dim'
  const iCor     = idadeCor(c.idade_dias)
  const iLabel   = idadeLabel(c.idade_dias)
  const titleAttr = [
    c.titulo,
    c.estado_origem ? `Estado: ${c.estado_origem}` : '',
    c.idade_dias !== null ? `Aberto há ${c.idade_dias} dia(s)` : '',
  ].filter(Boolean).join('\n')

  return (
    <div
      className="bg-panel border border-edge rounded-lg p-3 space-y-1.5 hover:border-blue-400 dark:hover:border-blue-600 transition-colors"
      title={titleAttr}
    >
      {/* linha 1: badge tipo + número + link */}
      <div className="flex items-center gap-1.5">
        <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded ${tipoCor}`}>
          {TIPO_LABEL[c.tipo] ?? c.tipo.toUpperCase()}
        </span>
        <span className="text-xs font-mono text-ink font-medium truncate flex-1">{c.numero}</span>
        {c.url && (
          <a
            href={c.url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-dim hover:text-blue-600 dark:hover:text-blue-400 shrink-0"
            title="Abrir no ServiceNow"
            onClick={e => e.stopPropagation()}
          >
            <ExternalLink size={12} />
          </a>
        )}
      </div>

      {/* linha 2: título */}
      <p className="text-xs text-ink leading-snug line-clamp-2">
        {c.titulo || <span className="text-dim italic">sem título</span>}
      </p>

      {/* linha 3: responsável + prioridade + idade */}
      <div className="flex items-center gap-2 flex-wrap">
        {c.atribuido_a && (
          <span className="text-[11px] text-dim truncate max-w-[140px]" title={c.atribuido_a}>
            {c.atribuido_a}
          </span>
        )}
        {c.prioridade && (
          <span className={`text-[11px] font-medium ${priCor}`}>{c.prioridade}</span>
        )}
        <span className={`ml-auto text-[11px] font-medium ${iCor}`} title={`Aberto há ${c.idade_dias ?? '?'} dia(s)`}>
          <Clock size={10} className="inline mr-0.5" />
          {iLabel}
        </span>
      </div>
    </div>
  )
}

// ── Coluna do kanban ──────────────────────────────────────────────────────────

function ColunaKanban({ col, chamados }: { col: { key: string; label: string }; chamados: Chamado[] }) {
  return (
    <div className="flex flex-col min-w-[220px] max-w-[280px] flex-1">
      <div className="flex items-center justify-between mb-2 px-1">
        <span className="text-xs font-semibold text-ink uppercase tracking-wide">{col.label}</span>
        <span className="text-xs bg-edge text-dim px-1.5 py-0.5 rounded-full">{chamados.length}</span>
      </div>
      <div className="flex flex-col gap-2 overflow-y-auto pr-1" style={{ maxHeight: 'calc(100vh - 220px)' }}>
        {chamados.length === 0 ? (
          <div className="text-center text-dim text-xs py-6 border border-dashed border-edge rounded-lg">
            vazio
          </div>
        ) : (
          chamados.map(c => <CardChamado key={c.sys_id} c={c} />)
        )}
      </div>
    </div>
  )
}

// ── Página principal ──────────────────────────────────────────────────────────

export default function Chamados() {
  const [filtroTipo,   setFiltroTipo]   = useState('')
  const [filtroPri,    setFiltroPri]    = useState('')
  const [filtroResp,   setFiltroResp]   = useState('')
  const [busca,        setBusca]        = useState('')

  const params = new URLSearchParams()
  if (filtroTipo) params.set('tipo', filtroTipo)
  if (filtroPri)  params.set('prioridade', filtroPri)
  if (filtroResp) params.set('atribuido_a', filtroResp)
  if (busca)      params.set('q', busca)
  const qs = params.toString()

  const { data, isLoading, isError, error, refetch, isFetching } = useQuery<ChamadosResp>({
    queryKey: ['chamados', qs],
    queryFn:  () => apiFetch<ChamadosResp>(`/chamados${qs ? `?${qs}` : ''}`),
    refetchInterval: 5 * 60 * 1000, // atualiza a cada 5min
  })

  // ── Estado degradado (migration ausente) ──────────────────────────────
  if (data?.degradado) {
    return (
      <div className="p-8 flex flex-col items-center gap-3 text-dim">
        <AlertTriangle size={32} className="text-amber-500" />
        <p className="text-sm font-medium text-ink">Sistema em atualização</p>
        <p className="text-xs">{data.motivo}</p>
      </div>
    )
  }

  // ── Agrupar por coluna ────────────────────────────────────────────────
  const porColuna: Record<string, Chamado[]> = {}
  COLUNAS.forEach(c => { porColuna[c.key] = [] })
  ;(data?.chamados ?? []).forEach(ch => {
    const col = ch.estado_kanban in porColuna ? ch.estado_kanban : 'outros'
    porColuna[col].push(ch)
  })

  const frescor = data?.frescor

  return (
    <div className="flex flex-col h-full">
      {/* ── Cabeçalho ────────────────────────────────────────────────── */}
      <div className="shrink-0 px-4 pt-4 pb-3 border-b border-edge space-y-3">
        <div className="flex items-center gap-3 flex-wrap">
          <h1 className="text-base font-semibold text-ink">Chamados da Engenharia</h1>

          {/* frescor */}
          {frescor && (
            <span className={`flex items-center gap-1 text-xs px-2 py-0.5 rounded-full border ${
              frescor.alerta
                ? 'bg-amber-50 text-amber-700 border-amber-300 dark:bg-amber-900/20 dark:text-amber-300 dark:border-amber-800'
                : 'bg-green-50 text-green-700 border-green-200 dark:bg-green-900/20 dark:text-green-300 dark:border-green-800'
            }`}>
              <Clock size={11} />
              {frescor.texto}
            </span>
          )}

          {/* erro de sync */}
          {data?.sync_status === 'ERRO' && (
            <span className="flex items-center gap-1 text-xs px-2 py-0.5 rounded-full bg-red-50 text-red-700 border border-red-200 dark:bg-red-900/20 dark:text-red-300 dark:border-red-800"
              title={data.sync_erro ?? ''}>
              <AlertTriangle size={11} />
              último sync com erro
            </span>
          )}

          <button
            onClick={() => refetch()}
            disabled={isFetching}
            className="ml-auto text-dim hover:text-ink transition-colors"
            title="Atualizar"
          >
            <RefreshCw size={15} className={isFetching ? 'animate-spin' : ''} />
          </button>
        </div>

        {/* filtros */}
        <div className="flex gap-2 flex-wrap">
          <select
            value={filtroTipo}
            onChange={e => setFiltroTipo(e.target.value)}
            className="text-xs border border-edge rounded px-2 py-1 bg-panel text-ink"
          >
            <option value="">Todos os tipos</option>
            <option value="incident">Incidente</option>
            <option value="ritm">RITM</option>
            <option value="task">Task</option>
            <option value="change">Mudança</option>
          </select>

          <select
            value={filtroPri}
            onChange={e => setFiltroPri(e.target.value)}
            className="text-xs border border-edge rounded px-2 py-1 bg-panel text-ink"
          >
            <option value="">Todas as prioridades</option>
            <option value="1 - Critical">1 - Critical</option>
            <option value="2 - High">2 - High</option>
            <option value="3 - Moderate">3 - Moderate</option>
            <option value="4 - Low">4 - Low</option>
          </select>

          <Input
            placeholder="Responsável..."
            value={filtroResp}
            onChange={e => setFiltroResp(e.target.value)}
            className="text-xs h-7 w-40"
          />

          <Input
            placeholder="Buscar número ou título..."
            value={busca}
            onChange={e => setBusca(e.target.value)}
            className="text-xs h-7 w-52"
          />

          {(filtroTipo || filtroPri || filtroResp || busca) && (
            <button
              onClick={() => { setFiltroTipo(''); setFiltroPri(''); setFiltroResp(''); setBusca('') }}
              className="text-xs text-dim hover:text-ink underline"
            >
              limpar filtros
            </button>
          )}

          <span className="ml-auto text-xs text-dim self-center">
            {data?.total ?? 0} chamado(s)
          </span>
        </div>
      </div>

      {/* ── Corpo ────────────────────────────────────────────────────── */}
      <div className="flex-1 overflow-auto p-4">
        {isLoading && (
          <div className="flex items-center justify-center h-40 text-dim text-sm">
            Carregando chamados...
          </div>
        )}

        {isError && (
          <div className="flex flex-col items-center gap-2 h-40 justify-center text-sm">
            <AlertTriangle size={24} className="text-red-500" />
            <span className="text-red-700 dark:text-red-400">
              {(error as Error)?.message ?? 'Erro ao carregar chamados'}
            </span>
          </div>
        )}

        {!isLoading && !isError && data && data.total === 0 && (
          <div className="flex flex-col items-center gap-3 h-40 justify-center text-dim text-sm">
            <Inbox size={32} />
            <span>Nenhum chamado encontrado</span>
            {!frescor && <span className="text-xs">O sync ainda não foi executado. Configure o ServiceNow no Admin.</span>}
          </div>
        )}

        {!isLoading && !isError && data && data.total > 0 && (
          <div className="flex gap-4 min-w-max">
            {COLUNAS.map(col => (
              <ColunaKanban key={col.key} col={col} chamados={porColuna[col.key]} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
