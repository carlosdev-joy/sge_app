import { Suspense, lazy, useId, useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Copy, History, Maximize2, Minimize2, PauseCircle, RefreshCw, ScrollText, X } from 'lucide-react'
import { apiFetch, apiFetchBruto } from '../../lib/api'
import { copyToClipboard } from '../../lib/clipboard'
import { encryptedParameter, nodeLabel, object, text, type WorkspaceDefinition, type WorkspaceNode } from '../../lib/workspace'
import { EXECUTION_POLL, EXECUTION_REVALIDATE_MS, STALE_INTENT_MESSAGE, clockLabel, completionLabel, engineAttemptList, engineAttemptsMatch, engineAttemptsPath, engineAttemptsQueryKey, engineClock, engineGapNote, engineLogSelection, engineReason, engineStateLabel, selectedStageAnnouncement, stageNeighbors, type ChainDirection, type EngineAttempts, type NodeRunState, type RunCounts, type RunPhase } from '../../lib/workspaceExecution'
import { useAuthStore } from '../../store/auth'
import { duracaoCurta, horaLonga, type EtapaExecucaoApi, type PausaApi, type PipelineExecucaoApi } from '../etapas/execucaoEtapas'
import { ValidacaoExecucao } from '../etapas/ValidacaoExecucao'
import { Button } from '../ui/Button'
import { PageSpinner } from '../ui/Spinner'
import { toast } from '../ui/Toast'
import { typeLabel } from './workspaceCatalog'
import { RunPhaseBadge, StateLabel } from './WorkspaceRunStatus'

export type RunInspectorTab = 'resumo' | 'tentativas' | 'logs' | 'parametros'
// Confirmações carregadas só ao abrir: ficam fora da entrada da Execução.
const ModalRerunEtapa = lazy(() => import('../etapas/ModalRerunEtapa').then(module => ({ default: module.ModalRerunEtapa })))
const ModalPausaEtapa = lazy(() => import('../etapas/ModalPausaEtapa').then(module => ({ default: module.ModalPausaEtapa })))
const TABS: readonly (readonly [RunInspectorTab, string])[] = [['resumo', 'Resumo'], ['tentativas', 'Tentativas'], ['logs', 'Logs'], ['parametros', 'Parâmetros']]
const TAB_BUTTON = 'inline-flex items-center border-b-2 -mb-px px-2 py-1.5 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-600'
const ACTION_NOTE = 'Cancelar uma pausa de etapa não encerra o job remoto. O workspace não oferece cancelamento geral da execução.'
// A tentativa SQL é o ciclo da etapa no Orquestra; o log segue o try_number do motor.
const OPERATIONAL_NOTE = 'Contadas pelo início da etapa no Orquestra (execução e reprocessamento). Retries automáticos do motor não entram nesta contagem e o número não identifica o log; horários da telemetria das etapas.'
// Reprocessar não é executar tudo: a confirmação mostra as etapas que o servidor
// vai limpar nesta corrida e pergunta, à parte, sobre os pipelines dependentes.
const REPROCESS_HINT = 'Retoma esta corrida a partir desta etapa; não executa o pipeline inteiro. A confirmação lista as etapas atingidas e pergunta se os pipelines dependentes também rodam.'

interface AttemptRow { attempt: number; status: string | null; inicio: string | null; fim: string | null; duration_seconds: number | null; host: string | null; current: boolean }
function attemptRows(step: EtapaExecucaoApi | undefined): AttemptRow[] {
 if (!step) return []
 const rows: AttemptRow[] = step.tentativas.filter(t => typeof t.attempt === 'number').map(t => ({ attempt: t.attempt!, status: t.status, inicio: t.inicio, fim: t.fim, duration_seconds: t.duration_seconds, host: t.host, current: false }))
 if (typeof step.attempt === 'number' && step.status) rows.push({ attempt: step.attempt, status: step.status, inicio: step.inicio, fim: step.fim, duration_seconds: step.duration_seconds, host: step.host, current: true })
 return rows.sort((a, b) => b.attempt - a.attempt)
}

