import { useState, useMemo, useCallback, useRef, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiFetch } from '../lib/api'
import { useAuthStore } from '../store/auth'
import { Button } from '../components/ui/Button'
import { Input, Select, Textarea } from '../components/ui/Input'
import { Autocomplete } from '../components/ui/Autocomplete'
import { Modal } from '../components/ui/Modal'
import { PageSpinner } from '../components/ui/Spinner'
import { toast } from '../components/ui/Toast'
import {
  ChevronRight, ChevronDown, Plus, Edit, Eye, GitBranch,
  History, Play, PowerOff, Settings, Save,
} from 'lucide-react'

// ── types ──────────────────────────────────────────────────────────────────

interface Pipeline {
  pipeline_name: string
  project_name: string | null
  domain: string | null
  tags: string | null
  scheduled_time: string | null
  schedule_type: string | null
  schedule_hour: number | null
  schedule_minute: number | null
  schedule_dow: number | null
  schedule_dom: number | null
  active: number
  dag_criada: number
  envia_msg_inicio: number
  envia_msg_fim: number
  envia_msg_erro: number
  depends_on: string | null
  dag_start_date: string | null
  descricao: string | null
  criticidade: string
  sla_minutos: number | null
  ambiente: string
  max_active_runs: number
  retries_count: number
  retry_delay_seconds: number
  pool_name: string | null
  runbook_md: string | null
  last_execution: string | null
  created_at: string | null
  updated_at: string | null
  // scheduling avançado (migrations 017/018) — podem vir ausentes
  horarios_especificos?: string | null
  dias_semana?: string | null
  somente_dias_uteis?: number | null
  calendario_nome?: string | null
  trigger_por_dependencia?: number | null
}

interface AuditRow {
  changed_at: string
  changed_by: string
  field_name: string
  old_value: string | null
  new_value: string | null
}

interface LineageObject {
  object_name: string
  object_type: string
  database_name?: string
}

interface LineageJob {
  job_name: string
  origens: LineageObject[]
  destinos: LineageObject[]
}

// ── constants ──────────────────────────────────────────────────────────────

const SCHEDULE_TYPES = ['daily', 'weekly', 'monthly', 'biweekly', 'hourly_n', 'custom', 'on_demand'] as const
const SCHEDULE_LABELS: Record<string, string> = {
  daily: 'Diário', weekly: 'Semanal', monthly: 'Mensal', biweekly: 'Quinzenal',
  hourly_n: 'A cada N horas', custom: 'Horários específicos', on_demand: 'Sob demanda',
}
const CRITICIDADES   = ['Alta', 'Media', 'Baixa'] as const
const AMBIENTES      = ['PROD', 'HML', 'DEV'] as const
const DAG_FACTORY_ID = 'etl_dag_factory'
const AIRFLOW_UI     = 'https://airflow.caixavidaeprevidencia.intranet'

// Job/Lineage — mesmos tipos e regras da tela de Jobs
const JOB_TYPES = ['datastage', 'shell', 'python', 'storedproc'] as const
type WizJobType = typeof JOB_TYPES[number]
const OBJECT_TYPES = ['Tabela', 'View', 'Arquivo', 'Procedure', 'Dataset', 'API'] as const

// Dias da semana — convenção cron (0=Domingo … 6=Sábado)
const DOW_LABELS: [number, string][] = [
  [0, 'Dom'], [1, 'Seg'], [2, 'Ter'], [3, 'Qua'], [4, 'Qui'], [5, 'Sex'], [6, 'Sáb'],
]

// ── helpers ────────────────────────────────────────────────────────────────

function pipelineToDagId(name: string) {
  return name.toLowerCase().replace(/[^a-z0-9_]/g, '_')
}

// Descreve a configuração de agendamento de forma normalizada para preview/payload
interface ScheduleConfig {
  type: string
  hour: number
  minute: number
  dow: number
  dom: number
  intervalH: number
  startH: number
  endH: number
  customTimes: string
  weekdays: number[]      // dias da semana selecionados (custom)
  businessDaysOnly: boolean
}

// Gera lista de horários "HH:MM" para o tipo "a cada N horas" dentro da janela [startH, endH]
function hourlyTimes(cfg: ScheduleConfig): string[] {
  const out: string[] = []
  const n = Math.max(1, cfg.intervalH)
  const mm = String(cfg.minute).padStart(2, '0')
  for (let h = cfg.startH; h <= cfg.endH; h += n) {
    out.push(`${String(h).padStart(2, '0')}:${mm}`)
  }
  return out
}

// Parse de "09:00, 13:30" → ["09:00","13:30"] (válidos, ordenados)
function parseCustomTimes(raw: string): string[] {
  const set = new Set<string>()
  for (const part of raw.split(/[,;]/)) {
    const t = part.trim()
    if (!t) continue
    const m = t.match(/^(\d{1,2}):?(\d{0,2})$/)
    if (!m) continue
    const hh = parseInt(m[1]); const mn = m[2] ? parseInt(m[2]) : 0
    if (hh < 0 || hh > 23 || mn < 0 || mn > 59) continue
    set.add(`${String(hh).padStart(2, '0')}:${String(mn).padStart(2, '0')}`)
  }
  return [...set].sort()
}

// Calcula as próximas N execuções, respeitando dia da semana / dia do mês / janela / dias úteis
function computeNextRuns(cfg: ScheduleConfig, count = 5): string[] {
  if (cfg.type === 'on_demand') return []
  const results: Date[] = []
  const now = new Date()

  function timesForDay(): { h: number; m: number }[] {
    if (cfg.type === 'hourly_n') return hourlyTimes(cfg).map(t => ({ h: +t.slice(0, 2), m: +t.slice(3) }))
    if (cfg.type === 'custom')   return parseCustomTimes(cfg.customTimes).map(t => ({ h: +t.slice(0, 2), m: +t.slice(3) }))
    return [{ h: cfg.hour, m: cfg.minute }]
  }

  function dayMatches(d: Date): boolean {
    const wd = d.getDay(); const dom = d.getDate()
    if (cfg.businessDaysOnly && (wd === 0 || wd === 6)) return false
    switch (cfg.type) {
      case 'daily':    return true
      case 'hourly_n': return true
      case 'weekly':   return wd === cfg.dow
      case 'monthly':  return dom === cfg.dom
      case 'biweekly': return dom === cfg.dom || dom === cfg.dom + 15
      case 'custom':   return cfg.weekdays.length === 0 ? true : cfg.weekdays.includes(wd)
      default:         return true
    }
  }

  const times = timesForDay()
  if (times.length === 0) return []

  const cur = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  for (let dayOffset = 0; dayOffset < 366 && results.length < count; dayOffset++) {
    const d = new Date(cur.getTime() + dayOffset * 86400_000)
    if (!dayMatches(d)) continue
    for (const t of times) {
      const dt = new Date(d.getFullYear(), d.getMonth(), d.getDate(), t.h, t.m, 0)
      if (dt > now) { results.push(dt); if (results.length >= count) break }
    }
  }
  return results.map(d =>
    d.toLocaleString('pt-BR', { weekday: 'short', day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }),
  )
}

// Quantas execuções por dia (para "a cada N horas")
function runsPerDay(cfg: ScheduleConfig): number {
  if (cfg.type === 'hourly_n') return hourlyTimes(cfg).length
  if (cfg.type === 'custom')   return parseCustomTimes(cfg.customTimes).length
  return 1
}

