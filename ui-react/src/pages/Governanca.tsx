import { useState, useMemo, useEffect, useCallback } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { apiFetch } from '../lib/api'
import { Button } from '../components/ui/Button'
import { PageSpinner } from '../components/ui/Spinner'
import { Modal } from '../components/ui/Modal'
import { Tabs } from '../components/ui/Tabs'
import { InfoBanner } from '../components/ui/InfoBanner'
import { useAuthStore } from '../store/auth'
import {
  Search, Download, ChevronDown, ChevronUp, ArrowRight, History,
  Tag, Pencil, FileText, Database, Network, Zap,
} from 'lucide-react'

// ════════════════════════════════════════════════════════════════════════════
// Tipos da API
// ════════════════════════════════════════════════════════════════════════════

interface LineageItem {
  object_name: string
  object_type?: string
  stage_name?: string
  stage_type_raw?: string
  type_label?: string
  database_name?: string
  sql_expression?: string
  file_path?: string
  columns?: string[]
}
interface LineageJob {
  execution_order: number
  job_name: string
  job_type?: string
  origens: LineageItem[]
  transformacoes: LineageItem[]
  destinos: LineageItem[]
}
interface LineageResponse {
  pipeline_name: string
  jobs: LineageJob[]
}

interface AssetRow {
  asset_name: string
  asset_type: string
  database_name?: string
  pipeline_count?: number
  as_origem?: number
  as_destino?: number
}
interface OverviewResponse {
  total_assets: number
  total_pipelines: number
  total_with_owner: number
  classification_counts: { pii: number; confidencial: number; regulado: number; publico: number }
  top_assets: AssetRow[]
  alerts: { type: string; message: string }[]
}
interface BrowseResponse {
  assets: AssetRow[]
  facets: { databases: string[]; types: string[]; classifications: string[] }
}
interface SearchJob {
  job_name: string
  execution_order: number
  job_type?: string
  direction: string
  object_name?: string
  object_type?: string
  database_name?: string
  file_path?: string
  stage_name?: string
  columns?: string[]
}
interface SearchPipeline {
  pipeline_name: string
  project_name: string
  domain: string
  active: number
  ocorrencias: number
  jobs: SearchJob[]
}
interface SearchResponse {
  search_type: string
  term: string
  direction: string
  total_pipelines: number
  total_ocorrencias: number
  pipelines: SearchPipeline[]
}
interface AssetDetailResponse {
  asset_name: string
  asset_type: string
  database_name: string
  pipelines_origem: { pipeline_name: string; job_name: string; execution_order: number; columns_json?: string }[]
  pipelines_destino: { pipeline_name: string; job_name: string; execution_order: number; columns_json?: string }[]
  columns: string[]
  tags: string[]
  sql_expression: string
}

// ════════════════════════════════════════════════════════════════════════════
// Helpers
// ════════════════════════════════════════════════════════════════════════════

const cat = <T,>(body: object) => apiFetch<T>('/catalogo', { method: 'POST', body: JSON.stringify(body) })

const fileBasename = (p?: string) => (p ? p.replace(/\\/g, '/').split('/').filter(Boolean).pop() || p : '')

