import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  BarChart3, RefreshCw, Search, AlertTriangle,
  Database, Network, X,
} from 'lucide-react'
import { apiFetch } from '../lib/api'
import { Card, KpiCard } from '../components/ui/Card'
import { Badge } from '../components/ui/Badge'
import { Tabs } from '../components/ui/Tabs'
import { Select } from '../components/ui/Input'
import { Button } from '../components/ui/Button'
import { Modal } from '../components/ui/Modal'
import { PageSpinner } from '../components/ui/Spinner'
import { InfoBanner } from '../components/ui/InfoBanner'

// ── Tipos ──────────────────────────────────────────────────────────────────

interface PbiStatus {
  configurado: boolean
  config: Record<string, string>
  token_ok: boolean
  workspaces_acessiveis: number | null
  admin_api_liberada: boolean | null
  erro: string | null
}

interface PbiWorkspace { id: string; name: string }

interface PbiDatasetRow {
  dataset_id: string
  dataset_name: string
  workspace_id: string
  workspace_name: string
  configured_by: string | null
  is_refreshable: boolean
  last_refresh_status: string | null
  last_refresh_start: string | null
  last_refresh_end: string | null
  last_refresh_error: string | null
  datasource_types: string[]
  erro: string | null
}

interface PbiOverview {
  workspaces: { total: number; data: PbiWorkspace[] }
  datasets: { total: number; truncado: boolean; data: PbiDatasetRow[] }
  resumo: {
    total_workspaces: number
    total_datasets: number
    datasets_com_falha: number
    datasets_sem_status: number
  }
}

interface PbiListResponse<T> { total: number; data: T[] }

interface PbiGateway { id: string; name: string; type?: string }

const STATUS_OPTIONS = [
  { value: '', label: 'Todos os status' },
  { value: 'falha', label: 'Com falha' },
  { value: 'ok', label: 'OK (Completed)' },
  { value: 'sem_status', label: 'Sem status / nunca atualizou' },
  { value: 'desabilitado', label: 'Refresh desabilitado' },
]

function refreshBadge(row: PbiDatasetRow) {
  if (!row.is_refreshable) return <Badge value="neutral">Não atualizável</Badge>
  const status = (row.last_refresh_status || '').toLowerCase()
  if (status === 'failed') return <Badge value="error">Falha</Badge>
  if (status === 'completed') return <Badge value="success">OK</Badge>
  if (status === 'disabled') return <Badge value="warning">Desabilitado</Badge>
  if (status === 'cancelled') return <Badge value="warning">Cancelado</Badge>
  return <Badge value="neutral">Sem status</Badge>
}

function fmtDt(v: string | null) {
  if (!v) return '—'
  try {
    return new Date(v).toLocaleString('pt-BR')
  } catch {
    return v
  }
}

function rowMatchesStatus(row: PbiDatasetRow, filter: string) {
  if (!filter) return true
  const status = (row.last_refresh_status || '').toLowerCase()
  if (filter === 'falha') return status === 'failed'
  if (filter === 'ok') return status === 'completed'
  if (filter === 'desabilitado') return !row.is_refreshable || status === 'disabled'
  if (filter === 'sem_status') return row.is_refreshable && !row.last_refresh_status
  return true
}

// ── Modal de drill-down de um dataset ────────────────────────────────────────

const DATASET_TABS = [
  { id: 'refreshes', label: 'Histórico de Refresh' },
  { id: 'schedule', label: 'Agendamento' },
  { id: 'datasources', label: 'Conexões' },
  { id: 'parameters', label: 'Parâmetros' },
  { id: 'users', label: 'Usuários' },
]

