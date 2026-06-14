import { useState, useCallback } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiFetch } from '../lib/api'
import { useAuthStore } from '../store/auth'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { Input, Select } from '../components/ui/Input'
import { Modal } from '../components/ui/Modal'
import { PageSpinner } from '../components/ui/Spinner'
import { toast } from '../components/ui/Toast'
import { Tabs } from '../components/ui/Tabs'
import {
  RefreshCw, RotateCcw, CheckSquare, FileText,
  ChevronDown, ChevronUp, Copy, ExternalLink, Search,
  ShieldCheck, ShieldAlert, ShieldX, AlertTriangle, CheckCircle2, Ticket,
} from 'lucide-react'
import { Textarea } from '../components/ui/Input'

// ── helpers ────────────────────────────────────────────────────────────────

const PROJETOS = ['BI_CVP', 'BI_VIDA', 'BI_PREVIDENCIA', 'BI_PRESTAMISTA']
const STATUS_OPTS = ['SUCCESS', 'FAILED', 'WARNING', 'RUNNING']
const AIRFLOW_UI = 'https://airflow.caixavidaeprevidencia.intranet'
const LIMIT = 30

function durStr(s?: number | null) {
  if (!s) return '-'
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = s % 60
  if (h > 0) return `${h}h ${m}m ${sec}s`
  return m > 0 ? `${m}m ${sec}s` : `${sec}s`
}

function fmtDt(dt?: string | null) {
  if (!dt) return '-'
  // "2026-06-14 12:00:00" → "14/06 12:00:00"
  try {
    const d = new Date(dt.replace(' ', 'T'))
    return d.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' }) + ' ' +
      d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  } catch { return dt }
}


function devBadge(durSec: number, avg: number) {
  const pct = Math.round(((durSec - avg) / avg) * 100)
  if (Math.abs(pct) < 10) return null
  const cls = pct >= 30 ? 'text-red-400' : pct > 0 ? 'text-amber-400' : 'text-green-400'
  return <span className={`text-xs font-mono ${cls}`}>{pct > 0 ? '+' : ''}{pct}%</span>
}

function copyText(t: string) {
  navigator.clipboard.writeText(t).then(() => toast.info('Copiado!')).catch(() => toast.error('Erro ao copiar'))
}

// ── types ──────────────────────────────────────────────────────────────────

interface ExecRow {
  execution_id: string
  project: string
  pipeline: string
  inicio: string
  fim: string
  duracao_total_segundos: number
  total_jobs: number
  jobs_ok: number
  jobs_falha: number
  jobs_warning: number
  jobs_running: number
  status_geral: string
  ack_by?: string
  display_name?: string
  ack_at?: string
  resolved_by?: string
  resolved_at?: string
  resolution_note?: string
  snow_ticket?: string
}

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
  resolved_at?: string
  resolution_note?: string
  snow_ticket?: string
}

interface JobDetailRow {
  execution_id: string
  pipeline: string
  job_name: string
  task_id: string
  status: string
  inicio: string
  fim: string
  duration_seconds: number
}

interface DsLog {
  execution_id: string
  pipeline_name: string
  job_name: string
  project: string
  wave_number: number
  pid: number
  status: string
  status_code: number
  child_jobs: { name: string; status: string; status_code: number }[]
  log_summary: string
  ds_start_time: string
  ds_end_time: string
  queued_seconds: number
  created_at: string
  updated_at: string
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

// ── Airflow Log Modal ──────────────────────────────────────────────────────

interface AirflowLogState {
  pipeline: string
  executionId: string
  dagRunId?: string
  taskId?: string
}

function buildDagRunId(executionId: string): string {
  // ts_nodash "20260614T120000" → "scheduled__2026-06-14T12:00:00+00:00"
  const m = executionId.match(/(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})/)
  if (m) return `scheduled__${m[1]}-${m[2]}-${m[3]}T${m[4]}:${m[5]}:${m[6]}+00:00`
  return executionId
}

