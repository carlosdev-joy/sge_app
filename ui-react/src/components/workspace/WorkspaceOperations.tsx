import { Suspense, lazy, useEffect, useId, useMemo, useState } from 'react'
import { createPortal } from 'react-dom'
import { useQuery } from '@tanstack/react-query'
import { AlertCircle, AlertTriangle, ChevronLeft, ChevronRight, History, Info, PanelRightClose, PanelRightOpen, Play, RefreshCw } from 'lucide-react'
import { apiFetch } from '../../lib/api'
import { arrangeWorkspace } from '../../lib/workspaceLayout'
import { EMPTY_HISTORY_FILTERS, EXECUTION_POLL, EXECUTION_REVALIDATE_MS, FRESHNESS_LABEL, activePhase, clockLabel, completionLabel, drawingSource, drawingSourceLabel, executionFreshness, executionPollInterval, executionQueryKey, executionRequestPath, operationScope, responseMatchesRequest, runCounts, runOverlay, runPhase, runStateFor, stageChain, stepsOutsideDrawing, type ChainDirection, type NodeRunKind, type RequestedRun, type RunHistoryFilters } from '../../lib/workspaceExecution'
import { type ExecutionView, type WorkspaceRunIdentity, runIdentityOrigin } from '../../lib/workspaceTabs'
import { definitionLabel, nodeLabel, type WorkspaceCapabilities, type WorkspaceDefinition, type WorkspaceLayout } from '../../lib/workspace'
import { usePageVisible } from '../../lib/usePageVisible'
import { useAuthStore } from '../../store/auth'
import { duracaoCurta, horaLonga, rotuloCorrida, textoRazao, type PipelineExecucaoApi } from '../etapas/execucaoEtapas'
import { Banner } from '../ui/Banner'
import { Button } from '../ui/Button'
import { Input, Select } from '../ui/Input'
import { Sheet } from '../ui/Sheet'
import { PageSpinner } from '../ui/Spinner'
import { toast } from '../ui/Toast'
import { WorkspaceCanvas } from './WorkspaceCanvas'
import { WorkspaceRunInspector, type RunInspectorTab } from './WorkspaceRunInspector'
import { RunPhaseBadge, RunStateIcon, StateLabel } from './WorkspaceRunStatus'
import { typeLabel } from './workspaceCatalog'

// Histórico e pedido de execução carregados só ao abrir: fora da entrada da Execução.
const WorkspaceRunHistory = lazy(() => import('./WorkspaceRunHistory').then(module => ({ default: module.WorkspaceRunHistory })))
const WorkspaceRunRequest = lazy(() => import('./WorkspaceRunRequest').then(module => ({ default: module.WorkspaceRunRequest })))
const LEGEND: readonly (readonly [NodeRunKind, string, string])[] = [['success','Concluída','sucesso confirmado'],['running','Executando','telemetria ativa'],['failed','Falhou',''],['gate','Em espera no portão',''],['skipped','Pulada','ramo não tomado'],['none','Sem telemetria','neutra, nunca verde'],['unknown','Estado não traduzido','código da origem']]
type ExecutionResponse = PipelineExecucaoApi & { workspaceVersion?: { number: number; definition: WorkspaceDefinition; layout: WorkspaceLayout } }
const sameStage = (a: string | null | undefined, b: string) => String(a ?? '').trim().toLowerCase() === b.trim().toLowerCase()
const NAV_BUTTON = 'inline-flex size-8 items-center justify-center rounded-md border border-edge text-ink hover:bg-edge/30 disabled:opacity-40 disabled:cursor-not-allowed focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-600'
const VIEW_BUTTON = 'rounded px-3 py-1 text-xs focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-600'
function shiftDay(iso: string, delta: number): string {
 const date = new Date(`${iso}T12:00:00Z`)
 if (Number.isNaN(date.getTime())) return iso
 date.setUTCDate(date.getUTCDate() + delta)
 return date.toISOString().slice(0, 10)
}

