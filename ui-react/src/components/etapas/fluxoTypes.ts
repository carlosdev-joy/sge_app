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

// Config do nó de E-mail (round-trip com /fluxo no campo `email`).
// Vive na mesma coluna do nó de notificação no banco (notify_json) — o tipo do
// job é quem diz qual das duas é.
export interface EmailNoConfig {
  assunto: string
  corpo: string
  html: boolean
  /** Lista própria do nó. Pode ser vazia se `incluir_pipeline` estiver ligado. */
  destinatarios: string[]
  /** Soma a lista cadastrada no fluxo (Propriedades do fluxo › E-mail). */
  incluir_pipeline: boolean
  /** Pasta entre as permitidas no Admin + nome livre (pode ainda não existir). */
  anexo: { raiz: string; nome: string } | null
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

// ── Nó E-mail (aviso por e-mail pelo servidor do DataStage) ─────────────────
// Config default de um nó recém-criado: herda a lista do fluxo (é o que quem
// cadastrou a lista espera) e já traz um assunto que faz sentido sozinho.
export function defaultEmailNo(): EmailNoConfig {
  return {
    assunto: '[Orquestra] {pipeline} — {status}',
    corpo: 'O fluxo {pipeline} terminou em {data}.',
    html: false,
    destinatarios: [],
    incluir_pipeline: true,
    anexo: null,
  }
}

// Lê a config de e-mail do payload da API (tolerante a null/parcial).
export function toEmailNoConfig(raw: EmailNoConfig | null | undefined): EmailNoConfig {
  if (!raw || typeof raw !== 'object') return defaultEmailNo()
  const anexo = raw.anexo
  const raiz = anexo && typeof anexo === 'object' ? `${anexo.raiz ?? ''}`.trim() : ''
  const nome = anexo && typeof anexo === 'object' ? `${anexo.nome ?? ''}`.trim() : ''
  return {
    assunto: typeof raw.assunto === 'string' ? raw.assunto : '',
    corpo: typeof raw.corpo === 'string' ? raw.corpo : '',
    html: raw.html === true,
    destinatarios: Array.isArray(raw.destinatarios) ? raw.destinatarios.map(d => `${d}`.trim()).filter(Boolean) : [],
    // Ausente = ligado, igual ao backend: um round-trip não pode desligar a
    // herança sozinho (o e-mail sairia para menos gente, em silêncio).
    incluir_pipeline: raw.incluir_pipeline !== false,
    anexo: raiz && nome ? { raiz, nome } : null,
  }
}

/** Placeholders que o operador do worker resolve (dags/utils/email_operator). */
export const EMAIL_PLACEHOLDERS = ['pipeline', 'job', 'data', 'odate', 'linhas',
                                   'status', 'inicio', 'duracao', 'execution_id']

// Resumo curto p/ o card: quem recebe, que é o que se quer ver sem abrir.
export function emailNoLabel(cfg: EmailNoConfig): string {
  const n = cfg.destinatarios.length
  if (n === 0) return cfg.incluir_pipeline ? 'destinatários do fluxo' : 'sem destinatário'
  const extra = cfg.incluir_pipeline ? ' + fluxo' : ''
  return n === 1 ? `${cfg.destinatarios[0]}${extra}` : `${n} destinatários${extra}`
}

// Régua local do nó — espelha _validate_email do backend (api/routers/jobs.py).
// `raizesPermitidas` vem do Admin (GET /email/status); vazia = nenhuma pasta
// liberada, e aí qualquer anexo é recusado.
export function errosDoEmailNo(cfg: EmailNoConfig, raizesPermitidas: string[]): string[] {
  const erros: string[] = []
  const assunto = (cfg.assunto || '').trim()
  if (!assunto) erros.push('Informe o assunto')
  else if (assunto.split(/\r|\n/).length > 1) erros.push('O assunto não pode ter quebra de linha')
  else if (assunto.length > 500) erros.push('Assunto com mais de 500 caracteres')
  if (!(cfg.corpo || '').trim()) erros.push('Informe o corpo da mensagem')
  else if (cfg.corpo.length > 20000) erros.push('Corpo com mais de 20.000 caracteres')
  const EMAIL_RE = /^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$/
  for (const d of cfg.destinatarios) {
    if (!EMAIL_RE.test(d)) erros.push(`Destinatário inválido: ${d}`)
  }
  if (cfg.destinatarios.length > 50) erros.push('No máximo 50 destinatários')
  if (!cfg.destinatarios.length && !cfg.incluir_pipeline) {
    erros.push('Informe um destinatário ou marque "incluir os destinatários do fluxo"')
  }
  if (cfg.anexo) {
    // `raizesPermitidas` vazio pode ser "Admin sem pasta liberada" OU falha ao
    // consultar o status: quem chama decide (o editor só cobra a pasta quando
    // a consulta respondeu), senão um erro de rede travaria o save do fluxo.
    if (raizesPermitidas.length && !raizesPermitidas.includes(cfg.anexo.raiz)) {
      erros.push('A pasta do anexo não está entre as permitidas no Admin › E-mail')
    }
    if (!cfg.anexo.raiz.trim()) erros.push('Escolha a pasta do anexo')
    // Nome vazio some em silêncio na serialização (anexo vira null) — o
    // usuário marcaria "Anexar", salvaria, e o anexo não existiria.
    if (!cfg.anexo.nome.trim()) erros.push('Informe o nome do arquivo do anexo')
    else if (/[/\\\r\n]/.test(cfg.anexo.nome) || cfg.anexo.nome === '..' || cfg.anexo.nome === '.') {
      erros.push('O nome do anexo não pode ter barra, "." ou ".."')
    } else if (cfg.anexo.nome.length > 200) {
      erros.push('Nome do anexo com mais de 200 caracteres')
    }
  }
  return erros
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
