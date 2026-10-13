// Execução do Pipeline (F5 da UX profissional): contrato puro do visualizador
// operacional comum. Decide estado de etapa, ligação e corrida, frequência de
// consulta, frescor, anúncio acessível, a solicitação guiada e os filtros do
// histórico. Sem React: a bancada tests/js/workspace_execution_harness.cjs
// executa este arquivo como está.
import type { CorridaApi, EtapaExecucaoApi, IdentidadeApi, PausaApi } from '../components/etapas/execucaoEtapas'
import type { WorkspaceDefinition } from './workspace'

const key = (value: string | null | undefined) => String(value ?? '').trim().toLowerCase()
const upper = (value: string | null | undefined) => String(value ?? '').trim().toUpperCase()

// ── Identidade da leitura ──────────────────────────────────────────────────
// Uma chave por sessão, pipeline, data e corrida: resposta de outra identidade
// nunca ocupa a tela atual (o React Query descarta e cancela pela chave).
export function executionQueryKey(token: string | null, name: string, date: string, runId: string) {
 return ['workspace-execution', token, name, date, runId] as const
}
export function executionRequestPath(name: string, date: string, runId: string): string {
 // A corrida explícita prevalece: mandar a data junto pediria ao servidor que escolhesse de novo.
 return `/workspace/executions?${new URLSearchParams({ name, ...(runId ? { runId } : date ? { date } : {}) })}`
}
// A resposta só descreve a corrida pedida se a identidade devolvida for ela.
export function responseMatchesRun(identity: Pick<IdentidadeApi, 'run_id' | 'dag_run_id'> | null | undefined, runId: string): boolean {
 if (!runId) return true
 return !!identity && (identity.run_id === runId || identity.dag_run_id === runId)
}
/** A resposta inteira (desenho, versão, título, estados) só vale para o pedido
 *  que a originou: o mesmo pipeline, pela grafia exata pedida ou pela grafia
 *  oficial informada pelo contexto (o mesmo run_id pode existir em outra DAG);
 *  a corrida pedida; e, sem corrida, a data pedida. */
export function responseMatchesRequest(response: { pipeline_name?: string | null; data_referencia?: string | null; identidade?: Pick<IdentidadeApi, 'run_id' | 'dag_run_id'> | null } | null | undefined, request: { names: readonly string[]; date: string; runId: string }): boolean {
 if (!response || typeof response.pipeline_name !== 'string' || !request.names.includes(response.pipeline_name)) return false
 if (request.runId) return responseMatchesRun(response.identidade, request.runId)
 return !request.date || !response.data_referencia || response.data_referencia === request.date
}
/** Identidade de uma intenção operacional (reprocessar, pausar, executar):
 *  aberta para uma sessão, pipeline, data, corrida, etapa e capacidade, ela
 *  não vale para outra. Mudou qualquer parte, a intenção é descartada. */
export function operationScope(parts: { token: string | null; name: string; date: string | null; runId: string | null; stage?: string | null; capabilities: readonly boolean[] }): string {
 return JSON.stringify([parts.token ?? '', parts.name, parts.date ?? '', parts.runId ?? '', parts.stage ?? '', parts.capabilities])
}
export const STALE_INTENT_MESSAGE = 'A sessão, a corrida, a etapa ou a permissão mudou desde que a confirmação foi aberta. Nada foi enviado; abra a ação novamente.'

