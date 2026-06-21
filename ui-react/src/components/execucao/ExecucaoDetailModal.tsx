import { useState, useCallback } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiFetch } from '../../lib/api'
import { useAuthStore } from '../../store/auth'
import { copyToClipboard } from '../../lib/clipboard'
import { Badge } from '../ui/Badge'
import { Button } from '../ui/Button'
import { Modal } from '../ui/Modal'
import { PageSpinner } from '../ui/Spinner'
import { toast } from '../ui/Toast'
import {
  RotateCcw, CheckSquare, Copy, ExternalLink, Search,
  ChevronDown, ChevronRight, Share2,
} from 'lucide-react'
import { useAirflowUrl } from '../../lib/config'
import { MalhaTreeView } from '../MalhaTreeModal'

// ── helpers ────────────────────────────────────────────────────────────────

export function durStr(s?: number | null) {
  if (!s) return '-'
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = s % 60
  if (h > 0) return `${h}h ${m}m ${sec}s`
  return m > 0 ? `${m}m ${sec}s` : `${sec}s`
}

export function fmtDt(dt?: string | null) {
  if (!dt) return '-'
  try {
    const d = new Date(dt.replace(' ', 'T'))
    return d.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' }) + ' ' +
      d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  } catch { return dt }
}

export function copyText(t: string) {
  copyToClipboard(t).then(ok => ok ? toast.info('Copiado!') : toast.error('Erro ao copiar'))
}

function devBadge(durSec: number, avg: number) {
  const pct = Math.round(((durSec - avg) / avg) * 100)
  if (Math.abs(pct) < 10) return null
  const cls = pct >= 30 ? 'text-red-400' : pct > 0 ? 'text-amber-400' : 'text-green-400'
  return <span className={`text-xs font-mono ${cls}`}>{pct > 0 ? '+' : ''}{pct}%</span>
}

// ── types ──────────────────────────────────────────────────────────────────

export interface ExecRow {
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
  fila_total_segundos?: number | null
  ack_by?: string
  display_name?: string
  ack_at?: string
  resolved_by?: string
  resolved_display_name?: string
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
  fila_segundos?: number | null
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

export interface AirflowLogState {
  pipeline: string
  executionId: string
  dagRunId?: string
  taskId?: string
}

// ── Airflow Log Modal ──────────────────────────────────────────────────────

function buildDagRunId(executionId: string): string {
  const m = executionId.match(/(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})/)
  if (m) return `scheduled__${m[1]}-${m[2]}-${m[3]}T${m[4]}:${m[5]}:${m[6]}+00:00`
  return executionId
}

// logical_date do Airflow → ts_nodash (ex.: 2026-06-19T01:58:04+00:00 → 20260619T015804)
function toNodash(dt?: string | null): string {
  if (!dt) return ''
  const m = dt.match(/(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2}):(\d{2})/)
  return m ? `${m[1]}${m[2]}${m[3]}T${m[4]}${m[5]}${m[6]}` : ''
}

