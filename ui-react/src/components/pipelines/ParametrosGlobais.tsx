import { useState } from 'react'
import { atualizarGrupo, type CatalogoParam } from '../../lib/pipelineCatalogo'
import { JobParamsEditor } from '../etapas/JobTypeFields'
import { ParametrosPipelineSecao } from './ParametrosPipeline'
import { ImportarParametros } from './ImportarParametros'
import { ParametroCatalogoSelect } from './ParametroCatalogoSelect'

export function ParametrosGlobais({ params, onChange, pipeline, project }: {
  params: CatalogoParam[]; onChange: (p: CatalogoParam[]) => void; pipeline?: string; project: string
}) {
  const [consulta, setConsulta] = useState('')
  return <div className="space-y-5">
    <p className="text-sm text-dim">Parâmetros compartilhados por este pipeline. Valores definidos na etapa prevalecem sobre seus defaults.</p>
    <ParametrosPipelineSecao params={params.filter(p => p.param_destino === 'datastage')}
      onChange={rows => onChange(atualizarGrupo(params, 'datastage', rows))} pipeline={pipeline} />
    <section className="space-y-2 border-t border-edge pt-4">
      <h3 className="text-sm font-semibold text-ink">Parâmetros Orquestra</h3>
      <p className="text-sm text-dim">Valores internos que não são enviados ao DataStage. A vinculação aos campos dos nós será disponibilizada na próxima etapa desta entrega.</p>
      <JobParamsEditor modo="datastage" params={params.filter(p => p.param_destino === 'orquestra')}
        onChange={rows => onChange(atualizarGrupo(params, 'orquestra', rows))} compact />
    </section>
    {params.some(p => p.param_name.trim()) && <ParametroCatalogoSelect params={params} value={consulta} onChange={setConsulta} />}
    <ImportarParametros key={project} project={project} params={params} onChange={onChange} />
  </div>
}
