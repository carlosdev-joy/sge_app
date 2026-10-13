import { WorkspaceCatalogFields } from '../components/workspace/WorkspacePipelineFields'
import { useId, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, ArrowRight, FilePlus2, Info } from 'lucide-react'
import { Input, Textarea } from '../components/ui/Input'
import { Button } from '../components/ui/Button'
import { PageSpinner } from '../components/ui/Spinner'
import { toast } from '../components/ui/Toast'
import { useWorkspaceCapabilities } from '../components/workspace/useWorkspaceCapabilities'
import { initialWorkspace, technicalSuggestion, workspacePath } from '../lib/workspace'
import { workspaceApi } from '../lib/workspaceApi'
import { createConflict, createFieldErrors, DESCRIPTION_MAX, type CreateFieldErrors } from '../lib/pipelineIndex'
import type { ErroApi } from '../lib/api'
import { useAuthStore } from '../store/auth'

// Criação essencial (F2): nome, identificador, projeto/domínio do catálogo e descrição.
// Agenda, parâmetros, políticas e notificações ficam na Configuração do pipeline.
export default function PipelineCreate(){
 const capabilities=useWorkspaceCapabilities();const navigate=useNavigate();const queryClient=useQueryClient();const user=useAuthStore(s=>s.user)
 const [name,setName]=useState('');const [identifier,setIdentifier]=useState('');const [custom,setCustom]=useState(false);const [project,setProject]=useState('');const [domain,setDomain]=useState('');const [description,setDescription]=useState('')
 const [submitted,setSubmitted]=useState(false);const [conflict,setConflict]=useState<string|null>(null);const [failure,setFailure]=useState('')
 const ids={name:useId(),identifier:useId(),description:useId()}
 const technical=custom?identifier:technicalSuggestion(name)
 const errors:CreateFieldErrors={...createFieldErrors({name,identifier:technical,description}),...(conflict?{identifier:conflict}:{})}
 const visible=submitted||!!conflict?errors:{}
 const create=useMutation({mutationFn:()=>{const flow=initialWorkspace(technical,name.trim(),project,domain,description.trim());return workspaceApi.create(flow.definition,flow.layout)},
  onSuccess:draft=>{void queryClient.invalidateQueries({queryKey:['pipeline-index']});toast.success('Rascunho criado. Nenhuma DAG foi criada ou disparada.');navigate(workspacePath(draft.pipelineName,'montagem','desenvolvimento'))},
  onError:error=>{const known=createConflict(error as ErroApi);if(known){setConflict(known);document.getElementById(ids.identifier)?.focus()}else{const api=error as ErroApi;setFailure(api.status&&typeof api.detail==='string'?`${api.detail} Seus dados continuam no formulário.`:'Não foi possível criar o rascunho agora. Seus dados continuam no formulário.')}}})
 if(capabilities.isPending)return <PageSpinner/>
 if(!capabilities.data?.enabled||!capabilities.data.actions.editDraft)return <section className="space-y-4"><h1 className="text-xl font-semibold text-ink">Criação de rascunho indisponível</h1><p className="text-sm text-dim">{capabilities.isError?'Não foi possível consultar o workspace. A lista de pipelines continua disponível.':'Sua sessão não tem a capacidade de criar rascunhos neste ambiente.'}</p><Link to="/pipelines" className="text-blue-700 dark:text-blue-400 underline">Voltar aos pipelines</Link></section>
 const order:(keyof CreateFieldErrors)[]=['name','identifier','description']
 const listed=order.filter(key=>visible[key])
 function submit(event:React.FormEvent){event.preventDefault();setSubmitted(true);setFailure('');const first=order.find(key=>errors[key]);if(first){document.getElementById(ids[first])?.focus();return}create.mutate()}
 const responsible=[user?.primeiro_nome,user?.ultimo_nome].filter(Boolean).join(' ')||user?.matricula||'Sua sessão'
 return <div className="space-y-5"><nav aria-label="Caminho" className="text-sm text-dim"><Link to="/pipelines" className="hover:underline">Pipelines</Link><span className="mx-2" aria-hidden>/</span><span className="text-ink">Novo pipeline</span></nav>
  <header><h1 className="text-2xl font-semibold text-ink">Criar pipeline</h1><p className="text-sm text-dim mt-1">Comece pelo essencial. As etapas e as demais configurações ficam no espaço de trabalho.</p></header>
  <form noValidate onSubmit={submit} className="grid lg:grid-cols-[minmax(0,1fr)_340px] gap-5 items-start">
   <section aria-labelledby={`${ids.name}-titulo`} className="bg-panel border border-edge rounded-lg p-5 space-y-5">
    <div><h2 id={`${ids.name}-titulo`} className="text-base font-semibold text-ink">Informações do pipeline</h2><p className="text-xs text-dim mt-1">Campos com * são obrigatórios.</p></div>
    {listed.length>0&&<div role="alert" className="rounded-md border px-3 py-2 text-sm bg-red-50 border-red-200 text-red-800 dark:bg-red-900/20 dark:border-red-800 dark:text-red-300"><p className="font-medium flex items-center gap-2"><AlertTriangle size={14} aria-hidden/>Revise {listed.length===1?'o campo destacado':`os ${listed.length} campos destacados`}</p><ul className="mt-1 space-y-0.5">{listed.map(key=><li key={key}><button type="button" className="underline underline-offset-2 text-left" onClick={()=>document.getElementById(ids[key])?.focus()}>{{name:'Nome',identifier:'Identificador',description:'Descrição'}[key]}: {visible[key]}</button></li>)}</ul></div>}
    <div className="grid sm:grid-cols-2 gap-5">
     <Input id={ids.name} label="Nome *" required maxLength={200} value={name} onChange={e=>setName(e.target.value)} error={visible.name} aria-invalid={!!visible.name} ajuda="Um nome fácil de reconhecer na operação." autoFocus/>
     <div className="flex flex-col gap-1">
      <Input id={ids.identifier} label="Identificador técnico *" required maxLength={200} readOnly={!custom} value={technical} onChange={e=>{setConflict(null);setIdentifier(e.target.value)}} error={visible.identifier} aria-invalid={!!visible.identifier} className={`font-mono ${custom?'':'bg-canvas text-dim'}`} ajuda={custom?'Preservado exatamente como informado; não pode ser renomeado depois.':'Gerado a partir do nome. Não pode ser renomeado depois de criado.'}/>
      {!custom&&<button type="button" className="self-start text-xs text-blue-700 dark:text-blue-400 hover:underline underline-offset-2 rounded focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500" onClick={()=>{setIdentifier(technical);setCustom(true);setConflict(null);setTimeout(()=>document.getElementById(ids.identifier)?.focus(),0)}}>Editar identificador</button>}
      {conflict&&<Link to={`/pipelines?${new URLSearchParams({busca:technical})}`} className="self-start text-xs text-blue-700 dark:text-blue-400 underline underline-offset-2">Encontrar o existente na lista</Link>}
     </div>
     <WorkspaceCatalogFields project={project} domain={domain} editable={!create.isPending} onChange={(field,value)=>field==='project_name'?setProject(value):setDomain(value)}/>
    </div>
    <div className="flex flex-col gap-1"><Textarea id={ids.description} label="Descrição" rows={3} maxLength={DESCRIPTION_MAX} value={description} onChange={e=>setDescription(e.target.value)} error={visible.description} aria-invalid={!!visible.description} placeholder="O que este pipeline entrega e para quem."/><span className="text-xs text-dim self-end tabular-nums" aria-hidden>{description.length}/{DESCRIPTION_MAX}</span></div>
    <div className="border-t border-edge pt-5 space-y-3"><h3 className="text-sm font-semibold text-ink">Como começar</h3>
     <div className="flex items-start gap-3 rounded-lg border border-blue-300 bg-blue-50 px-4 py-3 dark:border-blue-800 dark:bg-blue-900/20"><FilePlus2 size={18} aria-hidden className="mt-0.5 text-blue-700 dark:text-blue-400 shrink-0"/><div><p className="text-sm font-medium text-ink">Fluxo em branco</p><p className="text-sm text-dim">Você adiciona e conecta as etapas na Montagem, logo após criar.</p></div></div>
     <p className="text-sm text-dim">Agenda, parâmetros, tentativas e notificações são definidos na <span className="text-ink">Configuração</span> do pipeline, depois de criar. Sem agenda, ele começa como execução sob demanda.</p>
    </div>
    {failure&&<p role="alert" className="text-sm rounded-md border px-3 py-2 bg-red-50 border-red-200 text-red-800 dark:bg-red-900/20 dark:border-red-800 dark:text-red-300">{failure}</p>}
    <div className="flex flex-wrap justify-end gap-3 pt-1 border-t border-edge"><Link to="/pipelines" className="text-sm text-dim px-3 py-2 mt-3 hover:underline rounded focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500">Cancelar</Link><Button type="submit" loading={create.isPending} className="mt-3">Criar e abrir montagem<ArrowRight size={16} aria-hidden/></Button></div>
   </section>
   <aside aria-label="Resumo do pipeline" className="bg-panel border border-edge rounded-lg p-5 space-y-5 lg:sticky lg:top-4">
    <div><h2 className="text-lg font-semibold text-ink break-words">{name.trim()||'Seu novo pipeline'}</h2><p className="font-mono text-xs text-dim mt-1 break-all">{technical||'identificador_do_pipeline'}</p></div>
    <dl className="text-sm space-y-2.5">{[['Projeto',project||'Não definido'],['Domínio',domain||'Não definido'],['Responsável',responsible],['Execução','Sob demanda'],['Estado inicial','Rascunho']].map(([label,value])=><div key={label} className="flex gap-3 justify-between"><dt className="text-dim">{label}</dt><dd className="text-ink text-right break-words min-w-0">{value}</dd></div>)}</dl>
    <div className="flex gap-2 rounded-md border px-3 py-2.5 text-sm bg-blue-50 border-blue-200 text-blue-800 dark:bg-blue-900/20 dark:border-blue-800 dark:text-blue-300"><Info size={16} aria-hidden className="mt-0.5 shrink-0"/><p><span className="font-medium">Será criado como rascunho.</span> Nenhuma DAG é criada ou disparada; executar depende de validar e publicar.</p></div>
    <div className="border-t border-edge pt-4"><h3 className="text-sm font-semibold text-ink">Próximo passo</h3><p className="text-sm text-dim mt-1">Adicionar etapas e conectar o fluxo na Montagem. O rascunho aparece na lista de pipelines para quem tem acesso.</p></div>
   </aside>
  </form></div>
}