// ── Estado da etapa ────────────────────────────────────────────────────────
export type NodeRunKind = 'none' | 'running' | 'success' | 'failed' | 'skipped' | 'gate' | 'unknown'
export interface NodeRunState {
 kind: NodeRunKind
 label: string
 /** status cru da telemetria (ou null sem linha) */
 code: string | null
 attempt: number | null
 attempts: number
 /** pausa pedida que ainda não segurou a etapa: marcador adicional, não estado */
 pauseMarked: boolean
 /** indicador de atividade: só com telemetria atual confiável */
 animate: boolean
 detail: string
}
/** `live`: corrida atual, fonte respondendo e aba visível. Sem isso nada anima. */
export function nodeRunState(step: EtapaExecucaoApi | undefined, pause: PausaApi | undefined, live: boolean): NodeRunState {
 const attempt = step?.attempt ?? null
 const attempts = step ? step.total_tentativas || (step.status ? 1 : 0) : 0
 const pending = pause && upper(pause.estado) === 'PENDENTE' ? pause : undefined
 const base = { attempt, attempts, pauseMarked: !!pending && !pending.aguardando_desde, animate: false }
 if (pending?.aguardando_desde) return { ...base, kind: 'gate', code: 'EM_ESPERA', label: 'Em espera no portão', detail: pending.parado_min != null ? `Parada há ${pending.parado_min} min aguardando liberação` : 'Aguardando liberação', pauseMarked: false }
 const code = step?.status ? step.status.trim() : ''
 if (!step || !code) return { ...base, kind: 'none', code: null, label: 'Sem telemetria', detail: step && !step.no_desenho ? 'Etapa fora do desenho exibido' : 'Nenhum registro desta etapa nesta corrida' }
 switch (code.toUpperCase()) {
  case 'SUCCESS': return { ...base, kind: 'success', code, label: 'Concluída', detail: 'Sucesso confirmado pela telemetria desta tentativa' }
  case 'FAILED': return { ...base, kind: 'failed', code, label: 'Falhou', detail: step.status_code ? `Código ${step.status_code}` : 'Falha registrada pela telemetria' }
  case 'SKIPPED': return { ...base, kind: 'skipped', code, label: 'Pulada', detail: 'Ramo não tomado; não conta como sucesso' }
  case 'RUNNING': return live
   ? { ...base, kind: 'running', code, label: 'Executando', animate: true, detail: 'Telemetria ativa' }
   : { ...base, kind: 'running', code, label: 'Último registro: executando', detail: 'Sem confirmação atual da telemetria' }
  default: return { ...base, kind: 'unknown', code, label: `Estado ${code}`, detail: 'Estado informado pela origem sem tradução nesta tela' }
 }
}
/** Etapa do desenho sem linha nesta corrida: neutra e dita, nunca verde. */
export const NO_TELEMETRY: NodeRunState = nodeRunState(undefined, undefined, false)
export function runOverlay(steps: EtapaExecucaoApi[], pauses: PausaApi[] | undefined, live: boolean): Map<string, NodeRunState> {
 const byStep = new Map<string, EtapaExecucaoApi>()
 // Uma linha por etapa: em empate vence a tentativa mais recente.
 for (const step of steps) { const id = key(step.job_name); const current = byStep.get(id); if (id && (!current || (current.attempt ?? 0) < (step.attempt ?? 0))) byStep.set(id, step) }
 const byPause = new Map<string, PausaApi>()
 for (const pause of pauses ?? []) if (upper(pause.estado) === 'PENDENTE') byPause.set(key(pause.job_name), pause)
 const ids = new Set([...byStep.keys(), ...byPause.keys()])
 return new Map([...ids].map(id => [id, nodeRunState(byStep.get(id), byPause.get(id), live)]))
}
export const runStateFor = (overlay: Map<string, NodeRunState> | null, id: string) => overlay?.get(key(id)) ?? null

// ── Dependências da etapa (realce no canvas) ───────────────────────────────
export const workspaceEdgeId = (edge: { source: string; target: string; branch?: unknown }) => JSON.stringify([edge.source, edge.target, edge.branch ?? null])
export type ChainDirection = 'ambos' | 'tras' | 'frente'
export function stageNeighbors(definition: WorkspaceDefinition, stage: string): { before: string[]; after: string[] } {
 return { before: [...new Set(definition.edges.filter(e => e.target === stage).map(e => e.source))], after: [...new Set(definition.edges.filter(e => e.source === stage).map(e => e.target))] }
}
/** Cadeia transitiva da etapa: o que ela espera (trás) e o que espera por ela (frente). */
export function stageChain(definition: WorkspaceDefinition, stage: string, direction: ChainDirection): { nodes: Set<string>; edges: Set<string>; before: number; after: number } | null {
 if (!definition.nodes.some(node => node.id === stage)) return null
 const walk = (forward: boolean) => {
  const seen = new Set<string>(), edges = new Set<string>(), queue = [stage]
  while (queue.length) {
   const id = queue.pop()!
   for (const edge of definition.edges) {
    const from = forward ? edge.source : edge.target, to = forward ? edge.target : edge.source
    if (from !== id) continue
    edges.add(workspaceEdgeId(edge))
    if (!seen.has(to)) { seen.add(to); queue.push(to) }
   }
  }
  seen.delete(stage)
  return { seen, edges }
 }
 const back = direction === 'frente' ? { seen: new Set<string>(), edges: new Set<string>() } : walk(false)
 const ahead = direction === 'tras' ? { seen: new Set<string>(), edges: new Set<string>() } : walk(true)
 return { nodes: new Set([stage, ...back.seen, ...ahead.seen]), edges: new Set([...back.edges, ...ahead.edges]), before: back.seen.size, after: ahead.seen.size }
}

