import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { apiFetch } from '../lib/api'
import { useAuthStore } from '../store/auth'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { Input, Select } from '../components/ui/Input'
import { Modal } from '../components/ui/Modal'
import { PageSpinner } from '../components/ui/Spinner'
import { toast } from '../components/ui/Toast'
import { Tabs } from '../components/ui/Tabs'
import { useShellVariant } from '../lib/shell'
import {
  RefreshCw, RotateCcw, RefreshCcwDot, CheckSquare, FileText,
  ChevronDown, ChevronUp, Copy,
  ShieldCheck, ShieldAlert, ShieldX, AlertTriangle, CheckCircle2, Ticket, Eye,
} from 'lucide-react'
import { Textarea } from '../components/ui/Input'
import {
  LogDetailModal, AirflowLogModal, DsLogModal,
  durStr, fmtDt, copyText,
  type ExecRow, type AirflowLogState,
} from '../components/execucao/ExecucaoDetailModal'

// ── helpers ────────────────────────────────────────────────────────────────

const PROJETOS = ['BI_CVP', 'BI_VIDA', 'BI_PREVIDENCIA', 'BI_PRESTAMISTA']
const STATUS_OPTS = ['SUCCESS', 'FAILED', 'WARNING', 'RUNNING']
const LIMIT = 30

// ── types ──────────────────────────────────────────────────────────────────

interface FalhaSummary {
  period_days: number
  total: number
  sem_ack: number
  com_ack: number
  resolvidas: number
}

interface FalhaRow {
  execution_id: string
  project: string
  pipeline: string
  inicio: string
  fim: string
  duracao_total_segundos: number
  total_jobs: number
  jobs_falha: number
  jobs_warning: number
  ack_by?: string
  display_name?: string
  ack_at?: string
  note?: string
  resolved_by?: string
  resolved_display_name?: string
  resolved_at?: string
  resolution_note?: string
  snow_ticket?: string
}

interface FactoryRun {
  dag_run_id: string
  iniciado_em: string
  finalizado_em: string
  estado: string
  escopo: string
  geradas: number
  erros: number
}

interface FactoryRunDetail {
  dag_run_id: string
  estado: string
  steps: { tipo: string; msg: string }[]
  erros_lista: string[]
}

// ── Factory Runs ───────────────────────────────────────────────────────────

function stepIcon(tipo: string) {
  const m: Record<string, string> = {
    reset: '🔄', gerada: '✅', erro: '❌', iniciando: '▶️', concluido: '🏁', info: 'ℹ️',
    aguardando: '⏳', ativada: '🟢', timeout: '⚠️',
  }
  return m[tipo] ?? '•'
}

