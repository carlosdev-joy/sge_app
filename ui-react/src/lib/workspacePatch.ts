// Patches diferenciais do rascunho: só os caminhos que mudaram, nunca uma cópia
// inteira. Arrays de objetos com `id` único (etapas) são comparados por `id`;
// os demais, por posição ou por um trecho contíguo. Campos desconhecidos são só
// mais caminhos: o que não mudou não é tocado.
import type { WorkspaceDefinition, WorkspaceNode } from './workspace'

export type PatchSegment = string | number | { id: string }
export type PatchOp =
 | { t: 'set'; path: PatchSegment[]; hb: boolean; b?: unknown; ha: boolean; a?: unknown }
 | { t: 'splice'; path: PatchSegment[]; index: number; removed: unknown[]; inserted: unknown[] }
 | { t: 'ins' | 'del'; path: PatchSegment[]; id: string; index: number; value: unknown }
export type PatchResult<T> = { ok: true; value: T } | { ok: false; message: string }

const plain = (value: unknown): value is Record<string, unknown> => value !== null && typeof value === 'object' && !Array.isArray(value)
const has = (value: Record<string, unknown>, key: string) => Object.prototype.hasOwnProperty.call(value, key)
const copy = <T>(value: T): T => value !== null && typeof value === 'object' ? structuredClone(value) : value
export function deepEqual(a: unknown, b: unknown): boolean {
 if (Object.is(a, b)) return true
 if (Array.isArray(a) || Array.isArray(b)) return Array.isArray(a) && Array.isArray(b) && a.length === b.length && a.every((item, i) => deepEqual(item, b[i]))
 if (!plain(a) || !plain(b)) return false
 const keys = Object.keys(a)
 return keys.length === Object.keys(b).length && keys.every(key => has(b, key) && deepEqual(a[key], b[key]))
}
function keyed(list: unknown[]): string[] | null {
 const ids = list.map(item => plain(item) && typeof item.id === 'string' ? item.id : null)
 return ids.every(id => id !== null) && new Set(ids).size === ids.length ? ids as string[] : null
}
function diff(a: unknown, b: unknown, path: PatchSegment[], out: PatchOp[]) {
 if (Object.is(a, b)) return
 if (plain(a) && plain(b)) {
  for (const key of new Set([...Object.keys(a), ...Object.keys(b)])) {
   if (has(a, key) && has(b, key)) diff(a[key], b[key], [...path, key], out)
   else out.push({ t: 'set', path: [...path, key], hb: has(a, key), b: copy(a[key]), ha: has(b, key), a: copy(b[key]) })
  }
  return
 }
 if (Array.isArray(a) && Array.isArray(b)) {
  const ka = keyed(a), kb = keyed(b)
  if (ka && kb && (ka.length || kb.length)) {
   const ia = new Map(ka.map((id, i) => [id, i])), ib = new Map(kb.map((id, i) => [id, i]))
   const common = ka.filter(id => ib.has(id)), order = kb.filter(id => ia.has(id))
   if (common.every((id, i) => id === order[i])) {
    // Remoções da maior posição para a menor e inserções da menor para a maior:
    // aplicar e inverter devolvem exatamente a ordem original.
    for (let i = ka.length - 1; i >= 0; i--) if (!ib.has(ka[i])) out.push({ t: 'del', path, id: ka[i], index: i, value: copy(a[i]) })
    for (const id of common) diff(a[ia.get(id)!], b[ib.get(id)!], [...path, { id }], out)
    kb.forEach((id, index) => { if (!ia.has(id)) out.push({ t: 'ins', path, id, index, value: copy(b[index]) }) })
    return
   }
  }
  if (a.length === b.length) { a.forEach((item, i) => diff(item, b[i], [...path, i], out)); return }
  let start = 0, end = 0
  while (start < a.length && start < b.length && deepEqual(a[start], b[start])) start++
  while (end < a.length - start && end < b.length - start && deepEqual(a[a.length - 1 - end], b[b.length - 1 - end])) end++
  out.push({ t: 'splice', path, index: start, removed: copy(a.slice(start, a.length - end)), inserted: copy(b.slice(start, b.length - end)) })
  return
 }
 if (!deepEqual(a, b)) out.push({ t: 'set', path, hb: true, b: copy(a), ha: true, a: copy(b) })
}
export function diffPatch(before: unknown, after: unknown): PatchOp[] { const out: PatchOp[] = []; diff(before, after, [], out); return out }
export function invertPatch(ops: PatchOp[]): PatchOp[] {
 return [...ops].reverse().map(op => op.t === 'set' ? { ...op, hb: op.ha, b: op.a, ha: op.hb, a: op.b }
  : op.t === 'splice' ? { ...op, removed: op.inserted, inserted: op.removed }
  : { ...op, t: op.t === 'ins' ? 'del' : 'ins' })
}

