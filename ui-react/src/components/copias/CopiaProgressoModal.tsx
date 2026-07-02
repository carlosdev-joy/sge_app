// Modal de progresso de uma execução de cópia — abre ao executar ou pelo
// Histórico. Polling em GET /copias/exec/{id} (refetchInterval 2500 enquanto
// pendente/executando/cancelando), barra de progresso, taxa, ETA, engine,
// tabela de faixas (streams) e cancelamento com confirmação.
import { useState, useEffect, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiFetch } from '../../lib/api'
import { useAuthStore } from '../../store/auth'
import { Badge } from '../ui/Badge'
import { Button } from '../ui/Button'
import { Modal } from '../ui/Modal'
import { PageSpinner } from '../ui/Spinner'
import { toast } from '../ui/Toast'
import { AlertTriangle, XCircle } from 'lucide-react'
import {
  type ExecProgresso,
  ENGINE_SERVER_SIDE, EXEC_ATIVA, STATUS_BADGE, STATUS_LABELS,
  engineLabel, faixaIntervalo, fmtDuracao, fmtEta, fmtRows,
} from './transformUtils'

// Duração decorrida (iniciado_em → concluido_em ou agora), em segundos.
function duracaoSegundos(p: ExecProgresso): number | null {
  if (!p.iniciado_em) return null
  try {
    const ini = new Date(p.iniciado_em.replace(' ', 'T')).getTime()
    const fim = p.concluido_em
      ? new Date(p.concluido_em.replace(' ', 'T')).getTime()
      : Date.now()
    return Math.max(0, Math.round((fim - ini) / 1000))
  } catch { return null }
}

function StatusBadge({ status }: { status: string }) {
  return <Badge value={STATUS_BADGE[status] ?? 'neutral'}>{STATUS_LABELS[status] ?? status}</Badge>
}

