import { useQuery } from '@tanstack/react-query'
import { ChevronLeft, ChevronRight, RefreshCw } from 'lucide-react'
import { apiFetch, type ErroApi } from '../../lib/api'
import { RUN_HISTORY_PAGE, RUN_HISTORY_STATUSES, clockLabel, historyPages, runHistoryIssue, runHistoryPath, runStatusPhase, type RunHistoryFilters, type RunHistoryItem, type RunHistoryPage } from '../../lib/workspaceExecution'
import { useAuthStore } from '../../store/auth'
import { Button } from '../ui/Button'
import { Input, Select } from '../ui/Input'
import { PageSpinner } from '../ui/Spinner'
import { RunPhaseBadge } from './WorkspaceRunStatus'

const HISTORY_SOURCE = 'Registro operacional das corridas'

// Lista paginada no servidor; abrir uma corrida devolve ao visualizador comum.
// Filtros ficam com quem abre o histórico, para voltar a ele como estavam.
// `enabled=false` (aba Execução fora de cena ou navegador oculto): nenhuma
// leitura, nem por troca de filtro ou foco; ao voltar, revalida.
export function WorkspaceRunHistory({ name, enabled = true, filters, onFilters, currentRunId, onOpen }: { name: string; enabled?: boolean; filters: RunHistoryFilters; onFilters: (filters: RunHistoryFilters) => void; currentRunId: string | null; onOpen: (item: RunHistoryItem) => void }) {
 const token = useAuthStore(s => s.token)
 const issue = runHistoryIssue(filters)
 const page = useQuery({ queryKey: ['workspace-run-history', token, name, filters], queryFn: ({ signal }) => apiFetch<RunHistoryPage>(runHistoryPath(name, filters), { signal }), enabled: enabled && !issue && !!token, refetchOnWindowFocus: enabled, retry: false, staleTime: 15_000 })
 const set = (patch: Partial<RunHistoryFilters>) => onFilters({ ...filters, ...patch, page: patch.page ?? 0 })
 const data = page.data, pages = data ? historyPages(data) : null
 const status = (page.error as ErroApi | null)?.status
 return <div className="space-y-4">
  <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
   <Input label="Data de referência a partir de" type="date" value={filters.from} onChange={e => set({ from: e.target.value })} />
   <Input label="Data de referência até" type="date" value={filters.to} onChange={e => set({ to: e.target.value })} />
   <Select label="Situação" value={filters.status} onChange={e => set({ status: e.target.value })}>{RUN_HISTORY_STATUSES.map(([id, label]) => <option key={id} value={id}>{label}</option>)}</Select>
   <Input label="Versão publicada" inputMode="numeric" placeholder="Todas" value={filters.version} onChange={e => set({ version: e.target.value.replace(/\D/g, '').slice(0, 9) })} />
  </div>
  <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-dim">
   <p>{data ? `${HISTORY_SOURCE} · consultado às ${clockLabel(page.dataUpdatedAt)}${data.versionsAvailable ? '' : ' · vínculo de versões indisponível neste ambiente'}` : HISTORY_SOURCE}</p>
   <Button variant="ghost" size="sm" loading={page.isFetching} disabled={!!issue} onClick={() => page.refetch()}><RefreshCw size={14} />Atualizar</Button>
  </div>
  {issue ? <p role="alert" className="text-sm text-red-700 dark:text-red-400">{issue}</p>
   : page.isPending && !enabled ? <p className="text-sm text-dim py-6 text-center">Consulta pausada enquanto a aba está oculta.</p>
   : page.isPending ? <PageSpinner />
   : page.isError ? <div role="alert" className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800 dark:border-red-900 dark:bg-red-950/30 dark:text-red-200"><p>{status === 403 ? 'Sua sessão não tem permissão para consultar o histórico de corridas.' : page.error.message || 'Histórico de corridas indisponível.'}</p>{status !== 403 && <Button className="mt-2" variant="secondary" size="sm" onClick={() => page.refetch()}>Tentar novamente</Button>}</div>
   : !data!.items.length ? <p className="text-sm text-dim py-6 text-center">Nenhuma corrida com estes filtros.</p>
   : <div className="overflow-x-auto"><table aria-label={`Corridas de ${name}, da mais recente para a mais antiga`} className="w-full text-left text-sm">
    <thead className="text-xs text-dim"><tr><th scope="col" className="py-2 pr-3 font-medium">Data de referência</th><th scope="col" className="py-2 pr-3 font-medium">Situação</th><th scope="col" className="py-2 pr-3 font-medium">Registro</th><th scope="col" className="py-2 pr-3 font-medium">Versão</th><th scope="col" className="py-2 pr-3 font-medium">Origem</th><th scope="col" aria-label="Abrir" className="py-2 font-medium" /></tr></thead>
    <tbody className="divide-y divide-edge">{data!.items.map((item, index) => {
     const current = !!item.runId && item.runId === currentRunId
     return <tr key={item.runId ?? `sem-corrida-${index}`} aria-current={current ? 'true' : undefined} className={current ? 'bg-blue-50/60 dark:bg-blue-950/20' : undefined}>
      <td className="py-2 pr-3 align-top"><p className="text-ink tabular-nums">{item.date ?? '—'}</p><p className="font-mono text-xs text-dim break-all mt-0.5">{item.runId ?? 'sem identificador'}</p></td>
      <td className="py-2 pr-3 align-top"><RunPhaseBadge phase={runStatusPhase(item.status)} code={item.status} />{item.replacedAt && <p className="text-xs text-dim mt-1">Substituída por reprocessamento</p>}</td>
      <td className="py-2 pr-3 align-top text-xs text-dim tabular-nums">{item.startedAt ?? '—'}<br />{item.finishedAt ?? 'em aberto'}</td>
      <td className="py-2 pr-3 align-top text-ink">{item.versionNumber != null ? `Versão ${item.versionNumber}` : <span className="text-dim">Não vinculada</span>}</td>
      <td className="py-2 pr-3 align-top text-dim [overflow-wrap:anywhere]">{item.triggeredBy ?? '—'}</td>
      <td className="py-2 align-top text-right"><Button variant={current ? 'ghost' : 'secondary'} size="sm" disabled={!item.runId || current} onClick={() => onOpen(item)}>{current ? 'Em exibição' : 'Abrir corrida'}</Button></td>
     </tr>
    })}</tbody>
   </table></div>}
  {data && pages && <nav aria-label="Páginas do histórico" className="flex flex-wrap items-center justify-between gap-2 text-sm">
   <p className="text-dim">Página {pages.current} de {pages.count} · {data.total} {data.total === 1 ? 'corrida' : 'corridas'} · {RUN_HISTORY_PAGE} por página</p>
   <div className="flex gap-2"><Button variant="secondary" size="sm" disabled={filters.page <= 0 || page.isFetching} onClick={() => set({ page: filters.page - 1 })}><ChevronLeft size={14} />Anteriores</Button><Button variant="secondary" size="sm" disabled={pages.current >= pages.count || page.isFetching} onClick={() => set({ page: filters.page + 1 })}>Próximas<ChevronRight size={14} /></Button></div>
  </nav>}
  <p className="text-xs text-dim">O horário “registro” vem do registro da corrida e usa outro relógio que a telemetria das etapas.</p>
 </div>
}
