import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '../lib/api'
import { queryClient } from '../lib/queryClient'
import { Card, KpiCard } from '../components/ui/Card'
import { Input, Select } from '../components/ui/Input'
import { Button } from '../components/ui/Button'
import { Spinner } from '../components/ui/Spinner'
import { Modal } from '../components/ui/Modal'
import { toast } from '../components/ui/Toast'
import { Search, Download, FileSearch, ChevronDown, ChevronRight, ListPlus } from 'lucide-react'

// ── Tipos do retorno de /lineage/field-impact ────────────────────
interface MatchedColumn {
  name: string
  sql_type: number | null
  type_name: string | null
  precision: number | null
  scale: number | null
  nullable: boolean | null
}
interface Ocorrencia {
  stage_name: string | null
  direction: string | null
  object_name: string | null
  object_type: string | null
  stage_type_raw: string | null
  database_name: string | null
  detalhe: string | null
  matched_columns: MatchedColumn[]
  total_columns: number
}
interface JobImpact { job_name: string; category?: string; ocorrencias: Ocorrencia[] }
interface FieldImpactResult {
  sucesso: boolean
  project_name: string
  dsx_file: string
  termo: string
  exato: boolean
  filtro_tipos: string[]
  filtro_excluir: boolean
  incluir_bkp: boolean
  incluir_copy: boolean
  jobs_bkp_ignorados: number
  jobs_copy_ignorados: number
  total_jobs_dsx: number
  total_jobs_impactados: number
  total_ocorrencias: number
  jobs: JobImpact[]
}
interface PlanoLite { id: number; nome: string; status: string }

// ── Presets de filtro de datatype ─────────────────────────────────
const TEXT_TYPES = 'VARCHAR,CHAR,LONGVARCHAR,NVARCHAR,NCHAR'
const NUM_TYPES = 'INTEGER,BIGINT,SMALLINT,TINYINT,DECIMAL,NUMERIC,FLOAT,REAL,DOUBLE,BIT'
const TIPO_PRESETS: { key: string; label: string; tipo: string; excluir: boolean }[] = [
  { key: 'all',    label: 'Qualquer tipo',              tipo: '',          excluir: false },
  { key: 'naotxt', label: '≠ Texto (≠ VARCHAR/CHAR)',    tipo: TEXT_TYPES,  excluir: true  },
  { key: 'num',    label: 'Numéricos (INT/DECIMAL/…)',   tipo: NUM_TYPES,   excluir: false },
  { key: 'txt',    label: 'Apenas texto (VARCHAR/CHAR)', tipo: TEXT_TYPES,  excluir: false },
  { key: 'datas',  label: 'Datas (DATE/TIMESTAMP)',      tipo: 'DATE,TIME,TIMESTAMP', excluir: false },
]

// ── Categoria/cor do datatype ─────────────────────────────────────
const NUM_SET = new Set(NUM_TYPES.split(','))
const TXT_SET = new Set(TEXT_TYPES.split(','))
const DATE_SET = new Set(['DATE', 'TIME', 'TIMESTAMP'])
function typeCls(t: string | null): string {
  const k = (t ?? '').toUpperCase()
  if (NUM_SET.has(k)) return 'bg-amber-100 text-amber-800 border-amber-300 dark:bg-yellow-900/40 dark:text-yellow-300 dark:border-yellow-800'
  if (TXT_SET.has(k)) return 'bg-blue-100 text-blue-700 border-blue-300 dark:bg-blue-900/40 dark:text-blue-300 dark:border-blue-800'
  if (DATE_SET.has(k)) return 'bg-purple-100 text-purple-700 border-purple-300 dark:bg-purple-900/40 dark:text-purple-300 dark:border-purple-800'
  return 'bg-slate-100 text-slate-600 border-slate-300 dark:bg-gray-800 dark:text-gray-400 dark:border-gray-700'
}
function typeLabel(c: MatchedColumn): string {
  if (!c.type_name) return '?'
  const showPrec = c.precision && c.precision > 0 && (TXT_SET.has(c.type_name) || c.type_name === 'DECIMAL' || c.type_name === 'NUMERIC')
  return showPrec ? `${c.type_name}(${c.precision}${c.scale ? `,${c.scale}` : ''})` : c.type_name
}

