// Aba "Job DataStage" da Governança (spec docs/spec-lineage-isx.md, F4): seletor de
// pipeline, lista de jobs com o estado ISX, Extrair/Atualizar (acao_editar), lote
// (admin), cabeçalho, grafo, tabela e painel por stage; sequence com os filhos.
// É o container (react-query): a bancada testa os componentes de apresentação.
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Search, Layers, Loader2 } from 'lucide-react'
import { apiFetch } from '../../../lib/api'
import { useAuthStore } from '../../../store/auth'
import { Button } from '../../ui/Button'
import { toast } from '../../ui/Toast'
import { ListaJobsIsx } from './ListaJobsIsx'
import { CabecalhoJobIsx } from './CabecalhoJobIsx'
import { FilhosSequenceIsx } from './FilhosSequenceIsx'
import { GrafoIsx } from './GrafoIsx'
import { TabelaStagesIsx } from './TabelaStagesIsx'
import { PainelStageIsx } from './PainelStageIsx'
import {
  erroIsx, fraseResumoLote, idDoStage,
  type JobIsx, type PipelineIsx, type RunLoteIsx,
} from '../../../lib/lineageIsx'

const inputCls = 'border border-edge bg-canvas text-ink text-sm rounded-md px-2.5 py-1.5 focus:outline-none focus:ring-2 focus:ring-[#1A5FA8]/40 placeholder:text-dim'
const enc = encodeURIComponent
const cat = <T,>(body: object) => apiFetch<T>('/catalogo', { method: 'POST', body: JSON.stringify(body) })

interface Props { pipeline: string; setPipeline: (p: string) => void }

