export interface Pipeline {
  pipeline_name: string
  projeto: string
  dominio?: string
  criticidade?: string
  ativo: boolean
  schedule?: string
  sla_minutos?: number
  descricao?: string
  ambiente?: string
  tags?: string[]
  job_count?: number
}

export interface Job {
  job_name: string
  pipeline_name: string
  ordem: number
  tipo: string
  job_command?: string
  ssh_conn_id?: string
  ativo?: boolean
}

export interface Execucao {
  execution_id: string
  pipeline_name: string
  projeto?: string
  status: 'SUCCESS' | 'FAILED' | 'WARNING' | 'RUNNING' | 'PENDING'
  inicio?: string
  fim?: string
  duracao_segundos?: number
  dag_run_id?: string
  ack?: boolean
}

export interface DashboardData {
  total: number
  sucesso: number
  falha: number
  aviso: number
  rodando: number
  taxa_sucesso: number
  falhas_criticas: number
  fila_datastage?: number
  pipelines: PipelineStatus[]
  falhas: Execucao[]
}

export interface PipelineStatus {
  pipeline_name: string
  projeto: string
  status: string
  ultima_execucao?: string
  criticidade?: string
}

export interface GanttItem {
  pipeline_name: string
  projeto: string
  status: string
  inicio: string
  fim?: string
  duracao_segundos?: number
}

export interface AdminConfig {
  chave: string
  valor: string
  descricao?: string
}

export interface Usuario {
  matricula: string
  perfil: string
  primeiro_nome?: string
  email?: string
  ativo?: boolean
  ultimo_login?: string
}

export interface Perfil {
  nome: string
  descricao?: string
  permissoes?: string[]
}

export interface LineageNode {
  nome: string
  tipo: string
  banco?: string
}

export interface LineageJob {
  job_name: string
  origens: LineageNode[]
  destinos: LineageNode[]
}

export interface MalhaItem {
  pipeline_name: string
  projeto: string
  criticidade?: string
  ativo: boolean
  schedule?: string
  sla_minutos?: number
  ambiente?: string
  dependencias?: string[]
  jobs: { job_name: string; ordem: number; tipo: string }[]
}

export interface DSStatus {
  job_name: string
  status: string
  wave?: number
  pid?: number
  atualizado?: string
  historico?: { status: string; ts: string }[]
  filhos?: { nome: string; status: string; exit_code?: number }[]
}

export interface FactoryRun {
  dag_run_id: string
  status: string
  inicio?: string
  fim?: string
  dags_gerados?: number
}

export interface Versao {
  versao: string
  titulo: string
  descricao?: string
  data?: string
}

export interface TipoJob {
  nome: string
  descricao?: string
  lineage_habilitado?: boolean
  ativo?: boolean
}

export interface Calendario {
  nome: string
  datas: string[]
  descricao?: string
}

export interface Blackout {
  id: number
  inicio: string
  fim?: string
  escopo?: string
  motivo?: string
  ativo?: boolean
}
