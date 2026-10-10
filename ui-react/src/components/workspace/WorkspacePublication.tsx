import { confirmAction } from '../../lib/dialogs'
import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { CheckCircle2, Upload, ShieldCheck } from 'lucide-react'
import { workspaceApi } from '../../lib/workspaceApi'
import type { WorkspaceDraft, WorkspacePublication, WorkspaceValidation } from '../../lib/workspace'
import { useAuthStore } from '../../store/auth'
import { Button } from '../ui/Button'
const labels: Record<string, string> = { pendente: 'Publicação solicitada', projetado: 'Configuração aplicada; aguardando DAG', gerando: 'Confirmando versão no Airflow', publicado: 'Versão publicada e confirmada', erro: 'Publicação interrompida' }
export function WorkspacePublicationPanel({ embedded = false, draft, fence, canPublish, dirty, busy, onFreeze, onConfirmed, onSelect }: { embedded?: boolean; draft: WorkspaceDraft; fence: number | undefined; canPublish: boolean; dirty: boolean; busy: boolean; onFreeze: (value: boolean) => void; onConfirmed: () => void; onSelect: (id: string) => void }) {
 const token = useAuthStore(s => s.token)
 const [validation, setValidation] = useState<WorkspaceValidation | null>(null)
 const [error, setError] = useState('')
 const [sent, setSent] = useState<WorkspacePublication | null>(null)
 const command = useRef<{revision: number; id: string} | null>(null)
 const confirmed = useRef<string | null>(null)
 const operations = useQuery({ queryKey: ['workspace-publications', token, draft.draftId], queryFn: ({ signal }) => workspaceApi.publications(draft.draftId, signal), retry: false, refetchInterval: 2000 })
 const operation = operations.data?.find(row => row.operationId === sent?.operationId) ?? sent ?? operations.data?.[0]
 const pending = !!operation && !['erro', 'publicado'].includes(operation.state)
 useEffect(() => { onFreeze(pending) }, [pending, operation, draft.revision, onFreeze])
 useEffect(() => { if (operation?.state === 'publicado' && confirmed.current !== operation.operationId) { confirmed.current = operation.operationId; onConfirmed() } }, [operation, onConfirmed])
 const validate = useMutation({ mutationFn: () => workspaceApi.validate(draft.draftId), onSuccess: value => { setValidation(value); setError('') }, onError: value => setError(value.message) })
 const publish = useMutation({ mutationFn: async () => {
  if (!fence || dirty) throw new Error('Salve o rascunho e mantenha a sessão de edição antes de publicar.')
  if (!command.current || command.current.revision !== draft.revision) command.current = { revision: draft.revision, id: crypto.randomUUID() }
  return workspaceApi.publish(draft, fence, command.current.id)
 }, onMutate: () => onFreeze(true), onSuccess: value => { setSent(value); setError(''); onFreeze(true); operations.refetch() }, onError: value => {setError(value.message); onFreeze(pending)} })
 const retry = useMutation({ mutationFn: () => workspaceApi.retry(draft, fence!, operation!.operationId), onSuccess: value => { setSent(value); setError(''); operations.refetch() }, onError: value => setError(value.message) })
 const currentGate=useRef({allowed:false,fence,draftId:draft.draftId,revision:draft.revision})
 const valid = validation?.revision === draft.revision && validation.valid && !dirty
 useLayoutEffect(()=>{currentGate.current={allowed:!!fence&&!!valid&&canPublish&&!busy&&!pending&&!validate.isPending&&!publish.isPending,fence,draftId:draft.draftId,revision:draft.revision}})
 return <section className={`${embedded ? 'border-t border-edge' : 'border border-edge rounded-lg'} bg-panel px-4 py-3 space-y-2`} aria-label="Validação e publicação">
  <div className="flex flex-wrap items-center justify-between gap-3"><div><h2 className="font-semibold text-sm text-ink">Validar e publicar</h2></div><div className="flex flex-wrap gap-2">
   <Button size="sm" variant="secondary" disabled={dirty || busy || pending || publish.isPending} loading={validate.isPending} onClick={() => validate.mutate()}><ShieldCheck size={15}/>Validar rascunho</Button>
   {canPublish && <Button size="sm" disabled={!fence || !valid || busy || pending || validate.isPending} loading={publish.isPending} onClick={async () => { if (await confirmAction('Publicar esta revisão e substituir a configuração ativa do pipeline?',()=>currentGate.current.allowed&&currentGate.current.fence===fence&&currentGate.current.draftId===draft.draftId&&currentGate.current.revision===draft.revision)) publish.mutate() }}><Upload size={15}/>Publicar versão</Button>}
  </div></div>
  {dirty && <p className="text-sm text-dim">Salve as alterações para validar esta revisão.</p>}
  {!canPublish && <p className="text-sm text-dim">Sua sessão pode consultar os diagnósticos. Publicar exige a permissão de publicação.</p>}
  {validation?.revision === draft.revision && !dirty && <div aria-live="polite">{validation.valid ? <p className="flex gap-2 text-sm text-green-800 dark:text-green-300"><CheckCircle2 size={16}/>Revisão {validation.revision} validada</p> : <ul className="space-y-2 text-sm">{validation.diagnostics.map((item, index) => <li key={index} className="text-red-700 dark:text-red-400">{item.nodeId && <button className="font-semibold underline mr-2" onClick={() => onSelect(item.nodeId!)}>{item.nodeId}</button>}{item.message}<span className="block text-xs text-dim">{item.field}</span></li>)}</ul>}</div>}
  {operation && <div role="status" className="text-sm text-ink"><p className="font-medium">{labels[operation.state] ?? 'Estado de publicação indisponível'}</p><p className="text-xs text-dim mt-1">Revisão {operation.revision} · {operation.attempts} tentativa(s). A operação continua no servidor após fechar esta tela.</p>{operation.state === 'erro' && <p className="text-sm text-dim mt-2">Corrija e salve o rascunho para publicar uma nova revisão, ou retome a mesma operação após resolver a dependência. O motor permanece protegido até a confirmação.</p>}{operation.error && <p className="text-red-700 dark:text-red-400 mt-2">{operation.error}</p>}{operation.state === 'erro' && canPublish && <Button size="sm" variant="secondary" className="mt-3" disabled={!fence || dirty || busy || draft.revision !== operation.revision} loading={retry.isPending} onClick={() => retry.mutate()}>Retomar esta publicação</Button>}</div>}
  {(error || operations.isError) && <p role="alert" className="text-sm text-red-700 dark:text-red-400">{error || operations.error?.message}</p>}
 </section>
}