function FactoryRuns() {
  const [expanded, setExpanded] = useState<string | null>(null)

  const { data, isLoading, refetch } = useQuery<{ data: FactoryRun[] }>({
    queryKey: ['factory-runs'],
    queryFn: () => apiFetch('/factory/runs?limit=20'),
  })

  const { data: logData } = useQuery<FactoryRunDetail>({
    queryKey: ['factory-log', expanded],
    queryFn: () => apiFetch(`/factory/runs/${encodeURIComponent(expanded!)}/log`),
    enabled: !!expanded,
  })

  if (isLoading) return <PageSpinner />

  const runs = data?.data ?? []

  return (
    <div className="flex flex-col gap-3">
      <div className="flex justify-end">
        <Button variant="secondary" size="sm" onClick={() => refetch()}><RefreshCw size={13} /> Atualizar</Button>
      </div>
      {runs.length === 0 && (
        <p className="text-dim text-sm text-center py-12">Nenhuma execução da factory encontrada.</p>
      )}
      {runs.map(r => (
        <div key={r.dag_run_id} className="bg-panel border border-edge rounded-lg overflow-hidden">
          <button
            className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-edge/30 transition-colors"
            onClick={() => setExpanded(expanded === r.dag_run_id ? null : r.dag_run_id)}
          >
            <Badge value={r.estado} />
            <div className="flex-1 min-w-0">
              <div className="text-xs text-ink font-mono truncate">{r.dag_run_id}</div>
              <div className="text-xs text-dim">
                {r.escopo} · {r.geradas} geradas · {r.erros} erros
              </div>
            </div>
            <span className="text-xs text-dim shrink-0">{fmtDt(r.iniciado_em)}</span>
            {expanded === r.dag_run_id ? <ChevronUp size={14} className="shrink-0 text-dim" /> : <ChevronDown size={14} className="shrink-0 text-dim" />}
          </button>

          {expanded === r.dag_run_id && (
            <div className="border-t border-edge bg-canvas px-4 py-3">
              {!logData ? (
                <PageSpinner />
              ) : (
                <div className="flex flex-col gap-1.5">
                  {logData.steps?.map((s, i) => (
                    <div key={i} className="flex items-start gap-2 text-xs">
                      <span className="shrink-0 w-5">{stepIcon(s.tipo)}</span>
                      <span className={
                        s.tipo === 'erro' || s.tipo === 'timeout' ? 'text-red-600 dark:text-red-400'
                          : s.tipo === 'gerada' || s.tipo === 'ativada' ? 'text-green-700 dark:text-green-400'
                          : s.tipo === 'aguardando' ? 'text-amber-700 dark:text-amber-400 font-medium'
                          : 'text-dim'}>
                        {s.msg}
                      </span>
                    </div>
                  ))}
                  {logData.erros_lista?.length > 0 && (
                    <div className="mt-2 bg-red-50 border border-red-200 dark:bg-red-900/20 dark:border-red-800 rounded p-2">
                      <p className="text-xs text-red-700 dark:text-red-400 font-medium mb-1">Erros:</p>
                      {logData.erros_lista.map((e, i) => (
                        <p key={i} className="text-xs text-red-700 dark:text-red-300">{e}</p>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

// ── Main Execuções Tab ─────────────────────────────────────────────────────

interface Filters {
  projeto: string
  pipeline: string
  status: string
  data_ini: string
  exec_id: string
  hours_back: string
}

function ExecucoesTab() {
  const qc = useQueryClient()
  const user = useAuthStore(s => s.user)
  const isViewer = user?.perfil === 'consulta'
  const [searchParams, setSearchParams] = useSearchParams()

  // Filtros iniciais vindos da URL (ex: drill-down do Dashboard)
  const [filters, setFilters] = useState<Filters>(() => ({
    projeto: searchParams.get('project') ?? '',
    pipeline: searchParams.get('pipeline') ?? '',
    status: searchParams.get('status') ?? '',
    data_ini: searchParams.get('date') ?? '',
    exec_id: searchParams.get('execution_id') ?? '',
    hours_back: '',
  }))
  const [page, setPage] = useState(0)

  // Limpa os query params da URL após aplicá-los, para não persistirem em navegações
  useEffect(() => {
    if ([...searchParams.keys()].length > 0) {
      setSearchParams({}, { replace: true })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  const [detail, setDetail] = useState<ExecRow | null>(null)
  const [airflowLog, setAirflowLog] = useState<AirflowLogState | null>(null)
  const [dsLog, setDsLog] = useState<{ executionId: string; jobName: string; pipelineName: string } | null>(null)

  const buildQs = (f: Filters, pg: number) => {
    const q = new URLSearchParams({ limit: String(LIMIT), offset: String(pg * LIMIT) })
    if (f.projeto) q.set('filter_project', f.projeto)
    if (f.pipeline) q.set('filter_pipeline', f.pipeline)
    if (f.status) q.set('filter_status', f.status)
    if (f.exec_id) q.set('filter_execution_id', f.exec_id)
    if (f.hours_back) q.set('filter_hours_back', f.hours_back)
    else if (f.data_ini) q.set('filter_date_from', f.data_ini)
    return q.toString()
  }

  const { data, isLoading, refetch } = useQuery<{ total: number; data: ExecRow[] }>({
    queryKey: ['execucoes', filters, page],
    queryFn: () => apiFetch(`/execucoes?${buildQs(filters, page)}`),
  })

  const rerunMut = useMutation({
    mutationFn: ({ pipeline, execution_id }: { pipeline: string; execution_id: string }) =>
      apiFetch('/execucoes/rerun', { method: 'POST', body: JSON.stringify({ pipeline_name: pipeline, execution_id }) }),
    onSuccess: () => { toast.success('Reexecução disparada'); qc.invalidateQueries({ queryKey: ['execucoes'] }) },
    onError: (e: any) => toast.error(e.message),
  })

  const reconciliarMut = useMutation({
    mutationFn: ({ pipeline, execution_id }: { pipeline: string; execution_id: string }) =>
      apiFetch<{ closed: number; execution_id: string; pipeline: string }>('/execucoes/reconciliar', {
        method: 'POST',
        body: JSON.stringify({ execution_id, pipeline }),
      }),
    onSuccess: (res) => {
      if ((res?.closed ?? 0) > 0) {
        toast.success('Execução reconciliada — status atualizado.')
        qc.invalidateQueries({ queryKey: ['execucoes'] })
      } else {
        toast.info('Nada a reconciliar — o job ainda está em execução no DataStage.')
      }
    },
    onError: (e: any) => toast.error(e.message),
  })

  function applyQuick(hours: number) {
    setFilters(f => ({ ...f, status: 'FAILED', hours_back: hours > 0 ? String(hours) : '', data_ini: '' }))
    setPage(0)
  }

  function clearFilters() {
    setFilters({ projeto: '', pipeline: '', status: '', data_ini: '', exec_id: '', hours_back: '' })
    setPage(0)
  }

  const rows = data?.data ?? []
  const total = data?.total ?? 0

  return (
    <>
      {/* Filters */}
      <div className="bg-panel border border-edge rounded-lg p-4">
        <div className="flex flex-wrap gap-3 items-end">
          <Select label="Projeto" value={filters.projeto}
            onChange={e => { setFilters(f => ({ ...f, projeto: e.target.value })); setPage(0) }}
            className="w-44">
            <option value="">Todos</option>
            {PROJETOS.map(p => <option key={p}>{p}</option>)}
          </Select>

          <Input label="Pipeline" value={filters.pipeline}
            onChange={e => setFilters(f => ({ ...f, pipeline: e.target.value }))}
            onKeyDown={e => e.key === 'Enter' && (setPage(0), refetch())}
            placeholder="nome do pipeline" className="w-52" />

          <Select label="Status" value={filters.status}
            onChange={e => { setFilters(f => ({ ...f, status: e.target.value })); setPage(0) }}
            className="w-36">
            <option value="">Todos</option>
            {STATUS_OPTS.map(s => <option key={s}>{s}</option>)}
          </Select>

          <Input label="Data (a partir de)" type="date" value={filters.data_ini}
            onChange={e => { setFilters(f => ({ ...f, data_ini: e.target.value, hours_back: '' })); setPage(0) }}
            className="w-44" />

          <Input label="Execution ID" value={filters.exec_id}
            onChange={e => setFilters(f => ({ ...f, exec_id: e.target.value }))}
            onKeyDown={e => e.key === 'Enter' && (setPage(0), refetch())}
            placeholder="20260614..." className="w-48" />

          <div className="flex gap-2 flex-wrap ml-auto items-end">
            <Button variant="secondary" size="sm" onClick={() => applyQuick(24)}>✕ Falhas 24h</Button>
            <Button variant="secondary" size="sm" onClick={() => applyQuick(168)}>✕ Falhas semana</Button>
            <Button variant="secondary" size="sm" onClick={() => applyQuick(0)}>✕ Todas falhas</Button>
            <Button variant="secondary" size="sm" onClick={clearFilters}>Limpar</Button>
            <Button size="sm" onClick={() => { setPage(0); refetch() }}><RefreshCw size={13} /></Button>
          </div>
        </div>
      </div>

      {/* Results */}
      {isLoading ? <PageSpinner /> : (
        <div className="bg-panel border border-edge rounded-lg overflow-hidden">
          <div className="px-4 py-2 border-b border-edge flex items-center justify-between">
            <span className="text-xs text-dim">{total} resultado{total !== 1 ? 's' : ''}</span>
            {filters.hours_back && (
              <span className="text-xs text-amber-400">Filtro: últimas {filters.hours_back}h · FAILED</span>
            )}
          </div>

          {rows.length === 0 ? (
            <p className="text-dim text-sm text-center py-12">Nenhuma execução encontrada.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead><tr className="text-xs text-dim border-b border-edge bg-canvas">
                  <th className="px-4 py-2 text-left">Pipeline</th>
                  <th className="px-4 py-2 text-left">Projeto</th>
                  <th className="px-4 py-2 text-left">Status</th>
                  <th className="px-4 py-2 text-left">Início</th>
                  <th className="px-4 py-2 text-left">Fim</th>
                  <th className="px-4 py-2 text-left">Duração</th>
                  <th className="px-4 py-2 text-left">Fila</th>
                  <th className="px-4 py-2 text-center">Jobs</th>
                  <th className="px-4 py-2 text-center">Falha/Aviso</th>
                  <th className="px-4 py-2 text-left">Execution ID</th>
                  <th className="px-4 py-2 text-right">Ações</th>
                </tr></thead>
                <tbody>
                  {rows.map(r => (
                    <tr key={r.execution_id} className="border-b border-edge/50 hover:bg-edge/20 transition-colors">
                      <td className="px-4 py-2 font-mono text-xs text-ink font-medium">{r.pipeline}</td>
                      <td className="px-4 py-2 text-dim text-xs">{r.project}</td>
                      <td className="px-4 py-2">
                        <div className="flex items-center gap-1.5">
                          <Badge value={r.status_geral} />
                          {r.ack_by && <span className="text-xs text-green-400" title={`Ack: ${r.display_name ?? r.ack_by}`}>✓</span>}
                        </div>
                      </td>
                      <td className="px-4 py-2 text-dim text-xs whitespace-nowrap">{fmtDt(r.inicio)}</td>
                      <td className="px-4 py-2 text-dim text-xs whitespace-nowrap">{fmtDt(r.fim)}</td>
                      <td className="px-4 py-2 text-dim text-xs">{durStr(r.duracao_total_segundos)}</td>
                      <td className="px-4 py-2 text-xs">
                        {r.fila_total_segundos ? <span className="text-amber-400">{durStr(r.fila_total_segundos)}</span> : <span className="text-dim">—</span>}
                      </td>
                      <td className="px-4 py-2 text-center text-xs text-dim">{r.total_jobs}</td>
                      <td className="px-4 py-2 text-center">
                        <span className={`text-xs font-mono ${r.jobs_falha > 0 ? 'text-red-400' : r.jobs_warning > 0 ? 'text-amber-400' : 'text-dim'}`}>
                          {r.jobs_falha}/{r.jobs_warning}
                        </span>
                      </td>
                      <td className="px-4 py-2">
                        <span
                          className="font-mono text-xs text-blue-400 cursor-pointer hover:underline"
                          onClick={() => copyText(r.execution_id)}
                          title="Clique para copiar"
                        >
                          {r.execution_id.slice(0, 18)}…
                        </span>
                      </td>
                      <td className="px-4 py-2 text-right">
                        <div className="flex justify-end gap-1">
                          <Button variant="ghost" size="sm" title="Detalhes" onClick={() => setDetail(r)}>
                            <FileText size={13} />
                          </Button>
                          {r.status_geral === 'RUNNING' && !isViewer && (
                            <Button variant="ghost" size="sm"
                              title="Reconciliar status (fechar se já concluído no DataStage)"
                              loading={reconciliarMut.isPending}
                              onClick={() => reconciliarMut.mutate({ pipeline: r.pipeline, execution_id: r.execution_id })}>
                              <RefreshCcwDot size={13} />
                            </Button>
                          )}
                          {r.status_geral === 'FAILED' && !isViewer && (
                            <Button variant="ghost" size="sm" title="Reexecutar" loading={rerunMut.isPending}
                              onClick={() => rerunMut.mutate({ pipeline: r.pipeline, execution_id: r.execution_id })}>
                              <RotateCcw size={13} />
                            </Button>
                          )}
                          {r.status_geral === 'FAILED' && !r.ack_by && !isViewer && (
                            <Button variant="ghost" size="sm" title="Reconhecer falha"
                              onClick={() => setDetail(r)}>
                              <CheckSquare size={13} />
                            </Button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Pagination */}
          <div className="px-4 py-2 flex items-center gap-3 border-t border-edge">
            <Button variant="ghost" size="sm" disabled={page === 0} onClick={() => setPage(p => p - 1)}>← Anterior</Button>
            <span className="text-xs text-dim">Página {page + 1} · {Math.min((page + 1) * LIMIT, total)} de {total}</span>
            <Button variant="ghost" size="sm" disabled={rows.length < LIMIT} onClick={() => setPage(p => p + 1)}>Próxima →</Button>
          </div>
        </div>
      )}

      {/* Modals */}
      {detail && (
        <LogDetailModal
          row={detail}
          onClose={() => setDetail(null)}
          onAirflowLog={s => { setDetail(null); setAirflowLog(s) }}
          onDsLog={(eid, jn, pn) => { setDetail(null); setDsLog({ executionId: eid, jobName: jn, pipelineName: pn }) }}
        />
      )}
      {airflowLog && <AirflowLogModal state={airflowLog} onClose={() => setAirflowLog(null)} />}
      {dsLog && <DsLogModal executionId={dsLog.executionId} jobName={dsLog.jobName} pipelineName={dsLog.pipelineName} onClose={() => setDsLog(null)} />}
    </>
  )
}

// ── Resolve Modal ──────────────────────────────────────────────────────────

function ResolveModal({
  row, onClose, readOnly = false,
}: { row: FalhaRow; onClose: () => void; readOnly?: boolean }) {
  const qc = useQueryClient()
  const user = useAuthStore(s => s.user)
  const [note, setNote] = useState(row.resolution_note ?? '')
  const [ticket, setTicket] = useState(row.snow_ticket ?? '')

  const resolveMut = useMutation({
    mutationFn: (remove: boolean) => apiFetch('/execucoes/resolve', {
      method: 'POST',
      body: JSON.stringify({
        execution_id: row.execution_id,
        pipeline: row.pipeline,
        label: row.pipeline,
        user: user?.matricula,
        display_name: `${user?.primeiro_nome ?? ''} ${user?.ultimo_nome ?? ''}`.trim(),
        resolution_note: note || null,
        snow_ticket: ticket || null,
        remove,
      }),
    }),
    onSuccess: (_, remove) => {
      toast.success(remove ? 'Resolução desfeita' : 'Falha marcada como resolvida')
      qc.invalidateQueries({ queryKey: ['falhas'] })
      qc.invalidateQueries({ queryKey: ['falhas-summary'] })
      qc.invalidateQueries({ queryKey: ['execucoes'] })
      onClose()
    },
    onError: (e: any) => toast.error(e.message),
  })

  const isResolved = !!row.resolved_at

  return (
    <Modal open title={isResolved ? 'Detalhes da Resolução' : 'Marcar como Resolvida'} onClose={onClose} size="md">
      <div className="flex flex-col gap-4">
        <div className="bg-canvas border border-edge rounded-lg p-3 text-xs flex flex-col gap-1.5">
          <div><span className="text-dim">Pipeline:</span> <span className="text-ink font-mono ml-1">{row.pipeline}</span></div>
          <div><span className="text-dim">Execution ID:</span> <span className="text-blue-400 font-mono ml-1">{row.execution_id}</span></div>
          {row.ack_by && (
            <div><span className="text-dim">Assumida por:</span> <span className="text-ink ml-1">{row.display_name ?? row.ack_by}</span> <span className="text-dim">em {fmtDt(row.ack_at)}</span></div>
          )}
        </div>

        {isResolved && (
          <div className="bg-green-50 border border-green-200 text-green-800 dark:bg-green-900/20 dark:border-green-800 dark:text-green-300 rounded-lg p-3 text-xs flex flex-col gap-1">
            <div className="flex items-center gap-1.5 font-medium text-green-700 dark:text-green-400">
              <CheckCircle2 size={13} /> Resolvida
            </div>
            <div>Por: <strong>{row.resolved_display_name ?? row.resolved_by}</strong> em {fmtDt(row.resolved_at)}</div>
            {row.resolution_note && <div>Nota: {row.resolution_note}</div>}
            {row.snow_ticket && <div>Ticket: <span className="font-mono">{row.snow_ticket}</span></div>}
          </div>
        )}

        {isResolved ? (
          // Modo leitura quando já resolvida — evita edição acidental
          <div className="flex flex-col gap-3">
            <div className="flex flex-col gap-1">
              <label className="text-xs text-dim font-medium">Nota de resolução</label>
              <p className="text-sm text-ink bg-canvas border border-edge rounded-md px-3 py-2 min-h-[60px]">
                {row.resolution_note ?? <span className="text-dim italic">Sem nota registrada</span>}
              </p>
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-xs text-dim font-medium flex items-center gap-1.5">
                <Ticket size={11} /> Ticket ServiceNow
              </label>
              <p className="text-sm font-mono text-blue-400 bg-canvas border border-edge rounded-md px-3 py-2">
                {row.snow_ticket ?? <span className="text-dim italic font-sans">Não informado</span>}
              </p>
            </div>
            <div className="flex gap-2 pt-1 border-t border-edge justify-between">
              {!readOnly && (
                <Button variant="secondary" size="sm" loading={resolveMut.isPending}
                  onClick={() => resolveMut.mutate(true)}>
                  Desfazer resolução
                </Button>
              )}
              <Button variant="secondary" size="sm" onClick={onClose} className={readOnly ? 'ml-auto' : ''}>Fechar</Button>
            </div>
          </div>
        ) : (
          // Modo edição quando ainda não resolvida
          <div className="flex flex-col gap-3">
            <Textarea
              label="Nota de resolução (opcional)"
              value={note}
              onChange={e => setNote(e.target.value)}
              rows={3}
              placeholder="Descreva o que foi feito para resolver a falha..."
            />
            <div className="flex flex-col gap-1">
              <label className="text-xs text-dim font-medium flex items-center gap-1.5">
                <Ticket size={11} /> Ticket ServiceNow (opcional)
              </label>
              <Input
                value={ticket}
                onChange={e => setTicket(e.target.value)}
                placeholder="INC0012345"
                className="font-mono"
              />
              <p className="text-xs text-dim/60">Integração automática com ServiceNow disponível em breve. Registre o ticket para referência.</p>
            </div>
            <div className="flex gap-2 pt-1 border-t border-edge justify-end">
              <Button variant="secondary" size="sm" onClick={onClose}>Cancelar</Button>
              <Button size="sm" loading={resolveMut.isPending}
                onClick={() => resolveMut.mutate(false)}>
                <CheckCircle2 size={13} /> Marcar como Resolvida
              </Button>
            </div>
          </div>
        )}
      </div>
    </Modal>
  )
}

// ── KPI Cards ──────────────────────────────────────────────────────────────

function FalhasKpiCards({ days, onFilter }: { days: number; onFilter?: (f: string) => void }) {
  const { data, isLoading } = useQuery<FalhaSummary>({
    queryKey: ['falhas-summary', days],
    queryFn: () => apiFetch(`/execucoes/falhas-summary?days=${days}`),
    refetchInterval: 60_000,
  })

  if (isLoading) return (
    <div className="grid grid-cols-4 gap-3">
      {[0,1,2,3].map(i => (
        <div key={i} className="bg-panel border border-edge rounded-xl p-4 animate-pulse h-24" />
      ))}
    </div>
  )

  const cards = [
    {
      label: 'Total de Falhas',
      value: data?.total ?? 0,
      icon: AlertTriangle,
      color: 'text-red-400',
      bg: 'bg-red-500/10 border-red-800/40',
      filter: '',
    },
    {
      label: 'Não Assumidas',
      value: data?.sem_ack ?? 0,
      icon: ShieldX,
      color: 'text-orange-400',
      bg: 'bg-orange-500/10 border-orange-800/40',
      filter: 'sem_ack',
    },
    {
      label: 'Em Investigação',
      value: data?.com_ack ?? 0,
      icon: ShieldAlert,
      color: 'text-amber-400',
      bg: 'bg-amber-500/10 border-amber-800/40',
      filter: 'com_ack',
    },
    {
      label: 'Resolvidas',
      value: data?.resolvidas ?? 0,
      icon: ShieldCheck,
      color: 'text-green-400',
      bg: 'bg-green-500/10 border-green-800/40',
      filter: 'resolvida',
    },
  ]

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
      {cards.map(c => {
        const Icon = c.icon
        return (
          <button
            key={c.label}
            onClick={() => onFilter?.(c.filter)}
            className={`bg-panel border ${c.bg} rounded-xl p-4 text-left hover:opacity-90 transition-opacity focus:outline-none focus:ring-2 focus:ring-blue-500/40`}
          >
            <div className="flex items-start justify-between mb-2">
              <span className="text-xs text-dim font-medium">{c.label}</span>
              <Icon size={16} className={c.color} />
            </div>
            <div className={`text-3xl font-bold ${c.color}`}>{c.value}</div>
            <div className="text-xs text-dim/60 mt-1">últimos {days} dias</div>
          </button>
        )
      })}
    </div>
  )
}

// ── Resolução em massa ─────────────────────────────────────────────────────

function BulkResolveModal({ rows, loading, onConfirm, onClose }: {
  rows: FalhaRow[]; loading: boolean
  onConfirm: (note: string, ticket: string) => void; onClose: () => void
}) {
  const [note, setNote] = useState('')
  const [ticket, setTicket] = useState('')
  const pipelines = Array.from(new Set(rows.map(r => r.pipeline)))
  return (
    <Modal open title={`Resolver ${rows.length} falha(s) em massa`} onClose={onClose} size="md">
      <div className="flex flex-col gap-4">
        <div className="text-xs text-dim bg-amber-50 dark:bg-amber-900/10 border border-amber-200 dark:border-amber-800/30 rounded-lg px-3 py-2">
          A mesma observação e ticket serão aplicados às <strong className="text-ink">{rows.length}</strong> falha(s)
          {pipelines.length === 1
            ? <> do pipeline <span className="font-mono text-ink">{pipelines[0]}</span></>
            : <> de <strong className="text-ink">{pipelines.length}</strong> pipelines</>}.
          Falhas ainda não assumidas serão <strong className="text-ink">auto-assumidas em seu nome</strong>.
        </div>
        <div className="max-h-32 overflow-auto border border-edge rounded-lg divide-y divide-edge/30">
          {rows.slice(0, 50).map(r => (
            <div key={`${r.execution_id}-${r.pipeline}`} className="px-3 py-1.5 text-[11px] flex items-center gap-2">
              <span className="font-mono text-ink truncate flex-1">{r.pipeline}</span>
              <span className="text-dim shrink-0">{fmtDt(r.inicio)}</span>
            </div>
          ))}
          {rows.length > 50 && <div className="px-3 py-1.5 text-[11px] text-dim">… e mais {rows.length - 50}</div>}
        </div>
        <Textarea label="Observação da resolução (aplicada a todas)" value={note}
          onChange={e => setNote(e.target.value)} rows={3}
          placeholder="ex: erros anteriores ao Orquestra — fechados para reexecução de análise" />
        <Input label="Ticket ServiceNow (opcional)" value={ticket}
          onChange={e => setTicket(e.target.value)} placeholder="ex: INC0012345" />
        <div className="flex justify-end gap-2 border-t border-edge pt-3">
          <Button variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button loading={loading} onClick={() => onConfirm(note, ticket)}
            className="border-green-800/40 text-green-400 hover:text-green-300">
            <CheckCircle2 size={13} /> Resolver {rows.length}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

// ── Gestão de Falhas Tab ───────────────────────────────────────────────────

export function GestaoFalhasTab() {
  const qc = useQueryClient()
  const user = useAuthStore(s => s.user)
  const isViewer = user?.perfil === 'consulta'

  const [days, setDays] = useState(7)
  const [statusAck, setStatusAck] = useState('')
  const [mine, setMine] = useState(false)   // "assumidas por mim" (ack_by = matrícula)
  const [filterPipeline, setFilterPipeline] = useState('')
  const [filterProject, setFilterProject] = useState('')
  const [page, setPage] = useState(0)
  const [resolveRow, setResolveRow] = useState<{ row: FalhaRow; readOnly: boolean } | null>(null)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [bulkOpen, setBulkOpen] = useState(false)
  const FLIMIT = 50

  const rowKey = (r: FalhaRow) => `${r.execution_id}|${r.pipeline}`
  // Rótulo amigável p/ notificação no Teams: o nome do pipeline.
  const falhaLabel = (r: FalhaRow) => r.pipeline

  // Seleção é limpa quando os filtros/página mudam (evita resolver o que saiu da lista)
  useEffect(() => { setSelected(new Set()) }, [days, statusAck, mine, filterPipeline, filterProject, page])

  const qs = new URLSearchParams({
    days: String(days),
    offset: String(page * FLIMIT),
    limit: String(FLIMIT),
  })
  if (statusAck) qs.set('status_ack', statusAck)
  if (filterPipeline) qs.set('filter_pipeline', filterPipeline)
  if (filterProject) qs.set('filter_project', filterProject)
  if (mine && user?.matricula) qs.set('ack_by', user.matricula)

  const { data, isLoading, refetch } = useQuery<{ total: number; data: FalhaRow[] }>({
    queryKey: ['falhas', days, statusAck, mine, filterPipeline, filterProject, page],
    queryFn: () => apiFetch(`/execucoes/falhas?${qs}`),
  })

  const ackMut = useMutation({
    mutationFn: (r: FalhaRow) => apiFetch<{ ok: boolean; ack_by?: string; display_name?: string }>('/execucoes/ack', {
      method: 'POST',
      body: JSON.stringify({
        execution_id: r.execution_id,
        pipeline: r.pipeline,
        label: falhaLabel(r),
        user: user?.matricula,
        display_name: `${user?.primeiro_nome ?? ''} ${user?.ultimo_nome ?? ''}`.trim(),
      }),
    }),
    onSuccess: (data) => {
      // Duas pessoas podem clicar "Assumir" quase ao mesmo tempo — o ack é
      // idempotente no backend, então quem perder a corrida recebe sucesso
      // com o ack_by de quem chegou primeiro. Avisa em vez de fingir que
      // este usuário assumiu.
      if (data.ack_by && data.ack_by !== user?.matricula) {
        toast.error(`Falha já assumida por ${data.display_name ?? data.ack_by}`)
      } else {
        toast.success('Falha assumida')
      }
      qc.invalidateQueries({ queryKey: ['falhas'] })
      qc.invalidateQueries({ queryKey: ['falhas-summary'] })
    },
    onError: (e: any) => toast.error(e.message),
  })

  const bulkMut = useMutation({
    mutationFn: (payload: { items: { execution_id: string; pipeline: string; label: string }[]; resolution_note: string; snow_ticket: string }) =>
      apiFetch<{ ok: boolean; resolved: number }>('/execucoes/resolve-bulk', {
        method: 'POST',
        body: JSON.stringify({
          items: payload.items,
          resolution_note: payload.resolution_note || null,
          snow_ticket: payload.snow_ticket || null,
          user: user?.matricula,
          display_name: `${user?.primeiro_nome ?? ''} ${user?.ultimo_nome ?? ''}`.trim(),
        }),
      }),
    onSuccess: (res) => {
      toast.success(`${res?.resolved ?? 0} falha(s) resolvida(s) em massa`)
      setSelected(new Set()); setBulkOpen(false)
      qc.invalidateQueries({ queryKey: ['falhas'] })
      qc.invalidateQueries({ queryKey: ['falhas-summary'] })
    },
    onError: (e: any) => toast.error(e.message),
  })

  const bulkAckMut = useMutation({
    mutationFn: (items: { execution_id: string; pipeline: string; label: string }[]) =>
      apiFetch<{ ok: boolean; acked: number; skipped: number }>('/execucoes/ack-bulk', {
        method: 'POST',
        body: JSON.stringify({
          items,
          user: user?.matricula,
          display_name: `${user?.primeiro_nome ?? ''} ${user?.ultimo_nome ?? ''}`.trim(),
        }),
      }),
    onSuccess: (res) => {
      toast.success(`${res?.acked ?? 0} falha(s) assumida(s)${res?.skipped ? ` · ${res.skipped} já tinham dono` : ''}`)
      setSelected(new Set())
      qc.invalidateQueries({ queryKey: ['falhas'] })
      qc.invalidateQueries({ queryKey: ['falhas-summary'] })
    },
    onError: (e: any) => toast.error(e.message),
  })

  const rows = data?.data ?? []
  const total = data?.total ?? 0

  // Só falhas ainda NÃO resolvidas são selecionáveis (não sobrescreve resolução existente)
  const selectable = rows.filter(r => !r.resolved_at)
  const allSelected = selectable.length > 0 && selectable.every(r => selected.has(rowKey(r)))
  const toggleRow = (r: FalhaRow) => setSelected(s => { const n = new Set(s); const k = rowKey(r); n.has(k) ? n.delete(k) : n.add(k); return n })
  const toggleAll = () => setSelected(() => allSelected ? new Set() : new Set(selectable.map(rowKey)))
  const selectedRows = rows.filter(r => selected.has(rowKey(r)))
  const selectedUnacked = selectedRows.filter(r => !r.ack_by)  // p/ assumir só os sem dono

  function statusAckLabel(r: FalhaRow) {
    if (r.resolved_at) return <span className="inline-flex items-center gap-1 text-xs text-green-400"><CheckCircle2 size={11} /> Resolvida</span>
    if (r.ack_by) return <span className="inline-flex items-center gap-1 text-xs text-amber-400"><ShieldAlert size={11} /> Em investigação</span>
    return <span className="inline-flex items-center gap-1 text-xs text-red-400"><ShieldX size={11} /> Não assumida</span>
  }

  return (
    <div className="flex flex-col gap-4">
      {/* KPI Cards */}
      <FalhasKpiCards days={days} onFilter={f => { setStatusAck(f); setPage(0) }} />

      {/* Filters */}
      <div className="bg-panel border border-edge rounded-lg p-4 flex flex-wrap gap-3 items-end">
        <Select label="Período" value={String(days)}
          onChange={e => { setDays(Number(e.target.value)); setPage(0) }}
          className="w-36">
          <option value="1">Hoje</option>
          <option value="7">Últimos 7 dias</option>
          <option value="30">Últimos 30 dias</option>
          <option value="90">Últimos 90 dias</option>
        </Select>

        <Select label="Situação" value={statusAck}
          onChange={e => { setStatusAck(e.target.value); setPage(0) }}
          className="w-44">
          <option value="">Todas</option>
          <option value="sem_ack">Não assumidas</option>
          <option value="com_ack">Em investigação</option>
          <option value="resolvida">Resolvidas</option>
        </Select>

        <Select label="Responsável" value={mine ? 'mine' : ''}
          onChange={e => { setMine(e.target.value === 'mine'); setPage(0) }}
          className="w-48">
          <option value="">Todos</option>
          <option value="mine">Assumidas por mim</option>
        </Select>

        <Select label="Projeto" value={filterProject}
          onChange={e => { setFilterProject(e.target.value); setPage(0) }}
          className="w-44">
          <option value="">Todos</option>
          {PROJETOS.map(p => <option key={p}>{p}</option>)}
        </Select>

        <Input label="Pipeline" value={filterPipeline}
          onChange={e => setFilterPipeline(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && (setPage(0), refetch())}
          placeholder="nome do pipeline" className="w-52" />

        <div className="flex gap-2 ml-auto items-end">
          <Button variant="secondary" size="sm" onClick={() => {
            setStatusAck(''); setMine(false); setFilterPipeline(''); setFilterProject(''); setPage(0)
          }}>Limpar</Button>
          <Button size="sm" onClick={() => { setPage(0); refetch() }}><RefreshCw size={13} /></Button>
        </div>
      </div>

      {/* Table */}
      {isLoading ? <PageSpinner /> : (
        <div className="bg-panel border border-edge rounded-lg overflow-hidden">
          <div className="px-4 py-2 border-b border-edge flex items-center gap-3">
            <span className="text-xs text-dim">{total} falha{total !== 1 ? 's' : ''}</span>
            {!isViewer && selected.size > 0 && (
              <div className="flex items-center gap-2 ml-auto">
                <span className="text-xs text-dim">{selected.size} selecionada{selected.size !== 1 ? 's' : ''}</span>
                <Button variant="ghost" size="sm" onClick={() => setSelected(new Set())}>Limpar seleção</Button>
                <Button variant="secondary" size="sm"
                  loading={bulkAckMut.isPending}
                  disabled={selectedUnacked.length === 0}
                  onClick={() => bulkAckMut.mutate(selectedUnacked.map(r => ({ execution_id: r.execution_id, pipeline: r.pipeline, label: falhaLabel(r) })))}
                  className="border-orange-700/50 text-orange-400 hover:text-orange-300"
                  title={selectedUnacked.length === 0 ? 'Todas as selecionadas já têm dono' : 'Assumir as selecionadas sem dono'}>
                  <ShieldAlert size={13} /> Assumir {selectedUnacked.length} em massa
                </Button>
                <Button size="sm" onClick={() => setBulkOpen(true)}
                  className="border-green-800/40 text-green-400 hover:text-green-300">
                  <CheckCircle2 size={13} /> Resolver {selected.size} em massa
                </Button>
              </div>
            )}
          </div>

          {rows.length === 0 ? (
            <p className="text-dim text-sm text-center py-12">Nenhuma falha encontrada no período.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead><tr className="text-dim border-b border-edge bg-canvas">
                  {!isViewer && (
                    <th className="px-3 py-2 text-left w-8">
                      <input type="checkbox" checked={allSelected} onChange={toggleAll}
                        disabled={selectable.length === 0} title="Selecionar todas (não resolvidas)"
                        className="accent-green-500 cursor-pointer" />
                    </th>
                  )}
                  <th className="px-3 py-2 text-left">Pipeline</th>
                  <th className="px-3 py-2 text-left">Projeto</th>
                  <th className="px-3 py-2 text-left">Início</th>
                  <th className="px-3 py-2 text-left">Situação</th>
                  <th className="px-3 py-2 text-left">Assumida por</th>
                  <th className="px-3 py-2 text-left">Assumida em</th>
                  <th className="px-3 py-2 text-left">Resolvida por</th>
                  <th className="px-3 py-2 text-left">Resolvida em</th>
                  <th className="px-3 py-2 text-left">Ticket</th>
                  <th className="px-3 py-2 text-right">Ações</th>
                </tr></thead>
                <tbody>
                  {rows.map(r => (
                    <tr key={`${r.execution_id}-${r.pipeline}`}
                      className={`border-b border-edge/40 hover:bg-edge/20 transition-colors ${r.resolved_at ? 'opacity-70' : ''} ${selected.has(rowKey(r)) ? 'bg-green-50 dark:bg-green-900/10' : ''}`}>
                      {!isViewer && (
                        <td className="px-3 py-2">
                          {!r.resolved_at && (
                            <input type="checkbox" checked={selected.has(rowKey(r))} onChange={() => toggleRow(r)}
                              className="accent-green-500 cursor-pointer" />
                          )}
                        </td>
                      )}
                      <td className="px-3 py-2 font-mono text-ink font-medium max-w-[240px]"
                        title={r.pipeline}>
                        <span className="truncate block">{r.pipeline}</span>
                      </td>
                      <td className="px-3 py-2 text-dim">{r.project}</td>
                      <td className="px-3 py-2 text-dim whitespace-nowrap">{fmtDt(r.inicio)}</td>
                      <td className="px-3 py-2">{statusAckLabel(r)}</td>
                      <td className="px-3 py-2 text-dim">
                        {r.ack_by ? (r.display_name ?? r.ack_by) : <span className="text-red-400/60">—</span>}
                      </td>
                      <td className="px-3 py-2 text-dim whitespace-nowrap">
                        {r.ack_at ? fmtDt(r.ack_at) : <span className="text-dim/40">—</span>}
                      </td>
                      <td className="px-3 py-2 text-dim">
                        {r.resolved_by ? (
                          <span title={r.resolution_note ?? ''}>{r.resolved_display_name ?? r.resolved_by}</span>
                        ) : <span className="text-dim/40">—</span>}
                      </td>
                      <td className="px-3 py-2 text-dim whitespace-nowrap">
                        {r.resolved_at ? fmtDt(r.resolved_at) : <span className="text-dim/40">—</span>}
                      </td>
                      <td className="px-3 py-2">
                        {r.snow_ticket
                          ? <span className="font-mono text-blue-400">{r.snow_ticket}</span>
                          : <span className="text-dim/40">—</span>}
                      </td>
                      <td className="px-3 py-2 text-right">
                        <div className="flex justify-end gap-1">
                          {!r.ack_by && !isViewer && (
                            <Button variant="secondary" size="sm" title="Assumir investigação"
                              loading={ackMut.isPending}
                              onClick={() => ackMut.mutate(r)}
                              className="border-orange-700/50 text-orange-400 hover:text-orange-300">
                              <ShieldAlert size={12} /> Assumir
                            </Button>
                          )}
                          {r.resolved_at ? (
                            <Button
                              variant="ghost"
                              size="sm"
                              title="Ver detalhes da resolução"
                              onClick={() => setResolveRow({ row: r, readOnly: isViewer })}
                            >
                              <Eye size={12} className="text-green-400" /> Detalhes
                            </Button>
                          ) : !isViewer && (
                            <Button
                              variant="ghost"
                              size="sm"
                              title="Marcar como resolvida"
                              onClick={() => setResolveRow({ row: r, readOnly: false })}
                            >
                              <CheckCircle2 size={12} />
                            </Button>
                          )}
                          <Button variant="ghost" size="sm" title="Copiar Execution ID"
                            onClick={() => copyText(r.execution_id)}>
                            <Copy size={12} />
                          </Button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <div className="px-4 py-2 flex items-center gap-3 border-t border-edge">
            <Button variant="ghost" size="sm" disabled={page === 0} onClick={() => setPage(p => p - 1)}>← Anterior</Button>
            <span className="text-xs text-dim">Página {page + 1} · {Math.min((page + 1) * FLIMIT, total)} de {total}</span>
            <Button variant="ghost" size="sm" disabled={rows.length < FLIMIT} onClick={() => setPage(p => p + 1)}>Próxima →</Button>
          </div>
        </div>
      )}

      {resolveRow && (
        <ResolveModal row={resolveRow.row} readOnly={resolveRow.readOnly} onClose={() => setResolveRow(null)} />
      )}
      {bulkOpen && (
        <BulkResolveModal
          rows={selectedRows}
          loading={bulkMut.isPending}
          onConfirm={(note, ticket) => bulkMut.mutate({
            items: selectedRows.map(r => ({ execution_id: r.execution_id, pipeline: r.pipeline, label: falhaLabel(r) })),
            resolution_note: note, snow_ticket: ticket,
          })}
          onClose={() => setBulkOpen(false)}
        />
      )}
    </div>
  )
}

// ── Root ───────────────────────────────────────────────────────────────────

export default function Logs() {
  const shell = useShellVariant()
  const [searchParams] = useSearchParams()
  // No v2, a Gestão de Falhas saiu para um menu próprio (/gestao-falhas) e some
  // das abas. No clássico continua como aba — lá é a única porta de entrada.
  const showGestao = shell !== 'v2'
  const tabs = [
    { id: 'execucoes', label: '≣ Execuções' },
    ...(showGestao ? [{ id: 'gestao', label: '⚠ Gestão de Falhas' }] : []),
    { id: 'factory', label: '♻ Regeneração de DAGs' },
  ]
  const urlTab = searchParams.get('tab')
  const [tab, setTab] = useState(
    urlTab && tabs.some((t) => t.id === urlTab) ? urlTab : 'execucoes',
  )

  return (
    <div className="flex flex-col gap-4">
      <Tabs tabs={tabs} active={tab} onChange={setTab} />

      {tab === 'execucoes' && <ExecucoesTab />}
      {tab === 'gestao' && showGestao && <GestaoFalhasTab />}
      {tab === 'factory' && <FactoryRuns />}
    </div>
  )
}