function AirflowLogModal({ state, onClose }: { state: AirflowLogState; onClose: () => void }) {
  const dagId = state.pipeline
  const [taskId, setTaskId] = useState(state.taskId ?? '')
  const [tryNum, setTryNum] = useState(1)
  const [logText, setLogText] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [err, setErr] = useState('')

  // Resolve dagRunId
  const dagRunId = state.dagRunId ?? buildDagRunId(state.executionId)

  const { data: tiData, isLoading: tiLoading } = useQuery({
    queryKey: ['airflow-ti', dagId, dagRunId],
    queryFn: () => apiFetch<{ task_instances: any[] }>(
      `/airflow/dags/${encodeURIComponent(dagId)}/dagRuns/${encodeURIComponent(dagRunId)}/taskInstances`
    ),
  })

  const tasks = (tiData?.task_instances ?? []).filter(
    t => !t.task_id.startsWith('log_') && !t.task_id.startsWith('teams_')
  ).sort((a: any, b: any) => {
    const order = ['FAILED', 'WARNING', 'SUCCESS', 'RUNNING', 'SKIPPED', 'UP_FOR_RETRY']
    return order.indexOf(a.state?.toUpperCase()) - order.indexOf(b.state?.toUpperCase())
  })

  const fetchLog = useCallback(async (tid: string, tn: number) => {
    setLoading(true)
    setErr('')
    setLogText(null)
    try {
      const res = await fetch(
        `/orquestra/airflow/dags/${encodeURIComponent(dagId)}/dagRuns/${encodeURIComponent(dagRunId)}/taskInstances/${encodeURIComponent(tid)}/logs/${tn}`,
        { headers: { Authorization: `Bearer ${localStorage.getItem('orquestra_token') ?? ''}` } }
      )
      const txt = await res.text()
      setLogText(txt)
    } catch (e: any) {
      setErr(e.message)
    } finally {
      setLoading(false)
    }
  }, [dagId, dagRunId])

  const airflowLink = `${AIRFLOW_UI}/dags/${dagId}/grid`

  function colorize(text: string) {
    return text.split('\n').map((line, i) => {
      const cls = /ERROR|EXCEPTION|CRITICAL/i.test(line) ? 'text-red-400'
        : /WARNING/i.test(line) ? 'text-amber-400'
        : /SUCCESS/i.test(line) ? 'text-green-400'
        : /^\[.*INFO/i.test(line) ? 'text-blue-300'
        : 'text-gray-300'
      return <div key={i} className={cls}>{line || ' '}</div>
    })
  }

  return (
    <Modal open title={`Log Airflow — ${state.pipeline}`} onClose={onClose} size="2xl">
      <div className="flex flex-col gap-3">
        {/* Task selector */}
        <div className="flex gap-2 items-end flex-wrap">
          {tiLoading ? (
            <span className="text-xs text-dim">Carregando tasks...</span>
          ) : (
            <div className="flex flex-col gap-1 flex-1 min-w-48">
              <label className="text-xs text-dim font-medium">Task</label>
              <select
                className="bg-panel border border-edge text-ink rounded-md px-3 py-1.5 text-sm"
                value={taskId}
                onChange={e => setTaskId(e.target.value)}
              >
                <option value="">Selecione uma task...</option>
                {tasks.map((t: any) => (
                  <option key={t.task_id} value={t.task_id}>
                    {t.task_id} ({t.state ?? 'N/A'})
                  </option>
                ))}
              </select>
            </div>
          )}
          <div className="flex flex-col gap-1">
            <label className="text-xs text-dim font-medium">Tentativa</label>
            <select
              className="bg-panel border border-edge text-ink rounded-md px-3 py-1.5 text-sm w-24"
              value={tryNum}
              onChange={e => setTryNum(Number(e.target.value))}
            >
              {[1,2,3].map(n => <option key={n} value={n}>{n}</option>)}
            </select>
          </div>
          <Button size="sm" onClick={() => taskId && fetchLog(taskId, tryNum)} disabled={!taskId || loading}>
            {loading ? '...' : <Search size={13} />} Carregar
          </Button>
          <a href={airflowLink} target="_blank" rel="noreferrer">
            <Button variant="secondary" size="sm"><ExternalLink size={13} /> Airflow</Button>
          </a>
        </div>

        {/* Log area */}
        {err && <p className="text-xs text-red-400">{err}</p>}
        {logText !== null && (
          <div className="relative">
            <div className="bg-gray-950 rounded-lg p-4 overflow-auto max-h-[60vh] font-mono text-xs leading-relaxed">
              {colorize(logText)}
            </div>
            <div className="absolute top-2 right-2 flex gap-2">
              <Button variant="secondary" size="sm" onClick={() => copyText(logText)}>
                <Copy size={11} /> Copiar
              </Button>
            </div>
          </div>
        )}
        {!logText && !loading && !err && (
          <p className="text-xs text-dim text-center py-8">Selecione uma task e clique em Carregar</p>
        )}
      </div>
    </Modal>
  )
}

// ── DataStage Log Modal ────────────────────────────────────────────────────

function DsLogModal({
  executionId, jobName, onClose,
}: { executionId: string; jobName: string; onClose: () => void }) {
  const { data, isLoading } = useQuery<{ total: number; logs: DsLog[] }>({
    queryKey: ['ds-log', executionId, jobName],
    queryFn: () => apiFetch(`/datastage/log?execution_id=${encodeURIComponent(executionId)}&job_name=${encodeURIComponent(jobName)}`),
  })

  const log = data?.logs?.[0]

  return (
    <Modal open title={`Log DataStage — ${jobName}`} onClose={onClose} size="xl">
      {isLoading ? <PageSpinner /> : !log ? (
        <p className="text-dim text-sm text-center py-8">Nenhum log encontrado.</p>
      ) : (
        <div className="flex flex-col gap-4">
          {/* Meta */}
          <div className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
            <div><span className="text-dim">Pipeline:</span> <span className="text-ink">{log.pipeline_name}</span></div>
            <div><span className="text-dim">Projeto:</span> <span className="text-ink">{log.project}</span></div>
            <div><span className="text-dim">Status:</span> <Badge value={log.status} /></div>
            <div><span className="text-dim">Status Code:</span> <span className="font-mono text-xs">{log.status_code}</span></div>
            <div><span className="text-dim">Início DS:</span> <span className="text-ink text-xs">{log.ds_start_time}</span></div>
            <div><span className="text-dim">Fim DS:</span> <span className="text-ink text-xs">{log.ds_end_time}</span></div>
            <div><span className="text-dim">Wave:</span> <span>{log.wave_number}</span></div>
            <div><span className="text-dim">PID:</span> <span className="font-mono text-xs">{log.pid}</span></div>
            {log.queued_seconds > 0 && (
              <div><span className="text-dim">Fila:</span> <span className="text-amber-400 text-xs">{durStr(log.queued_seconds)} em fila</span></div>
            )}
          </div>

          {/* Child jobs */}
          {log.child_jobs?.length > 0 && (
            <div>
              <p className="text-xs text-dim font-medium mb-2">Jobs filhos</p>
              <table className="w-full text-xs">
                <thead><tr className="text-dim border-b border-edge">
                  <th className="text-left pb-1">Job</th>
                  <th className="text-left pb-1">Status</th>
                  <th className="text-left pb-1">Código</th>
                </tr></thead>
                <tbody>
                  {log.child_jobs.map((c, i) => (
                    <tr key={i} className="border-b border-edge/40">
                      <td className="py-1 font-mono">{c.name}</td>
                      <td className="py-1"><Badge value={c.status} /></td>
                      <td className="py-1 font-mono text-dim">{c.status_code}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Log summary */}
          {log.log_summary && (
            <div>
              <div className="flex items-center justify-between mb-2">
                <p className="text-xs text-dim font-medium">Resumo do Log</p>
                <Button variant="ghost" size="sm" onClick={() => copyText(log.log_summary)}>
                  <Copy size={11} /> Copiar
                </Button>
              </div>
              <pre className="bg-gray-950 text-gray-300 text-xs font-mono p-4 rounded-lg overflow-auto max-h-72 leading-relaxed whitespace-pre-wrap">
                {log.log_summary.slice(0, 4000)}
                {log.log_summary.length > 4000 && '\n... (truncado)'}
              </pre>
            </div>
          )}
        </div>
      )}
    </Modal>
  )
}

// ── Log Detail Modal ───────────────────────────────────────────────────────

function LogDetailModal({
  row, onClose, onAirflowLog, onDsLog,
}: {
  row: ExecRow
  onClose: () => void
  onAirflowLog: (s: AirflowLogState) => void
  onDsLog: (executionId: string, jobName: string) => void
}) {
  const qc = useQueryClient()
  const user = useAuthStore(s => s.user)

  const { data: detailData, isLoading: detailLoading } = useQuery<{ data: JobDetailRow[] }>({
    queryKey: ['exec-detail', row.execution_id, row.pipeline],
    queryFn: () => apiFetch(`/execucoes?detail_mode=true&filter_execution_id=${encodeURIComponent(row.execution_id)}&filter_pipeline=${encodeURIComponent(row.pipeline)}&limit=200`),
  })

  const { data: avgData } = useQuery<{ data: Record<string, { avg: number; n: number }> }>({
    queryKey: ['exec-avg', row.pipeline],
    queryFn: () => apiFetch(`/execucoes/duracao-media?pipeline=${encodeURIComponent(row.pipeline)}`),
  })

  const rerunMut = useMutation({
    mutationFn: ({ pipeline_name, execution_id, task_id }: { pipeline_name: string; execution_id: string; task_id: string }) =>
      apiFetch('/execucoes/rerun', { method: 'POST', body: JSON.stringify({ pipeline_name, execution_id, task_id }) }),
    onSuccess: () => { toast.success('Reexecução disparada'); qc.invalidateQueries({ queryKey: ['execucoes'] }) },
    onError: (e: any) => toast.error(e.message),
  })

  const jobs = detailData?.data ?? []
  const avgs = avgData?.data ?? {}

  const statusOrder = ['FAILED', 'WARNING', 'RUNNING', 'SUCCESS']
  const sortedJobs = [...jobs].sort((a, b) =>
    statusOrder.indexOf(a.status) - statusOrder.indexOf(b.status)
  )

  // Runbook: only shown if execution has failures (no runbook data from API in this view,
  // but could be shown if pipeline data is fetched separately)
  const hasFail = row.jobs_falha > 0

  const dagId = row.pipeline

  return (
    <Modal open title={`Execução: ${row.pipeline}`} onClose={onClose} size="2xl">
      <div className="flex flex-col gap-4">
        {/* Header info */}
        <div className="grid grid-cols-3 gap-3 text-sm">
          <div><span className="text-dim">Execution ID:</span>
            <span className="font-mono text-xs ml-1 text-blue-400 cursor-pointer" onClick={() => copyText(row.execution_id)}>
              {row.execution_id} <Copy size={10} className="inline" />
            </span>
          </div>
          <div><span className="text-dim">Projeto:</span> <span className="text-ink ml-1">{row.project}</span></div>
          <div><span className="text-dim">Status:</span> <span className="ml-1"><Badge value={row.status_geral} /></span></div>
          <div><span className="text-dim">Início:</span> <span className="text-ink text-xs ml-1">{fmtDt(row.inicio)}</span></div>
          <div><span className="text-dim">Fim:</span> <span className="text-ink text-xs ml-1">{fmtDt(row.fim)}</span></div>
          <div><span className="text-dim">Duração:</span> <span className="text-ink ml-1">{durStr(row.duracao_total_segundos)}</span></div>
        </div>

        {/* Ack info */}
        {row.ack_by && (
          <div className="bg-green-900/20 border border-green-800 rounded-lg px-3 py-2 text-xs text-green-400">
            ✓ Reconhecida por <strong>{row.display_name ?? row.ack_by}</strong> em {fmtDt(row.ack_at)}
          </div>
        )}

        {/* Pipeline execution chain */}
        {jobs.length > 1 && (
          <div className="border border-edge rounded-lg bg-canvas px-3 py-3 overflow-x-auto">
            <p className="text-xs text-dim font-medium mb-2">Cadeia de execução</p>
            <div className="flex items-center gap-0">
              {[...jobs]
                .sort((a, b) => String(a.inicio || '').localeCompare(String(b.inicio || '')))
                .map((j, idx, arr) => {
                  const dotColor: Record<string, string> = {
                    SUCCESS: 'bg-green-500 ring-green-500/25',
                    FAILED: 'bg-red-500 ring-red-500/25',
                    WARNING: 'bg-amber-500 ring-amber-500/25',
                    RUNNING: 'bg-blue-500 ring-blue-500/25',
                  }
                  const dot = dotColor[j.status] ?? 'bg-slate-500 ring-slate-500/25'
                  const short = j.job_name.length > 22 ? j.job_name.slice(0, 20) + '…' : j.job_name
                  return (
                    <div key={j.job_name} className="flex items-center shrink-0">
                      <div
                        className="flex flex-col items-center"
                        style={{ minWidth: 90 }}
                        title={`${j.job_name} — ${j.status} (${durStr(j.duration_seconds)})`}
                      >
                        <div className={`w-3.5 h-3.5 rounded-full ring-4 ${dot}`} />
                        <span className="text-[9px] text-dim mt-1 max-w-[88px] truncate text-center leading-tight">
                          {short}
                        </span>
                        <span className="text-[9px] text-dim/60">{durStr(j.duration_seconds)}</span>
                      </div>
                      {idx < arr.length - 1 && (
                        <span className="text-edge text-sm mx-0.5 pb-4 shrink-0">→</span>
                      )}
                    </div>
                  )
                })}
            </div>
          </div>
        )}

        {/* Jobs table */}
        {detailLoading ? <PageSpinner /> : (
          <div className="overflow-auto">
            <table className="w-full text-xs">
              <thead><tr className="text-dim border-b border-edge">
                <th className="text-left px-2 py-1.5">Job</th>
                <th className="text-left px-2 py-1.5">Status</th>
                <th className="text-left px-2 py-1.5">Início</th>
                <th className="text-left px-2 py-1.5">Fim</th>
                <th className="text-left px-2 py-1.5">Duração</th>
                <th className="text-left px-2 py-1.5">vs Média</th>
                <th className="text-right px-2 py-1.5">Ações</th>
              </tr></thead>
              <tbody>
                {sortedJobs.map(j => {
                  const avg = avgs[j.job_name]?.avg
                  return (
                    <tr key={j.job_name} className="border-b border-edge/40 hover:bg-edge/20">
                      <td className="px-2 py-1.5 font-mono text-ink">{j.job_name}</td>
                      <td className="px-2 py-1.5"><Badge value={j.status} /></td>
                      <td className="px-2 py-1.5 text-dim">{fmtDt(j.inicio)}</td>
                      <td className="px-2 py-1.5 text-dim">{fmtDt(j.fim)}</td>
                      <td className="px-2 py-1.5 text-dim">{durStr(j.duration_seconds)}</td>
                      <td className="px-2 py-1.5">
                        {avg && j.duration_seconds ? devBadge(j.duration_seconds, avg) : <span className="text-dim">—</span>}
                      </td>
                      <td className="px-2 py-1.5 text-right flex justify-end gap-1">
                        <Button variant="ghost" size="sm" title="Log Airflow"
                          onClick={() => onAirflowLog({ pipeline: dagId, executionId: row.execution_id, taskId: j.task_id })}>
                          📋
                        </Button>
                        <Button variant="ghost" size="sm" title="Log DataStage"
                          onClick={() => onDsLog(row.execution_id, j.job_name)}>
                          ⬡
                        </Button>
                        {j.status === 'FAILED' && user?.perfil !== 'consulta' && (
                          <Button variant="ghost" size="sm" title="Reexecutar a partir daqui"
                            loading={rerunMut.isPending}
                            onClick={() => rerunMut.mutate({ pipeline_name: row.pipeline, execution_id: row.execution_id, task_id: j.task_id })}>
                            <RotateCcw size={11} />
                          </Button>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}

        {/* Footer actions */}
        <div className="flex gap-2 pt-2 border-t border-edge">
          <a href={`${AIRFLOW_UI}/dags/${dagId}/grid`} target="_blank" rel="noreferrer">
            <Button variant="secondary" size="sm"><ExternalLink size={13} /> Ver no Airflow</Button>
          </a>
          {hasFail && !row.ack_by && user?.perfil !== 'consulta' && (
            <AckButton executionId={row.execution_id} pipeline={row.pipeline} onDone={() => { qc.invalidateQueries({ queryKey: ['execucoes'] }); onClose() }} />
          )}
        </div>
      </div>
    </Modal>
  )
}

// ── Ack Button ─────────────────────────────────────────────────────────────

function AckButton({ executionId, pipeline, onDone }: { executionId: string; pipeline: string; onDone: () => void }) {
  const user = useAuthStore(s => s.user)
  const ackMut = useMutation({
    mutationFn: () => apiFetch('/execucoes/ack', {
      method: 'POST',
      body: JSON.stringify({
        execution_id: executionId,
        pipeline,
        user: user?.matricula,
        display_name: `${user?.primeiro_nome ?? ''} ${user?.ultimo_nome ?? ''}`.trim(),
      }),
    }),
    onSuccess: () => { toast.success('Falha reconhecida'); onDone() },
    onError: (e: any) => toast.error(e.message),
  })
  return (
    <Button variant="secondary" size="sm" loading={ackMut.isPending} onClick={() => ackMut.mutate()}>
      <CheckSquare size={13} /> Reconhecer falha
    </Button>
  )
}

// ── Factory Runs ───────────────────────────────────────────────────────────

function stepIcon(tipo: string) {
  const m: Record<string, string> = {
    reset: '🔄', gerada: '✅', erro: '❌', iniciando: '▶️', concluido: '🏁', info: 'ℹ️',
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
                      <span className={s.tipo === 'erro' ? 'text-red-400' : s.tipo === 'gerada' ? 'text-green-400' : 'text-dim'}>
                        {s.msg}
                      </span>
                    </div>
                  ))}
                  {logData.erros_lista?.length > 0 && (
                    <div className="mt-2 bg-red-900/20 border border-red-800 rounded p-2">
                      <p className="text-xs text-red-400 font-medium mb-1">Erros:</p>
                      {logData.erros_lista.map((e, i) => (
                        <p key={i} className="text-xs text-red-300">{e}</p>
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

  const [filters, setFilters] = useState<Filters>({
    projeto: '', pipeline: '', status: '', data_ini: '', exec_id: '', hours_back: '',
  })
  const [page, setPage] = useState(0)
  const [detail, setDetail] = useState<ExecRow | null>(null)
  const [airflowLog, setAirflowLog] = useState<AirflowLogState | null>(null)
  const [dsLog, setDsLog] = useState<{ executionId: string; jobName: string } | null>(null)

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
          onDsLog={(eid, jn) => { setDetail(null); setDsLog({ executionId: eid, jobName: jn }) }}
        />
      )}
      {airflowLog && <AirflowLogModal state={airflowLog} onClose={() => setAirflowLog(null)} />}
      {dsLog && <DsLogModal executionId={dsLog.executionId} jobName={dsLog.jobName} onClose={() => setDsLog(null)} />}
    </>
  )
}

// ── Resolve Modal ──────────────────────────────────────────────────────────

function ResolveModal({
  row, onClose,
}: { row: FalhaRow; onClose: () => void }) {
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
          <div className="bg-green-900/20 border border-green-800 rounded-lg p-3 text-xs text-green-300 flex flex-col gap-1">
            <div className="flex items-center gap-1.5 font-medium text-green-400">
              <CheckCircle2 size={13} /> Resolvida
            </div>
            <div>Por: <strong>{row.resolved_by}</strong> em {fmtDt(row.resolved_at)}</div>
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
              <Button variant="secondary" size="sm" loading={resolveMut.isPending}
                onClick={() => resolveMut.mutate(true)}>
                Desfazer resolução
              </Button>
              <Button variant="secondary" size="sm" onClick={onClose}>Fechar</Button>
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

// ── Gestão de Falhas Tab ───────────────────────────────────────────────────

function GestaoFalhasTab() {
  const qc = useQueryClient()
  const user = useAuthStore(s => s.user)
  const isViewer = user?.perfil === 'consulta'

  const [days, setDays] = useState(7)
  const [statusAck, setStatusAck] = useState('')
  const [filterPipeline, setFilterPipeline] = useState('')
  const [filterProject, setFilterProject] = useState('')
  const [page, setPage] = useState(0)
  const [resolveRow, setResolveRow] = useState<FalhaRow | null>(null)
  const FLIMIT = 50

  const qs = new URLSearchParams({
    days: String(days),
    offset: String(page * FLIMIT),
    limit: String(FLIMIT),
  })
  if (statusAck) qs.set('status_ack', statusAck)
  if (filterPipeline) qs.set('filter_pipeline', filterPipeline)
  if (filterProject) qs.set('filter_project', filterProject)

  const { data, isLoading, refetch } = useQuery<{ total: number; data: FalhaRow[] }>({
    queryKey: ['falhas', days, statusAck, filterPipeline, filterProject, page],
    queryFn: () => apiFetch(`/execucoes/falhas?${qs}`),
  })

  const ackMut = useMutation({
    mutationFn: (r: FalhaRow) => apiFetch('/execucoes/ack', {
      method: 'POST',
      body: JSON.stringify({
        execution_id: r.execution_id,
        pipeline: r.pipeline,
        user: user?.matricula,
        display_name: `${user?.primeiro_nome ?? ''} ${user?.ultimo_nome ?? ''}`.trim(),
      }),
    }),
    onSuccess: () => {
      toast.success('Falha assumida')
      qc.invalidateQueries({ queryKey: ['falhas'] })
      qc.invalidateQueries({ queryKey: ['falhas-summary'] })
    },
    onError: (e: any) => toast.error(e.message),
  })

  const rows = data?.data ?? []
  const total = data?.total ?? 0

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
            setStatusAck(''); setFilterPipeline(''); setFilterProject(''); setPage(0)
          }}>Limpar</Button>
          <Button size="sm" onClick={() => { setPage(0); refetch() }}><RefreshCw size={13} /></Button>
        </div>
      </div>

      {/* Table */}
      {isLoading ? <PageSpinner /> : (
        <div className="bg-panel border border-edge rounded-lg overflow-hidden">
          <div className="px-4 py-2 border-b border-edge">
            <span className="text-xs text-dim">{total} falha{total !== 1 ? 's' : ''}</span>
          </div>

          {rows.length === 0 ? (
            <p className="text-dim text-sm text-center py-12">Nenhuma falha encontrada no período.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead><tr className="text-dim border-b border-edge bg-canvas">
                  <th className="px-3 py-2 text-left">Pipeline</th>
                  <th className="px-3 py-2 text-left">Projeto</th>
                  <th className="px-3 py-2 text-left">Início</th>
                  <th className="px-3 py-2 text-left">Situação</th>
                  <th className="px-3 py-2 text-left">Assumida por</th>
                  <th className="px-3 py-2 text-left">Resolvida por</th>
                  <th className="px-3 py-2 text-left">Ticket</th>
                  <th className="px-3 py-2 text-right">Ações</th>
                </tr></thead>
                <tbody>
                  {rows.map(r => (
                    <tr key={`${r.execution_id}-${r.pipeline}`}
                      className={`border-b border-edge/40 hover:bg-edge/20 transition-colors ${r.resolved_at ? 'opacity-70' : ''}`}>
                      <td className="px-3 py-2 font-mono text-ink font-medium max-w-[220px] truncate" title={r.pipeline}>{r.pipeline}</td>
                      <td className="px-3 py-2 text-dim">{r.project}</td>
                      <td className="px-3 py-2 text-dim whitespace-nowrap">{fmtDt(r.inicio)}</td>
                      <td className="px-3 py-2">{statusAckLabel(r)}</td>
                      <td className="px-3 py-2 text-dim">
                        {r.ack_by ? (
                          <span title={fmtDt(r.ack_at) ?? ''}>{r.display_name ?? r.ack_by}</span>
                        ) : <span className="text-red-400/60">—</span>}
                      </td>
                      <td className="px-3 py-2 text-dim">
                        {r.resolved_by ? (
                          <span title={`${fmtDt(r.resolved_at)} · ${r.resolution_note ?? ''}`}>{r.resolved_by}</span>
                        ) : <span className="text-dim/40">—</span>}
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
                          {!isViewer && (
                            <Button
                              variant="ghost"
                              size="sm"
                              title={r.resolved_at ? 'Ver / editar resolução' : 'Marcar como resolvida'}
                              onClick={() => setResolveRow(r)}
                            >
                              <CheckCircle2 size={12} className={r.resolved_at ? 'text-green-400' : ''} />
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

      {resolveRow && <ResolveModal row={resolveRow} onClose={() => setResolveRow(null)} />}
    </div>
  )
}

// ── Root ───────────────────────────────────────────────────────────────────

export default function Logs() {
  const [tab, setTab] = useState('execucoes')

  return (
    <div className="flex flex-col gap-4">
      <Tabs
        tabs={[
          { id: 'execucoes', label: '≣ Execuções' },
          { id: 'gestao', label: '⚠ Gestão de Falhas' },
          { id: 'factory', label: '♻ Regeneração de DAGs' },
        ]}
        active={tab}
        onChange={setTab}
      />

      {tab === 'execucoes' && <ExecucoesTab />}
      {tab === 'gestao' && <GestaoFalhasTab />}
      {tab === 'factory' && <FactoryRuns />}
    </div>
  )
}
