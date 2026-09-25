import { useState, type ReactNode } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { apiFetch } from '../../../lib/api'
import { Button } from '../../ui/Button'
import { Input, Select } from '../../ui/Input'
import { Modal } from '../../ui/Modal'
import { PageSpinner } from '../../ui/Spinner'
import { toast } from '../../ui/Toast'
import { queryClient } from '../../../lib/queryClient'
import { adminPost } from '../comum'
import { ConfirmModal } from '../ComumUI'
import { Trash2, Plus, Eye, RefreshCw, Database } from 'lucide-react'

// ── Monitoramento de tabelas (observabilidade de dados) ──────────
interface MonitorSnapshot { total_linhas: number | null; ultima_data: string | null; last_write: string | null; qtde_ultimo_dia: number | null; por_dia: { dia: string; qtde: number }[]; captured_at: string | null; erro: string | null }
interface MonitorItem {
  id: number; database_name: string; schema_name: string; table_name: string; coluna_data: string
  coluna_atualizacao: string | null; criticidade: string | null; sla_horas: number | null; ativo: boolean; descricao: string | null
  snapshot: MonitorSnapshot | null
}
interface LiveResult { ok?: boolean; erro?: string; total_linhas?: number | null; ultima_data?: string | null; last_write?: string | null; qtde_ultimo_dia?: number | null; por_dia?: { dia: string; qtde: number }[] }

