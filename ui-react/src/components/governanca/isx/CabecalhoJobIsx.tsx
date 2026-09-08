// Cabeçalho de um job extraído: nome, projeto, pasta, tipo, descrição, última
// modificação no DataStage, quando/quem extraiu e o badge cache × extraído agora.
import { useState } from 'react'
import { Zap, Download, AlertTriangle } from 'lucide-react'
import { Badge } from '../../ui/Badge'
import { formatarBytes, formatarDuracao, type JobIsx } from '../../../lib/lineageIsx'

interface Props {
  job: JobIsx
  /** Como o último resultado chegou: true = cache, false = extraído agora, undefined = só banco. */
  cacheHit?: boolean
}

export function CabecalhoJobIsx({ job, cacheHit }: Props) {
  const [longa, setLonga] = useState(false)
  const naoRec = job.nao_reconhecidos?.length ?? 0
  return (
    <div className="flex flex-col gap-2 border border-edge rounded-lg bg-panel p-3" data-cabecalho-job>
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-sm font-semibold text-ink break-all" data-job-nome>{job.job_name}</span>
        <Badge value="neutral">{job.job_type ?? '?'}</Badge>
        {job.status === 'erro' && <Badge value="error">erro na última extração</Badge>}
        {cacheHit === true && (
          <span className="inline-flex items-center gap-1 text-xs text-dim" data-badge-cache>
            <Zap size={12} className="text-amber-600 dark:text-amber-400" /> dados do cache
          </span>
        )}
        {cacheHit === false && (
          <span className="inline-flex items-center gap-1 text-xs text-dim" data-badge-extraido>
            <Download size={12} className="text-emerald-700 dark:text-emerald-400" /> extraído agora do DataStage
          </span>
        )}
      </div>
      <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-1 text-xs">
        <div className="flex gap-2"><dt className="text-dim w-28 shrink-0">Projeto</dt><dd className="font-mono text-ink">{job.ds_project ?? '—'}</dd></div>
        <div className="flex gap-2"><dt className="text-dim w-28 shrink-0">Pasta</dt><dd className="font-mono text-ink break-all">{job.ds_folder_path ?? '—'}</dd></div>
        <div className="flex gap-2"><dt className="text-dim w-28 shrink-0">Modificado no DS</dt><dd className="font-mono text-ink">{job.ds_last_modified ?? '—'}</dd></div>
        <div className="flex gap-2"><dt className="text-dim w-28 shrink-0">Extraído</dt>
          <dd className="text-ink">{job.extracted_at ?? '—'}{job.extracted_by ? ` por ${job.extracted_by}` : ''}
            {job.duracao_ms !== null && job.duracao_ms !== undefined ? ` · ${formatarDuracao(job.duracao_ms)}` : ''}
            {job.isx_bytes ? ` · .isx ${formatarBytes(job.isx_bytes)}` : ''}</dd></div>
      </dl>
      {job.status === 'erro' && job.erro && (
        <div className="flex items-start gap-2 rounded-md border px-3 py-2 text-xs bg-red-50 border-red-200 text-red-800 dark:bg-red-900/20 dark:border-red-800 dark:text-red-300" data-erro-job>
          <AlertTriangle size={14} className="shrink-0 mt-0.5" />
          <span>{job.erro}{job.stages.length > 0
            ? ' — os dados abaixo são da última extração que deu certo.'
            : ' — ainda não houve extração que desse certo para este job.'}</span>
        </div>
      )}
      {job.job_description && <p className="text-sm text-ink" data-descricao>{job.job_description}</p>}
      {job.job_long_description && (
        <div>
          <button type="button" onClick={() => setLonga(v => !v)} data-acao="descricao-longa"
            className="text-xs text-dim hover:text-ink underline-offset-2 hover:underline">
            {longa ? 'Ocultar descrição completa' : 'Ver descrição completa'}
          </button>
          {longa && <p className="mt-1 text-xs text-ink whitespace-pre-line" data-descricao-longa>{job.job_long_description}</p>}
        </div>
      )}
      {naoRec > 0 && (
        <p className="text-[11px] text-dim" data-nao-reconhecidos>
          {naoRec} stage(s) com tipo fora do mapa: {job.nao_reconhecidos.map(n => `${n.stage} (${n.stage_type})`).join(', ')} — o Admin pode incluir o tipo em etl_stage_type_map.
        </p>
      )}
    </div>
  )
}
