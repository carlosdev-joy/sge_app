// Helpers de condição de Decisão para o canvas de fluxo. Espelham o modelo do
// PipelineFormModal (ConditionEntry/defaultCondition/operadores) para manter o
// editor do canvas idêntico ao do wizard. `conditionLabel` gera o resumo curto
// exibido dentro do losango da decisão.
import type { CasoSwitch, NodeCondition } from './DecisaoNode'

export const COND_OPERADORES = ['=', '<>', '>', '>=', '<', '<='] as const

export function defaultCondition(): NodeCondition {
  return {
    tipo: 'contagem', operador: '>', valor: '',
    tabela: '', database: '', sql: '', mssql_conn_id: '',
    job_name: '', child_job: '',
    source_job: '', comparacao: 'texto',
    on_error: 'falhar',
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
  // SWITCH (N-way): presença de `casos` (lista) muda o modo — normaliza cada
  // caso com valor string e ramo lista; on_error válido = falhar|senao.
  const isSwitch = Array.isArray(raw.casos)
  const casos: CasoSwitch[] | undefined = isSwitch
    ? (raw.casos as Record<string, unknown>[]).map((c) => ({
        nome: typeof c?.nome === 'string' ? c.nome : '',
        operador: typeof c?.operador === 'string' && c.operador ? c.operador : '>',
        valor: c?.valor != null ? String(c.valor) : '',
        ramo: Array.isArray(c?.ramo) ? (c.ramo as string[]) : [],
      }))
    : undefined
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
    // Sem on_error salvo (condição legada) exibe 'falhar' — é o default que o
    // backend carimba no próximo save; quem quiser manter o degrade legado
    // escolhe 'ramo_falso' explicitamente no painel. on_error_legado marca o
    // gap: a DAG publicada ainda degrada até salvar + republicar.
    on_error: isSwitch
      ? (raw.on_error === 'senao' ? 'senao' : 'falhar')
      : (raw.on_error === 'ramo_falso' ? 'ramo_falso' : 'falhar'),
    on_error_legado: !isSwitch && raw.on_error == null,
    ramo_verdadeiro: Array.isArray(raw.ramo_verdadeiro) ? (raw.ramo_verdadeiro as string[]) : [],
    ramo_falso: Array.isArray(raw.ramo_falso) ? (raw.ramo_falso as string[]) : [],
    ...(isSwitch
      ? { casos, ramo_senao: Array.isArray(raw.ramo_senao) ? (raw.ramo_senao as string[]) : [] }
      : {}),
  }
}

// Resumo curto exibido no losango (ex.: "contagem > 0", "query MAX(...) >= 1").
export function conditionLabel(c: NodeCondition | null | undefined): string {
  if (!c) return 'decisão'
  if (Array.isArray(c.casos)) {
    const fonte =
      c.tipo === 'query' ? 'query'
        : c.tipo === 'linhas_job' ? `linhas ${(c.job_name || '').trim() || '?'}`
        : c.tipo === 'valor_sql' ? `valor de ${(c.source_job || '').trim() || '?'}`
        : `contagem${(c.tabela || '').trim() ? ` ${c.tabela!.split('.').pop()}` : ''}`
    return `switch ${fonte} · ${c.casos.length} caso${c.casos.length === 1 ? '' : 's'}`
  }
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