function DatasetDetailModal({ row, onClose }: { row: PbiDatasetRow; onClose: () => void }) {
  const [tab, setTab] = useState('refreshes')
  const base = `/powerbi/workspaces/${row.workspace_id}/datasets/${row.dataset_id}`

  const refreshesQ = useQuery({
    queryKey: ['pbi-refreshes', row.dataset_id],
    queryFn: () => apiFetch<PbiListResponse<any>>(`${base}/refreshes?top=15`),
    enabled: tab === 'refreshes',
  })
  const scheduleQ = useQuery({
    queryKey: ['pbi-schedule', row.dataset_id],
    queryFn: () => apiFetch<any>(`${base}/refresh-schedule`),
    enabled: tab === 'schedule',
  })
  const datasourcesQ = useQuery({
    queryKey: ['pbi-datasources', row.dataset_id],
    queryFn: () => apiFetch<PbiListResponse<any>>(`${base}/datasources`),
    enabled: tab === 'datasources',
  })
  const parametersQ = useQuery({
    queryKey: ['pbi-parameters', row.dataset_id],
    queryFn: () => apiFetch<PbiListResponse<any>>(`${base}/parameters`),
    enabled: tab === 'parameters',
  })
  const usersQ = useQuery({
    queryKey: ['pbi-users', row.dataset_id],
    queryFn: () => apiFetch<PbiListResponse<any>>(`${base}/users`),
    enabled: tab === 'users',
  })

  function renderError(q: { error: unknown }) {
    return (
      <div className="text-xs text-red-400 flex items-center gap-2 py-6 justify-center">
        <AlertTriangle size={14} /> {(q.error as Error)?.message || 'Erro ao consultar Power BI'}
      </div>
    )
  }

  return (
    <Modal open onClose={onClose} title={row.dataset_name} size="xl">
      <div className="text-xs text-dim mb-3">
        Workspace: <span className="text-ink">{row.workspace_name}</span>
        {row.configured_by && <> · Configurado por: <span className="text-ink">{row.configured_by}</span></>}
      </div>
      <Tabs tabs={DATASET_TABS} active={tab} onChange={setTab} size="sm" />
      <div className="mt-4">
        {tab === 'refreshes' && (
          refreshesQ.isLoading ? <PageSpinner /> : refreshesQ.isError ? renderError(refreshesQ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-[10px] text-dim border-b border-edge">
                  <th className="px-2 py-2 text-left">Status</th>
                  <th className="px-2 py-2 text-left">Início</th>
                  <th className="px-2 py-2 text-left">Fim</th>
                  <th className="px-2 py-2 text-left">Tipo</th>
                </tr>
              </thead>
              <tbody>
                {(refreshesQ.data?.data ?? []).map((r: any, i: number) => (
                  <tr key={i} className="border-b border-edge/40 last:border-0">
                    <td className="px-2 py-2"><Badge value={r.status === 'Failed' ? 'error' : r.status === 'Completed' ? 'success' : 'neutral'}>{r.status}</Badge></td>
                    <td className="px-2 py-2 font-mono text-[11px]">{fmtDt(r.startTime)}</td>
                    <td className="px-2 py-2 font-mono text-[11px]">{fmtDt(r.endTime)}</td>
                    <td className="px-2 py-2">{r.refreshType ?? '—'}</td>
                  </tr>
                ))}
                {!refreshesQ.data?.data?.length && (
                  <tr><td colSpan={4} className="px-2 py-6 text-center text-dim">Sem histórico de refresh.</td></tr>
                )}
              </tbody>
            </table>
          )
        )}

        {tab === 'schedule' && (
          scheduleQ.isLoading ? <PageSpinner /> : scheduleQ.isError ? renderError(scheduleQ) : (
            <div className="text-sm space-y-2">
              <div><span className="text-dim">Habilitado:</span> {scheduleQ.data?.enabled ? 'Sim' : 'Não'}</div>
              <div><span className="text-dim">Fuso horário:</span> {scheduleQ.data?.localTimeZoneId ?? '—'}</div>
              <div><span className="text-dim">Horários:</span> {(scheduleQ.data?.times ?? []).join(', ') || '—'}</div>
              <div><span className="text-dim">Dias:</span> {(scheduleQ.data?.days ?? []).join(', ') || '—'}</div>
              <div><span className="text-dim">Notificar falha:</span> {scheduleQ.data?.notifyOption ?? '—'}</div>
            </div>
          )
        )}

        {tab === 'datasources' && (
          datasourcesQ.isLoading ? <PageSpinner /> : datasourcesQ.isError ? renderError(datasourcesQ) : (
            <div className="space-y-2">
              {(datasourcesQ.data?.data ?? []).map((d: any, i: number) => (
                <div key={i} className="border border-edge rounded-md p-3 text-sm">
                  <div className="flex items-center gap-2 mb-1">
                    <Database size={14} className="text-dim" />
                    <span className="font-semibold">{d.datasourceType}</span>
                    {d.gatewayId && <Badge value="info">Via Gateway</Badge>}
                  </div>
                  <div className="text-xs text-dim font-mono break-all">
                    {Object.entries(d.connectionDetails ?? {}).map(([k, v]) => `${k}=${v}`).join('  ·  ') || '—'}
                  </div>
                </div>
              ))}
              {!datasourcesQ.data?.data?.length && <div className="text-center text-dim py-6">Sem datasources retornados.</div>}
            </div>
          )
        )}

        {tab === 'parameters' && (
          parametersQ.isLoading ? <PageSpinner /> : parametersQ.isError ? renderError(parametersQ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-[10px] text-dim border-b border-edge">
                  <th className="px-2 py-2 text-left">Nome</th>
                  <th className="px-2 py-2 text-left">Tipo</th>
                  <th className="px-2 py-2 text-left">Valor atual</th>
                </tr>
              </thead>
              <tbody>
                {(parametersQ.data?.data ?? []).map((p: any, i: number) => (
                  <tr key={i} className="border-b border-edge/40 last:border-0">
                    <td className="px-2 py-2">{p.name}</td>
                    <td className="px-2 py-2">{p.type}</td>
                    <td className="px-2 py-2 font-mono text-[11px]">{String(p.currentValue ?? '—')}</td>
                  </tr>
                ))}
                {!parametersQ.data?.data?.length && (
                  <tr><td colSpan={3} className="px-2 py-6 text-center text-dim">Sem parâmetros.</td></tr>
                )}
              </tbody>
            </table>
          )
        )}

        {tab === 'users' && (
          usersQ.isLoading ? <PageSpinner /> : usersQ.isError ? renderError(usersQ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-[10px] text-dim border-b border-edge">
                  <th className="px-2 py-2 text-left">Usuário / Identidade</th>
                  <th className="px-2 py-2 text-left">Nível de acesso</th>
                </tr>
              </thead>
              <tbody>
                {(usersQ.data?.data ?? []).map((u: any, i: number) => (
                  <tr key={i} className="border-b border-edge/40 last:border-0">
                    <td className="px-2 py-2">{u.identifier}</td>
                    <td className="px-2 py-2">{u.datasetUserAccessRight}</td>
                  </tr>
                ))}
                {!usersQ.data?.data?.length && (
                  <tr><td colSpan={2} className="px-2 py-6 text-center text-dim">Sem usuários retornados.</td></tr>
                )}
              </tbody>
            </table>
          )
        )}
      </div>
    </Modal>
  )
}

