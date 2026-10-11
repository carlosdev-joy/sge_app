import { WorkspaceCatalogFields, WorkspaceScheduleFields, WorkspaceGovernanceFields, type GovernanceSection } from './WorkspacePipelineFields'
import { lazy, Suspense, useLayoutEffect, useRef, useState } from 'react'
const DependenciasModal=lazy(()=>import('../pipelines/DependenciasModal').then(module=>({default:module.DependenciasModal})))
import { workspacePredecessors, setWorkspacePredecessors } from '../../lib/workspaceCatalog'
import { toast } from '../ui/Toast'
import { definitionLabel, object, pipelineMetadata, text, type WorkspaceDefinition } from '../../lib/workspace'
import { Button } from '../ui/Button'
import { Textarea } from '../ui/Input'

// Campos do pipeline por grupo da Configuração. Os formulários são os mesmos
// do cadastro anterior; cada alteração preserva as demais chaves de legacyPipeline.
export function WorkspacePipelineGroup({group,definition,editable,onApply,responsible}:{group:GovernanceSection;definition:WorkspaceDefinition;editable:boolean;onApply:(next:WorkspaceDefinition)=>void;responsible?:string}) {
 const [dependencies,setDependencies]=useState<WorkspaceDefinition|null>(null)
 const current=useRef({definition,editable,onApply});useLayoutEffect(()=>{current.current={definition,editable,onApply}})
 const metadata=pipelineMetadata(definition)
 const patch=(next:Record<string,unknown>)=>onApply({...definition,metadata:{...object(definition.metadata),legacyPipeline:next}})
 const predecessors=workspacePredecessors(definition)
 return <div className="space-y-6">
  {group==='identificacao'&&<><dl className="grid sm:grid-cols-2 gap-4 text-sm"><div><dt className="text-dim">Nome amigável</dt><dd className="text-ink mt-1 break-words">{definitionLabel(definition)}</dd></div><div><dt className="text-dim">Identificador técnico</dt><dd className="text-ink mt-1 font-mono text-xs break-all">{definition.identity.pipelineName}</dd></div>{responsible&&<div><dt className="text-dim">Responsável pelo rascunho</dt><dd className="text-ink mt-1 break-words">{responsible}</dd></div>}</dl><p className="text-xs text-dim">Nome amigável e identificador são definidos na criação.</p><div className="grid sm:grid-cols-2 gap-3"><WorkspaceCatalogFields project={text(metadata.project_name)} domain={text(metadata.domain)} editable={editable} onChange={(field,value)=>patch({...metadata,[field]:value})}/></div></>}
  {group==='agenda'&&<><WorkspaceScheduleFields value={metadata} editable={editable} onChange={patch}/><section className="space-y-3 border-t border-edge pt-5"><h3 className="text-sm font-medium text-ink">Dependências entre pipelines</h3><p className="text-sm text-dim break-words">{predecessors.join(', ')||'Nenhum predecessor configurado.'}</p>{editable&&<Button variant="secondary" size="sm" onClick={()=>setDependencies(definition)}>Escolher predecessores</Button>}</section></>}
  <WorkspaceGovernanceFields section={group} value={metadata} editable={editable} onChange={patch}/>
  {dependencies&&<Suspense fallback={<p role="status" className="text-sm text-dim">Carregando dependências…</p>}><DependenciasModal pipelineAtual={definition.identity.pipelineName} isEdit={false} draft selecionadas={workspacePredecessors(dependencies)} onClose={()=>setDependencies(null)} onConfirmar={names=>{if(!current.current.editable||current.current.definition!==dependencies)return;try{current.current.onApply(setWorkspacePredecessors(dependencies,names))}catch(error){toast.error(error instanceof Error?error.message:'Confira as dependências.')}}}/></Suspense>}
 </div>
}

// Ações avançadas em JSON: metadados completos (Configuração) e importação em lote (Montagem).
export function WorkspaceJsonTools({definition,editable,onApply,mode:kind}:{definition:WorkspaceDefinition;editable:boolean;onApply:(next:WorkspaceDefinition)=>void;mode:'metadata'|'import'}) {
 const [open,setOpen]=useState(false);const [value,setValue]=useState('');const [error,setError]=useState('')
 function start(){setOpen(true);setError('');setValue(kind==='metadata'?JSON.stringify(definition.metadata??{},null,2):'[\n  {"job_name":"nova_etapa","job_type":"shell","job_command":"true","execution_order":1}\n]')}
 function apply(){try{
  const raw:unknown=JSON.parse(value)
  if(kind==='metadata') {if(!raw||typeof raw!=='object'||Array.isArray(raw))throw new Error('Use um objeto JSON para a configuração do pipeline.');onApply({...definition,metadata:object(raw)})}
  else {
   if(!Array.isArray(raw)||!raw.length||raw.length+definition.nodes.length>500)throw new Error('Informe uma lista com até 500 etapas no total.')
   const names=new Set(definition.nodes.map(n=>n.id.toLocaleLowerCase()));const nodes=raw.map(item=>{const row=object(item);const name=text(row.job_name);if(!/^[A-Za-z0-9_.-]+$/.test(name)||name.length>200||names.has(name.toLocaleLowerCase()))throw new Error('Cada etapa exige um identificador único, sem espaços.');names.add(name.toLocaleLowerCase());if(!text(row.job_type))throw new Error('Informe job_type em cada etapa.');if(row.depends_on_jobs||row.condition_json)throw new Error('Importe primeiro as etapas sem dependências/decisões e monte as conexões no canvas. Esses campos não são descartados silenciosamente.');return {id:name,type:text(row.job_type),configuration:{legacyJob:{...row,pipeline_name:definition.identity.pipelineName},etl_pipeline_job_param:[],...(object(definition.metadata).workspaceLineageVersion===1?{etl_job_lineage:[]}: {})}}})
   onApply({...definition,nodes:[...definition.nodes,...nodes]})
  };setOpen(false)
 }catch(e){setError(e instanceof Error?e.message:'Configuração inválida.')}}
 if(kind==='import'&&!editable)return null
 return <div className="space-y-3">{!open&&<Button size="sm" variant="secondary" onClick={start}>{kind==='metadata'?'Configuração completa (JSON)':'Importar etapas em lote (JSON)'}</Button>}{open&&<><Textarea label={kind==='metadata'?'Metadados e catálogos do pipeline':'Etapas a importar (lista JSON)'} value={value} readOnly={!editable} onChange={e=>setValue(e.target.value)} rows={12} error={error} className="font-mono text-xs"/><div className="flex gap-2">{editable&&<Button size="sm" onClick={apply}>{kind==='import'?'Adicionar ao rascunho':'Aplicar ao rascunho'}</Button>}<Button size="sm" variant="secondary" onClick={()=>setOpen(false)}>Fechar</Button></div></>}</div>
}
