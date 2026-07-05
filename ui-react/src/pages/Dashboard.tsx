import { useState, useMemo, useCallback, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { apiFetch } from '../lib/api'
import { PageSpinner } from '../components/ui/Spinner'
import { Select } from '../components/ui/Input'
import { Button } from '../components/ui/Button'
import {
  RefreshCw, AlertTriangle, CheckCircle, XCircle, Clock,
  Activity, Layers, BarChart2, ChevronRight, FileText,
} from 'lucide-react'
import {
  LogDetailModal, AirflowLogModal, DsLogModal,
  type ExecRow, type AirflowLogState,
} from '../components/execucao/ExecucaoDetailModal'

// ── types ──────────────────────────────────────────────────────────────────

interface KpiData {
  total_execucoes: number
  total_sucesso: number
  total_falha: number
  total_warning: number
  taxa_sucesso_pct: number
  duracao_media_segundos: number
  fila_media_segundos: number
  fila_max_segundos: number
  fila_jobs: number
  por_projeto: { project: string; execucoes: number; falhas: number; warnings: number }[]
  filter_project: string
}

interface PipelineStatus {
  pipeline: string
  project: string
  ultimo_status: string
  ultimo_inicio: string | null
  duracao_segundos: number
  fila_segundos?: number
  total_jobs: number
  execution_id: string
  criticidade: string
}

interface Falha {
  pipeline: string
  project: string
  job_name: string
  status: string
  inicio: string | null
  execution_id: string
  log_file: string | null
  situacao?: string
}

interface Executando {
  execution_id: string
  project: string
  pipeline: string
  inicio: string | null
  total_jobs: number
  jobs_running: number
  jobs_ok: number
  elapsed_seconds: number
}

interface AlertaPerf {
  execution_id: string
  project: string
  pipeline: string
  inicio: string | null
  elapsed_seconds: number
  alerta_horas: number
}

interface DashResponse {
  date_ref: string
  kpis: KpiData
  pipeline_status: PipelineStatus[]
  ultimas_falhas: Falha[]
  executando_agora: Executando[]
  alertas_perf: AlertaPerf[]
}

interface GanttItem {
  execution_id: string
  pipeline: string
  project: string
  inicio: string | null
  fim: string | null
  status: string
  total_jobs: number
  criticidade: string
}

// ── helpers ────────────────────────────────────────────────────────────────

const PROJETOS = ['Todos', 'BI_CVP', 'BI_VIDA', 'BI_PREVIDENCIA', 'BI_PRESTAMISTA']

const STATUS_COLOR: Record<string, string> = {
  SUCCESS: '#22c55e', FAILED: '#ef4444', WARNING: '#f59e0b',
  RUNNING: '#3b82f6', PENDING: '#6b7280', DESCONHECIDO: '#6b7280',
  SKIPPED: '#94a3b8',
}

const STATUS_LABEL: Record<string, string> = {
  SUCCESS: 'Sucesso', FAILED: 'Falha', WARNING: 'Aviso',
  RUNNING: 'Rodando', PENDING: 'Aguardando', SKIPPED: 'Pulada',
}

function fmtSec(s: number) {
  if (s < 60) return `${s}s`
  if (s < 3600) return `${Math.floor(s / 60)}m ${s % 60}s`
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  return `${h}h ${m}m`
}

function fmtTime(iso: string | null) {
  if (!iso) return '—'
  return iso.substring(11, 16)
}

function fmtDateTime(iso: string | null) {
  if (!iso) return '—'
  const d = iso.substring(8, 10), mo = iso.substring(5, 7)
  const h = iso.substring(11, 16)
  return `${d}/${mo} ${h}`
}

function todayBRT() {
  try {
    return new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Sao_Paulo' }).format(new Date())
  } catch {
    return new Date().toISOString().substring(0, 10)
  }
}

// ── status badge ───────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    SUCCESS:     'bg-green-100  dark:bg-green-900/30  text-green-700  dark:text-green-300  border-green-300  dark:border-green-700',
    FAILED:      'bg-red-100    dark:bg-red-900/30    text-red-700    dark:text-red-300    border-red-300    dark:border-red-700',
    WARNING:     'bg-amber-100  dark:bg-amber-900/30  text-amber-700  dark:text-amber-300  border-amber-300  dark:border-amber-700',
    RUNNING:     'bg-blue-100   dark:bg-blue-900/30   text-blue-700   dark:text-blue-300   border-blue-300   dark:border-blue-700',
    DESCONHECIDO:'bg-slate-100  dark:bg-slate-800/40  text-slate-600  dark:text-slate-400  border-slate-300  dark:border-slate-600',
    SKIPPED:     'bg-slate-100  dark:bg-slate-800/40  text-slate-600  dark:text-slate-400  border-slate-300  dark:border-slate-600',
  }
  const cls = colors[status] ?? colors['DESCONHECIDO']
  return (
    <span className={`inline-flex items-center justify-center w-20 py-0.5 rounded text-[10px] font-bold border ${cls}`}>
      {STATUS_LABEL[status] ?? status}
    </span>
  )
}

