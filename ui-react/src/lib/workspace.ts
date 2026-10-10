// Contrato F2 e operações puras: nenhuma chamada ao cadastro ativo.
export type JsonObject = Record<string, unknown>
export interface WorkspaceNode { id: string; type: string; configuration: JsonObject; [key: string]: unknown }
export interface WorkspaceEdge { source: string; target: string; branch?: unknown; [key: string]: unknown }
export interface WorkspaceDefinition { schemaVersion: number; identity: { pipelineName: string; displayName?: string | null; [key: string]: unknown }; metadata?: JsonObject | null; schedule?: unknown; parameters?: unknown; nodes: WorkspaceNode[]; edges: WorkspaceEdge[]; [key: string]: unknown }
export interface WorkspaceLayout { schemaVersion: number; nodes: Record<string, { x: number; y: number; [key: string]: unknown }>; [key: string]: unknown }
export interface WorkspaceLease { holderUser: string; fence: number; expiresAt: string; heldBySession: boolean }
export interface WorkspaceDraft { draftId: string; pipelineName: string; baseVersionId: string | null; definition: WorkspaceDefinition; layout: WorkspaceLayout; revision: number; state: string; createdBy: string; responsible: string; createdAt: string; updatedAt: string; readOnlyReasons: string[]; lease: WorkspaceLease | null }
export interface WorkspaceContext { pipelineName: string; draftsAvailable: boolean; environmentLabel?: string; summary?: JsonObject; published: { definition: WorkspaceDefinition; layout: WorkspaceLayout; readOnlyReasons: string[] } | null; draft: WorkspaceDraft | null }
export interface WorkspaceCapabilities { schemaVersion: number; enabled: boolean; knownNodeTypes: string[]; actions: { consultDefinition: boolean; consultStages: boolean; consultLogs: boolean; consultVersions?: boolean; editDraft: boolean; administer: boolean; publish: boolean; execute: boolean; reprocess?: boolean; pauseStages?: boolean; contextualNavigation?: boolean } }
export type WorkspaceExperience = 'desenvolvimento' | 'consulta' | 'sustentacao'
export function object(value: unknown): JsonObject { return value !== null && typeof value === 'object' && !Array.isArray(value) ? value as JsonObject : {} }
export function text(value: unknown): string { return typeof value === 'string' ? value : '' }
export function workspacePath(name: string, tab = 'visao-geral', experience: WorkspaceExperience = 'consulta'): string { return `/pipelines/${encodeURIComponent(name)}/${tab==='etapas'?'fluxo':tab}?experiencia=${experience}` }
export function technicalSuggestion(name: string): string { return name.normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/[^a-zA-Z0-9_]+/g, '_').replace(/^_+|_+$/g, '').toLowerCase().slice(0, 200) }
export function cloneFlow<T>(value: T): T { return structuredClone(value) }
export function patchLegacy(node: WorkspaceNode, key: string, value: unknown): WorkspaceNode {
 return { ...node, configuration: { ...node.configuration, legacyJob: { ...object(node.configuration.legacyJob), [key]: value } } }
}
export function nodeLabel(node: WorkspaceNode): string { return text(node.displayName) || node.id }
export function renameWorkspaceNode(definition: WorkspaceDefinition, layout: WorkspaceLayout, id: string, nextId: string): { definition: WorkspaceDefinition; layout: WorkspaceLayout } {
 const node = definition.nodes.find(n => n.id === id)
 if (!node || !/^[A-Za-z0-9_.-]+$/.test(nextId) || nextId.length > 200 || definition.nodes.some(n => n.id !== id && n.id.toLowerCase() === nextId.toLowerCase())) throw new Error('Informe um identificador único, sem espaços.')
 if (Array.isArray(node.configuration.etl_pipeline_job_param) && node.configuration.etl_pipeline_job_param.some(r => encryptedParameter(object(r)))) throw new Error('Esta etapa possui parâmetros protegidos vinculados ao identificador. Preserve o identificador até migrar as referências na origem.')
 const replaceList = (v: unknown) => Array.isArray(v) ? v.map(x => x === id ? nextId : x) : v
 const nodes = definition.nodes.map(n => {
  const configuration = cloneFlow(n.configuration); const job = object(configuration.legacyJob)
  if (n.id === id) { job.job_name = nextId; for (const table of ['etl_pipeline_job_param','etl_valida_arquivo_no','etl_valida_arquivo_config']) if (Array.isArray(configuration[table])) configuration[table] = configuration[table].map(r => ({...object(r),[table === 'etl_pipeline_job_param' ? 'job_name' : 'task_id']:nextId})) }
  if (typeof job.depends_on_jobs === 'string') job.depends_on_jobs = job.depends_on_jobs.split(',').map(v => v.trim() === id ? nextId : v).join(',')
  if (typeof job.condition_json === 'string') { try { const condition = object(JSON.parse(job.condition_json)); for(const key of ['job_name','source_job']) if(typeof condition[key]==='string' && text(condition[key]).toLowerCase()===id.toLowerCase()) condition[key]=nextId; for (const key of ['ramo_verdadeiro','ramo_falso','ramo_senao']) if (key in condition) condition[key] = replaceList(condition[key]); if (Array.isArray(condition.casos)) condition.casos = condition.casos.map(c => ({...object(c),ramo:replaceList(object(c).ramo)})); job.condition_json = JSON.stringify(condition) } catch { throw new Error('Corrija a configuração da decisão antes de renomear uma etapa.') } }
  if(Array.isArray(configuration.etl_valida_arquivo_config)) configuration.etl_valida_arquivo_config=configuration.etl_valida_arquivo_config.map(r=>{const row=object(r);return typeof row.alvo==='string'&&text(row.alvo).toLowerCase()===id.toLowerCase()?{...row,alvo:nextId}:row})
  configuration.legacyJob = job
  return {...n,id:n.id === id ? nextId : n.id,configuration}
 })
 const positions = {...layout.nodes}; if (positions[id]) { positions[nextId] = positions[id]; if (nextId !== id) delete positions[id] }
 return {definition:{...definition,nodes,edges:definition.edges.map(e=>({...e,source:e.source===id?nextId:e.source,target:e.target===id?nextId:e.target}))},layout:{...layout,nodes:positions}}
}
export function definitionLabel(definition: WorkspaceDefinition): string { return text(definition.identity.displayName) || text(object(definition.metadata).displayName) || definition.identity.pipelineName }
export function pipelineMetadata(definition: WorkspaceDefinition): JsonObject { return object(object(definition.metadata).legacyPipeline) }
export function pipelineParameters(definition: WorkspaceDefinition): JsonObject[] {
 const rows = object(object(definition.metadata).legacyTables).etl_pipeline_param
 return Array.isArray(rows) ? rows.map(object) : Array.isArray(definition.parameters) ? definition.parameters.map(object) : []
}
export function setPipelineParameters(definition: WorkspaceDefinition, rows: JsonObject[]): WorkspaceDefinition {
 if (Array.isArray(definition.parameters)) return { ...definition, parameters: rows }
 return { ...definition, metadata: { ...object(definition.metadata), legacyTables: { ...object(object(definition.metadata).legacyTables), etl_pipeline_param: rows } } }
}
export function encryptedParameter(row: JsonObject): boolean { return text(row.param_type).toLowerCase() === 'encrypted' || row.secretReference !== undefined }
export function removeWorkspaceNode(definition: WorkspaceDefinition, layout: WorkspaceLayout, id: string): { definition: WorkspaceDefinition; layout: WorkspaceLayout } {
 const positions = { ...layout.nodes }; delete positions[id]
 return { definition: { ...definition, nodes: definition.nodes.filter(n => n.id !== id), edges: definition.edges.filter(e => e.source !== id && e.target !== id) }, layout: { ...layout, nodes: positions } }
}
export function connectWorkspace(definition: WorkspaceDefinition, source: string, target: string): WorkspaceDefinition {
 if (source === target || !definition.nodes.some(n => n.id === source) || !definition.nodes.some(n => n.id === target)) throw new Error('Selecione duas etapas diferentes')
 if (definition.edges.some(e => e.source === source && e.target === target)) return definition
 const queue = [target]; const seen = new Set<string>()
 while (queue.length) { const id = queue.pop()!; if (id === source) throw new Error('Esta dependência criaria um ciclo'); if (!seen.has(id)) { seen.add(id); queue.push(...definition.edges.filter(e => e.source === id).map(e => e.target)) } }
 return { ...definition, edges: [...definition.edges, { source, target }] }
}
export function initialWorkspace(name: string, displayName: string, project: string, domain: string, description: string): { definition: WorkspaceDefinition; layout: WorkspaceLayout } {
 return { definition: { schemaVersion: 1, identity: { pipelineName: name, displayName }, metadata: { legacyPipeline: { pipeline_name: name, project_name: project || null, domain: domain || null, descricao: description || null, schedule_type: 'on_demand', active: 1 } }, nodes: [], edges: [] }, layout: { schemaVersion: 1, nodes: {} } }
}

export interface WorkspaceDiagnostic { nodeId: string | null; field: string; code: string; message: string }
export interface WorkspaceValidation { revision: number; valid: boolean; diagnostics: WorkspaceDiagnostic[] }
export interface WorkspacePublication { operationId: string; draftId: string; versionId: string; pipelineName: string; revision: number; state: string; attempts: number; projected: boolean; error: string | null; updatedAt: string }
export interface WorkspaceVersion { versionId: string; number: number; origin: string; contentHash: string; definition: WorkspaceDefinition; layout: WorkspaceLayout; createdBy: string; createdAt: string; state: string }
export function compareWorkspaceVersions(before: unknown, after: unknown, path = ''): { path: string; before: unknown; after: unknown }[] {
 if (JSON.stringify(before) === JSON.stringify(after)) return []
 if (before !== null && after !== null && typeof before === 'object' && typeof after === 'object') {
  const left = before as Record<string, unknown>, right = after as Record<string, unknown>
  return [...new Set([...Object.keys(left), ...Object.keys(right)])].sort().flatMap(key => compareWorkspaceVersions(left[key], right[key], `${path}/${key}`))
 }
 return [{ path: path || '/', before, after }]
}
