// Tipos e utilitários do módulo "Cópia de Dados".
//
// Os tipos espelham EXATAMENTE o formato snake_case do backend
// (api/routers/copias.py + api/services/copy_sql.py) — não renomear campos.

// ── Tipos das respostas da API ────────────────────────────────────────────────

export interface Conexao {
  conn_id: string
  host: string
  port?: number | null
  schema?: string
  description?: string
}

export interface TabelaInfo { schema: string; name: string; rows: number }

export interface ColunaInfo {
  name: string
  type: string
  max_length: number
  precision: number
  scale: number
  is_nullable: boolean
  is_identity: boolean
  is_pk: boolean
}

// via: 'direto' (credencial do app) | 'cache' | 'airflow' (RPC pela DAG — lento)
export interface DatabasesResp { databases: string[]; via: string }
export interface TablesResp { tables: TabelaInfo[]; via: string }
export interface ColumnsResp { columns: ColunaInfo[]; particao_sugerida: string | null; via: string }
export interface PreviewResp { columns: string[]; rows: unknown[][]; via: string }

// ── Transformações (formato colunas_json do backend) ─────────────────────────

export type TransformTipo =
  | 'pad_condicional' | 'pad_fixo' | 'trim' | 'upper' | 'lower'
  | 'substring' | 'cast' | 'sql'

export interface CasoPad { valor: string; tamanho: number }

export interface Transform {
  tipo: TransformTipo
  // pad_condicional
  campo_condicao?: string
  casos?: CasoPad[]
  // pad_fixo / substring
  tamanho?: number
  // substring
  inicio?: number
  // cast
  tipo_sql?: string
  // sql (expressão livre validada no backend)
  expressao?: string
}

export interface ColunaMapeada {
  origem: string
  destino: string
  transform: Transform | null
}

// Rótulos das transformações no Select do passo Colunas (ordem da spec).
export const TRANSFORM_OPTIONS: { value: '' | TransformTipo; label: string }[] = [
  { value: '',                label: 'Nenhuma' },
  { value: 'pad_condicional', label: 'Zeros à esquerda condicional' },
  { value: 'pad_fixo',        label: 'Zeros à esquerda' },
  { value: 'trim',            label: 'Trim' },
  { value: 'upper',           label: 'Maiúsculas' },
  { value: 'lower',           label: 'Minúsculas' },
  { value: 'substring',       label: 'Substring' },
  { value: 'cast',            label: 'Cast' },
  { value: 'sql',             label: 'SQL livre' },
]

export const TRANSFORM_LABELS: Record<TransformTipo, string> = Object.fromEntries(
  TRANSFORM_OPTIONS.filter(o => o.value).map(o => [o.value, o.label]),
) as Record<TransformTipo, string>

// Sugestão de casos do pad_condicional (CNPJ 14 / CPF 11) — pré-preenche o editor.
export const CASOS_SUGESTAO: CasoPad[] = [
  { valor: 'J', tamanho: 14 },
  { valor: 'F', tamanho: 11 },
]

// Tipos aceitos na allowlist do cast (backend valida por regex — só sugestão).
export const CAST_TIPOS_SUGERIDOS = [
  'INT', 'BIGINT', 'DECIMAL(18,2)', 'VARCHAR(50)', 'NVARCHAR(100)',
  'DATE', 'DATETIME', 'FLOAT', 'BIT',
]

// Tipos de coluna que a DAG sabe dividir em faixas (coluna de partição).
export const PARTICAO_TIPOS = new Set(['int', 'bigint', 'decimal', 'numeric', 'date', 'datetime'])

/** Transform recém-criado ao trocar o tipo no Select (com defaults úteis). */
export function novoTransform(tipo: TransformTipo): Transform {
  switch (tipo) {
    case 'pad_condicional':
      return { tipo, campo_condicao: '', casos: CASOS_SUGESTAO.map(c => ({ ...c })) }
    case 'pad_fixo':  return { tipo, tamanho: 14 }
    case 'substring': return { tipo, inicio: 1, tamanho: 10 }
    case 'cast':      return { tipo, tipo_sql: '' }
    case 'sql':       return { tipo, expressao: '' }
    default:          return { tipo }
  }
}

/** Resumo humano da transformação (passo Revisão / tooltip). */
export function transformResumo(t: Transform | null): string {
  if (!t) return '—'
  switch (t.tipo) {
    case 'pad_condicional':
      return `zeros à esquerda por [${t.campo_condicao || '?'}]: ` +
        (t.casos ?? []).map(c => `${c.valor || '?'} → ${c.tamanho}`).join(', ')
    case 'pad_fixo':  return `zeros à esquerda (${t.tamanho})`
    case 'trim':      return 'trim'
    case 'upper':     return 'maiúsculas'
    case 'lower':     return 'minúsculas'
    case 'substring': return `substring(${t.inicio}, ${t.tamanho})`
    case 'cast':      return `cast → ${t.tipo_sql || '?'}`
    case 'sql':       return `SQL: ${(t.expressao || '').slice(0, 60)}`
  }
}