function SituacaoBadge({ situacao }: { situacao?: string }) {
  const s = situacao ?? 'Aguardando'
  const cls =
    s === 'Resolvido'  ? 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300 border-green-300 dark:border-green-700' :
    s === 'Em análise' ? 'bg-blue-100  dark:bg-blue-900/30  text-blue-700  dark:text-blue-300  border-blue-300  dark:border-blue-700' :
                         'bg-slate-100 dark:bg-slate-800/40 text-slate-600 dark:text-slate-400 border-slate-300 dark:border-slate-600'
  return (
    <span className={`inline-flex items-center justify-center w-24 py-0.5 rounded text-[10px] font-bold border ${cls}`}>
      {s}
    </span>
  )
}

function CritBadge({ crit }: { crit: string }) {
  const c = crit?.toUpperCase()
  const cls = c === 'ALTA' ? 'text-red-500 dark:text-red-400' : c === 'MEDIA' ? 'text-amber-500 dark:text-amber-400' : 'text-green-500 dark:text-green-400'
  if (!crit) return null
  return <span className={`text-[10px] font-bold ${cls}`}>{crit}</span>
}

// ── KPI card ───────────────────────────────────────────────────────────────

interface KpiProps {
  label: string
  value: React.ReactNode
  sub?: string
  icon: React.ReactNode
  color: 'blue' | 'green' | 'red' | 'yellow' | 'purple' | 'slate'
  onClick?: () => void
  pulse?: boolean
}

function KpiCard({ label, value, sub, icon, color, onClick, pulse }: KpiProps) {
  const bg: Record<string, string> = {
    blue:   'from-blue-500/10   to-blue-500/5   border-blue-500/20',
    green:  'from-green-500/10  to-green-500/5  border-green-500/20',
    red:    'from-red-500/10    to-red-500/5    border-red-500/20',
    yellow: 'from-amber-500/10  to-amber-500/5  border-amber-500/20',
    purple: 'from-purple-500/10 to-purple-500/5 border-purple-500/20',
    slate:  'from-slate-500/10  to-slate-500/5  border-slate-500/20',
  }
  const txt: Record<string, string> = {
    blue: 'text-blue-500 dark:text-blue-400', green: 'text-green-500 dark:text-green-400',
    red: 'text-red-500 dark:text-red-400', yellow: 'text-amber-500 dark:text-amber-400',
    purple: 'text-purple-500 dark:text-purple-400', slate: 'text-slate-500 dark:text-slate-400',
  }
  return (
    <div
      onClick={onClick}
      className={`bg-gradient-to-br ${bg[color]} border rounded-xl p-3.5 flex flex-col gap-1.5 ${onClick ? 'cursor-pointer hover:brightness-110 transition-all' : ''} ${pulse ? 'animate-pulse' : ''}`}
    >
      <div className="flex items-center justify-between">
        <span className="text-[10px] font-semibold text-dim uppercase tracking-wider">{label}</span>
        <span className={`${txt[color]} opacity-70`}>{icon}</span>
      </div>
      <div className={`text-2xl font-bold ${txt[color]}`}>{value}</div>
      {sub && <div className="text-[10px] text-dim">{sub}</div>}
    </div>
  )
}

// ── Gantt chart (SVG simples, sem biblioteca) ──────────────────────────────

function useNowBRT(enabled: boolean) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!enabled) return
    const id = setInterval(() => setNow(Date.now()), 30_000)
    return () => clearInterval(id)
  }, [enabled])
  return now
}

