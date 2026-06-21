import { useState, useMemo, useRef, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiFetch } from '../../lib/api'
import { useAuthStore } from '../../store/auth'
import { Button } from '../ui/Button'
import { Input, Select, Textarea } from '../ui/Input'
import { Modal } from '../ui/Modal'
import { toast } from '../ui/Toast'
import { Save, Plus } from 'lucide-react'
import type { Pipeline, LineageJob } from '../../types/pipeline'
import {
  SCHEDULE_TYPES, SCHEDULE_LABELS, CRITICIDADES, AMBIENTES, MAX_MONTH_DAYS,
  JOB_TYPES, OBJECT_TYPES, DOW_LABELS,
  type WizJobType, type ScheduleConfig, type MonthDayEntry,
  hourlyTimes, parseCustomTimes, computeNextRuns, runsPerDay,
  typeBadgeColor, critColor, buildCron, parseMonthDaysTimes, serializeMonthDaysTimes,
} from './pipelineUtils'

// ── Sub-types ─────────────────────────────────────────────────────────────────

interface JobParamEntry {
  id: string
  param_name: string
  param_type: string
  param_value: string
}

const PARAM_TYPES = ['VARCHAR', 'INT', 'DATE', 'DATETIME', 'DECIMAL', 'BIT'] as const

interface JobEntry {
  id: string
  job_name: string
  job_type: WizJobType
  job_command: string
  execution_order: number
  ssh_conn_id: string
  verbose_log: boolean
  mssql_conn_id: string
  params: JobParamEntry[]
}

interface LineageEntry {
  id: string
  job_name: string
  direction: 'origem' | 'destino'
  object_name: string
  object_type: string
  database_name: string
}

interface FormState {
  pipeline_name: string
  project_name: string
  domain: string
  tags_list: string[]
  descricao: string
  schedule_type: string
  schedule_hour: number
  schedule_minute: number
  schedule_dow: number
  schedule_dom: number
  schedule_interval_hours: number
  schedule_start_hour: number
  schedule_end_hour: number
  schedule_custom_times: string
  schedule_weekdays: number[]
  schedule_month_days: MonthDayEntry[]
  somente_dias_uteis: boolean
  calendario_nome: string
  trigger_por_dependencia: boolean
  active: boolean
  dag_start_date: string
  envia_msg_inicio: boolean
  envia_msg_fim: boolean
  envia_msg_erro: boolean
  criticidade: string
  sla_minutos: string
  ambiente: string
  max_active_runs: number
  retries_count: number
  retry_delay_seconds: number
  pool_name: string
  depends_on: string
  runbook_md: string
  motivo_inativacao: string
}

// Resultado da sincronização da DAG no Airflow ao salvar (vem de /pipelines/register).
type DagSync = { attempted: boolean; exists: boolean | null; is_paused: boolean | null; error: string | null }

// Mensagem amigável sobre o efeito no Airflow (pausar/despausar a DAG).
function dagSyncMsg(ds?: DagSync | null): { ok: boolean; msg: string } {
  if (!ds || ds.attempted === false) return { ok: true, msg: '' }
  if (ds.error) return { ok: false, msg: `DAG não sincronizada no Airflow: ${ds.error}` }
  if (ds.exists === false) return { ok: true, msg: 'sem DAG no Airflow' }
  if (ds.is_paused === true)  return { ok: true, msg: 'DAG pausada no Airflow' }
  if (ds.is_paused === false) return { ok: true, msg: 'DAG ativada no Airflow' }
  return { ok: true, msg: '' }
}

const defaultForm = (): FormState => ({
  pipeline_name: '', project_name: '', domain: '', tags_list: [], descricao: '',
  schedule_type: 'daily', schedule_hour: 6, schedule_minute: 0,
  schedule_dow: 1, schedule_dom: 1, schedule_interval_hours: 2,
  schedule_start_hour: 8, schedule_end_hour: 18,
  schedule_custom_times: '', schedule_weekdays: [1, 2, 3, 4, 5], schedule_month_days: [],
  somente_dias_uteis: false, calendario_nome: '', trigger_por_dependencia: false,
  active: true, dag_start_date: '',
  envia_msg_inicio: true, envia_msg_fim: true, envia_msg_erro: true,
  criticidade: 'Media', sla_minutos: '', ambiente: 'PROD',
  max_active_runs: 1, retries_count: 1, retry_delay_seconds: 300,
  pool_name: '', depends_on: '', runbook_md: '', motivo_inativacao: '',
})

function pipelineToForm(p: Pipeline): FormState {
  const horarios = (p.horarios_especificos ?? '').trim()
  const diasRaw  = (p.dias_semana ?? '').trim()
  const weekdays = diasRaw ? diasRaw.split(',').map(s => parseInt(s.trim())).filter(n => !isNaN(n)) : [1, 2, 3, 4, 5]
  const monthDays = parseMonthDaysTimes(p.dias_horarios_mes)
  const schedType = monthDays.length > 0 ? 'monthly_days_times' : (horarios ? 'custom' : (p.schedule_type ?? 'daily'))
  return {
    ...defaultForm(),
    pipeline_name:           p.pipeline_name,
    project_name:            p.project_name ?? '',
    domain:                  p.domain ?? '',
    tags_list:               p.tags ? p.tags.split(',').map(t => t.trim()).filter(Boolean) : [],
    descricao:               p.descricao ?? '',
    schedule_type:           schedType,
    schedule_hour:           p.schedule_hour ?? 6,
    schedule_minute:         p.schedule_minute ?? 0,
    schedule_dow:            p.schedule_dow ?? 1,
    schedule_dom:            p.schedule_dom ?? 1,
    schedule_custom_times:   horarios,
    schedule_weekdays:       weekdays,
    schedule_month_days:     monthDays,
    somente_dias_uteis:      !!p.somente_dias_uteis,
    calendario_nome:         p.calendario_nome ?? '',
    trigger_por_dependencia: !!p.trigger_por_dependencia,
    active:                  !!p.active,
    dag_start_date:          p.dag_start_date ?? '',
    envia_msg_inicio:        !!p.envia_msg_inicio,
    envia_msg_fim:           !!p.envia_msg_fim,
    envia_msg_erro:          !!p.envia_msg_erro,
    criticidade:             p.criticidade ?? 'Media',
    sla_minutos:             p.sla_minutos != null ? String(p.sla_minutos) : '',
    ambiente:                p.ambiente ?? 'PROD',
    max_active_runs:         p.max_active_runs ?? 1,
    retries_count:           p.retries_count ?? 1,
    retry_delay_seconds:     p.retry_delay_seconds ?? 300,
    pool_name:               p.pool_name ?? '',
    depends_on:              p.depends_on ?? '',
    runbook_md:              p.runbook_md ?? '',
    motivo_inativacao:       p.motivo_inativacao ?? '',
  }
}

// ── TagsInput ─────────────────────────────────────────────────────────────────

function TagsInput({ value, onChange }: { value: string[]; onChange: (v: string[]) => void }) {
  const [input, setInput] = useState('')

  function addTag(raw: string) {
    const parts = raw.split(/[,;]/).map(s => s.trim().toUpperCase()).filter(Boolean)
    if (!parts.length) return
    const next = [...value]
    parts.forEach(t => { if (!next.includes(t)) next.push(t) })
    onChange(next)
    setInput('')
  }

  function removeTag(t: string) { onChange(value.filter(x => x !== t)) }

  return (
    <div className="flex flex-col gap-1">
      <label className="text-xs text-dim font-medium">Tags * <span className="text-dim/50 font-normal">(Enter ou vírgula para adicionar)</span></label>
      <div className="min-h-[42px] flex flex-wrap gap-1.5 items-center bg-panel border border-edge rounded-md px-2 py-1.5 focus-within:ring-1 focus-within:ring-blue-500">
        {value.map(t => (
          <span key={t} className="inline-flex items-center gap-1 bg-blue-100 text-blue-700 border border-blue-300 dark:bg-blue-600/25 dark:text-blue-200 dark:border-blue-600/50 rounded-full px-2 py-0.5 text-xs font-semibold">
            {t}
            <button type="button" onClick={() => removeTag(t)} className="hover:text-red-500 transition-colors leading-none">×</button>
          </span>
        ))}
        <input
          type="text"
          value={input}
          placeholder={value.length === 0 ? 'ex: COBRANCA, DIARIO…' : ''}
          className="flex-1 min-w-[120px] bg-transparent outline-none text-sm text-ink placeholder:text-dim/50"
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => {
            if (e.key === 'Enter' || e.key === ',') { e.preventDefault(); addTag(input) }
            if (e.key === 'Backspace' && input === '' && value.length > 0) removeTag(value[value.length - 1])
          }}
          onBlur={() => { if (input.trim()) addTag(input) }}
        />
      </div>
    </div>
  )
}

// ── Wizard stepper ────────────────────────────────────────────────────────────

const STEPS = ['Identificação', 'Agendamento', 'Notificações', 'Jobs', 'Lineage', 'Revisão'] as const
type Step = 0 | 1 | 2 | 3 | 4 | 5

