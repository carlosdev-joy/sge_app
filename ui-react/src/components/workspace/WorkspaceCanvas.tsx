import { useEffect, useMemo, useRef, useState, type RefObject } from 'react'
import { ReactFlow, Background, Controls, MarkerType, type Node, type NodeChange, type EdgeChange, type Connection, type ReactFlowInstance, useReactFlow, useStoreApi } from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { Button } from '../ui/Button'
import { Modal } from '../ui/Modal'
import { GitBranch } from 'lucide-react'
import type { WorkspaceDefinition, WorkspaceLayout } from '../../lib/workspace'
import { nodeLabel } from '../../lib/workspace'
import { WorkspaceFlowNode } from './WorkspaceFlowNode'
import { decisionCondition, decisionEdgeHandle } from '../../lib/workspaceDecision'
import { WORKSPACE_COMPONENT_MIME, WORKSPACE_TYPES } from './workspaceCatalog'
import { arrangeWorkspace } from '../../lib/workspaceLayout'
import { NO_TELEMETRY, edgeRunState, runStateFor, workspaceEdgeId, type NodeRunState } from '../../lib/workspaceExecution'
import { fitViewDuration, nodeForEnter } from '../../lib/workspaceCanvasA11y'
type CanvasNode = Node<{ label: string; kind: string; condition:Record<string,unknown>;hasPlainDependency:boolean;run?:NodeRunState|null }, 'workspace'>
// Camada operacional (Execução): estado por etapa, cadeia em destaque e foco pedido pelo localizador.
export interface CanvasRunLayer { states: Map<string, NodeRunState> | null; highlight?: { nodes: Set<string>; edges: Set<string> } | null }
// Fora da cadeia em destaque: mesmo esmaecido medido do realce legado (texto legível, sem cor).
const DIMMED_NODE = { opacity: 0.65, filter: 'grayscale(0.8)' }
const EDGE_RUN_STYLE = { observed: { stroke: 'rgb(var(--ink))', strokeWidth: 2.25 }, unknown: { stroke: 'rgb(var(--dim))', strokeWidth: 1.5 }, skipped: { stroke: 'rgb(var(--dim))', strokeWidth: 1.5, strokeDasharray: '6 5', opacity: 0.4 } }
const edgeId=workspaceEdgeId
const nodeTypes={workspace:WorkspaceFlowNode}
const motion=()=>fitViewDuration(query=>window.matchMedia(query))
function FocusOnMobile({selected,request}:{selected:string|null;request?:{id:string;seq:number}|null}) {
 const flow=useReactFlow();const store=useStoreApi()
 // Canvas conservado oculto (sem caixa de layout) não é reenquadrado: o zoom do usuário fica.
 useEffect(()=>{if(selected&&!!store.getState().domNode?.getClientRects().length&&window.matchMedia('(max-width:1023px)').matches)flow.fitView({nodes:[{id:selected}],minZoom:0.8,maxZoom:1,padding:0.2,duration:motion()})},[selected,flow,store])
 // Localizar etapa: centraliza a etapa pedida em qualquer largura (pedido explícito, não a cada atualização).
 useEffect(()=>{if(request&&!!store.getState().domNode?.getClientRects().length&&store.getState().nodeLookup.has(request.id))flow.fitView({nodes:[{id:request.id}],minZoom:0.8,maxZoom:1,padding:0.3,duration:motion()})},[request,flow,store])
 return null
}
export function WorkspaceCanvas({focusRef,definition,layout,editable,selected,onSelect,onPositions,onRemoveEdge,onConnect,onRequestRemoveNode,onDropComponent,run,focusRequest,label,heightClass}:{focusRef?:RefObject<HTMLDivElement|null>;definition:WorkspaceDefinition;layout:WorkspaceLayout;editable:boolean;selected:string|null;onSelect:(id:string)=>void;onPositions?:(changes:NodeChange[])=>void;onRemoveEdge?:(changes:EdgeChange[])=>void;onConnect?:(connection:Connection)=>void;onRequestRemoveNode?:(id:string)=>void;onDropComponent?:(type:string,position:{x:number;y:number})=>void;run?:CanvasRunLayer|null;focusRequest?:{id:string;seq:number}|null;label?:string;heightClass?:string}) {
 const flowRef=useRef<Pick<ReactFlowInstance,'screenToFlowPosition'>|null>(null)
 // O editor pode receber o elemento focável do canvas (devolução de foco após desfazer/refazer).
 const ownRef=useRef<HTMLDivElement>(null);const canvasRef=focusRef??ownRef
 const [selectedEdge,setSelectedEdge]=useState<string|null>(null);const [confirmEdge,setConfirmEdge]=useState(false)
 // A seleção de etapa também pode vir do localizador ou de um diagnóstico.
 if(selected&&selectedEdge!==null)setSelectedEdge(null)
 const chosen=selectedEdge===null?null:definition.edges.find(edge=>edgeId(edge)===selectedEdge)
 const automatic=useMemo(()=>arrangeWorkspace(definition,layout),[definition,layout])
 const states=run?.states??null;const highlight=run?.highlight??null
 // Medidas devolvidas pelo React Flow. Nó recriado sem elas (seleção, estados da corrida)
 // fica invisível até remedir, e a etapa focada perde o foco para o documento.
 const [measured,setMeasured]=useState<Record<string,{width:number;height:number}>>({})
 function nodesChange(changes:NodeChange[]){
  setMeasured(current=>{let next=current;for(const change of changes)if(change.type==='dimensions'&&change.dimensions&&(current[change.id]?.width!==change.dimensions.width||current[change.id]?.height!==change.dimensions.height)){if(next===current)next={...current};next[change.id]=change.dimensions}return next})
  if(editable)onPositions?.(changes)
 }
 const baseNodes=useMemo<CanvasNode[]>(()=>definition.nodes.map(node=>({id:node.id,type:'workspace',position:layout.nodes[node.id]??automatic.nodes[node.id],data:{label:nodeLabel(node),kind:node.type,condition:decisionCondition(node),hasPlainDependency:node.type==='decisao'&&definition.edges.some(e=>e.source===node.id&&!decisionEdgeHandle(node,e)),...(run?{run:states?runStateFor(states,node.id)??NO_TELEMETRY:null}:{})},selected:false,measured:measured[node.id],...(highlight&&!highlight.nodes.has(node.id)?{style:DIMMED_NODE}:{})})),[definition.nodes,definition.edges,layout.nodes,automatic,run,states,highlight,measured])
 const nodes=useMemo(()=>baseNodes.map(node=>node.id===selected?{...node,selected:true}:node),[baseNodes,selected])
 const edges=useMemo(()=>definition.edges.map(edge=>({id:edgeId(edge),source:edge.source,target:edge.target,type:'smoothstep',sourceHandle:definition.nodes.find(n=>n.id===edge.source)?.type==='decisao'?decisionEdgeHandle(definition.nodes.find(n=>n.id===edge.source)!,edge)??'legacy':undefined,label:typeof edge.branch==='string'?edge.branch:undefined,markerEnd:{type:MarkerType.ArrowClosed},selected:edgeId(edge)===selectedEdge,style:edgeId(edge)===selectedEdge?{stroke:'rgb(var(--workspace-edge-selected))',strokeWidth:3}:run?{...EDGE_RUN_STYLE[edgeRunState(runStateFor(states,edge.source),runStateFor(states,edge.target))],...(highlight&&!highlight.edges.has(edgeId(edge))?{opacity:0.15}:{})}:{stroke:'rgb(var(--dim))',strokeWidth:1.5}})),[definition.edges,definition.nodes,selectedEdge,run,states,highlight])
 return <div ref={canvasRef} onDragOver={event=>{if(!editable||!event.dataTransfer.types.includes(WORKSPACE_COMPONENT_MIME)||document.querySelector('[role="dialog"]'))return;event.preventDefault();event.dataTransfer.dropEffect='copy'}} onDrop={event=>{
   if(!editable||!flowRef.current||document.querySelector('[role="dialog"]')||!(event.target instanceof Element)||!event.target.closest('.react-flow'))return
   const type=event.dataTransfer.getData(WORKSPACE_COMPONENT_MIME)
   if(!WORKSPACE_TYPES.some(([kind])=>kind===type))return
   event.preventDefault()
   const position=flowRef.current.screenToFlowPosition({x:event.clientX,y:event.clientY})
   if(!Number.isFinite(position.x)||!Number.isFinite(position.y))return
   onDropComponent?.(type,position);canvasRef.current?.focus({preventScroll:true})
  }} tabIndex={0} aria-keyshortcuts="Delete" onKeyDownCapture={event=>{
   // Enter na etapa focada seleciona como o clique (inspector e URL) e o foco fica nela; a seleção interna do ReactFlow não recebe a tecla.
   const id=nodeForEnter(event.nativeEvent,event.target instanceof Element?event.target:null,id=>definition.nodes.some(node=>node.id===id),!!document.querySelector('[role="dialog"]'))
   if(!id)return
   event.preventDefault();event.stopPropagation();setSelectedEdge(null);onSelect(id)
  }} onKeyDown={event=>{
   if(event.key!=='Delete'||!editable||event.defaultPrevented||event.repeat||event.nativeEvent.isComposing||event.ctrlKey||event.altKey||event.metaKey||event.shiftKey)return
   const target=event.target
   if(target instanceof Element&&target.closest('input,textarea,select,button,a,[contenteditable]:not([contenteditable="false"]),[role="dialog"]'))return
   if(document.querySelector('[role="dialog"]'))return
   if(chosen){event.preventDefault();setConfirmEdge(true)}
   else if(selected&&definition.nodes.some(node=>node.id===selected)){event.preventDefault();onRequestRemoveNode?.(selected)}
  }} className={`relative ${heightClass??'h-[420px] lg:h-[max(470px,calc(100dvh-26rem))]'} bg-canvas rounded-b-lg [--workspace-edge-selected:37,99,235] dark:[--workspace-edge-selected:96,165,250] [--xy-controls-button-background-color:rgb(var(--panel))] [--xy-controls-button-background-color-hover:rgb(var(--edge))] [--xy-controls-button-color:rgb(var(--ink))] [--xy-controls-button-border-color:rgb(var(--edge))] [--xy-edge-label-background-color:rgb(var(--panel))] [--xy-edge-label-color:rgb(var(--ink))]`} aria-label={label??(editable?'Canvas de montagem do rascunho':'Canvas em modo consulta')}>
  <ReactFlow onInit={flow=>{flowRef.current=flow}} nodes={nodes} edges={edges} nodeTypes={nodeTypes} onNodeClick={(_,node)=>{setSelectedEdge(null);onSelect(node.id);canvasRef.current?.focus({preventScroll:true})}} onEdgeClick={(_,edge)=>{setSelectedEdge(edge.id);onSelect('');canvasRef.current?.focus({preventScroll:true})}} onPaneClick={()=>{setSelectedEdge(null);onSelect('')}} onNodesChange={nodesChange} onEdgesChange={changes=>{for(const change of changes)if(change.type==='select'&&change.selected){setSelectedEdge(change.id);onSelect('')}}} onConnect={editable?onConnect:undefined} onEdgeDoubleClick={editable?(_,edge)=>{setSelectedEdge(edge.id);setConfirmEdge(true)}:undefined} nodesDraggable={editable} nodesConnectable={editable} edgesReconnectable={false} deleteKeyCode={null} fitView fitViewOptions={{padding:0.12,maxZoom:1,minZoom:0.7}} minZoom={0.2} maxZoom={2} ariaLabelConfig={{'controls.zoomIn.ariaLabel':'Ampliar','controls.zoomOut.ariaLabel':'Reduzir','controls.fitView.ariaLabel':'Enquadrar fluxo','node.a11yDescription.default':'Etapa. Pressione Enter para selecionar.'}}>
   <FocusOnMobile selected={selected} request={focusRequest}/><Background color="rgb(var(--edge))" gap={20}/><Controls showInteractive={false}/>
  </ReactFlow>
  {chosen&&<div className="absolute top-3 left-3 right-3 flex items-center justify-between gap-3 rounded-md border border-edge bg-panel px-3 py-2"><p className="text-xs text-ink min-w-0 [overflow-wrap:anywhere]">Ligação selecionada: {chosen.source} → {chosen.target}</p>{editable&&<Button size="sm" variant="danger" onClick={()=>setConfirmEdge(true)}>Remover ligação</Button>}</div>}
  <Modal open={confirmEdge&&!!chosen} onClose={()=>setConfirmEdge(false)} title="Remover ligação" size="sm"><p className="text-sm text-ink [overflow-wrap:anywhere]">Remover a ligação de {chosen?.source} para {chosen?.target} do rascunho?</p><p className="text-xs text-dim mt-2">A configuração publicada permanece disponível.</p><div className="flex justify-end gap-3 mt-5"><Button variant="secondary" onClick={()=>setConfirmEdge(false)}>Cancelar</Button><Button variant="danger" disabled={!editable} onClick={()=>{const index=definition.edges.findIndex(edge=>edgeId(edge)===selectedEdge);if(index>=0)onRemoveEdge?.([{id:String(index),type:'remove'}]);setSelectedEdge(null);setConfirmEdge(false)}}>Remover ligação</Button></div></Modal>
  {!definition.nodes.length&&<div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none px-6 text-center"><GitBranch size={36} className="text-dim mb-4"/><h3 className="text-base font-semibold text-ink">Seu fluxo começa aqui</h3><p className="text-sm text-dim mt-2 max-w-sm">{editable?'Adicione uma etapa na biblioteca e conecte os componentes.':'Este fluxo ainda não tem etapas.'}</p></div>}
 </div>
}
