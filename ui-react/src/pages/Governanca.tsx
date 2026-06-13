import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '../lib/api'
import { Button } from '../components/ui/Button'
import { Input, Select } from '../components/ui/Input'
import { Badge } from '../components/ui/Badge'
import { PageSpinner } from '../components/ui/Spinner'
import { Tabs } from '../components/ui/Tabs'
import type { LineageJob } from '../types'
import { Search } from 'lucide-react'

function LineageView() {
  const [pipeline, setPipeline] = useState('')
  const [searched, setSearched] = useState('')

  const { data, isLoading } = useQuery<{ jobs: LineageJob[] }>({
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
            <div key={job.job_name} className="bg-[#1a1d27] border border-[#2a2d3a] rounded-lg p-4">
              <div className="font-mono text-sm text-blue-400 mb-3">{job.job_name}</div>
              <div className="flex gap-6">
                <div className="flex-1">
                  <div className="text-xs text-[#94a3b8] mb-2 font-medium">ORIGENS</div>
                  <div className="flex flex-col gap-1">
                    {job.origens.map((o, i) => (
                      <div key={i} className="flex items-center gap-2 text-xs">
                        <span className="text-green-400">←</span>
                        <span className="text-[#e2e8f0] font-mono">{o.nome}</span>
                        <Badge value={o.tipo} />
                        {o.banco && <span className="text-[#94a3b8]">{o.banco}</span>}
                      </div>
                    ))}
                  </div>
                </div>
                <div className="flex-1">
                  <div className="text-xs text-[#94a3b8] mb-2 font-medium">DESTINOS</div>
                  <div className="flex flex-col gap-1">
                    {job.destinos.map((d, i) => (
                      <div key={i} className="flex items-center gap-2 text-xs">
                        <span className="text-blue-400">→</span>
                        <span className="text-[#e2e8f0] font-mono">{d.nome}</span>
                        <Badge value={d.tipo} />
                        {d.banco && <span className="text-[#94a3b8]">{d.banco}</span>}
                      </div>
                    ))}
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

function Catalogo() {
  const [query, setQuery] = useState('')
  const [tipo, setTipo] = useState('')
  const [searched, setSearched] = useState<{ q: string; tipo: string } | null>(null)

  const { data, isLoading } = useQuery<{ itens: any[] }>({
    queryKey: ['catalogo', searched],
    queryFn: () => apiFetch('/catalogo', {
      method: 'POST',
      body: JSON.stringify({ modo: 'busca', query: searched!.q, tipo: searched!.tipo || undefined }),
    }),
    enabled: !!searched,
  })

  return (
    <div className="flex flex-col gap-4">
      <div className="flex gap-3 items-end flex-wrap">
        <Input label="Buscar" value={query} onChange={e => setQuery(e.target.value)} placeholder="tabela, arquivo, pipeline…" className="w-72" />
        <Select label="Tipo" value={tipo} onChange={e => setTipo(e.target.value)} className="w-36">
          <option value="">Todos</option>
          <option>tabela</option>
          <option>arquivo</option>
          <option>pipeline</option>
        </Select>
        <Button onClick={() => setSearched({ q: query, tipo })} disabled={!query}><Search size={13} /> Buscar</Button>
      </div>
      {isLoading && <PageSpinner />}
      {data?.itens && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {data.itens.map((item, i) => (
            <div key={i} className="bg-[#1a1d27] border border-[#2a2d3a] rounded-lg p-4">
              <div className="flex items-start justify-between gap-2 mb-2">
                <span className="font-mono text-sm text-[#e2e8f0]">{item.nome}</span>
                <Badge value={item.tipo} />
              </div>
              {item.banco && <div className="text-xs text-[#94a3b8]">{item.banco}</div>}
              {item.classificacao && <Badge value={item.classificacao} />}
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
      <h1 className="text-lg font-bold text-[#e2e8f0]">Governança</h1>
      <Tabs tabs={[{ id: 'lineage', label: 'Lineage' }, { id: 'catalogo', label: 'Catálogo de Dados' }]} active={tab} onChange={setTab} />
      <div className="mt-2">{tab === 'lineage' ? <LineageView /> : <Catalogo />}</div>
    </div>
  )
}
