import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { Plus, Trash2 } from 'lucide-react'
import { apiFetch } from '../../lib/api'
import { confirmAction } from '../../lib/dialogs'
import { object, pipelineMetadata, text, type JsonObject, type WorkspaceDefinition, type WorkspaceNode } from '../../lib/workspace'
import { Button } from '../ui/Button'
import { Input, Select, Textarea } from '../ui/Input'
import { toast } from '../ui/Toast'
import type { SecretContext } from './WorkspaceSecretParameter'

const FIELDS: readonly [string,string,number?][] = [['object_type','Tipo do objeto',100],['stage_name','Stage',200],['stage_type_raw','Tipo do stage',100],['database_name','Banco de dados',200],['file_path','Caminho do arquivo',500],['dsx_source_file','Arquivo DSX de origem',500],['stage_internal_id','Identificador interno do stage',20]]
const LONG_FIELDS: readonly [string,string][] = [['sql_expression','SQL / expressão'],['columns_json','Colunas de saída (JSON)'],['input_columns_json','Colunas de entrada (JSON)'],['expressions_json','Expressões (JSON)'],['apt_code','Código APT']]
export default function WorkspaceLineage({node,definition,editable,context,canApply,onApply,onClose}:{node:WorkspaceNode;definition:WorkspaceDefinition;editable:boolean;context?:SecretContext;canApply:()=>boolean;onApply:(node:WorkspaceNode)=>void;onClose:()=>void}) {
 const captured=object(definition.metadata).workspaceLineageVersion===1
 const [rows,setRows]=useState<JsonObject[]>(()=>Array.isArray(node.configuration.etl_job_lineage)?node.configuration.etl_job_lineage.map(object):[])
 const [selected,setSelected]=useState(0);const [project,setProject]=useState(text(pipelineMetadata(definition).project_name));const [job,setJob]=useState(text(object(node.configuration.legacyJob).job_command));const [source,setSource]=useState('dsx')
 const [busy,setBusy]=useState(false);const [preview,setPreview]=useState<{rows:JsonObject[];prior:JsonObject[];key:string}|null>(null)
 const mounted=useRef(true);useEffect(()=>{mounted.current=true;return()=>{mounted.current=false}},[])
 const current=useRef({rows,project,job,source,canApply,editable,context})
 useLayoutEffect(()=>{current.current={rows,project,job,source,canApply,editable,context}})
 const ready=captured&&editable&&canApply()
 const allowed=()=>captured&&current.current.editable&&current.current.canApply()
 const key=JSON.stringify([source,project,job,context?.draftId,context?.expectedRevision,context?.fence])
 const previewValid=!!preview&&preview.prior===rows&&preview.key===key&&ready
 const row=rows[selected]
 const errors=rows.flatMap((value,index)=>{
  const result:string[]=[]
  if(!text(value.object_name).trim()||text(value.object_name).length>500)result.push(`Objeto ${index+1}: informe um nome com até 500 caracteres.`)
  if(!text(value.direction).trim())result.push(`Objeto ${index+1}: informe a direção.`)
  for(const [field,label] of LONG_FIELDS)if(field.endsWith('_json')&&text(value[field]).trim())try{JSON.parse(text(value[field]))}catch{result.push(`Objeto ${index+1}: ${label} inválido.`)}
  return result
 })
 function change(field:string,value:string){if(allowed())setRows(previous=>previous.map((item,index)=>index===selected?{...item,[field]:value||null}:item))}
 async function importSource(){
  if(!allowed()||!context||busy)return
  const opening=current.current;setBusy(true);setPreview(null)
  try{
   const result=await apiFetch<{rows:JsonObject[]}>(`/workspace-adapter/lineage/${encodeURIComponent(context.draftId)}/${source}-preview`,{method:'POST',body:JSON.stringify({...context,jobName:node.id,projectName:project,dataStageJob:job})})
   if(!mounted.current)return
   const now=current.current
   if(!allowed()||now.rows!==opening.rows||now.project!==opening.project||now.job!==opening.job||now.source!==opening.source||now.context?.draftId!==opening.context?.draftId||now.context?.expectedRevision!==opening.context?.expectedRevision||now.context?.fence!==opening.context?.fence){toast.info('A configuração mudou. Solicite uma nova prévia.');return}
   setPreview({rows:result.rows,prior:opening.rows,key})
  }catch(error){if(mounted.current&&allowed())toast.error(error instanceof Error?error.message:'Não foi possível consultar o extrator.')}finally{if(mounted.current)setBusy(false)}
 }
 return <div className="space-y-5 min-w-0">
  <p className="text-sm text-dim">Origens, destinos e transformações desta etapa. Aplicar mantém as mudanças no Fluxo; salve o rascunho para persistir.</p>
  {!captured&&<p role="status" className="text-sm text-dim">Esta versão não capturou lineage. Conclua ou descarte o rascunho e reimporte o pipeline para editar estes dados.</p>}
  <div className="flex flex-wrap items-center justify-between gap-3"><p className="text-sm text-dim">{rows.length} objeto{rows.length===1?'':'s'} no lineage</p>{ready&&<Button size="sm" variant="secondary" onClick={()=>{setSelected(rows.length);setRows([...rows,{direction:'origem',object_name:'',object_type:'Tabela',extraction_method:'manual'}])}}><Plus size={14}/>Adicionar objeto</Button>}</div>
  {rows.length>0?<div className="grid gap-5 md:grid-cols-[minmax(150px,1fr)_minmax(0,3fr)]">
   <nav aria-label="Objetos do lineage" className="max-h-96 overflow-y-auto min-w-0 border-r border-edge pr-3"><ul className="space-y-1">{rows.map((item,index)=><li key={index}><button type="button" aria-current={index===selected?'true':undefined} onClick={()=>setSelected(index)} className={`w-full text-left rounded px-3 py-2 text-sm break-words focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary ${index===selected?'bg-canvas text-ink font-medium':'text-dim hover:bg-canvas'}`}><span className="block">{text(item.object_name)||'Novo objeto'}</span><span className="text-xs text-dim">{text(item.direction)} · {text(item.extraction_method)||'legado'}</span></button></li>)}</ul></nav>
   {row&&<fieldset disabled={!ready} className="space-y-4 min-w-0"><div className="grid gap-4 sm:grid-cols-2"><Select label="Direção" value={text(row.direction)} onChange={e=>change('direction',e.target.value)}>{['origem','destino','transformacao'].map(value=><option key={value} value={value}>{value==='transformacao'?'Transformação':value==='origem'?'Origem':'Destino'}</option>)}{!['origem','destino','transformacao'].includes(text(row.direction))&&<option value={text(row.direction)}>{text(row.direction)||'Selecione'}</option>}</Select><Input label="Nome do objeto *" value={text(row.object_name)} maxLength={500} onChange={e=>change('object_name',e.target.value)}/>{FIELDS.map(([field,label,length])=><Input key={field} label={label} maxLength={length} value={text(row[field])} onChange={e=>change(field,e.target.value)}/>)}</div>{LONG_FIELDS.map(([field,label])=><Textarea key={field} label={label} rows={field==='sql_expression'||field==='apt_code'?5:3} value={text(row[field])} onChange={e=>change(field,e.target.value)} className="font-mono text-xs"/>)}</fieldset>}
  </div>:<p className="text-sm text-dim">Nenhum objeto registrado. Uma lista vazia capturada também faz parte da versão.</p>}
  {row&&ready&&<Button variant="danger" size="sm" onClick={async()=>{const opening=current.current.rows;if(await confirmAction('Remover este objeto do lineage do rascunho?',()=>allowed()&&current.current.rows===opening)&&allowed()&&current.current.rows===opening){setRows(rows.filter((_,index)=>index!==selected));setSelected(Math.max(0,selected-1))}}}><Trash2 size={14}/>Remover objeto selecionado</Button>}
  {node.type==='datastage'&&captured&&context&&<section className="border-t border-edge pt-5 space-y-4"><h3 className="text-sm font-medium text-ink">Importar lineage DataStage</h3><p className="text-sm text-dim">Consulte o extrator existente e revise o resultado. A importação substitui somente os objetos do mesmo método no rascunho.</p><fieldset disabled={!ready||busy} className="grid gap-4 sm:grid-cols-3"><Select label="Fonte" value={source} onChange={e=>setSource(e.target.value)}><option value="dsx">Arquivo DSX</option><option value="isx">DataStage ISX</option></Select><Input label="Projeto DataStage" value={project} onChange={e=>setProject(e.target.value)} maxLength={source==='isx'?50:100}/><Input label="Job DataStage" value={job} onChange={e=>setJob(e.target.value)} maxLength={200}/></fieldset><Button variant="secondary" disabled={!ready||!project||!job||busy} loading={busy} onClick={importSource}>Consultar prévia</Button>{preview&&<div role="status" className="space-y-3"><p className="text-sm text-ink">{preview.rows.length} objeto{preview.rows.length===1?'':'s'} encontrado{preview.rows.length===1?'':'s'}.</p><ul className="max-h-48 overflow-auto text-sm text-dim divide-y divide-edge">{preview.rows.map((item,index)=><li key={index} className="py-2 break-words">{text(item.direction)} · {text(item.object_name)}</li>)}</ul><Button variant="secondary" disabled={!previewValid} onClick={()=>{if(previewValid){setRows([...rows.filter(item=>text(item.extraction_method)!==`${source}_auto`),...preview.rows]);setSelected(0);setPreview(null)}}}>Aplicar importação ao editor</Button>{!previewValid&&<p className="text-sm text-dim">A configuração mudou. Consulte uma nova prévia.</p>}</div>}</section>}
  {errors.length>0&&<div role="status" className="text-sm text-amber-800 dark:text-amber-300">{errors.slice(0,20).map(error=><p key={error}>{error}</p>)}</div>}
  <div className="flex flex-wrap justify-end gap-2 border-t border-edge pt-4"><Button variant="secondary" onClick={onClose}>{editable?'Cancelar':'Fechar'}</Button>{ready&&<Button disabled={errors.length>0} onClick={()=>{if(allowed())onApply({...node,configuration:{...node.configuration,etl_job_lineage:rows}})}}>Aplicar lineage ao fluxo</Button>}</div>
 </div>
}