// ── Aba Gateways ──────────────────────────────────────────────────────────────

function GatewaysTab() {
  const [selected, setSelected] = useState<PbiGateway | null>(null)

  const gatewaysQ = useQuery({
    queryKey: ['pbi-gateways'],
    queryFn: () => apiFetch<PbiListResponse<PbiGateway>>('/powerbi/gateways'),
  })
  const datasourcesQ = useQuery({
    queryKey: ['pbi-gateway-datasources', selected?.id],
    queryFn: () => apiFetch<PbiListResponse<any>>(`/powerbi/gateways/${selected!.id}/datasources`),
    enabled: !!selected,
  })

  if (gatewaysQ.isLoading) return <PageSpinner />
  if (gatewaysQ.isError) return (
    <div className="text-sm text-red-400 flex items-center gap-2 py-6 justify-center">
      <AlertTriangle size={14} /> {(gatewaysQ.error as Error).message}
    </div>
  )

  const gateways = gatewaysQ.data?.data ?? []

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      <Card title={`Gateways (${gateways.length})`}>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-[10px] text-dim border-b border-edge">
              <th className="px-2 py-2 text-left">Nome</th>
              <th className="px-2 py-2 text-left">Tipo</th>
            </tr>
          </thead>
          <tbody>
            {gateways.map((g) => (
              <tr
                key={g.id}
                onClick={() => setSelected(g)}
                className={`border-b border-edge/40 last:border-0 cursor-pointer hover:bg-blue-50 dark:hover:bg-blue-900/10 ${selected?.id === g.id ? 'bg-blue-50 dark:bg-blue-900/20' : ''}`}
              >
                <td className="px-2 py-2 flex items-center gap-2"><Network size={13} className="text-dim" /> {g.name}</td>
                <td className="px-2 py-2">{g.type ?? '—'}</td>
              </tr>
            ))}
            {!gateways.length && <tr><td colSpan={2} className="px-2 py-6 text-center text-dim">Nenhum gateway acessível ao service principal.</td></tr>}
          </tbody>
        </table>
      </Card>

      <Card title={selected ? `Conexões do gateway "${selected.name}"` : 'Selecione um gateway'}>
        {!selected && <div className="text-center text-dim py-6 text-sm">Clique em um gateway à esquerda.</div>}
        {selected && datasourcesQ.isLoading && <PageSpinner />}
        {selected && datasourcesQ.isError && (
          <div className="text-sm text-red-400 flex items-center gap-2 py-6 justify-center">
            <AlertTriangle size={14} /> {(datasourcesQ.error as Error).message}
          </div>
        )}
        {selected && datasourcesQ.data && (
          <div className="space-y-2">
            {(datasourcesQ.data.data ?? []).map((d: any, i: number) => (
              <div key={i} className="border border-edge rounded-md p-3 text-sm">
                <div className="font-semibold mb-1">{d.datasourceType}</div>
                <div className="text-xs text-dim font-mono break-all">
                  {Object.entries(d.connectionDetails ?? {}).map(([k, v]) => `${k}=${v}`).join('  ·  ') || '—'}
                </div>
              </div>
            ))}
            {!datasourcesQ.data.data?.length && <div className="text-center text-dim py-6">Sem datasources neste gateway.</div>}
          </div>
        )}
      </Card>
    </div>
  )
}

