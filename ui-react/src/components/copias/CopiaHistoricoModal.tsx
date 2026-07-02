// Histórico de execuções de uma cópia (GET /copias/{id}/execucoes, paginado).
// Cada linha abre o modal de progresso/detalhe da execução.
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '../../lib/api'
import { Badge } from '../ui/Badge'
import { Button } from '../ui/Button'
import { Modal } from '../ui/Modal'
import { PageSpinner } from '../ui/Spinner'
import { Eye } from 'lucide-react'
import {
  type CopiaJob, type ExecHistorico,
  STATUS_BADGE, STATUS_LABELS, engineLabel, fmtDuracao, fmtRows,
} from './transformUtils'

interface HistResp { total: number; offset: number; limit: number; data: ExecHistorico[] }

const LIMIT = 20

export function CopiaHistoricoModal({ copia, onClose, onVerExec }: {
  copia: CopiaJob
  onClose: () => void
  onVerExec: (execId: number) => void   // abre o modal de progresso/detalhe
}) {
  const [page, setPage] = useState(0)

  const { data, isLoading } = useQuery<HistResp>({
    queryKey: ['copia-execucoes', copia.id, page],
    queryFn: () => apiFetch(`/copias/${copia.id}/execucoes?limit=${LIMIT}&offset=${page * LIMIT}`),
  })

  const rows = data?.data ?? []
  const total = data?.total ?? 0
  const pages = Math.max(1, Math.ceil(total / LIMIT))

  return (
    <Modal open onClose={onClose} title={`Histórico: ${copia.nome}`} size="lg">
      {isLoading ? <PageSpinner /> : (
        <div className="flex flex-col gap-3">
          <span className="text-xs text-dim">
            {total} {total === 1 ? 'execução' : 'execuções'}
          </span>

          {rows.length === 0 ? (
            <p className="text-dim text-sm text-center py-8">
              Nenhuma execução registrada para esta cópia.
            </p>
          ) : (
            <div className="border border-edge rounded-lg overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-xs text-dim border-b border-edge bg-canvas/50">
                      <th className="px-3 py-2 text-left font-semibold">Quando</th>
                      <th className="px-3 py-2 text-left font-semibold">Status</th>
                      <th className="px-3 py-2 text-right font-semibold">Linhas</th>
                      <th className="px-3 py-2 text-left font-semibold">Duração</th>
                      <th className="px-3 py-2 text-left font-semibold">Engine</th>
                      <th className="px-3 py-2 text-left font-semibold">Quem</th>
                      <th className="px-3 py-2 w-10"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map(e => (
                      <tr key={e.id}
                        onClick={() => onVerExec(e.id)}
                        className="border-b border-edge/50 hover:bg-canvas/50 transition-colors cursor-pointer">
                        <td className="px-3 py-2 text-xs text-dim whitespace-nowrap">{e.criado_em ?? '—'}</td>
                        <td className="px-3 py-2">
                          <Badge value={STATUS_BADGE[e.status] ?? 'neutral'}>
                            {STATUS_LABELS[e.status] ?? e.status}
                          </Badge>
                        </td>
                        <td className="px-3 py-2 text-right text-xs text-ink whitespace-nowrap">
                          {fmtRows(e.rows_copied)}
                          {e.rows_total != null && (
                            <span className="text-dim"> / {fmtRows(e.rows_total)}</span>
                          )}
                        </td>
                        <td className="px-3 py-2 text-xs text-dim whitespace-nowrap">{fmtDuracao(e.duracao_s)}</td>
                        <td className="px-3 py-2 text-xs text-dim whitespace-nowrap"
                          title={e.engine ?? undefined}>
                          {engineLabel(e.engine)}
                        </td>
                        <td className="px-3 py-2 text-xs text-dim font-mono">{e.matricula ?? '—'}</td>
                        <td className="px-3 py-2">
                          <button
                            onClick={ev => { ev.stopPropagation(); onVerExec(e.id) }}
                            className="text-slate-400 hover:text-[#1A5FA8] dark:hover:text-blue-400 p-1 rounded"
                            title="Ver detalhes / progresso">
                            <Eye size={13} />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {pages > 1 && (
            <div className="flex items-center justify-between">
              <Button variant="secondary" size="sm" disabled={page === 0}
                onClick={() => setPage(p => Math.max(0, p - 1))}>
                ← Anteriores
              </Button>
              <span className="text-xs text-dim">página {page + 1} de {pages}</span>
              <Button variant="secondary" size="sm" disabled={page + 1 >= pages}
                onClick={() => setPage(p => p + 1)}>
                Próximas →
              </Button>
            </div>
          )}
        </div>
      )}
    </Modal>
  )
}