const TAG_OPTIONS = ['PII', 'Confidencial', 'Regulado', 'Publico'] as const
const TAG_STYLES: Record<string, string> = {
  PII:          'bg-red-100 text-red-700 border border-red-200 dark:bg-red-900/40 dark:text-red-300 dark:border-red-800',
  CONFIDENCIAL: 'bg-orange-100 text-orange-700 border border-orange-200 dark:bg-orange-900/40 dark:text-orange-300 dark:border-orange-800',
  REGULADO:     'bg-purple-100 text-purple-700 border border-purple-200 dark:bg-purple-900/40 dark:text-purple-300 dark:border-purple-800',
  PUBLICO:      'bg-green-100 text-green-700 border border-green-200 dark:bg-green-900/40 dark:text-green-300 dark:border-green-800',
}
function TagChip({ tag }: { tag: string }) {
  return <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold ${TAG_STYLES[tag.toUpperCase()] ?? 'bg-slate-100 text-slate-600'}`}>{tag}</span>
}

const parseCols = (j?: string): string[] => { try { return j ? JSON.parse(j) : [] } catch { return [] } }

const smartIsArquivo = (v: string) => /\.(ds|dx|csv|txt|seq|dat)$/i.test(v) || /^(ds_|seq_|file:|arquivo:)/i.test(v)

const inputCls = 'border border-edge bg-canvas text-ink text-sm rounded-md px-2.5 py-1.5 focus:outline-none focus:ring-2 focus:ring-[#1A5FA8]/40 placeholder:text-dim'

const RECENT_KEY = 'orq_cat_recent'
interface RecentItem { name: string; type: string; dbName: string; ts: number }
function readRecent(): RecentItem[] { try { return JSON.parse(localStorage.getItem(RECENT_KEY) || '[]') } catch { return [] } }
function pushRecent(name: string, type: string, dbName: string) {
  let list = readRecent().filter(x => x.name !== name || x.type !== type)
  list.unshift({ name, type, dbName: dbName || '', ts: Date.now() })
  if (list.length > 8) list = list.slice(0, 8)
  localStorage.setItem(RECENT_KEY, JSON.stringify(list))
}

// ════════════════════════════════════════════════════════════════════════════
// Modal de lista pesquisável (SQL / campos / itens)
// ════════════════════════════════════════════════════════════════════════════

function ListModal({ title, items, onClose }: { title: string; items: string[]; onClose: () => void }) {
  const [q, setQ] = useState('')
  const noun = title.toLowerCase().includes('campo') ? 'campos' : 'itens'
  const filtered = q ? items.filter(i => i.toLowerCase().includes(q.toLowerCase())) : items
  return (
    <Modal open onClose={onClose} title={title} size="lg">
      <div className="flex flex-col gap-2">
        <div className="text-xs text-dim">{q ? `${filtered.length} de ${items.length} ${noun}` : `${items.length} ${noun}`}</div>
        {items.length > 8 && (
          <input autoFocus value={q} onChange={e => setQ(e.target.value)} placeholder="Filtrar…" className={inputCls} />
        )}
        <ul className="flex flex-col divide-y divide-edge max-h-[55vh] overflow-y-auto">
          {filtered.length ? filtered.map((it, i) => (
            <li key={i} className="py-1.5 px-1 font-mono text-xs text-ink break-all">{it}</li>
          )) : <li className="py-2 text-xs text-dim">—</li>}
        </ul>
      </div>
    </Modal>
  )
}

// ════════════════════════════════════════════════════════════════════════════
// Nó de lineage
// ════════════════════════════════════════════════════════════════════════════

type NodeKind = 'origem' | 'destino' | 'transf' | 'job'
const NODE_STYLES: Record<NodeKind, string> = {
  origem: 'bg-[#EEF5FD] border-[#A3C7F0] text-[#185FA5] dark:bg-[#185FA5]/15 dark:border-[#185FA5]/50 dark:text-[#7db3ee]',
  destino:'bg-[#EEF9F2] border-[#A8D5B5] text-[#27500A] dark:bg-[#27500A]/20 dark:border-[#27500A]/60 dark:text-[#86c98f]',
  transf: 'bg-[#FDF8EE] border-[#F0D68C] text-[#854F0B] dark:bg-[#854F0B]/15 dark:border-[#854F0B]/50 dark:text-[#e0b766]',
  job:    'bg-[#F3EFFE] border-[#C5A8F5] text-[#534AB7] dark:bg-[#534AB7]/20 dark:border-[#534AB7]/60 dark:text-[#b3a4f0]',
}

function LineageNode({ item, kind, onShow }: { item: LineageItem; kind: NodeKind; onShow: (title: string, items: string[]) => void }) {
  const isFile = !!item.file_path
  const isDb = !isFile && (!!item.database_name || (item.object_type || '').toLowerCase().includes('odbc') || (item.object_type || '').toLowerCase().includes('banco'))
  const label = item.stage_name || item.object_name || '—'
  let detail = ''
  if (isFile) detail = `Arquivo: ${fileBasename(item.file_path)}`
  else if (isDb) detail = `ODBC${item.database_name ? ': ' + item.database_name : ''}`
  else detail = item.type_label || item.object_type || ''

  const sql = (!isFile && item.sql_expression) ? String(item.sql_expression).trim() : ''
  const cols = Array.isArray(item.columns) ? item.columns : []

  return (
    <div className={`border rounded-lg px-3 py-2 min-w-[140px] text-center ${NODE_STYLES[kind]}`}>
      <div className="flex items-center justify-center gap-1.5">
        <span className="text-xs font-medium">{label}</span>
        {sql && (
          <button onClick={() => onShow('SQL / Tabelas', sql.split('\n').map(s => s.trim()).filter(Boolean))}
            title="Ver SQL / tabelas" className="w-4 h-4 rounded-full border border-current text-[10px] leading-none flex items-center justify-center hover:opacity-70">+</button>
        )}
        {cols.length > 0 && (
          <button onClick={() => onShow(`Campos utilizados (${cols.length})`, cols)}
            title="Ver campos utilizados" className="w-4 h-4 rounded-full border border-orange-400 text-orange-600 bg-orange-100 dark:bg-orange-900/40 text-[10px] leading-none flex items-center justify-center hover:opacity-70">⊞</button>
        )}
      </div>
      {detail && <div className="text-[10px] opacity-80 mt-0.5">{detail}</div>}
    </div>
  )
}

function Arrow() { return <ArrowRight size={16} className="text-dim shrink-0" /> }

// ════════════════════════════════════════════════════════════════════════════
// Aba LINEAGE
// ════════════════════════════════════════════════════════════════════════════

function LineageTab({ pipeline, setPipeline }: { pipeline: string; setPipeline: (p: string) => void }) {
  const [input, setInput] = useState(pipeline)
  const [mode, setMode] = useState<'job' | 'pipeline'>('job')
  const [selectedJob, setSelectedJob] = useState('')
  const [modal, setModal] = useState<{ title: string; items: string[] } | null>(null)

  useEffect(() => { setInput(pipeline) }, [pipeline])

  const { data: pipeList } = useQuery<{ pipelines: string[] }>({
    queryKey: ['list_pipelines'],
    queryFn: () => cat({ mode: 'list_pipelines' }),
    staleTime: 5 * 60_000,
  })

  const { data, isLoading, isFetching } = useQuery<LineageResponse>({
    queryKey: ['lineage', pipeline],
    queryFn: () => apiFetch(`/lineage?pipeline_name=${encodeURIComponent(pipeline)}`),
    enabled: !!pipeline,
  })

  const jobs = data?.jobs ?? []
  useEffect(() => { if (jobs.length && !selectedJob) setSelectedJob(jobs[0].job_name) }, [jobs, selectedJob])
  useEffect(() => { setSelectedJob('') }, [pipeline])

  const showModal = useCallback((title: string, items: string[]) => setModal({ title, items }), [])
  const load = () => { setPipeline(input.trim()); setMode('job') }

  const job = jobs.find(j => j.job_name === selectedJob)

  return (
    <div className="flex flex-col gap-4">
      {/* Filtro */}
      <div className="flex flex-wrap gap-2 items-center">
        <input
          list="gov-pipeline-list"
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') load() }}
          placeholder="Nome do pipeline…"
          className={`${inputCls} w-72`}
        />
        <datalist id="gov-pipeline-list">
          {(pipeList?.pipelines ?? []).map(n => <option key={n} value={n} />)}
        </datalist>
        <Button onClick={load} disabled={!input.trim()} loading={isFetching}><Search size={13} /> Carregar lineage</Button>
        {data && <span className="text-xs text-dim">Lineage de {jobs.length} job(s) carregado.</span>}
      </div>

      {/* Toggle de modo */}
      {data && jobs.length > 0 && (
        <div className="flex flex-wrap gap-2 items-center">
          <div className="flex gap-1">
            <button onClick={() => setMode('job')}
              className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${mode === 'job' ? 'bg-[#1A5FA8] text-white' : 'border border-edge bg-canvas text-dim hover:text-ink'}`}>
              Nível Job
            </button>
            <button onClick={() => setMode('pipeline')}
              className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${mode === 'pipeline' ? 'bg-[#1A5FA8] text-white' : 'border border-edge bg-canvas text-dim hover:text-ink'}`}>
              Nível Pipeline
            </button>
          </div>
          {mode === 'job' && (
            <select value={selectedJob} onChange={e => setSelectedJob(e.target.value)} className={`${inputCls} w-72`}>
              <option value="">Selecione o job…</option>
              {jobs.map(j => <option key={j.job_name} value={j.job_name}>#{j.execution_order} {j.job_name}</option>)}
            </select>
          )}
        </div>
      )}

      {/* Visualização */}
      {isLoading ? <PageSpinner /> : !data ? (
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <Network size={40} className="text-dim mb-3" />
          <p className="font-semibold text-ink">Informe o pipeline e carregue o lineage</p>
          <p className="text-sm text-dim mt-1">O diagrama aparecerá aqui.</p>
        </div>
      ) : mode === 'job' ? (
        !job ? (
          <div className="text-sm text-dim py-8 text-center">Selecione um job.</div>
        ) : (job.origens.length || job.transformacoes.length || job.destinos.length) ? (
          <div className="bg-panel border border-edge rounded-lg p-4 overflow-x-auto">
            <div className="flex items-center gap-3 min-w-max">
              <div className="flex flex-col gap-2">
                {job.origens.length ? job.origens.map((o, i) => <LineageNode key={i} item={o} kind="origem" onShow={showModal} />)
                  : <i className="text-xs text-dim">Sem origens</i>}
              </div>
              <Arrow />
              {job.transformacoes.length > 0 && (<>
                <div className="flex flex-col gap-2">
                  {job.transformacoes.map((t, i) => <LineageNode key={i} item={t} kind="transf" onShow={showModal} />)}
                </div>
                <Arrow />
              </>)}
              <div className={`border rounded-lg px-3 py-2 min-w-[140px] text-center ${NODE_STYLES.job}`}>
                <div className="text-xs font-semibold">{job.job_name}</div>
                <div className="text-[10px] opacity-80 mt-0.5">Job #{job.execution_order}{job.job_type ? ` · ${job.job_type}` : ''}</div>
              </div>
              <Arrow />
              <div className="flex flex-col gap-2">
                {job.destinos.length ? job.destinos.map((d, i) => <LineageNode key={i} item={d} kind="destino" onShow={showModal} />)
                  : <i className="text-xs text-dim">Sem destinos</i>}
              </div>
            </div>
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center py-16 text-center">
            <p className="font-semibold text-ink">Sem lineage cadastrado para este job</p>
            <p className="text-sm text-dim mt-1">Cadastre origens e destinos na tela de Jobs.</p>
          </div>
        )
      ) : (
        // Modo pipeline — fluxo vertical
        <div className="flex flex-col gap-3">
          {jobs.map((j, idx) => (
            <div key={j.job_name}>
              <div className="bg-panel border border-edge rounded-lg p-3">
                <div className="flex items-center gap-2 mb-2">
                  <span className="w-7 h-7 rounded-full bg-[#1A5FA8] text-white text-xs font-bold flex items-center justify-center shrink-0">{j.execution_order}</span>
                  <span className="font-mono text-sm font-semibold text-ink">{j.job_name}</span>
                  {j.job_type && <span className="text-[10px] text-dim">{j.job_type}</span>}
                </div>
                <div className="flex items-center gap-2 flex-wrap pl-9">
                  <div className="flex flex-wrap gap-1.5">
                    {j.origens.length ? j.origens.map((o, i) => <LineageNode key={i} item={o} kind="origem" onShow={showModal} />)
                      : <i className="text-xs text-dim">Sem origens</i>}
                  </div>
                  <Arrow />
                  <div className="flex flex-wrap gap-1.5">
                    {j.destinos.length ? j.destinos.map((d, i) => <LineageNode key={i} item={d} kind="destino" onShow={showModal} />)
                      : <i className="text-xs text-dim">Sem destinos</i>}
                  </div>
                </div>
              </div>
              {idx < jobs.length - 1 && <div className="flex justify-center"><ChevronDown size={16} className="text-dim my-0.5" /></div>}
            </div>
          ))}
        </div>
      )}

      {modal && <ListModal title={modal.title} items={modal.items} onClose={() => setModal(null)} />}
    </div>
  )
}

// ════════════════════════════════════════════════════════════════════════════
// Modal de detalhe de ativo
// ════════════════════════════════════════════════════════════════════════════

function AssetDetailModal({ asset, onClose, onGoLineage }: {
  asset: { name: string; type: string; db: string }
  onClose: () => void
  onGoLineage: (pipeline: string) => void
}) {
  const [colsModal, setColsModal] = useState<string[] | null>(null)
  const { data, isLoading } = useQuery<AssetDetailResponse>({
    queryKey: ['asset_detail', asset.name, asset.type, asset.db],
    queryFn: () => cat({ mode: 'asset_detail', asset_name: asset.name, asset_type: asset.type, database_name: asset.db }),
  })

  const readers = data?.pipelines_origem ?? []
  const writers = data?.pipelines_destino ?? []

  const PipeRow = ({ p, dir }: { p: AssetDetailResponse['pipelines_origem'][0]; dir: 'origem' | 'destino' }) => {
    const cols = parseCols(p.columns_json)
    return (
      <div className="flex items-center gap-2 px-2 py-1 rounded hover:bg-canvas">
        <span className={`text-[10px] font-bold min-w-[44px] ${dir === 'origem' ? 'text-[#185FA5]' : 'text-[#27500A] dark:text-[#86c98f]'}`}>{dir === 'origem' ? '← lê' : '→ grava'}</span>
        <span className="font-mono text-xs flex-1 truncate text-ink">{p.pipeline_name}</span>
        <span className="text-[10px] text-dim">#{p.execution_order}</span>
        {cols.length > 0 && (
          <button onClick={() => setColsModal(cols)} className="text-[10px] px-1.5 rounded bg-orange-100 dark:bg-orange-900/40 text-orange-600 border border-orange-300">⊞ {cols.length}</button>
        )}
        <button onClick={() => onGoLineage(p.pipeline_name)} title="Ver lineage" className="text-[#1A5FA8] hover:opacity-70"><ArrowRight size={12} /></button>
      </div>
    )
  }

  return (
    <Modal open onClose={onClose} title={asset.name} size="lg">
      <div className="text-xs text-dim mb-3">{asset.type === 'arquivo' ? '◈ Arquivo' : `◫ ${asset.db || 'Tabela'}`}</div>
      {isLoading ? <PageSpinner /> : (
        <div className="flex flex-col gap-4">
          {(data?.tags?.length ?? 0) > 0 && (
            <div>
              <div className="text-[10px] font-bold uppercase tracking-wider text-dim mb-1">Classificação</div>
              <div className="flex flex-wrap gap-1">{data!.tags.map(t => <TagChip key={t} tag={t} />)}</div>
            </div>
          )}
          {readers.length > 0 && (
            <div>
              <div className="text-[10px] font-bold uppercase tracking-wider text-dim mb-1">← Lido por ({readers.length} pipeline{readers.length > 1 ? 's' : ''})</div>
              <div className="flex flex-col gap-0.5">{readers.map((p, i) => <PipeRow key={i} p={p} dir="origem" />)}</div>
            </div>
          )}
          {writers.length > 0 && (
            <div>
              <div className="text-[10px] font-bold uppercase tracking-wider text-dim mb-1">→ Gravado por ({writers.length} pipeline{writers.length > 1 ? 's' : ''})</div>
              <div className="flex flex-col gap-0.5">{writers.map((p, i) => <PipeRow key={i} p={p} dir="destino" />)}</div>
            </div>
          )}
          {(data?.columns?.length ?? 0) > 0 && (
            <div>
              <div className="text-[10px] font-bold uppercase tracking-wider text-dim mb-1">Colunas ({data!.columns.length})</div>
              <div className="flex flex-wrap gap-1">
                {data!.columns.map(c => <span key={c} className="font-mono text-[10px] px-1.5 py-0.5 rounded bg-[#1A5FA8]/10 text-[#1A5FA8]">{c}</span>)}
              </div>
            </div>
          )}
          {data?.sql_expression && (
            <div>
              <div className="text-[10px] font-bold uppercase tracking-wider text-dim mb-1">SQL / Tabelas referenciadas</div>
              <pre className="text-[10px] bg-canvas border border-edge rounded p-2 overflow-x-auto whitespace-pre-wrap break-all">{data.sql_expression}</pre>
            </div>
          )}
          {!readers.length && !writers.length && <div className="text-sm text-dim">Nenhuma linhagem encontrada para este objeto.</div>}
        </div>
      )}
      {colsModal && <ListModal title={`Campos (${colsModal.length})`} items={colsModal} onClose={() => setColsModal(null)} />}
    </Modal>
  )
}

// ════════════════════════════════════════════════════════════════════════════
// Modais auxiliares: histórico, file lineage, owner, tags
// ════════════════════════════════════════════════════════════════════════════

function HistoryModal({ pipeline, onClose }: { pipeline: string; onClose: () => void }) {
  const { data, isLoading } = useQuery<{ history: { imported_at?: string; status?: string; reviewed_by?: string; reviewed_at?: string; obs?: string }[] }>({
    queryKey: ['pipeline_history', pipeline],
    queryFn: () => cat({ mode: 'pipeline_history', pipeline_name: pipeline }),
  })
  return (
    <Modal open onClose={onClose} title={`Histórico — ${pipeline}`} size="lg">
      {isLoading ? <PageSpinner /> : (data?.history?.length ? (
        <table className="w-full text-xs">
          <thead><tr className="text-left text-dim border-b border-edge">
            <th className="py-1 pr-2">Importado</th><th className="pr-2">Status</th><th className="pr-2">Revisor</th><th>Obs</th>
          </tr></thead>
          <tbody>
            {data.history.map((h, i) => (
              <tr key={i} className="border-b border-edge/50">
                <td className="py-1 pr-2 whitespace-nowrap">{h.imported_at?.slice(0, 19) ?? '—'}</td>
                <td className="pr-2">{h.status ?? '—'}</td>
                <td className="pr-2">{h.reviewed_by ?? '—'}</td>
                <td className="text-dim">{h.obs ?? ''}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : <div className="text-sm text-dim">Nenhum histórico de importação.</div>)}
    </Modal>
  )
}

function FileLineageModal({ file, onClose, onGoLineage }: { file: string; onClose: () => void; onGoLineage: (p: string) => void }) {
  const { data, isLoading } = useQuery<{ writers: { pipeline_name: string; job_name: string }[]; readers: { pipeline_name: string; job_name: string }[] }>({
    queryKey: ['file_lineage', file],
    queryFn: () => cat({ mode: 'file_lineage', file_name: file }),
  })
  const Row = ({ p }: { p: { pipeline_name: string; job_name: string } }) => (
    <div className="flex items-center gap-2 px-2 py-1 rounded hover:bg-canvas">
      <span className="font-mono text-xs flex-1 truncate text-ink">{p.pipeline_name}</span>
      <span className="text-[10px] text-dim">{p.job_name}</span>
      <button onClick={() => onGoLineage(p.pipeline_name)} className="text-[#1A5FA8] hover:opacity-70"><ArrowRight size={12} /></button>
    </div>
  )
  return (
    <Modal open onClose={onClose} title={`Linhagem do arquivo — ${fileBasename(file)}`} size="lg">
      {isLoading ? <PageSpinner /> : (
        <div className="flex flex-col gap-4">
          <div>
            <div className="text-[10px] font-bold uppercase tracking-wider text-dim mb-1">→ Gravado por ({data?.writers.length ?? 0})</div>
            {data?.writers.length ? data.writers.map((p, i) => <Row key={i} p={p} />) : <div className="text-xs text-dim">—</div>}
          </div>
          <div>
            <div className="text-[10px] font-bold uppercase tracking-wider text-dim mb-1">← Lido por ({data?.readers.length ?? 0})</div>
            {data?.readers.length ? data.readers.map((p, i) => <Row key={i} p={p} />) : <div className="text-xs text-dim">—</div>}
          </div>
        </div>
      )}
    </Modal>
  )
}

function OwnerModal({ pipeline, user, onClose }: { pipeline: string; user: string; onClose: () => void }) {
  const qc = useQueryClient()
  const [form, setForm] = useState({ owner_name: '', owner_email: '', steward_name: '', steward_email: '' })
  const [saving, setSaving] = useState(false)
  const { data } = useQuery<{ owner_name?: string; owner_email?: string; steward_name?: string; steward_email?: string }>({
    queryKey: ['get_owner', pipeline],
    queryFn: () => cat({ mode: 'get_owner', pipeline_name: pipeline }),
  })
  useEffect(() => { if (data) setForm({ owner_name: data.owner_name ?? '', owner_email: data.owner_email ?? '', steward_name: data.steward_name ?? '', steward_email: data.steward_email ?? '' }) }, [data])
  const save = async () => {
    setSaving(true)
    try {
      await cat({ mode: 'save_owner', pipeline_name: pipeline, user, data: form })
      qc.invalidateQueries({ queryKey: ['get_owner', pipeline] })
      onClose()
    } finally { setSaving(false) }
  }
  const fld = (k: keyof typeof form, label: string) => (
    <label className="flex flex-col gap-1">
      <span className="text-xs text-dim font-medium">{label}</span>
      <input value={form[k]} onChange={e => setForm({ ...form, [k]: e.target.value })} className={inputCls} />
    </label>
  )
  return (
    <Modal open onClose={onClose} title={`Responsável — ${pipeline}`} size="md">
      <div className="flex flex-col gap-3">
        {fld('owner_name', 'Nome do Data Owner')}
        {fld('owner_email', 'Email do Data Owner')}
        {fld('steward_name', 'Nome do Data Steward')}
        {fld('steward_email', 'Email do Data Steward')}
        <div className="flex justify-end gap-2 mt-2">
          <Button variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button onClick={save} loading={saving}>Salvar</Button>
        </div>
      </div>
    </Modal>
  )
}

function TagModal({ objectKey, user, onClose }: { objectKey: string; user: string; onClose: () => void }) {
  const qc = useQueryClient()
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [original, setOriginal] = useState<Set<string>>(new Set())
  const [saving, setSaving] = useState(false)
  const { data } = useQuery<{ tags: { tag: string }[] }>({
    queryKey: ['get_tags', objectKey],
    queryFn: () => cat({ mode: 'get_tags', object_key: objectKey }),
  })
  useEffect(() => {
    if (data) { const s = new Set(data.tags.map(t => t.tag)); setSelected(new Set(s)); setOriginal(new Set(s)) }
  }, [data])
  const toggle = (t: string) => { const s = new Set(selected); s.has(t) ? s.delete(t) : s.add(t); setSelected(s) }
  const save = async () => {
    setSaving(true)
    try {
      for (const t of selected) if (!original.has(t)) await cat({ mode: 'save_tag', object_key: objectKey, tag: t, user, remove: false })
      for (const t of original) if (!selected.has(t)) await cat({ mode: 'save_tag', object_key: objectKey, tag: t, user, remove: true })
      qc.invalidateQueries({ queryKey: ['get_tags', objectKey] })
      qc.invalidateQueries({ queryKey: ['asset_detail'] })
      onClose()
    } finally { setSaving(false) }
  }
  return (
    <Modal open onClose={onClose} title="Classificar objeto" size="md">
      <div className="text-xs text-dim mb-3 font-mono break-all">{objectKey}</div>
      <div className="flex flex-col gap-2">
        {TAG_OPTIONS.map(t => (
          <label key={t} className="flex items-center gap-2 text-sm text-ink cursor-pointer">
            <input type="checkbox" checked={selected.has(t)} onChange={() => toggle(t)} />
            <TagChip tag={t} />
          </label>
        ))}
        <div className="flex justify-end gap-2 mt-3">
          <Button variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button onClick={save} loading={saving}>Salvar</Button>
        </div>
      </div>
    </Modal>
  )
}

// ════════════════════════════════════════════════════════════════════════════
// Card de pipeline (resultado de busca) com ownership inline
// ════════════════════════════════════════════════════════════════════════════

function DirBadge({ dir }: { dir: string }) {
  const isOrigem = dir === 'origem'
  return <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded ${isOrigem ? 'bg-[#185FA5]/10 text-[#185FA5]' : 'bg-[#27500A]/10 text-[#27500A] dark:text-[#86c98f]'}`}>{isOrigem ? '← origem' : '→ destino'}</span>
}

