// Fluxos — tela dedicada do editor de fluxo (canvas em tela cheia).
// A tela Etapas mantém o toggle Lista↔Fluxo para edição rápida; aqui é a
// "bancada de montagem": biblioteca de pipelines + canvas com espaço total e
// deep-link estável (?pipeline=). Mesmo componente FluxoEditor, sem fork —
// revisão registrada em docs/DESIGN_navegacao_regroup.md.
import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { apiFetch } from '../lib/api'
import { useAuthStore } from '../store/auth'
import { Button } from '../components/ui/Button'
import { Autocomplete } from '../components/ui/Autocomplete'
import { PageSpinner } from '../components/ui/Spinner'
import { FluxoEditor } from '../components/etapas/FluxoEditor'
import { GitBranch, List, Search, X } from 'lucide-react'

interface PipelineItem {
  pipeline_name: string
  project_name?: string | null
  domain?: string | null
  active?: number | boolean
  last_execution?: string | null
}

export default function Fluxos() {
  const user = useAuthStore(s => s.user)
  const isViewer = user?.perfil === 'consulta'

  // URL é a fonte da verdade do pipeline aberto (deep-link/estado navegável).
  const [searchParams, setSearchParams] = useSearchParams()
  const pipeline = (searchParams.get('pipeline') ?? '').trim()

  const [input, setInput] = useState(pipeline)
  const [busca, setBusca] = useState('')      // filtro da biblioteca (debounced)
  const [q, setQ] = useState('')

  useEffect(() => { setInput(pipeline) }, [pipeline])
  useEffect(() => {
    const t = setTimeout(() => setQ(busca.trim()), 300)
    return () => clearTimeout(t)
  }, [busca])

  function abrir(nome: string) {
    const n = (nome ?? '').trim()
    if (!n) return
    setSearchParams({ pipeline: n })
  }
  function fechar() {
    setSearchParams({})
  }

  // Biblioteca — só busca quando nenhum pipeline está aberto.
  const { data, isLoading } = useQuery<{ data: PipelineItem[]; total: number }>({
    queryKey: ['fluxos-biblioteca', q],
    queryFn: () => apiFetch(`/pipelines?limit=30&filter_name=${encodeURIComponent(q)}`),
    enabled: !pipeline,
  })
  const pipelines = data?.data ?? []

  // ── Canvas em tela cheia (pipeline aberto) ─────────────────────────────────
  if (pipeline) {
    return (
      <div className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="flex items-center gap-2 text-lg font-semibold text-ink">
            <GitBranch size={20} className="text-[#1A5FA8]" /> Fluxo
            <span className="font-mono text-base text-dim">· {pipeline}</span>
          </h1>
          <div className="ml-auto flex items-center gap-2">
            <Button
              variant="secondary" size="sm"
              title="Abrir as etapas deste pipeline em formato de lista"
              onClick={() => window.open(`/jobs?pipeline=${encodeURIComponent(pipeline)}`, '_blank', 'noopener,noreferrer')}
            >
              <List size={13} /> Ver na Lista
            </Button>
            <Button variant="secondary" size="sm" onClick={fechar} title="Voltar à biblioteca de fluxos">
              <X size={13} /> Fechar
            </Button>
          </div>
        </div>
        <div className="h-[calc(100vh-11rem)]">
          <FluxoEditor pipeline={pipeline} readOnly={isViewer} />
        </div>
      </div>
    )
  }

  // ── Biblioteca de fluxos (nenhum pipeline aberto) ──────────────────────────
  return (
    <div className="flex flex-col gap-5">
      <div>
        <h1 className="flex items-center gap-2 text-lg font-semibold text-ink">
          <GitBranch size={20} className="text-[#1A5FA8]" /> Fluxos
        </h1>
        <p className="mt-1 text-sm text-dim">
          Monte a sequência de tarefas de um pipeline no canvas — dependências,
          execução paralela, decisões, SQL e notificações — em tela cheia.
        </p>
      </div>

      <div className="flex flex-wrap items-end gap-3">
        <Autocomplete
          label="Abrir pipeline"
          value={input}
          onChange={setInput}
          onSelect={abrir}
          fetchSuggestions={s =>
            apiFetch<{ data: { pipeline_name: string }[] }>(
              `/pipelines?limit=10&filter_name=${encodeURIComponent(s)}`)
              .then(r => r.data.map(p => p.pipeline_name))
          }
          onKeyDown={e => e.key === 'Enter' && abrir(input)}
          placeholder="ex: etl_cobranca_diaria"
          className="w-72"
        />
        <Button size="sm" onClick={() => abrir(input)} disabled={!input.trim()}>
          Abrir fluxo
        </Button>
        <div className="relative ml-auto">
          <Search size={14} className="pointer-events-none absolute left-2.5 top-2.5 text-dim" />
          <input
            value={busca}
            onChange={e => setBusca(e.target.value)}
            placeholder="Filtrar a lista…"
            className="w-64 rounded-md border border-edge bg-panel py-1.5 pl-8 pr-3 text-sm text-ink placeholder-dim focus:outline-none focus:ring-1 focus:ring-blue-500"
          />
        </div>
      </div>

      {isLoading ? <PageSpinner /> : (
        <div className="overflow-hidden rounded-lg border border-edge bg-panel shadow-sm">
          <div className="border-b border-edge px-4 py-2">
            <span className="text-xs text-dim">
              {pipelines.length} pipeline{pipelines.length !== 1 ? 's' : ''}
              {typeof data?.total === 'number' && data.total > pipelines.length
                ? ` (de ${data.total} — refine o filtro)` : ''}
            </span>
          </div>
          {pipelines.length === 0 ? (
            <p className="py-12 text-center text-sm text-dim">
              Nenhum pipeline encontrado{q ? ' para o filtro atual' : ''}.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-edge bg-canvas/50 text-xs text-dim">
                    <th className="px-4 py-2.5 text-left font-semibold">Pipeline</th>
                    <th className="px-4 py-2.5 text-left font-semibold">Projeto</th>
                    <th className="px-4 py-2.5 text-left font-semibold">Domínio</th>
                    <th className="px-4 py-2.5 text-left font-semibold">Última execução</th>
                    <th className="w-32 px-4 py-2.5"></th>
                  </tr>
                </thead>
                <tbody>
                  {pipelines.map(p => (
                    <tr key={p.pipeline_name}
                      className="cursor-pointer border-b border-edge/50 transition-colors hover:bg-canvas/50"
                      onClick={() => abrir(p.pipeline_name)}>
                      <td className="px-4 py-2.5">
                        <span className="font-mono text-xs font-medium text-ink">{p.pipeline_name}</span>
                        {!p.active && (
                          <span className="ml-2 rounded border border-amber-200 bg-amber-50 px-1.5 py-0.5 text-[10px] text-amber-700 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-300">
                            inativo
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-2.5 text-xs text-ink">{p.project_name ?? '—'}</td>
                      <td className="px-4 py-2.5 text-xs text-ink">{p.domain ?? '—'}</td>
                      <td className="px-4 py-2.5 text-xs text-ink whitespace-nowrap">{p.last_execution ?? '—'}</td>
                      <td className="px-4 py-2.5 text-right">
                        <Button variant="secondary" size="sm"
                          onClick={e => { e.stopPropagation(); abrir(p.pipeline_name) }}>
                          <GitBranch size={12} /> Abrir fluxo
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
