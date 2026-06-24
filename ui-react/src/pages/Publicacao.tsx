import { Rocket } from 'lucide-react'
import { FactoryRuns } from '../components/factory/FactoryRuns'

// "Publicação" (antiga aba "Regeneração de DAGs" dentro de Logs) promovida a item
// de menu próprio no shell v2. Reusa exatamente o mesmo componente FactoryRuns —
// no shell clássico a aba continua no Logs, que não tem esse menu. Zero duplicação.
export default function Publicacao() {
  return (
    <div className="flex flex-col gap-5">
      <div>
        <h1 className="text-lg font-semibold text-ink flex items-center gap-2">
          <Rocket size={20} className="text-[#1A5FA8]" /> Publicação
        </h1>
        <p className="text-sm text-dim mt-1">Histórico de geração dos DAGs a partir dos pipelines.</p>
      </div>
      <FactoryRuns />
    </div>
  )
}
