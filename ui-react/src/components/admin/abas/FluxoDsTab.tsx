import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '../../../lib/api'
import { Button } from '../../ui/Button'
import { Input, Select } from '../../ui/Input'
import { DsSeqFlowGraph } from '../../console/DsSeqFlowGraph'
import { PROJETOS } from '../comum'
import { AlertTriangle, RefreshCw, Database } from 'lucide-react'

// ── Fluxo DS (validação do parser do XML) ───────────────────────────────────
interface SeqFlowResp {
  sucesso?: boolean
  nodes?: { id: string; name: string; type: string; jobname?: string | null }[]
  edges?: { source: string; target: string; label: string; cond: string; expr?: string | null }[]
  cached?: boolean
  parsed_at?: string
  source_file?: string
}

export function FluxoDsTab() {
  const [project, setProject] = useState('')
  const [job, setJob] = useState('')
  // req guarda a consulta disparada (nonce força refetch a cada clique).
  const [req, setReq] = useState<{ project: string; job: string; refresh: boolean; nonce: number } | null>(null)

  const projetos = useQuery<{ projects: { project_name: string }[] }>({
    queryKey: ['admin-projects-all'],
    queryFn: () => apiFetch('/pipelines/projects/all'),
  })
  const projectOptions = (projetos.data?.projects ?? []).map(p => p.project_name)
  const options = projectOptions.length ? projectOptions : PROJETOS

  const flow = useQuery<SeqFlowResp>({
    queryKey: ['admin-seq-flow', req?.nonce],
    queryFn: () => apiFetch(
      '/datastage/seq-flow?project=' + encodeURIComponent(req!.project) +
      '&job=' + encodeURIComponent(req!.job) + (req!.refresh ? '&refresh=true' : '')),
    enabled: !!req,
    retry: false,
    staleTime: Infinity,
  })

  const load = (refresh: boolean) => {
    if (!project.trim() || !job.trim()) return
    setReq({ project: project.trim(), job: job.trim(), refresh, nonce: Date.now() })
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-start gap-3 p-4 rounded-lg bg-blue-50 border border-blue-200 dark:bg-blue-900/20 dark:border-blue-800">
        <Database size={16} className="text-blue-600 dark:text-blue-400 mt-0.5 shrink-0" />
        <div className="text-sm text-blue-800 dark:text-blue-300">
          Validação do <strong>fluxo real da Sequence</strong> lido do export XML (idêntico ao desenho do DataStage).
          Use para validar as evoluções do parser. Requer o <code className="font-mono text-xs">{'<projeto>.xml'}</code> importado na malha (<code className="font-mono text-xs">/opt/airflow/dsx</code>).
        </div>
      </div>

      <div className="bg-panel border border-edge rounded-lg p-4 shadow-sm">
        <div className="flex flex-wrap gap-3 items-end">
          <Select label="Projeto" value={project} onChange={e => setProject(e.target.value)} className="w-48">
            <option value="">Selecione…</option>
            {options.map(p => <option key={p}>{p}</option>)}
          </Select>
          <Input label="Sequence (job)" value={job} onChange={e => setJob(e.target.value)}
            placeholder="ex.: SeqSsdVidaGeralDiario" className="w-72"
            onKeyDown={e => { if (e.key === 'Enter') load(false) }} />
          <Button onClick={() => load(false)} loading={flow.isFetching && !req?.refresh} disabled={!project.trim() || !job.trim()}>
            Carregar
          </Button>
          <Button variant="secondary" onClick={() => load(true)} loading={flow.isFetching && !!req?.refresh}
            disabled={!project.trim() || !job.trim()}>
            <RefreshCw size={14} className="mr-1" /> Atualizar do XML
          </Button>
        </div>
      </div>

      {flow.isFetching && (
        <p className="text-sm text-dim">Lendo o fluxo da sequence…</p>
      )}
      {flow.isError && (
        <div className="flex items-start gap-3 p-4 rounded-lg bg-amber-50 border border-amber-200 dark:bg-yellow-900/20 dark:border-yellow-700">
          <AlertTriangle size={16} className="text-amber-600 dark:text-yellow-400 mt-0.5 shrink-0" />
          <p className="text-sm text-amber-800 dark:text-yellow-300">
            Não foi possível obter o fluxo: {(flow.error as any)?.message ?? 'erro'}. Verifique se o XML do projeto está importado e se o job é uma Sequence.
          </p>
        </div>
      )}
      {flow.data?.sucesso && (
        <div className="flex flex-col gap-2">
          <div className="flex flex-wrap items-center gap-2 text-xs text-dim">
            <span>{flow.data.cached ? 'Do cache' : 'Lido do XML agora'}</span>
            {flow.data.parsed_at && <span>· {new Date(flow.data.parsed_at).toLocaleString('pt-BR')}</span>}
            {flow.data.source_file && <span>· <span className="font-mono text-ink">{flow.data.source_file}</span></span>}
            <span className="ml-auto">{flow.data.nodes?.length ?? 0} atividades · {flow.data.edges?.length ?? 0} dependências</span>
          </div>
          <DsSeqFlowGraph nodes={flow.data.nodes ?? []} edges={flow.data.edges ?? []} />
        </div>
      )}
      {!req && (
        <p className="text-xs text-dim">Selecione o projeto, informe a Sequence e clique em <strong>Carregar</strong>.</p>
      )}
    </div>
  )
}