function exportModeloCsv() {
  const headers = [
    'pipeline_name','project_name','domain','tags','descricao','criticidade','ambiente',
    'schedule_type','schedule_hour','schedule_minute','schedule_interval_hours','schedule_start_hour','schedule_end_hour',
    'schedule_dow','schedule_dom','horarios_especificos','dias_semana','somente_dias_uteis','calendario_nome',
    'dag_start_date','sla_minutos','max_active_runs','retries_count','retry_delay_seconds','pool_name',
    'depends_on','trigger_por_dependencia','envia_msg_inicio','envia_msg_fim','envia_msg_erro',
    'job_execution_order','job_name','job_type','job_command','job_ssh_conn_id','job_verbose_log',
    'lineage_job_name','lineage_direction','lineage_object_name','lineage_object_type','lineage_database',
  ]
  // Vários exemplos cobrindo cada opção de domínio (ambiente, criticidade, tipos de agendamento, tipos de job)
  const examples = [
    // Diário, ambiente PROD, criticidade Alta, job datastage
    ['ETL_DIARIO_EXEMPLO','BI_CVP','FINANCEIRO','ETL,DIARIO','ETL diário de cobrança','Alta','PROD',
     'daily','6','0','','','','','','','','0','','','60','1','1','300','',
     '','0','1','1','1',
     '1','BiCvp_Extrai_01','datastage','BiCvp.Extrai_01','','0',
     'BiCvp_Extrai_01','origem','dbo.tabela_origem','Tabela','PROD_DB'],
    // Semanal (segunda), ambiente HML, criticidade Media, job shell + SSH, dias úteis
    ['ETL_SEMANAL_EXEMPLO','BI_VIDA','ATUARIAL','ETL,SEMANAL','Carga semanal','Media','HML',
     'weekly','8','30','','','','1','','','','','1','','','120','1','2','600','',
     '','0','1','1','1',
     '1','load_semanal','shell','/opt/scripts/load.sh','ssh_prod','0',
     'load_semanal','destino','dbo.tabela_destino','Tabela','HML_DB'],
    // Mensal (dia 5), ambiente DEV, criticidade Baixa, job python
    ['ETL_MENSAL_EXEMPLO','BI_PREVIDENCIA','REGULATORIO','ETL,MENSAL','Fechamento mensal','Baixa','DEV',
     'monthly','7','0','','','','','5','','','','0','','','240','1','1','300','',
     '','0','1','0','1',
     '1','calc_mensal','python','scripts.mensal.run','','0',
     'calc_mensal','origem','dbo.movimentos','Tabela','DEV_DB'],
    // Quinzenal (dia 1 e 16), job storedproc
    ['ETL_QUINZENAL_EXEMPLO','BI_PRESTAMISTA','COMERCIAL','ETL,QUINZENAL','Apuração quinzenal','Media','PROD',
     'biweekly','9','0','','','','','1','','','','0','Feriados BR','','90','1','1','300','',
     '','0','1','1','1',
     '1','sp_apura','storedproc','dbo.sp_apura_quinzenal','','0',
     'sp_apura','destino','dbo.resultado','Procedure','PROD_DB'],
    // A cada N horas (a cada 2h entre 08 e 18), dias úteis
    ['ETL_HORARIO_EXEMPLO','BI_CVP','MONITORAMENTO','ETL,INTRADAY','Carga intraday a cada 2h','Alta','PROD',
     'hourly_n','0','','2','8','18','','','','','1','1','','30','3','1','120','',
     '','0','1','1','1',
     '1','sync_intraday','python','scripts.sync.run','','0',
     'sync_intraday','origem','api.externa','API','EXTERNO'],
    // Horários específicos (09:00 e 15:30 em seg/qua/sex)
    ['ETL_CUSTOM_EXEMPLO','BI_VIDA','OPERACIONAL','ETL,CUSTOM','Horários fixos','Media','PROD',
     'custom','0','','','','','','','09:00,15:30','1,3,5','0','','','45','1','1','300','',
     '','0','1','1','1',
     '1','exporta_arquivo','shell','/opt/scripts/exporta.sh','ssh_prod','0',
     'exporta_arquivo','destino','/dados/saida/arquivo.csv','Arquivo',''],
    // Sob demanda, disparado por dependência (ignora horário)
    ['ETL_DEPENDENTE_EXEMPLO','BI_CVP','CONSOLIDACAO','ETL,DEPENDENTE','Roda após o ETL diário','Media','PROD',
     'on_demand','0','','','','','','','','','0','','','60','1','1','300','',
     'ETL_DIARIO_EXEMPLO','1','1','1','1',
     '1','consolida','python','scripts.consolida.run','','0',
     'consolida','origem','dbo.tabela_origem','Tabela','PROD_DB'],
  ]
  // Linha-legenda com os valores permitidos por campo (facilita escolha correta)
  const legend = [
    'OPÇÕES →','BI_CVP|BI_VIDA|BI_PRESTAMISTA|BI_PREVIDENCIA','(texto livre)','(lista separada por vírgula)','(texto livre)',
    'Alta|Media|Baixa','PROD|HML|DEV',
    'daily|weekly|monthly|biweekly|hourly_n|custom|on_demand','0-23','0-59','1-23 (hourly_n)','0-23 (hourly_n)','0-23 (hourly_n)',
    '0=Dom..6=Sab (weekly)','1-28 (monthly/biweekly)','HH:MM,HH:MM (custom)','0-6 sep. vírgula (custom)','0|1','(nome calendário ou vazio)',
    'AAAA-MM-DD','min ou vazio','1-10','0-10','segundos','(nome pool ou vazio)',
    'pipelines sep. vírgula','0|1','0|1','0|1','0|1',
    '1,2,3…','(texto)','datastage|shell|python|storedproc','(comando/caminho)','(conn SSH p/ shell)','0|1',
    '(= job_name acima)','origem|destino','(nome objeto)','Tabela|View|Arquivo|Procedure|Dataset|API','(banco/schema)',
  ]
  const esc = (v: string) => /[;"\n]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v
  const rows = [headers, legend, ...examples].map(r => r.map(esc).join(';'))
  const csv  = rows.join('\n')
  const blob = new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8;' })
  const url  = URL.createObjectURL(blob)
  const a    = document.createElement('a')
  a.href     = url
  a.download = 'modelo_pipelines.csv'
  a.click()
  URL.revokeObjectURL(url)
}

function critColor(c: string) {
  return c === 'Alta' ? 'text-red-400' : c === 'Media' ? 'text-yellow-400' : 'text-green-400'
}

// Cor do badge por tipo de job (alinhado à tela de Jobs)
function typeBadgeColor(t: string) {
  const m: Record<string, string> = {
    datastage:  'bg-blue-500/15 text-blue-600 dark:text-blue-400 border border-blue-300 dark:border-blue-800/40',
    shell:      'bg-amber-500/15 text-amber-600 dark:text-amber-400 border border-amber-300 dark:border-amber-800/40',
    python:     'bg-green-500/15 text-green-600 dark:text-green-400 border border-green-300 dark:border-green-800/40',
    storedproc: 'bg-purple-500/15 text-purple-600 dark:text-purple-400 border border-purple-300 dark:border-purple-800/40',
  }
  return m[t] ?? 'bg-slate-500/15 text-slate-500 border border-slate-300 dark:border-slate-700'
}

// CRON simplificado para exibição (ViewModal) — pipelines já persistidos
function buildCron(type: string, h: number, m: number, dow: number, dom: number) {
  const t = (type || 'daily').toLowerCase()
  if (t === 'on_demand') return '(sem agendamento automático)'
  if (t === 'hourly')    return `${m} * * * *`
  if (t === 'daily')     return `${m} ${h} * * *`
  if (t === 'weekly')    return `${m} ${h} * * ${dow}`
  if (t === 'monthly')   return `${m} ${h} ${dom} * *`
  if (t === 'biweekly')  return `${m} ${h} ${dom},${dom + 15} * *`
  if (t === 'custom')    return '(horários específicos)'
  return `${m} ${h} * * *`
}

// ── PipelineFormModal ──────────────────────────────────────────────────────

interface JobEntry {
  id: string
  job_name: string
  job_type: WizJobType
  job_command: string
  execution_order: number
  ssh_conn_id: string
  verbose_log: boolean
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
}

const defaultForm = (): FormState => ({
  pipeline_name: '', project_name: '', domain: '', tags_list: [], descricao: '',
  schedule_type: 'daily', schedule_hour: 6, schedule_minute: 0,
  schedule_dow: 1, schedule_dom: 1, schedule_interval_hours: 2,
  schedule_start_hour: 8, schedule_end_hour: 18,
  schedule_custom_times: '', schedule_weekdays: [1, 2, 3, 4, 5],
  somente_dias_uteis: false, calendario_nome: '', trigger_por_dependencia: false,
  active: true, dag_start_date: '',
  envia_msg_inicio: true, envia_msg_fim: true, envia_msg_erro: true,
  criticidade: 'Media', sla_minutos: '', ambiente: 'PROD',
  max_active_runs: 1, retries_count: 1, retry_delay_seconds: 300,
  pool_name: '', depends_on: '', runbook_md: '',
})

function pipelineToForm(p: Pipeline): FormState {
  const horarios = (p.horarios_especificos ?? '').trim()
  const diasRaw  = (p.dias_semana ?? '').trim()
  const weekdays = diasRaw ? diasRaw.split(',').map(s => parseInt(s.trim())).filter(n => !isNaN(n)) : [1, 2, 3, 4, 5]
  // Se há horários específicos persistidos, o pipeline é do tipo "custom" (horários)
  const schedType = horarios ? 'custom' : (p.schedule_type ?? 'daily')
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
  }
}

