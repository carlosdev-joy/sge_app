// Seção "Parâmetros DataStage do pipeline" do wizard (F4 da spec
// docs/spec-parametros-job-datastage.md): os DEFAULTS que valem para toda etapa
// DataStage cujo job declara o nome — a etapa sobrepõe por nome. Reusa o mesmo
// editor da etapa (JobParamsEditor em modo datastage), com a prévia do servidor
// e o "Simular com a referência".
import { useState } from 'react'
import { Hint } from '../ui/Hint'
import { JobParamsEditor } from '../etapas/JobTypeFields'
import { DS_ENCRYPTED_MASCARA, hojeLocalISO, type JobParam } from '../../lib/dsParams'

export function ParametrosPipelineSecao({ params, onChange }: {
  params: JobParam[]
  onChange: (params: JobParam[]) => void
}) {
  const [referencia, setReferencia] = useState(() => hojeLocalISO())
  return (
    <div className="flex flex-col gap-1.5" data-secao-params-pipeline>
      <div className="flex flex-wrap items-center gap-1.5">
        <label className="flex items-center gap-1.5 text-xs font-medium text-dim">
          Parâmetros DataStage do pipeline (opcional)
          <Hint texto={
            'Defaults enviados como -param a TODA etapa DataStage deste pipeline cujo job declarar o nome (conferido no dsjob -lparams); job que não declara ignora, sem erro. A etapa pode sobrepor pelo mesmo nome.\n'
            + 'Origem de data: valor calculado a cada execução na ordem meses → âncora → dias → formato.\n'
            + `Encrypted: cifrado no banco, nunca em log; ${DS_ENCRYPTED_MASCARA} = manter o valor gravado.`
          } />
          {params.length > 0 && (
            <span className="rounded-full border border-blue-300 bg-blue-100 px-1.5 py-0 text-[9px] font-bold text-blue-700 dark:border-blue-800/40 dark:bg-blue-900/30 dark:text-blue-300" data-contagem={params.length}>
              {params.length}
            </span>
          )}
        </label>
        {params.length > 0 && (
          <label className="ml-auto flex items-center gap-1 text-[11px] text-dim">
            Simular com a referência
            <input
              type="date"
              value={referencia}
              onChange={e => setReferencia(e.target.value)}
              className="rounded-md border border-edge bg-panel px-2 py-0.5 text-xs text-ink focus:outline-none focus:ring-1 focus:ring-blue-500"
              data-referencia-previa
            />
          </label>
        )}
      </div>
      <JobParamsEditor modo="datastage" params={params} onChange={onChange} referencia={referencia} />
    </div>
  )
}