const CONFLICT = Symbol('conflito')
type Step = unknown | typeof CONFLICT
function key(container: unknown, segment: PatchSegment): string | number | undefined {
 if (typeof segment === 'object') { const index = Array.isArray(container) ? container.findIndex(item => plain(item) && item.id === segment.id) : -1; return index < 0 ? undefined : index }
 if (typeof segment === 'number') return Array.isArray(container) && segment >= 0 && segment < container.length ? segment : undefined
 return plain(container) ? segment : undefined
}
// Copia só o caminho até a alteração; o restante continua compartilhado.
function within(value: unknown, path: PatchSegment[], depth: number, change: (holder: unknown) => Step): Step {
 if (depth === path.length) return change(value)
 const k = key(value, path[depth])
 if (k === undefined) return CONFLICT
 const child = (value as Record<string | number, unknown>)[k]
 const next = within(child, path, depth + 1, change)
 if (next === CONFLICT || next === child) return next === CONFLICT ? CONFLICT : value
 if (Array.isArray(value)) { const list = [...value]; list[k as number] = next; return list }
 return { ...(value as Record<string, unknown>), [k]: next }
}
function applyOne(root: unknown, op: PatchOp): Step {
 if (op.t !== 'set') return within(root, op.path, 0, list => {
  if (!Array.isArray(list)) return CONFLICT
  if (op.t === 'splice') {
   if (op.index > list.length || !deepEqual(list.slice(op.index, op.index + op.removed.length), op.removed)) return CONFLICT
   return [...list.slice(0, op.index), ...copy(op.inserted), ...list.slice(op.index + op.removed.length)]
  }
  const at = list.findIndex(item => plain(item) && item.id === op.id)
  if (op.t === 'del') return at < 0 || !deepEqual(list[at], op.value) ? CONFLICT : list.filter((_, i) => i !== at)
  if (at >= 0) return CONFLICT
  const index = Math.min(op.index, list.length)
  return [...list.slice(0, index), copy(op.value), ...list.slice(index)]
 })
 const last = op.path[op.path.length - 1]
 return within(root, op.path.slice(0, -1), 0, holder => {
  const k = typeof last === 'string' && plain(holder) ? last : key(holder, last)
  if (k === undefined) return CONFLICT
  const container = holder as Record<string | number, unknown>
  const present = Array.isArray(holder) ? true : has(container as Record<string, unknown>, String(k))
  if (present !== op.hb || (present && !deepEqual(container[k], op.b))) return CONFLICT
  if (Array.isArray(holder)) { const list = [...holder]; list[k as number] = copy(op.a); return list }
  if (op.ha) return { ...container, [k]: copy(op.a) }
  const rest = { ...container }; delete rest[k]; return rest
 })
}
/** Aplica conferindo cada caminho: se o valor atual não é o esperado, nada muda. */
export function applyPatch<T>(root: T, ops: PatchOp[]): PatchResult<T> {
 let value: unknown = root
 for (const op of ops) { const next = applyOne(value, op); if (next === CONFLICT) return { ok: false, message: 'O rascunho mudou nos mesmos campos.' }; value = next }
 return { ok: true, value: value as T }
}

/** Problema estrutural das ligações: ponta ausente, ligação repetida ou ciclo. */
export function edgeIssue(definition: WorkspaceDefinition): string | null {
 const ids = new Set(definition.nodes.map(node => node.id)), seen = new Set<string>(), next = new Map<string, string[]>()
 for (const edge of definition.edges) {
  if (!ids.has(edge.source) || !ids.has(edge.target)) return 'Uma ligação aponta para uma etapa ausente.'
  const signature = JSON.stringify([edge.source, edge.target, edge.branch ?? null])
  if (seen.has(signature)) return 'A mesma ligação ficaria repetida.'
  seen.add(signature); next.set(edge.source, [...next.get(edge.source) ?? [], edge.target])
 }
 const state = new Map<string, number>()
 const visit = (id: string): boolean => { state.set(id, 1); for (const target of next.get(id) ?? []) { if (state.get(target) === 1 || (!state.has(target) && visit(target))) return true } state.set(id, 2); return false }
 return [...ids].some(id => !state.has(id) && visit(id)) ? 'As ligações formariam um ciclo.' : null
}
const STALE = 'A etapa mudou nos mesmos campos, foi removida ou renomeada desde que você começou a editar. Nada foi aplicado; descarte as alterações do inspector e revise.'
/** Mescla no rascunho atual só os campos que o formulário alterou a partir da sua base. */
export function mergeNodePatch(definition: WorkspaceDefinition, base: WorkspaceNode, next: WorkspaceNode): PatchResult<WorkspaceDefinition> {
 if (base.id !== next.id) return { ok: false, message: 'Use Renomear identificador para trocar o identificador da etapa.' }
 const result = applyPatch(definition, diffPatch(base, next).map(op => ({ ...op, path: ['nodes', { id: base.id }, ...op.path] })))
 return result.ok ? result : { ok: false, message: STALE }
}
export function mergeDefinitionPatch(definition: WorkspaceDefinition, base: WorkspaceDefinition, next: WorkspaceDefinition): PatchResult<WorkspaceDefinition> {
 const result = applyPatch(definition, diffPatch(base, next))
 if (!result.ok) return { ok: false, message: STALE }
 const issue = edgeIssue(result.value)
 return issue && !edgeIssue(definition) ? { ok: false, message: `${issue} Nada foi aplicado; revise as ligações no canvas.` } : result
}