function GanttChart({ items, dateRef }: { items: GanttItem[]; dateRef: string }) {
  const sorted = useMemo(() => [...items].sort((a, b) => (a.inicio ?? '').localeCompare(b.inicio ?? '')), [items])

  const isToday = dateRef === todayBRT()
  const now = useNowBRT(isToday)

  if (sorted.length === 0) return null

  const dayStart = new Date(`${dateRef}T00:00:00-03:00`).getTime()
  const dayEnd   = new Date(`${dateRef}T23:59:59-03:00`).getTime()
  const span     = dayEnd - dayStart

  function pct(iso: string | null) {
    if (!iso) return 0
    const t = new Date(iso.replace(' ', 'T') + '-03:00').getTime()
    return Math.max(0, Math.min(100, ((t - dayStart) / span) * 100))
  }
  function width(ini: string | null, fim: string | null) {
    const s = pct(ini), e = pct(fim)
    return Math.max(0.3, e - s)
  }

  const nowPct = isToday ? Math.max(0, Math.min(100, ((now - dayStart) / span) * 100)) : null
  // Em foco: rodando agora, ou com início dentro de uma janela de ±15min do horário atual
  const FOCUS_WINDOW_MS = 15 * 60 * 1000
  function isInFocus(it: GanttItem) {
    if (!isToday) return false
    if (it.status === 'RUNNING') return true
    if (!it.inicio) return false
    const t = new Date(it.inicio.replace(' ', 'T') + '-03:00').getTime()
    return Math.abs(t - now) <= FOCUS_WINDOW_MS
  }

  const hourMarks = Array.from({ length: 25 }, (_, i) => i)

  return (
    <div className="overflow-x-auto">
      <div className="min-w-[720px]">
        {/* Hour axis */}
        <div className="flex ml-36 mr-20 mb-1 relative h-4">
          {hourMarks.map(h => (
            <div key={h} className="absolute text-[9px] text-dim" style={{ left: `${(h / 24) * 100}%` }}>
              {String(h).padStart(2, '0')}h
            </div>
          ))}
          {nowPct !== null && (
            <div className="absolute text-[9px] font-bold text-red-500" style={{ left: `${nowPct}%`, transform: 'translateX(-50%)' }}>
              agora
            </div>
          )}
        </div>
        {/* Rows */}
        <div className="flex flex-col gap-1">
          {sorted.map(it => {
            const focus = isInFocus(it)
            return (
              <div
                key={it.execution_id}
                className={`flex items-center group rounded transition-colors ${
                  focus ? 'bg-red-50 dark:bg-red-900/15 ring-1 ring-red-300/50 dark:ring-red-700/40' : ''
                }`}
              >
                <div className={`sticky left-0 z-20 w-36 flex-shrink-0 text-[10px] truncate text-right pr-2 ${focus ? 'bg-red-50 dark:bg-red-900/15 text-red-600 dark:text-red-300 font-semibold' : 'bg-panel text-dim'}`} title={it.pipeline}>
                  {it.pipeline}
                </div>
                <div className="flex-1 relative h-5 bg-edge/20 rounded">
                  {hourMarks.map(h => (
                    <div key={h} className="absolute top-0 bottom-0 border-l border-edge/20" style={{ left: `${(h / 24) * 100}%` }} />
                  ))}
                  {nowPct !== null && (
                    <div className="absolute top-0 bottom-0 w-px bg-red-500 z-10 pointer-events-none" style={{ left: `${nowPct}%` }} />
                  )}
                  <div
                    className={`absolute top-0.5 bottom-0.5 rounded ${it.status === 'RUNNING' ? 'animate-pulse' : ''}`}
                    style={{
                      left: `${pct(it.inicio)}%`,
                      width: `${width(it.inicio, it.fim)}%`,
                      backgroundColor: STATUS_COLOR[it.status] ?? '#6b7280',
                      opacity: it.status === 'RUNNING' ? 0.9 : 0.75,
                      boxShadow: focus ? '0 0 0 1px #ef4444' : undefined,
                    }}
                    title={`${it.pipeline} · ${it.status} · ${fmtTime(it.inicio)}–${fmtTime(it.fim)}`}
                  />
                </div>
                <div className={`sticky right-0 z-20 w-20 flex-shrink-0 flex justify-end items-center pl-1 ${focus ? 'bg-red-50 dark:bg-red-900/15' : 'bg-panel'}`}>
                  <StatusBadge status={it.status} />
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}

// ── Por projeto badges ─────────────────────────────────────────────────────

function ProjBadges({ items }: { items: KpiData['por_projeto'] }) {
  if (!items?.length) return null
  return (
    <div className="flex flex-wrap gap-2">
      {items.map(p => (
        <div key={p.project}
          className={`flex items-center gap-2 px-3 py-1.5 rounded-lg border text-xs font-medium ${
            p.falhas > 0 ? 'bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800 text-red-700 dark:text-red-300'
            : p.warnings > 0 ? 'bg-amber-50 dark:bg-amber-900/20 border-amber-200 dark:border-amber-800 text-amber-700 dark:text-amber-300'
            : 'bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800 text-green-700 dark:text-green-300'
          }`}>
          <span className="font-bold">{p.project}</span>
          <span className="opacity-60">{p.execucoes} exec</span>
          {p.falhas > 0 && <span className="text-red-600 dark:text-red-400 font-bold">{p.falhas} ✗</span>}
          {p.warnings > 0 && <span className="text-amber-600 dark:text-amber-400 font-bold">{p.warnings} ⚠</span>}
        </div>
      ))}
    </div>
  )
}

// Abre o modal de detalhe da execução (cadeia de jobs + logs) sem sair do dashboard.
function LogBtn({ onClick, className = '' }: { onClick: () => void; className?: string }) {
  return (
    <button
      onClick={e => { e.stopPropagation(); onClick() }}
      title="Ver execução e logs (sem sair do dashboard)"
      className={`text-dim hover:text-blue-500 transition-colors shrink-0 ${className}`}
    >
      <FileText size={13} />
    </button>
  )
}

// ── Alerta de performance ──────────────────────────────────────────────────

function AlertaRow({ a, onOpen, onDetail }: { a: AlertaPerf; onOpen: () => void; onDetail: () => void }) {
  const cls = a.alerta_horas >= 12
    ? 'border-red-300 dark:border-red-800 bg-red-50 dark:bg-red-900/20'
    : a.alerta_horas >= 6
    ? 'border-amber-400 dark:border-amber-700 bg-amber-50 dark:bg-amber-900/20'
    : 'border-yellow-300 dark:border-yellow-800 bg-yellow-50 dark:bg-yellow-900/20'
  const icon = a.alerta_horas >= 12 ? '🔴' : a.alerta_horas >= 6 ? '🟠' : '🟡'
  return (
    <div className={`flex items-center gap-3 px-4 py-2.5 border-b border-edge/40 last:border-0 ${cls} hover:brightness-95 transition-all cursor-pointer`} onClick={onOpen}>
      <span className="text-sm">{icon}</span>
      <div className="flex-1 min-w-0">
        <div className="font-mono text-xs font-medium text-ink truncate">{a.pipeline}</div>
        <div className="text-[10px] text-dim">{a.project} · início {fmtDateTime(a.inicio)}</div>
      </div>
      <span className="text-xs font-bold text-amber-600 dark:text-amber-400 flex-shrink-0">{fmtSec(a.elapsed_seconds)}</span>
      <LogBtn onClick={onDetail} />
      <ChevronRight size={13} className="text-dim flex-shrink-0" />
    </div>
  )
}

// ── Executando agora row ───────────────────────────────────────────────────

function RunningRow({ e, onOpen, onDetail }: { e: Executando; onOpen: () => void; onDetail: () => void }) {
  const pct = e.total_jobs > 0 ? Math.round((e.jobs_ok / e.total_jobs) * 100) : 0
  return (
    <div className="flex items-center gap-3 px-4 py-2.5 border-b border-edge/40 last:border-0 hover:bg-blue-50 dark:hover:bg-blue-900/10 transition-all cursor-pointer" onClick={onOpen}>
      <span className="relative flex h-2 w-2 flex-shrink-0">
        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75" />
        <span className="relative inline-flex rounded-full h-2 w-2 bg-blue-500" />
      </span>
      <div className="flex-1 min-w-0">
        <div className="font-mono text-xs font-medium text-ink truncate">{e.pipeline}</div>
        <div className="text-[10px] text-dim">{e.project} · {fmtSec(e.elapsed_seconds)} rodando</div>
        <div className="mt-1 h-1 bg-edge/30 rounded-full overflow-hidden w-full max-w-[120px]">
          <div className="h-full bg-blue-500 rounded-full transition-all" style={{ width: `${pct}%` }} />
        </div>
      </div>
      <div className="text-right flex-shrink-0">
        <div className="text-[10px] text-blue-500 dark:text-blue-400 font-bold">{e.jobs_running} rod.</div>
        <div className="text-[10px] text-dim">{e.jobs_ok}/{e.total_jobs} ok</div>
      </div>
      <LogBtn onClick={onDetail} />
    </div>
  )
}

// ── Dashboard principal ────────────────────────────────────────────────────

// Converte um item de "Rodando agora" / "Alerta de performance" no ExecRow que o
// modal de detalhe consome. O modal recarrega a cadeia de jobs pelo execution_id,
// então só os campos de cabeçalho precisam estar preenchidos.
function executandoToExecRow(e: Executando): ExecRow {
  return {
    execution_id: e.execution_id,
    project: e.project,
    pipeline: e.pipeline,
    inicio: e.inicio ?? '',
    fim: '',
    duracao_total_segundos: e.elapsed_seconds,
    total_jobs: e.total_jobs,
    jobs_ok: e.jobs_ok,
    jobs_falha: 0,
    jobs_warning: 0,
    jobs_running: e.jobs_running,
    status_geral: 'RUNNING',
    fila_total_segundos: null,
  }
}

function alertaToExecRow(a: AlertaPerf): ExecRow {
  return {
    execution_id: a.execution_id,
    project: a.project,
    pipeline: a.pipeline,
    inicio: a.inicio ?? '',
    fim: '',
    duracao_total_segundos: a.elapsed_seconds,
    total_jobs: 0,
    jobs_ok: 0,
    jobs_falha: 0,
    jobs_warning: 0,
    jobs_running: 0,
    status_geral: 'RUNNING',
    fila_total_segundos: null,
  }
}

function pipelineStatusToExecRow(p: PipelineStatus): ExecRow {
  return {
    execution_id: p.execution_id,
    project: p.project,
    pipeline: p.pipeline,
    inicio: p.ultimo_inicio ?? '',
    fim: '',
    duracao_total_segundos: p.duracao_segundos,
    total_jobs: p.total_jobs,
    jobs_ok: 0,
    jobs_falha: p.ultimo_status === 'FAILED' ? 1 : 0,
    jobs_warning: p.ultimo_status === 'WARNING' ? 1 : 0,
    jobs_running: p.ultimo_status === 'RUNNING' ? 1 : 0,
    status_geral: p.ultimo_status,
    fila_total_segundos: p.fila_segundos ?? null,
  }
}

export default function Dashboard() {
  const navigate = useNavigate()
  const [projeto,      setProjeto]      = useState('Todos')
  const [date,         setDate]         = useState(todayBRT())
  const [autoRefresh,  setAutoRefresh]  = useState(false)
  const [showGantt,    setShowGantt]    = useState(true)
  const [ganttFilter,  setGanttFilter]  = useState<'all' | 'running'>('all')
  const [detail,       setDetail]       = useState<ExecRow | null>(null)
  const [airflowLog,   setAirflowLog]   = useState<AirflowLogState | null>(null)
  const [dsLog,        setDsLog]        = useState<{ executionId: string; jobName: string; pipelineName: string } | null>(null)

  const qs = useMemo(() => {
    const p = new URLSearchParams({ date_ref: date })
    if (projeto !== 'Todos') p.set('filter_project', projeto)
    return p.toString()
  }, [projeto, date])

  const { data, isLoading, dataUpdatedAt, refetch } = useQuery<DashResponse>({
    queryKey: ['dashboard', projeto, date],
    queryFn: () => apiFetch(`/dashboard?${qs}`),
    refetchInterval: autoRefresh ? 60_000 : false,
  })

  const { data: ganttData, isLoading: ganttLoading } = useQuery<{ date_ref: string; data: GanttItem[] }>({
    queryKey: ['dashboard-gantt', projeto, date],
    queryFn: () => apiFetch(`/dashboard/gantt?${qs}`),
    refetchInterval: autoRefresh ? 60_000 : false,
  })
  const ganttRunningCount = ganttData?.data?.filter(it => it.status === 'RUNNING').length ?? 0
  const handleFalhaDrillDown = useCallback(() => {
    // "Ver todos": Logs filtrado por FALHA na data selecionada
    navigate(`/logs?status=FAILED&date=${date}`)
  }, [navigate, date])

  const kpis = data?.kpis
  const lastUpdate = dataUpdatedAt ? new Date(dataUpdatedAt).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' }) : null

  // Taxa de sucesso entre as execuções FINALIZADAS (estados terminais).
  // Não usar executando_agora aqui: ele conta runs de dias anteriores ainda
  // rodando, que não entram em total_execucoes (filtrado por data) — isso fazia
  // o denominador < numerador e a taxa estourar (ex.: 200%).
  const adjustedTaxa = useMemo(() => {
    if (!kpis) return 0
    const finished = kpis.total_sucesso + kpis.total_falha + kpis.total_warning
    return finished > 0 ? Math.min(100, (kpis.total_sucesso / finished) * 100) : 100
  }, [kpis])

  return (
    <div className="flex flex-col gap-5">

      {/* ── Toolbar ── */}
      <div className="bg-panel border border-edge rounded-xl px-4 py-3">
        <div className="flex flex-wrap items-center gap-3">
          <Select value={projeto} onChange={e => setProjeto(e.target.value)} className="w-44">
            {PROJETOS.map(p => <option key={p}>{p}</option>)}
          </Select>
          <input
            type="date"
            value={date}
            onChange={e => setDate(e.target.value)}
            className="bg-panel border border-edge text-ink rounded-md px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
          />
          <label className="flex items-center gap-1.5 text-xs text-dim cursor-pointer select-none">
            <input type="checkbox" checked={autoRefresh} onChange={e => setAutoRefresh(e.target.checked)} className="accent-blue-500" />
            Auto (1min)
          </label>
          {lastUpdate && <span className="text-[10px] text-dim hidden sm:block">Atualizado {lastUpdate}</span>}
          <Button variant="secondary" size="sm" onClick={() => refetch()} className="ml-auto">
            <RefreshCw size={13} /> Atualizar
          </Button>
        </div>
      </div>

      {isLoading && <PageSpinner />}

      {!isLoading && data && kpis && (
        <>
          {/* ── KPI Cards ── */}
          <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-3">
            <KpiCard
              label="Execuções"
              value={kpis.total_execucoes}
              sub={date === todayBRT() ? 'hoje' : date}
              icon={<BarChart2 size={16} />}
              color="blue"
            />
            <KpiCard
              label="Sucesso"
              value={`${adjustedTaxa.toFixed(1)}%`}
              sub={`${kpis.total_sucesso} de ${kpis.total_sucesso + kpis.total_falha + kpis.total_warning} finalizados`}
              icon={<CheckCircle size={16} />}
              color={adjustedTaxa >= 95 ? 'green' : adjustedTaxa >= 80 ? 'yellow' : 'red'}
            />
            <KpiCard
              label="Falhas"
              value={kpis.total_falha}
              icon={<XCircle size={16} />}
              color="red"
              onClick={kpis.total_falha > 0 ? handleFalhaDrillDown : undefined}
            />
            <KpiCard
              label="Avisos"
              value={kpis.total_warning}
              icon={<AlertTriangle size={16} />}
              color="yellow"
            />
            <KpiCard
              label="Rodando"
              value={data.executando_agora.length}
              icon={<Activity size={16} />}
              color="blue"
              pulse={data.executando_agora.length > 0}
            />
            <KpiCard
              label="Alerta Perf."
              value={data.alertas_perf.length}
              sub={data.alertas_perf.length > 0 ? `max ${fmtSec(Math.max(...data.alertas_perf.map(a => a.elapsed_seconds)))}` : undefined}
              icon={<Clock size={16} />}
              color={data.alertas_perf.length > 0 ? 'yellow' : 'slate'}
            />
            <KpiCard
              label="Fila DS (avg)"
              value={fmtSec(kpis.fila_media_segundos)}
              sub={kpis.fila_jobs > 0 ? `${kpis.fila_jobs} jobs` : 'sem fila'}
              icon={<Layers size={16} />}
              color="purple"
            />
          </div>

          {/* ── Por projeto ── */}
          {kpis.por_projeto?.length > 0 && (
            <ProjBadges items={kpis.por_projeto} />
          )}

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">

            {/* ── Rodando agora ── */}
            {data.executando_agora.length > 0 && (
              <div className="bg-panel border border-blue-200 dark:border-blue-900/50 rounded-xl overflow-hidden">
                <div className="px-4 py-2.5 border-b border-edge flex items-center gap-2">
                  <span className="relative flex h-2 w-2">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75" />
                    <span className="relative inline-flex rounded-full h-2 w-2 bg-blue-500" />
                  </span>
                  <h3 className="text-sm font-semibold text-blue-500 dark:text-blue-400">
                    Rodando agora ({data.executando_agora.length})
                  </h3>
                </div>
                {data.executando_agora.map(e => (
                  <RunningRow key={e.execution_id} e={e}
                    onOpen={() => navigate(`/logs?execution_id=${e.execution_id}&pipeline=${encodeURIComponent(e.pipeline)}`)}
                    onDetail={() => setDetail(executandoToExecRow(e))} />
                ))}
              </div>
            )}

            {/* ── Alertas de performance ── */}
            {data.alertas_perf.length > 0 && (
              <div className="bg-panel border border-amber-200 dark:border-amber-900/50 rounded-xl overflow-hidden">
                <div className="px-4 py-2.5 border-b border-edge">
                  <h3 className="text-sm font-semibold text-amber-600 dark:text-amber-400">
                    ⚠ Alertas de performance ({data.alertas_perf.length})
                  </h3>
                </div>
                {data.alertas_perf.map(a => (
                  <AlertaRow key={a.execution_id} a={a}
                    onOpen={() => navigate(`/logs?execution_id=${a.execution_id}&pipeline=${encodeURIComponent(a.pipeline)}`)}
                    onDetail={() => setDetail(alertaToExecRow(a))} />
                ))}
              </div>
            )}

          </div>

          {/* ── Últimas falhas ── */}
          {data.ultimas_falhas.length > 0 && (
            <div className="bg-panel border border-red-200 dark:border-red-900/50 rounded-xl overflow-hidden">
              <div className="px-4 py-2.5 border-b border-edge flex items-center justify-between">
                <h3 className="text-sm font-semibold text-red-500 dark:text-red-400">
                  Últimas falhas ({data.ultimas_falhas.length})
                </h3>
                <Button variant="ghost" size="sm" onClick={handleFalhaDrillDown} className="text-xs text-red-400">
                  Ver todos em Logs →
                </Button>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-[10px] text-dim border-b border-edge bg-canvas/50">
                      <th className="px-4 py-2 text-left">Pipeline</th>
                      <th className="px-4 py-2 text-left">Projeto</th>
                      <th className="px-4 py-2 text-left">Job</th>
                      <th className="px-4 py-2 text-left">Hora</th>
                      <th className="px-4 py-2 text-left">Status</th>
                      <th className="px-4 py-2 text-left">Situação</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.ultimas_falhas.map((f, i) => (
                      <tr key={`${f.execution_id}-${i}`}
                        className="border-b border-edge/40 last:border-0 hover:bg-red-50 dark:hover:bg-red-900/10 transition-colors cursor-pointer"
                        onClick={() => navigate(`/logs?execution_id=${f.execution_id}`)}>
                        <td className="px-4 py-2 font-mono text-[11px] text-ink font-medium">
                          <span className="truncate">{f.pipeline}</span>
                        </td>
                        <td className="px-4 py-2 text-xs text-dim">{f.project}</td>
                        <td className="px-4 py-2 font-mono text-[11px] text-dim">{f.job_name}</td>
                        <td className="px-4 py-2 text-xs text-dim">{fmtTime(f.inicio)}</td>
                        <td className="px-4 py-2"><StatusBadge status={f.status} /></td>
                        <td className="px-4 py-2"><SituacaoBadge situacao={f.situacao} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* ── Linha do tempo (Gantt) ── */}
          <div className="bg-panel border border-edge rounded-xl overflow-hidden">
            <button
              className="w-full px-4 py-2.5 border-b border-edge flex items-center justify-between hover:bg-canvas/50 transition-colors text-left"
              onClick={() => setShowGantt(v => !v)}
            >
              <h3 className="text-sm font-semibold text-ink flex items-center gap-2">
                Linha do tempo — {date}
                {ganttData?.data && <span className="text-dim font-normal text-xs">({ganttData.data.length} execuções)</span>}
                {ganttRunningCount > 0 && (
                  <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 text-[10px] font-bold">
                    <span className="relative flex h-1.5 w-1.5">
                      <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75" />
                      <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-blue-500" />
                    </span>
                    {ganttRunningCount} rodando
                  </span>
                )}
              </h3>
              <span className="text-dim text-xs">{showGantt ? '▲ ocultar' : '▼ expandir'}</span>
            </button>
            {showGantt && (
              <div className="p-4">
                {ganttLoading && <div className="text-center py-6 text-dim text-sm">Carregando…</div>}
                {!ganttLoading && (!ganttData?.data || ganttData.data.length === 0) && (
                  <div className="text-center py-8 text-dim text-sm">Nenhuma execução no período</div>
                )}
                {!ganttLoading && ganttData?.data && ganttData.data.length > 0 && (
                  <>
                    {/* Legenda status + filtro */}
                    <div className="flex items-center justify-between gap-4 mb-3 flex-wrap">
                      <div className="flex items-center gap-4 flex-wrap">
                        {Object.entries(STATUS_COLOR).slice(0, 4).map(([s, c]) => (
                          <span key={s} className="flex items-center gap-1 text-[10px] text-dim">
                            <span className="w-2.5 h-2.5 rounded-sm" style={{ backgroundColor: c }} />
                            {STATUS_LABEL[s]}
                          </span>
                        ))}
                      </div>
                      <div className="flex items-center gap-1 text-xs">
                        <button
                          className={`px-2.5 py-1 rounded-md transition-colors ${ganttFilter === 'all' ? 'bg-canvas border border-edge font-medium text-ink' : 'text-dim hover:text-ink'}`}
                          onClick={() => setGanttFilter('all')}
                        >
                          Todas ({ganttData.data.length})
                        </button>
                        <button
                          className={`px-2.5 py-1 rounded-md transition-colors ${ganttFilter === 'running' ? 'bg-canvas border border-edge font-medium text-ink' : 'text-dim hover:text-ink'}`}
                          onClick={() => setGanttFilter('running')}
                        >
                          Ativas ({ganttRunningCount})
                        </button>
                      </div>
                    </div>

                    {ganttFilter === 'running' && ganttRunningCount === 0 ? (
                      <div className="text-center py-8 text-dim text-sm">Nenhuma execução ativa neste momento</div>
                    ) : (
                      <GanttChart
                        items={ganttFilter === 'running' ? ganttData.data.filter(it => it.status === 'RUNNING') : ganttData.data}
                        dateRef={date}
                      />
                    )}
                  </>
                )}
              </div>
            )}
          </div>

          {/* ── Status por pipeline ── */}
          {data.pipeline_status.length > 0 && (
            <div className="bg-panel border border-edge rounded-xl overflow-hidden">
              <div className="px-4 py-2.5 border-b border-edge">
                <h3 className="text-sm font-semibold text-ink">
                  Status por pipeline
                  <span className="text-dim font-normal ml-2 text-xs">top {Math.min(5, data.pipeline_status.length)} por atividade recente</span>
                </h3>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-[10px] text-dim border-b border-edge bg-canvas/50">
                      <th className="px-4 py-2 text-left">Pipeline</th>
                      <th className="px-4 py-2 text-left">Projeto</th>
                      <th className="px-4 py-2 text-left">Crit.</th>
                      <th className="px-4 py-2 text-left">Status</th>
                      <th className="px-4 py-2 text-left">Última exec.</th>
                      <th className="px-4 py-2 text-left">Duração</th>
                      <th className="px-4 py-2 text-left">Fila total</th>
                      <th className="px-4 py-2 text-left">Etapas</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.pipeline_status.slice(0, 5).map(p => (
                      <tr key={p.pipeline}
                        className="border-b border-edge/40 last:border-0 hover:bg-edge/20 transition-colors cursor-pointer"
                        onClick={() => setDetail(pipelineStatusToExecRow(p))}>
                        <td className="px-4 py-2 font-mono text-[11px] text-ink font-medium max-w-[220px]" title={p.pipeline}>
                          <span className="truncate block">{p.pipeline}</span>
                        </td>
                        <td className="px-4 py-2 text-xs text-dim">{p.project}</td>
                        <td className="px-4 py-2"><CritBadge crit={p.criticidade} /></td>
                        <td className="px-4 py-2"><StatusBadge status={p.ultimo_status} /></td>
                        <td className="px-4 py-2 text-xs text-dim">{fmtDateTime(p.ultimo_inicio)}</td>
                        <td className="px-4 py-2 text-xs text-dim tabular-nums">{fmtSec(p.duracao_segundos)}</td>
                        <td className="px-4 py-2 text-xs text-dim tabular-nums">
                          {p.fila_segundos != null ? fmtSec(p.fila_segundos) : '—'}
                        </td>
                        <td className="px-4 py-2 text-xs text-dim">{p.total_jobs}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="px-4 py-2 border-t border-edge bg-canvas/30 text-[10px] text-dim leading-relaxed">
                Top 5 pipelines por <span className="text-ink/80 font-medium">atividade mais recente</span> (último início ou fim de execução) no dia selecionado — somente pipelines de produção.
                Para acompanhar tudo que está em execução neste momento, use o painel <span className="text-ink/80 font-medium">“Rodando agora”</span> no topo.
              </div>
            </div>
          )}

          {/* Estado vazio */}
          {!data.pipeline_status.length && !data.ultimas_falhas.length && !data.executando_agora.length && (
            <div className="bg-panel border border-edge rounded-xl py-20 flex flex-col items-center gap-2 text-dim">
              <BarChart2 size={36} className="opacity-20" />
              <p className="text-sm font-medium">Nenhuma execução em {date}</p>
              <p className="text-xs">Selecione outra data ou projeto.</p>
            </div>
          )}
        </>
      )}

      {/* Modais de detalhe de execução (reuso da tela de Logs) */}
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
    </div>
  )
}
