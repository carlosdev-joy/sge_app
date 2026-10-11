// Destinos do Pipeline e compatibilidade das rotas anteriores. Sem imports:
// workspace.ts e workspaceNavigation.ts dependem deste módulo.
export type WorkspaceDestination = 'visao-geral' | 'montagem' | 'execucao' | 'configuracao' | 'versoes'
export const WORKSPACE_DESTINATIONS: readonly (readonly [WorkspaceDestination, string])[] = [['visao-geral', 'Visão geral'], ['montagem', 'Montagem'], ['execucao', 'Execução'], ['configuracao', 'Configuração'], ['versoes', 'Versões']]

export type ConfigurationGroup = 'identificacao' | 'agenda' | 'parametros' | 'politicas' | 'notificacoes' | 'documentacao'
export const CONFIGURATION_GROUPS: readonly (readonly [ConfigurationGroup, string, string])[] = [
 ['identificacao', 'Identificação', 'Finalidade, projeto, domínio, tags, criticidade e destino.'],
 ['agenda', 'Agenda e dependências', 'Agendamento, calendário, ODATE e pipelines predecessores. Ligações entre etapas ficam na Montagem.'],
 ['parametros', 'Parâmetros', 'Defaults compartilhados pelas etapas e referências protegidas.'],
 ['politicas', 'Políticas de execução', 'Ativação, SLA, concorrência, retries, pool e conclusão sem movimento.'],
 ['notificacoes', 'Notificações', 'Mensagens de início, conclusão e falha e destinatários de e-mail do fluxo.'],
 ['documentacao', 'Documentação', 'Runbook consultado pela sustentação.'],
]
export function configurationGroup(value: string | null | undefined): ConfigurationGroup {
 return CONFIGURATION_GROUPS.find(([id]) => id === value)?.[0] ?? 'identificacao'
}
export type ExecutionView = 'grafo' | 'tabela'
export function executionView(value: string | null | undefined): ExecutionView { return value === 'tabela' ? 'tabela' : 'grafo' }

// Rotas anteriores continuam válidas: o destino muda, a query e o hash ficam.
const ALIASES: Record<string, { to: WorkspaceDestination; set?: Record<string, string> }> = {
 fluxo: { to: 'montagem' }, etapas: { to: 'montagem' }, ferramentas: { to: 'montagem' },
 execucoes: { to: 'execucao' }, logs: { to: 'execucao', set: { vista: 'tabela' } },
 parametros: { to: 'configuracao', set: { grupo: 'parametros' } },
}
export function isWorkspaceDestination(value: string): value is WorkspaceDestination { return WORKSPACE_DESTINATIONS.some(([id]) => id === value) }
export function workspaceAlias(segment: string): { to: WorkspaceDestination; set: Record<string, string> } | null {
 const alias = Object.prototype.hasOwnProperty.call(ALIASES, segment) ? ALIASES[segment] : undefined
 return alias ? { to: alias.to, set: alias.set ?? {} } : null
}
// Destino canônico de um identificador de aba, inclusive dos antigos.
export function canonicalWorkspaceTab(tab: string): string { return workspaceAlias(tab)?.to ?? tab }
// Query canônica: preserva tudo e acrescenta o que o alias identifica (vista/grupo).
export function canonicalWorkspaceQuery(tab: string, search: URLSearchParams): URLSearchParams {
 const next = new URLSearchParams(search)
 for (const [key, value] of Object.entries(workspaceAlias(tab)?.set ?? {})) next.set(key, value)
 return next
}
export function workspaceAliasRedirect(name: string, segment: string, search: URLSearchParams, hash = ''): string | null {
 const alias = workspaceAlias(segment)
 if (!alias) return null
 return `/pipelines/${encodeURIComponent(name)}/${alias.to}?${canonicalWorkspaceQuery(segment, search)}${hash}`
}

