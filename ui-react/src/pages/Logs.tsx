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
} from 'lucide-react'

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

function statusColor(s: string) {
  const m: Record<string, string> = {
    SUCCESS: 'bg-green-500', FAILED: 'bg-red-500', WARNING: 'bg-amber-500', RUNNING: 'bg-blue-500',
  }
  return m[s] ?? 'bg-slate-500'
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

        {/* Mini pipeline graph */}
        {jobs.length > 0 && (
          <div className="flex flex-wrap gap-1.5 py-2">
            {jobs.map(j => (
              <div
                key={j.job_name}
                title={`${j.job_name}: ${j.status} (${durStr(j.duration_seconds)})`}
                className={`w-5 h-5 rounded-sm ${statusColor(j.status)} opacity-90 cursor-help`}
              />
            ))}
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

// ── Root ───────────────────────────────────────────────────────────────────

export default function Logs() {
  const [tab, setTab] = useState('execucoes')

  return (
    <div className="flex flex-col gap-4">
      <Tabs
        tabs={[
          { id: 'execucoes', label: '≣ Execuções' },
          { id: 'factory', label: '♻ Regeneração de DAGs' },
        ]}
        active={tab}
        onChange={setTab}
      />

      {tab === 'execucoes' && <ExecucoesTab />}
      {tab === 'factory' && <FactoryRuns />}
    </div>
  )
}