// ── TagsInput ──

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

// ── Wizard stepper ──

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

// ── PipelineFormModal (wizard) ──

function PipelineFormModal({ pipeline, onClose }: { pipeline?: Pipeline; onClose: () => void }) {
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

  const { data: allPipes } = useQuery<{ data: Pipeline[] }>({
    queryKey: ['pipelines', '', '', '', 0],
    queryFn: () => apiFetch('/pipelines?limit=200'),
    staleTime: 60_000,
  })
  const otherPipelines = (allPipes?.data ?? [])
    .map(p => p.pipeline_name)
    .filter(n => n !== form.pipeline_name)

  // Calendários de bloqueio (admin) e conexões SSH (mesma fonte da tela de Jobs)
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

  // Edição: carrega jobs + lineage existentes para não sobrescrever/perder dados
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
    })))
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

  // Configuração normalizada de agendamento (para preview)
  const schedCfg: ScheduleConfig = {
    type: form.schedule_type,
    hour: form.schedule_hour, minute: form.schedule_minute,
    dow: form.schedule_dow, dom: form.schedule_dom,
    intervalH: form.schedule_interval_hours,
    startH: form.schedule_start_hour, endH: form.schedule_end_hour,
    customTimes: form.schedule_custom_times,
    weekdays: form.schedule_weekdays,
    businessDaysOnly: form.somente_dias_uteis,
  }
  const showBizToggle = !['custom', 'on_demand'].includes(form.schedule_type)
  const nextRuns = useMemo(
    () => computeNextRuns(schedCfg, form.schedule_type === 'biweekly' ? 2 : 5),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [JSON.stringify(schedCfg)],
  )
  const perDay   = runsPerDay(schedCfg)

  // ── Validation per step ──
  function validateStep(s: number): string[] {
    if (s === 0) {
      const e: string[] = []
      if (!form.pipeline_name.trim()) e.push('Nome do pipeline é obrigatório')
      if (!form.project_name)         e.push('Projeto é obrigatório')
      if (!form.domain.trim())        e.push('Domínio é obrigatório')
      if (form.tags_list.length === 0) e.push('Ao menos uma tag é obrigatória')
      if (!form.descricao.trim())     e.push('Descrição é obrigatória')
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
      })
      // nomes duplicados (nomeando quais)
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

  // Monta os campos de agendamento conforme o tipo (alinhado ao backend)
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
    }
    if (t === 'hourly_n') {
      // gera horários da janela e envia como horários específicos (backend prioriza isso)
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
    // daily/weekly/monthly/biweekly/on_demand
    return {
      ...base,
      scheduled_time: `${h}:${m}:00`,
      schedule_type: t,
      schedule_hour: form.schedule_hour,
      schedule_minute: form.schedule_minute,
    }
  }

  // ── Save (2 etapas: pipeline e depois jobs+lineage) ──
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
      await apiFetch('/pipelines/register', { method: 'POST', body: JSON.stringify(body) })

      // Jobs + lineage (endpoint dedicado). Defaults evitam erros de validação.
      // Ordena por execution_order do usuário para reindexar de forma estável.
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
          // Pipeline já foi salvo; sinaliza sucesso parcial sem perder o trabalho.
          return { pname, jobsError: e?.message || 'erro ao salvar jobs' }
        }
      }
      return { pname }
    },
    onSuccess: (res: { pname: string; jobsError?: string }) => {
      qc.invalidateQueries({ queryKey: ['pipelines'] })
      qc.invalidateQueries({ queryKey: ['jobs'] })
      if (res.jobsError) {
        toast.error(`Pipeline salvo, mas os jobs falharam: ${res.jobsError}. Edite o pipeline para reenviar.`)
        setStepErrors(prev => ({ ...prev, 5: [`Pipeline salvo, mas os jobs falharam: ${res.jobsError}`] }))
        return
      }
      toast.success(isEdit ? 'Pipeline atualizado!' : 'Pipeline criado com sucesso!')
      onClose()
    },
    onError: (e: any) => {
      setStepErrors(prev => ({ ...prev, 5: [e?.message || 'Erro ao salvar pipeline'] }))
    },
  })

  // Valida todas as etapas obrigatórias antes de salvar (stepper permite pular)
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

  // ── Jobs helpers ──
  function addJob() {
    setJobs(prev => [...prev, {
      id: `j_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`,
      job_name: '',
      job_type: 'datastage',
      job_command: '',
      execution_order: prev.length + 1,
      ssh_conn_id: '',
      verbose_log: false,
    }])
  }

  function removeJob(id: string) {
    const job = jobs.find(j => j.id === id)
    setJobs(prev => prev.filter(j => j.id !== id))
    if (job) setLineage(prev => prev.filter(l => l.job_name !== job.job_name))
  }

  function updateJob(id: string, patch: Partial<JobEntry>) {
    const job = jobs.find(j => j.id === id)
    // se o nome do job mudar, propaga para a lineage vinculada (setter separado, fora do updater)
    if (job && patch.job_name !== undefined && patch.job_name !== job.job_name) {
      const oldName = job.job_name
      setLineage(prevL => prevL.map(l => l.job_name === oldName ? { ...l, job_name: patch.job_name! } : l))
    }
    setJobs(prev => prev.map(j => j.id === id ? { ...j, ...patch } : j))
  }

  // ── Lineage helpers ──
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

        {/* Stepper */}
        <Stepper step={step} setStep={setStep} errors={stepErrors} />

        {/* Error banner */}
        {curStepErrors.length > 0 && (
          <div className="bg-red-900/20 border border-red-800 rounded-lg px-3 py-2">
            {curStepErrors.map((e, i) => (
              <p key={i} className="text-xs text-red-400">⚠ {e}</p>
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
                  value={form.domain}
                  onChange={e => f('domain', e.target.value.toUpperCase())}
                  placeholder="ex: COBRANCA"
                  className="bg-panel border border-edge text-ink rounded-md px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
                />
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
          </div>
        )}

        {/* ── STEP 1: AGENDAMENTO ── */}
        {step === 1 && (
          <div className="flex flex-col gap-3 overflow-y-auto max-h-[55vh] pr-1">
            <Select label="Tipo de agendamento" value={form.schedule_type} onChange={e => f('schedule_type', e.target.value)}>
              {SCHEDULE_TYPES.map(t => <option key={t} value={t}>{SCHEDULE_LABELS[t]}</option>)}
            </Select>

            {/* A cada N horas — intervalo + janela + minuto */}
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

            {/* Horários específicos — lista de horários + dias da semana */}
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

            {/* Diário / Semanal / Mensal / Quinzenal — hora/minuto + dow/dom */}
            {!['on_demand', 'hourly_n', 'custom'].includes(form.schedule_type) && (
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

            {/* Finais de semana vs dias úteis (todos exceto custom/on_demand) */}
            {showBizToggle && (
              <label className="flex items-center gap-2 cursor-pointer bg-canvas border border-edge rounded-lg px-3 py-2">
                <input type="checkbox" checked={form.somente_dias_uteis}
                  onChange={e => f('somente_dias_uteis', e.target.checked)} className="accent-blue-500" />
                <span className="text-sm text-ink">Somente dias úteis (não roda sáb/dom)</span>
              </label>
            )}

            {/* Calendário de bloqueio */}
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

            {/* Preview */}
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
                  {/* Linha 1: nome, ordem, tipo */}
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
                  {/* Linha 2: comando + (SSH p/ shell ou verbose p/ datastage) */}
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
                  </div>
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
                    {/* Origens */}
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
                    {/* Destinos */}
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
            <p className="text-xs text-blue-400 bg-blue-900/10 border border-blue-800/30 rounded-lg px-3 py-2">
              Revise todas as informações antes de salvar. Use o stepper acima para corrigir qualquer etapa.
            </p>

            {/* Identificação */}
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

            {/* Agendamento */}
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

            {/* Jobs */}
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
                        </div>
                        {j.job_command && (
                          <div className="pl-8 flex items-center gap-1">
                            <span className="text-dim text-[10px]">{j.job_type === 'datastage' ? 'Job DataStage:' : 'Comando:'}</span>
                            <span className="font-mono text-[10px] text-ink/80 break-all">{j.job_command}</span>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
              }
            </div>

            {/* Lineage */}
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
              <div className="bg-red-900/20 border border-red-800 rounded-lg px-3 py-2 text-xs text-red-400">
                Erro ao salvar: {(saveMut.error as any)?.message}
              </div>
            )}
          </div>
        )}

        {/* Navigation footer */}
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

// ── ViewModal ──────────────────────────────────────────────────────────────

function ViewModal({ pipeline: p, onClose }: { pipeline: Pipeline; onClose: () => void }) {
  const pill = (v: string, active = false) => (
    <span className={`inline-block px-2 py-0.5 rounded-full text-xs border ${active ? 'bg-green-900/20 text-green-400 border-green-800/40' : 'bg-panel text-dim border-edge'}`}>{v}</span>
  )
  // Célula individual do grid
  const cell = (label: string, val: React.ReactNode, spanFull = false) => (
    <div className={`flex flex-col gap-0.5 ${spanFull ? 'col-span-2' : ''}`}>
      <span className="text-[10px] font-bold uppercase tracking-wider text-dim">{label}</span>
      <div className="text-sm font-medium text-ink min-h-[1.25rem]">
        {val || <span className="text-dim/50 italic text-xs">—</span>}
      </div>
    </div>
  )
  const notifs = [p.envia_msg_inicio && 'Início', p.envia_msg_fim && 'Conclusão', p.envia_msg_erro && 'Erro'].filter(Boolean)
  const cron = p.schedule_type && p.schedule_type !== 'on_demand'
    ? buildCron(p.schedule_type, p.schedule_hour ?? 6, p.schedule_minute ?? 0, p.schedule_dow ?? 1, p.schedule_dom ?? 1)
    : null

  return (
    <Modal open title={p.pipeline_name} onClose={onClose} size="lg">
      {/* Scroll interno — modal não cresce além da viewport */}
      <div className="overflow-y-auto max-h-[70vh] pr-1">
        {/* Seção: Identificação */}
        <div className="mb-4">
          <p className="text-[10px] font-bold uppercase tracking-wider text-blue-400 mb-2 border-b border-edge pb-1">Identificação</p>
          <div className="grid grid-cols-2 gap-x-6 gap-y-3">
            {cell('Projeto',     p.project_name)}
            {cell('Domínio',     p.domain)}
            {cell('Ambiente',    p.ambiente)}
            {cell('Criticidade', <span className={`font-semibold ${critColor(p.criticidade)}`}>{p.criticidade}</span>)}
            {cell('Status',
              <div className="flex flex-wrap gap-1.5">
                {pill(p.active ? 'Ativo' : 'Inativo', !!p.active)}
                {pill(p.dag_criada ? 'DAG ✓' : 'DAG não gerada', !!p.dag_criada)}
              </div>
            )}
            {cell('Tags',
              p.tags
                ? <div className="flex flex-wrap gap-1">{p.tags.split(',').map(t => pill(t.trim(), true))}</div>
                : null
            )}
          </div>
        </div>

        {/* Seção: Agendamento */}
        <div className="mb-4">
          <p className="text-[10px] font-bold uppercase tracking-wider text-blue-400 mb-2 border-b border-edge pb-1">Agendamento</p>
          <div className="grid grid-cols-2 gap-x-6 gap-y-3">
            {cell('Tipo',          p.schedule_type ? SCHEDULE_LABELS[p.schedule_type] ?? p.schedule_type : null)}
            {cell('Horário',       p.scheduled_time)}
            {cell('Expressão CRON', cron)}
            {cell('Data início',   p.dag_start_date || 'Imediato')}
            {cell('SLA',           p.sla_minutos ? `${p.sla_minutos} min` : null)}
            {cell('Depende de',
              p.depends_on
                ? <div className="flex flex-wrap gap-1">{p.depends_on.split(',').map(d => pill(d.trim()))}</div>
                : null
            )}
          </div>
        </div>

        {/* Seção: Execução */}
        <div className="mb-4">
          <p className="text-[10px] font-bold uppercase tracking-wider text-blue-400 mb-2 border-b border-edge pb-1">Execução</p>
          <div className="grid grid-cols-2 gap-x-6 gap-y-3">
            {cell('Runs simultâneas', p.max_active_runs ?? 1)}
            {cell('Retries',          `${p.retries_count ?? 1}x · delay ${p.retry_delay_seconds ?? 300}s`)}
            {cell('Fila (pool)',       p.pool_name || 'padrão')}
            {cell('Notificações',      notifs.length ? notifs.join(' · ') : null)}
            {cell('Última execução',   p.last_execution)}
          </div>
        </div>

        {/* Seção: Metadados */}
        <div className="mb-4">
          <p className="text-[10px] font-bold uppercase tracking-wider text-blue-400 mb-2 border-b border-edge pb-1">Metadados</p>
          <div className="grid grid-cols-2 gap-x-6 gap-y-3">
            {cell('Criado em',  p.created_at)}
            {cell('Atualizado', p.updated_at)}
          </div>
        </div>

        {/* Descrição — full width */}
        {p.descricao && (
          <div className="mb-4">
            <p className="text-[10px] font-bold uppercase tracking-wider text-blue-400 mb-2 border-b border-edge pb-1">Descrição</p>
            <p className="text-xs text-ink whitespace-pre-wrap leading-relaxed">{p.descricao}</p>
          </div>
        )}

        {/* Runbook — full width */}
        {p.runbook_md && (
          <div>
            <p className="text-[10px] font-bold uppercase tracking-wider text-blue-400 mb-2 border-b border-edge pb-1">Runbook</p>
            <pre className="text-xs text-dim whitespace-pre-wrap font-mono bg-canvas border border-edge rounded-lg p-3 leading-relaxed">{p.runbook_md}</pre>
          </div>
        )}
      </div>
    </Modal>
  )
}

// ── AuditModal ─────────────────────────────────────────────────────────────

function AuditGroup({ day, rows }: { day: string; rows: AuditRow[] }) {
  const [open, setOpen] = useState(false)
  const fmt  = day.split('-').reverse().join('/')
  const user = rows[0]?.changed_by ?? '—'
  return (
    <div className="border border-edge rounded-lg mb-2 overflow-hidden">
      <button onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between px-3 py-2 bg-canvas hover:bg-edge/20 transition-colors text-left">
        <span className="text-sm font-semibold">{fmt}</span>
        <span className="text-xs text-dim">{user} · {rows.length} campo(s)</span>
        {open ? <ChevronDown size={14} className="text-dim" /> : <ChevronRight size={14} className="text-dim" />}
      </button>
      {open && (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-t border-edge bg-canvas/50 text-dim">
                {['Hora','Usuário','Campo','Antes','Depois'].map(h => (
                  <th key={h} className="px-3 py-1.5 text-left font-medium">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => {
                const time = r.changed_at.includes('T')
                  ? r.changed_at.split('T')[1].substring(0, 8)
                  : r.changed_at.substring(11, 19)
                return (
                  <tr key={i} className="border-t border-edge/40">
                    <td className="px-3 py-1.5 text-dim">{time}</td>
                    <td className="px-3 py-1.5">{r.changed_by || '—'}</td>
                    <td className="px-3 py-1.5 font-medium">{r.field_name || '—'}</td>
                    <td className="px-3 py-1.5 text-dim truncate max-w-[150px]" title={r.old_value ?? ''}>{(r.old_value ?? '—').substring(0, 60)}</td>
                    <td className="px-3 py-1.5 truncate max-w-[150px]" title={r.new_value ?? ''}>{(r.new_value ?? '—').substring(0, 60)}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function AuditModal({ pipeline, onClose }: { pipeline: Pipeline; onClose: () => void }) {
  const { data, isLoading } = useQuery<{ data: AuditRow[] }>({
    queryKey: ['pipeline-audit', pipeline.pipeline_name],
    queryFn: () => apiFetch(`/audit?pipeline_name=${encodeURIComponent(pipeline.pipeline_name)}&limit=50`),
  })
  const rows = data?.data ?? []
  const byDate = useMemo(() => {
    const m: Record<string, AuditRow[]> = {}
    rows.forEach(r => {
      const day = (r.changed_at || '').substring(0, 10) || 'Desconhecido'
      if (!m[day]) m[day] = []
      m[day].push(r)
    })
    return Object.entries(m).sort(([a], [b]) => b.localeCompare(a))
  }, [rows])

  return (
    <Modal open title={`Histórico — ${pipeline.pipeline_name}`} onClose={onClose} size="lg">
      <div className="text-xs text-dim bg-canvas border border-edge rounded-lg px-3 py-2 mb-3">
        📌 São exibidas as <strong className="text-ink">últimas 50 alterações</strong>. O registro de criação é sempre preservado.
      </div>
      {isLoading && <div className="py-8 text-center text-dim text-sm">Carregando…</div>}
      {!isLoading && rows.length === 0 && (
        <div className="py-12 flex flex-col items-center gap-2 text-dim">
          <History size={32} className="opacity-30" />
          <p className="text-sm">Sem histórico registrado</p>
          <p className="text-xs">Alterações futuras aparecerão aqui.</p>
        </div>
      )}
      {byDate.map(([day, dayRows]) => <AuditGroup key={day} day={day} rows={dayRows} />)}
    </Modal>
  )
}

// ── LineageModal ───────────────────────────────────────────────────────────

function LineageModal({ pipeline, onClose }: { pipeline: Pipeline; onClose: () => void }) {
  const { data, isLoading, error } = useQuery<{ pipeline_name: string; jobs: LineageJob[] }>({
    queryKey: ['pipeline-lineage', pipeline.pipeline_name],
    queryFn: () => apiFetch(`/lineage?pipeline_name=${encodeURIComponent(pipeline.pipeline_name)}`),
  })
  const jobs = data?.jobs ?? []

  const origens = useMemo(() => {
    const seen: Record<string, LineageObject> = {}
    jobs.forEach(j => (j.origens || []).forEach(o => {
      const k = o.object_name.toLowerCase()
      if (!seen[k]) seen[k] = o
    }))
    return Object.values(seen).sort((a, b) => a.object_name.localeCompare(b.object_name))
  }, [jobs])

  const destinos = useMemo(() => {
    const seen: Record<string, LineageObject> = {}
    jobs.forEach(j => (j.destinos || []).forEach(o => {
      const k = o.object_name.toLowerCase()
      if (!seen[k]) seen[k] = o
    }))
    return Object.values(seen).sort((a, b) => a.object_name.localeCompare(b.object_name))
  }, [jobs])

  return (
    <Modal open title={`Lineage — ${pipeline.pipeline_name}`} onClose={onClose} size="lg">
      {isLoading && <div className="py-8 text-center text-dim text-sm">Carregando lineage…</div>}
      {!!error && <p className="text-red-400 text-sm py-4">Erro ao carregar lineage</p>}
      {!isLoading && !error && jobs.length === 0 && (
        <div className="py-12 flex flex-col items-center gap-2 text-dim">
          <GitBranch size={32} className="opacity-30" />
          <p className="text-sm">Nenhum job cadastrado</p>
          <p className="text-xs">Adicione jobs ao pipeline para visualizar o lineage.</p>
        </div>
      )}
      {!isLoading && jobs.length > 0 && (
        <>
          <div className="overflow-x-auto">
            <div className="grid grid-cols-[1fr_36px_auto_36px_1fr] gap-2 items-start py-2 min-w-[480px]">
              <div>
                <div className="text-[10px] font-bold uppercase tracking-wider text-blue-400 mb-2 text-center">
                  Origens ({origens.length})
                </div>
                <div className="flex flex-col gap-1.5">
                  {origens.length ? origens.map(o => (
                    <div key={o.object_name}
                      className="border border-blue-800/40 bg-blue-900/10 rounded-lg px-2.5 py-1.5 text-xs"
                      title={`${o.object_name}${o.database_name ? ' · ' + o.database_name : ''}`}>
                      <div className="font-mono font-medium text-blue-300 truncate">{o.object_name}</div>
                      <div className="text-[10px] text-dim/60">{o.database_name || o.object_type}</div>
                    </div>
                  )) : <span className="text-xs text-dim/50 italic text-center block mt-2">sem origens</span>}
                </div>
              </div>
              <div className="text-center text-dim text-xl font-thin mt-8">→</div>
              <div className="flex flex-col items-center mt-4">
                <div className="border border-edge bg-panel rounded-xl px-4 py-3 min-w-[140px] text-center">
                  <div className="font-mono text-sm font-bold text-ink truncate">{pipeline.pipeline_name}</div>
                  <div className="text-[10px] text-dim mt-0.5">{jobs.length} job(s)</div>
                </div>
              </div>
              <div className="text-center text-dim text-xl font-thin mt-8">→</div>
              <div>
                <div className="text-[10px] font-bold uppercase tracking-wider text-green-400 mb-2 text-center">
                  Destinos ({destinos.length})
                </div>
                <div className="flex flex-col gap-1.5">
                  {destinos.length ? destinos.map(o => (
                    <div key={o.object_name}
                      className="border border-green-800/40 bg-green-900/10 rounded-lg px-2.5 py-1.5 text-xs"
                      title={`${o.object_name}${o.database_name ? ' · ' + o.database_name : ''}`}>
                      <div className="font-mono font-medium text-green-300 truncate">{o.object_name}</div>
                      <div className="text-[10px] text-dim/60">{o.database_name || o.object_type}</div>
                    </div>
                  )) : <span className="text-xs text-dim/50 italic text-center block mt-2">sem destinos</span>}
                </div>
              </div>
            </div>
          </div>
          <p className="text-xs text-dim/60 text-center border-t border-edge pt-2 mt-1">
            Visualização consolidada — para detalhe por job, use Governança › Lineage.
          </p>
        </>
      )}
    </Modal>
  )
}

// ── InactivateModal ────────────────────────────────────────────────────────

function InactivateModal({ pipeline, onClose }: { pipeline: Pipeline; onClose: () => void }) {
  const qc   = useQueryClient()
  const user = useAuthStore(s => s.user)
  const mut  = useMutation({
    mutationFn: () => apiFetch('/pipelines/register', {
      method: 'POST',
      body: JSON.stringify({
        pipeline_name:       pipeline.pipeline_name,
        scheduled_time:      pipeline.scheduled_time ?? '00:00:00',
        schedule_type:       pipeline.schedule_type,
        schedule_hour:       pipeline.schedule_hour,
        schedule_minute:     pipeline.schedule_minute,
        schedule_dow:        pipeline.schedule_dow,
        schedule_dom:        pipeline.schedule_dom,
        active:              0,
        envia_msg_inicio:    pipeline.envia_msg_inicio,
        envia_msg_fim:       pipeline.envia_msg_fim,
        envia_msg_erro:      pipeline.envia_msg_erro,
        project_name:        pipeline.project_name ?? '',
        domain:              pipeline.domain ?? '',
        tags:                pipeline.tags ?? '',
        dag_criada:          pipeline.dag_criada,
        descricao:           pipeline.descricao ?? null,
        criticidade:         pipeline.criticidade ?? 'Media',
        sla_minutos:         pipeline.sla_minutos ?? null,
        ambiente:            pipeline.ambiente ?? 'PROD',
        max_active_runs:     pipeline.max_active_runs ?? 1,
        retries_count:       pipeline.retries_count ?? 1,
        retry_delay_seconds: pipeline.retry_delay_seconds ?? 300,
        pool_name:           pipeline.pool_name ?? null,
        depends_on:          pipeline.depends_on ?? null,
        runbook_md:          pipeline.runbook_md ?? null,
        dag_start_date:      pipeline.dag_start_date ?? null,
        changed_by:          user?.matricula ?? 'react-ui',
      }),
    }),
    onSuccess: () => {
      toast.success(`Pipeline "${pipeline.pipeline_name}" inativado`)
      qc.invalidateQueries({ queryKey: ['pipelines'] })
      onClose()
    },
    onError: (e: any) => toast.error(e.message),
  })
  return (
    <Modal open title="Inativar pipeline" onClose={onClose} size="sm">
      <div className="flex flex-col gap-4">
        <p className="text-sm text-dim">
          Inativar <span className="font-mono text-ink font-medium">{pipeline.pipeline_name}</span>?
          Pode ser reativado a qualquer momento pela edição.
        </p>
        <div className="flex justify-end gap-2 border-t border-edge pt-3">
          <Button variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button loading={mut.isPending} className="border-amber-800/40 text-amber-400"
            onClick={() => mut.mutate()}>
            <PowerOff size={13} /> Inativar
          </Button>
        </div>
      </div>
    </Modal>
  )
}

// ── GenDagModal ────────────────────────────────────────────────────────────

function GenDagModal({ pipeline, onConfirm, onClose, loading }: {
  pipeline: Pipeline; onConfirm: () => void; onClose: () => void; loading: boolean
}) {
  return (
    <Modal open title={pipeline.dag_criada ? 'Regenerar DAG' : 'Gerar DAG'} onClose={onClose} size="sm">
      <div className="flex flex-col gap-4">
        <p className="text-sm text-dim">
          {pipeline.dag_criada
            ? <>Regenerar a DAG de <span className="font-mono text-ink font-medium">{pipeline.pipeline_name}</span>? Isso irá atualizar a DAG no Airflow com as configurações atuais.</>
            : <>Gerar a DAG para <span className="font-mono text-ink font-medium">{pipeline.pipeline_name}</span> no Airflow via etl_dag_factory?</>}
        </p>
        {pipeline.dag_criada ? (
          <p className="text-xs text-amber-400 bg-amber-900/15 border border-amber-800/40 rounded-lg px-3 py-2">
            ⚠ A DAG existente será sobrescrita com as configurações atuais do pipeline.
          </p>
        ) : null}
        <div className="flex justify-end gap-2 border-t border-edge pt-3">
          <Button variant="secondary" onClick={onClose} disabled={loading}>Cancelar</Button>
          <Button loading={loading} className="border-blue-800/40 text-blue-400" onClick={onConfirm}>
            <Settings size={13} /> {pipeline.dag_criada ? 'Regenerar' : 'Gerar DAG'}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

// ── ExecModal ──────────────────────────────────────────────────────────────

function ExecModal({ pipeline, onConfirm, onClose, loading }: {
  pipeline: Pipeline; onConfirm: () => void; onClose: () => void; loading: boolean
}) {
  return (
    <Modal open title="Executar pipeline agora" onClose={onClose} size="sm">
      <div className="flex flex-col gap-4">
        <p className="text-sm text-dim">
          Disparar <span className="font-mono text-ink font-medium">{pipeline.pipeline_name}</span> agora, fora do agendamento?
        </p>
        <p className="text-xs text-amber-400 bg-amber-900/15 border border-amber-800/40 rounded-lg px-3 py-2">
          ⚠ Inicia uma execução imediata no Airflow. Certifique-se que não há execução ativa.
        </p>
        <div className="flex justify-end gap-2 border-t border-edge pt-3">
          <Button variant="secondary" onClick={onClose} disabled={loading}>Cancelar</Button>
          <Button loading={loading} className="border-green-800/40 text-green-400" onClick={onConfirm}>
            <Play size={13} /> Executar
          </Button>
        </div>
      </div>
    </Modal>
  )
}

// ── Pipeline row ───────────────────────────────────────────────────────────

function PipelineRow({ pipeline: p, isViewer, onView, onEdit, onLineage, onAudit, onInactivate, onGenDag, onExec }: {
  pipeline: Pipeline; isViewer: boolean
  onView: () => void; onEdit: () => void; onLineage: () => void
  onAudit: () => void; onInactivate: () => void; onGenDag: () => void; onExec: () => void
}) {
  return (
    <div className="flex items-center gap-2 px-4 py-2 border-t border-edge/30 hover:bg-edge/10 transition-colors group">
      {/* ── Metadados fixos à esquerda (sempre visíveis, mesma largura) ── */}
      <span className={`w-2 h-2 rounded-full flex-shrink-0 ${p.active ? 'bg-green-500' : 'bg-slate-600'}`}
        title={p.active ? 'Ativo' : 'Inativo'} />
      <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded border flex-shrink-0 w-[46px] text-center ${p.dag_criada ? 'text-green-400 border-green-800/40 bg-green-900/10' : 'text-dim border-edge bg-canvas'}`}>
        {p.dag_criada ? 'DAG ✓' : 'DAG —'}
      </span>
      <span className="text-[10px] text-dim flex-shrink-0 tabular-nums w-[42px]">
        {p.scheduled_time ? p.scheduled_time.substring(0, 5) : '—:——'}
      </span>
      <span className="text-[10px] flex-shrink-0 w-4 text-center"
        title={p.envia_msg_inicio || p.envia_msg_fim || p.envia_msg_erro
          ? ['Início','Conclusão','Erro'].filter((_,i) => [p.envia_msg_inicio,p.envia_msg_fim,p.envia_msg_erro][i]).join(', ')
          : 'Sem notificações'}>
        {(p.envia_msg_inicio || p.envia_msg_fim || p.envia_msg_erro) ? '✉' : ''}
      </span>

      {/* ── Nome do pipeline (ocupa espaço restante) ── */}
      <span className="font-mono text-xs text-ink font-medium flex-1 truncate min-w-0" title={p.pipeline_name}>
        {p.pipeline_name}
      </span>

      {/* ── Criticidade ── */}
      <span className={`text-[9px] font-bold flex-shrink-0 w-10 text-right ${critColor(p.criticidade)}`}
        title={`Criticidade: ${p.criticidade}`}>
        {p.criticidade}
      </span>

      {/* ── Ações (aparecem no hover, não empurram o layout) ── */}
      <div className="flex items-center gap-0.5 flex-shrink-0 opacity-0 group-hover:opacity-100 focus-within:opacity-100 transition-opacity border-l border-edge/40 pl-2 ml-1">
        <Button variant="ghost" size="sm" title="Visualizar" aria-label={`Visualizar ${p.pipeline_name}`} onClick={onView}><Eye size={12} /></Button>
        <span className={isViewer ? 'invisible pointer-events-none' : ''}>
          <Button variant="ghost" size="sm" title="Editar" aria-label={`Editar ${p.pipeline_name}`} onClick={onEdit}><Edit size={12} /></Button>
        </span>
        <Button variant="ghost" size="sm" title="Lineage" aria-label={`Ver lineage de ${p.pipeline_name}`} onClick={onLineage}><GitBranch size={12} /></Button>
        <Button variant="ghost" size="sm" title="Histórico" aria-label={`Ver histórico de ${p.pipeline_name}`} onClick={onAudit}><History size={12} /></Button>
        <span className={isViewer || !p.active ? 'invisible pointer-events-none' : ''}>
          <Button variant="ghost" size="sm" title="Inativar" aria-label={`Inativar ${p.pipeline_name}`} onClick={onInactivate}
            className="text-amber-500/60 hover:text-amber-400"><PowerOff size={12} /></Button>
        </span>
        <span className={isViewer ? 'invisible pointer-events-none' : ''}>
          <Button variant="ghost" size="sm"
            title={p.dag_criada ? 'Regenerar DAG' : 'Gerar DAG'}
            aria-label={p.dag_criada ? `Regenerar DAG de ${p.pipeline_name}` : `Gerar DAG para ${p.pipeline_name}`}
            onClick={onGenDag}
            className={p.dag_criada ? 'text-blue-400/70 hover:text-blue-300' : 'text-dim hover:text-ink'}>
            <Settings size={12} />
          </Button>
        </span>
        <span className={isViewer || !p.dag_criada ? 'invisible pointer-events-none' : ''}>
          <Button variant="ghost" size="sm" title="Executar agora" aria-label={`Executar ${p.pipeline_name} agora`} onClick={onExec}
            className="text-green-500/60 hover:text-green-400"><Play size={12} /></Button>
        </span>
      </div>
    </div>
  )
}

// ── Main component ─────────────────────────────────────────────────────────

export default function Pipelines() {
  const qc      = useQueryClient()
  const user    = useAuthStore(s => s.user)
  const isViewer = user?.perfil === 'consulta'

  const [nameFilter,    setNameFilter]    = useState('')
  const [projectFilter, setProjectFilter] = useState('')
  const [activeFilter,  setActiveFilter]  = useState('')
  const [domainFilter,  setDomainFilter]  = useState('')
  const [page, setPage] = useState(0)
  const LIMIT = 50

  // projects and domains expanded by the user — all start collapsed
  const [expanded,     setExpanded]     = useState<Set<string>>(new Set())
  const [expandedDoms, setExpandedDoms] = useState<Set<string>>(new Set())

  const [viewPipeline,        setViewPipeline]        = useState<Pipeline | undefined>()
  const [editPipeline,        setEditPipeline]        = useState<Pipeline | undefined>()
  const [showNew,             setShowNew]             = useState(false)
  const [auditPipeline,       setAuditPipeline]       = useState<Pipeline | undefined>()
  const [lineagePipeline,     setLineagePipeline]     = useState<Pipeline | undefined>()
  const [inactivatePipeline,  setInactivatePipeline]  = useState<Pipeline | undefined>()
  const [execPipeline,        setExecPipeline]        = useState<Pipeline | undefined>()
  const [genDagPipeline,      setGenDagPipeline]      = useState<Pipeline | undefined>()
  const revalidateTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    return () => { if (revalidateTimerRef.current) clearTimeout(revalidateTimerRef.current) }
  }, [])

  const qs = new URLSearchParams({ limit: String(LIMIT), offset: String(page * LIMIT) })
  if (nameFilter)         qs.set('filter_name',    nameFilter)
  if (projectFilter)      qs.set('filter_project', projectFilter)
  if (activeFilter !== '') qs.set('filter_active', activeFilter)

  const { data, isLoading } = useQuery<{ total: number; pages: number; data: Pipeline[] }>({
    queryKey: ['pipelines', nameFilter, projectFilter, activeFilter, page],
    queryFn: () => apiFetch(`/pipelines?${qs}`),
  })

  const { data: projData } = useQuery<{ projects: string[] }>({
    queryKey: ['pipeline-projects'],
    queryFn: () => apiFetch('/pipelines/projects'),
    staleTime: 300_000,
  })
  const projects = projData?.projects ?? []

  const tree = useMemo(() => {
    const t: Record<string, Record<string, Pipeline[]>> = {}
    ;(data?.data ?? []).forEach(p => {
      const proj = p.project_name || '(sem projeto)'
      const dom  = p.domain       || '(sem domínio)'
      if (domainFilter && dom.toUpperCase() !== domainFilter.toUpperCase()) return
      if (!t[proj]) t[proj] = {}
      if (!t[proj][dom]) t[proj][dom] = []
      t[proj][dom].push(p)
    })
    return t
  }, [data, domainFilter])

  const projNames = useMemo(() => Object.keys(tree).sort(), [tree])

  // all unique domains from current page (for domain filter dropdown)
  const allDomains = useMemo(() => {
    const s = new Set<string>()
    ;(data?.data ?? []).forEach(p => { if (p.domain) s.add(p.domain) })
    return [...s].sort()
  }, [data])

  // Gerar DAG via factory
  const genDagMut = useMutation({
    mutationFn: (p: Pipeline) => {
      const runId = `orquestra_ui_${Date.now()}`
      return apiFetch(`/airflow/dags/${DAG_FACTORY_ID}/dagRuns`, {
        method: 'POST',
        body: JSON.stringify({ dag_run_id: runId, conf: { pipeline_name: p.pipeline_name } }),
      })
    },
    onSuccess: (_d, p) => {
      toast.success(`Factory disparada para "${p.pipeline_name}" — aguarde para ver resultado.`)
      setGenDagPipeline(undefined)
      // Revalida após 10s para refletir dag_criada=1
      if (revalidateTimerRef.current) clearTimeout(revalidateTimerRef.current)
      revalidateTimerRef.current = setTimeout(() => qc.invalidateQueries({ queryKey: ['pipelines'] }), 10_000)
    },
    onError: (e: unknown) => {
      const msg = e instanceof Error ? e.message : 'Erro inesperado'
      toast.error(`Erro ao gerar DAG: ${msg}`)
    },
  })

  // Executar agora
  const execMut = useMutation({
    mutationFn: (p: Pipeline) => {
      const dagId = pipelineToDagId(p.pipeline_name)
      return apiFetch<{ dag_run_id?: string }>(`/airflow/dags/${encodeURIComponent(dagId)}/dagRuns`, {
        method: 'POST',
        body: JSON.stringify({ dag_run_id: `manual_orq_${Date.now()}`, conf: {} }),
      })
    },
    onSuccess: (res, p) => {
      const dagId = pipelineToDagId(p.pipeline_name)
      setExecPipeline(undefined)
      toast.success(`Pipeline disparado! (${res?.dag_run_id ?? 'ok'})`)
      window.open(`${AIRFLOW_UI}/dags/${dagId}/grid`, '_blank')
    },
    onError: (e: unknown) => {
      const msg = e instanceof Error ? e.message : ''
      if (msg.startsWith('404')) toast.error('DAG não encontrada. Gere o DAG primeiro.')
      else if (msg.startsWith('409')) toast.error('Já existe uma execução ativa para este pipeline.')
      else toast.error(msg || 'Erro ao executar')
    },
  })

  const fetchPipelineNames = useCallback(
    (q: string) =>
      apiFetch<{ data: { pipeline_name: string }[] }>(`/pipelines?limit=10&filter_name=${encodeURIComponent(q)}`)
        .then(r => r.data.map(p => p.pipeline_name)),
    [],
  )

  const total = data?.total ?? 0
  const pages = data?.pages ?? 1

  return (
    <div className="flex flex-col gap-4">

      {/* Filter bar */}
      <div className="bg-panel border border-edge rounded-xl p-4">
        <div className="flex flex-wrap gap-3 items-end">
          <Autocomplete
            label="Nome"
            value={nameFilter}
            onChange={v => { setNameFilter(v); setPage(0) }}
            fetchSuggestions={fetchPipelineNames}
            placeholder="filtrar por nome…"
            className="w-64"
          />
          <Select label="Projeto" value={projectFilter}
            onChange={e => { setProjectFilter(e.target.value); setPage(0) }} className="w-40">
            <option value="">Todos</option>
            {projects.map(p => <option key={p}>{p}</option>)}
          </Select>
          <Select label="Domínio" value={domainFilter}
            onChange={e => { setDomainFilter(e.target.value); setPage(0) }} className="w-40">
            <option value="">Todos</option>
            {allDomains.map(d => <option key={d}>{d}</option>)}
          </Select>
          <Select label="Status" value={activeFilter}
            onChange={e => { setActiveFilter(e.target.value); setPage(0) }} className="w-32">
            <option value="">Todos</option>
            <option value="1">Ativos</option>
            <option value="0">Inativos</option>
          </Select>
          <div className="flex gap-2 ml-auto items-end">
            <Button variant="secondary" size="sm" onClick={() => { setNameFilter(''); setProjectFilter(''); setDomainFilter(''); setActiveFilter(''); setPage(0) }}>
              × Limpar
            </Button>
            <Button variant="secondary" size="sm" onClick={exportModeloCsv} title="Baixar modelo CSV para importação em massa">
              ↓ Exportar modelo
            </Button>
            {!isViewer && (
              <Button size="sm" onClick={() => setShowNew(true)}>
                <Plus size={13} /> Novo pipeline
              </Button>
            )}
          </div>
        </div>
      </div>

      {/* Count + pagination */}
      {!isLoading && (
        <div className="flex items-center justify-between text-xs text-dim px-1">
          <span>{total} pipeline{total !== 1 ? 's' : ''}</span>
          {pages > 1 && (
            <div className="flex items-center gap-2">
              <Button variant="ghost" size="sm" disabled={page === 0} onClick={() => setPage(p => p - 1)}>← Anterior</Button>
              <span>Página {page + 1} de {pages}</span>
              <Button variant="ghost" size="sm" disabled={page + 1 >= pages} onClick={() => setPage(p => p + 1)}>Próxima →</Button>
            </div>
          )}
        </div>
      )}

      {isLoading && <PageSpinner />}

      {!isLoading && total === 0 && (
        <div className="bg-panel border border-edge rounded-xl py-16 flex flex-col items-center gap-2 text-dim">
          <span className="text-4xl">◎</span>
          <p className="text-sm font-medium">Nenhum pipeline encontrado</p>
          <p className="text-xs">Ajuste os filtros ou crie um novo pipeline.</p>
        </div>
      )}

      {/* Tree: projeto → domínio → pipelines */}
      {!isLoading && projNames.map(proj => {
        const isExpanded = expanded.has(proj)
        const domNames   = Object.keys(tree[proj]).sort()
        const totalProj  = domNames.reduce((s, d) => s + tree[proj][d].length, 0)
        const activeProj = domNames.reduce((s, d) => s + tree[proj][d].filter(p => p.active).length, 0)
        return (
          <div key={proj} className="bg-panel border border-edge rounded-xl overflow-hidden">
            <button
              onClick={() => setExpanded(s => { const n = new Set(s); n.has(proj) ? n.delete(proj) : n.add(proj); return n })}
              className="w-full flex items-center gap-2 px-4 py-3 bg-canvas hover:bg-edge/20 transition-colors text-left"
            >
              {isExpanded ? <ChevronDown size={15} className="text-dim flex-shrink-0" /> : <ChevronRight size={15} className="text-dim flex-shrink-0" />}
              <span className="font-semibold text-ink text-sm">{proj}</span>
              <span className="text-xs text-dim">
                {totalProj} pipeline{totalProj !== 1 ? 's' : ''} · {activeProj} ativo{activeProj !== 1 ? 's' : ''}
              </span>
            </button>

            {isExpanded && domNames.map(dom => {
              const domKey      = `${proj}::${dom}`
              const isDomOpen   = expandedDoms.has(domKey)
              const toggleDom   = () => setExpandedDoms(s => { const n = new Set(s); n.has(domKey) ? n.delete(domKey) : n.add(domKey); return n })
              const domPipelines = tree[proj][dom]
              return (
                <div key={dom}>
                  <button
                    onClick={toggleDom}
                    className="w-full flex items-center gap-2 px-5 py-1.5 bg-panel/60 border-t border-edge/30 hover:bg-edge/10 transition-colors text-left"
                  >
                    {isDomOpen
                      ? <ChevronDown size={11} className="text-dim flex-shrink-0" />
                      : <ChevronRight size={11} className="text-dim flex-shrink-0" />}
                    <span className="text-[10px] font-bold uppercase tracking-wider text-dim">{dom}</span>
                    <span className="text-[10px] text-dim/40 ml-1">({domPipelines.length})</span>
                  </button>
                  {isDomOpen && domPipelines.map(p => (
                    <PipelineRow
                      key={p.pipeline_name}
                      pipeline={p}
                      isViewer={isViewer}
                      onView={()        => setViewPipeline(p)}
                      onEdit={()        => setEditPipeline(p)}
                      onLineage={()     => setLineagePipeline(p)}
                      onAudit={()       => setAuditPipeline(p)}
                      onInactivate={()  => setInactivatePipeline(p)}
                      onGenDag={()      => setGenDagPipeline(p)}
                      onExec={()        => setExecPipeline(p)}
                    />
                  ))}
                </div>
              )
            })}
          </div>
        )
      })}

      {/* Modals */}
      {showNew            && <PipelineFormModal onClose={() => setShowNew(false)} />}
      {editPipeline       && <PipelineFormModal pipeline={editPipeline} onClose={() => setEditPipeline(undefined)} />}
      {viewPipeline       && <ViewModal pipeline={viewPipeline} onClose={() => setViewPipeline(undefined)} />}
      {auditPipeline      && <AuditModal pipeline={auditPipeline} onClose={() => setAuditPipeline(undefined)} />}
      {lineagePipeline    && <LineageModal pipeline={lineagePipeline} onClose={() => setLineagePipeline(undefined)} />}
      {inactivatePipeline && <InactivateModal pipeline={inactivatePipeline} onClose={() => setInactivatePipeline(undefined)} />}
      {execPipeline       && (
        <ExecModal
          pipeline={execPipeline}
          loading={execMut.isPending}
          onConfirm={() => execMut.mutate(execPipeline)}
          onClose={() => { if (!execMut.isPending) setExecPipeline(undefined) }}
        />
      )}
      {genDagPipeline     && (
        <GenDagModal
          pipeline={genDagPipeline}
          loading={genDagMut.isPending}
          onConfirm={() => genDagMut.mutate(genDagPipeline)}
          onClose={() => { if (!genDagMut.isPending) setGenDagPipeline(undefined) }}
        />
      )}
    </div>
  )
}
