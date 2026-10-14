import { useCallback, useEffect, useId, useMemo, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, CheckCircle2, ChevronDown, ChevronLeft, ChevronRight, Circle, Pencil, Plus, PowerOff, RefreshCw, Search, SlidersHorizontal, User } from 'lucide-react'
import { Button } from '../ui/Button'
import { Input, Select } from '../ui/Input'
import { DropdownMenu } from '../ui/DropdownMenu'
import { toast } from '../ui/Toast'
import { apiFetch, type ErroApi } from '../../lib/api'
import { workspaceApi } from '../../lib/workspaceApi'
import { workspacePath, type WorkspaceCapabilities } from '../../lib/workspace'
import { useAuthStore } from '../../store/auth'
import type { Pipeline } from '../../types/pipeline'
import {
 PIPELINE_INDEX_DEBOUNCE_MS, filtersFromSearch, filtersToSearch, hasActiveFilters, indexErrorMessage, legacyRecord, overviewRoute, pageSummary,
 pipelineChips, pipelineIndexQueryKey, pipelineMenu, pipelineTitle, resumeAction, updatedLabel, withFilter,
 type LegacyView, type PipelineChip, type PipelineIndexFilters, type PipelineIndexItem, type PipelineIndexState, type PipelineRoute,
} from '../../lib/pipelineIndex'
import { AuditModal, LineageModal, ViewModal } from './PipelineModals'

type Actions = WorkspaceCapabilities['actions']
// A lista é a grade no desktop e cada linha herda as colunas (subgrid): cabeçalho e
// linhas alinham mesmo com a coluna de ações de largura variável.
const GRID = 'lg:grid lg:gap-x-4 lg:grid-cols-[minmax(0,2.2fr)_minmax(0,2fr)_minmax(0,1.1fr)_minmax(0,1.1fr)_auto]'
const ROW = 'lg:col-span-full lg:grid-cols-subgrid'
const TONE: Record<PipelineChip['tone'], string> = {
 success: 'bg-green-50 text-green-800 border-green-200 dark:bg-green-900/30 dark:text-green-300 dark:border-green-800',
 info: 'bg-blue-50 text-blue-800 border-blue-200 dark:bg-blue-900/30 dark:text-blue-300 dark:border-blue-800',
 warning: 'bg-amber-50 text-amber-800 border-amber-200 dark:bg-amber-900/30 dark:text-amber-300 dark:border-amber-800',
 neutral: 'bg-canvas text-dim border-edge',
}
const ICON: Record<PipelineChip['key'], typeof Circle> = { published: CheckCircle2, unpublished: Circle, draft: Pencil, editing: User, inactive: PowerOff }
const STATE_OPTIONS: { value: PipelineIndexState; label: string }[] = [
 { value: 'all', label: 'Todos' }, { value: 'draft', label: 'Em desenvolvimento' }, { value: 'published', label: 'Publicados' },
 { value: 'editing', label: 'Em edição' }, { value: 'inactive', label: 'Inativos' },
]

