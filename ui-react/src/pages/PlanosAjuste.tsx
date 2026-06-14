import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '../lib/api'
import { queryClient } from '../lib/queryClient'
import { Card } from '../components/ui/Card'
import { Button } from '../components/ui/Button'
import { Spinner } from '../components/ui/Spinner'
import { toast } from '../components/ui/Toast'
import { ClipboardList, ArrowLeft, CheckCircle2, Trash2, Lock, Unlock } from 'lucide-react'

interface PlanoLite {
  id: number; nome: string; descricao: string | null; status: string
  created_by: string | null; created_at: string | null
  finalized_at: string | null; finalized_by: string | null
  total_itens: number; concluidos: number
}
interface Item {
  id: number; job_name: string; stage_name: string | null; stage_type: string | null
  direction: string | null; object_name: string | null; column_name: string
  datatype_atual: string | null; datatype_alvo: string | null
  status: string; observacao: string | null
  started_at: string | null; done_at: string | null; done_by: string | null
}
interface PlanoDetail {
  plano: PlanoLite & { updated_at?: string | null }
  itens: Item[]
}

const STATUS_LABEL: Record<string, string> = { pendente: 'Pendente', em_andamento: 'Em andamento', concluido: 'Concluído' }
const STATUS_CLS: Record<string, string> = {
  pendente:     'bg-slate-100 text-slate-600 border-slate-300 dark:bg-gray-800 dark:text-gray-400 dark:border-gray-700',
  em_andamento: 'bg-blue-100 text-blue-700 border-blue-300 dark:bg-blue-900/40 dark:text-blue-300 dark:border-blue-800',
  concluido:    'bg-green-100 text-green-700 border-green-300 dark:bg-green-900/40 dark:text-green-300 dark:border-green-800',
}

function Progress({ done, total }: { done: number; total: number }) {
  const pct = total ? Math.round((done / total) * 100) : 0
  return (
    <div className="flex items-center gap-2 w-52">
      <div className="flex-1 h-2 rounded bg-edge overflow-hidden">
        <div className="h-full bg-green-500 transition-all" style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-dim whitespace-nowrap">{done}/{total}</span>
      <span className={`text-xs font-semibold whitespace-nowrap ${pct === 100 && total > 0 ? 'text-green-500' : 'text-ink'}`}>{pct}%</span>
    </div>
  )
}

export default function PlanosAjuste() {
  const [openId, setOpenId] = useState<number | null>(null)
  return openId == null
    ? <PlanList onOpen={setOpenId} />
    : <PlanDetail planId={openId} onBack={() => setOpenId(null)} />
}

