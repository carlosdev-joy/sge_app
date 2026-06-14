import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '../lib/api'
import { Button } from '../components/ui/Button'
import { Input, Select } from '../components/ui/Input'
import { Badge } from '../components/ui/Badge'
import { PageSpinner } from '../components/ui/Spinner'
import { Tabs } from '../components/ui/Tabs'
import { Search } from 'lucide-react'

interface LineageAsset { object_name: string; type_label?: string; object_type?: string; database_name?: string }
interface LineageJobRow { job_name: string; execution_order: number; origens: LineageAsset[]; destinos: LineageAsset[]; transformacoes: LineageAsset[] }

function LineageView() {
  const [pipeline, setPipeline] = useState('')
  const [searched, setSearched] = useState('')

  const { data, isLoading } = useQuery<{ jobs: LineageJobRow[] }>({
    queryKey: ['lineage', searched],
    queryFn: () => apiFetch(`/lineage?pipeline_name=${encodeURIComponent(searched)}`),
    enabled: !!searched,
  })

  return (
    <div className="flex flex-col gap-4">
      <div className="flex gap-3 items-end">
        <Input label="Pipeline" value={pipeline} onChange={e => setPipeline(e.target.value)} placeholder="nome do pipeline" className="w-72" />
        <Button onClick={() => setSearched(pipeline)} disabled={!pipeline}><Search size={13} /> Carregar</Button>
      </div>
      {isLoading && <PageSpinner />}
      {data?.jobs && (
        <div className="flex flex-col gap-3">
          {data.jobs.map((job) => (
            <div key={job.job_name} className="bg-panel border border-edge rounded-lg p-4">
              <div className="font-mono text-sm text-blue-400 mb-3">{job.job_name}</div>
              <div className="flex gap-6">
                <div className="flex-1">
                  <div className="text-xs text-dim mb-2 font-medium">ORIGENS</div>
                  <div className="flex flex-col gap-1">
                    {job.origens.map((o, i) => (
                      <div key={i} className="flex items-center gap-2 text-xs">
                        <span className="text-green-400">←</span>
                        <span className="text-ink font-mono">{o.object_name}</span>
                        {(o.type_label || o.object_type) && <Badge value={o.type_label || o.object_type} />}
                        {o.database_name && <span className="text-dim">{o.database_name}</span>}
                      </div>
                    ))}
                    {job.origens.length === 0 && <span className="text-xs text-[#4a4d5a]">—</span>}
                  </div>
                </div>
                <div className="flex-1">
                  <div className="text-xs text-dim mb-2 font-medium">DESTINOS</div>
                  <div className="flex flex-col gap-1">
                    {job.destinos.map((d, i) => (
                      <div key={i} className="flex items-center gap-2 text-xs">
                        <span className="text-blue-400">→</span>
                        <span className="text-ink font-mono">{d.object_name}</span>
                        {(d.type_label || d.object_type) && <Badge value={d.type_label || d.object_type} />}
                        {d.database_name && <span className="text-dim">{d.database_name}</span>}
                      </div>
                    ))}
                    {job.destinos.length === 0 && <span className="text-xs text-[#4a4d5a]">—</span>}
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

interface Asset {
  asset_name: string
  asset_type: string
  database_name?: string
  pipeline_count?: number
  as_origem?: number
  as_destino?: number
}
function Catalogo() {
  const [query, setQuery] = useState('')
  const [tipo, setTipo] = useState('')
  const [searched, setSearched] = useState<{ q: string; tipo: string } | null>(null)

  const { data, isLoading } = useQuery<{ assets: Asset[] }>({
    queryKey: ['catalogo', searched],
    queryFn: () => apiFetch('/catalogo', {
      method: 'POST',
      body: JSON.stringify({ mode: 'browse', search: searched!.q, asset_type: searched!.tipo || undefined, top_n: 100 }),
    }),
    enabled: !!searched,
  })

  return (
    <div className="flex flex-col gap-4">
      <div className="flex gap-3 items-end flex-wrap">
        <Input label="Buscar" value={query} onChange={e => setQuery(e.target.value)} placeholder="nome da tabela ou arquivo…" className="w-72" />
        <Select label="Tipo" value={tipo} onChange={e => setTipo(e.target.value)} className="w-36">
          <option value="">Todos</option>
          <option value="tabela">tabela</option>
          <option value="arquivo">arquivo</option>
        </Select>
        <Button onClick={() => setSearched({ q: query, tipo })}><Search size={13} /> Buscar</Button>
      </div>
      {isLoading && <PageSpinner />}
      {data?.assets && (
        data.assets.length === 0
          ? <div className="text-sm text-dim py-8 text-center">Nenhum ativo encontrado.</div>
          : <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
              {data.assets.map((item, i) => (
                <div key={i} className="bg-panel border border-edge rounded-lg p-4">
                  <div className="flex items-start justify-between gap-2 mb-2">
                    <span className="font-mono text-sm text-ink break-all">{item.asset_name}</span>
                    <Badge value={item.asset_type} />
                  </div>
                  {item.database_name && <div className="text-xs text-dim mb-2">{item.database_name}</div>}
                  <div className="flex gap-3 text-xs text-dim">
                    <span>{item.pipeline_count ?? 0} pipelines</span>
                    <span className="text-green-400">←{item.as_origem ?? 0}</span>
                    <span className="text-blue-400">→{item.as_destino ?? 0}</span>
                  </div>
                </div>
              ))}
            </div>
      )}
    </div>
  )
}

export default function Governanca() {
  const [tab, setTab] = useState('lineage')
  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-lg font-bold text-ink">Governança</h1>
      <Tabs tabs={[{ id: 'lineage', label: 'Lineage' }, { id: 'catalogo', label: 'Catálogo de Dados' }]} active={tab} onChange={setTab} />
      <div className="mt-2">{tab === 'lineage' ? <LineageView /> : <Catalogo />}</div>
    </div>
  )
}