function Stepper({ step, setStep, errors }: { step: Step; setStep: (s: Step) => void; errors: Record<number, string[]> }) {
  return (
    <div className="flex items-center gap-0 mb-1">
      {STEPS.map((label, i) => {
        const hasErr = (errors[i]?.length ?? 0) > 0
        const active = i === step
        const done   = i < step && !hasErr
        return (
          <button
            key={i}
            type="button"
            onClick={() => setStep(i as Step)}
            className="flex items-center gap-0 group"
          >
            <div className="flex flex-col items-center">
              <div className={`w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-bold border transition-colors
                ${hasErr ? 'bg-red-500 border-red-500 text-white' :
                  active ? 'bg-blue-600 border-blue-600 text-white' :
                  done   ? 'bg-green-600 border-green-600 text-white' :
                           'bg-panel border-edge text-dim'}`}>
                {hasErr ? '!' : done ? '✓' : i + 1}
              </div>
              <span className={`text-[9px] mt-0.5 whitespace-nowrap transition-colors
                ${hasErr ? 'text-red-500 font-semibold' : active ? 'text-blue-600 dark:text-blue-300 font-semibold' : done ? 'text-green-600 dark:text-green-400' : 'text-dim'}`}>
                {label}
              </span>
            </div>
            {i < STEPS.length - 1 && (
              <div className={`w-6 h-0.5 mt-[-10px] mx-0.5 transition-colors
                ${i < step ? 'bg-green-500' : 'bg-edge'}`} />
            )}
          </button>
        )
      })}
    </div>
  )
}

// ── PipelineFormModal (wizard) ────────────────────────────────────────────────

