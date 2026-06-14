import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '../lib/api'
import { Card, KpiCard } from '../components/ui/Card'
import { Input, Select } from '../components/ui/Input'
import { Button } from '../components/ui/Button'
import { Spinner } from '../components/ui/Spinner'
import { toast } from '../components/ui/Toast'
import { Search, Download, FileSearch, ChevronDown, ChevronRight } from 'lucide-react'

// ── Tipos do retorno de /lineage/field-impact ────────────────────
interface Ocorrencia {
  stage_name: string | null
  direction: string | null
  object_name: string | null
  object_type: string | null
  stage_type_raw: string | null
  database_name: string | null
  detalhe: string | null
  matched_columns: string[]
  total_columns: number
}
interface JobImpact {
  job_name: string
  ocorrencias: Ocorrencia[]
}
interface FieldImpactResult {
  sucesso: boolean
  project_name: string
  dsx_file: string
  termo: string
  exato: boolean
  total_jobs_dsx: number
  total_jobs_impactados: number
  total_ocorrencias: number
  jobs: JobImpact[]
}

// ── Cor da direção do stage ───────────────────────────────────────
const DIR_LABEL: Record<string, string> = {
  origem: 'Origem', destino: 'Destino', transformacao: 'Transformação',
}
const DIR_CLS: Record<string, string> = {
  origem:         'bg-blue-100 text-blue-700 border-blue-300 dark:bg-blue-900/40 dark:text-blue-300 dark:border-blue-800',
  destino:        'bg-green-100 text-green-700 border-green-300 dark:bg-green-900/40 dark:text-green-300 dark:border-green-800',
  transformacao:  'bg-amber-100 text-amber-700 border-amber-300 dark:bg-yellow-900/40 dark:text-yellow-300 dark:border-yellow-800',
}
function DirBadge({ dir }: { dir: string | null }) {
  const k = (dir ?? '').toLowerCase()
  const cls = DIR_CLS[k] ?? 'bg-slate-100 text-slate-600 border-slate-300 dark:bg-gray-800 dark:text-gray-400 dark:border-gray-700'
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium whitespace-nowrap border ${cls}`}>
      {DIR_LABEL[k] ?? (dir || '—')}
    </span>
  )
}

// Destaca, no nome da coluna, o trecho que casou com o termo buscado.
function HighlightCol({ col, termo }: { col: string; termo: string }) {
  const i = termo ? col.toLowerCase().indexOf(termo.toLowerCase()) : -1
  if (i < 0) return <>{col}</>
  return (
    <>
      {col.slice(0, i)}
      <mark className="bg-yellow-300 text-slate-900 rounded px-0.5">{col.slice(i, i + termo.length)}</mark>
      {col.slice(i + termo.length)}
    </>
  )
}

// ── CSV ───────────────────────────────────────────────────────────
function toCsv(r: FieldImpactResult): string {
  const head = ['dsx', 'job', 'direcao', 'stage', 'objeto', 'tipo_objeto', 'base', 'coluna', 'detalhe']
  const esc = (v: unknown) => {
    const s = v == null ? '' : String(v)
    return /[",;\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
  }
  const lines = [head.join(';')]
  for (const job of r.jobs) {
    for (const o of job.ocorrencias) {
      for (const col of o.matched_columns) {
        lines.push([
          r.dsx_file, job.job_name, DIR_LABEL[(o.direction ?? '').toLowerCase()] ?? o.direction,
          o.stage_name, o.object_name, o.object_type, o.database_name, col, o.detalhe,
        ].map(esc).join(';'))
      }
    }
  }
  return lines.join('\n')
}

// ── Página ────────────────────────────────────────────────────────
export default function ImpactoCampo() {
  const [dsx, setDsx] = useState('')
  const [campo, setCampo] = useState('')
  const [exato, setExato] = useState(false)
  const [result, setResult] = useState<FieldImpactResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({})

  const { data: dsxData, isLoading: loadingDsx } = useQuery<{ base_dir: string; files: string[] }>({
    queryKey: ['dsx-files'],
    queryFn: () => apiFetch('/lineage/dsx-files'),
  })

  const buscar = async () => {
    if (!dsx) { toast.error('Selecione um arquivo .dsx'); return }
    if (!campo.trim()) { toast.error('Informe o campo a procurar'); return }
    setLoading(true)
    setResult(null)
    setCollapsed({})
    try {
      const q = new URLSearchParams({ dsx, campo: campo.trim(), exato: String(exato) })
      const r = await apiFetch<FieldImpactResult>(`/lineage/field-impact?${q.toString()}`)
      setResult(r)
      if (r.total_jobs_impactados === 0) toast.info('Nenhum job impactado para esse termo.')
    } catch (e: any) {
      toast.error(e.message)
    } finally {
      setLoading(false)
    }
  }

  const exportCsv = () => {
    if (!result) return
    const blob = new Blob([toCsv(result)], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `impacto_${result.project_name}_${result.termo}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  const toggle = (job: string) => setCollapsed((c) => ({ ...c, [job]: !c[job] }))

  return (
    <div className="flex flex-col gap-5">
      {/* Cabeçalho */}
      <div>
        <h1 className="text-lg font-semibold text-ink flex items-center gap-2">
          <FileSearch size={20} className="text-[#1A5FA8]" /> Impacto por Campo
        </h1>
        <p className="text-sm text-dim mt-1">
          Varre um arquivo <code>.dsx</code> e mostra quais jobs usam um campo —
          busca por parte do nome (ex.: <code>CNPJ</code> casa <code>NUM_CNPJ</code>, <code>CPF_CNPJ</code>…).
        </p>
      </div>

      {/* Busca */}
      <Card>
        <div className="flex flex-wrap items-end gap-3">
          <div className="w-60">
            <Select
              label="Arquivo .dsx"
              value={dsx}
              onChange={(e) => setDsx(e.target.value)}
              disabled={loadingDsx}
            >
              <option value="">{loadingDsx ? 'Carregando…' : 'Selecione…'}</option>
              {(dsxData?.files ?? []).map((f) => (
                <option key={f} value={f}>{f}.dsx</option>
              ))}
            </Select>
          </div>
          <div className="w-72">
            <Input
              label="Campo (ou parte do nome)"
              placeholder="ex.: CNPJ, CPF, cliente…"
              value={campo}
              onChange={(e) => setCampo(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') buscar() }}
            />
          </div>
          <label className="flex items-center gap-1.5 text-xs text-dim pb-2 select-none cursor-pointer">
            <input type="checkbox" checked={exato} onChange={(e) => setExato(e.target.checked)} />
            Correspondência exata
          </label>
          <Button onClick={buscar} loading={loading} className="mb-0.5">
            <Search size={14} /> Buscar
          </Button>
          {result && result.total_ocorrencias > 0 && (
            <Button variant="secondary" onClick={exportCsv} className="mb-0.5">
              <Download size={14} /> CSV
            </Button>
          )}
        </div>
      </Card>

      {/* Estados */}
      {loading && (
        <div className="flex items-center justify-center h-40"><Spinner size={36} /></div>
      )}

      {!loading && result && (
        <>
          {/* KPIs */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <KpiCard label="Jobs no DSX"       value={result.total_jobs_dsx} color="blue" />
            <KpiCard label="Jobs impactados"   value={result.total_jobs_impactados} color={result.total_jobs_impactados ? 'red' : 'green'} />
            <KpiCard label="Ocorrências"       value={result.total_ocorrencias} color="purple" />
            <KpiCard label="Termo"             value={result.termo} sub={result.exato ? 'exato' : 'contém'} color="yellow" />
          </div>

          {/* Resultados por job */}
          {result.total_jobs_impactados === 0 ? (
            <Card>
              <p className="text-sm text-dim text-center py-6">
                Nenhum job de <strong>{result.dsx_file}</strong> usa um campo que contém “{result.termo}”.
              </p>
            </Card>
          ) : (
            <div className="flex flex-col gap-3">
              {result.jobs.map((job) => {
                const isCollapsed = collapsed[job.job_name]
                const nCols = job.ocorrencias.reduce((a, o) => a + o.matched_columns.length, 0)
                return (
                  <Card key={job.job_name} className="overflow-hidden">
                    <button
                      onClick={() => toggle(job.job_name)}
                      className="flex items-center gap-2 w-full text-left -m-4 mb-0 p-4 hover:bg-edge/30 transition-colors"
                    >
                      {isCollapsed ? <ChevronRight size={16} className="text-dim" /> : <ChevronDown size={16} className="text-dim" />}
                      <span className="font-medium text-ink text-sm">{job.job_name}</span>
                      <span className="text-xs text-dim ml-auto">
                        {job.ocorrencias.length} stage(s) · {nCols} coluna(s)
                      </span>
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
                              <th className="py-2 font-medium">Colunas que casaram</th>
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
                                <td className="py-2 pr-3 text-dim max-w-[260px] truncate" title={o.detalhe ?? ''}>
                                  {o.detalhe || '—'}
                                </td>
                                <td className="py-2">
                                  <div className="flex flex-wrap gap-1">
                                    {o.matched_columns.map((c) => (
                                      <span key={c} className="inline-flex items-center px-1.5 py-0.5 rounded text-xs font-mono bg-edge/60 text-ink border border-edge">
                                        <HighlightCol col={c} termo={result.termo} />
                                      </span>
                                    ))}
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
        <Card>
          <p className="text-sm text-dim text-center py-8">
            Selecione um arquivo <code>.dsx</code>, informe o campo e clique em <strong>Buscar</strong>.
          </p>
        </Card>
      )}
    </div>
  )
}
