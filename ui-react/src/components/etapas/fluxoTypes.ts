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

// Config do nó Aguarde (round-trip com /fluxo no campo `aguarde`).
export interface AguardeConfig {
  // 'todas_sucesso'    → só libera se todas as etapas ligadas derem certo
  // 'todas_terminarem' → libera quando todas terminarem, mesmo com falha
  //                      (caso da limpeza de arquivos compartilhados)
  politica: 'todas_sucesso' | 'todas_terminarem'
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

// ── Nó Aguarde (ponto de encontro entre pernas paralelas) ────────────────────
// Config default de um Aguarde recém-criado: o conservador. Ninguém herda
// "segue mesmo com falha" sem escolher.
export function defaultAguarde(): AguardeConfig {
  return { politica: 'todas_sucesso' }
}

// Lê a config do Aguarde do payload da API (tolerante a null/parcial). Espelha
// a normalização do backend: qualquer valor fora do domínio vira o default.
export function toAguardeConfig(raw: AguardeConfig | null | undefined): AguardeConfig {
  if (!raw || typeof raw !== 'object') return defaultAguarde()
  return {
    politica: raw.politica === 'todas_terminarem' ? 'todas_terminarem' : 'todas_sucesso',
  }
}

// Resumo curto p/ o card — a política precisa ser legível sem abrir o painel.
export function aguardeLabel(cfg: AguardeConfig): string {
  return cfg.politica === 'todas_terminarem' ? 'mesmo com falha' : 'todas com sucesso'
}

// Pontas soltas do fluxo que a ação "prender" ligaria num Aguarde: nós SEM
// nenhuma aresta de saída (normal ou de ramo — uma decisão só tem saídas de
// ramo e NÃO é ponta solta), que não sejam o próprio Aguarde, não estejam já
// ligados nele, e não estejam a jusante dele — ligar um descendente de volta
// fecharia um ciclo.
//
// Função PURA sobre (id, arestas) para poder ser testada sem React Flow.
export function pontasSoltas(
  aguardeId: string,
  nodeIds: string[],
  arestas: { source: string; target: string }[],
): string[] {
  const temSaida = new Set(arestas.map(e => e.source))
  const filhos = new Map<string, string[]>()
  for (const e of arestas) {
    filhos.set(e.source, [...(filhos.get(e.source) ?? []), e.target])
  }
  // Descendentes do Aguarde (BFS).
  const jusante = new Set<string>()
  const fila = [aguardeId]
  while (fila.length) {
    const cur = fila.shift() as string
    for (const f of filhos.get(cur) ?? []) {
      if (jusante.has(f)) continue
      jusante.add(f)
      fila.push(f)
    }
  }
  const jaLigados = new Set(arestas.filter(e => e.target === aguardeId).map(e => e.source))
  return nodeIds.filter(id =>
    id !== aguardeId && !jusante.has(id) && !jaLigados.has(id) && !temSaida.has(id))
}
