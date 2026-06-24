import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ListChecks, AlertTriangle, ShieldX, ShieldAlert, ShieldCheck, ArrowRight, CheckCircle2 } from 'lucide-react'
import { apiFetch } from '../lib/api'
import { Spinner } from '../components/ui/Spinner'
import { Button } from '../components/ui/Button'
import { toast } from '../components/ui/Toast'
import { useAuthStore } from '../store/auth'

// Landing "Operação do dia" do shell v2 — visão focada do que precisa de ação:
// contadores de falhas (falhas-summary) + fila das NÃO assumidas (falhas?status_ack=sem_ack),
// com "Assumir" inline. A triagem completa (ações em massa, resolver, notas) continua
// na aba "Gestão de Falhas" do Logs — os botões levam pra lá (/logs?tab=gestao).
// Reusa os mesmos endpoints; nenhum backend novo.

interface FalhaSummary { period_days: number; total: number; sem_ack: number; com_ack: number; resolvidas: number }
interface FalhaRow {
  execution_id: string; project: string; pipeline: string; inicio: string
  jobs_falha: number; origem?: string; job_name?: string
}

const PERIODS = [1, 7, 30]

// KPI cards no padrão claro+escuro (par dark: em toda cor de paleta).
const CARD_HUE: Record<string, string> = {
  red:    'bg-red-50 border-red-200 dark:bg-red-900/20 dark:border-red-800',
  orange: 'bg-orange-50 border-orange-200 dark:bg-orange-900/20 dark:border-orange-800',
  amber:  'bg-amber-50 border-amber-200 dark:bg-amber-900/20 dark:border-amber-800',
  green:  'bg-green-50 border-green-200 dark:bg-green-900/20 dark:border-green-800',
}
const CARD_TEXT: Record<string, string> = {
  red:    'text-red-700 dark:text-red-400',
  orange: 'text-orange-700 dark:text-orange-400',
  amber:  'text-amber-700 dark:text-amber-400',
  green:  'text-green-700 dark:text-green-400',
}

function fmtDt(iso: string | null): string {
  if (!iso || iso.length < 16) return ''
  return `${iso.substring(8, 10)}/${iso.substring(5, 7)} ${iso.substring(11, 16)}`
}

