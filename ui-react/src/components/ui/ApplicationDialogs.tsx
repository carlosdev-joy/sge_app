import { useEffect, useState, useSyncExternalStore } from 'react'
import { useLocation } from 'react-router-dom'
import { useAuthStore } from '../../store/auth'
import { cancelDialogs, currentDialog, finishDialog, subscribeDialogs, type DialogRequest } from '../../lib/dialogs'
import { Modal } from './Modal'
import { Button } from './Button'
import { Input } from './Input'
function DialogContent({request}:{request:DialogRequest}){
 const [value,setValue]=useState(request.initialValue)
 return <Modal open onClose={()=>finishDialog(null)} title={request.kind==='confirm'?'Confirmar ação':'Informar valor'} size="sm"><form onSubmit={event=>{event.preventDefault();finishDialog(request.kind==='text'?value:true)}}>
  {request.kind==='text'?<Input autoFocus label={request.message} value={value} onChange={event=>setValue(event.target.value)} maxLength={200}/>:<p className="text-sm text-ink whitespace-pre-wrap [overflow-wrap:anywhere]">{request.message}</p>}
  <div className="flex justify-end gap-3 mt-5"><Button type="button" variant="secondary" onClick={()=>finishDialog(null)}>Cancelar</Button><Button type="submit">{request.kind==='text'?'Aplicar':'Confirmar'}</Button></div>
 </form></Modal>
}
export function ApplicationDialogs(){
 const request=useSyncExternalStore(subscribeDialogs,currentDialog,currentDialog)
 const location=useLocation();const token=useAuthStore(state=>state.token)
 // A mudança de tela/sessão cancela intenções antigas; nunca executar uma ação atrasada.
 useEffect(()=>()=>cancelDialogs(),[location.key,token])
 return request?<DialogContent key={request.id} request={request}/>:null
}