// ── Lista de planos ───────────────────────────────────────────────
function PlanList({ onOpen }: { onOpen: (id: number) => void }) {
  const { data, isLoading } = useQuery<{ planos: PlanoLite[] }>({
    queryKey: ['change-plans'], queryFn: () => apiFetch('/change-plans'),
  })

  const removePlan = async (id: number) => {
    if (!confirm('Remover este plano e todos os seus itens?')) return
    try {
      await apiFetch(`/change-plans/${id}`, { method: 'DELETE' })
      toast.success('Plano removido')
      queryClient.invalidateQueries({ queryKey: ['change-plans'] })
    } catch (e: any) { toast.error(e.message) }
  }

  const planos = data?.planos ?? []

  return (
    <div className="flex flex-col gap-5">
      <div>
        <h1 className="text-lg font-semibold text-ink flex items-center gap-2">
          <ClipboardList size={20} className="text-[#1A5FA8]" /> Planos de Ajuste
        </h1>
        <p className="text-sm text-dim mt-1">
          Acompanhe as alterações de campo planejadas. Crie um plano na tela <strong>Impacto Campo</strong> selecionando colunas.
        </p>
      </div>

      {isLoading ? <div className="flex justify-center h-40 items-center"><Spinner size={36} /></div> : (
        planos.length === 0 ? (
          <Card><p className="text-sm text-dim text-center py-8">Nenhum plano ainda. Vá em <strong>Impacto Campo</strong>, selecione colunas e clique em “Adicionar ao plano”.</p></Card>
        ) : (
          <div className="flex flex-col gap-2">
            {planos.map((p) => (
              <Card key={p.id} className="hover:border-[#1A5FA8]/50 transition-colors">
                <div className="flex items-center gap-3">
                  <button className="flex-1 text-left" onClick={() => onOpen(p.id)}>
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-ink">{p.nome}</span>
                      <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs border ${p.status === 'finalizado' ? STATUS_CLS.concluido : STATUS_CLS.em_andamento}`}>
                        {p.status === 'finalizado' ? 'Finalizado' : 'Aberto'}
                      </span>
                    </div>
                    <span className="text-xs text-dim">
                      {p.created_by ?? '—'} · {p.created_at ?? ''}
                      {p.descricao ? ` · ${p.descricao}` : ''}
                    </span>
                  </button>
                  <Progress done={p.concluidos} total={p.total_itens} />
                  <Button variant="ghost" size="sm" onClick={() => removePlan(p.id)} title="Remover plano">
                    <Trash2 size={14} />
                  </Button>
                </div>
              </Card>
            ))}
          </div>
        )
      )}
    </div>
  )
}

// ── Detalhe do plano ──────────────────────────────────────────────
function PlanDetail({ planId, onBack }: { planId: number; onBack: () => void }) {
  const { data, isLoading } = useQuery<PlanoDetail>({
    queryKey: ['change-plan', planId], queryFn: () => apiFetch(`/change-plans/${planId}`),
  })

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ['change-plan', planId] })
    queryClient.invalidateQueries({ queryKey: ['change-plans'] })
  }

  const patchItem = async (itemId: number, body: Record<string, unknown>) => {
    try {
      await apiFetch(`/change-plans/${planId}/items/${itemId}`, { method: 'PATCH', body: JSON.stringify(body) })
      refresh()
    } catch (e: any) { toast.error(e.message) }
  }

  const removeItem = async (itemId: number) => {
    try { await apiFetch(`/change-plans/${planId}/items/${itemId}`, { method: 'DELETE' }); refresh() }
    catch (e: any) { toast.error(e.message) }
  }

  const finalize = async (reabrir: boolean) => {
    try {
      await apiFetch(`/change-plans/${planId}/finalize`, { method: 'POST', body: JSON.stringify({ reabrir }) })
      toast.success(reabrir ? 'Plano reaberto' : 'Plano finalizado')
      refresh()
    } catch (e: any) { toast.error(e.message) }
  }

  if (isLoading || !data) return <div className="flex justify-center h-40 items-center"><Spinner size={36} /></div>

  const { plano, itens } = data
  const done = itens.filter((i) => i.status === 'concluido').length
  const finalizado = plano.status === 'finalizado'

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-center gap-3 flex-wrap">
        <Button variant="ghost" size="sm" onClick={onBack}><ArrowLeft size={14} /> Voltar</Button>
        <h1 className="text-lg font-semibold text-ink">{plano.nome}</h1>
        <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs border ${finalizado ? STATUS_CLS.concluido : STATUS_CLS.em_andamento}`}>
          {finalizado ? 'Finalizado' : 'Aberto'}
        </span>
        <Progress done={done} total={itens.length} />
        <div className="ml-auto">
          {finalizado ? (
            <Button variant="secondary" size="sm" onClick={() => finalize(true)}><Unlock size={14} /> Reabrir</Button>
          ) : (
            <Button size="sm" onClick={() => finalize(false)}><Lock size={14} /> Finalizar plano</Button>
          )}
        </div>
      </div>

      <Card className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-dim border-b border-edge">
              <th className="py-2 pr-3 font-medium">Job / Stage</th>
              <th className="py-2 pr-3 font-medium">Coluna</th>
              <th className="py-2 pr-3 font-medium">Atual → Alvo</th>
              <th className="py-2 pr-3 font-medium">Status</th>
              <th className="py-2 pr-3 font-medium">Concluído em</th>
              <th className="py-2 pr-3 font-medium">Obs.</th>
              <th className="py-2 font-medium"></th>
            </tr>
          </thead>
          <tbody>
            {itens.map((it) => (
              <tr key={it.id} className="border-b border-edge/50 last:border-0 align-top">
                <td className="py-2 pr-3">
                  <span className="text-ink">{it.job_name}</span>
                  <span className="block text-[11px] text-dim">{it.stage_name} · {it.stage_type}</span>
                </td>
                <td className="py-2 pr-3 font-mono text-ink">{it.column_name}</td>
                <td className="py-2 pr-3">
                  <span className="text-dim">{it.datatype_atual ?? '?'}</span>
                  <span className="mx-1">→</span>
                  <input
                    className="w-24 bg-panel border border-edge rounded px-1.5 py-0.5 text-xs text-ink disabled:opacity-60"
                    defaultValue={it.datatype_alvo ?? ''} placeholder="alvo" disabled={finalizado}
                    onBlur={(e) => { if (e.target.value !== (it.datatype_alvo ?? '')) patchItem(it.id, { datatype_alvo: e.target.value }) }}
                  />
                </td>
                <td className="py-2 pr-3">
                  <select
                    className={`rounded px-1.5 py-0.5 text-xs border ${STATUS_CLS[it.status]} disabled:opacity-60`}
                    value={it.status} disabled={finalizado}
                    onChange={(e) => patchItem(it.id, { status: e.target.value })}
                  >
                    {Object.entries(STATUS_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                  </select>
                </td>
                <td className="py-2 pr-3 text-xs text-dim">
                  {it.done_at ? <>{it.done_at}<span className="block">{it.done_by}</span></> : '—'}
                </td>
                <td className="py-2 pr-3">
                  <input
                    className="w-40 bg-panel border border-edge rounded px-1.5 py-0.5 text-xs text-ink disabled:opacity-60"
                    defaultValue={it.observacao ?? ''} placeholder="observação" disabled={finalizado}
                    onBlur={(e) => { if (e.target.value !== (it.observacao ?? '')) patchItem(it.id, { observacao: e.target.value }) }}
                  />
                </td>
                <td className="py-2 whitespace-nowrap">
                  {!finalizado && it.status !== 'concluido' && (
                    <Button variant="ghost" size="sm" title="Concluir" onClick={() => patchItem(it.id, { status: 'concluido' })}>
                      <CheckCircle2 size={14} className="text-green-500" />
                    </Button>
                  )}
                  {!finalizado && (
                    <Button variant="ghost" size="sm" title="Remover item" onClick={() => removeItem(it.id)}>
                      <Trash2 size={14} className="text-dim" />
                    </Button>
                  )}
                </td>
              </tr>
            ))}
            {itens.length === 0 && (
              <tr><td colSpan={7} className="py-6 text-center text-dim text-sm">Plano sem itens.</td></tr>
            )}
          </tbody>
        </table>
      </Card>
    </div>
  )
}
