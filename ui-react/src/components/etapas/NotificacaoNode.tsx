// Nó de notificação (Teams) do React Flow. Mesmo visual do EtapaNode (tile de
// ícone + nome embaixo), com identidade própria (acento teal + ícone de sino).
// Um target handle (entrada, à esquerda) e um source handle (saída, à direita)
// — pode ser ligado por dependência NORMAL ou virar ramo de uma decisão.
import { memo } from 'react'
import { Handle, Position, type NodeProps } from '@xyflow/react'
import { BellRing } from 'lucide-react'

// Config do nó (round-trip com /fluxo no campo `notify`). Guardamos o objeto
// inteiro no `data` para ecoar no save; `label` é um resumo curto p/ o card.
export interface NotificacaoNodeData {
  name: string
  notify: { grupo_id: number | null; template_id: number | null; mensagem: string }
  label: string
  isNew?: boolean
  [k: string]: unknown
}

// Bolinha discreta dos handles — mesma do EtapaNode, neutra nos dois temas.
const HANDLE_CLS =
  '!h-2.5 !w-2.5 !rounded-full !border-2 !border-panel !bg-slate-400 dark:!bg-slate-500'

// Tile do ícone tem ~44px de altura no topo; handles no seu centro vertical.
const HANDLE_Y = 16

function NotificacaoNodeImpl({ data, selected }: NodeProps & { data: NotificacaoNodeData }) {
  return (
    <div className="group flex w-[128px] flex-col items-center">
      <Handle
        type="target"
        position={Position.Left}
        className={HANDLE_CLS}
        style={{ top: HANDLE_Y }}
      />

      {/* Tile do ícone (teal) — ícone de sino branco; anel de seleção no tile. */}
      <div
        className={[
          'flex h-8 w-8 items-center justify-center rounded-xl bg-teal-500 text-white shadow-sm transition-shadow',
          'group-hover:shadow-md',
          selected ? 'ring-2 ring-blue-500 ring-offset-2 ring-offset-canvas' : '',
        ].join(' ')}
      >
        <BellRing size={16} strokeWidth={2} />
      </div>

      {/* Nome embaixo — até 2 linhas, sem truncar. */}
      <p
        className="mt-1.5 line-clamp-2 break-words text-center text-[11px] font-semibold leading-tight text-ink"
        title={data.name}
      >
        {data.name}
      </p>

      {/* Linha de baixo: resumo curto do destino/modelo (label). */}
      <p className="mt-0.5 line-clamp-1 text-center text-[9px] leading-tight text-dim" title={data.label}>
        {data.label}
      </p>

      <Handle
        type="source"
        position={Position.Right}
        className={HANDLE_CLS}
        style={{ top: HANDLE_Y }}
      />
    </div>
  )
}

export const NotificacaoNode = memo(NotificacaoNodeImpl)
