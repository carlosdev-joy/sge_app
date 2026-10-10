import { Navigate, Link, useSearchParams } from 'react-router-dom'
import { legacyWorkspacePath } from '../../lib/workspaceNavigation'
import { useWorkspaceCapabilities } from './useWorkspaceCapabilities'
import { PageSpinner } from '../ui/Spinner'

export function LegacyWorkspaceEntry({kind,children}:{kind:'jobs'|'fluxos';children:React.ReactNode}) {
 const [search]=useSearchParams();const caps=useWorkspaceCapabilities()
 if(caps.isPending&&caps.fetchStatus!=='idle')return <PageSpinner/>
 if(caps.data?.enabled&&caps.data.actions.contextualNavigation&&search.get('legado')!=='1'){
  const target=legacyWorkspacePath(kind,search)
  if(target)return <Navigate to={target} replace/>
  return <section className="space-y-3"><h1 className="text-xl font-semibold text-ink">Abra um pipeline</h1><p className="text-sm text-dim">O desenvolvimento das etapas acontece no Fluxo de cada pipeline. Use a busca da lista para selecionar o contexto.</p><Link to="/pipelines" className="text-blue-700 dark:text-blue-400 underline text-sm">Buscar pipeline</Link></section>
 }
 return <>{children}</>
}
