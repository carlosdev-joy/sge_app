// ── types ──────────────────────────────────────────────────────────────────

export interface Pipeline {
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
  // scheduling avançado (migrations 017/018/024) — podem vir ausentes
  horarios_especificos?: string | null
  dias_semana?: string | null
  somente_dias_uteis?: number | null
  calendario_nome?: string | null
  trigger_por_dependencia?: number | null
  dias_horarios_mes?: string | null
}

export interface AuditRow {
  changed_at: string
  changed_by: string
  field_name: string
  old_value: string | null
  new_value: string | null
}

export interface LineageObject {
  object_name: string
  object_type: string
  database_name?: string
}

export interface LineageJob {
  job_name: string
  origens: LineageObject[]
  destinos: LineageObject[]
}
