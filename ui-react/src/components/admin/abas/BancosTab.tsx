import { ServidorTab } from '../bancos/ServidorTab'
import { MonitoramentoTab } from '../bancos/MonitoramentoTab'

// ── Integrações › Bancos & Monitoramento ────────────────────────
// Decisão explícita da spec (docs/spec-admin-reestruturacao.md, F3): até a F2
// eram duas abas vizinhas — "Bancos do servidor" (integracoes/bancos, id antigo
// `servidor`) e "Monitoramento de tabelas" (integracoes/monitoramento, id
// antigo `monitor`). Juntas aqui, Servidor em cima e Monitoramento embaixo,
// cada seção intacta no seu arquivo em components/admin/bancos/. Não separar
// nem inverter a ordem.
export function BancosTab() {
  return (
    <div className="flex flex-col gap-6">
      <ServidorTab />
      <div className="border-t border-edge pt-6">
        <MonitoramentoTab />
      </div>
    </div>
  )
}
