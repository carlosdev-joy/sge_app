import { useEffect, useMemo, useRef, useState } from 'react'
import { ReactFlow, Background, Controls, MarkerType, type Node, type NodeChange, type EdgeChange, type Connection, useReactFlow } from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { Button } from '../ui/Button'
import { Modal } from '../ui/Modal'
import { GitBranch } from 'lucide-react'
import type { WorkspaceDefinition, WorkspaceLayout } from '../../lib/workspace'
import { nodeLabel } from '../../lib/workspace'
import { WorkspaceFlowNode } from './WorkspaceFlowNode'
import { decisionCondition, decisionEdgeHandle } from '../../lib/workspaceDecision'
import { arrangeWorkspace } from '../../lib/workspaceLayout'
type CanvasNode = Node<{ label: string; kind: string; condition:Record<string,unknown>;hasPlainDependency:boolean }, 'workspace'>
const edgeId=(edge:WorkspaceDefinition['edges'][number])=>JSON.stringify([edge.source,edge.target,edge.branch??null])
const nodeTypes={workspace:WorkspaceFlowNode}
function FocusOnMobile({selected}:{selected:string|null}) {
 const flow=useReactFlow()
 useEffect(()=>{if(selected&&window.matchMedia('(max-width:1023px)').matches)flow.fitView({nodes:[{id:selected}],minZoom:0.8,maxZoom:1,padding:0.2,duration:200})},[selected,flow])
 return null
}
export function WorkspaceCanvas({definition,layout,editable,selected,onSelect,onPositions,onRemoveEdge,onConnect,onRequestRemoveNode}:{definition:WorkspaceDefinition;layout:WorkspaceLayout;editable:boolean;selected:string|null;onSelect:(id:string)=>void;onPositions:(changes:NodeChange[])=>void;onRemoveEdge:(changes:EdgeChange[])=>void;onConnect:(connection:Connection)=>void;onRequestRemoveNode:(id:string)=>void}) {
 const canvasRef=useRef<HTMLDivElement>(null)
 const [selectedEdge,setSelectedEdge]=useState<string|null>(null);const [confirmEdge,setConfirmEdge]=useState(false)
 // A seleção de etapa também pode vir do localizador ou de um diagnóstico.
 if(selected&&selectedEdge!==null)setSelectedEdge(null)
 const chosen=selectedEdge===null?null:definition.edges.find(edge=>edgeId(edge)===selectedEdge)
 const automatic=useMemo(()=>arrangeWorkspace(definition,layout),[definition,layout])
 const nodes=useMemo<CanvasNode[]>(()=>definition.nodes.map(node=>({id:node.id,type:'workspace',position:layout.nodes[node.id]??automatic.nodes[node.id],data:{label:nodeLabel(node),kind:node.type,condition:decisionCondition(node),hasPlainDependency:node.type==='decisao'&&definition.edges.some(e=>e.source===node.id&&!decisionEdgeHandle(node,e))},selected:node.id===selected})),[definition.nodes,definition.edges,layout.nodes,selected,automatic])
 const edges=useMemo(()=>definition.edges.map(edge=>({id:edgeId(edge),source:edge.source,target:edge.target,type:'smoothstep',sourceHandle:definition.nodes.find(n=>n.id===edge.source)?.type==='decisao'?decisionEdgeHandle(definition.nodes.find(n=>n.id===edge.source)!,edge)??'legacy':undefined,label:typeof edge.branch==='string'?edge.branch:undefined,markerEnd:{type:MarkerType.ArrowClosed},selected:edgeId(edge)===selectedEdge,style:{stroke:edgeId(edge)===selectedEdge?'rgb(var(--workspace-edge-selected))':'rgb(var(--dim))',strokeWidth:edgeId(edge)===selectedEdge?3:1.5}})),[definition.edges,definition.nodes,selectedEdge])
 return <div ref={canvasRef} tabIndex={0} aria-keyshortcuts="Delete" onKeyDown={event=>{
   if(event.key!=='Delete'||!editable||event.defaultPrevented||event.repeat||event.nativeEvent.isComposing||event.ctrlKey||event.altKey||event.metaKey||event.shiftKey)return
   const target=event.target
   if(target instanceof Element&&target.closest('input,textarea,select,button,a,[contenteditable]:not([contenteditable="false"]),[role="dialog"]'))return
   if(document.querySelector('[role="dialog"]'))return
   if(chosen){event.preventDefault();setConfirmEdge(true)}
   else if(selected&&definition.nodes.some(node=>node.id===selected)){event.preventDefault();onRequestRemoveNode(selected)}
  }} className="relative h-[420px] lg:h-[470px] bg-canvas rounded-b-lg [--workspace-edge-selected:37,99,235] dark:[--workspace-edge-selected:96,165,250] [--xy-controls-button-background-color:rgb(var(--panel))] [--xy-controls-button-background-color-hover:rgb(var(--edge))] [--xy-controls-button-color:rgb(var(--ink))] [--xy-controls-button-border-color:rgb(var(--edge))] [--xy-edge-label-background-color:rgb(var(--panel))] [--xy-edge-label-color:rgb(var(--ink))]" aria-label={editable?'Canvas de montagem do rascunho':'Canvas em modo consulta'}>
  <ReactFlow nodes={nodes} edges={edges} nodeTypes={nodeTypes} onNodeClick={(_,node)=>{setSelectedEdge(null);onSelect(node.id);canvasRef.current?.focus({preventScroll:true})}} onEdgeClick={(_,edge)=>{setSelectedEdge(edge.id);onSelect('');canvasRef.current?.focus({preventScroll:true})}} onPaneClick={()=>{setSelectedEdge(null);onSelect('')}} onNodesChange={editable?onPositions:undefined} onEdgesChange={changes=>{for(const change of changes)if(change.type==='select'&&change.selected){setSelectedEdge(change.id);onSelect('')}}} onConnect={editable?onConnect:undefined} onEdgeDoubleClick={editable?(_,edge)=>{setSelectedEdge(edge.id);setConfirmEdge(true)}:undefined} nodesDraggable={editable} nodesConnectable={editable} edgesReconnectable={false} deleteKeyCode={null} fitView fitViewOptions={{padding:0.12,maxZoom:1,minZoom:0.7}} minZoom={0.2} maxZoom={2} ariaLabelConfig={{'controls.zoomIn.ariaLabel':'Ampliar','controls.zoomOut.ariaLabel':'Reduzir','controls.fitView.ariaLabel':'Enquadrar fluxo','node.a11yDescription.default':'Etapa. Pressione Enter para selecionar.'}}>
   <FocusOnMobile selected={selected}/><Background color="rgb(var(--edge))" gap={20}/><Controls showInteractive={false}/>
  </ReactFlow>
  {chosen&&<div className="absolute top-3 left-3 right-3 flex items-center justify-between gap-3 rounded-md border border-edge bg-panel px-3 py-2"><p className="text-xs text-ink min-w-0 [overflow-wrap:anywhere]">Ligação selecionada: {chosen.source} → {chosen.target}</p>{editable&&<Button size="sm" variant="danger" onClick={()=>setConfirmEdge(true)}>Remover ligação</Button>}</div>}
  <Modal open={confirmEdge&&!!chosen} onClose={()=>setConfirmEdge(false)} title="Remover ligação" size="sm"><p className="text-sm text-ink [overflow-wrap:anywhere]">Remover a ligação de {chosen?.source} para {chosen?.target} do rascunho?</p><p className="text-xs text-dim mt-2">A configuração publicada permanece disponível.</p><div className="flex justify-end gap-3 mt-5"><Button variant="secondary" onClick={()=>setConfirmEdge(false)}>Cancelar</Button><Button variant="danger" disabled={!editable} onClick={()=>{const index=definition.edges.findIndex(edge=>edgeId(edge)===selectedEdge);if(index>=0)onRemoveEdge([{id:String(index),type:'remove'}]);setSelectedEdge(null);setConfirmEdge(false)}}>Remover ligação</Button></div></Modal>
  {!definition.nodes.length&&<div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none px-6 text-center"><GitBranch size={36} className="text-dim mb-4"/><h3 className="text-base font-semibold text-ink">Seu fluxo começa aqui</h3><p className="text-sm text-dim mt-2 max-w-sm">{editable?'Adicione uma etapa na biblioteca e conecte os componentes.':'Este fluxo ainda não tem etapas.'}</p></div>}
 </div>
}
