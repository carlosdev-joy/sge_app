import { lazy, Suspense, useCallback, useState } from 'react'
import { Navigate, Link, useLocation, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { GitBranch, FilePlus2, Settings2, Activity } from 'lucide-react'
const WorkspaceOperations = lazy(() => import('../components/workspace/WorkspaceOperations').then(module => ({ default: module.WorkspaceOperations })))
import { contextualPath, malhaReturnPath } from '../lib/workspaceNavigation'
import { useGuardedNavigate } from '../lib/navigationGuard'
import { OverlayScope } from '../components/ui/overlay'
import { workspaceApi } from '../lib/workspaceApi'
import { definitionLabel, object, pipelineMetadata, text, workspacePath, type WorkspaceDraft, type WorkspaceExperience } from '../lib/workspace'
import { WORKSPACE_DESTINATIONS, configurationGroup, executionView, parseAttempt, runIdentityOrigin, workspaceAliasRedirect, workspaceHeaderContext, type ConfigurationGroup, type ExecutionView, type WorkspaceDestination, type WorkspaceRunIdentity } from '../lib/workspaceTabs'
import { workspacePredecessors } from '../lib/workspaceCatalog'
import { SCHEDULE_LABELS } from '../components/pipelines/pipelineUtils'
import { useWorkspaceCapabilities } from '../components/workspace/useWorkspaceCapabilities'
import { WORKSPACE_FRAMED_CONTENT } from '../lib/shellFrame'
const WorkspaceVersions = lazy(() => import('../components/workspace/WorkspaceVersions').then(module => ({ default: module.WorkspaceVersions })))
import { WorkspaceEditor, type WorkspaceSessionState } from '../components/workspace/WorkspaceEditor'
import { Button } from '../components/ui/Button'
import { Select } from '../components/ui/Input'
import { PageSpinner } from '../components/ui/Spinner'
import { toast } from '../components/ui/Toast'
import { useAuthStore } from '../store/auth'

const CONTEXT_TONES = { draft: 'border-edge text-ink bg-canvas', published: 'border-green-300 text-green-800 bg-green-50 dark:border-green-800 dark:text-green-300 dark:bg-green-900/20', run: 'border-blue-300 text-blue-800 bg-blue-50 dark:border-blue-800 dark:text-blue-300 dark:bg-blue-900/20' }
export default function PipelineWorkspace(){
 const [actionsHost,setActionsHost]=useState<HTMLDivElement|null>(null)
 // Estado vindo de filhos guarda a origem: nunca mostrar sessão/corrida de outro pipeline, data ou corrida.
 const [session,setSession]=useState<{name:string;state:WorkspaceSessionState}|null>(null);const [runIdentity,setRunIdentity]=useState<{origin:string;identity:WorkspaceRunIdentity|null}|null>(null)
 const [operationsFor,setOperationsFor]=useState<string|null>(null)
 const params=useParams();const nome=params.nome??'';const [search]=useSearchParams();const location=useLocation();const navigate=useNavigate();const guardedNavigate=useGuardedNavigate();const client=useQueryClient();const token=useAuthStore(s=>s.token)
 const caps=useWorkspaceCapabilities();const requested=search.get('experiencia');const experience:WorkspaceExperience=requested==='desenvolvimento'||requested==='sustentacao'?requested:'consulta'
 const tab=(params['*']??'').split('/').filter(Boolean)[0]??'';const date=search.get('data')??'';const runId=search.get('run_id')??''
 const group=configurationGroup(search.get('grupo'));const view=executionView(search.get('vista'))
 // Investigação da Execução (contrato entre gráfico, tabela e links): etapa e tentativa na URL.
 const stage=search.get('etapa')??'';const attempt=parseAttempt(search.get('tentativa'))
 const onSession=useCallback((state:WorkspaceSessionState)=>setSession({name:nome,state}),[nome])
 const onIdentity=useCallback((origin:string,identity:WorkspaceRunIdentity|null)=>setRunIdentity({origin,identity}),[])
 function path(id:string,nextExperience=experience){const next=new URLSearchParams(search);if(draft)next.set('fonte','rascunho');return contextualPath(nome,id,next,nextExperience,location.hash)}
 // Mesma tela, outra query: conserva o hash; não navega se nada mudou.
 function setQuery(next:URLSearchParams,replace=false){if(next.toString()!==search.toString())navigate({search:`?${next}`,hash:location.hash},{replace})}
 function setParam(key:string,value:string|null,clear:string[]=[]){const next=new URLSearchParams(search);if(value)next.set(key,value);else next.delete(key);for(const item of clear)next.delete(item);setQuery(next)}
 const setDate=(value:string|null)=>setParam('data',value,['run_id','tentativa'])
 const setRun=(value:string|null)=>setParam('run_id',value,['tentativa'])
 const setGroup=(value:ConfigurationGroup)=>setParam('grupo',value)
 const setView=(value:ExecutionView)=>setParam('vista',value==='tabela'?value:null)
 function investigate(nextStage:string|null,nextAttempt:number|null){const next=new URLSearchParams(search);if(nextStage)next.set('etapa',nextStage);else next.delete('etapa');if(nextStage&&nextAttempt)next.set('tentativa',String(nextAttempt));else next.delete('tentativa');setQuery(next,true)}
 const context=useQuery({queryKey:['workspace-context',token,nome],queryFn:({signal})=>workspaceApi.context(nome,signal),enabled:!!nome&&caps.data?.enabled===true&&caps.data.actions.consultDefinition,retry:false,refetchInterval:30_000})
 const importing=useMutation({mutationFn:()=>workspaceApi.import(nome),onSuccess:()=>{client.invalidateQueries({queryKey:['workspace-context',token,nome]});navigate(workspacePath(nome,'montagem','desenvolvimento'))},onError:error=>toast.error(error.message)})
 const data=context.data;const development=experience==='desenvolvimento';const draft=development||search.get('fonte')==='rascunho'||!data?.published?data?.draft??null:null;const flow=draft?{definition:draft.definition,layout:draft.layout,readOnlyReasons:draft.readOnlyReasons}:data?.published
 const actions=caps.data?.actions
 const tabs=WORKSPACE_DESTINATIONS.filter(([id])=>id==='visao-geral'||(id==='versoes'?!!actions?.consultVersions:id==='execucao'?!!actions?.consultStages&&!!actions.consultLogs:!!actions?.consultStages))
 function saved(next:WorkspaceDraft){if(next.state==='publicado')client.invalidateQueries({queryKey:['workspace-context',token,nome]});client.setQueryData(['workspace-context',token,nome],data?{...data,draft:next}:undefined)}
 const redirect=workspaceAliasRedirect(nome,tab,search,location.hash)
 if(redirect)return <Navigate replace to={redirect}/>
 if(caps.isPending||context.isPending&&context.fetchStatus!=='idle')return <PageSpinner/>
 if(caps.isError||!caps.data?.enabled||!caps.data.actions.consultDefinition||context.isError)return <div className="space-y-4"><h1 className="text-xl font-semibold text-ink">Workspace indisponível</h1><p role="alert" className="text-sm text-dim">{context.error?.message??'Não foi possível consultar o workspace nesta sessão. A lista de pipelines continua disponível.'}</p><Link className="text-sm text-blue-700 dark:text-blue-400 underline" to="/pipelines">Voltar aos pipelines</Link></div>
 if(!data)return <PageSpinner/>
 const viewingTab:WorkspaceDestination=tabs.find(t=>t[0]===tab)?.[0]??(experience==='sustentacao'&&tabs.some(t=>t[0]==='execucao')?'execucao':development&&tabs.some(t=>t[0]==='montagem')?'montagem':'visao-geral')
 const running=viewingTab==='execucao'
 // Execução fica montada (oculta) depois da primeira visita, por pipeline.
 if(running&&data.published&&operationsFor!==nome)setOperationsFor(nome)
 const identity=running&&runIdentity?.origin===runIdentityOrigin(nome,date,runId)?runIdentity.identity:null
 // Na Execução, nome e metadados são os da definição executada (snapshot) ou publicada, nunca os do rascunho.
 const shown=running?data.published?.definition:flow?.definition
 const title=running&&identity?.title?identity.title:shown?definitionLabel(shown):data.pipelineName;const metadata=shown?pipelineMetadata(shown):object(data.summary)
 const header=workspaceHeaderContext(viewingTab,draft,!!data.published,identity)
 const dirty=!running&&session?.name===nome&&session.state.dirty
 const unapplied=!running&&session?.name===nome&&session.state.unapplied
 const malha=malhaReturnPath(search)
 const canStages=caps.data.actions.consultStages
 const schedule=text(metadata.schedule_type);const scheduleTime=text(metadata.scheduled_time).slice(0,5);const predecessors=flow?workspacePredecessors(flow.definition):[]
 return <div className="space-y-4"><nav aria-label="Caminho" className="text-sm text-dim"><Link to="/pipelines" className="hover:underline">Pipelines</Link>{text(metadata.domain)&&<><span className="mx-2">/</span><span>{text(metadata.domain)}</span></>}<span className="mx-2">/</span><span className="text-ink">{title}</span></nav>{malha&&<Link className="text-sm text-blue-700 dark:text-blue-400 underline" to={malha}>Voltar à malha</Link>}
  <header className="flex flex-wrap justify-between items-start gap-4"><div className="min-w-0"><div className="flex flex-wrap items-center gap-x-3 gap-y-2"><h1 className="text-2xl font-semibold text-ink break-words">{title}</h1><span className="px-2 py-1 rounded-md border border-edge text-xs text-dim bg-panel">Ambiente da aplicação: {data.environmentLabel??'Workspace'}</span><span className={`px-2 py-1 rounded-md border text-xs font-medium break-all ${CONTEXT_TONES[header.tone]}`}>{header.label}</span>{dirty&&<span className="px-2 py-1 rounded-md border text-xs font-medium border-amber-300 bg-amber-50 text-amber-800 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-300">Alterações não salvas</span>}{unapplied&&<span className="px-2 py-1 rounded-md border text-xs font-medium border-amber-300 bg-amber-50 text-amber-800 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-300">Alterações não aplicadas no inspector</span>}</div><p className="font-mono text-xs text-dim mt-2 break-all">{data.pipelineName}</p></div>
   <div className="flex flex-wrap items-end justify-end gap-3">{data.published&&data.draft&&!running&&<Select label="Definição" value={draft?'rascunho':'publicado'} onChange={e=>{const next=new URLSearchParams(search);next.set('fonte',e.target.value);if(e.target.value==='publicado'&&development)next.set('experiencia','consulta');guardedNavigate(`${location.pathname}?${next}${location.hash}`)}} className="w-40"><option value="publicado">Configuração publicada</option><option value="rascunho">Rascunho · revisão {data.draft.revision}</option></Select>}<Select label="Experiência" value={experience} onChange={e=>guardedNavigate(path(e.target.value==='sustentacao'?'execucao':e.target.value==='desenvolvimento'?'montagem':'visao-geral',e.target.value as WorkspaceExperience))} className="min-w-44"><option value="consulta">Consulta</option><option value="desenvolvimento">Desenvolvimento</option><option value="sustentacao">Sustentação</option></Select><div ref={setActionsHost} className="flex flex-wrap gap-2"/></div></header>
  <nav aria-label="Áreas do pipeline" className="flex gap-1 border-b border-edge overflow-x-auto">{tabs.map(([id,label])=><Link key={id} to={path(id)} aria-current={viewingTab===id?'page':undefined} className={`px-4 py-3 text-sm whitespace-nowrap border-b-2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-600 ${viewingTab===id?'border-blue-600 text-blue-700 dark:text-blue-400 font-semibold':'border-transparent text-dim hover:text-ink'}`}>{label}</Link>)}</nav>

  {development&&!data.draft&&caps.data.actions.editDraft&&data.published&&!running&&<div className="flex flex-wrap items-center justify-between gap-3 bg-panel border border-edge rounded-lg p-4"><p className="text-sm text-dim">Crie um rascunho a partir da configuração publicada para iniciar a montagem.</p><Button onClick={()=>importing.mutate()} loading={importing.isPending}><FilePlus2 size={16}/>Criar rascunho desta configuração</Button></div>}
  {viewingTab==='versoes'&&<div className={WORKSPACE_FRAMED_CONTENT}><Suspense fallback={<PageSpinner />}><WorkspaceVersions name={nome} canRestore={caps.data.actions.editDraft}/></Suspense></div>}
  {viewingTab==='visao-geral'&&<section className={`${WORKSPACE_FRAMED_CONTENT} bg-panel border border-edge rounded-lg p-5 sm:p-6 space-y-6`} aria-labelledby="workspace-overview"><div className="space-y-2"><h2 id="workspace-overview" className="text-base font-semibold text-ink">O que este pipeline faz</h2>{text(metadata.descricao)?<p className="text-sm text-ink whitespace-pre-wrap max-w-3xl">{text(metadata.descricao)}</p>:<p className="text-sm text-dim">A finalidade ainda não foi descrita.{canStages&&<> Cadastre em <Link className="text-blue-700 dark:text-blue-400 underline" to={path('configuracao')}>Configuração → Identificação</Link>.</>}</p>}</div>
   <dl className="grid sm:grid-cols-2 lg:grid-cols-4 gap-5 text-sm">{[['Projeto',text(metadata.project_name)],['Domínio',text(metadata.domain)],['Responsável',draft?.responsible||text(object(data.summary).responsible)],['Desenvolvimento',data.draft?`Rascunho · revisão ${data.draft.revision}`:'Sem rascunho em edição'],['Publicação',data.published?'Configuração publicada':'Ainda não publicado'],['Agenda',schedule?`${SCHEDULE_LABELS[schedule]??schedule}${scheduleTime&&!['on_demand','custom','monthly_days_times'].includes(schedule)?` · ${scheduleTime}`:''}`:''],['Predecessores',flow?predecessors.join(', ')||'Sem predecessores':''],['Etapas',flow?String(flow.definition.nodes.length):''],['Destino de execução',text(metadata.ambiente)],['Runbook',flow?text(metadata.runbook_md)?'Disponível em Configuração → Documentação':'Não cadastrado':'']].filter(([,value])=>value).map(([label,value])=><div key={label}><dt className="text-dim mb-1">{label}</dt><dd className="text-ink break-words">{value}</dd></div>)}</dl>
   {canStages?<div className="flex flex-wrap gap-3 border-t border-edge pt-5">{tabs.some(t=>t[0]==='configuracao')&&<Link to={path('configuracao')} className="inline-flex items-center gap-2 rounded-md border border-edge px-3 py-1.5 text-sm text-ink hover:bg-edge/30 focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-600"><Settings2 size={16}/>{development?'Editar configuração':'Consultar configuração'}</Link>}<Link to={path('montagem')} className="inline-flex items-center gap-2 rounded-md border border-edge px-3 py-1.5 text-sm text-ink hover:bg-edge/30 focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-600"><GitBranch size={16}/>Abrir montagem</Link>{tabs.some(t=>t[0]==='execucao')&&<Link to={path('execucao')} className="inline-flex items-center gap-2 rounded-md border border-edge px-3 py-1.5 text-sm text-ink hover:bg-edge/30 focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-600"><Activity size={16}/>Ver execuções</Link>}</div>:<p className="text-sm text-dim">A consulta de etapas não está autorizada nesta sessão.</p>}</section>}
  {data.published&&operationsFor===nome&&<OverlayScope.Provider value={running}><div hidden={!running}><Suspense fallback={<PageSpinner />}><WorkspaceOperations key={nome} name={nome} date={date} runId={runId} stage={stage} attempt={attempt} definition={data.published.definition} layout={data.published.layout} draftRevision={data.draft?.revision??null} caps={caps.data} view={view} active={running} onView={setView} onDate={setDate} onRun={setRun} onInvestigate={investigate} onIdentity={onIdentity} actionsHost={actionsHost}/></Suspense></div></OverlayScope.Provider>}
  {running&&!data.published&&<p className="text-sm text-dim">Este pipeline possui somente rascunho. Publique uma versão para executar e acompanhar corridas.</p>}
  {flow&&canStages?<WorkspaceEditor key={`${nome}-${draft?.draftId??'published'}-${experience}`} name={nome} actionsHost={actionsHost} draft={draft} definition={flow.definition} layout={flow.layout} reasons={flow.readOnlyReasons} capabilities={caps.data} development={development&&!!draft} tab={viewingTab} configGroup={group} onConfigGroup={setGroup} onOpenTab={id=>navigate(path(id))} onSession={onSession} onSaved={saved} onDiscarded={()=>{client.invalidateQueries({queryKey:['workspace-context',token,nome]});navigate('/pipelines')}}/>:(viewingTab==='montagem'||viewingTab==='configuracao')&&<p className="text-sm text-dim">A definição do fluxo não está disponível neste contexto.</p>}
 </div>
}
