import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { useMutation, useQuery } from '@tanstack/react-query'
import { Play, ScrollText } from 'lucide-react'
import { apiFetch, apiFetchBruto } from '../../lib/api'
import { arrangeWorkspace } from '../../lib/workspaceLayout'
import { publishedExecutionFlow } from '../../lib/workspaceNavigation'
import { executionInvestigation, runIdentityOrigin, stageAttempts, type ExecutionView, type WorkspaceRunIdentity } from '../../lib/workspaceTabs'
import { definitionLabel, type WorkspaceCapabilities, type WorkspaceDefinition, type WorkspaceLayout } from '../../lib/workspace'
import { useAuthStore } from '../../store/auth'
import { FluxoEditor } from '../etapas/FluxoEditor'
import { estiloEtapa, type PipelineExecucaoApi } from '../etapas/execucaoEtapas'
import { Button } from '../ui/Button'
import { Input, Select, Textarea } from '../ui/Input'
import { OverlayScope } from '../ui/overlay'
import { PageSpinner } from '../ui/Spinner'

type LogSelection = { task: string; attempt: number }
function TaskLog({name,runId,selection}:{name:string;runId:string;selection:LogSelection}) {
 const token = useAuthStore(s=>s.token)
 const log = useQuery({queryKey:['workspace-log',token,name,runId,selection.task,selection.attempt],queryFn:async({signal})=>(await apiFetchBruto(`/pipeline-task-log?${new URLSearchParams({pipeline_name:name,run_id:runId,task_id:selection.task,try_number:String(selection.attempt)})}`,{signal})).text(),retry:false})
 return <section className="min-w-0 border-t border-edge pt-4" aria-label="Log da tentativa"><h3 className="text-sm font-semibold text-ink mb-2">{selection.task} · tentativa {selection.attempt} · Airflow</h3>{log.isPending?<PageSpinner/>:log.isError?<p role="alert" className="text-sm text-red-700 dark:text-red-400">{log.error.message} <Button variant="secondary" size="sm" onClick={()=>log.refetch()}>Tentar novamente</Button></p>:<pre className="max-h-[480px] overflow-auto bg-canvas p-4 rounded-md text-xs text-ink whitespace-pre-wrap break-words">{log.data || 'Esta tentativa ainda não possui conteúdo de log.'}</pre>}</section>
}
function RunRequest({name,onRun,onClose}:{name:string;onRun:(id:string)=>void;onClose:()=>void}) {
 const [conf,setConf]=useState('{}');const [date,setDate]=useState('');const [error,setError]=useState('');const id=useRef(`workspace__${crypto.randomUUID()}`)
 const run=useMutation({mutationFn:async()=>{let parsed:unknown;try{parsed=JSON.parse(conf)}catch{throw new Error('Use um objeto JSON válido para os parâmetros da execução.')};if(!parsed||Array.isArray(parsed)||typeof parsed!=='object')throw new Error('Os parâmetros da execução devem ser um objeto JSON.');return apiFetch<{runId:string;state:string}>(`/workspace/runs?${new URLSearchParams({name})}`,{method:'POST',body:JSON.stringify({conf:parsed,dag_run_id:id.current,...(date?{logical_date:date}:{})})})},onSuccess:next=>{onRun(next.runId);onClose()},onError:e=>setError(e.message)})
 return <section className="border border-edge bg-panel rounded-lg p-4 space-y-3" aria-label="Solicitar execução"><h2 className="font-semibold text-sm text-ink">Executar a configuração publicada</h2><p className="text-sm text-dim">O disparo cria uma corrida no Airflow. Uma DAG pausada continuará aguardando ativação; publicar e executar são ações separadas.</p><div className="grid gap-3 sm:grid-cols-2"><Textarea label="Parâmetros desta execução (JSON)" value={conf} onChange={e=>setConf(e.target.value)} rows={3}/><Input label="Data lógica (ISO 8601, opcional)" value={date} onChange={e=>setDate(e.target.value)} placeholder="2026-10-09T12:00:00Z"/></div>{error&&<p role="alert" className="text-sm text-red-700 dark:text-red-400">{error}</p>}<div className="flex gap-2"><Button loading={run.isPending} onClick={()=>run.mutate()}><Play size={14}/>Confirmar execução</Button><Button variant="secondary" disabled={run.isPending} onClick={onClose}>Fechar</Button></div></section>
}
const ISSUES={etapa:(stage:string)=>`A etapa ${stage} não aparece nesta corrida. Escolha uma etapa da tabela.`,tentativa:(stage:string,attempt:number|null)=>`A tentativa ${attempt} da etapa ${stage} não pertence a esta corrida. Abra uma das tentativas listadas.`,corrida:()=>'A corrida pedida não corresponde à corrida exibida. Confira a data operacional e a corrida acima.','sem-tentativa':(stage:string)=>`A etapa ${stage} ainda não tem tentativas nesta corrida.`}
// Execução sempre lê a configuração publicada ou o snapshot da corrida, nunca o rascunho.
// Uma instância por Pipeline: gráfico e tabela ficam montados (o inativo oculto)
// e a etapa/tentativa investigadas vêm da URL, compartilhadas entre as vistas.
export function WorkspaceOperations({name,date,runId,stage,attempt,definition,layout,caps,view,active=true,onView,onDate,onRun,onInvestigate,onIdentity,actionsHost}:{name:string;date:string;runId:string;stage:string;attempt:number|null;definition:WorkspaceDefinition;layout:WorkspaceLayout;caps:WorkspaceCapabilities;view:ExecutionView;active?:boolean;onView:(view:ExecutionView)=>void;onDate:(date:string|null)=>void;onRun:(id:string|null)=>void;onInvestigate:(stage:string|null,attempt:number|null)=>void;onIdentity?:(origin:string,identity:WorkspaceRunIdentity|null)=>void;actionsHost?:HTMLElement|null}) {
 const token=useAuthStore(s=>s.token);const [requesting,setRequesting]=useState(false)
 const [search,setSearch]=useState(stage);const [seenStage,setSeenStage]=useState(stage)
 const matches=(step:{job_name:string;task_id:string|null},value:string)=>[step.job_name,step.task_id??''].some(id=>id.toLocaleLowerCase().includes(value.toLocaleLowerCase()))
 // Etapa trocada fora da tabela (gráfico, link): a busca não pode escondê-la.
 if(stage!==seenStage){setSeenStage(stage);if(stage&&!matches({job_name:stage,task_id:null},search))setSearch(stage)}
 // Seleção no gráfico troca a etapa investigada (sem tentativa: vale a corrente).
 const investigateRef=useRef(onInvestigate);useLayoutEffect(()=>{investigateRef.current=onInvestigate})
 const investigateStage=useCallback((id:string|null)=>investigateRef.current(id,null),[])
 const [graphMounted,setGraphMounted]=useState(view==='grafo')
 if(view==='grafo'&&!graphMounted)setGraphMounted(true)
 const query=useQuery({queryKey:['workspace-execution',token,name,date,runId],queryFn:({signal})=>apiFetch<PipelineExecucaoApi & {workspaceVersion?: {number:number;definition:WorkspaceDefinition;layout:WorkspaceLayout}}>(`/workspace/executions?${new URLSearchParams({name,...(date?{date}:{}),...(runId?{runId}:{})})}`,{signal}),retry:false,refetchInterval:active?30_000:false})
 const version=query.data?.workspaceVersion
 const flow=useMemo(()=>{
  const snapshot=version?.definition??definition;const saved=version?.layout??layout
  // Um snapshot com posições incompletas usa um desenho inteiro em memória;
  // misturar auto-layout legado e posições salvas pode sobrepor etapas.
  const display=snapshot.nodes.some(n=>!saved.nodes[n.id])?arrangeWorkspace(snapshot,saved,170):saved
  return publishedExecutionFlow(snapshot,display)
 },[version,definition,layout])
 const identity=query.data?.identidade
 const resolved=identity?.dag_run_id??identity?.run_id??''
 const reference=query.data?.data_referencia??(date||null)
 const title=version?definitionLabel(version.definition):null
 useEffect(()=>{onIdentity?.(runIdentityOrigin(name,date,runId),query.data?{runId:resolved||null,date:reference,versionNumber:version?.number??null,title}:null)},[onIdentity,name,date,runId,query.data,resolved,reference,version,title])
 const investigation=executionInvestigation(query.data?.etapas,stage,attempt,runId,[identity?.dag_run_id,identity?.run_id])
 const opened=investigation.open&&investigation.step?.task_id&&investigation.attempt!==null?{task:investigation.step.task_id,attempt:investigation.attempt}:null
 const run=active&&caps.actions.execute&&<Button size="sm" onClick={()=>setRequesting(true)}><Play size={14}/>Executar pipeline</Button>
 const steps=query.data?.etapas.filter(step=>matches(step,search))??[]
 const showing=active&&view==='tabela'
 return <div className="space-y-4">{actionsHost&&run?createPortal(run,actionsHost):null}
  <div className="flex flex-wrap items-center justify-between gap-3"><p className="text-xs text-dim">{version?`Definição da corrida · versão ${version.number}`:'Definição publicada atual · corrida sem versão histórica vinculada'}</p><div className="flex flex-wrap items-center gap-2"><div role="group" aria-label="Visualização da execução" className="inline-flex rounded-md border border-edge bg-panel p-0.5">{([['grafo','Gráfico'],['tabela','Tabela e logs']] as const).map(([id,label])=><button key={id} type="button" aria-pressed={view===id} onClick={()=>onView(id)} className={`rounded px-3 py-1 text-xs focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-600 ${view===id?'bg-blue-50 text-blue-700 font-semibold dark:bg-blue-900/30 dark:text-blue-300':'text-dim hover:text-ink'}`}>{label}</button>)}</div>{!actionsHost&&run}</div></div>
  {requesting&&<RunRequest name={name} onRun={id=>onRun(id)} onClose={()=>setRequesting(false)}/>}
  {graphMounted&&<OverlayScope.Provider value={active&&view==='grafo'}><div hidden={view!=='grafo'}><div className="h-[980px] lg:h-[620px] min-w-0"><FluxoEditor pipeline={name} readOnly modoExecucao dataExecucao={date||null} onDataExecucao={onDate} workspace={{flow,runId:runId||null,onRun,canReprocess:!!caps.actions.reprocess,canPause:!!caps.actions.pauseStages,active:active&&view==='grafo',stage:stage||null,onStage:investigateStage}}/></div></div></OverlayScope.Provider>}
  <div hidden={view!=='tabela'}><section className="bg-panel border border-edge rounded-lg p-4 space-y-4" aria-label="Etapas, tentativas e logs da corrida"><div className="flex flex-wrap gap-3"><Input label="Buscar etapa nesta corrida" value={search} onChange={e=>setSearch(e.target.value)} className="sm:max-w-xs"/><Input label="Data operacional" type="date" value={date} onChange={e=>onDate(e.target.value||null)}/>{identity?.candidatos?.length?<Select label="Corrida" value={runId||resolved} onChange={e=>onRun(e.target.value)} className="min-w-0 sm:max-w-md">{identity.candidatos.map(row=><option key={row.run_id} value={row.run_id??''}>{row.run_id} · {row.status}</option>)}</Select>:null}</div><p className="text-xs text-dim break-all">Corrida: {resolved||'Nenhuma corrida identificada'} · {query.data?.data_referencia??date}</p>{query.isPending?<PageSpinner/>:query.isError?<p role="alert" className="text-sm text-red-700 dark:text-red-400">{query.error.message}</p>:<><div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead className="text-xs text-dim"><tr><th className="py-2 pr-3 font-medium">Etapa</th><th className="py-2 pr-3 font-medium">Estado</th><th className="py-2 pr-3 font-medium">Início</th><th className="py-2 pr-3 font-medium">Tentativas</th><th className="py-2 font-medium">Logs</th></tr></thead><tbody className="divide-y divide-edge">{steps.map(step=>{const attempts=stageAttempts(step);return <tr key={step.job_name} aria-current={investigation.step===step?'true':undefined}><td className="py-2 pr-3 text-ink break-words">{step.job_name}</td><td className="py-2 pr-3 text-dim">{step.sem_execucao?'Sem telemetria':estiloEtapa(step.status)?.rotulo??'Não informado'}</td><td className="py-2 pr-3 text-dim">{step.inicio??'—'}</td><td className="py-2 pr-3 text-dim tabular-nums">{step.total_tentativas??step.tentativas.length}</td><td className="py-2"><div className="flex flex-wrap gap-2">{attempts.length?attempts.map(value=><Button key={value} variant="secondary" size="sm" aria-pressed={!!opened&&investigation.step===step&&opened.attempt===value} disabled={!resolved||!step.task_id} onClick={()=>onInvestigate(step.job_name,value)}><ScrollText size={14}/>Tentativa {value}</Button>):<span className="text-xs text-dim">Sem tentativas</span>}</div></td></tr>})}</tbody></table></div>{!query.data.etapas.length?<p className="text-sm text-dim py-4">Nenhuma etapa nesta corrida.</p>:!steps.length&&<p className="text-sm text-dim py-4">Nenhuma etapa encontrada nesta corrida para a busca.</p>}{investigation.issue&&<p role="status" className="text-sm text-dim">{ISSUES[investigation.issue](stage,investigation.attempt)}</p>}{showing&&opened&&resolved&&<TaskLog key={`${name}:${resolved}:${opened.task}:${opened.attempt}`} name={name} runId={resolved} selection={opened}/>}</>}</section></div>
  <p className="text-xs text-dim">Cancelar uma pausa de etapa não encerra o job remoto. O workspace não oferece cancelamento geral da execução.</p>
 </div>
}