export function PainelJobIsx({ pipeline, setPipeline }: Props) {
  const [input, setInput] = useState(pipeline)
  const [jobEscolhido, setJobEscolhido] = useState('')
  const [stageSel, setStageSel] = useState<string | null>(null)
  const [extraindo, setExtraindo] = useState<string | null>(null)
  const [ultimo, setUltimo] = useState<{ job: string; cacheHit: boolean } | null>(null)
  const [runId, setRunId] = useState<string | null>(null)
  const [pipelineAnterior, setPipelineAnterior] = useState(pipeline)
  const perms = useAuthStore(s => s.user?.permissoes) ?? []
  const podeEditar = perms.includes('acao_editar')
  const ehAdmin = useAuthStore(s => s.isAdmin)()
  const qc = useQueryClient()

  // Pipeline trocado por fora (aba Catálogo → "ver lineage"): ajusta o estado
  // durante o render, sem efeito (react-hooks/set-state-in-effect).
  if (pipeline !== pipelineAnterior) {
    setPipelineAnterior(pipeline)
    setInput(pipeline)
    setJobEscolhido(''); setStageSel(null); setUltimo(null); setRunId(null)
  }

  const { data: pipeList } = useQuery<{ pipelines: string[] }>({
    queryKey: ['list_pipelines'], queryFn: () => cat({ mode: 'list_pipelines' }), staleTime: 5 * 60_000,
  })
  const estado = useQuery<PipelineIsx>({
    queryKey: ['isx-pipeline', pipeline],
    queryFn: () => apiFetch(`/lineage/isx/pipeline?pipeline_name=${enc(pipeline)}`),
    enabled: !!pipeline,
  })
  const jobs = useMemo(() => estado.data?.jobs ?? [], [estado.data])
  // Sem escolha do usuário, o primeiro job com lineage (senão o primeiro) — derivado, não estado.
  const jobSel = jobEscolhido || (jobs.find(j => j.isx?.status === 'ok') ?? jobs[0])?.job_name || ''
  const jobAtual = jobs.find(j => j.job_name === jobSel)

  const detalhe = useQuery<JobIsx>({
    queryKey: ['isx-job', pipeline, jobSel],
    queryFn: () => apiFetch(`/lineage/isx/job?pipeline_name=${enc(pipeline)}&job_name=${enc(jobSel)}`),
    enabled: !!pipeline && !!jobSel && !!jobAtual?.isx,
  })

  const extrair = useMutation({
    mutationFn: ({ job, forcar }: { job: string; forcar: boolean }) =>
      apiFetch<JobIsx>('/lineage/isx/extrair', {
        method: 'POST', body: JSON.stringify({ pipeline_name: pipeline, job_name: job, force: forcar }),
      }),
    // Clicar em Extrair/Atualizar É escolher o job: fixa a seleção antes do resultado,
    // senão a seleção derivada ("1º job ok") pularia para outro job se este falhar.
    onMutate: ({ job }) => { setExtraindo(job); setJobEscolhido(job); setStageSel(null) },
    onSuccess: (dados, { job }) => {
      qc.setQueryData(['isx-job', pipeline, job], dados)
      void qc.invalidateQueries({ queryKey: ['isx-pipeline', pipeline] })
      setUltimo({ job, cacheHit: !!dados.cache_hit })
      toast.success(dados.cache_hit ? `${job}: o lineage já estava atualizado (cache).` : `${job}: lineage extraído do DataStage.`)
    },
    onError: (e, { job }) => {
      toast.error(erroIsx(e).mensagem)
      // a API registra a tentativa no cabeçalho: lista E detalhe do job saem do cache
      void qc.invalidateQueries({ queryKey: ['isx-pipeline', pipeline] })
      void qc.invalidateQueries({ queryKey: ['isx-job', pipeline, job] })
    },
    onSettled: () => setExtraindo(null),
  })

  const lote = useMutation({
    mutationFn: () => apiFetch<{ dag_run_id: string; state: string }>('/lineage/isx/lote', {
      method: 'POST', body: JSON.stringify({ pipeline_name: pipeline }),
    }),
    onSuccess: (r) => { setRunId(r.dag_run_id); toast.info(`Lote disparado (${r.dag_run_id}).`) },
    onError: (e) => toast.error(erroIsx(e).mensagem),
  })
  const run = useQuery<RunLoteIsx>({
    queryKey: ['isx-lote', runId],
    queryFn: () => apiFetch(`/lineage/isx/lote/${enc(runId ?? '')}`),
    enabled: !!runId,
    refetchInterval: (q) => {
      if (q.state.status === 'error') return false   // erro ao consultar: para e mostra
      const s = q.state.data?.state
      return s === 'success' || s === 'failed' ? false : 5000
    },
  })
  const runTerminou = run.data?.state === 'success' || run.data?.state === 'failed' || run.isError
  useEffect(() => {
    if (!runTerminou) return
    void qc.invalidateQueries({ queryKey: ['isx-pipeline', pipeline] })
    void qc.invalidateQueries({ queryKey: ['isx-job', pipeline] })
  }, [runTerminou, qc, pipeline])

  const carregar = () => { setPipeline(input.trim()) }
  const selecionarJob = useCallback((job: string) => { setJobEscolhido(job); setStageSel(null); setUltimo(null) }, [])
  const job = detalhe.data
  const stageAtual = job?.stages.find(s => idDoStage(s) === stageSel) ?? null
  const nomesDoPipeline = useMemo(() => new Set(jobs.map(j => j.job_name)), [jobs])

  return (
    <div className="flex flex-col gap-4" data-painel-isx>
      <div className="flex flex-wrap gap-2 items-center">
        <input list="isx-pipeline-list" value={input} onChange={e => setInput(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') carregar() }}
          placeholder="Nome do pipeline…" className={`${inputCls} w-72`} data-campo="pipeline" />
        <datalist id="isx-pipeline-list">
          {(pipeList?.pipelines ?? []).map(n => <option key={n} value={n} />)}
        </datalist>
        <Button type="button" onClick={carregar} disabled={!input.trim()} loading={estado.isFetching}><Search size={13} /> Carregar</Button>
        {estado.data && (
          <span className="text-xs text-dim">
            Projeto DataStage <span className="font-mono text-ink">{estado.data.ds_project || '—'}</span> · {jobs.length} job(s)
            · {jobs.filter(j => j.isx?.status === 'ok').length} com lineage ISX
          </span>
        )}
        {ehAdmin && estado.data && jobs.length > 0 && (
          <Button type="button" variant="secondary" size="sm" onClick={() => lote.mutate()} loading={lote.isPending}
            disabled={!!runId && !runTerminou} title="Dispara a DAG etl_lineage_extract_isx para todos os jobs deste pipeline" data-acao="lote">
            <Layers size={13} /> Extrair todos (lote)
          </Button>
        )}
      </div>

      {runId && (
        <div className="text-xs text-dim flex items-center gap-2" data-lote-estado={run.isError ? 'erro' : (run.data?.state ?? 'queued')}>
          {!runTerminou && <Loader2 size={12} className="animate-spin" />}
          {run.isError
            ? <span className="text-red-700 dark:text-red-400">Não foi possível acompanhar o lote: {erroIsx(run.error).mensagem}</span>
            : <span>{fraseResumoLote(run.data?.resumo, run.data?.state)}</span>}
          {run.data?.resumo?.erros.length ? (
            <span title={run.data.resumo.erros.map(e => `${e.job_name}: ${e.detail}`).join('\n')} className="underline decoration-dotted cursor-help">ver erros</span>
          ) : null}
        </div>
      )}

      {estado.isError && <p className="text-sm text-red-700 dark:text-red-400" data-erro-pipeline>{erroIsx(estado.error).mensagem}</p>}
      {!pipeline && <p className="text-sm text-dim">Informe o pipeline: o lineage ISX é por job mapeado num pipeline do Orquestra.</p>}

      {estado.data && (
        <div className="grid grid-cols-1 lg:grid-cols-[20rem_1fr] gap-4 items-start">
          <ListaJobsIsx jobs={jobs} selecionado={jobSel} onSelecionar={selecionarJob}
            onExtrair={(j, forcar) => extrair.mutate({ job: j, forcar })} podeEditar={podeEditar} extraindo={extraindo} />

          <div className="flex flex-col gap-4 min-w-0">
            {extraindo && extraindo === jobSel && (
              <div className="flex items-center gap-2 text-sm text-dim" data-extraindo>
                <Loader2 size={16} className="animate-spin" /> Extraindo {extraindo} do DataStage… (istool, até 60 s)
              </div>
            )}
            {jobAtual && !jobAtual.isx && !extraindo && !job && (
              <p className="text-sm text-dim" data-nao-extraido>
                <span className="font-mono text-ink">{jobAtual.job_name}</span> ainda não foi extraído do DataStage.
                {podeEditar ? ' Use o botão Extrair ao lado.' : ' Peça a extração a quem tem permissão de edição.'}
              </p>
            )}
            {jobAtual?.isx && detalhe.isLoading && <p className="text-sm text-dim">Carregando…</p>}
            {jobAtual?.isx && detalhe.isError && <p className="text-sm text-red-700 dark:text-red-400" data-erro-job>{erroIsx(detalhe.error).mensagem}</p>}
            {job && (
              <>
                <CabecalhoJobIsx job={job} cacheHit={ultimo?.job === job.job_name ? ultimo.cacheHit : undefined} />
                {job.job_type === 'SEQUENCE' && (
                  <FilhosSequenceIsx filhos={job.children} jobsDoPipeline={nomesDoPipeline}
                    onSelecionar={selecionarJob} onExtrair={(j) => extrair.mutate({ job: j, forcar: false })}
                    podeEditar={podeEditar} extraindo={extraindo} />
                )}
                {job.stages.length > 0 ? (
                  <>
                    {/* key por job: remonta o grafo e o fitView roda de novo (senão o zoom/offset
                        do job anterior fica e os nós podem cair fora da área) */}
                    <GrafoIsx key={job.job_name} stages={job.stages} flow={job.flow} selecionado={stageSel} onSelecionar={setStageSel} />
                    <TabelaStagesIsx stages={job.stages} selecionado={stageSel} onSelecionar={setStageSel} />
                  </>
                ) : (
                  <p className="text-sm text-dim">Sem stages gravados para este job.</p>
                )}
              </>
            )}
          </div>
        </div>
      )}

      <PainelStageIsx stage={stageAtual} onClose={() => setStageSel(null)} />
    </div>
  )
}
