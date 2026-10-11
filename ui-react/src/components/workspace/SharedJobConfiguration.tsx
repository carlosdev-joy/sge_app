import type { SecretContext } from './WorkspaceSecretParameter'
import { useLayoutEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '../../lib/api'
import { applyWorkspaceJobPatch, jobParameterRows, jsonField, workspaceJobFields, type WorkspaceJobPatch } from '../../lib/workspaceJobFields'
import { encryptedParameter, text, type WorkspaceNode } from '../../lib/workspace'
import type { JobParamApi } from '../../lib/dsParams'
import { JobTypeFields, jobTypeFieldsErrors, pythonFromApi, pythonToApi, type ConnOpt, type JobTypeFieldsValue, type PythonNodeApi } from '../etapas/JobTypeFields'
import { Button } from '../ui/Button'
import { Select } from '../ui/Input'
import { toast } from '../ui/Toast'

export default function SharedJobConfiguration({ node, editable, defaults, context, pipelineName, canApply, onApply, onClose }: {
 context?: SecretContext; pipelineName:string;
 node: WorkspaceNode; editable: boolean; defaults: JobParamApi[]; canApply: () => boolean;
 onApply: (node: WorkspaceNode) => void; onClose: () => void;
}) {
 const [value, setValue] = useState<JobTypeFieldsValue>(() => ({ ...workspaceJobFields(node), python: pythonFromApi(jsonField(jsonField(node.configuration.legacyJob).python_json) as unknown as PythonNodeApi) }))
 const touched = useRef(new Set<keyof JobTypeFieldsValue>())
 const current = useRef({ editable, canApply })
 useLayoutEffect(() => { current.current = { editable, canApply } })
 const allowed = () => current.current.editable && current.current.canApply()
 const ssh = useQuery<{ connections: ConnOpt[] }>({ queryKey: ['ssh-connections'], queryFn: () => apiFetch('/airflow/connections/ssh'), staleTime: 300_000 })
 const mssql = useQuery<{ connections: ConnOpt[] }>({ queryKey: ['mssql-connections'], queryFn: () => apiFetch('/airflow/connections/mssql'), staleTime: 300_000 })
 const errors = jobTypeFieldsErrors(value)
 if (['datastage','shell','storedproc'].includes(node.type) && !value.job_command.trim()) errors.push(node.type === 'storedproc' ? 'Informe o nome da procedure.' : node.type === 'datastage' ? 'Informe o nome do job DataStage.' : 'Informe o comando Shell.')
 if (node.type === 'datastage' && !value.ssh_conn_id) errors.push('Conexão SSH é obrigatória para esta etapa DataStage.')
 if (node.type === 'python' && value.python?.modo === 'modulo' && !value.ssh_conn_id) errors.push('Informe uma conexão SSH para publicar esta etapa Python.')
 const protectedRows = jobParameterRows(node).filter(encryptedParameter)
 function change(patch: Partial<JobTypeFieldsValue>) {
  if (!allowed()) return
  Object.keys(patch).forEach(key => touched.current.add(key as keyof JobTypeFieldsValue))
  setValue(previous => ({ ...previous, ...patch }))
 }
 function apply() {
  if (!allowed()) { toast.info('A sessão de edição mudou. Feche e reabra a configuração após iniciar a edição.'); return }
  if (errors.length) return
  const patch: WorkspaceJobPatch = {}
  for (const key of touched.current) {
   if (key === 'python') { const python = pythonToApi(value.python); patch.python_json = python ? JSON.stringify(python) : null }
   else if (key !== 'job_type') Object.assign(patch, { [key]: value[key] })
  }
  try { onApply(applyWorkspaceJobPatch(node, patch)); onClose() }
  catch (error) { toast.error(error instanceof Error ? error.message : 'Não foi possível aplicar a configuração.') }
 }
 return <div className="space-y-5 min-w-0">
  <p className="text-sm text-dim">{editable ? 'Configure esta etapa no rascunho. Aplicar mantém as alterações no Fluxo; use Salvar rascunho para persistir.' : 'Consulte a configuração desta etapa.'}</p>
  {!editable && <p role="status" className="text-sm text-dim">Modo consulta. Inicie a edição do rascunho para alterar esta configuração.</p>}
  {(ssh.isError || mssql.isError) && <p role="status" className="text-sm text-dim">Não foi possível carregar um catálogo de conexões. Confira a conexão configurada e tente novamente.</p>}
  {errors.length > 0 && <div role="status" className="space-y-1 text-sm text-amber-800 dark:text-amber-300">{errors.map(error => <p key={error}>{error}</p>)}</div>}
  <fieldset disabled={!editable} className="min-w-0">
   {(node.type === 'datastage' || (node.type === 'python' && value.python?.modo === 'modulo')) && <div className="mb-4"><Select label="Servidor SSH (conexão Airflow) *" value={value.ssh_conn_id} onChange={event => change({ ssh_conn_id: event.target.value })}>
    <option value="">Selecione a conexão SSH…</option>
    {(ssh.data?.connections ?? []).map(connection => <option key={connection.conn_id} value={connection.conn_id}>{connection.conn_id}{connection.host ? ` (${connection.host})` : ''}</option>)}
    {value.ssh_conn_id && !(ssh.data?.connections ?? []).some(connection => connection.conn_id === value.ssh_conn_id) && <option value={value.ssh_conn_id}>{value.ssh_conn_id} (fora da lista)</option>}
   </Select></div>}
   <JobTypeFields value={value} onChange={change} sshConns={ssh.data?.connections ?? []} mssqlConns={mssql.data?.connections ?? []} defaultsOverride={defaults} disableEncrypted disableMaestro={!context} pipeline={pipelineName} jobName={node.id} workspaceMaestro={context?{...context,canApply:allowed,defaults}:undefined} canApply={allowed}/>
  </fieldset>
  {protectedRows.length > 0 && <div className="border-t border-edge pt-4 space-y-2"><h4 className="text-sm font-medium text-ink">Parâmetros protegidos</h4>{protectedRows.map((row, index) => <p key={index} className="text-sm text-dim"><span className="font-medium text-ink">{text(row.param_name)}</span> · preservado por referência</p>)}</div>}
  <div className="flex flex-wrap justify-end gap-2 border-t border-edge pt-4"><Button variant="secondary" onClick={onClose}>{editable ? 'Cancelar' : 'Fechar'}</Button>{editable && <Button onClick={apply} disabled={errors.length > 0}>Aplicar ao fluxo</Button>}</div>
 </div>
}