export default function OperacaoDia() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const user = useAuthStore((s) => s.user)
  const [days, setDays] = useState(7)

  const { data: summary, isLoading: sumLoading } = useQuery<FalhaSummary>({
    queryKey: ['falhas-summary', days],
    queryFn: () => apiFetch(`/execucoes/falhas-summary?days=${days}`),
    refetchInterval: 60_000,
  })
  const { data: lista, isLoading: listLoading } = useQuery<{ total: number; data: FalhaRow[] }>({
    queryKey: ['falhas', days, 'sem_ack', 'operacao'],
    queryFn: () => apiFetch(`/execucoes/falhas?days=${days}&status_ack=sem_ack&offset=0&limit=10`),
    refetchInterval: 60_000,
  })

  const falhaLabel = (r: FalhaRow) => (r.origem === 'malha' ? (r.job_name || r.pipeline) : r.pipeline)

  // Mesmo corpo do ack da aba Gestão de Falhas (idempotente no backend).
  const ackMut = useMutation({
    mutationFn: (r: FalhaRow) => apiFetch<{ ok: boolean; ack_by?: string; display_name?: string }>('/execucoes/ack', {
      method: 'POST',
      body: JSON.stringify({
        execution_id: r.execution_id,
        pipeline: r.pipeline,
        label: falhaLabel(r),
        user: user?.matricula,
        display_name: `${user?.primeiro_nome ?? ''} ${user?.ultimo_nome ?? ''}`.trim(),
      }),
    }),
    onSuccess: (data) => {
      if (data.ack_by && data.ack_by !== user?.matricula) {
        toast.error(`Falha já assumida por ${data.display_name ?? data.ack_by}`)
      } else {
        toast.success('Falha assumida')
      }
      qc.invalidateQueries({ queryKey: ['falhas'] })
      qc.invalidateQueries({ queryKey: ['falhas-summary'] })
    },
    onError: (e: any) => toast.error(e.message),
  })

  const cards = [
    { hue: 'red',    label: 'Total de falhas', value: summary?.total ?? 0,      icon: AlertTriangle },
    { hue: 'orange', label: 'Não assumidas',   value: summary?.sem_ack ?? 0,    icon: ShieldX },
    { hue: 'amber',  label: 'Em investigação', value: summary?.com_ack ?? 0,    icon: ShieldAlert },
    { hue: 'green',  label: 'Resolvidas',      value: summary?.resolvidas ?? 0, icon: ShieldCheck },
  ]
  const rows = lista?.data ?? []
  const periodLabel = days === 1 ? '24h' : `${days} dias`

  return (
    <div className="flex flex-col gap-5">
      {/* Cabeçalho + seletor de período */}
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-lg font-semibold text-ink flex items-center gap-2">
            <ListChecks size={20} className="text-[#1A5FA8]" /> Operação do dia
          </h1>
          <p className="text-sm text-dim mt-1">Falhas que precisam de atenção. Assuma aqui ou abra a triagem completa.</p>
        </div>
        <div className="flex items-center gap-0.5 bg-panel border border-edge rounded-lg p-0.5">
          {PERIODS.map((d) => (
            <button
              key={d}
              onClick={() => setDays(d)}
              className={`px-2.5 py-1 text-xs rounded-md transition-colors ${
                days === d ? 'bg-blue-50 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300' : 'text-dim hover:text-ink'
              }`}
            >
              {d === 1 ? '24h' : `${d}d`}
            </button>
          ))}
        </div>
      </div>

      {/* KPI cards */}
      {sumLoading ? (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          {[0, 1, 2, 3].map((i) => <div key={i} className="bg-panel border border-edge rounded-xl h-24 animate-pulse" />)}
        </div>
      ) : (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          {cards.map((c) => {
            const Icon = c.icon
            return (
              <button
                key={c.label}
                onClick={() => navigate('/logs?tab=gestao')}
                className={`border rounded-xl p-4 text-left hover:opacity-90 transition-opacity focus:outline-none focus:ring-2 focus:ring-blue-500/40 ${CARD_HUE[c.hue]}`}
              >
                <div className="flex items-start justify-between mb-2">
                  <span className="text-xs text-dim font-medium">{c.label}</span>
                  <Icon size={16} className={CARD_TEXT[c.hue]} />
                </div>
                <div className={`text-3xl font-bold ${CARD_TEXT[c.hue]}`}>{c.value}</div>
                <div className="text-xs text-dim/70 mt-1">últimos {periodLabel}</div>
              </button>
            )
          })}
        </div>
      )}

      {/* Fila das não assumidas */}
      <div className="bg-panel border border-edge rounded-lg overflow-hidden">
        <div className="flex items-center justify-between px-4 py-3 border-b border-edge">
          <h2 className="text-sm font-semibold text-ink flex items-center gap-2">
            <ShieldX size={15} className="text-orange-700 dark:text-orange-400" /> Não assumidas
            {rows.length > 0 && <span className="text-xs text-dim font-normal">({lista?.total ?? rows.length})</span>}
          </h2>
          <button
            onClick={() => navigate('/logs?tab=gestao')}
            className="inline-flex items-center gap-1 text-xs text-blue-700 dark:text-blue-400 hover:underline"
          >
            Triagem completa <ArrowRight size={13} />
          </button>
        </div>

        {listLoading ? (
          <div className="flex justify-center h-32 items-center"><Spinner size={32} /></div>
        ) : rows.length === 0 ? (
          <div className="flex flex-col items-center gap-2 py-10 text-center">
            <CheckCircle2 size={28} className="text-green-700 dark:text-green-400" />
            <p className="text-sm text-dim">Nenhuma falha não assumida no período. 🎉</p>
          </div>
        ) : (
          <ul className="divide-y divide-edge/60">
            {rows.map((r) => {
              const acking = ackMut.isPending && ackMut.variables?.execution_id === r.execution_id && ackMut.variables?.pipeline === r.pipeline
              return (
                <li key={`${r.execution_id}|${r.pipeline}`} className="flex items-center gap-3 px-4 py-2.5">
                  <div className="min-w-0 flex-1">
                    <div className="text-sm font-medium text-ink truncate flex items-center gap-2">
                      <span className="truncate">{falhaLabel(r)}</span>
                      {r.origem === 'malha' && (
                        <span className="shrink-0 text-[10px] px-1.5 py-0.5 rounded border bg-purple-100 text-purple-700 border-purple-300 dark:bg-purple-900/30 dark:text-purple-300 dark:border-purple-800">malha</span>
                      )}
                    </div>
                    <div className="text-xs text-dim truncate">
                      {r.project} · {fmtDt(r.inicio)}{r.jobs_falha ? ` · ${r.jobs_falha} job(s) com falha` : ''}
                    </div>
                  </div>
                  <Button size="sm" variant="secondary" loading={acking} onClick={() => ackMut.mutate(r)}>
                    Assumir
                  </Button>
                </li>
              )
            })}
          </ul>
        )}
      </div>
    </div>
  )
}