// Rótulo curto do filtro de tipo aplicado (evita estourar o KPI card)
function filtroNome(r: FieldImpactResult): string {
  if (!r.filtro_tipos.length) return 'nenhum'
  const s = new Set(r.filtro_tipos)
  const eqSet = (o: Set<string>) => o.size === s.size && [...o].every((x) => s.has(x))
  if (eqSet(TXT_SET)) return r.filtro_excluir ? '≠ Texto' : 'Texto'
  if (eqSet(NUM_SET)) return r.filtro_excluir ? '≠ Num.' : 'Numéricos'
  if (eqSet(DATE_SET)) return r.filtro_excluir ? '≠ Datas' : 'Datas'
  return `${r.filtro_excluir ? '≠' : '='} ${r.filtro_tipos.length} tipos`
}

// ── Direção do stage ──────────────────────────────────────────────
const DIR_LABEL: Record<string, string> = { origem: 'Origem', destino: 'Destino', transformacao: 'Transformação' }
const DIR_CLS: Record<string, string> = {
  origem:        'bg-blue-100 text-blue-700 border-blue-300 dark:bg-blue-900/40 dark:text-blue-300 dark:border-blue-800',
  destino:       'bg-green-100 text-green-700 border-green-300 dark:bg-green-900/40 dark:text-green-300 dark:border-green-800',
  transformacao: 'bg-amber-100 text-amber-700 border-amber-300 dark:bg-yellow-900/40 dark:text-yellow-300 dark:border-yellow-800',
}
function DirBadge({ dir }: { dir: string | null }) {
  const k = (dir ?? '').toLowerCase()
  const cls = DIR_CLS[k] ?? 'bg-slate-100 text-slate-600 border-slate-300 dark:bg-gray-800 dark:text-gray-400 dark:border-gray-700'
  return <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium whitespace-nowrap border ${cls}`}>{DIR_LABEL[k] ?? (dir || '—')}</span>
}

function HighlightCol({ name, termo }: { name: string; termo: string }) {
  const i = termo ? name.toLowerCase().indexOf(termo.toLowerCase()) : -1
  if (i < 0) return <>{name}</>
  return (
    <>
      {name.slice(0, i)}
      <mark className="bg-yellow-300 text-slate-900 rounded px-0.5">{name.slice(i, i + termo.length)}</mark>
      {name.slice(i + termo.length)}
    </>
  )
}

const selKey = (job: string, stage: string | null, col: string) => `${job}␟${stage ?? ''}␟${col}`

// ── CSV ───────────────────────────────────────────────────────────
function toCsv(r: FieldImpactResult): string {
  const head = ['dsx', 'job', 'direcao', 'stage', 'stage_type', 'objeto', 'base', 'coluna', 'datatype', 'precision', 'scale', 'nullable', 'detalhe']
  const esc = (v: unknown) => {
    const s = v == null ? '' : String(v)
    return /[",;\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
  }
  const lines = [head.join(';')]
  for (const job of r.jobs) for (const o of job.ocorrencias) for (const c of o.matched_columns) {
    lines.push([r.dsx_file, job.job_name, DIR_LABEL[(o.direction ?? '').toLowerCase()] ?? o.direction,
      o.stage_name, o.stage_type_raw, o.object_name, o.database_name,
      c.name, c.type_name, c.precision, c.scale, c.nullable, o.detalhe].map(esc).join(';'))
  }
  return lines.join('\n')
}

// ── Página ────────────────────────────────────────────────────────
export default function ImpactoCampo() {
  const [dsx, setDsx] = useState('')
  const [campo, setCampo] = useState('')
  const [exato, setExato] = useState(false)
  const [incluirBkp, setIncluirBkp] = useState(false)
  const [incluirCopy, setIncluirCopy] = useState(false)
  const [tipoKey, setTipoKey] = useState('all')
  const [result, setResult] = useState<FieldImpactResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({})
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [planOpen, setPlanOpen] = useState(false)

  const { data: dsxData, isLoading: loadingDsx } = useQuery<{ base_dir: string; files: string[] }>({
    queryKey: ['dsx-files'], queryFn: () => apiFetch('/lineage/dsx-files'),
  })

  const buscar = async () => {
    if (!dsx) { toast.error('Selecione um arquivo .dsx'); return }
    if (!campo.trim()) { toast.error('Informe o campo a procurar'); return }
    setLoading(true); setResult(null); setCollapsed({}); setSelected(new Set())
    try {
      const preset = TIPO_PRESETS.find((p) => p.key === tipoKey) ?? TIPO_PRESETS[0]
      const q = new URLSearchParams({ dsx, campo: campo.trim(), exato: String(exato) })
      if (preset.tipo) { q.set('tipo', preset.tipo); q.set('excluir', String(preset.excluir)) }
      if (incluirBkp) q.set('incluir_bkp', 'true')
      if (incluirCopy) q.set('incluir_copy', 'true')
      const r = await apiFetch<FieldImpactResult>(`/lineage/field-impact?${q.toString()}`)
      setResult(r)
      if (r.total_jobs_impactados === 0) toast.info('Nenhum job impactado para esse filtro.')
    } catch (e: any) { toast.error(e.message) } finally { setLoading(false) }
  }

  const exportCsv = () => {
    if (!result) return
    const blob = new Blob([toCsv(result)], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url; a.download = `impacto_${result.project_name}_${result.termo}.csv`; a.click()
    URL.revokeObjectURL(url)
  }

  const toggle = (job: string) => setCollapsed((c) => ({ ...c, [job]: !c[job] }))

  const toggleSel = (k: string) => setSelected((s) => {
    const n = new Set(s); n.has(k) ? n.delete(k) : n.add(k); return n
  })
  const allKeys = (): string[] => {
    if (!result) return []
    const ks: string[] = []
    for (const job of result.jobs) for (const o of job.ocorrencias) for (const c of o.matched_columns)
      ks.push(selKey(job.job_name, o.stage_name, c.name))
    return ks
  }
  const selectAll = () => setSelected(new Set(allKeys()))
  const clearSel = () => setSelected(new Set())

  const collectItems = () => {
    if (!result) return []
    const out: any[] = []
    for (const job of result.jobs) for (const o of job.ocorrencias) for (const c of o.matched_columns) {
      if (!selected.has(selKey(job.job_name, o.stage_name, c.name))) continue
      out.push({
        dsx_file: result.dsx_file, project_name: result.project_name, job_name: job.job_name,
        stage_name: o.stage_name, stage_type: o.stage_type_raw, direction: o.direction,
        object_name: o.object_name, column_name: c.name, datatype_atual: c.type_name,
        precision: c.precision, scale: c.scale,
      })
    }
    return out
  }

  const totalKeys = allKeys().length

  return (
    <div className="flex flex-col gap-5">
      <div>
        <h1 className="text-lg font-semibold text-ink flex items-center gap-2">
          <FileSearch size={20} className="text-[#1A5FA8]" /> Impacto por Campo
        </h1>
        <p className="text-sm text-dim mt-1">
          Varre um <code>.dsx</code> e mostra quais jobs usam um campo, com o <strong>datatype</strong> de cada coluna.
          Selecione as colunas e envie para um <strong>plano de ajuste</strong>.
        </p>
      </div>

      {/* Busca */}
      <Card>
        <div className="flex flex-wrap items-end gap-3">
          <div className="w-52">
            <Select label="Arquivo .dsx" value={dsx} onChange={(e) => setDsx(e.target.value)} disabled={loadingDsx}>
              <option value="">{loadingDsx ? 'Carregando…' : 'Selecione…'}</option>
              {(dsxData?.files ?? []).map((f) => <option key={f} value={f}>{f}.dsx</option>)}
            </Select>
          </div>
          <div className="w-60">
            <Input label="Campo (ou parte do nome)" placeholder="ex.: CNPJ, CPF, cliente…"
              value={campo} onChange={(e) => setCampo(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') buscar() }} />
          </div>
          <div className="w-56">
            <Select label="Datatype" value={tipoKey} onChange={(e) => setTipoKey(e.target.value)}>
              {TIPO_PRESETS.map((p) => <option key={p.key} value={p.key}>{p.label}</option>)}
            </Select>
          </div>
          <label className="flex items-center gap-1.5 text-xs text-dim pb-2 select-none cursor-pointer">
            <input type="checkbox" checked={exato} onChange={(e) => setExato(e.target.checked)} /> Nome exato
          </label>
          <label className="flex items-center gap-1.5 text-xs text-dim pb-2 select-none cursor-pointer" title="Por padrão, jobs em pastas bkp/bckp/backup são ignorados">
            <input type="checkbox" checked={incluirBkp} onChange={(e) => setIncluirBkp(e.target.checked)} /> Incluir backup
          </label>
          <label className="flex items-center gap-1.5 text-xs text-dim pb-2 select-none cursor-pointer" title="Por padrão, jobs cópia (CopyOf…) são ignorados">
            <input type="checkbox" checked={incluirCopy} onChange={(e) => setIncluirCopy(e.target.checked)} /> Incluir cópias
          </label>
          <Button onClick={buscar} loading={loading} className="mb-0.5"><Search size={14} /> Buscar</Button>
          {result && result.total_ocorrencias > 0 && (
            <Button variant="secondary" onClick={exportCsv} className="mb-0.5"><Download size={14} /> CSV</Button>
          )}
        </div>
      </Card>

      {loading && <div className="flex items-center justify-center h-40"><Spinner size={36} /></div>}

      {!loading && result && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <KpiCard label="Jobs no DSX" value={result.total_jobs_dsx} color="blue" />
            <KpiCard label="Jobs impactados" value={result.total_jobs_impactados} color={result.total_jobs_impactados ? 'red' : 'green'} />
            <KpiCard label="Colunas (ocorrências)" value={result.total_ocorrencias} color="purple" />
            <KpiCard label="Filtro de tipo"
              value={filtroNome(result)}
              sub={`termo: ${result.termo}${result.exato ? ' (exato)' : ''}`} color="yellow" />
          </div>

          {(result.jobs_bkp_ignorados > 0 || result.jobs_copy_ignorados > 0) && (
            <p className="text-xs text-dim -mt-1">
              Ignorados: {result.jobs_bkp_ignorados} em pastas de backup, {result.jobs_copy_ignorados} cópia(s).
              Use <em>“Incluir backup”</em> / <em>“Incluir cópias”</em> para considerá-los.
            </p>
          )}

          {/* Barra de seleção */}
          {result.total_ocorrencias > 0 && (
            <div className="flex items-center gap-3 text-sm">
              <span className="text-dim">{selected.size} de {totalKeys} coluna(s) selecionada(s)</span>
              <button className="text-blue-500 hover:underline" onClick={selectAll}>selecionar todas</button>
              {selected.size > 0 && <button className="text-dim hover:underline" onClick={clearSel}>limpar</button>}
              <Button size="sm" className="ml-auto" disabled={selected.size === 0} onClick={() => setPlanOpen(true)}>
                <ListPlus size={14} /> Adicionar ao plano
              </Button>
            </div>
          )}

          {result.total_jobs_impactados === 0 ? (
            <Card><p className="text-sm text-dim text-center py-6">
              Nenhum job de <strong>{result.dsx_file}</strong> tem coluna que contém “{result.termo}”
              {result.filtro_tipos.length ? ` com o filtro de tipo aplicado` : ''}.
            </p></Card>
          ) : (
            <div className="flex flex-col gap-3">
              {result.jobs.map((job) => {
                const isCollapsed = collapsed[job.job_name]
                const nCols = job.ocorrencias.reduce((a, o) => a + o.matched_columns.length, 0)
                return (
                  <Card key={job.job_name} className="overflow-hidden">
                    <button onClick={() => toggle(job.job_name)}
                      className="flex items-center gap-2 w-full text-left -m-4 mb-0 p-4 hover:bg-edge/30 transition-colors">
                      {isCollapsed ? <ChevronRight size={16} className="text-dim" /> : <ChevronDown size={16} className="text-dim" />}
                      <span className="flex flex-col">
                        <span className="font-medium text-ink text-sm">{job.job_name}</span>
                        {job.category && <span className="text-[11px] text-dim font-mono">{job.category.replace(/\\\\/g, '\\')}</span>}
                      </span>
                      <span className="text-xs text-dim ml-auto">{job.ocorrencias.length} stage(s) · {nCols} coluna(s)</span>
                    </button>
                    {!isCollapsed && (
                      <div className="mt-3 overflow-x-auto">
                        <table className="w-full text-sm">
                          <thead>
                            <tr className="text-left text-xs text-dim border-b border-edge">
                              <th className="py-2 pr-3 font-medium">Direção</th>
                              <th className="py-2 pr-3 font-medium">Stage</th>
                              <th className="py-2 pr-3 font-medium">Objeto</th>
                              <th className="py-2 pr-3 font-medium">Tabela / Arquivo</th>
                              <th className="py-2 font-medium">Colunas · datatype (selecione)</th>
                            </tr>
                          </thead>
                          <tbody>
                            {job.ocorrencias.map((o, i) => (
                              <tr key={i} className="border-b border-edge/50 last:border-0 align-top">
                                <td className="py-2 pr-3"><DirBadge dir={o.direction} /></td>
                                <td className="py-2 pr-3">
                                  <span className="text-ink">{o.stage_name}</span>
                                  <span className="block text-[11px] text-dim">{o.stage_type_raw}</span>
                                </td>
                                <td className="py-2 pr-3 text-ink">{o.object_name}</td>
                                <td className="py-2 pr-3 text-dim max-w-[220px] truncate" title={o.detalhe ?? ''}>{o.detalhe || '—'}</td>
                                <td className="py-2">
                                  <div className="flex flex-wrap gap-1.5">
                                    {o.matched_columns.map((c) => {
                                      const k = selKey(job.job_name, o.stage_name, c.name)
                                      const on = selected.has(k)
                                      return (
                                        <label key={c.name}
                                          className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-xs border cursor-pointer ${typeCls(c.type_name)} ${on ? 'ring-2 ring-[#1A5FA8]/60' : ''}`}>
                                          <input type="checkbox" className="scale-90" checked={on} onChange={() => toggleSel(k)} />
                                          <span className="font-mono"><HighlightCol name={c.name} termo={result.termo} /></span>
                                          <span className="opacity-70 font-semibold">{typeLabel(c)}</span>
                                        </label>
                                      )
                                    })}
                                  </div>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </Card>
                )
              })}
            </div>
          )}
        </>
      )}

      {!loading && !result && (
        <Card><p className="text-sm text-dim text-center py-8">
          Selecione um arquivo <code>.dsx</code>, informe o campo e clique em <strong>Buscar</strong>.
        </p></Card>
      )}

      <AddToPlanModal open={planOpen} onClose={() => setPlanOpen(false)} itens={collectItems()}
        onDone={() => { setPlanOpen(false); setSelected(new Set()) }} />
    </div>
  )
}

