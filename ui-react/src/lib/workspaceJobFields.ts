/** Adaptador local: formulários compartilhados nunca gravam o cadastro ativo. */
import { paramsFromApi, paramsToApi, type JobParamApi } from './dsParams'
import { encryptedParameter, object, text, type JsonObject, type WorkspaceNode } from './workspace'
import type { JobFieldsType, JobTypeFieldsValue } from '../components/etapas/JobTypeFields'

const SHARED_TYPES: readonly string[] = ['datastage', 'shell', 'python', 'storedproc', 'http']
export function hasSharedJobFields(type: string): type is JobFieldsType { return SHARED_TYPES.includes(type) }
export function jobParameterRows(node: WorkspaceNode): JsonObject[] {
 return Array.isArray(node.configuration.etl_pipeline_job_param) ? node.configuration.etl_pipeline_job_param.map(object) : []
}
export function jsonField(value: unknown): JsonObject {
 if (typeof value === 'string') { try { return object(JSON.parse(value)) } catch { return {} } }
 return object(value)
}
export function workspaceJobFields(node: WorkspaceNode): JobTypeFieldsValue {
 if (!hasSharedJobFields(node.type)) throw new Error('Este componente usa um formulário especializado.')
 const job = object(node.configuration.legacyJob)
 const params = jobParameterRows(node).flatMap((row, index) => encryptedParameter(row) ? [] : [{
  ...paramsFromApi([row as unknown as JobParamApi])[0], id: `workspace-param-${index}`,
 }])
 return {
  job_type: node.type, job_command: text(job.job_command), ssh_conn_id: text(job.ssh_conn_id),
  verbose_log: job.verbose_log === true || job.verbose_log === 1,
  mssql_conn_id: text(job.mssql_conn_id), mssql_database: text(job.mssql_database), params,
  param_vinculos: jsonField(job.param_vinculos_json) as Record<string, string>,
 }
}
export type WorkspaceJobPatch = Partial<Omit<JobTypeFieldsValue, 'python' | 'job_type'>> & { python_json?: string | null }
export function applyWorkspaceJobPatch(node: WorkspaceNode, patch: WorkspaceJobPatch): WorkspaceNode {
 const job = { ...object(node.configuration.legacyJob) }
 const configuration: JsonObject = { ...node.configuration, legacyJob: job }
 for (const key of ['job_command','ssh_conn_id','verbose_log','mssql_conn_id','mssql_database','python_json'] as const) {
  if (key in patch) job[key] = patch[key]
 }
 if ('python_json' in patch) {
  const previous = jsonField(object(node.configuration.legacyJob).python_json)
  const known = new Set(['modo','script_path','destino_dir','arquivo','codigo','interpretador'])
  const extras = Object.fromEntries(Object.entries(previous).filter(([key]) => !known.has(key)))
  if (patch.python_json === null && Object.keys(extras).length) throw new Error('Esta configuração Python contém campos adicionais. Preserve um modo com configuração para não descartá-los.')
  job.python_json = patch.python_json === null ? null : JSON.stringify({ ...extras, ...jsonField(patch.python_json) })
 }
 if ('param_vinculos' in patch) job.param_vinculos_json = JSON.stringify(patch.param_vinculos ?? {})
 if (patch.params) {
  const rows = jobParameterRows(node)
  const protectedRows = rows.filter(encryptedParameter)
  const protectedNames = new Set(protectedRows.map(row => text(row.param_name)))
  if (patch.params.some(param => param.param_type.toLowerCase() === 'encrypted' || protectedNames.has(param.param_name.trim()))) {
   throw new Error('Parâmetros protegidos devem continuar por referência, sem valores neste formulário.')
  }
  const next = patch.params.flatMap(param => {
   const converted = paramsToApi(node.type, [param])[0]
   if (!converted) return []
   const original = rows.find((row, index) => !encryptedParameter(row) && param.id === `workspace-param-${index}`)
   return [{ ...original, ...converted } as JsonObject]
  })
  // Referências protegidas conservam conteúdo e posição relativa no conjunto.
  rows.forEach((row, index) => { if (encryptedParameter(row)) next.splice(Math.min(index, next.length), 0, row) })
  configuration.etl_pipeline_job_param = next.map((row, index) => ({ ...row, param_order: index + 1 }))
 }
 return { ...node, configuration }
}
