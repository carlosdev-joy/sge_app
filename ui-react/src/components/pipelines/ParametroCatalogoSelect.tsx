import { Select } from '../ui/Input'
import { legendaParametro, type CatalogoParam } from '../../lib/pipelineCatalogo'

export function ParametroCatalogoSelect({ params, value, onChange, label = 'Consultar parâmetro', disabled = false }: {
  params: CatalogoParam[]; value: string; onChange: (name: string) => void; label?: string; disabled?: boolean
}) {
  const p = params.find(p => p.param_name === value)
  return <Select label={label} value={p ? value : ''} disabled={disabled} onChange={e => onChange(e.target.value)}
    ajuda={legendaParametro(p)}>
    <option value="">Selecione um parâmetro</option>
    {params.filter(p => p.param_name.trim()).map((p, i) => <option key={p.id ?? i} value={p.param_name}>
      [{p.param_destino === 'orquestra' ? 'ORQ' : 'DS'}] {p.param_name}
    </option>)}
  </Select>
}
