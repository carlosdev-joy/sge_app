import { useEffect, useMemo } from 'react'
import { ReactFlow, Background, Controls, MarkerType, type Node, type NodeChange, type EdgeChange, type Connection, useReactFlow } from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { GitBranch } from 'lucide-react'
import type { WorkspaceDefinition, WorkspaceLayout } from '../../lib/workspace'
import { nodeLabel } from '../../lib/workspace'
import { WorkspaceFlowNode } from './WorkspaceFlowNode'
import { decisionCondition, decisionEdgeHandle } from '../../lib/workspaceDecision'
import { arrangeWorkspace } from '../../lib/workspaceLayout'
type CanvasNode = Node<{ label: string; kind: string; condition:Record<string,unknown>;hasPlainDependency:boolean }, 'workspace'>
const nodeTypes={workspace:WorkspaceFlowNode}
function FocusOnMobile({selected}:{selected:string|null}) {
 const flow=useReactFlow()
 useEffect(()=>{if(selected&&window.matchMedia('(max-width:1023px)').matches)flow.fitView({nodes:[{id:selected}],minZoom:0.8,maxZoom:1,padding:0.2,duration:200})},[selected,flow])
 return null
}
export function WorkspaceCanvas({definition,layout,editable,selected,onSelect,onPositions,onRemoveEdge,onConnect}:{definition:WorkspaceDefinition;layout:WorkspaceLayout;editable:boolean;selected:string|null;onSelect:(id:string)=>void;onPositions:(changes:NodeChange[])=>void;onRemoveEdge:(changes:EdgeChange[])=>void;onConnect:(connection:Connection)=>void}) {
 const automatic=useMemo(()=>arrangeWorkspace(definition,layout),[definition,layout])
 const nodes=useMemo<CanvasNode[]>(()=>definition.nodes.map(node=>({id:node.id,type:'workspace',position:layout.nodes[node.id]??automatic.nodes[node.id],data:{label:nodeLabel(node),kind:node.type,condition:decisionCondition(node),hasPlainDependency:node.type==='decisao'&&definition.edges.some(e=>e.source===node.id&&!decisionEdgeHandle(node,e))},selected:node.id===selected})),[definition.nodes,definition.edges,layout.nodes,selected,automatic])
 const edges=useMemo(()=>definition.edges.map((edge,index)=>({id:String(index),source:edge.source,target:edge.target,type:'smoothstep',sourceHandle:definition.nodes.find(n=>n.id===edge.source)?.type==='decisao'?decisionEdgeHandle(definition.nodes.find(n=>n.id===edge.source)!,edge)??'legacy':undefined,label:typeof edge.branch==='string'?edge.branch:undefined,markerEnd:{type:MarkerType.ArrowClosed},style:{stroke:'rgb(var(--dim))'}})),[definition.edges,definition.nodes])
 return <div className="relative h-[420px] lg:h-[470px] bg-canvas rounded-b-lg [--xy-controls-button-background-color:rgb(var(--panel))] [--xy-controls-button-background-color-hover:rgb(var(--edge))] [--xy-controls-button-color:rgb(var(--ink))] [--xy-controls-button-border-color:rgb(var(--edge))] [--xy-edge-label-background-color:rgb(var(--panel))] [--xy-edge-label-color:rgb(var(--ink))]" aria-label={editable?'Canvas de montagem do rascunho':'Canvas em modo consulta'}>
  <ReactFlow nodes={nodes} edges={edges} nodeTypes={nodeTypes} onNodeClick={(_,node)=>onSelect(node.id)} onNodesChange={editable?onPositions:undefined} onEdgesChange={editable?onRemoveEdge:undefined} onConnect={editable?onConnect:undefined} onEdgeDoubleClick={editable?(_,edge)=>{if(window.confirm('Remover esta ligação do rascunho?'))onRemoveEdge([{id:edge.id,type:'remove'}])}:undefined} nodesDraggable={editable} nodesConnectable={editable} edgesReconnectable={false} deleteKeyCode={null} fitView fitViewOptions={{padding:0.12,maxZoom:1,minZoom:0.7}} minZoom={0.2} maxZoom={2} ariaLabelConfig={{'controls.zoomIn.ariaLabel':'Ampliar','controls.zoomOut.ariaLabel':'Reduzir','controls.fitView.ariaLabel':'Enquadrar fluxo','node.a11yDescription.default':'Etapa. Pressione Enter para selecionar.'}}>
   <FocusOnMobile selected={selected}/><Background color="rgb(var(--edge))" gap={20}/><Controls showInteractive={false}/>
  </ReactFlow>
  {!definition.nodes.length&&<div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none px-6 text-center"><GitBranch size={36} className="text-dim mb-4"/><h3 className="text-base font-semibold text-ink">Seu fluxo começa aqui</h3><p className="text-sm text-dim mt-2 max-w-sm">{editable?'Adicione uma etapa na biblioteca e conecte os componentes.':'Este fluxo ainda não tem etapas.'}</p></div>}
 </div>
}
