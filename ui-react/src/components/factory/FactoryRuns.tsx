import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '../../lib/api'
import { Badge } from '../ui/Badge'
import { Button } from '../ui/Button'
import { PageSpinner } from '../ui/Spinner'
import { RefreshCw, ChevronDown, ChevronUp } from 'lucide-react'
import { fmtDt } from '../execucao/ExecucaoDetailModal'

// ── types ──────────────────────────────────────────────────────────────────

interface FactoryRun {
  dag_run_id: string
  iniciado_em: string
  finalizado_em: string
  estado: string
  escopo: string
  geradas: number
  erros: number
}

interface FactoryRunDetail {
  dag_run_id: string
  estado: string
  steps: { tipo: string; msg: string }[]
  erros_lista: string[]
}

// ── helpers ────────────────────────────────────────────────────────────────

function stepIcon(tipo: string) {
  const m: Record<string, string> = {
    reset: '🔄', gerada: '✅', erro: '❌', iniciando: '▶️', concluido: '🏁', info: 'ℹ️',
    aguardando: '⏳', ativada: '🟢', timeout: '⚠️',
  }
  return m[tipo] ?? '•'
}

// ── Factory Runs ───────────────────────────────────────────────────────────

export function FactoryRuns() {
  const [expanded, setExpanded] = useState<string | null>(null)

  const { data, isLoading, refetch } = useQuery<{ data: FactoryRun[] }>({
    queryKey: ['factory-runs'],
    queryFn: () => apiFetch('/factory/runs?limit=20'),
  })

  const { data: logData } = useQuery<FactoryRunDetail>({
    queryKey: ['factory-log', expanded],
    queryFn: () => apiFetch(`/factory/runs/${encodeURIComponent(expanded!)}/log`),
    enabled: !!expanded,
  })

  if (isLoading) return <PageSpinner />

  const runs = data?.data ?? []

  return (
    <div className="flex flex-col gap-3">
      <div className="flex justify-end">
        <Button variant="secondary" size="sm" onClick={() => refetch()}><RefreshCw size={13} /> Atualizar</Button>
      </div>
      {runs.length === 0 && (
        <p className="text-dim text-sm text-center py-12">Nenhuma publicação encontrada.</p>
      )}
      {runs.map(r => (
        <div key={r.dag_run_id} className="bg-panel border border-edge rounded-lg overflow-hidden">
          <button
            className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-edge/30 transition-colors"
            onClick={() => setExpanded(expanded === r.dag_run_id ? null : r.dag_run_id)}
          >
            <Badge value={r.estado} />
            <div className="flex-1 min-w-0">
              <div className="text-xs text-ink font-mono truncate">{r.dag_run_id}</div>
              <div className="text-xs text-dim">
                {r.escopo} · {r.geradas} geradas · {r.erros} erros
              </div>
            </div>
            <span className="text-xs text-dim shrink-0">{fmtDt(r.iniciado_em)}</span>
            {expanded === r.dag_run_id ? <ChevronUp size={14} className="shrink-0 text-dim" /> : <ChevronDown size={14} className="shrink-0 text-dim" />}
          </button>

          {expanded === r.dag_run_id && (
            <div className="border-t border-edge bg-canvas px-4 py-3">
              {!logData ? (
                <PageSpinner />
              ) : (
                <div className="flex flex-col gap-1.5">
                  {logData.steps?.map((s, i) => (
                    <div key={i} className="flex items-start gap-2 text-xs">
                      <span className="shrink-0 w-5">{stepIcon(s.tipo)}</span>
                      <span className={
                        s.tipo === 'erro' || s.tipo === 'timeout' ? 'text-red-600 dark:text-red-400'
                          : s.tipo === 'gerada' || s.tipo === 'ativada' ? 'text-green-700 dark:text-green-400'
                          : s.tipo === 'aguardando' ? 'text-amber-700 dark:text-amber-400 font-medium'
                          : 'text-dim'}>
                        {s.msg}
                      </span>
                    </div>
                  ))}
                  {logData.erros_lista?.length > 0 && (
                    <div className="mt-2 bg-red-50 border border-red-200 dark:bg-red-900/20 dark:border-red-800 rounded p-2">
                      <p className="text-xs text-red-700 dark:text-red-400 font-medium mb-1">Erros:</p>
                      {logData.erros_lista.map((e, i) => (
                        <p key={i} className="text-xs text-red-700 dark:text-red-300">{e}</p>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}
