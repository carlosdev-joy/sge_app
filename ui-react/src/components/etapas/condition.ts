// Helpers de condição de Decisão para o canvas de fluxo. Espelham o modelo do
// PipelineFormModal (ConditionEntry/defaultCondition/operadores) para manter o
// editor do canvas idêntico ao do wizard. `conditionLabel` gera o resumo curto
// exibido dentro do losango da decisão.
import type { NodeCondition } from './DecisaoNode'

export const COND_OPERADORES = ['=', '<>', '>', '>=', '<', '<='] as const

export function defaultCondition(): NodeCondition {
  return {
    tipo: 'contagem', operador: '>', valor: '',
    tabela: '', database: '', sql: '', mssql_conn_id: '',
    job_name: '', child_job: '',
    source_job: '', comparacao: 'texto',
    ramo_verdadeiro: [], ramo_falso: [],
  }
}

// Normaliza um objeto de condição vindo da API (campos podem faltar) num
// NodeCondition completo, com `valor` sempre string.
export function toNodeCondition(raw: Record<string, unknown> | null | undefined): NodeCondition {
  const base = defaultCondition()
  if (!raw) return base
  const tipo: NodeCondition['tipo'] =
    raw.tipo === 'query' ? 'query'
      : raw.tipo === 'linhas_job' ? 'linhas_job'
      : raw.tipo === 'valor_sql' ? 'valor_sql'
      : 'contagem'
  const comparacao: NodeCondition['comparacao'] =
    raw.comparacao === 'data' ? 'data' : raw.comparacao === 'numero' ? 'numero' : 'texto'
  return {
    ...base,
    ...raw,
    tipo,
    operador: typeof raw.operador === 'string' && raw.operador ? raw.operador : base.operador,
    valor: raw.valor != null ? String(raw.valor) : '',
    job_name: typeof raw.job_name === 'string' ? raw.job_name : '',
    child_job: typeof raw.child_job === 'string' ? raw.child_job : '',
    source_job: typeof raw.source_job === 'string' ? raw.source_job : '',
    comparacao,
    ramo_verdadeiro: Array.isArray(raw.ramo_verdadeiro) ? (raw.ramo_verdadeiro as string[]) : [],
    ramo_falso: Array.isArray(raw.ramo_falso) ? (raw.ramo_falso as string[]) : [],
  }
}

// Resumo curto exibido no losango (ex.: "contagem > 0", "query MAX(...) >= 1").
export function conditionLabel(c: NodeCondition | null | undefined): string {
  if (!c) return 'decisão'
  const op = c.operador || '?'
  const val = (c.valor ?? '').toString().trim() || '?'
  if (c.tipo === 'query') {
    const sql = (c.sql || '').replace(/\s+/g, ' ').trim()
    const trecho = sql ? (sql.length > 24 ? sql.slice(0, 24) + '…' : sql) : 'query'
    return `${trecho} ${op} ${val}`
  }
  if (c.tipo === 'linhas_job') {
    const job = (c.job_name || '').trim()
    const child = (c.child_job || '').trim()
    const alvo = child ? (job ? `${job}›${child}` : child) : (job || '?')
    return `linhas ${alvo} ${op} ${val}`
  }
  if (c.tipo === 'valor_sql') {
    const src = (c.source_job || '').trim() || '?'
    return `valor de ${src} ${op} ${val}`
  }
  const tab = (c.tabela || '').trim()
  const alvo = tab ? tab.split('.').pop() : 'contagem'
  return `contagem ${op} ${val}${tab ? ` · ${alvo}` : ''}`
}
