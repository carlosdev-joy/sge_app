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
  // motivo de inativação (migration 031) — preenchido quando active=0
  motivo_inativacao?: string | null
  inativado_por?: string | null
  inativado_em?: string | null
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
  // Janela e virada (migration 067) — SEM cast: foi um `as unknown as Record`
  // que escondeu do tsc o round-trip quebrado destes três campos (D26).
  // 'HH:MM' ou null; null também quando a 067 não foi aplicada (degradação).
  hora_virada: string | null
  nao_iniciar_antes: string | null
  hora_limite_dependencia: string | null
  // Pendência de publicação da DAG (migration 073, D30) — 1 quando a DAG no
  // Airflow roda uma configuração anterior à do cadastro; null sem a 073.
  dag_config_pendente?: number | null
}

// ── GET /pipelines/dependencias/estado (F5) ────────────────────────────────
// O painel fala o predicado do MOTOR (port de dags/utils/dependencias.py):
// `liberado`/`faltantes` decidem a mensagem; `predecessores` é só exibição.

export interface DependenciaPredecessor {
  nome: string
  status: string | null          // última execução na data (exibição)
  sucesso_na_data: boolean       // do predicado EXISTS — nunca do "mais recente"
}

export interface DependenciaCorrida {
  status: string
  execution_id: string | null
  inicio: string | null
  fim: string | null
  disparado_por: string | null
  motivo: string | null
}

export interface DependenciaEstadoItem {
  pipeline_name: string
  liberado: boolean
  faltantes: string[]
  predecessores: DependenciaPredecessor[]
  corrida: DependenciaCorrida | null
  janela: {
    hora_virada: string | null
    nao_iniciar_antes: string | null
    hora_limite_dependencia: string | null
  }
  eventos: { tipo: string; detalhe: string | null; detectado_em: string | null }[]
}

export interface DependenciasEstadoApi {
  data_referencia: string
  data: DependenciaEstadoItem[]
  migration_067_pendente?: boolean
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
