// Tipos e helpers PUROS compartilhados entre o FluxoEditor e os painéis de
// propriedades (./paineis). Módulo sem estado/JSX — os dois lados importam
// daqui, sem import circular em runtime (nenhum painel importa o FluxoEditor).

// ── Tipos do payload da API (/fluxo) ────────────────────────────────────────
export interface Condition {
  ramo_verdadeiro?: string[]
  ramo_falso?: string[]
  // SWITCH (N-way): presença de `casos` muda o modo (ramos binários vazios).
  casos?: { nome?: string; operador?: string; valor?: unknown; ramo?: string[] }[]
  ramo_senao?: string[]
  [k: string]: unknown
}
// Config do nó de notificação (round-trip com /fluxo no campo `notify`).
export interface NotifyConfig {
  grupo_id: number | null
  template_id: number | null
  mensagem: string
}
// Config do nó SQL (round-trip com /fluxo no campo `sql`).
export interface SqlConfig {
  sql: string
  mssql_conn_id: string | null
  database: string | null
  // O que fazer se a consulta falhar: 'falhar' (task falha alto — default dos
  // saves novos) | 'nulo' (publica None em silêncio, comportamento legado).
  on_error: 'falhar' | 'nulo'
  // Derivado (NÃO persiste): JSON salvo sem on_error — DAG publicada ainda
  // degrada em silêncio até salvar + republicar. Alimenta o aviso no painel.
  on_error_legado?: boolean
}

// Catálogo de mensagens (Teams) — alimentam os Selects do nó de notificação.
export interface MsgGrupo { id: number; nome: string; descricao: string | null; has_webhook?: boolean; ativo?: boolean }
export interface MsgTemplate { id: number; grupo_id: number | null; nome: string; titulo: string | null }

// ── Notificação (Teams) ─────────────────────────────────────────────────────
// Config default de um nó de notificação recém-criado (grupo a escolher).
export function defaultNotify(): NotifyConfig {
  return { grupo_id: null, template_id: null, mensagem: '' }
}

// Lê a config de notificação do payload da API (tolerante a null/parcial).
export function toNotifyConfig(raw: NotifyConfig | null | undefined): NotifyConfig {
  if (!raw || typeof raw !== 'object') return defaultNotify()
  const gid = raw.grupo_id
  const tid = raw.template_id
  return {
    grupo_id: typeof gid === 'number' ? gid : (gid != null && `${gid}`.trim() ? Number(gid) : null),
    template_id: typeof tid === 'number' ? tid : (tid != null && `${tid}`.trim() ? Number(tid) : null),
    mensagem: typeof raw.mensagem === 'string' ? raw.mensagem : '',
  }
}

// Resumo curto p/ o card. Usa o nome do grupo quando disponível (gruposById),
// senão "Teams: #<id>"; sem grupo escolhido mostra "notificação".
export function notifyLabel(cfg: NotifyConfig, gruposById?: Map<number, string>): string {
  if (cfg.grupo_id == null) return 'notificação'
  const nome = gruposById?.get(cfg.grupo_id)
  return `Teams: ${nome ?? `#${cfg.grupo_id}`}`
}

// ── Nó SQL (consulta que retorna 1 valor, lido por uma Decisão a jusante) ─────
// Config default de um nó SQL recém-criado.
export function defaultSql(): SqlConfig {
  return { sql: '', mssql_conn_id: null, database: null, on_error: 'falhar' }
}

// Lê a config SQL do payload da API (tolerante a null/parcial).
export function toSqlConfig(raw: SqlConfig | null | undefined): SqlConfig {
  if (!raw || typeof raw !== 'object') return defaultSql()
  return {
    sql: typeof raw.sql === 'string' ? raw.sql : '',
    mssql_conn_id: raw.mssql_conn_id != null && `${raw.mssql_conn_id}`.trim() ? `${raw.mssql_conn_id}` : null,
    database: raw.database != null && `${raw.database}`.trim() ? `${raw.database}` : null,
    // Sem on_error salvo (nó legado) exibe 'falhar' — default carimbado no
    // próximo save; 'nulo' é a escolha explícita de manter o degrade legado.
    on_error: raw.on_error === 'nulo' ? 'nulo' : 'falhar',
    on_error_legado: raw.on_error == null,
  }
}

// Resumo curto p/ o card: "SQL: <banco>" quando há banco, senão "consulta".
export function sqlLabel(cfg: SqlConfig): string {
  const db = (cfg.database || '').trim()
  return db ? `SQL: ${db}` : 'consulta'
}
