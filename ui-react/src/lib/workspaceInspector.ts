// Subseções do inspector da Montagem e atalhos de desfazer/refazer.
import { encryptedParameter, object, type JsonObject } from './workspace'
import { deepEqual } from './workspacePatch'
export type InspectorSection = 'configuracao' | 'etapa' | 'lineage' | 'avancado'
export const INSPECTOR_SECTIONS: readonly (readonly [InspectorSection, string])[] = [['configuracao', 'Configuração'], ['etapa', 'Etapa'], ['lineage', 'Lineage'], ['avancado', 'Avançado']]
const STEP_FIELDS = new Set(['id', 'job_name', 'displayName', 'execution_order', 'nodes'])
const FIELD_LABELS: Record<string, string> = { configuration: 'configuração da etapa', parameters: 'parâmetros da etapa', execution_order: 'ordem de execução', displayName: 'nome para exibição', id: 'identificador', job_name: 'identificador', edges: 'ligações' }
/** Subseção que contém o campo de um diagnóstico; campo desconhecido abre a configuração. */
export function inspectorSectionFor(field: string): InspectorSection {
 if (/lineage/i.test(field)) return 'lineage'
 return STEP_FIELDS.has(field) ? 'etapa' : 'configuracao'
}
export function diagnosticFieldLabel(field: string): string { return FIELD_LABELS[field] ?? field }
export interface DiagnosticControl<T> { element: T; field: string | null; editable: boolean }
/** Alvo do diagnóstico com a subseção já carregada: o controle editável do campo (o nome para exibição fica fora das subseções), senão o primeiro controle editável da subseção, senão a própria subseção. Somente leitura ou desabilitado não recebe foco de edição. */
export function diagnosticFocusTarget<T>(field: string, section: T, controls: DiagnosticControl<T>[], outside: DiagnosticControl<T>[] = []): T {
 return [...outside, ...controls].find(control => control.editable && control.field === field)?.element ?? controls.find(control => control.editable)?.element ?? section
}
/** O foco do diagnóstico só sai de onde o usuário o deixou ao pedir (ou do body); outra subseção, campo, seleção, diálogo ou inspector oculto encerram o pedido. */
export function diagnosticFocusAllowed<T>(focus: { active: T | null; body: T | null; trigger: T | null; visible: boolean; dialogOpen: boolean }): boolean {
 return focus.visible && !focus.dialogOpen && (focus.active === null || focus.active === focus.body || focus.active === focus.trigger)
}
/** O JSON avançado não cria, altera nem remove parâmetro protegido: isso tem ação própria. */
export function protectedRowsUnchanged(base: JsonObject, next: JsonObject): boolean {
 const rows = (configuration: JsonObject) => (Array.isArray(configuration.etl_pipeline_job_param) ? configuration.etl_pipeline_job_param.map(object) : []).filter(encryptedParameter)
 return deepEqual(rows(base), rows(next))
}
export interface ShortcutEvent { key: string; ctrlKey: boolean; metaKey: boolean; shiftKey: boolean; altKey: boolean; isComposing: boolean; defaultPrevented: boolean }
/** Ctrl/⌘+Z desfaz; Ctrl/⌘+Shift+Z ou Ctrl+Y refaz. Campo de texto, diálogo ou vista inativa ficam com o comportamento nativo. */
export function historyShortcut(event: ShortcutEvent, context: { active: boolean; textTarget: boolean; dialogOpen: boolean }): 'undo' | 'redo' | null {
 if (!context.active || context.textTarget || context.dialogOpen || event.defaultPrevented || event.isComposing || event.altKey || !(event.ctrlKey || event.metaKey)) return null
 const key = event.key.toLowerCase()
 if (key === 'z') return event.shiftKey ? 'redo' : 'undo'
 return key === 'y' && event.ctrlKey && !event.shiftKey ? 'redo' : null
}
export interface HistoryFocus<T> { trigger: T | null; active: T | null; body: T | null; undo: T | null; redo: T | null; canvas: T | null; disabled: (element: T) => boolean; visible: boolean; dialogOpen: boolean }
/** Depois de desfazer/refazer com sucesso: se o botão do histórico que tinha o foco ficou desabilitado (o navegador manda o foco ao body), o foco vai ao botão oposto habilitado ou ao canvas. Foco em outro lugar, diálogo ou vista oculta ficam como estão. */
export function historyFocusTarget<T>(focus: HistoryFocus<T>): T | null {
 const { trigger, active, undo, redo } = focus
 if (!trigger || !focus.visible || focus.dialogOpen || (trigger !== undo && trigger !== redo) || !focus.disabled(trigger)) return null
 if (active !== null && active !== trigger && active !== focus.body) return null
 const opposite = trigger === undo ? redo : undo
 return opposite && !focus.disabled(opposite) ? opposite : focus.canvas
}
