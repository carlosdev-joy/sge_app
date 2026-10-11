// Desfazer/refazer local do rascunho: até 50 passos com patches diferenciais da
// definição e do layout. Não alcança save, publicação, execução nem segredos.
import { encryptedParameter, object, pipelineParameters, text, type WorkspaceDefinition, type WorkspaceLayout } from './workspace'
import { applyPatch, deepEqual, diffPatch, invertPatch, type PatchOp } from './workspacePatch'

export const HISTORY_LIMIT = 50
// Digitação contínua no mesmo campo vira um passo até uma pausa desta duração.
export const TEXT_GROUP_MS = 1500
export interface WorkspaceSnapshot { definition: WorkspaceDefinition; layout: WorkspaceLayout }
export interface HistoryEntry { label: string; ops: PatchOp[]; group?: string; at: number; sealed: boolean; select?: { before: string | null; after: string | null } }
export interface WorkspaceHistory { past: HistoryEntry[]; future: HistoryEntry[]; reset?: 'protected' }
export interface HistoryChange { label: string; group?: string; window?: number; now: number; select?: { before: string | null; after: string | null } }

export function emptyHistory(): WorkspaceHistory { return { past: [], future: [] } }
// Referência protegida nova vem do servidor (valor cifrado fora do rascunho):
// desfazer não pode desligá-la nem religá-la, então o histórico recomeça.
function protectedReferences(definition: WorkspaceDefinition): Set<string> {
 const rows = [...pipelineParameters(definition).map(row => ['', row] as const), ...definition.nodes.flatMap(node => (Array.isArray(node.configuration.etl_pipeline_job_param) ? node.configuration.etl_pipeline_job_param : []).map(row => [node.id, object(row)] as const))]
 return new Set(rows.filter(([, row]) => encryptedParameter(row)).map(([scope, row]) => JSON.stringify([scope, text(row.param_name).toLowerCase(), row.secretReference ?? null])))
}
export function addsProtectedReference(before: WorkspaceDefinition, after: WorkspaceDefinition): boolean {
 if (before === after) return false
 const known = protectedReferences(before)
 return [...protectedReferences(after)].some(reference => !known.has(reference))
}
// Valor protegido só circula mascarado; um valor aberto (JSON avançado, rascunho
// legado) nunca entra no histórico. Confere as duas listas de parâmetros do pipeline.
const rowsOf = (value: unknown) => Array.isArray(value) ? value.map(object) : []
export function exposesProtectedValue(definition: WorkspaceDefinition): boolean {
 const rows = [...pipelineParameters(definition), ...rowsOf(definition.parameters), ...rowsOf(object(object(definition.metadata).legacyTables).etl_pipeline_param), ...definition.nodes.flatMap(node => rowsOf(node.configuration.etl_pipeline_job_param))]
 return rows.some(row => encryptedParameter(row) && row.param_value != null && row.param_value !== '' && row.param_value !== '***')
}
const pathKey = (op: PatchOp) => JSON.stringify(op.path)
// Mesma digitação/arraste: o passo guarda o valor de antes do primeiro evento e o do último.
function merge(ops: PatchOp[], incoming: PatchOp[]): PatchOp[] {
 const result = [...ops]
 for (const op of incoming) {
  let at = -1
  if (op.t === 'set') for (let i = result.length - 1; i >= 0 && at < 0; i--) if (result[i].t === 'set' && pathKey(result[i]) === pathKey(op)) at = i
  const previous = result[at]
  // Só junta se nada depois tocou o mesmo caminho, um ancestral ou um descendente.
  const overlaps = (item: PatchOp) => pathKey(op).startsWith(pathKey(item).slice(0, -1)) || pathKey(item).startsWith(pathKey(op).slice(0, -1))
  if (op.t !== 'set' || at < 0 || previous.t !== 'set' || result.slice(at + 1).some(overlaps)) { result.push(op); continue }
  const combined = { ...previous, ha: op.ha, a: op.a }
  if (combined.hb === combined.ha && (!combined.hb || deepEqual(combined.b, combined.a))) result.splice(at, 1)
  else result[at] = combined
 }
 return result
}
// O passo guarda o valor de antes e o de depois: se qualquer um dos dois tem valor
// protegido aberto (inclusive mascarar, ou remover o parâmetro ou a etapa que o
// contém), nada é registrado e o histórico recomeça vazio.
export function recordHistory(history: WorkspaceHistory, before: WorkspaceSnapshot, after: WorkspaceSnapshot, change: HistoryChange): WorkspaceHistory {
 if (addsProtectedReference(before.definition, after.definition) || exposesProtectedValue(before.definition) || exposesProtectedValue(after.definition)) return { past: [], future: [], reset: 'protected' }
 const ops = diffPatch(before, after)
 if (!ops.length) return history
 const top = history.past[history.past.length - 1]
 if (top && change.group && !top.sealed && top.group === change.group && !history.future.length && change.now - top.at <= (change.window ?? Infinity)) {
  const combined = merge(top.ops, ops)
  const past = history.past.slice(0, -1)
  return { past: combined.length ? [...past, { ...top, ops: combined, at: change.now, select: { before: top.select?.before ?? null, after: change.select?.after ?? null } }] : past, future: [] }
 }
 const past = history.past.map((entry, index) => index === history.past.length - 1 && !entry.sealed ? { ...entry, sealed: true } : entry)
 return { past: [...past, { label: change.label, ops, group: change.group, at: change.now, sealed: !change.group, select: change.select }].slice(-HISTORY_LIMIT), future: [] }
}
export function sealHistory(history: WorkspaceHistory): WorkspaceHistory {
 const top = history.past[history.past.length - 1]
 return !top || top.sealed ? history : { ...history, past: [...history.past.slice(0, -1), { ...top, sealed: true }] }
}
export type HistoryTravel = { ok: true; history: WorkspaceHistory; state: WorkspaceSnapshot; entry: HistoryEntry } | { ok: false; history: WorkspaceHistory; message: string }
function travel(history: WorkspaceHistory, current: WorkspaceSnapshot, undo: boolean): HistoryTravel | null {
 const entry = undo ? history.past[history.past.length - 1] : history.future[history.future.length - 1]
 if (!entry) return null
 const result = applyPatch(current, undo ? invertPatch(entry.ops) : entry.ops)
 if (!result.ok) return { ok: false, history: emptyHistory(), message: 'O rascunho não corresponde mais ao histórico local. O histórico foi reiniciado e nada foi alterado.' }
 const moved = { ...entry, sealed: true }
 return { ok: true, entry, state: result.value, history: undo ? { past: history.past.slice(0, -1), future: [...history.future, moved] } : { past: [...history.past, moved], future: history.future.slice(0, -1) } }
}
export const undoHistory = (history: WorkspaceHistory, current: WorkspaceSnapshot) => travel(sealHistory(history), current, true)
export const redoHistory = (history: WorkspaceHistory, current: WorkspaceSnapshot) => travel(history, current, false)
export function historyLabels(history: WorkspaceHistory): { undo: string | null; redo: string | null } {
 return { undo: history.past[history.past.length - 1]?.label ?? null, redo: history.future[history.future.length - 1]?.label ?? null }
}