function PipelineResultCard({ p, defaultOpen, canEdit, onCols, onTag, onFileLineage, onHistory, onOwner, onGoLineage, forceOpen }: {
  p: SearchPipeline
  defaultOpen: boolean
  canEdit: boolean
  onCols: (cols: string[]) => void
  onTag: (key: string) => void
  onFileLineage: (file: string) => void
  onHistory: (pipeline: string) => void
  onOwner: (pipeline: string) => void
  onGoLineage: (pipeline: string) => void
  forceOpen: boolean | null
}) {
  const [open, setOpen] = useState(defaultOpen)
  useEffect(() => { if (forceOpen !== null) setOpen(forceOpen) }, [forceOpen])

  const { data: owner } = useQuery<{ owner_name?: string; steward_name?: string }>({
    queryKey: ['get_owner', p.pipeline_name],
    queryFn: () => cat({ mode: 'get_owner', pipeline_name: p.pipeline_name }),
  })
  const ownerParts: string[] = []
  if (owner?.owner_name) ownerParts.push(`Owner: ${owner.owner_name}`)
  if (owner?.steward_name) ownerParts.push(`Steward: ${owner.steward_name}`)

  return (
    <div className="border border-edge rounded-xl overflow-hidden">
      <div className="flex items-center gap-2 px-4 py-2.5 cursor-pointer bg-canvas select-none" onClick={() => setOpen(o => !o)}>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-mono text-sm font-semibold text-ink">{p.pipeline_name}</span>
            <span className={`text-[10px] px-1.5 py-0.5 rounded ${p.active ? 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300' : 'bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400'}`}>{p.active ? 'Ativo' : 'Inativo'}</span>
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-edge/60 text-dim">{p.project_name}</span>
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-edge/40 text-dim">{p.domain}</span>
          </div>
          <div className="text-[11px] text-dim mt-0.5">{p.ocorrencias} ocorrência(s)</div>
        </div>
        <button onClick={e => { e.stopPropagation(); onHistory(p.pipeline_name) }} className="text-[10px] flex items-center gap-1 px-2 py-1 rounded border border-edge text-dim hover:text-ink"><History size={11} /> Histórico</button>
        <button onClick={e => { e.stopPropagation(); onGoLineage(p.pipeline_name) }} className="text-[10px] flex items-center gap-1 px-2 py-1 rounded border border-[#1A5FA8] bg-[#1A5FA8]/10 text-[#1A5FA8]"><ArrowRight size={11} /> Lineage</button>
        {open ? <ChevronUp size={14} className="text-dim" /> : <ChevronDown size={14} className="text-dim" />}
      </div>

      {open && (
        <div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-left text-dim bg-canvas border-y border-edge">
                  <th className="py-1.5 px-2 w-12">Ord.</th><th className="px-2">Job</th><th className="px-2">Direção</th>
                  <th className="px-2">Objeto / Arquivo</th><th className="px-2">Campos</th>{canEdit && <th className="px-2 w-10"></th>}
                </tr>
              </thead>
              <tbody>
                {p.jobs.map((j, i) => {
                  const cols = Array.isArray(j.columns) ? j.columns : []
                  const hasFile = !!j.file_path
                  const objKey = hasFile ? j.file_path! : `${j.database_name ? j.database_name + '.' : ''}${j.object_name ?? ''}`
                  return (
                    <tr key={i} className="border-b border-edge/40">
                      <td className="py-1.5 px-2 text-center font-bold text-dim">#{j.execution_order}</td>
                      <td className="px-2 font-mono truncate max-w-[160px]">{j.job_name}</td>
                      <td className="px-2"><DirBadge dir={j.direction} /></td>
                      <td className="px-2">
                        {hasFile ? (
                          <div className="flex items-center gap-1.5">
                            <span className="font-mono text-[11px] truncate max-w-[200px]">{j.file_path}</span>
                            <button onClick={() => onFileLineage(j.file_path!)} className="text-[10px] flex items-center gap-0.5 px-1 rounded border border-edge text-dim hover:text-ink whitespace-nowrap" title="Ver quem lê e grava"><FileText size={10} /> Linhagem</button>
                          </div>
                        ) : (
                          <span><span className="text-ink">{j.object_name || '—'}</span> {j.database_name && <span className="text-dim font-semibold">{j.database_name}</span>}</span>
                        )}
                      </td>
                      <td className="px-2">
                        {cols.length > 0 && (
                          <button onClick={() => onCols(cols)} className="text-[10px] px-1.5 py-0.5 rounded-full bg-orange-100 dark:bg-orange-900/40 text-orange-600 border border-orange-300">⊞ {cols.length} campo(s)</button>
                        )}
                      </td>
                      {canEdit && (
                        <td className="px-2">
                          <button onClick={() => onTag(objKey)} title="Classificar objeto" className="text-dim hover:text-ink"><Tag size={12} /></button>
                        </td>
                      )}
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          {/* Ownership inline */}
          <div className="flex items-center gap-2 px-4 py-2 bg-canvas border-t border-edge flex-wrap">
            <span className="text-[10px] font-semibold uppercase tracking-wider text-dim">Responsável:</span>
            <span className="text-[11px] text-dim">{ownerParts.length ? ownerParts.join(' · ') : '—'}</span>
            {canEdit && <button onClick={() => onOwner(p.pipeline_name)} className="text-[10px] flex items-center gap-1 px-2 py-0.5 rounded border border-edge text-dim hover:text-ink ml-auto"><Pencil size={10} /> Editar</button>}
          </div>
        </div>
      )}
    </div>
  )
}

// ════════════════════════════════════════════════════════════════════════════
// Aba CATÁLOGO
// ════════════════════════════════════════════════════════════════════════════

function CatalogoTab({ onGoLineage }: { onGoLineage: (pipeline: string) => void }) {
  const { user, isAdmin } = useAuthStore()
  const canEdit = isAdmin() || !!user?.permissoes?.includes('acao_editar')
  const userName = user?.matricula ?? 'sistema'

  const [subtab, setSubtab] = useState('overview')
  const [assetModal, setAssetModal] = useState<{ name: string; type: string; db: string } | null>(null)
  const [colsModal, setColsModal] = useState<string[] | null>(null)
  const [tagKey, setTagKey] = useState<string | null>(null)
  const [fileLineage, setFileLineage] = useState<string | null>(null)
  const [history, setHistory] = useState<string | null>(null)
  const [ownerPipe, setOwnerPipe] = useState<string | null>(null)
  const [recent, setRecent] = useState<RecentItem[]>(readRecent())
  const [uniSearch, setUniSearch] = useState('')
  const [exploreClass, setExploreClass] = useState('')

  const openAsset = (name: string, type: string, db: string) => {
    pushRecent(name, type, db); setRecent(readRecent()); setAssetModal({ name, type, db })
  }

  return (
    <div className="flex flex-col gap-4">
      {/* Busca universal */}
      <UniversalSearch onSearch={(val) => { setUniSearch(val); setSubtab('pipelines') }} />

      <Tabs
        size="sm"
        active={subtab}
        onChange={setSubtab}
        tabs={[
          { id: 'overview', label: 'Visão Geral' },
          { id: 'explore', label: 'Explorar' },
          { id: 'list', label: 'Tabelas & Arquivos' },
          { id: 'pipelines', label: 'Pipelines' },
        ]}
      />

      {subtab === 'overview' && <OverviewPanel onOpenAsset={openAsset} recent={recent} onGoExplore={(c) => { setExploreClass(c); setSubtab('explore') }} />}
      {subtab === 'explore' && <ExplorePanel onOpenAsset={openAsset} initialClass={exploreClass} />}
      {subtab === 'list' && <ListPanel onOpenAsset={openAsset} />}
      {subtab === 'pipelines' && (
        <PipelinesPanel
          key={uniSearch}
          canEdit={canEdit}
          initial={uniSearch}
          onCols={setColsModal} onTag={setTagKey} onFileLineage={setFileLineage}
          onHistory={setHistory} onOwner={setOwnerPipe} onGoLineage={onGoLineage}
        />
      )}

      {assetModal && <AssetDetailModal asset={assetModal} onClose={() => setAssetModal(null)} onGoLineage={(p) => { setAssetModal(null); onGoLineage(p) }} />}
      {colsModal && <ListModal title={`Campos (${colsModal.length})`} items={colsModal} onClose={() => setColsModal(null)} />}
      {tagKey && <TagModal objectKey={tagKey} user={userName} onClose={() => setTagKey(null)} />}
      {fileLineage && <FileLineageModal file={fileLineage} onClose={() => setFileLineage(null)} onGoLineage={(p) => { setFileLineage(null); onGoLineage(p) }} />}
      {history && <HistoryModal pipeline={history} onClose={() => setHistory(null)} />}
      {ownerPipe && <OwnerModal pipeline={ownerPipe} user={userName} onClose={() => setOwnerPipe(null)} />}
    </div>
  )
}

// ── Visão Geral ──────────────────────────────────────────────────────────────

function OverviewPanel({ onOpenAsset, recent, onGoExplore }: {
  onOpenAsset: (name: string, type: string, db: string) => void
  recent: RecentItem[]
  onGoExplore: (cls: string) => void
}) {
  const { data, isLoading } = useQuery<OverviewResponse>({ queryKey: ['cat_overview'], queryFn: () => cat({ mode: 'overview' }) })
  if (isLoading) return <PageSpinner />
  if (!data) return null

  const kpis = [
    { label: 'Objetos', value: data.total_assets, color: 'text-[#1A5FA8]', onClick: undefined as (() => void) | undefined },
    { label: 'Pipelines', value: data.total_pipelines, color: 'text-[#1A5FA8]', onClick: undefined },
    { label: 'Com owner', value: `${data.total_with_owner} / ${data.total_pipelines}`, color: 'text-green-600', onClick: undefined },
    { label: 'PII', value: data.classification_counts.pii, color: 'text-red-600', onClick: () => onGoExplore('PII') },
    { label: 'Regulado', value: data.classification_counts.regulado, color: 'text-purple-600', onClick: () => onGoExplore('Regulado') },
    { label: 'Confidencial', value: data.classification_counts.confidencial, color: 'text-orange-600', onClick: () => onGoExplore('Confidencial') },
  ]

  return (
    <div className="flex flex-col gap-5">
      {/* KPIs */}
      <div className="grid gap-2" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))' }}>
        {kpis.map(k => (
          <div key={k.label} onClick={k.onClick}
            className={`border border-edge rounded-lg px-3 py-2.5 ${k.onClick ? 'cursor-pointer hover:shadow-md' : ''} transition-shadow bg-panel`}>
            <div className="text-[11px] font-semibold uppercase tracking-wider text-dim mb-1">{k.label}</div>
            <div className={`text-xl font-bold ${k.color}`}>{k.value}</div>
          </div>
        ))}
      </div>

      <div className="grid gap-5 md:grid-cols-3">
        {/* Top assets */}
        <div className="md:col-span-2">
          <div className="text-xs font-semibold text-dim uppercase tracking-wider mb-2">Ativos mais utilizados</div>
          <div className="grid gap-2" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))' }}>
            {data.top_assets.length ? data.top_assets.map((a, i) => (
              <div key={i} onClick={() => onOpenAsset(a.asset_name, a.asset_type, a.database_name || '')}
                className="border border-edge rounded-lg px-3 py-2 cursor-pointer hover:bg-canvas">
                <div className="font-mono text-[11px] font-semibold text-ink truncate" title={a.asset_name}>{a.asset_name}</div>
                <div className="flex justify-between text-[10px] text-dim mt-0.5">
                  <span>{a.asset_type === 'arquivo' ? '◈ Arquivo' : `◫ ${a.database_name || 'ODBC'}`}</span>
                  <span className="font-semibold text-[#1A5FA8]">{a.pipeline_count} pipeline(s)</span>
                </div>
              </div>
            )) : <div className="text-xs text-dim">Nenhum dado encontrado.</div>}
          </div>
        </div>

        {/* Recentes + alertas */}
        <div className="flex flex-col gap-4">
          <div>
            <div className="text-xs font-semibold text-dim uppercase tracking-wider mb-2">Vistos recentemente</div>
            <div className="flex flex-col gap-0.5">
              {recent.length ? recent.map((x, i) => (
                <div key={i} onClick={() => onOpenAsset(x.name, x.type, x.dbName)}
                  className="flex items-center gap-1.5 px-2 py-1 rounded cursor-pointer hover:bg-canvas text-[11px]">
                  <span className="text-dim">{x.type === 'arquivo' ? '◈' : '◫'}</span>
                  <span className="font-mono truncate text-ink" title={x.name}>{x.name}</span>
                </div>
              )) : <div className="text-[11px] text-dim">—</div>}
            </div>
          </div>
          <div>
            <div className="text-xs font-semibold text-dim uppercase tracking-wider mb-2">Alertas</div>
            <div className="flex flex-col gap-1">
              {data.alerts.length ? data.alerts.map((a, i) => (
                <div key={i} className={`text-[11px] px-2 py-1 border-l-2 ${a.type.includes('pii') ? 'border-red-500' : 'border-amber-500'} text-ink`}>{a.message}</div>
              )) : <div className="text-[11px] text-dim">Nenhum alerta.</div>}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

// ── Explorar ───────────────────────────────────────────────────────────────

function useBrowse() {
  return useQuery<BrowseResponse>({ queryKey: ['cat_browse'], queryFn: () => cat({ mode: 'browse', top_n: 200 }), staleTime: 2 * 60_000 })
}

function ExplorePanel({ onOpenAsset, initialClass }: { onOpenAsset: (n: string, t: string, db: string) => void; initialClass: string }) {
  const { data, isLoading } = useBrowse()
  const [type, setType] = useState('')
  const [db, setDb] = useState('')
  const [cls, setCls] = useState(initialClass)
  const [q, setQ] = useState('')
  useEffect(() => { setCls(initialClass) }, [initialClass])

  // Para filtrar por classificação precisamos rebuscar no servidor (browse com classification)
  const { data: clsData } = useQuery<BrowseResponse>({
    queryKey: ['cat_browse_cls', cls],
    queryFn: () => cat({ mode: 'browse', top_n: 200, classification: cls }),
    enabled: !!cls,
  })

  const base = cls ? (clsData?.assets ?? []) : (data?.assets ?? [])
  const assets = base.filter(a =>
    (!type || a.asset_type === type) &&
    (!db || a.database_name === db) &&
    (!q || a.asset_name.toLowerCase().includes(q.toLowerCase()))
  )

  if (isLoading) return <PageSpinner />

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap gap-2 items-center">
        <input value={q} onChange={e => setQ(e.target.value)} placeholder="Buscar objeto…" className={`${inputCls} w-56`} />
        <select value={type} onChange={e => setType(e.target.value)} className={`${inputCls} w-36`}>
          <option value="">Todos os tipos</option>
          <option value="tabela">Tabela</option>
          <option value="arquivo">Arquivo</option>
        </select>
        <select value={db} onChange={e => setDb(e.target.value)} className={`${inputCls} w-44`}>
          <option value="">Todos os bancos</option>
          {(data?.facets.databases ?? []).map(d => <option key={d} value={d}>{d}</option>)}
        </select>
        <select value={cls} onChange={e => setCls(e.target.value)} className={`${inputCls} w-44`}>
          <option value="">Toda classificação</option>
          {TAG_OPTIONS.map(t => <option key={t} value={t}>{t}</option>)}
        </select>
        <span className="text-xs text-dim">{assets.length} objeto(s)</span>
      </div>
      <div className="grid gap-2" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))' }}>
        {assets.length ? assets.map((a, i) => (
          <div key={i} onClick={() => onOpenAsset(a.asset_name, a.asset_type, a.database_name || '')}
            className="border border-edge rounded-lg px-3 py-2 cursor-pointer hover:bg-canvas">
            <div className="font-mono text-[11px] font-semibold text-ink truncate" title={a.asset_name}>{a.asset_name}</div>
            <div className="flex justify-between text-[10px] text-dim mt-0.5">
              <span>{a.asset_type === 'arquivo' ? '◈ Arquivo' : `◫ ${a.database_name || 'ODBC'}`}</span>
              <span className="font-semibold">{a.pipeline_count}p</span>
            </div>
          </div>
        )) : <div className="text-xs text-dim p-2">Nenhum objeto encontrado.</div>}
      </div>
    </div>
  )
}