// ── Cópias / execuções (respostas dos endpoints /copias*) ────────────────────

export interface UltimaExec {
  id: number
  status: string
  rows_copied: number
  rows_total: number | null
  criado_em: string | null
}

export interface CopiaJob {
  id: number
  nome: string
  src_conn_id: string; src_database: string; src_schema: string; src_table: string
  dst_conn_id: string; dst_database: string; dst_schema: string; dst_table: string
  criar_tabela: boolean
  truncar_antes: boolean
  particao_coluna: string | null
  streams: number
  batch_size: number
  criado_por?: string | null
  criado_em?: string | null
  atualizado_em?: string | null
  ultima_exec: UltimaExec | null
}

// GET /copias/{id} — detalhe (colunas_json parseado em `colunas`)
export interface CopiaDetalhe extends Omit<CopiaJob, 'ultima_exec'> {
  src_filtro: string | null
  colunas: ColunaMapeada[]
  select_sql: string | null
  count_sql: string | null
  dst_columns: string[]
  ativo: boolean
}

export interface ExecRange {
  range_index: number
  valor_ini: string | null
  valor_fim: string | null
  status: string
  rows_copied: number
  erro_msg: string | null
  iniciado_em: string | null
  concluido_em: string | null
}

// GET /copias/exec/{exec_id} — progresso (polling)
export interface ExecProgresso {
  id: number
  copy_job_id: number | null
  nome: string | null
  status: string
  rows_total: number | null
  rows_copied: number
  engine: string | null
  streams: number | null
  erro_msg: string | null
  iniciado_em: string | null
  concluido_em: string | null
  dag_run_id: string | null
  rate_rows_s: number | null
  eta_s: number | null
  ranges: ExecRange[]
}

// GET /copias/{id}/execucoes — linha do histórico
export interface ExecHistorico {
  id: number
  dag_run_id: string | null
  status: string
  rows_total: number | null
  rows_copied: number
  streams: number | null
  engine: string | null
  erro_msg: string | null
  matricula: string | null
  iniciado_em: string | null
  concluido_em: string | null
  criado_em: string | null
  duracao_s: number | null
}

// ── Status de execução ────────────────────────────────────────────────────────

// Status "vivos" — mantêm o polling de progresso ligado (refetchInterval 2500).
export const EXEC_ATIVA = new Set(['pendente', 'executando', 'cancelando'])

export const STATUS_LABELS: Record<string, string> = {
  pendente:   'Pendente',
  executando: 'Executando',
  cancelando: 'Cancelando',
  concluido:  'Concluído',
  erro:       'Erro',
  cancelado:  'Cancelado',
}

// Chave de cor do <Badge value=…> (mapa do componente ui/Badge) por status.
export const STATUS_BADGE: Record<string, string> = {
  pendente:   'PENDING',
  executando: 'RUNNING',
  cancelando: 'warning',
  concluido:  'success',
  erro:       'error',
  cancelado:  'neutral',
}

// ── Formatação pt-BR ─────────────────────────────────────────────────────────

const NF_PTBR = new Intl.NumberFormat('pt-BR')

/** Inteiro com separador de milhar pt-BR (1234567 → "1.234.567"). */
export function fmtRows(n?: number | null): string {
  if (n == null) return '—'
  return NF_PTBR.format(n)
}

/** Duração legível ("2h 5m 3s" / "4m 12s" / "37s"). */
export function fmtDuracao(s?: number | null): string {
  if (s == null || s < 0) return '—'
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = Math.floor(s % 60)
  if (h > 0) return `${h}h ${m}m ${sec}s`
  return m > 0 ? `${m}m ${sec}s` : `${sec}s`
}

/** ETA no formato mm:ss (minutos podem passar de 59 — ex.: "75:08"). */
export function fmtEta(s?: number | null): string {
  if (s == null || s < 0) return '—'
  const m = Math.floor(s / 60)
  const sec = Math.floor(s % 60)
  return `${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`
}

/** Descrição do intervalo de uma faixa (stream) para a tabela de progresso. */
export function faixaIntervalo(r: ExecRange): string {
  if (r.range_index === -1) return 'valores nulos (IS NULL)'
  if (r.valor_ini == null && r.valor_fim == null) return 'faixa única (sem partição)'
  return `${r.valor_ini ?? '—'} → ${r.valor_fim ?? '—'}`
}
