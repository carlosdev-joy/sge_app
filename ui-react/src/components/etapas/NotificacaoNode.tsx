// Nó de notificação (Teams) do React Flow. Card compacto no estilo de EtapaNode,
// mas com identidade própria (acento teal + ícone de sino). Um target handle
// (entrada, à esquerda) e um source handle (saída, à direita) — pode ser ligado
// por dependência NORMAL ou virar ramo de uma decisão, como uma etapa.
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

function NotificacaoNodeImpl({ data, selected }: NodeProps & { data: NotificacaoNodeData }) {
  return (
    <div
      className={[
        'group w-[148px] rounded-lg border bg-panel shadow-sm transition-shadow',
        'hover:shadow-md',
        selected ? 'border-blue-500 ring-2 ring-blue-500' : 'border-edge',
      ].join(' ')}
    >
      <Handle type="target" position={Position.Left} className={HANDLE_CLS} />

      {/* Cabeçalho: chip de ícone (teal) + nome */}
      <div className="flex items-center gap-1.5 px-2 pt-1.5">
        <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded bg-teal-500 text-white">
          <BellRing size={12} strokeWidth={2.2} />
        </span>
        <span className="min-w-0 flex-1 truncate text-xs font-semibold text-ink">
          {data.name}
        </span>
      </div>

      {/* Subtítulo: resumo do destino/modelo (label) */}
      <div className="px-2 pb-1.5 pt-0.5">
        <p className="truncate text-[10px] text-dim" title={data.label}>
          {data.label}
        </p>
      </div>

      {/* Rodapé: badge "Notificação" */}
      <div className="flex items-center justify-between border-t border-edge px-2 py-1">
        <span className="rounded px-1 py-0.5 text-[9px] font-semibold bg-teal-50 text-teal-700 border border-teal-200 dark:bg-teal-900/30 dark:text-teal-300 dark:border-teal-800">
          Notificação
        </span>
      </div>

      <Handle type="source" position={Position.Right} className={HANDLE_CLS} />
    </div>
  )
}

export const NotificacaoNode = memo(NotificacaoNodeImpl)
