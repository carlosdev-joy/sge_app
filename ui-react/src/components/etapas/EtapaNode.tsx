// Node card custom do React Flow para uma etapa do pipeline (mockup).
// Visual estilo designer de workflow: chip de ícone colorido por tipo, nome em
// destaque, subtítulo mono com o comando/path e rodapé com badge do tipo + ordem.
import { memo } from 'react'
import { Handle, Position, type NodeProps } from '@xyflow/react'
import { TYPE_META, type EtapaType } from './types'

export interface EtapaNodeData {
  name: string
  type: EtapaType
  command: string
  order: number
  [key: string]: unknown
}

// Bolinha discreta dos handles — neutra e coerente nos dois temas.
const HANDLE_CLS =
  '!h-2.5 !w-2.5 !rounded-full !border-2 !border-panel !bg-slate-400 dark:!bg-slate-500'

function EtapaNodeImpl({ data, selected }: NodeProps & { data: EtapaNodeData }) {
  const meta = TYPE_META[data.type]
  const Icon = meta.icon

  return (
    <div
      className={[
        'group w-[190px] rounded-lg border bg-panel shadow-sm transition-shadow',
        'hover:shadow-md',
        selected
          ? 'border-blue-500 ring-2 ring-blue-500'
          : 'border-edge',
      ].join(' ')}
    >
      <Handle type="target" position={Position.Left} className={HANDLE_CLS} />

      {/* Cabeçalho: chip de ícone + nome */}
      <div className="flex items-center gap-2 px-3 pt-2.5">
        <span
          className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-md ${meta.chip}`}
        >
          <Icon size={15} strokeWidth={2.2} />
        </span>
        <span className="min-w-0 flex-1 truncate text-sm font-semibold text-ink">
          {data.name}
        </span>
      </div>

      {/* Subtítulo: comando / path em mono */}
      <div className="px-3 pb-2 pt-1">
        <p className="truncate font-mono text-xs text-dim" title={data.command}>
          {data.command}
        </p>
      </div>

      {/* Rodapé: badge do tipo + ordem */}
      <div className="flex items-center justify-between border-t border-edge px-3 py-1.5">
        <span
          className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${meta.badge}`}
        >
          {meta.label}
        </span>
        <span className="font-mono text-[10px] text-dim">#{data.order}</span>
      </div>

      <Handle type="source" position={Position.Right} className={HANDLE_CLS} />
    </div>
  )
}

export const EtapaNode = memo(EtapaNodeImpl)
