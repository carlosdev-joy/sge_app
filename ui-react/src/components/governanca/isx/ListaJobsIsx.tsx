// Lista dos jobs do pipeline com o estado da extração ISX (GET /lineage/isx/pipeline).
// Apresentação pura: o container decide o que acontece ao selecionar/extrair.
import { RefreshCw, Download, Loader2 } from 'lucide-react'
import { Badge } from '../../ui/Badge'
import { rotuloEstado, type JobDoPipelineIsx } from '../../../lib/lineageIsx'

interface Props {
  jobs: JobDoPipelineIsx[]
  selecionado: string
  onSelecionar: (job: string) => void
  onExtrair: (job: string, forcar: boolean) => void
  podeEditar: boolean
  extraindo: string | null
}

export function ListaJobsIsx({ jobs, selecionado, onSelecionar, onExtrair, podeEditar, extraindo }: Props) {
  if (jobs.length === 0) {
    return <p className="text-sm text-dim" data-lista-vazia>Este pipeline não tem jobs mapeados.</p>
  }
  return (
    <ul className="flex flex-col divide-y divide-edge border border-edge rounded-lg bg-panel" data-lista-jobs>
      {jobs.map(j => {
        const ehDs = !j.job_type || j.job_type.toLowerCase() === 'datastage'
        const estado = rotuloEstado(j.isx)
        const ativo = j.job_name === selecionado
        const ocupado = extraindo === j.job_name
        const jaTem = !!j.isx && j.isx.status === 'ok'
        return (
          <li key={j.job_name} data-job={j.job_name} data-selecionado={ativo ? '1' : undefined}
            className={`flex items-center gap-2 px-3 py-2 ${ativo ? 'bg-canvas' : ''}`}>
            <button type="button" onClick={() => onSelecionar(j.job_name)} data-acao="selecionar"
              className="flex-1 min-w-0 text-left">
              <div className="flex items-center gap-2">
                <span className={`font-mono text-xs truncate ${ativo ? 'text-ink font-semibold' : 'text-ink'}`}>{j.job_name}</span>
                {j.isx?.ds_job_type && <Badge value="neutral">{j.isx.ds_job_type}</Badge>}
                {!ehDs && <Badge value="neutral">{j.job_type}</Badge>}
              </div>
              {/* badge curto + detalhe truncado com title: a coluna da lista é estreita */}
              <div className="mt-0.5 flex items-center gap-1.5 min-w-0">
                <Badge value={estado.tom}>{ehDs ? (estado.tom === 'error' ? 'erro' : estado.tom === 'neutral' ? 'não extraído' : 'extraído') : 'não é job DataStage'}</Badge>
                {ehDs && estado.tom !== 'neutral' && (
                  <span className="text-[10px] text-dim truncate" title={estado.texto + (j.isx?.extracted_by ? ` · por ${j.isx.extracted_by}` : '')} data-estado-detalhe>
                    {estado.texto.replace(/^(extraído em|erro: )/, '')}{j.isx?.extracted_by ? ` · ${j.isx.extracted_by}` : ''}
                  </span>
                )}
              </div>
            </button>
            {podeEditar && ehDs && (
              <button type="button" disabled={extraindo !== null} onClick={() => onExtrair(j.job_name, jaTem)}
                data-acao="extrair" data-forcar={jaTem ? '1' : '0'}
                title={jaTem ? 'Atualizar: reextrai do DataStage mesmo sem mudança (force)' : 'Extrair o lineage do DataStage (istool)'}
                className="shrink-0 inline-flex items-center gap-1 rounded-md border border-edge bg-panel px-2 py-1 text-xs text-ink hover:bg-canvas disabled:opacity-50 disabled:cursor-not-allowed">
                {ocupado ? <Loader2 size={12} className="animate-spin" /> : jaTem ? <RefreshCw size={12} /> : <Download size={12} />}
                {ocupado ? 'Extraindo…' : jaTem ? 'Atualizar' : 'Extrair'}
              </button>
            )}
          </li>
        )
      })}
    </ul>
  )
}