// ── Ligações ───────────────────────────────────────────────────────────────
// Observada: a origem terminou com sucesso e o destino começou nesta corrida.
// Pulada: uma das pontas foi pulada. O resto é desconhecido; não saber não é negar.
export type EdgeRunKind = 'observed' | 'skipped' | 'unknown'
export function edgeRunState(source: NodeRunState | null, target: NodeRunState | null): EdgeRunKind {
 if (source?.kind === 'skipped' || target?.kind === 'skipped') return 'skipped'
 const started = upper(target?.code) === 'RUNNING' || upper(target?.code) === 'SUCCESS' || upper(target?.code) === 'FAILED'
 return upper(source?.code) === 'SUCCESS' && started ? 'observed' : 'unknown'
}

// ── Estado da corrida ──────────────────────────────────────────────────────
export type RunPhase = 'none' | 'requested' | 'queued' | 'waiting' | 'running' | 'success' | 'failed' | 'skipped' | 'not-released' | 'unknown'
export const RUN_PHASE_LABEL: Record<RunPhase, string> = { none: 'Nenhuma corrida', requested: 'Solicitado', queued: 'Em fila', waiting: 'Aguardando dependência', running: 'Executando', success: 'Concluída', failed: 'Falhou', skipped: 'Pulada', 'not-released': 'Não liberou dependentes', unknown: 'Estado não confirmado' }
const PHASE_BY_STATUS: Record<string, RunPhase> = { SUCESSO: 'success', SUCCESS: 'success', FALHA: 'failed', FAILED: 'failed', EXECUTANDO: 'running', RUNNING: 'running', QUEUED: 'queued', AGUARDANDO: 'queued', AGUARDANDO_DEPENDENCIA: 'waiting', PULADO: 'skipped', SKIPPED: 'skipped', NAO_LIBEROU: 'not-released' }
export function runStatusPhase(status: string | null | undefined): RunPhase { return status ? PHASE_BY_STATUS[upper(status)] ?? 'unknown' : 'unknown' }
export interface RequestedRun { name: string; runId: string; state: string | null }
/** Solicitado, em fila e executando são fatos diferentes: o recebimento do
 *  pedido não significa que o motor começou. */
export function runPhase(input: { name: string; runId: string; requested: RequestedRun | null; identity: Pick<IdentidadeApi, 'run_id' | 'dag_run_id'> | null | undefined; corrida: Pick<CorridaApi, 'status'> | null | undefined }): RunPhase {
 const registered = !!input.corrida && responseMatchesRun(input.identity, input.runId)
 if (registered) return runStatusPhase(input.corrida!.status)
 if (input.requested && input.requested.name === input.name && input.requested.runId === input.runId) return 'requested'
 return input.identity?.run_id || input.identity?.dag_run_id ? 'unknown' : 'none'
}
export const activePhase = (phase: RunPhase) => phase === 'requested' || phase === 'queued' || phase === 'waiting' || phase === 'running'

// ── Frequência de consulta ─────────────────────────────────────────────────
// 5 s é o alvo da spec, condicionado à medição de SQL, upstream e carga
// concorrente. Sem evidência registrada, corrida ativa também usa 30 s.
export const EXECUTION_POLL = { targetMs: 5_000, fallbackMs: 30_000, targetMeasured: false } as const
// Ao voltar à aba (ou ao navegador visível), uma leitura com mais de 5 s é
// refeita uma vez; não é cadência: a consulta periódica segue as regras acima.
export const EXECUTION_REVALIDATE_MS = 5_000
export function executionPollInterval(input: { visible: boolean; shown: boolean; phase: RunPhase; measured?: boolean }): number | false {
 if (!input.visible || !input.shown) return false
 if (activePhase(input.phase) && (input.measured ?? EXECUTION_POLL.targetMeasured)) return EXECUTION_POLL.targetMs
 return EXECUTION_POLL.fallbackMs
}