// `enabled`: aba Execução exibida e navegador visível; fora disso nem a primeira
// leitura acontece, e ao voltar o log é revalidado.
function TaskLog({ name, runId, task, attempt, enabled }: { name: string; runId: string; task: string; attempt: number; enabled: boolean }) {
 const token = useAuthStore(s => s.token)
 const log = useQuery({ queryKey: ['workspace-log', token, name, runId, task, attempt], queryFn: async ({ signal }) => (await apiFetchBruto(`/pipeline-task-log?${new URLSearchParams({ pipeline_name: name, run_id: runId, task_id: task, try_number: String(attempt) })}`, { signal })).text(), enabled: enabled && !!token, refetchOnWindowFocus: false, retry: false })
 return <section className="min-w-0 space-y-2" aria-label="Log da tentativa">
  <div className="flex flex-wrap items-center justify-between gap-2"><h3 className="text-sm font-semibold text-ink">{task} · tentativa {attempt} · Airflow</h3><div className="flex gap-1"><Button variant="ghost" size="sm" disabled={!log.data} onClick={async () => { if (log.data && await copyToClipboard(log.data)) toast.success('Log copiado'); else toast.error('Não foi possível copiar o log') }}><Copy size={14} />Copiar</Button><Button variant="ghost" size="sm" loading={log.isFetching} onClick={() => log.refetch()}><RefreshCw size={14} />Atualizar</Button></div></div>
  {log.isPending && !enabled ? <p className="text-sm text-dim">Leitura do log pausada enquanto a aba está oculta.</p> : log.isPending ? <PageSpinner /> : log.isError ? <p role="alert" className="text-sm text-red-700 dark:text-red-400">{log.error.message} <Button variant="secondary" size="sm" onClick={() => log.refetch()}>Tentar novamente</Button></p> : log.data ? <pre className="max-h-[min(60vh,560px)] overflow-auto rounded-md border border-edge bg-canvas p-3 text-xs leading-relaxed text-ink whitespace-pre-wrap break-words">{log.data}</pre> : <p className="text-sm text-dim">Esta tentativa ainda não possui conteúdo de log.</p>}
 </section>
}

export interface RunInspectorProps {
 name: string
 data: PipelineExecucaoApi | undefined
 /** corrida exibida (resolvida pela identidade); sem ela não há log nem ação */
 runId: string | null
 phase: RunPhase
 /** corrida atual com telemetria confiável: só então algo indica atividade */
 live: boolean
 counts: RunCounts | null
 versionNumber: number | null
 sourceLabel: string
 definition: WorkspaceDefinition
 node: WorkspaceNode | null
 step: EtapaExecucaoApi | undefined
 state: NodeRunState | null
 attempt: number | null
 tab: RunInspectorTab
 onTab: (tab: RunInspectorTab) => void
 onAttempt: (attempt: number | null) => void
 onSelect: (stage: string | null) => void
 chain: ChainDirection | null
 onChain: (direction: ChainDirection | null) => void
 canReprocess: boolean
 canPause: boolean
 active: boolean
 /** navegador visível: com a aba oculta nenhuma leitura sob demanda acontece */
 visible: boolean
 /** identidade atual (sessão, pipeline, data, corrida, etapa, capacidades):
  *  a confirmação aberta só vale enquanto ela for a mesma */
 actionScope: string
 focused: boolean
 onToggleFocus: () => void
 onChanged: () => void
}

interface ActionIntent { kind: 'rerun' | 'pause'; scope: string; token: string | null; pipeline: string; runId: string | null; date: string | null; taskId: string; jobName: string; pauseId: number | null }

