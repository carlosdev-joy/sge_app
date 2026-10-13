import { memo } from 'react'
import { Handle, Position, type NodeProps } from '@xyflow/react'
import { Box, PauseCircle } from 'lucide-react'
import { WORKSPACE_TYPES, typeLabel } from './workspaceCatalog'
import { object, text } from '../../lib/workspace'
import type { NodeRunKind, NodeRunState } from '../../lib/workspaceExecution'
import { RunStateIcon } from './WorkspaceRunStatus'

// Borda pelo estado da corrida; a seleção usa anel externo e nunca apaga o estado.
const RUN_BORDER: Record<NodeRunKind, string> = {
 none: 'border-edge', unknown: 'border-slate-400 dark:border-slate-500',
 running: 'border-blue-600 dark:border-blue-400', success: 'border-green-600 dark:border-green-500',
 failed: 'border-red-600 dark:border-red-400', gate: 'border-amber-500 dark:border-amber-400',
 skipped: 'border-dashed border-slate-400 dark:border-slate-500',
}
export const WorkspaceFlowNode = memo(function WorkspaceFlowNode({data,selected,type,isConnectable}:NodeProps) {
 const kind=text(data.kind)||text(data.type)||(type==='etapa'?'datastage':type??'')
 const Icon=WORKSPACE_TYPES.find(t=>t[0]===kind)?.[2]??Box
 const run=data.run as NodeRunState|null|undefined
 const condition=object(data.condition);const cases=Array.isArray(condition.casos)?condition.casos.map(object):null
 const handles=kind==='decisao'?(cases?[...cases.map(c=>'caso:'+text(c.nome)),'senao']:['sim','nao']):['']
 const border=run?RUN_BORDER[run.kind]:selected?'border-blue-600 dark:border-blue-400':'border-edge'
 return <div className={`w-[176px] min-h-[64px] rounded-md border bg-panel px-3 py-2 transition-[border-color,box-shadow] duration-200 motion-reduce:transition-none ${border} ${run&&selected?'ring-2 ring-blue-600 ring-offset-2 ring-offset-canvas dark:ring-blue-400':''} ${run?.kind==='skipped'?'opacity-75':''}`}>
  <Handle type="target" position={Position.Left} isConnectable={isConnectable} className="!h-2.5 !w-2.5 !bg-dim !border-panel"/>
  <div className="flex items-center gap-2"><Icon size={19} className="shrink-0 text-blue-700 dark:text-blue-400"/><div className="min-w-0 flex-1"><p className="text-sm font-semibold text-ink line-clamp-2 [overflow-wrap:anywhere]" title={text(data.name)||text(data.label)}>{(text(data.name)||text(data.label)).replace(/_/g,'_​')}</p><p className="text-xs text-dim mt-0.5">{typeLabel(kind)}</p></div></div>
  {run&&<div title={run.detail} className="mt-2 border-t border-edge pt-1.5 space-y-0.5"><p className="flex items-center gap-1.5 text-xs text-ink"><RunStateIcon kind={run.kind} animate={run.animate}/><span className="min-w-0 [overflow-wrap:anywhere]">{run.label}</span>{run.attempts>1&&<span className="ml-auto shrink-0 text-dim tabular-nums" title="Tentativa operacional (registro do Orquestra); as do motor ficam na investigação">tent. {run.attempt??run.attempts}</span>}</p>{run.pauseMarked&&<p className="flex items-center gap-1.5 text-xs text-fuchsia-700 dark:text-fuchsia-300"><PauseCircle size={13} aria-hidden="true" className="shrink-0"/>Pausa marcada</p>}</div>}
  {data.hasPlainDependency===true&&<Handle id="legacy" type="source" position={Position.Right} isConnectable={false} style={{top:'90%'}}/>}
  {handles.map((handle,index)=><Handle key={handle} id={handle||undefined} type="source" position={Position.Right} isConnectable={isConnectable} style={{top:`${(index+1)*100/(handles.length+1)}%`}} className="!h-2.5 !w-2.5 !bg-dim !border-panel"/>)}
 </div>
})
