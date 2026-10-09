import { useMemo } from 'react'
import { ReactFlow, Background, Controls, Handle, Position, MarkerType, type Node, type NodeProps, type NodeChange, type EdgeChange, type Connection } from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { Box, GitBranch } from 'lucide-react'
import type { WorkspaceDefinition, WorkspaceLayout } from '../../lib/workspace'
import { nodeLabel } from '../../lib/workspace'
import { WORKSPACE_TYPES, typeLabel } from './workspaceCatalog'
type CanvasNode = Node<{ label: string; kind: string }, 'workspace'>
function WorkspaceNodeView({ data, selected }: NodeProps<CanvasNode>) {
 const Icon=WORKSPACE_TYPES.find(t=>t[0]===data.kind)?.[2] ?? Box
 return <div className={`min-w-44 max-w-64 rounded-lg bg-panel border px-4 py-3 ${selected?'border-blue-600 dark:border-blue-400':'border-edge'}`}>
  <Handle type="target" position={Position.Left} />
  <div className="flex items-center gap-3"><Icon size={20} className="text-blue-700 dark:text-blue-400 shrink-0"/><div className="min-w-0"><div className="text-sm font-semibold text-ink break-words">{data.label}</div><div className="text-xs text-dim mt-1">{typeLabel(data.kind)}</div></div></div>
  <Handle type="source" position={Position.Right} />
 </div>
}
const nodeTypes={workspace:WorkspaceNodeView}
export function WorkspaceCanvas({definition,layout,editable,selected,onSelect,onPositions,onRemoveEdge,onConnect}:{definition:WorkspaceDefinition;layout:WorkspaceLayout;editable:boolean;selected:string|null;onSelect:(id:string)=>void;onPositions:(changes:NodeChange[])=>void;onRemoveEdge:(changes:EdgeChange[])=>void;onConnect:(connection:Connection)=>void}) {
 const nodes=useMemo<CanvasNode[]>(()=>definition.nodes.map((node,index)=>({id:node.id,type:'workspace',position:layout.nodes[node.id]??{x:80+(index%4)*250,y:80+Math.floor(index/4)*150},data:{label:nodeLabel(node),kind:node.type},selected:node.id===selected})),[definition.nodes,layout.nodes,selected])
 const edges=useMemo(()=>definition.edges.map((edge,index)=>({id:String(index),source:edge.source,target:edge.target,label:typeof edge.branch==='string'?edge.branch:undefined,markerEnd:{type:MarkerType.ArrowClosed},style:{stroke:'rgb(var(--dim))'}})),[definition.edges])
 return <div className="relative h-[440px] lg:h-[540px] bg-canvas rounded-b-lg [--xy-controls-button-background-color:rgb(var(--panel))] [--xy-controls-button-background-color-hover:rgb(var(--edge))] [--xy-controls-button-color:rgb(var(--ink))] [--xy-controls-button-border-color:rgb(var(--edge))] [--xy-edge-label-background-color:rgb(var(--panel))] [--xy-edge-label-color:rgb(var(--ink))]" aria-label={editable?'Canvas de montagem do rascunho':'Canvas em modo consulta'}>
  <ReactFlow key={selected===null?'overview':'properties'} nodes={nodes} edges={edges} nodeTypes={nodeTypes} onNodeClick={(_,node)=>onSelect(node.id)} onNodesChange={editable?onPositions:undefined} onEdgesChange={editable?onRemoveEdge:undefined} onConnect={editable?onConnect:undefined} nodesDraggable={editable} nodesConnectable={editable} edgesReconnectable={false} deleteKeyCode={null} fitView minZoom={0.2} maxZoom={2} ariaLabelConfig={{'controls.zoomIn.ariaLabel':'Ampliar','controls.zoomOut.ariaLabel':'Reduzir','controls.fitView.ariaLabel':'Enquadrar fluxo','node.a11yDescription.default':'Etapa. Pressione Enter para selecionar.'}}>
   <Background color="rgb(var(--edge))" gap={20}/><Controls showInteractive={false}/>
  </ReactFlow>
  {!definition.nodes.length&&<div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none px-6 text-center"><GitBranch size={36} className="text-dim mb-4"/><h3 className="text-base font-semibold text-ink">Seu fluxo começa aqui</h3><p className="text-sm text-dim mt-2 max-w-sm">{editable?'Adicione uma etapa na biblioteca e conecte os componentes.':'Este fluxo ainda não tem etapas.'}</p></div>}
 </div>
}
