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
  verbose_log?: boolean
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

// ─── A CORRIDA de malha (F4 — spec-malha-execucao §9.1) ──────────────────────
// O ciclo da malha como REGISTRO (etl_malha_execucao, migration 085). É ele
// que responde "a malha rodou?" — e não mais "qual membro começou por último",
// que é a chave de comparação do defeito que esta fase mata: `CARGA_A` falha
// às 03:00, `CARGA_B` conclui às 03:40, e o card dizia "sucesso · CARGA_B".
//
// ⚠️ A chave `corrida` é OPCIONAL no payload, e a ausência dela é o contrato
// (Decisão 41): API anterior à F4, banco sem a 085 e malha que ainda não teve
// ciclo nenhum caem todas no mesmo lugar — o fallback "(membro mais recente)".
// Nunca vem `corrida: null` para o front interpretar.

/** Um membro que a corrida está esperando, com a CLASSE do problema — três
 *  donos diferentes, nunca somados em "3 pendentes" (Decisão 21). */
export interface PendenteCorrida {
  pipeline: string
  /** falhou | orfa | nao_liberou | nao_partiu — em ordem de gravidade, e o
   *  servidor já entrega ordenado: `pendentes[0]` é o que a tela nomeia. */
  classe: string
  desde: string | null
  /** De quem esta pendência espera. `null` no CARD de propósito (respondê-lo
   *  por card seria um N+1 na lista inteira); o painel preenche. */
  faltante: string | null
}

/** O CABEÇALHO do ciclo — exatamente o que `GET /malhas/{m}/corridas` entrega
 *  por linha. Separado de `CorridaApi` de propósito: a lista NÃO traz os
 *  derivados da leitura (saúde, denominador, pendentes), e tipá-los como
 *  presentes convidaria a tela a ler `undefined` como "zero". */
export interface CorridaCabecalho {
  id: number
  malha_name: string
  /** ODATE do ciclo — 'YYYY-MM-DD'. É o dia de PROCESSAMENTO, não o relógio. */
  data_referencia: string
  /** N-ésima corrida do dia. Só vira texto quando > 1 (Decisão 74). */
  sequencia: number
  /** ABERTA | CONCLUIDA | FALHA | EXPIRADA | ABORTADA | SEM_TRABALHO | CANCELADA */
  status: string
  aberta_em: string | null
  fechada_em: string | null
  fechada_por: string | null
  origem: string | null
  aberta_por: string | null
  ancora_pipeline: string | null
  modo_fechamento: string | null
  teto_em: string | null
  tentativas: number
  reaberta_em: string | null
  motivo: string | null
}

/** A corrida com os DERIVADOS DA LEITURA — o que o card e a faixa consomem. */
export interface CorridaApi extends CorridaCabecalho {
  reaberta_por: string | null
  /** SAÚDE — só existe com o ciclo ABERTO (§6.1): OK | COM_FALHA | ATRASADA |
   *  SEM_PROGRESSO. É ela que manda na COR enquanto a corrida está em voo. */
  saude: string | null
  /** `apurado_em − aberta_em`, subtraído NO SERVIDOR (Decisão 60). O front
   *  soma a ele o que passou no relógio LOCAL — nunca subtrai `aberta_em` de
   *  `Date.now()`. */
  decorrido_min: number | null
  /** Relógio do BANCO no instante da apuração. Alimenta SÓ o texto absoluto do
   *  tooltip: no dev o banco está 3 h à frente do navegador. */
  apurado_em: string | null
  /** Denominador do snapshot — e ele NÃO ENCOLHE durante a corrida (D52). */
  membros_total: number | null
  membros_ok: number | null
  membros_vivos: number | null
  /** `PULADO` / regra de dia. Conta no denominador, nunca como concluído. */
  membros_dispensados: number | null
  /** Fica FORA do que a barra preenche (D54) — é chip, não comprimento. */
  membros_travados: number | null
  membros_fora_do_odate: number | null
  /** Inativos na abertura: ficaram FORA do denominador, mas não somem. */
  membros_inativos: number | null
  pendentes: PendenteCorrida[]
  ultimo_movimento_em: string | null
  sem_sinal_min: number | null
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
