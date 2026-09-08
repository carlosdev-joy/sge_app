// Sequence: a lista de jobs que ela chama (children_json). Filho mapeado no
// mesmo pipeline vira link (seleciona) e ganha Extrair; fora do pipeline fica
// só informado — a regra do lineage ISX é "job só com pipeline".
import { Download, ExternalLink } from 'lucide-react'
import type { FilhoIsx } from '../../../lib/lineageIsx'

interface Props {
  filhos: FilhoIsx[]
  jobsDoPipeline: Set<string>
  onSelecionar: (job: string) => void
  onExtrair: (job: string) => void
  podeEditar: boolean
  extraindo: string | null
}

export function FilhosSequenceIsx({ filhos, jobsDoPipeline, onSelecionar, onExtrair, podeEditar, extraindo }: Props) {
  if (filhos.length === 0) {
    return <p className="text-xs text-dim" data-filhos-vazio>Esta sequence não chama nenhum job (ou as atividades não têm JobName).</p>
  }
  // O DataStage distingue caixa e o SQL Server não: o nome que vale daqui em diante é o
  // da LISTA (grafia cadastrada no pipeline), não o do XML da sequence.
  const canonico = (nome: string) => [...jobsDoPipeline].find(j => j.toLowerCase() === nome.toLowerCase()) ?? null
  return (
    <div className="border border-edge rounded-lg bg-panel p-3" data-filhos-sequence>
      <h3 className="text-xs font-semibold text-dim uppercase tracking-wide mb-2">Jobs chamados por esta sequence ({filhos.length})</h3>
      <ul className="flex flex-col gap-1">
        {filhos.map(f => {
          const nome = canonico(f.job_name)
          const dentro = nome !== null
          return (
            <li key={`${f.activity}:${f.job_name}`} data-filho={f.job_name} data-mapeado={dentro ? '1' : '0'}
              className="flex items-center gap-2 text-xs">
              <span className="text-dim w-40 shrink-0 truncate" title={`atividade ${f.activity}`}>{f.activity}</span>
              {nome !== null ? (
                <button type="button" onClick={() => onSelecionar(nome)} data-acao="ver-filho"
                  className="inline-flex items-center gap-1 font-mono text-ink hover:underline">
                  <ExternalLink size={11} /> {nome}
                </button>
              ) : (
                <span className="font-mono text-ink">{f.job_name} <span className="text-dim">(fora deste pipeline)</span></span>
              )}
              {nome !== null && podeEditar && (
                <button type="button" onClick={() => onExtrair(nome)} disabled={extraindo !== null}
                  data-acao="extrair-filho"
                  className="ml-auto inline-flex items-center gap-1 rounded-md border border-edge px-2 py-0.5 text-[11px] text-ink hover:bg-canvas disabled:opacity-50">
                  <Download size={11} /> Extrair
                </button>
              )}
            </li>
          )
        })}
      </ul>
    </div>
  )
}
