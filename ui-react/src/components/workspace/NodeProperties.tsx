import { useState } from 'react'
import { Button } from '../ui/Button'
import { Input, Textarea } from '../ui/Input'
import { encryptedParameter, nodeLabel, object, patchLegacy, text, type JsonObject, type WorkspaceNode } from '../../lib/workspace'
import { typeLabel } from './workspaceCatalog'
import { Trash2, X } from 'lucide-react'
function AdvancedConfiguration({node,editable,onApply,onClose}:{node:WorkspaceNode;editable:boolean;onApply:(configuration:JsonObject)=>void;onClose:()=>void}) {
 const [value,setValue]=useState(()=>JSON.stringify(node.configuration,null,2));const [error,setError]=useState('')
 function apply(){try{const parsed:unknown=JSON.parse(value);if(!parsed||Array.isArray(parsed)||typeof parsed!=='object')throw new Error();onApply(object(parsed));onClose()}catch{setError('Use um objeto JSON válido. Os valores protegidos devem continuar por referência.')}}
 return <div className="space-y-3"><Textarea label="Configuração completa" value={value} onChange={e=>setValue(e.target.value)} readOnly={!editable} rows={15} className="font-mono text-xs" error={error}/><p className="text-xs text-dim">Campos adicionais são preservados. Use identificadores de conexão; valores protegidos permanecem na origem.</p><div className="flex gap-2">{editable&&<Button onClick={apply}>Aplicar configuração</Button>}<Button variant="secondary" onClick={onClose}>Voltar</Button></div></div>
}
export function NodeProperties({node,editable,onChange,onDelete,onClose}:{node:WorkspaceNode;editable:boolean;onChange:(node:WorkspaceNode)=>void;onDelete:()=>void;onClose:()=>void}) {
 const [advanced,setAdvanced]=useState(false);const legacy=object(node.configuration.legacyJob);const rows=Array.isArray(node.configuration.etl_pipeline_job_param)?node.configuration.etl_pipeline_job_param.map(object):[]
 function field(key:string,value:string){onChange(patchLegacy(node,key,value))}
 return <aside className="bg-panel border border-edge rounded-lg p-4 min-w-0" aria-label="Propriedades da etapa">
  <div className="flex items-start justify-between gap-2 mb-5"><div className="min-w-0"><h3 className="font-semibold text-sm text-ink break-words">{nodeLabel(node)}</h3><p className="text-xs text-dim mt-1">{typeLabel(node.type)}</p></div><Button variant="ghost" size="sm" aria-label="Fechar propriedades" onClick={onClose}><X size={16}/></Button></div>
  {advanced?<AdvancedConfiguration node={node} editable={editable} onApply={configuration=>onChange({...node,configuration})} onClose={()=>setAdvanced(false)}/>:<div className="space-y-4">
   <Input label="Nome para exibição" value={text(node.displayName)||node.id} readOnly={!editable} onChange={e=>onChange({...node,displayName:e.target.value})}/>
   <Input label="Identificador da etapa" value={node.id} readOnly className="font-mono"/>
   <Textarea label={node.type==='datastage'?'Comando do job':'Comando / código'} value={text(legacy.job_command)} readOnly={!editable} onChange={e=>field('job_command',e.target.value)} rows={4}/>
   <Input label="Conexão SSH (identificador)" value={text(legacy.ssh_conn_id)} readOnly={!editable} onChange={e=>field('ssh_conn_id',e.target.value)}/>
   {['sql','storedproc','email','python'].includes(node.type)&&<><Input label="Conexão SQL (identificador)" value={text(legacy.mssql_conn_id)} readOnly={!editable} onChange={e=>field('mssql_conn_id',e.target.value)}/><Input label="Banco de dados" value={text(legacy.mssql_database)} readOnly={!editable} onChange={e=>field('mssql_database',e.target.value)}/></>}
   {!!rows.length&&<div className="border-t border-edge pt-4"><h4 className="text-sm font-medium text-ink mb-3">Parâmetros da etapa</h4><div className="space-y-3">{rows.map((row,index)=>encryptedParameter(row)?<div key={index} className="text-xs text-dim"><span className="font-medium text-ink">{text(row.param_name)}</span><p>Valor protegido na origem</p></div>:<Input key={index} label={text(row.param_name)} value={text(row.param_value)} readOnly={!editable} onChange={e=>onChange({...node,configuration:{...node.configuration,etl_pipeline_job_param:rows.map((r,i)=>i===index?{...r,param_value:e.target.value}:r)}})}/>)}</div></div>}
   <Button variant="secondary" className="w-full justify-center" onClick={()=>setAdvanced(true)}>Configurações avançadas</Button>
   {editable&&<Button variant="danger" size="sm" onClick={onDelete}><Trash2 size={14}/>Remover etapa</Button>}
  </div>}
 </aside>
}
