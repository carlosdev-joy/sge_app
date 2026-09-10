// Seção "Parâmetros DataStage do pipeline" do wizard (F4 da spec
// docs/spec-parametros-job-datastage.md): os DEFAULTS que valem para toda etapa
// DataStage cujo job declara o nome — a etapa sobrepõe por nome. Reusa o mesmo
// editor da etapa (JobParamsEditor em modo datastage), com a prévia do servidor
// e o "Simular com a referência".
import { useEffect, useRef, useState } from 'react'
import { Hint } from '../ui/Hint'
import { toast } from '../ui/Toast'
import { JobParamsEditor } from '../etapas/JobTypeFields'
import { MaestroChat } from '../etapas/MaestroChat'
import { DS_ENCRYPTED_MASCARA, hojeLocalISO, type JobParam } from '../../lib/dsParams'
import { aplicarProposta, resumoAplicacao } from '../../lib/maestro'
import { useMaestroStatus } from '../../lib/maestroStatus'

export function ParametrosPipelineSecao({ params, onChange, pipeline }: {
  params: JobParam[]
  onChange: (params: JobParam[]) => void
  /** Nome do pipeline (vazio no cadastro novo): dá ao Maestro as etapas e o que elas declaram. */
  pipeline?: string
}) {
  const [referencia, setReferencia] = useState(() => hojeLocalISO())
  // Maestro no nível do pipeline: o que ele propõe vira DEFAULT (herdado pelas
  // etapas cujo job declarar o nome). Mesma proteção do editor da etapa: a
  // mescla lê a lista ATUAL via ref, depois do await.
  const maestro = useMaestroStatus(true)
  const paramsRef = useRef(params)
  useEffect(() => { paramsRef.current = params }, [params])
  function aplicarDoMaestro(novos: JobParam[]) {
    const r = aplicarProposta(paramsRef.current, novos)
    onChange(r.params)
    toast.success(resumoAplicacao(r, 'pipeline'))
  }
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
        {maestro.enabled && (
          <MaestroChat
            nivel="pipeline"
            pipeline={(pipeline ?? '').trim() || undefined}
            params={params}
            referencia={referencia}
            sugestoes={maestro.sugestoes}
            onAplicar={aplicarDoMaestro}
          />
        )}
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