// ── Frescor ────────────────────────────────────────────────────────────────
export type Freshness = 'loading' | 'live' | 'refreshing' | 'unavailable'
export function executionFreshness(input: { hasData: boolean; isError: boolean; isFetching: boolean; dataUpdatedAt: number; errorUpdatedAt: number }): Freshness {
 if (!input.hasData) return input.isError ? 'unavailable' : 'loading'
 if (input.isError && input.errorUpdatedAt >= input.dataUpdatedAt) return 'unavailable'
 return input.isFetching ? 'refreshing' : 'live'
}
export const FRESHNESS_LABEL: Record<Freshness, string> = { loading: 'Consultando', live: 'Conectado', refreshing: 'Atualizando', unavailable: 'Fonte indisponível' }
export function clockLabel(at: number): string {
 if (!at) return '—'
 const date = new Date(at)
 return [date.getHours(), date.getMinutes(), date.getSeconds()].map(v => String(v).padStart(2, '0')).join(':')
}

// ── Fonte do desenho ───────────────────────────────────────────────────────
// Snapshot vinculado à corrida é a fonte preferida. Sem ele, a tela desenha a
// configuração publicada atual e diz isso; o rascunho nunca entra. Enquanto a
// corrida pedida não é confirmada pela resposta, nada dela define o desenho.
export type DrawingSource = 'snapshot' | 'published-fallback' | 'published' | 'published-unconfirmed'
export function drawingSource(hasRun: boolean, versionNumber: number | null | undefined, unconfirmed = false): DrawingSource {
 if (unconfirmed) return 'published-unconfirmed'
 if (versionNumber != null) return 'snapshot'
 return hasRun ? 'published-fallback' : 'published'
}
export function drawingSourceLabel(source: DrawingSource, versionNumber: number | null | undefined): string {
 if (source === 'snapshot') return `Desenho da versão ${versionNumber} vinculada a esta corrida`
 if (source === 'published-fallback') return 'Corrida sem versão vinculada: o desenho é a configuração publicada atual e pode diferir do que executou'
 if (source === 'published-unconfirmed') return 'Corrida ainda não confirmada: o desenho é a configuração publicada atual, sem estados'
 return 'Desenho da configuração publicada atual'
}
/** Etapas da corrida que não existem no desenho exibido (não são inventadas no gráfico). */
export function stepsOutsideDrawing(definition: WorkspaceDefinition, steps: EtapaExecucaoApi[]): string[] {
 const ids = new Set(definition.nodes.map(node => key(node.id)))
 return steps.filter(step => step.status && !ids.has(key(step.job_name))).map(step => step.job_name)
}

// ── Contagens confiáveis ───────────────────────────────────────────────────
export interface RunCounts { total: number; success: number; failed: number; running: number; skipped: number; none: number; unknown: number; gate: number; pauseMarked: number }
export function runCounts(overlay: Map<string, NodeRunState>, definition: WorkspaceDefinition): RunCounts {
 const counts: RunCounts = { total: definition.nodes.length, success: 0, failed: 0, running: 0, skipped: 0, none: 0, unknown: 0, gate: 0, pauseMarked: 0 }
 for (const node of definition.nodes) {
  const state = overlay.get(key(node.id))
  const kind = state?.kind ?? 'none'
  counts[kind === 'gate' ? 'gate' : kind] += 1
  if (state?.pauseMarked) counts.pauseMarked += 1
 }
 return counts
}
/** "4 de 6 etapas concluídas" conta sucesso confirmado; não é percentual de tempo. */
export function completionLabel(counts: RunCounts): string {
 return `${counts.success} de ${counts.total} ${counts.total === 1 ? 'etapa concluída' : 'etapas concluídas'}`
}

