// ── constants ──────────────────────────────────────────────────────────────

export const SCHEDULE_TYPES = ['daily', 'weekly', 'monthly', 'biweekly', 'hourly_n', 'custom', 'monthly_days_times', 'on_demand'] as const
export const SCHEDULE_LABELS: Record<string, string> = {
  daily: 'Diário', weekly: 'Semanal', monthly: 'Mensal', biweekly: 'Quinzenal',
  hourly_n: 'A cada N horas', custom: 'Horários específicos',
  monthly_days_times: 'Dia + Hora Específico', on_demand: 'Sob demanda',
}
export const MAX_MONTH_DAYS = 5
export const CRITICIDADES   = ['Alta', 'Media', 'Baixa'] as const
export const AMBIENTES      = ['PROD', 'HML', 'DEV'] as const
export const DAG_FACTORY_ID = 'etl_dag_factory'

// Job/Lineage — mesmos tipos e regras da tela de Jobs
export const JOB_TYPES = ['datastage', 'shell', 'python', 'storedproc'] as const
export type WizJobType = typeof JOB_TYPES[number]
export const OBJECT_TYPES = ['Tabela', 'View', 'Arquivo', 'Procedure', 'Dataset', 'API'] as const

// Dias da semana — convenção cron (0=Domingo … 6=Sábado)
export const DOW_LABELS: [number, string][] = [
  [0, 'Dom'], [1, 'Seg'], [2, 'Ter'], [3, 'Qua'], [4, 'Qui'], [5, 'Sex'], [6, 'Sáb'],
]

// ── helpers ────────────────────────────────────────────────────────────────

export function pipelineToDagId(name: string) {
  return name
}

// Descreve a configuração de agendamento de forma normalizada para preview/payload
export interface ScheduleConfig {
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
  monthDays?: { dia: number; horarios: string[] }[]  // dias do mês + horários (monthly_days_times)
}

// Uma entrada de "Dia + Hora Específico" no formulário (horariosRaw é texto
// livre "HH:MM, HH:MM" — parse/validação via parseCustomTimes, igual ao
// campo de horários do tipo 'custom')
export interface MonthDayEntry {
  dia: number
  horariosRaw: string
}

// Gera lista de horários "HH:MM" para o tipo "a cada N horas" dentro da janela [startH, endH]
export function hourlyTimes(cfg: ScheduleConfig): string[] {
  const out: string[] = []
  const n = Math.max(1, cfg.intervalH)
  const mm = String(cfg.minute).padStart(2, '0')
  for (let h = cfg.startH; h <= cfg.endH; h += n) {
    out.push(`${String(h).padStart(2, '0')}:${mm}`)
  }
  return out
}

// Parse de "09:00, 13:30" → ["09:00","13:30"] (válidos, ordenados)
export function parseCustomTimes(raw: string): string[] {
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

// Serializa os blocos de "Dia + Hora Específico" para o JSON persistido
// (dias_horarios_mes). Descarta dias sem nenhum horário válido.
export function serializeMonthDaysTimes(entries: MonthDayEntry[]): string {
  const days = entries
    .map(e => ({ dia: e.dia, horarios: parseCustomTimes(e.horariosRaw) }))
    .filter(e => e.horarios.length > 0)
    .sort((a, b) => a.dia - b.dia)
  return JSON.stringify(days)
}

// Parse do JSON persistido (dias_horarios_mes) de volta para os blocos do formulário
export function parseMonthDaysTimes(raw: string | null | undefined): MonthDayEntry[] {
  if (!raw) return []
  try {
    const data = JSON.parse(raw)
    if (!Array.isArray(data)) return []
    return data
      .filter((e: any) => e && typeof e.dia === 'number' && Array.isArray(e.horarios))
      .map((e: any) => ({ dia: e.dia, horariosRaw: e.horarios.join(', ') }))
  } catch {
    return []
  }
}

// Calcula as próximas N execuções, respeitando dia da semana / dia do mês / janela / dias úteis
export function computeNextRuns(cfg: ScheduleConfig, count = 5): string[] {
  if (cfg.type === 'on_demand') return []
  const results: Date[] = []
  const now = new Date()

  function timesForDay(d: Date): { h: number; m: number }[] {
    if (cfg.type === 'hourly_n') return hourlyTimes(cfg).map(t => ({ h: +t.slice(0, 2), m: +t.slice(3) }))
    if (cfg.type === 'custom')   return parseCustomTimes(cfg.customTimes).map(t => ({ h: +t.slice(0, 2), m: +t.slice(3) }))
    if (cfg.type === 'monthly_days_times') {
      const entry = cfg.monthDays?.find(e => e.dia === d.getDate())
      return entry ? entry.horarios.map(t => ({ h: +t.slice(0, 2), m: +t.slice(3) })) : []
    }
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
      case 'monthly_days_times': return cfg.monthDays?.some(e => e.dia === dom) ?? false
      default:         return true
    }
  }

  const cur = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  for (let dayOffset = 0; dayOffset < 366 && results.length < count; dayOffset++) {
    const d = new Date(cur.getTime() + dayOffset * 86400_000)
    if (!dayMatches(d)) continue
    const times = timesForDay(d)
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
export function runsPerDay(cfg: ScheduleConfig): number {
  if (cfg.type === 'hourly_n') return hourlyTimes(cfg).length
  if (cfg.type === 'custom')   return parseCustomTimes(cfg.customTimes).length
  return 1
}

export function exportModeloCsv() {
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

export function critColor(c: string) {
  return c === 'Alta' ? 'text-red-400' : c === 'Media' ? 'text-yellow-400' : 'text-green-400'
}

// Cor do badge por tipo de job (alinhado à tela de Jobs)
export function typeBadgeColor(t: string) {
  const m: Record<string, string> = {
    datastage:  'bg-blue-500/15 text-blue-600 dark:text-blue-400 border border-blue-300 dark:border-blue-800/40',
    shell:      'bg-amber-500/15 text-amber-600 dark:text-amber-400 border border-amber-300 dark:border-amber-800/40',
    python:     'bg-green-500/15 text-green-600 dark:text-green-400 border border-green-300 dark:border-green-800/40',
    storedproc: 'bg-purple-500/15 text-purple-600 dark:text-purple-400 border border-purple-300 dark:border-purple-800/40',
  }
  return m[t] ?? 'bg-slate-500/15 text-slate-500 border border-slate-300 dark:border-slate-700'
}

// CRON simplificado para exibição (ViewModal) — pipelines já persistidos
export function buildCron(type: string, h: number, m: number, dow: number, dom: number) {
  const t = (type || 'daily').toLowerCase()
  if (t === 'on_demand') return '(sem agendamento automático)'
  if (t === 'hourly')    return `${m} * * * *`
  if (t === 'daily')     return `${m} ${h} * * *`
  if (t === 'weekly')    return `${m} ${h} * * ${dow}`
  if (t === 'monthly')   return `${m} ${h} ${dom} * *`
  if (t === 'biweekly')  return `${m} ${h} ${dom},${dom + 15} * *`
  if (t === 'custom')    return '(horários específicos)'
  if (t === 'monthly_days_times') return '(dia + hora específico)'
  return `${m} ${h} * * *`
}