export function WorkspaceRunInspector(p: RunInspectorProps) {
 const id = useId()
 const token = useAuthStore(s => s.token)
 // A confirmação congela o alvo que a abriu. Mudou sessão, pipeline, data,
 // corrida, etapa, capacidade ou a pausa pendente, ou a aba saiu de cena: a
 // intenção é descartada (não reaparece nem passa a mirar outro alvo).
 const [intent, setIntent] = useState<ActionIntent | null>(null)
 const pendingNow = p.node ? p.data?.pausas?.find(row => row.job_name.trim().toLowerCase() === p.node!.id.trim().toLowerCase() && row.estado.toUpperCase() === 'PENDENTE') ?? null : null
 const allowedNow = intent?.kind === 'rerun' ? p.canReprocess : intent?.kind === 'pause' ? p.canPause : false
 if (intent && (!p.active || intent.scope !== p.actionScope || intent.token !== token || !allowedNow || (intent.kind === 'pause' && intent.pauseId !== (pendingNow?.id ?? null)))) setIntent(null)
 // Conferido de novo no instante do envio, contra o estado mais recente.
 const latest = useRef({ scope: p.actionScope, active: p.active, pauseId: pendingNow?.id ?? null })
 useLayoutEffect(() => { latest.current = { scope: p.actionScope, active: p.active, pauseId: pendingNow?.id ?? null } })
 const guardFor = (opened: ActionIntent) => () => useAuthStore.getState().token !== opened.token || !latest.current.active || latest.current.scope !== opened.scope || (opened.kind === 'pause' && latest.current.pauseId !== opened.pauseId) ? STALE_INTENT_MESSAGE : null
 // Anúncio só quando muda a etapa selecionada ou o estado dela, nunca a cada consulta.
 const announcement = p.node ? selectedStageAnnouncement(p.node.id, p.state) : null
 const [spoken, setSpoken] = useState<{ key: string | null; message: string }>({ key: null, message: '' })
 if ((announcement?.key ?? null) !== spoken.key) setSpoken({ key: announcement?.key ?? null, message: announcement?.message ?? '' })
 const message = spoken.message
 // Tentativas do motor: só com uma etapa da corrida aberta em Tentativas ou Logs,
 // a aba Execução exibida e o navegador visível. Chave por sessão, pipeline,
 // corrida e tarefa; resposta de outro alvo não é usada.
 const engineTask = p.node && p.runId ? p.step?.task_id ?? null : null
 const engineWanted = !!engineTask && (p.tab === 'tentativas' || p.tab === 'logs')
 const engineReading = engineWanted && p.active && p.visible && !!token
 const engine = useQuery({ queryKey: engineAttemptsQueryKey(token, p.name, p.runId ?? '', engineTask ?? ''), queryFn: ({ signal }) => apiFetch<EngineAttempts>(engineAttemptsPath(p.name, p.runId!, engineTask!), { signal }), enabled: engineReading, staleTime: EXECUTION_REVALIDATE_MS, retry: false, refetchOnWindowFocus: false, refetchInterval: engineReading && p.live ? EXECUTION_POLL.fallbackMs : false, refetchIntervalInBackground: false })
 const engineData = engineTask && engineAttemptsMatch(engine.data, { name: p.name, runId: p.runId!, task: engineTask }) ? engine.data : undefined
 const engineRows = engineAttemptList(engineData)
 const pending = pendingNow
 const live = <p aria-live="polite" role="status" className="sr-only">{message}</p>
 const header = (title: string, subtitle: string) => <div className="flex items-start justify-between gap-2"><div className="min-w-0"><h2 className="text-sm font-semibold text-ink [overflow-wrap:anywhere]">{title}</h2><p className="text-xs text-dim mt-1 [overflow-wrap:anywhere]">{subtitle}</p></div><div className="flex shrink-0 gap-1"><Button variant="ghost" size="sm" aria-label={p.focused ? 'Voltar ao canvas' : 'Expandir investigação'} title={p.focused ? 'Voltar ao canvas (Esc)' : 'Expandir a investigação sobre o canvas'} aria-pressed={p.focused} onClick={p.onToggleFocus}>{p.focused ? <Minimize2 size={16} /> : <Maximize2 size={16} />}</Button>{p.node && <Button variant="ghost" size="sm" aria-label="Fechar investigação da etapa" onClick={() => p.onSelect(null)}><X size={16} /></Button>}</div></div>

 if (!p.node) return <aside className="relative bg-panel border border-edge rounded-lg p-4 min-w-0 space-y-4" aria-label="Resumo da corrida">{live}
  {header('Corrida', p.runId ?? 'Nenhuma corrida selecionada')}
  <RunPhaseBadge phase={p.phase} live={p.live} />
  {p.runId ? <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
   <div className="col-span-2"><dt className="text-xs text-dim">Identificador</dt><dd className="text-ink font-mono text-xs break-all mt-0.5">{p.runId}</dd></div>
   <div><dt className="text-xs text-dim">Data de referência</dt><dd className="text-ink mt-0.5">{p.data?.data_referencia ?? '—'}</dd></div>
   <div><dt className="text-xs text-dim">Versão</dt><dd className="text-ink mt-0.5">{p.versionNumber != null ? `Versão ${p.versionNumber}` : 'Não vinculada'}</dd></div>
   <div><dt className="text-xs text-dim">Origem</dt><dd className="text-ink mt-0.5 [overflow-wrap:anywhere]">{p.data?.corrida?.disparado_por ?? 'Não informada'}</dd></div>
   <div><dt className="text-xs text-dim">Situação registrada</dt><dd className="text-ink mt-0.5">{p.data?.corrida?.status ?? 'Sem registro'}</dd></div>
   {p.counts && <div className="col-span-2"><dt className="text-xs text-dim">Etapas</dt><dd className="text-ink mt-0.5">{completionLabel(p.counts)}{p.counts.failed ? ` · ${p.counts.failed} com falha` : ''}{p.counts.running ? ` · ${p.counts.running} executando` : ''}{p.counts.skipped ? ` · ${p.counts.skipped} puladas` : ''}</dd></div>}
  </dl> : <p className="text-sm text-dim">Escolha uma corrida pelo Histórico ou pela data de referência. Sem corrida selecionada, nenhuma etapa aparece em andamento.</p>}
  <p className="text-xs text-dim border-t border-edge pt-3">{p.sourceLabel}</p>
  {p.runId && <ValidacaoExecucao pipeline={p.name} runId={p.runId} active={p.active} enabled={p.active && p.visible} />}
  <p className="text-xs text-dim">Selecione uma etapa no gráfico ou na tabela para consultar tentativas, logs e ações.</p>
 </aside>

 const node = p.node, step = p.step, task = step?.task_id ?? null
 // Reprocessar mira a tarefa real do Airflow; o id do nó só vale sem task_id.
 const rerunTask = task || node.id
 const rows = attemptRows(step)
 const selection = engineLogSelection(engineRows, p.attempt)
 const logAttempts = engineRows.filter(row => row.has_log).map(row => row.try_number)
 const engineGap = engineData ? engineGapNote(engineData, engineRows) : null
 // Situação que impede listar as tentativas do motor (null: há tentativas a listar).
 const engineIssue: ReactNode = !p.runId ? <p className="text-sm text-dim">Selecione uma corrida para consultar as tentativas do motor.</p>
  : !task ? <p className="text-sm text-dim">A etapa não tem identificador de tarefa nesta corrida; o motor não é consultado e não há log para abrir.</p>
  : engine.isPending && !engineReading ? <p className="text-sm text-dim">Consulta ao motor pausada enquanto a aba está oculta.</p>
  : engine.isPending ? <PageSpinner />
  : engine.isError && !engineData ? <p role="alert" className="text-sm text-red-700 dark:text-red-400">{engine.error.message} <Button variant="secondary" size="sm" onClick={() => engine.refetch()}>Tentar novamente</Button></p>
  : !engineData ? <p role="status" className="text-sm text-dim">A resposta do motor não corresponde a esta etapa e corrida; nada dela foi usado.</p>
  : !engineRows.length ? <p role="status" className="text-sm text-dim">{engineReason(engineData)}</p>
  : null
 const { before, after } = stageNeighbors(p.definition, node.id)
 const params = Array.isArray(node.configuration.etl_pipeline_job_param) ? node.configuration.etl_pipeline_job_param.map(object) : []
 const statusCode = step?.status ?? null
 const pausable = (p.data?.etapas ?? []).filter(row => !(row.status ?? '').trim() && !(p.data?.pausas ?? []).some(x => x.estado.toUpperCase() === 'PENDENTE' && x.job_name.trim().toLowerCase() === row.job_name.trim().toLowerCase())).map(row => row.job_name)
 const history: PausaApi[] = (p.data?.pausas ?? []).filter(row => row.job_name.trim().toLowerCase() === node.id.trim().toLowerCase())
 const pauseLabel = pending ? (pending.aguardando_desde ? 'Em espera — liberar' : 'Pausa marcada') : statusCode || p.data?.portao === 'dag_sem_portao' ? 'Pausar…' : 'Pausar aqui'
 function open(kind: ActionIntent['kind']) {
  if (!p.active || (kind === 'rerun' ? !p.canReprocess || !p.runId || !step : !p.canPause)) return
  setIntent({ kind, scope: p.actionScope, token, pipeline: p.name, runId: p.runId, date: p.data?.data_referencia ?? null, taskId: rerunTask, jobName: node.id, pauseId: pending?.id ?? null })
 }
 function close() { setIntent(null); p.onChanged() }
 const content: Record<RunInspectorTab, () => ReactNode> = {
  resumo: () => <div className="space-y-4">
   <StateLabel state={p.state} />
   {p.state && <p className="text-xs text-dim">{p.state.detail}</p>}
   <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
    <div><dt className="text-xs text-dim">Início</dt><dd className="text-ink mt-0.5 tabular-nums">{step?.inicio ? horaLonga(step.inicio) : '—'}</dd></div>
    <div><dt className="text-xs text-dim">Fim</dt><dd className="text-ink mt-0.5 tabular-nums">{step?.fim ? horaLonga(step.fim) : step?.inicio ? 'em aberto' : '—'}</dd></div>
    <div><dt className="text-xs text-dim">Duração</dt><dd className="text-ink mt-0.5 tabular-nums">{step?.duration_seconds != null ? duracaoCurta(step.duration_seconds) : '—'}</dd></div>
    <div><dt className="text-xs text-dim">Tentativa operacional</dt><dd className="text-ink mt-0.5 tabular-nums">{step?.attempt != null ? `${step.attempt} de ${Math.max(step.total_tentativas, step.attempt)}` : '—'}</dd></div>
    {step?.host && <div className="col-span-2"><dt className="text-xs text-dim">Host</dt><dd className="text-ink mt-0.5 break-all">{step.host}</dd></div>}
   </dl>
   <p className="text-xs text-dim">Horários da telemetria das etapas; o registro da corrida usa outro relógio.</p>
   {pending && <p className="rounded-md border border-fuchsia-300 bg-fuchsia-50 px-3 py-2 text-xs text-fuchsia-800 dark:border-fuchsia-800 dark:bg-fuchsia-950/30 dark:text-fuchsia-200">{pending.aguardando_desde ? `Parada no portão${pending.parado_min != null ? ` há ${pending.parado_min} min` : ''}, aguardando liberação.` : 'Pausa marcada: a etapa para aqui quando chegar; ainda não está parada.'}{pending.motivo ? ` Motivo: ${pending.motivo}.` : ''}</p>}
   {step && !step.no_desenho && <p className="text-xs text-dim">Esta etapa executou, mas não está no desenho exibido.</p>}
   <section aria-label="Dependências da etapa" className="border-t border-edge pt-3 space-y-2">
    <h3 className="text-xs font-semibold text-ink">Dependências</h3>
    <DependencyList label="Depende de" ids={before} empty="Inicia o fluxo" onSelect={p.onSelect} />
    <DependencyList label="Libera" ids={after} empty="Nenhuma etapa depende desta" onSelect={p.onSelect} />
    <div role="group" aria-label="Destacar cadeia no canvas" className="flex flex-wrap gap-1 pt-1">{([['ambos', 'Cadeia completa'], ['tras', 'Antes'], ['frente', 'Depois']] as const).map(([value, label]) => <button key={value} type="button" aria-pressed={p.chain === value} onClick={() => p.onChain(p.chain === value ? null : value)} className={`rounded-md border px-2 py-1 text-xs focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-600 ${p.chain === value ? 'border-blue-300 bg-blue-50 text-blue-800 dark:border-blue-800 dark:bg-blue-900/30 dark:text-blue-300' : 'border-edge text-ink hover:bg-edge/30'}`}>{label}</button>)}</div>
   </section>
  </div>,
  tentativas: () => <div className="space-y-4">
   <section aria-label="Tentativas do motor" className="space-y-2">
    <div className="flex flex-wrap items-center justify-between gap-2"><h3 className="text-xs font-semibold text-ink">Tentativas do motor (Airflow)</h3>{task && p.runId && <Button variant="ghost" size="sm" disabled={!engineReading} loading={engine.isFetching} onClick={() => engine.refetch()}><RefreshCw size={14} />Atualizar</Button>}</div>
    {engineIssue ?? <><ol className="space-y-2">{engineRows.map(row => <li key={row.try_number} className="rounded-md border border-edge p-3 text-sm"><div className="flex flex-wrap items-center justify-between gap-2"><span className="font-medium text-ink">Tentativa {row.try_number}{row.current ? ' · atual' : ''}</span><span className="text-xs text-dim">{engineStateLabel(row.state)}</span></div><p className="text-xs text-dim mt-1 tabular-nums">{row.started ? `${engineClock(row.start_date)} → ${row.end_date ? engineClock(row.end_date) : row.state === 'running' ? 'em aberto' : 'sem fim registrado'}` : 'Sem início registrado no motor'}{row.duration != null ? ` · ${duracaoCurta(row.duration)}` : ''}{row.hostname ? ` · ${row.hostname}` : ''}</p>{row.has_log ? <Button className="mt-2" variant="secondary" size="sm" aria-pressed={selection.attempt === row.try_number && p.tab === 'logs'} onClick={() => { p.onAttempt(row.try_number); p.onTab('logs') }}><ScrollText size={14} />Ver log</Button> : <p className="mt-2 text-xs text-dim">Sem log: a tentativa não iniciou no motor.</p>}</li>)}</ol>
     {engineGap && <p className="text-xs text-dim">{engineGap}</p>}</>}
    {engineData && <p className="text-xs text-dim">Origem: motor Airflow, instância e histórico desta tarefa nesta corrida{engine.dataUpdatedAt ? ` · consultado às ${clockLabel(engine.dataUpdatedAt)}` : ''}{engine.isError ? ' · a última consulta falhou; mostrando a anterior' : ''}.</p>}
   </section>
   <section aria-label="Tentativas operacionais" className="space-y-2 border-t border-edge pt-3">
    <h3 className="text-xs font-semibold text-ink">Tentativas operacionais (registro do Orquestra)</h3>
    <p className="text-xs text-dim">{OPERATIONAL_NOTE}</p>
    {rows.length ? <ol className="space-y-2">{rows.map(row => <li key={row.attempt} className="rounded-md border border-edge p-3 text-sm"><div className="flex flex-wrap items-center justify-between gap-2"><span className="font-medium text-ink">Tentativa operacional {row.attempt}{row.current ? ' · atual' : ''}</span><span className="text-xs text-dim">{row.status ?? 'sem estado'}</span></div><p className="text-xs text-dim mt-1 tabular-nums">{horaLonga(row.inicio)} → {row.fim ? horaLonga(row.fim) : 'em aberto'}{row.duration_seconds != null ? ` · ${duracaoCurta(row.duration_seconds)}` : ''}{row.host ? ` · ${row.host}` : ''}</p></li>)}</ol> : <p className="text-sm text-dim">{step?.status ? 'A telemetria não informou tentativas numeradas.' : 'Esta etapa ainda não tem tentativas nesta corrida.'}</p>}
   </section>
  </div>,
  logs: () => engineIssue ?? <div className="space-y-3">{(logAttempts.length > 1 || (selection.issue !== null && logAttempts.length > 0)) && <div role="group" aria-label="Tentativa do log" className="flex flex-wrap gap-1">{logAttempts.map(value => <Button key={value} variant="secondary" size="sm" aria-pressed={value === selection.attempt} onClick={() => p.onAttempt(value)}>Tentativa {value}</Button>)}</div>}
   {selection.issue === 'fora' ? <p role="status" className="text-sm text-dim">A tentativa {selection.attempt} não consta no motor para a etapa {node.id} nesta corrida. Abra uma das tentativas listadas.</p>
    : selection.issue === 'sem-inicio' ? <p role="status" className="text-sm text-dim">{selection.attempt !== null ? `A tentativa ${selection.attempt} da etapa ${node.id} não iniciou no motor; não há log.` : `Nenhuma tentativa da etapa ${node.id} iniciou no motor; não há log.`}</p>
    : selection.issue === 'sem-log' || selection.attempt === null ? <p role="status" className="text-sm text-dim">A etapa {node.id} ainda não tem tentativas no motor nesta corrida.</p>
    : <TaskLog key={`${p.name}:${p.runId}:${task}:${selection.attempt}`} name={p.name} runId={p.runId!} task={task!} attempt={selection.attempt} enabled={p.active && p.visible} />}</div>,
  parametros: () => params.length ? <dl className="space-y-3 text-sm">{params.map((param, index) => <div key={index}><dt className="text-xs text-dim break-words">{text(param.param_name) || text(param.name)}</dt><dd className="text-ink break-words mt-0.5">{encryptedParameter(param) ? 'Valor protegido na origem' : text(param.param_value) || text(param.value) || 'Não informado'}</dd></div>)}<p className="text-xs text-dim">Valores da definição exibida; o valor efetivo da execução pode vir do pipeline ou da data de referência.</p></dl> : <p className="text-sm text-dim">Nenhum parâmetro de etapa nesta definição.</p>,
 }
 return <aside className="relative bg-panel border border-edge rounded-lg p-4 min-w-0" aria-label="Investigação da etapa">{live}
  {header(nodeLabel(node), `${typeLabel(node.type)}${nodeLabel(node) !== node.id ? ` · ${node.id}` : ''}`)}
  <div role="group" aria-label="Seções da investigação" className="mt-4 mb-4 flex flex-wrap gap-x-1 border-b border-edge">{TABS.map(([tab, label]) => <button key={tab} type="button" aria-pressed={p.tab === tab} aria-controls={`${id}-${tab}`} onClick={() => p.onTab(tab)} className={`${TAB_BUTTON} ${p.tab === tab ? 'border-blue-600 font-medium text-ink dark:border-blue-400' : 'border-transparent text-dim hover:text-ink'}`}>{label}{tab === 'tentativas' && engineRows.length > 1 && <span className="ml-1.5 text-xs text-dim tabular-nums">{engineRows.length}</span>}</button>)}</div>
  {TABS.map(([tab, label]) => <section key={tab} id={`${id}-${tab}`} aria-label={label} hidden={p.tab !== tab} className="min-w-0">{p.tab === tab && content[tab]()}</section>)}
  {(p.canReprocess || p.canPause) && <div className="mt-5 border-t border-edge pt-4 space-y-2"><div className="flex flex-wrap gap-2">
   {p.canReprocess && <Button variant="secondary" size="sm" disabled={!p.runId || !step || !p.active} title={REPROCESS_HINT} onClick={() => open('rerun')}><History size={14} />Reprocessar a partir desta etapa</Button>}
   {p.canPause && <Button variant="secondary" size="sm" disabled={!p.active} onClick={() => open('pause')}><PauseCircle size={14} />{pauseLabel}</Button>}
  </div><p className="text-xs text-dim">{ACTION_NOTE}</p></div>}
  {intent && <Suspense fallback={null}>{intent.kind === 'rerun' ? <ModalRerunEtapa open onClose={close} pipeline={intent.pipeline} taskId={intent.taskId} jobName={intent.jobName} dataReferencia={intent.date} runId={intent.runId} status={statusCode} guard={guardFor(intent)} /> : <ModalPausaEtapa open onClose={close} pipeline={intent.pipeline} jobName={intent.jobName} dataReferencia={intent.date} runId={intent.runId} status={statusCode} pausa={pending} historico={history} etapasPausaveis={pausable} portao={p.data?.portao ?? null} guard={guardFor(intent)} />}</Suspense>}
 </aside>
}

function DependencyList({ label, ids, empty, onSelect }: { label: string; ids: string[]; empty: string; onSelect: (id: string) => void }) {
 return <div className="text-sm"><p className="text-xs text-dim">{label}</p>{ids.length ? <ul className="mt-1 flex flex-wrap gap-1">{ids.map(id => <li key={id}><button type="button" onClick={() => onSelect(id)} className="rounded border border-edge px-2 py-0.5 text-xs text-ink hover:bg-edge/30 focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-600 [overflow-wrap:anywhere]">{id}</button></li>)}</ul> : <p className="text-ink mt-0.5">{empty}</p>}</div>
}