// A sessão de edição (rascunho, alterações locais, posse e fence) pertence ao
// Pipeline aberto na mesma experiência e fonte. Trocar de destino dentro dela
// não desmonta o editor nem pede confirmação de saída.
function sessionSource(search: URLSearchParams): string {
 return search.get('experiencia') === 'desenvolvimento' ? 'rascunho' : search.get('fonte') ?? ''
}
export function sameWorkspaceSession(name: string, from: string | URL, to: string | URL): boolean {
 const current = new URL(from), next = new URL(to)
 if (current.origin !== next.origin) return false
 const prefix = `/pipelines/${encodeURIComponent(name)}/`
 if (!current.pathname.startsWith(prefix) || !next.pathname.startsWith(prefix)) return false
 const segment = next.pathname.slice(prefix.length).replace(/\/+$/, '')
 if (!isWorkspaceDestination(segment) && !workspaceAlias(segment)) return false
 return (current.searchParams.get('experiencia') ?? '') === (next.searchParams.get('experiencia') ?? '') && sessionSource(current.searchParams) === sessionSource(next.searchParams)
}

// Cabeçalho: rascunho, publicado e corrida nunca dividem o mesmo rótulo.
// `title` é o nome da definição executada (snapshot da versão da corrida).
export interface WorkspaceRunIdentity { runId: string | null; date: string | null; versionNumber: number | null; title?: string | null }
// Origem da identidade: só vale para o mesmo pipeline, data e corrida pedidos.
export function runIdentityOrigin(name: string, date: string, runId: string): string { return JSON.stringify([name, date, runId]) }

// Investigação da Execução. Etapa e tentativa são o contrato compartilhado
// entre gráfico, tabela e links (`etapa`, `tentativa`, com `run_id`); um log só
// abre se a etapa e a tentativa pertencem à corrida exibida. Sem tentativa
// explícita vale a corrente da etapa nessa corrida — nunca uma inventada.
export interface InvestigationStep { job_name: string; task_id: string | null; attempt: number | null; tentativas: { attempt: number | null }[] }
export function stageAttempts(step: InvestigationStep): number[] {
 const values = [...step.tentativas.map(t => t.attempt), step.attempt].filter((v): v is number => typeof v === 'number' && Number.isInteger(v) && v > 0)
 return [...new Set(values)].sort((a, b) => a - b)
}
export function parseAttempt(value: string | null | undefined): number | null {
 const number = Number(value); return value && Number.isInteger(number) && number > 0 ? number : null
}
export type InvestigationIssue = 'etapa' | 'tentativa' | 'corrida' | 'sem-tentativa' | null
export function executionInvestigation<S extends InvestigationStep>(steps: S[] | undefined, stage: string, attempt: number | null, requestedRun: string, runIds: (string | null | undefined)[]): { step: S | null; attempt: number | null; open: boolean; issue: InvestigationIssue } {
 if (!stage || !steps) return { step: null, attempt: null, open: false, issue: null }
 const step = steps.find(row => row.task_id === stage || row.job_name === stage) ?? null
 if (!step) return { step: null, attempt: null, open: false, issue: 'etapa' }
 if (requestedRun && !runIds.includes(requestedRun)) return { step, attempt: null, open: false, issue: 'corrida' }
 const list = stageAttempts(step), chosen = attempt ?? step.attempt ?? list.at(-1) ?? null
 if (chosen === null) return { step, attempt: null, open: false, issue: 'sem-tentativa' }
 if (!list.includes(chosen)) return { step, attempt: chosen, open: false, issue: 'tentativa' }
 return { step, attempt: chosen, open: !!step.task_id, issue: null }
}
export function workspaceHeaderContext(tab: string, draft: { revision: number } | null, published: boolean, run: WorkspaceRunIdentity | null): { label: string; tone: 'draft' | 'published' | 'run' } {
 if (canonicalWorkspaceTab(tab) === 'execucao') {
  if (!run?.runId) return { label: published ? 'Execução · configuração publicada · nenhuma corrida selecionada' : 'Execução · sem configuração publicada', tone: 'run' }
  const version = run.versionNumber != null ? `versão ${run.versionNumber}` : 'versão da corrida não vinculada'
  return { label: `Corrida ${run.runId}${run.date ? ` · ${run.date}` : ''} · ${version}`, tone: 'run' }
 }
 if (draft) return { label: `Rascunho · revisão ${draft.revision}`, tone: 'draft' }
 return { label: published ? 'Configuração publicada' : 'Rascunho', tone: published ? 'published' : 'draft' }
}
