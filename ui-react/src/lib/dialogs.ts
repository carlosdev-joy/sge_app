export type DialogRequest = { id:number; kind:'confirm'|'text'; message:string; initialValue:string; allowed:()=>boolean; resolve:(value:boolean|string|null)=>void }
let sequence=0
let current:DialogRequest|null=null
const listeners=new Set<()=>void>()
const queue:DialogRequest[]=[]
const emit=()=>listeners.forEach(listener=>listener())
export const subscribeDialogs=(listener:()=>void)=>{listeners.add(listener);return()=>{listeners.delete(listener)}}
export const currentDialog=()=>current
export function finishDialog(value:boolean|string|null){const request=current;current=queue.shift()??null;emit();request?.resolve(value!==null&&request.allowed()?value:null)}
export function cancelDialogs(){const requests=[...(current?[current]:[]),...queue];current=null;queue.length=0;emit();requests.forEach(request=>request.resolve(null))}
function enqueue(request:Omit<DialogRequest,'id'>){const next={...request,id:++sequence};if(current)queue.push(next);else current=next;emit()}
export function confirmAction(message:string,allowed:()=>boolean=()=>true):Promise<boolean>{return new Promise(resolve=>enqueue({kind:'confirm',message,initialValue:'',allowed,resolve:value=>resolve(value===true)}))}
export function requestText(message:string,initialValue='',allowed:()=>boolean=()=>true):Promise<string|null>{return new Promise(resolve=>enqueue({kind:'text',message,initialValue,allowed,resolve:value=>resolve(typeof value==='string'?value:null)}))}
