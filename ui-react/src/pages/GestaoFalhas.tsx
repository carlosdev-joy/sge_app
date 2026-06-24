import { ShieldAlert } from 'lucide-react'
import { GestaoFalhasTab } from './Logs'

// "Gestão de Falhas" promovida a item de menu próprio no shell v2 (antes era só
// uma aba dentro de Logs). Reusa exatamente o mesmo componente — no shell clássico
// a aba continua no Logs, que não tem esse menu. Zero duplicação de lógica.
export default function GestaoFalhas() {
  return (
    <div className="flex flex-col gap-5">
      <div>
        <h1 className="text-lg font-semibold text-ink flex items-center gap-2">
          <ShieldAlert size={20} className="text-[#1A5FA8]" /> Gestão de Falhas
        </h1>
        <p className="text-sm text-dim mt-1">Falhas a tratar: assuma, investigue e resolva — individual ou em massa.</p>
      </div>
      <GestaoFalhasTab />
    </div>
  )
}