function freshness(ultima: string | null | undefined): { label: string; cls: string } {
  const red = 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300'
  if (!ultima) return { label: 'sem dados', cls: red }
  const d = ultima.substring(0, 10)
  const today = new Date().toLocaleDateString('en-CA')
  const yest = new Date(Date.now() - 86400000).toLocaleDateString('en-CA')
  if (d >= today) return { label: 'hoje', cls: 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300' }
  if (d === yest) return { label: 'ontem', cls: 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300' }
  return { label: `desde ${d.substring(8, 10)}/${d.substring(5, 7)}`, cls: red }
}

function Sparkbars({ data, h = 28 }: { data: { dia: string; qtde: number }[]; h?: number }) {
  if (!data?.length) return <span className="text-dim/50 text-xs">—</span>
  const max = Math.max(...data.map(d => d.qtde), 1)
  return (
    <div className="flex items-end gap-px" style={{ height: h }} title={data.map(d => `${d.dia}: ${d.qtde.toLocaleString('pt-BR')}`).join('\n')}>
      {data.slice(-40).map((d, i) => (
        <div key={i} className="w-1.5 bg-[#1A5FA8]/70 dark:bg-blue-400/70 rounded-sm" style={{ height: `${Math.max(3, (d.qtde / max) * 100)}%` }} />
      ))}
    </div>
  )
}

function Stat({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="bg-canvas border border-edge rounded-lg px-3 py-2">
      <div className="text-[10px] text-dim uppercase tracking-wide">{label}</div>
      <div className="text-sm font-semibold text-ink mt-0.5 truncate">{value}</div>
    </div>
  )
}

function AddMonitorModal({ onClose }: { onClose: () => void }) {
  const [database, setDatabase] = useState('')
  const [sel, setSel] = useState<{ schema: string; tabela: string } | null>(null)
  const [colData, setColData] = useState('')
  const [colAtu, setColAtu] = useState('')
  const [crit, setCrit] = useState('')
  const [sla, setSla] = useState('')
  const [tableQ, setTableQ] = useState('')

  const dbsQ = useQuery<{ databases: { name: string }[] }>({ queryKey: ['server_databases'], queryFn: () => adminPost('server_databases') })
  const tabelasQ = useQuery<{ data: { schema: string; tabela: string; linhas: number }[] }>({
    queryKey: ['monitor-tabelas', database], enabled: !!database,
    queryFn: () => apiFetch(`/admin/monitor/tabelas?database=${encodeURIComponent(database)}`),
  })
  const colsQ = useQuery<{ data: { nome: string; tipo: string; is_data: boolean }[] }>({
    queryKey: ['monitor-colunas', database, sel?.schema, sel?.tabela], enabled: !!sel,
    queryFn: () => apiFetch(`/admin/monitor/colunas?database=${encodeURIComponent(database)}&schema=${encodeURIComponent(sel!.schema)}&tabela=${encodeURIComponent(sel!.tabela)}`),
  })
  const save = useMutation({
    mutationFn: () => apiFetch('/admin/monitor', { method: 'POST', body: JSON.stringify({
      database_name: database, schema_name: sel!.schema, table_name: sel!.tabela,
      coluna_data: colData, coluna_atualizacao: colAtu || undefined,
      criticidade: crit || undefined, sla_horas: sla || undefined,
    }) }),
    onSuccess: () => { toast.success('Tabela adicionada ao monitoramento.'); queryClient.invalidateQueries({ queryKey: ['monitor'] }); onClose() },
    onError: (e: Error) => toast.error(e?.message || 'Falha ao adicionar'),
  })
  const tabelas = (tabelasQ.data?.data ?? []).filter(t => !tableQ || `${t.schema}.${t.tabela}`.toLowerCase().includes(tableQ.toLowerCase()))
  const cols = colsQ.data?.data ?? []
  const dateCols = cols.filter(c => c.is_data)

  return (
    <Modal open onClose={onClose} title="Adicionar tabela ao monitoramento" size="lg">
      <div className="flex flex-col gap-3">
        <Select label="1. Banco" value={database} onChange={e => { setDatabase(e.target.value); setSel(null); setColData('') }}>
          <option value="">Selecione…</option>
          {(dbsQ.data?.databases ?? []).map(d => <option key={d.name} value={d.name}>{d.name}</option>)}
        </Select>

        {database && (
          <div className="flex flex-col gap-1">
            <label className="text-xs text-dim font-medium">2. Tabela {tabelasQ.isFetching && <span className="text-dim/60">(carregando…)</span>}</label>
            <Input placeholder="Filtrar tabela…" value={tableQ} onChange={e => setTableQ(e.target.value)} />
            <div className="max-h-48 overflow-y-auto border border-edge rounded-md mt-1">
              {tabelas.map(t => (
                <button key={`${t.schema}.${t.tabela}`} type="button"
                  onClick={() => { setSel({ schema: t.schema, tabela: t.tabela }); setColData(''); setColAtu('') }}
                  className={`w-full text-left px-3 py-1.5 text-xs flex justify-between gap-2 hover:bg-edge/40 ${sel?.schema === t.schema && sel?.tabela === t.tabela ? 'bg-blue-50 dark:bg-blue-900/20' : ''}`}>
                  <span className="font-mono text-ink truncate">{t.schema}.{t.tabela}</span>
                  <span className="text-dim tabular-nums shrink-0">{t.linhas.toLocaleString('pt-BR')}</span>
                </button>
              ))}
              {tabelas.length === 0 && !tabelasQ.isFetching && <div className="px-3 py-3 text-xs text-dim text-center">Nenhuma tabela.</div>}
            </div>
          </div>
        )}

        {sel && (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            <Select label="3. Coluna de data (competência)" value={colData} onChange={e => setColData(e.target.value)}>
              <option value="">Selecione…</option>
              {dateCols.length > 0 && <optgroup label="Colunas de data">{dateCols.map(c => <option key={c.nome} value={c.nome}>{c.nome} ({c.tipo})</option>)}</optgroup>}
              {dateCols.length < cols.length && <optgroup label="Outras">{cols.filter(c => !c.is_data).map(c => <option key={c.nome} value={c.nome}>{c.nome} ({c.tipo})</option>)}</optgroup>}
            </Select>
            <Select label="Coluna de atualização (opcional)" value={colAtu} onChange={e => setColAtu(e.target.value)}>
              <option value="">—</option>{cols.map(c => <option key={c.nome} value={c.nome}>{c.nome} ({c.tipo})</option>)}
            </Select>
            <Select label="Criticidade" value={crit} onChange={e => setCrit(e.target.value)}>
              <option value="">—</option><option>Alta</option><option>Media</option><option>Baixa</option>
            </Select>
            <Input label="SLA de atualização (horas)" type="number" value={sla} onChange={e => setSla(e.target.value)} placeholder="ex.: 24" />
          </div>
        )}

        <div className="flex justify-end gap-2 border-t border-edge pt-3">
          <Button variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button loading={save.isPending} disabled={!sel || !colData} onClick={() => save.mutate()}>Adicionar</Button>
        </div>
      </div>
    </Modal>
  )
}

function MonitorDetail({ item, onClose }: { item: MonitorItem; onClose: () => void }) {
  const liveQ = useQuery<LiveResult>({ queryKey: ['monitor-live', item.id], queryFn: () => apiFetch(`/admin/monitor/${item.id}/live?dias=30`) })
  const histQ = useQuery<{ data: { captured_at: string; total_linhas: number | null; ultima_data: string | null; qtde_ultimo_dia: number | null; erro: string | null }[] }>({
    queryKey: ['monitor-hist', item.id], queryFn: () => apiFetch(`/admin/monitor/${item.id}/historico?limit=20`),
  })
  const live = liveQ.data
  return (
    <Modal open onClose={onClose} title={`${item.database_name}.${item.schema_name}.${item.table_name}`} size="lg">
      <div className="flex flex-col gap-4">
        {liveQ.isLoading && <PageSpinner />}
        {live?.erro && <div className="text-xs text-red-700 dark:text-red-400 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded p-2 break-words">Erro ao consultar: {live.erro}</div>}
        {live?.ok && (
          <>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              <Stat label="Total (aprox.)" value={live.total_linhas?.toLocaleString('pt-BR') ?? '—'} />
              <Stat label="Última competência" value={live.ultima_data ?? '—'} />
              <Stat label="Última escrita" value={live.last_write ?? '—'} />
              <Stat label="Qtde último dia" value={live.qtde_ultimo_dia?.toLocaleString('pt-BR') ?? '—'} />
            </div>
            <div>
              <div className="text-xs text-dim mb-1">Volume por dia (coluna <code className="text-[11px]">{item.coluna_data}</code>, últimos 30 dias)</div>
              <div className="border border-edge rounded-lg p-3 overflow-x-auto"><Sparkbars data={live.por_dia ?? []} h={120} /></div>
            </div>
          </>
        )}
        <div>
          <div className="text-xs text-dim mb-1">Histórico de snapshots</div>
          <div className="border border-edge rounded-lg max-h-48 overflow-y-auto">
            <table className="w-full text-xs">
              <thead className="bg-edge/30 text-dim sticky top-0"><tr className="text-left">
                <th className="px-3 py-1.5 font-medium">Capturado</th><th className="px-3 py-1.5 font-medium text-right">Total</th>
                <th className="px-3 py-1.5 font-medium">Última comp.</th><th className="px-3 py-1.5 font-medium text-right">Últ. dia</th>
              </tr></thead>
              <tbody>
                {(histQ.data?.data ?? []).map((h, i) => (
                  <tr key={i} className="border-t border-edge/40">
                    <td className="px-3 py-1.5 text-dim">{h.captured_at}</td>
                    <td className="px-3 py-1.5 text-right text-ink tabular-nums">{h.total_linhas?.toLocaleString('pt-BR') ?? '—'}</td>
                    <td className="px-3 py-1.5 text-dim">{h.ultima_data ?? (h.erro ? <span className="text-red-600 dark:text-red-400">erro</span> : '—')}</td>
                    <td className="px-3 py-1.5 text-right text-dim tabular-nums">{h.qtde_ultimo_dia?.toLocaleString('pt-BR') ?? '—'}</td>
                  </tr>
                ))}
                {(histQ.data?.data ?? []).length === 0 && <tr><td colSpan={4} className="px-3 py-4 text-center text-dim">Sem snapshots ainda. Use "Capturar agora".</td></tr>}
              </tbody>
            </table>
          </div>
        </div>
        <div className="flex justify-end border-t border-edge pt-3"><Button variant="secondary" onClick={onClose}>Fechar</Button></div>
      </div>
    </Modal>
  )
}

export function MonitoramentoTab() {
  const [add, setAdd] = useState(false)
  const [detail, setDetail] = useState<MonitorItem | null>(null)
  const [delItem, setDelItem] = useState<MonitorItem | null>(null)
  const { data, isLoading } = useQuery<{ data: MonitorItem[] }>({ queryKey: ['monitor'], queryFn: () => apiFetch('/admin/monitor') })
  const items = data?.data ?? []
  const capturar = useMutation({
    mutationFn: (id: number) => apiFetch(`/admin/monitor/${id}/capturar`, { method: 'POST' }),
    onSuccess: () => { toast.success('Snapshot capturado.'); queryClient.invalidateQueries({ queryKey: ['monitor'] }) },
    onError: (e: Error) => toast.error(e?.message || 'Falha ao capturar'),
  })
  const del = useMutation({
    mutationFn: (id: number) => apiFetch(`/admin/monitor/${id}`, { method: 'DELETE' }),
    onSuccess: () => { toast.success('Removido do monitoramento.'); setDelItem(null); queryClient.invalidateQueries({ queryKey: ['monitor'] }) },
    onError: (e: Error) => toast.error(e?.message || 'Falha ao remover'),
  })
  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2">
          <Database size={16} className="text-[#1A5FA8] dark:text-blue-400" />
          <div>
            <h2 className="text-sm font-bold text-ink">Monitoramento de tabelas</h2>
            <p className="text-xs text-dim mt-0.5">Última atualização e volume por dia das tabelas importantes. Snapshot diário automático + alerta de atraso/queda.</p>
          </div>
        </div>
        <Button onClick={() => setAdd(true)}><Plus size={14} /> Adicionar tabela</Button>
      </div>

      {isLoading && <PageSpinner />}
      {!isLoading && items.length === 0 && <div className="text-xs text-dim py-8 text-center">Nenhuma tabela monitorada. Clique em "Adicionar tabela".</div>}

      {items.length > 0 && (
        <div className="overflow-x-auto border border-edge rounded-lg">
          <table className="w-full text-sm">
            <thead className="bg-edge/30 text-dim">
              <tr className="text-left">
                <th className="px-3 py-2 font-medium">Tabela</th>
                <th className="px-3 py-2 font-medium">Crit.</th>
                <th className="px-3 py-2 font-medium whitespace-nowrap">Última atualização</th>
                <th className="px-3 py-2 font-medium text-right">Total</th>
                <th className="px-3 py-2 font-medium text-right">Últ. dia</th>
                <th className="px-3 py-2 font-medium">Volume (por dia)</th>
                <th className="px-3 py-2 font-medium"></th>
              </tr>
            </thead>
            <tbody>
              {items.map(it => {
                const s = it.snapshot
                const fr = freshness(s?.ultima_data)
                return (
                  <tr key={it.id} className={`border-t border-edge/40 hover:bg-edge/20 ${!it.ativo ? 'opacity-60' : ''}`}>
                    <td className="px-3 py-2">
                      <div className="font-mono text-ink text-xs">{it.database_name}.{it.schema_name}.{it.table_name}</div>
                      <div className="text-[10px] text-dim">por {it.coluna_data}{s?.captured_at && <> · snapshot {s.captured_at.substring(0, 16)}</>}</div>
                    </td>
                    <td className="px-3 py-2 text-xs text-dim">{it.criticidade ?? '—'}</td>
                    <td className="px-3 py-2"><span className={`text-[10px] px-1.5 py-0.5 rounded ${fr.cls}`}>{fr.label}</span></td>
                    <td className="px-3 py-2 text-right text-dim tabular-nums text-xs">{s?.total_linhas?.toLocaleString('pt-BR') ?? '—'}</td>
                    <td className="px-3 py-2 text-right text-dim tabular-nums text-xs">{s?.qtde_ultimo_dia?.toLocaleString('pt-BR') ?? '—'}</td>
                    <td className="px-3 py-2"><Sparkbars data={s?.por_dia ?? []} /></td>
                    <td className="px-3 py-2">
                      <div className="flex items-center gap-1 justify-end">
                        <button onClick={() => capturar.mutate(it.id)} disabled={capturar.isPending} className="text-slate-400 hover:text-[#1A5FA8] dark:hover:text-blue-400 p-1 rounded disabled:opacity-50" title="Capturar agora"><RefreshCw size={13} /></button>
                        <button onClick={() => setDetail(it)} className="text-slate-400 hover:text-[#1A5FA8] dark:hover:text-blue-400 p-1 rounded" title="Detalhe"><Eye size={13} /></button>
                        <button onClick={() => setDelItem(it)} className="text-slate-400 hover:text-red-500 dark:hover:text-red-400 p-1 rounded" title="Excluir"><Trash2 size={13} /></button>
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {add && <AddMonitorModal onClose={() => setAdd(false)} />}
      {detail && <MonitorDetail item={detail} onClose={() => setDetail(null)} />}
      <ConfirmModal open={!!delItem} title="Remover do monitoramento" danger confirmLabel="Remover"
        message={`Parar de monitorar "${delItem?.table_name}"? Os snapshots históricos também serão removidos.`}
        onConfirm={() => delItem && del.mutate(delItem.id)} onCancel={() => setDelItem(null)} />
    </div>
  )
}
