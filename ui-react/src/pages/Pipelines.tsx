import { useState, useMemo, useCallback, useRef, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiFetch } from '../lib/api'
import { useAuthStore } from '../store/auth'
import { Button } from '../components/ui/Button'
import { Select } from '../components/ui/Input'
import { Autocomplete } from '../components/ui/Autocomplete'
import { PageSpinner } from '../components/ui/Spinner'
import { InfoBanner } from '../components/ui/InfoBanner'
import { toast } from '../components/ui/Toast'
import { useAirflowUrl } from '../lib/config'
import { ChevronRight, ChevronDown, Plus } from 'lucide-react'
import type { Pipeline } from '../types/pipeline'
import { DAG_FACTORY_ID, pipelineToDagId, exportModeloCsv } from '../components/pipelines/pipelineUtils'
import { PipelineFormModal } from '../components/pipelines/PipelineFormModal'
import { PipelineRow } from '../components/pipelines/PipelineRow'
import {
  ViewModal, AuditModal, LineageModal, InactivateModal,
  GenDagModal, ExecModal,
} from '../components/pipelines/PipelineModals'

export default function Pipelines() {
  const qc      = useQueryClient()
  const user    = useAuthStore(s => s.user)
  const isViewer = user?.perfil === 'consulta'
  const airflowUiUrl = useAirflowUrl()

  const [nameFilter,    setNameFilter]    = useState('')
  const [projectFilter, setProjectFilter] = useState('')
  const [activeFilter,  setActiveFilter]  = useState('')
  const [domainFilter,  setDomainFilter]  = useState('')
  const [expanded,     setExpanded]     = useState<Set<string>>(new Set())
  const [expandedDoms, setExpandedDoms] = useState<Set<string>>(new Set())

  const [viewPipeline,        setViewPipeline]        = useState<Pipeline | undefined>()
  const [editPipeline,        setEditPipeline]        = useState<Pipeline | undefined>()
  const [showNew,             setShowNew]             = useState(false)
  const [auditPipeline,       setAuditPipeline]       = useState<Pipeline | undefined>()
  const [lineagePipeline,     setLineagePipeline]     = useState<Pipeline | undefined>()
  const [inactivatePipeline,  setInactivatePipeline]  = useState<Pipeline | undefined>()
  const [execPipeline,        setExecPipeline]        = useState<Pipeline | undefined>()
  const [genDagPipeline,      setGenDagPipeline]      = useState<Pipeline | undefined>()
  const revalidateTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    return () => { if (revalidateTimerRef.current) clearTimeout(revalidateTimerRef.current) }
  }, [])

  // Carrega TODOS os pipelines do filtro (agrega as páginas do backend, que limita
  // a 100/req) para as pastas por projeto ficarem completas — sem partir entre
  // páginas (o que dava a falsa sensação de pipeline excluído).
  const { data, isLoading } = useQuery<{ total: number; data: Pipeline[] }>({
    queryKey: ['pipelines', nameFilter, projectFilter, activeFilter],
    queryFn: async () => {
      const all: Pipeline[] = []
      let offset = 0, total = 0
      do {
        const qs = new URLSearchParams({ limit: '100', offset: String(offset) })
        if (nameFilter)          qs.set('filter_name',    nameFilter)
        if (projectFilter)       qs.set('filter_project', projectFilter)
        if (activeFilter !== '')  qs.set('filter_active', activeFilter)
        const r = await apiFetch<{ total: number; data: Pipeline[] }>(`/pipelines?${qs}`)
        total = r.total
        all.push(...r.data)
        offset += 100
        if (offset > 5000) break  // guarda de segurança
      } while (all.length < total)
      return { total, data: all }
    },
  })

  const { data: projData } = useQuery<{ projects: string[] }>({
    queryKey: ['pipeline-projects'],
    queryFn: () => apiFetch('/pipelines/projects'),
    staleTime: 300_000,
  })
  const projects = projData?.projects ?? []

  const tree = useMemo(() => {
    const t: Record<string, Record<string, Pipeline[]>> = {}
    ;(data?.data ?? []).forEach(p => {
      const proj = p.project_name || '(sem projeto)'
      const dom  = p.domain       || '(sem domínio)'
      if (domainFilter && dom.toUpperCase() !== domainFilter.toUpperCase()) return
      if (!t[proj]) t[proj] = {}
      if (!t[proj][dom]) t[proj][dom] = []
      t[proj][dom].push(p)
    })
    return t
  }, [data, domainFilter])

  const projNames = useMemo(() => Object.keys(tree).sort(), [tree])

  const allDomains = useMemo(() => {
    const s = new Set<string>()
    ;(data?.data ?? []).forEach(p => { if (p.domain) s.add(p.domain) })
    return [...s].sort()
  }, [data])

  const genDagMut = useMutation({
    mutationFn: (p: Pipeline) => {
      const runId = `orquestra_ui_${Date.now()}`
      return apiFetch(`/airflow/dags/${DAG_FACTORY_ID}/dagRuns`, {
        method: 'POST',
        body: JSON.stringify({ dag_run_id: runId, conf: { pipeline_name: p.pipeline_name } }),
      })
    },
    onSuccess: (_d, p) => {
      toast.success(`Factory disparada para "${p.pipeline_name}" — aguarde para ver resultado.`)
      setGenDagPipeline(undefined)
      if (revalidateTimerRef.current) clearTimeout(revalidateTimerRef.current)
      revalidateTimerRef.current = setTimeout(() => qc.invalidateQueries({ queryKey: ['pipelines'] }), 10_000)
    },
    onError: (e: unknown) => {
      const msg = e instanceof Error ? e.message : 'Erro inesperado'
      toast.error(`Erro ao gerar DAG: ${msg}`)
    },
  })

  const execMut = useMutation({
    mutationFn: (p: Pipeline) => {
      const dagId = pipelineToDagId(p.pipeline_name)
      return apiFetch<{ dag_run_id?: string }>(`/airflow/dags/${encodeURIComponent(dagId)}/dagRuns`, {
        method: 'POST',
        body: JSON.stringify({ dag_run_id: `manual_orq_${Date.now()}`, conf: {} }),
      })
    },
    onSuccess: (res, p) => {
      const dagId = pipelineToDagId(p.pipeline_name)
      setExecPipeline(undefined)
      toast.success(`Pipeline disparado! (${res?.dag_run_id ?? 'ok'})`)
      window.open(`${airflowUiUrl}/dags/${dagId}/grid`, '_blank')
    },
    onError: (e: unknown) => {
      const msg = e instanceof Error ? e.message : ''
      if (msg.startsWith('404')) toast.error('DAG não encontrada. Gere o DAG primeiro.')
      else if (msg.startsWith('409')) toast.error('Já existe uma execução ativa para este pipeline.')
      else toast.error(msg || 'Erro ao executar')
    },
  })

  const fetchPipelineNames = useCallback(
    (q: string) =>
      apiFetch<{ data: { pipeline_name: string }[] }>(`/pipelines?limit=10&filter_name=${encodeURIComponent(q)}`)
        .then(r => r.data.map(p => p.pipeline_name)),
    [],
  )

  const total = data?.total ?? 0

  return (
    <div className="flex flex-col gap-4">

      <InfoBanner icon="≡" storageKey="pipelines">
        <strong>Pipelines:</strong> são os fluxos de ETL orquestrados no Airflow. Cada pipeline agrupa um conjunto
        de <strong>jobs</strong> executados em ordem (serial e paralelo), com <strong>agendamento</strong>,
        notificações, criticidade e dependências entre si. Use <strong>Novo Pipeline</strong> para cadastrar com o
        assistente passo a passo, ou expanda um projeto/domínio para visualizar, editar, gerar a DAG e executar.
      </InfoBanner>

      {/* Filter bar */}
      <div className="bg-panel border border-edge rounded-xl p-4">
        <div className="flex flex-wrap gap-3 items-end">
          <Autocomplete
            label="Nome"
            value={nameFilter}
            onChange={v => setNameFilter(v)}
            fetchSuggestions={fetchPipelineNames}
            placeholder="filtrar por nome…"
            className="w-64"
          />
          <Select label="Projeto" value={projectFilter}
            onChange={e => setProjectFilter(e.target.value)} className="w-40">
            <option value="">Todos</option>
            {projects.map(p => <option key={p}>{p}</option>)}
          </Select>
          <Select label="Domínio" value={domainFilter}
            onChange={e => setDomainFilter(e.target.value)} className="w-40">
            <option value="">Todos</option>
            {allDomains.map(d => <option key={d}>{d}</option>)}
          </Select>
          <Select label="Status" value={activeFilter}
            onChange={e => setActiveFilter(e.target.value)} className="w-32">
            <option value="">Todos</option>
            <option value="1">Ativos</option>
            <option value="0">Inativos</option>
          </Select>
          <div className="flex gap-2 ml-auto items-end">
            <Button variant="secondary" size="sm" onClick={() => { setNameFilter(''); setProjectFilter(''); setDomainFilter(''); setActiveFilter('') }}>
              × Limpar
            </Button>
            <Button variant="secondary" size="sm" onClick={exportModeloCsv} title="Baixar modelo CSV para importação em massa">
              ↓ Exportar modelo
            </Button>
            {!isViewer && (
              <Button size="sm" onClick={() => setShowNew(true)}>
                <Plus size={13} /> Novo pipeline
              </Button>
            )}
          </div>
        </div>
      </div>

      {/* Count */}
      {!isLoading && (
        <div className="flex items-center justify-between text-xs text-dim px-1">
          <span>{total} pipeline{total !== 1 ? 's' : ''} em {Object.keys(tree).length} projeto{Object.keys(tree).length !== 1 ? 's' : ''}</span>
        </div>
      )}

      {isLoading && <PageSpinner />}

      {!isLoading && total === 0 && (
        <div className="bg-panel border border-edge rounded-xl py-16 flex flex-col items-center gap-2 text-dim">
          <span className="text-4xl">◎</span>
          <p className="text-sm font-medium">Nenhum pipeline encontrado</p>
          <p className="text-xs">Ajuste os filtros ou crie um novo pipeline.</p>
        </div>
      )}

      {/* Tree: projeto → domínio → pipelines */}
      {!isLoading && projNames.map(proj => {
        const isExpanded = expanded.has(proj)
        const domNames   = Object.keys(tree[proj]).sort()
        const totalProj  = domNames.reduce((s, d) => s + tree[proj][d].length, 0)
        const activeProj = domNames.reduce((s, d) => s + tree[proj][d].filter(p => p.active).length, 0)
        return (
          <div key={proj} className="bg-panel border border-edge rounded-xl overflow-hidden">
            <button
              onClick={() => setExpanded(s => { const n = new Set(s); n.has(proj) ? n.delete(proj) : n.add(proj); return n })}
              className="w-full flex items-center gap-2 px-4 py-3 bg-canvas hover:bg-edge/20 transition-colors text-left"
            >
              {isExpanded ? <ChevronDown size={15} className="text-dim flex-shrink-0" /> : <ChevronRight size={15} className="text-dim flex-shrink-0" />}
              <span className="font-semibold text-ink text-sm">{proj}</span>
              <span className="text-xs text-dim">
                {totalProj} pipeline{totalProj !== 1 ? 's' : ''} · {activeProj} ativo{activeProj !== 1 ? 's' : ''}
              </span>
            </button>

            {isExpanded && domNames.map(dom => {
              const domKey      = `${proj}::${dom}`
              const isDomOpen   = expandedDoms.has(domKey)
              const toggleDom   = () => setExpandedDoms(s => { const n = new Set(s); n.has(domKey) ? n.delete(domKey) : n.add(domKey); return n })
              const domPipelines = tree[proj][dom]
              return (
                <div key={dom}>
                  <button
                    onClick={toggleDom}
                    className="w-full flex items-center gap-2 px-5 py-1.5 bg-panel/60 border-t border-edge/30 hover:bg-edge/10 transition-colors text-left"
                  >
                    {isDomOpen
                      ? <ChevronDown size={11} className="text-dim flex-shrink-0" />
                      : <ChevronRight size={11} className="text-dim flex-shrink-0" />}
                    <span className="text-[10px] font-bold uppercase tracking-wider text-dim">{dom}</span>
                    <span className="text-[10px] text-dim/40 ml-1">({domPipelines.length})</span>
                  </button>
                  {isDomOpen && domPipelines.map(p => (
                    <PipelineRow
                      key={p.pipeline_name}
                      pipeline={p}
                      isViewer={isViewer}
                      onView={()        => setViewPipeline(p)}
                      onEdit={()        => setEditPipeline(p)}
                      onLineage={()     => setLineagePipeline(p)}
                      onAudit={()       => setAuditPipeline(p)}
                      onInactivate={()  => setInactivatePipeline(p)}
                      onGenDag={()      => setGenDagPipeline(p)}
                      onExec={()        => setExecPipeline(p)}
                    />
                  ))}
                </div>
              )
            })}
          </div>
        )
      })}

      {/* Modals */}
      {showNew            && <PipelineFormModal onClose={() => setShowNew(false)} />}
      {editPipeline       && <PipelineFormModal pipeline={editPipeline} onClose={() => setEditPipeline(undefined)} />}
      {viewPipeline       && <ViewModal pipeline={viewPipeline} onClose={() => setViewPipeline(undefined)} />}
      {auditPipeline      && <AuditModal pipeline={auditPipeline} onClose={() => setAuditPipeline(undefined)} />}
      {lineagePipeline    && <LineageModal pipeline={lineagePipeline} onClose={() => setLineagePipeline(undefined)} />}
      {inactivatePipeline && <InactivateModal pipeline={inactivatePipeline} onClose={() => setInactivatePipeline(undefined)} />}
      {execPipeline       && (
        <ExecModal
          pipeline={execPipeline}
          loading={execMut.isPending}
          onConfirm={() => execMut.mutate(execPipeline)}
          onClose={() => { if (!execMut.isPending) setExecPipeline(undefined) }}
        />
      )}
      {genDagPipeline     && (
        <GenDagModal
          pipeline={genDagPipeline}
          loading={genDagMut.isPending}
          onConfirm={() => genDagMut.mutate(genDagPipeline)}
          onClose={() => { if (!genDagMut.isPending) setGenDagPipeline(undefined) }}
        />
      )}
    </div>
  )
}
