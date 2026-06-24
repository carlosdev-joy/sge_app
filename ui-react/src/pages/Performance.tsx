import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '../lib/api'
import { KpiCard } from '../components/ui/Card'
import { Input } from '../components/ui/Input'
import { Button } from '../components/ui/Button'
import { PageSpinner } from '../components/ui/Spinner'
import { Gauge, RefreshCw } from 'lucide-react'
import { durStr, fmtDt } from '../components/execucao/ExecucaoDetailModal'

// ── Tipos do retorno de GET /performance ─────────────────────────────────────
interface PerfRow {
  pipeline: string
  project: string
  execution_id: string
  alerta_horas: number       // limite (em horas) cuja ultrapassagem disparou o alerta
  elapsed_seconds: number    // duração real da execução (segundos)
  snapshot_at: string        // ISO datetime de quando o snapshot foi tirado
}
interface PerfResp {
  total: number
  offset: number
  limit: number
  pages: number
  data: PerfRow[]
}

const LIMIT = 100

// Excedente = quanto a execução passou do limite de SLA (nunca negativo).
const excedenteSeg = (r: PerfRow) => Math.max(0, r.elapsed_seconds - r.alerta_horas * 3600)

export default function Performance() {
  const [pipeline, setPipeline] = useState('')        // texto digitado no input
  const [filtro, setFiltro] = useState('')            // termo efetivamente aplicado
  const [page, setPage] = useState(0)

  const qs = new URLSearchParams({ limit: String(LIMIT), offset: String(page * LIMIT) })
  if (filtro) qs.set('pipeline', filtro)

  const { data, isLoading, refetch } = useQuery<PerfResp>({
    queryKey: ['performance', filtro, page],
    queryFn: () => apiFetch(`/performance?${qs}`),
  })

  const aplicar = () => { setFiltro(pipeline.trim()); setPage(0) }

  const rows = data?.data ?? []
  const total = data?.total ?? 0
  const pages = data?.pages ?? 0

  // KPIs calculados sobre a página corrente.
  const pipelinesDistintos = new Set(rows.map(r => r.pipeline)).size
  const maiorExcedente = rows.reduce((mx, r) => Math.max(mx, excedenteSeg(r)), 0)

  return (
    <div className="flex flex-col gap-5">
      <div>
        <h1 className="text-lg font-semibold text-ink flex items-center gap-2">
          <Gauge size={20} className="text-[#1A5FA8]" /> Performance
        </h1>
        <p className="text-sm text-dim mt-1">
          Alertas de duração — execuções que ultrapassaram o limite de SLA configurado.
        </p>
      </div>

      {/* Filtro */}
      <div className="bg-panel border border-edge rounded-lg p-4 flex flex-wrap gap-3 items-end">
        <Input label="Pipeline" value={pipeline}
          onChange={e => setPipeline(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && aplicar()}
          placeholder="nome do pipeline" className="w-52" />
        <div className="flex gap-2 ml-auto items-end">
          <Button size="sm" onClick={() => { aplicar(); refetch() }}>
            <RefreshCw size={13} /> Atualizar
          </Button>
        </div>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
        <KpiCard label="Alertas (total)" value={total} color="red" />
        <KpiCard label="Pipelines distintos" value={pipelinesDistintos} color="blue" />
        <KpiCard label="Maior excedente" value={maiorExcedente ? durStr(maiorExcedente) : '—'} color="yellow" />
      </div>

      {/* Tabela */}
      {isLoading ? <PageSpinner /> : (
        <div className="bg-panel border border-edge rounded-lg overflow-hidden">
          <div className="px-4 py-2 border-b border-edge">
            <span className="text-xs text-dim">{total} alerta{total !== 1 ? 's' : ''}</span>
          </div>

          {rows.length === 0 ? (
            <p className="text-dim text-sm text-center py-12">Nenhum alerta de duração registrado.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead><tr className="text-xs text-dim border-b border-edge bg-canvas">
                  <th className="px-4 py-2 text-left">Pipeline</th>
                  <th className="px-4 py-2 text-left">Projeto</th>
                  <th className="px-4 py-2 text-left">Execution ID</th>
                  <th className="px-4 py-2 text-left">Limite</th>
                  <th className="px-4 py-2 text-left">Duração</th>
                  <th className="px-4 py-2 text-left">Excedente</th>
                  <th className="px-4 py-2 text-left">Quando</th>
                </tr></thead>
                <tbody>
                  {rows.map(r => (
                    <tr key={`${r.execution_id}-${r.pipeline}`}
                      className="border-b border-edge/50 hover:bg-edge/20 transition-colors">
                      <td className="px-4 py-2 font-mono text-xs text-ink font-medium">{r.pipeline}</td>
                      <td className="px-4 py-2 text-dim text-xs">{r.project}</td>
                      <td className="px-4 py-2">
                        <span className="font-mono text-xs text-blue-400" title={r.execution_id}>
                          {r.execution_id.slice(0, 18)}…
                        </span>
                      </td>
                      <td className="px-4 py-2 text-dim text-xs whitespace-nowrap">{r.alerta_horas}h</td>
                      <td className="px-4 py-2 text-dim text-xs whitespace-nowrap">{durStr(r.elapsed_seconds)}</td>
                      <td className="px-4 py-2">
                        <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium whitespace-nowrap border bg-red-100 text-red-700 border-red-300 dark:bg-red-900/40 dark:text-red-300 dark:border-red-800">
                          {durStr(excedenteSeg(r))}
                        </span>
                      </td>
                      <td className="px-4 py-2 text-dim text-xs whitespace-nowrap">{fmtDt(r.snapshot_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Paginação */}
          <div className="px-4 py-2 flex items-center gap-3 border-t border-edge">
            <Button variant="ghost" size="sm" disabled={page === 0} onClick={() => setPage(p => p - 1)}>← Anterior</Button>
            <span className="text-xs text-dim">Página {page + 1} de {Math.max(pages, 1)}</span>
            <Button variant="ghost" size="sm" disabled={page + 1 >= pages} onClick={() => setPage(p => p + 1)}>Próxima →</Button>
          </div>
        </div>
      )}
    </div>
  )
}
