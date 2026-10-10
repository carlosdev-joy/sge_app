import { Modal } from '../ui/Modal'
import { useEffect, useRef, useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { type Connection, type EdgeChange, type NodeChange } from '@xyflow/react'
import { GitBranch, LockKeyhole, Pencil, RefreshCw, Save, UnlockKeyhole } from 'lucide-react'
import { workspaceApi } from '../../lib/workspaceApi'
import { cloneFlow, encryptedParameter, object, pipelineParameters, removeWorkspaceNode, renameWorkspaceNode, setPipelineParameters, text, type WorkspaceCapabilities, type WorkspaceDefinition, type WorkspaceDraft, type WorkspaceLayout, type WorkspaceLease } from '../../lib/workspace'
import { useAuthStore } from '../../store/auth'
import { Button } from '../ui/Button'
import { Input, Select } from '../ui/Input'
import { toast } from '../ui/Toast'
import { NodeProperties } from './NodeProperties'
import { WorkspaceCanvas } from './WorkspaceCanvas'
import { WorkspaceDraftTools } from './WorkspaceDraftTools'
import { WorkspacePublicationPanel } from './WorkspacePublication'
import { connectWorkspaceDecision, removeWorkspaceEdges } from '../../lib/workspaceDecision'
import { createPortal } from 'react-dom'
import { arrangeWorkspace } from '../../lib/workspaceLayout'
import { WORKSPACE_TYPES, typeLabel } from './workspaceCatalog'

type LocalDraft = {base:WorkspaceDraft;definition:WorkspaceDefinition;layout:WorkspaceLayout}
const localDrafts=new Map<string,LocalDraft>()
useAuthStore.subscribe((state,previous)=>{if(state.token!==previous.token)localDrafts.clear()})
export function WorkspaceEditor({draft,definition:source,layout:sourceLayout,reasons,capabilities,development,tab,onSaved,onDiscarded,actionsHost}:{actionsHost?:HTMLElement|null;draft:WorkspaceDraft|null;definition:WorkspaceDefinition;layout:WorkspaceLayout;reasons:string[];capabilities:WorkspaceCapabilities;development:boolean;tab:string;onSaved:(draft:WorkspaceDraft)=>void;onDiscarded:()=>void}) {
 const [pendingNodeId,setPendingNodeId]=useState<string|null>(null)
 const editorRef=useRef<HTMLDivElement>(null);const [diagnosticRequest,setDiagnosticRequest]=useState<{id:string;key:number}|null>(null)
 const [layoutKey,setLayoutKey]=useState(0);const [search,setSearch]=useState('');const [librarySearch,setLibrarySearch]=useState('');const [publicationFrozen,setPublicationFrozen]=useState(false)
 const cached=development&&draft?localDrafts.get(draft.draftId):undefined
 const [storedBase,setBase]=useState(cached?.base??draft);const [storedDefinition,setDefinition]=useState(()=>cloneFlow(cached?.definition??source));const [storedLayout,setLayout]=useState(()=>cloneFlow(cached?.layout??sourceLayout));const [dirty,setDirty]=useState(!!cached);const [busy,setBusy]=useState(false);const [lease,setLease]=useState<WorkspaceLease|null>(null);const [selected,setSelected]=useState<string|null>(null);const [issue,setIssue]=useState(cached?'Alterações não salvas foram retomadas nesta aba. Confira a sessão antes de salvar.':'');const [clock,setClock]=useState(()=>Date.now())
 const base=dirty||lease?storedBase:draft
 const definition=development&&draft&&(dirty||lease)?storedDefinition:source
 const layout=development&&draft&&(dirty||lease)?storedLayout:sourceLayout
 const manage=!!base&&base.state==='ativo'&&development&&capabilities.actions.editDraft
 const allowed=manage&&reasons.length===0
 const held=manage&&!!lease&&lease.heldBySession&&Date.parse(lease.expiresAt)>clock
 const editable=allowed&&held&&!busy&&!publicationFrozen
 const pendingRef=useRef(false);const renewRef=useRef<()=>void>(()=>{})
 const renew=useMutation({mutationFn:()=>workspaceApi.lease(base!.draftId,lease!.fence),onSuccess:next=>setLease(next),onError:()=>{setLease(null);setIssue('A sessão de edição foi interrompida. Suas alterações continuam nesta aba. Inicie a edição novamente para conferir a revisão.')}})
 const renewMutation=renew.mutate
 useEffect(()=>{renewRef.current=()=>{if(!pendingRef.current)renewMutation()}},[renewMutation])
 const fence=lease?.fence;const expires=lease?.expiresAt
 useEffect(()=>{if(!fence||!expires||!manage)return;const delay=Math.max(5000,Math.min(30000,(Date.parse(expires)-Date.now())/2));const timer=setInterval(()=>renewRef.current(),delay);return()=>clearInterval(timer)},[fence,expires,manage])
 useEffect(()=>{if(base&&development){if(dirty)localDrafts.set(base.draftId,{base,definition,layout});else localDrafts.delete(base.draftId)}},[base,definition,layout,dirty,development])
 useEffect(()=>{const timer=setInterval(()=>setClock(Date.now()),1000);return()=>clearInterval(timer)},[])
 useEffect(()=>{
  if(!dirty)return
  const unload=(event:BeforeUnloadEvent)=>{event.preventDefault();event.returnValue=''}
  const click=(event:MouseEvent)=>{const target=event.target instanceof Element?event.target.closest('a[href]'):null;if(target&& !window.confirm('Há alterações não salvas nesta aba. Deseja sair?')){event.preventDefault();event.stopImmediatePropagation()}}
  window.addEventListener('beforeunload',unload);document.addEventListener('click',click,true);return()=>{window.removeEventListener('beforeunload',unload);document.removeEventListener('click',click,true)}
 },[dirty])
 function changed(next:WorkspaceDefinition,nextLayout=layout){if(!editable)return;setDefinition(next);setLayout(nextLayout);setDirty(true)}
 function failure(error:unknown){setLease(null);setIssue(error instanceof Error?error.message:'Não foi possível concluir a operação. Suas alterações continuam nesta aba.')}
 async function begin(transfer=false){
  if(!manage||!base||busy)return
  if(transfer&&!window.confirm('Assumir a edição interrompe a posse atual. Deseja continuar?'))return
  pendingRef.current=true;setBusy(true)
  try{
   const current=await workspaceApi.draft(base.draftId)
   if(current.revision!==base.revision&&dirty){setIssue('O rascunho foi alterado por outra sessão. Recarregue para conferir; as alterações desta aba não foram substituídas.');return}
   if(!dirty){setBase(current);setDefinition(cloneFlow(current.definition));setLayout(cloneFlow(current.layout))}
   onSaved(current)
   const next=transfer?await workspaceApi.transfer(current,current.lease?.fence??0):await workspaceApi.lease(current.draftId)
   setLease(next);setIssue('');setClock(Date.now())
  }catch(error){failure(error)}finally{pendingRef.current=false;setBusy(false)}
 }
 const save=useMutation({mutationFn:()=>workspaceApi.save(base!,definition,layout,lease!.fence),onMutate:()=>{pendingRef.current=true;setBusy(true)},onSuccess:next=>{localDrafts.delete(next.draftId);setBase(next);setDefinition(cloneFlow(next.definition));setLayout(cloneFlow(next.layout));setLease(next.lease);setDirty(false);setIssue('');onSaved(next);toast.success('Rascunho salvo')},onError:failure,onSettled:()=>{pendingRef.current=false;setBusy(false)}})
 async function reload(){if(!base||busy)return;if(dirty&&!window.confirm('Recarregar substitui as alterações não salvas desta aba. Continuar?'))return;try{const next=await workspaceApi.draft(base.draftId);localDrafts.delete(next.draftId);setBase(next);setDefinition(cloneFlow(next.definition));setLayout(cloneFlow(next.layout));setLease(null);setDirty(false);setIssue('');onSaved(next)}catch(error){failure(error)}}
 async function release(discard=false){if(!base||!lease||busy)return;if(dirty&&!window.confirm('Há alterações não salvas. Deseja encerrar a edição?'))return;if(discard&&!window.confirm('Descartar este rascunho? A configuração publicada permanece disponível.'))return;pendingRef.current=true;setBusy(true);try{if(discard){await workspaceApi.discard(base,lease.fence);localDrafts.delete(base.draftId);setDirty(false);setLease(null);onDiscarded()}else{await workspaceApi.release(base,lease.fence);setLease(null)}}catch(error){failure(error)}finally{pendingRef.current=false;setBusy(false)}}
 function add(type:string){if(!editable)return;let index=1;while(definition.nodes.some(n=>n.id===`${type}_${index}`))index++;const id=`${type}_${index}`;changed({...definition,nodes:[...definition.nodes,{id,type,configuration:{legacyJob:{pipeline_name:definition.identity.pipelineName,job_name:id,job_type:type,job_command:null,execution_order:definition.nodes.length+1},etl_pipeline_job_param:[]}}]},{...layout,nodes:{...layout.nodes,[id]:{x:100+(definition.nodes.length%4)*250,y:80+Math.floor(definition.nodes.length/4)*150}}});setSelected(id)}
 function positions(changes:NodeChange[]){if(!editable)return;const positions={...layout.nodes};let modified=false;for(const change of changes)if(change.type==='position'&&change.position){positions[change.id]={...positions[change.id],x:change.position.x,y:change.position.y};modified=true}if(modified)changed(definition,{...layout,nodes:positions})}
 function edges(changes:EdgeChange[]){const removed=new Set(changes.filter(c=>c.type==='remove').map(c=>c.id));if(removed.size)changed(removeWorkspaceEdges(definition,removed))}
 function connect(connection:Connection){if(!editable)return;try{changed(connectWorkspaceDecision(definition,connection.source,connection.target,connection.sourceHandle))}catch(error){toast.error(error instanceof Error?error.message:'Dependência inválida')}}
 const node=definition.nodes.find(n=>n.id===selected);const params=pipelineParameters(definition);const owner=lease??draft?.lease??base?.lease
 useEffect(()=>{
  if(!diagnosticRequest)return
  const frame=requestAnimationFrame(()=>{const panel=editorRef.current?.querySelector<HTMLElement>('[aria-label="Propriedades da etapa"]');panel?.scrollIntoView({block:'start'});panel?.querySelector<HTMLElement>('textarea')?.focus({preventScroll:true})})
  return()=>cancelAnimationFrame(frame)
 },[diagnosticRequest])
 const actions=(<div className="flex flex-wrap gap-2">{base&&<Button size="sm" variant="secondary" disabled={busy} onClick={reload}><RefreshCw size={14}/>Recarregar</Button>}{manage&&!held&&<Button disabled={busy} size="sm" onClick={()=>begin()}><Pencil size={14}/>{reasons.length?'Gerenciar rascunho':'Iniciar edição'}</Button>}{manage&&!held&&capabilities.actions.administer&&owner&&!owner.heldBySession&&<Button size="sm" variant="secondary" disabled={busy} onClick={()=>begin(true)}>Assumir edição</Button>}{held&&<><Button disabled={busy} size="sm" variant="secondary" onClick={()=>release()}>Encerrar edição</Button>{allowed&&<Button size="sm" onClick={()=>save.mutate()} disabled={!dirty||publicationFrozen} loading={save.isPending}><Save size={14}/>Salvar rascunho</Button>}</>}</div>)
 const publication=base&&development&&capabilities.actions.consultVersions&&<WorkspacePublicationPanel embedded={tab!=='parametros'} draft={base} fence={held?lease?.fence:undefined} canPublish={capabilities.actions.publish} dirty={dirty} busy={busy} onFreeze={setPublicationFrozen} onConfirmed={reload} onSelect={id=>{setSelected(id);setDiagnosticRequest({id,key:Date.now()})}}/>
 return <div ref={editorRef} className="space-y-3">
  <div className="flex flex-wrap items-center justify-between gap-3 px-0 py-0">
   <div className="text-xs flex items-center gap-2 text-dim">{editable?<UnlockKeyhole size={17}/>:<LockKeyhole size={17}/>}<span>{editable?'Você está editando o rascunho':owner&&Date.parse(owner.expiresAt)>clock?`${owner.holderUser} possui a sessão de edição`:'Modo consulta'}{base&&` · revisão ${base.revision}`}</span></div>
   {!actionsHost&&actions}
   {actionsHost&&createPortal(actions,actionsHost)}
  </div>
  {(issue||!!reasons.length)&&<div role="alert" className="border border-amber-300 bg-amber-50 text-amber-900 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-300 rounded-lg p-3 text-sm">{issue||reasons.join(' · ')}</div>}
  <div className="text-xs text-dim flex flex-wrap justify-between gap-2"><span>{dirty?'Alterações ainda não salvas nesta aba':base?`Último salvamento: ${new Date(base.updatedAt).toLocaleString('pt-BR')}`:'Configuração publicada'} · {definition.nodes.length} etapas</span>{base&&<span>Responsável: {base.responsible}</span>}</div>


  {tab==='parametros'?<div className="border border-edge rounded-lg bg-panel p-5"><h2 className="font-semibold text-ink mb-4">Parâmetros do pipeline</h2>{editable&&<Button variant="secondary" size="sm" className="mb-4" onClick={()=>{const name=window.prompt("Nome do parâmetro");if(!name)return;if(params.some(p=>text(p.param_name).toLowerCase()===name.toLowerCase())){toast.error("Já existe um parâmetro com este nome.");return}changed(setPipelineParameters(definition,[...params,{pipeline_name:definition.identity.pipelineName,param_name:name,param_type:"String",param_value:""}]))}}>Adicionar parâmetro</Button>}{params.length?<div className="space-y-4 max-w-2xl">{params.map((row,index)=>encryptedParameter(row)?<div key={index} className="text-sm text-dim"><strong className="text-ink">{text(row.param_name)}</strong><p>Valor protegido na origem</p></div>:<Input key={index} label={text(row.param_name)} value={text(row.param_value)} readOnly={!editable} onChange={event=>changed(setPipelineParameters(definition,params.map((r,i)=>i===index?{...r,param_value:event.target.value}:r)))}/>)}</div>:<p className="text-sm text-dim">Nenhum parâmetro cadastrado.</p>}</div>:<div className="grid gap-3 lg:grid-cols-[160px_minmax(0,1fr)_260px]">
   <aside className="border border-edge rounded-lg bg-panel p-3"><h2 className="text-sm font-semibold text-ink mb-3">Componentes</h2><Input label="Buscar componente" value={librarySearch} onChange={e=>setLibrarySearch(e.target.value)} className="mb-3"/>{[['Integração',['datastage','sql','python','shell','storedproc','http']],['Controle',['decisao','aguarde']],['Entrega',['valida_arquivo','notificacao','email']]].map(([group,kinds])=><div key={String(group)} className="mb-4"><h3 className="text-xs font-medium text-dim mb-2">{group}</h3><div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-1 gap-2">{WORKSPACE_TYPES.filter(([type,label])=>(kinds as string[]).includes(type)&&label.toLocaleLowerCase().includes(librarySearch.toLocaleLowerCase())).map(([type,label,Icon])=><button key={type} type="button" disabled={!editable} onClick={()=>add(type)} className="flex items-center gap-2 px-2 py-2 text-left text-xs rounded border border-edge text-ink hover:bg-edge/20 focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-600 disabled:opacity-60 disabled:cursor-not-allowed"><Icon size={15} className="text-blue-700 dark:text-blue-400 shrink-0"/>{label}</button>)}</div></div>)}<p className="text-xs text-dim mt-4">{editable?'Clique para adicionar uma etapa.':'Tipos de etapa disponíveis no workspace.'}</p></aside>
   <section className="border border-edge rounded-lg bg-panel min-w-0 overflow-hidden"><div className="flex items-center justify-between gap-2 px-4 py-3 border-b border-edge"><h2 className="text-sm font-semibold text-ink">{tab==='etapas'?'Etapas do pipeline':development?'Fluxo em montagem':base?'Fluxo do rascunho':'Fluxo publicado'}</h2><div className="flex items-center gap-2"><Button size="sm" variant="secondary" disabled={!editable||!definition.nodes.length} onClick={()=>{changed(definition,arrangeWorkspace(definition,layout));setLayoutKey(v=>v+1)}}><GitBranch size={13}/>Organizar</Button><span className="text-xs text-dim">{editable?'Montagem':'Somente leitura'}</span></div></div>{tab!=='etapas'&&<div className="px-4 py-2 border-b border-edge"><Select label="Localizar etapa no fluxo" value={selected??''} onChange={e=>setSelected(e.target.value||null)}><option value="">Selecione uma etapa</option>{definition.nodes.map(n=><option key={n.id} value={n.id}>{n.id} · {typeLabel(n.type)}</option>)}</Select></div>}{tab==='etapas'?<div><div className="p-3 border-b border-edge"><Input label="Buscar etapa no pipeline" value={search} onChange={e=>setSearch(e.target.value)}/></div><div className="divide-y divide-edge">{definition.nodes.filter(n=>(n.id+' '+typeLabel(n.type)).toLocaleLowerCase().includes(search.toLocaleLowerCase())).map(n=><button key={n.id} onClick={()=>setSelected(n.id)} className="w-full text-left flex gap-4 px-4 py-3 text-sm text-ink hover:bg-edge/20"><span className="min-w-0 break-words flex-1">{n.id}</span><span className="text-dim">{typeLabel(n.type)} · ordem {Number(object(n.configuration.legacyJob).execution_order)||1}</span></button>)}{!definition.nodes.length&&<p className="p-5 text-sm text-dim">Nenhuma etapa no fluxo.</p>}</div></div>:<WorkspaceCanvas key={layoutKey} definition={definition} layout={layout} editable={editable} selected={selected} onSelect={setSelected} onPositions={positions} onRemoveEdge={edges} onConnect={connect}/>}
    {publication}
   </section>
   {!node&&<aside className="border border-edge rounded-lg bg-panel p-4 min-w-0"><h2 className="text-sm font-semibold text-ink">Propriedades da etapa</h2><p className="text-sm text-dim mt-3">Selecione uma etapa no fluxo para consultar sua configuração.</p><dl className="mt-6 space-y-4 text-sm"><div><dt className="text-dim">Pipeline</dt><dd className="text-ink break-all">{definition.identity.pipelineName}</dd></div><div><dt className="text-dim">Componentes</dt><dd className="text-ink">{definition.nodes.length}</dd></div><div><dt className="text-dim">Conexões</dt><dd className="text-ink">{definition.edges.length}</dd></div></dl></aside>}
   {node&&<NodeProperties key={`${node.id}:${diagnosticRequest?.id===node.id?diagnosticRequest.key:0}`} node={node} editable={editable} diagnosticRequest={diagnosticRequest?.id===node.id?diagnosticRequest.key:undefined} onClose={()=>setSelected(null)} onRename={id=>{try{const next=renameWorkspaceNode(definition,layout,node.id,id);changed(next.definition,next.layout);setSelected(id)}catch(e){toast.error(e instanceof Error?e.message:'Não foi possível renomear')}}} onChange={next=>changed({...definition,nodes:definition.nodes.map(n=>n.id===next.id?next:n)})} onDelete={()=>setPendingNodeId(node.id)}/>}
  </div>}
  {tab==='parametros'&&publication}
  <Modal open={pendingNodeId!==null} onClose={()=>setPendingNodeId(null)} title="Remover etapa" size="sm"><p className="text-sm text-ink [overflow-wrap:anywhere]">Remover a etapa {pendingNodeId} e suas ligações do rascunho?</p><p className="text-xs text-dim mt-2">A configuração publicada permanece disponível.</p><div className="flex justify-end gap-3 mt-5"><Button variant="secondary" onClick={()=>setPendingNodeId(null)}>Cancelar</Button><Button variant="danger" disabled={!editable} onClick={()=>{if(pendingNodeId){const next=removeWorkspaceNode(definition,layout,pendingNodeId);changed(next.definition,next.layout);setSelected(null)}setPendingNodeId(null)}}>Remover etapa</Button></div></Modal>
  <WorkspaceDraftTools key={`${base?.revision}-${editable}`} definition={definition} editable={editable} onApply={next=>changed(next)}/>
  {held&&base&&<div className="flex justify-end"><Button variant="ghost" size="sm" disabled={busy||publicationFrozen} onClick={()=>release(true)}>Descartar rascunho</Button></div>}
 </div>
}
