import { WorkspaceSecretParameter, type SecretContext } from './WorkspaceSecretParameter'
import { confirmAction, requestText } from '../../lib/dialogs'
import { lazy, Suspense, useContext, useEffect, useId, useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import { Button } from '../ui/Button'
import { Input, Textarea } from '../ui/Input'
import { encryptedParameter, nodeLabel, object, patchLegacy, text, type JsonObject, type WorkspaceNode, type WorkspaceDefinition } from '../../lib/workspace'
import { typeLabel } from './workspaceCatalog'
import { Maximize2, Minimize2, Trash2, X } from 'lucide-react'
import { Modal } from '../ui/Modal'
import { OverlayScope } from '../ui/overlay'
import { hasSharedJobFields } from '../../lib/workspaceJobFields'
import { hasSpecializedFields } from '../../lib/workspaceSpecialized'
import { deepEqual } from '../../lib/workspacePatch'
import { diagnosticFieldLabel, diagnosticFocusAllowed, diagnosticFocusTarget, INSPECTOR_SECTIONS, inspectorSectionFor, protectedRowsUnchanged, type DiagnosticControl, type InspectorSection } from '../../lib/workspaceInspector'
const SpecializedConfiguration = lazy(() => import('./SpecializedConfiguration'))
import type { JobParamApi } from '../../lib/dsParams'
const WorkspaceLineage = lazy(() => import('./WorkspaceLineage'))
const SharedJobConfiguration = lazy(() => import('./SharedJobConfiguration'))
export interface InspectorDiagnostic { key: number; field: string; message: string; focus: boolean }
type Flags = Partial<Record<InspectorSection, boolean>>
// Limite da espera pelo formulário lazy de um diagnóstico; depois disso o foco fica na subseção.
const DIAGNOSTIC_WAIT_MS = 5000
// Controles visíveis: :disabled inclui o fieldset do modo consulta e <details> fechado não conta.
function diagnosticControls(root:HTMLElement|null):DiagnosticControl<HTMLElement>[] {
 const elements=!root?[]:root.matches('input,select,textarea')?[root]:[...root.querySelectorAll<HTMLElement>('input,select,textarea')]
 return elements.filter(element=>element.getAttribute('type')!=='hidden'&&element.getClientRects().length>0).map(element=>({element,field:element.dataset.diagnosticField??null,editable:!element.matches(':disabled,[readonly]')}))
}
function AdvancedConfiguration({node,editable,onApply,onStaging,onDiscard}:{node:WorkspaceNode;editable:boolean;onApply:(next:WorkspaceNode,base:WorkspaceNode)=>boolean;onStaging:(dirty:boolean)=>void;onDiscard:()=>void}) {
 const [base]=useState(node);const [value,setValue]=useState(()=>JSON.stringify(base.configuration,null,2));const [dirty,setDirty]=useState(false);const [error,setError]=useState('')
 function edit(next:string){setValue(next);if(!dirty){setDirty(true);onStaging(true)}}
 function apply(){
  let parsed:unknown
  try{parsed=JSON.parse(value)}catch{parsed=null}
  if(!parsed||Array.isArray(parsed)||typeof parsed!=='object'){setError('Use um objeto JSON válido. Os valores protegidos devem continuar por referência.');return}
  if(!protectedRowsUnchanged(base.configuration,object(parsed))){setError('Parâmetros protegidos não mudam por aqui. Use Alterar ou Remover na configuração da etapa.');return}
  setError('');onApply({...base,configuration:object(parsed)},base)
 }
 return <div className="space-y-3"><Textarea label="Configuração completa" value={value} onChange={e=>edit(e.target.value)} readOnly={!editable} rows={15} className="font-mono text-xs" error={error}/><p className="text-xs text-dim">Campos adicionais são preservados e só os campos alterados são aplicados. Use identificadores de conexão; valores protegidos permanecem na origem.</p>{editable&&<div className="flex flex-wrap justify-end gap-2"><Button variant="secondary" disabled={!dirty} onClick={onDiscard}>Descartar alterações</Button><Button disabled={!dirty} onClick={apply}>Aplicar configuração</Button></div>}</div>
}
// Inspector da etapa: campos principais à vista e subseções na mesma área (sem
// modal). Cada subseção visitada continua montada e oculta, com o que ainda não
// foi aplicado; Aplicar mescla só os campos alterados a partir da base do formulário.
export function NodeProperties({node,editable,onChange,onPatchNode,onPatchDefinition,onStaging,onDelete,onClose,diagnostic,onDiagnosticFocus,focused,onToggleFocus,onRename,canApply,defaults=[],definition,secretContext}:{secretContext?:SecretContext;definition:WorkspaceDefinition;defaults?:JobParamApi[];canApply:()=>boolean;onRename:(id:string)=>void;diagnostic?:InspectorDiagnostic;onDiagnosticFocus?:()=>void;focused:boolean;onToggleFocus:()=>void;node:WorkspaceNode;editable:boolean;onChange:(node:WorkspaceNode,field?:string)=>void;onPatchNode:(base:WorkspaceNode,next:WorkspaceNode,label:string)=>boolean;onPatchDefinition:(base:WorkspaceDefinition,next:WorkspaceDefinition,label:string)=>boolean;onStaging:(dirty:boolean)=>void;onDelete:()=>void;onClose:()=>void}) {
 const inherited=useContext(OverlayScope);const id=useId()
 const current=useRef({editable,nodeId:node.id,node,onChange,definition,onDiagnosticFocus});useLayoutEffect(()=>{current.current={editable,nodeId:node.id,node,onChange,definition,onDiagnosticFocus}})
 const displayRef=useRef<HTMLInputElement>(null)
 const allowed=()=>current.current.editable&&canApply()
 const shared=hasSharedJobFields(node.type),specialized=hasSpecializedFields(node.type)
 const opening=diagnostic?inspectorSectionFor(diagnostic.field):'configuracao'
 const [section,setSection]=useState<InspectorSection>(opening);const [visited,setVisited]=useState<Flags>({[opening]:true})
 const [staged,setStaged]=useState<Flags>({});const stagedRef=useRef<Flags>({})
 const [versions,setVersions]=useState<Record<string,number>>({});const version=(s:InspectorSection)=>versions[s]??0
 const [seen,setSeen]=useState({node,definition});const [seenDiagnostic,setSeenDiagnostic]=useState(diagnostic?.key)
 const [focusRequest,setFocusRequest]=useState<{section:InspectorSection;field:string}|null>(diagnostic?.focus?{section:opening,field:diagnostic.field}:null)
 const [secret,setSecret]=useState<{node:WorkspaceNode;definition:WorkspaceDefinition;row?:JsonObject;allowed:()=>boolean}|null>(null)
 const bump=(sections:InspectorSection[])=>setVersions(previous=>({...previous,...Object.fromEntries(sections.map(s=>[s,(previous[s]??0)+1]))}))
 // Diagnóstico abre a subseção do campo (campo desconhecido: configuração) e foca o controle do campo.
 // O pedido de foco vale uma vez: remontar o inspector depois (outra seleção e volta) só mostra a mensagem.
 if(diagnostic&&diagnostic.key!==seenDiagnostic){const target=inspectorSectionFor(diagnostic.field);setSeenDiagnostic(diagnostic.key);setSection(target);setVisited(previous=>({...previous,[target]:true}));if(diagnostic.focus)setFocusRequest({section:target,field:diagnostic.field})}
 // A etapa mudou fora do formulário (desfazer, save, outra aba): subseção sem
 // alterações recarrega da etapa atual; a que tem alterações fica como está.
 if(seen.node!==node||seen.definition!==definition){
  const nodeChanged=seen.node.configuration!==node.configuration&&!deepEqual(seen.node.configuration,node.configuration)
  const flowChanged=nodeChanged||seen.definition.edges!==definition.edges||seen.definition.nodes.length!==definition.nodes.length||seen.definition.metadata!==definition.metadata
  const stale=(['configuracao','lineage','avancado'] as const).filter(s=>!staged[s]&&(s==='configuracao'&&specialized?flowChanged:nodeChanged))
  setSeen({node,definition});if(stale.length)bump([...stale])
 }
 // O formulário da subseção pode ser lazy: observa só a subseção até o carregamento sair, por
 // tempo limitado. Mover o foco, trocar de subseção ou de etapa, abrir diálogo ou ocultar o
 // inspector encerra o pedido sem tocar no foco.
 useEffect(()=>{
  if(!focusRequest)return
  current.current.onDiagnosticFocus?.()
  const panel=document.getElementById(`${id}-secao-${focusRequest.section}`),aside=panel?.closest('aside')
  if(!panel||!aside)return
  const trigger=document.activeElement
  let done=false,observer:MutationObserver|undefined
  const stop=()=>{done=true;cancelAnimationFrame(frame);clearTimeout(timer);observer?.disconnect()}
  const allowed=()=>diagnosticFocusAllowed<Element>({active:document.activeElement,body:document.body,trigger,visible:!panel.hidden&&panel.getClientRects().length>0,dialogOpen:!!document.querySelector('[role="dialog"]')})
  const place=(target:HTMLElement)=>{stop();aside.scrollIntoView({block:'start'});target.focus({preventScroll:true})}
  const attempt=()=>{if(done)return;if(!allowed())stop();else if(!panel.querySelector('[data-loading]'))place(diagnosticFocusTarget<HTMLElement>(focusRequest.field,panel,diagnosticControls(panel),diagnosticControls(displayRef.current)))}
  const frame=requestAnimationFrame(()=>{attempt();if(!done){observer=new MutationObserver(attempt);observer.observe(panel,{childList:true,subtree:true})}})
  const timer=window.setTimeout(()=>{if(!done&&allowed())place(panel);else stop()},DIAGNOSTIC_WAIT_MS)
  return stop
 },[focusRequest,id])
 function mark(s:InspectorSection,dirty:boolean){const next={...stagedRef.current,[s]:dirty};stagedRef.current=next;setStaged(next);onStaging(Object.values(next).some(Boolean))}
 function discard(s:InspectorSection){mark(s,false);bump([s])}
 function applied(s:InspectorSection,ok:boolean){if(ok){mark(s,false);bump([s])}return ok}
 function open(s:InspectorSection){setFocusRequest(null);setSection(s);setVisited(previous=>({...previous,[s]:true}))}
 const legacy=object(node.configuration.legacyJob);const rows=Array.isArray(node.configuration.etl_pipeline_job_param)?node.configuration.etl_pipeline_job_param.map(object):[]
 function field(key:string,value:string){onChange(patchLegacy(node,key,value),key)}
 const stage=(s:InspectorSection)=>({onStaging:(dirty:boolean)=>mark(s,dirty),onDiscard:()=>discard(s)})
 const loading=<p role="status" data-loading className="text-sm text-dim">Carregando configuração…</p>
 const content:Record<InspectorSection,()=>ReactNode>={
  configuracao:()=><>
   {shared?<Suspense fallback={loading}><SharedJobConfiguration key={`configuracao-${version('configuracao')}`} context={secretContext} pipelineName={definition.identity.pipelineName} projectName={text(object(object(definition.metadata).legacyPipeline).project_name)} node={node} editable={editable} defaults={defaults} canApply={allowed} onApply={(next,base)=>applied('configuracao',onPatchNode(base,next,'Configuração da etapa'))} onMaximize={focused?undefined:onToggleFocus} {...stage('configuracao')}/></Suspense>
   :specialized?<Suspense fallback={loading}><SpecializedConfiguration key={`configuracao-${version('configuracao')}`} node={node} definition={definition} editable={editable} canApply={allowed} onApply={(next,base)=>applied('configuracao',onPatchDefinition(base,next,'Configuração da etapa'))} onMaximize={focused?undefined:onToggleFocus} {...stage('configuracao')}/></Suspense>
   :<><Textarea label={node.type==='datastage'?'Comando do job':'Comando / código'} value={text(legacy.job_command)} readOnly={!editable} onChange={e=>field('job_command',e.target.value)} rows={4}/><Input label="Conexão SSH (identificador)" value={text(legacy.ssh_conn_id)} readOnly={!editable} onChange={e=>field('ssh_conn_id',e.target.value)}/>
    {['sql','storedproc','email','python'].includes(node.type)&&<><Input label="Conexão SQL (identificador)" value={text(legacy.mssql_conn_id)} readOnly={!editable} onChange={e=>field('mssql_conn_id',e.target.value)}/><Input label="Banco de dados" value={text(legacy.mssql_database)} readOnly={!editable} onChange={e=>field('mssql_database',e.target.value)}/></>}
    {!!rows.length&&<div className="border-t border-edge pt-4"><h4 className="text-sm font-medium text-ink mb-3">Parâmetros da etapa</h4><div className="space-y-3">{rows.map((row,index)=>encryptedParameter(row)?<div key={index} className="text-xs text-dim"><span className="font-medium text-ink">{text(row.param_name)}</span><p>Valor protegido na origem</p></div>:<Input key={index} label={text(row.param_name)} value={text(row.param_value)} readOnly={!editable} onChange={e=>onChange({...node,configuration:{...node.configuration,etl_pipeline_job_param:rows.map((r,i)=>i===index?{...r,param_value:e.target.value}:r)}},`param:${index}`)}/>)}</div></div>}</>}
   {node.type==='datastage'&&editable&&secretContext&&<div className="space-y-2 border-t border-edge pt-4"><h4 className="text-sm font-medium text-ink">Valores protegidos</h4><p className="text-xs text-dim">O valor é cifrado no servidor na hora; desfazer não o reverte.</p>{rows.filter(encryptedParameter).map((row,index)=><Button key={index} size="sm" variant="secondary" className="w-full justify-center" onClick={()=>setSecret({node,definition,row,allowed})}>Alterar {text(row.param_name)}</Button>)}<Button size="sm" variant="secondary" className="w-full justify-center" onClick={()=>setSecret({node,definition,allowed})}>Adicionar parâmetro protegido</Button>{rows.filter(encryptedParameter).map((row,index)=><Button key={`remove-${index}`} size="sm" variant="danger" className="w-full justify-center" onClick={async()=>{const still=()=>current.current.editable&&current.current.node===node&&canApply();if(await confirmAction(`Remover o parâmetro protegido ${text(row.param_name)} desta etapa?`,still)&&still())onChange({...node,configuration:{...node.configuration,etl_pipeline_job_param:rows.filter(item=>item!==row)}})}}>Remover {text(row.param_name)}</Button>)}</div>}
  </>,
  etapa:()=><>
   <Input label="Identificador da etapa" value={node.id} readOnly className="font-mono"/>{editable&&<Button size="sm" variant="secondary" onClick={async()=>{const next=await requestText('Novo identificador da etapa',node.id,()=>current.current.editable&&current.current.nodeId===node.id&&canApply());if(next&&next!==node.id)onRename(next)}}>Renomear identificador</Button>}
   <Input label="Ordem de execução" type="number" min={1} value={String(Number(legacy.execution_order)||1)} data-diagnostic-field="execution_order" readOnly={!editable} ajuda="Prioridade entre etapas liberadas; as dependências continuam no canvas." onChange={e=>onChange({...node,configuration:{...node.configuration,legacyJob:{...legacy,execution_order:Number(e.target.value)}}},'execution_order')}/>
   {editable&&<Button variant="danger" size="sm" onClick={onDelete}><Trash2 size={14}/>Remover etapa</Button>}
  </>,
  lineage:()=><Suspense fallback={<p role="status" data-loading className="text-sm text-dim">Carregando lineage…</p>}><WorkspaceLineage key={`lineage-${version('lineage')}`} node={node} definition={definition} editable={editable} context={secretContext} canApply={allowed} onApply={(next,base)=>applied('lineage',onPatchNode(base,next,'Lineage da etapa'))} {...stage('lineage')}/></Suspense>,
  avancado:()=><AdvancedConfiguration key={`avancado-${version('avancado')}`} node={node} editable={editable} onApply={(next,base)=>applied('avancado',onPatchNode(base,next,'Configuração avançada'))} {...stage('avancado')}/>,
 }
 return <aside className="bg-panel border border-edge rounded-lg p-4 min-w-0" aria-label="Propriedades da etapa">
  <div className="flex items-start justify-between gap-2 mb-4"><div className="min-w-0"><h3 className="font-semibold text-sm text-ink break-words">{nodeLabel(node)}</h3><p className="text-xs text-dim mt-1">{typeLabel(node.type)}</p></div><div className="flex shrink-0 gap-1"><Button variant="ghost" size="sm" aria-label={focused?'Voltar ao canvas':'Expandir propriedades'} title={focused?'Voltar ao canvas (Esc)':'Expandir propriedades sobre o canvas'} aria-pressed={focused} onClick={onToggleFocus}>{focused?<Minimize2 size={16}/>:<Maximize2 size={16}/>}</Button><Button variant="ghost" size="sm" aria-label="Fechar propriedades" onClick={onClose}><X size={16}/></Button></div></div>
  <Input ref={displayRef} label="Nome para exibição" value={text(node.displayName)||node.id} data-diagnostic-field="displayName" readOnly={!editable} onChange={e=>onChange({...node,displayName:e.target.value},'displayName')}/>
  {diagnostic&&<p role="status" className="mt-3 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-800 dark:border-red-900 dark:bg-red-950/30 dark:text-red-300 [overflow-wrap:anywhere]">Última validação: {diagnostic.message} <span className="text-red-700 dark:text-red-400">· campo {diagnosticFieldLabel(diagnostic.field)}</span></p>}
  <div role="group" aria-label="Seções da etapa" className="mt-4 mb-4 flex flex-wrap gap-x-1 border-b border-edge">{INSPECTOR_SECTIONS.map(([s,label])=><button key={s} type="button" aria-pressed={section===s} aria-controls={`${id}-secao-${s}`} aria-label={staged[s]?`${label}, alterações não aplicadas`:undefined} onClick={()=>open(s)} className={`-mb-px inline-flex items-center gap-1.5 border-b-2 px-2 py-1.5 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-600 ${section===s?'border-blue-600 font-medium text-ink dark:border-blue-400':'border-transparent text-dim hover:text-ink'}`}>{label}{staged[s]&&<span aria-hidden="true" className="size-1.5 rounded-full bg-amber-500 dark:bg-amber-400"/>}</button>)}</div>
  {INSPECTOR_SECTIONS.map(([s,label])=>visited[s]&&<section key={s} id={`${id}-secao-${s}`} tabIndex={-1} aria-label={label} hidden={section!==s} className="space-y-4 min-w-0 focus:outline-none"><OverlayScope.Provider value={inherited&&section===s}>{content[s]()}</OverlayScope.Provider></section>)}
  <Modal open={!!secret} onClose={()=>setSecret(null)} title="Valor protegido da etapa" size="md">{secret&&secretContext&&<WorkspaceSecretParameter definition={secret.definition} context={secretContext} jobName={secret.node.id} row={secret.row} canApply={()=>current.current.editable&&current.current.definition===secret.definition&&current.current.node===secret.node&&secret.allowed()} onClose={()=>setSecret(null)} onApply={row=>{if(!current.current.editable||current.current.definition!==secret.definition||current.current.node!==secret.node||!secret.allowed())return;const existing=Array.isArray(secret.node.configuration.etl_pipeline_job_param)?secret.node.configuration.etl_pipeline_job_param.map(object):[];if(existing.some(item=>item!==secret.row&&text(item.param_name).toLowerCase()===text(row.param_name).toLowerCase()))throw new Error('Já existe um parâmetro com este nome.');current.current.onChange({...secret.node,configuration:{...secret.node.configuration,etl_pipeline_job_param:secret.row?existing.map(item=>item===secret.row?row:item):[...existing,row]}})}}/>}</Modal>
 </aside>
}
