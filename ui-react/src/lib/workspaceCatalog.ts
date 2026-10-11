import { connectWorkspaceDecision } from './workspaceDecision'
/** Catálogo local: guarda identidades/extras e nunca transforma referência em valor. */
import { catalogoFromApi, catalogoToApi, type CatalogoApi, type CatalogoParam } from './pipelineCatalogo'
import { encryptedParameter, object, pipelineParameters, setPipelineParameters, text, type JsonObject, type WorkspaceDefinition } from './workspace'

export function workspaceCatalog(definition: WorkspaceDefinition): CatalogoParam[] {
 return catalogoFromApi(pipelineParameters(definition).filter(row => !encryptedParameter(row)) as unknown as CatalogoApi[])
  .map((row, index) => ({ ...row, id: `workspace-catalog-${index}` }))
}
export function applyWorkspaceCatalog(definition: WorkspaceDefinition, catalog: CatalogoParam[]): WorkspaceDefinition {
 const original = pipelineParameters(definition)
 const visible = original.filter(row => !encryptedParameter(row))
 const protectedRows = original.filter(encryptedParameter)
 const names = new Set(protectedRows.map(row => text(row.param_name).toLowerCase()))
 const rows = catalogoToApi(catalog).map((row, index) => {
  const key = row.param_name.trim().toLowerCase()
  if (names.has(key)) throw new Error('Cada parâmetro exige um nome único, incluindo os valores protegidos.')
  if (row.param_type.toLowerCase() === 'encrypted') throw new Error('Use o formulário de valor protegido.')
  names.add(key)
  const identity = catalog.filter(p => p.param_name.trim())[index].id
  const previous = visible.find((_, i) => identity === `workspace-catalog-${i}`)
  return { ...previous, ...row, pipeline_name: definition.identity.pipelineName } as JsonObject
 })
 original.forEach((row, index) => { if (encryptedParameter(row)) rows.splice(Math.min(index, rows.length), 0, row) })
 return setPipelineParameters(definition, rows.map((row, index) => ({ ...row, param_order: index + 1 })))
}
export function reorderWorkspaceExecution(definition: WorkspaceDefinition, ids: string[]): WorkspaceDefinition {
 if (ids.length !== definition.nodes.length || new Set(ids).size !== ids.length || ids.some(id => !definition.nodes.some(n => n.id === id))) throw new Error('A ordem deve conter cada etapa uma única vez.')
 // Ordem é o desempate executável; dependências continuam sendo a autoridade do grafo.
 const positions = new Map(ids.map((id, index) => [id, index + 1]))
 return { ...definition, nodes: definition.nodes.map(node => ({ ...node, configuration: { ...node.configuration, legacyJob: { ...object(node.configuration.legacyJob), execution_order: positions.get(node.id) } } })) }
}

export interface WorkspaceImportRow { name: string; type: string; command: string; parent: string; branch: string }
export function importWorkspaceRows(definition: WorkspaceDefinition, rows: WorkspaceImportRow[]): WorkspaceDefinition {
 const types = new Set(['datastage','sql','python','shell','storedproc','http','decisao','aguarde','notificacao','email','valida_arquivo'])
 if (!rows.length || definition.nodes.length + rows.length > 500) throw new Error('Informe até 500 etapas no total.')
 const names = new Set(definition.nodes.map(node => node.id.toLowerCase()))
 const nodes = rows.map((row,index) => {
  const name = row.name.trim()
  if (!/^[A-Za-z0-9_.-]+$/.test(name) || name.length>200 || names.has(name.toLowerCase())) throw new Error('Cada etapa exige identificador único, sem espaços.')
  if (!types.has(row.type)) throw new Error('Selecione um tipo de componente válido.')
  names.add(name.toLowerCase())
  return { id:name, type:row.type, configuration:{legacyJob:{pipeline_name:definition.identity.pipelineName,job_name:name,job_type:row.type,job_command:row.command||null,execution_order:definition.nodes.length+index+1},etl_pipeline_job_param:[],...(object(definition.metadata).workspaceLineageVersion===1?{etl_job_lineage:[]}: {})} }
 })
 let next:WorkspaceDefinition={...definition,nodes:[...definition.nodes,...nodes]}
 for (const row of rows) if (row.parent) next=connectWorkspaceDecision(next,row.parent,row.name.trim(),row.branch||undefined)
 return next
}


export function workspacePredecessors(definition:WorkspaceDefinition):string[] {
 const tables=object(object(definition.metadata).legacyTables)
 const rows=Array.isArray(tables.etl_pipeline_dependencia)?tables.etl_pipeline_dependencia.map(object):[]
 return [...new Set([...rows.filter(row=>text(row.tipo)==='PIPELINE').map(row=>text(row.depende_de)),...text(object(object(definition.metadata).legacyPipeline).depends_on).split(',').map(name=>name.trim()).filter(Boolean)])]
}
export function setWorkspacePredecessors(definition:WorkspaceDefinition,names:string[]):WorkspaceDefinition {
 const metadata=object(definition.metadata);const tables=object(metadata.legacyTables)
 const previous=Array.isArray(tables.etl_pipeline_dependencia)?tables.etl_pipeline_dependencia.map(object):[]
 const selected=new Set(names.map(name=>name.toLowerCase()))
 if(selected.size!==names.length||names.some(name=>!name||name.toLowerCase()===definition.identity.pipelineName.toLowerCase()))throw new Error('Selecione predecessores distintos do próprio pipeline.')
 if(previous.some(row=>row.origem_no!=null&&!selected.has(text(row.depende_de).toLowerCase())))throw new Error('Dependências compiladas devem ser editadas pela malha dona.')
 const rows=previous.filter(row=>text(row.tipo)!=='PIPELINE'||selected.has(text(row.depende_de).toLowerCase()))
 for(const name of names)if(!rows.some(row=>text(row.tipo)==='PIPELINE'&&text(row.depende_de).toLowerCase()===name.toLowerCase()))rows.push({pipeline_name:definition.identity.pipelineName,depende_de:name,tipo:'PIPELINE',job_origem:null,job_destino:null})
 return {...definition,metadata:{...metadata,legacyTables:{...tables,etl_pipeline_dependencia:rows},legacyPipeline:{...object(metadata.legacyPipeline),depends_on:names.join(',')||null,...(names.length?{}:{nao_iniciar_antes:null,hora_limite_dependencia:null})}}}
}