// ── Página principal ──────────────────────────────────────────────────────────

export default function PowerBI() {
  const [tab, setTab] = useState('datasets')
  const [search, setSearch] = useState('')
  const [workspaceFilter, setWorkspaceFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [sourceFilter, setSourceFilter] = useState('')
  const [selectedRow, setSelectedRow] = useState<PbiDatasetRow | null>(null)

  const statusQ = useQuery({
    queryKey: ['pbi-status'],
    queryFn: () => apiFetch<PbiStatus>('/powerbi/status'),
  })

  const configurado = !!statusQ.data?.configurado

  const overviewQ = useQuery({
    queryKey: ['pbi-overview'],
    queryFn: () => apiFetch<PbiOverview>('/powerbi/overview'),
    enabled: configurado,
    refetchInterval: configurado ? 5 * 60 * 1000 : false,
  })

  const datasets = overviewQ.data?.datasets.data ?? []
  const workspaces = overviewQ.data?.workspaces.data ?? []

  const sourceTypes = useMemo(() => {
    const set = new Set<string>()
    datasets.forEach((d) => d.datasource_types.forEach((t) => set.add(t)))
    return Array.from(set).sort()
  }, [datasets])

  const filtered = useMemo(() => {
    const term = search.trim().toLowerCase()
    return datasets.filter((d) => {
      if (workspaceFilter && d.workspace_id !== workspaceFilter) return false
      if (!rowMatchesStatus(d, statusFilter)) return false
      if (sourceFilter && !d.datasource_types.includes(sourceFilter)) return false
      if (term && !`${d.dataset_name} ${d.workspace_name}`.toLowerCase().includes(term)) return false
      return true
    })
  }, [datasets, search, workspaceFilter, statusFilter, sourceFilter])

  if (statusQ.isLoading) return <PageSpinner />

  if (!configurado) {
    return (
      <div className="p-6 space-y-4">
        <h1 className="text-xl font-semibold flex items-center gap-2"><BarChart3 size={20} /> Power BI — Sustentação</h1>
        <InfoBanner icon="⚠️">
          Power BI ainda não está configurado. Em <strong>Admin &gt; Configurações</strong>, adicione os parâmetros:
          <code className="block mt-1 text-[11px] bg-black/20 rounded px-2 py-1">
            powerbi_tenant_id · powerbi_client_id · powerbi_client_secret · powerbi_scope (opcional) · powerbi_token_url (opcional)
          </code>
          {statusQ.data?.erro && <div className="mt-2 text-red-700 dark:text-red-300">{statusQ.data.erro}</div>}
        </InfoBanner>
      </div>
    )
  }

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold flex items-center gap-2"><BarChart3 size={20} /> Power BI — Sustentação</h1>
        <Button variant="secondary" size="sm" onClick={() => overviewQ.refetch()} loading={overviewQ.isFetching}>
          <RefreshCw size={13} /> Atualizar
        </Button>
      </div>

      {statusQ.data?.admin_api_liberada === false && (
        <InfoBanner storageKey="pbi_admin_api_gate" icon="ℹ️">
          O service principal só consegue ver workspaces onde foi adicionado como membro. Para inventário
          completo do tenant, habilite no Admin Portal do Power BI (Tenant settings &gt; Developer settings)
          "Allow service principals to use Power BI APIs" e "...read-only admin APIs".
        </InfoBanner>
      )}

      {overviewQ.isError && (
        <InfoBanner icon="⚠️">{(overviewQ.error as Error).message}</InfoBanner>
      )}

      {overviewQ.isLoading ? <PageSpinner /> : overviewQ.data && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <KpiCard label="Workspaces" value={overviewQ.data.resumo.total_workspaces} color="blue" />
            <KpiCard label="Datasets" value={overviewQ.data.resumo.total_datasets} color="blue" />
            <KpiCard label="Com falha" value={overviewQ.data.resumo.datasets_com_falha} color="red" />
            <KpiCard label="Sem status" value={overviewQ.data.resumo.datasets_sem_status} color="yellow" />
          </div>

          <Tabs
            tabs={[{ id: 'datasets', label: 'Datasets' }, { id: 'gateways', label: 'Gateways' }]}
            active={tab}
            onChange={setTab}
          />

          {tab === 'datasets' && (
            <Card>
              <div className="flex flex-wrap items-end gap-3 mb-4">
                <div className="flex-1 min-w-[200px] flex flex-col gap-1">
                  <label className="text-xs text-dim font-medium">Buscar</label>
                  <div className="relative">
                    <Search size={14} className="absolute left-2.5 top-2.5 text-dim" />
                    <input
                      value={search}
                      onChange={(e) => setSearch(e.target.value)}
                      placeholder="Nome do dataset ou workspace..."
                      className="w-full bg-panel border border-edge text-ink rounded-md pl-8 pr-3 py-1.5 text-sm placeholder-dim focus:outline-none focus:ring-1 focus:ring-blue-500"
                    />
                  </div>
                </div>
                <Select label="Workspace" value={workspaceFilter} onChange={(e) => setWorkspaceFilter(e.target.value)}>
                  <option value="">Todos os workspaces</option>
                  {workspaces.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}
                </Select>
                <Select label="Status" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
                  {STATUS_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                </Select>
                <Select label="Tipo de fonte" value={sourceFilter} onChange={(e) => setSourceFilter(e.target.value)}>
                  <option value="">Todas as fontes</option>
                  {sourceTypes.map((t) => <option key={t} value={t}>{t}</option>)}
                </Select>
                {(search || workspaceFilter || statusFilter || sourceFilter) && (
                  <Button variant="ghost" size="sm" onClick={() => { setSearch(''); setWorkspaceFilter(''); setStatusFilter(''); setSourceFilter('') }}>
                    <X size={13} /> Limpar
                  </Button>
                )}
              </div>

              {overviewQ.data.datasets.truncado && (
                <div className="text-[11px] text-amber-500 mb-2 flex items-center gap-1">
                  <AlertTriangle size={12} /> Lista truncada — há mais datasets do que o limite exibido por consulta.
                </div>
              )}

              <table className="w-full text-sm">
                <thead>
                  <tr className="text-[10px] text-dim border-b border-edge bg-canvas/50">
                    <th className="px-3 py-2 text-left">Dataset</th>
                    <th className="px-3 py-2 text-left">Workspace</th>
                    <th className="px-3 py-2 text-left">Fonte</th>
                    <th className="px-3 py-2 text-left">Última atualização</th>
                    <th className="px-3 py-2 text-left">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((row) => (
                    <tr
                      key={row.dataset_id}
                      onClick={() => setSelectedRow(row)}
                      className="border-b border-edge/40 last:border-0 hover:bg-blue-50 dark:hover:bg-blue-900/10 transition-colors cursor-pointer"
                    >
                      <td className="px-3 py-2 font-medium">{row.dataset_name}</td>
                      <td className="px-3 py-2 text-dim">{row.workspace_name}</td>
                      <td className="px-3 py-2">
                        <div className="flex flex-wrap gap-1">
                          {row.datasource_types.length
                            ? row.datasource_types.map((t) => <Badge key={t} value="info">{t}</Badge>)
                            : <span className="text-dim">—</span>}
                        </div>
                      </td>
                      <td className="px-3 py-2 font-mono text-[11px] text-dim">{fmtDt(row.last_refresh_end)}</td>
                      <td className="px-3 py-2">{refreshBadge(row)}</td>
                    </tr>
                  ))}
                  {!filtered.length && (
                    <tr><td colSpan={5} className="px-3 py-8 text-center text-dim">Nenhum dataset encontrado com os filtros atuais.</td></tr>
                  )}
                </tbody>
              </table>
            </Card>
          )}

          {tab === 'gateways' && <GatewaysTab />}
        </>
      )}

      {selectedRow && <DatasetDetailModal row={selectedRow} onClose={() => setSelectedRow(null)} />}
    </div>
  )
}