// ── Anúncio acessível ──────────────────────────────────────────────────────
// Só a etapa selecionada, e só quando a etapa ou o estado dela muda; cada
// consulta periódica não gera anúncio.
export function selectedStageAnnouncement(stage: string, state: NodeRunState | null): { key: string; message: string } | null {
 if (!stage || !state) return null
 return { key: `${stage}\u0000${state.kind}\u0000${state.attempt ?? ''}`, message: `Etapa ${stage}: ${state.label}${state.attempt ? `, tentativa operacional ${state.attempt}` : ''}` }
}

// ── Tentativas do motor ────────────────────────────────────────────────────
// A tentativa da telemetria SQL é o ciclo operacional do Orquestra (contado
// pelo início da etapa, fora do retry automático). O log do Airflow é pedido
// pelo try_number do MOTOR, lido sob demanda de GET /pipeline-task-attempts
// para a corrida e a tarefa exatas; o número SQL nunca vira try_number.
export interface EngineAttempt { try_number: number; state: string | null; start_date: string | null; end_date: string | null; duration: number | null; hostname: string | null; started: boolean; has_log: boolean; current: boolean }
export interface EngineAttempts { pipeline_name: string; run_id: string; task_id: string; source: string; available: boolean; reason: string | null; try_number: number | null; attempts: EngineAttempt[]; complete: boolean; history: boolean; ignored: number }
export function engineAttemptsQueryKey(token: string | null, name: string, runId: string, task: string) {
 return ['workspace-engine-attempts', token, name, runId, task] as const
}
export function engineAttemptsPath(name: string, runId: string, task: string): string {
 return `/pipeline-task-attempts?${new URLSearchParams({ pipeline_name: name, run_id: runId, task_id: task })}`
}
/** Resposta de outra etapa, corrida ou pipeline (pedido antigo) não é usada. */
export function engineAttemptsMatch(response: Partial<EngineAttempts> | null | undefined, request: { name: string; runId: string; task: string }): response is EngineAttempts {
 return !!response && response.pipeline_name === request.name && response.run_id === request.runId && response.task_id === request.task && Array.isArray(response.attempts)
}
const validTry = (value: unknown): value is number => typeof value === 'number' && Number.isInteger(value) && value > 0 && value <= 10_000
/** Tentativas comprovadas pelo motor, da mais recente para a mais antiga; linha sem número válido ou repetida não entra. */
export function engineAttemptList(response: EngineAttempts | undefined): EngineAttempt[] {
 if (!response?.available) return []
 const seen = new Set<number>(), rows: EngineAttempt[] = []
 for (const row of response.attempts) if (validTry(row?.try_number) && !seen.has(row.try_number)) { seen.add(row.try_number); rows.push(row) }
 return rows.sort((a, b) => b.try_number - a.try_number)
}
export const ENGINE_STATE_LABEL: Record<string, string> = { success: 'Concluída', failed: 'Falhou', up_for_retry: 'Falhou · nova tentativa prevista', running: 'Executando', queued: 'Na fila', scheduled: 'Agendada', up_for_reschedule: 'Aguardando reagendamento', deferred: 'Adiada · aguardando gatilho', skipped: 'Pulada', upstream_failed: 'Não executou · dependência falhou', removed: 'Removida do fluxo', restarting: 'Reiniciando', shutdown: 'Interrompida' }
export function engineStateLabel(state: string | null | undefined): string {
 const code = key(state)
 return !code ? 'Sem estado no motor' : ENGINE_STATE_LABEL[code] ?? `Estado ${code}`
}
/** Horário do motor sempre em UTC e rotulado: o relógio da telemetria SQL é outro. */
export function engineClock(iso: string | null | undefined): string {
 const date = iso ? new Date(iso) : null
 return date && !Number.isNaN(date.getTime()) ? `${date.toISOString().slice(11, 19)} UTC` : '—'
}
export const ENGINE_REASON: Record<string, string> = {
 instancia_ausente: 'O motor não tem instância desta tarefa nesta corrida.',
 instancia_divergente: 'A resposta do motor não corresponde a esta tarefa e corrida; nada dela foi usado.',
 tarefa_mapeada: 'A tarefa é mapeada por índice no motor; esta tela não escolhe índice nem mistura tentativas de índices diferentes.',
 contador_invalido: 'O motor devolveu um contador de tentativas inválido; nada foi presumido.',
 sem_tentativas: 'O motor ainda não agendou nenhuma tentativa desta tarefa.',
}
export function engineReason(response: EngineAttempts): string {
 return (response.reason && ENGINE_REASON[response.reason]) || 'O motor não informou tentativas desta tarefa.'
}
/** Lacunas: o contador do motor diz n, mas nem toda tentativa 1..n veio com registro. Nada é preenchido. */
export function engineGapNote(response: EngineAttempts, list: EngineAttempt[]): string | null {
 if (!response.available || response.complete || !response.try_number) return null
 const missing = response.try_number - list.filter(row => row.try_number <= response.try_number!).length
 if (missing <= 0) return null
 return `O motor conta ${response.try_number} tentativas; ${missing === 1 ? 'uma não veio' : `${missing} não vieram`} com registro ${response.history ? 'no histórico' : '(histórico do motor indisponível)'}. Estado e horários delas não são presumidos.`
}
export type EngineLogIssue = 'sem-log' | 'sem-inicio' | 'fora' | null
/** Log a abrir: o pedido (URL) se o motor o comprova com log; sem pedido, a
 *  tentativa mais recente com log. Nunca um número que o motor não informou. */