// Lista única de entrada (F2): publicados e rascunhos ativos do índice .NET, filtros e páginas no servidor.
export function PipelineCatalog({ actions }: { actions: Actions }) {
 const navigate = useNavigate()
 const [params, setParams] = useSearchParams()
 const token = useAuthStore(s => s.token)
 const me = useAuthStore(s => s.user?.matricula ?? null)
 const filters = useMemo(() => filtersFromSearch(params), [params])
 // Texto digitado e o valor da URL em que se baseia: voltar/avançar ou limpar reescreve
 // o campo; o próprio commit não apara o que ainda se digita.
 const [typed, setTyped] = useState({ text: filters.search, base: filters.search })
 if (typed.base !== filters.search) setTyped({ text: typed.text.trim() === filters.search ? typed.text : filters.search, base: filters.search })
 const searchText = typed.text
 const setSearchText = (text: string) => setTyped(current => ({ ...current, text }))
 const [moreOpen, setMoreOpen] = useState(!!(filters.project || filters.domain))
 const [legacy, setLegacy] = useState<{ view: LegacyView; pipeline: Pipeline } | null>(null)
 const moreId = useId()

 const commit = useCallback((next: PipelineIndexFilters) => setParams(filtersToSearch(next, params), { replace: true }), [params, setParams])
 // Busca com debounce de 250 ms.
 useEffect(() => {
  const value = searchText.trim()
  if (value === filters.search) return
  const timer = setTimeout(() => commit(withFilter(filters, { search: value })), PIPELINE_INDEX_DEBOUNCE_MS)
  return () => clearTimeout(timer)
 }, [searchText, filters, commit])

 // Chave por sessão e filtros: trocar a chave cancela a leitura anterior (signal) e
 // resposta antiga nunca substitui a atual.
 const index = useQuery({ queryKey: pipelineIndexQueryKey(token, filters), queryFn: ({ signal }) => workspaceApi.pipelineIndex(filters, signal), placeholderData: previous => previous, staleTime: 15_000, retry: false })
 const catalogsOn = moreOpen || !!filters.project || !!filters.domain
 const projects = useQuery<{ projects: string[] }>({ queryKey: ['pipeline-projects'], queryFn: () => apiFetch('/pipelines/projects'), staleTime: 300_000, enabled: catalogsOn })
 const domains = useQuery<{ domains: string[] }>({ queryKey: ['pipeline-domains'], queryFn: () => apiFetch('/pipelines/domains'), staleTime: 300_000, enabled: catalogsOn })

 const go = (name: string, route: PipelineRoute) => navigate(workspacePath(name, route.tab, route.experience))
 async function openLegacy(view: LegacyView, item: PipelineIndexItem) {
  try {
   const rows = await apiFetch<{ data: Pipeline[] }>(`/pipelines?${new URLSearchParams({ limit: '100', filter_name: item.pipelineName })}`)
   const record = legacyRecord(rows.data, item.pipelineName)
   if (record) setLegacy({ view, pipeline: record })
   else toast.error('Cadastro publicado não encontrado para este pipeline.')
  } catch { toast.error('Não foi possível abrir o cadastro publicado agora.') } // a rota legada pode devolver detalhe interno
 }

 const page = index.data
 const summary = page ? pageSummary({ total: page.total, limit: page.limit, offset: page.offset, count: page.items.length }) : null
 const failure = indexErrorMessage(index.isError ? index.error as ErroApi : null)
 const extraFilters = (filters.project ? 1 : 0) + (filters.domain ? 1 : 0)
 const stale = index.isPlaceholderData || (index.isFetching && !index.isPending)

 return <div className="flex flex-col gap-4">
  <header className="flex flex-wrap items-end justify-between gap-3">
   <div className="min-w-0">
    <h1 className="ui-title text-ink">Pipelines</h1>
    <p className="text-sm text-dim mt-1">Publicados e em desenvolvimento numa única lista. Entre pelo nome ou continue a montagem de onde parou.</p>
   </div>
   <div className="flex flex-wrap items-center gap-3">
    <Link to={{ search: '?legado=1' }} className="text-sm text-dim hover:text-ink hover:underline underline-offset-2 rounded focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500">Lista clássica</Link>
    {actions.editDraft && <Button onClick={() => navigate('/pipelines/novo')}><Plus size={16} aria-hidden />Novo pipeline</Button>}
   </div>
  </header>

  <section aria-label="Busca e filtros" className="bg-panel border border-edge rounded-lg p-3 space-y-3">
   <div className="flex flex-wrap items-end gap-3">
    <div className="relative flex-1 min-w-0 basis-60">
     <Input label="Buscar" type="search" value={searchText} onChange={e => setSearchText(e.target.value)} placeholder="Nome ou identificador técnico" maxLength={200} className="w-full pl-8" autoComplete="off" />
     <Search size={14} aria-hidden className="absolute left-2.5 bottom-3 text-dim pointer-events-none" />
    </div>
    <div role="group" aria-label="Situação" className="flex flex-wrap gap-1">
     {STATE_OPTIONS.map(o => <button key={o.value} type="button" aria-pressed={filters.state === o.value} onClick={() => commit(withFilter(filters, { state: o.value }))}
      className={`ui-button px-3 py-1.5 rounded-md text-sm border transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 ${filters.state === o.value ? 'bg-blue-50 text-blue-800 border-blue-300 font-medium dark:bg-blue-900/30 dark:text-blue-300 dark:border-blue-700' : 'bg-panel text-dim border-edge hover:text-ink hover:bg-canvas'}`}>{o.label}</button>)}
    </div>
    <Button variant="secondary" aria-expanded={moreOpen} aria-controls={moreId} onClick={() => setMoreOpen(open => !open)}>
     <SlidersHorizontal size={14} aria-hidden />Filtros{extraFilters ? ` (${extraFilters})` : ''}
    </Button>
   </div>
   {moreOpen && <div id={moreId} className="flex flex-wrap items-end gap-3 border-t border-edge pt-3">
    <Select label="Projeto" value={filters.project} onChange={e => commit(withFilter(filters, { project: e.target.value }))} className="w-56">
     <option value="">Todos os projetos</option>
     {filters.project && !projects.data?.projects.includes(filters.project) && <option value={filters.project}>{filters.project}</option>}
     {projects.data?.projects.map(p => <option key={p} value={p}>{p}</option>)}
    </Select>
    <Select label="Domínio" value={filters.domain} onChange={e => commit(withFilter(filters, { domain: e.target.value }))} className="w-56">
     <option value="">Todos os domínios</option>
     {filters.domain && !domains.data?.domains.includes(filters.domain) && <option value={filters.domain}>{filters.domain}</option>}
     {domains.data?.domains.map(d => <option key={d} value={d}>{d}</option>)}
    </Select>
    {hasActiveFilters(filters) && <Button variant="ghost" onClick={() => { setSearchText(''); commit({ search: '', project: '', domain: '', state: 'all', page: 1 }) }}>Limpar filtros</Button>}
   </div>}
  </section>

  <p className="text-xs text-dim px-1 min-h-4" aria-live="polite">{index.isPending ? 'Carregando pipelines…' : summary ? `${summary.text}${stale ? ' · atualizando…' : ''}` : ''}</p>

  {failure.text && <div role="alert" className="flex flex-wrap items-start gap-3 rounded-lg border px-4 py-3 bg-red-50 border-red-200 text-red-800 dark:bg-red-900/20 dark:border-red-800 dark:text-red-300">
   <AlertTriangle size={16} aria-hidden className="mt-0.5 shrink-0" />
   <p className="text-sm flex-1 min-w-[200px]">{failure.text}</p>
   <div className="flex gap-2">
    <Button size="sm" variant="secondary" onClick={() => index.refetch()}><RefreshCw size={12} aria-hidden />Tentar novamente</Button>
    {failure.offerLegacy && <Button size="sm" variant="secondary" onClick={() => setParams({ legado: '1' })}>Usar lista clássica</Button>}
   </div>
  </div>}

  {page && page.items.length > 0 && <ul aria-busy={stale} aria-label="Pipelines" className={`bg-panel border border-edge rounded-lg divide-y divide-edge transition-opacity ${GRID} ${stale ? 'opacity-70' : ''}`}>
   <li aria-hidden className={`hidden lg:grid ${ROW} px-4 py-2 text-xs font-medium text-dim`}><span>Pipeline</span><span>Situação</span><span>Projeto e domínio</span><span>Atualização</span><span /></li>
   {page.items.map(item => <PipelineCatalogRow key={item.pipelineName} item={item} actions={actions} me={me} onRoute={route => go(item.pipelineName, route)} onLegacy={view => void openLegacy(view, item)} />)}
  </ul>}

  {page && page.items.length === 0 && !index.isError && <div className="bg-panel border border-edge rounded-lg py-14 px-6 flex flex-col items-center gap-2 text-center">
   {hasActiveFilters(filters) || filters.page > 1 ? <>
    <p className="text-sm font-medium text-ink">{filters.page > 1 && page.total > 0 ? 'Esta página não tem mais resultados.' : 'Nenhum pipeline corresponde a esta busca.'}</p>
    <div className="flex gap-2 mt-2">
     {filters.page > 1 && page.total > 0 && <Button variant="secondary" size="sm" onClick={() => commit({ ...filters, page: 1 })}>Ir para a primeira página</Button>}
     {hasActiveFilters(filters) && <Button variant="secondary" size="sm" onClick={() => { setSearchText(''); commit({ search: '', project: '', domain: '', state: 'all', page: 1 }) }}>Limpar filtros</Button>}
    </div>
   </> : <>
    <p className="text-sm font-medium text-ink">Nenhum pipeline cadastrado ainda.</p>
    {actions.editDraft && <Button size="sm" className="mt-2" onClick={() => navigate('/pipelines/novo')}><Plus size={14} aria-hidden />Novo pipeline</Button>}
   </>}
  </div>}

  {summary && (summary.hasPrevious || summary.hasNext) && <nav aria-label="Páginas da lista" className="flex items-center justify-between gap-3">
   <Button variant="secondary" size="sm" disabled={!summary.hasPrevious || index.isFetching} onClick={() => commit({ ...filters, page: filters.page - 1 })}><ChevronLeft size={14} aria-hidden />Anterior</Button>
   <span className="text-xs text-dim">Página {summary.current} de {summary.pages}</span>
   <Button variant="secondary" size="sm" disabled={!summary.hasNext || index.isFetching} onClick={() => commit({ ...filters, page: filters.page + 1 })}>Próxima<ChevronRight size={14} aria-hidden /></Button>
  </nav>}

  {legacy?.view === 'cadastro' && <ViewModal pipeline={legacy.pipeline} onClose={() => setLegacy(null)} />}
  {legacy?.view === 'lineage' && <LineageModal pipeline={legacy.pipeline} onClose={() => setLegacy(null)} />}
  {legacy?.view === 'historico' && <AuditModal pipeline={legacy.pipeline} onClose={() => setLegacy(null)} />}
 </div>
}

