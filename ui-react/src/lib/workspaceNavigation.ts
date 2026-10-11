import { object, text, type WorkspaceDefinition, type WorkspaceLayout } from './workspace'
import type { FluxoResp } from '../components/etapas/FluxoEditor'
import { canonicalWorkspaceQuery, canonicalWorkspaceTab } from './workspaceTabs'

// Apenas destinos locais conhecidos; query de origem nunca vira URL livre.
// Abas anteriores (fluxo, execucoes, logs, parametros...) resolvem para o destino atual.
export function contextualPath(name: string, tab: string, search: URLSearchParams, experience?: string, hash = ''): string {
 const next = canonicalWorkspaceQuery(tab, search)
 next.delete('pipeline'); next.delete('legado')
 if (experience) next.set('experiencia', experience)
 return `/pipelines/${encodeURIComponent(name)}/${canonicalWorkspaceTab(tab)}?${next}${hash.startsWith('#') ? hash : ''}`
}
// Volta à Malha de origem (`de=malha:NOME`) na lente de execução, com a data e
// a corrida da malha quando informadas. O destino é montado aqui, nunca lido
// da query (mesmo molde de linkDaCorrida e de pages/Fluxos).
export function malhaReturnPath(search: URLSearchParams): string | null {
 const origin = search.get('de') ?? ''
 const malha = origin.startsWith('malha:') ? origin.slice(6).trim() : ''
 if (!malha) return null
 const next = new URLSearchParams({ malha, modo: 'execucao' })
 const run = Number((search.get('corrida') ?? '').trim())
 if (Number.isInteger(run) && run > 0) next.set('corrida', String(run))
 const date = (search.get('data') ?? '').trim()
 if (date) next.set('data', date)
 return `/malha?${next}`
}
export function legacyWorkspacePath(kind: 'jobs' | 'fluxos', search: URLSearchParams, hash = ''): string | null {
 const name = search.get('pipeline')?.trim()
 if (!name || search.get('legado') === '1') return null
 const execution = kind === 'fluxos' && search.get('modo') === 'execucao'
 return contextualPath(name, execution ? 'execucao' : 'montagem', search, execution ? 'sustentacao' : 'desenvolvimento', hash)
}
function decoded(value: unknown): unknown {
 if (typeof value !== 'string') return value ?? null
 try { return JSON.parse(value) } catch { return null }
}
// O canvas operacional desenha o snapshot confirmado, nunca cadastro parcialmente projetado.
export function publishedExecutionFlow(definition: WorkspaceDefinition, layout: WorkspaceLayout): FluxoResp {
 const nodes = definition.nodes.map(node => {
  const job = object(node.configuration.legacyJob); const position = layout.nodes[node.id]
  return { ...job, job_name: node.id, job_type: node.type, job_command: text(job.job_command) || null,
   execution_order: Number(job.execution_order) || 1,
   depends_on_jobs: definition.edges.filter(e => e.target === node.id && !e.branch).map(e => e.source),
   condition: decoded(job.condition_json), sql_node: decoded(job.sql_json), notify: node.type === 'notificacao' ? decoded(job.notify_json) : null,
   email: node.type === 'email' ? decoded(job.notify_json) : null, aguarde: decoded(job.aguarde_json), python: decoded(job.python_json), valida_arquivo: Array.isArray(node.configuration.etl_valida_arquivo_no) && node.configuration.etl_valida_arquivo_no.length ? {...object(node.configuration.etl_valida_arquivo_no[0]),entradas:node.configuration.etl_valida_arquivo_config??[]} : decoded(job.valida_arquivo_json),
   params: node.configuration.etl_pipeline_job_param ?? [], layout_x: position?.x ?? null, layout_y: position?.y ?? null }
 })
 return { nodes } as FluxoResp
}