export function engineLogSelection(list: EngineAttempt[], requested: number | null): { attempt: number | null; issue: EngineLogIssue } {
 if (requested !== null) {
  const row = list.find(item => item.try_number === requested)
  return !row ? { attempt: requested, issue: 'fora' } : row.has_log ? { attempt: requested, issue: null } : { attempt: requested, issue: 'sem-inicio' }
 }
 const latest = list.find(item => item.has_log)
 return latest ? { attempt: latest.try_number, issue: null } : { attempt: null, issue: list.length ? 'sem-inicio' : 'sem-log' }
}

// ── Solicitação guiada ─────────────────────────────────────────────────────
// A DAG gerada lê `conf.data_referencia` (ODATE). Data lógica do Airflow é
// opcional e informada em UTC. JSON avançado só sob demanda, preservando as
// chaves já presentes; o identificador do pedido é estável enquanto o pedido
// estiver aberto (repetir não cria outra corrida).
export interface RunRequestForm { odate: string; logicalDate: string; extraConf: Record<string, unknown> }
export type RunRequestResult = { ok: true; body: { conf: Record<string, unknown>; dag_run_id: string; logical_date?: string } } | { ok: false; field: 'odate' | 'logicalDate' | 'conf' | 'runId'; message: string }
export const RUN_CONF_LIMIT = 65_536
export function validOperationalDate(value: string): boolean {
 const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value)
 if (!match) return false
 const [year, month, day] = [Number(match[1]), Number(match[2]), Number(match[3])]
 const date = new Date(Date.UTC(year, month - 1, day))
 return date.getUTCFullYear() === year && date.getUTCMonth() === month - 1 && date.getUTCDate() === day
}
export function logicalDateIso(value: string): string | null {
 const match = /^(\d{4}-\d{2}-\d{2})T(\d{2}):(\d{2})(?::(\d{2}))?$/.exec(value)
 if (!match || !validOperationalDate(match[1]) || Number(match[2]) > 23 || Number(match[3]) > 59 || Number(match[4] ?? 0) > 59) return null
 return `${match[1]}T${match[2]}:${match[3]}:${match[4] ?? '00'}Z`
}
export function buildRunRequest(form: RunRequestForm, runId: string): RunRequestResult {
 if (!/^workspace__[0-9a-f-]{36}$/.test(runId)) return { ok: false, field: 'runId', message: 'Identificador da solicitação inválido. Feche e abra a solicitação novamente.' }
 const odate = form.odate.trim()
 if (odate && !validOperationalDate(odate)) return { ok: false, field: 'odate', message: 'Informe uma data de referência válida (AAAA-MM-DD) ou deixe em branco.' }
 const logical = form.logicalDate.trim()
 const iso = logical ? logicalDateIso(logical) : null
 if (logical && !iso) return { ok: false, field: 'logicalDate', message: 'Informe data e hora válidas para a data lógica ou deixe em branco.' }
 const conf: Record<string, unknown> = { ...form.extraConf }
 if (odate) conf.data_referencia = odate; else delete conf.data_referencia
 const body = { conf, dag_run_id: runId, ...(iso ? { logical_date: iso } : {}) }
 if (new TextEncoder().encode(JSON.stringify(body)).length > RUN_CONF_LIMIT) return { ok: false, field: 'conf', message: 'Os parâmetros desta execução excedem 64 KiB.' }
 return { ok: true, body }
}
/** JSON avançado → formulário. A data de referência do JSON volta ao campo guiado. */
export function parseAdvancedConf(value: string): { ok: true; odate: string; extraConf: Record<string, unknown> } | { ok: false; message: string } {
 let parsed: unknown
 try { parsed = JSON.parse(value || '{}') } catch { return { ok: false, message: 'Use um objeto JSON válido.' } }
 if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return { ok: false, message: 'Os parâmetros da execução devem ser um objeto JSON.' }
 const { data_referencia: odate, ...extraConf } = parsed as Record<string, unknown>
 if (odate !== undefined && (typeof odate !== 'string' || !validOperationalDate(odate))) return { ok: false, message: 'data_referencia deve ser uma data AAAA-MM-DD.' }
 return { ok: true, odate: odate ?? '', extraConf }
}
export function advancedConfText(form: Pick<RunRequestForm, 'odate' | 'extraConf'>): string {
 return JSON.stringify({ ...form.extraConf, ...(form.odate.trim() ? { data_referencia: form.odate.trim() } : {}) }, null, 2)
}