// Execução lê a configuração publicada ou o snapshot da corrida, nunca o rascunho.
// Uma leitura alimenta gráfico, tabela e inspector; etapa/tentativa vêm da URL.
// A instância fica montada (oculta) ao sair da aba: zoom, seleção e filtros voltam iguais.
// `draftRevision`: só informa que existe rascunho; nada dele entra no gráfico ou na execução.
// `pipelineName`: grafia oficial devolvida pelo contexto; a resposta da execução
// precisa nomear este pipeline (pela grafia pedida ou pela oficial) para ser usada.
export function WorkspaceOperations({name,pipelineName,date,runId,stage,attempt,definition,layout,draftRevision=null,caps,view,active=true,onView,onDate,onRun,onOpenRun,onInvestigate,onIdentity,actionsHost}:{name:string;pipelineName?:string;date:string;runId:string;stage:string;attempt:number|null;definition:WorkspaceDefinition;layout:WorkspaceLayout;draftRevision?:number|null;caps:WorkspaceCapabilities;view:ExecutionView;active?:boolean;onView:(view:ExecutionView)=>void;onDate:(date:string|null)=>void;onRun:(id:string|null)=>void;onOpenRun?:(id:string,date:string|null)=>void;onInvestigate:(stage:string|null,attempt:number|null)=>void;onIdentity?:(origin:string,identity:WorkspaceRunIdentity|null)=>void;actionsHost?:HTMLElement|null}) {
 const token=useAuthStore(s=>s.token);const visible=usePageVisible();const panelId=useId()
 // Pedido de execução aberto: guarda o contexto em que nasceu (sessão,
 // pipeline, data, corrida, permissão). Mudou o contexto ou a aba saiu de
 // cena, o diálogo some e uma resposta tardia não seleciona nada.
 const runScope=operationScope({token,name,date,runId,capabilities:[!!caps.actions.execute]})
 const [requested,setRequested]=useState<RequestedRun|null>(null);const [requesting,setRequesting]=useState<string|null>(null)
 if(requesting!==null&&(requesting!==runScope||!active||!caps.actions.execute))setRequesting(null)
 const [historyOpen,setHistoryOpen]=useState(false);const [historyFilters,setHistoryFilters]=useState<RunHistoryFilters>(EMPTY_HISTORY_FILTERS)
 const [tab,setTab]=useState<RunInspectorTab>(attempt?'logs':'resumo');const [inspectorOpen,setInspectorOpen]=useState(true);const [focused,setFocused]=useState(false)
 const [chain,setChain]=useState<{stage:string;direction:ChainDirection}|null>(null);const [focusRequest,setFocusRequest]=useState<{id:string;seq:number}|null>(null)
 const [search,setSearch]=useState('')
 const [graphMounted,setGraphMounted]=useState(view==='grafo')
 if(view==='grafo'&&!graphMounted)setGraphMounted(true)
 // Uma resposta só é usada se nomear este pipeline, a corrida pedida e, sem
 // corrida, a data pedida. Fora disso nada dela (desenho, versão, título,
 // estados, identidade) entra na tela: o desenho fica no publicado, rotulado.
 const accepts=(response:ExecutionResponse|undefined)=>responseMatchesRequest(response,{names:pipelineName&&pipelineName!==name?[name,pipelineName]:[name],date,runId})
 const phaseOf=(own:ExecutionResponse|undefined)=>runPhase({name,runId:runId||own?.identidade?.dag_run_id||own?.identidade?.run_id||'',requested,identity:own?.identidade,corrida:own?.corrida})
 // Leitura só com a aba Execução exibida e o navegador visível; trocar a chave
 // com a aba oculta não dispara busca, e voltar revalida.
 const query=useQuery({queryKey:executionQueryKey(token,name,date,runId),queryFn:({signal})=>apiFetch<ExecutionResponse>(executionRequestPath(name,date,runId),{signal}),enabled:active&&visible&&!!token,staleTime:EXECUTION_REVALIDATE_MS,retry:false,refetchOnWindowFocus:active&&visible,refetchIntervalInBackground:false,refetchInterval:q=>executionPollInterval({visible,shown:active,phase:phaseOf(accepts(q.state.data)?q.state.data:undefined)})})
 const data=query.data
 const trusted=useMemo(()=>responseMatchesRequest(data,{names:pipelineName&&pipelineName!==name?[name,pipelineName]:[name],date,runId})?data:undefined,[data,name,pipelineName,date,runId])
 const matches=!!trusted
 const version=trusted?.workspaceVersion,identity=trusted?.identidade
 const resolved=identity?.dag_run_id??identity?.run_id??''
 const phase=phaseOf(trusted)
 const freshness=executionFreshness({hasData:!!data,isError:query.isError,isFetching:query.isFetching,dataUpdatedAt:query.dataUpdatedAt,errorUpdatedAt:query.errorUpdatedAt})
 const live=active&&visible&&matches&&freshness!=='unavailable'&&activePhase(phase)
 const snapshot=version?.definition??definition
 const drawing=useMemo(()=>{const saved=version?.layout??layout
  // Snapshot com posições incompletas usa um desenho inteiro em memória; misturar
  // auto-layout e posições salvas pode sobrepor etapas.
  return snapshot.nodes.some(n=>!saved.nodes[n.id])?arrangeWorkspace(snapshot,saved,170):saved},[snapshot,version,layout])
 const overlay=useMemo(()=>trusted?runOverlay(trusted.etapas,trusted.pausas,live):null,[trusted,live])
 const counts=overlay?runCounts(overlay,snapshot):null
 const source=drawingSource(!!resolved,version?.number,!!runId&&!matches)
 const outside=trusted?stepsOutsideDrawing(snapshot,trusted.etapas):[]
 const reference=trusted?.data_referencia??(date||null)
 const title=version?definitionLabel(version.definition):null
 useEffect(()=>{onIdentity?.(runIdentityOrigin(name,date,runId),trusted?{runId:resolved||null,date:reference,versionNumber:version?.number??null,title}:null)},[onIdentity,name,date,runId,trusted,resolved,reference,version,title])
 const node=stage?snapshot.nodes.find(n=>n.id===stage)??null:null
 const step=stage&&trusted?trusted.etapas.find(row=>row.task_id===stage||sameStage(row.job_name,stage)):undefined
 const state=node?runStateFor(overlay,node.id):null
 const direction=chain&&chain.stage===stage?chain.direction:null
 const highlight=useMemo(()=>direction&&stage?stageChain(snapshot,stage,direction):null,[direction,stage,snapshot])
 const run=useMemo(()=>({states:overlay,highlight}),[overlay,highlight])
 function select(id:string|null,locate=false){onInvestigate(id||null,null);if(id){setInspectorOpen(true);if(locate)setFocusRequest(current=>({id,seq:(current?.seq??0)+1}))}else setFocused(false)}
 function requestedRun(next:RequestedRun){if(next.name!==name)return;setRequested(next);setRequesting(null);onRun(next.runId);toast.success(`Execução solicitada: ${next.runId}`)}
 const runButton=active&&caps.actions.execute&&<Button size="sm" onClick={()=>setRequesting(runScope)}><Play size={14}/>Executar pipeline</Button>
 // Reprocessar/pausar: a confirmação vale só para esta sessão, corrida, data, etapa e capacidades.
 const actionScope=operationScope({token,name,date:reference,runId:resolved||null,stage:stage||null,capabilities:[!!caps.actions.reprocess,!!caps.actions.pauseStages]})
 const shownDate=reference??''
 const ambiguous=!!identity?.ambiguo&&(identity.candidatos?.length??0)>1
 const steps=(trusted?trusted.etapas:[]).filter(row=>!search||[row.job_name,row.task_id??''].some(value=>value.toLocaleLowerCase().includes(search.toLocaleLowerCase())))
 const unknownStage=!!stage&&!node
 return <div className="space-y-3" onKeyDown={event=>{if(event.key==='Escape'&&focused&&!event.defaultPrevented&&!document.querySelector('[role="dialog"]')){event.preventDefault();setFocused(false)}}}>{actionsHost&&runButton?createPortal(runButton,actionsHost):null}
  <section aria-label="Corrida em exibição" className="rounded-lg border border-edge bg-panel">
   <div className="flex flex-wrap items-center gap-x-4 gap-y-2 px-3 py-2.5 border-b border-edge">
    <RunPhaseBadge phase={phase} live={live} code={trusted?.corrida?.status??null}/>
    <p className="min-w-0 text-sm text-ink"><span className="text-dim">Corrida </span><span className="font-mono text-xs break-all">{runId||resolved||'nenhuma selecionada'}</span></p>
    <div className="flex items-center gap-1.5" role="group" aria-label="Data de referência"><button type="button" className={NAV_BUTTON} aria-label="Dia anterior" disabled={!shownDate} onClick={()=>onDate(shiftDay(shownDate,-1))}><ChevronLeft size={15}/></button><Input aria-label="Data de referência da execução" type="date" value={shownDate} onChange={e=>onDate(e.target.value||null)} className="w-[9.5rem]"/><button type="button" className={NAV_BUTTON} aria-label="Dia seguinte" disabled={!shownDate} onClick={()=>onDate(shiftDay(shownDate,1))}><ChevronRight size={15}/></button><Button variant="ghost" size="sm" disabled={!date&&!runId} title="Data de referência corrente, calculada pela virada" onClick={()=>onDate(null)}>Hoje</Button></div>
    <Button variant="secondary" size="sm" aria-haspopup="dialog" onClick={()=>setHistoryOpen(true)}><History size={14}/>Histórico</Button>
    <div className="ml-auto flex flex-wrap items-center gap-2 text-xs text-dim" aria-label="Atualização dos dados">
     <span className="inline-flex items-center gap-1.5"><span aria-hidden="true" className={`size-2 rounded-full ${freshness==='unavailable'?'bg-red-600 dark:bg-red-400':freshness==='live'||freshness==='refreshing'?'bg-green-600 dark:bg-green-400':'bg-slate-400'}`}/>{FRESHNESS_LABEL[freshness]}</span>
     <span className="tabular-nums">{query.dataUpdatedAt?`${freshness==='unavailable'?'último estado às':'atualizado às'} ${clockLabel(query.dataUpdatedAt)}`:'sem dados ainda'}</span>
     <span>{!visible?'atualização pausada com a aba oculta':`atualiza a cada ${(executionPollInterval({visible,shown:true,phase})||EXECUTION_POLL.fallbackMs)/1000} s`}</span>
     <Button variant="ghost" size="sm" loading={query.isFetching} onClick={()=>query.refetch()}><RefreshCw size={14}/>{freshness==='unavailable'?'Tentar novamente':'Atualizar'}</Button>
    </div>
   </div>
   <div className="flex flex-wrap items-center gap-x-4 gap-y-1 px-3 py-2 text-xs text-dim">
    {counts&&<p className="text-sm text-ink">{completionLabel(counts)}</p>}
    {counts&&<p className="flex flex-wrap gap-x-3 gap-y-1">{([['failed','com falha'],['running','executando'],['gate','em espera no portão'],['skipped','puladas'],['none','sem telemetria'],['unknown','com estado não traduzido'],['pauseMarked','com pausa marcada']] as const).filter(([k])=>counts[k]>0).map(([k,label])=><span key={k}>{counts[k]} {label}</span>)}</p>}
    <p className="min-w-0">{drawingSourceLabel(source,version?.number)}{draftRevision!==null&&` · o rascunho (revisão ${draftRevision}) só é executado depois de publicado`}</p>
   </div>
  </section>
  {query.isError&&!data&&<Banner tom="erro" icone={<AlertCircle size={14} className="shrink-0"/>}>Não foi possível consultar a execução: {query.error.message}. A configuração publicada aparece sem estados.</Banner>}
  {query.isError&&data&&<Banner tom="alerta" icone={<AlertTriangle size={14} className="shrink-0"/>}>Fonte indisponível: mostrando o último estado recebido às {clockLabel(query.dataUpdatedAt)}, sem indicar atividade atual.</Banner>}
  {data&&!matches&&<Banner tom="alerta" icone={<AlertTriangle size={14} className="shrink-0"/>}>A resposta não corresponde {runId?`à corrida pedida (${runId})`:'a este pipeline e data'}; desenho, versão e estados dela não são usados. Confira a corrida pelo Histórico.</Banner>}
  {phase==='requested'&&<Banner tom="info" icone={<Info size={14} className="shrink-0"/>}>Solicitação {runId} recebida{requested?.state?` (o Airflow informou: ${requested.state})`:''}. Aguardando o motor registrar a corrida; nenhuma etapa aparece em andamento antes da telemetria.</Banner>}
  {trusted?.migration_067_pendente&&<Banner tom="alerta" icone={<AlertTriangle size={14} className="shrink-0"/>}>Migration 067 pendente: a corrida foi associada à data por aproximação sobre a telemetria das etapas.</Banner>}
  {trusted?.airflow_indisponivel&&<Banner tom="alerta" icone={<AlertTriangle size={14} className="shrink-0"/>}>O Airflow não respondeu; a identidade da corrida pode estar incompleta. Nada foi presumido.</Banner>}
  {trusted?.vazio&&phase!=='requested'&&<Banner tom="info" icone={<Info size={14} className="shrink-0"/>}>{textoRazao(trusted.razao)} Nenhuma etapa aparece como concluída: ausência de registro não é sucesso.</Banner>}
  {ambiguous&&<div className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950/30 dark:text-amber-200"><p>{identity!.candidatos.length} corridas em {shownDate}. Exibindo {runId?'a escolhida':'a mais recente'}{identity!.regra?` (regra ${identity!.regra})`:''}.</p><div className="mt-2 flex flex-wrap gap-1.5">{identity!.candidatos.map((candidate,index)=>{const current=!!candidate.run_id&&candidate.run_id===resolved;return <Button key={candidate.run_id??`sem-${index}`} variant="secondary" size="sm" aria-pressed={current} disabled={current||!candidate.run_id} title={candidate.run_id??undefined} onClick={()=>onRun(candidate.run_id)}>{rotuloCorrida(candidate)}</Button>})}{runId&&<Button variant="ghost" size="sm" onClick={()=>onRun(null)}>Voltar à mais recente</Button>}</div></div>}
  {outside.length>0&&<Banner tom="info" icone={<Info size={14} className="shrink-0"/>}>{outside.length===1?'Uma etapa executada não está':`${outside.length} etapas executadas não estão`} no desenho exibido: {outside.join(', ')}. Consulte na Tabela.</Banner>}
  {unknownStage&&<p role="status" className="text-sm text-dim">A etapa {stage} não aparece no desenho desta corrida. Escolha uma etapa do gráfico ou da tabela.</p>}

  <div className={`grid gap-3 ${focused?'lg:grid-cols-1':inspectorOpen?'lg:grid-cols-[minmax(0,1fr)_320px] xl:grid-cols-[minmax(0,1fr)_352px]':'lg:grid-cols-1'}`}>
   <section hidden={focused} aria-label="Etapas da corrida" className="min-w-0 overflow-hidden rounded-lg border border-edge bg-panel">
    <div className="flex flex-wrap items-center gap-2 border-b border-edge px-3 py-2">
     <div role="group" aria-label="Visualização da execução" className="inline-flex rounded-md border border-edge bg-panel p-0.5">{([['grafo','Gráfico'],['tabela','Tabela']] as const).map(([id,label])=><button key={id} type="button" aria-pressed={view===id} onClick={()=>onView(id)} className={`${VIEW_BUTTON} ${view===id?'bg-blue-50 text-blue-800 font-semibold dark:bg-blue-900/30 dark:text-blue-300':'text-dim hover:text-ink'}`}>{label}</button>)}</div>
     <div className="ml-auto flex flex-wrap items-center gap-2"><Select aria-label="Localizar etapa na corrida" value={node?.id??''} onChange={e=>select(e.target.value||null,true)} className="w-44 xl:w-56"><option value="">Localizar etapa…</option>{snapshot.nodes.map(n=><option key={n.id} value={n.id}>{nodeLabel(n)}{nodeLabel(n)!==n.id?` · ${n.id}`:''}</option>)}</Select>
      <button type="button" aria-label="Investigação" title={inspectorOpen?'Recolher investigação':'Mostrar investigação'} aria-expanded={inspectorOpen} aria-controls={`${panelId}-investigacao`} onClick={()=>setInspectorOpen(open=>!open)} className={`inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-xs focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-600 ${inspectorOpen?'border-blue-300 bg-blue-50 text-blue-800 dark:border-blue-800 dark:bg-blue-900/30 dark:text-blue-300':'border-edge text-ink hover:bg-edge/30'}`}><span className="lg:hidden xl:inline">Investigação</span>{inspectorOpen?<PanelRightClose size={15}/>:<PanelRightOpen size={15}/>}</button></div>
    </div>
    {graphMounted&&<div hidden={view!=='grafo'}><WorkspaceCanvas definition={snapshot} layout={drawing} editable={false} selected={node?.id??null} onSelect={id=>select(id||null)} run={run} focusRequest={focusRequest} label="Canvas da execução" heightClass="h-[460px] lg:h-[max(520px,calc(100dvh-25rem))]"/></div>}
    <div hidden={view!=='tabela'} className="p-3 space-y-3">
     <Input label="Buscar etapa nesta corrida" value={search} onChange={e=>setSearch(e.target.value)} className="sm:max-w-xs"/>
     {!data?<p className="text-sm text-dim py-4">{query.isError?'Sem dados da corrida para listar.':!active||!visible?'Consulta pausada enquanto a aba está oculta.':'Consultando a corrida…'}</p>:!trusted?null:<div className="overflow-x-auto"><table aria-label={`Etapas da corrida ${resolved||'sem identificador'}`} className="w-full text-left text-sm"><thead className="text-xs text-dim"><tr><th scope="col" className="py-2 pr-3 font-medium">Etapa</th><th scope="col" className="py-2 pr-3 font-medium">Estado</th><th scope="col" className="py-2 pr-3 font-medium">Início</th><th scope="col" className="py-2 pr-3 font-medium">Fim</th><th scope="col" className="py-2 pr-3 font-medium">Duração</th><th scope="col" className="py-2 font-medium">Tentativas</th></tr></thead>
      <tbody className="divide-y divide-edge">{steps.map(row=>{const drawn=snapshot.nodes.find(n=>sameStage(n.id,row.job_name));const rowState=runStateFor(overlay,row.job_name);const current=!!node&&sameStage(row.job_name,node.id);return <tr key={row.job_name} aria-current={current?'true':undefined} className={current?'bg-blue-50/60 dark:bg-blue-950/20':undefined}>
       <td className="py-2 pr-3 align-top">{drawn?<button type="button" onClick={()=>select(drawn.id)} className="text-left text-ink font-medium hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-600 [overflow-wrap:anywhere]">{nodeLabel(drawn)}</button>:<span className="text-ink [overflow-wrap:anywhere]">{row.job_name}</span>}<p className="text-xs text-dim mt-0.5">{drawn?typeLabel(drawn.type):'fora do desenho exibido'}</p></td>
       <td className="py-2 pr-3 align-top"><StateLabel state={rowState}/></td>
       <td className="py-2 pr-3 align-top text-dim tabular-nums">{row.inicio?horaLonga(row.inicio):'—'}</td>
       <td className="py-2 pr-3 align-top text-dim tabular-nums">{row.fim?horaLonga(row.fim):row.inicio?'em aberto':'—'}</td>
       <td className="py-2 pr-3 align-top text-dim tabular-nums">{row.duration_seconds!=null?duracaoCurta(row.duration_seconds):'—'}</td>
       <td className="py-2 align-top text-dim tabular-nums">{row.total_tentativas||(row.status?1:0)}</td>
      </tr>})}</tbody></table>
      {!trusted.etapas.length?<p className="text-sm text-dim py-4">Nenhuma etapa nesta corrida.</p>:!steps.length&&<p className="text-sm text-dim py-4">Nenhuma etapa encontrada nesta corrida para a busca.</p>}</div>}
    </div>
    <ul aria-label="Legenda dos estados" className="flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-edge px-3 py-2 text-xs text-dim">{LEGEND.map(([kind,label,hint])=><li key={kind} className="inline-flex items-center gap-1.5"><RunStateIcon kind={kind} size={13}/><span className="text-ink">{label}</span>{hint&&<span>· {hint}</span>}</li>)}<li className="sm:ml-auto">Linha cheia: caminho observado · tracejada: ramo pulado</li></ul>
   </section>
   <div id={`${panelId}-investigacao`} hidden={!inspectorOpen&&!focused} className={focused?'min-w-0 lg:min-h-[max(520px,calc(100dvh-25rem))] [&>aside]:min-h-full lg:[&>aside]:mx-auto lg:[&>aside]:max-w-5xl':'min-w-0 lg:[contain:size] lg:overflow-y-auto [&>aside]:min-h-full'}>
    <WorkspaceRunInspector name={name} data={trusted} runId={resolved||null} phase={phase} live={live} counts={counts} versionNumber={version?.number??null} sourceLabel={drawingSourceLabel(source,version?.number)} definition={snapshot} node={node} step={step} state={state} attempt={attempt} tab={tab} onTab={setTab} onAttempt={value=>onInvestigate(stage||null,value)} onSelect={id=>select(id)} chain={direction} onChain={value=>setChain(value&&stage?{stage,direction:value}:null)} canReprocess={!!caps.actions.reprocess} canPause={!!caps.actions.pauseStages} active={active} visible={visible} actionScope={actionScope} focused={focused} onToggleFocus={()=>setFocused(value=>!value)} onChanged={()=>{void query.refetch()}}/>
   </div>
  </div>
  <Sheet open={historyOpen} onClose={()=>setHistoryOpen(false)} title="Histórico de corridas" widthClass="max-w-4xl"><Suspense fallback={<PageSpinner/>}><WorkspaceRunHistory name={name} enabled={active&&visible} filters={historyFilters} onFilters={setHistoryFilters} currentRunId={resolved||null} onOpen={item=>{setHistoryOpen(false);if(!item.runId)return;if(onOpenRun)onOpenRun(item.runId,item.date);else onRun(item.runId)}}/></Suspense></Sheet>
  {requesting!==null&&<Suspense fallback={null}><WorkspaceRunRequest name={name} open context={active?runScope:''} onClose={()=>setRequesting(null)} onRequested={requestedRun}/></Suspense>}
 </div>
}
