// MOCKUP visual (rota escondida, fora do menu) para validar o estilo do futuro
// editor de Etapas — designer de workflow estilo Informatica sobre React Flow.
// Não conecta à API: tudo é dado de exemplo hardcoded em EtapasCanvas.
import { EtapasCanvas } from '../components/etapas/EtapasCanvas'

export default function EtapasMockup() {
  return (
    <div className="flex flex-col gap-3">
      <div>
        <h1 className="text-lg font-semibold text-ink">
          Mockup — Etapas (estilo Informatica)
        </h1>
        <p className="text-sm text-dim">
          Validação visual do canvas de workflow. Dados de exemplo, sem conexão com a API.
        </p>
      </div>
      <div className="h-[calc(100vh-7rem)]">
        <EtapasCanvas />
      </div>
    </div>
  )
}
