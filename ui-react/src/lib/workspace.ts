// Contrato F2 e operações puras: nenhuma chamada ao cadastro ativo.
export type JsonObject = Record<string, unknown>
export interface WorkspaceNode { id: string; type: string; configuration: JsonObject; [key: string]: unknown }
export interface WorkspaceEdge { source: string; target: string; branch?: unknown; [key: string]: unknown }
export interface WorkspaceDefinition { schemaVersion: number; identity: { pipelineName: string; displayName?: string | null; [key: string]: unknown }; metadata?: JsonObject | null; schedule?: unknown; parameters?: unknown; nodes: WorkspaceNode[]; edges: WorkspaceEdge[]; [key: string]: unknown }
export interface WorkspaceLayout { schemaVersion: number; nodes: Record<string, { x: number; y: number; [key: string]: unknown }>; [key: string]: unknown }
export interface WorkspaceLease { holderUser: string; fence: number; expiresAt: string; heldBySession: boolean }
export interface WorkspaceDraft { draftId: string; pipelineName: string; baseVersionId: string | null; definition: WorkspaceDefinition; layout: WorkspaceLayout; revision: number; state: string; createdBy: string; responsible: string; createdAt: string; updatedAt: string; readOnlyReasons: string[]; lease: WorkspaceLease | null }
export interface WorkspaceContext { pipelineName: string; draftsAvailable: boolean; environmentLabel?: string; summary?: JsonObject; published: { definition: WorkspaceDefinition; layout: WorkspaceLayout; readOnlyReasons: string[] } | null; draft: WorkspaceDraft | null }
export interface WorkspaceCapabilities { schemaVersion: number; enabled: boolean; knownNodeTypes: string[]; actions: { consultDefinition: boolean; consultStages: boolean; consultLogs: boolean; editDraft: boolean; administer: boolean; publish: boolean; execute: boolean } }
export type WorkspaceExperience = 'desenvolvimento' | 'consulta' | 'sustentacao'
export function object(value: unknown): JsonObject { return value !== null && typeof value === 'object' && !Array.isArray(value) ? value as JsonObject : {} }
export function text(value: unknown): string { return typeof value === 'string' ? value : '' }
export function workspacePath(name: string, tab = 'visao-geral', experience: WorkspaceExperience = 'consulta'): string { return `/pipelines/${encodeURIComponent(name)}/${tab}?experiencia=${experience}` }
export function technicalSuggestion(name: string): string { return name.normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/[^a-zA-Z0-9_]+/g, '_').replace(/^_+|_+$/g, '').toLowerCase().slice(0, 200) }
export function cloneFlow<T>(value: T): T { return structuredClone(value) }
export function patchLegacy(node: WorkspaceNode, key: string, value: unknown): WorkspaceNode {
 return { ...node, configuration: { ...node.configuration, legacyJob: { ...object(node.configuration.legacyJob), [key]: value } } }
}
export function nodeLabel(node: WorkspaceNode): string { return text(node.displayName) || node.id }
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
 return { definition: { schemaVersion: 1, identity: { pipelineName: name, displayName }, metadata: { legacyPipeline: { pipeline_name: name, project_name: project || null, domain: domain || null, descricao: description || null } }, nodes: [], edges: [] }, layout: { schemaVersion: 1, nodes: {} } }
}
