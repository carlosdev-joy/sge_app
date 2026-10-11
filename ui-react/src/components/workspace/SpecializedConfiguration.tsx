import { useLayoutEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import type { Node, Edge } from '@xyflow/react'
import { apiFetch } from '../../lib/api'
import { cloneFlow, encryptedParameter, object, pipelineParameters, type WorkspaceDefinition, type WorkspaceNode } from '../../lib/workspace'
import { attachLooseEnds, editDecisionCases, patchSpecializedDefinition, specializedConfiguration, specializedConfigurationIssue, type DecisionCaseAction } from '../../lib/workspaceSpecialized'
import { decisionEdgeHandle } from '../../lib/workspaceDecision'
import { toNodeCondition } from '../etapas/condition'
import { toSqlConfig, toEmailNoConfig, toNotifyConfig, toAguardeConfig, pontasSoltas, type MsgGrupo, type SqlConfig, type EmailNoConfig, type NotifyConfig, type AguardeConfig } from '../etapas/fluxoTypes'
import type { NodeCondition } from '../etapas/DecisaoNode'
import { novaValidacao, type ValidaConfig } from '../../lib/validaArquivo'
import type { CatalogoApi } from '../../lib/pipelineCatalogo'
import { PainelSql } from '../etapas/paineis/PainelSql'
import { PainelDecisao } from '../etapas/paineis/PainelDecisao'
import { PainelEmail } from '../etapas/paineis/PainelEmail'
import { PainelNotificacao } from '../etapas/paineis/PainelNotificacao'
import { PainelAguarde } from '../etapas/paineis/PainelAguarde'
import { PainelValidaArquivo } from '../etapas/paineis/PainelValidaArquivo'
import { Button } from '../ui/Button'
import { toast } from '../ui/Toast'

function panelNode(node: WorkspaceNode): Node {
 const raw = specializedConfiguration(node)
 const value = Object.keys(raw).length ? raw : null
 const config = node.type === 'sql' ? { sql: toSqlConfig(value as unknown as SqlConfig) }
  : node.type === 'decisao' ? { condition: toNodeCondition(raw) }
  : node.type === 'email' ? { email: toEmailNoConfig(value as unknown as EmailNoConfig) }
  : node.type === 'notificacao' ? { notify: toNotifyConfig(value as unknown as NotifyConfig) }
  : node.type === 'aguarde' ? { aguarde: toAguardeConfig(value as unknown as AguardeConfig) }
  : node.type === 'valida_arquivo' ? { valida_arquivo: Object.keys(raw).length ? raw : novaValidacao() } : {}
 return { id: node.id, type: node.type, position: { x: 0, y: 0 }, data: { name: node.id, workspace: true, ...config } }
}
// Inline no inspector: os painéis editam uma cópia do rascunho (base) e aplicar
// entrega base e cópia para a Montagem mesclar só o que mudou (etapa e ramos).
export default function SpecializedConfiguration({ node, definition, editable, canApply, onApply, onStaging, onDiscard, onMaximize }: {
 node: WorkspaceNode; definition: WorkspaceDefinition; editable: boolean; canApply: () => boolean;
 onApply: (next: WorkspaceDefinition, base: WorkspaceDefinition) => boolean; onStaging: (dirty: boolean) => void; onDiscard: () => void; onMaximize?: () => void;
}) {
 const issue = specializedConfigurationIssue(node)
 const [base] = useState(definition)
 const [dirty, setDirty] = useState(false)
 const [staged, setStaged] = useState(() => {
  const flow = cloneFlow(base)
  if (issue || Object.keys(specializedConfiguration(node)).length) return flow
  const data = panelNode(node).data
  const key = { sql: 'sql', decisao: 'condition', email: 'email', notificacao: 'notify', aguarde: 'aguarde', valida_arquivo: 'valida_arquivo' }[node.type]
  return key ? patchSpecializedDefinition(flow, node.id, object(data[key])) : flow
 })
 const current = useRef({ editable, canApply, staged })
 useLayoutEffect(() => { current.current = { editable, canApply, staged } })
 const allowed = () => !issue && current.current.editable && current.current.canApply()
 const ssh = useQuery<{ connections: { conn_id: string; host: string }[] }>({ queryKey: ['ssh-connections'], queryFn: () => apiFetch('/airflow/connections/ssh'), staleTime: 300_000 })
 const sql = useQuery<{ connections: { conn_id: string; host: string }[] }>({ queryKey: ['mssql-connections'], queryFn: () => apiFetch('/airflow/connections/mssql'), staleTime: 300_000 })
 const groups = useQuery<{ data: MsgGrupo[] }>({ queryKey: ['msg-grupos'], queryFn: () => apiFetch('/msg/grupos'), enabled: node.type === 'notificacao' })
 const nodes = staged.nodes.map(panelNode); const selected = nodes.find(row => row.id === node.id)!
 selected.data.isNew = !Object.keys(specializedConfiguration(node)).length
 const edges: Edge[] = staged.edges.map((edge, index) => ({ id: String(index), source: edge.source, target: edge.target }))
 const defaults = pipelineParameters(staged).filter(row => !encryptedParameter(row))
 const directories = defaults.filter(row => ['String','Pathname'].includes(String(row.param_type)) && row.param_source === 'fixo')
 function mutate(operation: (definition: WorkspaceDefinition) => WorkspaceDefinition): boolean {
  if (!allowed()) return false
  try { const next = operation(current.current.staged); current.current.staged = next; setStaged(next); if (!dirty) { setDirty(true); onStaging(true) } return true }
  catch (error) { toast.error(error instanceof Error ? error.message : 'Não foi possível alterar a configuração.'); return false }
 }
 const patch = (id: string, value: object) => mutate(flow => patchSpecializedDefinition(flow, id, value as Record<string, unknown>))
 const caseAction = (action: DecisionCaseAction) => mutate(flow => editDecisionCases(flow, node.id, action))
 const common = { node: selected, onRename: () => false, onDelete: () => {} }
 const ramos: Record<string, string[]> = {}
 const currentNode = staged.nodes.find(row => row.id === node.id)!
 for (const edge of staged.edges.filter(row => row.source === node.id)) {
  const handle = decisionEdgeHandle(currentNode, edge)
  if (handle) { const name = handle.startsWith('caso:') ? handle.slice(5) : handle; ramos[name] = [...(ramos[name] ?? []), edge.target] }
 }
 const sqlNames = staged.edges.filter(edge => edge.target === node.id && staged.nodes.some(row => row.id === edge.source && row.type === 'sql')).map(edge => edge.source)
 if (issue) return <p role="status" className="text-sm text-dim">{issue}</p>
 return <div className="min-w-0 space-y-4">
  {!editable && <p role="status" className="text-sm text-dim">Modo consulta. Inicie a edição do rascunho para alterar esta configuração.</p>}
  <fieldset disabled={!editable} className="min-w-0">
   {node.type === 'sql' && <PainelSql {...common} mssqlConns={sql.data?.connections ?? []} onPatchSql={patch} canPreview={allowed} onMaximizar={onMaximize}/>}
   {node.type === 'email' && <PainelEmail {...common} sqlNames={sqlNames} onPatchEmail={patch}/>}
   {node.type === 'notificacao' && <PainelNotificacao {...common} grupos={groups.data?.data ?? []} onPatchNotify={patch}/>}
   {node.type === 'aguarde' && <PainelAguarde {...common} entradas={staged.edges.filter(edge => edge.target === node.id).length} pontasSoltas={pontasSoltas(node.id, staged.nodes.map(row => row.id), staged.edges)} onPatchAguarde={patch} onPrenderPontasSoltas={() => mutate(flow => attachLooseEnds(flow, node.id, pontasSoltas(node.id, flow.nodes.map(row => row.id), flow.edges)))}/>}
   {node.type === 'decisao' && <PainelDecisao {...common} onMaximizar={onMaximize} nodes={nodes} ramos={ramos} jobNames={staged.nodes.map(row => row.id)} sqlNodeNames={sqlNames} mssqlConns={sql.data?.connections ?? []} onPatchCondition={(id, value: Partial<NodeCondition>) => patch(id, value)} onSimular={(_, branch) => toast.info(`Prévia do rascunho: ramo ${branch}. Nenhuma etapa foi executada.`)} canPreview={allowed} onAlternarModo={(_, mode) => caseAction({ type: 'mode', switch: mode })} onAddCaso={() => caseAction({ type: 'add' })} onUpdateCaso={(_, index, value) => caseAction({ type: 'update', index, patch: value })} onRemoveCaso={(_, index) => caseAction({ type: 'remove', index })} onMoveCaso={(_, index, delta) => caseAction({ type: 'move', index, delta })}/>}
   {node.type === 'valida_arquivo' && <PainelValidaArquivo {...common} pipeline={staged.identity.pipelineName} nodes={nodes} edges={edges} sshConns={ssh.data?.connections ?? []} catalogOverride={defaults as unknown as CatalogoApi[]} canPreview={allowed} onPatchData={(id, value) => patch(id, object(value.valida_arquivo) as unknown as ValidaConfig)} previewOverride={body => apiFetch('/workspace-adapter/valida-arquivo/preview', { method: 'POST', body: JSON.stringify({ ...JSON.parse(body), taskId: node.id, catalog: directories.map(row => ({ param_name: row.param_name, param_type: row.param_type, param_source: row.param_source, param_value: row.param_value })) }) })}/>}
  </fieldset>
  {editable && <div className="space-y-2 border-t border-edge pt-4"><p className="text-xs text-dim">Aplicar inclui na Montagem desta aba; Salvar rascunho persiste e Publicar é uma ação separada.</p><div className="flex flex-wrap justify-end gap-2"><Button variant="secondary" disabled={!dirty} onClick={onDiscard}>Descartar alterações</Button><Button disabled={!dirty} onClick={() => { if (!allowed()) { toast.info('A sessão de edição mudou. Inicie a edição para aplicar; o formulário continua aqui.'); return }; onApply(current.current.staged, base) }}>Aplicar à etapa</Button></div></div>}
 </div>
}
