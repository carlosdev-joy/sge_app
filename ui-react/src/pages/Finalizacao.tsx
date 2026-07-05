// Finalizar Pipeline — encerramento manual de execuções penduradas em RUNNING.
// Para processos que já terminaram no DataStage mas ficaram órfãos no Orquestra
// (worker morreu antes do log_end e o reconciliador não tem status terminal para
// espelhar). Fecha o log principal, a estrutura no log do DataStage e limpa os
// snapshots de performance — numa ação só. NÃO toca no DataStage nem no Airflow.
import { useEffect, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { apiFetch } from '../lib/api'
import { queryClient } from '../lib/queryClient'
import { useAuthStore } from '../store/auth'
import { Button } from '../components/ui/Button'
import { Select, Textarea } from '../components/ui/Input'
import { Modal } from '../components/ui/Modal'
import { PageSpinner } from '../components/ui/Spinner'
import { InfoBanner } from '../components/ui/InfoBanner'
import { toast } from '../components/ui/Toast'
import { OctagonX, Search } from 'lucide-react'

interface ExecucaoPendurada {
  execution_id: string
  pipeline: string
  project: string | null
  jobs_running: number
  inicio: string | null
  elapsed_seconds: number
  estruturas_abertas: number
  snapshots: number
}

interface ResultadoFinalizacao {
  ok: boolean
  pipeline: string
  status_final: string
  execucoes_finalizadas: string[]
  jobs_fechados: number
  estruturas_fechadas: number
  snapshots_removidos: number
}

const STATUS_FINAL_LABEL: Record<string, string> = {
  SUCCESS: 'Sucesso — terminou OK no DataStage',
  WARNING: 'Alerta — terminou com warnings',
  FAILED: 'Falha — abortou / desfecho desconhecido',
}

function fmtElapsed(s: number): string {
  if (!s || s < 0) return '—'
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  if (h >= 48) return `${Math.floor(h / 24)}d ${h % 24}h`
  if (h > 0) return `${h}h ${m}min`
  return `${m}min`
}

export default function Finalizacao() {
  const user = useAuthStore(s => s.user)
  const isAdmin = useAuthStore(s => s.isAdmin)
  const podeExecutar = isAdmin() || !!user?.permissoes?.includes('acao_executar')

  const [busca, setBusca] = useState('')
  const [q, setQ] = useState('')            // busca com debounce (vira ?q=)
  const [alvo, setAlvo] = useState<ExecucaoPendurada | null>(null)

  useEffect(() => {
    const t = setTimeout(() => setQ(busca.trim()), 300)
    return () => clearTimeout(t)
  }, [busca])

  const { data, isLoading } = useQuery<{ data: ExecucaoPendurada[] }>({
    queryKey: ['finalizacao', q],
    queryFn: () => apiFetch(`/finalizacao/executando?q=${encodeURIComponent(q)}`),
    refetchInterval: 30_000,
  })
  const execucoes = data?.data ?? []

  return (
    <div className="flex flex-col gap-5">
      <div>
        <h1 className="text-lg font-semibold text-ink flex items-center gap-2">
          <OctagonX size={20} className="text-[#1A5FA8]" /> Finalizar Pipeline
        </h1>
        <p className="text-sm text-dim mt-1">
          Encerra manualmente execuções penduradas em EXECUTANDO nos logs do Orquestra —
          o pipeline sai do Executando, da Performance e dos indicadores de uma vez.
        </p>
      </div>

      <InfoBanner storageKey="finalizacao_pipeline">
        Use quando o processo <strong>já terminou no DataStage</strong> mas continua como
        EXECUTANDO aqui (o registro ficou órfão). A finalização fecha apenas os logs do
        Orquestra — não interrompe nada no DataStage nem no Airflow. Antes de finalizar,
        tente o “Reconciliar” na tela de Logs: ele fecha usando o status real do DataStage.
      </InfoBanner>

      <div className="relative">
        <Search size={14} className="absolute left-2.5 top-2.5 text-dim pointer-events-none" />
        <input
          value={busca}
          onChange={e => setBusca(e.target.value)}
          placeholder="Buscar pelo nome do pipeline…"
          className="w-80 bg-panel border border-edge text-ink rounded-md pl-8 pr-3 py-1.5 text-sm placeholder-dim focus:outline-none focus:ring-1 focus:ring-blue-500"
        />
      </div>

      {isLoading ? <PageSpinner /> : (
        <div className="bg-panel border border-edge rounded-lg overflow-hidden shadow-sm">
          <div className="px-4 py-2 border-b border-edge">
            <span className="text-xs text-dim">
              {execucoes.length} execução{execucoes.length !== 1 ? 'ões' : ''} em andamento
            </span>
          </div>

          {execucoes.length === 0 ? (
            <p className="text-dim text-sm text-center py-12">
              Nenhuma execução em EXECUTANDO{q ? ' para o filtro atual' : ''} — nada pendurado. 🎉
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-xs text-dim border-b border-edge bg-canvas/50">
                    <th className="px-4 py-2.5 text-left font-semibold">Pipeline</th>
                    <th className="px-4 py-2.5 text-left font-semibold">Execução</th>
                    <th className="px-4 py-2.5 text-left font-semibold">Projeto</th>
                    <th className="px-4 py-2.5 text-right font-semibold">Jobs rodando</th>
                    <th className="px-4 py-2.5 text-right font-semibold">Estruturas abertas</th>
                    <th className="px-4 py-2.5 text-right font-semibold">Snapshots perf.</th>
                    <th className="px-4 py-2.5 text-left font-semibold">Início</th>
                    <th className="px-4 py-2.5 text-left font-semibold">Decorrido</th>
                    <th className="px-4 py-2.5 w-24"></th>
                  </tr>
                </thead>
                <tbody>
                  {execucoes.map(e => (
                    <tr key={`${e.execution_id}|${e.pipeline}`}
                      className="border-b border-edge/50 hover:bg-canvas/50 transition-colors">
                      <td className="px-4 py-2.5 text-xs font-medium text-ink">{e.pipeline}</td>
                      <td className="px-4 py-2.5 text-xs font-mono text-dim">{e.execution_id}</td>
                      <td className="px-4 py-2.5 text-xs text-ink">{e.project ?? '—'}</td>
                      <td className="px-4 py-2.5 text-xs text-ink text-right">{e.jobs_running}</td>
                      <td className="px-4 py-2.5 text-xs text-ink text-right">{e.estruturas_abertas}</td>
                      <td className="px-4 py-2.5 text-xs text-ink text-right">{e.snapshots}</td>
                      <td className="px-4 py-2.5 text-xs text-ink whitespace-nowrap">{e.inicio ?? '—'}</td>
                      <td className="px-4 py-2.5 text-xs whitespace-nowrap">
                        <span className={e.elapsed_seconds >= 10800
                          ? 'text-red-600 dark:text-red-400 font-medium'
                          : 'text-ink'}>
                          {fmtElapsed(e.elapsed_seconds)}
                        </span>
                      </td>
                      <td className="px-4 py-2.5 text-right whitespace-nowrap">
                        {podeExecutar && (
                          <Button variant="danger" size="sm" onClick={() => setAlvo(e)}>
                            <OctagonX size={14} /> Finalizar
                          </Button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {alvo && <FinalizarModal alvo={alvo} onClose={() => setAlvo(null)} />}
    </div>
  )
}

// ── Modal de confirmação da finalização ──────────────────────────────────────
function FinalizarModal({ alvo, onClose }: {
  alvo: ExecucaoPendurada
  onClose: () => void
}) {
  const [statusFinal, setStatusFinal] = useState('SUCCESS')
  const [motivo, setMotivo] = useState('')

  const finalizarMut = useMutation({
    mutationFn: () => apiFetch<ResultadoFinalizacao>('/finalizacao/finalizar', {
      method: 'POST',
      body: JSON.stringify({
        pipeline: alvo.pipeline,
        execution_id: alvo.execution_id,
        status_final: statusFinal,
        motivo: motivo.trim() || undefined,
      }),
    }),
    onSuccess: r => {
      toast.success(
        `${r.pipeline} finalizado como ${r.status_final} — ${r.jobs_fechados} job(s), ` +
        `${r.estruturas_fechadas} estrutura(s), ${r.snapshots_removidos} snapshot(s) limpos`)
      queryClient.invalidateQueries({ queryKey: ['finalizacao'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      queryClient.invalidateQueries({ queryKey: ['execucoes'] })
      onClose()
    },
    onError: (e: any) => toast.error(e?.message || 'Falha ao finalizar'),
  })

  return (
    <Modal open onClose={onClose} size="md" title={`Finalizar — ${alvo.pipeline}`}>
      <div className="flex flex-col gap-4">
        <p className="text-sm text-ink">
          Encerrar a execução <span className="font-mono text-xs">{alvo.execution_id}</span> nos
          logs do Orquestra: fecha <strong>{alvo.jobs_running}</strong> job(s) em RUNNING,{' '}
          <strong>{alvo.estruturas_abertas}</strong> estrutura(s) no log do DataStage e remove{' '}
          <strong>{alvo.snapshots}</strong> snapshot(s) de performance.
        </p>
        <p className="text-xs text-dim">
          A ação não interrompe nada no DataStage/Airflow — só corrige o registro aqui.
          Fica auditada (quem, quando e motivo) no histórico do pipeline.
        </p>

        <Select label="Status final *" value={statusFinal}
          onChange={e => setStatusFinal(e.target.value)}>
          {Object.entries(STATUS_FINAL_LABEL).map(([k, v]) =>
            <option key={k} value={k}>{v}</option>)}
        </Select>

        <Textarea label="Motivo" rows={2} value={motivo}
          onChange={e => setMotivo(e.target.value)}
          placeholder="ex.: job terminou no DataStage às 03h; worker do Airflow reiniciou antes do log_end" />

        <div className="flex justify-end gap-2 border-t border-edge pt-4">
          <Button variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button variant="danger" loading={finalizarMut.isPending}
            onClick={() => finalizarMut.mutate()}>
            <OctagonX size={14} /> Finalizar execução
          </Button>
        </div>
      </div>
    </Modal>
  )
}