export function AirflowLogModal({ state, onClose }: { state: AirflowLogState; onClose: () => void }) {
  const dagId = state.pipeline
  const [taskId, setTaskId] = useState(state.taskId ?? '')
  const [tryNum, setTryNum] = useState(1)
  const [logText, setLogText] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [err, setErr] = useState('')

  // Resolve o dag_run_id REAL: runs manuais têm run_id 'manual_orq_...' (não
  // 'scheduled__...'), então casa pelo logical_date == execution_id (ts_nodash).
  const { data: runsData } = useQuery<{ dag_runs?: any[] }>({
    queryKey: ['airflow-dagruns', dagId],
    queryFn: () => apiFetch(`/airflow/dags/${encodeURIComponent(dagId)}/dagRuns?limit=100`),
    enabled: !state.dagRunId,
  })
  const matchedRun = (runsData?.dag_runs ?? []).find(
    r => toNodash(r.logical_date ?? r.execution_date) === state.executionId
  )
  const runsResolved = !!state.dagRunId || runsData !== undefined
  const dagRunId = state.dagRunId ?? matchedRun?.dag_run_id ?? buildDagRunId(state.executionId)

  const { data: tiData, isLoading: tiLoading } = useQuery({
    queryKey: ['airflow-ti', dagId, dagRunId],
    queryFn: () => apiFetch<{ task_instances: any[] }>(
      `/airflow/dags/${encodeURIComponent(dagId)}/dagRuns/${encodeURIComponent(dagRunId)}/taskInstances`
    ),
    enabled: runsResolved && !!dagRunId,
  })

  const tasks = (tiData?.task_instances ?? []).filter(
    t => !t.task_id.startsWith('log_') && !t.task_id.startsWith('teams_')
  ).sort((a: any, b: any) => {
    const order = ['FAILED', 'WARNING', 'SUCCESS', 'RUNNING', 'SKIPPED', 'UP_FOR_RETRY']
    return order.indexOf(a.state?.toUpperCase()) - order.indexOf(b.state?.toUpperCase())
  })

  const airflowUiUrl = useAirflowUrl()

  const fetchLog = useCallback(async (tid: string, tn: number) => {
    setLoading(true); setErr(''); setLogText(null)
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

  const airflowLink = `${airflowUiUrl}/dags/${dagId}/grid`

  function colorize(text: string) {
    return text.split('\n').map((line, i) => {
      const cls = /ERROR|EXCEPTION|CRITICAL/i.test(line) ? 'text-red-400'
        : /WARNING/i.test(line) ? 'text-amber-400'
        : /SUCCESS/i.test(line) ? 'text-green-400'
        : /^\[.*INFO/i.test(line) ? 'text-blue-300'
        : 'text-gray-300'
      return <div key={i} className={cls}>{line || ' '}</div>
    })
  }

  return (
    <Modal open title={`Log Airflow — ${state.pipeline}`} onClose={onClose} size="2xl">
      <div className="flex flex-col gap-3">
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

export function DsLogModal({
  executionId, jobName, pipelineName, onClose,
}: { executionId: string; jobName: string; pipelineName: string; onClose: () => void }) {
  const [showMalha, setShowMalha] = useState(true)
  const { data, isLoading } = useQuery<{ total: number; logs: DsLog[] }>({
    queryKey: ['ds-log', executionId, jobName, pipelineName],
    queryFn: () => apiFetch(`/datastage/log?execution_id=${encodeURIComponent(executionId)}&job_name=${encodeURIComponent(jobName)}&pipeline_name=${encodeURIComponent(pipelineName)}`),
  })

  const log = data?.logs?.[0]

  return (
    <Modal open title={`Log DataStage — ${jobName}`} onClose={onClose} size="xl">
      {isLoading ? <PageSpinner /> : (
        <div className="flex flex-col gap-4">
          {!log ? (
            <p className="text-dim text-sm text-center py-4">Nenhum log de execução encontrado para esta sequence.</p>
          ) : (
          <>
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
          </>
          )}

          {/* Malha do projeto (estrutura projetada — vínculo por nome do job) */}
          <div className="border border-edge rounded-lg overflow-hidden">
            <button
              onClick={() => setShowMalha(v => !v)}
              className="w-full flex items-center gap-2 px-3 py-2 bg-canvas/60 hover:bg-canvas text-left"
            >
              {showMalha ? <ChevronDown size={14} className="text-dim" /> : <ChevronRight size={14} className="text-dim" />}
              <Share2 size={13} className="text-[#1A5FA8]" />
              <span className="text-xs font-medium text-ink">Malha do projeto (estrutura projetada)</span>
              <span className="text-[10px] text-dim ml-auto">vínculo por nome</span>
            </button>
            {showMalha && (
              <div className="p-3">
                <MalhaTreeView jobName={jobName} enabled={showMalha} />
              </div>
            )}
          </div>
        </div>
      )}
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

// ── Log Detail Modal ───────────────────────────────────────────────────────

export function LogDetailModal({
  row, onClose, onAirflowLog, onDsLog,
}: {
  row: ExecRow
  onClose: () => void
  onAirflowLog: (s: AirflowLogState) => void
  onDsLog: (executionId: string, jobName: string, pipelineName: string) => void
}) {
  const qc = useQueryClient()
  const user = useAuthStore(s => s.user)
  const airflowUiUrl = useAirflowUrl()

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

  // Fila total: usa o sumarizado da execução ou soma o detalhe job a job
  const filaTotal = row.fila_total_segundos ?? jobs.reduce((s, j) => s + (j.fila_segundos ?? 0), 0)

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
          {filaTotal > 0 && (
            <div><span className="text-dim">Fila total:</span> <span className="text-amber-400 ml-1">{durStr(filaTotal)}</span></div>
          )}
        </div>

        {/* Ack info */}
        {row.ack_by && (
          <div className="bg-green-50 border border-green-200 dark:bg-green-900/20 dark:border-green-800 rounded-lg px-3 py-2 text-xs text-green-700 dark:text-green-400">
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
                <th className="text-left px-2 py-1.5">Fila</th>
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
                        {j.fila_segundos ? <span className="text-amber-400">{durStr(j.fila_segundos)}</span> : <span className="text-dim">—</span>}
                      </td>
                      <td className="px-2 py-1.5">
                        {avg && j.duration_seconds ? devBadge(j.duration_seconds, avg) : <span className="text-dim">—</span>}
                      </td>
                      <td className="px-2 py-1.5 text-right flex justify-end gap-1">
                        <Button variant="ghost" size="sm" title="Log Airflow"
                          onClick={() => onAirflowLog({ pipeline: dagId, executionId: row.execution_id, taskId: j.task_id })}>
                          📋
                        </Button>
                        <Button variant="ghost" size="sm" title="Log DataStage"
                          onClick={() => onDsLog(row.execution_id, j.job_name, row.pipeline)}>
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
          <a href={`${airflowUiUrl}/dags/${dagId}/grid`} target="_blank" rel="noreferrer">
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