export function PipelineFormModal({ pipeline, onClose }: { pipeline?: Pipeline; onClose: () => void }) {
  const qc     = useQueryClient()
  const user   = useAuthStore(s => s.user)
  const isEdit = !!pipeline

  const [form,  setForm]  = useState<FormState>(pipeline ? pipelineToForm(pipeline) : defaultForm())
  const [step,  setStep]  = useState<Step>(0)
  const [stepErrors, setStepErrors] = useState<Record<number, string[]>>({})
  const [jobs,  setJobs]  = useState<JobEntry[]>([])
  const [lineage, setLineage] = useState<LineageEntry[]>([])

  const { data: projData } = useQuery<{ projects: string[] }>({
    queryKey: ['pipeline-projects'],
    queryFn: () => apiFetch('/pipelines/projects'),
    staleTime: 300_000,
  })
  const projects = projData?.projects ?? []

  // Domínios já existentes — para autocompletar e evitar variações parecidas
  const { data: domData } = useQuery<{ domains: string[] }>({
    queryKey: ['pipeline-domains'],
    queryFn: () => apiFetch('/pipelines/domains'),
    staleTime: 300_000,
  })
  const domains = domData?.domains ?? []

  const { data: allPipes } = useQuery<{ data: Pipeline[] }>({
    queryKey: ['pipelines', '', '', '', 0],
    queryFn: () => apiFetch('/pipelines?limit=200'),
    staleTime: 60_000,
  })
  const otherPipelines = (allPipes?.data ?? [])
    .map(p => p.pipeline_name)
    .filter(n => n !== form.pipeline_name)

  const { data: calData } = useQuery<{ calendarios: { calendario_nome: string; datas: number }[] }>({
    queryKey: ['agenda-calendarios'],
    queryFn: () => apiFetch('/agenda/calendarios'),
    staleTime: 300_000,
  })
  const calendarios = calData?.calendarios ?? []

  const { data: sshData } = useQuery<{ connections: { conn_id: string; host: string }[] }>({
    queryKey: ['ssh-connections'],
    queryFn: () => apiFetch('/airflow/connections/ssh'),
    staleTime: 300_000,
  })
  const sshConns = sshData?.connections ?? []

  const { data: mssqlData } = useQuery<{ connections: { conn_id: string; host: string }[] }>({
    queryKey: ['mssql-connections'],
    queryFn: () => apiFetch('/airflow/connections/mssql'),
    staleTime: 300_000,
  })
  const mssqlConns = mssqlData?.connections ?? []

  const editName = pipeline?.pipeline_name
  const { data: editJobs } = useQuery<{ data: { job_name: string; execution_order: number; job_type: string; job_command: string | null; ssh_conn_id: string | null; verbose_log: boolean }[] }>({
    queryKey: ['wizard-edit-jobs', editName],
    queryFn: () => apiFetch(`/jobs?limit=200&filter_pipeline=${encodeURIComponent(editName!)}`),
    enabled: isEdit && !!editName,
  })
  const { data: editLineage } = useQuery<{ jobs: LineageJob[] }>({
    queryKey: ['wizard-edit-lineage', editName],
    queryFn: () => apiFetch(`/lineage?pipeline_name=${encodeURIComponent(editName!)}`),
    enabled: isEdit && !!editName,
  })
  const populatedRef = useRef(false)
  useEffect(() => {
    if (!isEdit || populatedRef.current || !editJobs) return
    populatedRef.current = true
    const rows = [...(editJobs.data ?? [])].sort((a, b) => a.execution_order - b.execution_order)
    setJobs(rows.map((j, i) => ({
      id: `j_${i}_${Math.random().toString(36).slice(2, 7)}`,
      job_name: j.job_name,
      job_type: (JOB_TYPES.includes(j.job_type as WizJobType) ? j.job_type : 'datastage') as WizJobType,
      job_command: j.job_command ?? '',
      execution_order: j.execution_order,
      ssh_conn_id: j.ssh_conn_id ?? '',
      verbose_log: !!j.verbose_log,
      mssql_conn_id: '',
      params: [],
    })))
    const storedprocJobs = rows.filter(j => j.job_type === 'storedproc')
    Promise.all(storedprocJobs.map(j =>
      apiFetch<{ mssql_conn_id: string | null; params: { param_name: string; param_type: string; param_value: string | null }[] }>(
        `/pipelines/jobs/${encodeURIComponent(editName!)}/${encodeURIComponent(j.job_name)}`,
      ).then(detail => ({ job_name: j.job_name, detail })).catch(() => null),
    )).then(results => {
      setJobs(prev => prev.map(je => {
        const found = results.find(r => r && r.job_name === je.job_name)
        if (!found) return je
        return {
          ...je,
          mssql_conn_id: found.detail.mssql_conn_id ?? '',
          params: (found.detail.params ?? []).map((p, ppi) => ({
            id: `p_${ppi}_${Math.random().toString(36).slice(2, 7)}`,
            param_name: p.param_name, param_type: p.param_type, param_value: p.param_value ?? '',
          })),
        }
      }))
    })
    const lin: LineageEntry[] = []
    ;(editLineage?.jobs ?? []).forEach(lj => {
      ;(lj.origens || []).forEach(o => lin.push({
        id: `l_${Math.random().toString(36).slice(2, 8)}`, job_name: lj.job_name, direction: 'origem',
        object_name: o.object_name, object_type: o.object_type || 'Tabela', database_name: o.database_name ?? '',
      }))
      ;(lj.destinos || []).forEach(o => lin.push({
        id: `l_${Math.random().toString(36).slice(2, 8)}`, job_name: lj.job_name, direction: 'destino',
        object_name: o.object_name, object_type: o.object_type || 'Tabela', database_name: o.database_name ?? '',
      }))
    })
    setLineage(lin)
  }, [isEdit, editJobs, editLineage])

  function f<K extends keyof FormState>(k: K, v: FormState[K]) {
    setForm(prev => ({ ...prev, [k]: v }))
  }

  const schedCfg: ScheduleConfig = {
    type: form.schedule_type,
    hour: form.schedule_hour, minute: form.schedule_minute,
    dow: form.schedule_dow, dom: form.schedule_dom,
    intervalH: form.schedule_interval_hours,
    startH: form.schedule_start_hour, endH: form.schedule_end_hour,
    customTimes: form.schedule_custom_times,
    weekdays: form.schedule_weekdays,
    businessDaysOnly: form.somente_dias_uteis,
    monthDays: form.schedule_month_days.map(e => ({ dia: e.dia, horarios: parseCustomTimes(e.horariosRaw) })),
  }
  const showBizToggle = !['custom', 'on_demand', 'monthly_days_times'].includes(form.schedule_type)
  const nextRuns = useMemo(
    () => computeNextRuns(schedCfg, form.schedule_type === 'biweekly' ? 2 : 5),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [JSON.stringify(schedCfg)],
  )
  const perDay   = runsPerDay(schedCfg)

  function validateStep(s: number): string[] {
    if (s === 0) {
      const e: string[] = []
      if (!form.pipeline_name.trim()) e.push('Nome do pipeline é obrigatório')
      if (!form.project_name)         e.push('Projeto é obrigatório')
      if (!form.domain.trim())        e.push('Domínio é obrigatório')
      if (form.tags_list.length === 0) e.push('Ao menos uma tag é obrigatória')
      if (!form.descricao.trim())     e.push('Descrição é obrigatória')
      if (!form.active && form.motivo_inativacao.trim().length < 5)
        e.push('Motivo da inativação é obrigatório (mín. 5 caracteres)')
      return e
    }
    if (s === 1) {
      const e: string[] = []
      const t = form.schedule_type
      if (t === 'on_demand') return []
      if (t === 'hourly_n') {
        if (form.schedule_interval_hours < 1 || form.schedule_interval_hours > 23) e.push('Intervalo deve ser entre 1 e 23 horas')
        if (form.schedule_start_hour < 0 || form.schedule_start_hour > 23) e.push('Hora de início inválida (0–23)')
        if (form.schedule_end_hour < 0 || form.schedule_end_hour > 23) e.push('Hora de término inválida (0–23)')
        if (form.schedule_end_hour < form.schedule_start_hour) e.push('Hora de término deve ser ≥ hora de início')
        if (form.schedule_minute < 0 || form.schedule_minute > 59) e.push('Minuto inválido (0–59)')
      } else if (t === 'custom') {
        if (parseCustomTimes(form.schedule_custom_times).length === 0) e.push('Informe ao menos um horário válido (HH:MM)')
        if (form.schedule_weekdays.length === 0) e.push('Selecione ao menos um dia da semana')
      } else if (t === 'monthly_days_times') {
        if (form.schedule_month_days.length === 0) e.push('Adicione ao menos um dia do mês')
        const seenDias = new Set<number>()
        form.schedule_month_days.forEach(entry => {
          if (seenDias.has(entry.dia)) e.push(`Dia ${entry.dia} duplicado`)
          seenDias.add(entry.dia)
          const times = parseCustomTimes(entry.horariosRaw)
          if (times.length === 0) e.push(`Dia ${entry.dia}: informe ao menos um horário válido (HH:MM)`)
          if (times.length > 5) e.push(`Dia ${entry.dia}: no máximo 5 horários`)
        })
      } else {
        if (form.schedule_hour < 0 || form.schedule_hour > 23) e.push('Hora inválida (0–23)')
        if (form.schedule_minute < 0 || form.schedule_minute > 59) e.push('Minuto inválido (0–59)')
        if (t === 'weekly' && (form.schedule_dow < 0 || form.schedule_dow > 6)) e.push('Dia da semana inválido')
        if (t === 'monthly' && (form.schedule_dom < 1 || form.schedule_dom > 28)) e.push('Dia do mês inválido (1–28)')
        if (t === 'biweekly' && (form.schedule_dom < 1 || form.schedule_dom > 13)) e.push('Dia da 1ª quinzena inválido (1–13)')
      }
      return e
    }
    if (s === 3) {
      const e: string[] = []
      jobs.forEach((j, i) => {
        if (!j.job_name.trim()) e.push(`Job #${i + 1}: nome é obrigatório`)
        if (j.job_type === 'shell' && !j.ssh_conn_id) e.push(`Job "${j.job_name || i + 1}": servidor SSH é obrigatório para tipo shell`)
        if (j.job_type === 'storedproc') {
          if (!j.mssql_conn_id) e.push(`Job "${j.job_name || i + 1}": conexão MSSQL é obrigatória para tipo storedproc`)
          const nomesVistos = new Set<string>()
          j.params.forEach((p, pi) => {
            const nome = p.param_name.trim()
            if (!nome) e.push(`Job "${j.job_name || i + 1}": parâmetro #${pi + 1} sem nome definido`)
            if (!p.param_type) e.push(`Job "${j.job_name || i + 1}": parâmetro #${pi + 1} sem tipo de dado definido`)
            const key = nome.replace(/^@/, '').toLowerCase()
            if (nome && nomesVistos.has(key)) e.push(`Job "${j.job_name || i + 1}": parâmetro "${nome}" duplicado`)
            nomesVistos.add(key)
          })
        }
      })
      const names = jobs.map(j => j.job_name.trim()).filter(Boolean)
      const dups = [...new Set(names.filter((n, i) => names.indexOf(n) !== i))]
      if (dups.length) e.push(`Jobs com nomes duplicados: ${dups.join(', ')}`)
      return e
    }
    return []
  }

  function goNext() {
    const e = validateStep(step)
    if (e.length) {
      setStepErrors(prev => ({ ...prev, [step]: e }))
      return
    }
    setStepErrors(prev => ({ ...prev, [step]: [] }))
    if (step < 5) setStep((step + 1) as Step)
  }

  function goPrev() { if (step > 0) setStep((step - 1) as Step) }

  function buildSchedulePayload() {
    const t = form.schedule_type
    const h = String(form.schedule_hour).padStart(2, '0')
    const m = String(form.schedule_minute).padStart(2, '0')
    const base: Record<string, unknown> = {
      schedule_dow: form.schedule_dow,
      schedule_dom: form.schedule_dom,
      somente_dias_uteis: form.somente_dias_uteis ? 1 : 0,
      calendario_nome: form.calendario_nome.trim() || null,
      horarios_especificos: null,
      dias_semana: null,
      dias_horarios_mes: null,
    }
    if (t === 'hourly_n') {
      return {
        ...base,
        scheduled_time: `${String(form.schedule_start_hour).padStart(2, '0')}:${m}:00`,
        schedule_type: 'custom',
        schedule_hour: form.schedule_start_hour,
        schedule_minute: form.schedule_minute,
        horarios_especificos: hourlyTimes(schedCfg).join(','),
      }
    }
    if (t === 'custom') {
      return {
        ...base,
        scheduled_time: `${(parseCustomTimes(form.schedule_custom_times)[0] ?? '06:00')}:00`,
        schedule_type: 'custom',
        schedule_hour: parseInt((parseCustomTimes(form.schedule_custom_times)[0] ?? '06:00').slice(0, 2)),
        schedule_minute: parseInt((parseCustomTimes(form.schedule_custom_times)[0] ?? '06:00').slice(3)),
        horarios_especificos: parseCustomTimes(form.schedule_custom_times).join(','),
        dias_semana: [...form.schedule_weekdays].sort((a, b) => a - b).join(','),
      }
    }
    if (t === 'monthly_days_times') {
      const serialized = serializeMonthDaysTimes(form.schedule_month_days)
      const firstTime = schedCfg.monthDays?.find(e => e.horarios.length > 0)?.horarios[0] ?? '06:00'
      return {
        ...base,
        scheduled_time: `${firstTime}:00`,
        schedule_type: 'monthly_days_times',
        schedule_hour: parseInt(firstTime.slice(0, 2)),
        schedule_minute: parseInt(firstTime.slice(3)),
        dias_horarios_mes: serialized,
      }
    }
    return {
      ...base,
      scheduled_time: `${h}:${m}:00`,
      schedule_type: t,
      schedule_hour: form.schedule_hour,
      schedule_minute: form.schedule_minute,
    }
  }

  const saveMut = useMutation({
    mutationFn: async () => {
      const pname = form.pipeline_name.trim().toUpperCase()
      const body: Record<string, unknown> = {
        pipeline_name:       pname,
        project_name:        form.project_name,
        domain:              form.domain.trim().toUpperCase(),
        tags:                form.tags_list.join(','),
        descricao:           form.descricao.trim() || null,
        active:              form.active ? 1 : 0,
        motivo_inativacao:   form.active ? null : (form.motivo_inativacao.trim() || null),
        dag_start_date:      form.dag_start_date || null,
        envia_msg_inicio:    form.envia_msg_inicio ? 1 : 0,
        envia_msg_fim:       form.envia_msg_fim ? 1 : 0,
        envia_msg_erro:      form.envia_msg_erro ? 1 : 0,
        criticidade:         form.criticidade,
        sla_minutos:         form.sla_minutos ? parseInt(form.sla_minutos) : null,
        ambiente:            form.ambiente,
        max_active_runs:     form.max_active_runs,
        retries_count:       form.retries_count,
        retry_delay_seconds: form.retry_delay_seconds,
        pool_name:           form.pool_name.trim() || null,
        depends_on:          form.depends_on.trim() || null,
        trigger_por_dependencia: form.trigger_por_dependencia ? 1 : 0,
        runbook_md:          form.runbook_md.trim() || null,
        changed_by:          user?.matricula ?? 'react-ui',
        dag_criada:          pipeline?.dag_criada ?? 0,
        ...buildSchedulePayload(),
      }
      const reg = await apiFetch<{ dag_sync?: DagSync | null }>('/pipelines/register', { method: 'POST', body: JSON.stringify(body) })
      const dagSync = reg?.dag_sync ?? null

      const validJobs = jobs.filter(j => j.job_name.trim())
        .sort((a, b) => a.execution_order - b.execution_order)
      if (validJobs.length > 0) {
        const jobsPayload = validJobs.map(j => {
          const origens  = lineage.filter(l => l.job_name === j.job_name && l.direction === 'origem' && l.object_name.trim())
          const destinos = lineage.filter(l => l.job_name === j.job_name && l.direction === 'destino' && l.object_name.trim())
          const mapObj = (l: LineageEntry) => ({
            object_name:   l.object_name.trim(),
            object_type:   l.object_type || 'Tabela',
            database_name: l.database_name.trim() || null,
            extraction_method: 'manual',
          })
          return {
            job_name:        j.job_name.trim(),
            execution_order: j.execution_order,
            job_type:        j.job_type || 'datastage',
            job_command:     j.job_command.trim() || null,
            ssh_conn_id:     j.job_type === 'shell' ? (j.ssh_conn_id || null) : null,
            verbose_log:     j.job_type === 'datastage' ? j.verbose_log : false,
            mssql_conn_id:   j.job_type === 'storedproc' ? (j.mssql_conn_id || null) : null,
            params:          j.job_type === 'storedproc'
              ? j.params.filter(p => p.param_name.trim()).map(p => ({
                  param_name: p.param_name.trim(), param_type: p.param_type, param_value: p.param_value,
                }))
              : [],
            origens:         origens.map(mapObj),
            destinos:        destinos.map(mapObj),
            transformacoes:  [],
            operacao:        'upsert',
          }
        })
        try {
          await apiFetch('/pipelines/jobs/register', {
            method: 'POST',
            body: JSON.stringify({ pipeline_name: pname, require_lineage: false, jobs: jobsPayload }),
          })
        } catch (e: any) {
          return { pname, jobsError: e?.message || 'erro ao salvar jobs', dagSync }
        }
      }
      return { pname, dagSync }
    },
    onSuccess: (res: { pname: string; jobsError?: string; dagSync?: DagSync | null }) => {
      qc.invalidateQueries({ queryKey: ['pipelines'] })
      qc.invalidateQueries({ queryKey: ['jobs'] })
      if (res.jobsError) {
        toast.error(`Pipeline salvo, mas os jobs falharam: ${res.jobsError}. Edite o pipeline para reenviar.`)
        setStepErrors(prev => ({ ...prev, 5: [`Pipeline salvo, mas os jobs falharam: ${res.jobsError}`] }))
        return
      }
      const dag = dagSyncMsg(res.dagSync)
      const base = isEdit ? 'Pipeline atualizado!' : 'Pipeline criado com sucesso!'
      if (!dag.ok) toast.error(`${base} Atenção: ${dag.msg}`)
      else toast.success(dag.msg ? `${base} · ${dag.msg}` : base)
      onClose()
    },
    onError: (e: any) => {
      setStepErrors(prev => ({ ...prev, 5: [e?.message || 'Erro ao salvar pipeline'] }))
    },
  })

  function validateAllAndSave() {
    const allErrors: Record<number, string[]> = {}
    let firstBad = -1
    for (const s of [0, 1, 3]) {
      const e = validateStep(s)
      if (e.length) { allErrors[s] = e; if (firstBad < 0) firstBad = s }
    }
    if (firstBad >= 0) {
      setStepErrors(prev => ({ ...prev, ...allErrors }))
      setStep(firstBad as Step)
      return
    }
    saveMut.mutate()
  }

  function addJob() {
    setJobs(prev => [...prev, {
      id: `j_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`,
      job_name: '',
      job_type: 'datastage',
      job_command: '',
      execution_order: prev.length + 1,
      ssh_conn_id: '',
      verbose_log: false,
      mssql_conn_id: '',
      params: [],
    }])
  }

  function removeJob(id: string) {
    const job = jobs.find(j => j.id === id)
    setJobs(prev => prev.filter(j => j.id !== id))
    if (job) setLineage(prev => prev.filter(l => l.job_name !== job.job_name))
  }

  function updateJob(id: string, patch: Partial<JobEntry>) {
    const job = jobs.find(j => j.id === id)
    if (job && patch.job_name !== undefined && patch.job_name !== job.job_name) {
      const oldName = job.job_name
      setLineage(prevL => prevL.map(l => l.job_name === oldName ? { ...l, job_name: patch.job_name! } : l))
    }
    setJobs(prev => prev.map(j => j.id === id ? { ...j, ...patch } : j))
  }

  const [expandedParams, setExpandedParams] = useState<Set<string>>(new Set())
  function toggleParams(jobId: string) {
    setExpandedParams(prev => {
      const next = new Set(prev)
      if (next.has(jobId)) next.delete(jobId); else next.add(jobId)
      return next
    })
  }
  function addParam(jobId: string) {
    setJobs(prev => prev.map(j => j.id !== jobId ? j : {
      ...j, params: [...j.params, {
        id: `p_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`,
        param_name: '', param_type: 'VARCHAR', param_value: '',
      }],
    }))
    setExpandedParams(prev => new Set(prev).add(jobId))
  }
  function removeParam(jobId: string, paramId: string) {
    setJobs(prev => prev.map(j => j.id !== jobId ? j : { ...j, params: j.params.filter(p => p.id !== paramId) }))
  }
  function updateParam(jobId: string, paramId: string, patch: Partial<JobParamEntry>) {
    setJobs(prev => prev.map(j => j.id !== jobId ? j : {
      ...j, params: j.params.map(p => p.id === paramId ? { ...p, ...patch } : p),
    }))
  }

  function addLineageEntry(job_name: string, direction: 'origem' | 'destino') {
    setLineage(prev => [...prev, {
      id: `l_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`,
      job_name, direction,
      object_name: '', object_type: 'Tabela', database_name: '',
    }])
  }

  function removeLineageEntry(id: string) { setLineage(prev => prev.filter(l => l.id !== id)) }

  function updateLineage(id: string, field: keyof LineageEntry, value: string) {
    setLineage(prev => prev.map(l => l.id === id ? { ...l, [field]: value } : l))
  }

  const curStepErrors = stepErrors[step] ?? []

  return (
    <Modal open title={isEdit ? `Editar: ${pipeline!.pipeline_name}` : 'Novo Pipeline'} onClose={onClose} size="xl">
      <div className="flex flex-col gap-4">

        <Stepper step={step} setStep={setStep} errors={stepErrors} />

        {curStepErrors.length > 0 && (
          <div className="bg-red-50 border border-red-200 dark:bg-red-900/20 dark:border-red-800 rounded-lg px-3 py-2">
            {curStepErrors.map((e, i) => (
              <p key={i} className="text-xs text-red-700 dark:text-red-400">⚠ {e}</p>
            ))}
          </div>
        )}

        {/* ── STEP 0: IDENTIFICAÇÃO ── */}
        {step === 0 && (
          <div className="flex flex-col gap-3 overflow-y-auto max-h-[55vh] pr-1">
            <Input
              label="Nome do pipeline *"
              value={form.pipeline_name}
              onChange={e => f('pipeline_name', e.target.value.toUpperCase())}
              placeholder="ex: ETL_COBRANCA_DIARIA"
              disabled={isEdit}
              className={`font-mono ${isEdit ? 'opacity-60' : ''}`}
            />
            {!isEdit && <p className="text-[10px] text-dim -mt-2">Apenas letras, números e _ (será convertido para maiúsculas)</p>}

            <div className="grid grid-cols-2 gap-3">
              <Select label="Projeto *" value={form.project_name} onChange={e => f('project_name', e.target.value)}>
                <option value="">Selecione…</option>
                {projects.map(p => <option key={p}>{p}</option>)}
              </Select>
              <div className="flex flex-col gap-1">
                <label className="text-xs text-dim font-medium">Domínio *</label>
                <input
                  type="text"
                  list="pipeline-domains"
                  value={form.domain}
                  onChange={e => f('domain', e.target.value.toUpperCase())}
                  placeholder="ex: COBRANCA"
                  className="bg-panel border border-edge text-ink rounded-md px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
                />
                <datalist id="pipeline-domains">
                  {domains.map(d => <option key={d} value={d} />)}
                </datalist>
                {domains.length > 0 && (
                  <p className="text-[10px] text-dim/70">
                    {domains.length} domínio(s) já em uso — selecione um existente para padronizar.
                  </p>
                )}
              </div>
            </div>

            <TagsInput value={form.tags_list} onChange={v => f('tags_list', v)} />

            <Textarea label="Descrição *" value={form.descricao} onChange={e => f('descricao', e.target.value)}
              rows={3} placeholder="Descreva a finalidade deste pipeline, fonte de dados, consumidores…" />

            <div className="grid grid-cols-3 gap-3">
              <Select label="Criticidade" value={form.criticidade} onChange={e => f('criticidade', e.target.value)}>
                {CRITICIDADES.map(c => <option key={c}>{c}</option>)}
              </Select>
              <Select label="Ambiente" value={form.ambiente} onChange={e => f('ambiente', e.target.value)}>
                {AMBIENTES.map(a => <option key={a}>{a}</option>)}
              </Select>
              <Input label="SLA (minutos)" type="number" value={form.sla_minutos}
                onChange={e => f('sla_minutos', e.target.value)} placeholder="ex: 60" />
            </div>

            <label className="flex items-center gap-2 cursor-pointer">
              <input type="checkbox" checked={form.active} onChange={e => f('active', e.target.checked)} className="accent-blue-500" />
              <span className="text-sm text-ink">Pipeline ativo</span>
            </label>

            {!form.active && (
              <div className="flex flex-col gap-1 bg-amber-50 dark:bg-amber-900/10 border border-amber-200 dark:border-amber-800/40 rounded-lg p-3">
                <Textarea
                  label="Motivo da inativação *"
                  rows={2}
                  value={form.motivo_inativacao}
                  onChange={e => f('motivo_inativacao', e.target.value)}
                  placeholder="Ex.: aguardando correção da origem X / migração em andamento / solicitado pela área Y…"
                />
                <span className="text-[11px] text-dim">
                  Obrigatório ao inativar. Fica visível na lista e nos detalhes do pipeline,
                  para a equipe saber por que o fluxo está indisponível para execução.
                </span>
              </div>
            )}
          </div>
        )}

        {/* ── STEP 1: AGENDAMENTO ── */}
        {step === 1 && (
          <div className="flex flex-col gap-3 overflow-y-auto max-h-[55vh] pr-1">
            <Select label="Tipo de agendamento" value={form.schedule_type} onChange={e => f('schedule_type', e.target.value)}>
              {SCHEDULE_TYPES.map(t => <option key={t} value={t}>{SCHEDULE_LABELS[t]}</option>)}
            </Select>

            {form.schedule_type === 'hourly_n' && (
              <div className="flex flex-col gap-3">
                <div className="grid grid-cols-2 gap-2">
                  <div className="flex flex-col gap-1">
                    <label className="text-xs text-dim font-medium">A cada quantas horas? (1–23)</label>
                    <input type="number" min={1} max={23} value={form.schedule_interval_hours}
                      onChange={e => f('schedule_interval_hours', Math.min(23, Math.max(1, parseInt(e.target.value) || 1)))}
                      className="bg-panel border border-edge text-ink rounded-md px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500" />
                  </div>
                  <div className="flex flex-col gap-1">
                    <label className="text-xs text-dim font-medium">Minuto (0–59)</label>
                    <input type="number" min={0} max={59} value={form.schedule_minute}
                      onChange={e => f('schedule_minute', Math.min(59, Math.max(0, parseInt(e.target.value) || 0)))}
                      className="bg-panel border border-edge text-ink rounded-md px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500" />
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <div className="flex flex-col gap-1">
                    <label className="text-xs text-dim font-medium">Começa às (hora 0–23)</label>
                    <input type="number" min={0} max={23} value={form.schedule_start_hour}
                      onChange={e => f('schedule_start_hour', Math.min(23, Math.max(0, parseInt(e.target.value) || 0)))}
                      className="bg-panel border border-edge text-ink rounded-md px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500" />
                  </div>
                  <div className="flex flex-col gap-1">
                    <label className="text-xs text-dim font-medium">Termina às (hora 0–23)</label>
                    <input type="number" min={0} max={23} value={form.schedule_end_hour}
                      onChange={e => f('schedule_end_hour', Math.min(23, Math.max(0, parseInt(e.target.value) || 0)))}
                      className="bg-panel border border-edge text-ink rounded-md px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500" />
                  </div>
                </div>
                <p className="text-[10px] text-dim">Ex: a cada 2h entre 08 e 18 → roda às 08, 10, 12, 14, 16 e 18.</p>
              </div>
            )}

            {form.schedule_type === 'custom' && (
              <div className="flex flex-col gap-3">
                <div className="flex flex-col gap-1">
                  <label className="text-xs text-dim font-medium">Horários de execução</label>
                  <input type="text" value={form.schedule_custom_times}
                    onChange={e => f('schedule_custom_times', e.target.value)}
                    placeholder="ex: 09:00, 10:30, 13:00, 15:30"
                    className="bg-panel border border-edge text-ink rounded-md px-3 py-1.5 text-sm font-mono focus:outline-none focus:ring-1 focus:ring-blue-500" />
                  <p className="text-[10px] text-dim">Vários horários separados por vírgula no formato <span className="font-mono">HH:MM</span>.</p>
                </div>
                <div className="flex flex-col gap-1">
                  <label className="text-xs text-dim font-medium">Dias da semana</label>
                  <div className="flex flex-wrap gap-1.5">
                    {DOW_LABELS.map(([v, l]) => {
                      const on = form.schedule_weekdays.includes(v)
                      return (
                        <button key={v} type="button"
                          onClick={() => f('schedule_weekdays', on ? form.schedule_weekdays.filter(d => d !== v) : [...form.schedule_weekdays, v])}
                          className={`px-2.5 py-1 rounded-md text-xs font-medium border transition-colors ${on
                            ? 'bg-blue-600 border-blue-600 text-white'
                            : 'bg-panel border-edge text-dim hover:text-ink'}`}>
                          {l}
                        </button>
                      )
                    })}
                  </div>
                </div>
              </div>
            )}

            {form.schedule_type === 'monthly_days_times' && (
              <div className="flex flex-col gap-3">
                {form.schedule_month_days.map((entry, di) => {
                  const usedDays = new Set(form.schedule_month_days.map(x => x.dia))
                  const times = parseCustomTimes(entry.horariosRaw)
                  return (
                    <div key={di} className="bg-canvas border border-edge rounded-lg p-3 flex flex-col gap-2">
                      <div className="flex items-center gap-2">
                        <label className="text-xs text-dim font-medium shrink-0">Dia do mês</label>
                        <select value={entry.dia}
                          onChange={e => {
                            const dia = parseInt(e.target.value)
                            f('schedule_month_days', form.schedule_month_days.map((x, i) => i === di ? { ...x, dia } : x))
                          }}
                          className="bg-panel border border-edge text-ink rounded-md px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500">
                          {Array.from({ length: 28 }, (_, i) => i + 1)
                            .filter(d => d === entry.dia || !usedDays.has(d))
                            .map(d => <option key={d} value={d}>{d}</option>)}
                        </select>
                        <button type="button"
                          onClick={() => f('schedule_month_days', form.schedule_month_days.filter((_, i) => i !== di))}
                          className="ml-auto text-xs text-red-400 hover:text-red-300">Remover dia</button>
                      </div>
                      <input type="text" value={entry.horariosRaw}
                        onChange={e => f('schedule_month_days', form.schedule_month_days.map((x, i) =>
                          i === di ? { ...x, horariosRaw: e.target.value } : x))}
                        placeholder="ex: 09:00, 14:00, 18:00"
                        className="bg-panel border border-edge text-ink rounded-md px-3 py-1.5 text-sm font-mono focus:outline-none focus:ring-1 focus:ring-blue-500" />
                      <p className="text-[10px] text-dim">
                        {times.length > 0
                          ? `${times.length} horário${times.length > 1 ? 's' : ''}: ${times.join(', ')}`
                          : 'Informe ao menos um horário válido (HH:MM)'}
                      </p>
                    </div>
                  )
                })}
                {form.schedule_month_days.length < MAX_MONTH_DAYS && (
                  <button type="button"
                    onClick={() => {
                      const used = new Set(form.schedule_month_days.map(x => x.dia))
                      const nextDia = Array.from({ length: 28 }, (_, i) => i + 1).find(d => !used.has(d)) ?? 1
                      f('schedule_month_days', [...form.schedule_month_days, { dia: nextDia, horariosRaw: '' }])
                    }}
                    className="self-start text-xs text-blue-400 hover:text-blue-300 font-medium border border-edge rounded-md px-3 py-1.5">
                    + Adicionar dia
                  </button>
                )}
                <p className="text-[10px] text-dim">Até 5 dias do mês, cada um com até 5 horários próprios (ex: dia 1 às 09:00 · dia 15 às 14:00 e 18:00).</p>
              </div>
            )}

            {!['on_demand', 'hourly_n', 'custom', 'monthly_days_times'].includes(form.schedule_type) && (
              <>
                <div className="grid grid-cols-2 gap-2">
                  <div className="flex flex-col gap-1">
                    <label className="text-xs text-dim font-medium">Hora (0–23)</label>
                    <input type="number" min={0} max={23} value={form.schedule_hour}
                      onChange={e => f('schedule_hour', Math.min(23, Math.max(0, parseInt(e.target.value) || 0)))}
                      className="bg-panel border border-edge text-ink rounded-md px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500" />
                  </div>
                  <div className="flex flex-col gap-1">
                    <label className="text-xs text-dim font-medium">Minuto (0–59)</label>
                    <input type="number" min={0} max={59} value={form.schedule_minute}
                      onChange={e => f('schedule_minute', Math.min(59, Math.max(0, parseInt(e.target.value) || 0)))}
                      className="bg-panel border border-edge text-ink rounded-md px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500" />
                  </div>
                </div>
                {form.schedule_type === 'weekly' && (
                  <Select label="Dia da semana" value={form.schedule_dow} onChange={e => f('schedule_dow', parseInt(e.target.value))}>
                    {[['0','Domingo'],['1','Segunda'],['2','Terça'],['3','Quarta'],['4','Quinta'],['5','Sexta'],['6','Sábado']].map(([v,l]) =>
                      <option key={v} value={v}>{l}</option>)}
                  </Select>
                )}
                {(form.schedule_type === 'monthly' || form.schedule_type === 'biweekly') && (
                  <div className="flex flex-col gap-1">
                    <label className="text-xs text-dim font-medium">
                      {form.schedule_type === 'biweekly' ? 'Dia da 1ª quinzena (1–13)' : 'Dia do mês (1–28)'}
                    </label>
                    <input type="number" min={1} max={form.schedule_type === 'biweekly' ? 13 : 28} value={form.schedule_dom}
                      onChange={e => {
                        const cap = form.schedule_type === 'biweekly' ? 13 : 28
                        f('schedule_dom', Math.min(cap, Math.max(1, parseInt(e.target.value) || 1)))
                      }}
                      className="bg-panel border border-edge text-ink rounded-md px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500" />
                    {form.schedule_type === 'biweekly' &&
                      <p className="text-[10px] text-dim">Roda neste dia e 15 dias depois (ex: dia 1 → roda nos dias 1 e 16).</p>}
                  </div>
                )}
              </>
            )}

            {showBizToggle && (
              <label className="flex items-center gap-2 cursor-pointer bg-canvas border border-edge rounded-lg px-3 py-2">
                <input type="checkbox" checked={form.somente_dias_uteis}
                  onChange={e => f('somente_dias_uteis', e.target.checked)} className="accent-blue-500" />
                <span className="text-sm text-ink">Somente dias úteis (não roda sáb/dom)</span>
              </label>
            )}

            {form.schedule_type !== 'on_demand' && (
              <div className="flex flex-col gap-1">
                <label className="text-xs text-dim font-medium">Calendário de bloqueio (opcional)</label>
                <select value={form.calendario_nome} onChange={e => f('calendario_nome', e.target.value)}
                  className="bg-panel border border-edge text-ink rounded-md px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500">
                  <option value="">— nenhum —</option>
                  {calendarios.map(c => (
                    <option key={c.calendario_nome} value={c.calendario_nome}>{c.calendario_nome} ({c.datas} data{c.datas !== 1 ? 's' : ''})</option>
                  ))}
                </select>
                <p className="text-[10px] text-dim">Datas do calendário (feriados/fechamento) em que o pipeline <strong>não roda</strong>. Gerencie em Admin ▸ Agendamento.</p>
              </div>
            )}

            <Input label="Data de início DAG (opcional)" type="date" value={form.dag_start_date}
              onChange={e => f('dag_start_date', e.target.value)} />

            <div className="bg-canvas border border-edge rounded-lg px-3 py-2.5">
              {form.schedule_type === 'on_demand' ? (
                <p className="text-xs text-dim">Sem agendamento automático — execução apenas manual ou por dependência.</p>
              ) : (
                <>
                  <div className="flex items-center justify-between mb-1">
                    <p className="text-[10px] text-dim font-bold uppercase tracking-wider">
                      {form.schedule_type === 'biweekly' ? 'Próximas 2 execuções' : 'Próximas execuções'}
                    </p>
                    {(form.schedule_type === 'hourly_n' || form.schedule_type === 'custom') && perDay > 0 && (
                      <span className="text-[10px] font-bold text-blue-600 dark:text-blue-300 bg-blue-100 dark:bg-blue-900/30 border border-blue-300 dark:border-blue-800/40 rounded-full px-2 py-0.5">
                        {perDay}× por dia
                      </span>
                    )}
                  </div>
                  {nextRuns.length > 0 ? (
                    <ul className="flex flex-col gap-0.5">
                      {nextRuns.map((t, i) => (
                        <li key={i} className="text-[11px] text-ink flex items-center gap-1.5">
                          <span className="w-1.5 h-1.5 rounded-full bg-green-500 flex-shrink-0" />
                          {t}
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="text-[11px] text-dim/60 italic">Preencha os campos para ver a simulação.</p>
                  )}
                </>
              )}
            </div>
          </div>
        )}

        {/* ── STEP 2: NOTIFICAÇÕES + AVANÇADO ── */}
        {step === 2 && (
          <div className="flex flex-col gap-4 overflow-y-auto max-h-[55vh] pr-1">
            <div>
              <p className="text-[10px] font-bold uppercase tracking-wider text-blue-400 mb-2">Notificações Teams / E-mail</p>
              <div className="flex flex-col gap-2">
                {([
                  ['envia_msg_inicio', '▶ Início da execução'],
                  ['envia_msg_fim',    '✓ Conclusão bem-sucedida'],
                  ['envia_msg_erro',   '⚠ Falha / erro'],
                ] as [keyof FormState, string][]).map(([key, label]) => (
                  <label key={key} className="flex items-center gap-2.5 cursor-pointer bg-canvas border border-edge rounded-lg px-3 py-2.5">
                    <input type="checkbox" checked={form[key] as boolean}
                      onChange={e => f(key, e.target.checked)} className="accent-blue-500" />
                    <span className="text-sm text-ink">{label}</span>
                  </label>
                ))}
              </div>
            </div>
            <div>
              <p className="text-[10px] font-bold uppercase tracking-wider text-blue-400 mb-2">Configurações Avançadas</p>
              <div className="flex flex-col gap-3">
                <div className="grid grid-cols-3 gap-3">
                  <div className="flex flex-col gap-1">
                    <label className="text-xs text-dim font-medium">Runs simultâneas</label>
                    <input type="number" min={1} max={10} value={form.max_active_runs}
                      onChange={e => f('max_active_runs', parseInt(e.target.value) || 1)}
                      className="bg-panel border border-edge text-ink rounded-md px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500" />
                  </div>
                  <div className="flex flex-col gap-1">
                    <label className="text-xs text-dim font-medium">Retries</label>
                    <input type="number" min={0} max={10} value={form.retries_count}
                      onChange={e => f('retries_count', parseInt(e.target.value) || 0)}
                      className="bg-panel border border-edge text-ink rounded-md px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500" />
                  </div>
                  <div className="flex flex-col gap-1">
                    <label className="text-xs text-dim font-medium">Delay retry (s)</label>
                    <input type="number" min={0} value={form.retry_delay_seconds}
                      onChange={e => f('retry_delay_seconds', parseInt(e.target.value) || 300)}
                      className="bg-panel border border-edge text-ink rounded-md px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500" />
                  </div>
                </div>
                <Input label="Fila de execução (pool)" value={form.pool_name}
                  onChange={e => f('pool_name', e.target.value)} placeholder="padrão do Airflow" />
                <div className="flex flex-col gap-1">
                  <label className="text-xs text-dim font-medium">Depende de (pipelines separados por vírgula)</label>
                  <input list="dep-list-wiz" value={form.depends_on}
                    onChange={e => f('depends_on', e.target.value)}
                    placeholder="ex: ETL_BASE_CLIENTES, ETL_CARTEIRA"
                    className="bg-panel border border-edge text-ink rounded-md px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500" />
                  <datalist id="dep-list-wiz">
                    {otherPipelines.map(n => <option key={n} value={n} />)}
                  </datalist>
                  <p className="text-[10px] text-dim">Os pipelines acima precisam concluir com sucesso antes deste iniciar.</p>
                  {form.depends_on.trim() && (
                    <label className="flex items-start gap-2 cursor-pointer bg-amber-50 dark:bg-amber-900/15 border border-amber-300 dark:border-amber-800/40 rounded-lg px-3 py-2 mt-1">
                      <input type="checkbox" checked={form.trigger_por_dependencia}
                        onChange={e => f('trigger_por_dependencia', e.target.checked)} className="mt-0.5 accent-amber-500" />
                      <div>
                        <span className="text-sm text-ink font-medium">Disparar quando as dependências concluírem</span>
                        <p className="text-[11px] text-amber-700 dark:text-amber-400 mt-0.5">
                          ⚠ Ao ativar, o pipeline é disparado automaticamente assim que as dependências concluírem e <strong>ignora o horário de execução agendado</strong>.
                        </p>
                      </div>
                    </label>
                  )}
                </div>
                <Textarea label="Runbook (Markdown)" value={form.runbook_md}
                  onChange={e => f('runbook_md', e.target.value)} rows={3}
                  placeholder="Como monitorar, tratar falhas, contato responsável…" />
              </div>
            </div>
          </div>
        )}

        {/* ── STEP 3: JOBS ── */}
        {step === 3 && (
          <div className="flex flex-col gap-3 overflow-y-auto max-h-[55vh] pr-1">
            <div className="flex items-center justify-between">
              <div className="text-xs text-dim">
                Defina os jobs em ordem de execução. <span className="text-dim/70">Mesma ordem = execução em paralelo.</span>
              </div>
              <Button size="sm" onClick={addJob}><Plus size={12} /> Adicionar job</Button>
            </div>
            {jobs.length === 0 && (
              <div className="py-10 flex flex-col items-center gap-2 text-dim border border-dashed border-edge rounded-xl">
                <span className="text-3xl opacity-30">⚙</span>
                <p className="text-sm">Nenhum job cadastrado</p>
                <p className="text-xs">Jobs são opcionais — podem ser adicionados depois na tela de Jobs.</p>
              </div>
            )}
            {jobs.map((j, idx) => {
              const cmdLabel = j.job_type === 'datastage' ? 'Nome do job DataStage'
                : j.job_type === 'storedproc' ? 'Procedure (ex: dbo.sp_nome)'
                : j.job_type === 'python' ? 'Módulo / Path' : 'Comando / Path'
              const cmdPlaceholder = j.job_type === 'datastage' ? 'ex: BiCvp.job_name'
                : j.job_type === 'shell' ? 'ex: /opt/scripts/run.sh'
                : j.job_type === 'python' ? 'ex: scripts.modulo.run' : 'ex: dbo.sp_procedure'
              return (
                <div key={j.id} className="border border-edge rounded-xl p-3 flex flex-col gap-2 bg-canvas">
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] font-bold text-blue-600 dark:text-blue-300 bg-blue-100 dark:bg-blue-900/30 border border-blue-300 dark:border-blue-800/40 rounded-full px-2 py-0.5">#{idx + 1}</span>
                    <span className="text-xs font-mono text-ink flex-1 truncate">{j.job_name || '(sem nome)'}</span>
                    <span className={`inline-flex items-center px-2 py-0.5 rounded text-[10px] font-medium ${typeBadgeColor(j.job_type)}`}>{j.job_type}</span>
                    <button onClick={() => removeJob(j.id)} className="text-dim hover:text-red-500 transition-colors text-xs ml-1">✕ remover</button>
                  </div>
                  <div className="grid grid-cols-[1fr_70px_130px] gap-2">
                    <div className="flex flex-col gap-1">
                      <label className="text-[10px] text-dim font-medium">Nome do Job *</label>
                      <input type="text" value={j.job_name}
                        onChange={e => updateJob(j.id, { job_name: e.target.value })}
                        placeholder="ex: BiCvp_Extrai_01"
                        className="bg-panel border border-edge text-ink rounded-md px-2 py-1 text-xs font-mono focus:outline-none focus:ring-1 focus:ring-blue-500" />
                    </div>
                    <div className="flex flex-col gap-1">
                      <label className="text-[10px] text-dim font-medium">Ordem</label>
                      <input type="number" min={1} value={j.execution_order}
                        onChange={e => updateJob(j.id, { execution_order: parseInt(e.target.value) || 1 })}
                        className="bg-panel border border-edge text-ink rounded-md px-2 py-1 text-xs text-center focus:outline-none focus:ring-1 focus:ring-blue-500" />
                    </div>
                    <div className="flex flex-col gap-1">
                      <label className="text-[10px] text-dim font-medium">Tipo</label>
                      <select value={j.job_type}
                        onChange={e => updateJob(j.id, { job_type: e.target.value as WizJobType })}
                        className="bg-panel border border-edge text-ink rounded-md px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-blue-500">
                        {JOB_TYPES.map(t => <option key={t}>{t}</option>)}
                      </select>
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <div className="flex flex-col gap-1">
                      <label className="text-[10px] text-dim font-medium">{cmdLabel}</label>
                      <input type="text" value={j.job_command}
                        onChange={e => updateJob(j.id, { job_command: e.target.value })}
                        placeholder={cmdPlaceholder}
                        className="bg-panel border border-edge text-ink rounded-md px-2 py-1 text-xs font-mono focus:outline-none focus:ring-1 focus:ring-blue-500" />
                    </div>
                    {j.job_type === 'shell' && (
                      <div className="flex flex-col gap-1">
                        <label className="text-[10px] text-dim font-medium">Servidor SSH *</label>
                        <select value={j.ssh_conn_id}
                          onChange={e => updateJob(j.id, { ssh_conn_id: e.target.value })}
                          className="bg-panel border border-edge text-ink rounded-md px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-blue-500">
                          <option value="">Selecione a conexão…</option>
                          {sshConns.map(c => <option key={c.conn_id} value={c.conn_id}>{c.conn_id}{c.host ? ` (${c.host})` : ''}</option>)}
                        </select>
                      </div>
                    )}
                    {j.job_type === 'datastage' && (
                      <label className="flex items-center gap-2 cursor-pointer self-end pb-1">
                        <input type="checkbox" checked={j.verbose_log}
                          onChange={e => updateJob(j.id, { verbose_log: e.target.checked })} className="accent-amber-500" />
                        <span className="text-xs text-ink">Log detalhado (jobs SEQUENCE)</span>
                      </label>
                    )}
                    {j.job_type === 'storedproc' && (
                      <div className="flex flex-col gap-1">
                        <label className="text-[10px] text-dim font-medium">Conexão MSSQL *</label>
                        <select value={j.mssql_conn_id}
                          onChange={e => updateJob(j.id, { mssql_conn_id: e.target.value })}
                          className="bg-panel border border-edge text-ink rounded-md px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-blue-500">
                          <option value="">Selecione a conexão…</option>
                          {mssqlConns.map(c => <option key={c.conn_id} value={c.conn_id}>{c.conn_id}{c.host ? ` (${c.host})` : ''}</option>)}
                        </select>
                      </div>
                    )}
                  </div>
                  {j.job_type === 'storedproc' && (
                    <div className="flex flex-col gap-1.5 pt-1 border-t border-edge/40">
                      <button type="button" onClick={() => toggleParams(j.id)}
                        className="text-[10px] text-dim hover:text-ink flex items-center gap-1.5 self-start">
                        <span>{expandedParams.has(j.id) ? '▾' : '▸'} Parâmetros (opcional)</span>
                        {j.params.length > 0 && (
                          <span className="bg-blue-100 text-blue-700 border border-blue-300 dark:bg-blue-900/30 dark:text-blue-300 dark:border-blue-800/40 rounded-full px-1.5 py-0 text-[9px] font-bold">
                            {j.params.length}
                          </span>
                        )}
                      </button>
                      {expandedParams.has(j.id) && (
                        <div className="flex flex-col gap-1.5">
                          {j.params.map(p => (
                            <div key={p.id} className="grid grid-cols-[1fr_90px_1fr_24px] gap-1.5 items-start">
                              <input type="text" value={p.param_name}
                                onChange={e => updateParam(j.id, p.id, { param_name: e.target.value })}
                                placeholder="@nome_param"
                                className={`bg-panel border rounded-md px-2 py-1 text-xs font-mono focus:outline-none focus:ring-1 focus:ring-blue-500 ${!p.param_name.trim() ? 'border-red-500/60' : 'border-edge'}`} />
                              <select value={p.param_type}
                                onChange={e => updateParam(j.id, p.id, { param_type: e.target.value })}
                                className="bg-panel border border-edge text-ink rounded-md px-1.5 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-blue-500">
                                {PARAM_TYPES.map(t => <option key={t}>{t}</option>)}
                              </select>
                              <input type="text" value={p.param_value}
                                onChange={e => updateParam(j.id, p.id, { param_value: e.target.value })}
                                placeholder="valor fixo"
                                className="bg-panel border border-edge text-ink rounded-md px-2 py-1 text-xs font-mono focus:outline-none focus:ring-1 focus:ring-blue-500" />
                              <button type="button" onClick={() => removeParam(j.id, p.id)}
                                className="text-dim hover:text-red-500 text-xs justify-self-center pt-1">✕</button>
                            </div>
                          ))}
                          <Button size="sm" variant="ghost" onClick={() => addParam(j.id)} className="self-start">
                            <Plus size={10} /> Adicionar parâmetro
                          </Button>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}

        {/* ── STEP 4: LINEAGE ── */}
        {step === 4 && (
          <div className="flex flex-col gap-3 overflow-y-auto max-h-[55vh] pr-1">
            <p className="text-xs text-dim">Mapeie origens e destinos de dados por job.</p>
            {jobs.length === 0 && (
              <div className="py-8 flex flex-col items-center gap-2 text-dim border border-dashed border-edge rounded-xl">
                <p className="text-sm">Nenhum job cadastrado na etapa anterior.</p>
                <p className="text-xs">Volte para a aba Jobs e adicione ao menos um job.</p>
              </div>
            )}
            {jobs.map(j => {
              const origens  = lineage.filter(l => l.job_name === j.job_name && l.direction === 'origem')
              const destinos = lineage.filter(l => l.job_name === j.job_name && l.direction === 'destino')
              if (!j.job_name.trim()) return null
              return (
                <div key={j.id} className="border border-edge rounded-xl overflow-hidden">
                  <div className="bg-canvas border-b border-edge px-3 py-2 flex items-center gap-2">
                    <span className="text-[10px] font-bold text-blue-400">#{j.execution_order}</span>
                    <span className="text-xs font-mono font-bold text-ink">{j.job_name}</span>
                    <span className="text-[10px] text-dim ml-1">{j.job_type}</span>
                  </div>
                  <div className="grid grid-cols-2 gap-0">
                    <div className="border-r border-edge p-3">
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-[10px] font-bold uppercase tracking-wider text-blue-400">Origens</span>
                        <button onClick={() => addLineageEntry(j.job_name, 'origem')}
                          className="text-[10px] text-blue-400 hover:text-blue-300 border border-blue-800/40 rounded px-1.5 py-0.5">+ adicionar</button>
                      </div>
                      {origens.length === 0 && <p className="text-[10px] text-dim/50 italic">Nenhuma origem</p>}
                      {origens.map(l => (
                        <div key={l.id} className="flex gap-1 items-center mb-1">
                          <select value={l.object_type}
                            onChange={e => updateLineage(l.id, 'object_type', e.target.value)}
                            className="bg-panel border border-edge text-dim rounded px-1 py-0.5 text-[10px] focus:outline-none focus:ring-1 focus:ring-blue-500 w-16 shrink-0">
                            {OBJECT_TYPES.map(t => <option key={t}>{t}</option>)}
                          </select>
                          <input type="text" value={l.object_name}
                            onChange={e => updateLineage(l.id, 'object_name', e.target.value)}
                            placeholder="dbo.tabela_origem"
                            className="bg-panel border border-edge text-ink rounded px-1.5 py-0.5 text-[10px] font-mono focus:outline-none focus:ring-1 focus:ring-blue-500 flex-1" />
                          <button onClick={() => removeLineageEntry(l.id)} className="text-dim hover:text-red-500 text-[10px] shrink-0">✕</button>
                        </div>
                      ))}
                    </div>
                    <div className="p-3">
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-[10px] font-bold uppercase tracking-wider text-green-400">Destinos</span>
                        <button onClick={() => addLineageEntry(j.job_name, 'destino')}
                          className="text-[10px] text-green-400 hover:text-green-300 border border-green-800/40 rounded px-1.5 py-0.5">+ adicionar</button>
                      </div>
                      {destinos.length === 0 && <p className="text-[10px] text-dim/50 italic">Nenhum destino</p>}
                      {destinos.map(l => (
                        <div key={l.id} className="flex gap-1 items-center mb-1">
                          <select value={l.object_type}
                            onChange={e => updateLineage(l.id, 'object_type', e.target.value)}
                            className="bg-panel border border-edge text-dim rounded px-1 py-0.5 text-[10px] focus:outline-none focus:ring-1 focus:ring-green-500 w-16 shrink-0">
                            {OBJECT_TYPES.map(t => <option key={t}>{t}</option>)}
                          </select>
                          <input type="text" value={l.object_name}
                            onChange={e => updateLineage(l.id, 'object_name', e.target.value)}
                            placeholder="dbo.tabela_destino"
                            className="bg-panel border border-edge text-ink rounded px-1.5 py-0.5 text-[10px] font-mono focus:outline-none focus:ring-1 focus:ring-green-500 flex-1" />
                          <button onClick={() => removeLineageEntry(l.id)} className="text-dim hover:text-red-500 text-[10px] shrink-0">✕</button>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        )}

        {/* ── STEP 5: REVISÃO ── */}
        {step === 5 && (
          <div className="flex flex-col gap-3 overflow-y-auto max-h-[55vh] pr-1">
            <p className="text-xs text-blue-700 dark:text-blue-400 bg-blue-50 dark:bg-blue-900/10 border border-blue-200 dark:border-blue-800/30 rounded-lg px-3 py-2">
              Revise todas as informações antes de salvar. Use o stepper acima para corrigir qualquer etapa.
            </p>

            <div className="border border-edge rounded-xl overflow-hidden">
              <div className="bg-canvas border-b border-edge px-3 py-2">
                <span className="text-[10px] font-bold uppercase tracking-wider text-blue-400">Identificação</span>
              </div>
              <div className="p-3 text-xs flex flex-col gap-1.5">
                <div className="flex flex-wrap gap-x-8 gap-y-1.5">
                  <div className="min-w-0"><span className="text-dim">Nome: </span><span className="font-mono font-bold text-ink break-all">{form.pipeline_name || '—'}</span></div>
                  <div><span className="text-dim">Projeto: </span><span className="text-ink">{form.project_name || '—'}</span></div>
                  <div className="min-w-0"><span className="text-dim">Domínio: </span><span className="text-ink break-all">{form.domain || '—'}</span></div>
                  <div><span className="text-dim">Ambiente: </span><span className={`font-medium ${form.ambiente === 'PROD' ? 'text-red-400' : 'text-yellow-400'}`}>{form.ambiente}</span></div>
                  <div><span className="text-dim">Criticidade: </span><span className={`font-medium ${critColor(form.criticidade)}`}>{form.criticidade}</span></div>
                  <div><span className="text-dim">Status: </span><span className={form.active ? 'text-green-400' : 'text-dim'}>{form.active ? 'Ativo' : 'Inativo'}</span></div>
                </div>
                {form.tags_list.length > 0 && (
                  <div className="flex items-center flex-wrap gap-1">
                    <span className="text-dim mr-1">Tags:</span>
                    {form.tags_list.map(t => (
                      <span key={t} className="bg-blue-100 text-blue-700 border border-blue-300 dark:bg-blue-600/25 dark:text-blue-200 dark:border-blue-600/50 rounded-full px-2 py-0.5 text-[10px] font-medium">{t}</span>
                    ))}
                  </div>
                )}
                {form.descricao && <div className="text-dim/80 break-words"><span className="text-dim">Descrição: </span><span className="text-ink">{form.descricao}</span></div>}
              </div>
            </div>

            <div className="border border-edge rounded-xl overflow-hidden">
              <div className="bg-canvas border-b border-edge px-3 py-2">
                <span className="text-[10px] font-bold uppercase tracking-wider text-blue-400">Agendamento</span>
              </div>
              <div className="grid grid-cols-2 gap-x-6 gap-y-2 p-3 text-xs">
                <div><span className="text-dim">Tipo:</span> <span className="text-ink">{SCHEDULE_LABELS[form.schedule_type] ?? form.schedule_type}</span></div>
                {form.schedule_type === 'hourly_n' && (
                  <div><span className="text-dim">Janela:</span> <span className="text-ink">a cada {form.schedule_interval_hours}h, {String(form.schedule_start_hour).padStart(2,'0')}h–{String(form.schedule_end_hour).padStart(2,'0')}h ({perDay}×/dia)</span></div>
                )}
                {form.schedule_type === 'custom' && (
                  <div className="col-span-2"><span className="text-dim">Horários:</span> <span className="font-mono text-ink">{parseCustomTimes(form.schedule_custom_times).join(', ') || '—'}</span> <span className="text-dim">· dias:</span> <span className="text-ink">{form.schedule_weekdays.length ? form.schedule_weekdays.slice().sort((a,b)=>a-b).map(d => DOW_LABELS.find(([v])=>v===d)?.[1]).join(', ') : '—'}</span></div>
                )}
                {form.schedule_type === 'monthly_days_times' && (
                  <div className="col-span-2 flex flex-col gap-0.5">
                    <span className="text-dim">Dias e horários:</span>
                    {(schedCfg.monthDays?.length ?? 0) > 0 ? schedCfg.monthDays!.map(e => (
                      <span key={e.dia} className="text-ink font-mono text-[11px]">Dia {e.dia} às {e.horarios.join(', ')}</span>
                    )) : <span className="text-dim/60 italic text-xs">—</span>}
                  </div>
                )}
                {form.schedule_type === 'weekly' && (
                  <div><span className="text-dim">Quando:</span> <span className="text-ink">{DOW_LABELS.find(([v])=>v===form.schedule_dow)?.[1]} {String(form.schedule_hour).padStart(2,'0')}:{String(form.schedule_minute).padStart(2,'0')}</span></div>
                )}
                {(form.schedule_type === 'monthly' || form.schedule_type === 'biweekly') && (
                  <div><span className="text-dim">Quando:</span> <span className="text-ink">dia {form.schedule_dom}{form.schedule_type === 'biweekly' ? ` e ${form.schedule_dom+15}` : ''} às {String(form.schedule_hour).padStart(2,'0')}:{String(form.schedule_minute).padStart(2,'0')}</span></div>
                )}
                {form.schedule_type === 'daily' && (
                  <div><span className="text-dim">Quando:</span> <span className="text-ink">diariamente às {String(form.schedule_hour).padStart(2,'0')}:{String(form.schedule_minute).padStart(2,'0')}</span></div>
                )}
                {showBizToggle && form.somente_dias_uteis && <div><span className="text-dim">Restrição:</span> <span className="text-ink">somente dias úteis</span></div>}
                {form.calendario_nome && <div><span className="text-dim">Calendário:</span> <span className="text-ink">{form.calendario_nome}</span></div>}
                {form.depends_on.trim() && <div className="col-span-2"><span className="text-dim">Depende de:</span> <span className="font-mono text-ink">{form.depends_on}</span>{form.trigger_por_dependencia && <span className="text-amber-600 dark:text-amber-400"> · dispara por dependência (ignora horário)</span>}</div>}
                {form.dag_start_date && <div><span className="text-dim">Início DAG:</span> <span className="text-ink">{form.dag_start_date}</span></div>}
                {form.sla_minutos && <div><span className="text-dim">SLA:</span> <span className="text-ink">{form.sla_minutos} min</span></div>}
                {nextRuns.length > 0 && (
                  <div className="col-span-2 border-t border-edge/50 pt-1.5 mt-0.5">
                    <span className="text-dim">Próximas:</span> <span className="text-ink">{nextRuns.slice(0, 3).join('  ·  ')}</span>
                  </div>
                )}
              </div>
            </div>

            <div className="border border-edge rounded-xl overflow-hidden">
              <div className="bg-canvas border-b border-edge px-3 py-2 flex items-center justify-between">
                <span className="text-[10px] font-bold uppercase tracking-wider text-blue-400">Jobs ({jobs.length})</span>
              </div>
              {jobs.length === 0
                ? <p className="text-xs text-dim/50 italic px-3 py-2">Nenhum job cadastrado</p>
                : <div className="divide-y divide-edge/40">
                    {jobs.map((j, i) => (
                      <div key={j.id} className="px-3 py-2 text-xs flex flex-col gap-0.5">
                        <div className="flex items-center gap-2">
                          <span className="text-[10px] text-blue-400 font-bold w-6">#{i+1}</span>
                          <span className={`text-[10px] px-1.5 py-0.5 rounded font-bold ${typeBadgeColor(j.job_type)}`}>{j.job_type}</span>
                          <span className="font-mono font-medium text-ink">{j.job_name || '(sem nome)'}</span>
                          {j.ssh_conn_id && <span className="text-dim/60 font-mono text-[10px]">SSH: {j.ssh_conn_id}</span>}
                          {j.verbose_log && <span className="text-[10px] text-amber-400">verbose</span>}
                          {j.job_type === 'storedproc' && j.mssql_conn_id && <span className="text-dim/60 font-mono text-[10px]">MSSQL: {j.mssql_conn_id}</span>}
                        </div>
                        {j.job_command && (
                          <div className="pl-8 flex items-center gap-1">
                            <span className="text-dim text-[10px]">{j.job_type === 'datastage' ? 'Job DataStage:' : 'Comando:'}</span>
                            <span className="font-mono text-[10px] text-ink/80 break-all">{j.job_command}</span>
                          </div>
                        )}
                        {j.job_type === 'storedproc' && j.params.length > 0 && (
                          <div className="pl-8 flex items-center gap-1 flex-wrap">
                            <span className="text-dim text-[10px]">Parâmetros:</span>
                            {j.params.map(p => (
                              <span key={p.id} className="font-mono text-[10px] text-ink/80">{p.param_name}={p.param_value || '∅'}</span>
                            ))}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
              }
            </div>

            {lineage.length > 0 && (
              <div className="border border-edge rounded-xl overflow-hidden">
                <div className="bg-canvas border-b border-edge px-3 py-2">
                  <span className="text-[10px] font-bold uppercase tracking-wider text-blue-400">Lineage ({lineage.length} entradas)</span>
                </div>
                <div className="divide-y divide-edge/40">
                  {lineage.map(l => (
                    <div key={l.id} className="px-3 py-1.5 text-xs flex items-center gap-3">
                      <span className="font-mono text-dim w-28 truncate">{l.job_name}</span>
                      <span className={`text-[10px] font-bold ${l.direction === 'origem' ? 'text-blue-400' : 'text-green-400'}`}>{l.direction.toUpperCase()}</span>
                      <span className="font-mono text-ink">{l.object_name || '(vazio)'}</span>
                      {l.database_name && <span className="text-dim/60">{l.database_name}</span>}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {saveMut.isError && (
              <div className="bg-red-50 border border-red-200 dark:bg-red-900/20 dark:border-red-800 rounded-lg px-3 py-2 text-xs text-red-700 dark:text-red-400">
                Erro ao salvar: {(saveMut.error as any)?.message}
              </div>
            )}
          </div>
        )}

        <div className="flex justify-between items-center pt-1 border-t border-edge">
          <Button variant="secondary" onClick={step === 0 ? onClose : goPrev}>
            {step === 0 ? 'Cancelar' : '← Voltar'}
          </Button>
          <div className="flex gap-2">
            {step < 5
              ? <Button onClick={goNext}>Próximo →</Button>
              : <Button loading={saveMut.isPending} onClick={validateAllAndSave}>
                  <Save size={13} /> {isEdit ? 'Salvar alterações' : 'Criar pipeline'}
                </Button>
            }
          </div>
        </div>
      </div>
    </Modal>
  )
}

// re-export buildCron for ViewModal (used in PipelineModals)
export { buildCron }