export function CopiaProgressoModal({ execId, onClose }: {
  execId: number
  onClose: () => void
}) {
  const qc = useQueryClient()
  const user = useAuthStore(s => s.user)
  const isAdmin = useAuthStore(s => s.isAdmin)
  const podeExecutar = isAdmin() || !!user?.permissoes?.includes('acao_executar')
  const [confirmCancel, setConfirmCancel] = useState(false)

  const { data, isLoading, error } = useQuery<ExecProgresso>({
    queryKey: ['copia-exec', execId],
    queryFn: () => apiFetch(`/copias/exec/${execId}`),
    // Polling só enquanto a execução está viva (pendente/executando/cancelando);
    // erro persistente na consulta também interrompe o polling.
    refetchInterval: q => {
      if (q.state.status === 'error') return false
      const s = q.state.data?.status
      return !s || EXEC_ATIVA.has(s) ? 2500 : false
    },
  })

  // Ao concluir (transição ativa → final): toast + invalida a lista de cópias.
  const prevStatus = useRef<string | null>(null)
  useEffect(() => {
    const s = data?.status
    if (!s) return
    const prev = prevStatus.current
    prevStatus.current = s
    if (prev && EXEC_ATIVA.has(prev) && !EXEC_ATIVA.has(s)) {
      if (s === 'concluido') {
        toast.success(`Cópia "${data?.nome ?? ''}" concluída: ${fmtRows(data?.rows_copied)} linhas`)
      } else if (s === 'erro') {
        toast.error(`Cópia "${data?.nome ?? ''}" terminou com erro`)
      } else if (s === 'cancelado') {
        toast.info(`Cópia "${data?.nome ?? ''}" cancelada`)
      }
      qc.invalidateQueries({ queryKey: ['copias'] })
      qc.invalidateQueries({ queryKey: ['copia-execucoes'] })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data?.status])

  const cancelMut = useMutation({
    mutationFn: () => apiFetch<{ id: number; status: string }>(
      `/copias/exec/${execId}/cancelar`, { method: 'POST' }),
    onSuccess: () => {
      toast.info('Cancelamento solicitado — as faixas em andamento serão interrompidas.')
      qc.invalidateQueries({ queryKey: ['copia-exec', execId] })
    },
    onError: (e: any) => toast.error(e?.message || 'Falha ao cancelar'),
  })

  const ativa = !!data && EXEC_ATIVA.has(data.status)
  const pct = data && data.rows_total
    ? Math.min(100, (data.rows_copied / Math.max(1, data.rows_total)) * 100)
    : null
  const dur = data ? duracaoSegundos(data) : null
  // Server-side sem partição (faixa única): o INSERT...SELECT roda inteiro
  // dentro do servidor — não há progresso incremental para mostrar.
  const serverSideFaixaUnica = !!data
    && data.engine === ENGINE_SERVER_SIDE
    && data.ranges.length === 1
    && data.ranges[0].range_index === 0
    && data.ranges[0].valor_ini == null
    && data.ranges[0].valor_fim == null

  return (
    <>
    <Modal open onClose={onClose}
      title={data?.nome ? `Execução: ${data.nome}` : `Execução #${execId}`} size="lg">
      {isLoading ? <PageSpinner /> : error ? (
        <p className="text-sm text-red-700 dark:text-red-400 py-4">
          {(error as any)?.message || 'Execução não encontrada'}
        </p>
      ) : data && (
        <div className="flex flex-col gap-4">

          {/* Status + barra de progresso */}
          <div className="flex flex-col gap-2">
            <div className="flex items-center justify-between">
              <StatusBadge status={data.status} />
              <span className="text-xs text-dim">
                {pct != null
                  ? `${pct.toLocaleString('pt-BR', { maximumFractionDigits: 1 })}%`
                  : ativa ? 'contando linhas…' : ''}
              </span>
            </div>
            <div className="h-3 w-full bg-edge/60 rounded-full overflow-hidden">
              {pct != null ? (
                <div className="h-full bg-blue-600 rounded-full transition-all duration-700"
                  style={{ width: `${pct}%` }} />
              ) : ativa ? (
                // Indeterminada — rows_total ainda desconhecido (COUNT em andamento)
                <div className="h-full w-full bg-blue-600/50 rounded-full animate-pulse" />
              ) : null}
            </div>
            <div className="flex items-center justify-between text-xs">
              <span className="text-ink font-medium">
                {fmtRows(data.rows_copied)}
                <span className="text-dim font-normal">
                  {data.rows_total != null ? ` de ${fmtRows(data.rows_total)}` : ''} linhas
                </span>
              </span>
              {ativa && data.eta_s != null && (
                <span className="text-dim">ETA <span className="font-mono text-ink">{fmtEta(data.eta_s)}</span></span>
              )}
            </div>
          </div>

          {/* Métricas */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            <div className="bg-canvas border border-edge rounded-lg px-3 py-2">
              <p className="text-[10px] text-dim uppercase tracking-wider">Velocidade</p>
              <p className="text-sm text-ink font-medium">
                {data.rate_rows_s != null ? `${fmtRows(Math.round(data.rate_rows_s))} linhas/s` : '—'}
              </p>
            </div>
            <div className="bg-canvas border border-edge rounded-lg px-3 py-2">
              <p className="text-[10px] text-dim uppercase tracking-wider">Duração</p>
              <p className="text-sm text-ink font-medium">{fmtDuracao(dur)}</p>
            </div>
            <div className="bg-canvas border border-edge rounded-lg px-3 py-2">
              <p className="text-[10px] text-dim uppercase tracking-wider">Streams</p>
              <p className="text-sm text-ink font-medium">{data.streams ?? '—'}</p>
            </div>
            <div className="bg-canvas border border-edge rounded-lg px-3 py-2">
              <p className="text-[10px] text-dim uppercase tracking-wider">Engine</p>
              <p className="text-sm text-ink font-medium" title={data.engine ?? undefined}>
                {engineLabel(data.engine)}
              </p>
            </div>
          </div>

          {/* Hint do engine server-side sem partição: a instrução única roda
              dentro do servidor e o rowcount só sai quando ela termina. */}
          {serverSideFaixaUnica && ativa && (
            <p className="text-[11px] text-dim">
              execução dentro do servidor — o total copiado aparece ao final da faixa
            </p>
          )}

          {/* Erro */}
          {data.erro_msg && (
            <div className="flex items-start gap-2 p-3 rounded-lg bg-red-50 border border-red-200 dark:bg-red-900/20 dark:border-red-800">
              <AlertTriangle size={16} className="text-red-500 shrink-0 mt-0.5" />
              <p className="text-xs text-red-700 dark:text-red-300 break-words">{data.erro_msg}</p>
            </div>
          )}

          {/* Faixas (streams) */}
          {data.ranges.length > 0 && (
            <div className="border border-edge rounded-lg overflow-hidden">
              <div className="px-3 py-1.5 border-b border-edge bg-canvas/50">
                <span className="text-[11px] text-dim font-semibold uppercase tracking-wider">
                  Faixas ({data.ranges.length})
                </span>
              </div>
              <div className="max-h-52 overflow-y-auto">
                <table className="w-full text-sm">
                  <thead className="sticky top-0 bg-canvas">
                    <tr className="text-xs text-dim border-b border-edge">
                      <th className="px-3 py-1.5 text-left font-semibold">Stream</th>
                      <th className="px-3 py-1.5 text-left font-semibold">Intervalo</th>
                      <th className="px-3 py-1.5 text-left font-semibold">Status</th>
                      <th className="px-3 py-1.5 text-right font-semibold">Linhas</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.ranges.map(r => (
                      <tr key={r.range_index} className="border-b border-edge/50">
                        <td className="px-3 py-1.5 text-xs text-ink font-mono">
                          {r.range_index === -1 ? 'NULOS' : `#${r.range_index + 1}`}
                        </td>
                        <td className="px-3 py-1.5 text-xs text-dim font-mono" title={faixaIntervalo(r)}>
                          {faixaIntervalo(r)}
                        </td>
                        <td className="px-3 py-1.5"><StatusBadge status={r.status} /></td>
                        <td className="px-3 py-1.5 text-right text-xs text-ink whitespace-nowrap">
                          {fmtRows(r.rows_copied)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Rodapé: metadados + ações */}
          <div className="flex items-center justify-between pt-1 border-t border-edge">
            <div className="text-[11px] text-dim flex flex-col gap-0.5">
              {data.iniciado_em && <span>Início: {data.iniciado_em}</span>}
              {data.concluido_em && <span>Fim: {data.concluido_em}</span>}
              {data.dag_run_id && <span className="font-mono">run: {data.dag_run_id}</span>}
            </div>
            <div className="flex gap-2">
              {ativa && podeExecutar && (
                <Button variant="danger" size="sm"
                  loading={cancelMut.isPending}
                  disabled={data.status === 'cancelando'}
                  onClick={() => setConfirmCancel(true)}>
                  <XCircle size={13} />
                  {data.status === 'cancelando' ? 'Cancelando…' : 'Cancelar'}
                </Button>
              )}
              <Button variant="secondary" size="sm" onClick={onClose}>Fechar</Button>
            </div>
          </div>
        </div>
      )}
    </Modal>

    {/* Confirmação do cancelamento */}
    {confirmCancel && (
      <Modal open onClose={() => setConfirmCancel(false)} title="Cancelar execução" size="sm">
        <div className="flex flex-col gap-5">
          <div className="flex items-start gap-2 p-3 rounded-lg bg-red-50 border border-red-200 dark:bg-red-900/20 dark:border-red-800">
            <AlertTriangle size={16} className="text-red-500 shrink-0 mt-0.5" />
            <p className="text-sm text-red-700 dark:text-red-300">
              Cancelar a execução em andamento? As linhas já copiadas para o
              destino <strong>não são desfeitas</strong>.
            </p>
          </div>
          <div className="flex justify-end gap-2">
            <Button variant="secondary" size="sm" onClick={() => setConfirmCancel(false)}>Voltar</Button>
            <Button variant="danger" size="sm"
              onClick={() => { setConfirmCancel(false); cancelMut.mutate() }}>
              Cancelar execução
            </Button>
          </div>
        </div>
      </Modal>
    )}
    </>
  )
}
