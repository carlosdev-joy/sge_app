import { cloneFlow, connectWorkspace, object, patchLegacy, text, type JsonObject, type WorkspaceDefinition, type WorkspaceNode } from './workspace'
import { decisionCondition, decisionEdgeHandle } from './workspaceDecision'
import { jsonField } from './workspaceJobFields'

const fields: Record<string, string> = { sql: 'sql_json', decisao: 'condition_json', notificacao: 'notify_json', email: 'notify_json', aguarde: 'aguarde_json' }
export function hasSpecializedFields(type: string) { return type in fields || type === 'valida_arquivo' }
export function specializedConfigurationIssue(node: WorkspaceNode): string | null {
 const header = node.configuration.etl_valida_arquivo_no
 if (node.type === 'valida_arquivo' && Array.isArray(header) && header.length > 1) return 'Esta etapa contém mais de uma configuração de validação. Consulte e revise os dados nas configurações avançadas.'
 const value = object(node.configuration.legacyJob)[node.type === 'valida_arquivo' ? 'valida_arquivo_json' : fields[node.type]]
 if (value != null && value !== '') {
  try {
   const parsed = typeof value === 'string' ? JSON.parse(value) : value
   if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) throw new Error()
  } catch { return 'A configuração existente não é um objeto JSON compatível. Ela foi preservada; revise as configurações avançadas antes de editar.' }
 }
 const raw = specializedConfiguration(node)
 if (node.type === 'decisao' && raw.casos != null && !Array.isArray(raw.casos)) return 'Os casos desta decisão têm um formato incompatível. Revise as configurações avançadas.'
 if (node.type === 'valida_arquivo' && (!Array.isArray(raw.entradas) || raw.entradas.some(entry => !entry || typeof entry !== 'object' || Array.isArray(entry))) && Object.keys(raw).length) return 'As entradas deste validador têm um formato incompatível. Revise as configurações avançadas.'
 return null
}
export function specializedConfiguration(node: WorkspaceNode): JsonObject {
 if (node.type !== 'valida_arquivo') return jsonField(object(node.configuration.legacyJob)[fields[node.type]])
 const rows = node.configuration.etl_valida_arquivo_no
 return Array.isArray(rows) && rows.length ? { ...object(rows[0]), entradas: cloneFlow(node.configuration.etl_valida_arquivo_config ?? []) } : jsonField(object(node.configuration.legacyJob).valida_arquivo_json)
}
// Merge only fields actually changed by the form; retain future fields and row metadata.
export function patchSpecializedNode(node: WorkspaceNode, patch: JsonObject): WorkspaceNode {
 if (!hasSpecializedFields(node.type)) throw new Error('Componente sem formulário especializado.')
 const issue = specializedConfigurationIssue(node)
 if (issue) throw new Error(issue)
 const raw = specializedConfiguration(node)
 const next = { ...raw, ...patch }
 if (['sql','decisao'].includes(node.type) && !('on_error' in next)) next.on_error = 'falhar'
 if (node.type === 'email' && 'anexo' in patch) {
  const original = object(raw.anexo)
  if (patch.anexo === null && Object.keys(original).some(key => !['raiz','nome'].includes(key))) throw new Error('O anexo contém campos adicionais. Preserve a configuração antes de remover o anexo.')
  if (patch.anexo !== null) next.anexo = { ...original, ...object(patch.anexo) }
 }
 delete next.on_error_legado
 if (node.type !== 'valida_arquivo') return patchLegacy(node, fields[node.type], JSON.stringify(next))
 const { entradas, ...header } = next
 const oldHeader = Array.isArray(node.configuration.etl_valida_arquivo_no) ? node.configuration.etl_valida_arquivo_no : []
 const oldEntries = Array.isArray(node.configuration.etl_valida_arquivo_config) ? node.configuration.etl_valida_arquivo_config.map(object) : []
 const rows = (Array.isArray(entradas) ? entradas : []).map((entry, ordem) => {
  const row = object(entry)
  return { ...oldEntries.find(old => old.entrada_id === row.entrada_id), ...row, ordem }
 })
 return { ...node, configuration: { ...node.configuration, etl_valida_arquivo_no: [{ ...object(oldHeader[0]), ...header }], etl_valida_arquivo_config: rows } }
}
export function patchSpecializedDefinition(definition: WorkspaceDefinition, id: string, patch: JsonObject): WorkspaceDefinition {
 return { ...definition, nodes: definition.nodes.map(node => node.id === id ? patchSpecializedNode(node, patch) : node) }
}
export type DecisionCaseAction = { type: 'mode'; switch: boolean } | { type: 'add' } | { type: 'update'; index: number; patch: JsonObject } | { type: 'remove'; index: number } | { type: 'move'; index: number; delta: -1 | 1 }
export function editDecisionCases(definition: WorkspaceDefinition, id: string, action: DecisionCaseAction): WorkspaceDefinition {
 const node = definition.nodes.find(row => row.id === id && row.type === 'decisao')
 if (!node) throw new Error('Decisão não encontrada.')
 const condition = cloneFlow(decisionCondition(node)); let cases = Array.isArray(condition.casos) ? condition.casos.map(object) : null
 let edges = definition.edges.map(edge => ({ ...edge }))
 const remap = (from: string, to: string | null) => { edges = edges.flatMap(edge => {
  if (edge.source !== id || decisionEdgeHandle(node, edge) !== from && edge.branch !== from) return [edge]
  return to === null ? [] : [{ ...edge, branch: to }]
 }) }
 if (action.type === 'mode') {
  if (action.switch === !!cases) return definition
  if (action.switch) {
   cases = [{ nome: 'caso_1', operador: condition.operador || '>', valor: condition.valor ?? '', ramo: condition.ramo_verdadeiro ?? [] }]
   remap('sim', 'caso:caso_1'); remap('nao', 'senao')
   condition.ramo_senao = condition.ramo_falso ?? []; condition.ramo_verdadeiro = []; condition.ramo_falso = []
   condition.on_error = condition.on_error === 'ramo_falso' ? 'senao' : 'falhar'
  } else {
   if ((cases?.length ?? 0) > 1) throw new Error('Para voltar ao modo binário, deixe no máximo um caso.')
   const first = cases?.[0]
   if (first && Object.keys(first).some(key => !['nome','operador','valor','ramo'].includes(key))) throw new Error('O caso contém campos adicionais. Preserve a configuração antes de converter para o modo binário.')
   if (first) remap('caso:' + text(first.nome), 'sim')
   remap('senao', 'nao'); condition.ramo_verdadeiro = first?.ramo ?? []; condition.ramo_falso = condition.ramo_senao ?? []
   condition.operador = first?.operador ?? condition.operador; condition.valor = first?.valor ?? condition.valor
   condition.on_error = condition.on_error === 'senao' ? 'ramo_falso' : 'falhar'
   condition.casos = undefined; condition.ramo_senao = undefined; cases = null
  }
 } else {
  if (!cases) throw new Error('Selecione o modo de múltiplos casos.')
  if (action.type === 'add') {
   if (cases.length >= 10) throw new Error('Máximo de dez casos por decisão.')
   let sequence = cases.length + 1
   while (cases.some(row => text(row.nome).toLowerCase() === `caso_${sequence}`)) sequence++
   cases.push({ nome: `caso_${sequence}`, operador: '=', valor: '', ramo: [] })
  } else {
   const old = cases[action.index]
   if (!old) throw new Error('Caso não encontrado.')
   if (action.type === 'update') {
    const patch = { ...action.patch }
    if ('nome' in patch) {
     const name = text(patch.nome).trim()
     if (!name || name.length > 40 || name.toLowerCase() === 'senao' || cases.some((row, i) => i !== action.index && text(row.nome).toLowerCase() === name.toLowerCase())) throw new Error('Informe um nome de caso único, com até 40 caracteres. Senão é reservado.')
     patch.nome = name; remap('caso:' + text(old.nome), 'caso:' + name)
    }
    cases[action.index] = { ...old, ...patch }
   } else if (action.type === 'remove') {
    if (cases.length <= 1) throw new Error('Mantenha pelo menos um caso.')
    remap('caso:' + text(old.nome), null); cases.splice(action.index, 1)
   } else {
    const target = action.index + action.delta
    if (target < 0 || target >= cases.length) return definition
    ;[cases[action.index], cases[target]] = [cases[target], cases[action.index]]
   }
  }
 }
 if (cases) condition.casos = cases
 return { ...patchSpecializedDefinition(definition, id, condition), edges }
}
export function attachLooseEnds(definition: WorkspaceDefinition, id: string, sources: string[]): WorkspaceDefinition {
 if (!definition.nodes.some(node => node.id === id && node.type === 'aguarde')) throw new Error('Aguarde não encontrado.')
 return sources.reduce((next, source) => connectWorkspace(next, source, id), definition)
}
