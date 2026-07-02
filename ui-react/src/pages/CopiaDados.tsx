// Cópia de Dados — copia tabelas entre servidores SQL Server usando as
// Airflow Connections (mssql) como fonte de credenciais. Tela principal:
// lista de cópias salvas + wizard de cadastro (5 passos), modal de progresso
// (polling) e histórico de execuções.
import { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { apiFetch } from '../lib/api'
import { queryClient } from '../lib/queryClient'
import { useAuthStore } from '../store/auth'
import { Button } from '../components/ui/Button'
import { Badge } from '../components/ui/Badge'
import { Modal } from '../components/ui/Modal'
import { PageSpinner } from '../components/ui/Spinner'
import { InfoBanner } from '../components/ui/InfoBanner'
import { toast } from '../components/ui/Toast'
import {
  AlertTriangle, Copy, Edit2, History, Play, Plus, Trash2,
} from 'lucide-react'
import { CopiaWizard } from '../components/copias/CopiaWizard'
import { CopiaProgressoModal } from '../components/copias/CopiaProgressoModal'
import { CopiaHistoricoModal } from '../components/copias/CopiaHistoricoModal'
import {
  type CopiaDetalhe, type CopiaJob,
  EXEC_ATIVA, STATUS_BADGE, STATUS_LABELS, fmtRows,
} from '../components/copias/transformUtils'

// ── Confirm Modal (mesmo padrão local de Admin.tsx) ──────────────────────────
interface ConfirmProps {
  open: boolean
  title: string
  message: string
  danger?: boolean
  confirmLabel?: string
  onConfirm: () => void
  onCancel: () => void
}
function ConfirmModal({ open, title, message, danger, confirmLabel = 'Confirmar', onConfirm, onCancel }: ConfirmProps) {
  if (!open) return null
  return (
    <Modal open onClose={onCancel} title={title} size="sm">
      <div className="flex flex-col gap-5">
        {danger ? (
          <div className="flex items-start gap-2 p-3 rounded-lg bg-red-50 border border-red-200 dark:bg-red-900/20 dark:border-red-800">
            <AlertTriangle size={16} className="text-red-500 shrink-0 mt-0.5" />
            <p className="text-sm text-red-700 dark:text-red-300">{message}</p>
          </div>
        ) : <p className="text-sm text-ink">{message}</p>}
        <div className="flex justify-end gap-2">
          <Button variant="secondary" size="sm" onClick={onCancel}>Cancelar</Button>
          <Button variant={danger ? 'danger' : 'primary'} size="sm" onClick={() => { onConfirm(); onCancel() }}>
            {confirmLabel}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

// ── Página ────────────────────────────────────────────────────────────────────

export default function CopiaDados() {
  const user = useAuthStore(s => s.user)
  const isAdmin = useAuthStore(s => s.isAdmin)
  const podeEditar = isAdmin() || !!user?.permissoes?.includes('acao_editar')
  const podeExecutar = isAdmin() || !!user?.permissoes?.includes('acao_executar')

  const [wizardNovo, setWizardNovo] = useState(false)
  const [editarId, setEditarId] = useState<number | null>(null)
  const [histCopia, setHistCopia] = useState<CopiaJob | null>(null)
  const [execAberta, setExecAberta] = useState<number | null>(null)
  const [executarCopia, setExecutarCopia] = useState<CopiaJob | null>(null)
  const [excluirCopia, setExcluirCopia] = useState<CopiaJob | null>(null)

  const { data, isLoading } = useQuery<{ data: CopiaJob[] }>({
    queryKey: ['copias'],
    queryFn: () => apiFetch('/copias'),
    // Mantém os badges frescos enquanto alguma cópia está executando.
    refetchInterval: q =>
      (q.state.data?.data ?? []).some(c => c.ultima_exec && EXEC_ATIVA.has(c.ultima_exec.status))
        ? 5000 : false,
  })
  const copias = data?.data ?? []

  // Detalhe da cópia em edição — o wizard só abre com os dados carregados.
  const { data: detalhe, isLoading: detalheLoading } = useQuery<CopiaDetalhe>({
    queryKey: ['copia-detalhe', editarId],
    queryFn: () => apiFetch(`/copias/${editarId}`),
    enabled: editarId != null,
    staleTime: 0,
  })

  const execMut = useMutation({
    mutationFn: (id: number) =>
      apiFetch<{ exec_id: number }>(`/copias/${id}/executar`, { method: 'POST' }),
    onSuccess: d => {
      queryClient.invalidateQueries({ queryKey: ['copias'] })
      setExecAberta(d.exec_id)
    },
    onError: (e: any) => toast.error(e?.message || 'Falha ao executar a cópia'),
  })

  const delMut = useMutation({
    mutationFn: (id: number) => apiFetch(`/copias/${id}`, { method: 'DELETE' }),
    onSuccess: () => {
      toast.success('Cópia excluída')
      queryClient.invalidateQueries({ queryKey: ['copias'] })
    },
    onError: (e: any) => toast.error(e?.message || 'Falha ao excluir'),
  })

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold text-ink flex items-center gap-2">
            <Copy size={20} className="text-[#1A5FA8]" /> Cópia de Dados
          </h1>
          <p className="text-sm text-dim mt-1">
            Copie tabelas entre servidores SQL Server com transformações por coluna,
            usando as conexões do Airflow.
          </p>
        </div>
        {podeEditar && (
          <Button onClick={() => setWizardNovo(true)}>
            <Plus size={14} /> Nova cópia
          </Button>
        )}
      </div>

      <InfoBanner storageKey="copia_dados">
        Cada cópia lê a tabela de origem em streaming e grava em bloco no destino,
        com paralelismo por faixas da coluna de partição. As credenciais ficam nas
        connections do Airflow — a plataforma nunca vê senhas. Acompanhe o progresso
        em tempo real e cancele quando precisar.
      </InfoBanner>

      {isLoading ? <PageSpinner /> : (
        <div className="bg-panel border border-edge rounded-lg overflow-hidden shadow-sm">
          <div className="px-4 py-2 border-b border-edge">
            <span className="text-xs text-dim">{copias.length} cópia{copias.length !== 1 ? 's' : ''}</span>
          </div>

          {copias.length === 0 ? (
            <p className="text-dim text-sm text-center py-12">
              Nenhuma cópia cadastrada — clique em “Nova cópia” para começar.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-xs text-dim border-b border-edge bg-canvas/50">
                    <th className="px-4 py-2.5 text-left font-semibold">Nome</th>
                    <th className="px-4 py-2.5 text-left font-semibold">Origem</th>
                    <th className="px-4 py-2.5 text-left font-semibold">Destino</th>
                    <th className="px-4 py-2.5 text-left font-semibold">Última execução</th>
                    <th className="px-4 py-2.5 w-32"></th>
                  </tr>
                </thead>
                <tbody>
                  {copias.map(c => {
                    const ex = c.ultima_exec
                    const execAtiva = !!ex && EXEC_ATIVA.has(ex.status)
                    return (
                      <tr key={c.id} className="border-b border-edge/50 hover:bg-canvas/50 transition-colors">
                        <td className="px-4 py-2.5">
                          <span className="text-xs font-medium text-ink">{c.nome}</span>
                        </td>
                        <td className="px-4 py-2.5">
                          <span className="block text-[11px] text-dim">{c.src_conn_id} · {c.src_database}</span>
                          <span className="font-mono text-xs text-ink">{c.src_schema}.{c.src_table}</span>
                        </td>
                        <td className="px-4 py-2.5">
                          <span className="block text-[11px] text-dim">{c.dst_conn_id} · {c.dst_database}</span>
                          <span className="font-mono text-xs text-ink">{c.dst_schema}.{c.dst_table}</span>
                        </td>
                        <td className="px-4 py-2.5">
                          {ex ? (
                            <button type="button" onClick={() => setExecAberta(ex.id)}
                              className="flex items-center gap-2 group" title="Ver progresso/detalhe">
                              <Badge value={STATUS_BADGE[ex.status] ?? 'neutral'}>
                                {STATUS_LABELS[ex.status] ?? ex.status}
                              </Badge>
                              <span className="text-[11px] text-dim group-hover:text-ink transition-colors whitespace-nowrap">
                                {fmtRows(ex.rows_copied)}
                                {ex.rows_total != null ? ` / ${fmtRows(ex.rows_total)}` : ''} linhas
                              </span>
                            </button>
                          ) : (
                            <span className="text-xs text-dim">nunca executada</span>
                          )}
                        </td>
                        <td className="px-4 py-2.5">
                          <div className="flex items-center gap-1 justify-end">
                            {podeExecutar && (
                              <button
                                onClick={() => execAtiva ? setExecAberta(ex!.id) : setExecutarCopia(c)}
                                disabled={execMut.isPending}
                                className="text-slate-400 hover:text-green-600 dark:hover:text-green-400 p-1 rounded disabled:opacity-50"
                                title={execAtiva ? 'Execução em andamento — ver progresso' : 'Executar'}>
                                <Play size={13} />
                              </button>
                            )}
                            {podeEditar && (
                              <button onClick={() => setEditarId(c.id)}
                                className="text-slate-400 hover:text-[#1A5FA8] dark:hover:text-blue-400 p-1 rounded"
                                title="Editar">
                                <Edit2 size={13} />
                              </button>
                            )}
                            <button onClick={() => setHistCopia(c)}
                              className="text-slate-400 hover:text-[#1A5FA8] dark:hover:text-blue-400 p-1 rounded"
                              title="Histórico de execuções">
                              <History size={13} />
                            </button>
                            {podeEditar && (
                              <button onClick={() => setExcluirCopia(c)}
                                className="text-slate-400 hover:text-red-500 dark:hover:text-red-400 p-1 rounded"
                                title="Excluir">
                                <Trash2 size={13} />
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Wizard — nova cópia */}
      {wizardNovo && (
        <CopiaWizard
          onClose={() => setWizardNovo(false)}
          onExecutado={execId => setExecAberta(execId)} />
      )}

      {/* Wizard — edição (abre quando o detalhe termina de carregar) */}
      {editarId != null && detalheLoading && (
        <Modal open onClose={() => setEditarId(null)} title="Carregando cópia…" size="sm">
          <PageSpinner />
        </Modal>
      )}
      {editarId != null && detalhe && detalhe.id === editarId && (
        <CopiaWizard copia={detalhe}
          onClose={() => setEditarId(null)}
          onExecutado={execId => setExecAberta(execId)} />
      )}

      {/* Progresso / detalhe da execução */}
      {execAberta != null && (
        <CopiaProgressoModal execId={execAberta} onClose={() => setExecAberta(null)} />
      )}

      {/* Histórico */}
      {histCopia && (
        <CopiaHistoricoModal copia={histCopia}
          onClose={() => setHistCopia(null)}
          onVerExec={execId => setExecAberta(execId)} />
      )}

      {/* Confirmação de execução (alerta de truncate quando configurado) */}
      <ConfirmModal
        open={!!executarCopia}
        title="Executar cópia"
        danger={!!executarCopia?.truncar_antes}
        confirmLabel="Executar"
        message={executarCopia?.truncar_antes
          ? `Executar "${executarCopia?.nome}"? O destino ${executarCopia?.dst_schema}.${executarCopia?.dst_table} será TRUNCADO antes da cópia.`
          : `Executar a cópia "${executarCopia?.nome}" agora?`}
        onConfirm={() => executarCopia && execMut.mutate(executarCopia.id)}
        onCancel={() => setExecutarCopia(null)} />

      {/* Confirmação de exclusão */}
      <ConfirmModal
        open={!!excluirCopia}
        title="Excluir cópia"
        danger
        confirmLabel="Excluir"
        message={`Excluir a cópia "${excluirCopia?.nome}"? O histórico de execuções é preservado.`}
        onConfirm={() => excluirCopia && delMut.mutate(excluirCopia.id)}
        onCancel={() => setExcluirCopia(null)} />
    </div>
  )
}
