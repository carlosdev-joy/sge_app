import { lazy, Suspense, useContext, type ReactNode } from 'react'
import { CONFIGURATION_GROUPS, type ConfigurationGroup } from '../../lib/workspaceTabs'
import type { WorkspaceDefinition } from '../../lib/workspace'
import type { SecretContext } from './WorkspaceSecretParameter'
import { WorkspaceJsonTools, WorkspacePipelineGroup } from './WorkspaceDraftTools'
import { WorkspaceAlerts } from './WorkspaceAlerts'
import { PageSpinner } from '../ui/Spinner'
import { OverlayScope } from '../ui/overlay'
const WorkspaceParameters = lazy(() => import('./WorkspaceParameters').then(module => ({ default: module.WorkspaceParameters })))

// Configuração do pipeline: um grupo visível por vez, todos montados para
// conservar o estado local dos formulários ao alternar grupos e abas.
// Cada grupo tem seu escopo de overlay: o herdado da aba E o grupo visível.
// Um overlay aberto num grupo que saiu de vista (ex.: catálogo de Parâmetros e
// o usuário volta para Identificação) fica montado e inerte, e um grupo
// visível nunca reativa overlays de uma aba oculta.
export function WorkspaceConfiguration({group,onGroup,definition,editable,onApply,canApply,secretContext,responsible,status,saveAction,jsonKey}:{group:ConfigurationGroup;onGroup:(group:ConfigurationGroup)=>void;definition:WorkspaceDefinition;editable:boolean;onApply:(next:WorkspaceDefinition)=>void;canApply:()=>boolean;secretContext?:SecretContext;responsible?:string;status:string;saveAction?:ReactNode;jsonKey:string}) {
 const overlayScope=useContext(OverlayScope)
 return <div className="grid gap-4 lg:grid-cols-[208px_minmax(0,1fr)] items-start">
  <nav aria-label="Grupos da configuração" className="flex lg:flex-col gap-1 overflow-x-auto lg:sticky lg:top-4">{CONFIGURATION_GROUPS.map(([id,label])=><button key={id} type="button" aria-current={group===id?'true':undefined} onClick={()=>onGroup(id)} className={`shrink-0 text-left rounded-md px-3 py-2 text-sm whitespace-nowrap focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-600 ${group===id?'bg-blue-50 text-blue-700 font-semibold dark:bg-blue-900/30 dark:text-blue-300':'text-dim hover:text-ink hover:bg-edge/30'}`}>{label}</button>)}</nav>
  <div className="min-w-0 max-w-4xl">
   {CONFIGURATION_GROUPS.map(([id,label,description])=><OverlayScope.Provider key={id} value={overlayScope&&group===id}>{id==='parametros'
    ?<section hidden={group!==id} aria-label={label}><Suspense fallback={<PageSpinner/>}><WorkspaceParameters secretContext={secretContext} definition={definition} editable={editable} canApply={canApply} onApply={next=>{if(canApply())onApply(next)}}/></Suspense></section>
    :<section hidden={group!==id} aria-labelledby={`workspace-config-${id}`} className="bg-panel border border-edge rounded-lg p-5 sm:p-6 space-y-5">
    <div><h2 id={`workspace-config-${id}`} className="text-base font-semibold text-ink">{label}</h2><p className="text-sm text-dim mt-1">{description}</p></div>
    {id==='notificacoes'?<>
      <WorkspaceAlerts active={overlayScope&&group===id} definition={definition} editable={editable} onApply={onApply} canApply={canApply} context={secretContext}/>
      <details className="border-t border-edge pt-5">
        <summary className="cursor-pointer text-sm font-medium text-ink">Comunicações atuais e destinatários dos componentes</summary>
        <div className="mt-4 space-y-4">
          <p className="text-sm text-dim">Estas configurações continuam atendendo aos fluxos e componentes atuais. A política acima não substitui as comunicações já configuradas.</p>
          <WorkspacePipelineGroup group={id} definition={definition} editable={editable} onApply={next=>{if(canApply())onApply(next)}} responsible={responsible}/>
        </div>
      </details>
    </>:<WorkspacePipelineGroup group={id} definition={definition} editable={editable} onApply={onApply} responsible={responsible}/>}
   </section>}</OverlayScope.Provider>)}
   <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-edge pt-4"><p className="text-sm text-dim" role="status">{status}</p>{saveAction}</div>
   <details className="mt-4 text-sm"><summary className="cursor-pointer text-dim hover:text-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-600">Avançado</summary><div className="mt-3 space-y-2"><p className="text-xs text-dim">Edição direta dos metadados do pipeline. Campos desconhecidos são preservados; referências protegidas continuam na origem.</p><WorkspaceJsonTools key={jsonKey} mode="metadata" definition={definition} editable={editable} onApply={onApply}/></div></details>
  </div>
 </div>
}
