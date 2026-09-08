// Painel lateral (Sheet) de um stage — o conteúdo está em ConteudoStageIsx.
import { Sheet } from '../../ui/Sheet'
import { ConteudoStageIsx } from './ConteudoStageIsx'
import { idDoStage, type StageIsx } from '../../../lib/lineageIsx'

export function PainelStageIsx({ stage, onClose }: { stage: StageIsx | null; onClose: () => void }) {
  return (
    <Sheet open={stage !== null} onClose={onClose} title={stage ? idDoStage(stage) : undefined} widthClass="max-w-3xl">
      {stage && <ConteudoStageIsx stage={stage} />}
    </Sheet>
  )
}