function PipelineCatalogRow({ item, actions, me, onRoute, onLegacy }: { item: PipelineIndexItem; actions: Actions; me: string | null; onRoute: (route: PipelineRoute) => void; onLegacy: (view: LegacyView) => void }) {
 const title = pipelineTitle(item)
 const overview = overviewRoute(actions)
 const resume = resumeAction(item, actions, me)
 const updated = updatedLabel(item)
 const menu = pipelineMenu(item, actions)
 return <li className={`relative grid gap-y-2 px-4 py-3 ${ROW} lg:items-center hover:bg-canvas/60 transition-colors`}>
  <div className="min-w-0">
   <Link to={workspacePath(item.pipelineName, overview.tab, overview.experience)} className="text-sm font-semibold text-ink hover:underline underline-offset-2 rounded break-words focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500">{title}</Link>
   {title !== item.pipelineName && <p className="font-mono text-xs text-dim break-all mt-0.5">{item.pipelineName}</p>}
  </div>
  <div className="flex flex-wrap gap-1.5 min-w-0">
   <span className="lg:sr-only text-xs text-dim w-full">Situação</span>
   {pipelineChips(item, me).map(chip => { const Icon = ICON[chip.key]; return <span key={chip.key} className={`inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-xs ${TONE[chip.tone]}`}><Icon size={12} aria-hidden />{chip.label}</span> })}
  </div>
  <div className="min-w-0 text-sm">
   <span className="lg:sr-only text-xs text-dim">Projeto e domínio: </span>
   {item.project || item.domain ? <><span className="text-ink break-words">{item.project ?? 'Sem projeto'}</span><span className="block text-xs text-dim break-words">{item.domain ?? 'Sem domínio'}</span></> : <span className="text-xs text-dim">Não definidos</span>}
  </div>
  <div className="min-w-0 text-xs text-dim">
   {updated && <span className="block">{updated}</span>}
   {item.responsible && <span className="block">Responsável: <span className="text-ink">{item.responsible}</span></span>}
  </div>
  <div className="flex items-center gap-2 lg:justify-end">
   {resume && <Button size="sm" onClick={() => onRoute(resume.route)}>{resume.label}</Button>}
   <DropdownMenu align="end" triggerClassName="inline-flex items-center gap-1 rounded-md border border-edge bg-panel px-2.5 py-1 text-xs font-medium text-ink hover:bg-canvas transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
    trigger={<>Mais<span className="sr-only"> ações de {title}</span><ChevronDown size={12} aria-hidden /></>}
    items={menu.map(entry => ({ label: entry.label, onSelect: () => entry.kind === 'route' ? onRoute(entry.route) : onLegacy(entry.view) }))} />
  </div>
 </li>
}