// ── Tabelas & Arquivos ───────────────────────────────────────────────────────

function ListPanel({ onOpenAsset }: { onOpenAsset: (n: string, t: string, db: string) => void }) {
  const { data, isLoading } = useBrowse()
  const [q, setQ] = useState('')
  const [type, setType] = useState('')
  const [sort, setSort] = useState<'pipeline_count' | 'asset_name' | 'as_origem' | 'as_destino'>('pipeline_count')

  const rows = useMemo(() => {
    let r = (data?.assets ?? []).filter(a =>
      (!q || a.asset_name.toLowerCase().includes(q.toLowerCase())) && (!type || a.asset_type === type))
    r = [...r].sort((a, b) => sort === 'asset_name' ? a.asset_name.localeCompare(b.asset_name) : (b[sort] || 0) - (a[sort] || 0))
    return r
  }, [data, q, type, sort])

  const exportCsv = () => {
    if (!rows.length) return
    const head = ['objeto', 'tipo', 'banco', 'como_origem', 'como_destino', 'pipelines']
    const lines = [head, ...rows.map(a => [a.asset_name, a.asset_type, a.database_name || '', a.as_origem || 0, a.as_destino || 0, a.pipeline_count || 0])]
    const csv = lines.map(r => r.map(v => `"${String(v).replace(/"/g, '""')}"`).join(',')).join('\r\n')
    const link = document.createElement('a')
    link.href = 'data:text/csv;charset=utf-8,' + encodeURIComponent(csv)
    link.download = `catalogo_objetos_${new Date().toISOString().slice(0, 10)}.csv`
    link.click()
  }

  if (isLoading) return <PageSpinner />

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap gap-2 items-center">
        <input value={q} onChange={e => setQ(e.target.value)} placeholder="Buscar nome…" className={`${inputCls} w-56`} />
        <select value={type} onChange={e => setType(e.target.value)} className={`${inputCls} w-36`}>
          <option value="">Todos os tipos</option>
          <option value="tabela">Tabela</option>
          <option value="arquivo">Arquivo</option>
        </select>
        <select value={sort} onChange={e => setSort(e.target.value as typeof sort)} className={`${inputCls} w-44`}>
          <option value="pipeline_count">Mais usados</option>
          <option value="asset_name">A → Z</option>
          <option value="as_origem">Origens</option>
          <option value="as_destino">Destinos</option>
        </select>
        <span className="text-xs text-dim">{rows.length} objeto(s)</span>
        <Button variant="secondary" size="sm" className="ml-auto" onClick={exportCsv}><Download size={13} /> Exportar CSV</Button>
      </div>
      <div className="border border-edge rounded-lg overflow-hidden overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-left text-dim bg-canvas border-b border-edge">
              <th className="py-2 px-3">Objeto</th><th className="px-2 w-20">Tipo</th><th className="px-2">Banco / Caminho</th>
              <th className="px-2 w-16 text-center">Origem</th><th className="px-2 w-16 text-center">Destino</th><th className="px-2 w-20 text-center">Pipelines</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((a, i) => (
              <tr key={i} onClick={() => onOpenAsset(a.asset_name, a.asset_type, a.database_name || '')} className="border-b border-edge/40 cursor-pointer hover:bg-canvas">
                <td className="py-1.5 px-3 font-mono text-[11px] truncate max-w-[280px]" title={a.asset_name}>{a.asset_name}</td>
                <td className="px-2 text-[10px] text-dim">{a.asset_type === 'arquivo' ? '◈ Arq' : '◫ Tab'}</td>
                <td className="px-2 text-[10px] text-dim truncate max-w-[160px]">{a.database_name || (a.asset_type === 'arquivo' ? a.asset_name : '')}</td>
                <td className="px-2 text-center font-semibold text-[#185FA5]">{a.as_origem || 0}</td>
                <td className="px-2 text-center font-semibold text-[#27500A] dark:text-[#86c98f]">{a.as_destino || 0}</td>
                <td className="px-2 text-center font-bold text-ink">{a.pipeline_count || 0}</td>
              </tr>
            ))}
            {!rows.length && <tr><td colSpan={6} className="p-3 text-xs text-dim">Nenhum resultado.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ── Pipelines (busca + impacto) ──────────────────────────────────────────────

function PipelinesPanel({ canEdit, initial, onCols, onTag, onFileLineage, onHistory, onOwner, onGoLineage }: {
  canEdit: boolean
  initial: string
  onCols: (c: string[]) => void
  onTag: (k: string) => void
  onFileLineage: (f: string) => void
  onHistory: (p: string) => void
  onOwner: (p: string) => void
  onGoLineage: (p: string) => void
}) {
  const [searchType, setSearchType] = useState<'tabela' | 'arquivo'>(initial && smartIsArquivo(initial) ? 'arquivo' : 'tabela')
  const [objectName, setObjectName] = useState(initial && !smartIsArquivo(initial) ? initial : '')
  const [fileName, setFileName] = useState(initial && smartIsArquivo(initial) ? initial : '')
  const [direction, setDirection] = useState('all')
  const [database, setDatabase] = useState('')
  const [query, setQuery] = useState<object | null>(initial ? buildInitial(initial) : null)
  const [impacto, setImpacto] = useState(false)
  const [forceOpen, setForceOpen] = useState<boolean | null>(null)

  function buildInitial(val: string): object {
    return smartIsArquivo(val)
      ? { mode: 'search', search_type: 'arquivo', file_name: val, direction: 'all' }
      : { mode: 'search', search_type: 'tabela', object_name: val, direction: 'all' }
  }

  const { data, isLoading, isFetching } = useQuery<SearchResponse>({
    queryKey: ['cat_search', query],
    queryFn: () => cat(query!),
    enabled: !!query,
  })

  const run = (imp: boolean) => {
    setImpacto(imp)
    if (imp) {
      // Impacto: igual ao legado — sempre tabela, direção origem (quem lê a tabela).
      if (!objectName.trim()) return
      setSearchType('tabela')
      setQuery({ mode: 'search', search_type: 'tabela', object_name: objectName.trim(), direction: 'origem', database_name: database.trim() })
    } else if (searchType === 'arquivo') {
      if (!fileName.trim()) return
      setQuery({ mode: 'search', search_type: 'arquivo', file_name: fileName.trim(), direction })
    } else {
      if (!objectName.trim()) return
      setQuery({ mode: 'search', search_type: 'tabela', object_name: objectName.trim(), direction, database_name: database.trim() })
    }
  }

  // No modo impacto o legado filtra pipelines inativos e recalcula os totais.
  const rawPipelines = data?.pipelines ?? []
  const pipelines = impacto ? rawPipelines.filter(p => p.active) : rawPipelines
  const totalPipelines = impacto ? pipelines.length : (data?.total_pipelines ?? 0)
  const totalOcorrencias = impacto ? pipelines.reduce((s, p) => s + p.ocorrencias, 0) : (data?.total_ocorrencias ?? 0)
  const leitores = pipelines.filter(p => p.jobs.some(j => j.direction === 'origem')).length
  const gravadores = pipelines.filter(p => p.jobs.some(j => j.direction === 'destino')).length

  const exportCsv = () => {
    if (!pipelines.length) return
    const head = ['pipeline', 'project', 'domain', 'active', 'job', 'direction', 'object', 'database', 'file_path', 'campos']
    const lines: (string | number)[][] = [head]
    pipelines.forEach(p => p.jobs.forEach(j => lines.push([
      p.pipeline_name, p.project_name, p.domain, p.active ? 'Ativo' : 'Inativo',
      j.job_name, j.direction, j.object_name || '', j.database_name || '', j.file_path || '',
      Array.isArray(j.columns) ? j.columns.join('; ') : '',
    ])))
    const csv = lines.map(r => r.map(v => `"${String(v).replace(/"/g, '""')}"`).join(',')).join('\r\n')
    const a = document.createElement('a')
    a.href = 'data:text/csv;charset=utf-8,' + encodeURIComponent(csv)
    a.download = `catalogo_${data?.term || 'export'}_${new Date().toISOString().slice(0, 10)}.csv`
    a.click()
  }

  return (
    <div className="flex flex-col gap-3">
      {/* Sub-tabs tipo */}
      <div className="flex gap-1">
        <button onClick={() => setSearchType('tabela')} className={`px-3 py-1.5 rounded-md text-sm font-medium flex items-center gap-1 ${searchType === 'tabela' ? 'bg-[#1A5FA8] text-white' : 'border border-edge bg-canvas text-dim hover:text-ink'}`}><Database size={13} /> Tabela / Banco</button>
        <button onClick={() => setSearchType('arquivo')} className={`px-3 py-1.5 rounded-md text-sm font-medium flex items-center gap-1 ${searchType === 'arquivo' ? 'bg-[#1A5FA8] text-white' : 'border border-edge bg-canvas text-dim hover:text-ink'}`}><FileText size={13} /> Arquivo</button>
      </div>

      {/* Campos de busca */}
      <div className="flex flex-wrap gap-2 items-center">
        {searchType === 'arquivo' ? (
          <input value={fileName} onChange={e => setFileName(e.target.value)} onKeyDown={e => e.key === 'Enter' && run(false)} placeholder="Nome do arquivo…" className={`${inputCls} w-64`} />
        ) : (
          <input value={objectName} onChange={e => setObjectName(e.target.value)} onKeyDown={e => e.key === 'Enter' && run(false)} placeholder="Nome da tabela / objeto…" className={`${inputCls} w-64`} />
        )}
        <select value={direction} onChange={e => setDirection(e.target.value)} className={`${inputCls} w-36`}>
          <option value="all">Origem e destino</option>
          <option value="origem">Só origem</option>
          <option value="destino">Só destino</option>
        </select>
        {searchType === 'tabela' && (
          <input value={database} onChange={e => setDatabase(e.target.value)} placeholder="Banco (opcional)" className={`${inputCls} w-40`} />
        )}
        <Button onClick={() => run(false)} loading={isFetching && !impacto}><Search size={13} /> Buscar</Button>
        <Button variant="secondary" onClick={() => run(true)} loading={isFetching && impacto}><Zap size={13} /> Impacto</Button>
      </div>

      {/* Status */}
      {data && (
        <div className="text-xs text-dim">
          {impacto ? '⚡ Análise de impacto' : 'Busca'}: "{data.term}" — {totalPipelines} pipeline(s) · {totalOcorrencias} ocorrência(s)
        </div>
      )}

      {isLoading ? <PageSpinner /> : data && pipelines.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-12 text-center">
          <Database size={36} className="text-dim mb-2" />
          <p className="font-semibold text-ink">Nenhum pipeline encontrado</p>
          <p className="text-sm text-dim mt-1">Tente outro termo ou verifique se o lineage foi importado.</p>
        </div>
      ) : pipelines.length > 0 ? (
        <>
          {/* Banner de impacto */}
          {impacto && (
            <div className="flex gap-2 flex-wrap">
              {leitores > 0 && <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-orange-100 dark:bg-orange-900/30 border border-orange-300 dark:border-orange-800 text-orange-700 dark:text-orange-300 text-xs"><strong>{leitores}</strong> pipeline(s) <strong>leem</strong> como origem →</div>}
              {gravadores > 0 && <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-100 dark:bg-blue-900/30 border border-blue-300 dark:border-blue-800 text-blue-700 dark:text-blue-300 text-xs"><strong>{gravadores}</strong> pipeline(s) <strong>gravam</strong> como destino →</div>}
            </div>
          )}
          {/* Toolbar */}
          <div className="flex items-center justify-between gap-2 flex-wrap">
            <div className="flex gap-1">
              <Button variant="secondary" size="sm" onClick={() => setForceOpen(o => o === true ? null : true)}>▼ Expandir todos</Button>
              <Button variant="secondary" size="sm" onClick={() => setForceOpen(o => o === false ? null : false)}>▲ Recolher todos</Button>
            </div>
            <Button variant="secondary" size="sm" onClick={exportCsv}><Download size={13} /> Exportar CSV</Button>
          </div>
          {/* Cards */}
          <div className="flex flex-col gap-2">
            {pipelines.map((p, pi) => (
              <PipelineResultCard
                key={p.pipeline_name}
                p={p}
                defaultOpen={pi < 3}
                forceOpen={forceOpen}
                canEdit={canEdit}
                onCols={onCols} onTag={onTag} onFileLineage={onFileLineage}
                onHistory={onHistory} onOwner={onOwner} onGoLineage={onGoLineage}
              />
            ))}
          </div>
        </>
      ) : (
        <div className="text-sm text-dim py-8 text-center">Informe um objeto ou arquivo e clique em Buscar.</div>
      )}
    </div>
  )
}

// ── Busca universal ───────────────────────────────────────────────────────────

function UniversalSearch({ onSearch }: { onSearch: (val: string) => void }) {
  const [val, setVal] = useState('')
  const hint = val ? (smartIsArquivo(val) ? '◈ Detectado como arquivo' : '◫ Detectado como tabela/banco') : ''
  return (
    <div className="flex flex-col gap-1">
      <div className="flex gap-2 items-center">
        <input value={val} onChange={e => setVal(e.target.value)} onKeyDown={e => { if (e.key === 'Enter' && val.trim()) onSearch(val.trim().toUpperCase()) }}
          placeholder="Busca universal: tabela, banco ou arquivo…" className={`${inputCls} flex-1`} />
        <Button onClick={() => val.trim() && onSearch(val.trim().toUpperCase())}><Search size={13} /> Buscar</Button>
      </div>
      {hint && <span className="text-[11px] text-dim">{hint}</span>}
    </div>
  )
}

// ════════════════════════════════════════════════════════════════════════════
// Página raiz
// ════════════════════════════════════════════════════════════════════════════

export default function Governanca() {
  const [tab, setTab] = useState('lineage')
  const [pipeline, setPipeline] = useState('')

  const goLineage = (p: string) => { setPipeline(p); setTab('lineage') }

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-xl font-bold text-ink">Governança</h1>
      <p className="text-sm text-dim -mt-2">Lineage de pipelines e catálogo de dados</p>
      <InfoBanner icon="◈" storageKey="governanca">
        <strong>Governança de dados:</strong> consulte a <strong>linhagem (lineage)</strong> de cada pipeline — as
        tabelas, views e arquivos consumidos (origens) e produzidos (destinos) por seus jobs — e navegue pelo{' '}
        <strong>catálogo de dados</strong> para descobrir onde cada objeto é usado, com rastreabilidade de impacto
        entre pipelines.
      </InfoBanner>
      <Tabs
        active={tab}
        onChange={setTab}
        tabs={[{ id: 'lineage', label: 'Lineage' }, { id: 'catalogo', label: 'Catálogo de Dados' }]}
      />
      <div>
        {tab === 'lineage'
          ? <LineageTab pipeline={pipeline} setPipeline={setPipeline} />
          : <CatalogoTab onGoLineage={goLineage} />}
      </div>
    </div>
  )
}
