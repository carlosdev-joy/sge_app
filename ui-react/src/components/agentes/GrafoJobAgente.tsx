// O grafo do job citado na conversa, aberto sem sair da tela do agente.
//
// Reaproveita `GrafoIsx` da Governança (critério 5 da F3) — o MESMO
// componente, alimentado pelo MESMO `GET /lineage/isx/job` (só banco, não
// toca o servidor DataStage). Nada é reimplementado aqui: o que este arquivo
// acrescenta é a busca do job e o link de volta para a Governança, onde
// estão a tabela de stages e o painel de detalhe.
//
// O `key` no GrafoIsx é obrigatório: sem ele o `fitView` não roda de novo ao
// trocar de job e o grafo novo herda o zoom do anterior (o mesmo cuidado que
// `PainelJobIsx` já toma).
import { useQuery } from '@tanstack/react-query'
import { ExternalLink } from 'lucide-react'
import { apiFetch } from '../../lib/api'
import type { JobIsx } from '../../lib/lineageIsx'
import { GrafoIsx } from '../governanca/isx/GrafoIsx'
import { mensagemDeErro } from '../../lib/agentes'

interface Props {
  pipeline: string
  job: string
  onFechar: () => void
  stageSel: string | null
  onSelecionarStage: (s: string) => void
}

export function GrafoJobAgente({ pipeline, job, onFechar, stageSel, onSelecionarStage }: Props) {
  const q = useQuery<JobIsx>({
    queryKey: ['agentes-grafo-isx', pipeline, job],
    queryFn: () => apiFetch<JobIsx>(
      `/lineage/isx/job?pipeline_name=${encodeURIComponent(pipeline)}&job_name=${encodeURIComponent(job)}`),
    retry: false,
  })

  const linkGovernanca = `/governanca?tab=isx&pipeline=${encodeURIComponent(pipeline)}&job=${encodeURIComponent(job)}`

  return (
    <section
      className="bg-panel border border-edge rounded-lg shadow-sm p-4 flex flex-col gap-3"
      data-agentes-grafo={job}
      aria-label={`Grafo do job ${job}`}
    >
      <header className="flex flex-wrap items-center justify-between gap-2">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-ink truncate">{job}</h3>
          <p className="text-xs text-dim truncate">{pipeline}</p>
        </div>
        <div className="flex items-center gap-3 shrink-0">
          <a
            href={linkGovernanca}
            className="text-[13px] text-[#1A5FA8] dark:text-blue-400 hover:underline inline-flex items-center gap-1"
          >
            abrir na Governança
            <ExternalLink className="w-3.5 h-3.5" aria-hidden="true" />
          </a>
          <button type="button" onClick={onFechar} className="text-[13px] text-dim hover:text-ink">
            fechar
          </button>
        </div>
      </header>

      {q.isLoading && <p className="text-sm text-dim py-6 text-center">Carregando o grafo…</p>}

      {q.isError && (
        <p className="text-sm text-dim py-6 text-center">
          {mensagemDeErro(q.error, `O job ${job} ainda não tem extração ISX em ${pipeline}.`)}
        </p>
      )}

      {q.data && (
        <GrafoIsx
          key={`${pipeline}/${job}`}
          stages={q.data.stages}
          flow={q.data.flow}
          selecionado={stageSel}
          onSelecionar={onSelecionarStage}
        />
      )}
    </section>
  )
}
