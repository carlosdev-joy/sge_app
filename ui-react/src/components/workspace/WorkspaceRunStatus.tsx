import { Ban, CheckCircle2, Circle, CircleHelp, CircleSlash, Clock, Hourglass, PauseCircle, Send, XCircle } from 'lucide-react'
import { RUN_PHASE_LABEL, type NodeRunKind, type NodeRunState, type RunPhase } from '../../lib/workspaceExecution'

// Ícone + rótulo sempre juntos: a cor nunca é a única pista do estado.
const PHASE_TONE: Record<RunPhase, string> = {
 none: 'border-edge text-dim bg-canvas', unknown: 'border-slate-300 text-slate-700 bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:bg-slate-900/40',
 requested: 'border-slate-300 text-slate-800 bg-slate-50 dark:border-slate-600 dark:text-slate-200 dark:bg-slate-900/40',
 queued: 'border-amber-300 text-amber-900 bg-amber-50 dark:border-amber-800 dark:text-amber-200 dark:bg-amber-950/30',
 waiting: 'border-amber-300 text-amber-900 bg-amber-50 dark:border-amber-800 dark:text-amber-200 dark:bg-amber-950/30',
 running: 'border-blue-300 text-blue-800 bg-blue-50 dark:border-blue-800 dark:text-blue-200 dark:bg-blue-950/30',
 success: 'border-green-300 text-green-800 bg-green-50 dark:border-green-800 dark:text-green-200 dark:bg-green-950/30',
 failed: 'border-red-300 text-red-800 bg-red-50 dark:border-red-800 dark:text-red-200 dark:bg-red-950/30',
 skipped: 'border-slate-300 text-slate-700 bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:bg-slate-900/40',
 'not-released': 'border-amber-300 text-amber-900 bg-amber-50 dark:border-amber-800 dark:text-amber-200 dark:bg-amber-950/30',
}
const PHASE_ICON = { none: Circle, unknown: CircleHelp, requested: Send, queued: Hourglass, waiting: Clock, success: CheckCircle2, failed: XCircle, skipped: CircleSlash, 'not-released': Ban } as const
/** `live`: corrida atual com fonte respondendo; sem isso Executando não pulsa. */
/** `code`: situação crua da origem, mostrada quando não há tradução. */
export function RunPhaseBadge({ phase, live = false, code }: { phase: RunPhase; live?: boolean; code?: string | null }) {
 const Icon = phase === 'running' ? null : PHASE_ICON[phase]
 return <span className={`inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-xs font-medium ${PHASE_TONE[phase]}`}>
  {Icon ? <Icon size={14} aria-hidden="true" className="shrink-0" /> : <span aria-hidden="true" className="relative inline-flex size-3.5 items-center justify-center"><span className={`absolute inset-0 rounded-full bg-blue-600/30 dark:bg-blue-400/30 ${live ? 'motion-safe:animate-run-indicator' : ''}`} /><span className="size-2 rounded-full bg-blue-600 dark:bg-blue-400" /></span>}
  {phase === 'unknown' && code ? `Estado ${code}` : RUN_PHASE_LABEL[phase]}
 </span>
}
const STATE_ICON: Record<NodeRunKind, [typeof Circle, string]> = {
 none: [Circle, 'text-dim'], unknown: [CircleHelp, 'text-slate-600 dark:text-slate-400'], running: [Circle, 'text-blue-700 dark:text-blue-400'],
 success: [CheckCircle2, 'text-green-700 dark:text-green-400'], failed: [XCircle, 'text-red-700 dark:text-red-400'],
 gate: [PauseCircle, 'text-amber-700 dark:text-amber-400'], skipped: [CircleSlash, 'text-slate-500 dark:text-slate-400'],
}
/** Ícone do estado da etapa: o mesmo no nó, no inspector, na tabela e na legenda.
 *  Executando é um ponto com anel; o anel só pulsa com telemetria ativa (`animate`). */
export function RunStateIcon({ kind, animate = false, size = 14 }: { kind: NodeRunKind; animate?: boolean; size?: number }) {
 if (kind === 'running') return <span aria-hidden="true" className="relative inline-flex shrink-0 items-center justify-center" style={{ width: size, height: size }}><span className={`absolute inset-0 rounded-full bg-blue-600/30 dark:bg-blue-400/30 ${animate ? 'motion-safe:animate-run-indicator' : ''}`} /><span className="size-2 rounded-full bg-blue-600 dark:bg-blue-400" /></span>
 const [Icon, tone] = STATE_ICON[kind]
 return <Icon size={size} aria-hidden="true" className={`shrink-0 ${tone}`} />
}
export function StateLabel({ state }: { state: NodeRunState | null }) {
 if (!state) return <span className="text-sm text-dim">Estado ainda não consultado</span>
 return <span className="inline-flex flex-wrap items-center gap-1.5 text-sm font-medium text-ink">
  <RunStateIcon kind={state.kind} animate={state.animate} size={16} />
  {state.label}{state.pauseMarked && <span className="inline-flex items-center gap-1 text-xs font-normal text-fuchsia-700 dark:text-fuchsia-300"><PauseCircle size={13} aria-hidden="true" />pausa marcada</span>}
 </span>
}