// ── Modal: adicionar seleção a um plano (novo ou existente) ───────
function AddToPlanModal({ open, onClose, itens, onDone }: {
  open: boolean; onClose: () => void; itens: any[]; onDone: () => void
}) {
  const [mode, setMode] = useState<'novo' | 'existente'>('novo')
  const [nome, setNome] = useState('')
  const [planId, setPlanId] = useState('')
  const [alvo, setAlvo] = useState('VARCHAR')
  const [saving, setSaving] = useState(false)

  const { data } = useQuery<{ planos: PlanoLite[] }>({
    queryKey: ['change-plans'], queryFn: () => apiFetch('/change-plans'), enabled: open,
  })
  const abertos = (data?.planos ?? []).filter((p) => p.status === 'aberto')

  const salvar = async () => {
    const payload = itens.map((it) => ({ ...it, datatype_alvo: alvo.trim() || null }))
    setSaving(true)
    try {
      if (mode === 'novo') {
        if (!nome.trim()) { toast.error('Informe o nome do plano'); setSaving(false); return }
        await apiFetch('/change-plans', { method: 'POST', body: JSON.stringify({ nome: nome.trim(), itens: payload }) })
      } else {
        if (!planId) { toast.error('Selecione um plano'); setSaving(false); return }
        await apiFetch(`/change-plans/${planId}/items`, { method: 'POST', body: JSON.stringify({ itens: payload }) })
      }
      toast.success(`${payload.length} item(ns) enviados ao plano`)
      queryClient.invalidateQueries({ queryKey: ['change-plans'] })
      setNome('')
      onDone()
    } catch (e: any) { toast.error(e.message) } finally { setSaving(false) }
  }

  return (
    <Modal open={open} onClose={onClose} title="Adicionar ao plano de ajuste" size="md">
      <div className="flex flex-col gap-4">
        <p className="text-sm text-dim">{itens.length} coluna(s) selecionada(s).</p>

        <div className="flex gap-4 text-sm">
          <label className="flex items-center gap-1.5 cursor-pointer">
            <input type="radio" checked={mode === 'novo'} onChange={() => setMode('novo')} /> Novo plano
          </label>
          <label className="flex items-center gap-1.5 cursor-pointer">
            <input type="radio" checked={mode === 'existente'} onChange={() => setMode('existente')} /> Plano existente
          </label>
        </div>

        {mode === 'novo' ? (
          <Input label="Nome do plano" placeholder="ex.: Ajuste CNPJ → VARCHAR" value={nome} onChange={(e) => setNome(e.target.value)} />
        ) : (
          <Select label="Plano (abertos)" value={planId} onChange={(e) => setPlanId(e.target.value)}>
            <option value="">Selecione…</option>
            {abertos.map((p) => <option key={p.id} value={p.id}>{p.nome}</option>)}
          </Select>
        )}

        <Input label="Datatype alvo (aplicado a todos)" placeholder="ex.: VARCHAR" value={alvo} onChange={(e) => setAlvo(e.target.value)} />

        <div className="flex justify-end gap-2">
          <Button variant="secondary" size="sm" onClick={onClose}>Cancelar</Button>
          <Button size="sm" loading={saving} onClick={salvar}>Adicionar</Button>
        </div>
      </div>
    </Modal>
  )
}
