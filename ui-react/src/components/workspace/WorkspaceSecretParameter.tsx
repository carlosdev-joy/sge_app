import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { apiFetch } from '../../lib/api'
import { object, text, type JsonObject, type WorkspaceDefinition } from '../../lib/workspace'
import { Button } from '../ui/Button'
import { Input } from '../ui/Input'
import { toast } from '../ui/Toast'

export interface SecretContext { draftId: string; expectedRevision: number; fence: number }
export function WorkspaceSecretParameter({definition,context,jobName=null,row,canApply,onApply,onClose}:{definition:WorkspaceDefinition;context:SecretContext;jobName?:string|null;row?:JsonObject;canApply:()=>boolean;onApply:(row:JsonObject)=>void;onClose:()=>void}) {
 const [name,setName]=useState(text(row?.param_name));const [value,setValue]=useState('');const [busy,setBusy]=useState(false)
 const mounted=useRef(true);useEffect(()=>{mounted.current=true;return()=>{mounted.current=false}},[])
 const current=useRef({canApply,context,definition})
 useLayoutEffect(()=>{current.current={canApply,context,definition}})
 async function protect(){
  if(busy||!current.current.canApply())return
  const opening=current.current;setBusy(true)
  try{
   const response=await apiFetch<{secretReference:JsonObject}>(`/workspace-adapter/secrets/${encodeURIComponent(context.draftId)}`,{method:'POST',body:JSON.stringify({...context,parameterName:name,jobName,value})})
   if(!mounted.current)return
   setValue('')
   if(!current.current.canApply()||current.current.definition!==opening.definition||current.current.context.draftId!==opening.context.draftId||current.current.context.expectedRevision!==opening.context.expectedRevision||current.current.context.fence!==opening.context.fence){toast.info('A sessão mudou. O valor não foi aplicado ao rascunho.');return}
   onApply({...object(row),pipeline_name:definition.identity.pipelineName,...(jobName?{job_name:jobName}:{}),param_name:name,param_type:'Encrypted',param_source:'fixo',param_value:'***',param_offset_meses:null,param_offset_dias:null,param_ancora:null,param_formato:null,secretReference:response.secretReference,tem_valor:true});onClose()
  }catch(error){if(!mounted.current)return;setValue('');toast.error(error instanceof Error?error.message:'Não foi possível proteger o valor.')}finally{if(mounted.current)setBusy(false)}
 }
 return <div className="space-y-4"><p className="text-sm text-dim">O valor será cifrado fora do rascunho. Apenas a referência será aplicada; publicação continua sendo uma ação separada.</p><Input label="Nome do parâmetro protegido" value={name} readOnly={!!row||busy||!canApply()} maxLength={128} onChange={e=>setName(e.target.value)} ajuda={row?'O nome identifica a referência histórica e permanece preservado.':undefined}/><Input label="Valor protegido" type="password" autoComplete="new-password" value={value} disabled={busy||!canApply()} onChange={e=>setValue(e.target.value)} ajuda="O valor não será exibido novamente."/><div className="flex justify-end gap-2 border-t border-edge pt-4"><Button variant="secondary" onClick={()=>{setValue('');onClose()}}>Cancelar</Button><Button disabled={!name||!value||value==='***'||busy||!canApply()} loading={busy} onClick={protect}>Proteger e aplicar referência</Button></div></div>
}
