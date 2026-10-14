import { WorkspaceFlowTools } from './WorkspaceFlowTools'
import { useNavigationGuard } from '../../lib/navigationGuard'
import { OverlayScope } from '../ui/overlay'
import { confirmAction } from '../../lib/dialogs'
import { Modal } from '../ui/Modal'
import { useContext, useEffect, useId, useLayoutEffect, useRef, useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { type Connection, type EdgeChange, type NodeChange } from '@xyflow/react'
import { GitBranch, LockKeyhole, PanelLeftClose, PanelLeftOpen, PanelRightClose, PanelRightOpen, Pencil, Redo2, RefreshCw, Save, Undo2, UnlockKeyhole } from 'lucide-react'
import { workspaceApi } from '../../lib/workspaceApi'
import { object, cloneFlow, pipelineParameters, removeWorkspaceNode, renameWorkspaceNode, type WorkspaceCapabilities, type WorkspaceDefinition, type WorkspaceDraft, type WorkspaceLayout, type WorkspaceLease } from '../../lib/workspace'
import { useAuthStore } from '../../store/auth'
import { Button } from '../ui/Button'
import { Input, Select } from '../ui/Input'
import { toast } from '../ui/Toast'
import { NodeProperties, type InspectorDiagnostic } from './NodeProperties'
import { emptyHistory, historyLabels, recordHistory, redoHistory, sealHistory, TEXT_GROUP_MS, undoHistory, type HistoryChange, type WorkspaceHistory } from '../../lib/workspaceHistory'
import { mergeDefinitionPatch, mergeNodePatch, type PatchResult } from '../../lib/workspacePatch'
import { historyFocusTarget, historyShortcut } from '../../lib/workspaceInspector'
import { WorkspaceCanvas } from './WorkspaceCanvas'
import { WorkspaceJsonTools } from './WorkspaceDraftTools'
import { WorkspaceConfiguration } from './WorkspaceConfiguration'
import type { JobParamApi } from '../../lib/dsParams'
import { sameWorkspaceSession, type ConfigurationGroup } from '../../lib/workspaceTabs'
import { WorkspacePublicationPanel } from './WorkspacePublication'
import { connectWorkspaceDecision, removeWorkspaceEdges } from '../../lib/workspaceDecision'
import { createPortal } from 'react-dom'
import { arrangeWorkspace } from '../../lib/workspaceLayout'
import { WORKSPACE_COMPONENT_MIME, WORKSPACE_TYPES, typeLabel } from './workspaceCatalog'
import { WORKSPACE_FRAMED_CONTENT } from '../../lib/shellFrame'

type LocalDraft = {base:WorkspaceDraft;definition:WorkspaceDefinition;layout:WorkspaceLayout}
const localDrafts=new Map<string,LocalDraft>()
useAuthStore.subscribe((state,previous)=>{if(state.token!==previous.token)localDrafts.clear()})
export interface WorkspaceSessionState { dirty: boolean; unapplied: boolean; editable: boolean; revision: number | null }
// Colunas da Montagem por painel aberto (biblioteca 160–216 px, inspector 260–352 px);
// painel recolhido sai da grade e o canvas recebe a largura.
const ASSEMBLY_COLUMNS = {
 both: 'lg:grid-cols-[160px_minmax(0,1fr)_260px] xl:grid-cols-[192px_minmax(0,1fr)_320px] 2xl:grid-cols-[216px_minmax(0,1fr)_352px]',
 library: 'lg:grid-cols-[160px_minmax(0,1fr)] xl:grid-cols-[192px_minmax(0,1fr)] 2xl:grid-cols-[216px_minmax(0,1fr)]',
 inspector: 'lg:grid-cols-[minmax(0,1fr)_260px] xl:grid-cols-[minmax(0,1fr)_320px] 2xl:grid-cols-[minmax(0,1fr)_352px]',
 none: 'lg:grid-cols-1',
}
const PANEL_TOGGLE = 'ui-button ui-button-small inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-xs focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-600'
const panelToggleTone = (open: boolean) => open ? 'border-blue-300 bg-blue-50 text-blue-800 dark:border-blue-800 dark:bg-blue-900/30 dark:text-blue-300' : 'border-edge text-ink hover:bg-edge/30'
const HISTORY_BUTTON = 'inline-flex size-8 items-center justify-center rounded-md text-ink hover:bg-edge/30 disabled:cursor-not-allowed disabled:opacity-40 focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-600'
const TEXT_TARGET = 'input,textarea,select,[contenteditable]:not([contenteditable="false"])'
const inside = (target: EventTarget | null, selector: string) => typeof Element !== 'undefined' && target instanceof Element && !!target.closest(selector)
type ChangeMeta = Omit<HistoryChange, 'now'>
// "alterações não salvas" (definição) e "não aplicadas" (inspector) são estados separados.
const pendingChanges = (dirty: boolean, stage: string | null) => [dirty && 'alterações não salvas', stage && `alterações não aplicadas no inspector da etapa ${stage}`].filter(Boolean).join(' e ')
// Relógio lido só em eventos e respostas (posse, histórico), nunca para renderizar.
const eventClock = () => Date.now()
// Uma instância por Pipeline/rascunho/experiência: Montagem e Configuração são
// vistas da mesma sessão; nos demais destinos ela continua montada e oculta.
export function WorkspaceEditor({name,draft,definition:source,layout:sourceLayout,reasons,capabilities,development,tab,configGroup,onConfigGroup,onOpenTab,onSession,onSaved,onDiscarded,actionsHost}:{name:string;actionsHost?:HTMLElement|null;draft:WorkspaceDraft|null;definition:WorkspaceDefinition;layout:WorkspaceLayout;reasons:string[];capabilities:WorkspaceCapabilities;development:boolean;tab:string;configGroup:ConfigurationGroup;onConfigGroup:(group:ConfigurationGroup)=>void;onOpenTab:(tab:'montagem'|'configuracao')=>void;onSession?:(state:WorkspaceSessionState)=>void;onSaved:(draft:WorkspaceDraft)=>void;onDiscarded:()=>void}) {
 // Escopo de overlay herdado: as vistas só o restringem, nunca o reativam.
 const overlayScope=useContext(OverlayScope)
 const [pendingNodeId,setPendingNodeId]=useState<string|null>(null)
 const editorRef=useRef<HTMLDivElement>(null);const [diagnosticRequest,setDiagnosticRequest]=useState<(InspectorDiagnostic&{id:string})|null>(null)
 // Histórico local (patches) e inspector: alterações não aplicadas bloqueiam
 // trocar de etapa sem confirmação; o modo focado expande o inspector sobre o canvas.
 const [history,setHistory]=useState<WorkspaceHistory>(emptyHistory);const historyRef=useRef(history);const [historyNote,setHistoryNote]=useState('')
 // Elemento com foco quando um desfazer/refazer deu certo (consumido no commit seguinte).
 const undoRef=useRef<HTMLButtonElement>(null);const redoRef=useRef<HTMLButtonElement>(null);const canvasRef=useRef<HTMLDivElement>(null);const travelFocus=useRef<Element|null>(null)
 const [staging,setStaging]=useState(false);const stagingRef=useRef(false);const [focused,setFocused]=useState(false);const dragGesture=useRef(0);const [inspectorEpoch,setInspectorEpoch]=useState(0)
 const [layoutKey,setLayoutKey]=useState(0);const [librarySearch,setLibrarySearch]=useState('');const [publicationFrozen,setPublicationFrozen]=useState(false)
 // Painéis recolhíveis: ficam montados e ocultos (busca, inspector, formulário em
 // edição e o canvas com zoom/posição continuam). Biblioteca começa recolhida
 // abaixo de 1024 px para não empilhar antes do canvas.
 const [assemblyView,setAssemblyView]=useState<'grafo'|'lista'>(()=>typeof window!=='undefined'&&window.matchMedia&&window.matchMedia('(max-width: 767px)').matches?'lista':'grafo')
 const panelId=useId();const [libraryOpen,setLibraryOpen]=useState(()=>typeof window==='undefined'||!window.matchMedia||window.matchMedia('(min-width: 1024px)').matches);const [inspectorOpen,setInspectorOpen]=useState(true)
 const [publishHost,setPublishHost]=useState<HTMLDivElement|null>(null)
 const cached=development&&draft?localDrafts.get(draft.draftId):undefined
 const [storedBase,setBase]=useState(cached?.base??draft);const [storedDefinition,setDefinition]=useState(()=>cloneFlow(cached?.definition??source));const [storedLayout,setLayout]=useState(()=>cloneFlow(cached?.layout??sourceLayout));const [dirty,setDirty]=useState(!!cached);const [busy,setBusy]=useState(false);const [lease,setLease]=useState<WorkspaceLease|null>(null);const [selected,setSelected]=useState<string|null>(null);const [issue,setIssue]=useState(cached?'Alterações não salvas foram retomadas nesta aba. Confira a sessão antes de salvar.':'');const [clock,setClock]=useState(()=>Date.now())
 const base=dirty||lease?storedBase:draft
 const definition=development&&draft&&(dirty||lease)?storedDefinition:source
 const layout=development&&draft&&(dirty||lease)?storedLayout:sourceLayout
 const manage=!!base&&base.state==='ativo'&&development&&capabilities.actions.editDraft
 const allowed=manage&&reasons.length===0
 const held=manage&&!!lease&&lease.heldBySession&&Date.parse(lease.expiresAt)>clock
 const editable=allowed&&held&&!busy&&!publicationFrozen
 const currentState=useRef({editable,definition,layout,base,lease,busy,manage,selected})
 useLayoutEffect(()=>{currentState.current={editable,definition,layout,base,lease,busy,manage,selected}})
 useEffect(()=>useAuthStore.subscribe((state,previous)=>{if(state.token!==previous.token){historyRef.current=emptyHistory();setHistory(historyRef.current)}}),[])
 const pendingRef=useRef(false);const renewRef=useRef<()=>void>(()=>{})
 const renew=useMutation({mutationFn:()=>workspaceApi.lease(base!.draftId,lease!.fence),onSuccess:next=>setLease(next),onError:()=>{setLease(null);setIssue('A sessão de edição foi interrompida. Suas alterações continuam nesta aba. Inicie a edição novamente para conferir a revisão.')}})
 const renewMutation=renew.mutate
 useEffect(()=>{renewRef.current=()=>{if(!pendingRef.current)renewMutation()}},[renewMutation])
 const fence=lease?.fence;const expires=lease?.expiresAt
 useEffect(()=>{if(!fence||!expires||!manage)return;const delay=Math.max(5000,Math.min(30000,(Date.parse(expires)-Date.now())/2));const timer=setInterval(()=>renewRef.current(),delay);return()=>clearInterval(timer)},[fence,expires,manage])
 useEffect(()=>{if(base&&development){if(dirty)localDrafts.set(base.draftId,{base,definition,layout});else localDrafts.delete(base.draftId)}},[base,definition,layout,dirty,development])
 useEffect(()=>{const timer=setInterval(()=>setClock(Date.now()),1000);return()=>clearInterval(timer)},[])
 const revision=base?.revision??null
 // Alterações não aplicadas no inspector (só existem enquanto a etapa existe):
 // Salvar não as inclui, mas sair da sessão as perde.
 const unapplied=staging&&!!selected&&definition.nodes.some(n=>n.id===selected)
 useEffect(()=>{onSession?.({dirty,unapplied,editable,revision})},[dirty,unapplied,editable,revision,onSession])
 // Sair da sessão (outro pipeline, fonte ou experiência, voltar, ou fora do
 // Pipeline) com alterações não salvas ou não aplicadas pede confirmação;
 // cancelar mantém tudo. Trocar de destino dentro dela (Montagem↔Configuração)
 // não desmonta e não pergunta. Com a saída confirmada, o cache local deste
 // rascunho é descartado e não volta.
 const guardedDraft=base?.draftId
 useNavigationGuard(dirty||unapplied?{leaves:(from,to)=>!sameWorkspaceSession(name,from,to),message:`Há ${pendingChanges(dirty,unapplied?selected:null)}${unapplied?'':' neste rascunho'}. Sair desta sessão descarta essas alterações. Deseja sair?`,onLeave:()=>{if(guardedDraft)localDrafts.delete(guardedDraft)}}:null)
 // Descarte confirmado do formulário do inspector (recarregar, descartar rascunho).
 function dropInspector(){stagingRef.current=false;setStaging(false);setInspectorEpoch(value=>value+1)}
 function editingCurrentDraft(expected=base,expectedFence=lease?.fence){const state=currentState.current;return state.editable&&Date.parse(state.lease?.expiresAt??'')>eventClock()&&state.base?.draftId===expected?.draftId&&state.base?.revision===expected?.revision&&state.lease?.fence===expectedFence}
 function sameDraftIntent(){const state=currentState.current;return state.base?.draftId===base?.draftId&&state.base?.revision===base?.revision&&!state.busy}
 function commitHistory(next:WorkspaceHistory){historyRef.current=next;setHistory(next);if(next.reset==='protected')setHistoryNote('O histórico de desfazer recomeçou: valores protegidos são gravados no servidor e não são desfeitos localmente.')}
 function clearHistory(){commitHistory(emptyHistory());setHistoryNote('')}
 // Toda alteração local elegível passa por aqui e vira um passo (ou se junta ao gesto/digitação em curso).
 function changed(next:WorkspaceDefinition,nextLayout?:WorkspaceLayout,meta:ChangeMeta={label:'Alteração no fluxo'}){
  const state=currentState.current;if(!state.editable)return
  const layoutNext=nextLayout??state.layout
  setHistoryNote('');commitHistory(recordHistory(historyRef.current,{definition:state.definition,layout:state.layout},{definition:next,layout:layoutNext},{...meta,now:eventClock()}))
  currentState.current={...state,definition:next,layout:layoutNext};setDefinition(next);setLayout(layoutNext);setDirty(true)
 }
 // Alterações não aplicadas só contam enquanto a etapa do inspector existe.
 function inspectorPending(){const state=currentState.current;return stagingRef.current&&state.definition.nodes.some(n=>n.id===state.selected)}
 // Desfazer/refazer: só com a posse vigente e sem alterações pendentes no inspector; marca alterações locais e não toca revisão, posse nem publicação.
 function travel(undo:boolean){
  if(!editingCurrentDraft())return
  if(inspectorPending()){toast.info('Aplique ou descarte as alterações do inspector antes de desfazer ou refazer.');return}
  const state=currentState.current;const result=(undo?undoHistory:redoHistory)(historyRef.current,{definition:state.definition,layout:state.layout})
  if(!result)return
  commitHistory(result.history)
  if(!result.ok){setHistoryNote(result.message);return}
  travelFocus.current=typeof document==='undefined'?null:document.activeElement
  const wanted=result.entry.select?(undo?result.entry.select.before:result.entry.select.after):state.selected
  const keep=wanted&&result.state.definition.nodes.some(n=>n.id===wanted)?wanted:null
  currentState.current={...state,definition:result.state.definition,layout:result.state.layout,selected:keep}
  setDefinition(result.state.definition);setLayout(result.state.layout);setDirty(true);setSelected(keep);if(!keep)setFocused(false)
  setHistoryNote(`${undo?'Desfeito':'Refeito'}: ${result.entry.label}.${state.selected&&!keep?' A etapa selecionada não existe neste ponto; a seleção foi limpa.':''}`)
 }
 // Trocar de etapa com alterações não aplicadas no inspector pede confirmação; cancelar mantém tudo.
 function select(id:string|null,then?:()=>void){
  const next=id||null,opening=currentState.current.selected
  const go=()=>{stagingRef.current=false;setStaging(false);currentState.current={...currentState.current,selected:next};setSelected(next);if(!next)setFocused(false);then?.()}
  if(next===opening){then?.();return}
  if(!inspectorPending()){go();return}
  void confirmAction(`A etapa ${opening} tem alterações não aplicadas no inspector. ${next?`Abrir ${next}`:'Fechar as propriedades'} descarta essas alterações. Continuar?`,()=>currentState.current.selected===opening).then(ok=>{if(ok)go()})
 }
 function patchFromInspector(label:string,merge:(current:WorkspaceDefinition)=>PatchResult<WorkspaceDefinition>):boolean{
  if(!editingCurrentDraft()){toast.info('A sessão de edição mudou. Inicie a edição para aplicar; o formulário continua no inspector.');return false}
  const result=merge(currentState.current.definition)
  if(!result.ok){toast.error(result.message);return false}
  changed(result.value,undefined,{label});return true
 }
 function failure(error:unknown){setLease(null);setIssue(error instanceof Error?error.message:'Não foi possível concluir a operação. Suas alterações continuam nesta aba.')}
 async function begin(transfer=false){
  if(!manage||!base||busy)return
  if(transfer&&!await confirmAction('Assumir a edição interrompe a posse atual. Deseja continuar?',()=>currentState.current.manage&&sameDraftIntent()))return
  pendingRef.current=true;setBusy(true)
  try{
   const current=await workspaceApi.draft(base.draftId)
   if(current.revision!==base.revision&&dirty){setIssue('O rascunho foi alterado por outra sessão. Recarregue para conferir; as alterações desta aba não foram substituídas.');return}
   if(!dirty){setBase(current);setDefinition(cloneFlow(current.definition));setLayout(cloneFlow(current.layout));clearHistory()}
   onSaved(current)
   const next=transfer?await workspaceApi.transfer(current,current.lease?.fence??0):await workspaceApi.lease(current.draftId)
   setLease(next);setIssue('');setClock(eventClock())
  }catch(error){failure(error)}finally{pendingRef.current=false;setBusy(false)}
 }
 const save=useMutation({mutationFn:()=>workspaceApi.save(base!,definition,layout,lease!.fence),onMutate:()=>{pendingRef.current=true;setBusy(true)},onSuccess:next=>{localDrafts.delete(next.draftId);setBase(next);setDefinition(cloneFlow(next.definition));setLayout(cloneFlow(next.layout));setLease(next.lease);setDirty(false);setIssue('');clearHistory();onSaved(next);toast.success('Rascunho salvo');if(stagingRef.current)toast.info('As alterações ainda não aplicadas continuam no inspector.')},onError:failure,onSettled:()=>{pendingRef.current=false;setBusy(false)}})
 // Recarregar substitui também o formulário não aplicado do inspector (com confirmação; só depois de obter o rascunho).
 async function reload(){const opening=currentState.current.selected,pending=inspectorPending();if(!base||busy)return;if((dirty||pending)&&!await confirmAction(`Recarregar substitui ${[dirty&&'as alterações não salvas desta aba',pending&&`as alterações não aplicadas no inspector da etapa ${opening}`].filter(Boolean).join(' e ')}. Continuar?`,()=>!!currentState.current.base&&sameDraftIntent()&&currentState.current.selected===opening))return;try{const next=await workspaceApi.draft(base.draftId);localDrafts.delete(next.draftId);setBase(next);setDefinition(cloneFlow(next.definition));setLayout(cloneFlow(next.layout));setLease(null);setDirty(false);setIssue('');clearHistory();if(pending)dropInspector();onSaved(next)}catch(error){failure(error)}}
 // Encerrar mantém o formulário não aplicado (aplicável ao reiniciar a edição); Descartar o rascunho o descarta. Ambos avisam antes.
 async function release(discard=false){const opening=currentState.current.selected,pending=inspectorPending();if(!base||!lease||busy)return;if((dirty||pending)&&!await confirmAction(`Há ${pendingChanges(dirty,pending?opening:null)}.${pending?discard?' Descartar o rascunho também descarta as alterações do inspector.':' As alterações do inspector continuam no formulário e só podem ser aplicadas depois de iniciar a edição novamente.':''} Deseja encerrar a edição?`,()=>!!currentState.current.lease&&sameDraftIntent()&&currentState.current.lease.fence===lease?.fence&&currentState.current.selected===opening))return;if(discard&&!await confirmAction('Descartar este rascunho? A configuração publicada permanece disponível.',()=>!!currentState.current.lease&&sameDraftIntent()&&currentState.current.lease.fence===lease?.fence))return;pendingRef.current=true;setBusy(true);try{if(discard){await workspaceApi.discard(base,lease.fence);localDrafts.delete(base.draftId);setDirty(false);setLease(null);clearHistory();dropInspector();onDiscarded()}else{await workspaceApi.release(base,lease.fence);setLease(null)}}catch(error){failure(error)}finally{pendingRef.current=false;setBusy(false)}}
 function add(type:string,position?:{x:number;y:number}){if(!editable||!WORKSPACE_TYPES.some(([kind])=>kind===type))return;let index=1;while(definition.nodes.some(n=>n.id===`${type}_${index}`))index++;const id=`${type}_${index}`;changed({...definition,nodes:[...definition.nodes,{id,type,configuration:{legacyJob:{pipeline_name:definition.identity.pipelineName,job_name:id,job_type:type,job_command:null,execution_order:definition.nodes.length+1},etl_pipeline_job_param:[],...(object(definition.metadata).workspaceLineageVersion===1?{etl_job_lineage:[]}: {})}}]},{...layout,nodes:{...layout.nodes,[id]:position??{x:100+(definition.nodes.length%4)*250,y:80+Math.floor(definition.nodes.length/4)*150}}},{label:'Adicionar etapa',select:{before:selected,after:id}});select(id)}
 // Um arraste (vários eventos com dragging, inclusive com várias etapas) é um passo; termina no evento sem dragging.
 function positions(changes:NodeChange[]){
  const state=currentState.current;if(!state.editable)return
  const moves=changes.filter(change=>change.type==='position');const nodes={...state.layout.nodes};let modified=false
  for(const change of moves)if(change.type==='position'&&change.position){nodes[change.id]={...nodes[change.id],x:change.position.x,y:change.position.y};modified=true}
  if(modified)changed(state.definition,{...state.layout,nodes},{label:'Mover etapas',group:`arrastar:${dragGesture.current}`})
  if(moves.some(change=>change.type==='position'&&change.dragging!==true)){dragGesture.current+=1;commitHistory(sealHistory(historyRef.current))}
 }
 function edges(changes:EdgeChange[]){const removed=new Set(changes.filter(c=>c.type==='remove').map(c=>c.id));if(removed.size)changed(removeWorkspaceEdges(definition,removed),undefined,{label:'Remover ligação'})}
 function connect(connection:Connection){if(!editable)return;try{changed(connectWorkspaceDecision(definition,connection.source,connection.target,connection.sourceHandle),undefined,{label:'Conectar etapas'})}catch(error){toast.error(error instanceof Error?error.message:'Dependência inválida')}}
 const node=definition.nodes.find(n=>n.id===selected);const params=pipelineParameters(definition);const owner=lease??draft?.lease??base?.lease
 const focusing=focused&&!!node;const labels=historyLabels(history)
 const publishing=!!base&&development&&capabilities.actions.consultVersions
 // Barra do cabeçalho: sessão e Salvar, depois o encaixe de Validar/Publicar da
 // instância única de publicação (ordem fixa). Publicar é a ação primária quando permitida.
 const actions=(<div className="flex flex-wrap gap-2">{base&&<Button size="sm" variant="secondary" disabled={busy} onClick={reload}><RefreshCw size={14}/>Recarregar</Button>}{manage&&!held&&<Button disabled={busy} size="sm" onClick={()=>begin()}><Pencil size={14}/>{reasons.length?'Gerenciar rascunho':'Iniciar edição'}</Button>}{manage&&!held&&capabilities.actions.administer&&owner&&!owner.heldBySession&&<Button size="sm" variant="secondary" disabled={busy} onClick={()=>begin(true)}>Assumir edição</Button>}{held&&<><Button disabled={busy} size="sm" variant="secondary" onClick={()=>release()}>Encerrar edição</Button>{allowed&&<Button size="sm" variant={publishing&&capabilities.actions.publish?'secondary':'primary'} onClick={()=>save.mutate()} disabled={!dirty||publicationFrozen} loading={save.isPending} title={unapplied?'Salvar grava o que já foi aplicado; as alterações não aplicadas do inspector não entram':undefined}><Save size={14}/>Salvar rascunho</Button>}</>}{publishing&&<div ref={setPublishHost} className="contents"/>}</div>)
 const assembling=tab==='montagem',configuring=tab==='configuracao'
 // Cada vista é montada na primeira visita e mantida, oculta fora do seu
 // destino: formulários, canvas (zoom, posição, seleção), inspector e JSON em
 // edição continuam como estavam. Overlays de uma vista oculta ficam inertes.
 const [configurationMounted,setConfigurationMounted]=useState(configuring)
 if(configuring&&!configurationMounted)setConfigurationMounted(true)
 const [assemblyMounted,setAssemblyMounted]=useState(assembling)
 if(assembling&&!assemblyMounted)setAssemblyMounted(true)
 // O botão de desfazer/refazer que tinha o foco e ficou desabilitado no último passo o
 // perderia para o body, e os atalhos (restritos à Montagem) parariam de responder.
 useLayoutEffect(()=>{
  const trigger=travelFocus.current;if(!trigger)return;travelFocus.current=null
  const target=historyFocusTarget<Element>({trigger,active:document.activeElement,body:document.body,undo:undoRef.current,redo:redoRef.current,canvas:canvasRef.current,disabled:element=>element instanceof HTMLButtonElement&&element.disabled,visible:assembling&&!focusing&&trigger.isConnected,dialogOpen:!!document.querySelector('[role="dialog"]')})
  if(target instanceof HTMLElement)target.focus({preventScroll:true})
 })
 const secretContext=base&&lease?{draftId:base.draftId,expectedRevision:base.revision,fence:lease.fence}:undefined
 // Uma única instância para as duas vistas: validação e comando de publicação não recomeçam.
 const publication=publishing&&<WorkspacePublicationPanel active={assembling||configuring} actionsHost={publishHost} draft={base} fence={held?lease?.fence:undefined} canPublish={capabilities.actions.publish} dirty={dirty} busy={busy} onFreeze={setPublicationFrozen} onConfirmed={reload} onSelect={(id,field,message)=>{if(!assembling)onOpenTab('montagem');select(id,()=>{setInspectorOpen(true);setDiagnosticRequest({id,field,message,key:Date.now(),focus:true})})}}/>
 const configurationStatus=dirty?'Há alterações não salvas neste rascunho. Publicar é uma ação separada.':manage&&!held?'Inicie a edição para alterar a configuração deste rascunho.':base?`Rascunho salvo · revisão ${base.revision}. Publicar é uma ação separada.`:'Configuração publicada em consulta.'
 return <div ref={editorRef} className="space-y-3" hidden={!assembling&&!configuring}>
  {/* Estado da sessão e do salvamento numa só linha (antes em duas), na mesma ordem. */}
  <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
   <div className="text-xs flex flex-wrap items-center gap-x-2 gap-y-1 text-dim">{editable?<UnlockKeyhole size={17}/>:<LockKeyhole size={17}/>}<span>{editable?'Você está editando o rascunho':owner&&Date.parse(owner.expiresAt)>clock?`${owner.holderUser} possui a sessão de edição`:'Modo consulta'}{base&&` · revisão ${base.revision}`} · publicação separada</span><span aria-hidden="true">·</span><span>{dirty?'Alterações ainda não salvas nesta sessão':base?`Último salvamento: ${new Date(base.updatedAt).toLocaleString('pt-BR')}`:'Configuração publicada'} · {definition.nodes.length} etapas{unapplied&&` · Alterações não aplicadas no inspector (${selected}); Salvar não as inclui`}</span></div>
   {base&&<span className="text-xs text-dim">Responsável: {base.responsible}</span>}
   {(assembling||configuring)&&!actionsHost&&actions}
   {(assembling||configuring)&&actionsHost&&createPortal(actions,actionsHost)}
  </div>
  {(issue||!!reasons.length)&&<div role="alert" className="border border-amber-300 bg-amber-50 text-amber-900 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-300 rounded-lg p-3 text-sm">{issue||reasons.join(' · ')}</div>}

  {configurationMounted&&<OverlayScope.Provider value={overlayScope&&configuring}><div hidden={!configuring} className={WORKSPACE_FRAMED_CONTENT}><WorkspaceConfiguration group={configGroup} onGroup={onConfigGroup} definition={definition} editable={editable} onApply={next=>changed(next,undefined,{label:'Configuração do pipeline',group:`configuracao:${configGroup}`,window:TEXT_GROUP_MS})} canApply={()=>editingCurrentDraft()} secretContext={secretContext} responsible={base?.responsible} status={configurationStatus} jsonKey={`${base?.revision}-${editable}`} saveAction={held&&allowed?<Button size="sm" onClick={()=>save.mutate()} disabled={!dirty||publicationFrozen} loading={save.isPending} title={unapplied?'Salvar grava o que já foi aplicado; as alterações não aplicadas do inspector não entram':undefined}><Save size={14}/>Salvar rascunho</Button>:undefined}/></div></OverlayScope.Provider>}

  {assemblyMounted&&<OverlayScope.Provider value={overlayScope&&assembling}><div hidden={!assembling} onKeyDown={event=>{
   // Atalhos só na Montagem visível e fora de campos de texto/diálogos (lá vale o desfazer nativo).
   const dialogOpen=typeof document!=='undefined'&&!!document.querySelector('[role="dialog"]')||inside(event.target,'[role="dialog"]')
   if(event.key==='Escape'&&focusing&&!dialogOpen&&!event.defaultPrevented){event.preventDefault();setFocused(false);return}
   const action=historyShortcut({key:event.key,ctrlKey:event.ctrlKey,metaKey:event.metaKey,shiftKey:event.shiftKey,altKey:event.altKey,isComposing:event.nativeEvent.isComposing,defaultPrevented:event.defaultPrevented},{active:assembling,textTarget:inside(event.target,TEXT_TARGET),dialogOpen})
   if(action){event.preventDefault();travel(action==='undo')}
  }}><div className={`grid gap-3 ${ASSEMBLY_COLUMNS[focusing?'none':libraryOpen?inspectorOpen?'both':'library':inspectorOpen?'inspector':'none']}`}>
   {/* No desktop os painéis não definem a altura da linha (contain:size) e rolam por dentro; o canvas define. */}
   <aside id={`${panelId}-componentes`} hidden={!libraryOpen||focusing} className="border border-edge rounded-lg bg-panel p-3 lg:[contain:size] lg:overflow-y-auto"><h2 className="text-sm font-semibold text-ink mb-3">Componentes</h2><Input label="Buscar componente" value={librarySearch} onChange={e=>setLibrarySearch(e.target.value)} className="mb-3"/>{[['Integração',['datastage','sql','python','shell','storedproc','http']],['Controle',['decisao','aguarde']],['Entrega',['valida_arquivo','notificacao','email']]].map(([group,kinds])=><div key={String(group)} className="mb-4"><h3 className="text-xs font-medium text-dim mb-2">{group}</h3><div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-1 gap-2">{WORKSPACE_TYPES.filter(([type,label])=>(kinds as string[]).includes(type)&&label.toLocaleLowerCase().includes(librarySearch.toLocaleLowerCase())).map(([type,label,Icon])=><button key={type} type="button" disabled={!editable} draggable={editable} onDragStart={event=>{if(!editable){event.preventDefault();return}event.dataTransfer.setData(WORKSPACE_COMPONENT_MIME,type);event.dataTransfer.effectAllowed='copy'}} onClick={()=>add(type)} className="ui-button ui-button-small flex items-center gap-2 px-2 py-2 text-left rounded border border-edge text-ink hover:bg-edge/20 cursor-grab active:cursor-grabbing focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-600 disabled:opacity-60 disabled:cursor-not-allowed"><Icon size={15} className="text-blue-700 dark:text-blue-400 shrink-0"/>{label}</button>)}</div></div>)}<p className="text-xs text-dim mt-4">{editable?'Clique ou arraste para adicionar uma etapa.':'Tipos de etapa disponíveis no workspace.'}</p></aside>
   {/* Localizar etapa passou da linha própria para a barra do canvas, na mesma ordem (depois do título). */}
   <section hidden={focusing} className="border border-edge rounded-lg bg-panel min-w-0 overflow-hidden"><div className="flex flex-wrap items-center gap-2 px-3 py-2 border-b border-edge"><button type="button" aria-label="Componentes" title={libraryOpen?'Recolher componentes':'Mostrar componentes'} aria-expanded={libraryOpen} aria-controls={`${panelId}-componentes`} onClick={()=>setLibraryOpen(open=>!open)} className={`${PANEL_TOGGLE} ${panelToggleTone(libraryOpen)}`}>{libraryOpen?<PanelLeftClose size={15}/>:<PanelLeftOpen size={15}/>}<span className="lg:hidden xl:inline">Componentes</span></button><h2 className="text-sm font-semibold text-ink">{development?'Fluxo em montagem':base?'Fluxo do rascunho':'Fluxo publicado'}</h2><div role="group" aria-label="Visualização da montagem" className="flex rounded-md border border-edge p-0.5">{(['grafo','lista'] as const).map(view=><button type="button" key={view} aria-pressed={assemblyView===view} onClick={()=>setAssemblyView(view)} className={`ui-button ui-button-small rounded px-2 ${assemblyView===view?'bg-info-surface text-info':'text-dim hover:text-ink'}`}>{view==='grafo'?'Desenho':'Lista'}</button>)}</div>{development&&<div className="flex items-center gap-0.5"><button ref={undoRef} type="button" aria-label="Desfazer" title={staging&&node?'Aplique ou descarte as alterações do inspector antes de desfazer':labels.undo?`Desfazer: ${labels.undo} (Ctrl+Z)`:'Nada para desfazer desde o último salvamento'} aria-keyshortcuts="Control+Z Meta+Z" disabled={!editable||!labels.undo} onClick={()=>travel(true)} className={HISTORY_BUTTON}><Undo2 size={15}/></button><button ref={redoRef} type="button" aria-label="Refazer" title={staging&&node?'Aplique ou descarte as alterações do inspector antes de refazer':labels.redo?`Refazer: ${labels.redo} (Ctrl+Shift+Z)`:'Nada para refazer'} aria-keyshortcuts="Control+Shift+Z Control+Y Meta+Shift+Z" disabled={!editable||!labels.redo} onClick={()=>travel(false)} className={HISTORY_BUTTON}><Redo2 size={15}/></button></div>}<div className="ml-auto flex flex-wrap items-center gap-2"><Select aria-label="Localizar etapa no fluxo" value={selected??''} onChange={e=>select(e.target.value||null)} className="w-44 xl:w-56"><option value="">Localizar etapa…</option>{definition.nodes.map(n=><option key={n.id} value={n.id}>{n.id} · {typeLabel(n.type)}</option>)}</Select><Button size="sm" variant="secondary" disabled={!editable||!definition.nodes.length} onClick={()=>{changed(definition,arrangeWorkspace(definition,layout),{label:'Organizar desenho'});setLayoutKey(v=>v+1)}}><GitBranch size={13}/>Organizar</Button><span className="text-xs text-dim">{editable?'Montagem':'Somente leitura'}</span><button type="button" aria-label="Propriedades" title={inspectorOpen?'Recolher propriedades':'Mostrar propriedades'} aria-expanded={inspectorOpen} aria-controls={`${panelId}-propriedades`} onClick={()=>setInspectorOpen(open=>!open)} className={`${PANEL_TOGGLE} ${panelToggleTone(inspectorOpen)}`}><span className="lg:hidden xl:inline">Propriedades</span>{inspectorOpen?<PanelRightClose size={15}/>:<PanelRightOpen size={15}/>}</button></div></div>{historyNote&&<p role="status" className="border-b border-edge px-3 py-1.5 text-xs text-dim">{historyNote}</p>}<div hidden={assemblyView!=='grafo'}><WorkspaceCanvas key={layoutKey} focusRef={canvasRef} definition={definition} layout={layout} editable={editable} selected={selected} onSelect={id=>select(id)} onPositions={changes=>positions(changes)} onRemoveEdge={changes=>edges(changes)} onConnect={connection=>connect(connection)} onRequestRemoveNode={setPendingNodeId} onDropComponent={(type,position)=>add(type,position)}/></div><div hidden={assemblyView!=='lista'} className="min-h-[320px] p-3"><p className="ui-help mb-3">Selecione uma etapa para consultar ou configurar. As dependências são as mesmas do desenho.</p><ul aria-label="Etapas da montagem" className="divide-y divide-edge">{definition.nodes.map(row=><li key={row.id}><button type="button" onClick={()=>select(row.id,()=>setInspectorOpen(true))} aria-pressed={selected===row.id} className={`w-full rounded-md p-3 text-left [overflow-wrap:anywhere] ${selected===row.id?'bg-info-surface text-info':'text-ink hover:bg-canvas'}`}><span className="block text-sm font-semibold">{row.id}</span><span className="block text-xs text-dim mt-1">{typeLabel(row.type)} · Entradas: {definition.edges.filter(edge=>edge.target===row.id).map(edge=>edge.source).join(', ')||'Início'}</span></button></li>)}</ul>{!definition.nodes.length&&<p className="text-sm text-dim">Adicione uma etapa pela biblioteca de componentes para iniciar.</p>}</div>
   </section>
   {/* Modo focado: o inspector ocupa a área do canvas (oculto, com zoom e seleção) na mesma posição da árvore; nada é remontado. */}
   <div id={`${panelId}-propriedades`} hidden={!inspectorOpen&&!focusing} className={focusing?'min-w-0 lg:min-h-[max(470px,calc(100dvh-26rem))] [&>aside]:min-h-full lg:[&>aside]:mx-auto lg:[&>aside]:max-w-5xl':'min-w-0 lg:[contain:size] lg:overflow-y-auto [&>aside]:min-h-full'}><OverlayScope.Provider value={overlayScope&&assembling&&(inspectorOpen||focusing)}>
   {!node&&<aside className="border border-edge rounded-lg bg-panel p-4 min-w-0"><h2 className="text-sm font-semibold text-ink">Propriedades da etapa</h2><p className="text-sm text-dim mt-3">Selecione uma etapa no fluxo para consultar sua configuração.</p><dl className="mt-6 space-y-4 text-sm"><div><dt className="text-dim">Pipeline</dt><dd className="text-ink break-all">{definition.identity.pipelineName}</dd></div><div><dt className="text-dim">Componentes</dt><dd className="text-ink">{definition.nodes.length}</dd></div><div><dt className="text-dim">Conexões</dt><dd className="text-ink">{definition.edges.length}</dd></div></dl></aside>}
   {node&&<NodeProperties secretContext={secretContext} key={`${node.id}:${inspectorEpoch}`} node={node} definition={definition} editable={editable} defaults={params as unknown as JobParamApi[]} canApply={()=>editingCurrentDraft()} diagnostic={diagnosticRequest?.id===node.id?diagnosticRequest:undefined} onDiagnosticFocus={()=>setDiagnosticRequest(request=>request?.focus?{...request,focus:false}:request)} focused={focusing} onToggleFocus={()=>setFocused(value=>!value)} onStaging={dirty=>{stagingRef.current=dirty;setStaging(dirty)}} onClose={()=>select(null)}
    onRename={id=>{if(inspectorPending()){toast.info('Aplique ou descarte as alterações do inspector antes de renomear.');return}try{const current=currentState.current;if(!current.editable||!current.definition.nodes.some(row=>row.id===node.id))return;const next=renameWorkspaceNode(current.definition,current.layout,node.id,id);changed(next.definition,next.layout,{label:'Renomear etapa',select:{before:node.id,after:id}});currentState.current={...currentState.current,selected:id};setSelected(id)}catch(e){toast.error(e instanceof Error?e.message:'Não foi possível renomear')}}}
    onChange={(next,field)=>{const current=currentState.current;if(current.editable&&current.definition.nodes.some(n=>n.id===next.id))changed({...current.definition,nodes:current.definition.nodes.map(n=>n.id===next.id?next:n)},undefined,field?{label:field==='displayName'?'Editar nome da etapa':field==='execution_order'?'Alterar ordem de execução':'Editar etapa',group:`campo:${next.id}:${field}`,window:TEXT_GROUP_MS}:{label:'Editar etapa'})}}
    onPatchNode={(previous,next,label)=>patchFromInspector(label,current=>mergeNodePatch(current,previous,next))} onPatchDefinition={(previous,next,label)=>patchFromInspector(label,current=>mergeDefinitionPatch(current,previous,next))} onDelete={()=>setPendingNodeId(node.id)}/>}
   </OverlayScope.Provider></div>
  </div></div></OverlayScope.Provider>}
  {publication&&<div className={configuring?WORKSPACE_FRAMED_CONTENT:undefined}>{publication}</div>}
  {assemblyMounted&&<OverlayScope.Provider value={overlayScope&&assembling}><div hidden={!assembling}>
  <section aria-label="Ferramentas do fluxo" className="flex flex-wrap items-start gap-2"><WorkspaceFlowTools definition={definition} editable={editable} canApply={()=>editingCurrentDraft()} onApply={next=>{if(editingCurrentDraft())changed(next,undefined,{label:next.nodes.length>currentState.current.definition.nodes.length?'Importar etapas':'Ordenar execução'})}}/><WorkspaceJsonTools key={`${base?.revision}-${editable}`} mode="import" definition={definition} editable={editable} onApply={next=>changed(next,undefined,{label:'Importar etapas em lote'})}/></section>
  <Modal open={pendingNodeId!==null} onClose={()=>setPendingNodeId(null)} title="Remover etapa" size="sm"><p className="text-sm text-ink [overflow-wrap:anywhere]">Remover a etapa {pendingNodeId} e suas ligações do rascunho?</p><p className="text-xs text-dim mt-2">A configuração publicada permanece disponível.</p><div className="flex justify-end gap-3 mt-5"><Button variant="secondary" onClick={()=>setPendingNodeId(null)}>Cancelar</Button><Button variant="danger" disabled={!editable} onClick={()=>{if(pendingNodeId){const next=removeWorkspaceNode(definition,layout,pendingNodeId);changed(next.definition,next.layout,{label:'Remover etapa',select:{before:pendingNodeId,after:null}});if(pendingNodeId===selected){stagingRef.current=false;setStaging(false);currentState.current={...currentState.current,selected:null};setSelected(null);setFocused(false)}}setPendingNodeId(null)}}>Remover etapa</Button></div></Modal>
  </div></OverlayScope.Provider>}
  {held&&base&&<div className={`flex justify-end ${configuring?WORKSPACE_FRAMED_CONTENT:''}`}><Button variant="ghost" size="sm" disabled={busy||publicationFrozen} onClick={()=>release(true)}>Descartar rascunho</Button></div>}
 </div>
}
