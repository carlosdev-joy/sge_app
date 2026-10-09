import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { workspaceApi } from '../../lib/workspaceApi'
import { compareWorkspaceVersions, workspacePath } from '../../lib/workspace'
import { useAuthStore } from '../../store/auth'
import { Button } from '../ui/Button'
import { Select } from '../ui/Input'
import { PageSpinner } from '../ui/Spinner'
export function WorkspaceVersions({name, canRestore}: {name: string; canRestore: boolean}) {
 const token = useAuthStore(s => s.token), client = useQueryClient(), navigate = useNavigate()
 const [left, setLeft] = useState(''), [right, setRight] = useState(''), [error, setError] = useState('')
 const versions = useQuery({queryKey: ['workspace-versions',token,name], queryFn: ({signal}) => workspaceApi.versions(name,signal), retry:false})
 const restore = useMutation({mutationFn: (id: string) => workspaceApi.restore(name,id), onSuccess: () => {client.invalidateQueries({queryKey:['workspace-context',token,name]});navigate(workspacePath(name,'fluxo','desenvolvimento'))}, onError: value => setError(value.message)})
 if(versions.isPending) return <PageSpinner/>
 if(versions.isError) return <p role="alert" className="text-sm text-red-700 dark:text-red-400">{versions.error.message}</p>
 const before = versions.data.find(v => v.versionId === left), after = versions.data.find(v => v.versionId === right)
 const changes = before && after ? compareWorkspaceVersions({definition:before.definition,layout:before.layout},{definition:after.definition,layout:after.layout}) : []
 return <section className="bg-panel border border-edge rounded-lg p-5 space-y-5"><div><h2 className="font-semibold text-ink">Versões do pipeline</h2><p className="text-sm text-dim mt-1">Restaurar cria um rascunho. Valide e publique para torná-lo ativo.</p></div>
  {versions.data.length ? <div className="overflow-x-auto"><table className="w-full text-sm text-left"><thead className="text-dim"><tr><th className="py-2 pr-4">Versão</th><th className="pr-4">Estado</th><th className="pr-4">Criada em</th><th>Restauração</th></tr></thead><tbody>{versions.data.map(v => <tr key={v.versionId} className="border-t border-edge"><td className="py-3 pr-4 text-ink tabular-nums">{v.number}</td><td className="pr-4 text-dim">{v.state === 'publicado' ? 'Publicada' : v.state === 'importada' ? 'Base importada' : 'Publicação não confirmada'}</td><td className="pr-4 text-dim whitespace-nowrap">{new Date(v.createdAt).toLocaleString('pt-BR')}</td><td>{canRestore && v.state === 'publicado' ? <Button size="sm" variant="secondary" loading={restore.isPending} onClick={() => restore.mutate(v.versionId)}>Criar rascunho desta versão</Button> : '—'}</td></tr>)}</tbody></table></div> : <p className="text-sm text-dim">Nenhuma versão registrada neste pipeline.</p>}
  {versions.data.length > 1 && <div className="space-y-3"><h3 className="font-semibold text-sm text-ink">Comparar versões</h3><div className="grid sm:grid-cols-2 gap-3">{[[left,setLeft,'Versão anterior'],[right,setRight,'Versão seguinte']].map(([value,setter,label]) => <Select key={String(label)} label={String(label)} value={String(value)} onChange={e => (setter as (value:string)=>void)(e.target.value)}><option value="">Selecione</option>{versions.data.map(v => <option key={v.versionId} value={v.versionId}>Versão {v.number}</option>)}</Select>)}</div>{before && after && <><p className="text-sm text-dim">{changes.length} campo(s) alterado(s)</p>{changes.length > 0 && <div className="overflow-x-auto"><table className="w-full text-xs text-left"><thead className="text-dim"><tr><th className="py-2 pr-3">Campo</th><th className="pr-3">Anterior</th><th>Seguinte</th></tr></thead><tbody>{changes.map(change => <tr key={change.path} className="border-t border-edge"><td className="py-2 pr-3 break-all text-ink">{change.path}</td><td className="pr-3 text-dim break-all">{JSON.stringify(change.before) ?? 'Ausente'}</td><td className="text-ink break-all">{JSON.stringify(change.after) ?? 'Ausente'}</td></tr>)}</tbody></table></div>}</>}</div>}
  {error && <p role="alert" className="text-sm text-red-700 dark:text-red-400">{error}</p>}
 </section>
}