// ── Histórico ──────────────────────────────────────────────────────────────
export const RUN_HISTORY_STATUSES: readonly (readonly [string, string])[] = [['', 'Todas'], ['EXECUTANDO', 'Executando'], ['AGUARDANDO_DEPENDENCIA', 'Aguardando dependência'], ['SUCESSO', 'Concluída'], ['FALHA', 'Falhou'], ['PULADO', 'Pulada'], ['NAO_LIBEROU', 'Não liberou dependentes']]
export const RUN_HISTORY_PAGE = 25
export interface RunHistoryFilters { from: string; to: string; status: string; version: string; page: number }
export const EMPTY_HISTORY_FILTERS: RunHistoryFilters = { from: '', to: '', status: '', version: '', page: 0 }
export function runHistoryIssue(filters: RunHistoryFilters): string | null {
 if (filters.from && !validOperationalDate(filters.from)) return 'Data inicial inválida.'
 if (filters.to && !validOperationalDate(filters.to)) return 'Data final inválida.'
 if (filters.from && filters.to && filters.from > filters.to) return 'A data inicial deve ser anterior ou igual à final.'
 if (filters.version && !/^[1-9]\d{0,8}$/.test(filters.version)) return 'Informe o número inteiro da versão.'
 if (filters.status && !RUN_HISTORY_STATUSES.some(([id]) => id === filters.status)) return 'Situação desconhecida.'
 return null
}
export function runHistoryPath(name: string, filters: RunHistoryFilters, limit = RUN_HISTORY_PAGE): string {
 const query = new URLSearchParams({ pipeline_name: name, limit: String(limit), offset: String(Math.max(0, filters.page) * limit) })
 if (filters.from) query.set('date_from', filters.from)
 if (filters.to) query.set('date_to', filters.to)
 if (filters.status) query.set('status', filters.status)
 if (filters.version) query.set('version', filters.version)
 return `/pipeline-run-history?${query}`
}
export interface RunHistoryItem { runId: string | null; date: string | null; status: string | null; startedAt: string | null; finishedAt: string | null; triggeredBy: string | null; replacedAt: string | null; versionNumber: number | null; snapshot: boolean }
export interface RunHistoryPage { total: number; limit: number; offset: number; items: RunHistoryItem[]; versionsAvailable: boolean; source: string }
export function historyPages(page: Pick<RunHistoryPage, 'total' | 'limit' | 'offset'>): { current: number; count: number } {
 const limit = Math.max(1, page.limit)
 return { current: Math.floor(page.offset / limit) + 1, count: Math.max(1, Math.ceil(page.total / limit)) }
}
