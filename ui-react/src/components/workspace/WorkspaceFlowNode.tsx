import { Handle, Position, type NodeProps } from '@xyflow/react'
import { Box } from 'lucide-react'
import { WORKSPACE_TYPES, typeLabel } from './workspaceCatalog'
import { object, text } from '../../lib/workspace'
import type { ExecNoEtapa } from '../etapas/execucaoEtapas'

export function WorkspaceFlowNode({data,selected,type,isConnectable}:NodeProps) {
 const kind=text(data.kind)||text(data.type)||(type==='etapa'?'datastage':type??'')
 const Icon=WORKSPACE_TYPES.find(t=>t[0]===kind)?.[2]??Box
 const exec=data.exec as ExecNoEtapa|null|undefined
 const condition=object(data.condition);const cases=Array.isArray(condition.casos)?condition.casos.map(object):null
 const handles=kind==='decisao'?(cases?[...cases.map(c=>'caso:'+text(c.nome)),'senao']:['sim','nao']):['']
 return <div className={`w-[176px] min-h-[64px] rounded-md border bg-panel px-3 py-2 ${selected?'border-blue-600 dark:border-blue-400':exec?.status==='SUCCESS'?'border-green-600 dark:border-green-500':exec?.status==='FAILED'?'border-red-600 dark:border-red-400':'border-edge'}`}>
  <Handle type="target" position={Position.Left} isConnectable={isConnectable} className="!h-2.5 !w-2.5 !bg-dim !border-panel"/>
  <div className="flex items-center gap-2"><Icon size={19} className="shrink-0 text-blue-700 dark:text-blue-400"/><div className="min-w-0"><p className="text-sm font-semibold text-ink break-normal">{(text(data.name)||text(data.label)).replace(/_/g,'_\u200b')}</p><p className="text-xs text-dim mt-0.5">{typeLabel(kind)}</p></div></div>
  {exec&&<div title={exec.titulo} className="mt-2 border-t border-edge pt-1.5"><p className="flex items-center gap-1.5 text-[11px] text-dim"><span className={`h-2 w-2 rounded-full ${exec.dot}`}/>{exec.rotulo}</p>{exec.status&&<p className="text-[10px] text-dim mt-0.5">{exec.resumo}</p>}</div>}
  {data.hasPlainDependency===true&&<Handle id="legacy" type="source" position={Position.Right} isConnectable={false} style={{top:'90%'}}/>}
  {handles.map((handle,index)=><Handle key={handle} id={handle||undefined} type="source" position={Position.Right} isConnectable={isConnectable} style={{top:`${(index+1)*100/(handles.length+1)}%`}} className="!h-2.5 !w-2.5 !bg-dim !border-panel"/>)}
 </div>
}
